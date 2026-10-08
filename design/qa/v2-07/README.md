# DASH-V2-07 browser QA (2026-10-08)

Chrome DevTools headless screenshots against an isolated Next.js production preview at 127.0.0.1:3013 (not a backend feed).

| Route | Viewport | Document width | Body width | Result |
|---|---:|---:|---:|---|
| /opportunities | 1440x960 | 1425 | 1425 | PASS: no global overflow |
| /opportunities | 390x844 | 390 | 390 | PASS: no global overflow |

Screenshots: `opportunities-desktop.png`, `opportunities-mobile.png`.
Reviewed visually: status colors distinguish WATCHING / ACTIVE_RESEARCH / DETECTED / EXPIRED and UP / DOWN; provenance panel identifies all five stale demo fixtures and no validated outcomes. Candidate table scrolls within its own region on mobile.

Not a visual parity PASS: the published Opportunities reference is misidentified; the actual approved target image is not present in the worktree. No Token Detail changes in this slice; v2-06 captures remain the prior evidence. No backend or execution access.
