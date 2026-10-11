# MASTER_PLAN

Stable strategic direction. Factual state lives in `docs/CURRENT_STATE.md`;
operational next work lives in `docs/TASK_QUEUE.md`.

## Direction

Build the Binance Futures market-intelligence system described in
`docs/PRODUCT_GOAL.md`: observe → understand → paper-prove → (only then, with
explicit authorization) consider execution. Final KPI is profitability and
risk-adjusted expectancy.

## Canonical architecture

```text
Binance public market data
  → normalization
  → feature engine
  → market-state / signal engine
  → persistence
```

Persistence feeds dashboard, research, and later paper trading.

Later:

```text
signal engine → position manager → risk engine → execution engine
```

Risk engine can never be bypassed. Dashboard never feeds the engine.

See `docs/ARCHITECTURE.md`.

## Phases and gates

| Phase | Name | Gate summary |
|---|---|---|
| 1 | Market Intelligence + Dashboard | Sustained multi-symbol WS coverage, feature engine (returns/velocity/rank/VWAP/vol), state classifier v0, dashboard routes live, 0 signals treated as entries |
| 2 | Persistent Dataset + Event Labeling | Snapshots persisted, forward outcomes (30s→60m + MFE/MAE) computed, dataset queryable |
| 3 | Strategy Discovery + Backtesting | Candidate strategies with costs/slippage, out-of-sample validation, expectancy report |
| 4 | Live Paper Trading + Position Mgmt | Live paper engine with state-driven exits, risk limits enforced, performance vs backtest |
| 5 | Controlled Execution | Explicit human authorization required. Small-size, kill-switch, full audit trail |

Full criteria: `docs/SUCCESS_GATES.md`. Sequence and dependencies: `docs/ROADMAP.md`.

## Current phase

**PHASE 1 — MARKET INTELLIGENCE + DASHBOARD.** Baseline: audited observe-only
probe (v0.2.0) + canonical `python run_tests.py`. Execution follows the binding
P1-00…P1-14 dependency order in `docs/TASK_QUEUE.md` (dashboard-progressive,
classifier only after raw-feature validation). Persistence foundation is a
Phase 1 task (P1-02); full labeling stays Phase 2. No paper trading and no
execution until their phases and authorizations.


## 2026-10-11 - Recorded research focus, phases unchanged
The user's mover/level strategy discussion is preserved in STRATEGY_THESIS.md
and [Movers and Levels](MOVER_LEVEL_STRATEGY_RESEARCH.md). First proposed studies:
H-A1 continuation after breakout/retest and H-B1 confirmed reversal after an
extended rise; secondary/deferred studies remain separate. Factual gap/approval
tracking is in FEATURE_BACKLOG.md. Existing historical labels and prospective
endpoints are foundations, not completion of full Phase 2/3 strategy validation.
No phase gate, active runtime task, run authorization or execution boundary
changes merely because this design is recorded.
