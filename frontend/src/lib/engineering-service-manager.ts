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

import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";

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
  detail?: string | null;
}

export interface StartServiceResult {
  ok: boolean;
  pid?: number;
  port?: number;
  sessions_dir?: string;
  already?: boolean;
  error?: string;
  detail?: string;
}

interface PidFileInfo {
  pid: number;
  port: number;
  host: string;
  service: string;
}

const SERVICE_NAME = "engineering-session-service/v1";

// --- configuración (env con defaults del proyecto) --------------------------

function serviceRoot(): string {
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

function pythonExecutable(): string {
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
  if (pid === null || healthPid === null || healthPid !== pid.pid) {
    return {
      state: "unidentified",
      service: String(body?.service ?? ""),
      engine_version: String(body?.engine_version ?? ""),
      pid: healthPid,
      port,
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
    detail: null,
  };
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

export async function startService(): Promise<StartServiceResult> {
  if (startInFlight) return startInFlight;
  startInFlight = doStartService().finally(() => {
    startInFlight = null;
  });
  return startInFlight;
}

async function doStartService(): Promise<StartServiceResult> {
  const port = servicePort();
  // 1) ¿Ya disponible y verificable? → no arrancar otra vez (idempotente).
  const before = await serviceStatus();
  if (before.state === "ready") {
    return { ok: true, already: true, pid: before.pid ?? undefined, port };
  }
  if (before.state === "unidentified") {
    return {
      ok: false,
      error: "ENGINEERING_SERVICE_UNIDENTIFIED",
      detail: before.detail ?? "puerto ocupado con identidad no verificable",
    };
  }

  // 2) Estado "down": iniciar la instancia canónica del proyecto.
  const args = [
    scriptPath(),
    "--host", "127.0.0.1",
    "--port", String(port),
    "--sessions-dir", sessionsDirPath(),
    "--pid-file", pidFilePath(),
  ];
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
  };
}

function recordStartFailure(r: StartServiceResult): StartServiceResult {
  // Gancho explícito para evidencia/logs futuros; el resultado es el mensaje.
  return r;
}
