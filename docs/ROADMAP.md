# ROADMAP

Future sequence. Operational now lives in `docs/TASK_QUEUE.md`.
Decision/feature traceability lives in `docs/FEATURE_BACKLOG.md`.

## Phase 1 — Market Intelligence + Dashboard (CURRENT)

Dependency order (binding — see `docs/DECISIONS.md` 2026-10-06):

```text
RAW MARKET DATA → RAW FEATURES → PERSISTENCE → DASHBOARD VISIBILITY
  → LIVE FEATURE VALIDATION → STATE CLASSIFIER
```

1. `P1-00` Tooling sanity — canonical `python run_tests.py` ✅ DONE.
2. `P1-01` Short transport validation (30–60 min observe-only; NOT the 6h soak).
3. `P1-02` Persistence foundation (local observe-only store → dashboard).
4. `P1-03` Minimal dashboard (`/overview`, `/system`: connection/stream health,
   message rates, latency p50/p95, stale symbols, gaps, reconnects, last
   update, runtime). Dedicated local port, 127.0.0.1, health endpoint.
5. `P1-04` Symbol universe + multi-timeframe returns.
6. `P1-05` Price velocity/acceleration + ranking.
7. `P1-06` Volume + aggressive trade flow.
8. `P1-07` Order book + open interest.
9. `P1-08` VWAP + volatility + market structure.
10. `P1-09` Market-intelligence dashboard (`/movers`, `/symbol/:symbol`;
    raw features before classifier scores). Browser access maintained live.
11. `P1-10` Prolonged ≥6h soak with dashboard live (screenshots while flowing).
12. `P1-11` Raw feature validation (distributions, missingness, freshness).
13. `P1-12` State classifier v0 (hypothesis thresholds; only after P1-11).
14. `P1-13` Signal / extreme-move UI (`/signals`, `/extreme-moves`).
15. `P1-14` 24h calibration review → Phase 1 gate evaluation.

### Parallel Dashboard V2 lane (architecture foundation complete)

Dashboard V2 does not reorder the market-intelligence dependencies above and
does not unblock P1-12. Its implementation is a reversible parallel lane:
contract normalization → frontend shell → Overview → Movers → token detail →
System/control → parity and cutover. Each slice must pass the gates in
`docs/DASHBOARD_V2_MIGRATION_PLAN.md`; the Python SSR dashboard remains the
rollback surface until parity is evidenced.

## Phase 2 — Persistent Dataset + Event Labeling

Builds on the P1-02 foundation: snapshot schema → outcome calculator
(30s→60m, MFE/MAE, peak/trough, continuation/reversal) → backfill/validation →
research access docs.

## Phase 3 — Strategy Discovery + Backtesting

Hypothesis A/B statistical tests → candidate definitions → cost-aware
backtests → out-of-sample + sensitivity → expectancy reports.

## Phase 4 — Live Paper Trading + Position Management

Paper engine → position manager (HOLD … FULL_EXIT) → risk enforcement →
paper/performance surfaces → divergence monitoring.

## Phase 5 — Controlled Execution

Authorization gate → small-size execution with kill-switch → audit. Not planned
in detail until Phase 4 proves expectancy. No code before authorization.


## 2026-10-11 - Proposed research sequence for movers/levels
Detailed dependencies: [Movers and Levels](MOVER_LEVEL_STRATEGY_RESEARCH.md).
After current runtime corrections and applicable phase gates, sequence proposed
work as: as-of identity/cohorts -> frozen level definitions -> full snapshot/path
adequacy -> incremental BTC/flow-response context -> optional catalyst ledger ->
costed H-A1/H-B1 comparison -> later paper validation. UI consumes reviewed
read-only research contracts; it does not determine strategy or execution.
Backlog IDs F-RES-MOVERS-01 through F-RES-VALIDATION-01 / F-V2-RESEARCH-01 remain
PROPOSED / NOT IMPLEMENTED. This ordering is not an instruction to launch runs,
backfills or advance phases; operational work remains in TASK_QUEUE.md.
