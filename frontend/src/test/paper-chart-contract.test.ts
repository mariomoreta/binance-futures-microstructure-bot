import {describe, expect, it} from "vitest";
import {
  buildPaperChartModel,
  msToChartSecond,
  PAPER_CHART_CONTRACT_VERSION,
} from "@/lib/paper-chart-contract";
import type {PaperCandle, PaperSessionState} from "@/lib/paper-lab-live";

const T0 = 0;
const T1 = 900000;
const T2 = 1800000;
const T3 = 2700000;
const T4 = 3600000;

function closed(t: number, o: number, h: number, l: number, c: number): PaperCandle {
  return {
    open_time_ms: t, open: o, high: h, low: l, close: c,
    close_time_ms: t + 899999, available_at: t + 900000, received_at: t + 900000,
  };
}

function openOnly(t: number, o: number): PaperCandle {
  return {
    open_time_ms: t, open: o, high: null, low: null, close: null,
    close_time_ms: null, available_at: null, received_at: null,
  };
}

function baseState(overrides: Partial<PaperSessionState> = {}): PaperSessionState {
  const state: PaperSessionState = {
    session_id: "PL-BTCUSDT-LONG-1",
    created_at_ms: 1000,
    updated_at_ms: 2000,
    status: "en_espera",
    revision: 4,
    config: {
      symbol: "BTCUSDT", interval: "15m", direction: "LONG",
      notional_usdt: 1000, entry_px: 101, stop_px: 95.95,
      stop_distance_pct: 5, horizon_ms: 10800000,
      fee_bps: 5, spread_bps: 1, slippage_bps: 2,
      decision: "ENTRADA_SIMULADA",
      decision_reason: "causal",
      decision_evidence: {
        decision_at_ms: T1,
        at_ms: T1,
        trigger_px: 101,
        available_at_ms: T2,
        entry_fill_px: null,
        entry_fill_ms: null,
      },
    },
    candles: [
      closed(T0, 100, 101, 99, 100.5),
      openOnly(T1, 101),
      closed(T2, 101, 102, 94, 95),
      closed(T3, 95, 96, 94, 95),
    ],
    context_candles: [
      closed(-1800000, 99, 100, 98, 99.5),
      closed(-900000, 99.5, 100.5, 99, 100),
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
    events: [
      {event_id: "PL-BTCUSDT-LONG-1:ev:0:protection:900000", at_ms: T1,
        label: "Decisión: ENTRADA_SIMULADA @ 101.00", kind: "protection"},
    ],
    result: null,
    clock_ms: T1,
    config_hash: "abc",
    input_hash: "def",
    engine_version: "paper-lab/v1",
    limitations: [],
    authoritative: null,
    can_step: true,
  };
  return {...state, ...overrides};
}

describe("paper-chart/v1 — identidad y tiempos", () => {
  it("expone versión, identidad de fixture y venue UNKNOWN", () => {
    const model = buildPaperChartModel(baseState(), {fixtureId: "btc_long_stop_order"});
    expect(model.contract_version).toBe(PAPER_CHART_CONTRACT_VERSION);
    expect(model.identity).toEqual({
      source: "fixture",
      venue: null,
      venue_status: "UNKNOWN",
      market_type: "simulated_futures",
      symbol: "BTCUSDT",
      interval: "15m",
      session_id: "PL-BTCUSDT-LONG-1",
      fixture_id: "btc_long_stop_order",
    });
    expect(model.times).toMatchObject({unit: "ms", epoch: "unix_utc", clock_ms: T1});
    expect(model.volume).toBeNull();
    expect(model.volume_status).toBe("UNKNOWN");
    expect(model.indicators).toEqual([]);
  });

  it("convierte ms UTC a segundos de la biblioteca conservando el ms exacto", () => {
    expect(msToChartSecond(1788904800000)).toBe(1788904800);
    // Precisión del eje en segundos: dos instantes del mismo segundo comparten
    // coordenada, pero el modelo conserva time_ms e id exactos.
    expect(msToChartSecond(1788904800999)).toBe(1788904800);
    expect(msToChartSecond(1788904801500)).toBe(1788904801);
    expect(() => msToChartSecond(Number.NaN)).toThrow("INVALID_TIME_MS");
  });

  it("no presenta velas con open_time_ms posterior al reloj de simulación", () => {
    const state = baseState({
      candles: [...baseState().candles, closed(T4, 95, 99, 94, 98)],
      clock_ms: T1,
    });
    const model = buildPaperChartModel(state);
    const times = [
      ...model.candles.context.map((c) => c.open_time_ms),
      ...model.candles.closed.map((c) => c.open_time_ms),
      ...model.candles.open_only.map((c) => c.open_time_ms),
    ];
    expect(times).toContain(T0);
    expect(times).not.toContain(T4);
    expect(times.every((t) => t <= T1)).toBe(true);
  });

  it("sin reloj no asume velas conocidas", () => {
    const model = buildPaperChartModel(baseState({clock_ms: null}));
    expect(model.candles.context).toEqual([]);
    expect(model.candles.closed).toEqual([]);
    expect(model.candles.open_only).toEqual([]);
  });
});

describe("paper-chart/v1 — velas conocidas vs solo-open", () => {
  it("publica la vela solo-open sin inventar high/low/close", () => {
    const model = buildPaperChartModel(baseState());
    expect(model.candles.open_only).toHaveLength(1);
    const candle = model.candles.open_only[0]!;
    expect(candle.kind).toBe("open");
    expect(candle.open_time_ms).toBe(T1);
    expect(candle.open).toBe(101);
    expect(candle.high).toBeNull();
    expect(candle.low).toBeNull();
    expect(candle.close).toBeNull();
    expect(candle.close_time_ms).toBeNull();
    // La vela futura T2 no se cuela como cerrada.
    expect(model.candles.closed.map((c) => c.open_time_ms)).toEqual([T0]);
  });

  it("ordena por tiempo, deduplica y conserva la última observación", () => {
    const state = baseState({
      candles: [
        closed(T0, 100, 101, 99, 100.5),
        openOnly(T1, 101),
        closed(T0, 100, 101, 99, 100.75),
        closed(T2, 101, 102, 94, 95),
      ],
      clock_ms: T2,
    });
    const model = buildPaperChartModel(state);
    expect(model.candles.closed.map((c) => c.open_time_ms)).toEqual([T0, T2]);
    expect(model.candles.closed[0]!.close).toBe(100.75);
    expect(model.candles.open_only.map((c) => c.open_time_ms)).toEqual([T1]);
    // Contexto también ordenado y sin duplicados.
    expect(model.candles.context.map((c) => c.open_time_ms))
      .toEqual([-1800000, -900000]);
  });
});

describe("paper-chart/v1 — operación", () => {
  it("señal pendiente no se confunde con un fill ejecutado", () => {
    const model = buildPaperChartModel(baseState());
    expect(model.operation.signal).toEqual({
      at_ms: T1, price: 101, event_id: "PL-BTCUSDT-LONG-1:ev:0:protection:900000",
    });
    expect(model.operation.pending_entry).toEqual({reference_px: 101});
    expect(model.operation.entry).toBeNull();
    expect(model.operation.stop_effective_px).toBeNull();
    expect(model.operation.exit).toBeNull();
    expect(model.operation.realized_net).toBeNull();
    expect(model.operation.realized_status).toBe("not_realized");
    expect(model.operation.target_px).toBeNull();
    expect(model.operation.target_status).toBe("UNKNOWN");
    expect(model.markers.map((m) => m.kind)).toEqual(["signal"]);
  });

  it("el fill usa entry_px/stop_px efectivos y conserva IDs de evento", () => {
    const state = baseState({
      status: "abierta",
      clock_ms: T2,
      position: {
        ...baseState().position,
        open: true, entry_px: 101, entry_ms: T2, stop_px: 95.95,
        mark_px: 101, mark_ms: T2, unrealized_net: 0,
      },
      events: [
        ...baseState().events,
        {event_id: "PL-BTCUSDT-LONG-1:ev:1:entry:1800000", at_ms: T2,
          label: "Entrada simulada @ 101.00", kind: "entry"},
      ],
    });
    const model = buildPaperChartModel(state);
    expect(model.operation.pending_entry).toBeNull();
    expect(model.operation.entry).toEqual({
      px: 101, ms: T2, event_id: "PL-BTCUSDT-LONG-1:ev:1:entry:1800000",
    });
    expect(model.operation.stop_effective_px).toBe(95.95);
    expect(model.operation.exit).toBeNull();
    expect(model.operation.unrealized_net).toBe(0);
    expect(model.markers.map((m) => m.kind)).toEqual(["signal", "entry"]);
    expect(model.markers.map((m) => m.time_s)).toEqual([900, 1800]);
  });

  it("regresión aceptada: LONG 101 → stop/salida 95.95 → realizado -51.56", () => {
    const state = baseState({
      status: "cerrada",
      clock_ms: T3,
      cursor: 3,
      position: {
        ...baseState().position,
        open: false, entry_px: 101, entry_ms: T2, stop_px: 95.95,
        mark_px: 95.95, mark_ms: T3,
      },
      result: {
        symbol: "BTCUSDT", direction: "LONG", entry_px: 101, exit_px: 95.95,
        entry_ms: T2, exit_ms: T3, exit_reason: "stop", exit_executed: true,
        qty: 9.900990099009901, filled_cost: 999.9999999999999,
        gross_pnl: -50, fees: 0.975, spread_slip: 0.585, funding: null,
        friction: 1.56, net_pnl: -51.56, realized_net: -51.56,
        open_at_end: false, entry_fees_executed: 0.5,
        exit_fees_executed: 0.475, entry_spread_slip_executed: 0.1,
        exit_spread_slip_executed: 0.485, exit_fees_estimated: 0,
        exit_spread_slip_estimated: 0,
      },
      events: [
        ...baseState().events,
        {event_id: "PL-BTCUSDT-LONG-1:ev:1:entry:1800000", at_ms: T2,
          label: "Entrada simulada @ 101.00", kind: "entry"},
        {event_id: "PL-BTCUSDT-LONG-1:ev:2:exit:2700000", at_ms: T3,
          label: "Salida stop @ 95.95", kind: "exit"},
      ],
    });
    const model = buildPaperChartModel(state);
    expect(model.operation.entry?.px).toBe(101);
    expect(model.operation.stop_effective_px).toBe(95.95);
    expect(model.operation.exit).toEqual({
      px: 95.95, ms: T3, reason: "stop",
      event_id: "PL-BTCUSDT-LONG-1:ev:2:exit:2700000",
    });
    expect(model.operation.realized_net).toBe(-51.56);
    expect(model.operation.realized_status).toBe("known");
    expect(model.markers.map((m) => m.kind)).toEqual(["signal", "entry", "exit"]);
    // No existe ni se dibuja una salida posterior a 80.
    expect(model.markers.some((m) => m.price === 80)).toBe(false);
    expect(model.operation.exit?.px).not.toBe(80);
  });

  it("open_at_end no inventa cierre ni resultado realizado", () => {
    const state = baseState({
      status: "cerrada",
      clock_ms: T4,
      cursor: 4,
      position: {
        ...baseState().position,
        open: true, entry_px: 101, entry_ms: T1, stop_px: 95.95,
        mark_px: 99, mark_ms: T4, unrealized_net: 30,
      },
      result: {
        symbol: "BTCUSDT", direction: "LONG", entry_px: 101, exit_px: 99,
        entry_ms: T1, exit_ms: T4, exit_reason: "horizon", exit_executed: false,
        qty: 9.900990099009901, filled_cost: 999.9999999999999,
        gross_pnl: 30, fees: 0.975, spread_slip: 0.585, funding: null,
        friction: 1.56, net_pnl: 28.44, realized_net: null,
        open_at_end: true, entry_fees_executed: 0.5,
        exit_fees_executed: 0, entry_spread_slip_executed: 0.1,
        exit_spread_slip_executed: 0, exit_fees_estimated: 0.475,
        exit_spread_slip_estimated: 0.485,
      },
      events: [
        ...baseState().events,
        {event_id: "PL-BTCUSDT-LONG-1:ev:1:entry:2700000", at_ms: T2,
          label: "Entrada simulada @ 101.00", kind: "entry"},
      ],
      can_step: false,
    });
    const model = buildPaperChartModel(state);
    expect(model.operation.open_at_end).toBe(true);
    expect(model.operation.exit).toBeNull();
    expect(model.operation.realized_net).toBeNull();
    expect(model.operation.realized_status).toBe("not_realized");
    expect(model.operation.unrealized_net).toBe(30);
    expect(model.markers.map((m) => m.kind)).toEqual(["signal", "entry"]);
    expect(model.capabilities.limits).toContain("fin de datos");
  });

  it("una decisión SIN_ENTRADA no produce señal ni entrada", () => {
    const state = baseState({
      config: {
        ...baseState().config,
        decision: "SIN_ENTRADA",
        decision_evidence: {decision_at_ms: T1, trigger_px: 101},
      },
    });
    const model = buildPaperChartModel(state);
    expect(model.operation.signal).toBeNull();
    expect(model.operation.pending_entry).toBeNull();
    expect(model.markers).toEqual([]);
  });
});
