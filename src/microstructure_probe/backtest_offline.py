"""Offline backtest preparation (research mechanics only, v3).

Pure, deterministic, stdlib-only replay over injected candles + study
events. No network, no live modules, no database access, no wall clock,
no randomness. Entry/exit rules are STRUCTURAL MECHANICS placeholders —
NOT validated signals; any result on fixtures is a MECHANICS SMOKE proof,
never performance. The v2 causality/closure guarantees refuted by review
(R1/R2) are WITHDRAWN and replaced below; the motor is NOT claimed
causally verified — only covered by the regression battery.

Temporal availability contract (v3):
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
- Funding accrues per full 8h held on filled notional, SIGNED by direction
  (LONG pays, SHORT receives at a positive rate). Single-rate model is a
  labeled limitation.
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

ENGINE_VERSION = "backtest-offline/v3"
FUNDING_INTERVAL_MS = 8 * 3600 * 1000


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
        payload = json.dumps(self.__dict__, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


LIMITATIONS = [
    "no-latency-model",
    "no-tick-lot-rounding",
    "no-min-notional-gate",
    "realized-only-drawdown",
    "funding-single-rate",
    "oos-split-by-event-time",
]


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
        n_fills = 0
        remaining = config.notional_usdt
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
                    remaining -= chunk
                    n_fills += 1
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
        spread_slip += exit_value * drag
        filled_notional = filled_cost_raw
        fees = filled_notional * config.fee_bps / 10_000.0 * \
            config.cost_scale * 2.0
        n_funding = max(0, (exit_ms - entry_ms) // FUNDING_INTERVAL_MS)
        sign = 1.0 if is_long else -1.0
        funding = sign * filled_notional * config.funding_8h_bps / \
            10_000.0 * config.cost_scale * n_funding
        friction = spread_slip + fees + funding
        net = gross - friction
        trades.append({
            "symbol": ev.symbol, "direction": ev.direction,
            "family": ev.family, "rules_version": ev.rules_version,
            "event_time_ms": ev.event_time_ms, "entry_ms": entry_ms,
            "exit_ms": exit_ms, "entry_px": avg_raw, "exit_px": exit_raw,
            "filled_qty": filled_qty, "filled_cost": filled_cost_raw,
            "gross_pnl": gross, "spread_slip_cost": spread_slip,
            "fees": fees, "funding": funding, "friction": friction,
            "net_pnl": net, "mfe_pct": mfe, "mae_pct": mae,
            "exit_reason": exit_reason, "open_at_end": open_at_end,
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
