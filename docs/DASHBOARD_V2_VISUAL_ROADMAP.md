# Dashboard V2 — visual completion roadmap (DASH-V2-49)

## DASH-V2-70 / V2-69 — 2026-10-11 — extraction accepted and recorded diagnostics
Backend c59c5ec extraction accepted after direct proof/docs repair published 9f3e084192e90b52948c398f021f64b7884e2df2; independent 909/909, no reviewer application-source edit. See DASHBOARD_V2_69_EXTRACTION_ACCEPTANCE.md. V2 recorded diagnostics now avoid timestamp-based run association and display missing-stream, parse/payload-error and signed clock-offset fields. 192/192 frontend, type/lint/build pass; System 3 widths, disclosure/refresh and Overview check pass, zero overflow/browser errors; canonical DB/registry bytes unchanged. Production http://127.0.0.1:3020 managed PID23296. See DASHBOARD_V2_70_RECORDED_DIAGNOSTICS.md. Exact reference fidelity/full cutover remain PARTIAL. Next V2-71 source-backed pipeline/persistence/universe parity; host/events require separate contracts. Old HTML, Start, gates, main and runtime operations preserved.


## Active visual control plan - 2026-10-11, DASH-V2-57

Owner: V2 frontend agent. This document is the single control plan for autonomous
visual rounds, separate from backend engineering and project operational gates.
User authorized phase-by-phase visual work and self-verification without repeated
approval. This supersedes the earlier stop-after-one-cycle sequencing below:
continue through ready visual rounds within the active work cycle; stop when the
planned visual cycle is complete or a real blocking condition cannot be isolated.
This is not a background job or a live-run authorization.

### Current state and next rounds

| Round | Scope | Status | Evidence / dependency |
|---|---|---|---|
| V56 | Overview and Movers hierarchy/composition | ROUND DONE; overall parity PARTIAL | DASHBOARD_V2_56_VISUAL_REFINEMENT.md; 39 before/after cases; 118 frontend / 496 snapshot |
| V57 | Autonomous visual control plan | ROUND DONE, documentation only | This dated control section |
| V58 / A | Token Detail | ROUND DONE; fidelity PARTIAL | DASHBOARD_V2_58_TOKEN_DETAIL_VISUAL.md; 3 before / 6 after browser cases, 118 frontend / 496 snapshot |
| V59 / B | Opportunities, observations, prospective | ROUND DONE; exact fidelity ASSET_MISMATCH | DASHBOARD_V2_59_RESEARCH_VISUAL.md; missing dedicated reference isolated |
| V60 / C | System and research archives | ROUND DONE; PARTIAL / NO DEDICATED REFERENCE | DASHBOARD_V2_60_CONSISTENCY_REVIEW.md; labels and record-table keyboard access retained |
| V60 / D | Backtest and Paper Lab unavailable states | ROUND DONE; fidelity PARTIAL | Neutral icons/hierarchy refined; engines/results unavailable, controls disabled |
| V60 / Final | Whole-dashboard desktop/mobile consistency | BOUNDED CYCLE DONE; exact fidelity remains PARTIAL | 39 browser cases; four mobile keyboard checks; screen-by-screen gaps in V60 report |

Read latest progress/backlog before selecting each round. Do not repeat verified
work just because an old historical section says it is pending. Backend report
review is an interrupting integration task at exact SHA, not permission to change
backend ownership or broaden visual work into strategy/control implementation.

### Entry and exit criteria for every round

1. Inspect the actual matching reference and current source. Record absent or
   misidentified assets. Capture BEFORE at 1672/1366/390 or a justified scoped
   viewport set. State the exact visual problem and the available data contract.
2. Define bounded layout/hierarchy/spacing/typography/table/responsive changes;
   retain routes, accessibility, source labels, timestamps, units and nullability.
   Never manufacture charts, history, market states, signals, probabilities,
   validated performance or functioning controls to imitate a reference.
3. Implement only in the owned V2 tree. Changes to shared components trigger
   checks on all affected screens. No canonical engine/DB/log/Start mutation.
4. Run relevant existing tests and required regression checks; type/build for
   frontend changes. Update existing tests only when intended behavior changes.
   No unnecessary mirrored tests for trivial CSS. Tests do not replace visuals.
5. Inspect fresh AFTER images against BEFORE and reference. Verify desktop/mobile
   alignment, hierarchy, readable labels, contrast, focus/navigation, table
   scrolling and absence of document overflow/browser errors. Record deliberate
   departures and unavailable capabilities, not just a screenshot filename.
6. Close ROUND DONE only when the bounded acceptance passes and regressions are
   resolved. Separately report screen fidelity as MATCHED COMPOSITION / PARTIAL /
   ASSET_MISMATCH / NO DEDICATED REFERENCE. ROUND DONE never means full reference
   parity, live data readiness, profitability or SUCCESS_GATES advancement.
7. Update progress, relevant decisions/backlog and this control matrix. Selective
   commit/push; managed V2 restart only when needed with verified process ownership.
   Give the user a concise outcome, dashboard route, checks, remaining gaps and
   next round. User preview is invited, not required as repeated approval.
8. Continue directly to the next READY round during the active cycle. On an
   isolated asset/API dependency, mark only that requirement BLOCKED and continue
   independent visual work. Stop on user instruction, unresolved regression,
   conflicting ownership, or changes outside authorized frontend scope.

### Stop and finish conditions

Finish after the planned round set and final consistency check are published.
Report screen-by-screen fidelity and precise external dependencies; do not mark
everything PASS because tests/build succeeded. A backend/API/ref dependency is
recorded for later integration when its evidence arrives, without fictitious data
or a new permission flow for ordinary reversible UI changes.
No live probes, backfills, long runs, paper, orders or Start enablement authorized.

### User feedback format

- What changed and why it improves the reference composition.
- Direct link to the updated dashboard route.
- Checks and visual verdict; unresolved dependency if any.
- Next round already selected and its acceptance target.

The user's design preference or correction steers the active round. This control
plan remains in Git, not a private agent-only file that can drift from the project.

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


## DASH-V2-53 future dependency — 2026-10-11

F-V2-RESEARCH-01 proposes truthful level/evidence/context detail within existing research screens after canonical data contracts exist. Documentation capture is DONE; visual implementation and verification of this proposal are NOT IMPLEMENTED. Do not add synthetic trade-plan fields or probabilities to make the interface appear complete. See [MOVER_LEVEL_STRATEGY_RESEARCH.md](MOVER_LEVEL_STRATEGY_RESEARCH.md) and FEATURE_BACKLOG.md. Current dashboard corrections and backend integration retain their established sequence; Start remains disabled.


## DASH-V2-56 - 2026-10-11 - Overview/Movers layout checkpoint
Full-width Movers table replaces the older desktop ranking side rail; rankings below in four columns. Default eight rows with 16/32 choices. Overview pulse tiles reduce vertical height, title and action hierarchy improved. All 13 routes checked before/after at 1672/1366/390: 39 cases each, no page overflow/browser errors. Overall parity remains PARTIAL; missing Opportunities reference unchanged. Next visual slice: Token Detail/Opportunities evidence composition under existing contracts. See DASHBOARD_V2_56_VISUAL_REFINEMENT.md. Current source content still governs unavailable/demo/live labels.

## DASH-V2-67 - 2026-10-11 - exact backend contract reconciliation
Backend 5dedacb local/origin verified; documentation+3 tests only since c635938. Focused3 and canonical905 independently pass. Five V2 GET checks and unchanged registry bytes recorded. Separate historical DB schema2 has14 coverage rows/2831 event instances; existing historical-research endpoint is prospective archive, not bar/study parity. No automatic SHA guard in runtime bridge; manual verification clarified. Search/window/Unicode residuals explicit. See DASHBOARD_V2_67_CONTRACT_RECONCILIATION.md and backend handoff. Next frontend V2-68: readonly coverage/studies presentation; backend owner: shared-helper extraction, no retirement. Full cutover/BFF remains PARTIAL; Start/gates unchanged. Nonvisual review only.

## DASH-V2-68 - 2026-10-11 - historical coverage and studies
Separate readonly historical.db adapter/API and coverage/study view implemented at /historical-research/coverage; archive naming/navigation and token links clarify provenance.183/183 frontend,496/496 V2 Python, types/lint/build,8 HTTP cases with native aggregation/hash parity and57 browser cases pass. Exact visual fidelity NO DEDICATED REFERENCE/PARTIAL. See DASHBOARD_V2_68_HISTORICAL_COVERAGE.md. Backend worktree has other agent's uncommitted helper-extraction changes; no new backend acceptance inferred. Full cutover/BFF remains PARTIAL. Next V2-69 diagnostic parity audit; backend exact-SHA review when report arrives. Start/old fallback/gates preserved.
