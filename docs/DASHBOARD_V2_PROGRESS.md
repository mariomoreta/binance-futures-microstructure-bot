# Dashboard V2 Progress

**Purpose:** factual slice ledger for Dashboard V2.  
**Status:** DASH-V2-01 COMPLETE 2026-10-07 (professional Overview composition; fixtures only, no API integration).  
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
## DASH-V2-01 — 2026-10-07 (professional market overview)

- Starting SHA: `75c34815e8963e25237b93344b3a66e8b2cc107f`.
- Scope: `frontend/` only — TopBar (market context, ENGINE/FEED/RESEARCH
  chips, OBSERVE ONLY example, last-data, compact DEMO pill),
  OverviewMetricGrid (6 provenance-carrying metric cards), MarketPulsePanel
  (breadth bar + accel/vol/activity/concentration, no-signal disclaimer),
  MoversSnapshot (8-column table + /movers link + symbol links),
  ExtremeMoveWatch (descriptive monitor, no predictions/entries/targets),
  ResearchHealthPanel (recorder/feed/persistence states kept distinct),
  MarketContextPanel (BTC/ETH refs + CMC-future note, no endpoints called).
  Nav regrouped with icons; literal `/symbol/[symbol]` menu link removed.
- Data: centralized fixtures with BFF-forward types (MetricPoint/PulseData/
  ExtremeMoveRow/HealthFacts/MarketContextFacts); null stays missing;
  zero external references in `frontend/src` (grep-verified).
- Tests: `tsc` clean; `eslint` clean; `vitest` 15/15 (freshness states,
  null-vs-zero, no-prediction language, snapshot links); `next build`
  9 routes; ephemeral checks + persistent preview on :3000 serve 5/5
  routes 200 (server PID renewed 31648 → 28552, old process
  identity-verified before stop; probe PID 19084 untouched).
- Visual QA: desktop + 390px-mobile overview screenshots, movers
  regression shot, 0 console errors; tables scroll intentionally on
  narrow widths. VISUAL_REFERENCE_COMPARISON: NOT AVAILABLE (four
  reference mockups absent).
- Python suite: 408/408 green (backend untouched, verification only).
- P1-10R: RUNNING throughout (read-only status checks only); no DB,
  registry, config, or evidence contact.
- Pending integration data per panel: versioned overview/pulse/movers/
  research/health/context contracts (DASH-V2-02+); provider legal review;
  reference mockups for future visual PASS.
- Next authorized slice: DASH-V2-02 only on explicit instruction.

## Gate status

P1-10R: RUNNING since 2026-10-08T00:48:20Z (do not disturb). P1-12:
blocked pending P1-10R PASS. P1-12B: not implemented. Dashboard V2:
architecture + static foundation (DASH-V2-00); no integration.
