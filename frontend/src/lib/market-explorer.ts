// Explorador de mercado — cliente del BFF (solo presentación).
//
// El backend (scripts/market_explorer.py -> market_explorer.py) es la única
// autoridad de catálogo, velas, cobertura, frescura y presupuesto. Este módulo
// solo construye consultas acotadas y las decodifica. No calcula velas ni
// cobertura, no inventa campos ausentes y no mezcla sesiones Paper Lab.

import type {
  MarketCatalogPayload,
  MarketContractRow,
  MarketSeriesPayload,
} from "./market-chart-contract";

const CATALOG_API = "/api/v1/market-contracts";
const SERIES_API = "/api/v1/market-series";

/** Tamaño de bloque del explorador (velas por petición de UI). */
export const EXPLORER_PAGE_BARS = 300;
/** Páginas máximas por petición (el backend también lo acota). */
export const EXPLORER_PAGE_LIMIT = 300;

export type ExplorerResult<T> = {
  ok: boolean;
  data?: T;
  error?: string;
  detail?: string;
  status: number;
};

function queryString(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function apiJson<T>(
  url: string,
  signal?: AbortSignal,
): Promise<ExplorerResult<T>> {
  let response: Response;
  try {
    response = await fetch(url, {cache: "no-store", signal});
  } catch (error) {
    // AbortError no es un fallo de datos: el llamador lo descarta.
    const aborted = error instanceof DOMException && error.name === "AbortError";
    return {
      ok: false,
      status: 0,
      error: aborted ? "ABORTED" : "NETWORK_ERROR",
      detail: error instanceof Error ? error.message : String(error),
    };
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const record = (body ?? {}) as {error?: string; detail?: string};
    return {
      ok: false,
      status: response.status,
      error: record.error ?? `HTTP_${response.status}`,
      detail: record.detail,
    };
  }
  return {ok: true, data: body as T, status: response.status};
}

export interface CatalogQuery {
  query?: string;
  limit?: number;
  eligibleOnly?: boolean;
  refresh?: boolean;
  signal?: AbortSignal;
}

export async function searchContractsApi(
  options: CatalogQuery = {},
): Promise<ExplorerResult<MarketCatalogPayload>> {
  const url = CATALOG_API + queryString({
    q: (options.query ?? "").trim(),
    limit: options.limit ?? 20,
    eligible: options.eligibleOnly ? "1" : null,
    refresh: options.refresh ? "1" : null,
  });
  return apiJson<MarketCatalogPayload>(url, options.signal);
}

export interface SeriesQuery {
  symbol: string;
  interval: string;
  fromMs?: number | null;
  toMs?: number | null;
  bars?: number;
  pages?: number;
  pageLimit?: number;
  source?: "klines" | "mark_klines";
  probeEarliest?: boolean;
  signal?: AbortSignal;
}

export async function fetchSeriesApi(
  options: SeriesQuery,
): Promise<ExplorerResult<MarketSeriesPayload>> {
  const url = SERIES_API + queryString({
    symbol: options.symbol,
    interval: options.interval,
    from_ms: options.fromMs ?? null,
    to_ms: options.toMs ?? null,
    bars: options.bars ?? EXPLORER_PAGE_BARS,
    pages: options.pages ?? 1,
    page_limit: options.pageLimit ?? EXPLORER_PAGE_LIMIT,
    source: options.source ?? "klines",
    probe_earliest: options.probeEarliest ? "1" : null,
  });
  return apiJson<MarketSeriesPayload>(url, options.signal);
}

/** Ventana inicial: el bloque más reciente de `bars` velas. */
export function initialWindow(nowMs: number, intervalMs: number,
  bars = EXPLORER_PAGE_BARS): {fromMs: number; toMs: number} {
  const toMs = nowMs;
  const fromMs = toMs - (Math.max(1, bars) - 1) * intervalMs;
  return {fromMs, toMs};
}

/** Ventana tras pedir el bloque anterior: extiende `fromMs` un bloque. */
export function extendWindow(windowFromMs: number, intervalMs: number,
  bars = EXPLORER_PAGE_BARS): {fromMs: number; toMs: number} {
  return {fromMs: windowFromMs - Math.max(1, bars) * intervalMs,
    toMs: windowFromMs};
}

export function contractLabel(contract: MarketContractRow | null): string {
  if (!contract) return "sin contrato en catálogo";
  return `${contract.contract_type ?? "UNKNOWN"} · ${contract.status ?? "UNKNOWN"} · ${contract.eligible ? "elegible" : "no elegible"}`;
}

/** Episodios derivados de los rangos que informa el backend (solo lectura). */
export function describeCoverage(payload: MarketSeriesPayload): string {
  const coverage = payload.coverage;
  const parts = [
    `Estado ${coverage.state}`,
    `${coverage.actual_bars}/${coverage.expected_bars} velas`,
    coverage.gap_count ? `${coverage.gap_count} huecos` : "sin huecos",
  ];
  if (coverage.absent_ranges.length) {
    parts.push(`${coverage.absent_ranges.length} tramo(s) sin cobertura`);
  }
  if (coverage.exhausted_before) parts.push("fin de histórico");
  return parts.join(" · ");
}

export function formatUtc(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "UNKNOWN";
  return new Date(ms).toISOString().replace(/\.000Z$/, "Z");
}

export function windowLabel(fromMs: number, toMs: number): string {
  return `${formatUtc(fromMs)} → ${formatUtc(toMs)}`;
}
