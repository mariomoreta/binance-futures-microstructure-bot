// @vitest-environment node
import {it, expect, describe} from "vitest";
import {
  createPaperSession, stepForward, manualExit, restartSession, stopSession,
  selectOperation, sessionView, formatMoneyPL, formatPricePL, formatPctPL,
  fmtUtcPL, type PaperSessionConfig, type PaperCandle, type PaperStepResult,
  type PaperSessionStatus, type PaperSessionState,
} from "@/lib/paper-lab-live";
import {PAPER_FIXTURES} from "@/lib/paper-fixtures";

function candle(openTime: number, open: number, high: number, low: number, close: number): PaperCandle {
  return {open_time_ms: openTime, open, high, low, close, close_time_ms: openTime + 15 * 60 * 1000 - 1};
}

function openSession(s: PaperSessionState): PaperSessionState {
  s.status = "abierta" as PaperSessionStatus;
  return s;
}

const baseConfig: PaperSessionConfig = {
  symbol: "BTCUSDT",
  interval: "15m",
  direction: "LONG",
  notional_usdt: 1000,
  entry_px: 100,
  stop_px: 95,
  stop_distance_pct: 5,
  horizon_ms: 3 * 60 * 60 * 1000,
  fee_bps: 5,
  spread_bps: 1,
  slippage_bps: 2,
};

const upCandles: PaperCandle[] = [
  candle(0, 100, 102, 99, 101),
  candle(900000, 101, 103, 100, 102),
  candle(1800000, 102, 104, 101, 103),
];

describe("createPaperSession", () => {
  it("crea sesion en_espera con costes de entrada devengados y sin posicion", () => {
    const s = createPaperSession(baseConfig, upCandles);
    expect(s.status).toBe("en_espera");
    expect(s.position.open).toBe(false);
    expect(s.costs.entry_fees).toBeCloseTo(1000 * (5 / 10000), 9);
    expect(s.costs.entry_spread_slip).toBeCloseTo(1000 * ((1 + 2) / 10000), 9);
    expect(s.costs.friction).toBeCloseTo(0.8, 9);
    expect(s.clock_ms).toBeNull();
    expect(s.result).toBeNull();
  });
});

describe("stepForward sin entrada", () => {
  it("avanza el cursor sin abrir posicion ni crear resultado", () => {
    const s = createPaperSession(baseConfig, upCandles);
    const r = stepForward(s);
    expect(r.kind).toBe("step");
    expect(r.state.cursor).toBe(1);
    expect(r.state.position.open).toBe(false);
    expect(r.state.result).toBeNull();
    expect(r.state.clock_ms!).toBe(upCandles[0]!.close_time_ms);
  });
});

describe("entrada y gestion de posicion", () => {
  it("entrar abre la posicion y establece marca, qty y costes", () => {
    const s = openSession(createPaperSession(baseConfig, upCandles));
    const r = stepForward(s);
    expect(r.kind).toBe("step");
    expect(r.state.status).toBe("abierta");
    expect(r.state.position.open).toBe(true);
    expect(r.state.position.entry_px).toBe(100);
    expect(r.state.position.entry_qty).toBeCloseTo(1000 / 100, 9);
    expect(r.state.position.entry_ms!).toBe(upCandles[0]!.close_time_ms);
    expect(r.state.position.mark_px!).toBe(100); // marca = precio de entrada al entrar
    expect(r.state.events.some((e) => e.kind === "entry")).toBe(true);
  });

  it("avance con posicion abierta actualiza marca y P&L no realizado", () => {
    const s = openSession(createPaperSession(baseConfig, upCandles));
    let r = stepForward(s); // ejecuta entrada en vela 0, avanza a vela 1
    expect(r.kind).toBe("step");
    expect(r.state.position.open).toBe(true);
    r = stepForward(r.state); // avanza a vela 2, actualiza marca a 102
    expect(r.kind).toBe("step");
    expect(r.state.position.mark_px).toBe(102);
    expect(r.state.position.unrealized_gross).toBeCloseTo((102 - 100) * 10, 9);
    expect(r.state.events.some((e) => e.kind === "mark")).toBe(true);
  });

  it("MFE sube con precios favorables, MAE baja con precios adversos", () => {
    const s = openSession(createPaperSession(baseConfig, upCandles));
    let r = stepForward(s); // entrar
    r = stepForward(r.state); // avanzar: marca 102 -> MFE +2%
    expect(r.state.position.mfe_pct).toBeCloseTo(2, 9);
    const downCandles: PaperCandle[] = [
      candle(0, 100, 102, 99, 101),
      candle(900000, 101, 101, 97, 98),
    ];
    const s2 = openSession(createPaperSession(baseConfig, downCandles));
    let r2 = stepForward(s2); // entrar
    r2 = stepForward(r2.state); // avanzar: marca 98 -> MAE -2%
    expect(r2.state.position.mae_pct).toBeCloseTo(-2, 9);
  });
});

describe("salida por stop", () => {
  it("vela cuyo low toca el stop cierra la posicion al precio de stop", () => {
    const stopCandles: PaperCandle[] = [
      candle(0, 100, 102, 99, 101),
      candle(900000, 101, 101, 94, 100),
    ];
    const s = openSession(createPaperSession(baseConfig, stopCandles));
    let r = stepForward(s);
    expect(r.kind).toBe("step");
    r = stepForward(r.state);
    expect(r.kind).toBe("exit_executed");
    if (r.kind !== "exit_executed") throw new Error("esperaba exit_executed");
    expect(r.exit).toBe("stop");
    expect(r.state.status).toBe("cerrada");
    expect(r.state.position.open).toBe(false);
    expect(r.state.position.mark_px).toBe(95);
    expect(r.state.result?.exit_reason).toBe("stop");
    expect(r.state.result?.exit_executed).toBe(true);
    expect(r.state.result?.gross_pnl).toBeCloseTo(-50, 9);
    expect(r.state.result?.net_pnl).toBeLessThan(-50);
  });
});

describe("salida por horizonte", () => {
  it("al alcanzar entry_ms + horizon_ms cierra al precio de marca", () => {
    const config: PaperSessionConfig = {...baseConfig, horizon_ms: 15 * 60 * 1000};
    const s = openSession(createPaperSession(config, upCandles));
    let r = stepForward(s);
    r = stepForward(r.state);
    expect(r.kind).toBe("exit_executed");
    if (r.kind !== "exit_executed") throw new Error("esperaba exit_executed");
    expect(r.exit).toBe("horizon");
    expect(r.state.status).toBe("cerrada");
    expect(r.state.result?.exit_reason).toBe("horizon");
    expect(r.state.result?.exit_executed).toBe(true);
  });
});

describe("salida manual", () => {
  it("cerrar posicion manualmente congela el resultado", () => {
    const s = openSession(createPaperSession(baseConfig, upCandles));
    let r = stepForward(s);
    r = stepForward(r.state);
    const m = manualExit(r.state);
    expect(m.kind).toBe("exit_executed");
    if (m.kind !== "exit_executed") throw new Error("esperaba exit_executed");
    expect(m.exit).toBe("manual");
    expect(m.state.status).toBe("cerrada");
    expect(m.state.position.open).toBe(false);
    expect(m.state.result?.exit_reason).toBe("manual");
    expect(m.state.result?.exit_executed).toBe(true);
  });
});

describe("open_at_end (sin salida ejecutada al terminar velas)", () => {
  it("si se agotan velas sin salida, la posicion queda abierta y open_at_end=true", () => {
    const s = openSession(createPaperSession(baseConfig, upCandles));
    let r = stepForward(s);
    r = stepForward(r.state);
    r = stepForward(r.state);
    expect(r.kind).toBe("finished");
    expect(r.state.status).toBe("cerrada");
    expect(r.state.result?.open_at_end).toBe(true);
    expect(r.state.result?.exit_executed).toBe(false);
    expect(r.state.result?.exit_reason).toBeNull();
  });
});

describe("restart y stop", () => {
  it("restart restaura sesion a en_espera sin posicion", () => {
    const s = openSession(createPaperSession(baseConfig, upCandles));
    let r = stepForward(s);
    r = stepForward(r.state);
    const rs = restartSession(r.state);
    expect(rs.status).toBe("en_espera");
    expect(rs.position.open).toBe(false);
    expect(rs.result).toBeNull();
    expect(rs.cursor).toBe(0);
  });

  it("stop congela la sesion en detenida", () => {
    const s = openSession(createPaperSession(baseConfig, upCandles));
    let r = stepForward(s);
    const st = stopSession(r.state);
    expect(st.status).toBe("detenida");
    expect(st.position.open).toBe(true);
  });
});

describe("fixtures", () => {
  it("cada fixture produce una sesion valida y se puede avanzar", () => {
    for (const id of Object.keys(PAPER_FIXTURES)) {
      const entry = PAPER_FIXTURES[id];
      if (!entry) throw new Error(`fixture ${id} no encontrado`);
      const s = openSession(createPaperSession(entry.config, entry.candles, entry.context));
      expect(s.status).toBe("abierta");
      let r: PaperStepResult = stepForward(s);
      expect(r.kind).toBe("step");
      expect(r.state.status).toBe("abierta");
      let steps = 0;
      while (r.kind === "step" && steps < entry.candles.length + 2) {
        r = stepForward(r.state);
        steps += 1;
      }
      expect(["exit_executed", "finished"]).toContain(r.kind);
      expect(r.state.status).toBe("cerrada");
    }
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

describe("sessionView", () => {
  it("deriva vista para la UI", () => {
    const s = createPaperSession(baseConfig, upCandles);
    const v = sessionView(s);
    expect(v.status).toBe("en_espera");
    expect(v.canEnter).toBe(true);
    expect(v.canStep).toBe(false);
    expect(v.canExit).toBe(false);
    expect(v.canRestart).toBe(true);
    expect(v.progress).toBe(0);
  });
});
