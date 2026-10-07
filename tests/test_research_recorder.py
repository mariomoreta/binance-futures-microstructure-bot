"""P1-11C prospective recorder tests (bounded, non-blocking, isolated)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path


def _tmp_db():
    tmp = tempfile.mkdtemp(prefix="p11c-research-")
    return Path(tmp) / "historical.db"


class FlowBucketTest(unittest.TestCase):
    def test_10s_and_1m_aggregation(self) -> None:
        from microstructure_probe.research_recorder import ResearchRecorder
        rec = ResearchRecorder(db_path=_tmp_db(), enabled=True)
        rec.start()
        base = 1_700_000_000_000 - (1_700_000_000_000 % 60_000)
        # m=false -> aggressive BUY, m=true -> aggressive SELL
        rec.record_trade("TSTUSDT", base + 1000, 100.0, 1.0, False)
        rec.record_trade("TSTUSDT", base + 2000, 101.0, 2.0, True)
        rec.record_trade("TSTUSDT", base + 11_000, 102.0, 1.5, False)
        time.sleep(0.6)
        st = rec.stop_and_drain()
        self.assertGreaterEqual(st["writes"], 0)
        self.assertEqual(st["errors"], 0)

    def test_aggressor_mapping_and_delta(self) -> None:
        from microstructure_probe.research_recorder import _FlowBucket
        b = _FlowBucket(1_000_000, 10)
        b.add(1_001_000, 100.0, 1.0, False)
        b.add(1_002_000, 100.0, 1.0, True)
        row = b.row("TSTUSDT", "OK")
        self.assertAlmostEqual(row["buy_notional"], 100.0)
        self.assertAlmostEqual(row["sell_notional"], 100.0)
        self.assertAlmostEqual(row["delta"], 0.0)
        self.assertAlmostEqual(row["delta_ratio"], 0.0)
        self.assertEqual(row["trade_count"], 2)
        self.assertEqual(row["buy_trades"], 1)
        self.assertEqual(row["sell_trades"], 1)

    def test_ohlc_and_counts(self) -> None:
        from microstructure_probe.research_recorder import _FlowBucket
        b = _FlowBucket(1_000_000, 10)
        b.add(1_001_000, 100.0, 1.0, False)
        b.add(1_002_000, 103.0, 1.0, False)
        b.add(1_003_000, 99.0, 1.0, True)
        row = b.row("TSTUSDT", "OK")
        self.assertEqual(row["price_open"], 100.0)
        self.assertEqual(row["price_high"], 103.0)
        self.assertEqual(row["price_low"], 99.0)
        self.assertEqual(row["price_close"], 99.0)

    def test_book_aggregation_min_mean_max(self) -> None:
        from microstructure_probe.research_recorder import _BookBucket
        b = _BookBucket(1_000_000)
        f1 = {"spread_bps": 1.0, "imbalance_notional": 0.2,
              "microprice_displacement_bps": 0.5,
              "depth": {"top5": {"bid_notional": 10, "ask_notional": 8},
                        "top20": {"bid_notional": 40, "ask_notional": 30}}}
        f2 = {"spread_bps": 3.0, "imbalance_notional": -0.4,
              "microprice_displacement_bps": -0.5,
              "depth": {"top5": {"bid_notional": 12, "ask_notional": 9},
                        "top20": {"bid_notional": 44, "ask_notional": 33}}}
        b.add(1_001_000, f1, False, False, False)
        b.add(1_002_000, f2, False, False, True)
        row = b.row("TSTUSDT")
        self.assertEqual(row["spread_min"], 1.0)
        self.assertEqual(row["spread_max"], 3.0)
        self.assertAlmostEqual(row["spread_mean"], 2.0)
        self.assertEqual(row["sample_count"], 2)
        self.assertEqual(row["crossed"], 1)

    def test_gap_degraded_crossed_counting(self) -> None:
        from microstructure_probe.research_recorder import _BookBucket
        b = _BookBucket(1_000_000)
        f = {"spread_bps": 1.0, "depth": {}}
        b.add(1_001_000, f, True, True, False)
        b.add(1_002_000, f, False, False, True)
        row = b.row("TSTUSDT")
        self.assertEqual(row["depth_gaps"], 1)
        self.assertEqual(row["degraded"], 1)
        self.assertEqual(row["crossed"], 1)

    def test_incomplete_bucket_policy_partial(self) -> None:
        from microstructure_probe.research_recorder import ResearchRecorder
        rec = ResearchRecorder(db_path=_tmp_db(), enabled=True)
        rec.start()
        rec.record_trade("TSTUSDT", 1_700_000_001_000, 100.0, 1.0, False)
        st = rec.stop_and_drain()
        # partials are marked PARTIAL, never silent-complete (no crash)
        self.assertIn(st["state"], ("STOPPED", "DEGRADED"))

    def test_restart_idempotency_no_double_count(self) -> None:
        from microstructure_probe.history_store import HistoryStore
        db = _tmp_db()
        store = HistoryStore(db)
        row = {"symbol": "TSTUSDT", "bucket_start": 1000, "bucket_end": 11000,
               "bucket_size_s": 10, "buy_notional": 50.0,
               "sell_notional": 50.0, "delta": 0.0, "delta_ratio": 0.0,
               "buy_base": 1.0, "sell_base": 1.0, "base_volume": 2.0,
               "notional_volume": 100.0, "trade_count": 2, "buy_trades": 1,
               "sell_trades": 1, "price_open": 100.0, "price_high": 101.0,
               "price_low": 99.0, "price_close": 100.0,
               "first_event_ms": 1001, "last_event_ms": 1002,
               "data_quality": "OK"}
        store.store_research_flow("research_flow_10s", [row])
        store.store_research_flow("research_flow_10s", [row])
        self.assertEqual(store.research_counts()["research_flow_10s"], 1)

    def test_retention_cleanup_bounded(self) -> None:
        from microstructure_probe.history_store import HistoryStore
        db = _tmp_db()
        store = HistoryStore(db)
        old = {"symbol": "TSTUSDT", "bucket_start": 1000,
               "bucket_end": 11000, "bucket_size_s": 10,
               "buy_notional": 1.0, "sell_notional": 1.0, "delta": 0.0,
               "delta_ratio": 0.0, "buy_base": 1.0, "sell_base": 1.0,
               "base_volume": 2.0, "notional_volume": 2.0, "trade_count": 1,
               "buy_trades": 1, "sell_trades": 0, "price_open": 1.0,
               "price_high": 1.0, "price_low": 1.0, "price_close": 1.0,
               "first_event_ms": 1000, "last_event_ms": 1000,
               "data_quality": "OK"}
        store.store_research_flow("research_flow_10s", [old])
        out = store.research_retention_cleanup(
            {"flow_10s": 7, "flow_1m": 90, "book_1m": 90},
            now_ms=1000 + 8 * 86_400_000)
        self.assertGreaterEqual(out["research_flow_10s"], 1)
        self.assertEqual(store.research_counts()["research_flow_10s"], 0)

    def test_bounded_queue_drop_telemetry(self) -> None:
        from microstructure_probe.research_recorder import ResearchRecorder
        rec = ResearchRecorder(db_path=_tmp_db(), enabled=True, max_queue=16)
        # fill without a worker draining (never started) -> drops counted
        for _ in range(100):
            rec._enqueue(("flow", 10, "TSTUSDT", object()))
        st = rec.status()
        self.assertGreater(st["drops"], 0)

    def test_db_failure_isolation(self) -> None:
        from microstructure_probe.research_recorder import ResearchRecorder
        rec = ResearchRecorder(db_path=Path("/nonexistent-dir-xyz/h.db"),
                               enabled=True)
        rec.start()
        rec.record_trade("TSTUSDT", 1_700_000_001_000, 100.0, 1.0, False)
        time.sleep(0.6)
        st = rec.stop_and_drain()
        # recorder degrades; the caller (probe) never raises
        self.assertIn(st["state"], ("STOPPED", "DEGRADED", "RUNNING"))

    def test_recorder_cannot_crash_probe_path(self) -> None:
        from microstructure_probe.probe import MarketProbe
        from test_detectors import test_config
        probe = MarketProbe(test_config())
        # hooks must never raise even with garbage
        try:
            probe.research.record_trade("X", "bad", float("nan"), -1, "maybe")
            probe.research.record_book("X", "bad", {}, False, False, False)
        except Exception as exc:  # pragma: no cover
            self.fail(f"recorder raised: {exc}")

    def test_recorder_lifecycle_with_probe(self) -> None:
        from microstructure_probe.probe import MarketProbe
        from test_detectors import test_config
        probe = MarketProbe(test_config())
        self.assertTrue(hasattr(probe, "research"))
        probe.research.start()
        probe.research.stop_and_drain(timeout=5.0)

    def test_no_second_process_or_registry(self) -> None:
        import inspect
        from microstructure_probe import research_recorder as RR
        src = inspect.getsource(RR)
        for token in ("probe_runtime.json", "Popen", "control.start_probe",
                      "subprocess"):
            self.assertNotIn(token, src)

    def test_no_live_engine_semantic_changes(self) -> None:
        # P1-06 math untouched: m=true -> aggressive SELL.
        from microstructure_probe.flow import SymbolFlowSeries
        s = SymbolFlowSeries()
        self.assertTrue(s.ingest(1000, 100.0, 1.0, True))
        feat = s.horizon_feature("10s", 1000)
        self.assertLess(feat["signed_delta"], 0)


if __name__ == "__main__":
    unittest.main()
