"""Tests for P1-05 velocity / acceleration / cross-sectional ranking."""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe.momentum import (
    RANK_METRICS,
    VELOCITY_HORIZONS,
    RankTracker,
    acceleration_at,
    return_at,
    velocity_at,
)
from microstructure_probe.returns import (
    BUCKET_MS,
    TIMEFRAMES_MS,
    ReturnEngine,
    SymbolPriceSeries,
)

T0 = 1_700_000_000_000


def _flat_then_jump(span_ms: int, jump_at_ms: int, jump_ratio: float,
                    symbols=("BTCUSDT",)) -> ReturnEngine:
    engine = ReturnEngine(symbols=symbols)
    bucket = T0 - (T0 % BUCKET_MS)
    last = T0 + span_ms
    while bucket <= last:
        price = 100.0 * jump_ratio if bucket >= jump_at_ms else 100.0
        engine.ingest(symbols[0], bucket + 1, price)
        bucket += BUCKET_MS
    return engine


class VelocityMathTest(unittest.TestCase):
    def test_flat_return_has_zero_velocity(self) -> None:
        """The key non-rename property: steady exponential trend => ~0."""
        engine = ReturnEngine(symbols=("BTCUSDT",))
        k = 0.000001
        base = T0
        for i in range(400):  # ~66 min of 10s buckets
            engine.ingest("BTCUSDT", base + i * BUCKET_MS,
                          100.0 * math.exp(k * i * BUCKET_MS / 1000.0))
        series = engine._series["BTCUSDT"]
        as_of = base + 399 * BUCKET_MS
        vel = velocity_at(series, as_of, 60_000)
        self.assertIsNotNone(vel)
        self.assertAlmostEqual(vel["value"], 0.0, places=12)
        acc = acceleration_at(series, as_of, 60_000)
        self.assertIsNotNone(acc)
        self.assertAlmostEqual(acc["value"], 0.0, places=12)

    def test_jump_gives_exact_velocity(self) -> None:
        engine = _flat_then_jump(300_000, T0 + 270_000, 1.01)
        series = engine._series["BTCUSDT"]
        as_of = T0 + 300_000
        vel = velocity_at(series, as_of, 60_000)
        # R_1m(now) = ln(1.01) (anchor 60s back is pre-jump); R_1m(prev) = 0.
        self.assertAlmostEqual(vel["value"], math.log(1.01) / 60.0, places=12)
        self.assertEqual(vel["horizon_ms"], 60_000)
        self.assertEqual(vel["basis_ms"], 60_000)

    def test_acceleration_exact(self) -> None:
        engine = _flat_then_jump(300_000, T0 + 270_000, 1.01)
        series = engine._series["BTCUSDT"]
        as_of = T0 + 300_000
        acc = acceleration_at(series, as_of, 60_000)
        # v(now) = ln(1.01)/60, v(60s earlier) = 0 -> a = v/60.
        self.assertAlmostEqual(acc["value"], math.log(1.01) / 3600.0, places=12)

    def test_insufficient_history_is_none(self) -> None:
        engine = ReturnEngine(symbols=("BTCUSDT",))
        engine.ingest("BTCUSDT", T0, 100.0)
        series = engine._series["BTCUSDT"]
        self.assertIsNone(velocity_at(series, T0, 60_000))
        self.assertIsNone(acceleration_at(series, T0, 60_000))
        # 90s span: 1m return exists but velocity needs two evaluations.
        for i in range(1, 10):
            engine.ingest("BTCUSDT", T0 + i * 10_000, 100.0)
        self.assertIsNone(velocity_at(series, T0 + 90_000, 60_000))

    def test_no_lookahead(self) -> None:
        engine = _flat_then_jump(300_000, T0 + 270_000, 2.0)
        series = engine._series["BTCUSDT"]
        early = velocity_at(series, T0 + 120_000, 60_000)
        self.assertIsNotNone(early)
        self.assertAlmostEqual(early["value"], 0.0, places=12)

    def test_irregular_timestamps(self) -> None:
        engine = ReturnEngine(symbols=("BTCUSDT",))
        engine.ingest("BTCUSDT", T0 - 70_000, 100.0)
        engine.ingest("BTCUSDT", T0, 100.0)
        engine.ingest("BTCUSDT", T0 + 45_000, 100.0)  # sparse but within tol
        engine.ingest("BTCUSDT", T0 + 130_000, 101.0)
        series = engine._series["BTCUSDT"]
        vel = velocity_at(series, T0 + 130_000, 60_000)
        # R(now): anchor = latest <= T0+70s -> T0+40s bucket (30s stale, ok).
        self.assertIsNotNone(vel)
        r_now = math.log(101.0 / 100.0)
        self.assertAlmostEqual(vel["r_now"], r_now, places=12)

    def test_engine_momentum_wrapper_shape(self) -> None:
        engine = _flat_then_jump(600_000, T0 + 540_000, 1.02)
        out = engine.momentum("BTCUSDT", T0 + 600_000)
        self.assertEqual(out["symbol"], "BTCUSDT")
        self.assertIn("1m", out["velocity"])
        self.assertIn("1m", out["acceleration"])
        self.assertIsNotNone(out["velocity"]["1m"])
        self.assertIsNone(out["velocity"]["24h"] if "24h" in out["velocity"] else None)
        ghost = engine.momentum("NOPEUSDT", T0)
        self.assertIsNone(ghost["velocity"]["1m"])


class RankTrackerTest(unittest.TestCase):
    def test_positive_negative_ordering_and_ties(self) -> None:
        tracker = RankTracker()
        tracker.evaluate(1_000, [("B", {"velocity_1m": 5.0}),
                                 ("A", {"velocity_1m": 5.0}),
                                 ("C", {"velocity_1m": -2.0})])
        snap = tracker.snapshot()
        ranks = snap["velocity_1m"]
        # Tie 5.0 broken by symbol asc: A=1, B=2, C=3.
        self.assertEqual((ranks["A"]["rank"], ranks["B"]["rank"],
                          ranks["C"]["rank"]), (1, 2, 3))
        self.assertIsNone(ranks["A"]["change"])  # single evaluation
        self.assertIsNone(ranks["A"]["velocity"])

    def test_change_velocity_acceleration(self) -> None:
        tracker = RankTracker()
        tracker.evaluate(0, [("A", {"velocity_1m": 1.0}),
                             ("B", {"velocity_1m": 2.0})])
        tracker.evaluate(60_000, [("A", {"velocity_1m": 3.0}),
                                  ("B", {"velocity_1m": 2.0})])
        snap = tracker.snapshot()["velocity_1m"]
        self.assertEqual(snap["A"]["rank"], 1)
        self.assertEqual(snap["A"]["change"], 1)  # 2 -> 1
        self.assertAlmostEqual(snap["A"]["velocity"], 1 / 60.0)
        self.assertIsNone(snap["A"]["acceleration"])  # needs 3 evals
        tracker.evaluate(120_000, [("A", {"velocity_1m": 3.0}),
                                  ("B", {"velocity_1m": 4.0})])
        snap = tracker.snapshot()["velocity_1m"]
        # A falls to rank 2; rank velocity = (1-2)/60; accel defined now.
        self.assertEqual(snap["A"]["rank"], 2)
        self.assertAlmostEqual(snap["A"]["velocity"], -1 / 60.0)
        self.assertIsNotNone(snap["A"]["acceleration"])

    def test_missing_values_excluded_not_zero(self) -> None:
        tracker = RankTracker()
        tracker.evaluate(0, [("A", {"velocity_1m": None}),
                             ("B", {"velocity_1m": 1.0})])
        snap = tracker.snapshot()["velocity_1m"]
        self.assertNotIn("A", snap)
        self.assertEqual(snap["B"]["rank"], 1)

    def test_empty_snapshot(self) -> None:
        self.assertEqual(RankTracker().snapshot(), {})
        self.assertEqual(RankTracker().evaluation_count(), 0)


if __name__ == "__main__":
    unittest.main()
