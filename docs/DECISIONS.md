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

## 2026-10-07 — P1-11A Movers category-value fix + validation conclusions

Movers bug (confirmed, fixed narrowly): `render_movers` in
`dashboard_views.py` wrote every category's display text into one shared
per-row key `_v`, so a symbol present in several tables showed the
last-assigned value everywhere (velocity/accel/vol-z/flow scales mixed).
Fix: per-category display keys (`_v_pct`, `_v_qvol`, `_v_hot`, `_v_vel`,
`_v_acc`, `_v_volz`, `_v_flow`) with the renderer taking the key as a
parameter — the bug class cannot recur. Source fields, sort keys, units
and formatters unchanged. Proven by `MoversIntegrityTest` (unique
fixtures: velocity 1.1e-6, accel 2.2e-8, flow 333333, vol-z 4.4,
quote-vol 55555555, 24h +6.6): 4/5 fail on old code, 5/5 pass fixed.

Durable validation conclusions from the P1-10 4.91h evidence (see
`docs/FEATURE_MODEL.md` for measured scales):

1. Tolerance-anchored UNKNOWN is the right degradation behavior: the
   degraded final hour starved fresh mark buckets (grid fill 31.7%) and
   15m/1h/24h returns went UNKNOWN instead of interpolating. Classifiers
   must consume UNKNOWN/staleness as first-class input.
2. OI is transport-isolated by construction (REST polls vs WS): 0 failures
   in both the healthy (T+2h→T+3h) and degraded (T+4h→END) windows while
   book ingest fell 64%. Keep the poller off the WS path permanently.
3. Funding-rate crossings re-confirmed as a hypothesis-artifact class
   (175–176 valueChanges / 13519 samples → 16.5k crossings); no threshold
   conclusion may ever be drawn from near-constant percentile series.
4. Book resilience and per-trade flow history remain the two retention
   gaps (latest snapshot + 600 bounded buckets only) — owned by P1-11B
   history design, not by live-engine changes.
5. Roadmap order fixed: P1-11A → P1-11B → P1-11C → P1-10R → P1-12 →
   P1-12B → P1-13A → P1-13B → P1-14 → P1-15 → P1-16 (see TASK_QUEUE).

## 2026-10-07 — P1-11A.1 velocity leader sign filter (narrow correctness)

The P1-11A per-category fix exposed the next layer: both velocity tables
drew from the same unfiltered subscribed population, so an all-negative
afternoon rendered negatives under "Fastest POSITIVE velocity". Now the
positive table admits only finite velocity_1m > 0 and the negative table
only finite velocity_1m < 0 (exact zero, None, NaN/inf in neither; empty
side renders an honest note). Membership filter only — velocity formula,
units, momentum engine and rank methodology untouched. Proven by
`MoversVelocitySemanticsTest` (5/5 fail on old code, 5/5 pass fixed) and
live-verified after restart (positive table honestly empty while all CORE
velocities are negative).

## 2026-10-07 — P1-11B historical foundation decisions

1. Separate research DB, not the live one: `data/historical/historical.db`
   (schema v1) — backfill must never disturb dashboard state; the store
   constructor refuses the live path. No manifests/checkpoints sidecar dirs:
   coverage + run ledger + gaps are DB tables (repo convention: SQLite
   stores, `data/` + `logs/` git-ignored).
2. Mark vs regular klines separated BY SCHEMA (mark table has no volume
   columns — verified live that the API serves zeros there), not by comment.
3. OI history: store only the served ~42h (500-row cap measured at 5m);
   never pretend deeper history exists; live tracker untouched.
4. aggTrades REST is most-recent-only (0.1-min-old probe) — no backfill
   designed around it; bounded recent capability only; archives deferred
   until provenance/semantics verified.
5. No historical book reconstruction — depth REST is present-only;
   documented limitation; prospective compact-bucket recorder designed but
   NOT enabled (estimates first).
6. Rate safety by construction: conservative assumed weights + adaptive
   live-weight hard pause (2000/2400), Retry-After honored with budget,
   418 aborts; CLI has no bulk mode (explicit symbols, 7d/25 defaults).
7. Docs-site fallback rule re-applied: developers.binance.com unfetchable
   here → contracts verified live + recorded exactly (MARKET_DATA.md).

## 2026-10-07 — P1-11B.1 probe run-control decisions

1. One registry (`logs/probe_runtime.json`), three launchers (agent CLI,
   direct terminal, dashboard API) — the probe self-registers in
   `__main__`, so all paths converge; dashboard holds no separate truth.
2. Identity = PID + python image + recorded creation time (reused the
   dashboard's own tasklist/wmic model, same trust class). STOP kills only
   the verified PID (SIGTERM POSIX / TerminateProcess Windows — no reliable
   graceful stdlib path exists there for detached children; documented).
   Stale records recover to FAILED, never kill.
3. Mutations are POST-only, localhost Host + local Origin + per-process
   nonce (403 otherwise); fixed argv, forced BOT_MODE=observe, no shell —
   browser input can never become a command.
4. Every control-started probe gets merged UTF-8 file logging
   (`logs/probe-runs/`, validation preset `logs/p1-10r/`) — keeps agent
   harnesses non-blocking and makes P1-10R evidence mechanics default, not
   special. A dashboard 6h run is NOT a validated P1-10R run; only the
   audit decides PASS.
5. UI uses `<input type=submit>`, never `<button` (repo no-controls tests),
   and carries no signal/trading words; process state and feed health are
   rendered side by side, never conflated.

## 2026-10-07 � P1-11C event studies + prospective recorder decisions

1. Historical DB schema v2 (additive): event_definitions / event_study_runs / event_instances / event_feature_snapshots / event_outcomes + research_flow_10s / research_flow_1m / research_book_1m. Research tables live with history (never microprobe.db); retention cleanup runs at most hourly, never per-tick (executor-starvation lesson).
2. The recorder is probe-owned (MarketProbe._research): starts on run() entry, drains (partials marked PARTIAL, book partials discarded) before final_summary. No second process/registry/launcher by construction (tested by source-absence + lifecycle tests).
3. Bounded-queue drops with telemetry (writes/drops/errors/inflight/high_water) instead of backpressure into the WS loop; any DB exception degrades the recorder only (probe never crashes � tested with an impossible path).
4. Sub-1h outcome horizons evaluated on 1h bars honestly share the next-bar outcome (resolution limit, not interpolated precision); 15m pilots added for the trio where stored. No threshold auto-tuning exists anywhere (tested by surface-absence).
5. NMR added by a justified 2-request bounded extension (719 1h bars, ratio 1.0); no bulk fetch. Dashboard research surface is read-only (/api/research/status, /api/events/*, token HISTORICAL RESEARCH card labeled RESEARCH ONLY � NOT A SIGNAL); ENGINE/FEED/RESEARCH states stay distinct; DASHBOARD_VERSION stays 0.8.0 (no IA redesign).

## 2026-10-08 � P1-10R PASS (formal 6h soak)

Single continuous WMI-detached process (PID 19084, 21603.9s, COMPLETED + duration-reached + exit 0, final_summary present). The session-survival problem that killed P1-10 at 4.91h is solved by service-tree parentage (python -> cmd -> WmiPrvSE Session 0), proven first by a 90s proof run on the identical mechanism. Transport verdict: 11/11 streams, 19M msgs, 10 auto-recovered reconnects, 0.76% rejects, p50 170-250ms; three bounded auto-recovered episodes (worst ~9.5min market handshake timeouts ~04:20-04:29Z) and a perfectly clean final hour � P1-10-style collapse did not recur. Research recorder drained STOPPED with 8273/0/0 and ~96% of row estimates. Gate consequence: P1-12 moves from BLOCKED to READY (instruction still required; no auto-start). The tasklist/wmic popup defect stays a documented cosmetic issue (P1-10R-FIX-01); its CREATE_NO_WINDOW fix is explicitly a separate post-soak change, not part of this verdict.

## 2026-10-08 � P1-10R-FIX-01 console suppression

Dashboard PID-identity subprocesses (tasklist/wmic) and probe spawns now pass CREATE_NO_WINDOW on Windows via a single dashboard.no_window_flags() helper (0 on POSIX, so non-Windows behavior is byte-identical). No caching, no WMIC removal, no registry-schema change, no validation weakening � the smallest change that removes the popup mechanism. Proven by mocked regression tests asserting the flag on every spawn path plus a live 75s observe lifecycle; dashboard-only restart (30984 -> 28440) with no probe active.

## 2026-10-08 � P1-12A classifier v0 architecture

New classifier.py module (ClassifierEngine + pure classify_symbol): versioned HYPOTHESIS rules (v0.1.0), evidence for/against + missing + validity on every record, priority REVERSAL > EXHAUSTION > EXPANSION > IGNITION > NORMAL, 2-eval dwell hysteresis with immediate UNKNOWN exit, 2-eval reversal confirmation, cold-restart memory, no forced cycle, no probabilities. Consumes already-built peer-engine rows (no duplicate math, no new endpoints); evaluated once per summary (~0.2ms measured). Persistence schema v7 additive (state_features REPLACE + state_transitions <=500). Dashboard shows a token-page observed-state panel via existing store reads (no new HTTP contract, no Next.js changes). Validated by 25 fixture tests + a 120s observe-only COMPLETED run (9 evals, transitions persisted, 0 orders).

## 2026-10-08 � Project governance: decision traceability & feature backlog

New canonical docs/FEATURE_BACKLOG.md with stable IDs (F-AREA-NN), split approval (DECIDED/PROPOSED) vs implementation (NOT IMPLEMENTED/PARTIAL/IMPLEMENTED/VERIFIED), and a mandatory 7-field closeout policy for every future phase. Registers Market State Intelligence per-dashboard (Python VERIFIED; V2 Overview/Movers/Token DECIDED; timeline PROPOSED) plus deferred P1-12B/P1-13A-B/P1-14/15/16, V2 BFF, and staged CMC work � all grounded in existing docs, no invented approvals. AGENTS.md now requires backlog review before planning and reconciliation after every task. Fixed two stale V2 status lines (P1-10R RUNNING, P1-12 blocked) to match the PASS record.

## 2026-10-08 � P1-12B dynamic universe architecture

New universe_manager.py (pure selection + lifecycle, no I/O): DISCOVERY/CORE/HOT split with explicit lifecycle states (never confused with P1-12A market states); consumes hysteresis-filtered select_hot proposals (no classifier input, no circularity); deterministic movement rank with documented tie-breaks; dwell/cooldown/rank-decay; CORE protection; fail-closed budgets (3 HOT slots, 60 streams, 50/conn, 6 conns � all UNVERIFIED caps, docs unfetchable). Transport: two managed HOT connections (URL callable per reconnect restores desired set); cancel+respawn only on desired change with 60s guard; canonical pair untouched; reconnect != healthy delivery. Engines gained minimal allow/forget; OI poller covers CORE+HOT; recorder finalizes demoted symbols PARTIAL; no DB migration (discovery blob extended). Validated by 31 tests + 300s observe COMPLETED run (3 promotions all LIVE, 0 incidents).

## 2026-10-08 � P1-12B.1 integrity audit corrections

Independent review concerns both reproduced against code: (A) ticker timestamp gate accepted None/future and aborted whole updates on malformed values � fixed with per-candidate fail-closed check_timestamp_fresh() (60s documented skew tolerance, local wall clock as reference); (B) budget math mixed connections into streams and docs claimed 17 canonical vs measured 11 � fixed with single authoritative ccount_streams() shared by enforcement and telemetry. Both errors erred conservative (fail-closed held; no unsafe promotion ever occurred). Added clock_skew_tolerance_ms to UniverseConfig (default 60s, additive). Provider docs still unfetchable � caps unchanged. Proven by 18 tests + 240s observe run; P1-12B PASS preserved append-only.


## 2026-10-11 — DASH-V2-53 strategy research documentation

User authorized evaluation and durable documentation of mover/level strategy intent. Record H-A1 continuation after breakout/retest and H-B1 confirmed short reversal as the first proposed research comparison; H-A2/C1 secondary and H-D1 deferred. Percentage-move cohorts, cap cutoff, confirmation/risk/sample parameters remain hypotheses/open decisions. PROPOSED implementation; no strategy, numeric threshold, classifier change, runtime run, paper or gate approval.

[MOVER_LEVEL_STRATEGY_RESEARCH.md](MOVER_LEVEL_STRATEGY_RESEARCH.md) owns the research specification; FEATURE_BACKLOG.md indexes seven future requirements. Reconcile canonical backend 55efaa2 implementations with V2 snapshot separately. Existing endpoint outcomes do not establish path metrics, executable returns or independent trade counts. Evaluate net expectancy and uncertainty under costs; sub-50% win rate alone is not a rejection rule. Preserve SUCCESS_GATES and existing operational boundaries.


## DASH-V2-61 - 2026-10-11 - withhold dormant launch acceptance

The newly added disabled engine at backend da231b9 has reproduced ownership, revalidation, command, time-budget and uncertainty discrepancies. Keep Start disabled and withhold integration; accepted prior BOOL/evidence-handoff fixes remain closed. Canonical 873/873 plus V2 496/496 pass but do not establish new launch correctness. Follow DASHBOARD_V2_61_SUPERVISED_LAUNCH_REVIEW.md and bounded backend handoff; no operational or strategy authorization.


## DASH-V2-62 - 2026-10-11 - direct bounded backend correction

The user authorized direct correction on the backend branch. Isolated c635938 resolves the V2-61 R1-R5/C1-C2 request in disabled preparation; 902 canonical and 52 focused tests pass with published code checksum checked. V2-61 handoff is historical; no repetition required. Start and runtime code remain unchanged. Enabled capability, actual watcher startup association/real OS behavior and longevity remain deferred. See DASHBOARD_V2_62_BACKEND_CORRECTIONS_ACCEPTANCE.md.

## DASH-V2-70 / V2-69 — 2026-10-11 — extraction accepted and recorded diagnostics
Backend c59c5ec extraction accepted after direct proof/docs repair published 9f3e084192e90b52948c398f021f64b7884e2df2; independent 909/909, no reviewer application-source edit. See DASHBOARD_V2_69_EXTRACTION_ACCEPTANCE.md. V2 recorded diagnostics now avoid timestamp-based run association and display missing-stream, parse/payload-error and signed clock-offset fields. 192/192 frontend, type/lint/build pass; System 3 widths, disclosure/refresh and Overview check pass, zero overflow/browser errors; canonical DB/registry bytes unchanged. Production http://127.0.0.1:3020 managed PID23296. See DASHBOARD_V2_70_RECORDED_DIAGNOSTICS.md. Exact reference fidelity/full cutover remain PARTIAL. Next V2-71 source-backed pipeline/persistence/universe parity; host/events require separate contracts. Old HTML, Start, gates, main and runtime operations preserved.
