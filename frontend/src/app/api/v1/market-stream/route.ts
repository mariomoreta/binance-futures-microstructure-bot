import {NextResponse} from "next/server";
import {explorerOriginAllowed} from "@/lib/explorer-bridge";
import {streamErrorDetail, streamServiceUrl} from "@/lib/stream-bridge";

// Feed de velas (`market-stream/v1`) en SSE, proxied desde el servicio local.
//
// Solo lectura pública y bajo demanda: la conexión se abre cuando el gráfico lo
// pide. El servicio comparte una única conexión al exchange y aplica
// presupuesto (streams, consumidores, memoria, REST de reparación). Todo el
// estado de autorización vive en el backend; aquí solo se validan parámetros.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

const SYMBOL_RE = /^[A-Z0-9]{2,32}$/;
const INTERVALS = new Set(["1m", "5m", "15m", "1h", "4h", "1d"]);

function intParam(params: URLSearchParams, name: string): number | null | undefined {
  const values = params.getAll(name);
  if (values.length === 0) return undefined;
  if (values.length > 1) return null;
  const raw = values[0] ?? "";
  if (!/^\d{1,16}$/.test(raw)) return null;
  const value = Number(raw);
  return Number.isSafeInteger(value) ? value : null;
}

export async function GET(req: Request) {
  if (!explorerOriginAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN_ORIGIN"}, {status: 403, headers});
  }
  const params = new URL(req.url).searchParams;
  const symbol = (params.get("symbol") ?? "").trim().toUpperCase();
  if (!SYMBOL_RE.test(symbol)) {
    return NextResponse.json({error: "INVALID_SYMBOL"}, {status: 400, headers});
  }
  const interval = params.get("interval") ?? "";
  if (!INTERVALS.has(interval)) {
    return NextResponse.json({error: "INVALID_INTERVAL"}, {status: 400, headers});
  }
  const fromMs = intParam(params, "from_ms");
  const toMs = intParam(params, "to_ms");
  if (fromMs === null || toMs === null) {
    return NextResponse.json({error: "INVALID_RANGE"}, {status: 400, headers});
  }
  if (fromMs !== undefined && toMs !== undefined && fromMs > toMs) {
    return NextResponse.json({error: "INVALID_RANGE"}, {status: 400, headers});
  }
  const bars = intParam(params, "bars");
  if (bars === null || (bars !== undefined && (bars < 1 || bars > 1000))) {
    return NextResponse.json({error: "INVALID_BARS"}, {status: 400, headers});
  }
  const upstreamParams = new URLSearchParams({symbol, interval});
  if (fromMs !== undefined) upstreamParams.set("from_ms", String(fromMs));
  if (toMs !== undefined) upstreamParams.set("to_ms", String(toMs));
  if (bars !== undefined) upstreamParams.set("bars", String(bars));

  let upstream: Response;
  try {
    upstream = await fetch(`${streamServiceUrl()}/stream?${upstreamParams.toString()}`, {
      headers: {Accept: "text/event-stream"},
      cache: "no-store",
      signal: req.signal,
    });
  } catch (error) {
    return NextResponse.json({
      error: "STREAM_SERVICE_DOWN",
      detail: streamErrorDetail(error),
    }, {status: 503, headers});
  }
  if (!upstream.ok || !upstream.body) {
    return NextResponse.json({
      error: "STREAM_SERVICE_DOWN",
      detail: `HTTP ${upstream.status}`,
    }, {status: 503, headers});
  }
  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-store, no-transform",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
