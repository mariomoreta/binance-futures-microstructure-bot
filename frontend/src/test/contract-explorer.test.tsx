import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {act, cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import type {MarketCatalogPayload, MarketSeriesPayload} from "@/lib/market-chart-contract";

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

// El gráfico real se sustituye por un doble identificable: aquí se prueba el
// flujo de búsqueda/selección/paginación/errores y el descarte de respuestas
// tardías, no el cableado de Lightweight Charts (cubierto aparte).
vi.mock("@/components/chart/PriceChart", () => ({
  PriceChart: ({model, onRequestEarlier, loadingEarlier, earlierExhausted}: {
    model: {
      identity: {symbol: string; interval: string};
      candles: {closed: unknown[]; provisional: unknown[]};
      capabilities: {earlier_from_ms: number | null};
      volume_unit: string | null;
      volume_status: string;
    };
    onRequestEarlier?: (beforeMs: number) => void;
    loadingEarlier?: boolean;
    earlierExhausted?: boolean;
  }) => (
    <div data-testid="chart-stub" data-symbol={model.identity.symbol}
      data-interval={model.identity.interval}
      data-bars={model.candles.closed.length}
      data-provisional={model.candles.provisional.length}
      data-volume={model.volume_status === "AVAILABLE" ? model.volume_unit : "UNAVAILABLE"}>
      <button type="button" data-testid="chart-earlier-trigger"
        disabled={loadingEarlier || earlierExhausted}
        onClick={() => onRequestEarlier?.(model.capabilities.earlier_from_ms ?? 0)}>
        prev
      </button>
    </div>
  ),
}));

import {ContractExplorer} from "@/components/market-lab/ContractExplorer";

const BTC = {
  symbol: "BTCUSDT", base_asset: "BTC", quote_asset: "USDT",
  contract_type: "PERPETUAL", status: "TRADING", eligible: true,
  exclusion_reasons: [],
};
const ETH = {
  symbol: "ETHUSDT", base_asset: "ETH", quote_asset: "USDT",
  contract_type: "PERPETUAL", status: "TRADING", eligible: true,
  exclusion_reasons: [],
};
const OLD = {
  symbol: "OLDUSDT", base_asset: "OLD", quote_asset: "USDT",
  contract_type: "PERPETUAL", status: "SETTLING", eligible: false,
  exclusion_reasons: ["status=SETTLING"],
};

function catalog(overrides: Partial<MarketCatalogPayload> = {}): MarketCatalogPayload {
  return {
    contract_version: "market-catalog/v1", venue: "binance",
    market_type: "usd_m_futures", api_family: "fapi",
    endpoint: "/fapi/v1/exchangeInfo", spot_included: false, available: true,
    reason: null, query: "", results: [BTC, ETH, OLD], result_count: 3,
    truncated: false,
    catalog: {
      entries: 900, fetched_at_ms: T0, age_ms: 1000, stale: false,
      endpoint: "/fapi/v1/exchangeInfo",
    },
    refresh: {refreshed: false, reason: "FRESH_CACHE", requests: 0},
    notes: [],
    ...overrides,
  };
}

function series(symbol: string, interval: string, bars: number[],
  overrides: Partial<MarketSeriesPayload> = {}): MarketSeriesPayload {
  const candles = bars.map((openTime, index) => ({
    open_time_ms: openTime,
    close_time_ms: openTime + H - 1,
    open: "100", high: "101", low: "99", close: String(100 + index),
    base_volume: "12.5", quote_volume: "1250", trade_count: 10,
    provisional: false, fetched_at_ms: T0, storage: "cache",
  }));
  const first = bars[0] ?? T0;
  const last = bars[bars.length - 1] ?? T0;
  return {
    contract_version: "market-series/v1", venue: "binance",
    market_type: "usd_m_futures", api_family: "fapi", source: "klines",
    endpoint: "/fapi/v1/klines", symbol, interval, interval_ms: H,
    contract: {symbol, base_asset: symbol.replace("USDT", ""), quote_asset: "USDT",
      contract_type: "PERPETUAL", status: "TRADING", eligible: true,
      exclusion_reasons: []},
    requested: {from_ms: first - 2 * H, to_ms: last},
    observed: {start_ms: first, end_ms: last},
    candles,
    coverage: {
      state: "PARTIAL", observed_start_ms: first, observed_end_ms: last,
      expected_bars: candles.length, actual_bars: candles.length, gap_count: 0,
      gaps: [], absent_ranges: [[first - 2 * H, first - H]],
      exhausted_before: false, earliest_available_ms: null, note: "",
    },
    volume: {
      available: true, base_asset: symbol.replace("USDT", ""), quote_asset: "USDT",
      fields: ["base_volume", "quote_volume"], reason: null,
    },
    freshness: {
      state: "HISTORICAL_ON_DEMAND", newest_open_ms: last,
      newest_close_ms: last + H - 1, fetched_at_ms: T0 + 1000, age_ms: 1000,
      provisional: false, note: "",
    },
    fetch: {
      allowed: true, performed: true, status: "ok", error: null, requests: 1,
      pages: 1, retries: 0, failures: 0, detail: null, bars_stored: candles.length,
      retry_after_ms: null,
    },
    storage: {canonical_error: null, canonical_rows: 0, cache_rows: candles.length},
    labels: {
      mode: "HISTORICAL_ON_DEMAND", live: false,
      banner: "HISTORICO / CONSULTA BAJO DEMANDA",
    },
    generated_at_ms: T0 + 2 * H, notes: [], ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return {promise, resolve};
}

beforeEach(() => {
  vi.clearAllMocks();
  api.searchContractsApi.mockResolvedValue({ok: true, data: catalog(), status: 200});
});
afterEach(() => cleanup());

async function selectSymbol(symbol: string) {
  const button = await screen.findByTestId(`explorer-open-${symbol}`);
  fireEvent.click(button);
}

describe("ContractExplorer — búsqueda, selección y paginación (A/C/D/E)", () => {
  it("carga el catálogo al montar y NO pide histórico sin selección", async () => {
    render(<ContractExplorer/>);
    await waitFor(() => expect(screen.getByTestId("explorer-row-BTCUSDT")).toBeTruthy());
    expect(api.searchContractsApi).toHaveBeenCalledTimes(1);
    expect(api.fetchSeriesApi).not.toHaveBeenCalled();
    // El contrato no elegible se muestra con motivos (nunca se oculta).
    const row = screen.getByTestId("explorer-row-OLDUSDT");
    expect(row.textContent).toContain("no elegible");
    expect(row.textContent).toContain("status=SETTLING");
    expect(screen.getByTestId("explorer-catalog-state").textContent)
      .toContain("900 contratos");
  });

  it("A: busca, selecciona y muestra histórico con procedencia", async () => {
    const pending = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    api.fetchSeriesApi.mockReturnValueOnce(pending.promise);
    render(<ContractExplorer/>);
    await waitFor(() => expect(screen.getByTestId("explorer-row-BTCUSDT")).toBeTruthy());

    fireEvent.change(screen.getByTestId("explorer-query"), {target: {value: "BTC"}});
    fireEvent.click(screen.getByTestId("explorer-search"));
    await waitFor(() => expect(api.searchContractsApi).toHaveBeenCalledTimes(2));
    expect(api.searchContractsApi.mock.calls[1]![0]).toMatchObject({query: "BTC"});

    await selectSymbol("BTCUSDT");
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(1));
    expect(api.fetchSeriesApi.mock.calls[0]![0]).toMatchObject({
      symbol: "BTCUSDT", interval: "1h", bars: 300, pages: 1, pageLimit: 300,
    });
    expect(screen.getByText(/Cargando histórico/)).toBeTruthy();

    await act(async () => {
      pending.resolve({ok: true, data: series("BTCUSDT", "1h", [T0, T0 + H]), status: 200});
    });
    const chart = await screen.findByTestId("chart-stub");
    expect(chart.getAttribute("data-symbol")).toBe("BTCUSDT");
    expect(chart.getAttribute("data-interval")).toBe("1h");
    expect(chart.getAttribute("data-bars")).toBe("2");
    expect(chart.getAttribute("data-volume")).toBe("BTC");
    expect(screen.getByTestId("explorer-provenance").textContent)
      .toContain("canónico 0 · caché 2");
    expect(screen.getByTestId("explorer-coverage").textContent).toContain("PARTIAL");
  });

  it("C: pide el bloque anterior y conserva la ventana al recibirlo", async () => {
    const first = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    api.fetchSeriesApi.mockReturnValueOnce(first.promise);
    render(<ContractExplorer/>);
    await waitFor(() => expect(screen.getByTestId("explorer-row-BTCUSDT")).toBeTruthy());
    await selectSymbol("BTCUSDT");
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(1));
    const firstArgs = api.fetchSeriesApi.mock.calls[0]![0] as {fromMs: number; toMs: number};
    await act(async () => {
      first.resolve({ok: true, data: series("BTCUSDT", "1h", [T0, T0 + H]), status: 200});
    });

    const second = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    api.fetchSeriesApi.mockReturnValueOnce(second.promise);
    fireEvent.click(await screen.findByTestId("chart-earlier-trigger"));
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(2));
    const secondArgs = api.fetchSeriesApi.mock.calls[1]![0] as {fromMs: number; toMs: number};
    // Bloque estrictamente anterior al borde cargado: no repite la ventana
    // reciente (eso producía solapamiento y el contador no crecía).
    expect(firstArgs.toMs).toBeGreaterThan(T0);
    expect(secondArgs.toMs).toBe(T0 - H);
    expect(secondArgs.fromMs).toBe(T0 - 300 * H);

    await act(async () => {
      second.resolve({ok: true, data: series("BTCUSDT", "1h", [T0 - 2 * H, T0 - H, T0, T0 + H]), status: 200});
    });
    const chart = await screen.findByTestId("chart-stub");
    // Antepone el bloque y conserva el extremo reciente (T0+H una sola vez).
    expect(chart.getAttribute("data-bars")).toBe("4");
  });

  it("C2: solapamiento legítimo no exige +300 velas ni declara pérdida", async () => {
    const bars300 = Array.from({length: 300}, (_, index) => T0 + index * H);
    const first = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    api.fetchSeriesApi.mockReturnValueOnce(first.promise);
    render(<ContractExplorer/>);
    await waitFor(() => expect(screen.getByTestId("explorer-row-BTCUSDT")).toBeTruthy());
    await selectSymbol("BTCUSDT");
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(1));
    await act(async () => {
      first.resolve({ok: true, data: series("BTCUSDT", "1h", bars300), status: 200});
    });
    expect((await screen.findByTestId("chart-stub")).getAttribute("data-bars")).toBe("300");

    // Respuesta de 300 velas que solapa 297: solo 3 son nuevas por delante.
    const overlapping = Array.from({length: 300}, (_, index) => T0 - 3 * H + index * H);
    const second = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    api.fetchSeriesApi.mockReturnValueOnce(second.promise);
    fireEvent.click(await screen.findByTestId("chart-earlier-trigger"));
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(2));
    await act(async () => {
      second.resolve({ok: true, data: series("BTCUSDT", "1h", overlapping), status: 200});
    });

    const chart = await screen.findByTestId("chart-stub");
    // 300 + 3 únicas = 303: el contador refleja velas reales, no el tamaño
    // nominal de la página.
    expect(chart.getAttribute("data-bars")).toBe("303");
    expect(chart.getAttribute("data-symbol")).toBe("BTCUSDT");
    expect((screen.getByTestId("chart-earlier-trigger") as HTMLButtonElement).disabled).toBe(false);
  });

  it("C3: un bloque sin velas nuevas marca el histórico como agotado", async () => {
    const bars = [T0, T0 + H, T0 + 2 * H];
    const first = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    api.fetchSeriesApi.mockReturnValueOnce(first.promise);
    render(<ContractExplorer/>);
    await waitFor(() => expect(screen.getByTestId("explorer-row-BTCUSDT")).toBeTruthy());
    await selectSymbol("BTCUSDT");
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(1));
    await act(async () => {
      first.resolve({ok: true, data: series("BTCUSDT", "1h", bars), status: 200});
    });

    const second = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    api.fetchSeriesApi.mockReturnValueOnce(second.promise);
    fireEvent.click(await screen.findByTestId("chart-earlier-trigger"));
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(2));
    await act(async () => {
      // El backend devuelve lo mismo ya cargado: no hay historia anterior.
      second.resolve({ok: true, data: series("BTCUSDT", "1h", bars), status: 200});
    });

    const chart = await screen.findByTestId("chart-stub");
    expect(chart.getAttribute("data-bars")).toBe("3");
    await waitFor(() => expect((screen.getByTestId("chart-earlier-trigger") as HTMLButtonElement).disabled).toBe(true));
  });

  it("D: descarta respuestas tardías al cambiar de símbolo", async () => {
    const btc = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    const eth = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    api.fetchSeriesApi.mockReturnValueOnce(btc.promise).mockReturnValueOnce(eth.promise);
    render(<ContractExplorer/>);
    await waitFor(() => expect(screen.getByTestId("explorer-row-BTCUSDT")).toBeTruthy());
    await selectSymbol("BTCUSDT");
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(1));
    await selectSymbol("ETHUSDT");
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(2));
    // Llega ETH primero y después la respuesta antigua de BTC: se descarta.
    await act(async () => {
      eth.resolve({ok: true, data: series("ETHUSDT", "1h", [T0]), status: 200});
    });
    await act(async () => {
      btc.resolve({ok: true, data: series("BTCUSDT", "1h", [T0, T0 + H, T0 + 2 * H]), status: 200});
    });
    const chart = await screen.findByTestId("chart-stub");
    expect(chart.getAttribute("data-symbol")).toBe("ETHUSDT");
    expect(chart.getAttribute("data-bars")).toBe("1");
  });

  it("D: cambiar la temporalidad pide la nueva y descarta la anterior", async () => {
    const oneHour = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    const fourHours = deferred<{ok: boolean; data?: MarketSeriesPayload; status: number}>();
    api.fetchSeriesApi.mockReturnValueOnce(oneHour.promise).mockReturnValueOnce(fourHours.promise);
    render(<ContractExplorer/>);
    await waitFor(() => expect(screen.getByTestId("explorer-row-BTCUSDT")).toBeTruthy());
    await selectSymbol("BTCUSDT");
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId("explorer-interval"), {target: {value: "4h"}});
    await waitFor(() => expect(api.fetchSeriesApi).toHaveBeenCalledTimes(2));
    expect(api.fetchSeriesApi.mock.calls[1]![0]).toMatchObject({symbol: "BTCUSDT", interval: "4h"});
    await act(async () => {
      fourHours.resolve({ok: true, data: series("BTCUSDT", "4h", [T0, T0 + 4 * H]), status: 200});
    });
    await act(async () => {
      oneHour.resolve({ok: true, data: series("BTCUSDT", "1h", [T0]), status: 200});
    });
    const chart = await screen.findByTestId("chart-stub");
    expect(chart.getAttribute("data-interval")).toBe("4h");
    expect(chart.getAttribute("data-bars")).toBe("2");
  });

  it("E: declara catálogo no disponible sin inventar contratos", async () => {
    api.searchContractsApi.mockResolvedValueOnce({
      ok: true,
      data: catalog({available: false, results: [], result_count: 0, reason: "CATALOG_NOT_CACHED"}),
      status: 200,
    });
    render(<ContractExplorer/>);
    expect((await screen.findByTestId("explorer-catalog-unavailable")).textContent)
      .toContain("no está en caché");
  });

  it("E: muestra el error del catálogo tal cual", async () => {
    api.searchContractsApi.mockResolvedValueOnce({
      ok: false, status: 502, error: "PYTHON_EMPTY_OUTPUT", detail: "fallo",
    });
    render(<ContractExplorer/>);
    const alert = await screen.findByTestId("explorer-catalog-error");
    expect(alert.textContent).toContain("PYTHON_EMPTY_OUTPUT");
    expect(alert.textContent).toContain("fallo");
  });

  it("E: error de histórico, presupuesto agotado y falta de cobertura son visibles", async () => {
    render(<ContractExplorer/>);
    await waitFor(() => expect(screen.getByTestId("explorer-row-BTCUSDT")).toBeTruthy());

    // 1) error de transporte/validación
    api.fetchSeriesApi.mockResolvedValueOnce({
      ok: false, status: 502, error: "SERIES_UNAVAILABLE", detail: "sin red",
    });
    await selectSymbol("BTCUSDT");
    expect((await screen.findByTestId("explorer-series-error")).textContent)
      .toContain("SERIES_UNAVAILABLE");

    // 2) presupuesto agotado: se muestra lo almacenado y se avisa
    api.fetchSeriesApi.mockResolvedValueOnce({
      ok: true,
      data: series("BTCUSDT", "1h", [T0], {
        fetch: {
          allowed: true, performed: false, status: "budget_exhausted",
          error: "RATE_BUDGET_EXHAUSTED", requests: 0, pages: 0, retries: 0,
          failures: 0, detail: "presupuesto agotado", retry_after_ms: 60_000,
        },
      }),
      status: 200,
    });
    fireEvent.click(screen.getByTestId("explorer-open-ETHUSDT"));
    const warning = await screen.findByTestId("explorer-fetch-warning");
    expect(warning.textContent).toContain("RATE_BUDGET_EXHAUSTED");
    expect(warning.textContent).toContain("no se reintenta en bucle");

    // 3) sin cobertura: no se rellena
    api.fetchSeriesApi.mockResolvedValueOnce({
      ok: true,
      data: series("BTCUSDT", "1h", [], {
        observed: {start_ms: null, end_ms: null},
        coverage: {
          state: "NO_COVERAGE", observed_start_ms: null, observed_end_ms: null,
          expected_bars: 0, actual_bars: 0, gap_count: null, gaps: [],
          absent_ranges: [[T0, T0 + H]], exhausted_before: false,
          earliest_available_ms: null, note: "",
        },
        volume: {
          available: false, base_asset: "BTC", quote_asset: "USDT", fields: [],
          reason: "SIN_VOLUMEN_EN_LO_ALMACENADO",
        },
      }),
      status: 200,
    });
    await selectSymbol("BTCUSDT");
    expect((await screen.findByTestId("explorer-no-coverage")).textContent)
      .toContain("Sin cobertura");
  });
});
