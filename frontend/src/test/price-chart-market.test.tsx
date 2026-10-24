import {afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi} from "vitest";
import {cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {buildMarketChartModel, type MarketSeriesPayload} from "@/lib/market-chart-contract";
import {PriceChart} from "@/components/chart/PriceChart";

const H = 3_600_000;
const T0 = 1_790_000_000_000;

const h = vi.hoisted(() => {
  type SeriesMock = {
    setData: ReturnType<typeof vi.fn>;
    update: ReturnType<typeof vi.fn>;
    createPriceLine: ReturnType<typeof vi.fn>;
    removePriceLine: ReturnType<typeof vi.fn>;
    priceScale: ReturnType<typeof vi.fn>;
  };
  const series: SeriesMock[] = [];
  const state = {range: {from: 0, to: 0}};
  const makeSeries = (): SeriesMock => {
    const s = {
      setData: vi.fn(),
      update: vi.fn(),
      createPriceLine: vi.fn(() => ({})),
      removePriceLine: vi.fn(),
      priceScale: vi.fn(() => ({applyOptions: vi.fn()})),
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
    getVisibleLogicalRange: vi.fn(() => ({from: 5, to: 6})),
    setVisibleLogicalRange: vi.fn(),
    getVisibleRange: vi.fn(() => state.range),
  };
  const chart = {
    addSeries: vi.fn(() => makeSeries()),
    timeScale: vi.fn(() => timeScale),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
    remove: vi.fn(),
  };
  return {series, markerPlugins, timeScale, chart, makeSeries, state};
});

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => h.chart),
  CandlestickSeries: {type: "Candlestick"},
  LineSeries: {type: "Line"},
  HistogramSeries: {type: "Histogram"},
  ColorType: {Solid: "solid"},
  CrosshairMode: {Normal: 0},
  LineStyle: {Solid: 0, Dotted: 1, Dashed: 2},
  createSeriesMarkers: vi.fn(() => {
    const plugin = {setMarkers: vi.fn(), detach: vi.fn()};
    h.markerPlugins.push(plugin);
    return plugin;
  }),
}));

// jsdom no calcula layout: el encuadre inicial depende de un ancho real. Se
// simula el ancho del contenedor para poder verificar el comportamiento.
let hostWidth = 800;
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get() {
      return hostWidth;
    },
  });
});
afterAll(() => {
  // @ts-expect-error eliminar la simulación de layout
  delete HTMLElement.prototype.clientWidth;
});

function candle(openTime: number, close = "100.5"): {
  open_time_ms: number;
  close_time_ms: number | null;
  open: string;
  high: string;
  low: string;
  close: string;
  base_volume: string;
  quote_volume: string;
  trade_count: number;
  provisional: boolean;
  fetched_at_ms: number;
  storage: string;
} {
  return {
    open_time_ms: openTime,
    close_time_ms: openTime + H - 1,
    open: "100", high: "101", low: "99", close,
    base_volume: "12.5", quote_volume: "1250", trade_count: 10,
    provisional: false, fetched_at_ms: T0, storage: "cache",
  };
}

function payload(candles = [candle(T0), candle(T0 + H)], overrides:
  Partial<MarketSeriesPayload> = {}): MarketSeriesPayload {
  return {
    contract_version: "market-series/v1", venue: "binance",
    market_type: "usd_m_futures", api_family: "fapi", source: "klines",
    endpoint: "/fapi/v1/klines", symbol: "BTCUSDT", interval: "1h",
    interval_ms: H,
    contract: {
      symbol: "BTCUSDT", base_asset: "BTC", quote_asset: "USDT",
      contract_type: "PERPETUAL", status: "TRADING", eligible: true,
      exclusion_reasons: [],
    },
    requested: {from_ms: T0 - 2 * H, to_ms: T0 + H},
    observed: {start_ms: T0, end_ms: T0 + H},
    candles,
    coverage: {
      state: "PARTIAL", observed_start_ms: T0,
      observed_end_ms: candles.length ? candles[candles.length - 1]!.open_time_ms : null,
      expected_bars: candles.length, actual_bars: candles.length, gap_count: 0,
      gaps: [], absent_ranges: [[T0 - 2 * H, T0 - H]], exhausted_before: false,
      earliest_available_ms: null, note: "",
    },
    volume: {
      available: true, base_asset: "BTC", quote_asset: "USDT",
      fields: ["base_volume", "quote_volume"], reason: null,
    },
    freshness: {
      state: "HISTORICAL_ON_DEMAND", newest_open_ms: T0 + H,
      newest_close_ms: T0 + 2 * H - 1, fetched_at_ms: T0 + 1000, age_ms: 60_000,
      provisional: false, note: "",
    },
    fetch: {
      allowed: true, performed: true, status: "ok", error: null, requests: 1,
      pages: 1, retries: 0, failures: 0, detail: null, bars_stored: 2,
      retry_after_ms: null,
    },
    labels: {
      mode: "HISTORICAL_ON_DEMAND", live: false,
      banner: "HISTORICO / CONSULTA BAJO DEMANDA",
    },
    generated_at_ms: T0 + 2 * H, notes: ["nota"], ...overrides,
  };
}

describe("PriceChart — modo mercado (market-chart/v1)", () => {
  beforeEach(() => {
    hostWidth = 800;
    h.series.length = 0;
    h.markerPlugins.length = 0;
    h.state.range = {from: 0, to: 0};
    vi.clearAllMocks();
    h.chart.addSeries.mockImplementation(() => h.makeSeries());
  });
  afterEach(() => cleanup());

  it("dibuja velas + volumen, sin niveles de operación ni contexto", async () => {
    render(<PriceChart model={buildMarketChartModel(payload())} />);
    await waitFor(() => expect(h.chart.addSeries).toHaveBeenCalledTimes(3));
    const candles = h.series[0]!;
    const volume = h.series[1]!;
    await waitFor(() => expect(candles.setData).toHaveBeenCalled());
    expect(candles.setData.mock.calls[0]![0]).toEqual([
      {time: T0 / 1000, open: 100, high: 101, low: 99, close: 100.5},
      {time: (T0 + H) / 1000, open: 100, high: 101, low: 99, close: 100.5},
    ]);
    expect(volume.setData).toHaveBeenCalled();
    expect(volume.setData.mock.calls[0]![0][0]).toMatchObject({value: 12.5});
    expect(candles.createPriceLine).not.toHaveBeenCalled();
    expect(screen.getByTestId("market-chart-source").textContent)
      .toContain("HISTORICO / CONSULTA BAJO DEMANDA");
    expect(screen.getByTestId("market-chart-volume").textContent).toContain("BTC");
    expect(screen.getByTestId("market-chart-coverage").textContent)
      .toContain("2 cerradas");
    expect(screen.queryByTestId("paper-chart-frame")).toBeNull();
  });

  it("rotula la vela provisional sin inventar cierre", async () => {
    const model = buildMarketChartModel(payload([
      candle(T0),
      {...candle(T0 + H), provisional: true, close_time_ms: null},
    ]));
    render(<PriceChart model={model} />);
    await waitFor(() => expect(h.markerPlugins.length).toBeGreaterThan(0));
    const markers = h.markerPlugins[0]!.setMarkers.mock.calls.at(-1)?.[0] ?? [];
    expect(markers.map((m: {text?: string}) => m.text)).toContain("provisional");
    expect(screen.getByTestId("market-chart-coverage").textContent)
      .toContain("1 provisional");
  });

  it("dibuja la vela en formación en serie aparte y la actualiza sin reescribir cerradas", async () => {
    const first = buildMarketChartModel(payload([
      candle(T0),
      {...candle(T0 + H), provisional: true, close_time_ms: null},
    ]));
    const {rerender} = render(<PriceChart model={first} />);
    await waitFor(() => expect(h.chart.addSeries).toHaveBeenCalledTimes(3));
    const candles = h.series[0]!;
    const provisional = h.series[2]!;
    await waitFor(() => expect(provisional.setData).toHaveBeenCalled());
    expect(provisional.setData.mock.calls.at(-1)![0]).toEqual([
      {time: (T0 + H) / 1000, open: 100, high: 101, low: 99, close: 100.5},
    ]);
    const closedSetDataCalls = candles.setData.mock.calls.length;

    // Tick de la misma vela en formación: solo cambia la serie provisional.
    const tick = buildMarketChartModel(payload([
      candle(T0),
      {...candle(T0 + H, "100.9"), provisional: true, close_time_ms: null},
    ]));
    rerender(<PriceChart model={tick} />);
    await waitFor(() => expect(
      provisional.setData.mock.calls.at(-1)![0][0].close).toBe(100.9));
    expect(candles.setData).toHaveBeenCalledTimes(closedSetDataCalls);

    // Cierre: la provisional desaparece y la cerrada se anexa con update().
    const closed = buildMarketChartModel(payload([candle(T0), candle(T0 + H)]));
    rerender(<PriceChart model={closed} />);
    await waitFor(() => expect(provisional.setData.mock.calls.at(-1)![0]).toEqual([]));
    expect(candles.update).toHaveBeenCalled();
  });

  it("ajusta el encuadre inicial una sola vez y respeta el zoom en updates", async () => {
    const first = buildMarketChartModel(payload([candle(T0)]));
    const {rerender} = render(<PriceChart model={first} />);
    await waitFor(() => expect(h.timeScale.fitContent).toHaveBeenCalledTimes(1));
    const extended = buildMarketChartModel(payload([candle(T0), candle(T0 + H)]));
    rerender(<PriceChart model={extended} />);
    // Actualización incremental (append): se usa update(), no setData completo.
    await waitFor(() => expect(h.series[0]!.update).toHaveBeenCalled());
    expect(h.series[0]!.update.mock.calls[0]![0]).toMatchObject({time: (T0 + H) / 1000});
    // Actualización normal: no se reencuadra.
    expect(h.timeScale.fitContent).toHaveBeenCalledTimes(1);
  });

  it("al anteponer un bloque anterior conserva el rango visible", async () => {
    const first = buildMarketChartModel(payload([candle(T0 + 2 * H), candle(T0 + 3 * H)]));
    const {rerender} = render(<PriceChart model={first} />);
    await waitFor(() => expect(h.timeScale.fitContent).toHaveBeenCalledTimes(1));
    const prepended = buildMarketChartModel(payload([
      candle(T0), candle(T0 + H), candle(T0 + 2 * H), candle(T0 + 3 * H),
    ]));
    rerender(<PriceChart model={prepended} />);
    await waitFor(() => expect(h.timeScale.setVisibleLogicalRange).toHaveBeenCalled());
    // 2 velas antepuestas -> desplazamiento +2 sobre el rango 5..6.
    expect(h.timeScale.setVisibleLogicalRange).toHaveBeenCalledWith({from: 7, to: 8});
    expect(h.timeScale.fitContent).toHaveBeenCalledTimes(1);
  });

  it("anteponer con el extremo reciente actualizado también conserva el encuadre", async () => {
    // Causa reproducida de la cadena: si el feed actualiza la última vela, la
    // detección estricta por sufijo fallaba, no se desplazaba el rango lógico
    // y la vista caía sobre el bloque recién antepuesto (borde izquierdo).
    const first = buildMarketChartModel(payload([candle(T0 + 2 * H), candle(T0 + 3 * H)]));
    const {rerender} = render(<PriceChart model={first} />);
    await waitFor(() => expect(h.timeScale.fitContent).toHaveBeenCalledTimes(1));
    const prepended = buildMarketChartModel(payload([
      candle(T0), candle(T0 + H), candle(T0 + 2 * H),
      candle(T0 + 3 * H, "100.9"),
    ]));
    rerender(<PriceChart model={prepended} />);
    await waitFor(() => expect(h.timeScale.setVisibleLogicalRange).toHaveBeenCalled());
    expect(h.timeScale.setVisibleLogicalRange).toHaveBeenCalledWith({from: 7, to: 8});
  });

  it("difiere el encuadre si el contenedor aún no tiene ancho", async () => {
    hostWidth = 0;
    const callbacks: Array<() => void> = [];
    const previous = globalThis.ResizeObserver;
    // @ts-expect-error stub mínimo de ResizeObserver para jsdom
    globalThis.ResizeObserver = class {
      constructor(cb: () => void) { callbacks.push(cb); }
      observe() {}
      disconnect() {}
    };
    try {
      render(<PriceChart model={buildMarketChartModel(payload())} />);
      await waitFor(() => expect(h.chart.addSeries).toHaveBeenCalled());
      expect(h.timeScale.fitContent).not.toHaveBeenCalled();
      hostWidth = 800;
      callbacks.forEach((cb) => cb());
      expect(h.timeScale.fitContent).toHaveBeenCalledTimes(1);
    } finally {
      globalThis.ResizeObserver = previous;
    }
  });

  it("expone el botón de bloque anterior solo si hay paginación", async () => {
    const withPagination = (onRequestEarlier: (beforeMs: number) => void) => (
      <PriceChart model={buildMarketChartModel(payload())}
        onRequestEarlier={onRequestEarlier} />
    );
    const handler = vi.fn();
    const {rerender} = render(withPagination(handler));
    const button = screen.getByTestId("market-chart-earlier");
    expect(button.textContent).toContain("Cargar anteriores");
    button.click();
    expect(handler).toHaveBeenCalledWith(T0);
    rerender(<PriceChart model={buildMarketChartModel(payload())} />);
    expect(screen.queryByTestId("market-chart-earlier")).toBeNull();
  });

  it("una interacción pide como máximo una página y anteponer no encadena", async () => {
    const handler = vi.fn();
    // Borde izquierdo visible = inicio del histórico observado (T0).
    h.state.range = {from: T0 / 1000, to: (T0 + H) / 1000};
    const first = buildMarketChartModel(payload());
    const {rerender} = render(
      <PriceChart model={first} onRequestEarlier={handler} />);
    await waitFor(() => expect(h.chart.addSeries).toHaveBeenCalledTimes(3));

    // Un gesto de rueda en el borde -> exactamente una petición.
    fireEvent.wheel(screen.getByTestId("market-chart"));
    await waitFor(() => expect(handler).toHaveBeenCalledTimes(1));
    expect(handler).toHaveBeenCalledWith(T0);

    // Anteponer una página mueve el rango visible y emite varios eventos; sin
    // gesto nuevo no se pide nada (ni cascada ni repetición del mismo rango).
    const prepended = buildMarketChartModel(payload([
      candle(T0 - 2 * H), candle(T0 - H), candle(T0), candle(T0 + H),
    ], {
      requested: {from_ms: T0 - 4 * H, to_ms: T0 + H},
      observed: {start_ms: T0 - 2 * H, end_ms: T0 + H},
      coverage: {
        ...payload().coverage,
        observed_start_ms: T0 - 2 * H,
        observed_end_ms: T0 + H,
        expected_bars: 4,
        actual_bars: 4,
        absent_ranges: [],
      },
    }));
    rerender(<PriceChart model={prepended} onRequestEarlier={handler} />);
    const rangeHandler = h.timeScale.subscribeVisibleTimeRangeChange
      .mock.calls.at(-1)![0] as (range: {from: number; to: number}) => void;
    h.state.range = {from: (T0 - 2 * H) / 1000, to: (T0 + H) / 1000};
    rangeHandler(h.state.range);
    rangeHandler({from: (T0 - 2 * H) / 1000, to: (T0 + 2 * H) / 1000});
    rangeHandler({from: (T0 - H) / 1000, to: (T0 + H) / 1000});
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(handler).toHaveBeenCalledTimes(1);

    // Un gesto nuevo sí puede pedir el bloque siguiente (ancla distinta).
    await new Promise((resolve) => setTimeout(resolve, 700));
    fireEvent.wheel(screen.getByTestId("market-chart"));
    await waitFor(() => expect(handler).toHaveBeenCalledTimes(2));
    expect(handler).toHaveBeenLastCalledWith(T0 - 2 * H);
  });
});
