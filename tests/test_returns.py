"""Tests for P1-04 symbol universe + multi-timeframe return engine."""

import json
import math
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe.returns import (
    BUCKET_MS,
    MAX_BUCKETS,
    TIMEFRAME_ORDER,
    TIMEFRAMES_MS,
    ReturnEngine,
    SymbolPriceSeries,
    anchor_tolerance_ms,
)
from microstructure_probe.universe import SymbolInfo, SymbolUniverse


class UniverseTest(unittest.TestCase):
    def test_from_config_preserves_validated_trio(self) -> None:
        from test_detectors import test_config

        universe = SymbolUniverse.from_config(
            test_config(), reason="unit-test")
        self.assertEqual(universe.active_symbols(), ("BTCUSDT",))
        info = universe.get("btcusdt")
        self.assertTrue(info.enabled)
        self.assertEqual(info.source, "static-config")
        self.assertEqual(info.reason, "unit-test")
        self.assertIsNotNone(info.activated_at)

    def test_unknown_symbol_lookup(self) -> None:
        universe = SymbolUniverse.from_list(
            ["BTCUSDT"], source="static-config", reason="t")
        self.assertIsNone(universe.get("DOGEUSDT"))
        self.assertNotIn("DOGEUSDT", universe)
        self.assertIn("BTCUSDT", universe)
        self.assertEqual(len(universe), 1)

    def test_disabled_symbols_excluded_from_active(self) -> None:
        universe = SymbolUniverse([
            SymbolInfo(symbol="BTCUSDT", enabled=True, source="s", reason="r"),
            SymbolInfo(symbol="ETHUSDT", enabled=False, source="s", reason="r"),
        ])
        self.assertEqual(universe.active_symbols(), ("BTCUSDT",))

    def test_duplicate_symbols_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SymbolUniverse.from_list(["BTCUSDT", "btcusdt"],
                                     source="s", reason="r")


def _two_level_engine(t0_ms: int, span_ms: int, old_price: float,
                      new_price: float, symbols=("BTCUSDT",)) -> ReturnEngine:
    """Engine with price old_price everywhere except the newest bucket."""
    engine = ReturnEngine(symbols=symbols)
    bucket0 = t0_ms - (t0_ms % BUCKET_MS)
    last_bucket = (t0_ms + span_ms) - ((t0_ms + span_ms) % BUCKET_MS)
    bucket = bucket0
    while bucket < last_bucket:
        engine.ingest(symbols[0], bucket + 1, old_price)
        bucket += BUCKET_MS
    engine.ingest(symbols[0], last_bucket + 1, new_price)
    return engine


class ReturnEngineTest(unittest.TestCase):
    def test_all_timeframes_known_log_values(self) -> None:
        t0 = 1_700_000_000_000
        engine = _two_level_engine(t0, 25 * 3600 * 1000, 100.0, 101.0)
        as_of = t0 + 25 * 3600 * 1000
        feat = engine.feature("BTCUSDT", as_of)
        expected = math.log(101.0 / 100.0)
        self.assertEqual(set(feat["returns"]), set(TIMEFRAME_ORDER))
        for tf in TIMEFRAME_ORDER:
            self.assertAlmostEqual(feat["returns"][tf], expected, places=12, msg=tf)
            self.assertIsNotNone(feat["anchor_ms"][tf])
        self.assertEqual(feat["current_price"], 101.0)
        self.assertEqual(feat["source"], "markPrice")
        self.assertTrue(feat["warmup_complete"])
        self.assertEqual(len(feat["available_tfs"]), 7)

    def test_empty_series_all_unknown_never_zero(self) -> None:
        engine = ReturnEngine(symbols=("BTCUSDT",))
        feat = engine.feature("BTCUSDT", 1_700_000_000_000)
        self.assertIsNone(feat["current_price"])
        for tf in TIMEFRAME_ORDER:
            self.assertIsNone(feat["returns"][tf])
            self.assertIsNone(feat["anchor_ms"][tf])
        self.assertFalse(feat["warmup_complete"])

    def test_short_history_long_horizons_unknown(self) -> None:
        t0 = 1_700_000_000_000
        engine = ReturnEngine(symbols=("BTCUSDT",))
        for i in range(10):  # 90s span
            engine.ingest("BTCUSDT", t0 + i * 10_000, 100.0)
        feat = engine.feature("BTCUSDT", t0 + 90_000)
        self.assertIsNotNone(feat["returns"]["1m"])
        for tf in ("3m", "5m", "15m", "1h", "4h", "24h"):
            self.assertIsNone(feat["returns"][tf], tf)
        self.assertFalse(feat["warmup_complete"])

    def test_no_lookahead_future_jump_invisible(self) -> None:
        t0 = 1_700_000_000_000
        engine = _two_level_engine(t0, 3 * 3600 * 1000, 100.0, 200.0)
        feat = engine.feature("BTCUSDT", t0 + 2 * 3600 * 1000)
        self.assertEqual(feat["current_price"], 100.0)
        for tf in ("1m", "3m", "5m", "15m", "1h"):
            self.assertAlmostEqual(feat["returns"][tf], 0.0, places=12, msg=tf)
        for tf, anchor in feat["anchor_ms"].items():
            if anchor is not None:
                self.assertLessEqual(anchor, t0 + 2 * 3600 * 1000 - TIMEFRAMES_MS[tf])

    def test_irregular_gap_within_tolerance_uses_nearest(self) -> None:
        t0 = 1_700_000_000_000
        engine = ReturnEngine(symbols=("BTCUSDT",))
        engine.ingest("BTCUSDT", t0, 100.0)
        engine.ingest("BTCUSDT", t0 + 30_000, 100.0)  # 30s gap, 1m tol 60s
        engine.ingest("BTCUSDT", t0 + 120_000, 110.0)
        feat = engine.feature("BTCUSDT", t0 + 120_000)
        self.assertAlmostEqual(feat["returns"]["1m"], math.log(1.1), places=12)

    def test_gap_beyond_tolerance_is_unknown(self) -> None:
        t0 = 1_700_000_000_000
        engine = ReturnEngine(symbols=("BTCUSDT",))
        engine.ingest("BTCUSDT", t0 - 130_000, 100.0)
        engine.ingest("BTCUSDT", t0, 110.0)
        feat = engine.feature("BTCUSDT", t0)
        # Anchor (t0-130s) is 70s behind the 1m target (t0-60s): too stale.
        self.assertIsNone(feat["returns"]["1m"])

    def test_tolerance_boundary_accepted(self) -> None:
        self.assertEqual(anchor_tolerance_ms(60_000), 60_000)
        self.assertEqual(anchor_tolerance_ms(86_400_000), 4_320_000)
        t0 = 1_700_000_000_000
        engine = ReturnEngine(symbols=("BTCUSDT",))
        engine.ingest("BTCUSDT", t0 - 60_000, 100.0)
        engine.ingest("BTCUSDT", t0, 110.0)
        feat = engine.feature("BTCUSDT", t0)
        self.assertAlmostEqual(feat["returns"]["1m"], math.log(1.1), places=12)

    def test_invalid_prices_and_unknown_symbols_refused(self) -> None:
        engine = ReturnEngine(symbols=("BTCUSDT",))
        for bad in (0.0, -5.0, float("nan"), float("inf")):
            self.assertFalse(engine.ingest("BTCUSDT", 1_700_000_000_000, bad))
        self.assertFalse(engine.ingest("DOGEUSDT", 1_700_000_000_000, 100.0))
        self.assertEqual(engine.dropped_unknown, 1)
        feat = engine.feature("BTCUSDT", 1_700_000_000_001)
        self.assertIsNone(feat["current_price"])

    def test_out_of_order_dropped_same_bucket_coalesced(self) -> None:
        t0 = 1_700_000_000_000
        series = SymbolPriceSeries()
        self.assertTrue(series.ingest(t0 + 1_000, 100.0))
        self.assertTrue(series.ingest(t0 + 2_000, 101.0))  # same bucket
        self.assertEqual(series.coalesced, 1)
        self.assertEqual(series.latest(), (t0 - (t0 % BUCKET_MS), 101.0))
        self.assertFalse(series.ingest(t0 + 500, 99.0))  # older event time
        self.assertEqual(series.dropped_late, 1)
        self.assertEqual(series.latest()[1], 101.0)

    def test_series_bounded(self) -> None:
        series = SymbolPriceSeries()
        base = 1_700_000_000_000
        for i in range(MAX_BUCKETS + 500):
            self.assertTrue(series.ingest(base + i * BUCKET_MS, 100.0))
        self.assertEqual(len(series.buckets()), MAX_BUCKETS)

    def test_restore_round_trip(self) -> None:
        t0 = 1_700_000_000_000
        engine = _two_level_engine(t0, 3600 * 1000, 100.0, 102.0)
        as_of = t0 + 3600 * 1000
        before = engine.feature("BTCUSDT", as_of)
        series = engine._series["BTCUSDT"]
        fresh = SymbolPriceSeries()
        fresh.restore(series.buckets())
        engine2 = ReturnEngine(symbols=("BTCUSDT",))
        engine2._series["BTCUSDT"] = fresh
        after = engine2.feature("BTCUSDT", as_of)
        self.assertEqual(before["returns"], after["returns"])

    def test_stats_shape(self) -> None:
        t0 = 1_700_000_000_000
        engine = ReturnEngine(symbols=("BTCUSDT",))
        engine.ingest("BTCUSDT", t0, 100.0)
        engine.ingest("BTCUSDT", t0 + 10_000, 101.0)
        stats = engine.stats()
        self.assertEqual(stats["BTCUSDT"]["samples"], 2)
        self.assertEqual(stats["BTCUSDT"]["updates"], 2)
        self.assertGreaterEqual(stats["BTCUSDT"]["span_ms"], 0)


class ProbeReturnsWiringTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        from microstructure_probe.persistence import PersistenceStore
        from microstructure_probe.probe import MarketProbe
        from test_detectors import test_config

        self.temp_dir = tempfile.mkdtemp(prefix="probe_ret_test_")
        self.db_path = Path(self.temp_dir) / "probe_ret.db"
        self.store = PersistenceStore(db_path=self.db_path)
        self.store.sample_interval_ms = {}
        self.probe = MarketProbe(test_config())
        self.probe.set_persistence(self.store)

    def tearDown(self) -> None:
        self.store.close()
        try:
            self.db_path.unlink(missing_ok=True)
            self.db_path.parent.rmdir()
        except OSError:
            pass

    def _markprice(self, event_ms: int, price: str = "100") -> str:
        return json.dumps({
            "stream": "!markPrice@arr@1s",
            "data": [{"E": event_ms, "T": 999_999, "s": "BTCUSDT",
                      "p": price, "r": "0.0001"}],
        })

    def test_valid_markprice_feeds_engine(self) -> None:
        """Two valid mark prices 10s apart land as two engine samples."""
        import time as _time

        from microstructure_probe.probe import MarketProbe
        from test_detectors import test_config

        t0 = 1_700_000_000_000
        clock = [t0]
        probe = MarketProbe(
            test_config(), wall_clock_ms=lambda: float(clock[0]),
            monotonic=lambda: 10.0)
        probe.set_persistence(self.store)
        for step in (0, 10_000):
            clock[0] = t0 + step
            probe._handle_message(self._markprice(t0 + step, "100"))
        stats = probe.returns.stats()
        self.assertEqual(stats["BTCUSDT"]["samples"], 2)

    def test_skew_rejected_markprice_never_reaches_engine(self) -> None:
        stale_ms = int(time.time() * 1000) - 6000
        self.probe._handle_message(self._markprice(stale_ms, "100"))
        self.assertEqual(self.probe.stats.rejected_timestamp, 1)
        self.assertNotIn("BTCUSDT", self.probe.returns.stats())
        with self.store._get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM rejected_observations")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_log_summary_persists_return_features(self) -> None:
        now_ms = int(time.time() * 1000)
        self.probe._handle_message(self._markprice(now_ms, "100"))
        self.probe.log_summary(final=False)
        latest = self.store.latest_return_features()
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["symbol"], "BTCUSDT")
        self.assertEqual(latest[0]["current_price"], 100.0)

    def test_universe_matches_config(self) -> None:
        self.assertEqual(self.probe.universe.active_symbols(), ("BTCUSDT",))

    def test_sampling_config_loads_from_file(self) -> None:
        import tempfile as _tf

        from microstructure_probe.config import load_config

        with _tf.TemporaryDirectory() as tmp:
            path = Path(tmp) / "probe.json"
            path.write_text(json.dumps({
                "symbols": ["BTCUSDT"],
                "summary_interval_seconds": 30,
                "stale_after_seconds": 10,
                "max_event_clock_skew_ms": 5000,
                "observation_sample_ms": {"bookTicker": 2000},
                "liquidation": {
                    "window_seconds": 10,
                    "individual_notional_usdt": {"BTCUSDT": 1000.0},
                    "window_notional_usdt": {"BTCUSDT": 2000.0}},
                "funding": {"history_size": 100, "minimum_samples": 30,
                            "lower_percentile": 0.05, "upper_percentile": 0.95},
                "volume": {"bucket_seconds": 10, "history_buckets": 120,
                           "minimum_buckets": 30, "z_score_threshold": 3.0},
            }), encoding="utf-8")
            config = load_config(path)
        self.assertEqual(config.observation_sample_ms, {"bookTicker": 2000})

    def test_new_modules_have_no_trading_paths(self) -> None:
        forbidden = ["/fapi/v1/order", "x-mbx-apikey", "create_order",
                     "place_order", "api_secret", "set_leverage"]
        root = Path(__file__).parent.parent / "src" / "microstructure_probe"
        for name in ("universe.py", "returns.py", "dashboard.py"):
            content = (root / name).read_text(encoding="utf-8").lower()
            for term in forbidden:
                self.assertNotIn(term, content, f"{name}: {term}")


if __name__ == "__main__":
    unittest.main()
