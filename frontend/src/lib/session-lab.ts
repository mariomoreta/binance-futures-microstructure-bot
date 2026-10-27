// Sesión de ingeniería — transporte local.
//
// Conecta el dashboard con los servicios existentes SIN crear un gestor paralelo:
//  * Datos: GET /api/v1/market-series (market-explorer sobre caché local,
//    client=None, 0 peticiones upstream). Fuente: LOCAL SIMULADA.
//  * Indicadores/contexto BTC: bloques versionados market-indicators/v1 y
//    market-btc-context/v1 que el backend ya incluye en el payload de series.
//  * Flujo: sin eventos aggTrade en cobertura local -> market-flow/v1 en
//    NO_COVERAGE (se declara UNKNOWN, nunca se inventan valores).
//  * Motor/Posición/P&L: scripts/paper_lab_session.py +
//    src/microstructure_probe/paper_lab_engine.py (canal dashboard -> BFF ->
//    Python existente).
//
// El navegador solo solicita acciones acotadas y presenta estados recibidos.
// Nunca envía decisiones ni estado económico como autoridad.

import type {
  PaperCandle,
  PaperSessionConfig,
  PaperSessionState,
} from "@/lib/paper-lab-live";

const API_BASE = "/api/v1/market-series";
const PAPER_SESSIONS_BASE = "/api/v1/paper-lab/sessions";

// Regla de ingeniería explícita, versionada y separada de cualquier
// estrategia aprobada. Caso de ingeniería, no selección por rentabilidad.
export const ENGINEERING_RULE_VERSION = "ENGINEERING-MINA-1M-v1";
export const ENGINEERING_HYPOTHESIS_ID = "ENG-MINA-01";
export const ENGINEERING_HYPOTHESIS_VERSION = "v1";

export interface MarketSeriesPayload {
  candles: Array<{
    open_time_ms: number;
    close_time_ms: number | null;
    open: string | number | null;
    high: string | number | null;
    low: string | number | null;
    close: string | number | null;
    base_volume: string | number | null;
    closed: boolean;
  }>;
  indicators: unknown;
  context_btc: unknown;
  symbol: string;
  interval: string;
  observed?: { start_ms: number | null; end_ms: number | null };
  coverage?: unknown;
  freshness?: unknown;
  fetch?: unknown;
}

type ApiResult<T> = {
  ok: boolean;
  data?: T;
  error?: string;
  detail?: string;
  status: number;
};

async function fetchJson<T = unknown>(path: string): Promise<ApiResult<T>> {
  const r = await fetch(path, { cache: "no-store", headers: { Accept: "application/json" } });
  let body: unknown;
  try {
    body = await r.json();
  } catch {
    body = null;
  }
  if (!r.ok) {
    return { ok: false, error: String(r.status), detail: String(body), status: r.status };
  }
  return { ok: true, data: body as T, status: r.status };
}

/** Trae velas (caché local, 0 upstream) para un símbolo/intervalo.
 *
 * Pasa un rango amplio ([0, 9999999999999]) para cubrir todo lo almacenado,
 * independientemente del reloj de pared actual, ya que las velas cacheadas
 * pueden ser de fechas pasadas. Cuando se pasa `atMs` (reloj T de la sesion),
 * se sobreescribe `to_ms` para que el payload solo incluya velas conocidas en
 * T y los indicadores / contexto BTC se recalculen sobre ese prefijo. Nunca
 * se consulta Binance publico (--no-fetch).
 */
export async function fetchMarketSeries(
  symbol: string,
  interval: string,
  bars: number,
  atMs?: number | null,
): Promise<MarketSeriesPayload | null> {
  const toParam = atMs != null ? `&to_ms=${atMs}` : "&to_ms=9999999999999";
  const url = `${API_BASE}?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&bars=${bars}&pages=1&from_ms=0${toParam}`;
  const r = await fetchJson<MarketSeriesPayload>(url);
  if (!r.ok || !r.data) return null;
  return r.data;
}

function toMs(value: string | number | null): number | null {
  if (value === null || value === undefined) return null;
  const n = typeof value === "string" ? Number(value) : value;
  return Number.isFinite(n) ? n : null;
}

/** Convierte velas del mercado en PaperCandle (fuente local simulada). */
export function marketCandlesToPaper(
  rows: MarketSeriesPayload["candles"],
  receivedAtMs: number,
): PaperCandle[] {
  // El CLI del BFF parsea close_time_ms con int(); las velas sin cierre
  // confirmado (close_time_ms nulo) no pueden viajar por linea de comandos y
  // se descartan aqui (sin tocar archivos canónicos).
  return rows
    .filter(
      (c) =>
        toMs(c.open_time_ms) != null && toMs(c.close_time_ms) != null &&
        toMs(c.open) != null && toMs(c.high) != null &&
        toMs(c.low) != null && toMs(c.close) != null,
    )
    .map((c) => ({
      open_time_ms: toMs(c.open_time_ms)!,
      open: toMs(c.open)!,
      high: toMs(c.high),
      low: toMs(c.low),
      close: toMs(c.close),
      close_time_ms: toMs(c.close_time_ms)!,
      available_at: toMs(c.open_time_ms),
      received_at: receivedAtMs,
    }));
}

/** Divide velas en contexto (primeras N) y ventana de operación (el resto). */
export function splitContextAndOperation(
  all: PaperCandle[],
  contextCount: number,
): { context: PaperCandle[]; operation: PaperCandle[] } {
  const context = all.slice(0, contextCount);
  const operation = all.slice(contextCount);
  return { context, operation };
}

/**
 * Construye la configuración de sesión de ingeniería.
 *
 * entry_px = cierre de la última vela de contexto (precio conocido en T).
 * La señal RULE-CAUSAL-V1 se evalúa sobre ese cierre: LONG entra si close >=
 * entry_px. El stop se deriva de entry_px × (1 - stop_distance_pct/100) y
 * el motor lo confirma como stop efectivo tras el fill (run_backtest).
 */
export function buildEngineeringConfig({
  symbol,
  interval,
  entryPx,
  stopDistancePct = 1.5,
  notionalUsdt = 1000,
  horizonMs = 60 * 60 * 1000,
  feeBps = 5,
  spreadBps = 1,
  slippageBps = 2,
}: {
  symbol: string;
  interval: string;
  entryPx: number;
  stopDistancePct?: number;
  notionalUsdt?: number;
  horizonMs?: number;
  feeBps?: number;
  spreadBps?: number;
  slippageBps?: number;
}): PaperSessionConfig {
  const stopPx = entryPx * (1 - stopDistancePct / 100);
  return {
    symbol,
    interval,
    direction: "LONG",
    notional_usdt: notionalUsdt,
    entry_px: entryPx,
    stop_px: stopPx,
    stop_distance_pct: stopDistancePct,
    horizon_ms: horizonMs,
    fee_bps: feeBps,
    spread_bps: spreadBps,
    slippage_bps: slippageBps,
    hypothesis_id: ENGINEERING_HYPOTHESIS_ID,
    hypothesis_version: ENGINEERING_HYPOTHESIS_VERSION,
    rule_version: ENGINEERING_RULE_VERSION,
  };
}

/** Reloj de evaluación T: cierre de la última vela de contexto. */
export function contextClock(context: PaperCandle[]): number | null {
  const last = context[context.length - 1];
  if (!last) return null;
  return last.close_time_ms ?? last.open_time_ms;
}

/** Último cierre plenamente conocido de la ventana de contexto. */
export function lastContextClose(context: PaperCandle[]): number | null {
  const last = context[context.length - 1];
  return last && last.close != null ? last.close : null;
}

export type CreateSessionInput = {
  config: PaperSessionConfig;
  candles: PaperCandle[];
  context: PaperCandle[];
};

/** Crea una sesión de ingeniería vía BFF (POST /api/v1/paper-lab/sessions). */
export async function createEngineeringSession(
  input: CreateSessionInput,
): Promise<{ ok: boolean; session?: PaperSessionState; error?: string; detail?: string; status?: number }> {
  const r = await fetch(PAPER_SESSIONS_BASE, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      config: input.config,
      candles: input.candles,
      context: input.context,
      hypothesis_id: input.config.hypothesis_id ?? null,
      hypothesis_version: input.config.hypothesis_version ?? null,
      rule_version: input.config.rule_version ?? null,
    }),
  });
  let body: unknown;
  try { body = await r.json(); } catch { body = null; }
  if (!r.ok || !body) {
    return { ok: false, error: String(r.status), detail: String(body), status: r.status };
  }
  const data = body as { session?: PaperSessionState };
  return { ok: true, session: data.session!, status: r.status };
}
