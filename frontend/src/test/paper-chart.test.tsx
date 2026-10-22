import {afterEach, beforeAll, beforeEach, describe, expect, it, vi} from "vitest";
import {cleanup, render, screen, waitFor} from "@testing-library/react";
import type {PaperChartModel} from "@/lib/paper-chart-contract";
import type {PaperSessionState} from "@/lib/paper-lab-live";
import {buildPaperChartModel} from "@/lib/paper-chart-contract";
import {PaperChart} from "@/components/paper-lab-live/PaperChart";

const h = vi.hoisted(() => {
  type SeriesMock = {
    setData: ReturnType<typeof vi.fn>;
    update: ReturnType<typeof vi.fn>;
    createPriceLine: ReturnType<typeof vi.fn>;
    removePriceLine: ReturnType<typeof vi.fn>;
  };
  const series: SeriesMock[] = [];
  const makeSeries = (): SeriesMock => {
    const s = {
      setData: vi.fn(),
      update: vi.fn(),
      createPriceLine: vi.fn(() => ({})),
      removePriceLine: vi.fn(),
    };
    series.push(s);
    return s;
  };
  const markerPlugins: Array<{setMarkers: ReturnType<typeof vi.fn>;
    detach: ReturnType<typeof vi.fn>}> = [];
  const timeScale = {
    fitContent: vi.fn(),
    subscribeVisibleTimeRangeChange: vi.fn(),
    unsubscribeVisibleTimeRangeChange: vi.fn(),
  };
  const chart = {
    addSeries: vi.fn(() => makeSeries()),
    timeScale: vi.fn(() => timeScale),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
    remove: vi.fn(),
  };
  return {series, markerPlugins, timeScale, chart, makeSeries};
});

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => h.chart),
  CandlestickSeries: {type: "Candlestick"},
  LineSeries: {type: "Line"},
  ColorType: {Solid: "solid"},
  CrosshairMode: {Normal: 0},
  LineStyle: {Solid: 0, Dotted: 1, Dashed: 2},
  createSeriesMarkers: vi.fn(() => {
    const plugin = {setMarkers: vi.fn(), detach: vi.fn()};
    h.markerPlugins.push(plugin);
    return plugin;
  }),
}));

// jsdom no calcula layout. El encuadre inicial se difiere hasta que el
// contenedor tiene ancho real (comportamiento de producción); aquí se simula
// un contenedor ya maquetado para poder verificar el ajuste inicial.
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get() {
      return 800;
    },
  });
});

function state(overrides: Partial<PaperSessionState> = {}): PaperSessionState {
  return {
    session_id: "PL-BTCUSDT-LONG-1",
    created_at_ms: 1000,
    updated_at_ms: 2000,
    status: "en_espera",
    revision: 3,
    config: {
      symbol: "BTCUSDT", interval: "15m", direction: "LONG",
      notional_usdt: 1000, entry_px: 101, stop_px: 95.95,
      stop_distance_pct: 5, horizon_ms: 10800000,
      fee_bps: 5, spread_bps: 1, slippage_bps: 2,
      decision: "ENTRADA_SIMULADA",
      decision_reason: "causal",
      decision_evidence: {decision_at_ms: 900000, at_ms: 900000, trigger_px: 101},
    },
    candles: [
      {open_time_ms: 0, open: 100, high: 101, low: 99, close: 100.5,
        close_time_ms: 899999},
      {open_time_ms: 900000, open: 101, high: null, low: null, close: null,
        close_time_ms: null},
    ],
    context_candles: [
      {open_time_ms: -1800000, open: 99, high: 100, low: 98, close: 99.5,
        close_time_ms: -900001},
      {open_time_ms: -900000, open: 99.5, high: 100.5, low: 99, close: 100,
        close_time_ms: -1},
    ],
    cursor: 2,
    position: {
      open: false, direction: "LONG", entry_px: null, entry_qty: null,
      entry_cost: null, entry_ms: null, stop_px: null, mark_px: null,
      mark_ms: null, unrealized_gross: null, unrealized_net: null,
      mfe_pct: null, mae_pct: null,
    },
    costs: {
      fee_bps: 5, spread_bps: 1, entry_fees: 0, exit_fees: 0,
      entry_spread_slip: 0, exit_spread_slip: 0, funding: null, friction: 0,
      entry_fees_executed: 0, exit_fees_executed: 0,
      entry_spread_slip_executed: 0, exit_spread_slip_executed: 0,
      exit_fees_estimated: 0, exit_spread_slip_estimated: 0,
    },
    events: [],
    result: null,
    clock_ms: 900000,
    config_hash: "abc",
    input_hash: "def",
    engine_version: "paper-lab/v1",
    limitations: [],
    authoritative: null,
    can_step: true,
    ...overrides,
  };
}

function pendingModel(): PaperChartModel {
  return buildPaperChartModel(state());
}

describe("PaperChart — integración con Lightweight Charts (mock de wiring)", () => {
  beforeEach(() => {
    h.series.length = 0;
    h.markerPlugins.length = 0;
    vi.clearAllMocks();
    h.chart.addSeries.mockImplementation(() => h.makeSeries());
  });

  afterEach(() => {
    cleanup();
  });

  it("monta la biblioteca en cliente, mapea velas/segundos y limpia recursos", async () => {
    const {unmount} = render(<PaperChart model={pendingModel()} />);

    await waitFor(() => expect(h.chart.addSeries).toHaveBeenCalledTimes(3));
    const contextSeries = h.series[0]!;
    const candleSeries = h.series[1]!;
    const openSeries = h.series[2]!;
    expect(contextSeries).toBeDefined();
    expect(candleSeries).toBeDefined();
    expect(openSeries).toBeDefined();

    await waitFor(() => expect(candleSeries.setData).toHaveBeenCalled());
    // Contexto: dos velas cerradas, tiempo en segundos.
    expect(contextSeries.setData.mock.calls[0]![0]).toEqual([
      {time: -1800, open: 99, high: 100, low: 98, close: 99.5},
      {time: -900, open: 99.5, high: 100.5, low: 99, close: 100},
    ]);
    // Operación: solo la vela cerrada en T; la solo-open no va aquí.
    expect(candleSeries.setData.mock.calls[0]![0]).toEqual([
      {time: 0, open: 100, high: 101, low: 99, close: 100.5},
    ]);
    // La vela solo-open es un punto en su open, sin OHLC inventado.
    expect(openSeries.setData).toHaveBeenCalledWith([{time: 900, value: 101}]);

    // Marcadores: "open" y "Señal" viajan con el punto porque la vela sigue
    // solo-open; las velas cerradas no reciben marcadores todavía.
    expect(h.markerPlugins).toHaveLength(2);
    expect(h.markerPlugins[0]!.setMarkers).toHaveBeenCalledWith([]);
    const openMarkers = h.markerPlugins[1]!.setMarkers.mock.calls.at(-1)?.[0];
    expect(openMarkers.map((m: {text?: string}) => m.text)).toEqual(["open", "Señal"]);
    expect(candleSeries.createPriceLine).toHaveBeenCalled();
    expect(h.timeScale.fitContent).toHaveBeenCalled();

    unmount();
    expect(h.chart.remove).toHaveBeenCalled();
    expect(h.markerPlugins[0]!.detach).toHaveBeenCalled();
    expect(h.markerPlugins[1]!.detach).toHaveBeenCalled();
    expect(h.chart.unsubscribeCrosshairMove).toHaveBeenCalled();
    expect(h.timeScale.unsubscribeVisibleTimeRangeChange).toHaveBeenCalled();
  });

  it("muestra estado de cobertura y declara volumen/indicadores UNKNOWN", async () => {
    render(<PaperChart model={pendingModel()} />);
    expect(screen.getByTestId("paper-chart-source").textContent)
      .toContain("FIXTURE / SIMULACIÓN");
    expect(screen.getByTestId("paper-chart-coverage").textContent)
      .toContain("2 contexto");
    expect(screen.getByTestId("paper-chart-coverage").textContent)
      .toContain("1 solo-open");
    expect(screen.getByText("Volumen UNKNOWN")).toBeTruthy();
    expect(screen.getByText("Indicadores: ninguno")).toBeTruthy();
  });

  it("en sesión cerrada dibuja entrada/stop/salida solo con exit_executed", async () => {
    const closed = state({
      status: "cerrada",
      clock_ms: 2700000,
      position: {
        ...state().position,
        open: false, entry_px: 101, entry_ms: 1800000, stop_px: 95.95,
      },
      result: {
        symbol: "BTCUSDT", direction: "LONG", entry_px: 101, exit_px: 95.95,
        entry_ms: 1800000, exit_ms: 2700000, exit_reason: "stop",
        exit_executed: true, qty: 9.9, filled_cost: 1000, gross_pnl: -50,
        fees: 0.975, spread_slip: 0.585, funding: null, friction: 1.56,
        net_pnl: -51.56, realized_net: -51.56, open_at_end: false,
        entry_fees_executed: 0.5, exit_fees_executed: 0.475,
        entry_spread_slip_executed: 0.1, exit_spread_slip_executed: 0.485,
        exit_fees_estimated: 0, exit_spread_slip_estimated: 0,
      },
      events: [],
    });
    render(<PaperChart model={buildPaperChartModel(closed)} />);
    await waitFor(() => expect(h.chart.addSeries).toHaveBeenCalledTimes(3));
    const candleSeries = h.series[1]!;
    await waitFor(() => expect(candleSeries.createPriceLine).toHaveBeenCalled());
    const titles = candleSeries.createPriceLine.mock.calls
      .map((c) => c[0].title as string);
    expect(titles.some((t) => t.startsWith("Entrada"))).toBe(true);
    expect(titles.some((t) => t.startsWith("Stop"))).toBe(true);
    expect(titles.some((t) => t.startsWith("Salida"))).toBe(true);
    expect(titles.some((t) => t.includes("80.00"))).toBe(false);
  });
});
