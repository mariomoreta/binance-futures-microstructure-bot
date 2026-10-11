# DASH-V2-70 — recorded transport diagnostics
Date: 2026-10-11. Bounded diagnostic presentation slice DONE; full legacy parity remains PARTIAL.

## Audit and change
System had eight diagnostic rows, omitted persisted missing-stream, parse/payload-error and clock-offset fields, and labeled a fresh sample RECENT_FROM_ACTIVE_RUN based solely on a timestamp near recorded started_at. Telemetry rows contain no independently verified run identifier; temporal compatibility cannot establish association.

Projection now labels RECENT_RECORDED_SAMPLE / HISTORICAL_ONLY / FUTURE_RECORDED_SAMPLE without inferring run membership. Future ages remain negative and explicitly unverified; malformed dates return no snapshot. Counter parsing preserves observed zero and unknown, rejects arrays, nonfinite/negative counts and partially malformed maps. Clock offsets retain signed milliseconds.

System displays four additional recorded fields. Overview keeps its four compact metrics and receives the corrected provenance semantics. Counters belong to the stored sample's observation window; no invented 24-hour rate or current liveness. Existing current runtime/feed/supervisor/sentinel separation and disabled control remain intact.

No data migration, Python application edit, writable DB initializer, acquisition or old HTTP dependency was introduced. Host resources and event feed remain NOT CONNECTED/NO EVENT FEED: current telemetry_snapshots schema has no host-resource column. Separate log/host adapter and timestamped event contract require another bounded phase.

## Verification
192/192 frontend tests (183 + nine regression cases), TypeScript/lint/build exit 0. One existing BotControl lint warning remains. Initial command wrapper incorrectly expanded PowerShell LASTEXITCODE; exit-sensitive checks were rerun through Python subprocess and recorded in checks.json. No frontend Python changes; prior V2 496-test result is historical, not rerun here.

Browser: System at 1672/1366/390, disclosure+Refresh status, Overview smoke check, zero page overflow/exceptions/errors. Full-page screenshots and browser.log in design/qa/v2-70. Manual desktop/mobile comparison with design/references/v2-approved/system.png: panel colors/borders, dense rows and responsive stacking retained; exact reference fidelity remains PARTIAL (reference contains demo health/gauges and panels awaiting real data). Do not copy demo status/numbers.

Readonly SQLite plus /system and runtime GET audit confirms canonical DB and registry hashes unchanged. Latest stored snapshot remains dated 2026-10-10; present health is not inferred from it. Managed production restart replaced only owned V2 Node process: http://127.0.0.1:3020, PID 23296. Old dashboard was not stopped.

## Continuation
Next V2-71 scope: source-backed persistence/research/universe panel parity inventory and a bounded readonly adapter where records support it; preserve unknown when a required timestamp/source is missing. Host and event contracts remain separate. Full legacy retirement is pending coverage review; extraction alone does not authorize deletion. Start, operational runs and SUCCESS_GATES are unchanged.

DECISIONS_REVIEWED: V2-64 contracts, V2-68 source separation, V2-69 extraction.
NEW_DECISIONS_RECORDED: sample recency never proves run identity; future timestamp cannot be fresh.
FEATURES_IMPLEMENTED: pure recorded projection, missing/error/clock rows, nine regressions.
FEATURES_VERIFIED: 192 frontend, type/lint/build, three widths plus control/Overview checks, hash purity.
DEFERRED_FEATURES: full pipeline/resource/event parity, retirement, liveness, Start and longevity.
BACKLOG_UPDATED: bounded diagnostic slice done; complete migration/BFF remains PARTIAL.
DOCUMENTATION_CONFLICTS: RECENT_FROM_ACTIVE_RUN overclaim removed; schema absence prevents host claims.
