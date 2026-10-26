"""Demostracion local de market-indicators/v1 (sin red, sin Binance).

Construye una cache temporal aislada con velas sinteticas y llama a
``series_payload`` real (``client=None``: cero upstream) para mostrar el
bloque versionado de indicadores:

  * ``A``: 16 velas cerradas contiguas en 1h con volumen estable;
  * ``B``: la misma serie con un hueco interior y volumen ausente;
  * ``C``: mark_klines (OHLC sin volumen) para volumes -> UNKNOWN.

El JSON resultante documenta formulas, calentamiento, huecos y la lista de
indicadores declinados (fuente ausente). Uso:
  python scripts/indicators_v1_demo.py --out docs/evidence/indicators-v1-2026-10-25.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from microstructure_probe import market_explorer as MX  # noqa: E402
from microstructure_probe.market_cache import MarketCache  # noqa: E402

STEP = 3_600_000  # 1h
T0 = 1_790_000_000_000


def _bar(open_time: int, close: float, base_volume: str = "12.0"):
    return {
        "open_time": open_time,
        "open": f"{close - 0.5:.6g}",
        "high": f"{close + 0.5:.6g}",
        "low": f"{close - 0.6:.6g}",
        "close": f"{close:.6g}",
        "base_volume": base_volume,
        "quote_volume": f"{float(base_volume) * close:.6g}",
        "trade_count": 100,
        "close_time": open_time + STEP - 1,
        "fetched_at": open_time,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    now = T0 + 16 * STEP  # 16 velas ya cerradas
    tmp = Path(tempfile.mkdtemp(prefix="indicators_demo_"))
    try:
        cache = MarketCache(tmp / "cache.db")
        cache.init_db()

        # --- Serie A: continua, volumen constante --------------------------
        closes = [100.0 + 0.6 * i + (0.35 * (-1) ** i) for i in range(16)]
        bars_a = [_bar(T0 + i * STEP, closes[i]) for i in range(16)]
        cache.upsert_klines("DEMOUSDT", "1h", "klines", bars_a, T0)
        payload_a = MX.series_payload(cache, None, symbol="DEMOUSDT",
                                      interval="1h", from_ms=T0,
                                      to_ms=T0 + 15 * STEP, now_ms=now,
                                      allow_fetch=False)

        # --- Serie B: hueco interior + volumen ausente en una vela ---------
        bars_b = [_bar(T0 + i * STEP, closes[i]) for i in range(16)]
        bars_b[3]["open_time"] = T0 + 2 * STEP + 1  # fuera de la rejilla
        bars_b = bars_b[:3] + bars_b[4:]            # hueco en el indice 3
        bars_b[10]["base_volume"] = None
        cache.upsert_klines("HOLESUSDT", "1h", "klines", bars_b, T0)
        payload_b = MX.series_payload(cache, None, symbol="HOLESUSDT",
                                      interval="1h", from_ms=T0,
                                      to_ms=T0 + 15 * STEP, now_ms=now,
                                      allow_fetch=False)

        # --- Serie C: mark_klines (sin volumen) ----------------------------
        bars_c = [_bar(T0 + i * STEP, closes[i]) for i in range(16)]
        for bar in bars_c:
            bar["base_volume"] = None
            bar["quote_volume"] = None
        cache.upsert_klines("MARKUSDT", "1h", "mark_klines", bars_c, T0)
        payload_c = MX.series_payload(cache, None, symbol="MARKUSDT",
                                      interval="1h", source="mark_klines",
                                      from_ms=T0, to_ms=T0 + 15 * STEP,
                                      now_ms=now, allow_fetch=False)

        def compact(payload, keep_rows=True):
            block = payload["indicators"]
            out = {
                "symbol": payload["symbol"],
                "interval": payload["interval"],
                "source": payload["source"],
                "candles_in_payload": len(payload["candles"]),
                "coverage_state": payload["coverage"]["state"],
                "indicators_block": block if keep_rows else None,
            }
            return out

        evidence = {
            "what": "market-indicators/v1: primera integracion vertical de "
                    "indicadores compartidos (backend autoridad)",
            "transport": "local sqlite; client=None; 0 peticiones upstream; "
                         "no se abrio Binance",
            "binance_calls": 0,
            "contract_version": payload_a["indicators"]["contract_version"],
            "supported": payload_a["indicators"]["supported"],
            "declined": payload_a["indicators"]["declined"],
            "definitions": payload_a["indicators"]["definitions"],
            "series_a_continuous": compact(payload_a),
            "series_b_gap_and_missing_volume": compact(payload_b),
            "series_c_mark_klines_no_volume": compact(payload_c),
            "rules": [
                "Solo velas cerradas: la vela en formacion queda excluida "
                "(provisional_policy PROVISIONAL_EXCLUDED).",
                "Sin lookahead: el valor de la vela t solo lee velas <= t.",
                "Hueco/warmup/volumen ausente -> UNKNOWN con motivo, nunca cero.",
                "Bloques declinados: flujo, spread, profundidad, OI y contexto "
                "BTC no se derivan de OHLC.",
            ],
        }
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"evidence: {out_path}")
        print(f"series A filas: {len(payload_a['indicators']['series'])},"
              f" B: {len(payload_b['indicators']['series'])},"
              f" C: {len(payload_c['indicators']['series'])}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
