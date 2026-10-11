# DASH-V2-51 - Enforcement follow-up and pure runtime observation
Backend audited: 07866176559954818dfccf880106bdf22feab40d.
Frontend baseline: d80fb9bef94a33dd912ee07c41d62e9cf9bed9da.

## Bounded plan
1. Review exact SHA and rerun enforcement/contract/sentinel regression suites.
2. Reproduce post-claim takeover, wrong-run lease and status terminal overwrite
   with temporary registries and mocked process termination only.
3. Remove legacy mutating status() from V2 observation and command preflight.
   Require canonical status_readonly(); absence must return explicit UNKNOWN/error.
   Do not implement a second lifecycle manager or a shadow-registry workaround.
4. Preserve recorded evidence independently; keep Start blocked.
5. Run frontend checks, V2 Python snapshot suite and desktop/mobile QA.
6. Publish evidence and precise backend owner follow-up. No backend edits or runs.

Acceptance: GET paths never invoke legacy status(); missing pure capability
does not trigger mutation; command preflight refuses unsafe fallback; clear
source-unavailable presentation; tests pass; no page overflow.
Rollback: frontend-only Git revert. Runtime launch gates remain unchanged.

## Independent findings at 0786617
48/48 enforcement + supervision-contract + sentinel tests rerun, exit 0.
Owner's full 808/808 result is reported evidence, not a full backend rerun here.

Accepted: STOPPING acquisition is locked; previous foreign owner/terminal
snapshot/write failure cases refuse before termination; terminal and timeout
marking check run PID/ctime and own marker; actual aborted_by persisted;
sentinel_once uses fenced heartbeat; duplicate/unreachable fragments removed.
The heartbeat test now performs writes and checks advancement and surviving
distinct updates. It is still a thread test sharing one process PID, not a
two-process-owner test. Silent OSError handling inside heartbeats means its
errors list alone cannot prove that every call wrote successfully.

### HIGH - unlocked interval between claim and termination
update_registry(_claim_stop) releases its lock before _terminate_verified_pid.
A takeover inserted after successful acquisition still reaches termination
for both owner kinds; terminal marking later returns superseded. That protects
the record after the action, not the action itself.
The termination helper still accepts PID alone and opens a process handle
after the previous identity check; handle identity must be verified to address
PID reuse, independently of registry ownership.
Both simulated calls: terminate_called=true, owner=999999, result=superseded.

### HIGH - owned lease need not cover the run being terminated
_owns_lease checks only watcher PID. _claim_stop does not compare watched_pid
to the run PID or validate owner lease identity at the operation boundary.
Owned lease with watched_pid=999999 while run pid=424243 reaches termination
and returns aborted=true, for both supervisor and sentinel.
Run association was explicitly required by the preceding task.

### HIGH - status() is not a pure read
Known residual confirmed: stale RUNNING snapshot + new ABORTED record,
is_canonical_pid=false -> status writes FAILED and removes abort evidence.
This affects V2's previous GET polling/readiness/diagnostics because all share
runtimeStatus(). A method name or HTTP GET does not make the controller pure.

## Frontend boundary decision
V2 requires canonical status_readonly() for GET observation and command
preflight. Absence returns READ_ONLY_STATUS_REQUIRED and UNKNOWN; legacy
status() is never called as fallback. Start remains blocked in both route
and helper. Recorded SQLite evidence is independent and remains available.
Current backend has no pure method, so runtime observation is intentionally
paused until its owner supplies and we audit that capability.
No duplicate lifecycle implementation, monkeypatch or shadow-registry adapter.

## Owner follow-up - no market runs
1. Fence the operation boundary through termination, not only acquisition
   and terminal marking. Preserve owner/run association through the action;
   verify PID/image/ctime on the actual handle used to terminate. Document
   how takeover/identity changes cannot interleave at that boundary.
2. Require owner lease watched_pid == target run PID and verified owner
   identity; test both owner kinds, wrong-run lease and post-claim takeover.
   Refusals must leave termination mock uncalled.
3. Add status_readonly(): same nullable status/watcher shape, no registry
   writes, reconciliation, log-handle mutation or process action. Exercise
   missing/dead/reused PIDs and races with ABORTED/STOPPING. Preserve bytes.
   Keep mutating reconciliation separate and fence it against current state.
4. Add independent process-owner concurrency tests, count actual writes and
   fail on dropped/silent errors; prove one claim winner. Existing thread
   test improvement is accepted but does not fulfill process-owner coverage.
5. Review remaining unlocked stop_probe/try_register/status writers before
   claiming the operation lock prevents races across the whole controller.
6. Rerun full suite, update factual docs and publish exact SHA. Preserve DB,
   logs, V2 and main. No new probe/market run or success-gate advancement.
Transactional supervised launch remains a separate pending task.

Evidence: scripts/review-p1-14b8-final-fencing.py and
design/qa/v2-51/backend-reproductions.json. All destructive actions mocked;
all registry mutations restricted to TemporaryDirectory.

## Frontend verification and closeout
Frontend 118/118 tests, 27 files, type/lint/build PASS.
V2 Python snapshot 496/496 PASS, 80.182 seconds; separate from owner's 808 suite.
Executed exact pure-status bridge with synthetic RUNNING registry: response
READ_ONLY_STATUS_REQUIRED, temporary registry bytes unchanged, canonical
registry SHA-256 unchanged (pure-guard.json). No market process action.
System + Overview at 1672/1366/390: 6 browser cases PASS, zero browser errors,
no whole-page overflow, correct main/title/navigation; expected pause alert
outside disclosure and disabled Start verified. Production DTOs show UNKNOWN
with explicit error; expanded captures retain separate watcher evidence areas.
Shared System frame reviewed against previously inspected approved system.png.
Fidelity remains PARTIAL: source pause/unknown states and archived evidence
replace illustrative healthy charts/counters; unsupported pipelines stay absent.
Canonical V2 updated by PID/image/creation-time-verified restart only.
No backend source modification, new market run or success-gate advancement.

DECISIONS_REVIEWED: WORKFLOW, V2-50 observation display, API contracts/backlog,
preceding V2 enforcement review and exact backend diff.
NEW_DECISIONS_RECORDED: V2 DECISIONS - pure status required, no mutating fallback.
FEATURES_IMPLEMENTED: bounded safe-observation boundary within F-V2-BFF-01.
FEATURES_VERIFIED: bridge byte-preservation test, 118 frontend tests, production
read-only DTO and desktop/mobile pause presentation. Feature remains PARTIAL.
DEFERRED_FEATURES: source status_readonly, operation-boundary enforcement,
process-owner concurrency coverage, fenced remaining writers, transactional
V2 launch, full System contracts and backtest/paper engines.
BACKLOG_UPDATED: yes; accepted improvements and exact remaining blockers.
DOCUMENTATION_CONFLICTS: thread tests are not independent process-owner tests;
locked acquisition does not cover termination interval; prior GET bridge was
not inherently read-only. Current documents record the explicit paused state.

NEXT: bounded backend owner task above, then review exact new SHA. Do not
enable runtime launch or interpret DONE acotado as general safety PASS.
