# MARKET_STATES

States: `NORMAL`, `IGNITION`, `EXPANSION`, `EXHAUSTION`, `REVERSAL`.

Status: **classifier NOT BUILT. Initial thresholds below are HYPOTHESIS only**
and must never be presented as statistically validated.

Gating (binding): the classifier is task `P1-12` and is BLOCKED until raw
feature validation `P1-11` (distributions, missingness, freshness) passes.
Raw features must be visible on the dashboard (`/movers`, `/symbol/:symbol`,
P1-09) before any classifier score is shown or trusted.

## Intended semantics

| State | Rough meaning | Hypothesis-level signature sketch |
|---|---|---|
| NORMAL | Baseline drift, no anomaly | Returns/rank/volume within trailing norms |
| IGNITION | Move starting, cause unknown | Rank velocity jump + volume accel + flow imbalance |
| EXPANSION | Directional range growth | Range expansion + realized-vol lift + displacement from VWAP + OI confirm |
| EXHAUSTION | Push losing fuel | Velocity decay + volume climax + imbalance flip + liq cascade / funding extreme |
| REVERSAL | Counter-direction confirmed | Structure break + displacement reversal + follow-through window |

## Rules

- States are per-symbol, timestamped, with the feature vector attached.
  A state without its evidence vector is just a label — useless for Phase 2.
- No state transition may trigger entries (paper or live) until Phases 3–4
  validate it. In Phase 1, states are observed and logged, never acted on.
- Hysteresis / minimum-dwell should be part of the design to avoid flapping;
  exact values are research outputs, not guesses committed here.
- Strategy mapping: momentum path (NORMAL→IGNITION→EXPANSION→CONTINUATION)
  vs exhaustion path (EXPANSION→EXHAUSTION→REVERSAL CONFIRMATION) per
  `docs/STRATEGY_THESIS.md`. The classifier serves both; statistics decide.
