// @vitest-environment node
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

// Directorio de runs aislado en un temp real, fuera del repo y de OneDrive.
let runsDir: string;
beforeEach(() => {
  runsDir = mkdtempSync(join(tmpdir(), "bt-ctrl-"));
  process.env.BACKTEST_RUNS_DIR = runsDir;
  vi.resetModules();
});
afterEach(() => {
  delete process.env.BACKTEST_RUNS_DIR;
  try { rmSync(runsDir, {recursive: true, force: true}); } catch { /* ignore */ }
});

const load = () => import("@/lib/backtest-control");
const jobDir = (experiment: string) => join(runsDir, experiment);

function writeState(experiment: string, state: Record<string, unknown>) {
  mkdirSync(jobDir(experiment), {recursive: true});
  writeFileSync(join(jobDir(experiment), "job_state.json"), JSON.stringify(state));
}

describe("backtest-control: allowlist identity", () => {
  it("accepts only the allowlisted experiment id", async () => {
    const {isBacktestExperiment} = await load();
    expect(isBacktestExperiment("eval-census-v2-trio")).toBe(true);
    expect(isBacktestExperiment("../x")).toBe(false);
    expect(isBacktestExperiment("")).toBe(false);
    expect(isBacktestExperiment(null)).toBe(false);
  });
});

describe("backtest-control: persisted job state", () => {
  it("returns null when there is no state (never fabricates a job)", async () => {
    const {readJobState} = await load();
    expect(readJobState("eval-census-v2-trio")).toBeNull();
  });

  it("reads a persisted completed state with its result hashes", async () => {
    writeState("eval-census-v2-trio", {
      job_id: "eval-census-v2-trio", experiment_id: "eval-census-v2-trio",
      status: "completado", n_trades: 15765, reconciliation_ok: true,
      result_hashes: {"summary.json": "abc"},
    });
    const {readJobState} = await load();
    const s = readJobState("eval-census-v2-trio");
    expect(s?.status).toBe("completado");
    expect(s?.n_trades).toBe(15765);
    expect(s?.reconciliation_ok).toBe(true);
  });

  it("reconciles an orphan 'ejecutando' state to fallido when the process is gone", async () => {
    // PID 999999 es practicamente seguro inexistente: process.kill(pid,0) lanza.
    writeState("eval-census-v2-trio", {
      job_id: "eval-census-v2-trio", experiment_id: "eval-census-v2-trio",
      status: "ejecutando", started_at_ms: 1, updated_at_ms: 2,
    });
    writeFileSync(join(jobDir("eval-census-v2-trio"), "job_pid.json"), JSON.stringify({pid: 999999}));
    const {readJobState} = await load();
    const s = readJobState("eval-census-v2-trio");
    expect(s?.status).toBe("fallido");
    expect(s?.error).toBe("PROCESS_INTERRUPTED");
    // El estado reconciliado se persiste para no reejecutar por error.
    const onDisk = JSON.parse(readFileSync(join(jobDir("eval-census-v2-trio"), "job_state.json"), "utf8"));
    expect(onDisk.status).toBe("fallido");
  });

  it("keeps an 'ejecutando' state while its process is alive", async () => {
    writeState("eval-census-v2-trio", {
      job_id: "eval-census-v2-trio", experiment_id: "eval-census-v2-trio",
      status: "ejecutando", started_at_ms: 1, updated_at_ms: 2,
    });
    writeFileSync(join(jobDir("eval-census-v2-trio"), "job_pid.json"), JSON.stringify({pid: process.pid}));
    const {readJobState} = await load();
    expect(readJobState("eval-census-v2-trio")?.status).toBe("ejecutando");
  });

  it("ignores an unknown status rather than trusting it", async () => {
    writeState("eval-census-v2-trio", {status: "weird"});
    const {readJobState} = await load();
    expect(readJobState("eval-census-v2-trio")).toBeNull();
  });
});

describe("backtest-control: results are only served when completed", () => {
  it("reports not-ready with the real status, never mock rows", async () => {
    // Sin PID vivo, un 'ejecutando' huerfano se reconcilia a fallido.
    writeState("eval-census-v2-trio", {status: "ejecutando"});
    const {readResults} = await load();
    const r = readResults("eval-census-v2-trio");
    expect(r.available).toBe(false);
    if (!r.available) expect(r.status).toBe("fallido");
  });

  it("reports not-ready while a live process is still running", async () => {
    writeState("eval-census-v2-trio", {status: "ejecutando"});
    writeFileSync(join(jobDir("eval-census-v2-trio"), "job_pid.json"), JSON.stringify({pid: process.pid}));
    const {readResults} = await load();
    const r = readResults("eval-census-v2-trio");
    expect(r.available).toBe(false);
    if (!r.available) expect(r.status).toBe("ejecutando");
  });

  it("reports sin_ejecutar when no run exists", async () => {
    const {readResults} = await load();
    const r = readResults("eval-census-v2-trio");
    expect(r.available).toBe(false);
    if (!r.available) expect(r.status).toBe("sin_ejecutar");
  });

  it("serves completed summary + trades", async () => {
    writeState("eval-census-v2-trio", {status: "completado"});
    writeFileSync(join(jobDir("eval-census-v2-trio"), "summary.json"),
      JSON.stringify({experiment_id: "eval-census-v2-trio", n_trades_1x: 5255}));
    writeFileSync(join(jobDir("eval-census-v2-trio"), "trades.json"),
      JSON.stringify({trades: [{trade_id: "t1"}]}));
    const {readResults} = await load();
    const r = readResults("eval-census-v2-trio");
    expect(r.available).toBe(true);
    if (r.available) expect(r.trades).toHaveLength(1);
  });
});

describe("backtest-control: replay link identity + cache", () => {
  it("names the artifact deterministically from the operation identity", async () => {
    const {replayArtifactName} = await load();
    const base = {experiment: "eval-census-v2-trio" as const, event_id: "e1",
      group: "continuation", segment: "dev", scale: 1};
    const a = replayArtifactName(base);
    const b = replayArtifactName({...base});
    const c = replayArtifactName({...base, scale: 2});
    expect(a).toBe(b);
    expect(a).not.toBe(c);
    expect(a).toMatch(/^replay_[0-9a-f]{16}\.json$/);
  });

  it("refuses materialization when the experiment is not completed", async () => {
    writeState("eval-census-v2-trio", {status: "ejecutando"});
    const {materializeReplay} = await load();
    const r = materializeReplay({experiment: "eval-census-v2-trio", event_id: "e",
      group: "continuation", segment: "dev", scale: 1});
    expect(r.ok).toBe(false);
    expect(r.error).toBe("RESULT_NOT_READY");
  });

  it("serves a cached artifact without re-running the generator", async () => {
    writeState("eval-census-v2-trio", {status: "completado"});
    const {materializeReplay, replayArtifactName} = await load();
    const req = {experiment: "eval-census-v2-trio" as const, event_id: "e1",
      group: "continuation", segment: "dev", scale: 1};
    writeFileSync(join(jobDir("eval-census-v2-trio"), replayArtifactName(req)),
      JSON.stringify({replay_id: "PLR-cached"}));
    const r = materializeReplay(req);
    expect(r.ok).toBe(true);
    expect(r.artifact).toMatchObject({replay_id: "PLR-cached"});
  });
});

describe("backtest-control: retention report is bounded to the runs dir", () => {
  it("reports non-existence without touching anything", async () => {
    rmSync(runsDir, {recursive: true, force: true});
    const {retentionReport} = await load();
    const r = retentionReport();
    expect(r.exists).toBe(false);
    expect(r.bytes).toBe(0);
  });
  it("counts bytes/files inside a run directory", async () => {
    writeState("eval-census-v2-trio", {status: "completado"});
    writeFileSync(join(jobDir("eval-census-v2-trio"), "trades.json"), JSON.stringify({trades: []}));
    const {retentionReport} = await load();
    const r = retentionReport();
    expect(r.exists).toBe(true);
    expect(r.files).toBeGreaterThanOrEqual(2);
    expect(r.bytes).toBeGreaterThan(0);
  });
});
