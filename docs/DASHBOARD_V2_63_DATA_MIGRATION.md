# DASH-V2-63 — canonical data migration
Date: 2026-10-11. Status: DONE bounded data migration, not complete cutover acceptance.

## Scope and execution
User authorized migration to V2 as the intended primary interface. Python collectors/classifiers and canonical SQLite remain authoritative. No DB migration, duplicate engine, market requests, probes or operational enablement. Old dashboard retained until coverage and cutover gates pass.

| Surface | Audited starting source | Target / validation |
|---|---|---|
| Overview | static fixtures | canonical persisted discovery/features/research counts; distinct timestamps; unknown runtime and aggregate measures |
| Movers | static professional fixtures | bounded retained discovery tops + feature symbols; historical coverage, no market-wide breadth claim |
| Token detail | fixture lookup | persisted classifier/evidence and per-feature timestamp; absent symbol stays unknown |
| Price series | Python HTTP, current 1h | persisted samples; explicitly anchored historical 1h; timestamp-scaled gaps |
| Observations/prospective/verified movers | Python HTTP; limited refresh | canonical read-only projections where contracts permit; no dependency on old SSR interface |
| Historical/archive/Market Lab | canonical SQLite read-only | retain and verify |
| Runtime/control | pure backend status; disabled Start | retain; process, watcher and feed health separate |
| Backtest / Paper Lab / enrichment | unavailable | remain unavailable; not invented by migration |

Sequence: consistent read-only snapshot and pure normalization → main screens → periodic refresh → adapter parity → frontend/Python checks → fresh desktop/mobile reference comparison → report/checkpoint.
Freshness is calculated at reading time from validated observation timestamps; captured freshness flags are historical evidence only. Future/malformed timestamps never fresh. Browser polling reads persisted state and does not create new market observations. Discovery context and deep features may have different dates; display both. No copy of production DB.

## Acceptance
No runtime fixture imports on migrated routes; unavailable source means empty/unknown, never demo fallback. Null values remain null. Persisted state is labelled recorded, not current trading signal. Filters preserve research semantics and do not become entry rules. Tests exercise malformed/future/absent/stale data and units. Visual references determine layout, never numeric content.
Source fail/refresh pause must be visible. Start stays disabled. Main/backend operational gates unchanged.
Old-interface retirement and fully live feed remain pending separately.

## Implemented migration matrix (2026-10-11)
| Surface | Implemented source / behavior | Residual |
|---|---|---|
| Overview | canonical discovery + retained feature evidence + saved sample counts; separate source dates | current market-wide activity and feed health unknown; state distribution pending |
| Main Movers | 29 retained symbols at audit; filter/sort/page; per-row source and independent dates; 8 rows/default | selected tops are not the full 439 eligible contracts; state filters and all legacy search/export variants pending |
| Main Opportunities | 68 saved candidates at audit; normalized canonical records; 12/page; visible-page evidence | priority/lifecycle historical, edge validation unknown; no predictive validation or execution |
| Token Detail | real stored classifier/version/evidence and 6 summary measures + extended dated families | complete depth/ranges/study linkage and timeline pending; unknown token stays unknown |
| Price series | schema 2, direct saved mark samples, last-retained historical hour, timestamp x-axis/gaps | historical observation, not fills or current quote |
| Saved/prospective/verified views | direct read-only SQLite BFF + bounded polling | no lifetime process counters/currentness inferred |
| Historical/archive/Market Lab | retained canonical reads + periodic refresh; distinct outcome symbol count | exhaustive legacy feature/export parity pending |
| System/control | existing pure runtime adapter and independent evidence retained | Start disabled; watcher binding/runtime observation remains separate |
| Future labs / enrichment | truthful unavailable workspace retained | no backtest/paper/provider engine introduced |

## Evidence and limits
Base frontend SHA: 9ad26c500cbbc2125ac842f74c391088b540e0cb. Branch: dash-v2-03-token-detail. Ending SHA is the checkpoint commit containing this report.
Backend acceptance c635938fc5542be992e06838a8727652225e1657 remains separate and unchanged; original backend checkout/data and main preserved.

Actual read-only BFF audit: market snapshot v1 returned 29 retained symbols; last discovery 2026-10-10T14:02:11.080Z, 439 eligible contracts. Opportunity adapter returned 68 saved candidates. Prospective returned 66 setups / 228 outcomes. BTC price schema 2 returned 226 valid historical points ending 2026-10-10T14:04:30Z. These are retained observations, not newly collected data. Reading the DB does not authorize or start its collector.

Validation:
- Frontend: 146/146 tests, 31 files; typecheck, lint and production build exit 0. One existing BotControl cleanup-ref warning remains. See design/qa/v2-63/verification.json and logs.
- V2 Python snapshot: 496/496, exit 0, 74.937s suite (75.861s wall). This is not the backend branch's separate 902-test acceptance.
- Temporary SQLite tests: reads allowed, UPDATE denied, fixture bytes unchanged; missing source not created. Production DB not used as a writable fixture.
- General real-browser audit: 15 routes × 1672/1366/390 = 45 captures, 0 page overflow, 0 browser errors, 0 unavailable-source responses. Main migrated screens have no rendered DEMO fallback; bounded tables, candidate pager and disabled Start checked.
- Actual browser auto-refresh: server read metadata advanced after the next 15s poll while source discovery date remained historical. This is DB-read refresh evidence only.
- Final affected-screen delta: 18 browser cases passed after absence/label cleanup (final-delta-results.json). Final token banner cleanup: 4 fresh desktop/mobile cases passed (final-token-label-results.json); known/absent-token images manually reviewed. No browser errors or unavailable-source responses in either delta. Final production build exit 0 (final-build.log); managed production PID 24168. General audit predates these small presentation cleanups; affected routes were recaptured.

## Visual review
Fresh screenshots compared with approved overview/movers/token references. Dark terminal frame, six-card metrics, table-first Movers with four ranking columns, token state/evidence grid and narrow-width navigation retained. Real values and missing measures override illustrative reference numbers/curves.
Deliberate departures: additional provenance/date rows; stale stored classifications instead of invented current state; selected-subset distribution instead of market-wide breadth; absent/unknown operational aggregates; descriptive acceleration/extreme-gainer filter labels; extended features collapsed to preserve density. Main candidates paginated rather than 68 rows expanding the workbench.
A local mobile source-label overrun was detected and fixed using compact human-readable source with full tooltip plus wrapping; tiny measured momentum no longer rounds to zero. Opportunities lacks an approved matching asset; no exact parity claim for it. Complete visual fidelity and whole legacy cutover are PARTIAL.

## Seven closeout fields
- DECISIONS_REVIEWED: approved migration/source-truth boundaries, source freshness and unknown semantics, local V2 skill, approved references, disabled Start and V2-62 backend acceptance.
- NEW_DECISIONS_RECORDED: canonical direct read-only facade, price schema 2 historical anchor, independent source dates, bounded polling/candidate paging, truthful filter names and absence counts; append-only DASHBOARD_V2_DECISIONS.md.
- FEATURES_IMPLEMENTED: main canonical views, research/price adapters, periodic read refresh, real persisted classifier explanation, extended feature presentation, small-value precision.
- FEATURES_VERIFIED: deterministic normalization/units/future/absence/readonly/polling/selection tests and browser evidence listed above. Does not establish current feed, watcher protection, new runtime longevity or economic edge.
- DEFERRED_FEATURES: full legacy search/export/study/depth/range parity, state distribution/filter/timeline, external enrichment, current liveness, supervised launch/watchers/runtime window, backtest/paper, old SSR retirement.
- BACKLOG_UPDATED: F-V2-DATA-MIG-01 bounded implementation; token real-data connection; explicit remaining state features and unchanged backend/operational gates. Current state/task queue/progress/architecture/contracts/migration/agent handoff reconciled.
- DOCUMENTATION_CONFLICTS: historical "not implemented" plan headers now dated; HTTP-only planned data path reconciled with existing/direct canonical read boundary; demo-only source labels removed from runtime views; borrowed flow/exhaustion labels corrected without changing research predicates; retained row count not confused with eligible universe.

## Current checkpoint and next boundary
Implementation, testing and visual closeout DONE within bounded migration scope. V2 production URL remains http://127.0.0.1:3020, with the old dashboard retained as fallback.
Next coverage phase audits every remaining legacy route/export/feature against V2 and closes safe presentation gaps. This checkpoint does not retire old SSR, turn on Start or authorize operating runs. SUCCESS_GATES unchanged.
