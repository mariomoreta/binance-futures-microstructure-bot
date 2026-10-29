// @vitest-environment jsdom
// Regresión del defecto encontrado en la corrida 1 (2026-10-28):
// `demoStatus` comparaba el campo `service` del /health del servicio de
// mercado (`market-stream-service/v1`) contra el CONTRATO
// (`market-stream/v1`) → la fuente aparecía NO DISPONIBLE con la demo en
// escucha y la puerta previa bloqueaba el create de sesión. La
// disponibilidad se acredita por `contract_version` (o el service canónico).
//
// Además: guardia DEMO_SOURCE_FOREIGN — si la fuente declarada ya tiene un
// servicio ajeno en escucha, startDemo RECHAZA sin spawn (no usa en
// silencio recursos que no son suyos).
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {mkdtempSync, mkdirSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import pathReal from "node:path";
import {
  _setIdentityEvidenceForTests,
} from "@/lib/engineering-service-manager";
import {
  _setDemoDepsForTests,
  demoStatus,
  startDemo,
} from "@/lib/local-demo-manager";

const ENGINEERING_BODY = (root: string) => ({
  service: "engineering-session-service/v1",
  engine_version: "paper-engine/v1",
  pid: 777,
  cadence_ms: 1000,
  sessions_dir: pathReal.join(root, "data", "engineering-session", "sessions"),
  market: {url: "http://127.0.0.1:18791"},
});

const MARKET_BODY = {
  service: "market-stream-service/v1",
  contract_version: "market-stream/v1",
  pid: 555,
};

function routerFetch(
  engineeringRoot: string,
  opts: {marketUp: boolean},
): typeof fetch {
  return (async (input: RequestInfo | URL) => {
    const url = String(input instanceof Request ? input.url : input);
    if (url.includes(":18797/health")) {
      return {
        ok: true, status: 200,
        json: async () => ENGINEERING_BODY(engineeringRoot),
      } as unknown as Response;
    }
    if (url.includes(":18791/health")) {
      if (!opts.marketUp) {
        throw new TypeError("connect ECONNREFUSED 127.0.0.1:18791");
      }
      return {
        ok: true, status: 200, json: async () => MARKET_BODY,
      } as unknown as Response;
    }
    if (url.includes(":18791/shutdown")) {
      return {ok: true, status: 200, json: async () => ({})} as unknown as Response;
    }
    throw new TypeError(`fetch no esperado: ${url}`);
  }) as unknown as typeof fetch;
}

describe("local-demo-manager — identidad de la fuente y guardia de fuente ajena", () => {
  let tmpRoot: string;
  const spawnMock = vi.fn(() => ({
    pid: 4242, unref() { /* noop */ }, once() { /* noop */ },
    on() { /* noop */ }, kill() { /* noop */ }, stdout: null,
  }));

  beforeEach(() => {
    tmpRoot = mkdtempSync(pathReal.join(tmpdir(), "demo-mgr-"));
    vi.stubEnv("ENGINEERING_SERVICE_ROOT", tmpRoot);
    vi.stubEnv("ENGINEERING_SERVICE_PORT", "18797");
    vi.stubEnv("ENGINEERING_DEMO_MARKET_PORT", "18791");
    // pid-file compatible con /health (pid 777): el GET de estado es puro y
    // NO reconcilia; con pid-file coincidente serviceStatus es "ready".
    mkdirSync(pathReal.join(tmpRoot, "data", "engineering-session"), {
      recursive: true,
    });
    writeFileSync(
      pathReal.join(tmpRoot, "data", "engineering-session", "service.json"),
      JSON.stringify({pid: 777, port: 18797, service:
        "engineering-session-service/v1"}) + "\n", "utf8");
    _setIdentityEvidenceForTests({
      pidAlive: () => true,
      verifyCmdline: async () => ({ok: true, commandLine: "python ..."}),
    });
  });

  afterEach(() => {
    _setIdentityEvidenceForTests(null);
    _setDemoDepsForTests(null);
    rmSync(tmpRoot, {recursive: true, force: true});
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    spawnMock.mockClear();
  });

  it("fuente disponible: health con contract_version market-stream/v1 (regresión corrida 1)", async () => {
    vi.stubGlobal("fetch", routerFetch(tmpRoot, {marketUp: true}));
    const st = await demoStatus();
    expect(st.engineering.state).toBe("ready");
    expect(st.source.available).toBe(true);
    expect(st.source.service).toBe("market-stream-service/v1");
    expect(st.demo.present).toBe(false);
  });

  it("fuente ausente: available=false con detalle explícito (sin inventar estado)", async () => {
    vi.stubGlobal("fetch", routerFetch(tmpRoot, {marketUp: false}));
    const st = await demoStatus();
    expect(st.source.available).toBe(false);
    expect(st.source.detail).toContain("sin respuesta");
  });

  it("startDemo con fuente AJENA en escucha → DEMO_SOURCE_FOREIGN, sin spawn", async () => {
    vi.stubGlobal("fetch", routerFetch(tmpRoot, {marketUp: true}));
    _setDemoDepsForTests({spawn: spawnMock as unknown as typeof import("node:child_process").spawn});
    const r = await startDemo();
    expect(r.ok).toBe(false);
    expect(r.error).toBe("DEMO_SOURCE_FOREIGN");
    expect(r.detail).toContain("ya tiene un servicio en escucha");
    expect(spawnMock).not.toHaveBeenCalled();
  });
});
