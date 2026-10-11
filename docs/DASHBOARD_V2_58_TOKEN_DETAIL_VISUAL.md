# DASH-V2-58 - Token Detail visual round

Base: f61d189d597a621aaffe4fff1c5f9860f6aa18a1. Date: 2026-10-11.

## Audit and bounded plan

Actual token-detail.png inspected after the corrected reference README. Current UI and fresh BEFORE captures at 1672/1366/390 reviewed: status is detached from categories, panels are tall, lower content lacks the reference's compact grouping.

Plan: combine categories with observed-state/direction/rules summary; compact evidence and six-metric desktop strip; use decorative SVG section icons; improve mobile hero and metric grids. Preserve fixture provenance, source-specific chart, unknown classifier/audit, route behavior and data contracts. Rollback boundary: two TokenDetail presentation files, no backend or API changes.

Verification pending. Do not interpret this planning record as acceptance.

## Result and visual verification

ROUND DONE; screen fidelity PARTIAL, not pixel-perfect. Preserved frame/provenance and larger source-specific chart cause deliberate differences from the mockup. No decorative price sparklines or invented history; no category falsely active while state is UNKNOWN.

Inspected fresh desktop 1672 screenshot and complete mobile 390 image against the actual reference and BEFORE. Categories and status now share a desktop row; four evidence cards and six metrics form compact strips, with neutral SVG icons. Mobile hero uses two price/change columns and full-width coverage; evidence stacks and metrics use two columns. Desktop total height 1300 -> 1267px; mobile 2863 -> 2316px. No layout completion claim for the shared shell.

Checks: frontend 118/118 (18.37s); typecheck/build exit 0; lint zero errors and one pre-existing BotControl cleanup-ref warning. Python snapshot 496/496 (87.816s), exit 0. Fresh browser: 3 BEFORE cases; 6 AFTER cases including BTC and unknown ORCA, widths 1672/1366/390; no runtime exceptions or document overflow; one main and one active navigation entry. Six expected price-series 503 responses remain separately recorded as source unavailability. Initial QA classified the newly tested ORCA 503 as unexpected; the explicit expected-endpoint list was corrected and the full scoped check rerun successfully. No application exception was hidden.

Fixtures retain historical timestamp and NOT LIVE label. ORCA retains NO SYMBOL FIXTURE, null fields and UNKNOWN classifier. Production updated after checking old Node PID 18520, creation time and owned listener. Route: http://127.0.0.1:3020/symbol/BTCUSDT.

## Closeout

- DECISIONS_REVIEWED: reference identity, V57 round acceptance, source/fixture separation.
- NEW_DECISIONS_RECORDED: neutral category treatment while UNKNOWN; no ornamental charts without verified series.
- FEATURES_IMPLEMENTED: bounded Token Detail layout/icons/responsive refinement; scoped capture configuration.
- FEATURES_VERIFIED: tests/build and actual desktop/mobile comparison described above; no live contract completion.
- DEFERRED_FEATURES: classifier/history and full shell parity; existing research proposals unchanged.
- BACKLOG_UPDATED: Token Detail bounded round DONE, fidelity PARTIAL; next Opportunities composition READY.
- DOCUMENTATION_CONFLICTS: next-A implementation PENDING superseded by this dated result; existing historical sections preserved.

Next ready round: Opportunities navigation and research-layout hierarchy. Its exact parity remains ASSET_MISMATCH because the matching reference is absent. Backend task remains separate; no probe, Start, execution or gate advancement.
