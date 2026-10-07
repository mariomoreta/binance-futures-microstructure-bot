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

Binding dependency — actual Phase 1 execution order (project decision
2026-10-06, reconciled with build sequence):

```text
P1-00 tooling → P1-01 transport validation → P1-02 persistence foundation
  → P1-03 minimal live dashboard → P1-04…P1-08 progressive raw features
  → P1-09 intelligence dashboard → P1-10 soak → P1-11 feature validation
  → P1-12 classifier → P1-13 signal UI → P1-14 calibration review
```

Persistence lands before raw features so the dashboard becomes useful
progressively; raw features must still be dashboard-validated (P1-11) before
any classifier (P1-12) consumes them. No prolonged blind observation before
the dashboard exists. No classifier before raw-feature dashboard validation.

## ACTIVE_TASK

- `P1-07` ORDER BOOK + OPEN INTEREST (depth slope, microprice, OI delta/accel).
  Status: NOT STARTED. (Queued only — do not begin without a new instruction.)

## NEXT_TASKS (ordered, all Phase 1)
- `P1-07` ORDER BOOK + OPEN INTEREST (depth slope, microprice, OI delta/accel).
- `P1-08` VWAP + VOLATILITY + MARKET STRUCTURE (displacement, realized vol,
  range expansion, swings/breakouts, no lookahead).
- `P1-09` MARKET-INTELLIGENCE DASHBOARD — add `/movers`, `/symbol/:symbol`;
  show raw features BEFORE classifier scores. Operator keeps working browser
  access through this and all later live stages.
- `P1-01R` TRANSPORT RE-VALIDATION (before P1-10): repeat the 30–60 min
  observe-only run in a healthy network; must show stable connections
  (reconnects ≈ 0 unexplained), delivery lags in the low-second range, and
  skew-rejections back to rare outliers before soak/calibration gates can pass.
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
- `P1-02` (2026-10-06) PERSISTENCE FOUNDATION: **PASS**. SQLite
  (`data/microprobe.db`, git-ignored), 3 tables + 9 indexes, schema v1 with
  version gate + column migration. Write path wired in probe (valid
  observations incl. markPrice MULTI records, skew-rejections to rejection
  table only, periodic snapshots on every summary). Non-blocking verified
  (schedule p50 0.021ms/p95 0.039ms; 2000-row drain 9.2s off-loop).
  47/47 tests green (19 persistence incl. probe write-path integration).
  P1-03 may read via `latest_telemetry()` / `latest_observations()`.
- `P1-03` (2026-10-06) MINIMAL LIVE DASHBOARD: **PASS**. Stdlib-only server
  (`dashboard.py`, v0.3.0, no new deps); routes `/overview`, `/system`,
  `/api/health`, `/api/snapshot` on P1-02 reads. Live at
  http://127.0.0.1:8091 (PID file `logs/dashboard.pid`), health `ok` at
  startup, all routes 200. Live-verified fix: dedicated snapshot writer
  (executor starvation → 0 snapshot rows; +regression test). 66/66 tests
  (18 dashboard). Seeded with real 40s probe data (no mocks).
- `P1-04` (2026-10-06) SYMBOL UNIVERSE + MULTI-TIMEFRAME RETURNS: **PASS**.
  Universe trio preserved with explicit metadata; mark-price log returns
  (7 TFs, 10s buckets, tolerance max(60s, tf/20), UNKNOWN never 0);
  sampling gate (accepted 36/dropped 858 counted in run); schema v2 + tested
  migration; dashboard Symbol Returns + `/api/features/returns` live.
  Live 240s clean run (exit 0, final_summary): 11/11 streams, 5 reconnects,
  11448 skew-rejects (~93% degraded env), engine 46 samples/symbol, 0 invalid,
  inflight high-water 345 drained to 0, safety 0/0/0. 106/106 tests.
- `P1-05` (2026-10-06) DISCOVERY + VELOCITY/ACCEL/RANKING: **PASS**. REST
  discovery (924 seen → 449 eligible → 475 filtered; core pinned); HOT 6
  small sharp movers (USUSDT +41%, 龙虾USDT +35%, BR/ORCA/NMR/GRIFFAIN),
  vote/dwell hysteresis, no WS changes; velocity/accel/ranks live on trio
  (accel honestly warming); intel UI + `/api/discovery` +
  `/api/features/momentum`; persistence v3 + tested migrations; forceOrder
  never-missing; health blocks separated. Clean 240s run (exit 0): 11/11,
  0 reconnects, 0 rejects, 143659 msgs, engine 91 samples/symbol, sampling
   accepted 1888/dropped 141k, high-water 6 → 0, safety 0/0/0. 144/144 tests.
- `P1-06` (2026-10-07) VOLUME + AGGRESSIVE TRADE FLOW: **PASS**. Official
  aggTrade docs + live payload verified (`m`/RPI-`nq`/`E`/`st`);
  `flow.py` engine (6 trailing horizons, 4 baselines, acceleration,
  same-E arrival fix after run 1 proved `<=` undercounts); schema v4 +
  tested migrations; dashboard v0.5.0 (flow table, split bars, DISCOVERY
  ONLY labels, `/api/features/flow` + `/volume`). Healthy 363s run
  (exit 0): 11/11, 0 reconnects, 0 rejects, 4027/4027 aggTrades into the
  engine (746 persisted raw — sampling provably lossless to flow),
  168/168 buckets, latency p50 0.030ms/p95 0.069, queue 0/0, safety 0/0/0.
  190/190 tests (46 new). Evidence: `logs/p1-06/` (local, git-ignored).

## LAST_VERIFICATION

- 2026-10-07 (P1-06): `python run_tests.py` → 190/190 OK. Flow engine live
  (4027/4027 accepted, 0 late, 0 invalid); dashboard v0.5.0 `ok`-while-fed
  with flow table + APIs (200). Full evidence in `docs/CURRENT_STATE.md`.
- 2026-10-06 (P1-05): `python run_tests.py` → 144/144 OK. Discovery live
  (449 eligible, HOT 6 small movers, promotions logged); momentum/ranks live
  on trio; clean 240s run exit 0 with final_summary
  (`logs/p1-05/probe-240s-clean.log`); dashboard `ok`-while-fed,
  STALE/DEGRADED honestly after. Full evidence in `docs/CURRENT_STATE.md`.
- 2026-10-06 (P1-04): 106/106 OK; dashboard live at http://127.0.0.1:8091.
- 2026-10-06 (P1-01): 1805s observe-only probe: exit 0, safety 0/0/0
  throughout; transport unhealthy in this environment (58 reconnects, p50 lags
  15–38s, 85% skew-rejected). Full evidence in `docs/CURRENT_STATE.md`.
- Port candidates 8091/8092/8093/18091/18765 probed FREE on 127.0.0.1
  (dashboard port policy evidence).
- Dashboard RUNNING at http://127.0.0.1:8091 (PID tracked in
  `logs/dashboard.pid`); snapshot STALEs honestly without a live probe feed.

## LAST_COMMIT

- Branch `phase1/market-intelligence-dashboard` published to private
  `mariomoreta/binance-futures-microstructure-bot` (origin in sync).
  P1-05 implementation/docs commit follows on this branch.
