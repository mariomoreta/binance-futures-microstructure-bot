from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import math

from .config import ProbeConfig
from .metrics import percentile, population_z_score
from .models import DetectedEvent
from .telemetry import NearMissCounter, RunningDistribution


@dataclass
class _VolumeBucket:
    start_ms: int
    notional: float = 0.0
    last_price: float = 0.0


class EventDetectors:
    def __init__(self, config: ProbeConfig) -> None:
        self.config = config
        self._liquidations: dict[str, deque[tuple[int, float]]] = defaultdict(deque)
        self._funding: dict[str, deque[float]] = {
            symbol: deque(maxlen=config.funding.history_size) for symbol in config.symbols
        }
        self._volume_history: dict[str, deque[float]] = {
            symbol: deque(maxlen=config.volume.history_buckets) for symbol in config.symbols
        }
        self._volume_current: dict[str, _VolumeBucket] = {}
        max_samples = config.telemetry_max_samples
        self._detections: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        self._liquidation_received: defaultdict[str, int] = defaultdict(int)
        self._liquidation_individual_near = {
            symbol: NearMissCounter() for symbol in config.symbols
        }
        self._liquidation_window_near = {
            symbol: NearMissCounter() for symbol in config.symbols
        }
        self._volume_trades_received: defaultdict[str, int] = defaultdict(int)
        self._volume_completed_buckets: defaultdict[str, int] = defaultdict(int)
        self._volume_evaluated_buckets: defaultdict[str, int] = defaultdict(int)
        self._volume_threshold_crossings: defaultdict[str, int] = defaultdict(int)
        self._volume_z_scores = {
            symbol: RunningDistribution(max_samples) for symbol in config.symbols
        }
        self._volume_near = {symbol: NearMissCounter() for symbol in config.symbols}
        self._funding_received: defaultdict[str, int] = defaultdict(int)
        self._funding_eligible: defaultdict[str, int] = defaultdict(int)
        self._funding_crossings: defaultdict[str, int] = defaultdict(int)
        self._funding_value_changes: defaultdict[str, int] = defaultdict(int)
        self._funding_distinct: dict[str, set[float]] = {
            symbol: set() for symbol in config.symbols
        }
        self._funding_last_rate: dict[str, float] = {}
        self._funding_current_percentile: dict[str, float | None] = {
            symbol: None for symbol in config.symbols
        }
        self._funding_min_rate: dict[str, float] = {}
        self._funding_max_rate: dict[str, float] = {}

    def liquidation(
        self, *, timestamp_ms: int, symbol: str, price: float, quantity: float, side: str
    ) -> list[DetectedEvent]:
        if symbol not in self.config.symbols:
            return []
        self._liquidation_received[symbol] += 1
        notional = price * quantity
        recent = self._liquidations[symbol]
        recent.append((timestamp_ms, notional))
        cutoff = timestamp_ms - self.config.liquidation.window_seconds * 1000
        while recent and recent[0][0] < cutoff:
            recent.popleft()
        window_notional = sum(item[1] for item in recent)
        self._liquidation_individual_near[symbol].observe(
            notional / self.config.liquidation.individual_notional_usdt[symbol]
        )
        self._liquidation_window_near[symbol].observe(
            window_notional / self.config.liquidation.window_notional_usdt[symbol]
        )

        events: list[DetectedEvent] = []
        if notional >= self.config.liquidation.individual_notional_usdt[symbol]:
            events.append(
                DetectedEvent(
                    timestamp_ms=timestamp_ms,
                    symbol=symbol,
                    event_type="large_liquidation_individual",
                    magnitude=notional,
                    price_snapshot=price,
                    details={"side": side, "notional_usdt": notional},
                )
            )
        if window_notional >= self.config.liquidation.window_notional_usdt[symbol]:
            events.append(
                DetectedEvent(
                    timestamp_ms=timestamp_ms,
                    symbol=symbol,
                    event_type="large_liquidation_window",
                    magnitude=window_notional,
                    price_snapshot=price,
                    details={
                        "side": side,
                        "window_seconds": self.config.liquidation.window_seconds,
                        "notional_usdt": window_notional,
                    },
                )
            )
            recent.clear()
        for event in events:
            detector = (
                "liquidationIndividual"
                if event.event_type == "large_liquidation_individual"
                else "liquidationWindow"
            )
            self._detections[(detector, symbol, side)] += 1
        return events

    def funding_rate(
        self, *, timestamp_ms: int, symbol: str, price: float, rate: float
    ) -> list[DetectedEvent]:
        if symbol not in self.config.symbols:
            return []
        self._funding_received[symbol] += 1
        self._funding_distinct[symbol].add(rate)
        if self._funding_last_rate.get(symbol) != rate:
            self._funding_value_changes[symbol] += 1
            self._funding_last_rate[symbol] = rate
        self._funding_min_rate[symbol] = min(rate, self._funding_min_rate.get(symbol, rate))
        self._funding_max_rate[symbol] = max(rate, self._funding_max_rate.get(symbol, rate))
        history = self._funding[symbol]
        event: DetectedEvent | None = None
        if len(history) >= self.config.funding.minimum_samples:
            self._funding_eligible[symbol] += 1
            low = percentile(tuple(history), self.config.funding.lower_percentile)
            high = percentile(tuple(history), self.config.funding.upper_percentile)
            self._funding_current_percentile[symbol] = (
                sum(1 for sample in history if sample <= rate) / len(history)
            )
            if rate < low or rate > high:
                event = DetectedEvent(
                    timestamp_ms=timestamp_ms,
                    symbol=symbol,
                    event_type="extreme_funding_rate",
                    magnitude=rate,
                    price_snapshot=price,
                    details={
                        "funding_rate": rate,
                        "lower_percentile_value": low,
                        "upper_percentile_value": high,
                        "history_samples": len(history),
                    },
                )
                category = "LOW" if rate < low else "HIGH"
                self._funding_crossings[symbol] += 1
                self._detections[("funding", symbol, category)] += 1
        history.append(rate)
        return [event] if event else []

    def aggregate_trade(
        self, *, timestamp_ms: int, symbol: str, price: float, quantity: float
    ) -> list[DetectedEvent]:
        if symbol not in self.config.symbols:
            return []
        self._volume_trades_received[symbol] += 1
        bucket_ms = self.config.volume.bucket_seconds * 1000
        start_ms = timestamp_ms - (timestamp_ms % bucket_ms)
        current = self._volume_current.get(symbol)
        if current is None:
            self._volume_current[symbol] = _VolumeBucket(
                start_ms=start_ms, notional=price * quantity, last_price=price
            )
            return []
        if start_ms == current.start_ms:
            current.notional += price * quantity
            current.last_price = price
            return []
        if start_ms < current.start_ms:
            return []

        history = self._volume_history[symbol]
        self._volume_completed_buckets[symbol] += 1
        event: DetectedEvent | None = None
        if len(history) >= self.config.volume.minimum_buckets:
            self._volume_evaluated_buckets[symbol] += 1
            z_score = population_z_score(current.notional, tuple(history))
            if z_score is not None:
                self._volume_z_scores[symbol].add(z_score)
                ratio = (
                    z_score / self.config.volume.z_score_threshold
                    if math.isfinite(z_score)
                    else 1.0
                )
                self._volume_near[symbol].observe(ratio)
            if z_score is not None and z_score >= self.config.volume.z_score_threshold:
                event = DetectedEvent(
                    timestamp_ms=current.start_ms + bucket_ms,
                    symbol=symbol,
                    event_type="volume_spike",
                    magnitude=current.notional,
                    price_snapshot=current.last_price,
                    details={
                        "bucket_seconds": self.config.volume.bucket_seconds,
                        "notional_usdt": current.notional,
                        "z_score": z_score,
                        "history_buckets": len(history),
                    },
                )
                self._volume_threshold_crossings[symbol] += 1
                self._detections[("volumeSpike", symbol, "ABOVE_THRESHOLD")] += 1
        history.append(current.notional)
        self._volume_current[symbol] = _VolumeBucket(
            start_ms=start_ms, notional=price * quantity, last_price=price
        )
        return [event] if event else []

    def telemetry_snapshot(self) -> dict[str, object]:
        categories = {
            "liquidationIndividual": ("BUY", "SELL"),
            "liquidationWindow": ("BUY", "SELL"),
            "funding": ("LOW", "HIGH"),
            "volumeSpike": ("ABOVE_THRESHOLD",),
        }
        detections: dict[str, dict[str, dict[str, int]]] = {
            detector: {
                symbol: {
                    **{
                        category: self._detections[(detector, symbol, category)]
                        for category in detector_categories
                    },
                    "total": sum(
                        self._detections[(detector, symbol, category)]
                        for category in detector_categories
                    ),
                }
                for symbol in self.config.symbols
            }
            for detector, detector_categories in categories.items()
        }
        for (detector, symbol, category), count in sorted(self._detections.items()):
            detections.setdefault(detector, {}).setdefault(symbol, {})[category] = count

        liquidation = {}
        volume = {}
        funding = {}
        for symbol in self.config.symbols:
            liquidation[symbol] = {
                "observationsReceived": self._liquidation_received[symbol],
                "observationsEvaluable": self._liquidation_received[symbol],
                "individual": self._liquidation_individual_near[symbol].snapshot(),
                "window": self._liquidation_window_near[symbol].snapshot(),
            }
            volume[symbol] = {
                "tradesReceived": self._volume_trades_received[symbol],
                "completedBuckets": self._volume_completed_buckets[symbol],
                "warmupBuckets": min(
                    len(self._volume_history[symbol]), self.config.volume.minimum_buckets
                ),
                "warmupRequired": self.config.volume.minimum_buckets,
                "warmupComplete": (
                    len(self._volume_history[symbol]) >= self.config.volume.minimum_buckets
                ),
                "evaluatedBuckets": self._volume_evaluated_buckets[symbol],
                "thresholdCrossings": self._volume_threshold_crossings[symbol],
                "zScore": self._volume_z_scores[symbol].snapshot(),
                "nearMiss": self._volume_near[symbol].snapshot(),
            }
            history_size = len(self._funding[symbol])
            funding[symbol] = {
                "samplesReceived": self._funding_received[symbol],
                "samplesEligible": self._funding_eligible[symbol],
                "warmupProgress": min(history_size, self.config.funding.minimum_samples),
                "warmupRequired": self.config.funding.minimum_samples,
                "warmupComplete": history_size >= self.config.funding.minimum_samples,
                "currentPercentile": (
                    None
                    if self._funding_current_percentile[symbol] is None
                    else round(self._funding_current_percentile[symbol], 6)
                ),
                "crossings": self._funding_crossings[symbol],
                "distinctRates": len(self._funding_distinct[symbol]),
                "valueChanges": self._funding_value_changes[symbol],
                "minimumRate": self._funding_min_rate.get(symbol),
                "maximumRate": self._funding_max_rate.get(symbol),
                "independenceNote": "repeated_stream_samples_are_not_independent",
            }
        return {
            "detections": detections,
            "liquidation": liquidation,
            "volume": volume,
            "funding": funding,
        }
