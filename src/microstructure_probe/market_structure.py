"""P1-08 VWAP + realized volatility + range + market-structure primitives.

Zero new data sources. Everything here is computed from already-validated,
already-persisted state — no new websocket streams, no REST, no kline
bootstrap (existing 10s mark-price buckets cover 25.5h; see MARKET_DATA):

- VWAP comes from the P1-06 FlowEngine horizon aggregates: VWAP_h =
  notional_h / base_h (sum(price*qty)/sum(qty) exactly, same pre-sampling
  provenance, no second trade ingest, no double-count risk). 30m/1h are
  NOT offered: flow provenance ends at 15m and P1-08 invents no window
  beyond its sources.
- Reference price is the P1-04 mark-price current_price (canonical return
  source: regular ~1s cadence, event-time stamped). Labeled
  `reference_source: "markPrice"` on every record; never silently mixed.
- Volatility/range/structure come from the P1-04 10s bucket series
  (last-wins, persisted + restored, no lookahead).

Definitions (deterministic, timestamp-aware, no lookahead, UNKNOWN is
None never 0):
- VWAP horizons 1m/3m/5m/15m: vwap, reference price, displacement abs/%/
  bps = (ref - vwap)/vwap (*100/*10_000), trade count, notional, freshness
  (flow-record age), warmup_complete (flow horizon flag). Denominator zero
  (no base volume) -> vwap/displacement UNKNOWN. Displacement is raw
  description — never bullish/bearish, never a signal.
- Realized volatility horizons 1m/5m/15m/1h: raw (non-annualized) horizon
  volatility rv = sqrt(sum of squared consecutive-bucket log returns) over
  buckets in (as_of - h, as_of]. Requires >= 5 returns AND span >= h,
  else UNKNOWN (never fake zero from missing data). Reports n, span_ms,
  warmed flag (n >= expected bucket count), freshness (price-data age).
- Range horizons 1m/5m/15m: rolling high/low over in-window buckets;
  range_abs, range_pct = (high-low)/low (*100 for pct? no — fraction;
  dashboard formats), range_position = (ref - low)/(high - low) in [0,1],
  null when high == low. Expansion: current range vs trailing median of up
  to 10 prior COMPLETED non-overlapping h-blocks (ratio), plus z-score
  when >= 10 blocks and std > 0 else null. UNKNOWN on thin history.
- Structure (method A: confirmed local pivots, L=R=3 buckets = 30s each
  side on the 10s grid): bucket i is a swing high iff price[i] is the
  strict maximum over [i-3, i+3]; swing low iff strict minimum. A pivot at
  i is CONFIRMED only once bucket i+3 exists — 30s explicit delay, no
  future bars beyond the confirmation window, timestamped at the pivot
  bucket. Exposes last two confirmed swing highs/lows, higher-high /
  lower-high / higher-low / lower-low relations (null until two pivots),
  signed distance bps to most recent swing high/low, and breakout state
  vs the prior COMPLETED 15m grid block: ABOVE_PRIOR_RANGE /
  BELOW_PRIOR_RANGE / INSIDE_PRIOR_RANGE (raw description only — never
  BUY/SELL/LONG/SHORT/signal).
- Book resilience (§11): DEFERRED — spread/depth event history is not
  retained anywhere (book engine keeps latest only); building it is a
  P1-11 modeling task, not a P1-08 freebie. See DECISIONS.

The engine is stateless compute over peer-engine state (+ its own latency
distribution and counters). Only subscribed symbols are evaluated; HOT/
discovery symbols never appear here.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

from .telemetry import RunningDistribution

# VWAP horizons mirror the flow engine (its provenance ends at 15m).
VWAP_HORIZONS = ("1m", "3m", "5m", "15m")

# Volatility horizons (1h needs ~360 buckets; persisted series covers it).
VOL_HORIZONS_MS: Dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
}
VOL_HORIZON_ORDER = ("1m", "5m", "15m", "1h")
VOL_MIN_RETURNS = 5

# Range horizons.
RANGE_HORIZONS_MS: Dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
}
RANGE_HORIZON_ORDER = ("1m", "5m", "15m")
RANGE_BASELINE_BLOCKS = 10

# Swing pivot half-windows in buckets (10s grid -> 30s each side).
SWING_HALF_WINDOW = 3

# Prior-range breakout reference: last completed 15m grid block.
BREAKOUT_BLOCK_MS = 900_000


def _horizon_buckets(buckets: List[Tuple[int, float]],
                     as_of_ms: int, window_ms: int) -> List[Tuple[int, float]]:
    """Buckets with (as_of - h) < start <= as_of (no lookahead)."""
    return [(ms, price) for ms, price in buckets
            if as_of_ms - window_ms < ms <= as_of_ms]


def vwap_record(flow_horizon: Dict[str, Any],
                reference_price: Optional[float],
                as_of_ms: int) -> Dict[str, Any]:
    """One-horizon VWAP from a P1-06 flow aggregate + mark reference."""
    base = flow_horizon.get("base_volume")
    notional = flow_horizon.get("notional")
    record: Dict[str, Any] = {
        "window_ms": flow_horizon.get("window_ms"),
        "vwap": None,
        "reference_price": reference_price,
        "reference_source": "markPrice",
        "displacement_abs": None,
        "displacement_pct": None,
        "displacement_bps": None,
        "trades": flow_horizon.get("trades"),
        "notional": notional,
        "base_volume": base,
        "freshness_ms": None,
        "warmup_complete": bool(flow_horizon.get("warmup_complete", False)),
    }
    fresh = flow_horizon.get("as_of_ms")
    if isinstance(fresh, (int, float)):
        record["freshness_ms"] = as_of_ms - fresh
    try:
        base_f = float(base) if base is not None else 0.0
        notional_f = float(notional) if notional is not None else 0.0
        ref = float(reference_price) if reference_price is not None else None
    except (TypeError, ValueError):
        return record
    if base_f <= 0 or ref is None or not math.isfinite(ref) or ref <= 0:
        return record
    vwap = notional_f / base_f
    if not math.isfinite(vwap) or vwap <= 0:
        return record
    record["vwap"] = vwap
    record["displacement_abs"] = ref - vwap
    record["displacement_pct"] = (ref - vwap) / vwap * 100.0
    record["displacement_bps"] = (ref - vwap) / vwap * 10_000.0
    return record


def realized_vol(buckets: List[Tuple[int, float]], as_of_ms: int,
                 window_ms: int, bucket_grid_ms: int = 10_000) -> Dict[str, Any]:
    """Raw horizon volatility: sqrt(sum of squared log bucket returns).

    Value rule: >= VOL_MIN_RETURNS consecutive returns spanning at least
    window minus one grid step (a full grid window inherently spans
    window - grid, never the full window — strict >= window could never
    warm). Warmed adds full grid coverage: bucket count >= window/grid.
    """
    window = _horizon_buckets(buckets, as_of_ms, window_ms)
    record: Dict[str, Any] = {
        "window_ms": window_ms,
        "realized_vol": None,
        "returns": 0,
        "span_ms": 0,
        "buckets": len(window),
        "warmed": False,
        "freshness_ms": None,
    }
    if not window:
        return record
    record["freshness_ms"] = as_of_ms - window[-1][0]
    record["span_ms"] = window[-1][0] - window[0][0] if len(window) > 1 else 0
    logrets: List[float] = []
    for (_, prev), (_, price) in zip(window, window[1:]):
        if prev > 0 and price > 0:
            logrets.append(math.log(price / prev))
    record["returns"] = len(logrets)
    if len(logrets) < VOL_MIN_RETURNS:
        return record
    if record["span_ms"] < window_ms - bucket_grid_ms:
        return record
    record["realized_vol"] = math.sqrt(sum(r * r for r in logrets))
    record["warmed"] = len(window) >= window_ms // bucket_grid_ms
    return record


def range_record(buckets: List[Tuple[int, float]], as_of_ms: int,
                 window_ms: int, reference_price: Optional[float],
                 baseline_blocks: int = RANGE_BASELINE_BLOCKS
                 ) -> Dict[str, Any]:
    """Rolling high/low/position + expansion vs trailing median block."""
    window = _horizon_buckets(buckets, as_of_ms, window_ms)
    record: Dict[str, Any] = {
        "window_ms": window_ms,
        "high": None, "low": None,
        "range_abs": None, "range_pct": None,
        "range_position": None,
        "expansion_ratio": None, "expansion_z": None,
        "baseline_blocks": 0,
        "freshness_ms": None,
    }
    if not window:
        return record
    record["freshness_ms"] = as_of_ms - window[-1][0]
    prices = [price for _, price in window]
    high, low = max(prices), min(prices)
    record["high"] = high
    record["low"] = low
    if low <= 0:
        return record
    record["range_abs"] = high - low
    record["range_pct"] = (high - low) / low
    if high > low and reference_price is not None:
        try:
            ref = float(reference_price)
            if math.isfinite(ref):
                record["range_position"] = (ref - low) / (high - low)
        except (TypeError, ValueError):
            pass
    # Expansion: up to N prior COMPLETED non-overlapping h-blocks, oldest
    # side only (all block ends <= window start — no lookahead).
    window_start = as_of_ms - window_ms
    block_ranges: List[float] = []
    cursor_end = window_start - (window_start % window_ms) \
        if window_ms > 0 else window_start
    for _ in range(baseline_blocks):
        block_start = cursor_end - window_ms
        block = [price for ms, price in buckets
                 if block_start < ms <= cursor_end]
        if len(block) >= 2:
            block_ranges.append(max(block) - min(block))
        cursor_end = block_start
    record["baseline_blocks"] = len(block_ranges)
    if not block_ranges:
        return record
    ordered = sorted(block_ranges)
    median = ordered[len(ordered) // 2]
    if median > 0 and (high - low) >= 0:
        record["expansion_ratio"] = (high - low) / median
    if len(block_ranges) >= 10:
        mean = sum(block_ranges) / len(block_ranges)
        variance = (sum((v - mean) ** 2 for v in block_ranges)
                    / len(block_ranges))
        if variance > 0:
            record["expansion_z"] = ((high - low) - mean) / math.sqrt(variance)
    return record


def find_swings(buckets: List[Tuple[int, float]],
                half_window: int = SWING_HALF_WINDOW
                ) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """Confirmed local pivots: strict max/min over [i-k, i+k].

    Pivot at i confirms only once bucket i+k exists (explicit delay);
    unconfirmed tail buckets never yield pivots (no lookahead).
    """
    highs: List[Tuple[int, float]] = []
    lows: List[Tuple[int, float]] = []
    prices = [price for _, price in buckets]
    last_confirmable = len(prices) - half_window - 1
    for i in range(half_window, last_confirmable + 1):
        price = prices[i]
        window = prices[i - half_window:i + half_window + 1]
        if price == max(window) and window.count(price) == 1:
            highs.append(buckets[i])
        if price == min(window) and window.count(price) == 1:
            lows.append(buckets[i])
    return highs, lows


def _signed_distance_bps(reference: Optional[float],
                         level: Optional[float]) -> Optional[float]:
    try:
        ref = float(reference) if reference is not None else None
        lvl = float(level) if level is not None else None
    except (TypeError, ValueError):
        return None
    if ref is None or lvl is None or not math.isfinite(ref) \
            or not math.isfinite(lvl) or lvl <= 0 or ref <= 0:
        return None
    return (ref - lvl) / lvl * 10_000.0


def structure_record(buckets: List[Tuple[int, float]], as_of_ms: int,
                     reference_price: Optional[float]) -> Dict[str, Any]:
    """Swing pivots, relations, distances, prior-range breakout state."""
    visible = [(ms, price) for ms, price in buckets if ms <= as_of_ms]
    highs, lows = find_swings(visible)
    record: Dict[str, Any] = {
        "swing_highs": [{"bucket_ms": ms, "price": price}
                        for ms, price in highs[-2:]],
        "swing_lows": [{"bucket_ms": ms, "price": price}
                       for ms, price in lows[-2:]],
        "higher_high": None,
        "lower_high": None,
        "higher_low": None,
        "lower_low": None,
        "distance_to_swing_high_bps": None,
        "distance_to_swing_low_bps": None,
        "breakout_state": "UNKNOWN",
        "prior_range_high": None,
        "prior_range_low": None,
        "freshness_ms": (as_of_ms - visible[-1][0]) if visible else None,
    }
    if len(highs) >= 2:
        record["higher_high"] = highs[-1][1] > highs[-2][1]
        record["lower_high"] = highs[-1][1] < highs[-2][1]
    if len(lows) >= 2:
        record["higher_low"] = lows[-1][1] > lows[-2][1]
        record["lower_low"] = lows[-1][1] < lows[-2][1]
    if highs:
        record["distance_to_swing_high_bps"] = _signed_distance_bps(
            reference_price, highs[-1][1])
    if lows:
        record["distance_to_swing_low_bps"] = _signed_distance_bps(
            reference_price, lows[-1][1])
    # Breakout vs the prior COMPLETED 15m grid block (fully before the
    # current block — no lookahead, no partial-block leakage).
    block = BREAKOUT_BLOCK_MS
    current_block_start = as_of_ms - (as_of_ms % block)
    prior = [(ms, price) for ms, price in buckets
             if current_block_start - block < ms <= current_block_start]
    if len(prior) >= 2 and reference_price is not None:
        try:
            ref = float(reference_price)
            if math.isfinite(ref) and ref > 0:
                phi = max(price for _, price in prior)
                plo = min(price for _, price in prior)
                record["prior_range_high"] = phi
                record["prior_range_low"] = plo
                if ref > phi:
                    record["breakout_state"] = "ABOVE_PRIOR_RANGE"
                elif ref < plo:
                    record["breakout_state"] = "BELOW_PRIOR_RANGE"
                else:
                    record["breakout_state"] = "INSIDE_PRIOR_RANGE"
        except (TypeError, ValueError):
            pass
    return record


class MarketStructureEngine:
    """Stateless compute over peer-engine state (+ latency and counters)."""

    def __init__(self, symbols: tuple = (),
                 latency_max_samples: int = 20000) -> None:
        self._allowed = ({str(s).upper() for s in symbols} if symbols else None)
        self.dropped_unknown = 0
        self.symbols_evaluated = 0
        # Synchronous in-memory path: no queue exists by design.
        self.queue_high_water = 0
        self.queue_depth = 0
        self._latency = RunningDistribution(max(1, int(latency_max_samples)))

    def snapshot_symbol(self, symbol: str, as_of_ms: int,
                        flow_record: Optional[Dict[str, Any]],
                        price_record: Optional[Dict[str, Any]],
                        buckets: List[Tuple[int, float]]) -> Dict[str, Any]:
        """One full per-symbol record (VWAP + vol + range + structure)."""
        start_ns = time.perf_counter_ns()
        try:
            key = str(symbol).upper()
            if self._allowed is not None and key not in self._allowed:
                self.dropped_unknown += 1
                return {"symbol": key, "subscribed": False,
                        "live": False, "as_of_ms": as_of_ms}
            ref = (price_record or {}).get("current_price")
            horizons = ((flow_record or {}).get("horizons")
                        if isinstance((flow_record or {}).get("horizons"), dict)
                        else {})
            vwap = {h: vwap_record(horizons.get(h, {}), ref, as_of_ms)
                    for h in VWAP_HORIZONS}
            volatility = {h: realized_vol(buckets, as_of_ms, ms)
                          for h, ms in VOL_HORIZONS_MS.items()}
            price_age = (price_record or {}).get("sample_age_ms")
            ranges = {h: range_record(buckets, as_of_ms, ms, ref)
                      for h, ms in RANGE_HORIZONS_MS.items()}
            structure = structure_record(buckets, as_of_ms, ref)
            self.symbols_evaluated += 1
            return {
                "symbol": key,
                "subscribed": True,
                "live": True,
                "as_of_ms": as_of_ms,
                "reference_price": ref,
                "reference_source": "markPrice",
                "price_age_ms": price_age,
                "vwap": vwap,
                "volatility": volatility,
                "ranges": ranges,
                "structure": structure,
            }
        finally:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            self._latency.add(max(elapsed_ms, 0.0))

    def stats(self) -> Dict[str, Any]:
        """Engine counters + latency distribution (probe summary block)."""
        return {
            "symbols_evaluated": self.symbols_evaluated,
            "dropped_unknown": self.dropped_unknown,
            "queue_high_water": self.queue_high_water,
            "queue_depth": self.queue_depth,
            "latency_ms": self._latency.snapshot(),
        }
