# P3 — Run linkage report (2026-10-12, schema v10)

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

## Deferred (explicit)

Research-bucket run linkage (historical schema + recorder row paths)
needs its own migration + recorder context threading; deferred to avoid
an oversized atomic change. Recording counts still work without it.
