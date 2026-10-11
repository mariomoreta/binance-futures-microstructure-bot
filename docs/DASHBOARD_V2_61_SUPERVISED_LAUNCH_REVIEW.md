# DASH-V2-61 - disabled supervised launch exact-SHA review

Date: 2026-10-11. Frontend base: 64c9b3915c48c5449abdea32613977af2acd2145.
Backend reviewed: da231b911e9b1a0cfe86b3aaa3325e5b71928687, from Git archive.
Verdict: CHANGES REQUIRED for the dormant implementation. Public disabled guard verified.
This is neither operational acceptance nor authorization. Accepted V2-55 R1/R2 stay closed.

## Audit and bounded plan

Read the published control implementation, 23 added tests and SUPERVISED_LAUNCH_CONTRACT.md, then compare them against the V2-56 handoff and existing BFF boundary. Reproduce disagreements with injected process identities, fake time, fake Popen and zero registry writes. Run both canonical suites independently. Publish review/handoff; do not import backend code or modify the other worktree. Visual verification NOT APPLICABLE: no frontend/runtime changes; production remains V2-60.

## Findings reproduced

| ID | Severity | Evidence | Required correction |
| --- | --- | --- | --- |
| R1 | Critical, dormant | start_probe returns own PID 100, but the next registry read contains foreign PID 999. Engine adopts 999, spawns watchers against it and can confirm it. A spawn failure invokes fake termination on 999 while own 100 survives. | Carry spawn-captured child PID+ctime into the transaction; never derive ownership from a later registry read. Reject differing association, roll back only owned identities and preserve foreign/terminal records. |
| R2 | High | _verify_launch_state checks both leases twice. First identity checks succeed; second checks fail. Their false results are ignored and the function returns verified with null ages. | Use one verified result per watcher, retaining age, or honor every subsequent failure. Never confirm after explicitly failed revalidation. |
| R3 | High | Default spawner produces module argument supervisor; argparse defines supervise, not supervisor. Test substitutes mask the real command construction. | Map internal role to canonical CLI command; test actual production argv with Popen mocked. No real watcher launch required. |
| R4 | High | Fake clock: budget 0.1s / interval 10s sleeps 10s, then confirms at t=10 before checking expiry. Infinity accepted after spawning. | Validate finite numeric inputs before effects; bound sleeps by remaining time; reject late confirmation. Define budget scope and avoid claiming a global bounded launch if spawn/reads can block. |
| R5 | High, contract discrepancy | Every verification read raises OSError. Simulated owned processes are terminated, but result is rejected with verify-unreadable. There is no readable final assessment; contract sections 6/7 require uncertain when final state cannot be assessed. | Preserve uncertainty/pending assessment when final registry is unreadable; distinguish identity mismatch/unknown from proved absence. Align tests with the published contract rather than weakening its promise. |

No actual foreign process was terminated: all PID examples and terminations above are injected mocks. R1 demonstrates wrong ownership selection, not OS termination success. R2 is an ignored explicit verifier result, not a claim that OS liveness can be atomically certified forever. R3 validates command construction/parser source, not actual dormant process execution. R4 uses fake time, not a ten-second real sleep. R5 tests missing final assessment, not incomplete simulated kills.

C1: new internal contract/helper accepts heartbeats up to 5 seconds in the future; prior reviewed freshness semantics reject future timestamps. Reconcile explicitly without silently weakening established display/enforcement semantics. This is not a reopening of accepted BOOL/handoff fixes.

C2: contract sequence says P1-P4 precede all effects, but implementation preflight does not perform the promised no-write lock probe. Clarify and deterministically test prerequisite timing; evidence creation handled by start_probe must not be described as an already verified pure preflight check.

## Evidence and verification

Reproduction script: scripts/review-supervised-launch-v2-61.py.
Results: design/qa/v2-61/backend-reproductions.json.
Nine recorded cases: disabled guard; two foreign identity cases; ignored second check; default argv; late confirmation; nonfinite budget; unreadable assessment; future tolerance.
The script intentionally asserts the current defects to preserve reproductions; exit 0 means reproduced, not accepted. It must run against the exact archived source checksum.

Backend canonical suite: 873/873 OK, 170.494s, exit 0, isolated exact-SHA archive.
V2 snapshot canonical suite: 496/496 OK, 83.491s, exit 0.
No frontend code changed; no frontend rebuild or new screenshot parity claim. No probes, market traffic, orders, Start, gate advancement, backend edits or main merge.

## Integration decision and next task

Keep Start disabled and the existing pure status GET boundary. Do not cherry-pick the dormant implementation into V2. Next: backend owner corrects R1-R5 and reconciles C1/C2 in the same disabled preparation scope, with failing-first tests on da231b9 and exact-SHA return. See DASHBOARD_V2_61_BACKEND_HANDOFF.md. Visual V58-V60 checkpoints remain unchanged; source/assets/engines and exact parity remain partial.

## Seven closeout fields

- DECISIONS_REVIEWED: V2-55 accepted R1/R2, V2-56 handoff, disabled launch contract and V2-60 checkpoint.
- NEW_DECISIONS_RECORDED: withhold dormant launch acceptance on reproduced new discrepancies; keep public/Start disabled.
- FEATURES_IMPLEMENTED: V2-owned review script, evidence, report and bounded correction handoff only.
- FEATURES_VERIFIED: nine deterministic cases; backend 873/873 and V2 snapshot 496/496 OK, exit 0; those suites do not cover all reproduced disagreements. Public disabled path verified.
- DEFERRED_FEATURES: enabled launch, real spawners, longevity, operational gates, missing reference assets and remaining parity.
- BACKLOG_UPDATED: F-LAUNCH-SUP-01 preparation reported but not accepted; F-P14A-01 evidence remains bounded/historical.
- DOCUMENTATION_CONFLICTS: ownership selection vs spawn contract; ignored revalidation; wrong default command; finite budget vs late confirmation; rejected vs unreadable uncertainty; future tolerance and claimed preflight timing explicitly flagged.
