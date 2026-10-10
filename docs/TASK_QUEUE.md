# TASK_QUEUE

## Dashboard V2 continuation — 2026-10-10

DASH-V2-47 frontend readiness correction implemented and tested. Next:
Windows acceptance and reconciliation with the owning backend's canonical
atomic supervisor+sentinel launch contract. Start stays disabled.
No probe run, soak or start/stop is authorized by this dashboard correction.
Existing backend task entries below are historical branch records; compare
with the owning backend's current docs before selecting backend work.

Operational next work. Updated every task. Docs-realism rule applies.

## CURRENT_PHASE

PHASE 1 — MARKET INTELLIGENCE + DASHBOARD

Traceability: `docs/FEATURE_BACKLOG.md` (stable IDs; reconcile after every task).

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

- `P1-13A` OPPORTUNITY / SETUP ENGINE — next candidate (starts only on
  explicit instruction). `P1-12B` is PASS (see COMPLETED). Do NOT start
  P1-13A, soaks, or trading automatically.

## NEXT_TASKS (ordered, all Phase 1)
- `P1-10R` PROLONGED ≥6H SOAK RE-RUN — P1-10 FAIL stays FAIL (truncated at
  4.91h); re-run with dashboard live, blocking survivable launch, merged
  stdout+stderr as UTF-8 (see `docs/DECISIONS.md` launch rule).
- Intended full sequence (binding order):
  P1-11A Raw Feature + Movers Integrity (DONE) → P1-11B Historical Data
  Foundation (DONE) → P1-11B.1 Probe Lifecycle + Run Control (DONE) →
  P1-11C Historical Event Studies (DONE) → P1-10R Formal ≥6h soak
  re-run (DONE — PASS) → P1-12A Market State Classifier v0
  (DONE — PASS) → P1-12B Dynamic Live Universe (DONE — PASS) →
  P1-13A Opportunity / Setup Engine (NEXT candidate) →
  P1-13B Professional Opportunities UX
  → P1-14 Historical Backtester → P1-15 Forward Paper Trading → P1-16 Paper
  Portfolio / Dynamic Exit.
- `P1-13` SIGNAL / EXTREME-MOVE UI — add `/signals`, `/extreme-moves`.
- `P1-14` 24H CALIBRATION REVIEW — thresholds vs real crossings + Phase 1 gate
  evaluation per `docs/SUCCESS_GATES.md`.

Out of phase (do NOT start): full event labeling/outcomes (P2), backtests and
strategies (P3), paper engine/positions (P4), execution (P5).

## BLOCKED

- Nothing currently blocked. `P1-13A` is the next candidate pending
  explicit instruction. Later tasks remain sequenced; each starts after
  its predecessor's evidence is recorded.

## COMPLETED

- `P1-12B.1` (2026-10-08) DYNAMIC UNIVERSE INTEGRITY AUDIT: **PASS**.
  Both review concerns reproduced and fixed: fail-closed ticker-
  timestamp gate (missing/malformed/unit/old/future reject; 60s skew
  tolerance) and single authoritative stream accounting (canonical 11,
  connections≠streams, globals once). Docs re-fetch empty — caps stay
  UNVERIFIED. 496/496 tests (18 new). 240s observe COMPLETED: strict
  gate blocks nothing healthy (3 promotions all LIVE, 0 skips).
  P1-12B PASS record preserved (append-only correction).

- `P1-12B` (2026-10-08) DYNAMIC LIVE UNIVERSE V0: **PASS**.
  Bounded HOT selection + lifecycle (`universe_manager.py`, v0) on two
  managed connections (canonical pair untouched): 3 HOT slots default,
  fail-closed budgets, deterministic movement rank, dwell 1800s,
  demotion cooldown 3600s, CORE never evicted. Engine allow/forget
  (flow/book/returns/structure/classifier/OI) + OI HOT poll list +
  recorder per-symbol PARTIAL finalize. 300s observe validation:
  6 proposals → 3 promotions (OGN/MET/GRIFFAINUSDT) all reaching LIVE,
  0 reconnects/rejects, HOT research buckets captured, 6 symbols
  classified, COMPLETED naturally, 0 orders. 478/478 tests (31 new).
  Spec: `docs/UNIVERSE_SPEC.md`. Transport caps stay UNVERIFIED
  (docs unfetchable here) — re-check before raising budgets.
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
- `P1-11A.1` (2026-10-07) MOVERS VELOCITY SEMANTICS: **PASS**. Sign-filtered
  leader tables (positive only >0, negative only <0; zero/None/NaN/inf in
  neither; honest empty notes). 5 new `MoversVelocitySemanticsTest` tests
  fail 5/5 on old code. Live-verified after restart. 322/322 tests.
- `P1-11B` (2026-10-07) HISTORICAL DATA FOUNDATION: **PASS**. Docs site
  unfetchable → 7 contracts verified live (klines/mark/aggTrades/OI-hist/
  exchangeInfo/weights/limits in `docs/MARKET_DATA.md`). Separate research
  DB schema v1 (mark table structurally volume-free); bounded pagination +
  resume + idempotency + adaptive limiter + 429/418 policy; listing-aware
  ingest (BTC Sep-2019 … ORCA Dec-2024 geneses recorded); CLOSED candles
  only; gaps stay UNKNOWN. Pilot 13 series ratio 1.0 (OI capped at 500
  rows/~41.6h served; aggTrades recent-only; no book reconstruction).
  CLI + `/api/history/*` + token coverage card live. 353/353 tests.
- `P1-11B.1` (2026-10-07) PROBE LIFECYCLE + DASHBOARD RUN CONTROL: **PASS**.
  Canonical `control.py` + registry + probe self-registration (direct
  launches converge); single-instance refusal; verified-PID-only stop;
  merged UTF-8 run logs; POST-only localhost control API (nonce+Origin);
  MARKET ENGINE header UI with polling (Continuous/6h/6H-Validation).
  Live roundtrip proven (dashboard start→RUNNING→STALE→ok→stop; external
  start auto-discovered; 90s run COMPLETED; dashboard survived).
  376/376 tests (23 new).
- `P1-12A` (2026-10-08) MARKET STATE CLASSIFIER V0: **PASS**.
  Deterministic explainable classifier (`classifier.py`, rules v0.1.0,
  all-HYPOTHESIS): NORMAL/IGNITION/EXPANSION/EXHAUSTION/REVERSAL +
  UNKNOWN, UP/DOWN/NONE/UNKNOWN, evidence for/against, missing list,
  validity, transitions with hysteresis (2-eval dwell) + 2-eval reversal
  confirmation, cold-restart memory, no forced sequence, no probabilities.
  Schema v7 (`state_features` + `state_transitions` ≤500); probe
  evaluates per summary (~0.2ms); token-page state panel (no new HTTP
  contract; no Next.js changes). 120s observe run COMPLETED: 9 evals,
  states + 4 transitions persisted, 0 rejects/reconnects, 0 orders.
   447/447 tests (25 new classifier + 2 new persistence). Spec:
   `docs/CLASSIFIER_SPEC.md`.
- `P1-10R-FIX-01` (2026-10-08) WINDOWS CONSOLE POPUPS: **FIXED**.
  `dashboard.no_window_flags()` (CREATE_NO_WINDOW, POSIX-neutral) applied
  to tasklist/wmic identity checks + probe spawn; semantics preserved.
  420/420 tests (12 new, mocked). Dashboard restarted 30984 → 28440;
  75s observe lifecycle COMPLETED naturally with feed HEALTHY while fed.
  P1-10R PASS and P1-12 READINESS unchanged.
- `P1-10R` (2026-10-08) FORMAL ≥6H SOAK RE-RUN: **PASS**. One continuous
  WMI-detached process (PID 19084, 00:48:20Z → 06:48:23Z, 21603.9s ≥
  21600s), registry COMPLETED + duration-reached + exit 0, final_summary
  present, 699 gap-free summaries. Transport: 11/11 streams, 19.0M msgs,
  10 reconnects (all auto-recovered), 0.76% skew-rejects, uptime
  99.10%/99.95%, p50 170–250ms; worst episode ~04:20–04:29Z (~9.5min,
  market handshake timeouts, self-recovered); final hour perfectly clean
  (0 reconnects, 0 rejects) — no P1-10-style collapse. Engines all
  monotonic (flow 566k, book 587k, returns 3886/symbol over 31.5h, OI
  1029/1029, discovery 36 scans). Research recorder drained STOPPED:
  8273 writes, 0 drops, 0 errors (+6191/+1041/+1041 rows, ~96% of
  estimate). DBs bounded (microprobe +32MB at retention caps;
  historical +1.6MB) and integrity-ok. Dashboard alive and truthful;
  popup defect stayed cosmetic. Safety 0/0/0. 408/408 tests.
  Evidence: `logs/p1-10r/probe-20261008T0048Z.log` (local, git-ignored).
   Full analysis in `docs/CURRENT_STATE.md`.
- `P1-11C` (2026-10-07) HISTORICAL EVENT STUDIES + PROSPECTIVE CAPTURE:
  **PASS**. No-lookahead engine (`events.py`, 6 versioned HYPOTHESIS
  families) + schema-v2 event tables in the historical DB + probe-owned
  async flow-10s/1m + book-1m recorder (starts/drains with MarketProbe;
  drops-with-telemetry; failure-isolated; idempotent; bounded retention).
  Pilot 38 runs (6 families × pilot symbols on stored 1h/15m bars; NMR
  added via 2-request bounded extension, 719 bars ratio 1.0). Short live
  verification 153s COMPLETED via the canonical control plane (writes 60,
  drops 0, errors 0). Dashboard `/api/research/status` + `/api/events/*`
  + token research card live. 408/408 tests (32 new).

## LAST_VERIFICATION

- 2026-10-08 (P1-12B.1): `python run_tests.py` → 496/496 OK (478 + 18
  new freshness/accounting tests; toy-epoch fixtures migrated to
  realistic ms epochs). 240s observe COMPLETED (strict gate live-proven).
  Next: P1-13A candidate (needs explicit instruction).

- 2026-10-08 (P1-12B): `python run_tests.py` → 478/478 OK (447 + 31 new
  universe/manager/transport/recorder/classifier tests). 300s observe
  validation COMPLETED via WMI-detached canonical module (temp 60s-scan
  config; repo config untouched): 3 promotions all LIVE, HOT research +
  classifier + dashboard verified, 0 orders. Next: P1-13A candidate
  (needs explicit instruction).
- 2026-10-08 (P1-12A): `python run_tests.py` → 447/447 OK (420 + 25 new
  classifier + 2 new persistence). 120s observe run COMPLETED via the
  canonical plane (9 evals ~0.2ms, states + transitions persisted, token
  pages render, dashboard restarted for the new panel). Next: P1-12B
  candidate (needs explicit instruction).
- 2026-10-08 (P1-10R-FIX-01): `python run_tests.py` → 420/420 OK (408 +
  12 new mocked identity tests; one pre-existing Popen fake extended for
  the new kwarg). Dashboard 30984 → 28440; 75s observe run COMPLETED;
  both frontends 200. P1-10R PASS / P1-12 READY unchanged.
- 2026-10-08 (P1-10R): **PASS**. `python run_tests.py` → 408/408 OK
  (no app changes). 21603.9s continuous, COMPLETED + duration-reached +
  exit 0, final_summary present. Transport/honest-episode analysis,
  research drain (8273/0/0), and gate matrix in `docs/CURRENT_STATE.md`.
  Next: P1-12 READY (needs explicit instruction; thresholds HYPOTHESIS).
- 2026-10-07 (P1-11C): `python run_tests.py` → 408/408 OK (376 + 32 new
  event/recorder tests). Pilot 38 bounded runs stored (NMR extension:
  2 requests, 719 bars, ratio 1.0). Short live verification 150s →
  COMPLETED naturally (research writes 60, drops 0, errors 0). New
  research/event APIs live-verified (200). P1-10R now PASS (see above).
- 2026-10-07 (P1-11B.1): `python run_tests.py` → 376/376 OK (353 + 23 new
  lifecycle/API tests). Live roundtrip verified (dashboard + external
  starts, feed transitions honest, dashboard survived all stops). P1-11C
  DONE. P1-10R still pending (6H-Validation preset mechanics ready;
  audit decides PASS).
- 2026-10-07 (P1-11B): `python run_tests.py` → 353/353 OK (322 + 31 new
  mocked-HTTP history tests). Pilot 13 series ratio 1.0 in
  `data/historical/historical.db`; CLI + history APIs live-verified.

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



## Dashboard V2 next work — 2026-10-10

DASH-V2-48 System visual slice completed with partial reference parity.
Next: reconcile five System data contracts with the owning agent's finished
report before integrating them. Keep atomic start disabled until guarantees
are independently verified. Further work remains frontend-only.


## 2026-10-10 — P1-14B.8 integration review

Backend babf3ac verified in GitHub; sentinel 15/15 targeted tests rerun, SQLite
66/228 quick_check OK. Long supervisor 70 cycles; three-layer evidence only
brief 14/12 cycles (long sentinel died). Reproduced STOPPED-fresh accepted,
malformed-established heartbeat unprotected, stale sentinel published ACTIVE.
Concurrent registry writes/lease fencing need tests. V2 drops sentinel and
start_probe does not launch watchers: F-V2-BFF-01 remains PARTIAL, start blocked.
Owner feedback and documentation discrepancies: DASHBOARD_V2_P1_14B_8_REVIEW.md.
No new run, backend edit, gate advancement or long-run authorization.
