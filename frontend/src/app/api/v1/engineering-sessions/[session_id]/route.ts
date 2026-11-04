import {NextResponse} from "next/server";
import { publicOriginAllowed } from "@/lib/engineering-service-manager";

// Proxy BFF -> servicio de sesiones de ingeniería: estado observado.
// GET es solo lectura (observación); no conduce el avance.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

const SERVICE_BASE =
  process.env.ENGINEERING_SERVICE_URL ?? "http://127.0.0.1:8797";

function originAllowed(req: Request): boolean {
  return publicOriginAllowed(req);
}

const SERVICE_DOWN_CODES = ["ECONNREFUSED", "EADDRNOTAVAIL", "UND_ERR_CONNECT",
  "UND_ERR_SOCKET", "ConnectTimeoutError"];

export async function GET(
  req: Request,
  {params}: {params: Promise<{session_id: string}>},
): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  const {session_id: sessionId} = await params;
  try {
    const r = await fetch(`${SERVICE_BASE}/sessions/${encodeURIComponent(sessionId)}`,
      {method: "GET", cache: "no-store"});
    let body: unknown;
    try {
      body = await r.json();
    } catch {
      body = null;
    }
    return NextResponse.json(body ?? {}, {status: r.status, headers});
  } catch (exc: unknown) {
    const err = exc as {code?: string; message?: string};
    const down = SERVICE_DOWN_CODES.includes(err?.code ?? "");
    return NextResponse.json(
      {error: down ? "ENGINEERING_SERVICE_DOWN" : "ENGINEERING_PROXY_ERROR",
       detail: String(err?.message ?? exc)},
      {status: 503, headers});
  }
}
