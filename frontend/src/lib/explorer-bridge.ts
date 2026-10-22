// Puente BFF -> CLI Python del explorador de mercado (solo REST público).
//
// Mismo criterio que el puente de Paper Lab: el backend Python es la autoridad;
// el frontend solo solicita acciones de una lista permitida y presenta el JSON
// resultante. No se aceptan rutas, comandos ni credenciales desde el cliente.

import {spawnSync} from "node:child_process";
import {join} from "node:path";

const ROOT = process.env.MARKET_EXPLORER_ROOT ??
  "C:/proyectos/binance-futures-microstructure-bot";
const PYTHON = process.env.MARKET_EXPLORER_PYTHON ?? "python";
const SCRIPT = join(ROOT, "scripts", "market_explorer.py");

export interface BridgeResult {
  ok: boolean;
  data?: unknown;
  error?: string;
  detail?: string;
}

export function runMarketExplorer(args: string[]): BridgeResult {
  const result = spawnSync(
    PYTHON, [SCRIPT, ...args],
    {
      cwd: ROOT, encoding: "utf8", timeout: 45_000,
      maxBuffer: 8 * 1024 * 1024, windowsHide: true,
      env: {...process.env, PYTHONPATH: ROOT + "/src"},
    },
  );
  let raw = (result.stdout || "").trim();
  if (!raw && result.status !== 0) raw = (result.stderr || "").trim();
  if (!raw) {
    return {
      ok: false,
      error: result.error ? "PYTHON_SPAWN_FAILED" : "PYTHON_EMPTY_OUTPUT",
      detail: (result.error?.message ?? result.stderr ?? "").slice(-500),
    };
  }
  try {
    const parsed = JSON.parse(raw) as BridgeResult;
    return parsed;
  } catch {
    // El CLI puede escribir el JSON de error en stderr con código != 0.
    const lines = raw.split(/\r?\n/).filter(Boolean);
    const last = lines[lines.length - 1] ?? "";
    try {
      return JSON.parse(last) as BridgeResult;
    } catch {
      return {ok: false, error: "PYTHON_BAD_JSON", detail: raw.slice(-300)};
    }
  }
}

/**
 * Origen local acotado. Acepta 127.0.0.1:3020 y localhost:3020 (misma
 * instancia del dashboard) y rechaza cualquier otro origen o host.
 */
export function explorerOriginAllowed(req: Request): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  if (host !== "127.0.0.1:3020" && host !== "localhost:3020") return false;
  return origin === null || origin === `http://${host}`;
}

export function statusForError(error?: string): number {
  if (error === "VALIDATION_ERROR" || error === "ACTION_NOT_ALLOWED"
    || error === "INVALID_QUERY" || error === "INVALID_LIMIT"
    || error === "INVALID_SYMBOL" || error === "INVALID_INTERVAL"
    || error === "INVALID_RANGE") {
    return 400;
  }
  return 502;
}
