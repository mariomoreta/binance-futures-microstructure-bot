import {NextResponse} from "next/server";
import {isBacktestExperiment, readResults, type BacktestExperiment} from "@/lib/backtest-control";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

// Resultados del experimento (agregados + operaciones individuales). Solo se
// sirven resultados COMPLETADOS; si la tarea no termino, se reporta el estado
// real y NUNCA se sustituye por datos de ejemplo.
export async function GET(req: Request) {
  const url = new URL(req.url);
  const experiment = url.searchParams.get("experiment");
  if (!isBacktestExperiment(experiment)) {
    return NextResponse.json({error: "EXPERIMENT_NOT_ALLOWED"}, {status: 400, headers});
  }
  const r = readResults(experiment as BacktestExperiment);
  if (!r.available) {
    return NextResponse.json({available: false, status: r.status, error: r.error},
      {status: 409, headers});
  }
  return NextResponse.json(r, {headers});
}
