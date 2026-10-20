import {NextResponse} from "next/server";
import {isBacktestExperiment, startJob, type BacktestExperiment} from "@/lib/backtest-control";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

// Guardas de origen local (mismo criterio que el resto del BFF): solo se
// acepta una peticion desde la propia app servida en 127.0.0.1:3020. No hay
// endpoint de ejecucion real ni toca el controlador del monitor.
function originAllowed(req: Request): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  return host === "127.0.0.1:3020" && (origin === "http://127.0.0.1:3020" || origin === null);
}

export async function POST(req: Request) {
  if (!originAllowed(req)) return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({error: "INVALID_BODY"}, {status: 400, headers});
  }
  const experiment = (body as {experiment?: unknown})?.experiment;
  if (!isBacktestExperiment(experiment)) {
    return NextResponse.json({error: "EXPERIMENT_NOT_ALLOWED",
      detail: "experiment debe pertenecer a la lista permitida"}, {status: 400, headers});
  }
  // El cliente solo envia el identificador del experimento: nunca rutas,
  // comandos ni codigo. La lista permitida y las combinaciones viven en el
  // ejecutor backend (scripts/run_dashboard_backtest.py). Cada llamada crea
  // una ejecucion con identidad unica; el bloqueo entre procesos impide
  // duplicados por doble clic o solicitudes concurrentes.
  const r = startJob(experiment as BacktestExperiment);
  return NextResponse.json({started: r.started, state: r.state,
    run_id: r.run_id ?? r.state?.run_id ?? null, error: r.error ?? null},
    {status: r.error === "SPAWN_FAILED" ? 500 : 200, headers});
}
