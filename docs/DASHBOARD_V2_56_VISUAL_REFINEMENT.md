# DASH-V2-56 - Overview and Movers reference composition

Date: 2026-10-11. V2 base: 7b2b5e75cf69263cbcdd1bf2e78bd01848ec63c4.
Scope: bounded frontend visual refinement and all-route regression captures.
Backend owner receives [separate preparation prompt](DASHBOARD_V2_56_BACKEND_HANDOFF.md).
No backend source/strategy/API-contract or execution change.

## AUDIT / PLAN

Reviewed approved README and actual overview.png/movers.png images, current
visual roadmap and fresh production captures before editing. Overview used a
tall vertical pulse-metric table; its navigation link ran into the panel title.
At 1672px Movers used a ranking side rail, constraining the primary market table
and hiding capability/freshness behind horizontal scrolling.

Plan: restore full-width Movers table and four-column rankings below it;
default to eight visible rows while retaining 16/32 choices; compact existing
Overview pulse values into a row of tiles and align panel links/title hierarchy.
Reuse current fixture data and clear DEMO/source/UNKNOWN labels. Do not copy
illustrative sparklines, economic metrics or healthy statuses from references.

## IMPLEMENT / TEST

Removed conflicting desktop side-rail overrides in the two Movers stylesheets.
Changed initial pagination to existing PAGE=8 and adjusted the pagination test
to exercise 8 -> 16 -> 8 -> next. Overview styles now arrange existing pulse
table rows as four tiles on desktop, two at narrower widths; preserve DOM content.
Increased Overview title hierarchy and aligned section action links.

Frontend: 118/118 tests, 27 files, 34.92s, exit 0.
Typecheck and production build: PASS, exit 0.
Lint: exit 0, zero errors, one existing BotControl effect/ref warning.
V2 Python snapshot: 496/496, 73.777s, exit 0.
Syntax and git diff checks: PASS.
No backend owner's changing suite was substituted for the separate V2 snapshot.

## VISUAL VERIFY

Before/after capture script: scripts/qa-dashboard-visual.mjs.
Routes: Overview, Movers, verified Movers, Opportunities, observations,
prospective outcomes, Token BTCUSDT, historical research, Market Archive,
Market Lab, System, Backtest, Paper Lab.
Widths: 1672, 1366, 390; viewport height 941.
Before results: 39 captures, no browser errors; expected unavailable endpoints
reported separately (18 occurrences).
After results: 39/39 cases, zero browser errors, zero page overflow, 18 expected
unavailable-source occurrences; design/qa/v2-56/after/results.json.
Automated checks cover document overflow, one main, active navigation, mobile
menu/Escape, plus desktop Movers table fit/eight rows/four ranking columns.
Actual matching reference and before/after screenshots inspected for changed
screens; other routes receive navigation/layout regression verification only.

| Screen | Visual conclusion / remaining gap |
|---|---|
| Overview | PARTIAL: compact pulse tiles, title/action hierarchy improved; source-backed activity/context contracts still pending, no copied graphs |
| Movers | PARTIAL: full-width eight-row table plus four-column boards matches primary composition; missing reference-only measurements/series not fabricated |
| Verified Movers | NO DEDICATED REFERENCE; existing recorded-data view preserved |
| Opportunities | ASSET_MISMATCH: correct approved asset still absent |
| Observations / prospective | NO DEDICATED REFERENCE; research data semantics preserved |
| Token Detail | PARTIAL, regression only in this slice |
| Historical research / Market Archive / Market Lab | NO DEDICATED REFERENCE; regression only |
| System | PARTIAL, regression only; recorded process and disabled Start preserved |
| Backtest / Paper Lab | PARTIAL: unavailable-engine compositions retained |

This is not pixel-perfect acceptance or a live-data claim. Overview and primary
Movers remain clearly labeled fixture compositions; verified observations remain
separate. No new values, history, probability or trading plan was invented.

Managed V2 restart: verified Node listener identity/creation time before restart;
old PID 35700 -> new PID 18520, URL http://127.0.0.1:3020.
Only V2 server restarted. No probe launch or canonical backend control action.

## DOCUMENT / CHECKPOINT / NEXT

Decision/progress/backlog/current state/queue/visual roadmap updated. Backend prompt
prepares a disabled transactional supervised contract with deterministic tests;
no actual run permission. Next visual scope: Token Detail/Opportunities composition
under current contracts; missing Opportunities target prevents visual parity PASS.
Rollback: revert this bounded V2 frontend commit and rebuild/restart managed V2.

DECISIONS_REVIEWED: approved visual target README; existing terminal composition,
fixture/source boundaries; V2-55 acceptance and visual roadmap.
NEW_DECISIONS_RECORDED: full-width Movers with rankings below and eight default
rows; retain user-selectable 16/32 and source semantics.
FEATURES_IMPLEMENTED: bounded Overview/Movers visual refinement; QA script.
FEATURES_VERIFIED: frontend/Python/static/build and scoped screenshot evidence.
DEFERRED_FEATURES: live Overview/Movers contract completion, missing reference,
complete pixel parity, transactional Start, longevity and strategy proposals.
BACKLOG_UPDATED: existing V2 presentation/BFF items remain PARTIAL; no new gate.
DOCUMENTATION_CONFLICTS: earlier side-rail layout superseded here; prior audit
and backend corrections remain historical; fixture UI is not live coverage.
