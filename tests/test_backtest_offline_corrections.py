"""Correcciones del motor offline: regresiones independientes (P1.1–P1.7+).

Cada test falla sobre el SHA auditado bdc9ef2 y pasa tras la corrección.
Fixtures sintéticos únicamente; ningún acceso a red, DB o reloj.
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


def _cfg(**kw):
    base = dict(fee_bps=0.0, funding_8h_bps=0.0, spread_bps=0.0,
                slippage_bps=0.0, notional_usdt=1000.0)
    base.update(kw)
    return BacktestConfig(**base)


class PartialFillCausalityTest(unittest.TestCase):
    """P1.1: ningún fill posterior altera una decisión/posición anterior."""

    def test_later_fill_cannot_move_entry_or_stop(self) -> None:
        candles = [
            Candle("BTCUSDT", 1000, 100.0, 100.0, 80.0, 100.0),
            Candle("BTCUSDT", 2000, 200.0, 200.0, 200.0, 200.0),
            Candle("BTCUSDT", 3000, 200.0, 200.0, 200.0, 200.0),
        ]
        cfg = _cfg(partial_fill_notional_cap=500.0, stop_distance_pct=10.0,
                   exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(res["n_trades"], 1)
        trade = res["trades"][0]
        self.assertEqual(trade["fills"], 1)
        self.assertAlmostEqual(trade["entry_px"], 100.0)
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertEqual(trade["exit_ms"], 2000)
        self.assertAlmostEqual(trade["exit_px"], 90.0)


class EntryAfterExitTest(unittest.TestCase):
    """P1.2: horizonte anterior a la primera vela => rechazo/expiración."""

    def test_entry_after_horizon_is_expired_not_traded(self) -> None:
        candles = [Candle("BTCUSDT", 1000, 100.0, 101.0, 99.0, 100.5)]
        cfg = _cfg(exit_horizon_ms=500)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(res["n_trades"], 0)
        self.assertEqual(res.get("n_expired"), 1)
        for trade in res["trades"]:
            self.assertLessEqual(trade["entry_ms"], trade["exit_ms"])


class ConcurrencyLimitTest(unittest.TestCase):
    """P1.3: max_concurrent se aplica en el tiempo, por símbolo y global."""

    def test_two_slots_admit_two_of_three_overlapping(self) -> None:
        candles = [Candle(s, 1000 + i * 1000, 100.0, 101.0, 99.0, 100.0)
                   for s in ("AAAUSDT", "BBBUSDT", "CCCUSDT")
                   for i in range(10)]
        events = [StudyEvent(s, 0, "LONG", 100.0)
                  for s in ("AAAUSDT", "BBBUSDT", "CCCUSDT")]
        cfg = _cfg(max_concurrent=2, exit_horizon_ms=50_000)
        res = run_backtest(events, candles, cfg)
        self.assertEqual(res["n_trades"], 2)
        self.assertEqual(res["skipped_overlap"], 1)


class StopGapTest(unittest.TestCase):
    """P1.4: gap bajo el stop => fill conservador al primer precio real."""

    def test_gap_through_stop_exits_at_open_not_stop(self) -> None:
        candles = [
            Candle("BTCUSDT", 1000, 100.0, 100.0, 100.0, 100.0),
            Candle("BTCUSDT", 2000, 80.0, 80.0, 80.0, 80.0),
            Candle("BTCUSDT", 3000, 80.0, 80.0, 80.0, 80.0),
        ]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(res["n_trades"], 1)
        trade = res["trades"][0]
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertAlmostEqual(trade["exit_px"], 80.0)


class IncompleteFillTest(unittest.TestCase):
    """P1.5: lo realmente llenado se conserva; fin de datos explícito."""

    def test_partial_position_kept_with_open_at_end(self) -> None:
        candles = [Candle("BTCUSDT", 1000, 100.0, 101.0, 99.0, 100.5)]
        cfg = _cfg(partial_fill_notional_cap=500.0,
                   stop_distance_pct=50.0,
                   exit_horizon_ms=600_000, fee_bps=5.0)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(res["n_trades"], 1)
        trade = res["trades"][0]
        self.assertTrue(trade.get("open_at_end"))
        self.assertAlmostEqual(trade["filled_qty"], 5.0)
        self.assertGreater(trade["fees"], 0.0)


class OhlcTimingTest(unittest.TestCase):
    """P1.6: close/high/low solo conocidos al cierre; nada intravela."""

    def test_boundary_horizon_cannot_use_unclosed_candle(self) -> None:
        candles = [Candle("BTCUSDT", 1000, 100.0, 105.0, 100.0, 105.0)]
        cfg = _cfg(exit_horizon_ms=1000, stop_distance_pct=50.0)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(res["n_trades"], 1)
        trade = res["trades"][0]
        self.assertAlmostEqual(trade["gross_pnl"], 0.0)
        self.assertAlmostEqual(trade["mfe_pct"], 0.0)


class QuantityAccountingTest(unittest.TestCase):
    """P1.7: cantidad, coste y P&L por fill, no medias de precios."""

    def test_quantity_weighted_average_and_pnl(self) -> None:
        candles = [
            Candle("BTCUSDT", 1000, 100.0, 100.0, 100.0, 100.0),
            Candle("BTCUSDT", 2000, 200.0, 200.0, 200.0, 200.0),
            Candle("BTCUSDT", 3000, 200.0, 200.0, 200.0, 200.0),
        ]
        cfg = _cfg(partial_fill_notional_cap=500.0,
                   stop_distance_pct=50.0, exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(res["n_trades"], 1)
        trade = res["trades"][0]
        self.assertAlmostEqual(trade["filled_qty"], 7.5)
        self.assertAlmostEqual(trade["filled_cost"], 1000.0)
        self.assertAlmostEqual(trade["entry_px"], 133.33333333333334)
        self.assertAlmostEqual(trade["exit_px"], 200.0)
        self.assertAlmostEqual(trade["gross_pnl"], 500.0)


class FamilyCoherenceTest(unittest.TestCase):
    """Revisión: family/rules_version del evento vs configuración."""

    def test_mismatched_family_version_skipped_and_counted(self) -> None:
        candles = [Candle("BTCUSDT", 1000, 100.0, 101.0, 99.0, 100.0),
                   Candle("BTCUSDT", 2000, 100.0, 101.0, 99.0, 100.0)]
        cfg = _cfg(family="H1", rules_version="H1-v1")
        ev = StudyEvent("BTCUSDT", 0, "LONG", 100.0, family="H2",
                        rules_version="H2-v1")
        res = run_backtest([ev], candles, cfg)
        self.assertEqual(res["n_trades"], 0)
        self.assertEqual(res.get("n_mismatched"), 1)


class UnsupportedKnobsTest(unittest.TestCase):
    """Revisión: latencia/tick/lot/mínimo se rechazan, no se fingen."""

    def test_unsupported_knobs_raise(self) -> None:
        import dataclasses

        candles = [Candle("BTCUSDT", 1000, 100.0, 101.0, 99.0, 100.0)]
        for knob in ("latency_ms", "tick_size", "lot_step",
                     "min_notional_usdt"):
            cfg = dataclasses.replace(_cfg(), **{knob: 1.0})
            with self.assertRaises(ValueError, msg=knob):
                run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                             candles, cfg)


class ReproducibilityIdentityTest(unittest.TestCase):
    """Revisión: hash de inputs + cutoff explícito en sensibilidad."""

    def test_input_hash_and_cutoff_reported(self) -> None:
        from microstructure_probe.backtest_offline import run_sensitivity

        candles = [Candle("BTCUSDT", 1000 + i * 1000, 100.0, 101.0,
                          99.0, 100.0) for i in range(6)]
        events = [StudyEvent("BTCUSDT", 500 + i * 1000, "LONG", 100.0)
                  for i in range(4)]
        out = run_sensitivity(events, candles, _cfg())
        self.assertIn("input_hash", out)
        self.assertIn("cutoff_ms", out)
        for seg in ("dev", "oos"):
            self.assertIn("input_hash",
                          out["segments"][seg]["1.0"])


if __name__ == "__main__":
    unittest.main()
