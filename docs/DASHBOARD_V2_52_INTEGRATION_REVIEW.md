# DASHBOARD V2-52 - Backend 55efaa2 review and pure observation integration

Date: 2026-10-11. Frontend base: 35401f925b974bae7df07e15b35fddbcb3cac3c4.
Backend reviewed: 55efaa2b171c83701f6736ab6e6374869a733af1, local/remote identical.
Scope: read-only backend audit, hermetic reproductions, V2 presentation and browser QA.
Verdict: pure observation integration VERIFIED; backend correction remains DONE bounded,
not general PASS or operational authorization.

## Audit and plan
Read the repository workflow, V2 skill, current state/queue, decisions/backlog and
previous V2-51 review. Review exact backend source and run its complete test suite;
execute the exact V2 bridge against temporary registry bytes; inspect native termination
and start ordering; clarify recorded-state semantics; verify System/Overview at three
widths; document and publish only the V2 slice. No backend source edits or market runs.

## Accepted fixes
- STOPPING claim and final verify-plus-kill use locked fresh transforms. Post-claim
  takeover/run replacement and wrong-run/inactive leases refuse before termination.
  Supervisor and sentinel ownership checks bind the lease to the target run.
- Windows creation time is read on the handle passed to termination when expected
  creation time is available. This is an improvement; native binding is still incomplete.
- status_readonly() shares the nullable projection, never reconciles or writes runtime
  records, and does not close log handles or perform lifecycle actions. The exact BFF
  bridge preserved synthetic active bytes and the canonical registry SHA-256.
  Read-only watcher identity queries are distinct from lifecycle mutation; this review
  does not claim that projection of all possible leases performs no OS queries.
- Legacy reconciliation is locked and preserves actual terminal/owned STOPPING states.
  Existing reg/stop/start/terminal writers now use locked transforms.
- Multiprocess tests use distinct owners; effective heartbeat writes are counted,
  role fields survive and claim races retain contenders through a barrier.

## Remaining findings

### H1 - Windows API failure is accepted, native HANDLE signatures incomplete
In _terminate_verified_pid(), OpenProcess and GetProcessTimes have explicit signatures.
TerminateProcess and CloseHandle do not. TerminateProcess's BOOL result is ignored.
A fake kernel32, matching creation time and a handle 0x100000123 returned API result 0;
the helper returned True. No native process was touched.
The caller still checks process identity/death and waits up to ten seconds; this
reproduction does NOT prove a live process is falsely marked ABORTED. It proves that
native refusal is not correctly propagated. Missing pointer-width signatures also
leave 64-bit HANDLE conversion unverified; an actual high-handle failure was not run.
Fix both signatures, propagate BOOL failure and bounded OS error evidence, guarantee
handle closure, and test matching/mismatched creation time, native refusal/exception
and pointer-width arguments without touching canonical processes.
The documented unknown-ctime fallback is not accepted as complete identity protection.

### H2 - Parent start rejects its own already-registered child
start_probe() spawns before committing STARTING. If its own child self-registers
RUNNING first, _commit_start sees a live run and refuses without recognizing that child.
The rollback calls proc.kill(), returns started=False/already_running=True/pid=None,
and leaves the child's RUNNING record.
A mocked Popen inserted that child's registration into a temporary registry before
return; mock kill was called exactly once. No child/probe was actually launched.
Preserve the same child's PID+creation-time RUNNING registration; refuse genuinely
foreign runs. Test parent-first/child-first ordering, foreign winner and write failures.
This is a regression in the changed writer, separate from the still-pending supervised
transactional launch.

### C1 - Concurrency coverage is bounded
The heartbeat workers have distinct PIDs and assert ten effective writes each.
They do not use a heartbeat-start barrier or assert strict timestamp advancement;
the barrier is present in the four-process claim races. This is useful multiprocess
coverage, not proof of every heartbeat interleaving or long-term stability. Correct
wording or strengthen the targeted assertions without market runs.

## V2 integration and presentation
The existing capability-detecting BFF automatically uses audited status_readonly();
no backend cherry-pick or parallel lifecycle controller is needed.
The pause error READ_ONLY_STATUS_REQUIRED is gone for the present source.
Production reports recorded COMPLETED, raw supervisor/sentinel STOPPED displayed STALE,
and feed UNKNOWN. The old recorded run is not a new supervised window.

status_readonly preserves a stored RUNNING even for a dead/reused PID. It does not
publish verified target-process liveness. V2 now labels the first card Recorded process
and explicitly says current process liveness is not reported by this endpoint.
Uptime is relabeled Elapsed since start: the current scalar is wall time since the
recorded start, even for terminal records, not measured live uptime or completed duration.
Foreign-session wording likewise says recorded. Readiness names the registry check, and
transport panels describe registry state separately from persisted feed samples.
Contract fields remain compatible.
Start stays disabled; no operational gate advanced.

## Verification
- Canonical backend: python run_tests.py, 826/826 PASS, 161.360s, exit 0.
- V2 Python snapshot: 496/496 PASS, 79.600s, exit 0 (separate baseline).
- Frontend: 118/118 PASS, 27 files, 40.90s. After final readiness/transport copy edits,
  all 23 affected tests were rerun and passed; final typecheck and production build PASS.
- ESLint exit 0, no errors, one existing effect-ref warning; not a warning-free claim.
- Exact-SHA audit script: scripts/review-p1-14b8-v2-52.py.
- Reproductions: design/qa/v2-52/backend-reproductions.json, temp registries, simulated
  child and kernel32 only. Canonical registry hash unchanged:
  45c6a39ec91f55db708e1b9011f86bc55248b4485e582c015ea4442cc7cab5da.
- Browser verification: 6/6 System/Overview cases at 1672, 1366, 390; see results.json and PNGs.
  Runtime DTOs and expanded watcher evidence captured. Start disabled throughout.
  This slice does not revalidate the other eleven routes from V2-49.
- Matching System approved PNG inspected again. Shared terminal composition retained;
  original healthy metrics/sparklines are illustrative and not copied into live UI.
  Reference fidelity remains PARTIAL; correct Opportunities target remains missing.

## Owner follow-up - deterministic corrections only
Read this review and reproduction script/JSON from the final V2-52 commit.
Base backend 55efaa2b171c83701f6736ab6e6374869a733af1.
Correct H1 and H2 with failing-first hermetic tests; tighten C1 evidence wording or tests.
Preserve pure status API and existing contracts. Review necessary native helper callers.
Keep SQLite/logs/evidence, V2/main and SUCCESS_GATES untouched; no probes, P1-14C,
long runs, paper, Start enablement or trading. Supervised transactional launch remains
separate. Run the complete suite, update factual docs/backlog and selectively commit/push.
Report initial/final/remote SHAs, exact regressions, native refusal semantics, child-first
outcome and residuals. Use DONE bounded, not general PASS.

## Closeout
DECISIONS_REVIEWED: V2-50 watcher semantics, V2-51 pure observation, frontend boundaries.
NEW_DECISIONS_RECORDED: show canonical registry state as recorded, never OS-liveness proof.
FEATURES_IMPLEMENTED: recorded-state and elapsed-time wording; V2-52 QA mode.
FEATURES_VERIFIED: audited pure BFF integration, backend/frontend suites, browser checks.
DEFERRED_FEATURES: native-helper/start corrections owned by backend; supervised launch;
current target liveness evidence; longevity, complete visual parity and missing reference.
BACKLOG_UPDATED: F-V2-BFF-01 and F-V2-SYSTEM-01 remain PARTIAL with this checkpoint.
DOCUMENTATION_CONFLICTS: previous V2-51 missing-capability statement is historical;
backend native success and heartbeat-advance wording require qualification as above.
