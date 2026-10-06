from __future__ import annotations

import math
from collections.abc import Sequence


def basis_points_change(initial: float, final: float) -> float:
    """Retorno simple expresado en basis points; 1% equivale a 100 bps."""
    if initial <= 0:
        raise ValueError("initial debe ser mayor que cero")
    return ((final - initial) / initial) * 10_000.0


def spread_bps(bid: float, ask: float) -> float:
    if bid <= 0 or ask <= 0 or ask < bid:
        raise ValueError("bid/ask invalidos")
    midpoint = (bid + ask) / 2.0
    return ((ask - bid) / midpoint) * 10_000.0


def order_book_imbalance(
    bids: Sequence[Sequence[str | float]], asks: Sequence[Sequence[str | float]]
) -> float:
    bid_quantity = sum(float(level[1]) for level in bids)
    ask_quantity = sum(float(level[1]) for level in asks)
    total = bid_quantity + ask_quantity
    if total <= 0:
        raise ValueError("El book no contiene cantidad positiva")
    return (bid_quantity - ask_quantity) / total


def percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requiere valores")
    if not 0 <= probability <= 1:
        raise ValueError("probability debe estar entre 0 y 1")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def population_z_score(value: float, history: Sequence[float]) -> float | None:
    if not history:
        return None
    mean = sum(history) / len(history)
    variance = sum((sample - mean) ** 2 for sample in history) / len(history)
    if variance == 0:
        return math.inf if value > mean else 0.0
    return (value - mean) / math.sqrt(variance)

