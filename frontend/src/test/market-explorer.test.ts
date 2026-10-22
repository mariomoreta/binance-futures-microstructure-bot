import {afterEach, describe, expect, it, vi} from "vitest";
import {
  EXPLORER_PAGE_BARS,
  contractLabel,
  describeCoverage,
  extendWindow,
  fetchSeriesApi,
  formatUtc,
  initialWindow,
  searchContractsApi,
  windowLabel,
} from "@/lib/market-explorer";
import type {MarketSeriesPayload} from "@/lib/market-chart-contract";

const HOUR = 3_600_000;
const T0 = 1_790_000_000_000;

function jsonResponse(body: unknown, status = 200) {
  return {ok: status >= 200 && status < 300, status, json: async () => body};
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("cliente del explorador — consultas acotadas", () => {
  it("construye la búsqueda de catálogo con límite explícito", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      available: true, results: [], result_count: 0,
    }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await searchContractsApi({query: " BTC ", limit: 20});
    expect(result.ok).toBe(true);
    const url = String(fetchMock.mock.calls[0]![0]);
    expect(url.startsWith("/api/v1/market-contracts?")).toBe(true);
    expect(url).toContain("q=BTC");
    expect(url).toContain("limit=20");
    expect(url).not.toContain("eligible");
    expect(fetchMock.mock.calls[0]![1]).toMatchObject({cache: "no-store"});
  });

  it("añade elegibilidad y refresco solo cuando se piden", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({available: true, results: []}));
    vi.stubGlobal("fetch", fetchMock);
    await searchContractsApi({eligibleOnly: true, refresh: true});
    const url = String(fetchMock.mock.calls[0]![0]);
    expect(url).toContain("eligible=1");
    expect(url).toContain("refresh=1");
  });

  it("propaga el error del BFF sin inventar resultados", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(
      {error: "CATALOG_UNAVAILABLE", detail: "sin caché"}, 503)));
    const result = await searchContractsApi({query: "BTC"});
    expect(result.ok).toBe(false);
    expect(result.status).toBe(503);
    expect(result.error).toBe("CATALOG_UNAVAILABLE");
    expect(result.detail).toBe("sin caché");
    expect(result.data).toBeUndefined();
  });

  it("distingue aborto de fallo de red", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(
      new DOMException("The operation was aborted.", "AbortError")));
    const aborted = await searchContractsApi({query: "BTC"});
    expect(aborted.error).toBe("ABORTED");

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    const failed = await searchContractsApi({query: "BTC"});
    expect(failed.error).toBe("NETWORK_ERROR");
    expect(failed.status).toBe(0);
  });

  it("pide la serie con ventana, páginas y límite de página explícitos", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({candles: []}));
    vi.stubGlobal("fetch", fetchMock);
    await fetchSeriesApi({
      symbol: "BTCUSDT", interval: "4h", fromMs: T0, toMs: T0 + HOUR,
      bars: 300, pages: 1, pageLimit: 300, source: "klines", probeEarliest: true,
    });
    const url = String(fetchMock.mock.calls[0]![0]);
    expect(url.startsWith("/api/v1/market-series?")).toBe(true);
    expect(url).toContain("symbol=BTCUSDT");
    expect(url).toContain("interval=4h");
    expect(url).toContain(`from_ms=${T0}`);
    expect(url).toContain(`to_ms=${T0 + HOUR}`);
    expect(url).toContain("pages=1");
    expect(url).toContain("page_limit=300");
    expect(url).toContain("source=klines");
    expect(url).toContain("probe_earliest=1");
  });
});

describe("ventanas de paginación", () => {
  it("la ventana inicial cubre exactamente el bloque pedido", () => {
    const {fromMs, toMs} = initialWindow(T0, HOUR);
    expect(toMs).toBe(T0);
    expect(toMs - fromMs).toBe((EXPLORER_PAGE_BARS - 1) * HOUR);
  });

  it("extender hacia atrás añade un bloque sin solapar el borde", () => {
    const {fromMs, toMs} = extendWindow(T0, HOUR, 100);
    expect(toMs).toBe(T0);
    expect(toMs - fromMs).toBe(100 * HOUR);
  });
});

describe("etiquetas de procedencia y cobertura", () => {
  const base: MarketSeriesPayload = {
    contract_version: "market-series/v1", venue: "binance",
    market_type: "usd_m_futures", api_family: "fapi", source: "klines",
    endpoint: "/fapi/v1/klines", symbol: "BTCUSDT", interval: "1h",
    interval_ms: HOUR, contract: null,
    requested: {from_ms: T0, to_ms: T0 + HOUR},
    observed: {start_ms: T0, end_ms: T0 + HOUR},
    candles: [],
    coverage: {
      state: "PARTIAL", observed_start_ms: T0, observed_end_ms: T0 + HOUR,
      expected_bars: 4, actual_bars: 3, gap_count: 1,
      gaps: [[T0 + HOUR, T0 + HOUR]],
      absent_ranges: [[T0 - HOUR, T0 - HOUR]], exhausted_before: true,
      earliest_available_ms: T0 - HOUR, note: "",
    },
    volume: {
      available: true, base_asset: "BTC", quote_asset: "USDT",
      fields: ["base_volume", "quote_volume"], reason: null,
    },
    freshness: {
      state: "HISTORICAL_ON_DEMAND", newest_open_ms: T0 + HOUR,
      newest_close_ms: T0 + 2 * HOUR - 1, fetched_at_ms: T0, age_ms: 1,
      provisional: false, note: "",
    },
    fetch: {
      allowed: true, performed: false, status: "not_requested", error: null,
      requests: 0, pages: 0, retries: 0, failures: 0, detail: null,
      retry_after_ms: null,
    },
    labels: {mode: "HISTORICAL_ON_DEMAND", live: false, banner: "HISTORICO"},
    generated_at_ms: T0, notes: [],
  };

  it("describe huecos, ausencia y fin de histórico por separado", () => {
    const text = describeCoverage(base);
    expect(text).toContain("Estado PARTIAL");
    expect(text).toContain("3/4 velas");
    expect(text).toContain("1 huecos");
    expect(text).toContain("1 tramo(s) sin cobertura");
    expect(text).toContain("fin de histórico");
  });

  it("el contrato desconocido se declara, no se inventa", () => {
    expect(contractLabel(null)).toBe("sin contrato en catálogo");
    expect(contractLabel({
      symbol: "X", base_asset: null, quote_asset: null, contract_type: null,
      status: null, eligible: false, exclusion_reasons: ["status=SETTLING"],
    })).toBe("UNKNOWN · UNKNOWN · no elegible");
  });

  it("formatea tiempos UTC sin sustituir desconocidos por cero", () => {
    expect(formatUtc(null)).toBe("UNKNOWN");
    expect(formatUtc(T0)).toBe(new Date(T0).toISOString().replace(/\.000Z$/, "Z"));
    expect(windowLabel(T0, T0 + HOUR)).toContain("→");
  });
});
