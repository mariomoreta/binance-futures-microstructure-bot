from __future__ import annotations

import math
from collections import deque


class RunningDistribution:
    """Estadisticas acumuladas con una ventana acotada para cuantiles.

    count/min/max/mean cubren toda la corrida. Los cuantiles usan las muestras
    mas recientes para mantener memoria acotada durante soaks prolongados.
    """

    def __init__(self, max_samples: int = 20_000) -> None:
        if max_samples <= 0:
            raise ValueError("max_samples debe ser mayor que cero")
        self._samples: deque[float] = deque(maxlen=max_samples)
        self.count = 0
        self.non_finite_count = 0
        self._sum = 0.0
        self._min: float | None = None
        self._max: float | None = None

    def add(self, value: float) -> None:
        number = float(value)
        if not math.isfinite(number):
            self.non_finite_count += 1
            return
        self.count += 1
        self._sum += number
        self._min = number if self._min is None else min(self._min, number)
        self._max = number if self._max is None else max(self._max, number)
        self._samples.append(number)

    def snapshot(self) -> dict[str, float | int | str | None]:
        ordered = sorted(self._samples)
        return {
            "count": self.count,
            "retainedCount": len(ordered),
            "retention": f"latest_{self._samples.maxlen}",
            "nonFiniteCount": self.non_finite_count,
            "min": self._rounded(self._min),
            "p50": self._quantile(ordered, 0.50),
            "p90": self._quantile(ordered, 0.90),
            "p95": self._quantile(ordered, 0.95),
            "p99": self._quantile(ordered, 0.99),
            "max": self._rounded(self._max),
            "mean": self._rounded(self._sum / self.count) if self.count else None,
        }

    @staticmethod
    def _quantile(ordered: list[float], probability: float) -> float | None:
        if not ordered:
            return None
        index = max(0, math.ceil(probability * len(ordered)) - 1)
        return RunningDistribution._rounded(ordered[index])

    @staticmethod
    def _rounded(value: float | None) -> float | None:
        return None if value is None else round(value, 6)


class NearMissCounter:
    LEVELS = (0.50, 0.75, 0.90, 1.00)

    def __init__(self) -> None:
        self.observations = 0
        self.maximum_ratio: float | None = None
        self._counts = {level: 0 for level in self.LEVELS}

    def observe(self, ratio: float) -> None:
        value = float(ratio)
        self.observations += 1
        self.maximum_ratio = value if self.maximum_ratio is None else max(self.maximum_ratio, value)
        for level in self.LEVELS:
            if value >= level:
                self._counts[level] += 1

    def snapshot(self) -> dict[str, float | int | dict[str, int] | None]:
        return {
            "observations": self.observations,
            "maxRatio": None if self.maximum_ratio is None else round(self.maximum_ratio, 6),
            "atOrAbove": {
                "50pct": self._counts[0.50],
                "75pct": self._counts[0.75],
                "90pct": self._counts[0.90],
                "100pct": self._counts[1.00],
            },
        }

