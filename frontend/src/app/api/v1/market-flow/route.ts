// Flujo agresivo comprador/vendedor — contrato `market-flow/v1`.
//
// Backend Python como unica autoridad (flow.py + market_flow.py); el frontend
// solo solicita y presenta. Transporte local exclusivamente: sin conexion a
// Binance publico, sin cobertura antes del primer evento de captura, sin
// reconstruccion desde OHLC.
//
// Delta positivo NO es senal alcista automatica: solo describe el saldo de
// volumen agresor en ventana.

import {randomUUID} from "node:crypto";
import {spawnSync} from "node:child_process";
import {join} from "node:path";
import {NextResponse} from "next/server";

const ROOT = process.env.MARKET_FLOW_ROOT ??
  "C:/proyectos/binance-futures-microstructure-bot";
const PYTHON = process.env.MARKET_FLOW_PYTHON ?? "python";
const SCRIPT = join(ROOT, "scripts", "market_flow.py");

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

const SYMBOL_RE = /^[A-Z0-9]{2,32}$/;

function intParam(params: URLSearchParams, name: string): number | null | undefined {
  const values = params.getAll(name);
  if (values.length === 0) return undefined;
  if (values.length > 1) return null;
  const raw = values[0] ?? "";
  if (!/^-?\d{1,16}$/.test(raw)) return null;
  const value = Number(raw);
  return Number.isSafeInteger(value) ? value : null;
}

export async function GET(req: Request) {
  // Origen local acotado: solo la misma instancia del dashboard.
  const host = req.headers.get("host");
  if (host !== "127.0.0.1:3020" && host !== "localhost:3020") {
    return NextResponse.json({error: "FORBIDDEN_ORIGIN"}, {status: 403, headers});
  }
  const origin = req.headers.get("origin");
  if (origin !== null && origin !== `http://${host}`) {
    return NextResponse.json({error: "FORBIDDEN_ORIGIN"}, {status: 403, headers});
  }

  const params = new URL(req.url).searchParams;
  const symbol = (params.get("symbol") ?? "").trim().toUpperCase();
  if (!SYMBOL_RE.test(symbol)) {
    return NextResponse.json({error: "INVALID_SYMBOL"}, {status: 400, headers});
  }
  const asOfMs = intParam(params, "as_of_ms");
  if (asOfMs === undefined || asOfMs === null) {
    return NextResponse.json({error: "INVALID_AS_OF_MS"}, {status: 400, headers});
  }

  // Un id de ejecucion por peticion: vincula al ledger de presupuesto si
  // el CLI lo usa; aqui se propaga para trazabilidad.
  const args = [
    "--symbol", symbol,
    "--as-of-ms", String(asOfMs),
  ];
  const result = spawnSync(
    PYTHON, [SCRIPT, ...args],
    {
      cwd: ROOT, encoding: "utf8", timeout: 30_000,
      maxBuffer: 8 * 1024 * 1024, windowsHide: true,
      env: {...process.env, PYTHONPATH: ROOT + "/src"},
    },
  );
  let raw = (result.stdout || "").trim();
  if (!raw && result.status !== 0) raw = (result.stderr || "").trim();
  if (!raw) {
    return NextResponse.json({
      error: result.error ? "PYTHON_SPAWN_FAILED" : "PYTHON_EMPTY_OUTPUT",
      detail: (result.error?.message ?? result.stderr ?? "").slice(-500),
    }, {status: 502, headers});
  }
  try {
    const parsed = JSON.parse(raw);
    if (!parsed.ok) {
      return NextResponse.json({error: parsed.error ?? "FLOW_ERROR",
        detail: parsed.detail ?? null}, {status: 502, headers});
    }
    return NextResponse.json(parsed.data, {headers});
  } catch {
    return NextResponse.json({error: "FLOW_BAD_JSON", detail: raw.slice(-300)},
      {status: 502, headers});
  }
}
