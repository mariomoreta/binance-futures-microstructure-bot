// Actualización continua del gráfico de mercado — contrato `market-stream/v1`.
//
// Extiende, de forma versionada e independiente, el modelo `market-chart/v1`:
// el histórico sigue viniendo del REST paginado y la cola viva del servicio
// local SSE. Nada de lo que hay aquí adquiere datos por su cuenta: este módulo
// solo valida, fusiona y describe lo que el backend publicó.
//
// Reglas duras:
//  * una vela solo se considera cerrada si el backend lo dijo (`closed: true`);
//  * nunca se reabre una vela cerrada ni se interpola un precio;
//  * `LIVE` exige RECEIVING + socket + identidad + antigüedad dentro de la
//    política; un socket abierto no basta;
//  * el volumen se conserva en su unidad (base) y es `null` si la fuente no lo
//    publica.

import type {MarketSeriesCandle, MarketSeriesPayload} from "./market-chart-contract";
import {applyStreamIndicators} from "./market-chart-contract";

export const MARKET_STREAM_CONTRACT_VERSION = "market-stream/v1";

export type MarketStreamState =
  | "CONNECTING"
  | "RECEIVING"
  | "STALE"
  | "DISCONNECTED"
  | "RECOVERING";

export interface MarketStreamCandle {
  symbol: string;
  interval: string;
  open_time_ms: number;
  close_time_ms: number | null;
  open: number;
  high: number;
  low: number;
  close: number;
  base_volume: number | null;
  quote_volume: number | null;
  trade_count: number | null;
  closed: boolean;
  event_ms: number;
  received_ms: number;
  source: string;
  seq: number;
}

export interface MarketStreamStatus {
  symbol: string;
  interval: string;
  connection: {
    state: MarketStreamState;
    socket_connected: boolean;
    fresh_ms: number;
    stale_ms: number;
  };
  last_message_ms: number | null;
  last_kline_open_ms: number | null;
  closed_through_ms: number | null;
  age_ms: number | null;
  live: boolean;
  recovering: boolean;
  generated_at_ms: number;
}

export interface MarketStreamGap {
  symbol: string;
  interval: string;
  reason: string;
  status: "detected" | "complete" | "partial" | "failed";
  expected_from_ms: number | null;
  expected_to_ms: number | null;
  missing: number[][];
  requests: number;
  recovered_bars?: number;
  detail?: string | null;
  note?: string;
}

export interface MarketStreamSnapshot {
  symbol: string;
  interval: string;
  window?: {from_ms?: number; to_ms?: number} | null;
  candles: Array<{
    open_time_ms: number;
    close_time_ms: number | null;
    open: number | null;
    high: number | null;
    low: number | null;
    close: number | null;
    base_volume: number | null;
    quote_volume: number | null;
    trade_count: number | null;
    closed: boolean;
  }>;
  observed?: {start_ms: number | null; end_ms: number | null} | null;
  coverage?: {state?: string} | null;
  source?: string;
  generated_at_ms?: number;
  /**
   * market-indicators/v1 calculado por el backend sobre la ventana del
   * snapshot (velas cerradas); opacidad `unknown`: el navegador no valida
   * aquí, la sanitización ocurre en `applyStreamIndicators`.
   */
  indicators?: unknown;
}

/** Metadatos del feed incorporados al modelo del gráfico. */
export interface MarketChartStream {
  contract_version: typeof MARKET_STREAM_CONTRACT_VERSION;
  state: MarketStreamState;
  live: boolean;
  socket_connected: boolean;
  age_ms: number | null;
  last_message_ms: number | null;
  last_kline_open_ms: number | null;
  closed_through_ms: number | null;
  fresh_ms: number;
  stale_ms: number;
  recovering: boolean;
  gaps: MarketStreamGap[];
  note: string;
}

/** Estado que consume la UI (no es autoridad: refleja el backend). */
export interface MarketStreamView {
  available: boolean | null;
  status: MarketStreamStatus | null;
  snapshot: MarketStreamSnapshot | null;
  updates: MarketStreamCandle[];
  gaps: MarketStreamGap[];
  /** Último bloque `market-indicators/v1` recibido por el stream (raw). */
  indicators: unknown;
  error: string | null;
  attempts: number;
}

export function emptyStreamView(): MarketStreamView {
  return {
    available: null, status: null, snapshot: null,
    updates: [], gaps: [], indicators: null, error: null, attempts: 0,
  };
}

export function streamStateLabel(state: MarketStreamState | null | undefined): string {
  switch (state) {
    case "CONNECTING": return "CONECTANDO";
    case "RECEIVING": return "RECIBIENDO";
    case "STALE": return "OBSOLETO";
    case "RECOVERING": return "RECUPERANDO";
    case "DISCONNECTED": return "DESCONECTADO";
    default: return "SIN FEED";
  }
}

/** `LIVE` solo si el backend lo justifica con las cuatro condiciones. */
export function livePermitted(status: MarketStreamStatus | null | undefined): boolean {
  if (!status) return false;
  if (status.live !== true) return false;
  if (status.connection?.state !== "RECEIVING") return false;
  if (status.connection?.socket_connected !== true) return false;
  const age = status.age_ms;
  const fresh = status.connection?.fresh_ms;
  if (age === null || age === undefined || fresh === undefined) return false;
  return age >= 0 && age <= fresh;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string" || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function streamCandleToSeriesRow(candle: MarketStreamCandle): MarketSeriesCandle | null {
  const open = toNumber(candle.open);
  const high = toNumber(candle.high);
  const low = toNumber(candle.low);
  const close = toNumber(candle.close);
  if ([open, high, low, close].some((value) => value === null)) return null;
  return {
    open_time_ms: candle.open_time_ms,
    close_time_ms: candle.closed ? candle.close_time_ms : null,
    open: String(open), high: String(high), low: String(low), close: String(close),
    base_volume: candle.base_volume === null ? null : String(candle.base_volume),
    quote_volume: candle.quote_volume === null ? null : String(candle.quote_volume),
    trade_count: candle.trade_count,
    provisional: candle.closed !== true,
    fetched_at_ms: candle.received_ms,
    storage: "stream",
  };
}

function snapshotCandleToSeriesRow(
  candle: MarketStreamSnapshot["candles"][number],
): MarketSeriesCandle | null {
  const open = toNumber(candle.open);
  const high = toNumber(candle.high);
  const low = toNumber(candle.low);
  const close = toNumber(candle.close);
  if ([open, high, low, close].some((value) => value === null)) return null;
  return {
    open_time_ms: candle.open_time_ms,
    close_time_ms: candle.closed ? candle.close_time_ms : null,
    open: String(open), high: String(high), low: String(low), close: String(close),
    base_volume: candle.base_volume === null ? null : String(candle.base_volume),
    quote_volume: candle.quote_volume === null ? null : String(candle.quote_volume),
    trade_count: candle.trade_count,
    provisional: candle.closed !== true,
    fetched_at_ms: null,
    storage: "stream_snapshot",
  };
}

/**
 * Fusiona velas por `open_time_ms`:
 *  * una cerrada gana sobre una provisional del mismo tiempo;
 *  * entre provisionales gana la última recibida;
 *  * nunca se elimina una vela del histórico REST.
 */
export function mergeCandleRows(
  base: MarketSeriesCandle[],
  incoming: MarketSeriesCandle[],
): MarketSeriesCandle[] {
  const byTime = new Map<number, MarketSeriesCandle>();
  for (const candle of base) byTime.set(candle.open_time_ms, candle);
  for (const candle of incoming) {
    const previous = byTime.get(candle.open_time_ms);
    if (previous && previous.provisional === false && candle.provisional === true) {
      continue; // una provisional no reabre una cerrada
    }
    byTime.set(candle.open_time_ms, candle);
  }
  return [...byTime.values()].sort((a, b) => a.open_time_ms - b.open_time_ms);
}

/** Aplica snapshot + actualizaciones del stream sobre el histórico REST. */
export function mergeStreamIntoSeries(
  payload: MarketSeriesPayload,
  view: MarketStreamView | null | undefined,
): MarketSeriesPayload {
  if (!view) return payload;
  const incoming: MarketSeriesCandle[] = [];
  for (const candle of view.snapshot?.candles ?? []) {
    const row = snapshotCandleToSeriesRow(candle);
    if (row) incoming.push(row);
  }
  for (const candle of view.updates) {
    if (candle.symbol !== payload.symbol || candle.interval !== payload.interval) {
      continue; // identidad: nunca se mezclan símbolos ni intervalos
    }
    const row = streamCandleToSeriesRow(candle);
    if (row) incoming.push(row);
  }
  // Indicadores versionados del feed (recalculados en el backend al cerrar
  // una vela): solo se aceptan del mismo símbolo/intervalo, sin recálculo
  // local y uniendo filas; si no hay velas nuevas igual se actualizan.
  const withIndicators = applyStreamIndicators(payload, view.indicators);
  if (incoming.length === 0) return withIndicators;
  const candles = mergeCandleRows(withIndicators.candles, incoming);
  const last = candles[candles.length - 1];
  return {
    ...withIndicators,
    candles,
    observed: {
      start_ms: candles[0]?.open_time_ms ?? null,
      end_ms: last?.open_time_ms ?? null,
    },
    freshness: {
      ...withIndicators.freshness,
      newest_open_ms: last?.open_time_ms ?? null,
      newest_close_ms: last && !last.provisional ? last.close_time_ms : null,
      provisional: last ? last.provisional : null,
    },
  };
}

export function buildStreamMeta(view: MarketStreamView | null | undefined): MarketChartStream | null {
  if (!view || !view.status) return null;
  const status = view.status;
  return {
    contract_version: MARKET_STREAM_CONTRACT_VERSION,
    state: status.connection.state,
    live: livePermitted(status),
    socket_connected: status.connection.socket_connected,
    age_ms: status.age_ms,
    last_message_ms: status.last_message_ms,
    last_kline_open_ms: status.last_kline_open_ms,
    closed_through_ms: status.closed_through_ms,
    fresh_ms: status.connection.fresh_ms,
    stale_ms: status.connection.stale_ms,
    recovering: status.recovering,
    gaps: view.gaps.slice(-5),
    note: status.connection.socket_connected
      ? "feed Binance USD-M por WebSocket público (market-stream/v1)"
      : "sin socket activo: se conserva el histórico y no se declara LIVE",
  };
}

/** Texto honesto para un hueco informado por el backend. */
export function describeGap(gap: MarketStreamGap): string {
  const range = gap.expected_from_ms !== null && gap.expected_to_ms !== null
    ? `${gap.expected_from_ms}→${gap.expected_to_ms} ms`
    : "tramo desconocido";
  switch (gap.status) {
    case "detected": return `hueco detectado (${gap.reason}) ${range}`;
    case "complete": return `hueco reparado por REST ${range} · ${gap.recovered_bars ?? 0} vela(s)`;
    case "partial": return `reparación parcial ${range} · faltan ${gap.missing.length} tramo(s)`;
    default: return `reparación fallida ${range}${gap.detail ? ` · ${gap.detail}` : ""}`;
  }
}
