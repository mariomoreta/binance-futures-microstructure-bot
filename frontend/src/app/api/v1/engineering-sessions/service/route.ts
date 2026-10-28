// Control EXPLÍCITO del servicio de ingeniería para el operador de la
// intranet del dashboard: arrancar/consultar la instancia canónica del
// proyecto. NUNCA arranca nada por GET ni por abrir la página; el arranque
// es una POST acción con las mismas guardias de origen que el resto del
// BFF. La identidad del proceso se verifica por pid-file + /health (no se
// reutiliza ni detiene un PID desconocido).

import {NextResponse} from "next/server";
import {
  serviceStatus,
  startService,
} from "@/lib/engineering-service-manager";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

function originAllowed(req: Request): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  return host === "127.0.0.1:3020" &&
    (origin === "http://127.0.0.1:3020" || origin === null);
}

/** Estado del servicio (consulta pura; no arranca ni detiene nada). */
export async function GET(req: Request): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  try {
    const st = await serviceStatus();
    return NextResponse.json({ok: true, ...st}, {status: 200, headers});
  } catch (exc: unknown) {
    return NextResponse.json(
      {ok: false, error: "ENGINEERING_SERVICE_STATUS_ERROR",
       detail: String(exc)},
      {status: 500, headers});
  }
}

/** POST {action: "start"}: arranque explícito con readiness y identidad. */
export async function POST(req: Request): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  let action: string | null = null;
  try {
    const body = await req.json().catch(() => ({}));
    action = (body as {action?: string} | null)?.action ?? null;
  } catch {
    action = null;
  }
  if (action !== "start") {
    return NextResponse.json(
      {error: "UNKNOWN_ACTION",
       detail: `servicio solo acepta action=start; recibido ${String(action)}`},
      {status: 400, headers});
  }
  try {
    const result = await startService();
    const status = result.ok ? 200 : 503;
    return NextResponse.json(
      {...result, error: result.error ?? null, detail: result.detail ?? null},
      {status, headers});
  } catch (exc: unknown) {
    return NextResponse.json(
      {ok: false, error: "ENGINEERING_SERVICE_START_FAILED", detail: String(exc)},
      {status: 503, headers});
  }
}
