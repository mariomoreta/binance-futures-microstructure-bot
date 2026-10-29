// @vitest-environment jsdom
// Dedupe de arranques CONCURRENTES del servicio de ingeniería: dos POST
// simultáneos al gestor comparten la MISMA promesa en curso — un solo spawn
// del CLI canónico. El caso secuencial (servicio ya listo) es idempotente
// por serviceStatus; el concurrente vive en startInFlight del módulo.
//
// El doble del spawn se inyecta por la costura _setSpawnForTests (vitest no
// intercepta los módulos builtin de Node en este entorno); la red se aisla
// con un stub global de fetch (→ estado "down", rama de spawn). El pid-file
// no existe en el entorno de prueba: readFile falla y el readiness nunca
// llega, por eso el límite se acorta por env.
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {mkdtempSync, rmSync} from "node:fs";
import {readFile as readFileReal} from "node:fs/promises";
import {tmpdir} from "node:os";
import pathReal from "node:path";
import {
  startService, _setSpawnForTests, _setIdentityEvidenceForTests,
} from "@/lib/engineering-service-manager";

// Child falso: unref/once/kill suficientes para el gestor; el readiness
// nunca llega (sin pid-file) y el límite se acorta por env.
function fakeChild() {
  return {
    pid: 4242,
    unref() { /* noop */ },
    once() { /* noop */ },
    kill() { /* noop */ },
  };
}

const spawnMock = vi.fn(() => fakeChild());

describe("engineering-service-manager — dedupe de arranques concurrentes", () => {
  beforeEach(() => {
    spawnMock.mockClear();
    _setSpawnForTests(spawnMock as unknown as typeof import("node:child_process").spawn);
    // Readiness límite corto: el test ejercita el DEDUPE (promesa
    // compartida), no el arranque real del servicio.
    vi.stubEnv("ENGINEERING_SERVICE_START_TIMEOUT_MS", "300");
    // Aislamiento de red: en la máquina de desarrollo el puerto real (8797)
    // puede tener el servicio canónico en escucha (→ unidentified). El stub
    // fuerza "down" para ejercitar la rama de spawn.
    vi.stubEnv("ENGINEERING_SERVICE_PORT", "18797");
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new Error("unreachable (test aislado de red)");
    }));
  });
  afterEach(() => {
    _setSpawnForTests(null);
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("dos startService simultáneos → UN solo spawn y la MISMA promesa/resultado", async () => {
    const [a, b] = await Promise.all([startService(), startService()]);
    expect(spawnMock).toHaveBeenCalledTimes(1);
    expect(b).toBe(a); // misma instancia de promesa compartida
    expect(a.ok).toBe(false);
    expect(a.error).toBe("ENGINEERING_SERVICE_START_TIMEOUT");
  });

  it("tras terminar el arranque en curso, un startService nuevo vuelve a intentarlo (sin pegarse al dedupe)", async () => {
    await Promise.all([startService(), startService()]);
    const antes = spawnMock.mock.calls.length;
    await startService();
    expect(spawnMock.mock.calls.length).toBe(antes + 1);
  });
});

// ---------------------------------------------------------------------------
// Reconciliación del pid-file por EVIDENCIA: ante pid-file ausente/desajustado
// el gestor solo REUTILIZA la instancia viva si la cadena completa de
// evidencia verifica (/health canónico + sessions_dir canónico + pid vivo +
// línea de comandos del SO == CLI canónico); sin la cadena, RECHAZA (no
// reutiliza, no detiene, no adopta). Incidente 2026-10-28 preservado en docs.
// ---------------------------------------------------------------------------

function healthFetcher(body: Record<string, unknown>): typeof fetch {
  return (async () => ({
    ok: true, status: 200, json: async () => body,
  })) as unknown as typeof fetch;
}

describe("reconciliación del pid-file por evidencia", () => {
  let tmpRoot: string;

  beforeEach(() => {
    tmpRoot = mkdtempSync(pathReal.join(tmpdir(), "engmgr-reconcile-"));
    vi.stubEnv("ENGINEERING_SERVICE_ROOT", tmpRoot);
    vi.stubEnv("ENGINEERING_SERVICE_PORT", "18797");
    // Identity dobles por defecto: pid vivo y cmdline canónica (caso feliz).
    _setIdentityEvidenceForTests({
      pidAlive: () => true,
      verifyCmdline: async () => ({ok: true, commandLine: "python ..."}),
    });
  });

  afterEach(() => {
    _setIdentityEvidenceForTests(null);
    rmSync(tmpRoot, {recursive: true, force: true});
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("pid-file ausente + health canónico + cmdline canónica → reconcilia y reutiliza (sin spawn)", async () => {
    const sessionsDir = pathReal.join(
      tmpRoot, "data", "engineering-session", "sessions");
    vi.stubGlobal("fetch", healthFetcher({
      service: "engineering-session-service/v1",
      pid: 777,
      sessions_dir: sessionsDir,
      market: {url: "http://127.0.0.1:8791"},
    }));
    const r = await startService();
    expect(r.ok).toBe(true);
    expect(r.already).toBe(true);
    expect(r.reconciled).toBe(true);
    expect(r.pid).toBe(777);
    expect(spawnMock).not.toHaveBeenCalled();
    const pidFile = JSON.parse(await readFileReal(
      pathReal.join(tmpRoot, "data", "engineering-session", "service.json"),
      "utf8"));
    expect(pidFile.pid).toBe(777);
    expect(pidFile.reconciled).toBe(true);
  });

  it("cmdline no canónica → RECHAZO explícito (sin spawn, sin pid-file escrito)", async () => {
    const sessionsDir = pathReal.join(
      tmpRoot, "data", "engineering-session", "sessions");
    vi.stubGlobal("fetch", healthFetcher({
      service: "engineering-session-service/v1",
      pid: 777,
      sessions_dir: sessionsDir,
    }));
    _setIdentityEvidenceForTests({
      pidAlive: () => true,
      verifyCmdline: async () => ({
        ok: false, error: "el proceso no apunta al CLI canónico",
      }),
    });
    const r = await startService();
    expect(r.ok).toBe(false);
    expect(r.error).toBe("ENGINEERING_SERVICE_UNIDENTIFIED");
    expect(r.detail).toContain("no apunta al CLI canónico");
    expect(spawnMock).not.toHaveBeenCalled();
    let wrote = false;
    try {
      await readFileReal(
        pathReal.join(tmpRoot, "data", "engineering-session", "service.json"),
        "utf8");
      wrote = true;
    } catch { /* esperado: no se escribe nada */ }
    expect(wrote).toBe(false);
  });

  it("sessions_dir declarado distinto del canónico → RECHAZO (no adopta)", async () => {
    vi.stubGlobal("fetch", healthFetcher({
      service: "engineering-session-service/v1",
      pid: 777,
      sessions_dir: pathReal.join(tmpRoot, "otro", "dir"),
    }));
    const r = await startService();
    expect(r.ok).toBe(false);
    expect(r.error).toBe("ENGINEERING_SERVICE_UNIDENTIFIED");
    expect(r.detail).toContain("sessions_dir declarado no canónico");
    expect(spawnMock).not.toHaveBeenCalled();
  });
});
