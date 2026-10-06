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

- `P1-02` PERSISTENCE FOUNDATION — local observe-only store for raw market
  data/features feeding the dashboard. No trading data, no keys, no private APIs.
  Status: NOT STARTED. (Network-independent; NOT blocked by P1-01 PARTIAL.)

## NEXT_TASKS (ordered, all Phase 1)

- `P1-01R` TRANSPORT RE-VALIDATION (follow-up, before P1-10): repeat the 30–60
  min observe-only run in a healthy network; must show stable connections
  (reconnects ≈ 0 unexplained), delivery lags in the low-second range, and
  skew-rejections back to rare outliers before soak/calibration gates can pass.

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
- `P1-01` (2026-10-06) SHORT TRANSPORT VALIDATION: **PARTIAL**. 1805s
  observe-only run, exit 0, 11/11 streams, uptime 98.5%/95.0%, but 58
  reconnects (`ConnectionClosedError`, no close frame), corrected delivery
  lags p50 15–38s / p95 45–76s, 147417 skew-rejections (~85%), depth gaps
  50/49/49, 26 funding events judged sampling artifacts (not signals).
  Evidence: `logs/p1-01/probe-1800s.log` (local, git-ignored). Tests 28/28
  before and after. Gates G2–G4 cannot pass on this evidence.

## LAST_VERIFICATION

- 2026-10-06 (P1-01): `python run_tests.py` → 28/28 OK before and after the
  live run. 1805s observe-only probe: exit 0, safety 0/0/0 throughout;
  transport unhealthy in this environment (58 reconnects, p50 lags 15–38s,
  85% skew-rejected). Full evidence in `docs/CURRENT_STATE.md`.
- Port candidates 8091/8092/8093/18091/18765 probed FREE on 127.0.0.1
  (dashboard port policy evidence).
- No dashboard running yet (first visible at P1-03).

## LAST_COMMIT

- Branch `phase1/market-intelligence-dashboard` published to private
  `mariomoreta/binance-futures-microstructure-bot` (origin in sync).
  Prior: `d6801a5` brain checkpoint on top of `157e85e` baseline.
  P1-01 evidence/docs commit follows on this branch.
