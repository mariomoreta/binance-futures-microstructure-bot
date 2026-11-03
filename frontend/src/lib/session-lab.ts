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

// Paso de rejilla (ms) por intervalo soportado. Se usa para construir la
// ventana explícita de velas CERRADAS que solicita fetchMarketSeries.
export const INTERVAL_STEP_MS: Record<string, number> = {
  "1m": 60_000, "5m": 300_000, "15m": 900_000,
  "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
};

/** Trae velas para un símbolo/intervalo.
 *
 * `readOnly=true` (sesión de ingeniería/replay) fuerza la opción de solo
 * lectura del backend (`read_only=1` → `--no-fetch`): cero upstream, ausencia
 * en caché devuelve motivo sin activar fetch. `readOnly=false` habilita la
 * adquisición bajo demanda del backend con presupuesto existente
 * (ledger compartido, pages <= 2, 30 req/min).
 *
 * `pages` (máx. 2) y `pageLimit` (máx. 1000) controlan cuántas páginas
 * solicita el backend para cubrir el rango. Cada página devuelve como
 * máximo `pageLimit` velas.
 *
 * Se pide siempre una VENTANA EXPLÍCITA DE VELAS CERRADA: `from_ms` y
 * `to_ms` se calculan sobre el reloj (o `atMs` si se pasa) de modo que el
 * rango nunca alcance velas futuras. Sin `atMs`, `to_ms` es la apertura de
 * la última vela cuya cierre es <= ahora (close_time_ms conocido), y
 * `from_ms = to_ms - (bars - 1) * paso`. Nunca se usa `from_ms=0` ni
 * `to_ms=9999999999999`. La adquisición pública permanece bloqueada salvo que
 * el llamador pase `readOnly=false` (activación expresa); el backend aplica
 * el presupuesto compartido (ledger, reserva antes del transporte).
 */
export async function fetchMarketSeries(
  symbol: string,
  interval: string,
  bars: number,
  atMs?: number | null,
  readOnly = true,
  pages = 1,
  pageLimit = 300,
): Promise<MarketSeriesPayload | null> {
  const stepMs = INTERVAL_STEP_MS[interval] ?? 60_000;
  const nBars = Math.max(1, Math.min(bars, 1000));
  const nowMs = Date.now();
  // Apertura de la última vela CERRADA conocida: su cierre <= ahora.
  const lastClosedOpen = Math.floor(nowMs / stepMs) * stepMs - stepMs;
  const toMs = atMs != null ? Math.floor(atMs) : lastClosedOpen;
  const fromMs = toMs - (nBars - 1) * stepMs;
  const readOnlyParam = readOnly ? "&read_only=1" : "";
  const url = `${API_BASE}?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&bars=${nBars}&pages=${pages}&page_limit=${pageLimit}&from_ms=${fromMs}&to_ms=${toMs}${readOnlyParam}`;
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
  /** Primera frontera de operación esperada (open_time_ms). El servicio la
    usa para fijar deliver_from_ms y no entregar velas ya cubiertas por el
    contexto. Si se omite, deliver_from_ms parte desde 0. */
  fromMs?: number | null;
  /** Última frontera de operación esperada (open_time_ms). Acota el rango
    del snapshot/stream. */
  toMs?: number | null;
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
      from_ms: input.fromMs ?? null,
      to_ms: input.toMs ?? null,
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
  market_url?: string | null;
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

// --- Demostración local (datos simulados; NO Binance) ------------------------

export interface EngineeringDemoSource {
  url: string | null;
  available: boolean;
  service: string | null;
  detail: string | null;
}

export interface EngineeringDemoStatus {
  ok: boolean;
  engineering: EngineeringServiceInfo;
  source: EngineeringDemoSource;
  demo: {
    present: boolean;
    active: boolean;
    expired: boolean;
    started_at_ms: number | null;
    max_runtime_s: number | null;
    stopped_at_ms: number | null;
    producer: { pid: number | null; port: number | null; alive: boolean };
    market: { pid: number | null; port: number | null; health_ok: boolean };
  };
  error?: string | null;
  detail?: string | null;
}

/** Estado de la demostración y de la fuente (GET puro: consulta). */
export async function fetchEngineeringDemo(): Promise<
  EngineeringApiResult<EngineeringDemoStatus>
> {
  return engineeringJson("/demo");
}

/**
 * Inicia la demostración local: recursos propios identificados
 * (productor WS loopback + servicio de mercado --transport local, acotados
 * en duración) + servicio de ingeniería verificado. NUNCA toca el servicio
 * preexistente 8792 ni habilita transporte público.
 */
export async function startEngineeringDemo(): Promise<
  EngineeringApiResult<{
    producer?: { pid: number; port: number };
    market?: { pid: number; port: number };
  }>
> {
  return engineeringJson("/demo", {
    method: "POST",
    body: JSON.stringify({action: "start"}),
  });
}

/** Detiene la demostración (solo recursos propios; sesiones intactas). */
export async function stopEngineeringDemo(): Promise<
  EngineeringApiResult<{ already?: boolean }>
> {
  return engineeringJson("/demo", {
    method: "POST",
    body: JSON.stringify({action: "stop"}),
  });
}

// --- Aceptación pública (Binance WS) -----------------------------------------

export interface PublicRunState {
  runId: string | null;
  startedAtMs: number | null;
  httpAttempts: number;
  active: boolean;
  deadlineExceeded: boolean;
  state?: string | null;
  cause?: string | null;
  error?: string | null;
  detail?: string | null;
  service?: { pid?: number | null; port?: number | null; sessions_dir?: string | null } | null;
}

/** Inicia la aceptación pública: genera run_id propio (o reutiliza el
 *  persistido de la misma corrida), arranca el servicio de ingeniería con
 *  --clock-source public y ese run_id, y establece el presupuesto de la
 *  corrida. Solo observación y simulación paper, sin órdenes reales.
 */
export async function startPublicRun(opts?: {
  runId?: string | null;
  symbols?: string;
  interval?: string;
}): Promise<
  EngineeringApiResult<{
    runId: string | null;
    startedAtMs: number | null;
    httpAttempts: number;
    deadlineExceeded: boolean;
    state?: string | null;
    cause?: string | null;
    service?: { pid?: number | null; port?: number | null; sessions_dir?: string | null } | null;
  }>
> {
  return engineeringJson("/public", {
    method: "POST",
    body: JSON.stringify({
      action: "start",
      run_id: opts?.runId ?? null,
      symbols: opts?.symbols ?? "MINAUSDT,BTCUSDT",
      interval: opts?.interval ?? "1m",
    }),
  });
}

/** Detiene la aceptación pública (solo recursos propios; sesiones intactas). */
export async function stopPublicRun(runId: string | null): Promise<
  EngineeringApiResult<{ already?: boolean; service_stopped?: boolean }>
> {
  return engineeringJson("/public", {
    method: "POST",
    body: JSON.stringify({action: "stop", run_id: runId ?? null}),
  });
}
