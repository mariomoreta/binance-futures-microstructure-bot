"""Funding v4: settlement-calendar accounting (no global interval swap).

Covers: single crossing, no crossing, 4h vs 8h calendars, sign matrix
(LONG/SHORT x positive/negative), partial exposure across fills,
entry/exit boundary convention, incomplete calendars (UNKNOWN, never
zero-invented), estimated-vs-realized separation, legacy fallback
preservation, calendar identity. Synthetic fixtures only.
Run: python run_tests.py
"""

from __future__ import annotations

import unittest

from microstructure_probe.backtest_offline import (
    BacktestConfig,
    Candle,
    FundingCalendar,
    FundingSettlement,
    StudyEvent,
    run_backtest,
)

H = 3600_000


def _cfg(**kw):
    base = dict(fee_bps=0.0, funding_8h_bps=0.0, spread_bps=0.0,
                slippage_bps=0.0, notional_usdt=1000.0,
                stop_distance_pct=50.0)
    base.update(kw)
    return BacktestConfig(**base)


def _hourly(n, start=0, px=100.0):
    return [Candle("BTCUSDT", start + i * H, px, px + 0.1, px - 0.1, px)
            for i in range(n)]


def _cal(hours, rate_bps, version="venue-4h/v1", source="synthetic-fixture",
         interval_ms=4 * H):
    return FundingCalendar(
        version=version, source=source, interval_ms=interval_ms,
        settlements=tuple(FundingSettlement(h * H, rate_bps) for h in hours))


class SingleCrossingTest(unittest.TestCase):
    def test_long_crossing_one_settlement(self) -> None:
        candles = _hourly(12)
        cfg = _cfg(exit_horizon_ms=10 * H,
                   funding_calendar=_cal([4], 10.0))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertEqual(trade["funding_model"], "settlement-calendar")
        self.assertAlmostEqual(trade["funding"], 1.0)
        self.assertEqual(len(trade["funding_events"]), 1)
        ev0 = trade["funding_events"][0]
        self.assertEqual(ev0["settlement_ms"], 4 * H)
        self.assertAlmostEqual(ev0["rate_bps"], 10.0)
        self.assertAlmostEqual(ev0["held_cost"], 1000.0)
        # Hold 1H->10H, calendar spans [4H,4H]: 3H head + 6H tail unknown.
        self.assertEqual(trade["funding_uncovered_ms"], 9 * H)
        self.assertEqual(res["funding_calendar"]["version"], "venue-4h/v1")
        self.assertEqual(res["funding_calendar"]["source"],
                         "synthetic-fixture")

    def test_no_crossing_no_funding_full_uncovered(self) -> None:
        candles = _hourly(12)
        cfg = _cfg(exit_horizon_ms=10 * H,
                   funding_calendar=_cal([48], 10.0))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertAlmostEqual(trade["funding"], 0.0)
        self.assertEqual(trade["funding_events"], [])
        self.assertGreater(trade["funding_uncovered_ms"], 0)


class CadenceTest(unittest.TestCase):
    def test_4h_vs_8h_settlement_lists(self) -> None:
        candles = _hourly(30)
        cfg8 = _cfg(exit_horizon_ms=24 * H,
                    funding_calendar=_cal([8, 16, 24], 10.0,
                                          version="venue-8h/v1",
                                          interval_ms=8 * H))
        cfg4 = _cfg(exit_horizon_ms=24 * H,
                    funding_calendar=_cal([4, 8, 12, 16, 20, 24], 10.0))
        r8 = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                          candles, cfg8)
        r4 = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                          candles, cfg4)
        ms8 = [e["settlement_ms"] for e in r8["trades"][0]["funding_events"]]
        ms4 = [e["settlement_ms"] for e in r4["trades"][0]["funding_events"]]
        self.assertEqual(ms8, [8 * H, 16 * H])
        self.assertEqual(ms4, [4 * H, 8 * H, 12 * H, 16 * H, 20 * H])
        self.assertAlmostEqual(r4["trades"][0]["funding"],
                               2.5 * r8["trades"][0]["funding"])


class SignMatrixTest(unittest.TestCase):
    def test_long_short_positive_negative(self) -> None:
        candles = _hourly(12)
        cases = [("LONG", 10.0, 1.0), ("SHORT", 10.0, -1.0),
                 ("LONG", -10.0, -1.0), ("SHORT", -10.0, 1.0)]
        for direction, rate, expected in cases:
            with self.subTest(direction=direction, rate=rate):
                cfg = _cfg(exit_horizon_ms=10 * H,
                           funding_calendar=_cal([4], rate))
                res = run_backtest(
                    [StudyEvent("BTCUSDT", 0, direction, 100.0)],
                    candles, cfg)
                self.assertAlmostEqual(res["trades"][0]["funding"], expected)


class PartialExposureTest(unittest.TestCase):
    def test_settlement_between_fills_sees_partial_cost(self) -> None:
        candles = _hourly(12)
        cfg = _cfg(exit_horizon_ms=10 * H,
                   partial_fill_notional_cap=500.0,
                   funding_calendar=_cal([1, 5], 10.0))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertEqual(trade["fills"], 2)
        held = [e["held_cost"] for e in trade["funding_events"]]
        self.assertAlmostEqual(held[0], 500.0)
        self.assertAlmostEqual(held[1], 1000.0)
        self.assertAlmostEqual(trade["funding"], 0.5 + 1.0)


class BoundaryTest(unittest.TestCase):
    def test_entry_edge_included_exit_edge_excluded(self) -> None:
        # Entry at first open t=H; gap-stop exit exactly at t=3H.
        candles = [_candle(H, 100.0, 100.0, 100.0, 100.0),
                   _candle(2 * H, 100.0, 100.0, 100.0, 100.0),
                   _candle(3 * H, 80.0, 80.0, 80.0, 80.0),
                   _candle(4 * H, 80.0, 80.0, 80.0, 80.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=10 * H,
                   funding_calendar=_cal([1, 3], 10.0,
                                         interval_ms=None))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        ms = [e["settlement_ms"] for e in trade["funding_events"]]
        self.assertEqual(ms, [H])  # exit edge 3H excluded
        self.assertAlmostEqual(trade["funding"], 1.0)


def _candle(t, o, h, l, c, symbol="BTCUSDT"):
    return Candle(symbol, t, o, h, l, c)


class IncompleteCalendarTest(unittest.TestCase):
    def test_uncovered_holding_reported_not_zeroed(self) -> None:
        candles = _hourly(30)
        cfg = _cfg(exit_horizon_ms=24 * H,
                   funding_calendar=_cal([4], 10.0))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertEqual(len(trade["funding_events"]), 1)
        self.assertGreater(trade["funding_uncovered_ms"], 0)
        # La completitud es por posicion: el importe liquidado observado no
        # acredita el total mientras exista exposicion sin cubrir.
        self.assertIs(trade["funding_accounting_complete"], False)
        # Settled only what the calendar lists; the rest is UNKNOWN time.
        self.assertAlmostEqual(trade["funding"], 1.0)


class EstimatedRateTest(unittest.TestCase):
    def test_estimate_is_context_never_accounting(self) -> None:
        candles = _hourly(12)
        base = dict(exit_horizon_ms=10 * H,
                    funding_calendar=_cal([4], 10.0))
        r1 = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                          candles, _cfg(**base, funding_estimated_bps=5.0))
        r2 = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                          candles, _cfg(**base, funding_estimated_bps=500.0))
        self.assertEqual(r1["trades"][0]["funding"],
                         r2["trades"][0]["funding"])
        self.assertEqual(r1["total_net"], r2["total_net"])
        self.assertEqual(r2["funding_estimated_bps_context"], 500.0)


class LegacyFallbackTest(unittest.TestCase):
    def test_no_calendar_keeps_interval_math(self) -> None:
        candles = _hourly(30)
        cfg = _cfg(exit_horizon_ms=24 * H, funding_8h_bps=10.0)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertEqual(trade["funding_model"], "interval-fallback")
        self.assertIsNone(res["funding_calendar"])
        self.assertGreater(trade["funding"], 0.0)


class CalendarIdentityTest(unittest.TestCase):
    def test_hash_stable_and_sensitive(self) -> None:
        a = _cal([4, 8], 10.0)
        b = _cal([4, 8], 10.0)
        c = _cal([4, 8], 20.0)
        self.assertEqual(a.calendar_hash(), b.calendar_hash())
        self.assertNotEqual(a.calendar_hash(), c.calendar_hash())


if __name__ == "__main__":
    unittest.main()
