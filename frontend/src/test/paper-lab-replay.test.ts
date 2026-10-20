// @vitest-environment node
import {it, expect, describe} from "vitest";
import artifact from "@/artifacts/paper-lab-replay-v1.json";
import {
  parsePaperLabReplay, ReplayPlayer, msPerStep, replayPositionState,
  directionLabel, closeActionLabel, playerState, playerStateLabel,
  contextCandlesKnownAt,
} from "@/lib/paper-lab-replay";

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
  expect(v.replay_id).toBe("PLR-BTCUSDT-LONG-1788903900000-continuation-1.0x");
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

describe("revelacion causal: formacion vs disponibilidad vs entrada", () => {
  const v = parsePaperLabReplay(a);

  it("formation_time pertenece al patron; available_at es cuando puede conocerse", () => {
    // La formacion es anterior a la disponibilidad, que es anterior a la entrada.
    expect(v.event.event_time_ms).toBeLessThan(v.event.available_at_ms as number);
    expect(v.event.available_at_ms as number).toBeLessThan(v.trade.entry_ms);
  });

  it("la cinta revela la deteccion SOLO en available_at, nunca en formation_time", () => {
    const formationSteps = v.window.steps.filter(
      (s) => s.known_at_ms === v.event.event_time_ms,
    );
    // No hay ningun paso (ni vela ni evento) con reloj == formation_time que revele la deteccion.
    for (const s of formationSteps) {
      expect(s.events.some((e) => e.kind === "detection")).toBe(false);
    }
  });

  it("la formacion se conserva como metadata en el paso de deteccion revelada", () => {
    const detectionSteps = v.window.steps.filter((s) => s.events.some((e) => e.kind === "detection"));
    expect(detectionSteps).toHaveLength(1);
    const step = detectionSteps[0]!;
    expect(step.known_at_ms).toBe(v.event.available_at_ms);
    const ev = step.events.find((e) => e.kind === "detection")!;
    expect(ev.formation_time_ms).toBe(v.event.event_time_ms);
    // La deteccion se conoce en su instante, no en el de formacion.
    expect(ev.at_ms).toBe(v.event.available_at_ms);
  });

  it("hay un paso de vela de formacion conocido ANTES (o en) available_at", () => {
    // La vela de formacion cierra en available_at; su presencia no revela deteccion.
    const formationCandle = v.window.steps.find(
      (s) => s.kind === "candle" && s.candle!.open_time_ms === v.event.event_time_ms,
    )!;
    expect(formationCandle).toBeDefined();
    expect(formationCandle.events).toHaveLength(0);
    expect(formationCandle.candle!.close_time_ms).toBe(v.event.available_at_ms);
  });
});

it("tiempos causales: deteccion -> disponible -> entrada -> salida (sin lookahead)", () => {
  const v = parsePaperLabReplay(a);
  const { trade: t } = v;
  expect(t.event_time_ms).toBeLessThan(t.entry_ms);
  expect(t.entry_ms).toBeLessThanOrEqual(t.exit_ms);
  expect(t.entry_ms).toBeGreaterThanOrEqual((v.event.available_at_ms as number) + 1);
  expect(t.exit_ms).toBe(t.event_time_ms + v.levels.horizon_ms);
});

it("niveles y costes originales del motor (sin TP ni trailing inventados)", () => {
  const v = parsePaperLabReplay(a);
  expect(v.levels.stop_px).toBeLessThan(v.levels.entry_px);
  expect(v.levels.stop_distance_pct).toBe(0.5);
  expect(v.levels.horizon_ms).toBe(3600000);
  expect(v.levels.notional_usdt).toBe(1000);
  expect(v.levels.fee_bps).toBe(5);
  expect(v.levels.spread_bps).toBe(1);
  expect(v.levels.slippage_bps).toBe(2);
  expect(v.trade.exit_reason).not.toBe("take_profit");
  expect(v.limitations.some((l: string) => /take-profit|trailing stop/i.test(l))).toBe(true);
});

describe("reconciliacion economica final: SIN cambios por esta correccion", () => {
  const v = parsePaperLabReplay(a);
  it("neto coincide con el replay del motor y con el valor registrado", () => {
    const r = v.result.reconciled_to_engine;
    expect(Object.values(r).every(Boolean)).toBe(true);
    expect(v.result.net_pnl).toBe(v.trade.net_pnl);
    expect(v.result.realized_net).toBe(v.trade.net_pnl);
    expect(v.result.gross_pnl + (-1) * (v.costs.friction)).toBeCloseTo(v.result.net_pnl, 9);
    // Valores exactos del motor (inalterados por la correccion de causalidad).
    expect(v.trade.gross_pnl).toBeCloseTo(-0.02421656234419101, 12);
    expect(v.trade.net_pnl).toBeCloseTo(-1.6241971890943157, 12);
    expect(v.trade.fees).toBeCloseTo(0.9999878917188278, 12);
    expect(v.trade.funding).toBe(0);
    expect(v.trade.entry_px).toBe(78458.7);
    expect(v.trade.exit_px).toBe(78456.8);
  });
});

it("procedencia versionada: hashes completos y sin dependencia de DB canonica", () => {
  const v = parsePaperLabReplay(a);
  expect(v.provenance.source_db).toContain("NO LEIDA");
  expect(v.provenance.db_sha256).toBeNull();
  expect(Object.keys(v.provenance.source_hashes).length).toBeGreaterThanOrEqual(8);
  expect(Object.keys(v.provenance.source_hashes).some((p) => p.includes("C:\\"))).toBe(false);
  for (const hash of Object.values(v.provenance.source_hashes)) expect(hash).toMatch(/^[0-9a-f]{64}$/);
});

describe("contexto previo y vista inicial (antes de la deteccion)", () => {
  const v = parsePaperLabReplay(a);
  const ctx = v.window.context_candles;

  it("contexto: velas reales, contiguas, solo contexto (no timeline)", () => {
    expect(v.window.n_context_candles).toBeGreaterThan(0);
    expect(ctx).toHaveLength(v.window.n_context_candles);
    const firstReplayOpen = v.window.candles[0]!.open_time_ms;
    expect(firstReplayOpen - ctx[ctx.length - 1]!.close_time_ms!).toBe(1);
    for (let i = 1; i < ctx.length; i++) {
      expect(ctx[i]!.open_time_ms - ctx[i - 1]!.open_time_ms).toBe(15 * 60 * 1000);
      expect(ctx[i]!.close_time_ms!).toBe(ctx[i]!.open_time_ms + 15 * 60 * 1000 - 1);
    }
    for (const c of ctx) expect(c.close_time_ms!).toBeLessThan(v.trade.event_time_ms);
    const stepCandleOpens = v.window.steps.filter((s) => s.kind === "candle").map((s) => s.candle!.open_time_ms);
    for (const c of ctx) expect(stepCandleOpens).not.toContain(c.open_time_ms);
  });

  it("el instante inicial es anterior a la deteccion y no revela nada de la operacion", () => {
    const init = v.window.initial_cursor_ms!;
    expect(init).toBeLessThan(v.event.event_time_ms);
    // En el instante inicial, la deteccion aun no es conocida.
    const revelado = v.window.steps.filter((s) => s.known_at_ms! <= init);
    expect(revelado.some((s) => s.events.some((e) => e.kind === "detection"))).toBe(false);
  });

  it("todas las velas de contexto mostradas cumplen close_time_ms <= cursor", () => {
    const init = v.window.initial_cursor_ms!;
    const shownInit = contextCandlesKnownAt(ctx, init);
    expect(shownInit.length).toBeGreaterThan(0);
    for (const c of shownInit) expect(c.close_time_ms!).toBeLessThanOrEqual(init);
    // A un instante intermedio, nunca se muestra contexto con cierre posterior.
    const mid = v.trade.entry_ms;
    for (const c of contextCandlesKnownAt(ctx, mid)) expect(c.close_time_ms!).toBeLessThanOrEqual(mid);
  });
});

it("cinta de pasos: separa EVENTOS de VELAS y no anticipa nada", () => {
  const v = parsePaperLabReplay(a);
  const steps = v.window.steps;
  for (const s of steps) {
    if (s.kind === "candle") { expect(s.candle).not.toBeNull(); expect(s.events).toHaveLength(0); }
    else { expect(s.candle).toBeNull(); expect(s.events.length).toBeGreaterThanOrEqual(1); }
    for (const e of s.events) expect(e.at_ms).toBeLessThanOrEqual(s.known_at_ms!);
  }
  const clocks = steps.map((s) => s.known_at_ms!);
  for (let i = 1; i < clocks.length; i++) expect(clocks[i]!).toBeGreaterThanOrEqual(clocks[i - 1]!);
  const entryStep = steps.find((s) => s.events.some((e) => e.kind === "entry"));
  expect(entryStep!.kind).toBe("event");
  expect(entryStep!.known_at_ms).toBe(v.trade.entry_ms);
  const exitStep = steps.find((s) => s.events.some((e) => e.kind === "exit"));
  expect(exitStep!.kind).toBe("event");
  expect(exitStep!.known_at_ms).toBe(v.trade.exit_ms);
});

describe("fronteras temporales de revelacion (t-1 ms / t exacto / t+1 ms)", () => {
  const v = parsePaperLabReplay(a);
  const steps = v.window.steps;

  const stateAt = (cursorMs: number) => {
    const revealed = steps.filter((s) => s.known_at_ms! <= cursorMs);
    const events = revealed.flatMap((s) => s.events);
    const last = revealed[revealed.length - 1] ?? null;
    return {
      events,
      detected: events.some((e) => e.kind === "detection"),
      entered: events.some((e) => e.kind === "entry"),
      exited: events.some((e) => e.kind === "exit"),
      position: last?.position_after ?? null,
      exit: last?.exit ?? null,
    };
  };

  it("deteccion: no revelada en available_at-1ms, revelada en available_at y mas alla", () => {
    const t = v.event.available_at_ms as number;
    expect(stateAt(t - 1).detected).toBe(false);
    expect(stateAt(t).detected).toBe(true);
    expect(stateAt(t + 1).detected).toBe(true);
  });

  it("formacion (t-1) NO revela la deteccion (aunque el patron pertenezca a ese instante)", () => {
    const formation = v.event.event_time_ms;
    expect(stateAt(formation).detected).toBe(false);
    expect(stateAt(formation + 1).detected).toBe(false);
  });

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
    const t = v.trade.exit_ms;
    const s = stateAt(t - 1);
    expect(s.exited).toBe(false);
    expect(s.exit).toBeNull();
    expect(s.position!.open).toBe(true);
  });

  it("cambiar datos posteriores no altera la vista anterior al cursor", () => {
    const cursorMs = v.trade.entry_ms;
    const before = steps.filter((s) => s.known_at_ms! <= cursorMs).map((s) => ({kind: s.kind, clock: s.known_at_ms}));
    // Alterar pasos posteriores al cursor no cambia nada anterior a el.
    const tampered = steps.map((s, i) => (s.known_at_ms! > cursorMs ? {...s, events: [], exit: {...(s.exit ?? {reason: "x", px: 0, ms: 0, executed: true}), reason: "ALTERADO"}} : s));
    const after = tampered.filter((s) => s.known_at_ms! <= cursorMs).map((s) => ({kind: s.kind, clock: s.known_at_ms}));
    expect(after).toEqual(before);
    const p1 = new ReplayPlayer(steps, {cursor: steps.filter((s) => s.known_at_ms! <= cursorMs).length, status: "paused"});
    const p2 = new ReplayPlayer(tampered, {cursor: steps.filter((s) => s.known_at_ms! <= cursorMs).length, status: "paused"});
    expect(p1.view().events).toEqual(p2.view().events);
    expect(p1.view().candles).toEqual(p2.view().candles);
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
      const candleSteps = steps.slice(0, k).filter((s) => s.kind === "candle");
      expect(view.candles).toHaveLength(candleSteps.length);
      for (const c of view.candles) expect(c.open_time_ms).toBeLessThanOrEqual(candleSteps[candleSteps.length - 1]!.candle!.open_time_ms);
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

  it("estados de posicion: SIN_POSICION -> EN_ESPERA -> ABIERTA -> CERRADA", () => {
    const p = new ReplayPlayer(steps, { cursor: 0, status: "idle", speed: 1 });
    const seen: string[] = [p.view().positionState.state];
    for (let k = 1; k <= steps.length; k++) { p.stepForward(); seen.push(p.view().positionState.state); }
    expect(seen[0]).toBe("SIN_POSICION");
    expect(seen).toContain("EN_ESPERA");
    expect(seen).toContain("ABIERTA");
    expect(seen[seen.length - 1]).toBe("CERRADA");
    expect(seen.indexOf("EN_ESPERA")).toBeLessThan(seen.indexOf("ABIERTA"));
    expect(seen.indexOf("ABIERTA")).toBeLessThan(seen.indexOf("CERRADA"));
  });

  it("no expone P&L final ni MFE/MAE final antes del cierre", () => {
    const sentinelSteps = steps.map((step, index) => index === steps.length - 1 ? {...step, mfe_pct: 999, mae_pct: 999} : step);
    const exitIdx = sentinelSteps.findIndex((s) => s.exit != null);
    const p = new ReplayPlayer(sentinelSteps, { cursor: exitIdx - 2, status: "paused", speed: 1 });
    const view = p.view();
    expect(view.finished).toBe(false);
    expect(view.exit).toBeNull();
    expect(view.position!.open).toBe(true);
    expect(view.unrealized).not.toBeNull();
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
    p.stepBackward();
    expect(p.cursor).toBe(0);
    p.stepForward(); p.stepForward();
    expect(p.cursor).toBe(2);
    p.seek(5); expect(p.cursor).toBe(Math.min(5, steps.length));
    p.seek(-999); expect(p.cursor).toBe(0);
    p.seek(99999); expect(p.cursor).toBe(steps.length); expect(p.status).toBe("finished");
  });
});

describe("estado del REPRODUCTOR (independiente del estado de posicion)", () => {
  const v = parsePaperLabReplay(a);
  const n = v.window.steps.length;

  it("distingue sin_iniciar / reproduciendo / pausado / terminado", () => {
    expect(playerState("idle", 0, n)).toBe("sin_iniciar");
    expect(playerState("playing", 0, n)).toBe("reproduciendo");
    expect(playerState("playing", 3, n)).toBe("reproduciendo");
    expect(playerState("paused", 3, n)).toBe("pausado");
    expect(playerState("idle", 3, n)).toBe("pausado"); // avanzar manualmente pausa
    expect(playerState("paused", n, n)).toBe("terminado");
    expect(playerState("playing", n, n)).toBe("terminado");
    expect(playerStateLabel("sin_iniciar")).toBe("SIN INICIAR");
    expect(playerStateLabel("reproduciendo")).toBe("REPRODUCIENDO");
    expect(playerStateLabel("pausado")).toBe("PAUSADO");
    expect(playerStateLabel("terminado")).toBe("TERMINADO");
  });

  it("estado del reproductor y estado de posicion son independientes", () => {
    // Tras avanzar manualmente hasta la posicion abierta: reproductor pausado,
    // posicion ABIERTA (no "REPOSO").
    const p = new ReplayPlayer(v.window.steps, {cursor: 0, status: "idle"});
    const open = v.window.steps.findIndex((s) => s.position_after.open);
    for (let k = 0; k <= open; k++) p.stepForward();
    const view = p.view();
    expect(view.positionState.state).toBe("ABIERTA");
    expect(playerState("idle", p.cursor, p.n)).toBe("pausado");
    expect(playerStateLabel(playerState("idle", p.cursor, p.n))).not.toBe("REPOSO");
  });

  it("reiniciar restablece reproductor (sin_iniciar) y posicion (SIN_POSICION)", () => {
    const p = new ReplayPlayer(v.window.steps, {cursor: 0, status: "idle"});
    for (let k = 0; k < 4; k++) p.stepForward();
    p.restart();
    const view = p.view();
    expect(playerState(p.status, p.cursor, p.n)).toBe("sin_iniciar");
    expect(view.positionState.state).toBe("SIN_POSICION");
    expect(view.cursor).toBe(0);
  });
});

describe("direccion vs accion de cierre (nunca 'compra en espera')", () => {
  it("LONG cierra con venta; SHORT cierra con compra", () => {
    expect(directionLabel("LONG")).toBe("LONG");
    expect(directionLabel("SHORT")).toBe("SHORT");
    expect(closeActionLabel("LONG")).toBe("cierre = venta");
    expect(closeActionLabel("SHORT")).toBe("cierre = compra");
    for (const d of ["LONG", "SHORT"]) expect(closeActionLabel(d)).not.toMatch(/espera/i);
  });
});

describe("estado del replay derivado solo de lo revelado", () => {
  it("sin eventos -> SIN_POSICION; con deteccion -> EN_ESPERA", () => {
    expect(replayPositionState([], null, null, false).state).toBe("SIN_POSICION");
    expect(replayPositionState([{at_ms: 1, label: "d", kind: "detection", formation_time_ms: 0}], null, null, false).state).toBe("EN_ESPERA");
  });
});

describe("rechazos de artefacto invalido o ausente", () => {
  it("rechaza schema no soportado", () => {
    expect(() => parsePaperLabReplay({...a, schema_version: 2})).toThrow("UNSUPPORTED_PAPER_LAB_REPLAY_SCHEMA");
  });
  it("rechaza version desconocida", () => {
    expect(() => parsePaperLabReplay({...a, artifact_version: "OTRO"})).toThrow("UNKNOWN_PAPER_LAB_REPLAY_ARTIFACT");
  });
  it("rechaza artefacto sin trade", () => {
    const b = {...a} as Record<string, unknown>;
    delete b.trade;
    expect(() => parsePaperLabReplay(b)).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
  });
  it("rechaza artefacto ausente / no objeto", () => {
    expect(() => parsePaperLabReplay(null)).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
    expect(() => parsePaperLabReplay(undefined)).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
    expect(() => parsePaperLabReplay("x")).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
  });
  it("rechaza numeros no finitos", () => {
    expect(() => parsePaperLabReplay({...a, trade: {...(a.trade as object), net_pnl: "no-numero"}})).toThrow("trade.net_pnl");
  });
  it("rechaza paso de evento que anticipa su instante", () => {
    const b = JSON.parse(JSON.stringify(a)) as Record<string, unknown>;
    const win = (b.window as { steps: Array<{kind: string; events: Array<{at_ms: number}>; known_at_ms: number}> });
    const evStep = win.steps.find((s) => s.kind === "event")!;
    evStep.events[0]!.at_ms = evStep.known_at_ms + 1000;
    expect(() => parsePaperLabReplay(b)).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
  });
  it("rechaza paso de evento con vela (no se rellena donde no la hay)", () => {
    const b = JSON.parse(JSON.stringify(a)) as Record<string, unknown>;
    const win = (b.window as { steps: Array<{kind: string; candle: unknown}> });
    const ev = win.steps.find((s) => s.kind === "event")!;
    ev.candle = {open_time_ms: 1, open: 1, high: 1, low: 1, close: 1, close_time_ms: 2};
    expect(() => parsePaperLabReplay(b)).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
  });
  it("rechaza deteccion revelada antes de su formacion", () => {
    const b = JSON.parse(JSON.stringify(a)) as Record<string, unknown>;
    const win = (b.window as { steps: Array<{events: Array<{kind: string; formation_time_ms?: number}>}> });
    const step = win.steps.find((s) => s.events.some((e) => e.kind === "detection"))!;
    step.events.find((e) => e.kind === "detection")!.formation_time_ms = Number.MAX_SAFE_INTEGER;
    expect(() => parsePaperLabReplay(b)).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
  });
  it("rechaza deteccion sin hora de formacion", () => {
    const b = JSON.parse(JSON.stringify(a)) as Record<string, unknown>;
    const win = (b.window as { steps: Array<{events: Array<{kind: string; formation_time_ms?: number}>}> });
    const step = win.steps.find((s) => s.events.some((e) => e.kind === "detection"))!;
    delete step.events.find((e) => e.kind === "detection")!.formation_time_ms;
    expect(() => parsePaperLabReplay(b)).toThrow("PAPER_LAB_REPLAY_UNAVAILABLE");
  });
});
