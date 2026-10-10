# DASH-V2-49 — all-screen visual audit and terminal composition

Date: 2026-10-10. V2 starting SHA f284bb58f2550914687c922f9a6a71925e37f5dc.
Branch dash-v2-03-token-detail. Scope: frontend, reference identity and documentation.
User authorized the complete bounded visual cycle without repeated confirmation.

## Outcome and verification

Audited 13 distinct views and eight actual PNG references. Completed shared
terminal header/sidebar, mobile menu, dense Overview composition, responsive
archive/lab layouts, unavailable-data screens, and Backtest/Paper Lab empty
workspaces. Token Detail now has six metrics on its desktop strip.
No backend code, market probe, portfolio, simulation or gate advancement.

Windows frontend: TypeScript, ESLint, 90/90 Vitest (25 files) and Next production
build PASS. Latest CSS-only iteration rebuilt successfully. V2 Python snapshot:
496/496 PASS in 89.456s; this is not the backend owner's evolving newer suite.

Chrome: 13 routes x 1672/1366/390 = 39 captures; every view has one h1, one main,
one active primary parent route, and scrollWidth <= viewport width. Mobile menu
opening and Escape verified. System disclosure captured. No unexpected browser
errors; 18 handled HTTP 503 responses from the stopped Python HTTP sources
(opportunities, live-movers and price-series) are recorded, not hidden or
misrepresented as working integration. Real SQLite sources remain readable.
Full-page desktop captures additionally inspect content below the first viewport.

During verification, reproduced and corrected:
- Missing Overview and Movers h1; six nested main landmarks.
- Missing primary active parent on research/symbol subroutes.
- Escape failed with focus outside the menu; global listener fixed and tested.
- Movers mobile page width 1028 at viewport 390.
- Prospective page width 1220 at 390, and 1412 at 1366.
  Corrected grid min-content tracks and contained ledger/table scrolling.
- Market Lab/archives had desktop-only grids and duplicated shell padding.
No clipping of document overflow is used to manufacture a layout PASS.

## Screen-by-screen result

All rows passed the three-width layout/navigation checks. Parity is deliberately
separate from operational availability and is not a pixel-perfect claim.

| View | Reference status | Visual result and material departure |
|---|---|---|
| Overview | overview.png verified | PARTIAL: six metrics, pulse/context columns, full-width snapshot and research panels; existing fixtures retained, no synthetic sparklines; actual runtime section adds height |
| Movers | movers.png / alternatives verified | PARTIAL: dense screener/rail preserved; common sidebar replaces this specific target's top navigation; wider tables scroll locally |
| Verified movers | no dedicated reference | Cohesive unavailable state, source/time fields, empty table and retry; owning HTTP source offline |
| Opportunities | approved target MISSING | ASSET_MISMATCH: coherent existing lifecycle/demo UI under shared shell; no unrelated image used as target |
| Saved observations | no dedicated reference | Cohesive unavailable state and empty ledger; provider offline, no records substituted |
| Prospective | no dedicated reference | Recorded ledger/recorder states preserved; mobile lifecycle cards stack; local table scrolling; source freshness limitations retained |
| Token Detail | corrected token-detail.png verified | PARTIAL: header, hero, state/evidence row, six metrics, price/history columns; no invented curves; price API offline |
| Historical Research | no dedicated reference | Four recorded metrics / two panels desktop, two metric columns mobile; contained tables; persisted evidence only |
| Market Archive | no dedicated reference | Shared page spacing and responsive metrics; stored values and capture time unchanged |
| Market Lab | no dedicated reference | Responsive recorded chart and comparison cards; gaps retained, no performance inference |
| System | system.png verified | PARTIAL: 4 actual state cards / 3 source-aware panels / recorded section; full target's six connected panels await contracts; Start disabled |
| Backtest | backtest.png verified | MATCHED MAJOR COMPOSITION, PARTIAL detail: configuration/readiness, 6 unavailable metrics, empty result/report panels; no sample experiments or results |
| Paper Lab | paper-lab.png verified | MATCHED MAJOR COMPOSITION, PARTIAL detail: 4 unavailable portfolio metrics, disabled scenario/journal, empty positions/performance; no fabricated account/fills |

## Reference correction

Renamed original opportunities.png -> token-detail.png, and original
token-detail.png -> movers-secondary.png. Compared SHA-256 to original HEAD
bytes: identical, no pixels changed. Original filenames remain in Git history
and ZIP. README and ASSET_AUDIT_STATUS now describe actual current mapping.
Correct Opportunities target remains missing from the uploaded package.

Common frame follows sidebar references (Overview/System/Token/future views).
Movers target uses a horizontal frame; the shared sidebar is an explicit
cross-screen coherence choice. Placeholder search, notifications/profile and
nonfunctional chart controls were omitted. Typography/iconography and panel
density are improved but not asserted identical to the artwork.

## Roadmap and next integration

DASHBOARD_V2_VISUAL_ROADMAP.md owns the route matrix, acceptance and sequence.
This execution completes its audit/shared-shell/screen-layout/validation/
documentation cycle for currently available sources. It does not close full
data or reference parity.

Pending external dependencies:
1. Correct approved Opportunities PNG.
2. Backend P1-14B.8 safety corrections at a reviewed committed SHA.
3. Authoritative, timestamped universe, recorder, classifier, host and events
   contracts; actual live HTTP source availability when separately authorized.
4. Canonical transactional launch of supervisor + sentinel with rollback.
5. Actual backtest/paper engines and validated results; still unavailable.

Next authorized frontend integration maps reviewed read-only contracts and
revalidates affected screens. No endless cosmetic loop or invented measurements.
Backend report received later is reviewed before any capability is enabled.

## Closeout

DECISIONS_REVIEWED: AGENTS, dashboard-v2 skill, workflow, design/reference
mapping, V2 architecture and source/data boundaries.
NEW_DECISIONS_RECORDED: shared sidebar supersedes DASH-V2-18 frame; explicit
reference identity correction; finished unavailable states without engines.
FEATURES_IMPLEMENTED: F-V2-VISUAL-01 bounded shell/responsive/empty compositions.
FEATURES_VERIFIED: 13 route layouts, navigation, menu recovery, 90 frontend tests;
F-V2-SYSTEM-01 and F-V2-BFF-01 remain PARTIAL in full capability terms.
DEFERRED_FEATURES: missing target and five external dependency groups above;
F-PAPER-01/backtest research remain NOT IMPLEMENTED.
BACKLOG_UPDATED: visual completion scope and remaining integration blockers.
DOCUMENTATION_CONFLICTS: stale static-foundation metadata fixed; prior filename
mismatch corrected; prior top-navigation/reference claims superseded explicitly.

Evidence: design/qa/v2-49/before, after/results.json, after/full-results.json,
contact sheets, individual captures and scripts/qa-dashboard-all.mjs.
