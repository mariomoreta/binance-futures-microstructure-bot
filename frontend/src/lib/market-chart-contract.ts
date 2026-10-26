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
import type {MarketChartStream} from "./market-stream";

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

/** market-indicators/v1: bloque versionado calculado por el backend. */
export interface MarketIndicatorDefinition {
  name: string;
  formula: string;
  unit: string;
  window_candles: number;
  requires: string;
}

export interface MarketIndicatorRow {
  open_time_ms: number;
  available_at_ms: number;
  /** Solo valores numéricos finitos; lo faltante está en `unknown`. */
  values: Record<string, number>;
  /** Motivos UNKNOWN por indicador; nunca cero substituto. */
  unknown: Record<string, string>;
}

export interface MarketIndicatorsBlock {
  contract_version: "market-indicators/v1";
  availability: string;
  provisional_policy: {included: boolean; reason: string;
    // brand de honestidad extra (permitir campos declarados después)
    [extra: string]: unknown};
  computed_over: string;
  identity: {
    symbol: string;
    interval: string;
    interval_ms: number;
    source: string;
  };
  definitions: MarketIndicatorDefinition[];
  supported: string[];
  declined: Array<{name: string; reason: string}>;
  series: MarketIndicatorRow[];
  generated_at_ms: number;
}

export interface MarketSeriesPayload {
  contract_version: string;
  venue: string;
  market_type: string;
  api_family: string;
  source: string;  endpoint: string;
  symbol: string;
  interval: string;
  interval_ms: number;
  contract: MarketContractRow | null;
  requested: {from_ms: number; to_ms: number};
  observed: {start_ms: number | null; end_ms: number | null};
  candles: MarketSeriesCandle[];
  indicators?: MarketIndicatorsBlock | null;
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
  /** Bloque `market-indicators/v1` del backend; null = sin indicadores. */
  indicators: MarketIndicatorsBlock | null;
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
  /** Feed continuo (`market-stream/v1`); `null` = solo histórico REST. */
  stream: MarketChartStream | null;
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

/**
 * Antepone un bloque histórico al ya cargado sin perder el extremo reciente.
 *
 * - Deduplica por apertura conservando la fila ya cargada: el extremo reciente
 *   manda y una provisional nunca reabre una cerrada.
 * - Recalcula rango observado y cobertura sobre la rejilla real; los huecos se
 *   declaran, no se interpolan.
 * - `exhausted_before` lo informa el bloque anterior (es quien mira más atrás).
 * - Devuelve `added` (velas únicas nuevas) para no exigir +300 cuando la
 *   respuesta solapa con lo ya cargado: solapamiento legítimo no es pérdida.
 */
export function mergeEarlierSeries(
  previous: MarketSeriesPayload,
  block: MarketSeriesPayload,
): {payload: MarketSeriesPayload; added: number} {
  if (block.symbol !== previous.symbol || block.interval !== previous.interval) {
    return {payload: previous, added: 0};
  }
  const byTime = new Map<number, MarketSeriesCandle>();
  for (const candle of previous.candles) byTime.set(candle.open_time_ms, candle);
  let added = 0;
  for (const candle of block.candles) {
    if (!byTime.has(candle.open_time_ms)) {
      byTime.set(candle.open_time_ms, candle);
      added += 1;
    }
  }
  const candles = [...byTime.values()].sort((a, b) => a.open_time_ms - b.open_time_ms);
  const step = previous.interval_ms;
  const start = candles[0]?.open_time_ms ?? null;
  const end = candles[candles.length - 1]?.open_time_ms ?? null;
  const expected = start !== null && end !== null && step > 0
    ? Math.round((end - start) / step) + 1
    : candles.length;
  const gaps: number[][] = [];
  for (let index = 1; index < candles.length; index += 1) {
    const previousOpen = candles[index - 1]!.open_time_ms;
    const open = candles[index]!.open_time_ms;
    if (open - previousOpen > step) gaps.push([previousOpen + step, open - step]);
  }
  const covered = previous.coverage.state === "COVERED"
    && block.coverage.state === "COVERED" && gaps.length === 0;
  return {
    added,
    payload: {
      ...previous,
      requested: {
        from_ms: Math.min(previous.requested.from_ms, block.requested.from_ms),
        to_ms: Math.max(previous.requested.to_ms, block.requested.to_ms),
      },
      observed: {start_ms: start, end_ms: end},
      candles,
      coverage: {
        ...previous.coverage,
        state: covered ? "COVERED" : (candles.length > 0 ? "PARTIAL" : "NO_COVERAGE"),
        observed_start_ms: start,
        observed_end_ms: end,
        expected_bars: expected,
        actual_bars: candles.length,
        gap_count: gaps.length,
        gaps,
        absent_ranges: covered ? [] : previous.coverage.absent_ranges,
        exhausted_before: block.coverage.exhausted_before,
        earliest_available_ms: block.coverage.earliest_available_ms
          ?? previous.coverage.earliest_available_ms,
      },
      indicators: mergeIndicatorBlocks(
        parseMarketIndicators(previous), parseMarketIndicators(block)),
    },
  };
}

/**
 * Validacion del bloque de indicadores sin identidad conectada: version,
 * filas finitas. Un bloque que no corresponda (version o filas corruptas)
 * se descarta entero (`null`), nunca se muestra con datos que no sean del
 * backend.
 */
export function sanitizeIndicatorsBlock(
  raw: unknown,
): MarketIndicatorsBlock | null {
  if (raw == null || typeof raw !== "object") return null;
  const block = raw as MarketIndicatorsBlock;
  if (block.contract_version !== "market-indicators/v1") return null;
  if (!block.identity || typeof block.identity !== "object") return null;
  if (!Array.isArray(block.series)) return null;
  const series: MarketIndicatorRow[] = [];
  for (const row of block.series) {
    if (row == null || typeof row !== "object") continue;
    const openTime = finiteOrNull(row.open_time_ms);
    if (openTime == null) continue;
    const values: Record<string, number> = {};
    const unknown: Record<string, string> = {};
    for (const [name, value] of Object.entries(row.values ?? {})) {
      const parsed = finiteOrNull(value);
      if (parsed != null) values[name] = parsed;
    }
    for (const [name, reason] of Object.entries(row.unknown ?? {})) {
      if (typeof reason === "string" && reason !== "") unknown[name] = reason;
    }
    series.push({
      open_time_ms: openTime,
      available_at_ms: finiteOrNull(row.available_at_ms)
        ?? (openTime + (block.identity.interval_ms ?? 0)),
      values,
      unknown,
    });
  }
  return {
    ...block,
    definitions: block.definitions ?? [],
    supported: block.supported ?? [],
    declined: block.declined ?? [],
    series,
  };
}

/**
 * Lectura del bloque de indicadores del payload. El navegador NO recalcula:
 * presencia, versión, identidad y filas finitas se validan, y un bloque que
 * no corresponda (versión, identidad o filas corruptas) se descarta entero
 * (`null`), nunca se muestra con datos que no sean del backend.
 */
export function parseMarketIndicators(
  payload: MarketSeriesPayload,
): MarketIndicatorsBlock | null {
  const block = sanitizeIndicatorsBlock(
    (payload as {indicators?: unknown}).indicators);
  if (!block) return null;
  if (block.identity?.symbol !== payload.symbol
    || block.identity?.interval !== payload.interval
    || block.identity?.interval_ms !== payload.interval_ms) return null;
  return block;
}

/** Fila de indicadores para la vela exacta bajo el cursor (o null). */
export function marketIndicatorAtCursor(
  block: MarketIndicatorsBlock | null,
  openTimeMs: number | null | undefined,
): MarketIndicatorRow | null {
  if (!block || openTimeMs == null) return null;
  return block.series.find((row) => row.open_time_ms === openTimeMs) ?? null;
}

const INDICATOR_LABELS: Record<string, string> = {
  log_return_bps: "ret",
  velocity_bps_5: "vel",
  rel_volume_10: "relvol",
  vwap_typical_10: "vwap",
  vwap_dev_bps_10: "vwapdev",
};

const INDICATOR_UNITS: Record<string, string> = {
  log_return_bps: "bps",
  velocity_bps_5: "bps",
  rel_volume_10: "x",
  vwap_typical_10: "",
  vwap_dev_bps_10: "bps",
};

const INDICATOR_DECIMALS: Record<string, number> = {
  log_return_bps: 2,
  velocity_bps_5: 2,
  rel_volume_10: 3,
  vwap_typical_10: 4,
  vwap_dev_bps_10: 2,
};

function formatIndicatorValue(name: string, value: number): string {
  const decimals = INDICATOR_DECIMALS[name] ?? 3;
  return `${value.toFixed(decimals)}${INDICATOR_UNITS[name] ?? ""}`;
}

/**
 * Texto compacto y honesto para el badge de indicadores, con UNIDAD visible:
 * `market-indicators/v1 · ret 12.30bps · relvol UNKNOWN(GAP_IN_WINDOW)` ...
 * El navegador solo lee lo que el backend ya calculó: sin UNKNOWN no se
 * imprime valor y nunca se substituye con 0 ni con re-cálculo local.
 */
export function marketIndicatorsBadgeText(
  block: MarketIndicatorsBlock | null,
  openTimeMs: number | null | undefined,
  provisionalHere: boolean = false,
): string {
  if (!block) return "Indicadores: ninguno (market-indicators/v1 ausente)";
  const row = marketIndicatorAtCursor(block, openTimeMs);
  if (!row) {
    if (provisionalHere) {
      return "Indicadores: vela provisional excluida (politica del bloque)";
    }
    return "Indicadores: sin fila para la vela bajo el cursor";
  }
  const parts: string[] = [];
  for (const name of block.supported) {
    const label = INDICATOR_LABELS[name] ?? name;
    const value = row.values[name];
    if (value != null && Number.isFinite(value)) {
      parts.push(`${label} ${formatIndicatorValue(name, value)}`);
      continue;
    }
    const reason = row.unknown[name];
    if (reason) parts.push(`${label} UNKNOWN(${reason})`);
  }
  for (const [name, reason] of Object.entries(row.unknown)) {
    if (!block.supported.includes(name)) {
      parts.push(`${name} UNKNOWN(${reason})`);
    }
  }
  return `Indicadores: ${parts.join(" · ")}`;
}

/** Une los bloques de indicadores de dos payloads (block = más reciente). */
export function mergeIndicatorBlocks(
  previous: MarketIndicatorsBlock | null,
  block: MarketIndicatorsBlock | null,
): MarketIndicatorsBlock | null {
  if (!previous && !block) return null;
  if (!previous) return block;
  if (!block) return previous;
  if (previous.identity.symbol !== block.identity.symbol
    || previous.identity.interval !== block.identity.interval
    || previous.identity.interval_ms !== block.identity.interval_ms) return null;
  const byTime = new Map<number, MarketIndicatorRow>();
  for (const row of previous.series) byTime.set(row.open_time_ms, row);
  for (const row of block.series) byTime.set(row.open_time_ms, row);
  const series = [...byTime.values()].sort(
    (a, b) => a.open_time_ms - b.open_time_ms);
  return {
    ...block,
    computed_over: "per_block_payload_windows",
    series,
  };
}

/**
 * Incorpora el bloque de indicadores que llega por el stream (recalculado en
 * el backend al cerrarse una vela) al payload. Identidad: solo se acepta un
 * bloque del MISMO símbolo/intervalo; las filas se unen (nuevo gana) sin
 * recalcular nada en el navegador.
 */
export function applyStreamIndicators(
  payload: MarketSeriesPayload,
  raw: unknown,
): MarketSeriesPayload {
  const incoming = sanitizeIndicatorsBlock(raw);
  if (!incoming) return payload;
  if (incoming.identity?.symbol !== payload.symbol
    || incoming.identity?.interval !== payload.interval
    || incoming.identity?.interval_ms !== payload.interval_ms) {
    return payload;
  }
  const merged = mergeIndicatorBlocks(
    payload.indicators ?? null, incoming)
    ?? payload.indicators ?? null;
  if (merged === payload.indicators) return payload;
  return {...payload, indicators: merged};
}

export function buildMarketChartModel(
  payload: MarketSeriesPayload,
  opts: {contract?: MarketContractRow | null; stream?: MarketChartStream | null} = {},
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
    indicators: parseMarketIndicators(payload),
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
    // `stream` es la extensión versionada independiente (`market-stream/v1`).
    // `capabilities.live` sigue siendo `false`: el modelo es histórico y el
    // estado del feed se declara aparte, nunca se deduce de un socket.
    stream: opts.stream ?? null,
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
