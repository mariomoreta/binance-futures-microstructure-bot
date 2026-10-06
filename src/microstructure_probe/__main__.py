from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from pathlib import Path

from .config import load_config
from .probe import MarketProbe, build_stream_urls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe publico Binance USD-M Futures")
    parser.add_argument(
        "--config",
        default="config/probe.json",
        help="Ruta al archivo JSON de configuracion",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Detener despues de N segundos; por defecto corre hasta Ctrl+C",
    )
    parser.add_argument(
        "--show-streams",
        action="store_true",
        help="Mostrar URLs calculadas y salir sin conectarse",
    )
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    config = load_config(Path(args.config))
    if args.show_streams:
        print(json.dumps(build_stream_urls(config), indent=2))
        return
    if args.duration is not None and args.duration <= 0:
        raise ValueError("--duration debe ser mayor que cero")

    probe = MarketProbe(config)
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, probe.stop)
        except (NotImplementedError, RuntimeError):
            pass
    await probe.run(args.duration)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

