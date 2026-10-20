// @vitest-environment node
// Reproducciones compactas de los cinco defectos probados en Backtest V2.
// El mismo archivo se ejecuta contra la base auditada (debe FALLAR: el defecto
// existe) y contra la implementacion corregida (debe PASAR). No usa APIs que
// solo existan en la version nueva: por eso puede correr en ambas.
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {createHash} from "node:crypto";
import {spawn, type ChildProcess} from "node:child_process";
import {existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

let resultsDir: string;
let fakeRoot: string;
const children: ChildProcess[] = [];

beforeEach(() => {
  resultsDir = mkdtempSync(join(tmpdir(), "bt-defect-"));
  fakeRoot = mkdtempSync(join(tmpdir(), "bt-defect-root-"));
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
  for (const child of children.splice(0)) { try { child.kill(); } catch { /* ignore */ } }
  try { rmSync(resultsDir, {recursive: true, force: true}); } catch { /* ignore */ }
  try { rmSync(fakeRoot, {recursive: true, force: true}); } catch { /* ignore */ }
});

const load = () => import("@/lib/backtest-control");
const EXP = "eval-census-v2-trio";
const expDir = () => join(resultsDir, EXP);
const runDir = (runId: string) => join(expDir(), runId);
const sha = (s: string) => createHash("sha256").update(Buffer.from(s)).digest("hex");

const FAKE_EXECUTOR = String.raw`
import argparse, hashlib, json, os, sys, time
ap = argparse.ArgumentParser()
ap.add_argument("--experiment"); ap.add_argument("--out-dir")
ap.add_argument("--run-id"); ap.add_argument("--executor-token")
ap.add_argument("--budget-ms"); ap.add_argument("--context-candles")
args, _ = ap.parse_known_args()
out = args.out_dir
os.makedirs(out, exist_ok=True)
time.sleep(float(os.environ.get("FAKE_EXECUTOR_SLEEP", "0.2")))
summary = {"experiment_id": args.experiment, "run_id": args.run_id,
           "cells": [], "n_trades_total": 0, "reconciliation_ok": True}
trades = {"experiment_id": args.experiment, "run_id": args.run_id,
          "n_trades": 0, "trades": []}
recon = {"experiment_id": args.experiment, "run_id": args.run_id,
         "ok": True, "cells": []}
hashes = {}
for name, doc in (("summary.json", summary), ("trades.json", trades),
                  ("reconciliation.json", recon)):
    p = os.path.join(out, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    with open(p, "rb") as f:
        hashes[name] = hashlib.sha256(f.read()).hexdigest()
state = {"job_id": args.run_id, "run_id": args.run_id,
         "experiment_id": args.experiment, "status": "completado",
         "executor_token": args.executor_token, "executor_pid": os.getpid(),
         "started_at_ms": int(time.time()*1000),
         "updated_at_ms": int(time.time()*1000), "identity": "declared",
         "n_trades": 0, "reconciliation_ok": True, "result_hashes": hashes}
tmp = os.path.join(out, "job_state.json.tmp")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(state, f)
os.replace(tmp, os.path.join(out, "job_state.json"))
`;

function writeRun(runId: string, state: Record<string, unknown>,
                  files: Record<string, string> = {}) {
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
function ownedExecutor(runId: string, token: string): ChildProcess {
  const child = spawn(process.execPath, ["-e", "setTimeout(()=>{},120000)", "--",
    "--run-id", runId, "--executor-token", token], {stdio: "ignore", windowsHide: true});
  children.push(child);
  return child;
}
function artifacts(runId: string, n = 0) {
  const rows = Array.from({length: n}, (_, i) => ({
    trade_id: `t${i}`, event_id: `E:${i}`, group: "continuation", segment: "dev",
    scale: 1, entry_ms: 1, exit_ms: 2, net_pnl: 0, fees: 0, funding: 0,
  }));
  const summary = JSON.stringify({experiment_id: EXP, run_id: runId,
    cells: [], n_trades_total: n, reconciliation_ok: true});
  const trades = JSON.stringify({experiment_id: EXP, run_id: runId,
    n_trades: n, trades: rows});
  const recon = JSON.stringify({experiment_id: EXP, run_id: runId, ok: true, cells: []});
  return {
    files: {"summary.json": summary, "trades.json": trades, "reconciliation.json": recon},
    hashes: {"summary.json": sha(summary), "trades.json": sha(trades),
      "reconciliation.json": sha(recon)},
  };
}

describe("defect 1+2: lock/identity must be run-scoped and OS-verified", () => {
  it("a TERMINAL run with a LIVE executor does not authorize a duplicate", async () => {
    const mod = await load();
    const runId = "bt-run-defect-lock-0001";
    const token = "0123456789abcdef0123456789abcdef";
    const child = ownedExecutor(runId, token);
    const doc = artifacts(runId, 0);
    writeRun(runId, {status: "completado", started_at_ms: Date.now() - 1000,
      updated_at_ms: Date.now() - 1000, executor_token: token,
      executor_pid: child.pid, result_hashes: doc.hashes}, doc.files);
    writeFileSync(join(runDir(runId), "job_pid.json"), JSON.stringify({
      pid: child.pid, run_id: runId, token, started_at_ms: Date.now() - 1000}));
    // El lock pertenece a la ejecucion, pero su PID de BFF ya no existe.
    writeFileSync(join(expDir(), "run.lock"), JSON.stringify({run_id: runId,
      pid: 999999, token, acquired_at_ms: Date.now(), host: "bff"}));
    setCurrent(runId);
    const r = mod.startJob(EXP);
    expect(r.started).toBe(false);
    expect(existsSync(join(expDir(), "run.lock"))).toBe(true);
    // El ejecutor vivo NO fue matado.
    expect(() => process.kill(child.pid!, 0)).not.toThrow();
  }, 120_000);

  it("a foreign live PID with a valid token is NOT 'ejecutando'", async () => {
    const mod = await load();
    const runId = "bt-run-defect-identity-0002";
    writeRun(runId, {status: "ejecutando", started_at_ms: Date.now(),
      updated_at_ms: Date.now(), executor_token: "0123456789abcdef0123456789abcdef",
      executor_pid: process.pid, identity: "verified"});
    setCurrent(runId);
    const s = mod.readJobState(EXP);
    expect(s?.status).toBe("fallido");
    expect(s?.identity).toBe("UNKNOWN");
  });
});

describe("defect 3: results require declared, complete hashes and identity", () => {
  it("does NOT serve a completed run that declares no hashes", async () => {
    const mod = await load();
    const runId = "bt-run-defect-hashes-0003";
    const doc = artifacts(runId, 2);
    writeRun(runId, {status: "completado"}, doc.files);
    setCurrent(runId);
    const r = mod.readResults(EXP);
    expect(r.available).toBe(false);
  });

  it("does NOT serve a completed run whose artifacts belong to another run", async () => {
    const mod = await load();
    const runId = "bt-run-defect-identity-0004";
    const other = artifacts("bt-run-defect-other-9999", 2);
    writeRun(runId, {status: "completado", result_hashes: other.hashes}, other.files);
    setCurrent(runId);
    const r = mod.readResults(EXP);
    expect(r.available).toBe(false);
  });
});

describe("defect 4: retention never removes a possibly-active run", () => {
  it("preserves an ACTIVE candidate with a live owned executor", async () => {
    const mod = await load();
    const token = "0123456789abcdef0123456789abcdef";
    const child = ownedExecutor("bt-run-0001", token);
    writeRun("bt-run-0001", {status: "ejecutando", started_at_ms: Date.now() - 1000,
      updated_at_ms: Date.now() - 1000, executor_token: token, executor_pid: child.pid});
    writeFileSync(join(runDir("bt-run-0001"), "job_pid.json"), JSON.stringify({
      pid: child.pid, run_id: "bt-run-0001", token, started_at_ms: Date.now() - 1000}));
    for (let i = 2; i <= 6; i += 1) {
      writeRun(`bt-run-000${i}`, {status: "completado", started_at_ms: 1,
        updated_at_ms: 2, executor_token: "0123456789abcdef", executor_pid: 999999});
    }
    setCurrent("bt-run-0006");
    mod.retentionReport(true);
    expect(existsSync(join(expDir(), "bt-run-0001"))).toBe(true);
    expect(() => process.kill(child.pid!, 0)).not.toThrow();
  }, 120_000);
});

describe("defect 5: aggregates keep UNKNOWN instead of zero", () => {
  it("a cell with missing economic data does not become zero", async () => {
    const {countsByScale} = await import("@/lib/backtest-results");
    const cell = {
      symbol: "BTCUSDT", res: "15m", group: "continuation", label: "H1",
      segment: "dev", scale: 1, n_events: 10, n_trades: 10, n_realized: null,
      n_open: null, skipped_overlap: 0, n_expired: 0, n_mismatched: 0,
      exit_reasons: null, expectancy_net: null, expectancy_gross: null,
      total_net: null, total_net_realized: null, total_fees: null,
      total_funding: null, max_drawdown: null, max_drawdown_realized: null,
      mfe_mean: null, mae_mean: null, config_hash: "x", n_trades_1x: 10,
      status: "ok",
    } as never;
    const c = countsByScale([cell], 1);
    expect(c.n_realized).toBeNull();
    expect(c.total_net_realized).toBeNull();
  });

  it("an empty set is UNKNOWN, not zero", async () => {
    const {countsByScale} = await import("@/lib/backtest-results");
    const c = countsByScale([], 1);
    expect(c.n_trades).toBeNull();
    expect(c.total_net_realized).toBeNull();
  });
});
