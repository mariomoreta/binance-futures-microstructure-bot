# OPPORTUNITY_ENGINE_SPEC - canonical research semantics

**Evidence:** canonical backend opportunity.py at
55efaa2b171c83701f6736ab6e6374869a733af1; rules v0.1.0.
**Scope:** documented backend behavior, not a code import into the V2 branch.
Research candidates are implemented; validated entry/position strategies are not.
Future experiment definitions: [Movers and Levels](MOVER_LEVEL_STRATEGY_RESEARCH.md).

## Implemented families - source-aligned correction

| Family | Classifier/state requirement and corroboration |
|---|---|
| MOMENTUM_CONTINUATION | EXPANSION, UP/DOWN, available 15m-or-1h return, agreeing velocity and flow |
| IGNITION_WATCH | IGNITION with UP/DOWN; classifier evidence recorded for monitoring |
| EXHAUSTION_WATCH | EXHAUSTION with UP/DOWN; prior move losing strength |
| REVERSAL_WATCH | REVERSAL with UP/DOWN plus classifier confirmation or agreeing flow and recognized structure breakout |
| EXTREME_MOVE_RESEARCH | Magnitude of 15m-or-1h log return meets configured extreme_move_ret_min (default 0.01), in EXPANSION/EXHAUSTION/IGNITION |

The canonical older prose listing COOLDOWN as the ignition/exhaustion trigger,
and "vol > 4 sigma not explained by flow" as the extreme trigger, does not match
this source snapshot. Cooldown is a lifecycle restriction after closure, not
a classifier state. Source and version, not old family-name prose, govern.
This is a documentation correction only; no threshold or family was changed.

## Meaning and lifecycle
Observed direction is descriptive. EXHAUSTION UP means prior upward movement
losing strength; REVERSAL direction is the new observed direction.
No automatic LONG/SHORT mapping, entry price, stop, target or profit probability.
score is research priority/completeness/activity, not calibrated win probability.
Implemented research lifecycle: DETECTED -> WATCHING -> ACTIVE_RESEARCH ->
INVALIDATED/EXPIRED/UNKNOWN. These states do not authorize a fill.
Per-source lifecycle defaults: cooldown 60m, TTL 24h, max 200 candidates;
prospective registration is at first DETECTED and does not prove independent episodes.

## Future separation
H-A1/H-B1 proposed strategy definitions are narrower level-based experiments;
they are not renamed existing families. A future plan separates observed
direction from nullable proposed side, fixes levels/activation/invalidation
and passes data, risk and executable-cost gates.
See SIGNAL_RESEARCH_PLAN.md, EVENT_LABELING.md and FEATURE_BACKLOG.md.
The current frontend remains read-only/observe-only with Start blocked.
