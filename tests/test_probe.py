import json
import tempfile
import unittest
from pathlib import Path
import time

from microstructure_probe.clock import ClockSynchronizer
from microstructure_probe.probe import MarketProbe, build_stream_urls

from test_detectors import test_config


def make_isolated_probe(case, config=None, **kwargs):
    """Probe bound to a temp PersistenceStore (never the canonical DB).

    ETAPA 1 isolation: ``_handle_message`` reaches ``self.persistence``,
    whose lazy default factory would open+write the canonical
    ``data/microprobe.db`` (and the failure is swallowed as
    ``persistence_error``, so the test stays green while contaminating).
    Every fixture below that feeds messages through the probe owns a temp
    store with cleanup, mirroring ``make_probe`` in test_universe_probe.
    """
    from microstructure_probe.persistence import PersistenceStore

    temp = tempfile.TemporaryDirectory(prefix="probe_isolated_test_")
    case.addCleanup(temp.cleanup)
    store = PersistenceStore(Path(temp.name) / "probe.db")
    store.init_db()
    case.addCleanup(store.close)
    probe = MarketProbe(config or test_config(), **kwargs)
    probe.set_persistence(store)
    return probe


class ProbeTest(unittest.TestCase):
    @staticmethod
    def _clock(offset_ms: float = 0.0) -> ClockSynchronizer:
        clock = ClockSynchronizer(sample_count=1, fetch_server_time=lambda: 0)
        clock.offset_ms = offset_ms
        clock.rtt_ms = 1.0
        return clock

    def test_streams_use_current_routed_endpoints(self) -> None:
        urls = build_stream_urls(test_config())
        self.assertIn("/public/stream?streams=", urls["public"])
        self.assertIn("btcusdt@bookTicker", urls["public"])
        self.assertIn("btcusdt@depth20@100ms", urls["public"])
        self.assertIn("/market/stream?streams=", urls["market"])
        self.assertIn("!forceOrder@arr", urls["market"])
        self.assertIn("!markPrice@arr@1s", urls["market"])
        self.assertIn("btcusdt@aggTrade", urls["market"])

    def test_future_or_stale_payload_is_discarded(self) -> None:
        probe = make_isolated_probe(self)
        payload = {
            "stream": "btcusdt@aggTrade",
            "data": {
                "E": int(time.time() * 1000) - 6000,
                "T": int(time.time() * 1000) - 6000,
                "s": "BTCUSDT",
                "p": "100",
                "q": "1",
            },
        }
        probe._handle_message(json.dumps(payload))
        self.assertEqual(probe.stats.discarded_clock_skew, 1)

    def test_latency_is_separated_by_stream_and_e_from_t(self) -> None:
        probe = make_isolated_probe(
            self,
            test_config(),
            clock_sync=self._clock(50.0),
            wall_clock_ms=lambda: 1000.0,
            monotonic=lambda: 10.0,
        )
        payload = {
            "stream": "btcusdt@aggTrade",
            "data": {
                "E": 900,
                "T": 800,
                "s": "BTCUSDT",
                "p": "100",
                "q": "1",
            },
        }
        probe._handle_message(json.dumps(payload))
        latency = probe.build_summary(final=True)["latency"]
        self.assertEqual(latency["rawEventLagMs"]["aggTrade/BTCUSDT"]["p50"], 100.0)
        self.assertEqual(
            latency["correctedEventLagMs"]["aggTrade/BTCUSDT"]["p50"], 150.0
        )
        self.assertEqual(
            latency["rawTransactionLagMs"]["aggTrade/BTCUSDT"]["p50"], 200.0
        )
        self.assertEqual(
            latency["exchangeEventMinusTransactionMs"]["aggTrade/BTCUSDT"]["p50"],
            100.0,
        )

    def test_mark_price_next_funding_time_is_not_transaction_time(self) -> None:
        probe = make_isolated_probe(
            self,
            test_config(),
            clock_sync=self._clock(),
            wall_clock_ms=lambda: 1000.0,
            monotonic=lambda: 10.0,
        )
        payload = {
            "stream": "!markPrice@arr@1s",
            "data": [
                {
                    "E": 900,
                    "T": 999_999,
                    "s": "BTCUSDT",
                    "p": "100",
                    "r": "0.001",
                }
            ],
        }
        probe._handle_message(json.dumps(payload))
        latency = probe.build_summary(final=True)["latency"]
        self.assertIn("markPrice/BTCUSDT", latency["rawEventLagMs"])
        self.assertNotIn("rawTransactionLagMs", latency)

    def test_processing_latency_uses_high_resolution_monotonic_clock(self) -> None:
        ticks = iter((0, 1_000_000, 3_000_000, 6_000_000, 10_000_000))
        probe = make_isolated_probe(
            self,
            test_config(),
            clock_sync=self._clock(),
            wall_clock_ms=lambda: 1000.0,
            monotonic=lambda: 10.0,
            perf_counter_ns=lambda: next(ticks),
        )
        payload = {
            "stream": "btcusdt@aggTrade",
            "data": {"E": 900, "T": 900, "s": "BTCUSDT", "p": "100", "q": "1"},
        }
        probe._handle_message(json.dumps(payload))
        processing = probe.build_summary(final=True)["processing"]
        stats = processing["processingLatencyMs"]["aggTrade/BTCUSDT"]
        self.assertEqual(stats["p50"], 10.0)
        self.assertEqual(
            processing["parseLatencyMs"]["aggTrade/BTCUSDT"]["p50"], 1.0
        )
        self.assertEqual(
            processing["metricsLatencyMs"]["aggTrade/BTCUSDT"]["p50"], 2.0
        )
        self.assertEqual(
            processing["detectorLatencyMs"]["aggTrade/BTCUSDT"]["p50"], 3.0
        )

    def test_final_summary_aggregates_data_quality_and_safety(self) -> None:
        probe = make_isolated_probe(
            self,
            test_config(),
            clock_sync=self._clock(),
            wall_clock_ms=lambda: 1000.0,
            monotonic=lambda: 10.0,
        )
        payload = {
            "stream": "btcusdt@bookTicker",
            "data": {
                "E": 900,
                "T": 899,
                "s": "BTCUSDT",
                "b": "99",
                "a": "101",
            },
        }
        probe._handle_message(json.dumps(payload))
        summary = probe.build_summary(final=True)
        self.assertEqual(summary["kind"], "final_summary")
        self.assertEqual(summary["dataQuality"]["activeStreams"], 1)
        self.assertEqual(summary["dataQuality"]["parseErrors"], 0)
        self.assertEqual(summary["safety"]["BOT_MODE"], "observe")
        self.assertFalse(summary["safety"]["orderExecutionPathPresent"])

    def test_event_driven_force_order_silence_is_not_reported_as_stale(self) -> None:
        current = [0.0]
        probe = MarketProbe(
            test_config(),
            clock_sync=self._clock(),
            wall_clock_ms=lambda: 1000.0,
            monotonic=lambda: current[0],
        )
        probe.stats.last_seen_monotonic["!forceOrder@arr"] = 0.0
        probe.stats.first_seen_monotonic["!forceOrder@arr"] = 0.0
        current[0] = 60.0
        summary = probe.build_summary(final=True)
        self.assertNotIn("!forceOrder@arr", summary["dataQuality"]["staleStreams"])
        self.assertIn("!forceOrder@arr", summary["dataQuality"]["silentStreams"])

    def test_source_contains_no_order_or_authenticated_client_paths(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in Path("src/microstructure_probe").glob("*.py")
        ).lower()
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
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
