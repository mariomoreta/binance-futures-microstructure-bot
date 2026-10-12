# Dashboard field semantics v1 (backend Python dashboard + V2 readers)

Each rendered field → persisted source → units/timestamps → UNKNOWN rule.
V2 reads SQLite directly with its own adapters; this file is the shared
semantic contract. No field below is a signal, forecast, or recommendation.

## Returns (live, anchored — NOT rolling, NOT REST)

- Source: `return_features` rows (`current_price`, `source="markPrice"`,
  `source_timestamp_ms`, `sample_age_ms`, `returns{1m..24h}`,
  `anchor_ms{1m..24h}`, `updated_ms` row write time).
- `r_tf = ln(current_price / anchor_price)`; anchor time in `anchor_ms`.
  24h live return is anchored like every TF — presented apart from the
  REST-discovery 24h change (exchange-computed, independent; may disagree).
- Reference block: price/time from `current_price`/`source_timestamp_ms`;
  row as_of from `updated_ms`; history span from `history_span_ms`; 24h
  anchor price DERIVED as P/exp(r) and labeled as such (never observed).
- 24h attribution split (current move vs anchor roll): UNKNOWN — only the
  latest row is retained; consecutive evaluations don't exist. Never
  simulated. Price trajectory stays visible in the mark-price chart.

## Market state (observed HYPOTHESIS)

- Source: `state_features` (`state`, `direction`, `observed_at_ms`,
  `rules_version`, `transition{previous_state, previous_direction,
  changed, state_since_ms, duration_ms, reasons}`, `evidence_for`,
  `evidence_against`, `missing_features`, `features_used`, `validity`).
- Phase age = `state_since_ms` + `duration_ms` (transition time, rendered).
  Evidence/counterevidence/missing rendered verbatim, capped, escaped.

## Open interest (base units)

- Source: `oi_features` (`current_oi` = base-asset units from
  `GET /fapi/v1/openInterest`, deltas per horizon, rate, acceleration,
  price/OI context labels, freshness/staleness).
- Valued (notional) OI: UNKNOWN — no persisted valuation basis (base × a
  price would mix timestamps). Long/short ACCOUNT ratios: no account data
  exists anywhere — not rendered, never inferred from flow notionals.

## Funding (quoted context only)

- Source: latest persisted markPrice MULTI array (`T` = next funding
  time, `r` = quoted rate, observation time = row time).
- Rendered: next time + quoted rate + observation age. Settled history:
  UNKNOWN (not computed). Calendar: UNKNOWN (no venue calendar stored).
  The rate is quoted-as-of (estimate for the coming settlement), never a
  settled record. Settled accounting belongs to versioned study runs.

## VWAP (trailing windows, explicit anchors)

- Source: `structure_features` (`vwap{h}`, `reference_price`,
  `reference_source="markPrice"`, `window_ms`, `as_of_ms`, freshness).
- Rendered per horizon as trailing window with anchor = as_of − window.
  Displacement raw vs the mark reference at as-of. Anchor UNKNOWN when
  `as_of_ms` is absent (never reconstructed).

## Absent by design (blockers, not backlog oversights)

- RSI/ATR: no such fields exist; research candidates, not classifier
  rules; no normative labels ("must correct/recover") anywhere.
- Execution buttons: none (verified); dashboard never feeds the engine.
- Long/short ratios, valued OI, funding calendar, 24h attribution:
  UNKNOWN with reasons above.
