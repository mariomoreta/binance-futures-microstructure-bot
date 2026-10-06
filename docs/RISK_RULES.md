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
