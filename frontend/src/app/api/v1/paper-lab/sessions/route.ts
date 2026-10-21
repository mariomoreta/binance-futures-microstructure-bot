import {NextResponse} from "next/server";
import {spawnSync} from "node:child_process";
import {join} from "node:path";

// Persistencia de sesiones Paper Lab (ingeniería). El backend Python es la
// fuente de verdad: posee reloj de sesión, configuración versionada,
// decisiones, posiciones, fills, costes, eventos y resultados. El frontend
// solicita acciones acotadas y presenta estados recibidos.
//
// Seguridad:
// - session_id validado contra traversal/alias antes de tocar el FS.
// - Escritura atómica delegada al backend Python (tmp + os.replace).
// - Escritura SOLO en el directorio aislado de sesiones de ingeniería.
// - Lista permitida de acciones; no se aceptan rutas ni comandos arbitrarios.
// - Origen local (mismo criterio que el resto del BFF).
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

function runPython(action: string, extra: string[]): {ok: boolean; data?: unknown; error?: string; detail?: string} {
  const r = spawnSync(
    PY, [SCRIPT, "--action", action, ...extra],
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

export async function GET(req: Request): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  const r = runPython("list", []);
  if (!r.ok) {
    return NextResponse.json({error: r.error, detail: r.detail},
      {status: 500, headers});
  }
  return NextResponse.json(r.data ?? {sessions: []}, {headers});
}

export async function POST(req: Request): Promise<NextResponse> {
  if (!originAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN"}, {status: 403, headers});
  }
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({error: "INVALID_BODY"}, {status: 400, headers});
  }
  const cfg = (body as {config?: unknown})?.config;
  const candles = (body as {candles?: unknown})?.candles;
  const context = (body as {context?: unknown})?.context;
  const hypothesisId = (body as {hypothesis_id?: unknown})?.hypothesis_id;
  const hypothesisVersion = (body as {hypothesis_version?: unknown})?.hypothesis_version;
  const decision = (body as {decision?: unknown})?.decision;
  const decisionReason = (body as {decision_reason?: unknown})?.decision_reason;

  const extra: string[] = ["--config-json", JSON.stringify(cfg ?? {})];
  if (candles != null) extra.push("--candles-json", JSON.stringify(candles));
  if (context != null) extra.push("--context-json", JSON.stringify(context));
  if (hypothesisId != null) extra.push("--hypothesis-id", String(hypothesisId));
  if (hypothesisVersion != null) {
    extra.push("--hypothesis-version", String(hypothesisVersion));
  }
  if (decision != null) extra.push("--decision", String(decision));
  if (decisionReason != null) {
    extra.push("--decision-reason", String(decisionReason));
  }

  const r = runPython("create", extra);
  if (!r.ok) {
    const status = r.error === "VALIDATION_ERROR" ? 400 : 500;
    return NextResponse.json({error: r.error, detail: r.detail},
      {status, headers});
  }
  return NextResponse.json(r.data ?? {ok: true}, {headers});
}
