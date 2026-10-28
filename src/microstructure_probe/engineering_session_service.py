"""Servicio de sesión de ingeniería autónoma (solo loopback).

Mantiene la sesión del lado backend y conduce el avance mediante EVENTOS del
transporte local: un reproductor con cadencia publica solo eventos de
revelado (uno por vela) y el controlador los interpreta con el motor
existente ``paper_lab_engine`` — autoridad económica única — paso a paso
incrementalmente. El navegador inicia (create + control start), observa (GET
del estado) y detiene (control stop); cerrar la pestaña NO detiene la sesión.

No hay Binance, no hay feed vivo, no hay órdenes reales, no hay capital real.
No hay un proceso Python por tick ni un gestor paralelo: un solo proceso de
servicio reutiliza el motor y los mecanismos de persistencia existentes
(escritura atómica + revisión optimista + lock por archivo).

El evaluador solo recibe el prefijo revelado: el dict público del motor no
publica velas futuras y el reproductor no entrega OHLC, solo el avance
(evento de revelado) que la conducción traduce en llamadas del motor.

Contrato (``engineering-session-service/v1``):
  GET  /health
  GET  /sessions                       -> lista resumida
  POST /sessions                       -> crea sesión {config, candles, ...}
  GET  /sessions/{id}                  -> estado público (prefijo revelado)
  POST /sessions/{id}/control          -> {"action": start|stop|step|exit|
                                          restart|stop_session|evaluate,
                                          "expected_revision"?,
                                          "request_id"?}
  POST /shutdown

Acciones del control:
  start        : comienza la conducción autónoma del backend.
  stop         : detiene la conducción; la sesión queda como está (sin
                 cierre inventado); reanudar con otra llamada start.
  step         : un avance manual (el mismo tipo de evento que produce el
                 transporte local; sin repetición por reloj).
  exit         : salida manual (manual_exit del motor).
  restart      : reinicio de sesión (motor).
  stop_session : detiene la conducción y congela la sesión (detenida).
  evaluate     : reevalua en T cuando el estado lo admite.

Escribe SOLO en el directorio de sesiones configurado (aislado en pruebas;
sin tocar bases canónicas).
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from microstructure_probe import paper_lab_engine as engine  # noqa: E402

SERVICE_VERSION = "engineering-session-service/v1"
SESSIONS_DEFAULT = ROOT / "paper-lab-sessions"
PID_DEFAULT = ROOT / "data" / "engineering-session" / "service.json"
DEFAULT_PORT = 8797
DEFAULT_HOST = "127.0.0.1"
DEFAULT_CADENCE_MS = 700.0
# Techo de seguridad por conducción: nº máximo de eventos consumidos.
DRIVE_MAX_EVENTS = 4096

ALLOWED_ACTIONS = {
    "start", "stop", "step", "exit", "restart", "stop_session", "evaluate",
}

CONFLICT_CODES = {"REVISION_CONFLICT", "SESSION_NOT_DRIVEABLE", "DRIVE_ACTIVE"}


def _now_ms() -> int:
    return int(time.time() * 1000)


class LocalReplayTransport:
    """Reproductor local con cadencia: emite eventos de REVELADO.

    Cada evento comunica únicamente que la vela ``index`` de la ventana de
    operación se abre (su open pasa a conocerse en el reloj del motor). NO
    lleva OHLC: el precio es propiedad del estado del motor y el evaluador
    solo recibe el prefijo revelado por el motor tras interpretar cada evento.

    ``schedule`` son los ``open_time_ms`` de la ventana de operación (futuro
    oculto del transporte). Al final emite ``EOF`` para cerrar el transporte
    con causa visible; ``STOPPED`` si la conducción se pide parar.
    """

    def __init__(self, schedule: List[int],
                 event_queue: "queue.Queue[Dict[str, Any]]",
                 cadence_ms: float,
                 stop_event: threading.Event,
                 started_event: threading.Event) -> None:
        self.schedule = list(schedule)
        self.event_queue = event_queue
        self.cadence_ms = max(float(cadence_ms), 0.0)
        self.stop_event = stop_event
        self.started_event = started_event
        self.thread: Optional[threading.Thread] = None
        self.emitted = 0

    def start(self) -> None:
        self.thread = threading.Thread(
            target=self._run, name="local-replay-transport", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        self.started_event.set()
        cadence_s = self.cadence_ms / 1000.0
        for index, open_time_ms in enumerate(self.schedule):
            if self.stop_event.is_set():
                self.event_queue.put({"type": "STOPPED", "index": index})
                return
            self.event_queue.put({
                "type": "REVEAL",
                "index": index,
                "open_time_ms": open_time_ms,
            })
            self.emitted += 1
            if cadence_s > 0:
                end = time.monotonic() + cadence_s
                while time.monotonic() < end:
                    if self.stop_event.is_set():
                        self.event_queue.put({
                            "type": "STOPPED", "index": index})
                        return
                    time.sleep(min(0.02, cadence_s))
        self.event_queue.put({"type": "EOF"})


class EngineeringSessionController:
    """Mantiene las sesiones y conduce el avance por eventos del transporte."""

    def __init__(self, sessions_dir: Path, cadence_ms: float) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.cadence_ms = float(cadence_ms)
        self._lock = threading.Lock()
        self._drives: Dict[str, Dict[str, Any]] = {}
        self._events: Dict[str, Dict[str, Any]] = {}

    # --- utilidades ---------------------------------------------------------
    def _load_state(self, session_id: str):
        if not engine._safe_session_id(session_id):
            raise ValueError("session_id inválido")
        return engine.load_session(session_id, str(self.sessions_dir))

    @staticmethod
    def _parse_config(raw: Dict[str, Any]) -> engine.PaperSessionConfig:
        return engine.PaperSessionConfig(
            symbol=str(raw["symbol"]), interval=str(raw["interval"]),
            direction=str(raw["direction"]),
            notional_usdt=float(raw["notional_usdt"]),
            entry_px=float(raw["entry_px"]), stop_px=float(raw["stop_px"]),
            stop_distance_pct=float(raw["stop_distance_pct"]),
            horizon_ms=int(raw["horizon_ms"]), fee_bps=float(raw["fee_bps"]),
            spread_bps=float(raw["spread_bps"]),
            slippage_bps=float(raw["slippage_bps"]),
            hypothesis_id=raw.get("hypothesis_id"),
            hypothesis_version=raw.get("hypothesis_version"),
            rule_version=raw.get("rule_version"),
            # create NO acepta decision: viene de evaluate (motor).
            decision=None,
            decision_reason=None,
            decision_evidence=None,
        )

    def _save(self, state, expected_revision: Optional[int],
              request_id: Optional[str]):
        res = engine.save_session(
            state, str(self.sessions_dir),
            expected_revision=expected_revision,
            request_id=request_id)
        if not res.ok:
            raise RuntimeError(
                res.error_code or "SAVE_FAILED",
                res.error_detail or "fallo al guardar")
        return res.state

    def drive_view(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            drive = self._drives.get(session_id)
            info = self._events.get(session_id)
        if drive is None:
            return {"state": "idle", "session_id": session_id}
        return self._drive_public(drive, info)

    def _drive_public(self, drive: Optional[Dict[str, Any]],
                      info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if drive is None:
            return {"state": "idle"}
        return {
            "state": drive["state"],
            "cause": drive.get("cause"),
            "started_at_ms": drive.get("started_at_ms"),
            "finished_at_ms": drive.get("finished_at_ms"),
            "events_processed": drive.get("events_processed", 0),
            "transport_events": (info or {}).get("transport_events", 0),
            "cadence_ms": drive.get("cadence_ms"),
            "runner": "local_replay",
        }

    # --- endpoints ----------------------------------------------------------
    def list_sessions(self) -> List[Dict[str, Any]]:
        rows = engine.list_sessions(str(self.sessions_dir))
        with self._lock:
            drives = {sid: self._drive_public(d, self._events.get(sid))
                      for sid, d in self._drives.items()}
        for row in rows:
            sid = row.get("session_id")
            if sid is not None and sid in drives:
                row["drive"] = drives[sid]
        return rows

    def create_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        config = self._parse_config(payload["config"])
        candles = [engine.PaperCandle(
            open_time_ms=int(r["open_time_ms"]), open=float(r["open"]),
            high=float(r["high"]), low=float(r["low"]),
            close=float(r["close"]),
            close_time_ms=int(r["close_time_ms"]),
        ) for r in payload.get("candles") or []]
        context = [engine.PaperCandle(
            open_time_ms=int(r["open_time_ms"]), open=float(r["open"]),
            high=float(r["high"]), low=float(r["low"]),
            close=float(r["close"]),
            close_time_ms=int(r["close_time_ms"]),
        ) for r in payload.get("context") or []]
        state = engine.create_session(
            config, candles, context,
            hypothesis_id=payload.get("hypothesis_id"),
            hypothesis_version=payload.get("hypothesis_version"),
            rule_version=payload.get("rule_version"),
        )
        state = self._save(state, None, payload.get("request_id"))
        return {"session": engine.session_to_public_dict(state)}

    def get_session(self, session_id: str) -> Dict[str, Any]:
        state = self._load_state(session_id)
        if state is None:
            raise KeyError("SESSION_NOT_FOUND")
        public = engine.session_to_public_dict(state, state.clock_ms)
        # Forma uniforme con el control: {session, drive} (drive como
        # hermano, no anidado dentro del estado del motor).
        return {"session": public, "drive": self.drive_view(session_id)}

    # --- acciones -----------------------------------------------------------
    def control(self, session_id: str, payload: Dict[str, Any]):
        action = str(payload.get("action") or "")
        if action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"acción no permitida: {action} (permitidas: "
                f"{sorted(ALLOWED_ACTIONS)})")
        expected_revision = payload.get("expected_revision")
        request_id = payload.get("request_id")
        if action in ("start", "stop"):
            with self._lock:
                if action == "start":
                    return self._start_drive(session_id, expected_revision)
                return self._stop_drive(session_id)
        return self._advance_action(
            session_id, action, expected_revision, request_id)

    # --- conducción ---------------------------------------------------------
    def _start_drive(self, session_id: str,
                     expected_revision: Optional[int]) -> Dict[str, Any]:
        state = self._load_state(session_id)
        if state is None:
            raise KeyError("SESSION_NOT_FOUND")
        drive = self._drives.get(session_id)
        if drive is not None and drive["state"] == "running":
            # Idempotencia: start repetido no crea un segundo reproductor.
            return {
                "session": engine.session_to_public_dict(state, state.clock_ms),
                "drive": self._drive_public(drive, self._events.get(session_id)),
            }
        if state.status in ("cerrada", "detenida"):
            raise RuntimeError(
                "SESSION_NOT_DRIVEABLE",
                f"estado {state.status} no admite conducción")
        if expected_revision is not None and state.revision != expected_revision:
            raise RuntimeError(
                "REVISION_CONFLICT",
                f"revision {state.revision} != esperada {expected_revision}")

        stop_event = threading.Event()
        started_event = threading.Event()
        event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        schedule = [c.open_time_ms for c in state.candles]
        transport = LocalReplayTransport(
            schedule, event_queue, self.cadence_ms, stop_event, started_event)
        drive = {
            "state": "running",
            "started_at_ms": _now_ms(),
            "finished_at_ms": None,
            "events_processed": 0,
            "cause": None,
            "stop_event": stop_event,
            "queue": event_queue,
            "transport": transport,
            "cadence_ms": self.cadence_ms,
        }
        self._drives[session_id] = drive
        self._events[session_id] = {"transport_events": 0}
        transport.start()
        thread = threading.Thread(
            target=self._run_drive, args=(session_id,),
            name=f"drive-{session_id[:24]}", daemon=True)
        thread.start()
        started_event.wait(timeout=2.0)
        return {
            "session": engine.session_to_public_dict(state, state.clock_ms),
            "drive": self._drive_public(drive, self._events.get(session_id)),
        }

    def _stop_drive(self, session_id: str) -> Dict[str, Any]:
        state = self._load_state(session_id)
        if state is None:
            raise KeyError("SESSION_NOT_FOUND")
        drive = self._drives.get(session_id)
        if drive is not None and drive["state"] == "running":
            drive["stop_requested"] = True
            drive["queue"].put({"type": "STOPPED"})
            # El hilo de conducción termina en el próximo límite de evento.
        return {
            "session": engine.session_to_public_dict(state, state.clock_ms),
            "drive": self._drive_public(drive, self._events.get(session_id)),
        }

    def _stop_drive_quiet(self, session_id: str) -> None:
        with self._lock:
            drive = self._drives.get(session_id)
        if drive is not None and drive["state"] == "running":
            drive["stop_requested"] = True
            drive["queue"].put({"type": "STOPPED"})

    def _advance_action(self, session_id: str, action: str,
                        expected_revision: Optional[int],
                        request_id: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(session_id)
        if state is None:
            raise KeyError("SESSION_NOT_FOUND")
        with self._lock:
            drive = self._drives.get(session_id)
            drive_running = drive is not None and drive["state"] == "running"
        if drive_running:
            raise RuntimeError(
                "DRIVE_ACTIVE",
                "la conducción autónoma está activa; pásela a stop antes de "
                "una acción manual")
        if expected_revision is not None and state.revision != expected_revision:
            raise RuntimeError(
                "REVISION_CONFLICT",
                f"revision {state.revision} != esperada {expected_revision}")
        if action == "step":
            state = self.advance_once(state, request_id=request_id)
        elif action == "exit":
            state = engine.manual_exit(state)
            state = self._save(state, expected_revision, request_id)
        elif action == "restart":
            state = engine.restart_session(state)
            state = self._save(state, expected_revision, request_id)
        elif action == "stop_session":
            self._stop_drive_quiet(session_id)
            state = self._load_state(session_id) or state
            if state.status not in ("cerrada", "detenida"):
                state = engine.stop_session(state)
                state = self._save(state, expected_revision, request_id)
        elif action == "evaluate":
            state = engine.evaluate_session(
                state,
                hypothesis_id=state.config.hypothesis_id,
                hypothesis_version=state.config.hypothesis_version,
                rule_version=state.config.rule_version,
                at_ms=state.clock_ms,
            )
            state = self._save(state, expected_revision, request_id)
        return {
            "session": engine.session_to_public_dict(state, state.clock_ms),
            "drive": self.drive_view(session_id),
        }

    def advance_once(self, state, request_id: Optional[str] = None):
        """Un evento del transporte interpretado por el motor Python.

        El motor es la única autoridad económica: cada evento de revelado
        avanza exactamente un paso (step_forward) y, si la única decisión
        vigente es abstención temporal, reevalua en el reloj recién conocido.
        Descartes terminales y sesiones cerradas no se reevaluan.
        """
        if state.status in ("cerrada", "detenida"):
            return state
        prev_revision = state.revision
        next_state = engine.step_forward(state)
        if next_state.status == state.status and \
                next_state.clock_ms == state.clock_ms and \
                next_state.cursor == state.cursor:
            # Sin vela por revelar: fin del transporte local (sin cambios).
            return state
        if next_state.status in ("sin_iniciar", "evaluando") and (
                next_state.config.decision in (None, "SIN_ENTRADA")):
            next_state = engine.evaluate_session(
                next_state,
                hypothesis_id=next_state.config.hypothesis_id,
                hypothesis_version=next_state.config.hypothesis_version,
                rule_version=next_state.config.rule_version or engine.RULE_CAUSAL_V1,
                at_ms=next_state.clock_ms,
            )
        return self._save(next_state, prev_revision, request_id)

    # --- hilo de conducción -------------------------------------------------
    def _run_drive(self, session_id: str) -> None:
        drive = self._drives.get(session_id)
        if drive is None:  # pragma: no cover
            return
        stop_event: threading.Event = drive["stop_event"]
        event_queue = drive["queue"]
        with self._lock:
            info = self._events.setdefault(
                session_id, {"transport_events": 0})
        while True:
            if stop_event.is_set():
                self._finish_drive(session_id, drive, "OPERATOR_STOP")
                break
            try:
                event = event_queue.get(
                    timeout=max(self.cadence_ms / 1000.0, 0.05))
            except queue.Empty:
                continue
            ev_type = event.get("type")
            with self._lock:
                if drive["state"] != "running":
                    continue
                if ev_type == "STOPPED":
                    self._finish_drive(session_id, drive, "OPERATOR_STOP")
                    break
                if ev_type == "EOF":
                    # El transporte local terminó: la sesión queda como está
                    # (sin cierre inventado); causa visible en la conducción.
                    self._finish_drive(session_id, drive, "END_OF_TRANSPORT")
                    break
                if ev_type != "REVEAL":
                    continue
                info["transport_events"] = int(info.get(
                    "transport_events", 0)) + 1
            drive["events_processed"] += 1
            try:
                state = self.advance_once(
                    self._load_state(session_id),
                    request_id=(f"drive-{session_id}-"
                                f"{drive['events_processed']}-{_now_ms()}"))
            except Exception as exc:  # noqa: BLE001 - superficie real
                self._finish_drive(
                    session_id, drive,
                    f"DRIVE_ERROR:{type(exc).__name__}: {exc}")
                break
            if state is None:
                self._finish_drive(session_id, drive, "SESSION_NOT_FOUND")
                break
            if state.status in ("cerrada", "detenida"):
                cause = ("SESSION_CLOSED" if state.status == "cerrada"
                         else "SESSION_STOPPED")
                self._finish_drive(session_id, drive, cause)
                break
            if drive["events_processed"] >= DRIVE_MAX_EVENTS:  # pragma: no cover
                self._finish_drive(
                    session_id, drive,
                    f"DRIVE_EVENT_LIMIT ({DRIVE_MAX_EVENTS})")
                break

    def _finish_drive(self, session_id: str, drive: Dict[str, Any],
                      cause: str) -> None:
        if drive["state"] == "running":
            drive["state"] = "stopped"
            drive["finished_at_ms"] = _now_ms()
            drive["cause"] = cause
        if drive.get("stop_event") is not None:
            drive["stop_event"].set()

    # --- parada -------------------------------------------------------------
    def shutdown(self) -> None:
        with self._lock:
            drives = list(self._drives.values())
        for drive in drives:
            if drive.get("stop_event") is not None:
                drive["stop_event"].set()


class _EngineeringHTTPHandler(BaseHTTPRequestHandler):
    server: "EngineeringHTTPServer"
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_guard(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        origin = self.headers.get("Origin")
        host_ok = host.startswith("127.0.0.1") or host.startswith("localhost")
        origin_ok = origin is None or origin.startswith("http://127.0.0.1") \
            or origin.startswith("http://localhost")
        return host_ok and origin_ok

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 16 * 1024 * 1024))
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            raise ValueError("JSON inválido en el cuerpo de la petición")
        if not isinstance(body, dict):
            raise ValueError("el cuerpo debe ser un objeto JSON")
        return body

    # --- verbos -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        world = self.server.world
        url = urlsplit(self.path)
        path = url.path.rstrip("/") or "/"
        try:
            if not self._auth_guard():
                self._send_json(403, {"error": "FORBIDDEN"})
                return
            if path == "/health":
                self._send_json(200, self.server.health_payload())
                return
            if path == "/sessions":
                self._send_json(200, {"sessions": world.list_sessions()})
                return
            if path.startswith("/sessions/"):
                sid = path[len("/sessions/"):]
                if "/" in sid:
                    self._send_json(404, {"error": "NOT_FOUND"})
                    return
                self._send_json(200, world.get_session(sid))
                return
            self._send_json(404, {"error": "NOT_FOUND", "path": path})
        except KeyError as exc:
            code = str(exc.__str__())
            code = code.strip("'\" ()")
            self._send_json(404, {"error": code or "NOT_FOUND"})
        except ValueError as exc:
            self._send_json(400, {"error": f"VALIDATION_ERROR: {exc}"})
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                500, {"error": "INTERNAL_ERROR",
                      "detail": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:  # noqa: N802
        world = self.server.world
        path = urlsplit(self.path).path.rstrip("/")
        try:
            if not self._auth_guard():
                self._send_json(403, {"error": "FORBIDDEN"})
                return
            if path == "/shutdown":
                self._send_json(200, {"ok": True, "pid": os.getpid()})
                self.server.stop_event.set()
                return
            if path == "/sessions":
                payload = self._read_json()
                self._send_json(200, world.create_session(payload))
                return
            if path.startswith("/sessions/"):
                parts = path[len("/sessions/"):].split("/")
                if len(parts) != 2 or parts[1] != "control":
                    self._send_json(404, {"error": "NOT_FOUND"})
                    return
                payload = self._read_json()
                self._send_json(200, world.control(parts[0], payload))
                return
            self._send_json(404, {"error": "NOT_FOUND", "path": path})
        except KeyError as exc:
            code = str(exc).strip("'\" ()")
            self._send_json(404, {"error": code or "NOT_FOUND"})
        except RuntimeError as exc:
            if len(exc.args) == 2:
                code, detail = exc.args
            else:
                code, detail = str(exc), None
            status = 409 if code in CONFLICT_CODES else (
                404 if code == "SESSION_NOT_FOUND" else 500)
            self._send_json(status, {"error": code, "detail": detail})
        except ValueError as exc:
            self._send_json(400, {"error": f"VALIDATION_ERROR: {exc}"})
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                500, {"error": "INTERNAL_ERROR",
                      "detail": f"{type(exc).__name__}: {exc}"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


class EngineeringHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        # Windows: el cierre del observador/proxy aborta conexiones (10054).
        # Ruido esperado; no polluye el stderr del servicio.
        import socketserver
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
            return
        socketserver.BaseServer.handle_error(self, request, client_address)

    def __init__(self, host: str, port: int,
                 world: EngineeringSessionController) -> None:
        super().__init__((host, port), _EngineeringHTTPHandler)
        self.world = world
        self.stop_event = threading.Event()

    def health_payload(self) -> Dict[str, Any]:
        with self.world._lock:
            drives = [self.world._drive_public(
                d, self.world._events.get(sid))
                for sid, d in self.world._drives.items()]
        return {
            "service": SERVICE_VERSION,
            "engine_version": engine.ENGINE_VERSION_PAPER,
            "pid": os.getpid(),
            "host": self.server_address[0],
            "port": self.server_address[1],
            "sessions_dir": str(self.world.sessions_dir),
            "cadence_ms": self.world.cadence_ms,
            "drives": drives,
            "generated_at_ms": _now_ms(),
        }


def stop_running(port: Optional[int] = None,
                 pid_path: Optional[Path] = None) -> Dict[str, Any]:
    """Detiene el servicio (endpoint /shutdown o pid file)."""
    if port is None and pid_path is not None:
        info = _read_pid_info(Path(pid_path))
        port = info.get("port")
    if not port:
        return {"ok": False, "error": "SERVICE_INFO_UNAVAILABLE"}
    import urllib.error
    import urllib.request
    url = f"http://127.0.0.1:{int(port)}/shutdown"
    try:
        req = urllib.request.Request(url, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=5.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {"ok": False, "error": "SHUTDOWN_REQUEST_FAILED",
                "detail": str(exc)}
    if pid_path is not None:
        try:
            Path(pid_path).unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass
    return {"ok": True, "shutdown": payload}


def _read_pid_info(pid_path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(Path(pid_path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Servicio de sesiones de ingeniería (loopback)")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--sessions-dir", default=None,
                        help="directorio de sesiones (default: "
                             "./paper-lab-sessions); se crea si no existe")
    parser.add_argument("--cadence-ms", type=float,
                        default=DEFAULT_CADENCE_MS,
                        help="cadencia del transporte local (ms por vela)")
    parser.add_argument("--pid-file", default=None)
    parser.add_argument("--stop", action="store_true",
                        help="detiene el servicio estrictamente en --port")
    args = parser.parse_args(argv)

    if args.stop:
        pid_file = Path(args.pid_file) if args.pid_file else PID_DEFAULT
        result = stop_running(args.port, pid_file)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    sessions_dir = Path(args.sessions_dir) if args.sessions_dir \
        else SESSIONS_DEFAULT
    sessions_dir.mkdir(parents=True, exist_ok=True)
    world = EngineeringSessionController(sessions_dir, args.cadence_ms)
    server = EngineeringHTTPServer(args.host, args.port, world)
    pid_file = Path(args.pid_file) if args.pid_file else PID_DEFAULT
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(json.dumps({
        "pid": os.getpid(),
        "port": server.server_address[1],
        "host": server.server_address[0],
        "service": SERVICE_VERSION,
        "started_at_ms": _now_ms(),
    }) + "\n", encoding="utf-8")
    print(json.dumps({
        "service": SERVICE_VERSION,
        "pid": os.getpid(),
        "url": f"http://{server.server_address[0]}:{server.server_address[1]}",
        "sessions_dir": str(sessions_dir),
        "cadence_ms": world.cadence_ms,
    }, ensure_ascii=False), flush=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        while not server.stop_event.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        world.shutdown()
        server.shutdown()
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
