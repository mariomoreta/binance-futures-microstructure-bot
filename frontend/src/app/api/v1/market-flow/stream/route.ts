// Endpoint SSE del mismo origen para `market-flow/v1`.
// El navegador se conecta a `/api/v1/market-flow/stream` (mismo puerto 3020,
// sin CORS). Recibe hello, snapshot, update y heartbeat del FlowEngine
// compartido.

import { NextResponse } from "next/server";
import { flowEngine, subscribeToFlow, unsubscribeFromFlow } from "@/lib/flow-instance";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const HEARTBEAT_MS = 5_000;
const SYMBOL_RE = /^[A-Z0-9]{2,32}$/;

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

  const encoder = new TextEncoder();
  let streamController: ReadableStreamDefaultController | null = null;
  const stream = new ReadableStream({
    start(controller) {
      streamController = controller;
      let hb: ReturnType<typeof setInterval> | null = null;

      // Enviar hello
      const hello = `event: hello\ndata: ${JSON.stringify({
        symbol,
        service: "market-flow/v1",
        at_ms: Date.now(),
      })}\n\n`;
      controller.enqueue(encoder.encode(hello));

      // Enviar snapshot inicial
      const block = flowEngine.snapshot(symbol, Date.now(), true);
      const snap = `event: snapshot\ndata: ${JSON.stringify({
        symbol,
        block,
      })}\n\n`;
      controller.enqueue(encoder.encode(snap));

      // Suscribir a actualizaciones
      subscribeToFlow(symbol, controller);

      // Heartbeat
      hb = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(
            `event: heartbeat\ndata: ${JSON.stringify({ at_ms: Date.now() })}\n\n`
          ));
        } catch {
          if (hb) clearInterval(hb);
        }
      }, HEARTBEAT_MS);

      // Limpiar al abortar (desconexión del cliente)
      req.signal.addEventListener("abort", () => {
        if (hb) clearInterval(hb);
        unsubscribeFromFlow(symbol, controller);
      });
    },
    cancel() {
      // Cliente desconectado
      if (streamController) {
        unsubscribeFromFlow(symbol, streamController);
      }
    },
  });

  return new NextResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    },
  });
}
