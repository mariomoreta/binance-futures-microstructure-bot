import artifact from "@/data/offline-eval-v1.json";
// Read-only adapter over the versioned offline-evaluation artifact
// (OFFLINE-EVAL-V1, docs/OFFLINE_EVAL_READ_CONTRACT_V1.md). No engine
// import, no database, no network, no mutation: parse + validate only.
export const OFFLINE_EVAL_SCHEMA = 1;
export const OFFLINE_EVAL_GROUPS = ["continuation","correction-exhaustion","correction-reversal","bearish-continuation","rebound-variant","baseline"] as const;
export const OFFLINE_EVAL_SEGMENTS = ["dev","oos"] as const;
export const OFFLINE_EVAL_SCALES = ["1.0","2.0","3.0"] as const;
type Num = number | null;
const num = (v: unknown): Num => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
const rec = (v: unknown): Record<string, unknown> | null =>
  typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
export type OfflineEvalCell = {
  n_events: Num; n_trades: Num; n_expired: Num; n_mismatched: Num;
  skipped_overlap: Num; n_realized: Num; n_open: Num;
  exit_reasons: { horizon: Num; stop: Num; open_at_end: Num };
  expectancy_net: Num; expectancy_gross: Num; total_net: Num;
  total_net_realized: Num; total_fees: Num; total_funding: Num;
  max_drawdown: Num; max_drawdown_realized: Num; mfe_mean: Num; mae_mean: Num;
  config_hash: string | null;
};
export type OfflineEvalSymbol = {
  venue: string | null; interval: string | null; n_candles: Num;
  window_open_ms: Num; window_close_ms: Num; null_close_time: Num;
  close_chain_violations: Num; n_events: Num; input_hash: string | null;
  n_dev: Num; n_oos: Num; n_purged: Num;
  funding_n: Num; funding_span: [Num, Num];
};
export type OfflineEval = {
  schema_version: 1; artifact_version: string; label: string;
  engine_version: string; formation_method: string; map_candidate: string;
  cutoff_ms: Num; horizon_ms: Num;
  cost_id: string | null; fee_bps: Num; spread_bps: Num; slippage_bps: Num;
  limits: string[]; symbols: Record<string, OfflineEvalSymbol>;
  cells: Record<string, Record<string, Record<string, Record<string, OfflineEvalCell>>>>;
  pooled: Record<string, Record<string, { n_events: Num; n_trades: Num; n_realized: Num; n_open: Num; skipped_overlap: Num; total_net: Num; total_net_realized: Num; total_fees: Num; total_funding: Num; expectancy_net: Num; expectancy_net_realized: Num }>>;
  semantics: string;
};
function cell(raw: unknown): OfflineEvalCell {
  const r = rec(raw);
  if (!r) throw Error("OFFLINE_EVAL_UNAVAILABLE");
  const ex = rec(r.exit_reasons);
  return {
    n_events: num(r.n_events), n_trades: num(r.n_trades), n_expired: num(r.n_expired),
    n_mismatched: num(r.n_mismatched), skipped_overlap: num(r.skipped_overlap),
    n_realized: num(r.n_realized), n_open: num(r.n_open),
    exit_reasons: { horizon: num(ex?.horizon), stop: num(ex?.stop), open_at_end: num(ex?.open_at_end) },
    expectancy_net: num(r.expectancy_net), expectancy_gross: num(r.expectancy_gross),
    total_net: num(r.total_net), total_net_realized: num(r.total_net_realized),
    total_fees: num(r.total_fees), total_funding: num(r.total_funding),
    max_drawdown: num(r.max_drawdown), max_drawdown_realized: num(r.max_drawdown_realized),
    mfe_mean: num(r.mfe_mean), mae_mean: num(r.mae_mean), config_hash: str(r.config_hash),
  };
}
export function parseOfflineEval(raw: unknown): OfflineEval {
  const r = rec(raw);
  if (!r) throw Error("OFFLINE_EVAL_UNAVAILABLE");
  if (r.schema_version !== OFFLINE_EVAL_SCHEMA) throw Error("UNSUPPORTED_OFFLINE_EVAL_SCHEMA");
  const cells = rec(r.cells);
  const symbols = rec(r.symbols);
  const pooled = rec(r.pooled_reference);
  if (!cells || !symbols || !pooled) throw Error("OFFLINE_EVAL_UNAVAILABLE");
  for (const sym of Object.keys(symbols)) {
    const sc = rec(cells[sym]);
    if (!sc) throw Error("OFFLINE_EVAL_UNAVAILABLE");
    for (const g of OFFLINE_EVAL_GROUPS) {
      const gc = rec(sc[g]);
      if (!gc) throw Error("OFFLINE_EVAL_UNAVAILABLE");
      for (const seg of OFFLINE_EVAL_SEGMENTS) {
        const rc = rec(gc[seg]);
        if (!rc) throw Error("OFFLINE_EVAL_UNAVAILABLE");
        for (const s of OFFLINE_EVAL_SCALES) cell(rc[s]);
      }
    }
  }
  const cost = rec(r.cost_assumption);
  const out: OfflineEval = {
    schema_version: 1,
    artifact_version: String(r.artifact_version ?? "UNKNOWN"),
    label: String(r.label ?? "UNKNOWN"),
    engine_version: String(r.engine_version ?? "UNKNOWN"),
    formation_method: String(r.formation_method ?? "UNKNOWN"),
    map_candidate: String(r.map_candidate ?? "UNKNOWN"),
    cutoff_ms: num(r.cutoff_ms), horizon_ms: num(r.horizon_ms),
    cost_id: str(cost?.id), fee_bps: num(cost?.fee_bps),
    spread_bps: num(cost?.spread_bps), slippage_bps: num(cost?.slippage_bps),
    limits: Array.isArray(r.limits) ? r.limits.map(String) : [],
    symbols: {},
    cells: {},
    pooled: {},
    semantics: "Conditioned replay mechanics with assumed costs and realized venue funding; NOT validation, NOT tradable signals. Realized-only metrics exclude open marks. Grouped events are not independent samples.",
  };
  for (const [sym, sraw] of Object.entries(symbols)) {
    const s = rec(sraw) ?? {};
    const sel = rec(s.selection) ?? {};
    const fc = rec(s.funding_calendar) ?? {};
    const span = Array.isArray(fc.span_ms) ? fc.span_ms : [null, null];
    out.symbols[sym] = {
      venue: str(s.venue), interval: str(s.interval), n_candles: num(s.n_candles),
      window_open_ms: num(s.window_open_ms), window_close_ms: num(s.window_close_ms),
      null_close_time: num(s.null_close_time), close_chain_violations: num(s.close_chain_violations),
      n_events: num(s.n_events), input_hash: str(s.input_hash),
      n_dev: num(sel.n_dev), n_oos: num(sel.n_oos), n_purged: num(sel.n_purged_dev_crossing),
      funding_n: num(fc.n_settlements),
      funding_span: [num(span[0]), num(span[1])],
    };
  }
  for (const [sym, sc] of Object.entries(cells)) {
    out.cells[sym] = {};
    for (const g of OFFLINE_EVAL_GROUPS) {
      out.cells[sym]![g] = {};
      for (const seg of OFFLINE_EVAL_SEGMENTS) {
        out.cells[sym]![g]![seg] = {};
        const rc = rec(rec(sc)?.[g]) as Record<string, Record<string, unknown>> | null;
        const segc = rec(rc?.[seg]) ?? {};
        for (const s of OFFLINE_EVAL_SCALES) out.cells[sym]![g]![seg]![s] = cell(segc[s]);
      }
    }
  }
  for (const [seg, sc] of Object.entries(pooled)) {
    out.pooled[seg] = {};
    for (const [s, praw] of Object.entries(rec(sc) ?? {})) {
      const p = rec(praw) ?? {};
      out.pooled[seg]![s] = {
        n_events: num(p.n_events), n_trades: num(p.n_trades), n_realized: num(p.n_realized),
        n_open: num(p.n_open), skipped_overlap: num(p.skipped_overlap),
        total_net: num(p.total_net), total_net_realized: num(p.total_net_realized),
        total_fees: num(p.total_fees), total_funding: num(p.total_funding),
        expectancy_net: num(p.expectancy_net), expectancy_net_realized: num(p.expectancy_net_realized),
      };
    }
  }
  return out;
}
export function offlineEval(): OfflineEval {
  return parseOfflineEval(artifact as unknown);
}
export function evalUtc(v: Num): string {
  return v !== null && Number.isSafeInteger(v) && v > 0 ? new Date(v).toISOString() : "UNKNOWN";
}
export function evalMoney(v: Num): string {
  return v === null || !Number.isFinite(v) ? "UNKNOWN" : (v >= 0 ? "+" : "") + v.toFixed(2);
}
