# DECISIONS

Append-only. Newest at the bottom. Never rewrite past entries; supersede with
a new dated entry.

## 2026-09-01 — Observe-only probe baseline (v0.1.0)

Public WS only (`bookTicker`, `depth20@100ms`, `aggTrade`, markPrice/funding,
forceOrder), `BOT_MODE=observe` enforced, thresholds in `config/probe.json`.
12.1s connectivity evidence; 0 threshold crossings — not calibration.

## 2026-09-01 — Phase 1B latency/clock correction (v0.2.0)

Single global clamped lag retired as gate metric (kept labeled `legacy`).
Per-stream/symbol raw/corrected E- and T-lags, monotonic processing split,
5-sample midpoint clock sync, near-miss/warm-up telemetry, cadence-only
staleness (event-driven silence ≠ stale). Rationale: the old metric mixed
semantics and hid the responsible stream.

## 2026-10-06 — PROJECT_BRAIN infrastructure created

Created `AGENTS.md` + 20 docs under `docs/` defining product goal, strategy
hypotheses (A momentum / B exhaustion, both unproven), feature model, market
states, dashboard spec, event labeling, paper/position/risk rules, gates,
roadmap, workflow, commands, and task queue. No engine/safety code changed;
`docs/PHASE_1_REPORT.md` preserved. Baseline: 28/28 tests green
(`PYTHONPATH=src`), commit `157e85e`, clean tree. Current phase set to
PHASE 1 — MARKET INTELLIGENCE + DASHBOARD.

## 2026-10-06 — Phase 1 execution order refined (P1-00…P1-14)

Binding dependency: RAW MARKET DATA → RAW FEATURES → PERSISTENCE →
DASHBOARD VISIBILITY → LIVE FEATURE VALIDATION → STATE CLASSIFIER.
No prolonged blind observation before the dashboard exists (minimal dashboard
at P1-03: `/overview`, `/system`); no classifier before raw-feature dashboard
validation (classifier P1-12 BLOCKED until P1-11 passes). This supersedes the
earlier "soak first" sketch.

## 2026-10-06 — Persistence foundation moved into Phase 1 (P1-02)

The "Phase 1 persists nothing" rule is superseded: a local observe-only
persistence foundation (raw market data/features → dashboard) is now an
explicit Phase 1 task. Rationale: the dashboard must become useful
progressively; it cannot visualize what is never stored. Still forbidden in
Phase 1: trading data, keys, private APIs, paper/live trading. Full event
snapshots + forward outcomes remain Phase 2 (`docs/EVENT_LABELING.md`).

## 2026-10-06 — Canonical test command (P1-00)

`python run_tests.py` from repo root (new root runner, prepends `src/` to
`sys.path`; exit 0/1). Retires the `PYTHONPATH=src` workaround. 28/28 green,
no application behavior changed. Dashboard port policy set: ordered candidates
from 8091, first-free at startup, bind 127.0.0.1, health endpoint, PID file;
8091/8092/8093/18091/18765 probed FREE.

## 2026-10-06 — P1-02 persistence architecture (SQLite, 3-table split)

Stdlib SQLite at `data/microprobe.db`, no new dependencies. Three tables with
distinct contracts: `telemetry_snapshots` (periodic summaries for the
dashboard), `market_observations` (valid-only, `is_valid` filter enforced at
read), `rejected_observations` (skew/parse rejects as telemetry, never feature
input). Writes are fire-and-forget via `asyncio.to_thread` under a lock so the
websocket loop only pays scheduling cost (~0.02ms); failures log
`persistence_error` and never break the probe. Retention bounds
(1000/10000/1000) cap steady-state storage. Rejected messages return before
the valid-write code path, so invalid data cannot become valid records by
construction. During verification this decision also fixed: missing
`spread_bps_json` column, INSERT arity, sync-context rejection crash, legacy
dict-vs-REAL binding, dropped markPrice arrays (now `MULTI` records), unwired
  snapshot persistence.

## 2026-10-06 — Phase 1 execution order supersedes the data-dependency sketch

The older binding chain (RAW MARKET DATA → RAW FEATURES → PERSISTENCE →
DASHBOARD VISIBILITY → LIVE FEATURE VALIDATION → STATE CLASSIFIER, recorded
above) is explicitly SUPERSEDED as a build order — it is preserved above for
history, not deleted. It described logical data-dependency, but building in
that order would force prolonged blind observation before any dashboard
exists. The binding execution order is now:

transport validation → persistence foundation → minimal live dashboard →
progressive raw features → live feature validation → classifier.

Persistence therefore lands before raw features so the dashboard becomes
useful progressively (P1-03 reads P1-02 state from day one); raw features must
still be dashboard-validated (P1-11) before any classifier (P1-12) consumes
them. No classifier before validation remains in force.

## 2026-10-06 — P1-03 dashboard stack (stdlib only, no framework)

`src/microstructure_probe/dashboard.py`: stdlib `ThreadingHTTPServer` +
server-rendered HTML (dark, auto-refresh 10s) + JSON API; zero new
dependencies. Rationale: the minimal dashboard needs tables and health JSON,
not a framework; API/data layer (`DashboardState` over P1-02 read paths) is
separate from presentation so P1-04+ metrics extend models, never the server.
Lifecycle is a Python CLI (`start/stop/restart/status/serve/pick-port`) with
PID file `logs/dashboard.pid` (pid + port + process creation time; stale or
foreign PIDs are never killed). Health model (display heuristics, not
signals): ok/degraded/stale/unknown from snapshot age (>120s = stale),
stale streams, reconnect count, retained rejection rate (>50% = degraded).

## 2026-10-06 — Dedicated snapshot writer (executor-starvation fix)

Live verification showed 0 snapshot rows while 9260 observations landed:
snapshot tasks starved behind thousands of queued observation writes on the
shared default executor (per-insert retention DELETEs saturate all workers
under floods). Fix: snapshots run on a dedicated single-thread executor, so
the dashboard feed can never wait behind bulk observation traffic; backed by
a regression test (flood + snapshot). Observation backpressure itself remains
a known risk owned by P1-04 sampling (queued tasks grow memory under extreme
sustained rates; the WS loop itself never blocks).

## 2026-10-06 — P1-04 canonical return source + sampling architecture

Canonical return input is Binance USD-M **mark price** (`markPrice` field `p`),
not aggTrade: it is the only regular (~1s), per-symbol, event-time-stamped
series, hence the only one fittable in a bounded sampled store. aggTrade
remains the future flow source (P1-06); bookTicker mid stays microstructure.
Semantics: log returns on 10s event-time buckets (last price wins, coalescing
counted), anchor = latest sample at-or-before (current − tf) within
max(60s, tf/20), else UNKNOWN (never 0, never interpolated, never lookahead).
Out-of-order/late samples are dropped, never rewrite history.
Backpressure: observation persistence is time-decimated per (stream kind,
symbol) — bookTicker/aggTrade/depth at most 1/s (code defaults, operator
overridable via `observation_sample_ms`, empty disables); markPrice arrays
and forceOrder ungated. Dropped writes are counted in `sample_stats()`
(surfaced in summaries), never hidden. No retention-limit increase.
