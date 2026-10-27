"""Contrato versionado de flujo agresivo comprador/vendedor (``market-flow/v1``).

Backend como unica autoridad: calcula flujo desde aggTrade (post-skew-guard,
via :class:`microstructure_probe.flow.FlowEngine`) y publica salida versionada.
El navegador no recalcula: solo refleja valores y reasons ya emitidos.

NO reconstruye flujo historico desde OHLC: sin cobertura antes del inicio de
captura. El flujo solo existe para datos in vivo del transporte local; antes
del primer evento de captura no hay cobertura ni valores inventados.

Interpretacion buyer-is-maker (verificada, docs/MARKET_DATA.md):
- ``m=true``  -> buyer is maker -> agresor es SELL (side=-1)
- ``m=false`` -> buyer is taker -> agresor es BUY  (side=+1)
- El maker nunca es el agresor; el lado nunca se adivina.

Deduplicacion: trades con mismo ``E`` son nuevo volumen (el WS nunca
redelibera), no duplicados. ``event_ms < newest seen`` se descuenta
(``dropped_late``) y nunca reescribe historial.

Unidades: notional en cotizada (USDT), base en moneda base, delta = buy -
sell (cotizada), delta_ratio en [-1,+1].
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .flow import FlowEngine, FLOW_HORIZON_ORDER

MARKET_FLOW_CONTRACT_VERSION = "market-flow/v1"
FLOW_AVAILABILITY = "LIVE_CAPTURE_ONLY"
NO_COVERAGE_BEFORE_FIRST_EVENT = "NO_COVERAGE_BEFORE_FIRST_CAPTURE"


def compute_flow_block(
    engine: FlowEngine,
    symbol: str,
    as_of_ms: int,
) -> Dict[str, Any]:
    """Bloque versionado de flujo para un simbolo en un instante.

    Retorna cobertura NINGUNA (no hay datos) cuando el simbolo no tiene
    eventos ingeridos: nunca rellena con ceros ni con historial de OHLC.
    """
    sym = str(symbol or "").strip().upper()
    series = engine._series.get(sym)  # type: ignore[attr-defined]
    if series is None or series.trades_total == 0:
        return {
            "contract_version": MARKET_FLOW_CONTRACT_VERSION,
            "availability": FLOW_AVAILABILITY,
            "coverage": NO_COVERAGE_BEFORE_FIRST_EVENT,
            "identity": {"symbol": sym, "venue": "binance",
                         "market_type": "usd_m_futures",
                         "source": "aggTrade_local_transport"},
            "as_of_ms": int(as_of_ms),
            "freshness_ms": None,
            "live": False,
            "trades_total": 0,
            "horizons": {h: _empty_horizon(h, int(as_of_ms))
                         for h in FLOW_HORIZON_ORDER},
            "baselines": {},
            "acceleration": {},
            "notes": ["Sin eventos de captura para este simbolo; "
                      "sin cobertura antes del inicio de captura."],
        }

    snapshot = series.snapshot(sym, int(as_of_ms), subscribed=True)
    horizons: Dict[str, Any] = {}
    for h in FLOW_HORIZON_ORDER:
        hf = snapshot["horizons"][h]
        horizons[h] = {
            "trades": hf["trades"],
            "base_volume": hf["base_volume"],
            "notional": hf["notional"],
            "buy_base": hf["buy_base"],
            "sell_base": hf["sell_base"],
            "buy_notional": hf["buy_notional"],
            "sell_notional": hf["sell_notional"],
            "signed_delta": hf["signed_delta"],  # cotizada: buy - sell
            "delta_ratio": hf["delta_ratio"],    # [-1,+1], + = net agresor BUY
            "buy_pct": hf["buy_pct"],
            "sell_pct": hf["sell_pct"],
            "trade_rate": hf["trade_rate"],
            "notional_rate": hf["notional_rate"],
            "warmup_complete": hf["warmup_complete"],
            "window_ms": hf["window_ms"],
            "as_of_ms": hf["as_of_ms"],
        }
    baselines = {label: snapshot["baselines"][label]
                 for label in snapshot["baselines"]}
    return {
        "contract_version": MARKET_FLOW_CONTRACT_VERSION,
        "availability": FLOW_AVAILABILITY,
        "coverage": "LIVE",
        "identity": {"symbol": sym, "venue": "binance",
                     "market_type": "usd_m_futures",
                     "source": "aggTrade_local_transport"},
        "as_of_ms": int(as_of_ms),
        "freshness_ms": snapshot["freshness_ms"],
        "live": snapshot["live"],
        "trades_total": snapshot["trades_total"],
        "rpi_base_total": snapshot["rpi_base_total"],
        "rpi_notional_total": snapshot["rpi_notional_total"],
        "rpi_trades": snapshot["rpi_trades"],
        "dropped_late": snapshot["dropped_late"],
        "dropped_invalid": snapshot["dropped_invalid"],
        "horizons": horizons,
        "baselines": baselines,
        "acceleration": snapshot["acceleration"],
        "notes": ["Delta positivo no es senal alcista automatica: "
                  "solo describe el saldo de volumen agresor en ventana."],
    }


def _empty_horizon(horizon: str, as_of_ms: int) -> Dict[str, Any]:
    from .flow import FLOW_HORIZONS_MS
    return {
        "trades": 0, "base_volume": 0.0, "notional": 0.0,
        "buy_base": 0.0, "sell_base": 0.0,
        "buy_notional": None, "sell_notional": None,
        "signed_delta": None, "delta_ratio": None,
        "buy_pct": None, "sell_pct": None,
        "trade_rate": 0.0, "notional_rate": 0.0,
        "warmup_complete": False,
        "window_ms": FLOW_HORIZONS_MS[horizon],
        "as_of_ms": as_of_ms,
        "coverage": NO_COVERAGE_BEFORE_FIRST_EVENT,
    }


def ingest_aggtrade(engine: FlowEngine, symbol: str, event_time_ms: int,
                    price: float, quantity: float,
                    buyer_is_maker: bool,
                    normal_quantity: Optional[float] = None) -> bool:
    """Ingest wrapper que re-exporta FlowEngine.ingest para el BFF.

    Devuelve True cuando el evento fue aceptado (flujo actualizado),
    False cuando fue rechazado (invalido, tardio, simbolo no permitido).
    """
    return engine.ingest(symbol, event_time_ms, price, quantity,
                         buyer_is_maker, normal_quantity)
