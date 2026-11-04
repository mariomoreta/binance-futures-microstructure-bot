"""Arnés compartido de aceptación pública (loopback, sin Binance).

Reúne los procesos REALES del camino productivo:
  * ``scripts/engineering_session_service.py`` (servicio canónico);
  * el BFF productivo de Next.js (``frontend`` build ya existente);
  * proveedores HTTP loopback configurables (``/time`` y ``/fapi/v1/klines``).

Aislamiento: sesiones, SQLite, pid-files, logs y el roots del gestor viven
bajo un ``TemporaryDirectory`` exclusivo por prueba. Nada escribe en
``data/engineering-session`` del repositorio.

Bloqueo de red pública: los procesos Python reciben un ``sitecustomize`` que
rechaza y registra conexiones fuera de loopback; el proceso Node recibe un
``--require`` que rechaza y registra resoluciones DNS no loopback. El registro
se publica en ``PUBLIC_BLOCK_LOG`` y las pruebas lo consultan.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "engineering_session_service.py"
FRONTEND = ROOT / "frontend"
NEXT_BIN = FRONTEND / "node_modules" / "next" / "dist" / "bin" / "next"
CANONICAL_HOST = "127.0.0.1:3020"  # guardia de origen del BFF productivo
SERVICE_NAME = "engineering-session-service/v1"


# ---------------------------------------------------------------------------
# Puertos / HTTP
# ---------------------------------------------------------------------------

def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def is_listening(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_port_listening(port: int, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_listening(port):
            return
        time.sleep(0.2)
    raise TimeoutError(f"puerto {port} no escuchó en {timeout_s}s")


def wait_port_free(port: int, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not is_listening(port):
            return
        time.sleep(0.2)
    raise TimeoutError(f"puerto {port} no se liberó en {timeout_s}s")


def http_json(
    port: int,
    path: str,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
    host: str = CANONICAL_HOST,
    timeout: float = 20.0,
) -> Tuple[int, Any]:
    """Petición HTTP real. ``host`` reproduce el Host canónico del BFF."""
    url = f"http://127.0.0.1:{port}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Host": host, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def health(port: int) -> Optional[Dict[str, Any]]:
    try:
        status, payload = http_json(
            port, "/health", host=f"127.0.0.1:{port}", timeout=2.0)
    except Exception:
        return None
    return payload if status == 200 and isinstance(payload, dict) else None


def wait_health(port: int, timeout_s: float = 30.0) -> Optional[Dict[str, Any]]:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = health(port)
        if last is not None and last.get("service") == SERVICE_NAME:
            return last
        time.sleep(0.2)
    return last


def wait_clock_ready(port: int, timeout_s: float = 30.0) -> Optional[Dict[str, Any]]:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        payload = health(port)
        if payload is not None:
            last = payload
            if (payload.get("clock") or {}).get("available") is True:
                return payload
        time.sleep(0.2)
    return last


def public_run(port: int) -> Any:
    try:
        status, payload = http_json(
            port, "/public-run", host=f"127.0.0.1:{port}", timeout=2.0)
    except Exception:
        return None
    return payload if status == 200 else None


def post_shutdown(port: int, timeout: float = 5.0) -> bool:
    try:
        status, _ = http_json(
            port, "/shutdown", method="POST", body={},
            host=f"127.0.0.1:{port}", timeout=timeout)
        return status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Guardas de red pública (se aplican a los procesos hijos)
# ---------------------------------------------------------------------------

_SITECUSTOMIZE = '''\
import os, socket

_LOG = os.environ.get("PUBLIC_BLOCK_LOG")
_ALLOWED = {"", "localhost", "127.0.0.1", "::1"}
_ORIG = socket.create_connection


def _log(msg):
    if not _LOG:
        return
    try:
        with open(_LOG, "a", encoding="utf-8") as fh:
            fh.write(msg + "\\n")
    except OSError:
        pass


def _guarded_create_connection(address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else address
    text = "" if host is None else str(host)
    if not (text in _ALLOWED or text.startswith("127.")):
        _log("BLOCKED_PYTHON_CONNECT " + repr(address))
        raise OSError("PUBLIC_NETWORK_BLOCKED: " + text)
    return _ORIG(address, *args, **kwargs)


socket.create_connection = _guarded_create_connection
'''

_NODE_GUARD = '''\
const dns = require("node:dns");
const fs = require("node:fs");
const allowed = new Set(["", "localhost", "127.0.0.1", "::1"]);
function log(msg) {
  const p = process.env.PUBLIC_BLOCK_LOG;
  if (!p) return;
  try { fs.appendFileSync(p, msg + "\\n"); } catch (e) { /* noop */ }
}
const orig = dns.lookup;
dns.lookup = function (host, opts, cb) {
  const text = host == null ? "" : String(host);
  if (!(allowed.has(text) || text.startsWith("127."))) {
    log("BLOCKED_NODE_LOOKUP " + text);
    const err = new Error("PUBLIC_NETWORK_BLOCKED: " + text);
    err.code = "ENOTFOUND";
    if (typeof opts === "function") return opts(err);
    return process.nextTick(() => cb(err));
  }
  return orig.call(dns, host, opts, cb);
};
'''


class NetworkGuard:
    """Directorio con las guardas y el registro de intentos bloqueados."""

    def __init__(self, base: Path) -> None:
        self.dir = base / "netguard"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
        self.node_guard = self.dir / "node_guard.js"
        self.node_guard.write_text(_NODE_GUARD, encoding="utf-8")
        self.log = base / "public-network-blocked.log"
        self.log.write_text("", encoding="utf-8")

    def python_env(self, env: Dict[str, str]) -> Dict[str, str]:
        current = env.get("PYTHONPATH") or ""
        env["PYTHONPATH"] = str(self.dir) + (os.pathsep + current if current else "")
        env["PUBLIC_BLOCK_LOG"] = str(self.log)
        return env

    def node_env(self, env: Dict[str, str]) -> Dict[str, str]:
        current = env.get("NODE_OPTIONS") or ""
        env["NODE_OPTIONS"] = (
            f"--require {self.node_guard.as_posix()}"
            + (f" {current}" if current else ""))
        env["PUBLIC_BLOCK_LOG"] = str(self.log)
        return env

    def blocked_lines(self) -> List[str]:
        try:
            return [ln for ln in self.log.read_text(encoding="utf-8").splitlines()
                    if ln.strip()]
        except OSError:
            return []


# ---------------------------------------------------------------------------
# Proveedor HTTP loopback: /time y /fapi/v1/klines con contadores reales
# ---------------------------------------------------------------------------

class LoopbackProvider:
    """Contabiliza cada solicitud REAL que recibe el transporte."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.time_hits = 0
        self.klines_hits: List[Dict[str, Any]] = []
        self.other_hits: List[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_GET(self) -> None:  # noqa: N802
                outer._handle(self)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True,
            name="loopback-provider")

    # --- ciclo de vida --------------------------------------------------
    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        try:
            self.server.shutdown()
        finally:
            self.server.server_close()

    # --- contrato -------------------------------------------------------
    @property
    def time_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/time"

    def counts(self) -> Dict[str, int]:
        with self.lock:
            return {
                "time": self.time_hits,
                "klines": len(self.klines_hits),
                "other": len(self.other_hits),
                "total": self.time_hits + len(self.klines_hits) + len(self.other_hits),
            }

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urllib.parse.urlsplit(handler.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/time":
            with self.lock:
                self.time_hits += 1
            body = json.dumps({"serverTime": int(time.time() * 1000)}).encode()
        elif path == "/fapi/v1/klines":
            query = urllib.parse.parse_qs(parsed.query)
            with self.lock:
                self.klines_hits.append({k: v[0] for k, v in query.items()})
            start = int(query.get("startTime", ["0"])[0] or 0)
            limit = min(int(query.get("limit", ["1"])[0] or 1), 10)
            rows = []
            for i in range(max(limit, 1)):
                open_ms = start + i * 60_000
                rows.append([
                    open_ms, "0.05562", "0.05565", "0.05555", "0.05562",
                    "100", open_ms + 59_999, "5.5", 10, "5", "5", "0",
                ])
            body = json.dumps(rows).encode()
        else:
            with self.lock:
                self.other_hits.append(handler.path)
            handler.send_response(404)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)


# ---------------------------------------------------------------------------
# Servicio de ingeniería (proceso canónico)
# ---------------------------------------------------------------------------

def start_engineering_service(
    port: int,
    sessions_dir: Path,
    run_id: str,
    guard: NetworkGuard,
    time_url: Optional[str] = None,
    deadline_s: Optional[int] = None,
    cache_db: Optional[Path] = None,
    extra_env: Optional[Dict[str, str]] = None,
) -> subprocess.Popen:
    env = guard.python_env(dict(os.environ))
    if cache_db is not None:
        env["MICROPROBE_MARKET_CACHE_DB"] = str(cache_db)
    if deadline_s is not None:
        env["PUBLIC_RUN_DEADLINE_S"] = str(deadline_s)
    if extra_env:
        env.update(extra_env)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(SCRIPT),
        "--host", "127.0.0.1", "--port", str(port),
        "--sessions-dir", str(sessions_dir),
        "--pid-file", str(sessions_dir / "service.json"),
    ]
    if time_url is not None:
        cmd += [
            "--clock-source", "public",
            "--public-max-requests", "5",
            "--public-fetch-url", time_url,
            "--run-id", run_id,
        ]
    else:
        cmd += ["--clock-source", "local"]
    log_dir = sessions_dir.parent
    out = open(log_dir / f"service-{port}.out.log", "w", encoding="utf-8")
    err = open(log_dir / f"service-{port}.err.log", "w", encoding="utf-8")
    return subprocess.Popen(
        cmd, cwd=str(ROOT), env=env, stdout=out, stderr=err,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def stop_process(proc: subprocess.Popen, port: Optional[int] = None,
                 timeout_s: float = 20.0) -> None:
    if port is not None and is_listening(port):
        post_shutdown(port)
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            pass


# ---------------------------------------------------------------------------
# BFF productivo (Next.js ya construido, puerto alterno, Host canónico)
# ---------------------------------------------------------------------------

class BffProcess:
    def __init__(self, port: int, service_root: Path, provider: LoopbackProvider,
                 guard: NetworkGuard, cache_db: Path, log_dir: Path,
                 allowed_host: Optional[str] = None,
                 service_port: int = 8797) -> None:
        self.port = port
        self.service_root = service_root
        self.proc: Optional[subprocess.Popen] = None
        self.log_dir = log_dir
        self._provider = provider
        self._guard = guard
        self._cache_db = cache_db
        # Origen explícito para el BFF de pruebas. Si se omite, el BFF usa
        # su valor de producción por defecto (127.0.0.1:3020) y las pruebas
        # deben spoofear el encabezado Host. Para navegador real (E) se pasa
        # el puerto del servidor de pruebas.
        self._allowed_host = allowed_host
        # Puerto del servicio de ingeniería (contrato 8797 por defecto; pruebas
        # aisladas pueden usar otro puerto libre).
        self._service_port = service_port

    def start(self) -> None:
        node = shutil.which("node")
        if node is None:
            raise RuntimeError("node no disponible para levantar el BFF")
        if not NEXT_BIN.exists():
            raise RuntimeError(f"build del BFF ausente: {NEXT_BIN}")
        env = self._guard.node_env(dict(os.environ))
        env.update({
            "ENGINEERING_SERVICE_ROOT": str(self.service_root),
            "ENGINEERING_SERVICE_SCRIPT": str(SCRIPT),
            "ENGINEERING_SERVICE_PORT": str(self._service_port),
            "ENGINEERING_SERVICE_PYTHON": sys.executable,
            "MICROPROBE_MARKET_CACHE_DB": str(self._cache_db),
            "PUBLIC_FETCH_URL": self._provider.time_url,
            "NEXT_TELEMETRY_DISABLED": "1",
        })
        if self._allowed_host is not None:
            env["ENGINEERING_PUBLIC_ALLOWED_HOST"] = self._allowed_host
        out = open(self.log_dir / f"bff-{self.port}.out.log", "w", encoding="utf-8")
        err = open(self.log_dir / f"bff-{self.port}.err.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [node, str(NEXT_BIN), "start", "-p", str(self.port), "-H", "127.0.0.1"],
            cwd=str(FRONTEND), env=env, stdout=out, stderr=err,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        wait_port_listening(self.port, timeout_s=60.0)

    def stop(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5.0)
        self.proc = None


def bff_sessions_dir(service_root: Path) -> Path:
    return service_root / "data" / "engineering-session" / "sessions"


def bff_public_run_path(service_root: Path) -> Path:
    """Registro persistente REAL del backend (vive en sessions_dir)."""
    return service_root / "data" / "engineering-session" / "sessions" / "public-run.json"


def bff_manager_run_record_path(service_root: Path) -> Path:
    """Ruta que ``readPublicRunRecord()`` del gestor BFF consulta.

    No coincide con la anterior: se conserva como evidencia del desajuste
    (criterio H), no como fuente de verdad.
    """
    return service_root / "data" / "engineering-session" / "public-run.json"


def bff_pid_file(service_root: Path) -> Path:
    return service_root / "data" / "engineering-session" / "service.json"


def pid_alive(pid: int) -> bool:
    """¿Sigue vivo el PID? (Windows: OpenProcess + STILL_ACTIVE)."""
    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [
        ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.GetExitCodeProcess.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(
        0x1000,  # PROCESS_QUERY_LIMITED_INFORMATION
        False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_uint32()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


# ---------------------------------------------------------------------------
# Sesión de ingeniería: contexto cerrado + cierres nuevos + entrada real
# ---------------------------------------------------------------------------

STEP_MS = 60_000


def entry_payload(now_ms: int, request_id: str) -> Dict[str, Any]:
    """Secuencia local existente que produce una entrada real (sin flags).

    Contexto cerrado (2 velas 1m) fija el reloj T. Tres aperturas de
    operación revelan: apertura 1 (sin señal), apertura 2 (cierre de la vela
    1 conocido y a favor => ENTRADA_SIMULADA pendiente) y apertura 3 (fill en
    el open revelado, mecánica canónica de run_backtest). No se tocan reglas
    ni parámetros económicos.
    """
    context = []
    for i in range(2):
        ot = now_ms - (3 - i) * STEP_MS
        context.append({
            "symbol": "MINAUSDT", "interval": "1m",
            "open_time_ms": ot,
            "close_time_ms": ot + STEP_MS - 1,
            "open": 0.05560, "high": 0.05565, "low": 0.05555, "close": 0.05562,
        })
    candles = []
    for i in range(3):
        ot = now_ms - (1 - i) * STEP_MS  # -1m, 0m, +1m
        candles.append({
            "open_time_ms": ot,
            "close_time_ms": ot + STEP_MS - 1,
            "open": 0.05562, "high": 0.05565, "low": 0.05555, "close": 0.05562,
        })
    config = {
        "symbol": "MINAUSDT", "interval": "1m", "direction": "LONG",
        "notional_usdt": 1000.0, "entry_px": 0.05562, "stop_px": 0.05479,
        "stop_distance_pct": 1.5, "horizon_ms": 3_600_000,
        "fee_bps": 5.0, "spread_bps": 1.0, "slippage_bps": 2.0,
        "hypothesis_id": "ENG-ACCEPTANCE", "hypothesis_version": "v1",
        "rule_version": "ENG-ACCEPTANCE-RULE-v1",
    }
    return {
        "config": config,
        "candles": candles,
        "context": context,
        "transport": "local_replay",
        "request_id": request_id,
    }
