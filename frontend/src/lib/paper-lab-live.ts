// Paper Lab — cliente de API para sesiones de ingeniería.
// Toda la lógica de simulación vive en el backend Python
// (src/microstructure_probe/paper_lab_engine.py + scripts/paper_lab_session.py).
// Este módulo expone solo tipos compartidos y funciones de llamada a la API.
// No toca el monitor, no inicia/detiene nada, no ejecuta ordenes.

export type PaperDirection = "LONG" | "SHORT";

export type PaperSessionStatus =
  | "sin_iniciar"
  | "evaluando"
  | "en_espera"
  | "abierta"
  | "cerrada"
  | "detenida";

export type PaperCandidateDecision =
  | "VIGILANDO"
  | "SIN_ENTRADA"
  | "DESCARTADO"
  | "ENTRADA_SIMULADA";

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
  entry_fees: number;      // ejecutados
  exit_fees: number;       // ejecutados (0 si no hay salida)
  entry_spread_slip: number;  // ejecutados
  exit_spread_slip: number;   // ejecutados (0 si no hay salida)
  funding: number | null;  // devengado (null = UNKNOWN sin calendario)
  friction: number;        // total ejecutado
  entry_fees_executed: number;
  exit_fees_executed: number;
  entry_spread_slip_executed: number;
  exit_spread_slip_executed: number;
  exit_fees_estimated: number;
  exit_spread_slip_estimated: number;
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
  fees: number;           // ejecutados
  spread_slip: number;    // ejecutados
  funding: number | null; // devengado (null = UNKNOWN)
  friction: number;       // total ejecutado
  net_pnl: number;
  realized_net: number | null;
  open_at_end: boolean;
  entry_fees_executed: number;
  exit_fees_executed: number;
  entry_spread_slip_executed: number;
  exit_spread_slip_executed: number;
  exit_fees_estimated: number;
  exit_spread_slip_estimated: number;
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
  hypothesis_id?: string | null;
  hypothesis_version?: string | null;
  rule_version?: string | null;
  decision?: PaperCandidateDecision | null;
  decision_reason?: string | null;
  decision_evidence?: Record<string, unknown> | null;
}

export interface PaperSessionState {
  session_id: string;
  created_at_ms: number;
  updated_at_ms: number;
  status: PaperSessionStatus;
  revision: number;
  config: PaperSessionConfig;
  candles: PaperCandle[];
  context_candles: PaperCandle[];
  cursor: number;
  position: PaperPosition;
  costs: PaperCosts;
  events: PaperEvent[];
  result: PaperTradeResult | null;
  clock_ms: number | null;
  config_hash: string | null;
  input_hash: string | null;
  engine_version: string;
  limitations: string[];
  authoritative: Record<string, unknown> | null;
  // El backend informa si se puede avanzar un paso (sin revelar datos
  // futuros). Cuando falta (tests/estado derivado local), se infiere abajo.
  can_step?: boolean;
}

export interface PaperSessionSummary {
  session_id: string;
  status: PaperSessionStatus;
  revision: number;
  created_at_ms: number;
  updated_at_ms: number;
  symbol: string;
  direction: string;
  config_hash: string | null;
  has_result: boolean;
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
  canDecide: boolean;
}

// --- Helpers de formato (solo render) -------------------------------------

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

// --- Vista derivada para la UI --------------------------------------------

export function sessionView(state: PaperSessionState): PaperSessionView {
  const {config, candles, cursor, position, costs, events, result,
    clock_ms, status} = state;
  const n = candles.length;
  const open = position.open === true;
  const finished = status === "cerrada" || status === "detenida";
  const decided = state.config.decision != null;
  // En cerrado con posición abierta (open_at_end) no se puede salir ni entrar.
  const closedWithOpenPosition = finished && open && result?.open_at_end;
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
    canEnter: status === "en_espera" && !open && decided && !finished,
    // Se puede avanzar mientras se vigila (decision tomada, sin entrada) o se
    // espera entrada, y con posicion abierta. El backend informa can_step sin
    // revelar datos futuros; candles.length de la respuesta filtrada no se usa
    // como prueba de que el scenario interno termino.
    canStep:
      (state as { can_step?: boolean }).can_step !== undefined
        ? Boolean((state as { can_step?: boolean }).can_step) &&
          (decided || open) && !closedWithOpenPosition
        : (decided || open) && cursor < n && !finished && !closedWithOpenPosition,
    canExit: open && !finished && !closedWithOpenPosition,
    canRestart: true,
    canStop: status === "abierta" || status === "en_espera",
    canDecide: status === "sin_iniciar" || status === "evaluando",
  };
}

// --- Cliente de API -------------------------------------------------------

const API_BASE = "/api/v1/paper-lab/sessions";

type ApiResult<T> = {
  ok: boolean;
  data?: T;
  error?: string;
  detail?: string;
  status: number;
};

async function apiJson<T = unknown>(path: string, opts?: RequestInit):
  Promise<ApiResult<T>> {
  const r = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: {"Content-Type": "application/json"},
    ...opts,
  });
  let body: unknown;
  try {
    body = await r.json();
  } catch {
    body = null;
  }
  if (!r.ok) {
    return {ok: false, data: undefined,
      error: (body as {error?: string})?.error,
      detail: (body as {detail?: string})?.detail,
      status: r.status};
  }
  return {ok: true, data: body as T, status: r.status};
}

export async function listSessionsApi(): Promise<ApiResult<PaperSessionSummary[]>> {
  const r = await apiJson("");
  if (!r.ok) {
    return {ok: false, data: undefined, error: r.error, detail: r.detail, status: r.status};
  }
  const data = r.data as {sessions?: unknown};
  return {
    ok: true,
    data: Array.isArray(data.sessions) ? (data.sessions as PaperSessionSummary[]) : [],
    status: r.status,
  };
}

export async function createSessionApi(
  config: PaperSessionConfig,
  candles: PaperCandle[],
  contextCandles: PaperCandle[] = [],
): Promise<ApiResult<PaperSessionState>> {
  const r = await apiJson<{session?: PaperSessionState}>("", {
    method: "POST",
    body: JSON.stringify({config, candles, context: contextCandles}),
  });
  if (!r.ok || !r.data) {
    return {ok: false, data: undefined, error: r.error, detail: r.detail, status: r.status};
  }
  return {ok: true, data: r.data.session!, status: r.status};
}

export async function evaluateSessionApi(
  sessionId: string,
  hypothesisId?: string | null,
  hypothesisVersion?: string | null,
  ruleVersion?: string | null,
  atMs?: number | null,
  requestId?: string | null,
  expectedRevision?: number | null,
): Promise<ApiResult<PaperSessionState>> {
  const r = await apiJson<{session?: PaperSessionState}>(`/${encodeURIComponent(sessionId)}/evaluate`,
    {
      method: "POST",
      body: JSON.stringify({
        hypothesis_id: hypothesisId ?? null,
        hypothesis_version: hypothesisVersion ?? null,
        rule_version: ruleVersion ?? null,
        at_ms: atMs ?? null,
        request_id: requestId ?? null,
        expected_revision: expectedRevision ?? null,
      }),
    });
  if (!r.ok || !r.data) {
    return {ok: false, data: undefined, error: r.error, detail: r.detail, status: r.status};
  }
  return {ok: true, data: r.data.session!, status: r.status};
}

export async function getSessionApi(sessionId: string):
  Promise<ApiResult<PaperSessionState>> {
  const r = await apiJson<{session?: PaperSessionState}>(`/${encodeURIComponent(sessionId)}`);
  if (!r.ok || !r.data) {
    return {ok: false, data: undefined, error: r.error, detail: r.detail, status: r.status};
  }
  return {ok: true, data: r.data.session!, status: r.status};
}

export async function stepSessionApi(
  sessionId: string,
  requestId?: string | null,
  expectedRevision?: number | null,
): Promise<ApiResult<PaperSessionState>> {
  const r = await apiJson<{session?: PaperSessionState}>(`/${encodeURIComponent(sessionId)}/step`,
    {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId ?? null,
        expected_revision: expectedRevision ?? null,
      }),
    });
  if (!r.ok || !r.data) {
    return {ok: false, data: undefined, error: r.error, detail: r.detail, status: r.status};
  }
  return {ok: true, data: r.data.session!, status: r.status};
}

export async function exitSessionApi(
  sessionId: string,
  requestId?: string | null,
  expectedRevision?: number | null,
): Promise<ApiResult<PaperSessionState>> {
  const r = await apiJson<{session?: PaperSessionState}>(`/${encodeURIComponent(sessionId)}/exit`,
    {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId ?? null,
        expected_revision: expectedRevision ?? null,
      }),
    });
  if (!r.ok || !r.data) {
    return {ok: false, data: undefined, error: r.error, detail: r.detail, status: r.status};
  }
  return {ok: true, data: r.data.session!, status: r.status};
}

export async function restartSessionApi(
  sessionId: string,
  requestId?: string | null,
  expectedRevision?: number | null,
): Promise<ApiResult<PaperSessionState>> {
  const r = await apiJson<{session?: PaperSessionState}>(`/${encodeURIComponent(sessionId)}/restart`,
    {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId ?? null,
        expected_revision: expectedRevision ?? null,
      }),
    });
  if (!r.ok || !r.data) {
    return {ok: false, data: undefined, error: r.error, detail: r.detail, status: r.status};
  }
  return {ok: true, data: r.data.session!, status: r.status};
}

export async function stopSessionApi(
  sessionId: string,
  requestId?: string | null,
  expectedRevision?: number | null,
): Promise<ApiResult<PaperSessionState>> {
  const r = await apiJson<{session?: PaperSessionState}>(`/${encodeURIComponent(sessionId)}/stop`,
    {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId ?? null,
        expected_revision: expectedRevision ?? null,
      }),
    });
  if (!r.ok || !r.data) {
    return {ok: false, data: undefined, error: r.error, detail: r.detail, status: r.status};
  }
  return {ok: true, data: r.data.session!, status: r.status};
}
