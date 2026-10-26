import {describe, expect, it} from "vitest";
import {
  buildMarketChartModel,
  marketIndicatorAtCursor,
  marketIndicatorsBadgeText,
  mergeEarlierSeries,
  mergeIndicatorBlocks,
  parseMarketIndicators,
  type MarketIndicatorsBlock,
  type MarketSeriesPayload,
} from "@/lib/market-chart-contract";

const HOUR = 3_600_000;
const T0 = 1_790_000_000_000;

function basePayload(overrides: Partial<MarketSeriesPayload> = {}):
  MarketSeriesPayload {
  return {
    contract_version: "market-series/v1", venue: "binance",
    market_type: "usd_m_futures", api_family: "fapi", source: "klines",
    endpoint: "/fapi/v1/klines", symbol: "BTCUSDT", interval: "1h",
    interval_ms: HOUR,
    contract: null,
    requested: {from_ms: T0, to_ms: T0 + HOUR},
    observed: {start_ms: T0, end_ms: T0 + HOUR},
    candles: [
      {open_time_ms: T0, close_time_ms: T0 + HOUR - 1, open: "100",
        high: "101", low: "99", close: "100.5", base_volume: "12.5",
        quote_volume: "1250", trade_count: 10, provisional: false,
        fetched_at_ms: T0, storage: "cache"},
    ],
    coverage: {
      state: "COVERED", observed_start_ms: T0, observed_end_ms: T0 + HOUR,
      expected_bars: 1, actual_bars: 1, gap_count: 0, gaps: [],
      absent_ranges: [], exhausted_before: false,
      earliest_available_ms: null, note: "",
    },
    volume: {
      available: true, base_asset: "BTC", quote_asset: "USDT",
      fields: ["base_volume"], reason: null,
    },
    freshness: {
      state: "HISTORICAL_ON_DEMAND", newest_open_ms: T0,
      newest_close_ms: T0 + HOUR - 1, fetched_at_ms: T0, age_ms: 1000,
      provisional: false, note: "",
    },
    fetch: {
      allowed: true, performed: false, status: "not_requested", error: null,
      requests: 0, pages: 0, retries: 0, failures: 0, detail: null,
      retry_after_ms: null,
    },
    labels: {
      mode: "HISTORICAL_ON_DEMAND", live: false,
      banner: "HISTORICO / CONSULTA BAJO DEMANDA",
    },
    generated_at_ms: T0 + HOUR,
    notes: ["nota"],
    ...overrides,
  };
}

function indicatorRow(openTimeMs: number, values: Record<string, number> = {},
  unknown: Record<string, string> = {}) {
  return {
    open_time_ms: openTimeMs,
    available_at_ms: openTimeMs + HOUR,
    values,
    unknown,
  };
}

function indicatorBlock(overrides: Partial<MarketIndicatorsBlock> = {}):
  MarketIndicatorsBlock {
  return {
    contract_version: "market-indicators/v1",
    availability: "CLOSED_CANDLES_ONLY",
    provisional_policy: {included: false, reason: "PROVISIONAL_EXCLUDED"},
    computed_over: "payload_window",
    identity: {symbol: "BTCUSDT", interval: "1h", interval_ms: HOUR,
      source: "klines"},
    definitions: [{
      name: "log_return_bps", formula: "f", unit: "bps", window_candles: 1,
      requires: "previedad",
    }],
    supported: ["log_return_bps"],
    declined: [{name: "flow_delta", reason: "AGGTRADES_SOURCE_REQUIRED"}],
    series: [indicatorRow(T0, {log_return_bps: 12.5})],
    generated_at_ms: T0 + HOUR,
    ...overrides,
  };
}

describe("market-indicators/v1 — el navegador solo lee, nunca recalcula", () => {
  it("transporta el bloque validado al modelo del gráfico", () => {
    const payload = basePayload({indicators: indicatorBlock()});
    const model = buildMarketChartModel(payload);
    expect(model.indicators).not.toBeNull();
    expect(model.indicators!.contract_version).toBe("market-indicators/v1");
    expect(model.indicators!.series[0]!.values.log_return_bps).toBe(12.5);
  });

  it("sin bloque en el payload el modelo declara null (no cero ni siempre [] )", () => {
    expect(buildMarketChartModel(basePayload()).indicators).toBeNull();
  });

  it("descarta el bloque si la identidad no corresponde (símbolo/intervalo)", () => {
    const stale = basePayload({indicators: indicatorBlock({
      identity: {symbol: "ETHUSDT", interval: "1h", interval_ms: HOUR,
        source: "klines"},
    })});
    expect(parseMarketIndicators(stale)).toBeNull();
    expect(buildMarketChartModel(stale).indicators).toBeNull();

    const wrongInterval = basePayload({indicators: indicatorBlock({
      identity: {symbol: "BTCUSDT", interval: "1m", interval_ms: 60_000,
        source: "klines"},
    })});
    expect(parseMarketIndicators(wrongInterval)).toBeNull();
  });

  it("descarta versiones desconocidas y filas corruptas sin inventar datos", () => {
    const wrongVersion = basePayload({indicators: indicatorBlock({
      contract_version: "market-indicators/v9" as "market-indicators/v1",
    })});
    expect(parseMarketIndicators(wrongVersion)).toBeNull();

    const partial = basePayload({indicators: indicatorBlock({
      series: [
        indicatorRow(T0, {log_return_bps: 5}),
        {open_time_ms: "x", available_at_ms: null, values: {}, unknown: {}},
        null,
      ] as MarketIndicatorsBlock["series"],
    })});
    const parsed = parseMarketIndicators(partial)!;
    expect(parsed.series.map((r) => r.open_time_ms)).toEqual([T0]);
  });

  it("no convierte strings ni Infinito en valores", () => {
    const payload = basePayload({indicators: indicatorBlock({
      series: [{
        open_time_ms: T0,
        available_at_ms: T0 + HOUR,
        values: {log_return_bps: "12.5" as unknown as number,
          rel_volume_10: Infinity as unknown as number},
        unknown: {},
      }],
    })});
    const parsed = parseMarketIndicators(payload)!;
    expect(Object.keys(parsed.series[0]!.values)).toEqual([]);
  });
});

describe("market-indicators/v1 — badge de valores al cursor", () => {
  it("presenta versión y valores formateados en la fila exacta", () => {
    expect(marketIndicatorsBadgeText(indicatorBlock({
      series: [indicatorRow(T0, {log_return_bps: -3.214567})],
    }), T0)).toBe("Indicadores: ret -3.21");
  });

  it("UNKNOWN con el motivo del backend, nunca cero ni recálculo", () => {
    expect(marketIndicatorsBadgeText(indicatorBlock({
      series: [indicatorRow(T0, {}, {log_return_bps: "GAP_IN_WINDOW"})],
    }), T0)).toBe("Indicadores: ret UNKNOWN(GAP_IN_WINDOW)");
  });

  it("sin cursor o sin fila declara ausencia honesta", () => {
    expect(marketIndicatorsBadgeText(indicatorBlock(), null))
      .toBe("Indicadores: sin fila para la vela bajo el cursor");
    expect(marketIndicatorsBadgeText(indicatorBlock(), T0 - HOUR))
      .toBe("Indicadores: sin fila para la vela bajo el cursor");
    // La vela provisional del backend no emite filas: si el cursor cae
    // en ella y por eso no hay fila, la exclusión se declara.
    expect(marketIndicatorsBadgeText(
      indicatorBlock({series: [indicatorRow(T0 - HOUR, {log_return_bps: 1})]}),
      T0, true,
    )).toBe("Indicadores: vela provisional excluida (politica del bloque)");
  });

  it("sin bloque el badge declara que market-indicators/v1 no llegó", () => {
    expect(marketIndicatorsBadgeText(null, T0))
      .toBe("Indicadores: ninguno (market-indicators/v1 ausente)");
  });

  it("marketIndicatorAtCursor busca la vela exacta", () => {
    const block = indicatorBlock({
      series: [indicatorRow(T0, {log_return_bps: 1})],
    });
    expect(marketIndicatorAtCursor(block, T0)!.values.log_return_bps).toBe(1);
    expect(marketIndicatorAtCursor(block, T0 + HOUR)).toBeNull();
    expect(marketIndicatorAtCursor(null, T0)).toBeNull();
  });
});

describe("market-indicators/v1 — fusión de bloques sin recalcular", () => {
  it("une filas de ambos bloques; el más reciente gana por apertura", () => {
    const merged = mergeIndicatorBlocks(
      indicatorBlock({series: [indicatorRow(T0, {log_return_bps: 1})]}),
      indicatorBlock({series: [
        indicatorRow(T0, {log_return_bps: 999}),
        indicatorRow(T0 - HOUR, {log_return_bps: 2}),
      ]}),
    )!;
    expect(merged.series.map((r) => r.open_time_ms)).toEqual([T0 - HOUR, T0]);
    expect(merged.series.find((r) => r.open_time_ms === T0)!.values.log_return_bps)
      .toBe(999);
    expect(merged.computed_over).toBe("per_block_payload_windows");
  });

  it("identidades distintas no se mezclan: null, no mezcla silenciosa", () => {
    expect(mergeIndicatorBlocks(
      indicatorBlock(),
      indicatorBlock({identity: {symbol: "ETHUSDT", interval: "1h",
        interval_ms: HOUR, source: "klines"}}),
    )).toBeNull();
  });

  it("un solo bloque pasa tal cual; ambos ausentes = null", () => {
    const one = indicatorBlock();
    expect(mergeIndicatorBlocks(one, null)).toBe(one);
    expect(mergeIndicatorBlocks(null, one)).toBe(one);
    expect(mergeIndicatorBlocks(null, null)).toBeNull();
  });

  it("mergeEarlierSeries transporta la unión de indicadores al payload fusionado", () => {
    const previous = basePayload({indicators: indicatorBlock({
      series: [indicatorRow(T0, {log_return_bps: 1})],
    })});
    const block = basePayload({indicators: indicatorBlock({
      series: [indicatorRow(T0 - HOUR, {log_return_bps: 2})],
    }), candles: [{
      open_time_ms: T0 - HOUR, close_time_ms: T0 - 1, open: "99", high: "100",
      low: "98", close: "99.5", base_volume: "10", quote_volume: "990",
      trade_count: 9, provisional: false, fetched_at_ms: T0,
      storage: "cache",
    }], requested: {from_ms: T0 - HOUR, to_ms: T0}}) as MarketSeriesPayload;
    const {payload: merged} = mergeEarlierSeries(previous, block);
    expect(merged.indicators!.series.map((r) => r.open_time_ms))
      .toEqual([T0 - HOUR, T0]);
  });
});

describe("market-indicators/v1 — cambio de identidad no arrastra valores", () => {
  it("un modelo nuevo por símbolo/intervalo no conserva el bloque anterior", () => {
    const btc = buildMarketChartModel(basePayload({indicators: indicatorBlock()}));
    expect(btc.indicators!.identity.symbol).toBe("BTCUSDT");
    const ethPayload = basePayload({symbol: "ETHUSDT",
      indicators: indicatorBlock()});
    ethPayload.indicators = indicatorBlock() as MarketIndicatorsBlock;
    // El payload nuevo no lleva bloque (backend honesto): el modelo tampoco.
    const eth = buildMarketChartModel({...ethPayload, indicators: null});
    expect(eth.indicators).toBeNull();
    // Y un bloque de otro símbolo no se cuela en un modelo nuevo.
    const mixed = basePayload({symbol: "ETHUSDT",
      indicators: indicatorBlock()});
    expect(buildMarketChartModel(mixed).indicators).toBeNull();
  });
});
