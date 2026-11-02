"""Arranque real del servicio con referencia temporal local (cero Binance).

Valida el cableado de ``ClockSynchronizer`` al controlador (referencia
pública validada) frente a reloj controlado por el transporte de prueba, en
los tres puntos de entrada: contexto inicial, snapshot y eventos ``closed``.

Cada prueba construye el servicio real (``EngineeringSessionController`` +
``EngineeringHTTPServer``) con un ``ClockSynchronizer`` alimentado por un
proveedor de tiempo local, y lo ejerce por su API HTTP real.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import asyncio
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import queue as _queue_module
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.clock import ClockSynchronizer  # noqa: E402
from microstructure_probe.engineering_session_service import (  # noqa: E402
    EngineeringHTTPServer,
    EngineeringSessionController,
)

STEP_MS = 60 * 1000  # 1m
T0 = 1_790_000_000_000  # instante base (pasado respecto al reloj real)


def sse_frame(event: str, payload: Dict[str, Any]) -> bytes:
    body = f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode("utf-8")
    return f"{len(body):x}\r\n".encode("ascii") + body + b"\r\n"


class _LocalTimeProvider:
    """Proveedor de tiempo local controlado (sin Binance, sin red pública)."""

    def __init__(self, server_ms: int, wall_ms: int) -> None:
        self.server_ms = server_ms
        self.wall_ms = wall_ms

    def fetch_server_time(self) -> int:
        return int(self.server_ms)

    def wall_clock_ms(self) -> float:
        return float(self.wall_ms)

    def set(self, server_ms: int, wall_ms: int) -> None:
        self.server_ms = server_ms
        self.wall_ms = wall_ms


def ctx_candle(idx_from_t0_ms: int, o: float, h: float, l: float,
               c: float) -> Dict[str, Any]:
    ot = T0 + idx_from_t0_ms
    return {"open_time_ms": ot, "open": o, "high": h, "low": l, "close": c,
            "close_time_ms": ot + STEP_MS - 1}


# Contexto reciente cerrado: última vela cierra en T0 - 1.
CONTEXT = [
    ctx_candle(-2 * STEP_MS, 99.0, 100.5, 98.5, 99.6),
    ctx_candle(-1 * STEP_MS, 99.6, 100.4, 99.2, 100.0),
]

# Cierre futuro del feed (open T0, cierre en T0 + STEP - 1).
FUTURE_CLOSE = {
    "open_time_ms": T0, "open": 100.2, "high": 100.6, "low": 99.4,
    "close": 99.8, "close_time_ms": T0 + STEP_MS - 1,
}

ENTRY_PX = 100.0
STOP_PX = 98.5


def closed_frame(candle: Dict[str, Any]) -> tuple:
    payload = dict(candle)
    payload.update({
        "symbol": "BTCUSDT", "interval": "1m", "closed": True,
        "base_volume": "123.4",
    })
    return "closed", payload


def hello_frame() -> tuple:
    return "hello", {
        "contract_version": "market-stream/v1",
        "service": "market-stream-service/v1",
        "identity": {"symbol": "BTCUSDT", "interval": "1m",
                     "venue": "binance", "market_type": "usd_m_futures",
                     "source": "ws_kline"},
    }


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
        "hypothesis_id": "ENG-STARTUP-v1", "hypothesis_version": "v1",
        "rule_version": "RULE-CAUSAL-V1",
        "request_id": request_id,
    }


def _free_port() -> int:
    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Harness:
    """Servicio HTTP real (EngineeringHTTPServer) con reloj inyectable."""

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

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        status, body = self.api("POST", "/sessions", payload)
        assert status == 200, f"create fallo: {status} {body}"
        return body

    def control(self, session_id: str, action: str,
                **opts: Any) -> tuple:
        return self.api("POST", f"/sessions/{session_id}/control", {
            "action": action,
            "expected_revision": opts.get("expected_revision"),
            "request_id": opts.get("request_id"),
        })

    def get(self, session_id: str) -> Dict[str, Any]:
        status, body = self.api("GET", f"/sessions/{session_id}")
        assert status == 200, f"get fallo: {status} {body}"
        return body

    def health(self) -> Dict[str, Any]:
        status, body = self.api("GET", "/health")
        assert status == 200, f"health fallo: {status} {body}"
        return body

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class _FakeSSEMarketServer:
    """Servidor SSE mínimo en loopback: publica frames de una cola."""

    def __init__(self) -> None:
        self.frames: "_queue_module.Queue[Any]" = _queue_module.Queue()
        outer = self

        class Handler(BaseHTTPRequestHandler):  # noqa: N801
            def do_GET(self):  # noqa: N802
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
                        except _queue_module.Empty:
                            continue
                        self.wfile.write(frame)
                        self.wfile.flush()
                except (ConnectionError, BrokenPipeError, OSError):
                    pass

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = __import__("threading").Thread(
            target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def send(self, event: str, payload: Dict[str, Any]) -> None:
        self.frames.put(sse_frame(event, payload))

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def wait_for(check, timeout: float = 15.0, interval: float = 0.05) -> Any:
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        last = check()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"condición no alcanzada en {timeout}s: {last!r}")


def _publish(tag: str, ahora: int, recibido: int, close_ms: int,
             t_prev: Optional[int], t_new: Optional[int], trigger: str,
             contador: int, decision: Optional[str],
             decision_reason: Optional[str]) -> None:
    print(
        f"[{tag}] referencia_temporal_ms={ahora} "
        f"recepcion_ms={recibido} cierre_close_time_ms={close_ms} "
        f"T_anterior_ms={t_prev} T_nuevo_ms={t_new} "
        f"evento_disparador={trigger} "
        f"contador_evaluaciones={contador} "
        f"resultado={decision} ({decision_reason})")


def _public(session: Dict[str, Any]) -> Dict[str, Any]:
    cfg = session.get("config") or {}
    return {
        "status": session.get("status"),
        "clock_ms": session.get("clock_ms"),
        "revision": session.get("revision"),
        "candles": [c.get("open_time_ms") for c in (session.get("candles")
                                                   or [])],
        "decision": cfg.get("decision"),
        "decision_reason": cfg.get("decision_reason"),
    }


class ClockStartupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="eng-startup-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_provider(self, server_ms: int, wall_ms: int
                       ) -> _LocalTimeProvider:
        return _LocalTimeProvider(server_ms, wall_ms)

    # --- prueba 1: sincronización válida → cierre conocido admitido una vez --

    def test_sincronizacion_valida_cierre_admitido_una_vez(self):
        """Reloj sincronizado (ahora = T0 + 2 pasos) → cierre con close_time
        <= ahora admitido, T avanza, evaluación con decisión y motivo;
        repetir no duplica el contador."""
        ahora = [T0 + 2 * STEP_MS]
        provider = self._make_provider(ahora[0], ahora[0])
        sync = ClockSynchronizer(
            fetch_server_time=provider.fetch_server_time,
            wall_clock_ms=provider.wall_clock_ms)
        self.assertTrue(asyncio.run(sync.sync()))  # sincronización local válida
        server = _FakeSSEMarketServer()
        harness = Harness(
            self.tmp, server.url,
            clock_sync=sync, clock_source="backend_sincronizado")
        try:
            self.assertIsNotNone(harness.world._now_ms())
            self.assertEqual(harness.world._now_ms(), T0 + 2 * STEP_MS)
            # Estado del reloj expuesto en /health.
            h = harness.health()
            clk = h["clock"]
            self.assertTrue(clk["available"], clk)
            self.assertEqual(clk["source"], "backend_sincronizado")
            self.assertIsNotNone(clk["offset_ms"])
            self.assertIsNotNone(clk["rtt_ms"])

            created = harness.create(live_payload(CONTEXT, "req-ok-1"))
            sid = created["session"]["session_id"]
            t_prev = created["session"]["clock_ms"]
            self.assertEqual(t_prev, T0 - 1)

            try:
                status, _ = harness.control(sid, "start",
                                            request_id="start-ok-1")
                self.assertEqual(status, 200)
                server.send(*hello_frame())

                # Cierre con close_time <= ahora: admitido.
                server.send(*closed_frame(FUTURE_CLOSE))
                body = wait_for(lambda: (lambda b: b if
                                         int(b["drive"]["evaluacion_contador"])
                                         >= 1 else None)(harness.get(sid)))
                # Esperar a que el guardado en disco complete (el contador
                # se incrementa en memoria antes de persistir).
                time.sleep(0.4)
                body = harness.get(sid)
                t_new = int(body["drive"]["evaluaciones"][-1]["T"])
                contador = int(body["drive"]["evaluacion_contador"])
                self.assertEqual(contador, 1, body)
                self.assertGreaterEqual(t_new, T0, body)
                cfg = body["session"]["config"]
                self.assertIsNotNone(cfg.get("decision"), body)
                self.assertIsNotNone(cfg.get("decision_reason"), body)
                _publish("CIERRE_ADMITIDO", ahora[0],
                         int(time.time() * 1000),
                         FUTURE_CLOSE["close_time_ms"], t_prev, t_new,
                         "closed", contador,
                         cfg.get("decision"), cfg.get("decision_reason"))

                # Repetir el mismo cierre: duplicado por marca de agua, no
                # duplica efectos ni el contador de evaluaciones.
                revision_antes = body["session"]["revision"]
                server.send(*closed_frame(FUTURE_CLOSE))
                time.sleep(0.4)
                body2 = harness.get(sid)
                self.assertEqual(int(body2["drive"]["evaluacion_contador"]),
                                 1, "no debe evaluar de nuevo")
                self.assertEqual(body2["session"]["revision"], revision_antes,
                                 "no debe revisar la sesión")
                _publish("CIERRE_REPETIDO_SIN_DUPLICAR", ahora[0],
                         int(time.time() * 1000),
                         FUTURE_CLOSE["close_time_ms"], t_new, t_new,
                         "closed", 1,
                         cfg.get("decision"),
                         "duplicado por marca de agua: sin efecto")
            finally:
                server.stop()
        finally:
            harness.close()

    # --- prueba 2: referencia no disponible o expirada → abstención ----------

    def test_referencia_no_disponible_o_expirada_abstiene(self):
        """Sin sincronización (o expirada): ahora_ms → None, create rechaza
        con RELOJ_REFERENCIA_INCERTO y los cierres se descartan sin avanzar
        watermark ni evaluar."""
        # Nunca sincronizada: referencia no disponible.
        provider = self._make_provider(T0, T0)
        sync = ClockSynchronizer(
            fetch_server_time=provider.fetch_server_time,
            wall_clock_ms=provider.wall_clock_ms)
        harness = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync, clock_source="backend_sincronizado")
        try:
            self.assertIsNone(harness.world._now_ms())
            status, body = harness.api("POST", "/sessions",
                                       live_payload(CONTEXT, "req-nosync-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)
            h = harness.health()
            self.assertFalse(h["clock"]["available"], h["clock"])
            _publish("SIN_SINCRONIZACION", T0, T0, None, None, None,
                     "create", 0, None,
                     "RELOJ_REFERENCIA_INCERTO: referencia no disponible")
        finally:
            harness.close()

        # Sincronizada y luego expirada: referencia expirada → abstención.
        provider2 = self._make_provider(T0, T0)
        sync2 = ClockSynchronizer(
            fetch_server_time=provider2.fetch_server_time,
            wall_clock_ms=provider2.wall_clock_ms)
        self.assertTrue(asyncio.run(sync2.sync()))
        harness2 = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync2, clock_source="backend_sincronizado")
        try:
            created = harness2.create(live_payload(CONTEXT, "req-exp-1"))
            sid = created["session"]["session_id"]
            self.assertEqual(created["session"]["clock_ms"], T0 - 1)
            # Expire la sincronización (marca de sincronización antigua).
            from datetime import datetime, timezone, timedelta
            sync2.last_sync_timestamp = (
                datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            self.assertIsNone(harness2.world._now_ms())
            server = _FakeSSEMarketServer()
            try:
                status, _ = harness2.control(sid, "start",
                                             request_id="start-exp-1")
                self.assertEqual(status, 200)
                server.send(*hello_frame())
                # Cierre con referencia expirada: descartado (abstención),
                # sin avanzar watermark ni evaluar.
                server.send(*closed_frame(FUTURE_CLOSE))
                time.sleep(0.4)
                body = harness2.get(sid)
                self.assertIsNone(body["session"]["config"].get("decision"))
                self.assertEqual(
                    len(body["session"]["candles"]), 0,
                    "sin avance de ventana por referencia expirada")
                _publish("REFERENCIA_EXPIRADA", T0,
                         int(time.time() * 1000),
                         FUTURE_CLOSE["close_time_ms"], T0 - 1, T0 - 1,
                         "closed", 0, None,
                         "abstención: referencia expirada")
            finally:
                server.stop()
        finally:
            harness2.close()

    # --- prueba 3: cierre futuro por contexto, snapshot y closed -----------

    def test_cierre_futuro_no_admitido_todas_las_entradas(self):
        """Con referencia válida (ahora = T0), un cierre futuro (close_time
        > ahora) no se admite por ninguno de los tres caminos:
        contexto inicial (create), snapshot y evento closed."""
        ahora = [T0]
        provider = self._make_provider(T0, T0)
        sync = ClockSynchronizer(
            fetch_server_time=provider.fetch_server_time,
            wall_clock_ms=provider.wall_clock_ms)
        self.assertTrue(asyncio.run(sync.sync()))

        # 1) Contexto inicial: última vela cierra tras ahora → rechazado.
        futuro_ctx = list(CONTEXT) + [
            ctx_candle(0, 100.0, 100.5, 99.5, 100.1)]  # close T0-1... usar futuro
        futuro_ctx[-1]["close_time_ms"] = T0 + STEP_MS  # futuro respecto a ahora
        harness = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync, clock_source="backend_sincronizado")
        try:
            status, body = harness.api("POST", "/sessions",
                                       live_payload(futuro_ctx, "req-fctx-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("CONTEXTO_FUTURO", str(body), body)
            _publish("CONTEXTO_FUTURO", ahora[0], ahora[0],
                     T0 + STEP_MS, None, None, "create", 0, None,
                     "cierre futuro respecto a referencia: no admitido")
        finally:
            harness.close()

        # 2) Snapshot: vela con close futuro no se admite (no avanza watermark).
        server = _FakeSSEMarketServer()
        harness2 = Harness(
            self.tmp, server.url,
            clock_sync=sync, clock_source="backend_sincronizado")
        try:
            created = harness2.create(live_payload(CONTEXT, "req-snap-1"))
            sid = created["session"]["session_id"]
            self.assertEqual(created["session"]["clock_ms"], T0 - 1)
            status, _ = harness2.control(sid, "start",
                                         request_id="start-snap-1")
            self.assertEqual(status, 200)
            server.send(*hello_frame())
            # Snapshot con una vela cuyo cierre es futuro.
            server.send("snapshot", {
                "symbol": "BTCUSDT", "interval": "1m",
                "candles": [dict(FUTURE_CLOSE, closed=True)],
                "observed": {"start_ms": T0, "end_ms": T0 + STEP_MS},
            })
            # Espera a que el drive procese el snapshot (sin admitir el futuro).
            wait_for(lambda: (lambda b: b if int(
                ((b.get("drive") or {}).get("stats") or {}).get("frames", 0)
            ) >= 2 else None)(harness2.get(sid)))
            body = harness2.get(sid)
            # La vela futura no entró en la ventana de operación.
            self.assertEqual(len(body["session"]["candles"]), 0,
                             "snapshot con cierre futuro no admitido")
            _publish("SNAPSHOT_FUTURO", ahora[0],
                     int(time.time() * 1000),
                     FUTURE_CLOSE["close_time_ms"], T0 - 1, T0 - 1,
                     "snapshot", 0, None,
                     "cierre futuro en snapshot: no admitido")
        finally:
            server.stop()
            harness2.close()

        # 3) Evento closed: cierre futuro no se admite.
        server3 = _FakeSSEMarketServer()
        harness3 = Harness(
            self.tmp, server3.url,
            clock_sync=sync, clock_source="backend_sincronizado")
        try:
            created = harness3.create(live_payload(CONTEXT, "req-closed-1"))
            sid = created["session"]["session_id"]
            status, _ = harness3.control(sid, "start",
                                         request_id="start-closed-1")
            self.assertEqual(status, 200)
            server3.send(*hello_frame())
            server3.send(*closed_frame(FUTURE_CLOSE))
            time.sleep(0.4)
            body = harness3.get(sid)
            self.assertEqual(len(body["session"]["candles"]), 0,
                             "closed con cierre futuro no admitido")
            self.assertEqual(int(body["drive"]["evaluacion_contador"]), 0,
                             "sin evaluación por cierre futuro")
            _publish("CLOSED_FUTURO", ahora[0],
                     int(time.time() * 1000),
                     FUTURE_CLOSE["close_time_ms"], T0 - 1, T0 - 1,
                     "closed", 0, None,
                     "cierre futuro por evento closed: no admitido")
        finally:
            server3.stop()
            harness3.close()

    # --- prueba 4: sincronización recuperada → progreso sin duplicados ------

    def test_sincronizacion_recuperada_progreso_sin_duplicados(self):
        """Referencia válida → cierre C1 admitido una vez → expiración → C2
        descartado → recuperación → C2 admitido una vez → repetir sin
        duplicar."""
        ahora = [T0 + 2 * STEP_MS]
        provider = self._make_provider(ahora[0], ahora[0])
        sync = ClockSynchronizer(
            fetch_server_time=provider.fetch_server_time,
            wall_clock_ms=provider.wall_clock_ms)
        self.assertTrue(asyncio.run(sync.sync()))
        server = _FakeSSEMarketServer()
        harness = Harness(
            self.tmp, server.url,
            clock_sync=sync, clock_source="backend_sincronizado")
        try:
            created = harness.create(live_payload(CONTEXT, "req-rec-1"))
            sid = created["session"]["session_id"]
            self.assertEqual(created["session"]["clock_ms"], T0 - 1)
            status, _ = harness.control(sid, "start",
                                        request_id="start-rec-1")
            self.assertEqual(status, 200)
            server.send(*hello_frame())

            # C1: close <= ahora → admitido una vez.
            c1 = dict(FUTURE_CLOSE)
            server.send(*closed_frame(c1))
            body = wait_for(lambda: (lambda b: b if
                                     int(b["drive"]["evaluacion_contador"])
                                     >= 1 else None)(harness.get(sid)))
            time.sleep(0.4)  # dejar que el guardado en disco complete
            body = harness.get(sid)
            contador1 = int(body["drive"]["evaluacion_contador"])
            self.assertEqual(contador1, 1, body)
            t_c1 = int(body["drive"]["evaluaciones"][-1]["T"])
            self.assertGreaterEqual(t_c1, T0, body)
            cfg = body["session"]["config"]
            self.assertIsNotNone(cfg.get("decision"), body)
            self.assertIsNotNone(cfg.get("decision_reason"), body)
            _publish("C1_ADMITIDO", ahora[0],
                     int(time.time() * 1000),
                     c1["close_time_ms"], T0 - 1, t_c1, "closed",
                     contador1, cfg.get("decision"),
                     cfg.get("decision_reason"))

            # Repetir C1: duplicado, sin duplicar.
            revision_antes = body["session"]["revision"]
            server.send(*closed_frame(c1))
            time.sleep(0.4)
            body = harness.get(sid)
            self.assertEqual(int(body["drive"]["evaluacion_contador"]), 1,
                             "no debe evaluar de nuevo")
            self.assertEqual(body["session"]["revision"], revision_antes,
                             "no debe revisar la sesión")

            # Expirar referencia → C2 descartado (abstención).
            from datetime import datetime, timezone, timedelta
            sync.last_sync_timestamp = (
                datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            self.assertIsNone(harness.world._now_ms())
            c2 = dict(FUTURE_CLOSE, open_time_ms=T0 + STEP_MS,
                        close_time_ms=T0 + 2 * STEP_MS - 1)
            server.send(*closed_frame(c2))
            time.sleep(0.4)
            body = harness.get(sid)
            self.assertEqual(int(body["drive"]["evaluacion_contador"]), 1,
                             "sin evaluación durante expiración")
            _publish("C2_DESCARTADO_EXPIRADO", ahora[0],
                     int(time.time() * 1000),
                     c2["close_time_ms"], t_c1, t_c1, "closed", 1, None,
                     "referencia expirada: abstención")

            # Recuperar sincronización → C2 admitido una vez.
            provider.set(T0 + 3 * STEP_MS, T0 + 3 * STEP_MS)
            self.assertTrue(asyncio.run(sync.sync()))
            self.assertEqual(harness.world._now_ms(), T0 + 3 * STEP_MS)
            server.send(*closed_frame(c2))
            body = wait_for(lambda: (lambda b: b if
                                     int(b["drive"]["evaluacion_contador"])
                                     >= 2 else None)(harness.get(sid)))
            time.sleep(0.4)
            body = harness.get(sid)
            contador2 = int(body["drive"]["evaluacion_contador"])
            self.assertEqual(contador2, 2, body)
            t_c2 = int(body["drive"]["evaluaciones"][-1]["T"])
            self.assertGreaterEqual(t_c2, T0 + STEP_MS, body)
            cfg = body["session"]["config"]
            self.assertIsNotNone(cfg.get("decision"), body)
            _publish("C2_ADMITIDO_TRAS_RECUPERACION",
                     T0 + 3 * STEP_MS, int(time.time() * 1000),
                     c2["close_time_ms"], t_c1, t_c2, "closed", contador2,
                     cfg.get("decision"), cfg.get("decision_reason"))

            # Repetir C2: sin duplicar.
            revision_antes2 = body["session"]["revision"]
            server.send(*closed_frame(c2))
            time.sleep(0.4)
            body2 = harness.get(sid)
            self.assertEqual(int(body2["drive"]["evaluacion_contador"]), 2)
            self.assertEqual(body2["session"]["revision"], revision_antes2)
            _publish("C2_REPETIDO_SIN_DUPLICAR", T0 + 3 * STEP_MS,
                     int(time.time() * 1000),
                     c2["close_time_ms"], t_c2, t_c2, "closed", 2,
                     body2["session"]["config"].get("decision"),
                     "duplicado por marca de agua: sin efecto")
        finally:
            server.stop()
            harness.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
