import {describe, expect, it} from "vitest";
import type {MarketSeriesPayload} from "@/lib/market-chart-contract";
import {
  buildStreamMeta, describeGap, emptyStreamView, livePermitted,
  mergeCandleRows, mergeStreamIntoSeries, streamStateLabel,
  type MarketStreamCandle, type MarketStreamStatus, type MarketStreamView,
} from "@/lib/market-stream";

const H = 3_600_000;
const T0 = 1_790_000_000_000;

function row(openMs: number, close: string, provisional = false) {
  return {
    open_time_ms: openMs, close_time_ms: provisional ? null : openMs + H - 1,
    open: "100", high: "101", low: "99", close,
    base_volume: "12.5", quote_volume: "1250", trade_count: 10,
    provisional, fetched_at_ms: T0, storage: "cache",
  };
}

function payload(): MarketSeriesPayload {
  return {
    contract_version: "market-series/v1", venue: "binance",
    market_type: "usd_m_futures", api_family: "fapi", source: "klines",
    endpoint: "/fapi/v1/klines", symbol: "BTCUSDT", interval: "1h",
    interval_ms: H, contract: null,
    requested: {from_ms: T0, to_ms: T0 + H},
    observed: {start_ms: T0, end_ms: T0 + H},
    candles: [row(T0, "100.5"), row(T0 + H, "100.5", true)],
    coverage: {
      state: "COVERED", observed_start_ms: T0, observed_end_ms: T0 + H,
      expected_bars: 2, actual_bars: 2, gap_count: 0, gaps: [],
      absent_ranges: [], exhausted_before: false, earliest_available_ms: null, note: "",
    },
    volume: {
      available: true, base_asset: "BTC", quote_asset: "USDT",
      fields: ["base_volume", "quote_volume"], reason: null,
    },
    freshness: {
      state: "fresh", newest_open_ms: T0 + H, newest_close_ms: null,
      fetched_at_ms: T0, age_ms: 1000, provisional: true, note: "",
    },
    fetch: {
      allowed: true, performed: false, status: "ok", error: null, requests: 0,
      pages: 0, retries: 0, failures: 0, detail: null, retry_after_ms: null,
    },
    labels: {mode: "HISTORICAL_ON_DEMAND", live: false, banner: "banner"},
    generated_at_ms: T0, notes: [],
  };
}

function streamCandle(overrides: Partial<MarketStreamCandle> = {}): MarketStreamCandle {
  return {
    symbol: "BTCUSDT", interval: "1h",
    open_time_ms: T0 + H, close_time_ms: null,
    open: 100, high: 102, low: 98, close: 101,
    base_volume: 3, quote_volume: 300, trade_count: 4,
    closed: false, event_ms: T0 + H + 1000, received_ms: T0 + H + 2000,
    source: "ws_kline", seq: 1,
    ...overrides,
  };
}

function status(overrides: Partial<MarketStreamStatus> = {}): MarketStreamStatus {
  return {
    symbol: "BTCUSDT", interval: "1h",
    connection: {state: "RECEIVING", socket_connected: true, fresh_ms: 10_000, stale_ms: 60_000},
    last_message_ms: T0 + H + 2000, last_kline_open_ms: T0 + H,
    closed_through_ms: T0 + H, age_ms: 500, live: true, recovering: false,
    generated_at_ms: T0 + H + 2500,
    ...overrides,
  };
}

describe("market-stream — fusión de velas", () => {
  it("una provisional no reabre una cerrada", () => {
    const merged = mergeCandleRows(
      [row(T0, "100.5")],
      [row(T0, "999", true)],
    );
    expect(merged).toHaveLength(1);
    expect(merged[0]!.close).toBe("100.5");
    expect(merged[0]!.provisional).toBe(false);
  });

  it("una cerrada reemplaza a la provisional del mismo tiempo", () => {
    const merged = mergeCandleRows(
      [row(T0, "100.5", true)],
      [row(T0, "101.5")],
    );
    expect(merged).toHaveLength(1);
    expect(merged[0]!.close).toBe("101.5");
    expect(merged[0]!.provisional).toBe(false);
  });

  it("ordena por apertura y nunca descarta histórico REST", () => {
    const merged = mergeCandleRows(
      [row(T0, "100"), row(T0 + 2 * H, "102")],
      [row(T0 + H, "101"), row(T0 + 3 * H, "103", true)],
    );
    expect(merged.map((c) => c.open_time_ms))
      .toEqual([T0, T0 + H, T0 + 2 * H, T0 + 3 * H]);
  });
});

describe("market-stream — snapshot + feed sobre el histórico", () => {
  it("ignora velas de otro símbolo o intervalo", () => {
    const view: MarketStreamView = {
      ...emptyStreamView(),
      updates: [
        streamCandle({symbol: "ETHUSDT", close: 9999}),
        streamCandle({interval: "4h", close: 8888}),
        streamCandle({close: 101.25}),
      ],
    };
    const merged = mergeStreamIntoSeries(payload(), view);
    expect(merged.candles).toHaveLength(2);
    expect(merged.candles.at(-1)!.close).toBe("101.25");
    expect(merged.candles.at(-1)!.provisional).toBe(true);
  });

  it("extiende con la vela nueva y recalcula observed/freshness", () => {
    const view: MarketStreamView = {
      ...emptyStreamView(),
      updates: [
        streamCandle({open_time_ms: T0 + H, close: 101.25}),
        streamCandle({open_time_ms: T0 + 2 * H, close: 102.5, closed: true,
          close_time_ms: T0 + 3 * H - 1, seq: 2}),
      ],
    };
    const merged = mergeStreamIntoSeries(payload(), view);
    expect(merged.candles.map((c) => c.open_time_ms)).toEqual([T0, T0 + H, T0 + 2 * H]);
    expect(merged.observed.end_ms).toBe(T0 + 2 * H);
    expect(merged.freshness.newest_open_ms).toBe(T0 + 2 * H);
    expect(merged.freshness.provisional).toBe(false);
    expect(merged.freshness.newest_close_ms).toBe(T0 + 3 * H - 1);
    // La cobertura del almacén no se falsea con el feed.
    expect(merged.coverage.state).toBe("COVERED");
  });

  it("el indicador del stream cierra velas en el payload sin recalcular", () => {
    const view: MarketStreamView = {
      ...emptyStreamView(),
      updates: [streamCandle({open_time_ms: T0 + 2 * H, closed: true,
        close_time_ms: T0 + 3 * H - 1, close: 102.5, seq: 2})],
      indicators: {
        contract_version: "market-indicators/v1",
        availability: "CLOSED_CANDLES_ONLY",
        provisional_policy: {included: false, reason: "PROVISIONAL_EXCLUDED"},
        computed_over: "payload_window",
        identity: {symbol: "BTCUSDT", interval: "1h", interval_ms: H,
          source: "ws_kline"},
        definitions: [], supported: ["log_return_bps"], declined: [],
        series: [{open_time_ms: T0 + 2 * H,
          available_at_ms: T0 + 3 * H,
          values: {log_return_bps: 12.34}, unknown: {}}],
        generated_at_ms: T0 + H,
      },
    };
    const merged = mergeStreamIntoSeries(payload(), view);
    const mergedIndicators = merged.indicators!;
    expect(mergedIndicators.identity.symbol).toBe("BTCUSDT");
    expect(mergedIndicators.identity.source).toBe("ws_kline");
    const updated = mergedIndicators.series.find(
      (r) => r.open_time_ms === T0 + 2 * H)!;
    expect(updated.values.log_return_bps).toBe(12.34);
  });

  it("un bloque de indicadores ajeno por identidad no se mezcla", () => {
    const view: MarketStreamView = {
      ...emptyStreamView(),
      indicators: {
        contract_version: "market-indicators/v1",
        availability: "CLOSED_CANDLES_ONLY",
        provisional_policy: {included: false, reason: "PROVISIONAL_EXCLUDED"},
        computed_over: "payload_window",
        identity: {symbol: "ETHUSDT", interval: "1h", interval_ms: H,
          source: "ws_kline"},
        definitions: [], supported: ["log_return_bps"], declined: [],
        series: [], generated_at_ms: T0,
      },
    };
    const source = payload();
    expect(mergeStreamIntoSeries(source, view)).toBe(source);
  });

  it("sin eventos devuelve el mismo payload (identidad estable)", () => {
    const source = payload();
    expect(mergeStreamIntoSeries(source, emptyStreamView())).toBe(source);
    expect(mergeStreamIntoSeries(source, null)).toBe(source);
  });
});

describe("market-stream — LIVE honesto", () => {
  it("exige estado, socket, identidad y frescura", () => {
    expect(livePermitted(status())).toBe(true);
    expect(livePermitted(status({live: false}))).toBe(false);
    expect(livePermitted(status({connection: {
      state: "STALE", socket_connected: true, fresh_ms: 10_000, stale_ms: 60_000,
    }}))).toBe(false);
    expect(livePermitted(status({connection: {
      state: "RECEIVING", socket_connected: false, fresh_ms: 10_000, stale_ms: 60_000,
    }}))).toBe(false);
    expect(livePermitted(status({age_ms: 11_000}))).toBe(false);
    expect(livePermitted(status({age_ms: null}))).toBe(false);
    expect(livePermitted(null)).toBe(false);
  });

  it("traduce estados a etiquetas estables", () => {
    expect(streamStateLabel("CONNECTING")).toBe("CONECTANDO");
    expect(streamStateLabel("RECEIVING")).toBe("RECIBIENDO");
    expect(streamStateLabel("STALE")).toBe("OBSOLETO");
    expect(streamStateLabel("RECOVERING")).toBe("RECUPERANDO");
    expect(streamStateLabel("DISCONNECTED")).toBe("DESCONECTADO");
    expect(streamStateLabel(null)).toBe("SIN FEED");
  });

  it("conserva solo los últimos huecos en los metadatos", () => {
    const gaps = Array.from({length: 7}, (_, index) => ({
      symbol: "BTCUSDT", interval: "1h", reason: "GAP",
      status: "detected" as const,
      expected_from_ms: T0 + index * H, expected_to_ms: T0 + index * H,
      missing: [], requests: 0,
    }));
    const meta = buildStreamMeta({...emptyStreamView(), status: status(), gaps});
    expect(meta).not.toBeNull();
    expect(meta!.gaps).toHaveLength(5);
    expect(meta!.live).toBe(true);
    expect(meta!.contract_version).toBe("market-stream/v1");
  });

  it("describe los huecos sin ocultar reparaciones parciales", () => {
    expect(describeGap({
      symbol: "BTCUSDT", interval: "1h", reason: "GAP", status: "partial",
      expected_from_ms: 1, expected_to_ms: 2, missing: [[2, 3]], requests: 1,
    })).toContain("parcial");
    expect(describeGap({
      symbol: "BTCUSDT", interval: "1h", reason: "GAP", status: "complete",
      expected_from_ms: 1, expected_to_ms: 2, missing: [], requests: 1,
      recovered_bars: 2,
    })).toContain("reparado");
    expect(describeGap({
      symbol: "BTCUSDT", interval: "1h", reason: "GAP", status: "failed",
      expected_from_ms: 1, expected_to_ms: 2, missing: [], requests: 0,
      detail: "REST_DOWN",
    })).toContain("REST_DOWN");
  });
});
