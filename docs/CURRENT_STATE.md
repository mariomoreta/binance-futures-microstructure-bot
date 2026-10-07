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

## Known gaps (Phase 1 work ahead, in order)

Minimal dashboard: DONE (P1-03 PASS) → terminal DONE (P1-09 PASS,
v0.8.0 live at http://127.0.0.1:8091).
Returns engine: DONE (P1-04 PASS — universe + 7-TF mark-price log returns).
Discovery + velocity/acceleration/ranking: DONE (P1-05 PASS — 449-eligible
scan, 6-HOT proposal, live momentum + ranks, intel UI + APIs).
Volume + aggressive flow: DONE (P1-06 PASS — 6-horizon flow, baselines,
acceleration, v0.5.0 dashboard + APIs, healthy 363s validation).
Order book + open interest: DONE (P1-07 PASS — snapshot book intel, OI
polls/deltas/contexts, v0.6.0 dashboard + APIs, 363s validation).
VWAP + volatility + structure: DONE (P1-08 PASS — flow-VWAP, raw vol,
range expansion, confirmed pivots, v0.7.0 dashboard + APIs, 372s run).
Transport re-validation: DONE (P1-01R PASS — 45min healthy window, soak
gate unblocked).
Remaining: ≥6h soak (P1-10, may start on instruction), state classifier
(P1-12, still blocked on P1-11), signal UI (P1-13), calibration evidence
(P1-14).

## Blockers / issues

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
