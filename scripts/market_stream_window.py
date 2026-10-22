"""Ventana viva acotada para ``market-stream/v1`` — PREPARADA, NO EJECUTADA.

Este script existe para que la ventana Binance real se autorice por separado y
se ejecute con límites verificables. Sin ``--execute`` solo imprime el plan
(símbolos, intervalo, duración, presupuesto y reglas de parada) y no abre
ninguna conexión.

Con ``--execute``:

  * abre UNA conexión pública a ``wss://fstream.binance.com/market`` con los
    streams indicados (por defecto un contrato del trío canónico y uno elegible
    fuera del trío),
  * mide mensajes, última recepción, huecos, reconexiones, errores y memoria
    estimada del anillo,
  * para sola por duración, por número de mensajes o por presupuesto de
    reconexiones,
  * no escribe nada en disco (ni DB canónica ni caché del explorador) y no
    toca el monitor del bot, el trío canónico ni las sesiones Paper Lab.

Uso:

  python scripts/market_stream_window.py
  python scripts/market_stream_window.py --symbols BTCUSDT,MINAUSDT \
      --interval 1m --duration 60 --execute --out docs/evidence/stream-window.json

La ejecución real requiere autorización humana explícita.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.history_client import HistoryClient  # noqa: E402
from microstructure_probe.market_stream import (  # noqa: E402
    MAX_CONSUMERS_PER_STREAM,
    MAX_SUBSCRIPTIONS,
    RING_SIZE,
    STREAM_CONTRACT_VERSION,
    BinanceKlineTransport,
    KlineStreamHub,
    build_recovery,
)

DEFAULT_SYMBOLS = "BTCUSDT,MINAUSDT"
DEFAULT_INTERVAL = "1m"
DEFAULT_DURATION_S = 60.0
DEFAULT_MAX_MESSAGES = 400
DEFAULT_MAX_RECONNECTS = 3


def plan(args: argparse.Namespace) -> Dict[str, Any]:
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    return {
        "contract_version": STREAM_CONTRACT_VERSION,
        "mode": "LIVE_WINDOW_PLAN" if not args.execute else "LIVE_WINDOW_EXECUTE",
        "authorization": ("REQUIERE AUTORIZACION HUMANA" if not args.execute
                          else "AUTORIZADA POR EL OPERADOR"),
        "endpoint": "wss://fstream.binance.com/market/stream?streams=…",
        "symbols": symbols,
        "interval": args.interval,
        "limits": {
            "duration_s": args.duration,
            "max_messages": args.max_messages,
            "max_reconnects": args.max_reconnects,
            "max_subscriptions": MAX_SUBSCRIPTIONS,
            "max_consumers_per_stream": MAX_CONSUMERS_PER_STREAM,
            "ring_size": RING_SIZE,
            "persistence": "NONE",
            "rest_recovery": "acotado (2 paginas x 500 velas, <=6/min)",
        },
        "stop_rules": [
            "duracion alcanzada",
            "max_messages alcanzado",
            "reconexiones > max_reconnects",
            "error de protocolo repetido o identidad inconsistente",
            "cualquier necesidad de credenciales u orden (no contemplada)",
        ],
        "metrics": [
            "mensajes por stream y total",
            "primera/ultima recepcion (ms UTC) y edad",
            "velas provisionales vs cerradas",
            "huecos detectados/reparados/parciales",
            "reconexiones y ultimo error",
            "contadores invalid/late/out_of_order/duplicate",
            "memoria estimada del anillo por stream",
        ],
        "writes": "ninguna (sin DB canonica, sin cache, sin sesiones paper)",
        "bot": "no arranca ni modifica el monitor; suscripcion canonica intacta",
        "command_example": (
            "python scripts/market_stream_window.py --symbols BTCUSDT,MINAUSDT "
            "--interval 1m --duration 60 --execute --out docs/evidence/stream-window.json"
        ),
    }


async def run_window(args: argparse.Namespace) -> Dict[str, Any]:
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    client = HistoryClient(request_timeout=20.0, max_429=1, max_retries=1)
    hub = KlineStreamHub(recovery=build_recovery(client))
    transport = BinanceKlineTransport(hub)
    consumers = []
    for index, symbol in enumerate(symbols):
        consumer, error = hub.subscribe(
            symbol, args.interval, consumer_id=f"window-{index}-{symbol}")
        if consumer is None:
            return {"stopped": True, "reason": f"SUBSCRIBE_FAILED:{symbol}:{error}"}
        hub.ready(consumer, None)
        consumers.append((symbol, consumer))

    stop = asyncio.Event()
    task = asyncio.ensure_future(transport.run(stop))
    started_at_ms = int(time.time() * 1000)
    messages_seen = 0
    reported: Dict[str, int] = {}
    stop_reason = "DURATION"

    try:
        deadline = time.monotonic() + float(args.duration)
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            health = hub.health()
            total = int(health["counters"].get("messages", 0))
            if total != messages_seen:
                messages_seen = total
            for stream in health["streams"]:
                key = f"{stream['symbol']}@{stream['interval']}"
                count = int((stream.get("counters") or {}).get("messages", 0))
                if count != reported.get(key, 0):
                    reported[key] = count
            if messages_seen >= int(args.max_messages):
                stop_reason = "MAX_MESSAGES"
                break
            if int(health["socket"].get("reconnects") or 0) > int(args.max_reconnects):
                stop_reason = "MAX_RECONNECTS"
                break
    finally:
        stop.set()
        try:
            await asyncio.wait_for(task, timeout=10.0)
        except asyncio.TimeoutError:
            task.cancel()
        for _, consumer in consumers:
            hub.unsubscribe(consumer)
        # Segunda pasada para dejar metricas finales coherentes.
        await asyncio.sleep(0)

    finished_at_ms = int(time.time() * 1000)
    health = hub.health()
    for stream in health["streams"]:
        stream["memory_bytes_estimate"] = int(stream.get("ring") or 0) * 192
    health["socket"].pop("route", None)
    return {
        "stopped": True,
        "reason": stop_reason,
        "contract_version": STREAM_CONTRACT_VERSION,
        "started_at_ms": started_at_ms,
        "finished_at_ms": finished_at_ms,
        "duration_s": round((finished_at_ms - started_at_ms) / 1000, 2),
        "symbols": symbols,
        "interval": args.interval,
        "health": health,
        "transport_stop_reason": transport.stop_reason,
        "authorization": "AUTORIZADA POR EL OPERADOR",
    }


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Ventana viva acotada market-stream/v1")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS,
                        help="uno del trio canonico y otro elegible fuera del trio")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_S)
    parser.add_argument("--max-messages", type=int, default=DEFAULT_MAX_MESSAGES)
    parser.add_argument("--max-reconnects", type=int, default=DEFAULT_MAX_RECONNECTS)
    parser.add_argument("--out", default=None, help="ruta JSON de evidencia")
    parser.add_argument("--execute", action="store_true",
                        help="abre la conexion real (requiere autorizacion)")
    args = parser.parse_args(argv)

    if not args.execute:
        print(json.dumps(plan(args), ensure_ascii=False, indent=2))
        return 0

    result = asyncio.run(run_window(args))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "written": str(out)}, ensure_ascii=False))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
