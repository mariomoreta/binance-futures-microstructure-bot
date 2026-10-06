import math
import unittest

from microstructure_probe.metrics import (
    basis_points_change,
    order_book_imbalance,
    percentile,
    population_z_score,
    spread_bps,
)


class MetricsTest(unittest.TestCase):
    def test_one_percent_is_one_hundred_basis_points(self) -> None:
        self.assertAlmostEqual(basis_points_change(100.0, 101.0), 100.0)

    def test_negative_half_percent_is_minus_fifty_basis_points(self) -> None:
        self.assertAlmostEqual(basis_points_change(200.0, 199.0), -50.0)

    def test_spread_uses_midpoint(self) -> None:
        self.assertAlmostEqual(spread_bps(99.0, 101.0), 200.0)

    def test_order_book_imbalance_known_value(self) -> None:
        # bids=75, asks=25 => (75-25)/(75+25) = 0.5
        self.assertAlmostEqual(
            order_book_imbalance([["100", "75"]], [["101", "25"]]), 0.5
        )

    def test_percentile_interpolates(self) -> None:
        self.assertAlmostEqual(percentile([0.0, 10.0], 0.25), 2.5)

    def test_population_z_score(self) -> None:
        self.assertAlmostEqual(population_z_score(3.0, [1.0, 2.0, 3.0]), 1.2247448714)
        self.assertTrue(math.isinf(population_z_score(2.0, [1.0, 1.0, 1.0])))


if __name__ == "__main__":
    unittest.main()

