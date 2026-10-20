import {spawn, spawnSync} from "node:child_process";
import {
  closeSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync,
  renameSync, rmSync, statSync, writeFileSync, writeSync,
} from "node:fs";
import {join} from "node:path";
import {createHash, randomBytes} from "node:crypto";

// Backtest offline controlado (Dashboard V2). SEPARADO del monitor Binance:
// nunca reutiliza el controlador de runtime ni escribe en el store de runs.
// Todo vive en un directorio propio aislado, ignorado por git, fuera de datos
// operacionales y de DBs canonicas.
//
// UBICACION CANONICA (unica, decidida en DECISIONS): `<repo>/backtest-results/`.
// El contrato la nombra explicitamente; el codigo y el contrato coinciden.
// Solo las pruebas la redirigen mediante variable de entorno; el cliente NUNCA
// puede cambiarla.
const ROOT = process.env.BACKTEST_ROOT ?? "C:/proyectos/binance-futures-microstructure-bot";
const RESULTS_DIR_DEFAULT = join(ROOT, "backtest-results");
function resultsDir(): string {
  return process.env.BACKTEST_RUNS_DIR ?? RESULTS_DIR_DEFAULT;
}
const PY = process.env.BACKTEST_PYTHON ?? "python";

// Presupuesto de ejecucion EFECTIVO: una tarea "ejecutando" que supere este
// limite sin cerrar estado se marca fallida (TIMEOUT), sin matar un proceso
// cuya propiedad no podamos verificar. El ejecutor backend tambien lo aplica.
export const BACKTEST_BUDGET_MS = 600_000;
export const BACKTEST_JOB_STATUSES = ["pendiente", "ejecutando", "completado", "fallido"] as const;
export type BacktestJobStatus = (typeof BACKTEST_JOB_STATUSES)[number];

// Lista permitida. El cliente NUNCA envia rutas ni simbolos libres.
export const BACKTEST_EXPERIMENTS = ["eval-census-v2-trio"] as const;
export type BacktestExperiment = (typeof BACKTEST_EXPERIMENTS)[number];
export function isBacktestExperiment(v: unknown): v is BacktestExperiment {
  return typeof v === "string" && (BACKTEST_EXPERIMENTS as readonly string[]).includes(v);
}

// Token de propiedad: identifica SIN ambiguedad la ejecucion que escribio el
// estado. Un PID vivo ajeno (o reutilizado) NO prueba propiedad: solo el token
// completo (run_id + executor_token + started_at_ms) la prueba.
export type ExecutorIdentity = {
  run_id: string;
  experiment_id: string;
  pid: number | null;
  executor_token: string;
  executor_version: string | null;
  started_at_ms: number | null;
};

export type BacktestJobState = {
  job_id: string;            // = run_id (identidad de ejecucion unica), no del experimento
  run_id: string;
  experiment_id: string;
  status: BacktestJobStatus;
  error: string | null;
  detail: string | null;
  started_at_ms: number | null;
  updated_at_ms: number | null;
  duration_ms: number | null;
  n_trades: number | null;
  reconciliation_ok: boolean | null;
  executor_token: string | null;
  executor_pid: number | null;
  executor_version: string | null;
  result_hashes: Record<string, string> | null;
  identity: "verified" | "UNKNOWN";
};

function experimentDir(experiment: string): string {
  return join(resultsDir(), experiment);
}
function runDir(experiment: string, runId: string): string {
  return join(experimentDir(experiment), runId);
}
// Puntero estable a la ejecucion "actual" (la mas reciente, o la activa).
function currentPointerPath(experiment: string): string {
  return join(experimentDir(experiment), "current.json");
}
// Lock por experimento: exclusion ENTRE PROCESOS mediante creacion exclusiva.
function lockPath(experiment: string): string {
  return join(experimentDir(experiment), "run.lock");
}

function readJson<T>(path: string): T | null {
  try {
    if (!existsSync(path)) return null;
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch {
    return null;
  }
}

// Escritura ATOMICA: archivo temporal + rename. Evita estados parciales, que
// es lo que necesita la exclusion entre procesos.
function writeJsonAtomic(path: string, data: unknown): void {
  mkdirSync(join(path, ".."), {recursive: true});
  const tmp = `${path}.tmp.${process.pid}.${randomBytes(4).toString("hex")}`;
  writeFileSync(tmp, JSON.stringify(data, null, 1));
  renameSync(tmp, path);
}

const TOKEN_SAFE = /^[a-z0-9-]{8,64}$/i;
export function newRunId(experiment: string): string {
  const ts = new Date().toISOString().replace(/[-:.TZ]/g, "");
  const rnd = randomBytes(4).toString("hex");
  return `bt-${experiment}-${ts}-${rnd}`.slice(0, 64);
}
export function newExecutorToken(): string {
  return randomBytes(16).toString("hex");
}

function normalizeJob(
  raw: Record<string, unknown> | null, experiment: string,
): BacktestJobState | null {
  if (!raw) return null;
  const status = String(raw.status ?? "");
  if (!(BACKTEST_JOB_STATUSES as readonly string[]).includes(status)) return null;
  const runId = String(raw.run_id ?? raw.job_id ?? "");
  if (!TOKEN_SAFE.test(runId)) return null;
  return {
    job_id: runId,
    run_id: runId,
    experiment_id: String(raw.experiment_id ?? experiment),
    status: status as BacktestJobStatus,
    error: raw.error == null ? null : String(raw.error),
    detail: raw.detail == null ? null : String(raw.detail),
    started_at_ms: typeof raw.started_at_ms === "number" ? raw.started_at_ms : null,
    updated_at_ms: typeof raw.updated_at_ms === "number" ? raw.updated_at_ms : null,
    duration_ms: typeof raw.duration_ms === "number" ? raw.duration_ms : null,
    n_trades: typeof raw.n_trades === "number" ? raw.n_trades : null,
    reconciliation_ok: typeof raw.reconciliation_ok === "boolean" ? raw.reconciliation_ok : null,
    executor_token: raw.executor_token == null ? null : String(raw.executor_token),
    executor_pid: typeof raw.executor_pid === "number" ? raw.executor_pid : null,
    executor_version: raw.executor_version == null ? null : String(raw.executor_version),
    result_hashes: (raw.result_hashes as Record<string, string>) ?? null,
    identity: raw.identity === "verified" ? "verified" : "UNKNOWN",
  };
}

// Un proceso sigue vivo si el PID existe. NUNCA prueba propiedad por si solo.
function pidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function readPointer(experiment: string): {run_id: string} | null {
  const p = readJson<{run_id?: unknown}>(currentPointerPath(experiment));
  const id = p && typeof p.run_id === "string" ? p.run_id : null;
  return id && TOKEN_SAFE.test(id) ? {run_id: id} : null;
}

// Resuelve el directorio de estado de la ejecucion actual sin crearla.
function currentStatePath(experiment: string): string | null {
  const ptr = readPointer(experiment);
  return ptr ? join(runDir(experiment, ptr.run_id), "job_state.json") : null;
}

function readRawState(experiment: string, runId: string): Record<string, unknown> | null {
  return readJson<Record<string, unknown>>(join(runDir(experiment, runId), "job_state.json"));
}

// Reconciliacion de un estado activo (pendiente/ejecutando) SIN relanzar:
//  - si el token/PID no prueban propiedad -> UNKNOWN (identidad ambiguada);
//  - si el proceso murio -> fallido PROCESS_INTERRUPTED;
//  - si excede el presupuesto -> fallido TIMEOUT.
// Nunca mata un proceso ajeno.
function reconcile(experiment: string, state: BacktestJobState): BacktestJobState {
  if (state.status !== "pendiente" && state.status !== "ejecutando") return state;
  const now = Date.now();
  const path = join(runDir(experiment, state.run_id), "job_state.json");
  // 1) Propiedad: solo un token+pid coincidentes prueban que el proceso es nuestro.
  const tokenOk = typeof state.executor_token === "string" && TOKEN_SAFE.test(state.executor_token);
  const pid = state.executor_pid;
  if (!tokenOk || pid === null) {
    // Identidad no verificable: no se declara ejecutando ni se relanza.
    const unknown: BacktestJobState = {...state, status: "fallido",
      error: "PROCESS_IDENTITY_UNKNOWN",
      detail: "No hay token/PID verificables para la ejecucion activa; no se relanza automaticamente.",
      updated_at_ms: now, identity: "UNKNOWN"};
    writeJsonAtomic(path, unknown);
    return unknown;
  }
  // 2) Proceso muerto: no dejo estado final, sea cual sea el presupuesto.
  if (!pidAlive(pid)) {
    const failed: BacktestJobState = {...state, status: "fallido",
      error: "PROCESS_INTERRUPTED",
      detail: "El proceso de backtest ya no esta activo y no dejo estado final. Reintente la ejecucion.",
      updated_at_ms: now};
    writeJsonAtomic(path, failed);
    return failed;
  }
  // 3) Proceso vivo y verificado que excede el presupuesto efectivo -> TIMEOUT.
  const basis = state.started_at_ms ?? state.updated_at_ms;
  if (basis !== null && now - basis > BACKTEST_BUDGET_MS) {
    const timedOut: BacktestJobState = {...state, status: "fallido", error: "TIMEOUT",
      detail: `La ejecucion supero el presupuesto de ${BACKTEST_BUDGET_MS} ms sin cerrar estado.`,
      updated_at_ms: now, identity: state.identity};
    writeJsonAtomic(path, timedOut);
    return timedOut;
  }
  return state;
}

// Estado persistido de la ejecucion ACTUAL del experimento (o null si no hay).
export function readJobState(experiment: BacktestExperiment): BacktestJobState | null {
  const ptr = readPointer(experiment);
  if (!ptr) return null;
  const raw = readRawState(experiment, ptr.run_id);
  const state = normalizeJob(raw, experiment);
  if (!state) return null;
  if (state.status === "pendiente" || state.status === "ejecutando") {
    return reconcile(experiment, state);
  }
  return state;
}

// Estado de una ejecucion concreta por run_id (para resultados vinculados).
export function readRunState(experiment: BacktestExperiment, runId: string): BacktestJobState | null {
  if (!TOKEN_SAFE.test(runId)) return null;
  const raw = readRawState(experiment, runId);
  const state = normalizeJob(raw, experiment);
  if (!state) return null;
  if (state.status === "pendiente" || state.status === "ejecutando") {
    return reconcile(experiment, state);
  }
  return state;
}

export function currentRunId(experiment: BacktestExperiment): string | null {
  return readPointer(experiment)?.run_id ?? null;
}

// --- Exclusion entre procesos ----------------------------------------------
// Try-lock con creacion EXCLUSIVA (O_EXCL). Devuelve true si se obtuvo.
type LockInfo = {run_id: string; pid: number | null; token: string; acquired_at_ms: number; host: string};

function tryAcquireLock(experiment: string, info: LockInfo): boolean {
  mkdirSync(experimentDir(experiment), {recursive: true});
  const path = lockPath(experiment);
  try {
    const fd = openSync(path, "wx"); // falla si ya existe
    try { writeSync(fd, JSON.stringify(info)); } finally { closeSync(fd); }
    return true;
  } catch (e) {
    const code = (e as NodeJS.ErrnoException).code;
    if (code !== "EEXIST") throw e;
    return false;
  }
}
function readLock(experiment: string): LockInfo | null {
  return readJson<LockInfo>(lockPath(experiment));
}
function releaseLock(experiment: string): void {
  try { rmSync(lockPath(experiment), {force: true}); } catch { /* ignore */ }
}
// Un lock es ABANDONADO si su proceso ya no vive, o si excede el presupuesto.
function lockIsStale(lock: LockInfo): boolean {
  if (typeof lock.pid === "number" && !pidAlive(lock.pid)) return true;
  if (typeof lock.acquired_at_ms === "number"
      && Date.now() - lock.acquired_at_ms > BACKTEST_BUDGET_MS) return true;
  return false;
}

// Single-flight ENTRE PROCESOS: si hay un lock vivo, no se lanza otra tarea.
// Un lock abandonado (proceso muerto/presupuesto excedido) NO bloquea
// indefinidamente: se marca la ejecucion abandonada como fallida y se libera.
export type StartResult = {started: boolean; state: BacktestJobState | null; error?: string;
  run_id?: string};

export function startJob(experiment: BacktestExperiment): StartResult {
  mkdirSync(experimentDir(experiment), {recursive: true});

  const lock = readLock(experiment);
  if (lock) {
    if (!lockIsStale(lock)) {
      // Hay una ejecucion activa verificable: NO se lanza otra.
      const active = readRunState(experiment, lock.run_id);
      return {started: false, state: active, run_id: lock.run_id};
    }
    // Lock abandonado: cerrar la ejecucion pendiente sin relanzarla.
    const abandoned = readRunState(experiment, lock.run_id);
    if (abandoned && (abandoned.status === "pendiente" || abandoned.status === "ejecutando")) {
      const failed: BacktestJobState = {...abandoned, status: "fallido",
        error: abandoned.status === "pendiente" ? "PENDING_ABANDONED" : "PROCESS_INTERRUPTED",
        detail: "La ejecucion anterior no dejo estado final verificable; no se relanza automaticamente.",
        updated_at_ms: Date.now()};
      writeJsonAtomic(join(runDir(experiment, abandoned.run_id), "job_state.json"), failed);
    }
    releaseLock(experiment);
  }

  const runId = newRunId(experiment);
  const token = newExecutorToken();
  const now = Date.now();
  const acquired: LockInfo = {run_id: runId, pid: process.pid, token,
    acquired_at_ms: now, host: "bff"};
  if (!tryAcquireLock(experiment, acquired)) {
    // Otra solicitud concurrente gano la carrera: no se lanza duplicado.
    const winner = readLock(experiment);
    const state = winner ? readRunState(experiment, winner.run_id) : null;
    return {started: false, state, run_id: winner?.run_id};
  }

  mkdirSync(runDir(experiment, runId), {recursive: true});
  const pending: BacktestJobState = {
    job_id: runId, run_id: runId, experiment_id: experiment, status: "pendiente",
    error: null, detail: null, started_at_ms: now, updated_at_ms: now,
    duration_ms: null, n_trades: null, reconciliation_ok: null,
    executor_token: token, executor_pid: null, executor_version: null,
    result_hashes: null, identity: "verified",
  };
  writeJsonAtomic(join(runDir(experiment, runId), "job_state.json"), pending);
  // Puntero a la ejecucion actual ANTES de lanzar: el estado es observable.
  writeJsonAtomic(currentPointerPath(experiment), {run_id: runId, updated_at_ms: now});

  let child: ReturnType<typeof spawn>;
  try {
    child = spawn(PY, ["scripts/run_dashboard_backtest.py",
      "--experiment", experiment, "--out-dir", runDir(experiment, runId),
      "--run-id", runId, "--executor-token", token,
      "--budget-ms", String(BACKTEST_BUDGET_MS)],
      {cwd: ROOT, windowsHide: true, detached: true, stdio: "ignore",
       env: {...process.env, PYTHONPATH: ROOT + "/src"}});
  } catch (e) {
    const failed: BacktestJobState = {...pending, status: "fallido", error: "SPAWN_FAILED",
      detail: `No se pudo iniciar el proceso de backtest: ${(e as Error).message}`,
      updated_at_ms: Date.now()};
    writeJsonAtomic(join(runDir(experiment, runId), "job_state.json"), failed);
    releaseLock(experiment);
    return {started: false, state: failed, error: "SPAWN_FAILED", run_id: runId};
  }

  // Error asincrono del spawn: se persiste, no se pierde.
  child.on("error", (err: Error) => {
    const failed: BacktestJobState = {...pending, status: "fallido", error: "SPAWN_FAILED",
      detail: `Fallo asincrono al iniciar el proceso: ${err.message}`, updated_at_ms: Date.now()};
    try { writeJsonAtomic(join(runDir(experiment, runId), "job_state.json"), failed); } catch { /* ignore */ }
    try { releaseLock(experiment); } catch { /* ignore */ }
  });

  if (!child.pid) {
    const failed: BacktestJobState = {...pending, status: "fallido", error: "SPAWN_FAILED",
      detail: "No se pudo iniciar el proceso de backtest (sin PID).", updated_at_ms: Date.now()};
    writeJsonAtomic(join(runDir(experiment, runId), "job_state.json"), failed);
    releaseLock(experiment);
    return {started: false, state: failed, error: "SPAWN_FAILED", run_id: runId};
  }

  const launched: BacktestJobState = {...pending, status: "ejecutando",
    executor_pid: child.pid, updated_at_ms: Date.now()};
  // job_pid.json conserva la identidad verificable del ejecutor.
  writeJsonAtomic(join(runDir(experiment, runId), "job_pid.json"),
    {pid: child.pid, run_id: runId, token, started_at_ms: now});
  writeJsonAtomic(join(runDir(experiment, runId), "job_state.json"), launched);
  // El lock se libera cuando el propio proceso hijo cierra el estado; el
  // backend escribe estado final y el siguiente lector reconcilia el lock.
  child.unref();
  return {started: true, state: launched, run_id: runId};
}

// --- Resultados vinculados a la ejecucion ---------------------------------
export type BacktestResults = {
  experiment_id: string;
  run_id: string;
  summary: Record<string, unknown>;
  trades: Record<string, unknown>[];
  reconciliation: Record<string, unknown> | null;
  available: true;
  result_hashes: Record<string, string>;
};

function sha256File(path: string): string | null {
  try { return createHash("sha256").update(readFileSync(path)).digest("hex"); }
  catch { return null; }
}

export type ResultsUnavailable = {available: false;
  status: BacktestJobStatus | "sin_ejecutar"; error: string; run_id?: string};

// Lee resultados de UNA ejecucion concreta y VERIFICA integridad antes de
// servir: si un hash declarado no coincide con el archivo, falla explicito
// (nunca se sirven resultados alterados o incompletos).
export function readRunResults(
  experiment: BacktestExperiment, runId: string,
): BacktestResults | ResultsUnavailable {
  const state = readRunState(experiment, runId);
  const status = state?.status ?? "sin_ejecutar";
  if (status !== "completado") {
    return {available: false, status, run_id: runId,
      error: status === "fallido" ? (state?.error ?? "EXECUTION_FAILED") : "RESULT_NOT_READY"};
  }
  const dir = runDir(experiment, runId);
  const declared = state?.result_hashes ?? null;
  const needs: Array<"summary.json" | "trades.json" | "reconciliation.json"> =
    ["summary.json", "trades.json", "reconciliation.json"];
  const verified: Record<string, string> = {};
  for (const name of needs) {
    const p = join(dir, name);
    if (!existsSync(p)) {
      return {available: false, status: "fallido", run_id: runId, error: "RESULT_INCOMPLETE"};
    }
    const actual = sha256File(p);
    if (!actual) return {available: false, status: "fallido", run_id: runId, error: "RESULT_UNREADABLE"};
    if (declared && declared[name] && declared[name] !== actual) {
      return {available: false, status: "fallido", run_id: runId, error: "RESULT_INTEGRITY_FAILED"};
    }
    verified[name] = actual;
  }
  const summary = readJson<Record<string, unknown>>(join(dir, "summary.json"));
  const trades = readJson<{trades?: Record<string, unknown>[]}>(join(dir, "trades.json"));
  if (!summary || !trades?.trades) {
    return {available: false, status: "fallido", run_id: runId, error: "RESULT_INCOMPLETE"};
  }
  return {experiment_id: experiment, run_id: runId, summary, trades: trades.trades,
    reconciliation: readJson<Record<string, unknown>>(join(dir, "reconciliation.json")),
    available: true, result_hashes: verified};
}

// Resultados de la ejecucion ACTUAL (compatibilidad con la ruta existente).
export function readResults(experiment: BacktestExperiment): BacktestResults | ResultsUnavailable {
  const runId = currentRunId(experiment);
  if (!runId) return {available: false, status: "sin_ejecutar", error: "RESULT_NOT_READY"};
  return readRunResults(experiment, runId);
}

// --- Enlace operacion -> Paper Lab ----------------------------------------
// Materializa (o reutiliza) el artefacto PAPER-LAB-REPLAY-V1 de UNA operacion,
// VINCULADO a una ejecucion concreta: nombre derivado de run_id + hash de
// resultados + identidad de operacion. Una ejecucion nueva NUNCA reutiliza el
// cache de otra.
export type ReplayLinkRequest = {
  experiment: BacktestExperiment;
  event_id: string;
  group: string;
  segment: string;
  scale: number;
  run_id?: string;
};

export function replayArtifactName(req: ReplayLinkRequest, runId: string, resultHash: string): string {
  const key = createHash("sha256")
    .update([runId, resultHash, req.event_id, req.group, req.segment, String(req.scale)].join("|"))
    .digest("hex").slice(0, 20);
  return `replay_${key}.json`;
}

export type ReplayMaterialization = {ok: true; artifact: unknown; run_id: string; cached: boolean}
  | {ok: false; error: string; detail?: string; run_id?: string};

export function materializeReplay(req: ReplayLinkRequest): ReplayMaterialization {
  const runId = req.run_id ?? currentRunId(req.experiment);
  if (!runId) return {ok: false, error: "RESULT_NOT_READY"};
  const results = readRunResults(req.experiment, runId);
  if (!results.available) {
    return {ok: false, error: results.error === "RESULT_NOT_READY" ? "RESULT_NOT_READY" : "REPLAY_UNSUPPORTED",
      detail: results.error, run_id: runId};
  }
  // La operacion DEBE pertenecer a los resultados de ESA ejecucion.
  const belongs = results.trades.some((t) =>
    String(t.event_id) === req.event_id && String(t.group) === req.group
    && String(t.segment) === req.segment && Number(t.scale) === Number(req.scale));
  if (!belongs) return {ok: false, error: "TARGET_NOT_IN_RUN",
    detail: "La operacion no pertenece a los resultados de esta ejecucion.", run_id: runId};

  const dir = runDir(req.experiment, runId);
  const tradesHash = results.result_hashes["trades.json"] ?? "no-hash";
  const out = join(dir, replayArtifactName(req, runId, tradesHash));
  const existing = readJson<unknown>(out);
  if (existing) return {ok: true, artifact: existing, run_id: runId, cached: true};

  // Escritura atomica: dos solicitudes concurrentes no producen archivo parcial.
  const tmp = `${out}.tmp.${process.pid}.${randomBytes(4).toString("hex")}`;
  const r = spawnSync(PY, ["scripts/build_paper_lab_replay.py",
    "--trades-json", join(dir, "trades.json"),
    "--target-event-id", req.event_id,
    "--target-group", req.group,
    "--target-segment", req.segment,
    "--target-scale", String(req.scale),
    "--out", tmp],
    {cwd: ROOT, encoding: "utf8", timeout: 60_000, maxBuffer: 8 * 1024 * 1024,
     windowsHide: true, env: {...process.env, PYTHONPATH: ROOT + "/src"}});
  if (r.status !== 0) {
    try { rmSync(tmp, {force: true}); } catch { /* ignore */ }
    return {ok: false, error: "REPLAY_UNSUPPORTED", run_id: runId,
      detail: (r.stderr || "").trim().slice(-400)};
  }
  const artifact = readJson<unknown>(tmp);
  if (!artifact) {
    try { rmSync(tmp, {force: true}); } catch { /* ignore */ }
    return {ok: false, error: "REPLAY_UNSUPPORTED", run_id: runId};
  }
  try { renameSync(tmp, out); } catch {
    // Otra solicitud concurrente gano: usar el artefacto ya presente.
    const raced = readJson<unknown>(out);
    if (raced) return {ok: true, artifact: raced, run_id: runId, cached: true};
    try { rmSync(tmp, {force: true}); } catch { /* ignore */ }
    return {ok: false, error: "REPLAY_UNSUPPORTED", run_id: runId};
  }
  return {ok: true, artifact, run_id: runId, cached: false};
}

// --- Retencion acotada -----------------------------------------------------
// Conserva las ejecuciones mas recientes por experimento; NUNCA elimina una
// ejecucion activa (lock vivo o estado pendiente/ejecutando). Solo actua
// dentro del directorio de resultados.
export const BACKTEST_RETENTION_RUNS = 5;

export function retentionReport(apply = false):
  {dir: string; exists: boolean; bytes: number; files: number; runs: number; removed: string[]} {
  const dir = resultsDir();
  if (!existsSync(dir)) return {dir, exists: false, bytes: 0, files: 0, runs: 0, removed: []};
  let bytes = 0, files = 0, runs = 0;
  const removed: string[] = [];
  const experiments = readdirSync(dir).filter((e) => {
    try { return statSync(join(dir, e)).isDirectory(); } catch { return false; }
  });
  for (const exp of experiments) {
    const base = join(dir, exp);
    const active = new Set<string>();
    const lock = readJson<LockInfo>(join(base, "run.lock"));
    if (lock && !lockIsStale(lock)) active.add(lock.run_id);
    const ptr = readJson<{run_id?: unknown}>(join(base, "current.json"));
    if (ptr && typeof ptr.run_id === "string") {
      const st = readRunState(exp as BacktestExperiment, ptr.run_id);
      if (st && (st.status === "pendiente" || st.status === "ejecutando")) active.add(ptr.run_id);
    }
    const runIds = readdirSync(base).filter((r) => {
      try { return statSync(join(base, r)).isDirectory(); } catch { return false; }
    }).sort(); // orden lexicografico ~ cronologico por timestamp en el id
    runs += runIds.length;
    for (const r of runIds) {
      const rd = join(base, r);
      for (const f of readdirSync(rd)) {
        try { const st = statSync(join(rd, f)); if (st.isFile()) { bytes += st.size; files += 1; } }
        catch { /* ignore */ }
      }
    }
    if (apply && runIds.length > BACKTEST_RETENTION_RUNS) {
      const keep = new Set(runIds.slice(-BACKTEST_RETENTION_RUNS));
      for (const r of runIds) {
        if (keep.has(r) || active.has(r)) continue;
        try { rmSync(join(base, r), {recursive: true, force: true}); removed.push(`${exp}/${r}`); }
        catch { /* ignore */ }
      }
    }
  }
  return {dir, exists: true, bytes, files, runs, removed};
}
