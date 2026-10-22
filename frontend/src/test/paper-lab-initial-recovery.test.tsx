import {afterEach, describe, expect, it, vi} from "vitest";
import {cleanup, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import type {PaperSessionState, PaperSessionSummary} from "@/lib/paper-lab-live";

const api = vi.hoisted(() => ({
  listSessionsApi: vi.fn(),
  getSessionApi: vi.fn(),
  createSessionApi: vi.fn(),
  evaluateSessionApi: vi.fn(),
  stepSessionApi: vi.fn(),
  exitSessionApi: vi.fn(),
  restartSessionApi: vi.fn(),
  stopSessionApi: vi.fn(),
}));

vi.mock("@/lib/paper-lab-live", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/paper-lab-live")>();
  return {...actual, ...api};
});

const h = vi.hoisted(() => {
  const makeSeries = () => ({
    setData: vi.fn(),
    update: vi.fn(),
    createPriceLine: vi.fn(() => ({})),
    removePriceLine: vi.fn(),
    priceScale: vi.fn(() => ({applyOptions: vi.fn()})),
  });
  const timeScale = {
    fitContent: vi.fn(),
    subscribeVisibleTimeRangeChange: vi.fn(),
    unsubscribeVisibleTimeRangeChange: vi.fn(),
    getVisibleLogicalRange: vi.fn(() => null),
    setVisibleLogicalRange: vi.fn(),
  };
  return {
    makeSeries,
    timeScale,
    chart: {
      addSeries: vi.fn(() => makeSeries()),
      timeScale: vi.fn(() => timeScale),
      subscribeCrosshairMove: vi.fn(),
      unsubscribeCrosshairMove: vi.fn(),
      remove: vi.fn(),
    },
  };
});

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => h.chart),
  CandlestickSeries: {type: "Candlestick"},
  LineSeries: {type: "Line"},
  HistogramSeries: {type: "Histogram"},
  ColorType: {Solid: "solid"},
  CrosshairMode: {Normal: 0},
  LineStyle: {Solid: 0, Dotted: 1, Dashed: 2},
  createSeriesMarkers: vi.fn(() => ({setMarkers: vi.fn(), detach: vi.fn()})),
}));

import PaperLabLive from "@/components/paper-lab-live/PaperLabLive";

function state(overrides: Partial<PaperSessionState> = {}): PaperSessionState {
  return {
    session_id: "PL-BTCUSDT-LONG-2",
    created_at_ms: 1000,
    updated_at_ms: 2000,
    status: "en_espera",
    revision: 1,
    config: {
      symbol: "BTCUSDT", interval: "15m", direction: "LONG",
      notional_usdt: 1000, entry_px: 101, stop_px: 95.95,
      stop_distance_pct: 5, horizon_ms: 10800000,
      fee_bps: 5, spread_bps: 1, slippage_bps: 2,
      decision: "ENTRADA_SIMULADA", decision_reason: "causal",
      decision_evidence: {decision_at_ms: 900000, at_ms: 900000, trigger_px: 101},
    },
    candles: [
      {open_time_ms: 0, open: 100, high: 101, low: 99, close: 100.5, close_time_ms: 899999},
    ],
    context_candles: [],
    cursor: 1,
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

const summaries: PaperSessionSummary[] = [
  {
    session_id: "PL-BTCUSDT-LONG-2", status: "en_espera", revision: 1,
    created_at_ms: 1000, updated_at_ms: 2000, symbol: "BTCUSDT",
    direction: "LONG", config_hash: "abc", has_result: false,
  },
  {
    session_id: "PL-ETHUSDT-SHORT-9", status: "cerrada", revision: 4,
    created_at_ms: 500, updated_at_ms: 1500, symbol: "ETHUSDT",
    direction: "SHORT", config_hash: "xyz", has_result: true,
  },
];

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Paper Lab — recuperar sesión desde la pantalla inicial (G)", () => {
  it("lista las sesiones guardadas sin crear otra fixture", async () => {
    api.listSessionsApi.mockResolvedValue({ok: true, data: summaries, status: 200});
    render(<PaperLabLive/>);
    const region = await screen.findByRole("region", {name: "Persistencia de sesiones paper"});
    const select = within(region).getByRole("combobox");
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(3));
    const options = within(select).getAllByRole("option").map((o) => o.textContent ?? "");
    expect(options.some((t) => t.includes("PL-BTCUSDT-LONG-2"))).toBe(true);
    expect(options.some((t) => t.includes("PL-ETHUSDT-SHORT-9"))).toBe(true);
    expect(screen.getByTestId("initial-session-recovery-note")).toBeTruthy();
    // Sin selección no se pide estado ni se crea nada.
    expect(api.getSessionApi).not.toHaveBeenCalled();
    expect(api.createSessionApi).not.toHaveBeenCalled();
  });

  it("carga el estado autoritativo de la sesión elegida sin nueva fixture", async () => {
    api.listSessionsApi.mockResolvedValue({ok: true, data: summaries, status: 200});
    api.getSessionApi.mockResolvedValue({
      ok: true, data: state({session_id: "PL-BTCUSDT-LONG-2"}), status: 200,
    });
    render(<PaperLabLive/>);
    const region = await screen.findByRole("region", {name: "Persistencia de sesiones paper"});
    const select = within(region).getByRole("combobox");
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(3));
    fireEvent.change(select, {target: {value: "PL-ETHUSDT-SHORT-9"}});
    await waitFor(() => expect(api.getSessionApi).toHaveBeenCalledWith("PL-ETHUSDT-SHORT-9"));
    // Se muestra el estado recuperado (gráfico Paper) y no se creó fixture.
    expect(await screen.findByTestId("paper-chart")).toBeTruthy();
    expect(api.createSessionApi).not.toHaveBeenCalled();
    expect(api.evaluateSessionApi).not.toHaveBeenCalled();
  });

  it("si la carga falla, muestra el error y mantiene la pantalla inicial", async () => {
    api.listSessionsApi.mockResolvedValue({ok: true, data: summaries, status: 200});
    api.getSessionApi.mockResolvedValue({
      ok: false, status: 404, error: "SESSION_NOT_FOUND", detail: "no existe",
    });
    render(<PaperLabLive/>);
    const region = await screen.findByRole("region", {name: "Persistencia de sesiones paper"});
    const select = within(region).getByRole("combobox");
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(3));
    fireEvent.change(select, {target: {value: "PL-BTCUSDT-LONG-2"}});
    const alert = await screen.findByTestId("initial-session-error");
    expect(alert.textContent).toContain("SESSION_NOT_FOUND");
    expect(alert.textContent).toContain("no existe");
    expect(screen.queryByTestId("paper-chart")).toBeNull();
    expect(api.createSessionApi).not.toHaveBeenCalled();
  });
});
