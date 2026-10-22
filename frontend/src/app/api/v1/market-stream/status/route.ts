import {NextResponse} from "next/server";
import {explorerOriginAllowed} from "@/lib/explorer-bridge";
import {streamErrorDetail, streamServiceUrl} from "@/lib/stream-bridge";

// Estado del servicio local de datos (`market-stream/v1`).
// Siempre responde 200 con `available` booleano: la UI distingue "servicio
// detenido" de "error de red" sin tratar el histórico como inexistente.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

export async function GET(req: Request) {
  if (!explorerOriginAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN_ORIGIN"}, {status: 403, headers});
  }
  try {
    const response = await fetch(`${streamServiceUrl()}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2500),
    });
    if (!response.ok) {
      return NextResponse.json(
        {available: false, detail: `HTTP ${response.status}`}, {headers});
    }
    const health = await response.json();
    return NextResponse.json({available: true, health}, {headers});
  } catch (error) {
    return NextResponse.json(
      {available: false, detail: streamErrorDetail(error)}, {headers});
  }
}
