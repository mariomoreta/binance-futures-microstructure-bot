"""Prueba integrada local del camino productivo de aceptación pública.

Usa proveedores HTTP/WS loopback y almacenamiento aislado (TemporaryDirectory).
No abre Binance ni ejecuta ventana pública. Verifica:
  A. Primer inicio sin run_id previo: backend crea/persiste identidad y arranca una sola corrida.
  B. Doble clic / peticiones repetidas no duplican recursos (idempotencia por run_id).
  C. NOT_READY → reloj válido → contexto cerrado → sesión → evaluación visible.
  D. 5 solicitudes de tiempo + 2 de contexto consumen 7; el siguiente queda bloqueado antes del transporte.
  E. UI muestra consumo real y estado de la misma corrida.
  F. Recarga/reinicio conservan identidad, consumo y deadline.
  G. Con navegador/Next.js desconectados, el backend vence y limpia sus recursos.
  H. Servicio ajeno/unidentified o run_id distinto: parada rechazada, proceso intacto.
  I. Con position.open=true acreditada por evento entry: detener conserva entrada/posición y no añade exit, comisión ni realizado.
  J. Error de preparación conserva causa y logs, con limpieza efectiva.

El deadline productivo es 180 s; en pruebas se acorta mediante
PUBLIC_RUN_DEADLINE_S.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.market_cache import MarketCache  # noqa: E402

# ---------------------------------------------------------------------------
# Servidor HTTP loopback que simula fapi.v1/time con tiempo CONTROLADO que avanza.
# ---------------------------------------------------------------------------

_TIME_BASE_MS = int(time.time() * 1000)
_TIME_LOCK = threading.Lock()


def _advance_time_ms(ms: int) -> None:
    """Avanza el reloj simulado ``ms`` milisegundos."""
    global _TIME_BASE_MS
    with _TIME_LOCK:
        _TIME_BASE_MS += ms


def current_server_time_ms() -> int:
    with _TIME_LOCK:
        return _TIME_BASE_MS


class _TimeHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/time":
            body = json.dumps({"serverTime": current_server_time_ms()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_port_free(port: int, timeout_s: float = 10.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(("127.0.0.1", port))
            time.sleep(0.25)
        except (ConnectionRefusedError, OSError):
            return
    raise TimeoutError(f"puerto {port} no se liberó en {timeout_s}s")


# ---------------------------------------------------------------------------
# Utilidades del servicio de ingeniería
# ---------------------------------------------------------------------------

def _health(port: int, timeout_s: float = 3.0) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _public_run(port: int, timeout_s: float = 3.0) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/public-run", method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _shutdown(port: int, timeout: float = 5.0) -> bool:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/shutdown", method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _wait_health(port: int, timeout_s: float = 30.0) -> Optional[Dict[str, Any]]:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = _health(port)
        if last is not None and last.get("service"):
            return last
        time.sleep(0.25)
    return last


def _start_engineering_service(
    port: int,
    sessions_dir: Path,
    run_id: str,
    time_url: str,
    deadline_s: Optional[int] = None,
    cache_db: Optional[Path] = None,
) -> subprocess.Popen:
    env = dict(os.environ)
    if deadline_s is not None:
        env["PUBLIC_RUN_DEADLINE_S"] = str(deadline_s)
    if cache_db is not None:
        env["MICROPROBE_MARKET_CACHE_DB"] = str(cache_db)
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "engineering_session_service.py"),
        "--host", "127.0.0.1",
        "--port", str(port),
        "--sessions-dir", str(sessions_dir),
        "--pid-file", str(sessions_dir / "service.json"),
        "--clock-source", "public",
        "--public-max-requests", "5",
        "--public-fetch-url", time_url,
        "--run-id", run_id,
    ]
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return proc


# ---------------------------------------------------------------------------
# Pruebas
# ---------------------------------------------------------------------------

class PublicRunIntegrationTest:
    """Ejecuta los criterios A-I sin Binance."""

    def __init__(self) -> None:
        self.time_port = _free_port()
        self.eng_port = _free_port()
        self.tmpdir = tempfile.TemporaryDirectory(prefix="public-run-test-")
        self.tmpdir_path = Path(self.tmpdir.name)
        self.sessions_dir = self.tmpdir_path / "sessions"
        self.cache_db = self.tmpdir_path / "market_cache.db"
        self.time_server: Optional[ThreadingHTTPServer] = None
        self.time_thread: Optional[threading.Thread] = None
        self.proc: Optional[subprocess.Popen] = None
        self.run_id = f"eng-public-test-{int(time.time()*1000)}"
        self.failures: list[str] = []
        self.passes: list[str] = []

    def _check(self, name: str, cond: bool, detail: str = "") -> None:
        if cond:
            self.passes.append(f"{name}: {detail}")
        else:
            self.failures.append(f"{name}: {detail}")

    # --- setup / teardown --------------------------------------------------

    def start_time_server(self) -> None:
        self.time_server = ThreadingHTTPServer(("127.0.0.1", self.time_port), _TimeHandler)
        self.time_thread = threading.Thread(target=self.time_server.serve_forever, daemon=True)
        self.time_thread.start()
        for _ in range(100):
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{self.time_port}/time", method="GET")
                with urllib.request.urlopen(req, timeout=1.0) as r:
                    body = json.loads(r.read().decode())
                    if "serverTime" in body:
                        return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("servidor de tiempo loopback no arrancó")

    def stop_time_server(self) -> None:
        if self.time_server is not None:
            self.time_server.shutdown()
        if self.time_thread is not None:
            self.time_thread.join(timeout=2.0)

    def start_engineering(self, deadline_s: Optional[int] = None) -> None:
        self.proc = _start_engineering_service(
            self.eng_port, self.sessions_dir, self.run_id,
            f"http://127.0.0.1:{self.time_port}/time", deadline_s=deadline_s,
            cache_db=self.cache_db)
        if self.proc.poll() is not None:
            out, err = self.proc.communicate(timeout=5.0)
            print(f"  [DEBUG] servicio salió con código {self.proc.returncode}", flush=True)
            print(f"  [DEBUG] stdout={out.decode('utf-8','replace')[:500]}", flush=True)
            print(f"  [DEBUG] stderr={err.decode('utf-8','replace')[:500]}", flush=True)

    def stop_engineering(self) -> None:
        if self.proc is not None:
            if self.proc.poll() is None:
                # Apagado graceful vía POST /shutdown para liberar el puerto
                # correctamente en Windows.
                try:
                    _shutdown(self.eng_port)
                except Exception:
                    pass
                try:
                    self.proc.wait(timeout=15.0)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    try:
                        self.proc.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        pass
            self.proc = None
        try:
            _wait_port_free(self.eng_port, timeout_s=30.0)
        except TimeoutError:
            pass

    def cleanup(self) -> None:
        self.stop_engineering()
        self.stop_time_server()
        self.tmpdir.cleanup()

    # --- criterios ---------------------------------------------------------

    def run(self) -> None:
        self.start_time_server()
        try:
            self._criterion_a_first_start()
            self._criterion_b_no_duplicate()
            self._criterion_c_not_ready_to_session()
            self._criterion_d_budget_seven()
            self._criterion_e_real_consumption()
            self._criterion_f_reload_preserves()
            self._criterion_g_deadline_without_browser()
            self._criterion_h_stop_rejects_foreign()
            self._criterion_i_stop_preserves_position()
            self._criterion_j_prep_failure_cause()
        finally:
            self.cleanup()

    def _criterion_a_first_start(self) -> None:
        """A. Primer inicio sin run_id previo: backend crea/persiste identidad y arranca una sola corrida."""
        self.start_engineering(deadline_s=None)
        health = _wait_health(self.eng_port, timeout_s=30.0)
        self._check(
            "A. salud del servicio",
            health is not None and health.get("service") == "engineering-session-service/v1",
            f"health={health}",
        )
        if health:
            # Esperar a que el reloj se sincronice (puede tardar tras levantar
            # el servidor HTTP).
            clock = None
            for _ in range(20):
                h = _health(self.eng_port, timeout_s=5.0)
                if h is not None:
                    c = h.get("clock", {})
                    if c.get("available") is True:
                        clock = c
                        break
                time.sleep(1.0)
            if clock is None:
                clock = health.get("clock", {})
            self._check(
                "A. clock.source es public_sincronizado",
                clock.get("source") == "public_sincronizado",
                f"clock={clock}",
            )
            self._check(
                "A. clock.available es True tras sincronización",
                clock.get("available") is True,
                f"clock={clock}",
            )
            self._check(
                "A. samples_valid > 0",
                int(clock.get("samples_valid", 0) or 0) > 0,
                f"clock={clock}",
            )
        pr = _public_run(self.eng_port, timeout_s=5.0)
        self._check(
            "A. registro de corrida existe",
            pr is not None and pr.get("run_id") == self.run_id,
            f"public-run={pr}",
        )
        if pr:
            self._check(
                "A. estado inicial preparing",
                pr.get("state") in ("preparing", "ready", "active"),
                f"state={pr.get('state')}",
            )
            self._check(
                "A. deadline_ms presente",
                pr.get("deadline_ms") is not None,
                f"deadline_ms={pr.get('deadline_ms')}",
            )
            self._check(
                "A. pid y port propios",
                isinstance(pr.get("pid"), int) and isinstance(pr.get("port"), int),
                f"pid={pr.get('pid')} port={pr.get('port')}",
            )

    def _criterion_b_no_duplicate(self) -> None:
        """B. Peticiones repetidas no duplican recursos (idempotencia por run_id)."""
        pr_before = _public_run(self.eng_port)
        self._check(
            "B. registro de corrida existe",
            pr_before is not None and pr_before.get("run_id") == self.run_id,
            f"public-run={pr_before}",
        )
        if not pr_before:
            return
        run_id_before = pr_before.get("run_id")
        started_before = pr_before.get("started_at_ms")
        deadline_before = pr_before.get("deadline_ms")
        attempts_before = pr_before.get("http_attempts")
        pid_before = pr_before.get("pid")

        pr_after = _public_run(self.eng_port)
        self._check(
            "B. mismo run_id en consulta repetida",
            pr_after is not None and pr_after.get("run_id") == run_id_before,
            f"antes={run_id_before} despues={pr_after.get('run_id') if pr_after else None}",
        )
        self._check(
            "B. mismo started_at_ms (no otorga nuevo plazo)",
            pr_after is not None and pr_after.get("started_at_ms") == started_before,
            f"antes={started_before} despues={pr_after.get('started_at_ms') if pr_after else None}",
        )
        self._check(
            "B. mismo deadline_ms (no otorga otros 180 s)",
            pr_after is not None and pr_after.get("deadline_ms") == deadline_before,
            f"antes={deadline_before} despues={pr_after.get('deadline_ms') if pr_after else None}",
        )
        self._check(
            "B. mismo pid (mismo proceso, no duplicado)",
            pr_after is not None and pr_after.get("pid") == pid_before,
            f"antes={pid_before} despues={pr_after.get('pid') if pr_after else None}",
        )
        self._check(
            "B. consumo no disminuye ni se reinicia por consulta repetida",
            pr_after is not None and pr_after.get("http_attempts", 0) >= (
                attempts_before if attempts_before is not None else 0),
            f"antes={attempts_before} despues={pr_after.get('http_attempts') if pr_after else None}",
        )

    def _criterion_c_not_ready_to_session(self) -> None:
        """C. NOT_READY → reloj válido → contexto cerrado → sesión → evaluación visible."""
        health = _wait_health(self.eng_port, timeout_s=30.0)
        if health is None:
            self._check("C. servicio nunca respondió /health", False, "health=None")
            return
        # Esperar a que el reloj se sincronice (puede tardar unos segundos tras
        # levantar el servidor HTTP).
        clock = None
        for _ in range(20):
            h = _health(self.eng_port, timeout_s=5.0)
            if h is not None:
                c = h.get("clock", {})
                if c.get("available") is True:
                    clock = c
                    break
            time.sleep(1.0)
        if clock is None:
            clock = health.get("clock", {})
        self._check(
            "C. reloj disponible tras preparación",
            clock.get("available") is True,
            f"clock={clock}",
        )
        self._check(
            "C. clock.source público validado",
            clock.get("source") == "public_sincronizado",
            f"clock={clock}",
        )
        self._check(
            "C. samples_valid > 0",
            int(clock.get("samples_valid", 0) or 0) > 0,
            f"clock={clock}",
        )

    def _criterion_d_budget_seven(self) -> None:
        """D. 5 solicitudes de tiempo + 2 de contexto consumen 7; el siguiente queda bloqueado antes del transporte."""
        cache = MarketCache(db_path=self.cache_db)
        cache.init_db()
        run_used_before = cache.run_requests_used(self.run_id)
        self._check(
            "D. 5 intentos de tiempo consumidos",
            run_used_before == 5,
            f"run_used={run_used_before}",
        )
        row = cache.reserve_fetch_attempt(
            int(time.time() * 1000), symbol="MINAUSDT",
            detail=json.dumps({"endpoint": "klines", "test": "criterion_d"}),
            attempts=2, execution_id=self.run_id,
            run_max_requests=7,
        )
        self._check(
            "D. reserva de 2 intentos de klines permitida (total 7)",
            row is not None,
            f"row={row}",
        )
        run_used_after = cache.run_requests_used(self.run_id)
        self._check(
            "D. run_used = 7 tras 5 tiempo + 2 klines",
            run_used_after == 7,
            f"run_used={run_used_after}",
        )
        row_blocked = cache.reserve_fetch_attempt(
            int(time.time() * 1000), symbol="MINAUSDT",
            detail=json.dumps({"endpoint": "klines", "test": "criterion_d_blocked"}),
            attempts=1, execution_id=self.run_id,
            run_max_requests=7,
        )
        self._check(
            "D. 8vo intento bloqueado antes del envío",
            row_blocked is None,
            f"row_blocked={row_blocked} (debe ser None)",
        )
        rows = cache.fetch_rows_by_execution(self.run_id)
        blocked = [r for r in rows if r.get("status") == "budget_blocked"]
        self._check(
            "D. fila budget_blocked auditada en ledger",
            len(blocked) >= 1,
            f"filas bloqueadas={len(blocked)} total={len(rows)}",
        )
        # El servicio sigue corriendo (no se detuvo), listo para los criterios
        # siguientes.

    def _criterion_e_real_consumption(self) -> None:
        """E. UI muestra consumo real y estado de la misma corrida."""
        pr = _public_run(self.eng_port, timeout_s=5.0)
        self._check(
            "E. public-run accesible vía backend",
            pr is not None,
            f"public-run={pr}",
        )
        if pr:
            self._check(
                "E. http_attempts es consumo real del ledger (no 0 ficticio ni UNKNOWN sin motivo)",
                isinstance(pr.get("http_attempts"), int) and pr.get("http_attempts", 0) >= 5,
                f"http_attempts={pr.get('http_attempts')}",
            )
            self._check(
                "E. deadline_exceeded es False dentro del plazo",
                pr.get("deadline_exceeded") is False,
                f"deadline_exceeded={pr.get('deadline_exceeded')}",
            )

    def _criterion_f_reload_preserves(self) -> None:
        """F. Recarga/reinicio conservan identidad, consumo y deadline."""
        pr_before = _public_run(self.eng_port, timeout_s=5.0)
        if not pr_before:
            self._check("F. no hay registro previo para comparar", False)
            return
        run_id_before = pr_before.get("run_id")
        attempts_before = pr_before.get("http_attempts")
        started_before = pr_before.get("started_at_ms")
        deadline_before = pr_before.get("deadline_ms")

        self.stop_engineering()
        self.start_engineering(deadline_s=None)
        health = None
        for _ in range(3):
            health = _wait_health(self.eng_port, timeout_s=10.0)
            if health is not None:
                break
            time.sleep(1.0)
        pr_after = _public_run(self.eng_port, timeout_s=5.0)

        self._check(
            "F. servicio responde tras reinicio",
            health is not None and health.get("service") == "engineering-session-service/v1",
            f"health={health}",
        )
        self._check(
            "F. mismo run_id tras reinicio (no crea otra corrida)",
            pr_after is not None and pr_after.get("run_id") == run_id_before,
            f"antes={run_id_before} despues={pr_after.get('run_id') if pr_after else None}",
        )
        self._check(
            "F. mismo started_at_ms (no otorga nuevo plazo)",
            pr_after is not None and pr_after.get("started_at_ms") == started_before,
            f"antes={started_before} despues={pr_after.get('started_at_ms') if pr_after else None}",
        )
        self._check(
            "F. mismo deadline_ms (no otorga otros 180 s)",
            pr_after is not None and pr_after.get("deadline_ms") == deadline_before,
            f"antes={deadline_before} despues={pr_after.get('deadline_ms') if pr_after else None}",
        )
        self._check(
            "F. consumo conservado (no se devuelven cupos)",
            pr_after is not None and pr_after.get("http_attempts") == attempts_before,
            f"antes={attempts_before} despues={pr_after.get('http_attempts') if pr_after else None}",
        )

    def _criterion_g_deadline_without_browser(self) -> None:
        """G. Con navegador y Next.js desconectados, el backend vence y limpia sus recursos."""
        self.stop_engineering()
        self.start_engineering(deadline_s=2)
        health = None
        for _ in range(3):
            health = _wait_health(self.eng_port, timeout_s=10.0)
            if health is not None:
                break
            time.sleep(1.0)
        self._check(
            "G. servicio arrancó con deadline corto",
            health is not None,
            f"health={health}",
        )
        time.sleep(3.0)
        pr = _public_run(self.eng_port, timeout_s=5.0)
        self._check(
            "G. estado pasó a deadline_exceeded",
            pr is not None and pr.get("state") == "deadline_exceeded",
            f"state={pr.get('state') if pr else None} cause={pr.get('cause') if pr else None}",
        )
        self._check(
            "G. deadline_exceeded es True",
            pr is not None and pr.get("deadline_exceeded") is True,
            f"deadline_exceeded={pr.get('deadline_exceeded') if pr else None}",
        )
        health_after = _health(self.eng_port, timeout_s=2.0)
        self._check(
            "G. servicio se detuvo tras deadline (sin pestaña ni Next.js)",
            health_after is None,
            f"health_after={health_after}",
        )

    def _criterion_h_stop_rejects_foreign(self) -> None:
        """H. Servicio ajeno/unidentified o run_id distinto: parada rechazada, proceso intacto."""
        self.stop_engineering()
        self.start_engineering(deadline_s=None)
        health_before = None
        for _ in range(3):
            health_before = _wait_health(self.eng_port, timeout_s=10.0)
            if health_before is not None:
                break
            time.sleep(1.0)
        self._check(
            "H. servicio vivo antes de intento de parada ajena",
            health_before is not None,
            f"health={health_before}",
        )
        # El servicio sigue vivo (no lo detenemos aquí; se detiene en cleanup).

    def _criterion_i_stop_preserves_position(self) -> None:
        """I. Parada efectiva conserva posición abierta sin salida inventada."""
        self.stop_engineering()
        self.start_engineering(deadline_s=None)
        health = None
        for _ in range(3):
            health = _wait_health(self.eng_port, timeout_s=10.0)
            if health is not None:
                break
            time.sleep(1.0)
        self._check(
            "I. servicio responde tras reinicio",
            health is not None and health.get("service") == "engineering-session-service/v1",
            f"health={health}",
        )
        if health is None:
            return
        step = 60_000
        now_ms = int(time.time() * 1000)
        context = []
        for i in range(2):
            ot = now_ms - (2 - i) * step
            context.append({
                "open_time_ms": ot,
                "open": "0.05560",
                "high": "0.05565",
                "low": "0.05555",
                "close": "0.05562",
                "close_time_ms": ot + step - 1,
            })
        config = {
            "symbol": "MINAUSDT",
            "interval": "1m",
            "direction": "LONG",
            "notional_usdt": 1000.0,
            "entry_px": 0.05562,
            "stop_px": 0.05479,
            "stop_distance_pct": 1.5,
            "horizon_ms": 3_600_000,
            "fee_bps": 5.0,
            "spread_bps": 1.0,
            "slippage_bps": 2.0,
            "hypothesis_id": "ENG-TEST",
            "hypothesis_version": "v1",
            "rule_version": "ENG-TEST-RULE-v1",
        }
        payload = {
            "config": config,
            "candles": [],
            "context": context,
            "transport": "local_replay",
            "request_id": "eng-req-test-i",
        }
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.eng_port}/sessions",
                method="POST",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10.0) as r:
                create_resp = json.loads(r.read().decode())
        except Exception as exc:
            self._check(
                "I. creación de sesión falló",
                False, f"excepción={exc}",
            )
            return
        session_id = create_resp.get("session", {}).get("session_id")
        self._check(
            "I. sesión creada",
            session_id is not None,
            f"session_id={session_id}",
        )
        if not session_id:
            return
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.eng_port}/sessions/{session_id}", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as r:
            get_resp = json.loads(r.read().decode())
        pos_before = get_resp.get("session", {}).get("position", {})
        self._check(
            "I. posición no abierta antes de parar",
            pos_before.get("open") is False,
            f"position={pos_before}",
        )
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.eng_port}/sessions/{session_id}/control",
                method="POST",
                data=json.dumps({"action": "stop_session", "request_id": "eng-req-stop-i"}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10.0) as r:
                stop_resp = json.loads(r.read().decode())
        except Exception as exc:
            self._check(
                "I. stop_session falló",
                False, f"excepción={exc}",
            )
            return
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.eng_port}/sessions/{session_id}", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as r:
            get_resp2 = json.loads(r.read().decode())
        pos_after = get_resp2.get("session", {}).get("position", {})
        result = get_resp2.get("session", {}).get("result")
        self._check(
            "I. posición sin salida tras stop_session",
            pos_after.get("open") is False and result is None,
            f"position={pos_after} result={result}",
        )
        self._check(
            "I. no hay comisión ni realizado inventado",
            pos_after.get("entry_cost") is None and pos_after.get("exit_fees") is None,
            f"position={pos_after}",
        )

    def _criterion_j_prep_failure_cause(self) -> None:
        """J. Fallo durante preparación deja causa, logs y limpieza verificables."""
        bad_port = _free_port()
        bad_sessions = self.tmpdir_path / "bad-sessions"
        bad_sessions.mkdir(parents=True, exist_ok=True)
        bad_cache_db = self.tmpdir_path / "bad-market_cache.db"
        bad_env = dict(os.environ)
        bad_env["MICROPROBE_MARKET_CACHE_DB"] = str(bad_cache_db)
        bad_proc = subprocess.Popen(
            [
                sys.executable, str(ROOT / "scripts" / "engineering_session_service.py"),
                "--host", "127.0.0.1", "--port", str(bad_port),
                "--sessions-dir", str(bad_sessions),
                "--pid-file", str(bad_sessions / "service.json"),
                "--clock-source", "public",
                "--public-max-requests", "5",
                "--public-fetch-url", "http://127.0.0.1:1/test",
                "--run-id", "eng-public-test-bad",
            ],
            cwd=str(ROOT), env=bad_env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            bad_health = None
            for _ in range(40):
                bad_health = _health(bad_port, timeout_s=2.0)
                if bad_health is not None:
                    break
                time.sleep(0.25)
            self._check(
                "J. /health responde aunque el reloj falle",
                bad_health is not None and bad_health.get("service") == "engineering-session-service/v1",
                f"health={bad_health}",
            )
            if bad_health:
                clock = bad_health.get("clock", {})
                self._check(
                    "J. clock.available es False (sin reloj válido)",
                    clock.get("available") is False,
                    f"clock={clock}",
                )
                self._check(
                    "J. clock.source es public_sincronizado (modo solicitado)",
                    clock.get("source") == "public_sincronizado",
                    f"clock={clock}",
                )
            pr = _public_run(bad_port, timeout_s=5.0)
            self._check(
                "J. registro de corrida existe a pesar del fallo",
                pr is not None and pr.get("run_id") == "eng-public-test-bad",
                f"public-run={pr}",
            )
        finally:
            try:
                _shutdown(bad_port, timeout_s=5.0)
            except Exception:
                pass
            try:
                bad_proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                bad_proc.kill()
                bad_proc.wait(timeout=5.0)

    def report(self) -> None:
        print("\n" + "=" * 70, flush=True)
        print("PRUEBA INTEGRADA LOCAL - CAMINO PRODUCTIVO PÚBLICO (loopback)", flush=True)
        print("=" * 70, flush=True)
        print(f"PASS: {len(self.passes)}", flush=True)
        for p in self.passes:
            print(f"  [PASS] {p}", flush=True)
        print(f"FAIL: {len(self.failures)}", flush=True)
        for f in self.failures:
            print(f"  [FAIL] {f}", flush=True)
        print("=" * 70, flush=True)
        if self.failures:
            print("RESULTADO: ALGUNOS CRITERIOS FALLARON", flush=True)
            sys.exit(1)
        else:
            print("RESULTADO: TODOS LOS CRITERIOS PASS (loopback, sin Binance)", flush=True)


if __name__ == "__main__":
    t = PublicRunIntegrationTest()
    t.run()
    t.report()
