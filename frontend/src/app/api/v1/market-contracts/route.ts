import {NextResponse} from "next/server";
import {explorerOriginAllowed, runMarketExplorer, statusForError} from "@/lib/explorer-bridge";

// Busqueda de contratos USD-M Futures sobre el catalogo cacheado.
// Solo lectura publica: el refresco (1 peticion) lo decide el backend segun
// TTL o `refresh=1`. Buscar o abrir un simbolo NO abre posicion, NO inicia el
// monitor y NO lo anade al universo del bot.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

export async function GET(req: Request) {
  if (!explorerOriginAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN_ORIGIN"}, {status: 403, headers});
  }
  const params = new URL(req.url).searchParams;
  if (params.getAll("q").length > 1 || params.getAll("limit").length > 1
    || params.getAll("eligible").length > 1 || params.getAll("refresh").length > 1) {
    return NextResponse.json({error: "INVALID_QUERY"}, {status: 400, headers});
  }
  const query = (params.get("q") ?? "").trim();
  if (query.length > 32) {
    return NextResponse.json({error: "INVALID_QUERY", detail: "q excede 32 caracteres"},
      {status: 400, headers});
  }
  const limit = Number(params.get("limit") ?? "20");
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
    return NextResponse.json({error: "INVALID_LIMIT", detail: "limit debe estar entre 1 y 50"},
      {status: 400, headers});
  }
  const args = ["--action", "catalog", "--query", query, "--limit", String(limit)];
  if (params.get("eligible") === "1") args.push("--eligible-only");
  if (params.get("refresh") === "1") args.push("--refresh");
  const result = runMarketExplorer(args);
  if (!result.ok || !result.data) {
    return NextResponse.json({error: result.error ?? "CATALOG_UNAVAILABLE",
      detail: result.detail ?? null}, {status: statusForError(result.error), headers});
  }
  return NextResponse.json(result.data, {headers});
}
