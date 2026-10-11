# Old dashboard read contracts — backend audit for Dashboard V2 (DASH-V2-64)

Date: 2026-10-11. Scope: read-only source audit of the legacy Python
dashboard (`dashboard.py` + `dashboard_data.py` + `dashboard_views.py`);
no code, route, formula, or data change. Backend base `c635938`, reconciled
by fast-forward from `da231b9` (clean worktree, no active Python process,
terminal COMPLETED registry). V2 branch `dash-v2-03-token-detail`
checkpoint `8780da2` read from Git only.

Deployed-source identity: V2 `runtime-control.ts` spawns Python with
`cwd` + `PYTHONPATH` = `C:/proyectos/binance-futures-microstructure-bot`
(`/src`), calling `control.status_readonly()`; V2 SQLite reads use
`DatabaseSync readOnly:true` on the canonical
`data/microprobe.db`. After the fast-forward, deployed source == accepted
checkpoint `c635938`, closing the cutover audit's da231b9-vs-remote split
on this checkout. SHA verification is MANUAL (exact-SHA audit scripts and
review checkpoints): the V2 bridge does NOT inspect Git SHA on every
consumption and no automatic pinned-version guard is claimed.

Conventions below: `generated_at` on JSON APIs is RESPONSE time
(`strftime(gmtime())`), never observation time. Empty stores answer 404
with an explicit error (never fixtures, never zeros). Timestamps are ISO
UTC strings or epoch ms as noted; `null` means unknown/absent, never zero.

## 1. GET route inventory (old HTTP server, 127.0.0.1, ThreadingHTTPServer)

Pages (server-rendered HTML, no `<button>`, no controls):

| Route | Params | Source |
|---|---|---|
| `/` | — | 302 to `/overview` |
| `/overview` | — | market cards + top activity + live-core rows (`render_overview`) |
| `/movers` | — | composed workbench table (`movers_table`) |
| `/search?q=` | `q` raw string | `render_search` (see §2) |
| `/system` | — | stream table + clock + persistence + safety (`render_system`) |
| `/opportunities` | — | research candidates + lifecycle (`render_opportunities`) |
| `/symbol/:symbol[?range=]` | symbol validated; `range` in 5m/15m/1h/4h/24h, default 1h | 400 invalid symbol/range; 404 unknown symbol; else `render_symbol` |

JSON APIs:

| Route | Key fields / units | Empty |
|---|---|---|
| `/api/search?q=` | `{query, results[]}` (see §2) | `[]` (empty query → `[]`, never error) |
| `/api/symbol/:s/price[?range=]` | `{symbol, source:"markPrice", range, generated_at, points[{timestamp ms, price}], points_total, points_returned, truncated, point_limit}`; price unit = quote price (USDT); timestamp = event-time bucket ms | 400 invalid symbol/range; 404 unknown symbol (not in universe); `insufficient:true` when 0 points |
| `/api/symbol/:s/price.csv[?range=]` | `text/csv`, `timestamp,price` lines, filename `{SYM}-{rng}.csv` | same 400/404 as JSON |
| `/api/health` | `{status, version, uptime_seconds (server process), server{...}, feed{status, snapshot_age_seconds, reasons}, host, persistence_reachable, latest_snapshot_timestamp, snapshot_age_seconds, stream_summary{expected, active, stale[], missing[]}, bot_mode, safety{apiKeysUsed, realOrdersSent, realCapitalAtRisk}, reasons}`; ages in seconds (float, 1 decimal); snapshot age null when no snapshot | always 200 (degrades to UNKNOWN fields) |
| `/api/control/probe/status` | pure `status_readonly()` + feed block (see §4) | always 200 |
| `/api/control/probe/start\|stop` (GET) | — | 405 POST required |
| `/api/history/status` | `{generated_at (response time), source:"historical research store (REST bootstrap)", series[]}` (separate historical DB) | 404 no coverage yet |
| `/api/history/:symbol` | `{symbol, series[]}` | 400 invalid; 404 no coverage |
| `/api/snapshot` | raw persisted telemetry snapshot verbatim | 404 no snapshot yet |
| `/api/features/returns` | `{generated_at, source:"markPrice", semantics, features[]}`; log returns per horizon, unavailable = null | 404 |
| `/api/features/momentum` | above + `velocity_semantics` (per-second), `acceleration_semantics`, `ranks{}`, per-symbol `{symbol, tier, current_price, sample_age_ms, warmup_complete, momentum, ranks}`; velocity unit 1/s, acceleration 1/s² | 404 |
| `/api/discovery` | architecture note + subscription note + `discovery` blob + `events` (universe_events limit 20) | 404 |
| `/api/features/flow` | `{source:"aggTrade", aggressor/quantity semantics, horizons[10s..15m], baselines[10s..5m], delta_semantics, symbols[]}`; notionals in USDT, delta_ratio in [-1,+1] | 404 |
| `/api/features/volume` | trailing completed-bucket quote notionals; `z_score` null on thin/zero-variance history | 404 |
| `/api/features/book` | `{source:"depth20@100ms", imbalance in [-1,+1], microprice, slopes, concentration (null when band unspanned), integrity_note}`; spreads in bps | 404 |
| `/api/features/open-interest` | `{source:"GET /fapi/v1/openInterest", actual-timestamp anchors, descriptive contexts}`; OI in base units, deltas signed | 404 |
| `/api/features/vwap` | `{source:"aggTrade via flow aggregates", horizons[1m..15m]}`; displacement in bps (raw) | 404 |
| `/api/features/volatility` | `{source:"markPrice 10s buckets", raw sqrt-sum-squared (not annualized), horizons[1m..1h]}`; null until ≥5 returns + span | 404 |
| `/api/features/structure` | `{confirmed pivots (30s delay), breakout tags (descriptive)}` | 404 |
| `/api/research/status` | `{source, note, research{writes/drops/errors/inflight/high_water, row counts}}` | always 200 (zeroed when absent) |
| `/api/events/studies` | `[{definition, version:1, horizons[]}]` over EVENT_FAMILIES | always 200 (`[]` when absent) |
| `/api/events/studies/:def` | `{definition, version:1, horizons, note}` | always 200 (empty horizons when unknown) |
| `/api/events/symbol/:sym` | `{symbol, events[{event_id, definition, version, event_time, direction, context, reference_price, reference_source}], note}` limit 50, newest first | 400 invalid symbol |
| `/api/opportunities` | `{generated_at, note, schema_version:1, rules_version:"v0.1.0", candidates[], lifecycle_events[:20]}` | always 200 (`[]`) |
| `/api/prospective` | `{generated_at, note, schema_version:9, prospective{setup_count, outcome_count, latest_outcomes[:10], recorder counters}}`; horizons 1m/5m/15m/1h/4h | always 200 |
| unknown route | `{error}` | 404 |

POST control (unchanged, NOT enabled beyond current design): start/stop
only, localhost Host + local Origin + per-process nonce (403 otherwise);
start validates duration/preset allowlist (200/409/500); stop
(200/404/409). GET on them is 405. No trading surface exists.

## 2. Universe / search contracts (priority)

- `normalize_symbol`: strip/upper; length 6..34; must end `USDT`; prefix
  chars unicode-alnum or `_-.'; rejects `/ ? & # < > " ' ` space %`.
  NOTE vs V2-64 audit: Python accepts MORE than ASCII A-Z0-9 (e.g.
 龍虾USDT flows through). Current V2 search uses retained records with
  max 50 and ASCII query validation (vs old max 25 + broader parser), so
  Unicode symbols and differing source unions are not full parity. Never
  join external tokens on symbol alone.
- `search_symbols(query, rows, limit=25)`: case-insensitive partial over
  persisted universe rows only (tops + core + hot + live); full exchange
  listing intentionally NOT persisted. Order: exact, prefix, substring,
  alphabetical within groups; query truncated to 32 chars; empty → `[]`.
- `compose_universe`: live_symbols = union of return/flow/book/OI/
  structure feature symbols; disc_rows from tops(gainers/losers/
  most_active) + core + hot_dynamic; core falls back to sorted live set.
- `movers_table` row: `{symbol, tier, capability, subscribed, price,
  change_24h_pct, quote_volume_24h, ret_1m/5m, velocity_1m, accel_1m,
  flow_delta (USDT signed), flow_ratio, vol_z_1m, sample_age_ms}`.
  Discovery-only 24h fields never mix with live fields without the
  per-row capability (`capability_for`: UNKNOWN / DISCOVERY ONLY / STALE /
  DEGRADED / WARMING / LIVE).
- Persisted already: tops/core/hot snapshot, all feature rows, universe
  events (limit 20), ranks. Absent by design: full listing, live
  subscription proof (subscribed = retained deep evidence only).

## 3. Historical coverage / event studies (priority)

Two different files — never conflate them by name alone:
(a) the prospective archive lives INSIDE canonical `microprobe.db`
(`prospective_setups` / `prospective_outcomes`, schema v9, §prospective
API above); (b) coverage + event studies live in the SEPARATE
`data/historical/historical.db` (`HistoryStore`, `history_meta` schema2).

- Coverage reads the separate historical DB (`coverage_summary()`);
  per-symbol filter is exact uppercased match. 404 when absent.
  Units/limits follow `docs/MARKET_DATA.md` + history contracts
  (klines/mark/OI availability caps); not duplicated here. A stored
  coverage row with zero bars and null span/ratio must be preserved
  as-is, never upgraded from neighboring datasets; ratio 1.0 is the
  recorded interval result, not current completeness.
- `event_studies()`: one `{definition, version:1, horizons}` per
  EVENT_FAMILY via `event_summary(fam, 1)`; `[]` on any error. Legacy
  AVG(forward_return) includes all non-null outcome rows while n_usable
  is a separate count — do not silently change the statistical
  population; methodology changes are separate research tasks.
- `event_summary(def, 1)` rows: per-horizon aggregates (served as-is).
- `event_symbol(sym, 50)`: fixed column list, `ORDER BY event_time DESC
  LIMIT 50`, uppercased symbol; `[]` on any error. `event_time` semantics
  per stored rows (no-lookahead formation documented in P1-11C).
- Absent: study-definition management UI, cohort/MFE-MAE aggregation
  endpoints, timeline persistence (separate proposal).

## 4. Price ranges + CSV/JSON export contracts (priority)

Old contract (`price_history_points`, source = persisted P1-04 10s
mark-price buckets, NO new source):

| Range | Window seconds | Anchor |
|---|---|---|
| 5m | 300 | request time (`now`) |
| 15m | 900 | request time |
| 1h | 3600 | request time |
| 4h | 14400 | request time |
| 24h | 86400 | request time |

- Filter: `lo <= bucket_ms <= now_ms` (future samples never); oldest
  first; invalid/non-finite/negative prices rejected at read.
- Bound: even downsampling to MAX_CHART_POINTS=1000 preserving endpoints;
  `truncated` + `points_total`/`points_returned`/`point_limit` reported;
  `insufficient:true` when zero points.
- CSV: same points, header `timestamp,price`, `text/csv`, attachment
  `{SYM}-{rng}.csv`.
- Anchor warning (do NOT silently substitute): the old window is anchored
  at REQUEST time. Current production V2 price response is schema_version
  3: the same five historical ranges anchored at LAST_RETAINED_SAMPLE,
  max 10_000 raw input samples with 1_200 display output samples, and
  separate fresh exports (CSV/JSON with metadata and gaps — not a frozen
  earlier chart snapshot, not an exhaustive raw export). REQUEST-time mode
  remains absent and the historical range is explicitly labeled. Budget per
  range before any implementation (frontend-owned).

## 5. Diagnostics contract (status_readonly purity + UNKNOWN rules)

- `control.status_readonly()` is the ONLY observation used by GET paths
  (`DashboardState.probe_status` + `/api/control/probe/status`); pinned by
  `tests/test_dashboard_get_purity.py` (G1–G3: stale RUNNING never
  reconciled, absent registry never created, process/feed reported
  separately, zero writes/handles/process actions; mutation check fails
  G1/G3 when legacy `status()` is restored).
- Scope limit: the purity pins cover `probe_status` ONLY. They do not
  certify every legacy GET's storage behavior — `HistoryStore` read
  helpers call `_ensure()`, which can initialize/migrate storage through
  writable connections (and `event_symbol` opens the historical DB
  read-write). V2 read-only presentation must avoid those methods and use
  an explicit read-only adapter that never creates absent DBs.
- Shape: same nullable keys as mutating `status()`; supervisor/sentinel
  blocks always present (ACTIVE only when verified, else STALE/UNKNOWN
  with raw lease evidence alongside).
- Separation: `probe_status` = process block (recorded registry state)
  + feed block (`feed_health` from snapshot age/health model, null-safe).
  `health()`: unknown (no snapshot) / stale (>120s) / degraded (stale
  streams, reconnects, reject rate) / ok.
- Rules: recency alone never proves identity, live process, run binding,
  or protection; unverified identity/liveness reads UNKNOWN (never
  healthy-by-default); stored RUNNING for a dead/reused PID stays RUNNING
  in pure reads (reconciliation lives in `status()`/stop paths only).
- A future expressly authorized observation run must produce, at minimum:
  fresh periodic snapshots (cadence ≤120s), live registry leases with
  fresh heartbeats for probe+supervisor+sentinel runs, discovery scans,
  price-sample span covering queried ranges, OI poll recency, research
  recorder writes without drops/errors, and clock sync recency — each
  feeding the UNKNOWN→verified transitions above. No standing
  authorization exists.

## 6. Old-server dependencies vs canonical modules

- Reads: `persistence.PersistenceStore` (canonical `data/microprobe.db`;
  `DashboardState` only calls `latest_*`; constructor `init_db()` creates
  schema on a fresh file), `history_store.HistoryStore` (separate
  historical DB; `coverage_summary`/`research_counts`/`event_summary`;
  `event_symbol` opens `sqlite3.connect` read-write on the historical DB),
  `control.status_readonly` (registry, pure), `events.EVENT_FAMILIES`.
- Mutations: `control.start_probe`/`stop_probe` (POST-only localhost +
  nonce/Origin), `control.mark_*` (probe-owned only).
- Identity/subprocess: `tasklist`/`wmic`/ctypes (PID checks), pidfile
  `logs/dashboard.pid`, ordered ports
  8091..8095/18091/18765 on 127.0.0.1, per-process control nonce.
- CLI (`dashboard`): start (detached, first free port) / stop (tracked PID
  only) / restart / status (PID + health + route check) / serve / pick-port.
- Views: `dashboard_views` render_* (overview/movers/search/symbol/system/
  opportunities) + `dashboard_components` theme + `dashboard_data` models.
  No formulas duplicated for V2: all metrics come from persisted rows.

## 7. Reversible old-UI retirement plan (PROPOSED — NOT executed)

Dependency update 2026-10-11: the DASH-V2-64 audit originally found lazy
control imports from dashboard.py. Extraction c59c5ec moved repo_root,
process_info, pid_is_ours, no_window_flags and _creation_time_ctypes to
host_process.py (stdlib only). control imports that module; dashboard
re-exports the same function objects. Source bodies were verified identical.
This closes the shared-helper extraction prerequisite; it does NOT authorize
HTML/file retirement or certify exhaustive V2 parity. The modern isolation
proof and exact-SHA review are recorded in DASH_V2_69_EXTRACTION_PROOF_REVIEW.md.

Preconditions for a future separately scoped retirement:
P1 Before any stop, verify the tracked server PID/image/ctime if present;
if absent, confirm absence without terminating unrelated processes.
P2 V2 parity/cutover gates must pass on the exact reviewed SHA.
P3 Canonical DB, registry and evidence need byte-verified recoverable backups.
None of these retirement steps was executed by the extraction/review task.

Steps (reversible, only after that retirement task is authorized):
1. Stop serving through the existing tracked-PID dashboard stop path if
   a verified owned server is running. Keep code installed. Confirm the old
   server is absent afterward; restart through dashboard start for rollback.
2. File-level gating remains PENDING: although control no longer imports the
   HTTP module, require the completed parity gate and reviewed compatibility
   before gating any handler/server/CLI. Do not delete or rename modules.
3. Preserve registry, SQLite, logs and evidence. Canonical host-process
   utilities remain independent of HTTP; legacy callers keep re-exports.
4. Recheck V2 readonly SQLite and pure bridge, canonical tests and old-server
   absence. Do not equate a free candidate port with proof all servers stopped.

Rollback triggers: a V2 read regression, missing audit field or operator
request. Restore serving through the retained old dashboard and verify routes.
No old listener/file was retired here; Start and operational gates are unchanged.
