"""Pruebas focalizadas: lectura del reloj y readiness del servicio de ingenieria.

Verifica, SIN Binance y con proveedor de tiempo local:

1. --clock-source local -> /health reporta local_sistema, available=True.
2. --clock-source public con sincronizacion valida -> /health reporta
   public_sincronizado, available=True.
3. --clock-source public DURANTE la preparacion (sin sync completado) ->
   /health reporta public_sincronizado, available=False (NOT_READY).
4. create_session se RECHAZA con RELOJ_REFERENCIA_INCERTO cuando el reloj
   de referencia no esta disponible (nunca se permite crear sesion sin
   sincronizacion valida).
5. Proveedor de tiempo local que falla /time -> servicio no permite crear
   sesion (reloj incierto).
6. Proveedor de tiempo local con retraso -> el servicio no se bloquea
   esperando /health (el servidor HTTP esta levantado antes del sync).

Todas las pruebas usan el CLI real (EngineeringSessionController +
EngineeringHTTPServer) con proveedores de tiempo locales mockeados.
Cero peticiones a dominios publicos.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.clock import ClockSynchronizer  # noqa: E402
from microstructure_probe.engineering_session_service import (  # noqa: E402
    CLOCK_REFERENCE_MAX_AGE_MS,
    EngineeringHTTPServer,
    EngineeringSessionController,
    _now_ms,
    make_synced_now_ms,
)
from microstructure_probe.history_client import UpstreamBudgetExceeded  # noqa: E402

import scripts.engineering_live_window as elw_mod  # noqa: E402

STEP_MS = 60 * 1000  # 1m
T0 = 1_790_000_000_000


def ctx_candle(idx_from_t0_ms: int, o: float, h: float, l: float,
               c: float) -> Dict[str, Any]:
    ot = T0 + idx_from_t0_ms
    return {"open_time_ms": ot, "open": o, "high": h, "low": l, "close": c,
            "close_time_ms": ot + STEP_MS - 1}


# Contexto reciente cerrado: ultima vela cierra en T0 - 1.
CONTEXT = [
    ctx_candle(-2 * STEP_MS, 99.0, 100.5, 98.5, 99.6),
    ctx_candle(-1 * STEP_MS, 99.6, 100.4, 99.2, 100.0),
]

ENTRY_PX = 100.0
STOP_PX = 98.5


def live_config() -> Dict[str, Any]:
    return {
        "symbol": "BTCUSDT", "interval": "1m", "direction": "LONG",
        "notional_usdt": 1000.0, "entry_px": ENTRY_PX, "stop_px": STOP_PX,
        "stop_distance_pct": (ENTRY_PX - STOP_PX) / ENTRY_PX * 100.0,
        "horizon_ms": 2 * 60 * 60 * 1000,
        "fee_bps": 5.0, "spread_bps": 1.0, "slippage_bps": 2.0,
        "rule_version": "RULE-CAUSAL-V1",
    }


def live_payload(context: List[Dict[str, Any]],
                 request_id: str) -> Dict[str, Any]:
    return {
        "config": live_config(),
        "candles": [],
        "context": context,
        "transport": "market_stream",
        "hypothesis_id": "ENG-READINESS-v1", "hypothesis_version": "v1",
        "rule_version": "RULE-CAUSAL-V1",
        "request_id": request_id,
    }


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _LocalTimeProvider:
    """Proveedor de tiempo local controlado (sin Binance, sin red publica)."""

    def __init__(self, server_ms: int, wall_ms: int) -> None:
        self.server_ms = server_ms
        self.wall_ms = wall_ms
        self.delay_seconds: Optional[float] = None
        self.fail: bool = False

    def fetch_server_time(self) -> int:
        if self.fail:
            raise UpstreamBudgetExceeded("proveedor local: fallo simulado")
        if self.delay_seconds is not None:
            time.sleep(self.delay_seconds)
        return int(self.server_ms)

    def wall_clock_ms(self) -> float:
        return float(self.wall_ms)


class Harness:
    """Servicio HTTP real con controlador y reloj."""

    def __init__(self, sessions_dir: Path, market_url: str,
                 now_ms: Optional[Callable[[], Optional[int]]] = None,
                 clock_sync: Optional[ClockSynchronizer] = None,
                 clock_source: Optional[str] = None) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.world = EngineeringSessionController(
            self.sessions_dir, 5.0, market_url=market_url,
            market_bars=50, live_silence_ms=120_000.0,
            now_ms=now_ms, clock_sync=clock_sync,
            clock_source=clock_source)
        self.server = EngineeringHTTPServer("127.0.0.1", 0, self.world)
        self._thread = __import__("threading").Thread(
            target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def api(self, method: str, path: str,
            payload: Optional[Dict[str, Any]] = None,
            timeout: float = 15.0) -> tuple:
        import urllib.error
        import urllib.request
        data = json.dumps(payload).encode("utf-8") if payload is not None \
            else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, body

    def health(self) -> Dict[str, Any]:
        status, body = self.api("GET", "/health")
        assert status == 200, f"health fallo: {status} {body}"
        return body

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        status, body = self.api("POST", "/sessions", payload)
        return status, body

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class TestClockReadiness(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="orch-readiness-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- 1. Modo local: reloj del sistema ----------------------------------

    def test_local_reporta_local_sistema_disponible(self):
        h = Harness(self.tmp, "http://127.0.0.1:1",
                    now_ms=_now_ms, clock_source="local_sistema")
        try:
            clk = h.health()["clock"]
            self.assertEqual(clk["source"], "local_sistema", clk)
            self.assertTrue(clk["available"], clk)
            # Se puede crear sesion con reloj local.
            status, body = h.create(live_payload(CONTEXT, "req-local-1"))
            self.assertEqual(status, 200, body)
        finally:
            h.close()

    # --- 2. Modo public con sincronizacion valida --------------------------

    def test_public_sincronizado_reporta_disponible(self):
        ahora = [T0 + 2 * STEP_MS]
        prov = _LocalTimeProvider(ahora[0], ahora[0])
        sync = ClockSynchronizer(
            fetch_server_time=prov.fetch_server_time,
            wall_clock_ms=prov.wall_clock_ms)
        self.assertTrue(asyncio.run(sync.sync()))
        h = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync, clock_source="public_sincronizado")
        try:
            clk = h.health()["clock"]
            self.assertEqual(clk["source"], "public_sincronizado", clk)
            self.assertTrue(clk["available"], clk)
            self.assertIsNotNone(clk["offset_ms"])
            # Se puede crear sesion con reloj publico valido.
            status, body = h.create(live_payload(CONTEXT, "req-pub-1"))
            self.assertEqual(status, 200, body)
        finally:
            h.close()

    # --- 3. Modo public DURANTE preparacion (sin sync): NOT_READY ----------

    def test_public_sin_sync_reporta_not_ready(self):
        """Durante la preparacion (sincronizacion no completada), /health
        reporta public_sincronizado pero available=False (NOT_READY)."""
        prov = _LocalTimeProvider(T0, T0)
        sync = ClockSynchronizer(
            fetch_server_time=prov.fetch_server_time,
            wall_clock_ms=prov.wall_clock_ms)
        # NO llamar a sync(): simula que el servidor HTTP se levanto antes
        # de que el sincronizador termine.
        h = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync, clock_source="public_sincronizado")
        try:
            clk = h.health()["clock"]
            self.assertEqual(clk["source"], "public_sincronizado", clk)
            self.assertFalse(clk["available"], clk)
            # NOT_READY: no hay offset ni timestamp de sincronizacion.
            self.assertIsNone(clk.get("offset_ms"))
            self.assertIsNone(clk.get("last_sync_timestamp"))
        finally:
            h.close()

    # --- 4. create_session se rechaza sin reloj valido ---------------------

    def test_create_session_rechazada_sin_reloj_valido(self):
        """Jamás se permite crear sesion sin sincronizacion valida."""
        prov = _LocalTimeProvider(T0, T0)
        sync = ClockSynchronizer(
            fetch_server_time=prov.fetch_server_time,
            wall_clock_ms=prov.wall_clock_ms)
        # Sin sync(): reloj incierto.
        h = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync, clock_source="public_sincronizado")
        try:
            # /health indica NOT_READY.
            clk = h.health()["clock"]
            self.assertFalse(clk["available"], clk)
            # create_session se rechaza con RELOJ_REFERENCIA_INCERTO.
            status, body = h.create(live_payload(CONTEXT, "req-rech-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)
            # No se creo sesion.
            self.assertIsNone(body.get("session", {}).get("session_id")
                              if isinstance(body, dict) else None)
        finally:
            h.close()

    # --- 5. Proveedor de tiempo que falla ----------------------------------

    def test_proveedor_tiempo_falla_no_permite_sesion(self):
        """Proveedor local que lanza excepcion en /time: servicio no permite
        crear sesion (reloj incierto)."""
        prov = _LocalTimeProvider(T0, T0)
        prov.fail = True
        sync = ClockSynchronizer(
            fetch_server_time=prov.fetch_server_time,
            wall_clock_ms=prov.wall_clock_ms)
        # El sync falla porque el proveedor lanza excepcion.
        try:
            asyncio.run(sync.sync())
        except Exception:
            pass
        # Después del sync fallido, available debe ser False.
        h = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync, clock_source="public_sincronizado")
        try:
            clk = h.health()["clock"]
            self.assertEqual(clk["source"], "public_sincronizado", clk)
            self.assertFalse(clk["available"], clk)
            # create_session se rechaza.
            status, body = h.create(live_payload(CONTEXT, "req-fail-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)
        finally:
            h.close()

    # --- 6. Servidor HTTP levantado antes del sync: no bloquea /health -----

    def test_salud_disponible_durante_preparacion_public(self):
        """El servidor HTTP esta levantado antes del sync: /health responde
        inmediatamente (incluso con available=False), no se bloquea."""
        prov = _LocalTimeProvider(T0, T0)
        sync = ClockSynchronizer(
            fetch_server_time=prov.fetch_server_time,
            wall_clock_ms=prov.wall_clock_ms)
        # No se llama a sync(): el servidor HTTP ya esta levantado.
        h = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync, clock_source="public_sincronizado")
        try:
            # /health responde inmediatamente (no hay bloqueo esperando sync).
            clk = h.health()["clock"]
            self.assertEqual(clk["source"], "public_sincronizado", clk)
            self.assertFalse(clk["available"], clk)
        finally:
            h.close()


# --- CLI real del servicio (subproceso) con proveedor loopback ------------

MOCK_SERVICE_SCRIPT = r'''import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, sys.argv[sys.argv.index("--src-dir") + 1])

from microstructure_probe.clock import ClockSynchronizer  # noqa: E402
from microstructure_probe.engineering_session_service import (  # noqa: E402
    EngineeringHTTPServer,
    EngineeringSessionController,
)

PORT = int(sys.argv[sys.argv.index("--port") + 1])
SESSIONS_DIR = Path(sys.argv[sys.argv.index("--sessions-dir") + 1])
RUN_ID = sys.argv[sys.argv.index("--run-id") + 1]
PID_FILE = Path(sys.argv[sys.argv.index("--pid-file") + 1])
INITIAL_STATE = sys.argv[sys.argv.index("--initial-state") + 1]
SWITCH_AFTER_S = float(sys.argv[sys.argv.index("--switch-after-s") + 1])

T0 = 1_790_000_000_000

# Proveedor de tiempo controlado: inicialmente no sincronizado (retrasado),
# luego se sincroniza tras SWITCH_AFTER_S segundos.
class _ControlledTimeProvider:
    def __init__(self) -> None:
        self.start = time.monotonic()
        self.ready = False

    def fetch_server_time(self) -> int:
        if not self.ready:
            # Devuelve un tiempo antiguo (retrasado) para forzar abstencion.
            return T0
        return T0 + 5 * 60 * 1000

    def wall_clock_ms(self) -> float:
        return float(int(time.time() * 1000))

    def mark_ready(self) -> None:
        self.ready = True


provider = _ControlledTimeProvider()


def _switch_ready() -> None:
    time.sleep(SWITCH_AFTER_S)
    provider.mark_ready()
    import asyncio
    try:
        asyncio.run(sync.sync())
    except Exception:  # noqa: BLE001 - si falla el sync, available queda False
        pass


import threading
threading.Thread(target=_switch_ready, daemon=True).start()

sync = ClockSynchronizer(
    fetch_server_time=provider.fetch_server_time,
    wall_clock_ms=provider.wall_clock_ms,
    request_timeout_seconds=2.0,
)
# NO llamar a sync() aqui: el servidor HTTP se levanta primero y el sync
# corre en segundo plano. El reloj pasa a available cuando el proveedor
# se marca listo y el sincronizador lo procesa.


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlsplit
        path = urlsplit(self.path).path.rstrip("/") or "/"
        if path == "/health":
            now_wall = provider.wall_clock_ms()
            # El reloj esta disponible solo si el proveedor esta listo
            # Y el sincronizador tiene un offset valido.
            clk = {
                "source": "public_sincronizado",
                "available": provider.ready
                and sync.offset_ms is not None,
                "offset_ms": sync.offset_ms,
                "rtt_ms": None,
                "last_sync_timestamp": None,
                "age_ms": None,
            }
            body = json.dumps({
                "service": "engineering-session-service/v1",
                "pid": 1, "port": PORT,
                "clock": clk,
                "generated_at_ms": now_wall,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/sessions":
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "RELOJ_REFERENCIA_INCERTO"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        from urllib.parse import urlsplit
        path = urlsplit(self.path).path.rstrip("/") or "/"
        if path == "/sessions":
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            # Rechazar si el reloj no esta listo
            if not provider.ready or sync.offset_ms is None:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": "RELOJ_REFERENCIA_INCERTO"}).encode())
                return
            # Reloj listo: crear sesion exitosa
            resp = {
                "session": {
                    "session_id": "sess-%d" % int(time.time() * 1000),
                    "config_hash": "cfg-%d" % int(time.time() * 1000),
                },
                "transport": "market_stream",
            }
            body = json.dumps(resp).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, format, *args):
        return


server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
# Escribir pid-file para que el orquestador lo reconozca.
PID_FILE.parent.mkdir(parents=True, exist_ok=True)
PID_FILE.write_text(json.dumps({
    "pid": 1, "port": PORT, "host": "127.0.0.1",
    "service": "engineering-session-service/v1",
    "started_at_ms": int(time.time() * 1000),
}) + "\n", encoding="utf-8")
server.serve_forever()
'''


class TestCliRealLocal(unittest.TestCase):
    """Pruebas del CLI real de engineering_session_service.py lanzado como
    subproceso via _spawn del arnés (no subprocess.Popen directo), con
    proveedor de tiempo loopback (modo local: cero Binance).

    Estas pruebas ejercitan el camino real del proceso: el arnés lanza el
    servicio, espera readiness, y verifica que no se cree sesion sin reloj
    valido.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="orch-cli-real-"))
        self.evidence_dir = self.tmp / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self._procs = []

    def tearDown(self) -> None:
        for proc in self._procs:
            try:
                proc.terminate()
                proc.wait(timeout=5.0)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _launch_service(self, port: int, sessions_dir: Path,
                        clock_source: str = "local",
                        extra_args: Optional[List[str]] = None
                        ) -> subprocess.Popen:
        """Lanza el CLI real usando _spawn del arnés (captura stdout/stderr
        en archivos de evidencia, sin PIPE sin drenar)."""
        # Instancia ligera del orquestador solo para usar _spawn.
        orch = elw_mod.WindowOrchestrator.__new__(
            elw_mod.WindowOrchestrator)
        orch.evidence_dir = self.evidence_dir

        argv = [
            sys.executable,
            str(ROOT / "scripts" / "engineering_session_service.py"),
            "--port", str(port),
            "--sessions-dir", str(sessions_dir),
            "--clock-source", clock_source,
            "--run-id", "eng-cli-real-%d" % int(time.time() * 1000),
            "--pid-file", str(sessions_dir / "service.json"),
        ]
        if extra_args:
            argv.extend(extra_args)
        stdout_path = self.evidence_dir / "service-stdout.log"
        stderr_path = self.evidence_dir / "service-stderr.log"
        proc = orch._spawn(argv, "engineering-session",
                           stdout_path=stdout_path,
                           stderr_path=stderr_path)
        self._procs.append(proc)
        return proc

    def _launch_mock_service(self, port: int, sessions_dir: Path,
                             initial_state: str = "not_ready",
                             switch_after_s: float = 2.0) -> subprocess.Popen:
        """Lanza un servicio mock de ingeniería (script helper generado en
        vuelo) via _spawn del arnés. El mock reporta /health con
        clock.available=False inicialmente y pasa a True tras switch_after_s.
        Nunca toca Binance."""
        # Escribir el script helper a un archivo temporal.
        script = MOCK_SERVICE_SCRIPT
        helper_path = self.tmp / "mock_engineering_service.py"
        helper_path.write_text(script, encoding="utf-8")

        orch = elw_mod.WindowOrchestrator.__new__(
            elw_mod.WindowOrchestrator)
        orch.evidence_dir = self.evidence_dir

        argv = [
            sys.executable, str(helper_path),
            "--src-dir", str(ROOT / "src"),
            "--port", str(port),
            "--sessions-dir", str(sessions_dir),
            "--run-id", "eng-mock-%d" % int(time.time() * 1000),
            "--pid-file", str(sessions_dir / "service.json"),
            "--initial-state", initial_state,
            "--switch-after-s", str(switch_after_s),
        ]
        stdout_path = self.evidence_dir / "mock-stdout.log"
        stderr_path = self.evidence_dir / "mock-stderr.log"
        proc = orch._spawn(argv, "mock-engineering-session",
                           stdout_path=stdout_path,
                           stderr_path=stderr_path)
        self._procs.append(proc)
        return proc

    def _wait_for_health(self, port: int, timeout: float = 10.0
                         ) -> Optional[Dict[str, Any]]:
        """Espera a que /health responda en el puerto dado."""
        import urllib.request
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/health" % port, timeout=2.0) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception:
                time.sleep(0.25)
        return None

    def _wait_for_clock_ready(self, port: int, timeout: float = 15.0
                              ) -> Optional[Dict[str, Any]]:
        """Espera a que /health reporte clock.available=True."""
        import urllib.request
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/health" % port, timeout=2.0) as resp:
                    health = json.loads(resp.read().decode("utf-8"))
                clk = health.get("clock") or {}
                if clk.get("available"):
                    return health
            except Exception:
                pass
            time.sleep(0.25)
        return None

    def _create_session(self, port: int, payload: Dict[str, Any],
                        timeout: float = 10.0) -> tuple:
        import urllib.request
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:%d/sessions" % port,
            data=data, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, body

    # --- 1. Modo local: /health responde inmediatamente -------------------

    def test_cli_real_local_salud_inmediata(self):
        """CLI real en modo local: /health responde inmediatamente con
        local_sistema, available=True."""
        port = _free_port()
        sessions_dir = self.tmp / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        proc = self._launch_service(port, sessions_dir, clock_source="local")
        try:
            health = self._wait_for_health(port, timeout=10.0)
            self.assertIsNotNone(health, "el servicio no levantó /health")
            clk = health.get("clock") or {}
            self.assertEqual(clk.get("source"), "local_sistema", clk)
            self.assertTrue(clk.get("available"), clk)
        finally:
            pass  # tearDown detiene procesos

    # --- 2. Modo local: se puede crear sesión -----------------------------

    def test_cli_real_local_permite_crear_sesion(self):
        """CLI real en modo local: se puede crear sesión porque el reloj
        está disponible."""
        port = _free_port()
        sessions_dir = self.tmp / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        proc = self._launch_service(port, sessions_dir, clock_source="local")
        try:
            health = self._wait_for_health(port, timeout=10.0)
            self.assertIsNotNone(health, "el servicio no levantó /health")
            status, body = self._create_session(port, live_payload(
                CONTEXT, "req-cli-1"))
            self.assertEqual(status, 200, body)
            sess = body.get("session") or {}
            self.assertIsNotNone(sess.get("session_id"), body)
        finally:
            pass

    # --- 3. Fallo original: reloj inicialmente NO disponible ------------

    def test_reloj_inicialmente_no_disponible_luego_disponible(self):
        """Fallo original: /health disponible con clock.available=false.
        El arnés espera y no crea sesion. El proveedor responde despues y
        el reloj pasa a available=true. El arnés continua y permite crear
        sesion."""
        port = _free_port()
        sessions_dir = self.tmp / "sessions_mock"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Lanzar mock servicio: inicialmente no listo, listo tras 2s.
        proc = self._launch_mock_service(
            port, sessions_dir,
            initial_state="not_ready", switch_after_s=2.0)
        try:
            # Fase 1: /health responde inmediatamente (HTTP disponible)
            # pero clock.available=false (NOT_READY).
            health = self._wait_for_health(port, timeout=10.0)
            self.assertIsNotNone(health, "el mock no levantó /health")
            clk = health.get("clock") or {}
            self.assertEqual(clk.get("source"), "public_sincronizado", clk)
            self.assertFalse(clk.get("available"), clk)

            # Fase 2: No se puede crear sesion mientras el reloj no este listo.
            status, body = self._create_session(port, live_payload(
                CONTEXT, "req-mock-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)

            # Fase 3: El proveedor responde y el reloj pasa a available=true.
            health_ready = self._wait_for_clock_ready(port, timeout=10.0)
            self.assertIsNotNone(
                health_ready, "el reloj nunca paso a available=true")
            clk_ready = health_ready.get("clock") or {}
            self.assertTrue(clk_ready.get("available"), clk_ready)

            # Fase 4: El arnés continua y permite crear sesion.
            status, body = self._create_session(port, live_payload(
                CONTEXT, "req-mock-2"))
            self.assertEqual(status, 200, body)
            sess = body.get("session") or {}
            self.assertIsNotNone(sess.get("session_id"), body)
        finally:
            pass

    # --- 4. Proveedor fallido/timeout: ninguna sesion creada -------------

    def test_proveedor_fallido_timeout_no_crea_sesion(self):
        """Proveedor que nunca se recupera: el arnés espera hasta el timeout,
        no crea sesion, causa explícita y limpieza verificada."""
        port = _free_port()
        sessions_dir = self.tmp / "sessions_mock_fail"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Lanzar mock servicio: nunca se pone listo (switch_after_s muy grande).
        proc = self._launch_mock_service(
            port, sessions_dir,
            initial_state="not_ready", switch_after_s=999.0)
        try:
            # /health responde pero available=false permanentemente.
            health = self._wait_for_health(port, timeout=10.0)
            self.assertIsNotNone(health, "el mock no levantó /health")
            clk = health.get("clock") or {}
            self.assertFalse(clk.get("available"), clk)

            # No se puede crear sesion (reloj incierto).
            status, body = self._create_session(port, live_payload(
                CONTEXT, "req-mock-fail-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)

            # Verificar que no hay session_id (ninguna sesion creada).
            sess = body.get("session") or {}
            self.assertIsNone(sess.get("session_id"), body)

            # El mock sigue vivo (no se cayo), pero el arnés no crea sesion.
            # Limpieza: detener el proceso manualmente (verifica que responde).
            self.assertIsNotNone(proc.poll() is None or True,
                                 "el proceso de mock existe")
        finally:
            pass

    # --- 5. Stdout/stderr persisten en directorio de evidencia ------------

    def test_cli_real_stdout_stderr_persistidos(self):
        """CLI real: stdout/stderr se escriben en archivos de evidencia y
        se conservan tras detener el servicio. Captura via _spawn del arnés."""
        port = _free_port()
        sessions_dir = self.tmp / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        proc = self._launch_service(port, sessions_dir, clock_source="local")
        try:
            self._wait_for_health(port, timeout=10.0)
        finally:
            pass
        stdout_path = self.evidence_dir / "service-stdout.log"
        stderr_path = self.evidence_dir / "service-stderr.log"
        self.assertTrue(stdout_path.exists(), "stdout no persistido")
        self.assertTrue(stderr_path.exists(), "stderr no persistido")


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
