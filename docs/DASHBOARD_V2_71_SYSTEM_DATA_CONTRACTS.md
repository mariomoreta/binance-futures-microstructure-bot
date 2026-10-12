# System V2 data contracts — persisted sources for integration (DASH-V2-71B)

Date: 2026-10-11. Backend base `9f3e084` (reconciled, clean). Read-only
audit: no source, route, formula, or data change except the purity pins in
`tests/test_read_purity.py`. No second collector, no second database, no
V2/main/SQLite/log/evidence mutation, no probe or market traffic.

Method: every reader below was traced to its table/columns (live
`data/microprobe.db`, schema v9, verified read-only) or file; timestamps,
nullability, limits, and side effects were read from code, not assumed.
`generated_at`/`read_at` on responses is RESPONSE time and never proves
data freshness. Recency never proves process identity, run association,
liveness, protection, or feed health. Examples are observation-time shapes
from the 2026-10-10 canonical data, not fresh acquisition.

## 1. Availability matrix (per System V2 panel need)

Notation — reader → table/columns; unit; observation ts vs read ts;
nullability/absence; scope+limits; historical vs current; side effects.

### 1.1 Persistence snapshot + feed health

- `DashboardState.snapshot()` → `telemetry_snapshots` latest row
  (`timestamp` REAL seconds, `runtime_seconds`, `bot_mode`,
  `api_keys_used`, `real_orders_sent`, `real_capital_at_risk`,
  kill-switch/authenticated/order-path flags, `clock_sync_json`,
  `latency_json`, `processing_json`, `detectors_json`,
  `data_quality_json`, `events_by_type_json`, `spread_bps_json`,
  `book_imbalance_json`). Observation ts: row `timestamp`
  (exposed as `snapshotTimestamp`); read ts: now. Absent → None →
  health UNKNOWN. Scope: latest 1 of ≤1000 retained rows. Historical
  evidence (a recorded observation window), never current health.
  Side effects: none on existing DBs (SELECT only).
- `health()` → derived `ok / degraded / stale / unknown` + reasons from
  the snapshot above (`stale` after 120s, `degraded` on stale streams /
  reconnects / reject rate). Pure computation. Example observed:
  `timestamp 1791641080.13, runtime 152.28s, bot_mode observe`.
- `rejection_stats()` → `rejected_observations` aggregates
  (total/rate/by-reason/by-stream). Pure SELECT.

### 1.2 Universe CORE/HOT + subscription budget

- `latest_discovery()` → `discovery_snapshots.payload_json` (single
  REPLACE row: `core[]`, `hot_dynamic[]`, `hot_full[]`,
  `hot_subscribed[]`, `tops{gainers,losers,most_active}`,
  `eligible_count`, `seen_count`, `min_quote_volume_usdt`,
  `generated_at_ms`, `universe_states`). Observation ts:
  `generated_at_ms`; read ts: now. Absent → None. Scope: one row
  (latest scan only; full listing intentionally NOT persisted).
  Historical scan evidence. No side effects.
  Example observed: core BTC/ETH/SOLUSDT, hot_dynamic [], tops×3.
- Subscription budget: NO persisted budget table exists. The only
  machine-readable rule is the `/api/discovery` contract text (CORE
  subscribed, HOT proposed-only) plus `hot_subscribed[]` inside the
  snapshot above. `subscribed` on movers rows means retained deep
  evidence, never verified present subscriptions → NOT_AVAILABLE as a
  live budget; see §3.
- `universe_events(limit)` → `universe_events` rows
  (`timestamp` s, `kind`, `symbol`, `detail`), newest capped at 500
  retained, read limit 50 (API surfaces 20). Individual timestamped
  lifecycle rows (e.g. hot_subscribed/unsubscribed), NOT aggregates.
  Absent → []. No side effects on existing DBs.
- `latest_ranks()` → `rank_snapshots` REPLACE-per-metric. Pure read.

### 1.3 Research recorder

- `research_status()` → `research_counts()` on historical DB
  (`research_flow_10s/1m`, `research_book_1m` row counts) + live
  recorder block from the latest snapshot (`writes/drops/errors/
  inflight/high_water/last_write_at`, defaulting 0/UNKNOWN). Counts are
  exact integers; live block is snapshot-carried evidence (stale when the
  snapshot is old). Absent DB → zeroed counts (V2 must use its own
  readOnly adapter: `HistoryStore` construction goes through `_ensure`,
  see §4).
- Research buckets (`research_flow_10s/1m`, `research_book_1m`):
  idempotent per (symbol, bucket) keys, 7d/90d/90d retention. Pure SELECT
  only via counts; no row-level read API on the old dashboard.

### 1.4 Classifier + opportunities

- `latest_state_features()` → `state_features` REPLACE-per-symbol
  (`symbol`, `updated_ms` ms, `feature_json` with state/evidence/version/
  previous). Observation ts: `updated_ms`; read ts: now. Absent → [].
  Example symbols observed: GRIFFAIN/AIOT/MET/OGN/RLC + USDT.
- `latest_opportunity_candidates()` → `opportunity_candidates`
  REPLACE-per-key (`candidate_key`, `symbol`, `updated_ms`,
  `candidate_json`); `opportunity_events(limit)` newest-first, bounded retained events (API surfaces 20; retention must be traced
  in the corresponding writer, not inferred from this reader). Individual lifecycle rows with
  timestamps. Absent → [].
- `prospective_setups()` / `prospective_outcomes(limit=50)` →
  `prospective_setups` (REPLACE per key: candidate_key/symbol/family/
  direction/market_state/rules_version/capability_tier/detected_at_ms/
  score/setup_json/lifecycle) + `prospective_outcomes` (append-only outcomes: horizon/observed_at_ms/mark_return_pct/detected_price/
  current_price/outcome_state/reason). Dashboard surfaces latest 10.
  Example observed: 1m×63, 5m×59, 15m×44, 1h×35, 4h×27, all COMPLETE.
  Times in ms (event-time); states never fabricated.

### 1.5 Runtime / supervisor / sentinel / feed (diagnostics)

- `control.status_readonly()` — the ONLY reader V2 may use: same nullable
  shape as mutating `status()`; never writes, reconciles, closes handles,
  or acts on processes (pinned by `test_status_readonly.py` +
  `test_dashboard_get_purity.py`). Process/supervisor/sentinel/feed blocks
  always present; ACTIVE labels require verified lease + fresh heartbeat +
  identity + run binding, else STALE/UNKNOWN with raw evidence alongside.
- Feed health is computed from snapshot age + health model, never from
  process state; process state never implies feed health.
- V2-70 already presents missing-stream, parse/payload-error, and signed
  clock-offset fields as RECORDED (RECENT_RECORDED_SAMPLE /
  HISTORICAL_ONLY / FUTURE_RECORDED_SAMPLE); future ages stay negative and
  unverified. No new liveness is claimed here.

### 1.6 Absent fields (NOT_AVAILABLE — do not render, do not infer)

- Host resources (CPU/RSS/bytes): NO column in `telemetry_snapshots`
  (verified on schema v9 and the live canonical DB). The P1-14B.6 `host`
  block exists ONLY in console log lines (`probe.py`), not in any
  queryable store. Future work: persist a bounded host sample (own table
  or snapshot column) from an authorized run; until then System shows
  NOT_AVAILABLE, never log-scraped numbers.
- Operational audit log: NO journal table exists. Only the registry's
  latest `last_exit` plus capped lifecycle tables (`universe_events`
  ≤500, `opportunity_events` ≤500/setup, `state_transitions` ≤500) hold
  individual timestamped rows; aggregate counters are not an audit log
  (no per-event severity/actor stream). Future work: append-only ops
  journal with timestamps + severity, or explicit NOT_CONNECTED.
- Live subscription proof, live feed certification, OS liveness:
  absent by design (pure status certifies nothing live).
- Current-window price anchor: explicitly absent; historical
  LAST_RETAINED_SAMPLE only (V2-66 scope).

## 2. Differences vs V1 presentation

- Prices: old API anchors ranges at REQUEST time (MAX 1000 points);
  current V2 anchors at LAST_RETAINED_SAMPLE (schema 3, 10k raw / 1200
  display, gap-segmented exports). Never substitute silently.
- Search: old max 25 + broader (unicode) parser; current V2 max 50 +
  ASCII validation. Differing source unions are not parity.
- Prospective route: old reads the `microprobe.db` archive (schema 9);
  historical coverage/studies read the SEPARATE
  `data/historical/historical.db` (schema 2). Names alone establish no
  bar/study parity.
- System: old rendered live-process assumptions in places; current V2
  projects RECORDED/STALE/UNKNOWN only, with disabled controls.

## 3. Safe readers for V2 (allowlist with purity notes)

Bounded final-byte equality on the populated temporary fixture checked by `tests/test_read_purity.py`
(both DB/registry/evidence bytes compared, content queries agree, no new
DB or log files; WAL sidecars remain tolerated). This is not proof of
readonly connection mode, absent-store behavior or intermediate writes.
Independent review observed four HistoryStore.init_db calls despite
equal final bytes. Do not promote these helpers to the V2 readonly
boundary from this test alone. Source-audited existing-store projections:
`latest_telemetry`, `latest_return_features`, `latest_discovery`,
`universe_events`, `latest_ranks`, all `latest_*_features`,
`latest_state_features`, `latest_opportunity_candidates`,
`opportunity_events`, `prospective_setups/outcomes`,
`search_symbols` /
`movers_table` / `compose_universe` (pure composition),
`status_readonly`, `compute_health`, `get_rejection_stats`.

NOT safe for V2 presentation (writable paths, V2 must keep its own
readOnly adapter that never creates absent DBs): `PersistenceStore`
construction (`mkdir -p`, read-write open creating the file, `init_db`
schema creation, `load_price_samples` auto-`init_db`), ANY `HistoryStore`
use (`_ensure` → `init_db` schema/migration, `_connect` mkdir + WAL-mode
set, `event_symbol` read-write open), `control.status()` (locked
reconciliation writes). Absent DB must read as unavailable, never be
created.

## 4. Examples derived from existing records

Observation-time shapes (canonical 2026-10-10 data; see §1 for live
values): discovery blob keys
`{core, eligible_count, filtered_count, generated_at_ms, hot_dynamic,
hot_full, hot_subscribed, min_quote_volume_usdt, seen_count, top_n,
tops{gainers,losers,most_active}, universe_states}`; coverage rows
`(symbol, interval, source, expected_bars, actual_bars, coverage_ratio)`
e.g. `ETHUSDT 1h klines 719/719 1.0`; outcome cells across
1m/5m/15m/1h/4h all COMPLETE. A stored BTC 1h coverage row with zero
bars and null span/ratio is preserved as-is (per V2-67), never upgraded.

## 5. Decisions the frontend must respect

- UNKNOWN on any unverified identity/liveness/binding/freshness; no
  healthy-by-default.
- `generated_at`/`read_at` are response times, not observation times.
- No Popen / ACTIVE-lease / recent-heartbeat confirmation of supervision;
  point-in-time only (see launch contract).
- No silent anchor substitution (REQUEST vs LAST_RETAINED_SAMPLE), no
  ASCII/Unicode silent narrowing, no statistical-population changes
  (AVG over non-nulls vs n_usable stay distinct).
- SHA verification is manual; no automatic bridge pin is claimed.
- Start stays disabled; no new runs, gates, or phases from this audit.

## 6. Concrete blockers for old-dashboard retirement

1. V2 parity gaps per the V2-64 cutover audit (search/token/range/export/
   coverage/diagnostics) — open, frontend-owned.
2. Helper-extraction file retirement: DONE as code separation
   (`host_process.py`); physical old-UI removal still needs the operator's
   explicit cutover approval after parity + parallel observation.
3. Writable-path discipline: V2 must never touch `HistoryStore`/
   `PersistenceStore` constructors or `control.status()`; allowlist in §3
   is the boundary.
4. An authorized observation run is the only source of fresh evidence;
   none is authorized here — all UNKNOWNs above stay UNKNOWN.

## DASH-V2-71 reviewer correction
Reviewer found that before_hist was captured but never asserted, and new
.log files were allowed. A historical tempfile mutation passed the original
test; the strengthened existing test now rejects it. No test-count change.
Environment overrides now restore prior values. No application source edit.

Final-byte equality is not a readonly-API guarantee: HistoryStore readers
invoke _ensure/init_db on existing fixtures. Keep V2 on fixed-path
DatabaseSync readOnly connections. Canonical universe rows detail='test'
are unverified in origin; preserve them and distinguish retained counts
from validated operational events. Do not silently delete or exclude.


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
