"use client";

// Paper Lab — motor de simulacion paper EN CALIENTE (ingeniería, fixtures).
// Simula entrada, gestion y salida de una posicion paper sobre velas de
// fixtures (sin Binance en vivo, sin ordenes reales, sin capital real).
// Todo el estado es local al cliente; la persistencia se delega a la capa de
// API/sesiones. No toca el monitor, no inicia/detiene nada, no ejecuta ordenes.

export type PaperDirection = "LONG" | "SHORT";

export type PaperSessionStatus =
  | "sin_iniciar"
  | "en_espera"
  | "abierta"
  | "cerrada"
  | "detenida";

export type PaperExitReason = "stop" | "horizon" | "manual";

export interface PaperCandle {
  open_time_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  close_time_ms: number;
}

export interface PaperCosts {
  fee_bps: number;
  spread_bps: number;
  entry_fees: number;
  exit_fees: number;
  entry_spread_slip: number;
  exit_spread_slip: number;
  funding: number;
  friction: number;
}

export interface PaperPosition {
  open: boolean;
  direction: PaperDirection | null;
  entry_px: number | null;
  entry_qty: number | null;
  entry_cost: number | null;
  entry_ms: number | null;
  stop_px: number | null;
  mark_px: number | null;
  mark_ms: number | null;
  unrealized_gross: number | null;
  unrealized_net: number | null;
  mfe_pct: number | null;
  mae_pct: number | null;
}

export interface PaperEvent {
  at_ms: number;
  label: string;
  kind: "entry" | "exit" | "stop" | "protection" | "mark" | "horizon";
  detail?: string;
}

export interface PaperTradeResult {
  symbol: string;
  direction: PaperDirection;
  entry_px: number;
  exit_px: number | null;
  entry_ms: number;
  exit_ms: number | null;
  exit_reason: PaperExitReason | null;
  exit_executed: boolean;
  qty: number;
  filled_cost: number;
  gross_pnl: number;
  fees: number;
  spread_slip: number;
  funding: number;
  friction: number;
  net_pnl: number;
  realized_net: number | null;
  open_at_end: boolean;
}

export interface PaperSessionConfig {
  symbol: string;
  interval: string;
  direction: PaperDirection;
  notional_usdt: number;
  entry_px: number;
  stop_px: number;
  stop_distance_pct: number;
  horizon_ms: number;
  fee_bps: number;
  spread_bps: number;
  slippage_bps: number;
}

export interface PaperSessionState {
  session_id: string;
  created_at_ms: number;
  updated_at_ms: number;
  status: PaperSessionStatus;
  config: PaperSessionConfig;
  candles: PaperCandle[];
  context_candles: PaperCandle[];
  cursor: number;
  position: PaperPosition;
  costs: PaperCosts;
  events: PaperEvent[];
  result: PaperTradeResult | null;
  clock_ms: number | null;
}

export type PaperStepResult =
  | {kind: "step"; state: PaperSessionState}
  | {kind: "exit_executed"; state: PaperSessionState; exit: PaperExitReason}
  | {kind: "finished"; state: PaperSessionState};

function nowMs(): number { return Date.now(); }

function randomHex(n: number): string {
  const buf = new Uint8Array(n);
  // Web Crypto (disponible en Node y navegador); getRandomValues es la API estandar.
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    crypto.getRandomValues(buf);
  } else {
    // Fallback determinista para entornos sin crypto (no debe ocurrir en vitest/jsdom ni Next).
    for (let i = 0; i < n; i += 1) buf[i] = Math.floor(Math.random() * 256);
  }
  let hex = "";
  for (let i = 0; i < n; i += 1) hex += buf[i]!.toString(16).padStart(2, "0");
  return hex;
}

function newSessionId(symbol: string, direction: PaperDirection): string {
  const ts = nowMs().toString();
  const rnd = randomHex(4);
  return `PL-${symbol}-${direction}-${ts}-${rnd}`.slice(0, 64);
}

function clampCursor(n: number, c: number): number {
  return Math.max(0, Math.min(n, c));
}

function entryFeesAmount(config: PaperSessionConfig): number {
  return config.notional_usdt * (config.fee_bps / 10000);
}

function entrySpreadSlipAmount(config: PaperSessionConfig): number {
  return config.notional_usdt * ((config.spread_bps + config.slippage_bps) / 10000);
}

function exitFeesAmount(notionalExitUsdt: number, config: PaperSessionConfig): number {
  return notionalExitUsdt * (config.fee_bps / 10000);
}

function exitSpreadSlipAmount(notionalExitUsdt: number, config: PaperSessionConfig): number {
  return notionalExitUsdt * ((config.spread_bps + config.slippage_bps) / 10000);
}

function grossPnl(direction: PaperDirection, entryPx: number, markPx: number, qty: number): number {
  if (direction === "LONG") return (markPx - entryPx) * qty;
  return (entryPx - markPx) * qty;
}

function excursionPct(direction: PaperDirection, entryPx: number, markPx: number): number {
  if (entryPx <= 0) return 0;
  if (direction === "LONG") return ((markPx - entryPx) / entryPx) * 100;
  return ((entryPx - markPx) / entryPx) * 100;
}

export function createPaperSession(
  config: PaperSessionConfig,
  candles: PaperCandle[],
  contextCandles: PaperCandle[] = [],
): PaperSessionState {
  const entryFees = entryFeesAmount(config);
  const entrySpreadSlip = entrySpreadSlipAmount(config);
  const now = nowMs();
  const session: PaperSessionState = {
    session_id: newSessionId(config.symbol, config.direction),
    created_at_ms: now,
    updated_at_ms: now,
    status: "en_espera",
    config,
    candles,
    context_candles: contextCandles,
    cursor: 0,
    position: {
      open: false,
      direction: null,
      entry_px: null,
      entry_qty: null,
      entry_cost: null,
      entry_ms: null,
      stop_px: config.stop_px,
      mark_px: null,
      mark_ms: null,
      unrealized_gross: null,
      unrealized_net: null,
      mfe_pct: null,
      mae_pct: null,
    },
    costs: {
      fee_bps: config.fee_bps,
      spread_bps: config.spread_bps,
      entry_fees: entryFees,
      exit_fees: 0,
      entry_spread_slip: entrySpreadSlip,
      exit_spread_slip: 0,
      funding: 0,
      friction: entryFees + entrySpreadSlip,
    },
    events: [],
    result: null,
    clock_ms: null,
  };
  return session;
}

function executeEntry(state: PaperSessionState): PaperSessionState {
  const {config, candles, cursor} = state;
  const candle = candles[cursor];
  if (!candle) return state;
  const entryPx = config.entry_px;
  const qty = config.notional_usdt / entryPx;
  const filledCost = entryPx * qty;
  const entryMs = candle.close_time_ms ?? candle.open_time_ms;

  const next: PaperSessionState = {
    ...state,
    updated_at_ms: nowMs(),
    status: "abierta",
    position: {
      ...state.position,
      open: true,
      direction: config.direction,
      entry_px: entryPx,
      entry_qty: qty,
      entry_cost: filledCost,
      entry_ms: entryMs,
      stop_px: config.stop_px,
      mark_px: entryPx,
      mark_ms: entryMs,
      unrealized_gross: 0,
      unrealized_net: 0 - state.costs.friction,
      mfe_pct: 0,
      mae_pct: 0,
    },
    costs: {
      ...state.costs,
      friction: state.costs.entry_fees + state.costs.entry_spread_slip,
    },
    events: [
      ...state.events,
      {
        at_ms: entryMs,
        label: `Entrada ${config.direction} @ ${entryPx.toFixed(2)}`,
        kind: "entry",
        detail: `qty=${qty.toFixed(8)} notional=${config.notional_usdt} stop=${config.stop_px}`,
      },
    ],
    result: null,
    clock_ms: entryMs,
  };
  return next;
}

export function stepForward(state: PaperSessionState): PaperStepResult {
  const {candles, cursor, position, status, config} = state;
  const n = candles.length;

  if (status === "cerrada" || status === "detenida") {
    return {kind: "finished", state};
  }

  // Ejecutar entrada automática si la sesión está "abierta" pero aún no hay
  // posición: la entrada se ejecuta en el paso actual (vela en cursor) y se
  // avanza el cursor para que el siguiente paso revele la siguiente vela.
  if (status === "abierta" && !position.open) {
    const entered = executeEntry(state);
    return {kind: "step", state: {...entered, cursor: Math.min(n, entered.cursor + 1)}};
  }

  const nextCursor = clampCursor(n, cursor + 1);
  const candle = candles[nextCursor - 1];
  const clockMs = candle ? candle.close_time_ms ?? candle.open_time_ms : null;

  let next: PaperSessionState = {
    ...state,
    cursor: nextCursor,
    updated_at_ms: nowMs(),
    clock_ms: clockMs,
  };

  if (next.position.open && next.position.entry_px != null && next.position.entry_qty != null) {
    const px = candle?.close ?? null;
    const markPx = px != null ? px : (next.position.mark_px ?? 0);
    const markMs = clockMs ?? (next.position.mark_ms ?? 0);
    const qty = next.position.entry_qty;
    const entryPx = next.position.entry_px!;

    const gross = grossPnl(config.direction, entryPx, markPx, qty);
    const mfePct = excursionPct(config.direction, entryPx, markPx);

    const prevMae = next.position.mae_pct ?? 0;
    const maePct = Math.min(prevMae, excursionPct(config.direction, entryPx, markPx));

    const notionalExit = markPx * qty;
    const exitFees = exitFeesAmount(notionalExit, config);
    const exitSpreadSlip = exitSpreadSlipAmount(notionalExit, config);
    const friction = next.costs.entry_fees + exitFees + next.costs.entry_spread_slip + exitSpreadSlip + next.costs.funding;
    const unrealizedNet = gross - friction;

    next = {
      ...next,
      position: {
        ...next.position,
        mark_px: markPx,
        mark_ms: markMs,
        unrealized_gross: gross,
        unrealized_net: unrealizedNet,
        mfe_pct: Math.max(next.position.mfe_pct ?? 0, mfePct),
        mae_pct: maePct,
      },
      costs: {
        ...next.costs,
        exit_fees: exitFees,
        exit_spread_slip: exitSpreadSlip,
        friction,
      },
      events: [
        ...next.events.filter((e) => e.kind !== "mark"),
        {
          at_ms: markMs,
          label: `Marca ${markPx.toFixed(2)}`,
          kind: "mark",
          detail: `P&L no realizado ${unrealizedNet.toFixed(2)}`,
        },
      ],
    };

    const stopPx = next.position.stop_px ?? 0;
    const hitStop = candle != null &&
      ((config.direction === "LONG" && candle.low <= stopPx) ||
       (config.direction === "SHORT" && candle.high >= stopPx));

    const horizonEnd = next.position.entry_ms != null
      ? next.position.entry_ms + config.horizon_ms
      : null;
    const hitHorizon = horizonEnd != null && clockMs != null && clockMs >= horizonEnd;

    if (hitStop) {
      const exitPx = stopPx;
      const exitMs = clockMs ?? markMs;
      const exitQty = qty;
      const exitGross = grossPnl(config.direction, entryPx, exitPx, exitQty);
      const exitFees2 = exitFeesAmount(exitPx * exitQty, config);
      const exitSlip2 = exitSpreadSlipAmount(exitPx * exitQty, config);
      const exitFriction = next.costs.entry_fees + exitFees2 + next.costs.entry_spread_slip + exitSlip2 + next.costs.funding;
      const exitNet = exitGross - exitFriction;

      const finishedState: PaperSessionState = {
        ...next,
        status: "cerrada",
        updated_at_ms: nowMs(),
        position: {
          ...next.position,
          open: false,
          mark_px: exitPx,
          mark_ms: exitMs,
          unrealized_gross: exitGross,
          unrealized_net: exitNet,
        },
        costs: {
          ...next.costs,
          exit_fees: exitFees2,
          exit_spread_slip: exitSlip2,
          friction: exitFriction,
        },
        events: [
          ...next.events,
          {
            at_ms: exitMs,
            label: `Stop alcanzado @ ${exitPx.toFixed(2)}`,
            kind: "exit",
            detail: `razon=stop P&L neto=${exitNet.toFixed(2)}`,
          },
        ],
        result: buildTradeResult(next, "stop", exitPx, exitMs, true),
        clock_ms: exitMs,
      };
      return {kind: "exit_executed", state: finishedState, exit: "stop"};
    }

    if (hitHorizon) {
      const exitPx = markPx;
      const exitMs = clockMs ?? markMs;
      const exitQty = qty;
      const exitGross = grossPnl(config.direction, entryPx, exitPx, exitQty);
      const exitFees2 = exitFeesAmount(exitPx * exitQty, config);
      const exitSlip2 = exitSpreadSlipAmount(exitPx * exitQty, config);
      const exitFriction = next.costs.entry_fees + exitFees2 + next.costs.entry_spread_slip + exitSlip2 + next.costs.funding;
      const exitNet = exitGross - exitFriction;

      const finishedState: PaperSessionState = {
        ...next,
        status: "cerrada",
        updated_at_ms: nowMs(),
        position: {
          ...next.position,
          open: false,
          mark_px: exitPx,
          mark_ms: exitMs,
          unrealized_gross: exitGross,
          unrealized_net: exitNet,
        },
        costs: {
          ...next.costs,
          exit_fees: exitFees2,
          exit_spread_slip: exitSlip2,
          friction: exitFriction,
        },
        events: [
          ...next.events,
          {
            at_ms: exitMs,
            label: `Horizonte alcanzado @ ${exitPx.toFixed(2)}`,
            kind: "exit",
            detail: `razon=horizon P&L neto=${exitNet.toFixed(2)}`,
          },
        ],
        result: buildTradeResult(next, "horizon", exitPx, exitMs, true),
        clock_ms: exitMs,
      };
      return {kind: "exit_executed", state: finishedState, exit: "horizon"};
    }
  }

  if (nextCursor >= n && next.position.open && !next.result) {
    const exitPx = next.position.mark_px ?? null;
    const exitMs = next.position.mark_ms ?? null;
    const qty = next.position.entry_qty ?? 0;
    const entryPx = next.position.entry_px ?? 0;
    const gross = exitPx != null ? grossPnl(config.direction, entryPx, exitPx, qty) : null;
    const friction = next.costs.friction;
    const net = gross != null ? gross - friction : null;

    const finishedState: PaperSessionState = {
      ...next,
      status: "cerrada",
      position: {
        ...next.position,
        open: false,
        unrealized_gross: gross ?? null,
        unrealized_net: net ?? null,
      },
      result: {
        symbol: config.symbol,
        direction: config.direction,
        entry_px: entryPx,
        exit_px: exitPx ?? null,
        entry_ms: next.position.entry_ms ?? 0,
        exit_ms: exitMs ?? null,
        exit_reason: null,
        exit_executed: false,
        qty,
        filled_cost: next.position.entry_cost ?? 0,
        gross_pnl: gross ?? 0,
        fees: next.costs.entry_fees,
        spread_slip: next.costs.entry_spread_slip,
        funding: next.costs.funding,
        friction,
        net_pnl: net ?? 0,
        realized_net: null,
        open_at_end: true,
      },
    };
    return {kind: "finished", state: finishedState};
  }

  return {kind: "step", state: next};
}

export function manualExit(state: PaperSessionState): PaperStepResult {
  if (state.status !== "abierta" || !state.position.open) {
    return {kind: "finished", state};
  }
  const {config, position, candles, cursor, clock_ms} = state;
  const candle = candles[cursor - 1] ?? null;
  const exitPx = candle?.close ?? (position.mark_px ?? null);
  const exitMs = clock_ms ?? (candle?.close_time_ms ?? null);
  const entryPx = position.entry_px ?? 0;
  const qty = position.entry_qty ?? 0;

  if (exitPx == null || exitMs == null) {
    return {kind: "finished", state};
  }

  const exitGross = grossPnl(config.direction, entryPx, exitPx, qty);
  const exitFees = exitFeesAmount(exitPx * qty, config);
  const exitSlip = exitSpreadSlipAmount(exitPx * qty, config);
  const exitFriction = state.costs.entry_fees + exitFees + state.costs.entry_spread_slip + exitSlip + state.costs.funding;
  const exitNet = exitGross - exitFriction;

  const next: PaperSessionState = {
    ...state,
    status: "cerrada",
    updated_at_ms: nowMs(),
    position: {
      ...position,
      open: false,
      mark_px: exitPx,
      mark_ms: exitMs,
      unrealized_gross: exitGross,
      unrealized_net: exitNet,
    },
    costs: {
      ...state.costs,
      exit_fees: exitFees,
      exit_spread_slip: exitSlip,
      friction: exitFriction,
    },
    events: [
      ...state.events.filter((e) => e.kind !== "mark"),
      {
        at_ms: exitMs,
        label: `Cierre manual @ ${exitPx.toFixed(2)}`,
        kind: "exit",
        detail: `razon=manual P&L neto=${exitNet.toFixed(2)}`,
      },
    ],
    clock_ms: exitMs,
  };
  next.result = buildTradeResult(next, "manual", exitPx, exitMs, true);
  return {kind: "exit_executed", state: next, exit: "manual"};
}

function buildTradeResult(
  state: PaperSessionState,
  reason: PaperExitReason | null,
  exitPx: number,
  exitMs: number,
  executed: boolean,
): PaperTradeResult {
  const {config, position, costs} = state;
  const entryPx = position.entry_px ?? 0;
  const qty = position.entry_qty ?? 0;
  const gross = grossPnl(config.direction, entryPx, exitPx, qty);
  const net = gross - costs.friction;
  return {
    symbol: config.symbol,
    direction: config.direction,
    entry_px: entryPx,
    exit_px: exitPx,
    entry_ms: position.entry_ms ?? 0,
    exit_ms: exitMs,
    exit_reason: reason,
    exit_executed: executed,
    qty,
    filled_cost: position.entry_cost ?? 0,
    gross_pnl: gross,
    fees: costs.entry_fees + costs.exit_fees,
    spread_slip: costs.entry_spread_slip + costs.exit_spread_slip,
    funding: costs.funding,
    friction: costs.friction,
    net_pnl: net,
    realized_net: executed ? net : null,
    open_at_end: !executed,
  };
}

export function restartSession(state: PaperSessionState): PaperSessionState {
  const {config, candles, context_candles} = state;
  const fresh = createPaperSession(config, candles, context_candles);
  return {
    ...fresh,
    created_at_ms: state.created_at_ms,
    updated_at_ms: nowMs(),
  };
}

export function stopSession(state: PaperSessionState): PaperSessionState {
  return {...state, status: "detenida", updated_at_ms: nowMs()};
}

export function selectOperation(
  config: PaperSessionConfig,
  candles: PaperCandle[],
  contextCandles: PaperCandle[] = [],
): PaperSessionState {
  return createPaperSession(config, candles, contextCandles);
}

export function formatMoneyPL(v: number | null): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(2);
}
export function formatPricePL(v: number | null): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: Math.abs(v) < 1 ? 8 : 2,
  }).format(v);
}
export function formatPctPL(v: number | null): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
}
export function fmtUtcPL(ms: number | null): string {
  if (ms == null) return "—";
  return new Date(ms).toISOString().replace(/\.000Z$/, "Z");
}

export interface PaperSessionView {
  status: PaperSessionStatus;
  cursor: number;
  n: number;
  progress: number;
  clockMs: number | null;
  clockUtc: string | null;
  candle: PaperCandle | null;
  position: PaperPosition;
  costs: PaperCosts;
  events: PaperEvent[];
  result: PaperTradeResult | null;
  canEnter: boolean;
  canStep: boolean;
  canExit: boolean;
  canRestart: boolean;
  canStop: boolean;
}

export function sessionView(state: PaperSessionState): PaperSessionView {
  const {config, candles, cursor, position, costs, events, result, clock_ms, status} = state;
  const n = candles.length;
  const open = position.open === true;
  const finished = status === "cerrada" || status === "detenida";
  return {
    status,
    cursor,
    n,
    progress: n === 0 ? 1 : cursor / n,
    clockMs: clock_ms,
    clockUtc: fmtUtcPL(clock_ms),
    candle: candles[Math.max(0, cursor - 1)] ?? null,
    position,
    costs,
    events,
    result,
    canEnter: status === "en_espera" && !open,
    canStep: status === "abierta" && cursor < n && !finished,
    canExit: open && !finished,
    canRestart: true,
    canStop: status === "abierta" || status === "en_espera",
  };
}
