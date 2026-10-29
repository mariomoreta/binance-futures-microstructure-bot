// ---------------------------------------------------------------------------
// Gestor de la DEMOSTRACIÓN LOCAL de ingeniería (solo para el BFF).
//
// Modo explícito "Demostración local — datos simulados": arranca
// EXCLUSIVAMENTE recursos propios identificados, acotados en duración y
// memoria, y claramente separados de la futura fuente Binance pública:
//   1. productor WS loopback determinista (scripts/local_demo_producer.py,
//      reutiliza el productor del arnés; parada automática propia);
//   2. servicio de mercado canónico en su puerto (8791) con
//      --transport local --base-url ws://127.0.0.1:<productor> y
//      --max-seconds (parada automática acotada);
//   3. el servicio de ingeniería canónico (8797) se reutiliza/arranca por
//      el gestor ya existente (engineering-service-manager).
//
// Reglas: NADA arranca por GET (la consulta es pura); el arranque/parada
// son POST con guardias de origen del BFF; NUNCA se usa silenciosamente el
// servicio preexistente 8792 ni se habilita transporte público; no se
// detiene ni adopta un proceso sin doble verificación (manifest + pid-file
// del propio recurso). La parada de la demo NO toca el servicio de
// ingeniería ni sus sesiones: una caída de fuente posterior queda
// registrada DENTRO de la sesión (visible, sin decisión falsa).
// ---------------------------------------------------------------------------

import { spawn, spawnSync } from "node:child_process";
import { mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { runMarketExplorer } from "@/lib/explorer-bridge";
import {
  pythonExecutable,
  serviceRoot,
  serviceStatus,
  startService,
  waitFor,
  type EngineeringServiceStatus,
} from "@/lib/engineering-service-manager";

// --- configuración (env con defaults del proyecto) ---------------------------

function demoDir(): string {
  return path.join(serviceRoot(), "data", "engineering-demo");
}

function manifestPath(): string {
  return path.join(demoDir(), "demo.json");
}

function producerPidPath(): string {
  return path.join(demoDir(), "producer.json");
}

function marketPidPath(): string {
  return path.join(demoDir(), "market.json");
}

function producerLogPath(): string {
  return path.join(demoDir(), "producer.log.jsonl");
}

function producerScriptPath(): string {
  const env = process.env.ENGINEERING_DEMO_PRODUCER_SCRIPT;
  return env ? path.resolve(env) : path.join(
    serviceRoot(), "scripts", "local_demo_producer.py");
}

function marketScriptPath(): string {
  const env = process.env.ENGINEERING_DEMO_MARKET_SCRIPT;
  return env ? path.resolve(env) : path.join(
    serviceRoot(), "scripts", "market_stream_service.py");
}

function marketPort(): number {
  const env = process.env.ENGINEERING_DEMO_MARKET_PORT;
  const n = env ? Number(env) : NaN;
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 8791;
}

function maxRuntimeS(): number {
  const env = process.env.ENGINEERING_DEMO_MAX_RUNTIME_S;
  const n = env ? Number(env) : NaN;
  return Number.isFinite(n) && n >= 60 ? Math.floor(n) : 2_700;
}

// --- manifest (recursos propios identificados) -------------------------------

interface DemoManifest {
  version: 1;
  started_at_ms: number;
  max_runtime_s: number;
  producer: { pid: number; port: number };
  market: { pid: number; port: number };
  stopped_at_ms?: number | null;
}

async function readManifest(): Promise<DemoManifest | null> {
  try {
    const raw = await readFile(manifestPath(), "utf8");
    const parsed = JSON.parse(raw) as Partial<DemoManifest>;
    if (parsed?.version !== 1 || typeof parsed.producer?.pid !== "number" ||
        typeof parsed.market?.pid !== "number") {
      return null;
    }
    return parsed as DemoManifest;
  } catch {
    return null;
  }
}

async function writeManifest(m: DemoManifest): Promise<void> {
  await mkdir(demoDir(), { recursive: true });
  const tmp = `${manifestPath()}.tmp.${process.pid}`;
  await writeFile(tmp, JSON.stringify(m) + "\n", "utf8");
  await rename(tmp, manifestPath());
}

async function readJsonFile(p: string): Promise<Record<string, unknown> | null> {
  try {
    return JSON.parse(await readFile(p, "utf8")) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function pidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function health(port: number, timeoutMs = 1_500): Promise<
  { reachable: false } | { reachable: true; body: Record<string, unknown> }
> {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/health`, {
      method: "GET", cache: "no-store", signal: AbortSignal.timeout(timeoutMs),
    });
    const body = await res.json().catch(() => null);
    return { reachable: true, body: (body ?? {}) as Record<string, unknown> };
  } catch {
    return { reachable: false };
  }
}

// --- estado (GET: consulta pura; NUNCA arranca ni detiene nada) --------------

export interface DemoStatus {
  engineering: EngineeringServiceStatus;
  source: {
    url: string | null;
    available: boolean;
    service: string | null;
    detail: string | null;
  };
  demo: {
    present: boolean;
    active: boolean;
    expired: boolean;
    started_at_ms: number | null;
    max_runtime_s: number | null;
    stopped_at_ms: number | null;
    producer: { pid: number | null; port: number | null; alive: boolean };
    market: { pid: number | null; port: number | null; health_ok: boolean };
  };
}

export async function demoStatus(): Promise<DemoStatus> {
  const engineering = await serviceStatus();
  const manifest = await readManifest();

  // Fuente: la que el servicio de ingeniería tiene declarada; disponible si
  // responde /health con el contrato market-stream/v1.
  const url = engineering.market_url ?? null;
  let source: DemoStatus["source"];
  if (engineering.state !== "ready" || url === null) {
    source = {
      url,
      available: false,
      service: null,
      detail: engineering.state === "ready"
        ? "el servicio no declara fuente"
        : `servicio de ingeniería ${engineering.state}`,
    };
  } else {
    const h = await health(new URL(url).port ? Number(new URL(url).port) : 8791);
    const svc = h.reachable ? String(h.body.service ?? "") : null;
    // Identidad del servicio de mercado: el contrato es `market-stream/v1`
    // (campo contract_version); el campo `service` del propio servicio es
    // `market-stream-service/v1` (defecto corregido: antes se comparaba el
    // service contra el contrato y la fuente aparecía como no disponible
    // con la demo perfectamente en escucha).
    const contract = h.reachable ? String(h.body.contract_version ?? "") : "";
    const sourceOk = h.reachable &&
      (contract === "market-stream/v1" || svc === "market-stream-service/v1");
    source = {
      url,
      available: sourceOk,
      service: svc,
      detail: h.reachable
        ? (sourceOk ? null : `servicio inesperado: ${svc || contract}`)
        : "sin respuesta (sin fuente conectada)",
    };
  }

  // Productor vivo: pid-file propio + coincidencia con el manifest.
  let producerAlive = false;
  let producerPid: number | null = null;
  if (manifest) {
    producerPid = manifest.producer.pid;
    const pf = await readJsonFile(producerPidPath());
    producerAlive = pf !== null &&
      pf.pid === manifest.producer.pid &&
      typeof manifest.producer.pid === "number" &&
      pidAlive(manifest.producer.pid);
  }
  let marketOk = false;
  if (manifest && !manifest.stopped_at_ms) {
    const h = await health(manifest.market.port);
    marketOk = h.reachable && Number(h.body.pid ?? -1) === manifest.market.pid;
  }
  const active = manifest !== null && !manifest.stopped_at_ms &&
    (producerAlive || marketOk);
  const expired = manifest !== null && !manifest.stopped_at_ms &&
    !producerAlive && !marketOk &&
    Date.now() > manifest.started_at_ms + manifest.max_runtime_s * 1000 + 30_000;

  return {
    engineering,
    source,
    demo: {
      present: manifest !== null,
      active,
      expired,
      started_at_ms: manifest?.started_at_ms ?? null,
      max_runtime_s: manifest?.max_runtime_s ?? null,
      stopped_at_ms: manifest?.stopped_at_ms ?? null,
      producer: {
        pid: manifest?.producer.pid ?? null,
        port: manifest?.producer.port ?? null,
        alive: producerAlive,
      },
      market: {
        pid: manifest?.market.pid ?? null,
        port: manifest?.market.port ?? null,
        health_ok: marketOk,
      },
    },
  };
}

// --- arranque (POST explícito) ----------------------------------------------

export interface DemoActionResult {
  ok: boolean;
  already?: boolean;
  error?: string;
  detail?: string;
  producer?: { pid: number; port: number };
  market?: { pid: number; port: number };
  source?: { url: string | null };
}

// Costuras SOLO para pruebas unitarias (spawn real y consulta al explorador
// no se ejercitan en vitest).
const spawnReal: typeof spawn = spawn;
let spawnImpl: typeof spawn = spawnReal;
let seriesImpl: (args: string[]) => { ok: boolean; data?: unknown } =
  (args) => runMarketExplorer(args);

export function _setDemoDepsForTests(impl: {
  spawn?: typeof spawn;
  series?: (args: string[]) => { ok: boolean; data?: unknown };
} | null): void {
  spawnImpl = impl?.spawn ?? spawnReal;
  seriesImpl = impl?.series ?? ((args) => runMarketExplorer(args));
}

let startInFlight: Promise<DemoActionResult> | null = null;

export async function startDemo(): Promise<DemoActionResult> {
  if (startInFlight) return startInFlight;
  startInFlight = doStartDemo().finally(() => {
    startInFlight = null;
  });
  return startInFlight;
}

/** Último close y última frontera de MINAUSDT 1m del cache local (el MISMO
 * origen del contexto de la sesión; la frontera alimenta el backfill del
 * productor para reparar cache→conexión sin reparación REST). */
function fetchBasePx(): {
  ok: true; base: number; backfillFromMs: number | null;
} | { ok: false; error: string; detail?: string } {
  const result = seriesImpl([
    "--action", "series",
    "--symbol", "MINAUSDT",
    "--interval", "1m",
    "--source", "klines",
    "--no-fetch",
    "--pages", "1",
    "--page-limit", "2",
    "--bars", "2",
    // Sin rango explícito el explorador acota to_ms=ahora y el cache
    // (p. ej. terminado hace horas) saldría VACÍO → backfill nulo y la
    // sesión moriría en GRID_GAP. Mismo rango que usa el contexto de la UI.
    "--from-ms", "0",
    "--to-ms", "9999999999999",
    "--execution-id", `demo-${Date.now()}`,
  ]);
  if (!result.ok || result.data == null) {
    return { ok: false, error: "DEMO_CACHE_EMPTY",
      detail: "cache local sin velas para MINAUSDT (el contexto de la sesión saldría vacío)" };
  }
  const data = result.data as {
    candles?: Array<{ close?: unknown; open_time_ms?: unknown }>;
  };
  const candles = data.candles ?? [];
  const last = candles[candles.length - 1];
  const close = last && typeof last.close === "number"
    ? last.close
    : Number(last?.close);
  if (!Number.isFinite(close) || close <= 0) {
    return { ok: false, error: "DEMO_CACHE_EMPTY",
      detail: "el último close del cache no es un precio utilizable" };
  }
  const lastOpen = Number(last?.open_time_ms);
  const backfillFromMs = Number.isFinite(lastOpen) && lastOpen > 0
    ? lastOpen + 60_000
    : null;
  return { ok: true, base: close, backfillFromMs };
}

async function doStartDemo(): Promise<DemoActionResult> {
  // 1) Manifest activo y recursos vivos → ya hay demo (idempotente).
  const manifest = await readManifest();
  if (manifest && !manifest.stopped_at_ms) {
    const st = await demoStatus();
    if (st.demo.active && !st.demo.expired) {
      return { ok: true, already: true,
        producer: manifest.producer, market: manifest.market };
    }
    return { ok: false, error: "DEMO_STALE",
      detail: "hay una demostración a medio apagar (manifest sin cerrar); pulse Detener demostración y vuelva a intentar" };
  }

  // 2) Servicio de ingeniería: reutilizar/arrancar/reconciliar por el gestor
  //    canónico (identidad verificada; sin adopción ciega).
  const started = await startService();
  if (!started.ok) {
    return { ok: false, error: started.error ?? "ENGINEERING_SERVICE_START_FAILED",
      detail: started.detail ?? undefined };
  }
  const eng = await serviceStatus();
  if (eng.state !== "ready" || !eng.market_url) {
    return { ok: false, error: "ENGINEERING_SERVICE_UNAVAILABLE",
      detail: "sin servicio de ingeniería verificado o sin fuente declarada" };
  }

  // 3) Fuente: si algo ya escucha en la fuente declarada y NO es de esta
  //    demostración, se rechaza EXPLÍCITAMENTE (no se usa en silencio).
  const marketPortValue = marketPort();
  const sourceUrl = new URL(eng.market_url);
  const sourcePort = Number(sourceUrl.port) || marketPortValue;
  const sourceHealth = await health(sourcePort);
  if (sourceHealth.reachable) {
    return { ok: false, error: "DEMO_SOURCE_FOREIGN",
      detail: `la fuente declarada (${eng.market_url}) ya tiene un servicio en escucha que no pertenece a esta demostración; deténgalo antes de iniciar la demo` };
  }

  // 4) Precio base: el MISMO origen del contexto de la sesión (cache local).
  const px = fetchBasePx();
  if (!px.ok) {
    return { ok: false, error: px.error, detail: px.detail };
  }

  // 5) Productor WS propio (parada automática acotada, pid-file propio).
  let producerChild: ReturnType<typeof spawn>;
  let producerOut = "";
  try {
    producerChild = spawnImpl(pythonExecutable(), [
      producerScriptPath(),
      "--base", String(px.base),
      ...(px.backfillFromMs != null
        ? ["--backfill-from-ms", String(px.backfillFromMs)]
        : []),
      "--log", producerLogPath(),
      "--pid-file", producerPidPath(),
      "--max-runtime-s", String(maxRuntimeS()),
    ], {
      cwd: serviceRoot(),
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
  } catch (exc: unknown) {
    return { ok: false, error: "DEMO_PRODUCER_FAILED",
      detail: `spawn del productor falló: ${String(exc)}` };
  }
  producerChild.stdout?.on("data", (chunk: Buffer) => {
    producerOut += chunk.toString("utf8");
  });
  let producerError: string | null = null;
  producerChild.once("error", (err: unknown) => {
    producerError = String(err instanceof Error
      ? (err as NodeJS.ErrnoException).message : err);
  });

  const producerReady = await waitFor(async () => {
    if (producerError !== null) return undefined;
    if (producerChild.exitCode !== null) return undefined;
    const line = producerOut.split(/\r?\n/).find((l) => l.trim().startsWith("{"));
    if (!line) return null;
    try {
      const parsed = JSON.parse(line) as { pid?: number; port?: number };
      if (typeof parsed.pid !== "number" || typeof parsed.port !== "number") {
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  }, 10_000);

  if (producerReady === undefined || producerReady === null) {
    try { producerChild.kill(); } catch { /* sin huérfanos */ }
    return { ok: false, error: "DEMO_PRODUCER_FAILED",
      detail: producerError !== null
        ? `spawn del productor falló: ${producerError}`
        : "el productor no publicó su identidad en 10 s (proceso propio detenido)" };
  }

  // 6) Servicio de mercado canónico: --transport local contra el productor,
  //    con --max-seconds (parada automática acotada) y pid-file propio.
  const marketArgs = [
    marketScriptPath(),
    "--host", "127.0.0.1",
    "--port", String(marketPortValue),
    "--transport", "local",
    "--base-url", `ws://127.0.0.1:${producerReady.port}`,
    "--max-seconds", String(maxRuntimeS()),
  ];
  let marketChild: ReturnType<typeof spawn>;
  try {
    marketChild = spawnImpl(pythonExecutable(), marketArgs, {
      cwd: serviceRoot(),
      detached: true,
      stdio: "ignore",
      windowsHide: true,
      env: {
        ...process.env,
        MICROPROBE_MARKET_STREAM_PID: marketPidPath(),
      },
    });
  } catch (exc: unknown) {
    try { producerChild.kill(); } catch { /* sin huérfanos */ }
    return { ok: false, error: "DEMO_MARKET_FAILED",
      detail: `spawn del servicio de mercado falló: ${String(exc)}` };
  }
  marketChild.unref();

  let occupiedByOther = false;
  const marketReady = await waitFor(async () => {
    if (marketChild.exitCode !== null) return undefined;
    const h = await health(marketPortValue, 1_200);
    if (!h.reachable) return null;
    if (Number(h.body.pid ?? -1) !== marketChild.pid) {
      occupiedByOther = true;
      return undefined;  // puerto ocupado por otro proceso → fracaso inmediato
    }
    return { pid: marketChild.pid };
  }, 15_000);

  if (marketReady === undefined || marketReady === null) {
    // Parada SOLO de los procesos propios generados (sin huérfanos).
    try { marketChild.kill(); } catch { /* noop */ }
    try { producerChild.kill(); } catch { /* noop */ }
    try { await unlink(producerPidPath()); } catch { /* noop */ }
    return { ok: false, error: marketReady === undefined
        ? (occupiedByOther ? "DEMO_MARKET_PORT_OCCUPIED" : "DEMO_MARKET_FAILED")
        : "DEMO_MARKET_START_TIMEOUT",
      detail: marketReady === undefined
        ? (occupiedByOther
          ? `el puerto ${marketPortValue} lo ocupa otro proceso; no se detiene ni adopta`
          : "el servicio de mercado generado salió antes de estar listo (procesos propios detenidos)")
        : `el puerto ${marketPortValue} no quedó en escucha con el proceso propio en 15 s (procesos propios detenidos)` };
  }

  const next: DemoManifest = {
    version: 1,
    started_at_ms: Date.now(),
    max_runtime_s: maxRuntimeS(),
    producer: {
      pid: Number(producerChild.pid),
      port: Number(producerReady.port),
    },
    market: { pid: Number(marketChild.pid), port: marketPortValue },
    stopped_at_ms: null,
  };
  try {
    await writeManifest(next);
  } catch (exc: unknown) {
    return { ok: false, error: "DEMO_MANIFEST_WRITE_FAILED",
      detail: `recursos activos (pid ${producerChild.pid}/${marketChild.pid}); no se pudo escribir el manifest: ${String(exc)}` };
  }
  return {
    ok: true,
    producer: next.producer,
    market: next.market,
    source: { url: eng.market_url },
  };
}

// --- parada (POST explícito; SOLO recursos propios identificados) ------------

async function treeKill(pid: number): Promise<void> {
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"],
      { timeout: 30_000, windowsHide: true });
    return;
  }
  try { process.kill(pid, "SIGKILL"); } catch { /* ya muerto */ }
}

async function waitDead(pid: number, timeoutMs = 5_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!pidAlive(pid)) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return !pidAlive(pid);
}

export async function stopDemo(): Promise<DemoActionResult> {
  const manifest = await readManifest();
  if (!manifest || manifest.stopped_at_ms) {
    return { ok: true, already: true };
  }

  // 1) Productor: identidad doble (manifest + pid-file propio). Si el
  //    pid-file ya no existe, el productor expiró solo (duración acotada).
  const producerFile = await readJsonFile(producerPidPath());
  if (producerFile && producerFile.pid !== manifest.producer.pid) {
    return { ok: false, error: "DEMO_PRODUCER_UNIDENTIFIED",
      detail: `el pid-file del productor declara otro pid (${String(producerFile.pid)}); no se detiene un proceso sin identidad verificable` };
  }
  if (producerFile && producerFile.pid === manifest.producer.pid &&
      pidAlive(manifest.producer.pid)) {
    await treeKill(manifest.producer.pid);
  }
  try { await unlink(producerPidPath()); } catch { /* ya fuera */ }

  // 2) Servicio de mercado: parada ordenada por su propio endpoint
  //    (/shutdown, solo loopback) + verificación del pid-file propio.
  const marketFile = await readJsonFile(marketPidPath());
  const marketPidMatches = marketFile !== null &&
    Number(marketFile.pid) === manifest.market.pid;
  if (marketFile && !marketPidMatches) {
    return { ok: false, error: "DEMO_MARKET_UNIDENTIFIED",
      detail: `el pid-file del servicio de mercado declara otro pid (${String(marketFile.pid)}); no se detiene un proceso sin identidad verificable` };
  }
  try {
    await fetch(`http://127.0.0.1:${manifest.market.port}/shutdown`, {
      method: "POST", signal: AbortSignal.timeout(3_000),
    });
  } catch { /* puede estar ya muerto */ }
  if (marketPidMatches && !await waitDead(manifest.market.pid)) {
    await treeKill(manifest.market.pid);
    await waitDead(manifest.market.pid);
  }
  try { await unlink(marketPidPath()); } catch { /* ya fuera */ }

  // 3) Manifest cerrado (auditoría); el servicio de ingeniería y sus
  //    sesiones NO se tocan: la caída de fuente queda registrada en la
  //    sesión (visible), la parada de sesión es del operador.
  try {
    await writeManifest({ ...manifest, stopped_at_ms: Date.now() });
  } catch { /* auditoría best-effort */ }
  return { ok: true };
}
