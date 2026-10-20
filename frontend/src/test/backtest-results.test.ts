import {describe, expect, it} from "vitest";
import {
  parseBacktestSummary, parseBacktestTrades, utcOf, moneyOf, durationOf,
} from "@/lib/backtest-results";

describe("backtest results parser (read-only adapter)", () => {
  it("parses a summary and keeps UNKNOWN for absent numeric fields", () => {
    const s = parseBacktestSummary({
      experiment_id: "eval-census-v2-trio", experiment_version: "EVAL-CENSUS-V2",
      label: "Evaluacion historica...", not_label: "NO es un backtest completo...",
      engine_version: "backtest-offline/v4.2", executor_version: "dashboard-backtest-executor/v1",
      package: "docs/evidence/eval-census-v2-package", package_version: "EVAL-CENSUS-V2",
      package_files_verified: 33, package_manifest_sha256: "e0c231a771a36322",
      combos: [["BTCUSDT", "15m"]], scales: [1, 2, 3],
      groups: [{group: "continuation", label: "H1"}],
      cells: [{symbol: "BTCUSDT", res: "15m", group: "continuation", label: "H1",
        segment: "dev", scale: 1, n_events: 100, n_trades: 12, n_realized: 11, n_open: 1,
        skipped_overlap: 3, n_expired: 0, n_mismatched: 0, exit_reasons: {horizon: 10, stop: 1},
        expectancy_net: 1.5, expectancy_gross: 2.0, total_net: 18, total_net_realized: 20,
        total_fees: 4, total_funding: 0.1, max_drawdown: -3, max_drawdown_realized: -3,
        mfe_mean: 0.8, mae_mean: -0.4, config_hash: "abc", n_trades_1x: 12, status: "con_operaciones"}],
      n_trades_total: 36, n_trades_1x: 12, reconciliation_ok: true, reconciliation_rows: 56,
      duration_ms: 1000, limitations: ["l1"],
    });
    expect(s.experiment_id).toBe("eval-census-v2-trio");
    expect(s.cells).toHaveLength(1);
    expect(s.cells[0]!.exit_reasons).toEqual({horizon: 10, stop: 1});
    expect(s.reconciliation_ok).toBe(true);
    expect(s.package_manifest_sha256).toBe("e0c231a771a36322");
  });

  it("throws explicitly when the summary is unavailable (no substitute)", () => {
    expect(() => parseBacktestSummary(null)).toThrow("BACKTEST_SUMMARY_UNAVAILABLE");
    expect(() => parseBacktestSummary("x")).toThrow("BACKTEST_SUMMARY_UNAVAILABLE");
  });

  it("parses trades, preserving open_at_end and UNKNOWN coverage", () => {
    const t = parseBacktestTrades({trades: [
      {trade_id: "BTCUSDT:15m:continuation:dev:1:5", event_id: "BTCUSDT:1:LONG:H1:H1-v1:5",
       symbol: "BTCUSDT", res: "15m", group: "continuation", segment: "dev", scale: 1,
       direction: "LONG", family: "H1", rules_version: "H1-v1",
       event_time_ms: 1788903900000, entry_ms: 1788904800000, exit_ms: 1788907500000,
       entry_px: 78458.7, exit_px: 78456.8, exit_reason: "horizon",
       exit_executed: true, open_at_end: false, status: "realizada",
       gross_pnl: -0.02, fees: 1.0, funding: 0.0, net_pnl: -1.62, realized_net: -1.62,
       mfe_pct: 0.1, mae_pct: -0.2, holding_ms: 2700000,
       funding_accounting_complete: true, coverage: "completa"},
      {trade_id: "open", event_id: "e", symbol: "BTCUSDT", res: "1h", group: "baseline",
       segment: "oos", scale: 1, direction: "SHORT", family: "H1", rules_version: "H1-v1",
       event_time_ms: 1, entry_ms: 2, exit_ms: 3, entry_px: 1, exit_px: 1, exit_reason: "open_at_end",
       exit_executed: false, open_at_end: true, status: "abierta",
       gross_pnl: -2.2, fees: 0, funding: 0, net_pnl: -2.2},
    ]});
    expect(t).toHaveLength(2);
    expect(t[0]!.coverage).toBe("completa");
    expect(t[1]!.open_at_end).toBe(true);
    expect(t[1]!.coverage).toBeNull();
    expect(t[1]!.funding_accounting_complete).toBeNull();
  });

  it("returns an empty list when trades are absent, never fabricated rows", () => {
    expect(parseBacktestTrades({})).toEqual([]);
    expect(parseBacktestTrades(null)).toEqual([]);
  });

  it("formats UNKNOWN explicitly and never prints NaN", () => {
    expect(utcOf(null)).toBe("UNKNOWN");
    expect(utcOf(0)).toBe("UNKNOWN");
    expect(moneyOf(null)).toBe("UNKNOWN");
    expect(moneyOf(1.5)).toBe("+1.50");
    expect(moneyOf(-1.5)).toBe("-1.50");
    expect(durationOf(null)).toBe("UNKNOWN");
    expect(durationOf(90_000)).toBe("1m 30s");
  });
});
