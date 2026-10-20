import {spawn, spawnSync} from "node:child_process";
import {existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync} from "node:fs";
import {join} from "node:path";
import {createHash} from "node:crypto";

// Backtest offline controlado (Dashboard V2). SEPARADO del monitor Binance:
// nunca reutiliza el controlador de runtime ni escribe en el store de runs.
// Todo vive en un directorio propio aislado (frontend/.backtest-runs/),
// ignorado por git, fuera de datos operacionales y de DBs canonicas.
const ROOT = process.env.BACKTEST_ROOT ?? "C:/proyectos/binance-futures-microstructure-bot";
// Directorio de runs: ruta constante y acotada al proyecto (el trazador de
// Next puede resolverla estaticamente). Solo las pruebas lo redirigen mediante
// variable de entorno; el cliente nunca puede cambiarlo.
const RUNS_DIR_DEFAULT = join("C:/proyectos/binance-futures-microstructure-bot", "frontend", ".backtest-runs");
function runsDir(): string {
  return process.env.BACKTEST_RUNS_DIR ?? RUNS_DIR_DEFAULT;
}
const PY = process.env.BACKTEST_PYTHON ?? "python";
// Ejecucion unica controlada: una evaluacion a la vez. El estado se persiste
// en disco, de modo que refrescar o cerrar el navegador NO pierde ni relanza
// la tarea.
export const BACKTEST_BUDGET_MS = 600_000;
export const BACKTEST_JOB_STATUSES = ["pendiente", "ejecutando", "completado", "fallido"] as const;
export type BacktestJobStatus = (typeof BACKTEST_JOB_STATUSES)[number];

// Lista permitida. El cliente NUNCA envia rutas ni simbolos libres.
export const BACKTEST_EXPERIMENTS = ["eval-census-v2-trio"] as const;
export type BacktestExperiment = (typeof BACKTEST_EXPERIMENTS)[number];
export function isBacktestExperiment(v: unknown): v is BacktestExperiment {
  return typeof v === "string" && (BACKTEST_EXPERIMENTS as readonly string[]).includes(v);
}

export type BacktestJobState = {
  job_id: string;
  experiment_id: string;
  status: BacktestJobStatus;
  error: string | null;
  detail: string | null;
  started_at_ms: number | null;
  updated_at_ms: number | null;
  duration_ms: number | null;
  n_trades: number | null;
  reconciliation_ok: boolean | null;
  run_id: string | null;
  result_hashes: Record<string, string> | null;
};

function jobDir(experiment: string): string {
  return join(runsDir(), experiment);
}
export function jobStatePath(experiment: string): string {
  return join(jobDir(experiment), "job_state.json");
}

function readJson<T>(path: string): T | null {
  try {
    if (!existsSync(path)) return null;
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function normalizeJob(raw: Record<string, unknown> | null, experiment: string): BacktestJobState | null {
  if (!raw) return null;
  const status = String(raw.status ?? "");
  if (!(BACKTEST_JOB_STATUSES as readonly string[]).includes(status)) return null;
  return {
    job_id: String(raw.job_id ?? experiment),
    experiment_id: String(raw.experiment_id ?? experiment),
    status: status as BacktestJobStatus,
    error: raw.error == null ? null : String(raw.error),
    detail: raw.detail == null ? null : String(raw.detail),
    started_at_ms: typeof raw.started_at_ms === "number" ? raw.started_at_ms : null,
    updated_at_ms: typeof raw.updated_at_ms === "number" ? raw.updated_at_ms : null,
    duration_ms: typeof raw.duration_ms === "number" ? raw.duration_ms : null,
    n_trades: typeof raw.n_trades === "number" ? raw.n_trades : null,
    reconciliation_ok: typeof raw.reconciliation_ok === "boolean" ? raw.reconciliation_ok : null,
    run_id: raw.run_id == null ? null : String(raw.run_id),
    result_hashes: (raw.result_hashes as Record<string, string>) ?? null,
  };
}

// Un proceso sigue vivo si el PID del estado existe. Se usa para reconciliar
// un estado "ejecutando" huerfano tras un reinicio del servidor.
function processAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function readJobState(experiment: BacktestExperiment): BacktestJobState | null {
  const state = normalizeJob(readJson<Record<string, unknown>>(jobStatePath(experiment)), experiment);
  if (!state) return null;
  if (state.status === "ejecutando") {
    const pid = readJson<{pid?: unknown}>(join(jobDir(experiment), "job_pid.json"));
    const pidNum = typeof pid?.pid === "number" ? pid.pid : null;
    if (pidNum === null || !processAlive(pidNum)) {
      // El proceso murio sin escribir estado final: no se sustituye por un
      // mock; se reporta fallido y se conserva el detalle.
      const failed: BacktestJobState = {...state, status: "fallido",
        error: "PROCESS_INTERRUPTED",
        detail: "El proceso de backtest ya no esta activo y no dejo estado final. Reintente la ejecucion."};
      writeFileSync(jobStatePath(experiment), JSON.stringify(failed, null, 1));
      return failed;
    }
  }
  return state;
}

// Single-flight: si ya hay una tarea pendiente/ejecutando viva, NO se lanza
// otra. Devuelve el estado actual. Evita duplicados por doble clic/refresco.
export function startJob(experiment: BacktestExperiment): {started: boolean; state: BacktestJobState | null; error?: string} {
  const current = readJobState(experiment);
  if (current && (current.status === "ejecutando" || current.status === "pendiente")) {
    return {started: false, state: current};
  }
  mkdirSync(jobDir(experiment), {recursive: true});
  // Estado "pendiente" ANTES de lanzar: si el spawn falla, no queda en blanco.
  const now = Date.now();
  const pending: BacktestJobState = {
    job_id: experiment, experiment_id: experiment, status: "pendiente",
    error: null, detail: null, started_at_ms: now, updated_at_ms: now,
    duration_ms: null, n_trades: null, reconciliation_ok: null,
    run_id: null, result_hashes: null,
  };
  writeFileSync(jobStatePath(experiment), JSON.stringify(pending, null, 1));
  const child = spawn(PY, ["scripts/run_dashboard_backtest.py",
    "--experiment", experiment, "--out-dir", jobDir(experiment)],
    {cwd: ROOT, windowsHide: true, detached: true, stdio: "ignore",
     env: {...process.env, PYTHONPATH: ROOT + "/src"}});
  if (!child.pid) {
    const failed = {...pending, status: "fallido" as const, error: "SPAWN_FAILED",
      detail: "No se pudo iniciar el proceso de backtest."};
    writeFileSync(jobStatePath(experiment), JSON.stringify(failed, null, 1));
    return {started: false, state: failed, error: "SPAWN_FAILED"};
  }
  writeFileSync(join(jobDir(experiment), "job_pid.json"), JSON.stringify({pid: child.pid}));
  child.unref();
  return {started: true, state: readJobState(experiment)};
}

export type BacktestResults = {
  experiment_id: string;
  summary: Record<string, unknown>;
  trades: Record<string, unknown>[];
  reconciliation: Record<string, unknown> | null;
  available: true;
};

export function readResults(experiment: BacktestExperiment): BacktestResults | {available: false; status: BacktestJobStatus | "sin_ejecutar"; error: string} {
  const state = readJobState(experiment);
  const status = state?.status ?? "sin_ejecutar";
  const summary = readJson<Record<string, unknown>>(join(jobDir(experiment), "summary.json"));
  const trades = readJson<{trades?: Record<string, unknown>[]}>(join(jobDir(experiment), "trades.json"));
  if (status !== "completado" || !summary || !trades?.trades) {
    return {available: false, status,
      error: status === "fallido" ? (state?.error ?? "EXECUTION_FAILED") : "RESULT_NOT_READY"};
  }
  return {experiment_id: experiment, summary,
    trades: trades.trades,
    reconciliation: readJson<Record<string, unknown>>(join(jobDir(experiment), "reconciliation.json")),
    available: true};
}

// Materializa (o reutiliza) el artefacto PAPER-LAB-REPLAY-V1 de UNA operacion
// elegida del experimento. Determinista: se cachea por hash de identidad.
export type ReplayLinkRequest = {
  experiment: BacktestExperiment;
  event_id: string;
  group: string;
  segment: string;
  scale: number;
};

export function replayArtifactName(req: ReplayLinkRequest): string {
  const key = createHash("sha256")
    .update([req.experiment, req.event_id, req.group, req.segment, String(req.scale)].join("|"))
    .digest("hex").slice(0, 16);
  return `replay_${key}.json`;
}

export function materializeReplay(req: ReplayLinkRequest): {ok: boolean; artifact?: unknown; error?: string} {
  const state = readJobState(req.experiment);
  if (state?.status !== "completado") {
    return {ok: false, error: "RESULT_NOT_READY"};
  }
  const dir = jobDir(req.experiment);
  const out = join(dir, replayArtifactName(req));
  const existing = readJson<unknown>(out);
  if (existing) return {ok: true, artifact: existing};
  const r = spawnSync(PY, ["scripts/build_paper_lab_replay.py",
    "--trades-json", join(dir, "trades.json"),
    "--target-event-id", req.event_id,
    "--target-group", req.group,
    "--target-segment", req.segment,
    "--target-scale", String(req.scale),
    "--out", out],
    {cwd: ROOT, encoding: "utf8", timeout: 60_000, maxBuffer: 8 * 1024 * 1024,
     windowsHide: true, env: {...process.env, PYTHONPATH: ROOT + "/src"}});
  if (r.status !== 0) {
    return {ok: false, error: "REPLAY_UNSUPPORTED",
      ...{ detail: (r.stderr || "").trim().slice(-400) }};
  }
  const artifact = readJson<unknown>(out);
  if (!artifact) return {ok: false, error: "REPLAY_UNSUPPORTED"};
  return {ok: true, artifact};
}

// Limpieza acotada: conserva el estado y los resultados mas recientes; no
// toca nada fuera del directorio de runs.
export function retentionReport(): {dir: string; exists: boolean; bytes: number; files: number} {
  if (!existsSync(runsDir())) return {dir: runsDir(), exists: false, bytes: 0, files: 0};
  let bytes = 0, files = 0;
  for (const entry of readdirSync(runsDir())) {
    const p = join(runsDir(), entry);
    try {
      const st = statSync(p);
      if (st.isFile()) { bytes += st.size; files += 1; }
      if (st.isDirectory()) {
        for (const f of readdirSync(p)) {
          const sp = join(p, f);
          try { const s = statSync(sp); if (s.isFile()) { bytes += s.size; files += 1; } } catch { /* ignore */ }
        }
      }
    } catch { /* ignore */ }
  }
  return {dir: runsDir(), exists: true, bytes, files};
}
