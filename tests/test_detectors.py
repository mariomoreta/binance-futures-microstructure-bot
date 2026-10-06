import unittest

from microstructure_probe.config import (
    ClockSyncConfig,
    FundingConfig,
    LiquidationConfig,
    ProbeConfig,
    VolumeConfig,
)
from microstructure_probe.detectors import EventDetectors


def test_config() -> ProbeConfig:
    return ProbeConfig(
        symbols=("BTCUSDT",),
        summary_interval_seconds=30,
        stale_after_seconds=10,
        max_event_clock_skew_ms=5000,
        telemetry_max_samples=100,
        clock_sync=ClockSyncConfig(
            interval_seconds=600,
            samples=3,
            request_timeout_seconds=1.0,
        ),
        liquidation=LiquidationConfig(
            window_seconds=10,
            individual_notional_usdt={"BTCUSDT": 1000.0},
            window_notional_usdt={"BTCUSDT": 2000.0},
        ),
        funding=FundingConfig(
            history_size=10,
            minimum_samples=3,
            lower_percentile=0.05,
            upper_percentile=0.95,
        ),
        volume=VolumeConfig(
            bucket_seconds=10,
            history_buckets=10,
            minimum_buckets=3,
            z_score_threshold=3.0,
        ),
    )


class DetectorsTest(unittest.TestCase):
    def test_individual_liquidation_notional(self) -> None:
        detector = EventDetectors(test_config())
        events = detector.liquidation(
            timestamp_ms=1000,
            symbol="BTCUSDT",
            price=100.0,
            quantity=10.0,
            side="SELL",
        )
        self.assertEqual(events[0].event_type, "large_liquidation_individual")
        self.assertEqual(events[0].magnitude, 1000.0)

    def test_liquidation_window_accumulates(self) -> None:
        detector = EventDetectors(test_config())
        detector.liquidation(
            timestamp_ms=1000, symbol="BTCUSDT", price=100.0, quantity=9.0, side="SELL"
        )
        events = detector.liquidation(
            timestamp_ms=2000, symbol="BTCUSDT", price=100.0, quantity=11.0, side="SELL"
        )
        self.assertIn("large_liquidation_window", [event.event_type for event in events])

    def test_funding_waits_for_minimum_history(self) -> None:
        detector = EventDetectors(test_config())
        for index, rate in enumerate((0.001, 0.002, 0.003)):
            self.assertEqual(
                detector.funding_rate(
                    timestamp_ms=index, symbol="BTCUSDT", price=100.0, rate=rate
                ),
                [],
            )
        events = detector.funding_rate(
            timestamp_ms=4, symbol="BTCUSDT", price=100.0, rate=0.1
        )
        self.assertEqual(events[0].event_type, "extreme_funding_rate")

    def test_volume_spike_uses_completed_buckets(self) -> None:
        detector = EventDetectors(test_config())
        for bucket, notional in enumerate((100.0, 110.0, 90.0, 1000.0, 100.0)):
            events = detector.aggregate_trade(
                timestamp_ms=bucket * 10_000,
                symbol="BTCUSDT",
                price=1.0,
                quantity=notional,
            )
        self.assertEqual(events[0].event_type, "volume_spike")
        self.assertEqual(events[0].magnitude, 1000.0)

    def test_liquidation_near_miss_telemetry(self) -> None:
        detector = EventDetectors(test_config())
        detector.liquidation(
            timestamp_ms=1000,
            symbol="BTCUSDT",
            price=100.0,
            quantity=7.5,
            side="SELL",
        )
        snapshot = detector.telemetry_snapshot()["liquidation"]["BTCUSDT"]
        self.assertEqual(snapshot["individual"]["atOrAbove"]["75pct"], 1)
        self.assertEqual(snapshot["individual"]["atOrAbove"]["100pct"], 0)

    def test_volume_telemetry_reports_warmup_and_evaluation(self) -> None:
        detector = EventDetectors(test_config())
        for bucket, notional in enumerate((100.0, 110.0, 90.0, 1000.0, 100.0)):
            detector.aggregate_trade(
                timestamp_ms=bucket * 10_000,
                symbol="BTCUSDT",
                price=1.0,
                quantity=notional,
            )
        snapshot = detector.telemetry_snapshot()["volume"]["BTCUSDT"]
        self.assertTrue(snapshot["warmupComplete"])
        self.assertEqual(snapshot["evaluatedBuckets"], 1)
        self.assertEqual(snapshot["thresholdCrossings"], 1)
        self.assertEqual(snapshot["zScore"]["count"], 1)

    def test_funding_marks_repeated_samples_as_non_independent(self) -> None:
        detector = EventDetectors(test_config())
        for timestamp in range(4):
            detector.funding_rate(
                timestamp_ms=timestamp,
                symbol="BTCUSDT",
                price=100.0,
                rate=0.001,
            )
        snapshot = detector.telemetry_snapshot()["funding"]["BTCUSDT"]
        self.assertEqual(snapshot["samplesReceived"], 4)
        self.assertEqual(snapshot["distinctRates"], 1)
        self.assertEqual(snapshot["valueChanges"], 1)
        self.assertEqual(
            snapshot["independenceNote"], "repeated_stream_samples_are_not_independent"
        )


if __name__ == "__main__":
    unittest.main()
