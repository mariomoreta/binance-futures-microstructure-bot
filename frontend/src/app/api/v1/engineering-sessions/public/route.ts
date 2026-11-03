// ACEPTACIÓN PÚBLICA para el operador de la intranet del dashboard:
// arrancar/consultar la corrida pública con run_id propio, presupuesto
// acotado (7 intentos HTTP upstream) y conexión WS pública a Binance
// (MINAUSDT+BTCUSDT, 1m). NUNCA arranca nada por GET; el arranque/parada son
// POST con las mismas guardias de origen que el resto del BFF.
// Observación y simulación paper únicamente: sin órdenes reales, sin claves
// privadas, sin pagos, sin móvil, sin cambios económicos.
// La autoridad del ciclo de vida de la corrida vive en el backend
// (engineering-session-service/v1, registro persistente public-run.json);
// React y Node no son la única autoridad. El BFF consulta y solicita acciones.
import { NextResponse } from "next/server";
import {
  serviceStatus,
  startService,
  stopService,
  type StartServiceOptions,
} from "@/lib/engineering-service-manager";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "no-store" };

function originAllowed(req: Request): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  return host === "127.0.0.1:3020" && (origin === "http://127.0.0.1:3020" || origin === null);
}

const PUBLIC_HTTP_MAX = 7;
const PUBLIC_DEADLINE_S = 180;
const PUBLIC_CLOCK_REQUESTS = 5; // 5 muestras para sincronización del reloj

/** Estado de la aceptación pública (consulta pura; lee del backend). */
export async function GET(req: Request): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({ error: "FORBIDDEN" }, { status: 403, headers });
  }
  try {
    const st = await serviceStatus();
    // Consulta el registro persistente de la corrida en el backend.
    const pr = await fetch("http://127.0.0.1:8797/public-run", {
      method: "GET",
      cache: "no-store",
      signal: AbortSignal.timeout(2_000),
    }).then(async (r) => {
      try { return await r.json(); } catch { return null; }
    }).catch(() => null);
    return NextResponse.json(
      {
        ok: true,
        service: st,
        publicRun: pr ?? {
          run_id: null, state: "idle",
          detail: "sin registro de corrida pública en el backend",
        },
      },
      { status: 200, headers },
    );
  } catch (exc: unknown) {
    return NextResponse.json(
      { ok: false, error: "PUBLIC_STATUS_ERROR", detail: String(exc) },
      { status: 500, headers },
    );
  }
}

/** POST {action: "start" | "stop", run_id?: string}: acciones explícitas del
 *  operador. "start" genera un run_id propio y arranca el servicio de
 *  ingeniería con --clock-source public y ese run_id. "stop" detiene el
 *  servicio tras verificar identidad y pertenencia a la corrida. */
export async function POST(req: Request): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({ error: "FORBIDDEN" }, { status: 403, headers });
  }
  let action: string | null = null;
  let body: { action?: string; run_id?: string; symbols?: string; interval?: string } = {};
  try {
    body = await req.json().catch(() => ({}));
    action = body.action ?? null;
  } catch {
    action = null;
  }
  if (action !== "start" && action !== "stop") {
    return NextResponse.json(
      { error: "UNKNOWN_ACTION", detail: `public acepta action=start|stop; recibido ${String(action)}` },
      { status: 400, headers },
    );
  }
  try {
    if (action === "start") {
      // 1. Arrancar el servicio de ingeniería si no está listo, en modo publico.
      //    Se pasa publicMaxRequests=5 (muestras de sincronización); el backend
      //    impone el techo TOTAL de 7 intentos upstream por corrida (run_id)
      //    a través del ledger compartido (reserva antes del envío).
      const started = await startService({
        clockSource: "public",
        runId: body.run_id ?? null,
        publicMaxRequests: PUBLIC_CLOCK_REQUESTS,
        // publicFetchUrl se deja sin definir: el CLI usa Binance real por defecto.
        // En pruebas locales se puede sobrescribir con variable de entorno.
        publicFetchUrl: process.env.PUBLIC_FETCH_URL ?? null,
      });
      if (!started.ok) {
        return NextResponse.json(
          { ok: false, error: started.error ?? "ENGINEERING_SERVICE_START_FAILED", detail: started.detail ?? undefined },
          { status: 503, headers },
        );
      }
      // 2. Consultar el registro persistente de la corrida en el backend.
      const pr = await fetch("http://127.0.0.1:8797/public-run", {
        method: "GET",
        cache: "no-store",
        signal: AbortSignal.timeout(2_000),
      }).then(async (r) => {
        try { return await r.json(); } catch { return null; }
      }).catch(() => null);
      const runId = pr?.run_id ?? started.runIdFromService ?? body.run_id;
      return NextResponse.json(
        {
          ok: true,
          run_id: runId,
          started_at_ms: pr?.started_at_ms ?? Date.now(),
          http_attempts: pr?.http_attempts ?? 0,
          deadline_s: PUBLIC_DEADLINE_S,
          http_max: PUBLIC_HTTP_MAX,
          state: pr?.state ?? "preparing",
          cause: pr?.cause ?? null,
          service: { pid: started.pid, port: started.port, sessions_dir: started.sessions_dir },
          deadline_exceeded: pr?.deadline_exceeded ?? false,
        },
        { status: 200, headers },
      );
    } else {
      // action === "stop": detener el servicio propio tras verificar identidad
      // y pertenencia a la corrida.
      const runId = body.run_id ?? null;
      const stopped = await stopService(runId);
      return NextResponse.json(
        { ok: true, stopped: !!runId, service_stopped: stopped.ok, detail: stopped.detail ?? null },
        { status: 200, headers },
      );
    }
  } catch (exc: unknown) {
    return NextResponse.json(
      { ok: false, error: "PUBLIC_ACTION_FAILED", detail: String(exc) },
      { status: 503, headers },
    );
  }
}
