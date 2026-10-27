// @vitest-environment jsdom
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import type {PaperSessionState} from "@/lib/paper-lab-live";
import EngineeringSession from "@/components/session-lab/EngineeringSession";

const SESSION_ID_STORAGE_KEY = "paper-lab-sesion-ingenieria-id";

// vi.hoisted evita la zona muerta temporal: las fábricas de vi.mock se izan
// al tope del archivo y necesitan los dobles ya inicializados.
const mocks = vi.hoisted(() => ({
  fetchMarketSeries: vi.fn(),
  getSessionApi: vi.fn(),
  stepSessionApi: vi.fn(),
  exitSessionApi: vi.fn(),
  restartSessionApi: vi.fn(),
  evaluateSessionApi: vi.fn(),
}));

vi.mock("@/lib/session-lab", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/session-lab")>();
  return {...actual, fetchMarketSeries: mocks.fetchMarketSeries};
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
