"""P1-07 order-book + open-interest tests (known-value style, no network).

Covers: top-of-book math, depth sums, imbalance, microprice, slope,
concentration + coverage, sequence-gap policy, freshness, invalid-depth
exclusion, skew-guard wiring, sampling independence, OI client parsing,
OI deltas/rates/acceleration, context labels, staleness, poll bounds,
restart persistence, schema migration, HOT scoping, dashboard + APIs,
P1-06 flow regression, safety.
"""

import json
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from microstructure_probe import dashboard
from microstructure_probe.book import (
    BookEngine,
    SymbolBookState,
    book_features,
    parse_levels,
)
from microstructure_probe.dashboard import (
    DashboardServer,
    render_book_section,
    render_oi_section,
)
from microstructure_probe.open_interest import (
    OI_HORIZON_ORDER,
    OpenInterestPoller,
    OpenInterestTracker,
    parse_oi_payload,
    price_oi_context,
)
from microstructure_probe.persistence import PersistenceStore
from microstructure_probe.probe import MarketProbe

from test_detectors import test_config


T0 = 1_700_000_000_000


def _snap(tracker, symbol, as_of_ms, subscribed=True,
           price_return_1m=None):
    """Single-symbol OI record from the multi-symbol tracker."""
    records = tracker.snapshot_all(
        as_of_ms, {symbol: price_return_1m})
    assert len(records) == 1
    return records[0]


def _bids_asks():
    return ([["99.00", "2.0"], ["98.00", "3.0"]],
            [["101.00", "1.0"], ["102.00", "4.0"]])


def _temp_store(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="book_oi_test_"))
    testcase.addCleanup(
        lambda: [p.unlink(missing_ok=True) for p in sorted(tmp.rglob("*"), reverse=True)]
        or tmp.rmdir())
    db_path = tmp / "book_oi.db"
    store = PersistenceStore(db_path=db_path)
    store.init_db()
    testcase.addCleanup(store.close)
    return store


class BookMathTest(unittest.TestCase):
    def test_best_bid_ask_mid_spread(self) -> None:
        bids, asks = _bids_asks()
        feat = book_features(
            parse_levels(bids), parse_levels(asks))
        self.assertEqual(feat["best_bid"], 99.0)
        self.assertEqual(feat["best_ask"], 101.0)
        self.assertEqual(feat["mid"], 100.0)
        self.assertEqual(feat["spread_abs"], 2.0)
        self.assertEqual(feat["spread_bps"], 200.0)
        self.assertFalse(feat["crossed"])

    def test_wire_order_never_assumed(self) -> None:
        bids = [["98.00", "3.0"], ["99.00", "2.0"]]
        asks = [["102.00", "4.0"], ["101.00", "1.0"]]
        feat = book_features(parse_levels(bids), parse_levels(asks))
        self.assertEqual(feat["best_bid"], 99.0)
        self.assertEqual(feat["best_ask"], 101.0)
        self.assertEqual(feat["depth"]["top1"]["bid_base"], 2.0)
        self.assertEqual(feat["depth"]["top1"]["ask_base"], 1.0)

    def test_depth_sums_top_n(self) -> None:
        bids = [[f"{100 - i}.00", "1.0"] for i in range(1, 11)]
        asks = [[f"{100 + i}.00", "2.0"] for i in range(1, 11)]
        feat = book_features(parse_levels(bids), parse_levels(asks))
        top5 = feat["depth"]["top5"]
        self.assertEqual(top5["bid_base"], 5.0)
        self.assertEqual(top5["ask_base"], 10.0)
        self.assertAlmostEqual(top5["bid_notional"],
                               sum(100 - i for i in range(1, 6)))
        self.assertAlmostEqual(top5["ask_notional"],
                               sum((100 + i) * 2 for i in range(1, 6)))
        self.assertEqual(top5["bid_levels"], 5)
        self.assertEqual(feat["depth"]["top20"]["bid_levels"], 10)

    def test_imbalance_formula_and_zero_denominator(self) -> None:
        self.assertIsNone(book_features([], []))
        feat = book_features(parse_levels([["100.00", "3.0"]]),
                             parse_levels([["101.00", "1.0"]]))
        self.assertAlmostEqual(feat["imbalance_qty"], (3.0 - 1.0) / 4.0)
        self.assertAlmostEqual(
            feat["imbalance_notional"],
            (300.0 - 101.0) / (300.0 + 101.0))

    def test_microprice_known_values(self) -> None:
        bids, asks = _bids_asks()
        feat = book_features(parse_levels(bids), parse_levels(asks))
        # (101*2 + 99*1) / 3 = 100.333...
        self.assertAlmostEqual(feat["microprice"], 301.0 / 3.0)
        self.assertAlmostEqual(feat["microprice_displacement_bps"],
                               (301.0 / 3.0 - 100.0) / 100.0 * 10_000.0)

    def test_microprice_zero_top_qty_is_unknown(self) -> None:
        state = SymbolBookState()
        # Zero-qty top levels are filtered; side empties -> invalid.
        self.assertFalse(state.ingest(T0, 1, None, [["100.00", "0.0"]],
                                      [["101.00", "1.0"]]))
        self.assertEqual(state.invalid_updates, 1)

    def test_crossed_top_kept_and_counted(self) -> None:
        state = SymbolBookState()
        self.assertTrue(state.ingest(T0, 1, None, [["102.00", "1.0"]],
                                                  [["101.00", "1.0"]]))
        self.assertTrue(state.features["crossed"])
        self.assertEqual(state.crossed_tops, 1)
        self.assertLess(state.features["spread_abs"], 0.0)

    def test_slope_known_fixture(self) -> None:
        bids, asks = _bids_asks()
        feat = book_features(parse_levels(bids), parse_levels(asks))
        # Bid: d=[100,200]bps, C=[198,492] -> 118200/50000 = 2.364.
        self.assertAlmostEqual(
            feat["slopes"]["bid_slope_notional_per_bp"], 2.364)
        # Ask: d=[100,200]bps, C=[101,101+408=509] -> (10100+101800)/50000.
        self.assertAlmostEqual(
            feat["slopes"]["ask_slope_notional_per_bp"],
            (100 * 101.0 + 200 * 509.0) / 50000.0)
        asym = feat["slopes"]["asymmetry"]
        self.assertTrue(-1.0 <= asym <= 1.0)

    def test_concentration_and_coverage(self) -> None:
        bids = [["100.01", "5.0"], ["99.00", "5.0"]]
        asks = [["100.02", "5.0"], ["101.00", "5.0"]]
        feat = book_features(parse_levels(bids), parse_levels(asks))
        conc_bid = feat["concentration"]["bid"]
        # Mid ~100.015; top bid within 5bps, tail at ~100bps.
        self.assertGreater(conc_bid["within_5bps"], 0.0)
        self.assertLess(conc_bid["within_5bps"], 1.0)
        self.assertAlmostEqual(conc_bid["within_25bps"],
                               conc_bid["within_5bps"])
        # Thin book that never reaches 25bps -> band is None, coverage shown.
        thin = book_features(parse_levels([["100.00", "1.0"]]),
                             parse_levels([["100.01", "1.0"]]))
        self.assertIsNone(thin["concentration"]["bid"]["within_25bps"])
        self.assertGreater(
            thin["concentration"]["bid"]["coverage_max_dist_bps"], 0.0)

    def test_invalid_levels_excluded(self) -> None:
        state = SymbolBookState()
        for bad_bids, bad_asks in (
                ("nope", [["101.00", "1.0"]]),
                ([["100.00", "1.0"]], [["101.00", "-2.0"]]),
                ([["nan", "1.0"]], [["101.00", "1.0"]]),
                ([["0.00", "1.0"]], [["101.00", "1.0"]]),
                ([], [["101.00", "1.0"]]),
        ):
            self.assertFalse(state.ingest(T0, 1, None, bad_bids, bad_asks))
        self.assertEqual(state.invalid_updates, 5)
        self.assertIsNone(state.features)


class SequenceIntegrityTest(unittest.TestCase):
    def test_first_update_always_accepted(self) -> None:
        engine = BookEngine(symbols=("BTCUSDT",))
        bids, asks = _bids_asks()
        self.assertTrue(engine.ingest("BTCUSDT", T0, 100, 55, bids, asks))
        rec = engine.snapshot_all(T0)[0]
        self.assertTrue(rec["live"])
        self.assertFalse(rec["degraded"])

    def test_gap_marks_degraded_until_chained(self) -> None:
        engine = BookEngine(symbols=("BTCUSDT",))
        bids, asks = _bids_asks()
        engine.ingest("BTCUSDT", T0, 100, 99, bids, asks)
        engine.ingest("BTCUSDT", T0 + 100, 101, 500, bids, asks)  # pu != 100
        rec = engine.snapshot_all(T0 + 100)[0]
        self.assertTrue(rec["degraded"])
        self.assertFalse(rec["live"])
        self.assertEqual(rec["sequence_gaps"], 1)
        self.assertIsNotNone(rec["book"])  # full snapshot still usable
        engine.ingest("BTCUSDT", T0 + 200, 102, 101, bids, asks)  # chained
        rec = engine.snapshot_all(T0 + 200)[0]
        self.assertFalse(rec["degraded"])
        self.assertTrue(rec["live"])
        self.assertEqual(rec["sequence_gaps"], 1)

    def test_strictly_older_snapshot_never_regresses(self) -> None:
        engine = BookEngine(symbols=("BTCUSDT",))
        bids, asks = _bids_asks()
        engine.ingest("BTCUSDT", T0 + 100, 100, 99, bids, asks)
        self.assertFalse(engine.ingest("BTCUSDT", T0, 101, 100, bids, asks))
        book = engine._books["BTCUSDT"]
        self.assertEqual(book.messages_processed, 1)
        self.assertEqual(book.dropped_late, 1)
        self.assertEqual(book.newest_ms, T0 + 100)

    def test_freshness_and_unknown_symbol(self) -> None:
        engine = BookEngine(symbols=("BTCUSDT",))
        bids, asks = _bids_asks()
        engine.ingest("BTCUSDT", T0, 100, 99, bids, asks)
        rec = engine.snapshot_all(T0 + 1500)[0]
        self.assertEqual(rec["freshness_ms"], 1500)
        self.assertFalse(engine.ingest("XRPUSDT", T0, 1, None, bids, asks))
        self.assertEqual(engine.dropped_unknown, 1)

    def test_latency_distribution_present(self) -> None:
        engine = BookEngine(symbols=("BTCUSDT",))
        bids, asks = _bids_asks()
        engine.ingest("BTCUSDT", T0, 100, 99, bids, asks)
        stats = engine.stats()
        self.assertEqual(stats["messages_processed"], 1)
        self.assertEqual(stats["queue_high_water"], 0)
        self.assertEqual(stats["queue_depth"], 0)
        self.assertEqual(stats["latency_ms"]["count"], 1)
        self.assertIsNotNone(stats["latency_ms"]["p50"])


class OIClientTest(unittest.TestCase):
    def test_parse_valid_payload(self) -> None:
        self.assertEqual(
            parse_oi_payload({"symbol": "BTCUSDT",
                              "openInterest": "95643.451",
                              "time": 1791335501318}),
            (95643.451, 1791335501318))

    def test_parse_rejects_garbage(self) -> None:
        for bad in (None, [], "x",
                    {"openInterest": "abc"},
                    {"openInterest": "-5"},
                    {"openInterest": "inf"},
                    {"symbol": "BTCUSDT"}):
            self.assertIsNone(parse_oi_payload(bad))

    def test_parse_tolerates_missing_time(self) -> None:
        self.assertEqual(parse_oi_payload({"openInterest": "10.5"}),
                         (10.5, None))


class OIEngineTest(unittest.TestCase):
    def _tracker(self, step_s=60, count=5, start_oi=1000.0, step_oi=10.0):
        tracker = OpenInterestTracker(symbols=("BTCUSDT",))
        base = T0
        for i in range(count):
            tracker.ingest("BTCUSDT", base + i * step_s * 1000,
                           base + i * step_s * 1000, start_oi + i * step_oi)
        return tracker, base

    def test_delta_rate_known_values(self) -> None:
        tracker, base = self._tracker()
        as_of = base + 4 * 60_000
        h1 = _snap(tracker, "BTCUSDT", as_of, True)["horizons"]["1m"]
        self.assertEqual(h1["current_oi"], 1040.0)
        self.assertEqual(h1["anchor_oi"], 1030.0)
        self.assertEqual(h1["delta"], 10.0)
        self.assertAlmostEqual(h1["delta_pct"], 10.0 / 1030.0)
        self.assertAlmostEqual(h1["rate_per_s"], 10.0 / 60.0)

    def test_acceleration_zero_on_linear(self) -> None:
        tracker, base = self._tracker()
        accel = _snap(tracker, "BTCUSDT", base + 4 * 60_000, True)
        self.assertAlmostEqual(accel["acceleration_per_s2"], 0.0)

    def test_acceleration_known_values(self) -> None:
        tracker = OpenInterestTracker(symbols=("BTCUSDT",))
        base = T0
        # 0,0,+30 over three minutes -> rate jumps 0 -> 0.5/s at the end.
        for i, oi in ((0, 1000.0), (1, 1000.0), (2, 1030.0)):
            tracker.ingest("BTCUSDT", base + i * 60_000,
                           base + i * 60_000, oi)
        accel = _snap(tracker, "BTCUSDT", base + 2 * 60_000, True)
        self.assertAlmostEqual(accel["acceleration_per_s2"],
                               (30.0 / 60.0 - 0.0) / 60.0)

    def test_insufficient_history_is_unknown(self) -> None:
        tracker, base = self._tracker(count=2)
        rec = _snap(tracker, "BTCUSDT", base + 60_000, True)
        self.assertIsNone(rec["horizons"]["5m"]["delta"])
        self.assertIsNone(rec["horizons"]["15m"]["delta"])
        self.assertIsNone(rec["acceleration_per_s2"])
        self.assertIsNotNone(rec["horizons"]["1m"]["delta"])

    def test_irregular_timestamps_use_actual_elapsed(self) -> None:
        tracker = OpenInterestTracker(symbols=("BTCUSDT",))
        tracker.ingest("BTCUSDT", T0, T0, 1000.0)
        tracker.ingest("BTCUSDT", T0 + 97_000, T0 + 97_000, 1010.0)
        h1 = _snap(tracker, "BTCUSDT", T0 + 97_000, True)["horizons"]["1m"]
        self.assertEqual(h1["delta"], 10.0)
        self.assertAlmostEqual(h1["rate_per_s"], 10.0 / 97.0)

    def test_no_lookahead_future_sample_invisible(self) -> None:
        tracker, base = self._tracker(count=3)
        # Query before the 3rd sample exists in as-of terms.
        rec = _snap(tracker, "BTCUSDT", base + 60_000, True)
        self.assertEqual(rec["horizons"]["1m"]["current_oi"], 1010.0)

    def test_stale_flag_and_freshness(self) -> None:
        tracker = OpenInterestTracker(symbols=("BTCUSDT",),
                                      stale_after_ms=180_000)
        tracker.ingest("BTCUSDT", T0, T0, 1000.0)
        fresh = _snap(tracker, "BTCUSDT", T0 + 60_000, True)
        self.assertFalse(fresh["stale"])
        self.assertEqual(fresh["freshness_ms"], 60_000)
        old = _snap(tracker, "BTCUSDT", T0 + 300_000, True)
        self.assertTrue(old["stale"])

    def test_context_labels(self) -> None:
        cases = {(0.1, 5.0): "PRICE_UP_OI_UP",
                 (0.1, -5.0): "PRICE_UP_OI_DOWN",
                 (-0.1, 5.0): "PRICE_DOWN_OI_UP",
                 (-0.1, -5.0): "PRICE_DOWN_OI_DOWN",
                 (0.0, 5.0): "MIXED",
                 (0.1, 0.0): "MIXED",
                 (None, 5.0): "UNKNOWN",
                 (0.1, None): "UNKNOWN"}
        for (ret, delta), label in cases.items():
            self.assertEqual(price_oi_context(ret, delta), label)

    def test_unknown_symbol_refused(self) -> None:
        tracker = OpenInterestTracker(symbols=("BTCUSDT",))
        self.assertFalse(tracker.ingest("XRPUSDT", T0, T0, 10.0))
        self.assertEqual(tracker.dropped_unknown, 1)


class OIPollerTest(unittest.TestCase):
    def _poller(self, fetch_fn, symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT")):
        return OpenInterestPoller(
            symbols=symbols, fetch_fn=fetch_fn, interval_seconds=60.0,
            wall_clock_ms=lambda: float(T0))

    def test_poll_once_bounded_one_request_per_symbol(self) -> None:
        calls = []

        def fake(symbol):
            calls.append(symbol)
            return {"symbol": symbol, "openInterest": "100.0",
                    "time": T0}

        tracker = OpenInterestTracker(symbols=("BTCUSDT", "ETHUSDT",
                                               "SOLUSDT"))
        poller = self._poller(fake)
        outcome = poller.poll_once(tracker)
        self.assertEqual(outcome, {"requested": 3, "ok": 3, "failed": 0})
        self.assertEqual(sorted(calls),
                         ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        self.assertEqual(poller.requests, 3)
        self.assertEqual(poller.successes, 3)
        self.assertEqual(poller.failures, 0)

    def test_rest_failure_counted_never_raises(self) -> None:
        def boom(symbol):
            raise ConnectionError("offline")

        tracker = OpenInterestTracker(symbols=("BTCUSDT",))
        poller = self._poller(boom, symbols=("BTCUSDT",))
        outcome = poller.poll_once(tracker)
        self.assertEqual(outcome, {"requested": 1, "ok": 0, "failed": 1})
        self.assertEqual(poller.failures, 1)
        self.assertEqual(tracker.snapshot_all(T0), [])

    def test_bad_payload_counted_as_failure(self) -> None:
        tracker = OpenInterestTracker(symbols=("BTCUSDT",))
        poller = self._poller(lambda s: {"garbage": True},
                              symbols=("BTCUSDT",))
        outcome = poller.poll_once(tracker)
        self.assertEqual(outcome["failed"], 1)
        self.assertEqual(poller.failures, 1)


class BookOIPersistenceTest(unittest.TestCase):
    def test_book_features_replace_and_read(self) -> None:
        store = _temp_store(self)
        self.assertEqual(store.latest_book_features(), [])
        store.store_book_features([{"symbol": "BTCUSDT", "live": True}])
        store.store_book_features([{"symbol": "BTCUSDT", "live": False}])
        latest = store.latest_book_features()
        self.assertEqual(len(latest), 1)
        self.assertFalse(latest[0]["live"])

    def test_oi_samples_round_trip_and_retention(self) -> None:
        store = _temp_store(self)
        rows = [{"symbol": "BTCUSDT", "fetch_ms": T0 + i * 1000,
                 "exchange_time_ms": T0 + i * 1000, "oi": 1000.0 + i}
                for i in range(2100)]
        store.store_oi_samples(rows)
        loaded = store.load_oi_samples(symbol="BTCUSDT", limit=5000)
        self.assertEqual(len(loaded), 2000)
        self.assertEqual(loaded[0]["fetch_ms"], T0 + 100 * 1000)
        self.assertEqual(loaded[-1]["oi"], 1000.0 + 2099)

    def test_oi_samples_rewrite_is_idempotent(self) -> None:
        store = _temp_store(self)
        row = {"symbol": "BTCUSDT", "fetch_ms": T0,
               "exchange_time_ms": T0, "oi": 5.0}
        store.store_oi_samples([row])
        store.store_oi_samples([row])
        self.assertEqual(len(store.load_oi_samples(symbol="BTCUSDT")), 1)

    def test_oi_features_replace_and_read(self) -> None:
        store = _temp_store(self)
        self.assertEqual(store.latest_oi_features(), [])
        store.store_oi_features([{"symbol": "ETHUSDT", "current_oi": 7.0}])
        latest = store.latest_oi_features()
        self.assertEqual(latest[0]["current_oi"], 7.0)

    def test_oi_restore_continuity(self) -> None:
        store = _temp_store(self)
        base = T0
        rows = [{"symbol": "BTCUSDT", "fetch_ms": base + i * 60_000,
                 "exchange_time_ms": base + i * 60_000,
                 "oi": 1000.0 + i * 10.0} for i in range(4)]
        store.store_oi_samples(rows)
        fresh = OpenInterestTracker(symbols=("BTCUSDT",))
        self.assertEqual(fresh.restore_samples(store.load_oi_samples()), 4)
        rec = fresh.snapshot_all(base + 3 * 60_000)[0]
        self.assertEqual(rec["horizons"]["1m"]["delta"], 10.0)


class ProbeBookOIWiringTest(unittest.TestCase):
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

    def _depth(self, event_ms, u=100, pu=99, bids=None, asks=None):
        bids = bids if bids is not None else [["100.00", "1.0"]]
        asks = asks if asks is not None else [["101.00", "1.0"]]
        return json.dumps({
            "stream": "btcusdt@depth20@100ms",
            "data": {"E": event_ms, "T": event_ms, "s": "BTCUSDT",
                     "U": u - 1, "u": u, "pu": pu, "b": bids, "a": asks},
        })

    def test_skew_rejected_depth_never_reaches_book(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        probe._handle_message(self._depth(now_ms - 6000))
        self.assertEqual(probe.stats.rejected_timestamp, 1)
        self.assertEqual(probe.book.messages_processed, 0)
        self.assertEqual(probe.book.snapshot_all(now_ms), [])

    def test_sampling_does_not_alter_book_state(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, store = self._probe(now_ms)
        for i in range(5):
            probe._handle_message(
                self._depth(now_ms - 400 + i * 100, u=100 + i,
                            pu=99 + i if i else 99))
        self.assertEqual(probe.book.messages_processed, 5)
        rec = probe.book.snapshot_all(now_ms)[0]
        self.assertTrue(rec["live"])
        self.assertEqual(rec["book"]["best_bid"], 100.0)
        persisted = [o for o in store.latest_observations(limit=50)
                     if "depth" in o.get("stream_type", "")]
        self.assertLess(len(persisted), 5)

    def test_probe_gap_counter_parity(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        probe._handle_message(self._depth(now_ms - 200, u=100, pu=99))
        probe._handle_message(self._depth(now_ms - 100, u=101, pu=500))
        self.assertEqual(probe.stats.depth_sequence_gaps["BTCUSDT"], 1)
        rec = probe.book.snapshot_all(now_ms)[0]
        self.assertTrue(rec["degraded"])
        self.assertEqual(rec["sequence_gaps"], 1)

    def test_unsubscribed_hot_gets_no_book_or_oi(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        probe._handle_message(json.dumps({
            "stream": "xrpusdt@depth20@100ms",
            "data": {"E": now_ms, "T": now_ms, "s": "XRPUSDT",
                     "U": 1, "u": 2, "pu": 1,
                     "b": [["2.0", "10.0"]], "a": [["2.1", "10.0"]]},
        }))
        self.assertEqual(probe.book.messages_processed, 0)
        self.assertEqual(probe.book.dropped_unknown, 1)
        self.assertFalse(probe.oi.ingest("XRPUSDT", now_ms, now_ms, 5.0))
        self.assertEqual(probe.oi.snapshot_all(now_ms), [])

    def test_summary_carries_book_and_oi_blocks(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        probe._handle_message(self._depth(now_ms))
        summary = probe.build_summary(final=True)
        self.assertIn("book", summary)
        self.assertIn("openInterest", summary)
        self.assertEqual(summary["book"]["messages_processed"], 1)
        self.assertIn("poll", summary["openInterest"])

    def test_log_summary_persists_book_and_oi(self) -> None:
        now_ms = int(time.time() * 1000)
        probe, store = self._probe(now_ms)
        probe._handle_message(self._depth(now_ms))
        probe.oi.ingest("BTCUSDT", now_ms, now_ms, 1234.5)
        probe.log_summary(final=False)
        books = store.latest_book_features()
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["symbol"], "BTCUSDT")
        self.assertTrue(books[0]["book"]["best_bid"] == 100.0)
        ois = store.latest_oi_features()
        self.assertEqual(len(ois), 1)
        self.assertEqual(ois[0]["current_oi"], 1234.5)
        self.assertEqual(ois[0]["price_oi_context"]["1m"], "UNKNOWN")
        samples = store.load_oi_samples(symbol="BTCUSDT")
        self.assertEqual(len(samples), 1)

    def test_flow_totals_untouched_by_depth_work(self) -> None:
        """P1-06 regression: depth/OI wiring never alters flow accounting."""
        now_ms = int(time.time() * 1000)
        probe, _ = self._probe(now_ms)
        for i in range(3):
            probe._handle_message(json.dumps({
                "stream": "btcusdt@aggTrade",
                "data": {"E": now_ms - 200 + i * 100,
                         "T": now_ms - 200 + i * 100, "s": "BTCUSDT",
                         "p": "100", "q": "1", "m": i % 2 == 0},
            }))
        probe._handle_message(self._depth(now_ms))
        probe.oi.ingest("BTCUSDT", now_ms, now_ms, 999.0)
        rec = probe.flow.snapshot_all(now_ms)[0]
        self.assertEqual(rec["trades_total"], 3)
        self.assertEqual(rec["horizons"]["1m"]["buy_notional"], 100.0)
        self.assertEqual(rec["horizons"]["1m"]["sell_notional"], 200.0)


class DashboardBookOITest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="book_oi_dash_test_"))
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
        engine = BookEngine(symbols=("BTCUSDT",))
        bids, asks = _bids_asks()
        engine.ingest("BTCUSDT", T0, 100, 99, bids, asks)
        book = engine.snapshot_all(T0)[0]
        tracker = OpenInterestTracker(symbols=("BTCUSDT",))
        tracker.ingest("BTCUSDT", T0, T0, 5000.0)
        tracker.ingest("BTCUSDT", T0 + 60_000, T0 + 60_000, 5010.0)
        oi = _snap(tracker, "BTCUSDT", T0 + 60_000, True, 0.001)
        self.store.store_book_features([book])
        self.store.store_oi_features([oi])
        self.store.store_telemetry_snapshot({
            "runtimeSeconds": 10.0,
            "safety": {"BOT_MODE": "observe", "apiKeysUsed": 0,
                       "realOrdersSent": 0, "realCapitalAtRisk": 0,
                       "maxDrawdownKillSwitchActive": False,
                       "authenticatedClientsPresent": False,
                       "orderExecutionPathPresent": False},
            "dataQuality": {"expectedStreams": 11, "activeStreams": 11},
        })

    def test_book_and_oi_apis_empty_is_404(self) -> None:
        code, _ = self._get("/api/features/book")
        self.assertEqual(code, 404)
        code, _ = self._get("/api/features/open-interest")
        self.assertEqual(code, 404)

    def test_book_api_payload_shape(self) -> None:
        self._seed()
        code, body = self._get("/api/features/book")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["source"], "depth20@100ms")
        symbol = payload["symbols"][0]
        self.assertEqual(symbol["symbol"], "BTCUSDT")
        self.assertTrue(symbol["live"])
        book = symbol["book"]
        self.assertEqual(book["best_bid"], 99.0)
        self.assertEqual(book["spread_bps"], 200.0)
        self.assertIn("imbalance_notional", book)
        self.assertIn("microprice", book)
        self.assertIn("slopes", book)
        self.assertIn("concentration", book)

    def test_oi_api_payload_shape(self) -> None:
        self._seed()
        code, body = self._get("/api/features/open-interest")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["source"], "GET /fapi/v1/openInterest")
        symbol = payload["symbols"][0]
        self.assertEqual(symbol["current_oi"], 5010.0)
        self.assertEqual(symbol["horizons"]["1m"]["delta"], 10.0)
        self.assertEqual(symbol["price_oi_context"]["1m"],
                         "PRICE_UP_OI_UP")
        self.assertIn("freshness_ms", symbol)

    def test_overview_renders_book_oi_and_no_live_book(self) -> None:
        # P1-09 IA: full book/OI detail lives on /symbol/:symbol; /overview
        # stays compact but keeps DISCOVERY ONLY honesty labels.
        self._seed()
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
        self.assertIn("NO LIVE FLOW/BOOK", body)
        self.assertNotIn("<button", body.lower())
        code, detail = self._get("/symbol/BTCUSDT")
        self.assertEqual(code, 200)
        self.assertIn("Order book", detail)
        self.assertIn("Open interest", detail)
        for page in (body, detail):
            for forbidden in ("entry", "place_order", "BUY SIGNAL",
                              "SELL SIGNAL", "bullish", "bearish"):
                self.assertNotIn(forbidden, page)

    def test_render_sections_empty_are_honest(self) -> None:
        self.assertIn("No live book yet", render_book_section([]))
        self.assertIn("No live OI yet", render_oi_section([]))


class BookOISafetyTest(unittest.TestCase):
    def test_new_modules_have_no_trading_paths(self) -> None:
        root = (Path(__file__).resolve().parent.parent
                / "src" / "microstructure_probe")
        forbidden = (
            "/fapi/v1/order",
            "x-mbx-apikey",
            "create_order",
            "place_order",
            "send_order",
            "api_secret",
            "/private/",
        )
        for module in ("book.py", "open_interest.py"):
            text = (root / module).read_text(encoding="utf-8").lower()
            for term in forbidden:
                self.assertNotIn(term, text, module)


if __name__ == "__main__":
    unittest.main()
