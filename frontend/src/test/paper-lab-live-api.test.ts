// @vitest-environment node
import {it, expect, describe, vi, beforeEach} from "vitest";
import {
  sessionView, formatMoneyPL, formatPricePL, formatPctPL, fmtUtcPL,
  type PaperSessionConfig, type PaperSessionState, type PaperCandle,
  type PaperCandidateDecision,
} from "@/lib/paper-lab-live";

function mkCandle(openTime: number, open: number, high: number,
                  low: number, close: number): PaperCandle {
  return {
    open_time_ms: openTime, open, high, low, close,
    close_time_ms: openTime + 15 * 60 * 1000 - 1,
  };
}

function mkState(overrides: Partial<PaperSessionState> = {}): PaperSessionState {
  const base: PaperSessionState = {
    session_id: "PL-BTCUSDT-LONG-1234567890-abcd1234",
    created_at_ms: 1788904800000,
    updated_at_ms: 1788904800000,
    status: "en_espera",
    config: {
      symbol: "BTCUSDT", interval: "15m", direction: "LONG",
      notional_usdt: 1000, entry_px: 100, stop_px: 95,
      stop_distance_pct: 5, horizon_ms: 3 * 60 * 60 * 1000,
      fee_bps: 5, spread_bps: 1, slippage_bps: 2,
      hypothesis_id: "ENGINEERING-FIXTURE-v1",
      hypothesis_version: "1.0",
      decision: "ENTRADA_SIMULADA",
      decision_reason: "candidato valido",
    },
    candles: [mkCandle(0, 100, 102, 99, 101)],
    context_candles: [],
    cursor: 0,
    position: {
      open: false, direction: null, entry_px: null, entry_qty: null,
      entry_cost: null, entry_ms: null, stop_px: 95, mark_px: null,
      mark_ms: null, unrealized_gross: null, unrealized_net: null,
      mfe_pct: null, mae_pct: null,
    },
    costs: {
      fee_bps: 5, spread_bps: 1, entry_fees: 0.5, exit_fees: 0,
      entry_spread_slip: 0.3, exit_spread_slip: 0, funding: 0,
      friction: 0.8,
    },
    events: [],
    result: null,
    clock_ms: null,
    config_hash: "abc123def456",
    input_hash: "def456ghi789",
    engine_version: "paper-lab-engine/v1.0",
    limitations: ["engineering-fixture-only"],
  };
  return {...base, ...overrides};
}

describe("sessionView (vista derivada para UI)", () => {
  it("estado sin_iniciar: puede decidir, no puede entrar", () => {
    const s = mkState({status: "sin_iniciar"});
    const v = sessionView(s);
    expect(v.status).toBe("sin_iniciar");
    expect(v.canDecide).toBe(true);
    expect(v.canEnter).toBe(false);
    expect(v.canStep).toBe(false);
    expect(v.canExit).toBe(false);
    expect(v.progress).toBe(0);
  });

  it("estado en_espera con decision: puede entrar", () => {
    const s = mkState({status: "en_espera"});
    const v = sessionView(s);
    expect(v.canEnter).toBe(true);
    expect(v.canStep).toBe(false);
    expect(v.canExit).toBe(false);
  });

  it("estado abierta con posicion: puede hacer step y salir", () => {
    const s = mkState({
      status: "abierta", cursor: 0,
      candles: [mkCandle(0, 100, 102, 99, 101), mkCandle(900000, 101, 103, 100, 102)],
      position: {...mkState().position, open: true, entry_px: 100, entry_qty: 10},
    });
    const v = sessionView(s);
    expect(v.canStep).toBe(true);
    expect(v.canExit).toBe(true);
    expect(v.canEnter).toBe(false);
  });

  it("estado cerrada: no puede hacer nada", () => {
    const s = mkState({status: "cerrada"});
    const v = sessionView(s);
    expect(v.canEnter).toBe(false);
    expect(v.canStep).toBe(false);
    expect(v.canExit).toBe(false);
    expect(v.canStop).toBe(false);
  });

  it("sin decision: no puede entrar", () => {
    const s = mkState({status: "sin_iniciar", config: {...mkState().config, decision: null}});
    const v = sessionView(s);
    expect(v.canDecide).toBe(true);
    expect(v.canEnter).toBe(false);
  });
});

describe("format helpers", () => {
  it("formatMoneyPL", () => {
    expect(formatMoneyPL(5)).toBe("+5.00");
    expect(formatMoneyPL(-3)).toBe("-3.00");
    expect(formatMoneyPL(null)).toBe("—");
  });
  it("formatPricePL", () => {
    expect(formatPricePL(100.5)).toBe("100.50");
    expect(formatPricePL(null)).toBe("—");
  });
  it("formatPctPL", () => {
    expect(formatPctPL(2.5)).toBe("+2.50%");
    expect(formatPctPL(-1.2)).toBe("-1.20%");
    expect(formatPctPL(null)).toBe("—");
  });
  it("fmtUtcPL", () => {
    expect(fmtUtcPL(1788904800000)).toContain("2026");
    expect(fmtUtcPL(null)).toBe("—");
  });
});
