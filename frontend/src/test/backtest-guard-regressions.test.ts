// @vitest-environment node
// Regresiones dirigidas de control.guard (mutex corto entre procesos).
//
// Corresponde a la corrección final acotada del guard:
//   A. Propietario activo durante mas de 30 segundos: una segunda solicitud
//      NO adquiere la seccion crítica (antigüedad != muerte).
//   B. Liberación tardía de A nunca retira el guard de B, incluso si ambos
//      usan el mismo PID (identidad única por adquisición: token).
//   C. Propietario muerto: recuperación concurrente entre PROCESOS
//      INDEPENDIENTES por el mismo guard huérfano; como máximo un
//      propietario activo; ninguno borra el guard del otro.
//   D. Identidad incierta: conservar exclusión y reportar causa
//      (guard ilegible, sin token, EPERM, PID desconocido).
//
// El mismo archivo se ejecuta contra el código con el defecto (debe FALLAR:
// A, B, C-concurrencia, D) y contra el código corregido (debe PASAR).
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {execSync, spawn, type ChildProcess} from "node:child_process";
import {
  createWriteStream, existsSync, mkdirSync, mkdtempSync, readFileSync,
  rmSync, writeFileSync, utimesSync} from "node:fs";
import {join} from "node:path";
import {pathToFileURL} from "node:url";
import {tmpdir} from "node:os";

let resultsDir: string;
let fakeRoot: string;
const children: ChildProcess[] = [];

beforeEach(() => {
  resultsDir = mkdtempSync(join(tmpdir(), "bt-guard-"));
  fakeRoot = mkdtempSync(join(tmpdir(), "bt-guard-root-"));
  mkdirSync(join(fakeRoot, "scripts"), {recursive: true});
  writeFileSync(join(fakeRoot, "scripts", "run_dashboard_backtest.py"), "");
  process.env.BACKTEST_RUNS_DIR = resultsDir;
  process.env.BACKTEST_ROOT = fakeRoot;
  vi.resetModules();
});

afterEach(() => {
  delete process.env.BACKTEST_RUNS_DIR;
  delete process.env.BACKTEST_ROOT;
  for (const child of children.splice(0)) {
    try { child.kill(); } catch { /* ignore */ }
  }
  try { rmSync(resultsDir, {recursive: true, force: true }); } catch { /* ignore */ }
  try { rmSync(fakeRoot, {recursive: true, force: true }); } catch { /* ignore */ }
});

const load = () => import("@/lib/backtest-control");
const EXP = "eval-census-v2-trio";
const expDir = () => join(resultsDir, EXP);
const guardPath = () => join(expDir(), "control.guard");
const GUARD_STALE_MS = 30_000;

// Ruta absoluta al punto de entrada del control (para bundlear con esbuild).
const CONTROL_SRC = join(__dirname, "..", "lib", "backtest-control.ts")
  .replace(/\\/g, "/");

function writeGuard(pid: number | null, acquiredAtMs: number, token: string | null,
                    mtimeMs?: number): void {
  mkdirSync(expDir(), {recursive: true});
  const obj: Record<string, unknown> = {pid, acquired_at_ms: acquiredAtMs};
  if (token !== null) obj.token = token;
  writeFileSync(guardPath(), JSON.stringify(obj));
  if (mtimeMs !== undefined) {
    const ref = Date.now() - 60_000;
    utimesSync(guardPath(), new Date(ref), new Date(mtimeMs));
  }
}

function readGuardRaw(): string | null {
  try { return readFileSync(guardPath(), "utf8"); } catch { return null; }
}

// Proceso hijo vivo cuyo pid conocemos (propietario del guard).
function spawnOwner(): ChildProcess {
  const child = spawn(process.execPath, [
    "-e", "setTimeout(()=>{},120000)",
  ], {stdio: "ignore", windowsHide: true});
  children.push(child);
  return child;
}

// Bundlea backtest-control.ts + dependencias a un archivo JS ejecutable con
// node puro, para que procesos hijos independientes puedan importar el código
// real del guard sin depender de --experimental-strip-types ni de extensiones
// TS en imports ESM.
function bundleGuard(): string {
  const bundlePath = join(resultsDir, "guard-bundle.js");
  execSync(
    `npx esbuild "${CONTROL_SRC}" --bundle --platform=node --format=cjs ` +
    `--outfile="${bundlePath}"`,
    {stdio: "pipe", encoding: "utf8"});
  return bundlePath;
}

// Script hijo (JS puro, sin TS) que intenta adquirir el guard y escribe su
// resultado a un archivo de salida.
function writeChildScript(bundlePath: string): string {
  const childPath = join(resultsDir, "guard-child.js");
  const src = [
    `const {acquireGuard, releaseGuard} = require("${bundlePath.replace(/\\/g, "/")}");`,
    `const {existsSync, writeFileSync} = require("fs");`,
    `const out = process.argv[2];`,
    `const exp = process.argv[3];`,
    `const startFlag = process.argv[4];`,
    // Barrera: todos los hijos esperan a que el padre señale el inicio para
    // ejercitar la carrera real de adquisición al mismo instante.
    `while (!existsSync(startFlag)) { /* espera barrera */ }`,
    `const r = acquireGuard(exp);`,
    `writeFileSync(out, JSON.stringify({`,
    `pid: process.pid, acquired: !!r, token: r?.token ?? null,`,
    `acquired_at_ms: r?.acquired_at_ms ?? null}));`,
    // El ganador se mantiene vivo 5s para ejercitar la exclusión durante
    // toda la sección crítica; el padre mata todos los hijos al final.
    `if (r) { setTimeout(() => releaseGuard(r), 5000); }`,
  ].join("\n");
  writeFileSync(childPath, src);
  return childPath;
}

// ---------------------------------------------------------------------------
// Caso A: propietario vivo durante mas de 30s -> segunda solicitud no adquiere
// ---------------------------------------------------------------------------
describe("control.guard: identidad y exclusión de sección crítica", () => {
  it("A: propietario activo durante mas de 30s -> segunda solicitud no adquiere", async () => {
    const owner = spawnOwner();
    // El guard pertenece a un propietario VIVO, pero tiene mtime antiguo (>30s).
    writeGuard(owner.pid!, Date.now() - 60_000, "tok-viejo",
      Date.now() - (GUARD_STALE_MS + 5_000));
    const mod = await load();
    const g = mod.acquireGuard(EXP);
    expect(g).toBeNull(); // segunda solicitud no adquiere: propietario activo
    expect(existsSync(guardPath())).toBe(true); // el guard del propietario persiste
    const content = readGuardRaw();
    expect(content).toContain("tok-viejo"); // no fue reemplazado
  }, 60_000);

  // -------------------------------------------------------------------------
  // Caso B: liberación tardía de A nunca retira el guard de B (mismo PID,
  // distinto token de adquisición). Se prueba releaseGuard directamente con
  // un handle antiguo (tokenA) contra un guard que lleva tokenB.
  // -------------------------------------------------------------------------
  it("B: liberación tardía de A conserva el guard de B (mismo PID, token distinto)", async () => {
    const mod = await load();

    // El guard actual pertenece a B: mismo PID del proceso actual, tokenB.
    const pid = process.pid;
    const acquiredB = Date.now();
    writeGuard(pid, acquiredB, "tok-B");

    // A intenta una liberación TARDÍA con su handle original (tokenA, mismo
    // PID pero distinto token y distinto acquired_at_ms).
    mod.releaseGuard({path: guardPath(), pid, acquired_at_ms: acquiredB - 1000,
      token: "tok-A"});

    // El guard de B debe conservarse intacto (token distinto -> no se borra).
    expect(existsSync(guardPath())).toBe(true);
    const after = JSON.parse(readGuardRaw()!);
    expect(after.token).toBe("tok-B");
    expect(after.pid).toBe(pid);

    // Limpieza: libera el guard de B con su propio handle (tokenB).
    mod.releaseGuard({path: guardPath(), pid, acquired_at_ms: acquiredB,
      token: "tok-B"});
    expect(existsSync(guardPath())).toBe(false);
  }, 60_000);

  // -------------------------------------------------------------------------
  // Caso C: recuperación concurrente entre PROCESOS independientes.
  // -------------------------------------------------------------------------
  it("C: recuperación concurrente -> como máximo un propietario activo", async () => {
    // Guard huérfano: PID que no existe, mtime antiguo, sin token.
    writeGuard(999999, Date.now() - 60_000, null,
      Date.now() - (GUARD_STALE_MS + 5_000));

    const bundlePath = bundleGuard();
    const childPath = writeChildScript(bundlePath);
    const startFlag = join(resultsDir, "start.flag");
    const N = 6;
    const outFiles: string[] = [];
    const procs: ChildProcess[] = [];

    for (let i = 0; i < N; i += 1) {
      const out = join(resultsDir, `child-${i}.json`);
      outFiles.push(out);
      const child = spawn(process.execPath, [childPath, out, EXP, startFlag], {
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
        env: {...process.env, BACKTEST_RUNS_DIR: resultsDir},
      });
      const outLog = join(resultsDir, `child-${i}.out`);
      const errLog = join(resultsDir, `child-${i}.err`);
      const outStream = createWriteStream(outLog);
      const errStream = createWriteStream(errLog);
      child.stdout!.pipe(outStream);
      child.stderr!.pipe(errStream);
      child.on("close", () => { outStream.end(); errStream.end(); });
      procs.push(child);
    }
    children.push(...procs);

    // Señal de inicio: todos los hijos llaman a acquireGuard al mismo instante.
    writeFileSync(startFlag, "");

    // Espera a que todos los hijos hayan intentado adquirir (escriben su
    // resultado nada más adquirir). El ganador se mantiene vivo 5s para
    // ejercitar la exclusión durante toda la sección crítica.
    await new Promise((res) => setTimeout(res, 1500));

    // Lee los archivos de salida de cada hijo.
    type ChildOutcome = {pid: number; acquired: boolean; token: string | null;
      acquired_at_ms: number | null} | {acquired: boolean};
    const outcomes = outFiles.map((f): ChildOutcome => {
      try {
        return JSON.parse(readFileSync(f, "utf8")) as ChildOutcome;
      } catch { return {acquired: false}; }
    });

    const winners = outcomes.filter((o): o is {pid: number; acquired: true;
      token: string | null; acquired_at_ms: number | null} =>
      o.acquired === true && "token" in o);
    // Propiedad de exclusión: como máximo un propietario activo al mismo
    // tiempo.
    expect(winners.length).toBeLessThanOrEqual(1);
    // Propiedad de recuperación: el guard huérfano se recupera (alguien lo
    // adquiere).
    expect(winners.length).toBeGreaterThanOrEqual(1);

    const winner = winners[0]!;
    expect(winner).not.toBeNull();
    expect(winner.token).not.toBeNull();
    // El guard actual pertenece al ganador (su token está escrito) y ningún
    // otro recuperador pudo borrarlo mientras el ganador vivía.
    const final = JSON.parse(readGuardRaw()!);
    expect(final.token).toBe(winner.token);
    expect(final.pid).toBe(winner.pid);

    // Limpieza: mata a todos los hijos (los ganadores siguen vivos por el
    // setTimeout de 5s; los perdedores ya terminaron).
    for (const p of procs) { try { p.kill(); } catch { /* ignore */ } }
  }, 60_000);

  // -------------------------------------------------------------------------
  // Caso D: identidad incierta -> conservar exclusión y reportar causa.
  // -------------------------------------------------------------------------
  it("D1: guard ilegible (no JSON) -> no adquiere, conserva el guard", async () => {
    mkdirSync(expDir(), {recursive: true});
    writeFileSync(guardPath(), "no-es-json-{{{");
    utimesSync(guardPath(), new Date(Date.now() - 60_000),
      new Date(Date.now() - (GUARD_STALE_MS + 5_000)));
    const mod = await load();
    const g = mod.acquireGuard(EXP);
    expect(g).toBeNull(); // identidad incierta: fail-closed
    expect(existsSync(guardPath())).toBe(true); // no borra el guard ilegible
    expect(readGuardRaw()).toBe("no-es-json-{{{");
  }, 60_000);

  it("D2: guard sin token (identidad incompleta) -> no adquiere, conserva", async () => {
    writeGuard(process.pid, Date.now() - 60_000, null,
      Date.now() - (GUARD_STALE_MS + 5_000));
    const mod = await load();
    const g = mod.acquireGuard(EXP);
    expect(g).toBeNull(); // sin token: identidad incompleta, conserva exclusión
    expect(existsSync(guardPath())).toBe(true);
  }, 60_000);

  it("D3: EPERM (proceso existe, sin permisos) -> conserva exclusión, no recupera", async () => {
    const owner = spawnOwner();
    writeGuard(owner.pid!, Date.now() - 60_000, "tok-vivo-eperm",
      Date.now() - (GUARD_STALE_MS + 5_000));
    const killSpy = vi.spyOn(process, "kill").mockImplementation(() => {
      const err: NodeJS.ErrnoException & {code?: string} = new Error("EPERM");
      err.code = "EPERM";
      throw err;
    });
    try {
      const mod = await load();
      const g = mod.acquireGuard(EXP);
      expect(g).toBeNull(); // EPERM: no se asume muerto, conserva exclusión
      expect(existsSync(guardPath())).toBe(true);
    } finally {
      killSpy.mockRestore();
    }
  }, 60_000);

  it("D4: PID desconocido (gone) -> recuperación segura, adquiere", async () => {
    writeGuard(888888, Date.now() - 60_000, "tok-muerto",
      Date.now() - (GUARD_STALE_MS + 5_000));
    const mod = await load();
    const g = mod.acquireGuard(EXP);
    expect(g).not.toBeNull(); // PID gone: se recupera
    expect(g?.pid).toBe(process.pid);
    mod.releaseGuard(g!);
    expect(existsSync(guardPath())).toBe(false);
  }, 60_000);
});