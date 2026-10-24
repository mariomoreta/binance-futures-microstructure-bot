/**
 * Temporalidades del explorador de contratos.
 *
 * `1m` faltaba en el selector aunque el backend ya lo soporta
 * (`EXPLORABLE_INTERVALS` incluye "1m"): la ventana de verificación por el camino
 * real exige que el gráfico pueda abrir `BTCUSDT`/`1m`, y sin la opción no había
 * camino de usuario posible.
 *
 * Se comprueba con dobles: el histórico/estado por `fetch` y una `EventSource`
 * falsa que registra la URL de suscripción y si se cerró.
 */
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {act, cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import type {MarketCatalogPayload, MarketSeriesPayload} from "@/lib/market-chart-contract";

const MIN = 60_000;
const H = 3_600_000;
const T0 = 1_790_000_000_000;

const api = vi.hoisted(() => ({
  searchContractsApi: vi.fn(),
  fetchSeriesApi: vi.fn(),
}));

vi.mock("@/lib/market-explorer", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/market-explorer")>();
  return {...actual, ...api};
});

vi.mock("@/components/chart/PriceChart", () => ({
  PriceChart: ({model}: {model: {identity: {symbol: string; interval: string}}}) => (
    <div data-testid="chart-stub"
      data-symbol={model.identity.symbol}
      data-interval={model.identity.interval}/>
  ),
}));

import {ContractExplorer} from "@/components/market-lab/ContractExplorer";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(): void {}

  close(): void {
    this.closed = true;
  }
}

const BTC = {
  symbol: "BTCUSDT", base_asset: "BTC", quote_asset: "USDT",
  contract_type: "PERPETUAL", status: "TRADING", eligible: true,
  exclusion_reasons: [],
};

function catalog(): MarketCatalogPayload {
  return {
    contract_version: "market-catalog/v1", venue: "binance",
    market_type: "usd_m_futures", api_family: "fapi",
    endpoint: "/fapi/v1/exchangeInfo", spot_included: false, available: true,
    reason: null, query: "", results: [BTC], result_count: 1, truncated: false,
    catalog: {
      entries: 900, fetched_at_ms: T0, age_ms: 1000, stale: false,
      endpoint: "/fapi/v1/exchangeInfo",
    },
    refresh: {refreshed: false, reason: "FRESH_CACHE", requests: 0},
    notes: [],
  };
}

function series(symbol: string, interval: string,
  overrides: Partial<MarketSeriesPayload> = {}): MarketSeriesPayload {
  const step = interval === "1m" ? MIN : H;
  const candles = [T0, T0 + step].map((openTime, index) => ({
    open_time_ms: openTime,
    close_time_ms: openTime + step - 1,
    open: "100", high: "101", low: "99", close: String(100 + index),
    base_volume: "12.5", quote_volume: "1250", trade_count: 10,
    provisional: false, fetched_at_ms: T0, storage: "cache",
  }));
  return {
    contract_version: "market-series/v1", venue: "binance",
    market_type: "usd_m_futures", api_family: "fapi", source: "klines",
    endpoint: "/fapi/v1/klines", symbol, interval, interval_ms: step,
    contract: {symbol, base_asset: symbol.replace("USDT", ""), quote_asset: "USDT",
      contract_type: "PERPETUAL", status: "TRADING", eligible: true,
      exclusion_reasons: []},
    requested: {from_ms: T0 - 2 * step, to_ms: T0 + step},
    observed: {start_ms: T0, end_ms: T0 + step},
    candles,
    coverage: {
      state: "PARTIAL", observed_start_ms: T0, observed_end_ms: T0 + step,
      expected_bars: 2, actual_bars: 2, gap_count: 0, gaps: [],
      absent_ranges: [[T0 - 2 * step, T0 - step]], exhausted_before: false,
      earliest_available_ms: null, note: "",
    },
    volume: {
      available: true, base_asset: symbol.replace("USDT", ""), quote_asset: "USDT",
      fields: ["base_volume", "quote_volume"], reason: null,
    },
    freshness: {
      state: "HISTORICAL_ON_DEMAND", newest_open_ms: T0 + step,
      newest_close_ms: T0 + 2 * step - 1, fetched_at_ms: T0 + 1000, age_ms: 1000,
      provisional: false, note: "",
    },
    fetch: {
      allowed: true, performed: true, status: "ok", error: null, requests: 1,
      pages: 1, retries: 0, failures: 0, detail: null, bars_stored: 2,
      retry_after_ms: null,
    },
    storage: {canonical_error: null, canonical_rows: 0, cache_rows: 2},
    labels: {
      mode: "HISTORICAL_ON_DEMAND", live: false,
      banner: "HISTORICO / CONSULTA BAJO DEMANDA",
    },
    generated_at_ms: T0 + 2 * step, notes: [], ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return {promise, resolve};
}

const originalEventSource = (globalThis as unknown as {EventSource?: unknown}).EventSource;
const originalFetch = globalThis.fetch;

function installEventSource(): void {
  FakeEventSource.instances = [];
  (globalThis as unknown as {EventSource: unknown}).EventSource = FakeEventSource;
}

function mockStatus(available: boolean, detail: string | null = null): void {
  globalThis.fetch = vi.fn().mockResolvedValue({
    json: async () => ({available, detail}),
  }) as unknown as typeof fetch;
}

beforeEach(() => {
  vi.clearAllMocks();
  api.searchContractsApi.mockResolvedValue({ok: true, data: catalog(), status: 200});
  api.fetchSeriesApi.mockImplementation(async (args: {symbol: string; interval: string}) => ({
    ok: true, data: series(args.symbol, args.interval), status: 200,
  }));
  installEventSource();
  mockStatus(true);
});

afterEach(() => {
  cleanup();
  (globalThis as unknown as {EventSource?: unknown}).EventSource = originalEventSource;
  globalThis.fetch = originalFetch;
});

describe("ContractExplorer — temporalidad 1m", () => {
  it("ofrece 1m sin perder los demás intervalos y mantiene 1h por defecto", async () => {
    render(<ContractExplorer/>);
    fireEvent.click(await screen.findByTestId("explorer-open-BTCUSDT"));
    const select = (await screen.findByTestId("explorer-interval")) as HTMLSelectElement;
    expect([...select.options].map((option) => option.value))
      .toEqual(["1m", "15m", "1h", "4h", "1d"]);
    expect(select.value).toBe("1h");
  });

  it("con 1m pide histórico y abre la suscripción con BTCUSDT/1m", async () => {
    render(<ContractExplorer/>);
    fireEvent.click(await screen.findByTestId("explorer-open-BTCUSDT"));
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByTestId("explorer-interval"), {target: {value: "1m"}});
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(2));
    expect(api.fetchSeriesApi.mock.calls[1]![0]).toMatchObject({
      symbol: "BTCUSDT", interval: "1m", bars: 300, pages: 1, pageLimit: 300,
    });

    const chart = await screen.findByTestId("chart-stub");
    expect(chart.getAttribute("data-symbol")).toBe("BTCUSDT");
    expect(chart.getAttribute("data-interval")).toBe("1m");

    // El gráfico de 1h se cierra al cambiar de temporalidad; el vigente es 1m.
    await waitFor(() => expect(
      FakeEventSource.instances.some((item) => item.url.includes("interval=1m")),
    ).toBe(true));
    const current = FakeEventSource.instances.at(-1)!;
    expect(current.closed).toBe(false);
    const source = new URL(current.url, "http://127.0.0.1:3020");
    expect(source.pathname).toBe("/api/v1/market-stream");
    expect(source.searchParams.get("symbol")).toBe("BTCUSDT");
    expect(source.searchParams.get("interval")).toBe("1m");
  });

  it("cambiar de intervalo descarta la respuesta anterior y cierra la suscripción previa", async () => {
    const oneMinute = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    api.fetchSeriesApi
      .mockReturnValueOnce({ok: true, data: series("BTCUSDT", "1h"), status: 200})
      .mockReturnValueOnce(oneMinute.promise);
    render(<ContractExplorer/>);
    fireEvent.click(await screen.findByTestId("explorer-open-BTCUSDT"));
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByTestId("explorer-interval"), {target: {value: "1m"}});
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(2));
    const pendingCall = api.fetchSeriesApi.mock.calls[1]![0] as {signal?: AbortSignal};
    expect(pendingCall.signal?.aborted).toBe(false);

    await act(async () => {
      oneMinute.resolve({ok: true, data: series("BTCUSDT", "1m"), status: 200});
    });
    await waitFor(() => expect(
      FakeEventSource.instances.some((item) => item.url.includes("interval=1m")),
    ).toBe(true));
    const openOneMinute = FakeEventSource.instances.filter(
      (item) => item.url.includes("interval=1m") && !item.closed);
    expect(openOneMinute.length).toBe(1);
    const oneMinuteSource = openOneMinute[0]!;
    expect(oneMinuteSource.url).toContain("from_ms=");

    fireEvent.change(screen.getByTestId("explorer-interval"), {target: {value: "15m"}});
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(3));
    // La respuesta de 1m que llegue tarde ya no puede pintar el gráfico.
    expect(pendingCall.signal?.aborted).toBe(true);
    await waitFor(() => expect(oneMinuteSource.closed).toBe(true));

    await waitFor(() => expect(
      FakeEventSource.instances.some((item) => item.url.includes("interval=15m")),
    ).toBe(true));
    const fifteenSource = FakeEventSource.instances
      .find((item) => item.url.includes("interval=15m"))!;
    expect(fifteenSource.closed).toBe(false);
    const chart = await screen.findByTestId("chart-stub");
    expect(chart.getAttribute("data-interval")).toBe("15m");
  });

  it("con el servicio detenido no declara LIVE ni abre suscripción", async () => {
    mockStatus(false, "ECONNREFUSED");
    render(<ContractExplorer/>);
    fireEvent.click(await screen.findByTestId("explorer-open-BTCUSDT"));
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(1));

    const state = await screen.findByTestId("explorer-stream-state");
    expect(state.textContent).toContain("DESCONECTADO");
    expect(screen.getByTestId("explorer-stream-live").textContent).toBe("no LIVE");
    expect(screen.getByTestId("explorer-stream-down").textContent)
      .toContain("no se declara LIVE");
    expect(FakeEventSource.instances.length).toBe(0);
  });
});
