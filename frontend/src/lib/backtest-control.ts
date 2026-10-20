import {spawn, spawnSync} from "node:child_process";
import {
  closeSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync,
  renameSync, rmSync, statSync, writeFileSync, writeSync,
} from "node:fs";
import {join} from "node:path";
import {createHash, randomBytes} from "node:crypto";
import {inspectProcess} from "./process-evidence";

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
// Guard de seccion critica: serializa adquisicion, liberacion y retencion.
// No representa una ejecucion; es un mutex corto entre procesos.
function guardPath(experiment: string): string {
  return join(experimentDir(experiment), "control.guard");
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
const RUN_ID_RE = /^bt-[a-z0-9-]{6,64}$/i;
const HASH_RE = /^[a-f0-9]{64}$/i;
export function newRunId(experiment: string): string {
  const ts = new Date().toISOString().replace(/[-:.TZ]/g, "");
  const rnd = randomBytes(4).toString("hex");
  return `bt-${experiment}-${ts}-${rnd}`.slice(0, 64);
}
export function newExecutorToken(): string {
  return randomBytes(16).toString("hex");
}

function asNumber(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function normalizeJob(
  raw: Record<string, unknown> | null, experiment: string, expectedRunId?: string,
): BacktestJobState | null {
  if (!raw) return null;
  const status = String(raw.status ?? "");
  if (!(BACKTEST_JOB_STATUSES as readonly string[]).includes(status)) return null;
  const rawExperiment = raw.experiment_id == null ? null : String(raw.experiment_id);
  if (rawExperiment !== null && rawExperiment !== experiment) return null;
  const declaredRun = raw.run_id == null ? raw.job_id : raw.run_id;
  const runId = String(declaredRun ?? "");
  if (!TOKEN_SAFE.test(runId)) return null;
  // La identidad de la ejecucion debe coincidir con el directorio que la
  // contiene: dos archivos con valores iguales no prueban nada por si solos,
  // pero un run_id distinto SI es una contradiccion explicita.
  if (expectedRunId !== undefined && runId !== expectedRunId) return null;
  return {
    job_id: runId,
    run_id: runId,
    experiment_id: rawExperiment ?? experiment,
    status: status as BacktestJobStatus,
    error: raw.error == null ? null : String(raw.error),
    detail: raw.detail == null ? null : String(raw.detail),
    started_at_ms: asNumber(raw.started_at_ms),
    updated_at_ms: asNumber(raw.updated_at_ms),
    duration_ms: asNumber(raw.duration_ms),
    n_trades: asNumber(raw.n_trades),
    reconciliation_ok: typeof raw.reconciliation_ok === "boolean" ? raw.reconciliation_ok : null,
    executor_token: raw.executor_token == null ? null : String(raw.executor_token),
    executor_pid: asNumber(raw.executor_pid),
    executor_version: raw.executor_version == null ? null : String(raw.executor_version),
    result_hashes: (raw.result_hashes as Record<string, string>) ?? null,
    // La etiqueta guardada NO es prueba de identidad. Solo la evidencia
    // independiente del proceso puede elevar esto a "verified".
    identity: "UNKNOWN",
  };
}

function readPointer(experiment: string): {run_id: string} | null {
  const p = readJson<{run_id?: unknown}>(currentPointerPath(experiment));
  const id = p && typeof p.run_id === "string" ? p.run_id : null;
  return id && TOKEN_SAFE.test(id) ? {run_id: id} : null;
}

function readRawState(experiment: string, runId: string): Record<string, unknown> | null {
  return readJson<Record<string, unknown>>(join(runDir(experiment, runId), "job_state.json"));
}

// Lectura SIN reconciliar: no escribe nada. Es la unica permitida en
// report-only (retencion) y en la evaluacion de identidad.
function readRunStatePure(
  experiment: BacktestExperiment, runId: string,
): BacktestJobState | null {
  if (!TOKEN_SAFE.test(runId)) return null;
  return normalizeJob(readRawState(experiment, runId), experiment, runId);
}

// --- Identidad efectiva del ejecutor ---------------------------------------
// La propiedad se contrasta con evidencia INDEPENDIENTE del sistema operativo:
// PID + instancia (fecha de creacion) + linea de comandos que contiene el
// token y el run_id de ESTA ejecucion. Los archivos de estado (incluido
// job_pid.json) solo se usan para descubrir candidatos y detectar
// contradicciones; nunca como prueba por si mismos.
export const EXECUTOR_START_GRACE_MS = 120_000;
export const PROC_CREATION_SKEW_MS = 60_000;
export const PROC_CREATION_FUTURE_MS = 180_000;

export type ExecutorEvidence = {
  verdict: "ACTIVE_VERIFIED" | "GONE" | "UNKNOWN";
  reason:
    | "VERIFIED" | "PROCESS_GONE" | "PROCESS_NOT_OWNED" | "PID_INSTANCE_MISMATCH"
    | "EVIDENCE_INCOMPLETE" | "IDENTITY_INCOMPLETE" | "STATE_CONTRADICTION";
  pid: number | null;
  creation_ms: number | null;
  detail?: string;
};

function argvOf(commandLine: string): string[] {
  return commandLine.split(/[\s"']+/).filter((x) => x.length > 0);
}

function containsFlagValue(argv: string[], flag: string, value: string): boolean {
  for (let i = 0; i < argv.length - 1; i += 1) {
    if (argv[i] === flag && argv[i + 1] === value) return true;
    if (argv[i] === `${flag}=${value}`) return true;
  }
  return argv.includes(value);
}

export function executorEvidence(
  experiment: BacktestExperiment, runId: string, state: BacktestJobState,
): ExecutorEvidence {
  const sidecar = readJson<{pid?: unknown; token?: unknown; run_id?: unknown;
    started_at_ms?: unknown}>(join(runDir(experiment, runId), "job_pid.json"));
  let pid = state.executor_pid;
  let token = state.executor_token;
  let started = state.started_at_ms;
  if (sidecar) {
    if (sidecar.run_id != null && String(sidecar.run_id) !== runId) {
      return {verdict: "UNKNOWN", reason: "STATE_CONTRADICTION", pid,
        creation_ms: null, detail: "job_pid.json pertenece a otra ejecucion"};
    }
    if (sidecar.token != null && token !== null && String(sidecar.token) !== token) {
      return {verdict: "UNKNOWN", reason: "STATE_CONTRADICTION", pid,
        creation_ms: null, detail: "token de job_pid.json no coincide con el estado"};
    }
    if (typeof sidecar.pid === "number" && pid !== null && sidecar.pid !== pid) {
      return {verdict: "UNKNOWN", reason: "STATE_CONTRADICTION", pid,
        creation_ms: null, detail: "PID de job_pid.json no coincide con el estado"};
    }
    if (pid === null && typeof sidecar.pid === "number") pid = sidecar.pid;
    if (token === null && sidecar.token != null) token = String(sidecar.token);
    if (started === null && typeof sidecar.started_at_ms === "number") {
      started = sidecar.started_at_ms as number;
    }
  }
  if (pid === null || !Number.isSafeInteger(pid) || pid <= 0
      || token === null || !TOKEN_SAFE.test(token)
      || started === null || !Number.isSafeInteger(started) || started <= 0) {
    return {verdict: "UNKNOWN", reason: "IDENTITY_INCOMPLETE", pid,
      creation_ms: null, detail: "faltan PID, token o inicio verificables"};
  }
  const evidence = inspectProcess(pid);
  if (!evidence.alive) {
    return {verdict: "GONE", reason: "PROCESS_GONE", pid, creation_ms: null};
  }
  if (evidence.creation_ms === null || evidence.command_line === null) {
    return {verdict: "UNKNOWN", reason: "EVIDENCE_INCOMPLETE", pid,
      creation_ms: evidence.creation_ms,
      detail: `sin evidencia suficiente del proceso (${evidence.source})`};
  }
  if (evidence.creation_ms < started - PROC_CREATION_SKEW_MS
      || evidence.creation_ms > started + PROC_CREATION_FUTURE_MS) {
    return {verdict: "UNKNOWN", reason: "PID_INSTANCE_MISMATCH", pid,
      creation_ms: evidence.creation_ms,
      detail: "la instancia del PID no corresponde al inicio de la ejecucion"};
  }
  const argv = argvOf(evidence.command_line);
  if (!containsFlagValue(argv, "--executor-token", token)
      || !containsFlagValue(argv, "--run-id", runId)) {
    return {verdict: "UNKNOWN", reason: "PROCESS_NOT_OWNED", pid,
      creation_ms: evidence.creation_ms,
      detail: "el proceso vivo no posee el token/run_id de esta ejecucion"};
  }
  return {verdict: "ACTIVE_VERIFIED", reason: "VERIFIED", pid,
    creation_ms: evidence.creation_ms};
}

// Un proceso ajeno o reutilizado NO puede ser el ejecutor de una ejecucion
// TERMINAL: la instancia original ya no existe. Eso permite cerrar el lock sin
// confundir "no puedo verificar" (UNKNOWN, se conserva) con "el proceso es otro".
function terminalExecutorGone(ev: ExecutorEvidence): boolean {
  return ev.verdict === "GONE"
    || ev.reason === "PROCESS_NOT_OWNED" || ev.reason === "PID_INSTANCE_MISMATCH";
}

function hasJobPid(experiment: string, runId: string): boolean {
  return existsSync(join(runDir(experiment, runId), "job_pid.json"));
}

// Reconciliacion de un estado activo (pendiente/ejecutando) SIN relanzar:
//  - proceso verificado -> se mantiene (TIMEOUT si excede presupuesto, sin matar);
//  - proceso ausente -> fallido PROCESS_INTERRUPTED;
//  - identidad incompleta/ajena/reutilizada -> fallido PROCESS_IDENTITY_UNKNOWN.
// El lock NO se libera aqui: su ciclo de vida se resuelve en startJob, que
// conserva la exclusion cuando la identidad es incierta.
function reconcile(experiment: BacktestExperiment, state: BacktestJobState,
                   write: boolean): BacktestJobState {
  if (state.status !== "pendiente" && state.status !== "ejecutando") return state;
  const now = Date.now();
  const path = join(runDir(experiment, state.run_id), "job_state.json");
  const age = now - (state.updated_at_ms ?? state.started_at_ms ?? now);
  // Ventana de arranque: el BFF escribe "pendiente" y lanza el proceso justo
  // despues. Un estado pendiente sin PID no es todavia evidencia de fallo.
  if (state.status === "pendiente" && state.executor_pid === null
      && age < EXECUTOR_START_GRACE_MS && !hasJobPid(experiment, state.run_id)) {
    return state;
  }
  const ev = executorEvidence(experiment, state.run_id, state);
  // Compare-and-set: la evidencia del sistema operativo puede tardar cientos
  // de ms. Si mientras tanto el ejecutor escribio un estado mas nuevo (p. ej.
  // "completado"), NO se debe sobrescribir con una conclusion ya obsoleta.
  const persist = (next: BacktestJobState): BacktestJobState => {
    if (write) {
      const fresh = readRunStatePure(experiment, state.run_id);
      if (!fresh || fresh.status !== state.status
          || fresh.updated_at_ms !== state.updated_at_ms
          || fresh.started_at_ms !== state.started_at_ms) {
        return fresh ?? state;
      }
      writeJsonAtomic(path, next);
    }
    return next;
  };
  if (ev.verdict === "GONE") {
    return persist({...state, status: "fallido", error: "PROCESS_INTERRUPTED",
      detail: "El proceso de backtest ya no esta activo y no dejo estado final. Reintente la ejecucion.",
      updated_at_ms: now, identity: "UNKNOWN"});
  }
  // El presupuesto es una condicion TEMPORAL, no una prueba sobre el proceso.
  // Se declara TIMEOUT sin matar nada y sin afirmar que el ejecutor termino;
  // la exclusion se conserva en startJob mientras no haya evidencia de salida.
  const basis = state.started_at_ms ?? state.updated_at_ms;
  if (basis !== null && now - basis > BACKTEST_BUDGET_MS) {
    return persist({...state, status: "fallido", error: "TIMEOUT",
      detail: `La ejecucion supero el presupuesto de ${BACKTEST_BUDGET_MS} ms sin cerrar estado. `
        + "No se mata ningun proceso ni se lanza otro mientras su identidad no este resuelta.",
      updated_at_ms: now, identity: ev.verdict === "ACTIVE_VERIFIED" ? "verified" : "UNKNOWN"});
  }
  if (ev.verdict !== "ACTIVE_VERIFIED") {
    return persist({...state, status: "fallido", error: "PROCESS_IDENTITY_UNKNOWN",
      detail: `No se puede verificar que el proceso de la ejecucion siga activo (${ev.reason}). `
        + "No se relanza automaticamente ni se mata ningun proceso.",
      updated_at_ms: now, identity: "UNKNOWN"});
  }
  return {...state, identity: "verified"};
}

// Estado persistido de la ejecucion ACTUAL del experimento (o null si no hay).
export function readJobState(experiment: BacktestExperiment): BacktestJobState | null {
  const ptr = readPointer(experiment);
  if (!ptr) return null;
  return readRunState(experiment, ptr.run_id);
}

// Estado de una ejecucion concreta por run_id (para resultados vinculados).
export function readRunState(experiment: BacktestExperiment, runId: string): BacktestJobState | null {
  const state = readRunStatePure(experiment, runId);
  if (!state) return null;
  if (state.status === "pendiente" || state.status === "ejecutando") {
    return reconcile(experiment, state, true);
  }
  return state;
}

export function currentRunId(experiment: BacktestExperiment): string | null {
  return readPointer(experiment)?.run_id ?? null;
}

// --- Seccion critica entre procesos ----------------------------------------

// Resultado de la inspección de liveness de un PID.
//   - "alive": el proceso existe y puede señalarse.
//   - "gone": SOLO ESRCH acredita que el proceso no existe (ausencia verificada).
//   - "epperm": el proceso existe pero no tenemos permisos para señalarlo.
//   - "error": cualquier otro error de inspección (no es prueba de muerte).
export type PidLiveness =
  | {kind: "alive"}
  | {kind: "gone"}
  | {kind: "epperm"}
  | {kind: "error"; code?: string};

// Identidad verificable y ÚNICA de una adquisición del guard. El token es un
// identificador aleatorio generado en el momento de adquirirlo: dos
// adquisiciones del mismo proceso (mismo PID) tienen tokens distintos, de modo
// que una liberación antigua nunca retira el guard de una adquisición
// posterior aunque reutilice el PID.
export type Guard = {
  path: string;
  pid: number;
  acquired_at_ms: number;
  token: string;
};

function newGuardToken(): string {
  return randomBytes(16).toString("hex");
}

function inspectPidLiveness(pid: number): PidLiveness {
  if (!Number.isSafeInteger(pid) || pid <= 0) {
    return {kind: "error", code: "INVALID_PID"}; // PID inválido: no autoriza retirada
  }
  try {
    process.kill(pid, 0); // senal 0: solo comprueba existencia, nunca mata
    return {kind: "alive"};
  } catch (e) {
    const code = (e as NodeJS.ErrnoException).code;
    if (code === "ESRCH") return {kind: "gone"}; // SOLO ESRCH acredita ausencia
    if (code === "EPERM") return {kind: "epperm"}; // existe, sin permisos: no es muerto
    // Cualquier otro error: no es prueba de muerte, conserva exclusión.
    return {kind: "error", code};
  }
}

// Resultado de la adquisición del guard. Nunca se borra un guard huérfano
// automáticamente: se conserva la exclusión y se devuelve una causa explícita.
export type AcquireResult =
  | {kind: "acquired"; guard: Guard}
  | {kind: "rejected"; reason: "OWNER_ALIVE" | "GUARD_ORPHANED" | "IDENTITY_UNCERTAIN"};

export function acquireGuard(experiment: string): AcquireResult {
  mkdirSync(experimentDir(experiment), {recursive: true});
  const path = guardPath(experiment);
  const token = newGuardToken();
  const acquired_at_ms = Date.now();
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const fd = openSync(path, "wx"); // O_EXCL: falla si ya existe
      try {
        // Una única identidad coherente entre lo escrito y el handle devuelto.
        writeSync(fd, JSON.stringify({pid: process.pid, acquired_at_ms, token}));
      } finally {
        closeSync(fd);
      }
      return {kind: "acquired", guard: {path, pid: process.pid, acquired_at_ms, token}};
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "EEXIST") throw e;
      // Un guard existente NO se retira por antigüedad ni por propietario
      // muerto: eso crearía la carrera lectura→borrado (A y B leen el mismo
      // guard huérfano, uno lo elimina y el otro borra el guard nuevo).
      // Se conserva el guard y se devuelve una causa explícita.
      // El archivo existe (estamos en EEXIST); si no se parsea como JSON es
      // identidad incierta: fail-closed, se conserva la exclusión.
      let owner: {pid?: unknown; acquired_at_ms?: unknown; token?: unknown} |
        null = null;
      try {
        owner = JSON.parse(readFileSync(path, "utf8"));
      } catch {
        return {kind: "rejected", reason: "IDENTITY_UNCERTAIN"}; // ilegible: no se toca
      }
      const ownerPid =
        typeof owner?.pid === "number" ? owner.pid : null;
      const ownerToken = typeof owner?.token === "string" ? owner.token : null;
      // Identidad completa requerida ANTES de consultar liveness: sin token
      // (o sin PID válido) no podemos verificar propiedad aunque el PID esté
      // vivo -> evidencia insuficiente, conserva exclusión (D2).
      if (ownerPid === null || !Number.isSafeInteger(ownerPid)
          || ownerPid <= 0 || ownerToken === null || ownerToken.length === 0) {
        return {kind: "rejected", reason: "IDENTITY_UNCERTAIN"};
      }
      const liveness = inspectPidLiveness(ownerPid);
      if (liveness.kind === "alive") {
        // El propietario sigue activo (aunque el guard supere los 30 s): no se
        // rompe la exclusión, la segunda solicitud no adquiere (A).
        return {kind: "rejected", reason: "OWNER_ALIVE"};
      }
      if (liveness.kind === "epperm" || liveness.kind === "error") {
        // EPERM (existe, sin permisos) o error de inspección: nunca es prueba
        // de muerte. Se conserva la exclusión y se reporta causa explícita (D3/D5).
        return {kind: "rejected", reason: "IDENTITY_UNCERTAIN"};
      }
      // liveness.kind === "gone": propietario muerto. Se CONSERVA el guard
      // huérfano (no se borra automáticamente) y se reporta GUARD_ORPHANED.
      // La recuperación solo puede hacerse por mantenimiento con todos los
      // participantes detenidos, nunca automáticamente entre procesos (C).
      return {kind: "rejected", reason: "GUARD_ORPHANED"};
    }
  }
  return {kind: "rejected", reason: "IDENTITY_UNCERTAIN"};
}

export function releaseGuard(guard: Guard | null): void {
  if (!guard) return;
  try {
    const current = readJson<{
      pid?: unknown; acquired_at_ms?: unknown; token?: unknown;
    }>(guard.path);
    const currentPid =
      typeof current?.pid === "number" ? current.pid : null;
    const currentToken = typeof current?.token === "string" ? current.token : null;
    const currentAcquired =
      typeof current?.acquired_at_ms === "number" ? current.acquired_at_ms : null;
    // Liberación condicionada por identidad COMPLETA de la adquisición:
    // mismo PID, mismo token y mismo acquired_at_ms. Una liberación antigua
    // de otra adquisición (incluso con PID reutilizado) nunca borra el guard
    // de una adquisición posterior (B).
    if (
      currentPid === null || currentPid !== guard.pid ||
      currentToken === null || currentToken !== guard.token ||
      currentAcquired === null || currentAcquired !== guard.acquired_at_ms
    ) {
      return;
    }
    rmSync(guard.path, {force: true});
  } catch { /* ignore */ }
}

// --- Exclusion entre procesos ----------------------------------------------
// Try-lock con creacion EXCLUSIVA (O_EXCL). Devuelve true si se obtuvo.
type LockInfo = {
  run_id: string; pid: number | null; token: string | null;
  acquired_at_ms: number; host: string;
};

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
// Libera UNICAMENTE el lock que coincide con la ejecucion y token esperados.
// Nunca borra el lock de una ejecucion sucesora. Debe llamarse dentro del
// guard (o mediante releaseLockFor, que lo adquiere).
function releaseLockIfMatches(experiment: string, runId: string, token: string | null): boolean {
  const current = readLock(experiment);
  if (!current) return false;
  if (current.run_id !== runId) return false;
  if (token !== null && current.token !== null && current.token !== token) return false;
  try {
    rmSync(lockPath(experiment), {force: true});
    return true;
  } catch {
    return false;
  }
}

/** Libera el lock solo si pertenece a (runId, token). API de ciclo de vida. */
export function releaseLockFor(
  experiment: BacktestExperiment, runId: string, token: string | null,
): boolean {
  const result = acquireGuard(experiment);
  if (result.kind !== "acquired") return false;
  const guard = result.guard;
  try {
    return releaseLockIfMatches(experiment, runId, token);
  } finally {
    releaseGuard(guard);
  }
}

// Decide si el lock conserva la exclusion. Devuelve hold=false SOLO con
// evidencia suficiente de que el ejecutor de esa ejecucion ya no existe.
function lockDisposition(experiment: BacktestExperiment, lock: LockInfo):
  {hold: boolean; reason: string; state: BacktestJobState | null; evidence: ExecutorEvidence | null} {
  if (typeof lock.run_id !== "string" || !TOKEN_SAFE.test(lock.run_id)) {
    // Lock ilegible: identidad incierta -> fail-closed.
    return {hold: true, reason: "LOCK_UNREADABLE", state: null, evidence: null};
  }
  const state = readRunStatePure(experiment, lock.run_id);
  if (!state) {
    // No hay ejecucion asociada. Bajo el guard, la ventana lock->estado ya
    // termino: no pudo lanzarse ningun ejecutor sin estado.
    return {hold: false, reason: "NO_STATE", state: null, evidence: null};
  }
  if (lock.run_id !== state.run_id) {
    return {hold: true, reason: "LOCK_STATE_RUN_MISMATCH", state, evidence: null};
  }
  if (lock.token !== null && state.executor_token !== null
      && lock.token !== state.executor_token) {
    return {hold: true, reason: "LOCK_STATE_TOKEN_MISMATCH", state, evidence: null};
  }
  const evidence = executorEvidence(experiment, lock.run_id, state);
  const active = state.status === "pendiente" || state.status === "ejecutando";
  // TIMEOUT no afirma que el proceso haya terminado: solo que se agoto el
  // presupuesto. Por eso exige evidencia de AUSENCIA (GONE) para liberar; un
  // PID ajeno o reutilizado no basta como prueba de salida en este caso.
  const timedOut = state.error === "TIMEOUT";
  if (!active) {
    if (timedOut ? evidence.verdict === "GONE" : terminalExecutorGone(evidence)) {
      return {hold: false, reason: "TERMINAL_EXECUTOR_GONE", state, evidence};
    }
    return {hold: true, reason: `TERMINAL_${evidence.reason}`, state, evidence};
  }
  if (evidence.verdict === "ACTIVE_VERIFIED") {
    return {hold: true, reason: "EXECUTOR_ACTIVE", state, evidence};
  }
  if (evidence.verdict === "GONE") {
    return {hold: false, reason: "EXECUTOR_GONE", state, evidence};
  }
  if (state.status === "pendiente" && state.executor_pid === null
      && !hasJobPid(experiment, state.run_id)
      && Date.now() - (state.updated_at_ms ?? state.started_at_ms ?? Date.now())
        > EXECUTOR_START_GRACE_MS) {
    // Ventana de arranque agotada sin PID ni sidecar: el ejecutor, si llego a
    // existir, habria escrito su identidad. Se cierra como pendiente abandonada.
    return {hold: false, reason: "PENDING_ABANDONED", state, evidence};
  }
  return {hold: true, reason: `EXECUTOR_${evidence.reason}`, state, evidence};
}

// Single-flight ENTRE PROCESOS: si hay un lock con ejecutor activo o identidad
// incierta, no se lanza otra tarea. Un lock terminal cuyo ejecutor ya no
// existe se libera para permitir una nueva solicitud EXPLICITA.
export type StartResult = {started: boolean; state: BacktestJobState | null; error?: string;
  run_id?: string};

export function startJob(experiment: BacktestExperiment): StartResult {
  mkdirSync(experimentDir(experiment), {recursive: true});
  const result = acquireGuard(experiment);
  if (result.kind !== "acquired") {
    return {started: false, state: readJobState(experiment), error: "GUARD_BUSY"};
  }
  const guard = result.guard;
  try {
    const lock = readLock(experiment);
    if (lock) {
      const disp = lockDisposition(experiment, lock);
      if (disp.hold) {
        return {started: false, state: readRunState(experiment, lock.run_id),
          error: "ALREADY_RUNNING", run_id: lock.run_id};
      }
      // Cerrar la ejecucion abandonada sin relanzarla automaticamente. Se
      // relee el estado: el ejecutor pudo cerrarlo mientras se evaluaba el lock.
      const fresh = disp.state ? readRunStatePure(experiment, disp.state.run_id) : null;
      if (fresh && (fresh.status === "pendiente" || fresh.status === "ejecutando")) {
        const failed: BacktestJobState = {...fresh, status: "fallido",
          error: fresh.status === "pendiente" ? "PENDING_ABANDONED" : "PROCESS_INTERRUPTED",
          detail: "La ejecucion anterior no dejo estado final verificable; no se relanza automaticamente.",
          updated_at_ms: Date.now(), identity: "UNKNOWN"};
        writeJsonAtomic(join(runDir(experiment, fresh.run_id), "job_state.json"), failed);
      }
      releaseLockIfMatches(experiment, lock.run_id, lock.token);
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
      return {started: false, state, error: "ALREADY_RUNNING", run_id: winner?.run_id};
    }

    mkdirSync(runDir(experiment, runId), {recursive: true});
    const pending: BacktestJobState = {
      job_id: runId, run_id: runId, experiment_id: experiment, status: "pendiente",
      error: null, detail: null, started_at_ms: now, updated_at_ms: now,
      duration_ms: null, n_trades: null, reconciliation_ok: null,
      executor_token: token, executor_pid: null, executor_version: null,
      result_hashes: null, identity: "UNKNOWN",
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
      releaseLockIfMatches(experiment, runId, token);
      return {started: false, state: failed, error: "SPAWN_FAILED", run_id: runId};
    }

    // Error asincrono del spawn: se persiste, no se pierde. La liberacion solo
    // afecta a ESTA ejecucion (nunca al lock de una sucesora).
    child.on("error", (err: Error) => {
      const failed: BacktestJobState = {...pending, status: "fallido", error: "SPAWN_FAILED",
        detail: `Fallo asincrono al iniciar el proceso: ${err.message}`, updated_at_ms: Date.now()};
      try { writeJsonAtomic(join(runDir(experiment, runId), "job_state.json"), failed); } catch { /* ignore */ }
      try { releaseLockFor(experiment, runId, token); } catch { /* ignore */ }
    });

    if (!child.pid) {
      const failed: BacktestJobState = {...pending, status: "fallido", error: "SPAWN_FAILED",
        detail: "No se pudo iniciar el proceso de backtest (sin PID).", updated_at_ms: Date.now()};
      writeJsonAtomic(join(runDir(experiment, runId), "job_state.json"), failed);
      releaseLockIfMatches(experiment, runId, token);
      return {started: false, state: failed, error: "SPAWN_FAILED", run_id: runId};
    }

    const launched: BacktestJobState = {...pending, status: "ejecutando",
      executor_pid: child.pid, updated_at_ms: Date.now()};
    // job_pid.json conserva la identidad declarada; la prueba de propiedad es
    // la evidencia del sistema operativo, no este archivo.
    writeJsonAtomic(join(runDir(experiment, runId), "job_pid.json"),
      {pid: child.pid, run_id: runId, token, started_at_ms: now});
    writeJsonAtomic(join(runDir(experiment, runId), "job_state.json"), launched);
    child.unref();
    return {started: true, state: launched, run_id: runId};
  } finally {
    releaseGuard(guard);
  }
}

// --- Resultados vinculados a la ejecucion ---------------------------------
export type BacktestResults = {
  experiment_id: string;
  run_id: string;
  summary: Record<string, unknown>;
  trades: Record<string, unknown>[];
  reconciliation: Record<string, unknown>;
  available: true;
  result_hashes: Record<string, string>;
};

function sha256File(path: string): string | null {
  try { return createHash("sha256").update(readFileSync(path)).digest("hex"); }
  catch { return null; }
}

export type ResultsUnavailable = {available: false;
  status: BacktestJobStatus | "sin_ejecutar"; error: string; run_id?: string;
  detail?: string};

const RESULT_FILES = ["summary.json", "trades.json", "reconciliation.json"] as const;

function unavailable(
  runId: string, error: string, detail?: string,
  status: BacktestJobStatus = "fallido",
): ResultsUnavailable {
  return {available: false, status, run_id: runId, error, detail};
}

function recordOf(v: unknown): Record<string, unknown> | null {
  return typeof v === "object" && v !== null && !Array.isArray(v)
    ? (v as Record<string, unknown>) : null;
}

// Lee resultados de UNA ejecucion concreta y VERIFICA, antes de servir:
//  - que los tres hashes fueron DECLARADOS por el ejecutor (completos y validos);
//  - que coinciden con los bytes actuales (nunca se recalculan como si fueran
//    los declarados);
//  - el esquema minimo de los artefactos y su identidad de ejecucion/experimento.
// Cualquier duda falla cerrado y NUNCA sirve resultados parciales o alterados.
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
  // Un estado COMPLETADO con artefactos no acreditables no es "fallido": es un
  // resultado no disponible. Se conserva el estado real y se declara la causa.
  const fail = (error: string, detail?: string) =>
    unavailable(runId, error, detail, "completado");
  const declaredRaw = state?.result_hashes;
  if (!recordOf(declaredRaw)) {
    return fail("RESULT_HASHES_MISSING",
      "El estado completado no declara hashes de resultados; no se puede acreditar integridad.");
  }
  const declared = declaredRaw as Record<string, unknown>;
  for (const name of RESULT_FILES) {
    const value = declared[name];
    if (typeof value !== "string" || value.length === 0) {
      return fail("RESULT_HASHES_INCOMPLETE",
        `Falta el hash declarado de ${name}.`);
    }
    if (!HASH_RE.test(value)) {
      return fail("RESULT_HASHES_INVALID",
        `El hash declarado de ${name} no es un sha256 valido.`);
    }
  }
  const verified: Record<string, string> = {};
  for (const name of RESULT_FILES) {
    const p = join(dir, name);
    if (!existsSync(p)) return fail("RESULT_INCOMPLETE", `Falta ${name}.`);
    const actual = sha256File(p);
    if (!actual) return fail("RESULT_UNREADABLE", `No se pudo leer ${name}.`);
    if (declared[name] !== actual) {
      return fail("RESULT_INTEGRITY_FAILED",
        `El contenido de ${name} no coincide con el hash declarado.`);
    }
    verified[name] = actual;
  }

  const summary = recordOf(readJson(join(dir, "summary.json")));
  const tradesDoc = recordOf(readJson(join(dir, "trades.json")));
  const reconciliation = recordOf(readJson(join(dir, "reconciliation.json")));
  if (!summary || !tradesDoc || !reconciliation) {
    return fail("RESULT_INVALID_JSON",
      "Algun artefacto no es un objeto JSON parseable.");
  }
  // Identidad ANTES del esquema: un artefacto sin identidad no acredita nada,
  // aunque su forma sea parcialmente valida.
  for (const [name, doc] of [["summary.json", summary],
    ["trades.json", tradesDoc], ["reconciliation.json", reconciliation]] as const) {
    if (doc.run_id == null || doc.experiment_id == null) {
      return fail("RESULT_IDENTITY_MISSING",
        `${name} no declara run_id/experiment_id; re-ejecute el experimento.`);
    }
    if (doc.run_id !== runId || doc.experiment_id !== experiment) {
      return fail("RESULT_IDENTITY_MISMATCH",
        `${name} pertenece a otra ejecucion o experimento.`);
    }
  }
  const tradeRows = tradesDoc.trades;
  if (!Array.isArray(tradeRows) || tradeRows.some((t) => recordOf(t) === null)) {
    return fail("RESULT_SCHEMA_INVALID",
      "trades.json no contiene una lista valida de operaciones.");
  }
  if (!Array.isArray(summary.cells)) {
    return fail("RESULT_SCHEMA_INVALID", "summary.json no contiene celdas.");
  }
  if (typeof reconciliation.ok !== "boolean" || !Array.isArray(reconciliation.cells)) {
    return fail("RESULT_SCHEMA_INVALID",
      "reconciliation.json no tiene la forma esperada (ok + cells).");
  }
  if (typeof tradesDoc.n_trades === "number" && tradesDoc.n_trades !== tradeRows.length) {
    return fail("RESULT_SCHEMA_INVALID",
      "trades.json declara un numero de operaciones distinto del listado.");
  }
  if (typeof summary.n_trades_total === "number" && summary.n_trades_total !== tradeRows.length) {
    return fail("RESULT_SCHEMA_INVALID",
      "summary.json y trades.json no describen el mismo conjunto de operaciones.");
  }
  if (reconciliation.ok !== true
      || (summary.reconciliation_ok !== undefined && summary.reconciliation_ok !== true)) {
    return fail("RESULT_RECONCILIATION_FAILED",
      "La reconciliacion con el motor no es correcta; el resultado no se declara integro.");
  }
  return {experiment_id: experiment, run_id: runId, summary,
    trades: tradeRows as Record<string, unknown>[], reconciliation,
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
// cache de otra, y un artefacto cacheado solo se sirve si prueba pertenecer a
// los resultados verificados de ESTA ejecucion.
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

function replayMismatch(
  artifact: unknown, req: ReplayLinkRequest, runId: string, tradesHash: string,
): string | null {
  const a = recordOf(artifact);
  if (!a) return "ARTIFACT_NOT_OBJECT";
  if (a.artifact_version !== "PAPER-LAB-REPLAY-V1" || a.schema_version !== 1) {
    return "ARTIFACT_VERSION";
  }
  if (a.backtest_run_id !== runId) return "RUN_ID";
  const event = recordOf(a.event);
  const trade = recordOf(a.trade);
  if (!event || !trade) return "EVENT_OR_TRADE";
  if (event.event_id !== req.event_id) return "EVENT_ID";
  if (trade.group !== req.group || trade.segment !== req.segment) return "GROUP_OR_SEGMENT";
  if (typeof a.replay_id !== "string"
      || !a.replay_id.endsWith(`-${req.scale.toFixed(1)}x`)) return "SCALE";
  const hashes = recordOf(recordOf(a.provenance)?.source_hashes);
  if (!hashes) return "SOURCE_HASHES";
  return Object.values(hashes).some((v) => v === tradesHash) ? null : "TRADES_HASH";
}

function replayMatches(
  artifact: unknown, req: ReplayLinkRequest, runId: string, tradesHash: string,
): boolean {
  return replayMismatch(artifact, req, runId, tradesHash) === null;
}

function sameTrade(artifact: unknown, row: Record<string, unknown>): boolean {
  const trade = recordOf(recordOf(artifact)?.trade);
  if (!trade) return false;
  for (const key of ["entry_ms", "exit_ms", "net_pnl", "fees", "funding"]) {
    if (typeof trade[key] !== "number" || typeof row[key] !== "number") return false;
    if (Math.abs((trade[key] as number) - (row[key] as number)) > 1e-9) return false;
  }
  return true;
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
  const row = results.trades.find((t) =>
    String(t.event_id) === req.event_id && String(t.group) === req.group
    && String(t.segment) === req.segment && Number(t.scale) === Number(req.scale));
  if (!row) return {ok: false, error: "TARGET_NOT_IN_RUN",
    detail: "La operacion no pertenece a los resultados de esta ejecucion.", run_id: runId};

  const dir = runDir(req.experiment, runId);
  const tradesHash = results.result_hashes["trades.json"] ?? "no-hash";
  const out = join(dir, replayArtifactName(req, runId, tradesHash));
  const existing = readJson<unknown>(out);
  if (existing && replayMatches(existing, req, runId, tradesHash)
      && sameTrade(existing, row)) {
    return {ok: true, artifact: existing, run_id: runId, cached: true};
  }

  // Escritura atomica: dos solicitudes concurrentes no producen archivo parcial.
  const tmp = `${out}.tmp.${process.pid}.${randomBytes(4).toString("hex")}`;
  const r = spawnSync(PY, ["scripts/build_paper_lab_replay.py",
    "--trades-json", join(dir, "trades.json"),
    "--target-event-id", req.event_id,
    "--target-group", req.group,
    "--target-segment", req.segment,
    "--target-scale", String(req.scale),
    "--run-id", runId,
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
  if (!replayMatches(artifact, req, runId, tradesHash) || !sameTrade(artifact, row)) {
    try { rmSync(tmp, {force: true}); } catch { /* ignore */ }
    return {ok: false, error: "REPLAY_UNVERIFIED", run_id: runId,
      detail: `El artefacto generado no prueba pertenecer a estos resultados `
        + `(${replayMismatch(artifact, req, runId, tradesHash) ?? "TRADE_MISMATCH"}).`};
  }
  try { renameSync(tmp, out); } catch {
    // Otra solicitud concurrente gano: usar SOLO si su artefacto es valido.
    const raced = readJson<unknown>(out);
    if (raced && replayMatches(raced, req, runId, tradesHash) && sameTrade(raced, row)) {
      return {ok: true, artifact: raced, run_id: runId, cached: true};
    }
    try { rmSync(tmp, {force: true}); } catch { /* ignore */ }
    return {ok: false, error: "REPLAY_UNVERIFIED", run_id: runId};
  }
  return {ok: true, artifact, run_id: runId, cached: false};
}

// --- Retencion acotada -----------------------------------------------------
// Conserva las ejecuciones mas recientes por experimento y NUNCA elimina una
// ejecucion que pueda seguir activa. Cada candidato se comprueba uno a uno con
// evidencia del proceso; ante duda se conserva y se reporta. Report-only no
// escribe estados ni elimina archivos. `_legacy` se preserva por contrato.
export const BACKTEST_RETENTION_RUNS = 5;

export type RetentionSkipped = {run: string; reason: string};

function experimentDirs(dir: string): string[] {
  return readdirSync(dir).filter((e) => {
    if (e.startsWith("_")) return false; // _legacy y evidencia historica
    if (!/^[a-z0-9][a-z0-9-]*$/i.test(e)) return false;
    try { return statSync(join(dir, e)).isDirectory(); } catch { return false; }
  });
}

function listRunDirs(base: string): string[] {
  return readdirSync(base).filter((r) => {
    if (!RUN_ID_RE.test(r)) return false;
    try { return statSync(join(base, r)).isDirectory(); } catch { return false; }
  }).sort(); // orden lexicografico ~ cronologico por el timestamp del id
}

export function retentionReport(apply = false): {
  dir: string; exists: boolean; bytes: number; files: number; runs: number;
  removed: string[]; would_remove: string[]; skipped: RetentionSkipped[];
  preserved: string[];
} {
  const dir = resultsDir();
  const removed: string[] = [], would_remove: string[] = [], skipped: RetentionSkipped[] = [];
  const preserved: string[] = [];
  if (!existsSync(dir)) {
    return {dir, exists: false, bytes: 0, files: 0, runs: 0, removed,
      would_remove, skipped, preserved};
  }
  let bytes = 0, files = 0, runs = 0;
  if (existsSync(join(dir, "_legacy"))) preserved.push("_legacy");
  for (const exp of experimentDirs(dir)) {
    const base = join(dir, exp);
    const runIds = listRunDirs(base);
    runs += runIds.length;
    for (const r of runIds) {
      const rd = join(base, r);
      for (const f of readdirSync(rd)) {
        try { const st = statSync(join(rd, f)); if (st.isFile()) { bytes += st.size; files += 1; } }
        catch { /* ignore */ }
      }
    }
    if (runIds.length <= BACKTEST_RETENTION_RUNS) continue;
    const keep = new Set(runIds.slice(-BACKTEST_RETENTION_RUNS));
    const candidates = runIds.filter((r) => !keep.has(r));
    if (candidates.length === 0) continue;

    let guard: Guard | null = null;
    if (apply) {
      const result = acquireGuard(exp);
      if (result.kind !== "acquired") {
        skipped.push({run: `${exp}/*`, reason: "GUARD_BUSY"});
        continue;
      }
      guard = result.guard;
    }
    try {
      const pointer = readJson<{run_id?: unknown}>(join(base, "current.json"));
      const current = pointer && typeof pointer.run_id === "string" ? pointer.run_id : null;
      const lock = readJson<LockInfo>(join(base, "run.lock"));
      for (const r of candidates) {
        const state = readRunStatePure(exp as BacktestExperiment, r);
        if (!state) {
          skipped.push({run: `${exp}/${r}`, reason: "NO_VERIFIABLE_STATE"});
          continue;
        }
        if (current === r) {
          skipped.push({run: `${exp}/${r}`, reason: "CURRENT_POINTER"});
          continue;
        }
        if (lock && lock.run_id === r) {
          // El lock se resuelve en la proxima solicitud explicita; no se borra
          // el directorio que aun referencia.
          skipped.push({run: `${exp}/${r}`, reason: "LOCK_REFERENCE"});
          continue;
        }
        const ev = executorEvidence(exp as BacktestExperiment, r, state);
        const active = state.status === "pendiente" || state.status === "ejecutando";
        // Solo se borra con evidencia suficiente de inactividad:
        //  - estado activo: el proceso registrado debe estar definitivamente ausente;
        //  - estado terminal: ademas, un PID ajeno/reutilizado prueba que la
        //    instancia original ya no existe.
        const deletable = active
          ? ev.verdict === "GONE"
          : terminalExecutorGone(ev);
        if (!deletable) {
          skipped.push({run: `${exp}/${r}`,
            reason: ev.verdict === "ACTIVE_VERIFIED" ? "EXECUTOR_ACTIVE" : `IDENTITY_${ev.reason}`});
          continue;
        }
        if (!apply) {
          would_remove.push(`${exp}/${r}`);
          continue;
        }
        try {
          rmSync(join(base, r), {recursive: true, force: true});
          removed.push(`${exp}/${r}`);
        } catch {
          skipped.push({run: `${exp}/${r}`, reason: "REMOVE_FAILED"});
        }
      }
    } finally {
      releaseGuard(guard);
    }
  }
  return {dir, exists: true, bytes, files, runs, removed, would_remove, skipped, preserved};
}
