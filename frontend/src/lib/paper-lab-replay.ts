"use client";

// Paper Lab — replay historico interactivo.
// Logica pura de reproduccion sobre el artefacto versionado PAPER-LAB-REPLAY-V1.
// No toca el monitor, no inicia/detiene nada, no ejecuta ordenes.

export type ReplayStatus = "idle" | "playing" | "paused" | "finished";

export interface ReplayCandle {
  open_time_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  close_time_ms: number | null;
}

export interface ReplayEvent {
  at_ms: number;
  label: string;
  kind: "signal" | "available" | "entry" | "exit";
}

export interface ReplayPosition {
  open: boolean;
  entry_px: number | null;
  qty: number | null;
  mark_px: number | null;
  mark_ms: number | null;
}

export interface ReplayUnrealized {
  gross: number;
  fees_est: number;
  net_est: number;
  mark_px: number;
}

export interface ReplayExit {
  reason: string;
  px: number;
  ms: number;
  executed: boolean;
}

export interface ReplayStep {
  step: number;
  kind: "candle" | "event";
  candle: ReplayCandle | null;
  known_at_ms: number | null;
  opens_at_ms: number | null;
  closed_at_ms: number | null;
  events: ReplayEvent[];
  position_after: ReplayPosition;
  mfe_pct: number | null;
  mae_pct: number | null;
  unrealized: ReplayUnrealized | null;
  exit: ReplayExit | null;
  final_candle?: boolean;
}

export interface ReplayTrade {
  symbol: string;
  direction: "LONG" | "SHORT";
  family: string;
  rules_version: string;
  event_time_ms: number;
  segment: string;
  group: string;
  entry_ms: number;
  exit_ms: number;
  exit_reason: string;
  entry_px: number;
  exit_px: number;
  filled_qty: number;
  filled_cost: number;
  gross_pnl: number;
  fees: number;
  entry_fees: number;
  exit_fees: number;
  funding: number;
  friction: number;
  net_pnl: number;
  realized_net: number | null;
  exit_executed: boolean;
  open_at_end: boolean;
  funding_accounting_complete: boolean | null;
}

export interface ReplayLevels {
  notional_usdt: number;
  qty_base: number;
  entry_px: number;
  stop_px: number;
  stop_distance_pct: number;
  horizon_ms: number;
  horizon_end_ms: number;
  fee_bps: number;
  spread_bps: number;
  slippage_bps: number;
  cost_scale: number;
}

export interface ReplayCosts {
  entry_fees: number;
  exit_fees: number;
  entry_spread_slip: number;
  exit_spread_slip: number;
  total_fees: number;
  total_spread_slip: number;
  funding: number;
  friction: number;
}

export interface ReplayResult {
  gross_pnl: number;
  net_pnl: number;
  realized_net: number | null;
  exit_reason: string;
  exit_executed: boolean;
  reconciled_to_engine: Record<string, unknown>;
  tolerance: {relative: number; absolute_usdt: number};
  note: string;
}

export interface ReplayProvenance {
  symbol: string;
  interval: string;
  source_db: string;
  db_sha256: string | null;
  events_file: string;
  candles_file: string;
  manifest_file: string;
  selection_file: string;
  funding_calendar: string;
  engine: string;
  engine_version: string;
  source_hashes: Record<string, string>;
  note: string;
}

export interface ReplaySelection {
  sort: string[];
  eligible_families: string[];
  excluded_family_reason: string;
  exclusions_before_choice: Record<string, number>;
  population_trades_1x: number;
}

export interface ReplayArtifact {
  schema_version: number;
  artifact_version: string;
  label: string;
  engine_version: string;
  eligibility_rule: string;
  replay_id: string;
  chosen_at_utc: string | null;
  selection: ReplaySelection;
  trade: ReplayTrade;
  event: {
    event_id: string;
    event_time_ms: number;
    direction: string;
    family: string;
    rules_version: string;
    reference_price: number;
    source: string;
    available_at_ms: number | null;
    detection_id: string;
  };
  levels: ReplayLevels;
  costs: ReplayCosts;
  result: ReplayResult;
  window: {
    symbol: string;
    interval: string;
    n_candles: number;
    n_context_candles: number;
    context_candles: ReplayCandle[];
    candles: ReplayCandle[];
    steps: ReplayStep[];
  };
  provenance: ReplayProvenance;
  limitations: string[];
}

const EXPECTED_VERSION = "PAPER-LAB-REPLAY-V1";
const EXPECTED_SCHEMA = 1;

function req(v: unknown, what: string): asserts v is NonNullable<typeof v> {
  if (v === null || v === undefined) throw new Error(`PAPER_LAB_REPLAY_UNAVAILABLE: ${what}`);
}

function finite(v: unknown, what: string): number {
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`PAPER_LAB_REPLAY_UNAVAILABLE: ${what}`);
  return n;
}

export function parsePaperLabReplay(raw: unknown): ReplayArtifact {
  const r = raw as Record<string, unknown> | null;
  if (!r || typeof r !== "object") throw new Error("PAPER_LAB_REPLAY_UNAVAILABLE");
  if (r.schema_version !== EXPECTED_SCHEMA) throw new Error("UNSUPPORTED_PAPER_LAB_REPLAY_SCHEMA");
  if (r.artifact_version !== EXPECTED_VERSION)
    throw new Error("UNKNOWN_PAPER_LAB_REPLAY_ARTIFACT");
  const trade = r.trade as Record<string, unknown>;
  const levels = r.levels as Record<string, unknown>;
  const costs = r.costs as Record<string, unknown>;
  const result = r.result as Record<string, unknown>;
  const prov = r.provenance as Record<string, unknown>;
  const selection = r.selection as Record<string, unknown>;
  const win = r.window as Record<string, unknown>;
  req(trade, "trade"); req(levels, "levels"); req(costs, "costs"); req(result, "result");
  req(prov, "provenance"); req(selection, "selection"); req(win, "window");
  const candles = Array.isArray(win.candles) ? win.candles : [];
  const steps = Array.isArray(win.steps) ? win.steps : [];
  for (const c of candles) {
    req((c as Record<string, unknown>).open_time_ms, "candle.open_time_ms");
    req((c as Record<string, unknown>).open, "candle.open");
    req((c as Record<string, unknown>).high, "candle.high");
    req((c as Record<string, unknown>).low, "candle.low");
    req((c as Record<string, unknown>).close, "candle.close");
  }
  for (const s of steps) {
    const step = s as Record<string, unknown>;
    req(step.known_at_ms, "step.known_at_ms");
    const kind = String(step.kind ?? "candle");
    if (kind !== "candle" && kind !== "event") throw new Error("UNKNOWN_PAPER_LAB_REPLAY_STEP_KIND");
    // Un paso de vela exige vela; un paso de evento la prohíbe. Nunca se
    // rellena una vela donde no la hay.
    if (kind === "candle") {
      const c = step.candle as Record<string, unknown> | null;
      req(c, "step.candle");
      req(c!.open_time_ms, "step.candle.open_time_ms");
      req(c!.close_time_ms, "step.candle.close_time_ms");
    } else if (step.candle != null) {
      throw new Error("PAPER_LAB_REPLAY_UNAVAILABLE: event step con vela");
    }
    // Invariante de causalidad: ningún evento puede superar el reloj del paso.
    const events = Array.isArray(step.events) ? (step.events as Record<string, unknown>[]) : [];
    for (const e of events) {
      const at = Number(e.at_ms);
      if (!Number.isFinite(at) || at > Number(step.known_at_ms)) {
        throw new Error("PAPER_LAB_REPLAY_UNAVAILABLE: evento anticipado respecto a su instante");
      }
    }
  }
  return {
    schema_version: Number(r.schema_version),
    artifact_version: String(r.artifact_version),
    label: String(r.label ?? "UNKNOWN"),
    engine_version: String(r.engine_version ?? "UNKNOWN"),
    eligibility_rule: String(r.eligibility_rule ?? ""),
    replay_id: String(r.replay_id ?? "UNKNOWN"),
    chosen_at_utc: typeof r.chosen_at_utc === "string" ? r.chosen_at_utc : null,
    selection: {
      sort: Array.isArray(selection.sort) ? selection.sort.map(String) : [],
      eligible_families: Array.isArray(selection.eligible_families) ? selection.eligible_families.map(String) : [],
      excluded_family_reason: String(selection.excluded_family_reason ?? "UNKNOWN"),
      exclusions_before_choice: (selection.exclusions_before_choice as Record<string, number>) ?? {},
      population_trades_1x: finite(selection.population_trades_1x, "selection.population_trades_1x"),
    },
    trade: {
      symbol: String(trade.symbol ?? "UNKNOWN"),
      direction: String(trade.direction ?? "UNKNOWN") as "LONG" | "SHORT",
      family: String(trade.family ?? "UNKNOWN"),
      rules_version: String(trade.rules_version ?? "UNKNOWN"),
      event_time_ms: finite(trade.event_time_ms, "trade.event_time_ms"),
      segment: String(trade.segment ?? "UNKNOWN"),
      group: String(trade.group ?? "UNKNOWN"),
      entry_ms: finite(trade.entry_ms, "trade.entry_ms"),
      exit_ms: finite(trade.exit_ms, "trade.exit_ms"),
      exit_reason: String(trade.exit_reason ?? "UNKNOWN"),
      entry_px: finite(trade.entry_px, "trade.entry_px"),
      exit_px: finite(trade.exit_px, "trade.exit_px"),
      filled_qty: finite(trade.filled_qty, "trade.filled_qty"),
      filled_cost: finite(trade.filled_cost, "trade.filled_cost"),
      gross_pnl: finite(trade.gross_pnl, "trade.gross_pnl"),
      fees: finite(trade.fees, "trade.fees"),
      entry_fees: finite(trade.entry_fees, "trade.entry_fees"),
      exit_fees: finite(trade.exit_fees, "trade.exit_fees"),
      funding: finite(trade.funding, "trade.funding"),
      friction: finite(trade.friction, "trade.friction"),
      net_pnl: finite(trade.net_pnl, "trade.net_pnl"),
      realized_net: trade.realized_net == null ? null : finite(trade.realized_net, "trade.realized_net"),
      exit_executed: Boolean(trade.exit_executed),
      open_at_end: Boolean(trade.open_at_end),
      funding_accounting_complete:
        trade.funding_accounting_complete == null
          ? null
          : Boolean(trade.funding_accounting_complete),
    },
    event: {
      event_id: String((r.event as Record<string, unknown>)?.event_id ?? "UNKNOWN"),
      event_time_ms: Number((r.event as Record<string, unknown>)?.event_time_ms),
      direction: String((r.event as Record<string, unknown>)?.direction ?? "UNKNOWN"),
      family: String((r.event as Record<string, unknown>)?.family ?? "UNKNOWN"),
      rules_version: String((r.event as Record<string, unknown>)?.rules_version ?? "UNKNOWN"),
      reference_price: Number((r.event as Record<string, unknown>)?.reference_price),
      source: String((r.event as Record<string, unknown>)?.source ?? "UNKNOWN"),
      available_at_ms:
        (r.event as Record<string, unknown>)?.available_at_ms == null
          ? null
          : Number((r.event as Record<string, unknown>)?.available_at_ms),
      detection_id: String((r.event as Record<string, unknown>)?.detection_id ?? "UNKNOWN"),
    },
    levels: {
      notional_usdt: Number(levels.notional_usdt),
      qty_base: Number(levels.qty_base),
      entry_px: Number(levels.entry_px),
      stop_px: Number(levels.stop_px),
      stop_distance_pct: Number(levels.stop_distance_pct),
      horizon_ms: Number(levels.horizon_ms),
      horizon_end_ms: Number(levels.horizon_end_ms),
      fee_bps: Number(levels.fee_bps),
      spread_bps: Number(levels.spread_bps),
      slippage_bps: Number(levels.slippage_bps),
      cost_scale: Number(levels.cost_scale),
    },
    costs: {
      entry_fees: Number(costs.entry_fees),
      exit_fees: Number(costs.exit_fees),
      entry_spread_slip: Number(costs.entry_spread_slip),
      exit_spread_slip: Number(costs.exit_spread_slip),
      total_fees: Number(costs.total_fees),
      total_spread_slip: Number(costs.total_spread_slip),
      funding: Number(costs.funding),
      friction: Number(costs.friction),
    },
    result: {
      gross_pnl: Number(result.gross_pnl),
      net_pnl: Number(result.net_pnl),
      realized_net: result.realized_net == null ? null : Number(result.realized_net),
      exit_reason: String(result.exit_reason ?? "UNKNOWN"),
      exit_executed: Boolean(result.exit_executed),
      reconciled_to_engine: (result.reconciled_to_engine as Record<string, unknown>) ?? {},
      tolerance: {
        relative: finite((result.tolerance as Record<string, unknown>)?.relative, "result.tolerance.relative"),
        absolute_usdt: finite((result.tolerance as Record<string, unknown>)?.absolute_usdt, "result.tolerance.absolute_usdt"),
      },
      note: String(result.note ?? ""),
    },
    window: {
      symbol: String(win.symbol ?? "UNKNOWN"),
      interval: String(win.interval ?? "UNKNOWN"),
      n_candles: Number(win.n_candles ?? candles.length),
      n_context_candles: Number(win.n_context_candles ?? 0),
      context_candles: (Array.isArray(win.context_candles) ? win.context_candles : []).map((c: ReplayCandle) => c),
      candles: candles.map((c: ReplayCandle) => c),
      steps: steps as ReplayStep[],
    },
    provenance: {
      symbol: String(prov.symbol ?? "UNKNOWN"),
      interval: String(prov.interval ?? "UNKNOWN"),
      source_db: String(prov.source_db ?? "UNKNOWN"),
      db_sha256: typeof prov.db_sha256 === "string" ? prov.db_sha256 : null,
      events_file: String(prov.events_file ?? "UNKNOWN"),
      candles_file: String(prov.candles_file ?? "UNKNOWN"),
      manifest_file: String(prov.manifest_file ?? "UNKNOWN"),
      selection_file: String(prov.selection_file ?? "UNKNOWN"),
      funding_calendar: String(prov.funding_calendar ?? "UNKNOWN"),
      engine: String(prov.engine ?? "UNKNOWN"),
      engine_version: String(prov.engine_version ?? prov.engine ?? "UNKNOWN"),
      source_hashes: (prov.source_hashes as Record<string, string>) ?? {},
      note: String(prov.note ?? ""),
    },
    limitations: Array.isArray(r.limitations) ? (r.limitations as string[]).map(String) : [],
  };
}

export function replayClockUtc(ms: number | null): string | null {
  if (ms === null || ms === undefined) return null;
  return new Date(ms).toISOString().replace(/\.000Z$/, "Z");
}

export function formatMoney(v: number | null): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(2);
}
export function formatPct(v: number | null): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
}
export function formatPrice(v: number | null): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: Math.abs(v) < 1 ? 8 : 2,
  }).format(v);
}

export interface ReplayView {
  status: ReplayStatus;
  cursor: number;
  n: number;
  finished: boolean;
  progress: number;
  step: ReplayStep | null;
  clockMs: number | null;
  clockUtc: string | null;
  candles: ReplayCandle[];
  events: ReplayEvent[];
  position: ReplayPosition | null;
  positionState: ReplayStepView;
  unrealized: ReplayUnrealized | null;
  exit: ReplayExit | null;
  canPlay: boolean;
  canPause: boolean;
  canRestart: boolean;
  canStepForward: boolean;
}

export class ReplayPlayer {
  readonly steps: ReplayStep[];
  readonly n: number;
  cursor: number;
  status: ReplayStatus;
  speed: number; // steps per second (>0)
  constructor(
    steps: ReplayStep[],
    { cursor = 0, status = "idle", speed = 1 }: { cursor?: number; status?: ReplayStatus; speed?: number } = {},
  ) {
    this.steps = steps;
    this.n = steps.length;
    this.cursor = Math.max(0, Math.min(this.n, cursor));
    this.status = status;
    this.speed = speed > 0 ? speed : 1;
    if (this.cursor === this.n) this.status = "finished";
  }
  play(): void {
    if (this.status === "finished") return;
    this.status = "playing";
  }
  pause(): void {
    this.status = "paused";
  }
  toggle(): void {
    if (this.status === "playing") this.pause();
    else this.play();
  }
  restart(): void {
    this.cursor = 0;
    this.status = "idle";
  }
  setSpeed(s: number): void {
    this.speed = s > 0 ? s : 1;
  }
  seek(c: number): void {
    this.cursor = Math.max(0, Math.min(this.n, c));
    if (this.cursor === this.n) this.status = "finished";
  }
  stepForward(): void {
    if (this.status === "finished") return;
    if (this.cursor < this.n) {
      this.cursor++;
      if (this.cursor === this.n) this.status = "finished";
    }
  }
  stepBackward(): void {
    if (this.cursor > 0) {
      this.cursor--;
      this.status = this.cursor === this.n ? "finished" : "paused";
    }
  }
  view(): ReplayView {
    const revealed = this.steps.slice(0, this.cursor);
    const step = revealed[revealed.length - 1] ?? null;
    const finished = this.cursor === this.n;
    const events = revealed.flatMap((s) => s.events);
    const position = step?.position_after ?? null;
    const exit = step?.exit ?? null;
    return {
      status: finished ? "finished" : this.status,
      cursor: this.cursor,
      n: this.n,
      finished,
      progress: this.n === 0 ? 1 : this.cursor / this.n,
      step,
      clockMs: step?.known_at_ms ?? null,
      clockUtc: step ? replayClockUtc(step.known_at_ms) : null,
      // Solo los pasos de VELA aportan velas; los pasos de EVENTO no.
      candles: revealed.filter((s) => s.kind === "candle" && s.candle).map((s) => s.candle as ReplayCandle),
      events,
      position,
      positionState: replayPositionState(events, position, exit, finished),
      unrealized: step?.unrealized ?? null,
      exit,
      canPlay: !finished,
      canPause: this.status === "playing",
      canRestart: true,
      canStepForward: this.cursor < this.n,
    };
  }
}

export function msPerStep(speed: number): number {
  return Math.max(50, Math.round(1200 / speed));
}

export function reconciledNet(result: ReplayResult, trade: ReplayTrade): boolean {
  const a = result.net_pnl;
  const b = trade.net_pnl;
  return Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));
}

// Estado del replay (separado del estado del monitor). Cuatro estados:
//   SIN POSICION  — aún no se ha revelado la señal ni la entrada.
//   EN ESPERA     — la operación está seleccionada pero la entrada no se ejecutó.
//   ABIERTA       — la entrada se ejecutó y el cierre aún no.
//   CERRADA       — el cierre se ejecutó (resultado realizado).
export type ReplayPositionState = "SIN_POSICION" | "EN_ESPERA" | "ABIERTA" | "CERRADA";

export interface ReplayStepView {
  state: ReplayPositionState;
  label: string;
  entered: boolean;
  closed: boolean;
  positionOpen: boolean;
}

export function replayPositionState(
  events: ReplayEvent[],
  position: ReplayPosition | null,
  exit: ReplayExit | null,
  finished: boolean,
): ReplayStepView {
  const entered = events.some((e) => e.kind === "entry");
  const exitedEvent = events.some((e) => e.kind === "exit");
  const closed = exitedEvent || (!!exit && exit.executed) || (finished && entered);
  const positionOpen = position?.open === true || (entered && !closed);
  if (closed) {
    return {state: "CERRADA", label: "CERRADA", entered, closed: true, positionOpen: false};
  }
  if (positionOpen) {
    return {state: "ABIERTA", label: "ABIERTA", entered, closed: false, positionOpen: true};
  }
  // Antes de la entrada: distinguir "sin señal aún" de "seleccionada, en espera".
  const hasSignal = events.some((e) => e.kind === "signal");
  if (hasSignal) {
    return {state: "EN_ESPERA", label: "SIN POSICIÓN / EN ESPERA", entered, closed: false, positionOpen: false};
  }
  return {state: "SIN_POSICION", label: "SIN POSICIÓN", entered, closed: false, positionOpen: false};
}

// La dirección describe el sesgo de la operación; la ACCIÓN de cierre se
// muestra aparte (cerrar un LONG es vender; cerrar un SHORT es comprar),
// nunca mezclada con el nombre del estado.
export function directionLabel(direction: string): string {
  if (direction === "LONG") return "LONG";
  if (direction === "SHORT") return "SHORT";
  return "—";
}

export function closeActionLabel(direction: string): string {
  if (direction === "LONG") return "cierre = venta";
  if (direction === "SHORT") return "cierre = compra";
  return "cierre = —";
}
