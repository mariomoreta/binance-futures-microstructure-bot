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
