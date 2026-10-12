"""Etapa 4: isolated offline backtest prep tests (synthetic fixtures only).

Proves replay MECHANICS deterministically: chronological order,
no-lookahead fills, exact cost math, stops, MFE/MAE, drawdown, dev/OOS
split, 1x/2x/3x sensitivity, partial fills, overlap skips. Fixture numbers
are MECHANICS SMOKE, never performance. No network, no DB, no wall clock.
Run: python run_tests.py
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from microstructure_probe.backtest_offline import (
    ENGINE_VERSION,
    BacktestConfig,
    Candle,
    StudyEvent,
    run_backtest,
    run_sensitivity,
    split_by_time,
)

T0 = 1_800_000_000_000


def _candles(symbol="BTCUSDT", n=12, step_ms=60_000, start=T0,
             start_px=100.0, drift=0.001):
    out = []
    px = start_px
    for i in range(n):
        o = px
        c = px * (1.0 + drift)
        out.append(Candle(symbol, start + i * step_ms, o,
                          max(o, c) * 1.0005, min(o, c) * 0.9995, c))
        px = c
    return out


def _ev(symbol="BTCUSDT", at=T0 - 1, direction="LONG"):
    return StudyEvent(symbol, at, direction, 100.0)


class ChronologyTest(unittest.TestCase):
    def test_fill_uses_first_candle_after_event(self) -> None:
        candles = _candles()
        res = run_backtest([_ev(at=T0 - 1)], candles, BacktestConfig())
        self.assertEqual(res["n_trades"], 1)
        self.assertEqual(res["trades"][0]["entry_ms"], T0)

    def test_no_candle_after_event_is_no_trade(self) -> None:
        candles = _candles()
        res = run_backtest([_ev(at=T0 + 999 * 60_000)], candles,
                           BacktestConfig())
        self.assertEqual(res["n_trades"], 0)

    def test_shuffled_inputs_replay_identically(self) -> None:
        candles = _candles()
        evs = [_ev(at=T0 - 1), _ev(at=T0 + 60_000)]
        fwd = run_backtest(evs, candles, BacktestConfig())
        rev = run_backtest(list(reversed(evs)), list(reversed(candles)),
                           BacktestConfig())
        self.assertEqual(fwd["trades"], rev["trades"])

    def test_poisoned_future_candle_ignored(self) -> None:
        candles = _candles() + [Candle("BTCUSDT", T0 - 5_000, 50.0, 50.0,
                                       50.0, 200.0)]
        res = run_backtest([_ev(at=T0 - 1)], candles, BacktestConfig())
        self.assertEqual(res["trades"][0]["entry_ms"], T0)

    def test_determinism_byte_identical(self) -> None:
        candles = _candles()
        evs = [_ev(at=T0 - 1), _ev(at=T0 + 120_000, direction="SHORT")]
        a = json.dumps(run_backtest(evs, candles, BacktestConfig()),
                       sort_keys=True)
        b = json.dumps(run_backtest(evs, candles, BacktestConfig()),
                       sort_keys=True)
        self.assertEqual(a, b)


class CostMathTest(unittest.TestCase):
    def test_fees_charged_both_sides(self) -> None:
        cfg = BacktestConfig(fee_bps=10.0, spread_bps=0.0, slippage_bps=0.0,
                             funding_8h_bps=0.0, notional_usdt=1000.0)
        res = run_backtest([_ev()], _candles(), cfg)
        self.assertAlmostEqual(res["trades"][0]["fees"], 2.0)

    def test_cost_scales_monotone(self) -> None:
        candles = _candles()
        nets = [run_backtest([_ev()], candles,
                             replace(BacktestConfig(), cost_scale=s)
                             )["total_net"] for s in (1.0, 2.0, 3.0)]
        self.assertGreater(nets[0], nets[1])
        self.assertGreater(nets[1], nets[2])

    def test_funding_accrues_per_8h(self) -> None:
        candles = _candles(n=600, step_ms=60_000)  # ~25d span
        cfg = BacktestConfig(exit_horizon_ms=9 * 3600 * 1000,
                             stop_distance_pct=50.0, fee_bps=0.0,
                             spread_bps=0.0, slippage_bps=0.0,
                             funding_8h_bps=10.0)
        res = run_backtest([_ev()], candles, cfg)
        self.assertGreater(res["trades"][0]["funding"], 0.0)

    def test_partial_fills_span_candles(self) -> None:
        cfg = BacktestConfig(partial_fill_notional_cap=400.0,
                             notional_usdt=1000.0)
        res = run_backtest([_ev()], _candles(), cfg)
        self.assertEqual(res["trades"][0]["fills"], 3)


class ExitMathTest(unittest.TestCase):
    def test_stop_triggers_on_adverse_candle(self) -> None:
        candles = [Candle("BTCUSDT", T0, 100.0, 100.1, 100.1, 100.1),
                   Candle("BTCUSDT", T0 + 60_000, 100.1, 100.1, 90.0, 91.0)]
        cfg = BacktestConfig(stop_distance_pct=0.5, fee_bps=0.0,
                             spread_bps=0.0, slippage_bps=0.0)
        res = run_backtest([_ev()], candles + _candles(start=T0 + 120_000),
                           cfg)
        self.assertEqual(res["trades"][0]["exit_reason"], "stop")

    def test_mfe_mae_recorded(self) -> None:
        res = run_backtest([_ev()], _candles(), BacktestConfig())
        t = res["trades"][0]
        self.assertGreater(t["mfe_pct"], 0.0)
        self.assertGreaterEqual(t["mae_pct"], 0.0)

    def test_overlap_skipped_and_counted(self) -> None:
        evs = [_ev(at=T0 - 1), _ev(at=T0 + 10_000)]
        res = run_backtest(evs, _candles(), BacktestConfig())
        self.assertEqual(res["n_trades"], 1)
        self.assertEqual(res["skipped_overlap"], 1)

    def test_empty_inputs(self) -> None:
        res = run_backtest([], _candles(), BacktestConfig())
        self.assertEqual(res["n_trades"], 0)
        self.assertEqual(res["expectancy_net"], 0.0)
        self.assertEqual(res["max_drawdown"], 0.0)


class SegmentationTest(unittest.TestCase):
    def test_split_by_time(self) -> None:
        evs = [_ev(at=T0), _ev(at=T0 + 10)]
        parts = split_by_time(evs, T0 + 10)
        self.assertEqual(len(parts["dev"]), 1)
        self.assertEqual(len(parts["oos"]), 1)

    def test_sensitivity_matrix_shape(self) -> None:
        out = run_sensitivity([_ev(at=T0 - 1), _ev(at=T0 + 500_000)],
                              _candles(n=30), BacktestConfig())
        self.assertEqual(out["engine_version"], ENGINE_VERSION)
        for seg in ("dev", "oos"):
            for scale in ("1.0", "2.0", "3.0"):
                self.assertIn("expectancy_net", out["segments"][seg][scale])

    def test_result_carries_identity(self) -> None:
        res = run_backtest([_ev()], _candles(), BacktestConfig(),
                           dataset_id="fixture-x")
        self.assertEqual(res["engine_version"], ENGINE_VERSION)
        self.assertEqual(res["dataset_id"], "fixture-x")
        self.assertEqual(len(res["config_hash"]), 16)
        self.assertIn("NOT performance", res["label"])


if __name__ == "__main__":
    unittest.main()
