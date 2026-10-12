# P3 — Run linkage report (2026-10-12, CORRECTED 2026-10-13)

## Addendum — research-bucket linkage v3 (2026-10-13)

The deferred research-bucket gap is now closed (minimum): history schema
v2→v3 adds nullable run_id/rules_version/as_of_ms/price_source/
dataset_id to research_flow_10s/1m + research_book_1m; the recorder
stamps run_id/rules_version/dataset_id context at flush plus as_of_ms
(persist-availability wall time, distinct from event time and bucket
close) and price_source ("aggTrade" flow, "depth20" book); the probe
threads its run_id + classifier/opportunity versions (dataset_id stays
None = UNKNOWN until a study binds the rows). Receive timestamps do not
exist and are never fabricated. Old rows stay NULL. Migration proven on
temp fixtures and a temp byte-copy of the real canonical historical DB
(counts preserved, zero leaked linkage); canonical never opened for
writing. Event-level linkage still rides run_id + (symbol, window);
study runs keep input_source_versions for dataset identity.

## Gap analysis (execution → observation → persist → rehydrate)

- universe_events: NO run column → ADDED (nullable run_id).
- prospective_setups / prospective_outcomes: NO run column → ADDED.
- telemetry_snapshots: NO run column → ADDED (via summary payload).
- event tables (historical): run_id already present (event_study_runs,
  event_instances) → REUSED, untouched.
- research buckets (flow/book): recorder path has no run context; linkage
  DEFERRED with rationale below (no silent omission).
- Rehydration (`ProspectiveRecorder._load_from_db`) reloads all stamped
  rows regardless of run (cross-restart continuity by design); run_id now
  distinguishes origin without breaking continuity.

## Corrective addendum (R6/R7, 2026-10-13)

- R6: EVERY supported chain (v1–v8, v9, fresh) reaches v10 in ONE
  `init_db` via `_finish_v10` (columns + stamp + initialized). No second
  instance required; repeat init is idempotent; migration errors propagate
  loudly (cursor rollback). Tests pinned to v9 were updated to v10 (not
  conserved green-by-pin). Proven on temp fixtures incl. a temp byte-copy
  of the real v9 canonical DB (counts preserved, old rows NULL, new
  writes stamped; canonical never opened for writing).
- R7: `ResearchRecorder._resolve_history` (injected → db_path → default)
  now covers status(), the writer worker AND retention cleanup. Proven by
  enqueue → worker → drain → forced cleanup with default constructions
  forbidden: injected store receives rows, zero errors. Default behavior
  (no injection) unchanged.
- run_id is full UUID4 hex (32). Guarantee, precisely: UUID4 randomness
  (122 bits); uniqueness is probabilistic (collision negligible), never
  claimed absolute; separation relies on inequality of stored ids, which
  the tests assert per execution. No absolute-unicity claim is made.

## Gap analysis (execution → observation → persist → rehydrate)

- universe_events: NO run column → ADDED (nullable run_id).
- prospective_setups / prospective_outcomes: NO run column → ADDED.
- telemetry_snapshots: NO run column → ADDED (via summary payload).
- event tables (historical): run_id already present (event_study_runs,
  event_instances) → REUSED, untouched.
- research buckets (flow/book): recorder path has no run context; linkage
  DEFERRED with rationale below (no silent omission).
- Rehydration (`ProspectiveRecorder._load_from_db`) reloads all stamped
  rows regardless of run (cross-restart continuity by design); run_id now
  distinguishes origin without breaking continuity.

## Propagation (guaranteed from this change on)

`MarketProbe.run_id` (uuid4 hex16, unique per construction) → stamped on
universe events (all 4 call sites), summary/snapshot payloads, and the
owned prospective recorder (setups/outcomes via worker). Separation: two
executions never share an id (uuid4); registry untouched.

## Historical treatment

Pre-existing rows keep run_id NULL = UNKNOWN provenance. No backfill
exists anywhere (writers only stamp new rows; migration only ADDS the
column). No run-id inference by symbol/date/content — prohibited and
not implemented. The 225 fixture rows and 150 operational-probable rows
keep their Etapa-2 dispositions.

## Migration (prepared, tested on temp copies, NOT applied to canonical)

v9→v10: `_ensure_run_id_columns` (PRAGMA-checked ALTER, established
idiom); fresh init lands v10 directly; v1–v8 chains still land v9 in one
call (existing version pins green) and reach v10 on the next init.
Proven on a temp byte-copy of the real v9 canonical DB
(`test_v9_copy_migrates_preserving_rows_without_backfill`): version 10,
all row counts preserved, old rows NULL, new writes stamped. Canonical
DBs never opened for writing by any test (P2 barrier evidence).

## Deferred (explicit) — research-bucket item CLOSED 2026-10-13

The deferral above is superseded by the v3 addendum at the top (kept for
history): research-bucket linkage is implemented with the minimum fields.
Remaining linkage-adjacent work (not blockers for this scope): study-run
binding of dataset_id on live buckets; venue funding calendars per symbol.
