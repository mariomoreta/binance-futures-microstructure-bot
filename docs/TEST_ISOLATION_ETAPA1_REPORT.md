# ETAPA 1 — Test isolation report (2026-10-12)

Base: `aea0376` (`phase1/market-intelligence-dashboard`, HEAD verified, remote
in sync; frontend `dash-v2-03-token-detail` `27b7af5` consulted from Git only).
No application source changed in this stage. No probes, traffic, orders,
Start, paper, V2/main changes, resets or evidence deletions.

## 1. Barrier (`scripts/audit_test_isolation.py`)

Full-suite audit (same discovery as `run_tests.py`) with four simultaneous
traps: forbidden default-persistence factory (records attempts even when
production swallows them as `persistence_error`), `sqlite3.connect` wrapper
for canonical DB paths, `control._write_registry` wrapper, and
`builtins.open`/`io.open` write-mode wrapper for canonical `data/`+`logs/`
trees. Plus SHA256 of both DBs + registry and full `data/`+`logs/`
inventories before/after. Exit 0 only on: suite green + zero prohibited
hits + equal hashes + clean inventories. Stdlib only.

## 2. PREFIX findings (pre-fix, 911 tests, exit 1)

Evidence: `docs/evidence/TEST_ISOLATION_AUDIT_PREFIX.json`.

- Suite green (911/911) **with 61 prohibited hits** — all
  `default_factory_call` from `test_probe` (5 tests), `test_host_telemetry`
  (2 tests) and `test_p14b_3_transport_freshness` (4 methods, incl. a 50-call
  burst loop). Every one swallowed internally: green never meant pure.
- 97 canonical connects in three residual routes (read-intent,
  byte-neutral — hashes stayed equal):
  - **Route B (64, microprobe.db):** every `MarketProbe()` construction →
    `ProspectiveRecorder._load_from_db` → `PersistenceStore()` default →
    `init_db` DDL no-op on schema v9 + SELECT rehydration. Production-code
    default; no test-side redirect exists (`ProbeConfig` has no `db_path`).
  - **Route C (33, historical.db):** dashboard/probe readers
    (`research_counts`, `coverage_summary`, `event_summary`) via
    `HistoryStore()` default + `_ensure` DDL no-op. Read-intent production
    paths; redirecting tests via env would change what those tests observe.
  - **Route D (1):** `control.py` read-only URI (`mode=ro`) supervision
    read. Explicitly read-only, not a violation.
- `logs/probe-runs/` gained 0-byte sidecars from three further test-side
  routes (**Route E**): `start_probe` without `evidence_dir`
  (`test_probe_control`, `test_process_identity`) and
  `_default_watcher_spawner` with only `dashboard.repo_root` patched
  (`test_supervised_launch_corrections` — control holds its own `repo_root`
  reference). Registry attempts: 0. `data/` inventory: clean.
- The prior 729-test audit is superseded: its path setup dropped the five
  `src.*`-importing modules (127 tests) and its six "errors" were that same
  path bug, not fixture failures. This audit covers all 911.

## 3. Reproduction on temp resources (no canonical touch)

`scripts/repro_default_store_writes.py` runs the 10 Route-A bodies with the
factory intercepted to a temp store.
Evidence: `docs/evidence/REPRO_DEFAULT_STORE_WRITES.json`.
Result: 10/10 pass, 10 factory calls captured **4 observation + 54
rejection rows on temp**, canonical hashes identical before/after (exit 0).

## 4. Fixes (test-only, production untouched)

- `tests/test_probe.py`: `make_isolated_probe` helper (temp store + cleanup,
  `make_probe` pattern); 5 message-feeding tests use it.
- `tests/test_host_telemetry.py`: same helper; 2 byte-counting tests use it.
- `tests/test_p14b_3_transport_freshness.py`: same helper in
  `TestAcceptedTrafficAccounting._probe`.
- `tests/test_probe_control.py`: `start_probe(..., evidence_dir=tmp)`.
- `tests/test_process_identity.py`: `start_probe(..., evidence_dir=tmp)`.
- `tests/test_supervised_launch_corrections.py`: additionally patch
  `pc.repo_root` in `test_default_supervisor_command`.
- New `tests/test_persistence_isolation.py` (5 tests): forbidden-factory +
  temp-landing for the three helpers; temp landing for `start_probe` and the
  default watcher spawner.

## 5. POSTFIX verification (exit 0)

Evidence: `docs/evidence/TEST_ISOLATION_AUDIT_POSTFIX.json`.

- **916/916 green, prohibited hits ZERO** (no factory calls, no canonical
  file writes, no registry writes), `data/`+`logs/` inventories clean.
- 100 residual connects, all classified: 67 Route B (64 + 3 from the new
  regression probes), 33 Route C, 1 Route D. Byte-neutrality proven by equal
  hashes, not assumed.
- Canonical `python run_tests.py -q`: **916/916 OK (162.068s)** with
  `microprobe.db` SHA256 stable at
  `221b33…fb86` before/after (plus historical.db `ca6479…` and registry
  `45c6a3…` unchanged). The whole-suite preservation failure is FIXED.
- Pure read-only re-check: **375 universe rows, 225 `detail='test'`** —
  unchanged, retained without cleanup/quarantine/reclassification.

## 6. Residual + blocker (no silent exclusion)

Routes B/C remain by design: eliminating them needs production injection
points (lazy prospective rehydration or config `db_path`; injectable
history store for `DashboardState`) — deferred, NOT implemented here, since
this stage forbids productive-behavior changes. "Complete purity"
(zero canonical connects) is therefore NOT claimed; zero prohibited writes
is proven. The 225 tagged rows keep their source-quality notice until
Etapa 2 dispositions provenance.

## 7. Closeout (seven fields)

- `DECISIONS_REVIEWED`: AGENTS.md ordering set (CURRENT_STATE, TASK_QUEUE,
  MASTER_PLAN, DECISIONS, SUCCESS_GATES), ARCHITECTURE/EVENT_LABELING
  research specs, DASH_V2_71B_REVIEW_CORRECTIONS,
  DASHBOARD_V2_71_SYSTEM_DATA_CONTRACTS, frontend
  DASHBOARD_V2_71_SYSTEM_INTEGRATION (from Git only).
- `NEW_DECISIONS_RECORDED`: prohibited-vs-residual write classification;
  fixture pattern (`make_isolated_probe` + `evidence_dir` + `pc.repo_root`
  patch); production untouched, Routes B/C deferred — appended to
  `docs/DECISIONS.md`.
- `FEATURES_IMPLEMENTED`: Etapa-1 barrier + repro + 6 test-file fixes + 5
  regression tests (no backlog ID; test-hygiene enabling work).
- `FEATURES_VERIFIED`: 916/916 canonical (162.068s) + barrier exit 0 +
  stable microprobe hash + 375/225 pure re-read; evidence links above.
- `DEFERRED_FEATURES`: production injection points for Routes B/C; Etapa 2
  provenance; Etapas 3–5 contracts/prep (separate stages).
- `BACKLOG_UPDATED`: this file is new; FEATURE_BACKLOG carries the Etapa-1
  line (no ID completed/verified beyond enabling work).
- `DOCUMENTATION_CONFLICTS`: prior 729-test/six-error audit superseded by
  full-911 audit (path bug, fixed); "green suite" overclaim corrected
  (61 swallowed attempts while green).
