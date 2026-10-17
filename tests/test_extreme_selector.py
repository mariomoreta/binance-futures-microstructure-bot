"""Extreme selector V1: mechanism with fixtures, no invented coverage.

Run: python run_tests.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from microstructure_probe.extreme_selector import (  # noqa: E402
    SELECTOR_VERSION,
    VERDICT_DISCARDED,
    VERDICT_WATCH,
    input_coverage,
    rank_board,
    select,
)


def _feat(**kw):
    base = {"symbol": "ALTUSDT", "prior_24h_return": 0.08,
            "prior_1h_return": 0.009, "range_position": 0.75,
            "volume_percentile": 0.8, "formation_gap": False,
            "available_at_consumer": "close_time-chain",
            "btc_context": {"available": True},
            "relative_return_1h": 0.004}
    base.update(kw)
    return base


def _universe():
    return {"ALTUSDT": {"eligible": True, "rank": 3, "as_of": 123},
            "BTCUSDT": {"eligible": True, "rank": 1, "as_of": 123}}


class ExtremeSelectorTest(unittest.TestCase):
    def test_gainer_watch_up_with_scenarios(self):
        v = select(_feat(), _universe())
        self.assertEqual(v["verdict"], VERDICT_WATCH)
        self.assertEqual(v["side"], "UP")
        self.assertIn("H1-continuation-candidate", v["scenarios"])
        self.assertIn("ranking != entry", v["ranking_note"])
        self.assertEqual(v["selector_version"], SELECTOR_VERSION)
        self.assertTrue(v["universe"]["known"])
        self.assertTrue(v["btc_available"])

    def test_loser_watch_down(self):
        v = select(_feat(prior_24h_return=-0.09, prior_1h_return=-0.01,
                         range_position=0.1, relative_return_1h=-0.005),
                   _universe())
        self.assertEqual(v["verdict"], VERDICT_WATCH)
        self.assertEqual(v["side"], "DOWN")
        self.assertIn("H3-continuation-candidate", v["scenarios"])

    def test_below_floors_discarded_with_reason(self):
        v = select(_feat(prior_24h_return=0.01), _universe())
        self.assertEqual(v["verdict"], VERDICT_DISCARDED)
        self.assertEqual(v["reason"], "below-move-floors")

    def test_gap_discarded(self):
        v = select(_feat(formation_gap=True), _universe())
        self.assertEqual((v["verdict"], v["reason"]),
                         (VERDICT_DISCARDED, "formation-gap"))

    def test_thin_volume_against_not_discard(self):
        v = select(_feat(volume_percentile=0.1), _universe())
        self.assertEqual(v["verdict"], VERDICT_WATCH)
        self.assertIn("thin-vs-own-history", v["against"])

    def test_no_universe_mechanism_still_scores_but_unknown(self):
        v = select(_feat(), None)
        self.assertEqual(v["verdict"], VERDICT_WATCH)
        self.assertFalse(v["universe"]["known"])
        self.assertTrue(any("universe" in m for m in v["missing"]))
        self.assertTrue(any("UNKNOWN" in c for c in
                            v["confirmations_needed"]))

    def test_mcap_always_unknown_never_low_cap(self):
        v = select(_feat(), _universe())
        self.assertTrue(any("market-cap" in m for m in v["missing"]))
        blob = str(v)
        self.assertNotIn("low cap", blob)
        self.assertNotIn("low_cap", blob)

    def test_bilateral_boards_rank_not_entry(self):
        up = select(_feat(symbol="AAAUSDT"), _universe())
        up2 = select(_feat(symbol="ZZZUSDT", prior_24h_return=0.2), _universe())
        down = select(_feat(symbol="LOSSUSDT", prior_24h_return=-0.1,
                            prior_1h_return=-0.02, range_position=0.05,
                            relative_return_1h=-0.01), _universe())
        board_up = rank_board([up, up2, down], "UP")
        self.assertEqual([r["symbol"] for r in board_up],
                         ["ZZZUSDT", "AAAUSDT"])
        board_down = rank_board([up, up2, down], "DOWN")
        self.assertEqual([r["symbol"] for r in board_down], ["LOSSUSDT"])

    def test_real_coverage_declares_unknowns(self):
        cov = input_coverage()
        for key in ("liquidity_spread_depth", "universe_ranking_history",
                    "market_cap"):
            self.assertIn("UNKNOWN", cov[key])
        self.assertIn("PARTIAL", cov["consequence"])


if __name__ == "__main__":
    unittest.main()
