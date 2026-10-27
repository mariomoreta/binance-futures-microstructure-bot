// @vitest-environment jsdom
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import type {
  PaperPosition, PaperSessionState, PaperTradeResult,
} from "@/lib/paper-lab-live";
import EngineeringSession from "@/components/session-lab/EngineeringSession";

const SESSION_ID_STORAGE_KEY = "paper-lab-sesion-ingenieria-id";

// vi.hoisted evita la zona muerta temporal: las fábricas de vi.mock se izan
// al tope del archivo y necesitan los dobles ya inicializados.
const mocks = vi.hoisted(() => ({
  fetchMarketSeries: vi.fn(),
  createEngineeringSession: vi.fn(),
  getSessionApi: vi.fn(),
  stepSessionApi: vi.fn(),
  exitSessionApi: vi.fn(),
  restartSessionApi: vi.fn(),
  evaluateSessionApi: vi.fn(),
}));

vi.mock("@/lib/session-lab", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/session-lab")>();
  return {
    ...actual,
    fetchMarketSeries: mocks.fetchMarketSeries,
    createEngineeringSession: mocks.createEngineeringSession,
  };
});

vi.mock("@/lib/paper-lab-live", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/paper-lab-live")>();
  return {
    ...actual,
    getSessionApi: mocks.getSessionApi,
    stepSessionApi: mocks.stepSessionApi,
    exitSessionApi: mocks.exitSessionApi,
    restartSessionApi: mocks.restartSessionApi,
    evaluateSessionApi: mocks.evaluateSessionApi,
  };
});

// PaperChart usa Lightweight Charts (canvas); se dobla en el test de unidad.
vi.mock("@/components/paper-lab-live/PaperChart", () => ({
  PaperChart: () => <div data-testid="stub-paper-chart" />,
}));

const INTERVAL_MS = 5 * 60 * 1000; // 5m
const T1 = 1_790_000_000_000;
const T2 = T1 + INTERVAL_MS;
const T3 = T2 + INTERVAL_MS;

function mkCandles(count: number, startMs: number): any[] {
  return Array.from({length: count}, (_, i) => {
    const ot = startMs + i * INTERVAL_MS;
    return {
      open_time_ms: ot, close_time_ms: ot + INTERVAL_MS - 1,
      open: 100 + i, high: 101 + i, low: 99 + i, close: 100 + i,
      base_volume: 10, closed: true,
    };
  });
}

function seriesPayload(candles: any[]) {
  return {
    candles: candles.map((c) => ({...c, closed: true})),
    indicators: {ret: 1},
    context_btc: {ret_btc_bps_5: 1},
    symbol: "BTCUSDT", interval: "5m",
    coverage: {state: "COVERED"},
  };
}

function mkSession(overrides: Partial<PaperSessionState> = {}): PaperSessionState {
  const base: PaperSessionState = {
    session_id: "sess-123",
    created_at_ms: 1788904800000,
    updated_at_ms: 1788904800000,
    status: "en_espera",
    revision: 1,
    config: {
      symbol: "BTCUSDT", interval: "5m", direction: "LONG",
      notional_usdt: 1000, entry_px: 100, stop_px: 95,
      stop_distance_pct: 5, horizon_ms: 3 * 60 * 60 * 1000,
      fee_bps: 5, spread_bps: 1, slippage_bps: 2,
      decision: "ENTRADA_SIMULADA", decision_reason: "candidato valido",
      rule_version: "ENGINEERING-MINA-1M-v1",
    },
    candles: [], context_candles: [], cursor: 0,
    position: {
      open: false, direction: null, entry_px: null, entry_qty: null,
      entry_cost: null, entry_ms: null, stop_px: null, mark_px: null,
      mark_ms: null, unrealized_gross: null, unrealized_net: null,
      mfe_pct: null, mae_pct: null,
    },
    costs: {
      fee_bps: 5, spread_bps: 1, entry_fees: 0, exit_fees: 0,
      entry_spread_slip: 0, exit_spread_slip: 0, funding: null,
      friction: 0, entry_fees_executed: 0, exit_fees_executed: 0,
      entry_spread_slip_executed: 0, exit_spread_slip_executed: 0,
      exit_fees_estimated: 0, exit_spread_slip_estimated: 0,
    },
    events: [], result: null,
    clock_ms: T1,
    config_hash: "abc", input_hash: "def",
    engine_version: "paper-lab-engine/v1",
    limitations: [], authoritative: null,
  };
  return {...base, ...overrides};
}

describe("sesión de ingeniería — recuperación y reloj T", () => {
  beforeEach(() => {
    mocks.fetchMarketSeries.mockResolvedValue(
      seriesPayload(mkCandles(40, T1 - 40 * INTERVAL_MS)),
    );
    mocks.getSessionApi.mockResolvedValue({ok: true, data: mkSession()});
    mocks.stepSessionApi.mockResolvedValue({ok: true, data: mkSession({clock_ms: T2})});
    mocks.exitSessionApi.mockResolvedValue({ok: true, data: mkSession({clock_ms: T3, status: "cerrada"})});
    mocks.restartSessionApi.mockResolvedValue({ok: true, data: mkSession({clock_ms: T1, status: "en_espera"})});
    mocks.evaluateSessionApi.mockResolvedValue({ok: true, data: mkSession()});
    localStorage.removeItem(SESSION_ID_STORAGE_KEY);
  });
  afterEach(() => {
    localStorage.removeItem(SESSION_ID_STORAGE_KEY);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("recupera usando símbolo/intervalo del config de la sesión, no los defaults del componente", async () => {
    localStorage.setItem(SESSION_ID_STORAGE_KEY, "sess-123");
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    // La recuperación se programa con setTimeout(0); esperar la llamada a fetch.
    await waitFor(() => expect(mocks.fetchMarketSeries).toHaveBeenCalled(), {timeout: 5000});
    const calls = mocks.fetchMarketSeries.mock.calls;
    const last = calls[calls.length - 1]!;
    // Identidad autoritativa del config (BTCUSDT/5m), no los props por defecto (MINAUSDT/1m).
    expect(last[0]).toBe("BTCUSDT");
    expect(last[1]).toBe("5m");
    expect(last[3]).toBe(T1); // reloj T de la sesión recuperada
    expect(last[4]).toBe(true); // fuente solo lectura (--no-fetch)
    // Nunca se usa el símbolo/intervalo por defecto del componente para la recuperación.
    expect(mocks.fetchMarketSeries).not.toHaveBeenCalledWith(
      "MINAUSDT", "1m", expect.any(Number), expect.any(Number), true,
    );
  });

  it("Entrar avanza el reloj T: recarga indicadores/contexto para el nuevo T", async () => {
    localStorage.setItem(SESSION_ID_STORAGE_KEY, "sess-123");
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() => expect(mocks.fetchMarketSeries).toHaveBeenCalledWith("BTCUSDT", "5m", 90, T1, true));

    fireEvent.click(screen.getByRole("button", {name: "Entrar"}));
    await waitFor(() => expect(mocks.stepSessionApi).toHaveBeenCalledTimes(1));
    // Después de Entrar, el contexto se reconstruye para el nuevo reloj T2.
    await waitFor(() => expect(mocks.fetchMarketSeries).toHaveBeenLastCalledWith("BTCUSDT", "5m", 90, T2, true));
  });

  it("Salir recarga el contexto para el reloj T de salida", async () => {
    localStorage.setItem(SESSION_ID_STORAGE_KEY, "sess-123");
    // Posición abierta para que "Cerrar posicion" esté habilitada.
    const abierta = mkSession({status: "abierta", clock_ms: T1, position: {...mkSession().position, open: true}});
    mocks.getSessionApi.mockResolvedValueOnce({ok: true, data: abierta});
    mocks.exitSessionApi.mockResolvedValueOnce({ok: true, data: mkSession({clock_ms: T3, status: "cerrada"})});
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() => expect(mocks.fetchMarketSeries).toHaveBeenCalledWith("BTCUSDT", "5m", 90, T1, true));

    fireEvent.click(screen.getByRole("button", {name: "Cerrar posicion"}));
    await waitFor(() => expect(mocks.exitSessionApi).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mocks.fetchMarketSeries).toHaveBeenLastCalledWith("BTCUSDT", "5m", 90, T3, true));
  });

  it("Reinicio reestablece el reloj T y recarga el contexto", async () => {
    localStorage.setItem(SESSION_ID_STORAGE_KEY, "sess-123");
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() => expect(mocks.fetchMarketSeries).toHaveBeenCalledWith("BTCUSDT", "5m", 90, T1, true));

    // Reinicio con reloj distinto al actual: debe recargar el contexto del nuevo T.
    mocks.restartSessionApi.mockResolvedValueOnce({ok: true, data: mkSession({clock_ms: T2, status: "en_espera"})});
    fireEvent.click(screen.getByRole("button", {name: "Reiniciar"}));
    await waitFor(() => expect(mocks.restartSessionApi).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mocks.fetchMarketSeries).toHaveBeenLastCalledWith("BTCUSDT", "5m", 90, T2, true));
  });

  it("mantiene fuente solo lectura sin reintentos (UNKNOWN del flujo sin cobertura)", async () => {
    localStorage.setItem(SESSION_ID_STORAGE_KEY, "sess-123");
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() => expect(mocks.fetchMarketSeries).toHaveBeenCalled());
    // Carga única, read_only=true, sin reintento ni fetch encadenado.
    expect(mocks.fetchMarketSeries).toHaveBeenCalledTimes(1);
    expect(mocks.fetchMarketSeries.mock.calls[0]![4]).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Modo autónomo: un solo "Iniciar sesion" conduce entrada pendiente → fill →
// gestión → cierre sin pulsar "Entrar" ni "Paso a paso" (A); la abstención
// nunca abre el bucle (B); el fin del transporte local detiene la autonomía
// con causa visible y sin entrada ni cierre inventado (C).

function mkResult(overrides: Partial<PaperTradeResult> = {}): PaperTradeResult {
  return {
    symbol: "BTCUSDT", direction: "LONG",
    entry_px: 100, exit_px: 101.2,
    entry_ms: T2, exit_ms: T3,
    exit_reason: "horizon", exit_executed: true,
    qty: 10, filled_cost: 1000,
    gross_pnl: 12, fees: 1, spread_slip: 0.4,
    funding: null, friction: 1.4, net_pnl: 10.6, realized_net: 10.6,
    open_at_end: false,
    entry_fees_executed: 0.5, exit_fees_executed: 0.5,
    entry_spread_slip_executed: 0.2, exit_spread_slip_executed: 0.2,
    exit_fees_estimated: 0, exit_spread_slip_estimated: 0,
    ...overrides,
  };
}

function mkPosition(overrides: Partial<PaperPosition> = {}): PaperPosition {
  return {
    open: false, direction: null, entry_px: null, entry_qty: null,
    entry_cost: null, entry_ms: null, stop_px: null, mark_px: null,
    mark_ms: null, unrealized_gross: null, unrealized_net: null,
    mfe_pct: null, mae_pct: null,
    ...overrides,
  };
}

// waitFor no convive con los timers falsos del bucle autónomo: se avanza el
// reloj simulado en incrementos pequeños (dentro de act) hasta cumplir la
// condición o agotar un tope generoso.
async function advanceUntil(cond: () => boolean, maxMs = 30000): Promise<void> {
  for (let elapsed = 0; elapsed <= maxMs; elapsed += 100) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    if (cond()) return;
  }
  throw new Error("advanceUntil: condición no alcanzada (timeout simulado)");
}

describe("sesión de ingeniería — modo autónomo (sin Entrar ni Paso a paso)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mocks.fetchMarketSeries.mockResolvedValue(
      seriesPayload(mkCandles(40, T1 - 40 * INTERVAL_MS)),
    );
    mocks.getSessionApi.mockResolvedValue({ok: true, data: mkSession()});
    mocks.stepSessionApi.mockResolvedValue({ok: true, data: mkSession({clock_ms: T2})});
    mocks.exitSessionApi.mockResolvedValue({ok: true, data: mkSession({clock_ms: T3, status: "cerrada"})});
    mocks.restartSessionApi.mockResolvedValue({ok: true, data: mkSession({clock_ms: T1, status: "en_espera"})});
    mocks.evaluateSessionApi.mockResolvedValue({ok: true, data: mkSession()});
    mocks.createEngineeringSession.mockResolvedValue({ok: true, session: mkSession()});
    localStorage.removeItem(SESSION_ID_STORAGE_KEY);
  });
  afterEach(() => {
    localStorage.removeItem(SESSION_ID_STORAGE_KEY);
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("A: un solo Iniciar conduce en_espera → abierta → cerrada sin botones de avance", async () => {
    const enEspera = mkSession();
    const abierta = mkSession({
      status: "abierta", revision: 2, clock_ms: T2,
      position: mkPosition({
        open: true, direction: "LONG", entry_px: 100, entry_qty: 10,
        entry_cost: 1000, entry_ms: T2, stop_px: 95, mark_px: 100.5,
        mark_ms: T2, unrealized_gross: 5, unrealized_net: 4,
        mfe_pct: 0.5, mae_pct: 0,
      }),
    });
    const cerrada = mkSession({
      status: "cerrada", revision: 3, clock_ms: T3,
      position: mkPosition(), result: mkResult(),
    });
    mocks.createEngineeringSession.mockResolvedValue({ok: true, session: enEspera});
    mocks.evaluateSessionApi.mockResolvedValue({ok: true, data: enEspera});
    mocks.stepSessionApi
      .mockResolvedValueOnce({ok: true, data: abierta})
      .mockResolvedValueOnce({ok: true, data: cerrada});

    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));

    // La autonomía arranca sola tras la evaluación (entrada pendiente).
    await advanceUntil(() => mocks.stepSessionApi.mock.calls.length >= 1);
    expect(screen.getByTestId("session-autonomous")).toBeTruthy();
    // Los botones de avance manual quedan inhabilitados durante la autonomía.
    expect(
      screen.getByRole("button", {name: "Paso a paso"}).hasAttribute("disabled"),
    ).toBe(true);

    // El cierre (segundo paso) llega con el retraso autónomo, sin pulsar nada.
    await advanceUntil(() => mocks.stepSessionApi.mock.calls.length >= 2);
    await advanceUntil(() => screen.queryByTestId("session-autonomous") === null);

    expect(mocks.stepSessionApi).toHaveBeenCalledTimes(2);
    expect(mocks.exitSessionApi).not.toHaveBeenCalled(); // el motor cierra, no un botón
    expect(screen.queryByTestId("session-transport-cause")).toBeNull();
    expect(document.querySelector('[data-state="cerrada"]')).toBeTruthy();
  });

  it("B: sin evidencia (sin_iniciar) la sesión se abstiene y la autonomía no arranca", async () => {
    const abstiene = mkSession({
      status: "sin_iniciar",
      config: {
        ...mkSession().config,
        decision: "SIN_ENTRADA",
        decision_reason: "evidencia insuficiente",
      },
    });
    mocks.createEngineeringSession.mockResolvedValue({ok: true, session: abstiene});
    mocks.evaluateSessionApi.mockResolvedValue({ok: true, data: abstiene});

    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await advanceUntil(() => mocks.evaluateSessionApi.mock.calls.length >= 1);
    await advanceUntil(() => document.querySelector('[data-state="sin_iniciar"]') !== null);

    // Un intervalo amplio sin pasos: la abstención nunca abre el bucle autónomo.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(mocks.stepSessionApi).not.toHaveBeenCalled();
    expect(screen.queryByTestId("session-autonomous")).toBeNull();
    expect(screen.queryByTestId("session-transport-cause")).toBeNull();
  });

  it("C: fin del transporte local detiene la autonomía con causa visible, sin entrada y sin cierre inventado", async () => {
    mocks.createEngineeringSession.mockResolvedValue({ok: true, session: mkSession()});
    mocks.evaluateSessionApi.mockResolvedValue({ok: true, data: mkSession()});
    // El paso no avanza el reloj: no hay más eventos locales disponibles en T.
    mocks.stepSessionApi.mockResolvedValue({
      ok: true, data: mkSession({clock_ms: T1, status: "en_espera"}),
    });

    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await advanceUntil(() => mocks.stepSessionApi.mock.calls.length >= 1);
    await advanceUntil(() => screen.queryByTestId("session-transport-cause") !== null);

    expect(mocks.stepSessionApi).toHaveBeenCalledTimes(1);
    const cause = screen.getByTestId("session-transport-cause").textContent ?? "";
    expect(cause).toContain("Sin entrada nueva");
    expect(cause).toContain("open_at_end");
    // Autonomía detenida y sin cierre inventado por el navegador.
    expect(screen.queryByTestId("session-autonomous")).toBeNull();
    expect(mocks.exitSessionApi).not.toHaveBeenCalled();
  });
});
