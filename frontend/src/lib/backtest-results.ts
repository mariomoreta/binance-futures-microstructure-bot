// Adaptador de SOLO LECTURA sobre los resultados del Backtest offline de
// Dashboard V2. Sin motor, sin red, sin mutacion: parseo + validacion.
// La ejecucion real vive en /api/v1/backtest/* (backend Python acotado).

export type BacktestJobStatus = "pendiente" | "ejecutando" | "completado" | "fallido" | "sin_ejecutar";

export type BacktestCell = {
  symbol: string; res: string; group: string; label: string;
  segment: string | null; scale: number | null;
  n_events: number | null; n_trades: number | null;
  n_realized: number | null; n_open: number | null;
  skipped_overlap: number | null; n_expired: number | null; n_mismatched: number | null;
  exit_reasons: Record<string, number> | null;
  expectancy_net: number | null; expectancy_gross: number | null;
  total_net: number | null; total_net_realized: number | null;
  total_fees: number | null; total_funding: number | null;
  max_drawdown: number | null; max_drawdown_realized: number | null;
  mfe_mean: number | null; mae_mean: number | null;
  config_hash: string | null; n_trades_1x: number | null; status: string | null;
};

export type BacktestSummary = {
  experiment_id: string; experiment_version: string; label: string; not_label: string;
  engine_version: string; executor_version: string;
  package: string; package_version: string; package_files_verified: number | null;
  package_manifest_sha256: string | null;
  combos: [string, string][]; scales: number[]; groups: {group: string; label: string}[];
  placebo_note: string | null; horizon_rule: string | null; mapping: string | null;
  cost_model: string | null; cells: BacktestCell[];
  n_trades_total: number | null; n_trades_1x: number | null;
  reconciliation_ok: boolean | null; reconciliation_rows: number | null;
  duration_ms: number | null; limitations: string[];
};

export type BacktestTrade = {
  trade_id: string; event_id: string; symbol: string; res: string;
  group: string; segment: string; scale: number;
  direction: string; family: string; rules_version: string;
  event_time_ms: number; entry_ms: number; exit_ms: number;
  entry_px: number; exit_px: number; exit_reason: string;
  exit_executed: boolean; open_at_end: boolean; status: string;
  gross_pnl: number | null; fees: number | null; funding: number | null;
  net_pnl: number | null; realized_net: number | null;
  mfe_pct: number | null; mae_pct: number | null; holding_ms: number | null;
  funding_accounting_complete: boolean | null; coverage: string | null;
};

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
const rec = (v: unknown): Record<string, unknown> | null =>
  typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : null;

function cell(raw: unknown): BacktestCell {
  const r = rec(raw) ?? {};
  const er = rec(r.exit_reasons);
  return {
    symbol: String(r.symbol ?? "UNKNOWN"), res: String(r.res ?? "UNKNOWN"),
    group: String(r.group ?? "UNKNOWN"), label: String(r.label ?? ""),
    segment: str(r.segment), scale: num(r.scale),
    n_events: num(r.n_events), n_trades: num(r.n_trades),
    n_realized: num(r.n_realized), n_open: num(r.n_open),
    skipped_overlap: num(r.skipped_overlap), n_expired: num(r.n_expired),
    n_mismatched: num(r.n_mismatched),
    exit_reasons: er ? Object.fromEntries(Object.entries(er).map(([k, v]) => [k, num(v) ?? 0])) : null,
    expectancy_net: num(r.expectancy_net), expectancy_gross: num(r.expectancy_gross),
    total_net: num(r.total_net), total_net_realized: num(r.total_net_realized),
    total_fees: num(r.total_fees), total_funding: num(r.total_funding),
    max_drawdown: num(r.max_drawdown), max_drawdown_realized: num(r.max_drawdown_realized),
    mfe_mean: num(r.mfe_mean), mae_mean: num(r.mae_mean),
    config_hash: str(r.config_hash), n_trades_1x: num(r.n_trades_1x), status: str(r.status),
  };
}

export function parseBacktestSummary(raw: unknown): BacktestSummary {
  const r = rec(raw);
  if (!r) throw Error("BACKTEST_SUMMARY_UNAVAILABLE");
  return {
    experiment_id: String(r.experiment_id ?? "UNKNOWN"),
    experiment_version: String(r.experiment_version ?? "UNKNOWN"),
    label: String(r.label ?? "UNKNOWN"), not_label: String(r.not_label ?? ""),
    engine_version: String(r.engine_version ?? "UNKNOWN"),
    executor_version: String(r.executor_version ?? "UNKNOWN"),
    package: String(r.package ?? "UNKNOWN"), package_version: String(r.package_version ?? "UNKNOWN"),
    package_files_verified: num(r.package_files_verified),
    package_manifest_sha256: str(r.package_manifest_sha256),
    combos: Array.isArray(r.combos) ? (r.combos as [string, string][]) : [],
    scales: Array.isArray(r.scales) ? r.scales.map((x) => num(x) ?? 0) : [],
    groups: Array.isArray(r.groups)
      ? (r.groups as unknown[]).map((g) => ({group: String(rec(g)?.group ?? ""), label: String(rec(g)?.label ?? "")}))
      : [],
    placebo_note: str(r.placebo_note), horizon_rule: str(r.horizon_rule),
    mapping: str(r.mapping), cost_model: str(r.cost_model),
    cells: Array.isArray(r.cells) ? r.cells.map(cell) : [],
    n_trades_total: num(r.n_trades_total), n_trades_1x: num(r.n_trades_1x),
    reconciliation_ok: typeof r.reconciliation_ok === "boolean" ? r.reconciliation_ok : null,
    reconciliation_rows: num(r.reconciliation_rows), duration_ms: num(r.duration_ms),
    limitations: Array.isArray(r.limitations) ? r.limitations.map(String) : [],
  };
}

export function parseBacktestTrades(raw: unknown): BacktestTrade[] {
  const r = rec(raw);
  const rows = Array.isArray(r?.trades) ? (r!.trades as unknown[]) : [];
  return rows.map((row) => {
    const t = rec(row) ?? {};
    return {
      trade_id: String(t.trade_id ?? "UNKNOWN"), event_id: String(t.event_id ?? "UNKNOWN"),
      symbol: String(t.symbol ?? "UNKNOWN"), res: String(t.res ?? "UNKNOWN"),
      group: String(t.group ?? "UNKNOWN"), segment: String(t.segment ?? "UNKNOWN"),
      scale: num(t.scale) ?? 1, direction: String(t.direction ?? "UNKNOWN"),
      family: String(t.family ?? "UNKNOWN"), rules_version: String(t.rules_version ?? "UNKNOWN"),
      event_time_ms: num(t.event_time_ms) ?? 0, entry_ms: num(t.entry_ms) ?? 0,
      exit_ms: num(t.exit_ms) ?? 0, entry_px: num(t.entry_px) ?? 0, exit_px: num(t.exit_px) ?? 0,
      exit_reason: String(t.exit_reason ?? "UNKNOWN"),
      exit_executed: Boolean(t.exit_executed), open_at_end: Boolean(t.open_at_end),
      status: String(t.status ?? "UNKNOWN"),
      gross_pnl: num(t.gross_pnl), fees: num(t.fees), funding: num(t.funding),
      net_pnl: num(t.net_pnl), realized_net: num(t.realized_net),
      mfe_pct: num(t.mfe_pct), mae_pct: num(t.mae_pct), holding_ms: num(t.holding_ms),
      funding_accounting_complete: typeof t.funding_accounting_complete === "boolean" ? t.funding_accounting_complete : null,
      coverage: str(t.coverage),
    };
  });
}

// Grupos que son HIPOTESIS (variantes evaluadas) frente al PLACEBO (baseline).
// El baseline es referencia, NO estrategia; no se comparan como si fueran la
// misma cosa. La clasificacion es explicita, no inferida por rentabilidad.
export const HYPOTHESIS_GROUPS = new Set([
  "continuation", "bearish-continuation", "correction-exhaustion", "correction-reversal",
]);
export const PLACEBO_GROUPS = new Set(["baseline"]);

export type CellCounts = {
  n_trades: number; n_realized: number; n_open: number;
  total_net_realized: number; total_net_with_marks: number;
};

const zeroCounts = (): CellCounts => ({
  n_trades: 0, n_realized: 0, n_open: 0, total_net_realized: 0, total_net_with_marks: 0,
});

function accumulate(acc: CellCounts, c: BacktestCell): CellCounts {
  return {
    n_trades: acc.n_trades + (c.n_trades ?? 0),
    n_realized: acc.n_realized + (c.n_realized ?? 0),
    n_open: acc.n_open + (c.n_open ?? 0),
    total_net_realized: acc.total_net_realized + (c.total_net_realized ?? 0),
    total_net_with_marks: acc.total_net_with_marks + (c.total_net ?? 0),
  };
}

// Agregado por ESCALA de coste (1x/2x/3x son escenarios de coste, NO
// apalancamiento). Se separa lo REALIZADO de las MARCAS de abiertas: `total_net`
// incluye marcas y NO debe presentarse como beneficio realizado.
export function countsByScale(cells: BacktestCell[], scale: number): CellCounts {
  return cells.filter((c) => c.segment && c.scale !== null && Math.abs(c.scale - scale) < 1e-9)
    .reduce(accumulate, zeroCounts());
}

// Desglose 1x por HIPOTESIS y por PLACEBO (separados, no sumados como una
// unica "estrategia"). Las celdas se agregan como EVENTOS de una misma familia
// de reglas, no como una cartera: la exposicion conjunta no esta modelada.
export function hypothesisPlacebo1x(cells: BacktestCell[]):
  {hypothesis: CellCounts; placebo: CellCounts; combined: CellCounts} {
  const one = cells.filter((c) => c.segment && c.scale !== null && Math.abs(c.scale - 1) < 1e-9);
  const hypothesis = one.filter((c) => HYPOTHESIS_GROUPS.has(c.group)).reduce(accumulate, zeroCounts());
  const placebo = one.filter((c) => PLACEBO_GROUPS.has(c.group)).reduce(accumulate, zeroCounts());
  return {hypothesis, placebo, combined: accumulate(hypothesis, {
    n_trades: placebo.n_trades, n_realized: placebo.n_realized, n_open: placebo.n_open,
    total_net_realized: placebo.total_net_realized, total_net_with_marks: placebo.total_net_with_marks,
  } as unknown as BacktestCell)};
}

// Filas del summary: celdas con segmento (resultado) + auxiliares (agregados
// por escala sin segmento). 70 = 56 + 14, no 70 resultados independientes.
export function summaryRowBreakdown(cells: BacktestCell[]):
  {result_cells: number; auxiliary_rows: number; total: number} {
  const result_cells = cells.filter((c) => c.segment).length;
  return {result_cells, auxiliary_rows: cells.length - result_cells, total: cells.length};
}

export function utcOf(ms: number | null): string {  return ms !== null && Number.isSafeInteger(ms) && ms > 0
    ? new Date(ms).toISOString().replace(/\.000Z$/, "Z") : "UNKNOWN";
}
export function moneyOf(v: number | null): string {
  return v === null || !Number.isFinite(v) ? "UNKNOWN" : (v >= 0 ? "+" : "") + v.toFixed(2);
}
export function pctOf(v: number | null): string {
  return v === null || !Number.isFinite(v) ? "UNKNOWN" : (v > 0 ? "+" : "") + v.toFixed(2) + "%";
}
export function durationOf(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return "UNKNOWN";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60), h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m ${s % 60}s`;
}
