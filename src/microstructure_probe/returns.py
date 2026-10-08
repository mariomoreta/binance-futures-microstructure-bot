"""P1-04 multi-timeframe return engine (log returns on mark price).

Canonical price source: Binance USD-M **mark price** (`markPrice` stream,
field `p`). Rationale: regular ~1s cadence per symbol, event-time stamped,
lowest-rate per-symbol series — suitable for a bounded sampled store.
aggTrade stays the future flow source (P1-06); bookTicker mid stays a
microstructure source. See docs/FEATURE_MODEL.md.

Semantics (deterministic, documented, no lookahead):
- Event-time 10s buckets; last price wins per bucket (coalesced counted).
- Log return: r_tf = ln(current_price / anchor_price).
- Anchor(tf) = latest sample with E <= current_E - tf, accepted only if
  (target_E - anchor_E) <= max(60s, tf/20). Otherwise UNKNOWN (None, never 0).
- Only valid (non-skew-rejected) observations are ingested; the probe calls
  ingest solely on the post-skew-guard path.
- Out-of-order samples at/before the newest event time are dropped (counted);
  history is never rewritten.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Dict, List, Optional, Tuple

TIMEFRAMES_MS: Dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "24h": 86_400_000,
}
TIMEFRAME_ORDER = ("1m", "3m", "5m", "15m", "1h", "4h", "24h")

BUCKET_MS = 10_000
# 25.5h of 10s buckets: covers the 24h anchor + its tolerance with margin.
MAX_BUCKETS = 9180


def anchor_tolerance_ms(timeframe_ms: int) -> int:
    """Max acceptable staleness of an anchor behind its ideal target."""
    return max(60_000, timeframe_ms // 20)


class SymbolPriceSeries:
    """Bounded event-time bucketed price series for one symbol."""

    def __init__(self) -> None:
        self._buckets: deque[Tuple[int, float]] = deque()
        self._last_event_ms: Optional[int] = None
        self.updates = 0
        self.coalesced = 0
        self.dropped_late = 0
        self.dropped_invalid = 0

    def ingest(self, event_time_ms: int, price: float) -> bool:
        """Add a valid observation. False when rejected (never stored)."""
        if not math.isfinite(price) or price <= 0:
            self.dropped_invalid += 1
            return False
        if self._last_event_ms is not None and event_time_ms <= self._last_event_ms:
            # Out-of-order or duplicate: never rewrite history with older data.
            self.dropped_late += 1
            return False
        self._last_event_ms = event_time_ms
        bucket = event_time_ms - (event_time_ms % BUCKET_MS)
        if self._buckets and bucket == self._buckets[-1][0]:
            # Same 10s bucket, newer event time: last price wins.
            self._buckets[-1] = (bucket, price)
            self.coalesced += 1
        else:
            self._buckets.append((bucket, price))
        self.updates += 1
        while len(self._buckets) > MAX_BUCKETS:
            self._buckets.popleft()
        return True

    def latest(self) -> Optional[Tuple[int, float]]:
        return self._buckets[-1] if self._buckets else None

    def oldest(self) -> Optional[Tuple[int, float]]:
        return self._buckets[0] if self._buckets else None

    def lookup_at_or_before(self, target_ms: int,
                             tolerance_ms: int) -> Optional[Tuple[int, float]]:
        """Latest sample with bucket_start <= target within tolerance.

        Never returns a sample newer than target (no lookahead) and never
        fabricates a point: gaps beyond tolerance yield None.
        """
        best: Optional[Tuple[int, float]] = None
        for bucket_start, price in self._buckets:
            if bucket_start > target_ms:
                break
            best = (bucket_start, price)
        if best is None:
            return None
        if target_ms - best[0] > tolerance_ms:
            return None
        return best

    def buckets(self) -> List[Tuple[int, float]]:
        return list(self._buckets)

    def restore(self, samples: List[Tuple[int, float]]) -> None:
        """Reload persisted buckets (restart continuity). Sorted, deduped."""
        ordered = sorted(set(samples))
        self._buckets = deque(ordered[-MAX_BUCKETS:])
        self._last_event_ms = self._buckets[-1][0] if self._buckets else None


class ReturnEngine:
    """Multi-timeframe log-return features over per-symbol sampled series."""

    def __init__(self, symbols: Tuple[str, ...] = ()) -> None:
        self._allowed = {s.upper() for s in symbols} if symbols else None
        self._series: Dict[str, SymbolPriceSeries] = {}
        self.dropped_unknown = 0
        self._dirty: Dict[Tuple[str, int], float] = {}

    def ingest(self, symbol: str, event_time_ms: int, price: float) -> bool:
        """Ingest one VALID observation. Unknown symbols are refused."""
        key = symbol.upper()
        if self._allowed is not None and key not in self._allowed:
            self.dropped_unknown += 1
            return False
        series = self._series.get(key)
        if series is None:
            series = self._series[key] = SymbolPriceSeries()
        accepted = series.ingest(event_time_ms, price)
        if accepted:
            bucket = event_time_ms - (event_time_ms % BUCKET_MS)
            self._dirty[(key, bucket)] = series.latest()[1]
        return accepted

    def allow(self, symbols) -> List[str]:
        """Admit symbols to deep observation (P1-12B HOT promotions)."""
        added = []
        if self._allowed is None:
            return added
        for symbol in symbols:
            key = str(symbol).upper()
            if key not in self._allowed:
                self._allowed.add(key)
                added.append(key)
        return sorted(added)

    def forget(self, symbol: str) -> bool:
        """Drop buckets + dirty markers for a demoted symbol.

        Persisted price_samples rows are untouched (bounded retention
        ages them out); a re-promotion rebuilds strictly from fresh
        post-skew-guard observations.
        """
        key = str(symbol).upper()
        dropped = self._series.pop(key, None) is not None
        for marker in [m for m in self._dirty if m[0] == key]:
            del self._dirty[marker]
        return dropped

    def feature(self, symbol: str, as_of_ms: int) -> Dict[str, object]:
        """Feature record for one symbol. Unavailable horizons are None."""
        key = symbol.upper()
        series = self._series.get(key)
        record: Dict[str, object] = {
            "symbol": key,
            "current_price": None,
            "source": "markPrice",
            "source_timestamp_ms": None,
            "sample_age_ms": None,
            "history_span_ms": 0,
            "returns": {tf: None for tf in TIMEFRAME_ORDER},
            "anchor_ms": {tf: None for tf in TIMEFRAME_ORDER},
            "available_tfs": [],
            "warmup_complete": False,
        }
        if series is None:
            return record
        latest = series.latest()
        if latest is None:
            return record
        _, current_price = latest
        # Current price = newest sample at or before as_of (no future leak:
        # samples newer than as_of are invisible to this query).
        current = latest
        for bucket_start, price in series.buckets():
            if bucket_start <= as_of_ms:
                current = (bucket_start, price)
            else:
                break
        _, current_price = current
        record["current_price"] = current_price
        record["source_timestamp_ms"] = current[0]
        record["sample_age_ms"] = as_of_ms - current[0]
        oldest = series.oldest()
        record["history_span_ms"] = current[0] - oldest[0] if oldest else 0
        returns: Dict[str, Optional[float]] = {}
        anchors: Dict[str, Optional[int]] = {}
        available: List[str] = []
        for tf in TIMEFRAME_ORDER:
            tf_ms = TIMEFRAMES_MS[tf]
            target = current[0] - tf_ms
            anchor = series.lookup_at_or_before(
                target, anchor_tolerance_ms(tf_ms))
            if anchor is None or anchor[1] <= 0:
                returns[tf] = None
                anchors[tf] = None
                continue
            returns[tf] = math.log(current_price / anchor[1])
            anchors[tf] = anchor[0]
            available.append(tf)
        record["returns"] = returns
        record["anchor_ms"] = anchors
        record["available_tfs"] = available
        record["warmup_complete"] = len(available) == len(TIMEFRAME_ORDER)
        return record

    def snapshot_all(self, as_of_ms: int) -> List[Dict[str, object]]:
        return [self.feature(symbol, as_of_ms) for symbol in sorted(self._series)]

    def buckets(self, symbol: str) -> List[Tuple[int, float]]:
        """Event-time buckets for one symbol, oldest first (P1-08 reuse).

        Read-only copy for structure/volatility computation; the engine
        owns the series and no caller can mutate it through this.
        """
        series = self._series.get(str(symbol).upper())
        if series is None:
            return []
        return series.buckets()

    def momentum(self, symbol: str, as_of_ms: float,
                 horizons: tuple = ("1m", "3m", "5m", "15m")) -> Dict[str, object]:
        """Velocity/acceleration per horizon (P1-05; feature() untouched).

        Values are log-return rates (velocity) and their change rate
        (acceleration); unavailable horizons are None, never fabricated.
        """
        from .momentum import acceleration_at, velocity_at

        key = symbol.upper()
        series = self._series.get(key)
        out: Dict[str, object] = {
            "symbol": key, "as_of_ms": as_of_ms,
            "velocity": {}, "acceleration": {},
        }
        if series is None:
            out["velocity"] = {h: None for h in horizons}
            out["acceleration"] = {h: None for h in horizons}
            return out
        h_ms = {h: TIMEFRAMES_MS[h] for h in horizons if h in TIMEFRAMES_MS}
        out["velocity"] = {
            h: (v["value"] if (v := velocity_at(series, as_of_ms, ms)) else None)
            for h, ms in h_ms.items()}
        out["acceleration"] = {
            h: (a["value"] if (a := acceleration_at(series, as_of_ms, ms)) else None)
            for h, ms in h_ms.items()}
        return out

    def stats(self) -> Dict[str, Dict[str, object]]:
        out = {}
        for symbol, series in sorted(self._series.items()):
            oldest = series.oldest()
            latest = series.latest()
            span = (latest[0] - oldest[0]) if oldest and latest else 0
            out[symbol] = {
                "samples": len(series.buckets()),
                "updates": series.updates,
                "coalesced": series.coalesced,
                "dropped_late": series.dropped_late,
                "dropped_invalid": series.dropped_invalid,
                "span_ms": span,
            }
        out["_dropped_unknown"] = self.dropped_unknown  # type: ignore[assignment]
        return out

    def drain_dirty_buckets(self) -> List[Tuple[str, int, float]]:
        """Buckets changed since the last drain (for persistence)."""
        rows = [(symbol, bucket, price)
                for (symbol, bucket), price in sorted(self._dirty.items())]
        self._dirty.clear()
        return rows
