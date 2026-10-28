"""Pruebas del transporte market_stream del servicio de ingeniería.

Contrato ``engineering-session-service/v1`` + transporte
``market_stream`` (SSE del servicio de mercado market-stream/v1, SOLO
loopback, fail-closed):

  A. El adaptador traduce frames SSE del servicio de mercado en eventos
     (hello/snapshot/candle/closed/indicators/context/gap/status) e ignora
     frames desconocidos y malformados sin romper el stream.
  B. Fail-closed: URL no loopback rechazado en construcción.
  C. Creación live: candles=[] obligatorio, contexto requerido, tope de
     nocional, dedupe de create por request_id (idempotencia backend).
  D. Ciclo live completo con productor SSE falso: sin señal → abstención
     explícita → confirmación posterior → entrada (fill único) → gestión
     (marcas) → salida por stop → sesión cerrada, causa SESSION_CLOSED.
  E. Duplicados y reconexión: la misma vela cerrada dos veces (o el mismo
     open_time en un snapshot tras reconexión) NO duplica decisiones, fills
     ni revisiones.
  F. Puerta: silencio del feed y hueco de rejilla → abstención con causa
     explícita (FEED_SILENCE / GRID_GAP), sin decisión inventada.
  G. Registro persistente: el transporte sobrevive al reinicio del servicio
     (drive-registry.json) y el drive se puede reanudar.
  H. Parada con posición abierta: sin cierre inventado (política existente).

El motor ``paper_lab_engine`` es la única autoridad económica; este archivo
no duplica su lógica. Sin Binance, sin feed público, sin órdenes reales.
"""

import json
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from microstructure_probe import engineering_session_service as svc  # noqa: E402

STEP_MS = 60 * 1000  # 1m
T0 = 1_790_000_000_000
ENTRY_PX = 100.0
STOP_PX = round(ENTRY_PX * (1 - 1.5 / 100.0), 4)  # 98.5


# --- servidor SSE falso (productor local determinista) ----------------------

def sse_frame(event: str, payload: Dict[str, Any]) -> bytes:
    body = f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode("utf-8")
    return f"{len(body):x}\r\n".encode("ascii") + body + b"\r\n"


def chunkify(data: bytes) -> bytes:
    return f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n"


class FakeSSEMarketServer:
    """Servidor SSE falso: publica frames de un guion (cola compartida).

    Todas las conexiones leen de la MISMA cola (el adaptador reconecta y
    sigue consumiendo el guion). El sentinel ``CLOSE`` cierra la conexión
    actual (caída simulada → reconexión con backoff).
    """

    CLOSE = b"__CLOSE__"

    def __init__(self) -> None:
        self.frames: "queue.Queue[Any]" = queue.Queue()
        self.connections = 0
        self.stopping = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                outer.connections += 1
                self.send_response(200)
                self.send_header("Content-Type",
                                 "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                try:
                    while True:
                        try:
                            frame = outer.frames.get(timeout=0.05)
                        except queue.Empty:
                            if outer.stopping:
                                break
                            continue
                        if frame is outer.CLOSE:
                            break
                        self.wfile.write(frame)
                        self.wfile.flush()
                except (ConnectionError, BrokenPipeError, OSError):
                    pass

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def send(self, event: str, payload: Dict[str, Any]) -> None:
        self.frames.put(sse_frame(event, payload))

    def send_raw(self, frame: bytes) -> None:
        self.frames.put(chunkify(frame))

    def close_connection(self) -> None:
        self.frames.put(self.CLOSE)

    def stop(self) -> None:
        self.stopping = True
        self.close_connection()
        self._server.shutdown()
        self._server.server_close()


# --- helpers de datos --------------------------------------------------------

def ctx_candle(idx_from_t0_ms: int, o: float, h: float, l: float,
               c: float) -> Dict[str, Any]:
    ot = T0 + idx_from_t0_ms
    return {"open_time_ms": ot, "open": o, "high": h, "low": l, "close": c,
            "close_time_ms": ot + STEP_MS - 1}


# Contexto (ventana conocida antes de T): la última vela cierra en T0-1 y
# fija entry_px=100.0 (close >= entry dispara LONG).
CONTEXT = [
    ctx_candle(-2 * STEP_MS, 99.0, 100.5, 98.5, 99.6),
    ctx_candle(-1 * STEP_MS, 99.6, 100.4, 99.2, 100.0),
]

# Guion live (velas CERRADAS del feed). El motor evalúa la señal en T con
# los cierres ya conocidos: al revelarse Ck, el cierre conocido es el de
# C(k-1). Guion:
#   C1 (close 99.8): abstención (vigilando, sin cierre conocido todavía).
#   C2 (close 99.9): SIN_ENTRADA (close(C1)=99.8 < 100).
#   C3 (close 102.4): ENTRADA_SIMULADA (close(C2)=102 >= 100), fill pendiente.
#   C4 (open 102.5, close 98.2): fill en open(C4) al revelarse C4; marca.
#   C5: revela el cierre de C4 (98.2 <= stop 98.5) → salida por stop.
FEED = [
    {"open_time_ms": T0 + 0 * STEP_MS, "open": 100.2, "high": 100.6,
     "low": 99.4, "close": 99.8},
    {"open_time_ms": T0 + 1 * STEP_MS, "open": 99.9, "high": 102.3,
     "low": 99.5, "close": 102.0},
    {"open_time_ms": T0 + 2 * STEP_MS, "open": 102.1, "high": 102.6,
     "low": 101.8, "close": 102.4},
    {"open_time_ms": T0 + 3 * STEP_MS, "open": 102.5, "high": 103.0,
     "low": 97.8, "close": 98.2},
    {"open_time_ms": T0 + 4 * STEP_MS, "open": 98.0, "high": 98.6,
     "low": 97.5, "close": 97.9},
]


def closed_frame(candle: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    payload = dict(candle)
    payload.update({
        "symbol": "BTCUSDT", "interval": "1m", "closed": True,
        "base_volume": "123.4",
    })
    return "closed", payload


def hello_frame() -> Tuple[str, Dict[str, Any]]:
    return "hello", {
        "contract_version": "market-stream/v1",
        "service": "market-stream-service/v1",
        "identity": {"symbol": "BTCUSDT", "interval": "1m",
                     "venue": "binance", "market_type": "usd_m_futures",
                     "source": "ws_kline"},
    }


def live_config(notional: float = 1000.0) -> Dict[str, Any]:
    return {
        "symbol": "BTCUSDT", "interval": "1m", "direction": "LONG",
        "notional_usdt": notional, "entry_px": ENTRY_PX,
        "stop_px": STOP_PX,
        "stop_distance_pct": (ENTRY_PX - STOP_PX) / ENTRY_PX * 100.0,
        "horizon_ms": 2 * 60 * 60 * 1000,
        "fee_bps": 5.0, "spread_bps": 1.0, "slippage_bps": 2.0,
        "rule_version": "RULE-CAUSAL-V1",
    }


def live_payload(candles: Optional[List[Dict[str, Any]]] = None,
                 context: List[Dict[str, Any]] = None,
                 notional: float = 1000.0,
                 request_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "config": live_config(notional),
        "candles": candles if candles is not None else [],
        "context": CONTEXT if context is None else context,
        "transport": "market_stream",
        "hypothesis_id": "ENG-MKT-TEST-v1", "hypothesis_version": "v1",
        "rule_version": "RULE-CAUSAL-V1",
        "request_id": request_id,
    }


# --- harness HTTP ------------------------------------------------------------

class Harness:
    """Servicio HTTP efímero (puerto 0) + controlador en el proceso test."""

    def __init__(self, sessions_dir: Path, market_url: str,
                 live_silence_ms: float = 120_000.0) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.world = svc.EngineeringSessionController(
            self.sessions_dir, 5.0, market_url=market_url,
            market_bars=50, live_silence_ms=live_silence_ms)
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

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        status, body = self.api("POST", "/sessions", payload)
        assert status == 200, f"create fallo: {status} {body}"
        return body

    def control(self, session_id: str, action: str, **opts: Any) -> Tuple[int, Any]:
        return self.api("POST", f"/sessions/{session_id}/control", {
            "action": action,
            "expected_revision": opts.get("expected_revision"),
            "request_id": opts.get("request_id"),
        })

    def get(self, session_id: str) -> Dict[str, Any]:
        status, body = self.api("GET", f"/sessions/{session_id}")
        assert status == 200, f"get fallo: {status} {body}"
        return body

    def wait_for(self, check, timeout: float = 15.0, interval: float = 0.05):
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            last = check()
            if last:
                return last
            time.sleep(interval)
        raise AssertionError(f"condición no alcanzada en {timeout}s: {last!r}")

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


# --- pruebas del adaptador ---------------------------------------------------

def test_adapter_translates_frames():
    server = FakeSSEMarketServer()
    try:
        q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        stop = threading.Event()
        started = threading.Event()
        adapter = svc.MarketServiceStreamAdapter(
            server.url, "BTCUSDT", "1m", 50, q, stop, started)
        adapter.start()
        server.send(*hello_frame())
        # snapshot: solo velas cerradas pasan al evento.
        server.send("snapshot", {
            "symbol": "BTCUSDT", "interval": "1m",
            "candles": [
                {"open_time_ms": T0 - STEP_MS, "open": 99.6, "high": 100.4,
                 "low": 99.2, "close": 100.0, "closed": True},
                {"open_time_ms": T0, "open": 100.2, "high": 100.6,
                 "low": 99.4, "close": 100.3, "closed": False},
            ],
            "observed": {"start_ms": T0 - STEP_MS, "end_ms": T0},
        })
        server.send(*closed_frame(FEED[0]))
        server.send("candle", {"open_time_ms": T0, "open": 100.2,
                               "closed": False})
        server.send("indicators", {"contract_version": "market-indicators/v1",
                                   "series": {}})
        server.send("context", {"contract_version": "market-btc-context/v1"})
        server.send("gap", {"reason": "GAP", "start_ms": T0, "end_ms": T0})
        server.send("status", {"connection": "LIVE"})
        server.send("desconocido", {"x": 1})
        server.send_raw(b"event: roto\ndata: {no-json\n\n")

        events: Dict[str, Dict[str, Any]] = {}
        needed = {"HELLO", "SNAPSHOT", "MARKET_CLOSED", "PROVISIONAL",
                  "EVIDENCE:indicators", "EVIDENCE:context_btc", "DATA_GAP",
                  "STATUS"}
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not needed <= set(events):
            try:
                ev = q.get(timeout=0.2)
            except queue.Empty:
                continue
            key = ev["type"] if ev["type"] != "EVIDENCE" \
                else f"EVIDENCE:{ev['evidence_kind']}"
            events.setdefault(key, ev)
        assert {"HELLO", "SNAPSHOT", "MARKET_CLOSED", "PROVISIONAL",
                "EVIDENCE:indicators", "EVIDENCE:context_btc", "DATA_GAP",
                "STATUS"} <= set(events), f"eventos: {sorted(events)}"
        assert events["HELLO"]["identity"]["symbol"] == "BTCUSDT"
        # Snapshot: SOLO la vela cerrada; la provisional excluida.
        snap = events["SNAPSHOT"]["candles"]
        assert len(snap) == 1 and snap[0]["open_time_ms"] == T0 - STEP_MS
        assert events["MARKET_CLOSED"]["candle"]["close"] == 99.8
        assert "received_at_ms" in events["MARKET_CLOSED"]
        # Espera activa a que el adaptador procese los frames finales
        # (desconocido + malformado) antes de contar sus métricas.
        end = time.monotonic() + 3.0
        while time.monotonic() < end and (
                adapter.stats["unknown_frames"] < 1
                or adapter.stats["bad_frames"] < 1):
            time.sleep(0.05)
        # El frame malformado y el desconocido no rompieron el stream:
        assert adapter.stats["bad_frames"] >= 1
        assert adapter.stats["unknown_frames"] >= 1
        stop.set()
        server.close_connection()
    finally:
        server.stop()


def test_adapter_rejects_non_loopback():
    for bad in ("http://example.com/stream", "https://127.0.0.1:8791",
                "http://binance.com:8791", "ftp://127.0.0.1:8791",
                "http://0.0.0.0:8791", ""):
        try:
            svc.MarketServiceStreamAdapter(
                bad, "BTCUSDT", "1m", 50, queue.Queue(),
                threading.Event(), threading.Event())
        except ValueError as exc:
            assert "MARKET_URL_NOT_LOOPBACK" in str(exc), bad
        else:
            raise AssertionError(f"URL no loopback aceptado: {bad!r}")


# --- pruebas de creación -----------------------------------------------------

def test_create_market_stream_validation_and_dedupe():
    tmp = Path(tempfile.mkdtemp(prefix="eng-mkt-create-"))
    server = FakeSSEMarketServer()
    harness = Harness(tmp, server.url)
    try:
        # candles=[] obligatorio en live.
        status, body = harness.api("POST", "/sessions", live_payload(
            candles=[{"open_time_ms": T0, "open": 1, "high": 1, "low": 1,
                      "close": 1, "close_time_ms": T0 + STEP_MS - 1}]))
        assert status == 400 and "LIVE_CANDLES_FORBIDDEN" in str(body), body
        # contexto requerido.
        status, body = harness.api("POST", "/sessions", live_payload(
            context=[]))
        assert status == 400 and "LIVE_CONTEXT_REQUIRED" in str(body), body
        # tope de nocional.
        status, body = harness.api("POST", "/sessions", live_payload(
            notional=5000.0))
        assert status == 400 and "NOTIONAL_CAP" in str(body), body
        # transporte desconocido.
        bad = live_payload()
        bad["transport"] = "otro"
        status, body = harness.api("POST", "/sessions", bad)
        assert status == 400 and "transporte no permitido" in str(body), body

        # Creación válida + dedupe por request_id (misma sesión).
        first = harness.create(live_payload(request_id="req-live-1"))
        sid = first["session"]["session_id"]
        assert first["transport"] == "market_stream"
        assert first["session"]["status"] == "sin_iniciar"
        assert first["session"]["candles"] == []
        assert first["session"]["clock_ms"] == T0 - 1  # cierre de contexto
        again = harness.create(live_payload(request_id="req-live-1"))
        assert again["session"]["session_id"] == sid
        # Registro persistente del transporte live.
        registry = json.loads(
            (tmp / "drive-registry.json").read_text(encoding="utf-8"))
        assert sid in registry["sessions"]
        assert registry["sessions"][sid]["transport"] == "market_stream"
        assert registry["sessions"][sid]["market_url"] == server.url
    finally:
        harness.close()
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)


# --- ciclo live completo -----------------------------------------------------

def push_hello_and_snapshot(server: FakeSSEMarketServer) -> None:
    server.send(*hello_frame())
    server.send("snapshot", {
        "symbol": "BTCUSDT", "interval": "1m",
        "candles": [dict(c, closed=True) for c in CONTEXT]
                   + [{"open_time_ms": T0, "open": 100.2, "high": 100.6,
                       "low": 99.4, "close": 100.3, "closed": False}],
    })


def test_drive_live_full_cycle_entry_and_stop_exit():
    tmp = Path(tempfile.mkdtemp(prefix="eng-mkt-cycle-"))
    server = FakeSSEMarketServer()
    harness = Harness(tmp, server.url)
    try:
        created = harness.create(live_payload(request_id="req-cycle-1"))
        sid = created["session"]["session_id"]
        status, _ = harness.control(sid, "start", request_id="start-cycle-1")
        assert status == 200
        body = harness.get(sid)
        assert body["drive"]["runner"] == "market_stream"

        push_hello_and_snapshot(server)

        def wait_decision(decision: str) -> Dict[str, Any]:
            return harness.wait_for(lambda: (lambda b: b if
                                             b["session"]["config"]
                                             .get("decision") == decision
                                             else None)(harness.get(sid)))

        # 1) vela cerrada sin señal: abstención temporal explícita
        #    (vigilando: el close de C1 aún no es conocido en T).
        server.send(*closed_frame(FEED[0]))
        wait_decision("SIN_ENTRADA")
        # 2) C2 cierra: el close de C1 (99.8) ya conocido en T y es < entry.
        server.send(*closed_frame(FEED[1]))
        harness.wait_for(lambda: (lambda b: b if
                                  len(b["session"]["candles"]) == 2
                                  else None)(harness.get(sid)))
        assert harness.get(sid)["session"]["config"]["decision"] \
            == "SIN_ENTRADA"
        # 3) C3 cierra: close(C2)=102 >= entry → ENTRADA_SIMULADA, fill
        #    pendiente (ningún open posterior conocido en T).
        server.send(*closed_frame(FEED[2]))
        wait_decision("ENTRADA_SIMULADA")
        # 4) C4 cierra: el paso pendiente hace fill en open(C4)=102.5 (único).
        server.send(*closed_frame(FEED[3]))
        body = harness.wait_for(lambda: (lambda b: b["session"] if
                                         b["session"]["position"]["open"]
                                         is True else None)(
            harness.get(sid)))
        assert body["position"]["entry_px"] == 102.5
        entry_events = [e for e in body["events"]
                        if e.get("kind") == "entry"]
        assert len(entry_events) == 1, entry_events
        assert "fill_basis=model_approximation" in (entry_events[0]["detail"]
                                                    or "")
        # 5) C5 cierra: close(C4)=98.2 <= stop → salida por stop.
        server.send(*closed_frame(FEED[4]))
        body = harness.wait_for(lambda: (lambda b: b["session"] if
                                         b["session"]["status"] == "cerrada"
                                         else None)(harness.get(sid)))
        result = body["result"]
        assert result["exit_executed"] is True
        assert result["open_at_end"] is False
        exit_events = [e for e in body["events"]
                       if e.get("kind") in ("exit", "stop")]
        assert exit_events, "sin evento de salida"
        assert any("fill_basis=model_approximation" in (e.get("detail") or "")
                   for e in exit_events)
        # 6) evidencia del adaptador en la decisión: identidad, disparo y 3
        #    relojes.
        ev = body["config"]["decision_evidence"]
        assert ev["adapter"]["runner"] == "market_stream"
        assert ev["adapter"]["trigger"]["frame"] == "closed"
        clocks = ev["adapter"]["clocks"]
        assert clocks["trigger_open_ms"] is not None
        assert clocks["trigger_received_at_ms"] is not None
        assert clocks["evaluation_wall_ms"] >= \
            clocks["trigger_received_at_ms"]
        assert body["config_hash"] == created["session"]["config_hash"]
        # 7) drive terminado por cierre de sesión (no por error).
        drive = harness.wait_for(
            lambda: (lambda d: d if d.get("cause") == "SESSION_CLOSED"
                     else None)(harness.get(sid)["drive"]))
        assert drive["state"] == "stopped"
        assert drive["last_trigger"]["frame"] == "closed"
        stats = drive["stats"]
        # hello + snapshot + 5 velas cerradas (frames traducidos).
        assert stats["frames"] >= 7
        assert stats["bad_frames"] == 0
    finally:
        harness.close()
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)


def test_drive_live_duplicates_and_reconnect_do_not_repeat_effects():
    tmp = Path(tempfile.mkdtemp(prefix="eng-mkt-dedupe-"))
    server = FakeSSEMarketServer()
    harness = Harness(tmp, server.url)
    try:
        created = harness.create(live_payload(request_id="req-dedupe-1"))
        sid = created["session"]["session_id"]
        harness.control(sid, "start", request_id="start-dedupe-1")
        push_hello_and_snapshot(server)
        # C1 dos veces: la segunda es duplicado exacto.
        server.send(*closed_frame(FEED[0]))
        harness.wait_for(lambda: (
            harness.get(sid)["session"]["revision"] == 4))
        server.send(*closed_frame(FEED[0]))
        time.sleep(0.4)
        body = harness.get(sid)
        assert body["session"]["revision"] == 4, body["session"]["revision"]
        assert body["session"]["candles"] == [] or \
            len(body["session"]["candles"]) == 1
        drive = body["drive"]
        assert drive["stats"]["frames"] >= 3

        # Reconexión: caída + hello + snapshot que re-includes C1 (cerrada)
        # y trae C2 nueva. Solo C2 avanza la sesión.
        server.close_connection()
        server.send(*hello_frame())
        server.send("snapshot", {
            "symbol": "BTCUSDT", "interval": "1m",
            "candles": [dict(c, closed=True) for c in CONTEXT]
                       + [dict(FEED[0], closed=True),
                          dict(FEED[1], closed=True)],
        })
        harness.wait_for(lambda: (
            len(harness.get(sid)["session"]["candles"]) == 2))
        time.sleep(0.3)
        body = harness.get(sid)
        # C1 (rev 4) + C2 (append+reveal+evaluate doble bump = +4): sin
        # duplicados (el snapshot re-incluía C1 y el contexto).
        assert body["session"]["revision"] == 8, body["session"]["revision"]
        assert body["session"]["status"] == "sin_iniciar"
        assert body["session"]["config"]["decision"] == "SIN_ENTRADA"
        drive = body["drive"]
        assert drive["watermark"] == FEED[1]["open_time_ms"]
    finally:
        harness.close()
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)


def test_gate_feed_silence_and_grid_gap_abstain():
    tmp = Path(tempfile.mkdtemp(prefix="eng-mkt-gate-"))
    server = FakeSSEMarketServer()
    harness = Harness(tmp, server.url, live_silence_ms=200.0)
    try:
        created = harness.create(live_payload(request_id="req-gate-1"))
        sid = created["session"]["session_id"]
        harness.control(sid, "start", request_id="start-gate-1")
        push_hello_and_snapshot(server)

        # --- silencio del feed: sin frames ~1s > live_silence_ms=200ms; al
        # llegar la vela siguiente la puerta debe abstenerse con causa.
        server.send(*closed_frame(FEED[0]))
        harness.wait_for(lambda: (
            harness.get(sid)["session"]["revision"] == 4))
        time.sleep(1.0)  # silencio real del feed (200ms de tope)
        server.send(*closed_frame(FEED[1]))
        body = harness.wait_for(lambda: (lambda d: d if
                                         (d.get("last_gate") or {}).get("cause")
                                         == "FEED_SILENCE"
                                         else None)(harness.get(sid)["drive"]))
        assert body["last_gate"]["ok"] is False
        assert body["last_gate"]["cause"] == "FEED_SILENCE"
        assert body["last_gate"]["silence_ms"] > 200
        # Sin decisión nueva durante el silencio: la sesión conserva la
        # abstención previa (SIN_ENTRADA de C1) sin reevaluar.
        body = harness.get(sid)
        assert body["session"]["config"]["decision"] == "SIN_ENTRADA"
        assert body["session"]["status"] == "sin_iniciar"

        # --- hueco de rejilla: C4 (salta C3) produce discontinuidad.
        server.send(*closed_frame(FEED[3]))
        body = harness.wait_for(lambda: (lambda d: d if
                                         (d.get("last_gate") or {}).get("cause")
                                         == "GRID_GAP"
                                         else None)(harness.get(sid)["drive"]))
        assert body["last_gate"]["grid_gap"], body["last_gate"]
        # El hueco quedó registrado y la decisión sigue sin reevaluar.
        body = harness.get(sid)
        assert body["session"]["config"]["decision"] == "SIN_ENTRADA"
    finally:
        harness.close()
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)


def test_registry_survives_service_restart_and_drive_resumes():
    tmp = Path(tempfile.mkdtemp(prefix="eng-mkt-registry-"))
    server = FakeSSEMarketServer()
    harness = Harness(tmp, server.url)
    try:
        created = harness.create(live_payload(request_id="req-reg-1"))
        sid = created["session"]["session_id"]
        harness.control(sid, "start", request_id="start-reg-1")
        push_hello_and_snapshot(server)
        server.send(*closed_frame(FEED[0]))
        harness.wait_for(lambda: (
            harness.get(sid)["session"]["revision"] == 4))
        harness.close()  # "reinicio" del servicio (mismo sessions_dir)

        # Nuevo servicio: sin drives en memoria; el registro indica live.
        harness2 = Harness(tmp, server.url)
        try:
            body = harness2.get(sid)
            assert body["drive"]["state"] == "idle"
            status, _ = harness2.control(sid, "start",
                                         request_id="start-reg-2")
            assert status == 200
            drive = harness2.get(sid)["drive"]
            assert drive["runner"] == "market_stream"
            # La sesión continua desde el estado persistido: C2 confirma.
            server.send(*closed_frame(FEED[1]))
            harness2.wait_for(lambda: (
                len(harness2.get(sid)["session"]["candles"]) == 2))
            body = harness2.get(sid)
            assert body["session"]["revision"] == 8
            assert body["session"]["config"]["decision"] == "SIN_ENTRADA"
        finally:
            harness2.close()
    finally:
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)


def test_stop_with_open_position_keeps_policy():
    tmp = Path(tempfile.mkdtemp(prefix="eng-mkt-stop-"))
    server = FakeSSEMarketServer()
    harness = Harness(tmp, server.url)
    try:
        created = harness.create(live_payload(request_id="req-stop-1"))
        sid = created["session"]["session_id"]
        harness.control(sid, "start", request_id="start-stop-1")
        push_hello_and_snapshot(server)
        # C1..C4: abstención → decisión → fill (posición abierta).
        for candle in FEED[:4]:
            server.send(*closed_frame(candle))
        harness.wait_for(lambda: (lambda b: b["session"] if
                                  b["session"]["position"]["open"] is True
                                  else None)(harness.get(sid)))
        # Parada del operador con posición abierta: SIN cierre inventado.
        harness.control(sid, "stop", request_id="stop-drive-1")
        drive = harness.wait_for(lambda: (lambda d: d if d.get("cause")
                                          == "OPERATOR_STOP" else None)(
            harness.get(sid)["drive"]))
        assert drive["state"] == "stopped"
        body = harness.get(sid)
        assert body["session"]["status"] == "abierta"
        assert body["session"]["position"]["open"] is True
        assert body["session"]["result"] is None
        # stop_session congela la sesión (detenida) sin inventar salida.
        harness.control(sid, "stop_session", request_id="stop-sess-1")
        body = harness.wait_for(lambda: (lambda b: b if
                                         b["session"]["status"] == "detenida"
                                         else None)(harness.get(sid)))
        assert body["session"]["position"]["open"] is True
        assert body["session"]["result"] is None
    finally:
        harness.close()
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"--- {name}")
            try:
                fn()
                print("OK")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                import traceback
                traceback.print_exc()
                print(f"FALLO: {exc}")
    print("RESUMEN:", "TODO OK" if failures == 0 else f"{failures} fallos")
    raise SystemExit(1 if failures else 0)
