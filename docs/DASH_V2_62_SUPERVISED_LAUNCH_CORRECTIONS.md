# DASH-V2-62 - supervised launch bounded corrections

Date: 2026-10-11. Base: da231b911e9b1a0cfe86b3aaa3325e5b71928687.
Owner: frontend reviewer, now explicitly authorized by the user to correct the backend branch directly.
Worktree: isolated detached checkout; original agent checkout and its untracked evidence preserved.
Review source: frontend f63dd162106b807c7d754da2834663d946000ccf (V2-61 report, script, JSON).
Scope: R1-R5 plus C1/C2 correction, DISABLED preparation only. V2-55 accepted BOOL/handoff fixes not reopened.

## Contract-first design and implementation

The V2-62 correction design was appended to SUPERVISED_LAUNCH_CONTRACT.md before changing control.py. No new HTTP route, CLI operation or enablement.

- R1: private optional _on_spawn callback transfers the actual Popen child PID and captured ctime from start_probe before registry commit/adoption/handoff. Ordinary callers/results keep their semantics. Transaction ownership is never obtained from a later registry read. Foreign, differing-ctime, STOPPING and terminal association reject before watcher spawn; only captured owned processes are rollback candidates.
- R2: each watcher lease is evaluated once, with its age retained. No ignored second identity result; known run identity is also checked in the production bundle.
- R3: default internal supervisor role maps to canonical supervise CLI; sentinel keeps sentinel. Default Popen is mocked in command tests, not launched.
- R4: finite positive budget and finite nonnegative cadence required, booleans/invalid/nonfinite values rejected before effects. The loop clamps sleeps to remaining time and checks deadline after reads and identity callbacks before confirming. Budget is verification-only after spawns, not a hard deadline on blocking IO/native calls.
- R5: rollback separates owned/gone/replaced/unknown; only owned with captured ctime may be terminated and only independently proved gone may count as cleaned. Windows identity/exit observation uses one full-width handle, exact BOOL signatures and finally-close. Missing ctime, access denied, replacement or unknown evidence stays pending. A pure final registry read is required; unreadable/malformed final assessment stays uncertain even when simulated cleanup succeeds. Single finish path avoids duplicate rollback.
- C1: strict non-future heartbeat age restored to [0, freshness bound]; no established supervision/display predicate weakened.
- C2: actual no-write sidecar lock probe and exclusive temporary evidence write-check run before spawn. Documentation now states the permitted filesystem preparation effects honestly; no registry record writes during verification/rollback.

Existing unreadable-verification test corrected to the published uncertainty contract. Successful fake child now supplies a known world-backed ctime; indeterminable identity has dedicated negative coverage. Both changes improve fixture/expectation correctness rather than relaxing protection.

## Verification

Baseline new regression file: 18 methods, 15 failing methods (25 assertion failures including timing subtests), exit 1 against unchanged da231b9 control.py. This proves the required new boundaries failed before correction.
Final focused suites: 52/52 OK, 2.543s (23 existing launch + 21 correction + 8 fake native identity), exit 0.
Canonical full suite: 902/902 OK (873 + 29 new), 160.768s, exit 0.
Evidence: docs/evidence/DASH_V2_62_LAUNCH_VERIFICATION.json.

Tests include owned/foreign association, ctime replacement, terminal/STOPPING, byte-preserving foreign registry, strict zero-write mocks, deadline expiry in read/identity callbacks, clamped wait, bad timing, lock/evidence refusal before spawn, uncertain unreadable final state, missing/replaced identity, happy path and default supervisor argv. Eight native mock cases cover exact identity, replacement, missing ctime, absent-PID error, access denied, exited handle, failed exit query and failed creation-time query.

No market probe, traffic, paper, orders, Start, operational authorization or new longevity window. Canonical suite retains its existing isolated worker-process concurrency tests; the added launch/native regressions perform no real Popen/termination. Visual verification NOT APPLICABLE. Canonical SQLite/logs/evidence and untracked files in the original checkout remain untouched; tests use temporary fixtures. No database/log/secret files are committed.

## Limits and next boundary

Public launch_supervised_transaction remains disabled with zero effects. No HTTP/CLI launch wiring, V2 control change, SUCCESS_GATES change, phase advance or main merge.
Production spawners remain dormant; real launch sequencing/leases/rollback and watcher startup association are not live-validated. Default watcher commands select the canonical registry when starting; transaction confirmation checks the captured association. Binding watcher startup itself to an expected transaction identity remains an enablement-review concern; no claim that dormant defaults are ready for operational use.
Windows absence/ctime proof is tested against mocked native APIs here, not a live kill certification. POSIX remains conservative with unknown creation time and retains its verified-kill race limitation. Existing nontransactional paths retain their documented ctime fallback / heartbeat ownership limitations.
Next: publish this bounded backend correction on phase1, then record exact-SHA V2 acceptance of corrected preparation. Enabling/runs remain separate explicit authorization tasks.

## Seven closeout fields

- DECISIONS_REVIEWED: V2-55 accepted fixes, V2-56 request, V2-61 findings and disabled launch contract.
- NEW_DECISIONS_RECORDED: spawn-owned identity and uncertainty proof required; strict future rejection; preflight filesystem effects and verification budget scope made explicit.
- FEATURES_IMPLEMENTED: F-LAUNCH-SUP-01 R1-R5/C1-C2 bounded correction, still PARTIAL/disabled.
- FEATURES_VERIFIED: 52 focused tests; 902/902 canonical tests, 160.768s, exit 0; failing-first and native mock evidence.
- DEFERRED_FEATURES: enablement, real watcher startup association, real launch/rollback, longevity, P1-14C and operational phases.
- BACKLOG_UPDATED: launch remains proposed for enablement and partial overall; corrected preparation/test evidence indexed.
- DOCUMENTATION_CONFLICTS: fresh read ownership, future tolerance, pure preflight effects, duplicate/ignored verification, finite budget and unreadable rejection claims corrected; historical decisions retained with this superseding factual entry.
