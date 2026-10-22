// Explorador de mercado — contrato presentacional del gráfico
// (market-chart/v1).
//
// Extiende, de forma versionada, el contrato aceptado `paper-chart/v1` SIN
// modificarlo: `paper-chart/v1` sigue siendo el modelo de Paper Lab sobre
// fixtures y este módulo produce un modelo distinto para histórico de mercado
// consultado bajo demanda.
//
// Procedencia real: Binance USD-M Futures (fapi), contrato, símbolo, intervalo
// y endpoint publicados por el backend (`market-series/v1`). El backend es la
// única autoridad de velas, cobertura y frescura; este módulo NO calcula
// indicadores, objetivos, señales, niveles ni P&L, y NUNCA mezcla marcas de
// operaciones de una sesión Paper Lab en un contexto de mercado.
//
// Unidades: el backend publica milisegundos Unix UTC; Lightweight Charts usa
// segundos Unix UTC. La conversión es explícita (msToChartSecond) y el
// milisegundo exacto se conserva aquí para detalle y evidencia. Los precios y
// volúmenes llegan como las cadenas exactas del exchange y se convierten con
// `Number()`; si no son numéricos quedan null (UNKNOWN), nunca 0.

import {msToChartSecond} from "./paper-chart-contract";
import type {OpenOnlyChartCandle} from "./paper-chart-contract";

export const MARKET_CHART_CONTRACT_VERSION = "market-chart/v1" as const;
export type MarketChartContractVersion = typeof MARKET_CHART_CONTRACT_VERSION;

export const MARKET_SERIES_CONTRACT_VERSION = "market-series/v1" as const;

export type MarketCoverageState = "NO_COVERAGE" | "PARTIAL" | "COVERED";

export interface MarketContractRow {
  symbol: string;
  base_asset: string | null;
  quote_asset: string | null;
  margin_asset?: string | null;
  contract_type: string | null;
  status: string | null;
  onboard_ms?: number | null;
  price_precision?: number | null;
  tick_size?: string | null;
  eligible: boolean;
  exclusion_reasons: string[];
  fetched_at?: number | null;
}

export interface MarketCatalogPayload {
  contract_version: string;
  venue: string;
  market_type: string;
  api_family: string;
  endpoint: string;
  spot_included: boolean;
  available: boolean;
  reason: string | null;
  query: string;
  results: MarketContractRow[];
  result_count: number;
  truncated: boolean;
  catalog: {
    entries: number;
    fetched_at_ms: number | null;
    age_ms: number | null;
    stale: boolean;
    endpoint: string | null;
  };
  refresh: {refreshed: boolean; reason: string; requests: number};
  notes: string[];
}

export interface MarketSeriesCandle {
  open_time_ms: number;
  close_time_ms: number | null;
  open: string | null;
  high: string | null;
  low: string | null;
  close: string | null;
  base_volume: string | null;
  quote_volume: string | null;
  trade_count: number | null;
  provisional: boolean;
  fetched_at_ms: number | null;
  storage: string | null;
}

export interface MarketSeriesPayload {
  contract_version: string;
  venue: string;
  market_type: string;
  api_family: string;
  source: string;
  endpoint: string;
  symbol: string;
  interval: string;
  interval_ms: number;
  contract: MarketContractRow | null;
  requested: {from_ms: number; to_ms: number};
  observed: {start_ms: number | null; end_ms: number | null};
  candles: MarketSeriesCandle[];
  coverage: {
    state: MarketCoverageState;
    observed_start_ms: number | null;
    observed_end_ms: number | null;
    expected_bars: number;
    actual_bars: number;
    gap_count: number | null;
    gaps: number[][];
    absent_ranges: number[][];
    exhausted_before: boolean;
    earliest_available_ms: number | null;
    note: string;
  };
  volume: {
    available: boolean;
    base_asset: string | null;
    quote_asset: string | null;
    fields: string[];
    reason: string | null;
  };
  freshness: {
    state: string;
    newest_open_ms: number | null;
    newest_close_ms: number | null;
    fetched_at_ms: number | null;
    age_ms: number | null;
    provisional: boolean | null;
    note: string;
  };
  fetch: {
    allowed: boolean;
    performed: boolean;
    status: string;
    error: string | null;
    requests: number;
    pages: number;
    retries: number;
    failures: number;
    detail: string | null;
    bars_stored?: number;
    block?: number[];
    retry_after_ms: number | null;
  };
  storage?: {
    canonical_error: string | null;
    canonical_rows: number;
    cache_rows: number;
  };
  labels: {mode: string; live: boolean; banner: string};
  generated_at_ms: number;
  notes: string[];
  budget?: {
    window_ms: number;
    max_requests_per_window: number;
    used_in_window: number;
    max_pages_per_request: number;
    max_page_limit: number;
    concurrency: number;
  };
}

export interface MarketClosedCandle {
  kind: "closed";
  open_time_ms: number;
  close_time_ms: number | null;
  open: number;
  high: number;
  low: number;
  close: number;
  base_volume: number | null;
  quote_volume: number | null;
  /** Milisegundos exactos de adquisición; no es hora de cierre. */
  fetched_at_ms: number | null;
  storage: string | null;
}

export interface MarketProvisionalCandle {
  kind: "provisional";
  open_time_ms: number;
  close_time_ms: null;
  open: number;
  high: number;
  low: number;
  close: number;
  base_volume: number | null;
  quote_volume: number | null;
  fetched_at_ms: number | null;
  storage: string | null;
}

export interface MarketVolumeBar {
  time_ms: number;
  /** Volumen del activo base (unidad explícita en `volume_unit`). */
  value: number;
  open: number;
  close: number;
}

/**
 * Marca de mercado: NO es una operación. Solo distingue la vela actual
 * provisional (aún sin cerrar) de las velas cerradas.
 */
export interface MarketChartMarker {
  id: string;
  kind: "provisional";
  time_ms: number;
  time_s: number;
  price: number | null;
  label: string;
  event_id: null;
}

export interface MarketChartModel {
  contract_version: MarketChartContractVersion;
  identity: {
    source: "binance_historical";
    venue: "binance";
    venue_status: "PUBLIC_REST";
    market_type: "usd_m_futures";
    symbol: string;
    interval: string;
    interval_ms: number;
    endpoint: string;
    session_id: null;
    contract: MarketContractRow | null;
  };
  times: {
    unit: "ms";
    epoch: "unix_utc";
    generated_at_ms: number;
    newest_open_ms: number | null;
    newest_close_ms: number | null;
    fetched_at_ms: number | null;
    age_ms: number | null;
  };
  candles: {
    context: [];
    closed: MarketClosedCandle[];
    open_only: OpenOnlyChartCandle[];
    provisional: MarketProvisionalCandle[];
    unusable: number;
  };
  volume: MarketVolumeBar[] | null;
  volume_unit: string | null;
  volume_status: "AVAILABLE" | "UNAVAILABLE";
  volume_reason: string | null;
  coverage: MarketSeriesPayload["coverage"];
  freshness: MarketSeriesPayload["freshness"];
  fetch: MarketSeriesPayload["fetch"];
  storage: MarketSeriesPayload["storage"] | null;
  /** El explorador nunca presenta una operación: no es una sesión. */
  operation: null;
  /** Solo marcas derivadas del propio histórico (p. ej. vela provisional). */
  markers: MarketChartMarker[];
  indicators: never[];
  capabilities: {
    mode: "market";
    live: false;
    banner: string;
    coverage_state: MarketCoverageState;
    can_fetch_earlier: boolean;
    earlier_from_ms: number | null;
    limits: string;
  };
  notes: string[];
}

function numFromText(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string" || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function finiteOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Deduplica por apertura conservando el último valor recibido y ordena. */
function dedupeByOpenTime<T extends {open_time_ms: number}>(items: T[]): T[] {
  const byTime = new Map<number, T>();
  for (const item of items) byTime.set(item.open_time_ms, item);
  return [...byTime.values()].sort((a, b) => a.open_time_ms - b.open_time_ms);
}

export function buildMarketChartModel(
  payload: MarketSeriesPayload,
  opts: {contract?: MarketContractRow | null} = {},
): MarketChartModel {
  const closed: MarketClosedCandle[] = [];
  const provisional: MarketProvisionalCandle[] = [];
  let unusable = 0;
  for (const raw of payload.candles ?? []) {
    const open = numFromText(raw?.open);
    const high = numFromText(raw?.high);
    const low = numFromText(raw?.low);
    const close = numFromText(raw?.close);
    const openTime = finiteOrNull(raw?.open_time_ms);
    // Sin OHLC numérico no se dibuja: se cuenta como no utilizable, no se
    // rellena con ceros ni con la apertura.
    if (open == null || high == null || low == null || close == null
      || openTime == null) {
      unusable += 1;
      continue;
    }
    const baseVolume = numFromText(raw.base_volume);
    const quoteVolume = numFromText(raw.quote_volume);
    const fetchedAt = finiteOrNull(raw.fetched_at_ms);
    if (raw.provisional === true) {
      provisional.push({
        kind: "provisional", open_time_ms: openTime, close_time_ms: null,
        open, high, low, close, base_volume: baseVolume,
        quote_volume: quoteVolume, fetched_at_ms: fetchedAt,
        storage: raw.storage ?? null,
      });
      continue;
    }
    closed.push({
      kind: "closed", open_time_ms: openTime,
      close_time_ms: finiteOrNull(raw.close_time_ms),
      open, high, low, close, base_volume: baseVolume,
      quote_volume: quoteVolume, fetched_at_ms: fetchedAt,
      storage: raw.storage ?? null,
    });
  }

  const closedSorted = dedupeByOpenTime(closed);
  const provisionalSorted = dedupeByOpenTime(provisional);
  const symbol = payload.symbol;
  const contract = opts.contract ?? payload.contract ?? null;

  const volumeAvailable = payload.volume?.available === true
    && closedSorted.some((c) => c.base_volume != null);
  const volumeBars: MarketVolumeBar[] | null = volumeAvailable
    ? closedSorted
      .filter((c) => c.base_volume != null)
      .map((c) => ({
        time_ms: c.open_time_ms, value: c.base_volume as number,
        open: c.open, close: c.close,
      }))
    : null;
  const volumeUnit = volumeAvailable
    ? (payload.volume?.base_asset ?? null)
    : null;

  const markers: MarketChartMarker[] = [];
  for (const candle of provisionalSorted) {
    markers.push({
      id: `provisional:${symbol}:${candle.open_time_ms}`,
      kind: "provisional",
      time_ms: candle.open_time_ms,
      time_s: msToChartSecond(candle.open_time_ms),
      price: candle.open,
      label: "provisional",
      event_id: null,
    });
  }
  markers.sort((a, b) => a.time_ms - b.time_ms);

  const observedStart = finiteOrNull(payload.observed?.start_ms);
  const exhausted = payload.coverage?.exhausted_before === true;
  const canFetchEarlier = !exhausted && observedStart != null
    && payload.requested?.from_ms != null
    && observedStart > payload.requested.from_ms
    && payload.coverage?.state !== "NO_COVERAGE";

  const coverage = payload.coverage;
  const limits = [
    `cobertura ${coverage?.state ?? "UNKNOWN"}`,
    coverage?.gap_count ? `${coverage.gap_count} hueco(s)` : "sin huecos",
    coverage?.exhausted_before
      ? "fin de histórico alcanzado"
      : (canFetchEarlier ? "hay tramos anteriores" : "sin tramos anteriores"),
  ].join(" · ");

  return {
    contract_version: MARKET_CHART_CONTRACT_VERSION,
    identity: {
      source: "binance_historical",
      venue: "binance",
      venue_status: "PUBLIC_REST",
      market_type: "usd_m_futures",
      symbol,
      interval: payload.interval,
      interval_ms: payload.interval_ms,
      endpoint: payload.endpoint,
      session_id: null,
      contract,
    },
    times: {
      unit: "ms",
      epoch: "unix_utc",
      generated_at_ms: payload.generated_at_ms,
      newest_open_ms: finiteOrNull(payload.freshness?.newest_open_ms),
      newest_close_ms: finiteOrNull(payload.freshness?.newest_close_ms),
      fetched_at_ms: finiteOrNull(payload.freshness?.fetched_at_ms),
      age_ms: finiteOrNull(payload.freshness?.age_ms),
    },
    candles: {
      context: [],
      closed: closedSorted,
      open_only: [],
      provisional: provisionalSorted,
      unusable,
    },
    volume: volumeBars,
    volume_unit: volumeUnit,
    volume_status: volumeAvailable ? "AVAILABLE" : "UNAVAILABLE",
    volume_reason: volumeAvailable ? null : (payload.volume?.reason ?? null),
    coverage,
    freshness: payload.freshness,
    fetch: payload.fetch,
    storage: payload.storage ?? null,
    operation: null,
    markers,
    indicators: [],
    capabilities: {
      mode: "market",
      live: false,
      banner: payload.labels?.banner ?? "HISTORICO / CONSULTA BAJO DEMANDA",
      coverage_state: (coverage?.state ?? "NO_COVERAGE") as MarketCoverageState,
      can_fetch_earlier: canFetchEarlier,
      earlier_from_ms: observedStart,
      limits,
    },
    notes: payload.notes ?? [],
  };
}

/**
 * Guarda de contrato: ninguna marca de operación Paper Lab puede viajar en un
 * modelo de mercado. Devuelve las marcas no permitidas (vacío = correcto).
 */
export function paperMarkersLeaked(model: MarketChartModel): string[] {
  return model.markers
    .map((m) => m.id)
    .filter((id) => !/^provisional:/.test(id));
}
