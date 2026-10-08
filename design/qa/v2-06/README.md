# DASH-V2-06 — Opportunities inspector and regression QA

Date: 2026-10-08
Worktree: C:\proyectos\binance-futures-dashboard-v2-worktree
Branch: dash-v2-03-token-detail

## Scope
- Refactored Opportunities into readable, semantically structured components.
- Added four-field candidate inspector summary (lifecycle, observed state, priority, freshness) with responsive layout and stale warning color.
- Added a polite live region for filter result count, explicit table column scopes, and preserved candidate selection/empty-state semantics.
- Added two deterministic component tests: candidate selection updates inspector, and filtered-out candidates cannot leak evidence.
- Preserved research-only DEMO fixture, rule version, provenance and no-probability wording. No backend or API changes.

## Validation
- TypeScript: PASS
- ESLint: PASS
- Vitest: 35/35 PASS (33 previous + 2 new)
- Next.js production build: PASS
- Chrome screenshots: opportunities desktop 1440x1000 and mobile 390x850; token detail regression desktop/mobile.
- Viewport overflow check: Opportunities desktop documentWidth=1425/1440, mobile=390/390; token desktop=1425/1440.
- Browser captures are evidence of rendered output and width checks, not a claim of pixel-perfect visual parity.

## Known blockers
- Approved Opportunities visual target is missing from the original asset ZIP; `opportunities.png` contains Token Detail, `token-detail.png` contains another Movers image. Preserve originals and do not claim parity PASS until corrected.
- F-V2-BFF-01 not implemented; all shown candidate metrics remain static DEMO examples.
- Git push may be blocked by tool safety; verify remote SHA before claiming publication.
