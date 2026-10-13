"""Funding assessment: qty x mark, identity, dedup, gaps, unknown, fallback.

Additive to funding v4 (existing battery untouched): exposure is current
quantity x causal settlement mark (not entry-frozen cost), every event
carries contract identity, exact duplicates dedup (conflicts reject the
run), interior gaps are detected against the nominal cadence (first/last
never imply completeness), unresolvable marks are excluded as unknown,
and the interval fallback carries an explicit synthetic marker.
Synthetic fixtures only. Run: python run_tests.py
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


def _hourly(n, start=0, px=100.0, growth=0.0):
    out = []
    p = px
    for i in range(n):
        out.append(Candle("BTCUSDT", start + i * H, p, p * 1.001,
                          p * 0.999, p))
        p *= (1.0 + growth)
    return out


def _cal(hours, rate_bps, **kw):
    base = dict(version="venue-4h/v1", source="synthetic-fixture",
                interval_ms=4 * H)
    base.update(kw)
    return FundingCalendar(
        **base,
        settlements=tuple(FundingSettlement(h * H, rate_bps)
                          for h in hours))


class QtyTimesMarkTest(unittest.TestCase):
    def test_sloped_prices_use_settlement_mark(self) -> None:
        # Sloped 1%/h: the fill lands on the 1H open (101.0, since the
        # event sits exactly on the 0H open and fills strictly after it);
        # the 4H settlement marks at the 4H candle open, NOT entry cost.
        candles = _hourly(12, px=100.0, growth=0.01)
        cfg = _cfg(exit_horizon_ms=10 * H,
                   funding_calendar=_cal([4], 10.0))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        t = res["trades"][0]
        ev = [e for e in t["funding_events"] if e["basis"] == "settled"]
        self.assertEqual(len(ev), 1)
        mark = 100.0 * (1.01 ** 4)  # open of the 4H candle
        qty = 1000.0 / (100.0 * 1.01)  # filled at the 1H open
        self.assertAlmostEqual(ev[0]["settlement_mark_px"], mark)
        self.assertAlmostEqual(ev[0]["held_qty"], qty)
        self.assertAlmostEqual(t["funding"], qty * mark * 10.0 / 10_000.0)
        self.assertNotAlmostEqual(t["funding"], 1.0)  # not entry-frozen
        self.assertEqual(ev[0]["mark_source"], "candle-open")

    def test_flat_prices_match_cost_basis(self) -> None:
        candles = _hourly(12)
        cfg = _cfg(exit_horizon_ms=10 * H,
                   funding_calendar=_cal([4], 10.0))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertAlmostEqual(res["trades"][0]["funding"], 1.0)


class IdentityTest(unittest.TestCase):
    def test_events_carry_contract_identity(self) -> None:
        candles = _hourly(12)
        cfg = _cfg(exit_horizon_ms=10 * H,
                   funding_calendar=_cal([4], 10.0, symbol="BTCUSDT",
                                         version="venue-4h/v9",
                                         source="exchange-history"))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        ev = res["trades"][0]["funding_events"][0]
        self.assertEqual(ev["symbol"], "BTCUSDT")
        self.assertEqual(ev["calendar_symbol"], "BTCUSDT")
        self.assertEqual(ev["calendar_version"], "venue-4h/v9")
        self.assertEqual(ev["calendar_source"], "exchange-history")
        self.assertEqual(ev["basis"], "settled")
        cal = res["funding_calendar"]
        self.assertEqual(cal["symbol"], "BTCUSDT")
        self.assertEqual(cal["version"], "venue-4h/v9")

    def test_absent_symbol_recorded_unknown_never_invented(self) -> None:
        candles = _hourly(12)
        cfg = _cfg(exit_horizon_ms=10 * H,
                   funding_calendar=_cal([4], 10.0))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        ev = res["trades"][0]["funding_events"][0]
        self.assertIsNone(ev["calendar_symbol"])
        self.assertIsNone(res["funding_calendar"]["symbol"])


class DuplicateSettlementTest(unittest.TestCase):
    def test_exact_duplicates_deduped_and_counted(self) -> None:
        candles = _hourly(12)
        cal = FundingCalendar(
            version="venue-4h/v1", source="synthetic-fixture",
            interval_ms=4 * H,
            settlements=(FundingSettlement(4 * H, 10.0),
                         FundingSettlement(4 * H, 10.0)))
        cfg = _cfg(exit_horizon_ms=10 * H, funding_calendar=cal)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        settled = [e for e in res["trades"][0]["funding_events"]
                   if e["basis"] == "settled"]
        self.assertEqual(len(settled), 1)  # no double payment
        self.assertAlmostEqual(res["trades"][0]["funding"], 1.0)
        self.assertEqual(res["funding_calendar"]["duplicates_deduped"], 1)

    def test_conflicting_duplicates_reject_run(self) -> None:
        candles = _hourly(12)
        cal = FundingCalendar(
            version="venue-4h/v1", source="synthetic-fixture",
            interval_ms=4 * H,
            settlements=(FundingSettlement(4 * H, 10.0),
                         FundingSettlement(4 * H, -10.0)))
        cfg = _cfg(exit_horizon_ms=10 * H, funding_calendar=cal)
        with self.assertRaises(ValueError):
            run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                         candles, cfg)


class GapAssessmentTest(unittest.TestCase):
    def test_interior_gap_detected_not_assumed_cadence(self) -> None:
        candles = _hourly(30)
        cfg = _cfg(exit_horizon_ms=24 * H,
                   funding_calendar=_cal([4, 12], 10.0))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        cal = res["funding_calendar"]
        self.assertFalse(cal["complete"])
        self.assertEqual(cal["gaps"], [{"from_ms": 4 * H, "to_ms": 12 * H}])
        # Holding 1H->24H overlaps the (4H,12H) gap: reported, bounded.
        self.assertGreater(res["trades"][0]["funding_gap_ms"], 0)
        # Listed settlements still settle exactly once each.
        ms = [e["settlement_ms"]
              for e in res["trades"][0]["funding_events"]
              if e["basis"] == "settled"]
        self.assertEqual(ms, [4 * H, 12 * H])

    def test_continuous_calendar_is_complete(self) -> None:
        candles = _hourly(30)
        cfg = _cfg(exit_horizon_ms=24 * H,
                   funding_calendar=_cal([4, 8, 12], 10.0))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        cal = res["funding_calendar"]
        self.assertTrue(cal["complete"])
        self.assertEqual(cal["gaps"], [])
        self.assertEqual(res["trades"][0]["funding_gap_ms"], 0)

    def test_no_nominal_cadence_is_unknown_basis(self) -> None:
        candles = _hourly(12)
        cfg = _cfg(exit_horizon_ms=10 * H,
                   funding_calendar=_cal([4], 10.0, interval_ms=None))
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        cal = res["funding_calendar"]
        self.assertFalse(cal["complete"])
        self.assertIn("first/last", cal["completeness_basis"])


class UnknownMarkTest(unittest.TestCase):
    def test_settlement_mark_helper_needs_cover(self) -> None:
        from microstructure_probe.backtest_offline import _settlement_mark
        candles = _hourly(4, start=H)
        self.assertEqual(_settlement_mark(candles, 0), (None, None))
        mark, age = _settlement_mark(candles, H)
        self.assertAlmostEqual(mark, 100.0)
        self.assertEqual(age, 0)
        # Far-future settlement reuses the last known open (causal) with
        # its age recorded; staleness is judged by the caller, not hidden.
        mark, age = _settlement_mark(candles, 99 * H)
        self.assertAlmostEqual(mark, 100.0)
        self.assertEqual(age, 95 * H)

    def test_pre_entry_settlement_settles_nothing(self) -> None:
        # Settlement at t=0 precedes the first fill (entry at H): outside
        # [entry, exit), so nothing settles; the span stays uncovered.
        candles = _hourly(12, start=H)
        cal = _cal([0], 10.0, interval_ms=None)
        cfg = _cfg(exit_horizon_ms=10 * H, funding_calendar=cal)
        res = run_backtest([StudyEvent("BTCUSDT", H - 1, "LONG", 100.0)],
                           candles, cfg)
        t = res["trades"][0]
        settled = [e for e in t["funding_events"]
                   if e["basis"] == "settled"]
        self.assertEqual(settled, [])
        self.assertAlmostEqual(t["funding"], 0.0)
        self.assertGreater(t["funding_uncovered_ms"], 0)


class FallbackMarkerTest(unittest.TestCase):
    def test_fallback_carries_explicit_synthetic_marker(self) -> None:
        candles = _hourly(30)
        cfg = _cfg(exit_horizon_ms=24 * H, funding_8h_bps=10.0)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        t = res["trades"][0]
        self.assertEqual(t["funding_model"], "interval-fallback")
        self.assertEqual(len(t["funding_events"]), 1)
        self.assertEqual(t["funding_events"][0]["basis"],
                         "synthetic-fallback")
        self.assertGreater(t["funding"], 0.0)


if __name__ == "__main__":
    unittest.main()
