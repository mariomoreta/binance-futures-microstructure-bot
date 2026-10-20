// @vitest-environment node
// Regresiones dirigidas de control.guard (mutex corto entre procesos).
//
// Reproduce y resuelve:
//   A. Propietario activo durante mas de 30 segundos: una segunda solicitud
//      NO puede adquirir la seccion critica (la antigüedad no es muerte).
//   B. Liberacion tardia de A: nunca elimina el guard de B (liberacion
//      condicionada a identidad/propiedad).
//   C. Propietario muerto: recuperacion segura, sin dos ganadores concurrentes.
//   D. Identidad incierta: conservar exclusión y reportar causa.
//
// El mismo archivo se ejecuta contra el codigo con el defecto (debe FALLAR:
// A/B/D se reproducen) y contra el codigo corregido (debe PASAR).
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {spawn, type ChildProcess} from "node:child_process";
import {
  existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync,
  utimesSync,
} from "node:fs";
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
  for (const child of children.splice(0)) {
    try { child.kill(); } catch { /* ignore */ }
  }
  try { rmSync(resultsDir, {recursive: true, force: true}); } catch { /* ignore */ }
  try { rmSync(fakeRoot, {recursive: true, force: true}); } catch { /* ignore */ }
});

const load = () => import("@/lib/backtest-control");
const EXP = "eval-census-v2-trio";
const expDir = () => join(resultsDir, EXP);
const guardPath = () => join(expDir(), "control.guard");
const GUARD_STALE_MS = 30_000;

// Escribe un guard simulado {pid, acquired_at_ms} y fija su mtime.
// pid puede ser null para simular identidad del propietario no verificable.
function writeGuard(pid: number | null, acquiredAtMs: number, mtimeMs?: number): void {
  mkdirSync(expDir(), {recursive: true});
  writeFileSync(guardPath(), JSON.stringify({pid, acquired_at_ms: acquiredAtMs}));
  if (mtimeMs !== undefined) {
    const ref = Date.now() - 60_000;
    utimesSync(guardPath(), new Date(ref), new Date(mtimeMs));
  }
}

function readGuard(): {pid?: unknown; acquired_at_ms?: unknown} | null {
  try {
    const raw = readFileSync(guardPath(), "utf8");
    return JSON.parse(raw) as {pid?: unknown; acquired_at_ms?: unknown};
  } catch {
    return null;
  }
}

// Proceso hijo vivo cuyo pid conocemos (propietario del guard).
function spawnOwner(): ChildProcess {
  const child = spawn(process.execPath, [
    "-e", "setTimeout(()=>{},120000)",
  ], {stdio: "ignore", windowsHide: true});
  children.push(child);
  return child;
}

function guardContent(): string | null {
  try { return readFileSync(guardPath(), "utf8"); } catch { return null; }
}

describe("control.guard: exclusión entre procesos (propiedad verificable)", () => {
  it("A: propietario activo durante mas de 30s -> segunda solicitud no adquiere", async () => {
    const owner = spawnOwner();
    // El guard pertenece a un propietario VIVO, pero tiene mtime antiguo (>30s).
    writeGuard(owner.pid!, Date.now() - 60_000, Date.now() - (GUARD_STALE_MS + 5_000));
    const mod = await load();
    const g = mod.acquireGuard(EXP);
    expect(g).toBeNull(); // segunda solicitud no adquiere: propietario activo
    expect(existsSync(guardPath())).toBe(true); // el guard del propietario persiste
    const content = readGuard();
    expect(content?.pid).toBe(owner.pid); // no fue reemplazado
  }, 60_000);

  it("B (fail-before / pass-after): liberacion tardia de A nunca elimina el guard de B", async () => {
    const owner = spawnOwner();
    // A (el hijo) adquiere el guard y vive; su mtime se vuelve antiguo.
    writeGuard(owner.pid!, Date.now() - 60_000, Date.now() - (GUARD_STALE_MS + 5_000));
    const mod = await load();

    // Intento de B mientras A vive y el guard es "antiguo".
    const bGuard = mod.acquireGuard(EXP);
    // Con la corrección: B no adquiere porque el propietario (A) sigue vivo.
    expect(bGuard).toBeNull();
    expect(readGuard()?.pid).toBe(owner.pid); // el guard sigue siendo de A

    // B simula que cree que posee el guard (pid ajeno) y libera tarde:
    // la liberacion condicionada NO debe borrar el guard de A.
    mod.releaseGuard({path: guardPath(), pid: 999999, acquired_at_ms: 0});
    expect(existsSync(guardPath())).toBe(true); // el guard de A no fue borrado
    expect(readGuard()?.pid).toBe(owner.pid);
  }, 60_000);

  it("C: propietario muerto -> recuperacion segura, sin dos ganadores concurrentes", async () => {
    // Guard huérfano: pid que no existe, mtime antiguo.
    writeGuard(999999, Date.now() - 60_000, Date.now() - (GUARD_STALE_MS + 5_000));
    const mod = await load();
    const g1 = mod.acquireGuard(EXP);
    expect(g1).not.toBeNull(); // recupera el guard huérfano
    // Un segundo intento concurrente no debe ganar: el guard ya es de este proceso.
    const g2 = mod.acquireGuard(EXP);
    expect(g2).toBeNull();
    expect(readGuard()?.pid).toBe(process.pid);
    mod.releaseGuard(g1!);
    expect(existsSync(guardPath())).toBe(false); // liberado por su propietario
  }, 60_000);

  it("D: identidad incierta -> conservar exclusión y reportar causa", async () => {
    // Guard ilegible (no JSON): identidad del propietario incierta -> fail-closed.
    mkdirSync(expDir(), {recursive: true});
    writeFileSync(guardPath(), "no-es-json-{{{");
    utimesSync(guardPath(), new Date(Date.now() - 60_000),
      new Date(Date.now() - (GUARD_STALE_MS + 5_000)));
    const mod = await load();
    const g = mod.acquireGuard(EXP);
    expect(g).toBeNull(); // no adquiere: identidad incierta, conserva exclusión
    expect(existsSync(guardPath())).toBe(true); // no borra el guard ilegible

    // Guard sin pid válido: misma conducta (fail-closed).
    writeGuard(null, Date.now() - 60_000,
      Date.now() - (GUARD_STALE_MS + 5_000));
    const g2 = mod.acquireGuard(EXP);
    expect(g2).toBeNull();
    expect(existsSync(guardPath())).toBe(true);
  }, 60_000);
});
