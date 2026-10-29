// DEMOSTRACIÓN LOCAL de ingeniería para el operador de la intranet del
// dashboard: "Demostración local — datos simulados". Arranca/para
// EXCLUSIVAMENTE recursos propios identificados (productor WS loopback +
// servicio de mercado canónico con --transport local, acotados) y consulta
// su estado. NUNCA arranca nada por GET; el arranque/parada son POST con
// las guardias de origen del BFF. No usa silenciosamente el servicio
// preexistente 8792 ni habilita transporte público: la futura fuente
// Binance es otra ruta, con autorización y presupuesto separados.

import {NextResponse} from "next/server";
import {
  demoStatus,
  startDemo,
  stopDemo,
} from "@/lib/local-demo-manager";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

function originAllowed(req: Request): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  return host === "127.0.0.1:3020" &&
    (origin === "http://127.0.0.1:3020" || origin === null);
}

/** Estado de la demostración y de la fuente (consulta pura). */
export async function GET(req: Request): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  try {
    const st = await demoStatus();
    return NextResponse.json({ok: true, ...st}, {status: 200, headers});
  } catch (exc: unknown) {
    return NextResponse.json(
      {ok: false, error: "DEMO_STATUS_ERROR", detail: String(exc)},
      {status: 500, headers});
  }
}

/** POST {action: "start" | "stop"}: acciones explícitas del operador. */
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
  if (action !== "start" && action !== "stop") {
    return NextResponse.json(
      {error: "UNKNOWN_ACTION",
       detail: `demo acepta action=start|stop; recibido ${String(action)}`},
      {status: 400, headers});
  }
  try {
    const result = action === "start" ? await startDemo() : await stopDemo();
    const status = result.ok ? 200 : 503;
    return NextResponse.json(
      {...result, error: result.error ?? null, detail: result.detail ?? null},
      {status, headers});
  } catch (exc: unknown) {
    return NextResponse.json(
      {ok: false, error: "DEMO_ACTION_FAILED", detail: String(exc)},
      {status: 503, headers});
  }
}
