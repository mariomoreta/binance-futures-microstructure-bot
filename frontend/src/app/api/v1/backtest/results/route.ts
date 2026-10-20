import {NextResponse} from "next/server";
import {currentRunId, isBacktestExperiment, readResults, readRunResults,
  type BacktestExperiment} from "@/lib/backtest-control";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

// Resultados del experimento (agregados + operaciones individuales), vinculados
// a UNA ejecucion concreta (?run=<run_id>) o a la actual. Solo se sirven
// resultados COMPLETADOS y con HASH VERIFICADO; si la tarea no termino o la
// integridad falla, se reporta el estado real y NUNCA se sustituye por datos
// de ejemplo ni por resultados alterados.
export async function GET(req: Request) {
  const url = new URL(req.url);
  const experiment = url.searchParams.get("experiment");
  if (!isBacktestExperiment(experiment)) {
    return NextResponse.json({error: "EXPERIMENT_NOT_ALLOWED"}, {status: 400, headers});
  }
  const run = url.searchParams.get("run");
  const r = run
    ? readRunResults(experiment as BacktestExperiment, run)
    : readResults(experiment as BacktestExperiment);
  if (!r.available) {
    return NextResponse.json({available: false, status: r.status, error: r.error,
      run_id: r.run_id ?? run ?? currentRunId(experiment as BacktestExperiment)},
      {status: 409, headers});
  }
  return NextResponse.json(r, {headers});
}
