import {NextResponse} from "next/server";
import { publicOriginAllowed } from "@/lib/engineering-service-manager";

// Proxy BFF -> servicio backend de sesiones de ingenieria (solo loopback).
// El backend mantiene la sesion y conduce el avance por eventos del
// transporte local; este proxy NO conduce. El navegador solo crea la sesion;
// la conduccion se inicia explicitamente con control start.

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

async function proxy(req: Request, init: RequestInit
): Promise<NextResponse> {
  try {
    const r = await fetch(`${SERVICE_BASE}/sessions`, init);
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

export async function GET(req: Request): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  return proxy(req, {method: "GET", cache: "no-store"});
}

export async function POST(req: Request): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  const body = await req.text();
  return proxy(req, {
    method: "POST",
    cache: "no-store",
    headers: {"Content-Type": "application/json"},
    body,
  });
}
