"""Pruebas del servicio de sesión de ingeniería autónoma (backend).

Contrato ``engineering-session-service/v1`` por HTTP real (loopback efímero):
  A. Abstención temporal (SIN_ENTRADA) → evento confirmatorio posterior →
     entrada simulada → gestión → cierre, SIN intervención del navegador
     (un solo POST start; el avance ocurre por eventos del transporte local).
  B. Fin del transporte local (EOF) detiene la conducción con causa visible
     END_OF_TRANSPORT y SIN cierre inventado (abstención queda temporal).
  C. DESCARTADO terminal cierra la sesión y no reabre ante eventos nuevos.
  D. Conflictos de revisión/conducción (409) con guardarrobas optimistas.
  E. Persistencia: reinicio del servicio conserva posición abierta y sigue
     manejable (no congelada).
  F. Parada con posición abierta no inventa cierre (detenida).

El motor ``paper_lab_engine`` es la única autoridad económica; este archivo
no duplica su lógica (cubre test_paper_lab_engine.py) sino la del servicio.
Sin Binance, sin feed vivo, sin órdenes reales, sin capital real.
"""

import json
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from microstructure_probe import engineering_session_service as svc  # noqa: E402

INTERVAL_MS = 15 * 60 * 1000
T0 = 1_790_000_000_000
ENTRY_PX = 105.0
STOP_PX = 95.0


# --- helpers ----------------------------------------------------------------

def candle(idx: int, o: float, h: float, l: float, c: float) -> Dict[str, Any]:
    ot = T0 + idx * INTERVAL_MS
    return {
        "open_time_ms": ot, "open": o, "high": h, "low": l, "close": c,
        "close_time_ms": ot + INTERVAL_MS - 1,
    }


def config_payload(entry_px: float = ENTRY_PX,
                   stop_px: float = STOP_PX,
                   horizon_ms: int = 2 * INTERVAL_MS) -> Dict[str, Any]:
    return {
        "symbol": "BTCUSDT", "interval": "15m", "direction": "LONG",
        "notional_usdt": 1000.0, "entry_px": entry_px, "stop_px": stop_px,
        "stop_distance_pct": (entry_px - stop_px) / entry_px * 100.0,
        "horizon_ms": horizon_ms,
        "fee_bps": 5.0, "spread_bps": 1.0, "slippage_bps": 2.0,
        "rule_version": "RULE-CAUSAL-V1",
    }


def create_payload(candles: List[Dict[str, Any]],
                   entry_px: float = ENTRY_PX,
                   stop_px: float = STOP_PX,
                   horizon_ms: int = 2 * INTERVAL_MS) -> Dict[str, Any]:
    return {
        "config": config_payload(entry_px, stop_px, horizon_ms),
        "candles": candles, "context": [],
        "hypothesis_id": "ENG-SVC-TEST-v1", "hypothesis_version": "v1",
        "rule_version": "RULE-CAUSAL-V1", "request_id": "svc-test-create",
    }


# Prefijo con abstención temporal inicial (close de c0 < entry) seguida de
# confirmación (close de c1 >= entry, low sin vulnerar stop) y velas
# suficientes para que el motor cierre por horizonte (2 intervalos).
CONFIRM_CANDLES = [
    candle(0, 100.0, 104.0, 99.0, 100.0),   # sin señal en close(c0)
    candle(1, 101.0, 111.0, 100.5, 110.0),  # señal confirmada en close(c1)
    candle(2, 112.0, 113.0, 108.0, 112.0),
    candle(3, 113.0, 114.0, 109.0, 113.0),
    candle(4, 114.0, 115.0, 110.0, 114.0),  # horizonte alcanzado
    candle(5, 115.0, 116.0, 111.0, 115.5),  # vela tras horizonte: salida
]


class Harness:
    """Servicio HTTP efímero (puerto 0) + controlador en el proceso test."""

    def __init__(self, sessions_dir: Path, cadence_ms: float = 5.0) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.world = svc.EngineeringSessionController(
            self.sessions_dir, cadence_ms)
        self.server = svc.EngineeringHTTPServer("127.0.0.1", 0, self.world)
        self._thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def api(self, method: str, path: str,
            payload: Optional[Dict[str, Any]] = None,
            timeout: float = 15.0) -> Tuple[int, Any]:
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
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = body
            return exc.code, parsed

    def create_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        status, body = self.api("POST", "/sessions", payload)
        assert status == 200, f"create fallo: {status} {body}"
        return body["session"]

    def control(self, session_id: str, action: str, **opts: Any) -> Tuple[int, Any]:
        return self.api("POST", f"/sessions/{session_id}/control", {
            "action": action,
            "expected_revision": opts.get("expected_revision"),
            "request_id": opts.get("request_id"),
        })

    def wait_for(self, check, timeout: float = 15.0, interval: float = 0.05):
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            last = check()
            if last:
                return last
            time.sleep(interval)
        raise AssertionError(f"condición no alcanzada en {timeout}s: {last!r}")

    def wait_status(self, session_id: str, statuses):
        def check():
            _, body = self.api("GET", f"/sessions/{session_id}")
            if not isinstance(body, dict) or "session" not in body:
                return None
            if body["session"]["status"] in statuses:
                return body
            return None
        return self.wait_for(check)

    def close(self) -> None:
        self.world.shutdown()
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5.0)
        shutil.rmtree(self.sessions_dir, ignore_errors=True)


# --- PRUEBAS ----------------------------------------------------------------

def test_health_y_contrato(tmp_path):
    h = Harness(tmp_path, cadence_ms=50.0)
    try:
        status, health = h.api("GET", "/health")
        assert status == 200
        assert health["service"] == "engineering-session-service/v1"
        assert health["pid"] == os.getpid()
        assert health["cadence_ms"] == 50.0
        assert str(tmp_path) in health["sessions_dir"].replace("\\", "/") \
            or Path(health["sessions_dir"]) == tmp_path
        status, sessions = h.api("GET", "/sessions")
        assert status == 200
        assert sessions["sessions"] == []
    finally:
        h.close()


def test_abstencion_temporal_luego_confirmacion_entrada_autonoma(tmp_path):
    """A: SIN_ENTRADA temporal → evento confirmatorio → entrada → cierre,
    con UN SOLO POST start y ningún avance del navegador."""
    h = Harness(tmp_path, cadence_ms=5.0)
    try:
        session = h.create_session(create_payload(CONFIRM_CANDLES))
        sid = session["session_id"]
        assert session["status"] == "sin_iniciar"
        assert session["config"]["decision"] is None

        # Un solo POST start; después el navegador solo OBSERVA (GET).
        status, body = h.control(sid, "start", request_id="drive-1")
        assert status == 200, body
        assert body["drive"]["state"] == "running"
        first_revision = body["session"]["revision"]

        # Sin pulsar nada: la abstención temporal (close c0 < entry) es
        # seguida de la confirmación con el evento siguiente (close c1).
        closed = h.wait_status(sid, {"abierta", "cerrada"})
        assert closed["session"]["config"]["decision"] == "ENTRADA_SIMULADA"
        assert closed["session"]["revision"] > first_revision

        # gestión y cierre autónomos por los eventos del transporte;
        # el horizonte cierra la posición sin intervención.
        final = h.wait_status(sid, {"cerrada"})
        fin = final["session"]
        kinds = [ev["kind"] for ev in fin["events"]]
        assert kinds.count("entry") == 1, fin["events"]
        assert kinds.count("exit") == 1, fin["events"]
        assert fin["result"] is not None
        assert fin["result"]["exit_executed"] is True
        assert fin["position"]["open"] is False
        # La conducción termina por cierre del motor (no por el operador).
        assert final["drive"]["state"] == "stopped"
        assert final["drive"]["cause"] == "SESSION_CLOSED"
        # Revisión monotónica: cerrada no retrocede respecto del cierre previo.
        assert fin["revision"] >= closed["session"]["revision"]
    finally:
        h.close()


def test_fin_de_transporte_sin_cierre_inventado(tmp_path):
    """B: EOF → causa END_OF_TRANSPORT, abstención queda temporal."""
    h = Harness(tmp_path, cadence_ms=5.0)
    try:
        # Solo c0 y c1 con close < entry: la sesión se abstiene siempre.
        session = h.create_session(create_payload(
            [candle(0, 100.0, 104.0, 99.0, 100.0),
             candle(1, 100.5, 104.5, 99.5, 100.2)]))
        sid = session["session_id"]
        status, body = h.control(sid, "start")
        assert status == 200
        final = h.wait_for(lambda: (
            None if h.api("GET", f"/sessions/{sid}")[1]["drive"]["state"]
            != "stopped"
            else h.api("GET", f"/sessions/{sid}")[1]))
        assert final["drive"]["cause"] == "END_OF_TRANSPORT"
        # Sin cierre inventado: sigue sin iniciar, sin posición, sin salida.
        assert final["session"]["status"] == "sin_iniciar"
        assert final["session"]["position"]["open"] is False
        assert final["session"]["result"] is None
        kinds = [ev["kind"] for ev in final["session"]["events"]]
        assert kinds.count("entry") == 0
        assert kinds.count("exit") == 0
    finally:
        h.close()


def test_descartado_terminal_cierra_y_no_reabre(tmp_path):
    """C: DESCARTADO (stop vulnerado en T) → cerrada terminal."""
    h = Harness(tmp_path, cadence_ms=5.0)
    try:
        session = h.create_session(create_payload(
            # La vela c0 vulnera el stop 95 con su low (conocido al cierre).
            [candle(0, 100.0, 104.0, 90.0, 100.0),
             candle(1, 101.0, 111.0, 100.5, 110.0)]))
        sid = session["session_id"]
        status, _ = h.control(sid, "start")
        assert status == 200
        final = h.wait_status(sid, {"cerrada"})
        fin = final["session"]
        assert fin["config"]["decision"] == "DESCARTADO"
        assert fin["position"]["open"] is False
        kinds = [ev["kind"] for ev in fin["events"]]
        assert kinds.count("entry") == 0
        assert kinds.count("exit") == 0
        assert final["drive"]["cause"] == "SESSION_CLOSED"
        stopped_revision = fin["revision"]

        # Terminal: eventos posteriores no reabren ni reevaluan (sin cambios).
        time.sleep(0.3)
        _, after = h.api("GET", f"/sessions/{sid}")
        assert after["session"]["revision"] == stopped_revision
        assert after["session"]["status"] == "cerrada"
        # Un paso manual no muta una sesión cerrada (sin reset de decisión).
        _, again = h.control(sid, "step", expected_revision=stopped_revision)
        assert again["session"]["revision"] == stopped_revision
        assert again["session"]["status"] == "cerrada"
    finally:
        h.close()


def test_conflictos_revision_y_conduccion(tmp_path):
    """D: 409 REVISION_CONFLICT / DRIVE_ACTIVE; 400 acción inválida."""
    # Cadencia lenta: la conducción NO debe agotar la ventana durante la prueba.
    h = Harness(tmp_path, cadence_ms=3000.0)
    try:
        session = h.create_session(create_payload(CONFIRM_CANDLES))
        sid = session["session_id"]

        # Revisión esperada incorrecta → 409, sin sesión creada al vuelo.
        status, body = h.control(sid, "start", expected_revision=999)
        assert status == 409
        assert body["error"] == "REVISION_CONFLICT"

        # Start correcto → drive en ejecución.
        status, _ = h.control(sid, "start", expected_revision=session["revision"])
        assert status == 200

        # Acción manual mientras la conducción está activa → 409.
        status, body = h.control(sid, "step")
        assert status == 409
        assert body["error"] == "DRIVE_ACTIVE"
        status, body = h.control(sid, "exit")
        assert status == 409
        assert body["error"] == "DRIVE_ACTIVE"

        # Detener y luego conflicto de revisión en acción manual.
        status, _ = h.control(sid, "stop")
        assert status == 200
        ended = h.wait_for(lambda: (
            None if h.api("GET", f"/sessions/{sid}")[1]["drive"]["state"]
            != "stopped" else True),
            timeout=10.0)
        _, cur = h.api("GET", f"/sessions/{sid}")
        status, body = h.control(sid, "step",
                                 expected_revision=cur["session"]["revision"] + 5)
        assert status == 409
        assert body["error"] == "REVISION_CONFLICT"

        # Acción no permitida → 400; sesión desconocida → 404; id inválido → 400/404.
        status, body = h.control(sid, "explode")
        assert status == 400
        assert "VALIDATION_ERROR" in body["error"]
        status, body = h.control("sess-no-existe", "step")
        assert status == 404
        assert body["error"] == "SESSION_NOT_FOUND"
        status, body = h.api("GET", "/sessions/sess-no-existe")
        assert status == 404
        status, body = h.api("POST", "/sessions/%2E%2E%2Fevil/control",
                             {"action": "step"})
        assert status in (400, 404)
        assert body.get("error") not in (None, 200)
    finally:
        h.close()


def test_persistencia_reinicio_mantiene_posicion_no_congelada(tmp_path):
    """E: reinicio del servicio conserva posición abierta y manejable."""
    h = Harness(tmp_path, cadence_ms=5.0)
    try:
        session = h.create_session(create_payload(
            [candle(0, 99.5, 101.0, 99.0, 100.0),   # señal al cierre de c0
             candle(1, 100.5, 112.0, 100.0, 110.0),
             candle(2, 111.0, 113.0, 108.0, 112.0),
             candle(3, 112.5, 116.0, 110.0, 113.0)],
            entry_px=100.0, stop_px=95.0,
            horizon_ms=12 * INTERVAL_MS))
        sid = session["session_id"]
        # evaluate usa state.clock_ms; dar un paso manual para revelar el
        # close de c0 y luego evaluar en ese T (candidato confirmado, el
        # open de c1 aún sin revelar → entrada pendiente de fill).
        _, stepped = h.control(sid, "step", expected_revision=session["revision"])
        assert stepped["session"]["clock_ms"] >= T0 + INTERVAL_MS - 1
        _, evaluated = h.control(sid, "evaluate",
                                 expected_revision=stepped["session"]["revision"],
                                 request_id="ev-1")
        assert evaluated["session"]["status"] == "en_espera"
        assert evaluated["session"]["config"]["decision"] == "ENTRADA_SIMULADA"

        # Fill por evento del transporte manual: entrada ejecutada única.
        _, entered = h.control(sid, "step",
                               expected_revision=evaluated["session"]["revision"],
                               request_id="fill-1")
        assert entered["session"]["status"] == "abierta"
        pos = entered["session"]["position"]
        assert pos["open"] is True
        assert pos["entry_px"] is not None
        kinds = [ev["kind"] for ev in entered["session"]["events"]]
        assert kinds.count("entry") == 1
        persisted_revision = entered["session"]["revision"]

        # "Cierre de pestaña": dejar de hablar con el servicio. El estado
        # queda PERSISTIDO (dinero y posición en el directorio de sesiones),
        # no solo en memoria como lo estaría en un frontend congelado.
    finally:
        pass

    # El servicio se reinicia (nuevo controlador, MISMO directorio).
    h2 = Harness(tmp_path, cadence_ms=5.0)
    try:
        status, recovered = h2.api("GET", f"/sessions/{sid}")
        assert status == 200
        assert recovered["session"]["status"] == "abierta"
        assert recovered["session"]["position"]["open"] is True
        assert recovered["session"]["revision"] == persisted_revision
        # La posición NO está congelada: un paso la sigue manejando
        # (nueva marca, revisión incremental, sin duplicar la entrada).
        _, stepped = h2.control(sid, "step",
                                expected_revision=recovered["session"]["revision"],
                                request_id="post-restart-step-1")
        assert stepped["session"]["status"] == "abierta"
        assert stepped["session"]["revision"] > recovered["session"]["revision"]
        kinds = [ev["kind"] for ev in stepped["session"]["events"]]
        assert kinds.count("entry") == 1

        # Parada con posición abierta: detenida SIN cierre inventado.
        _, stopped = h2.control(sid, "stop",
                                expected_revision=stepped["session"]["revision"])
        assert stopped["drive"]["state"] in ("idle", "stopped")
        _, frozen = h2.control(sid, "stop_session",
                               expected_revision=stopped["session"]["revision"],
                               request_id="halt-1")
        assert frozen["session"]["status"] == "detenida"
        assert frozen["session"]["position"]["open"] is True
        assert frozen["session"]["result"] is None
        kinds = [ev["kind"] for ev in frozen["session"]["events"]]
        assert kinds.count("exit") == 0
        # Una sesión detenida no admite conducción.
        status, body = h2.control(sid, "start")
        assert status == 409
        assert body["error"] == "SESSION_NOT_DRIVEABLE"
    finally:
        h2.close()


def test_restart_idempotente_y_activo_conflicto(tmp_path):
    """start repetido no crea segundo reproductor (idempotencia)."""
    # Cadencia lenta para que la parada del operador llegue en marcha.
    h = Harness(tmp_path, cadence_ms=3000.0)
    try:
        session = h.create_session(create_payload(CONFIRM_CANDLES))
        sid = session["session_id"]
        status, first = h.control(sid, "start", request_id="start-1")
        assert status == 200
        started_at = first["drive"]["started_at_ms"]
        status, again = h.control(sid, "start", request_id="start-2")
        assert status == 200
        assert again["drive"]["state"] == "running"
        assert again["drive"]["started_at_ms"] == started_at
        status, stop_body = h.control(sid, "stop")
        assert status == 200, stop_body
        ended = h.wait_for(lambda: (
            None if h.api("GET", f"/sessions/{sid}")[1]["drive"]["state"]
            != "stopped" else h.api("GET", f"/sessions/{sid}")[1]))
        assert ended["drive"]["cause"] == "OPERATOR_STOP"
    finally:
        h.close()


def test_shutdown_endpoint(tmp_path):
    h = Harness(tmp_path, cadence_ms=5.0)
    try:
        status, body = h.api("POST", "/shutdown", {})
        assert status == 200
        assert body["ok"] is True
        assert body["pid"] == os.getpid()
    finally:
        h.close()


def test_default_sessions_dir_dedicado_sin_colision():
    """El default de sesiones es un directorio dedicado del servicio de
    ingeniería: NO colisiona con el raíz del controlador anterior
    (`paper-lab-sessions/`); las sesiones existentes del controlador
    anterior se conservan sin migración ni borrado."""
    from microstructure_probe import engineering_session_service as svc

    expected = Path(__file__).resolve(
        ).parents[1] / "data" / "engineering-session" / "sessions"
    assert Path(svc.SESSIONS_DEFAULT).resolve() == expected.resolve()
    # Guarda: el default no es el raíz canónico del controlador anterior.
    assert Path(svc.SESSIONS_DEFAULT).name != "paper-lab-sessions"
