# P1-13A Research Opportunity / Setup Engine (V0)

**Status**: IMPLEMENTED + VALIDATED (observe-only)
**Rules version**: `OPPORTUNITY_RULES_VERSION = "v0.1.0"`
**Dashboard version**: 0.9.0 (bumped for P1-13A)

## What it does

An explainable, versioned, OBSERVE-ONLY engine that identifies market setups
worthy of further research. It consumes existing P1-12A classifier output,
P1-12B universe, and all feature rows — never recalculates states, never
generates orders/signals.

## Setup families (5)

| Family | Trigger |
|---|---|
| `MOMENTUM_CONTINUATION` | EXPANSION + direction-consistent velocity + agreeing flow |
| `IGNITION_WATCH` | COOLDOWN + velocity reversal + flow agrees |
| `EXHAUSTION_WATCH` | COOLDOWN + momentum decel + range breakout |
| `REVERSAL_WATCH` | REVERSAL + confirmation requirements met |
| `EXTREME_MOVE_RESEARCH` | Extreme move (vol > 4σ) not explained by flow |

## Lifecycle

`DETECTED → WATCHING → ACTIVE_RESEARCH → INVALIDATED/EXPIRED → UNKNOWN`

- Cooldown: 60s after INVALIDATED/EXPIRED (prevents flapping)
- TTL: 24h default (auto-expires open candidates)
- Max candidates: 50; max events: 500 (rolling)

## Persistence (schema v8)

- `opportunity_candidates` — REPLACE per candidate_key
- `opportunity_events` — append-only, 500-row cap
- All version upgrade chains migrated through v8

## Fabrication guards

- No confidence percentages, no win-rate, no expected return, no MFE/MAE
- No "probability of X%" patterns; honest disclaimers use "NOT ... probability"
- `interpretation` field says "research priority only — NOT expected profit"

## Integration points

- `OpportunityEngine` wired into `Probe` via `opportunity()` property
- Demotion: `forget(symbol)` + `classifier.forget(symbol)` + `engine.forget()`
- Promotion: `allow(symbol)` clears cooldown, starts cold
- Dashboard: `/opportunities` page + `/api/opportunities` JSON endpoint

## Tests

58 tests in `tests/test_opportunity.py` — all pass.
Full suite: 554 tests OK.

## Validation run (120s, observe-only)

- 3 candidates stored (REVERSAL_WATCH, DETECTED)
- 4 lifecycle events
- 7 state rows (rules v0.1.0)
- Safety: BOT_MODE=observe, apiKeysUsed=0, realOrdersSent=0
- Streams: 11/11 active, 0 missing, 0 stale
