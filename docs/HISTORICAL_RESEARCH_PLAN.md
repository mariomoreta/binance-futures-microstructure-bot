# HISTORICAL_RESEARCH_PLAN

Future phases P1-11B (Historical Data Foundation) and P1-11C (Historical
Event Studies). Design only — NOT implemented in P1-11A. No backfill was run.

## P1-11B — Historical Data Foundation (planned)

Goal: multi-resolution mark-price (and where justified, flow/OI) history so
event studies and calibration have samples beyond one live window.

Target resolutions (to confirm against current official Binance USD-M docs
BEFORE implementation — klines/aggTrades limits, weight costs, archive
availability):

- 1m: recent 30–90d (event-study backbone).
- 5m/15m: 6–12 months (regime + structure context).
- 1h: 1–2 years or available lifetime (cycle context).
- 4h/1d: full available contract history (listing-to-now anchors).

Rules carried over from Phase 1: public endpoints only, no keys; provenance
labeled (REST bootstrap vs live WS); no interpolated fills — missing stays
missing (UNKNOWN); tolerance-anchored returns unchanged; retention bounded
per resolution (raw archive is Phase 2 scope, not the dashboard DB).

## P1-11C — Historical Event Studies (planned)

Event formation with NO lookahead: an event is defined at time T using only
data ≤ T (returns/velocity/flow/book/OI/structure/BTC context as validated
in P1-11A). Outcomes measured forward from T:

- Fixed horizons: 1m / 3m / 5m / 15m / 30m / 1h (mark-price log return sign
  and magnitude).
- Path outcomes: MFE / MAE / time-to-MFE / time-to-MAE / invalidation time
  (invalidation = first touch of a pre-declared level fixed at T, e.g.
  back-through-VWAP or swing break — never refit after seeing the path).

Candidate event families (hypotheses, not signals): extended-gainer
continuation vs exhaustion, buy/sell absorption (see
`docs/SIGNAL_RESEARCH_PLAN.md`), velocity-deceleration + failed-high,
VWAP-loss after aggressive-buy dominance, OI-regime flips, book-imbalance
persistence. Each family needs a pre-registered definition + minimum sample
size before any confidence is quoted.

## What current data already supports

- 10s mark-price buckets with honest gaps (grid fill measured 31.7% in a
  degraded window) — the event clock and return math already handle sparsity.
- Completed-bucket-only baselines and tolerance anchors — reusable unchanged
  on historical bars.
- UNKNOWN-first rendering — event studies must keep, not impute.

## What is still missing (P1-11B must provide)

- Any history older than the live window (dashboard DB holds ~16h span).
- Retained per-trade flow history (only aggregates + 600 bounded buckets
  per size/symbol persist) — absorption studies need denser retained flow
  or re-derivable bucket detail.
- Book depth history (latest snapshot only) — resilience/recovery-time
  metrics need a new retained series (deferred since P1-08).
