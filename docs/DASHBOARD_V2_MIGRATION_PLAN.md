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


# Dashboard V2 Migration Plan

## DASH-V2-71 — 2026-10-11 — recorded System integration
Schema9 fixed-path readonly system adapter/API, six-panel layout, dated
independent counters/classifier/lifecycles, 15s stored-data refresh implemented.
207 frontend + type/lint/build;496 V2 Python; native SQL/9 GET/hash purity;
System3 widths, control/preflight disclosures and Overview pass. Reference
fidelity/full cutover PARTIAL. 222 universe rows marked detail=test remain
unverified; prominent notice, no deletion/exclusion. Backend89232f7 reviewed
910 baseline; existing purity proof/docs strengthened (historical-byte
assertion, no new logs, env restoration); no application source change.
See DASHBOARD_V2_71_SYSTEM_INTEGRATION.md and backend correction report.
Next: readonly origin/fixture-isolation audit, host/ops contract, deployment
build isolation. Old UI/Start/gates/main/DB retained. Exact published SHAs
and final backend results recorded in checkpoint section.


## DASH-V2-70 / V2-69 — 2026-10-11 — extraction accepted and recorded diagnostics
Backend c59c5ec extraction accepted after direct proof/docs repair published 9f3e084192e90b52948c398f021f64b7884e2df2; independent 909/909, no reviewer application-source edit. See DASHBOARD_V2_69_EXTRACTION_ACCEPTANCE.md. V2 recorded diagnostics now avoid timestamp-based run association and display missing-stream, parse/payload-error and signed clock-offset fields. 192/192 frontend, type/lint/build pass; System 3 widths, disclosure/refresh and Overview check pass, zero overflow/browser errors; canonical DB/registry bytes unchanged. Production http://127.0.0.1:3020 managed PID23296. See DASHBOARD_V2_70_RECORDED_DIAGNOSTICS.md. Exact reference fidelity/full cutover remain PARTIAL. Next V2-71 source-backed pipeline/persistence/universe parity; host/events require separate contracts. Old HTML, Start, gates, main and runtime operations preserved.



## Current implementation checkpoint — 2026-10-11
The 2026-10-07 plan below is historical. V2 is implemented at loopback port 3020; main persisted-data migration is DASH-V2-63. See its migration matrix/report and canonical data contract. Old SSR retained; full cutover gate NOT accepted. The backend/control authority and collector remain unchanged. The next migration phase is an exhaustive legacy-function coverage audit, not another demo scaffold.


**Purpose:** migrate presentation in parallel while preserving the verified
Python backend and current dashboard.  
**Status at 2026-10-07:** PLAN APPROVED; NO MIGRATION IMPLEMENTED (historical; current checkpoint above).
**Date:** 2026-10-07.

## Invariants

- Existing Python dashboard stays available at `http://127.0.0.1:8091` unless
  its own safe first-free policy selects another port.
- Proposed Next.js default `127.0.0.1:3000` is checked before use; no process is
  killed for a conflict.
- No MarketProbe/formula/history/recorder/registry/control behavior changes as
  a side effect of frontend work.
- No second process manager, browser SQLite, credentials, live trading or
  dashboard-to-engine decision path.
- Every slice is independently reversible and keeps Python SSR usable.

## Stages

### DASH-V2-ARCH — this documentation checkpoint

Architecture, design tokens, current/missing API contracts, provider study,
identity policy, migration gates, agent handoff and project-local skill.
Acceptance: docs/link/path checks; full Python suite green; no production code,
runtime or dependency change.

### DASH-V2-00 — scaffold and primitives

Create `frontend/`, strict TypeScript/App Router, shell, tokens, status/source/
freshness components, test harness and an allowlisted read-only BFF skeleton.
No live controls. Acceptance: build/lint/type/unit/E2E shell checks, screenshot
comparison with supplied references, Python suite green.

### DASH-V2-01 — Overview

Implement versioned overview facade/BFF, real health/pulse blocks and honest
external-context placeholders. Acceptance covers all capability/freshness
states, real-data screenshot and no fabricated metrics.

### DASH-V2-02 — Movers

Typed paginated/filterable table, real sparklines and numeric contracts.
Acceptance re-proves category field/unit isolation and sign-filtered velocity.

### DASH-V2-03 — Symbol Detail

Chart and feature/research panels, history-only routes, identity/profile
surface. Acceptance includes `ORCAUSDT` historical-only and `龙虾USDT`
unknown-mapping fixtures, partial/warming/stale/degraded/unknown states.

### DASH-V2-04 — System and control

Diagnostics plus secure BFF integration with the existing control plane.
Acceptance: nonce never reaches browser; Origin/Host/CSRF/allowlist tests;
short bounded observe start/status/stop only when explicitly authorized; no
runtime interruption during ordinary tests.

### DASH-V2-05 — Opportunities shell

Explanatory capability/blocked shell and future typed contract. No candidates,
probabilities or trade fields until P1-12/P1-13A provide them.

### DASH-V2-06 — advanced charting/history

Incremental chart series, comparable source-labeled context and historical
projections. Add TradingView attribution if Lightweight Charts is adopted.

### CMC-00 / CMC-01 / CMC-02

- CMC-00: provider feasibility fixtures + identity mapping persistence design.
- CMC-01: bounded keyless ID/metadata adapter only after approval.
- CMC-02: optional quotes/indices/context only if measured research value and
  licensing/budget remain acceptable.

No provider work is required to deliver core Binance screens.

## Slice workflow

`AUDIT -> PLAN -> IMPLEMENT -> TEST -> VISUAL VERIFY -> DOCUMENT -> CHECKPOINT -> NEXT`

Each slice records starting/ending SHA, files, exact commands/results,
screenshots, known gaps and the next gate in `DASHBOARD_V2_PROGRESS.md`.
Stage only coherent intended files. Stop on unresolved tests, security
weakening, missing reference decisions, provider/legal uncertainty, engine
methodology change or need for credentials/runtime disruption.

## Cutover gate

Do not retire Python SSR until V2 covers Overview, Movers, Symbol Detail and
System/control with parity tests; survives a bounded parallel observation;
passes security/accessibility/visual checks; and the operator explicitly
approves cutover. Retirement is a later task, not implied by V2 completion.

## Phase dependencies

P1-10R is PASS (2026-10-08); P1-12A classifier v0 is DONE. P1-12B and
functional Opportunities, Backtest and Paper Lab remain bound to their
engine phases (see `docs/FEATURE_BACKLOG.md` F-UNI-01, F-OPP-01,
F-BT-01, F-PAPER-01). Documentation work does not advance those gates.

## DASH-V2-64 - next coverage sequence
Current exhaustive coverage assessment and retirement criteria: DASHBOARD_V2_64_CUTOVER_AUDIT.md. Search/token fields -> ranges/exports -> historical studies/diagnostics -> reversible presentation cutover. Start/operating readiness and future research are separate gates. Backend contract/deployment handoff: DASHBOARD_V2_64_BACKEND_HANDOFF.md.

## DASH-V2-65 - 2026-10-11
V2-65 delivered retained-symbol search and additional saved token fields. Next V2-66 range selectors and exports; legacy retirement criteria remain V2-64, no operation gate advancement.

## DASH-V2-66 - 2026-10-11
V2-66 five ranges and bounded exports delivered; next V2-67 saved historical coverage/study routes/diagnostic presentation. Complete retirement still requires V2-64 acceptance matrix.

## DASH-V2-67 - 2026-10-11 - exact backend contract reconciliation
Backend 5dedacb local/origin verified; documentation+3 tests only since c635938. Focused3 and canonical905 independently pass. Five V2 GET checks and unchanged registry bytes recorded. Separate historical DB schema2 has14 coverage rows/2831 event instances; existing historical-research endpoint is prospective archive, not bar/study parity. No automatic SHA guard in runtime bridge; manual verification clarified. Search/window/Unicode residuals explicit. See DASHBOARD_V2_67_CONTRACT_RECONCILIATION.md and backend handoff. Next frontend V2-68: readonly coverage/studies presentation; backend owner: shared-helper extraction, no retirement. Full cutover/BFF remains PARTIAL; Start/gates unchanged. Nonvisual review only.

## DASH-V2-68 - 2026-10-11 - historical coverage and studies
Separate readonly historical.db adapter/API and coverage/study view implemented at /historical-research/coverage; archive naming/navigation and token links clarify provenance.183/183 frontend,496/496 V2 Python, types/lint/build,8 HTTP cases with native aggregation/hash parity and57 browser cases pass. Exact visual fidelity NO DEDICATED REFERENCE/PARTIAL. See DASHBOARD_V2_68_HISTORICAL_COVERAGE.md. Backend worktree has other agent's uncommitted helper-extraction changes; no new backend acceptance inferred. Full cutover/BFF remains PARTIAL. Next V2-69 diagnostic parity audit; backend exact-SHA review when report arrives. Start/old fallback/gates preserved.
