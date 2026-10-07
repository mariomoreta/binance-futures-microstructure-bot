"""P1-11C generic no-lookahead event-study engine (research only, no signals).

Contract:
- An event forms at time T using ONLY bars with open_time <= T (closed bars).
- Outcomes use ONLY bars with open_time > T (strictly after).
- Reference price = closed bar close at/preceding T (mark preferred, labeled).
- No future-aware thresholds, no refit after outcomes, no fabricated flow/book.
- Historical taker-buy share is labeled HISTORICAL_TAKER_BUY_PROXY.
- Absorption studies are labeled ABSORPTION_PROXY, never CONFIRMED.
- Kline-derived acceleration is HISTORICAL_MOMENTUM_PROXY, not P1-05 live.

Outcome horizons: 1m/3m/5m/15m/30m/1h (fixed).
Path states: COMPLETE / PARTIAL / INVALID_GAP / INSUFFICIENT_HISTORY.
Sample tiers: <30 INSUFFICIENT, 30-99 EXPLORATORY, 100-499 PRELIMINARY, 500+ LARGER SAMPLE.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EVENT_SCHEMA_VERSION = 1

OUTCOME_HORIZONS_MS: Dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
}
OUTCOME_HORIZON_ORDER = ("1m", "3m", "5m", "15m", "30m", "1h")

# Research-only event families (descriptive, never LONG/SHORT signals).
EVENT_FAMILIES = (
    "EXTENDED_GAINER",
    "EXTENDED_LOSER",
    "MOMENTUM_ACCELERATION_UP",
    "MOMENTUM_ACCELERATION_DOWN",
    "FAILED_HIGH_CANDIDATE",
    "FAILED_LOW_CANDIDATE",
)

# Direction/context orientation for MFE/MAE semantics (descriptive only).
_FAMILY_DIRECTION = {
    "EXTENDED_GAINER": "up",
    "MOMENTUM_ACCELERATION_UP": "up",
    "FAILED_HIGH_CANDIDATE": "up",
    "EXTENDED_LOSER": "down",
    "MOMENTUM_ACCELERATION_DOWN": "down",
    "FAILED_LOW_CANDIDATE": "down",
}


def sample_size_label(n: int) -> str:
    """Quantity-only label (never profitability/validity)."""
    n = int(n)
    if n < 30:
        return "INSUFFICIENT"
    if n < 100:
        return "EXPLORATORY"
    if n < 500:
        return "PRELIMINARY"
    return "LARGER_SAMPLE"


def default_definition(family: str, version: int = 1) -> Dict[str, Any]:
    """Conservative HYPOTHESIS parameters for one research family version."""
    if family not in EVENT_FAMILIES:
        raise ValueError(f"unknown event family {family!r}")
    base: Dict[str, Any] = {
        "definition_name": family,
        "definition_version": int(version),
        "research_status": "DESCRIPTIVE_RESEARCH_ONLY_HYPOTHESIS",
        "created_at": int(time.time() * 1000),
        "source_requirements": {
            "bars": "closed klines only (mark preferred, else regular labeled)",
            "flow": "HISTORICAL_TAKER_BUY_PROXY only; no live aggTrade claims",
            "book": "none historically; ABSORPTION_PROXY only",
        },
    }
    if family == "EXTENDED_GAINER":
        base.update({
            "parameters": {
                "prior_24h_return_min": 0.05,
                "prior_1h_return_min": 0.005,
                "range_position_min": 0.7,
                "evaluation_horizon": "15m",
                "continuation_threshold": 0.005,
                "reversal_threshold": -0.005,
                "invalidation_pct": None,
            },
            "required_features": ["prior_24h_return", "prior_1h_return",
                                  "range_position", "reference_price"],
        })
    elif family == "EXTENDED_LOSER":
        base.update({
            "parameters": {
                "prior_24h_return_max": -0.05,
                "prior_1h_return_max": -0.005,
                "range_position_max": 0.3,
                "evaluation_horizon": "15m",
                "continuation_threshold": -0.005,
                "reversal_threshold": 0.005,
                "invalidation_pct": None,
            },
            "required_features": ["prior_24h_return", "prior_1h_return",
                                  "range_position", "reference_price"],
        })
    elif family == "MOMENTUM_ACCELERATION_UP":
        base.update({
            "parameters": {
                "accel_window_bars": 4,
                "accel_min": 0.001,
                "prior_1h_return_min": 0.0,
                "semantics": "HISTORICAL_MOMENTUM_PROXY (not P1-05 live)",
                "evaluation_horizon": "15m",
                "continuation_threshold": 0.005,
                "reversal_threshold": -0.005,
                "invalidation_pct": None,
            },
            "required_features": ["accel_proxy", "prior_1h_return",
                                  "reference_price"],
        })
    elif family == "MOMENTUM_ACCELERATION_DOWN":
        base.update({
            "parameters": {
                "accel_window_bars": 4,
                "accel_max": -0.001,
                "prior_1h_return_max": 0.0,
                "semantics": "HISTORICAL_MOMENTUM_PROXY (not P1-05 live)",
                "evaluation_horizon": "15m",
                "continuation_threshold": -0.005,
                "reversal_threshold": 0.005,
                "invalidation_pct": None,
            },
            "required_features": ["accel_proxy", "prior_1h_return",
                                  "reference_price"],
        })
    elif family == "FAILED_HIGH_CANDIDATE":
        base.update({
            "parameters": {
                "trailing_high_bars": 96,
                "proximity_pct": 0.002,
                "closeback_pct": 0.001,
                "evaluation_horizon": "15m",
                "continuation_threshold": 0.005,
                "reversal_threshold": -0.005,
                "invalidation_pct": None,
            },
            "required_features": ["trailing_high", "reference_price"],
        })
    elif family == "FAILED_LOW_CANDIDATE":
        base.update({
            "parameters": {
                "trailing_low_bars": 96,
                "proximity_pct": 0.002,
                "closeback_pct": 0.001,
                "evaluation_horizon": "15m",
                "continuation_threshold": -0.005,
                "reversal_threshold": 0.005,
                "invalidation_pct": None,
            },
            "required_features": ["trailing_low", "reference_price"],
        })
    return base


def _fnum(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def taker_buy_proxy(bar: Dict[str, Any]) -> Optional[float]:
    """HISTORICAL TAKER-BUY PROXY = taker_buy_quote / quote_volume."""
    qv = _fnum(bar.get("quote_volume"))
    tb = _fnum(bar.get("taker_buy_quote"))
    if qv is None or tb is None or qv <= 0:
        return None
    return tb / qv


def _log_return(new: float, old: float) -> Optional[float]:
    if old is None or new is None or old <= 0 or new <= 0:
        return None
    return math.log(new / old)


def _close_at_or_before(bars: List[Dict[str, Any]], ts: int) -> Optional[int]:
    idx = None
    for i, b in enumerate(bars):
        try:
            ot = int(b["open_time"])
        except (KeyError, TypeError, ValueError):
            continue
        if ot <= ts:
            idx = i
        else:
            break
    return idx


def _bar_step_ms(bars: List[Dict[str, Any]]) -> Optional[int]:
    ots = []
    for b in bars:
        try:
            ots.append(int(b["open_time"]))
        except (KeyError, TypeError, ValueError):
            continue
    ots.sort()
    if len(ots) < 2:
        return None
    diffs = [b - a for a, b in zip(ots, ots[1:]) if b > a]
    if not diffs:
        return None
    diffs.sort()
    return diffs[len(diffs) // 2]


def _has_gap(opens: List[int], step: int, start: int, end: int) -> bool:
    """True if the expected grid in [start, end] is not fully present."""
    if step is None or step <= 0:
        return True
    have = {o for o in opens if start <= o <= end}
    expect = start - (start % step)
    # align to grid of first available? use step walk from start
    t = start
    # walk at most a bounded number of steps (horizons are small vs grid)
    count = 0
    while t <= end and count < 100000:
        # allow any open within [t, t+step)? grid bars are exact in practice
        if t not in have:
            return True
        t += step
        count += 1
    return False


def formation_features(
    bars: List[Dict[str, Any]],
    idx: int,
    symbol: str,
    reference_source: str,
    btc_bars: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """All features using bars[0..idx] only (never idx+1)."""
    ref_bar = bars[idx]
    ref = _fnum(ref_bar.get("close"))
    ref_ot = int(ref_bar["open_time"])
    # trailing closes for returns
    closes = [(_fnum(b.get("close")), int(b["open_time"])) for b in bars[: idx + 1]]
    # helper: close at/before ref_ot - horizon
    def ret_before(h_ms: int) -> Optional[float]:
        target = ref_ot - h_ms
        # latest close with open_time <= target
        best = None
        for c, ot in closes:
            if ot <= target:
                best = c
            else:
                break
        if best is None or ref is None:
            return None
        return _log_return(ref, best)

    prior_1h = ret_before(3_600_000)
    prior_4h = ret_before(4 * 3_600_000)
    prior_24h = ret_before(24 * 3_600_000)
    # trailing 96-bar high/low + range position
    window = bars[max(0, idx - 95): idx + 1]
    highs = [_fnum(b.get("high")) for b in window]
    lows = [_fnum(b.get("low")) for b in window]
    highs = [h for h in highs if h is not None]
    lows = [l for l in lows if l is not None]
    trailing_high = max(highs) if highs else None
    trailing_low = min(lows) if lows else None
    if trailing_high and trailing_low and trailing_high > trailing_low and ref:
        range_pos = (ref - trailing_low) / (trailing_high - trailing_low)
        dist_high = (trailing_high - ref) / ref
        dist_low = (ref - trailing_low) / ref
    else:
        range_pos = None
        dist_high = None
        dist_low = None
    # 30d high/low as-of (bounded by available history, never future)
    deep = bars[max(0, idx - 2880): idx + 1]  # ~30d of 15m bars cap
    dh = [_fnum(b.get("high")) for b in deep]
    dl = [_fnum(b.get("low")) for b in deep]
    dh = [h for h in dh if h is not None]
    dl = [l for l in dl if l is not None]
    high_30d = max(dh) if dh else None
    low_30d = min(dl) if dl else None
    # volume / volatility percentiles over trailing 100 bars
    vols = [_fnum(b.get("quote_volume")) for b in bars[max(0, idx - 99): idx + 1]]
    vols = [v for v in vols if v is not None]
    cur_vol = _fnum(ref_bar.get("quote_volume"))
    if vols and cur_vol is not None and len(vols) >= 5:
        vol_pct = sum(1 for v in vols if v <= cur_vol) / len(vols)
    else:
        vol_pct = None
    rets = []
    prev = None
    for b in bars[max(0, idx - 99): idx + 1]:
        c = _fnum(b.get("close"))
        if prev is not None and c is not None:
            r = _log_return(c, prev)
            if r is not None:
                rets.append(abs(r))
        prev = c
    rv = math.sqrt(sum(r * r for r in rets)) if len(rets) >= 5 else None
    if rets and rv is not None and len(rets) >= 10:
        vol_pct2 = sum(1 for r in rets if r <= rets[-1]) / len(rets)
    else:
        vol_pct2 = None
    tb_proxy = taker_buy_proxy(ref_bar)
    # implied sell share proxy
    sell_proxy = (1.0 - tb_proxy) if tb_proxy is not None else None
    # accel proxy: change of 1h return over accel window (kline-derived)
    accel = None
    if prior_1h is not None:
        lag_idx_ot = ref_ot - 4 * 3_600_000
        # 1h return as of 4h ago (still <= T)
        sub = [b for b in bars[: idx + 1] if int(b["open_time"]) <= lag_idx_ot]
        if len(sub) >= 2:
            c_then = _fnum(sub[-1].get("close"))
            base_ot = lag_idx_ot - 3_600_000
            base = None
            for b in sub:
                if int(b["open_time"]) <= base_ot:
                    base = _fnum(b.get("close"))
                else:
                    break
            if c_then and base:
                old_ret = _log_return(c_then, base)
                if old_ret is not None:
                    accel = prior_1h - old_ret
    # BTC context (synchronized lookup at/before T, never after)
    btc_ctx: Dict[str, Any] = {"available": False}
    btc_ret_1h = btc_ret_5m = btc_ret_15m = btc_ret_15m_raw = None
    btc_rel = None
    if btc_bars:
        bi = _close_at_or_before(btc_bars, ref_ot)
        if bi is not None:
            bc = _fnum(btc_bars[bi].get("close"))
            btc_ctx["available"] = True
            btc_ctx["reference_close"] = bc
            btc_ctx["reference_time"] = int(btc_bars[bi]["open_time"])

            def bret(h_ms: int) -> Optional[float]:
                tgt = ref_ot - h_ms
                bj = _close_at_or_before(btc_bars or [], tgt)
                # must also be <= ref index time (no future): _close_at_or_before(tgt) guarantees
                if bj is None or bc is None:
                    return None
                old = _fnum(btc_bars[bj].get("close"))  # type: ignore[index]
                if old is None:
                    return None
                return _log_return(bc, old)

            btc_ret_1h = bret(3_600_000)
            btc_ret_5m = bret(300_000)
            btc_ret_15m = bret(900_000)
            btc_ctx.update({"ret_5m": btc_ret_5m, "ret_15m": btc_ret_15m,
                            "ret_1h": btc_ret_1h})
            if prior_1h is not None and btc_ret_1h is not None:
                btc_rel = prior_1h - btc_ret_1h
    opens = []
    for b in bars:
        try:
            opens.append(int(b["open_time"]))
        except (KeyError, TypeError, ValueError):
            continue
    step = _bar_step_ms(bars)
    formation_gap = False
    if step:
        ws = ref_ot - 24 * 3_600_000
        # check only the trailing 24h grid present
        have = set(opens)
        t = ref_ot
        missing = 0
        while t >= ws:
            if t not in have:
                # grid may be coarser than 1 bar per ms-walk; check nearest
                missing += 1
                if missing >= 1:
                    # confirm by counting expected vs actual in window
                    expected = (ref_ot - ws) // step + 1
                    actual = sum(1 for o in opens if ws <= o <= ref_ot)
                    if actual < expected:
                        formation_gap = True
                    break
            t -= step
            if (ref_ot - t) // max(step, 1) > 10000:
                break
    return {
        "symbol": symbol.upper(),
        "event_time": ref_ot,
        "reference_price": ref,
        "reference_source": reference_source,
        "reference_timestamp": ref_ot,
        "formation_window_start": ref_ot - 24 * 3_600_000,
        "formation_window_end": ref_ot,
        "prior_1h_return": prior_1h,
        "prior_4h_return": prior_4h,
        "prior_24h_return": prior_24h,
        "trailing_high": trailing_high,
        "trailing_low": trailing_low,
        "range_position": range_pos,
        "distance_from_high": dist_high,
        "distance_from_low": dist_low,
        "high_30d": high_30d,
        "low_30d": low_30d,
        "volume_percentile": vol_pct,
        "realized_volatility_abs": rv,
        "volatility_percentile": vol_pct2,
        "taker_buy_proxy": tb_proxy,
        "taker_buy_proxy_label": "HISTORICAL_TAKER_BUY_PROXY",
        "implied_sell_share_proxy": sell_proxy,
        "accel_proxy": accel,
        "accel_proxy_label": "HISTORICAL_MOMENTUM_PROXY",
        "btc_context": btc_ctx,
        "btc_ret_1h": btc_ret_1h,
        "relative_return_1h": btc_rel,
        "formation_gap": formation_gap,
        "bar_step_ms": step,
        "source_interval": None,
    }


def _matches_definition(family: str, params: Dict[str, Any],
                         feat: Dict[str, Any]) -> Tuple[bool, str]:
    """Pure T-known gate (never touches future bars). Returns (fire, context)."""
    if family == "EXTENDED_GAINER":
        r24 = feat.get("prior_24h_return")
        r1 = feat.get("prior_1h_return")
        rp = feat.get("range_position")
        if r24 is None or r1 is None or rp is None:
            return False, "missing-features"
        if r24 >= float(params["prior_24h_return_min"]) \
                and r1 >= float(params["prior_1h_return_min"]) \
                and rp >= float(params["range_position_min"]):
            return True, "extended-up"
        return False, "below-threshold"
    if family == "EXTENDED_LOSER":
        r24 = feat.get("prior_24h_return")
        r1 = feat.get("prior_1h_return")
        rp = feat.get("range_position")
        if r24 is None or r1 is None or rp is None:
            return False, "missing-features"
        if r24 <= float(params["prior_24h_return_max"]) \
                and r1 <= float(params["prior_1h_return_max"]) \
                and rp <= float(params["range_position_max"]):
            return True, "extended-down"
        return False, "above-threshold"
    if family == "MOMENTUM_ACCELERATION_UP":
        a = feat.get("accel_proxy")
        r1 = feat.get("prior_1h_return")
        if a is None or r1 is None:
            return False, "missing-features"
        if a >= float(params["accel_min"]) \
                and r1 >= float(params.get("prior_1h_return_min", 0.0)):
            return True, "accel-up"
        return False, "below-threshold"
    if family == "MOMENTUM_ACCELERATION_DOWN":
        a = feat.get("accel_proxy")
        r1 = feat.get("prior_1h_return")
        if a is None or r1 is None:
            return False, "missing-features"
        if a <= float(params["accel_max"]) \
                and r1 <= float(params.get("prior_1h_return_max", 0.0)):
            return True, "accel-down"
        return False, "above-threshold"
    if family == "FAILED_HIGH_CANDIDATE":
        th = feat.get("trailing_high")
        ref = feat.get("reference_price")
        if th is None or ref is None or ref <= 0:
            return False, "missing-features"
        prox = float(params.get("proximity_pct", 0.002))
        back = float(params.get("closeback_pct", 0.001))
        # reached/approached trailing high then closed back below by `back`
        if ref >= th * (1 - prox) and ref <= th * (1 - back):
            return True, "failed-high"
        return False, "no-failure-shape"
    if family == "FAILED_LOW_CANDIDATE":
        tl = feat.get("trailing_low")
        ref = feat.get("reference_price")
        if tl is None or ref is None or ref <= 0:
            return False, "missing-features"
        prox = float(params.get("proximity_pct", 0.002))
        back = float(params.get("closeback_pct", 0.001))
        if ref <= tl * (1 + prox) and ref >= tl * (1 + back):
            return True, "failed-low"
        return False, "no-failure-shape"
    return False, "unknown-family"


def detect_events(
    bars: List[Dict[str, Any]],
    definition: Dict[str, Any],
    symbol: str,
    reference_source: str,
    interval: str,
    btc_bars: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Scan closed bars; each index i uses only bars[..i] for formation."""
    fam = str(definition["definition_name"])
    params = dict(definition.get("parameters", {}))
    direction = _FAMILY_DIRECTION.get(fam, "up")
    ordered = sorted(bars, key=lambda b: int(b["open_time"]))
    # need warmup: at least enough history for 24h return where required
    events = []
    for i in range(len(ordered)):
        # require some minimum history (else INSUFFICIENT, skip honestly)
        if i < 5:
            continue
        feat = formation_features(ordered[: i + 1], i, symbol,
                                  reference_source, btc_bars)
        feat["source_interval"] = interval
        fire, ctx = _matches_definition(fam, params, feat)
        if not fire:
            continue
        if feat.get("reference_price") is None:
            continue
        ev = {
            "definition_name": fam,
            "definition_version": int(definition.get("definition_version", 1)),
            "symbol": symbol.upper(),
            "event_time": feat["event_time"],
            "direction": direction,
            "context": ctx,
            "source_interval": interval,
            "reference_price": feat["reference_price"],
            "reference_source": reference_source,
            "reference_timestamp": feat["reference_timestamp"],
            "features": feat,
            "formation_window_start": feat["formation_window_start"],
            "formation_window_end": feat["formation_window_end"],
            "formation_gap": bool(feat.get("formation_gap")),
            "provenance": {
                "bars": len(ordered),
                "interval": interval,
                "reference_source": reference_source,
            },
        }
        events.append(ev)
    # deterministic order
    events.sort(key=lambda e: (e["event_time"], e["symbol"]))
    # assign stable ids
    for k, e in enumerate(events):
        e["event_id"] = f"{fam}-v{e['definition_version']}-{e['symbol']}-{e['event_time']}-{k}"
    return events


def compute_outcome(
    event: Dict[str, Any],
    future_bars: List[Dict[str, Any]],
    horizon: str,
    invalidation_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Outcome strictly after T (open_time > event_time). Never fills gaps."""
    h_ms = OUTCOME_HORIZONS_MS[horizon]
    t = int(event["event_time"])
    ref = event.get("reference_price")
    direction = event.get("direction", "up")
    ordered = sorted([b for b in future_bars
                      if int(b["open_time"]) > t],
                     key=lambda b: int(b["open_time"]))
    if ref is None or ref <= 0:
        return {"event_id": event.get("event_id"), "horizon": horizon,
                "path": "INSUFFICIENT_HISTORY", "usable_for_statistics": False,
                "reason": "no-reference-price"}
    step = _bar_step_ms(future_bars) or _bar_step_ms(ordered)
    # path coverage: need a closed bar covering t+h. With a single future
    # bar the grid step is unknowable -> PARTIAL (never claim COMPLETE).
    end_needed = t + h_ms
    if step is not None and ordered:
        covered = any(int(b["open_time"]) + step >= end_needed
                      for b in ordered)
    else:
        covered = False
    window = [b for b in ordered if int(b["open_time"]) < t + h_ms + (step or 0)]
    # gap detection on the outcome grid
    gap_crossed = False
    if step and ordered:
        have = {int(b["open_time"]) for b in ordered}
        tt = ordered[0]["open_time"] and int(ordered[0]["open_time"])
        # walk expected grid from first future bar to horizon end
        cur = t + step - (t % step) if t % step else t + step
        # simpler: check contiguous stepping of window opens
        prev = None
        for b in window:
            ot = int(b["open_time"])
            if prev is not None and ot - prev > step * 1.5:
                gap_crossed = True
                break
            prev = ot
        # also horizon coverage gap
        if window:
            last = int(window[-1]["open_time"])
            if last + step < end_needed - step * 0.5:
                gap_crossed = gap_crossed  # coverage handled via path below
    if not window:
        return {"event_id": event.get("event_id"), "horizon": horizon,
                "path": "INSUFFICIENT_HISTORY", "usable_for_statistics": False,
                "reason": "no-future-bars", "gap_crossed": gap_crossed}
    fwd_close = None
    # forward return uses the last close with open_time < t+h (still > t)
    in_h = [b for b in window if int(b["open_time"]) < t + h_ms]
    use = in_h or window
    last_bar = use[-1]
    lc = _fnum(last_bar.get("close"))
    forward_return = (lc / ref - 1.0) if lc else None
    # MFE/MAE over highs/lows of bars strictly after T within horizon
    mfe = mae = None
    t_mfe = t_mae = None
    inv_time = None
    if direction == "up":
        best_up = -math.inf
        best_dn = math.inf
        for b in use:
            hi = _fnum(b.get("high"))
            lo = _fnum(b.get("low"))
            ot = int(b["open_time"])
            if hi is not None:
                r = hi / ref - 1.0
                if r > best_up:
                    best_up = r
                    t_mfe = ot
                if invalidation_pct is not None and inv_time is None:
                    pass
            if lo is not None:
                r = lo / ref - 1.0
                if r < best_dn:
                    best_dn = r
                    t_mae = ot
                if invalidation_pct is not None and inv_time is None \
                        and r <= -abs(invalidation_pct):
                    inv_time = ot
        mfe = best_up if best_up != -math.inf else None
        mae = best_dn if best_dn != math.inf else None
        if mfe is not None and mfe < 0:
            # no favorable excursion: MFE is negative excursion capped at 0? keep raw
            pass
        t_mfe_out = t_mfe - t if (mfe is not None and t_mfe is not None) else None
        t_mae_out = t_mae - t if (mae is not None and t_mae is not None) else None
    else:
        # SHORT-oriented mirror: favorable = downward
        best_fav = -math.inf  # (ref-low)/ref
        best_adv = -math.inf  # (high-ref)/ref
        for b in use:
            hi = _fnum(b.get("high"))
            lo = _fnum(b.get("low"))
            ot = int(b["open_time"])
            if lo is not None:
                r = ref / lo - 1.0 if lo > 0 else None
                # favorable magnitude as positive when price falls:
                fav = (ref - lo) / ref
                if fav > best_fav:
                    best_fav = fav
                    t_mfe = ot
                if invalidation_pct is not None and inv_time is None:
                    adv_now = ((hi - ref) / ref) if hi else None
                    if adv_now is not None and adv_now >= abs(invalidation_pct):
                        inv_time = ot
            if hi is not None:
                adv = (hi - ref) / ref
                if adv > best_adv:
                    best_adv = adv
                    t_mae = ot
        mfe = best_fav if best_fav != -math.inf else None
        mae = best_adv if best_adv != -math.inf else None
        t_mfe_out = t_mfe - t if (mfe is not None and t_mfe is not None) else None
        t_mae_out = t_mae - t if (mae is not None and t_mae is not None) else None
    # path completeness
    if gap_crossed:
        path = "INVALID_GAP"
        usable = False
    elif not covered:
        # check if horizon end beyond last available bar
        path = "PARTIAL"
        usable = False
    else:
        path = "COMPLETE"
        usable = True
    if event.get("formation_gap"):
        usable = False
    return {
        "event_id": event.get("event_id"),
        "horizon": horizon,
        "forward_return": forward_return,
        "mfe": mfe,
        "mae": mae,
        "time_to_mfe_ms": t_mfe_out,
        "time_to_mae_ms": t_mae_out,
        "invalidation_time": inv_time,
        "path": path,
        "path_complete": path == "COMPLETE",
        "gap_crossed": gap_crossed,
        "usable_for_statistics": usable,
        "reference_price": ref,
        "bars_used": len(use),
    }


def continuation_label(event: Dict[str, Any], outcome: Dict[str, Any],
                       params: Dict[str, Any]) -> str:
    """Fixed predeclared thresholds (never tuned on outcomes)."""
    if not outcome.get("usable_for_statistics"):
        return "INSUFFICIENT_DATA"
    fwd = outcome.get("forward_return")
    if fwd is None:
        return "INSUFFICIENT_DATA"
    direction = event.get("direction", "up")
    cont = float(params.get("continuation_threshold", 0.005 if direction == "up" else -0.005))
    rev = float(params.get("reversal_threshold", -0.005 if direction == "up" else 0.005))
    if direction == "up":
        if fwd >= cont:
            return "CONTINUED_UP"
        if fwd <= rev:
            return "REVERSED_DOWN"
        return "MIXED"
    else:
        if fwd <= cont:
            return "CONTINUED_DOWN"
        if fwd >= rev:
            return "REVERSED_UP"
        return "MIXED"


def _quantile(sorted_vals: List[float], q: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def distribution(values: List[float]) -> Dict[str, Any]:
    """Descriptive distribution with mandatory N (never confidence claims)."""
    vals = sorted(v for v in values if v is not None and math.isfinite(v))
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "p25": None,
                "p75": None, "p90": None, "p95": None}
    mean = sum(vals) / n
    return {"n": n, "mean": mean, "median": _quantile(vals, 0.5),
            "p25": _quantile(vals, 0.25), "p75": _quantile(vals, 0.75),
            "p90": _quantile(vals, 0.90), "p95": _quantile(vals, 0.95)}


def summarize_study(events: List[Dict[str, Any]],
                    outcomes_by_horizon: Dict[str, List[Dict[str, Any]]],
                    params: Dict[str, Any]) -> Dict[str, Any]:
    """Per-horizon descriptive summary (always with N + exclusions)."""
    total = len(events)
    out: Dict[str, Any] = {"n_total": total, "horizons": {},
                           "sample_label": sample_size_label(total)}
    for h, outs in outcomes_by_horizon.items():
        usable = [o for o in outs if o.get("usable_for_statistics")]
        excluded = [o for o in outs if not o.get("usable_for_statistics")]
        reasons: Dict[str, int] = {}
        for o in excluded:
            reasons[o.get("path", "UNKNOWN")] = reasons.get(
                o.get("path", "UNKNOWN"), 0) + 1
        fwd = [o["forward_return"] for o in usable
               if o.get("forward_return") is not None]
        mfe = [o["mfe"] for o in usable if o.get("mfe") is not None]
        mae = [o["mae"] for o in usable if o.get("mae") is not None]
        ttmfe = [o["time_to_mfe_ms"] for o in usable
                 if o.get("time_to_mfe_ms") is not None]
        ttmae = [o["time_to_mae_ms"] for o in usable
                 if o.get("time_to_mae_ms") is not None]
        out["horizons"][h] = {
            "n_total": len(outs),
            "n_usable": len(usable),
            "n_excluded": len(excluded),
            "exclusion_reasons": reasons,
            "sample_label": sample_size_label(len(usable)),
            "forward_return": distribution(fwd),
            "mfe": distribution(mfe),
            "mae": distribution(mae),
            "time_to_mfe_ms": distribution([float(v) for v in ttmfe]),
            "time_to_mae_ms": distribution([float(v) for v in ttmae]),
        }
    return out


# ---------------------------------------------------------------- CLI ----

def _hist_db(path: Optional[str] = None):
    from .history_store import HistoryStore
    return HistoryStore(Path(path) if path else None)


def cmd_definitions(_args: argparse.Namespace) -> int:
    for fam in EVENT_FAMILIES:
        d = default_definition(fam)
        print(json.dumps({"family": fam, "version": d["definition_version"],
                          "parameters": d["parameters"],
                          "research_status": d["research_status"]},
                         indent=1, sort_keys=True))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from .history_store import HistoryStore
    store = HistoryStore(Path(args.db) if args.db else None)
    definition = default_definition(args.definition, args.version)
    store.upsert_event_definition(definition)
    bars = store.load_bars(args.symbol, args.interval,
                           "mark_klines" if args.mark else "klines")
    if args.mark and not bars:
        bars = store.load_bars(args.symbol, args.interval, "klines")
        ref_source = "regular_close (mark insufficient, labeled)"
    else:
        ref_source = ("mark_close" if args.mark else "regular_close")
    # time filter
    if args.start:
        bars = [b for b in bars if int(b["open_time"]) >= int(args.start)]
    if args.end:
        bars = [b for b in bars if int(b["open_time"]) <= int(args.end)]
    btc_bars: Optional[List[Dict[str, Any]]] = None
    if args.symbol != "BTCUSDT":
        try:
            btc_bars = store.load_bars("BTCUSDT", args.interval,
                                       "mark_klines" if args.mark else "klines")
        except Exception:
            btc_bars = None
    events = detect_events(bars, definition, args.symbol, ref_source,
                           args.interval, btc_bars)
    run_id = store.start_event_run(
        {"definition": args.definition, "version": args.version,
         "symbol": args.symbol, "interval": args.interval,
         "start": args.start, "end": args.end, "mark": bool(args.mark)})
    stored = store.store_event_instances(run_id, definition, events)
    # outcomes for fixed horizons over the same bar universe
    n_usable = 0
    for h in OUTCOME_HORIZON_ORDER:
        outs = [compute_outcome(
            e, bars,
            h, definition.get("parameters", {}).get("invalidation_pct"))
            for e in events]
        store.store_event_outcomes(run_id, outs, h)
        n_usable += sum(1 for o in outs if o.get("usable_for_statistics"))
    store.finish_event_run(run_id, len(events), n_usable)
    print(json.dumps({"run_id": run_id, "events": len(events),
                      "stored": stored, "reference_source": ref_source}))
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    store = _hist_db(args.db)
    rows = store.event_summary(args.definition, args.version)
    print(json.dumps({"definition": args.definition, "version": args.version,
                      "horizons": rows}, indent=1, sort_keys=True,
                     allow_nan=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Event studies (research only)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("definitions", help="list versioned research families")
    run = sub.add_parser("run", help="bounded deterministic study run")
    run.add_argument("--definition", required=True, choices=list(EVENT_FAMILIES))
    run.add_argument("--symbol", required=True)
    run.add_argument("--interval", default="15m")
    run.add_argument("--version", type=int, default=1)
    run.add_argument("--start", default=None)
    run.add_argument("--end", default=None)
    run.add_argument("--mark", action="store_true",
                     help="prefer mark-price klines (labeled)")
    run.add_argument("--db", default=None)
    summ = sub.add_parser("summary", help="summarize stored study outcomes")
    summ.add_argument("--definition", required=True)
    summ.add_argument("--version", type=int, default=1)
    summ.add_argument("--db", default=None)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "definitions":
        return cmd_definitions(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "summary":
        return cmd_summary(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
