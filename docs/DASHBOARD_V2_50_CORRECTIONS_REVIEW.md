# DASH-V2-50 - Corrections review and read-only watcher integration

Backend under review: 8648366ec5ea82a46e4573cf81a53546f666d8d6.
Frontend baseline: e201dfa607e462cda87a781737da4c8c5c45c6bc.

## Bounded plan (2026-10-11)
1. Audit exact backend diff and run contract/sentinel tests.
2. Reproduce ownership and concurrent-write paths in temporary registries with
   termination mocked. Never edit backend source or touch the canonical registry.
3. Normalize and preserve both watcher blocks through the V2 BFF; expose raw
   lease evidence in System. ACTIVE is a controller observation, not a guarantee.
4. Expire ACTIVE in the browser when heartbeat/observation exceeds 90 seconds;
   reject future/malformed timestamps and mismatched run associations.
5. Keep Start blocked; preserve process/feed/watchers as separate states.
6. Run frontend checks, V2 Python snapshot suite, production read-only API checks
   and fresh desktop/mobile System captures against system.png.
7. Publish audit, owner follow-up and scoped frontend changes.

Acceptance: sentinel survives BFF, null/zero/raw state preserved, no stale cached
ACTIVE, no runtime mutations, no page overflow, all applicable tests pass.
Rollback: frontend-only Git revert; backend branch remains untouched.
Operational launch/long-run success gates are not advanced by this slice.

## Independent backend audit

Verdict: PARTIAL / CHANGES REQUIRED for enforcement ownership. Read-only display
predicate fixes accepted; no operational gate advancement or new market run.

Exact backend commit verified locally and by git ls-remote:
8648366ec5ea82a46e4573cf81a53546f666d8d6. Diff from babf3ac: 9 files,
907 additions / 151 deletions. Main remains d6801a5855bdac9d6620c69363b298b6881da5f7.
The backend tree's existing untracked files were preserved; no backend source edit.

34/34 existing contract+sentinel tests rerun, exit 0. The owner's 794/794 full
backend result is reported evidence, not an independently rerun full suite here.
V2's separate Python snapshot suite rerun: 496/496, exit 0, 78.142 seconds.

### Accepted corrections
- STOPPED, FAILED, dead, mismatched, malformed/future/old heartbeat cannot
  become ok-supervised. watcher_alive is now required.
- Both display blocks use ACTIVE/fresh/alive/associated checks and publish
  raw lease identity/heartbeat evidence.
- Locked heartbeat transforms and ownership no-ops exist; a positive replay
  with owned leases performed 4 threads x25 heartbeat calls and retained both watcher
  failure values (11/22), advancing both heartbeats and preserving the run.
- Historical report fixes distinguish 57/202 from 66/228, 68 summaries+final,
  runtime 2102.147, and brief three-layer vs long supervisor-only evidence.

### HIGH - enforce_abort does not fence before termination
control.py:1074-1091 reads a snapshot, checks process identity, then writes
STOPPING with _write_registry (no update_registry lock) and calls termination.
owner_kind is only checked later during terminal marking.
A replaced watcher therefore still reaches the termination call. Checking
ownership after a kill cannot protect that operation.

Deterministic synthetic-registry results (all termination calls mocked):
1. Foreign supervisor owner: terminate_called=true; returned superseded;
   registry left STOPPING despite the caller not owning the lease.
2. COMPLETED + new-owner takeover inserted between read and STOPPING:
   old snapshot overwrites both; terminate_called=true, returned aborted=true,
   final ABORTED with the old owner restored.
3. STOPPING write OSError: terminate_called=true; returned superseded.
   The failed marker does not prevent the irreversible operation.

The reported stop/try_register residual does not cover this: the unsafe
write is inside enforce_abort, which is in the correction's mandated scope.
The terminal-mark transform also checks only STOPPING marker/owner, not the
original run PID+creation-time; the timeout branch omits its own marker check.
Atomic rename prevents torn reads; it does not prevent this lost-update race.

### HIGH evidence gap - concurrent-heartbeat test performs no writes
test_supervision_contract.py:test_concurrent_heartbeats_keep_both_fields seeds
watcher PIDs 424244 and 424245, while _owns_lease compares against os.getpid().
Both heartbeat functions silently no-op. Replaying the fixture returned a
byte-equivalent record. The assertions check only that pre-existing fields
remain, not that a heartbeat advanced or that all threads exited.
The positive owned-lease replay above supports locked transforms, but does
not repair the committed regression test or validate two process owners.

### Lower-priority cleanup and correspondence
- update_registry parses identical JSON twice; _supervisor_lease_verified has
  unreachable duplicate abort-field code referencing block. Remove as cleanup;
  the real _supervisor_block still correctly emits its abort fields.
- aborted_by is hardcoded supervisor even for owner_kind=sentinel. It must
  identify the actual enforcer; abort_at/by are not exposed in the status blocks.
- The submitted report calls a healthy >=30-min window undemonstrated while
  its Git document says historically demonstrated twice. Distinguish historical
  evidence from the corrected SHA, on which no new window was run.
- No claim is made that stricter predicates resolve the original watcher's
  unexplained death or demonstrate uninterrupted long three-layer protection.

Evidence: scripts/review-p1-14b8-corrections.py and
design/qa/v2-50/backend-reproductions.json. The script redirects all writes to
a TemporaryDirectory and patches termination/OS-liveness for enforcement cases.
It must be run with PYTHONPATH pointing to the audited backend src and tests.

## Owner follow-up (bounded, no market runs)

Complete before transactional V2 launch work:
1. Put the STOPPING transition under update_registry; recheck original run
   identity, eligible state, owner lease and marker. Refuse replaced owners
   before termination. Do not call termination if writing/claiming fails.
2. Fence the termination boundary and terminal/timeout updates against takeover,
   run replacement and foreign terminal state. Persist actual aborting owner.
   Address the check-to-kill race explicitly; post-kill validation is insufficient.
3. Add failing-first tests for all three reproductions; termination mock must
   remain uncalled on refusal. Test run PID/ctime replacement and timeout-marker
   mismatch, plus supervisor and sentinel owners.
4. Replace the no-op heartbeat test with genuine owners/writes; assert each
   heartbeat advanced, distinctive updates survive, no silent failures,
   all workers exit, and exactly one winner among independent claimants.
5. Remove duplicate/unreachable fragments, clarify report window scope, rerun
   the full backend suite and publish exact SHA + evidence. Preserve DB/logs.
6. Do not launch P1-14C, 35-min, long runs or paper trading in this task.

V2 launch remains separately PENDING: canonical transaction must launch probe
and both watchers, verify their leases/identities/association and roll back
every launched process on failure before V2 can enable Start.

## V2 implementation and verification
- Normalized both watcher blocks in BFF; explicit nulls/false/zero/text retained.
- Added BFF observed_at UTC; it is not a market/feed timestamp.
- System shows process/feed/supervisor/sentinel/mode independently; raw lease
  state, watcher PID/ctime, watched PID, run, heartbeat and action remain inspectable.
- ACTIVE display requires current canonical ACTIVE + raw ACTIVE lease + this run
  association + identity evidence + valid heartbeat/observation in [0,90s].
  Browser expiry runs every second. Unknown/missing evidence is never protection.
  Failed fetch clears earlier evidence; sequence guard prevents old replies replacing
  newer observations. Receipt clock is updated before evaluating new evidence.
- Start still disabled, backend launch route untouched. Stop ownership guard unchanged.
- Frontend final 116/116 tests (27 files), typecheck/lint/production build PASS.
  Includes null/zero, both watcher BFF blocks, malformed/future/expired evidence,
  cached ACTIVE expiry without a new response and clearing after fetch failure.
- V2 Python snapshot 496/496 PASS. This is not the backend owner's 794-test suite.
- Chrome System/Overview at 1672/1366/390: 6 cases PASS, no unexpected errors or
  whole-page overflow, one main/h1/active parent. Expanded watcher evidence captured
  at all three widths. Read-only production DTOs preserve both watcher blocks.
- system.png inspected against fresh desktop/mobile and expanded captures.
  Common sidebar, five-card row, dense health panels retained. Deliberate departures:
  actual process/feed/watchers replace illustrative healthy/resource counters;
  unsupported graphs/pipeline/events absent or explicitly NOT CONNECTED; watcher
  inspection is a disclosure. Full reference fidelity remains PARTIAL.
- Actual source: process COMPLETED, both raw leases STOPPED, both display states
  STALE, feed UNKNOWN. Historical 66/228 evidence remains separate from runtime.
- Canonical uptime_seconds continues elapsed-since-start after COMPLETED; it is
  not final run duration. The archive reports captured runtime separately. Backend
  contract clarification remains pending; no runtime performance claim is made.

## Seven-field closeout
DECISIONS_REVIEWED: V2 common-frame and bounded-System records;
API contracts, backlog, WORKFLOW, prior P1-14B.8 review, backend corrections log.
NEW_DECISIONS_RECORDED: DASHBOARD_V2_DECISIONS - observation-only watcher display,
raw evidence separation, 90s expiry, Start remains blocked.
FEATURES_IMPLEMENTED: bounded watcher read-only portion of F-V2-BFF-01 and
F-V2-SYSTEM-01; both complete features remain PARTIAL.
FEATURES_VERIFIED: watcher BFF/presentation via 26 additional regressions,
116/116 full frontend suite and fresh read-only Chrome/API evidence.
DEFERRED_FEATURES: transactional supervised Start, full F-V2-BFF-01/System
contracts, backtest/paper engines, uninterrupted three-layer long-run validation.
BACKLOG_UPDATED: yes; current partial states and remaining enforcement blocker.
DOCUMENTATION_CONFLICTS: heartbeat concurrency proof is a no-op as committed;
enforce_abort fencing claim contradicts reproduced pre-kill path; historical
healthy-window scope clarified. Old review findings superseded only where verified.

NEXT: backend owner follow-up above. Review the resulting exact SHA before
operational integration. No new market runs or long-run authorization granted.
