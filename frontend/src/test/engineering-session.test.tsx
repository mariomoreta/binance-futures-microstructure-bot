// @vitest-environment jsdom
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import type {
  PaperPosition, PaperSessionState, PaperTradeResult,
} from "@/lib/paper-lab-live";
import EngineeringSession from "@/components/session-lab/EngineeringSession";

// Objetivo: probar el COMPONENTE frente a la conducción backend (servicio
// engineering-session-service/v1). El navegador crea (POST), arranca
// (control start), OBSERVA (GET) y detiene (control stop/stop_session);
// NUNCA programa pasos con un temporizador de React: el avance autónomo es
// del backend. Los dobles simulan el servicio; las pruebas de conducción
// real (eventos locales → evaluación → fill → cierre) viven en pytest.
const SESSION_ID_STORAGE_KEY = "paper-lab-sesion-ingenieria-id";

// vi.hoisted evita la zona muerta temporal: las fábricas de vi.mock se izan
// al tope del archivo y necesitan los dobles ya inicializados.
const mocks = vi.hoisted(() => ({
  fetchMarketSeries: vi.fn(),
  createBackendSession: vi.fn(),
  fetchBackendSession: vi.fn(),
  controlBackendSession: vi.fn(),
  fetchEngineeringService: vi.fn(),
  startEngineeringService: vi.fn(),
}));

vi.mock("@/lib/session-lab", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/session-lab")>();
  return {
    ...actual,
    fetchMarketSeries: mocks.fetchMarketSeries,
    createBackendSession: mocks.createBackendSession,
    fetchBackendSession: mocks.fetchBackendSession,
    controlBackendSession: mocks.controlBackendSession,
    fetchEngineeringService: mocks.fetchEngineeringService,
    startEngineeringService: mocks.startEngineeringService,
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

function mkPosition(overrides: Partial<PaperPosition> = {}): PaperPosition {
  return {
    open: false, direction: null, entry_px: null, entry_qty: null,
    entry_cost: null, entry_ms: null, stop_px: null, mark_px: null,
    mark_ms: null, unrealized_gross: null, unrealized_net: null,
    mfe_pct: null, mae_pct: null,
    ...overrides,
  };
}

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
    position: mkPosition(),
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

// Respuesta GET del backend: {session, drive} (drive como hermano).
function getResp(
  session: PaperSessionState,
  drive: Record<string, unknown> = {state: "idle"},
) {
  return {ok: true, data: {session, drive}, status: 200};
}

// Respuesta POST /control del backend: {session, drive}.
function ctlResp(
  session: PaperSessionState,
  drive: Record<string, unknown> = {state: "idle"},
) {
  return {ok: true, data: {session, drive}, status: 200};
}

describe("sesión de ingeniería — navegador observador (backend conduce)", () => {
  beforeEach(() => {
    mocks.fetchMarketSeries.mockResolvedValue(
      seriesPayload(mkCandles(40, T1 - 40 * INTERVAL_MS)),
    );
    mocks.fetchBackendSession.mockResolvedValue(getResp(mkSession()));
    mocks.createBackendSession.mockResolvedValue(
      {ok: true, data: {session: mkSession()}, status: 200},
    );
    mocks.controlBackendSession.mockImplementation(
      (_sid: unknown, action: unknown, _opts?: unknown) => {
        if (action === "start") {
          return Promise.resolve(ctlResp(mkSession(), {state: "running"}));
        }
        return Promise.resolve(ctlResp(mkSession(), {state: "stopped"}));
      },
    );
    // Servicio de ingeniería disponible y verificado por defecto: la mayoría
    // de casos prueba el flujo de sesión, no la puerta del servicio.
    mocks.fetchEngineeringService.mockResolvedValue({
      ok: true,
      data: {state: "ready", service: "engineering-session-service/v1",
        pid: 4242, port: 8797, detail: null},
      status: 200,
    });
    mocks.startEngineeringService.mockResolvedValue({
      ok: true, data: {pid: 4242, port: 8797}, status: 200,
    });
    localStorage.removeItem(SESSION_ID_STORAGE_KEY);
  });
  afterEach(() => {
    localStorage.removeItem(SESSION_ID_STORAGE_KEY);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("recupera la sesión del BACKEND y usa la identidad autoritativa del config, no los defaults", async () => {
    localStorage.setItem(SESSION_ID_STORAGE_KEY, "sess-123");
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() => expect(mocks.fetchBackendSession).toHaveBeenCalledWith("sess-123"));
    await waitFor(() => expect(mocks.fetchMarketSeries).toHaveBeenCalled(), {timeout: 5000});
    const calls = mocks.fetchMarketSeries.mock.calls;
    const last = calls[calls.length - 1]!;
    // Identidad autoritativa del config (BTCUSDT/5m), no las props por defecto (MINAUSDT/1m).
    expect(last[0]).toBe("BTCUSDT");
    expect(last[1]).toBe("5m");
    expect(last[3]).toBe(T1); // reloj T de la sesión recuperada
    expect(last[4]).toBe(true); // fuente solo lectura (--no-fetch)
    expect(mocks.createBackendSession).not.toHaveBeenCalled();
  });

  it("Iniciar: sesión creada EN el backend + control start (el navegador no crea ni conduce localmente)", async () => {
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await waitFor(() => expect(mocks.createBackendSession).toHaveBeenCalledTimes(1));
    // Transporte live explícito en el payload de create: solo la ventana de
    // contexto viaja (candles=[]); la operación la produce el feed. El
    // request_id hace idempotente el create en el backend (dedupe).
    const createInput = mocks.createBackendSession.mock.calls[0]![0];
    expect(createInput.transport).toBe("market_stream");
    expect(createInput.requestId).toEqual(expect.any(String));
    expect(createInput.candles).toEqual([]);
    expect(createInput.context.length).toBeGreaterThan(0);
    expect(mocks.controlBackendSession).toHaveBeenCalledWith(
      "sess-123", "start",
      expect.objectContaining({requestId: expect.any(String)}),
    );
    // El identificador de sesión vive en el navegador; el estado, no.
    expect(localStorage.getItem(SESSION_ID_STORAGE_KEY)).toBe("sess-123");
    // Servicio ya listo: el arranque explícito del servicio NO se repite.
    expect(mocks.startEngineeringService).not.toHaveBeenCalled();
  });

  it("montaje: consulta el estado del servicio con GET puro; NO arranca procesos ni sesiones", async () => {
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() => expect(mocks.fetchEngineeringService).toHaveBeenCalled());
    // Evitar confusión con el ciclo de observador: solo contamos la llamada
    // de servicio, que es consulta (la puerta de arranque es POST del botón).
    expect(mocks.startEngineeringService).not.toHaveBeenCalled();
    expect(mocks.createBackendSession).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.getByTestId("service-chip").dataset.state).toBe("ready"));
  });

  it("servicio detenido → Iniciar: arranque explícito ONCE, servicio listo y una sola sesión", async () => {
    // Estado coherente: consultas de servicio devuelven "down" hasta que el
    // POST de arranque explícito cambia el estado (el montaje consume la
    // primera consulta GET; la puerta del botón hace la suya).
    let serviceReady = false;
    mocks.fetchEngineeringService.mockImplementation(() => Promise.resolve({
      ok: true,
      data: serviceReady
        ? {state: "ready", service: "engineering-session-service/v1",
          pid: 4242, port: 8797, detail: null}
        : {state: "down", detail: "sin escucha", pid: null, port: 8797},
      status: 200,
    } as never));
    mocks.startEngineeringService.mockImplementation(() => {
      serviceReady = true;
      return Promise.resolve({
        ok: true, data: {pid: 4242, port: 8797}, status: 200,
      });
    });
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() =>
      expect(screen.getByTestId("service-chip").dataset.state).toBe("down"));
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await waitFor(() => expect(mocks.createBackendSession).toHaveBeenCalledTimes(1));
    // Arranque explícito con POST action=start, UNA sola vez (sin duplicados).
    expect(mocks.startEngineeringService).toHaveBeenCalledTimes(1);
    expect(mocks.startEngineeringService.mock.calls[0]).toEqual([]);
    await waitFor(() =>
      expect(screen.getByTestId("service-chip").dataset.state).toBe("ready"));
    // Una sola sesión: ni segunda creación ni segundo control start.
    expect(mocks.createBackendSession).toHaveBeenCalledTimes(1);
  });

  it("fallo de arranque del servicio: error visible y claro SIN crear sesión", async () => {
    mocks.fetchEngineeringService.mockResolvedValue({
      ok: true,
      data: {state: "down", detail: "sin escucha", pid: null, port: 8797},
      status: 200,
    });
    mocks.startEngineeringService.mockResolvedValue({
      ok: false,
      error: "ENGINEERING_SERVICE_START_FAILED",
      detail: "spawn del controlador canónico falló",
      status: 503,
    });
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() =>
      expect(screen.getByTestId("service-chip").dataset.state).toBe("down"));
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await waitFor(() => expect(screen.getByTestId("session-error")).toBeTruthy());
    const banner = screen.getByTestId("session-error").textContent ?? "";
    expect(banner).toContain("ENGINEERING_SERVICE_START_FAILED");
    expect(banner).toContain("spawn del controlador canónico falló");
    expect(banner).toContain("No quedó ninguna sesión creada");
    // Identidad conservadora: sin procesos huérfanos ni sesión creada.
    expect(mocks.startEngineeringService).toHaveBeenCalledTimes(1);
    expect(mocks.createBackendSession).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.getByTestId("service-chip").dataset.state).toBe("error"));
  });

  it("puerto ocupado por servicio de identidad no verificable: error claro, sin arrancar ni detener PID desconocido", async () => {
    mocks.fetchEngineeringService.mockResolvedValue({
      ok: true,
      data: {state: "unidentified", detail: "puerto ocupado por un servicio desconocido",
        pid: null, port: 8797},
      status: 200,
    });
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() =>
      expect(screen.getByTestId("service-chip").dataset.state).toBe("error"));
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await waitFor(() => expect(screen.getByTestId("session-error")).toBeTruthy());
    const banner = screen.getByTestId("session-error").textContent ?? "";
    expect(banner).toContain("no identificable");
    expect(banner).toContain("no se reutiliza ni se detiene");
    // Conservador: ni arranque repetido ni creación de sesión.
    expect(mocks.startEngineeringService).not.toHaveBeenCalled();
    expect(mocks.createBackendSession).not.toHaveBeenCalled();
  });

  it("durante la conducción backend el chip session-autonomous aparece y el avance manual queda deshabilitado", async () => {
    const abierta = mkSession({
      status: "abierta", revision: 2, clock_ms: T1,
      position: mkPosition({
        open: true, direction: "LONG", entry_px: 100, entry_qty: 10,
        entry_cost: 1000, entry_ms: T2, stop_px: 95, mark_px: 100.5,
        mark_ms: T2, unrealized_gross: 5, unrealized_net: 4,
        mfe_pct: 0.5, mae_pct: 0,
      }),
    });
    mocks.createBackendSession.mockResolvedValue(
      {ok: true, data: {session: mkSession()}, status: 200},
    );
    mocks.controlBackendSession.mockResolvedValue(
      ctlResp(abierta, {state: "running", cause: null}),
    );
    mocks.fetchBackendSession.mockResolvedValue(getResp(abierta, {state: "running"}));
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await waitFor(() => expect(screen.getByTestId("session-autonomous")).toBeTruthy());
    // El botón de avance manual queda inhabilitado: no hay temporizador React.
    expect(screen.getByRole("button", {name: "Paso a paso"}).hasAttribute("disabled")).toBe(true);
    // Ningún avance manual espontáneo del navegador durante la conducción.
    await new Promise((r) => setTimeout(r, 900));
    const stepActions = mocks.controlBackendSession.mock.calls.filter(
      (c) => c[1] !== "start",
    );
    expect(stepActions).toEqual([]);
  });

  it("error si el servicio backend no está disponible: banner visible sin estado local", async () => {
    localStorage.setItem(SESSION_ID_STORAGE_KEY, "sess-123");
    mocks.fetchBackendSession.mockResolvedValue({
      ok: false, error: "BFF_UNREACHABLE", status: 0,
    });
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() => expect(screen.getByTestId("session-error")).toBeTruthy());
    expect(screen.getByTestId("session-error").textContent).toContain("BFF_UNREACHABLE");
  });

  it("causa de fin de conducción visible (END_OF_TRANSPORT) tomada del drive del backend", async () => {
    mocks.controlBackendSession.mockResolvedValue(ctlResp(mkSession(), {
      state: "stopped", cause: "END_OF_TRANSPORT",
    }));
    mocks.fetchBackendSession.mockResolvedValue(getResp(mkSession(), {
      state: "stopped", cause: "END_OF_TRANSPORT",
    }));
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await waitFor(() => expect(screen.getByTestId("session-drive-cause")).toBeTruthy());
    const cause = screen.getByTestId("session-drive-cause").textContent ?? "";
    expect(cause).toContain("transporte local");
    expect(cause).toContain("agotó");
    // Sin conducción no hay chip autónomo.
    expect(screen.queryByTestId("session-autonomous")).toBeNull();
  });

  it("abstención (sin_iniciar) sin conducción: sin chip autónomo y sin pasos espontáneos del navegador", async () => {
    const abstiene = mkSession({
      status: "sin_iniciar",
      config: {
        ...mkSession().config, decision: "SIN_ENTRADA",
        decision_reason: "evidencia insuficiente",
      },
    });
    mocks.createBackendSession.mockResolvedValue(
      {ok: true, data: {session: abstiene}, status: 200},
    );
    // El drive queda detenido sin causa: la abstención temporal espera
    // eventos del transporte EN EL BACKEND, no una rueda del navegador.
    mocks.controlBackendSession.mockResolvedValue(
      ctlResp(abstiene, {state: "stopped", cause: null}),
    );
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await waitFor(() => expect(mocks.controlBackendSession).toHaveBeenCalledTimes(1));
    await new Promise((r) => setTimeout(r, 900));
    // La abstención nunca genera avances desde el navegador: solo quedó la
    // puesta en marcha; observar (GET) no conduce.
    const advanceCalls = mocks.controlBackendSession.mock.calls.filter(
      (c) => c[1] !== "start",
    );
    expect(advanceCalls).toEqual([]);
    expect(screen.queryByTestId("session-autonomous")).toBeNull();
    expect(screen.queryByTestId("session-drive-cause")).toBeNull();
  });

  it("transporte live: puerta de abstención visible (FEED_SILENCE) y panel de evidencia del stream", async () => {
    // Drive live observado con GET: la puerta (last_gate) explica la
    // abstención y la evidencia (indicadores/contexto BTC) viene del MISMO
    // stream que conduce. El navegador solo presenta; no evalúa nada.
    const liveDrive = {
      state: "running", cause: null, runner: "market_stream",
      market_url: "http://127.0.0.1:8791/events", bars: 60,
      live_silence_ms: 120000, watermark: T1,
      last_gate: {
        ok: false, cause: "FEED_SILENCE", silence_ms: 130000,
        live_silence_ms: 120000, clock_ms: null,
        note: "feed en silencio (sin frames)",
      },
      evidence: {
        indicators: {block: {ret: 1}, received_at_ms: T1},
        context_btc: {block: {ret_btc_bps_5: 2}, received_at_ms: T1},
      },
      transport_events: 7,
    };
    mocks.createBackendSession.mockResolvedValue(
      {ok: true, data: {session: mkSession()}, status: 200},
    );
    mocks.controlBackendSession.mockResolvedValue(
      ctlResp(mkSession(), liveDrive),
    );
    mocks.fetchBackendSession.mockResolvedValue(getResp(mkSession(), liveDrive));
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await waitFor(() =>
      expect(screen.getByTestId("session-abstention-gate")).toBeTruthy());
    const gate = screen.getByTestId("session-abstention-gate").textContent ?? "";
    expect(gate).toContain("FEED_SILENCE");
    expect(gate).toContain("silencio del feed");
    expect(gate).toContain("130000");
    await waitFor(() =>
      expect(screen.getByTestId("stream-evidence")).toBeTruthy());
    const panel = screen.getByTestId("stream-evidence").textContent ?? "";
    expect(panel).toContain("market_stream");
    expect(panel).toContain("8791");
    expect(panel).toContain("evidencia indicators");
    expect(panel).toContain("evidencia context_btc");
  });

  it("Detener sesión conduce stop del drive y luego stop_session (una paradigación explícita)", async () => {
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    fireEvent.click(screen.getByRole("button", {name: "Iniciar sesion"}));
    await waitFor(() => expect(mocks.controlBackendSession).toHaveBeenCalledTimes(1));
    const detenida = mkSession({status: "detenida", clock_ms: T1});
    mocks.controlBackendSession.mockImplementation(
      (_sid: unknown, action: unknown) => Promise.resolve(
        action === "stop"
          ? ctlResp(detenida, {state: "stopped", cause: "OPERATOR_STOP"})
          : ctlResp(detenida, {state: "stopped", cause: "SESSION_STOPPED"}),
      ),
    );
    fireEvent.click(screen.getByTestId("btn-detener-sesion"));
    await waitFor(() => expect(mocks.controlBackendSession).toHaveBeenCalledTimes(3));
    const actions = mocks.controlBackendSession.mock.calls.map((c) => c[1]);
    expect(actions).toEqual(["start", "stop", "stop_session"]);
  });

  it("Cerrar posicion conduce exit en el backend, no por la API del frontend", async () => {
    localStorage.setItem(SESSION_ID_STORAGE_KEY, "sess-123");
    const abierta = mkSession({
      status: "abierta", clock_ms: T1,
      position: mkPosition({open: true, direction: "LONG", entry_px: 100, entry_qty: 10, entry_cost: 1000, entry_ms: T1, stop_px: 95}),
    });
    mocks.fetchBackendSession.mockResolvedValue(getResp(abierta, {state: "idle"}));
    mocks.controlBackendSession.mockResolvedValue(
      ctlResp(mkSession({status: "cerrada", clock_ms: T3, result: mkResult()}),
        {state: "idle"}),
    );
    render(<EngineeringSession symbol="MINAUSDT" interval="1m" bars={90} />);
    await waitFor(() => expect(screen.getByRole("button", {name: "Cerrar posicion"})).toBeTruthy());
    fireEvent.click(screen.getByRole("button", {name: "Cerrar posicion"}));
    await waitFor(() => expect(mocks.controlBackendSession).toHaveBeenCalledWith(
      "sess-123", "exit", expect.objectContaining({expectedRevision: 1}),
    ));
  });
});
