import {randomUUID} from "node:crypto";
import {NextResponse} from "next/server";
import {explorerOriginAllowed, runMarketExplorer, statusForError} from "@/lib/explorer-bridge";

// Historico de velas Binance USD-M consultado bajo demanda.
// Politica acotada (la aplica tambien el backend): como maximo 2 paginas, 1000
// velas por pagina, 1 peticion concurrente, 20 s de timeout por peticion, 30
// peticiones/minuto por ventana movil y politica 429/418 sin reintentos
// agresivos. Si el presupuesto se agota se devuelve lo almacenado con
// `fetch.error` explicito (no se oculta ni se reintenta en bucle).
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};

const SYMBOL_RE = /^[A-Z0-9]{2,32}$/;
const INTERVALS = new Set(["1m", "5m", "15m", "1h", "4h", "1d"]);
const SOURCES = new Set(["klines", "mark_klines"]);

function intParam(params: URLSearchParams, name: string): number | null | undefined {
  const values = params.getAll(name);
  if (values.length === 0) return undefined;
  if (values.length > 1) return null;
  const raw = values[0] ?? "";
  if (!/^-?\d{1,16}$/.test(raw)) return null;
  const value = Number(raw);
  return Number.isSafeInteger(value) ? value : null;
}

export async function GET(req: Request) {
  if (!explorerOriginAllowed(req)) {
    return NextResponse.json({error: "FORBIDDEN_ORIGIN"}, {status: 403, headers});
  }
  const params = new URL(req.url).searchParams;
  const symbol = (params.get("symbol") ?? "").trim().toUpperCase();
  if (!SYMBOL_RE.test(symbol)) {
    return NextResponse.json({error: "INVALID_SYMBOL"}, {status: 400, headers});
  }
  const interval = params.get("interval") ?? "1h";
  if (!INTERVALS.has(interval)) {
    return NextResponse.json({error: "INVALID_INTERVAL"}, {status: 400, headers});
  }
  const source = params.get("source") ?? "klines";
  if (!SOURCES.has(source)) {
    return NextResponse.json({error: "INVALID_SOURCE"}, {status: 400, headers});
  }
  const fromMs = intParam(params, "from_ms");
  const toMs = intParam(params, "to_ms");
  const atMs = intParam(params, "at_ms");
  // Reloj T de la sesion de ingenieria: si se pasa, se usa como to_ms para
  // que el payload solo incluya velas conocidas en T y los indicadores /
  // contexto BTC se recalculen sobre ese prefijo (sin futuros).
  const effectiveToMs = atMs !== undefined ? atMs : toMs;
  if (effectiveToMs != null && fromMs != null && effectiveToMs < fromMs) {
    return NextResponse.json({error: "INVALID_RANGE"}, {status: 400, headers});
  }
  const bars = intParam(params, "bars");
  const pages = intParam(params, "pages");
  const pageLimit = intParam(params, "page_limit");
  if (bars === null || (bars !== undefined && (bars < 50 || bars > 1000))) {
    return NextResponse.json({error: "INVALID_BARS"}, {status: 400, headers});
  }
  if (pages === null || (pages !== undefined && (pages < 1 || pages > 2))) {
    return NextResponse.json({error: "INVALID_PAGES"}, {status: 400, headers});
  }
  if (pageLimit === null || (pageLimit !== undefined && (pageLimit < 50 || pageLimit > 1000))) {
    return NextResponse.json({error: "INVALID_PAGE_LIMIT"}, {status: 400, headers});
  }
  // `read_only=1` es la opcion de solo lectura controlada por backend para la
  // sesion de ingeniería/replay sobre caché: fuerza --no-fetch (cero upstream,
  // solo lo almacenado, ausencia -> motivo sin activar fetch). Sin ella, el
  // explorador normal conserva la adquisición bajo demanda sujeta a los
  // presupuestos existentes (ledger compartido, pages <= 2, 30 req/min).
  const readOnly = params.get("read_only") === "1";
  const args = [
    "--action", "series",
    "--symbol", symbol,
    "--interval", interval,
    "--source", source,
    ...(readOnly ? ["--no-fetch"] : []),
    "--pages", String(pages ?? 1),
    "--page-limit", String(pageLimit ?? 300),
    // Un id de ejecucion por peticion: vincula las filas del ledger de
    // presupuesto (reservadas por intento, antes del transporte) con la
    // consulta que llego del dashboard.
    "--execution-id", `bff-${randomUUID()}`,
  ];
  if (fromMs !== null) args.push("--from-ms", String(fromMs));
  if (effectiveToMs !== null) args.push("--to-ms", String(effectiveToMs));
  if (bars !== undefined) args.push("--bars", String(bars));
  if (params.get("probe_earliest") === "1") args.push("--probe-earliest");
  const result = runMarketExplorer(args);
  if (!result.ok || !result.data) {
    return NextResponse.json({error: result.error ?? "SERIES_UNAVAILABLE",
      detail: result.detail ?? null}, {status: statusForError(result.error), headers});
  }
  return NextResponse.json(result.data, {headers});
}
