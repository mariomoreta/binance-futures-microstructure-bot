// Endpoint SSE del mismo origen para `market-flow/v1`.
// BFF puro proxy: reenvía el SSE del servicio Python de mercado
// (`market_stream_service`, puerto 8791). El navegador se conecta a
// `/api/v1/market-flow/stream` (mismo puerto 3020, sin CORS).
//
// Transporte local exclusivamente: sin conexión a Binance público.

import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const SYMBOL_RE = /^[A-Z0-9]{2,32}$/;

const FLOW_SERVICE_HOST = "127.0.0.1";
const FLOW_SERVICE_PORT = 8792;

export async function GET(req: Request) {
  // Origen local acotado: solo la misma instancia del dashboard.
  const host = req.headers.get("host");
  if (host !== "127.0.0.1:3020" && host !== "localhost:3020") {
    return new NextResponse("FORBIDDEN_ORIGIN", { status: 403 });
  }
  const origin = req.headers.get("origin");
  if (origin !== null && origin !== `http://${host}`) {
    return new NextResponse("FORBIDDEN_ORIGIN", { status: 403 });
  }

  const params = new URL(req.url).searchParams;
  const symbol = (params.get("symbol") ?? "").trim().toUpperCase();
  if (!SYMBOL_RE.test(symbol)) {
    return new NextResponse("INVALID_SYMBOL", { status: 400 });
  }

  // Proxy SSE al servicio Python de mercado.
  let res: Response;
  try {
    res = await fetch(
      `http://${FLOW_SERVICE_HOST}:${FLOW_SERVICE_PORT}/flow/stream?symbol=${encodeURIComponent(symbol)}`,
      { headers: { "Accept": "text/event-stream" }, signal: AbortSignal.timeout(30_000) },
    );
  } catch {
    return new NextResponse("FLOW_SERVICE_NOT_REACHABLE", { status: 502 });
  }

  if (!res.ok) {
    return new NextResponse(`FLOW_SERVICE_ERROR ${res.status}`, { status: 502 });
  }

  return new NextResponse(res.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-store",
      "Connection": "keep-alive",
    },
  });
}
