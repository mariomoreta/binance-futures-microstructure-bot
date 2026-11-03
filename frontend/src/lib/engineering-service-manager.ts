// ---------------------------------------------------------------------------
// Gestor del SERVICIO de sesiones de ingeniería (solo para el BFF).
//
// Arranca la instancia canónica del proyecto —el controlador canónico ya
// existente `scripts/engineering_session_service.py` (contrato
// engineering-session-service/v1)— y verifica su identidad por pid-file +
// /health. Nada se lanza por GET ni por abrir la página; el arranque solo
// ocurre por POST explícito con las guardias de origen del BFF. NUNCA
// reutiliza ni detiene un PID desconocido: el alcance de parada del gestor
// es exclusivamente el proceso que él mismo generó (child.kill()).
// ---------------------------------------------------------------------------

import { spawn, spawnSync } from "node:child_process";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import http from "node:http";

export type EngineeringServiceState =
  | "down"          // sin escucha verificable
  | "unidentified"  // hay algo en el puerto, pero la identidad no es verificable
  | "ready";        // /health responde y coincide con el pid-file

export interface EngineeringServiceStatus {
  state: EngineeringServiceState;
  service?: string | null;
  engine_version?: string | null;
  pid?: number | null;
  port?: number | null;
  cadence_ms?: number | null;
  sessions_dir?: string | null;
  market_url?: string | null;
  detail?: string | null;
}

export interface StartServiceResult {
  ok: boolean;
  pid?: number;
  port?: number;
  sessions_dir?: string;
  already?: boolean;
  reconciled?: boolean;
  /** run_id usado cuando se arranca en modo public; undefined en modo local. */
  runIdFromService?: string | null;
  error?: string;
  detail?: string;
}

export type ClockSource = "local" | "public";

export interface StartServiceOptions {
  /** Fuente del reloj: "local" (default) o "public". */
  clockSource?: ClockSource;
  /** run_id estable de la corrida (obligatorio en modo public). */
  runId?: string | null;
  /** URL del endpoint de tiempo para sincronización pública (pruebas loopback). */
  publicFetchUrl?: string | null;
  /** Tope de intentos /time para sincronización pública. */
  publicMaxRequests?: number | null;
  /** Puesto de mercado del servicio (loopback). */
  marketUrl?: string | null;
}

interface PidFileInfo {
  pid: number;
  port: number;
  host: string;
  service: string;
}

const SERVICE_NAME = "engineering-session-service/v1";

// --- configuración (env con defaults del proyecto) --------------------------
// serviceRoot/pythonExecutable se exportan: el gestor de la DEMOSTRACIÓN
// local (local-demo-manager.ts) reutiliza la misma raíz canónica y el mismo
// intérprete, sin duplicar configuración.

export function serviceRoot(): string {
  // Raíz canónica del repo (padre del frontend servido), con sobreescritura
  // opcional para entornos de prueba.
  const env = process.env.ENGINEERING_SERVICE_ROOT;
  if (env) return path.resolve(env);
  // process.cwd() es el directorio frontend al correr `next start`.
  return path.resolve(process.cwd(), "..");
}

function servicePort(): number {
  const env = process.env.ENGINEERING_SERVICE_PORT;
  const n = env ? Number(env) : NaN;
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 8797;
}

export function pythonExecutable(): string {
  // Sobreescritura de prueba: ENGINEERING_SERVICE_PYTHON (p. ej. una ruta
  // inexistente para el caso de fallo de arranque).
  return process.env.ENGINEERING_SERVICE_PYTHON ?? "python";
}

function startTimeoutMs(): number {
  const env = process.env.ENGINEERING_SERVICE_START_TIMEOUT_MS;
  const n = env ? Number(env) : NaN;
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 15_000;
}

function scriptPath(): string {
  const env = process.env.ENGINEERING_SERVICE_SCRIPT;
  return env ? path.resolve(env) : path.join(
    serviceRoot(), "scripts", "engineering_session_service.py");
}

function pidFilePath(): string {
  return path.join(serviceRoot(), "data", "engineering-session", "service.json");
}

function sessionsDirPath(): string {
  // Directorio DEDICADO (el motor anida paper-lab-sessions/ debajo).
  return path.join(serviceRoot(), "data", "engineering-session", "sessions");
}

// --- utilidades -------------------------------------------------------------

async function readPidFile(): Promise<PidFileInfo | null> {
  try {
    const raw = await readFile(pidFilePath(), "utf8");
    const parsed = JSON.parse(raw) as Partial<PidFileInfo>;
    if (typeof parsed?.pid !== "number" || typeof parsed?.port !== "number") {
      return null;
    }
    return parsed as PidFileInfo;
  } catch {
    return null;
  }
}

async function health(port: number): Promise<
  { reachable: false; code: string; } | { reachable: true; body: Record<string, unknown>; }
> {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/health`, {
      method: "GET",
      cache: "no-store",
      signal: AbortSignal.timeout(1_500),
    });
    const body = await res.json().catch(() => null);
    return { reachable: true, body: (body ?? {}) as Record<string, unknown> };
  } catch (exc: unknown) {
    const err = exc as { cause?: { code?: string }; code?: string };
    return {
      reachable: false,
      code: err?.code ?? err?.cause?.code ?? "UNREACHABLE",
    };
  }
}

/** Estado observable del servicio: consulta pura; NUNCA arranca nada. */
export async function serviceStatus(): Promise<EngineeringServiceStatus> {
  const port = servicePort();
  const pid = await readPidFile();
  const h = await health(port);
  if (!h.reachable) {
    return {
      state: "down",
      service: null,
      engine_version: null,
      pid: null,
      port,
      cadence_ms: null,
      sessions_dir: sessionsDirPath(),
      detail: pid
        ? `pid-file presente pero sin escucha (${h.code})`
        : `sin escucha (${h.code})`,
    };
  }
  const body = h.body;
  if (body?.service !== SERVICE_NAME) {
    return {
      state: "unidentified",
      service: null,
      engine_version: null,
      pid: null,
      port,
      detail: "puerto ocupado por un servicio desconocido (no se reutiliza ni detiene)",
    };
  }
  const healthPid = typeof body?.pid === "number" ? body.pid : null;
  // Fuente de mercado declarada por el propio servicio (para el estado de
  // la demo y el aviso previo de fuente); presente siempre que /health
  // responda con el contrato canónico.
  const marketUrl = (() => {
    const market = body?.market as { url?: unknown } | null | undefined;
    return typeof market?.url === "string" ? market.url : null;
  })();
  if (pid === null || healthPid === null || healthPid !== pid.pid) {
    return {
      state: "unidentified",
      service: String(body?.service ?? ""),
      engine_version: String(body?.engine_version ?? ""),
      pid: healthPid,
      port,
      sessions_dir: typeof body?.sessions_dir === "string"
        ? body.sessions_dir
        : null,
      market_url: marketUrl,
      detail: "servicio en escucha con identidad no verificable (pid-file ausente o desajustado)",
    };
  }
  return {
    state: "ready",
    service: String(body.service),
    engine_version: String(body?.engine_version ?? ""),
    pid: healthPid,
    port,
    cadence_ms: typeof body?.cadence_ms === "number" ? body.cadence_ms : null,
    sessions_dir: typeof body?.sessions_dir === "string" ? body.sessions_dir : null,
    market_url: marketUrl,
    detail: null,
  };
}

// --- reconciliación del pid-file por EVIDENCIA (nunca adopción ciega) ------
//
// Incidente (2026-10-28, preservado en docs): una corrida efímera
// sobrescribió el pid-file canónico (pid 10112/puerto 18797) mientras la
// instancia canónica real (pid 29096/puerto 8797) seguía viva; el gestor
// reportaba "unidentified" y el operador tenía que reconciliar a mano.
// Regla nueva: ante pid-file incompatible, el gestor puede RECONCILIAR
// únicamente con una cadena completa de evidencia independiente; con
// cualquier eslabón faltante RECHAZA (no reutiliza, no detiene, no adopta).

function pidAliveReal(pid: number): boolean {
  try {
    process.kill(pid, 0);  // señal 0: existence check, no envía nada
    return true;
  } catch {
    return false;
  }
}

let pidAliveImpl: (pid: number) => boolean = pidAliveReal;

export interface CmdlineEvidence {
  ok: boolean;
  commandLine?: string;
  error?: string;
}

/** Consulta al SO (evidencia independiente del pid-file y de /health). */
async function verifyCmdlineReal(
  pid: number,
  port: number,
): Promise<CmdlineEvidence> {
  const scriptNeedle = normalizeCmdPath(scriptPath());
  try {
    let commandLine: string;
    if (process.platform === "win32") {
      const r = spawnSync(
        "powershell",
        ["-NoProfile", "-Command",
          `(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}').CommandLine`],
        { encoding: "utf8", timeout: 5_000, windowsHide: true });
      if (r.error) {
        return { ok: false, error: `consulta al SO falló: ${r.error.message}` };
      }
      commandLine = (r.stdout || "").trim();
    } else {
      const r = spawnSync("ps", ["-p", String(pid), "-o", "args="],
        { encoding: "utf8", timeout: 5_000 });
      if (r.error) {
        return { ok: false, error: `consulta al SO falló: ${r.error.message}` };
      }
      commandLine = (r.stdout || "").trim();
    }
    if (!commandLine) {
      return { ok: false, error: "proceso sin línea de comandos (¿no existe?)" };
    }
    if (!normalizeCmdPath(commandLine).includes(scriptNeedle)) {
      return { ok: false, commandLine, error: "el proceso no apunta al CLI canónico" };
    }
    const portMatch = commandLine.match(/--port[= ](\d+)/);
    if (!portMatch || Number(portMatch[1]) !== port) {
      return { ok: false, commandLine, error: `el proceso no declara --port ${port}` };
    }
    // Si declara sessions-dir/pid-file, deben apuntar a los canónicos.
    const sessionsDirMatch = commandLine.match(/--sessions-dir[= ](\S+)/);
    const sessionsDirArg = sessionsDirMatch?.[1];
    if (sessionsDirArg &&
        path.resolve(sessionsDirArg) !== path.resolve(sessionsDirPath())) {
      return { ok: false, commandLine, error: "--sessions-dir no canónico" };
    }
    const pidFileMatch = commandLine.match(/--pid-file[= ](\S+)/);
    const pidFileArg = pidFileMatch?.[1];
    if (pidFileArg &&
        path.resolve(pidFileArg) !== path.resolve(pidFilePath())) {
      return { ok: false, commandLine, error: "--pid-file no canónico" };
    }
    return { ok: true, commandLine };
  } catch (exc: unknown) {
    return { ok: false, error: `consulta al SO falló: ${String(exc)}` };
  }
}

function normalizeCmdPath(p: string): string {
  return p.replace(/\\/g, "/").toLowerCase();
}

let verifyCmdlineImpl: (
  pid: number,
  port: number,
) => Promise<CmdlineEvidence> = verifyCmdlineReal;

/** Costura SOLO para pruebas unitarias (el SO real no se consulta en tests). */
export function _setIdentityEvidenceForTests(
  impl: {
    pidAlive?: (pid: number) => boolean;
    verifyCmdline?: (pid: number, port: number) => Promise<CmdlineEvidence>;
  } | null,
): void {
  pidAliveImpl = impl?.pidAlive ?? pidAliveReal;
  verifyCmdlineImpl = impl?.verifyCmdline ?? verifyCmdlineReal;
}

/**
 * Reconciliación del pid-file con la instancia viva, SOLO con evidencia
 * verificable: (1) /health declara el servicio canónico; (2) el sessions_dir
 * declarado por el servicio es el dedicado canónico; (3) el pid está vivo;
 * (4) la línea de comandos del SO apunta al CLI canónico con el mismo puerto
 * (y, si declara sessions-dir/pid-file, con los canónicos). Sin TODA la
 * cadena → rechazo; nunca se detiene ni adopta a ciegas.
 */
export async function reconcileServiceByEvidence(
  st: EngineeringServiceStatus,
): Promise<{ reconciled: boolean; reason?: string }> {
  const pid = st.pid ?? null;
  if (st.service !== SERVICE_NAME) {
    return { reconciled: false, reason: "health sin identidad canónica" };
  }
  if (pid === null) {
    return { reconciled: false, reason: "health sin pid" };
  }
  if (st.sessions_dir == null ||
      path.resolve(st.sessions_dir) !== path.resolve(sessionsDirPath())) {
    return { reconciled: false, reason: "sessions_dir declarado no canónico" };
  }
  if (!pidAliveImpl(pid)) {
    return { reconciled: false, reason: "pid no vivo" };
  }
  const cmd = await verifyCmdlineImpl(pid, servicePort());
  if (!cmd.ok) {
    return { reconciled: false, reason: cmd.error ?? "cmdline no verificable" };
  }
  const port = servicePort();
  const body = {
    pid,
    port,
    host: "127.0.0.1",
    service: SERVICE_NAME,
    reconciled: true,
    reconciled_at_ms: Date.now(),
  };
  const tmp = `${pidFilePath()}.tmp.${process.pid}`;
  try {
    await mkdir(path.dirname(pidFilePath()), { recursive: true });
    await writeFile(tmp, JSON.stringify(body) + "\n", "utf8");
    await rename(tmp, pidFilePath());
  } catch (exc: unknown) {
    return { reconciled: false, reason: `pid-file no escribible: ${String(exc)}` };
  }
  return { reconciled: true };
}

// --- arranque explícito -----------------------------------------------------

export function waitFor<T>(
  attempt: () => Promise<T | null>,
  timeoutMs: number,
  everyMs = 300,
): Promise<T | null> {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const tick = async () => {
      try {
        const found = await attempt();
        if (found !== null) { resolve(found); return; }
      } catch { /* reintentar */ }
      if (Date.now() >= deadline) { resolve(null); return; }
      setTimeout(tick, everyMs);
    };
    void tick();
  });
}

/**
 * POST explícito: si el servicio no está, genera la instancia canónica del
 * proyecto (spawn del CLI `scripts/engineering_session_service.py`), espera
 * readiness con límite y verifica identidad (child.pid == pid-file == health).
 * En fallo de readiness termina SOLO el proceso que generó (sin huérfanos).
 *
 * Dedupe de arranques CONCURRENTES: dos POST simultáneos comparten la MISMA
 * promesa en curso — solo un spawn (la idempotencia del servicio ya listo
 * cubre el caso secuencial; el caso concurrente vive aquí).
 */
let startInFlight: Promise<StartServiceResult> | null = null;

// Punto de inyección SOLO para pruebas unitarias: vitest no intercepta los
// módulos builtin de Node en este entorno, así que el doble del spawn del
// CLI canónico se inyecta aquí (ver
// src/test/engineering-service-manager.test.ts). En producción siempre se
// usa el spawn real.
const spawnReal: typeof spawn = spawn;
let spawnImpl: typeof spawn = spawnReal;

export function _setSpawnForTests(impl: typeof spawn | null): void {
  spawnImpl = impl ?? spawnReal;
}

/** Ruta del archivo que persiste el run_id de la corrida activa (sessions_dir). */
function publicRunIdPath(): string {
  return path.join(serviceRoot(), "data", "engineering-session", "public-run-id.json");
}

/** Lee el run_id persistido de una corrida previa, si existe. */
function readPublicRunId(): string | null {
  try {
    const raw = readFileSync(publicRunIdPath(), "utf8");
    const data = JSON.parse(raw);
    if (typeof data?.run_id === "string" && data.run_id) return data.run_id;
    return null;
  } catch {
    return null;
  }
}

/** Escribe el run_id de la corrida para que un reinicio lo reutilice. */
function writePublicRunId(runId: string): void {
  const p = publicRunIdPath();
  mkdir(path.dirname(p), { recursive: true }).then(() => {
    writeFileSync(p, JSON.stringify({ run_id: runId }) + "\n", "utf8");
  }).catch(() => { /* no bloquea el arranque si no se puede persistir */ });
}

/** Borra el run_id persistido al detener la corrida. */
function clearPublicRunId(): void {
  try { writeFileSync(publicRunIdPath(), JSON.stringify({ run_id: null }) + "\n", "utf8"); } catch { /* no bloquea */ }
}

/** Lee el registro persistente de la corrida pública (si existe). */
function readPublicRunRecord(): { run_id?: string | null; pid?: number | null; port?: number | null; state?: string | null } | null {
  try {
    const p = path.join(serviceRoot(), "data", "engineering-session", "public-run.json");
    const raw = readFileSync(p, "utf8");
    const data = JSON.parse(raw);
    if (typeof data !== "object" || data === null) return null;
    return {
      run_id: typeof data.run_id === "string" ? data.run_id : null,
      pid: typeof data.pid === "number" ? data.pid : null,
      port: typeof data.port === "number" ? data.port : null,
      state: typeof data.state === "string" ? data.state : null,
    };
  } catch {
    return null;
  }
}

export async function startService(opts: StartServiceOptions = {}): Promise<StartServiceResult> {
  if (startInFlight) return startInFlight;
  startInFlight = doStartService(opts).finally(() => {
    startInFlight = null;
  });
  return startInFlight;
}

async function doStartService(opts: StartServiceOptions): Promise<StartServiceResult> {
  const port = servicePort();
  // 1) ¿Ya disponible y verificable? → no arrancar otra vez (idempotente).
  const before = await serviceStatus();
  if (before.state === "ready") {
    // Si se pide modo publico y el servicio vivo es local, conflicto explícito:
    // no se sustituye ni detiene el servicio local silenciosamente.
    if (opts.clockSource === "public") {
      const healthBody = await health(port).then(h => h.reachable ? h.body : {}).catch(() => ({}));
      const hb = healthBody as { clock?: { source?: string } } | null;
      const declaredSource = typeof hb?.clock?.source === "string" ? hb.clock.source : null;
      if (declaredSource !== "public_sincronizado") {
        return {
          ok: false,
          error: "ENGINEERING_SERVICE_MODE_CONFLICT",
          detail: `el servicio en el puerto ${port} está en modo ${declaredSource ?? "desconocido"}; ` +
            `el modo publico requiere --clock-source public y no se sustituye ni detiene ` +
            `una instancia local silenciosamente. Detenga el servicio local primero si corresponde.`,
        };
      }
    }
    return { ok: true, already: true, pid: before.pid ?? undefined, port };
  }
  if (before.state === "unidentified") {
    // Antes de rechazar: ¿la instancia viva es reconciliable con evidencia
    // verificable (health canónico + sessions_dir canónico + pid vivo +
    // línea de comandos del SO == CLI canónico)? Sin la cadena completa se
    // rechaza igual (no se reutiliza ni detiene procesos desconocidos).
    const rec = await reconcileServiceByEvidence(before);
    if (!rec.reconciled) {
      return {
        ok: false,
        error: "ENGINEERING_SERVICE_UNIDENTIFIED",
        detail:
          `${before.detail ?? "identidad no verificable"}; reconciliación ` +
          `rechazada (${rec.reason ?? "sin evidencia"}); no se reutiliza ni detiene`,
      };
    }
    return {
      ok: true,
      already: true,
      reconciled: true,
      pid: before.pid ?? undefined,
      port,
    };
  }

  // 2) Estado "down": iniciar la instancia canónica del proyecto.
  // run_id estable: si se pide modo public y no se pasó run_id, reutilizar
  // el persistido de una corrida previa (mismo run_id = misma corrida,
  // sin devolver cupos ni crear otra sesión).
  let runId = opts.runId ?? null;
  if (!runId && opts.clockSource === "public") {
    const persisted = readPublicRunId();
    if (persisted) runId = persisted;
  }
  if (opts.clockSource === "public" && !runId) {
    return {
      ok: false,
      error: "ENGINEERING_SERVICE_PUBLIC_RUN_ID_REQUIRED",
      detail: "modo publico requiere run_id estable para atribuir el presupuesto de la corrida a una identidad estable.",
    };
  }

  const args = [
    scriptPath(),
    "--host", "127.0.0.1",
    "--port", String(port),
    "--sessions-dir", sessionsDirPath(),
    "--pid-file", pidFilePath(),
  ];
  if (opts.clockSource === "public") {
    args.push("--clock-source", "public");
    if (runId) {
      args.push("--run-id", runId);
      writePublicRunId(runId);
    }
    if (opts.publicMaxRequests != null) {
      args.push("--public-max-requests", String(opts.publicMaxRequests));
    }
    if (opts.publicFetchUrl) {
      args.push("--public-fetch-url", opts.publicFetchUrl);
    }
  } else {
    args.push("--clock-source", "local");
  }
  if (opts.marketUrl) {
    args.push("--market-url", opts.marketUrl);
  }
  let child: ReturnType<typeof spawn>;
  try {
    child = spawnImpl(pythonExecutable(), args, {
      cwd: serviceRoot(),
      detached: true,
      stdio: "ignore",
      windowsHide: true,
    });
  } catch (exc: unknown) {
    return recordStartFailure({
      ok: false, error: "ENGINEERING_SERVICE_START_FAILED",
      detail: `spawn del controlador canónico falló: ${String(exc)}`,
    });
  }
  child.unref();

  let exitedWith: number | null = null;
  child.once("exit", (code) => {
    exitedWith = code === null ? null : Number(code);
  });
  // El fallo de generación (p. ej. intérprete inexistente) llega por el
  // evento "error" de child_process, no por excepción: hay que escucharlo
  // para no colgar el proceso del dashboard y reportarlo con detalle.
  let spawnError: string | null = null;
  child.once("error", (err: unknown) => {
    spawnError = String(
      err instanceof Error ? (err as NodeJS.ErrnoException).message : err);
  });

  // 3) Readiness con límite + verificación de identidad.
  const verified = await waitFor(
    async () => {
      if (spawnError !== null) return undefined;      // no se pudo generar
      if (exitedWith !== null) return undefined;      // salió antes de listo
      const pidFile = await readPidFile();
      if (!pidFile) return null;
      const h = await health(port);
      if (!h.reachable) return null;
      const ok = (h.body.service === SERVICE_NAME) &&
        typeof h.body.pid === "number" &&
        h.body.pid === pidFile.pid &&
        pidFile.pid === child.pid &&
        pidFile.port === port;
      return ok ? { pid: pidFile.pid, healthBody: h.body } : null;
    },
    startTimeoutMs(),
  );

  if (verified === undefined) {
    return recordStartFailure({
      ok: false,
      error: spawnError !== null
        ? "ENGINEERING_SERVICE_START_FAILED"
        : "ENGINEERING_SERVICE_EXITED",
      detail: spawnError !== null
        ? `spawn del controlador canónico falló: ${spawnError}`
        : `el proceso generado salió con código ${exitedWith}`,
    });
  }
  if (verified === null) {
    // Límite agotado: terminar SOLO el proceso que generamos (no desconocidos).
    try { child.kill(); } catch { /* sin huérfanos fallidos */ }
    return recordStartFailure({
      ok: false,
      error: "ENGINEERING_SERVICE_START_TIMEOUT",
      detail: `readiness no alcanzada en ${startTimeoutMs()} ms (proceso propio detenido)`,
    });
  }
  return {
    ok: true,
    pid: verified.pid,
    port,
    sessions_dir: sessionsDirPath(),
    runIdFromService: opts.clockSource === "public" ? (runId ?? null) : null,
  };
}

function recordStartFailure(r: StartServiceResult): StartServiceResult {
  // Gancho explícito para evidencia/logs futuros; el resultado es el mensaje.
  return r;
}

/** Detiene el servicio de ingeniería propio vía POST /shutdown (pid-file + /health).
 * Solo detiene el proceso que este gestor generó; nunca un PID desconocido.
 */
export interface StopServiceResult {
  ok: boolean;
  pid?: number | null;
  error?: string;
  detail?: string;
}

export async function stopService(runId?: string | null): Promise<StopServiceResult> {
  const port = servicePort();
  const pidFile = await readPidFile();
  const pid = pidFile?.pid ?? null;

  // Verificar que el servicio esté listo antes de apagar.
  const st = await serviceStatus();
  if (st.state !== "ready") {
    return {
      ok: false,
      pid: null,
      error: "ENGINEERING_SERVICE_NOT_RUNNING",
      detail: `el servicio no está en estado ready (estado: ${st.state ?? "desconocido"}).`,
    };
  }

  // Identidad acreditada: pid-file coincide con /health.pid.
  const healthPid = typeof st.pid === "number" ? st.pid : null;
  if (pid === null || healthPid === null || pid !== healthPid) {
    return {
      ok: false,
      pid,
      error: "ENGINEERING_SERVICE_IDENTITY_UNCERTAIN",
      detail: `pid-file (${pid}) y /health (${healthPid}) no coinciden; no se apaga proceso de identidad incierta.`,
    };
  }

  // Pertenencia a la corrida pública: si se solicita run_id, el pid del
  // servicio debe coincidir con el pid registrado en public-run.json.
  if (runId != null && runId !== "") {
    const rec = readPublicRunRecord();
    if (rec === null) {
      return {
        ok: false,
        pid,
        error: "ENGINEERING_SERVICE_RUN_NOT_FOUND",
        detail: `no existe registro persistente de corrida pública; no se puede verificar pertenencia a la corrida ${runId}.`,
      };
    }
    if (rec.run_id !== runId) {
      return {
        ok: false,
        pid,
        error: "ENGINEERING_SERVICE_RUN_MISMATCH",
        detail: `el registro de corrida pública tiene run_id ${rec.run_id ?? "null"}; se solicitó detener ${runId}; no se detiene proceso de corrida ajena.`,
      };
    }
    if (typeof rec.pid === "number" && rec.pid !== pid) {
      return {
        ok: false,
        pid,
        error: "ENGINEERING_SERVICE_RUN_PID_MISMATCH",
        detail: `el pid registrado para la corrida ${runId} (${rec.pid}) no coincide con el pid del servicio (${pid}); no se detiene proceso ajeno.`,
      };
    }
    if (typeof rec.state === "string" && rec.state === "deadline_exceeded") {
      // El deadline ya venció; el servicio debería haberse detenido solo.
      return {
        ok: false,
        pid,
        error: "ENGINEERING_SERVICE_DEADLINE_EXCEEDED",
        detail: `la corrida ${runId} ya excedió su deadline; el servicio debería haberse detenido por el watcher del backend.`,
      };
    }
  }

  let shutdownOk = false;
  let shutdownDetail: string | null = null;
  if (pid != null) {
    try {
      shutdownOk = await postShutdown(port);
      shutdownDetail = null;
    } catch (exc: unknown) {
      shutdownDetail = String(exc);
    }
  } else {
    shutdownDetail = "sin pid verificable; no se apaga proceso desconocido.";
  }

  if (!shutdownOk) {
    // No borrar el registro persistido si la parada falló: conserva historial
    // y consumo para auditoría.
    return {
      ok: false,
      pid,
      error: shutdownDetail ? "ENGINEERING_SERVICE_STOP_FAILED" : "ENGINEERING_SERVICE_NOT_OURS",
      detail: shutdownDetail ?? "no se pudo verificar identidad del servicio; no se detuvo proceso desconocido.",
    };
  }

  // Parada confirmada: solo ahora limpiar el run_id persistido.
  clearPublicRunId();

  return { ok: true, pid };
}

/** POST a /shutdown del servicio de ingeniería. Resuelve true si respondió 200. */
function postShutdown(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port,
        path: "/shutdown",
        method: "POST",
        headers: { "Content-Length": 0 },
        timeout: 5000,
      },
      (res) => {
        let body = "";
        res.on("data", (c) => { body += c; });
        res.on("end", () => {
          resolve(res.statusCode === 200);
        });
      },
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
    req.end();
  });
}
