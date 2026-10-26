"""Contexto BTC compartido sobre velas cerradas (``market-btc-context/v1``).

Info contextuel para el explorador: muestra el movimiento del token junto al
de BTC usando velas CERRADAS de ambos disponibles en el mismo instante. El
bloque es INFORMATIVO: no es una senial, no es un filtro de entrada y la
diferencia de retornos NO se presenta como "alpha" ni como rentabilidad.

Ingesta de datos: ``market-indicators/v1`` declina derivar contexto BTC de
las velas del PROPIO payload; este bloque hermano declara SU fuente en
``context.sources`` (cache y/o ws_kline del canal compartido) y en
``context.acquisition`` el coste real de adquisicion (nunca una cifra
supuesta: el REST de tramos faltantes de BTC no se ejecuta aqui, y su
numero paginas depende del tramo, no es fijo).

Causalidad:
  * mismo venue (Binance USD-M) y mismo intervalo que la sesion del token;
  * alineacion por ``open_time_ms`` (rejilla comun), nunca por posicion del
    arreglo (tests anclados reordenando filas);
  * solo velas cerradas conocidas en T; la vela en formacion de BTC nunca
    aporta valores;
  * sin lookahead: la fila ``t`` solo lee velas ``<= t`` de ambas series
    (tests de perturbacion del futuro);
  * si falta BTC o su ventana tiene hueco, la fila queda ``unknown`` con
    motivo ``BTC_*``; los valores historicos validados NO se rewriten ni se
    arrastran silenciosamente (la frescura del bloque declara el estado).
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

MARKET_BTC_CONTEXT_VERSION = "market-btc-context/v1"
BTC_CONTEXT_AVAILABILITY = "CLOSED_CANDLES_ONLY"
#: Benchmark del contexto compartido. Si el token ES el benchmark no hay
#: bloque (no se compara consigo mismo) y no se crea ninguna segunda
#: suscripcion: la propia sesion del token es la serie BTC.
BTC_BENCHMARK_SYMBOL = "BTCUSDT"
#: Horizonte de la comparacion: las 5 velas cerradas del token (4 saltos),
#: alineadas con las velas cerradas de BTC en la misma rejilla.
HORIZON_CANDLES = 5

DIFF_LABEL = "diferencia de retornos"

#: Razon por la que el bloque no se emite.
NOT_EMITTED_SAME_SYMBOL = "TOKEN_IS_BTC"

RECT_SUBSCRIPTION_REASONS = ("MAX_SUBSCRIPTIONS", "MAX_CONSUMERS",
                             "INVALID_SYMBOL", "INVALID_INTERVAL")


def _num(value: Any) -> Optional[float]:
    """Flotante finito o None; nunca inventa 0 (comportamiento de V1)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _is_closed(open_time_ms: int, interval_ms: int, now_ms: int) -> bool:
    return open_time_ms + interval_ms <= int(now_ms)


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 6)


def _grid(bars: Optional[Sequence[Any]], step: int, now: int) -> Dict[int, Dict[str, Any]]:
    """Rejilla de velas CERRADAS (clave = open_time).

    No se exige alineacion absoluta al epoch: las velas pueden empezar en
    cualquier open_time; la contiguidad se valida por diferencias de ``step``
    entre open_times consecutivos (rejilla relativa), nunca por posiciones
    del arreglo.
    """
    cells: Dict[int, Dict[str, Any]] = {}
    for bar in bars or []:
        if not isinstance(bar, dict):
            continue
        try:
            open_time = int(bar.get("open_time"))
        except (TypeError, ValueError):
            continue
        if not _is_closed(open_time, step, now):
            continue
        cells[open_time] = bar
    return cells


def _btc_row_reason(needed: Sequence[int], btc: Dict[int, Dict[str, Any]],
                    btc_first: Optional[int], btc_last: Optional[int],
                    target: int) -> Tuple[Optional[str], Dict[str, str]]:
    """Motivo UNKNOWN de la fila BTC y/o motivos auxiliares de la ventana.

    Reglas declaradas:
      * ``BTC_MISSING``: no hay NINGUNA vela BTC cerrada conocida;
      * ``BTC_LAGGING``: el cierre esperado de BTC en ``target`` aun no
        llego (``target > last`` de la rejilla BTC): ni el valor ni el
        arrastre silencioso, la fila queda unknown;
      * ``BTC_GAP_IN_WINDOW``: falta una rejilla del horizonte dentro del
        rango observado de BTC;
      * ``BTC_INSUFICIENT_CANDLES``: el horizonte arranca antes del primer
        dato BTC del bloque.
    """
    if not btc:
        return "BTC_MISSING", {}
    if target > (btc_last or 0):
        return "BTC_LAGGING", {}
    missing = [t for t in needed if t not in btc]
    if not missing:
        return None, {}
    if btc_first is None or any(t < btc_first for t in missing):
        return "BTC_INSUFICIENT_CANDLES", {}
    return "BTC_GAP_IN_WINDOW", {}


def _close_of(cell: Optional[Dict[str, Any]]) -> Optional[float]:
    return _num(cell.get("close")) if cell else None


def _velocity(cell_end: Optional[Dict[str, Any]], cell_now: Optional[Dict[str, Any]],
              reason: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    close_end = _close_of(cell_end)
    close_now = _close_of(cell_now)
    if reason:
        return None, reason
    if close_end is None or close_now is None:
        return None, "MISSING_CLOSE"
    if close_end <= 0 or close_now <= 0:
        return None, "INVALID_PRICE"
    return _round(10000.0 * math.log(close_now / close_end)), None


def _token_velocity_lookup(series: Optional[Sequence[Dict[str, Any]]]) -> Dict[int, Dict[str, Any]]:
    """Velocidad del token por fila, en el formato de market-indicators/v1."""
    lookup: Dict[int, Dict[str, Any]] = {}
    for row in series or []:
        if not isinstance(row, dict):
            continue
        try:
            open_time = int(row["open_time_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        lookup[open_time] = {
            "value": row.get("values", {}).get("velocity_bps_5")
            if isinstance(row.get("values"), dict) else None,
            "unknown": row.get("unknown", {}).get("velocity_bps_5")
            if isinstance(row.get("unknown"), dict) else None,
        }
    return lookup


def _gaps(btc: Dict[int, Dict[str, Any]], token_open_times: Sequence[int],
          btc_first: int, btc_last: int) -> List[List[int]]:
    """Huecos BTC dentro del rango observado de BTC sobre la rejilla del token.

    Dejan fuera los tiempos posteriores al ultimo dato BTC (retraso):
    los declara ``freshness.lagging`` y los motivos ``BTC_LAGGING``, no
    ``gaps``.
    """
    touched = sorted(t for t in token_open_times if btc_first <= t <= btc_last)
    gaps: List[List[int]] = []
    run_start: Optional[int] = None
    run_end: Optional[int] = None
    for t in touched:
        if t in btc:
            if run_start is not None and run_end is not None:
                gaps.append([run_start, run_end])
            run_start = None
            run_end = None
        else:
            if run_start is None:
                run_start = t
            run_end = t
    if run_start is not None and run_end is not None:
        gaps.append([run_start, run_end])
    return gaps


def compute_btc_context(
    token_bars: Sequence[Dict[str, Any]],
    btc_bars: Optional[Sequence[Any]],
    interval_ms: int,
    now_ms: int,
    symbol: str = "",
    interval: str = "",
    token_source: str = "",
    token_indicators: Optional[Sequence[Dict[str, Any]]] = None,
    btc_sources: Sequence[str] = (),
    btc_subscription: Optional[Dict[str, Any]] = None,
    rest_upstream_requests: int = 0,
    btc_symbol: str = BTC_BENCHMARK_SYMBOL,
) -> Optional[Dict[str, Any]]:
    """Bloque ``market-btc-context/v1`` para la sesion del token.

    Devuelve ``None`` cuando token==BTC (no hay comparacion consigo mismo ni
    necesidad de segunda suscripcion) o cuando el token no tiene velas
    cerradas que anclar.
    """
    now = int(now_ms)
    step = int(interval_ms)
    if step <= 0:
        return None
    sym = str(symbol or "").strip().upper()
    bench = str(btc_symbol or "").strip().upper()
    if not sym or sym == bench:
        return None

    token = _grid(token_bars, step, now)
    token_times = sorted(token)
    if not token_times:
        return None
    bench_grid = _grid(btc_bars, step, now)
    bench_times = sorted(bench_grid)
    bench_first = bench_times[0] if bench_times else None
    bench_last = bench_times[-1] if bench_times else None
    token_velocity = _token_velocity_lookup(token_indicators)

    rows: List[Dict[str, Any]] = []
    for t in token_times:
        values: Dict[str, float] = {}
        unknown: Dict[str, str] = {}

        needed = [t - i * step for i in range(0, HORIZON_CANDLES)]
        reason, _ = _btc_row_reason(needed, bench_grid, bench_first,
                                    bench_last, t)
        btc_velocity, btc_reason = _velocity(
            bench_grid.get(t - (HORIZON_CANDLES - 1) * step),
            bench_grid.get(t), reason)
        if btc_velocity is not None:
            values["ret_btc_bps_5"] = btc_velocity
        elif btc_reason is not None:
            unknown["ret_btc_bps_5"] = btc_reason

        token_rate = token_velocity.get(t) or {}
        token_value = token_rate.get("value")
        token_unknown = token_rate.get("unknown")
        token_ok = isinstance(token_value, (int, float)) \
            and math.isfinite(float(token_value))
        if not token_ok:
            unknown["ret_diff_bps_5"] = str(token_unknown or "MISSING_TOKEN_ROW")
        elif btc_velocity is not None:
            values["ret_diff_bps_5"] = _round(
                float(token_value) - btc_velocity)
        elif btc_reason is not None:
            unknown["ret_diff_bps_5"] = btc_reason

        rows.append({
            "open_time_ms": t,
            "available_at_ms": t + step,
            "values": values,
            "unknown": unknown,
        })

    normalized = _normalized_series(token, bench_grid, token_times, step)
    subscription = dict(btc_subscription or {})
    return {
        "contract_version": MARKET_BTC_CONTEXT_VERSION,
        "availability": BTC_CONTEXT_AVAILABILITY,
        "identity": {"symbol": sym, "interval": interval,
                     "interval_ms": step, "source": token_source},
        "context": {
            "symbol": bench,
            "venue": "binance",
            "market_type": "usd_m_futures",
            "interval": interval,
            "interval_ms": step,
            "same_asset_as_token": False,
            "subscription": {
                "reuses_token_stream": False,
                "shared": bool(subscription.get("shared")),
                **({"live": subscription["live"]}
                   if "live" in subscription else {}),
                **({"reason": subscription["reason"]}
                   if subscription.get("reason") else {}),
            },
            "sources": sorted({str(s) for s in btc_sources if str(s)}),
            "horizon_candles": HORIZON_CANDLES,
            "timeframe": {
                "aligned_by": "open_time_ms",
                "token_window": {"first": token_times[0],
                                 "last": token_times[-1]},
                "btc_observed": {"first": bench_first, "last": bench_last},
                "expected_grid": len(rows),
                "present_grid": sum(
                    1 for r in rows if "ret_btc_bps_5" in r["values"]),
                "gaps": _gaps(bench_grid, token_times, bench_first,
                              bench_last) if bench_first is not None else [],
            },
            "freshness": _freshness(bench_times, bench_last, step, now),
            "acquisition": {
                "rest_upstream_requests": int(rest_upstream_requests or 0),
                "mode": "cache+ws" if "ws_kline" in set(
                    str(s) for s in btc_sources) else "cache",
                "note": ("REST de tramos faltantes no ejecutado; si se "
                         "autorizara, el numero de paginas depende del "
                         "tramo faltante, nunca es una cifra fija"),
            },
        },
        "definitions": BASE_DEFINITIONS,
        "supported": list(BASE_SUPPORTED),
        "labels": {"ret_diff_bps_5": DIFF_LABEL},
        "series": rows,
        "normalized": normalized,
        "generated_at_ms": now if now > 0 else int(time.time() * 1000),
    }


BASE_SUPPORTED = ("ret_btc_bps_5", "ret_diff_bps_5")

BASE_DEFINITIONS = (
    {
        "name": "ret_btc_bps_5",
        "formula": "10000 * ln(close_t^BTC / close_(t-4)^BTC)",
        "unit": "bps",
        "window_candles": HORIZON_CANDLES,
        "requires": ("velas cerradas de BTC en la MISMA rejilla del token"
                     " (t-4..t por open_time_ms); mismas 5 velas cerradas"
                     " que velocity_bps_5"),
    },
    {
        "name": "ret_diff_bps_5",
        "formula": "velocity_bps_5(token) - ret_btc_bps_5",
        "unit": "bps",
        "window_candles": HORIZON_CANDLES,
        "requires": ("velocidad del token y velocidad de BTC conocidas"
                     " en la misma fila"),
    },
)


def _freshness(bench_times: List[int], bench_last: Optional[int], step: int,
               now: int) -> Dict[str, Any]:
    last_available = (int(bench_last) + step) if bench_last is not None else None
    age = (now - last_available) if last_available is not None else None
    return {
        "btc_last_closed_open_ms": bench_last,
        "btc_last_available_at_ms": last_available,
        "age_ms": age,
        "threshold_ms": step,
        "lagging": bool(age is not None and age > step) if bench_last is not None else True,
        "note": ("BTC atras del cierre esperado en la rejilla: las filas "
                 "sin dato quedan UNKNOWN(BTC_LAGGING); no se arrastran "
                 "valores antiguos como si fueran nuevos"),
    }


def _normalized_series(token: Dict[int, Dict[str, Any]],
                       bench: Dict[int, Dict[str, Any]],
                       token_times: Sequence[int],
                       step: int) -> Optional[Dict[str, Any]]:
    """Comparacion normalizada sobre UNA base comun conocida.

    Base = primer ``open_time`` de la rejilla del token donde el close del
    token y el de BTC son conocidos, positivos y de velas cerradas. Cada
    fila: porcentaje desde esa base para ambas series, calculado AQUI
    (el navegador no recalcula). Filas sin ambos closes: se omiten (hueco
    declarado) y NO se interpolan.
    """
    base = None
    for t in token_times:
        token_close = _close_of(token.get(t))
        bench_close = _close_of(bench.get(t))
        if token_close is not None and bench_close is not None \
                and token_close > 0 and bench_close > 0:
            base = t
            break
    if base is None:
        return None
    base_row: Dict[str, Any] = {
        "open_time_ms": base,
        "token_pct": 0.0,
        "btc_pct": 0.0,
    }
    series: List[Dict[str, Any]] = [base_row]
    token_base = _close_of(token[base])
    bench_base = _close_of(bench[base])
    for t in token_times:
        if t == base or t < base:
            continue
        token_close = _close_of(token.get(t))
        bench_close = _close_of(bench.get(t))
        if token_close is None or bench_close is None \
                or token_close <= 0 or bench_close <= 0:
            continue
        series.append({
            "open_time_ms": t,
            "token_pct": round(100.0 * (token_close / token_base - 1.0), 4),
            "btc_pct": round(100.0 * (bench_close / bench_base - 1.0), 4),
        })
    return {"base_open_time_ms": base,
            "unit": "percent_from_base",
            "series": series}
