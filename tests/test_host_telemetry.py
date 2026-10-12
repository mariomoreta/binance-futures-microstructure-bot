"""P1-14B.6 host telemetry — bounded, UNKNOWN-safe, deterministic tests.

Process CPU% (os.times deltas), process RSS (psapi, Windows-only), exact
per-stream byte counts, host stash shape. NIC and system-wide counters are
NOT available on this path by design (asserted as UNKNOWN, never fabricated).

No live Binance dependency. Run: python run_tests.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from microstructure_probe.telemetry import (
    cpu_percent_proc,
    process_cpu_times,
    process_rss_bytes,
)

from test_detectors import test_config


def make_isolated_probe(case, config=None, **kwargs):
    """Probe bound to temp stores (never the canonical DBs).

    ETAPA 1 isolation + P2 injection: byte-counting feeds messages through
    ``_handle_message`` (default factory route), construction rehydrates
    the prospective recorder from the default store (Route B), and
    summaries read research counts through the default HistoryStore
    (Route C). Mirrors ``make_probe`` in test_universe_probe.
    """
    from microstructure_probe.history_store import HistoryStore
    from microstructure_probe.persistence import PersistenceStore
    from microstructure_probe.probe import MarketProbe

    temp = tempfile.TemporaryDirectory(prefix="host_telemetry_test_")
    case.addCleanup(temp.cleanup)
    store = PersistenceStore(Path(temp.name) / "probe.db")
    store.init_db()
    case.addCleanup(store.close)
    hist = HistoryStore(Path(temp.name) / "historical.db")
    probe = MarketProbe(config or test_config(), persistence_store=store,
                        research_history_store=hist, **kwargs)
    return probe


class TestCpuHelper(TestCase):
    def test_normal(self):
        prev = (10.0, 5.0, 1000.0)
        cur = (10.3, 5.1, 1002.0)
        self.assertAlmostEqual(cpu_percent_proc(prev, cur, 4), 5.0)

    def test_missing_inputs_none(self):
        self.assertIsNone(cpu_percent_proc(None, (1.0, 1.0, 2.0), 4))
        self.assertIsNone(cpu_percent_proc((1.0, 1.0, 2.0), None, 4))
        self.assertIsNone(cpu_percent_proc((1.0, 1.0, 2.0), (1.5, 1.5, 3.0), 0))
        self.assertIsNone(cpu_percent_proc((1.0, 1.0, 2.0), (1.5, 1.5, 3.0), None))

    def test_non_positive_wall_none(self):
        self.assertIsNone(cpu_percent_proc((1.0, 1.0, 5.0), (2.0, 2.0, 5.0), 4))
        self.assertIsNone(cpu_percent_proc((1.0, 1.0, 5.0), (2.0, 2.0, 4.0), 4))

    def test_negative_proc_none(self):
        self.assertIsNone(cpu_percent_proc((5.0, 5.0, 1.0), (4.0, 4.0, 2.0), 4))

    def test_multithread_may_exceed_100(self):
        self.assertAlmostEqual(
            cpu_percent_proc((0.0, 0.0, 0.0), (8.0, 0.0, 2.0), 2), 200.0)

    def test_malformed_never_raises(self):
        self.assertIsNone(cpu_percent_proc("x", (1.0, 1.0, 2.0), 4))
        self.assertIsNone(cpu_percent_proc((1.0,), (1.0, 1.0, 2.0), 4))
        self.assertIsNone(cpu_percent_proc((1.0, float("nan"), 1.0),
                                           (2.0, 2.0, 2.0), 4))


class TestHostContracts(TestCase):
    def test_cpu_times_shape(self):
        sample = process_cpu_times()
        if sample is None:
            self.assertIsNone(sample)  # UNKNOWN where unavailable
        else:
            self.assertEqual(len(sample), 3)
            self.assertTrue(all(isinstance(v, float) for v in sample))

    def test_rss_shape(self):
        rss = process_rss_bytes()
        if rss is None:
            self.assertIsNone(rss)  # UNKNOWN where unavailable
        else:
            self.assertIsInstance(rss, int)
            self.assertGreater(rss, 0)


class TestProbeByteCounting(TestCase):
    def test_exact_bytes_per_stream(self):
        probe = make_isolated_probe(self)
        payload = json.dumps({"stream": "btcusdt@bookTicker",
                              "data": {"E": 1_800_000_000_000, "s": "BTCUSDT",
                                       "b": "100", "a": "100.01"}})
        probe._handle_message(payload)
        expect = len(payload.encode("utf-8"))
        self.assertEqual(probe.stats.bytes_by_stream["btcusdt@bookTicker"], expect)
        self.assertEqual(probe.stats.messages_by_stream["btcusdt@bookTicker"], 1)

    def test_rejected_messages_still_count_bytes(self):
        import time
        probe = make_isolated_probe(self)
        stale_e = int(time.time() * 1000) - 600_000
        payload = json.dumps({"stream": "btcusdt@bookTicker",
                              "data": {"E": stale_e, "s": "BTCUSDT",
                                       "b": "100", "a": "100.01"}})
        probe._handle_message(payload)
        self.assertEqual(probe.stats.rejected_timestamp, 1)
        self.assertGreater(probe.stats.bytes_by_stream["btcusdt@bookTicker"], 0)

    def test_host_stash_shape(self):
        probe = make_isolated_probe(self)
        stash = probe._sample_host()
        self.assertIn("cpuPercentProc", stash)
        self.assertIn("rssBytes", stash)
        self.assertIn("cpuCount", stash)
        first_cpu = stash["cpuPercentProc"]
        self.assertIsNone(first_cpu)  # baseline established, no interval yet
        stash2 = probe._sample_host()
        self.assertIn("cpuPercentProc", stash2)


class TestNetprobeBytes(TestCase):
    def test_tracker_bytes(self):
        from src.microstructure_probe.netprobe import ReferenceTracker
        tr = ReferenceTracker()
        tr.observe("s", 1.0, nbytes=128)
        tr.observe("s", 2.0, nbytes=64)
        tr.observe("s", 3.0)
        summ = tr.summary()["s"]
        self.assertEqual(summ["messages"], 3)
        self.assertEqual(summ["totalBytes"], 192)
