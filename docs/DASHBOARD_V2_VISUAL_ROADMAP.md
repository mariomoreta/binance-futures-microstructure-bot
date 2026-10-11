# Dashboard V2 — visual completion roadmap (DASH-V2-49)

Authorized 2026-10-10: audit all routes/references, then proceed phase by phase
without repeated approval. Backend owner remains separate. No market run or
execution authorization inferred.

## Reference identity and screen matrix

| Screen / route | Reference | Current source / boundary |
|---|---|---|
| Overview /overview | overview.png | labeled demo panels + real runtime diagnostics |
| Movers /movers | movers.png; alternative secondary | demo ranking + verified history links |
| Verified movers /movers/verified | no dedicated reference; Movers system | persisted read-only records |
| Opportunities /opportunities | correct asset absent; ASSET_MISMATCH | labeled demo lifecycle UI |
| Observations /opportunities/observations | no dedicated reference | persisted observations |
| Prospective /opportunities/prospective | no dedicated reference | persisted prospective outcomes |
| Token /symbol/BTCUSDT | token-detail.png (verified filename corrected) | mixed clearly labeled fixture and verified price series |
| Evidence /historical-research | no dedicated reference | persisted SQLite |
| Market Archive /market-archive | no dedicated reference | persisted SQLite |
| Market Lab /market-lab | no dedicated reference | recorded price research |
| System /system | system.png | current control + recorded evidence; start blocked |
| Backtest /backtest | backtest.png | unavailable engine; empty composition only |
| Paper Lab /paper-lab | paper-lab.png | unavailable engine; empty composition only |

All eight PNG contents inspected via actual contact sheet and relevant full-size
references. Original token-detail.png was another Movers design; it is now
movers-secondary.png. Original opportunities.png is now token-detail.png.
SHA-256 proves both pixel contents unchanged; Git history preserves originals.
Missing Opportunities target prevents a parity PASS, not useful frontend work.

## Bounded execution sequence

1. AUDIT: capture all 13 routes desktop 1672x941 and mobile 390x941, inspect
   reference content, source boundaries, broken navigation/overflow/errors.
2. Shared shell: reference-style desktop sidebar and compact header; accessible
   mobile menu, stable page widths, active descendants, no fictitious search/
   notification controls. Preserve URLs and component data contracts.
3. Screen composition: Overview dense metric/panel layout; cohesive archives
   and responsive grids; Backtest/Paper Lab reference-like unavailable panels.
   Tune remaining existing terminal screens only where captured evidence
   identifies defects. Never populate absent graphs with invented data.
4. VERIFY: all routes desktop/mobile captures, keyboard/menu/navigation, no
   page overflow, usable table scrolling, frontend suite/type/lint/build.
   Run V2 Python regression snapshot separately from changing backend branch.
5. DOCUMENT/CHECKPOINT: actual per-screen verdict, gaps, seven closeout fields,
   selective V2 commit/push, managed V2 restart only with PID identity verified.

## Acceptance and continuing integration

Use MATCHED COMPOSITION / PARTIAL / ASSET_MISMATCH / NO DEDICATED REFERENCE,
never equate build success with design fidelity. Record all deliberate
departures: real contracts override illustrative charts and metrics. Where
data are unavailable provide finished empty/loading/error states.

Backend reports are reviewed at exact SHA before mapping fields. Supervisor/
sentinel safety defects and transactional launch remain blocking Start, but
not sidebar, spacing or read-only visual composition. Do not cherry-pick
backend work into V2 without a reviewed integration need.

Stop this frontend cycle after all route checks and documented bounded changes
are published; list external dependencies precisely. Resume their integration
when the user supplies the owning report. Rollback: revert the V2 visual commits.


## 2026-10-11 - Integration checkpoint DASH-V2-50
Reviewed backend corrections at 8648366. Watcher read-only contracts integrated
in V2 with sentinel/raw lease evidence and 90s observation expiry.
System remains visually PARTIAL. Safety review remains CHANGES REQUIRED:
enforce_abort pre-termination ownership/locking, genuine heartbeat race tests.
Next: owner follow-up in DASHBOARD_V2_50_CORRECTIONS_REVIEW.md, then review exact
new SHA before transactional launch integration. No market run authorized here.


## 2026-10-11 - DASH-V2-51 follow-up checkpoint
Backend 0786617 reviewed. Pre-claim and final-mark fixes accepted; operation
boundary, run-associated lease, pure status and process-owner race coverage
remain pending. V2 now pauses runtime observation until status_readonly exists;
historical evidence remains visible. Next owner task is specified in
DASHBOARD_V2_51_FENCING_REVIEW.md. Start and launch gates remain blocked.


## 2026-10-11 - DASH-V2-52 pure observation and native boundary review
Backend exact SHA 55efaa2 reviewed; canonical suite independently 826/826 PASS.
V2 bridge status_readonly verified byte-preserving; runtime observation resumes.
Recorded COMPLETED / watcher STALE / feed UNKNOWN are independent observations.
Registry state is not verified target liveness: V2 labels it Recorded process,
uses Elapsed since start, and describes readiness as a registry check.
Two remaining reproductions: native TerminateProcess FALSE accepted as True,
missing native HANDLE signatures; start kills its own child if registration wins
before parent commit. Both are hermetic, without probes or actual OS termination.
Native/start corrections remain owned by backend; full detail and follow-up in
DASHBOARD_V2_52_INTEGRATION_REVIEW.md. Start and operational gates remain blocked.
Frontend 118/118, V2 Python snapshot 496/496; type/build PASS. System/Overview at
1672/1366/390: 6 cases, no browser errors/page overflow. Visual parity PARTIAL.
F-V2-BFF-01 and F-V2-SYSTEM-01 remain PARTIAL. No new supervised run or gate advance.
