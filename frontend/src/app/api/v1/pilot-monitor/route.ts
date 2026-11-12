// Monitor del piloto operativo (`scripts/research_pilot.py`).
//
// BFF de solo lectura: NO calcula decisiones, funding ni P&L. NO abre
// conexiones: lee unicamente artefactos locales de la corrida autorizada y
// publica el estado que el piloto ya persistio. El cliente envia un `run_id`
// (nunca una ruta) y la lectura queda acotada a `PILOT_MONITOR_ROOT`.

import { NextResponse } from "next/server";
import { buildPilotMonitor, resolveRunDir } from "@/lib/pilot-monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "no-store" };

export async function GET(req: Request) {
  // Origen local acotado: solo la misma instancia del dashboard.
  const host = req.headers.get("host");
  if (host !== "127.0.0.1:3020" && host !== "localhost:3020") {
    return NextResponse.json({ error: "FORBIDDEN_ORIGIN" }, { status: 403, headers });
  }
  const origin = req.headers.get("origin");
  if (origin !== null && origin !== `http://${host}`) {
    return NextResponse.json({ error: "FORBIDDEN_ORIGIN" }, { status: 403, headers });
  }

  const params = new URL(req.url).searchParams;
  const runId = (params.get("run") ?? "").trim();
  if (!runId) {
    return NextResponse.json({ error: "MISSING_RUN_ID" }, { status: 400, headers });
  }
  if (!resolveRunDir(runId)) {
    return NextResponse.json({ error: "INVALID_RUN_ID" }, { status: 400, headers });
  }

  const payload = buildPilotMonitor(runId);
  if (!payload) {
    return NextResponse.json({ error: "RUN_NOT_FOUND" }, { status: 404, headers });
  }
  return NextResponse.json({ ok: true, data: payload }, { headers });
}

// POST no esta expuesto: el monitor observa, nunca modifica la corrida.
export async function POST() {
  return NextResponse.json(
    { error: "METHOD_NOT_ALLOWED", detail: "El monitor es de solo lectura." },
    { status: 405, headers },
  );
}
