"""P1-06 aggressive trade-flow tests (known-value style, no network).

Covers: aggressor-side semantics (m flag), notional/delta/ratio math,
multi-horizon trailing windows + exact boundaries, late/out-of-order,
no-lookahead (completed-buckets-only baselines), z-score semantics
(insufficient/zero-variance -> UNKNOWN), acceleration, persistence
round-trip + restart continuity, sampling-independence + skew-guard
probe wiring, HOT scoping, dashboard rendering + APIs, safety.
"""

import json
import math
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from microstructure_probe import dashboard
from microstructure_probe.dashboard import (
    DashboardServer,
    render_flow_section,
)
from microstructure_probe.flow import (
    BASELINE_KEEP_BUCKETS,
    FLOW_HORIZON_ORDER,
    FLOW_HORIZONS_MS,
    FlowEngine,
    SymbolFlowSeries,
)
from microstructure_probe.persistence import PersistenceStore
from microstructure_probe.probe import MarketProbe

from test_detectors import test_config


T0 = 1_700_000_000_000


def _engine(symbols=("BTCUSDT",), min_buckets=3):
    return FlowEngine(symbols=symbols, min_baseline_buckets=min_buckets)


def _temp_store(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="flow_test_"))
    testcase.addCleanup(
        lambda: [p.unlink(missing_ok=True) for p in sorted(tmp.rglob("*"), reverse=True)]
        or tmp.rmdir())
    db_path = tmp / "flow.db"
    store = PersistenceStore(db_path=db_path)
    store.init_db()
    testcase.addCleanup(store.close)
    return store


class AggressorSemanticsTest(unittest.TestCase):
    def test_buyer_is_maker_true_is_aggressive_sell(self) -> None:
        series = SymbolFlowSeries()
        self.assertTrue(series.ingest(T0, 100.0, 2.0, True))
        rec = series.snapshot("BTCUSDT", T0, True)
        h = rec["horizons"]["10s"]
        self.assertEqual(h["trades"], 1)
        self.assertEqual(h["buy_notional"], 0.0)
        self.assertEqual(h["sell_notional"], 200.0)
        self.assertEqual(h["signed_delta"], -200.0)
        self.assertEqual(h["delta_ratio"], -1.0)

    def test_buyer_is_maker_false_is_aggressive_buy(self) -> None:
        series = SymbolFlowSeries()
        self.assertTrue(series.ingest(T0, 100.0, 2.0, False))
        rec = series.snapshot("BTCUSDT", T0, True)
        h = rec["horizons"]["10s"]
        self.assertEqual(h["buy_notional"], 200.0)
        self.assertEqual(h["sell_notional"], 0.0)
        self.assertEqual(h["signed_delta"], 200.0)
        self.assertEqual(h["delta_ratio"], 1.0)

    def test_quote_notional_math_and_signed_delta(self) -> None:
        series = SymbolFlowSeries()
        series.ingest(T0, 100.0, 1.0, False)  # buy 100
        series.ingest(T0 + 1000, 200.0, 3.0, True)  # sell 600
        h = series.snapshot("BTCUSDT", T0 + 1000, True)["horizons"]["1m"]
        self.assertEqual(h["buy_base"], 1.0)
        self.assertEqual(h["sell_base"], 3.0)
        self.assertEqual(h["buy_notional"], 100.0)
        self.assertEqual(h["sell_notional"], 600.0)
        self.assertEqual(h["signed_delta"], -500.0)
        self.assertAlmostEqual(h["delta_ratio"], -500.0 / 700.0)

    def test_delta_ratio_bounds_and_zero_denominator_unknown(self) -> None:
        series = SymbolFlowSeries()
        rec = series.snapshot("BTCUSDT", T0, True)
        self.assertIsNone(rec["horizons"]["1m"]["delta_ratio"])
        self.assertIsNone(rec["horizons"]["1m"]["buy_pct"])
        series.ingest(T0, 50.0, 4.0, False)
        series.ingest(T0 + 1000, 50.0, 4.0, True)
        h = series.snapshot("BTCUSDT", T0 + 1000, True)["horizons"]["1m"]
        self.assertEqual(h["delta_ratio"], 0.0)
        self.assertEqual(h["buy_pct"], 50.0)
        self.assertEqual(h["sell_pct"], 50.0)

    def test_buy_sell_percentages(self) -> None:
        series = SymbolFlowSeries()
        series.ingest(T0, 100.0, 3.0, False)  # 300 buy
        series.ingest(T0 + 1000, 100.0, 1.0, True)  # 100 sell
        h = series.snapshot("BTCUSDT", T0 + 1000, True)["horizons"]["1m"]
        self.assertAlmostEqual(h["buy_pct"], 75.0)
        self.assertAlmostEqual(h["sell_pct"], 25.0)

    def test_rpi_quantity_tracked_but_totals_use_q(self) -> None:
        series = SymbolFlowSeries()
        # q=10 total incl. RPI, nq=6 normal -> 4 RPI base @100.
        self.assertTrue(series.ingest(T0, 100.0, 10.0, False, 6.0))
        rec = series.snapshot("BTCUSDT", T0, True)
        self.assertEqual(rec["horizons"]["1m"]["buy_notional"], 1000.0)
        self.assertEqual(rec["rpi_base_total"], 4.0)
        self.assertEqual(rec["rpi_notional_total"], 400.0)
        self.assertEqual(rec["rpi_trades"], 1)

    def test_missing_or_non_bool_maker_flag_is_invalid(self) -> None:
        series = SymbolFlowSeries()
        for bad in (None, "true", 1, 0):
            self.assertFalse(series.ingest(T0, 100.0, 1.0, bad))
        self.assertEqual(series.dropped_invalid, 4)
        self.assertEqual(series.trades_total, 0)

    def test_invalid_price_or_quantity_refused(self) -> None:
        series = SymbolFlowSeries()
        for price, qty in ((0.0, 1.0), (-5.0, 1.0), (100.0, 0.0),
                           (100.0, -1.0), (float("nan"), 1.0),
                           (100.0, float("inf"))):
            self.assertFalse(series.ingest(T0, price, qty, True))
        self.assertEqual(series.trades_total, 0)
        self.assertEqual(series.dropped_invalid, 6)


class HorizonAggregationTest(unittest.TestCase):
    def test_multi_horizon_membership(self) -> None:
        engine = _engine()
        engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)
        engine.ingest("BTCUSDT", T0 + 20_000, 100.0, 1.0, False)
        engine.ingest("BTCUSDT", T0 + 70_000, 100.0, 1.0, False)
        rec = engine.snapshot_all(T0 + 70_000)[0]
        self.assertEqual(rec["horizons"]["10s"]["trades"], 1)
        self.assertEqual(rec["horizons"]["30s"]["trades"], 1)
        self.assertEqual(rec["horizons"]["1m"]["trades"], 2)
        self.assertEqual(rec["horizons"]["3m"]["trades"], 3)
        self.assertEqual(rec["horizons"]["15m"]["trades"], 3)

    def test_exact_window_boundary_excluded(self) -> None:
        # (as_of - h, as_of]: a trade exactly h old is OUT, 1ms newer is IN.
        engine = _engine()
        engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)
        engine.ingest("BTCUSDT", T0 + 10_000, 100.0, 1.0, False)
        rec = engine.snapshot_all(T0 + 10_000)[0]
        self.assertEqual(rec["horizons"]["10s"]["trades"], 1)
        engine.ingest("BTCUSDT", T0 + 19_999, 100.0, 1.0, False)
        rec = engine.snapshot_all(T0 + 19_999)[0]
        self.assertEqual(rec["horizons"]["10s"]["trades"], 2)

    def test_irregular_timestamps(self) -> None:
        engine = _engine()
        times = [T0, T0 + 1000, T0 + 61000, T0 + 119000, T0 + 120000]
        for t in times:
            engine.ingest("BTCUSDT", t, 100.0, 1.0, False)
        rec = engine.snapshot_all(T0 + 120000)[0]
        self.assertEqual(rec["horizons"]["10s"]["trades"], 2)
        self.assertEqual(rec["horizons"]["1m"]["trades"], 3)
        self.assertEqual(rec["horizons"]["3m"]["trades"], 5)

    def test_expiry_is_exact_per_horizon(self) -> None:
        engine = _engine()
        engine.ingest("BTCUSDT", T0, 100.0, 5.0, True)
        engine.ingest("BTCUSDT", T0 + 11_000, 100.0, 1.0, False)
        rec = engine.snapshot_all(T0 + 11_000)[0]
        self.assertEqual(rec["horizons"]["10s"]["trades"], 1)
        self.assertEqual(rec["horizons"]["10s"]["buy_notional"], 100.0)
        self.assertEqual(rec["horizons"]["1m"]["trades"], 2)
        self.assertEqual(rec["horizons"]["1m"]["sell_notional"], 500.0)

    def test_trade_and_notional_rates_use_full_window(self) -> None:
        engine = _engine()
        for i in range(6):
            engine.ingest("BTCUSDT", T0 + i * 10_000, 100.0, 1.0, False)
        rec = engine.snapshot_all(T0 + 50_000)[0]
        m = rec["horizons"]["1m"]
        self.assertEqual(m["trades"], 6)
        self.assertAlmostEqual(m["trade_rate"], 6 / 60.0)
        self.assertAlmostEqual(m["notional_rate"], 600.0 / 60.0)

    def test_warmup_flags_span(self) -> None:
        engine = _engine()
        engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)
        engine.ingest("BTCUSDT", T0 + 5_000, 100.0, 1.0, False)
        rec = engine.snapshot_all(T0 + 5_000)[0]
        self.assertFalse(rec["horizons"]["10s"]["warmup_complete"])
        engine.ingest("BTCUSDT", T0 + 10_000, 100.0, 1.0, False)
        rec = engine.snapshot_all(T0 + 10_000)[0]
        self.assertTrue(rec["horizons"]["10s"]["warmup_complete"])
        self.assertFalse(rec["horizons"]["15m"]["warmup_complete"])


class LatePolicyTest(unittest.TestCase):
    def test_strictly_older_events_dropped_and_counted(self) -> None:
        engine = _engine()
        self.assertTrue(engine.ingest("BTCUSDT", T0 + 2000, 100.0, 1.0, False))
        self.assertFalse(engine.ingest("BTCUSDT", T0 + 1000, 100.0, 9.0, False))
        self.assertFalse(engine.ingest("BTCUSDT", T0 + 1999, 100.0, 9.0, False))
        rec = engine.snapshot_all(T0 + 2000)[0]
        self.assertEqual(rec["horizons"]["1m"]["buy_notional"], 100.0)
        self.assertEqual(rec["dropped_late"], 2)
        self.assertEqual(rec["trades_total"], 1)

    def test_same_event_time_accepted_in_arrival_order(self) -> None:
        # One 100ms push carries several distinct aggregates with identical
        # E; the stream never redelivers, so same-E trades are new volume.
        engine = _engine()
        self.assertTrue(engine.ingest("BTCUSDT", T0, 100.0, 1.0, False))
        self.assertTrue(engine.ingest("BTCUSDT", T0, 100.0, 2.0, True))
        rec = engine.snapshot_all(T0)[0]
        self.assertEqual(rec["horizons"]["1m"]["trades"], 2)
        self.assertEqual(rec["horizons"]["1m"]["buy_notional"], 100.0)
        self.assertEqual(rec["horizons"]["1m"]["sell_notional"], 200.0)
        self.assertEqual(rec["dropped_late"], 0)

    def test_history_never_rewritten_by_older_trade(self) -> None:
        engine = _engine()
        engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)
        engine.ingest("BTCUSDT", T0 + 60_000, 100.0, 1.0, False)
        before = engine.snapshot_all(T0 + 60_000)[0]["horizons"]["1m"]["trades"]
        engine.ingest("BTCUSDT", T0 + 30_000, 100.0, 50.0, True)
        after = engine.snapshot_all(T0 + 60_000)[0]["horizons"]["1m"]
        self.assertEqual(after["trades"], before)
        self.assertEqual(after["sell_notional"], 0.0)


class NoLookaheadTest(unittest.TestCase):
    def test_partial_bucket_never_enters_own_baseline(self) -> None:
        engine = _engine(min_buckets=1)
        for i in range(5):
            engine.ingest("BTCUSDT", T0 + i * 1000, 100.0, 1.0, False)
        rec = engine.snapshot_all(T0 + 4000)[0]
        base = rec["baselines"]["10s"]
        self.assertEqual(base["samples"], 0)
        self.assertIsNone(base["z_score"])
        self.assertIsNone(base["mean_notional"])

    def test_acceleration_needs_completed_bucket(self) -> None:
        engine = _engine(min_buckets=1)
        engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)
        accel = engine.snapshot_all(T0)[0]["acceleration"]
        self.assertIsNotNone(accel["notional_rate"])
        self.assertIsNone(accel["notional_rate_change"])
        self.assertIsNone(accel["delta_rate_change"])


class BaselineZTest(unittest.TestCase):
    def _warmed(self, min_buckets=3):
        engine = _engine(min_buckets=min_buckets)
        # Four completed 10s buckets with notionals 10/20/30, then current 30.
        buckets = [(0, 10.0), (10_000, 20.0), (20_000, 30.0)]
        for offset, notional in buckets:
            engine.ingest("BTCUSDT", T0 + offset, 100.0, notional / 100.0,
                           False)
        engine.ingest("BTCUSDT", T0 + 30_000, 100.0, 0.30, False)
        return engine

    def test_z_score_known_values(self) -> None:
        engine = self._warmed()
        base = engine.snapshot_all(T0 + 30_000)[0]["baselines"]["10s"]
        history = (10.0, 20.0, 30.0)
        mean = 20.0
        std = math.sqrt(sum((v - mean) ** 2 for v in history) / 3)
        self.assertEqual(base["samples"], 3)
        self.assertAlmostEqual(base["mean_notional"], mean)
        self.assertAlmostEqual(base["std_notional"], std)
        self.assertAlmostEqual(base["z_score"], (30.0 - mean) / std)
        self.assertTrue(base["warmup"])

    def test_insufficient_baseline_is_unknown(self) -> None:
        engine = _engine(min_buckets=5)
        engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)
        engine.ingest("BTCUSDT", T0 + 10_000, 100.0, 1.0, False)
        base = engine.snapshot_all(T0 + 10_000)[0]["baselines"]["10s"]
        self.assertEqual(base["samples"], 1)
        self.assertIsNone(base["z_score"])
        self.assertIsNone(base["mean_notional"])
        self.assertFalse(base["warmup"])

    def test_zero_variance_baseline_is_unknown(self) -> None:
        engine = _engine(min_buckets=2)
        for i in range(4):
            engine.ingest("BTCUSDT", T0 + i * 10_000, 100.0, 1.0, False)
        base = engine.snapshot_all(T0 + 30_000)[0]["baselines"]["10s"]
        self.assertEqual(base["samples"], 3)
        self.assertIsNotNone(base["mean_notional"])
        self.assertIsNone(base["std_notional"])
        self.assertIsNone(base["z_score"])
        self.assertFalse(base["warmup"])

    def test_skipped_buckets_counted_never_fabricated(self) -> None:
        engine = _engine(min_buckets=1)
        engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)
        engine.ingest("BTCUSDT", T0 + 50_000, 100.0, 2.0, False)
        base = engine.snapshot_all(T0 + 50_000)[0]["baselines"]["10s"]
        self.assertEqual(base["samples"], 1)
        # Buckets T0+10s..T0+40s never observed: counted, never zero-filled.
        self.assertEqual(base["skipped_buckets"], 4)
        self.assertIsNone(base["z_score"])


class AccelerationTest(unittest.TestCase):
    def test_volume_and_delta_acceleration_known_values(self) -> None:
        engine = _engine(min_buckets=1)
        # Minute-aligned base so all six setup trades share one 1m bucket.
        base = (T0 // 60_000) * 60_000
        # Completed 1m bucket: 600 notional over 60s -> rate 10/s, 6 trades.
        for i in range(6):
            engine.ingest("BTCUSDT", base + i * 10_000, 100.0, 1.0, False)
        # Current partial 1m bucket: 2 trades x 200 = 400 over ~10s -> ~40/s.
        engine.ingest("BTCUSDT", base + 60_000, 100.0, 2.0, True)
        engine.ingest("BTCUSDT", base + 70_000, 100.0, 2.0, True)
        accel = engine.snapshot_all(base + 70_000)[0]["acceleration"]
        self.assertEqual(accel["baseline"], "1m")
        elapsed_s = 10_001 / 1000.0
        self.assertAlmostEqual(accel["notional_rate"], 400.0 / elapsed_s,
                               delta=0.01)
        self.assertAlmostEqual(accel["notional_rate_change"],
                               400.0 / elapsed_s - 600.0 / 60.0, delta=0.01)
        self.assertAlmostEqual(accel["trade_rate_change"],
                               2 / elapsed_s - 6 / 60.0, delta=0.001)
        # Current delta -400 @~10s -> ~-40/s; prev +600 @60s -> +10/s.
        self.assertAlmostEqual(accel["delta_rate"], -400.0 / elapsed_s,
                               delta=0.01)
        self.assertAlmostEqual(accel["delta_rate_change"],
                               -400.0 / elapsed_s - 10.0, delta=0.01)


class EngineScopeTest(unittest.TestCase):
    def test_unknown_symbol_refused_and_counted(self) -> None:
        engine = _engine(symbols=("BTCUSDT",))
        self.assertFalse(
            engine.ingest("ETHUSDT", T0, 100.0, 1.0, False))
        self.assertEqual(engine.dropped_unknown, 1)
        self.assertEqual(engine.snapshot_all(T0), [])

    def test_stats_shape_with_latency(self) -> None:
        engine = _engine()
        engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)
        stats = engine.stats()
        self.assertEqual(stats["events_processed"], 1)
        self.assertEqual(stats["queue_high_water"], 0)
        self.assertEqual(stats["queue_depth"], 0)
        lat = stats["latency_ms"]
        self.assertEqual(lat["count"], 1)
        self.assertIsNotNone(lat["p50"])
        self.assertIsNotNone(lat["p95"])
        self.assertIsNotNone(lat["max"])
        self.assertIn("BTCUSDT", stats["symbols"])

    def test_horizon_catalog_complete(self) -> None:
        self.assertEqual(set(FLOW_HORIZONS_MS),
                         {"10s", "30s", "1m", "3m", "5m", "15m"})
        self.assertEqual(list(FLOW_HORIZON_ORDER),
                         ["10s", "30s", "1m", "3m", "5m", "15m"])


class FlowPersistenceTest(unittest.TestCase):
    def test_flow_features_round_trip(self) -> None:
        store = _temp_store(self)
        self.assertEqual(store.latest_flow_features(), [])
        engine = _engine()
        engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)
        rows = engine.snapshot_all(T0)
        store.store_flow_features(rows)
        latest = store.latest_flow_features()
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["symbol"], "BTCUSDT")
        self.assertEqual(latest[0]["horizons"]["10s"]["buy_notional"], 100.0)

    def test_flow_buckets_round_trip_and_restart(self) -> None:
        store = _temp_store(self)
        engine = _engine(min_buckets=1)
        for i in range(4):
            engine.ingest("BTCUSDT", T0 + i * 10_000, 100.0, 1.0, False)
        store.store_flow_buckets(engine.drain_completed_buckets())
        loaded = store.load_flow_buckets(symbol="BTCUSDT", size_s=10)
        self.assertEqual(len(loaded), 3)
        fresh = _engine(min_buckets=1)
        self.assertEqual(
            fresh.restore_buckets(
                [dict(r, symbol="BTCUSDT") for r in loaded]), 3)
        base = fresh.snapshot_all(T0 + 30_000)[0]["baselines"]["10s"]
        self.assertEqual(base["samples"], 3)
        self.assertIsNotNone(base["mean_notional"])
        # Live windows restart empty: no fake continuity.
        rec = fresh.snapshot_all(T0 + 30_000)[0]
        self.assertEqual(rec["trades_total"], 0)
        self.assertEqual(rec["horizons"]["10s"]["trades"], 0)

    def test_flow_buckets_retention_bounded(self) -> None:
        store = _temp_store(self)
        rows = [{"symbol": "BTCUSDT", "size_s": 10,
                 "bucket_ms": T0 + i * 10_000, "notional": 1.0, "base": 0.01,
                 "buy_notional": 1.0, "sell_notional": 0.0, "trades": 1}
                for i in range(BASELINE_KEEP_BUCKETS + 50)]
        store.store_flow_buckets(rows)
        loaded = store.load_flow_buckets(
            symbol="BTCUSDT", size_s=10, limit=BASELINE_KEEP_BUCKETS + 100)
        self.assertEqual(len(loaded), BASELINE_KEEP_BUCKETS)
        self.assertEqual(loaded[0]["bucket_ms"], T0 + 50 * 10_000)

    def test_repeated_bucket_rewrite_is_idempotent(self) -> None:
        store = _temp_store(self)
        row = {"symbol": "BTCUSDT", "size_s": 10, "bucket_ms": T0,
               "notional": 1.0, "base": 0.01, "buy_notional": 1.0,
               "sell_notional": 0.0, "trades": 1}
        store.store_flow_buckets([row])
        store.store_flow_buckets([row])
        self.assertEqual(
            len(store.load_flow_buckets(symbol="BTCUSDT", size_s=10)), 1)


class ProbeFlowWiringTest(unittest.TestCase):
    def _probe(self, now_ms):
        probe = MarketProbe(test_config(),
                            wall_clock_ms=lambda: float(now_ms),
                            monotonic=lambda: 10.0)
        store = _temp_store(self)
        probe.set_persistence(store)
        return probe, store

    def _aggtrade(self, event_ms, price="100", qty="1", maker=False):
        return json.dumps({
            "stream": "btcusdt@aggTrade",
            "data": {"E": event_ms, "T": event_ms, "s": "BTCUSDT",
                     "p": price, "q": qty, "m": maker},
        })

    def test_skew_rejected_trades_never_reach_engine(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        probe._handle_message(self._aggtrade(now_ms - 6000, maker=True))
        self.assertEqual(probe.stats.rejected_timestamp, 1)
        self.assertEqual(probe.flow.events_processed, 0)
        self.assertEqual(probe.flow.snapshot_all(now_ms), [])

    def test_sampling_does_not_alter_engine_flow_totals(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, store = self._probe(now_ms)
        # 5 valid trades 100ms apart: engine must see all 5; the 1/s
        # persistence gate keeps far fewer raw observations.
        for i in range(5):
            probe._handle_message(
                self._aggtrade(now_ms - 400 + i * 100, maker=(i % 2 == 0)))
        self.assertEqual(probe.flow.events_processed, 5)
        rec = probe.flow.snapshot_all(now_ms)[0]
        self.assertEqual(rec["trades_total"], 5)
        self.assertEqual(rec["horizons"]["1m"]["sell_notional"], 300.0)
        self.assertEqual(rec["horizons"]["1m"]["buy_notional"], 200.0)
        persisted = [o for o in store.latest_observations(limit=50)
                     if o["symbol"] == "BTCUSDT"]
        self.assertLess(len(persisted), 5)
        sample_stats = store.sample_stats()
        self.assertGreater(sample_stats["dropped"].get("aggTrade", 0), 0)

    def test_missing_maker_flag_reaches_detectors_but_not_flow(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        probe._handle_message(json.dumps({
            "stream": "btcusdt@aggTrade",
            "data": {"E": now_ms, "T": now_ms, "s": "BTCUSDT",
                     "p": "100", "q": "1"},
        }))
        # Detector path untouched (no payload error); flow refuses to guess.
        self.assertEqual(probe.stats.payload_errors, 0)
        self.assertEqual(probe.flow.events_processed, 0)

    def test_unsubscribed_hot_symbol_gets_no_live_flow(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        probe._handle_message(json.dumps({
            "stream": "xrpusdt@aggTrade",
            "data": {"E": now_ms, "T": now_ms, "s": "XRPUSDT",
                     "p": "2", "q": "10", "m": False},
        }))
        self.assertEqual(probe.flow.events_processed, 0)
        self.assertEqual(probe.flow.dropped_unknown, 1)
        self.assertEqual(probe.flow.snapshot_all(now_ms), [])

    def test_summary_carries_flow_counters(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        probe._handle_message(self._aggtrade(now_ms, maker=False))
        summary = probe.build_summary(final=True)
        self.assertIn("flow", summary)
        self.assertEqual(summary["flow"]["events_processed"], 1)
        self.assertIn("latency_ms", summary["flow"])

    def test_log_summary_persists_flow_state(self) -> None:
        now_ms = int(time.time() * 1000)
        # Mutable wall clock: each message is fresh at its own event time
        # (an 11s-old E against a fixed clock would be skew-rejected).
        clock = [float(now_ms)]
        probe = MarketProbe(test_config(),
                            wall_clock_ms=lambda: clock[0],
                            monotonic=lambda: 10.0)
        store = _temp_store(self)
        probe.set_persistence(store)
        # Span two 10s buckets so one bucket completes for persistence.
        probe._handle_message(self._aggtrade(now_ms, maker=False))
        clock[0] = float(now_ms + 11_000)
        probe._handle_message(self._aggtrade(now_ms + 11_000, maker=True))
        probe.log_summary(final=False)
        latest = store.latest_flow_features()
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["symbol"], "BTCUSDT")
        self.assertTrue(latest[0]["subscribed"])
        self.assertEqual(latest[0]["horizons"]["1m"]["trades"], 2)
        buckets = store.load_flow_buckets(symbol="BTCUSDT", size_s=10)
        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0]["buy_notional"], 100.0)


class DashboardFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="flow_dash_test_"))
        self.addCleanup(
            lambda: [p.unlink(missing_ok=True)
                     for p in sorted(tmp.rglob("*"), reverse=True)]
            or tmp.rmdir())
        self.store = PersistenceStore(db_path=tmp / "dash.db")
        self.store.init_db()
        self.addCleanup(self.store.close)
        self.server = DashboardServer(host="127.0.0.1", port=0,
                                     db_path=self.store.db_path).start()
        self.addCleanup(self.server.stop)
        self.base = f"http://127.0.0.1:{self.server.bound_port()}"

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path,
                                        timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.request.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def _flow_record(self):
        engine = _engine()
        engine.ingest("BTCUSDT", T0, 100.0, 3.0, False)
        engine.ingest("BTCUSDT", T0 + 1000, 100.0, 1.0, True)
        return engine.snapshot_all(T0 + 1000)[0]

    def test_flow_api_empty_is_404(self) -> None:
        code, body = self._get("/api/features/flow")
        self.assertEqual(code, 404)
        code, body = self._get("/api/features/volume")
        self.assertEqual(code, 404)

    def test_flow_api_payload_shape(self) -> None:
        self.store.store_flow_features([self._flow_record()])
        code, body = self._get("/api/features/flow")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["source"], "aggTrade")
        self.assertIn("aggressive", payload["aggressor_semantics"])
        self.assertEqual(payload["horizons"],
                         ["10s", "30s", "1m", "3m", "5m", "15m"])
        symbol = payload["symbols"][0]
        self.assertEqual(symbol["symbol"], "BTCUSDT")
        self.assertTrue(symbol["subscribed"])
        hour = symbol["horizons"]["1m"]
        self.assertEqual(hour["buy_notional"], 300.0)
        self.assertEqual(hour["sell_notional"], 100.0)
        self.assertEqual(hour["signed_delta"], 200.0)
        self.assertAlmostEqual(hour["delta_ratio"], 0.5)
        self.assertIn("baselines", symbol)
        self.assertIn("acceleration", symbol)
        self.assertIn("freshness_ms", symbol)

    def test_volume_api_payload_shape(self) -> None:
        self.store.store_flow_features([self._flow_record()])
        code, body = self._get("/api/features/volume")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["source"], "aggTrade")
        symbol = payload["symbols"][0]
        self.assertIn("baselines", symbol)
        self.assertIn("acceleration", symbol)
        self.assertNotIn("horizons", symbol)

    def test_overview_renders_flow_split_and_no_signals(self) -> None:
        self.store.store_telemetry_snapshot({
            "runtimeSeconds": 10.0,
            "safety": {"BOT_MODE": "observe", "apiKeysUsed": 0,
                       "realOrdersSent": 0, "realCapitalAtRisk": 0,
                       "maxDrawdownKillSwitchActive": False,
                       "authenticatedClientsPresent": False,
                       "orderExecutionPathPresent": False},
            "dataQuality": {"expectedStreams": 11, "activeStreams": 11},
        })
        self.store.store_flow_features([self._flow_record()])
        code, body = self._get("/overview")
        self.assertEqual(code, 200)
        self.assertIn("Live trade flow", body)
        self.assertIn("BUY", body)
        self.assertIn("SELL", body)
        self.assertIn("75%", body)
        self.assertNotIn("<button", body.lower())
        for forbidden in ("entry", "place_order", " signal ", "BUY SIGNAL",
                          "SELL SIGNAL"):
            self.assertNotIn(forbidden, body)

    def test_discovery_table_labels_unsubscribed(self) -> None:
        self.store.store_telemetry_snapshot({
            "runtimeSeconds": 10.0,
            "safety": {"BOT_MODE": "observe", "apiKeysUsed": 0,
                       "realOrdersSent": 0, "realCapitalAtRisk": 0,
                       "maxDrawdownKillSwitchActive": False,
                       "authenticatedClientsPresent": False,
                       "orderExecutionPathPresent": False},
            "dataQuality": {"expectedStreams": 11, "activeStreams": 11},
        })
        self.store.store_discovery_snapshot({
            "generated_at_ms": int(time.time() * 1000),
            "eligible_count": 2, "seen_count": 2, "filtered_count": 0,
            "core": ["BTCUSDT"], "hot_dynamic": ["XRPUSDT"],
            "hot_full": ["BTCUSDT", "XRPUSDT"], "top_n": 10,
            "tops": {"gainers": [
                {"symbol": "XRPUSDT", "change_24h_pct": 12.5,
                 "price": "2.5", "quote_volume_24h": "999"}],
                     "losers": [], "most_active": []},
        })
        code, body = self._get("/overview")
        self.assertEqual(code, 200)
        self.assertIn("DISCOVERY ONLY", body)
        self.assertIn("NO LIVE FLOW", body)

    def test_render_flow_section_empty_is_honest(self) -> None:
        body = render_flow_section([], [])
        self.assertIn("No live flow yet", body)

    def test_render_flow_section_marks_unknown_z(self) -> None:
        body = render_flow_section([self._flow_record()], [])
        # 1m baseline has no completed buckets -> z shows the gap marker.
        self.assertIn("baseline warming up or zero variance", body)


class FlowSafetyTest(unittest.TestCase):
    def test_flow_module_has_no_trading_paths(self) -> None:
        # Same forbidden-path contract as the probe-wide safety test.
        root = (Path(__file__).resolve().parent.parent
                / "src" / "microstructure_probe")
        text = (root / "flow.py").read_text(encoding="utf-8").lower()
        forbidden = (
            "/fapi/v1/order",
            "x-mbx-apikey",
            "create_order",
            "place_order",
            "send_order",
            "api_secret",
            "/private/",
        )
        for term in forbidden:
            self.assertNotIn(term, text)


if __name__ == "__main__":
    unittest.main()
