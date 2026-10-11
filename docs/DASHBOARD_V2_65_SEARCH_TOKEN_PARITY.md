# DASH-V2-65 - retained symbol search and recorded token parity
Date: 2026-10-11. Status: DONE bounded implementation; old-interface retirement remains pending.
Base: 8780da2b9f6829119f433962d56a0914488115fa; branch dash-v2-03-token-detail.

Scope: same-origin global retained-symbol search plus saved token fields absent from V2-63. Original backend/main/data/controls untouched. User-managed backend agent owns deployment reconciliation and read-only contract audit separately.
Search scans literal canonical symbol-bearing tables and retained discovery; no exchange call or token identity enrichment. Parameterized input, bounded output and visible coverage limits. Historical-only result never implies current subscription or deep feature presence. Existing ASCII identity restriction remains explicit pending coordinated policy.
Token families: saved book depth/microprice/slopes/concentration/integrity; flow notional/rate/delta; OI absolute/rate/acceleration/context; VWAP raw prices; range and swing/prior-range structure. Independent dates; null and warmup evidence retained; conversions use audited units only. No reconstructed depth, strategy signal or predictive claim.
Workflow: source/reference audit -> implementation -> meaningful tests + V2 Python suite -> build -> desktop/mobile browser review -> docs/checkpoint. Old UI remains recoverable. Charts/ranges/exports/study linkage and full retirement remain subsequent slices.

## Delivered
Global header search + /search server route and navigation entry, source-bound retained symbols across ten literal tables and saved discovery tops. Matches pushed into parameterized SQL before a 51-row output cap; UI shows up to 50 unique ASCII symbols, exact/prefix ranking and truncation notice. Input rejects unsupported characters/wildcards/length >32. Historical-only identities can be found; their detail still honestly shows missing deep features rather than fabricating a quote. No new /api/search JSON equivalence claimed. Search is a submitted read, not automatic collection.
Token now has nine collapsible dated families. Added visible top1/5/10/20 notionals, microprice displacement, slope asymmetry, concentration, recorded sequence gaps/degradation, flow notional/trade rate/delta ratio/warmup, OI absolute delta/rate/acceleration/context, raw VWAP, ranges and last saved swing/HH-LH/HL-LL/prior-range structure. Values reuse saved JSON; unmeasured horizons stay null. Other raw metadata/rank display, full legacy study linkage, chart ranges/exports and identity policy still require coverage review. This is not a claim that every raw field has migrated.

## Verification
Final frontend: 157/157, 34 files (146 baseline + 4 query normalization/ranking/cap + 4 token units/date/missing/warmup + 3 real SQLite in-memory search-query regressions). Types/lint/build exit 0; one pre-existing BotControl cleanup-ref warning. Python V2 snapshot: 496/496, exit 0, 86.403s suite. Not a backend operational run.
Full browser: 8 routes x 3 widths = 24 cases, no browser errors/unavailable responses or page overflow. Native header form Enter verified with LUMIA query at each width; missing query remains empty. All nine token families opened for capture at known/absent symbols, no rendered demo fallback. Desktop Movers preserved 8 rows/four ranking columns.
Mobile search table initially required horizontal scroll to reach Inspect; wrap/layout correction rebuilt successfully and affected search routes recaptured separately (mobile-search-results.json). Tests precede only this final class/CSS correction; build and fresh browser assertions verify it. Production http://127.0.0.1:3020, managed PID 25632.
Evidence: design/qa/v2-65/verification.json, final-frontend-verification.json, logs and after/full-results.json plus mobile-search-results.json. Final mobile correction: 3 affected search cases passed with explicit table-fit assertion and native Enter; fresh mobile image manually reviewed. Closeout checks passed. Ending SHA is the checkpoint commit containing this report.

## Visual assessment
Approved token/Overview targets inspected. Global search now restores part of intended header functionality; dark terminal layout and evidence hierarchy retained. Nine feature families default collapsed, preserving main-screen density; expanded rows show independent dates and recorded flags. Mobile token crop manually reviewed. Search has no dedicated approved target; it reuses terminal controls/table style. Exact reference parity remains PARTIAL and missing Opportunities reference unchanged. Mobile-only results wrap preserves visible token action.

## Seven closeout fields
DECISIONS_REVIEWED: V2-64 coverage sequence, V2-63 canonical contract, local dashboard skill and approved reference assets.
NEW_DECISIONS_RECORDED: retained-record search vs current exchange universe; fixed output cap/ASCII boundary; additional family projections; recorded warmup/integrity never current health.
FEATURES_IMPLEMENTED: search/header/navigation plus expanded saved token fields and mobile search action visibility.
FEATURES_VERIFIED: deterministic tests, native SQLite search, full browser/keyboard and final mobile build/captures as scoped above.
DEFERRED_FEATURES: ranges/exports/studies, exhaustive field/identity parity, state distribution/timeline, feed/process liveness, runtime enablement and old SSR retirement.
BACKLOG_UPDATED: bounded V2-65 coverage implemented; next V2-66 range/export contract; backend user-managed handoff remains separate.
DOCUMENTATION_CONFLICTS: search was previously table-local only; now globally accessible retained search, not current-universe completeness. Book/OI/structure parity progressed without adding formulas. No new backend acceptance claimed.

## Next
DASH-V2-66: explicitly bounded historical chart ranges and CSV/JSON exports, aligned with backend read-contract audit when received. Keep old HTML as fallback. No DB writes, Python backend edits, Start, probes, market requests, backfills, paper, orders, main merge or SUCCESS_GATES changes in V2-65.
