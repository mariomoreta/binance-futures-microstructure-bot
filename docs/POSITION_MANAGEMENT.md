# POSITION_MANAGEMENT

Entry discovery and position management are separate engines.

## Future position actions

`HOLD` · `LET_WINNER_RUN` · `RAISE_STOP` · `PROTECT_PROFIT` · `PARTIAL_EXIT` · `FULL_EXIT`

## Concept

Trade duration must ultimately be evidence-driven and market-state-driven, not a
universal fixed number of minutes. The system must learn whether a position
should remain open based on how features evolve after entry:

- Continuation features persist (expansion holding, OI supporting, no
  exhaustion signature) → HOLD / LET_WINNER_RUN / RAISE_STOP.
- Exhaustion features appear (velocity decay, imbalance flip, climax) →
  PROTECT_PROFIT / PARTIAL_EXIT / FULL_EXIT.
- Invalidation (structure break against the position, MAE beyond tolerance) →
  FULL_EXIT.

The `HUMAN_STRATEGY_HYPOTHESIS` hold range (minutes to ~1h, dynamic) becomes a
prior to test against labeled outcomes (`docs/EVENT_LABELING.md` horizons
30s→60m + MFE/MAE), never a hardcoded rule.

## Rules

- Position manager consumes the same feature/state pipeline as discovery —
  never dashboard output, never ad-hoc signals.
- Every management decision logged with state evidence + config version.
- Risk engine limits (stops, exposure, kill-switch) override the position
  manager unconditionally.
- No position code exists yet (Phase 4). Phase 1–3 work must keep the
  post-entry feature evolution measurable so this engine has inputs.


## 2026-10-11 - Proposed mover strategy management
[Movers and Levels](MOVER_LEVEL_STRATEGY_RESEARCH.md) specifies future H-A1/H-B1
plans; no position code or validated exit rule is added.
Freeze invalidation/stop, target zones, maximum chase price, plan expiry and a
maximum exposure duration before simulation. Study continuation-driven holding,
structure-based stop protection and deterioration-driven exits against simple
fixed-time baselines. Do not assume capturing the observed maximum is feasible.
The minutes-to-about-one-hour prior is not a universal timer; 4h mark endpoints
are not proof of viable long holding. Partial exits and trailing alternatives
must each justify costs/out-of-sample behavior before adoption. Hard risk limits
override the manager; missing executable data cannot become a new entry.
Observed_move_direction, proposed_trade_side, actual fill and position state
remain distinct records. Unknown/stale open-position handling needs a separately
validated paper protection policy; this document does not implement it.
