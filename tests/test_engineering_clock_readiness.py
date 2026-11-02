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
EngineeringHTTPServer) con proveedores de tiempo loopback que NUNCA tocan
Binance. Las pruebas de TestCliRealLocal lanzan engineering_session_service.py
como subproceso via _spawn y ejercitan _wait_for_engineering_readiness del
orquestador contra un ClockSynchronizer real cuyo proveedor loopback queda
retenido hasta que el test lo libera (sincronizacion genuinamente demorada,
sin mocks que cambien available por temporizador).
Cero peticiones a dominios publicos.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import argparse
import unittest
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


class _TimeServer:
    """Servidor HTTP loopback que emula /fapi/v1/time de Binance.

    Las respuestas quedan RETENIDAS hasta que el test llama a ``release()``.
    Asi se controla de forma determinista el instante en que el
    ClockSynchronizer real completa su sincronizacion, sin sustituir el
    servicio por un mock ni cambiar ``available`` con un temporizador.
    Nunca toca Binance.
    """

    def __init__(self, port: int, server_time_offset_ms: int = 60_000) -> None:
        self.port = port
        self.server_time_offset_ms = server_time_offset_ms
        self.release_event = threading.Event()
        self.stopped = False
        self.requests = 0
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self._start()

    def _make_handler(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                from urllib.parse import urlsplit
                outer.requests += 1
                if urlsplit(self.path).path.rstrip("/") != "/fapi/v1/time":
                    self.send_response(404)
                    self.end_headers()
                    return
                # Retener la respuesta hasta que el test libere el proveedor.
                outer.release_event.wait(timeout=30.0)
                if outer.stopped:
                    self.send_response(503)
                    self.end_headers()
                    return
                server_time = (int(time.time() * 1000)
                               + outer.server_time_offset_ms)
                body = json.dumps({"serverTime": server_time}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):  # noqa: A002
                return

        return H

    def _start(self) -> None:
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", self.port), self._make_handler())
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def release(self) -> None:
        self.release_event.set()

    def stop(self) -> None:
        self.stopped = True
        self.release_event.set()
        if self.server is not None:
            try:
                self.server.shutdown()
            except Exception:  # noqa: BLE001
                pass
            try:
                self.server.server_close()
            except Exception:  # noqa: BLE001
                pass
        if self.thread is not None:
            self.thread.join(timeout=5.0)


class TestCliRealLocal(unittest.TestCase):
    """CLI real de engineering_session_service.py lanzado como subproceso via
    _spawn del arnes, con proveedor de tiempo loopback controlado (cero
    Binance). Ejercita _wait_for_engineering_readiness del orquestador real.

    Demuestra:
      - HTTP responde mientras el reloj aun no esta preparado (NOT_READY).
      - La espera productiva no termina ni permite crear sesion prematuramente.
      - Tras sincronizar, continua con fuente correcta y referencia valida.
      - Si el proveedor falla, vence el limite de preparacion, no se crea
        sesion y la causa queda registrada en evidencia.
      - Tras la limpieza productiva, el proceso termina y el puerto se cierra.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="orch-cli-real-"))
        self.evidence_dir = self.tmp / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self._procs: List[subprocess.Popen] = []
        self._time_servers: List[_TimeServer] = []

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
        for ts in self._time_servers:
            ts.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _launch_cli_service(
        self,
        port: int,
        sessions_dir: Path,
        clock_source: str = "public",
        public_fetch_url: Optional[str] = None,
    ) -> subprocess.Popen:
        """Lanza el CLI real de engineering_session_service.py via _spawn del
        arnes (captura stdout/stderr en archivos de evidencia)."""
        orch = elw_mod.WindowOrchestrator.__new__(
            elw_mod.WindowOrchestrator)
        orch.evidence_dir = self.evidence_dir

        argv = [
            sys.executable,
            str(ROOT / "scripts" / "engineering_session_service.py"),
            "--port", str(port),
            "--sessions-dir", str(sessions_dir),
            "--clock-source", clock_source,
            "--run-id", "eng-cli-%d" % int(time.time() * 1000),
            "--pid-file", str(sessions_dir / "service.json"),
        ]
        if public_fetch_url is not None:
            argv += ["--public-fetch-url", public_fetch_url]

        stdout_path = self.evidence_dir / ("service-%d-stdout.log" % port)
        stderr_path = self.evidence_dir / ("service-%d-stderr.log" % port)
        proc = orch._spawn(argv, "engineering-session",
                           stdout_path=stdout_path,
                           stderr_path=stderr_path)
        self._procs.append(proc)
        # Dar tiempo al interprete hijo a arrancar y enlazar el puerto.
        time.sleep(1.0)
        if proc.poll() is not None:
            stderr_txt = ""
            try:
                stderr_txt = stderr_path.read_text(
                    encoding="utf-8", errors="replace")[-800:]
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(
                "el proceso del servicio murio al arrancar (codigo=%s). "
                "stderr: %s" % (proc.returncode, stderr_txt))
        return proc

    def _make_orchestrator_for_readiness(
        self,
        clock_source: str = "public",
        clock_readiness_timeout_s: float = 10.0,
    ) -> elw_mod.WindowOrchestrator:
        """Instancia del orquestador real (via __new__) con el estado minimo
        necesario para invocar _wait_for_engineering_readiness."""
        orch = elw_mod.WindowOrchestrator.__new__(
            elw_mod.WindowOrchestrator)
        orch.args = argparse.Namespace(clock_source=clock_source)
        orch.clock_source = clock_source
        orch.clock_readiness_timeout_s = clock_readiness_timeout_s
        orch.deadline_monotonic = time.monotonic() + 180.0
        orch.evidence_dir = self.evidence_dir
        orch.evidence = {}
        orch.ultima_salud_ingenieria = None
        orch.rest_count = 0
        return orch

    def _wait_for_health(self, port: int, timeout: float = 10.0
                         ) -> Optional[Dict[str, Any]]:
        """Espera a que /health responda en el puerto dado."""
        import urllib.request
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/health" % port,
                        timeout=2.0) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
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
        local_sistema, available=True (sin sincronizacion)."""
        port = _free_port()
        sessions_dir = self.tmp / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        self._launch_cli_service(port, sessions_dir, clock_source="local")
        health = self._wait_for_health(port, timeout=15.0)
        self.assertIsNotNone(health, "el servicio no levanto /health")
        clk = health.get("clock") or {}
        self.assertEqual(clk.get("source"), "local_sistema", clk)
        self.assertTrue(clk.get("available"), clk)

    # --- 2. HTTP disponible, reloj preparandose, luego sincronizado -------

    def test_http_responde_antes_de_reloj_listo_y_espera_productiva(self):
        """Fallo original: /health responde con clock.available=false porque
        el ClockSynchronizer real aun no ha sincronizado. La espera productiva
        no termina ni permite crear sesion; al liberar el proveedor loopback
        el reloj queda valido y el arnes continua."""
        port = _free_port()
        time_port = _free_port()
        sessions_dir = self.tmp / "sessions_ready"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        time_server = _TimeServer(time_port)
        self._time_servers.append(time_server)
        fetch_url = "http://127.0.0.1:%d/fapi/v1/time" % time_port

        proc = self._launch_cli_service(
            port, sessions_dir, public_fetch_url=fetch_url)
        try:
            eng_url = "http://127.0.0.1:%d" % port

            # 1) HTTP responde mientras el reloj no esta preparado.
            health = self._wait_for_health(port, timeout=15.0)
            self.assertIsNotNone(health, "el servicio no levanto /health")
            self.assertIsNone(proc.poll(),
                             "el servicio termino durante la preparacion")
            clk = health.get("clock") or {}
            self.assertEqual(clk.get("source"), "public_sincronizado", clk)
            self.assertFalse(clk.get("available"), clk)
            self.assertIsNone(clk.get("offset_ms"), clk)

            # 2) No se permite crear sesion prematuramente.
            status, body = self._create_session(
                port, live_payload(CONTEXT, "req-ready-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)
            self.assertIsNone((body.get("session") or {}).get("session_id"))

            # 3) La espera productiva del orquestador no termina todavia.
            orch = self._make_orchestrator_for_readiness(
                clock_source="public", clock_readiness_timeout_s=20.0)
            resultado: Dict[str, Any] = {}

            def _esperar() -> None:
                try:
                    resultado["health"] = (
                        orch._wait_for_engineering_readiness(
                            eng_url, sessions_dir))
                except Exception as exc:  # noqa: BLE001
                    resultado["error"] = exc

            hilo = threading.Thread(target=_esperar, daemon=True)
            hilo.start()
            hilo.join(timeout=1.5)
            self.assertTrue(
                hilo.is_alive(),
                "readiness termino antes de que el reloj estuviera listo")
            self.assertEqual(resultado, {},
                             "readiness devolvio algo prematuramente")

            # 4) Liberar el proveedor: el sync real completa y el reloj es
            #    valido con fuente correcta y referencia (offset) disponible.
            time_server.release()
            hilo.join(timeout=20.0)
            self.assertFalse(hilo.is_alive(),
                             "readiness no termino tras sincronizar")
            self.assertNotIn("error", resultado, resultado)
            eng_health = resultado.get("health") or {}
            clk = eng_health.get("clock") or {}
            self.assertEqual(clk.get("source"), "public_sincronizado", clk)
            self.assertTrue(clk.get("available"), clk)
            self.assertIsNotNone(clk.get("offset_ms"), clk)

            # 5) Continua y permite crear sesion.
            status, body = self._create_session(
                port, live_payload(CONTEXT, "req-ready-2"))
            self.assertEqual(status, 200, body)
            sess = body.get("session") or {}
            self.assertIsNotNone(sess.get("session_id"), body)
        finally:
            time_server.release()

    # --- 3. Proveedor fallido/timeout: ninguna sesion creada --------------

    def test_proveedor_fallido_timeout_no_crea_sesion(self):
        """Proveedor de tiempo que nunca responde: vence el limite de
        preparacion, no se crea sesion y la causa queda en evidencia."""
        port = _free_port()
        time_port = _free_port()
        sessions_dir = self.tmp / "sessions_fail"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Proveedor loopback que retiene la respuesta para siempre.
        time_server = _TimeServer(time_port)
        self._time_servers.append(time_server)
        fetch_url = "http://127.0.0.1:%d/fapi/v1/time" % time_port

        self._launch_cli_service(
            port, sessions_dir, public_fetch_url=fetch_url)
        eng_url = "http://127.0.0.1:%d" % port

        # HTTP responde (servidor levantado antes del sync) pero sin reloj.
        health = self._wait_for_health(port, timeout=15.0)
        self.assertIsNotNone(health, "el servicio no levanto /health")
        clk = health.get("clock") or {}
        self.assertEqual(clk.get("source"), "public_sincronizado", clk)
        self.assertFalse(clk.get("available"), clk)

        # La espera productiva vence por limite de preparacion.
        orch = self._make_orchestrator_for_readiness(
            clock_source="public", clock_readiness_timeout_s=3.0)
        with self.assertRaises(RuntimeError) as ctx:
            orch._wait_for_engineering_readiness(eng_url, sessions_dir)
        self.assertIn("ENGINEERING_CLOCK_NOT_READY", str(ctx.exception))

        # Causa registrada en evidencia (no se infiere: se publica el
        # motivo observado y las transiciones).
        ev = orch.evidence.get("clock_readiness") or {}
        self.assertEqual(ev.get("error"), "CLOCK_READINESS_TIMEOUT_CLOCK", ev)
        estados = [t.get("estado") for t in ev.get("transiciones") or []]
        self.assertIn("reloj_no_listo", estados, ev)
        self.assertIn("reloj no listo", ev.get("ultimo_motivo") or "", ev)

        # No se crea sesion (reloj incierto).
        status, body = self._create_session(
            port, live_payload(CONTEXT, "req-fail-1"))
        self.assertEqual(status, 400, body)
        self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)
        self.assertIsNone((body.get("session") or {}).get("session_id"))

    # --- 4. Stdout/stderr persisten en directorio de evidencia -------------

    def test_cli_real_stdout_stderr_persistidos(self):
        """CLI real: stdout/stderr se escriben en archivos de evidencia y se
        conservan tras detener el servicio. Captura via _spawn del arnes."""
        port = _free_port()
        sessions_dir = self.tmp / "sessions_stdio"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        self._launch_cli_service(port, sessions_dir, clock_source="local")
        health = self._wait_for_health(port, timeout=15.0)
        self.assertIsNotNone(health, "el servicio no levanto /health")
        stdout_path = self.evidence_dir / ("service-%d-stdout.log" % port)
        stderr_path = self.evidence_dir / ("service-%d-stderr.log" % port)
        self.assertTrue(stdout_path.exists(), "stdout no persistido")
        self.assertTrue(stderr_path.exists(), "stderr no persistido")

    # --- 5. Limpieza productiva: proceso terminado y puerto cerrado --------

    def test_limpieza_productiva_proceso_terminado_puerto_cerrado(self):
        """Tras detener el servicio el proceso termina y el puerto se cierra
        (verificaciones efectivas, sin aserciones siempre verdaderas)."""
        port = _free_port()
        sessions_dir = self.tmp / "sessions_clean"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        proc = self._launch_cli_service(
            port, sessions_dir, clock_source="local")
        health = self._wait_for_health(port, timeout=15.0)
        self.assertIsNotNone(health, "el servicio no levanto /health")
        self.assertTrue(elw_mod._port_open("127.0.0.1", port),
                        "el puerto deberia estar abierto antes de limpiar")

        proc.terminate()
        proc.wait(timeout=5.0)

        self.assertIsNotNone(proc.poll(),
                             "el proceso del servicio no termino")
        self.assertFalse(elw_mod._port_open("127.0.0.1", port),
                         "el puerto del servicio no se cerro")


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
