"""Indicadores compartidos sobre velas cerradas (``market-indicators/v1``).

Primera integracion vertical del bloque "indicadores compartidos": el backend
es la unica autoridad de calculo y publica la MISMA salida versionada al
grafico de ``/market-lab`` y al futuro evaluador. El navegador no recalcula
nada: solo mira valores y reasons ya emitidos.

Relacion con los motores de Fase 1 (`returns`, `momentum`, `flow`, `book`,
`open_interest`, `market_structure`): esos viven de feeds de evento
(mark price WS, aggTrades WS, libro de ordenes, openInterest por REST) y NO
son re-derivables de OHLC. Este modulo no los reemplaza ni reimplementa; solo
calcula el subconjunto que las velas OHLCV cerradas auditadas en
``market_cache`` permiten sostener.

Por disenio aqui NUNCA se derivan flujo comprador/vendedor, spread,
profundidad ni open interest a partir de OHLC: quedan en la lista `declined`
con su motivo, no como cero ni como valor aproximado.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Sequence

MARKET_INDICATORS_CONTRACT_VERSION = "market-indicators/v1"
AVAILABILITY = "CLOSED_CANDLES_ONLY"

#: Ventanas elegidas para la primera integracion (en velas CERRADAS).
VELOCITY_WINDOW_CANDLES = 5
REL_VOLUME_BASELINE_CANDLES = 10
VWAP_WINDOW_CANDLES = 10

SUPPORTED = (
    "log_return_bps",
    "velocity_bps_5",
    "rel_volume_10",
    "vwap_dev_bps_10",
)

DECLINED = (
    {"name": "flow_delta", "reason": "AGGTRADES_SOURCE_REQUIRED"},
    {"name": "spread_bps", "reason": "ORDER_BOOK_SOURCE_REQUIRED"},
    {"name": "depth", "reason": "ORDER_BOOK_SOURCE_REQUIRED"},
    {"name": "open_interest", "reason": "OI_REST_POLL_REQUIRED"},
    {"name": "btc_context", "reason": "SECOND_SYMBOL_KLINES_REQUIRED"},
)

_DEFINITIONS = (
    {
        "name": "log_return_bps",
        "formula": "10000 * ln(close_t / close_(t-1))",
        "unit": "bps",
        "window_candles": 1,
        "requires": "previous grid candle closed and present",
    },
    {
        "name": "velocity_bps_5",
        "formula": "10000 * ln(close_t / close_(t-4))",
        "unit": "bps",
        "window_candles": VELOCITY_WINDOW_CANDLES,
        "requires": "contiguous run of 5 closed grid candles ending at t",
    },
    {
        "name": "rel_volume_10",
        "formula": "base_volume_t / mean(base_volume t-9..t-1)",
        "unit": "ratio",
        "window_candles": REL_VOLUME_BASELINE_CANDLES,
        "requires": ("current base_volume and contiguous baseline of 10"
                     " closed candles with base_volume"),
    },
    {
        "name": "vwap_typical_10",
        "formula": "sum(((h+l+c)/3 * v)) / sum(v) over t-9..t",
        "unit": "price (quote)",
        "window_candles": VWAP_WINDOW_CANDLES,
        "requires": ("contiguous run of 10 closed candles with base_volume;"
                     " approximation weighted by typical price, NOT the"
                     " traded VWAP of market_structure.vwap_record"),
    },
    {
        "name": "vwap_dev_bps_10",
        "formula": "10000 * (close_t / vwap_typical_10 - 1)",
        "unit": "bps",
        "window_candles": VWAP_WINDOW_CANDLES,
        "requires": "vwap_typical_10 of the same candle",
    },
)


def _num(value: Any) -> Optional[float]:
    """Convierte a float finito; None si falta o no es numerico seguro.

    Nunca inventa 0: la ausencia es UNKNOWN.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _is_closed(open_time_ms: int, interval_ms: int, now_ms: int) -> bool:
    """Candidata confirmada: una vela cierra a ``open_time + interval_ms``."""
    return open_time_ms + interval_ms <= int(now_ms)


def _round(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 6)


def _window_reason(needed_times: Sequence[int], grid: Dict[int, Any],
                   first_open: Optional[int]) -> str:
    """Motivo de UNKNOWN para una ventana de velas contiguas.

    Regla declarada: si falta una vela DENTRO del rango del payload es un
    hueco real (``GAP_IN_WINDOW``); si lo que falta queda antes del inicio
    del propio rango es calentamiento (``INSUFICIENT_CANDLES``). Nunca se
    devuelve 0 en ninguno de los dos casos.
    """
    missing = [t for t in needed_times if t not in grid]
    if not missing:
        return "OK"
    if first_open is None:
        return "INSUFICIENT_CANDLES"
    if any(t >= first_open for t in missing):
        return "GAP_IN_WINDOW"
    return "INSUFICIENT_CANDLES"


def compute_kline_indicators(
    bars: Sequence[Dict[str, Any]],
    interval_ms: int,
    now_ms: int,
    symbol: str = "",
    interval: str = "",
    source: str = "",
) -> Dict[str, Any]:
    """Bloque versionado de indicadores para el rango printable del payload.

    Criterios:
      * solo velas cerradas; la vela en formacion queda excluida (sin valor
        provisional basado en close incompleto en esta integracion);
      * huesos: si la vela necesaria no esta en el rango del payload el
        resultado es UNKNOWN con reason, nunca 0;
      * sin lookahead: el valor de la vela ``t`` solo lee velas ``<= t``;
      * calculado sobre el PROPIO rango del payload (``computed_over``), por
        lo que las primeras velas del bloque declaran warmup como UNKNOWN
        aunque el cache tenga velas anteriores fuera de la ventana: es un
        limite declarado, no un dato inventado.
    """
    now = int(now_ms)
    step = int(interval_ms)
    grid: Dict[int, Dict[str, Any]] = {}
    for bar in bars or []:
        if not isinstance(bar, dict):
            continue
        open_time = bar.get("open_time")
        try:
            open_time = int(open_time)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if not _is_closed(open_time, step, now):
            continue
        grid[open_time] = bar
    open_times = sorted(grid)
    first_open = open_times[0] if open_times else None

    rows: List[Dict[str, Any]] = []
    for open_time in open_times:
        values: Dict[str, float] = {}
        unknown: Dict[str, str] = {}

        bar = grid[open_time]
        close = _num(bar.get("close"))

        # --- log_return_bps -------------------------------------------------
        prev_time = open_time - step
        prev_bar = grid.get(prev_time)
        prev_close = _num(prev_bar.get("close")) if prev_bar else None
        if prev_bar is None:
            unknown["log_return_bps"] = "NO_PREVIOUS_CANDLE"
        elif close is None or prev_close is None:
            unknown["log_return_bps"] = "MISSING_CLOSE"
        else:
            if prev_close > 0 and close > 0:
                values["log_return_bps"] = _round(
                    10000.0 * math.log(close / prev_close))
            else:
                unknown["log_return_bps"] = "INVALID_PRICE"
        run_missing = [open_time - i * step
                       for i in range(1, VELOCITY_WINDOW_CANDLES)]
        end_time = open_time - (VELOCITY_WINDOW_CANDLES - 1) * step
        reason_v = _window_reason(run_missing, grid, first_open)
        end_bar = grid.get(end_time)
        if reason_v != "OK" or end_bar is None:
            unknown["velocity_bps_5"] = reason_v if reason_v != "OK" \
                else "INSUFICIENT_CANDLES"
        else:
            end_close = _num(end_bar.get("close"))
            if close is None or end_close is None:
                unknown["velocity_bps_5"] = "MISSING_CLOSE"
            else:
                if close > 0 and end_close > 0:
                    values["velocity_bps_5"] = _round(
                        10000.0 * math.log(close / end_close))
                else:
                    unknown["velocity_bps_5"] = "INVALID_PRICE"
        # --------------------------------------------------------------------
        # Baseline de volumen y VWAP compartida: n velas cerradas contiguas
        # ANTERIORES a `t` (baseline) y la propia `t` para VWAP.
        baseline_missing = [open_time - i * step
                            for i in range(1, REL_VOLUME_BASELINE_CANDLES + 1)]
        base_volume = _num(bar.get("base_volume"))
        reason_r = _window_reason(baseline_missing, grid, first_open)
        if reason_r != "OK":
            unknown["rel_volume_10"] = reason_r
        elif base_volume is None:
            unknown["rel_volume_10"] = "MISSING_VOLUME"
        else:
            baseline = []
            for i in range(1, REL_VOLUME_BASELINE_CANDLES + 1):
                volume = _num((grid[open_time - i * step] or {}).get(
                    "base_volume"))
                if volume is None:
                    unknown["rel_volume_10"] = "MISSING_BASELINE_VOLUME"
                    baseline = []
                    break
                baseline.append(volume)
            if baseline:
                mean = sum(baseline) / len(baseline)
                if mean > 0:
                    values["rel_volume_10"] = _round(base_volume / mean)
                else:
                    unknown["rel_volume_10"] = "INVALID_BASELINE"

        window_missing = [open_time - i * step
                          for i in range(0, VWAP_WINDOW_CANDLES)]
        reason_w = _window_reason(window_missing, grid, first_open)
        if reason_w != "OK":
            unknown["vwap_typical_10"] = reason_w
            unknown["vwap_dev_bps_10"] = reason_w
        else:
            sampling: List[tuple[float, float]] = []
            failed_reason: Optional[str] = None
            for i in range(0, VWAP_WINDOW_CANDLES):
                wbar = grid[open_time - i * step]
                high = _num(wbar.get("high"))
                low = _num(wbar.get("low"))
                w_close = _num(wbar.get("close"))
                volume = _num(wbar.get("base_volume"))
                if high is None or low is None or w_close is None:
                    failed_reason = "MISSING_OHLC"
                    break
                if volume is None:
                    failed_reason = "MISSING_VOLUME"
                    break
                if volume <= 0 or min(high, low, w_close) <= 0:
                    failed_reason = "INVALID_WINDOW_DATA"
                    break
                typical = (high + low + w_close) / 3.0
                sampling.append((typical, volume))
            if failed_reason is None:
                total_q = sum(q for _, q in sampling)
                total_typical_q = sum(r * q for r, q in sampling)
                if total_q > 0:
                    vwap = total_typical_q / total_q
                    values["vwap_typical_10"] = _round(vwap)
                    if close is None:
                        unknown["vwap_dev_bps_10"] = "MISSING_CLOSE"
                    else:
                        values["vwap_dev_bps_10"] = _round(
                            10000.0 * (close / vwap - 1))
                else:
                    unknown["vwap_typical_10"] = "INVALID_WINDOW_DATA"
                    unknown["vwap_dev_bps_10"] = "INVALID_WINDOW_DATA"
            else:
                unknown["vwap_typical_10"] = failed_reason
                unknown["vwap_dev_bps_10"] = failed_reason

        rows.append({
            "open_time_ms": open_time,
            "available_at_ms": open_time + step,
            "values": values,
            "unknown": unknown,
        })

    return {
        "contract_version": MARKET_INDICATORS_CONTRACT_VERSION,
        "availability": AVAILABILITY,
        "provisional_policy": {"included": False,
                               "reason": "PROVISIONAL_EXCLUDED"},
        "computed_over": "payload_window",
        "identity": {"symbol": symbol, "interval": interval,
                     "interval_ms": step, "source": source},
        "definitions": list(_DEFINITIONS),
        "supported": list(SUPPORTED),
        "declined": list(DECLINED),
        "series": rows,
        "generated_at_ms": int(now_ms) if int(now_ms) > 0
        else int(time.time() * 1000),
    }
