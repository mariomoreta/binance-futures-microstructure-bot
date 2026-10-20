// @vitest-environment node
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {createHash} from "node:crypto";
import {spawn, type ChildProcess} from "node:child_process";
import {existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync,
  rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

// Directorio de resultados aislado en un temp real, fuera del repo y de OneDrive.
let resultsDir: string;
let fakeRoot: string;
const spawnedChildren: ChildProcess[] = [];
const startedRunPids = new Set<number>();

beforeEach(() => {
  resultsDir = mkdtempSync(join(tmpdir(), "bt-ctrl-"));
  fakeRoot = mkdtempSync(join(tmpdir(), "bt-root-"));
  mkdirSync(join(fakeRoot, "scripts"), {recursive: true});
  writeFileSync(join(fakeRoot, "scripts", "run_dashboard_backtest.py"), FAKE_EXECUTOR);
  process.env.BACKTEST_RUNS_DIR = resultsDir;
  process.env.BACKTEST_ROOT = fakeRoot;
  process.env.FAKE_EXECUTOR_SLEEP = "0.2";
  vi.resetModules();
});
afterEach(() => {
  delete process.env.BACKTEST_RUNS_DIR;
  delete process.env.BACKTEST_ROOT;
  delete process.env.FAKE_EXECUTOR_SLEEP;
  for (const child of spawnedChildren.splice(0)) {
    try { child.kill(); } catch { /* ignore */ }
  }
  for (const pid of startedRunPids) {
    try { process.kill(pid); } catch { /* ya termino */ }
  }
  startedRunPids.clear();
  try { rmSync(resultsDir, {recursive: true, force: true}); } catch { /* ignore */ }
  try { rmSync(fakeRoot, {recursive: true, force: true}); } catch { /* ignore */ }
});

// Ejecutor FALSO para las pruebas de ciclo de vida: mismo contrato de argv y
// de estado que el real, sin ejecutar el motor. Permite probar adquisicion,
// liberacion y recuperacion de forma determinista y rapida.
const FAKE_EXECUTOR = String.raw`
import argparse, hashlib, json, os, sys, time
ap = argparse.ArgumentParser()
ap.add_argument("--experiment"); ap.add_argument("--out-dir")
ap.add_argument("--run-id"); ap.add_argument("--executor-token")
ap.add_argument("--budget-ms"); ap.add_argument("--context-candles")
args, _ = ap.parse_known_args()
out = args.out_dir
os.makedirs(out, exist_ok=True)
EVENT = "BTCUSDT:1:LONG:H1:H1-v1:1"
def write(status, **extra):
    p = {"job_id": args.run_id, "run_id": args.run_id,
         "experiment_id": args.experiment, "status": status,
         "executor_token": args.executor_token, "executor_pid": os.getpid(),
         "started_at_ms": int(time.time()*1000),
         "updated_at_ms": int(time.time()*1000), "identity": "declared"}
    p.update(extra)
    tmp = os.path.join(out, "job_state.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f)
    os.replace(tmp, os.path.join(out, "job_state.json"))
write("ejecutando")
time.sleep(float(os.environ.get("FAKE_EXECUTOR_SLEEP", "0.2")))
if os.environ.get("FAKE_EXECUTOR_FAIL") == "1":
    write("fallido", error="EXECUTION_FAILED", detail="fixture")
    sys.exit(4)
summary = {"experiment_id": args.experiment, "run_id": args.run_id,
           "cells": [], "n_trades_total": 1, "reconciliation_ok": True}
trades = {"experiment_id": args.experiment, "run_id": args.run_id, "n_trades": 1,
          "trades": [{"trade_id": "t1", "event_id": EVENT, "group": "continuation",
                      "segment": "dev", "scale": 1, "entry_ms": 10, "exit_ms": 20,
                      "net_pnl": 1.0, "fees": 0.1, "funding": 0.0,
                      "exit_executed": True, "open_at_end": False}]}
recon = {"experiment_id": args.experiment, "run_id": args.run_id, "ok": True, "cells": []}
for name, doc in (("summary.json", summary), ("trades.json", trades),
                  ("reconciliation.json", recon)):
    with open(os.path.join(out, name), "w", encoding="utf-8") as f:
        json.dump(doc, f)
hashes = {}
for name in ("summary.json", "trades.json", "reconciliation.json"):
    with open(os.path.join(out, name), "rb") as f:
        hashes[name] = hashlib.sha256(f.read()).hexdigest()
write("completado", n_trades=1, reconciliation_ok=True, result_hashes=hashes)
`;

const load = () => import("@/lib/backtest-control");
const EXP = "eval-census-v2-trio";
const EXP_ID = "eval-census-v2-trio" as const;
const expDir = () => join(resultsDir, EXP);
const runDir = (runId: string) => join(expDir(), runId);

const sha = (s: string) => createHash("sha256").update(Buffer.from(s)).digest("hex");

// Crea una ejecucion con layout y estado validos.
function writeRun(runId: string, state: Record<string, unknown>, files: Record<string, string> = {}) {
  mkdirSync(runDir(runId), {recursive: true});
  for (const [name, content] of Object.entries(files)) {
    writeFileSync(join(runDir(runId), name), content);
  }
  writeFileSync(join(runDir(runId), "job_state.json"),
    JSON.stringify({run_id: runId, experiment_id: EXP, ...state}));
}
function setCurrent(runId: string) {
  mkdirSync(expDir(), {recursive: true});
  writeFileSync(join(expDir(), "current.json"), JSON.stringify({run_id: runId}));
}

// Artefactos COMPLETOS y con identidad de ejecucion (esquema exigido).
function completedFiles(runId: string, over: {
  summary?: Record<string, unknown>; trades?: Record<string, unknown>[];
  reconciliation?: Record<string, unknown>;
} = {}) {
  const tradeRows = over.trades ?? [
    {trade_id: "t1", event_id: "E:1:LONG:H1:H1-v1:5", group: "continuation",
     segment: "dev", scale: 1, net_pnl: 1.0, entry_ms: 10, exit_ms: 20,
     fees: 0.1, funding: 0.0},
    {trade_id: "t2", event_id: "E:2:SHORT:H1:H1-v1:6", group: "continuation",
     segment: "oos", scale: 1, net_pnl: -1.0, entry_ms: 30, exit_ms: 40,
     fees: 0.1, funding: 0.0},
  ];
  const summary = JSON.stringify({
    experiment_id: EXP, run_id: runId, cells: [], n_trades_total: tradeRows.length,
    reconciliation_ok: true, ...over.summary});
  const trades = JSON.stringify({
    experiment_id: EXP, run_id: runId, n_trades: tradeRows.length, trades: tradeRows,
    ...over.trades ? {} : {}});
  const reconciliation = JSON.stringify({
    experiment_id: EXP, run_id: runId, ok: true, cells: [], ...over.reconciliation});
  return {
    files: {"summary.json": summary, "trades.json": trades, "reconciliation.json": reconciliation},
    hashes: {"summary.json": sha(summary), "trades.json": sha(trades),
      "reconciliation.json": sha(reconciliation)},
  };
}

// Hijo real (node) con la identidad de ejecucion en su linea de comandos.
function spawnOwnedExecutor(runId: string, token: string, sleepMs = 60_000): ChildProcess {
  const child = spawn(process.execPath, ["-e", `setTimeout(()=>{},${sleepMs})`, "--",
    "--run-id", runId, "--executor-token", token], {stdio: "ignore", windowsHide: true});
  spawnedChildren.push(child);
  return child;
}

async function waitFor<T>(fn: () => T | null | undefined, timeoutMs = 20_000, step = 100): Promise<T> {
  const end = Date.now() + timeoutMs;
  for (;;) {
    const value = fn();
    if (value) return value;
    if (Date.now() > end) throw new Error("timeout esperando condicion");
    await new Promise((r) => setTimeout(r, step));
  }
}

async function waitPidGone(pid: number, timeoutMs = 20_000): Promise<void> {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try { process.kill(pid, 0); } catch { return; }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`el PID ${pid} sigue vivo`);
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
    expect(a).toMatch(/^[a-z0-9-]{8,64}$/);
    expect(newExecutorToken()).not.toBe(newExecutorToken());
  });
});

describe("backtest-control: persisted run state", () => {
  it("returns null when there is no state (never fabricates a job)", async () => {
    const {readJobState} = await load();
    expect(readJobState(EXP)).toBeNull();
  });
  it("reads the CURRENT run via the pointer, with its unique run_id", async () => {
    const {files, hashes} = completedFiles("bt-run-one-0001");
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
    const onDisk = JSON.parse(readFileSync(join(runDir("bt-run-dead-0002"), "job_state.json"), "utf8"));
    expect(onDisk.status).toBe("fallido");
  });
  it("keeps 'ejecutando' only with REAL process evidence (own executor alive)", async () => {
    const runId = "bt-run-live-0003";
    const token = "0123456789abcdef0123456789abcdef";
    const child = spawnOwnedExecutor(runId, token);
    const started = Date.now() - 1000;
    writeRun(runId, {status: "ejecutando", started_at_ms: started,
      updated_at_ms: started, executor_token: token, executor_pid: child.pid});
    writeFileSync(join(runDir(runId), "job_pid.json"),
      JSON.stringify({pid: child.pid, run_id: runId, token, started_at_ms: started}));
    setCurrent(runId);
    const {readJobState} = await load();
    const s = readJobState(EXP);
    expect(s?.status).toBe("ejecutando");
    expect(s?.identity).toBe("verified");
  });
  it("REJECTS a foreign live PID with a format-valid token and identity:'verified'", async () => {
    // Reproduccion del defecto: PID de Node ajeno + token valido + etiqueta
    // guardada "verified". Sin evidencia del proceso NO es ejecutando.
    const runId = "bt-run-unknown-0004";
    writeRun(runId, {status: "ejecutando", started_at_ms: Date.now(),
      updated_at_ms: Date.now(), executor_token: "0123456789abcdef0123456789abcdef",
      executor_pid: process.pid, identity: "verified"});
    setCurrent(runId);
    const {readJobState} = await load();
    const s = readJobState(EXP);
    expect(s?.status).toBe("fallido");
    expect(s?.error).toBe("PROCESS_IDENTITY_UNKNOWN");
    expect(s?.identity).toBe("UNKNOWN");
    const onDisk = JSON.parse(readFileSync(join(runDir(runId), "job_state.json"), "utf8"));
    expect(onDisk.identity).not.toBe("verified");
  });
  it("REJECTS a recycled PID instance (creation far from run start)", async () => {
    const runId = "bt-run-recycled-0005";
    writeRun(runId, {status: "ejecutando",
      started_at_ms: Date.now() + 3_600_000, updated_at_ms: Date.now(),
      executor_token: "0123456789abcdef0123456789abcdef", executor_pid: process.pid});
    setCurrent(runId);
    const {readJobState} = await load();
    const s = readJobState(EXP);
    expect(s?.status).toBe("fallido");
    expect(s?.error).toBe("PROCESS_IDENTITY_UNKNOWN");
  });
  it("REJECTS an executor whose live process does NOT own the token", async () => {
    const runId = "bt-run-wrong-token-0006";
    const child = spawnOwnedExecutor(runId, "ffffffffffffffffffffffffffffffff");
    const started = Date.now() - 1000;
    writeRun(runId, {status: "ejecutando", started_at_ms: started, updated_at_ms: started,
      executor_token: "0123456789abcdef0123456789abcdef", executor_pid: child.pid});
    setCurrent(runId);
    const {readJobState} = await load();
    const s = readJobState(EXP);
    expect(s?.status).toBe("fallido");
    expect(s?.error).toBe("PROCESS_IDENTITY_UNKNOWN");
  });
  it("REJECTS incomplete identity (no started_at evidence)", async () => {
    const runId = "bt-run-incomplete-0007";
    const token = "0123456789abcdef0123456789abcdef";
    const child = spawnOwnedExecutor(runId, token);
    writeRun(runId, {status: "ejecutando", executor_token: token, executor_pid: child.pid});
    setCurrent(runId);
    const {readJobState} = await load();
    const s = readJobState(EXP);
    expect(s?.status).toBe("fallido");
    expect(s?.error).toBe("PROCESS_IDENTITY_UNKNOWN");
  });
  it("closes an over-budget 'ejecutando' as TIMEOUT without killing the verified process", async () => {
    const runId = "bt-run-timeout-0008";
    const token = "0123456789abcdef0123456789abcdef";
    const child = spawnOwnedExecutor(runId, token);
    const {BACKTEST_BUDGET_MS} = await load();
    const started = Date.now() - BACKTEST_BUDGET_MS - 1000;
    writeRun(runId, {status: "ejecutando", started_at_ms: started, updated_at_ms: started,
      executor_token: token, executor_pid: child.pid});
    setCurrent(runId);
    const {readJobState} = await load();
    const s = readJobState(EXP);
    expect(s?.status).toBe("fallido");
    expect(s?.error).toBe("TIMEOUT");
    // El proceso sigue vivo: no se ha matado ni se declara terminado.
    expect(() => process.kill(child.pid!, 0)).not.toThrow();
  });
  it("ignores an unknown status or a malformed run_id", async () => {
    writeRun("bt-run-weird-0009", {status: "weird"});
    setCurrent("bt-run-weird-0009");
    let {readJobState} = await load();
    expect(readJobState(EXP)).toBeNull();
    vi.resetModules();
    mkdirSync(expDir(), {recursive: true});
    writeFileSync(join(expDir(), "current.json"), JSON.stringify({run_id: "../../etc"}));
    ({readJobState} = await load());
    expect(readJobState(EXP)).toBeNull();
  });
});

describe("backtest-control: lock represents the run lifecycle (single-flight)", () => {
  it("two CONSECUTIVE real offline executions complete and the second is not blocked", async () => {
    const mod = await load();
    const first = mod.startJob(EXP);
    expect(first.started).toBe(true);
    expect(first.run_id).toBeTruthy();
    if (first.run_id && first.state?.executor_pid) startedRunPids.add(first.state.executor_pid);
    const done1 = await waitFor(() => {
      const s = mod.readRunState(EXP, first.run_id!);
      return s?.status === "completado" ? s : null;
    });
    expect(done1.n_trades).toBe(1);
    // El lock sigue existiendo tras completar, pero NO bloquea una nueva
    // solicitud explicita: su ejecutor ya no existe.
    expect(existsSync(join(expDir(), "run.lock"))).toBe(true);
    if (done1.executor_pid) await waitPidGone(done1.executor_pid);

    const second = mod.startJob(EXP);
    expect(second.started).toBe(true);
    expect(second.run_id).not.toBe(first.run_id);
    if (second.run_id && second.state?.executor_pid) startedRunPids.add(second.state.executor_pid);
    const done2 = await waitFor(() => {
      const s = mod.readRunState(EXP, second.run_id!);
      return s?.status === "completado" ? s : null;
    });
    expect(done2.run_id).toBe(second.run_id);
    // Resultados servidos SOLO con hashes declarados y verificados.
    const results = mod.readRunResults(EXP, second.run_id!);
    expect(results.available).toBe(true);
    if (results.available) expect(results.run_id).toBe(second.run_id);
  }, 120_000);
  it("serializes an explicit double request: exactly one executor", async () => {
    const mod = await load();
    process.env.FAKE_EXECUTOR_SLEEP = "1.5";
    const a = mod.startJob(EXP);
    const b = mod.startJob(EXP);
    expect([a.started, b.started].filter(Boolean)).toHaveLength(1);
    const winner = a.started ? a : b;
    expect(winner.run_id).toBeTruthy();
    if (winner.state?.executor_pid) startedRunPids.add(winner.state.executor_pid);
    const done = await waitFor(() => {
      const s = mod.readRunState(EXP, winner.run_id!);
      return s?.status === "completado" ? s : null;
    });
    if (done.executor_pid) await waitPidGone(done.executor_pid);
  }, 120_000);
  it("BFF interruption: preserves exclusion while the executor lives and recovers after it exits", async () => {
    const mod = await load();
    process.env.FAKE_EXECUTOR_SLEEP = "30";
    const first = mod.startJob(EXP);
    expect(first.started).toBe(true);
    const pid = first.state?.executor_pid;
    expect(pid).toBeTruthy();
    startedRunPids.add(pid!);
    // Simula la caida del BFF: el lock queda con un PID dueno muerto.
    const lockPath = join(expDir(), "run.lock");
    writeFileSync(lockPath, JSON.stringify({run_id: first.run_id, pid: 999999,
      token: first.state?.executor_token, acquired_at_ms: Date.now(), host: "bff"}));
    // El ejecutor sigue vivo -> NO se lanza otro.
    const blocked = mod.startJob(EXP);
    expect(blocked.started).toBe(false);
    expect(blocked.run_id).toBe(first.run_id);
    expect(existsSync(lockPath)).toBe(true);
    // Cierre del ejecutor (interrupcion): ahora si hay recuperacion explicita.
    process.kill(pid!);
    await waitPidGone(pid!);
    process.env.FAKE_EXECUTOR_SLEEP = "0.2";
    const recovered = mod.startJob(EXP);
    expect(recovered.started).toBe(true);
    expect(recovered.run_id).not.toBe(first.run_id);
    if (recovered.state?.executor_pid) startedRunPids.add(recovered.state.executor_pid);
    const done = await waitFor(() => {
      const s = mod.readRunState(EXP, recovered.run_id!);
      return s?.status === "completado" ? s : null;
    });
    if (done.executor_pid) await waitPidGone(done.executor_pid);
  }, 120_000);
  it("a late callback of run A never releases nor modifies the lock of run B", async () => {
    const mod = await load();
    mkdirSync(expDir(), {recursive: true});
    const lockB = {run_id: "bt-run-b-0042", pid: process.pid,
      token: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", acquired_at_ms: Date.now(), host: "bff"};
    writeFileSync(join(expDir(), "run.lock"), JSON.stringify(lockB));
    const released = mod.releaseLockFor(EXP, "bt-run-a-0041", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    expect(released).toBe(false);
    expect(JSON.parse(readFileSync(join(expDir(), "run.lock"), "utf8"))).toMatchObject(lockB);
    // Con el token correcto pero otro run_id tampoco se libera.
    expect(mod.releaseLockFor(EXP, "bt-run-a-0041", lockB.token)).toBe(false);
    expect(existsSync(join(expDir(), "run.lock"))).toBe(true);
  });
  it("TIMEOUT with a still-live executor does NOT allow a duplicate", async () => {
    const mod = await load();
    const runId = "bt-run-timeout-lock-0043";
    const token = "0123456789abcdef0123456789abcdef";
    const child = spawnOwnedExecutor(runId, token, 120_000);
    const {BACKTEST_BUDGET_MS} = await load();
    const old = Date.now() - BACKTEST_BUDGET_MS - 5000;
    writeRun(runId, {status: "ejecutando", started_at_ms: old, updated_at_ms: old,
      executor_token: token, executor_pid: child.pid});
    writeFileSync(join(runDir(runId), "job_pid.json"),
      JSON.stringify({pid: child.pid, run_id: runId, token, started_at_ms: old}));
    writeFileSync(join(expDir(), "run.lock"), JSON.stringify({run_id: runId,
      pid: 999999, token, acquired_at_ms: old, host: "bff"}));
    setCurrent(runId);
    expect(mod.readJobState(EXP)?.error).toBe("TIMEOUT");
    const r = mod.startJob(EXP);
    expect(r.started).toBe(false);
    expect(r.run_id).toBe(runId);
    expect(existsSync(join(expDir(), "run.lock"))).toBe(true);
  });
});

describe("backtest-control: results require declared, complete and coherent hashes", () => {
  it("refuses a completed state WITHOUT declared hashes", async () => {
    const {files} = completedFiles("bt-run-nohash-0010");
    writeRun("bt-run-nohash-0010", {status: "completado"}, files);
    setCurrent("bt-run-nohash-0010");
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.error).toBe("RESULT_HASHES_MISSING");
  });
  it("refuses PARTIAL declared hashes", async () => {
    const {files, hashes} = completedFiles("bt-run-partial-0011");
    const partial = {trades: hashes["trades.json"]};
    writeRun("bt-run-partial-0011", {status: "completado",
      result_hashes: partial as unknown as Record<string, string>}, files);
    setCurrent("bt-run-partial-0011");
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.error).toBe("RESULT_HASHES_INCOMPLETE");
  });
  it("refuses an invalid hash format", async () => {
    const {files, hashes} = completedFiles("bt-run-badhash-0012");
    const bad = {...hashes, "summary.json": "not-a-sha256"};
    writeRun("bt-run-badhash-0012", {status: "completado", result_hashes: bad}, files);
    setCurrent("bt-run-badhash-0012");
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.error).toBe("RESULT_HASHES_INVALID");
  });
  it("serves results ONLY with complete declared hashes that match the bytes", async () => {
    const {files, hashes} = completedFiles("bt-run-ok-0013");
    writeRun("bt-run-ok-0013", {status: "completado", result_hashes: hashes}, files);
    setCurrent("bt-run-ok-0013");
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(true);
    if (r.available) {
      expect(r.trades).toHaveLength(2);
      expect(r.result_hashes).toEqual(hashes);
    }
  });
  for (const target of ["summary.json", "trades.json", "reconciliation.json"] as const) {
    it(`refuses an ALTERED ${target} (never recomputes it as declared)`, async () => {
      const runId = `bt-run-tamper-${target.replace(/\W/g, "")}`;
      const {files, hashes} = completedFiles(runId);
      writeRun(runId, {status: "completado", result_hashes: hashes}, files);
      setCurrent(runId);
      const original = JSON.parse(files[target]);
      writeFileSync(join(runDir(runId), target), JSON.stringify({...original, injected: 1}));
      const {readResults} = await load();
      const r = readResults(EXP);
      expect(r.available).toBe(false);
      if (!r.available) expect(r.error).toBe("RESULT_INTEGRITY_FAILED");
    });
  }
  it("refuses unparseable reconciliation.json even if its hash matches", async () => {
    const runId = "bt-run-badjson-0014";
    const {files} = completedFiles(runId);
    const broken = "{not json";
    files["reconciliation.json"] = broken;
    const hashes = {
      "summary.json": sha(files["summary.json"]), "trades.json": sha(files["trades.json"]),
      "reconciliation.json": sha(broken),
    };
    writeRun(runId, {status: "completado", result_hashes: hashes}, files);
    setCurrent(runId);
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.error).toBe("RESULT_INVALID_JSON");
  });
  it("refuses a reconciliation with invalid shape (ok/cells)", async () => {
    const runId = "bt-run-reconshape-0015";
    const {files, hashes} = completedFiles(runId, {reconciliation: {ok: "yes", cells: "no"}});
    writeRun(runId, {status: "completado", result_hashes: hashes}, files);
    setCurrent(runId);
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.error).toBe("RESULT_SCHEMA_INVALID");
  });
  it("refuses a reconciliation that is not OK (result not integral)", async () => {
    const runId = "bt-run-reconfail-0016";
    const {files, hashes} = completedFiles(runId, {reconciliation: {ok: false}});
    writeRun(runId, {status: "completado", result_hashes: hashes}, files);
    setCurrent(runId);
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.error).toBe("RESULT_RECONCILIATION_FAILED");
  });
  it("refuses artifacts from ANOTHER run or experiment", async () => {
    const runId = "bt-run-identity-0017";
    const other = completedFiles("bt-run-other-9999");
    writeRun(runId, {status: "completado", result_hashes: other.hashes}, other.files);
    setCurrent(runId);
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.error).toBe("RESULT_IDENTITY_MISMATCH");
  });
  it("refuses artifacts that do not declare run identity at all", async () => {
    const runId = "bt-run-noid-0018";
    const base = completedFiles(runId);
    const trades = JSON.stringify({experiment_id: EXP, n_trades: 2, trades: []});
    const files = {...base.files, "trades.json": trades};
    const hashes = {...base.hashes, "trades.json": sha(trades)};
    writeRun(runId, {status: "completado", result_hashes: hashes}, files);
    setCurrent(runId);
    const {readResults} = await load();
    const r = readResults(EXP);
    expect(r.available).toBe(false);
    if (!r.available) expect(r.error).toBe("RESULT_IDENTITY_MISSING");
  });
  it("serves results of a SPECIFIC run, not the current one", async () => {
    const a = completedFiles("bt-run-alpha-0019");
    const b = completedFiles("bt-run-beta-0020");
    writeRun("bt-run-alpha-0019", {status: "completado", result_hashes: a.hashes}, a.files);
    writeRun("bt-run-beta-0020", {status: "completado", result_hashes: b.hashes}, b.files);
    setCurrent("bt-run-beta-0020");
    const {readRunResults} = await load();
    const r = readRunResults(EXP, "bt-run-alpha-0019");
    expect(r.available).toBe(true);
    if (r.available) expect(r.run_id).toBe("bt-run-alpha-0019");
  });
});

function boundReplay(req: {event_id: string; group: string; segment: string; scale: number},
                     runId: string, tradesHash: string, over: Record<string, unknown> = {}) {
  return {
    schema_version: 1, artifact_version: "PAPER-LAB-REPLAY-V1",
    replay_id: `PLR-BTCUSDT-LONG-1788903900000-continuation-${req.scale.toFixed(1)}x`,
    backtest_run_id: runId,
    event: {event_id: req.event_id},
    trade: {group: req.group, segment: req.segment, entry_ms: 10, exit_ms: 20,
      net_pnl: 1.0, fees: 0.1, funding: 0.0},
    provenance: {source_hashes: {"generated-traces/trades.json": tradesHash}},
    ...over,
  };
}

describe("backtest-control: replay cache is run-bound and result-bound", () => {
  it("names the artifact from run_id + result hash + operation identity", async () => {
    const {replayArtifactName} = await load();
    const req = {experiment: EXP_ID, event_id: "e1",
      group: "continuation", segment: "dev", scale: 1};
    const a = replayArtifactName(req, "bt-run-a", "hashA");
    const b = replayArtifactName(req, "bt-run-a", "hashA");
    const c = replayArtifactName(req, "bt-run-b", "hashA");
    const d = replayArtifactName(req, "bt-run-a", "hashB");
    const e = replayArtifactName({...req, scale: 2}, "bt-run-a", "hashA");
    expect(a).toBe(b);
    expect(new Set([a, c, d, e]).size).toBe(4);
    expect(a).toMatch(/^replay_[0-9a-f]{20}\.json$/);
  });
  it("refuses materialization when the run is not completed", async () => {
    writeRun("bt-run-notready-0021", {status: "pendiente",
      started_at_ms: Date.now(), updated_at_ms: Date.now()});
    setCurrent("bt-run-notready-0021");
    const {materializeReplay} = await load();
    const r = materializeReplay({experiment: EXP, event_id: "e",
      group: "continuation", segment: "dev", scale: 1});
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toBe("RESULT_NOT_READY");
  });
  it("refuses an operation that does NOT belong to that run's results", async () => {
    const {files, hashes} = completedFiles("bt-run-foreign-0022");
    writeRun("bt-run-foreign-0022", {status: "completado", result_hashes: hashes}, files);
    setCurrent("bt-run-foreign-0022");
    const {materializeReplay} = await load();
    const r = materializeReplay({experiment: EXP, event_id: "NO-EXISTE",
      group: "continuation", segment: "dev", scale: 1});
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toBe("TARGET_NOT_IN_RUN");
  });
  it("reuses the cache ONLY when it is bound to this run and these results", async () => {
    const runId = "bt-run-cache-0023";
    const {files, hashes} = completedFiles(runId);
    writeRun(runId, {status: "completado", result_hashes: hashes}, files);
    setCurrent(runId);
    const {materializeReplay, replayArtifactName} = await load();
    const req = {experiment: EXP_ID, event_id: "E:1:LONG:H1:H1-v1:5",
      group: "continuation", segment: "dev", scale: 1};
    const name = replayArtifactName(req, runId, hashes["trades.json"]!);
    writeFileSync(join(runDir(runId), name),
      JSON.stringify(boundReplay(req, runId, hashes["trades.json"]!)));
    const r = materializeReplay(req);
    expect(r.ok).toBe(true);
    if (r.ok) { expect(r.cached).toBe(true); expect(r.run_id).toBe(runId); }
  });
  it("does NOT serve a cache file that belongs to another run (unverified cache)", async () => {
    const runId = "bt-run-cachebad-0024";
    const {files, hashes} = completedFiles(runId);
    writeRun(runId, {status: "completado", result_hashes: hashes}, files);
    setCurrent(runId);
    const {materializeReplay, replayArtifactName} = await load();
    const req = {experiment: EXP_ID, event_id: "E:1:LONG:H1:H1-v1:5",
      group: "continuation", segment: "dev", scale: 1};
    const name = replayArtifactName(req, runId, hashes["trades.json"]!);
    writeFileSync(join(runDir(runId), name),
      JSON.stringify(boundReplay(req, "bt-run-OTHER", hashes["trades.json"]!)));
    const r = materializeReplay(req);
    expect(!r.ok || (r.artifact as {replay_id?: string; backtest_run_id?: string})
      .backtest_run_id !== "bt-run-OTHER").toBe(true);
  });
  it("a NEW run never silently reuses the previous run's replay cache", async () => {
    const oldRun = "bt-run-old-0025", newRun = "bt-run-new-0026";
    const {files, hashes} = completedFiles(oldRun);
    writeRun(oldRun, {status: "completado", result_hashes: hashes}, files);
    const {replayArtifactName} = await load();
    const req = {experiment: EXP_ID, event_id: "E:1:LONG:H1:H1-v1:5",
      group: "continuation", segment: "dev", scale: 1};
    writeFileSync(join(runDir(oldRun), replayArtifactName(req, oldRun, hashes["trades.json"]!)),
      JSON.stringify(boundReplay(req, oldRun, hashes["trades.json"]!)));
    const fresh = completedFiles(newRun);
    writeRun(newRun, {status: "completado", result_hashes: fresh.hashes}, fresh.files);
    setCurrent(newRun);
    const {materializeReplay} = await load();
    const r = materializeReplay(req);
    expect(r.ok === false
      || (r.ok && (r.artifact as {backtest_run_id?: string}).backtest_run_id !== oldRun)).toBe(true);
  });
});

describe("backtest-control: retention never removes a possibly-active run", () => {
  it("reports non-existence without touching anything", async () => {
    rmSync(resultsDir, {recursive: true, force: true});
    const {retentionReport} = await load();
    const r = retentionReport();
    expect(r.exists).toBe(false);
    expect(r.bytes).toBe(0);
    expect(r.removed).toEqual([]);
  });
  it("counts runs/bytes/files per experiment", async () => {
    const {files, hashes} = completedFiles("bt-run-count-0027");
    writeRun("bt-run-count-0027", {status: "completado", result_hashes: hashes}, files);
    setCurrent("bt-run-count-0027");
    const {retentionReport} = await load();
    const r = retentionReport();
    expect(r.exists).toBe(true);
    expect(r.runs).toBe(1);
    expect(r.files).toBeGreaterThanOrEqual(4);
    expect(r.bytes).toBeGreaterThan(0);
  });
  it("REPORT-ONLY does not modify states nor delete files", async () => {
    buildRetentionFixture();
    const {retentionReport} = await load();
    const before = snapshotTree(resultsDir);
    const r = retentionReport(false);
    expect(r.removed).toEqual([]);
    expect(snapshotTree(resultsDir)).toEqual(before);
  }, 120_000);
  it("only removes a TERMINAL and truly inactive candidate, checking every candidate", async () => {
    const fixture = buildRetentionFixture();
    const {retentionReport} = await load();
    const r = retentionReport(true);
    // Solo el terminal realmente inactivo (fuera de las 5 mas recientes).
    expect(r.removed).toEqual([`${EXP}/bt-run-0005`]);
    expect(existsSync(join(expDir(), "bt-run-0005"))).toBe(false);
    for (const id of ["bt-run-0001", "bt-run-0002", "bt-run-0003", "bt-run-0004",
      "bt-run-0006", "bt-run-0007", "bt-run-0008", "bt-run-0009", "bt-run-0010"]) {
      expect(existsSync(join(expDir(), id)), id).toBe(true);
    }
    // Evidencia historica preservada.
    expect(existsSync(join(resultsDir, "_legacy"))).toBe(true);
    expect(r.preserved).toContain("_legacy");
    const reasons = new Set(r.skipped.map((s) => s.reason));
    expect(reasons.has("EXECUTOR_ACTIVE")).toBe(true);
    expect(reasons.has("LOCK_REFERENCE")).toBe(true);
    expect(reasons.has("IDENTITY_PROCESS_NOT_OWNED")).toBe(true);
    // Los procesos vivos siguen vivos (nunca se matan desde retencion).
    for (const pid of fixture.livePids) expect(() => process.kill(pid, 0)).not.toThrow();
  }, 120_000);
  it("never removes the run referenced by the current pointer", async () => {
    for (let i = 1; i <= 6; i += 1) {
      writeRun(`bt-run-${String(i).padStart(4, "0")}`, {status: "completado",
        started_at_ms: 1, updated_at_ms: 2,
        executor_token: "0123456789abcdef", executor_pid: 999999});
    }
    setCurrent("bt-run-0001");
    const {retentionReport} = await load();
    const r = retentionReport(true);
    // Con 6 ejecuciones la ventana conserva 0002..0006; 0001 es el puntero.
    expect(r.removed).toEqual([]);
    expect(existsSync(join(expDir(), "bt-run-0001"))).toBe(true);
    expect(r.skipped).toContainEqual({run: `${EXP}/bt-run-0001`, reason: "CURRENT_POINTER"});
  }, 120_000);
});

// Fixture de retencion: 10 ejecuciones; las 5 primeras fuera de la ventana.
//  - 0001: activa, proceso verificado vivo (no-current)  -> conservar
//  - 0002: TIMEOUT con proceso todavia vivo              -> conservar
//  - 0003: identidad UNKNOWN (PID ajeno)                 -> conservar
//  - 0004: terminal con proceso todavia vivo             -> conservar
//  - 0005: terminal realmente inactivo                   -> UNICO eliminable
//  - 0006..0010: recientes (dentro de la ventana)        -> conservar
function buildRetentionFixture(): {livePids: number[]} {
  const livePids: number[] = [];
  const runIdFor = (i: number) => `bt-run-${String(i).padStart(4, "0")}`;
  const tokenFor = (i: number) => `${String(i).padStart(2, "0")}`.repeat(16);
  const owned = (i: number) => {
    const runId = runIdFor(i);
    const token = tokenFor(i);
    const started = Date.now() - 1000 - i * 1000;
    const child = spawnOwnedExecutor(runId, token, 180_000);
    livePids.push(child.pid!);
    writeRun(runId, {status: "ejecutando", started_at_ms: started, updated_at_ms: started,
      executor_token: token, executor_pid: child.pid});
    writeFileSync(join(runDir(runId), "job_pid.json"),
      JSON.stringify({pid: child.pid, run_id: runId, token, started_at_ms: started}));
    return {runId, token};
  };
  // 0001 activa verificada
  const a = owned(1);
  // 0002 TIMEOUT con proceso vivo (presupuesto vencido)
  const {BACKTEST_BUDGET_MS} = {BACKTEST_BUDGET_MS: 600_000};
  const token2 = tokenFor(2);
  const c2 = spawnOwnedExecutor("bt-run-0002", token2, 180_000);
  livePids.push(c2.pid!);
  const oldStart = Date.now() - BACKTEST_BUDGET_MS - 10_000;
  writeRun("bt-run-0002", {status: "ejecutando", started_at_ms: oldStart,
    updated_at_ms: oldStart, executor_token: token2, executor_pid: c2.pid});
  writeFileSync(join(runDir("bt-run-0002"), "job_pid.json"),
    JSON.stringify({pid: c2.pid, run_id: "bt-run-0002", token: token2, started_at_ms: oldStart}));
  // 0003 identidad UNKNOWN: PID ajeno (el del propio test) con token valido
  writeRun("bt-run-0003", {status: "ejecutando", started_at_ms: Date.now(),
    updated_at_ms: Date.now(), executor_token: tokenFor(3), executor_pid: process.pid});
  // 0004 terminal con proceso todavia vivo
  const token4 = tokenFor(4);
  const c4 = spawnOwnedExecutor("bt-run-0004", token4, 180_000);
  livePids.push(c4.pid!);
  const started4 = Date.now() - 4000;
  writeRun("bt-run-0004", {status: "completado", started_at_ms: started4,
    updated_at_ms: started4, executor_token: token4, executor_pid: c4.pid});
  writeFileSync(join(runDir("bt-run-0004"), "job_pid.json"),
    JSON.stringify({pid: c4.pid, run_id: "bt-run-0004", token: token4, started_at_ms: started4}));
  // 0005 terminal realmente inactivo (PID muerto)
  writeRun("bt-run-0005", {status: "completado", started_at_ms: 1, updated_at_ms: 2,
    executor_token: tokenFor(5), executor_pid: 999999});
  // 0006..0010 recientes, terminales con PID muerto; 0010 es current
  for (let i = 6; i <= 10; i += 1) {
    writeRun(runIdFor(i), {status: "completado", started_at_ms: 1, updated_at_ms: 2,
      executor_token: tokenFor(i), executor_pid: 999999});
  }
  setCurrent("bt-run-0010");
  // Lock apuntando a una ejecucion reciente (no se borra su directorio).
  writeFileSync(join(expDir(), "run.lock"), JSON.stringify({run_id: a.runId,
    pid: 999999, token: a.token, acquired_at_ms: Date.now(), host: "bff"}));
  writeRun(a.runId, {status: "ejecutando", started_at_ms: Date.now() - 1000,
    updated_at_ms: Date.now() - 1000, executor_token: a.token,
    executor_pid: JSON.parse(readFileSync(join(runDir(a.runId), "job_state.json"), "utf8")).executor_pid});
  // _legacy en la raiz
  mkdirSync(join(resultsDir, "_legacy", "preliminary"), {recursive: true});
  writeFileSync(join(resultsDir, "_legacy", "preliminary", "evidence.txt"), "historico\n");
  return {livePids};
}

function snapshotTree(root: string): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, {withFileTypes: true})) {
      const p = join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.isFile() && !entry.name.endsWith(".tmp")) out[p] = sha(readFileSync(p).toString("binary"));
    }
  };
  walk(root);
  return out;
}
