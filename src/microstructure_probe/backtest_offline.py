"""Offline backtest preparation (research mechanics only, v2).

Pure, deterministic, stdlib-only replay over injected candles + study
events. No network, no live modules, no database access, no wall clock,
no randomness. Entry/exit rules are STRUCTURAL MECHANICS placeholders —
NOT validated signals; any result on fixtures is a MECHANICS SMOKE proof,
never performance.

Causality contract (v2):
- Fills are sequential: each fill buys qty = chunk_notional / fill_price
  at successive candle opens; stops are evaluated against the position
  AS OF each candle. A later fill can never move an earlier entry/stop.
- A candle's open is known at its open_time; its high/low/close are known
  only at its close_time (next candle's open_time, same symbol). A candle
  with unknown close_time, or closing after the horizon, contributes no
  high/low/close. No intra-candle timing is ever attributed.
- Stop policy (conservative, explicit): if the stop level lies inside the
  candle's [low, high], the stop fills AT the stop price; otherwise the
  candle gapped through it and the exit fills at the candle OPEN (first
  available price). Stop-exit knowledge time = candle close_time when
  known, else its open_time.
- Entry window: if the first fillable open falls after the horizon, the
  event EXPIRES (counted, never traded). exit_ms is never before entry_ms.
- Incomplete data: actually-filled quantity/costs are kept; the position
  closes at the last KNOWN price with reason "open_at_end" and an explicit
  flag (never silently dropped).
- Quantity accounting: filled_qty, filled_cost (raw), average entry =
  cost/qty. gross_pnl is pure price P&L on filled qty; friction =
  spread/slippage drag + fees + signed funding; net = gross - friction.
- Funding accrues per full 8h held on filled notional, SIGNED by direction
  (LONG pays, SHORT receives at a positive rate). Single-rate model is a
  labeled limitation.
- Concurrency is enforced over signal-to-exit intervals (capacity
  commits at event time), per max_concurrent; simultaneous events compete
  deterministically in time order.
- Events whose (family, rules_version) differ from config are SKIPPED and
  counted (never silently pooled).
- Unsupported knobs (latency_ms, tick_size, lot_step, min_notional_usdt)
  REJECT the run with ValueError; they are never simulated as supported.
- Drawdown is REALIZED-only (closed-trade net equity); mark-to-market is
  explicitly NOT modeled. dev/OOS splits by event time (documented).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

ENGINE_VERSION = "backtest-offline/v2"
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

        for i in fill_idx:
            c = series[i]
            if entry_ms is not None and c.open_time_ms > horizon_end:
                break  # past the window: no more fills, no post-window info
            ct = closes[ev.symbol][i]
            # (a) Fill at this candle's open (known at open_time) while the
            # window is open and notional remains. Unfilled remainder past
            # the last in-window open is CANCELLED, never force-filled.
            if remaining > 0 and c.open_time_ms <= horizon_end:
                chunk = remaining if config.partial_fill_notional_cap is None \
                    else min(remaining, config.partial_fill_notional_cap)
                if chunk > 0:
                    fill_px_raw = c.open
                    qty = chunk / fill_px_raw
                    filled_qty += qty
                    filled_cost_raw += chunk
                    spread_slip += chunk * drag
                    remaining -= chunk
                    n_fills += 1
                    if entry_ms is None:
                        entry_ms = c.open_time_ms
                    last_known_px = c.open
            if filled_qty <= 0:
                continue
            # (b) Stop check against the position AS OF this candle (only
            # candles at/inside the window can trigger; later fills can
            # never retroactively move this decision).
            avg_raw = filled_cost_raw / filled_qty
            stop_px = avg_raw * (1.0 - config.stop_distance_pct / 100.0) \
                if is_long else avg_raw * (
                    1.0 + config.stop_distance_pct / 100.0)
            touched = (c.low <= stop_px) if is_long else (c.high >= stop_px)
            if touched and c.open_time_ms <= horizon_end:
                in_range = (c.low <= stop_px <= c.high)
                exit_raw = stop_px if in_range else c.open  # gap: first real
                exit_ms = ct if ct is not None else c.open_time_ms
                exit_reason = "stop"
                break
            # (c) Usable high/low/close only when known within the horizon.
            if ct is not None and ct <= horizon_end:
                if is_long:
                    mfe = max(mfe, (c.high - avg_raw) / avg_raw * 100.0)
                    mae = max(mae, (avg_raw - c.low) / avg_raw * 100.0)
                else:
                    mfe = max(mfe, (avg_raw - c.low) / avg_raw * 100.0)
                    mae = max(mae, (c.high - avg_raw) / avg_raw * 100.0)
                last_known_px = c.close
                exit_raw = c.close
                exit_ms = horizon_end
                exit_reason = "horizon"

        if entry_ms is None:
            n_expired += 1
            continue
        cancelled_notional = remaining
        if exit_raw is None or exit_ms is None:
            # Data ended with the position open: keep what was simulated,
            # close at the last KNOWN price, flag explicitly.
            exit_raw = last_known_px if last_known_px is not None else \
                filled_cost_raw / filled_qty
            exit_ms = entry_ms
            exit_reason = "open_at_end"
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
