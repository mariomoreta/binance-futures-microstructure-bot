"""Effective horizon must exceed the grid step (close-knowledge rule R1).

A 1h window on 1h candles resolves no close (entry == exit, gross == 0
by construction); 4h on 1h resolves. The runner exposes --horizon-ms
(default 1h preserves prior behavior).
Run: python run_tests.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from microstructure_probe.backtest_offline import (  # noqa: E402
    BacktestConfig,
    Candle,
    StudyEvent,
    run_backtest,
)


def _candles(step_ms=3_600_000, n=8, base=1_780_000_000_000):
    out = []
    px = 100.0
    for i in range(n):
        o = px
        px = px * 1.004
        out.append(Candle(symbol="TSTUSDT", open_time_ms=base + i * step_ms,
                          open=o, high=px * 1.001, low=o * 0.999,
                          close=px, close_time_ms=base + (i + 1) * step_ms - 1))
    return out


def _run(step_ms, horizon_ms):
    candles = _candles(step_ms=step_ms)
    ev = StudyEvent(symbol="TSTUSDT",
                    event_time_ms=candles[1].open_time_ms, direction="LONG",
                    reference_price=candles[1].close,
                    family="H1", rules_version="H1-v1")
    cfg = BacktestConfig(family="H1", rules_version="H1-v1",
                         exit_horizon_ms=horizon_ms, cost_scale=1.0,
                         funding_calendar=None)
    res = run_backtest([ev], candles, cfg, dataset_id="t", segment="dev")
    return res


class HorizonGridTest(unittest.TestCase):
    def test_1h_window_on_1h_grid_is_degenerate(self):
        res = _run(3_600_000, 3_600_000)
        self.assertEqual(res["n_trades"], 1)
        t = res["trades"][0]
        self.assertEqual(t["entry_ms"], t["exit_ms"])
        self.assertAlmostEqual(t["gross_pnl"], 0.0, places=9)

    def test_4h_window_on_1h_grid_resolves(self):
        res = _run(3_600_000, 4 * 3_600_000)
        self.assertEqual(res["n_trades"], 1)
        t = res["trades"][0]
        self.assertGreater(t["exit_ms"], t["entry_ms"])
        self.assertNotEqual(t["gross_pnl"], 0.0)

    def test_1h_window_on_15m_grid_resolves(self):
        res = _run(900_000, 3_600_000)
        self.assertEqual(res["n_trades"], 1)
        self.assertGreater(res["trades"][0]["exit_ms"],
                           res["trades"][0]["entry_ms"])

    def test_runner_horizon_flag_default_preserved(self):
        import run_family_evaluation as rfe
        import argparse
        args = rfe.main.__wrapped__ if hasattr(rfe.main, "__wrapped__") else None
        self.assertIsNone(args)  # main is a plain function; flag parsed below
        parser_args = ["--demo"]
        # demo path must keep working with the default horizon
        import tempfile
        out = Path(tempfile.mkdtemp(prefix="horizon_"))
        rc = rfe.main(["--demo", "--out", str(out / "m.json")])
        self.assertEqual(rc, 0)
        import json
        manifest = json.loads((out / "m.json").read_text())
        self.assertEqual(manifest["exit_horizon_ms"], 3600 * 1000)


if __name__ == "__main__":
    unittest.main()
