# DASH-V2-71 — recorded System integration
Date: 2026-10-11. Frontend base f52b68fc72dd3b4c5dc6dc6d7085f411c64fa900.
Bounded presentation/integration DONE after final verification; complete cutover remains PARTIAL.

## Implemented
System uses two responsive three-column panel rows matching the approved
System composition: transport, persistence, prospective research,
universe allocation, classifier/opportunities, and explicit host/service
source absence. Launch readiness is a separate keyboard-accessible
disclosure; runtime controls remain unchanged with Start disabled.

New fixed-path schema-9 readonly transaction projects /api/v1/system-evidence
(schema_version 1, no-store, 200 available / 503 unavailable). No writable
store constructor, Python acquisition, old HTTP dependency or new DB.
System rereads stored evidence every 15s while visible, with bounded retry;
polling does not acquire market data. Read time is not observation time.

Source timestamps remain independent: discovery updated_ms; classifier
and candidate stored-update spans; prospective detected_at_ms/observed_at_ms;
telemetry seconds converted to milliseconds; price bucket_ms. Stored update
time is not independently verified evaluation time. Versions are retained
rules, not proof of running engines. Counters describe retained populations
rather than current sessions or 24-hour rates.

Persistence reports logical allocated SQLite page bytes, not host disk use.
Research COMPLETE outcomes are recordings, not profitable trades. Queue,
drops, capacity, CPU/memory and operational-event feed remain unavailable.
Classifier/lifecycle aggregates include unknown/malformed records explicitly;
distinct versions bounded to 20 with overflow flag; discovery JSON capped
at 1 MiB before parsing. Query aggregate cost grows with retained populations;
this is bounded output, not a guaranteed fixed execution-time budget.

## Source-quality limitation from backend review
At the initial review 222 retained universe rows carried detail='test';
the final read reports 225 (see checkpoint and test-isolation correction below). Their origin remains
unverified; no record was deleted, quarantined or silently excluded.
API exposes the flagged count and Universe shows a prominent source-quality
notice. The retained total is not certified operational activity.
Potentially matching test source text does not establish provenance.
The HOT fixture leakage is corrected below; older-row lineage remains unaudited.

## Verification
207/207 frontend tests (192 + 15), 43 files; typecheck/lint/build exit 0,
one existing BotControl lint warning. Frontend Python snapshot canonical:
496/496 OK, 92.448s, process exit0; no Python source change in this checkout.
Initial shell wrapper reported exit1 despite OK; subprocess rerun confirms
exit0. Backend tests are separate and reviewed below.

Native-SQL comparison: 66 setups, 228/228 COMPLETE outcomes, 392 opportunity
events, 500 state transitions, initially 366 universe rows (final 375), 14 retained classifications,
68 candidate keys. Universe saved record: CORE3/HOT0/eligible439.
Candidate labels include 12 ACTIVE_RESEARCH, which never means open positions.

Readonly GET matrix: system-evidence plus eight existing routes, no-store
contract, exact SQL totals/group sums, and both canonical DBs/registry hashes
unchanged. Browser System 1672/1366/390, controls disclosure/Refresh,
launch-preflight disclosure and Overview smoke pass, zero overflow or errors.
Screenshots/source audit/check outputs in design/qa/v2-71.

Manual desktop/mobile review against design/references/v2-approved/system.png:
six-panel composition and dense row styling advanced; exact fidelity PARTIAL.
Reference demo gauges/health, host resources, operational log and icons are
not fabricated. Before-capture attempt timed out while the running Next
output was rebuilt; committed V2-70 captures serve as historical baseline.
Final managed restart and fresh after-captures pass. Build-output isolation
should be a separate deployment improvement, rather than repeating this
running-output rebuild workflow.

## Backend DASH-V2-71B review
89232f734b0ac80238060347b0a3fd5eacffbe65 is docs plus one test; no source change.
Independent discovery/canonical confirm 910/910; prior 905 count unreplicated,
root cause not established. Found missing historical-byte assertion and
new-log tolerance. Reviewer strengthened existing test without count increase,
restored environment overrides, and corrected purity/recorder/retention claims.

Historical-tempfile mutation passes original test and fails strengthened test.
Four HistoryStore.init_db calls leave final bytes equal in this fixture:
final-byte equality does not certify readonly connections or intermediate
writes. V2 retains fixed-path DatabaseSync readOnly adapters. Exact correction
SHA and focused/final results are recorded at checkpoint.

## Remaining and closeout
Old dashboard retained; no retirement, collector runs, backfills, market
traffic, Start, paper/orders, main merge or SUCCESS_GATES changes.
Host/resource/operational-journal source and complete legacy parity remain
pending. NEXT: readonly audit of test-marker origin and test fixture isolation;
then contract-specific integration. Do not clean canonical evidence by guess.

DECISIONS_REVIEWED: V2-69/70, System reference, BFF migration, backend71B.
NEW_DECISIONS_RECORDED: independent dated aggregates; test-tag quality flagged
without altering populations; final bytes are not readonly certification.
FEATURES_IMPLEMENTED: system adapter/API, six-panel layout, polling and
provenance notice; backend existing proof/docs correction.
FEATURES_VERIFIED: 207 frontend, 496 snapshot Python, native SQL/GET/hash
matrix, three browser widths/disclosures/Overview; backend910 below.
DEFERRED_FEATURES: lineage audit, host/ops adapter, deployment isolation,
complete legacy cutover, Start and longevity.
BACKLOG_UPDATED: F-V2-BFF-01 and F-V2-DATA-MIG-01 bounded System slice;
overall PARTIAL, no gate change.
DOCUMENTATION_CONFLICTS: absent recorder block/default zeros clarified;
hist-byte assertion/log tolerance/readonly overclaim corrected; retained
events not declared certified operational history.

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

Backend corrected/pushed SHA: aea037629ed867534c68474bea6b883a19e280bf
System production managed restart PID27636; 207/207 frontend, typecheck/lint/build0; snapshot496/496. Fresh browser1672/1366/390 and nine readonly GETs/native SQL checks pass. Final GET read: 375 universe rows/225 tagged, included verbatim. Canonical hashes unchanged during GET checks. Visual parity and full cutover PARTIAL.
