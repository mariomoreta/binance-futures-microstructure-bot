"""P1-13A research opportunity / setup engine v0 (OBSERVE ONLY).

Identifies market setups worthy of further research from already-built
peer-engine state. Consumes P1-12A classifications (never recomputes them),
P1-12B LIVE universe membership, returns/velocity/acceleration, aggressive
flow, book, OI, VWAP/volatility/structure rows, and historical-study
references where legitimately applicable.

Research lifecycle states (DETECTED/WATCHING/ACTIVE_RESEARCH/INVALIDATED/
EXPIRED/UNKNOWN) are research tracking only — never orders or positions.
Ranking is research priority, never expected profit or win probability.
No confidence percentages, no entries/exits/stops/targets, no lookahead:
every evaluation consumes records computed at or before the observation
instant. All thresholds are HYPOTHESIS (see RULES + docs/OPPORTUNITY_ENGINE_SPEC.md).
"""

from __future__ import annotations

import math
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

OPPORTUNITY_RULES_VERSION = "v0.1.0"

FAMILY_MOMENTUM_CONTINUATION = "MOMENTUM_CONTINUATION"
FAMILY_IGNITION_WATCH = "IGNITION_WATCH"
FAMILY_EXHAUSTION_WATCH = "EXHAUSTION_WATCH"
FAMILY_REVERSAL_WATCH = "REVERSAL_WATCH"
FAMILY_EXTREME_MOVE_RESEARCH = "EXTREME_MOVE_RESEARCH"

FAMILIES = (
    FAMILY_MOMENTUM_CONTINUATION,
    FAMILY_IGNITION_WATCH,
    FAMILY_EXHAUSTION_WATCH,
    FAMILY_REVERSAL_WATCH,
    FAMILY_EXTREME_MOVE_RESEARCH,
)

# Setup family -> required classifier state (consumed, never recomputed).
FAMILY_STATE = {
    FAMILY_MOMENTUM_CONTINUATION: "EXPANSION",
    FAMILY_IGNITION_WATCH: "IGNITION",
    FAMILY_EXHAUSTION_WATCH: "EXHAUSTION",
    FAMILY_REVERSAL_WATCH: "REVERSAL",
    FAMILY_EXTREME_MOVE_RESEARCH: None,  # any energetic state; size-gated
}

EXTREME_OK_STATES = ("EXPANSION", "EXHAUSTION", "IGNITION")

LIFECYCLE_DETECTED = "DETECTED"
LIFECYCLE_WATCHING = "WATCHING"
LIFECYCLE_ACTIVE_RESEARCH = "ACTIVE_RESEARCH"
LIFECYCLE_INVALIDATED = "INVALIDATED"
LIFECYCLE_EXPIRED = "EXPIRED"
LIFECYCLE_UNKNOWN = "UNKNOWN"

LIFECYCLES = (
    LIFECYCLE_DETECTED,
    LIFECYCLE_WATCHING,
    LIFECYCLE_ACTIVE_RESEARCH,
    LIFECYCLE_INVALIDATED,
    LIFECYCLE_EXPIRED,
    LIFECYCLE_UNKNOWN,
)

ELIGIBLE = "ELIGIBLE"
INELIGIBLE = "INELIGIBLE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

DIR_UP = "UP"
DIR_DOWN = "DOWN"
DIR_NONE = "NONE"
DIR_UNKNOWN = "UNKNOWN"

_SYMBOL_RE = re.compile(r"^[A-Z0-9]+USDT$")

# HYPOTHESIS thresholds and lifecycle policy (units documented per key).
RULES: Dict[str, Any] = {
    "max_sample_age_ms": 300_000,      # mandatory price freshness (markPrice)
    "max_state_age_ms": 120_000,       # classification as-of compatibility
    "extreme_move_ret_min": 0.01,      # |log return| on 15m or 1h (size gate)
    "extreme_move_vel_min_per_s": 2e-6,  # corroborating motion floor (1/s)
    "ranking_weights": {               # HYPOTHESIS; research priority only
        "movement": 3.0,
        "corroboration": 2.0,
        "activity": 1.0,
        "freshness": 1.0,
        "completeness": 1.0,
        "state_compat": 1.0,
        "counterevidence_penalty": 2.0,
    },
    "watching_evals": 2,               # consecutive evals -> WATCHING
    "active_research_evals": 3,        # consecutive evals -> ACTIVE_RESEARCH
    "cooldown_ms": 3_600_000,          # re-DETECT block after INVALID/EXPIRE
    "ttl_ms": 86_400_000,              # candidate expiry (24h)
    "max_candidates": 200,             # bounded retention
    "max_eval_ms_budget": 5.0,         # per-evaluation soft budget (measured)
}


def _num(value: Any) -> Optional[float]:
    """Finite float or None (missing is never 0 — enforced here)."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _get(record: Dict[str, Any], *path: str) -> Any:
    node: Any = record
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def normalize_symbol(symbol: Any) -> Optional[str]:
    """Uppercase USDT-M symbol identity, or None when malformed."""
    if not isinstance(symbol, str):
        return None
    candidate = symbol.strip().upper()
    if not _SYMBOL_RE.match(candidate):
        return None
    return candidate


def historical_reference(
    family: str,
    lookup: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Historical-study reference for a setup family.

    Without an explicit mapping + comparable timestamps there is no claim:
    returns INSUFFICIENT_HISTORICAL_EVIDENCE. Never invents win rates,
    MFE/MAE, expected returns, or significance.
    """
    if lookup is not None:
        try:
            mapped = lookup(family)
        except Exception:
            mapped = None
        if isinstance(mapped, dict) and mapped.get("study_id"):
            return {
                "status": "MAPPED",
                "study_id": str(mapped.get("study_id")),
                "note": str(mapped.get("note", "explicit mapping supplied")),
            }
    return {
        "status": "INSUFFICIENT_HISTORICAL_EVIDENCE",
        "reason": ("no explicit mapping from setup family %s to a "
                   "historical event family with comparable timestamps" % family),
    }


def _ranking(
    movement: float,
    corroboration: int,
    activity: float,
    freshness_s: Optional[float],
    completeness: float,
    state_compat: float,
    counterevidence: int,
    weights: Dict[str, float],
) -> Dict[str, Any]:
    """Transparent research-priority score with exposed components."""
    freshness_term = 0.0
    if freshness_s is not None and freshness_s >= 0:
        freshness_term = max(0.0, 1.0 - min(1.0, freshness_s / 300.0))
    score = (
        weights.get("movement", 0.0) * min(1.0, movement)
        + weights.get("corroboration", 0.0) * min(1.0, corroboration / 3.0)
        + weights.get("activity", 0.0) * min(1.0, activity)
        + weights.get("freshness", 0.0) * freshness_term
        + weights.get("completeness", 0.0) * completeness
        + weights.get("state_compat", 0.0) * state_compat
        - weights.get("counterevidence_penalty", 0.0) * min(1.0, counterevidence / 3.0)
    )
    return {
        "score": round(score, 4),
        "weights_version": OPPORTUNITY_RULES_VERSION,
        "weights_hypothesis": True,
        "components": {
            "movement": round(min(1.0, movement), 4),
            "corroboration": int(corroboration),
            "activity": round(min(1.0, activity), 4),
            "freshness_s": freshness_s,
            "completeness": round(completeness, 4),
            "state_compat": round(state_compat, 4),
            "counterevidence": int(counterevidence),
        },
        "interpretation": "research priority only — NOT expected profit or win probability",
    }


def evaluate_symbol(
    symbol: str,
    bundle: Dict[str, Any],
    as_of_ms: int,
    rules: Optional[Dict[str, Any]] = None,
    historical_lookup: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Evaluate one symbol bundle into (matched, rejected) setup records.

    Never reaches into live engines or future data: everything comes from
    the supplied bundle (classification + feature rows + tier/transport).
    Rejected records carry eligibility reasons and lifecycle UNKNOWN — the
    caller decides retention; deep setups never accept them.
    """
    cfg = rules or RULES
    matched: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    sym = normalize_symbol(symbol)
    if sym is None:
        rejected.append(_rejection(
            str(symbol), as_of_ms, INELIGIBLE,
            "symbol identity invalid: expected uppercase <BASE>USDT",
            ["valid_symbol"], cfg))
        return matched, rejected

    tier = str(bundle.get("tier", "DISCOVERY")).upper()
    subscribed = bool(bundle.get("subscribed", False))
    live = bool(bundle.get("live", subscribed and tier in ("CORE", "HOT")))
    classification = bundle.get("classification")
    if not isinstance(classification, dict) or not classification:
        rejected.append(_rejection(
            sym, as_of_ms, INSUFFICIENT_DATA,
            "missing classification record (classifier warming or absent)",
            ["classification"], cfg, tier=tier))
        return matched, rejected

    if not subscribed or not live or tier not in ("CORE", "HOT"):
        rejected.append(_rejection(
            sym, as_of_ms, INELIGIBLE,
            "discovery-only coverage: no LIVE deep-data capability (%s)" % tier,
            ["live_subscription"], cfg, tier=tier,
            classification=classification))
        return matched, rejected

    transport = bundle.get("transport") if isinstance(
        bundle.get("transport"), dict) else {}
    if transport.get("degraded") is True:
        rejected.append(_rejection(
            sym, as_of_ms, INSUFFICIENT_DATA,
            "unresolved transport degradation for mandatory inputs: %s"
            % transport.get("reason", "stale mandatory stream"),
            ["healthy_transport"], cfg, tier=tier,
            classification=classification))
        return matched, rejected

    state = str(classification.get("state", "UNKNOWN"))
    direction = str(classification.get("direction", "UNKNOWN"))
    classifier_version = str(classification.get("rules_version", "?"))
    observed_at = _num(classification.get("observed_at_ms"))
    max_state_age = int(cfg.get("max_state_age_ms", 120_000))
    if observed_at is None or abs(int(as_of_ms) - int(observed_at)) > max_state_age:
        rejected.append(_rejection(
            sym, as_of_ms, INSUFFICIENT_DATA,
            "classification as-of incompatible: observed_at_ms=%s (limit %dms)"
            % (observed_at, max_state_age),
            ["compatible_classification_timestamp"], cfg, tier=tier,
            classification=classification))
        return matched, rejected

    features = bundle.get("features") if isinstance(
        bundle.get("features"), dict) else {}
    price = _get(features, "price", "current_price")
    if price is None:
        price = _num(features.get("current_price"))
    else:
        price = _num(price)
    age_ms = _num(_get(features, "price", "sample_age_ms"))
    if age_ms is None:
        age_ms = _num(features.get("sample_age_ms"))
    max_age = int(cfg.get("max_sample_age_ms", 300_000))
    if price is None or age_ms is None or age_ms < 0 or age_ms > max_age:
        missing = ["fresh_price"] if price is None or age_ms is None \
            else ["fresh_price"]
        rejected.append(_rejection(
            sym, as_of_ms, INSUFFICIENT_DATA,
            "stale mandatory price input: age_ms=%s (limit %dms)"
            % (age_ms, max_age),
            missing, cfg, tier=tier, classification=classification))
        return matched, rejected

    if state == "UNKNOWN" or direction not in (DIR_UP, DIR_DOWN, DIR_NONE):
        rejected.append(_rejection(
            sym, as_of_ms, INSUFFICIENT_DATA,
            "valid market-state context required: state=%s direction=%s"
            % (state, direction),
            ["valid_market_state"], cfg, tier=tier,
            classification=classification))
        return matched, rejected

    # Shared raw measurements (T-known rows only; missing stays missing).
    ret = _get(features, "returns", "returns")
    ret1m = _num(ret.get("1m")) if isinstance(ret, dict) else None
    ret15m = _num(ret.get("15m")) if isinstance(ret, dict) else None
    ret1h = _num(ret.get("1h")) if isinstance(ret, dict) else None
    mom = features.get("momentum") if isinstance(
        features.get("momentum"), dict) else {}
    vel = mom.get("velocity") if isinstance(mom.get("velocity"), dict) else {}
    acc = mom.get("acceleration") if isinstance(
        mom.get("acceleration"), dict) else {}
    vel1m = _num(vel.get("1m"))
    acc1m = _num(acc.get("1m"))
    flow = features.get("flow") if isinstance(features.get("flow"), dict) else {}
    horizons = flow.get("horizons") if isinstance(
        flow.get("horizons"), dict) else {}
    h1m = horizons.get("1m") if isinstance(horizons.get("1m"), dict) else {}
    flow_delta = _num(h1m.get("signed_delta"))
    flow_ratio = _num(h1m.get("delta_ratio"))
    flow_notional = _num(h1m.get("notional"))
    baselines = flow.get("baselines") if isinstance(
        flow.get("baselines"), dict) else {}
    b1m = baselines.get("1m") if isinstance(baselines.get("1m"), dict) else {}
    vol_z = _num(b1m.get("z_score"))
    struct = features.get("structure") if isinstance(
        features.get("structure"), dict) else {}
    ranges = struct.get("ranges") if isinstance(struct.get("ranges"), dict) else {}
    r15m = ranges.get("15m") if isinstance(ranges.get("15m"), dict) else {}
    expansion_ratio = _num(r15m.get("expansion_ratio"))
    range_pos = _num(r15m.get("range_position"))
    structure = struct.get("structure") if isinstance(
        struct.get("structure"), dict) else {}
    breakout = structure.get("breakout_state")
    vol = struct.get("volatility") if isinstance(
        struct.get("volatility"), dict) else {}
    v15m = vol.get("15m") if isinstance(vol.get("15m"), dict) else {}
    realized_vol = _num(v15m.get("realized_vol"))
    book = features.get("book") if isinstance(features.get("book"), dict) else {}
    imbalance = _num(book.get("imbalance_notional"))
    if imbalance is None:
        imbalance = _num(book.get("imbalance_qty"))
    oi = features.get("oi") if isinstance(features.get("oi"), dict) else {}
    oi_h = oi.get("horizons") if isinstance(oi.get("horizons"), dict) else {}
    oi1m = oi_h.get("1m") if isinstance(oi_h.get("1m"), dict) else {}
    oi_delta = _num(oi1m.get("delta"))

    evidence_against = list(classification.get("evidence_against") or [])
    missing_all = list(classification.get("missing_features") or [])
    market = str(bundle.get("market", "%s USDT-M PERP" % sym))
    freshness_s = round(float(age_ms) / 1000.0, 1)  # price-sample age
    weights = cfg.get("ranking_weights") if isinstance(
        cfg.get("ranking_weights"), dict) else {}

    def base_record(family: str, observed_dir: str,
                    evidence_for: List[str], counter: List[str],
                    missing: List[str], movement: float,
                    corroboration: int, activity: float,
                    completeness: float, reason: str) -> Dict[str, Any]:
        key = "%s:%s:%s" % (family, sym, observed_dir)
        return {
            "candidate_key": key,
            "candidate_id": key,
            "setup_family": family,
            "rule_version": OPPORTUNITY_RULES_VERSION,
            "observed_at_ms": int(as_of_ms),
            "symbol": sym,
            "market": market,
            "direction": observed_dir,
            "eligibility": ELIGIBLE,
            "eligibility_reason": reason,
            "capability_tier": tier,
            "market_state": state,
            "classifier_version": classifier_version,
            "classification_observed_at_ms": int(observed_at or 0),
            "evidence_for": sorted(set(evidence_for)),
            "evidence_against": sorted(set(counter)),
            "missing_features": sorted(set(missing)),
            "thresholds": _thresholds_for(family, cfg),
            "ranking": _ranking(movement, corroboration, activity,
                                freshness_s, completeness, 1.0,
                                len(counter), weights),
            "historical_reference": historical_reference(
                family, historical_lookup),
            "lifecycle": LIFECYCLE_DETECTED,
            "lifecycle_reason": "first evaluation matched family rules",
            "evals_in_lifecycle": 1,
            "data_freshness": {
                "price_age_ms": age_ms,
                "state_age_ms": abs(int(as_of_ms) - int(observed_at or 0)),
            },
        }

    dir_sign = 1 if direction == DIR_UP else -1 if direction == DIR_DOWN else 0
    big_ret = ret15m if ret15m is not None else ret1h

    # Completeness: fraction of the 10 headline inputs present.
    present = sum(1 for v in (vel1m, acc1m, flow_ratio, flow_notional,
                              vol_z, expansion_ratio, range_pos, imbalance,
                              oi_delta, realized_vol) if v is not None)
    completeness = present / 10.0
    activity = 0.0
    if flow_notional is not None and flow_notional > 0:
        activity = min(1.0, abs(flow_delta or 0.0) / flow_notional)

    # A. MOMENTUM_CONTINUATION — EXPANSION + consistent direction/motion/flow.
    if state == "EXPANSION" and direction in (DIR_UP, DIR_DOWN) and big_ret is not None:
        agree = flow_ratio is not None and dir_sign != 0 and (
            (flow_ratio > 0) == (dir_sign > 0))
        vel_ok = vel1m is not None and dir_sign != 0 and (
            (vel1m > 0) == (dir_sign > 0))
        if agree and vel_ok:
            matched.append(base_record(
                FAMILY_MOMENTUM_CONTINUATION, direction,
                ["state EXPANSION (%s)" % classifier_version,
                 "return_15m/1h %.4f" % big_ret,
                 "velocity_1m %.3g/s consistent" % (vel1m or 0.0),
                 "flow agrees (ratio %+.2f)" % (flow_ratio or 0.0)],
                evidence_against, missing_all,
                min(1.0, abs(big_ret) / 0.01),
                2 + (1 if expansion_ratio is not None and expansion_ratio >= 1.5 else 0),
                activity, completeness,
                "EXPANSION with direction-consistent velocity and agreeing flow"))
        else:
            rejected.append(_rejection(
                sym, as_of_ms, INELIGIBLE,
                "MOMENTUM_CONTINUATION corroboration missing "
                "(velocity/flow must agree with direction)",
                ["corroborating_momentum"], cfg, tier=tier,
                classification=classification, family=FAMILY_MOMENTUM_CONTINUATION))

    # B. IGNITION_WATCH — IGNITION + emerging acceleration evidence.
    if state == "IGNITION" and direction in (DIR_UP, DIR_DOWN):
        ignition_evidence = ["state IGNITION (%s)" % classifier_version]
        if vel1m is not None:
            ignition_evidence.append("velocity_1m %.3g/s" % vel1m)
        matched.append(base_record(
            FAMILY_IGNITION_WATCH, direction,
            ignition_evidence,
            evidence_against, missing_all,
            min(1.0, abs(vel1m or 0.0) / 1e-5),
            len([e for e in (classification.get("evidence_for") or [])
                 if isinstance(e, str)]),
            activity, completeness,
            "IGNITION state warrants monitoring, not action"))

    # C. EXHAUSTION_WATCH — EXHAUSTION after an established move.
    if state == "EXHAUSTION" and direction in (DIR_UP, DIR_DOWN):
        matched.append(base_record(
            FAMILY_EXHAUSTION_WATCH, direction,
            ["state EXHAUSTION (%s)" % classifier_version,
             "prior move direction %s losing strength" % direction],
            evidence_against, missing_all,
            min(1.0, abs(big_ret or 0.0) / 0.01),
            len([e for e in (classification.get("evidence_for") or [])
                 if isinstance(e, str)]),
            activity, completeness,
            "EXHAUSTION: loss of directional strength after a move"))

    # D. REVERSAL_WATCH — REVERSAL with confirmation requirements.
    if state == "REVERSAL" and direction in (DIR_UP, DIR_DOWN):
        confirmed = any("confirm" in str(e).lower()
                        for e in (classification.get("evidence_for") or []))
        flow_ok = flow_ratio is not None and dir_sign != 0 and (
            (flow_ratio > 0) == (dir_sign > 0))
        struct_ok = breakout in ("ABOVE_PRIOR_RANGE", "BELOW_PRIOR_RANGE")
        if confirmed or (flow_ok and struct_ok):
            matched.append(base_record(
                FAMILY_REVERSAL_WATCH, direction,
                ["state REVERSAL (%s)" % classifier_version,
                 "new direction %s with confirmation" % direction],
                evidence_against, missing_all,
                min(1.0, abs(vel1m or 0.0) / 1e-5),
                (1 if confirmed else 0) + (1 if flow_ok else 0)
                + (1 if struct_ok else 0),
                activity, completeness,
                "REVERSAL with confirmation requirements met"))
        else:
            rejected.append(_rejection(
                sym, as_of_ms, INELIGIBLE,
                "REVERSAL_WATCH confirmation missing "
                "(needs classifier confirmation or flow+structure)",
                ["reversal_confirmation"], cfg, tier=tier,
                classification=classification, family=FAMILY_REVERSAL_WATCH))

    # E. EXTREME_MOVE_RESEARCH — unusually large move; study, not fade.
    if big_ret is not None and abs(big_ret) >= float(
            cfg.get("extreme_move_ret_min", 0.01)) and state in EXTREME_OK_STATES:
        extreme_dir = DIR_UP if big_ret > 0 else DIR_DOWN
        matched.append(base_record(
            FAMILY_EXTREME_MOVE_RESEARCH, extreme_dir,
            ["|return| %.4f >= %.4f (research only, not a fade)"
             % (abs(big_ret), float(cfg.get("extreme_move_ret_min", 0.01))),
             "state %s" % state],
            evidence_against, missing_all,
            min(1.0, abs(big_ret) / 0.03),
            1 + (1 if vel1m is not None and (
                (vel1m > 0) == (big_ret > 0)) else 0),
            activity, completeness,
            "extreme move warrants detailed study, not automatic contrarian action"))

    return matched, rejected


def _rejection(symbol: str, as_of_ms: int, eligibility: str, reason: str,
               missing: List[str], cfg: Dict[str, Any],
               tier: str = "UNKNOWN",
               classification: Optional[Dict[str, Any]] = None,
               family: Optional[str] = None) -> Dict[str, Any]:
    state = str((classification or {}).get("state", "UNKNOWN"))
    direction = str((classification or {}).get("direction", "UNKNOWN"))
    return {
        "candidate_key": None,
        "setup_family": family or "NONE",
        "rule_version": OPPORTUNITY_RULES_VERSION,
        "observed_at_ms": int(as_of_ms),
        "symbol": symbol,
        "market": "%s USDT-M PERP" % symbol if symbol else "UNKNOWN",
        "direction": direction,
        "eligibility": eligibility,
        "eligibility_reason": reason,
        "capability_tier": tier,
        "market_state": state,
        "classifier_version": str((classification or {}).get(
            "rules_version", "?")),
        "evidence_for": [],
        "evidence_against": list((classification or {}).get(
            "evidence_against", []) or []),
        "missing_features": sorted(set(missing)),
        "thresholds": {},
        "ranking": None,
        "historical_reference": {"status": "INSUFFICIENT_HISTORICAL_EVIDENCE",
                                 "reason": "rejected before family match"},
        "lifecycle": LIFECYCLE_UNKNOWN,
        "lifecycle_reason": reason,
        "evals_in_lifecycle": 0,
    }


def _thresholds_for(family: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    base = {
        "max_sample_age_ms": {"value": cfg.get("max_sample_age_ms"),
                              "unit": "ms"},
        "max_state_age_ms": {"value": cfg.get("max_state_age_ms"),
                             "unit": "ms"},
    }
    if family == FAMILY_EXTREME_MOVE_RESEARCH:
        base["extreme_move_ret_min"] = {
            "value": cfg.get("extreme_move_ret_min"), "unit": "log_return"}
        base["extreme_move_vel_min_per_s"] = {
            "value": cfg.get("extreme_move_vel_min_per_s"), "unit": "1/s"}
    return base


class OpportunityEngine:
    """Bounded per-candidate lifecycle memory + deterministic evaluation."""

    def __init__(self, rules: Optional[Dict[str, Any]] = None,
                 historical_lookup: Optional[Callable[
                     [str], Optional[Dict[str, Any]]]] = None) -> None:
        self.rules = dict(rules or RULES)
        self._historical_lookup = historical_lookup
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._cooldown_until: Dict[str, int] = {}
        self._pending_closed: List[Dict[str, Any]] = []
        self.evaluated = 0
        self.detected = 0
        self.rejected = 0
        self.last_eval_ms: Optional[float] = None
        self.max_eval_ms = 0.0

    def note_eval_ms(self, elapsed_ms: float) -> None:
        try:
            value = max(0.0, float(elapsed_ms))
        except (TypeError, ValueError):
            return
        self.last_eval_ms = value
        self.max_eval_ms = max(self.max_eval_ms, value)

    def evaluate(self, bundles: Dict[str, Dict[str, Any]],
                 as_of_ms: int) -> Tuple[List[Dict[str, Any]],
                                        List[Dict[str, Any]]]:
        """Evaluate all symbol bundles at one instant (no lookahead)."""
        matched_now: List[Dict[str, Any]] = []
        rejected_now: List[Dict[str, Any]] = []
        seen_keys: set = set()
        for symbol in sorted(bundles):
            fresh, rej = evaluate_symbol(
                symbol, bundles[symbol] or {}, int(as_of_ms),
                self.rules, self._historical_lookup)
            rejected_now.extend(rej)
            for cand in fresh:
                key = str(cand["candidate_key"])
                seen_keys.add(key)
                if self._in_cooldown(key, int(as_of_ms)):
                    rej_rec = _rejection(
                        str(cand["symbol"]), int(as_of_ms), INELIGIBLE,
                        "cooldown active after prior INVALIDATED/EXPIRED",
                        ["cooldown_elapsed"], self.rules,
                        tier=str(cand.get("capability_tier", "?")),
                        classification={"state": cand.get("market_state"),
                                        "direction": cand.get("direction"),
                                        "rules_version": cand.get(
                                            "classifier_version")},
                        family=str(cand.get("setup_family")))
                    rejected_now.append(rej_rec)
                    continue
                prev = self._memory.get(key)
                cand = self._apply_lifecycle(cand, prev, int(as_of_ms))
                self._memory[key] = _mem_from(cand)
                matched_now.append(cand)
        self._invalidate_absent(seen_keys, int(as_of_ms))
        self._expire(int(as_of_ms))
        self._enforce_bounds()
        # Returned records must reflect post-expiry truth: a candidate
        # that kept matching but aged past TTL reports EXPIRED (and is
        # still persisted, so the store never shows a stale open state).
        # Absent-rule closures are reported via drain_closed_events.
        for cand in matched_now:
            mem = self._memory.get(str(cand.get("candidate_key")))
            if mem is None:
                continue
            cand["lifecycle"] = mem.get("lifecycle")
            cand["lifecycle_reason"] = mem.get("lifecycle_reason", "")
            cand["evals_in_lifecycle"] = mem.get("evals_in_lifecycle", 1)
        self.evaluated += len(bundles)
        self.detected += len(matched_now)
        self.rejected += len(rejected_now)
        matched_now.sort(key=lambda c: (
            -(c.get("ranking") or {}).get("score", 0.0),
            str(c.get("symbol")), str(c.get("setup_family"))))
        return matched_now, rejected_now

    def drain_closed_events(self) -> List[Dict[str, Any]]:
        """Newly INVALIDATED/EXPIRED closures since the last drain.

        The probe persists these to the bounded opportunity event log for
        audit, then they are cleared. Open candidates are never reported
        here.
        """
        out = list(self._pending_closed)
        self._pending_closed = []
        return out

    def _close(self, key: str, mem: Dict[str, Any], lifecycle: str,
               reason: str, as_of_ms: int) -> None:
        mem["lifecycle"] = lifecycle
        mem["lifecycle_reason"] = reason
        mem["invalidated_at_ms"] = int(as_of_ms)
        self._cooldown_until[key] = int(as_of_ms) + int(
            self.rules.get("cooldown_ms", 3_600_000))
        self._pending_closed.append({
            "candidate_key": key,
            "symbol": mem.get("symbol", "?"),
            "family": mem.get("setup_family", "?"),
            "transition": lifecycle,
            "reason": reason,
        })

    def _in_cooldown(self, key: str, as_of_ms: int) -> bool:
        until = self._cooldown_until.get(key)
        if until is None:
            return False
        if int(as_of_ms) >= int(until):
            self._cooldown_until.pop(key, None)
            return False
        return True

    def _apply_lifecycle(self, cand: Dict[str, Any],
                         prev: Optional[Dict[str, Any]],
                         as_of_ms: int) -> Dict[str, Any]:
        cfg = self.rules
        if prev is None:
            cand["lifecycle"] = LIFECYCLE_DETECTED
            cand["lifecycle_reason"] = "first evaluation matched family rules"
            cand["evals_in_lifecycle"] = 1
            return cand
        if prev.get("lifecycle") in (LIFECYCLE_INVALIDATED, LIFECYCLE_EXPIRED):
            if prev.get("lifecycle") == LIFECYCLE_EXPIRED:
                first = int(prev.get("first_observed_at_ms",
                                     prev.get("observed_at_ms", as_of_ms)))
                if int(as_of_ms) - first >= int(
                        cfg.get("ttl_ms", 86_400_000)):
                    # Still past TTL: stay EXPIRED without re-detecting
                    # (no new close event; the closure was already
                    # reported via drain_closed_events).
                    cand["lifecycle"] = LIFECYCLE_EXPIRED
                    cand["lifecycle_reason"] = "retention TTL elapsed"
                    cand["evals_in_lifecycle"] = int(
                        prev.get("evals_in_lifecycle", 0)) + 1
                    return cand
            cand["lifecycle"] = LIFECYCLE_DETECTED
            cand["lifecycle_reason"] = "re-detected after %s (cooldown elapsed)" % prev.get(
                "lifecycle")
            cand["evals_in_lifecycle"] = 1
            return cand
        evals = int(prev.get("evals_in_lifecycle", 0)) + 1
        cand["evals_in_lifecycle"] = evals
        if evals >= int(cfg.get("active_research_evals", 3)):
            if prev.get("lifecycle") != LIFECYCLE_ACTIVE_RESEARCH:
                cand["lifecycle"] = LIFECYCLE_ACTIVE_RESEARCH
                cand["lifecycle_reason"] = (
                    "matched %d consecutive evaluations" % evals)
            else:
                cand["lifecycle"] = LIFECYCLE_ACTIVE_RESEARCH
                cand["lifecycle_reason"] = "still matching family rules"
        elif evals >= int(cfg.get("watching_evals", 2)):
            cand["lifecycle"] = LIFECYCLE_WATCHING
            cand["lifecycle_reason"] = (
                "matched %d consecutive evaluations" % evals)
        else:
            cand["lifecycle"] = LIFECYCLE_DETECTED
            cand["lifecycle_reason"] = "first evaluation matched family rules"
        cand["first_observed_at_ms"] = prev.get(
            "first_observed_at_ms", prev.get("observed_at_ms", as_of_ms))
        return cand

    def _invalidate_absent(self, seen_keys: set, as_of_ms: int) -> None:
        for key, mem in list(self._memory.items()):
            if key in seen_keys:
                continue
            if mem.get("lifecycle") in (LIFECYCLE_INVALIDATED,
                                        LIFECYCLE_EXPIRED):
                continue
            self._close(key, mem, LIFECYCLE_INVALIDATED,
                        "family rules no longer matched at this evaluation",
                        int(as_of_ms))

    def _expire(self, as_of_ms: int) -> None:
        ttl = int(self.rules.get("ttl_ms", 86_400_000))
        for key, mem in list(self._memory.items()):
            if mem.get("lifecycle") in (LIFECYCLE_INVALIDATED,
                                        LIFECYCLE_EXPIRED):
                continue
            first = int(mem.get("first_observed_at_ms",
                                mem.get("observed_at_ms", as_of_ms)))
            if int(as_of_ms) - first >= ttl:
                self._close(key, mem, LIFECYCLE_EXPIRED,
                            "retention TTL elapsed", int(as_of_ms))

    def _enforce_bounds(self) -> None:
        limit = int(self.rules.get("max_candidates", 200))
        if len(self._memory) <= limit:
            return
        ranked = sorted(
            self._memory.items(),
            key=lambda kv: (
                0 if kv[1].get("lifecycle") in (
                    LIFECYCLE_DETECTED, LIFECYCLE_WATCHING,
                    LIFECYCLE_ACTIVE_RESEARCH) else 1,
                int(kv[1].get("observed_at_ms", 0))))
        for key, _ in ranked[:len(self._memory) - limit]:
            self._memory.pop(key, None)

    def forget(self, symbol: str, reason: str = "hot_demotion",
               as_of_ms: Optional[int] = None) -> bool:
        """Drop lifecycle memory for a demoted symbol (no stale reuse).

        Open candidates for the symbol are closed INVALIDATED with the
        reason; a re-promotion starts cold. Returns True when anything
        was forgotten. as_of_ms anchors cooldown/expiry bookkeeping
        (defaults to wall clock; tests pass the evaluation epoch so
        fixture time stays consistent — no wall-clock dependence).
        """
        key = normalize_symbol(symbol) or str(symbol).upper()
        now_ms = int(as_of_ms) if as_of_ms is not None else int(
            time.time() * 1000)
        removed = False
        for cand_key in [k for k in self._memory if f":{key}:" in k]:
            mem = self._memory[cand_key]
            if mem.get("lifecycle") not in (LIFECYCLE_INVALIDATED,
                                            LIFECYCLE_EXPIRED):
                self._close(cand_key, mem, LIFECYCLE_INVALIDATED,
                            "stale evidence barred: %s" % reason, now_ms)
            removed = True
        return removed

    def allow(self, symbols) -> List[str]:  # parity with classifier/universe
        return sorted({normalize_symbol(s) or str(s).upper() for s in symbols})

    def open_candidates(self) -> List[Dict[str, Any]]:
        return [dict(m) for m in self._memory.values() if m.get(
            "lifecycle") in (LIFECYCLE_DETECTED, LIFECYCLE_WATCHING,
                             LIFECYCLE_ACTIVE_RESEARCH)]

    def stats(self) -> Dict[str, Any]:
        return {"rules_version": OPPORTUNITY_RULES_VERSION,
                "evaluated": self.evaluated,
                "detected": self.detected,
                "rejected": self.rejected,
                "open": len(self.open_candidates()),
                "tracked": len(self._memory),
                "last_eval_ms": self.last_eval_ms,
                "max_eval_ms": self.max_eval_ms}


def _mem_from(cand: Dict[str, Any]) -> Dict[str, Any]:
    mem = dict(cand)
    mem["first_observed_at_ms"] = cand.get(
        "first_observed_at_ms", cand.get("observed_at_ms"))
    return mem


def rank_candidates(candidates: List[Dict[str, Any]]
                    ) -> List[Dict[str, Any]]:
    """Sort research candidates by transparent priority score (desc)."""
    return sorted(
        [c for c in candidates if isinstance(c, dict)],
        key=lambda c: (-float((c.get("ranking") or {}).get("score", 0.0)),
                       str(c.get("symbol", "")),
                       str(c.get("setup_family", ""))))
