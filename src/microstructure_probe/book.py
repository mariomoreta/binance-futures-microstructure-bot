"""P1-07 order-book intelligence (incremental, snapshot-based, in-memory).

Source: Binance USD-M ``<symbol>@depth20@100ms`` (public WS, `/public`).
Every push is a FULL top-20 snapshot (not diffs), verified 2026-10-08
against the current USD-M docs + live payloads (see docs/MARKET_DATA.md):
fields ``e``/``E``/``T``/``s``/``U`` (first update ID) / ``u`` (final
update ID) / ``pu`` (previous final ID) / ``b``/``a`` levels /
``st`` (+``ps``). Only VALID updates (post-skew-guard) are ingested,
synchronously, before and independent of the raw-observation sampling
gate — sampling never defines book accuracy.

Definitions (deterministic, no lookahead, UNKNOWN is None never 0):
- Levels are (price, qty) pairs; best bid = max bid price, best ask = min
  ask price (never assume wire order). Zero-qty levels are filtered;
  negative/non-finite prices or quantities, or an emptied side, make the
  update INVALID (dropped + counted, previous snapshot retained).
- A crossed top (best bid >= best ask) is kept and counted, not dropped:
  it is real (transient) market data.
- mid = (bid + ask) / 2; spread_abs = ask - bid;
  spread_bps = spread_abs / mid * 10_000.
- Depth sums over the visible levels, per side, base + notional, for
  top-1/5/10/20 (fewer levels when coverage is thinner; counts exposed).
- imbalance_qty = (bidQ - askQ) / (bidQ + askQ); imbalance_notional uses
  notionals instead. None when the denominator is zero.
- microprice = (Pa * Qb + Pb * Qa) / (Qb + Qa) on top-of-book quantities;
  None when Qb + Qa == 0. displacement_bps = (micro - mid) / mid * 10_000.
  Pure description — never a signal.
- Depth slope (explicit secant-free method): least-squares fit THROUGH THE
  ORIGIN of cumulative side notional C(d) against level distance d in bps
  from mid: slope = sum(d*C) / sum(d^2) (notional per bp). Uses every
  visible level; single-level books yield C/d exactly. slope_asymmetry =
  (bid_slope - ask_slope) / (bid_slope + ask_slope), None on zero denom.
- Concentration: share of side notional within 5/10/25 bps of mid. A band
  is reported ONLY if the visible book spans it (max distance >= band);
  otherwise None + coverage exposed (max_dist_bps per side). Never
  fabricated.
- Sequence integrity: continuity requires ``pu == last u``. A mismatch
  means intermediate snapshots were missed (counts as a gap); the current
  FULL snapshot is still a valid picture, but state is marked DEGRADED
  until a chained update (``pu == last u``) re-establishes continuity.
  Strictly-older ``E`` never regresses the book (dropped + counted);
  same-E accepted in arrival order. First update per symbol is always
  accepted (nothing to chain against).
- Freshness: as_of - newest_E (None before the first update).

This module is pure feature math + bounded state. No trading, no signals,
no thresholds, no composite quality score (P1-11/P1-12 own modeling).
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

from .telemetry import RunningDistribution

# Visible depth cutoffs (top-N levels per side).
TOP_NS = (1, 5, 10, 20)

# Concentration bands in bps from mid.
CONCENTRATION_BANDS_BPS = (5.0, 10.0, 25.0)

Level = Tuple[float, float]  # (price, qty)


def parse_levels(raw: Any) -> Optional[List[Level]]:
    """Parse wire levels [[price, qty], ...] -> [(float, float)].

    Returns None when the shape is unusable. Zero-qty levels are filtered
    (tolerated); negative or non-finite numbers invalidate the whole side.
    """
    if not isinstance(raw, (list, tuple)):
        return None
    out: List[Level] = []
    for entry in raw:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            return None
        try:
            price = float(entry[0])
            qty = float(entry[1])
        except (TypeError, ValueError):
            return None
        if (not math.isfinite(price) or not math.isfinite(qty)
                or price <= 0 or qty < 0):
            return None
        if qty > 0:
            out.append((price, qty))
    return out


def _sums_sorted(levels_sorted_asc: List[Level], top_n: int,
                 best_first: bool) -> Tuple[float, float, int]:
    """(base_qty, notional, levels_used) over the best top_n levels.

    Bids are asc-sorted (best = last, best_first=False); asks are asc-sorted
    (best = first, best_first=True). Kept explicit to avoid side confusion.
    """
    if best_first:
        chosen = levels_sorted_asc[:max(top_n, 0)]
    else:
        chosen = levels_sorted_asc[-max(top_n, 0):] if top_n > 0 else []
    base = sum(q for _, q in chosen)
    notional = sum(p * q for p, q in chosen)
    return base, notional, len(chosen)


def _imbalance(bid: float, ask: float) -> Optional[float]:
    denom = bid + ask
    if denom <= 0:
        return None
    return (bid - ask) / denom


def _slope_ls_origin(distances_bps: List[float],
                     cum_notionals: List[float]) -> Optional[float]:
    """Least-squares slope through the origin: sum(d*C)/sum(d^2)."""
    denom = sum(d * d for d in distances_bps)
    if denom <= 0 or not distances_bps:
        return None
    return sum(d * c for d, c in zip(distances_bps, cum_notionals)) / denom


def book_features(bids: List[Level], asks: List[Level]) -> Optional[Dict[str, Any]]:
    """Pure book intelligence from one validated snapshot.

    Returns None only when a side is empty (caller counts invalid).
    """
    if not bids or not asks:
        return None
    best_bid = max(p for p, _ in bids)
    best_ask = min(p for p, _ in asks)
    top_bid_qty = sum(q for p, q in bids if p == best_bid)
    top_ask_qty = sum(q for p, q in asks if p == best_ask)
    mid = (best_bid + best_ask) / 2.0
    spread_abs = best_ask - best_bid
    spread_bps = spread_abs / mid * 10_000.0 if mid > 0 else None

    bids_asc = sorted(bids, key=lambda lv: lv[0])
    asks_asc = sorted(asks, key=lambda lv: lv[0])
    depth: Dict[str, Any] = {}
    for top_n in TOP_NS:
        bid_base, bid_not, bid_n = _sums_sorted(bids_asc, top_n, best_first=False)
        ask_base, ask_not, ask_n = _sums_sorted(asks_asc, top_n, best_first=True)
        depth[f"top{top_n}"] = {
            "bid_base": bid_base, "bid_notional": bid_not,
            "ask_base": ask_base, "ask_notional": ask_not,
            "bid_levels": bid_n, "ask_levels": ask_n,
        }
    full = depth["top20"]
    imbalance_qty = _imbalance(full["bid_base"], full["ask_base"])
    imbalance_notional = _imbalance(full["bid_notional"], full["ask_notional"])

    denom_q = top_bid_qty + top_ask_qty
    microprice = ((best_ask * top_bid_qty + best_bid * top_ask_qty) / denom_q
                  if denom_q > 0 else None)
    displacement_bps = ((microprice - mid) / mid * 10_000.0
                        if microprice is not None and mid > 0 else None)

    slopes: Dict[str, Any] = {}
    concentrations: Dict[str, Any] = {}
    for side, ordered in (("bid", list(reversed(bids_asc))), ("ask", asks_asc)):
        cum = 0.0
        distances: List[float] = []
        cumulated: List[float] = []
        within: Dict[float, float] = {band: 0.0 for band in CONCENTRATION_BANDS_BPS}
        total = 0.0
        for price, qty in ordered:
            notional = price * qty
            cum += notional
            total += notional
            dist = abs(price - mid) / mid * 10_000.0 if mid > 0 else 0.0
            distances.append(dist)
            cumulated.append(cum)
            for band in CONCENTRATION_BANDS_BPS:
                if dist <= band:
                    within[band] += notional
        slope = _slope_ls_origin(distances, cumulated)
        max_dist = max(distances) if distances else 0.0
        slopes[f"{side}_slope_notional_per_bp"] = slope
        slopes[f"{side}_max_dist_bps"] = max_dist
        conc: Dict[str, Any] = {}
        for band in CONCENTRATION_BANDS_BPS:
            key = f"within_{int(band)}bps" if band == int(band) else f"within_{band}bps"
            if max_dist >= band and total > 0:
                conc[key] = within[band] / total
            else:
                conc[key] = None
        conc["coverage_max_dist_bps"] = max_dist
        concentrations[side] = conc
    bid_slope = slopes["bid_slope_notional_per_bp"]
    ask_slope = slopes["ask_slope_notional_per_bp"]
    if (bid_slope is not None and ask_slope is not None
            and (bid_slope + ask_slope) > 0):
        slope_asymmetry = (bid_slope - ask_slope) / (bid_slope + ask_slope)
    else:
        slope_asymmetry = None
    slopes["asymmetry"] = slope_asymmetry

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "top_bid_qty": top_bid_qty,
        "top_ask_qty": top_ask_qty,
        "mid": mid,
        "spread_abs": spread_abs,
        "spread_bps": spread_bps,
        "crossed": best_bid >= best_ask,
        "depth": depth,
        "bid_levels": len(bids),
        "ask_levels": len(asks),
        "imbalance_qty": imbalance_qty,
        "imbalance_notional": imbalance_notional,
        "microprice": microprice,
        "microprice_displacement_bps": displacement_bps,
        "slopes": slopes,
        "concentration": concentrations,
    }


class SymbolBookState:
    """Latest-book state for one LIVE symbol (snapshot replaces, bounded)."""

    def __init__(self) -> None:
        self.features: Optional[Dict[str, Any]] = None
        self.newest_ms: Optional[int] = None
        self.last_u: Optional[int] = None
        self.messages_processed = 0
        self.invalid_updates = 0
        self.dropped_late = 0
        self.sequence_gaps = 0
        self.crossed_tops = 0
        self.degraded = False
        self.features_updated = 0

    def ingest(self, event_time_ms: int, update_id: Any,
               prev_update_id: Any, bids_raw: Any, asks_raw: Any) -> bool:
        """Ingest one post-skew-guard depth push. False when refused."""
        try:
            event_ms = int(event_time_ms)
        except (TypeError, ValueError):
            self.invalid_updates += 1
            return False
        if isinstance(event_ms, bool):
            self.invalid_updates += 1
            return False
        try:
            update_id = int(update_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            self.invalid_updates += 1
            return False
        bids = parse_levels(bids_raw)
        asks = parse_levels(asks_raw)
        if bids is None or asks is None or not bids or not asks:
            self.invalid_updates += 1
            return False
        if self.newest_ms is not None and event_ms < self.newest_ms:
            self.dropped_late += 1
            return False
        features = book_features(bids, asks)
        if features is None:  # unreachable given non-empty sides; guard anyway
            self.invalid_updates += 1
            return False
        # Sequence continuity: pu must chain onto the previous final id.
        # The FIRST update has nothing to chain against (always accepted).
        if self.last_u is not None and prev_update_id is not None:
            try:
                if int(prev_update_id) != self.last_u:  # type: ignore[arg-type]
                    self.sequence_gaps += 1
                    self.degraded = True
                else:
                    self.degraded = False
            except (TypeError, ValueError):
                self.sequence_gaps += 1
                self.degraded = True
        self.features = features
        self.newest_ms = event_ms
        self.last_u = update_id
        self.messages_processed += 1
        self.features_updated += 1
        if features["crossed"]:
            self.crossed_tops += 1
        return True

    def snapshot(self, symbol: str, as_of_ms: int,
                 subscribed: bool) -> Dict[str, Any]:
        """Latest-book record (historical/stale-flagged, never fabricated)."""
        freshness_ms = (as_of_ms - self.newest_ms
                        if self.newest_ms is not None else None)
        record: Dict[str, Any] = {
            "symbol": symbol,
            "subscribed": subscribed,
            "live": subscribed and self.features is not None and not self.degraded,
            "as_of_ms": as_of_ms,
            "freshness_ms": freshness_ms,
            "degraded": self.degraded,
            "sequence_gaps": self.sequence_gaps,
            "last_u": self.last_u,
            "messages_processed": self.messages_processed,
            "invalid_updates": self.invalid_updates,
            "dropped_late": self.dropped_late,
            "crossed_tops": self.crossed_tops,
            "features_updated": self.features_updated,
            "book": self.features,
        }
        return record


class BookEngine:
    """Multi-symbol incremental order-book intelligence."""

    def __init__(self, symbols: tuple = (),
                 latency_max_samples: int = 20000) -> None:
        self._allowed = ({str(s).upper() for s in symbols} if symbols else None)
        self._books: Dict[str, SymbolBookState] = {}
        self.dropped_unknown = 0
        self.messages_processed = 0
        # Synchronous in-memory path: no queue exists by design.
        self.queue_high_water = 0
        self.queue_depth = 0
        self._latency = RunningDistribution(max(1, int(latency_max_samples)))

    def ingest(self, symbol: str, event_time_ms: int, update_id: Any,
               prev_update_id: Any, bids: Any, asks: Any) -> bool:
        """Ingest one VALID depth push. Unknown symbols refused (counted)."""
        start_ns = time.perf_counter_ns()
        try:
            key = str(symbol).upper()
            if self._allowed is not None and key not in self._allowed:
                self.dropped_unknown += 1
                return False
            book = self._books.get(key)
            if book is None:
                book = self._books[key] = SymbolBookState()
            accepted = book.ingest(event_time_ms, update_id,
                                   prev_update_id, bids, asks)
            if accepted:
                self.messages_processed += 1
            return accepted
        finally:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            self._latency.add(max(elapsed_ms, 0.0))

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
        """Drop in-memory book state for a demoted symbol.

        Persisted latest rows are untouched (they age out honestly via
        freshness gates); a fresh subscription starts DEGRADED-free only
        after a chained update sequence, never from stale memory.
        """
        return self._books.pop(str(symbol).upper(), None) is not None

    def snapshot_all(self, as_of_ms: int) -> List[Dict[str, Any]]:
        """One record per known symbol (subscribed set = allowed set)."""
        out = []
        for symbol in sorted(self._books):
            subscribed = (self._allowed is None) or (symbol in self._allowed)
            out.append(self._books[symbol].snapshot(
                symbol, as_of_ms, subscribed))
        return out

    def stats(self) -> Dict[str, Any]:
        """Engine counters + latency distribution (probe summary block)."""
        latency = self._latency.snapshot()
        per_symbol = {}
        for symbol in sorted(self._books):
            book = self._books[symbol]
            per_symbol[symbol] = {
                "messages_processed": book.messages_processed,
                "invalid_updates": book.invalid_updates,
                "dropped_late": book.dropped_late,
                "sequence_gaps": book.sequence_gaps,
                "degraded": book.degraded,
                "crossed_tops": book.crossed_tops,
                "newest_ms": book.newest_ms,
            }
        return {
            "messages_processed": self.messages_processed,
            "dropped_unknown": self.dropped_unknown,
            "queue_high_water": self.queue_high_water,
            "queue_depth": self.queue_depth,
            "latency_ms": latency,
            "symbols": per_symbol,
        }
