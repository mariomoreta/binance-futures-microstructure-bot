"""P1-05 velocity / acceleration / cross-sectional ranking.

Built ONLY on the P1-04 return engine (mark-price 10s buckets). No second
price-history implementation exists.

Definitions (deterministic, timestamp-aware, no lookahead):
- R_h(t): h-horizon log return evaluated with samples at-or-before t.
- velocity(h; b)(t) = [R_h(t) - R_h(t-b)] / b_seconds. Default b = h.
  A flat high return has ~zero velocity; velocity is NOT a renamed return.
- acceleration(h; b; c)(t) = [v(t) - v(t-c)] / c_seconds with v evaluated at
  the two as-of offsets (actual sample times embedded, no grid assumed).
  Default b = c = h (1m acceleration needs ~3min of span + tolerances).
- Unavailable until enough history exists: None (never fabricated zero).
- Ranking: per metric, descending value with (value desc, symbol asc)
  tie-breaks. rank_change = prev_rank - rank (positive = climbed);
  rank_velocity = change / elapsed_s; rank_acceleration = Δrank_velocity /
  elapsed_s. All need ≥2 evaluations; acceleration needs ≥3.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from .returns import SymbolPriceSeries, anchor_tolerance_ms

VELOCITY_HORIZONS = ("1m", "3m", "5m", "15m")
RANK_METRICS = ("velocity_1m", "velocity_5m", "acceleration_1m")


def return_at(series: SymbolPriceSeries, as_of_ms: float,
              horizon_ms: int) -> Optional[Dict[str, Any]]:
    """Single-horizon log return with full provenance (shared with engine)."""
    current = None
    for bucket_start, price in series.buckets():
        if bucket_start <= as_of_ms:
            current = (bucket_start, price)
        else:
            break
    if current is None:
        return None
    target = current[0] - horizon_ms
    anchor = series.lookup_at_or_before(target, anchor_tolerance_ms(horizon_ms))
    if anchor is None or anchor[1] <= 0 or current[1] <= 0:
        return None
    return {"value": math.log(current[1] / anchor[1]),
            "current_ms": current[0], "current_price": current[1],
            "anchor_ms": anchor[0]}


def velocity_at(series: SymbolPriceSeries, as_of_ms: float, horizon_ms: int,
                basis_ms: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Change in the h-return over the basis window, per second."""
    basis_ms = horizon_ms if basis_ms is None else basis_ms
    now = return_at(series, as_of_ms, horizon_ms)
    prev = return_at(series, as_of_ms - basis_ms, horizon_ms)
    if now is None or prev is None or basis_ms <= 0:
        return None
    return {"value": (now["value"] - prev["value"]) / (basis_ms / 1000.0),
            "horizon_ms": horizon_ms, "basis_ms": basis_ms,
            "t_now_ms": now["current_ms"], "t_prev_ms": prev["current_ms"],
            "r_now": now["value"], "r_prev": prev["value"]}


def acceleration_at(series: SymbolPriceSeries, as_of_ms: float,
                    horizon_ms: int, basis_ms: Optional[int] = None,
                    span_ms: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Timestamp-aware change in velocity over the span window, per second."""
    basis_ms = horizon_ms if basis_ms is None else basis_ms
    span_ms = horizon_ms if span_ms is None else span_ms
    now = velocity_at(series, as_of_ms, horizon_ms, basis_ms)
    prev = velocity_at(series, as_of_ms - span_ms, horizon_ms, basis_ms)
    if now is None or prev is None or span_ms <= 0:
        return None
    return {"value": (now["value"] - prev["value"]) / (span_ms / 1000.0),
            "horizon_ms": horizon_ms, "basis_ms": basis_ms,
            "span_ms": span_ms,
            "v_now": now["value"], "v_prev": prev["value"]}


class RankTracker:
    """Cross-sectional ranks over live symbols with change dynamics.

    Evaluations arrive irregularly (summary ticks); all deltas use actual
    elapsed seconds. Bounded memory (recent evaluations deque).
    """

    def __init__(self, metrics: tuple = RANK_METRICS, history: int = 200) -> None:
        self.metrics = tuple(metrics)
        self._evals: deque = deque(maxlen=history)  # (as_of_ms, {metric: {sym: value}})

    def evaluate(self, as_of_ms: float,
                 rows: List[Tuple[str, Dict[str, Optional[float]]]]
                 ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Rank one evaluation across symbols. Returns
        {metric: {symbol: {rank, change, velocity, acceleration}}}."""
        values: Dict[str, Dict[str, float]] = {m: {} for m in self.metrics}
        for symbol, metrics in rows:
            for metric in self.metrics:
                value = metrics.get(metric)
                if value is not None and math.isfinite(value):
                    values[metric][symbol.upper()] = value
        self._evals.append((as_of_ms, values))
        return self.snapshot()

    def _ranked(self, values: Dict[str, float]) -> Dict[str, int]:
        ordered = sorted(values, key=lambda s: (-values[s], s))
        return {symbol: rank + 1 for rank, symbol in enumerate(ordered)}

    def snapshot(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Current ranks + change dynamics from stored evaluation history."""
        if not self._evals:
            return {}
        _, latest = self._evals[-1]
        out: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for metric in self.metrics:
            ranks = self._ranked(latest.get(metric, {}))
            metric_out: Dict[str, Dict[str, Any]] = {}
            for symbol, rank in ranks.items():
                change = self._change(metric, symbol, rank)
                velocity = self._rate(metric, symbol, rank, depth=1)
                acceleration = self._rate(metric, symbol, rank, depth=2)
                metric_out[symbol] = {
                    "rank": rank, "change": change,
                    "velocity": velocity, "acceleration": acceleration,
                }
            out[metric] = metric_out
        return out

    def _rank_at(self, index: int, metric: str, symbol: str) -> Optional[int]:
        _, values = self._evals[index]
        ranks = self._ranked(values.get(metric, {}))
        return ranks.get(symbol)

    def _change(self, metric: str, symbol: str, rank: int) -> Optional[int]:
        if len(self._evals) < 2:
            return None
        prev = self._rank_at(-2, metric, symbol)
        return (prev - rank) if prev is not None else None

    def _rate(self, metric: str, symbol: str, rank: int,
              depth: int) -> Optional[float]:
        """Rank velocity (depth=1, needs 2 evals) or acceleration (depth=2)."""
        if len(self._evals) < depth + 1:
            return None
        now_ms = self._evals[-1][0]
        then_ms = self._evals[-(depth + 1)][0]
        dt_s = (now_ms - then_ms) / 1000.0
        if dt_s <= 0:
            return None
        if depth == 1:
            prev = self._rank_at(-2, metric, symbol)
            if prev is None:
                return None
            return (prev - rank) / dt_s
        mid = self._rank_at(-2, metric, symbol)
        old = self._rank_at(-3, metric, symbol)
        if mid is None or old is None:
            return None
        mid_ms = self._evals[-2][0]
        dt1 = (now_ms - mid_ms) / 1000.0
        dt2 = (mid_ms - then_ms) / 1000.0
        if dt1 <= 0 or dt2 <= 0:
            return None
        v_now = (mid - rank) / dt1
        v_prev = (old - mid) / dt2
        return (v_now - v_prev) / dt_s

    def evaluation_count(self) -> int:
        return len(self._evals)
