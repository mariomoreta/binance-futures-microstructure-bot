# DASH-V2-64 - legacy coverage and cutover assessment
Date: 2026-10-11. Scope: read-only audit and next-work definition. No UI/backend/control/DB changes.

## Verdict
V2-63 canonical persisted presentation is implemented; complete old-interface replacement is NOT accepted. A successful page read or refreshing read timestamp is not collector/feed health. Old SSR remains recoverable; its Python modules and controller must not be deleted as part of visual migration.
Frontend audited: 328d4066cab1a66c2f1f8f082df7c86ee60e19de, dash-v2-03-token-detail. Backend published accepted bounded checkpoint: c635938fc5542be992e06838a8727652225e1657. Actual original backend checkout: da231b911e9b1a0cfe86b3aaa3325e5b71928687. V2 runtime-control.ts imports from that original checkout; do not equate remote acceptance with deployed code.

## Current direct checks
Ten GETs returned 200: overview, movers, opportunities, LUMIA detail, system, market-snapshot, opportunities API, prospective API, runtime API and BTC price API. Snapshot: available true, 29 retained symbols, 439 eligible scan contracts, 66 setups, 228 outcomes, 3042 saved price buckets. Discovery remains 2026-10-10T14:02:11.080Z.
Runtime GET: running false, registry state COMPLETED, launcher agent, feed_health UNKNOWN; supervisor and sentinel STOPPED leases projected STALE. This is read-only registry evidence, not independently verified OS liveness or failed active-run supervision. No operational Start/Stop was invoked.
Last V2-63 functional evidence: frontend 146/146, V2 Python snapshot 496/496, types/lint/build passed. These are prior checkpoint results, not newly rerun suites. No source implementation change warrants repeating those suites for this documentation audit.
Fresh browser re-audit: 13 routes x 3 widths = 39 cases, exit 0, 89.28s; zero browser errors, page overflows or unavailable-source responses. Results are recorded under design/qa/v2-64/after/full-results.json. This existing script checks route/layout/browser behavior; V2-63-specific rendered-demo/source assertions are in its v2-63 branch, not automatically exercised by this differently named round. Do not claim exhaustive semantic verification from screenshots.

## Source-reviewed old vs new coverage
Old source inspected: src/microstructure_probe/dashboard.py routing and dashboard_views.py render_symbol; dashboard_data.py function inventory. New route inventory, canonical persisted normalization, historical read projection and runtime bridge inspected. Runtime old HTTP server was not started for this audit.

| Function | V2 status | Remaining / owner |
|---|---|---|
| Overview discovery, Movers, saved candidates | Implemented bounded persisted views | Validate sorted/filtered subset against same DB snapshot; frontend |
| Search | Main tables have local filters | Old /search and /api/search search universe; history-only/unsupported-symbol access audit; frontend/backend contract |
| Token price/state/evidence/features | Main families connected | Additional saved fields below; frontend |
| Token chart | Historical 1h, last-retained anchor, <=600 buckets | Old 5m/15m/1h/4h/24h selector, downsampling and metadata; frontend + bounded data contract |
| Price exports | Not migrated as equivalent downloads | Old price JSON/CSV links, timestamps/units/source/gap metadata; frontend |
| Book detail | bid/ask/spread/imbalance | Visible depth notionals, microprice displacement, slope/concentration and sequence-gap/degraded evidence; frontend |
| Flow/OI | selected windows/shares/deltas | Trade rate/notional, OI absolute deltas/rate/acceleration and price/OI context; frontend |
| Structure | VWAP displacement + volatility | Range high/low/position/expansion, swings/HH-LH/HL-LL and prior-range classification; frontend |
| Research | prospective counts/outcomes and candidate explanation | Legacy historical bar/source coverage and event-study definitions/per-horizon detail; source contract + frontend |
| System | pure registry projection + disabled controls | Accepted code deployment, bounded runtime/feed diagnostic coverage and identity evidence; backend first |
| Empty/stale/unknown | Implemented and tested bounded cases | Review invalid/Unicode identity, limits/truncation, malformed sources across migrated routes; joint |
| State overview/filter/timeline | Pending | Overview distribution + Movers state filters existing decided backlog; timeline later proposal, not automatically a legacy retirement blocker |
| Backtest/Paper/CMC/catalysts | Unavailable/proposed | Future research capabilities, not required for replacing existing old UI |

Main persisted parser/detail symbol path currently accepts ASCII A-Z0-9 only. This is a coverage boundary, not proof that every contract identity is supported. Audit existing normalizer and retained identities before deciding a Unicode policy; never join external tokens on symbol alone.
Not all absent fields require backend feature development: many already exist in persisted feature JSON and only need presentation. Do not ask the other agent to reimplement formulas already present.

## Recommended order and ownership
1. DASH-V2-65: frontend parity matrix and first implementation slice: global symbol discovery/search and complete recorded token fields. Compare actual fields/units/timestamps to old source and canonical JSON; unavailable remains unknown. No new formulas.
2. DASH-V2-66: chart range selector and bounded exports; explicitly define historical vs current anchors, max points, truncation/downsampling and missing-history semantics. A 600-row query is not automatically sufficient for 24h; budget per range before implementation.
3. DASH-V2-67: historical coverage/study navigation and diagnostic completeness. State filters/distribution can be included after saved state coverage is known. Timeline needs real transition persistence and remains a separate proposal.
4. In parallel, user-managed backend agent: deployment reconciliation and read-only diagnostic contract audit (see handoff). No collector or watcher runs implicitly authorized by this report.
5. DASH-V2-CUTOVER: source-parity/reliability/security/reference checks, route/dependency scan for old SSR HTTP, desktop/mobile empty/partial/stale/failure cases, refresh while filters remain stable, recovery test and launch instructions. Archive old UI entry point reversibly only after those criteria pass.

## Cutover acceptance, distinct from operational readiness
Required: every legacy feature classified as migrated, intentionally retired with recorded decision, or explicitly accessible equivalent; no accidental loss of data/export access. Same-source field/units/null/date comparisons pass. Source failure/limits visible, no fixture fallback. No browser/Next SQLite write path; GET status remains pure. V2 works with the old HTML server unavailable without interrupting canonical collector/control services. Preserve restart/rollback instructions and old files until recovery verified. Do not stop an old process until its identity and dependencies are proven.
Start may remain disabled when V2 becomes the sole presentation interface. New supervised runs, long-run readiness, paper and execution are separate gates; retiring HTML does not authorize them. Current feed data will only advance if the authorized canonical collector produces new records.

## Seven closeout fields
DECISIONS_REVIEWED: V2-63 source contract, migration plan, local dashboard skill, approved asset inventory, backend acceptance/deployed split.
NEW_DECISIONS_RECORDED: separate legacy retirement from new research/operational gates; prioritized coverage sequence, no claim of full migration.
FEATURES_IMPLEMENTED: audit/report and scoped backend handoff only; no runtime feature.
FEATURES_VERIFIED: current source inventory, ten safe GETs, canonical counts/dates, branch/checkout identity and browser evidence; scope limitations above.
DEFERRED_FEATURES: listed parity gaps, OS/feed liveness, watcher runs, control enablement, strategy validation and future labs.
BACKLOG_UPDATED: next frontend parity slice and backend-only deployment/diagnostic audit, without advancing SUCCESS_GATES.
DOCUMENTATION_CONFLICTS: published backend commit was not original deployed checkout; new report explicitly distinguishes them. Earlier historical plan labels remain dated.

## Manual visual assessment
Fresh desktop Overview and mobile BTC captures inspected; actual approved Overview asset compared. Composition is coherent and readable, with no page overflow in the audited widths, but exact reference parity is PARTIAL. Current panels devote more height to provenance and repeated research/freshness text. Approved reference has a richer global search/header, icon-led metrics, denser rankings/mini-series and compact health hierarchy. Some illustrative aggregates/state/sparklines cannot be copied because source evidence is absent. Next visual pass should consolidate repeated provenance into inspectable details while preserving visible stale/date status, strengthen metric hierarchy and align spacing/icons/header after functional parity. Missing Opportunities target remains an asset limitation. No arbitrary percentage of visual completion assigned.
