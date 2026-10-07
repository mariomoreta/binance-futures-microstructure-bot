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

- `P1-11B` HISTORICAL DATA FOUNDATION — multi-resolution history plan in
  `docs/HISTORICAL_RESEARCH_PLAN.md` (verify current official Binance USD-M
  docs before any implementation; no backfill yet run).
  Status: NOT STARTED. (Queued only — do not begin without a new
  instruction.)

## NEXT_TASKS (ordered, all Phase 1)
- `P1-11B` HISTORICAL DATA FOUNDATION — as above.
- `P1-11C` HISTORICAL EVENT STUDIES — outcomes + MFE/MAE, no lookahead.
- `P1-10R` PROLONGED ≥6H SOAK RE-RUN — P1-10 FAIL stays FAIL (truncated at
  4.91h); re-run with dashboard live, blocking survivable launch, merged
  stdout+stderr as UTF-8 (see `docs/DECISIONS.md` launch rule).
- Intended full sequence (binding order, nothing beyond P1-11A executed):
  P1-11A Raw Feature + Movers Integrity (DONE) → P1-11B Historical Data
  Foundation → P1-11C Historical Event Studies → P1-10R Formal ≥6h soak
  re-run → P1-12 Market State Classifier → P1-12B Dynamic Live Universe →
  P1-13A Opportunity / Setup Engine → P1-13B Professional Opportunities UX
  → P1-14 Historical Backtester → P1-15 Forward Paper Trading → P1-16 Paper
  Portfolio / Dynamic Exit.
- `P1-12` STATE CLASSIFIER V0 (NORMAL/IGNITION/EXPANSION/EXHAUSTION/REVERSAL).
  All thresholds explicitly HYPOTHESIS. Allowed only after the P1-11A/B/C
  evidence chain and the P1-10R gate.
- `P1-13` SIGNAL / EXTREME-MOVE UI — add `/signals`, `/extreme-moves`.
- `P1-14` 24H CALIBRATION REVIEW — thresholds vs real crossings + Phase 1 gate
  evaluation per `docs/SUCCESS_GATES.md`.

Out of phase (do NOT start): full event labeling/outcomes (P2), backtests and
strategies (P3), paper engine/positions (P4), execution (P5).

## BLOCKED

- `P1-12` (classifier) blocked until the P1-11A/B/C evidence chain and the
  `P1-10R` gate. All other P1 tasks sequenced above; each starts after its
  predecessor's evidence is recorded.

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
- `P1-07` (2026-10-08) ORDER BOOK + OPEN INTEREST: **PASS**. Depth/OI docs
  + live payloads verified (full-snapshot `pu`-chain, OI shape);
  `book.py` (spreads, top-N sums, imbalances, microprice, slopes,
  concentration, gap→DEGRADED recovery) + `open_interest.py` (60s bounded
  poller, 1m/5m/15m deltas, accel, descriptive contexts); schema v5 +
  tested migrations; dashboard v0.6.0 (book/OI tables, NO LIVE FLOW/BOOK,
  `/api/features/book` + `/open-interest`). Live 363s run (exit 0):
  11/11, 1 reconnect, book 7309/7309 valid (1 gap/symbol recovered),
  OI 18/18 polls ok, flow 5684 intact, sampling lossless, safety 0/0/0.
   239/239 tests (49 new). Evidence: `logs/p1-07/` (local, git-ignored).
- `P1-08` (2026-10-09) VWAP + VOLATILITY + STRUCTURE: **PASS**. Zero new
  sources (flow-VWAP, bucket vol/range/structure, mark reference);
  `market_structure.py` (stateless over peer state; displacement, raw
  `sqrt(sum(r²))`, median/z expansion, confirmed pivots, breakout tags;
  resilience deferred); schema v6 + tested migrations; dashboard v0.7.0
  (structure table + vwap/volatility/structure APIs, P1-09-ready
  contracts). Live 372s run (exit 0): 11/11, 2 reconnects, STRUCT 27
  evals p50 0.84ms, flow/book/OI intact, sampling lossless, safety 0/0/0.
  277/277 tests (38 new). Evidence: `logs/p1-08/` (local, git-ignored).
- `P1-09` (2026-10-09) MARKET-INTELLIGENCE DASHBOARD: **PASS**. Terminal IA
  (OVERVIEW/MOVERS/`/symbol/:symbol`/SYSTEM + search), capability/tier
  vocabulary, mark-price chart + CSV APIs (bounded, no new source), book
  integrity copy, code split (data/components/views). Dashboard v0.8.0
  live at http://127.0.0.1:8091. Live 360s run (exit 0): 11/11, 0
  reconnects, 0 rejects, lags p50 ~180–260ms, all engines green, safety
  0/0/0; 22 routes 200; discovery-only honesty verified (龙虾USDT).
  312/312 tests (35 new). Evidence: `logs/p1-09/` (local, git-ignored).
  P1-10 NOT started; P1-01R still owed before it.
- `P1-01R` (2026-10-07) TRANSPORT RE-VALIDATION: **PASS**. Attached
  2700s observe-only run (exit 0): 11/11 streams, 0 reconnects, 0 rejects,
  corrected lags p50 171–251ms / p95 ≤390ms, gaps 0, clock 5/5 ok,
  engines green, persistence drained, safety 0/0/0; dashboard `ok`
  while fed, honest `stale` after. Evidence: `logs/p1-01r/`
  (local, git-ignored). P1-10 soak gate unblocked; P1-10 NOT started.
- `P1-10` (2026-10-07) PROLONGED SOAK: **FAIL** (truncated). Requested
  21600s, one continuous process, but killed externally at 17677.9s
  (4.91h, 81.8%) with no `final_summary` and unknown exit. 554 gap-free
  periodic summaries fully audited: bookTicker core stayed P1-01R-grade
  (p50 ~190–200ms) while aggTrade ETH/SOL (p50 90–152s), depth/markPrice
  tails and a final-hour reconnect storm (29 reconnects + 366k rejects in
  55 min) regressed to P1-01-grade. Engines/persistence/dashboard/safety
  all behaved (details in `docs/CURRENT_STATE.md`). Evidence:
  `logs/p1-10/probe-21600s.log` (local, git-ignored). Requires `P1-10R`.
- `P1-11A` (2026-10-07) RAW FEATURE + MOVERS INTEGRITY AUDIT: **PASS**.
  Used the valid 4.91h of P1-10 evidence (P1-10 stays FAIL). Movers
  shared-`_v` contamination bug found, root-caused, fixed narrowly
  (per-category display keys; sources/sorts/units/formatters unchanged;
  5 new `MoversIntegrityTest` tests fail 4/5 on old code, pass 5/5 fixed).
  All feature families measured trustworthy as raw research inputs
  (scales/availability in `docs/FEATURE_MODEL.md`; healthy-vs-degraded
  comparison: degradation starves honestly, OI isolated, no corruption).
  Design-only plans added: `docs/SIGNAL_RESEARCH_PLAN.md` (BTC context,
  exhaustion, absorption, opportunity lifecycle, backtest/paper sim),
  `docs/HISTORICAL_RESEARCH_PLAN.md` (P1-11B/C). 317/317 tests.

## LAST_VERIFICATION

- 2026-10-07 (P1-11A): `python run_tests.py` → 317/317 OK (312 + 5 new
  `MoversIntegrityTest`). Movers fix + full feature validation recorded in
  `docs/CURRENT_STATE.md` + `docs/FEATURE_MODEL.md`; P1-10 stays FAIL.
- 2026-10-07 (P1-10 closure): `python run_tests.py` → 312/312 OK (no app
  code changed during the soak; HEAD still `cca1b78`). Soak FAIL closed
  (17677.9s/21600s, truncated, evidence in `docs/CURRENT_STATE.md` +
  `logs/p1-10/`).

- 2026-10-07 (P1-01R): `python run_tests.py` → 312/312 OK (before run;
  no code changed). 2700s transport run PASS (0 reconnects, 0% rejects,
  sub-second lags). Full evidence in `docs/CURRENT_STATE.md` +
  `logs/p1-01r/`.
- 2026-10-09 (P1-09): `python run_tests.py` → 312/312 OK. Terminal live
  (v0.8.0, 22 routes 200, chart + CSV + search verified, safety 0/0/0).
  Full evidence in `docs/CURRENT_STATE.md` + `logs/p1-09/`.
- 2026-10-09 (P1-08): `python run_tests.py` → 277/277 OK. Structure
  eval live (27 evals, p50 0.84ms); dashboard v0.7.0 with structure
  table + APIs (200). Full evidence in `docs/CURRENT_STATE.md`.
- 2026-10-08 (P1-07): `python run_tests.py` → 239/239 OK. Book engine live
  (7309/7309, p50 0.15ms); OI 18/18 polls; dashboard v0.6.0 with book/OI
  tables + APIs (200). Full evidence in `docs/CURRENT_STATE.md`.
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
