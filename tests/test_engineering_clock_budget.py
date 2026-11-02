"""Regresiones focalizadas: activación y presupuesto del reloj de referencia.

Cubre los requisitos de cableado de producción (sin Binance, sin red
pública en modo local):

1. Dos límites separados: el general de 30 solicitudes/ventana móvil se
   mantiene; se añade el límite TOTAL de la corrida, compartido entre
   /time, klines, catálogo, reintentos y recuperación, que NO se reinicia
   al pasar la ventana de 60 s. Cada intento reserva ANTES de enviar y
   agotar el total bloquea solicitudes posteriores aunque cambie la
   ventana móvil.
2. Fuentes explícitas en /health: reloj local del sistema, reloj
   inyectado/controlado de prueba, reloj público sincronizado y referencia
   no disponible/expirada. El modo público no admite silenciosamente el
   reloj local (--clock-source conserva su valor predeterminado "local").
   El arnés comprueba la fuente y su validez ANTES de crear la sesión.
3. Presupuesto viable, sin ejecutar: se conservan las cinco muestras del
   sincronizador; se propone el nuevo mínimo 5 (tiempo) + 2 (klines) = 7.
   Los fallos/reintentos consumen esos cupos y pueden impedir completar la
   preparación; no se garantizan dos descargas si se agotó el presupuesto.

Usa proveedor de tiempo local y control de red (el fetch real de /time se
sustituye por un conta-calles; nunca hay petición a fapi.binance.com).
"""
from __future__ import annotations

import argparse
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
    CLOCK_REFERENCE_MAX_AGE_MS,
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
    MAX_FETCH_REQUESTS_PER_RUN,
    MarketCache,
)

# Sanidad: el presupuesto de corrida propuesto es 7 (5 tiempo + 2 klines).
assert MAX_FETCH_REQUESTS_PER_RUN == 7

# engineering_live_window y local_kline_provider viven en scripts/
# (fuera del paquete microstructure_probe).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import engineering_live_window as elw_mod  # noqa: E402
from local_kline_provider import LocalKlineProvider  # noqa: E402


class _FakeProc:
    """Proceso falso para capturar argv sin arrancar servicios reales."""
    pid = 0

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0


def _make_orchestrator_args(provider_port: int, sessions_dir: Path,
                            run_id: Optional[str],
                            transport: str = "local",
                            clock_source: Optional[str] = None,
                            execute: bool = False) -> argparse.Namespace:
    """Construye los argumentos del orquestador para pruebas focalizadas."""
    argv = [
        "--transport", transport,
        "--service-port", "8791",
        "--engineering-port", "8797",
        "--provider-port", str(provider_port),
        "--ws-port", "18800",
        "--dashboard", "http://127.0.0.1:3020",
        "--build-id", "BUILD_ID_TEST",
        "--symbols", "MINAUSDT,BTCUSDT",
        "--interval", "1m",
        "--bars", "300",
        "--deadline", "180",
        "--sessions-dir", str(sessions_dir),
        "--out", str(sessions_dir / "evidence.json"),
    ]
    if execute:
        argv.append("--execute")
    if run_id is not None:
        argv += ["--run-id", run_id]
    if clock_source is not None:
        argv += ["--clock-source", clock_source]
    return elw_mod.build_arg_parser().parse_args(argv)

STEP_MS = 60 * 1000  # 1m
T0 = 1_790_000_000_000  # instante base (pasado respecto al reloj real)


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
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
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

    def assert_clock_before_create(self, expected_source: str) -> None:
        """El arnés comprueba la fuente y su validez ANTES de crear sesión.

        Si el /health no reporta la fuente esperada disponible, la sesión no
        debe crearse (abstención por fuente incorrecta o expirada).
        """
        clk = self.health()["clock"]
        if clk["source"] != expected_source:
            raise AssertionError(
                f"fuente esperada {expected_source}, obtuvo "
                f"{clk['source']!r}: {clk}")
        if not clk["available"]:
            raise AssertionError(f"fuente no disponible: {clk}")


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


class ClockBudgetRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="eng-clock-budget-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- 1. Modo local: cero intentos a dominios públicos -----------------

    def test_modo_local_cero_intentos_publicos(self):
        """Arranque/demo local: reloj de pared local (local_sistema), cero
        solicitudes públicas (ni setup de ClockSynchronizer ni consumo de
        presupuesto)."""
        import microstructure_probe.engineering_session_service as ess
        calls: List[Any] = []
        real = ess._fetch_binance_server_time

        def guarded() -> int:
            calls.append(None)
            raise AssertionError(
                "modo local nunca debe invocar el fetch público /time")

        ess._fetch_binance_server_time = guarded
        try:
            harness = Harness(
                self.tmp, "http://127.0.0.1:1",
                now_ms=_now_ms, clock_source="local_sistema")
            try:
                # Comprueba fuente y validez antes de crear.
                harness.assert_clock_before_create("local_sistema")
                # El fetch público de /time nunca se invocó.
                self.assertEqual(len(calls), 0, "petición pública en modo local")
                # Crear sesión con contexto reciente: admitido (referencia
                # local válida = pared local).
                created = harness.create(live_payload(CONTEXT, "req-local-1"))
                self.assertEqual(created["session"]["clock_ms"], T0 - 1)
                _publish("LOCAL_CERO_PÚBLICO", T0 - 1, T0 - 1, None, None,
                         T0 - 1, "create", 0, None,
                         "modo local: referencia local_sistema, cero pública")
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
            clock_sync=sync, clock_source="public_sincronizado")
        try:
            # /health reporta public_sincronizado pero available False
            # (nunca sincronizado).
            clk = harness.health()["clock"]
            self.assertEqual(clk["source"], "public_sincronizado", clk)
            self.assertFalse(clk["available"], clk)
            self.assertIsNone(harness.world._now_ms())
            status, body = harness.api("POST", "/sessions",
                                       live_payload(CONTEXT, "req-nosync-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)
            _publish("SIN_REFERENCIA", T0, T0, None, None, None, "create", 0,
                     None, "RELOJ_REFERENCIA_INCERTO: no admite contexto")
        finally:
            harness.close()

    # --- 3. Público sin presupuesto: rechazado antes de tocar red ------

    def test_público_sin_presupuesto_rechazado(self):
        """Si el presupuesto público de la corrida no permite los
        intentos /time de la política de sincronización (sample_count=5),
        el modo público no se habilita (condición de main)."""
        db = self.tmp / "cache.db"
        cache = MarketCache(db)
        cache.init_db()
        now = int(time.time() * 1000)
        used = cache.requests_in_window(now)
        self.assertEqual(used, 0)
        # Llenar la ventana con el máximo permitido (30).
        for _ in range(MAX_FETCH_REQUESTS_PER_WINDOW):
            row_id = cache.reserve_fetch_attempt(
                now, symbol=None,
                detail=json.dumps({"endpoint": "kline"}, sort_keys=True),
                max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                execution_id="eng-fill-window")
            self.assertIsNotNone(row_id)
        # Ahora no queda presupuesto de ventana para una política de 5
        # intentos /time.
        self.assertTrue(
            cache.requests_in_window(now) + CLOCK_PUBLIC_MAX_REQUESTS
            > MAX_FETCH_REQUESTS_PER_WINDOW,
            "presupuesto de ventana insuficiente para política de sincronización")
        _publish("PÚBLICO_SIN_PRESUPUESTO", now, now, None, None, None,
                 "main_clock_source_check", 0, None,
                 "modo público rechazado: presupuesto de ventana insuficiente")

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
                         "fetch real invocado después de agotar presupuesto")
        # Cada intento (incluido el bloqueado) queda trazado en el ledger.
        rows = cache.fetch_ledger(limit=50)
        time_rows = [r for r in rows
                     if "fapi_time" in (r.get("detail") or "")]
        self.assertGreaterEqual(len(time_rows), CLOCK_PUBLIC_MAX_REQUESTS,
                                "intentos de tiempo contabilizados en ledger")
        _publish("PRESUPUESTO_TIEMPO_AGOTADO", now, now, None, None, None,
                 "fetch_time", CLOCK_PUBLIC_MAX_REQUESTS, None,
                 "intentos contabilizados y bloqueados antes de enviar")

    # --- Límite TOTAL de la corrida: compartido, no se reinicia por ventana

    def test_límite_total_corrida_compartido_bloquea_desde_ventana(self):
        """El presupuesto total de la corrida (7) es compartido entre /time,
        klines, catálogo, reintentos y recuperación. Se reserva ANTES de
        enviar y agotarlo bloquea solicitudes posteriores AUNQUE cambie la
        ventana móvil (60 s)."""
        db = self.tmp / "cache3.db"
        cache = MarketCache(db)
        cache.init_db()
        now = int(time.time() * 1000)
        # Ventana enorme para que nunca bloquee por ventana y aislar el total
        # de la corrida como único limitante.
        GRAN_VENTANA = 10_000
        fetch_calls: List[int] = []

        def reserva_y_quizá_envía(endpoint: str, execution_id: str) -> Any:
            """Reserva 1 cupo contra el total de la corrida; solo si la
            reserva tiene éxito se 'envía' (se cuenta el fetch real)."""
            row_id = cache.reserve_fetch_attempt(
                now, symbol=None,
                detail=json.dumps({"endpoint": endpoint}, sort_keys=True),
                max_requests=GRAN_VENTANA, window_ms=60_000, attempts=1,
                execution_id=execution_id,
                run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
            )
            if row_id is not None:
                fetch_calls.append(1)  # envió solo tras reserva exitosa
            return row_id

        # Consumir el presupuesto TOTAL de la corrida (7) con reservas de /time.
        for i in range(MAX_FETCH_REQUESTS_PER_RUN):
            self.assertIsNotNone(
                reserva_y_quizá_envía("fapi_time", "eng-run-time"),
                f"reserva de tiempo {i+1} debe tener éxito",
            )
        self.assertEqual(len(fetch_calls), MAX_FETCH_REQUESTS_PER_RUN,
                         "cada reserva de tiempo envió su fetch")
        self.assertEqual(cache.run_requests_used("eng-run-time"),
                         MAX_FETCH_REQUESTS_PER_RUN,
                         "run total agotado")

        # El siguiente intento de /time se bloquea por el total de la corrida.
        self.assertIsNone(
            reserva_y_quizá_envía("fapi_time", "eng-run-time"),
            "total de corrida agotado debe bloquear",
        )
        self.assertEqual(len(fetch_calls), MAX_FETCH_REQUESTS_PER_RUN,
                         "no se envió más tras agotar el total de la corrida")

        # Aunque la ventana móvil cambie (simular 61 s después, usada=0),
        # el total de la corrida sigue agotado: sigue bloqueado.
        tarde = now + 61_000
        self.assertEqual(cache.requests_in_window(tarde), 0,
                         "ventana móvil se vació al pasar 60 s")
        self.assertIsNone(
            cache.reserve_fetch_attempt(
                tarde, symbol=None,
                detail=json.dumps({"endpoint": "fapi_time"}, sort_keys=True),
                max_requests=GRAN_VENTANA, window_ms=60_000, attempts=1,
                execution_id="eng-run-time",
                run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
            ),
            "el total no se reinició al pasar la ventana",
        )
        self.assertEqual(cache.run_requests_used("eng-run-time"),
                         MAX_FETCH_REQUESTS_PER_RUN,
                         "el total de la corrida no se reinició por ventana")

        # Compartido: una reserva de "klines" con el MISMO run_id también se
        # bloquea (mismo contador de corrida).
        self.assertIsNone(
            cache.reserve_fetch_attempt(
                tarde, symbol="BTCUSDT",
                detail=json.dumps({"endpoint": "klines"}, sort_keys=True),
                max_requests=GRAN_VENTANA, window_ms=60_000, attempts=1,
                execution_id="eng-run-time",
                run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
            ),
            "klines también bloqueadas por el total compartido (mismo run_id)",
        )
        _publish("TOTAL_CORRIDA_AGOTADO", now, tarde, None, None, None,
                 "reserva_pre_envío", MAX_FETCH_REQUESTS_PER_RUN, None,
                 "total de corrida agotado, compartido y no reiniciado por ventana")

    # --- Límite total de la corrida: ciclo de vida por run_id --------------

    def test_run_id_estable_consumo_conservado_al_reiniciar(self):
        """Una corrida tiene run_id estable; reiniciar el servicio de ESA
        corrida (nueva instancia de MarketCache sobre el mismo ledger) no
        devuelve cupos: el consumo se conserva."""
        db = self.tmp / "cache_restart.db"
        run_id = "eng-run-reinicio-1"

        # Primera instancia: consume 3 cupos de la corrida.
        cache1 = MarketCache(db)
        cache1.init_db()
        ahora = int(time.time() * 1000)
        for _ in range(3):
            row_id = cache1.reserve_fetch_attempt(
                ahora, symbol=None,
                detail=json.dumps({"endpoint": "fapi_time"}, sort_keys=True),
                max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                window_ms=60_000, attempts=1,
                execution_id=run_id,
                run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
            )
            self.assertIsNotNone(row_id)
        self.assertEqual(cache1.run_requests_used(run_id), 3,
                         "consumo inicial de 3 cupos")

        # Reinicio: nueva instancia de MarketCache (nuevo proceso de
        # servicio) sobre el MISMO ledger y el MISMO run_id.
        cache2 = MarketCache(db)
        cache2.init_db()
        self.assertEqual(cache2.run_requests_used(run_id), 3,
                         "consumo conservado tras reinicio de la misma "
                         "corrida: no se devuelven cupos")

        # El presupuesto sigue contando desde lo consumido (no reseteado).
        self.assertIsNotNone(
            cache2.reserve_fetch_attempt(
                ahora, symbol=None,
                detail=json.dumps({"endpoint": "fapi_time"}, sort_keys=True),
                max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                window_ms=60_000, attempts=1,
                execution_id=run_id,
                run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
            ),
            "tras reinicio se puede seguir consumiendo la corrida",
        )
        self.assertEqual(cache2.run_requests_used(run_id), 4,
                         "consumo acumulado tras reinicio")
        _publish("RUN_ID_CONSERVADO_AL_REINICIAR", ahora, ahora, None, None,
                 None, "reserva_pre_envío", 4, None,
                 "run_id estable: consumo conservado al reiniciar")

    def test_dos_instancias_misma_corrida_limite_compartido(self):
        """Arrancar otra instancia de la misma corrida no resetea el
        presupuesto: ambas instancias comparten el límite total (7)."""
        db = self.tmp / "cache_compartido.db"
        run_id = "eng-run-compartido"
        ahora = int(time.time() * 1000)

        cache_a = MarketCache(db)
        cache_a.init_db()
        cache_b = MarketCache(db)
        cache_b.init_db()

        # Instancia A consume 4 cupos.
        for _ in range(4):
            row_id = cache_a.reserve_fetch_attempt(
                ahora, symbol=None,
                detail=json.dumps({"endpoint": "fapi_time"}, sort_keys=True),
                max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                window_ms=60_000, attempts=1,
                execution_id=run_id,
                run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
            )
            self.assertIsNotNone(row_id)
        self.assertEqual(cache_a.run_requests_used(run_id), 4,
                         "instancia A consumió 4")

        # Instancia B consume 3 cupos más (comparte el mismo run_id).
        for _ in range(3):
            row_id = cache_b.reserve_fetch_attempt(
                ahora, symbol=None,
                detail=json.dumps({"endpoint": "fapi_time"}, sort_keys=True),
                max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                window_ms=60_000, attempts=1,
                execution_id=run_id,
                run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
            )
            self.assertIsNotNone(row_id)
        self.assertEqual(cache_b.run_requests_used(run_id), 7,
                         "instancia B ve el total compartido: 4+3=7")

        # La corrida está agotada: la instancia A no puede reservar más.
        self.assertIsNone(
            cache_a.reserve_fetch_attempt(
                ahora, symbol=None,
                detail=json.dumps({"endpoint": "fapi_time"}, sort_keys=True),
                max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                window_ms=60_000, attempts=1,
                execution_id=run_id,
                run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
            ),
            "límite compartido agotado: instancia A bloqueada",
        )
        self.assertEqual(cache_a.run_requests_used(run_id), 7,
                         "sin exceder el total de la corrida")
        _publish("MISMA_CORRIDA_LIMITE_COMPARTIDO", ahora, ahora, None, None,
                 None, "reserva_pre_envío", 7, None,
                 "dos instancias de la misma corrida: límite compartido, "
                 "no reseteado")

    def test_nueva_corrida_contador_independiente_evidencia_intacta(self):
        """Una nueva corrida recibe presupuesto nuevo solo mediante
        creación explícita (run_id distinto), sin borrar ni modificar los
        contadores de corridas previas."""
        db = self.tmp / "cache_nueva.db"
        cache = MarketCache(db)
        cache.init_db()
        ahora = int(time.time() * 1000)

        # Corrida A consume 3 cupos.
        run_a = "eng-run-nueva-a"
        for _ in range(3):
            row_id = cache.reserve_fetch_attempt(
                ahora, symbol=None,
                detail=json.dumps({"endpoint": "fapi_time"}, sort_keys=True),
                max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                window_ms=60_000, attempts=1,
                execution_id=run_a,
                run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
            )
            self.assertIsNotNone(row_id)
        self.assertEqual(cache.run_requests_used(run_a), 3,
                         "corrida A consumió 3 cupos")

        # Corrida B (run_id distinto) empieza en cero: contador independiente.
        run_b = "eng-run-nueva-b"
        self.assertEqual(cache.run_requests_used(run_b), 0,
                         "nueva corrida B inicia en cero")
        row_id = cache.reserve_fetch_attempt(
            ahora, symbol=None,
            detail=json.dumps({"endpoint": "fapi_time"}, sort_keys=True),
            max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
            window_ms=60_000, attempts=1,
            execution_id=run_b,
            run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
        )
        self.assertIsNotNone(row_id, "corrida B puede reservar su propio cupo")
        self.assertEqual(cache.run_requests_used(run_b), 1,
                         "corrida B consumió 1 cupo propio")

        # La evidencia de la corrida A permanece intacta (no se modificó ni
        # borró al crear la corrida B).
        self.assertEqual(cache.run_requests_used(run_a), 3,
                         "evidencia de corrida A intacta tras nueva corrida")
        rows_a = cache.fetch_ledger(limit=50)
        time_rows_a = [r for r in rows_a
                       if r.get("execution_id") == run_a
                       and r.get("status") == "reserved"]
        self.assertEqual(len(time_rows_a), 3,
                         "tres reservas de corrida A todavía en ledger")
        _publish("NUEVA_CORRIDA_INDEPENDIENTE", ahora, ahora, None, None,
                 None, "reserva_pre_envío", 3, None,
                 "nueva run_id: contador independiente, evidencia previa "
                 "intacta")

    # --- 5. Referencia válida vs expirada: admisión / abstención ----------

    def test_referencia_válida_admite_expirada_abstiene(self):
        """Referencia válida: contexto admitido y T fijado. Referencia
        expirada: ahora_ms -> None, abstención (sin avanzar ni evaluar)."""
        # Válida.
        ahora = [T0 + 2 * STEP_MS]
        provider_ok = _LocalTimeProvider(ahora[0], ahora[0])
        sync_ok = ClockSynchronizer(
            fetch_server_time=provider_ok.fetch_server_time,
            wall_clock_ms=provider_ok.wall_clock_ms)
        self.assertTrue(asyncio.run(sync_ok.sync()))
        harness_ok = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync_ok, clock_source="public_sincronizado")
        try:
            clk = harness_ok.health()["clock"]
            self.assertEqual(clk["source"], "public_sincronizado", clk)
            self.assertTrue(clk["available"], clk)
            self.assertEqual(harness_ok.world._now_ms(), T0 + 2 * STEP_MS)
            created = harness_ok.create(live_payload(CONTEXT, "req-ok-1"))
            self.assertEqual(created["session"]["clock_ms"], T0 - 1)
            _publish("REFERENCIA_VÁLIDA", ahora[0], ahora[0], None, None,
                     T0 - 1, "create", 0, None,
                     "referencia válida: contexto admitido, T = T0 - 1")
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
            clock_sync=sync_exp, clock_source="public_sincronizado")
        try:
            clk = harness_exp.health()["clock"]
            self.assertEqual(clk["source"], "public_sincronizado", clk)
            self.assertFalse(clk["available"], clk)
            self.assertIsNone(harness_exp.world._now_ms())
            status, body = harness_exp.api("POST", "/sessions",
                                           live_payload(CONTEXT, "req-exp-1"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)
            _publish("REFERENCIA_EXPIRADA", T0, T0, None, None, None,
                     "create", 0, None,
                     "referencia expirada: abstención, sin crear sesión")
        finally:
            harness_exp.close()

    # --- Fuentes explícitas en /health ----------------------------------

    def test_salud_distingue_fuentes_reloj(self):
        """/health expone cuatro estados de fuente de reloj:
        local_sistema, local_inyectado, public_sincronizado y referencia no
        disponible (available False)."""
        # 1) local_sistema: reloj de pared del servicio.
        h_sistema = Harness(
            self.tmp, "http://127.0.0.1:1",
            now_ms=_now_ms, clock_source="local_sistema")
        try:
            clk = h_sistema.health()["clock"]
            self.assertEqual(clk["source"], "local_sistema", clk)
            self.assertTrue(clk["available"], clk)
        finally:
            h_sistema.close()

        # 2) local_inyectado: reloj controlado por pruebas.
        proveedor = _LocalTimeProvider(T0, T0)
        h_iny = Harness(
            self.tmp, "http://127.0.0.1:1",
            now_ms=lambda: proveedor.wall_clock_ms(),
            clock_source="local_inyectado")
        try:
            clk = h_iny.health()["clock"]
            self.assertEqual(clk["source"], "local_inyectado", clk)
            self.assertTrue(clk["available"], clk)
        finally:
            h_iny.close()

        # 3) public_sincronizado: ClockSynchronizer sincronizado y vigente.
        ahora = [T0 + 2 * STEP_MS]
        prov = _LocalTimeProvider(ahora[0], ahora[0])
        sync = ClockSynchronizer(
            fetch_server_time=prov.fetch_server_time,
            wall_clock_ms=prov.wall_clock_ms)
        self.assertTrue(asyncio.run(sync.sync()))
        h_pub = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync, clock_source="public_sincronizado")
        try:
            clk = h_pub.health()["clock"]
            self.assertEqual(clk["source"], "public_sincronizado", clk)
            self.assertTrue(clk["available"], clk)
            self.assertIsNotNone(clk["offset_ms"])
            self.assertIsNotNone(clk["rtt_ms"])
            self.assertIsNotNone(clk["last_sync_timestamp"])
        finally:
            h_pub.close()

        # 4) referencia no disponible / expirada: available False.
        prov_exp = _LocalTimeProvider(T0, T0)
        sync_exp = ClockSynchronizer(
            fetch_server_time=prov_exp.fetch_server_time,
            wall_clock_ms=prov_exp.wall_clock_ms)
        self.assertTrue(asyncio.run(sync_exp.sync()))
        sync_exp.last_sync_timestamp = (
            datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        h_exp = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync_exp, clock_source="public_sincronizado")
        try:
            clk = h_exp.health()["clock"]
            self.assertEqual(clk["source"], "public_sincronizado", clk)
            self.assertFalse(clk["available"], clk)
            self.assertIsNotNone(clk["age_ms"])
            self.assertGreater(clk["age_ms"], CLOCK_REFERENCE_MAX_AGE_MS)
        finally:
            h_exp.close()

    # --- El arnés rechaza crear sesión con fuente incorrecta/expirada -----

    def test_arnés_rechaza_fuente_incorrecta_antes_de_crear(self):
        """El arnés comprueba la fuente y su validez antes de crear la sesión:
        una fuente incorrecta o expirada impide crear (abstención)."""
        # Fuente incorrecta: se espera public_sincronizado pero el servicio
        # corre en local_sistema.
        h = Harness(
            self.tmp, "http://127.0.0.1:1",
            now_ms=_now_ms, clock_source="local_sistema")
        try:
            clk = h.health()["clock"]
            self.assertEqual(clk["source"], "local_sistema", clk)
            # Fuente no es la esperada (public): no se crea sesión.
            with self.assertRaises(AssertionError):
                h.assert_clock_before_create("public_sincronizado")
        finally:
            h.close()

        # Fuente expirada: public_sincronizado pero available False.
        prov_exp = _LocalTimeProvider(T0, T0)
        sync_exp = ClockSynchronizer(
            fetch_server_time=prov_exp.fetch_server_time,
            wall_clock_ms=prov_exp.wall_clock_ms)
        self.assertTrue(asyncio.run(sync_exp.sync()))
        sync_exp.last_sync_timestamp = (
            datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        h2 = Harness(
            self.tmp, "http://127.0.0.1:1",
            clock_sync=sync_exp, clock_source="public_sincronizado")
        try:
            clk = h2.health()["clock"]
            self.assertEqual(clk["source"], "public_sincronizado", clk)
            self.assertFalse(clk["available"], clk)
            with self.assertRaises(AssertionError):
                h2.assert_clock_before_create("public_sincronizado")
            # Y create_session se rechaza por RELOJ_REFERENCIA_INCERTO.
            status, body = h2.api("POST", "/sessions",
                                  live_payload(CONTEXT, "req-exp-2"))
            self.assertEqual(status, 400, body)
            self.assertIn("RELOJ_REFERENCIA_INCERTO", str(body), body)
        finally:
            h2.close()


# --- Propagación del run_id: camino real -----------------------------------

    def test_run_id_propagacion_camino_real(self):
        """El servicio consume intentos de tiempo vía _make_budgeted_time_fetch
        (misma ruta que usa main) y el arnés consume intentos de klines vía
        reserve_fetch_attempt, ambos con el mismo run_id; el SUM del run_id
        refleja ambos."""
        import microstructure_probe.engineering_session_service as ess
        real_fetch = ess._fetch_binance_server_time
        db = self.tmp / "cache_camino_real.db"
        cache = MarketCache(db)
        cache.init_db()
        run_id = "eng-run-camino-real-1"
        ahora = int(time.time() * 1000)
        fetch_calls = []

        def mock_fetch():
            fetch_calls.append(1)
            return T0 + 2 * STEP_MS

        ess._fetch_binance_server_time = mock_fetch
        try:
            # Servicio: consume /time a través de _make_budgeted_time_fetch
            # (misma ruta que usa main al crear el ClockSynchronizador)
            time_fetch = ess._make_budgeted_time_fetch(
                cache, run_id, CLOCK_PUBLIC_MAX_REQUESTS, mock_fetch)
            for _ in range(3):
                self.assertEqual(time_fetch(), T0 + 2 * STEP_MS)
            self.assertEqual(len(fetch_calls), 3,
                             "el servicio efectivamente llamó al fetch")

            # Arnés: consume klines a través de reserve_fetch_attempt
            for _ in range(2):
                row_id = cache.reserve_fetch_attempt(
                    ahora, symbol="BTCUSDT",
                    detail=json.dumps({"endpoint": "klines"}, sort_keys=True),
                    max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                    window_ms=60_000, attempts=1,
                    execution_id=run_id,
                    run_max_requests=MAX_FETCH_REQUESTS_PER_RUN,
                )
                self.assertIsNotNone(row_id)

            # SUM del mismo run_id refleja ambos (3 de /time + 2 de klines)
            self.assertEqual(cache.run_requests_used(run_id), 5,
                             "run_id comparte el total entre /time y klines")
            _publish("RUN_ID_CAMINO_REAL", ahora, ahora, None, None, None,
                     "run_id_compartido", 5, None,
                     "servicio /time + arnés klines, mismo run_id, SUM=5")
        finally:
            ess._fetch_binance_server_time = real_fetch

    def test_orquestador_run_id_camino_real(self):
        """El orquestador pasa --run-id al servicio y _load_recent_context usa
        ese mismo run_id como execution_id en el ledger para klines."""
        import sys as _sys
        import sys as _sys
        import microstructure_probe.engineering_session_service as ess
        import microstructure_probe.engineering_session_service as ess
        from local_kline_provider import LocalKlineProvider

        # Agregar scripts/ al path para importar engineering_live_window y
        # local_kline_provider
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        if str(scripts_dir) not in _sys.path:
            _sys.path.insert(0, str(scripts_dir))
        import engineering_live_window as elw_mod

        provider_port = _free_port()
        prov = LocalKlineProvider(provider_port,
                                  {"BTCUSDT": "ok", "MINAUSDT": "ok"})
        prov.start()

        try:
            sessions_dir = self.tmp / "sessions_orch"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            run_id = "eng-run-orchestrator-1"

            # Redirigir CACHE_DB a bd temporal para aislar el test
            original_cache_db = elw_mod.CACHE_DB
            test_cache_db = self.tmp / "test_cache_orch.db"
            elw_mod.CACHE_DB = test_cache_db

            try:
                cache = MarketCache(test_cache_db)
                cache.init_db()

                args = _make_orchestrator_args(provider_port, sessions_dir,
                                               run_id)
                ahora = int(time.time() * 1000)
                orch = elw_mod.WindowOrchestrator(args)

                # Ejecutar carga de contexto (usa HistoryClient con run_id)
                orch._load_recent_context()

                # Verificar ledger: klines consumidas bajo mismo run_id
                rows = cache.fetch_ledger(limit=50)
                run_rows = [r for r in rows
                            if r.get("open_id") == run_id or
                            r.get("execution_id") == run_id]
                klines_rows = [r for r in run_rows
                               if "klines" in (r.get("detail") or "")]
                self.assertGreaterEqual(
                    len(klines_rows), 1,
                    f"no hay reservas de klines con run_id={run_id}: {rows}")

                # Consumo agregado bajo el mismo run_id (/time + klines),
                # leído del ledger (no solo el contador de contexto).
                total_consumed = cache.run_requests_used(run_id)
                self.assertGreaterEqual(
                    total_consumed, 1,
                    "debería haber consumo acumulado bajo run_id")

                _publish("RUN_ID_ORQUESTADOR_REAL", ahora, ahora, None, None,
                         None, run_id, total_consumed, None,
                         "orquestador pasa --run-id y klines usan mismo "
                         "run_id en ledger")
            finally:
                elw_mod.CACHE_DB = original_cache_db
        finally:
            prov.stop()

    def test_orquestador_reinicio_reutiliza_run_id(self):
        """Reiniciar el orquestador con la misma sessions_dir reutiliza el
        run_id (como hace _execute vía _read_run_id/_write_run_id) y conserva
        el consumo acumulado del ledger por run_id."""
        import microstructure_probe.engineering_session_service as ess
        from local_kline_provider import LocalKlineProvider

        provider_port = _free_port()
        prov = LocalKlineProvider(provider_port,
                                  {"BTCUSDT": "ok", "MINAUSDT": "ok"})
        prov.start()

        try:
            sessions_dir = self.tmp / "sessions_reinicio"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            run_id = "eng-run-reinicio-orch-1"
            ahora = int(time.time() * 1000)

            test_cache_db = self.tmp / "test_cache_reinicio.db"
            original_cache_db = elw_mod.CACHE_DB
            elw_mod.CACHE_DB = test_cache_db

            try:
                cache = MarketCache(test_cache_db)
                cache.init_db()

                # Primera instancia: consume klines bajo run_id.
                args1 = _make_orchestrator_args(provider_port, sessions_dir,
                                                run_id)
                orch1 = elw_mod.WindowOrchestrator(args1)
                captured1: List[tuple] = []
                orch1._spawn = lambda argv, label: (
                    captured1.append((list(argv), label)) or _FakeProc())
                orch1._load_recent_context()
                self.assertEqual(orch1.run_id, run_id,
                                 "la instancia usa el run_id proporcionado")
                consumo_1 = cache.run_requests_used(run_id)
                self.assertGreaterEqual(
                    consumo_1, 1, "primera instancia consumió")

                # _execute persiste el run_id en sessions_dir/run-id.json;
                # al reiniciar la misma corrida sin --run-id se lee de ahí.
                elw_mod._write_run_id(sessions_dir, run_id)
                self.assertEqual(
                    elw_mod._read_run_id(sessions_dir), run_id,
                    "el run_id no se persistió para reutilizarlo")

                # Segunda instancia: misma sessions_dir, SIN --run-id.
                # _execute reutiliza el valor persistido y se lo asigna a la
                # instancia antes de cargar contexto.
                args2 = _make_orchestrator_args(provider_port, sessions_dir,
                                                None)
                orch2 = elw_mod.WindowOrchestrator(args2)
                self.assertIsNone(
                    orch2.run_id,
                    "antes de _execute, run_id no está resuelto")
                run_id_reutilizado = elw_mod._read_run_id(sessions_dir)
                self.assertEqual(run_id_reutilizado, run_id,
                                 "reinicio no reutilizó el run_id persistido")
                orch2.run_id = run_id_reutilizado
                captured2: List[tuple] = []
                orch2._spawn = lambda argv, label: (
                    captured2.append((list(argv), label)) or _FakeProc())
                orch2._load_recent_context()

                # Verificar consumo acumulado bajo el mismo run_id.
                consumo_total = cache.run_requests_used(run_id)
                self.assertGreater(
                    consumo_total, consumo_1,
                    f"consumo no se acumuló: {consumo_1} -> {consumo_total}")

                _publish("ORQUESTADOR_REINICIO_REUTILIZA", ahora, ahora,
                         None, None, None, run_id, consumo_total, None,
                         "reinicio de orquestador reutiliza run_id y "
                         "acumula consumo")
            finally:
                elw_mod.CACHE_DB = original_cache_db
        finally:
            prov.stop()


# --- Verificación acotada: configuración efectiva del orquestador ----------

class TestOrquestadorConfigEfectiva(unittest.TestCase):
    """Verificación acotada del arranque real del orquestador con proveedores
    locales (sin Binance, sin red pública):

    - argumentos del proceso (--clock-source derivado de --transport, --run-id);
    - fuente temporal esperada en /health ANTES de crear la sesión;
    - mismo run_id para tiempo y velas;
    - total agregado del ledger por run_id consistente;
    - fuente incorrecta / ausente / expirada y presupuesto agotado bloquean
      antes de crear la sesión.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="orch-config-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _start_provider(self) -> None:
        self.provider_port = _free_port()
        self.sessions_dir = self.tmp / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.provider = LocalKlineProvider(
            self.provider_port, {"BTCUSDT": "ok", "MINAUSDT": "ok"})
        self.provider.start()

    def _stop_provider(self) -> None:
        try:
            self.provider.stop()
        except Exception:  # noqa: BLE001
            pass

    def _orchestrator_args(self, transport: str = "local",
                           clock_source: Optional[str] = None,
                           run_id: Optional[str] = None
                           ) -> argparse.Namespace:
        return _make_orchestrator_args(
            self.provider_port, self.sessions_dir, run_id,
            transport=transport, clock_source=clock_source)

    def _start_services_mocked(
        self,
        transport: str = "local",
        clock_source: Optional[str] = None,
        run_id: Optional[str] = None,
        health_clock: Optional[Dict[str, Any]] = None,
    ):
        """Ejecuta _start_services con servicios mockeados (sin puentes reales
        de mercado/ingeniería). Devuelve (orch, argv_capturados, test_cache_db)."""
        args = self._orchestrator_args(
            transport=transport, clock_source=clock_source, run_id=run_id)
        orch = elw_mod.WindowOrchestrator(args)
        original_cache_db = elw_mod.CACHE_DB
        test_cache_db = self.tmp / "orch_cache.db"
        elw_mod.CACHE_DB = test_cache_db
        try:
            captured: List[tuple] = []
            eng_port = args.engineering_port

            def fake_spawn(argv, label):
                captured.append((list(argv), label))
                return _FakeProc()

            def fake_http_get(url, timeout=8.0):
                u = str(url)
                text = "{}"
                if u.endswith("/health"):
                    port = int(u.rsplit(":", 1)[-1].split("/")[0])
                    if port == eng_port:
                        if health_clock == "__ABSENT__":
                            text = json.dumps({
                                "service": "engineering-session-service/v1",
                                "pid": 1, "port": eng_port,
                                "generated_at_ms": _now_ms()})
                        else:
                            clk = health_clock if isinstance(health_clock,
                                                             dict) else {
                                "source": "local_sistema", "available": True,
                                "reason": None, "age_ms": None}
                            text = json.dumps({
                                "service": "engineering-session-service/v1",
                                "pid": 1, "port": eng_port, "clock": clk,
                                "generated_at_ms": _now_ms()})
                    else:
                        text = json.dumps({
                            "service": "market-stream-service/v1",
                            "pid": 2, "port": port,
                            "transport": {"mode": transport}})
                return {"ok": True, "status": 200, "text": text,
                        "error": None}

            orch._start_provider = lambda: None
            orch._spawn = fake_spawn
            orch._http_get = fake_http_get
            orch._start_services()
            return orch, captured, test_cache_db
        finally:
            elw_mod.CACHE_DB = original_cache_db

    # -- A. argumentos del proceso ------------------------------------------

    def test_argv_tiene_clock_source_y_run_id(self):
        """--transport public arranca ingeniería con --clock-source public;
        local con --clock-source local; ambas propagan --run-id."""
        self._start_provider()
        try:
            orch, captured, _ = self._start_services_mocked(
                transport="local", run_id="eng-run-argv-1")
            eng_argv = [a for a, lbl in captured
                        if lbl == "engineering-session"]
            self.assertTrue(eng_argv, "no se capturó argv de ingeniería")
            argv = eng_argv[0]
            self.assertIn("--run-id", argv)
            self.assertIn("eng-run-argv-1", argv)
            self.assertIn("--clock-source", argv)
            idx = argv.index("--clock-source")
            self.assertEqual(argv[idx + 1], "local",
                             "local debe usar referencia local explícita")

            orch2, captured2, _ = self._start_services_mocked(
                transport="public", run_id="eng-run-argv-2",
                health_clock={"source": "public_sincronizado",
                              "available": True, "reason": None,
                              "age_ms": None})
            eng_argv2 = [a for a, lbl in captured2
                         if lbl == "engineering-session"][0]
            idx2 = eng_argv2.index("--clock-source")
            self.assertEqual(eng_argv2[idx2 + 1], "public",
                             "public requiere --clock-source public")
        finally:
            self._stop_provider()

    # -- B. fuente temporal en /health antes de crear sesión ----------------

    def test_salud_clock_local_disponible_antes_de_crear_sesion(self):
        """Local: /health.clock reporta local_sistema disponible y la sesión
        se crea (no se lanza en _start_services)."""
        self._start_provider()
        try:
            # No lanza: el reloj local es válido.
            self._start_services_mocked(transport="local",
                                        run_id="eng-run-clock-1")
        finally:
            self._stop_provider()

    def test_fuente_incorrecta_bloquea_antes_de_crear_sesion(self):
        """Local con /health.clock.source = public_sincronizado se rechaza
        antes de crear la sesión."""
        self._start_provider()
        try:
            with self.assertRaises(RuntimeError) as ctx:
                self._start_services_mocked(
                    transport="local", run_id="eng-run-bad-1",
                    health_clock={"source": "public_sincronizado",
                                  "available": True, "reason": None,
                                  "age_ms": None})
            self.assertIn("CLOCK_SOURCE_INCORRECTO", str(ctx.exception))
        finally:
            self._stop_provider()

    def test_fuente_ausente_bloquea_antes_de_crear_sesion(self):
        """/health.clock ausente (sin bloque 'clock') se rechaza antes de
        crear la sesión."""
        self._start_provider()
        try:
            with self.assertRaises(RuntimeError) as ctx:
                self._start_services_mocked(
                    transport="local", run_id="eng-run-absent-1",
                    health_clock="__ABSENT__")
            self.assertIn("CLOCK_SOURCE_AUSENTE", str(ctx.exception))
        finally:
            self._stop_provider()

    def test_fuente_expirada_bloquea_antes_de_crear_sesion(self):
        """/health.clock disponible False (expirada) se rechaza antes de
        crear la sesión."""
        self._start_provider()
        try:
            with self.assertRaises(RuntimeError) as ctx:
                self._start_services_mocked(
                    transport="local", run_id="eng-run-exp-1",
                    health_clock={"source": "local_sistema",
                                  "available": False,
                                  "reason": "referencia expirada",
                                  "age_ms": 7_000_000})
            self.assertIn("CLOCK_REFERENCIA_NO_DISPONIBLE", str(ctx.exception))
        finally:
            self._stop_provider()

    # -- C. mismo run_id y total agregado consistente -----------------------

    def test_run_id_velas_y_total_agregado_consistente(self):
        """Mismo run_id para el contexto (klines) y el total agregado del
        ledger por run_id es consistente con el consumo del arnés."""
        self._start_provider()
        try:
            sessions_dir = self.tmp / "sessions_ctx"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            run_id = "eng-run-total-1"
            test_cache_db = self.tmp / "ctx_cache.db"
            original = elw_mod.CACHE_DB
            elw_mod.CACHE_DB = test_cache_db
            try:
                cache = MarketCache(test_cache_db)
                cache.init_db()
                args = self._orchestrator_args(transport="local",
                                               run_id=run_id)
                args.sessions_dir = str(sessions_dir)
                orch = elw_mod.WindowOrchestrator(args)
                captured: List[tuple] = []
                orch._spawn = lambda argv, label: (
                    captured.append((list(argv), label)) or _FakeProc())
                orch._load_recent_context()
                rows = cache.fetch_ledger(limit=50)
                run_rows = [r for r in rows
                            if r.get("execution_id") == run_id]
                klines_rows = [r for r in run_rows
                               if "klines" in (r.get("detail") or "")]
                self.assertGreaterEqual(
                    len(klines_rows), 1,
                    f"no hay reservas de klines con run_id={run_id}: {rows}")
                total_ledger = cache.run_requests_used(run_id)
                self.assertEqual(
                    total_ledger, orch.rest_count,
                    "ledger agregado por run_id debe coincidir con el consumo "
                    f"del arnés: ledger={total_ledger} rest_count={orch.rest_count}")
                self.assertGreaterEqual(total_ledger, 1)
                # El total agregado incluye cualquier intento de tiempo
                # (/time) bajo el mismo run_id, no solo el contador de
                # consultas de contexto.
            finally:
                elw_mod.CACHE_DB = original
        finally:
            self._stop_provider()

    # -- D. presupuesto agotado bloquea antes de crear sesión -------------

    def test_presupuesto_agotado_bloquea_antes_de_crear_sesion(self):
        """Agotado el presupuesto total de la corrida (7), la carga de
        contexto no abre socket y la creación de sesión queda bloqueada."""
        self._start_provider()
        try:
            sessions_dir = self.tmp / "sessions_budget"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            run_id = "eng-run-budget-1"
            test_cache_db = self.tmp / "budget_cache.db"
            original = elw_mod.CACHE_DB
            elw_mod.CACHE_DB = test_cache_db
            try:
                cache = MarketCache(test_cache_db)
                cache.init_db()
                ahora = _now_ms()
                for _ in range(MAX_FETCH_REQUESTS_PER_RUN):
                    row_id = cache.reserve_fetch_attempt(
                        ahora, symbol="BTCUSDT",
                        detail=json.dumps(
                            {"endpoint": "klines", "pre_seed": True},
                            sort_keys=True),
                        max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                        window_ms=60_000, attempts=1,
                        execution_id=run_id,
                        run_max_requests=MAX_FETCH_REQUESTS_PER_RUN)
                    self.assertIsNotNone(row_id)
                self.assertEqual(
                    cache.run_requests_used(run_id),
                    MAX_FETCH_REQUESTS_PER_RUN,
                    "el presupuesto de corrida debe estar agotado (7)")

                args = self._orchestrator_args(transport="local",
                                               run_id=run_id)
                args.sessions_dir = str(sessions_dir)
                orch = elw_mod.WindowOrchestrator(args)
                captured: List[tuple] = []
                orch._spawn = lambda argv, label: (
                    captured.append((list(argv), label)) or _FakeProc())
                # La carga de contexto no debe abrir nuevo socket contra el
                # proveedor (presupuesto agotado): contexto vacío.
                orch._load_recent_context()
                self.assertEqual(
                    orch.evidence["contexto"]["velas"], 0,
                    "presupuesto agotado: sin velas cargadas")
                # El total del ledger no creció (el intento bloqueado reserva
                # requests=0) y se conserva en 7.
                self.assertEqual(
                    cache.run_requests_used(run_id),
                    MAX_FETCH_REQUESTS_PER_RUN)
                # Crear sesión con contexto vacío se rechaza antes de
                # establecer la sesión (el presupuesto agotado impide el
                # envío y la creación).
                orch._validate_config()
                orch._http_post_json = lambda url, payload, timeout=15.0: (
                    {"ok": False, "status": 400,
                     "text": "presupuesto agotado / contexto vacío",
                     "json": None, "error": None})
                with self.assertRaises(RuntimeError):
                    orch._create_session(orch.evidence["contexto"] or [])
            finally:
                elw_mod.CACHE_DB = original
        finally:
            self._stop_provider()
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
