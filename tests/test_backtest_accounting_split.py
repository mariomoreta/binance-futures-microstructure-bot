"""Accounting split: realized vs open positions vs marks (additive fields).

Proves open_at_end marks NEVER feed realized metrics, exit-leg costs on
open marks are flagged hypothetical (entry legs stay executed), and the
realized curve runs in effective-close-time order. Legacy totals/curve
are preserved untouched (they still include open marks). Synthetic only.
Run: python run_tests.py
"""

from __future__ import annotations

import unittest

from microstructure_probe.backtest_offline import (
    BacktestConfig,
    Candle,
    StudyEvent,
    run_backtest,
)

T0 = 1_800_000_000_000
H = 3600_000


def _flat(symbol="BTCUSDT", n=6, start=T0, px=100.0):
    return [Candle(symbol, start + i * 60_000, px, px + 0.05,
                   px - 0.05, px) for i in range(n)]


def _cfg(**kw):
    base = dict(fee_bps=0.0, spread_bps=0.0, slippage_bps=0.0,
                funding_8h_bps=0.0, notional_usdt=1000.0,
                stop_distance_pct=50.0, exit_horizon_ms=H)
    base.update(kw)
    return BacktestConfig(**base)


class OpenMarkExclusionTest(unittest.TestCase):
    def test_open_at_end_feeds_no_realized_metric(self) -> None:
        # Data ends (6 min) long before the 1h horizon: open mark.
        res = run_backtest([StudyEvent("BTCUSDT", T0 - 1, "LONG", 100.0)],
                           _flat(), _cfg())
        self.assertEqual(res["n_trades"], 1)
        t = res["trades"][0]
        self.assertEqual(t["exit_reason"], "open_at_end")
        self.assertTrue(t["open_at_end"])
        self.assertFalse(t["exit_executed"])
        self.assertIsNone(t["realized_net"])
        self.assertEqual(res["n_open"], 1)
        self.assertEqual(res["n_realized"], 0)
        self.assertEqual(res["total_net_realized"], 0.0)
        self.assertEqual(res["expectancy_net_realized"], 0.0)
        self.assertEqual(res["equity_curve_realized"], [])
        self.assertEqual(res["max_drawdown_realized"], 0.0)
        self.assertEqual(len(res["open_positions"]), 1)
        mark = res["open_positions"][0]
        self.assertEqual(mark["mark_ms"], t["exit_ms"])
        self.assertEqual(mark["mark_px"], t["exit_px"])
        self.assertEqual(mark["filled_qty"], t["filled_qty"])
        # Legacy fields still carry the mark (unchanged behavior).
        self.assertEqual(len(res["equity_curve"]), 1)

    def test_closed_trade_is_fully_realized(self) -> None:
        candles = _flat(n=120)  # 2h of data covers the 1h horizon
        res = run_backtest([StudyEvent("BTCUSDT", T0 - 1, "LONG", 100.0)],
                           candles, _cfg())
        t = res["trades"][0]
        self.assertEqual(t["exit_reason"], "horizon")
        self.assertTrue(t["exit_executed"])
        self.assertAlmostEqual(t["realized_net"], t["net_pnl"])
        self.assertEqual(res["n_realized"], 1)
        self.assertEqual(res["n_open"], 0)
        self.assertAlmostEqual(res["total_net_realized"], t["net_pnl"])
        self.assertEqual(len(res["equity_curve_realized"]), 1)
        self.assertEqual(res["equity_curve_realized"][0]["exit_ms"],
                         t["exit_ms"])


class HypotheticalExitCostTest(unittest.TestCase):
    def test_open_mark_exit_leg_is_hypothetical(self) -> None:
        cfg = _cfg(fee_bps=10.0, spread_bps=5.0, slippage_bps=5.0)
        res = run_backtest([StudyEvent("BTCUSDT", T0 - 1, "LONG", 100.0)],
                           _flat(), cfg)
        t = res["trades"][0]
        self.assertTrue(t["open_at_end"])
        self.assertGreater(t["costs_exit_hypothetical"], 0.0)
        self.assertAlmostEqual(t["costs_exit_hypothetical"],
                               t["exit_spread_slip"] + t["exit_fees"])
        self.assertAlmostEqual(t["costs_executed"],
                               t["friction"] - t["costs_exit_hypothetical"])
        self.assertAlmostEqual(t["costs_executed"],
                               t["entry_spread_slip"] + t["entry_fees"])
        self.assertAlmostEqual(res["total_exit_costs_hypothetical"],
                               t["costs_exit_hypothetical"])
        self.assertAlmostEqual(res["total_costs_executed"],
                               t["costs_executed"])

    def test_closed_trade_has_no_hypothetical_cost(self) -> None:
        cfg = _cfg(fee_bps=10.0, spread_bps=5.0, slippage_bps=5.0)
        res = run_backtest([StudyEvent("BTCUSDT", T0 - 1, "LONG", 100.0)],
                           _flat(n=120), cfg)
        t = res["trades"][0]
        self.assertTrue(t["exit_executed"])
        self.assertEqual(t["costs_exit_hypothetical"], 0.0)
        self.assertAlmostEqual(t["costs_executed"], t["friction"])


class RealizedCurveOrderTest(unittest.TestCase):
    def test_curve_follows_effective_close_time(self) -> None:
        # A holds BTC to the 1h horizon; B enters ETH at +50m and stops at
        # +51m on an ETH-only dip. Effective closes run B(51m) < A(60m)
        # while events run A < B: the realized curve must follow exits.
        btc = _flat("BTCUSDT", n=180)
        eth = _flat("ETHUSDT", n=180)
        eth[51] = Candle("ETHUSDT", T0 + 51 * 60_000, 100.0, 100.05, 90.0,
                         99.0)
        cfg = _cfg(stop_distance_pct=0.5)
        cfg2 = BacktestConfig(**{**cfg.__dict__, "max_concurrent": 2})
        res = run_backtest(
            [StudyEvent("BTCUSDT", T0 - 1, "LONG", 100.0),
             StudyEvent("ETHUSDT", T0 + 50 * 60_000, "LONG", 100.0)],
            btc + eth, cfg2)
        self.assertEqual(res["n_trades"], 2)
        self.assertTrue(all(t["exit_executed"] for t in res["trades"]))
        by_sym = {t["symbol"]: t for t in res["trades"]}
        self.assertEqual(by_sym["ETHUSDT"]["exit_reason"], "stop")
        self.assertEqual(by_sym["BTCUSDT"]["exit_reason"], "horizon")
        curve = res["equity_curve_realized"]
        self.assertEqual(len(curve), 2)
        exits = [c["exit_ms"] for c in curve]
        self.assertEqual(exits, sorted(exits))
        # First curve point is the stopped ETH trade (earlier close).
        self.assertEqual(curve[0]["exit_ms"],
                         by_sym["ETHUSDT"]["exit_ms"])
        self.assertAlmostEqual(curve[0]["equity"],
                               by_sym["ETHUSDT"]["net_pnl"])
        self.assertAlmostEqual(curve[1]["equity"],
                               res["total_net_realized"])


if __name__ == "__main__":
    unittest.main()
