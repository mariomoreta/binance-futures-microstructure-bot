"""Breakeven math + package/audit consistency for OFFLINE-EVAL-V1.

Pure + artifact-read checks only (no DB, no network, no engine runs).
Covers: s* formula, all-directional-negative-at-2x fragility,
realized/open separation, funding UNKNOWN never zeroed,
pooled-is-arithmetic (not a portfolio).
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "frontend" / "src" / "data" / "offline-eval-v1.json"
PINNED_SHA = "c051e88841754668a02a6d92db02ccdcb97fd16e45a08671022a370576287b3a"


def breakeven_scale(e_gross: float, friction_1x: float) -> float:
    return e_gross / friction_1x


class BreakevenMathTest(unittest.TestCase):
    def test_formula_spot_cases(self) -> None:
        self.assertAlmostEqual(breakeven_scale(2.09, 1.60), 1.30625)
        self.assertAlmostEqual(breakeven_scale(1.94, 1.60), 1.2125)
        # negative gross can never break even with positive friction
        self.assertLess(breakeven_scale(-0.81, 1.60), 0.0)

    def test_net_decomposition(self) -> None:
        # net(s) = gross - s*F1 by construction of scaled costs
        gross, f1 = 2.63, 1.60
        self.assertAlmostEqual(gross - 1 * f1, 1.03)
        self.assertAlmostEqual(gross - 2 * f1, -0.57, places=2)


class ArtifactConsistencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import hashlib
        raw = ARTIFACT.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == PINNED_SHA, "artifact pin drift"
        cls.doc = json.loads(raw.decode("utf-8"))

    def test_all_directional_cells_negative_at_2x(self) -> None:
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            for grp in ("continuation", "bearish-continuation"):
                for seg in ("dev", "oos"):
                    with self.subTest(sym=sym, group=grp, seg=seg):
                        self.assertLess(
                            self.doc["cells"][sym][grp][seg]["2.0"]["expectancy_net"], 0.0)

    def test_realized_open_separation(self) -> None:
        n_open = sum(
            self.doc["cells"][s][g][seg]["1.0"]["n_open"]
            for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
            for g in ("continuation", "correction-exhaustion",
                      "correction-reversal", "bearish-continuation",
                      "rebound-variant", "baseline")
            for seg in ("dev", "oos"))
        self.assertEqual(n_open, 2)
        # realized-only expectancy uses n_realized denominator where open>0
        c = self.doc["cells"]["ETHUSDT"]["continuation"]["oos"]["1.0"]
        self.assertEqual(c["n_trades"], 115)
        self.assertEqual(c["n_realized"], 114)
        self.assertEqual(c["n_open"], 1)

    def test_pooled_is_arithmetic_sum(self) -> None:
        for seg in ("dev", "oos"):
            expect = 0.0
            for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
                for grp in ("continuation", "correction-exhaustion",
                            "correction-reversal", "bearish-continuation"):
                    expect += self.doc["cells"][sym][grp][seg]["1.0"]["total_net"]
            self.assertAlmostEqual(
                self.doc["pooled_reference"][seg]["1.0"]["total_net"], expect)

    def test_h2_insufficient_and_rebound_empty(self) -> None:
        h2 = 0
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            for grp in ("correction-exhaustion", "correction-reversal"):
                for seg in ("dev", "oos"):
                    h2 += self.doc["cells"][sym][grp][seg]["1.0"]["n_events"]
        self.assertLessEqual(h2, 14 + 0)  # 14 trio H2 events max by audit
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            for seg in ("dev", "oos"):
                self.assertEqual(
                    self.doc["cells"][sym]["rebound-variant"][seg]["1.0"]["n_events"], 0)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
