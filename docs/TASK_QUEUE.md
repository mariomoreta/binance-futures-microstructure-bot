# TASK_QUEUE

Operational next work. Updated every task. Docs-realism rule applies.

## CURRENT_PHASE

PHASE 1 — MARKET INTELLIGENCE + DASHBOARD

## CURRENT_OBJECTIVE

Execute Phase 1 in dependency order: tooling sanity → short transport
validation → persistence foundation → minimal dashboard → raw features
(returns → velocity/rank → flow → book/OI → VWAP/vol/structure) with the
dashboard growing alongside → prolonged soak with dashboard live → raw-feature
validation → state classifier v0 → signal/extreme-move UI → 24h calibration
review and gate evaluation.

Binding dependency (project decision 2026-10-06):

```text
RAW MARKET DATA → RAW FEATURES → PERSISTENCE → DASHBOARD VISIBILITY
  → LIVE FEATURE VALIDATION → STATE CLASSIFIER
```

No prolonged blind observation before the dashboard exists. No classifier
before raw-feature dashboard validation.

## ACTIVE_TASK

- `P1-01` SHORT TRANSPORT VALIDATION — 30–60 min observe-only run; measure WS
  connectivity, latency, gaps, staleness, reconnects, data quality. NOT the 6h
  soak. Status: NOT STARTED.

## NEXT_TASKS (ordered, all Phase 1)

- `P1-02` PERSISTENCE FOUNDATION — local observe-only store for raw market
  data/features feeding the dashboard. No trading data, no keys, no private APIs.
- `P1-03` MINIMAL DASHBOARD — routes `/overview`, `/system` exposing:
  connection health, stream health, message rates, latency p50/p95, stale
  symbols, sequence gaps, reconnects, last update, runtime duration.
  Dedicated port (first-free from 8091…), bind 127.0.0.1, health endpoint,
  URL returned to operator. See `docs/DASHBOARD_SPEC.md` access plan.
- `P1-04` SYMBOL UNIVERSE + MULTI-TIMEFRAME RETURNS (1m/3m/5m/15m/1h/4h/24h).
- `P1-05` PRICE VELOCITY / ACCELERATION + RANKING (rank velocity/acceleration).
- `P1-06` VOLUME + AGGRESSIVE TRADE FLOW (multi-bucket z, delta, imbalance).
- `P1-07` ORDER BOOK + OPEN INTEREST (depth slope, microprice, OI delta/accel).
- `P1-08` VWAP + VOLATILITY + MARKET STRUCTURE (displacement, realized vol,
  range expansion, swings/breakouts, no lookahead).
- `P1-09` MARKET-INTELLIGENCE DASHBOARD — add `/movers`, `/symbol/:symbol`;
  show raw features BEFORE classifier scores. Operator keeps working browser
  access through this and all later live stages.
- `P1-10` PROLONGED ≥6H SOAK — run with dashboard live so the operator can
  inspect it and take screenshots while data flows.
- `P1-11` RAW FEATURE VALIDATION — distributions, missingness, freshness,
  obvious measurement errors. Classifier is BLOCKED until this passes.
- `P1-12` STATE CLASSIFIER V0 (NORMAL/IGNITION/EXPANSION/EXHAUSTION/REVERSAL).
  All thresholds explicitly HYPOTHESIS. Allowed only after P1-11.
- `P1-13` SIGNAL / EXTREME-MOVE UI — add `/signals`, `/extreme-moves`.
- `P1-14` 24H CALIBRATION REVIEW — thresholds vs real crossings + Phase 1 gate
  evaluation per `docs/SUCCESS_GATES.md`.

Out of phase (do NOT start): full event labeling/outcomes (P2), backtests and
strategies (P3), paper engine/positions (P4), execution (P5).

## BLOCKED

- `P1-12` (classifier) blocked until `P1-11` passes. All other P1 tasks sequenced
  above; each starts after its predecessor's evidence is recorded.

## COMPLETED

- `BRAIN-00` (2026-10-06) PROJECT_BRAIN infrastructure: AGENTS.md + 20 docs.
- `P1-00` (2026-10-06) REPOSITORY / TOOLING SANITY: canonical test command
  `python run_tests.py` works from repo root, 28/28 green, no app behavior change
  (new root runner only, prepends `src/` to `sys.path`).
- `ORDER-01` (2026-10-06) PHASE1_ORDER_REFINED: P1-00…P1-14 dependency order
  adopted (dashboard-progressive, classifier-after-validation).

## LAST_VERIFICATION

- 2026-10-06: `python run_tests.py` → 28/28 OK. `--show-streams` → correct
  routed `/public` + `/market` URLs. Port candidates 8091/8092/8093/18091/18765
  probed FREE on 127.0.0.1 (dashboard port policy evidence).
- No dashboard running yet (first visible at P1-03). No soak run yet (P1-01).

## LAST_COMMIT

- `157e85e` Phase 1 baseline (pre-brain). Brain files + `run_tests.py`
  staged, uncommitted — commit blocked: no git identity configured.
