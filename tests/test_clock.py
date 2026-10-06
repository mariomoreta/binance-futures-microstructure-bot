import unittest

from microstructure_probe.clock import (
    ClockSynchronizer,
    calculate_clock_sample,
    corrected_lag_ms,
)


class ClockMathTest(unittest.TestCase):
    def test_clock_offset_uses_request_midpoint(self) -> None:
        sample = calculate_clock_sample(1000.0, 1015.0, 1010.0)
        self.assertEqual(sample.offset_ms, 10.0)
        self.assertEqual(sample.rtt_ms, 10.0)

    def test_corrected_event_lag_applies_offset(self) -> None:
        self.assertEqual(corrected_lag_ms(1000.0, 900.0, 25.0), 125.0)


class ClockFailureTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_sync_preserves_last_valid_estimate(self) -> None:
        def fail() -> int:
            raise OSError("offline")

        synchronizer = ClockSynchronizer(sample_count=2, fetch_server_time=fail)
        synchronizer.offset_ms = 7.5
        synchronizer.rtt_ms = 3.0

        self.assertFalse(await synchronizer.sync())
        self.assertEqual(synchronizer.offset_ms, 7.5)
        self.assertEqual(synchronizer.rtt_ms, 3.0)
        self.assertEqual(synchronizer.failed_syncs, 1)
        self.assertEqual(synchronizer.failed_samples, 2)


if __name__ == "__main__":
    unittest.main()

