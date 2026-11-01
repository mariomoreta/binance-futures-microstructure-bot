"""Regresiones focalizadas: referencia temporal explícita en create_session
y admisión de cierres (cero Binance, cero red pública).

Valida el defecto de causalidad: fijar T desde el último close_time de
contexto no acredita que ese cierre ya ocurrió. Se introduce una referencia
temporal explícita (reloj de referencia inyectable en el controlador:
tiempo del backend con sincronización en modo público; reloj controlado por
el transporte de prueba en local/replay) y se rechazan los cierres futuros
sin tolerancia positiva de intervalo.

Cubre:
  1. Creación rechaza contexto futuro contra el reloj de referencia
     (caso histórico: crear a T-60s con última vela cerrando en T-1s →
     CONTEXTO_FUTURO, no se admite como contexto cerrado).
  2. Avance legítimo: cierre futuro provisional → avanza el reloj de prueba →
     mismo cierre admitido una vez → evaluación con decisión y motivo;
     repetirlo no duplica efectos (contador de evaluaciones inalterado).
  3. Determinismo: dos futuros distintos con el mismo prefijo producen el
     mismo estado hasta T.

Publica (por consola, al final de cada prueba): referencia temporal,
recepción, cierre, T anterior/nuevo, evento disparador, contador de
evaluaciones y resultado.
"""
from __future__ import annotations

import json
import queue
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe import engineering_session_service as svc  # noqa: E402

STEP_MS = 60 * 1000  # 1m
T0 = 1_790_000_000_000  # instante base (pasado respecto al reloj de pared)


def sse_frame(event: str, payload: Dict[str, Any]) -> bytes:
    body = f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode("utf-8")
    return f"{len(body):x}\r\n".encode("ascii") + body + b"\r\n"


class FakeSSEMarketServer:
    """Servidor SSE mínimo en loopback: publica frames de una cola compartida.

    Cada conexión GET /stream se bloquea esperando frames del guion. Sirve
    para emular el servicio de mercado market-stream/v1 sin Binance.
    """

    def __init__(self) -> None:
        self.frames: "queue.Queue[Any]" = queue.Queue()
        outer = self

        class Handler(BaseHTTPRequestHandler):  # noqa: N801
            def do_GET(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    while True:
                        try:
                            frame = outer.frames.get(timeout=0.05)
                        except queue.Empty:
                            continue
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

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def ctx_candle(idx_from_t0_ms: int, o: float, h: float, l: float,
               c: float) -> Dict[str, Any]:
    ot = T0 + idx_from_t0_ms
    return {"open_time_ms": ot, "open": o, "high": h, "low": l, "close": c,
            "close_time_ms": ot + STEP_MS - 1}


# Contexto reciente cerrado: última vela cierra en T0 - 1 (fija T = T0 - 1).
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


def live_config() -> Dict[str, Any]:
    return {
        "symbol": "BTCUSDT", "interval": "1m", "direction": "LONG",
        "notional_usdt": 1000.0, "entry_px": ENTRY_PX, "stop_px": STOP_PX,
        "stop_distance_pct": (ENTRY_PX - STOP_PX) / ENTRY_PX * 100.0,
        "horizon_ms": 2 * 60 * 60 * 1000,
        "fee_bps": 5.0, "spread_bps": 1.0, "slippage_bps": 2.0,
        "rule_version": "RULE-CAUSAL-V1",
    }


def live_payload(context: List[Dict[str, Any]], request_id: str
                 ) -> Dict[str, Any]:
    return {
        "config": live_config(),
        "candles": [],
        "context": context,
        "transport": "market_stream",
        "hypothesis_id": "ENG-CLOCK-REF-v1", "hypothesis_version": "v1",
        "rule_version": "RULE-CAUSAL-V1",
        "request_id": request_id,
    }


class Harness:
    """Servicio HTTP efímero + controlador en proceso con reloj inyectable.

    ``now_ms`` es la referencia temporal independiente. Por defecto usa el
    reloj de pared; en las pruebas se inyecta un reloj controlado.
    """

    def __init__(self, sessions_dir: Path, market_url: str,
                 now_ms: Optional[Callable[[], Optional[int]]] = None
                 ) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.world = svc.EngineeringSessionController(
            self.sessions_dir, 5.0, market_url=market_url,
            market_bars=50, live_silence_ms=120_000.0, now_ms=now_ms)
        self.server = svc.EngineeringHTTPServer("127.0.0.1", 0, self.world)
        self._thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def api(self, method: str, path: str,
            payload: Optional[Dict[str, Any]] = None,
            timeout: float = 15.0) -> Tuple[int, Any]:
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
                **opts: Any) -> Tuple[int, Any]:
        return self.api("POST", f"/sessions/{session_id}/control", {
            "action": action,
            "expected_revision": opts.get("expected_revision"),
            "request_id": opts.get("request_id"),
        })

    def get(self, session_id: str) -> Dict[str, Any]:
        status, body = self.api("GET", f"/sessions/{session_id}")
        assert status == 200, f"get fallo: {status} {body}"
        return body

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def wait_for(check, timeout: float = 15.0, interval: float = 0.05) -> Any:
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        last = check()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"condición no alcanzada en {timeout}s: {last!r}")


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


def _publish(tag: str, ahora: int, received_at: int, close_ms: int,
             t_prev: Optional[int], t_new: Optional[int], trigger: str,
             contador: int, decision: Optional[str],
             decision_reason: Optional[str]) -> None:
    print(
        f"[{tag}] referencia_temporal_ms={ahora} "
        f"recepcion_ms={received_at} cierre_close_time_ms={close_ms} "
        f"T_anterior_ms={t_prev} T_nuevo_ms={t_new} "
        f"evento_disparador={trigger} "
        f"contador_evaluaciones={contador} "
        f"resultado={decision} ({decision_reason})")


class ClockReferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="eng-clock-ref-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- prueba 1: creación rechaza contexto futuro (caso histórico) ------

    def test_create_rechaza_contexto_futuro_caso_historico(self):
        """Crear a T-60s con última vela cerrando en T-1s no se admite como
        contexto cerrado: el cierre todavía no ocurrió respecto a la
        referencia temporal."""
        ahora = [T0 - 60_000]  # referencia: "ahora" = T-60s
        server = FakeSSEMarketServer()
        harness = Harness(self.tmp, server.url, now_ms=lambda: ahora[0])
        try:
            status, body = harness.api("POST", "/sessions",
                                       live_payload(CONTEXT,
                                                    "req-futuro-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("CONTEXTO_FUTURO", str(body), body)
            # No se creó sesión: no hay session_id.
            self.assertNotIn("session", body)
            _publish("CREATE_FUTURO_RECHAZADO", ahora[0], ahora[0],
                     T0 - 1, None, None, "create", 0, None,
                     "CONTEXTO_FUTURO: cierre T-1 posterior a referencia T-60s")
        finally:
            harness.close()
            server.stop()

    # --- prueba 2: avance legítimo vía HTTP/SSE (camino real) -----------

    def test_cierre_futuro_provisional_avanza_reloj_admitido_una_vez(self):
        """Contexto válido (T = T0 - 1) → cierre futuro aún provisional
        (close_time > referencia, no se admite) → avanza el reloj de prueba
        → mismo cierre ahora disponible → admitido una vez → evaluación con
        decisión y motivo → repetir no duplica el contador de evaluaciones."""
        ahora = [T0 - 1]  # referencia inicial: contexto ya cerrado, T = T0 - 1
        server = FakeSSEMarketServer()
        harness = Harness(self.tmp, server.url, now_ms=lambda: ahora[0])
        try:
            created = harness.create(live_payload(CONTEXT, "req-avance-1"))
            sid = created["session"]["session_id"]
            t_prev = created["session"]["clock_ms"]
            self.assertEqual(t_prev, T0 - 1)

            status, _ = harness.control(sid, "start",
                                        request_id="start-avance-1")
            self.assertEqual(status, 200)
            # Identidad del feed + silencio inicial.
            server.send(*hello_frame())

            # Cierre futuro: close_time (T0 + STEP - 1) > referencia (T0 - 1).
            # Aún no ocurrió: provisional, no se admite, T no avanza, sin
            # evaluación.
            server.send(*closed_frame(FUTURE_CLOSE))
            wait_for(lambda: harness.get(sid)["session"]["clock_ms"] == T0 - 1
                     and len(harness.get(sid)["session"]["candles"]) == 0)
            body = harness.get(sid)
            self.assertEqual(body["session"]["clock_ms"], T0 - 1)
            self.assertEqual(body["session"]["candles"], [])
            self.assertEqual(body["drive"]["evaluacion_contador"], 0)
            received_provisional = int(time.time() * 1000)
            _publish("CIERRE_PROVISIONAL", ahora[0], received_provisional,
                     FUTURE_CLOSE["close_time_ms"], t_prev, T0 - 1,
                     "closed", 0, None,
                     "close_time futuro respecto a referencia: no admitido")

            # Avanza el reloj de prueba: ahora el cierre ya ocurrió.
            ahora[0] = T0 + 2 * STEP_MS
            server.send(*closed_frame(FUTURE_CLOSE))
            # Espera a que la evaluación quede registrada en el drive Y que el
            # estado persistido refleje el nuevo T (evita leer el disco antes
            # de que el guardado de _live_advance complete).
            body = wait_for(lambda: (lambda b: b if (
                    int(b["drive"]["evaluacion_contador"]) >= 1
                    and int(b["session"]["clock_ms"] or 0) >= T0
                ) else None)(harness.get(sid)))
            t_new = body["session"]["clock_ms"]
            contador = int(body["drive"]["evaluacion_contador"])
            self.assertEqual(contador, 1, body)
            self.assertGreaterEqual(t_new, T0, body)  # T avanzó tras el cierre
            cfg = body["session"]["config"]
            self.assertIsNotNone(cfg.get("decision"), body)
            self.assertIsNotNone(cfg.get("decision_reason"), body)
            received_admitido = int(time.time() * 1000)
            _publish("CIERRE_ADMITIDO", ahora[0], received_admitido,
                     FUTURE_CLOSE["close_time_ms"], t_prev, t_new,
                     "closed", contador, cfg.get("decision"),
                     cfg.get("decision_reason"))

            # Repetir el mismo cierre: duplicado por marca de agua, no duplica
            # efectos (ni vela, ni decisión, ni contador de evaluaciones).
            revision_antes = body["session"]["revision"]
            server.send(*closed_frame(FUTURE_CLOSE))
            time.sleep(0.3)
            body2 = harness.get(sid)
            self.assertEqual(int(body2["drive"]["evaluacion_contador"]), 1,
                             "el cierre repetido no debe evaluar de nuevo")
            self.assertEqual(body2["session"]["revision"], revision_antes,
                             "el cierre repetido no debe revisar la sesión")
            self.assertEqual(len(body2["session"]["candles"]),
                             len(body["session"]["candles"]))
            _publish("CIERRE_REPETIDO_SIN_DUPLICAR", ahora[0],
                     int(time.time() * 1000), FUTURE_CLOSE["close_time_ms"],
                     t_new, t_new, "closed", 1,
                     cfg.get("decision"),
                     "duplicado por marca de agua: sin efecto")
        finally:
            harness.close()
            server.stop()

    # --- prueba 3: determinismo, mismo prefijo, futuros distintos ----------

    def test_dos_futuros_mismo_prefijo_estado_igual_hasta_T(self):
        """Dos sesiones con el mismo prefijo (contexto idéntico) y futuros
        distintos producen el mismo estado hasta T (cierre no acreditado aún
        no entra en el prefijo)."""
        ahora = [T0 - 1]
        server = FakeSSEMarketServer()
        harness = Harness(self.tmp, server.url,
                          now_ms=lambda: ahora[0])
        try:
            futuros = [
                ("A", dict(FUTURE_CLOSE, close=99.8)),
                ("B", dict(FUTURE_CLOSE, close=50.0)),  # futuro distinto
            ]
            sesiones = []
            for tag, fut in futuros:
                created = harness.create(
                    live_payload(CONTEXT, f"req-det-{tag}"))
                sid = created["session"]["session_id"]
                harness.control(sid, "start", request_id=f"start-det-{tag}")
                server.send(*hello_frame())
                server.send(*closed_frame(fut))
                # Futuros con close_time > referencia: ninguno admitido,
                # estado hasta T inalterado.
                wait_for(lambda s=sid: (
                    harness.get(s)["session"]["clock_ms"] == T0 - 1
                    and len(harness.get(s)["session"]["candles"]) == 0))
                sesiones.append((tag, sid, harness.get(sid)))

            # Mismo prefijo -> mismo estado hasta T (clock, velas, decisión).
            (tag_a, sid_a, body_a), (tag_b, sid_b, body_b) = sesiones
            self.assertEqual(_public(body_a["session"]),
                             _public(body_b["session"]))
            self.assertEqual(body_a["session"]["clock_ms"], T0 - 1)
            self.assertEqual(body_b["session"]["clock_ms"], T0 - 1)
            self.assertEqual(body_a["session"]["candles"], [])
            self.assertEqual(body_b["session"]["candles"], [])
            self.assertEqual(body_a["drive"]["evaluacion_contador"], 0)
            self.assertEqual(body_b["drive"]["evaluacion_contador"], 0)
            _publish("DETERMINISMO_HASTA_T", ahora[0], ahora[0],
                     T0 + STEP_MS - 1, T0 - 1, T0 - 1, "closed", 0, None,
                     f"mismo prefijo, futuros {tag_a}/{tag_b}: estado igual "
                     "hasta T (cierres futuros no acreditados no entran)")
        finally:
            harness.close()
            server.stop()


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
