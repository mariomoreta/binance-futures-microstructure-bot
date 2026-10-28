import {NextResponse} from "next/server";

// Proxy BFF -> control del servicio backend de sesiones de ingeniería.
// Solo peticiones explícitas del operador (start/stop/paso manual/etc.);
// el avance autónomo lo conduce el backend mismo por eventos del transporte.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

const SERVICE_BASE =
  process.env.ENGINEERING_SERVICE_URL ?? "http://127.0.0.1:8797";

function originAllowed(req: Request): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  return host === "127.0.0.1:3020" &&
    (origin === "http://127.0.0.1:3020" || origin === null);
}

const SERVICE_DOWN_CODES = ["ECONNREFUSED", "EADDRNOTAVAIL", "UND_ERR_CONNECT",
  "UND_ERR_SOCKET", "ConnectTimeoutError"];

export async function POST(
  req: Request,
  {params}: {params: Promise<{session_id: string}>},
): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  const {session_id: sessionId} = await params;
  try {
    const body = await req.text();
    const r = await fetch(
      `${SERVICE_BASE}/sessions/${encodeURIComponent(sessionId)}/control`,
      {method: "POST", cache: "no-store",
       headers: {"Content-Type": "application/json"}, body});
    let data: unknown;
    try {
      data = await r.json();
    } catch {
      data = null;
    }
    return NextResponse.json(data ?? {}, {status: r.status, headers});
  } catch (exc: unknown) {
    const err = exc as {code?: string; message?: string};
    const down = SERVICE_DOWN_CODES.includes(err?.code ?? "");
    return NextResponse.json(
      {error: down ? "ENGINEERING_SERVICE_DOWN" : "ENGINEERING_PROXY_ERROR",
       detail: String(err?.message ?? exc)},
      {status: 503, headers});
  }
}
