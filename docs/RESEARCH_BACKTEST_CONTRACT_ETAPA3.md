# ETAPA 3 — Research & backtest contract (2026-10-12)

Status: CONTRACT ONLY. No engine implemented, no backtest run, no
validation claimed. All thresholds HYPOTHESIS. Rule versions referenced:
classifier `v0.1.0`, opportunity `v0.1.0`, event definitions v1 (six
families, `DESCRIPTIVE_RESEARCH_ONLY_HYPOTHESIS`).

## 0. Global non-negotiables

- Exploration move sizes (5%, 15%, 40%, 70%) define STUDY POPULATIONS
  (which historical moves enter an event study), never entry signals.
- Capitalization source: UNKNOWN — no validated source exists. Low-cap
  must never be inferred from volume or price rise.
- Costs are part of every hypothesis: taker fees, funding, spread,
  slippage, latency, partial fills, contract constraints (min notional,
  tick/lot steps — values UNKNOWN until sourced from exchangeInfo at
  research time; never hardcoded from memory).
- COMPLETE outcome rows are recordings, never profitable trades.
- Replay limits (historical): klines-only formation (no book/flow
  reconstruction), OI capped windows, recent-only aggTrades, gaps stay
  UNKNOWN/GAP (no fill), CLOSED candles only, sub-1h horizons on 1h bars
  share outcomes (resolution limit).

## H1 — Impulse continuation after breakout or level recovery

- Universe/liquidity: USDT-M perpetuals, TRADING status, quote-vol floor
  TBD by measurement (no floor is valid until measured; never inherit one
  from discovery scanning, which serves a different purpose).
- Context/level/confirmation: prior EXPANSION state (classifier v0.1.0)
  + direction-consistent velocity + agreeing aggressive flow +
  confirmed structure breakout (prior-block high/low tag + 30s
  confirmation delay). Recovery variant: reclaim of the same level with
  the same confirmations after a failed breakdown.
- Data-availability timing: every input timestamped at summary time from
  closed 10s buckets / confirmed pivots only; nothing evaluated on
  forming candles.
- Entry/invalidation/stop/exits: ENTRY postponed to contract v2 (this
  contract defines the STUDY event, not a trade). Study invalidation:
  level loss on closed-bar basis, opposite-direction REVERSAL with 2
  confirmations, or data going UNKNOWN/stale. Horizons: 1m/3m/5m/15m/
  30m/1h/4h forward returns + MFE/MAE per EVENT_LABELING.
- Sizing/exposure: not authorized in this contract version (research
  only; sizing belongs to a risk contract that does not exist yet).
- No-trade conditions: UNKNOWN/stale data, unsubscribed symbol (no deep
  features), funding-artifact windows, gap-crossed formations, single
  exchange-venue moves without BTC-context check.
- Params/versions: study population = moves ≥5% (exploration tier T1);
  version string `H1-v1`; any threshold change creates `H1-v2`.
- Accept/discard evidence: ACCEPT requires out-of-sample net expectancy
  > 0 after full costs at 1x/2x/3x sensitivity with distributions (not
  point estimates); DISCARD on net ≤ 0, on OOS failure, or when the
  edge concentrates in unusable/FORMATION_GAP rows.

## H2 — Exhaustion and reversal after strong expansion

- Universe/liquidity: same venue/status rules as H1, measured floor TBD.
- Context/level/confirmation: prior EXPANSION + deceleration (accel
  opposes velocity) + one of weak/flipped flow, extreme range position,
  opposing book imbalance, OI divergence (classifier EXHAUSTION rule);
  reversal needs prior direction + velocity sign flip + 2 consecutive
  confirmations (REVERSAL rule). A big move alone never qualifies.
- Data-availability timing: same closed-bucket/confirmed-pivot discipline
  as H1; reversal confirmations counted on successive summaries only.
- Entry/invalidation/stop/exits: study-only (as H1). Invalidation:
  continuation to new extremes on closed bars, confirmation count reset
  by UNKNOWN gaps, contradiction stored in evidence_against.
- Sizing/exposure: not authorized (as H1).
- No-trade conditions: H1 list + never fade a move on range position
  alone; never treat funding-rate crossings as exhaustion (documented
  sampling-artifact class).
- Params/versions: tiers T1 ≥5%, T2 ≥15% (strong-expansion gate);
  `H2-v1`; threshold changes fork versions.
- Accept/discard: same statistical bar as H1, computed separately for
  the exhaustion leg and the reversal leg (they are different claims).

## H3 — Bearish continuation after support loss (≠ loser recovery)

- Separation statement: H3 is DOWN-direction continuation after a lost
  support level. Loser recovery (DOWN move followed by UP reversal) is a
  DIFFERENT hypothesis (belongs to H2's reversal leg) with different
  evidence; results must never be pooled.
- Universe/liquidity: same venue/status rules, measured floor TBD.
- Context/level/confirmation: DOWN EXPANSION + direction-consistent
  velocity (negative) + sell-agreeing flow + confirmed breakdown of a
  prior-block low (mirror of H1, SHORT-down MFE/MAE accounting).
- Data-availability timing / invalidation / sizing / no-trade: mirrors
  of H1 with sign flipped; invalidation on level reclaim (which then
  becomes an H1-recovery candidate, not an H3 continuation).
- Params/versions: tiers T1 ≥5%, T2 ≥15%, plus documented large-drop
  exploration tiers T3 ≥40%, T4 ≥70% for SEPARATE tail studies (rare by
  construction — INSUFFICIENT tier expected; never promote on counts
  alone). `H3-v1`.
- Accept/discard: same bar as H1; tail tiers reported with sample-tier
  labels, never pooled with T1/T2.

## Cost model (applies to all families, values versioned per study)

Taker fee rate, funding accrual over holding horizons, spread at entry/
exit (book-implied, honestly UNKNOWN on klines-only replay), slippage
function of notional vs trailing volume, latency distribution from
measured corrected lags (p50/p95 per stream, NOT legacy metrics),
partial fills on thin books, min-notional/tick/lot gates. Sensitivity:
every result reported at 1x, 2x, 3x costs. Cost assumptions stored
separately from raw outcomes (per EVENT_LABELING) so they stay auditable.

## Dataset fitness gates (from Etapa 2 — must hold before any study)

Fixture rows (`detail='test'`) filtered explicitly; single-version rules
documented as limitation; rare tiers stay INSUFFICIENT until counts grow;
FORMATION_GAP rows excluded by the `usable_for_statistics` flag, never
deleted; no OOS span exists yet — any study today is IN-SAMPLE
EXPLORATION and must be labeled as such.

## Closeout (seven fields)

- `DECISIONS_REVIEWED`: Etapa-2 readiness, CLASSIFIER_SPEC v0.1.0,
  OPPORTUNITY_ENGINE_SPEC v0.1.0, EVENT_LABELING, P1-11C pilot limits.
- `NEW_DECISIONS_RECORDED`: H1/H2/H3 separation (H3≠loser-recovery);
  cost-model versioning rule; in-sample labeling mandate — appended to
  `docs/DECISIONS.md`.
- `FEATURES_IMPLEMENTED`: this contract (no backlog ID; research enabling).
- `FEATURES_VERIFIED`: none (contract unimplemented by design).
- `DEFERRED_FEATURES`: engine (Etapa 4), live validation, sizing/risk
  contract, capitalization source, measured liquidity floors.
- `BACKLOG_UPDATED`: Etapa-3 line (no ID verified).
- `DOCUMENTATION_CONFLICTS`: none; thresholds explicitly HYPOTHESIS,
  consistent with AGENTS.md rule 7.
