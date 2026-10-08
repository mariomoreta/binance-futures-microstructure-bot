# CLASSIFIER_SPEC — market-state classifier v0 (P1-12A)

Status: **IMPLEMENTED v0.1.0. All thresholds HYPOTHESIS.** Observed states
with evidence only — never signals, entries, probabilities, or confidence.

## Vocabulary

States: `NORMAL` (sufficient fresh data, no anomaly) / `IGNITION` /
`EXPANSION` / `EXHAUSTION` / `REVERSAL` / `UNKNOWN` (missing, stale, or
discovery-only data). Directions: `UP` / `DOWN` / `NONE` / `UNKNOWN`.

## Inputs (all T-known, never future)

Per symbol, the already-built peer-engine rows at summary time:

- returns row: `current_price` + `sample_age_ms` (markPrice), `returns`
  {1m,15m,1h}, `momentum` {velocity {1m,5m} in 1/s, acceleration {1m} in 1/s²}, `tier`
- flow row: `subscribed`, `live`, `horizons.1m` {signed_delta USDT,
  delta_ratio, notional}, `baselines.1m` {z_score}
- book features: `imbalance_notional` ([−1,+1])
- OI row: `horizons.1m.delta` (base units)
- structure row: `ranges.15m` {expansion_ratio, range_position},
  `structure.breakout_state`, `volatility.15m.realized_vol`

Anything absent is `missing_features` — never zero-filled, never interpolated.

## Minimum-data gate (else UNKNOWN)

Subscribed + live (CORE/HOT with live flow; DISCOVERY-only never yields
deep states) AND fresh mark price (`sample_age_ms` ≤ 300_000ms) AND at
least one of: velocity_1m, 1m flow (nonzero notional), 1m realized vol.

## Rules v0.1.0 (HYPOTHESIS, units in code)

- Direction: sign(velocity_1m), else sign(return_1m), else NONE.
- IGNITION: |velocity_1m| ≥ 3e-6/s AND one of: |accel_1m| ≥ 1e-7/s²,
  vol_z_1m ≥ 2.0, |flow_ratio_1m| ≥ 0.3, direction-consistent breakout.
- EXPANSION: |return_15m or 1h| ≥ 0.003 AND |velocity| ≥ 2e-6/s AND one
  of: 15m expansion_ratio ≥ 1.5, agreeing flow sign, observed 15m vol.
  A large 24h-style return alone never qualifies.
- EXHAUSTION: deceleration (accel opposes velocity, |accel| ≥ 1e-7/s²)
  AND one of: weak flow (|ratio| ≤ 0.1), flipped flow, extreme range
  position (≥0.8 up / ≤0.2 down), opposing book imbalance, OI divergence.
  A big up move alone never qualifies.
- REVERSAL: prior UP/DOWN direction AND velocity sign flip AND
  (structure/flow confirmation recorded as evidence); needs 2
  consecutive confirmations (engine memory). Small pullbacks never qualify.
- Priority on overlap: REVERSAL > EXHAUSTION > EXPANSION > IGNITION >
  NORMAL. Contradictory evidence is stored in `evidence_against`, never hidden.
- Buyer aggression is NEVER rendered as rally probability; no LONG/SHORT
  wording exists anywhere in outputs or UI.

## Time, hysteresis, restarts, gaps

- Every record: `observed_at_ms`, `features_used`, `evidence_for/against`,
  `missing_features`, `validity`, `rules_version`, `transition`
  {previous_state/direction, changed, state_since_ms, duration_ms, reasons}.
- Hysteresis: energetic states held for `min_dwell_evals` = 2 evaluations
  before yielding (reason recorded); no forced NORMAL→…→REVERSAL sequence.
- UNKNOWN exits hysteresis immediately (data loss is not smoothed over).
- Engine memory (dwell counts, reversal confirmations) restarts cold on
  probe restart and says so; states recompute from fresh features.
- Gaps/starvation surface as UNKNOWN via the freshness/minimum gates.

## Persistence & integration

- `state_features` (REPLACE/symbol, schema v7) + `state_transitions`
  (append, ≤500) in the operational DB. Probe evaluates once per ~30s
  summary (measured 0.16–0.20ms per batch — negligible).
- Dashboard: token-page "Market state v0" panel (state/direction/as-of/
  rules/previous/reasons/features/missing/validity) + honest
  discovery-only/warming notes. No new HTTP contract (server-rendered
  from existing store reads). No Next.js changes.

## Validation

- `tests/test_classifier.py`: 25 deterministic fixture tests (all five
  states × directions where applicable, UNKNOWN paths, contradictions,
  transitions, hysteresis, gaps, cold restart, no-lookahead, timestamps,
  discovery-only, serialization, determinism).
- Live: 120s observe-only run → 9 evaluations, states + transitions
  persisted, token pages render, 0 orders. No predictive accuracy is
  claimed without prospective evaluation (P1-14 territory).
