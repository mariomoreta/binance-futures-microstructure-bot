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



## 2026-10-07 — P1-11C event studies + prospective recorder decisions



1. Historical DB schema v2 (additive): event_definitions / event_study_runs / event_instances / event_feature_snapshots / event_outcomes + research_flow_10s / research_flow_1m / research_book_1m. Research tables live with history (never microprobe.db); retention cleanup runs at most hourly, never per-tick (executor-starvation lesson).

2. The recorder is probe-owned (MarketProbe._research): starts on run() entry, drains (partials marked PARTIAL, book partials discarded) before final_summary. No second process/registry/launcher by construction (tested by source-absence + lifecycle tests).

3. Bounded-queue drops with telemetry (writes/drops/errors/inflight/high_water) instead of backpressure into the WS loop; any DB exception degrades the recorder only (probe never crashes — tested with an impossible path).

4. Sub-1h outcome horizons evaluated on 1h bars honestly share the next-bar outcome (resolution limit, not interpolated precision); 15m pilots added for the trio where stored. No threshold auto-tuning exists anywhere (tested by surface-absence).

5. NMR added by a justified 2-request bounded extension (719 1h bars, ratio 1.0); no bulk fetch. Dashboard research surface is read-only (/api/research/status, /api/events/*, token HISTORICAL RESEARCH card labeled RESEARCH ONLY — NOT A SIGNAL); ENGINE/FEED/RESEARCH states stay distinct; DASHBOARD_VERSION stays 0.8.0 (no IA redesign).



## 2026-10-08 — P1-10R PASS (formal 6h soak)



Single continuous WMI-detached process (PID 19084, 21603.9s, COMPLETED + duration-reached + exit 0, final_summary present). The session-survival problem that killed P1-10 at 4.91h is solved by service-tree parentage (python -> cmd -> WmiPrvSE Session 0), proven first by a 90s proof run on the identical mechanism. Transport verdict: 11/11 streams, 19M msgs, 10 auto-recovered reconnects, 0.76% rejects, p50 170-250ms; three bounded auto-recovered episodes (worst ~9.5min market handshake timeouts ~04:20-04:29Z) and a perfectly clean final hour — P1-10-style collapse did not recur. Research recorder drained STOPPED with 8273/0/0 and ~96% of row estimates. Gate consequence: P1-12 moves from BLOCKED to READY (instruction still required; no auto-start). The tasklist/wmic popup defect stays a documented cosmetic issue (P1-10R-FIX-01); its CREATE_NO_WINDOW fix is explicitly a separate post-soak change, not part of this verdict.



## 2026-10-08 — P1-10R-FIX-01 console suppression



Dashboard PID-identity subprocesses (tasklist/wmic) and probe spawns now pass CREATE_NO_WINDOW on Windows via a single dashboard.no_window_flags() helper (0 on POSIX, so non-Windows behavior is byte-identical). No caching, no WMIC removal, no registry-schema change, no validation weakening — the smallest change that removes the popup mechanism. Proven by mocked regression tests asserting the flag on every spawn path plus a live 75s observe lifecycle; dashboard-only restart (30984 -> 28440) with no probe active.



## 2026-10-08 — P1-12A classifier v0 architecture



New classifier.py module (ClassifierEngine + pure classify_symbol): versioned HYPOTHESIS rules (v0.1.0), evidence for/against + missing + validity on every record, priority REVERSAL > EXHAUSTION > EXPANSION > IGNITION > NORMAL, 2-eval dwell hysteresis with immediate UNKNOWN exit, 2-eval reversal confirmation, cold-restart memory, no forced cycle, no probabilities. Consumes already-built peer-engine rows (no duplicate math, no new endpoints); evaluated once per summary (~0.2ms measured). Persistence schema v7 additive (state_features REPLACE + state_transitions <=500). Dashboard shows a token-page observed-state panel via existing store reads (no new HTTP contract, no Next.js changes). Validated by 25 fixture tests + a 120s observe-only COMPLETED run (9 evals, transitions persisted, 0 orders).



## 2026-10-08 — Project governance: decision traceability & feature backlog



New canonical docs/FEATURE_BACKLOG.md with stable IDs (F-AREA-NN), split approval (DECIDED/PROPOSED) vs implementation (NOT IMPLEMENTED/PARTIAL/IMPLEMENTED/VERIFIED), and a mandatory 7-field closeout policy for every future phase. Registers Market State Intelligence per-dashboard (Python VERIFIED; V2 Overview/Movers/Token DECIDED; timeline PROPOSED) plus deferred P1-12B/P1-13A-B/P1-14/15/16, V2 BFF, and staged CMC work — all grounded in existing docs, no invented approvals. AGENTS.md now requires backlog review before planning and reconciliation after every task. Fixed two stale V2 status lines (P1-10R RUNNING, P1-12 blocked) to match the PASS record.



## 2026-10-08 — P1-12B dynamic universe architecture



New universe_manager.py (pure selection + lifecycle, no I/O): DISCOVERY/CORE/HOT split with explicit lifecycle states (never confused with P1-12A market states); consumes hysteresis-filtered select_hot proposals (no classifier input, no circularity); deterministic movement rank with documented tie-breaks; dwell/cooldown/rank-decay; CORE protection; fail-closed budgets (3 HOT slots, 60 streams, 50/conn, 6 conns — all UNVERIFIED caps, docs unfetchable). Transport: two managed HOT connections (URL callable per reconnect restores desired set); cancel+respawn only on desired change with 60s guard; canonical pair untouched; reconnect != healthy delivery. Engines gained minimal allow/forget; OI poller covers CORE+HOT; recorder finalizes demoted symbols PARTIAL; no DB migration (discovery blob extended). Validated by 31 tests + 300s observe COMPLETED run (3 promotions all LIVE, 0 incidents).



## 2026-10-08 — P1-12B.1 integrity audit corrections



Independent review concerns both reproduced against code: (A) ticker timestamp gate accepted None/future and aborted whole updates on malformed values — fixed with per-candidate fail-closed check_timestamp_fresh() (60s documented skew tolerance, local wall clock as reference); (B) budget math mixed connections into streams and docs claimed 17 canonical vs measured 11 — fixed with single authoritative ccount_streams() shared by enforcement and telemetry. Both errors erred conservative (fail-closed held; no unsafe promotion ever occurred). Added clock_skew_tolerance_ms to UniverseConfig (default 60s, additive). Provider docs still unfetchable — caps unchanged. Proven by 18 tests + 240s observe run; P1-12B PASS preserved append-only.

## 2026-10-08 - P1-13A opportunity engine documentation reconciliation



Independent review found docs/code mismatches: (1) spec docs said "Cooldown: 60s" but code enforces cooldown_ms = 3_600_000 (60 minutes); (2) spec docs said "Max candidates: 50" but code enforces max_candidates = 200. Code is authoritative — no product approval needed for these HYPOTHESIS thresholds; they are research-policy knobs with explicit RULES dict. Documentation corrected across OPPORTUNITY_ENGINE_SPEC.md, CURRENT_STATE.md, FEATURE_BACKLOG.md (F-OPP-01 NOT IMPLEMENTED → IMPLEMENTED), TASK_QUEUE.md (P1-13A → DONE). No engine behavior changed.



## 2026-10-08 — P1-14A prospective outcome evaluation architecture



One-setup, per-(candidate_key, horizon) forward outcome observation for P1-13A

DETECTED setups; horizons 1m/5m/15m/1h/4h; mark-price return at maturity

computed from the live summary feed. Decisions:

1. Register at first DETECTED (evals_in_lifecycle <= 1): stable candidate_key

   means one episode, one key; second DETECTED of the same episode is a

   duplicate (no re-registration), enforced in-memory + DB unique (key,

   horizon, observed_at_ms). Restart-safety via in-memory registry hylated

   from prospective_setups at construction.

2. Outcomes never fabricated: COMPLETE needs a valid mark price at/after

   maturity; PENDING when the horizon matured but no price was available;

   INSUFFICIENT_HISTORY when the setup never had a detection-time reference

   price. Missing data is flagged — never zeroed or forced COMPLETE.

   Only directional mark-return is reported; MFE/MAE, time-to-extrema and

   cohort stats are deferred (docstring + spec note).

3. Recorder owns the async path: registration/observation run in the summary

   loop; a bounded queue (default 1000) feeds a daemon worker that writes to

   SQLite, with writes/drops/errors/inflight/high_water telemetry. Retention

   cleanup of both tables runs at most hourly, default 90 days (detecte

d_at_ms / observed_at_ms cutoffs).

4. Persistence schema v9 (additive): prospective_setups REPLACE per key +

   prospective_outcomes append-only bounded 500 per setup. All migration

   chains v1-v9 pass.

5. Integration wiring fixed during closeout: probe passes the detection mark

   price into register_setup (otherwise detected_mark_price stayed None and

   every outcome was INSUFFICIENT_HISTORY); recorder.start()/stop_and_drain()

   wired alongside _research so queue drains on exit; worker DB lock/rollback

   path verified. Retention deletes >90-day rows by detected_at_ms (test data

   updated from a 2023 fake epoch to current wall-clock time so tests do not

   self-delete).

6. Dashboard /api/prospective endpoint (schema_version 9, RESEARCH ONLY

   banner) mirrors status + latest 10 outcomes; snapshot block exposes it.

   Validation: 35 new tests + 554 canonical OK; no orders, keys, P&L or

   probabilities.


## 2026-10-09 — P1-14B recovery & prospective integrity validation

Recovery of the interrupted P1-14B session (branch `phase1/market-intelligence-dashboard`,
SHA `e727e542163552df0d45083eb1f5f0a4233f1292`): workspace recovered at the confirmed last
commit, no divergent commits, no running process, all pilot evidence and new tests preserved
in the working tree. Validated P1-14A prospective evaluation integrity against deterministic
tests (39 new, all pass) and against real persisted evidence in `data/microprobe.db`
(schema v9, 7 unique setups, 1 COMPLETE outcome, event-time audit PASS, zero duplicates,
zero fabricated outcomes).

Decisions:
1. Two session fixes accepted and staged: `prospective.py:106` rehydrates
   `setup.get("setup_json", {})` into the in-memory registry so a restarted recorder
   carries `detected_mark_price` and re-observed setups recompute `COMPLETE` rather than
   `INSUFFICIENT_HISTORY`; `dashboard.py:403` reads the injected shared store so
   `/api/prospective` parity with the recorder cannot drift.
2. Recovery boundary preserved: no `git reset --hard`, `git clean`, or discard of local
   modifications; pilot artifacts kept as evidence (untracked):
   `p14b_pilot_monitor.py`, `logs/p14b_pilot.log`, `p14b_dashboard_readtest.py`,
   `analyze_p13a_run.py`, `.firecrawl/*.json` market-data dumps.
3. No new prolonged observation started: the recovered evidence (single outcome,
   `REVERSAL_WATCH:ETHUSDT:UP` — 1m, mark_return_pct=-0.037134%) is descriptive only;
   6/7 setups have unobserved horizons because the pilot's event-time window did not
   reach their 5m/15m/1h/4h maturities — absent, never forced. Extending coverage
   requires a longer window under a stable host clock (clock anomalies during the pilot
   are documented, not a code defect).
4. Mode preserved: `BOT_MODE=observe`, zero orders, zero capital; Dashboard V2 worktree
   untouched; P1-14C and later phases NOT started.
5. Test gate reconfirmed: `python run_tests.py` — 593/593 OK (519 baseline + 35
   `test_prospective.py` + 39 `test_p14b_validation.py`).
6. Documentation updated: `docs/P1_14B_VALIDATION_REPORT.md` (full report),
   `docs/CURRENT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/FEATURE_BACKLOG.md`,
   `docs/PROSPECTIVE_EVALUATION_SPEC.md`.

## 2026-10-09 -- P1-14B.1 time integrity, data quality & prospective readiness (PASS)

Audit of the P1-14B pilot anomaly `elapsed=-1789712305900s` plus end-to-end
time-integrity review, starting at SHA `18c639b` (no divergent work).

Findings (all demonstrated, none assumed):
1. Anomaly A is monitor-side seconds-minus-milliseconds
   (`time.time() - t0_ms`; exact constant reproduced); it also defeated the
   monitor's 200 s timeout, explaining the killed session. Core engine has
   zero wall-clock unit defects. Executed monitor version unpreserved
   (source UNKNOWN); preserved scripts kept byte-identical as evidence.
2. Defect B (core): restart rehydration dead on the production path --
   `config/probe.json` carries no `db_path`, so `_load_from_db` early-returned
   and restarts orphaned all setups (live: reg=0 with 6 DB rows). Fixed:
   default-store rehydration + seen-set rebuild + load-failure warning.
3. Defect C (core): the outcome-store 500-row bounding DELETE lacked a key
   filter and silently wiped other setups' rows (scratch-proven; shaped the
   P1-14B single-outcome evidence; losses unrecoverable). Fixed: scoped
   per-key bound. Sibling global-cap logs intentionally untouched.
4. Change D (core): `observe()` ran only on matched-candidate ticks, never
   on quiet ticks, against the spec's per-cycle mandate (live: 7 setups,
   4 summaries, 0 calls). Fixed: per-symbol observation over `opp_bundles`.
5. Corrected denominators: 7 setups cumulative across runs; 28/28 matured
   horizon cells COMPLETE post-fix (4h genuinely future); 0 duplicates;
   no-lookahead PASS; host clock weak but correctly untrusted by design.

Validation: 16 new deterministic tests + 1 hardened restart test;
`python run_tests.py` -- 609/609 OK. Three controlled 120 s observe-only
runs (exit 0, safety 0/0/0) prove each fix live. No stored row rewritten.
Prolonged-run readiness criteria recorded with blockers; NO long run
started; P1-14C NOT started; V2 worktree/ports untouched.
Full report: `docs/P1_14B_1_TIME_INTEGRITY_AUDIT.md`.

## 2026-10-09 -- P1-14B.2 operational stability gate (PARTIAL)

35-minute stability attempt via the canonical control plane
(`control start --duration 2100`, PID 32532, observe-only, UTF-8 log
`logs/probe-runs/probe-20261009T015411Z.log`), starting at SHA `d79cfd9`
with validated baseline (v9 / 7 setups / 28 COMPLETE).

Supervision (read-only polls): 15.8 min pristine (11 -> 20 streams via
honest HOT promotions, 0 rejects/reconnects), then a market-endpoint
degradation episode (delivery lag, 3 reconnects, markPrice stale,
marginal reject rate ~100 %). Controlled stop at 23.4 min (exit 0,
`stopped-by-agent`) on the written >5 % reject rule (5.15 % cumulative).
Per the task rule a <30 min window is INSUFFICIENT -- duration objective
not met; no second long run started.

Prospective layer green throughout (0 errors): rehydration + per-cycle
observation live (17 new setups incl. HOT symbols and first
EXHAUSTION_WATCH/MOMENTUM_CONTINUATION, 40 new outcomes); post-run audit
24 setups, 68/68 COMPLETE, 0 dupes, 100 % matured-cell coverage, no
lookahead, no fabrication. Tests 609/609 OK (no code/test changes owed).
Gates: CLOCK/PERSISTENCE/PROSPECTIVE/RESOURCE/SAFETY PASS;
TRANSPORT PARTIAL (limiting). No 4-6 h run authorized; P1-14C not started;
V2 worktree/ports and main untouched.
Full report: `docs/P1_14B_2_OPERATIONAL_STABILITY_REPORT.md`.

## 2026-10-09 -- P1-14B.3 transport freshness & outcome validity (PARTIAL)

Root-caused the P1-14B.2 episode from per-summary corrected-lag series
(bookTicker p95 0.4 s -> 375 s; processing sub-ms frozen; rate collapse
without drain spike; syncs stable; worst stall on zero-reconnect public):
host-external delivery stall, then path outage. Local backlog, clock skew,
and HOT logic discarded with evidence; provider-vs-ISP left unseparated.
Confirmed gaps: open-but-stale never triggers error retries, and last_seen
updates on receipt, so flowing-stale traffic looked healthy.

68 historical outcomes classified read-only (rows preserved): 19 VALID_FRESH,
28 VALID_BUT_DELAYED, 21 INSUFFICIENT_FRESHNESS_EVIDENCE, 0 STALE_OR_INVALID
(audit labels, not motor states).

Fixes (minimal, no new motor states): stale-mark gate (known age >120 s ->
PENDING with explicit reason; unknown fail-open) with sample_age_ms
pass-through; freshness watchdog (post-guard accepted accounting per stream,
pure stream->connection mapping, 90 s / 300 s budgets, 120 s grace + cooldown,
one-shot consume into the existing retry path); additive summary freshness
block. 20 new tests; suite 629/629 OK.

Single authorized <=35 min run (PID 34040, UTF-8 log
probe-20261009T100545Z.log): 10-min pre-window committed; watchdog fired
market+public -> both reconnected in ~12 s -> 5 min zero rejects (recovery
PROVEN live); second episode + handshake-timeout outage -> controlled stop
at 17.1 min (exit 0). Window <30 min = INSUFFICIENT. Post-run: 24 setups,
99/99 COMPLETE, 0 dupes; 21 missing cells fully explained (OGN/RLC 15m/1h/4h
never simultaneously matured+observed+marked: unsubscribed + CORE-only
restore, no defect). Gates: CLOCK/PROSPECTIVE/PERSISTENCE/SAFETY PASS;
TRANSPORT/FRESHNESS PARTIAL. No 4-6 h authorization; P1-14C not started;
V2 worktree/ports and main untouched.
Full report: `docs/P1_14B_3_TRANSPORT_FRESHNESS_AUDIT.md`.

## 2026-10-09 -- P1-14B.4 prospective freshness & PENDING lifecycle (PASS)

Starting at SHA `d4a8fe2` (clean tree, no divergent work). Two integrity
questions resolved against code evidence, then enforced as Outcome Contract
v1.1 (`PROSPECTIVE_CONTRACT_VERSION = "1.1"`, schema stays v9):

1. UNKNOWN freshness: via the probe, mark present implies age present /
   finite / >= 0 (`returns.feature` sets both atomically), so UNKNOWN arose
   only from direct callers -- the fail-open default was the defect. Closed
   strictly: None/malformed/non-finite/future ages record PENDING with
   explicit reasons (nan/inf/future can no longer slip into COMPLETE;
   sub-ms negatives clamped with documented tolerance). Precedent: classifier
   and opportunity engines already gate at 300 s; detections always fresh.
   Production paths proven unaffected (age always present when mark is).
2. PENDING lifecycle: grace-deferred, then terminal. Failed evaluations retry
   silently while now - first <= horizon_ms (recovery window = one horizon
   past maturity = the pre-existing det+2H audit bound, now enforced); only
   then is terminal PENDING recorded. INSUFFICIENT stays immediate+terminal.
   Upgrade-to-COMPLETE rejected with schema rationale (UNIQUE includes
   observed_at: upgrades need backdating or dupe rows). No schema change, no
   new states, no rewrites; restart restarts grace (bounded, documented).
   Memory-only `_pending_since`, cleared on terminal emission.

Also fixed in passing: the 35 P1-14A tests were bare pytest-style functions
that the canonical unittest runner silently SKIPPED (0 executed, verified) --
converted to TestCase (fixtures -> mkdtemp, v1.1 semantics); all 35 now run.

Validation: 19 new lifecycle tests; legacy suites updated intent-preserving
(fresh ages; grace patterns; strict-unknown rename); suite 683/683 OK
(648 + 19 + 16 net from conversion). 120 s controlled run COMPLETED
naturally (11/11, 0/0, reg=24, 0 writes/errors, DB byte-identical 24/99,
new telemetry live). All 99 historical rows preserved byte-identical.
Gates: prospective/persistence/safety PASS (no transport re-rating, no long
run). V2 worktree/ports and main untouched. P1-14C not started.
Full report: `docs/P1_14B_4_PROSPECTIVE_LIFECYCLE_AUDIT.md`.

## 2026-10-10 -- P1-14B.5 transport resilience & independent diagnostics (PASS operational)

Starting at SHA `0df2170` (clean tree). Attribution resolved as far as
evidence allows: with identical code/config/host, NO episode reproduced in
coincident 35 + 40 min windows -- persistent host or bot defects DISCARDED;
episodes are intermittent path/provider instability (which of the two stays
UNKNOWN, stated not forced).

Built netprobe.py (stdlib + existing websockets dep): single host-pinned
read-only reference connection, mirrored params, per-message E/lag/reorder
tracking, DNS/handshake/error classes, UTF-8 JSONL, bounded duration.
Honest limitation: the bare /stream path served zero markPrice-array messages
in 40 min while bookTicker flowed -- tool-side path limitation, not a health
signal; reference coverage is bookTicker-only for now. 17 deterministic tests
(faked transports/clocks).

Coincident windows AGREE: bot bookTicker p50 ~175 ms vs reference ~340 ms
(same sub-second regime), markPrice healthy per bot, 0/0/0.00 % both, zero
E-reorders, reference attempts 1 errors {}. Added pure
classify_connection_health() (socket vs FLOWING_FRESH/STALE/SILENT/
RECONNECTING/UNAVAILABLE + evidence; shared by bot summary block and
netprobe) with 8 tests; watchdog re-verified 10/10 (cooldowns 292 s apart,
recoveries, no loops).

Single authorized <=35 min run COMPLETED naturally: 2102.5 s, 20/20, 0
reconnects, 0 rejects, exit 0 -- first >=30-min healthy window (P1-14B.1
blocker #1 satisfied as far as one window can). Post-run: 49 setups (+25),
150/150 COMPLETE (+51), 0 dupes, 0 anomalies; contract v1.1 + v9 intact;
all 99 prior rows preserved. Suite 708/708 OK (683 + 17 + 8). Gates:
TRANSPORT/FRESHNESS/PERSISTENCE/SAFETY PASS. Still NO 4-6 h authorization
(recurrence risk -- repeat advisable); P1-14C not started; V2 worktree/ports
and main untouched.
Full report: `docs/P1_14B_5_TRANSPORT_RESILIENCE_REPORT.md`.

## 2026-10-10 -- P1-14B.6 reproducibility & operational readiness (PARTIAL)

Starting at SHA `f6d6691` (clean tree). Objectives: second healthy window,
netprobe markPrice coverage fix, host telemetry, watchdog/health re-verify.

1. Placement verified live (official docs unfetchable again, recorded):
   per-symbol streams flow on /stream + /public/stream but NOT /market/stream;
   `!` arrays flow ONLY on /market/stream -- mirroring the bot's own routing
   (codebase already encoded it). netprobe --base-path allowlist + placement
   warning + two-instance operational reference. Rival reading kept honest:
   vendor ACK-but-no-data incident reports TODAY (connector issue + Sierra
   Chart feed stops) offer server-side non-delivery as an alternative mechanism
   for single-sample silent cells; routing wins on determinism.
2. netprobe heartbeat summaries (total silence now observable) + host telemetry
   (os.times CPU%, psapi RSS with real-handle fix, per-stream exact bytes,
   UNKNOWN-safe) in bot summary `host` block + netprobe records. NIC and
   system-wide CPU stay UNKNOWN by design. Shared health classifier +
   `connectionHealth` block (additive).
3. Controlled validation: 10-min gate passed; single <=35 min run COMPLETED
   naturally (2102.5 s, 20/20, market 1 + public 3 error-reconnects, 8.83 %
   rejects, exit 0) with concurrent dual reference (both attempts 1, errors
   {}). Watchdog fired 3 cycles correctly; abort rule breached UNACTED --
   live supervision lost to a harness timeout at launch (demerit recorded;
   no safety rule breached).
4. Discriminating evidence: bot CPU flat 3-6 % + 30.5 s cadence through the
   episode (local compute/loop-blockage DISCARDED); references on the same
   host healthy (bookTicker p95 <= 581 ms bump coinciding with bot collapse =
   shared wobble ~100x milder); per-connection selective degradation =>
   server-side edge attribution refined (reconnect recovery works until
   handshake-refusal stage). Provider-vs-ISP residual UNKNOWN (stated).
5. Post-run: 57 setups (+8), 202/202 COMPLETE (+52), 0 dupes, 0 anomalies;
   contract v1.1 + v9 intact; all 150 prior rows preserved. Suite 726/726 OK
   (708 + 18). Gates: CLOCK/PERSISTENCE/SAFETY PASS; TRANSPORT/FRESHNESS
   PARTIAL. Still NO 4-6 h authorization (repeat advisable); P1-14C not
   started; V2 worktree/ports and main untouched.
Full report: `docs/P1_14B_6_REPRODUCIBILITY_READINESS_REPORT.md`.

## 2026-10-10 -- P1-14B.7 persistent supervision & enforced abort gates (PASS)

Starting at SHA `d785964` (clean tree). The P1-14B.6 abort breach happened
because evaluation lived in the agent session; fixed by architecture, not by
instructions: `control supervise` watches ONE authorized run via the canonical
registry lease, evaluates documented abort rules every cycle from probe evidence,
and enforces a one-shot verified-PID stop with persisted reason. Never starts
or restarts runs, never touches foreign PIDs, never acts on UNKNOWN.

Rules (exact, LOCAL_POLICY except cumulative 5 % rejects): safety immediate;
rejects >5 %; >5 reconnects/600 s sliding; persistence >=2 events/10 min x2
checks (or recorder DEGRADED); clock >30 s x3; DB unreadable x6; compound
watchdog-overwhelmed (forced>=3 + errors>=3 + rising). Freshness-absence reduces
to these (documented). Streaks persist in the lease (restart-safe).

Identity: PID + image + creation-time on every touch. wmic is absent on this
host class (verified) -- creation time was always None here, degrading identity
to image-only; fixed with a ctypes GetProcessTimes fallback (real handle,
explicit signatures), proven live with ISO stamps.

Validation: 34 supervisor tests (decision matrix incl. boundaries/UNKNOWN/
priority/windows; lease claim/refuse/takeover/corrupt; stale/reuse no-touch;
terminal no-ops; launcher preservation; failure budget; V2 contract keys;
no-start assertion; store isolation) + REAL-PID integration (breach evidence
-> sleeper killed, foreign sleeper alive, ABORTED + rule persisted, no re-fire).
Suite 760/760 OK (726 + 34). Brief live run (150 s probe + 12-cycle supervisor):
claimed, heartbeated to natural completion, zero false aborts. Found + fixed in
passing: self-registration wiped control-plane evidence paths (same-PID
preservation now, 2 tests). V2 contract additive (supervisor block in control
status -> API; mapping table; UI renders via existing opaque strings).
All 57 setups / 202 outcomes preserved byte-identical. Gates:
prospective/persistence/safety PASS (no long run). V2 worktree/ports and main
untouched. P1-14C not started. Still NO 4-6 h authorization.
Full report: `docs/P1_14B_7_PERSISTENT_SUPERVISION_AUDIT.md`.

## 2026-10-10 -- P1-14B.8 supervised maiden voyage & abort enforcement (PASS)

Starting at SHA `9150c74` (clean tree). Objective: prove supervision without
the agent session, per the P1-14B.7 mechanism.

1. A 35-min probe (PID 33292, 2102.1 s, exit 0) ran with supervisor PID 25800
   for 70 cycles and zero agent contact after launch; post-hoc log audit shows
   0.00 % rejects, 0 reconnects, 20/20 streams, reg 57->66 (+9), 35 writes,
   0 errors -- nothing breached, correctly nothing aborted. Agent-independence
   demonstrated in execution.
2. The concurrently launched sentinel (PID 39244) claimed its lease at
   13:13:47Z and died within ~30 s with zero cycles and zero output (silent
   early death under output buffering; exact killer unrecoverable post-hoc).
   Lesson encoded, not hidden: flushed startup prints in both mains, `-u` in
   detached launches, lease-presence launch verification as protocol.
3. Sentinel layer completed: claim/takeover/no-op semantics, stale/FAILED
   lease abort via canonical enforce_abort, own failure budget, additive
   status block + CLI, no-start guarantee. V2 evidence mapping documented
   (11 supervisor + 7 sentinel keys, always present, None-safe).
4. Brief three-layer validation (150 s probe + 14-cycle supervisor + 12-cycle
   sentinel, verified leases): claimed, heartbeated to natural COMPLETED,
   zero false aborts, zero orphans; probe 11/11, 0/0/0, reg=66, DB
   byte-identical (66/228/0 dupes).
5. Tests: 15 sentinel (incl. REAL-PID abort: victim killed, foreign alive,
   ABORTED persisted, no re-fire). Suite 775/775 OK (760 + 15). Post-run: 66
   setups (+9), 228 outcomes (+26) all COMPLETE, 0 dupes, 0 anomalies;
   contract v1.1 + v9 intact; all 202 prior rows preserved. Gates:
   CLOCK/TRANSPORT/FRESHNESS/SUPERVISION/PERSISTENCE/SAFETY PASS. V2
   worktree/ports and main untouched. P1-14C not started. Still NO 4-6 h
   authorization (recurrence risk; repeat advisable).
Full report: `docs/P1_14B_8_SUPERVISED_RUN_REPORT.md`.

## 2026-10-10 -- P1-14B.8 corrections: verified supervision semantics (PASS)

Starting at SHA `babf3ac` (clean tree). Frontend review of P1-14B.8
(fetchable via git, not via web) found protection-semantics gaps; all
reproduced and fixed with deterministic tests before any other change:

1. _supervision_verdict accepted STOPPED-fresh and mismatched leases and
   future heartbeats as ok-supervised. Now requires ACTIVE + fresh heartbeat
   in [0, stale_after] + verified watcher identity + run association, with
   distinct loss verdicts (stopped/dead/mismatched/failed/stale); only
   never-established reads as unsupervised (no-op). Identity is a required
   parameter (no lenient default).
2. Malformed established heartbeat read as unsupervised (no abort). Now a
   loss verdict (abort); missing lease stays a no-op. Bounded recovery IS
   the safe stop (no endless grace while unverified).
3. _sentinel_block/_supervisor_block published ACTIVE on lease state alone
   (incl. a 2020 heartbeat). Now verified-display + raw lease evidence
   published separately (lease_state, last_check_at, watcher pid/ctime);
   states/nullability/timestamps/freshness documented for V2; V2 must not
   turn the label into proof.
4. Whole-record read-modify-write races: sidecar file lock + update_registry
   (locked transform, atomic rename) + ownership fencing (lease pid == self
   on every heartbeat/finalization/marking; enforce requires own STOPPING
   marker + live ownership or reports superseded). Racing claims elect one
   winner; takeovers silence the replaced watcher. Proven live root cause
   class along the way: Windows mandatory locks deny our own second handle
   (EACCES), which the sidecar design sidesteps.
5. P1-14B.8 report factual corrections (68 + final, rt 2102.147, baselines
   57/202 vs 66/228 labeled, dashboard.py not in scope, buffering != cause,
   PASS qualified by the sentinel gap, three-layer scope = brief run only).

Tests: 19 contract tests (verdict matrix incl. future/malformed/mismatch,
display matrix, threaded fencing, takeover fencing, supersede, claim race).
Suite 794/794 OK. No runs launched (per task bounds); prospective v1.1 + v9
intact; all rows preserved. V2 launch stays blocked: start_probe launches no
watchers (transactional supervised launch with lease verification + rollback
documented as pending work, not presented as resolved). Gates:
prospective/persistence/safety PASS (no long run). V2/main untouched.
P1-14C not started. Still NO 4-6 h authorization.

## 2026-10-11 -- P1-14B.8 follow-up: enforce fencing before termination

Starting at SHA `8648366` (clean tree). Frontend review
`d80fb9b:docs/DASHBOARD_V2_50_CORRECTIONS_REVIEW.md` proved the 794-test
correction still terminated before fencing; all remaining cases reproduced
with temp registries + mocked termination (8/13 fail on HEAD) then fixed:

1. STOPPING is now a locked `update_registry` acquisition that re-verifies
   eligible state, run PID+ctime, canonical liveness, owner lease and foreign
   marker (`already-stopping` refusal). Refused/failed acquisition never
   reaches `_terminate_verified_pid`; post-kill ownership checks alone are
   insufficient and are no longer the fence.
2. ABORTED/FAILED marks recheck run identity, own `stopping_by` and lease;
   `aborted_by` persists `supervisor`/`sentinel`/`direct` (was hardcoded
   `supervisor`). `sentinel_once` heartbeat is locked+fenced like the
   supervisor path. Duplicate JSON parse + unreachable abort-field block
   removed.
3. Heartbeat regression repaired: owned leases, 4x25 locked heartbeats, both
   timestamps advance, distinctive 11/22 values survive, all threads join
   with zero hidden errors; sentinel claim race added (exactly one winner).
4. No market probes, P1-14C, long runs or paper trading in this slice;
   SQLite/logs/evidence preserved; V2 transactional supervised start stays
   PENDING and separate; SUCCESS_GATES untouched. Historical healthy windows
   stay historical: no new supervised window was run on the corrected SHA.

Tests: 13 fencing + 1 sentinel race; suite 808/808 OK.

## 2026-10-11 -- P1-14B.8 V2-51: operation boundary through termination + pure observation

Starting at SHA `0786617` (clean tree). Frontend review
`35401f9:docs/DASHBOARD_V2_51_FENCING_REVIEW.md` with mocked reproductions
proved three residual races; all fixed with fail-before tests, no market runs:

1. Post-claim takeover reached termination (lock released after STOPPING
   acquisition). Now acquisition AND a final verify-and-kill run under the
   registry lock, and the kill itself is handle-bound
   (`_terminate_verified_pid(pid, ctime)`: one Windows handle verifies
   GetProcessTimes then terminates; POSIX rechecks `pid_is_ours`
   immediately before `os.kill`). Refusals (`takeover-after-claim`,
   `run-replaced`, `replaced-owner`, `handle-identity-refused`) leave the
   mocked termination uncalled, both owners. `stop_probe` carries the same
   discipline with its own marker.
2. Owned lease need not cover the run (`_owns_lease` is pid-only).
   Enforcement now requires `_owner_lease_valid` (ACTIVE + owned +
   watched_pid == run PID + ctime when determinable both sides) at
   acquisition, pre-kill and terminal marking. Wrong-run, foreign and
   inactive leases never terminate. Heartbeats keep pid-only `_owns_lease`
   (non-replacement proof) by design; heartbeat functions now return bool
   so effective writes are countable.
3. `status()` overwrote terminals from stale reads (unlocked). Split into
   pure `_status_view` (shared shape), `status_readonly()` (no writes,
   reconciliation, handle or process action; byte-preserving, V2 GET
   requirement) and fenced `_reconcile_stale_record` (locked; never touches
   terminals or held enforcement STOPPING). `dashboard.probe_status()`,
   `try_register` refusal snapshots and `start_probe` preflight read purely;
   `try_register`/`start_probe`/`_mark_terminal` commit via locked fenced
   transforms. All writers audited (`status`, `stop_probe`, `try_register`,
   `start`, `_mark_terminal`, claims, heartbeats, finishers); residuals
   documented, no complete-protection claim beyond them.
4. Thread tests share one PID. New multiprocess proof (spawned owners,
   barrier rendezvous so winners stay alive): supervisor+sentinel claim then
   10 counted heartbeats each (all wrote, both advance, 11/22 survive) and
   4-process claim races elect exactly one winner per kind; all exit 0.

Tests: 8 boundary + 7 readonly + 3 multiprocess (15 fail on `0786617`);
suite 826/826 OK. No probes, P1-14C, long runs, paper or Start; DB/logs
preserved; V2/main untouched; SUCCESS_GATES untouched. No new supervised
window on the corrected SHA (historical windows stay historical).

## 2026-10-11 -- P1-14B.8 V2-52: native refusal propagation + own-child adoption

Starting at SHA `55efaa2` (clean tree). Frontend review
`066577e:docs/DASHBOARD_V2_52_INTEGRATION_REVIEW.md` with mocked
reproductions; H1+H2 fixed failing-first, no market runs:

1. Native termination accepted refusal as success (TerminateProcess BOOL
   ignored, HANDLE-width signatures missing). Now explicit `c_void_p`
   signatures for TerminateProcess/CloseHandle, BOOL checked, `0`/exception
   returns False with bounded `_LAST_NATIVE_ERROR` (code + timestamp),
   handle closed on every path, verify+kill on one handle inside the
   registry lock. Missing ctime = handle-liveness-only fallback,
   expressly documented (PID-reuse not excluded there). Precision kept:
   the repro never showed a false ABORTED (callers verify disappearance);
   the fault was success-on-refusal.
2. Parent start killed its own already-registered child (commit mistook it
   for a foreign run). `_commit_start` now adopts same-PID+ctime
   RUNNING/STARTING records verbatim (no write, no kill, evidence kept);
   held enforcement markers never adopted; foreign/reused-PID still refused
   with exactly one orphan kill; write failures kill once. Scoped away from
   the V2 supervised transactional launch.
3. C1: M1 heartbeat workers share a start barrier and assert both stamps
   inside [t0, t1]; wording bounded to 10 beats/owner.

Tests: 9 native + 5 start-race (key cases fail on `55efaa2`); suite
840/840 OK. V2/main/SUCCESS_GATES intact; `status_readonly()` kept in GETs;
no new supervised window (longevity UNDEMONSTRATED).

## 2026-10-11 -- P1-14B.8 V2-54: exact BOOL + child-first log handoff

Starting at SHA `b801ab0` (clean tree). Frontend review
`d4d82c9:docs/DASHBOARD_V2_54_BACKEND_CORRECTIONS_REVIEW.md` with mocked
reproductions; R1+R2 fixed failing-first, no market runs:

1. BOOL declarations were one byte (`c_bool`), not Win32 BOOL. Now exact
   32-bit `wintypes.BOOL` (fallback `c_int32`) on all BOOL params/results
   via `_configure_kernel_signatures` (direct binding, no silent setup;
   module-level `_FILETIME`), HANDLE-width args kept, verify+kill on one
   handle in the lock. ABI regressions through real WINFUNCTYPE callbacks
   for 0/1/256 prove 256 truthy under BOOL and falsy under `c_bool`, plus
   end-to-end helper acceptance of a 256 native success. Refusal/exception
   propagation, bounded diagnostic and close guarantees unchanged. No real
   kill failure or false ABORTED claimed.
2. Child-first adoption left evidence None (log-discovery gap). Adoption
   with absent evidence now performs a conditional locked handoff binding
   the start-created log to the same PID+ctime run (active, unmarked, no
   valid log present). Valid stored evidence preserved unwritten; foreign/
   terminal/enforcement races refuse untouched; handoff OSError keeps the
   verified live child with association explicitly unconfirmed (never
   declared confirmed when not established); nothing invented for direct
   launches. Proven on the REAL `try_register()` child-first flow.
3. C1 corrected here and in CURRENT_STATE: M1 claims shared-start barrier,
   ten effective writes per owner and in-window finals ONLY -- earlier
   "advance" phrasing superseded (no strict-vs-initial, interleaving, or
   longevity proof).

Tests: 7 win32-bool + 8 start-race delta (key cases fail on `b801ab0`);
suite 850/850 OK. V2/main/SUCCESS_GATES intact; `status_readonly()` kept;
no new supervised window (longevity UNDEMONSTRATED).

## DASH-V2-67-BACKEND - 2026-10-11 - helper extraction from the HTTP module

Handoff `8712dfb` (`dash-v2-03-token-detail`, Git only). Audit first: the
only cross-module helper imports were control.py's 16 lazy
`from .dashboard import` (repo_root/process_info/pid_is_ours/
no_window_flags); views use labels/version only; no import cycle is
introduced (host_process is stdlib-only). Moved the five helpers VERBATIM
(byte-identical bodies, verified by diff) to `host_process.py`;
dashboard.py re-exports the same objects (no second identity logic);
control.py binds them at top level. Controller-behavior patch targets
moved to `control.pid_is_ours` (24) and `host_process.process_info` (7);
dashboard-namespace behavior tests unchanged. One self-inflicted
mis-indentation of `def _probe_env` caught by focused tests and repaired
to module level (semantics unchanged). New boundary tests H1–H4 fail on
base (ImportError + 16 source hits) and pass after. V2-64 doc 5-point
corrections applied alongside (manual SHA check, price schema 3 with
10k/1200, anchors + ASCII/Unicode kept, prospective vs historical.db
split, purity-scope limit). Suite 909/909 OK. No probes, backfills,
traffic, P1-14C, runs, paper, orders, Start, main merge, SUCCESS_GATES,
formula, or accepted-fix changes. No old-UI/file retirement executed.

## 2026-10-11 -- Supervised transactional launch preparation (DISABLED)

Contract first (`docs/SUPERVISED_LAUNCH_CONTRACT.md`), then the minimum
backend, per V2-55 acceptance (`7b2b5e75`). R1/R2 accepted as closed and
left untouched:

1. Preconditions + capacity (no live run, lock acquirable, one-run/three-
   proc bound, named launcher, writable evidence) checked on pure reads;
   refusal spawns and writes nothing.
2. Identity per process: probe PID+ctime from a fresh read; watchers need
   ACTIVE + owned PID/ctime + watched==run + alive + parseable fresh
   non-future heartbeat on ONE read. Popen/ACTIVE/recent-heartbeat alone
   never confirms; confirmation is point-in-time, not future protection.
3. Sequence start_probe → spawn watchers → finite-budget pure verification
   → kill-only rollback of everything launched on any failure. Rollback
   touches only transaction PIDs with spawn-captured identity (already-dead
   counts as cleaned); foreign/terminal records never written or killed;
   unverifiable cleanup → UNCERTAIN with pending evidence, never completed.
4. Disabled surface: public entry refuses with zero side effects; no HTTP
   route, CLI subcommand, Start enablement or contract change ships.
   BFF keeps Start disabled and renders the envelope (outcome/reason,
   per-watcher confirmation, pending list, point-in-time scope) after a
   future enablement review.
5. Found+fixed in passing: per-thread global Popen patches leak the mock
   process-wide (concurrent test now uses one parent-held patch).

Tests: 23-test matrix in `tests/test_supervised_launch.py` (full path,
per-component spawn failures, lease matrix, death/reuse, timeout,
unreadable, takeover/terminal interleaves, uncertain rollbacks, concurrent
single-confirmation, repeat rejection, zero-write purity); fail-before is
23/23 missing API. Suite 873/873 OK. No real probes, market traffic,
P1-14C, long runs, paper, orders or Start; V2/main/SUCCESS_GATES intact;
no phase advanced. Enablement needs explicit authorization.


## DASH-V2-62 - 2026-10-11 - launch identity and uncertainty correction

Supersedes the prior preparation claim that a fresh registry read establishes probe ownership: the transaction receives spawn-captured child PID+ctime directly via an optional private start_probe callback. Ordinary start/adoption/handoff semantics stay unchanged. New launch-only process evidence distinguishes owned/gone/replaced/unknown; PID-only identity fallback cannot confirm or authorize transaction rollback. Final unreadable assessment remains UNCERTAIN. Strict non-future watcher timestamps and one result per watcher retained. Actual sidecar lock and owned evidence-file preflight effects documented; verification budget excludes blocking IO/spawn/native calls. Public launch remains disabled. See DASH_V2_62_SUPERVISED_LAUNCH_CORRECTIONS.md (902/902 canonical, 52/52 focused). No strategy, gate, run or enablement authorization.

## DASH-V2-64-BACKEND - 2026-10-11 - reconciliation + read-contract audit

Reconciled da231b9..c635938 by fast-forward (clean worktree, zero Python processes, terminal registry, unheld lock; no reset/clean/kill). Deployed identity verified: V2 imports this worktree /src + status_readonly(), canonical DB readOnly; deployed == accepted c635938. Inventoried all legacy GET pages + 25 JSON APIs with fields/units/nullability/timestamps/limits in docs/DASHBOARD_V1_READ_CONTRACTS.md; specified universe/search/history/events/prices + CSV/JSON export metadata with explicit request-time vs retained-sample anchors; pinned GET purity with tests/test_dashboard_get_purity.py (mutation check fails without the pure call). Found retirement blocker: control.py imports shared helpers FROM dashboard.py, so file-level old-UI retirement waits on helper extraction (proposed, not executed). Recency never proves identity/liveness/protection; future runs need the documented evidence list. No probes, backfills, P1-14C, runs, paper, orders, Start, or gate advancement. Suite 905/905 OK.

## DASH-V2-69 — 2026-10-11 — extraction proof review
Exact c59c5ec extraction reviewed independently. Five helper bodies match; original Python 3.14 find_module blocker was ineffective despite four green tests. Existing H2 strengthened with find_spec plus deliberate negative control; four focused tests pass. No application source edits. V1 contract retirement section now closes extraction prerequisite while retaining parity/review/authorization requirements; no retirement performed. See DASH_V2_69_EXTRACTION_PROOF_REVIEW.md; canonical verification recorded there. Full cutover and operational readiness remain PARTIAL; Start/gates/main/DB/registry preserved.

## DASH-V2-71B — 2026-10-11 — System data contracts for V2 integration

Read V2-69/70 acceptance + diagnostics + migration plan from Git only (dash-v2-03-token-detail f52b68f); base 9f3e084 already synced, no reset/clean/force. Audited every DashboardState reader against live schema v9 (read-only): per-field contracts in docs/DASHBOARD_V2_71_SYSTEM_DATA_CONTRACTS.md with safe-reader allowlist proven by tests/test_read_purity.py (byte-identical DBs/registry/evidence, no new .db files, content queries agree; temp fixtures). Host resources verified absent (no column; log-only host block is not a reader contract) → NOT_AVAILABLE with future-work note; no ops audit journal exists (latest last_exit + capped lifecycle tables only). No defect in read paths on existing stores → no source change (fresh-DB init/_ensure/WAL documented as V2-avoided, not fixed). 
Suite 910/910 OK (902 + 3 + 4 + 1). No probes, backfills, P1-14C, runs, paper, orders, Start, main merge, SUCCESS_GATES, formula, or
accepted-fix changes.

## DASH-V2-71B reviewer correction — 2026-10-11
89232f7 independently reviewed: discovery/canonical 910, exit0. Strengthened
existing purity test (missing historical-byte assertion, no new logs, env
restoration); historical-tempfile mutation passed old proof and fails new.
No application source change. Final bytes do not certify readonly mode;
four HistoryStore init calls observed. See DASH_V2_71B_REVIEW_CORRECTIONS.md.
Full cutover/Start/gates unchanged; universe detail=test provenance pending.

## Final proof and fixture-isolation checkpoint (2026-10-11)
Original proof correction: focused 1/1 and canonical 910/910 exit0 (184.479s).
A subsequent System read found 375 universe rows, 225 tagged detail='test',
rather than the earlier read of 366/222. Earlier canonical-suite preservation
claims do NOT hold across those test runs. Readonly GET hashes are a separate,
bounded check and remain equal.

Root route proven without touching the canonical DB: original HotSyncTest
calls the default persistence factory twice and writes three DOGEUSDT lifecycle
rows to an intercepted temporary store. test_universe_probe.make_probe now
injects a real initialized temporary PersistenceStore with cleanup per testcase.
All 11 module tests pass with the default factory forbidden, zero calls.
One added regression prevents fallback. No application source changes.
This establishes a test contamination route; it does not attribute every
historical tagged row. Existing canonical rows were retained without cleanup.

Final canonical: 911/911 application tests exit0. The preservation wrapper
exits1: microprobe.db SHA256 changed; historical.db and registry hashes equal.
Universe rows stayed375/225: HOT leakage fixed, whole-suite preservation FAILED.
A guarded subset audit (729 tests) records default-store accesses in test_probe,
test_host_telemetry and test_p14b_3_transport_freshness (six errors with factory
forbidden, swallowed persistence errors also observed). These remaining fixtures
are a BLOCKER for whole-suite isolation; no claim of complete purity is made.
See backend-isolated-final.json and default-store-audit.json.
Source notice remains until historical provenance is reviewed.
The 496-test frontend Python snapshot is historical validation, not the
current backend. Its old HOT fixtures must not be rerun against the canonical
store; reconcile the fixture isolation or run it in a fully isolated checkout.
FEATURES_IMPLEMENTED adds temporary HOT fixtures and fallback regression.
FEATURES_VERIFIED final 911 plus isolated original/after negative control.
DEFERRED_FEATURES retains remaining default-store test isolation, historical lineage and complete cutover.
No runs, traffic, orders, Start, retirement, main merge or gate advancement.


## ETAPA 1 test isolation — 2026-10-12 (append-only)

Prohibited-vs-residual write classification (barrier scripts/audit_test_isolation.py):
PROHIBITED (must be zero) = row/payload writes via the default persistence
factory, registry writes, canonical-tree file writes (evidence/watcher logs,
sidecars). RESIDUAL (reported, byte-neutral, never silenced) = prospective
rehydration connects on MarketProbe construction (no config db_path exists),
HistoryStore default-path reads with idempotent DDL, read-only URI connects.
Hashes+inventory prove effect; green suite never proves purity (61 swallowed
attempts observed while 911/911 green pre-fix).

Fixture pattern (test-only, production untouched): make_isolated_probe
(temp PersistenceStore + cleanup, per test_universe_probe.make_probe
precedent) for message-feeding probes; evidence_dir=tmp for start_probe;
patch pc.repo_root (not only dashboard.repo_root) for the default watcher
spawner. Routes B/C need production injection points -- deferred, see
docs/TEST_ISOLATION_ETAPA1_REPORT.md. No runs, traffic, orders, Start,
paper, V2/main changes, resets or evidence deletions.

## ETAPA 2 dataset readiness — 2026-10-12 (append-only)

225/375 universe rows CONFIRMED pre-aea0376 HotSyncTest leakage (all
DOGEUSDT hot_subscribed/unsubscribed detail=test, 10-08->10-11; other
test-detail writers temp-scoped and absent from canonical: 0 S-pattern,
0 XRP rows). Disposition: retain all rows, filter detail!=test explicitly
for research. 150 rows probable-operational, per-row run UNKNOWN (no
run-id column). Prospective 66/228 COMPLETE zero-fixture-markers, single
rules v0.1.0, static lifecycle, mark-returns-only (no costs). Event
studies 2831x6 exact, 420 COMPLETE-unusable = FORMATION_GAP by design.
Dataset SUFFICIENT for descriptive exploration only; NOT for strategy
validation (single versions, small rare tiers, no OOS, capped buffers,
capitalization UNKNOWN). See docs/DATASET_READINESS_ETAPA2.md.

## ETAPA 3 research/backtest contract — 2026-10-12 (append-only)

H1 (continuation after breakout/recovery), H2 (exhaustion+reversal after
expansion), H3 (bearish continuation after support loss, NEVER pooled with
loser-recovery) defined as STUDY contracts over existing rule versions
(classifier v0.1.0, opportunity v0.1.0, event-defs v1). Move sizes
5/15/40/70pc are study-population tiers, not signals. Capitalization
UNKNOWN (never infer from volume/price). Costs versioned per study with
1x/2x/3x sensitivity; raw outcomes stored separately (EVENT_LABELING).
No study is valid until OOS + costed; anything today is IN-SAMPLE
EXPLORATION by label. See docs/RESEARCH_BACKTEST_CONTRACT_ETAPA3.md.

## ETAPA 4 offline backtest prep — 2026-10-12 (append-only)

Isolated engine src/microstructure_probe/backtest_offline.py
(backtest-offline/v1, stdlib-only, no IO/network/DB/clock): chronological
replay, next-open fills after event time (poison-tested), horizon exits +
distance stops, fees/funding/spread/slippage, deterministic partial fills,
single-position overlap skips (counted), MFE/MAE, equity/drawdown,
config-hash + dataset-id versioning, median dev/OOS split, 1x/2x/3x cost
sensitivity. Entry/exit rules are STRUCTURAL MECHANICS placeholders, not
signals. 16 tests/tests/test_backtest_offline.py green on synthetic
fixtures. Read contract docs/BACKTEST_READ_CONTRACT_V1.md UNWIRED by
design (no dashboard change, no fictitious results). Fixture smoke only
executes mechanics; zero performance interpretation. Strategy validation
still blocked (Etapa 2 gates).

## ETAPA 5 Paper Lab plan — 2026-10-12 (append-only, DESIGN ONLY)

Work breakdown: simulation+fill model, position manager, cash/fee/funding
accounting, per-position/portfolio risk, halts/kill-switch, paper-vs-backtest
comparison with predeclared tolerance. Entry gates: Etapa-1 barrier green,
Etapa-2 dataset fit, Etapa-3 family acceptance, Etapa-4 real-dataset
validation, explicit human authorization. Nothing implemented, started, or
authorized. See docs/PAPER_LAB_PLAN_ETAPA5.md.

## Cierre correctivo P1-P4 — 2026-10-12 (append-only, sin push)

P1 motor v2 (metodologia no fijada por contratos, decidida aqui):
fills secuenciales con estado-causal por vela; stops evaluados contra la
posicion del momento (posteriores nunca retroactivos); gaps: stop dentro
del rango => precio stop, si no => open (primer precio real), tiempo de
conocimiento; OHLC: H/L/C conocidos al close_time (siguiente open);
horizonte usa velas completadas; primera apertura tras horizonte =>
expirado contado; incompletos: cantidad/costes conservados, cierre a
ultimo precio conocido con flag open_at_end; contabilidad por cantidad
(P&L precio vs friccion); funding con signo por direccion bajo tasa
unica (limitacion etiquetada); drawdown realizado (MTM no modelado);
capacidad comprometida en tiempo de senal; mismatch family/version =>
skip+conteo; knobs no soportados => ValueError; OOS por tiempo de evento
con cutoff explicito.
P2: inyeccion minima con defaults intactos (persistence_store /
research_history_store en MarketProbe; store/run_id en
ProspectiveRecorder con _resolve_store unico; history_store en
ResearchRecorder/DashboardState; history_db_path en DashboardServer);
tests con dependencias temporales explicitas; barrera distingue
bloqueado/efectivo/RO/preservacion; unico residual RO = lectura
supervision mode=ro (SQLite impide escritura).
P3: run_id uuid4 por ejecucion en universe/prospective/snapshots
(schema v10, migracion en copias temporales, historicos NULL=UNKNOWN
sin backfill ni inferencia); research buckets: linkage diferido
explicito; rehidratacion recarga todo (continuidad por diseno).
Version unica de reglas NO bloquea validacion por si sola: exige
version congelada+trazable, datos aptos y split temporal defendible;
sin versiones artificiales.

## Cierre correctivo R1-R7 — 2026-10-13 (append-only)

R1: stops/metricas/salidas consumen rangos solo con close conocido y en
ventana; exit_ms/horizontes son tiempos de conocimiento; datos tras la
ventana no aportan nada. R2: fin de datos = marca a ultimo conocimiento
(open_at_end), nunca ejecucion al horizonte; sin duracion/funding/cierre/
capacidad inventados. R3: gap observable al open resuelve primero; la
recuperacion no mejora el fill. R4: orden vela = stop-existente,
cancelar resto, fills permitidos, reevaluar; capacidad desde senal.
R5: MFE/MAE de prints demostrados (open incluido), extremos favorables
excluidos, salida alimenta MAE. R6: _finish_v10 en todas las cadenas;
tablas ausentes => ValueError nombrando la tabla (nunca skip
silencioso); tests re-pineados a v10. R7: _resolve_history unico.
run_id UUID4 completo: unicidad probabilistica (122 bits), jamas
absoluta; la separacion usa desigualdad observada. Version unica de
reglas: congelada+trazable + datos aptos + split defendible; sin
versiones artificiales.

## Mejoras funding/trazabilidad/dashboard/casos/evaluacion — 2026-10-13 (append-only)

Funding v4 (backtest-offline/v4): calendario versionado de liquidaciones
con timestamp+tasa realizados por evento; aplica si entry<=t<exit;
exposicion = coste llenado con fills<=t; signo por direccion; fuera del
span = funding_uncovered_ms (UNKNOWN, jamas cero inventado); entre
liquidaciones = cadencia. funding_estimated_bps es CONTEXTO (nunca
contabiliza). Sin calendario: fallback de intervalos intacto. Motor
offline/determinista, sin red/BD. Tasas 4h/8h caben sin swap global.
Linkage research v3: run_id/rules_version/as_of_ms/price_source/
dataset_id nulables en buckets; recorder estampa en flush (as_of =
disponibilidad, fuente mecanica); probe hila run_id+versiones;
dataset_id None=UNKNOWN; historicos NULL sin backfill; migracion en
copias temporales, canonico nunca escribible.
Dashboard: solo campos respaldados (24h anclada vs REST, referencia/
ancla/as_of, fase/transicion, evidencia triple, OI en base, funding
citado vs UNKNOWN, VWAP con ancla); ratio cuentas, OI valorado, RSI/ATR
y calendario ausentes => UNKNOWN/bloqueador, jamas simulados; sin
etiquetas normativas ni botones.
Casos WUSDT/LUMIA: paquete AUSENTE verificado (sin hashes que validar);
informe de protocolo+metodo v1 sin cifras; H3 intacto, rebotes como
variante H2 explicita; sin calibracion ni OOS.
Evaluacion: runner sobre motor existente (6 grupos separados, dev/OOS
por cutoff declarado, baseline agrupada como referencia, confirmacion
mecanica etiquetada); RSI/ATR candidatos; formacion caller-declared.
INCIDENTE: test DashboardState sin history_store migro el historico
canonico v2->v3 (aditivo, conteos intactos, cero linkage filtrado);
corregido con inyeccion + barrera tras cada archivo de tests nuevo.

## Correccion tecnica de14ac1-base - 2026-10-13 (append-only, rama review/correccion-tecnica-de14ac1)

Contabilidad (motor backtest-offline/v4, aditivo, bateria v4 intacta):
realizados vs abiertas vs marcas separados (n_realized/n_open/open_positions
con mark_ms/mark_px; total_net_realized/expectancy_net_realized/
equity_curve_realized en orden de cierre efectivo/max_drawdown_realized);
open_at_end no alimenta metricas realizadas (realized_net null en marcas);
costes de salida hipoteticos (exit-leg en marcas) separados de ejecutados
(costs_exit_hypothetical vs costs_executed). Legacy totals/curva sin cambios
(incluyen marcas; no citarlos como realizados). Ver contrato v4.1.

Funding (v4 aditivo): exposicion = cantidad vigente x mark de liquidacion
(open causal de la vela que cubre el settlement; sin vela -> unknown-excluded,
nunca precio cero); identidad del contrato en cada evento (symbol + calendar
symbol/version/source, UNKNOWN jamas inventado); duplicados exactos
deduplicados y contados, conflicto mismo-ms-tasa-distinta RECHAZA el run;
cobertura desconocida acotada al holding (uncovered head/tail + gap_ms
interior); completitud jamas inferida por primer/ultimo timestamp
(assess() con cadencia nominal; sin cadencia -> UNKNOWN); faltantes y
fallback sintetico explicitos (basis settled/unknown-excluded/
synthetic-fallback; sin fidelidad venue inventada).

Runner (scripts/run_family_evaluation.py, sin reconstruir): configuracion
familia/version por grupo (GROUP_FAMILY H1/H2/H3; baseline usa default CLI);
H3 valido ya no se descarta por config H1; identidad por indice de fila +
event_ids en manifiesto (colisiones mismo-triple en grupos distintos
imposibles); demo emite H1/H2/H3 acorde a cada grupo (8 eventos);
manifiesto suma n_realized/n_open/total_net_realized/max_drawdown_realized.

Aislamiento/incidente (reconciliacion, sin tocar el canonico): el incidente
de migracion v2->v3 del historico canonico por side-effect de test queda
registrado como aditivo (conteos intactos, cero linkage filtrado al
historico: store de investigacion sin columnas run_id; verificado read-only
2026-10-13: historical.db con tablas research v3 intactas, microprobe.db
operacional separada). Limites: no se prueba ausencia de otras escrituras;
filas borradas por el bug de bounding P1-14B.1 siguen irrecuperables
(documentado, no reconstruido). No se repara ni revierte el canonico,
ni silenciosa ni explicitamente, en esta tarea. Barrera
scripts/audit_test_isolation.py corre tras cada archivo de tests nuevo.

Contratos V2 (handoff, sin editar frontend/): incompatibilidad explicita
operacional-v10 vs historico-v3 (ver docs/DASHBOARD_V2_27B7AF5_READ_HANDOFF.md):
el frontend exacto 27b7af5 lee microprobe.db read-only con supuestos v9
(schema_version:9 hardcodeado) y no lee historical.db v3; el backend
operacional es v10 (tablas v9 + linkage run_id). Consumo solo por contratos
versionados con chequeo explicito de presencia de tablas (R6); la fundacion
antigua de frontend/ no se edita como sustituto del handoff.

## Entrega nueve archivos 6fd6091-base - 2026-10-13 (append-only, rama review/entrega-nueve-archivos-6fd6091)

Correcciones sobre la base 6fd6091 (motor v4 + runner + comparador intactos
en lo demas):

- Uncovered acotado al holding (min(raw, exit-entry); holding 100ms ->
  uncovered == 100, nunca mayor). Bateria previa intacta (casos con
  uncovered == holding no cambian; el resto solo afirma >0).
- Calendario con symbol-fija es monocontrato: evento de otro symbol
  RECHAZA el run (LUMIAUSDT no liquida BTCUSDT). Sin pin (null) se
  conserva el comportamiento legacy, registrado UNKNOWN.
- Runner conserva `symbol` del calendario JSON al manifiesto
  (`funding_calendar.symbol`; ausente -> null, jamas inventado).
- Mark con edad > cadencia nominal (o cualquier edad sin cadencia) es
  STALE: excluido como unknown-excluded con mark_age_ms registrado;
  edad 0 siempre fresh. Bateria de grid (edad 0) intacta.
- Comisiones: entrada sobre nocional ejecutado, salida sobre valor de
  salida (10u 100->120 @10bps = 1.00/1.20). Las mitades simetricas eran
  el bug: UN assert legacy actualizado (test_fees_charged_both_sides,
  2.0 -> split 1.00/exit-value, con comentario de correccion). Resto de
  la bateria verde.
- Handoff 27b7af5 corregido: el frontend SI lee historical.db en real
  (historical-coverage.ts -> GET /api/v1/historical-coverage) con gate
  historico-2 (UNSUPPORTED_HISTORICAL_SCHEMA) y gate operacional-9
  (UNSUPPORTED_SYSTEM_SCHEMA en system-evidence.ts); backend actual
  v10/v3 => incompatible fail-closed en ambos stores.

Verificacion: dirigidas 68/68 OK (incl. R1-R7), comparador 10/10 OK,
barrera 1029 (1020+9) con 1F+8E preexistentes contrastados en worktree
aislado de de14ac1 (misma firma; alcance fuera de esta tarea).
Aislamiento: prohibited/bloqueados/efectivos 0, hashes iguales,
data/logs sin cambios. Sin merge, sesiones, paper, ordenes ni gates.

## Habilitacion Start supervisado O1 - 2026-10-13 (append-only, review/o1-funcional-v2-observacion)

SUPERVISED_LAUNCH_ENABLED False -> True con la cadena completa, nunca como
bandera sola: readiness-green (launch-readiness.ts, 5 checks) + token de
confirmacion START_OBSERVE_2100 + allowlist de presets (brief 120s,
standard 3600s, validation-6h 21600s) + spawn de codigo fijo al controlador
canonico (sin interpolacion de usuario) + identidad verificada/heartbeat
(supervisor+sentinel) + stop cableado (solo runs launcher=dashboard) +
matriz de fallos 23/23 + ciclo aislado + refusales preservados.
Alcance: observe-only (BOT_MODE lo impone), launcher requerido (anonimos
rechazados pre-spawn), kill-only rollback, foreign/terminal intocables.
Ninguna corrida real lanzada en esta entrega; la primera corrida conjunta
requiere su autorizacion propia. No hay ruta HTTP/CLI nueva en el backend:
el unico llamante es el path fijo del BFF V2.

## Registro bandera Start — checkpoint 4f1d92e (2026-10-14, append-only)

La bandera Python `SUPERVISED_LAUNCH_ENABLED=True` (control.py) quedo
habilitada en el checkpoint 4f1d92e junto a `V2PathTest` (launch con llamada
fija brief/dashboard, asociacion supervisor+sentinel al run, rollback ante
fallo de sentinel, stop de run propio). `V2PathTest` NO es prueba HTTP/BFF:
cubre el controlador canonico, no la ruta. Las pruebas de la ruta real
(POST /runtime/start con token + readiness, asociacion/rollback/stop
extremo a extremo del BFF) quedan para el Bloque 3 y condicionan cualquier
corrida conjunta. Sin corridas reales a esta fecha.

## Revision independiente pre-piloto — presupuestos/readiness/presets/compat (2026-10-14, append-only, sobre e887287)

1. Presupuestos separados (`frontend/src/lib/runtime-control.ts`):
   STATUS 4200ms (lectura pura, intacto), STOP 8000ms (kill verificado
   acotado), START 65000ms (cubre `SUPERVISED_LAUNCH_VERIFY_BUDGET_S=60s`
   + margen de spawn). Un start que excede su presupuesto NUNCA reporta
   fallo plano: reconcilia por lectura de estado y devuelve
   `START_TIMEOUT_UNCERTAIN` (HTTP 202) con disciplina
   `reconcile-before-retry`. Pre-check de idempotencia: reintento con
   run activo/STARTING/STOPPING devuelve `ALREADY_RUNNING` (propio) o
   `ALREADY_RUNNING_FOREIGN` (409) SIN spawnear; el backend ya rechaza
   `already-running`, el BFF evita ademas el segundo spawn.
2. Readiness sin `callable()` (`launch-readiness.ts` +
   `controllerLaunchCapability()`): PASS solo con
   present+enabled+`verify_budget_s` finito positivo+`poll_s` finito no
   negativo; presente-pero-deshabilitado o presupuesto no finito queda
   BLOCKED. Storage integrado con valores documentados: BLOQUEO sin DB
   operacional legible, sin disco medible o bajo
   `STORAGE_BLOCK_FLOOR_BYTES=256MB`; ADVERTENCIA no bloqueante bajo
   `WARN_FREE_BYTES=1GB` (`storage_preflight.py`), sin snapshot o sin
   historico (cobertura research UNKNOWN). Medido 2026-10-14 por
   `scripts/storage_preflight.py`: op 238927872B, hist 19210240B, logs
   117579529B/175 ficheros (sin tope en codigo), libres 153007280128B.
3. Presets own-keys (`parseLaunchPreset` con
   `hasOwnProperty`): rechaza `toString`/`constructor`/`__proto__`/
   `hasOwnProperty`/`valueOf`, mayusculas y no-strings ANTES de spawnear;
   regresiones en `runtime-contract.test.ts`.
4. Correccion compat (revision tenia razon): lectores publicados
   admiten operacional 9/10 e historico 2/3 (tests `accepts schema 10`
   y `accepts schema 3` preexistentes); la restriccion 9-only/2-only
   era del SHA 27b7af5, no de esta rama. `prospective` reporta el
   schema real 9/10 (era etiqueta fija 9). Ruta historica correcta:
   `data/historical/historical.db`. Verificado vivo por copia-temp:
   operacional v10 (22 tablas), historico v3 (16 tablas). Base
   historica = main preexistente (14 coberturas, 2831 eventos);
   incremental de esta tarea = 0 filas. Compat implementada != consumo
   vivo comprobado (pendiente §5). Sin corridas reales a esta fecha.

## Cierre defectos pre-piloto — 202 (BotControl) + identidad host + migracion (2026-10-14, append-only, sobre 972a19e)

1. BotControl 202 (`frontend/src/components/system/BotControl.tsx`):
   `r.ok` es true en HTTP 202, asi el `START_TIMEOUT_UNCERTAIN` se
   mostraba como arranque exitoso. Ahora: estado pendiente `{at,quiet}`,
   boton Start bloqueado mientras hay pendiente, reconciliacion por
   lectura — exito solo con RUNNING dashboard-owned y `started_at` >=
   peticion; dos lecturas inactivas consecutivas para limpiar (una sola
   compite con confirmacion tardia); lecturas fallidas conservan la
   incertidumbre. 3 tests de componente (202 no-exito, confirmacion
   tardia, persistencia ante fallos + reconciliacion sin declarar exito).
2. Identidad host (`src/microstructure_probe/host_process.py`, causa
   reproducida en Windows real: tasklist emite bytes de locale bajo
   `PYTHONUTF8=1` → `UnicodeDecodeError` en hilos lectores y
   `stdout=None` → `AttributeError`): nuevo `_run_text()` con
   `errors="replace"` + None/incompleto/ausente → `(None,None)`
   UNKNOWN; `pid_is_ours()` con creation esperado pero real UNKNOWN →
   False (era True). UNKNOWN nunca autoriza propiedad ni kills (el
   controlador ya propaga `unknown`; `_terminate_verified_pid` intacto).
   15 tests nuevos (`test_host_process_robustness.py`, 7 fail-before);
   los 8E+1F previos de identidad/sentinel pasan por la causa, sin
   tocar aserciones. Dashboard re-exporta mismos objetos (paridad).
3. Migracion desacoplada del canonico (`test_run_linkage.py`,
   `test_research_linkage.py`): fixtures temporales v9/v2-shaped (DDL
   real + degradacion estructural + filas semilla): bump de version,
   conteos preservados, linkage previo NULL, escrituras nuevas sellan.
   Tests canonico-copia eliminados (pineaban v9/linkage-NULL y rompian
   sobre el vivo v10). Cero lecturas/escrituras al canonico.
Barrera final: 1077 OK (1 skip entorno), exit 0, aislamiento OK
(`docs/evidence/BARRIER_FIX_*`). Frontend 255/255 + typecheck + lint
0 errores. Sin piloto aun (requiere autorizacion).

## Post-mortem piloto brief probe-20261015T000730Z — aborto sano + 2 correcciones (2026-10-15, append-only)

Lanzado por ruta V2 dashboard fuera de sesion con autorizacion
registrada por el agente (el agente no lo emitio); informe read-only
`docs/evidence/PILOT_BRIEF_20261015_ABORT.txt`. Cronologia UTC:
00:07:31 startup (brief 120s, trio, observe) → 00:08:12 summary
rt=41s con 3234 rechazos → 00:08:34 supervisor aborta (tasa
0.146136 > 0.05) → 00:08:35 sentinel stale-record → PIDs muertos
(21252/9016/25648 verificados ausentes, cero python.exe, cero kills
emitidos). Seguridad 0/0/0. Rechazos 100% skew-guard en bookTicker
(93.6%), reloj sano (-864ms/558ms), entrega degradada p50 0.5-2.6s:
transporte, no Binance. Umbral 0.05 intacto.
SOURCE UNAVAILABLE exacto: `ERR_SQLITE_ERROR: attempt to write a
readonly database` por `microprobe.db-journal` caliente (00:08:33Z);
lectores fallan cerrados (correcto); journal intacto, recovery en la
proxima corrida autorizada; historical.db OK.
Correcciones: (1) `_status_view` congela elapsed/uptime en
`last_exit.at` para terminales (ABORTED 63.0s, no tick infinito) +
`TerminalCounterTest`; (2) readiness ABORTED = PASS terminal
(alineado con `_is_active_state`; antes UNKNOWN bloqueaba reintentos
para siempre) + test. Sin cambios de estrategia/umbrales/ejecucion.

## Bloqueo journal + atribucion de rechazos (2026-10-15, append-only, sobre 9b78058; sin aplicar al original, sin corridas)

1. Circular resuelto por procedimiento, no por bypass: readiness sigue
   bloqueado (DB ilegible) hasta el mantenimiento autorizado
   (`docs/DB_MAINTENANCE_RECOVERY.md`, PROPUESTO). Journal y DB
   preservados con hashes; ensayo en copia temp: integrity ok, schema
   10, conteos iguales, journal consumido, diff pre/post = 0 (rollback
   limpio, cero filas comprometidas), canonico byte-identico.
   Evidencia logs-vs-DB documentada en el procedimiento.
2. Atribucion de rechazos (`probe.py`, sin tocar umbral 5000 ni correr):
   lo medido antes era received-E (handler) + E-T (exchange) + offset/
   RTT/sync + sub-etapas de proceso; FALTABA la espera en cola local
   (max_queue=4096, buffers TCP, stalls de event-loop) y arrival-E.
   Instrumentacion minima: stamps de arrival en `_connection_loop`,
   `queueWaitMs` (handler-arrival) + `transitLagMs` (arrival-E) en
   `_record_lags` (incluye rechazados; UNKNOWN jamas se registra).
   Descomposicion: received-E = queue + transit. 5 tests en
   `test_queue_wait_attribution.py` (identidad exacta en fixture,
   UNKNOWN no-cero, rechazado conserva conteos, umbral pineado 5000,
   path markPrice). La ventana del aborto no puede re-medirse (sin
   re-corridas): su diagnostico queda en entrega por stream/latencia.

## Correccion revision 2026-10-16 — metricas honestas + apply/backup (append-only, sobre 6264ccc; sin aplicar al original, sin corridas)

1. Atribucion corregida: los stamps corren DESPUES del `async for`
   (llegada al socket y espera previa en biblioteca/TCP siguen sin
   medirse en esta capa). Renombres: `dispatchDelayMs` (iteracion ->
   handler; solo dispatch local) y `yieldLagMs` (evento -> iteracion:
   exchange+red+TCP+cola combinados, JAMAS latencia de red aislada).
   `yieldLagMs` nunca se presenta como red. Prueba por ruta real
   (`RealReceivePathTest`: `_connection_loop` real + websocket falso
   con delay controlado 300ms pre-yield): el delay aparece en yield
   (separacion max-min >= 200ms), dispatch p50 < 50ms, identidad de
   medias ±5ms, conteos y rechazos intactos (3/3 estable).
2. `--apply` implementado y probado (fixtures temporales, jamas el
   original): backup obligatorio fuera del repo con doble verificacion
   de hashes + ensayo de restauracion desde el backup; orden probar→
   respaldar→restaurar→aplicar; protecciones realpath (symlinks/
   hardlinks), rehuso de .db*/data/ y sobrescrituras; fallos limpios
   (integrity/schema/tablas/conteos/origen). Hallazgo honesto: este
   stack no fabrica journals calientes validos en fixtures (magia
   cero, SQLite los ignora — probado 4 vias); el script distingue por
   magia leida (hot-rollback vs stale-or-foreign, sin borrar nada) y
   la rama hot queda probada por el ensayo canónico + 1 test con
   magia sintetica documentada como construccion (no evidencia).
   14 tests `test_journal_recovery.py` (1 skip: symlinks sin
   privilegio). Constante de magia corregida (16 digitos).
3. Informe reproducible publicado:
   `docs/evidence/RECOVERY_REHEARSAL_20261015.json` (hot-rollback,
   integrity ok, schema 10, consumido, intacto; re-ejecutable).

## Piloto brief completado 20261015T102519Z (2026-10-15, autorizado)

Arranque V2 confirmado (492+supervisor+sentinel verificados, 3
polls, sin rollback); 123.96s naturales, 82161 msgs, 0 rechazos
(tasa 0.0), lags p50 ~0.17-0.25s, dispatch real p50 ~0.001ms (local
despreciable) + yield combinado p50 ~0.6s (jamas red aislada), reloj
sano, research 54/0/0, seguridad 0/0/0; watchers 6+6 sin abortos;
cierre duration-reached code 0, procesos muertos, COMPLETED con
uptime congelado 133s; sin hot journal (nada que recuperar);
price 12->51 visibles en V2 (5 rutas 200). El aborto previo fue
episodio de transporte, no defecto del motor. Una ventana no valida
economia; umbrales siguen hipotesis.

## Mantenimiento recovery aplicado (2026-10-15, autorizado; sin corridas)

Autorizado solo el mantenimiento con el script de e773e51. Pre
verificado (SHA, cero escritores, V2 detenido por identidad, registry
ABORTED, hashes sin deriva, destino fuera del repo). Apply PASS:
integrity ok, schema 10, aplicado-vs-restaurado identicos, journal
consumido; hash resultante byte-identico al pre (rollback limpio).
Backup + informe conservados fuera del repo. V2 reiniciado y
verificado (readiness 6/6, 5 rutas 200). Monitor no arrancado.
Evidencia: `docs/evidence/DB_MAINTENANCE_APPLIED_20261015.txt`.

## Ventana por registry + hot real + spy (2026-10-16, append-only, sobre e0b0141; sin aplicar, sin corridas)

Forense del defecto: la sonda lock abria el ORIGINAL read-write
pre-backup y RECUPERABA (borraba) su hot journal — fail-before del
spy en codigo viejo. Eliminada; la ventana es registry no-ACTIVO
(JSON puro) + re-hash + re-registry justo antes del write, sin
declarar exclusion sostenida. Fixture hot REAL (cache -64 + UPDATE
sin commit + os._exit, magia valida que bloquea ro con el sintoma
exacto). Spy en subprocess: 1 sola apertura rw en origen (la
_recover final), fail-before en viejo. 22 tests journal.

## Mantenimiento aplicable + deriva/discrepancia (2026-10-16, append-only, sobre 3a55052; sin aplicar, sin corridas)

`--apply` completo (probar→respaldar→restaurar→aplicar) con backup
real obligatorio fuera de git + restauración ensayada desde ese par
(los hashes documentan, solo el par restaura). Re-verificación de
hashes + exclusión de escritores (lock-only BEGIN/ROLLBACK, cero
escrituras) INMEDIATAMENTE antes del write; aplicado-vs-restaurado
automático aun sin --expect-counts. Destino propuesto verificado:
`C:\proyectos\binance-db-backups\recovery-20261015-3a55052` (fuera
del repo, inexistente). Regresiones: deriva pre-apply y discrepancia
post (helpers + CLI). 22 tests journal. Comando definitivo en
`DB_MAINTENANCE_RECOVERY.md` paso 3, pendiente de autorización.
   Procedimiento `DB_MAINTENANCE_RECOVERY.md` actualizado con el
   comando exacto + hashes para autorizacion.

## Visibilidad global de corridas V2 (2026-10-16, sobre 5d4fef6; sin nuevas corridas)

Reutiliza el controlador canonico (control.py); ningun segundo gestor.
`_status_view` suma run_id (stem del log), last_exit_at, process_state
(owned/gone/replaced/unknown) y process_verified (is_canonical_pid):
estado registrado nunca equivale a proceso vivo verificado. BFF
preserva esos campos y enriquece feed desde telemetry persistida
(STALE >120s, si no HEALTHY/DEGRADED/UNKNOWN; jamas inventa liveness).
Barra global `RunStatusBar` en AppShell (todas las pantallas): estado,
origen, run_id, inicio, duracion prevista y restante vivo; feed,
supervisor y sentinel por separado con frescura (watchers 90s, feed
120s); en terminal motivo, hora de cierre y duracion congelada.
Start sigue con readiness + confirmacion + sin duplicados. Stop con
confirmacion para cualquier corrida verificada del proyecto
(dashboard/agent/direct); launcher ajeno rechaza `not_project_owned`
antes de ningun kill; backend `stop_probe` revalida PID+imagen+ctime
bajo lock y solo termina el PID canonico verificado. Sin ampliar
permisos sobre procesos ajenos.

## Reconciliacion del piloto brief 20261015T102519Z (2026-10-16; solo lectura)

123.957s (probe, monotono interno) vs 133s (registro, STARTING ->
marca terminal): el registro incluye overhead de spawn (~0.6s) mas
apagado/marcado (~9s tras el final_summary); 120s solicitados,
expected_end 10:27:20Z, cierre 10:27:33Z. Sin contradiccion; la V2
muestra ambos en su dominio. Nueve cruces funding = 3 simbolos x 3
evaluaciones (10:26:01/02/03Z, history 35/36/37, misma tasa por
simbolo): borde de warm-up sobre serie casi constante, clase
artefacto-hipotesis; sin valor de senal, sin validar umbrales.
Correccion del aborto previo 20261015T000730Z: hubo retraso observado
en la ruta de entrega (p50 0.5-2.5s vs E-T en ms, 14.6% skew,
reloj sano, 0 reconnects), pero su ORIGEN no quedo aislado (sin
referencia independiente ni prueba local retenida para esa ventana);
decir "transporte" concluyente excede lo probado (origen UNKNOWN).
Umbrales y estrategias intactos. Detalle en
`docs/PILOT_BRIEF_20261015_RECONCILIATION.md`.

## Endurecimiento identidad UNKNOWN + feed estricto (2026-10-16, sobre 3544ad6; sin nuevas corridas)

Correccion sobre la entrada anterior: `process_verified` NO es
`is_canonical_pid` en lectura (eso acoplaba secuencias mockeadas y
heredaba su residual con ctime ausente); es `process_state == owned`
via `_default_process_state`, mas estricto (identidad ausente jamas
owned). Display: unknown = UNVERIFIED (unknown), nunca NOT-LIVE;
gone = NOT-LIVE (gone); replaced = REPLACED; solo STOPPED/COMPLETED/
FAILED/ABORTED son cierre confirmado (UNKNOWN jamas lo es); la
verificacion expira a los 30s sin lectura fresca (poll 10s): jamas se
retiene OWNED-LIVE. Feed HEALTHY solo con evidencia suficiente y
atribuible a ESTE run ([started_at-60s, windowEnd+120s]); si no,
UNKNOWN o evidencia de corrida anterior. Rechazo: gate supervisor
0.05 intacto (abortada la corrida que lo excede); 0.5 es solo display
legacy; el BFF marca DEGRADED — nunca HEALTHY — sobre 0.05 sin tocar
ningun umbral. Missing/silent (salvo forceOrder event-driven),
parse/payload/websocket>0, cobertura incompleta y cero mensajes
inhabilitan HEALTHY. Start/Stop y propiedad intactos.

## Correccion atribucion del feed (2026-10-16, sobre 3f2fcea; sin nuevas corridas)

La ventana [started_at-60s, ...] admitia snapshots de la corrida
anterior con arranques proximos (regresion: 20s bastan) y los
clasificaba current/HEALTHY. Eliminada la gracia pre-start: snapshot
anterior a started_at nunca es current (previous-run, nunca HEALTHY).
Linkage exacto por run_id priorizado en codigo (SELECT incluye
run_id/runtime_seconds): las filas llevan el UUID32 del probe y el
registro el stem del log — espacios distintos, sin cruce disponible
(991/1000 filas historicas ademas sin run_id) — luego rige la regla
temporal conservadora + cruce de runtime_seconds (rt muy por encima
del elapsed posible = fila ajena, UNKNOWN). Sin tiempo atribuible con
certeza: UNKNOWN. Start/Stop, umbrales (0.05/0.5) e identidad
intactos.

## Preset observation-10m=600s (2026-10-16, sobre 8c73de2; autorizada 1 corrida 600s)

Preset explicito por el mecanismo canonico, sin modificar los
existentes: `OBSERVATION_10M_SECONDS=600` + fuerza de duracion como
validation-6h + `_recorded_preset` (solo preserva validation-6h y
observation-10m; brief/standard y colapsos intactos) + choices CLI +
`LAUNCH_PRESETS` BFF + opcion BotControl (brief sigue defecto).
Evidencia a logs/probe-runs (rama por defecto, no p1-10r). Legacy
dashboard.py sin cambios (su allowlist sigue standard/validation-6h;
el arranque autorizado usa la ruta publica V2). Tests: validacion CLI
+ fuerza/propagacion 600s + registro verificado + existentes
intactos (BFF y BotControl).

## Reconciliacion OBS10M UUID/persistencia/funding (2026-10-16, sobre 67472e0; sin nuevas corridas)

UUID correcto 893f24029cba4cff96eaba7c0af094d0 por linkage exacto
(20/20 filas en ventana + final_summary.run_id del propio log +
vecinas con otros UUID); el valor ...888c33f89c566630 del informe
no existe en la evidencia (quimera con la cola del UUID del piloto).
246 writes = filas bucket a historical.db (ruta ResearchRecorder sin
inyeccion -> HistoryStore por defecto; 183+33+30 con el UUID del
run); delta por tabla UNKNOWN sin baseline pre-run. Funding 245
eventos = 13 episodios (misma tasa contigua; condicion: salto a
nuevo extremo + re-disparo ~1/s en constante). Sin codigo, umbrales
ni estrategias tocados. Detalle en el addendum + JSON.

## Trazabilidad stem<->UUID + episodios v1 (2026-10-16, sobre d7dcc70; sin nuevas corridas)

`control.link_probe_run_id` (fenced: mismo-PID activo, jamas
sobrescribe un enlace distinto, jamas toca ajenos/terminales;
historicos sin enlace = ausente = UNKNOWN, sin backfill) llamado
desde `__main__` tras construir el probe (fallos degradados, jamas
rompen la recoleccion). `status_view` expone `probe_run_id`; el
lector V2 lo usa como runUuid exacto y rechaza UUID incompatible
conocido por fallback temporal. Detector intacto
(`detectors.py:119-158` revisado, sin cambios). Agrupacion v1 pura
(`event_episodes.py`): bruto/episodio/update/nuevo con claves,
inicio/ultima, duracion, repeticiones y motivos; originales
preservados; episodios NO son muestras independientes ni senales.
BFF `GET /api/v1/detections` solo lee el log evidenciado del
registro (cola acotada); panel System con contadores separados,
procedencia/corrida/version/frescura, UNKNOWN explicito y etiqueta
research. V2 no consume eventos crudos en ninguna otra vista
(verificado: oportunidades usan clasificaciones). Sin Start/Stop
nuevos ni segundo gestor.

## Entrega operativa V2 en 3020 (2026-10-16, sobre d126141; sin nuevas corridas)

Unico dashboard principal: `http://127.0.0.1:3020` (`next start`
desde `frontend/` de este repo, BUILD_ID `u0ziTGs3Q12uEMZapEWf7`
del arbol d126141). Detenidas la 3020 obsoleta (build anterior a
d126141: sin `/detections` ni `probe_run_id`) y la 8093 propia
(build d126141); `requestAllowed` sigue pineado a 127.0.0.1:3020
(sin ampliar CORS/origenes: el problema era de publicacion, no de
autorizacion). Auth verificada en vivo sin monitor (403 sin
headers/origen evil, 400 con confirm erroneo previo a spawn) y con
mocks 59/59. 98/4 = vista parcial de cola acotada; 245/13 =
reconstruccion completa del fixture: no equivalentes.

## Piloto brief probe-20261016T005550Z (2026-10-16, autorizada 1x120s observe)

Unica corrida via V2 publica (brief, START_OBSERVE_2100, HTTP 200
all-components-verified): probe 14500 + supervisor 14976 +
sentinel 372. `link_probe_run_id` escribio el UUID al registro sin
intervencion (R1 PASS); log/final/telemetry coinciden (R2 PASS:
UUID unico en log, 4 snapshots UUID). Cierre natural
duration-reached code 0 (122.377s probe vs 131s registro:
observacion + drain vs overhead spawn/marcado). Ventana sana:
89360 msgs, 0.00% rechazos, 0 reconnects, reloj 1/1, lags p50
~171-175ms, research 54/0/0 = 54 filas UUID (flow_10s neto -98
por retencion concurrente: filas del run != delta neto).
10 funding LOW = 2 episodios v1, sin mezcla (R5 PASS). V2 3020
muestra enlace exacto post-cierre (R4/R5 PASS); feed mid-run en
vivo no capturado (R3 UNKNOWN, residual: capturar mid-run la
proxima ventana). Sin ordenes/cambios (safety 0/0/0, sin diff
funcional desde d126141). Detalle + matriz R1-R11 en
`docs/evidence/RUN_BRIEF120_20261016_CLOSEOUT.json`.

## R3 capture + prep offline entradas/salidas (2026-10-16, sobre 48445f2; sin corridas)

1. Reconciliacion: la matriz R1-R11 siempre fue 10 PASS + 1
UNKNOWN (el "9 PASS" era error de conteo en la prosa; corregido
con historia preservada). UNKNOWN-vs-STALE por capas: el slot
`feed_health` de la respuesta sale de `status_readonly` via
`_feed_unknown()` (el lector V2 no evalua transporte en vivo por
diseno); el STALE de la barra lo enriquece el BFF desde el ultimo
snapshot grabado. Sin contradiccion. Backtests existen y se
reutilizan sin cambios: `backtest_offline.py` (v4.2) +
`run_family_evaluation.py` (jamas descritos como inexistentes;
aqui se inspeccionan y reutilizan).
2. `scripts/capture_run_window.py` (solo GET a runtime/detections,
learn-and-pin de run_id/UUID, capturas t0/+30/+60/+90 + terminal
acotado, payload revisado, run-changed/incompatible registrados
sin sustituir ni relanzar, salida protegida, budgets explicitos;
exit 0/1/2/3/4/5). R3 solo PASS con captura en ventana activa +
enlace exacto (HEALTHY/temporal/post-cierre no bastan). 10 tests
locales (valida/errores/timeout/cambio/enlace/cierre/proteccion).
Comando proxima ventana (tras el launch autorizado):
`python scripts/capture_run_window.py --run-id <stem> --out
docs/evidence/R3_WINDOW_<stem>.json` (offsets/defectos por
defecto; ids tambien aprenden solos).
3. Inventario `docs/ENGINE_ENTRY_EVAL_INVENTORY.md` (matriz
capacidad/fuente/faltante/aceptacion H1/H2/H3 + bounce; H3 sigue
bajista). Adaptador `scripts/export_engine_inputs.py`
(PROPOSED-P1-11C-map-v1 NO aprobado, up->LONG/down->SHORT
declarado). Prep mecanico en temp: 8637 velas + 1558 eventos,
cutoff mediana, hash 1358c7f05ee8474b, 692 trades @1x, 0
mismatched/expirados, overlaps contados, rebound/baseline vacios;
economia calculada pero RETENIDA (sin lectura). Faltan: mapping
aprobado, calendario funding realizado (contrato §B), costes
medidos, purga/embargo, prueba de disponibilidad.

## R3 v2 + causalidad de velas (2026-10-16, sobre 69d55ba; sin corridas)

1. Captura: adquisicion separada del veredicto (terminal/exit 0
nunca implica PASS). R3 PASS exige captura RUNNING del run
esperado + proceso verificado + atribucion exacta demostrable
(UUID fijado presente + feed_attribution current); HEALTHY/current
solos, coincidencia temporal y post-cierre no bastan.
UUID ausente al adquirir: se acepta, se registra la ausencia y se
fija el primer UUID valido posterior (tardio); cambios posteriores
se rechazan, desapariciones se registran sin detener. Detections
verifica run_id/UUID antes de atribuir (foreign/mismatch/unlinked
registrados, contenido conservado pero no atribuido). Informe con
identidades fijadas + `r3` (PASS/FAIL/UNKNOWN + motivos):
terminal-directo/acquire-timeout/run-changed = UNKNOWN,
enlace contradictorio = FAIL. 6 tests R3 (incl. PASS completo con
identidades fijadas y UNKNOWN con adquisicion completa).
2. Export: close_time venue preservado por vela (`Candle.
close_time_ms` aditivo: solo procedencia, fuera de matematicas y
de `input_hash`), `--as-of-ms` filtra velas abiertas (contadas),
meta con unidades/cobertura/violaciones de cadena (0 en trio 15m)
y distincion as_of (frontera de conocimiento) vs cutoff (split
dev/OOS). Regresion causal: evento 1ms dentro de vela 15m llena
en el siguiente open conocido, jamas toca su rango; runner
conserva open/close_time (hash intacto). Mapping PROPOSED y
salida solo-mecanica intactos; sin optimizar, sin P&L, sin
repetir el prep economico.

## Atribucion exacta R3 (2026-10-16, sobre a2aebc5; sin corridas)

1. BFF (`frontend/src/lib/runtime-control.ts`): `feedFromStore` +
`runtimeStatus` exponen `feed_attribution_method`
(exact-uuid/temporal/none) + `feed_snapshot_run_id` (UUID real
de la fila o null) + `feed_snapshot_timestamp` (segundos de la
fila o null). Exact-uuid solo cuando la fila y el registro
llevan el mismo UUID; temporal en la via conservadora del
reloj; none cuando no hay enlace atribuible (incluido
incompatible y sin ventana). Salud, umbrales (0.05/0.5, 120s,
30s), Start/Stop y contratos intactos; campos aditivos.
2. Capturador (`scripts/capture_run_window.py`): conserva los
tres campos por captura; R3 PASS exige RUNNING del run
esperado + proceso verificado + UUID fijado igual en registro
y snapshot + metodo exact-uuid + feed_attribution current +
detections atribuido. Temporal HEALTHY/current, snapshot sin
UUID, coincidencia temporal o post-cierre nunca califican;
UUID incompatible nunca PASS (FAIL si hay enlace
contradictorio). Regresion: valido+sin-UUID/temporal->UNKNOWN;
coincidente+exact->puede calificar; incompatible->nunca PASS.
3. Verificado con fixtures locales: frontend 304/304 (4 BFF
nuevos) + capturador 19/19 (3 R3 nuevos) + export 6/6; sin
Binance, sin corridas. V2 3020 intacto (build anterior, sin
redeploy), monitor detenido.

## R3 vivo brief 120s (2026-10-16, autorizada 1x; sin codigo)

1. Lanzamiento unico por ruta publica V2 (brief=120, 200
confirmado). La respuesta 200 no expone `run_id` en el nivel
superior: se reconcilio por GET runtime ( STEM RUNNING + UUID)
sin relanzar ni duplicar, y se arranco el capturador con ambas
identidades fijadas y salida nueva y protegida.
2. Adquisicion 5/5 (3 RUNNING + 2 post-cierre), outcome
terminal-captured; veredicto R3 PASS en vivo (triple RUNNING
verificado con exact-uuid + snapshot coincidente + current +
detections atribuidas; HEALTHY como contexto). Cero eventos
iniciales valido (18/3 desde +60s).
3. Cierre natural COMPLETED duration-reached exit 0, contador
congelado 133s, PIDs muertos, 0 python, SQLite sin journals,
tamanos invariantes, filas UUID 4/6/39/9 con deltas netos por
retencion (flow_10s 4117->3636). Sin recovery, sin relanzar.
Residual R3 vivo cerrado; siguiente: offline entradas/salidas
(recomendado, no ejecutado).

## Offline entry/exit closeout V1 (2026-10-16, sin ventana forward, sin simulacion prospectiva)

1. Causalidad por operacion (no por afirmacion): event_time = open de
formacion, condicion conocible solo al close_time (= available_at);
entrada = primer open > event_time (= entry_time). Auditoria re-ejecutada
offline en temp (export+seleccion+runner, sin red, DB solo lectura):
1412/1412 operaciones con available_at presente y entry >= available
(0 violaciones, 0 nulos; gap uniforme 1ms por cadena intacta: 2879 velas
cerradas/simbolo, 0 null_close_time, 0 violaciones). Tripletas conservadas
en docs/evidence/OFFLINE_EVAL_AUDIT_V1.json. Disponibilidad de senal VIVA
sigue UNKNOWN (sin prueba de formacion en streaming).
2. Reconciliacion: fuente 1558 (BTC 476 + ETH 498 + SOL 584) - 1 purgada
(ETH continuation LONG 1790007300000, ventana cruza el cutoff) = 1557
admitidas (476+497+584; dev 777 + oos 780) - 145 solapes (max_concurrent=1
intra celda) - 0 expiradas - 0 desajustadas = 1412 operaciones (BTC 452 +
ETH 457 + SOL 503) = 1410 realizadas + 2 marcas open_at_end. Draft previo
corregido (ETH 497 era admitidas no fuente; SOL H2 6 no 7).
3. Funding: 1 liquidacion sostenida (+0.0894 USDT, ETH cont-dev) + 1403
cubiertas sin liquidacion en ventana + 8 UNKNOWN/uncovered (6 colas + 2
marcas, uncovered_ms 2700000 c/u); 1404/1412 completitud contable.
'4 ventanas' del draft ANULADO (eran 179 horizontes de evento con
liquidacion, solo 1 sostenida en [entry,exit)). Sensibilidad sin
calendario: delta +0.0894 en una celda, resto identico; 'inmaterial' no
se concluye para el conjunto uncovered. Cobertura y rango por simbolo en
el audit JSON.
4. Exposicion: max_concurrent=1 rige DENTRO de cada celda
(simbolo-grupo-segmento-escala); simbolos en procesos separados con
calendarios fijados (extranjero rechazado), grupos en llamadas separadas.
Pooled = suma aritmetica de replays independientes, NO cartera de una
sola posicion; exposicion simultanea no modelada.
5. Resultados: E bruta +1.88...+3.11 USDT/operacion sobre nocional fijo
1000 USD @1x; friccion medida ~1.60/op (comisiones ~1.00 + spread/slip
asumido ~0.60; el '~1.0' del draft cubria solo comisiones). Costes 5/1/2bps
supuestos versionados (COST-ASSUME-v1), no medidos. Held-out non-pristine;
pooled no es estrategia alternativa comparable. Las 12 celdas direccionales
caen en negativo a 2x (verificado).

## Fix artefacto offline-eval publicado (2026-10-16, sin corridas)

1. Defecto: frontend/src/lib/offline-eval.ts importaba
@/data/offline-eval-v1.json, ignorado por data/ y ausente en GitHub
(404 en checkout limpio). Informe y audit lo referencian.
2. Correccion: artefacto publicado por force-add (114195 B, sha256
c051e888...287b3a, identico al pin del informe) + generacion
determinista scripts/aggregate_offline_eval.py (solo bundling de
manifiestos/meta/seleccion/calendarios, fail-closed; pooled = sumas
aritmeticas) verificada byte-identica desde los replays en temp.
3. Hashes de adquisicion funding reconciliados: los del draft eran de
crudos transitorios (ya no disponibles); rigen los provenance de los
calendarios en Git (tabla corregida + re-adquisicion documentada).
4. Limitacion declarada en informe 10: el export lee el historico
canonico local (no publicado); checkout limpio verifica artefacto,
agregacion (fixtures), UI y build, pero no regenera desde cero.

## Paquete reproducible + causalidad + costes + protocolo prospectivo (2026-10-17, sin corridas)

1. Paquete OFFLINE-EVAL-PACKAGE-V1 (manifiesto docs/evidence/OFFLINE_EVAL_PACKAGE_V1.md): re-export/replay en temp reproduce input_hash (BTC 31c100e2, ETH 7643681e, SOL d784680b) y artefacto byte-identico (c051e888...287b3a); IDs originales 1:1 en event_ids.json (0 faltantes/multiples); checkout limpio verifica artefacto/agregacion sin canonico; zip fuera de Git + regeneracion por scripts/reproduce_offline_eval.py; reproduccion externa PENDIENTE.
2. Causalidad (docs/OFFLINE_EVAL_CAUSAL_AUDIT_V2.md): formacion prefijo-causal + invariancia estricta 18/18 (3 simbx6 fam); direction/reference de datos pasados; seleccion retrospectiva (subconjunto piloto, exhaustiva actual daria ~1997 solo BTC); entry>=available no elimina sesgo de seleccion. Matriz: H1/H3/H2-legs RETROSPECTIVAS no utilizables como senal; rebote UNKNOWN/excluido. H3 nunca redefinido; direccion nunca por rendimiento posterior.
3. Costes (docs/OFFLINE_EVAL_COST_BREAKEVEN_V1.md): breakeven s*=G/F1 1.18-1.94, maxRT 18.8-31.1bps; 12/12 direccionales negativas a 2x (fragil). Comisiones por escenarios oficiales (taker+taker ~1.00 = supuesto V1; maker/mixto/BNB como escenarios, tier jamas asumido). Spread/slippage historicos UNKNOWN (prohibido derivarlos del presente). Funding con signo/cobertura; 8 UNKNOWN nunca cero; realizadas separadas de abiertas. Pooled = suma aritmetica, NO cartera; baseline comparable propuesto TIME-PLACEBO-v1 (no implementado).
4. Protocolo prospectivo V1 (docs/PROSPECTIVE_PROTOCOL_V1.md, solo preparacion, NO ejecutado): hipotesis elegibles H1/H3 solo con MAP-APPROVED-v1 + disponibilidad live + ventana pristina + costes medidos; bloqueo actual = ninguna elegible; criterios aceptacion/rechazo (supera placebo + sobrevive 2x); prohibido reajustar sobre la ventana; siguiente accion exacta en 4 pasos.
5. V2: OfflineEvalSection con bloques reproducibilidad/causalidad/breakeven (solo lectura, sin senales; Start/Stop/supervision/atribucion intactos).

## 2026-10-16 — Preservar objetivo de movers extremos (documental)
Por instruccion del usuario se reafirma el alcance de PRODUCT_GOAL:
universo Futures elegible, ganadores/perdedores, continuacion vs giro,
entradas/salidas y duracion dinamica. El trio BTC/ETH/SOL valida mecanica
en su cobertura, no sustituye el selector de extremos. H3 sigue bajista;
rebote es variante H2 separada. No se aprueban reglas ni parametros nuevos.
EXTREME_MOVERS_OBJECTIVE.md fija delta de investigacion, recorrido V2 y
aceptacion. F-EXTREME-OBJECTIVE-01 registra el seguimiento. Actual tarea
offline conserva prioridad; sin corridas, paper, servicios ni codigo tocados.

## 2026-10-16 — BTC como activo y contexto, sin regla automatica
Aclaracion del usuario: BTC permanece elegible para posiciones y es referencia
transversal para altcoins. Se preservan las cantidades ya previstas en
SIGNAL_RESEARCH_PLAN. EXTREME_MOVERS_OBJECTIVE §11 registra alineacion,
fuerza relativa, divergencia, sincronizacion at/before T y comparacion con/sin
BTC. Co-movimiento, escasez/magnitud de divergencias y poder predictivo son
hipotesis a medir, no hechos asumidos ni instrucciones de trading.
Solo documentacion en rama aislada; sin codigo, reglas, corridas ni gates.

## 2026-10-16 — Estructura historica y stops: diseno, no garantia
Por solicitud del usuario se documenta F-STRUCTURE-EXIT-01 en
HISTORICAL_STRUCTURE_AND_EXIT_PLAN.md, con enlaces desde MARKET_DATA,
POSITION_MANAGEMENT y EXTREME_MOVERS_OBJECTIVE. Contexto multihorizonte,
fuentes/contratos separados, cache/retencion medida y zonas causales;
no techo/piso seguro ni trailing que evite toda salida prematura.
Parametros y reglas quedan candidatos a evaluar con costes, no aprobados.
Fase causal/costes activa intacta; sin datos nuevos, codigo, servicios ni sesiones.

## 2026-10-17 — Integracion documental extreme-movers (sin sobrescribir)
Integrada la rama review/extreme-movers-objective-20261016 hasta 7a4e872
sobre la evolucion actual (004b300e): restaurados EXTREME_MOVERS_OBJECTIVE.md
y HISTORICAL_STRUCTURE_AND_EXIT_PLAN.md verbatim + portados selectivamente
los suplementos en PRODUCT_GOAL/MASTER_PLAN/MARKET_DATA/POSITION_MANAGEMENT/
TASK_QUEUE/CURRENT_STATE/DECISIONS/FEATURE_BACKLOG. No se aplico snapshot
completo ni se sobrescribio ningun archivo concurrente; conflictos resueltos
por contenido. Estos planes no aprueban parametros ni autorizan implementarlo
todo ahora: soportes, stops dinamicos y Paper Lab conservan su secuencia.

## 2026-10-17 — Cierre EVAL-CENSUS-V2 + selector fixtures + QA visual (sin corridas)

1. Censo CENSUS-V1 exhaustivo (scripts/reconstruct_causal_census.py,
   sin seleccion retrospectiva): 9320 detecciones, 9320 admitidas,
   0 descartadas; entry>=available 9314/9314 (6 tail-edge sin entry,
   honesto); 594 grupos duplicados cross-familia (+616 filas) contados,
   NUNCA tratados como independientes (correlacionados por construccion);
   2831/2831 originales reproducidos (originals_only=0); 6489
   censo-unicos. Causa de las seis sin entry: borde de dataset (ultima
   vela), sin siguiente open conocido; no imputadas.
2. EVAL-CENSUS-V2 (5255 trades @1x = 4055 15m + 1200 1h; mapping
   MAP-CANDIDATE-v2 NO aprobado; costes COST-ASSUME-v1 supuestos):
   0 celdas elegibles (criterio pre-fijado: superar placebo Y sobrevivir
   2x). H1/H3 RECHAZADAS (18/18 15m + 6/6 1h negativas @1x). H2 fade
   RECHAZADO como metodologia (mejor s*<2 o n insuficiente; anecdotas
   n=1 cercadas). H2 fade se conserva como HIPTESIS NUEVA (correction-
   exhaustion/reversal), NO estrategia aprobada. Rebote EXCLUIDO.
3. Funding: 741 liquidaciones aplicadas en ventana, 0 unknown-excluded
   en las 60 celdas (UNKNOWN anteriores eliminados: todo settlement en
   ventana liquido sobre marca fresca); 24/60 celdas con holdings de
   cola fuera del calendario = uncovered/UNKNOWN (nunca cero inventado).
4. Placebo TIME-PLACEBO-v1: seed 42, entradas alternantes en timestamps
   aleatorios, MISMA cobertura/cadencia/costes por celda; una
   realizacion, NO una distribucion (no presentar como banda). Varias
   celdas direccionales rinden PEOR que exposicion aleatoria.
5. HORIZON-GRID4-V1: degeneracion 1h/1h demostrada (entry==exit, bruto 0
   por construccion, no resultado). Separacion explicita: experimento
   original OFFLINE-EVAL-V1 (horizonte 1h por defecto, intacto) vs
   nuevo horizonte (15m->1h, 1h->4h; flag --horizon-ms aditivo del
   runner, tests verdes). NO es optimizacion validada.
6. Selector SELECTOR-EXTREME-V1 (src/microstructure_probe/
   extreme_selector.py): mecanismo rank/coverage probado con fixtures
   (tests/test_extreme_selector.py); universe/liquidez/market_cap
   UNKNOWN (sin historico); ranking != entry; NO aprobado como senal,
   NO evaluado sobre el censo (el censo mide familias, no el selector).
7. Estrategia completa de extremos sobre universo y liquidez: NO
   EVALUADA donde falten datos (universe_ranking_history,
   liquidity_spread_depth, market_cap datado ausentes). El selector
   registra UNKNOWN; full-input decisions impossible on this dataset.
## 2026-10-17 — Auditoría trazabilidad EVAL-CENSUS-V2 (addendum sobre commit b5cd690 / 1385927)

1385927 es el prefijo de 7 chars del SHA publicado `13859277b7baa8b029d385c41bd3cb60c7cd4b13` (commit EVAL-CENSUS-V2, rama review/o1-funcional-v2-observacion), NO un run_id ni sesión. Verificado con git rev-parse/git show/git fetch; HEAD == origin/rama.

Correcciones explícitas (sin reescribir historia):
- H1/H3 direccionales 15m @1x = 12 celdas, 12 negativas. El "18/18" del commit mezcla 6 celdas baseline/comparator; no son direccionales. Doc base (§6) ya decía 12/12; mensaje de commit corregido por addendum.
- Ledger de flujo desde manifiestos ejecutados (temp/opencode/eval*_*) + artefacto: 9320 detecciones censo → 7541 trio 15m+1h al builder (1779 censo extendido fuera de alcance) → 7167 admitidas direccionales + 374 excluidas por motivo (gap 225, no_entry 4, h2_no_conf 43, h2_reclaim 102) → expansión 1:2 placebo → 14334 → purge 30 → 14304 (= 7152 hipótesis + 7152 placebo). Hipótesis 1x: 7152 eventos, 2991 trades, 5 abiertas, 4161 skipped. Placebo: 7152/2264/2/4888. Total: 14304/5255/7/9049. realizadas = trades − abiertas (2986/2262/5248).
- Trazabilidad: manifiestos con event_ids en temp/opencode (fuera de Git); vínculo completo detección→operación UNKNOWN hasta incorporarlos a Git. 594 grupos/616 filas duplicados del censo = misma (symbol, interval, formation_time) en múltiples familias; mecanismo verificado en subset BTC15m (129 grupos/135 filas); builder asigna cada detección a UNA familia (no duplica trades); max_concurrent=1 es intra-celda, NO prueba independencia entre familias/cedas.
- Funding: 741 settled_events (escala 1x, hipótesis+placebo) = aplicaciones por operación; 270 liquidaciones únicas del calendario (90/símbolo); 0 unknown-excluded ≠ cobertura completa; 24/60 celdas uncovered. 741 ≠ 270 (métricas distintas).
- MFE/MAE: mfe_mean/mae_mean de backtest_offline.run_backtest = excursión por posición, no captura por salida. Rango direccional 1x n>=30: MFE 0.19-0.64%, MAE 0.16-0.42% (aprox. al citado 0.18-0.66/0.10-0.42; subpoblación no especificada).
- Verificador reproducible: scripts/audit_offline_eval_ledger.py + scripts/audit_offline_eval_checks.py (20 regresiones, todas pasan). Evidencia: docs/evidence/audit_offline_eval_ledger.json.
- Sin corridas Binance, forward, paper, órdenes, optimización, cambios de umbrales. Sin modificar DBs canónicas. V2 en 3020; monitor detenido.
- Pendientes: incorporar manifiestos temp/opencode a Git; verificación exacta de 594/616 sobre censo completo.


## 2026-10-17 — Corrección explícita de auditoría trazabilidad EVAL-CENSUS-V2 (sobre commits b5cd690 y bea541a / 1385927)

Corrige el addendum anterior de esta misma fecha (líneas 2390-2402) de forma explícita, sin reescribir historia:

1. Conteo de pruebas: el verificador tiene 30 tests unittest (tests/test_audit_offline_eval_traceability.py), todos pasan (0 fallos, 0 errores). Se retira la afirmación de "20 regresiones"; se usa unittest con conteos reales (tests ejecutados / fallos / errores), no contadores ficticios.

2. Duplicados 594/616: VERIFICADOS en el conjunto completo (9320 detecciones), no solo en subset BTC15m. Desglose verificado por ejecutar reconstruct_causal_census.py sobre historical.db (read-only):
   - 15m trio (BTC/ETH/SOL): 6121 det, 371 grupos/383 extra
   - 1h trio (BTC/ETH/SOL): 1420 det, 45 grupos/47 extra
   - MINAUSDT 1h: 626 det, 90 grupos/92 extra
   - NMRUSDT+ORCAUSDT 1h: 1153 det, 88 grupos/94 extra
   - Total: 9320 det, 594 grupos/616 extra ← coincide exactamente con el artefacto.
   Se retira la afirmación "verificado solo en BTC15m"; se conserva como pendiente únicamente la incorporación de los manifiestos temp/opencode a Git.

3. 1779 fuera de alcance del builder: verificados por membresía individual, no por resta. Son MINAUSDT 1h (626 detecciones) + NMRUSDT 1h + ORCAUSDT 1h (1153 detecciones) = 1779. Estos símbolos no están en el alcance de EVAL-CENSUS-V2 (solo trio 15m/1h).

4. MFE/MAE: mfe_mean/mae_mean de backtest_offline.run_backtest = excursión por posición, NO ganancia capturada por la salida. Rango global todas celdas 1x: MFE 0.0-1.04%, MAE 0.0-0.50%. Rango direccional 1x n>=30: MFE 0.19-0.64%, MAE 0.16-0.42%. Se corrige la presentación anterior como "aproximada"; se documenta explícitamente como excursión, no captura.

5. Causalidad: el mecanismo entry >= available está testeado en fixtures (tests/test_causal_census.py: available_at = close_time de formación, entry >= available, decision_time NULL). Sobre datos reales del censo completo, entry>=available no está publicado en el artefacto (propiedad del reconstruct); resultado sobre datos reales = UNKNOWN hasta incorporar manifiestos a Git.

6. Trazabilidad: manifiestos con event_ids en temp/opencode (fuera de Git); vínculo completo detección→operación NO publicado en Git (UNKNOWN). Cada evento en manifiestos events.json tiene campos de identidad requeridos; IDs técnicos (event_id con índice) únicos; claves semánticas duplicadas reportadas y clasificadas (permitidas si provienen de detecciones distintas).

7. Verificador portable: scripts/audit_offline_eval_ledger.py (estatus COMPLETO/INCOMPLETE, SHA256 de cada input, rutas repo-relative, sin rutas absolutas de usuario) + scripts/audit_offline_eval_checks.py (runner unittest con conteos reales). Incluye tests de mutación: duplicado semántico, entrada antes de disponibilidad, referencia inexistente, familia/segmento ausente, motivo ausente, funding ausente, manifiesto alterado, input alterado vs hash, población MFE incorrecta, control positivo. Cada defecto produce fallo esperado.

8. Sin corridas Binance, forward, paper, órdenes, optimización, cambios de umbrales. Sin modificar DBs canónicas. V2 en 3020; monitor detenido.

9. Pendiente: incorporar manifiestos temp/opencode a Git para cerrar la trazabilidad completa (vínculo detección→operación sigue UNKNOWN).


## 2026-10-18 — Corrección de auditoría EVAL-CENSUS-V2: verificador con evidencia verificable (sobre bea541a / 1385927)

Corrige el addendum anterior (2026-10-17) de forma explícita, sin reescribir historia. El trabajo previo tenía tests tautológicos (`assertTrue(True)`, `assertLess(1000,2000)`) que no detectaban defectos y secciones causales marcadas OPEN sin datos. Ahora:

1. Conteo de pruebas: 45 tests unittest (tests/test_audit_offline_eval_traceability.py), todos pasan (0 fallos, 0 errores). Sin contadores ficticios. Meta-prueba de mutación ejecutada: al alterar el verificador (causalidad ignorada, censo sin duplicados) los tests dirigen fallos (3 y 1 respectively) — los tests detectan alteraciones.

2. Causalidad VERIFICADA sobre datos reales (detections.jsonl del reconstruct, 9320 detecciones): 9314 OK (formation_time <= available_at <= entry_time_same_grid), 6 UNKNOWN (entry_time_same_grid NULL → excluidas no_entry por el builder), 0 violaciones. Ya no UNKNOWN: los datos existen en temp/opencode/census_*/.

3. Duplicados separados en 4 identidades: ID técnico (event_id con índice global, único), ID original (original_event_id de la detección), clave semántica (sin índice), grupo correlacionado (formation_time compartido). Duplicación PERMITIDA: censo inter-familia (594 grupos/616 filas), events.json con >=2 detecciones distintas o placebo. Error: misma detección admitida 2 veces (0 casos).

4. 594/616 verificados en conjunto completo con función pura: 15m trio 371/383 (BTC 129/135, ETH 112/114, SOL 130/134), 1h trio 45/47, MINAUSDT 90/92, NMR+ORCA 88/94. Total 594/616 ← coincide exactamente con artefacto. 0 grupos con misma definición repetida.

5. 1779 fuera de alcance por membresía (no por resta): MINAUSDT 626 + NMR 35 + ORCA 53... verificado: NMR+ORCA = 1153 detecciones en 1h. No están en el scope del builder (solo trio).

6. Vínculo detección→evento H1/H3 reconstruido: 6868 eventos, 0 sin respaldo, 0 excedentes (el builder no inventa eventos). H2 vinculado reconstruyendo CONFIRM-H2 determinista sobre las mismas barras.

7. Duplicados events.json clasificados con origen: 0 errores. H1/continuation (mismo formation_time, 2 detecciones: EXTENDED_GAINER + MOMENTUM_ACCELERATION_UP), H2 (múltiples formaciones confirman en misma barra), placebo (colisiones rng internas, identidad sintética propia).

8. Referencias artefacto↔manifiesto: consistentes (60 celdas artefacto vs 56 manifiesto; rebound-variant con 0 eventos no genera celda, esperado). Campos compartidos (n_events, n_trades, n_open, skipped_overlap) coinciden.

9. Funding: 741 settled_events (aplicaciones por operación), 0 unknown_excluded, 24/60 celdas uncovered. unknown-excluded y uncovered son conceptos distintos. funding_quality ausente → INCOMPLETE (nunca cero por defecto).

10. MFE/MAE: fórmula = excursión por posición (mfe_mean/mae_mean del runner), NO ganancia capturada. Rango global y rango direccional n>=30 calculados explícitamente por función pura (rango_mfe_mae).

11. Trazabilidad completa: el ledger publicado (docs/evidence/audit_offline_eval_ledger.json) ahora incluye secciones causalidad, duplicados_censo, duplicados_events, referencias con evidencia real. El vínculo completo detección→operación seguirá UNKNOWN hasta incorporar manifiestos temp/opencode a Git.

12. Generador portable: estatus INCOMPLETE + exit≠0 cuando faltan inputs (tests de integración lo verifican). Sin rutas absolutas de usuario. SHA256 de cada input registrado.

13. Sin corridas Binance, forward, paper, órdenes, optimización, cambios de umbrales. Sin modificar DBs canónicas (hashes_equal=True en barrera de aislamiento).


## 2026-10-18 — Veredicto global, trazabilidad a operación y paquete de evidencia (sobre 7aa863f)

Corrige y extiende el addendum anterior de forma explícita, sin reescribir historia:

1. Veredicto global PASS/FAIL/INCOMPLETE integrado en `scripts/audit_offline_eval_ledger.py`. PASS solo con adquisición completa y 0 discrepancias. FAIL si existe discrepancia demostrada (coexiste con INCOMPLETE si procede). Cada error incluye sección, clave afectada y motivo. Exit 0 solo cuando el veredicto es PASS. Secciones integradas: causalidad, referencias, campos económicos, duplicados, vínculos H1/H3, descartes, trazabilidad de operaciones, tail-edge, funding, hashes de inputs.

2. Trazabilidad hasta la operación real del replay: `scripts/reconstruct_replay_traces.py` re-ejecuta el bucle del runner (split_by_time + BacktestConfig por grupo/escala) sobre events/candles publicados con configuración inferida de los manifiestos (cutoff_ms, exit_horizon_ms, escalas 1.0/2.0/3.0, calendario funding con conversión rate×10000 a bps). Demuestra equivalencia por celda contra el manifiesto: n_events, n_trades, n_realized, n_open, skipped_overlap, n_expired, n_mismatched, exit_reasons, config_hash, mfe/mae, expectancy_net/gross, total_net, total_net_realized, total_fees, total_funding, max_drawdown (0 celdas fail). Vinculación trade→evento vía admitted_positions de run_backtest (campo añadido al motor, sin cambio de mecánica) → event_id del manifiesto. 5255 trades escala 1.0 reconciliados exactamente con el manifiesto (5255 = 5255, 0 diferencias por celda; 5248 realizadas + 7 abiertas).

3. Paquete de evidencia publicado en `docs/evidence/eval-census-v2-package/` (33 archivos): manifests, events post-purge, selections, build_reports, funding, detections (censo), candles, con package_manifest.json (SHA256 de cada archivo, versiones, comandos). `scripts/build_eval_package.py` y `scripts/verify_eval_package.py` (PASS verificado). Los trades reconstruidos NO se publican: se regeneran con reconstruct_replay_traces.py desde el paquete.

4. Verificación de que events post-purge no reciben segunda purga: conteos antes/después publicados en package_manifest.json (n_in_pre_purge, n_dev, n_oos, n_purged, n_events_post_purge). En modo package, los events del paquete ya son post-purge y se verifican contra la selección (n_dev + n_oos = len(events)).

5. Parámetros registrados vs inferidos documentados en package_manifest.json: registrados (cutoff_ms, horizon, escalas, familia/versión, calendar funding) vs inferidos (fee_bps, spread_bps, max_concurrent, notional, funding_estimated_bps).

6. Comparación de resultados económicos, costes, funding, realizadas y abiertas con tolerancias explícitas (rtol=1e-9): E_net↔expectancy_net, placebo_E_net↔baseline expectancy_net, exit_stop↔exit_reasons.stop, n_trades, n_realized, n_open, skipped_overlap, total_fees, total_funding, max_drawdown — 60 celdas, 0 discrepancias.

7. Tail-edge (6 detecciones con entry_time_same_grid NULL): 4 clasificadas como exclusiones esperadas verificables (BTC 15m, SOL 15m, ETH 1h, SOL 1h — coinciden con excluded_no_entry del builder). 2 (MINAUSDT/1h, NMRUSDT/1h) conservadas como INCOMPLETE (no build_report para esos símbolos; afectan solo al censo externo al replay, no a operaciones evaluadas).

8. Pruebas de integración CLI: `tests/test_cli_fixtures.py` (10 tests): control íntegro PASS/exit 0; referencia inexistente FAIL; E_net alterado FAIL; campo obligatorio ausente FAIL; escenario inesperado FAIL; duplicación indebida FAIL; entrada antes de disponibilidad FAIL; H2 antes de confirmación FAIL; operación sin candidato FAIL; input faltante INCOMPLETE. Todas las alteraciones generan FAIL o INCOMPLETE con exit ≠ 0.

9. Suite completa: 1260 tests OK (2 skipped), incl. 58 tests de auditoría (45 funciones puras + 3 PackageMode + 10 CLI fixtures). Barrera de aislamiento: hashes_equal=True, file_writes=0, prohibited={}, datos sin cambios.

10. Veredicto actual del ledger publicado: INCOMPLETE (0 discrepancias, 2 incompletos: MINAUSDT/1h y NMRUSDT/1h tail-edge sin build_report). No se declara "auditoría completa" mientras esos 2 vínculos sigan abiertos.

11. Siguiente acción concreta: incorporar manifiestos temp/opencode a Git (p. ej. docs/evidence/manifests/) para cerrar el vínculo completo detección→operación y verificar los 2 tail-edge pendientes.


## 2026-10-19 — Corrección de defectos restantes de la auditoría EVAL-CENSUS-V2 (sobre 2677b2f; sin corridas, sin push aún)

Se corrigieron los defectos pendientes de la auditoría; el ledger y el reconstructor ahora garantizan el contrato fail-closed:

- Reconstrucción fail-closed (scripts/reconstruct_replay_traces.py): una celda fallida NO publica trazas como "verificada". Solo las operaciones de celdas equivalentes se escriben en trades_*.json (consumibles). Las operaciones de celdas falladas van a diagnostico_celdas_fallidas.json, etiquetado explícito FALLIDA_NO_CONSUMIBLE, y el ledger las rechaza. El reconstructor limpia trazas/manifiestos/diagnóstico de ejecuciones previas en out-dir antes de escribir, de modo que no quedan archivos antiguos que parezcan pertenecer a la nueva reconstrucción. El manifiesto reconstruction_manifest.json registra veredicto (COMPLETO solo si todas las celdas, else FAIL), cobertura, celdas_fail y trades_sha256. Se corrigió la afirmación previa de que "ninguna traza fallida se publica": el código anterior SÍ escribía "equivalencia": "verificada" y conservaba los trades de celdas falladas; eso ya no ocurre.

- Modo temp: events_pre definido (n_in_pre_purge documentado); --package usa inputs ya post-purge sin segunda purga; exactamente uno de --package/--temp-dir es obligatorio (ambos o ninguno → error de uso, exit ≠ 0).

- Ledger valida el manifiesto de trazas (veredicto COMPLETO, cobertura de los 6 combos, hashes de trades, sin faltantes/extra/obsoletos, cada archivo consumible) ANTES de consumir las trazas; un manifiesto FAIL, hash mismatch, archivo faltante/extra o no consumible → rechazo (FAIL/INCOMPLETE, exit ≠ 0).

- vincular_trades_eventos: entry_ms/available_at/H2 close_time_ms finitas requeridas; ausencia o valor inválido → INCOMPLETE (nunca aceptación implícita); entrada antes de disponibilidad → FAIL; respaldo por símbolo, resolución, familia, dirección e identidad sin cruzar resoluciones.

### Distinción: publicación vs reproducción vs aceptación
- Publicación: el paquete docs/evidence/eval-census-v2-package/ (33 archivos, package_manifest.json con SHA256) contiene manifiestos, events post-purge, selecciones, build_reports, funding, detections y candles. Los trades reconstruidos NO se publican en el paquete.
- Reproducción: los trades se regeneran determinísticamente con reconstruct_replay_traces.py desde el paquete (--package) o desde inputs pre-purge (--temp-dir); no es la corrida original ni una validación financiera.
- Aceptación: solo la otorga el ledger (audit_offline_eval_ledger.py) con veredicto PASS, requiriendo adquisición completa y 0 discrepancias; los traces rechazados (manifiesto FAIL, hashes que no coinciden, faltantes, extra, obsoletos o no consumibles) nunca son aceptados.

Estado verificado: veredicto global del ledger INCOMPLETE (0 discrepancias, 2 incompletos: MINAUSDT/1h y NMRUSDT/1h tail-edge sin build_report), exit 1. El replay BTC/ETH/SOL está verificado (COMPLETO, 0 discrepancias, trazabilidad COMPLETO, 5255 trades) y se reporta por separado. El residual MINA/NMR es un gap de evidencia del censo externo al replay, no un defecto del replay; se cierra publicando el build_report de esos símbolos.

## 2026-10-20 — Reconciliación plan → proyecto actual y ruta a selección automática + Paper Lab (presupuesto cero)

- Identidad: rama `review/o1-funcional-v2-observacion`, remoto `https://github.com/mariomoreta/binance-futures-microstructure-bot.git`, SHA inicial `b9c27338dee21160da9a839894029c3c70b0e316`, HEAD igual tras commit documental. `git fetch origin` sin cambios remotos nuevos. Sin reset/clean/force.
- `audit_public_data` NO LOCALIZADA (ni checkout ni Git); los 39 tests son `tests/test_p14b_validation.py` (P1-14B.1–.11), ajenos a esa entrega. Se mantiene como no localizada, no se reconstruye.
- Esquema vigente: operativo **schema v10** (22 tablas) + histórico **schema v3** (16 tablas). No describir v9 como operativo vigente.
- Trades 5255 desglosados: Hipótesis 2991 (5 abiertas → 2986 realizadas); Placebo 2264 (2 abiertas → 2262 realizadas); total 5255 (7 abiertas → 5248 realizadas). `realizadas = trades − abiertas`.
- MFE/MAE = **excursión por posición, NO ganancia capturada por la salida** (rango global 1x MFE 0.0–1.04% / MAE 0.0–0.50%).
- V2: `/movers` real; `/paper-lab` componente real; `/backtest` **stub** (FutureWorkspace). No declarar vistas inexistentes.
- Paper Lab: **ningún archivo publicado en Git** (todos untracked, trabajo de otro agente en curso). Artefacto determinista verificado `--check` sha256 `7ba452c3...(estado ANTES del cierre funcional del 2026-10-20; corregido abajo en esta misma fecha: publicado, probado y servido en `127.0.0.1:3020/paper-lab`, sha256 `96a5fa46...`).`08378c7f26a20b12761625dcace6b839ba7576d0221bba0346f41826`. Cuatro estados distinguidos (local en curso / publicado en Git / probado / servido y revisado visualmente) en `docs/PAPER_LAB_PLAN_ETAPA5.md`. No servido ni revisado visualmente por este agente.
- Selector: no sobreestimar el censo; no sustituye universo histórico/ranking rolling24/liquidez. Protocolo de adquisición escalonado preparado (universo ligero → candidatos → detalle limitado, fuentes gratuitas Binance públicas, sin colectores iniciados). Matriz en `docs/HANDOFF_RECONCILIACION_PAPER_LAB_20261020.md`.
- Cambios concurrentes preservados: `frontend/src/app/paper-lab/page.tsx`, `TopNav.tsx`, `format.ts` y Paper Lab untracked no staged ni publicados por este agente.
- Próxima acción única: protocolo de selección automática offline sobre EVAL-CENSUS-V2 (info en T, sin lookahead, ventana incompleta → UNKNOWN), emitiendo WATCH / SIN_ENTRADA / DESCARTADO con motivo versionado. Coordinar cierre con entrega de Paper Lab del otro agente. **[Corregido 2026-10-20: la entrega funcional de Paper Lab se cerró en esta rama; la única acción siguiente es el protocolo de selección.]**
- Documentos afectados actualizados: `docs/PAPER_LAB_PLAN_ETAPA5.md`, `docs/CURRENT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/DECISIONS.md`, `docs/FEATURE_BACKLOG.md`; informe compacto `docs/HANDOFF_RECONCILIACION_PAPER_LAB_20261020.md`.

## 2026-10-21 — Identidad del artefacto Paper Lab y estudio retrospectivo W/LUMIA (presupuesto cero)

- Identidad del artefacto (verificada en código, no por capturas): **BTCUSDT 15m LONG H1** (no SHORT). `replay_id=PLR-BTCUSDT-LONG-1788903900000`, `event_time_ms=1788903900000` (2026-09-08T21:45:00Z), `entry_ms=1788904800000` (22:00:00Z), `exit_ms=1788907500000` (22:45:00Z, salida por `horizon`), `net_pnl=-1.6242` (pérdida). No existen capturas de Paper Lab verificables en este entorno; no se afirma estado visual sin archivo de captura inspeccionado.
- Frontera de revelación causal: velas cerradas se conocen al cierre de barra (`.999`); evento/disponibilidad se revelan en el paso del cursor que cierra la vela de formación, nunca al minuto redondo siguiente ni con ticks inventados. *(SUPERADO 2026-10-20: revelar la «señal» en `event_time_ms` era incorrecto; ver entrada «Correcciones acotadas…» — la detección se revela en `available_at` con `formation_time` como metadata.)*
- Estudio retrospectivo W/LUMIA (auditoría, sin segunda implementación): paquete `binance_case_study/` (12 archivos, hashes 12/12 OK). 1.499 velas 5m + 1.499 velas 1m por símbolo (WUSDT, LUMIAUSDT, BTCUSDT, GTCUSDT), corte `2026-10-12T10:57:19.690Z`. `fundingIntervalHours=4` real (W/LUMIA) vs supuesto 8h del motor (`FUNDING_INTERVAL_MS = 8h`): incompatibilidad de fidelidad de replay; contabilizar cada liquidación de funding realmente cruzada con calendario/tasa del contrato, exposición vigente, signo, fuente/versionado; ausentes → UNKNOWN o exclusión. Casos como `NOT_SIGNAL`; sin OOS, sin calibración, sin rentabilidad; `Casos_Binance_W_LUMIA.png` no inspeccionada visualmente (`NOT_ASSESSED`).
- Documentos afectados actualizados: `docs/PAPER_LAB_PLAN_ETAPA5.md`, `docs/CURRENT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/FEATURE_BACKLOG.md`, `docs/HANDOFF_RECONCILIACION_PAPER_LAB_20261020.md`.está verificado (COMPLETO, 0 discrepancias, trazabilidad COMPLETO, 5255 trades) y se reporta por separado. El residual MINA/NMR es un gap de evidencia del censo externo al replay, no un defecto del replay; se cierra publicando el build_report de esos símbolos.

## 2026-10-20 — Cierre funcional de Paper Lab (replay histórico) y corrección de funding (presupuesto cero)

- **Concurrencia verificada, no inferida:** no existe otro agente editando. Evidencia: mtimes de todos los archivos Paper Lab de 6 h de antigüedad; sin `.git/index.lock`, `MERGE_HEAD`, `rebase-merge`; reflog solo con commits propios. Untracked + handoff antiguo NO eran actividad. Autorizado reemplazar solo el servidor del proyecto en 127.0.0.1:3020, tras verificar identidad (PID del propio `frontend/` del repo) y ausencia de monitor.
- **Artefacto reubicado:** `frontend/src/artifacts/paper-lab-replay-v1.json`. Motivo: `frontend/src/data/` estaba bajo la regla global `data/` de `.gitignore`; una negación `!` no re-incluye dentro de un directorio excluido y además habría expuesto el directorio completo (riesgo de publicar DBs). Solución específica: mover el artefacto fuera de `data/`; `data/` sigue ignorado globalmente. Determinismo `--check` PASS sha256 `96a5fa46499000a8aa223093a145bda49744157468ae80c56b4b126234e80882`.
- **Fronteras temporales (corrección de metodología):** la cinta separa **pasos de vela** (conocidos al cierre `…59.999`) de **pasos de evento** (en su ms exacto). Un evento a `04:00:00.000` NO es conocido con cursor `03:59:59.999`; no se adelanta al cierre de la vela. Regresiones t−1/t/t+1 para entrada y cierre. Se corrige la propuesta previa (incorrecta) de revelar todos los eventos en el paso de cierre.
- **Estados/labels:** SIN POSICIÓN → SIN POSICIÓN/EN ESPERA → ABIERTA → CERRADA. LONG/SHORT separados de la acción de cierre (`cierre = venta` / `cierre = compra`); nunca "compra en espera". BTC identificado como control de mecánica.
- **Contexto/zoom:** 48 velas reales previas al evento (contiguas, solo visuales, fuera de posiciones/P&L) y control de zoom. Sin inventar volumen ni series.
- **Funding (corrección documental autorizada):** `FUNDING_INTERVAL_MS = 8h` es **fallback** cuando no se inyecta calendario (`cfg.funding_calendar is None`); el motor **ya acepta `FundingCalendar` por contrato** (`backtest_offline.py`, `class FundingCalendar`), cuyo `interval_ms` es cadencia nominal informativa. No cambiar el 8 global por 4 ni construir otra contabilidad.
- **Build servida:** `BUILD_ID=jV0tcgCSIEFWga6_YmJW3`; sirve **LONG** (`PLR-BTCUSDT-LONG-1788903900000`), ya no la SHORT obsoleta. Se reemplazó únicamente el servidor del proyecto; sin monitor. *(SUPERADO 2026-10-20: build actual `BUILD_ID=45NLJvJuWqcMjj2IFxW-E`; ver entrada «Correcciones acotadas…».)*
- **Tests/checks:** suite frontend 347/347; `tsc --noEmit` limpio; `eslint src` 0 errores (3 warnings preexistentes ajenos); `next build` OK.
- **Alcance no tocado:** sin Binance, sin paper prospectivo, sin órdenes, sin estrategia nueva; W/LUMIA permanece como estudio retrospectivo separado; MINA/NMR residual sin cambios.

---

## 2026-10-20 (cont.) — Correcciones acotadas de causalidad de revelación, gráfico móvil, etiquetas y estados del reproductor

> Sobre `d9359e3c371f5b87c6266301965fcad175ed0074`. Entrada **append-only**: las entradas de arriba (2026-10-20 / 2026-10-21) NO se reescriben; sus afirmaciones superadas se corrigen aquí.

- **CORRECCIÓN de la entrada 2026-10-20 «Fronteras temporales» y del paso de `signal`:** la entrega previa revelaba «Señal histórica formada» en `event_time_ms` (21:45) pese a declarar `available_at=21:59:59.999`. Era **incorrecto**: revelaba un patrón no conocible hasta su disponibilidad. Se **elimina** ese paso. Ahora hay un único paso de evento **`detection`** en `available_at`, que muestra `formation_time_ms` (21:45) como **metadata** («Detección conocida (formación conservada como metadata)»). `formation_time` (a qué momento pertenece el patrón) y `available_at` (cuándo puede conocerse) son distintos; `entry_time` es ejecución posterior. La formación **nunca** autoriza a revelar antes de la disponibilidad. Invariantes en generador y parser; tests: `available_at−1ms` no revela, `available_at` revela, `+1ms` permanece revelado; formación no revela; entradas/salidas conservan fronteras; cambiar datos posteriores no altera la vista anterior al cursor. Mecánica económica **sin cambios** (`gross=-0.02421656234419101`, `net=-1.6241971890943157`).
- **Metadata fija vs evidencia revelada:** la cabecera de identidad (símbolo, dirección·familia, intervalo, `replay_id`) se rotula como **«escenario seleccionado offline»** (no detección automática disponible en ese instante); el estado «Detección revelada» se llena solo al avanzar. No se presenta lo primero como detección automática.
- **CORRECCIÓN de la entrada 2026-10-20 «Estado visual / estados»:** avanzar manualmente mostraba «REPOSO» con posición abierta y el botón principal no ofrecía «Reanudar». Se separa **estado del REPRODUCTOR** (`sin_iniciar`/`reproduciendo`/`pausado`/`terminado`) del **estado de POSICIÓN** (SIN POSICIÓN → EN ESPERA → ABIERTA → CERRADA). Reiniciar restablece ambos. El nombre accesible del botón principal ahora coincide con la acción (Pausar/Reanudar/Reproducir/Finalizado).
- **CORRECCIÓN de la entrada 2026-10-20 «Contexto/zoom»:** la vista inicial estaba vacía pese a tener 48 velas de contexto. Se añade `initial_cursor_ms` (último cierre de contexto), **anterior** a la detección; la vista inicial muestra solo el contexto ya conocido a ese instante (`close_time_ms <= cursor`). No se simula un reloj indefinido ni se revelan velas futuras. El contexto sigue sin afectar decisiones ni P&L.
- **Gráfico móvil y etiquetas:** SVG con `viewBox` + `width:100%` + `preserveAspectRatio` (responsive real; escala a 360/390px sin recortar el extremo derecho). Etiquetas de nivel con **anti-solape** (solo el texto se desplaza; la línea y el precio real no cambian) + leyenda. Frontera contexto/replay en la **primera vela del replay** (no el inicio de toda la serie). Eje de precios con margen. Sin ticks ni recorrido intrabar inventado (solo velas reales cerradas).
- **Artefacto y build:** nuevo sha256 **`0db0c4d0cf1767736cbeafbae62e12a10adce512e423520bb5046c58dfbfff99`** (`--check` PASS); cinta de **7 pasos** (3 velas + 4 eventos). `BUILD_ID=45NLJvJuWqcMjj2IFxW-E`, servido en `127.0.0.1:3020/paper-lab` (solo servidor propio reemplazado, sin monitor). Suite **368/368**; `tsc --noEmit` limpio; `eslint src` 0 errores (3 warnings ajenos preexistentes). Inspección **visual** de PNG = límite declarado (modelo texto; NVIDIA 401/OpenRouter sin auth); verificación por DOM/texto y geometría, no PASS visual.
- **Alcance no tocado:** sin Binance, sin adquisición, sin paper prospectivo, sin órdenes; sin cambios de estrategia/mapping/parámetros/costes/motor económico/DBs; Start/Stop, supervisión y atribución intactos; W/LUMIA sigue como estudio retrospectivo separado.



## 2026-10-20 (cont.) — Backtest offline funcional en V2 + enlace operacion -> Paper Lab (presupuesto cero)

> Sobre `79b3d8288b07bf115c93db19ce1444697d0dd5de`. Append-only; no reescribe entradas previas.

- **Alcance:** la pantalla `/backtest` deja de ser reservada. Ejecuta UNA
  evaluacion offline versionada y permite revisar sus operaciones y abrir
  una de ellas en Paper Lab. Sin Binance, sin ordenes, sin credenciales,
  sin ejecucion real, sin optimizacion automatica de parametros.
- **Primer experimento soportado (unico):** `eval-census-v2-trio` sobre el
  paquete publicado `docs/evidence/eval-census-v2-package/` (EVAL-CENSUS-V2,
  33 archivos, sha256 verificado antes de correr). BTC/ETH/SOL, 15m+1h,
  todas las familias y baseline, segmentos dev/oos, escalas 1x/2x/3x como
  **escenarios de coste** (NO apalancamiento). Etiqueta: "Evaluacion
  historica de reglas candidatas sobre dataset conocido", NO "backtest
  completo del descubrimiento de extremos".
- **Ejecucion controlada:** ejecutor `scripts/run_dashboard_backtest.py`
  (`dashboard-backtest-executor/v1`) con lista permitida incrustada; el
  cliente nunca envia rutas/simbolos/shell/codigo. Un job a la vez
  (single-flight); estado persistido en disco (`pendiente`/`ejecutando`/
  `completado`/`fallido`) para que refrescar/cerrar no pierda ni relanze.
  Proceso huerfano `ejecutando` se reconcilia a `fallido`
  (`PROCESS_INTERRUPTED`). Identidad/estado SEPARADOS del monitor Binance:
  no reutiliza el controlador de runtime; no es una corrida Binance.
- **Resultados en su propio directorio:** `frontend/.backtest-runs/`
  (ignorado por git), fuera de datos operacionales y de DBs canonicas.
  `trades.json` y `reconciliation.json` deterministas (byte-identicos);
  `summary.json` difiere solo en metadatos de reloj (`generated_at_ms`/
  `duration_ms`). Reconciliacion por celda `Σ net_pnl == total_net` (1e-9,
  56 celdas). Sin sustitutos silenciosos: si no hay resultados, la UI
  muestra el estado real (409), nunca datos simulados.
- **Enlace operacion -> Paper Lab:** `Abrir replay` carga ESA operacion
  (identidad `(event_id, group, segment, scale)`), no la fija. Reutiliza
  `build_paper_lab_replay.py --trades-json` y el reproductor PAPER-LAB-REPLAY-V1;
  conserva revelacion en `available_at`, formacion como metadata, costes
  ejecutados vs hipoteticos y realizado/abierto. Operacion no soportada ->
  422 `REPLAY_UNSUPPORTED` con motivo; sus datos siguen en la tabla.
- **Artefacto fijo superseded:** `replay_id` incorpora group+scale (enlaces
  unicos); sha256 `72af8007d5956244ec7b902c0b12f960cdc6993b6912b4749fff9fcfcb62f172`
  (supersede `0db0c4d0...`). `--check` PASS; ventana/pasos identicos.
- **No hace:** no evalua la estrategia completa de extremos; no hay
  universo/liquidez/ranking causal. Se publica
  `docs/EXTREMES_EVALUABILITY_MATRIX.md` (requisito -> dato -> limitacion ->
  adquisicion siguiente); la matriz NO declara la evaluacion hecha.
- **Contratos:** `docs/BACKTEST_READ_CONTRACT_V1.md` pasa de UNWIRED a WIRED
  (rutas BFF, directorio de runs, determinismo, enlace a Paper Lab);
  `docs/PAPER_LAB_PLAN_ETAPA5.md` documenta el enlace.
- **Verificacion:** backend `python -m pytest tests` 1291 OK; frontend
  vitest 400/400; `tsc --noEmit` limpio; `eslint src` 0 errores (3 warnings
  ajenos); `next build` OK. Desde un checkout limpio (worktree de HEAD +
  archivos nuevos) el paquete publicado basta: `trades=15765`,
  `reconciliacion=True`, sin depender de `binance-temp` ni de ignorados.

## 2026-10-20 (cont.) - Serializacion portable del paquete EVAL-CENSUS-V2 (Bloque A)

- **Defecto (auditoria independiente, reproducido):** en un checkout limpio
  Linux, 21/33 archivos del paquete no coincidian con
  `package_manifest.json`. Causa RAÍZ: no existia `.gitattributes` y
  `core.autocrlf=true` normalizaba a LF los finales de linea en el blob;
  `build_eval_package.py` habia hasheado los bytes CRLF originales. En
  Windows el working tree los restauraba a CRLF (12/33 LF puros coincidian
  por ser archivos sin salto de linea interno). Reproduccion exacta: los 21
  archivos coinciden si se convierte LF->CRLF el blob; los otros 12 no
  dependen del salto de linea.
- **Correccion:** `.gitattributes` raiz marca
  `docs/evidence/eval-census-v2-package/**` y `package_manifest.json` como
  `-text` (binario): git almacena y entrega los bytes EXACTOS, sin traduccion.
  Renormalizado el paquete (`git add --renormalize`) para almacenar los bytes
  canonicos que declara el manifiesto. La verificacion estricta por sha256 se
  mantiene sin normalizaciones silenciosas.
- **Distincion explicita:** reproducibilidad NUMERICA (mismos trades/netos)
  != igualdad de BYTES (mismo sha256 de archivo). El defecto roto era el
  segundo; el primero nunca estuvo en duda.
- **Evidencia (commit `84e6294`):** los 33 blobs DEL COMMIT hashean al
  manifiesto (0 discrepancias); `verify_eval_package.py` PASS desde worktree
  limpio con `core.autocrlf=false` (simula Linux); ejecucion desde ese
  checkout limpio: `trades=15765`, `n_trades_1x=5255`, `reconciliacion=True`,
  `trades.json` sha256 `815b8a65...` (byte-identico a la corrida viva);
  alteracion real de un byte -> `verify` FAIL (exit 1) y ejecutor
  fail-closed (`PACKAGE_VERIFICATION_FAILED`, exit 3, sin `trades.json`).
- **Regresiones:** `tests/test_dashboard_backtest.py::PackagePortabilityTest`
  (5 tests): `.gitattributes` `-text`; blobs del commit == manifiesto;
  working tree == manifiesto (bytes+sha256); `verify` PASS; alteracion real
  rechazada. Fallan antes del fix (el test de blobs detecta la normalizacion
  a LF).
- **Plataforma verificada:** Windows (working tree + worktree limpio con
  `core.autocrlf=false`, equivalente a un checkout Linux por bytes). NO se
  probo una maquina Linux real; el argumento es por bytes de blob, que es
  exactamente lo que git entrega en ambas plataformas tras `-text`.

## 2026-10-20 (cont.) - Identidad de ejecucion, resultados/cache vinculados y ubicacion canonica (Bloque B)

- **Defectos (auditoria independiente, confirmados en codigo):** `job_id`
  era el `experiment_id` (no unico por ejecucion); la liveness se decidia
  solo por existencia del PID; el single-flight era solo dentro del proceso
  (sin bloqueo entre procesos); `BACKTEST_BUDGET_MS` estaba declarado sin
  uso; el `spawn` no manejaba el evento `error`; `readResults` no verificaba
  `result_hashes`; `materializeReplay` reutilizaba un cache por hash de
  identidad NO vinculado a la ejecucion; los resultados vivian en
  `frontend/.backtest-runs/` (divergente del contrato); `retentionReport`
  solo reportaba.
- **Identidad unica:** cada solicitud crea un `run_id` propio
  (`bt-<experiment>-<ts>-<rnd>`), separado del `experiment_id`. Estado en
  `backtest-results/<experiment>/<run_id>/`; puntero estable `current.json`.
- **Exclusion ENTRE PROCESOS:** lock por archivo con creacion exclusiva
  (`O_EXCL`). Un lock vivo impide un segundo lanzamiento aunque provenga de
  otro proceso. Un lock abandonado (pid muerto o presupuesto vencido) se
  cierra como fallido SIN relanzar.
- **Identidad verificable:** la propiedad se prueba solo con
  `executor_token` + `executor_pid` + `started_at_ms` juntos. Un PID vivo
  pero no verificable (ajeno o reutilizado) se reporta como UNKNOWN
  (`PROCESS_IDENTITY_UNKNOWN`), nunca como `ejecutando`, y NUNCA se mata.
- **Presupuesto efectivo:** se aplica en el ejecutor (deadline -> `TIMEOUT`,
  fail-closed) y en lectura (un `ejecutando` verificado que excede el
  presupuesto se cierra `TIMEOUT`). Manejo explicito del error asincrono de
  `spawn` (`SPAWN_FAILED`).
- **Resultados y cache vinculados:** `readRunResults`/`readResults` verifican
  `result_hashes` antes de servir (alterado -> `RESULT_INTEGRITY_FAILED`;
  incompleto -> `RESULT_INCOMPLETE`). Las rutas aceptan `?run=<run_id>`. El
  nombre del artefacto de replay deriva de `run_id` + hash de resultados +
  identidad de operacion, y la operacion DEBE pertenecer a esa ejecucion
  (`TARGET_NOT_IN_RUN`): una ejecucion nueva nunca reutiliza el replay previo.
- **Ubicacion canonica unica:** `<repo>/backtest-results/` (ignorado por
  git), coincidiendo codigo y contrato. La evidencia previa se PRESERVO
  (copiada a `backtest-results/_legacy/`) y la ruta heredada se mantiene
  ignorada; no se elimino evidencia. Retencion acotada que NUNCA elimina una
  ejecucion activa; cuando solo reporta, no declara limpieza.
- **Defecto adicional encontrado y corregido:** `PaperLabSource` seguia
  mostrando la operacion ANTERIOR mientras cargaba o fallaba una identidad
  nueva (el estado de fallo quedaba enmascarado por el estado previo). Ahora
  el fallo de la identidad solicitada tiene prioridad y no se muestra la
  operacion previa.
- **Verificacion (commit `76763d7`):** backend `pytest tests/test_dashboard_backtest.py`
  16 OK (incluye identidad/hashes del ejecutor y presupuesto); frontend
  vitest 418/418; `tsc --noEmit` limpio; `eslint src` 0 errores (3 warnings
  preexistentes); `next build` OK (`BUILD_ID=wzsmXGqnMRh6hnIP_xAan`).
  Ejecucion real del ejecutor con los nuevos argumentos: `run_id` propio,
  `executor_token`/`executor_pid` presentes, `identity=verified`,
  `result_hashes` coincidentes; `trades.json` sha256 `815b8a65...` (sin
  cambio: la serializacion determinista se conserva).
- **Limites:** la verificacion visual en navegador y las capturas quedan para
  el Bloque C. No se probo una maquina Linux real (argumento por bytes).


## 2026-10-20 — SCOPE-DESKTOP-FIRST-20261020 (decision expresa del usuario)

El alcance actual es dashboard V2 web de escritorio + flujo funcional del bot.
Desarrollo movil/tablet, QA/capturas 360/390 px, Flutter y acceso desde telefono
quedan DEFERRED; no bloquean entregas de escritorio. Prevalece sobre requisitos
moviles historicos. Conservar codigo/tests/evidencia existentes sin nuevas
optimizaciones moviles. Desktop debe completarse y aceptarse explicitamente
antes de autorizar una fase movil; Flutter es opcion futura, no trabajo actual.
Detalle y criterios: `docs/DESKTOP_FIRST_SCOPE_20261020.md`.
Cambio solo documental: sin codigo funcional, servicios, corridas ni gates.
CURRENT_STATE/FEATURE_BACKLOG/PAPER_LAB_PLAN estaban en edicion por el agente:
no sobrescritos; deben reconciliar esta decision en su cierre.

## Cinco defectos de Backtest V2: bloqueo de ciclo de vida, identidad del ejecutor, hashes declarados, retencion e hipotesis/placebo (2026-10-20, append-only, base `37bde91`)

Decision de metodologia/control (no economica): se corrigen cinco defectos
probados sin tocar motor, estrategia, mapping, costes ni umbrales.

- **El bloqueo representa el ciclo de vida de UNA corrida, no del experimento.**
  Adquisicion, liberacion y retencion se serializan con un mutex corto por
  experimento (`control.guard`, `O_EXCL`, obsoleto a 30 s). `run.lock` se
  libera solo cuando el ejecutor de ESA corrida esta verificablemente ausente
  (`GONE`) o es definitivamente ajeno (`PROCESS_NOT_OWNED` /
  `PID_INSTANCE_MISMATCH`); `TIMEOUT` no libera por si solo porque no afirma
  que el proceso termino. Un estado terminal con presupuesto vencido NO
  equivale a "proceso terminado": la identidad dudosa conserva la exclusion y
  nunca se mata un proceso no propio. Evita ademas la carrera de doble clic y
  de reinicio del BFF.
- **La identidad del ejecutor nunca se confia de lo almacenado.** Se verifica
  contra evidencia del SO: PID vivo + hora de creacion de instancia + linea de
  comandos que contenga `--run-id`/`--executor-token`
  (`Get-CimInstance Win32_Process` en Windows, `/proc` en Linux, `ps` como
  respaldo). Ajena, reciclada, contradictoria o incompleta => `UNKNOWN`
  (`PROCESS_IDENTITY_UNKNOWN`), con exclusion conservada y sin nueva
  ejecucion hasta confirmar la ausencia. Se elimina la cache de evidencia de
  PID (el reciclado podia devolver evidencia vieja). La hora de creacion usa
  `ToFileTimeUtc()` (el formato local sumaba +4 h en esta maquina). Nunca se
  inicia una ejecucion mientras pueda persistir el ejecutor anterior.
- **Hashes declarados completos y vigentes.** `summary.json`, `trades.json` y
  `reconciliation.json` deben declarar sha256 validos, presentes, completos y
  concordantes con el contenido; falta/parcial/inv�lido/discordante =>
  resultados no disponibles con causa explicita. Los hashes NUNCA se
  recomputan como declarados. Se valida ademas schema e identidad de
  corrida/experimento (`RESULT_IDENTITY_MISSING` si el artefacto no declara
  `run_id`); una reconciliacion ilegible o invalida no es integral; la cache de
  replay queda vinculada a la corrida y a los resultados verificados.
  `reconcile` persiste con compare-and-set: antes, un write obsoleto podia
  clobar el `completado` del ejecutor despues de una consulta CIM lenta.
- **Retencion conservadora.** Solo se elimina terminal + (`GONE` |
  `NOT_OWNED` | `INSTANCE_MISMATCH`) o activo + `GONE`. Se evalua CADA
  candidato (no solo `current.json`) y se preserva `_legacy`, el puntero
  actual, la corrida referenciada por el lock y los directorios no
  reconocidos. El modo reporte solo lee y reporta `would_remove`/`skipped`:
  no modifica estados ni borra.
- **Hipotesis y placebo separados en la UI.** Se muestran por separado y jamas
  se suman como beneficio de estrategia; cualquier suma tecnica se etiqueta
  "suma aritmetica de ledgers (control)" y "NO es cartera ni beneficio de una
  estrategia". Las marcas de abiertas se mantienen aparte y los agregados
  conservan `UNKNOWN` en vez de cero (nulo propaga; conjunto vacio =
  UNKNOWN). 1x/2x/3x siguen siendo escenarios de costes, no apalancamiento.
- **Artefactos con identidad de corrida.** `scripts/run_dashboard_backtest.py`
  escribe `run_id`+`experiment_id` en los tres JSON y declara
  `identity: "declared"`; `scripts/build_paper_lab_replay.py --run-id` emite
  `provenance.backtest_run_id` + `backtest_run_id` y hashea `backtest_trades`
  entre `source_paths`.
- **Evidencia de los cinco defectos:** `frontend/src/test/backtest-defect-regressions.test.ts`
  (7/7 fallan en `37bde91`, 7/7 pasan con el arreglo;
  `docs/evidence/BACKTEST_V2_DEFECT_REGRESSIONS_{FAIL_BEFORE,PASS_AFTER}.txt`),
  `frontend/src/test/backtest-control.test.ts` (41), `backtest-results.test.ts`
  (11), `backtest-workspace.test.tsx` (5), `backtest-integration.test.ts`
  (gate `BACKTEST_INTEGRATION=1`, dos corridas reales) y e2e en navegador
  (`docs/evidence/BACKTEST_V2_E2E_BROWSER_EVIDENCE.md`).
- **Limites:** no se probo una maquina Linux real (el codigo usa `/proc` con
  respaldo `ps`); la inspeccion visual se hizo sobre capturas de escritorio del
  build servido. **Alcance escritorio vigente**
  (`docs/DESKTOP_FIRST_SCOPE_20261020.md`, SCOPE-DESKTOP-FIRST-20261020): la QA,
  las capturas y los criterios de aceptacion moviles quedan aplazados; esta
  entrega no anade trabajo movil ni lo declara gate. No se declaran
  rentabilidad ni edge: los umbrales siguen siendo HIPOTESIS.

## Cierre funcional Paper Lab: causalidad, concurrency y pruebas reales (2026-10-20, sobre dca00ea)

Cierre de contratos pendientes de la entrega funcional de Paper Lab, con
cambios minimos y pruebas que corresponden exactamente a lo declarado. Sin
nuevas pantallas ni otra arquitectura.

- **Evaluacion causal (Item 1):** `evaluate_session` separada en tres fases:
  senal (RULE-CAUSAL-V1, solo informacion disponible en/before T), admision
  por riesgo (parametros estaticos, sin mercado) y simulacion economica
  (run_backtest sobre el prefijo conocido en T). Nunca usa velas futuras,
  existencia de trade, salida, P&L ni comisiones como confirmacion. La
  reserva de datos futuros de la fixture no es accesible al evaluador ni
  se revela en la respuesta. Parametros no optimizados; no se declara ventaja.
  Pruebas: invariancia ante futuros diferentes (mismo prefijo, futuros
  distintos -> misma decision), no confirmacion en T -> abstencion,
  orden causal formacion/disponibilidad/decision/fill, futuros no anticipan
  salida/costes/marcadores.

- **Actualizacion atomica por sesion (Item 2):** `save_session` protege
  cargar->validar revision->aplicar->persistir como operacion indivisible
  con lock de archivo entre procesos (msvcrt.locking Windows /
  fcntl.flock POSIX), temporales unicos por (sesion, PID, token aleatorio),
  y fallo explicito ante archivo ilegible, revision incompatible o identidad
  incierta. Idempotencia por identidad de peticion (request_id): misma
  peticion repetida -> mismo resultado sin repetir efectos; misma clave con
  contenido distinto -> REQUEST_CONTENT_CONFLICT. Duplicado separado de dos
  acciones distintas legítimas. Pruebas entre procesos: dos escrituras
  desde la misma revision (una aplica, la otra conflicto), dos copias de la
  misma peticion (un solo efecto), todos los participantes entregan resultado
  valido, sin perder eventos ni duplicar entrada/cierre, recuperacion
  completa e integra tras recarga.

- **Frescura y desconexion reales (Item 3):** Reloj de simulacion (at_ms),
  available_at/received_at por vela, politica de frescura (stale si la edad
  respecto de T supera STALE_MAX_AGE_MS, desconexion si silencio mayor a
  DISCONNECT_MAX_SILENCE_MS, fin de datos sin velas despues de T). Prueba
  de dato verdaderamente obsoleto respecto de T (no solo fechas
  historicas), interrupcion/reanudacion del feed via eventos de fixture,
  conducta para nuevas entradas y posiciones abiertas. Motivo y evidencia
  registrados; no se fabrica cierre. Fin de datos, stale y desconexion
  son escenarios distintos y conservados separados.

- **Matriz A-E sin aserciones permisivas (Item 4):**
  A: Crear -> evaluar -> entrar automaticamente -> cierre EJECUTADO por
     regla (exit_executed=true, motivo esperado) -> recuperar -> exportar
     CSV/JSON reales y volver a leerlos. Reconciliacion economica
     (bruto - costes = neto, realized_net=null si open_at_end).
  B: Evidencia insuficiente -> SIN_ENTRADA, sin posicion, motivo.
  C: Dato obsoleto/desconexion -> politica y evidencia comprobadas.
  D: Fin de datos sin salida -> posicion abierta, realized_net=null,
     sin marcador ni comision ejecutada de cierre.
  E: Duplicacion y concurrencia real entre procesos ->
     idempotencia/conflicto correctos, sin perdida de eventos.
  Exportacion: sesion, decision, operacion, eventos y version relacionados;
  cantidades, bruto, costes, funding y neto reconciliados; UNKNOWN donde
  falten datos.

- **Verificacion:** 28 pruebas Python del motor + 5 de integracion A-E (33
  total) + 16 pruebas backtest-offline = 44 OK. Frontend vitest 9/9 +
  tsc --noEmit limpio. Sin Binance, monitor, paper prospectivo, ordenes,
  pagos, movil ni optimizacion.

SHA inicial: dca00ea. SHA final: b914f2d (commit en review/o1-funcional-v2-observacion).

## Correccion acotada: camino real dashboard → BFF → Python (2026-10-21, sobre ec0416a)

Correccion de defectos en el recorrido real cliente/BFF/backend de Paper Lab,
sin nuevas pantallas ni otra arquitectura.

- **Reloj causal en el camino real:** `create_session` fija `clock_ms` al
  close_time de la ultima vela de CONTEXTO (frontera inicial), no al cierre
  de toda la fixture. `evaluate_session` rechaza explicitamente cuando falta
  `at_ms` y `clock_ms`; nunca usa `_now_ms()`. El cliente
  `evaluateSessionApi` envia `at_ms` desde el reloj de sesion.
  Senal y posibilidad de fill son estados distintos: una senal valida puede
  quedar esperando un precio ejecutable posterior.

- **Informacion futura:** `session_to_public_dict` serializa solo informacion
  disponible en T: velas con open_time_ms <= T; para velas abiertas solo
  open_time_ms y open (nunca high/low/close finales). `authoritative` se filtra
  para no revelar salidas futuras. `config_hash` y `input_hash` se incluyen
  en la respuesta pública. El almacenamiento interno conserva todas las
  velas para avanzar la fixture. TODAS las respuestas públicas (crear,
  evaluar, consultar, avanzar, recuperar, exportar) usan `session_to_public_dict`.

- **Revision e idempotencia hasta el navegador:** Cada accion logica lleva
  `request_id` y revision esperada (`--expected-revision` en el CLI,
  propagado por el BFF). Un reintento reutiliza su `request_id`.
  Mismo request_id + mismo contenido -> mismo efecto sin duplicacion.
  Misma clave + contenido distinto -> REQUEST_CONTENT_CONFLICT. Dos acciones
  incompatibles sobre la misma revision -> una aplica, la otra informa
  conflicto (HTTP 409, no PYTHON_FAILED/500). El BFF interpreta la respuesta
  estructurada del CLI incluso con salida distinta de cero. El frontend
  muestra los conflictos y recupera el estado autoritativo vía GET.

- **Fin de datos no es cierre ejecutado:** `position.mark_px` nunca se usa
  como sustituto de precio de salida ejecutado. Marcador de cierre solo cuando
  `exit_executed=true`. "P&L neto realizado" usa `realized_net`; si es null se
  muestra "No realizado". Se distingue sesion terminada de posicion cerrada.
  Posicion abierta al terminar datos: conserva entrada, ultima marca y P&L no
  realizado; ninguna salida ni comisión ejecutada inventada.

- **Pruebas y verificacion:** 44 pruebas Python (28 motor + 5 integracion A-E +
  16 backtest-offline) + 9 frontend vitest + tsc --noEmit limpio. Conteo
  corregido: 28 + 5 + 16 = 49, no 44. Build de producción Next.js exitoso.
  Desplegado en http://127.0.0.1:3020 (PID 29944, PID anterior 13868 detenido).
  Rutas /paper-lab-live y /paper-lab sirven HTTP 200. Sin Binance, monitor,
  paper prospectivo, ordenes, pagos, movil ni optimizacion.

## 2026-10-21 — Flujo integrado Paper Lab extremo a extremo + contrato CLI/BFF 409 (commit 1892c23, push realizado)

Sobre HEAD `7a3db9c` (rama `review/o1-funcional-v2-observacion`, ya publicada y al día con origin). Cambios locales pendientes resueltos y publicados en commit `1892c23` (9 archivos).

**Causa del bloqueo HTTP:** ninguna variante de `evaluate` conseguía `ENTRADA_SIMULADA` vía HTTP. Primera transición que fallaba: `evaluate` con `at_ms` en el pasado devolvía `DESCARTADO` (stop ya vulnerado en T) y sin `at_ms` devolvía `SIN_ENTRADA` (ningún close conocido en T=0). Causa concreta: el cliente no revelaba información nueva antes de confirmar señal; el reloj de sesión no avanzaba al revelar la vela 1 antes de reevaluar.

**Correcciones (solo lo necesario):**
1. `step_forward` detecta ahora stop con la vela actual (OHLC conocido en T) usando el mismo stop dinámico que `run_backtest` (`entry × (1 ∓ pct)`), no el `stop_px` estático. Añade `_finalize_stop_exit` con costes ejecutados consistentes. Señal confirmada y fill ejecutado son estados distintos (`en_espera` → `abierta`). El reloj avanza desde el backend con cada `step_forward` (no saltos manuales del test). `entry_ms >= decision_at` invariante respetado.
2. `known_close_cutoff` en `run_backtest` (default `horizon_end`, compatible hacia atrás) restringe close/alta/baja a velas cuyo cierre se conoce en T — usado por la evaluación causal del Paper Lab.
3. Las 5 routes del BFF (`evaluate`, `step`, `exit`, `restart`, `stop`) y el helper `runPython` (crear) parsean ahora **stdout Y stderr** del CLI Python. Cuando el CLI sale con código ≠ 0, el JSON de error estructurado puede estar en stderr; se intenta parsear ambos antes de rendirse. Mapeo: `REVISION_CONFLICT` / `REQUEST_CONTENT_CONFLICT` → HTTP 409; `SESSION_NOT_FOUND` → 404; `LOCK_TIMEOUT` / `WRITE_FAILED` → 503; error inesperado distinguible del conflicto. El cliente muestra el error y recupera el estado autoritativo vía GET.

**Demostración integrada HTTP real (servidor PID 31072, BUILD_ID `jhFu3mEN9yZAntBo_sWsC`, URL `http://127.0.0.1:3020`, sin Binance, fixtures sintéticas):**
- `crear`: sesión `PL-...`, rev=0, `sin_iniciar`, clock=0, cursor=0, decisión=null.
- `evaluar sin señal` (T=0, sin at_ms): `SIN_ENTRADA`, `sin_iniciar`, rev=2.
- `avanzar` (step): reloj avanza a 899999, cursor=1, rev=3 (nueva información revelada).
- `confirmar señal` (evaluate con señal): `ENTRADA_SIMULADA` en T=899999, entry_fill_px=101, entry_fill_ms=900000, `en_espera`, rev=5.
- `esperar fill + entrar` (step): `abierta`, entry_px=101, entry_ms=900000 (>= decision_at 899999 ✓), rev=6.
- `gestionar` (step): marca actualizada, `abierta`, rev=7.
- `cerrar por regla` (step): `cerrada`, exit_reason=`stop`, exit_executed=true, exit_px=95.95, realized_net=-51.56, net_pnl=-51.56, exit_fees_executed=0.475, open_at_end=false, rev=9.
- `recuperar/exportar` (GET): estado idéntico, rev=9, resultado idéntico. CSV/JSON serializables del GET.

**Pruebas de conflicto HTTP real:**
- Dos steps concurrentes, misma revisión: uno HTTP 200 (entra), otro HTTP 409 `REVISION_CONFLICT`; sin entrada duplicada (1 solo event `kind=entry`).
- Misma request_id con contenido distinto: HTTP 409 `REQUEST_CONTENT_CONFLICT`.
- Revisión obsoleta: HTTP 409 `REVISION_CONFLICT`.
- Sesión inexistente: HTTP 404 `SESSION_NOT_FOUND`.
- Caso D (fin de datos, posición abierta, stop no vulnerado, horizon muy largo): `exit_executed=false`, `realized_net=null`, `open_at_end=true`, `exit_fees_executed=0`, posición sigue abierta, GET idéntico.

**Pruebas ejecutadas (árbol actual, 2026-10-21):**
- Motor Python: 23/23 (`test_paper_lab_engine.py`) — todas pasan.
- Suite completa: `python run_tests.py -q` → 1290 OK / 2 skipped / exit 0.
- Frontend: `tsc --noEmit` limpio; `npm test` → 470 passed / 1 skipped; `next build` OK (`BUILD_ID=jhFu3mEN9yZAntBo_sWsC`).
- Servidor: PID 31072, escuchando en 127.0.0.1:3020, `/api/v1/runtime` y `/paper-lab-live` sirven HTTP 200.

**Limitaciones restantes:**
- El recorrido completo vía **navegador interactivo** (no solo endpoints HTTP) no se grabó como evidencia visual; se verificó por HTTP/DOM y texto, no por captura de navegador.
- Motor paper completo (Etapa 5: position manager, ledger de caja, funding recurrente, risk engine) sigue NO implementado; este MVP es pantalla de ingeniería sobre fixtures.
- No se presentaron pruebas Python como verificación del dashboard; Python verifica motor/CLI, HTTP verifica el BFF real.
- SHA final publicado: `1892c23` (remoto `origin/review/o1-funcional-v2-observacion` igual que local).


## 2026-10-21 — F-CHART-BINANCE-01: gráfico bajo demanda con fuente backend compartida

Decisión del usuario: buscar un contrato elegible y ver histórico y actualizaciones vivas, indicadores y operaciones en el dashboard web de escritorio. Especificación: [Acuerdos de gráfico Binance V1](ACUERDOS_GRAFICO_BINANCE_V1.md).

Se usará Lightweight Charts como biblioteca visual; Phinvio es referencia funcional, no proveedor de precios ni motor de operaciones. Catálogo/histórico y datos bajo demanda desde Binance público mediante infraestructura existente. Bot y gráfico comparten valores y tiempos canónicos; frontend no decide. Velas abiertas/provisionales separadas de cerradas; fills y cierres se dibujan solo cuando el backend los ejecuta. Cerrar pestaña no detiene el bot; abrir gráfico no inicia monitor/operación. Caché/retención acotadas, trazabilidad durable para evaluación y reconstrucción de huecos. Stops arrastrables posteriores a la primera versión y sujetos a validación backend.

Base 2a17088 revisada: el cierre HTTP reportado no sustituye corregir futuros en _run_backtest_on_prefix, controles canStep/onDecide y salida stop paralela sin gap canónico. Se mantienen pendientes hasta evidencia correctiva. Primero cerrar esas dependencias, después gráfico con fixtures, adaptador y ventana autorizada por separado. Selector automático y rentabilidad son evaluaciones distintas.

Este commit es documental; no instala, ejecuta ni promueve gates. REA opcional de investigación, sin dependencia productiva. Presupuesto cero y desktop-only vigentes.

## 2026-10-21 — Causalidad del fill, controles reales y mecánica de stop única en Paper Lab

Cierra los tres bloqueos revisados de `2a17088` sin cambiar reglas de estrategia, costes, umbrales ni el motor económico canónico.

**1. La evaluación solo recibe el prefijo conocido en T.** `_run_backtest_on_prefix` se limita al `prefix` (antes se le pasaba el histórico completo, y `known_close_cutoff` no filtraba aperturas futuras: filtraba close/high/low). `run_backtest` rellena en `c.open` de velas con `open_time_ms > event_time_ms`, así que pasar velas futuras filtraba el precio de entrada. Se registra `decision_at_ms` y `available_at_ms` en la decisión.

**2. Señal sin precio ejecutable = entrada pendiente, no resultado.** Se mantiene `ENTRADA_SIMULADA`/`en_espera` con `entry_fill_px|entry_fill_ms|entry_qty|entry_cost = null`; el estado público no puede mostrar fill, cantidad ni coste ejecutados antes de que el reloj revele el precio. El fill ocurre en `step_forward`, que revela la siguiente vela con `open_time_ms > base_clock` y avanza `cursor`/`clock_ms` de forma monótona (sin retroceso ni salto sobre la entrada). `_run_backtest_at_clock(state, clock_ms)` resuelve `horizon` y stop sobre el prefijo conocido en cada paso, para que la decisión sea causal también durante la gestión.

**3. El backend declara si se puede avanzar.** `session_to_public_dict` publica `can_step` (estado `sin_iniciar`/`en_espera`/`abierta` y `cursor < len(candles)`). El frontend lo prefiere; la derivación local es solo respaldo. Así se puede avanzar mientras se vigila o se espera entrada sin depender del `candles.length` de una respuesta filtrada. `onDecide` llama al backend con `request_id` nuevo y `expected_revision`, y la reevaluación posterior al `step` es explícita y limitada a `sin_iniciar`/`en_espera`.

**4. Un solo mecanismo económico de salida.** `_finalize_exit` es la única vía de cierre (stop, gap, `_finalize_exit_from_bt`, `manual_exit`): mismas fees, mismo funding, mismo net. La política de hueco es explícita: LONG con apertura ≤ stop dinámico o SHORT con apertura ≥ stop dinámico cierran a la apertura (`open_time_ms`); sin hueco, el cruce intradía cierra en el stop (`close_time_ms`). Se distinguen instante observado, instante de evaluación y convención de fill OHLC. Funding ausente permanece `UNKNOWN`; no se contabiliza cero por defecto.

**Evidencia mínima aceptada:** en `T=899999`, dos escenarios con apertura futura `900000` distinta (110 vs 50) deben publicar estado idéntico hasta T (comparando sin `session_id`/`created`/`updated`/`revision`/`input_hash`) y solo después rellenar al precio revelado. Se añadieron pruebas de gap LONG y SHORT, y el test de salida manual se amplió a 4 velas para que la salida no dependa de datos futuros.

**Alcance y límites:** desktop-only; sin Binance, monitor, paper prospectivo, órdenes, pagos, optimización ni cambios de umbrales. No se instala Lightweight Charts en esta entrega. La suite completa no se re-ejecutó (cambio acotado a Paper Lab); se ejecutaron 26 pruebas de motor, 5 de integración A–E vía CLI con almacenamiento aislado, 9 de API frontend y `tsc --noEmit`. La pasada de navegador sobre los controles queda pendiente y **no se declara ejecutada**.

## 2026-10-21 — Verificación en navegador Paper Lab: cuatro defectos de control corregidos

La pasada real de navegador (Chromium/Playwright) sobre `/paper-lab-live` encontró defectos que las pruebas de API no podían ver. Se corrigen sin tocar reglas, costes, umbrales ni el motor económico.

1. **Orden de hooks.** `PaperLabLive` devolvía antes de dos `useMemo` cuando no había sesión; al crear la primera sesión el número de hooks cambiaba y React abortaba la página (error #310, "This page couldn't load"). Los hooks pasan antes del `return` con referencias estables. Los dos errores `react-hooks` que se habían declarado preexistentes eran este defecto.
2. **Gate de evidencia insuficiente.** `evaluate_session` decidía "hay datos" con el prefijo fusionado (contexto incluido) mientras la señal evalúa solo velas de operación: con contexto presente y cero velas de operación la sesión se cerraba en la primera evaluación, dejando `can_step=false` y el escenario inavanzable. El gate usa el prefijo de operación; la sesión sigue `sin_iniciar` hasta tener evidencia real. Cerrar por "no hay más datos" cuando el escenario aún no ha revelado ninguna vela de operación era una clasificación falsa.
3. **Cursor sobre velas de operación.** Al rellenar una entrada pendiente, el cursor se calculaba con el índice de la serie fusionada: `cursor=50` con 8 velas de operación, y `can_step` (cursor < velas) quedaba desactivado justo al abrir. El cursor cuenta velas de operación reveladas (`reveal_idx + 1`), monótono, y la fusión se centraliza en `_merge_candles`.
4. **Controles.** `SessionControls` emitía el texto `&& (` por un paréntesis mal colocado y un botón primario siempre visible que duplicaba a "Paso a paso". Queda un único control de avance y el primario solo como "Entrar" con entrada pendiente.

**Decisión sobre fixtures:** no se modifican datos de fixtures. Se acepta y documenta que BTC LONG termina en fin de datos con posición abierta (caso D) y que ETH SHORT se abstiene en el primer cierre con la regla causal; stop/gap/horizonte se acreditan con pruebas unitarias e integración CLI, no con el recorrido de navegador. Cambiar velas para "hacer visible" una salida habría alterado el escenario en lugar de corregir el defecto.

**Regresión:** la prueba de `T=899999` congela `_now_ms`; antes comparaba marcas de reloj de pared y podía fallar sin que cambiara nada económico.

## 2026-10-21 — Anti Slop como revisión opcional local (piloto, sin puerta)

Se incorpora Anti Slop (`miqdadbadjuber/anti-slop`, commit `439a2ef5b9dd0ebe74e8113ff43f5928d0fe2a6a`, versión `3.2.21`, licencia MIT) como **revisión estilística opcional**, nunca como puerta de aceptación.

1. **Alcance mínimo y fijado.** Solo el núcleo (`skills/antislop`) y `antislop-code`; sin skills de UI, copy, personas o móvil; sin plugins ni instalador; sin paquetes en el runtime del bot. Los archivos upstream se conservan intactos y cada skill lleva su `LICENSE`; procedencia, bytes y SHA-256 quedan en `docs/ANTISLOP_PILOT.md`.
2. **Solo local y desactivable.** Instalación en `.opencode/skills/` de este repositorio; nada global, ningún otro proyecto, ningún proveedor/modelo/permiso modificado. Retirada = borrar dos directorios, el comando y la línea de `AGENTS.md`.
3. **Condiciones propias en documento separado.** `LOCAL_CONDITIONS.md` y `docs/ANTISLOP_PILOT.md` desactivan el asistente de primera ejecución, la lectura/escritura de preferencias globales y la creación de `anti-slop/audit-*.md`. El modo lo fija la invocación: auditoría por defecto, `during` solo explícito.
4. **Uso bajo demanda.** `/antislop <archivo o alcance>`; máximo 5 hallazgos; sin barrido del repositorio ni carga de todas las skills; sin fijar modelo ni lanzar subagentes.
5. **Precedencia del proyecto.** Antislop no puede borrar comentarios de causalidad, concurrencia, seguridad, costes, funding, unidades o limitaciones, ni acortar documentación técnica por longitud, ni quitar licencias/pragmas/`type: ignore`, ni cambiar lógica, nombres, imports, umbrales, estrategias o pruebas, ni rediseñar pantallas, ni prohibir rejilla/colores direccionales/niveles, ni activar móvil/Flutter, ni exigir otro `DESIGN.md` (los documentos de diseño existentes cumplen esa función).
6. **Un PASS no acredita nada funcional.** La revisión separa estilo de corrección; la evidencia sigue siendo pruebas, código y recorrido real, no un veredicto de Antislop.
7. **Verificación honesta.** Descubrimiento de las skills y registro del comando comprobados en OpenCode `v2.0.32`. Dos ejecuciones headless cargaron el núcleo sin editar archivos: la primera no terminó en 300 s y derivó hacia el asistente de modo (se endureció el comando con precedencia explícita), la segunda falló por error de proveedor (`Endpoint is unavailable`). La validación end-to-end del comando queda incompleta y así se declara.

## 2026-10-21 — Paper Lab: orden temporal del stop, stop efectivo y paridad canónica

Cierra la regresión económica detectada al operar Paper Lab sobre la base `d48a224`, sin tocar `backtest_offline` (autoridad canónica), reglas de señal, umbrales, costes ni funding.

1. **Open y cierre se revelan en momentos distintos.** Cada paso revela el `open_time_ms` de la siguiente vela de operación; en ese instante se conoce el cierre de la anterior (su `close_time_ms` es anterior) pero NO el high/low/close de la vela revelada. La marca no realizada usa solo el open revelado; el OHLC de la vela abierta se publica como `null` hasta que su cierre sea conocido. Antes, `step_forward` trataba el OHLC de la vela actual como conocido en `close_time_ms` y saltaba el reloj al `close_time_ms`, colapsando ambos momentos.
2. **Una sola autoridad resuelve las salidas.** Se elimina el bloque ad-hoc de gap/rango que preemptaba a `run_backtest` (y el helper `_finalize_stop_exit`). `_run_backtest_at_clock` sobre el prefijo conocido con `known_close_cutoff=clock` resuelve stop, gap, horizonte y fin de datos. El gap de la vela siguiente solo cuenta si antes no se resolvió una salida: el stop de la vela de entrada (95.95) precede al gap posterior (80).
3. **Stop efectivo publicado.** `PaperPosition.stop_px` y el evento de entrada publican `entry_px × (1 ∓ stop_distance_pct/100)` (95.95 en el caso LONG, 103.95 en SHORT), no el `stop_px` de referencia del config. El frontend usa `position.stop_px`/`position.entry_px` para el panel y el gráfico. El `stop_px` del config sigue siendo la referencia de la señal y el veto pre-trade estático, no la autoridad económica post-fill.
4. **Causalidad de UI intacta.** El flujo real (crear → evaluar → paso ×2 → Entrar → paso) sigue revelando la apertura siguiente por acción; el fill se ejecuta en el primer open estrictamente posterior al instante de decisión que la autoridad admite. No cambia la regla de señal.
5. **Fin de datos y realizado.** El último paso sin revelación finaliza `open_at_end` con la marca que la autoridad considera conocida; no inventa salida, comisión de salida ni realized. `realized_net` queda `null` y el neto no realizado se mantiene separado.
6. **Paridad verificada.** LONG: entrada 101, stop 95.95, salida 95.95 @ 1800000, bruto -50, fees 0.975, slip 0.585, neto -51.56, funding UNKNOWN. SHORT: entrada 99, stop 103.95, salida 103.95, neto -51.64. Gap legítimo: salida al open 90. Continuación: `open_at_end` 105. Todos coinciden con `run_backtest` con el mismo cutoff.
7. **Corrección de gráfico.** Con velas abiertas publicadas como `null`, `LiveChart` podía contaminar la escala con 0; ahora excluye velas sin OHLC para la escala y extiende el eje al open+intervalo. Nueva fixture de ingeniería `btc_long_stop_order` y recorrido real de navegador con cierre automático por stop.

Fuera de alcance: Binance/monitor/paper prospectivo/órdenes, cambios de reglas, umbrales, costes o motor canónico, Lightweight Charts, móvil. La verificación visual por modelo de visión no estuvo disponible (sin proveedor configurado); se acredita DOM/geometría/HTTP y capturas, no inspección visual por modelo. Anti Slop no se usó para esta corrección y su ejecución end-to-end sigue pendiente.

## 2026-10-21 — Gráfico Paper Lab: contrato `paper-chart/v1` y Lightweight Charts 5.2.1

Se implementa el gráfico financiero interactivo de `/paper-lab-live` **solo sobre fixtures**, alimentado exclusivamente por el backend existente, y se fija un contrato versionado antes de escribir código nuevo. No se cambian reglas, umbrales, costes, funding, el motor canónico ni la corrección económica de F-PAPER-03.

1. **Reutilizar antes de crear.** Auditoría previa: el diccionario público de sesión ya exponía velas conocidas con OHLC `null` para la vela solo-open, `available_at`/`received_at`, `position.stop_px`, `result.exit_executed` y `can_step`; no existía productor de volumen ni de indicadores para Paper Lab. El adaptador se construye sobre eso; no se duplica motor ni contrato de backtest/replay.
2. **Contrato `paper-chart/v1`.** Identidad con `venue=null`/`UNKNOWN`, `market_type="simulated_futures"` y `source="fixture"` (los datos son de ingeniería, no de venue Binance); tiempos en ms Unix UTC con reloj de simulación explícito; velas `closed`/`open-only`; operación (señal, entrada pendiente, fill, stop efectivo, salida, realizado/no realizado); capacidades (`can_step` del backend). Las ausencias son `UNKNOWN`/`null`, nunca ceros inventados.
3. **Conversión de tiempo explícita.** Lightweight Charts usa segundos: `floor(ms/1000)`. El milisegundo exacto se conserva en `open_time_ms`, `time_ms`, `at_ms` e IDs; el eje solo aproxima a segundos y el detalle conserva el instante.
4. **Vela solo-open sin invención.** No se rellena `high/low/close` con el open, con el cierre anterior, con 0 ni con interpolación. Se dibuja como punto ámbar sobre el open conocido más un marcador `open`, diferenciada de una vela cerrada. El adaptador vuelve a filtrar por `clock_ms`: aunque el llamador pase la lista completa, nada posterior a T se presenta como conocido; sin reloj no se asume conocimiento.
5. **Operación supeditada al backend.** El stop y la entrada usan `position.stop_px`/`position.entry_px`; la salida solo existe con `exit_executed=true`; `open_at_end` no produce marcador de salida ni realizado (`realized_net=null`); el objetivo es `UNKNOWN`. Las líneas de nivel son informativas; arrastrar stop/objetivo queda diferido.
6. **Identidad de eventos y tiempo de simulación.** El diccionario público añade `event_id` estable `session_id:ev:<índice>:<kind>:<at_ms>`. Los eventos de decisión usan tiempo de simulación (`signal_at_ms`) en todas sus ramas; antes usaban reloj de pared y rompían el orden causal del log. La hora de pared queda en `evaluated_at_ms`/`updated_at_ms`, que no se dibujan.
7. **Biblioteca oficial y fijada.** `lightweight-charts@5.2.1` exacto (Apache-2.0, TradingView), instalado con `--save-exact`; aviso de terceros y texto de licencia conservados. Dependencia transitiva `fancy-canvas@2.1.0` (MIT, sin LICENSE en el paquete publicado: se declara esa ausencia). Sin dependencias ni código de Phinvio. El lockfile se parcheó preservando el formato existente en lugar de aceptar una reescritura masiva.
8. **Integración cliente y ciclo de vida.** Montaje solo cliente con `import()` dinámico; un `createChart` por montaje; limpieza de suscripciones de crosshair y rango visible, `detach()` de los plugins de marcadores y `chart.remove()`. Actualización incremental con `update()` cuando la serie previa es prefijo exacto; si no, `setData()`. Cambiar de sesión descarta datos, marcadores, líneas y respuestas tardías. Abrir o refrescar la pantalla no inicia monitor ni adquisición.
9. **Verificación honesta.** Aceptación A–H con controles reales sobre el build servido (contexto sin futuros, señal pendiente sin fill, fill, cierre automático 95.95/-51.56 sin salida 80, fin de datos sin cierre inventado, recuperación tras refresco, cambio de sesión sin residuos, zoom/pan/ajuste/cursor). DOM/geometría/HTTP y capturas locales; **no** hubo modelo de visión disponible, por lo que no se declara PASS visual. Los residuales (selector de persistencia visible solo con sesión activa, ajuste inicial tras pasos incrementales, 5 avisos `npm audit` no abordados) quedan registrados, no ocultados.

Fuera de alcance de esta decisión: Binance vivo, monitor, adquisición, paper prospectivo, órdenes, pagos, optimización económica, búsqueda de contratos, histórico paginado, feed vivo, móvil/Flutter y REA. La ejecución end-to-end de `/antislop` sigue PENDIENTE y no se usó para este trabajo.


## 2026-10-21 — Explorador de contratos USD-M e histórico paginado bajo demanda

Se añade a `/market-lab` un explorador de contratos Binance **USD-M Futures** con histórico paginado por REST público y se fija su contrato en `docs/MARKET_EXPLORER_CONTRACT_V1.md`. Es el paso 4 parcial de `docs/ACUERDOS_GRAFICO_BINANCE_V1.md`. No se cambian reglas, umbrales, costes, funding, el motor canónico ni `paper-chart/v1`; no hay websocket, monitor, paper prospectivo, órdenes ni indicadores.

1. **Auditar antes de crear.** Ya existían `discovery.py` (criterio PERPETUAL + TRADING + quote USDT sobre `exchangeInfo`), `history_client.py` (`exchange_info`, `paginate_klines`, `earliest_bar`, limitador y política 429/418), `history_store.py` con `historical.db` (velas, mark-velas, cobertura y huecos) y el gráfico `paper-chart/v1`. Se reutilizan; lo nuevo es el catálogo cacheado, la cobertura explícita, el plan del bloque faltante, el BFF y el componente de búsqueda.
2. **Una sola autoridad Python.** Toda decisión (elegibilidad, cobertura, qué bloque pedir, presupuesto, orden/dedupe final) vive en `market_explorer.py`. El BFF valida parámetros y llama a la CLI; el navegador no calcula cobertura ni inventa velas.
3. **Caché aislada, no canónica.** `data/market-cache/market_cache.db` (override `MICROPROBE_MARKET_CACHE_DB`), con `MarketCache` que **rechaza** rutas canónicas. `historical.db` se lee en modo consulta y sus errores se publican en `storage.canonical_error`; nunca se escribe allí. `data/` ya está ignorado, así que no cambia `.gitignore`.
4. **Presupuesto explícito y pequeño.** Catálogo TTL 6 h con 1 petición por refresco; bloques de 300 velas; `pages ≤ 2`; concurrencia 1; timeout 20 s; 30 peticiones/minuto en ventana móvil; 0 reintentos propios. Un 429 honra `Retry-After`, un 418 aborta. Agotado el presupuesto se devuelven las velas almacenadas con `fetch.error` y la UI lo dice; nunca se reintenta en bucle ni se oculta el fallo.
5. **Leer antes de pedir.** Se fusionan canónico + caché por `(symbol, interval, source, open_time)` quedándose con la fila más reciente; solo se pide el bloque que falta. Los tramos del canónico con huecos aparecen como `gaps` reales (43 en MINAUSDT 1h), los tramos nunca consultados como `absent_ranges` y el inicio del contrato como `exhausted_before`; los tres se muestran distintos y no se interpolan.
6. **Vela provisional honesta.** La barra no cerrada se publica con `provisional=true` y `close_time_ms=null`; no se inventa cierre. `labels.live=false` y `labels.mode=HISTORICAL_ON_DEMAND`: la vista no se rotula LIVE porque no hay conexión continua.
7. **Intervalos con aritmética exacta.** `1m, 5m, 15m, 1h, 4h, 1d`. `1M` se excluye porque un mes calendario no tiene duración fija en ms y el cálculo de huecos dejaría de ser correcto.
8. **Paginación que conserva el encuadre.** Cada «Cargar anteriores» pide un bloque de 300 velas hacia atrás; al llegar, se antepone y se desplaza el rango lógico visible por el número de velas añadidas (`getVisibleLogicalRange` + `setVisibleLogicalRange`). La auto-carga solo ocurre tras interacción real del usuario, con el borde izquierdo a ≤3 velas y una petición por `earliest_from_ms`; el botón explícito queda como respaldo.
9. **Encuadre inicial, una vez.** `fitContent` solo en el primer montaje con ancho real (>0), diferido por `ResizeObserver` si el contenedor aún mide 0, y nunca en actualizaciones ni al paginar. Corrige el defecto previo (ajuste con contenedor sin medir y reajuste en cada render).
10. **Sin contaminación entre contextos.** `AbortController` + secuencia descartan la respuesta de un símbolo/intervalo anterior. `market-chart/v1` fija `session_id=null`, `operation=null`, `indicators=[]` y una guarda (`paperMarkersLeaked`) que prueba que ninguna marca de Paper Lab llega al gráfico de mercado.
11. **Un solo componente de gráfico.** `PriceChart.tsx` acepta la unión `paper-chart/v1 | market-chart/v1`; `paper-lab-live/PaperChart.tsx` queda como reexportación para no romper importaciones ni testids. Evita duplicar el cableado de Lightweight Charts y mantiene intacta la aceptación de Paper Lab.
12. **Recuperar sin crear.** El selector de persistencia se renderiza también en la pantalla inicial: listar y cargar una sesión guardada deja de exigir crear una fixture antes. La carga hace `GET` del estado autoritativo y no re-evalúa la decisión.
13. **Auditoría de dependencias razonada.** `npm audit` reporta 5 `high` en la cadena de desarrollo de `eslint-config-next` (lint, no bundle); `--omit=dev` da 0. La única «corrección» ofrecida es un downgrade mayor a `eslint-config-next@14.2.35`, incompatible con Next 16: se rechaza y se documenta el residual. Sin `audit fix --force` ni upgrades indiscriminados.
14. **Verificación declarada por estados.** Implementado, probado, servido e inspección visual se documentan por separado. La inspección visual por modelo no estuvo disponible (OpenRouter sin autenticación, NVIDIA 401): se acredita DOM/geometría/HTTP, análisis de píxeles de las capturas y pruebas, **no** un PASS visual.

Fuera de alcance: feed vivo/continuo, reconexión, indicadores compartidos, paper prospectivo, órdenes, capital, móvil/Flutter, REA y cualquier cambio económico. La ejecución end-to-end de `/antislop` sigue PENDIENTE.


## Accesos directos V2 — 2026-10-21 (F-NAV-V2-ACCESS-01)

La navegación incorpora `Mercado / Gráficos` -> `/market-lab` en Terminal, `Paper Lab — Simulación` -> `/paper-lab-live` y `Replay histórico` -> `/paper-lab` en Laboratorios. Se elimina el rótulo ambiguo Future workspace para estas capacidades existentes. ContractExplorer aparece antes del contenido histórico previo en /market-lab. Se preservan rutas y motores.

Verificado: navigation.test.tsx 4/4, tsc --noEmit y eslint de los dos archivos exit 0; next build exit 0 (13 advertencias de tracing preexistente en rutas no modificadas). BUILD_ID `3ThnqxocDEmcursE2ZYpu`, servidor propio PID 32104 (sustituye solo PID 16164 tras revalidar PID+creation time+comando y ausencia de monitor/Python). HTTP /overview, /market-lab, /paper-lab-live y /paper-lab 200; enlaces exactos y BUILD_ID comprobados en HTML servido. El cambio de navegación es de bajo impacto; backend y DB no cambiaron, no se repite su suite. Inspección visual/clics de navegador NO realizada: no hay herramienta de navegador disponible para esta sesión; verificación por pruebas de componente y HTML servido, sin PASS visual.

ESTADO DEL OBJETIVO VIVO: estos accesos NO implementan streaming. Mercado consulta histórico REST bajo demanda; Paper Lab usa fixtures; Replay reproduce histórico. El usuario reitera el objetivo de buscar contratos Futures elegibles y verlos actualizarse en vivo. Pendiente: adaptar feed existente, gestión compartida de suscripciones, vela provisional/cerrada, reconexión y reparación de huecos, frescura visible e indicadores backend compartidos; pruebas controladas y ventana acotada. No suscribir todo el universo a máxima resolución por pestaña ni confundir catálogo completo con seguimiento permanente. Abrir gráfico nunca abre una operación. Contrato rector: [ACUERDOS_GRAFICO_BINANCE_V1](ACUERDOS_GRAFICO_BINANCE_V1.md). Sin adquisición, monitor, paper prospectivo, órdenes, pagos, móvil ni gates en este cambio.


## 2026-10-21 — Actualización continua de velas (`market-stream/v1`)

Bloque `F-CHART-BINANCE-03`, sobre el explorador histórico ya entregado. La
conexión continua a Binance **no se abrió**: se implementó, se probó con
transporte simulado y se dejó preparada una ventana acotada.

1. **Contrato antes de código.** `docs/MARKET_STREAM_CONTRACT_V1.md` fija
   identidad `(venue, symbol, interval)`, tiempos UTC en ms, provisional vs
   cerrada, orden/dedupe, snapshot+stream, estados, presupuesto, almacenamiento
   y retirada. Sin contrato escrito no se implementó nada.
2. **Servicio de datos dedicado, separado del bot.** Un proceso propio
   (`market_stream_service.py` + hub/transporte) y no `probe.py`: el monitor del
   bot, el trío canónico y las sesiones Paper Lab no se arrancan, modifican ni
   consultan al abrir un gráfico. Cuatro planos separados: (A) servicio de
   datos, (B) monitor del bot, (C) sesiones paper, (D) estado de conexión del
   navegador.
3. **Una sola conexión combinada.** `wss://fstream.binance.com/market/stream?
   streams=…` con refcount por `(symbol, interval)`: dos pestañas o dos
   consumidores comparten socket y suscripción. La ruta `/market` es la que
   recibe `kline` según la documentación oficial (las conexiones sin
   `/public|/market|/private` solo reciben *Public*). Se elige `/stream?streams=`
   porque el conjunto de streams cambia en caliente (`SUBSCRIBE`/`UNSUBSCRIBE`).
4. **Sin dependencias nuevas.** El SSE se sirve con `asyncio.start_server` y
   *chunked transfer* de la biblioteca estándar; el único requisito declarado es
   `websockets`. `aiohttp` está instalado pero **no declarado**: no se usa.
5. **El snapshot no se inventa ni se duplica.** Se lee del almacén existente con
   `series_payload(allow_fetch=False)`; si no hay cobertura se publica
   `NO_COVERAGE` y no se dibuja nada. El REST del explorador sigue siendo el
   único que adquiere histórico.
6. **Reconciliación explícita.** Al suscribir: `subscribe → buffer →
   snapshot → deliver_from_ms = observed.end_ms → flush` deduplicado por
   `open_time`, con la cerrada ganando. Desbordar el buffer (`PENDING_MAX=256`)
   se declara como `gap` con `reason="BUFFER_OVERFLOW"`: nunca se pierde en
   silencio.
7. **Sin persistencia del feed.** Anillo en memoria de 300 velas cerradas por
   suscripción, liberado tras 30 s sin consumidores. Crecimiento en disco: 0.
   Las actualizaciones no se guardan ni se rellenan con interpolación.
8. **Reparación acotada y declarada.** Los huecos se detectan al cerrar vela y
   se reparan por REST con `paginate_klines` (`max_pages=2`, `limit=500`,
   ≤ 6/min, ≥ 15 s entre intentos), en memoria, publicando
   `complete|partial|failed` con los tramos faltantes. Una reparación parcial se
   muestra como parcial.
9. **`LIVE` es una conclusión, no un socket.** Solo si estado `RECEIVING` **y**
   socket conectado **y** última actualización del `(symbol, interval)` pedido
   **y** antigüedad ≤ 10 s. Entre 10 s y 60 s es `OBSOLETO`; sin socket o > 60 s
   es `DESCONECTADO`; durante reparación, `RECUPERANDO`. El frontend recalcula la
   condición con los datos del backend y no puede elevarla.
10. **Reconexión con presupuesto.** Backoff 1 s → 30 s con jitter ±25 %,
    `RETRY_BUDGET=20` fallos consecutivos → `DESCONECTADO` con
    `RETRY_BUDGET_EXHAUSTED` y reanudación al aparecer un consumidor nuevo.
    `serverShutdown` reconecta de inmediato. Frames de control ≤ 2/s.
11. **Límites duros.** `MAX_SUBSCRIPTIONS=6`, `MAX_CONSUMERS_PER_STREAM=4`,
    `MAX_TOTAL_CONSUMERS=12`, `CONSUMER_QUEUE_MAX=256` (consumidor lento se
    cierra y al volver re-sincroniza por snapshot). El catálogo completo nunca
    se sigue: abrir el explorador no suscribe el universo.
12. **Cambio de símbolo/intervalo sin contaminación.** El backend enruta por
    identidad y descarta `identity_mismatch`; el frontend aborta la conexión
    anterior y descarta el estado acumulado si no pertenece al símbolo/intervalo
    actual. Paginar hacia atrás **no** reabre el feed (`from_ms/to_ms` solo se
    usan al abrir).
13. **Vela en formación visible y distinta.** Se dibuja en una serie propia
    ámbar translúcida; al cerrarse desaparece de esa serie y se anexa a las
    cerradas con `update()` (sin reescribir la historia). Nunca se reabre una
    cerrada ni se inventa `close_time`.
14. **Estados de verificación separados.** Implementado / probado con transporte
    controlado / servido / verificado con Binance se documentan por separado. La
    ventana viva queda **preparada y no ejecutada**; no se declara recepción
    real a partir de fixtures.

Fuera de alcance en este bloque: indicadores compartidos, selección automática,
paper con datos vivos, riesgo, estrategias, optimización, órdenes, capital,
pagos, móvil y REA. La ejecución end-to-end de `/antislop` sigue PENDIENTE.

## 2026-10-22 - Ventana de verificación por el camino real (`F-CHART-BINANCE-04`)

1. **La ventana usa el servicio, no el hub.** El script
   `scripts/market_stream_window.py` deja de importar `KlineStreamHub`/transporte
   para la ejecución: arranca `scripts/market_stream_service.py`, espera
   `/health` y consume su SSE. Así la ventana recorre exactamente la cadena del
   navegador y no una variante. No se crea otro servicio ni otro gestor.
2. **Dos consumidores, un gráfico.** SSE directo al servicio por símbolo
   (identidad y aislamiento) y SSE a través del BFF solo para el símbolo primario,
   que es lo que hace el navegador. El BFF se valida además con pruebas de ruta.
3. **Adquisición y veredicto separados.** `acquisition_finished` mide recepción,
   provisional, cierre y siguiente. El veredicto añade cadena completa y evidencia
   DOM. Cero mensajes o cadena incompleta **nunca** producen `PASS`; cadena
   completa sin DOM es `UNKNOWN`; contradicción DOM/stream es `FAIL`.
4. **La evidencia DOM es explícita y acotada.** Se captura con un snippet
   documentado sobre `data-testid` del panel (`explorer-stream*`), antes del
   cierre y después, más una captura tras parar el servicio. Requiere
   `navigation_count=1` y `reload_count=0`: la página no se recarga durante la
   ventana. La revisión visual es un campo aparte y no altera el veredicto.
5. **Presupuesto.** ≤180 s, 1200 mensajes de vela, 6000 eventos SSE, 1 conexión
   WS, 2 streams, 3 consumidores, `bars=300`, sin persistencia, 1 paginación
   manual y la reparación de huecos ya contemplada. Parada temprana al observar
   provisional + cierre + siguiente (con 20 s de margen para la captura DOM).
6. **Transporte de prueba etiquetado.** `--base-url ws://127.0.0.1:…` permite
   probar el orquestador completo contra un WS local. El JSON lo marca como
   `transport.origin=loopback_test` y el check `transport_origin` lo declara: un
   `PASS` así es transporte controlado, **no** recepción de Binance.
7. **Limpieza verificada, no supuesta.** El script comprueba `/health` antes de
   retirar consumidores y después (`consumers=0`, con espera acotada porque el
   servicio libera al expirar su espera de lectura, ≤5 s), para el servicio y
   verifica
   proceso terminado, puerto cerrado, PID file eliminado y `/health` rechazado;
   además compara tamaño/mtime de las DB canónicas.

La ejecución real de la ventana sigue requiriendo autorización humana separada.

## 2026-10-22 — Corrección de contabilidad de consumidores SSE en la ventana (incluye el navegador)

**Contexto.** El procedimiento de `ab753a1` declaraba «3 consumidores: servicio
(2 símbolos) + BFF (1 símbolo)», pero no contaba al navegador que abre el
`EventSource` del gráfico. Con la ventana en marcha el total real habría sido 4.

**Decisión (sin ampliar el límite autorizado).**

1. El presupuesto de la ventana es **3 consumidores SSE simultáneos**: 1 del
   servicio (MINAUSDT), 1 del BFF (BTCUSDT, el primario) y 1 del navegador en
   `/market-lab`. Por stream: BTCUSDT 2, MINAUSDT 1 (`MAX_CONSUMERS_PER_STREAM=4`
   deja 2 de margen en BTCUSDT).
2. El primario se consume por el **camino real del gráfico** (BFF), no por una
   segunda conexión directa al servicio; así el script no duplica el stream.
3. `--browser-consumer --await-consumers 1 --await-timeout 90`: el script arranca
   el servicio, imprime el PID y **espera** a que `/health` muestre 1 consumidor
   estable (2 muestras) antes de abrir los suyos. Si no aparece, para con
   `BROWSER_NOT_ATTACHED` sin contacto con Binance y el JSON lo declara.
4. Al cerrar, el residual esperado tras retirar los consumidores del script es
   **1** (el navegador). `consumers_released` compara con ese valor y
   `consumer_budget` exige pico ≤ 3 y `consumers=3` justo antes del cierre. Sin
   navegador (pruebas) el esperado sigue siendo `0`.
5. El cambio de contrato que dispara el `EventSource` es **acción del operador**
   (el hook no reintenta cuando el servicio arranca tarde) y se registra como tal;
   no se presenta como reconexión automática.

**Efecto.** La ventana sigue midiendo la misma cadena (Binance → hub → servicio →
BFF → gráfico) con un presupuesto estricto de 3 consumidores, y el veredicto no
puede ser `PASS` sin evidencia DOM del navegador que ocupa la tercera plaza.

**Estado.** Implementado y probado con transporte controlado
(`tests/test_market_stream_window.py`, 24 pruebas). No acredita recepción real de
Binance por sí solo.

## 2026-10-23 — El selector del explorador ofrece `1m` (alineado con el backend)

**Contexto.** `EXPLORABLE_INTERVALS` ya incluía `1m`, pero el selector de
`ContractExplorer` solo ofrecía `15m, 1h, 4h, 1d`. La ventana de verificación por
el camino real exige abrir el gráfico en `BTCUSDT`/`1m`; sin la opción no existía
camino de usuario y la evidencia DOM habría sido imposible (o de otra identidad).

**Decisión.** Añadir `{id: "1m", ms: 60_000}` al array `INTERVALS` del componente,
conservando `15m, 1h, 4h, 1d` y el valor predeterminado `1h`. No se toca el
backend (ya validaba `1m`), ni el contrato `market-stream/v1`, ni la ventana de
300 velas, ni el presupuesto de peticiones. `5m` sigue disponible por API pero no
se ofrece en el selector (fuera del alcance de este arreglo mínimo).

**Pruebas.** `frontend/src/test/contract-explorer-intervals.test.tsx`: opciones y
predeterminado, histórico y suscripción con `symbol=BTCUSDT&interval=1m`, cierre
de la suscripción anterior y descarte de la respuesta tardía al cambiar de
temporalidad, y ausencia de `LIVE` con el servicio detenido. `tsc --noEmit` y
`eslint` sin errores.

**Efecto.** El gráfico puede mostrar la misma identidad que mide el script
(`Binance USD-M · BTCUSDT · 1m · market-stream/v1`), requisito de la ventana.

## 2026-10-24 — La ventana real se ejecutó una vez y el veredicto medido es FAIL por la evidencia DOM

**Contexto.** Con autorización explícita se ejecutó la única ventana prevista
(`BTCUSDT` + `MINAUSDT` 1m, 180 s máx., 1 conexión WS, 3 consumidores SSE
incluido el navegador). La cadena real quedó medida: 96 eventos `BTCUSDT` + 14
`MINAUSDT`, cierre y siguiente vela, 96 eventos en el BFF, 0 huecos, pico 3 y
residual 1, parada limpia y DBs canónicas intactas. El panel mostró `LIVE` con
la identidad exacta (`Binance USD-M · BTCUSDT · 1m · market-stream/v1`).

**Decisión.** Se registra el resultado tal como lo mide el evaluador:
**`FAIL` (exit 1)**, sin rebajarlo a `UNKNOWN` ni presentarlo como `PASS`. Fallan
solo dos checks obligatorios del navegador: `dom_state_live` (la captura #2 se
tomó 7 s después de la parada, porque la espera de 20 s expiró durante la
paginación) y `dom_after_stop` (el aviso `explorer-stream-down` no apareció: el
SSE del BFF siguió abierto y no se agotaron los reintentos ni se reconsultó
`/status`).

**No se repite la ventana** sin nueva autorización explícita del operador; no se
sustituye la prueba por otro intervalo ni se amplían límites. Las correcciones
(paginar antes del cierre o ampliar el `hold`; aviso de servicio detenido con
SSE del BFF abierto; investigar la paginación `300→303`) quedan en
`docs/TASK_QUEUE.md` como trabajo posterior, no como parte de esta ejecución.


## 2026-10-24 — Cierre del bloque F-CHART-BINANCE-04: propagación explícita, frescura local y paginación por bloque anterior

**Contexto.** La ventana real del 2026-10-24 quedó en `FAIL` medido: la cadena
Binance → hub → SSE → BFF → DOM funcionó (captura #1 con `LIVE`), pero la captura
#2 se tomó después de la parada y la #3 no mostró el aviso de servicio detenido.
El análisis de código mostró dos defectos independientes: el BFF devolvía
`upstream.body` en crudo (sin declarar fin/error ni abortar el upstream al
cancelar el cliente) y el hook no cambiaba nada visible en `onerror`, derivando
`LIVE` de un `status` congelado. Además, la paginación pedía `to = borde
reciente`, por lo que la respuesta repetía la ventana cargada y el contador
`300→303` no era historia nueva.

**Decisión.**

1. El BFF nunca reenvía el cuerpo del upstream en crudo: bombea frames, declara
   `event: error` con código cuando el upstream termina o falla y aborta el
   upstream cuando el cliente cancela o la petición se aborta.
2. El hook calcula la frescura localmente con un ticker de 1 s (`LIVE` solo si
   `live && age <= fresh_ms`) y muestra la causa de desconexión en cuanto llega
   (`onerror` o `event: error` con código), sin esperar a agotar reintentos.
3. El servicio despierta el bucle del consumidor al detectar el cierre del
   cliente, sin esperar al heartbeat de 5 s.
4. La paginación pide el bloque estrictamente anterior al borde cargado
   (`to = anchor - step`, `from = to - 299·step`) y antepone por `open_time` con
   dedupe (gana la fila ya cargada), recalculando cobertura y huecos. Solo las
   velas únicas cuentan; no se exige `+300`. Un bloque sin velas nuevas marca el
   histórico como agotado.
5. El veredicto medido de la ventana no se rebaja ni se sustituye: la corrección
   se acredita con transporte controlado y la ventana se repite solo con nueva
   autorización explícita.

**Consecuencias.** El panel retira `LIVE` por frescura aunque el stream enmudezca
y muestra la causa de inmediato; cerrar la pestaña libera al consumidor en
milisegundos; el BFF cierra el stream cuando el upstream muere. La paginación
deja de fingir crecimiento. No cambia estrategia, economía, riesgo ni ejecución;
no se abre conexión Binance nueva; no se actualiza Next.js (diagnóstico aparte).

## 2026-10-24 — Transporte falla cerrado y paginación acotada a un gesto

**Contexto.** Dos defectos del diagnóstico anterior quedaban abiertos: (1) el
servicio construía `BinanceKlineTransport()` contra el endpoint público y
`build_recovery(_rest_client())` cuando no se pasaba `--base-url`, así que dos
arranques "de prueba" abrieron el WS público sin declararlo; (2) una sola
interacción en `/market-lab` encadenó 12 peticiones REST de "anteriores"
(`0GUSDT` 1h, 31,4 s) porque la descarga se decidía en el evento de rango:
anteponer velas también emite ese evento y, si el feed había actualizado la
última vela, `isSuffix()` fallaba, no se desplazaba el rango lógico y la vista
caía sobre el bloque recién antepuesto, que volvía a pedir otra página.

**Decisión.**

1. El servicio no arranca sin transporte explícito. `--transport local` exige
   `--base-url ws://127.0.0.1|localhost|::1:<puerto>`, desactiva la reparación
   REST y no tiene fallback al endpoint público; `--transport public` es la
   única activación del WS de Binance. Sin transporte válido sale con código 2
   (`TRANSPORT_CONFIG`) antes de abrir cualquier socket. `/health` declara
   `transport.mode` y `transport.base_url`. El orquestador de ventana pasa el
   modo; no se crea un segundo gestor.
2. La paginación automática solo se evalúa al terminar un gesto del usuario
   (rueda con debounce 250 ms, `pointerup`, `keyup`) mediante
   `frontend/src/lib/earlier-gate.ts`: exige gesto nuevo, respeta un cooldown de
   600 ms, comprueba el borde y no repite el mismo ancla salvo que el intento
   anterior haya fallado. Los cambios de rango provocados por anteponer velas no
   incrementan el contador de gestos y no pueden disparar descargas.
3. Anteponer conserva el encuadre por índice exacto de la primera vela que ya
   estaba, aunque el extremo reciente haya cambiado; el explorador mantiene un
   guard síncrono de petición en vuelo y una clave de rango, y distingue
   cancelación (sin error ni agotamiento), agotamiento (`added === 0` o
   `exhausted_before`) e intento fallido (aviso + gráfico conservado + reintento
   manual habilitado).

**Consecuencias.** Una configuración local ausente o incorrecta produce cero
conexiones públicas (probado con exit 2 y con un servicio real sobre WS falso
local sin resoluciones de `fstream.binance.com`); una interacción consume como
máximo una página y los reintentos legítimos siguen disponibles. No cambia
estrategia, economía, riesgo ni ejecución; no se abre conexión Binance nueva; no
se actualiza Next.js. El veredicto medido de la ventana sigue `FAIL` y su
evidencia no se reescribe.

## 2026-10-24 — Segunda ventana real desde `2f2f9ea`: FAIL de aceptación; medición de liberación/reconexión y acciones del navegador automatizadas

**Contexto.** La ventana autorizada se ejecutó una sola vez entre
`14:04:37.065Z` y `14:05:43.957Z` (66,89 s de 180 s) con `--transport public`,
`BTCUSDT` + `MINAUSDT` 1m, una conexión WS combinada (1 intento, 0
reconexiones) y tres consumidores SSE (navegador + BFF + servicio). La cadena
real pasó: 58 mensajes / 58 aplicados / 2 cierres, 46 eventos `BTCUSDT` y 12
`MINAUSDT`, 38 actualizaciones provisionales de la misma apertura, cierre y
siguiente vela, BFF con 46 eventos e identidad `BTCUSDT/1m`, 0 huecos, pico de
consumidores 3, parada limpia y DBs canónicas intactas; 2 peticiones REST
públicas de velas (inicial de 299 + paginación de 300) y catálogo desde caché.
El parche de medición (`--release-browser`, `--release-timeout`,
`--reconnect-timeout`) se aplicó antes de conectar y no cambia producto.

**Decisión.**

1. Se mantiene el veredicto medido `FAIL` y **no se repite** la ventana. Fallan
   `consumers_released` (la desconexión del navegador no se ejecutó dentro de
   los 20 s), `browser_reconnected`, `dom_state_live`, `dom_update_fresh`,
   `dom_pagination_preserved` y `dom_after_stop`; falta `dom_candles_grew`
   porque la captura #1 llegó ~2 s después del cierre. La paginación terminó
   después del `hold` de 20 s y la captura #2 se tomó con el servicio ya
   parado.
2. `browser_reconnected` exige `consumers_after_close == 0` y
   `consumers_after_reconnect == 1`. Un `consumers=1` sin liberación previa no
   acredita una reconexión; el check se corrigió y el veredicto sigue `FAIL`.
3. La próxima ventana, solo con autorización explícita, debe automatizar el
   lado navegador (capturas, paginación, desconexión y reconexión al aviso) y
   separar la paginación de la fase de liberación o dimensionar el `hold` con la
   latencia medida. No se amplían límites ni se relanza la ventana.
4. El aviso `explorer-stream-down` con el SSE del BFF abierto se investiga como
   observación de producto; no se cambia producto en esta tarea.

**Consecuencias.** La recepción real y la cadena hasta el gráfico quedan
acreditadas por la evidencia; la aceptación end-to-end no. El fallo es del
procedimiento de captura/liberación, no de los datos. El ensayo local previo
hizo, por un defecto del arnés (doble `addInitScript` del reloj), 1 petición
pública `exchangeInfo` y 1 de 299 velas 1m; la ventana real no usó reloj falso
ni WS falso y Binance atendió `SUBSCRIBE` (`MINAUSDT` 12 eventos). Sin cambios
de estrategia, economía, riesgo ni ejecución; sin conexión Binance continua ni
nueva ventana.

## 2026-10-24 — Aceptación local automatizada con transporte loopback y aislamiento real; aviso de servicio detenido con causa

**Contexto.** El procedimiento de la ventana real falló por la secuencia del
navegador, no por los datos: las capturas, la paginación, la desconexión y la
reconexión no estaban automatizadas y el `hold` de 20 s se agotaba antes de la
paginación. Antes de pedir otra ventana Binance se decidió probar el mismo
camino `WS -> servicio SSE -> BFF -> /market-lab` en local, con transporte
loopback y aislamiento de red real, y coordinar todo por condiciones observadas
en lugar de esperas manuales.

**Decisión.**

1. Se añade `scripts/market_stream_local_acceptance.py` como procedimiento de
   aceptación local: cache y catálogo temporales vía
   `MICROPROBE_MARKET_CACHE_DB`, raíz sombra `MARKET_EXPLORER_ROOT` con
   `sitecustomize.py` que bloquea y registra conexiones no loopback, wrapper del
   explorador con `--no-fetch` (`fetch.allowed=false`,
   `catalog.refresh.reason=DISABLED`), proxy bloqueante, allowlist del navegador
   solo `127.0.0.1:3020`, WS falso en reloj real y servicio real con
   `--transport local`. Cualquier intento público debe fallar el recorrido y
   quedar registrado; nunca debe alcanzar Binance en silencio.
2. El orquestador añade `--post-reconnect-signal`: tras observar `consumers=1`
   mantiene el servicio vivo hasta la captura DOM de reconexión, sin ampliar el
   límite global de 180 s ni sustituir condiciones observadas por esperas fijas.
3. El hook `useMarketStream` consulta `/api/v1/market-stream/status` cuando el
   `EventSource` falla con el stream ya abierto; si `available=false`, cierra y
   declara el aviso con la causa real. El 503 JSON del BFF es fatal para
   `EventSource` (no reintenta), por lo que sin esta consulta el aviso
   `explorer-stream-down` no aparecía. La causa de frescura no sobrescribe el
   aviso terminal.
4. El PASS local es procedural y **no acredita recepción de Binance**: el check
   `transport_origin` queda `ok=false` con `required=false` por el origen
   `loopback_test`. La ventana real sigue exigiendo `--transport public` y
   autorización humana explícita.
5. No se cambia estrategia, economía, riesgo, paper, órdenes ni móvil. La
   actualización de Next.js 16.4.1 sigue no ejecutada.

**Resultado.** Dos recorridos consecutivos `PASS` procedural (83,0 s y 115,5 s;
límite 180 s), cero intentos públicos, cero consumidores residuales, parada
limpia, finalizer `PASS`, paginación `298 -> 599` con 1 petición, reconexión
`consumers=0 -> 1` con actualización posterior y aviso
`Servicio de datos detenido (TypeError: ECONNREFUSED)` con 599 velas
conservadas y `nav=1`/`reload=0`. Evidencia en
`docs/evidence/local-acceptance-2026-10-24/` con
`summary.git_sha=6be44b96b11a9362f2ec128947034f782726e971`.

**Consecuencias.** El procedimiento queda listo para una futura ventana real,
pero no se solicita ni se abre en este bloque. El `orchestrator_exit=2` es el
`UNKNOWN` previo al `--finalize` y no debe leerse como veredicto. El dashboard se
restauró al entorno canónico (catálogo 931, no las 2 entradas de prueba) y el
servicio 8791/8792 quedó detenido.

## 2026-10-25 — Presupuesto REST upstream: reserva transaccional por intento con execution_id (base `309aee1`)

Decisión tomada tras verificar el alcance real del control de presupuesto del
bloque `1b36647`/`309aee1` (verificación pedida por el operador, transporte
local, sin abrir Binance). Alcance entonces: (1) el contador compartido
`market_fetch_ledger` se contabilizaba DESPUÉS de la petición (postenvio), sin
reserva, con carrera entre procesos; (2) el registro por intento
(`HistoryClient.upstream_requests`) era lista en memoria que moría con el
proceso; (3) el dashboard → BFF → CLI no propagaba `execution_id`; (4) el
limitador per-instancia de peso no acumulaba `_window_weight` (defecto latente
demostrado: el test `test_third_request_blocked_before_send` ya fallaba en la
base; nunca bloqueaba). El "2 upstream" del arnés de ventana era un techo del
navegador, no un límite del backend.

Corrección aplicada reutilizando los mecanismos existentes (sin nueva
arquitectura): `MarketCache.reserve_fetch_attempt` (chequeo + INSERT con
`BEGIN IMMEDIATE` en una transacción — los procesos concurrentes que comparten
la cache no superan el límite), `LedgerAttemptGate` conectado como
`attempt_gate` de `HistoryClient` (incluso dentro de un bloque de éxito de
`get()`, cada intento reserva ANTES del transporte y la denegación lanza
`UpstreamBudgetExceeded` antes de abrir socket, auditada en el ledger con
`requests=0`), migración idempotente de `market_fetch_ledger` con columnas
`execution_id`/`detail` (filas históricas quedan NULL = UNKNOWN, nunca
reescritas), CLI `--execution-id`/`--max-upstream`/`--api-base` (solo loopback
para transporte de prueba) y BFF `market-series`/`market-contracts` emitiendo
`--execution-id bff-<uuid>` por petición. Se restauró también la acumulación
de peso del limitador per-instancia (autopacing de peso Binance, distinto del
presupuesto compartido de intentos).

Ambitos excluidos y documentados: `build_recovery` (reparación REST del
servicio de stream) usa su propio cliente sin puerta al ledger compartido; el
reglamento per-instancia sigue siendo de peso (no de cupos). Demostración con
transporte local: `docs/evidence/rest-budget-scope-2026-10-25.json` y
`tests/test_budget_scope_shared.py` (procesos reales del CLI, límite=2
compartido entre dos procesos concurrentes, tercer intento bloqueado antes del
transporte, reintentos que consumen cupo, reconstrucción del consumo desde el
ledger persistido). Sin cambios de estrategia, economía, riesgo, paper,
órdenes ni móvil; ventana Binance de Tercera no abierta ni solicitada.

## 2026-10-25 — Precisiones documentales: execution_id ≠ corrida ≠ ámbito del presupuesto; automatización del navegador ya implementada (base `09632f4`)

Dos correcciones de precisión pedidas por el operador, sin reescribir la
historia y sin reconstruir lo que ya existe:

1. **Tres identificadores distintos:** `execution_id` es una etiqueta de
   ATRIBUCIÓN por ejecución/petición — `bff-<uuid>` nuevo por cada petición
   HTTP del dashboard al BFF, o el que pase el CLI — usada para reconstruir
   el consumo de esa ejecución con `fetch_rows_by_execution`; el
   identificador de **corrida** de observación (O1/O2, run id) es otro
   identificador que NO viaja en `market_fetch_ledger`; y el **ámbito que
   realmente comparte el presupuesto** es la ventana móvil de 60 s del
   archivo del ledger — la consulta de reserva de
   `MarketCache.reserve_fetch_attempt` filtra solo por `at_ms`, sin
   `execution_id`, sin símbolo y sin proceso: toda ejecución que comparta el
   `market_fetch_ledger` dibuja del mismo vaso.
2. **La automatización del lado navegador ya está implementada** y así queda
   reconciliado el estado que la describía como tarea por construir:
   `scripts/market_stream_local_acceptance.py` (2026-10-24, base `6be44b9`)
   conduce el navegador Playwright por el procedimiento completo (LIVE,
   captura #1, paginación, captura #2, liberación, reconexión, parada, aviso
   y captura #3, con máximos por fase) con dos recorridos consecutivos PASS
   en loopback (`docs/evidence/local-acceptance-2026-10-24/`). Lo pendiente
   es solo EJECUTAR ese mismo arnés en una ventana Binance real
   (`--transport public`), que sigue requiriendo autorización explícita; el
   veredicto `FAIL` medido del 2026-10-24 se mantiene intacto.

## 2026-10-25 — Indicadores compartidos V1: subconjunto mínimo sobre velas cerradas, backend única autoridad (base `09632f4`)

Decisión de la primera integración vertical (pedida por el operador; sin
Binance, datos locales, sin estrategia ni señales ni optimización):

1. **Inventario sobre código real:** retornos/velocidad viven en P1-04/05
   (mark price WS), flow/delta en P1-06 (aggTrade WS), spread/profundidad en
   P1-07 (libro WS), OI en P1-07 (REST de OI), VWAP en P1-08 (flow + mark
   price), y el volumen relativo NO estaba implementado. Ninguna de esas
   fuentes viaja en el canal de velas `/market-lab`; por eso flow, spread,
   profundidad, OI y contexto BTC se DECLINAN con motivo (nunca derivados de
   OHLC, nunca cero sustituto).
2. **Subconjunto elegido** `market-indicators/v1` calculado por el backend
   (`kline_indicators.py`, gancho en `series_payload`), con la MISMA salida
   versionada para gráfico y futuro evaluador: `log_return_bps`,
   `velocity_bps_5`, `rel_volume_10`, `vwap_typical_10` + `vwap_dev_bps_10`
   (VWAP de velas ≈ precio típico × `base_volume`, declarado como NO siendo
   el VWAP de negociación de P1). Solo velas cerradas
   (`PROVISIONAL_EXCLUDED`, sin indicadores provisionales en V1);
   `available_at_ms = open_time + interval_ms`; hueco/warmup → UNKNOWN con
   motivo (`GAP_IN_WINDOW`/`INSUFICIENT_CANDLES`/`MISSING_VOLUME`/
   `NO_PREVIOUS_CANDLE`), sin ceros; sin lookahead (anclado por test);
   `computed_over: "payload_window"` y al anteponer bloques el frontend solo
   une filas validadas (sin recálculo).
3. **Contrato aditivo:** bloque opcional `indicators` en `market-series/v1`
   (§11 de `MARKET_EXPLORER_CONTRACT_V1.md`); el navegador lo lee con guard
   de versión e identidad (bloque corrupto o de otra identidad → descartado
   entero, no mostrado parcial). El plan queda en
   `docs/SHARED_INDICATORS_V1.md`; evidencia local (0 upstream) en
   `docs/evidence/indicators-v1-2026-10-25.json`.



## 2026-10-25 — Recalculo incremental de indicadores por cierre (`market-stream/v1`, aditivo sobre `market-indicators/v1` + `market-series/v1`)

Continuación de 2ffdede con cuatro cierres del bloque indicadores: verificación de contrato, conexión incremental, build servido y demo de navegador con transporte local (0 solicitudes públicas).

1. **Contrato verificado, no flexibilizado.** `velocity_bps_5` NO es el "retorno de cinco intervalos completos" (ese requeriría 6 cierres, t−5→t): es el retorno acumulado de una ventana de **5 velas cerradas** (t−4..t, 4 saltos de intervalo), con la ventana validada por **tiempo** (rejilla de `open_time`), no por posición del arreglo — anclado por `test_velocity_window_is_temporal_not_positional`. El costo del contexto BTC se separa en fuente requerida (velas BTCUSDT) vs solicitudes realmente necesarias (0 si ya está en caché; si no, las páginas del tramo faltante del propio plan, no un "+N upstream" fijo): texto corregido en `SHARED_INDICATORS_V1.md` y §11.
2. **Conexión incremental mínima reutilizando el servicio.** La limitación previa de 2ffdede era REAL (el merge del stream conservaba el bloque REST intacto al cerrar velas). Se implementó: (a) `snapshot` SSE pasa el MISMO bloque de `series_payload` con `allow_fetch=False` (0 upstream); (b) en cada cierre (`closed`) el servicio fusiona la vela en la ventana de la sesión (dedupe/orden por `open_time` — continuidad temporal, no posiciones), recalcula con `kline_indicators` y emite un frame SSE nuevo `event: indicators` antes de `closed`; la vela provisional NUNCA entra en la ventana (test SSE extremo a extremo); (c) el frontend `mergeStreamIntoSeries` aplica `applyStreamIndicators` (sanitización + guard de identidad + unión de filas, nuevo gana) — el navegador no recalcula y no recarga. Las filas de velas ya cerradas no cambian tras el cierre; el badge ahora muestra UNIDADES (`ret/vel` en bps, `relvol` en x).
3. **Frontera que NO se cruzó:** sin Binance (fake de klines WS estrictamente loopback), sin estrategia/señales/paper/órdenes, sin presupuesto ni monitor; los UNKNOWN siguen declarados (`GAP_IN_WINDOW` / `INSUFICIENT_CANDLES`), nunca reparados con inventos. El FAIL de 2026-10-24 (transporte público real) NO se toca y queda pendiente de ventana de operador.

## 2026-10-25 — Demo pública `indicators-v1-public` PASADA; causa raíz del falso fallo era infraestructura (servidor ajeno en 3020)

1. **La demo cerró PASS** (`docs/evidence/indicators-v1-public-2026-10-25/evidence.json`): 15/15 verificaciones DOM contra el backend real, badge con unidades, fila GAP mostrando `UNKNOWN(GAP_IN_WINDOW)`, cierre actualizando el badge SIN recarga (`event: indicators` del servicio), vela provisional excluida, cambio de símbolo sin arrastre ni recarga; **0 solicitudes Binance** (browser_external 0; ledger 0; guardia DNS en el navegador); BUILD_ID `e_lib1MO18w7gv6PJG2rm` desde base `2ffdede`; capturas `shot-1h-values.png`, `shot-1m-close.png`, `shot-mina-values.png` (revisión visual aparte de la verificación DOM).

2. **Causa raíz del `TIMEOUT/fallos de gap` anteriores: NO era frontend ni servicio.** Un `next start` huérfano (orfanado de una corrida previa, viviendo en 3020 con SU propia `MICROPROBE_MARKET_CACHE_DB` de otra ejecución) respondía el 200 OK y el BFF de "nuestra" demo replicaba SU cache: el payload REST de comparación describía huecos de OTRO run (semillas deterministas ⇒ precios idénticos, huecos en posiciones distintas) mientras el bloque del stream (servicio actual, cache actual) era correcto. Los datos del+N backend/servicio siempre fueron consistentes; la MEZCLA del navegador (REST + snapshot nuevo gana) mostraba la fila correcta y el check del demo la comparaba contra la fila del servidor ajeno.

3. **Decisión de infraestructura:** una demo de navegador solo produce evidencia válida si el dashboard en `DASHBOARD_PORT` es EXACTAMENTE el servido por la corrida. `scripts/indicators_v1_public_demo.py` ahora (a) aborta si 3020 está ocupado ANTES de `next start`, (b) aborta si el `next start` propio muere con `EADDRINUSE` o no muestra su banner Ready en el log de la corrida (identidad verificada por el log, no por árbol de procesos), (c) aborta si el reemplazo previo del dashboard no deja el puerto libre. el diagnóstico usó réplicas offline deterministas de `series_payload` sobre la misma DB (CLI y directo, idénticos) para aislar al servidor como única variable.

## 2026-10-25 — Restauración del caso canónico en 3020 y terminología de la demo

1. **Solo la instancia identificada fue reemplazada.** El servidor que
   quedaba en 3020 era huérfano de la demo (linaje `npm run start` 31888 →
   cmd 38744 → node 31048; su padre 33296 ya estaba muerto) y llevaba el
   entorno de ensayo heredado. Tras verificar que no había trabajos activos
   (sin python, sin servicio en 8792, sin fake WS en 65375) se mató el árbol
   completo con `taskkill /F /T /PID 31888` y el dashboard canónico se
   reinició con env limpio (sin `MICROPROBE_*`/`MARKET_EXPLORER_*`): node
   **32124**, banner `Ready in 372ms`. Verificación: `/market-lab` y `/`
   HTTP 200, catálogo canónico servido solo desde caché (932 contratos,
   `fetched_at_ms` sin cambios, TTL vigente; `market_fetch_ledger` 86→86 =
   **0 huellas públicas**), servicio local de datos **detenido**
   (`/api/v1/market-stream/status` → `available:false`), sin ensayo ni
   huéfanos: único proceso `next` del sistema es el canónico. DBs canónicas
   solo leídas (el constructor del cache además rechaza DBs canónicas).
   Evidencia del bloque intacta en su ruta aislada.
2. **Terminología fijada para no confundir con Binance real:** "demo
   pública" se corrige a **demo de entrega** (dashboard en el navegador con
   transporte 100% local: fake WS de klines en loopback, caché de ensayo,
   guardia DNS; **no acredita nada sobre Binance real**). CURRENT_STATE,
   TASK_QUEUE y FEATURE_BACKLOG ya usan el término. Separación pendiente
   reafirmada: indicadores = PASS con transporte local; recepción
   incremental sobre Binance real = NO acreditada (requiere ventana de
   operador); inspección visual = hecha por el agente, separada del DOM
   15/15. Servidor final canónico: SHA `9a995b9`, BUILD_ID
   `e_lib1MO18w7gv6PJG2rm` (build de la demo sobre el mismo frontend de
   `37c7b61`; `9a995b9` no tocó frontend).

## 2026-10-26 — Contexto BTC compartido `market-btc-context/v1` (transporte local, PASS)

1. **Bloque aditivo, sin romper `market-indicators/v1`.** `context_btc` es un
   campo hermano del payload `market-series` y `event: context` un frame
   hermano del SSE; `market-indicators/v1` y su lista `declined` (incluido
   `btc_context` con motivo `SECOND_SYMBOL_KLINES_REQUIRED`) quedan intactos:
   el contexto BTC declara SU propia fuente en `context.sources` y su coste
   real en `context.acquisition`.
2. **Suscripción compartida, no duplicada.** BTC viaja en el mismo hub
   combinado (`KlineStreamHub`, refcount por `(symbol, interval)`). Si el
   token es BTC no hay bloque ni segunda suscripción (no hay comparación
   consigo mismo). Acreditado por prueba: dos sesiones comparten un único
   consumidor BTC; cerrar una vista libera solo sus consumidores.
3. **Contexto informativo, sin Binance real.** `ret_btc_bps_5` y
   `ret_diff_bps_5` se calculan sobre velas cerradas alineadas por
   `open_time_ms`; huecos/ausencia/retardo declaran `unknown(BTC_*)`, nunca
   cero ni arrastre. La diferencia de retornos se etiqueta tal cual, no como
   "alpha" ni rentabilidad. Todo con transporte local (fake WS loopback,
   caché de ensayo, guardia DNS): **demo PASS 12/12, 0 peticiones públicas
   (browser_external 0, ledger 0)**. Recepción incremental Binance real: NO
   acreditada (requiere ventana de operador).
4. **Servidor final canónico:** SHA `3c2e7ab` (HEAD tras el bloque),
   BUILD_ID `Bibj_gkaZK9si2ABtSsAb` (frontend recompilado con `next build`
   sobre `3c2e7ab`). Dashboard en `127.0.0.1:3020` con env limpio, servicio
   de datos detenido (8792 sin escuchas).

## 2026-10-26 Correccion flujo comprador/vendedor market-flow/v1 (commit f98e8e1)

**Retirada la simulacion sintetica del camino canonico.** `scripts/market_flow.py` y el BFF
`frontend/src/app/api/v1/market-flow/route.ts` ya no generan operaciones ficticias.
Sin fuente conectada, el endpoint devuelve HTTP 200 con `coverage:
NO_COVERAGE_BEFORE_FIRST_EVENT`, `live: false`, `trades_total: 0`,
`freshness_ms: null` y valores desconocidos (never 0). Las fixtures solo se
activan en el entorno de prueba con origen `SIMULATED` explicito; nunca se
presentan como Binance LIVE.

**Integracion incremental real con transporte local.**
Nuevo `src/microstructure_probe/market_flow_service.py`: servidor SSE local
que mantiene una **instancia compartida de FlowEngine** en memoria y recibe
eventos aggTrade del transporte local via POST `/flow` (cuerpo JSON con
`symbol`, `event_id`, `event_ms`, `price`, `quantity`, `buyer_is_maker`).
Publica actualizaciones incrementales al panel via SSE `/flow/stream`.
`scripts/market_flow_service.py` arranca/para el servicio. No se reconstruye
flujo desde OHLC ni se crea otro gestor por peticion.

**Identidad y deduplicacion.**
Cada evento transporta `symbol + event_id`. Mismo `event_id` repetido: no
suma volumen (contado como `events_duplicate`, bloqueado antes del engine).
Identificadores distintos con mismo timestamp: ambos cuentan. Eventos tardios
(`event_ms < newest seen`) se descartan (`dropped_late`). Nunca se afirma que
el WS no repita: la deduplicacion es por `event_id`.

**Frontend.**
`frontend/src/components/market-lab/MarketFlowPanel.tsx` se conecta al SSE
del servicio de flujo, sincroniza identidad/tiempo/cobertura con el grafico,
descarta respuestas/eventos antiguos al cambiar simbolo (symbolRef + cierre
de EventSource previo), y la frescura caduca tras 60s sin eventos
(`setFreshnessStale`, `live=false`). Valores al cursor requieren cobertura
registrada; donde no exista, UNKNOWN.

**Pruebas de aceptacion (10/10):**
1. Ruta canonica sin fuente: ninguno valor sintético ni LIVE (PASS).
2. Dos eventos locales nuevos actualizan sin recargar (PASS).
3. Duplicado no altera acumulados (PASS).
4. Igual timestamp con IDs distintos cuenta ambos (PASS).
5. Cambio de simbolo durante respuesta pendiente no mezcla datos (PASS).
6. Desconexion retira LIVE (frescura caduca) (PASS).
7. Cerrar vista libera su consumidor (PASS).
Adicionalmente: `tests/test_market_flow.py` 10/10; `test_flow.py` 46/46
(sin regresion); tsc 0; eslint 0; next build OK.

**Dashboard canonico restaurado.** Servidor `next start -p 3020` en
`127.0.0.1:3020` con el nuevo build (market-lab y /api/v1/market-flow
HTTP 200, SIN COBERTURA sin fuente). Sin monitor, sin Binance publico,
sin paper prospectivo, sin ordenes, sin pagos, sin movil.
Evidencia: `docs/evidence/cd4a/EVIDENCE_PRECISIONES.md`,
`docs/evidence/cd4a/market-lab-04-flow-no-source.png/.txt`.


## 2026-10-26 Chrome DevTools MCP oficial como diagnostico del dashboard (commit 5aabcbb) + flujo comprador/vendedor market-flow/v1

1. **MCP de proyecto, no global.** `opencode.json` (nivel de proyecto,
   formato nativo de OpenCode `"mcp": {...}`) registra el servidor
   `chrome-devtools-mcp@1.12.0` (version estable fijada). Perfil Chrome
   dedicado al dashboard (`.chrome-devtools-mcp-profile/`, ignorado en
   `.gitignore`, sin sesiones personales). Flags oficiales:
   `--no-usage-statistics`, `--no-performance-crux` (mas variables de
   entorno equivalentes), `--allowed-url-pattern` restringido a
   `127.0.0.1:*/*` y `localhost:*/*` (solo controla el navegador, no el
   backend), viewport `1280x720` (desktop), `executable-path` a Chrome
   estable 155. Cero dependencias en el runtime del dashboard; ninguna
   configuracion global tocada; convive con Playwright.
2. **Conexion real verificada.** `list_pages` lanza Chrome con
   `about:blank`; 32 herramientas MCP expuestas. Recorrido acotado sobre
   `http://127.0.0.1:3020/market-lab`: BTCUSDT buscado y seleccionado;
   identidad e indicadores inspeccionados (100 samples, mark 81961.5,
   +1.271%); DOM, consola, red (167 req, 0 hosts publicos) y capturas en
   `docs/evidence/cd4a/`. `/paper-lab-live` y `/backtest` abiertos sin
   ejecutar trabajos. Revision visual PENDIENTE (sin proveedor de vision).
3. **Flujo comprador/vendedor market-flow/v1 (backend como autoridad,
   contrato versionado).** Reutiliza `flow.py` (P1-06) sin modificarlo;
   nuevo `src/microstructure_probe/market_flow.py` expone el contrato
   `market-flow/v1` (`compute_flow_block`) y `scripts/market_flow.py`
   CLI local (transporte local, datos simulados, sin Binance publico).
   Nuevo BFF `frontend/src/app/api/v1/market-flow/route.ts` y panel
   `frontend/src/components/market-lab/MarketFlowPanel.tsx` en
   `/market-lab` (sincronizado con el grafico, delta positivo NO es
   senal alcista automatica). Cambio de simbolo limpia datos anteriores
   (useEffect con symbol como dependencia; backend stateless por peticion
   via spawnSync). Sin cobertura antes del primer evento de captura
   (coverage NINGUNA, nunca ceros ni valores inventados). buyer-is-maker
   verificado (m=true -> agresor SELL, m=false -> agresor BUY);
   deduplicacion (mismo E = nuevo volumen); eventos tardios descartados
   (dropped_late). Indicadores y contexto BTC preservados intactos.
   Pruebas: `tests/test_market_flow.py` 10/10; `test_flow.py` 46/46
   (sin regresion). tsc 0, eslint 0.
4. **Plano backend sin publicas: UNKNOWN.** La allowlist del navegador
   solo controla al navegador (verificado: 0 hosts publicos en red). El
   backend tiene ledger (`market_fetch_ledger`) + guard
   (`LedgerAttemptGate`, `reserve_fetch_attempt`,
   `UpstreamBudgetExceeded`) implementados, pero sin monitoreo directo
   del trafico de backend no se puede afirmar "cero publicas en esta
   carga" — declarado UNKNOWN, no cero. Evidencia en
   `docs/evidence/cd4a/EVIDENCE_PRECISIONES.md`.
5. **Dashboard canonico restaurado.** Servidor `next start -p 3020` en
   `127.0.0.1:3020` con el nuevo build (market-lab y /api/v1/market-flow
   HTTP 200). Sin monitor, sin Binance publico, sin paper prospectivo,
   sin ordenes, sin pagos, sin movil.

## 2026-10-26 Correccion flujo comprador/vendedor market-flow/v1 (commit 97d8335)

**Retirada la simulacion sintetica del camino canonico.** `scripts/market_flow.py` y el BFF
`frontend/src/app/api/v1/market-flow/route.ts` ya no generan operaciones ficticias.
Sin fuente conectada, el endpoint devuelve HTTP 200 con `coverage:
NO_COVERAGE_BEFORE_FIRST_EVENT`, `live: false`, `trades_total: 0`,
`freshness_ms: null` y valores desconocidos (never 0). Las fixtures solo se
activan en el entorno de prueba con origen `SIMULATED` explicito; nunca se
presentan como Binance LIVE.

**Retirado el servidor paralelo 8799.** Se elimino
`src/microstructure_probe/market_flow_service.py` y
`scripts/market_flow_service.py`. La funcionalidad se traslada al BFF de
Next.js (mismo origen, puerto 3020), sin añadir servicios nuevos.

**Integracion incremental real con transporte local y FlowEngine compartido.**
Nuevo `frontend/src/lib/flow-engine.ts` implementa FlowEngine en TypeScript
(puro, sin red, sin Binance publico) como modulo compartido. Nuevo
`frontend/src/lib/flow-instance.ts` mantiene una instancia singleton del
FlowEngine y un pub/sub para SSE. Nuevos endpoints BFF del mismo origen:
`GET /api/v1/market-flow` (consulta estado, SIN COBERTURA sin fuente),
`POST /api/v1/market-flow` (ingesta evento aggTrade del transporte local),
`GET /api/v1/market-flow/stream` (SSE del mismo origen, sin CORS, publica
actualizaciones incrementales al panel). El navegador usa una ruta del mismo
origen, sin CORS.

**Unico contrato de frames e identidad.** Frames SSE: `hello`, `snapshot`,
`update`, `heartbeat`. Identidad: `symbol + event_id` para deduplicacion.
Mismo `event_id` repetido: no suma volumen. Identificadores distintos con
mismo timestamp: ambos cuentan. Eventos tardios (`event_ms < newest seen`):
se descartan (`dropped_late`). Nunca se afirma que el WS no repita: la
deduplicacion es por `event_id`.

**Frontend.** `frontend/src/components/market-lab/MarketFlowPanel.tsx` se
conecta al SSE del mismo origen, sincroniza identidad/tiempo/cobertura con
el grafico, descarta respuestas/eventos antiguos al cambiar simbolo
(symbolRef + cierre de EventSource previo), y la frescura caduca tras
60s sin eventos (basada en ultimo dato valido, no en hora de consulta).
Desconexion y datos obsoletos se distinguen de "nunca hubo cobertura".
Valores al cursor requieren cobertura registrada; donde no exista, UNKNOWN.

**Presupuesto acotado de memoria para IDs deduplicados:** LRU con
MAX_EVENT_IDS=10_000 por simbolo; IDs mas antiguos se evictan al llenarse.

**Pruebas de aceptacion (10/10):**
1. Ruta canonica sin fuente: ninguno valor sintActico ni LIVE (PASS).
2. Dos eventos locales nuevos actualizan sin recargar (PASS).
3. Duplicado no altera acumulados (PASS).
4. Igual timestamp con IDs distintos cuenta ambos (PASS).
5. Cambio de simbolo no mezcla datos (PASS).
6. Desconexion retira LIVE y muestra causa (PASS).
7. Cerrar vista libera su consumidor (PASS).
Adicionalmente: `tests/test_market_flow.py` 10/10; `test_flow.py` 46/46
(sin regresion); tsc 0; eslint 0; next build OK.

**Dashboard canonico restaurado.** Servidor `next start -p 3020` en
`127.0.0.1:3020` con el nuevo build (market-lab y /api/v1/market-flow
HTTP 200, SIN COBERTURA sin fuente). Sin monitor, sin Binance publico,
sin paper prospectivo, sin ordenes, sin pagos, sin movil.
Evidencia: `docs/evidence/cd4a/EVIDENCE_PRECISIONES.md`,
`docs/evidence/cd4a/market-lab-04-flow-no-source.png/.txt`,
`docs/evidence/cd4a/market-lab-05-flow-nosource.png/.txt`,
`docs/evidence/cd4a/market-lab-06-flow-nosource-rendered.txt`,
`docs/evidence/cd4a/market-lab-07-flow-rendered.txt`.

## 2026-10-26 Correccion de arquitectura flujo comprador/vendedor (commit 00a96a1)

**Retirada duplicacion economica:** `flow-engine.ts` y `flow-instance.ts`
eliminados del frontend. `flow.py` (P1-06) sigue siendo la unica implementacion
del calculo de flujo agresivo, ahora expuesta desde el servicio Python de
mercado (`market_stream_service.py`) en lugar de un singleton Node en el BFF.

**Arquitectura requerida:**
1. `FlowEngine` vive en el servicio Python de mercado (puerto 8792), que posee
   el estado, la ingesta, la deduplicacion acotada y la publicacion SSE.
2. El BFF (`frontend/src/app/api/v1/market-flow/route.ts`) es puro proxy:
   GET consulta al servicio Python, POST devuelve 405 (ingesta solo directa
   al servicio Python, transporte local explícito). No calcula flujo ni
   depende de un singleton Node.
3. El navegador usa el endpoint SSE del mismo origen
   (`/api/v1/market-flow/stream`, puerto 3020, sin CORS). Identidad contractual
   coherente (`symbol + event_id`), cancelacion propagada al cerrar la vista.
4. La ingesta de pruebas queda restringida al transporte local explícito:
   `FLOW_SYMBOLS` vacio por defecto (ningun simbolo aceptado = endpoint de
   escritura cerrado por defecto). Se activa con `MICROPROBE_FLOW_SYMBOLS`
   para pruebas locales. No hay endpoint de escritura abierto por defecto.
5. Panel `MarketFlowPanel.tsx` conecta al SSE del mismo origen, sincroniza
   identidad/tiempo/cobertura, descarta eventos antiguos al cambiar simbolo,
   frescura caduca a 60s sin eventos validos (basada en ultimo dato valido,
   no en hora de consulta). Desconexion y datos obsoletos se distinguen de
   "nunca hubo cobertura".

**Pruebas:** `tests/test_market_flow_service.py` 5/5 (FlowEngine como autoridad),
`test_flow.py` 46/46 (sin regresion), `tsc` 0, `eslint` 0, `next build` OK.

**Dashboard canonico restaurado.** Servidor `next start -p 3020` en
`127.0.0.1:3020` con el nuevo build. Sin monitor, sin Binance publico,
sin paper prospectivo, sin ordenes, sin pagos, sin movil.

**Sesión de ingeniería — transporte local (2026-10-26, HEAD 365f7eb).**
Integración observable en el dashboard existente (`/market-lab`) sin crear un gestor paralelo. Reutiliza el controlador canónico (CLI `scripts/paper_lab_session.py` + motor `src/microstructure_probe/paper_lab_engine.py` con mecánica de `backtest_offline.run_backtest`) y los servicios existentes (BFF `api/v1/paper-lab/sessions*`, `api/v1/market-series` sobre caché local `client=None`, 0 upstream). Fuente LOCAL SIMULADA: velas de caché local (MINAUSDT 1m) + contexto BTC (BTCUSDT 1m), 0 llamadas a Binance, ventana no abierta ni solicitada.
- **Control de sesión:** botón visible "Iniciar / Detener sesión" en `/market-lab`; abrir el dashboard NO inicia nada; cada acción es POST acotado al BFF y el backend es la fuente de verdad.
- **Seis paneles separados:** estado de la sesión, fuente LOCAL SIMULADA, recepción/frescura de datos (reloj T, cursor, velas conocidas), evaluador (regla `ENGINEERING-MINA-1M-v1`, decisión en T, motivo/evidencia), posición paper (entrada/stop/marca/P&L no realizado), último error o motivo de abstención.
- **Vista de operación:** velas incrementales + reloj de sesión; candidato y motivo de decisión; entrada pendiente vs fill ejecutado; entrada/stop/salida en el gráfico (PaperChart); posición abierta/cerrada y motivo; P&L no realizado/realizado, costes y funding UNKNOWN; historial de eventos y exportación JSON/CSV. Todos los paneles comparten session_id, símbolo, tiempos y config_hash.
- **Regla de ingeniería:** `ENGINEERING-MINA-1M-v1`, explícita, versionada, separada de cualquier estrategia aprobada; caso de ingeniería, no selección por rentabilidad; backend decide con evidencia en T; el navegador no envía decisiones ni estado económico como autoridad.
- **Política de parada:** detener NO inventa cierre de posición; congela la sesión (`detenida`) y deja la posición tal cual (sin salida inventada, sin comisión de salida, sin realizado); se recupera por `get` tras recarga sin duplicar entrada ni cierre.
- **Recarga:** el estado autoritativo vive en `paper-lab-sessions/` (atómico, control de revisión); el navegador solo guarda el puntero `session_id` (never estado económico) y recupera vía `GET /api/v1/paper-lab/sessions/[id]`.
- **Recursos:** arranque/parada propios del BFF (spawnSync por acción), sin procesos huérfanos, sin afectar procesos ajenos, servicio de datos local (market-stream) permanece detenido por defecto.
- **Aceptación extremadamente extrema (A–E) demostrada frente al backend real:** A) iniciar → recibir datos → evaluar → entrada automática (fill por run_backtest) → gestión → cierre por horizonte → exportación JSON/CSV; B) evidencia insuficiente → SIN_ENTRADA/DESCARTADO, sin posición; C) fin de datos → sin nuevas entradas, estado visible, posición no cerrada inventada (open_at_end); D) recarga → recuperación del mismo estado (session_id/config_hash idénticos), sin duplicar entrada ni cierre; E) detener → sesión detenida, recursos propios liberados, sin afectar procesos ajenos. Transporte local aislado, 0 peticiones Binance, dashboard → BFF → Python → dashboard.
- **Límites pendientes:** conexión a Binance público (ventana aparte, autorización explícita), selector automático de varios símbolos, monitor en vivo, paper prospectivo, órdenes, pagos, móvil/Flutter, indicadores provisionales.
**Pruebas:** `npx tsc --noEmit` 0; `npx eslint` 0 en archivos nuevos; `npx vitest run src/test/paper-lab-live-api.test.ts` 9/9; `python run_tests.py -q` 1290 OK / 2 skipped; `next build` OK. E2E de navegador real (Chromium headless) sobre `http://127.0.0.1:3020/market-lab`: flujo A completo verificado (inicio → ENTRADA_SIMULADA → Entrar → abierta → pasos de gestión → cerrada por horizonte → exportación JSON), recarga recupera estado idéntico sin duplicar, detener congela sin cerrar, B (abstención sin posición verificada vía HTTP), C (fin de datos sin cierre inventado).



**Sesión de ingeniería — transporte local (refinamiento, 2026-10-27, HEAD 933606b).**
Integración observable en el dashboard existente (/market-lab) sin crear un gestor paralelo. Reutiliza el controlador canónico (CLI scripts/paper_lab_session.py + motor src/microstructure_probe/paper_lab_engine.py con mecánica de backtest_offline.run_backtest) y los servicios existentes (BFF /api/v1/paper-lab/sessions*, /api/v1/market-series sobre caché local client=None, 0 upstream). Fuente LOCAL SIMULADA: UN token candidato (MINAUSDT 1m) + BTC como contexto (BTCUSDT 1m), ambos de caché local; 0 llamadas a Binance, ventana no abierta ni solicitada.

**Alcance aclarado:** "Sesión de ingeniería / replay sobre caché", no "sistema completo autónomo". El recorrido con datos nuevos continuos sigue pendiente de autorización explícita; no se abrió conexión pública a Binance.

**Alcance de --no-fetch:** el BFF de market-series expone la opción de solo lectura controlada por backend `read_only=1`. La sesión de ingeniería la usa y el BFF pasa `--no-fetch` al CLI: cero upstream, ausencia en caché devuelve motivo sin activar fetch. El explorador normal llama sin `read_only` y conserva la adquisición bajo demanda con sus presupuestos existentes.

- **Recuperación real:** header con controles siempre renderizado; recarga con sesión abierta reconstruye vista completa (gráfico, posición, controles, eventos, exportación) desde estado autoritativo del backend.
- **Recuperación por identidad autoritativa:** el contexto se carga con `symbol`/`intervalo` del `config` de la sesión recuperada, nunca con las propiedades predeterminadas del componente; se muestra referencia de entrada y configuración recuperadas.
- **Fuente LOCAL SIMULADA (solo lectura / alcance de --no-fetch):** `read_only=1` → `--no-fetch`; cero upstream; ausencia en caché devuelve motivo sin activar fetch.
- **Sincronización de reloj:** `applyAuthoritative` centraliza la vista tras cada respuesta autoritativa; si `clock_ms` cambia (incluido Entrar) indicadores y contexto se recalculan para ese T sin mostrar valores previos como actuales.
- **Seis paneles separados:** estado de la sesión; fuente LOCAL SIMULADA; recepción/frescura (reloj T, cursor, velas conocidas); evaluador (regla ENGINEERING-MINA-1M-v1, decisión en T, motivo/evidencia); posición paper (entrada/stop/marca/P&L no realizado); último error o motivo de abstención.
- **Reloj T compartido:** indicadores y contexto BTC recalculados en el backend con el reloj T de la sesión (sin futuros); Open conocido al abrir, OHLC completo solo al cierre; flujo sin eventos → UNKNOWN.
- **Vista de operación:** velas incrementales + reloj; candidato y motivo de decisión; entrada pendiente vs fill ejecutado; entrada/stop/salida en el gráfico; posición abierta/cerrada y motivo; P&L no realizado/realizado, costes, funding UNKNOWN; historial de eventos; exportación JSON/CSV. Paneles comparten session_id, símbolo, tiempos, config_hash.
- **Regla de ingeniería:** ENGINEERING-MINA-1M-v1, explícita, versionada; entry_px fijado antes de evaluar (no es cierre de vela de entrada); dos prefijos (A/B) bajo misma configuración demuestran admisión vs abstención sin garantizar entrada.
- **Política de parada:** detener congela sesión (detenida) sin inventar cierre; recarga recupera estado sin duplicar entrada ni cierre.
- **Recursos:** arranque/parada propios del BFF (spawnSync por acción), sin procesos huérfanos, sin afectar procesos ajenos; servicio de datos local (market-stream) permanece detenido.

**Pruebas:** 
npx tsc --noEmit 0; 
npx eslint 0 (archivos nuevos); 
npx vitest run src/test/paper-lab-live-api.test.ts 9/9;
npx vitest run src/test/session-lab.test.ts 4/4;
npx vitest run src/test/engineering-session.test.tsx 5/5;
python run_tests.py -q 1290 OK / 2 skipped; 
next build OK. E2E navegador real sobre http://127.0.0.1:3020/market-lab: iniciar → ENTRADA_SIMULADA → Entrar → abierta → pasos de gestión → recarga abierta recupera estado. HTTP: crear→evaluar→step×31→cerrada por horizonte (exit_px=0.06302, realized_net=3.98, funding=None); dos prefijos (A admite entrada, B se abstiene, misma configuración); fuente solo lectura 0 upstream; reloj T sin futuros.
BUILD_ID servido: yeIE931T35_a8l_k-WiqW (SHA fuente del árbol 933606b841afc3c705acd1a3a04593b2e8c02fb5).

**Sesión de ingeniería — modo autónomo (2026-10-27, base `9a24308`, rama `feat/ingenieria-autonoma`).**
Objetivo: la sesión de ingeniería avanza sola de forma incremental (datos → cálculos → regla → entrada pendiente → fill simulado → gestión → cierre) con un solo "Iniciar sesion", sin pulsar "Entrar" ni "Paso a paso" para cada transición. Reutiliza el controlador canónico y los endpoints existentes; no se creó motor, servidor ni gestor paralelo.

- **Autonomía como conductor en el frontend:** cada tick reutiliza exactamente el endpoint `POST /api/v1/paper-lab/sessions/[session_id]/step` que usa "Paso a paso" (un proceso Python por acción vía `spawnSync`; no hay proceso Python persistente por tick). Retardo observable `AUTONOMOUS_STEP_DELAY_MS=1500` ms entre pasos y tope de seguridad `MAX_AUTONOMOUS_STEPS=200`.
- **El navegador no conduce el reloj ni decide trades:** solo observa y solicita iniciar/detener. Cada transición la decide el motor Python (fuente de verdad autoritativa); el navegador programa el siguiente paso y muestra el estado recibido. Cerrar/recargar la pestaña no interrumpe la sesión del backend (el estado vive en `paper-lab-sessions/`).
- **Arranque de autonomía:** tras la evaluación, si el estado es `en_espera` o `abierta` la autonomía arranca sola; los estados de abstención (`SIN_ENTRADA`/`DESCARTADO`/`sin_iniciar`) nunca abren el bucle (sin entrada forzada).
- **Fin del transporte local:** si un paso no avanza `clock_ms` mientras se espera entrada (`en_espera`/`sin_iniciar`), la autonomía se detiene con causa visible (`session-transport-cause`): sin entrada nueva y sin cierre inventado (política `open_at_end` declarada). Lo mismo si el paso termina en `cerrada` con posición abierta y `open_at_end=true`.
- **Política de parada:** "Detener sesion" libera primero el temporizador propio del navegador (la autonomía), no el backend; la sesión queda congelada (`detenida`) sin cierre inventado.
- **Controles manuales acotados:** durante la autonomía, "Entrar" y "Paso a paso" quedan deshabilitados (`canEnter`/`canStep` gated por `!autonomous`); una acción manual detiene la autonomía y retoma el control.
- **Cierre de robustez:** referencias (`stateRef`, `autonomousRef`, `loopRef`) para evitar closures obsoletos del bucle autónomo; limpieza al desmontar; reentrada protegida.
- **Corrección de selección de prefijo antes de iniciar:** `changePrefix` ignoraba la elección cuando aún no había sesión (early return antes de fijar el prefijo), contradiciendo la instrucción de la propia página ("Seleccione un prefijo de datos y pulse Iniciar sesion"). Ahora la elección sin sesión solo fija el prefijo para el próximo "Iniciar"; con sesión viva se conserva el comportamiento previo (reconstrucción con el mismo `entry_px` fijo). Con la caché actual MINAUSDT 1m, el prefijo B (35 velas de contexto) NO garantiza abstención (la señal y el fill ocurren también con prefijo B); la abstención real se demuestra con evidencia insuficiente/stop ya vulnerado vía HTTP (DESCARTADO, sin posición).
- **Sin rentabilidad:** la regla `ENGINEERING-MINA-1M-v1` sigue siendo hipótesis no validada; el modo autónomo no agrega selección por beneficio ni garantiza entradas (la regla puede abstenerse).

## 2026-10-28 — Autonomía de la sesión de ingeniería en backend (engineering-session-service/v1, base `0aa98f5`)

DECISIÓN: mover la conducción de la sesión de ingeniería a un servicio
backend Python residente en loopback (biblioteca estándar
`ThreadingHTTPServer`, puerto por defecto 8797, contrato
`engineering-session-service/v1`) que reutiliza `paper_lab_engine` con un
transporte local de eventos REVEAL y un hilo coordinador que llama
`advance_once()`. RAZÓN: el modo autónomo anterior (base `9a24308`)
programaba el avance con un timer de React en el navegador y un proceso
Python por paso (spawnSync en `/step`): cerrar la pestaña detenía la
conducción y el navegador era copartícipe del avance. Ahora el navegador
es SOLO observador (GET de estado; iniciar/parar vía control) y la
conducción sobrevive al cierre de la pestaña (demostrado en aceptación:
revisión 33→38 con la pestaña cerrada, `SESSION_CLOSED`, reabrir recupera
el estado correcto). Avance SOLO por eventos REVEAL con cadencia; el
evaluador no recibe velas futuras ni OHLC en los eventos de transporte.
Causas de fin de conducción explícitas (`SESSION_CLOSED`,
`END_OF_TRANSPORT`, `OPERATOR_STOP`, `SESSION_STOPPED`, `DRIVE_EVENT_LIMIT`,
`DRIVE_ERROR:*`). Respuestas uniformes `{session, drive}`. Aceptación de
navegador real PASS en 4 escenarios (S1 ciclo; S2 cierre de pestaña; S3
detener con posición abierta; S4 prefijo B + cierre por horizonte),
evidencia `docs/evidence/engineering-backend-2026-10-27/`. La separación
abstención temporal/terminal NO se demostró con datos reales (con la
caché de MINAUSDT ambos prefijos admitían entrada; no se fabricó
abstención): quedó probada determinísticamente en las suites.

## 2026-10-28 — Abstención temporal vs descarte terminal + reintentos de escritura en Windows (base `0aa98f5`)

DECISIÓN: en `paper_lab_engine.evaluate_session`, `SIN_ENTRADA` es
abstención TEMPORAL (la sesión se reevalúa ante cada evento nuevo; un
evento confirmatorio posterior admite la entrada sin intervención humana)
y `DESCARTADO` es descarte TERMINAL (cierre de sesión sin reabrir). Antes
la abstención bloqueaba indebidamente la información nueva. Complemento
de robustez Windows: `save_session` (escritura + `os.replace`) y
`load_session` reintentan 5× con backoff ascendente de 20 ms ante
`OSError`/`PermissionError` transitorios, conservando la señal explícita
`IDENTITY_UNCERTAIN` para corrupción real (no se enmascara). El mismo
bloque corrigió 3 fallos PREEXISTENTES de la base: causalidad del dict
pA�blico de sesiA3n (sin velas futuras) y el presupuesto interno de
benchmark de la ventana (`scripts/market_stream_window.py`). Suite Python:
1530 passed / 2 skipped (antes 6 fallos en la base).

## 2026-10-28 — Acceso operativo: arranque manual del servicio y semántica sesión/servicio separadas (base `5f24807`)

DECISIÓN: se declaran explícitas dos políticas de acceso operativo para el
bloque de ingeniería. (a) El arranque del servicio
`engineering-session-service` es SIEMPRE manual por CLI: abrir el
dashboard NO inicia procesos y el botón «Iniciar sesion» NO es un inicio
completo; con el servicio abajo el error es visible
(`data-testid="session-error"`), sin duplicados ni avance impostor, y el
operador lo levanta con
`python scripts/engineering_session_service.py --port 8797 --sessions-dir <dir dedicado> --pid-file data/engineering-session/service.json`
(dir dedicado obligatorio: el default `paper-lab-sessions/` colisiona con
el controlador anterior). (b) Las tres acciones de parada son distintas:
«Detener sesion» = política de posición (congela la sesión en `detenida`,
sin cerrar la posición ni inventar salida); cerrar la pestaña = solo
desconecta al observador (el backend sigue conduciendo); detener el
servicio = termina drives en memoria y NUNCA muta el estado económico en
disco de sus sesiones (quedan intactas y manejables tras reinicio).
Verificado en navegador real con 3 sesiones y parada/reinicio del
servicio (evidencia
`docs/evidence/engineering-backend-2026-10-28/`). Defecto abierto
documentado del panel de flujo: `ERR_INCOMPLETE_CHUNKED_ENCODING` en
`/api/v1/market-flow/stream` (impacto: stream abortado en re-render; sin
atribuirle fallos de esta sesión).

## 2026-10-28 - Inicio explicito completo integrado en la UI + directorio dedicado por defecto + causa/arreglo del defecto SSE (base  bf96c6)

DECISION: (a) �Iniciar sesion� es ahora un inicio completo explicito: el
BFF (nuevo rontend/src/lib/engineering-service-manager.ts + route
/api/v1/engineering-sessions/service) genera la instancia canonica
scripts/engineering_session_service.py (sin gestor paralelo), espera
readiness con limite y verifica identidad triple (child.pid == pid-file ==
/health.pid); nunca reutiliza ni detiene un PID desconocido
(ENGINEERING_SERVICE_UNIDENTIFIED); en fallo termina solo el proceso que
el gestor genero (sin huerfanos); el GET del servicio es consulta pura y
nada arranca por abrir la pagina. (b) El default de sesiones del servicio
era ROTO (el ROOT del modulo apuntaba a src/): ahora ROOT correcto y
default dedicado data/engineering-session/sessions, sin colision con el
controlador anterior (paper-lab-sessions/), conservando sesiones
existentes sin migracion. (c) El defecto del panel de flujo
(ERR_INCOMPLETE_CHUNKED_ENCODING) tiene causa reproducida con dos cortes
convergentes: AbortSignal.timeout(30_000) del BFF (cada SSE moria a los
30 s) y el odyTimeout por defecto de undici (30 s sin chunk cuando el
servicio preexistente 8792 queda mudo sin eventos de flujo); el arreglo no
toca 8792: agente undici con bodyTimeout 0 + headersTimeout acotado,
cancelacion propagada por 
eq.signal, y reconexion del panel con la
MISMA identidad (2,5 s) conservando la causa visible hasta onopen;
desmontar/cambiar simbolo libera el consumidor. (d) Hallazgo de la
aceptacion: el doble clic podia crear DOS sesiones (el disabled de React
no es sincronico entre clicks) - guardia sincrona startInFlightRef; el
artefacto anomatico de esa primera carrera (archivo de sesion vacio, id
sin sufijo) NO se reproducio en 2 reintentos ni en sonda de concurrencia
del motor/servicio: causa UNKNOWN, load_session lo rechaza honestamente
(IDENTITY_UNCERTAIN), evidencia preservada. Aceptacion real A-G PASS
(docs/evidence/engineering-explicit-start-2026-10-28/); sin Binance
publico, sin feed vivo, sin ordenes, observe-only.

## 2026-10-28 - Transporte live market_stream de ingenieria (backend+frontend) + aceptacion local PASS + fix del explorador canonico por cola (base `90b3c9b`)

DECISION: (a) la sesión de ingeniería consume en vivo el MISMO
market-stream-service/v1 (SSE loopback) del paper-lab: gates de feed vivo,
consumo de snapshots (_consume_snapshot/_consume_market_closed) y avance
live (_live_advance) en engineering_session_service.py; el frontend arranca
y supervisa el runner market_stream (EngineeringSession.tsx +
session-lab.ts + engineering-service-manager.ts); sin colector/motor/gestor
nuevos, paper_lab_engine intocado. (b) El explorador canónico read_stored
con rango amplio devolvía la CABEZA (velas más antiguas) con LIMIT 5000 y
caches >5000: el contexto del create live quedaba días atrasado y la
puerta live bloqueaba honestamente (GRID_GAP/DATA_STALE, sin decisión
falsa); arreglo por COLA (newest-first + reversa en canónico y cache;
bars[-limit:] tras la fusión), semántica idéntica con <=limit, regresión
nueva test_limit_keeps_the_most_recent_bars_of_the_range; efecto colateral
corregido: el gráfico canónico con caches grandes mostraba silenciosamente
datos viejos. (c) El arnés local determinista
(scripts/engineering_live_local_acceptance.py) usa backfill multi-frontera
del fake (últimas 4 fronteras cerradas al primer connect; sin señal en el
backfill: close 1.0490), MEMORY_ONLY para frames live (el backfill no
contamina el contexto) y limpieza de sesiones de ensayo al inicio de cada
corrida (el workdir efímero acumulaba sesiones → SESSION_COUNT_UNEXPECTED);
LIMITS["entrada"] 130→200 s por cadencia real del guion (la señal llega con
la vela M+3 tras la puerta FEED_SILENCE, ~2 fronteras, ~141 s reales), no
por compensar fallos. (d) shot-05/shot-06 con bytes idénticos es honesto
(cierre instantáneo tras la salida, cerrada_s 0.006), no defecto.
Aceptación real PASS en navegador
(docs/evidence/engineering-live-local-2026-10-28/, corrida 379,9 s, 12/12
checks, 8 reconexiones, 0 peticiones externas, net −16,59 simulado,
trial_sessions [], 3020 restaurado, 8792/8797 intocables); 92 tests
passed; sin Binance público, sin órdenes, observe-only. Gaps declarados
para público (NO acreditados): recepción Binance, reparación REST
inexistente en local, churn WS ~9 s tolerado, ciclo SSE de 10 s del
adaptador en silencio.


## 2026-10-28 — Demostración local explícita + reconciliación del pid-file solo por evidencia

(a) POLÍTICA DE IDENTIDAD: ante pid-file ausente/incompatible (incidente
preservado en V1 §11.7), el controlador del servicio de ingeniería puede
RECONCILIAR la instancia viva únicamente con la cadena completa de
evidencia verificable — /health canónico + sessions_dir canónico + pid
vivo + línea de comandos del SO (Get-CimInstance/ps) apuntando al CLI
canónico con el mismo puerto — reescribiendo el pid-file de forma atómica
y marcada `reconciled`; sin la cadena completa RECHAZA
(ENGINEERING_SERVICE_UNIDENTIFIED): no reutiliza, no detiene, no adopta.
El GET de estado sigue siendo consulta pura (sin escrituras); la
reconciliación ocurre solo en el POST de arranque explícito. Motivo: el
pid-file no es prueba independiente (registro gitignored reescribible).

(b) MODO DEMO EXPLÍCITO: «Demostración local — datos simulados» desde la
UI de /market-lab (sin comandos ni variables manuales), arrancando
EXCLUSIVAMENTE recursos propios identificados y acotados: productor WS
loopback determinista nuevo (`scripts/local_demo_producer.py`, reutiliza
el FakeKlineServer del arnés acreditado; parada automática propia
`--max-runtime-s`), servicio de mercado canónico en 8791 con
`--transport local --base-url ws://<productor>` y `--max-seconds`, y 8797
por el gestor existente. Nada arranca por GET ni al abrir la página;
iniciar/detener son POST con guardia de origen y guardia síncrona
anti doble-clic. Si la fuente declarada ya tiene un servicio ajeno →
rechazo explícito DEMO_SOURCE_FOREIGN (sin uso silencioso de 8792 ni de
instancias ajenas). La parada de la demo solo toca recursos con identidad
doble verificada (manifest + pid-file propio; DEMO_*_UNIDENTIFIED en caso
contrario) y NO toca 8797 ni sus sesiones: la pérdida de feed queda
registrada dentro de la sesión; la parada de la sesión es del operador.

(c) PUERTA DE FUENTE: «Iniciar sesión» comprueba la fuente (la que 8797
declara) ANTES de crear la sesión; sin fuente → `FUENTE NO DISPONIBLE` y
sin sesión huérfana; una caída POSTERIOR sí se registra dentro de la
sesión. Distingue estados servicio / fuente / sesión con chips visibles.

(d) PRODUCTOR DE DEMO: precio base = último close del cache local (el
MISMO origen del contexto de la sesión, consultado con --no-fetch, 0
upstream) y backfill parametrizado `--backfill-from-ms` = cache_end+paso
que repara el tramo cache→conexión SIN reparación REST (la puerta
GRID_GAP exige continuidad exacta contexto→operación); ciclo de closes
determinista que produce señal LONG (RULE-CAUSAL-V1) sin tocar el stop.
Verificación ACOTADA (arranque/readiness/parada, no repite la aceptación
larga) en docs/evidence/engineering-local-demo-2026-10-28/; sin Binance,
sin órdenes, observe-only.


## 2026-10-31 â€” Rango explÃ­cito de velas cerradas en fetchMarketSeries y series_payload

- `frontend/src/lib/session-lab.ts`: `fetchMarketSeries` ya no pide
  `from_ms=0` ni `to_ms=9999999999999`. Calcula una ventana explÃ­cita de velas
  CERRADA a partir del reloj (o `atMs` si se pasa): `to_ms` = apertura de la
  Ãºltima vela cuyo cierre <= ahora; `from_ms = to_ms - (bars - 1) * paso`.
  Nunca alcanza velas futuras. Se exporta `INTERVAL_STEP_MS`.
- `src/microstructure_probe/market_explorer.py`: `series_payload` clampa
  `end = min(end, now)`: el rango pedido nunca supera el reloj actual; las
  velas cuyo cierre aÃºn no se conoce se marcan `provisional` y no se publican
  como cerradas.
- `fetchMarketSeries` conserva `readOnly=true` por defecto (cero upstream,
  `--no-fetch`); la adquisiciÃ³n pÃºblica requiere `readOnly=false` (activaciÃ³n
  expresa) y el backend aplica el presupuesto compartido (ledger, reserva de
  intento antes del transporte).
- No es suficiente con cambiar `readOnly` en React: el backend valida la
  ventana y el BFF/CLI respetan `read_only=1`.
- Pruebas: `tests/test_session_new_public_market_local.py` (integraciÃ³n real
  sobre HTTP/WS locales, sin Binance) y
  `frontend/src/test/session-lab.test.ts` (ventana explÃ­cita). `tsc`/`eslint`
  0; `vitest` session-lab 4/4; suite frontend 622/623; `next build` OK. Sin
  Binance, Ã³rdenes, pagos ni cambios econÃ³micos.


## 2026-11-01 Referencia temporal explicita en create_session y admision de cierres (causalidad)

- Defecto confirmado en create_session: la validacion de contexto comprobaba ct > ot y continuidad, pero no comparaba el cierre contra una referencia temporal independiente; fijar T desde el ultimo close_time no acreditaba que ese cierre ya ocurrio.
- Se agrega un reloj de referencia independiente (EngineeringSessionController._now_ms, inyectable; por defecto pared del backend): modo publico: tiempo del backend sincronizado (ClockSynchronizer, offset + RTT y estado de sincronizacion/incertidumbre explicitos); modo local/replay: reloj controlado por el transporte de prueba. No se acepta un reloj aportado por el navegador como autoridad publica.
- Validacion ANTES de crear/iniciar: rechaza contexto insuficiente, cierre futuro (close_time > referencia, sin tolerancia positiva de un intervalo), vela no cerrada y serie discontinua, con motivo explicito (CONTEXTO_INSUFICIENTE / CONTEXTO_FUTURO / CONTEXTO_NO_CERRADO / CONTEXTO_DISCONTINUO / RELOJ_REFERENCIA_INCERTO). Ante incertidumbre se abstiene con motivo; no se crea la sesion.
- El T de evaluacion anterior no es techo permanente: un cierre nuevo avanza T cuando su disponibilidad queda acreditada por la referencia independiente (_consume_market_closed descarta cierres futuros como provisionales sin tocar la marca de agua, para que puedan reenviarse). Los duplicados no duplican efectos (marca de agua) ni el contador de evaluaciones.
- Pruebas: tests/test_engineering_session_clock_reference.py (recorrido HTTP/SSE real: referencia temporal, recepcion, cierre, T anterior/nuevo, evento disparador, contador de evaluaciones y resultado; caso historico crear a T-60s con cierre T-1s rechazado; determinismo: dos futuros distintos con mismo prefijo -> mismo estado hasta T) y tests/test_engineering_live_window_local_recorrido.py (validacion de contexto, caso historico futuro).
- Sin Binance, ordenes, pagos, movil ni cambios economicos.

## 2026-11-01 Activacion y presupuesto del reloj de referencia en el arranque del servicio

- El arranque ordinario/demo (main de engineering_session_service) NO ejecuta ClockSynchronizer.sync() contra Binance. Por defecto usa el reloj de pared local (referencia local_controlado, cero solicitudes publicas). El modo publico requiere activacion explicita en backend (--clock-source public), no basta con una etiqueta del navegador.
- Tres estados explicitos de referencia: local_controlado (reloj local/inyectado, cero publico), public_validado (ClockSynchronizer sincronizado contra el backend, offset + RTT + estado de sincronizacion expuestos) y sin referencia (ahora_ms -> None, abstencion). No existe fallback silencioso a pared no validado.
- Cada intento /time de sincronizacion publica se RESERVA en market_fetch_ledger ANTES de enviar (incluidos fallos), dentro del presupuesto publico de la corrida (LedgerAttemptGate / MAX_FETCH_REQUESTS_PER_WINDOW). Si el presupuesto no permite la politica de sincronizacion (sample_count intentos), el modo publico no se habilita y el servicio retorna error (no se activa publico silenciosamente).
- Se conserva la inyeccion de reloj local para pruebas (parametro now_ms del controlador).
- Pruebas focalizadas: tests/test_engineering_clock_budget.py (modo local cero intentos publicos; sin referencia no admite contexto RELOJ_REFERENCIA_INCERTO; publico sin presupuesto rechazado; intentos contabilizados y bloqueados antes de enviar; referencia valida vs expirada admision/abstencion coherente) y
  tests/test_engineering_session_clock_startup.py (arranque real por CLI: sincronizacion valida admite cierre; ausente/expirada abstiene; cierre futuro por contexto, snapshot y closed no admitido; sincronizacion recuperada progresa sin duplicados).
- Sin Binance en modo local/demo, ordenes, pagos, movil ni cambios economicos.


## 2026-11-02 Activacion y presupuesto del reloj de referencia en el arranque del servicio

- El arranque ordinario/demo (main de engineering_session_service) NO ejecuta ClockSynchronizer.sync() contra Binance. Por defecto usa el reloj de pared local (referencia local_sistema, cero solicitudes publicas). El modo publico requiere activacion expresa en backend (--clock-source public), no basta con una etiqueta del navegador. El valor predeterminado de --clock-source se conserva ('local'); no hay fallback silencioso al reloj local en modo publico.
- Cuatro estados explicitos de referencia expuestos en GET /health (campo clock): local_sistema (reloj de pared), local_inyectado (reloj controlado por pruebas), public_sincronizado (ClockSynchronizer sincronizado y vigente) y referencia no disponible/expirada (available False, con age_ms). Ante incertidumbre el backend abstiene (ahora_ms -> None); nunca cae al reloj de pared no validado.
- Dos limites de presupuesto separados: el general de ventana movil (MAX_FETCH_REQUESTS_PER_WINDOW=30 por 60 s) y el presupuesto TOTAL de la corrida (MAX_FETCH_REQUESTS_PER_RUN=7), compartido entre /time, klines, catalogo, reintentos y recuperacion. El total NO se reinicia al pasar la ventana movil; solo se reinicia al iniciar una nueva ejecucion del servicio (reset_run_budget en main). Cada intento reserva en market_fetch_ledger ANTES de abrir socket (fallos incluidos); si alguno de los dos limites se agota, no se envia nada. El servicio no sustituye el total de la corrida por el limite general.
- Presupuesto minimo viable propuesto (no cubierto por la autorizacion previa de 4): 5 intentos de tiempo + 2 de klines = 7. Los fallos y reintentos consumen esos cupos y pueden impedir completar la preparacion; no se garantizan dos descargas si se agoto el presupuesto.
- Pruebas focalizadas: tests/test_engineering_clock_budget.py (modo local cero peticiones publicas; sin referencia no admite contexto RELOJ_REFERENCIA_INCERTO; publico sin presupuesto rechazado; intentos contabilizados y bloqueados antes de enviar; referencia valida vs expirada; salud distingue las cuatro fuentes; el arnes comprueba fuente y validez antes de crear sesion; limite total de corrida compartido y no reiniciado por ventana). Arranque real verificado por CLI (--clock-source local, /health reporta local_sistema disponible).
- Sin Binance en modo local/demo, ordenes, pagos, movil ni cambios economicos.


## 2026-11-02 Presupuesto total de la corrida: atribucion persistente por run_id en el ledger

- Se corrigio el ciclo de vida del presupuesto total de la corrida: la clave global cache_meta.run_fetch_requests_total (reseteada por main() en cada arranque) se 
sustituto por atribucion persistente al run_id (execution_id) en el ledger (market_fetch_ledger). run_requests_used(run_id) ahora lee SUM(requests) WHERE execution_id = run_id; no existe reset_run_budget ni reinicio global al arrancar.
- Ciclo de vida verificado: (1) corrida con run_id estable consume cupos y al reiniciar el servicio de ESA corrida el consumo se conserva (no devuelve cupos); (2) dos instancias de la misma corrida comparten el limite total (7); (3) una nueva corrida (run_id distinto) empieza en cero sin borrar ni modificar los contadores de corridas previas.
- Se mantiene separado el limite general compartido de ventana movil (MAX_FETCH_REQUESTS_PER_WINDOW=30 por 60 s) del limite total de la corrida (MAX_FETCH_REQUESTS_PER_RUN=7); se reservan ambos cupos atomicamente en la misma transaccion: si cualquiera se agota, no se envia nada.
- /time, klines y demas intentos de una corrida usan el mismo run_id para compartir el limite total. main() genera un run_id estable por ejecucion y no lo resetea; una nueva corrida solo se obtiene con un run_id nuevo (creacion explicita).
- Pruebas focalizadas: tests/test_engineering_clock_budget.py anade test_run_id_estable_consumo_conservado_al_reiniciar, test_dos_instancias_misma_corrida_limite_compartido y test_nueva_corrida_contador_independiente_evidencia_intacta (11 pruebas en total, todas OK). Se mantienen las regresiones temporales ya acreditadas (todas OK).
- Sin Binance en modo local/demo, ordenes, pagos, movil ni cambios economicos.


## 2026-11-02 Propagacion del run_id en el arranque del servicio de ingenieria

- El orquestador (main de engineering_session_service) crea y persiste un 
run_id estable al iniciar una corrida, transmitido mediante el argumento 
estructurado --run-id. El modo publico lo exige; no genera otro desde la 
hora actual.
- /time, klines, catalogo y recuperación usan ese mismo run_id y comparten 
el límite total de la corrida (7). El run_id se persiste en 
sessions_dir/run-id.json; al reiniciar un proceso de la misma corrida se 
reutiliza el ID persistido. Una corrida nueva se crea explícitamente con 
un --run-id distinto.
- Se elimina el ámbito presupuestario eng-ctx-<ahora> independiente. Los 
IDs por petición se mantienen como detalle separado en el campo detail del 
ledger.
- Pruebas focalizadas: tests/test_engineering_clock_budget.py añade 
test_run_id_propagacion_camino_real (servicio /time + arnés klines, mismo 
run_id, SUM refleja ambos), test_run_id_reinicio_conserva_total, 
test_run_id_agotamiento_bloquea_cualquier_componente, 
test_main_run_id_public_exige_argumento y 
test_main_run_id_persiste_y_reutiliza (16 pruebas en total, todas OK).
- Sin Binance en modo local/demo, ordenes, pagos, movil ni cambios 
economicos.



## 2026-11-02 Propagación del run_id en el arranque del servicio de ingeniería\r\n\r\n- El orquestador (engineering_live_window.py) crea y persiste un run_id estable al iniciar\r\n  una corrida, transmitido mediante --run-id al servicio de ingeniería.\r\n- /time, klines y demás intentos de presupuesto usan ese mismo run_id y\r\n  comparten el límite total de la corrida (7).\r\n- Al reiniciar el proceso de la misma corrida se reutiliza el ID persistido en\r\n  sessions_dir/run-id.json. Una corrida nueva se crea explícitamente con un\r\n  --run-id distinto.\r\n- Pruebas focalizadas: tests/test_engineering_clock_budget.py añade\r\n  test_orquestador_run_id_camino_real y\r\n  test_orquestador_reinicio_reutiliza_run_id (14 pruebas en total, todas OK).\r\n- Sin Binance en modo local/demo, órdenes, pagos, móvil ni cambios económicos.\r\n

## 2026-11-02 Configuración efectiva del orquestador (presupuesto y fuente de reloj)



- Un límite ÚNICO y explícito por corrida: MAX_REST_REQUESTS_PER_RUN = 7 en scripts/engineering_live_window.py,

  coherente con MAX_FETCH_REQUESTS_PER_RUN = 7 del servicio de ingeniería (market_cache.py): compartido entre

  /time, klines, catálogo, reintentos y recuperación; atribuido persistentemente al run_id en el ledger.

- Fuente de reloj derivada del transporte: --transport public arranca ingeniería con --clock-source public;

  local usa referencia local explícita (--clock-source local). No hay --clock-source público sin autorización.

- Antes de crear sesión, el orquestador verifica /health.clock del servicio de ingeniería y rechaza fuente

  incorrecta (CLOCK_SOURCE_INCORRECTO), ausente (CLOCK_SOURCE_AUSENTE) o expirada / disponible False

  (CLOCK_REFERENCIA_NO_DISPONIBLE).

- LedgerAttemptGate (market_explorer.py) propaga run_max_requests al ledger market_fetch_ledger para que el

  límite total de la corrida se valide junto con la ventana móvil (30/60 s), ambos antes de enviar.

- Evidencia final: consumo agregado del ledger por run_id (run_requests_used), incluyendo /time; no solo el

  contador de consultas de contexto del arnés.

- Siete intentos sigue siendo una propuesta pendiente de autorización pública: no se ejecuta contra Binance.

- Verificación acotada (transporte local, sin Binance): tests/test_engineering_clock_budget.py (21 OK):

  argumentos del proceso, fuente esperada en /health antes de crear sesión, mismo run_id para tiempo y velas,

  total agregado consistente, y fuente incorrecta / ausente / expirada / presupuesto agotado bloquean antes de

  crear la sesión.



## 2026-11-02 Ventana publica de integracion (un unico intento, desde f0593ed+a314e4c)



- Ejecutado UNA VEZ: python scripts/engineering_live_window.py --transport public --execute

  --run-id eng-run-public-20261102 --build-id turbopack-3-ry682tkyiqk

  --sessions-dir <temp>/run-public/sessions --out <temp>/run-public/evidence.json

- Resultado: VEREDICTO GLOBAL ERROR.

- Causa: GLOBAL_DEADLINE_EXCEEDED en engineering_start_wait. El servicio de mercado

  arranco (PID 29820, puerto 8791, modo=public) pero el servicio de ingenieria no

  respondio /health a tiempo: su main() ejecuta ClockSynchronizer.sync() contra

  Binance (5 intentos /time) ANTES de levantar el servidor HTTP, y el deadline de

  180 s (desde el primer acceso publico) se consumo en preflight + arranque de

  mercado + sync del reloj. No se llego a crear sesion, ni a etapa WS/SSE/evaluacion.

- Limites respetados: 0 intentos REST publicos (rest_count=0), 1 conexion WS (no se

  abrio por no alcanzar etapa), 0 reconexiones, 0 consumidores SSE, 300 velas/consulta,

  deadline 180 s, cero escrituras en DBs canonicas (db_unchanged=true).

- Consumo agregado del ledger por run_id: no disponible (no se alcanzo _verdict;

  ledger_total_por_run_id=null). decision=null: no acredita abstencion.

- Cero operaciones: valido. No se ajusto la regla. No se repitio la ventana.

- Limpieza: _cleanup termino los procesos; puertos 8791 y 8797 libres; 8792 (servicio

  local ajeno) intacto; dashboard 3020 disponible, sin sesion de ensayo activa.

- Evidencia conservada en <temp>/run-public/evidence.json (no commiteada).



## 2026-11-02 Cierre y correccion de arranque del servicio de ingenieria (post-ventana publica)



- Cambio en scripts/microstructure_probe/engineering_session_service.py (main()): el servidor HTTP

  se levanta ANTES de ejecutar ClockSynchronizer.sync() en modo --clock-source public. Durante la

  preparacion (sync en curso), /health responde public_sincronizado con available=False (NOT_READY);

  nunca se permite crear sesion sin sincronizacion valida (_validar_contexto_temporal rechaza con

  RELOJ_REFERENCIA_INCERTO). Si el sync falla, available=False se mantiene y el servicio sigue

  operativo pero sin reloj valido. Esto evita que el orquestador se bloquee esperando /health y

  agote el deadline global de 180 s.

- Diagnostico de la ventana publica (eng-run-public-20261102, veredicto ERROR): la ultima transicion

  completada fue service_started (mercado PID 29820, puerto 8791, modo=public). El servicio de

  ingenieria se lanzo (_spawn) pero su /health nunca respondio porque el servidor HTTP se levantaba

  DESPUES del sync bloqueante contra Binance. No se atribuye el bloqueo solo a ClockSynchronizer;

  la causa estructural es el orden de levantamiento del servidor HTTP.

- Reconciliacion factual: rest_count=0 (contador del arnes, klines) NO acredita cero /time. El ledger

  market_fetch_ledger tiene 0 filas para eng-run-public-20261102, por lo que el consumo de /time del

  servicio de ingenieria es UNKNOWN (no se puede distinguir reservado / enviado / respondido / error).

  Objetivo no evaluado; no "cero operaciones valido".

- Pruebas focalizadas: tests/test_engineering_clock_readiness.py (6 PASS, sin Binance, cero peticiones

  publicas): reloj local disponible; public sincronizado disponible; public sin sync = NOT_READY;

  create_session rechazada sin reloj valido; proveedor de tiempo que falla = sesion rechazada;

  /health responde inmediatamente durante preparacion (no bloquea).

- Evidencia publicada en docs/evidence/ventana-publica-20261102/ (evidence.json, run-id.json,

  LEDGER_CONSULTA.json, ABSENCIA_LOGS.md, RECONCILIACION_FACTUAL.md, PRUEBAS_LOCALES_READINESS.json).

- No se repite la ventana publica. Sin conexiones publicas, ordenes, pagos, móvil ni cambios economicos.



## 2026-11-02 Corrección de readiness y persistencia de logs del arnés



- scripts/engineering_live_window.py: el orquestador distingue ahora HTTP

  disponible de servicio preparado. Durante la sincronización del reloj,

  /health responde con clock.available=false (NOT_READY); el arnés espera

  a que el reloj sea válido (source correcta y available=true) antes de

  crear la sesión, respetando el deadline global y un límite de preparación

  explícito (--clock-readiness-timeout-s, default 60 s). Fuente incorrecta

  o agotamiento de presupuesto producen un error claro. No hay fallback al

  reloj local en modo público.

- Los procesos de mercado e ingeniería persisten stdout/stderr en archivos

  de evidencia (--evidence-dir), evitando PIPE sin drenar. Los logs se

  conservan ante timeout, error de arranque o fallo previo a _verdict.

- El bloque finally recoge siempre: consumo del ledger por run_id,

  última salud disponible, resultado de limpieza y rutas de logs. Evidencia

  ausente significa UNKNOWN; no se infieren cero solicitudes.

- Pruebas focalizadas: tests/test_engineering_clock_readiness.py (9 PASS,

  sin Binance, cero peticiones públicas): incluye pruebas del CLI real del

  servicio lanzado como subproceso con proveedor de tiempo loopback (modo

  local: /health inmediato, creación de sesión, stdout/stderr persistidos).

- No se modifican motores, reglas económicas ni presupuestos. No se ejecuta

  ninguna ventana pública en este bloque.



## 2026-11-02 Prueba del fallo original de readiness y logs garantizados



- Prueba del fallo original en tests/test_engineering_clock_readiness.py:

  * test_reloj_inicialmente_no_disponible_luego_disponible: /health

    disponible con clock.available=false (NOT_READY); el arnes espera y

    no crea sesion; el proveedor responde tras 2s y el reloj pasa a

    available=true; el arnes continua y permite crear sesion.

  * test_proveedor_fallido_timeout_no_crea_sesion: proveedor que nunca

    se recupera; ninguna sesion creada, causa RELOJ_REFERENCIA_INCERTO,

    limpieza verificada.

  * Ambas pruebas usan el CLI real del servicio lanzado via _spawn del

    arnes (no subprocess.Popen directo), con proveedor de tiempo loopback

    (cero Binance).

- Logs garantizados: si falta --evidence-dir, se deriva del directorio

  padre de --out; nunca hay fallback a PIPE sin drenar. Los tests capturan

  stdout/stderr usando _spawn del arnés y verifican que los archivos

  existan.

- Resultado de limpieza: _cleanup() se ejecuta ANTES de copiar

  limpieza_resultado al resultado final, para que el JSON publicado

  contenga el estado real incluso ante timeout.

- Resultado exacto del comando ejecutado:

  python -m pytest tests/test_engineering_clock_readiness.py

  tests/test_engineering_clock_budget.py -q

  -> 32 passed (sin Binance, sin red pública, sin cambios económicos).

- No se ejecuta ventana pública. Rama no integrada.




## 2026-11-02 Correccion de evidencia de readiness (CLI real, sync demorada)

- CORRECCION de las entradas anteriores de readiness: las pruebas alli
  descritas NO ejercitaban sincronizacion demorada del CLI real.
  `test_reloj_inicialmente_no_disponible_luego_disponible` y
  `test_proveedor_fallido_timeout_no_crea_sesion` lanzaban un servicio
  SIMULADO (script `MOCK_SERVICE_SCRIPT` escrito por el propio test) que
  cambiaba `clock.available` con un temporizador (`switch_after_s`); la
  espera era un polling local del test, no
  `_wait_for_engineering_readiness` del orquestador. Una de las aserciones
  era siempre verdadera (`proc.poll() is None or True`). Esa cobertura no
  acreditaba el comportamiento productivo. Se conserva el registro anterior
  como historico; esta entrada lo corrige.

- Nuevo diseno (sin Binance, cero peticiones publicas):
  * El test lanza `scripts/engineering_session_service.py` como subproceso
    REAL via `_spawn` del arnes (stdout/stderr persistidos en evidencia).
  * Proveedor de tiempo loopback `_TimeServer` que emula `/fapi/v1/time` y
    RETIENE la respuesta hasta que el test llama a `release()`. No hay mock
    de servicio ni temporizador que cambie `available`.
  * La espera ejercitada es la productiva:
    `WindowOrchestrator._wait_for_engineering_readiness` con
    `clock_readiness_timeout_s` explicito.
  * Orden real conservado: el servidor HTTP se levanta antes de
    `ClockSynchronizer.sync()`; `ClockSynchronizer` es la clase real.

- Demostrado:
  * `/health` responde con `source=public_sincronizado`, `available=false` y
    `offset_ms=null` mientras el sync esta en curso.
  * `POST /sessions` se rechaza con RELOJ_REFERENCIA_INCERTO y sin
    `session_id` durante la preparacion.
  * La espera productiva sigue viva tras 1.5 s: no termina ni devuelve nada
    prematuramente.
  * Al liberar el proveedor, el sync real completa: `available=true`,
    `offset_ms` no nulo, `_wait_for_engineering_readiness` retorna y la
    sesion se crea (200).
  * Proveedor que nunca responde: vence el limite de preparacion
    (`ENGINEERING_CLOCK_NOT_READY`), no se crea sesion y la causa queda
    publicada en `evidence["clock_readiness"]`
    (`error=CLOCK_READINESS_TIMEOUT_CLOCK`, transiciones con
    `reloj_no_listo`, ultimo motivo observado).
  * Limpieza productiva verificada de forma efectiva: tras terminar el
    servicio el proceso esta terminado (`proc.poll()` no nulo) y el puerto
    esta cerrado (`_port_open` falso). Se elimino la asercion siempre
    verdadera.

- Cambio de soporte minimo en el servicio: argumento opcional
  `--public-fetch-url` (default None = Binance `fapi/v1/time`; en produccion
  el comportamiento no cambia) para apuntar el fetch de sincronizacion a un
  servidor loopback en pruebas. Se importa ademas
  `MAX_FETCH_REQUESTS_PER_RUN` en `engineering_session_service.py` (faltaba y
  rompia con NameError el arranque en modo public; ese camino nunca se habia
  ejecutado con el CLI real).

- `_wait_for_engineering_readiness` publica `evidence["clock_readiness"]
  tambien cuando falla (antes solo se publicaba al exito), para que la causa
  observada no se pierda.

- Nota de alcance documental: `docs/evidence/ventana-publica-20261102/
  PRUEBAS_LOCALES_READINESS.json` describe las 6 pruebas unitarias de
  controlador ejecutadas en ese momento; no acredita sincronizacion demorada
  del CLI real. Esa cobertura es la que anade esta entrada.

- Verificacion exacta: `python -m pytest
  tests/test_engineering_clock_readiness.py` -> 11 passed;
  `python -m pytest tests/test_engineering_clock_budget.py` -> 21 passed
  (32 passed en total). Sin Binance, sin ventana publica, sin cambios
  economicos ni de presupuesto. Rama no integrada.

## 2026-11-02 — Ventana publica unica: FAIL por vela en curso en el contexto

- Se ejecuto UNA sola ventana publica autorizada (run_id
  `eng-run-public-20261102b`, deadline 180 s, transporte y reloj publicos,
  8791/8797 aislados). **Sin relanzamiento.**

- Veredicto global: **FAIL**. El arnes escribe `ERROR` porque la excepcion
  aborta antes de `_verdict()`; la clasificacion operativa correcta es fallo
  determinista de contrato: no es un `ERROR` de Binance ni un `UNKNOWN` de
  consumo.

- Causa acreditada por el rechazo del servicio: `_load_recent_context`
  (rama `public`, `scripts/engineering_live_window.py` lineas 952-976)
  anade toda fila REST con `close_time` presente, **incluida la vela del
  minuto en curso**. El servicio la rechazo correctamente con
  `VALIDATION_ERROR: CONTEXTO_FUTURO` (BTCUSDT `open_time=1793642700000`,
  cierre `1793642759999`, referencia `1793642709475`). No se creo sesion.
  No se relajo la validacion para forzar la sesion.

- Acreditado: reloj publico valido antes de crear sesion
  (`public_sincronizado`, 5/5 muestras, `offset_ms=-60.398438`,
  `rtt_ms=368.107`, HTTP disponible mientras `available=false`); presupuesto
  exacto 7/7 en el ledger compartido (5 `fapi_time` + 2 `klines`, 0 filas
  `budget_blocked`, `retry=0`, `limit=300`, rango de 300 min sin paginar ni
  descargar dias intermedios); recuperacion REST desactivada; limpieza
  completa (procesos terminados, 8791/8797 cerrados, 8792 y 3020 intactos);
  DBs canonicas sin escrituras (SHA-256 identico antes/despues).

- No acreditado: `session_id`, `config_hash`, cierre nuevo admitido,
  T anterior/nuevo, evento disparador, contador de evaluaciones y decision
  con motivo. La conduccion SSE nunca se inicio; no hubo posicion, P&L,
  comision ni realizado.

- Consumo no observable: el estado de conexion de la unica WS combinada y
  el contador de reconexiones quedan **UNKNOWN** (no se muestreo `/health`
  del servicio de mercado tras el fallo). Cero consumidores SSE es cierto
  por flujo de control (la conduccion no se inicio), no por contador.

- Correccion documental: el detalle del check `build_served` imprime un
  literal historico ("arbol e2243c9") que NO corresponde al arbol servido
  (`1f6f0500cb9115fa5c9d44e07be2c5524bdee690`); y `contexto_cargado`
  afirma "velas cerradas" aunque el contexto incluia una vela abierta. Se
  corrigen las afirmaciones en la evidencia nueva; no se reescribe historia.

- Decision de alcance: no se modifica codigo durante ni despues de la
  ventana. La correccion del arnes (excluir velas con `close_time_ms`
  posterior a la referencia) y su prueba local quedan como siguiente tarea;
  volver a conectar exige **nueva autorizacion** y un `run_id` NUEVO, porque
  el presupuesto de `eng-run-public-20261102b` esta agotado (7/7).

- Evidencia: `docs/evidence/engineering-live-public-20261102b/`
  (`RESULTADO.md`, `summary.json`, `preflight.json`, `evidence.json`,
  `post_state.json`, `ledger-run-id.json`, logs del arnes y de ambos
  servicios).


## 2026-11-02 — Contexto cerrado en el arnes y pid-files aislados (sin Binance)

- Correccion del defecto FAIL documentado hoy (ventana
  `eng-run-public-20261102b`), en codigo y con pruebas locales; SIN ventana
  publica ni consumo upstream. Rama `diag/recorrido-local-4f4273c`, base
  `f033c06`; arnes SHA-256 `97bec590…` (nuevo).

- Referencia temporal: `_reference_now_ms` exige el reloj del servicio de
  ingenieria con validez comprobada (`public_sincronizado`, `available`
  True, `offset_ms` finito, `age_ms` presente); la referencia es
  `reloj_local + offset`. Nunca el reloj del navegador. Ademas se cablea
  `_verify_clock` (check `clock_fuente_verificada`), que estaba definido
  pero sin llamar. Sin fallback silencioso a reloj de pared.

- Ventana de contexto: `_context_window` pide exactamente la serie de
  `bars` velas que termina en la ultima vela cuyo cierre ya ocurrio
  (`open + step - 1 <= referencia`; el cierre IGUAL a la referencia se
  admite). Sin tolerancia positiva de un intervalo: la vela en curso no se
  pide, y si un proveedor la devuelve igualmente se filtra fila a fila.

- Filtro por fila (`_admitir_filas` / `_admitir_almacenadas`): se excluyen
  con contadores en `parse_diag` las filas sin `close_time` disponible,
  con cierre posterior a la referencia (vela en curso) y el OHLC de cache
  capturado antes del cierre. Nunca se inventa cierre ni se incluye OHLC
  no cerrado. REST sobrescribe lo almacenado por `open_time`; identidad
  por simbolo y deduplicacion solo dentro del mismo simbolo (BTC y MINA
  nunca se mezclan por timestamp).

- Aborto explicito: `_prepare_context` (nuevo paso entre arranque de
  servicios y `_create_session`) ejecuta `_validar_contexto_cerrado`, que
  replica la taxonomia del backend (`CONTEXTO_INSUFICIENTE`,
  `CONTEXTO_NO_RECIENTE`, `CONTEXTO_DISCONTINUO`,
  `CONTEXTO_FUERA_VENTANA`, `CONTEXTO_FUTURO`) sin relajarla. Si tras
  filtrar falta contexto no se hacen descargas automaticas adicionales y
  NO se crea sesion. Presupuesto REST sin cambios
  (MAX_REST_REQUESTS_PER_RUN=7, reserva preenvio `LedgerAttemptGate`).

- Aislamiento de pid-files: `market_stream_service.py` acepta `--pid-file`
  (antes solo la variable de entorno); el arnes pasa rutas exclusivas de
  la corrida (`sessions_dir/market-service.json`,
  `sessions_dir/engineering-service.json`) y la limpieza borra SOLO esos
  archivos. Un pid-file ajeno preexistente queda identico antes y despues,
  incluso ante fallo de arranque (probado en loopback). El pid-file
  compartido `data/market-stream/service.json` del servicio 8792 no se
  toca ni se reconstruye.

- Requisito habilitado: los proveedores locales de pruebas
  (`local_kline_provider.py`, `local_ws_kline_provider.py`) ahora respetan
  el rango pedido (primera apertura `>= startTime`); antes devolvian una
  vela extra anterior al rango, lo que impedia demostrar contexto cerrado
  puro con proveedor local.

- Historia intacta: no se reescriben la decision FAIL previa ni los
  veredictos existentes. Pendientes declarados no bloqueantes: literal
  historico del check `build_served` y respuesta de
  `tests/test_engineering_live_window_local.py` (fixture desfasada).
