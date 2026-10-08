# DASH-V2-09 browser QA — 2026-10-08

Preview: http://127.0.0.1:3014 (isolated worktree production build, DEMO only).

| Route | Viewport | Screenshot | Document width | Body width | Global horizontal overflow |
| --- | --- | --- | ---: | ---: | --- |
| /symbol/BTCUSDT | 1440x1000 | token-detail-desktop.png | 1425 | 1425 | NO |
| /symbol/BTCUSDT | 390x850 | token-detail-mobile.png | 390 | 390 | NO |
| /opportunities | 1440x1000 | opportunities-desktop.png | 1425 | 1425 | NO |
| /opportunities | 390x850 | opportunities-mobile.png | 390 | 390 | NO |

Chrome headless CDP captures via frontend/scripts/capture-v2.cjs, reviewed visually. Token Detail evidence section now follows the approved mockup's four-card desktop structure, while maintaining responsive stacking and explicitly UNKNOWN classifier history. No market-state inference from demo prices.

Validation: TypeScript PASS; ESLint PASS; Vitest 40/40 PASS; Next.js production build PASS.

LIMITATIONS: Original approved reference filenames remain incorrect, corrected asset ZIP not present in Windows worktree; pixel parity NOT VERIFIED. No read-only BFF/live-data integration. No orders, execution, account API, trading, or backend modifications. GitHub remote publication must be checked separately.
