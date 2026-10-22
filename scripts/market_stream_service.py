"""CLI del servicio local ``market-stream/v1`` (SSE, solo loopback).

Arranque/parada explicitos; no se lanza solo al abrir una pagina y no arranca el
monitor del bot.

Uso (desde la raiz del repo):

  python scripts/market_stream_service.py --port 8791
  python scripts/market_stream_service.py --port 8791 --stop
  python scripts/market_stream_service.py --port 8791 --max-seconds 60

La ventana viva contra Binance NO esta autorizada por este script: se prepara y
se ejecuta solo cuando la instruccion humana lo pida.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.market_stream_service import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
