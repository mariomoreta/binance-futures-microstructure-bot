"""Etapa 4: isolated offline backtest preparation (research mechanics only).

Pure, deterministic, stdlib-only replay over injected candles + study
events. No network, no live modules, no database access, no wall clock,
no randomness. Entry/exit rules here are STRUCTURAL MECHANICS placeholders
(next-open fills, horizon exits, distance stops) — NOT validated signals;
any result on fixtures is a MECHANICS SMOKE proof, never performance.

No-lookahead is structural: fills use the first candle with
``open_time > event_time`` only; exits walk candles in time order; inputs
are re-sorted defensively. Results carry config hash + dataset id +
engine version so reruns are byte-reproducible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ENGINE_VERSION = "backtest-offline/v1"
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

    def config_hash(self) -> str:
        payload = json.dumps(self.__dict__, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _bps_cost(notional: float, bps: float, scale: float) -> float:
    return abs(notional) * bps / 10_000.0 * scale


@dataclass
class _Fill:
    time_ms: int
    price: float
    qty_notional: float


def _fill_price(side: str, candle_open: float, cfg: BacktestConfig) -> float:
    adj = (cfg.spread_bps + cfg.slippage_bps) * cfg.cost_scale / 10_000.0
    return candle_open * (1.0 + adj) if side == "LONG" else candle_open * (1.0 - adj)


def _exit_price(side: str, raw: float, cfg: BacktestConfig) -> float:
    adj = (cfg.spread_bps + cfg.slippage_bps) * cfg.cost_scale / 10_000.0
    return raw * (1.0 - adj) if side == "LONG" else raw * (1.0 + adj)


def split_by_time(events: List[StudyEvent],
                  cutoff_ms: int) -> Dict[str, List[StudyEvent]]:
    ordered = sorted(events, key=lambda e: (e.event_time_ms, e.symbol))
    return {
        "dev": [e for e in ordered if e.event_time_ms < cutoff_ms],
        "oos": [e for e in ordered if e.event_time_ms >= cutoff_ms],
    }


def run_backtest(events: List[StudyEvent], candles: List[Candle],
                 config: BacktestConfig,
                 dataset_id: str = "synthetic-fixture",
                 segment: str = "dev") -> Dict[str, Any]:
    """Chronological replay. Returns a versioned, reproducible result dict."""
    ordered_events = sorted(events, key=lambda e: (e.event_time_ms, e.symbol))
    by_symbol: Dict[str, List[Candle]] = {}
    for c in sorted(candles, key=lambda c: (c.symbol, c.open_time_ms)):
        by_symbol.setdefault(c.symbol, []).append(c)

    trades: List[Dict[str, Any]] = []
    skipped_overlap = 0
    open_until = 0
    for ev in ordered_events:
        if ev.direction not in ("LONG", "SHORT"):
            continue
        if ev.event_time_ms < open_until and config.max_concurrent <= 1:
            skipped_overlap += 1
            continue
        series = by_symbol.get(ev.symbol, [])
        fill_from = [c for c in series if c.open_time_ms > ev.event_time_ms]
        if not fill_from:
            continue
        # Deterministic (possibly partial) fills at successive opens.
        fills: List[_Fill] = []
        remaining = config.notional_usdt
        for c in fill_from:
            if remaining <= 0:
                break
            chunk = remaining if config.partial_fill_notional_cap is None \
                else min(remaining, config.partial_fill_notional_cap)
            fills.append(_Fill(c.open_time_ms, _fill_price(
                ev.direction, c.open, config), chunk))
            remaining -= chunk
        if remaining > 0:
            continue  # never fully filled inside the series: no trade
        entry_px = sum(f.price * f.qty_notional for f in fills) / sum(
            f.qty_notional for f in fills)
        entry_ms = fills[0].time_ms
        horizon_end = ev.event_time_ms + config.exit_horizon_ms
        stop_px = entry_px * (1.0 - config.stop_distance_pct / 100.0) \
            if ev.direction == "LONG" else entry_px * (
                1.0 + config.stop_distance_pct / 100.0)
        mfe = 0.0
        mae = 0.0
        exit_ms = horizon_end
        exit_raw = fill_from[-1].close if any(
            c.open_time_ms <= horizon_end for c in fill_from) else entry_px
        exit_reason = "horizon"
        for c in fill_from:
            if c.open_time_ms > horizon_end:
                break
            if ev.direction == "LONG":
                mfe = max(mfe, (c.high - entry_px) / entry_px * 100.0)
                mae = max(mae, (entry_px - c.low) / entry_px * 100.0)
                if c.low <= stop_px:
                    exit_raw, exit_ms, exit_reason = stop_px, c.open_time_ms, "stop"
                    break
            else:
                mfe = max(mfe, (entry_px - c.low) / entry_px * 100.0)
                mae = max(mae, (c.high - entry_px) / entry_px * 100.0)
                if c.high >= stop_px:
                    exit_raw, exit_ms, exit_reason = stop_px, c.open_time_ms, "stop"
                    break
            exit_raw = c.close
            exit_ms = c.open_time_ms
        exit_px = _exit_price(ev.direction, exit_raw, config)
        gross = (exit_px - entry_px) / entry_px * config.notional_usdt \
            if ev.direction == "LONG" else \
            (entry_px - exit_px) / entry_px * config.notional_usdt
        fees = _bps_cost(config.notional_usdt, config.fee_bps,
                         config.cost_scale) * 2.0
        n_funding = max(0, (exit_ms - entry_ms) // FUNDING_INTERVAL_MS)
        funding = _bps_cost(config.notional_usdt, config.funding_8h_bps,
                            config.cost_scale) * n_funding
        net = gross - fees - funding
        trades.append({
            "symbol": ev.symbol, "direction": ev.direction,
            "event_time_ms": ev.event_time_ms, "entry_ms": entry_ms,
            "exit_ms": exit_ms, "entry_px": entry_px, "exit_px": exit_px,
            "gross_pnl": gross, "fees": fees, "funding": funding,
            "net_pnl": net, "mfe_pct": mfe, "mae_pct": mae,
            "exit_reason": exit_reason, "fills": len(fills),
        })
        open_until = max(open_until, exit_ms)

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
    result = {
        "engine_version": ENGINE_VERSION,
        "config_hash": config.config_hash(),
        "config": config.__dict__,
        "dataset_id": dataset_id,
        "segment": segment,
        "label": "MECHANICS-SMOKE — fixture replay, NOT performance",
        "n_events": len(ordered_events),
        "n_trades": len(trades),
        "skipped_overlap": skipped_overlap,
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
                         for k in ("horizon", "stop")},
        "equity_curve": curve,
        "trades": trades,
    }
    return result


def run_sensitivity(events: List[StudyEvent], candles: List[Candle],
                    config: BacktestConfig, dataset_id: str = "synthetic-fixture",
                    scales: tuple = (1.0, 2.0, 3.0)) -> Dict[str, Any]:
    """Dev/OOS segments × cost scales, all reproducible."""
    from dataclasses import replace

    out: Dict[str, Any] = {"engine_version": ENGINE_VERSION,
                           "dataset_id": dataset_id, "segments": {}}
    for name, seg_events in split_by_time(
            events, _median_time(events)).items():
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
