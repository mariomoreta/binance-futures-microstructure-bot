// Flujo agresivo comprador/vendedor — contrato `market-flow/v1`.
// BFF puro proxy: no calcula flujo ni mantiene estado. Consulta al servicio
// Python de mercado (`market_stream_service`, puerto 8791) y reenvía su SSE.
// Transporte local exclusivamente: sin conexión a Binance público, sin
// cobertura antes del primer evento de captura, sin reconstrucción desde OHLC.
//
// Delta positivo NO es señal alcista automática: solo describe el saldo de
// volumen agresor en ventana.

import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "no-store" };

const FLOW_SERVICE_HOST = "127.0.0.1";
const FLOW_SERVICE_PORT = 8792;
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

function flowServiceUrl(symbol: string, asOfMs?: number): string {
  const qs = new URLSearchParams({ symbol });
  if (asOfMs !== undefined) qs.set("as_of_ms", String(asOfMs));
  return `http://${FLOW_SERVICE_HOST}:${FLOW_SERVICE_PORT}/flow?${qs.toString()}`;
}

function flowServiceStreamUrl(symbol: string): string {
  return `http://${FLOW_SERVICE_HOST}:${FLOW_SERVICE_PORT}/flow/stream?symbol=${encodeURIComponent(symbol)}`;
}

export async function GET(req: Request) {
  // Origen local acotado: solo la misma instancia del dashboard.
  const host = req.headers.get("host");
  if (host !== "127.0.0.1:3020" && host !== "localhost:3020") {
    return NextResponse.json({ error: "FORBIDDEN_ORIGIN" }, { status: 403, headers });
  }
  const origin = req.headers.get("origin");
  if (origin !== null && origin !== `http://${host}`) {
    return NextResponse.json({ error: "FORBIDDEN_ORIGIN" }, { status: 403, headers });
  }

  const params = new URL(req.url).searchParams;
  const symbol = (params.get("symbol") ?? "").trim().toUpperCase();
  if (!SYMBOL_RE.test(symbol)) {
    return NextResponse.json({ error: "INVALID_SYMBOL" }, { status: 400, headers });
  }
  const asOfMs = intParam(params, "as_of_ms") ?? Date.now();

  // Proxy al servicio Python de mercado (única autoridad de flujo).
  let res: Response;
  try {
    res = await fetch(flowServiceUrl(symbol, asOfMs), {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
      headers: { "Accept": "application/json" },
    });
  } catch (err) {
    // Servicio no alcanzado: SIN COBERTURA, sin sinteticos, live=false.
    return NextResponse.json({
      ok: false,
      data: {
        contract_version: "market-flow/v1",
        availability: "LIVE_CAPTURE_ONLY",
        coverage: "NO_COVERAGE_BEFORE_FIRST_EVENT",
        identity: { symbol, venue: "binance", market_type: "usd_m_futures",
          source: "aggTrade_local_transport" },
        as_of_ms: asOfMs,
        freshness_ms: null,
        live: false,
        trades_total: 0,
        horizons: {},
        baselines: {},
        acceleration: {},
        deduplication: { seen_event_ids: 0, max_event_ids: 10_000 },
        notes: ["Sin servicio de flujo conectado: sin cobertura, sin valores "
          + "ni ceros inventados."],
      },
      error: "FLOW_SERVICE_NOT_REACHABLE",
      detail: err instanceof Error ? err.message : String(err),
    }, { headers });
  }

  if (!res.ok) {
    return NextResponse.json({
      ok: false,
      data: {
        contract_version: "market-flow/v1",
        availability: "LIVE_CAPTURE_ONLY",
        coverage: "NO_COVERAGE_BEFORE_FIRST_EVENT",
        identity: { symbol, venue: "binance", market_type: "usd_m_futures",
          source: "aggTrade_local_transport" },
        as_of_ms: asOfMs,
        freshness_ms: null,
        live: false,
        trades_total: 0,
        horizons: {},
        baselines: {},
        acceleration: {},
        deduplication: { seen_event_ids: 0, max_event_ids: 10_000 },
        notes: ["Sin servicio de flujo conectado: sin cobertura, sin valores "
          + "ni ceros inventados."],
      },
      error: `HTTP_${res.status}`,
    }, { headers });
  }

  const json = await res.json();
  return NextResponse.json({ ok: true, data: json.data ?? json }, { headers });
}

// POST (ingesta) no está expuesto por el BFF: la ingesta de flujo solo se
// permite directo al servicio Python de mercado (transporte local explícito,
// no por el BFF). Devolver 405 para evitar escrituras accidentales.
export async function POST() {
  return NextResponse.json({
    error: "METHOD_NOT_ALLOWED",
    detail: "La ingesta de flujo solo se permite directo al servicio Python "
      + "de mercado (puerto 8791, transporte local explícito).",
  }, { status: 405, headers });
}
