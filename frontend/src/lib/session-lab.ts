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

// Servicio backend de sesiones de ingeniería (sesion autónoma del lado
// backend): el navegador crea la sesión, observa su estado con GET y la
// detiene con control stop. El avance autónomo lo conduce el backend con los
// eventos del transporte local; este cliente no conduce.
const ENGINEERING_BASE = "/api/v1/engineering-sessions";

export interface EngineeringDriveState {
  state: "running" | "stopped" | "idle";
  cause?: string | null;
  started_at_ms?: number | null;
  finished_at_ms?: number | null;
  events_processed?: number;
  transport_events?: number;
  cadence_ms?: number | null;
  runner?: "local_replay" | "market_stream" | null;
  session_id?: string | null;
  // --- transporte market_stream (live) --------------------------------
  market_url?: string | null;
  bars?: number | null;
  live_silence_ms?: number | null;
  watermark?: number | null;
  last_trigger?: Record<string, unknown> | null;
  last_gate?: {
    ok?: boolean;
    cause?: string | null;
    silence_ms?: number | null;
    live_silence_ms?: number | null;
    clock_ms?: number | null;
    evaluated_at_ms?: number | null;
    grid_gap?: unknown;
    note?: string | null;
  } | null;
  last_gap?: Record<string, unknown> | null;
  last_status?: Record<string, unknown> | null;
  evidence?: Record<string, { block?: unknown; received_at_ms?: number | null }>;
  stats?: Record<string, unknown>;
}

// Transporte de la sesión de ingeniería: "market_stream" consume los
// eventos del servicio de mercado existente (SSE, solo loopback);
// "local_replay" es el reproductor con cadencia (retained para pruebas).
export const ENGINEERING_TRANSPORT_MARKET_STREAM = "market_stream";
export const ENGINEERING_TRANSPORT_LOCAL_REPLAY = "local_replay";
export type EngineeringTransport =
  | typeof ENGINEERING_TRANSPORT_MARKET_STREAM
  | typeof ENGINEERING_TRANSPORT_LOCAL_REPLAY;

export type EngineeringControlAction =
  | "start" | "stop" | "step" | "exit" | "restart" | "stop_session"
  | "evaluate";

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
 * `readOnly=true` (sesión de ingeniería/replay) fuerza la opción de solo
 * lectura del backend (`read_only=1` → `--no-fetch`): cero upstream, ausencia
 * en caché devuelve motivo sin activar fetch. `readOnly=false` se reserva al
 * explorador normal, que conserva la adquisición bajo demanda con sus
 * presupuestos existentes (ledger compartido, pages <= 2).
 *
 * Pasa un rango amplio ([0, 9999999999999]) para cubrir todo lo almacenado,
 * independientemente del reloj de pared actual, ya que las velas cacheadas
 * pueden ser de fechas pasadas. Cuando se pasa `atMs` (reloj T de la sesion),
 * se sobreescribe `to_ms` para que el payload solo incluya velas conocidas en
 * T y los indicadores / contexto BTC se recalculen sobre ese prefijo.
 */
export async function fetchMarketSeries(
  symbol: string,
  interval: string,
  bars: number,
  atMs?: number | null,
  readOnly = true,
): Promise<MarketSeriesPayload | null> {
  const toParam = atMs != null ? `&to_ms=${atMs}` : "&to_ms=9999999999999";
  const readOnlyParam = readOnly ? "&read_only=1" : "";
  const url = `${API_BASE}?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&bars=${bars}&pages=1&from_ms=0${toParam}${readOnlyParam}`;
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
  /** Transporte de conducción (default backend: local_replay). */
  transport?: EngineeringTransport;
  /** Idempotencia del POST create en el backend (dedupe por request_id). */
  requestId?: string | null;
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

// ---------------------------------------------------------------------------
// Sesión autónoma en el backend (serviced engineering-session/v1)
// ---------------------------------------------------------------------------

export interface EngineeringApiResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
  detail?: string;
  status: number;
}

async function engineeringJson<T = unknown>(
  path: string, init?: RequestInit,
): Promise<EngineeringApiResult<T>> {
  let r: Response;
  try {
    r = await fetch(`${ENGINEERING_BASE}${path}`, {
      cache: "no-store",
      headers: { "Content-Type": "application/json" }, ...init,
    });
  } catch (exc: unknown) {
    return { ok: false, error: "BFF_UNREACHABLE", detail: String(exc), status: 0 };
  }
  let body: unknown;
  try { body = await r.json(); } catch { body = null; }
  if (!r.ok) {
    const err = (body as { error?: string; detail?: string }) ?? {};
    return {
      ok: false, error: err.error ?? String(r.status),
      detail: err.detail ?? String(body ?? ""), status: r.status,
    };
  }
  return { ok: true, data: body as T, status: r.status };
}

/** Crea la sesión en el backend (motor Python + transporte elegido). */
export async function createBackendSession(input: CreateSessionInput): Promise<
  EngineeringApiResult<{ session: PaperSessionState }>
> {
  return engineeringJson("", {
    method: "POST",
    body: JSON.stringify({
      config: input.config,
      candles: input.candles,
      context: input.context,
      transport: input.transport ?? ENGINEERING_TRANSPORT_LOCAL_REPLAY,
      request_id: input.requestId ?? null,
      hypothesis_id: input.config.hypothesis_id ?? null,
      hypothesis_version: input.config.hypothesis_version ?? null,
      rule_version: input.config.rule_version ?? null,
    }),
  });
}

/** Lee el estado público del backend (solo el prefijo revelado). */
export async function fetchBackendSession(
  sessionId: string,
): Promise<EngineeringApiResult<{ session: PaperSessionState;
  drive?: EngineeringDriveState }>> {
  return engineeringJson(`/${encodeURIComponent(sessionId)}`);
}

/** Control explícito del navegador: start/stop/paso manual/exit/etc. */
export async function controlBackendSession(
  sessionId: string,
  action: EngineeringControlAction,
  opts?: { expectedRevision?: number | null; requestId?: string | null },
): Promise<EngineeringApiResult<{ session: PaperSessionState;
  drive?: EngineeringDriveState }>> {
  return engineeringJson(`/${encodeURIComponent(sessionId)}/control`, {
    method: "POST",
    body: JSON.stringify({
      action,
      expected_revision: opts?.expectedRevision ?? null,
      request_id: opts?.requestId ?? null,
    }),
  });
}

// ---------------------------------------------------------------------------
// SERVICIO de ingeniería: estado y arranque explícito (control del operador)
// ---------------------------------------------------------------------------

export interface EngineeringServiceInfo {
  state: "down" | "unidentified" | "ready";
  service?: string | null;
  engine_version?: string | null;
  pid?: number | null;
  port?: number | null;
  cadence_ms?: number | null;
  sessions_dir?: string | null;
  detail?: string | null;
}

/** Estado del servicio (GET puro: consulta; NUNCA arranca nada). */
export async function fetchEngineeringService(): Promise<
  EngineeringApiResult<EngineeringServiceInfo>
> {
  return engineeringJson("/service");
}

/**
 * Arranque explícito del servicio canónico del proyecto vía BFF (POST con
 * guardia de origen; readiness con límite; identidad verificada). Idempotente
 * si el servicio ya está listo y verificado.
 */
export async function startEngineeringService(): Promise<
  EngineeringApiResult<{ pid?: number; port?: number; already?: boolean }>
> {
  return engineeringJson("/service", {
    method: "POST",
    body: JSON.stringify({action: "start"}),
  });
}
