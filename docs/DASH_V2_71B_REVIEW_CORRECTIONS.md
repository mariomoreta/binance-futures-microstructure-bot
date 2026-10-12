# DASH-V2-71B reviewer proof corrections
Date: 2026-10-11. Reviewed backend 89232f734b0ac80238060347b0a3fd5eacffbe65.
Bounded proof/documentation corrections, no application source change.

Independent discovery and canonical run confirm 910 tests on the published
SHA, exit 0. The earlier 905 result was not reproduced; root cause unknown.
Original test omitted its historical DB byte comparison and allowed new
logs. Historical tempfile mutation control passed the old test and is
rejected by the strengthened existing test. Four HistoryStore.init_db
calls leave final bytes equal in the fixture, demonstrating why this is
not a readonly-connection certification. Env patches now restore values.

V2 continues using its own fixed-path readonly adapter. Canonical query reads were read only; subsequent suite-level contamination
is explicitly corrected and recorded below.
Their origin is not attributed to a test file merely from matching text.
No cleanup or data exclusion is authorized/performed here.

DECISIONS_REVIEWED: V2-69/70 and backend V2-71B contracts.
NEW_DECISIONS_RECORDED: final-byte equality does not prove no write path;
historical-byte assertion and historical-tempfile negative control required.
FEATURES_IMPLEMENTED: existing purity test strengthened and doc scope fixed.
FEATURES_VERIFIED: original 910, historical mutation control, focused/final
verification below; no test-count increase.
DEFERRED_FEATURES: origin audit, retirement, host/ops source, Start, longevity.
BACKLOG_UPDATED: bounded proof correction; full BFF remains PARTIAL.
DOCUMENTATION_CONFLICTS: historical bytes/log tolerance and readonly
overclaim resolved; recorder defaults do not become observed evidence.

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
