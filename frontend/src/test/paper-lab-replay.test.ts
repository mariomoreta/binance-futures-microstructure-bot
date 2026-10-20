// @vitest-environment node
import {it, expect, describe} from "vitest";
import artifact from "@/artifacts/paper-lab-replay-v1.json";
import {parsePaperLabReplay, ReplayPlayer, msPerStep, replayPositionState, directionLabel, closeActionLabel} from "@/lib/paper-lab-replay";

const a = artifact as Record<string, unknown>;

it("parse: artifact version and schema are pinned", () => {
  const v = parsePaperLabReplay(a);
  expect(v.schema_version).toBe(1);
  expect(v.artifact_version).toBe("PAPER-LAB-REPLAY-V1");
  expect(v.engine_version).toBe("backtest-offline/v4.2");
  expect(v.label).toContain("replay historico");
  expect(v.eligibility_rule).toContain("primera operacion");
  expect(v.eligibility_rule).toContain("no se elige por rentabilidad");
  expect(v.selection.population_trades_1x).toBe(5255);
  expect(v.selection.exclusions_before_choice.baseline_comparator).toBe(69);
});

it("identidad de la operacion elegida (regla determinista: primera por timestamp)", () => {
  const v = parsePaperLabReplay(a);
  expect(v.replay_id).toBe("PLR-BTCUSDT-LONG-1788903900000");
  expect(v.trade.symbol).toBe("BTCUSDT");
  expect(v.trade.direction).toBe("LONG");
  expect(v.trade.family).toBe("H1");
  expect(v.trade.rules_version).toBe("H1-v1");
  expect(v.trade.segment).toBe("dev");
  expect(v.trade.group).toBe("continuation");
  expect(v.trade.exit_reason).toBe("horizon");
  expect(v.trade.exit_executed).toBe(true);
  expect(v.trade.open_at_end).toBe(false);
  expect(v.trade.funding_accounting_complete).toBe(true);
});

it("tiempos causales: senal -> disponible -> entrada -> salida (sin lookahead)", () => {
  const v = parsePaperLabReplay(a);
  const { trade: t } = v;
  expect(t.event_time_ms).toBeLessThan(t.entry_ms);
  expect(t.entry_ms).toBeLessThanOrEqual(t.exit_ms);
  // disponibilidad = cierre de vela de formacion; la entrada es la primera vela despues del evento
  expect(t.entry_ms).toBeGreaterThanOrEqual((v.event.available_at_ms as number) + 1);
  // salida por horizonte en el instante del horizonte
  expect(t.exit_ms).toBe(t.event_time_ms + v.levels.horizon_ms);
});

it("niveles y costes originales del motor (sin TP ni trailing inventados)", () => {
  const v = parsePaperLabReplay(a);
  expect(v.levels.stop_px).toBeLessThan(v.levels.entry_px); // LONG: stop por debajo
  expect(v.levels.stop_distance_pct).toBe(0.5);
  expect(v.levels.horizon_ms).toBe(3600000);
  expect(v.levels.notional_usdt).toBe(1000);
  expect(v.levels.fee_bps).toBe(5);
  expect(v.levels.spread_bps).toBe(1);
  expect(v.levels.slippage_bps).toBe(2);
  // no take-profit ni trailing en el artefacto: el cierre es el motivo real del replay
  expect(v.trade.exit_reason).not.toBe("take_profit");
  expect(v.limitations.some((l: string) => /take-profit|trailing stop/i.test(l))).toBe(true);
});

it("reconciliacion economica final: neto coincide con el replay del motor", () => {
  const v = parsePaperLabReplay(a);
  const r = v.result.reconciled_to_engine;
  expect(Object.keys(r).length).toBeGreaterThan(0);
  expect(Object.values(r).every(Boolean)).toBe(true);
  expect(v.result.net_pnl).toBe(v.trade.net_pnl);
  expect(v.result.realized_net).toBe(v.trade.net_pnl);
  expect(v.result.gross_pnl + (-1) * (v.costs.friction)).toBeCloseTo(v.result.net_pnl, 6);
  expect(v.result.tolerance.relative).toBe(1e-9);
  expect(v.result.tolerance.absolute_usdt).toBe(1e-9);
});

it("procedencia versionada: hashes completos y sin dependencia de DB canonica", () => {
  const v = parsePaperLabReplay(a);
  expect(v.provenance.source_db).toContain("NO LEIDA");
  expect(v.provenance.db_sha256).toBeNull();
  expect(Object.keys(v.provenance.source_hashes).length).toBeGreaterThanOrEqual(8);
  expect(Object.keys(v.provenance.source_hashes).some((p) => p.includes("C:\\"))).toBe(false);
  for (const hash of Object.values(v.provenance.source_hashes)) expect(hash).toMatch(/^[0-9a-f]{64}$/);
});

it("contexto previo: velas reales, contiguas, solo contexto (no timeline)", () => {
  const v = parsePaperLabReplay(a);
  expect(v.window.n_context_candles).toBeGreaterThan(0);
  expect(v.window.context_candles).toHaveLength(v.window.n_context_candles);
  // contexto contiguo: termina justo antes de la vela de formacion, sin huecos
  const ctx = v.window.context_candles;
  const firstReplayOpen = v.window.candles[0]!.open_time_ms;
  expect(firstReplayOpen - ctx[ctx.length - 1]!.close_time_ms!).toBe(1);
  for (let i = 1; i < ctx.length; i++) {
    expect(ctx[i]!.open_time_ms - ctx[i - 1]!.open_time_ms).toBe(15 * 60 * 1000);
    expect(ctx[i]!.close_time_ms!).toBe(ctx[i]!.open_time_ms + 15 * 60 * 1000 - 1);
  }
  // todas son anteriores al evento y nunca forman parte de pasos (kind=candle)
  for (const c of ctx) expect(c.close_time_ms!).toBeLessThan(v.trade.event_time_ms);
  const stepCandleOpens = v.window.steps.filter((s) => s.kind === "candle").map((s) => s.candle!.open_time_ms);
  for (const c of ctx) expect(stepCandleOpens).not.toContain(c.open_time_ms);
});

it("cinta de pasos: separa EVENTOS de VELAS y no anticipa nada", () => {
  const v = parsePaperLabReplay(a);
  const steps = v.window.steps;
  // cada paso es de uno de los dos tipos, nunca ambos
  for (const s of steps) {
    if (s.kind === "candle") { expect(s.candle).not.toBeNull(); expect(s.events).toHaveLength(0); }
    else { expect(s.candle).toBeNull(); expect(s.events.length).toBeGreaterThanOrEqual(1); }
    // invariante causal: ningun evento supera el reloj del paso
    for (const e of s.events) expect(e.at_ms).toBeLessThanOrEqual(s.known_at_ms!);
  }
  // el reloj es monotono no decreciente
  const clocks = steps.map((s) => s.known_at_ms!);
  for (let i = 1; i < clocks.length; i++) expect(clocks[i]!).toBeGreaterThanOrEqual(clocks[i - 1]!);
  // los eventos clave viven en pasos de evento, en su instante exacto
  const entryStep = steps.find((s) => s.events.some((e) => e.kind === "entry"));
  expect(entryStep!.kind).toBe("event");
  expect(entryStep!.known_at_ms).toBe(v.trade.entry_ms);
  const exitStep = steps.find((s) => s.events.some((e) => e.kind === "exit"));
  expect(exitStep!.kind).toBe("event");
  expect(exitStep!.known_at_ms).toBe(v.trade.exit_ms);
});

describe("fronteras temporales (t-1 ms / t exacto / t+1 ms)", () => {
  const v = parsePaperLabReplay(a);
  const steps = v.window.steps;
  const n = steps.length;

  // Devuelve el estado tras revelar todos los pasos cuyo reloj <= cursorMs.
  const stateAt = (cursorMs: number) => {
    const revealed = steps.filter((s) => s.known_at_ms! <= cursorMs);
    const events = revealed.flatMap((s) => s.events);
    const last = revealed[revealed.length - 1] ?? null;
    return {
      events,
      entered: events.some((e) => e.kind === "entry"),
      exited: events.some((e) => e.kind === "exit"),
      position: last?.position_after ?? null,
      exit: last?.exit ?? null,
    };
  };

  it("entrada: no conocida en t-1 ms, conocida en t y mas alla", () => {
    const t = v.trade.entry_ms;
    expect(stateAt(t - 1).entered).toBe(false);
    expect(stateAt(t).entered).toBe(true);
    expect(stateAt(t + 1).entered).toBe(true);
  });

  it("salida: no conocida en t-1 ms, conocida en t y mas alla", () => {
    const t = v.trade.exit_ms;
    expect(stateAt(t - 1).exited).toBe(false);
    expect(stateAt(t).exited).toBe(true);
    expect(stateAt(t + 1).exited).toBe(true);
  });

  it("el instante justo antes del cierre de la ultima vela NO revela la salida", () => {
    const t = v.trade.exit_ms; // 22:45:00.000
    const beforeClose = t - 1; // 22:44:59.999 = cierre de la ultima vela
    const s = stateAt(beforeClose);
    expect(s.exited).toBe(false);
    expect(s.exit).toBeNull();
    // la posicion seguia abierta: el resultado realizado aun no existe
    expect(s.position!.open).toBe(true);
  });

  it("ningun paso revela un evento con reloj anterior a su instante", () => {
    for (const s of steps) for (const e of s.events) expect(e.at_ms).toBeLessThanOrEqual(s.known_at_ms!);
    // reforzado: existe un paso de vela cuyo reloj (…59.999) precede al evento de cierre
    const candleBeforeExit = steps.find((s) => s.kind === "candle" && s.known_at_ms! === v.trade.exit_ms - 1);
    expect(candleBeforeExit).toBeDefined();
    expect(candleBeforeExit!.events).toHaveLength(0);
  });
});

describe("ReplayPlayer (estado del replay, separado del monitor)", () => {
  const v = parsePaperLabReplay(a);
  const steps = v.window.steps;

  it("inicia en reposo sin revelar nada", () => {
    const p = new ReplayPlayer(steps, { cursor: 0, status: "idle", speed: 1 });
    const view = p.view();
    expect(view.status).toBe("idle");
    expect(view.cursor).toBe(0);
    expect(view.finished).toBe(false);
    expect(view.candles).toHaveLength(0);
    expect(view.exit).toBeNull();
    expect(view.position).toBeNull();
    expect(view.positionState.state).toBe("SIN_POSICION");
    expect(view.canPlay).toBe(true);
    expect(view.canPause).toBe(false);
  });

  it("avance paso a paso solo revela lo conocido hasta el cursor", () => {
    const p = new ReplayPlayer(steps, { cursor: 0, status: "idle", speed: 1 });
    const n = steps.length;
    for (let k = 1; k <= n; k++) {
      p.stepForward();
      const view = p.view();
      expect(view.cursor).toBe(k);
      // solo los pasos de vela aportan velas
      const candleSteps = steps.slice(0, k).filter((s) => s.kind === "candle");
      expect(view.candles).toHaveLength(candleSteps.length);
      // nunca se revelan velas futuras
      for (const c of view.candles) expect(c.open_time_ms).toBeLessThanOrEqual(candleSteps[candleSteps.length - 1]!.candle!.open_time_ms);
      // el cierre (salida) solo aparece en el ultimo paso
      if (steps[k - 1]!.kind !== "event" || !steps[k - 1]!.events.some((e) => e.kind === "exit")) {
        expect(view.exit).toBeNull();
      }
      if (k === n) {
        expect(view.exit).not.toBeNull();
        expect(view.exit!.reason).toBe("horizon");
        expect(view.exit!.executed).toBe(true);
        expect(view.finished).toBe(true);
        expect(view.positionState.state).toBe("CERRADA");
      }
    }
  });

  it("estados: SIN_POSICION -> EN_ESPERA -> ABIERTA -> CERRADA", () => {
    const p = new ReplayPlayer(steps, { cursor: 0, status: "idle", speed: 1 });
    const seen: string[] = [p.view().positionState.state];
    for (let k = 1; k <= steps.length; k++) { p.stepForward(); seen.push(p.view().positionState.state); }
    expect(seen[0]).toBe("SIN_POSICION");
    expect(seen).toContain("EN_ESPERA");
    expect(seen).toContain("ABIERTA");
    expect(seen[seen.length - 1]).toBe("CERRADA");
    // el orden es monotono en el sentido exigido
    expect(seen.indexOf("EN_ESPERA")).toBeLessThan(seen.indexOf("ABIERTA"));
    expect(seen.indexOf("ABIERTA")).toBeLessThan(seen.indexOf("CERRADA"));
  });

  it("no expone P&L final ni MFE/MAE final antes del cierre", () => {
    const sentinelSteps = steps.map((step, index) => index === steps.length - 1 ? {...step, mfe_pct: 999, mae_pct: 999} : step);
    const exitIdx = sentinelSteps.findIndex((s) => s.exit != null);
    // un paso intermedio con posicion abierta y aun sin cierre
    const p = new ReplayPlayer(sentinelSteps, { cursor: exitIdx - 2, status: "paused", speed: 1 });
    const view = p.view();
    expect(view.finished).toBe(false);
    expect(view.exit).toBeNull();
    expect(view.position!.open).toBe(true);
    expect(view.unrealized).not.toBeNull();
    // el bruto no realizado es el de la marca conocida, no el resultado realizado
    expect(view.unrealized!.gross).not.toBe(parsePaperLabReplay(a).trade.gross_pnl);
    expect(view.step!.mfe_pct).not.toBe(999);
    expect(view.step!.mae_pct).not.toBe(999);
  });

  it("play/pause/restart y velocidad", () => {
    const p = new ReplayPlayer(steps, { cursor: 0, status: "idle", speed: 1 });
    p.play(); expect(p.status).toBe("playing");
    p.pause(); expect(p.status).toBe("paused");
    expect(msPerStep(1)).toBe(1200);
    expect(msPerStep(4)).toBe(300);
    expect(msPerStep(0.25)).toBe(4800);
    p.setSpeed(2); expect(p.speed).toBe(2);
    p.restart(); expect(p.status).toBe("idle"); expect(p.cursor).toBe(0);
    expect(p.view().finished).toBe(false);
  });

  it("no retrocede y respeta limites", () => {
    const p = new ReplayPlayer(steps, { cursor: 0, status: "idle", speed: 1 });
    p.stepBackward(); // en 0 no hace nada
    expect(p.cursor).toBe(0);
    p.stepForward(); p.stepForward();
    expect(p.cursor).toBe(2);
    p.seek(5); expect(p.cursor).toBe(Math.min(5, steps.length));
    p.seek(-999); expect(p.cursor).toBe(0);
    p.seek(99999); expect(p.cursor).toBe(steps.length); expect(p.status).toBe("finished");
  });
});

describe("direccion vs accion de cierre (nunca 'compra en espera')", () => {
  it("LONG cierra con venta; SHORT cierra con compra", () => {
    expect(directionLabel("LONG")).toBe("LONG");
    expect(directionLabel("SHORT")).toBe("SHORT");
    expect(closeActionLabel("LONG")).toBe("cierre = venta");
    expect(closeActionLabel("SHORT")).toBe("cierre = compra");
    // la accion de cierre nunca describe un estado de espera
    for (const d of ["LONG", "SHORT"]) expect(closeActionLabel(d)).not.toMatch(/espera/i);
  });
});

describe("estado del replay derivado solo de lo revelado", () => {
  const v = parsePaperLabReplay(a);
  it("sin eventos -> SIN_POSICION; con senal -> EN_ESPERA", () => {
    expect(replayPositionState([], null, null, false).state).toBe("SIN_POSICION");
    expect(replayPositionState([{at_ms: 1, label: "s", kind: "signal"}], null, null, false).state).toBe("EN_ESPERA");
  });
});

it("rechaza artefato con schema no soportado", () => {
  expect(() => parsePaperLabReplay({...a, schema_version: 2})).toThrow("UNSUPPORTED_PAPER_LAB_REPLAY_SCHEMA");
});
it("rechaza artefato con version desconocida", () => {
  expect(() => parsePaperLabReplay({...a, artifact_version: "OTRO"})).toThrow("UNKNOWN_PAPER_LAB_REPLAY_ARTIFACT");
});
it("rechaza artefato sin trade", () => {
  const b = {...a} as Record<string, unknown>;
  delete b.trade;
  expect(() => parsePaperLabReplay(b)).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
});
it("rechaza numeros no finitos", () => {
  expect(() => parsePaperLabReplay({...a, trade: {...(a.trade as object), net_pnl: "no-numero"}})).toThrow("trade.net_pnl");
});
it("rechaza paso de evento que anticipa su instante", () => {
  const b = JSON.parse(JSON.stringify(a)) as Record<string, unknown>;
  const win = (b.window as { steps: Array<{events: Array<{at_ms: number}>; known_at_ms: number}> });
  win.steps[0]!.events[0]!.at_ms = win.steps[0]!.known_at_ms + 1000;
  expect(() => parsePaperLabReplay(b)).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
});
it("rechaza paso de evento con vela (no se rellena donde no la hay)", () => {
  const b = JSON.parse(JSON.stringify(a)) as Record<string, unknown>;
  const win = (b.window as { steps: Array<{kind: string; candle: unknown}> });
  const ev = win.steps.find((s) => s.kind === "event")!;
  ev.candle = {open_time_ms: 1, open: 1, high: 1, low: 1, close: 1, close_time_ms: 2};
  expect(() => parsePaperLabReplay(b)).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
});
