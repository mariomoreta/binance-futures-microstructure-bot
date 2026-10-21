import {NextResponse} from "next/server";
import {existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync} from "node:fs";
import {join} from "node:path";

// Persistencia de sesiones Paper Lab (ingenieria). Los archivos viven en un
// directorio aislado, fuera de datos operacionales y de DBs canonicas.
// Solo lectura/escritura de sesiones propias del usuario de este cliente.
// No hay Binance, no hay ordenes, no hay capital real.
const ROOT = process.env.PAPER_LAB_SESSIONS_DIR ?? "C:/proyectos/binance-futures-microstructure-bot";
const SESSIONS_DIR = join(ROOT, "paper-lab-sessions");

function ensureDir(): void {
  mkdirSync(SESSIONS_DIR, {recursive: true});
}

function listSessions(): Array<{session_id: string; status: string; created_at_ms: number; symbol: string; direction: string}> {
  ensureDir();
  try {
    return readdirSync(SESSIONS_DIR)
      .filter((f) => f.endsWith(".json"))
      .map((f) => {
        try {
          const raw = readFileSync(join(SESSIONS_DIR, f), "utf8");
          const j = JSON.parse(raw);
          return {
            session_id: j.session_id ?? f.replace(/\.json$/, ""),
            status: j.status ?? "desconocido",
            created_at_ms: typeof j.created_at_ms === "number" ? j.created_at_ms : 0,
            symbol: j.config?.symbol ?? "—",
            direction: j.config?.direction ?? "—",
          };
        } catch {
          return {session_id: f.replace(/\.json$/, ""), status: "ilegible", created_at_ms: 0, symbol: "—", direction: "—"};
        }
      })
      .sort((a, b) => b.created_at_ms - a.created_at_ms);
  } catch {
    return [];
  }
}

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

export async function GET(): Promise<NextResponse> {
  try {
    const sessions = listSessions();
    return NextResponse.json({sessions}, {headers});
  } catch (e) {
    return NextResponse.json({error: "SESSIONS_LIST_FAILED", detail: (e as Error).message}, {status: 500, headers});
  }
}

export async function POST(req: Request): Promise<NextResponse> {
  try {
    let body: unknown;
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({error: "INVALID_BODY"}, {status: 400, headers});
    }
    const session = body as {session_id?: unknown; status?: unknown; [key: string]: unknown};
    if (!session || typeof session !== "object" || typeof session.session_id !== "string") {
      return NextResponse.json({error: "SESSION_ID_REQUIRED"}, {status: 400, headers});
    }
    ensureDir();
    const path = join(SESSIONS_DIR, `${session.session_id}.json`);
    writeFileSync(path, JSON.stringify(session, null, 1));
    const sessions = listSessions();
    return NextResponse.json({ok: true, session_id: session.session_id, sessions}, {headers});
  } catch (e) {
    return NextResponse.json({error: "SESSION_SAVE_FAILED", detail: (e as Error).message}, {status: 500, headers});
  }
}
