"""CLI local de flujo agresivo comprador/vendedor (transporte local).

Calcula market-flow/v1 para un simbolo usando FlowEngine con datos de
captura local simulada (sin conexion a Binance publico). Cada invocacion es
independiente: no hay estado persistente entre peticiones.

Uso:
  python scripts/market_flow.py --symbol BTCUSDT --as-of-ms <ms>

Salida: JSON con claves ok/data o error/detail (patron del puente BFF).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, "src")

from microstructure_probe.flow import FlowEngine
from microstructure_probe.market_flow import (
    MARKET_FLOW_CONTRACT_VERSION,
    compute_flow_block,
    ingest_aggtrade,
)


def _simulate_local_capture(symbol: str, engine: FlowEngine, as_of_ms: int) -> None:
    """Ingresa una secuencia breve de aggTrades de transporte local.

    Datos sinteticos SOLO para prueba de transporte local: no representan
    mercado real ni se usan como senal. buyer_is_maker se alterna para
    ejercitar ambos lados (agresor BUY y agresor SELL).
    """
    base = as_of_ms - 60_000  # ventana de 1 minuto
    ticks: List[tuple[int, float, float, bool]] = [
        (base + 5_000, 100_000.0, 0.5, False),   # agresor BUY
        (base + 10_000, 100_001.0, 0.3, True),    # agresor SELL
        (base + 15_000, 100_002.0, 0.8, False),   # agresor BUY
        (base + 20_000, 100_003.0, 0.2, True),    # agresor SELL
        (base + 25_000, 100_004.0, 1.0, False),   # agresor BUY
        (base + 30_000, 100_005.0, 0.4, True),    # agresor SELL
        (base + 35_000, 100_006.0, 0.6, False),   # agresor BUY
        (base + 40_000, 100_007.0, 0.1, True),    # agresor SELL
        (base + 45_000, 100_008.0, 0.9, False),   # agresor BUY
        (base + 50_000, 100_009.0, 0.3, True),    # agresor SELL
    ]
    for t_ms, price, qty, bim in ticks:
        ingest_aggtrade(engine, symbol, t_ms, price, qty, bim)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Flujo agresivo comprador/vendedor (transporte local)")
    parser.add_argument("--symbol", required=True, help="Simbolo USD-M")
    parser.add_argument("--as-of-ms", type=int, required=True,
                        help="Instante de consulta (ms Unix UTC)")
    args = parser.parse_args()

    symbol = str(args.symbol).strip().upper()
    as_of_ms = int(args.as_of_ms)

    engine = FlowEngine(symbols=(symbol,), min_baseline_buckets=5)
    _simulate_local_capture(symbol, engine, as_of_ms)

    block = compute_flow_block(engine, symbol, as_of_ms)
    print(json.dumps({"ok": True, "data": block}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": "FLOW_CALC_FAILED",
                          "detail": str(exc)[:500]}, ensure_ascii=False))
        raise SystemExit(1)
