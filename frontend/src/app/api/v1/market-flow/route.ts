// Flujo agresivo comprador/vendedor — contrato `market-flow/v1`.
//
// Backend Python como unica autoridad (flow.py + market_flow_service.py);
// el frontend solo solicita y presenta. Transporte local exclusivamente:
// sin conexion a Binance publico, sin cobertura antes del primer evento de
// captura, sin reconstruccion desde OHLC. Sin fuente conectada: SIN
// COBERTURA, valores desconocidos, live=false.
//
// Delta positivo NO es senal alcista automatica: solo describe el saldo de
// volumen agresor en ventana.

import {NextResponse} from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8799;
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

function emptyBlock(symbol: string, asOfMs: number): Record<string, unknown> {
  return {
    contract_version: "market-flow/v1",
    availability: "LIVE_CAPTURE_ONLY",
    coverage: "NO_COVERAGE_BEFORE_FIRST_EVENT",
    identity: {symbol, venue: "binance", market_type: "usd_m_futures",
               source: "aggTrade_local_transport"},
    as_of_ms: asOfMs,
    freshness_ms: null,
    live: false,
    trades_total: 0,
    horizons: {},
    baselines: {},
    acceleration: {},
    deduplication: {seen_event_ids: 0},
    notes: ["Sin servicio de flujo conectado: sin cobertura, sin valores ni ceros inventados."],
  };
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
  const asOfMs = intParam(params, "as_of_ms") ?? Date.now();

  const flowHost = process.env.MARKET_FLOW_HOST ?? DEFAULT_HOST;
  const flowPort = Number(process.env.MARKET_FLOW_PORT ?? DEFAULT_PORT);
  const url = `http://${flowHost}:${flowPort}/flow?symbol=${encodeURIComponent(symbol)}&as_of_ms=${asOfMs}`;

  try {
    const res = await fetch(url, {cache: "no-store", signal: AbortSignal.timeout(5000)});
    if (!res.ok) {
      return NextResponse.json({
        ok: false,
        data: emptyBlock(symbol, asOfMs),
        error: `HTTP_${res.status}`,
      }, {headers});
    }
    const json = await res.json();
    if (!json.ok) {
      // El servicio devolvio error: SIN COBERTURA, no rellenar con sinteticos.
      return NextResponse.json({
        ok: false,
        data: emptyBlock(symbol, asOfMs),
        error: json.error ?? "FLOW_SERVICE_ERROR",
        detail: json.detail ?? null,
      }, {headers});
    }
    return NextResponse.json({ok: true, data: json.data}, {headers});
  } catch (err) {
    // Cualquier error de red/servicio no alcanzado: SIN COBERTURA, sin
    // sinteticos, live=false, HTTP 200.
    return NextResponse.json({
      ok: false,
      data: emptyBlock(symbol, asOfMs),
      error: "FLOW_SERVICE_NOT_REACHABLE",
      detail: err instanceof Error ? err.message : String(err),
    }, {headers});
  }
}
