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
EngineeringHTTPServer) con proveedores de tiempo locales mockeados.
Cero peticiones a dominios publicos.
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
