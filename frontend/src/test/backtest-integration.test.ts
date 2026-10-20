// @vitest-environment node
// Integracion REAL (gated): dos ejecuciones consecutivas del ejecutor offline
// Python sobre el paquete EVAL-CENSUS-V2. No toca DBs canonicas ni el monitor:
// los resultados viven en un directorio temporal. Se ejecuta solo con
// BACKTEST_INTEGRATION=1 porque tarda ~11 s por corrida.
import {afterAll, describe, expect, it, vi} from "vitest";
import {existsSync, mkdtempSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

const REPO = "C:/proyectos/binance-futures-microstructure-bot";
const runsDir = mkdtempSync(join(tmpdir(), "bt-integration-"));
const livePids = new Set<number>();

process.env.BACKTEST_ROOT = REPO;
process.env.BACKTEST_RUNS_DIR = runsDir;
process.env.BACKTEST_PYTHON = process.env.BACKTEST_PYTHON ?? "python";
vi.resetModules();

const enabled = process.env.BACKTEST_INTEGRATION === "1";

async function waitFor<T>(
  fn: () => T | null | undefined, timeoutMs = 120_000, step = 500,
): Promise<T> {
  const end = Date.now() + timeoutMs;
  for (;;) {
    const value = fn();
    if (value) return value;
    if (Date.now() > end) throw new Error("timeout esperando la ejecucion real");
    await new Promise((r) => setTimeout(r, step));
  }
}

afterAll(() => {
  for (const pid of livePids) {
    try { process.kill(pid); } catch { /* ya termino */ }
  }
  try { rmSync(runsDir, {recursive: true, force: true}); } catch { /* ignore */ }
});

describe.skipIf(!enabled)("backtest integration: real offline executor", () => {
  it("two consecutive runs complete, each with verified results, and the second is not blocked", async () => {
    const mod = await import("@/lib/backtest-control");
    const exp = "eval-census-v2-trio" as const;
    const first = mod.startJob(exp);
    expect(first.started).toBe(true);
    expect(first.run_id).toMatch(/^bt-/);
    if (first.state?.executor_pid) livePids.add(first.state.executor_pid);

    const done1 = await waitFor(() => {
      const s = mod.readRunState(exp, first.run_id!);
      return s?.status === "completado" || s?.status === "fallido" ? s : null;
    });
    expect(done1.status).toBe("completado");
    expect(done1.error).toBeNull();
    expect(done1.n_trades).toBeGreaterThan(0);
    expect(done1.reconciliation_ok).toBe(true);
    expect(done1.result_hashes).toBeTruthy();
    // El lock NO se libera solo porque el estado sea terminal.
    expect(existsSync(join(runsDir, exp, "run.lock"))).toBe(true);

    const results1 = mod.readRunResults(exp, first.run_id!);
    expect(results1.available).toBe(true);
    if (results1.available) {
      expect(results1.run_id).toBe(first.run_id);
      expect(results1.trades.length).toBeGreaterThan(0);
      expect(Object.keys(results1.result_hashes).sort()).toEqual(
        ["reconciliation.json", "summary.json", "trades.json"]);
    }
    if (done1.executor_pid) {
      livePids.delete(done1.executor_pid);
      await waitFor(() => {
        try { process.kill(done1.executor_pid!, 0); return null; } catch { return true; }
      }, 30_000);
    }

    // Segunda solicitud EXPLICITA: el ejecutor anterior ya no existe.
    const second = mod.startJob(exp);
    expect(second.started).toBe(true);
    expect(second.run_id).not.toBe(first.run_id);
    if (second.state?.executor_pid) livePids.add(second.state.executor_pid);

    const done2 = await waitFor(() => {
      const s = mod.readRunState(exp, second.run_id!);
      return s?.status === "completado" || s?.status === "fallido" ? s : null;
    });
    expect(done2.status).toBe("completado");
    expect(done2.run_id).toBe(second.run_id);
    const results2 = mod.readRunResults(exp, second.run_id!);
    expect(results2.available).toBe(true);
    if (results2.available) expect(results2.run_id).toBe(second.run_id);
    // Los resultados de la PRIMERA siguen disponibles y NO se mezclan.
    const again1 = mod.readRunResults(exp, first.run_id!);
    expect(again1.available).toBe(true);
    if (again1.available) expect(again1.run_id).toBe(first.run_id);

    // Replay de una operacion real, vinculado a la SEGUNDA ejecucion.
    if (results2.available) {
      const trade = results2.trades.find((t) => t.exit_executed && !t.open_at_end)
        ?? results2.trades[0]!;
      const replay = mod.materializeReplay({
        experiment: exp, event_id: String(trade.event_id),
        group: String(trade.group), segment: String(trade.segment),
        scale: Number(trade.scale), run_id: second.run_id,
      });
      expect(replay.ok, JSON.stringify(replay)).toBe(true);
      if (replay.ok) {
        expect(replay.run_id).toBe(second.run_id);
        expect((replay.artifact as {backtest_run_id?: string}).backtest_run_id)
          .toBe(second.run_id);
      }
    }
    if (done2.executor_pid) {
      livePids.delete(done2.executor_pid);
      await waitFor(() => {
        try { process.kill(done2.executor_pid!, 0); return null; } catch { return true; }
      }, 30_000);
    }
  }, 240_000);
});
