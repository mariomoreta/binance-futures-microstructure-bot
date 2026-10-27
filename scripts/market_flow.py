"""CLI de consulta y envio de flujo agresivo comprador/vendedor (transporte local).

Consulta el servicio compartido de flujo (``market_flow_service.py``) o, si no
hay servicio en ejecucion, devuelve SIN COBERTURA (valores desconocidos,
live=false). Nunca genera operaciones ficticias ni reconstruye desde OHLC.

Uso:

    # Consultar estado de un simbolo (sin fuente: SIN COBERTURA)
    python scripts/market_flow.py --symbol BTCUSDT --as-of-ms <ms>

    # Enviar un evento aggTrade del transporte local al servicio compartido
    python scripts/market_flow.py --symbol BTCUSDT --event-id abc123 \
        --event-ms <ms> --price 100000 --quantity 0.5 --buyer-is-maker false

    # Detener el servicio de flujo
    python scripts/market_flow_service.py --stop
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8799


def _empty_block(symbol: str, as_of_ms: int) -> dict:
    return {
        "contract_version": "market-flow/v1",
        "availability": "LIVE_CAPTURE_ONLY",
        "coverage": "NO_COVERAGE_BEFORE_FIRST_EVENT",
        "identity": {"symbol": symbol, "venue": "binance",
                     "market_type": "usd_m_futures",
                     "source": "aggTrade_local_transport"},
        "as_of_ms": as_of_ms,
        "freshness_ms": None,
        "live": False,
        "trades_total": 0,
        "rpi_base_total": None,
        "rpi_notional_total": None,
        "rpi_trades": None,
        "dropped_late": 0,
        "dropped_invalid": 0,
        "horizons": {},
        "baselines": {},
        "acceleration": {},
        "deduplication": {"seen_event_ids": 0},
        "notes": ["Sin servicio de flujo conectado: sin cobertura, sin valores "
                  "ni ceros inventados."],
    }


def _get(url: str, timeout: float = 10.0) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {"ok": False, "error": "SERVICE_NOT_REACHABLE",
                "detail": str(exc)}


def _post(url: str, payload: dict, timeout: float = 10.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {"ok": False, "error": "SERVICE_NOT_REACHABLE",
                "detail": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consulta/envia flujo agresivo (transporte local)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host loopback")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="Puerto del servicio de flujo")
    parser.add_argument("--symbol", required=True, help="Simbolo USD-M")
    parser.add_argument("--as-of-ms", type=int, default=None,
                        help="Instante de consulta (ms Unix UTC)")
    # Envio de evento (transporte local)
    parser.add_argument("--event-id", default=None, help="Identificador aggTrade")
    parser.add_argument("--event-ms", type=int, default=None,
                        help="Tiempo del evento (ms Unix UTC)")
    parser.add_argument("--price", type=float, default=None,
                        help="Precio del trade")
    parser.add_argument("--quantity", type=float, default=None,
                        help="Cantidad base del trade")
    parser.add_argument("--buyer-is-maker", action="store_true",
                        help="El comprador es maker (agresor SELL)")
    parser.add_argument("--no-buyer-is-maker", action="store_true",
                        help="El comprador es taker (agresor BUY)")
    parser.add_argument("--normal-quantity", type=float, default=None,
                        help="Cantidad normal sin RPI (opcional)")
    args = parser.parse_args()

    base = f"http://{args.host}:{args.port}"
    symbol = str(args.symbol).strip().upper()
    as_of_ms = args.as_of_ms

    # Modo envio de evento (transporte local al servicio compartido)
    if args.event_id is not None or args.event_ms is not None:
        if args.event_id is None or args.event_ms is None:
            print(json.dumps({"ok": False, "error": "INVALID_REQUEST",
                              "detail": "--event-id y --event-ms son obligatorios "
                              "para enviar un evento"}))
            return 1
        if args.price is None or args.quantity is None:
            print(json.dumps({"ok": False, "error": "INVALID_REQUEST",
                              "detail": "--price y --quantity son obligatorios"}))
            return 1
        buyer_is_maker = args.no_buyer_is_maker is False and (
            args.buyer_is_maker or not args.no_buyer_is_maker)
        # Por defecto, si no se especifica, buyer_is_maker=False (agresor BUY)
        if args.buyer_is_maker and args.no_buyer_is_maker:
            print(json.dumps({"ok": False, "error": "INVALID_REQUEST",
                              "detail": "especifique solo uno de --buyer-is-maker / --no-buyer-is-maker"}))
            return 1
        if not args.buyer_is_maker and not args.no_buyer_is_maker:
            # Default: comprador taker => agresor BUY
            buyer_is_maker = False
        payload = {
            "symbol": symbol,
            "event_id": args.event_id,
            "event_ms": args.event_ms,
            "price": args.price,
            "quantity": args.quantity,
            "buyer_is_maker": buyer_is_maker,
        }
        if args.normal_quantity is not None:
            payload["normal_quantity"] = args.normal_quantity
        result = _post(f"{base}/flow", payload)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    # Modo consulta: preguntar al servicio compartido
    result = _get(f"{base}/flow?symbol={symbol}"
                  f"{'&as_of_ms=' + str(as_of_ms) if as_of_ms else ''}")
    if not result.get("ok"):
        # Servicio no alcanzado: SIN COBERTURA, sin sinteticos
        block = _empty_block(symbol, as_of_ms or 0)
        print(json.dumps({"ok": False, "data": block,
                          "error": result.get("error", "SERVICE_ERROR"),
                          "detail": result.get("detail")}, ensure_ascii=False))
        return 0
    print(json.dumps({"ok": True, "data": result.get("data")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
