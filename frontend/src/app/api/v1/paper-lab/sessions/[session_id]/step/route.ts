import {NextResponse} from "next/server";
import {spawnSync} from "node:child_process";
import {join} from "node:path";

// Avanza un paso en la sesion (vela cerrada conocida, evaluacion de
// stop/horizon). Backend ejecuta, frontend presenta.
const ROOT = process.env.PAPER_LAB_SESSIONS_ROOT ??
  "C:/proyectos/binance-futures-microstructure-bot";
const PY = process.env.PAPER_LAB_PYTHON ?? "python";
const SCRIPT = join(ROOT, "scripts", "paper_lab_session.py");

type PyResult = {ok: boolean; data?: unknown; error?: string; detail?: string};

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

function originAllowed(req: Request): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  return host === "127.0.0.1:3020" &&
    (origin === "http://127.0.0.1:3020" || origin === null);
}

export async function POST(
  req: Request,
  {params}: {params: Promise<{session_id: string}>},
): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  const {session_id: sessionId} = await params;
  const r = spawnSync(
    PY, [SCRIPT, "--action", "step", "--session-id", sessionId],
    {cwd: ROOT, encoding: "utf8", timeout: 30_000,
     maxBuffer: 8 * 1024 * 1024, windowsHide: true,
     env: {...process.env, PYTHONPATH: ROOT + "/src"}});
  if (r.status !== 0) {
    return NextResponse.json(
      {error: "PYTHON_FAILED", detail: (r.stderr || "").trim().slice(-500)},
      {status: 500, headers});
  }
  let data: PyResult;
  try {
    data = JSON.parse(r.stdout) as PyResult;
  } catch {
    return NextResponse.json(
      {error: "PYTHON_BAD_JSON", detail: (r.stdout || "").trim().slice(-200)},
      {status: 500, headers});
  }
  if (!data.ok) {
    const status = data.error === "SESSION_NOT_FOUND" ? 404 : 500;
    return NextResponse.json({error: data.error, detail: data.detail},
      {status, headers});
  }
  return NextResponse.json(data.data ?? {ok: true}, {headers});
}
