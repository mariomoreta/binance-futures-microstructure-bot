# Backend/frontend data handoff — DASH-V2-63
Date: 2026-10-11.

V2 at http://127.0.0.1:3020 is the intended principal research interface. Its existing core screens now read the canonical Python SQLite directly on the Next.js server in read-only mode. This is a presentation migration; Python acquisition, feature formulas, candidate ranking, prospective recorder and control plane remain authoritative.

## Responsibilities
- Backend branch: phase1/market-intelligence-dashboard. Accepted bounded disabled launch corrections remain c635938fc5542be992e06838a8727652225e1657. Original checkout was preserved; reconcile it normally before new backend work.
- Frontend branch: dash-v2-03-token-detail. No copies of the production DB and no second collector.
- Persist timestamps, symbol identity, units, nulls, schema/version and rule-version evidence. Do not inject current health into old snapshots.
- Changes to persisted schema/JSON semantics require a contract review with V2; additive fields are preferred. Never rename a fractional return to a percent without coordinated conversion.
- All browser data goes through V2/server-rendered views or same-origin BFF. The browser cannot open SQLite.
- Old HTML dashboard remains a fallback; do not remove it. Production collector/control modules remain in the backend checkout.
- This task does not authorize probes, Start, traffic, paper, trading, long runs or success-gate advancement.

## Sources
Overview/Movers: discovery_snapshots plus bounded feature-table records. Retained tops are a selected subset, not all eligible contracts and not market-wide breadth.
Token: return/flow/book/OI/structure/state records with independent observation timestamps; persisted classifier evidence is labelled recorded.
Research: opportunity_candidates and prospective tables. A saved score is research priority, not calibrated probability.
Charts: price_samples, BFF schema 2 historical 1h anchored to the last retained sample; gap-aware timestamp rendering.
Runtime: existing pure status path; process, supervisor, sentinel and feed remain separate. Start remains disabled.

## Remaining cutover work
This checkpoint does not certify exhaustive parity with every legacy export/search/study/feature-depth view, current liveness or a supervised runtime window. Keep those as explicit tasks in the migration matrix. Retiring old SSR requires its separate cutover gate.
