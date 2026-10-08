# Dashboard V2 Progress

**Purpose:** factual slice ledger for Dashboard V2.  
**Status:** DASH-V2-00 COMPLETE 2026-10-07 (isolated static foundation; no API integration).  
**Rule:** update after every slice; never describe planned code as implemented.

## DASH-V2-ARCH — 2026-10-07

- Starting SHA: `6270be29a5444e56d4fac9e51f04d5882bc5554b`.
- Workspace/branch gate: PASS.
- Pre-existing untracked content: `.firecrawl/`, preserved and excluded.
- Audit: current Python SSR/API/control/history/research contracts verified.
- External research: official CMC, CoinGecko, Next.js/Vite and TradingView
  documentation reviewed; two CMC keyless routes live-probed HTTP 200 and an
  immediate third received 429, proving keyless access and the need for a
  conservative unknown-rate budget.
- Decisions: Python preserved; Next.js+BFF recommended; Binance canonical;
  stable-ID mapping; CMC-first optional context; CoinGecko fallback.
- Application code: unchanged.
- Runtime: unchanged; no dashboard/probe restart and no soak.
- Dependency installation/scaffold: none.
- Verification/ending SHA/commit/remote: fill at checkpoint completion.

## Future slice template

```text
SLICE / DATE
STARTING_SHA / ENDING_SHA
SCOPE / FILES
CONTRACTS CHANGED
TESTS + EXACT RESULT
VISUAL CAPTURES + REFERENCE RESULT
RUNTIME IMPACT
KNOWN GAPS / DECISIONS
COMMIT / REMOTE STATUS
NEXT AUTHORIZED SLICE
```

## DASH-V2-00 — 2026-10-07 (isolated frontend foundation)

- Starting SHA: `8be06aa8824126785bdc10734a97f0e3adff5d63`.
- Scope: `frontend/` only (Next 16.4.0 + React 19.3.0 + TS strict
  `react-jsx`, eslint flat, vitest+jsdom+testing-library). Tokens,
  15 foundation components, 7 static routes + dynamic `/symbol/[symbol]`
  (singular, matching the Python backend; architecture folder plan shows
  plural — resolved in slice decision, see DASHBOARD_V2_DECISIONS.md).
- No API integration: zero fetch/Binance/CMC/127.0.0.1 references in
  `frontend/src`; fixtures labeled DEMO DATA — NOT LIVE; no Start/Stop
  wiring; no chart library.
- Tests: `tsc --noEmit` clean; `eslint src` clean; `vitest run` 10/10;
  `next build` 9 routes prerendered; ephemeral `next start :3000`
  served 7/7 routes HTTP 200 then stopped (no persistent server).
- Visual: /overview + /movers screenshots captured from the ephemeral
  server; NO visual PASS claimed (four reference mockups absent).
- Python suite: 408/408 green (untouched backend, verification only).
- P1-10R: running probe (PID 19084) undisturbed; no DB/registry/config
  contact; `node_modules/` + `.next/` local-only, never committed.
- Next authorized slice: DASH-V2-01 only on explicit instruction.

## Gate status

P1-10R: RUNNING since 2026-10-08T00:48:20Z (do not disturb). P1-12:
blocked pending P1-10R PASS. P1-12B: not implemented. Dashboard V2:
architecture + static foundation (DASH-V2-00); no integration.
