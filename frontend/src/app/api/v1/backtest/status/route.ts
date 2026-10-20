import {NextResponse} from "next/server";
import {isBacktestExperiment, readJobState, retentionReport, type BacktestExperiment} from "@/lib/backtest-control";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

// Estado persistido de la tarea de backtest. Un refresco o el cierre del
// navegador no pierde ni relanza la tarea: el estado vive en disco y se lee
// aqui. Sin sustitutos: si no hay estado, se reporta explicitamente.
export async function GET(req: Request) {
  const url = new URL(req.url);
  const experiment = url.searchParams.get("experiment");
  if (!isBacktestExperiment(experiment)) {
    return NextResponse.json({error: "EXPERIMENT_NOT_ALLOWED"}, {status: 400, headers});
  }
  const state = readJobState(experiment as BacktestExperiment);
  return NextResponse.json({experiment_id: experiment, state,
    retention: retentionReport()}, {headers});
}
