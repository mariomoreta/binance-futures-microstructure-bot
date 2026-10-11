# DASH-V2-61 - backend correction handoff


> V2-62 superseding checkpoint: user-authorized direct backend correction is published at c635938. R1-R5/C1-C2 are resolved within disabled scope; this V2-61 file is historical base evidence, not a pending correction request. See [V2-62 acceptance](DASHBOARD_V2_62_BACKEND_CORRECTIONS_ACCEPTANCE.md).

Copy this complete prompt to the backend owner.

Work only in C:\proyectos\binance-futures-microstructure-bot, branch phase1/market-intelligence-dashboard.
Expected base: da231b911e9b1a0cfe86b3aaa3325e5b71928687.
Read the frontend published checkpoint containing docs/DASHBOARD_V2_61_SUPERVISED_LAUNCH_REVIEW.md, scripts/review-supervised-launch-v2-61.py and design/qa/v2-61/backend-reproductions.json with git fetch + git show/archive. Do not touch the V2 worktree. Accepted V2-55 R1/R2 remain closed.

Bounded task: correct the NEW disabled transactional launch implementation. No enabling, HTTP/CLI operation, Start, probes, traffic, P1-14C, long runs, paper, orders, SUCCESS_GATES or main changes.

Before changing code, reproduce and record failing-first safety regressions on this base:
1. R1: post-start foreign ACTIVE record is never adopted/confirmed/killed. Retain transaction child PID+creation-time captured at spawn, without borrowing later registry identity; clean only owned processes. Test foreign PID, reused PID with differing ctime, unreadable post-start and terminal/STOPPING transitions. Preserve foreign registry bytes. If a private helper or additive captured-identity result is needed, preserve public compatibility and existing accepted handoff semantics.
2. R2: failed second watcher identity check cannot result in verified/confirmed. Prefer a single evaluated lease result retaining age; otherwise propagate all failed rechecks.
3. R3: production internal supervisor role invokes canonical control supervise, sentinel invokes sentinel. Test actual default spawner command using mocked Popen/temp evidence only; no real watcher.
4. R4: finite verification budget, input validation before effects, sleep clamped to remaining time, deadline checked before confirmation after callbacks. Test interval > budget, exact/expired deadline, inf/nan/non-numeric/negative policy. Document scope of the time budget honestly; do not claim blocking spawn/OS operations have a hard deadline without evidence.
5. R5: final unreadable registry/identity-unverifiable state must yield uncertain with pending assessment. Proved dead differs from identity mismatch/unknown. Do not declare completed cleanup from inability to verify identity. Add cases for unreadable final assessment after simulated successful kills and for identity loss. Preserve kill-only rollback and zero registry writes during verification/rollback.

Reconcile C1 future tolerance with prior strict non-future supervision/display contract; no silent weakening. Reconcile C2 promised no-write locked preflight and actual evidence/precondition timing, with deterministic evidence. Update SUPERVISED_LAUNCH_CONTRACT before implementation if internal design clarification is necessary; do not relax ownership, uncertainty or established protection criteria to pass tests.

Run python run_tests.py, retain precise count/exit and failing-first evidence. Record initial/final/remote SHAs, source review checkpoint SHA, seven closeout fields and residual limitations. Selective commit/push only owned backend files. Preserve SQLite/logs/evidence/untracked assets. Return DONE acotado; do not claim general PASS, live validation, longevity or operational authorization. Frontend owner will review the exact returned SHA before any integration.
