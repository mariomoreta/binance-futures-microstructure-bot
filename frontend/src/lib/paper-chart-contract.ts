// Paper Lab — contrato presentacional del gráfico (paper-chart/v1).
//
// El backend Python (paper_lab_engine.session_to_public_dict) es la única
// autoridad de velas conocidas en T, posición, stop efectivo, eventos y
// resultado. Este módulo NO calcula decisiones, fills, stops ni P&L: solo
// adapta la respuesta pública a un modelo de presentación con:
//   - identidad y tiempos explícitos,
//   - velas cerradas vs. velas solo-open (campos desconocidos en T),
//   - operación separada en señal / entrada pendiente / fill / salida,
//   - niveles y marcadores derivados de campos del backend,
//   - límites de cobertura y capacidad de avance informados por el backend.
//
// Unidades: el backend publica milisegundos Unix UTC; Lightweight Charts usa
// segundos Unix UTC. La conversión se hace explícitamente (msToChartSecond) y
// el milisegundo exacto se conserva en este modelo para detalle/evidencia.
//
// Datos implementados hoy: Paper Lab sobre fixtures. Venue, volumen,
// indicadores, objetivo y feed vivo NO están implementados: se representan
// como null/UNKNOWN, nunca como ceros o valores inventados.

import type {
  PaperCandle,
  PaperEvent,
  PaperSessionState,
  PaperSessionStatus,
} from "./paper-lab-live";

export const PAPER_CHART_CONTRACT_VERSION = "paper-chart/v1" as const;
export type PaperChartContractVersion = typeof PAPER_CHART_CONTRACT_VERSION;

export interface ChartIdentity {
  source: "fixture";
  // Fixtures sintéticas: no hay venue Binance que declarar.
  venue: null;
  venue_status: "UNKNOWN";
  market_type: "simulated_futures";
  symbol: string;
  interval: string;
  session_id: string;
  fixture_id: string | null;
}

export interface ChartTimes {
  unit: "ms";
  epoch: "unix_utc";
  created_at_ms: number;
  updated_at_ms: number;
  clock_ms: number | null;
}

export interface ClosedChartCandle {
  kind: "closed";
  open_time_ms: number;
  close_time_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  available_at_ms: number | null;
  received_at_ms: number | null;
}

export interface OpenOnlyChartCandle {
  kind: "open";
  open_time_ms: number;
  close_time_ms: null;
  open: number;
  high: null;
  low: null;
  close: null;
  available_at_ms: number | null;
  received_at_ms: number | null;
}

export type ChartCandle = ClosedChartCandle | OpenOnlyChartCandle;

export interface ChartSignal {
  at_ms: number;
  price: number | null;
  event_id: string | null;
}

export interface ChartPendingEntry {
  // Precio de referencia de la señal; NO es un fill ejecutado.
  reference_px: number;
}

export interface ChartFill {
  px: number;
  ms: number;
  event_id: string | null;
}

export interface ChartExit {
  px: number;
  ms: number;
  reason: string | null;
  event_id: string | null;
}

export interface ChartOperation {
  decision: string | null;
  signal: ChartSignal | null;
  pending_entry: ChartPendingEntry | null;
  entry: ChartFill | null;
  stop_effective_px: number | null;
  target_px: null;
  target_status: "UNKNOWN";
  exit: ChartExit | null;
  realized_net: number | null;
  realized_status: "known" | "UNKNOWN" | "not_realized";
  unrealized_net: number | null;
  open_at_end: boolean;
  mark_px: number | null;
  mark_ms: number | null;
}

export interface ChartMarker {
  id: string;
  kind: "signal" | "entry" | "exit";
  time_ms: number;
  time_s: number;
  price: number | null;
  label: string;
  event_id: string | null;
}

export interface ChartCapabilities {
  status: PaperSessionStatus;
  can_step: boolean;
  cursor: number;
  context_count: number;
  closed_count: number;
  open_only_count: number;
  limits: string;
}

export interface PaperChartModel {
  contract_version: PaperChartContractVersion;
  identity: ChartIdentity;
  times: ChartTimes;
  candles: {
    context: ClosedChartCandle[];
    closed: ClosedChartCandle[];
    open_only: OpenOnlyChartCandle[];
  };
  indicators: never[];
  volume: null;
  volume_status: "UNKNOWN";
  operation: ChartOperation;
  markers: ChartMarker[];
  capabilities: ChartCapabilities;
}

export function msToChartSecond(ms: number): number {
  if (!Number.isFinite(ms)) {
    throw new Error(`INVALID_TIME_MS: ${String(ms)}`);
  }
  return Math.floor(ms / 1000);
}

function finiteOrNull(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function recordOrNull(v: unknown): Record<string, unknown> | null {
  return v != null && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
}

function toChartCandle(c: PaperCandle): ChartCandle | null {
  const open = finiteOrNull(c?.open);
  const openTime = finiteOrNull(c?.open_time_ms);
  if (open == null || openTime == null) return null;
  const available = finiteOrNull(c.available_at);
  const received = finiteOrNull(c.received_at);
  const high = finiteOrNull(c.high);
  const low = finiteOrNull(c.low);
  const close = finiteOrNull(c.close);
  const closeTime = finiteOrNull(c.close_time_ms);
  if (high == null || low == null || close == null || closeTime == null) {
    return {
      kind: "open",
      open_time_ms: openTime,
      open,
      high: null,
      low: null,
      close: null,
      close_time_ms: null,
      available_at_ms: available,
      received_at_ms: received,
    };
  }
  return {
    kind: "closed",
    open_time_ms: openTime,
    close_time_ms: closeTime,
    open,
    high,
    low,
    close,
    available_at_ms: available,
    received_at_ms: received,
  };
}

/** Ordena por open_time_ms y elimina duplicados exactos de tiempo. */
function dedupeSorted<T extends {open_time_ms: number}>(items: T[]): T[] {
  const byTime = new Map<number, T>();
  for (const item of items) byTime.set(item.open_time_ms, item);
  return [...byTime.values()].sort((a, b) => a.open_time_ms - b.open_time_ms);
}

function findEvent(
  events: PaperEvent[],
  kind: PaperEvent["kind"],
  atMs: number,
): PaperEvent | null {
  return events.find((e) => e.kind === kind && e.at_ms === atMs) ?? null;
}

function decisionTime(evidence: Record<string, unknown> | null): number | null {
  return finiteOrNull(evidence?.decision_at_ms) ?? finiteOrNull(evidence?.at_ms);
}

export function buildPaperChartModel(
  state: PaperSessionState,
  opts: {fixtureId?: string | null} = {},
): PaperChartModel {
  const config = state.config;
  const position = state.position;
  const result = state.result;
  const evidence = recordOrNull(config.decision_evidence);
  const events = Array.isArray(state.events) ? state.events : [];

  const context: ClosedChartCandle[] = [];
  for (const c of state.context_candles ?? []) {
    const mapped = toChartCandle(c);
    // El contexto previo debe estar cerrado; si no, no se presenta.
    if (mapped?.kind === "closed") context.push(mapped);
  }

  const closed: ClosedChartCandle[] = [];
  const openOnly: OpenOnlyChartCandle[] = [];
  for (const c of state.candles ?? []) {
    const mapped = toChartCandle(c);
    if (!mapped) continue;
    if (mapped.kind === "closed") closed.push(mapped);
    else openOnly.push(mapped);
  }

  // Defensa de contrato: nada con open_time_ms > reloj de simulación puede
  // presentarse como conocido, aunque el llamador pase la lista completa.
  // Sin reloj no se asume conocimiento (UNKNOWN), no se muestran velas.
  const clock = finiteOrNull(state.clock_ms);
  const known = (openTime: number) => clock != null && openTime <= clock;
  const contextKnown = context.filter((c) => known(c.open_time_ms));
  const closedKnown = closed.filter((c) => known(c.open_time_ms));
  const openKnown = openOnly.filter((c) => known(c.open_time_ms));

  const signalAt = decisionTime(evidence);
  const trigger = finiteOrNull(evidence?.trigger_px);
  const hasDecisionEntry = config.decision === "ENTRADA_SIMULADA";
  const pending = state.status === "en_espera" && hasDecisionEntry
    && position.open !== true;

  const entryMs = finiteOrNull(position.entry_ms) ?? finiteOrNull(result?.entry_ms);
  const entryPx = finiteOrNull(position.entry_px) ?? finiteOrNull(result?.entry_px);
  const hasFill = entryMs != null && entryPx != null;

  const exitExecuted = result?.exit_executed === true;
  const exitPx = exitExecuted ? finiteOrNull(result?.exit_px) : null;
  const exitMs = exitExecuted ? finiteOrNull(result?.exit_ms) : null;
  const hasExit = exitExecuted && exitPx != null && exitMs != null;

  const stopPx = hasFill ? finiteOrNull(position.stop_px) : null;
  const openAtEnd = result?.open_at_end === true;

  const realized = hasExit ? finiteOrNull(result?.realized_net) : null;
  const realizedStatus: ChartOperation["realized_status"] = hasExit
    ? (realized == null ? "UNKNOWN" : "known")
    : "not_realized";

  const unrealized = position.open === true
    ? (finiteOrNull(position.unrealized_net)
      ?? (openAtEnd ? finiteOrNull(result?.net_pnl) : null))
    : null;

  const signalEvent = signalAt == null
    ? null
    : events.find(
      (e) => e.kind === "protection" && e.at_ms === signalAt
        && /ENTRADA_SIMULADA/i.test(e.label),
    ) ?? null;
  const entryEvent = hasFill ? findEvent(events, "entry", entryMs) : null;
  const exitEvent = hasExit ? findEvent(events, "exit", exitMs) : null;

  const markers: ChartMarker[] = [];
  if (hasDecisionEntry && signalAt != null) {
    markers.push({
      id: `signal:${state.session_id}:${signalAt}`,
      kind: "signal",
      time_ms: signalAt,
      time_s: msToChartSecond(signalAt),
      price: trigger,
      label: "Señal",
      event_id: signalEvent?.event_id ?? null,
    });
  }
  if (hasFill) {
    markers.push({
      id: `entry:${state.session_id}:${entryMs}`,
      kind: "entry",
      time_ms: entryMs,
      time_s: msToChartSecond(entryMs),
      price: entryPx,
      label: "Entrada",
      event_id: entryEvent?.event_id ?? null,
    });
  }
  if (hasExit) {
    markers.push({
      id: `exit:${state.session_id}:${exitMs}`,
      kind: "exit",
      time_ms: exitMs,
      time_s: msToChartSecond(exitMs),
      price: exitPx,
      label: "Salida",
      event_id: exitEvent?.event_id ?? null,
    });
  }
  markers.sort((a, b) => a.time_ms - b.time_ms
    || ["signal", "entry", "exit"].indexOf(a.kind)
      - ["signal", "entry", "exit"].indexOf(b.kind));

  const contextSorted = dedupeSorted(contextKnown);
  const closedSorted = dedupeSorted(closedKnown);
  const openSorted = dedupeSorted(openKnown);

  const limits = state.can_step === true
    ? "fixture: quedan aperturas por revelar o paso final"
    : (state.status === "cerrada"
      ? (openAtEnd ? "fin de datos: posición abierta, sin salida ejecutada" : "sesión cerrada")
      : "sin avance disponible");

  return {
    contract_version: PAPER_CHART_CONTRACT_VERSION,
    identity: {
      source: "fixture",
      venue: null,
      venue_status: "UNKNOWN",
      market_type: "simulated_futures",
      symbol: config.symbol,
      interval: config.interval,
      session_id: state.session_id,
      fixture_id: opts.fixtureId ?? null,
    },
    times: {
      unit: "ms",
      epoch: "unix_utc",
      created_at_ms: state.created_at_ms,
      updated_at_ms: state.updated_at_ms,
      clock_ms: state.clock_ms ?? null,
    },
    candles: {
      context: contextSorted,
      closed: closedSorted,
      open_only: openSorted,
    },
    indicators: [],
    volume: null,
    volume_status: "UNKNOWN",
    operation: {
      decision: config.decision ?? null,
      signal: hasDecisionEntry && signalAt != null
        ? {at_ms: signalAt, price: trigger, event_id: signalEvent?.event_id ?? null}
        : null,
      pending_entry: pending
        ? {reference_px: config.entry_px}
        : null,
      entry: hasFill ? {px: entryPx, ms: entryMs, event_id: entryEvent?.event_id ?? null} : null,
      stop_effective_px: stopPx,
      target_px: null,
      target_status: "UNKNOWN",
      exit: hasExit
        ? {
          px: exitPx,
          ms: exitMs,
          reason: result?.exit_reason ?? null,
          event_id: exitEvent?.event_id ?? null,
        }
        : null,
      realized_net: realized,
      realized_status: realizedStatus,
      unrealized_net: unrealized,
      open_at_end: openAtEnd,
      mark_px: finiteOrNull(position.mark_px),
      mark_ms: finiteOrNull(position.mark_ms),
    },
    markers,
    capabilities: {
      status: state.status,
      can_step: state.can_step === true,
      cursor: state.cursor,
      context_count: contextSorted.length,
      closed_count: closedSorted.length,
      open_only_count: openSorted.length,
      limits,
    },
  };
}
