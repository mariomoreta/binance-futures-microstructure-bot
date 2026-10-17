import artifact from "@/data/census-eval-v2.json";
// Read-only adapter over the census evaluation summary (CENSUS-EVAL-V2,
// docs/OFFLINE_EVAL_CENSUS_V2.md). No engine import, no database, no
// network, no mutation: parse + validate only. Research display only:
// 0 cells eligible for operation; no operable signals anywhere here.
export const CENSUS_EVAL_SCHEMA = 1;
export const CENSUS_EVAL_GROUPS = ["continuation","bearish-continuation","correction-exhaustion","correction-reversal","baseline"] as const;
export const CENSUS_EVAL_SEGMENTS = ["dev","oos"] as const;
export const CENSUS_EVAL_SCALES = ["1.0","2.0","3.0"] as const;
type Num = number | null;
const num = (v: unknown): Num => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
const rec = (v: unknown): Record<string, unknown> | null =>
  typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
export type CensusEvalCell = {
  n_events: Num; n_trades: Num; n_open: Num;
  E_net: Num; E_gross: Num; s_star: Num; placebo_E_net: Num;
  verdict: string | null; skipped_overlap: Num; exit_stop: Num;
};
export type CensusEvalFamily = { group: string | null; scenario: string | null; sources: string | null; status: string | null };
export type CensusEval = {
  schema_version: 1; artifact_version: string; label: string;
  engine_version: string; census_version: string; selector_version: string;
  mapping: string | null; horizon_rule: string | null; cutoff_ms: Num;
  cost_id: string | null;
  census: Record<string, unknown>;
  coverage: Record<string, string>;
  families: CensusEvalFamily[];
  btc_context: string | null;
  cells: Record<string, Record<string, Record<string, Record<string, Record<string, CensusEvalCell>>>>>;
  limits: string[];
};
function cell(raw: unknown): CensusEvalCell {
  const r = rec(raw);
  if (!r) throw Error("CENSUS_EVAL_UNAVAILABLE");
  return {
    n_events: num(r.n_events), n_trades: num(r.n_trades), n_open: num(r.n_open),
    E_net: num(r.E_net), E_gross: num(r.E_gross), s_star: num(r.s_star),
    placebo_E_net: num(r.placebo_E_net), verdict: str(r.verdict),
    skipped_overlap: num(r.skipped_overlap), exit_stop: num(r.exit_stop),
  };
}
export function parseCensusEval(raw: unknown): CensusEval {
  const r = rec(raw);
  if (!r) throw Error("CENSUS_EVAL_UNAVAILABLE");
  if (r.schema_version !== CENSUS_EVAL_SCHEMA) throw Error("UNSUPPORTED_CENSUS_EVAL_SCHEMA");
  const cells = rec(r.cells);
  const coverage = rec(r.coverage);
  if (!cells || !coverage) throw Error("CENSUS_EVAL_UNAVAILABLE");
  if (!Array.isArray(r.families) || !Array.isArray(r.limits)) throw Error("CENSUS_EVAL_UNAVAILABLE");
  const out: CensusEval = {
    schema_version: 1,
    artifact_version: String(r.artifact_version ?? "UNKNOWN"),
    label: String(r.label ?? "UNKNOWN"),
    engine_version: String(r.engine_version ?? "UNKNOWN"),
    census_version: String(r.census_version ?? "UNKNOWN"),
    selector_version: String(r.selector_version ?? "UNKNOWN"),
    mapping: str(r.mapping), horizon_rule: str(r.horizon_rule),
    cutoff_ms: num(r.cutoff_ms), cost_id: str(r.cost_id),
    census: rec(r.census) ?? {},
    coverage: Object.fromEntries(Object.entries(coverage).map(([k, v]) => [k, String(v)])),
    families: (r.families as unknown[]).map(f => {
      const fr = rec(f) ?? {};
      return {group: str(fr.group), scenario: str(fr.scenario), sources: str(fr.sources), status: str(fr.status)};
    }),
    btc_context: str(r.btc_context),
    cells: {}, limits: (r.limits as unknown[]).map(String),
  };
  for (const [sym, sraw] of Object.entries(cells)) {
    out.cells[sym] = {};
    for (const [res, rraw] of Object.entries(rec(sraw) ?? {})) {
      out.cells[sym]![res] = {};
      for (const g of CENSUS_EVAL_GROUPS) {
        out.cells[sym]![res]![g] = {};
        const grec = rec(rec(rraw)?.[g]);
        if (!grec) throw Error("CENSUS_EVAL_UNAVAILABLE");
        for (const seg of CENSUS_EVAL_SEGMENTS) {
          out.cells[sym]![res]![g]![seg] = {};
          const segrec = rec(grec[seg]);
          if (!segrec) throw Error("CENSUS_EVAL_UNAVAILABLE");
          for (const s of CENSUS_EVAL_SCALES) out.cells[sym]![res]![g]![seg]![s] = cell(segrec[s]);
        }
      }
    }
  }
  return out;
}
export function censusEval(): CensusEval {
  return parseCensusEval(artifact as unknown);
}
export function censusMoney(v: Num): string {
  return v === null || !Number.isFinite(v) ? "UNKNOWN" : (v >= 0 ? "+" : "") + v.toFixed(2);
}
