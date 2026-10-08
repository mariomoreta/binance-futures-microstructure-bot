# CURRENT_STATE

Factual state as of 2026-10-06 (order refinement). Historical evidence:
`docs/PHASE_1_REPORT.md` (do not rewrite).

## Baseline (audited, preserved)

- Codebase: `src/microstructure_probe/` — `probe.py`, `detectors.py`, `metrics.py`,
  `telemetry.py`, `clock.py`, `config.py`, `models.py`, `__main__.py`.
  Plus root `run_tests.py` (P1-00; test tooling only, no app behavior change).
- Version: 0.2.0 (`pyproject.toml`). History: `157e85e` baseline + `d6801a5`
  brain checkpoint, branch `phase1/market-intelligence-dashboard`, published to
  private `mariomoreta/binance-futures-microstructure-bot` (origin/main +
  origin/phase1 in sync). Repo-local git identity configured per operator
  authorization; nothing global was changed.
- Mode: OBSERVE ONLY. `BOT_MODE=observe` enforced in code; any other value aborts.
  No authenticated clients, no order paths (covered by static test).
- Feeds (public, routed endpoints): `/public` (bookTicker, depth20@100ms),
  `/market` (aggTrade, `!markPrice@arr@1s`, `!forceOrder@arr`).
  Symbols: BTCUSDT, ETHUSDT, SOLUSDT (`config/probe.json`).
- Implemented: clock sync (5-sample midpoint median, ~10 min), gap/staleness
  detection (staleness only on cadenced streams; event-driven silence ≠ stale),
  raw/corrected event+transaction latency per stream/symbol, monotonic processing
  latency split (parse/metrics/detector), liquidation individual+10s-window
  detectors, funding percentile extremes with warm-up + non-independence note,
  10s-bucket volume z-score with warm-up + near-miss, telemetry
  (quantiles over last 20k samples; exact count/min/max/mean), JSON logs +
  `final_summary`.
- Phase 1B semantics: `E` = event time; `T` = trade/transaction time except
  markPrice where `T` = next funding time (NOT latency). Legacy global clamped
  lag kept labeled as legacy, not a gate metric.

## Verification (2026-10-06)

- Canonical: `python run_tests.py` from repo root → **144/144 PASS** (28 baseline
  + 32 persistence/sampling/v2 + 22 universe/returns + 24 dashboard + 38 P1-05).
- `--show-streams` → correct routed `/public` + `/market` URLs.
- Port candidates 8091/8092/8093/18091/18765 probed FREE on 127.0.0.1
  (dashboard port-policy evidence; selection happens at P1-03 startup).

## P1-01 short transport validation — RESULT: PARTIAL (2026-10-06)

Run: `python -m microstructure_probe --duration 1800`, BOT_MODE=observe,
`runtimeSeconds: 1804.969`, exit 0. Evidence log (local, git-ignored):
`logs/p1-01/probe-1800s.log`. No keys, no orders, no capital, no private APIs.

Measured (from `final_summary`):

- Coverage: 11/11 streams active, `missingStreams: []`, `staleStreams: []`.
- Uptime: market 98.51% (1773.3s/1800.1s), public 95.05% (1711.0s).
  Attempts 60 (public 46, market 14), all succeeded.
- Reconnects: 58 total (public 45, market 13) — every one
  `ConnectionClosedError: no close frame received or sent`, retry 1s
  (backoff resets on success, so it never grew). ~1 drop per 31s average.
- Messages: 172,906 total. bookTicker 32.2/31.5/17.9 msg/s (BTC/ETH/SOL);
  depth ~2/s per symbol (cadence allows ~10/s); markPrice arrays 1563 of ~1800
  expected; forceOrder 421; aggTrade 5466/4709/3205.
- Delivery lag (corrected event lag): bookTicker p50 14.8–19.2s / p95
  45.6–53.8s; depth p50 ~14.7s / p95 ~50.4s; aggTrade p50 31.6–38.1s / p95
  73.5–75.6s; markPrice p50 35.0s / p95 75.9s; forceOrder p50 38.5s / p95 69.0s;
  max ~127s. Exchange-side E−T deltas are milliseconds (bookTicker p50 0ms),
  so the delay is entirely in the delivery path to this host, not Binance.
  Clock sync 3/3 ok (15/15 samples); offset drifted −231ms → −475ms; RTT
  610–943ms — slow/lossy path confirmed.
- Skew guard: `timestampRejected: 147417` (~85% of messages, |received−E| >
  5000ms, degraded from the first 30s summary onward). Rejected messages skip
  metrics+detectors, so detectors operated on survivors only.
- Gaps/silence: depth sequence gaps 50/49/49 (reconnect-driven, expected).
  Max observed silence: depth ≤28s, bookTicker ≤21.5s, aggTrade ≤16s,
  markPrice 12s. forceOrder silent up to 111s — event-driven, correctly NOT
  reported stale (Phase 1B fix works in practice).
- Errors: parse 0, payload 0, websocket errors = reconnects (58).
  Processing latency sub-ms (p50 ≤0.17ms) — probe CPU is fine.
- Detectors: 26 `extreme_funding_rate`, 0 liquidation, 0 volume. The 26 funding
  events are sampling artifacts (near-constant series ±1e-7…1e-5 evaluated on
  sparse post-rejection arrivals, first firing at the 30-sample warm-up edge),
  NOT signal validation. No threshold conclusion may be drawn from this run.
- Safety block in every summary: observe, 0 keys, 0 orders, 0 capital,
  no authenticated clients, no order paths.

Verdict reasoning: P1-01 as a measurement exercise succeeded (full
characterization obtained), but transport in THIS environment is unhealthy
(reconnect storm + 15–75s delivery lags + 85% skew-rejection). Therefore
PARTIAL: evidence recorded, P1-02/P1-03 (local builds) may proceed, but gates
G2–G4 cannot pass on this evidence and P1-10/P1-14 require re-validation in a
healthy network (tracked as `P1-01R` in `docs/TASK_QUEUE.md`).
`docs/PHASE_1_REPORT.md` historical evidence untouched.

## Phase 1 execution order (binding, refined 2026-10-06)

`P1-00` tooling ✅ → `P1-01` short transport validation (30–60 min, NOT 6h) →
`P1-02` persistence foundation → `P1-03` minimal dashboard (`/overview`,
`/system`) → `P1-04` universe+returns → `P1-05` velocity/rank → `P1-06`
volume/flow → `P1-07` book/OI → `P1-08` VWAP/vol/structure → `P1-09`
intelligence dashboard (`/movers`, `/symbol/:symbol`, raw features first) →
`P1-10` ≥6h soak with dashboard live → `P1-11` raw feature validation →
`P1-12` classifier v0 (BLOCKED until P1-11) → `P1-13` signal/extreme-move UI →
`P1-14` 24h calibration + gate evaluation. Full detail: `docs/TASK_QUEUE.md`.

Superseded: the earlier "soak first, persist nothing in Phase 1" sketch.
Persistence foundation is now explicitly a Phase 1 task (local, observe-only,
dashboard-feeding) — see `docs/DECISIONS.md`.

## P1-02 persistence foundation — RESULT: PASS (2026-10-06)

- Tech: stdlib SQLite (`sqlite3`), no new dependencies. Store:
  `data/microprobe.db` (project-local, git-ignored via `data/` + `*.db`).
- Schema v1 + version gate + column migration: `persistence_meta`,
  `telemetry_snapshots` (periodic `build_summary` output for the P1-03
  dashboard), `market_observations` (valid only, `is_valid` + symbol/stream
  indexes), `rejected_observations` (skew/parse rejects, reason + stream
  indexes). 9 indexes total.
- Write path (probe.py, all fire-and-forget with `persistence_error` logging,
  never breaking the probe): valid dict payloads → observations with
  normalized price/qty/E/T; markPrice arrays → single `MULTI` record (no
  longer dropped); skew-rejected payloads (dict or list) → rejections only;
  every summary (30s + final) → snapshot row.
- Invalid-data guarantee: the skew guard returns before the valid-write code,
  so rejected messages can only reach `rejected_observations`;
  `latest_observations()` hard-filters `is_valid = 1` (both proven by tests,
  including a probe-level skew test).
- Retention: snapshots ≤1000, observations ≤10000, rejections ≤1000 rows
  (instance-overridable); steady-state storage bounded (~10–20MB worst case).
- Non-blocking: writes run via `asyncio.to_thread` under a lock (single
  shared connection); smoke (2000 mixed msgs): schedule p50/p95
  0.021/0.039ms, full drain 9.2s off-loop. Per-insert retention DELETE is the
  dominant cost (~4.6ms) — fine at current rates; see risks.
- Restart: close() is idempotent; reopen replays schema gate and all rows
  survive (tested).
- Found and fixed during verification (were failing, 5 errors): missing
  `spread_bps_json` column + 19-vs-18 INSERT mismatch; `store_rejection_record`
  crashed with no running loop; real-summary legacy-lag dict vs REAL column;
  markPrice arrays never persisted; snapshots never wired to the probe.
- Known risks: (1) no write backpressure — sustained rates far above ~200/s
  queue tasks in memory (dashboard freshness lags, WS never blocks); P1-04
  sampling/aggregation is the planned remedy. (2) At full healthy-network
  bookTicker rates the 10k observation cap retains only recent minutes —
  sufficient for dashboard/P1-04 bootstrap, not archival history (Phase 2
  owns that).

## Project brain

- Live corrigendum (found during P1-03): snapshot writes starved behind bulk
  observation traffic on the shared executor (0 snapshot rows vs 9260
  observations in a live run). Fixed with a dedicated single-thread snapshot
  writer + regression test; 2 snapshots landed on the very next live run.
  See `docs/DECISIONS.md`.

## P1-03 minimal live dashboard — RESULT: PASS (2026-10-06)

- Stack: stdlib only (`src/microstructure_probe/dashboard.py`,
  `ThreadingHTTPServer`, server-rendered dark HTML, no new dependencies,
  version 0.3.0). Data only via P1-02 reads (`latest_telemetry`,
  `latest_observations`, `get_rejection_stats`, `storage_info`).
- Routes live: `/overview` (safety banner, connections, uptime, message
  activity, stale/silent, reconnects, gaps, rejections, snapshot age,
  detector counts labeled NOT trade signals), `/system` (per-stream table,
  rates, raw/corrected p50/p95, processing latency, clock, rejections,
  persistence, safety), `/api/health` (status/version/uptime/reachability/
  snapshot time/streams/BOT_MODE/safety/reasons), `/api/snapshot`.
  No buttons, no trading controls, no private-account data.
- Live instance: http://127.0.0.1:8091 (first candidate, was free),
  PID 10796, `logs/dashboard.pid`, health `ok` at startup, all routes
  HTTP 200, unknown route 404. Started via
  `python -m microstructure_probe.dashboard start`; left running (read-only,
  localhost — safe).
- Seed: 40s observe-only probe (exit 0) wrote 10k observations + 2 snapshots
  of real market data — no mock data anywhere. Seed window itself was healthy
  (0 reconnects, 0 skew-rejections), so the pages currently show HEALTHY;
  the model reports DEGRADED/STALE/UNKNOWN from persisted evidence when
  present (proven by tests, and P1-01-style degradation would surface the
  same way). Snapshot ages without a running probe — STALE chip after 120s
  is honest; continuous freshness arrives with the P1-10 soak feed.
- Found and fixed live: snapshot executor starvation (see DECISIONS).
- Tests: 66/66 (18 dashboard: health ok/degraded/stale/unknown, routes,
  empty-DB, banner values, no-controls, port skip/busy, PID live/dead/stale).

## P1-04 symbol universe + multi-timeframe returns — RESULT: PASS (2026-10-06)

- Universe: `universe.py`, active trio preserved (BTC/ETH/SOLUSDT, explicit
  enabled/source/reason/activated_at metadata); no expansion, no ranking.
  No new REST endpoint introduced (static-config source; exchangeInfo remains
  future work) — no Binance-docs verification owed.
- Engine: `returns.py` — mark-price log returns, 7 TFs, 10s buckets (≤9180),
  tolerance max(60s, tf/20), UNKNOWN never 0, no lookahead, late/invalid
  refused. Valid-path-only ingestion (rejected messages return before it).
- Backpressure: sampling gate (bookTicker/aggTrade/depth ≤1/s per symbol;
  markPrice/forceOrder ungated; counts in `sample_stats()`); dedicated
  snapshot writer kept; schema v2 (`price_samples`, `return_features`,
  migration tested). 106/106 tests.
- Live 360s attempt: harness session-end killed the detached probe at ~330s
  (11 periodic summaries, no final) — lesson: detached children die with the
  tool session; reran 240s blocking → clean exit 0 + `final_summary`.
  Mid-run API: all 3 symbols with real prices, 1m warmed first, longer
  horizons honestly unavailable; dashboard `ok` while fed, STALE/DEGRADED
  honestly after (DEGRADED currently live from persisted reconnects +
  rejection rate — P1-01 degradation surfacing as required).
- Clean-run evidence (244s, 11/11 streams, 0 stale, safety 0/0/0):
  5 reconnects, 11448 skew-rejects (~93%, lags p50 22–85s — degraded env);
  engine 46 samples/symbol over 25-min restored+live span, 0 invalid, 0 late,
  0 unknown-symbol; sampling accepted 36/dropped 858 counted;
  inflight high-water 345, drained to 0 — no unbounded queue growth.
  Rejects went to `rejected_observations` only (cap 1000); returns contain
  no rejected input by construction + unit test.
- Dashboard: Symbol Returns on `/overview` + `/api/features/returns` live;
  partial warmup renders values + "—", no movers/rank/states/controls.

## P1-05 dynamic discovery + velocity/acceleration/ranking — RESULT: PASS (2026-10-06)

- Discovery (`discovery.py`, public REST only, no keys): exchangeInfo +
  24hr tickers on `fapi.binance.com` (docs site unfetchable — behavior
  verified live instead). Live scan: 924 seen → 449 eligible → 475 filtered
  (PERPETUAL + TRADING + USDT + ≥1M quote-vol floor). Core trio preserved.
- HOT: 6 dynamic (USUSDT +41%, 龙虾USDT +35%, BR/ORCA/NMR/GRIFFAIN +31–41% —
  small sharp movers, not large caps) promoted after 2 votes, stable after;
  losers LYN −25%, MINA −24%; most-active BTC/ETH/SOL by volume (movement ≠
  volume demonstrated). No WS subscription changes (trio only); HOT proposed
  via API/dashboard/logs; dynamic resubscribe is a documented next step.
- Momentum (`momentum.py` on P1-04 series, `feature()` untouched): velocity =
  return-change per second (flat trends ≈ 0 — not renamed returns),
  timestamp-aware acceleration, None until warmed; live velocity_1m values
  (e.g. ETH +3.2e-6/s) with accel honestly None until 3 evaluations;
  ranks ±/ties/change/velocity/accel across the trio (ETH #1 climbing).
- Dashboard: three separated health blocks, Symbol Returns kept, new
  intelligence area (tiers, live momentum, discovery movers, event history),
  `/api/discovery` + `/api/features/momentum`; forceOrder never missing;
  reject labels split run-vs-retained; no movers route, no states, no controls.
- Persistence v3 (discovery snapshot REPLACE, universe_events ≤500, rank
  vectors REPLACE-per-metric; tested v1→v3 and v2→v3 migrations).
- Live windows: 360s detached run killed by tool-session end (~330s, lesson
  recorded — detached children die with the harness session) + clean 240s
  blocking run (exit 0, final_summary): 11/11 streams, 0 reconnects,
  0 skew-rejects (healthy window!), 143659 msgs, engine 91 samples/symbol
  over 89-min span, sampling accepted 1888/dropped 141k counted, inflight
  high-water 6 → 0, safety 0/0/0. Dashboard `ok` while fed, STALE/DEGRADED
  honestly after. 30 funding crossings judged non-signal artifacts as before.
- Tests: 144/144 (38 new). Unicode HOT symbol (龙虾USDT) flows through
  JSON/DB/HTML correctly; only legacy Windows-console display needed UTF-8.

- `AGENTS.md` + 20 docs under `docs/`. No strategy, engine, or safety code
  touched. `docs/PHASE_1_REPORT.md` preserved as-is.

## P1-06 volume + aggressive trade flow — RESULT: PASS (2026-10-07)

- Semantics verified against CURRENT official USD-M docs + live payloads:
  same-price/same-side 100ms aggregation (insurance/ADL excluded), `m`
  (true→aggressive SELL, false→aggressive BUY), `q` RPI-inclusive vs `nq`
  normal, `E` ordering key, `st: 1` live. Recorded in `docs/MARKET_DATA.md`.
- Engine (`flow.py`, NEW): every valid aggTrade ingested pre-sampling;
  trailing windows 10s/30s/1m/3m/5m/15m with exact per-horizon expiry;
  baselines 10s/30s/1m/5m on completed buckets (skips counted, z null on
  thin/zero-variance history); 1m-referenced acceleration; same-E accepted
  in arrival order (first live run proved `<=` undercounts ~35% BTC flow —
  fixed, re-validated to 4027/4027 accepted, 0 late, 0 invalid).
- Persistence v4 (additive, tested v1/v2/v3→v4): `flow_features` per symbol
  + bounded `flow_buckets` (168 rows/run); restarts restore closed buckets
  only — returns span grew across runs (9340s → 9970s), no double-count.
- Live windows (blocking, BOT_MODE=observe, exit 0, dashboard live):
  (a) 363s degraded-transport lesson run (2403 processed, 35% same-E lesson);
  (b) 363s HEALTHY run — 11/11 streams, 0 reconnects, 0 skew-rejects,
  clock 5/5: 4027/4027 valid aggTrades into the engine (BTC 2035 / ETH 1317
  / SOL 675), raw persistence kept 746 aggTrade (3281 sampled away — flow
  totals provably unaffected), 168/168 buckets persisted, engine latency
  p50 0.030ms / p95 0.069 / max 0.19, queue 0/0, inflight 6→0, safety 0/0/0.
  Snapshot BTC 1m: 408 trades, $2.61M notional, 85.9% aggressive buy,
  delta +$1.88M, ratio +0.72 (raw feature, no conclusion). Baselines
  honestly warming (6/30 samples → z null). HOT [] (one scan < 600s
  interval → votes 1/2, hysteresis honest). 37 funding crossings — same
  hypothesis-artifact class as before, no threshold conclusions (P1-11).
- Dashboard v0.5.0 live at http://127.0.0.1:8091 (restarted, PID 31436):
  flow table + BUY/SELL bars on /overview, DISCOVERY ONLY labels,
  `/api/features/flow` + `/api/features/volume` live (200), health `ok`
  while fed; no buttons/controls/signals.
- Tests: 190/190 (46 new: 44 flow + v3→v4 migration + same-E arrival).
  Two pre-existing version-3 assertions updated to v4 (migration, expected).

## P1-07 order book + open interest — RESULT: PASS (2026-10-08)

- Docs verified (current USD-M pages + live payloads): depth20@100ms = FULL
  top-20 snapshots (`U`/`u`/`pu` chain, `st: 1`, `ps` live); OI = public
  `GET /fapi/v1/openInterest` (`{symbol, openInterest base, time}` live);
  `openInterestHist` evaluated + deferred (single provenance). In MARKET_DATA.
- Book (`book.py`, NEW): every valid depth snapshot pre-sampling; best/mid/
  spread, top-1/5/10/20 sums, imbalances, microprice + displacement,
  LS-origin slopes + asymmetry, 5/10/25bps concentration (null when
  unspanned), crossed kept+counted, gap→DEGRADED-until-chained, no score.
- OI (`open_interest.py`, NEW): 60s bounded poller (worker thread, failures
  counted, WS untouched) + tracker (2000/symbol; 1m/5m/15m deltas+rug rates,
  1m accel, descriptive price/OI contexts, staleness honest).
- Persistence v5 (additive, tested v1/v2/v3/v4→v5): `book_features` latest
  only (never restored live), `oi_samples` + `oi_features`.
- Live 363s blocking run (exit 0, dashboard live): 11/11 streams, 1 public
  reconnect, 15992 skew-rejects (degraded bookTicker window — recorded
  honestly). BOOK 7309/7309 valid processed (0 invalid/late), latency p50
  0.15ms/p95 0.30/max 1.07, 1 gap/symbol all recovered, queue 0/0.
  OI 18/18 polls ok (0 failures, p50 380ms/max 7.6s absorbed). FLOW intact
  (5684 processed — P1-06 regression green). Sampling lossless to engines
  (depth persisted 739 vs 7309). Safety 0/0/0. Live book: spreads
  0.012/0.037/0.834bps, ask-heavy imbalances, micro ~0, SOL 55% conc@10bps
  (BTC/ETH honestly null — band unspanned). Live OI: BTC 96105.2 (+9.4/1m,
  +69.7/5m), ETH 2323727.6, SOL 8287311.7 with descriptive contexts only.
  99 funding crossings — same hypothesis-artifact class, no conclusions.
- Dashboard v0.6.0 at http://127.0.0.1:8091 (restarted, PID 27296): book +
  OI tables, NO LIVE FLOW/BOOK labels, `/api/features/book` +
  `/api/features/open-interest` live (200), health DEGRADED honestly
  (reconnect + retained rejects); no buttons/controls/signals.
- Tests: 239/239 (49 new: 48 book/OI + v4→v5 migration). Five v4
  assertions updated to v5 (migration, expected).

## P1-08 VWAP + volatility + structure — RESULT: PASS (2026-10-09)

- Zero new sources: VWAP from flow aggregates, vol/range/structure from
  persisted 10s mark buckets, mark reference (MARKET_DATA §P1-08).
- Engine (`market_structure.py`, NEW, stateless over peer state): VWAP
  1m/3m/5m/15m + displacement; raw `sqrt(sum(r²))` vol 1m/5m/15m/1h
  (≥5 returns + window−10s span, grid-coverage `warmed`); range + position
  + median/z expansion over completed blocks; confirmed pivots (30s delay),
  HH/LH/HL/LL, swing distances, prior-15m-block breakout tags. Resilience
  deferred (DECISIONS).
- Persistence v6 (additive, tested v1..v5→v6): `structure_features`
  REPLACE-per-symbol; continuity inherited, never fabricated.
- Live 372s blocking run (exit 0, dashboard live): 11/11 streams, 2 public
  reconnects, 57954 skew-rejects (degraded bookTicker window — honest).
  STRUCT 27 evals (9 summaries × 3), latency p50 0.84ms/p95 1.26, queue
  0/0. FLOW 4111 + BOOK 1737 + OI 15/15 intact (peer regressions green).
  Sampling lossless (aggTrade 172 vs 4111). Safety 0/0/0. Live: VWAP disp
  +0.7..+1.1bps (raw only); 1m vol UNKNOWN — fresh mark buckets starved
  by rejects, reported honestly; swings (incl. ETH HH) from restored
  history proving continuity; breakouts UNKNOWN (thin prior block).
  11 funding crossings — same hypothesis class, no conclusions.
- Dashboard v0.7.0 at http://127.0.0.1:8091 (restarted, PID 30344):
  structure table + `/api/features/vwap|volatility|structure` live (200),
  health DEGRADED honestly; no buttons/controls/signals.
- Tests: 277/277 (38 new: 37 structure + v5→v6 migration). Five v5
  assertions updated to v6 (migration, expected).

## P1-09 market-intelligence terminal — RESULT: PASS (2026-10-09)

- IA: `OVERVIEW` (market summary cards, top activity, compact live-core
  rows linking to token pages) → `MOVERS` (market table + 8 categories:
  24h gainers/losers/most-active, HOT, live velocity ±, acceleration,
  volume expansion, aggressive-flow leaders) → `/symbol/:symbol`
  (header + mark-price SVG chart + momentum/flow/book/OI/VWAP-vol-
  structure panels) → `SYSTEM` (all P1-03…P1-08 diagnostics + API index).
  Search (`/search` + `/api/search`, case-insensitive partial over the
  persisted universe, escaped, deterministic). Capability vocabulary
  LIVE/WARMING/DISCOVERY ONLY/STALE/DEGRADED/UNKNOWN UI-wide, tier
  orthogonal (neutral chips). No signals, no controls, no private data.
- Code: `dashboard.py` (routing/health/lifecycle, v0.8.0) +
  `dashboard_data.py` + `dashboard_components.py` + `dashboard_views.py`.
  Chart/CSV: `GET /api/symbol/:symbol/price[?range][.csv]` over P1-04
  `price_samples` (5m/15m/1h/4h/24h, ≤1000 pts, oldest-first, no futures,
  400/404 semantics). Book integrity copy: HEALTHY / Recovered N gaps /
  DEGRADED — gap active (no more `OK (1 gaps)`).
- Tests: 312/312 (35 new P1-09: routing/search/movers/token/chart-CSV/
  UI-regressions/unicode/escaping; 3 old overview-table assertions moved
  to `/symbol/:symbol` as intentional IA evolution; P1-04…P1-08 APIs green).
- Live 360s blocking run (exit 0, dashboard live, BOT_MODE=observe):
  11/11 streams, 0 reconnects, 0 skew-rejects (healthy window), uptime
  99.7%, corrected lags p50 ~180–260ms, clock 1/1 ok (−137ms/356ms RTT).
  FLOW 11086 events p50 0.03ms; BOOK 10274, 0 gaps; OI 18/18 polls ok;
  STRUCT 33 evals p50 ~1.05ms; returns 236 samples/symbol over 18.38M ms
  span, 0 invalid/late; discovery 924→481 eligible, HOT [] (one interval,
  votes 1/2 — honest); 140 funding crossings (same hypothesis-artifact
  class, no conclusions); safety 0/0/0. Evidence: `logs/p1-09/`
  (local, git-ignored).
- Dashboard live at http://127.0.0.1:8091 (restarted, PID 7564, v0.8.0):
  health `ok` while fed; all 22 routes 200 (pages 9–49ms, APIs 2–30ms);
  BTC chart 1h=44pts/5m=26pts; search `btc`→BTCUSDT; discovery-only
  龙虾USDT (+54.08%) page 200 with DISCOVERY ONLY — NO LIVE DEEP FEATURES
  and no fake panels; BTC page WARMING + HEALTHY integrity; CSV
  `text/csv timestamp,price`; forbidden-language scan clean on
  overview/movers/token pages. P1-01R transport re-validation still owed
  before P1-10 (this window was healthy but is not the gated 30–60 min
  P1-01R run).

## P1-01R transport re-validation — RESULT: PASS (2026-10-07)

Run: `python -m microstructure_probe --duration 2700`, BOT_MODE=observe,
`runtimeSeconds: 2702.262`, exit 0, attached blocking (no detached child).
Evidence (local, git-ignored): `logs/p1-01r/probe-2700s.log` (4.5MB raw
console) + `logs/p1-01r/transport-summary.json` (extracted final_summary)
+ `logs/p1-01r/dashboard-health.json`. No keys, no orders, no capital, no
private APIs. No application-code changes in this phase.

Measured (from `final_summary`):

- Coverage: 11/11 streams active, `missingStreams: []`, `staleStreams: []`,
  `silentStreams: ["!forceOrder@arr"]` only (event-driven, correctly
  not-stale).
- Uptime: market 99.964765% (2699.097s), public 99.965575% (2699.119s).
  Attempts 1/1 per endpoint, 0 failures.
- Reconnects: 0 total (market 0, public 0); websocket errors 0.
- Messages: 2,259,664 total. bookTicker 958k/773k/375k (BTC/ETH/SOL);
  depth ~26k/symbol; markPrice 2699 updates; forceOrder 519; aggTrade
  30457/31289/9179.
- Delivery lag (corrected event lag): p50 171–251ms across all streams
  (aggTrade ~171–174ms, bookTicker 175–216ms, depth ~175ms, forceOrder
  174ms, markPrice 251ms); p95 199–390ms; max ~3.2–3.4s rare outliers
  simultaneous across streams (one transient ~3.3s stall, auto-recovered,
  no reconnect). Exchange-side E−T is milliseconds (bookTicker p50 0ms,
  depth p50 1–4ms), so the sub-second path delay is the delivery path to
  this host, not Binance.
- Skew guard: `timestampRejected: 0` (0.0% — vs 85% in P1-01).
- Gaps/silence: depth sequence gaps 0/0/0. Max cadenced silence 2.85s;
  forceOrder silent up to 66.9s — event-driven, correctly NOT stale.
- Errors: parse 0, payload 0. Processing p50 sub-ms (parse/metrics/
  detector); full-processing p50 ≤2.4ms, p95 ≤22ms; isolated max spikes
  (one 464ms aggTrade) with all queues 0/0 — no backlog, probe CPU fine.
- Clock sync 5/5 ok (25/25 samples); offset −254ms; RTT 340ms.
- Engines (regression watch only, no semantic changes): returns 507
  samples/symbol over 21.58M ms span, 0 invalid, 0 late; FLOW 70925
  events p50 0.043ms queue 0/0; BOOK 77081 msgs 0 gaps 0 crossed p50
  0.19ms; OI 132/132 polls ok 0 failures; STRUCT 267 evals p50 1.93ms
  queue 0/0; persistence inflight high-water 43, drained to 0.
- Discovery: 924 seen → 482 eligible; HOT 6 promoted over multiple scans
  with votes (multi-scan hysteresis working as designed).
- Detectors: 3701 `extreme_funding_rate` (same hypothesis-artifact class
  as P1-01/P1-05 — near-constant series, NOT signal validation),
  2 `large_liquidation_individual` (ETH SELL, real counted observations),
  22 `volume_spike` (real hypothesis-threshold crossings). No threshold
  conclusion drawn from any of these.
- Safety block in final summary: observe, 0 keys, 0 orders, 0 capital,
  no authenticated clients, no order paths.
- Dashboard (v0.8.0, PID 7564, left running): `ok` while fed (53.7s
  snapshot age at check); post-run `/overview`, `/movers`, `/system`,
  `/symbol/BTCUSDT`, `/api/health` all 200 (20–51ms); health transitioned
  honestly to `stale` 134s after probe exit (snapshot age >120s chip).

Verdict reasoning: every P1-01R gate passes on the full 45-minute window
— full coverage, 0 reconnects, sub-second p50/p95 delivery lag, 0%
rejections, sub-ms-typical processing with drained queues, 5/5 clock sync.
The single ~3.3s transient stall is rare-outlier grade (p99 ≤1.1s worst
stream), not P1-01-grade degradation. Therefore PASS: transport is healthy
enough for the P1-10 ≥6h soak. `docs/PHASE_1_REPORT.md` untouched.

## P1-10 prolonged soak — RESULT: FAIL, truncated at 4.91h (2026-10-07)

Run: `python -u -m microstructure_probe --duration 21600` (requested
21600s), BOT_MODE=observe, started 2026-10-07 05:15:41 local. Evidence
(local, git-ignored): `logs/p1-10/probe-21600s.log` (52MB, UTF-16 —
PowerShell stdout-redirect capture, long JSON lines wrapped; reconstructed
by rejoining wrapped fragments, proven by 0 runtime drops). No
checkpoint/final-summary sidecar files were written; all metrics below come
from the 554 periodic summaries (every ~30–32s) parsed out of the raw log.

Continuity: ONE process (`startup` × 1, no restart). Last periodic summary
`runtimeSeconds: 17677.917` (81.8% of 21600); log wall span 05:15:41 →
10:10:37 (~17696s); NO `final_summary`; tail ends mid-stream on detector
lines with no shutdown/traceback and the process is gone — externally
killed between summaries, exit code UNKNOWN. Max inter-summary gap 62s, no
gap >120s: no evidence gap *within* the run, but the run itself is
truncated. Duration gate (≥21600s continuous) NOT met → FAIL per
docs/SUCCESS_GATES procedure (duration invalid). Dashboard was NOT
restarted (PID 7564, v0.8.0, uptime 63283s spanning the whole run).

Full-window (END, rt=17677.9s) transport:
- Coverage 11/11, missing [], stale [], silent `!forceOrder@arr` only
  (event-driven, correct). Uptime market 99.65% (17613.6s), public 97.08%.
- Reconnects 43 total (public 38, market 5); attempts 45 (public 39,
  market 6); websocket errors 43 (= reconnects). Jump +29 reconnects in the
  final 55 min (14 → 43) — closing-phase reconnect storm, nearly all public.
- Messages 15,341,473. bookTicker p50 ~190–200ms / p95 ~321–465ms
  (HEALTHY, P1-01R-grade); depth p50 ~182ms but p95 ~45–47s; aggTrade SPLIT:
  BTC p50 214ms vs ETH p50 152s / SOL p50 90s (P1-01-grade); markPrice p50
  253ms but p95 132s; forceOrder p50 205ms–1.2s, p95 ~158–159s; max ~265s.
  Exchange-side E−T stays milliseconds (bookTicker p50 0–1ms), so the delay
  is delivery-path, not Binance. Mixed verdict: bookTicker core stayed
  P1-01R-grade while aggTrade (ETH/SOL), depth-tail, markPrice-tail and the
  final hour regressed to P1-01-grade. Prolonged stalls: max observed
  silence 51–133s incl. 132.5s on cadenced bookTicker/depth — real stall
  episodes, not sampling noise.
- Skew guard: `timestampRejected: 742182` (~4.8% of messages; rejects by
  stream worst on bookTicker/aggTrade). Far better than P1-01's 85%, worse
  than P1-01R's 0%. +366k rejects landed in the final 55 min (376k → 742k).
- Depth gaps 33/32/32 (reconnect-driven, all recovered, `degraded: false`
  at END, crossed books 0 — final book integrity HEALTHY).
- Clock 30/30 syncs ok (150/150 samples), offset −413ms at END, RTT
  338ms; full-run offsets min −1001.6 / max +47.1 / median −241.6ms, RTT
  319.6–376.2ms (median 336.3). One ~1050ms offset discontinuity between
  sync 6 (−1001.6) and sync 7 (+47.1), then steady drift to −413 — sync
  never failed, recorded as drift, not a gate break.
- Processing sub-ms typical (parse/detector/metrics p50 ≤0.03ms); isolated
  max spikes (941ms bookTicker metrics, 1660ms SOL aggTrade processing,
  1098ms markPrice) with all engine queues 0/0 — absorbed, no backlog.

Engines (all alive at END, 0 invalid / 0 late everywhere):
- Returns: 1867 samples/symbol over 58,830,000ms span (16.34h incl.
  restored history), 0 invalid, 0 late. 1m/3m/5m/15m/1h/4h mature; 24h
  partial (16.34h/24h, honest).
- Flow: 502,191 events (BTC 222513 / ETH 228183 / SOL 51495 trades),
  latency p50 0.017ms / p95 0.085 / max 64.6, queue 0/0, 2103 completed
  10s-buckets/symbol (~5.8h live) — 15m maturity + volume baselines mature.
- Book: 388,570 msgs (130853/131465/126252), p50 0.19ms / p95 0.33,
  gaps 33/32/32 all recovered, crossed 0, integrity HEALTHY.
- OI: 813/813 polls ok (0 failures), latency p50 341ms / p95 3028 /
  max 10190 (slow polls absorbed); tracker 332 samples/symbol (271 total);
  1m/5m/15m + acceleration mature.
- Structure: 1659 evals, p50 5.9ms / p95 10.2, queue 0/0; pivots/HH-LH/
  HL-LL/breakout/range all evaluating (maturity inherited from 16.34h span).
- VWAP 1m/3m/5m/15m + volatility 1m/5m/15m/1h available (zero stays 0.0,
  distinct from unknown, per P1-08 contract).

Discovery/HOT (proposal/discovery only — no WS resubscribe, trio intact):
30 scans (600s cadence × 4.91h), seen 924 constant, eligible 486 → 496.
HOT 6-slot rotation with vote/dwell hysteresis working (26 promote/demote
events embedded in scan records; END set: AIN/MINA/AIOT/RLC/CAP/龙虾USDT;
earlier windows held NMR/GRIFFAIN/LYN/PHA — rotation, not flapping).

Dashboard long-run: all routes 200 during post-mortem
(`/overview` 49.6ms, `/movers` 12ms, `/system` 6.4ms, token pages 9–22ms,
`/api/health` 21.5ms, `/api/snapshot` 3.7ms, search 7.2ms). Health `stale`
honestly (snapshot 22520s old — probe dead, expected); was `ok`-while-fed
per 749 persisted snapshots. 9/9 movers categories render; discovery-only
honesty holds (AINUSDT page: DISCOVERY ONLY + NO LIVE DEEP FEATURES).
Chart: 4h MATURED during soak (16.34h span); 24h PARTIAL (16.34h/24h,
capped 1000 pts, restored-history dependent). Post-mortem trailing-4h
query returns 0 pts — honest staleness artifact (feed 6.25h old), not a bug.
Movers anomaly CONFIRMED by code inspection (`dashboard_views.py`
movers section: shared per-row `_v` overwritten by each later category
loop, so a symbol in several categories shows the last-assigned value in
every table — velocity/accel/vol-z/flow scales mixed). Recorded as a
P1-11A audit item; NOT fixed during closure.

Persistence (DB `data/microprobe.db`, schema v6, ~197MB at END; start size
not captured — unavailable, not guessed): snapshots 749 (cap 1000, holds;
min rt 32.19 / max rt 17677.917 — this run's 554 + prior runs retained),
observations 10000 (cap holds), rejections 1000 (cap holds), price_samples
5601 (16.34h span), flow_buckets 4710 bounded (600/597/304/69 per
size/symbol), oi_samples 996, return/flow/book/OI/structure features 3
each (REPLACE latest-only), discovery snapshot 1 (REPLACE), universe_events
46 (cap 500), rank snapshots 3. Write errors 0, lock errors 0, no snapshot
starvation (dedicated writer held), persistence inflight high-water 5063 →
final 0, drained to 0. Sampling gate intact (accepted 34k/40k/39k vs
dropped 468k/13.6M/349k aggTrade/bookTicker/depth; markPrice/forceOrder
ungated and fully ingested).

Resources: RSS/CPU NOT captured by the probe (UNAVAILABLE — do not infer
from DB size). Backpressure bounded everywhere (engine queues 0/0,
inflight 0, dashboard ms-grade post-mortem).

Errors (full 4.91h): websocket 43 (38 public + 5 market) CONCERNING in the
final hour (storm) / RECOVERED earlier; parse 0, payload 0, invalid engine
events 0, late events 0; timestamp rejects 742182 (~4.8%) CONCERNING
(final-hour concentration); persistence errors 0; SQLite errors 0; OI REST
failures 0/813; depth gaps 97 total, all recovered (RECOVERED); dashboard
HTTP errors 0 (post-mortem 200s); reconnects 43 CONCERNING. None BLOCKING
except the duration gate itself.

Detectors (telemetry only, NOT signals): `extreme_funding_rate` 16512 log
lines (crossings BTC 5417 / ETH 4960 / SOL 6095 — near-constant series:
175–176 valueChanges over 13519 samples; same hypothesis-artifact class,
no conclusions); `large_liquidation_individual` 25 (all SELL: 8/12/5);
`large_liquidation_window` 8 (1/4/3); `volume_spike` 102 (36/35/31). No
threshold tuned.

Safety: BOT_MODE=observe in startup + all 554 summaries; apiKeysUsed 0,
authenticated clients false, realOrdersSent 0, cancels 0, leverage changes
0, private/account endpoints 0, capital at risk 0, order paths absent
(static test green). NO VIOLATION.

Checkpoints (reconnects / rejects / msgs / gaps / flow / HOT):
START rt32: 0 / 0 / 16k / 0s / 349 / [] → T+1h: 6 / 125k / 3.07M / 3s /
108895 / 5 HOT → T+2h: 10 / 231k / 5.90M / 7s / 192706 / 6 HOT → T+3h:
10 / 231k (flat — healthy middle third) / 9.20M / 7s / 292131 → T+4h:
14 / 376k / 12.51M / 11s / 409250 → END rt17678: 43 / 742k / 15.34M /
33s / 502191. Drift story: healthy middle (T+2h→T+3h: 0 new reconnects,
0 new rejects over 3600s), degraded bookends, collapsing final hour.

Verdict reasoning: gate A (one continuous run ≥21600s) fails — 17677.9s
is the proven maximum, no final_summary, unclean externally-killed exit.
Per the closure rubric FAIL is forced ("duration invalid"); PARTIAL does
not apply (the run did not complete). Safety is clean, engines/persistence
/dashboard all behaved, but transport showed sustained P1-01-grade episodes
(aggTrade ETH/SOL p50 90–152s, final-hour storm). The 4.91h of evidence is
VALID for P1-11 raw-feature auditing (monotonic, gap-free summaries), but
P1-10 itself must be re-run (P1-10R) with a survivable launch before any
gate may pass. `docs/PHASE_1_REPORT.md` untouched.

## P1-11A raw feature + Movers integrity audit — RESULT: PASS (2026-10-07)

Used the valid P1-10 4.91h evidence (554 gap-free summaries, 15.34M msgs;
P1-10 stays FAIL on duration — not marked PASS). Baseline before work:
312/312 PASS. No strategy/backfill/classifier/subscription/signal/paper
work started.

Movers bug — FOUND, ROOT-CAUSED, FIXED NARROWLY: `render_movers`
(`dashboard_views.py`) shared one per-row `_v` across all 9 category loops
(last write won: symbols in several tables showed e.g. the flow value in
the gainers table). Source→render audited per category (DISCOVERY: 24h
gainers/losers → `change_24h_pct` sorted by signed 24h %, shown `+%.2f%%`;
quote-volume leaders → `quote_volume_24h`; HOT → "proposed". LIVE,
subscribed-only: velocity ± → `velocity_1m` (`%.3g/s`); acceleration →
`accel_1m` (`%.3g/s²`, sorted by |accel|); volume expansion →
`vol_z_1m` (`%+.2f z`); aggressive-flow → `flow_delta` (`%+.2f`, sorted by
|delta|)). Fix: per-category display keys passed to the renderer; sources,
sorts, units, formatters unchanged. Proven: new `MoversIntegrityTest`
(5 tests, unique fixtures) fails 4/5 on old code, passes 5/5 fixed.

Feature verdicts (END-state rows + START/END summaries; full scales in
`docs/FEATURE_MODEL.md`): returns 1m/3m/5m/4h live with sane log scales
(15m/1h/24h honestly UNKNOWN after the degraded finale); velocity/accel
scales 1e-6–1e-5 /s and 1e-7–1e-8 /s² with correct warming gates; flow all
6 horizons + baselines + accel present (ratios in [−1,+1], units USD
notional, BTC>ETH>SOL ordering); book spreads 0.012–0.86bps, imbalances in
[−1,+1], 0 crossed, gaps recovered; OI base-unit units verified with mixed
horizon signs and coherent anchors; VWAP ±4.6bps; vol warmed flags honest
(UNKNOWN ≠ 0); range positions in [0,1]; structure evaluating on 16.34h
span. No impossible values, no unit mismatches, no malformed transitions.
Funding crossings re-confirmed artifact-class (near-constant series).

Transport impact (healthy T+2h→T+3h vs degraded T+4h→END): 918 msg/s 0%
rejects 0 reconnects 0 gaps vs 867 msg/s 12.9% rejects 29 reconnects 64
gaps. Feature effect: returns span still grew (+360 vs +129 samples); flow
−6.5%; book ingest −64% (depth starved, integrity HEALTHY); structure
−19%; OI ISOLATED (0 failures both). Degradation starves honestly, never
corrupts — classifiers must take UNKNOWN/staleness as first-class input.

Design-only plans added (nothing implemented): BTC context + relative/
correlation/beta/lead-lag, exhaustion/absorption research, opportunity
lifecycle, backtest/paper sim costs (`docs/SIGNAL_RESEARCH_PLAN.md`);
P1-11B resolutions + P1-11C event studies with MFE/MAE/no-lookahead
(`docs/HISTORICAL_RESEARCH_PLAN.md`); roadmap P1-11A→…→P1-16 in TASK_QUEUE.
Tests after: 317/317 (312 + 5 new). `docs/PHASE_1_REPORT.md` untouched.

## P1-11B historical data foundation — RESULT: PASS (2026-10-07)

Official docs first: developers.binance.com unfetchable here (empty
responses, same as P1-05) → all seven contracts verified LIVE against
fapi.binance.com (public, no keys, ~35 tiny requests) + OpenAPI enum
cross-check; recorded exactly in `docs/MARKET_DATA.md` (params, limits
1500/500/1000, weights measured ~1/1/20, intervals, startTime/endTime
edge behavior, 2400/min pool).

Built (stdlib only): `history_client.py` (conservative weights + adaptive
weight-header hard pause 2000/2400; retries budget 5 exp-backoff+jitter;
429 honors Retry-After budget 2 then abort; 418 aborts; forward pagination
with overlap-raise + skip-record; OI timestamp pagination; aggTrades fromId
helper) + `history_store.py` (separate `data/historical/historical.db`,
schema v1: klines WITH volume / mark klines WITHOUT volume columns /
OI as-served / coverage / run ledger / gaps) + `history.py` CLI (status /
fetch / verify; explicit symbols, 7d/25 defaults, no bulk mode).
Listing-aware (geneses recorded: BTC Sep-2019, MINA Feb-2023, ORCA
Dec-2024); CLOSED candles only; gaps stay UNKNOWN/GAP (no fill).

Pilot (bounded): 1h×30d klines ×5 syms (719 each), 15m×30d ×3 (2879),
1m×3d BTC (4319), 1h×30d mark ×3 (719) — all ratio 1.0, 0 gaps, 0 malformed;
5m×7d OI BTC hit the 500-row availability cap (~41.6h — documented
limitation); aggTrades confirmed recent-only (0.1 min). Resume re-run: 0
rows, 1 request (idempotent). 13 series stored. No backfill beyond pilot.

Minimal exposure: `/api/history/status` + `/api/history/:symbol`
(404-empty/unknown, 400-malformed) + HISTORICAL COVERAGE token card; no
Opportunities/Signals/Paper/Backtest UI. Storage tiers + prospective
flow/book retention + fidelity contract in HISTORICAL_RESEARCH_PLAN.md /
FEATURE_MODEL.md. Tests after: 353/353 (322 + 31 new mocked-HTTP history
tests). `docs/PHASE_1_REPORT.md` untouched.

## P1-11B.1 probe lifecycle + dashboard run control — RESULT: PASS (2026-10-07)

Canonical manager `control.py` (registry `logs/probe_runtime.json` with
pid/ctime/started/mode/duration/expected-end/launcher/preset/evidence/
last-exit; CLI status/start/stop). Probe self-registers on EVERY direct
launch (`__main__`; refuses with exit 2 when another probe holds the
registry; COMPLETED/FAILED/STOPPED marked on exit; registry failures never
break collection). Single-instance refusal; stale-PID recovery to FAILED;
stop kills only the verified PID (bounded 10s wait). All control-started
probes get merged UTF-8 file logs (`logs/probe-runs/`, validation preset
`logs/p1-10r/`). Dashboard: `GET /api/control/probe/status` (process +
feed separated) + POST-only start/stop (localhost Host + local Origin +
per-process nonce; GET mutations 405; fixed argv, BOT_MODE forced observe,
no shell) + MARKET ENGINE header block on all pages (no `<button>`, 4s
polling, green/gray/amber/red). Modes: Continuous, 6 Hours, 6H Validation
(evidence mechanics — NOT an automatic P1-10R PASS).

Live-verified (short bounded only, no 6h started): dashboard START →
RUNNING PID 16336 (tasklist-confirmed) → feed STALE→ok honestly →
dashboard STOP killed only the probe (dashboard survived); external CLI
start (--duration 90/75) auto-discovered as RUNNING/launcher=agent in UI;
90s run self-marked COMPLETED duration-reached; CLI stop → STOPPED.
Tests after: 376/376 (353 + 23 new mocked lifecycle/API tests).
`docs/PHASE_1_REPORT.md` untouched.

## P1-11C historical event studies + prospective capture — RESULT: PASS (2026-10-07)

- Engine (`events.py`, NEW, research-only, no signals): formation uses
  bars with open_time <= T only; outcomes use open_time > T only (proven
  by no-lookahead tests incl. poisoned-future reruns). Reference price =
  closed bar close at/preceding T, labeled mark_close vs regular_close
  (never silently mixed). Fixed horizons 1m/3m/5m/15m/30m/1h; LONG-up
  MFE/MAE + SHORT-down mirror; time_to_MFE/MAE; predeclared invalidation
  only; path COMPLETE/PARTIAL/INVALID_GAP/INSUFFICIENT_HISTORY (never
  filled); formation/outcome gap exclusions; BTC synchronized lookup +
  relative_return = token − BTC; 30d as-of levels; HISTORICAL_TAKER_BUY_
  PROXY + ABSORPTION_PROXY labels; sample tiers
  INSUFFICIENT/EXPLORATORY/PRELIMINARY/LARGER_SAMPLE (quantity only).
- Definitions: 6 versioned HYPOTHESIS families (EXTENDED_GAINER/LOSER,
  MOMENTUM_ACCELERATION_UP/DOWN as HISTORICAL_MOMENTUM_PROXY, FAILED_
  HIGH/LOW_CANDIDATE); changing a threshold creates a new version; runs
  recorded with params/symbols/ranges/sources (deterministic reruns).
- Storage: historical DB schema v2 (additive over v1): event_definitions,
  event_study_runs, event_instances, event_feature_snapshots,
  event_outcomes + research_flow_10s/1m + research_book_1m (idempotent
  keys; retention cleanup batched/hourly, never per-tick).
- Recorder (`research_recorder.py`, NEW, probe-owned): starts with
  MarketProbe, drains (partials marked) on exit; same process/registry/
  launcher — no second manager. Bounded queue (drops counted, engine
  never stalls); DB failures degrade the recorder only (probe survives,
  tested). Flow semantics reuse validated P1-06 m-mapping read-only.
  Retention 7d/90d/90d configurable; measured estimate ~200B/row →
  ~66KB/day/symbol flow-10s + ~288KB/day/symbol each 1m table (~35MB for
  15 symbols at full retention).
- Live verification (canonical control plane, 150s → COMPLETED
  duration-reached, evidence `logs/probe-runs/probe-20261007T224304Z.log`):
  runtime 153.15s, flow 1722 events, book 4042 msgs, research writes 60
  (flow_10s 45 + flow_1m 9 + book_1m 6 rows), drops 0, errors 0,
  inflight 0, high_water 2, final_summary present. Dashboard restarted
  (PID 30984): /api/research/status + /api/events/studies +
  /api/events/studies/:def + /api/events/symbol/:sym all 200; control
  status/start/stop/external-detection intact; 6H-Validation preset
  verified compatible (forces 21600s, same registry/evidence path —
  NOT started).
- Pilot (bounded, stored bars only): 38 runs — 1h × (BTC/ETH/SOL/MINA/
  ORCA/NMR) × 6 families + 15m × trio GAINER/LOSER. NMR added by a
  justified 2-request extension (719 bars, ratio 1.0, ~144KB). Counts:
  GAINER 168 usable (mean fwd −0.04bps), LOSER 67 (−25.8bps), ACCEL_UP
  1170/1203 (+8.7bps), ACCEL_DOWN 1147/1184 (+4.4bps), FAILED_HIGH 18/19,
  FAILED_LOW 8/10. Sub-1h horizons on 1h bars share the next-bar outcome
  (resolution limitation, documented). No profitability/edge claim; small
  samples flagged INSUFFICIENT/EXPLORATORY.
- Tests: 408/408 (376 + 32 new: 18 events incl. no-lookahead/MFE-MAE/
  gaps/BTC/relativity/as-of/proxy/versioning/idempotency/no-autotune +
  14 recorder incl. buckets/quality/retention/queue-drops/isolation/
  lifecycle/no-second-process). `docs/PHASE_1_REPORT.md` untouched.

## P1-10R formal ≥6h soak re-run — RESULT: PASS (2026-10-08)

Run: ONE continuous WMI-detached process (PID 19084; parent chain
python → cmd → WmiPrvSE Session 0, independent of all agent shells),
`--duration 21600`, preset validation-6h, launcher
scheduler-6h-validation, BOT_MODE=observe. Started 2026-10-08T00:48:20Z,
final summary 2026-10-08T06:48:23Z: **21603.9s ≥ 21600s**. Registry
COMPLETED + duration-reached + exit 0; process exited (no orphan); 1
startup; 699 periodic summaries, max inter-summary gap 49.7s, 0 gaps
>120s. Evidence (local, git-ignored):
`logs/p1-10r/probe-20261008T0048Z.log` (33.3MB merged UTF-8) +
`logs/p1-10r/P1-10R_HANDOFF.md`. No app-code changes during the run
(proven: empty `git log` on src/tests/config since launch baseline).

Transport (vs P1-01R healthy precedent and P1-10 degraded finale):
- Coverage 11/11 all 6h, missing [], stale []. 19,004,903 messages
  (bookTicker 17.77M, depth 590k, aggTrade 595k, markPrice 42k,
  forceOrder 8.8k).
- Reconnects 10 total (public 4 × ConnectionClosed, market 6: 1
  ConnectionClosed + 5 opening-handshake TimeoutErrors with 2→30s
  backoff); attempts 12, parse 0, payload 0.
- Skew-rejects 143,624 (0.76%); uptime market 99.10% (21406s),
  public 99.95%.
- Corrected delivery lag p50 ~170–250ms every stream (P1-01R-grade);
  p95 sub-second except sparse forceOrder; p99 ≤0.66s (forceOrder
  excluded: event-driven). Rare single-message max outliers (~311–510s)
  with steady neighboring throughput — isolated, not episodes.
- Episodes (all auto-recovered, none hidden in averages): ~01:29–01:32Z
  (public reconnect, ~24k rejects); ~02:31–02:35Z (public reconnect,
  ~37k rejects); ~04:20–04:29Z (~9.5min: market handshake timeouts,
  6 market + 1 public reconnects, ~82k rejects, market-stream silence
  ≤192s). Final hour rt 18007→21590: 0 reconnects, 0 rejects, 3.07M
  msgs — NO P1-10-style final-hour collapse.
- Depth gaps 5/5/5 total (reconnect-driven), all recovered
  (degraded=false, crossed 0 at END). Clock 36/36 syncs ok, 0 failures
  (offset −582ms → −208ms, RTT ~343ms).

Engines (all monotonic, 0 invalid / 0 late everywhere): returns 3886
samples/symbol over 31.5h span (restored + live); flow 566,244 events;
book 587,330 msgs; OI 1029/1029 polls ok (p50 347ms, slow polls
absorbed); discovery 36 scans (924 seen → 467 eligible, HOT 6 with
hysteresis); structure evaluating (symbols_evaluated). Detectors are
telemetry only: 22622 funding crossings (same hypothesis-artifact
class), 11 individual + 1 window liquidations, 181 volume spikes — no
threshold conclusions.

Research recorder (P1-11C validation): RUNNING all 6h → drained STOPPED;
writes 8273, drops 0, errors 0, inflight 0, high-water 6. Rows added:
flow_10s +6191 (vs ~6480 est, 95.5%), flow_1m +1041 (~96%), book_1m
+1041 (~96%) — shortfall is the documented stall episode plus edge
partials, no unexplained loss. Historical DB +1.58MB (16.47 → 18.05MB),
integrity ok; operational DB 206.9 → 238.9MB (retention caps hold:
snapshots at 1000), integrity ok; persistence errors 0, locks 0.

Dashboard: alive throughout and after (PID 30984); feed/health states
independent and truthful (STALE chip after completion is honest — last
snapshot is the 06:48:23Z final). No phantom RUNNING. The known
tasklist/wmic popup defect (P1-10R-FIX-01) stayed cosmetic: 2 spawns
per 4s poll, negligible overhead, no evidence impact; fix deferred to a
separate post-soak change (CREATE_NO_WINDOW), NOT applied here.

Safety: BOT_MODE=observe in startup + final; apiKeysUsed 0,
authenticated clients false, realOrdersSent 0, capital 0, no order
paths (static tests green). NO VIOLATION.

P1-10 failure mode eliminated: the old run died externally at 4.91h
with an unhealthy finale; P1-10R survived its full window in a
session-independent process AND its worst transport episode (~9.5min)
self-recovered with 3.5 clean hours after it.

## Known gaps (Phase 1 work ahead, in order)

Minimal dashboard: DONE (P1-03 PASS) → terminal DONE (P1-09 PASS,
v0.8.0 live at http://127.0.0.1:8091).
Returns engine: DONE (P1-04 PASS — universe + 7-TF mark-price log returns).
Discovery + velocity/acceleration/ranking: DONE (P1-05 PASS — 449-eligible
scan, 6-HOT proposal, live momentum + ranks, intel UI + APIs).
Movers integrity + raw-feature validation: DONE (P1-11A PASS — per-category
display keys, 5 regression tests, all families measured trustworthy).
Volume + aggressive flow: DONE (P1-06 PASS — 6-horizon flow, baselines,
acceleration, v0.5.0 dashboard + APIs, healthy 363s validation).
Order book + open interest: DONE (P1-07 PASS — snapshot book intel, OI
polls/deltas/contexts, v0.6.0 dashboard + APIs, 363s validation).
VWAP + volatility + structure: DONE (P1-08 PASS — flow-VWAP, raw vol,
range expansion, confirmed pivots, v0.7.0 dashboard + APIs, 372s run).
Transport re-validation: DONE (P1-01R PASS — 45min healthy window, soak
gate unblocked).
Remaining: P1-12 state classifier v0 (READY — P1-11C PASS + P1-10R PASS;
starts only on explicit instruction; thresholds stay HYPOTHESIS), then
signal UI (P1-13), calibration evidence (P1-14). P1-11 raw-feature validation may use the valid
4.91h P1-10 evidence; the Movers shared-`_v` category-value anomaly is a
recorded P1-11A audit item (not fixed).

## Blockers / issues

- P1-10 FAIL (2026-10-07): soak killed externally at 4.91h/6h (17677.9s),
  no final_summary, exit unknown. P1-10R re-run required before any soak
  gate passes; launch must survive the full window (see DECISIONS) and
  capture merged stdout+stderr as UTF-8 (the P1-10 UTF-16 PowerShell `>`
  capture wrapped every long JSON line and had to be reconstructed).
- Transport was flaky in this environment (P1-01 PARTIAL: 58 reconnects,
  85% rejects), but P1-01R (45min, 0 reconnects, 0% rejects, sub-second
  lags) now PASSES the soak gate. If a future run shows P1-01-grade
  degradation again, re-validate before trusting soak/calibration gates.
- Detached probe processes die with the harness tool session (observed twice):
  use blocking bounded runs for evidence windows.
- Dashboard RUNNING at http://127.0.0.1:8091 (PID 7564, v0.8.0; read-only,
  localhost — safe to keep). Snapshot goes STALE without a running probe
  feed (honest chip); continuous freshness arrives with the P1-10 soak.
- No secrets, keys, or account access exist or are needed.
