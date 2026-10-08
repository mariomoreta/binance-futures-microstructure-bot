"""P1-06 aggressive trade-flow engine (incremental, event-time, in-memory).

Source: Binance USD-M ``<symbol>@aggTrade`` (public WS). Every VALID event
that survives the probe skew guard is ingested here SYNCHRONOUSLY, before
(and independently of) the P1-04 raw-observation persistence sampling gate.
Sampling therefore never defines flow accuracy: the engine sees all valid
trades even when most raw observations are sampling-dropped.

Official aggTrade semantics (verified 2026-10-07 against the current
USD-M Futures docs + live WS payload; see docs/MARKET_DATA.md):
- One message aggregates fills with the SAME price and SAME taking side.
- ``m`` ("Is the buyer the market maker?"): true  -> buyer is maker, so the
  aggressive (taker) side is SELL; false -> buyer is taker, aggressive BUY.
  The maker side is NEVER the aggressor.
- ``q`` = total base quantity INCLUDING RPI fills; ``nq`` = normal quantity
  WITHOUT RPI fills. Totals use ``q``; ``rpi_qty = q - nq`` is tracked for
  transparency whenever ``nq`` is present and sane.
- ``E`` = event time (ordering + bucketing key); ``T`` = trade time.

Definitions (deterministic, no lookahead, UNKNOWN is None never 0):
- Horizon h is a trailing event-time window: a trade belongs to h iff
  ``as_of_ms - h_ms < event_ms <= as_of_ms``.
- signed_delta = buy_notional - sell_notional (quote/USDT terms).
- delta_ratio = delta / (buy_notional + sell_notional), None when the
  denominator is zero. Range [-1, +1]; + = net aggressive buying.
- buy_pct/sell_pct = side share of (buy+sell) notional in percent.
- Late/out-of-order: ``event_ms < newest seen`` is dropped and counted
  (dropped_late); history is never rewritten. Equal event times are ACCEPTED
  in arrival order: one 100ms push carries several distinct aggregates with
  identical ``E``, and the websocket never redelivers a message, so same-E
  trades are new volume, not duplicates. Unknown symbols refused and
  counted. Non-finite/non-positive price/qty or a missing/non-bool ``m``
  is dropped as invalid and counted (dropped_invalid) — the side is never
  guessed. Skew-rejected payloads never reach this engine (probe returns
  before it); that is covered by a probe-level test.
- Volume baselines: per size (10s/30s/1m/5m) the engine keeps COMPLETED
  bucket notionals only. Buckets skipped by a gap are counted
  (skipped_buckets) and NEVER fabricated as zeros. z = (cur-mean)/std over
  the trailing history; None when samples < min_buckets or std <= 0
  (zero-variance and insufficient history are UNKNOWN, never fake 0).
- Acceleration (canonical 1m baseline, timestamp-aware): current partial
  bucket rate vs last completed bucket rate, per-second for deltas:
  notional_rate_change, trade_rate_change, delta_rate_change. None until
  one bucket completed and elapsed > 0.

This module is pure feature math + bounded state. No trading, no signals,
no thresholds (existing detector thresholds stay HYPOTHESIS and untouched).
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from .telemetry import RunningDistribution

# Required flow horizons (trailing event-time windows).
FLOW_HORIZONS_MS: Dict[str, int] = {
    "10s": 10_000,
    "30s": 30_000,
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
}
FLOW_HORIZON_ORDER = ("10s", "30s", "1m", "3m", "5m", "15m")

# Volume baseline bucket sizes (seconds). z-scores are quote-notional based.
BASELINE_SIZES_S = (10, 30, 60, 300)
BASELINE_LABELS = ("10s", "30s", "1m", "5m")

# Completed buckets retained per (symbol, size) — bounds baseline memory and
# doubles as the restart-continuity payload (5m x 600 = ~50h coverage).
BASELINE_KEEP_BUCKETS = 600

# Acceleration reference baseline (documented canonical choice).
ACCEL_BASELINE_S = 60

# Longest horizon kept in the live trade window (+ small tolerance so a
# boundary trade is never evicted before its window closes).
MAX_WINDOW_MS = FLOW_HORIZONS_MS["15m"]


def _horizon_contains(event_ms: int, as_of_ms: int, horizon_ms: int) -> bool:
    """Trailing-window membership: (as_of - h, as_of]."""
    return (as_of_ms - horizon_ms) < event_ms <= as_of_ms


class SymbolFlowSeries:
    """Incremental per-symbol aggressive-flow state (one LIVE symbol).

    Trades are stored once in arrival order (which is non-decreasing event
    time by the late-drop policy). Per-horizon running totals are maintained
    incrementally: ingest is O(1) amortized, queries evict expired trades
    lazily before reading.
    """

    def __init__(self, min_baseline_buckets: int = 30) -> None:
        self.min_baseline_buckets = max(int(min_baseline_buckets), 1)
        # Per-horizon windows: (event_ms, qty, notional, side) with side
        # +1 buy / -1 sell, oldest first. Each window holds exactly the
        # trades in (newest - h, newest]; expiry is exact per horizon.
        self._windows: Dict[str, Deque[Tuple[int, float, float, int]]] = {
            h: deque() for h in FLOW_HORIZON_ORDER}
        # Per-horizon running totals over the CURRENT window contents.
        self._totals: Dict[str, Dict[str, float]] = {
            h: {"trades": 0.0, "base": 0.0, "notional": 0.0,
                "buy_base": 0.0, "sell_base": 0.0,
                "buy_notional": 0.0, "sell_notional": 0.0}
            for h in FLOW_HORIZON_ORDER
        }
        self.newest_ms: Optional[int] = None
        self.oldest_ms: Optional[int] = None
        self.trades_total = 0
        self.rpi_base_total = 0.0
        self.rpi_notional_total = 0.0
        self.rpi_trades = 0
        self.dropped_late = 0
        self.dropped_invalid = 0
        # Volume baselines per bucket size: open (partial) bucket + completed.
        self._open_bucket: Dict[int, Optional[Dict[str, Any]]] = {
            s: None for s in BASELINE_SIZES_S}
        self._completed: Dict[int, Deque[Dict[str, Any]]] = {
            s: deque(maxlen=BASELINE_KEEP_BUCKETS)
            for s in BASELINE_SIZES_S}
        self.skipped_buckets: Dict[int, int] = {s: 0 for s in BASELINE_SIZES_S}
        self.completed_buckets = 0
        # Completed buckets not yet drained for persistence.
        self._dirty_buckets: List[Dict[str, Any]] = []

    # -- ingest ---------------------------------------------------------

    def ingest(self, event_time_ms: int, price: float, quantity: float,
               buyer_is_maker: Any,
               normal_quantity: Any = None) -> bool:
        """Ingest one post-skew-guard aggTrade. False when refused (counted).

        ``buyer_is_maker`` must be a real bool; anything else is invalid
        (the side is never guessed). ``normal_quantity`` (nq) is optional.
        """
        if not isinstance(event_time_ms, int) or isinstance(event_time_ms, bool):
            try:
                event_time_ms = int(event_time_ms)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                self.dropped_invalid += 1
                return False
        if (not isinstance(price, (int, float))
                or not isinstance(quantity, (int, float))
                or isinstance(price, bool) or isinstance(quantity, bool)
                or not math.isfinite(price) or not math.isfinite(quantity)
                or price <= 0 or quantity <= 0):
            self.dropped_invalid += 1
            return False
        if not isinstance(buyer_is_maker, bool):
            # Side unknown: never fabricate direction.
            self.dropped_invalid += 1
            return False
        if self.newest_ms is not None and event_time_ms < self.newest_ms:
            self.dropped_late += 1
            return False

        side = -1 if buyer_is_maker else +1
        notional = float(price) * float(quantity)
        trade = (event_time_ms, float(price), float(quantity), notional, side)
        entry = (event_time_ms, float(quantity), notional, side)
        self.newest_ms = event_time_ms
        if self.oldest_ms is None:
            self.oldest_ms = event_time_ms
        self.trades_total += 1

        # RPI transparency: rpi_qty = q - nq when nq is present and sane.
        if (isinstance(normal_quantity, (int, float))
                and not isinstance(normal_quantity, bool)
                and math.isfinite(normal_quantity)
                and 0 <= normal_quantity <= quantity):
            rpi_qty = float(quantity) - float(normal_quantity)
            if rpi_qty > 0:
                self.rpi_base_total += rpi_qty
                self.rpi_notional_total += float(price) * rpi_qty
                self.rpi_trades += 1

        for horizon in FLOW_HORIZON_ORDER:
            window = self._windows[horizon]
            window.append(entry)
            totals = self._totals[horizon]
            totals["trades"] += 1.0
            totals["base"] += quantity
            totals["notional"] += notional
            if side > 0:
                totals["buy_base"] += quantity
                totals["buy_notional"] += notional
            else:
                totals["sell_base"] += quantity
                totals["sell_notional"] += notional
        self._evict_expired()
        self._accumulate_baseline(trade)
        return True

    def _evict_expired(self) -> None:
        """Exact per-horizon expiry: drop trades at/before newest - window.

        Each trade leaves a horizon exactly when it stops satisfying the
        trailing-window membership (event_ms > newest - h). Amortized O(1)
        per horizon per ingest; memory stays bounded by the 15m window.
        """
        assert self.newest_ms is not None
        for horizon, window_ms in FLOW_HORIZONS_MS.items():
            cutoff = self.newest_ms - window_ms
            window = self._windows[horizon]
            totals = self._totals[horizon]
            while window and window[0][0] <= cutoff:
                _, qty, notional, side = window.popleft()
                totals["trades"] -= 1.0
                totals["base"] -= qty
                totals["notional"] -= notional
                if side > 0:
                    totals["buy_base"] -= qty
                    totals["buy_notional"] -= notional
                else:
                    totals["sell_base"] -= qty
                    totals["sell_notional"] -= notional
        longest = self._windows["15m"]
        self.oldest_ms = longest[0][0] if longest else self.newest_ms

    # -- volume baselines ------------------------------------------------

    def _accumulate_baseline(
            self, trade: Tuple[int, float, float, float, int]) -> None:
        event_ms, price, qty, notional, side = trade
        for size_s in BASELINE_SIZES_S:
            size_ms = size_s * 1000
            bucket = event_ms - (event_ms % size_ms)
            current = self._open_bucket[size_s]
            if current is None:
                self._open_bucket[size_s] = self._new_bucket(bucket, trade)
                continue
            if bucket == current["bucket_ms"]:
                current["notional"] += notional
                current["base"] += qty
                current["trades"] += 1
                if side > 0:
                    current["buy_notional"] += notional
                else:
                    current["sell_notional"] += notional
                current["last_ms"] = event_ms
                continue
            # bucket > current (older is impossible: late drops guarantee
            # non-decreasing event time). Close the current bucket.
            self._close_bucket(size_s)
            if bucket > current["bucket_ms"] + size_ms:
                self.skipped_buckets[size_s] += (
                    (bucket - current["bucket_ms"]) // size_ms - 1)
            self._open_bucket[size_s] = self._new_bucket(bucket, trade)

    @staticmethod
    def _new_bucket(bucket_ms: int,
                    trade: Tuple[int, float, float, float, int]
                    ) -> Dict[str, Any]:
        _, _, qty, notional, side = trade
        return {"bucket_ms": bucket_ms, "notional": notional, "base": qty,
                "trades": 1,
                "buy_notional": notional if side > 0 else 0.0,
                "sell_notional": notional if side < 0 else 0.0,
                "first_ms": trade[0], "last_ms": trade[0]}

    def _close_bucket(self, size_s: int) -> None:
        current = self._open_bucket[size_s]
        if current is None:
            return
        record = {"size_s": size_s, "bucket_ms": current["bucket_ms"],
                  "notional": current["notional"], "base": current["base"],
                  "trades": current["trades"],
                  "buy_notional": current["buy_notional"],
                  "sell_notional": current["sell_notional"]}
        self._completed[size_s].append(record)
        self._dirty_buckets.append(record)
        self.completed_buckets += 1
        self._open_bucket[size_s] = None

    def drain_completed_buckets(self) -> List[Dict[str, Any]]:
        """Completed buckets since the last drain (for persistence)."""
        rows = list(self._dirty_buckets)
        self._dirty_buckets.clear()
        return rows

    def restore_buckets(self, rows: List[Dict[str, Any]]) -> int:
        """Reload persisted COMPLETED buckets (restart continuity).

        Only closed buckets are restored, so live accounting can never
        double-count them. Returns the number of rows accepted.
        """
        accepted = 0
        by_size: Dict[int, List[Dict[str, Any]]] = {}
        for row in rows:
            try:
                size_s = int(row["size_s"])
                bucket_ms = int(row["bucket_ms"])
            except (KeyError, TypeError, ValueError):
                continue
            if size_s not in BASELINE_SIZES_S:
                continue
            by_size.setdefault(size_s, []).append({
                "size_s": size_s, "bucket_ms": bucket_ms,
                "notional": float(row.get("notional", 0.0)),
                "base": float(row.get("base", 0.0)),
                "trades": int(row.get("trades", 0)),
                "buy_notional": float(row.get("buy_notional", 0.0)),
                "sell_notional": float(row.get("sell_notional", 0.0)),
            })
            accepted += 1
        for size_s, records in by_size.items():
            ordered = sorted(records, key=lambda r: r["bucket_ms"])
            for record in ordered[-BASELINE_KEEP_BUCKETS:]:
                self._completed[size_s].append(record)
        return accepted

    # -- features --------------------------------------------------------

    def horizon_feature(self, horizon: str, as_of_ms: int) -> Dict[str, Any]:
        """Trailing-window aggregate. Exact for the observed span."""
        window_ms = FLOW_HORIZONS_MS[horizon]
        totals = self._totals[horizon]
        buy = totals["buy_notional"]
        sell = totals["sell_notional"]
        denom = buy + sell
        delta = buy - sell
        if denom > 0:
            ratio: Optional[float] = delta / denom
            buy_pct: Optional[float] = buy / denom * 100.0
            sell_pct: Optional[float] = sell / denom * 100.0
        else:
            ratio = None
            buy_pct = None
            sell_pct = None
        span_ms = ((self.newest_ms - self.oldest_ms)
                   if self.newest_ms is not None and self.oldest_ms is not None
                   else 0)
        # Totals are maintained against newest_ms (the latest observed event
        # time): membership is exactly _horizon_contains(event, newest, h).
        # as_of_ms is carried for record provenance; wall-clock as_of beyond
        # newest adds no trades (no lookahead possible by construction).
        return {
            "trades": int(totals["trades"]),
            "base_volume": totals["base"],
            "notional": totals["notional"],
            "buy_base": totals["buy_base"],
            "sell_base": totals["sell_base"],
            "buy_notional": buy,
            "sell_notional": sell,
            "signed_delta": delta,
            "delta_ratio": ratio,
            "buy_pct": buy_pct,
            "sell_pct": sell_pct,
            "trade_rate": totals["trades"] / (window_ms / 1000.0),
            "notional_rate": totals["notional"] / (window_ms / 1000.0),
            "warmup_complete": span_ms >= window_ms,
            "window_ms": window_ms,
            "as_of_ms": as_of_ms,
        }

    def baseline_feature(self, size_s: int, as_of_ms: int) -> Dict[str, Any]:
        """Current bucket + trailing baseline stats for one bucket size."""
        label = {10: "10s", 30: "30s", 60: "1m", 300: "5m"}[size_s]
        history = [r["notional"] for r in self._completed[size_s]]
        current = self._open_bucket[size_s]
        cur_notional = current["notional"] if current else 0.0
        cur_base = current["base"] if current else 0.0
        cur_trades = current["trades"] if current else 0
        elapsed_ms = ((current["last_ms"] - current["bucket_ms"] + 1)
                      if current else 0)
        mean: Optional[float] = None
        std: Optional[float] = None
        z: Optional[float] = None
        warmed = len(history) >= self.min_baseline_buckets
        if warmed:
            mean = sum(history) / len(history)
            variance = (sum((v - mean) ** 2 for v in history) / len(history))
            if variance > 0:
                std = math.sqrt(variance)
                z = (cur_notional - mean) / std
            # else: zero-variance baseline -> z stays None (UNKNOWN).
        return {
            "bucket": label,
            "bucket_size_s": size_s,
            "current_notional": cur_notional,
            "current_base": cur_base,
            "current_trades": cur_trades,
            "bucket_start_ms": current["bucket_ms"] if current else None,
            "elapsed_ms": elapsed_ms,
            "mean_notional": mean,
            "std_notional": std,
            "z_score": z,
            "samples": len(history),
            "min_samples": self.min_baseline_buckets,
            "warmup": warmed and std is not None,
            "skipped_buckets": self.skipped_buckets[size_s],
            "as_of_ms": as_of_ms,
        }

    def acceleration_feature(self, as_of_ms: int) -> Dict[str, Any]:
        """Rate changes on the canonical 1m baseline (timestamp-aware)."""
        size_s = ACCEL_BASELINE_S
        current = self._open_bucket[size_s]
        completed = self._completed[size_s]
        out: Dict[str, Any] = {
            "baseline": "1m",
            "notional_rate": None,
            "notional_rate_change": None,
            "trade_rate": None,
            "trade_rate_change": None,
            "delta_rate": None,
            "delta_rate_change": None,
        }
        if current is None:
            return out
        elapsed_s = max((current["last_ms"] - current["bucket_ms"] + 1)
                        / 1000.0, 1e-3)
        cur_notional_rate = current["notional"] / elapsed_s
        cur_trade_rate = current["trades"] / elapsed_s
        cur_delta = current["buy_notional"] - current["sell_notional"]
        cur_delta_rate = cur_delta / elapsed_s
        out["notional_rate"] = cur_notional_rate
        out["trade_rate"] = cur_trade_rate
        out["delta_rate"] = cur_delta_rate
        if not completed:
            return out
        prev = completed[-1]
        span_s = float(size_s)
        out["notional_rate_change"] = (
            cur_notional_rate - prev["notional"] / span_s)
        out["trade_rate_change"] = cur_trade_rate - prev["trades"] / span_s
        prev_delta = prev["buy_notional"] - prev["sell_notional"]
        out["delta_rate_change"] = cur_delta_rate - prev_delta / span_s
        return out

    def snapshot(self, symbol: str, as_of_ms: int,
                 subscribed: bool) -> Dict[str, Any]:
        """Compact per-symbol flow record (persisted + dashboard/API)."""
        freshness_ms = (as_of_ms - self.newest_ms
                        if self.newest_ms is not None else None)
        span_ms = ((self.newest_ms - self.oldest_ms)
                   if self.newest_ms is not None and self.oldest_ms is not None
                   else 0)
        return {
            "symbol": symbol,
            "subscribed": subscribed,
            "live": subscribed and self.trades_total > 0,
            "as_of_ms": as_of_ms,
            "freshness_ms": freshness_ms,
            "span_ms": span_ms,
            "trades_total": self.trades_total,
            "rpi_base_total": self.rpi_base_total,
            "rpi_notional_total": self.rpi_notional_total,
            "rpi_trades": self.rpi_trades,
            "dropped_late": self.dropped_late,
            "dropped_invalid": self.dropped_invalid,
            "horizons": {h: self.horizon_feature(h, as_of_ms)
                         for h in FLOW_HORIZON_ORDER},
            "baselines": {label: self.baseline_feature(size_s, as_of_ms)
                          for label, size_s in
                          zip(BASELINE_LABELS, BASELINE_SIZES_S)},
            "acceleration": self.acceleration_feature(as_of_ms),
        }


class FlowEngine:
    """Multi-symbol incremental aggressive-flow engine."""

    def __init__(self, symbols: Tuple[str, ...] = (),
                 min_baseline_buckets: int = 30,
                 latency_max_samples: int = 20000) -> None:
        self._allowed = ({s.upper() for s in symbols} if symbols else None)
        self._series: Dict[str, SymbolFlowSeries] = {}
        self.min_baseline_buckets = max(int(min_baseline_buckets), 1)
        self.dropped_unknown = 0
        self.events_processed = 0
        self.bucket_updates = 0
        # Synchronous in-memory path: no queue exists by design.
        self.queue_high_water = 0
        self.queue_depth = 0
        self._latency = RunningDistribution(max(1, int(latency_max_samples)))

    def ingest(self, symbol: str, event_time_ms: int, price: float,
               quantity: float, buyer_is_maker: Any,
               normal_quantity: Any = None) -> bool:
        """Ingest one VALID aggTrade. Unknown symbols refused (counted)."""
        start_ns = time.perf_counter_ns()
        try:
            key = str(symbol).upper()
            if self._allowed is not None and key not in self._allowed:
                self.dropped_unknown += 1
                return False
            series = self._series.get(key)
            if series is None:
                series = self._series[key] = SymbolFlowSeries(
                    min_baseline_buckets=self.min_baseline_buckets)
            before = series.completed_buckets
            accepted = series.ingest(event_time_ms, price, quantity,
                                     buyer_is_maker, normal_quantity)
            if accepted:
                self.events_processed += 1
                self.bucket_updates += (series.completed_buckets - before)
            return accepted
        finally:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            self._latency.add(max(elapsed_ms, 0.0))

    def allow(self, symbols) -> List[str]:
        """Admit symbols to deep observation (P1-12B HOT promotions).

        No-op when the engine allows everything (tests). Returns the
        newly admitted symbols, sorted.
        """
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
        """Drop in-memory state for a demoted symbol.

        Persisted rows are untouched (history stays readable and ages out
        honestly). The caller must drain completed buckets first — see
        drain_completed_buckets — so no closed bucket is lost.
        """
        return self._series.pop(str(symbol).upper(), None) is not None

    def snapshot_all(self, as_of_ms: int) -> List[Dict[str, Any]]:
        """One record per known symbol (subscribed set = allowed set)."""
        out = []
        for symbol in sorted(self._series):
            subscribed = (self._allowed is None) or (symbol in self._allowed)
            out.append(self._series[symbol].snapshot(
                symbol, as_of_ms, subscribed))
        return out

    def drain_completed_buckets(self) -> List[Dict[str, Any]]:
        """Completed flow buckets since the last drain, with symbols."""
        rows = []
        for symbol in sorted(self._series):
            for record in self._series[symbol].drain_completed_buckets():
                rows.append({"symbol": symbol, **record})
        return rows

    def restore_buckets(self, rows: List[Dict[str, Any]]) -> int:
        """Reload persisted completed buckets per symbol (no double-count)."""
        by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            try:
                by_symbol.setdefault(str(row["symbol"]).upper(), []).append(row)
            except (KeyError, TypeError, AttributeError):
                continue
        accepted = 0
        for symbol, symbol_rows in by_symbol.items():
            if self._allowed is not None and symbol not in self._allowed:
                continue
            series = self._series.get(symbol)
            if series is None:
                series = self._series[symbol] = SymbolFlowSeries(
                    min_baseline_buckets=self.min_baseline_buckets)
            accepted += series.restore_buckets(symbol_rows)
        return accepted

    def stats(self) -> Dict[str, Any]:
        """Engine counters + latency distribution (probe summary block)."""
        latency = self._latency.snapshot()
        per_symbol = {}
        for symbol in sorted(self._series):
            series = self._series[symbol]
            per_symbol[symbol] = {
                "trades_total": series.trades_total,
                "dropped_late": series.dropped_late,
                "dropped_invalid": series.dropped_invalid,
                "completed_buckets": series.completed_buckets,
                "newest_ms": series.newest_ms,
            }
        return {
            "events_processed": self.events_processed,
            "dropped_unknown": self.dropped_unknown,
            "bucket_updates": self.bucket_updates,
            "queue_high_water": self.queue_high_water,
            "queue_depth": self.queue_depth,
            "latency_ms": latency,
            "symbols": per_symbol,
        }
