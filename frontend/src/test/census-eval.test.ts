// @vitest-environment node
import {it, expect} from "vitest";
import {parseCensusEval, censusEval, CENSUS_EVAL_SCHEMA} from "@/lib/census-eval";
function cell(over: Record<string, unknown> = {}) {
  return {
    n_events: 40, n_trades: 24, n_open: 0, E_net: -1.8, E_gross: -0.25,
    s_star: -0.16, placebo_E_net: -1.5, verdict: "REJECTED (fails accept: beats-placebo AND survives-2x)",
    skipped_overlap: 16, exit_stop: 6, ...over,
  };
}
function minimal() {
  const groups = ["continuation","bearish-continuation","correction-exhaustion","correction-reversal","baseline"];
  const cells: Record<string, unknown> = {BTCUSDT: {"15m": {}, "1h": {}}};
  for (const res of ["15m", "1h"]) {
    for (const g of groups) {
      ((cells.BTCUSDT as Record<string, unknown>)[res] as Record<string, unknown>)[g] = {};
      for (const seg of ["dev","oos"]) {
        ((((cells.BTCUSDT as Record<string, unknown>)[res] as Record<string, unknown>)[g]) as Record<string, unknown>)[seg] = {"1.0": cell(), "2.0": cell(), "3.0": cell()};
      }
    }
  }
  return {
    schema_version: 1, artifact_version: "CENSUS-EVAL-V2", label: "x",
    engine_version: "backtest-offline/v4.2", census_version: "CENSUS-V1",
    selector_version: "SELECTOR-EXTREME-V1", mapping: "MAP-CANDIDATE-v2",
    horizon_rule: "HORIZON-GRID4-V1", cutoff_ms: 1790010000000,
    cost_id: "COST-ASSUME-v1",
    census: {detections: 9320}, coverage: {market_cap: "UNKNOWN (never low-cap-by-proxy)"},
    families: [{group: "rebound-variant", scenario: "H2 rebound", sources: "none", status: "EXCLUDED"}],
    btc_context: "synced at/before T",
    cells, limits: ["a"],
  };
}
it("parses a minimal valid census summary without touching engine/db/network", () => {
  const v = parseCensusEval(minimal());
  expect(v.schema_version).toBe(CENSUS_EVAL_SCHEMA);
  expect(v.cells.BTCUSDT?.["15m"]?.continuation?.dev?.["1.0"]?.n_trades).toBe(24);
  expect(v.coverage.market_cap).toContain("UNKNOWN");
});
it("rejects unknown schema versions instead of coercing", () => {
  expect(() => parseCensusEval({...minimal(), schema_version: 2})).toThrow("UNSUPPORTED_CENSUS_EVAL_SCHEMA");
});
it("reports unavailable on missing groups rather than fabricating", () => {
  const m = minimal() as Record<string, unknown>;
  delete (((m.cells as Record<string, unknown>).BTCUSDT as Record<string, unknown>)["15m"] as Record<string, unknown>).continuation;
  expect(() => parseCensusEval(m)).toThrow("CENSUS_EVAL_UNAVAILABLE");
  expect(() => parseCensusEval(null)).toThrow("CENSUS_EVAL_UNAVAILABLE");
});
it("bundled summary pins the census evaluation (no operable signals)", () => {
  const v = censusEval();
  expect(v.artifact_version).toBe("CENSUS-EVAL-V2");
  expect(v.census_version).toBe("CENSUS-V1");
  expect(v.families.some(f => (f.group ?? "").includes("rebound") && (f.status ?? "").includes("EXCLUDED"))).toBe(true);
  expect(v.limits.length).toBeGreaterThan(5);
  // spot-check a real evaluated cell: BTC 15m continuation dev 145 trades, negative @1x
  expect(v.cells.BTCUSDT?.["15m"]?.continuation?.dev?.["1.0"]).toMatchObject({n_trades: 145});
  expect(v.cells.BTCUSDT?.["15m"]?.continuation?.dev?.["1.0"]?.E_net as number).toBeLessThan(0);
});
