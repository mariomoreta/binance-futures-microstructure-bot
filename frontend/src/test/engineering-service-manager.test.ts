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
import {
  startService, _setSpawnForTests,
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
