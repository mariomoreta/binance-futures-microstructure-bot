"""Candidate extreme-movers selector (research only, NOT approved).

Version: SELECTOR-EXTREME-V1. Status: CANDIDATE (no methodology approval,
no threshold validation, no signal). Ranking is research priority
(ranking != entry), following the opportunity-engine discipline.

Reuse (delta minimo):
- discovery.py: eligibility dimensions (PERPETUAL/TRADING/USDT/volume
  floor) + bilateral boards (gainers/losers) + movement score idea.
  Historical universe/ranking snapshots do NOT exist -> the selector
  takes an injected universe provider (fixture-proven mechanism) and
  records UNKNOWN when history is absent. No coverage is invented.
- universe_manager.py: CORE protection + HOT lifecycle vocabulary
  (dwell/cooldown) reused as labels only; no live managed connections.
- classifier.py: state vocabulary (IGNITION/EXPANSION/EXHAUSTION/
  REVERSAL/NORMAL/UNKNOWN) reused as scenario language. Live
  flow/book/OI features do not exist historically -> the classifier
  itself is NOT replayed; thresholds stay HYPOTHESIS.
- opportunity.py: lifecycle (WATCH/DISCARDED/candidate) + ranking!=entry
  + freshness gates discipline. Live peer rows do not exist offline ->
  the engine is NOT replayed; only its contract is honored.
- events.py formation_features: the ONLY historically replayable input.
  Every selector input below is a field of that prefix-causal dict.

Inputs known at T (nothing else may enter):
  move_24h + anchor time | move_recent_1h | range_position |
  volume_percentile (own trailing history) | quote notional |
  coverage/formation_gap | available_at (close_time) |
  BTC context synced at/before T (ret_5m/15m/1h + relative) |
  universe membership/ranking at/before T (injected, may be UNKNOWN).
Deliberately excluded (unavailable, justified): RSI/ATR (no series),
market cap (no dated source -> UNKNOWN, never "low cap"), spread/depth
history (no venue history -> liquidity UNKNOWN), live flow/book/OI/VWAP.

Threshold provenance tags: INHERITED (from P1-11C v1, still HYPOTHESIS),
IMPL (implementation choice, reversible), NEW-HYPOTHESIS (needs review).
Nothing here was tuned against evaluation outcomes.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

SELECTOR_VERSION = "SELECTOR-EXTREME-V1"

VERDICT_WATCH = "WATCH"
VERDICT_DISCARDED = "DESCARTADO"

SIDE_UP = "UP"
SIDE_DOWN = "DOWN"

RULES: Dict[str, Any] = {
    # --- inherited HYPOTHESIS floors (P1-11C v1, NOT validated) ---
    "move_24h_min": 0.05,          # INHERITED (EXTENDED_* prior_24h)
    "move_recent_1h_min": 0.005,   # INHERITED (EXTENDED_* prior_1h)
    # --- implementation choices (reversible, no edge claim) ---
    "min_bars_for_volume": 5,      # IMPL (matches formation_features gate)
    "ranking_weights": {           # NEW-HYPOTHESIS (needs review)
        "movement": 3.0,
        "recent": 2.0,
        "volume": 1.0,
        "freshness": 1.0,
        "btc_confirmation": 1.0,
    },
    "volume_percentile_min": 0.5,  # NEW-HYPOTHESIS (needs review)
}

RULES_PROVENANCE = {
    "move_24h_min": "INHERITED-P1-11C-v1-HYPOTHESIS",
    "move_recent_1h_min": "INHERITED-P1-11C-v1-HYPOTHESIS",
    "min_bars_for_volume": "IMPL",
    "ranking_weights": "NEW-HYPOTHESIS",
    "volume_percentile_min": "NEW-HYPOTHESIS",
}


def _num(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _universe_at(universe: Optional[Dict[str, Any]], symbol: str) -> Dict[str, Any]:
    """Universe membership known at/before T, or explicit UNKNOWN."""
    if not universe:
        return {"known": False, "eligible": None, "rank": None,
                "reason": "no-universe-history"}
    entry = universe.get(symbol.upper())
    if not entry:
        return {"known": False, "eligible": None, "rank": None,
                "reason": "symbol-absent-from-universe"}
    return {"known": True, "eligible": bool(entry.get("eligible")),
            "rank": entry.get("rank"),
            "as_of": entry.get("as_of"),
            "reason": None if entry.get("eligible") else "universe-ineligible"}


def select(features: Dict[str, Any],
           universe: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Score one prefix-causal feature dict. Pure function of (features, universe).

    Returns WATCH (side + scenario tags + confirmations needed + rank score)
    or DESCARTADO (reason). Never an entry order.
    """
    symbol = str(features.get("symbol", "UNKNOWN"))
    move24 = _num(features.get("prior_24h_return"))
    move1h = _num(features.get("prior_1h_return"))
    range_pos = _num(features.get("range_position"))
    vol_pct = _num(features.get("volume_percentile"))
    gap = bool(features.get("formation_gap"))
    available = features.get("available_at_consumer", "close_time-chain")
    btc = features.get("btc_context") or {}
    btc_ok = bool(btc.get("available"))
    rel1h = _num(features.get("relative_return_1h"))
    uni = _universe_at(universe, symbol)

    fav: List[str] = []
    against: List[str] = []
    missing: List[str] = ["market-cap (no dated source -> UNKNOWN)",
                          "liquidity/spread-depth history (UNKNOWN)"]
    if move24 is None:
        missing.append("prior_24h_return")
    if move1h is None:
        missing.append("prior_1h_return")
    if range_pos is None:
        missing.append("range_position")
    if vol_pct is None:
        missing.append("volume_percentile")
    if not btc_ok:
        missing.append("btc-context")
    if not uni["known"]:
        missing.append("universe/ranking at T (%s)" % uni["reason"])

    if gap:
        return {"selector_version": SELECTOR_VERSION, "symbol": symbol,
                "verdict": VERDICT_DISCARDED, "reason": "formation-gap",
                "favorable": fav, "against": against, "missing": missing,
                "rules_provenance": RULES_PROVENANCE}
    if move24 is None or move1h is None:
        return {"selector_version": SELECTOR_VERSION, "symbol": symbol,
                "verdict": VERDICT_DISCARDED, "reason": "missing-move-features",
                "favorable": fav, "against": against, "missing": missing,
                "rules_provenance": RULES_PROVENANCE}
    side = None
    if move24 >= RULES["move_24h_min"] and move1h >= 0:
        side = SIDE_UP
    elif move24 <= -RULES["move_24h_min"] and move1h <= 0:
        side = SIDE_DOWN
    if side is None:
        return {"selector_version": SELECTOR_VERSION, "symbol": symbol,
                "verdict": VERDICT_DISCARDED, "reason": "below-move-floors",
                "favorable": fav, "against": against, "missing": missing,
                "rules_provenance": RULES_PROVENANCE}
    if abs(move1h) < RULES["move_recent_1h_min"]:
        against.append("recent-move-weak")
    else:
        fav.append("recent-confirms-24h" if (move1h > 0) == (side == SIDE_UP)
                   else "recent-diverges")
    if vol_pct is not None:
        if vol_pct >= RULES["volume_percentile_min"]:
            fav.append("volume-elevated-vs-own-history")
        else:
            against.append("thin-vs-own-history")
    if btc_ok and rel1h is not None:
        if (rel1h > 0) == (side == SIDE_UP):
            fav.append("relative-strength-vs-btc")
        else:
            against.append("lags-btc")
    # scenario tags reuse classifier vocabulary (language only, no replay)
    scenarios: List[str] = []
    if side == SIDE_UP:
        scenarios.append("H1-continuation-candidate")
        if range_pos is not None and range_pos >= 0.8:
            scenarios.append("H2-exhaustion-watch")
    else:
        scenarios.append("H3-continuation-candidate")
        if range_pos is not None and range_pos <= 0.2:
            scenarios.append("H2-reversal-watch")
    scenarios.append("H2-rebound-variant-excluded (no bounce definition)")
    w = RULES["ranking_weights"]
    score = (w["movement"] * abs(move24) + w["recent"] * abs(move1h)
             + w["volume"] * (vol_pct or 0.0)
             + w["freshness"] * (1.0 if available else 0.0)
             + w["btc_confirmation"] * (1.0 if ("relative-strength-vs-btc" in fav)
                                        else 0.0))
    confirmations_needed = [
        "live formation proof (streaming detector at close_time)",
        "universe/ranking history at T (currently %s)" % (
            "known" if uni["known"] else "UNKNOWN"),
        "liquidity evidence (spread/depth history absent)",
        "approved mapping + costs + pristine window (protocol)",
    ]
    _ = range_pos
    return {"selector_version": SELECTOR_VERSION, "symbol": symbol,
            "verdict": VERDICT_WATCH, "side": side,
            "scenarios": scenarios, "rank_score": score,
            "ranking_note": "research priority only; ranking != entry",
            "favorable": fav, "against": against, "missing": missing,
            "universe": uni, "btc_available": btc_ok,
            "confirmations_needed": confirmations_needed,
            "rules_provenance": RULES_PROVENANCE}


def rank_board(verdicts: List[Dict[str, Any]],
               side: str) -> List[Dict[str, Any]]:
    """One deterministic board per side (gainers / losers)."""
    rows = [v for v in verdicts
            if v.get("verdict") == VERDICT_WATCH and v.get("side") == side]
    rows.sort(key=lambda v: (-v.get("rank_score", 0.0), v.get("symbol", "")))
    return rows


def input_coverage() -> Dict[str, Any]:
    """Real-dataset input availability per series (no extrapolation)."""
    return {
        "move_24h": "available (klines regular_close; anchor recorded)",
        "move_recent_1h": "available",
        "range_position": "available",
        "volume_percentile_own": "available (regular klines carry volume)",
        "quote_notional": "available (quote_volume)",
        "coverage_formation_gap": "available",
        "freshness_close_time": "available (chain 0 violations)",
        "btc_context_synced": "available trio 15m/1h + MINA/NMR/ORCA 1h"
                              " (BTC same-interval bars); UNKNOWN if BTC gaps",
        "liquidity_spread_depth": "UNKNOWN (no venue depth history ingested)",
        "universe_ranking_history": "UNKNOWN (discovery snapshots not retained"
                                    " historically; mechanism fixture-proven)",
        "market_cap": "UNKNOWN (no dated source; never low-cap-by-proxy)",
        "live_flow_book_oi_vwap": "UNKNOWN offline (live-only engines)",
        "consequence": "every census detection is at best PARTIAL-input;"
                       " full-input decisions are impossible on this dataset",
    }
