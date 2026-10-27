"""CLI para arrancar/parar el servicio local de flujo ``market-flow/v1``.

Transporte local exclusivamente (loopback). Sin conexion a Binance publico.
Sin datos sinteticos: sin fuente conectada, devuelve SIN COBERTURA.

Uso (PowerShell, desde la raiz del repositorio):

    python scripts/market_flow_service.py --port 8799
    python scripts/market_flow_service.py --port 8799 --stop
    python scripts/market_flow_service.py --port 8799 --max-seconds 120

Endpoints (solo 127.0.0.1):

    GET  /health
    POST /flow        {symbol, event_id, event_ms, price, quantity, buyer_is_maker}
    GET  /flow?symbol=BTCUSDT
    GET  /flow/stream?symbol=BTCUSDT   (SSE)
    POST /shutdown
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from microstructure_probe.market_flow_service import FlowService, DEFAULT_PORT


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Servicio local de flujo agresivo comprador/vendedor")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="Puerto loopback (default 8799)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host loopback (default 127.0.0.1)")
    parser.add_argument("--stop", action="store_true",
                        help="Solicitar parada ordenada al servicio")
    parser.add_argument("--max-seconds", type=float, default=None,
                        help="Detener automaticamente tras N segundos")
    parser.add_argument("--token", default=None,
                        help="Token opcional para /shutdown y /flow/stream")
    args = parser.parse_args()

    service = FlowService(
        host=args.host, port=args.port, token=args.token,
        max_seconds=args.max_seconds,
    )

    if args.stop:
        # Solicitar parada via HTTP al servicio en ejecucion
        import urllib.request, urllib.error
        try:
            req = urllib.request.Request(
                f"http://{args.host}:{args.port}/shutdown",
                data=b"{}", headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
            print(body)
            return 0
        except urllib.error.URLError as exc:
            print(json.dumps({"ok": False, "error": "SERVICE_NOT_REACHABLE",
                              "detail": str(exc)}))
            return 1

    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        asyncio.run(service.stop())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
