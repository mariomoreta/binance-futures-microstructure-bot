# Dashboard V2 API Contracts

**Purpose:** inventory current Python routes and define the compatibility
boundary required by the future Next.js BFF.  
**Status:** CURRENT ROUTES VERIFIED FROM CODE; V1 FACADE PROPOSED, NOT BUILT.  
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
| GET `/api/opportunities` | schema_version/rules_version/candidates[]/lifecycle_events[] | opportunity store v8 | P1-13A research surface |

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

Consolidates process/feed/research states without conflation. Read-only
(`control.status_readonly`, never `status()` on GET). Shape (additive,
2026-10-16 run-visibility): `state` (recorded registry state),
`process_state` (owned/gone/replaced/unknown, verified OS liveness),
`process_verified` (is_canonical_pid), `launcher` (dashboard/agent/
direct/foreign), `run_id` (evidence-log stem), `pid`, `started_at`,
`duration_seconds`, `elapsed_seconds` (frozen on terminal),
`remaining_seconds` (RUNNING only), `expected_end_at`,
`last_exit_code/reason/at` (terminal close motive + close time),
`feed_health` + `latest_snapshot_age` + `feed_attribution`
(current/previous-run/none) + `feed_note` (BFF-enriched from recorded
telemetry, attributed to THIS run window; never invents liveness),
`supervisor`/`sentinel` raw blocks + `observed_at` (browser ages them
against the 90s freshness bound; raw evidence retained after expiry).
Recorded state and verified liveness are never conflated.

Identity display (2026-10-16 hardening): owned requires verified
(OWNED-LIVE); gone is NOT-LIVE (gone); replaced is REPLACED (run
replaced); unknown is UNVERIFIED (unknown) — never NOT-LIVE. Only the
explicit terminal states STOPPED/COMPLETED/FAILED/ABORTED render as a
confirmed close; UNKNOWN never does. Browser verification expires
after 30s without a fresh read (poll 10s): expired reads render
UNVERIFIED (expired), never a retained OWNED-LIVE.

Feed HEALTHY rule (2026-10-16 hardening, strict): HEALTHY only for
fresh (age <=120s), attributable (timestamp inside
[started_at-60s, windowEnd+120s]) snapshots with parseable quality,
non-zero messages, complete coverage/error fields, no stale or missing
streams, no reconnect/websocket errors, reject rate within the
supervisor gate, no parse/payload errors, and silence limited to the
event-driven `!forceOrder@arr`. Invalid JSON, insufficient data, zero
messages, missing fields, stale data, or another run's evidence render
UNKNOWN (previous-run evidence labeled as such), never HEALTHY.
Reject-gate reconciliation (thresholds untouched): the enforced
supervisor abort gate is 0.05 cumulative reject rate
(control.REJECT_ABORT_RATE — a run above it is aborted as invalid
observation); the 0.5 dashboard concept
(dashboard.DEGRADED_REJECTION_RATE) is only a looser legacy transport
display, never a health claim. The BFF reports DEGRADED — never
HEALTHY — for any data breaching the 0.05 supervisor quality
condition, without modifying either threshold.

### `POST /api/v1/runtime/start|stop`

Fixed typed commands. Same 400/403/409 semantics, plus request/audit ID. Only
the trusted BFF may call; browser never sees Python nonce. Start: readiness-
green + `START_OBSERVE_2100` + preset allowlist (brief/standard/
validation-6h) + transactional supervised launch + 202-uncertain reconcile
+ no-double-spawn pre-check. Stop: `STOP_DASHBOARD_SESSION` + confirmation;
allowed for any verified project run (launcher dashboard/agent/direct);
foreign launchers refuse `not_project_owned` before any kill. Backend
`stop_probe`/`enforce_abort` revalidate PID+image+ctime under the registry
lock and terminate only the verified canonical PID (kill-only rollback;
foreign/terminal never touched). The global `RunStatusBar` (AppShell, all
screens) renders this contract; `/system` BotControl keeps the detailed
controls + evidence.

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
