# DASH-V2-08 browser QA — 2026-10-08

Independent Next.js production preview: `http://127.0.0.1:3012` (new port; existing preview and backend servers untouched).

| Route | Viewport | Capture | documentWidth | bodyWidth | Global overflow |
| --- | --- | --- | ---: | ---: | --- |
| `/opportunities` | 1440×1000 | `opportunities-desktop.png` | 1425 | 1425 | No |
| `/opportunities` | 390×850 | `opportunities-mobile.png` | 390 | 390 | No |
| `/symbol/BTCUSDT` | 1440×1000 | `token-detail-desktop.png` | 1425 | 1425 | No |
| `/symbol/BTCUSDT` | 390×850 | `token-detail-mobile.png` | 390 | 390 | No |

Chrome headless CDP script: `frontend/scripts/capture-v2.cjs`. Visual inspection: no global horizontal overflow, provenance strip legible on desktop/mobile, state remains UNKNOWN and fixture as-of clearly labeled. The Opportunities table intentionally scrolls inside its panel on mobile. These captures are implementation evidence, **not** approval of pixel parity with the official visual references; original reference bundle still contains mislabeled Opportunities and Token Detail files. No backend or live-data integration.
