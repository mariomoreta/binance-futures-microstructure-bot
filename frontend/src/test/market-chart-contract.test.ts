import {describe, expect, it} from "vitest";
import {
  MARKET_CHART_CONTRACT_VERSION,
  buildMarketChartModel,
  mergeEarlierSeries,
  paperMarkersLeaked,
  type MarketSeriesPayload,
} from "@/lib/market-chart-contract";

const HOUR = 3_600_000;
const T0 = 1_790_000_000_000;

function candle(openTime: number, opts: {
  open?: string; high?: string; low?: string; close?: string;
  baseVolume?: string | null; quoteVolume?: string | null;
  provisional?: boolean; closeTime?: number | null;
} = {}) {
  return {
    open_time_ms: openTime,
    close_time_ms: opts.closeTime === undefined
      ? (opts.provisional ? null : openTime + HOUR - 1)
      : opts.closeTime,
    open: opts.open ?? "100",
    high: opts.high ?? "101",
    low: opts.low ?? "99",
    close: opts.close ?? "100.5",
    base_volume: opts.baseVolume === undefined ? "12.5" : opts.baseVolume,
    quote_volume: opts.quoteVolume === undefined ? "1250" : opts.quoteVolume,
    trade_count: 10,
    provisional: opts.provisional === true,
    fetched_at_ms: T0 + 5000,
    storage: "cache",
  };
}

function payload(overrides: Partial<MarketSeriesPayload> = {}): MarketSeriesPayload {
  const candles = [
    candle(T0 + HOUR, {open: "101", high: "102", low: "100", close: "101.5"}),
    candle(T0, {open: "100", high: "101", low: "99", close: "100.5"}),
  ];
  return {
    contract_version: "market-series/v1",
    venue: "binance",
    market_type: "usd_m_futures",
    api_family: "fapi",
    source: "klines",
    endpoint: "/fapi/v1/klines",
    symbol: "BTCUSDT",
    interval: "1h",
    interval_ms: HOUR,
    contract: {
      symbol: "BTCUSDT", base_asset: "BTC", quote_asset: "USDT",
      contract_type: "PERPETUAL", status: "TRADING", eligible: true,
      exclusion_reasons: [],
    },
    requested: {from_ms: T0, to_ms: T0 + HOUR},
    observed: {start_ms: T0, end_ms: T0 + HOUR},
    candles,
    coverage: {
      state: "COVERED", observed_start_ms: T0, observed_end_ms: T0 + HOUR,
      expected_bars: 2, actual_bars: 2, gap_count: 0, gaps: [],
      absent_ranges: [], exhausted_before: false,
      earliest_available_ms: null, note: "",
    },
    volume: {
      available: true, base_asset: "BTC", quote_asset: "USDT",
      fields: ["base_volume", "quote_volume"], reason: null,
    },
    freshness: {
      state: "HISTORICAL_ON_DEMAND", newest_open_ms: T0 + HOUR,
      newest_close_ms: T0 + 2 * HOUR - 1, fetched_at_ms: T0 + 5000,
      age_ms: 42_000, provisional: false, note: "",
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
    generated_at_ms: T0 + 10 * HOUR,
    notes: ["nota del backend"],
    ...overrides,
  };
}

describe("market-chart/v1 — adaptación del payload del backend", () => {
  it("ordena, deduplica por apertura y conserva el último valor", () => {
    const duplicated = payload({
      candles: [
        candle(T0 + HOUR, {close: "101.5"}),
        candle(T0, {close: "100.5"}),
        candle(T0, {close: "100.9"}),
      ],
    });
    const model = buildMarketChartModel(duplicated);
    expect(model.candles.closed.map((c) => c.open_time_ms)).toEqual([T0, T0 + HOUR]);
    expect(model.candles.closed[0]!.close).toBe(100.9);
    expect(model.candles.unusable).toBe(0);
  });

  it("separa la vela provisional y no le inventa cierre", () => {
    const model = buildMarketChartModel(payload({
      candles: [
        candle(T0, {}),
        candle(T0 + HOUR, {provisional: true, closeTime: null}),
      ],
    }));
    expect(model.candles.closed).toHaveLength(1);
    expect(model.candles.provisional).toHaveLength(1);
    expect(model.candles.provisional[0]!.close_time_ms).toBeNull();
    expect(model.candles.provisional[0]!.kind).toBe("provisional");
    expect(model.markers.map((m) => m.id)).toEqual([`provisional:BTCUSDT:${T0 + HOUR}`]);
  });

  it("descarta velas sin OHLC numérico y las cuenta como no utilizables", () => {
    const model = buildMarketChartModel(payload({
      candles: [
        candle(T0, {}),
        candle(T0 + HOUR, {open: "n/a", close: null as unknown as string}),
      ],
    }));
    expect(model.candles.closed).toHaveLength(1);
    expect(model.candles.unusable).toBe(1);
  });

  it("publica volumen solo si la fuente lo trae, con unidad explícita", () => {
    const withVolume = buildMarketChartModel(payload());
    expect(withVolume.volume_status).toBe("AVAILABLE");
    expect(withVolume.volume_unit).toBe("BTC");
    expect(withVolume.volume?.map((b) => b.value)).toEqual([12.5, 12.5]);

    const withoutVolume = buildMarketChartModel(payload({
      source: "mark_klines",
      volume: {
        available: false, base_asset: "BTC", quote_asset: "USDT", fields: [],
        reason: "mark_klines no publica volumen",
      },
      candles: [candle(T0, {baseVolume: null, quoteVolume: null})],
    }));
    expect(withoutVolume.volume).toBeNull();
    expect(withoutVolume.volume_status).toBe("UNAVAILABLE");
    expect(withoutVolume.volume_reason).toBe("mark_klines no publica volumen");
  });

  it("nunca transporta marcas de operación Paper Lab", () => {
    const model = buildMarketChartModel(payload());
    expect(model.operation).toBeNull();
    expect(model.identity.session_id).toBeNull();
    expect(model.indicators).toBeNull();
    expect(paperMarkersLeaked(model)).toEqual([]);
  });

  it("declara si hay tramos anteriores y el fin de histórico", () => {
    const more = buildMarketChartModel(payload({
      requested: {from_ms: T0 - 10 * HOUR, to_ms: T0 + HOUR},
      observed: {start_ms: T0, end_ms: T0 + HOUR},
    }));
    expect(more.capabilities.can_fetch_earlier).toBe(true);
    expect(more.capabilities.earlier_from_ms).toBe(T0);
    expect(more.capabilities.limits).toContain("hay tramos anteriores");

    const exhausted = buildMarketChartModel(payload({
      requested: {from_ms: T0 - 10 * HOUR, to_ms: T0 + HOUR},
      coverage: {
        state: "PARTIAL", observed_start_ms: T0, observed_end_ms: T0 + HOUR,
        expected_bars: 2, actual_bars: 2, gap_count: 0, gaps: [],
        absent_ranges: [[T0 - 10 * HOUR, T0 - HOUR]], exhausted_before: true,
        earliest_available_ms: T0, note: "",
      },
    }));
    expect(exhausted.capabilities.limits).toContain("fin de histórico");
    expect(exhausted.capabilities.can_fetch_earlier).toBe(false);
  });

  it("no declara LIVE y conserva procedencia y tiempos exactos", () => {
    const model = buildMarketChartModel(payload());
    expect(model.contract_version).toBe(MARKET_CHART_CONTRACT_VERSION);
    expect(model.capabilities.live).toBe(false);
    expect(model.identity.venue).toBe("binance");
    expect(model.identity.market_type).toBe("usd_m_futures");
    expect(model.identity.endpoint).toBe("/fapi/v1/klines");
    expect(model.times.unit).toBe("ms");
    expect(model.times.epoch).toBe("unix_utc");
    expect(model.times.newest_open_ms).toBe(T0 + HOUR);
    expect(model.times.age_ms).toBe(42_000);
    expect(model.coverage.state).toBe("COVERED");
    expect(model.notes).toEqual(["nota del backend"]);
  });

  it("permite que el catálogo seleccionado aporte el contrato", () => {
    const model = buildMarketChartModel(payload({contract: null}), {
      contract: {
        symbol: "BTCUSDT", base_asset: "BTC", quote_asset: "USDT",
        contract_type: "PERPETUAL", status: "TRADING", eligible: false,
        exclusion_reasons: ["status=SETTLING"],
      },
    });
    expect(model.identity.contract?.eligible).toBe(false);
    expect(model.identity.contract?.exclusion_reasons).toEqual(["status=SETTLING"]);
  });

  it("tolera payloads vacíos sin fabricar datos", () => {
    const model = buildMarketChartModel(payload({
      candles: [],
      observed: {start_ms: null, end_ms: null},
      coverage: {
        state: "NO_COVERAGE", observed_start_ms: null, observed_end_ms: null,
        expected_bars: 0, actual_bars: 0, gap_count: null, gaps: [],
        absent_ranges: [[T0, T0 + HOUR]], exhausted_before: false,
        earliest_available_ms: null, note: "",
      },
      volume: {
        available: false, base_asset: "BTC", quote_asset: "USDT", fields: [],
        reason: "SIN_VOLUMEN_EN_LO_ALMACENADO",
      },
      freshness: {
        state: "HISTORICAL_ON_DEMAND", newest_open_ms: null,
        newest_close_ms: null, fetched_at_ms: null, age_ms: null,
        provisional: null, note: "",
      },
    }));
    expect(model.candles.closed).toEqual([]);
    expect(model.candles.provisional).toEqual([]);
    expect(model.markers).toEqual([]);
    expect(model.volume).toBeNull();
    expect(model.capabilities.coverage_state).toBe("NO_COVERAGE");
  });
});

describe("mergeEarlierSeries — anteponer histórico sin perder el extremo reciente", () => {
  const bars = (from: number, count: number, close = "100.5") =>
    Array.from({length: count}, (_, index) => candle(from + index * HOUR, {close}));

  it("antepone el bloque y conserva la fila reciente ya cargada", () => {
    const previous = payload({
      candles: [candle(T0, {close: "100.5"}), candle(T0 + HOUR, {close: "101.5"})],
    });
    // El bloque solapa T0 y T0+HOUR con valores distintos: manda lo cargado.
    const block = payload({
      requested: {from_ms: T0 - 2 * HOUR, to_ms: T0 + HOUR},
      candles: [
        candle(T0 - 2 * HOUR, {close: "98"}),
        candle(T0 - HOUR, {close: "99"}),
        candle(T0, {close: "999"}),
        candle(T0 + HOUR, {close: "999"}),
      ],
    });

    const merged = mergeEarlierSeries(previous, block);

    expect(merged.added).toBe(2);
    expect(merged.payload.candles.map((row) => row.open_time_ms))
      .toEqual([T0 - 2 * HOUR, T0 - HOUR, T0, T0 + HOUR]);
    expect(merged.payload.candles.at(-1)?.close).toBe("101.5");
    expect(merged.payload.candles.at(-1)?.open_time_ms).toBe(T0 + HOUR);
    expect(merged.payload.requested).toEqual({from_ms: T0 - 2 * HOUR, to_ms: T0 + HOUR});
    expect(merged.payload.observed).toEqual({start_ms: T0 - 2 * HOUR, end_ms: T0 + HOUR});
    expect(merged.payload.coverage.state).toBe("COVERED");
    expect(merged.payload.coverage.actual_bars).toBe(4);
    expect(merged.payload.coverage.expected_bars).toBe(4);
    expect(merged.payload.coverage.gaps).toEqual([]);
    // El extremo reciente (frescura) no lo reescribe el bloque antiguo.
    expect(merged.payload.freshness.newest_open_ms).toBe(T0 + HOUR);
  });

  it("300 -> 303: cuenta velas únicas y no exige +300 por página", () => {
    const previous = payload({candles: bars(T0, 300)});
    // Respuesta de 300 velas que solapa 297 con lo ya cargado.
    const block = payload({
      requested: {from_ms: T0 - 300 * HOUR, to_ms: T0 - HOUR},
      candles: bars(T0 - 3 * HOUR, 300),
    });

    const merged = mergeEarlierSeries(previous, block);

    expect(merged.added).toBe(3);
    expect(merged.payload.candles).toHaveLength(303);
    expect(merged.payload.candles[0]?.open_time_ms).toBe(T0 - 3 * HOUR);
    expect(merged.payload.candles.at(-1)?.open_time_ms).toBe(T0 + 299 * HOUR);
  });

  it("un hueco real se declara como PARTIAL y no se interpola", () => {
    const previous = payload({
      candles: [candle(T0, {close: "100.5"}), candle(T0 + HOUR, {close: "101.5"})],
    });
    const block = payload({
      requested: {from_ms: T0 - 5 * HOUR, to_ms: T0 - 3 * HOUR},
      candles: [candle(T0 - 5 * HOUR), candle(T0 - 4 * HOUR), candle(T0 - 3 * HOUR)],
    });

    const merged = mergeEarlierSeries(previous, block);

    expect(merged.added).toBe(3);
    expect(merged.payload.coverage.state).toBe("PARTIAL");
    expect(merged.payload.coverage.gaps).toEqual([[T0 - 2 * HOUR, T0 - HOUR]]);
    expect(merged.payload.coverage.gap_count).toBe(1);
    expect(merged.payload.candles).toHaveLength(5);
  });

  it("no mezcla símbolos ni intervalos distintos", () => {
    const previous = payload();
    const block = payload({symbol: "ETHUSDT", candles: [candle(T0 - HOUR)]});

    const merged = mergeEarlierSeries(previous, block);

    expect(merged.added).toBe(0);
    expect(merged.payload).toBe(previous);
  });
});
