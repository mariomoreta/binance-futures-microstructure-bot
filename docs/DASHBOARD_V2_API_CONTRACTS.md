# Dashboard V2 API Contracts


## DASH-V2-63 — 2026-10-11 — implemented persisted facade
Current core data reads use canonical read-only SQLite server projection. Main market snapshot schema 1; opportunities normalized schema "1"; prospective schema 9; price series schema 2 with LAST_RETAINED_SAMPLE anchor. Read time is not observation time. Source tags and independent source dates are explicit; no current liveness proof from persistence. See DASHBOARD_V2_63_DATA_CONTRACT.md for exact bounds/nullability/refresh and compatibility. Old route inventories below are historical; no backend HTTP contract was changed.



## DASH-V2-62 - 2026-10-11 - backend corrections completed directly

User authorized this reviewer to correct backend R1-R5/C1-C2 directly. Published c635938fc5542be992e06838a8727652225e1657 on phase1/market-intelligence-dashboard: bounded disabled correction DONE/ACCEPTED, 902/902 canonical and 52 focused OK; exact published source checksum verified. Original backend checkout/evidence preserved and needs git pull --ff-only. V2-61 handoff is superseded; no repeat correction request. See [bounded acceptance](DASHBOARD_V2_62_BACKEND_CORRECTIONS_ACCEPTANCE.md). Internal disabled preparation is not an enabled capability: Start/pure GETs/production V2-60 and SUCCESS_GATES remain unchanged. Actual watcher startup binding/spawn/rollback and longevity remain unverified; no operational PASS or new runs. Visual N/A for this checkpoint.


## DASH-V2-61 - 2026-10-11 - disabled launch review

Exact backend da231b911e9b1a0cfe86b3aaa3325e5b71928687 reviewed read-only from Git archive: CHANGES REQUIRED, not accepted for integration. Public disabled guard verified; nine deterministic cases reproduce five new issues (foreign run ownership/rollback, ignored watcher recheck, wrong default supervisor command, finite-budget violation, unreadable-final uncertainty). Future tolerance and claimed pure preflight timing also require reconciliation. Backend canonical 873/873 OK (170.494s); V2 snapshot 496/496 OK (83.491s), both exit 0. Passing existing suites do not negate new reproductions. See [review/evidence](DASHBOARD_V2_61_SUPERVISED_LAUNCH_REVIEW.md) and [complete backend correction prompt](DASHBOARD_V2_61_BACKEND_HANDOFF.md). Start stays disabled; pure status GETs and production V2-60 remain unchanged at http://127.0.0.1:3020. Next: backend owner fixes bounded R1-R5/C1-C2, then exact-SHA review. V2-55 accepted R1/R2 remain closed; no probes, gates, main merge or backend worktree edits. Visual verification N/A for this nonvisual checkpoint.

> Current reconciliation: DASH-V2-53 (2026-10-11). Original inventories/statuses below are dated historical checkpoints; consult the dated reconciliation section and MOVER_LEVEL_STRATEGY_RESEARCH.md before interpreting implementation status. Backend 55efaa2 and the V2 snapshot are separate source trees.

**Purpose:** inventory current Python routes and define the compatibility
boundary required by the future Next.js BFF.  
**Status at original inventory:** CURRENT ROUTES VERIFIED FROM CODE; V1 FACADE PROPOSED, NOT BUILT (historical; current facade above).
**Evidence:** `src/microstructure_probe/dashboard.py`,
`dashboard_data.py`, persistence readers and tests at commit `6270be29`.

## Current transport rules

Python binds loopback and returns JSON without an explicit API version.
Read endpoints generally return `404 {"error": string}` when no persisted
data exists; invalid inputs return 400; unknown route returns 404. Nested
feature records are persistence pass-through JSON and are not runtime-schema
versioned. This is usable by current SSR, but insufficiently stable for an
independent frontend.

## Current route inventory

| Method/path | Current success shape | Freshness/provenance | V2 use |
|---|---|---|---|
| GET `/api/health` | status/version/uptime, server, feed, host, persistence, snapshot times, stream summary, bot mode, safety, reasons | latest snapshot + server clock | System/Overview |
| GET `/api/snapshot` | raw telemetry snapshot object | `snapshotTimestamp`; mixed nested provenance | diagnostics only |
| GET `/api/search?q=` | `{query, results: MoverRow[]}` | composed at request time | symbol search |
| GET `/api/symbol/{symbol}/price?range=` | `{symbol,source,range,generated_at,points[{timestamp,price}],points_total,points_returned,truncated,point_limit}` | Binance markPrice buckets | chart |
| GET `.csv` twin | `timestamp,price` | same | export |
| GET `/api/features/returns` | `{generated_at,source,semantics,features[]}` | markPrice; nested as-of/sample age | Symbol/Movers |
| GET `/api/features/momentum` | generated/source/semantics/ranks/features[] | markPrice | Symbol/Movers |
| GET `/api/features/flow` | generated/source/aggressor/quantity/delta semantics, horizons, baselines, symbols[] | aggTrade | Symbol/Movers |
| GET `/api/features/volume` | generated/source/semantics/symbols[] | aggTrade buckets | Symbol/Movers |
| GET `/api/features/book` | generated/source/semantics/integrity_note/symbols[] | depth20@100ms | Symbol |
| GET `/api/features/open-interest` | generated/source/semantics/context_note/symbols[] | `/fapi/v1/openInterest` | Symbol |
| GET `/api/features/vwap` | generated/source/semantics/horizons/symbols[] | flow + mark reference | Symbol |
| GET `/api/features/volatility` | generated/source/semantics/horizons/symbols[] | mark buckets | Symbol |
| GET `/api/features/structure` | generated/source/semantics/symbols[] | mark buckets | Symbol |
| GET `/api/discovery` | architecture/subscription note, discovery object, events[] | latest Binance REST scan | Overview/Movers |
| GET `/api/history/status` | generated/source/series[] | historical DB coverage | System |
| GET `/api/history/{symbol}` | `{symbol,series[]}` | historical DB coverage | Symbol |
| GET `/api/research/status` | generated/source/note/research | recorder snapshot + DB counts | System |
| GET `/api/events/studies` | generated/note/studies[] | historical DB | research |
| GET `/api/events/studies/{definition}` | definition/version/horizons/note | historical DB | research |
| GET `/api/events/symbol/{symbol}` | symbol/events/note | historical DB | Symbol |
| GET `/api/control/probe/status` | process registry fields plus `feed_health`, `latest_snapshot_age` | live registry + snapshot | Engine control |
| POST `/api/control/probe/start` | started/pid/mode/duration/preset/evidence; 409 if running | mutation; nonce+local Origin/Host | System only through BFF |
| POST `/api/control/probe/stop` | stopped/pid | mutation; same boundary | System only through BFF |

Current HTML routes are `/overview`, `/movers`, `/search`, `/symbol/{symbol}`
and `/system`; they are not frontend data contracts.

## Verified current row contracts

`MoverRow` is currently composed as:

```ts
type MoverRow = {
  symbol: string;
  tier: "CORE" | "HOT" | "DISCOVERY";
  capability: "LIVE" | "WARMING" | "DISCOVERY ONLY" | "STALE" |
              "DEGRADED" | "UNKNOWN";
  subscribed: boolean;
  price: number | null;
  change_24h_pct: number | null;
  quote_volume_24h: number | null;
  ret_1m: number | null;
  ret_5m: number | null;
  velocity_1m: number | null;
  accel_1m: number | null;
  flow_delta: number | null;
  flow_ratio: number | null;
  vol_z_1m: number | null;
  sample_age_ms: number | null;
};
```

Price points use integer Unix milliseconds and numeric mark price. Search is
bounded to 25 persisted-universe results. Valid chart ranges are
`5m|15m|1h|4h|24h`, max 1000 points, oldest first, future rows excluded.

## Required versioned facade

Add future Python `/api/v1/` view-model endpoints; the Next.js BFF mirrors
them under its own same origin. Each response uses:

```ts
type Envelope<T> = {
  schema_version: "1";
  generated_at: string;          // ISO-8601 UTC
  as_of: string | null;          // newest source observation
  source: SourceRef[];
  freshness: "FRESH" | "STALE" | "EXPIRED" | "UNKNOWN";
  quality_flags: string[];
  data: T;
};
type ApiError = {
  schema_version: "1";
  error: { code: string; message: string; details?: unknown };
  request_id: string;
};
```

Null means not measured/not available. Numeric zero remains zero. Stale values
may be present only with `STALE`; expired/untrusted values should be null or
omitted according to the field contract. Frontend must not infer values.

## Required view models

### `GET /api/v1/overview`

Engine/feed/research health; safety; discovery/live counts; bounded notable
movers; optional externally sourced context. Every block has its own as-of and
source. This avoids sequential fan-out across all feature endpoints.

### `GET /api/v1/movers`

Query: `cursor`, `limit<=200`, `sort`, `direction`, `tier`, `capability`,
`search`. Returns `items: MoverRowV1[]`, `next_cursor`, filters and a
`metric_definitions` map. Raw numbers only; display strings are frontend work.

### `GET /api/v1/symbols/{symbol}`

One contract identity and per-panel blocks for market/discovery/live features,
historical coverage/events, mapping/profile and completeness. A Binance-known
historical-only contract returns 200. This fixes the current gap where route
knownness is derived from live/discovery sets and can exclude `ORCAUSDT` even
though historical coverage exists.

### `GET /api/v1/research/studies`

Definition/version pagination, sample tier, provenance and honest resolution
limitations. Existing per-definition and per-symbol routes can back it.

### `GET /api/v1/runtime`

Consolidates process/feed/research states without conflation. Read-only.

### `POST /api/v1/runtime/start|stop`

Fixed typed commands. Same 400/403/409 semantics, plus request/audit ID. Only
the trusted BFF may call; browser never sees Python nonce.

### `GET /api/v1/assets/{symbol}/profile`

Verified identity plus nullable metadata/context values, each with provider
provenance/freshness. Unverified mapping returns known Binance identity and
`mapping_status: UNKNOWN|AMBIGUOUS`, not a guessed profile.

### `GET /api/v1/opportunities`

Future only. Cursor pagination and lifecycle filters. Candidate fields include
selection reasons, capability, evidence blocks, BTC/historical context,
completeness, counterevidence and risks. Direction/zone/invalidation/targets/
horizon/cost/sizing/paper results remain nullable and versioned. Endpoint must
return an honest empty/blocked state until P1-12/P1-13A exist.

## Security, caching and errors

Read endpoints: same-origin BFF allowlist, bounded timeout/body, no open proxy;
cache only within source TTL and never conceal stale transitions. Mutation:
POST only, same-origin CSRF, server-held nonce, fixed payload and no caching.
No wildcard CORS. Do not expose SQLite, file paths, raw nonce, provider keys or
arbitrary process arguments.

## Acceptance criteria

Runtime schemas and Python contract tests; null/zero/stale fixtures; Unicode
symbol and historical-only routing fixtures; pagination/filter determinism;
security tests; backwards-compatible current SSR until cutover.


## 2026-10-11 - DASH-V2-50 read-only watcher integration
Current frontend BFF adapts canonical control.status() at backend 8648366.
This slice adds sentinel and preserves supervisor/sentinel raw lease evidence.
It does not implement or authorize transactional runtime launch.

| Field | Representation / rule |
|---|---|
| observed_at | BFF response observation time, ISO UTC; not a feed sample timestamp |
| supervisor / sentinel | separate normalized watcher blocks |
| state | controller label preserved as observed |
| lease_state | raw lease lifecycle; nullable |
| lease_last_check_at / last_check_at | raw UTC heartbeat strings; nullable |
| watcher_pid / watcher_create_time | watcher identity evidence; nullable |
| watched_pid / run_id | associated run evidence; nullable |
| abort_triggered | explicit true/false or null; never inferred from missing data |
| abort_rule / abort_reason / abort_threshold / abort_observed | supervisor evidence; numbers/text/null; numeric zero retained |
| action_taken / action_reason | sentinel action evidence; nullable |

ACTIVE display requires the canonical ACTIVE label plus raw ACTIVE lease, a
valid UTC lease heartbeat in [0,90s], associated watched PID, watcher identity
evidence and observation in [0,90s]. Future, malformed or expired timestamps
never count as fresh. The client updates expiry every second, independently
of the 10-second poll; failed fetches replace previous evidence with UNKNOWN.
Canonical watcher liveness is a controller observation; the browser does not
independently verify the OS process. ACTIVE is never a protection guarantee.
Raw controller labels remain inspectable when the displayed state ages to STALE.

Missing blocks render UNKNOWN; established but invalid evidence renders STALE.
Process lifecycle, feed health, supervisor and sentinel remain distinct.
Start stays blocked; launch readiness and success gates are unchanged.
Residual source contract: abort_at / aborted_by persist in registry but are not
published by control.status() watcher blocks at this SHA; V2 does not invent them.


## 2026-10-11 - DASH-V2-51 pure observation requirement
The runtime BFF and command preflight require canonical control.status_readonly().
Its shape must match existing process + supervisor + sentinel status fields.
It must not write/reconcile registry, close/mutate log handles or take process
actions. Legacy control.status() is not called as fallback.
Current backend 0786617 lacks this capability: runtime returns explicit
READ_ONLY_STATUS_REQUIRED with UNKNOWN process/feed/watchers and null evidence.
This intentionally supersedes the direct control.status() bridge in DASH-V2-50.
It does not imply that historical SQLite evidence is missing or that the
underlying engine is stopped. Client commands are disabled on the source error.
Start remains blocked in its route and helper; mutation/security gates unchanged.
The pure method must be independently audited before accepting a backend handoff.


## 2026-10-11 - DASH-V2-52 pure-status interpretation
Backend 55efaa2 provides status_readonly(); exact V2 bridge verified byte-preserving.
state/running are canonical registry projection fields. Stored RUNNING is preserved
for a dead/reused PID. They do not certify current target liveness. uptime_seconds
is elapsed wall time since recorded start, including terminal records; UI labels
it Elapsed since start. Watcher verification/expiry and feed UNKNOWN remain separate.
No live duration, protection, or supervised-launch capability is inferred.


## Proposed research projection boundary — DASH-V2-53, 2026-10-11

The original inventory/facade status above is historical at 6270be29; subsequent V2 integration is recorded in the progress and integration reports. Backend contract statements in this checkpoint refer to 55efaa2, not to the older Python snapshot inside V2. This documentation adds no route, API version or wire field and changes no prospective v1.1 contract.

F-V2-RESEARCH-01 proposes a future read-only projection with stable episode/strategy identity; canonical observed direction separate from nullable proposed trade side; level formation/availability and price basis; feature/source/as-of/quality evidence; endpoint actual observation time; declared path coverage; and nullable activation/entry/invalidation/cost-plan fields. Names are conceptual pending a separate contract decision. Missing paths never become zero MFE/MAE; mark returns never become fills; research lifecycle never becomes position state. Existing registry-readiness projection and disabled Start remain unchanged. See [MOVER_LEVEL_STRATEGY_RESEARCH.md](MOVER_LEVEL_STRATEGY_RESEARCH.md).


## DASH-V2-54 compatibility review - 2026-10-11
Backend b801ab0 preserves status_readonly and nullable GET projection. Exact current pureStatusCode against its archived source passed RUNNING/STOPPING/ABORTED/COMPLETED/absent temporary registry cases without writes. No new DTO/route or target-liveness guarantee. Native/start follow-ups in DASHBOARD_V2_54_BACKEND_CORRECTIONS_REVIEW.md do not require frontend changes. Start remains disabled.


## DASH-V2-55 compatibility acceptance - 2026-10-11
Current pureStatusCode against backend e317569 passed five temporary recorded/absent registry cases without mutation. No frontend status DTO/route change required. Launch evidence_associated distinguishes confirmed parent-log association from absent/different evidence; started=True alone never certifies supervisor protection. V2 Start stays disabled. See DASHBOARD_V2_55_CORRECTIONS_ACCEPTANCE.md.

## DASH-V2-65 - 2026-10-11
GET /search?q=<ASCII fragment> is server-rendered read-only search over ten canonical symbol tables plus retained discovery. Up to 50 output symbols, cap notice, input/source errors explicit. No new API search response contract. Token additional fields reuse saved feature families; range_pct and concentration are fractions converted once, OI rate_per_s stays base units/s, VWAP displacement_pct already percent.

## DASH-V2-66 - 2026-10-11
GET /api/v1/price-series/{symbol}?range=5m|15m|1h|4h|24h&format=json|csv (defaults 1h/no attachment) now returns model schema 3. See V2-66 report for nullable bounds/read limits/gaps/coverage/empty CSV. Invalid input 400; source failure 503. v1/v2 pure normalizers are compatibility helpers, not current production response.

## DASH-V2-68 - separate historical coverage endpoint
GET /api/v1/historical-coverage?symbol=&definition=; response schema1, historical-store schema2. Fixed historical.db readOnly transaction; separate from prospective /historical-research. Exact ASCII symbol and six v1 definition allowlist, repeated/invalid filters400; absent/incompatible source503, absent symbol200 with genuine empties; all no-store. Fields:source/read_at/filter/coverage/gaps/studies/events/counts/limits/truncated/semantics. Times epochms except read_at ISO; mean_forward_return is raw simple fraction AVG over all non-null rows, n_usable separate; display ×100%. Limits500/100/100/50 with overflow flags; aggregate counts scan original selected population. Symbol affects all panels; definition studies/events only. No writable initialization or old HTTP fallback. Polling response read time never proves observation freshness. Full contract/verification in DASHBOARD_V2_68_HISTORICAL_COVERAGE.md.
