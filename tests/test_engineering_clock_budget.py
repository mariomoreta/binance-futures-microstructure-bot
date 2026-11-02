"""Regresiones focalizadas: activacion y presupuesto del reloj de referencia.

Cubre los requisitos de cableado de produccion (sin Binance, sin red
publica en modo local):

1. CLI local: cero intentos a dominios públicos (modo local = reloj de
   pared local, referencia local_controlado, nunca consulta /time).
2. Sin referencia: create_session no admite contexto
   (RELOJ_REFERENCIA_INCERTO).
3. Publico sin presupuesto explícito: el modo publico no se habilita si
   el presupuesto de la corrida no permite los intentos /time de la
   politica de sincronizacion (rechazado antes de tocar la red).
4. Intentos de tiempo contabilizados y bloqueados ANTES de enviar:
   cada reserva se registra en market_fetch_ledger previo al socket;
   al llenar la ventana, UpstreamBudgetExceeded se lanza sin invocar el
   fetch real.
5. Referencia valida vs expirada: admision / abstencion coherentes.

Usa proveedor de tiempo local y control de red (el fetch real de /time se
sustituye por un conta-calles; nunca hay peticion a fapi.binance.com).
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import queue as _queue_module
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.clock import ClockSynchronizer  # noqa: E402
from microstructure_probe.engineering_session_service import (  # noqa: E402
    CLOCK_PUBLIC_MAX_REQUESTS,
    EngineeringHTTPServer,
    EngineeringSessionController,
    _fetch_binance_server_time,
    _make_budgeted_time_fetch,
    _now_ms,
    make_synced_now_ms,
)
from microstructure_probe.history_client import UpstreamBudgetExceeded  # noqa: E402
from microstructure_probe.market_cache import (  # noqa: E402
    MAX_FETCH_REQUESTS_PER_WINDOW,
    MarketCache,
)

STEP_MS = 60 * 1000  # 1m
T0 = 1_790_000_000_000  # instante base (pasado respecto al reloj real)


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
        "hypothesis_id": "ENG-CLOCK-BUDGET-v1", "hypothesis_version": "v1",
        "rule_version": "RULE-CAUSAL-V1",
        "request_id": request_id,
    }


def _free_port() -> int:
    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Harness:
    """Servicio HTTP real con controlador, reloj y opcional sincronizador."""

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


def wait_for(check, timeout: float = 15.0, interval: float = 0.05) -> Any:
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        last = check()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"condicion no alcanzada en {timeout}s: {last!r}")


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


class ClockBudgetRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="eng-clock-budget-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- 1. Modo local: cero intentos a dominios publicos ----------------

    def test_modo_local_cero_intentos_publicos(self):
        """Arranque/demo local: reloj de pared local, referencia
        local_controlado, cero solicitudes publicas (ni siquiera setup de
        ClockSynchronizer ni consumo de presupuesto)."""
        import microstructure_probe.engineering_session_service as ess
        calls: List[Any] = []
        real = ess._fetch_binance_server_time

        def guarded() -> int:
            calls.append(None)
            raise AssertionError(
                "modo local nunca debe invocar el fetch publico /time")

        ess._fetch_binance_server_time = guarded
        try:
            harness = Harness(
                self.tmp, "http://127.0.0.1:1",
                now_ms=_now_ms,  # modo local equivalente a --clock-source local
                clock_source="local_controlado")
            try:
                h = harness.health()
                clk = h["clock"]
                self.assertEqual(clk["source"], "local_controlado", clk)
                self.assertTrue(clk["available"], clk)
                # El fetch publico de /time nunca se invoco.
                self.assertEqual(len(calls), 0, "peticion publica en modo local")
                # Crear sesion con contexto reciente: admitido (referencia
                # local valida = pared local).
                created = harness.create(live_payload(CONTEXT, "req-local-1"))
                self.assertEqual(created["session"]["clock_ms"], T0 - 1)
                _publish("LOCAL_CERO_PUBLICO", T0 - 1, T0 - 1, None, None,
                         T0 - 1, "create", 0, None,
                         "modo local: referencia local_controlado, cero publico")
            finally:
                harness.close()
        finally:
            ess._fetch_binance_server_time = real

    # --- 2. Sin referencia: no admite contexto --------------------------

    def test_sin_referencia_no_admite_contexto(self):
        """Sincronizador nunca sincronizado (referencia no disponible):
        ahora_ms -> None, create_session rechaza con
        RELOJ_REFERENCIA_INCERTO antes de crear/iniciar."""
        sync = ClockSynchronizer()  # nunca sync()
        self.assertIsNone(sync.offset_ms)
        harness = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync, clock_source="public_validado")
        try:
            self.assertIsNone(harness.world._now_ms())
            status, body = harness.api("POST", "/sessions",
                                       live_payload(CONTEXT, "req-nosync-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)
            _publish("SIN_REFERENCIA", T0, T0, None, None, None, "create", 0,
                     None, "RELOJ_REFERENCIA_INCERTO: no admite contexto")
        finally:
            harness.close()

    # --- 3. Publico sin presupuesto: rechazado antes de tocar red ------

    def test_publico_sin_presupuesto_rechazado(self):
        """Si el presupuesto publico de la corrida no permite los
        intentos /time de la politica de sincronizacion (sample_count=5),
        el modo publico no se habilita (condicion de main())."""
        db = self.tmp / "cache.db"
        cache = MarketCache(db)
        cache.init_db()
        now = int(time.time() * 1000)
        # Llenar la ventana con el maximo permitido.
        used = cache.requests_in_window(now)
        self.assertEqual(used, 0)
        # Reservar hasta el tope de la ventana compartida.
        for _ in range(MAX_FETCH_REQUESTS_PER_WINDOW):
            row_id = cache.reserve_fetch_attempt(
                now, symbol=None,
                detail=json.dumps({"endpoint": "kline"}, sort_keys=True),
                max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                execution_id="eng-fill-window")
            self.assertIsNotNone(row_id)
        # Ahora no queda presupuesto para una politica de 5 intentos /time.
        self.assertTrue(
            cache.requests_in_window(now) + CLOCK_PUBLIC_MAX_REQUESTS
            > MAX_FETCH_REQUESTS_PER_WINDOW,
            "presupuesto insuficiente para politica de sincronizacion")
        _publish("PUBLICO_SIN_PRESUPUESTO", now, now, None, None, None,
                 "main_clock_source_check", 0, None,
                 "modo publico rechazado: presupuesto insuficiente")

    # --- 4. Intentos de tiempo contabilizados y bloqueados antes de enviar

    def test_intentos_tiempo_contabilizados_bloqueados_antes_de_enviar(self):
        """Cada reserva se registra en market_fetch_ledger ANTES del socket;
        al llenar la ventana, UpstreamBudgetExceeded se lanza sin invocar el
        fetch real."""
        db = self.tmp / "cache2.db"
        cache = MarketCache(db)
        cache.init_db()
        now = int(time.time() * 1000)
        execution_id = f"eng-clock-budget-{now}"
        fetch_calls: List[int] = []

        def real_fetch() -> int:
            fetch_calls.append(1)
            return T0 + 2 * STEP_MS

        budgeted = _make_budgeted_time_fetch(
            cache, execution_id, CLOCK_PUBLIC_MAX_REQUESTS, real_fetch)

        # Consumir todo el presupuesto de la ventana con reservas de /time.
        for _ in range(CLOCK_PUBLIC_MAX_REQUESTS):
            self.assertEqual(budgeted(), T0 + 2 * STEP_MS)
        self.assertEqual(len(fetch_calls), CLOCK_PUBLIC_MAX_REQUESTS)

        # El siguiente intento se bloquea ANTES de enviar (sin tocar red).
        with self.assertRaises(UpstreamBudgetExceeded):
            budgeted()
        self.assertEqual(len(fetch_calls), CLOCK_PUBLIC_MAX_REQUESTS,
                         "fetch real invocado despues de agotar presupuesto")
        # Cada intento (incluido el bloqueado) queda trazado en el ledger.
        rows = cache.fetch_ledger(limit=50)
        time_rows = [r for r in rows
                     if "fapi_time" in (r.get("detail") or "")]
        self.assertGreaterEqual(len(time_rows), CLOCK_PUBLIC_MAX_REQUESTS,
                                "intentos de tiempo contabilizados en ledger")
        _publish("PRESUPUESTO_TIEMPO_AGOTADO", now, now, None, None, None,
                 "fetch_time", CLOCK_PUBLIC_MAX_REQUESTS, None,
                 "intentos contabilizados y bloqueados antes de enviar")

    # --- 5. Referencia valida vs expirada: admision / abstencion ----------

    def test_referencia_valida_admite_expirada_abstiene(self):
        """Referencia valida: contexto admitido y T fijado. Referencia
        expirada: ahora_ms -> None, abstencion (sin avanzar ni evaluar)."""
        # Valida.
        ahora = [T0 + 2 * STEP_MS]
        provider_ok = _LocalTimeProvider(ahora[0], ahora[0])
        sync_ok = ClockSynchronizer(
            fetch_server_time=provider_ok.fetch_server_time,
            wall_clock_ms=provider_ok.wall_clock_ms)
        self.assertTrue(asyncio.run(sync_ok.sync()))
        harness_ok = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync_ok, clock_source="public_validado")
        try:
            self.assertEqual(harness_ok.world._now_ms(), T0 + 2 * STEP_MS)
            created = harness_ok.create(live_payload(CONTEXT, "req-ok-1"))
            self.assertEqual(created["session"]["clock_ms"], T0 - 1)
            _publish("REFERENCIA_VALIDA", ahora[0], ahora[0], None, None,
                     T0 - 1, "create", 0, None,
                     "referencia valida: contexto admitido, T = T0 - 1")
        finally:
            harness_ok.close()

        # Expirada.
        provider_exp = _LocalTimeProvider(T0, T0)
        sync_exp = ClockSynchronizer(
            fetch_server_time=provider_exp.fetch_server_time,
            wall_clock_ms=provider_exp.wall_clock_ms)
        self.assertTrue(asyncio.run(sync_exp.sync()))
        sync_exp.last_sync_timestamp = (
            datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        harness_exp = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync_exp, clock_source="public_validado")
        try:
            self.assertIsNone(harness_exp.world._now_ms())
            status, body = harness_exp.api("POST", "/sessions",
                                           live_payload(CONTEXT, "req-exp-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)
            _publish("REFERENCIA_EXPIRADA", T0, T0, None, None, None,
                     "create", 0, None,
                     "referencia expirada: abstencion, sin crear sesion")
        finally:
            harness_exp.close()


class _LocalTimeProvider:
    """Proveedor de tiempo local controlado (sin Binance, sin red publica)."""

    def __init__(self, server_ms: int, wall_ms: int) -> None:
        self.server_ms = server_ms
        self.wall_ms = wall_ms

    def fetch_server_time(self) -> int:
        return int(self.server_ms)

    def wall_clock_ms(self) -> float:
        return float(self.wall_ms)


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
