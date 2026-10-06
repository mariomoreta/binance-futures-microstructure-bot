import unittest

from microstructure_probe.telemetry import NearMissCounter, RunningDistribution


class RunningDistributionTest(unittest.TestCase):
    def test_required_statistics_are_reported(self) -> None:
        distribution = RunningDistribution(max_samples=10)
        for value in (1.0, 2.0, 3.0, 4.0, 5.0):
            distribution.add(value)
        snapshot = distribution.snapshot()
        self.assertEqual(snapshot["count"], 5)
        self.assertEqual(snapshot["min"], 1.0)
        self.assertEqual(snapshot["p50"], 3.0)
        self.assertEqual(snapshot["p90"], 5.0)
        self.assertEqual(snapshot["p95"], 5.0)
        self.assertEqual(snapshot["p99"], 5.0)
        self.assertEqual(snapshot["max"], 5.0)
        self.assertEqual(snapshot["mean"], 3.0)


class NearMissCounterTest(unittest.TestCase):
    def test_near_miss_buckets_are_cumulative(self) -> None:
        counter = NearMissCounter()
        for ratio in (0.49, 0.50, 0.80, 0.95, 1.10):
            counter.observe(ratio)
        snapshot = counter.snapshot()
        self.assertEqual(
            snapshot["atOrAbove"],
            {"50pct": 4, "75pct": 3, "90pct": 2, "100pct": 1},
        )
        self.assertEqual(snapshot["maxRatio"], 1.1)


if __name__ == "__main__":
    unittest.main()

