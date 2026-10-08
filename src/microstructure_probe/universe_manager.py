"""P1-12B dynamic universe manager (selection + lifecycle, no transport).

Separates three universes:

- DISCOVERY: every eligible contract from cheap public REST scans.
- CORE: protected deeply-observed symbols (config trio; never evicted by
  HOT rotation, never demoted by a failed HOT promotion).
- HOT: a bounded set of discovery candidates promoted to deep observation.

Per-symbol lifecycle states (subscription/capability lifecycle — NOT the
P1-12A market-state classifications; EXPANSION must never be confused
with LIVE):

DISCOVERY_ONLY / PROMOTION_PENDING / SUBSCRIBING / WARMING / LIVE /
DEGRADED / DEMOTION_PENDING / UNSUBSCRIBING / STALE / UNKNOWN.

Pure deterministic logic over discovery snapshots: eligibility, freshness,
budget, rank (movement score with deterministic tie-breaks), dwell,
cooldowns. No classifier output is consumed (no circular dependency);
no flow/book/OI is assumed pre-subscription. All thresholds HYPOTHESIS.

Resource posture: conservative local policy only. The official USD-M
websocket docs were not fetchable from this environment, so every
transport cap is an UNVERIFIED assumption and the manager fails closed
(no promotion) whenever a budget would break.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

UNIVERSE_VERSION = "v0"

ST_DISCOVERY_ONLY = "DISCOVERY_ONLY"
ST_PROMOTION_PENDING = "PROMOTION_PENDING"
ST_SUBSCRIBING = "SUBSCRIBING"
ST_WARMING = "WARMING"
ST_LIVE = "LIVE"
ST_DEGRADED = "DEGRADED"
ST_DEMOTION_PENDING = "DEMOTION_PENDING"
ST_UNSUBSCRIBING = "UNSUBSCRIBING"
ST_STALE = "STALE"
ST_UNKNOWN = "UNKNOWN"

LIFECYCLE_STATES = (
    ST_DISCOVERY_ONLY, ST_PROMOTION_PENDING, ST_SUBSCRIBING, ST_WARMING,
    ST_LIVE, ST_DEGRADED, ST_DEMOTION_PENDING, ST_UNSUBSCRIBING,
    ST_STALE, ST_UNKNOWN,
)

# Streams consumed per deeply-observed symbol: bookTicker + depth20 +
# aggTrade. markPrice (!arr) and forceOrder (!arr) are global array feeds
# already carried by the canonical market connection — never duplicated.
STREAMS_PER_SYMBOL = 3

DEFAULT_BUDGET: Dict[str, Any] = {
    "max_hot_slots": 3,
    "max_total_streams": 60,
    "max_streams_per_connection": 50,
    "max_connections": 6,
    "promotion_interval_seconds": 600,
    "min_dwell_seconds": 1800,
    "demotion_cooldown_seconds": 3600,
    "max_discovery_age_seconds": 1800,
    "demote_after_missed_scans": 2,
    "max_hot_reconnects_per_hour": 10,
}


def movement_key(change_24h_pct: Optional[float],
                 quote_volume_24h: Optional[float],
                 symbol: str) -> tuple:
    """Deterministic movement rank: |24h%| desc, volume desc, symbol asc.

    Candidates without a 24h change cannot express movement and sort last;
    missing volume sorts after measured volume (never zero-filled).
    """
    return (change_24h_pct is None,
            -(abs(change_24h_pct) if change_24h_pct is not None else 0.0),
            quote_volume_24h is None,
            -(quote_volume_24h if quote_volume_24h is not None else 0.0),
            symbol)


def streams_for_symbols(symbols: Tuple[str, ...]) -> int:
    """Deep-observation streams needed for a symbol set (deterministic)."""
    return len({str(s).upper() for s in symbols}) * STREAMS_PER_SYMBOL


class UniverseManager:
    """Bounded HOT selection + per-symbol lifecycle (no I/O, no threads)."""

    def __init__(self, core: Tuple[str, ...] = (),
                 budget: Optional[Dict[str, Any]] = None) -> None:
        self.core = tuple(s.upper() for s in core)
        cfg = dict(DEFAULT_BUDGET)
        if budget:
            cfg.update(budget)
        self.budget = cfg
        # symbol -> lifecycle record (HOT-tracked symbols only; CORE and
        # never-seen symbols are derived, never stored here).
        self._symbols: Dict[str, Dict[str, Any]] = {}
        self.promotions_total = 0
        self.demotions_total = 0
        self.failed_promotions = 0
        self.budget_refusals = 0
        self.last_update_ms: Optional[int] = None

    # -- queries --------------------------------------------------------

    def desired_hot(self) -> Tuple[str, ...]:
        """Symbols that should hold deep subscriptions right now."""
        live = [s for s, r in self._symbols.items()
                if r["state"] in (ST_PROMOTION_PENDING, ST_SUBSCRIBING,
                                  ST_WARMING, ST_LIVE, ST_DEGRADED)]
        # Deterministic rank order among desired (movement rank, then name).
        return tuple(sorted(live))

    def states_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Lifecycle records for dashboard/summary (copies, read-only)."""
        return {s: dict(r) for s, r in sorted(self._symbols.items())}

    def slot_usage(self, core_count: Optional[int] = None) -> Dict[str, Any]:
        """Slot/stream budget accounting (fail-closed inputs for update)."""
        hot = self.desired_hot()
        core_n = len(self.core) if core_count is None else int(core_count)
        hot_streams = streams_for_symbols(hot)
        return {
            "core_symbols": list(self.core),
            "core_count": core_n,
            "hot_desired": list(hot),
            "hot_used": len(hot),
            "hot_free": max(int(self.budget["max_hot_slots"]) - len(hot), 0),
            "hot_streams": hot_streams,
            "total_streams": hot_streams,  # caller adds canonical streams
            "max_hot_slots": int(self.budget["max_hot_slots"]),
            "max_total_streams": int(self.budget["max_total_streams"]),
        }

    # -- update ---------------------------------------------------------

    def update(self, candidates: Dict[str, Dict[str, Any]],
               hot_proposals: List[str],
               now_ms: int,
               scan_ms: Optional[int] = None,
               transport_ok: bool = True) -> Dict[str, Any]:
        """One deterministic lifecycle step. Returns decisions + events.

        candidates: symbol -> {eligible, change_24h_pct, quote_volume_24h,
          ticker_close_ms}. hot_proposals: hysteresis-filtered rank order
          from discovery select_hot (may be empty). transport_ok=False
          freezes promotions (fail closed) but lets demotions proceed.
        """
        now = int(now_ms)
        self.last_update_ms = now
        scan = int(scan_ms) if scan_ms is not None else now
        cfg = self.budget
        decisions: Dict[str, Any] = {"promote": [], "demote": [],
                                     "events": [], "refused": []}
        core_set = set(self.core)

        # 1. Drop records for symbols that are now CORE (protected; a HOT
        #    record must never shadow a CORE subscription).
        for symbol in [s for s in self._symbols if s in core_set]:
            self._symbols.pop(symbol, None)
            decisions["events"].append(
                {"kind": "core_protected", "symbol": symbol,
                 "reason": "became CORE; HOT record retired"})

        # 2. Score eligible fresh proposals deterministically.
        ranked: List[Tuple[tuple, str]] = []
        for symbol in hot_proposals:
            sym = str(symbol).upper()
            if sym in core_set:
                continue
            info = candidates.get(sym, {})
            if not info.get("eligible"):
                continue
            close_ms = info.get("ticker_close_ms")
            age_ok = (close_ms is None or
                      (scan - int(close_ms)) <= int(
                          cfg["max_discovery_age_seconds"]) * 1000)
            if not age_ok:
                decisions["events"].append(
                    {"kind": "skipped", "symbol": sym,
                     "reason": "discovery data too old"})
                continue
            ranked.append((movement_key(info.get("change_24h_pct"),
                                        info.get("quote_volume_24h"), sym),
                          sym))
        ranked.sort(key=lambda item: item[0])
        ranked_symbols = [sym for _, sym in ranked]

        # 3. Demotions: ineligible, vanished, rank-decayed, or dwell-expired.
        desired_now = set(self.desired_hot())
        for symbol in sorted(desired_now):
            rec = self._symbols[symbol]
            info = candidates.get(symbol, {})
            reason: Optional[str] = None
            if not info.get("eligible"):
                reason = "ineligible"
            elif symbol not in ranked_symbols:
                rec["missed_scans"] = int(rec.get("missed_scans", 0)) + 1
                if rec["missed_scans"] >= int(
                        cfg["demote_after_missed_scans"]):
                    reason = ("rank_decay_%d_scans"
                              % rec["missed_scans"])
            else:
                rec["missed_scans"] = 0
            if reason is not None and rec["state"] not in (
                    ST_DEMOTION_PENDING, ST_UNSUBSCRIBING):
                live_since = rec.get("live_since_ms")
                if reason != "ineligible" and live_since is not None and (
                        now - int(live_since) < int(
                            cfg["min_dwell_seconds"]) * 1000):
                    rec["missed_scans"] = 0
                    decisions["events"].append(
                        {"kind": "dwell_hold", "symbol": symbol,
                         "reason": "minimum dwell not served"})
                    continue
                rec["state"] = ST_DEMOTION_PENDING
                rec["since_ms"] = now
                rec["reason"] = reason
                decisions["events"].append(
                    {"kind": "demote_decided", "symbol": symbol,
                     "reason": reason})
        # Finalize demotions promptly once decided: the pending state frees
        # reconnect budgets without delay (dwell was enforced above on LIVE
        # tenure, so no rotation on small ranking changes can occur).
        for symbol in sorted(desired_now):
            rec = self._symbols.get(symbol)
            if rec is None or rec["state"] != ST_DEMOTION_PENDING:
                continue
            rec["state"] = ST_UNSUBSCRIBING
            rec["since_ms"] = now
            decisions["demote"].append(symbol)
            self.demotions_total += 1
            decisions["events"].append(
                {"kind": "demoted", "symbol": symbol,
                 "reason": rec.get("reason", "")})

        # 4. Promotions: top-ranked fresh proposals into free slots.
        if transport_ok:
            incumbent = {s for s in self.desired_hot()
                         if self._symbols.get(s, {}).get("state")
                         not in (ST_DEMOTION_PENDING, ST_UNSUBSCRIBING)}
            free = int(cfg["max_hot_slots"]) - len(incumbent)
            for _, sym in ranked:
                if free <= 0:
                    break
                if sym in incumbent:
                    continue
                rec = self._symbols.get(sym)
                if rec is not None and rec["state"] in (
                        ST_PROMOTION_PENDING, ST_SUBSCRIBING, ST_WARMING,
                        ST_LIVE, ST_DEGRADED):
                    continue
                cooled_until = int(rec.get("cooled_until_ms", 0)) \
                    if rec else 0
                if now < cooled_until:
                    continue
                # Budget gate (fail closed): streams + connections.
                trial = tuple(sorted(set(incumbent) | {sym}))
                if not self._budget_ok(trial):
                    self.budget_refusals += 1
                    decisions["refused"].append(sym)
                    decisions["events"].append(
                        {"kind": "refused", "symbol": sym,
                         "reason": "stream/connection budget"})
                    continue
                self._symbols[sym] = {
                    "tier": "HOT", "state": ST_PROMOTION_PENDING,
                    "since_ms": now, "reason": "ranked proposal",
                    "missed_scans": 0, "live_since_ms": None,
                    "first_data_ms": None,
                    "cooled_until_ms": cooled_until,
                    "errors": 0, "last_error": None,
                }
                incumbent.add(sym)
                free -= 1
                self.promotions_total += 1
                decisions["promote"].append(sym)
                decisions["events"].append(
                    {"kind": "promoted", "symbol": sym,
                     "reason": "ranked proposal"})
        else:
            decisions["events"].append(
                {"kind": "frozen", "symbol": "*",
                 "reason": "transport degraded; promotions frozen"})

        # 5. Cleanup fully-retired records (post-unsubscribe).
        for symbol in [s for s, r in self._symbols.items()
                       if r["state"] == ST_UNSUBSCRIBING
                       and s not in decisions["demote"]]:
            # Transport confirms via confirm_unsubscribed(); without it the
            # record ages out after one more update to avoid ghosts.
            if now - int(r.get("since_ms", now)) > 3_600_000:
                self._symbols.pop(symbol, None)
        return decisions

    def _budget_ok(self, desired: Tuple[str, ...]) -> bool:
        """Fail-closed budget gate for a candidate desired set."""
        cfg = self.budget
        if len(desired) > int(cfg["max_hot_slots"]):
            return False
        hot_streams = streams_for_symbols(desired)
        # Canonical CORE streams: 3 symbols x (bookTicker+depth+aggTrade)
        # + 2 global array feeds, plus 2 HOT connections when active.
        canonical = len(self.core) * 3 + 2
        total = canonical + hot_streams + (2 if desired else 0)
        if total > int(cfg["max_total_streams"]):
            return False
        conns = 2 + (2 if desired else 0)
        if conns > int(cfg["max_connections"]):
            return False
        per_conn = max(hot_streams // 2 if desired else 0,
                       len(desired) * 2)
        if per_conn > int(cfg["max_streams_per_connection"]):
            return False
        return True

    # -- transport callbacks (called by the probe, never by selection) ---

    def confirm_subscribed(self, symbols: List[str], now_ms: int) -> None:
        """Transport reports streams actually flowing for these symbols."""
        now = int(now_ms)
        for symbol in symbols:
            sym = str(symbol).upper()
            rec = self._symbols.get(sym)
            if rec is None:
                continue
            if rec["state"] in (ST_PROMOTION_PENDING, ST_SUBSCRIBING):
                rec["state"] = ST_SUBSCRIBING
                rec["since_ms"] = now
                rec["reason"] = "streams requested"

    def note_first_data(self, symbol: str, now_ms: int) -> None:
        """First valid post-skew message observed for a HOT symbol."""
        rec = self._symbols.get(str(symbol).upper())
        if rec is None:
            return
        now = int(now_ms)
        if rec.get("first_data_ms") is None:
            rec["first_data_ms"] = now
        if rec["state"] in (ST_PROMOTION_PENDING, ST_SUBSCRIBING):
            rec["state"] = ST_WARMING
            rec["since_ms"] = now
            rec["reason"] = "first data flowing; warming per feature"

    def note_live(self, symbol: str, now_ms: int) -> None:
        """Minimum deep data present (mark + trade + depth observed)."""
        rec = self._symbols.get(str(symbol).upper())
        if rec is None:
            return
        if rec["state"] in (ST_PROMOTION_PENDING, ST_SUBSCRIBING,
                            ST_WARMING):
            rec["state"] = ST_LIVE
            rec["since_ms"] = int(now_ms)
            rec["live_since_ms"] = int(now_ms)
            rec["reason"] = "minimum deep data present"

    def note_degraded(self, symbol: str, reason: str, now_ms: int) -> None:
        rec = self._symbols.get(str(symbol).upper())
        if rec is None:
            return
        if rec["state"] in (ST_WARMING, ST_LIVE):
            rec["state"] = ST_DEGRADED
            rec["since_ms"] = int(now_ms)
            rec["reason"] = str(reason)[:160]
            rec["errors"] = int(rec.get("errors", 0)) + 1
            rec["last_error"] = str(reason)[:160]

    def note_failure(self, symbol: str, reason: str, now_ms: int) -> None:
        """Partial subscription failure / timeout: back to pending + count."""
        rec = self._symbols.get(str(symbol).upper())
        if rec is None:
            return
        rec["errors"] = int(rec.get("errors", 0)) + 1
        rec["last_error"] = str(reason)[:160]
        if rec["state"] in (ST_PROMOTION_PENDING, ST_SUBSCRIBING,
                            ST_WARMING):
            rec["state"] = ST_PROMOTION_PENDING
            rec["since_ms"] = int(now_ms)
            rec["reason"] = "retry: " + str(reason)[:120]
            self.failed_promotions += 1

    def confirm_unsubscribed(self, symbols: List[str], now_ms: int) -> None:
        """Transport confirms removal: retire records, start cooldowns."""
        now = int(now_ms)
        for symbol in symbols:
            sym = str(symbol).upper()
            rec = self._symbols.pop(sym, None)
            if rec is None:
                continue
            self._symbols[sym] = {
                "tier": "HOT", "state": ST_UNKNOWN,
                "since_ms": now, "reason": rec.get("reason", ""),
                "missed_scans": 0, "live_since_ms": None,
                "first_data_ms": None,
                "cooled_until_ms": now + int(
                    self.budget["demotion_cooldown_seconds"]) * 1000,
                "errors": int(rec.get("errors", 0)), "last_error": None,
            }

    def stats(self) -> Dict[str, Any]:
        states: Dict[str, int] = {}
        for rec in self._symbols.values():
            states[rec["state"]] = states.get(rec["state"], 0) + 1
        return {"version": UNIVERSE_VERSION, "core": list(self.core),
                "desired_hot": list(self.desired_hot()),
                "states": states,
                "promotions_total": self.promotions_total,
                "demotions_total": self.demotions_total,
                "failed_promotions": self.failed_promotions,
                "budget_refusals": self.budget_refusals,
                "budget": {k: self.budget[k] for k in
                           ("max_hot_slots", "max_total_streams",
                            "max_streams_per_connection",
                            "max_connections")},
                "last_update_ms": self.last_update_ms}
