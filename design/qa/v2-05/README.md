# DASH-V2-05 visual QA — 2026-10-08

Captured from the isolated Next.js production preview at `http://127.0.0.1:3008`.
The four screenshots are actual Chrome DevTools Protocol renders, **not generated design images**.

| Screen | Desktop 1440×1000 | Mobile emulated 390×850 |
|---|---|---|
| Opportunities | `opportunities-desktop.png` | `opportunities-mobile.png` |
| BTCUSDT Token Detail | `token-detail-desktop.png` | `token-detail-mobile.png` |

Capture script: `frontend/scripts/capture-v2.cjs`. Example from `frontend/`:
`node scripts/capture-v2.cjs /opportunities 390 850 ../design/qa/v2-05/opportunities-mobile.png`

The CDP tool sets the *actual emulated viewport* and checks document/body width.
Measured: 390px viewport, 390px document/body for both screens; desktop 1440px viewport, <=1440px document/body. No global horizontal overflow. The candidate table is intentionally independently horizontally scrollable. Mobile nav scrolls horizontally rather than forcing page width.

Visual comparison:
- Token Detail: PARTIAL visual match to the approved design (the matching visual is currently misnamed `opportunities.png` in `design/references/v2-approved`). Core panels, evidence blocks and status semantics present. Target's global top bar and future chart affordances are not implemented.
- Opportunities: **ASSET_MISMATCH / parity NOT EVALUABLE**. The published `opportunities.png` is actually Token Detail; the correct approved Opportunities target is not in the original on-disk ZIP. Current UI was reviewed against the chat-approved design concept, not falsely pixel-certified.
- DEMO-only fixtures remain clearly labeled; no authoritative live classifier, execution or profit data is connected.

Scope: static frontend shell, research-only accessibility and visual QA. Backend, Python tests, databases, provider calls, P1-14A, and existing server processes were not modified. The preview is separate from existing ports 3000–3007.
