"""Offline backtest preparation (research mechanics only, v4.2).

Pure, deterministic, stdlib-only replay over injected candles + study
events. No network, no live modules, no database access, no wall clock,
no randomness. Entry/exit rules are STRUCTURAL MECHANICS placeholders —
NOT validated signals; any result on fixtures is a MECHANICS SMOKE proof,
never performance. The v2 causality/closure guarantees refuted by review
(R1/R2) are WITHDRAWN and replaced below; the motor is NOT claimed
causally verified — only covered by the regression battery.

v4.1 revision (2026-10-13): exit commissions on exit value (not symmetric
halves); settlement exposure is current quantity x causal settlement mark
with data-step freshness tiers (fresh/proxy/stale); per-position funding
accounting completeness; config_hash carries the engine version so v4 and
v4.1 result hashes never compare equal. 2026-10-14 causality fix: the data
step and settlement marks use the candle prefix known at exit_ms — candles
printed later never reclassify earlier settlements (R8 regression). Flat-price fixture amounts from v4
are unchanged; legacy totals still include open marks (never realized).

v4.2 revision (2026-10-14, review 4f1d92e): per-SETTLEMENT causality. The
exit_ms prefix was still retrospective INSIDE the holding: on 0/12/24/36h
data, inserting 21/22/23h candles dragged the shared median step and
flipped the 16h/20h settlements from proxy to stale (3 -> 1). Each
settlement now computes its data step AND its mark from the candle prefix
known at its own settlement_ms (R9 regression beside R8). Behavior change
is versioned: ENGINE_VERSION is backtest-offline/v4.2, so v4.1 and v4.2
result/config hashes never compare equal.

Temporal availability contract (v4; v3 rules kept, funding reworked):
- A candle's OPEN is known at its open_time. Its high/low/close are known
  ONLY at its close_time (the next same-symbol open_time, or UNKNOWN for
  the last candle and across gaps — a following open never proves how long
  the prior candle lasted). No intra-candle timing is ever attributed.
- Stops, MFE/MAE and exits consume a candle's range ONLY when its close is
  known AND within the window (close_time <= horizon_end). Using a future
  or unknown low/high and then patching exit_ms does NOT cure lookahead.
- Gap-first ordering: an existing position resolves against the KNOWN open
  before any new fill at that candle. An open through the stop exits AT
  the open (first available price); a later recovery cannot upgrade it. A
  stopped position cancels its remainder; new fills happen only while the
  position stays open and the window is open.
- Range stops (open on the safe side) fill AT the stop price with knowledge
  time = close_time. MFE/MAE credit only demonstrated prints: prior candles
  plus the current OPEN (observed while holding); the candle's favorable
  extreme is excluded (order vs the exit is unknown). The exit move itself
  always feeds MAE.
- Horizon vs data end: candles past the window contribute nothing (no
  fills, no stops, no metrics). If data extends past the window, the rule
  closes the position marked at the last knowledge (reason "horizon"). If
  the data ends first, the position is OPEN at data end: marked at the
  last known price/time with reason "open_at_end" (a MARK, never an
  executed exit — no invented duration, funding, close, or capacity
  release beyond knowledge).
- Quantity accounting: filled_qty, filled_cost (raw), average entry =
  cost/qty. gross_pnl is pure price P&L on filled qty; friction =
  spread/slip drag + fees + signed funding; net = gross - friction.
- Realized vs open vs marks (additive split; legacy totals UNCHANGED and
  still include open marks — never cite them as realized): trades closed
  inside the window (exit_executed) feed total_net_realized,
  expectancy_net_realized, equity_curve_realized (effective-close-time
  order) and max_drawdown_realized. Trades with reason "open_at_end" are
  listed under open_positions with their mark (mark_ms/mark_px) and
  contribute NOTHING to realized metrics; their exit-leg costs sit in
  costs_exit_hypothetical (totaled separately), entry-leg costs in
  costs_executed.
- Funding (v4.2): per-SETTLEMENT accounting over an explicit versioned
  calendar — never a global interval swap. Each settlement carries its own
  timestamp and realized rate; a settlement applies iff
  entry_ms <= settlement_ms < exit_ms (boundary convention, tested both
  edges). Exposure at settlement = CURRENT QUANTITY x SETTLEMENT MARK
  (causal candle open covering the settlement; a settlement with no
  covering candle is excluded as unknown, never zero-priced). Mark
   freshness is judged against the DATA step, never the funding cadence
   (v4.2: step AND mark per settlement, from the prefix known at that
   settlement_ms — R9):
  age 0 = fresh (observed), within one data step = proxy (settles,
  flagged with its age), older = stale (excluded as unknown). Sign by
  direction (LONG pays / SHORT receives at a positive rate). Every settled
  event records contract identity (trade symbol + calendar symbol/
  version/source; UNKNOWN when absent, never invented). Exact duplicate
  settlements (same ms AND rate) are deduped and counted; same-ms
  different-rate conflicts REJECT the run. A symbol-pinned calendar
  settles ONE contract (foreign symbols rejected). Completeness is never
  inferred from first/last timestamps: interior gaps against the nominal
  cadence are reported (gap_ms), and without a nominal cadence
  completeness is UNKNOWN. Accounting completeness is PER POSITION
  (all in-window settlements fresh-or-proxy, no gap overlap, no
  uncovered holding) — calendar-complete never implies it. Holding time
  OUTSIDE the calendar's listed span [first, last] is reported as
  funding_uncovered_ms capped at the holding (truncated head/tail
  = unknown cadence continuity, never invented as zero-rate);
  inter-settlement spans inside the span are cadence (no payment due). `funding_estimated_bps`, when set, is CONTEXT ONLY (e.g. a
  forecast shown on a dashboard) and never enters accounting — estimated
  vs realized rates are different quantities. Without a calendar, the
  legacy interval fallback applies (unchanged math, labeled as such, with
  an explicit synthetic marker event).
- Concurrency is enforced over signal-to-exit intervals (capacity commits
  at event time), per max_concurrent; simultaneous events compete
  deterministically in time order.
- Events whose (family, rules_version) differ from config are SKIPPED and
  counted (never silently pooled).
- Unsupported knobs (latency_ms, tick_size, lot_step, min_notional_usdt)
  REJECT the run with ValueError; they are never simulated as supported.
- Drawdown is REALIZED-only (closed-trade net equity); mark-to-market is
  explicitly NOT modeled. dev/OOS splits by event time (documented;
  cutoff_ms reported but credited with no purging power).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

ENGINE_VERSION = "backtest-offline/v4.2"
FUNDING_INTERVAL_MS = 8 * 3600 * 1000


@dataclass(frozen=True)
class FundingSettlement:
    """One realized funding settlement: timestamp + rate actually paid."""
    settlement_ms: int
    rate_bps: float


@dataclass(frozen=True)
class FundingCalendar:
    """Versioned settlement calendar (per-symbol venue reality, injected).

    NOT a global interval: each settlement carries its own timestamp and
    realized rate (4h cadences, 8h cadences, irregular histories all fit).
    `source` names provenance ("synthetic-fixture",
    "exchange-funding-history", ...); `interval_ms` is an informational
    nominal cadence only, never used for accounting.
    `symbol` names the contract the calendar was pulled for (None =
    UNKNOWN, never invented: events record it verbatim).
    """

    version: str = "synthetic/v1"
    source: str = "synthetic-fixture"
    interval_ms: Optional[int] = None
    settlements: Tuple[FundingSettlement, ...] = ()
    symbol: Optional[str] = None

    def calendar_hash(self) -> str:
        payload = json.dumps({
            "version": self.version, "source": self.source,
            "interval_ms": self.interval_ms, "symbol": self.symbol,
            "settlements": sorted((s.settlement_ms, s.rate_bps)
                                  for s in self.settlements),
        }, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def normalized(self) -> Tuple[Tuple[FundingSettlement, ...], int]:
        """Deduped settlements + exact-duplicate count.

        Exact duplicates (same timestamp AND rate) are rejected down to one
        (double-payment protection). Same timestamp with a DIFFERENT rate
        is a conflict: raises ValueError (never averaged silently).
        """
        seen: Dict[Tuple[int, float], FundingSettlement] = {}
        duplicates = 0
        by_time: Dict[int, float] = {}
        for s in sorted(self.settlements, key=lambda s: s.settlement_ms):
            key = (s.settlement_ms, s.rate_bps)
            if key in seen:
                duplicates += 1
                continue
            if (s.settlement_ms in by_time
                    and by_time[s.settlement_ms] != s.rate_bps):
                raise ValueError(
                    "conflicting duplicate funding settlement at ms=%d: "
                    "%r vs %r bps (calendar %s)" % (
                        s.settlement_ms, by_time[s.settlement_ms],
                        s.rate_bps, self.version))
            seen[key] = s
            by_time[s.settlement_ms] = s.rate_bps
        ordered = tuple(seen[k] for k in sorted(seen))
        return ordered, duplicates

    def assess(self) -> Dict[str, Any]:
        """Completeness assessment (never inferred from first/last only).

        Interior gaps are detected against the nominal cadence: a span
        between consecutive settlements wider than 1.5x `interval_ms` is a
        GAP (unknown continuity inside the span, even though listed
        settlements still settle). Without a nominal cadence
        (`interval_ms is None`) interior completeness is UNKNOWN.
        """
        ordered, _ = self.normalized()
        gaps = []
        if self.interval_ms:
            nominal = int(self.interval_ms)
            for a, b in zip(ordered, ordered[1:]):
                if b.settlement_ms - a.settlement_ms > 1.5 * nominal:
                    gaps.append({"from_ms": a.settlement_ms,
                                 "to_ms": b.settlement_ms})
            complete = bool(ordered) and not gaps
            basis = ("nominal-cadence-no-gaps" if complete
                     else ("empty-calendar" if not ordered
                           else "interior-gaps-present"))
        else:
            complete = False
            basis = "unknown-basis (no nominal cadence; first/last prove nothing)"
        return {"complete": complete, "completeness_basis": basis,
                "gaps": gaps}


@dataclass(frozen=True)
class StudyEvent:
    symbol: str
    event_time_ms: int
    direction: str  # "LONG" | "SHORT"
    reference_price: float
    family: str = "H1"
    rules_version: str = "H1-v1"


@dataclass(frozen=True)
class Candle:
    symbol: str
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class BacktestConfig:
    family: str = "H1"
    rules_version: str = "H1-v1"
    exit_horizon_ms: int = 3600 * 1000
    stop_distance_pct: float = 0.5
    notional_usdt: float = 1000.0
    fee_bps: float = 5.0
    funding_8h_bps: float = 1.0
    # Explicit settlement calendar (v4). When None, the legacy interval
    # fallback applies (full 8h intervals from entry at funding_8h_bps).
    funding_calendar: Optional[FundingCalendar] = None
    # Estimated future rate: CONTEXT ONLY (e.g. dashboard forecast display).
    # Never enters accounting; only realized calendar rates settle.
    funding_estimated_bps: Optional[float] = None
    spread_bps: float = 1.0
    slippage_bps: float = 2.0
    cost_scale: float = 1.0
    max_concurrent: int = 1
    # Fill at most this notional per candle open; remainder spills to the
    # next candles (deterministic partial-fill mechanics). None = full.
    partial_fill_notional_cap: Optional[float] = None
    # Unsupported knobs: any non-None value REJECTS the run (P1 review).
    latency_ms: Optional[float] = None
    tick_size: Optional[float] = None
    lot_step: Optional[float] = None
    min_notional_usdt: Optional[float] = None

    def config_hash(self) -> str:
        # Versioned implementation identity: the engine version joins the
        # payload so a v4/v4.1/v4.2 result hash never equals another
        # version's hash even with identical knobs (fee semantics changed
        # in v4.1, per-settlement causality in v4.2).
        payload = json.dumps({"engine_version": ENGINE_VERSION,
                              "config": self.__dict__},
                             sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


LIMITATIONS = [
    "no-latency-model",
    "no-tick-lot-rounding",
    "no-min-notional-gate",
    "realized-only-drawdown",
    "funding-calendar-or-interval-fallback",
    "oos-split-by-event-time",
]


def _settlement_mark(series: List[Candle],
                      settlement_ms: int) -> Tuple[Optional[float],
                                                  Optional[int]]:
    """Causal (mark, age_ms) at settlement: open of the candle holding it.

    The open is known exactly at its open_time, so it is usable at any
    settlement_ms >= open_time. Returns (None, None) when no candle covers
    the settlement (unknown mark: never invented from thin air).
    """
    mark: Optional[float] = None
    age: Optional[int] = None
    for c in series:
        if c.open_time_ms <= settlement_ms:
            mark = c.open
            age = settlement_ms - c.open_time_ms
        else:
            break
    return mark, age


def _data_step_ms(series: List[Candle]) -> Optional[int]:
    """Nominal data cadence: median positive open_time step, or None."""
    diffs = sorted(b.open_time_ms - a.open_time_ms
                   for a, b in zip(series, series[1:])
                   if b.open_time_ms > a.open_time_ms)
    if not diffs:
        return None
    return diffs[len(diffs) // 2]


def _mark_freshness(age_ms: int,
                    data_step_ms: Optional[int]) -> str:
    """Freshness judged against the DATA cadence, never funding cadence.

    - age 0: "fresh" (the settlement prints exactly on a candle open —
      an observed print, not a proxy).
    - 0 < age <= data step: "proxy" (the best causal print, explicitly
      aged; settles with its age recorded).
    - older, or no data step to judge by: "stale" (excluded as unknown).
    A 4h-old print on 12h data is a PROXY, never "fresh because the
    funding cadence is 4h".
    """
    if age_ms <= 0:
        return "fresh"
    if data_step_ms is None:
        return "stale"
    return "proxy" if age_ms <= data_step_ms else "stale"


def _overlap_ms(lo: int, hi: int, spans: List[Tuple[int, int]]) -> int:
    total = 0
    for (a, b) in spans:
        total += max(0, min(hi, b) - max(lo, a))
    return total


def _funding_for_trade(side: str,
                       fill_ledger: List[Tuple[int, float, float]],
                       entry_ms: int, exit_ms: int,
                       cfg: BacktestConfig, symbol: str,
                       series: List[Candle]) -> Tuple[float, list, int, int,
                                                     int, str, dict]:
    """Returns (total, events, uncovered_ms, gap_ms, unknown, model, meta).

    Calendar path: exposure is CURRENT QUANTITY x SETTLEMENT MARK
    (causal candle open at the settlement, never entry-frozen cost), signed
    by direction, per settlement with entry_ms <= t < exit_ms. Every event
    carries contract identity (trade symbol + calendar symbol/version/
    source, UNKNOWN when absent, never invented). Settlements with no
    covering candle are EXCLUDED as unknown (counted, never zero-priced).
    Holding outside the calendar span is uncovered (unknown, never zero);
    holding inside detected interior gaps is reported as gap_ms.
    Fallback path: legacy full-interval math, unchanged, with an explicit
    synthetic marker event (no venue fidelity claimed).
    """
    sign = 1.0 if side == "LONG" else -1.0
    scale = cfg.cost_scale
    if cfg.funding_calendar is None:
        filled_notional = sum(cost for (_, cost, _) in fill_ledger)
        n = max(0, (exit_ms - entry_ms) // FUNDING_INTERVAL_MS)
        total = sign * filled_notional * cfg.funding_8h_bps / \
            10_000.0 * scale * n
        marker = [{"basis": "synthetic-fallback",
                   "detail": "legacy full-interval math; no venue calendar",
                   "intervals": n, "symbol": symbol}]
        meta = {"accounting_complete": False,
                "accounting_basis": "synthetic-fallback (no venue calendar)"}
        return total, marker, 0, 0, 0, "interval-fallback", meta
    cal = cfg.funding_calendar
    ordered, _ = cal.normalized()  # conflicts raise here, before any math
    assessment = cal.assess()
    gap_spans = [(g["from_ms"], g["to_ms"]) for g in assessment["gaps"]]
    # CAUSALITY v4.2 (2026-10-14, review 4f1d92e): cadence AND availability
    # are computed per settlement from the candle prefix known at THAT
    # settlement_ms — never from the holding's full prefix. The exit_ms
    # prefix (v4.1 fix, R8) was still retrospective inside the holding: on
    # 0/12/24/36h data, inserting 21/22/23h candles dragged the shared
    # median step and flipped the 16h/20h settlements proxy->stale (3->1).
    # Later candles — even inside the holding — never move earlier funding.
    by_open = sorted(series, key=lambda c: c.open_time_ms)
    opens = [c.open_time_ms for c in by_open]

    def _prefix(ms: int) -> list:
        import bisect
        return by_open[:bisect.bisect_right(opens, ms)] or series
    total = 0.0
    events: list = []
    unknown = 0
    for s in ordered:
        if entry_ms <= s.settlement_ms < exit_ms:
            held_cost = sum(cost for (t, cost, _) in fill_ledger
                            if t <= s.settlement_ms)
            held_qty = sum(qty for (t, _, qty) in fill_ledger
                           if t <= s.settlement_ms)
            prefix = _prefix(s.settlement_ms)
            mark, age = _settlement_mark(prefix, s.settlement_ms)
            data_step = _data_step_ms(prefix)
            if mark is None or age is None:
                unknown += 1
                events.append({"basis": "unknown-excluded",
                               "settlement_ms": s.settlement_ms,
                               "rate_bps": s.rate_bps,
                               "reason": "no covering candle: mark UNKNOWN",
                               "symbol": symbol,
                               "calendar_symbol": cal.symbol,
                               "calendar_version": cal.version,
                               "calendar_source": cal.source})
                continue
            freshness = _mark_freshness(age, data_step)
            if freshness == "stale":
                unknown += 1
                events.append({"basis": "unknown-excluded",
                               "settlement_ms": s.settlement_ms,
                               "rate_bps": s.rate_bps,
                               "reason": "stale mark proxy: age_ms=%d "
                               "exceeds data step %s" % (age, data_step),
                               "mark_age_ms": age,
                               "data_step_ms": data_step,
                               "symbol": symbol,
                               "calendar_symbol": cal.symbol,
                               "calendar_version": cal.version,
                               "calendar_source": cal.source})
                continue
            amount = sign * held_qty * mark * s.rate_bps / 10_000.0 * scale
            total += amount
            events.append({"basis": "settled",
                           "settlement_ms": s.settlement_ms,
                           "rate_bps": s.rate_bps,
                           "symbol": symbol,
                           "calendar_symbol": cal.symbol,
                           "calendar_version": cal.version,
                           "calendar_source": cal.source,
                           "held_qty": held_qty, "held_cost": held_cost,
                           "settlement_mark_px": mark,
                           "mark_source": "candle-open",
                           "mark_age_ms": age,
                           "data_step_ms": data_step,
                           "mark_freshness": freshness,
                           "amount": amount})
    # UNKNOWN coverage, never zero-invented: holding time outside the
    # calendar's listed span [first, last] is silent about cadence
    # continuity (truncated head/tail). Inter-settlement spans inside the
    # span are cadence (no payment due), not unknown — except detected
    # interior gaps, reported separately as gap_ms. Unknown time OF THE
    # HOLDING never exceeds the holding itself (capped at exit-entry).
    if ordered:
        span_lo = ordered[0].settlement_ms
        span_hi = ordered[-1].settlement_ms
        raw = max(0, span_lo - entry_ms) + max(0, exit_ms - span_hi)
        uncovered = min(raw, max(0, exit_ms - entry_ms))
    else:
        uncovered = max(0, exit_ms - entry_ms)
    gap_ms = _overlap_ms(entry_ms, exit_ms, gap_spans)
    # Accounting completeness is PER POSITION, never calendar-level:
    # every in-window settlement settled on a fresh-or-proxy mark, no
    # interior gap overlap, no uncovered holding. A continuous calendar
    # (complete=True) with one stale mark is accounting-INCOMPLETE.
    reasons = []
    if unknown:
        reasons.append("%d unknown-excluded settlement(s)" % unknown)
    if gap_ms:
        reasons.append("interior-gap overlap %dms" % gap_ms)
    if uncovered:
        reasons.append("uncovered holding %dms" % uncovered)
    meta = {"calendar_complete": assessment["complete"],
            "completeness_basis": assessment["completeness_basis"],
            "calendar_gaps": assessment["gaps"],
            "accounting_complete": not reasons,
            "accounting_basis": ("fully settled, no gaps, no uncovered "
                                 "holding" if not reasons
                                 else "; ".join(reasons))}
    return total, events, uncovered, gap_ms, unknown, "settlement-calendar", meta


def _check_supported(config: BacktestConfig) -> None:
    for knob in ("latency_ms", "tick_size", "lot_step",
                 "min_notional_usdt"):
        if getattr(config, knob) is not None:
            raise ValueError("unsupported backtest knob: %s (not modeled, "
                             "refusing to simulate partial support)" % knob)
    if config.max_concurrent is None or int(config.max_concurrent) < 1:
        raise ValueError("max_concurrent must be >= 1")


def _drag_rate(cfg: BacktestConfig) -> float:
    return (cfg.spread_bps + cfg.slippage_bps) * cfg.cost_scale / 10_000.0


def split_by_time(events: List[StudyEvent],
                  cutoff_ms: int) -> Dict[str, List[StudyEvent]]:
    ordered = sorted(events, key=lambda e: (e.event_time_ms, e.symbol))
    return {
        "dev": [e for e in ordered if e.event_time_ms < cutoff_ms],
        "oos": [e for e in ordered if e.event_time_ms >= cutoff_ms],
    }


def input_hash(events: List[StudyEvent], candles: List[Candle]) -> str:
    ev_tuples = sorted((e.symbol, e.event_time_ms, e.direction,
                        e.reference_price, e.family, e.rules_version)
                       for e in events)
    c_tuples = sorted((c.symbol, c.open_time_ms, c.open, c.high, c.low,
                       c.close) for c in candles)
    payload = json.dumps({"events": ev_tuples, "candles": c_tuples},
                         sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _close_times(series: List[Candle]) -> List[Optional[int]]:
    """Knowledge time of each candle's high/low/close (next open or None)."""
    return [series[i + 1].open_time_ms if i + 1 < len(series) else None
            for i in range(len(series))]


def run_backtest(events: List[StudyEvent], candles: List[Candle],
                 config: BacktestConfig,
                 dataset_id: str = "synthetic-fixture",
                 segment: str = "dev") -> Dict[str, Any]:
    """Chronological causal replay. Versioned, reproducible result dict."""
    _check_supported(config)
    ordered_events = sorted(events, key=lambda e: (e.event_time_ms, e.symbol))
    by_symbol: Dict[str, List[Candle]] = {}
    for c in sorted(candles, key=lambda c: (c.symbol, c.open_time_ms)):
        by_symbol.setdefault(c.symbol, []).append(c)
    closes: Dict[str, List[Optional[int]]] = {
        s: _close_times(series) for s, series in by_symbol.items()}

    trades: List[Dict[str, Any]] = []
    skipped_overlap = 0
    n_expired = 0
    n_mismatched = 0
    open_intervals: List[Tuple[int, int]] = []

    # Fail fast on calendar conflicts (same ms, different rates) before
    # any replay math. Exact duplicates are deduped per trade below.
    cal_duplicates = 0
    cal_assessment: Dict[str, Any] = {}
    if config.funding_calendar is not None:
        _, cal_duplicates = config.funding_calendar.normalized()
        cal_assessment = config.funding_calendar.assess()
        # A symbol-pinned calendar settles ONE contract only: replaying a
        # foreign symbol against it would silently misattribute venue
        # reality, so the run is REJECTED (fail-closed, never coerced).
        if config.funding_calendar.symbol is not None:
            foreign = sorted({e.symbol for e in ordered_events
                              if e.symbol != config.funding_calendar.symbol})
            if foreign:
                raise ValueError(
                    "funding calendar for %s cannot settle %s "
                    "(calendar %s)" % (
                        config.funding_calendar.symbol, foreign,
                        config.funding_calendar.version))

    for ev in ordered_events:
        if ev.direction not in ("LONG", "SHORT"):
            continue
        if (ev.family, ev.rules_version) != (config.family,
                                             config.rules_version):
            n_mismatched += 1
            continue
        concurrent = sum(1 for (s, e) in open_intervals
                         if s <= ev.event_time_ms < e)
        if concurrent >= int(config.max_concurrent):
            skipped_overlap += 1
            continue
        series = by_symbol.get(ev.symbol, [])
        if not series:
            n_expired += 1
            continue
        horizon_end = ev.event_time_ms + config.exit_horizon_ms
        fill_idx = [i for i, c in enumerate(series)
                    if c.open_time_ms > ev.event_time_ms]
        if not fill_idx or series[fill_idx[0]].open_time_ms > horizon_end:
            n_expired += 1  # window closed before any fill was possible
            continue

        is_long = ev.direction == "LONG"
        drag = _drag_rate(config)
        filled_qty = 0.0
        filled_cost_raw = 0.0
        spread_slip = 0.0
        entry_spread_slip = 0.0
        n_fills = 0
        remaining = config.notional_usdt
        fill_ledger: List[Tuple[int, float, float]] = []
        cancelled_notional = 0.0
        entry_ms: Optional[int] = None
        exit_ms: Optional[int] = None
        exit_raw: Optional[float] = None
        exit_reason = "horizon"
        open_at_end = False
        mfe = 0.0
        mae = 0.0
        last_known_px: Optional[float] = None
        last_known_ms: Optional[int] = None

        def _fav(px: float, avg: float) -> float:
            return (px - avg) / avg * 100.0 if is_long else \
                (avg - px) / avg * 100.0

        def _adv(px: float, avg: float) -> float:
            return (avg - px) / avg * 100.0 if is_long else \
                (px - avg) / avg * 100.0

        def _stop_px(avg: float) -> float:
            return avg * (1.0 - config.stop_distance_pct / 100.0) \
                if is_long else avg * (
                    1.0 + config.stop_distance_pct / 100.0)

        for i in fill_idx:
            c = series[i]
            if c.open_time_ms > horizon_end:
                break  # past the window: nothing here is usable (R1/R2)
            ct = closes[ev.symbol][i]
            known_close = ct is not None and ct <= horizon_end
            # (1) Existing position resolves against the KNOWN open first
            # (R3/R4): a gap through the stop exits AT the open; a later
            # recovery cannot upgrade it; a stopped position takes no fills.
            if filled_qty > 0:
                avg_now = filled_cost_raw / filled_qty
                stop_now = _stop_px(avg_now)
                gapped = (c.open <= stop_now) if is_long else \
                    (c.open >= stop_now)
                if gapped:
                    exit_raw, exit_ms = c.open, c.open_time_ms
                    exit_reason = "stop"
                    mae = max(mae, _adv(c.open, avg_now))
                    break
            # (2) New fill at the known open while notional remains.
            if remaining > 0:
                chunk = remaining if config.partial_fill_notional_cap is None \
                    else min(remaining, config.partial_fill_notional_cap)
                if chunk > 0:
                    qty = chunk / c.open
                    filled_qty += qty
                    filled_cost_raw += chunk
                    spread_slip += chunk * drag
                    entry_spread_slip += chunk * drag
                    remaining -= chunk
                    n_fills += 1
                    fill_ledger.append((c.open_time_ms, chunk, qty))
                    if entry_ms is None:
                        entry_ms = c.open_time_ms
                    last_known_px, last_known_ms = c.open, c.open_time_ms
            if filled_qty <= 0:
                continue
            # (3) Range stop + metrics need the KNOWN close (R1/R5).
            if not known_close:
                continue
            avg_now = filled_cost_raw / filled_qty
            stop_now = _stop_px(avg_now)
            # The open printed while holding: demonstrated, credited.
            mfe = max(mfe, _fav(c.open, avg_now))
            mae = max(mae, _adv(c.open, avg_now))
            touched = (c.low <= stop_now) if is_long else \
                (c.high >= stop_now)
            if touched:
                # Open was safe (gap handled above), so the level is in
                # range: fill AT the stop with knowledge time = close.
                exit_raw, exit_ms = stop_now, ct
                exit_reason = "stop"
                mae = max(mae, _adv(stop_now, avg_now))
                break
            # Favorable extreme excluded: order vs a later exit is unknown.
            mfe = max(mfe, _fav(c.high if is_long else c.low, avg_now))
            mae = max(mae, _adv(c.low if is_long else c.high, avg_now))
            last_known_px, last_known_ms = c.close, ct
            exit_raw, exit_ms = c.close, ct

        if entry_ms is None:
            n_expired += 1
            continue
        cancelled_notional = remaining
        if exit_raw is None or exit_ms is None:
            # No usable close ever resolved: fall back to last knowledge
            # (always exists: at least the fill open is known).
            exit_raw = last_known_px if last_known_px is not None else \
                filled_cost_raw / filled_qty
            exit_ms = last_known_ms if last_known_ms is not None else entry_ms
        data_past_horizon = series[-1].open_time_ms > horizon_end
        if exit_raw is None or exit_ms is None:
            # No resolution inside the window: mark at last knowledge.
            exit_raw = last_known_px if last_known_px is not None else \
                filled_cost_raw / filled_qty
            exit_ms = last_known_ms if last_known_ms is not None else entry_ms
        if data_past_horizon and exit_reason != "stop":
            exit_reason = "horizon"  # rule closed it; price/time are marks
        elif exit_reason != "stop":
            exit_reason = "open_at_end"  # data ended first: a MARK, flagged
            open_at_end = True
        if exit_ms is not None and exit_ms < entry_ms:
            exit_ms = entry_ms  # invariant: knowledge time never precedes entry

        avg_raw = filled_cost_raw / filled_qty
        move = (exit_raw - avg_raw) if is_long else (avg_raw - exit_raw)
        gross = filled_qty * move
        exit_value = filled_qty * exit_raw
        exit_spread_slip = exit_value * drag
        spread_slip += exit_spread_slip
        filled_notional = filled_cost_raw
        # Entry commission on executed notional; exit commission on the
        # exit VALUE (qty x exit price): closing 10u at 120 with 10 bps
        # costs 1.20, not the 1.00 entry figure. Symmetric halves would
        # misprice every non-flat exit.
        entry_fees = filled_notional * config.fee_bps / 10_000.0 * \
            config.cost_scale
        exit_fees = exit_value * config.fee_bps / 10_000.0 * \
            config.cost_scale
        fees = entry_fees + exit_fees
        funding, funding_events, funding_uncovered_ms, funding_gap_ms, \
            funding_unknown, funding_model, funding_meta = \
            _funding_for_trade(ev.direction, fill_ledger, entry_ms, exit_ms,
                               config, ev.symbol, series)
        friction = spread_slip + fees + funding
        net = gross - friction
        exit_executed = not open_at_end
        # Exit-leg costs on an open mark are HYPOTHETICAL (no executed
        # exit); entry-leg costs always executed. Funding accrues over the
        # actually-held span either way and stays whole in friction.
        costs_exit_hypothetical = (exit_spread_slip + exit_fees) \
            if open_at_end else 0.0
        costs_executed = friction - costs_exit_hypothetical
        realized_net = net if exit_executed else None
        trades.append({
            "symbol": ev.symbol, "direction": ev.direction,
            "family": ev.family, "rules_version": ev.rules_version,
            "event_time_ms": ev.event_time_ms, "entry_ms": entry_ms,
            "exit_ms": exit_ms, "entry_px": avg_raw, "exit_px": exit_raw,
            "filled_qty": filled_qty, "filled_cost": filled_cost_raw,
            "gross_pnl": gross, "spread_slip_cost": spread_slip,
            "entry_spread_slip": entry_spread_slip,
            "exit_spread_slip": exit_spread_slip,
            "fees": fees, "entry_fees": entry_fees, "exit_fees": exit_fees,
            "funding": funding, "friction": friction,
            "funding_events": funding_events,
            "funding_model": funding_model,
            "funding_uncovered_ms": funding_uncovered_ms,
            "funding_gap_ms": funding_gap_ms,
            "funding_unknown": funding_unknown,
            "funding_symbol": ev.symbol,
            "funding_complete": funding_meta.get("calendar_complete")
            if funding_meta else None,
            "funding_accounting_complete": funding_meta.get(
                "accounting_complete") if funding_meta else None,
            "funding_accounting_basis": funding_meta.get(
                "accounting_basis") if funding_meta else None,
            "net_pnl": net, "mfe_pct": mfe, "mae_pct": mae,
            "exit_reason": exit_reason, "open_at_end": open_at_end,
            "exit_executed": exit_executed,
            "costs_executed": costs_executed,
            "costs_exit_hypothetical": costs_exit_hypothetical,
            "realized_net": realized_net,
            "fills": n_fills, "cancelled_notional": cancelled_notional,
        })
        # Capacity commitment starts at signal time (not at fill time), so
        # simultaneous events compete for the same slots deterministically.
        open_intervals.append((ev.event_time_ms, exit_ms))

    equity = 0.0
    curve: List[float] = []
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t["net_pnl"]
        curve.append(equity)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    nets = [t["net_pnl"] for t in trades]
    # Realized-only books: open_at_end marks NEVER feed realized metrics.
    # The realized curve runs in effective-close-time order (exit_ms), not
    # event order. Legacy totals/curve above are unchanged (they include
    # open marks; do not cite them as realized performance).
    realized = [t for t in trades if t["exit_executed"]]
    open_positions = [{
        "symbol": t["symbol"], "direction": t["direction"],
        "family": t["family"], "rules_version": t["rules_version"],
        "event_time_ms": t["event_time_ms"], "entry_ms": t["entry_ms"],
        "mark_ms": t["exit_ms"], "mark_px": t["exit_px"],
        "filled_qty": t["filled_qty"], "filled_cost": t["filled_cost"],
    } for t in trades if t["open_at_end"]]
    realized_nets = [t["net_pnl"] for t in realized]
    realized_curve: List[Dict[str, Any]] = []
    req = 0.0
    rpeak = 0.0
    rmax_dd = 0.0
    for t in sorted(realized, key=lambda t: (t["exit_ms"], t["entry_ms"])):
        req += t["net_pnl"]
        realized_curve.append({"exit_ms": t["exit_ms"], "equity": req})
        rpeak = max(rpeak, req)
        rmax_dd = max(rmax_dd, rpeak - req)
    return {
        "engine_version": ENGINE_VERSION,
        "config_hash": config.config_hash(),
        "config": config.__dict__,
        "dataset_id": dataset_id,
        "input_hash": input_hash(events, candles),
        "segment": segment,
        "label": "MECHANICS-SMOKE — fixture replay, NOT performance",
        "limitations": list(LIMITATIONS),
        "drawdown_scope": "realized-only",
        "n_events": len(ordered_events),
        "n_trades": len(trades),
        "skipped_overlap": skipped_overlap,
        "n_expired": n_expired,
        "n_mismatched": n_mismatched,
        "expectancy_net": sum(nets) / len(nets) if nets else 0.0,
        "expectancy_gross": sum(t["gross_pnl"] for t in trades) / len(trades)
        if trades else 0.0,
        "total_net": sum(nets),
        "total_fees": sum(t["fees"] for t in trades),
        "total_funding": sum(t["funding"] for t in trades),
        "n_realized": len(realized),
        "n_open": len(open_positions),
        "open_positions": open_positions,
        "total_net_realized": sum(realized_nets),
        "expectancy_net_realized": sum(realized_nets) / len(realized_nets)
        if realized_nets else 0.0,
        "equity_curve_realized": realized_curve,
        "max_drawdown_realized": rmax_dd,
        "total_costs_executed": sum(t["costs_executed"] for t in trades),
        "total_exit_costs_hypothetical": sum(
            t["costs_exit_hypothetical"] for t in trades),
        "funding_calendar": None if config.funding_calendar is None else {
            "version": config.funding_calendar.version,
            "source": config.funding_calendar.source,
            "interval_ms": config.funding_calendar.interval_ms,
            "symbol": config.funding_calendar.symbol,
            "n_settlements": len(config.funding_calendar.settlements),
            "duplicates_deduped": cal_duplicates,
            "complete": cal_assessment.get("complete"),
            "completeness_basis": cal_assessment.get("completeness_basis"),
            "gaps": cal_assessment.get("gaps", []),
            "hash": config.funding_calendar.calendar_hash(),
        },
        "funding_estimated_bps_context": config.funding_estimated_bps,
        "max_drawdown": max_dd,
        "mfe_mean": sum(t["mfe_pct"] for t in trades) / len(trades)
        if trades else 0.0,
        "mae_mean": sum(t["mae_pct"] for t in trades) / len(trades)
        if trades else 0.0,
        "exit_reasons": {k: sum(1 for t in trades if t["exit_reason"] == k)
                         for k in ("horizon", "stop", "open_at_end")},
        "equity_curve": curve,
        "trades": trades,
    }


def run_sensitivity(events: List[StudyEvent], candles: List[Candle],
                    config: BacktestConfig, dataset_id: str = "synthetic-fixture",
                    scales: tuple = (1.0, 2.0, 3.0)) -> Dict[str, Any]:
    """Dev/OOS segments × cost scales, all reproducible."""
    from dataclasses import replace

    cutoff = _median_time(events)
    out: Dict[str, Any] = {"engine_version": ENGINE_VERSION,
                           "dataset_id": dataset_id,
                           "input_hash": input_hash(events, candles),
                           "cutoff_ms": cutoff, "segments": {}}
    for name, seg_events in split_by_time(events, cutoff).items():
        out["segments"][name] = {}
        for scale in scales:
            cfg = replace(config, cost_scale=float(scale))
            out["segments"][name][str(scale)] = run_backtest(
                seg_events, candles, cfg, dataset_id, segment=name)
    return out


def _median_time(events: List[StudyEvent]) -> int:
    if not events:
        return 0
    ordered = sorted(e.event_time_ms for e in events)
    return ordered[len(ordered) // 2]


def result_to_jsonable(result: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(result, default=str))
