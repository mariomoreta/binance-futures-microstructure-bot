"""Explorador de mercado Binance USD-M — CLI JSON para el BFF de Next.js.

Solo lectura publica acotada: catalogo de contratos (exchangeInfo) e historico
de velas (klines/markPriceKlines) reutilizando lo ya almacenado antes de
consultar Binance. No hay credenciales, no hay ordenes, no hay monitor, no hay
websocket continuo y no se anade ningun simbolo al universo del bot.

Uso (desde la raiz del repo):
  python scripts/market_explorer.py --action catalog --query BTC --limit 20
  python scripts/market_explorer.py --action catalog --refresh
  python scripts/market_explorer.py --action series --symbol BTCUSDT \
      --interval 1h --bars 300 --pages 2
  python scripts/market_explorer.py --action series --symbol BTCUSDT \
      --interval 1h --from-ms 1788816600000 --to-ms 1788826600000 --no-fetch

Salida: JSON en stdout con claves "ok" y "data" (o "error"/"detail").
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.market_cache import (  # noqa: E402
    CATALOG_TTL_MS,
    MAX_FETCH_REQUESTS_PER_WINDOW,
    MarketCache,
)
from microstructure_probe.market_explorer import (  # noqa: E402
    DEFAULT_SERIES_BARS,
    EXPLORABLE_INTERVALS,
    MAX_PAGES_PER_REQUEST,
    PAGE_LIMIT,
    SOURCES,
    build_client,
    catalog_payload,
    series_payload,
)

ALLOWED_ACTIONS = {"catalog", "series"}


def _fail(code: str, detail: str) -> Dict[str, Any]:
    return {"ok": False, "error": code, "detail": detail}


def _ok(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "data": data}


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--action", required=True, help="catalog | series")
    ap.add_argument("--query", default="", help="fragmento de simbolo/asset")
    ap.add_argument("--limit", type=int, default=50,
                    help="maximo de filas de catalogo (1..500)")
    ap.add_argument("--eligible-only", action="store_true",
                    help="solo contratos elegibles (PERPETUAL+TRADING+USDT)")
    ap.add_argument("--refresh", action="store_true",
                    help="forzar refresco del catalogo (1 peticion)")
    ap.add_argument("--max-age-ms", type=int, default=CATALOG_TTL_MS,
                    help="TTL del catalogo antes de refrescar")
    ap.add_argument("--symbol", default="", help="contrato USD-M (p.ej. BTCUSDT)")
    ap.add_argument("--interval", default="1h",
                    help="temporalidad: " + "|".join(EXPLORABLE_INTERVALS))
    ap.add_argument("--source", default="klines", help="klines | mark_klines")
    ap.add_argument("--from-ms", type=int, default=None, help="inicio (ms UTC)")
    ap.add_argument("--to-ms", type=int, default=None, help="fin (ms UTC)")
    ap.add_argument("--bars", type=int, default=DEFAULT_SERIES_BARS,
                    help="velas del tramo inicial cuando no se da from-ms")
    ap.add_argument("--pages", type=int, default=MAX_PAGES_PER_REQUEST,
                    help="paginas maximas a adquirir (acotado)")
    ap.add_argument("--page-limit", type=int, default=PAGE_LIMIT,
                    help="velas por pagina (maximo del endpoint)")
    ap.add_argument("--no-fetch", action="store_true",
                    help="solo lectura de lo almacenado; no consulta Binance")
    ap.add_argument("--probe-earliest", action="store_true",
                    help="una peticion extra para conocer el inicio de historico")
    ap.add_argument("--now-ms", type=int, default=None,
                    help="reloj de referencia (determinismo en pruebas)")
    ap.add_argument("--cache-db", default=None,
                    help="ruta de la cache aislada (default data/market-cache)")
    ap.add_argument("--history-db", default=None,
                    help="ruta de la DB historica de investigacion (read-only)")
    args = ap.parse_args(argv)

    if args.action not in ALLOWED_ACTIONS:
        print(json.dumps(_fail("ACTION_NOT_ALLOWED",
                               f"accion no permitida: {args.action}")),
              file=sys.stderr)
        return 2

    now_ms = args.now_ms if args.now_ms is not None else int(time.time() * 1000)
    cache = MarketCache(Path(args.cache_db) if args.cache_db else None)
    cache.init_db()
    history_db = Path(args.history_db) if args.history_db else None
    pages = max(1, min(int(args.pages), MAX_PAGES_PER_REQUEST))
    page_limit = max(1, min(int(args.page_limit), PAGE_LIMIT))

    try:
        if args.action == "catalog":
            if args.query.strip() and len(args.query.strip()) > 32:
                print(json.dumps(_fail("INVALID_QUERY",
                                       "la consulta excede 32 caracteres")),
                      file=sys.stderr)
                return 2
            if not (1 <= int(args.limit) <= 500):
                print(json.dumps(_fail("INVALID_LIMIT",
                                       "limit debe estar entre 1 y 500")),
                      file=sys.stderr)
                return 2
            client = build_client()
            data = catalog_payload(
                cache, client, query=args.query, limit=int(args.limit),
                eligible_only=bool(args.eligible_only), refresh=bool(args.refresh),
                max_age_ms=int(args.max_age_ms), now_ms=now_ms,
                allow_fetch=not args.no_fetch,
            )
            print(json.dumps(_ok(data)))
            return 0

        if args.source not in SOURCES:
            print(json.dumps(_fail("INVALID_SOURCE", str(args.source))),
                  file=sys.stderr)
            return 2
        client = build_client()
        data = series_payload(
            cache, client if not args.no_fetch else None,
            symbol=args.symbol, interval=args.interval, source=args.source,
            from_ms=args.from_ms, to_ms=args.to_ms, pages=pages,
            allow_fetch=not args.no_fetch, page_limit=page_limit,
            bars=int(args.bars), probe_earliest=bool(args.probe_earliest),
            now_ms=now_ms, history_db=history_db,
        )
        data["budget"] = {
            "window_ms": 60_000,
            "max_requests_per_window": MAX_FETCH_REQUESTS_PER_WINDOW,
            "used_in_window": cache.requests_in_window(now_ms),
            "max_pages_per_request": MAX_PAGES_PER_REQUEST,
            "page_limit": page_limit,
            "concurrency": 1,
        }
        print(json.dumps(_ok(data)))
        return 0
    except ValueError as exc:
        print(json.dumps(_fail("VALIDATION_ERROR", str(exc))), file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - se reporta tal cual
        print(json.dumps(_fail("INTERNAL_ERROR", str(exc))), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
