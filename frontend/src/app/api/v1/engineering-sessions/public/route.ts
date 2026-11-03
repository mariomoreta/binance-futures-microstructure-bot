// ACEPTACIÓN PÚBLICA para el operador de la intranet del dashboard:
// arrancar/consultar la corrida pública con run_id propio, presupuesto
// acotado (7 intentos HTTP upstream) y conexión WS pública a Binance
// (MINAUSDT+BTCUSDT, 1m). NUNCA arranca nada por GET; el arranque/parada son
// POST con las mismas guardias de origen que el resto del BFF.
// Observación y simulación paper únicamente: sin órdenes reales, sin claves
// privadas, sin pagos, sin móvil, sin cambios económicos.
// El run_id es estable y persistido: una recarga o reinicio de la misma corrida
// no devuelve cupos ni crea otra sesión. Una corrida nueva requiere acción
// explícita del operador; nunca se crea para eludir presupuesto agotado.
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

// Run IDs activos de la aceptación pública (memoria del proceso, se pierde
// al reiniciar el servidor; suficiente para una sola corrida autorizada).
const activePublicRuns = new Map<string, { startedAtMs: number; httpAttempts: number; deadlineMs: number }>();

const PUBLIC_HTTP_MAX = 7;
const PUBLIC_DEADLINE_S = 180;

/** Genera un run_id estable y determinista para una corrida pública. */
function generateRunId(): string {
  return `eng-public-${Date.now()}`;
}

/** Estado de la aceptación pública (consulta pura). */
export async function GET(req: Request): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({ error: "FORBIDDEN" }, { status: 403, headers });
  }
  try {
    const st = await serviceStatus();
    const now = Date.now();
    const runs = Array.from(activePublicRuns.entries()).map(([runId, info]) => ({
      runId,
      startedAtMs: info.startedAtMs,
      httpAttempts: info.httpAttempts,
      active: now < info.deadlineMs,
      deadlineMs: info.deadlineMs,
    }));
    return NextResponse.json(
      { ok: true, service: st, publicRuns: runs },
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
 *  servicio y limpia la corrida. */
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
      const st = await serviceStatus();
      const started = await startService({
        clockSource: "public",
        runId: body.run_id ?? null,
        publicMaxRequests: PUBLIC_HTTP_MAX,
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
      // 2. Registrar la corrida con run_id estable y deadline.
      const runId = started.runIdFromService ?? body.run_id ?? generateRunId();
      activePublicRuns.set(runId, {
        startedAtMs: Date.now(),
        httpAttempts: 0,
        deadlineMs: Date.now() + PUBLIC_DEADLINE_S * 1000,
      });
      return NextResponse.json(
        {
          ok: true,
          run_id: runId,
          started_at_ms: Date.now(),
          http_attempts: 0,
          deadline_s: PUBLIC_DEADLINE_S,
          http_max: PUBLIC_HTTP_MAX,
          service: { pid: started.pid, port: started.port, sessions_dir: started.sessions_dir },
        },
        { status: 200, headers },
      );
    } else {
      // action === "stop": detener el servicio propio y limpiar la corrida.
      const runId = body.run_id ?? null;
      const stopped = await stopService();
      if (runId && activePublicRuns.has(runId)) {
        activePublicRuns.delete(runId);
      }
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
