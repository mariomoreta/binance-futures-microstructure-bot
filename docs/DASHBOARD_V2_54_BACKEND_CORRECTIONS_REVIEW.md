# DASHBOARD V2-54 - Published backend b801ab0 corrections review

Date: 2026-10-11.
V2 base: c8a2b99c3af0cf494727fa26b245d4b37f886478.
Backend base/final reviewed: 55efaa2b171c83701f6736ab6e6374869a733af1 ->
b801ab094d64b6b45caabfc7fed22276abb0c0b6 (origin identical).
Verdict: bounded review complete; original defects improved, two precise follow-ups remain.
No general PASS, operational authorization or strategy-validation claim.

## AUDIT / PLAN

Read project workflow, V2 skill, current state/queue, backlog/decisions and the
V2-52 report at 066577e. Fetched the published backend into V2 Git objects and
exported an isolated temporary source archive. No backend tree mutation, merge,
cherry-pick, canonical probe launch or frontend/runtime rebuild.
Plan: verify H1/H2/C1 corrections, run published-source tests, exercise exact
V2 pure-status bridge with temporary registries, document bounded conclusions.

## Accepted corrections

- H1 original failure: native return 0 now returns False and records bounded
  error evidence; return 1 returns True. Pointer-width HANDLE arguments for
  TerminateProcess/CloseHandle are configured. Handle closure and same-handle
  identity checks exist. No false ABORTED process claim was established before
  or in this review. Remaining BOOL-width issue below is separate.
- H2 original race: same PID+ctime child-first registration is adopted without
  killing that child. Existing populated evidence survives adoption. Foreign
  winner, reused PID and write-failure cleanup regressions pass.
  Adopting absent evidence leaves a log-discovery gap below.
- C1: heartbeat workers now rendezvous at a shared barrier; ten effective writes
  per owner and both final timestamps within a bounded current window are checked.
  This proves bounded multiprocess coverage and timestamp freshness. It does not
  prove strict advance relative to claim timestamps, forced write interleaving
  or longevity; repeated writes can share an ISO second. Accept with this scope.

## R1 - Native BOOL declarations use one byte, not Windows BOOL

control.py uses ctypes.c_bool restype for TerminateProcess, CloseHandle and
GetProcessTimes; OpenProcess's inherit argument also uses c_bool.
On reviewed Windows, sizeof(c_bool)=1 while sizeof(c_int)=4.
Official Windows BOOL is an int; TerminateProcess success is any nonzero return.
The new Python fake entry points record signature attributes but do not marshal
returns, and tests merely assert attributes are non-null.

A hermetic WINFUNCTYPE callback returned signed 32-bit 256; the helper configured
its return as c_bool and observed False. No kernel process API was called.
This proves a declaration/marshalling defect. It does NOT prove that the actual
Windows TerminateProcess implementation returns 256 or that a live kill failed.
Use ctypes.wintypes.BOOL (or an explicit compatible 32-bit type) for actual BOOL
parameters/results and assert exact signature types/widths. Include an ABI
callback test for 0, 1 and another nonzero value, retaining HANDLE-width checks.
GetProcessTimes prototypes are assigned using locally constructed structure
types; review binding consistency rather than silently accepting setup exceptions.

Sources checked 2026-10-11:
- [Microsoft Windows types](https://learn.microsoft.com/en-us/windows/win32/winprog/windows-data-types)
- [Microsoft TerminateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess)
- Local reviewed Python ctypes widths; ABI callback is recorded in evidence JSON.

## R2 - Child-first self-registration loses the parent's log association

The new test inserts a handcrafted RUNNING record containing child-evidence.log.
Actual try_register() starts with preserved_evidence=None when the registry is
empty; it can only inherit evidence from an already-present same-PID record.
start_probe() creates its own log, spawns the child and later adopts the child's
registration verbatim, including evidence=None. Neither registration nor the
response supplies the created log path in that ordering.

Reproduction invokes actual try_register() from a mocked Popen callback against
an initially absent temporary registry, with identity/PID mocked:
started=True, adopted_child_registration=True, kill count 0,
registry bytes preserved, created log exists, response/record evidence null.
collect_supervision_snapshot leaves key log-derived measurements null while some
other fields retain defaults (for example persistence_errors_10m=0). Those
defaults do not establish healthy persistence. Its
documented rules skip unavailable inputs; this is loss of log-derived coverage,
not proof that all supervision or sentinel protection disappears.

Preserve populated child evidence and identity/state. Ensure the controlled
parent's evidence is associated with the same child when evidence is absent,
via a safely bound handoff or a fresh locked same-PID+ctime conditional update.
Do not overwrite a foreign run, terminal/enforcement state or valid child log.
Test actual try_register for child-first and parent-first order, populated
evidence, write failure and intervening takeover/STOPPING. Never invent a log
path for a direct launch that did not create one. No new launch transaction
or wire contract is required by this review.

## V2 integration / TEST / VISUAL VERIFY

Published backend archive: python run_tests.py, 840/840 OK, 162.462s, exit 0.
V2 Python snapshot: python run_tests.py, 496/496 OK, 67.975s, exit 0.
Exact-SHA script: scripts/review-p1-14b8-v2-54.py.
Evidence: design/qa/v2-54/backend-reproductions.json.
Script compares archived control.py bytes with published Git source before import.
BFF pureStatusCode from current runtime-control.ts was run against archived backend
and temporary RUNNING, STOPPING, ABORTED, COMPLETED and absent records: 5/5 passed;
existing bytes unchanged, missing registry not created.
No frontend contract/copy change is needed. Recorded process and elapsed-time
semantics from V2-52 remain appropriate. Start remains disabled.
Visual verification NOT APPLICABLE: nonvisual review/documentation only.
Existing visual reference parity remains PARTIAL, not revalidated here.
No backend source changed by this V2 checkpoint; no canonical database/logs mutation, market
runs, backfills, P1-14C, paper, orders, gate advancement or main merge.

Residuals: POSIX PID reuse window; absent ctime; pid-only heartbeat ownership;
CLI mutation paths by design; target OS liveness not certified by pure status;
transactional supervised launch separate; no new supervised longevity window.
Open+queryable process times is not by itself proof of current process liveness.

## Owner follow-up prompt - deterministic, bounded

Base branch phase1/market-intelligence-dashboard at b801ab0.
Read this report, script and evidence JSON from the containing V2 commit via Git,
without modifying V2. Reproduce R1/R2 before changing code.
Fix Win32 BOOL signatures with exact type/width assertions and ABI-marshalling
regressions. Close the child-first log association gap using actual try_register
tests and locked identity/state checks; preserve nonempty evidence and foreign/
terminal/enforcement records. Qualify C1 as shared-start, counted writes and
in-window timestamps, unless strict advancement is explicitly tested.
Review native callers and factual docs. Run python run_tests.py and selectively
commit/push only owned backend files. Preserve GET status_readonly, existing
contracts, V2/main/SUCCESS_GATES, SQLite/logs/evidence and unrelated work.
No probes, long runs, paper, Start or trading. Report initial/final/remote SHAs,
failing-first cases, results, remaining residuals. Use DONE bounded, not PASS general.

## DOCUMENT / CHECKPOINT / closeout

DECISIONS_REVIEWED: V2-52 correction requirements, pure observation boundary,
V2-53 proposal traceability and backend published correction notes.
NEW_DECISIONS_RECORDED: no new operational permission; exact BOOL representation
and genuine self-registration evidence are required for correction acceptance.
FEATURES_IMPLEMENTED: review script, deterministic evidence and documentation.
FEATURES_VERIFIED: published 840-test suite and 5-case pure bridge; original 0
refusal propagation and same-child survival accepted within stated limits.
DEFERRED_FEATURES: R1/R2 backend follow-up; transactional supervised launch;
longevity; OS-liveness contract; complete reference parity and research proposals.
BACKLOG_UPDATED: F-V2-BFF-01/F-V2-SYSTEM-01 remain PARTIAL; no feature/gate promotion.
DOCUMENTATION_CONFLICTS: BOOL-checked is not exact Win32 type correctness; evidence
preserved may preserve null; in-window timestamps are not strict progression.
