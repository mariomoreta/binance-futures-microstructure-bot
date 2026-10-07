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

## 2026-10-06 — P1-05 discovery + momentum architecture

Discovery uses public REST only (`GET /fapi/v1/exchangeInfo` for
status/contractType/quoteAsset, `GET /fapi/v1/ticker/24hr` for price/24h
change/quote volume) on the same `fapi.binance.com` host family as the
existing clock sync; verified live (924 symbols, TRADING/PERPETUAL/USDT
filtering) after the docs site proved unfetchable from this environment.
Eligible = PERPETUAL + TRADING + USDT + 24h quote volume floor (operator
`min_quote_volume_usdt`, default 1M); unknowns are ineligible with explicit
reasons, never fabricated. No CoinMarketCap, no market-cap ranking (Binance
provides none). Universe tiers: CORE pinned benchmarks, DISCOVERY broad scan,
HOT = core + ≤N dynamic by movement score (|24h%| desc, volume desc, symbol
asc) with vote/dwell hysteresis (enter after 2 consecutive scans, leave after
2 absences, immediate on proven breach). No dynamic websocket resubscription
in P1-05: HOT is proposed and exposed; integration is a documented next step.
Velocity(h;b) = [R_h(t) − R_h(t−b)]/b (default b=h; a flat high return has
~zero velocity — deliberately NOT a renamed return); acceleration is the
timestamp-aware change in velocity (default span h; 1m needs ~3min span).
Ranks per metric descending with (value, symbol) tie-breaks; change/velocity/
acceleration need 2/2/3 evaluations. Live ranks cover subscribed symbols;
broad movers come from 24h REST stats labeled discovery-only — no fake live
features for unsubscribed symbols, no signals anywhere.

## 2026-10-07 — P1-06 aggressive trade-flow architecture

Aggressor semantics (official USD-M docs + live payload verified, recorded
in `docs/MARKET_DATA.md`): `m=true` → aggressive SELL, `m=false` →
aggressive BUY; `q` totals (RPI-inclusive), `nq` tracked for transparency;
bucketing/ordering on `E`. Signed delta = buy − sell notional;
delta_ratio = delta/(buy+sell) in [−1,+1], null on zero denominator —
raw feature, never a signal.
Critical path: VALID raw aggTrade → in-memory incremental `FlowEngine`
(`src/microstructure_probe/flow.py`: per-symbol trailing windows
10s/30s/1m/3m/5m with exact per-horizon expiry, volume baselines
10s/30s/1m/5m on COMPLETED buckets only, 1m-referenced acceleration) →
compact persistence (schema v4: `flow_features` REPLACE-per-symbol +
`flow_buckets` bounded history) → dashboard/API. The P1-04 sampling gate
still throttles raw observation writes only; the engine ingests pre-gate,
synchronously, with its own latency distribution (no per-trade tasks, no
queue — queue metrics honestly 0/0).
Late policy: strictly-older `E` dropped+counted; identical `E` accepted in
arrival order (one 100ms push holds several distinct aggregates — the first
live run proved `<=` undercounts ~35% of BTC flow). Baselines: skipped
buckets counted, never zero-fabricated; z null on insufficient history or
zero variance (never fake 0). Only subscribed CORE symbols get live flow;
HOT/discovery rows are labeled DISCOVERY ONLY — NO LIVE FLOW. Existing
volume-spike detector thresholds stay HYPOTHESIS, untouched.

## 2026-10-07 — P1-06 persistence schema v4 (additive migration)

v3→v4 adds `flow_features` + `flow_buckets` (600-per-(symbol,size)
retention, INSERT OR REPLACE keys); v1/v2 paths extended to land on v4
with rows preserved (tested v1→v4, v2→v4, v3→v4). Only CLOSED buckets
persist/restore, so restarts cannot double-count; live trailing windows
restart empty by design. Telemetry snapshots intentionally carry no flow
block (fixed-column subset, as with returns/discovery) — counters live in
summaries/logs, features in `flow_features`.

## 2026-10-08 — P1-07 order-book intelligence architecture

Depth pushes are FULL top-20 snapshots (verified docs + live payloads, see
`docs/MARKET_DATA.md`). Engine: `src/microstructure_probe/book.py`
(`SymbolBookState` per LIVE symbol, `BookEngine` multi-symbol) ingests
every valid depth message pre-sampling, synchronously, with its own
latency distribution. Features per snapshot: best bid/ask (explicit
max/min, never wire order), mid, spread abs/bps, top-1/5/10/20
base+notional sums, qty/notional imbalance in [-1,+1] (null on zero),
microprice `(Pa*Qb+Pb*Qa)/(Qb+Qa)` + displacement bps, LS-through-origin
slope of cumulative notional vs distance-bps per side + asymmetry,
concentration within 5/10/25bps (null when the visible book does not span
the band, coverage exposed). Crossed tops kept + counted (real transient
data). Invalid books (empty side, bad numbers) dropped + counted, previous
snapshot retained. Late = strictly-older `E` (never regresses); same-E
accepted. Gap policy: `pu != last u` → gap counted, state DEGRADED but the
current full snapshot still featured, until a chained update recovers
(proven live: 1 gap/symbol after a reconnect, all recovered). No composite
quality score (P1-11/P1-12 own modeling). No thresholds anywhere.

## 2026-10-08 — P1-07 open-interest source + polling architecture

Source: public `GET /fapi/v1/openInterest` only (verified live shape
`{symbol, openInterest base units, time}`; 3 req/min at 60s cadence is
negligible under the 1000/5min IP limit). `openInterestHist` evaluated and
DEFERRED: one provenance (our timestamped polls) keeps delta math exact
and scope bounded; revisit as a bootstrap option later. Engine:
`src/microstructure_probe/open_interest.py` — `OpenInterestPoller` (one
sequential round per tick in a worker thread, failures counted, never
breaks WS) + `OpenInterestTracker` (bounded 2000-sample deque/symbol;
deltas vs actual-timestamp anchors with max(60s,h/20) tolerance over
1m/5m/15m; 1m acceleration; UNKNOWN until warmed). Price/OI context labels
(`PRICE_UP_OI_UP` etc., `MIXED` on exact zero, `UNKNOWN` on missing) are
descriptive regime tags only — no long/short/squeeze/bullish/bearish
claims without validated methodology.

## 2026-10-08 — P1-07 persistence schema v5 (additive migration)

v4→v5 adds `book_features` (REPLACE-per-symbol latest snapshot),
`oi_samples` (timestamped polls, 2000/symbol retention, idempotent keys),
`oi_features` (REPLACE-per-symbol). Tested v1/v2/v3/v4→v5 with rows
preserved. Restart rule: OI history restores (timestamps stay valid, gaps
age out via tolerance); the book NEVER restores as live — the latest row
persists for continuity but only fresh depth marks it live.

## 2026-10-09 — P1-08 VWAP-from-flow + mark-price structure methods

No new endpoint: VWAP = flow `notional/base` per trailing window (exact,
same provenance, no second trade ingest); 30m/1h VWAP refused — provenance
ends at 15m and P1-08 invents no window beyond its sources. Reference
price is P1-04 mark `current_price` (labeled `markPrice`, never mixed).
Volatility = raw `sqrt(sum(r²))` over consecutive 10s-bucket log returns
(non-annualized; value needs ≥5 returns spanning window−10s, `warmed`
adds full grid coverage; measured flat zero stays 0.0, distinct from
missing). Range position in [0,1] (null on flat); expansion = current /
trailing median of ≤10 prior completed blocks (+z when ≥10 blocks with
variance, else null). Structure = confirmed pivots, L=R=3 buckets (30s
explicit confirmation delay, no future bars); breakout vs prior completed
15m grid block (`ABOVE/BELOW/INSIDE_PRIOR_RANGE`, else `UNKNOWN`) —
descriptive tags only. Book resilience DEFERRED: spread/depth event
history is retained nowhere, so any recovery-time metric would need a new
retained series — that is P1-11 modeling scope, not a P1-08 freebie.

## 2026-10-09 — P1-08 persistence schema v6 (additive migration)

v5→v6 adds `structure_features` (REPLACE-per-symbol full record:
vwap + volatility + ranges + structure). Tested v1/v2/v3/v4/v5→v6 with
rows preserved. No raw history stored here: inputs recompute each summary
from flow aggregates + persisted buckets, so restart continuity is
inherited (buckets restore, flow windows warm live) — never fabricated.

## 2026-10-09 — P1-09 terminal information architecture (no new sources)

`/overview` becomes a market summary (cards + top activity + compact
live-core rows with token links); full P1-04…P1-08 detail moves to
`/symbol/:symbol` and `/system`. Rationale: the operator's questions are
what-is-moving → which-deserve-inspection → why-interesting → inside-one-
symbol → data-state → scan-to-detail path; a diagnostics console of
disconnected tables answers none of them directly. Three old overview
assertions (flow/book-OI/structure tables on `/overview`) were updated to
assert the same content on `/symbol/:symbol` — intentional IA evolution,
not coverage loss (312/312 green, incl. 35 new P1-09 tests).

## 2026-10-09 — P1-09 dashboard code split (presentation out of routing)

`dashboard.py` (was ~72KB single file) keeps routing + health model +
lifecycle CLI + backwards-compatible render entry points; new
`dashboard_data.py` (capability/tier vocabulary, universe composition,
movers rows, search, bounded chart points), `dashboard_components.py`
(terminal theme, nav, chips, formatters), `dashboard_views.py`
(overview/movers/symbol/search/system renderers). Rationale: the file was
already the largest in the tree and P1-09 triples its renders; the split
follows data-access / presentation / HTTP-routing separation without a
framework or over-engineering.

## 2026-10-09 — P1-09 capability model + bounded chart contract

Tier (CORE/HOT/DISCOVERY) and data state (LIVE/WARMING/DISCOVERY ONLY/
STALE/DEGRADED/UNKNOWN) are orthogonal dimensions with one shared
definition (`dashboard_data.py`); subscribed = symbol present in ANY live
feature set (returns/flow/book/OI/structure), so partially-warmed symbols
still show their honest panels. Chart/CSV read P1-04 `price_samples`
(mark-price 10s buckets, no new source): window-filtered
(now−range…now, future samples excluded), oldest-first, even-downsampled
to ≤1000 points keeping endpoints. Search covers the persisted universe
only (tops + CORE + HOT + live symbols) — the full exchange list is
deliberately not persisted (P1-05 compact-snapshot contract), and the
dashboard never hits Binance REST (read-only over persistence).

## 2026-10-07 — P1-01R PASS unblocks the P1-10 soak (transport precedent)

A 45-minute attached observe-only run (0 reconnects, 0% skew-rejections,
sub-second p50/p95 delivery lag, 5/5 clock sync) is recorded as PASS and
unblocks the P1-10 soak gate. Precedent: transport health in this
environment is variable (P1-01 PARTIAL vs P1-01R PASS), so any future run
showing P1-01-grade degradation (reconnect storm, tens-of-seconds lags,
mass rejection) must trigger a fresh re-validation before soak or
calibration gates may be trusted. No code or threshold changed.

## 2026-10-07 — P1-10 soak launch + log-capture rule (durable, from FAIL)

The P1-10 soak (`--duration 21600`) died externally at 4.91h with no
`final_summary` and unknown exit — same failure shape as the earlier
detached-children lesson (tool-session end kills the run). Rule for P1-10R
and any future multi-hour run: launch attached/blocking from a session
that demonstrably survives the full window; never detached without a
surviving parent. Logging rule: the probe logs to stderr
(`logging.basicConfig`), so a PowerShell `> file` redirect captures only
stdout and PowerShell decorates stderr chunks as UTF-16 error records with
wrapped long lines (P1-10's 52MB log had to be reconstructed fragment by
fragment). P1-10R must capture merged streams explicitly as UTF-8
(e.g. `2>&1` with `$OutputEncoding`/UTF-8, or in-app file logging) so
`startup` / periodic `summary` / `final_summary` records stay greppable.
Audit cadence stands: 30s periodic summaries + per-event detector lines
proved sufficient to reconstruct START/MID/END behavior without any
sidecar files.
