from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import time
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

    # P1-11B.1: EVERY canonical launch self-registers (direct terminal /
    # agent launches included) so the dashboard discovers the probe
    # without having launched it. Registry failures never break the probe.
    from . import control
    started_wall = time.time()
    try:
        reg = control.try_register(args.duration)
    except Exception as exc:  # never break data collection on registry IO
        logging.getLogger(__name__).warning(
            json.dumps({"kind": "registry_error", "error": str(exc)}))
        reg = {"registered": True, "degraded": "registry-exception"}
    if not reg.get("registered"):
        print(json.dumps({"kind": "already_running",
                          "detail": reg.get("already_running")}))
        raise SystemExit(2)

    probe = MarketProbe(config)
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, probe.stop)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        await probe.run(args.duration)
    except KeyboardInterrupt:
        control.mark_stopped("keyboard-interrupt", exit_code=0)
        raise
    except asyncio.CancelledError:
        control.mark_stopped("cancelled", exit_code=0)
        raise
    except Exception as exc:
        control.mark_failed(f"exception: {type(exc).__name__}: {exc}")
        raise
    elapsed = time.time() - started_wall
    if args.duration is not None and elapsed >= float(args.duration):
        control.mark_completed(exit_code=0)
    else:
        control.mark_stopped("run-returned", exit_code=0)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

