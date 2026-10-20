import {NextResponse} from "next/server";
import {isBacktestExperiment, materializeReplay, type BacktestExperiment} from "@/lib/backtest-control";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

// Materializa el artefacto PAPER-LAB-REPLAY-V1 de UNA operacion elegida del
// listado de Backtest (identidad exacta: event_id, grupo, segmento, escala).
// Reutiliza el generador y el parser de Paper Lab; conserva la causalidad
// (formacion como metadata, revelacion en available_at). Si el tipo de
// operacion no esta soportado, se reporta el motivo y NO se fabrica un replay.
export async function GET(req: Request) {
  const url = new URL(req.url);
  const experiment = url.searchParams.get("experiment");
  if (!isBacktestExperiment(experiment)) {
    return NextResponse.json({error: "EXPERIMENT_NOT_ALLOWED"}, {status: 400, headers});
  }
  const eventId = url.searchParams.get("event_id");
  const group = url.searchParams.get("group");
  const segment = url.searchParams.get("segment");
  const scaleRaw = url.searchParams.get("scale");
  const scale = scaleRaw == null ? NaN : Number(scaleRaw);
  if (!eventId || !group || !segment || !Number.isFinite(scale)) {
    return NextResponse.json({error: "INVALID_TARGET",
      detail: "se requieren event_id, group, segment y scale"}, {status: 400, headers});
  }
  const r = materializeReplay({experiment: experiment as BacktestExperiment,
    event_id: eventId, group, segment, scale});
  if (!r.ok) {
    const status = r.error === "RESULT_NOT_READY" ? 409 : 422;
    return NextResponse.json({error: r.error ?? "REPLAY_UNSUPPORTED"}, {status, headers});
  }
  return NextResponse.json(r.artifact, {headers});
}
