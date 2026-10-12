"""P1-08 VWAP + realized volatility + range + structure tests.

Known-value style, no network. Covers: VWAP math/zero-denom/warmup,
volatility fixtures/zero/insufficient/irregular/no-lookahead, range
high-low/position/flat/expansion/baselines, swings/relations/breakouts/
confirmation delay, engine scoping, probe wiring + HOT exclusion,
persistence round-trip, dashboard + APIs, peer-engine regressions,
safety.
"""

import json
import math
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from microstructure_probe.dashboard import (
    DashboardServer,
    render_structure_section,
)
from microstructure_probe.market_structure import (
    MarketStructureEngine,
    find_swings,
    range_record,
    realized_vol,
    structure_record,
    vwap_record,
)
from microstructure_probe.persistence import PersistenceStore
from microstructure_probe.probe import MarketProbe

from test_detectors import test_config


T0 = 1_700_000_000_000
BA = (T0 // 60_000) * 60_000  # minute-aligned base for grid tests


def _temp_store(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="struct_test_"))
    testcase.addCleanup(
        lambda: [p.unlink(missing_ok=True) for p in sorted(tmp.rglob("*"), reverse=True)]
        or tmp.rmdir())
    db_path = tmp / "struct.db"
    store = PersistenceStore(db_path=db_path)
    store.init_db()
    testcase.addCleanup(store.close)
    return store


def _flow_horizon(base=4.0, notional=500.0, trades=4, window_ms=60_000,
                  warmup=True, as_of_ms=T0):
    return {"base_volume": base, "notional": notional, "trades": trades,
            "window_ms": window_ms, "warmup_complete": warmup,
            "as_of_ms": as_of_ms}


class VwapTest(unittest.TestCase):
    def test_exact_known_vwap(self) -> None:
        rec = vwap_record(_flow_horizon(base=4.0, notional=500.0), 100.0, T0)
        self.assertEqual(rec["vwap"], 125.0)
        self.assertEqual(rec["displacement_abs"], -25.0)
        self.assertAlmostEqual(rec["displacement_pct"], -20.0)
        self.assertAlmostEqual(rec["displacement_bps"], -2000.0)
        self.assertEqual(rec["reference_source"], "markPrice")
        self.assertEqual(rec["trades"], 4)
        self.assertTrue(rec["warmup_complete"])

    def test_zero_denominator_is_unknown(self) -> None:
        rec = vwap_record(_flow_horizon(base=0.0, notional=0.0), 100.0, T0)
        self.assertIsNone(rec["vwap"])
        self.assertIsNone(rec["displacement_bps"])
        self.assertIsNone(rec["displacement_pct"])

    def test_missing_reference_is_unknown(self) -> None:
        for ref in (None, 0.0, -5.0, float("nan")):
            rec = vwap_record(_flow_horizon(), ref, T0)
            self.assertIsNone(rec["vwap"], ref)

    def test_multi_horizon_passthrough(self) -> None:
        engine = MarketStructureEngine(symbols=("BTCUSDT",))
        flow = {"horizons": {
            "1m": _flow_horizon(base=1.0, notional=100.0),
            "3m": _flow_horizon(base=3.0, notional=303.0),
            "5m": _flow_horizon(base=0.0, notional=0.0),
            "15m": _flow_horizon(base=5.0, notional=500.0)},
                "other": "ignored"}
        price = {"current_price": 101.0, "sample_age_ms": 100}
        rec = engine.snapshot_symbol("BTCUSDT", T0, flow, price, [])
        self.assertEqual(rec["vwap"]["1m"]["vwap"], 100.0)
        self.assertEqual(rec["vwap"]["3m"]["vwap"], 101.0)
        self.assertIsNone(rec["vwap"]["5m"]["vwap"])
        self.assertEqual(rec["vwap"]["15m"]["vwap"], 100.0)
        self.assertEqual(rec["reference_source"], "markPrice")

    def test_engine_unknown_symbol_refused(self) -> None:
        engine = MarketStructureEngine(symbols=("BTCUSDT",))
        rec = engine.snapshot_symbol("XRPUSDT", T0, {}, {}, [])
        self.assertFalse(rec["subscribed"])
        self.assertFalse(rec["live"])
        self.assertEqual(engine.dropped_unknown, 1)

    def test_engine_stats_shape(self) -> None:
        engine = MarketStructureEngine(symbols=("BTCUSDT",))
        engine.snapshot_symbol("BTCUSDT", T0, {"horizons": {}}, {}, [])
        stats = engine.stats()
        self.assertEqual(stats["symbols_evaluated"], 1)
        self.assertEqual(stats["queue_high_water"], 0)
        self.assertEqual(stats["queue_depth"], 0)
        self.assertEqual(stats["latency_ms"]["count"], 1)
        self.assertIsNotNone(stats["latency_ms"]["p50"])


class VolatilityTest(unittest.TestCase):
    def _rising(self, n=8, start=100.0, step=1.0, base=T0, gap=10_000):
        return [(base + i * gap, start + i * step) for i in range(n)]

    def test_known_log_return_fixture(self) -> None:
        # Window (T0+10k, T0+70k]: in-window prices 102 x5 flat then 103.
        buckets = [(T0 + i * 10_000, p)
                   for i, p in enumerate([100.0, 101.0, 102.0] + [102.0] * 4
                                         + [103.0])]
        rec = realized_vol(buckets, T0 + 70_000, 60_000)
        rb = math.log(103.0 / 102.0)
        self.assertEqual(rec["returns"], 5)
        self.assertAlmostEqual(rec["realized_vol"], abs(rb))
        self.assertTrue(rec["warmed"])

    def test_zero_movement_is_measured_zero(self) -> None:
        buckets = self._rising(n=8, step=0.0)
        rec = realized_vol(buckets, T0 + 70_000, 60_000)
        self.assertEqual(rec["realized_vol"], 0.0)
        self.assertTrue(rec["warmed"])

    def test_insufficient_samples_is_unknown(self) -> None:
        buckets = self._rising(n=4)
        rec = realized_vol(buckets, T0 + 30_000, 60_000)
        self.assertEqual(rec["returns"], 3)
        self.assertIsNone(rec["realized_vol"])
        self.assertFalse(rec["warmed"])

    def test_short_span_is_unknown(self) -> None:
        buckets = [(T0 + i * 5_000, 100.0 + i) for i in range(8)]
        rec = realized_vol(buckets, T0 + 35_000, 60_000)
        self.assertEqual(rec["returns"], 7)
        self.assertIsNone(rec["realized_vol"])  # span 35s < 60s window

    def test_irregular_timestamps(self) -> None:
        # 91 jittered buckets over a 15m window: full grid coverage.
        buckets = [(BA - 900_000 + i * 10_000 + (5_000 if i % 7 == 0 else 0),
                    100.0 + i * 0.1)
                   for i in range(91)]
        rec = realized_vol(buckets, BA, 900_000)
        self.assertTrue(rec["warmed"])
        self.assertGreater(rec["realized_vol"], 0.0)
        self.assertEqual(rec["returns"], 90)

    def test_no_lookahead_future_buckets_invisible(self) -> None:
        buckets = self._rising(n=10)
        early = realized_vol(buckets, T0 + 40_000, 60_000)
        # Only buckets <= as_of participate: 5 buckets -> 4 returns.
        self.assertEqual(early["returns"], 4)
        self.assertIsNone(early["realized_vol"])


class RangeTest(unittest.TestCase):
    def test_high_low_range_position(self) -> None:
        buckets = [(BA + i * 10_000, p)
                   for i, p in enumerate([100.0, 104.0, 101.0, 109.0,
                                           102.0, 107.0])]
        rec = range_record(buckets, BA + 50_000, 60_000, 106.0)
        self.assertEqual(rec["high"], 109.0)
        self.assertEqual(rec["low"], 100.0)
        self.assertEqual(rec["range_abs"], 9.0)
        self.assertAlmostEqual(rec["range_pct"], 0.09)
        self.assertAlmostEqual(rec["range_position"], 6.0 / 9.0)

    def test_flat_range_position_unknown(self) -> None:
        buckets = [(BA + i * 10_000, 100.0) for i in range(6)]
        rec = range_record(buckets, BA + 50_000, 60_000, 100.0)
        self.assertEqual(rec["range_abs"], 0.0)
        self.assertIsNone(rec["range_position"])

    def test_expansion_ratio_known(self) -> None:
        buckets = []
        for b in range(11):
            base = BA - 600_000 + b * 60_000
            lo, hi = (100.0, 104.0) if b == 10 else (100.0, 102.0)
            for i in range(6):
                buckets.append((base + i * 10_000, lo if i % 2 == 0 else hi))
        rec = range_record(buckets, BA + 60_000, 60_000, 103.0)
        self.assertEqual(rec["baseline_blocks"], 10)
        self.assertAlmostEqual(rec["expansion_ratio"], 2.0)
        # Zero-variance baseline -> z stays null (UNKNOWN).
        self.assertIsNone(rec["expansion_z"])

    def test_expansion_z_known(self) -> None:
        buckets = []
        ranges = [2.0 + (i % 3) for i in range(10)]  # 2,3,4,2,3,4,...
        for b in range(11):
            base = BA - 600_000 + b * 60_000
            width = 4.0 if b == 10 else ranges[b]
            for i in range(6):
                buckets.append((base + i * 10_000,
                                100.0 if i % 2 == 0 else 100.0 + width))
        rec = range_record(buckets, BA + 60_000, 60_000, 102.0)
        self.assertEqual(rec["baseline_blocks"], 10)
        hist = ranges
        mean = sum(hist) / 10
        var = sum((v - mean) ** 2 for v in hist) / 10
        self.assertAlmostEqual(rec["expansion_ratio"], 4.0 / (sorted(hist)[5]))
        self.assertAlmostEqual(rec["expansion_z"],
                               (4.0 - mean) / math.sqrt(var))

    def test_insufficient_baseline_is_unknown(self) -> None:
        buckets = [(BA + i * 10_000, 100.0 + (i % 2)) for i in range(6)]
        rec = range_record(buckets, BA + 50_000, 60_000, 100.5)
        self.assertEqual(rec["baseline_blocks"], 0)
        self.assertIsNone(rec["expansion_ratio"])
        self.assertIsNone(rec["expansion_z"])
        self.assertIsNotNone(rec["high"])


class StructureTest(unittest.TestCase):
    def _series(self, prices, base=T0, gap=10_000):
        return [(base + i * gap, float(p)) for i, p in enumerate(prices)]

    def test_swing_high_and_low_confirmed(self) -> None:
        buckets = self._series([5, 4, 3, 2, 1, 2, 3, 4, 9, 4, 3, 2, 1])
        highs, lows = find_swings(buckets)
        self.assertEqual(highs, [(T0 + 80_000, 9.0)])
        self.assertEqual(lows, [(T0 + 40_000, 1.0)])

    def test_unconfirmed_tail_never_pivots(self) -> None:
        # Global max sits on the last bucket: no lookahead -> no pivot.
        buckets = self._series([1, 2, 3, 4, 5, 6, 7, 8, 9])
        highs, lows = find_swings(buckets)
        self.assertEqual(highs, [])
        rec = structure_record(buckets, T0 + 80_000, 9.0)
        self.assertEqual(rec["swing_highs"], [])

    def test_confirmation_delay_exact(self) -> None:
        # Peak at index 4 confirms exactly when bucket 7 lands.
        buckets = self._series([1, 2, 3, 4, 9, 4, 3, 2, 1])
        early_highs, _ = find_swings(buckets[:7])
        self.assertEqual(early_highs, [])
        late_highs, _ = find_swings(buckets[:8])
        self.assertEqual(late_highs, [(T0 + 40_000, 9.0)])

    def test_higher_high_lower_low_relations(self) -> None:
        prices = [1, 2, 3, 2, 1, 2, 3, 4, 9, 4, 3, 2, 1, 2, 3, 8, 12,
                  5, 4, 3, 2, 1]
        buckets = self._series(prices)
        rec = structure_record(buckets, T0 + 210_000, 4.0)
        self.assertEqual([h["price"] for h in rec["swing_highs"]], [9.0, 12.0])
        self.assertTrue(rec["higher_high"])
        self.assertFalse(rec["lower_high"])
        self.assertEqual(rec["distance_to_swing_high_bps"],
                         (4.0 - 12.0) / 12.0 * 10_000.0)

    def test_lower_high_lower_low_relations(self) -> None:
        # Down-trending series: lower highs AND lower lows (honest labels).
        prices = [9, 5, 4, 3, 5, 8, 4, 3, 2, 4, 6, 3, 2, 1]
        buckets = self._series(prices)
        rec = structure_record(buckets, T0 + 130_000, 2.0)
        self.assertTrue(rec["lower_high"])
        self.assertFalse(rec["higher_high"])
        self.assertTrue(rec["lower_low"])
        self.assertFalse(rec["higher_low"])

    def test_single_pivot_relations_unknown(self) -> None:
        buckets = self._series([5, 4, 3, 2, 1, 2, 3, 4, 9, 4, 3, 2, 1])
        rec = structure_record(buckets, T0 + 120_000, 3.0)
        self.assertIsNone(rec["higher_high"])
        self.assertIsNone(rec["lower_low"])

    def test_breakout_above_below_inside(self) -> None:
        buckets = [(BA - 1_200_000 + i * 10_000, 100.0) for i in range(120)]
        as_of = BA + 60_000
        self.assertEqual(
            structure_record(buckets, as_of, 105.0)["breakout_state"],
            "ABOVE_PRIOR_RANGE")
        self.assertEqual(
            structure_record(buckets, as_of, 95.0)["breakout_state"],
            "BELOW_PRIOR_RANGE")
        self.assertEqual(
            structure_record(buckets, as_of, 100.0)["breakout_state"],
            "INSIDE_PRIOR_RANGE")

    def test_breakout_unknown_without_history(self) -> None:
        rec = structure_record([], T0, 100.0)
        self.assertEqual(rec["breakout_state"], "UNKNOWN")
        self.assertEqual(rec["swing_highs"], [])
        self.assertIsNone(rec["freshness_ms"])


class ProbeStructureWiringTest(unittest.TestCase):
    def _probe(self, now_ms):
        from microstructure_probe.history_store import HistoryStore

        store = _temp_store(self)
        hist = HistoryStore(store.db_path.parent / "historical.db")
        probe = MarketProbe(test_config(),
                            wall_clock_ms=lambda: float(now_ms),
                            monotonic=lambda: 10.0,
                            persistence_store=store,
                            research_history_store=hist)
        return probe, store

    def _markprice(self, event_ms, price):
        return json.dumps({
            "stream": "!markPrice@arr@1s",
            "data": [{"E": event_ms, "T": 999_999, "s": "BTCUSDT",
                      "p": str(price), "r": "0.0001"}],
        })

    def _aggtrade(self, event_ms, price="100", qty="1", maker=False):
        return json.dumps({
            "stream": "btcusdt@aggTrade",
            "data": {"E": event_ms, "T": event_ms, "s": "BTCUSDT",
                     "p": price, "q": qty, "m": maker},
        })

    def test_log_summary_persists_structure(self) -> None:
        now_ms = int(time.time() * 1000)
        base = (now_ms // 10_000) * 10_000 - 70_000
        # Advancing wall clock: each message is fresh at its own event
        # time (a fixed clock would skew-reject everything older than 5s).
        clock = [float(base)]
        store = _temp_store(self)
        from microstructure_probe.history_store import HistoryStore
        hist = HistoryStore(store.db_path.parent / "historical.db")
        probe = MarketProbe(test_config(),
                            wall_clock_ms=lambda: clock[0],
                            monotonic=lambda: 10.0,
                            persistence_store=store,
                            research_history_store=hist)
        for i in range(8):
            clock[0] = float(base + i * 10_000)
            probe._handle_message(
                self._markprice(base + i * 10_000, 100.0 + i))
            probe._handle_message(
                self._aggtrade(base + i * 10_000 + 1, "100", "1", False))
        probe.log_summary(final=False)
        latest = store.latest_structure_features()
        self.assertEqual(len(latest), 1)
        rec = latest[0]
        self.assertEqual(rec["symbol"], "BTCUSDT")
        self.assertTrue(rec["subscribed"])
        self.assertEqual(rec["reference_source"], "markPrice")
        self.assertAlmostEqual(rec["vwap"]["1m"]["vwap"], 100.0)
        self.assertGreater(rec["volatility"]["1m"]["realized_vol"], 0.0)
        self.assertIn(rec["structure"]["breakout_state"],
                      ("ABOVE_PRIOR_RANGE", "BELOW_PRIOR_RANGE",
                       "INSIDE_PRIOR_RANGE", "UNKNOWN"))

    def test_hot_symbol_gets_no_structure(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, store = self._probe(now_ms)
        probe._handle_message(json.dumps({
            "stream": "!markPrice@arr@1s",
            "data": [{"E": now_ms, "T": 999_999, "s": "XRPUSDT",
                      "p": "2.5", "r": "0.0001"}],
        }))
        probe.log_summary(final=False)
        symbols = [f["symbol"] for f in store.latest_structure_features()]
        self.assertNotIn("XRPUSDT", symbols)

    def test_summary_carries_structure_block(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        summary = probe.build_summary(final=True)
        self.assertIn("structure", summary)
        self.assertIn("latency_ms", summary["structure"])

    def test_peer_regressions_intact(self) -> None:
        """P1-04..P1-07 wiring untouched: returns/flow/book/OI all advance."""
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        probe._handle_message(
            self._markprice(now_ms, "100"))
        probe._handle_message(json.dumps({
            "stream": "btcusdt@aggTrade",
            "data": {"E": now_ms, "T": now_ms, "s": "BTCUSDT",
                     "p": "100", "q": "2", "m": True},
        }))
        probe._handle_message(json.dumps({
            "stream": "btcusdt@depth20@100ms",
            "data": {"E": now_ms, "T": now_ms, "s": "BTCUSDT",
                     "U": 1, "u": 2, "pu": 1,
                     "b": [["99.0", "1.0"]], "a": [["101.0", "1.0"]]},
        }))
        probe.oi.ingest("BTCUSDT", now_ms, now_ms, 500.0)
        self.assertEqual(len(probe.returns.buckets("BTCUSDT")), 1)
        flow = probe.flow.snapshot_all(now_ms)[0]
        self.assertEqual(flow["horizons"]["1m"]["sell_notional"], 200.0)
        book = probe.book.snapshot_all(now_ms)[0]
        self.assertEqual(book["book"]["best_bid"], 99.0)
        self.assertEqual(probe.oi.snapshot_all(now_ms)[0]["current_oi"], 500.0)
        struct = probe.structure.snapshot_symbol(
            "BTCUSDT", now_ms, flow,
            probe.returns.feature("BTCUSDT", now_ms),
            probe.returns.buckets("BTCUSDT"))
        self.assertEqual(struct["vwap"]["1m"]["vwap"], 100.0)


class StructurePersistenceTest(unittest.TestCase):
    def test_round_trip_replace(self) -> None:
        store = _temp_store(self)
        self.assertEqual(store.latest_structure_features(), [])
        store.store_structure_features([{"symbol": "BTCUSDT", "live": True}])
        store.store_structure_features([{"symbol": "BTCUSDT", "live": False}])
        latest = store.latest_structure_features()
        self.assertEqual(len(latest), 1)
        self.assertFalse(latest[0]["live"])


class DashboardStructureTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="struct_dash_test_"))
        self.addCleanup(
            lambda: [p.unlink(missing_ok=True)
                     for p in sorted(tmp.rglob("*"), reverse=True)]
            or tmp.rmdir())
        self.store = PersistenceStore(db_path=tmp / "dash.db")
        self.store.init_db()
        self.addCleanup(self.store.close)
        self.server = DashboardServer(host="127.0.0.1", port=0,
                                     db_path=self.store.db_path,
                                     history_db_path=self.store.db_path.parent / "hist.db").start()
        self.addCleanup(self.server.stop)
        self.base = f"http://127.0.0.1:{self.server.bound_port()}"

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path,
                                        timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.request.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def _seed(self):
        self.store.store_structure_features([{
            "symbol": "BTCUSDT", "subscribed": True, "live": True,
            "as_of_ms": T0, "reference_price": 102.0,
            "reference_source": "markPrice", "price_age_ms": 500,
            "vwap": {"1m": {"vwap": 101.0, "displacement_bps": 99.0,
                            "trades": 10, "notional": 1010.0,
                            "warmup_complete": True}},
            "volatility": {"1m": {"realized_vol": 0.0012, "returns": 6,
                                  "warmed": True},
                           "5m": {"realized_vol": None, "returns": 0,
                                  "warmed": False}},
            "ranges": {"5m": {"high": 103.0, "low": 100.0,
                              "range_position": 0.667,
                              "expansion_ratio": 1.5}},
            "structure": {"higher_high": True, "lower_high": False,
                          "higher_low": None, "lower_low": None,
                          "breakout_state": "INSIDE_PRIOR_RANGE"},
        }])
        self.store.store_telemetry_snapshot({
            "runtimeSeconds": 10.0,
            "safety": {"BOT_MODE": "observe", "apiKeysUsed": 0,
                       "realOrdersSent": 0, "realCapitalAtRisk": 0,
                       "maxDrawdownKillSwitchActive": False,
                       "authenticatedClientsPresent": False,
                       "orderExecutionPathPresent": False},
            "dataQuality": {"expectedStreams": 11, "activeStreams": 11},
        })

    def test_apis_empty_is_404(self) -> None:
        for path in ("/api/features/vwap", "/api/features/volatility",
                     "/api/features/structure"):
            code, _ = self._get(path)
            self.assertEqual(code, 404, path)

    def test_vwap_api_shape(self) -> None:
        self._seed()
        code, body = self._get("/api/features/vwap")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["horizons"], ["1m", "3m", "5m", "15m"])
        symbol = payload["symbols"][0]
        self.assertEqual(symbol["vwap"]["1m"]["vwap"], 101.0)
        self.assertEqual(symbol["reference_source"], "markPrice")

    def test_volatility_api_shape(self) -> None:
        self._seed()
        code, body = self._get("/api/features/volatility")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        symbol = payload["symbols"][0]
        self.assertEqual(symbol["volatility"]["1m"]["realized_vol"], 0.0012)
        self.assertEqual(symbol["ranges"]["5m"]["expansion_ratio"], 1.5)

    def test_structure_api_shape(self) -> None:
        self._seed()
        code, body = self._get("/api/features/structure")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        symbol = payload["symbols"][0]
        self.assertEqual(symbol["structure"]["breakout_state"],
                         "INSIDE_PRIOR_RANGE")
        self.assertTrue(symbol["structure"]["higher_high"])

    def test_overview_renders_section_cleanly(self) -> None:
        # P1-09 IA: VWAP/volatility/structure detail lives on
        # /symbol/:symbol; /overview links there.
        self._seed()
        code, body = self._get("/overview")
        self.assertEqual(code, 200)
        self.assertIn("/symbol/BTCUSDT", body)
        code, detail = self._get("/symbol/BTCUSDT")
        self.assertEqual(code, 200)
        self.assertIn("VWAP / volatility / structure", detail)
        self.assertIn("INSIDE_PRIOR_RANGE", detail)
        for page in (body, detail):
            self.assertNotIn("<button", page.lower())
            for forbidden in ("entry", "place_order", "BUY SIGNAL",
                               "SELL SIGNAL", "bullish", "bearish",
                               "BREAKOUT SIGNAL", "LONG", "SHORT"):
                self.assertNotIn(forbidden, page)

    def test_render_empty_is_honest(self) -> None:
        self.assertIn("No structure features yet",
                      render_structure_section([]))


class StructureSafetyTest(unittest.TestCase):
    def test_module_has_no_trading_paths(self) -> None:
        root = (Path(__file__).resolve().parent.parent
                / "src" / "microstructure_probe")
        text = (root / "market_structure.py").read_text(encoding="utf-8").lower()
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
