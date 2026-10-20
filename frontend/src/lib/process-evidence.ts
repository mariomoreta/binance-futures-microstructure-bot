// Evidencia INDEPENDIENTE del proceso del sistema operativo.
//
// Un PID por si solo no prueba propiedad: puede ser ajeno, estar reutilizado o
// pertenecer a un proceso que ya termino. Este modulo consulta el sistema
// operativo (no los archivos de estado del backtest) para obtener:
//   - si el PID existe;
//   - cuando se creo ese proceso (instancia, no solo numero);
//   - su linea de comandos (posesion del token/run_id de la ejecucion).
//
// Solo lectura. Nunca envia senales distintas de 0 y NUNCA mata procesos.
// Si la evidencia no esta disponible (sin permisos, plataforma desconocida o
// salida ilegible) devuelve `null` en el campo correspondiente para que el
// llamante lo trate como UNKNOWN, nunca como verificado.
import {spawnSync} from "node:child_process";
import {readFileSync} from "node:fs";
import os from "node:os";

export type ProcessEvidence = {
  pid: number;
  alive: boolean;
  creation_ms: number | null;
  command_line: string | null;
  source: "proc" | "cim" | "ps" | "none";
};

function validPid(pid: number): boolean {
  return Number.isSafeInteger(pid) && pid > 0;
}

function liveness(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    // EPERM = el proceso existe pero no podemos senalizarlo.
    return (e as NodeJS.ErrnoException).code === "EPERM";
  }
}

function fromProc(pid: number): {creation_ms: number | null; command_line: string | null} {
  const n = process.platform === "linux" ? 100 : 100;
  let creation_ms: number | null = null;
  let command_line: string | null = null;
  try {
    const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
    const close = stat.lastIndexOf(")");
    if (close > 0) {
      const fields = stat.slice(close + 1).trim().split(/\s+/);
      // Tras "(comm)" el primer campo es state (campo 3); starttime es el 22.
      const startTicks = Number(fields[19]);
      if (Number.isFinite(startTicks)) {
        const bootMs = Date.now() - os.uptime() * 1000;
        creation_ms = Math.round(bootMs + (startTicks / n) * 1000);
      }
    }
  } catch {
    creation_ms = null;
  }
  try {
    command_line = readFileSync(`/proc/${pid}/cmdline`, "utf8")
      .split("\u0000").filter(Boolean).join(" ");
    if (!command_line) command_line = null;
  } catch {
    command_line = null;
  }
  return {creation_ms, command_line};
}

function fromCim(pid: number): {creation_ms: number | null; command_line: string | null} {
  // Una sola consulta devuelve instancia y linea de comandos. Se interpola
  // solo un entero ya validado.
  // FileTime (ticks UTC desde 1601) evita que el literal de epoch se
  // interprete en la zona horaria local, que desplazaba la instancia horas.
  const script = "$p=Get-CimInstance Win32_Process -Filter 'ProcessId=" + pid + "'; "
    + "if($p){$c=$p.CreationDate.ToUniversalTime();"
    + "$ms=[int64]($c.ToFileTimeUtc()/10000)-11644473600000;"
    + "[pscustomobject]@{ProcessId=$p.ProcessId;CreationMs=$ms;"
    + "CommandLine=$p.CommandLine}|ConvertTo-Json -Compress}else{''}";
  const r = spawnSync("powershell", ["-NoLogo", "-NoProfile", "-NonInteractive",
    "-Command", script], {encoding: "utf8", windowsHide: true, timeout: 20_000});
  if (r.status !== 0 || !r.stdout) return {creation_ms: null, command_line: null};
  try {
    const parsed = JSON.parse(r.stdout.trim()) as
      {CreationMs?: unknown; CommandLine?: unknown};
    return {
      creation_ms: typeof parsed.CreationMs === "number" && Number.isFinite(parsed.CreationMs)
        ? parsed.CreationMs : null,
      command_line: typeof parsed.CommandLine === "string" && parsed.CommandLine.length > 0
        ? parsed.CommandLine : null,
    };
  } catch {
    return {creation_ms: null, command_line: null};
  }
}

function fromPs(pid: number): {creation_ms: number | null; command_line: string | null} {
  const r = spawnSync("ps", ["-p", String(pid), "-o", "lstart=", "-o", "command="],
    {encoding: "utf8", windowsHide: true, timeout: 20_000});
  if (r.status !== 0 || !r.stdout) return {creation_ms: null, command_line: null};
  const line = r.stdout.trim();
  if (!line) return {creation_ms: null, command_line: null};
  // lstart tiene 5 tokens (dow mon dd hh:mm:ss yyyy); el resto es command.
  const parts = line.split(/\s+/);
  const stamp = parts.slice(0, 5).join(" ");
  const parsed = Date.parse(stamp);
  return {
    creation_ms: Number.isFinite(parsed) ? parsed : null,
    command_line: parts.slice(5).join(" ") || null,
  };
}

/**
 * Evidencia del proceso `pid`.
 *
 * No hay cache por PID: el sistema operativo puede RECICLAR un PID y entonces
 * la evidencia guardada de una instancia anterior describiria a otro proceso.
 * Como la identidad del ejecutor es una decision de seguridad (exclusion,
 * liberacion de lock y retencion), se consulta siempre el estado actual.
 */
export function inspectProcess(pid: number): ProcessEvidence {
  if (!validPid(pid)) {
    return {pid, alive: false, creation_ms: null, command_line: null, source: "none"};
  }
  const alive = liveness(pid);
  let detail: {creation_ms: number | null; command_line: string | null} =
    {creation_ms: null, command_line: null};
  let source: ProcessEvidence["source"] = "none";
  if (alive) {
    if (process.platform === "linux") {
      detail = fromProc(pid); source = "proc";
    } else if (process.platform === "win32") {
      detail = fromCim(pid); source = "cim";
    } else {
      detail = fromPs(pid); source = "ps";
    }
  }
  return {pid, alive, ...detail, source};
}
