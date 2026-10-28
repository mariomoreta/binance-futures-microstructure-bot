// Endpoint SSE del mismo origen para `market-flow/v1`.
// BFF puro proxy: reenvía el SSE del servicio Python de mercado
// (`market_stream_service`, puerto 8792). El navegador se conecta a
// `/api/v1/market-flow/stream` (mismo puerto 3020, sin CORS).
//
// Transporte local exclusivamente: sin conexión a Binance público.
//
// IMPORTANTE (causa reproducida del defecto ERR_INCOMPLETE_CHUNKED_ENCODING):
//   1. Un AbortSignal.timeout(30_000) cortaba cada SSE a los 30 s.
//   2. ADEMÁS el fetch global de Node (undici) tiene bodyTimeout por defecto
//      (30 s sin NINGÚN chunk del upstream): `/flow/stream` del servicio
//      (preexistente, no modificable) queda mudo cuando no se procesan
//      eventos de flujo por más de 30 s, y undici mataba la conexión con
//      UND_ERR_BODY_TIMEOUT ("failed to pipe response" en el BFF). Ambos
//      cortes producían el mismo síntoma en el panel.
// Arreglo: sin timeout de cuerpo en el upstream (agent undici bodyTimeout 0,
// headersTimeout acotado para la fase de conexión) y cancelación propagada
// desde `req.signal`: cuando el navegador cierra la conexión (cambio de
// símbolo, desmontaje, cierre de pestaña) el proxy libera su upstream; un
// re-render SIN cambio de identidad no toca la conexión.

import { NextResponse } from "next/server";
import { Agent, fetch as undiciFetch } from "undici";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const SYMBOL_RE = /^[A-Z0-9]{2,32}$/;

const FLOW_SERVICE_HOST = "127.0.0.1";
const FLOW_SERVICE_PORT = 8792;

// Agente dedicado del stream: sin límite de inactividad en el cuerpo del
// SSE (bodyTimeout 0) y límite acotado en la fase de conexión/headers.
const streamDispatcher = new Agent({ bodyTimeout: 0, headersTimeout: 10_000 });

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

  // Proxy SSE al servicio Python de mercado. Sin timeout de cuerpo: la vida
  // del SSE la gobierna el navegador (req.signal), no un temporizador del
  // BFF. La conexión al servicio caído falla inmediatamente (502) y la
  // reconexión la maneja el panel (EventSource con reintento).
  let res: Response;
  try {
    res = await undiciFetch(
      `http://${FLOW_SERVICE_HOST}:${FLOW_SERVICE_PORT}/flow/stream?symbol=${encodeURIComponent(symbol)}`,
      {
        headers: { "Accept": "text/event-stream" },
        signal: req.signal as never,
        dispatcher: streamDispatcher,
      },
    ) as unknown as Response;
  } catch {
    // Abort del PROPIO cliente (cambio de símbolo/desmonte): no es un error
    // del servicio; el consumidor ya se liberó.
    if (req.signal.aborted) {
      return new NextResponse(null, { status: 499 });
    }
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
