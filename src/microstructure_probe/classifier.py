"""P1-12A market-state classifier v0 (deterministic, explainable, versioned).

States: NORMAL / IGNITION / EXPANSION / EXHAUSTION / REVERSAL, plus UNKNOWN
when data are missing, stale, or coverage is discovery-only. Directions:
UP / DOWN / NONE / UNKNOWN. No probabilities, no confidence percentages —
every output carries its evidence for/against, missing features, validity
conditions, rules version, and transition reasons.

As-of discipline: the classifier consumes ONLY feature records computed at
or before the observation instant (the probe passes already-built rows;
the classifier never reaches into live engines or future data).

All thresholds are HYPOTHESIS (see RULES + docs/CLASSIFIER_SPEC.md), never
statistically validated edge. In Phase 1 states are observed and logged,
never acted on; nothing here can trade.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

RULES_VERSION = "v0.1.0"

STATE_NORMAL = "NORMAL"
STATE_IGNITION = "IGNITION"
STATE_EXPANSION = "EXPANSION"
STATE_EXHAUSTION = "EXHAUSTION"
STATE_REVERSAL = "REVERSAL"
STATE_UNKNOWN = "UNKNOWN"

STATES = (STATE_NORMAL, STATE_IGNITION, STATE_EXPANSION,
          STATE_EXHAUSTION, STATE_REVERSAL, STATE_UNKNOWN)

DIR_UP = "UP"
DIR_DOWN = "DOWN"
DIR_NONE = "NONE"
DIR_UNKNOWN = "UNKNOWN"

DIRECTIONS = (DIR_UP, DIR_DOWN, DIR_NONE, DIR_UNKNOWN)

# HYPOTHESIS thresholds (units documented per key; see CLASSIFIER_SPEC.md).
# Chosen conservatively against P1-11A measured live scales so v0 defaults
# to NORMAL/UNKNOWN rather than inventing activity.
RULES: Dict[str, Any] = {
    # Minimum-data gate.
    "max_sample_age_ms": 300_000,          # price older than this -> UNKNOWN
    # IGNITION: |velocity_1m| plus one corroboration.
    "ignition_vel_min_per_s": 3e-6,       # 1/s
    "ignition_accel_min_per_s2": 1e-7,    # 1/s^2
    "ignition_vol_z_min": 2.0,            # baseline z (dimensionless)
    "ignition_flow_ratio_min": 0.3,       # |delta_ratio| (dimensionless)
    # EXPANSION: sustained directional move + continuation evidence.
    "expansion_ret_min": 0.003,           # log return on 15m or 1h
    "expansion_vel_min_per_s": 2e-6,      # 1/s
    "expansion_range_ratio_min": 1.5,     # 15m expansion_ratio (dimensionless)
    # EXHAUSTION: deceleration against the move + weakening/positional clue.
    "exhaustion_accel_min_per_s2": 1e-7,  # opposing accel magnitude
    "exhaustion_flow_weak_max": 0.1,      # |delta_ratio| below this = weak
    "exhaustion_extreme_position": 0.8,   # range_position beyond this
    # Hysteresis / confirmation (evaluation counts, not wall time).
    "min_dwell_evals": 2,                 # hold IGN/EXP/EXH/REV this long
    "reversal_confirm_evals": 2,          # consecutive reversal reads needed
}


def _num(value: Any) -> Optional[float]:
    """Finite float or None (UNKNOWN is never 0 — enforced here)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _sign(value: Optional[float]) -> str:
    if value is None:
        return DIR_UNKNOWN
    if value > 0:
        return DIR_UP
    if value < 0:
        return DIR_DOWN
    return DIR_NONE


def _get(record: Dict[str, Any], *path: str) -> Any:
    node: Any = record
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


class Classification(Dict[str, Any]):
    """A dict subclass so records stay JSON-serializable plain dicts."""


def _unknown(symbol: str, as_of_ms: int, reasons: List[str],
             missing: List[str],
             prev: Optional[Dict[str, Any]] = None) -> Classification:
    return Classification(
        symbol=symbol, state=STATE_UNKNOWN, direction=DIR_UNKNOWN,
        observed_at_ms=as_of_ms, features_used=[], evidence_for=[],
        evidence_against=[], missing_features=sorted(set(missing)),
        validity={"sufficient_data": False, "fresh": False,
                  "reasons": reasons},
        rules_version=RULES_VERSION,
        transition=_transition(prev, STATE_UNKNOWN, DIR_UNKNOWN, as_of_ms,
                               reasons, changed_hint=True),
    )


def _transition(prev: Optional[Dict[str, Any]], state: str, direction: str,
                as_of_ms: int, reasons: List[str],
                changed_hint: Optional[bool] = None) -> Dict[str, Any]:
    prev_state = (prev or {}).get("state")
    prev_dir = (prev or {}).get("direction")
    since = (prev or {}).get("state_since_ms", as_of_ms)
    changed = changed_hint if changed_hint is not None else (
        state != prev_state or direction != prev_dir)
    if changed:
        since = as_of_ms
    return {"previous_state": prev_state, "previous_direction": prev_dir,
            "changed": bool(changed), "state_since_ms": since,
            "duration_ms": max(0, as_of_ms - since),
            "reasons": list(reasons)}


def classify_symbol(symbol: str, features: Dict[str, Any], as_of_ms: int,
                    prev: Optional[Dict[str, Any]] = None,
                    rules: Optional[Dict[str, Any]] = None
                    ) -> Classification:
    """One deterministic classification from T-known feature rows only."""
    cfg = rules or RULES
    sym = str(symbol).upper()
    missing: List[str] = []
    used: List[str] = []
    evidence_for: List[str] = []
    evidence_against: List[str] = []

    subscribed = bool(features.get("subscribed", False))
    live = bool(features.get("live", subscribed))
    if not subscribed or not live:
        return _unknown(sym, as_of_ms,
                        ["not subscribed/live: discovery-only coverage "
                         "never yields deep states"],
                        ["live_subscription"], prev)

    price = _num(_get(features, "price", "current_price"))
    if price is None:
        price = _num(features.get("current_price"))
    age_ms = _num(_get(features, "price", "sample_age_ms"))
    if age_ms is None:
        age_ms = _num(features.get("sample_age_ms"))
    if price is None:
        return _unknown(sym, as_of_ms, ["no current mark price"],
                        ["current_price"], prev)
    used.append("current_price(markPrice)")
    max_age = int(cfg.get("max_sample_age_ms", 300_000))
    if age_ms is None or age_ms < 0 or age_ms > max_age:
        return _unknown(sym, as_of_ms,
                        ["price sample missing/too old: age_ms=%s (limit %d)"
                         % (age_ms, max_age)], ["fresh_price"], prev)

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
    vel5m = _num(vel.get("5m"))
    acc1m = _num(acc.get("1m"))

    flow = features.get("flow") if isinstance(features.get("flow"), dict) \
        else {}
    horizons = flow.get("horizons") if isinstance(flow.get("horizons"), dict) \
        else {}
    h1m = horizons.get("1m") if isinstance(horizons.get("1m"), dict) else {}
    flow_delta = _num(h1m.get("signed_delta"))
    flow_ratio = _num(h1m.get("delta_ratio"))
    flow_notional = _num(h1m.get("notional"))
    baselines = flow.get("baselines") if isinstance(
        flow.get("baselines"), dict) else {}
    b1m = baselines.get("1m") if isinstance(baselines.get("1m"), dict) \
        else {}
    vol_z = _num(b1m.get("z_score"))

    struct = features.get("structure") if isinstance(
        features.get("structure"), dict) else {}
    ranges = struct.get("ranges") if isinstance(struct.get("ranges"), dict) \
        else {}
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

    book = features.get("book") if isinstance(features.get("book"), dict) \
        else {}
    imbalance = _num(book.get("imbalance_notional"))
    if imbalance is None:
        imbalance = _num(book.get("imbalance_qty"))

    oi = features.get("oi") if isinstance(features.get("oi"), dict) else {}
    oi_h = oi.get("horizons") if isinstance(oi.get("horizons"), dict) else {}
    oi1m = oi_h.get("1m") if isinstance(oi_h.get("1m"), dict) else {}
    oi_delta = _num(oi1m.get("delta"))

    # Minimum-data gate: at least one directional/activity input.
    has_motion = vel1m is not None
    has_flow = flow_delta is not None and flow_notional is not None \
        and flow_notional > 0
    has_vol = realized_vol is not None
    if not (has_motion or has_flow or has_vol):
        return _unknown(sym, as_of_ms,
                        ["minimum-data gate: need velocity_1m, 1m flow, "
                         "or 1m realized vol"],
                        ["velocity_1m", "flow_1m", "volatility_1m"], prev)
    if vel1m is not None:
        used.append("velocity_1m(1/s)")
    if flow_delta is not None:
        used.append("flow_signed_delta_1m(USDT)")
    if realized_vol is not None:
        used.append("realized_vol_1m(log)")

    direction = _sign(vel1m)
    if direction == DIR_UNKNOWN:
        direction = _sign(ret1m)
    if direction == DIR_UNKNOWN:
        direction = DIR_NONE
    dir_sign = 1 if direction == DIR_UP else -1 if direction == DIR_DOWN \
        else 0

    # --- candidate evidence (each rule independent, corroboration explicit)
    ignition_bits: List[str] = []
    if vel1m is not None and abs(vel1m) >= float(cfg["ignition_vel_min_per_s"]):
        ignition_bits.append("velocity_1m %.3g/s >= %.1g" % (
            vel1m, float(cfg["ignition_vel_min_per_s"])))
    else:
        missing.append("ignition_velocity")
    corroborate: List[str] = []
    if acc1m is not None and abs(acc1m) >= float(cfg["ignition_accel_min_per_s2"]):
        corroborate.append("accel_1m %.3g/s^2" % acc1m)
    if vol_z is not None and vol_z >= float(cfg["ignition_vol_z_min"]):
        corroborate.append("vol_z_1m %+.2f" % vol_z)
    if flow_ratio is not None and abs(flow_ratio) >= float(cfg["ignition_flow_ratio_min"]):
        corroborate.append("flow_ratio_1m %+.2f" % flow_ratio)
    if breakout in ("ABOVE_PRIOR_RANGE", "BELOW_PRIOR_RANGE"):
        side_ok = (breakout == "ABOVE_PRIOR_RANGE" and dir_sign > 0) or \
                  (breakout == "BELOW_PRIOR_RANGE" and dir_sign < 0)
        (corroborate if side_ok else evidence_against).append(
            "breakout %s vs direction %s" % (breakout, direction))
    ignition = bool(ignition_bits) and bool(corroborate)

    expansion_bits: List[str] = []
    big_ret = ret15m if ret15m is not None else ret1h
    if big_ret is not None and abs(big_ret) >= float(cfg["expansion_ret_min"]):
        expansion_bits.append("return %.4f >= %.4f" % (
            big_ret, float(cfg["expansion_ret_min"])))
    else:
        missing.append("expansion_return")
    if vel1m is not None and abs(vel1m) >= float(cfg["expansion_vel_min_per_s"]):
        expansion_bits.append("velocity_1m %.3g/s sustained" % vel1m)
    else:
        missing.append("expansion_velocity")
    continuation: List[str] = []
    if expansion_ratio is not None and expansion_ratio >= float(cfg["expansion_range_ratio_min"]):
        continuation.append("range_expansion_15m %.2f" % expansion_ratio)
    if flow_ratio is not None and dir_sign != 0 and (
            (flow_ratio > 0) == (dir_sign > 0)):
        continuation.append("flow agrees (ratio %+.2f)" % flow_ratio)
    elif flow_ratio is not None and dir_sign != 0:
        evidence_against.append("flow contradicts (ratio %+.2f vs %s)" % (
            flow_ratio, direction))
    if realized_vol is not None:
        continuation.append("vol_15m %.5f observed" % realized_vol)
    expansion = len(expansion_bits) >= 2 and bool(continuation)

    exhaustion_bits: List[str] = []
    if vel1m is not None and acc1m is not None and vel1m != 0 and (
            acc1m * vel1m < 0) and abs(acc1m) >= float(
                cfg["exhaustion_accel_min_per_s2"]):
        exhaustion_bits.append("deceleration: accel %.3g opposes vel %.3g" % (
            acc1m, vel1m))
    else:
        missing.append("deceleration")
    weaken: List[str] = []
    if flow_ratio is not None and abs(flow_ratio) <= float(cfg["exhaustion_flow_weak_max"]):
        weaken.append("flow weak (|ratio| %.2f)" % abs(flow_ratio))
    if flow_ratio is not None and dir_sign != 0 and (
            (flow_ratio > 0) != (dir_sign > 0)):
        weaken.append("flow flipped vs direction")
    if range_pos is not None and dir_sign != 0 and (
            (range_pos >= float(cfg["exhaustion_extreme_position"])
             and dir_sign > 0) or
            (range_pos <= 1.0 - float(cfg["exhaustion_extreme_position"])
             and dir_sign < 0)):
        weaken.append("range_position %.2f extreme" % range_pos)
    if imbalance is not None and dir_sign != 0 and (
            (imbalance > 0) != (dir_sign > 0)):
        weaken.append("book imbalance opposes (%.2f)" % imbalance)
    if oi_delta is not None and big_ret is not None and (
            (oi_delta > 0) != (big_ret > 0)) and big_ret != 0:
        weaken.append("OI diverges from price move")
    exhaustion = bool(exhaustion_bits) and bool(weaken)

    # REVERSAL needs a prior directional move + sign flip + confirmation.
    reversal_bits: List[str] = []
    prev_dir = (prev or {}).get("direction")
    prev_state = (prev or {}).get("state")
    if prev_dir in (DIR_UP, DIR_DOWN) and direction in (DIR_UP, DIR_DOWN) \
            and direction != prev_dir and dir_sign != 0:
        reversal_bits.append("velocity sign flipped %s -> %s" % (
            prev_dir, direction))
        if breakout in ("ABOVE_PRIOR_RANGE", "BELOW_PRIOR_RANGE"):
            side_ok = (breakout == "ABOVE_PRIOR_RANGE" and dir_sign > 0) or \
                      (breakout == "BELOW_PRIOR_RANGE" and dir_sign < 0)
            if side_ok:
                reversal_bits.append("structure confirms (%s)" % breakout)
        if flow_ratio is not None and (
                (flow_ratio > 0) == (dir_sign > 0)):
            reversal_bits.append("flow confirms new direction")
    elif prev_dir in (DIR_UP, DIR_DOWN):
        missing.append("reversal_flip")
    else:
        missing.append("prior_direction")
    reversal_ready = bool(reversal_bits)

    # Priority: REVERSAL > EXHAUSTION > EXPANSION > IGNITION > NORMAL.
    if reversal_ready:
        candidate, cand_dir = STATE_REVERSAL, direction
        cand_evidence = reversal_bits
    elif exhaustion:
        candidate, cand_dir = STATE_EXHAUSTION, direction
        cand_evidence = exhaustion_bits + weaken
    elif expansion:
        candidate, cand_dir = STATE_EXPANSION, direction
        cand_evidence = expansion_bits + continuation
    elif ignition:
        candidate, cand_dir = STATE_IGNITION, direction
        cand_evidence = ignition_bits + corroborate
    else:
        candidate, cand_dir = STATE_NORMAL, \
            direction if direction in (DIR_UP, DIR_DOWN) else DIR_NONE
        cand_evidence = ["no anomaly thresholds crossed; data sufficient"]
        if direction == DIR_NONE:
            evidence_against.append("no measurable direction")

    # Hysteresis: hold energetic states for min dwell; UNKNOWN exits at
    # once. REVERSAL candidates skip the dwell hold — the engine's
    # confirmation counter governs them (dwell + confirmation would
    # double-gate and delay real flips).
    reasons = list(cand_evidence)
    prev_evals = int((prev or {}).get("evals_in_state", 0))
    dwell_need = int(cfg.get("min_dwell_evals", 2))
    pending = (prev or {}).get("pending_reversal") or {}
    if candidate == STATE_REVERSAL:
        # Confirmation counting happens in evaluate().
        pass
    elif prev_state in (STATE_IGNITION, STATE_EXPANSION, STATE_EXHAUSTION,
                        STATE_REVERSAL) and candidate != prev_state \
            and candidate != STATE_UNKNOWN and prev_evals + 1 < dwell_need:
        reasons = ["hysteresis hold: %s dwelled %d/%d evals; candidate %s "
                   "deferred" % (prev_state, prev_evals + 1, dwell_need,
                                 candidate)]
        candidate, cand_dir = prev_state, (prev or {}).get(
            "direction", cand_dir)

    validity = {"sufficient_data": True,
                "fresh": True,
                "price_age_ms": age_ms,
                "max_sample_age_ms": max_age,
                "reasons": ["price fresh (%dms <= %dms)" % (age_ms, max_age)]}
    return Classification(
        symbol=sym, state=candidate, direction=cand_dir,
        observed_at_ms=as_of_ms, features_used=sorted(set(used)),
        evidence_for=sorted(set(cand_evidence)),
        evidence_against=sorted(set(evidence_against)),
        missing_features=sorted(set(missing)), validity=validity,
        rules_version=RULES_VERSION,
        transition=_transition(prev, candidate, cand_dir, as_of_ms, reasons),
    )


class ClassifierEngine:
    """Per-symbol state memory + batch evaluation (deterministic)."""

    def __init__(self, symbols: Tuple[str, ...] = (),
                 rules: Optional[Dict[str, Any]] = None) -> None:
        self._allowed = ({s.upper() for s in symbols} if symbols else None)
        self.rules = dict(rules or RULES)
        self._memory: Dict[str, Dict[str, Any]] = {}
        self.dropped_unknown = 0
        self.evaluated = 0
        self.last_eval_ms: Optional[float] = None
        self.max_eval_ms = 0.0

    def note_eval_ms(self, elapsed_ms: float) -> None:
        """Record one batch evaluation cost (probe summary telemetry)."""
        try:
            value = max(0.0, float(elapsed_ms))
        except (TypeError, ValueError):
            return
        self.last_eval_ms = value
        self.max_eval_ms = max(self.max_eval_ms, value)

    def evaluate(self, records: Dict[str, Dict[str, Any]],
                 as_of_ms: int) -> List[Classification]:
        """Classify every supplied symbol record at one instant."""
        out: List[Classification] = []
        for symbol in sorted(records):
            key = str(symbol).upper()
            if self._allowed is not None and key not in self._allowed:
                self.dropped_unknown += 1
                continue
            prev = self._memory.get(key)
            result = classify_symbol(key, records[symbol] or {},
                                     int(as_of_ms), prev, self.rules)
            # Memory update: dwell counting + reversal confirmation.
            prev_state = (prev or {}).get("state")
            if result["state"] == prev_state:
                evals = int((prev or {}).get("evals_in_state", 0)) + 1
            else:
                evals = 0
            pending = dict((prev or {}).get("pending_reversal") or {})
            if result["state"] == STATE_REVERSAL:
                want = result["direction"]
                if pending.get("direction") == want:
                    pending["count"] = int(pending.get("count", 0)) + 1
                else:
                    pending = {"direction": want, "count": 1}
                need = int(self.rules.get("reversal_confirm_evals", 2))
                if pending["count"] < need and prev_state in (
                        STATE_IGNITION, STATE_EXPANSION, STATE_EXHAUSTION,
                        STATE_REVERSAL) and prev_state != STATE_REVERSAL:
                    # Not yet confirmed: hold prior state, keep counting.
                    held = dict(result)
                    held["state"] = prev_state
                    held["direction"] = (prev or {}).get(
                        "direction", result["direction"])
                    held["evidence_for"] = sorted(set(
                        held.get("evidence_for", [])) | {
                            "reversal unconfirmed (%d/%d)" % (
                                pending["count"], need)})
                    held["transition"] = _transition(
                        prev, prev_state, held["direction"], int(as_of_ms),
                        ["reversal confirmation %d/%d" % (
                            pending["count"], need)])
                    result = Classification(held)
                    evals = int((prev or {}).get("evals_in_state", 0)) + 1
            elif result["state"] != STATE_UNKNOWN:
                pending = {}
            self._memory[key] = {
                "state": result["state"], "direction": result["direction"],
                "state_since_ms": result["transition"]["state_since_ms"],
                "evals_in_state": evals, "pending_reversal": pending,
                "observed_at_ms": int(as_of_ms),
            }
            self.evaluated += 1
            out.append(result)
        return out

    def stats(self) -> Dict[str, Any]:
        return {"rules_version": RULES_VERSION,
                "evaluated": self.evaluated,
                "dropped_unknown": self.dropped_unknown,
                "last_eval_ms": self.last_eval_ms,
                "max_eval_ms": self.max_eval_ms,
                "symbols": sorted(self._memory),
                "states": {s: sum(1 for m in self._memory.values()
                                  if m["state"] == s) for s in STATES}}
