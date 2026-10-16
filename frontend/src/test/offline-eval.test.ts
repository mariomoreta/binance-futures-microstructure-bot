// @vitest-environment node
import {it, expect} from "vitest";
import {parseOfflineEval, offlineEval, OFFLINE_EVAL_SCHEMA} from "@/lib/offline-eval";
function cell(over: Record<string, unknown> = {}) {
  return {
    n_events: 10, n_trades: 8, n_expired: 0, n_mismatched: 0, skipped_overlap: 2,
    n_realized: 8, n_open: 0, exit_reasons: {horizon: 7, stop: 1, open_at_end: 0},
    expectancy_net: 0.5, expectancy_gross: 2.0, total_net: 4.0, total_net_realized: 4.0,
    total_fees: 8.0, total_funding: 0.0, max_drawdown: 1.0, max_drawdown_realized: 1.0,
    mfe_mean: 0.3, mae_mean: 0.1, config_hash: "abcd1234",
    funding_quality: {}, ...over,
  };
}
function minimal() {
  const groups = ["continuation","correction-exhaustion","correction-reversal","bearish-continuation","rebound-variant","baseline"];
  const cells: Record<string, unknown> = {};
  for (const g of ["BTCUSDT"]) {
    cells[g] = {};
    for (const gr of groups) {
      (cells[g] as Record<string, unknown>)[gr] = {};
      for (const seg of ["dev","oos"]) {
        ((cells[g] as Record<string, unknown>)[gr] as Record<string, unknown>)[seg] = {"1.0": cell(), "2.0": cell(), "3.0": cell()};
      }
    }
  }
  return {
    schema_version: 1, artifact_version: "OFFLINE-EVAL-V1", label: "x",
    engine_version: "backtest-offline/v4.2", formation_method: "m", map_candidate: "c",
    cutoff_ms: 1790010000000, horizon_ms: 3600000,
    cost_assumption: {id: "COST-ASSUME-v1", fee_bps: 5, spread_bps: 1, slippage_bps: 2},
    limits: ["a"],
    symbols: {BTCUSDT: {venue: "v", interval: "15m", n_candles: 2879, window_open_ms: 1, window_close_ms: 2, null_close_time: 0, close_chain_violations: 0, n_events: 10, input_hash: "h", selection: {n_dev: 5, n_oos: 5, n_purged_dev_crossing: 0}, funding_calendar: {n_settlements: 90, span_ms: [1, 2]}}},
    cells, pooled_reference: {dev: {"1.0": {n_events: 10, n_trades: 8, n_realized: 8, n_open: 0, skipped_overlap: 2, total_net: 4, total_net_realized: 4, total_fees: 8, total_funding: 0, expectancy_net: 0.5, expectancy_net_realized: 0.5}}},
  };
}
it("parses a minimal valid artifact without touching engine/db/network", () => {
  const v = parseOfflineEval(minimal());
  expect(v.schema_version).toBe(OFFLINE_EVAL_SCHEMA);
  expect(v.cells.BTCUSDT?.continuation?.dev?.["1.0"]?.n_trades).toBe(8);
  expect(v.symbols.BTCUSDT?.funding_n).toBe(90);
  expect(v.pooled.dev?.["1.0"]?.expectancy_net).toBe(0.5);
});
it("rejects unknown schema versions instead of coercing", () => {
  expect(() => parseOfflineEval({...minimal(), schema_version: 2})).toThrow("UNSUPPORTED_OFFLINE_EVAL_SCHEMA");
});
it("reports unavailable on missing cells rather than fabricating", () => {
  const m = minimal() as Record<string, unknown>;
  delete (m.cells as Record<string, unknown>).BTCUSDT;
  expect(() => parseOfflineEval(m)).toThrow("OFFLINE_EVAL_UNAVAILABLE");
  expect(() => parseOfflineEval(null)).toThrow("OFFLINE_EVAL_UNAVAILABLE");
});
it("bundled artifact pins the evaluated run (versions, counts, purge)", () => {
  const v = offlineEval();
  expect(v.artifact_version).toBe("OFFLINE-EVAL-V1");
  expect(v.engine_version).toBe("backtest-offline/v4.2");
  expect(v.cutoff_ms).toBe(1790010000000);
  expect(Object.keys(v.symbols).sort()).toEqual(["BTCUSDT","ETHUSDT","SOLUSDT"]);
  expect(v.symbols.BTCUSDT?.n_candles).toBe(2879);
  expect(v.symbols.BTCUSDT?.close_chain_violations).toBe(0);
  // flow BTC continuation dev: 121 events -> 105 trades, 16 overlap skips
  expect(v.cells.BTCUSDT?.continuation?.dev?.["1.0"]).toMatchObject({n_events: 121, n_trades: 105, skipped_overlap: 16, n_open: 0});
  // rebound-variant is excluded-empty everywhere by construction
  expect(v.cells.SOLUSDT?.["rebound-variant"]?.oos?.["1.0"]?.n_events).toBe(0);
  // pooled held-out reference at 1x (conditioned, not a strategy)
  expect(v.pooled.oos?.["1.0"]?.n_trades).toBe(746);
  expect(v.limits.length).toBeGreaterThan(5);
});
