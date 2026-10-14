"""Delivery regressions R1-R7: corrective closeout numbers, pinned exactly.

Each case pins one demanded figure: 100ms holding cap, cross-contract
calendar rejection, runner symbol preservation, stale-mark exclusion,
entry/exit commissions 1.00/1.20, open-mark exclusion, and the V2 schema
matrix. Synthetic fixtures only; temp dirs for runner I/O; no network,
no DB, no canonical paths. Run: python run_tests.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from microstructure_probe.backtest_offline import (
    BacktestConfig,
    Candle,
    FundingCalendar,
    FundingSettlement,
    StudyEvent,
    run_backtest,
)

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts" / "run_family_evaluation.py"
H = 3600_000


def _cfg(**kw):
    base = dict(fee_bps=0.0, funding_8h_bps=0.0, spread_bps=0.0,
                slippage_bps=0.0, notional_usdt=1000.0,
                stop_distance_pct=50.0)
    base.update(kw)
    return BacktestConfig(**base)


def _ms_candles(opens, px=100.0, symbol="BTCUSDT"):
    return [Candle(symbol, t, px, px + 0.05, px - 0.05, px)
            for t in opens]


class R1HoldingCapTest(unittest.TestCase):
    def test_100ms_holding_uncovered_never_above_100(self) -> None:
        # Entry at t=0, effective close at t=100 (100ms holding); the only
        # listed settlement sits at t=5000 (far outside the span).
        candles = _ms_candles([0, 50, 100])
        cal = FundingCalendar(version="venue-4h/v1",
                              source="synthetic-fixture", interval_ms=4 * H,
                              settlements=(FundingSettlement(5000, 10.0),))
        cfg = _cfg(exit_horizon_ms=101, funding_calendar=cal)
        res = run_backtest([StudyEvent("BTCUSDT", -1, "LONG", 100.0)],
                           candles, cfg)
        t = res["trades"][0]
        holding = t["exit_ms"] - t["entry_ms"]
        self.assertEqual(holding, 100)
        self.assertEqual(t["funding_uncovered_ms"], 100)
        self.assertLessEqual(t["funding_uncovered_ms"], holding)


class R2CrossContractRejectionTest(unittest.TestCase):
    def test_lumia_calendar_cannot_settle_btc_operation(self) -> None:
        candles = [Candle("BTCUSDT", i * H, 100.0, 100.1, 99.9, 100.0)
                   for i in range(12)]
        cal = FundingCalendar(version="venue-4h/v1",
                              source="exchange-funding-history",
                              interval_ms=4 * H, symbol="LUMIAUSDT",
                              settlements=(FundingSettlement(4 * H, 10.0),))
        cfg = _cfg(exit_horizon_ms=10 * H, funding_calendar=cal)
        with self.assertRaises(ValueError):
            run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                         candles, cfg)

    def test_matching_symbol_settles(self) -> None:
        candles = [Candle("BTCUSDT", i * H, 100.0, 100.1, 99.9, 100.0)
                   for i in range(12)]
        cal = FundingCalendar(version="venue-4h/v1",
                              source="exchange-funding-history",
                              interval_ms=4 * H, symbol="BTCUSDT",
                              settlements=(FundingSettlement(4 * H, 10.0),))
        cfg = _cfg(exit_horizon_ms=10 * H, funding_calendar=cal)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(len(res["trades"]), 1)


class R3RunnerSymbolPreservationTest(unittest.TestCase):
    def test_calendar_symbol_survives_json_load(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="r3_"))
        candles = [{"symbol": "BTCUSDT", "open_time_ms": 1_700_000_000_000
                    + i * H, "open": 100.0, "high": 100.1, "low": 99.9,
                    "close": 100.0} for i in range(30)]
        events = [{"symbol": "BTCUSDT", "event_time_ms": 1_700_000_000_000,
                   "direction": "LONG", "reference_price": 100.0,
                   "family": "H1", "rules_version": "H1-v1",
                   "group": "continuation"}]
        calendar = {"version": "venue-4h/v1", "source": "external",
                    "interval_ms": 4 * H, "symbol": "BTCUSDT",
                    "settlements": [{"settlement_ms": 1_700_000_000_000
                                     + 4 * H, "rate_bps": 10.0}]}
        (tmp / "candles.json").write_text(json.dumps(candles),
                                          encoding="utf-8")
        (tmp / "events.json").write_text(json.dumps(events),
                                         encoding="utf-8")
        (tmp / "calendar.json").write_text(json.dumps(calendar),
                                           encoding="utf-8")
        out = tmp / "manifest.json"
        proc = subprocess.run(
            [sys.executable, str(RUNNER), "--events", str(tmp / "events.json"),
             "--candles", str(tmp / "candles.json"),
             "--calendar", str(tmp / "calendar.json"),
             "--cutoff-ms", str(1_700_000_000_000 + 100 * H),
             "--out", str(out)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        manifest = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(manifest["funding_calendar"]["symbol"], "BTCUSDT")
        self.assertEqual(manifest["funding_calendar"]["version"],
                         "venue-4h/v1")


class R4StaleMarkTest(unittest.TestCase):
    def test_stale_proxy_excluded_fresh_settles_with_age(self) -> None:
        # Irregular 0/12/24/60H candles (data step 12H) with a 4H nominal
        # calendar. Settlement at 28H rides a 4H-old print: PROXY (settles,
        # age recorded, never called fresh). At 40H the print is 16H old
        # (data gap): STALE -> UNKNOWN-excluded, never settled as proxy.
        candles = [Candle("BTCUSDT", h * H, 100.0, 100.1, 99.9, 100.0)
                   for h in (0, 12, 24, 60)]
        cal = FundingCalendar(version="venue-4h/v1",
                              source="synthetic-fixture", interval_ms=4 * H,
                              settlements=(FundingSettlement(28 * H, 10.0),
                                           FundingSettlement(40 * H, 10.0)))
        cfg = _cfg(exit_horizon_ms=70 * H, funding_calendar=cal)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        t = res["trades"][0]
        settled = [e for e in t["funding_events"]
                   if e["basis"] == "settled"]
        excluded = [e for e in t["funding_events"]
                    if e["basis"] == "unknown-excluded"]
        self.assertEqual([e["settlement_ms"] for e in settled], [28 * H])
        self.assertEqual(settled[0]["mark_age_ms"], 4 * H)
        self.assertEqual(settled[0]["mark_freshness"], "proxy")
        self.assertEqual(settled[0]["data_step_ms"], 12 * H)
        self.assertEqual([e["settlement_ms"] for e in excluded], [40 * H])
        self.assertEqual(t["funding_unknown"], 1)
        self.assertAlmostEqual(t["funding"], 1.0)
        # This calendar itself is gapped (28H->40H vs 4H nominal), and
        # the position is accounting-incomplete for its own reasons
        # (stale exclusion + gap/uncovered spans): two verdicts, never
        # one inferred from the other.
        self.assertFalse(t["funding_accounting_complete"])
        self.assertFalse(res["funding_calendar"]["complete"])
        self.assertEqual(res["funding_calendar"]["gaps"],
                         [{"from_ms": 28 * H, "to_ms": 40 * H}])

    def test_fully_covered_position_is_accounting_complete(self) -> None:
        # Entry exactly on the first settlement, exit exactly on the last:
        # one fresh settlement, zero gaps, zero uncovered holding.
        candles = [Candle("BTCUSDT", i * H, 100.0, 100.1, 99.9, 100.0)
                   for i in range(30)]
        cal = FundingCalendar(version="venue-4h/v1",
                              source="synthetic-fixture", interval_ms=4 * H,
                              settlements=(FundingSettlement(H, 10.0),
                                           FundingSettlement(5 * H, 10.0)))
        cfg = _cfg(exit_horizon_ms=5 * H, funding_calendar=cal)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        t = res["trades"][0]
        self.assertEqual(t["entry_ms"], H)
        self.assertEqual(t["exit_ms"], 5 * H)
        self.assertEqual([e["settlement_ms"]
                          for e in t["funding_events"]
                          if e["basis"] == "settled"], [H])
        self.assertEqual(t["funding_unknown"], 0)
        self.assertEqual(t["funding_gap_ms"], 0)
        self.assertEqual(t["funding_uncovered_ms"], 0)
        self.assertTrue(t["funding_accounting_complete"])


class R5CommissionsTest(unittest.TestCase):
    def test_10u_100_to_120_fee_10bps_is_1_00_and_1_20(self) -> None:
        T0 = 1_800_000_000_000
        candles = [Candle("BTCUSDT", T0 + i * 60_000, 100.0, 100.05,
                          99.95, 100.0) for i in range(58)]
        candles.append(Candle("BTCUSDT", T0 + 58 * 60_000, 100.0, 120.0,
                              100.0, 120.0))
        candles += [Candle("BTCUSDT", T0 + i * 60_000, 120.0, 120.05,
                           119.95, 120.0) for i in range(59, 71)]
        cfg = _cfg(fee_bps=10.0, exit_horizon_ms=H)
        res = run_backtest([StudyEvent("BTCUSDT", T0 - 1, "LONG", 100.0)],
                           candles, cfg)
        t = res["trades"][0]
        self.assertTrue(t["exit_executed"])
        self.assertAlmostEqual(t["filled_qty"], 10.0)
        self.assertAlmostEqual(t["entry_fees"], 1.00)
        self.assertAlmostEqual(t["exit_fees"], 1.20)
        self.assertAlmostEqual(t["fees"], 2.20)


class R6OpenExcludedTest(unittest.TestCase):
    def test_open_positions_out_of_realized(self) -> None:
        T0 = 1_800_000_000_000
        candles = [Candle("BTCUSDT", T0 + i * 60_000, 100.0, 100.05,
                          99.95, 100.0) for i in range(6)]
        res = run_backtest([StudyEvent("BTCUSDT", T0 - 1, "LONG", 100.0)],
                           candles, _cfg(exit_horizon_ms=H))
        self.assertEqual(res["n_open"], 1)
        self.assertEqual(res["n_realized"], 0)
        self.assertEqual(res["total_net_realized"], 0.0)
        self.assertEqual(res["equity_curve_realized"], [])
        self.assertEqual(res["max_drawdown_realized"], 0.0)


class R7SchemaMatrixTest(unittest.TestCase):
    def test_backend_v10_v3_matrix_pinned(self) -> None:
        from microstructure_probe import history_store, persistence
        self.assertEqual(history_store.SCHEMA_VERSION, 3)
        self.assertTrue(callable(
            getattr(persistence.PersistenceStore, "_finish_v10", None)))

    def test_handoff_states_real_reads_and_gates(self) -> None:
        doc = (ROOT / "docs" / "DASHBOARD_V2_27B7AF5_READ_HANDOFF.md"
               ).read_text(encoding="utf-8")
        for anchor in ("historical-coverage.ts",
                       "data/historical/historical.db",
                       "UNSUPPORTED_HISTORICAL_SCHEMA",
                       "UNSUPPORTED_SYSTEM_SCHEMA",
                       "history_meta.schema_version",
                       "persistence_meta.schema_version"):
            self.assertIn(anchor, doc)


class R8FundingHorizonCausalityTest(unittest.TestCase):
    def test_later_candles_never_move_earlier_funding(self) -> None:
        # Review finding on dcb2e32: 0/12/24/36h candles, entry 12h,
        # effective exit 24h, calendar 12/16/20/24h. The full-series data
        # step (12h) settles 12/16/20 (fresh/proxy/proxy = 3); appending
        # 37-48h hourly candles dragged the median step to ~1h and flipped
        # 16h/20h to stale (3 -> 1). Causality demands the prefix known at
        # exit_ms: both inputs must settle identically.
        base = [Candle("BTCUSDT", h * H, 100.0, 100.1, 99.9, 100.0)
                for h in (0, 12, 24, 36)]
        late = base + [Candle("BTCUSDT", 37 * H + k * (H // 12), 100.0,
                              100.1, 99.9, 100.0) for k in range(132)]
        cal = FundingCalendar(version="venue-4h/v1",
                              source="synthetic-fixture", interval_ms=4 * H,
                              symbol="BTCUSDT",
                              settlements=tuple(
                                  FundingSettlement(m * H, 10.0)
                                  for m in (12, 16, 20, 24)))
        cfg = _cfg(exit_horizon_ms=24 * H, funding_calendar=cal)
        r_base = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                              base, cfg)
        r_late = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                              late, cfg)
        t_base = r_base["trades"][0]
        t_late = r_late["trades"][0]
        for t in (t_base, t_late):
            self.assertEqual((t["entry_ms"], t["exit_ms"]), (12 * H, 24 * H))
        settled = lambda t: [e["settlement_ms"] for e in t["funding_events"]
                             if e["basis"] == "settled"]
        self.assertEqual(settled(t_base), [12 * H, 16 * H, 20 * H])
        self.assertEqual(settled(t_late), settled(t_base))
        self.assertAlmostEqual(t_late["funding"], t_base["funding"])
        self.assertAlmostEqual(t_base["funding"], 3.0)
        self.assertEqual(t_late["funding_unknown"],
                         t_base["funding_unknown"])
        self.assertEqual(t_late["funding_accounting_complete"],
                         t_base["funding_accounting_complete"])


class R9InHoldingCausalityTest(unittest.TestCase):
    def test_mid_holding_candles_never_move_earlier_settlements(self) -> None:
        # Review finding on 4f1d92e: the exit_ms prefix (R8) was still
        # retrospective INSIDE the holding. Base 0/12/24/36h settles
        # 12/16/20 (fresh/proxy/proxy = 3); inserting 21/22/23h candles
        # dragged the shared median step and flipped 16h/20h to stale
        # (3 -> 1). Each settlement must use the prefix known at its own
        # settlement_ms, so both inputs settle identically.
        base = [Candle("BTCUSDT", h * H, 100.0, 100.1, 99.9, 100.0)
                for h in (0, 12, 24, 36)]
        mid = sorted(
            base + [Candle("BTCUSDT", h * H, 100.0, 100.1, 99.9, 100.0)
                    for h in (21, 22, 23)],
            key=lambda c: c.open_time_ms)
        cal = FundingCalendar(version="venue-4h/v1",
                              source="synthetic-fixture", interval_ms=4 * H,
                              symbol="BTCUSDT",
                              settlements=tuple(
                                  FundingSettlement(m * H, 10.0)
                                  for m in (12, 16, 20, 24)))
        cfg = _cfg(exit_horizon_ms=24 * H, funding_calendar=cal)
        r_base = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                              base, cfg)
        r_mid = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                             mid, cfg)
        t_base = r_base["trades"][0]
        t_mid = r_mid["trades"][0]
        settled = lambda t: [e["settlement_ms"] for e in t["funding_events"]
                             if e["basis"] == "settled"]
        self.assertEqual(settled(t_base), [12 * H, 16 * H, 20 * H])
        self.assertEqual(settled(t_mid), settled(t_base))
        fresh = lambda t: {e["settlement_ms"]: e["mark_freshness"]
                           for e in t["funding_events"]
                           if e["basis"] == "settled"}
        self.assertEqual(fresh(t_mid), fresh(t_base))
        self.assertEqual(fresh(t_base)[16 * H], "proxy")
        self.assertEqual(fresh(t_base)[20 * H], "proxy")
        self.assertAlmostEqual(t_mid["funding"], t_base["funding"])
        self.assertAlmostEqual(t_base["funding"], 3.0)
        # Behavior version is identifiable in results (review 4f1d92e:
        # a contract note alone does not distinguish executions).
        self.assertEqual(r_base["engine_version"], "backtest-offline/v4.2")
        self.assertEqual(r_mid["engine_version"], "backtest-offline/v4.2")


if __name__ == "__main__":
    unittest.main()
