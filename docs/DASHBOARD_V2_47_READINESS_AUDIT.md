# DASH-V2-47 — Evidence-based runtime readiness

Date: 2026-10-10. Source: `dash-v2-03-token-detail` at
`fcaaca2c29c131c5d2192b4461320d09cb78ccde`.

## Audit and bounded plan

The unavailable-controller fallback asserted mode=observe, causing the
observe-only readiness check to PASS without evidence. UNKNOWN and unsupported
process states also cleared the concurrency check. JSON null could throw;
arrays and scalars were accepted as controller objects.

Correct only runtime-response normalization and readiness decisions. Preserve
explicit observed states, controller errors and UNKNOWN. Do not enable start,
change Python, query Binance, touch production databases or alter layouts.
Acceptance: regression tests fail on the old code and pass after correction;
frontend checks/build pass; unavailable-backend production HTTP returns UNKNOWN.
Rollback: revert this frontend/documentation commit.

## Result

- Unavailable/missing mode stays UNKNOWN; nonzero command exit never asserts observe.
- Non-object JSON is rejected; absent/nonboolean running evidence yields UNKNOWN state.
- Controller-reported errors propagate to readiness instead of clearing checks.
- Only STOPPED/COMPLETED/FAILED explicitly clear concurrency. Active, STARTING
  and STOPPING remain BLOCKED; unsupported/UNKNOWN states remain UNKNOWN.
- Atomic supervised launch remains BLOCKED, ready=false. No start/stop invoked.

## Verification

- New targeted Vitest: 18/18 PASS. Same tests against original frontend:
  12 FAIL, 6 PASS (original files restored only during that controlled check).
- Complete frontend Vitest: 84/84 PASS, 23 files.
- TypeScript, ESLint, production Next build: PASS.
- Initial type/build attempt found a file omitted by retrieval; recovered the
  exact original LiveMoversView.tsx and reran successfully. No change to that file.
- Production HTTP smoke on free 127.0.0.1:3020: runtime and readiness both 200;
  absent Windows controller/database yields UNKNOWN checks and ready=false.
  Temporary smoke server stopped by its own Popen handle.
- Canonical Python suite: 496 run, 494 PASS, 2 FAIL. Failures:
  test_dashboard.PidfileTest.test_live_python_pid_is_ours and
  test_probe_control.RegistryStatusTest.test_register_flows_running.
  Both reproduce independently on unchanged Python sources: process_info()
  invokes Windows tasklist/WMIC, unavailable on this Linux host.
  This is NOT a full Python PASS; Windows re-verification remains pending.
- Visual verification: NOT APPLICABLE to this nonvisual contract correction.
  No screenshot/design-parity claim. Windows runtime/deployment unverified.

## Closeout

- DECISIONS_REVIEWED: DASHBOARD_V2_DECISIONS.md, frontend architecture and
  repository dashboard-v2 skill; retain UNKNOWN and observe-only boundaries.
- NEW_DECISIONS_RECORDED: no new product/methodology decision; this corrects
  implementation to the existing missing-evidence contract.
- FEATURES_IMPLEMENTED: F-V2-BFF-01, partial runtime readiness correction only.
- FEATURES_VERIFIED: F-V2-BFF-01 targeted normalization/readiness tests and
  unavailable-backend HTTP smoke; full integration not VERIFIED.
- DEFERRED_FEATURES: atomic supervisor+sentinel launch, Windows acceptance,
  source-populated UI validation, CMC, paper/backtest functionality.
- BACKLOG_UPDATED: yes; scoped BFF evidence addendum, no complete-feature claim.
- DOCUMENTATION_CONFLICTS: uploaded docs end at DASH-V2-02, branch progress
  reaches DASH-V2-46; branch CURRENT_STATE/TASK_QUEUE contain older backend
  records than attachments. Neither was treated as current Windows runtime.
  Backlog's static-only BFF status is superseded by a scoped PARTIAL addendum.

Next: verify on Windows and reconcile the owning backend's atomic launch
contract before considering any start enablement.
