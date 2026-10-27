// Flujo agresivo comprador/vendedor — contrato `market-flow/v1`.
// Backend como autoridad (FlowEngine compartido en `flow-instance.ts`);
// el frontend solo solicita y presenta. Transporte local exclusivamente:
// sin conexión a Binance público, sin cobertura antes del primer evento de
// captura, sin reconstrucción desde OHLC.
//
// Delta positivo NO es señal alcista automática: solo describe el saldo de
// volumen agresor en ventana.

import { NextResponse } from "next/server";
import { flowEngine } from "@/lib/flow-instance";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "no-store" };

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
    notes: ["Sin eventos de captura para este símbolo: sin cobertura, sin valores ni ceros inventados."],
  };
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

  const block = flowEngine.snapshot(symbol, asOfMs, true);
  return NextResponse.json({ ok: true, data: block }, { headers });
}

interface FlowEventBody {
  symbol: string;
  event_id: string;
  event_ms: number;
  price: number;
  quantity: number;
  buyer_is_maker: boolean;
  normal_quantity?: number;
}

export async function POST(req: Request) {
  const host = req.headers.get("host");
  if (host !== "127.0.0.1:3020" && host !== "localhost:3020") {
    return NextResponse.json({ error: "FORBIDDEN_ORIGIN" }, { status: 403, headers });
  }

  let body: FlowEventBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "INVALID_JSON" }, { status: 400, headers });
  }

  const symbol = String(body.symbol ?? "").trim().toUpperCase();
  const event_id = String(body.event_id ?? "").trim();
  const event_ms = body.event_ms;
  const price = body.price;
  const quantity = body.quantity;
  const buyer_is_maker = body.buyer_is_maker;
  const normal_quantity = body.normal_quantity;

  if (!SYMBOL_RE.test(symbol)) {
    return NextResponse.json({ error: "INVALID_SYMBOL", detail: `símbolo inválido: ${symbol}` }, { status: 400, headers });
  }
  if (!event_id) {
    return NextResponse.json({ error: "MISSING_EVENT_ID", detail: "event_id es obligatorio" }, { status: 400, headers });
  }
  if (typeof event_ms !== "number" || !Number.isFinite(event_ms)) {
    return NextResponse.json({ error: "INVALID_EVENT_MS", detail: "event_ms debe ser un número" }, { status: 400, headers });
  }
  if (typeof price !== "number" || !Number.isFinite(price) || price <= 0) {
    return NextResponse.json({ error: "INVALID_PRICE", detail: "price inválido" }, { status: 400, headers });
  }
  if (typeof quantity !== "number" || !Number.isFinite(quantity) || quantity <= 0) {
    return NextResponse.json({ error: "INVALID_QUANTITY", detail: "quantity inválida" }, { status: 400, headers });
  }
  if (typeof buyer_is_maker !== "boolean") {
    return NextResponse.json({ error: "INVALID_MAKER", detail: "buyer_is_maker debe ser booleano" }, { status: 400, headers });
  }

  const result = flowEngine.ingest({
    symbol,
    event_id,
    event_ms,
    price,
    quantity,
    buyer_is_maker,
    normal_quantity: typeof normal_quantity === "number" ? normal_quantity : undefined,
  });

  if (!result.ok) {
    return NextResponse.json({
      ok: false,
      error: result.reason ?? "REJECTED",
      detail: result.reason === "DUPLICATE_EVENT_ID" ? "identificador repetido: no suma volumen" : "evento descartado",
    }, { status: 200, headers });
  }

  const block = flowEngine.snapshot(symbol, event_ms, true);
  return NextResponse.json({ ok: true, duplicate: false, event_id, symbol, block }, { headers });
}
