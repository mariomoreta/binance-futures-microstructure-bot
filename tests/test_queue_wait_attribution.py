"""Lag attribution: socket arrival splits received-E into queue + transit.

2026-10-15 (pilot probe-20261015T000730Z post-mortem): received_ms was
stamped at handler entry, so local queueing (library max_queue=4096,
TCP buffers, event-loop stalls) was invisible and every skew reject
looked like network lag. These fixture tests prove the minimal
instrumentation on TEMP stores exclusively:

- arrival stamps decompose received-E == queue_wait + transit, with
  E-T staying the exchange-side component;
- UNKNOWN arrival is never recorded (never zero-filled);
- the skew guard still rejects identically (threshold untouched).

No live traffic, no threshold change. Run: python run_tests.py
"""

import json
import unittest

from test_detectors import test_config
from test_probe import make_isolated_probe


def _agg(symbol="BTCUSDT", event_ms=99000, txn_ms=98900):
    return {"stream": "btcusdt@aggTrade",
            "data": {"E": event_ms, "T": txn_ms, "s": symbol,
                     "p": "100", "q": "1"}}


def _probe(case, **kwargs):
    return make_isolated_probe(
        case, test_config(), clock_sync=None,
        wall_clock_ms=lambda: 100000.0, monotonic=lambda: 100.0,
        perf_counter_ns=lambda: 5_000_000_000, **kwargs)


class QueueWaitAttributionTest(unittest.TestCase):
    def test_decomposition_identity_on_fixture(self) -> None:
        probe = _probe(self)
        probe._handle_message(
            json.dumps(_agg()), arrival_ms=99750.0,
            arrival_mono_ns=4_750_000_000)
        latency = probe.build_summary(final=True)["latency"]
        key = "aggTrade/BTCUSDT"
        raw = latency["rawEventLagMs"][key]["p50"]
        queue = latency["queueWaitMs"][key]["p50"]
        transit = latency["transitLagMs"][key]["p50"]
        self.assertEqual(raw, 1000.0)
        self.assertEqual(queue, 250.0)
        self.assertEqual(transit, 750.0)
        self.assertAlmostEqual(queue + transit, raw)
        # Exchange-side component untouched by local queueing.
        self.assertEqual(
            latency["exchangeEventMinusTransactionMs"][key]["p50"], 100.0)

    def test_unknown_arrival_never_recorded_as_zero(self) -> None:
        probe = _probe(self)
        probe._handle_message(json.dumps(_agg()))
        latency = probe.build_summary(final=True)["latency"]
        key = "aggTrade/BTCUSDT"
        self.assertEqual(latency["rawEventLagMs"][key]["p50"], 1000.0)
        self.assertNotIn("queueWaitMs", latency)
        self.assertNotIn("transitLagMs", latency)

    def test_rejected_message_keeps_attribution_and_counts(self) -> None:
        probe = _probe(self)
        old = _agg(event_ms=90000, txn_ms=89900)
        probe._handle_message(
            json.dumps(old), arrival_ms=99750.0,
            arrival_mono_ns=4_750_000_000)
        self.assertEqual(probe.stats.discarded_clock_skew, 1)
        self.assertEqual(probe.stats.rejected_timestamp, 1)
        latency = probe.build_summary(final=True)["latency"]
        key = "aggTrade/BTCUSDT"
        # 10000 = 250 queue + 9750 transit: the reject is dominated by
        # transit here, measured — not assumed.
        self.assertEqual(latency["rawEventLagMs"][key]["p50"], 10000.0)
        self.assertEqual(latency["queueWaitMs"][key]["p50"], 250.0)
        self.assertEqual(latency["transitLagMs"][key]["p50"], 9750.0)

    def test_skew_threshold_untouched(self) -> None:
        probe = _probe(self)
        self.assertEqual(probe.config.max_event_clock_skew_ms, 5000)
        probe._handle_message(json.dumps(_agg(event_ms=95000)))
        self.assertEqual(probe.stats.rejected_timestamp, 0)
        probe._handle_message(json.dumps(_agg(event_ms=94999)))
        self.assertEqual(probe.stats.rejected_timestamp, 1)

    def test_markprice_array_records_per_symbol_attribution(self) -> None:
        probe = _probe(self)
        payload = {"stream": "!markPrice@arr@1s", "data": [
            {"s": "BTCUSDT", "E": 99000}]}
        probe._handle_message(
            json.dumps(payload), arrival_ms=99750.0,
            arrival_mono_ns=4_750_000_000)
        latency = probe.build_summary(final=True)["latency"]
        key = "markPrice/BTCUSDT"
        self.assertEqual(latency["queueWaitMs"][key]["p50"], 250.0)
        self.assertEqual(latency["transitLagMs"][key]["p50"], 750.0)


if __name__ == "__main__":
    unittest.main()
