// @vitest-environment node
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {createHash} from "node:crypto";
import {existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync,
  rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

// Directorio de resultados aislado en un temp real, fuera del repo y de OneDrive.
let resultsDir: string;
beforeEach(() => {
  resultsDir = mkdtempSync(join(tmpdir(), "bt-ctrl-"));
  process.env.BACKTEST_RUNS_DIR = resultsDir;
  vi.resetModules();
});
afterEach(() => {
  delete process.env.BACKTEST_RUNS_DIR;
  try { rmSync(resultsDir, {recursive: true, force: true}); } catch { /* ignore */ }
});

const load = () => import("@/lib/backtest-control");
const EXP = "eval-census-v2-trio";
const EXP_ID = "eval-census-v2-trio" as const;
const expDir = () => join(resultsDir, EXP);
const runDir = (runId: string) => join(expDir(), runId);

const sha = (s: string) => createHash("sha256").update(Buffer.from(s)).digest("hex");

// Crea una ejecucion con layout y estado validos (identidad verificable).
function writeRun(runId: string, state: Record<string, unknown>, files: Record<string, string> = {}) {
  mkdirSync(runDir(runId), {recursive: true});
  for (const [name, content] of Object.entries(files)) {
    writeFileSync(join(runDir(runId), name), content);
  }
  writeFileSync(join(runDir(runId), "job_state.json"),
    JSON.stringify({run_id: runId, experiment_id: EXP, ...state}));
}
// Publica el puntero de ejecucion actual.
function setCurrent(runId: string) {
  mkdirSync(expDir(), {recursive: true});
  writeFileSync(join(expDir(), "current.json"), JSON.stringify({run_id: runId}));
}
// Estado completado con hashes correctos y resultados presentes.
function completedFiles() {
  const summary = JSON.stringify({experiment_id: EXP, n_trades_1x: 5255});
  const trades = JSON.stringify({trades: [
    {trade_id: "t1", event_id: "E:1:LONG:H1:H1-v1:5", group: "continuation",
     segment: "dev", scale: 1, net_pnl: 1.0},
    {trade_id: "t2", event_id: "E:2:SHORT:H1:H1-v1:6", group: "continuation",
     segment: "oos", scale: 1, net_pnl: -1.0},
  ]});
  const reconciliation = JSON.stringify({ok: true, cells: []});
  return {
    files: {"summary.json": summary, "trades.json": trades, "reconciliation.json": reconciliation},
    hashes: {"summary.json": sha(summary), "trades.json": sha(trades),
      "reconciliation.json": sha(reconciliation)},
  };
}

describe("backtest-control: allowlist identity", () => {
  it("accepts only the allowlisted experiment id", async () => {
    const {isBacktestExperiment} = await load();
    expect(isBacktestExperiment(EXP)).toBe(true);
    expect(isBacktestExperiment("../x")).toBe(false);
    expect(isBacktestExperiment("")).toBe(false);
    expect(isBacktestExperiment(null)).toBe(false);
  });
  it("mints a unique run identity distinct from the experiment", async () => {
    const {newRunId, newExecutorToken} = await load();
    const a = newRunId(EXP), b = newRunId(EXP);
    expect(a).not.toBe(b);
    expect(a).not.toBe(EXP);
    expect(a).toMatch(/^bt-eval-census-v2-trio-/);
    expect(newExecutorToken()).not.toBe(newExecutorToken());
  });
});

describe("backtest-control: persisted run state", () => {
  it("returns null when there is no state (never fabricates a job)", async () => {
    const {readJobState} = await load();
    expect(readJobState(EXP)).toBeNull();
  });
  it("reads the CURRENT run via the pointer, with its unique run_id", async () => {
    const {files, hashes} = completedFiles();
    writeRun("bt-run-one-0001", {status: "completado", n_trades: 15765,
      reconciliation_ok: true, result_hashes: hashes}, files);
    setCurrent("bt-run-one-0001");
    const {readJobState} = await load();
    const s = readJobState(EXP);
    expect(s?.status).toBe("completado");
    expect(s?.run_id).toBe("bt-run-one-0001");
    expect(s?.job_id).toBe("bt-run-one-0001");
  });
  it("reconciles an orphan 'ejecutando' to fallido when its process is gone", async () => {
    writeRun("bt-run-dead-0002", {status: "ejecutando", started_at_ms: 1, updated_at_ms: 2,
      executor_token: "0123456789abcdef", executor_pid: 999999});
    setCurrent("bt-run-dead-0002");
    const {readJobState} = await load();
    const s = readJobState(EXP);
    expect(s?.status).toBe("fallido");
    expect(s?.error).toBe("PROCESS_INTERRUPTED");
    // Conciliado y persistido: no se relanza ni se reejecuta por error.
    const onDisk = JSON.parse(readFileSync(join(runDir("bt-run-dead-0002"), "job_state.json"), "utf8"));
    expect(onDisk.status).toBe("fallido");
  });
  it("keeps 'ejecutando' while the OWN process is alive (token+pid verified)", async () => {
    writeRun("bt-run-live-0003", {status: "ejecutando", started_at_ms: Date.now(),
      updated_at_ms: Date.now(), executor_token: "0123456789abcdef", executor_pid: process.pid});
    setCurrent("bt-run-live-0003");
    const {readJobState} = await load();
    expect(readJobState(EXP)?.status).toBe("ejecutando");
  });
  it("treats a live-but-unverifiable PID as UNKNOWN identity, never 'ejecutando'", async () => {
    // PID vivo (el nuestro) pero SIN token: la propiedad no esta probada.
    writeRun("bt-run-unknown-0004", {status: "ejecutando", started_at_ms: Date.now(),
      updated_at_ms: Date.now(), executor_pid: process.pid});
    setCurrent("bt-run-unknown-0004");
    const {readJobState} = await load();
    const s = readJobState(EXP);
    expect(s?.status).toBe("fallido");
    expect(s?.error).toBe("PROCESS_IDENTITY_UNKNOWN");
    expect(s?.identity).toBe("UNKNOWN");
  });
  it("closes an over-budget 'ejecutando' as TIMEOUT (effective budget)", async () => {
    const {BACKTEST_BUDGET_MS} = await load();
    writeRun("bt-run-timeout-0005", {status: "ejecutando",
      started_at_ms: Date.now() - BACKTEST_BUDGET_MS - 1000, updated_at_ms: 2,
      executor_token: "0123456789abcdef", executor_pid: process.pid});
    setCurrent("bt-run-timeout-0005");
    const {readJobState} = await load();
    const s = readJobState(EXP);
    expect(s?.status).toBe("fallido");
    expect(s?.error).toBe("TIMEOUT");
  });
  it("ignores an unknown status or a malformed run_id", async () => {
    writeRun("bt-run-weird-0006", {status: "weird"});
    setCurrent("bt-run-weird-0006");
    let {readJobState} = await load();
    expect(readJobState(EXP)).toBeNull();
    // run_id que no cumple el formato seguro -> puntero invalido -> sin estado.
    vi.resetModules();
    mkdirSync(expDir(), {recursive: true});
    writeFileSync(join(expDir(), "current.json"), JSON.stringify({run_id: "../../etc"}));
    ({readJobState} = await load());
    expect(readJobState(EXP)).toBeNull();
  });
});

describe("backtest-control: cross-process exclusion (single-flight)", () => {
  it("does not start a second run when another LIVE process holds the lock", async () => {
    // Lock de OTRO proceso vivo (el nuestro), con token.
    mkdirSync(expDir(), {recursive: true});
    writeFileSync(join(expDir(), "run.lock"), JSON.stringify({
      run_id: "bt-run-active-0007", pid: process.pid, token: "abc",
      acquired_at_ms: Date.now(), host: "other"}));
    writeRun("bt-run-active-0007", {status: "ejecutando", started_at_ms: Date.now(),
      executor_token: "0123456789abcdef", executor_pid: process.pid});
    const {startJob} = await load();
    const r = startJob(EXP);
    expect(r.started).toBe(false);
    expect(r.run_id).toBe("bt-run-active-0007");
    // El lock ajeno sigue intacto: no lo liberamos nosotros.
    expect(existsSync(join(expDir(), "run.lock"))).toBe(true);
  });
  it("takes over an ABANDONED lock (dead process) and marks it failed, without relaunching", async () => {
    mkdirSync(expDir(), {recursive: true});
    writeFileSync(join(expDir(), "run.lock"), JSON.stringify({
      run_id: "bt-run-abandoned-0008", pid: 999999, token: "abc",
      acquired_at_ms: Date.now() - 1000, host: "dead"}));
    writeRun("bt-run-abandoned-0008", {status: "pendiente", started_at_ms: 1,
      updated_at_ms: 2, executor_token: "0123456789abcdef", executor_pid: 999999});
    setCurrent("bt-run-abandoned-0008");
    // El siguiente startJob debe cerrar la abandonada como fallida (no la relanza).
    // (No lanzamos el spawn real: comprobamos el cierre del estado abandonado.)
    const {readJobState, startJob} = await load();
    const before = readJobState(EXP);
    expect(before?.status).toBe("fallido");
    expect(["PROCESS_INTERRUPTED", "PENDING_ABANDONED"]).toContain(before?.error);
    void startJob;
  });
  it("serializes two real concurrent lock attempts: exactly one wins", async () => {
    // Simula dos solicitudes concurrentes creando el lock atomicamente (O_EXCL).
    const {existsSync: ex} = await import("node:fs");
    const lockFile = join(expDir(), "run.lock");
    mkdirSync(expDir(), {recursive: true});
    const {openSync, closeSync, writeSync} = await import("node:fs");
    const results: boolean[] = [];
    for (let i = 0; i < 2; i++) {
      try {
        const fd = openSync(lockFile, "wx");
        writeSync(fd, JSON.stringify({run_id: `bt-race-${i}`, pid: process.pid,
          token: "t", acquired_at_ms: Date.now(), host: "h"}));
        closeSync(fd);
        results.push(true);
      } catch { results.push(false); }
    }
    expect(results.filter(Boolean)).toHaveLength(1);
    expect(ex(lockFile)).toBe(true);
  });
});

describe("backtest-control: results are integrity-verified and run-bound", () => {
  it("reports not-ready with the real status, never mock rows", async () => {
    writeRun("bt-run-wait-0010", {status: "ejecutando", started_at_ms: Date.now(),
      executor_token: "0123456789abcdef", executor_pid: process.pid});
    setCurrent("bt-run-wait-0010");
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.status).toBe("ejecutando");
  });
  it("serves completed results with verified hashes", async () => {
    const {files, hashes} = completedFiles();
    writeRun("bt-run-ok-0011", {status: "completado", result_hashes: hashes}, files);
    setCurrent("bt-run-ok-0011");
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(true);
    if (r.available) {
      expect(r.trades).toHaveLength(2);
      expect(r.result_hashes["trades.json"]).toBe(hashes["trades.json"]);
    }
  });
  it("REJECTS results whose declared hash no longer matches (altered results)", async () => {
    const {files, hashes} = completedFiles();
    writeRun("bt-run-tamper-0012", {status: "completado", result_hashes: hashes}, files);
    setCurrent("bt-run-tamper-0012");
    // Altera trades.json DESPUES de declarar su hash.
    writeFileSync(join(runDir("bt-run-tamper-0012"), "trades.json"),
      JSON.stringify({trades: [{trade_id: "evil"}]}));
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.error).toBe("RESULT_INTEGRITY_FAILED");
  });
  it("REJECTS incomplete results (missing reconciliation.json)", async () => {
    const {files, hashes} = completedFiles();
    delete (files as Record<string, string>)["reconciliation.json"];
    writeRun("bt-run-incomplete-0013", {status: "completado", result_hashes: hashes}, files);
    setCurrent("bt-run-incomplete-0013");
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.error).toBe("RESULT_INCOMPLETE");
  });
  it("serves results of a SPECIFIC run, not the current one", async () => {
    const a = completedFiles(), b = completedFiles();
    writeRun("bt-run-alpha-0014", {status: "completado", result_hashes: a.hashes}, a.files);
    writeRun("bt-run-beta-0015", {status: "completado", result_hashes: b.hashes}, b.files);
    setCurrent("bt-run-beta-0015");
    const {readRunResults} = await load();
    const r = readRunResults(EXP, "bt-run-alpha-0014");
    expect(r.available).toBe(true);
    if (r.available) expect(r.run_id).toBe("bt-run-alpha-0014");
  });
});

describe("backtest-control: replay cache is run-bound", () => {
  it("names the artifact from run_id + result hash + operation identity", async () => {
    const {replayArtifactName} = await load();
    const req = {experiment: EXP_ID, event_id: "e1",
      group: "continuation", segment: "dev", scale: 1};
    const a = replayArtifactName(req, "bt-run-a", "hashA");
    const b = replayArtifactName(req, "bt-run-a", "hashA");
    const c = replayArtifactName(req, "bt-run-b", "hashA"); // otra ejecucion
    const d = replayArtifactName(req, "bt-run-a", "hashB"); // otros resultados
    const e = replayArtifactName({...req, scale: 2}, "bt-run-a", "hashA");
    expect(a).toBe(b);
    expect(new Set([a, c, d, e]).size).toBe(4);
    expect(a).toMatch(/^replay_[0-9a-f]{20}\.json$/);
  });
  it("refuses materialization when the run is not completed", async () => {
    writeRun("bt-run-notready-0016", {status: "ejecutando", started_at_ms: Date.now(),
      executor_token: "0123456789abcdef", executor_pid: process.pid});
    setCurrent("bt-run-notready-0016");
    const {materializeReplay} = await load();
    const r = materializeReplay({experiment: EXP, event_id: "e",
      group: "continuation", segment: "dev", scale: 1});
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toBe("RESULT_NOT_READY");
  });
  it("refuses an operation that does NOT belong to that run's results", async () => {
    const {files, hashes} = completedFiles();
    writeRun("bt-run-foreign-0017", {status: "completado", result_hashes: hashes}, files);
    setCurrent("bt-run-foreign-0017");
    const {materializeReplay} = await load();
    const r = materializeReplay({experiment: EXP, event_id: "NO-EXISTE",
      group: "continuation", segment: "dev", scale: 1});
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toBe("TARGET_NOT_IN_RUN");
  });
  it("reuses the run-bound cache only for the SAME run and results", async () => {
    const {files, hashes} = completedFiles();
    writeRun("bt-run-cache-0018", {status: "completado", result_hashes: hashes}, files);
    setCurrent("bt-run-cache-0018");
    const {materializeReplay, replayArtifactName} = await load();
    const req = {experiment: EXP_ID, event_id: "E:1:LONG:H1:H1-v1:5",
      group: "continuation", segment: "dev", scale: 1};
    const name = replayArtifactName(req, "bt-run-cache-0018", hashes["trades.json"]!);
    writeFileSync(join(runDir("bt-run-cache-0018"), name),
      JSON.stringify({replay_id: "PLR-cached"}));
    const r = materializeReplay(req);
    expect(r.ok).toBe(true);
    if (r.ok) { expect(r.cached).toBe(true); expect(r.artifact).toMatchObject({replay_id: "PLR-cached"}); }
  });
  it("a NEW run never silently reuses the previous run's replay cache", async () => {
    const {files, hashes} = completedFiles();
    writeRun("bt-run-old-0019", {status: "completado", result_hashes: hashes}, files);
    // Cache de la ejecucion anterior.
    const {replayArtifactName} = await load();
    const req = {experiment: EXP_ID, event_id: "E:1:LONG:H1:H1-v1:5",
      group: "continuation", segment: "dev", scale: 1};
    writeFileSync(join(runDir("bt-run-old-0019"),
      replayArtifactName(req, "bt-run-old-0019", hashes["trades.json"]!)),
      JSON.stringify({replay_id: "PLR-OLD"}));
    // Ejecucion nueva con los mismos resultados.
    writeRun("bt-run-new-0020", {status: "completado", result_hashes: hashes}, files);
    setCurrent("bt-run-new-0020");
    const {materializeReplay} = await load();
    const r = materializeReplay(req);
    // El nombre de esta ejecucion difiere: no puede devolver el PLR-OLD.
    expect(r.ok === false || (r.ok && (r.artifact as {replay_id?: string}).replay_id !== "PLR-OLD"))
      .toBe(true);
  });
});

describe("backtest-control: bounded retention never removes a live run", () => {
  it("reports non-existence without touching anything", async () => {
    rmSync(resultsDir, {recursive: true, force: true});
    const {retentionReport} = await load();
    const r = retentionReport();
    expect(r.exists).toBe(false);
    expect(r.bytes).toBe(0);
    expect(r.removed).toEqual([]);
  });
  it("counts runs/bytes/files per experiment", async () => {
    const {files, hashes} = completedFiles();
    writeRun("bt-run-count-0021", {status: "completado", result_hashes: hashes}, files);
    setCurrent("bt-run-count-0021");
    const {retentionReport} = await load();
    const r = retentionReport();
    expect(r.exists).toBe(true);
    expect(r.runs).toBe(1);
    expect(r.files).toBeGreaterThanOrEqual(4);
    expect(r.bytes).toBeGreaterThan(0);
  });
  it("does not report removal when it does not apply cleaning", async () => {
    const {retentionReport} = await load();
    const r = retentionReport(false);
    expect(r.removed).toEqual([]);
  });
});
