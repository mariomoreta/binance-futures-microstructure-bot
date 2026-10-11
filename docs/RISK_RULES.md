# RISK_RULES

Unbypassable by design: neither signal nor position engines can override risk.
(Enforcement code arrives with the engines in Phases 4–5; limits below are
starting constraints, not yet live code.)

## Starting limits (hypothesis, tighten-only without a decision record)

- Max concurrent paper positions, max notional per position, max total exposure.
- Per-trade max adverse excursion stop; daily loss limit → halt + human review.
- Kill-switch: data staleness beyond tolerance, WS outage, or config/version
  mismatch halts new entries immediately; open paper positions go to
  protect/exit mode.
- Cost awareness: strategies must clear fees + slippage with margin
  (sensitivity at 1x/2x/3x costs in every report).

## Forbidden (without explicit human authorization)

Private account APIs, API keys in repo/env, order placement/cancellation,
leverage or position changes, signing, withdrawals/transfers, live capital,
enabling execution. See `docs/SAFETY_RULES.md`.

## Rules

- Any loosening of a limit requires a `docs/DECISIONS.md` entry with evidence.
- Risk events (halts, kills, limit hits) are first-class log/persisted records.
- In Phase 1 the "risk engine" is the observe-only enforcement + no-order-paths
  static test. That is sufficient because there is nothing to lose — keep it so.


## 2026-10-11 - Proposed operability gate for movers
Future requirements: [Movers and Levels](MOVER_LEVEL_STRATEGY_RESEARCH.md).
Small capitalization/large 24h change never waives liquidity or data quality.
Before any future simulated entry, separately validate freshness/clock/coverage,
spread and depth sufficient for the proposed size, frozen invalidation, maximum
chase price/expiry, cost sensitivity and exposure constraints. Descriptive
classifier minimum-data gates cannot substitute for these checks.
Position sizing must use a separately selected loss budget and adverse-move plus
cost assumptions; stops do not guarantee fill at their trigger price. No numeric
risk limit, leverage setting, averaging-down rule or live protection guarantee
is chosen by this documentation. Existing tighten-only/governance rules remain.
