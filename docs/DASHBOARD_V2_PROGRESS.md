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


## DASH-V2-03 — Token Detail isolated preview slice (2026-10-08)

- Implementation lane: dedicated Git worktree `C:\proyectos\binance-futures-dashboard-v2-worktree`, branch `dash-v2-03-token-detail`, segregated from P1-13A backend agent. No Python changes.
- Implemented `/symbol/[symbol]` research workspace: contract identity, demo price and 24h change, tier/capability, Market State Intelligence panel (state/direction/rule version/support/counterevidence/missing/previous), structured microstructure metrics, honest chart/history placeholders.
- Demo contract: BTCUSDT supplies explicitly static fixture values but state remains UNKNOWN (no authoritative Python response); other symbols default to null/UNKNOWN and do not borrow BTC evidence. No API integration, no expected returns, no signals.
- Governance traceability: F-STATE-V2-TK-01 is **PARTIALLY IMPLEMENTED DESIGN ONLY**, not VERIFIED with live classifier data. F-STATE-V2-TL-01 remains PROPOSED. BFF remains NOT IMPLEMENTED.
- Typecheck, ESLint, Vitest (26/26, including 2 token-detail tests) and Next production build passed locally in isolated worktree; browser pixel comparison not yet verified.
- Existing preview `127.0.0.1:3000` is the original worktree and is deliberately NOT restarted or replaced. New worktree preview requires its own independent port.
- Next: optional isolated browser QA/preview on 3001, then review/merge after P1-13A status reconciliation. Do not claim this is live-data-ready.

## DASH-V2-03B — Token Detail visual refinement (2026-10-08)

- Following user browser screenshot review, reorganized the detail page: market-state category strip (explicitly nonsequential), concise three-column support/counterevidence/missing panel, metric-card grid, smaller no-data modules for chart and research.
- No invented price series, transitions or market-state claims. Classifier remains UNKNOWN until versioned backend connection, timeline remains proposed. The displayed count describes populated DEMO metrics only.
- Independent worktree and branch; P1-13A backend lane untouched. Local typecheck PASS, ESLint PASS, Vitest 26/26 PASS, production build PASS. Screenshot/browser pixel QA pending user review of updated preview.

## DASH-V2-04 — Opportunities V2 DEMO research screener (2026-10-08)

- Independent development worktree/branch only; backend P1-13A.1 remains owned by separate agent, no frontend API calls or backend mutations.
- Implemented /opportunities: four research summary cards, symbol/family/lifecycle/direction/tier filters, deterministic priority sorting (null last), interactive candidate inspector with supporting/contradictory/missing evidence, history-status and token detail links.
- Five explicitly synthetic DEMO candidates exercise distinct families and lifecycles. All freshness STALE; data source clearly labeled DEMO. Research-priority score is NOT probability, forecast, profitability, execution signal or expected return.
- Runtime data integration and versioned /api/v1 BFF remain NOT IMPLEMENTED. F-OPP-UI-01 remains design-stage, not live-data VERIFIED. Backend P1-13A API/status under independent corrective audit; no merging without reconciliation.
- Local verification: TypeScript PASS, ESLint PASS, Vitest 30/30 PASS (4 new opportunities tests), Next.js production build PASS, independent preview http://127.0.0.1:3004/opportunities HTTP 200; Chrome desktop 1440x1000 and narrow 390x850 capture inspected. Responsive layout adjustments applied after narrow-screen findings; shared shell/nav horizontal overflow remains an existing cross-route concern for a later shell pass.

## DASH-V2-04B — visual-target governance and Opportunities polish (2026-10-08)

- Published approved V2 target PNGs but contact-sheet inspection found source ZIP name mismatches: `opportunities.png` actually Token Detail, `token-detail.png` actually Movers; correctly labeled Opportunities image is NOT present in the local eight-image ZIP. The discrepancy is documented in `design/references/v2-approved/README.md`; never report asset parity based on the wrong PNG.
- Updated AGENTS.md, dashboard-v2 skill, and handoff to make approved visual targets binding with actual-data truth constraints.
- Opportunities DEMO screen CSS refined for professional terminal treatment: accent/contrast, metric hierarchy, clearer selected rows, inspector/evidence emphasis, focus outlines and narrow layout; no change to business rules, backend, Python or API.
- Local TypeScript, ESLint, Vitest (30/30), and production build passed. Live browser visual comparison of this new CSS still required after an isolated preview starts; do not claim screenshot parity yet.

## DASH-V2-05 — shared shell, accessible research views, reproducible QA (2026-10-08)

- Isolated worktree: `C:\\proyectos\\binance-futures-dashboard-v2-worktree`, branch `dash-v2-03-token-detail`. Started at `91a64f7`; no backend, DB, probe, Python, main, or Muse Spark worktree changes.
- Shared shell: single semantic main landmark with keyboard skip link; responsive scrollable horizontal navigation below 1024px; current-page navigation semantics including future routes; min-width/overflow guards to prevent whole-page horizontal scrolling.
- Opportunities: selection buttons expose `aria-pressed` and inspector relationship; candidate table has keyboard-focusable named scroll region; summary decoration no longer empty squares; duplicate in-page DEMO badge removed (persistent shell indicator remains).
- Token Detail: removed nested main landmark and duplicate DEMO badge, added explicit observed-state/direction labels, signed demo change tone, stronger evidence/metric hierarchy and mobile layout. Authoritative classifier remains UNKNOWN.
- Verification: TypeScript PASS; ESLint PASS; Vitest **33/33** (3 new accessibility tests); Next production build PASS (10 generated pages including dynamic token route). Chrome CDP 1440x1000 desktop and 390x850 mobile screenshot evidence in `design/qa/v2-05/`.
- Browser viewport check: Opportunities mobile 390/390 document width, Token Detail mobile 390/390; desktop 1440/1440 or narrower. No global horizontal overflow. The Opportunities candidate table scrolls within its own panel.
- Visual reference: Token Detail PARTIAL design match; Opportunities **ASSET_MISMATCH** (correct approved image not present under its name). No pixel-perfect claim. Mockup values remain illustrative and never represented as real data.
- Feature ledger: F-OPP-UI-01 and F-STATE-V2-TK-01 marked PARTIAL (DEMO UI only) on this V2 branch. F-V2-BFF-01 remains NOT IMPLEMENTED. Backend P1-14A belongs to the other agent.
- Python suite deliberately not rerun here because backend P1-14A is concurrently owned; no Python source modified.
- Next: reconcile approved Opportunities image filename/content, further parity refinements, then design and verify versioned read-only BFF contract before live data integration. No strategy/execution authorization implied.

## DASH-V2-06 — Opportunities inspector clarity and QA (2026-10-08)

- On isolated `dash-v2-03-token-detail` worktree only, refactored Opportunities component and added a compact responsive candidate evidence summary: lifecycle, observed state/direction, priority and freshness. All values are explicit DEMO fixture data, not authoritative live opportunities.
- Improved table semantics (column scopes), filter-result announcement and evidence selection/empty-state accessibility.
- TypeScript PASS, ESLint PASS, Vitest **35/35 PASS** (2 added tests), production build PASS.
- Chrome CDP captured Opportunities 1440x1000 and 390x850 plus Token Detail regression; no global horizontal overflow in verified viewports. Evidence: `design/qa/v2-06/`.
- Visual parity **NOT VERIFIED**: approved Opportunities PNG absent/misnamed. Token Detail screenshot regression captured but not pixel-parity approved.
- Backend, main, Muse Spark P1-14A, and BFF untouched. Git remote sync must be checked independently; do not claim published until SHA matches.

## DASH-V2-07 — 2026-10-08 (Opportunities provenance and lifecycle semantics)

- Starting local HEAD: `0f6110f`; branch `dash-v2-03-token-detail`, worktree isolated from backend. Remote HEAD before slice: `91a64f7` (two earlier commits not yet published).
- Scope: Opportunities DEMO presentation only. Added lifecycle-specific color semantics and UP/DOWN direction treatment; a dedicated dataset provenance panel now exposes fixture mode, stale count, zero verified outcomes and disconnected API. No backend requests or contract changes.
- Tests: TypeScript PASS, ESLint PASS, Vitest **37/37 PASS** (two new tests), Next.js production build PASS.
- Browser QA: Chrome CDP captures `design/qa/v2-07/opportunities-desktop.png` at 1440x960 and `opportunities-mobile.png` at 390x844. Document/body widths: desktop 1425/1425 within 1440; mobile 390/390 within 390. Reviewed both images: readable badges, no global horizontal overflow; candidates table remains independently scrollable on mobile.
- Token Detail: no source changes this slice; prior v2-06 desktop/mobile evidence retained, not reclassified as a new capture.
- Visual parity: PARTIAL. Approved Opportunities target remains absent/mislabeled in original bundle; do not claim image parity PASS. Approved Token Detail target is present under wrong filename.
- Safety: no live data integration, trading, execution, account or backend changes. All displayed candidate values remain explicitly illustrative.
- Publication: local commit pending at time of writing; GitHub push attempt blocked by tool safety check. Do not mark remote synced without independent SHA confirmation.
- Next: reconcile approved image assets without losing originals; continue approved visual parity and independently publish local commits when allowed.

## DASH-V2-08 — 2026-10-08 (Token Detail provenance + two-page regression)

- Worktree/branch: isolated `C:\proyectos\binance-futures-dashboard-v2-worktree` / `dash-v2-03-token-detail`. Baseline HEAD `0f6110f`, two earlier local commits ahead of remote `91a64f7`; previous DASH-V2-07 changes were still uncommitted at slice start.
- Token Detail: added explicit as-of UTC provenance strip for the BTCUSDT static fixture, NOT LIVE and classifier API NOT CONNECTED labels; unknown symbols state no fixture/timestamp available. Clarified that displayed rules version is an illustrative label, not an authoritative classifier result. Coverage badge now explicitly DEMO. No data model or backend changes.
- Opportunities: retained DASH-V2-07 lifecycle/direction semantics and provenance panel, without promoting research priority to probability or trading signal.
- Validation: TypeScript PASS; ESLint PASS; Vitest **39/39 PASS** (2 new Token Detail provenance tests); Next.js production build PASS. No Python suite run (separate Muse Spark backend lane).
- Browser: independent production preview :3012; Chrome CDP 1440x1000 and 390x850 for both Opportunities and Token Detail. Four captures + widths in `design/qa/v2-08/`; no global horizontal overflow. Screens inspected for label readability and truthful data states.
- Visual parity: PARTIAL/ASSET_MISMATCH. Original on-disk approved ZIP misnames two references and lacks correctly named Opportunities artwork; corrected bundle exists in ChatGPT working files but has not been transferred into this Windows worktree. Do not claim target-image parity or remote publication.
- Safety: read-only DEMO UI; no API integration, backend/DB/probe modification, execution, orders, account keys or capital.
- Publication: local commit/push state to be verified after checkpoint; do not mark remote synced without GitHub SHA evidence.
- Next: install corrected visual assets only when available on the Windows worktree; independently verify GitHub publication and continue pixel comparison against matching approved images.

## DASH-V2-09 — 2026-10-08 (Token Detail observation audit and four-column parity)

- Scope: isolated V2 worktree, no Python/backend/Muse Spark changes. Starting HEAD `64276fd` (DASH-V2-07/08 locally committed). Remote publication remained behind local HEAD; push operation blocked by tool safety checks.
- Token Detail: moved previous-state and last-authoritative-evaluation fields from dense footer into a fourth dedicated Observation audit card. Desktop evidence layout now has four balanced panels, matching the approved Token Detail composition more closely. On mobile it stacks without global overflow. UNKNOWN and NOT CONNECTED remain explicit; no fabricated classifier history.
- Tests: TypeScript PASS; ESLint PASS; Vitest **40/40 PASS** (1 new observation audit test); Next.js production build PASS.
- Chrome CDP preview :3014; screenshots in `design/qa/v2-09/`: Token Detail and Opportunities desktop 1440x1000 (document/body 1425), mobile 390x850 (document/body 390). No global horizontal overflow in any capture; Opportunities remains DEMO-only and unchanged.
- Visual parity: PARTIAL for Token Detail, NOT VERIFIED for Opportunities because corrected reference package is not yet installed. Do not claim pixel parity or live API integration.
- Publication: local commit may be created, but remote push remains blocked by safety checks; do not claim synced until verified by remote SHA.
- Next: install corrected approved assets through an authorized transfer, compare screenshots against matching targets, and publish local branch when allowed. F-STATE-V2-TK-01 and F-OPP-UI-01 remain PARTIAL, F-V2-BFF-01 remains NOT IMPLEMENTED.

## DASH-V2-10 — System research diagnostics DEMO shell (2026-10-08)

- Existing four locally pending DASH-V2-05..09 commits published to GitHub before this slice; branch remains independent from Muse Spark P1-14A backend.
- Replaced System placeholder with professional terminal structure based on approved System target: 4 operational overview cards, 6 subsystem diagnostics panels, visible no-data warning and audit-log empty state.
- All operational values remain UNKNOWN / NOT CONNECTED / NOT CHECKED; no manufactured HEALTHY status, uptime, stream counts, integrity claims or fake events. No process start/stop controls implemented. No backend or BFF integration.
- Verified locally: TypeScript PASS, ESLint PASS, Vitest 41/41 PASS (new System honesty test), Next production build PASS. Browser QA and remote publication must be reported independently.
- Do not build new production preview over the same `.next` directory while multiple old ports use it; prefer a new isolated port or independent build output and verify every CSS asset returns 200.

## DASH-V2-11 — Opportunity read-only BFF foundation (2026-10-08)

- Independent frontend worktree and branch only. Python backend and active P1-14A agent files untouched.
- Added Next same-origin GET `/api/v1/opportunities`, fixed allowlisted Python loopback GET `/api/opportunities` target, timeout 2500ms, maximum response body, no-store, fail-closed 503 errors, and explicit schema v1 adapter. No mutations, runtime controls or private access.
- Output includes provenance source `python-marketprobe`, observed timestamp, bounded candidate rows, raw evidence, missing fields, ranking score (research-only), and quality flags. Missing scores remain null. Time-aged persisted records are STALE, never auto-labeled LIVE; near-time records remain UNKNOWN until feed health semantics can establish freshness.
- Local contract test with Python backend: HTTP 200, schema 1, source python-marketprobe, 3 persisted candidates, freshness STALE with `PERSISTED_DATA_STALE`; frontend `/opportunities` remains explicitly DEMO and does not consume BFF yet.
- TypeScript PASS, ESLint PASS, Vitest **45/45** (4 adapter tests added), Next production build PASS. Isolated preview port 3016 HTTP 200 for BFF/page and both CSS assets. No claim of verified predictive validity or live connectivity.
- Next: security and compatibility hardening of BFF, browser evidence, optional explicit source-toggle based on reviewed UI schema, and API contract update. Do not interpret BFF existence as live-data-ready Opportunities UX.

## DASH-V2-12 — Persisted opportunity observation inspector (2026-10-08)

- Added isolated `/opportunities/observations` view consuming same-origin read-only `/api/v1/opportunities`; existing `/opportunities` DEMO UI unchanged, no live signal claims. Displays source/as-of, stale status, quality flags, stored candidates and observed lifecycle; never presents persisted records as actionable current signals.
- Reuses existing bounded Python BFF adapter. No mutation APIs, no backend/P1-14B changes, no fabricated outcomes. TypeScript PASS, ESLint PASS, Vitest 46/46 PASS, production build PASS. Actual browser/CSS QA performed separately.
- Feature status: F-OPP-UI-01 PARTIAL; F-V2-BFF-01 PARTIAL READ ONLY, no full verified live model. Historical-validation and probability remain unavailable.
