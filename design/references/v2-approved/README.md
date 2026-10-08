# Dashboard V2 — Official Visual Targets (approved 2026-10-08)

These designs are the intended product UI target, not merely decorative inspiration. All agents must review this folder before implementing or redesigning V2 screens.

| Route | Approved reference asset |
|---|---|
| Overview | overview.png |
| Movers | movers.png |
| Opportunities | opportunities.png |
| Token Detail | token-detail.png |
| System | system.png |
| Backtest (future) | backtest.png |
| Paper Lab (future) | paper-lab.png |
| Movers dense alternative | movers-alternative.png |

## Binding design and safety rules

- Pursue the mockup's professional terminal composition: layout, information density, hierarchy, restrained contrast, iconography, data tables and panels.
- The mockup figures, statuses, performance curves and timelines are *illustrative*, not observations or permission to fabricate data.
- Populate numeric fields only from authoritative versioned APIs with provenance/as-of/coverage/freshness; otherwise render UNKNOWN/STALE/NOT AVAILABLE.
- NEVER represent discovery-only contracts as deep LIVE; research priority is not profit probability or a trading recommendation.
- No trading, real orders, account access, capital or execution authorized. Backtest and Paper Lab remain clearly unavailable until actual validation exists.
- Reconcile actual behavior with `docs/FEATURE_BACKLOG.md`, `docs/DASHBOARD_V2_DESIGN_SPEC.md` and `docs/DASHBOARD_V2_API_CONTRACTS.md`.
- Report visual parity screen-by-screen and document deliberate deviations. Do not claim screenshots show currently implemented functionality.

## Asset publication status

Images to be copied from the approved ChatGPT image bundle into this directory and committed as real PNG files. A README by itself is not completion. Verify all eight PNG files are present in GitHub before reporting visual references as fully published.

## Visual asset identity audit (2026-10-08)

IMPORTANT: The originally uploaded ZIP contains misnamed PNG files. An actual-image contact-sheet audit found:

- `overview.png`: Overview target (correct).
- `movers.png`: dense Movers layout (correct).
- `movers-alternative.png`: dense Movers/watchlist layout (correct).
- `backtest.png`: Backtest target (correct).
- `paper-lab.png`: Paper Lab target (correct).
- `system.png`: System target (correct).
- `opportunities.png`: INCORRECTLY NAMED — its content is Token Detail / BTCUSDT.
- `token-detail.png`: INCORRECTLY NAMED — its content is another Movers layout.

Do NOT treat `opportunities.png` as an Opportunities reference or `token-detail.png` as Token Detail until assets are corrected. The approved Opportunities image shown in the chat is still missing from this on-disk ZIP and must be obtained and checked before claiming its asset publication. The approved Token Detail visual is physically present under the wrong filename; do not discard it. Treat all values in every image as illustrative, never factual market data.

Visual quality gate: report ASSET_MISMATCH instead of marking a screen parity PASS when its matching image is absent or mislabeled.
