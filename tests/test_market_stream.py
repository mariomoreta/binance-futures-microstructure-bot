"""Pruebas de ``market-stream/v1`` con transporte y REST simulados.

Sin red y sin Binance: el hub recibe JSON como lo haria el socket y la
reparacion REST se inyecta como funcion async. Cubre los casos A-I del bloque:

A. snapshot + novedades concurrentes (sin huecos ni duplicados)
B. provisional -> cierre -> vela nueva
C. cambio rapido de simbolo/intervalo sin contaminacion
D. mensajes atrasados, duplicados e invalidos
E. desconexion -> obsolescencia -> estado honesto
F. reconexion con hueco y reparacion completa/parcial/fallida
G. dos consumidores y liberacion de uno
H. recarga sin suscripciones duplicadas
I. servicio detenido: historico visible, sin falso LIVE

Ademas: URL/backoff del transporte, frames de control y endpoints HTTP/SSE en
loopback con puerto efimero.
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from microstructure_probe import market_stream_service as service_mod  # noqa: E402
from microstructure_probe.market_cache import MarketCache  # noqa: E402
from microstructure_probe.market_stream import (  # noqa: E402
    FRESH_MS,
    STALE_MS,
    BinanceKlineTransport,
    KlineStreamHub,
    normalize_kline,
)
from microstructure_probe.market_stream_service import (  # noqa: E402
    MarketStreamService,
)

T0 = 1_700_000_000_000
STEP = 60_000


class Clock:
    """Reloj inyectable (ms) para frescura determinista."""

    def __init__(self, start_ms: int = T0) -> None:
        self.ms = int(start_ms)

    def __call__(self) -> float:
        return self.ms / 1000.0

    def advance(self, ms: int) -> None:
        self.ms += int(ms)


def kline(
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    open_ms: int = T0,
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 12.5,
    quote: float = 1250.0,
    trades: int = 7,
    closed: bool = False,
    event_ms: int | None = None,
) -> str:
    step = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
            "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}[interval]
    payload = {
        "stream": f"{symbol.lower()}@kline_{interval}",
        "data": {
            "e": "kline", "E": int(event_ms if event_ms is not None else open_ms + 1000),
            "s": symbol,
            "k": {
                "t": int(open_ms), "T": int(open_ms) + step - 1, "s": symbol,
                "i": interval, "o": str(open_), "c": str(close),
                "h": str(high), "l": str(low), "v": str(volume),
                "q": str(quote), "n": trades, "x": bool(closed),
            },
        },
    }
    return json.dumps(payload)


def drain(consumer) -> list[tuple[str, dict]]:
    items = []
    while not consumer.queue.empty():
        item = consumer.queue.get_nowait()
        if item is not None:
            items.append(item)
    return items


def events_of(consumer, name: str) -> list[dict]:
    return [payload for event, payload in drain(consumer) if event == name]


async def _pump(times: int = 5) -> None:
    for _ in range(times):
        await asyncio.sleep(0)


class HubContractTests(unittest.TestCase):
    """Normalizacion pura: nada se inventa."""

    def test_normalize_rejects_missing_ohlc_and_bad_identity(self):
        good = json.loads(kline())
        candle, error = normalize_kline(good["data"], T0)
        self.assertIsNone(error)
        assert candle is not None
        self.assertEqual(candle["symbol"], "BTCUSDT")
        self.assertEqual(candle["interval"], "1m")
        self.assertFalse(candle["closed"])
        self.assertIsNone(candle["close_time_ms"])
        self.assertEqual(candle["base_volume"], 12.5)
        self.assertEqual(candle["quote_volume"], 1250.0)
        self.assertEqual(candle["trade_count"], 7)

        broken = json.loads(kline())
        del broken["data"]["k"]["h"]
        candle, error = normalize_kline(broken["data"], T0)
        self.assertIsNone(candle)
        self.assertEqual(error, "invalid")

        wrong_interval = json.loads(kline())
        wrong_interval["data"]["k"]["i"] = "17m"
        candle, error = normalize_kline(wrong_interval["data"], T0)
        self.assertIsNone(candle)
        self.assertEqual(error, "identity_mismatch")

        not_kline = {"e": "aggTrade", "s": "BTCUSDT"}
        candle, error = normalize_kline(not_kline, T0)
        self.assertIsNone(candle)
        self.assertEqual(error, "unrouted")

    def test_volume_absent_is_null_not_zero(self):
        payload = json.loads(kline())
        payload["data"]["k"].pop("v")
        payload["data"]["k"].pop("q")
        candle, error = normalize_kline(payload["data"], T0)
        self.assertIsNone(error)
        assert candle is not None
        self.assertIsNone(candle["base_volume"])
        self.assertIsNone(candle["quote_volume"])

    def test_closed_candle_exposes_close_time(self):
        payload = json.loads(kline(closed=True))
        candle, error = normalize_kline(payload["data"], T0)
        self.assertIsNone(error)
        assert candle is not None
        self.assertTrue(candle["closed"])
        self.assertEqual(candle["close_time_ms"], T0 + STEP - 1)


class SnapshotReconciliationTests(unittest.TestCase):
    """A. snapshot + novedades concurrentes sin huecos ni duplicados."""

    def test_buffered_updates_flush_after_snapshot_in_order(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        consumer, error = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
        self.assertIsNone(error)
        assert consumer is not None
        self.assertIsNone(consumer.deliver_from_ms)

        # Llegan novedades mientras el consumidor hace su snapshot.
        self.assertEqual(hub.on_message(kline(open_ms=T0, close=100.9)), "applied")
        self.assertEqual(hub.on_message(kline(open_ms=T0 + STEP, closed=True)), "closed")
        self.assertEqual(hub.on_message(kline(open_ms=T0 + 2 * STEP, close=101.5)), "applied")
        self.assertEqual(drain(consumer), [])

        # Snapshot termino en la vela T0 (provisional en el almacen).
        hub.ready(consumer, T0)
        items = drain(consumer)
        names = [event for event, _ in items]
        self.assertEqual(names, ["candle", "closed", "candle"])
        opens = [payload["open_time_ms"] for _, payload in items]
        self.assertEqual(opens, [T0, T0 + STEP, T0 + 2 * STEP])
        self.assertTrue(items[1][1]["closed"])
        self.assertEqual(consumer.deliver_from_ms, T0)

    def test_snapshot_gap_is_declared_when_buffer_overflows(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        consumer, error = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
        self.assertIsNone(error)
        assert consumer is not None
        from microstructure_probe import market_stream as MS

        original = MS.PENDING_MAX
        MS.PENDING_MAX = 2
        try:
            for index in range(4):
                hub.on_message(kline(open_ms=T0 + index * STEP))
        finally:
            MS.PENDING_MAX = original
        hub.ready(consumer, T0)
        items = drain(consumer)
        names = [event for event, _ in items]
        self.assertIn("gap", names)
        gap = [p for e, p in items if e == "gap"][0]
        self.assertEqual(gap["reason"], "BUFFER_OVERFLOW")
        self.assertEqual(gap["status"], "partial")

    def test_snapshot_without_coverage_delivers_everything_buffered(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
        assert consumer is not None
        hub.on_message(kline(open_ms=T0))
        hub.ready(consumer, None)
        items = drain(consumer)
        self.assertEqual([e for e, _ in items], ["candle"])
        self.assertEqual(consumer.deliver_from_ms, 0)


class CandleLifecycleTests(unittest.TestCase):
    """B. provisional -> cierre -> vela nueva; sin reabrir cerradas."""

    def test_provisional_then_closed_then_next(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
        assert consumer is not None
        hub.ready(consumer, 0)

        self.assertEqual(hub.on_message(kline(open_ms=T0, close=100.2)), "applied")
        self.assertEqual(hub.on_message(kline(open_ms=T0, close=100.8, volume=20.0)), "applied")
        self.assertEqual(hub.on_message(kline(open_ms=T0, close=101.0, volume=21.0, closed=True)), "closed")
        # Reapertura de una vela ya cerrada: se descarta como atrasada.
        self.assertEqual(hub.on_message(kline(open_ms=T0, close=999.0)), "late")
        self.assertEqual(hub.on_message(kline(open_ms=T0 + STEP, close=102.0)), "applied")

        items = drain(consumer)
        candles = [(e, p) for e, p in items if e in {"candle", "closed"}]
        names = [e for e, _ in candles]
        # Dos provisionales distintas + cierre + siguiente provisional.
        self.assertEqual(names, ["candle", "candle", "closed", "candle"])
        closed_payload = candles[2][1]
        self.assertTrue(closed_payload["closed"])
        self.assertEqual(closed_payload["close_time_ms"], T0 + STEP - 1)
        self.assertEqual(closed_payload["base_volume"], 21.0)
        self.assertEqual(candles[3][1]["open_time_ms"], T0 + STEP)
        sub = hub.subs[("BTCUSDT", "1m")]
        self.assertEqual(sub.closed_through_ms, T0 + STEP)
        self.assertEqual(sub.counters["late"], 1)

    def test_identical_provisional_is_duplicate(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
        assert consumer is not None
        hub.ready(consumer, 0)
        message = kline(open_ms=T0)
        self.assertEqual(hub.on_message(message), "applied")
        self.assertEqual(hub.on_message(message), "duplicate")
        items = [e for e, _ in drain(consumer) if e == "candle"]
        self.assertEqual(items, ["candle"])


class IdentityIsolationTests(unittest.TestCase):
    """C. cambio de simbolo/intervalo sin contaminacion."""

    def test_two_streams_do_not_mix(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        btc, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="btc")
        eth, _ = hub.subscribe("ETHUSDT", "1m", consumer_id="eth")
        assert btc is not None and eth is not None
        hub.ready(btc, 0)
        hub.ready(eth, 0)

        hub.on_message(kline(symbol="BTCUSDT", open_ms=T0, close=100.0))
        self.assertEqual([e for e, _ in drain(btc)], ["candle", "status"])
        self.assertEqual(drain(eth), [])

        hub.on_message(kline(symbol="ETHUSDT", open_ms=T0, close=2000.0))
        eth_items = drain(eth)
        self.assertEqual([e for e, _ in eth_items if e == "candle"], ["candle"])
        self.assertEqual(eth_items[0][1]["close"], 2000.0)
        self.assertEqual(drain(btc), [])

        hub.unsubscribe(btc)
        self.assertEqual(hub.desired_streams(), ["ethusdt@kline_1m"])
        self.assertEqual(hub.on_message(kline(symbol="BTCUSDT", open_ms=T0 + STEP)), "unrouted")
        self.assertEqual(len(hub.subs), 2)  # la inactiva espera gracia

    def test_interval_change_keeps_separate_state(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        m1, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="m1")
        h1, _ = hub.subscribe("BTCUSDT", "1h", consumer_id="h1")
        assert m1 is not None and h1 is not None
        hub.ready(m1, 0)
        hub.ready(h1, 0)
        hub.on_message(kline(interval="1h", open_ms=T0, close=101.0))
        self.assertEqual([e for e, _ in drain(h1) if e in {"candle", "closed"}], ["candle"])
        self.assertEqual([e for e, _ in drain(m1) if e in {"candle", "closed"}], [])
        self.assertEqual(sorted(hub.desired_streams()),
                         ["btcusdt@kline_1h", "btcusdt@kline_1m"])

    def test_late_identity_mismatch_is_rejected(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
        assert consumer is not None
        hub.ready(consumer, 0)
        wrong = json.loads(kline(open_ms=T0))
        wrong["stream"] = "ethusdt@kline_1m"
        result = hub.on_message(json.dumps(wrong))
        self.assertIn(result, {"unrouted", "identity_mismatch", "invalid"})
        self.assertEqual([e for e, _ in drain(consumer) if e == "candle"], [])


class BadMessageTests(unittest.TestCase):
    """D. atrasados, duplicados, fuera de orden e invalidos."""

    def test_counters_and_no_fabrication(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
        assert consumer is not None
        hub.ready(consumer, 0)
        sub = hub.subs[("BTCUSDT", "1m")]

        self.assertEqual(hub.on_message("not-json"), "invalid")
        self.assertEqual(sub.counters["invalid"], 1)

        broken = json.loads(kline(open_ms=T0))
        del broken["data"]["k"]["c"]
        self.assertEqual(hub.on_message(json.dumps(broken)), "invalid")
        self.assertEqual(sub.counters["invalid"], 2)

        self.assertEqual(hub.on_message(kline(open_ms=T0, event_ms=T0 + 5000)), "applied")
        self.assertEqual(hub.on_message(kline(open_ms=T0, event_ms=T0 + 4000)), "out_of_order")
        self.assertEqual(sub.counters["out_of_order"], 1)

        self.assertEqual(hub.on_message(kline(open_ms=T0, event_ms=T0 + 6000, closed=True)), "closed")
        self.assertEqual(hub.on_message(kline(open_ms=T0 - STEP, event_ms=T0 + 7000)), "late")
        self.assertEqual(sub.counters["late"], 1)

        self.assertEqual(hub.on_message(kline(open_ms=T0 + 5 * STEP, closed=True)), "closed")
        candles = [p for e, p in drain(consumer) if e in {"candle", "closed"}]
        # provisional T0, cierre T0 y cierre adelantado: la reapertura se descarto.
        self.assertEqual([p["open_time_ms"] for p in candles],
                         [T0, T0, T0 + 5 * STEP])
        self.assertEqual([p["closed"] for p in candles], [False, True, True])
        # El hueco entre T0 y T0+5*STEP se declara, no se rellena.
        self.assertGreaterEqual(sub.counters["gaps"], 1)


class FreshnessTests(unittest.TestCase):
    """E/I. desconexion, obsolescencia y LIVE honesto."""

    def test_live_requires_socket_and_fresh_identity(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
        assert consumer is not None
        hub.ready(consumer, 0)

        state, age, live = hub.state_for(hub.subs[("BTCUSDT", "1m")])
        self.assertEqual(state, "CONNECTING")
        self.assertIsNone(age)
        self.assertFalse(live)

        # Socket abierto sin mensajes: sigue sin ser LIVE.
        hub.on_socket_open()
        state, _, live = hub.state_for(hub.subs[("BTCUSDT", "1m")])
        self.assertEqual(state, "CONNECTING")
        self.assertFalse(live)

        hub.on_message(kline(open_ms=T0))
        state, age, live = hub.state_for(hub.subs[("BTCUSDT", "1m")])
        self.assertEqual(state, "RECEIVING")
        self.assertEqual(age, 0)
        self.assertTrue(live)

        clock.advance(FRESH_MS + 1)
        state, _, live = hub.state_for(hub.subs[("BTCUSDT", "1m")])
        self.assertEqual(state, "STALE")
        self.assertFalse(live)

        clock.advance(STALE_MS)
        state, _, live = hub.state_for(hub.subs[("BTCUSDT", "1m")])
        self.assertEqual(state, "DISCONNECTED")
        self.assertFalse(live)

    def test_socket_loss_is_disconnected_even_if_recent(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
        assert consumer is not None
        hub.ready(consumer, 0)
        hub.on_socket_open()
        hub.on_message(kline(open_ms=T0))
        self.assertTrue(hub.state_for(hub.subs[("BTCUSDT", "1m")])[2])
        hub.on_socket_closed("ConnectionResetError: boom")
        state, _, live = hub.state_for(hub.subs[("BTCUSDT", "1m")])
        self.assertEqual(state, "DISCONNECTED")
        self.assertFalse(live)
        statuses = [p for e, p in drain(consumer) if e == "status"]
        self.assertTrue(statuses)
        self.assertFalse(statuses[-1]["live"])
        self.assertEqual(hub.health()["socket"]["last_error"], "ConnectionResetError: boom")

    def test_health_reports_no_persistence(self):
        hub = KlineStreamHub(clock=Clock())
        consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
        assert consumer is not None
        hub.ready(consumer, 0)
        hub.on_socket_open()
        hub.on_message(kline(open_ms=T0))
        health = hub.health()
        self.assertEqual(health["limits"]["persistence"], "MEMORY_ONLY")
        self.assertEqual(health["contract_version"], "market-stream/v1")
        self.assertEqual(len(health["streams"]), 1)
        self.assertTrue(health["streams"][0]["live"])
        self.assertEqual(health["streams"][0]["ring"], 0)


class RecoveryTests(unittest.TestCase):
    """F. reconexion con hueco y reparacion completa/parcial/fallida."""

    def _candle(self, open_ms: int, close: float) -> dict:
        return {
            "open_time_ms": open_ms,
            "close_time_ms": open_ms + STEP - 1,
            "open": close - 1, "high": close + 1, "low": close - 2, "close": close,
            "base_volume": 5.0, "quote_volume": 500.0, "trade_count": 3,
        }

    def test_gap_is_repaired_and_declared_complete(self):
        clock = Clock()

        async def recovery(symbol, interval, start_ms, end_ms):
            return {"status": "complete", "requests": 1, "missing": [],
                    "candles": [self._candle(start_ms, 100.0),
                                self._candle(start_ms + STEP, 101.0)]}

        async def scenario():
            hub = KlineStreamHub(clock=clock, recovery=recovery)
            consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
            assert consumer is not None
            hub.ready(consumer, 0)
            hub.on_message(kline(open_ms=T0, closed=True))
            # Salto: se cierran T0 y T0+3*STEP, faltan T0+STEP y T0+2*STEP.
            hub.on_message(kline(open_ms=T0 + 3 * STEP, closed=True))
            await _pump(20)
            sub = hub.subs[("BTCUSDT", "1m")]
            self.assertFalse(sub.recovering)
            self.assertEqual(sub.counters["gaps"], 1)
            self.assertEqual(sub.counters["recoveries"], 1)
            self.assertEqual(sub.counters["gap_recovered_bars"], 2)
            self.assertEqual(sub.closed_through_ms, T0 + 4 * STEP)
            items = drain(consumer)
            gaps = [p for e, p in items if e == "gap"]
            self.assertEqual([g["status"] for g in gaps], ["detected", "complete"])
            closed = [p for e, p in items if e == "closed"]
            self.assertIn(T0 + STEP, [p["open_time_ms"] for p in closed])
            self.assertIn(T0 + 2 * STEP, [p["open_time_ms"] for p in closed])
            self.assertEqual(gaps[-1]["requests"], 1)

        asyncio.run(scenario())

    def test_partial_recovery_is_not_hidden(self):
        clock = Clock()

        async def recovery(symbol, interval, start_ms, end_ms):
            return {"status": "partial", "requests": 2,
                    "missing": [[start_ms + STEP, end_ms]],
                    "candles": [self._candle(start_ms, 100.0)]}

        async def scenario():
            hub = KlineStreamHub(clock=clock, recovery=recovery)
            consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
            assert consumer is not None
            hub.ready(consumer, 0)
            hub.on_message(kline(open_ms=T0, closed=True))
            hub.on_message(kline(open_ms=T0 + 2 * STEP, closed=True))
            await _pump(20)
            gaps = [p for e, p in drain(consumer) if e == "gap"]
            self.assertEqual(gaps[-1]["status"], "partial")
            self.assertTrue(gaps[-1]["missing"])
            self.assertEqual(gaps[-1]["recovered_bars"], 1)

        asyncio.run(scenario())

    def test_failed_recovery_counts_and_declares(self):
        clock = Clock()

        async def recovery(symbol, interval, start_ms, end_ms):
            return {"status": "failed", "requests": 1, "candles": [],
                    "missing": [[start_ms, end_ms]], "detail": "REST_DOWN"}

        async def scenario():
            hub = KlineStreamHub(clock=clock, recovery=recovery)
            consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
            assert consumer is not None
            hub.ready(consumer, 0)
            hub.on_message(kline(open_ms=T0, closed=True))
            hub.on_message(kline(open_ms=T0 + 2 * STEP, closed=True))
            await _pump(20)
            sub = hub.subs[("BTCUSDT", "1m")]
            self.assertEqual(sub.counters["recovery_failures"], 1)
            gaps = [p for e, p in drain(consumer) if e == "gap"]
            self.assertEqual(gaps[-1]["status"], "failed")
            self.assertEqual(gaps[-1]["detail"], "REST_DOWN")

        asyncio.run(scenario())

    def test_recovery_exception_does_not_break_the_hub(self):
        clock = Clock()

        async def recovery(symbol, interval, start_ms, end_ms):
            raise RuntimeError("socket already closed")

        async def scenario():
            hub = KlineStreamHub(clock=clock, recovery=recovery)
            consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
            assert consumer is not None
            hub.ready(consumer, 0)
            hub.on_message(kline(open_ms=T0, closed=True))
            hub.on_message(kline(open_ms=T0 + 2 * STEP, closed=True))
            await _pump(20)
            sub = hub.subs[("BTCUSDT", "1m")]
            self.assertFalse(sub.recovering)
            gaps = [p for e, p in drain(consumer) if e == "gap"]
            self.assertEqual(gaps[-1]["status"], "failed")
            self.assertIn("socket already closed", gaps[-1]["detail"])

        asyncio.run(scenario())


class ConsumerLifecycleTests(unittest.TestCase):
    """G/H. comparticion, liberacion y recarga sin duplicados."""

    def test_two_consumers_share_one_subscription(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        a, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="a")
        b, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="b")
        assert a is not None and b is not None
        hub.ready(a, 0)
        hub.ready(b, 0)
        self.assertEqual(len(hub.subs), 1)
        self.assertEqual(hub.desired_streams(), ["btcusdt@kline_1m"])

        hub.on_message(kline(open_ms=T0))
        self.assertEqual([e for e, _ in drain(a) if e == "candle"], ["candle"])
        self.assertEqual([e for e, _ in drain(b) if e == "candle"], ["candle"])

        hub.unsubscribe(a)
        hub.on_message(kline(open_ms=T0, close=101.0))
        self.assertEqual(drain(a), [])
        self.assertEqual([e for e, _ in drain(b) if e == "candle"], ["candle"])
        self.assertEqual(hub.health()["streams"][0]["consumers"], 1)

    def test_idle_release_only_after_grace(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock, idle_grace_ms=30_000)
        consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="a")
        assert consumer is not None
        hub.ready(consumer, 0)
        hub.on_message(kline(open_ms=T0))
        hub.unsubscribe(consumer)
        self.assertEqual(hub.release_idle(), [])
        clock.advance(30_001)
        self.assertEqual(hub.release_idle(), ["btcusdt@kline_1m"])
        self.assertEqual(hub.subs, {})
        self.assertEqual(hub.desired_streams(), [])

    def test_page_reload_reuses_state_without_duplicate_subscription(self):
        clock = Clock()
        hub = KlineStreamHub(clock=clock)
        first, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="tab-1")
        assert first is not None
        hub.ready(first, 0)
        hub.on_message(kline(open_ms=T0, closed=True))
        hub.unsubscribe(first)

        second, error = hub.subscribe("BTCUSDT", "1m", consumer_id="tab-1-reload")
        self.assertIsNone(error)
        assert second is not None
        hub.ready(second, T0)
        self.assertEqual(len(hub.subs), 1)
        self.assertEqual(hub.desired_streams(), ["btcusdt@kline_1m"])
        self.assertEqual(hub.subs[("BTCUSDT", "1m")].closed_through_ms, T0 + STEP)

        # La vela ya cubierta por el snapshot no se reenvia; la nueva si.
        hub.on_message(kline(open_ms=T0, close=999.0))
        hub.on_message(kline(open_ms=T0 + STEP, close=102.0))
        candles = [p for e, p in drain(second) if e == "candle"]
        self.assertEqual([p["open_time_ms"] for p in candles], [T0 + STEP])
        self.assertEqual(hub.subscription_generation, 2)

    def test_max_consumers_is_enforced(self):
        hub = KlineStreamHub(clock=Clock(), max_consumers_per_stream=1)
        first, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="a")
        self.assertIsNotNone(first)
        second, error = hub.subscribe("BTCUSDT", "1m", consumer_id="b")
        self.assertIsNone(second)
        self.assertEqual(error, "MAX_CONSUMERS")


class TransportTests(unittest.TestCase):
    """URL, backoff y frames de control del transporte."""

    def test_url_uses_market_route_and_combined_streams(self):
        hub = KlineStreamHub(clock=Clock())
        transport = BinanceKlineTransport(hub)
        url = transport.build_url(["btcusdt@kline_1m", "ethusdt@kline_1h"])
        self.assertEqual(
            url,
            "wss://fstream.binance.com/market/stream?streams=btcusdt@kline_1m/ethusdt@kline_1h",
        )

    def test_backoff_is_bounded_and_jittered(self):
        hub = KlineStreamHub(clock=Clock())
        transport = BinanceKlineTransport(hub, rng=lambda: 0.5)
        self.assertAlmostEqual(transport.backoff_seconds(1), 1.0, places=3)
        self.assertAlmostEqual(transport.backoff_seconds(3), 4.0, places=3)
        self.assertAlmostEqual(transport.backoff_seconds(20), 30.0, places=3)
        jittered = BinanceKlineTransport(hub, rng=lambda: 1.0)
        self.assertAlmostEqual(jittered.backoff_seconds(2), 2.5, places=3)
        low = BinanceKlineTransport(hub, rng=lambda: 0.0)
        self.assertAlmostEqual(low.backoff_seconds(2), 1.5, places=3)

    def test_transport_reads_messages_and_sends_control_frames(self):
        clock = Clock()

        class FakeWs:
            def __init__(self) -> None:
                self.queue: asyncio.Queue = asyncio.Queue()
                self.sent: list[dict] = []
                self.closed = False

            async def send(self, data):
                self.sent.append(json.loads(data))

            def __aiter__(self):
                return self

            async def __anext__(self):
                item = await self.queue.get()
                if item is None:
                    raise StopAsyncIteration
                return item

            async def close(self):
                self.closed = True

        async def scenario():
            hub = KlineStreamHub(clock=clock)
            consumer, _ = hub.subscribe("BTCUSDT", "1m", consumer_id="c1")
            assert consumer is not None
            hub.ready(consumer, 0)
            fake = FakeWs()
            urls: list[str] = []

            async def connect(url):
                urls.append(url)
                return fake

            transport = BinanceKlineTransport(hub, connect=connect, sleep=asyncio.sleep)
            stop = asyncio.Event()
            task = asyncio.ensure_future(transport.run(stop))
            await _pump(10)
            self.assertTrue(urls and "/market/stream?streams=btcusdt@kline_1m" in urls[0])
            self.assertTrue(hub.socket_connected)

            await fake.queue.put(kline(open_ms=T0))
            await _pump(10)
            self.assertEqual([e for e, _ in drain(consumer) if e == "candle"], ["candle"])

            # Cambio en caliente: se envia SUBSCRIBE, sin reconectar.
            hub.subscribe("ETHUSDT", "1h", consumer_id="c2")
            await _pump(20)
            frames = [f for f in fake.sent if f.get("method") == "SUBSCRIBE"]
            self.assertTrue(frames)
            self.assertIn("ethusdt@kline_1h", frames[-1]["params"])
            self.assertEqual(len(urls), 1)

            stop.set()
            await fake.queue.put(None)
            await asyncio.wait_for(task, timeout=5.0)
            self.assertTrue(fake.closed)

        asyncio.run(scenario())


class ServiceEndpointTests(unittest.TestCase):
    """HTTP/SSE en loopback con puerto efimero (transporte simulado)."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_health_sse_and_shutdown(self):
        async def scenario():
            class NullTransport:
                async def run(self, stop):
                    await stop.wait()

            with tempfile.TemporaryDirectory() as tmp:
                cache = MarketCache(Path(tmp) / "cache.db")
                cache.init_db()
                hub = KlineStreamHub(clock=Clock())
                service = MarketStreamService(
                    hub=hub, transport=NullTransport(), cache=cache,
                    port=0, pid_path=Path(tmp) / "service.json",
                )
                await service.start()
                port = service.port

                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(b"GET /health HTTP/1.1\r\nHost: local\r\n\r\n")
                await writer.drain()
                raw = await asyncio.wait_for(reader.read(65536), timeout=5.0)
                text = raw.decode("utf-8", "replace")
                writer.close()
                self.assertIn("200 OK", text)
                self.assertIn("market-stream/v1", text)
                self.assertIn("MEMORY_ONLY", text)

                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(
                    b"GET /stream?symbol=BTCUSDT&interval=1m&bars=5 HTTP/1.1\r\n"
                    b"Host: local\r\n\r\n"
                )
                await writer.drain()
                buffered = b""
                while b"event: snapshot" not in buffered:
                    part = await asyncio.wait_for(reader.read(4096), timeout=5.0)
                    if not part:
                        break
                    buffered += part
                text = buffered.decode("utf-8", "replace")
                self.assertIn("text/event-stream", text)
                self.assertIn("event: hello", text)
                self.assertIn("event: snapshot", text)
                self.assertIn("NO_COVERAGE", text)

                # Una actualizacion real del hub llega al consumidor SSE.
                hub.on_socket_open()
                hub.on_message(kline(open_ms=T0))
                while b"event: candle" not in buffered:
                    part = await asyncio.wait_for(reader.read(4096), timeout=5.0)
                    if not part:
                        break
                    buffered += part
                self.assertIn(b"event: candle", buffered)
                self.assertIn(str(T0).encode(), buffered)
                writer.close()

                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(b"GET /stream?symbol=BTCUSDT&interval=17m HTTP/1.1\r\n\r\n")
                await writer.drain()
                raw = await asyncio.wait_for(reader.read(65536), timeout=5.0)
                self.assertIn(b"400", raw.split(b"\r\n", 1)[0])
                self.assertIn(b"INVALID_INTERVAL", raw)
                writer.close()

                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(b"POST /shutdown HTTP/1.1\r\nHost: local\r\n\r\n")
                await writer.drain()
                raw = await asyncio.wait_for(reader.read(65536), timeout=5.0)
                self.assertIn(b"200", raw.split(b"\r\n", 1)[0])
                writer.close()
                await asyncio.wait_for(service.stop_event.wait(), timeout=5.0)
                await service.stop()
                self.assertFalse((Path(tmp) / "service.json").exists())

        self._run(scenario())

    def test_stream_rejects_unknown_symbol_shape(self):
        async def scenario():
            class NullTransport:
                async def run(self, stop):
                    await stop.wait()

            with tempfile.TemporaryDirectory() as tmp:
                cache = MarketCache(Path(tmp) / "cache.db")
                cache.init_db()
                service = MarketStreamService(
                    hub=KlineStreamHub(clock=Clock()), transport=NullTransport(),
                    cache=cache, port=0, pid_path=Path(tmp) / "service.json",
                )
                await service.start()
                reader, writer = await asyncio.open_connection("127.0.0.1", service.port)
                writer.write(b"GET /stream?symbol=btc-usdt&interval=1m HTTP/1.1\r\n\r\n")
                await writer.drain()
                raw = await asyncio.wait_for(reader.read(65536), timeout=5.0)
                self.assertIn(b"INVALID_SYMBOL", raw)
                writer.close()
                await service.stop()

        self._run(scenario())

    def test_client_close_releases_consumer_immediately(self):
        """Cerrar el SSE libera al consumidor sin esperar al heartbeat (5 s)."""

        async def scenario():
            class NullTransport:
                async def run(self, stop):
                    await stop.wait()

            with tempfile.TemporaryDirectory() as tmp:
                cache = MarketCache(Path(tmp) / "cache.db")
                cache.init_db()
                hub = KlineStreamHub(clock=Clock())
                service = MarketStreamService(
                    hub=hub, transport=NullTransport(), cache=cache,
                    port=0, pid_path=Path(tmp) / "service.json",
                )
                await service.start()
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1", service.port)
                writer.write(
                    b"GET /stream?symbol=BTCUSDT&interval=1m&bars=5 HTTP/1.1\r\n"
                    b"Host: local\r\n\r\n"
                )
                await writer.drain()
                buffered = b""
                while b"event: snapshot" not in buffered:
                    part = await asyncio.wait_for(reader.read(4096), timeout=5.0)
                    if not part:
                        break
                    buffered += part
                self.assertEqual(hub.health()["consumers"], 1)

                writer.close()
                await writer.wait_closed()
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 1.0
                while loop.time() < deadline:
                    if hub.health()["consumers"] == 0:
                        break
                    await asyncio.sleep(0.02)
                self.assertEqual(hub.health()["consumers"], 0)
                await service.stop()

        self._run(scenario())


def _cache_bar(open_ms: int, close: float, base_volume: str = "10.0") -> dict:
    """Vela cerrada en formato de almacen (upsert_klines)."""
    return {
        "open_time": open_ms,
        "open": str(close - 0.5),
        "high": str(close + 0.5),
        "low": str(close - 0.6),
        "close": str(close),
        "base_volume": base_volume,
        "quote_volume": "1000.0",
        "trade_count": 50,
        "close_time": open_ms + STEP - 1,
        "fetched_at": open_ms,
    }


class SessionIndicatorsTests(unittest.TestCase):
    """Recalculo incremental: ventana de sesion y bloque versionado."""

    def test_session_candle_rejects_provisional_and_garbage(self):
        provisional = service_mod._session_candle(
            {"closed": False, "open_time_ms": T0})
        self.assertIsNone(provisional)
        self.assertIsNone(service_mod._session_candle({"closed": True}))
        bar = service_mod._session_candle({
            "closed": True, "open_time_ms": T0, "high": 101.0,
            "low": 99.0, "close": 100.5, "base_volume": 12.5,
        })
        self.assertEqual(bar["open_time"], T0)
        self.assertEqual(bar["close"], 100.5)

    def test_merge_closed_replaces_and_sorts_by_open_time(self):
        candles = service_mod._merge_closed([], {
            "open_time_ms": T0, "close": 100.0, "high": 101.0,
            "low": 99.0, "base_volume": 10.0,
        })
        candles = service_mod._merge_closed(candles, {
            "open_time_ms": T0 + 2 * STEP, "close": 101.0, "high": 102.0,
            "low": 100.0, "base_volume": 11.0,
        })
        candles = service_mod._merge_closed(candles, {
            "open_time_ms": T0 + STEP, "close": 100.5, "high": 101.0,
            "low": 99.0, "base_volume": 10.5,
        })
        self.assertEqual([c["open_time"] for c in candles],
                         [T0, T0 + STEP, T0 + 2 * STEP])
        candles = service_mod._merge_closed(candles, {
            "open_time_ms": T0 + STEP, "close": 100.75, "high": 101.5,
            "low": 99.5, "base_volume": 10.75,
        })
        self.assertEqual(len(candles), 3)
        self.assertEqual(candles[1]["close"], 100.75)

    def test_session_indicators_warmup_gap_and_temporal_grid(self):
        # 3 velas con hueco: la ventana se valida por TIEMPO (rejilla), no
        # por posiciones del arreglo: el hueco interior es GAP_IN_WINDOW y
        # el calentamiento INSUFICIENT_CANDLES; nunca cero.
        candles = [
            {"open_time": T0, "high": 101.0, "low": 99.0, "close": 100.0,
             "base_volume": 10.0},
            {"open_time": T0 + STEP, "high": 101.0, "low": 99.0,
             "close": 100.5, "base_volume": 10.0},
            {"open_time": T0 + 3 * STEP, "high": 101.0, "low": 99.0,
             "close": 101.0, "base_volume": 10.0},
        ]
        block = service_mod._session_indicators("TESTUSDT", "1m", candles)
        self.assertEqual(block["contract_version"], "market-indicators/v1")
        self.assertEqual(block["identity"]["source"], "ws_kline")
        last = block["series"][-1]
        self.assertEqual(last["unknown"]["velocity_bps_5"], "GAP_IN_WINDOW")
        self.assertNotIn("velocity_bps_5", last["values"])
        self.assertEqual(
            last["unknown"]["rel_volume_10"], "GAP_IN_WINDOW")
        self.assertNotIn("rel_volume_10", last["values"])
        self.assertEqual(
            block["series"][1]["values"]["log_return_bps"],
            round(10000 * math.log(100.5 / 100.0), 6))
        self.assertEqual(block["series"][0]["unknown"]["velocity_bps_5"],
                         "INSUFICIENT_CANDLES")

    def test_session_indicators_skips_invalid_interval(self):
        self.assertIsNone(
            service_mod._session_indicators("TESTUSDT", "17m", []))


class ServiceSseIndicatorsTests(unittest.TestCase):
    """SSE de extremo a extremo: snapshot con bloque + frame por cierre."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_snapshot_carries_block_and_close_emits_indicators_frame(self):
        async def scenario():
            class NullTransport:
                async def run(self, stop):
                    await stop.wait()

            with tempfile.TemporaryDirectory() as tmp:
                cache = MarketCache(Path(tmp) / "cache.db")
                cache.init_db()
                cache.upsert_klines(
                    "BTCUSDT", "1m", "klines",
                    [_cache_bar(T0 + i * STEP, 100.0 + i) for i in range(6)],
                    T0)
                hub = KlineStreamHub(clock=Clock(T0 + 9 * STEP))
                service = MarketStreamService(
                    hub=hub, transport=NullTransport(), cache=cache,
                    port=0, pid_path=Path(tmp) / "service.json",
                )
                await service.start()
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1", service.port)
                writer.write(
                    ("GET /stream?symbol=BTCUSDT&interval=1m&bars=10"
                     f"&from_ms={T0}&to_ms={T0 + 9 * STEP} HTTP/1.1\r\n"
                     "Host: local\r\n\r\n").encode("ascii")
                )
                await writer.drain()

                async def read_until(marker: bytes, budget: int = 65536) -> bytes:
                    buffered = b""
                    while marker not in buffered:
                        part = await asyncio.wait_for(
                            reader.read(4096), timeout=5.0)
                        if not part:
                            break
                        buffered += part
                    return buffered

                buffered = await read_until(b"event: snapshot")
                # El frame SSE puede llegar troceado: se sigue leyendo hasta
                # el fin de linea del propio frame (\n\n tras el snapshot).
                tail = buffered.index(b"event: snapshot")
                while b"\n\n" not in buffered[tail:]:
                    buffered += await asyncio.wait_for(
                        reader.read(4096), timeout=5.0)
                snapshot_frame = buffered[tail:]
                body = json.loads(snapshot_frame.split(b"data: ", 1)[1]
                                  .split(b"\n\n", 1)[0])
                self.assertEqual(
                    body["indicators"]["contract_version"],
                    "market-indicators/v1")
                self.assertEqual(body["indicators"]["identity"]["symbol"],
                                 "BTCUSDT")

                # Cierre por stream: frame indicators ANTES de closed, con la
                # vela nueva ya en el bloque (7 filas) y su fila completa.
                hub.on_socket_open()
                hub.on_message(kline(open_ms=T0 + 6 * STEP, closed=True,
                                     close=106.0, event_ms=T0 + 7 * STEP - 1))
                buffered = await read_until(b"event: indicators")
                self.assertIsNotNone(buffered)
                indicators_frames = [
                    frame.split(b"data: ", 1)[1].split(b"\n\n", 1)[0]
                    for frame in buffered.split(b"event: ", 1)[1:]
                    if frame.startswith(b"indicators\ndata: ")
                ]
                self.assertTrue(indicators_frames)
                block = json.loads(indicators_frames[-1])
                self.assertEqual(block["identity"]["source"], "ws_kline")
                self.assertEqual(len(block["series"]), 7)
                last = block["series"][-1]
                self.assertEqual(last["open_time_ms"], T0 + 6 * STEP)
                self.assertNotIn("velocity_bps_5", last["unknown"])
                self.assertIn("velocity_bps_5", last["values"])
                # La vela provisional NO recalcula ni emite el frame.
                hub.on_message(kline(open_ms=T0 + 7 * STEP, closed=False,
                                     close=106.5, event_ms=T0 + 7 * STEP + 1))
                segment = await read_until(b"event: candle")
                self.assertIn(b"event: candle", segment)
                # En el tramo nuevo no hay ningun frame indicators: el
                # recalculo ocurre solo con velas cerradas.
                self.assertEqual(segment.count(b"event: indicators"), 0)
                writer.close()
                await service.stop()

        self._run(scenario())


if __name__ == "__main__":
    unittest.main()
