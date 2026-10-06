# PAPER_TRADING

Phase 4 scope. No paper engine exists. Nothing here authorizes trading.

## Purpose

Trade candidate strategies (Phase 3 outputs) against live public data with
simulated fills, to confirm or reject backtest expectancy before any execution
conversation.

## Requirements (when built)

- Simulated fills with explicit fee + slippage model (configurable, recorded
  per fill; sensitivity analysis mandatory — edge that dies at 2x costs is noted).
- State-driven, evidence-driven exits via the position manager
  (`docs/POSITION_MANAGEMENT.md`); fixed-time exits only as a baseline comparator.
- Full audit trail: signal → fill → management actions → exit, with
  config/version recorded.
- Performance accounting feeding `/paper` and `/performance`: expectancy,
  win rate, profit factor, MFE/MAE capture, drawdown, exposure time, costs paid.
- Risk limits enforced by the risk engine, unbypassable (`docs/RISK_RULES.md`).

## Rules

- Paper trading validates; it does not promise. No fixed-profit projections —
  probabilistic distributions from historical similar cases only.
- Divergence paper-vs-backtest beyond tolerance stops promotion and opens an
  investigation task; it never "adjusts" the backtest to match.
- Phase 5 (controlled execution) requires proven paper profitability AND
  explicit human authorization. This file alone authorizes nothing.
