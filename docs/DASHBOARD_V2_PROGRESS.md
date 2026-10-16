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

## O2-RUN-OBS10M — 2026-10-15 (corrida autorizada 600s COMPLETADA)

- Starting SHA: `10cad5c` (presetcommit pre-ejecucion).
- Run: probe-20261015T230630Z (UUID 893f...), 602.615s, 468162 msgs,
  0 rechazos/reconnects/parse, lags sanos, watchers 22+22, cierre
  natural, PIDs muertos, COMPLETED 610s, sin journal, DB 0B.
- Evidencia: RUN_OBS10M_20261015_COMPLETED.txt + 2 capturas terminal.
- Informe push 67472e0; reconciliacion push d7dcc70. V2 abierto, monitor detenido.

## DASH-V2-LINK-EP — 2026-10-16 (trazabilidad stem<->UUID + episodios v1)

- Starting SHA: `d7dcc70`.
- Scope: `link_probe_run_id` + `probe_run_id` + `read_run_detections`
  + `event_episodes.py` v1 + BFF `runtime-control`/`detections` +
  ruta `/detections` + panel System + fixture 245 + contrato
  EVENT_EPISODES; correccion documental agrupados/sin-byte-identidad.
  Sin corridas, umbrales, estrategias, calibracion ni Start/Stop nuevos.
- Verification: suites + typecheck + build + barrera + visual en el cierre.
- Next: commit selectivo, push, entrega.

## DASH-V2-FEEDATTR — 2026-10-16 (correccion atribucion del feed, push 8c73de2)

- Starting SHA: `3f2fcea`.
- Scope: `runtime-control.ts` (sin gracia pre-start, run_id exacto
  primero con fallback temporal conservador + cruce runtime_seconds,
  previous-run distinguido); `runtime-feed.test.ts` (regresion 20s A/B
  + exacto + inconsistente); contratos + decisiones; Start/Stop,
  umbrales e identidad intactos; sin nuevas corridas.
- Verification: typecheck + suites + build + QA visual en el cierre.
- Next: barrera, commit selectivo, push, entrega.

## DASH-V2-RUNVIS-HARDEN — 2026-10-16 (identidad UNKNOWN + feed estricto, push 3f2fcea)

- Starting SHA: `3544ad6`.
- Scope: `supervision.ts` (display owned/gone/replaced/unknown,
  terminal explicito, expiracion 30s); `runtime-control.ts` (feed
  estricto + atribucion current/previous-run/none, 0.05 vs 0.5
  documentados, missing/silent/parse); `RunStatusBar` + `BotControl`
  (misma semantica); contratos + decisiones; tests feed/supervision/
  barra/BotControl (incluida evidencia reciente de otro run);
  Start/Stop/propiedad intactos; sin nuevas corridas.
- Verification: typecheck limpio; frontend 286/286; propiedad backend
  67 verdes; build + QA visual pendientes en el cierre.
- Runtime: ninguna corrida Binance; registry COMPLETED retenido.
- Next: barrera completa, commit selectivo, push, entrega.

## DASH-V2-RUNVIS — 2026-10-16 (visibilidad y control global de corridas, push 3544ad6)

- Starting SHA: `5d4fef6`.
- Scope: backend `control.py` (run_id/process_state/verified/last_exit_at
  aditivos); BFF `runtime-control.ts` (preserva contrato + feed desde
  telemetry + stop proyecto dashboard/agent/direct); `RunStatusBar` global
  en `AppShell` (todas las pantallas); `BotControl` (registrado vs
  verificado, terminal congelado, stop proyecto con confirmación);
  contratos + reconciliación piloto (sin nuevas corridas).
- Tests: backend `test_run_visibility.py` 10 OK (fixtures + sleep
  aislados); frontend 63 OK (bot-control/run-status-bar/stop/contract);
  `tsc --noEmit` limpio; barrera completa + QA visual desktop/móvil
  pendientes en el cierre.
- Runtime: ninguna corrida Binance iniciada; registry COMPLETED retenido;
  V2 abierto para verificación, monitor detenido.
- Next: barrera, commit selectivo, push, entrega con SHA/pruebas/capturas.

## Gate status

P1-10R: RUNNING since 2026-10-08T00:48:20Z (do not disturb). P1-12:
blocked pending P1-10R PASS. P1-12B: DONE. P1-13A: DONE (backend
opportunity engine + dashboard API). Dashboard V2: architecture +
static foundation (DASH-V2-00/01/02); no integration.

## DASH-V2-02 - Professional Futures Market Movers (2026-10-07)

- Implementation: professional DEMO screener with summary cards, combined search/direction/coverage/state/research-interest filters, stable numeric sorting with nulls last, ranked gainers/losers, coverage/data-quality counts, resettable empty state and 8-row pagination.
- Fixture contract: 16 centralized records with raw numeric values, explicit source/as-of, tier, capability and nulls. Criteria are UI exercise boundaries, not validated economic thresholds.
- Semantics: zero is neither gainer nor loser; missing fields never become zero; rankings use only comparable observations; all symbol links use /symbol/[symbol].
- Verification: typecheck PASS; ESLint PASS; Vitest 24/24 PASS; Next production build PASS.
- Responsive/browser QA (recovery agent, live preview :3000): desktop 1440 overview + movers screenshots, 390 mobile overview + movers screenshots, interactive filter/search/sort/pagination/empty/reset checks all correct, overview regression clean, console errors/warnings 0. Table overflow stays table-local on narrow widths.
- Visual reference comparison: NOT EVALUABLE because the reference mockups remain unavailable; no visual-comparison PASS claimed.
- Preview: http://127.0.0.1:3000/movers (production server; PID renewed with identity verification, see decisions).
- Recovery fixes applied: removed both route templates (root CSS-hack banner suppressor + movers children-ignoring override); /movers now composes MoversDashboard directly in page.tsx; AppShell foundation banner replaced by a compact demo strip; fixed summary double-% unit bug. Rankings scope note kept as designed (filtered dataset, explicitly labeled).
- Python backend, databases, runtime registry and formal P1-10R evidence: unchanged.
- P1-10R last observed RUNNING (PID 19084, read-only checks); no PASS/FAIL conclusion made.
