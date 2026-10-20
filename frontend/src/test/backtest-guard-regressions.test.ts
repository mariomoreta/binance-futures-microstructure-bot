// @vitest-environment node
// Regresiones dirigidas de control.guard (mutex corto entre procesos).
//
// Corresponde a la corrección final acotada del guard (alternativa acotada):
//   - Nunca se borra un guard huérfano automáticamente.
//   - acquireGuard devuelve una causa explícita:
//       OWNER_ALIVE   : propietario vivo, se conserva la exclusión (A).
//       GUARD_ORPHANED: propietario muerto, se conserva el guard (C-recuperación).
//       IDENTITY_UNCERTAIN: ilegible / sin token / EPERM / error de inspección
//                         / PID inválido, se conserva la exclusión (D).
//   - releaseGuard libera condicionada por identidad completa (B).
//
// El mismo archivo se ejecuta contra el código con el defecto (debe FALLAR:
// A, C-recuperación, D) y contra el código corregido (debe PASAR).
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {execSync, spawn, type ChildProcess} from "node:child_process";
import {
  createWriteStream, existsSync, mkdirSync, mkdtempSync, readFileSync,
  rmSync, writeFileSync, utimesSync} from "node:fs";
import {join} from "node:path";
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
  // Limpieza exclusiva de procesos y temporales creados por la prueba.
  for (const child of children.splice(0)) {
    try { child.kill("SIGKILL"); } catch { /* ignore */ }
  }
  try { rmSync(resultsDir, {recursive: true, force: true }); } catch { /* ignore */ }
  try { rmSync(fakeRoot, {recursive: true, force: true }); } catch { /* ignore */ }
});

const load = () => import("@/lib/backtest-control");
const EXP = "eval-census-v2-trio";
const expDir = () => join(resultsDir, EXP);
const guardPath = () => join(expDir(), "control.guard");
const GUARD_STALE_MS = 30_000; // referencia documentada; ya no se usa para borrar

type GuardHandle = {path: string; pid: number; acquired_at_ms: number; token: string};

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

// Ruta absoluta al punto de entrada del control (para bundlear con esbuild).
const CONTROL_SRC = join(__dirname, "..", "lib", "backtest-control.ts")
  .replace(/\\/g, "/");

function bundleGuard(): string {
  const bundlePath = join(resultsDir, "guard-bundle.js");
  execSync(
    `npx esbuild "${CONTROL_SRC}" --bundle --platform=node --format=cjs ` +
    `--outfile="${bundlePath}"`,
    {stdio: "pipe", encoding: "utf8"});
  return bundlePath;
}

// Script hijo (JS puro, sin TS) que intenta adquirir el guard y escribe su
// resultado a un archivo de salida. Espera a la barrera de inicio antes de
// adquirir, para forzar la carrera real entre procesos independientes.
function writeChildScript(bundlePath: string): string {
  const childPath = join(resultsDir, "guard-child.js");
  // IIFE async: CJS no permite await a nivel superior del módulo.
  const src = [
    `(async () => {`,
    `  try {`,
    `    const {acquireGuard} = require("${bundlePath.replace(/\\/g, "/")}");`,
    `    const {existsSync, writeFileSync} = require("fs");`,
    `    const out = process.argv[2];`,
    `    const exp = process.argv[3];`,
    `    const startFlag = process.argv[4];`,
    // Barrera: esperar a que el padre señale el inicio (todos los hijos
    // llaman a acquireGuard al mismo instante).
    `    let waited = 0;`,
    `    while (!existsSync(startFlag) && waited < 10000) {`,
    `      await new Promise(res => setTimeout(res, 50)); waited += 50;`,
    `    }`,
    `    if (!existsSync(startFlag)) {`,
    `      writeFileSync(out, JSON.stringify({error: "BARRIER_TIMEOUT"}));`,
    `      process.exit(1);`,
    `    }`,
    `    const r = acquireGuard(exp);`,
    `    writeFileSync(out, JSON.stringify({pid: process.pid, result: r}));`,
    `  } catch (e) {`,
    `    try { writeFileSync(process.argv[2], JSON.stringify({pid: process.pid, error: String(e)})); } catch { /* ignore */ }`,
    `    process.exit(1);`,
    `  }`,
    `})();`,
  ].join("\n");
  writeFileSync(childPath, src);
  return childPath;
}

// ---------------------------------------------------------------------------
// Caso A: propietario vivo durante mas de 30s -> OWNER_ALIVE, no adquiere
// ---------------------------------------------------------------------------
describe("control.guard: identidad y exclusión de sección crítica", () => {
  it("A: propietario activo durante mas de 30s -> OWNER_ALIVE, no adquiere, conserva", async () => {
    const owner = spawnOwner();
    // El guard pertenece a un propietario VIVO, mtime antiguo (>30s).
    writeGuard(owner.pid!, Date.now() - 60_000, "tok-viejo",
      Date.now() - (GUARD_STALE_MS + 5_000));
    const mod = await load();
    const r = mod.acquireGuard(EXP);
    expect(r.kind).toBe("rejected");
    if (r.kind !== "rejected") throw new Error("esperado rejected");
    expect(r.reason).toBe("OWNER_ALIVE");
    expect(existsSync(guardPath())).toBe(true); // el guard del propietario persiste
    const content = readGuardRaw();
    expect(content).toContain("tok-viejo"); // no fue reemplazado
  }, 60_000);

  // -------------------------------------------------------------------------
  // Caso B: liberación tardía de A nunca retira el guard de B (mismo PID,
  // distinto token de adquisición). Se prueba releaseGuard directamente.
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
  // Caso C1: guard huérfano + N procesos concurrentes -> GUARD_ORPHANED para
  // TODOS, el guard se conserva (ningún borrado automático, no hay carrera).
  // -------------------------------------------------------------------------
  it("C1: guard huérfano + procesos concurrentes -> GUARD_ORPHANED, se conserva", async () => {
    // Guard huérfano: PID que no existe, mtime antiguo, CON token (identidad
    // completa pero propietario muerto) -> GUARD_ORPHANED.
    writeGuard(999999, Date.now() - 60_000, "tok-huerfano",
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

    // Esperar resultados válidos de TODOS los hijos, con timeout acotado.
    const results = await Promise.all(outFiles.map((f) =>
      new Promise<unknown>((resolve, reject) => {
        const t = setTimeout(() => {
          // Diagnosticar: leer stderr/stdout del hijo correspondiente.
          const idx = outFiles.indexOf(f);
          const errLog = join(resultsDir, `child-${idx}.err`);
          let errDetail = "";
          try { errDetail = readFileSync(errLog, "utf8"); } catch { /* ignore */ }
          reject(new Error(`timeout hijo ${f}. stderr: ${errDetail}`));
        }, 10_000);
        const iv = setInterval(() => {
          if (existsSync(f)) {
            clearTimeout(t); clearInterval(iv);
            try { resolve(JSON.parse(readFileSync(f, "utf8"))); }
            catch { resolve({error: "INVALID_JSON", file: f}); }
          }
        }, 100);
      })));

    // Cada hijo debe haber escrito un resultado válido (no ausente, no error).
    for (const res of results) {
      expect(res).not.toHaveProperty("error", "BARRIER_TIMEOUT");
      expect(res).not.toHaveProperty("error", "INVALID_JSON");
      expect(res).toHaveProperty("result");
    }

    // Propiedad de exclusión: NINGÚN proceso adquiere el guard huérfano
    // (todos devuelven GUARD_ORPHANED), porque no hay borrado automático.
    const acquired = results.filter((r) =>
      (r as {result?: {kind?: string}}).result?.kind === "acquired");
    expect(acquired.length).toBe(0); // cero propietarios automáticos

    const orphans = results.filter((r) =>
      (r as {result?: {reason?: string}}).result?.reason === "GUARD_ORPHANED");
    expect(orphans.length).toBe(N); // todos reportan GUARD_ORPHANED

    // Ningún hijo debe haber tenido error de barrera ni JSON inválido.
    for (const res of results) {
      expect((res as {error?: string}).error).toBeUndefined();
    }

    // El guard huérfano se conserva intacto (ningún proceso lo borró).
    expect(existsSync(guardPath())).toBe(true);
    const final = JSON.parse(readGuardRaw()!);
    expect(final.pid).toBe(999999); // sigue siendo el guard huérfano original

    // Limpieza: mata a todos los hijos.
    for (const p of procs) { try { p.kill("SIGKILL"); } catch { /* ignore */ } }
  }, 60_000);

  // -------------------------------------------------------------------------
  // Caso C2: guard válido VIVO (sección crítica) + N procesos concurrentes ->
  // TODOS OWNER_ALIVE, el guard del propietario vivo se conserva.
  // Demuestra exclusión durante toda la sección crítica: el ganador (proceso
  // padre) se mantiene vivo hasta completar la comprobación.
  // -------------------------------------------------------------------------
  it("C2: guard válido vivo + procesos concurrentes -> OWNER_ALIVE, exclusión", async () => {
    const mod = await load();

    // El proceso PADRE adquiere un guard válido (no existe guard previo) y se
    // mantiene vivo durante toda la sección crítica hasta completar la comprobación.
    const ownerResult = mod.acquireGuard(EXP);
    expect(ownerResult.kind).toBe("acquired");
    if (ownerResult.kind !== "acquired") throw new Error("esperado acquired");
    const ownerGuard = ownerResult.guard;

    // Verificar que el guard existe y pertenece al padre.
    expect(existsSync(guardPath())).toBe(true);
    const written = JSON.parse(readGuardRaw()!);
    expect(written.pid).toBe(process.pid);
    expect(written.token).toBe(ownerGuard.token);

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

    // Señal de inicio: todos los hijos intentan adquirir mientras el padre
    // sigue siendo el propietario activo (sección crítica abierta).
    writeFileSync(startFlag, "");

    // Esperar resultados válidos de TODOS los hijos.
    const results = await Promise.all(outFiles.map((f) =>
      new Promise<unknown>((resolve, reject) => {
        const t = setTimeout(() => reject(new Error(`timeout hijo ${f}`)), 10_000);
        const iv = setInterval(() => {
          if (existsSync(f)) {
            clearTimeout(t); clearInterval(iv);
            try { resolve(JSON.parse(readFileSync(f, "utf8"))); }
            catch { resolve({error: "INVALID_JSON", file: f}); }
          }
        }, 100);
      })));

    // Ningún hijo debe haber adquirido el guard (todos OWNER_ALIVE).
    for (const res of results) {
      const r = (res as {result?: {kind?: string; reason?: string}}).result;
      expect(r?.kind).toBe("rejected");
      expect(r?.reason).toBe("OWNER_ALIVE");
    }

    // El guard del padre sigue intacto (ningún hijo lo borró ni reemplazó).
    expect(existsSync(guardPath())).toBe(true);
    const stillOwner = JSON.parse(readGuardRaw()!);
    expect(stillOwner.pid).toBe(process.pid);
    expect(stillOwner.token).toBe(ownerGuard.token);

    // Liberación condicionada: el padre libera su propio guard.
    mod.releaseGuard(ownerGuard);
    expect(existsSync(guardPath())).toBe(false);

    // Limpieza: mata a todos los hijos.
    for (const p of procs) { try { p.kill("SIGKILL"); } catch { /* ignore */ } }
  }, 60_000);

  // -------------------------------------------------------------------------
  // Caso D: identidad incierta -> conservar exclusión y reportar causa.
  // -------------------------------------------------------------------------
  it("D1: guard ilegible (no JSON) -> IDENTITY_UNCERTAIN, conserva el guard", async () => {
    mkdirSync(expDir(), {recursive: true});
    writeFileSync(guardPath(), "no-es-json-{{{");
    utimesSync(guardPath(), new Date(Date.now() - 60_000),
      new Date(Date.now() - (GUARD_STALE_MS + 5_000)));
    const mod = await load();
    const g = mod.acquireGuard(EXP);
    expect(g.kind).toBe("rejected");
    if (g.kind !== "rejected") throw new Error("esperado rejected");
    expect(g.reason).toBe("IDENTITY_UNCERTAIN"); // identidad incierta: fail-closed
    expect(existsSync(guardPath())).toBe(true); // no borra el guard ilegible
    expect(readGuardRaw()).toBe("no-es-json-{{{");
  }, 60_000);

  it("D2: guard sin token (identidad incompleta) -> IDENTITY_UNCERTAIN, conserva", async () => {
    writeGuard(process.pid, Date.now() - 60_000, null,
      Date.now() - (GUARD_STALE_MS + 5_000));
    const mod = await load();
    const g = mod.acquireGuard(EXP);
    expect(g.kind).toBe("rejected");
    if (g.kind !== "rejected") throw new Error("esperado rejected");
    expect(g.reason).toBe("IDENTITY_UNCERTAIN"); // sin token: identidad incompleta
    expect(existsSync(guardPath())).toBe(true);
  }, 60_000);

  it("D3: EPERM (proceso existe, sin permisos) -> IDENTITY_UNCERTAIN, conserva", async () => {
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
      expect(g.kind).toBe("rejected");
      if (g.kind !== "rejected") throw new Error("esperado rejected");
      expect(g.reason).toBe("IDENTITY_UNCERTAIN"); // EPERM: no se asume muerto
      expect(existsSync(guardPath())).toBe(true);
    } finally {
      killSpy.mockRestore();
    }
  }, 60_000);

  it("D4: PID desconocido (ESRCH, gone) -> GUARD_ORPHANED, conserva el guard", async () => {
    writeGuard(888888, Date.now() - 60_000, "tok-muerto",
      Date.now() - (GUARD_STALE_MS + 5_000));
    const mod = await load();
    const g = mod.acquireGuard(EXP);
    expect(g.kind).toBe("rejected");
    if (g.kind !== "rejected") throw new Error("esperado rejected");
    expect(g.reason).toBe("GUARD_ORPHANED"); // PID gone: se conserva, causa explícita
    expect(existsSync(guardPath())).toBe(true); // NO se borra automáticamente
    expect(readGuardRaw()).toContain("tok-muerto");
  }, 60_000);

  it("D5: error de inspección desconocido -> IDENTITY_UNCERTAIN, conserva", async () => {
    const owner = spawnOwner();
    writeGuard(owner.pid!, Date.now() - 60_000, "tok-vivo-error",
      Date.now() - (GUARD_STALE_MS + 5_000));
    const killSpy = vi.spyOn(process, "kill").mockImplementation(() => {
      const err: NodeJS.ErrnoException & {code?: string} = new Error("EACCES");
      err.code = "EACCES";
      throw err;
    });
    try {
      const mod = await load();
      const g = mod.acquireGuard(EXP);
      expect(g.kind).toBe("rejected");
      if (g.kind !== "rejected") throw new Error("esperado rejected");
      expect(g.reason).toBe("IDENTITY_UNCERTAIN"); // error desconocido: conserva
      expect(existsSync(guardPath())).toBe(true);
    } finally {
      killSpy.mockRestore();
    }
  }, 60_000);
});