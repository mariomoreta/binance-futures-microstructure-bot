import {NextResponse} from "next/server";
import {spawnSync} from "node:child_process";
import {join} from "node:path";

// Recupera UNA sesion completa por ID (rehidratada desde persistencia).
// El backend Python es la fuente de verdad; el frontend solo presenta.
const ROOT = process.env.PAPER_LAB_SESSIONS_ROOT ??
  "C:/proyectos/binance-futures-microstructure-bot";
const PY = process.env.PAPER_LAB_PYTHON ?? "python";
const SCRIPT = join(ROOT, "scripts", "paper_lab_session.py");

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

function originAllowed(req: Request): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  return host === "127.0.0.1:3020" &&
    (origin === "http://127.0.0.1:3020" || origin === null);
}

function runPython(sessionId: string, action: string):
  {ok: boolean; data?: unknown; error?: string; detail?: string} {
  const r = spawnSync(
    PY, [SCRIPT, "--action", action, "--session-id", sessionId],
    {cwd: ROOT, encoding: "utf8", timeout: 30_000,
     maxBuffer: 8 * 1024 * 1024, windowsHide: true,
     env: {...process.env, PYTHONPATH: ROOT + "/src"}});
  if (r.status !== 0) {
    return {ok: false, error: "PYTHON_FAILED",
      detail: (r.stderr || "").trim().slice(-500)};
  }
  try {
    return JSON.parse(r.stdout) as {ok: boolean; data?: unknown};
  } catch {
    return {ok: false, error: "PYTHON_BAD_JSON",
      detail: (r.stdout || "").trim().slice(-200)};
  }
}

export async function GET(
  req: Request,
  {params}: {params: Promise<{session_id: string}>},
): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  const {session_id: sessionId} = await params;
  const r = runPython(sessionId, "get");
  if (!r.ok) {
    const status = r.error === "SESSION_NOT_FOUND" ? 404 : 500;
    return NextResponse.json({error: r.error, detail: r.detail},
      {status, headers});
  }
  return NextResponse.json(r.data ?? {ok: true}, {headers});
}
