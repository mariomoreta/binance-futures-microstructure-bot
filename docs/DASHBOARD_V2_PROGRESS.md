# Dashboard V2 Progress


## DASH-V2-62 - 2026-10-11 - backend corrections completed directly

User authorized this reviewer to correct backend R1-R5/C1-C2 directly. Published c635938fc5542be992e06838a8727652225e1657 on phase1/market-intelligence-dashboard: bounded disabled correction DONE/ACCEPTED, 902/902 canonical and 52 focused OK; exact published source checksum verified. Original backend checkout/evidence preserved and needs git pull --ff-only. V2-61 handoff is superseded; no repeat correction request. See [bounded acceptance](DASHBOARD_V2_62_BACKEND_CORRECTIONS_ACCEPTANCE.md). Internal disabled preparation is not an enabled capability: Start/pure GETs/production V2-60 and SUCCESS_GATES remain unchanged. Actual watcher startup binding/spawn/rollback and longevity remain unverified; no operational PASS or new runs. Visual N/A for this checkpoint.


## DASH-V2-61 - 2026-10-11 - disabled launch review

Exact backend da231b911e9b1a0cfe86b3aaa3325e5b71928687 reviewed read-only from Git archive: CHANGES REQUIRED, not accepted for integration. Public disabled guard verified; nine deterministic cases reproduce five new issues (foreign run ownership/rollback, ignored watcher recheck, wrong default supervisor command, finite-budget violation, unreadable-final uncertainty). Future tolerance and claimed pure preflight timing also require reconciliation. Backend canonical 873/873 OK (170.494s); V2 snapshot 496/496 OK (83.491s), both exit 0. Passing existing suites do not negate new reproductions. See [review/evidence](DASHBOARD_V2_61_SUPERVISED_LAUNCH_REVIEW.md) and [complete backend correction prompt](DASHBOARD_V2_61_BACKEND_HANDOFF.md). Start stays disabled; pure status GETs and production V2-60 remain unchanged at http://127.0.0.1:3020. Next: backend owner fixes bounded R1-R5/C1-C2, then exact-SHA review. V2-55 accepted R1/R2 remain closed; no probes, gates, main merge or backend worktree edits. Visual verification N/A for this nonvisual checkpoint.

## DASH-V2-47 — Evidence-based runtime readiness (2026-10-10)

- Continued from remote DASH-V2-46 at fcaaca2, rather than uploaded DASH-V2-02.
- Fixed fabricated observe mode and concurrency PASS on missing/UNKNOWN
  controller evidence. Reject non-object JSON and preserve controller errors.
- Frontend: 84/84 tests, TypeScript, lint and production build PASS. New
  18-case regression suite fails 12/18 on original code. Production HTTP
  runtime/readiness smoke returns 200 and UNKNOWN with unavailable controller.
- Python: 494/496 PASS; two independently reproduced Windows PID-identity
  tests fail on Linux. No backend edits; Windows acceptance remains pending.
- Nonvisual correction: visual verification NOT APPLICABLE. No Windows
  deployment or live-data verification claimed; start remains disabled.
- Audit, bounded plan, evidence and seven closeout fields:
  docs/DASHBOARD_V2_47_READINESS_AUDIT.md.

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

## DASH-V2-13 — Persisted observations evidence inspector (2026-10-08)

- Expanded saved-opportunity read-only view with selectable persisted records, direct evidence for/against/missing inspector, rule version, historical evidence status, and original observation timestamp. Added navigation from the DEMO Opportunities screen to the separate persisted-record page. Never merges synthetic DEMO rows with actual stored candidates.
- Local TypeScript PASS, ESLint PASS, Vitest 46/46 PASS, Next production build PASS. Test phase took longer under resource contention; no backend Python/P1-14B changes.
- API remains bounded read-only v1; persisted candidates retain STALE/UNKNOWN and are not represented as actionable current signals. Browser smoke and publication to be verified separately.

## DASH-V2-14 — Prospective read-only research panel (2026-10-08)

- Added `/api/v1/prospective` read-only local Python adapter for schema v9 with timeout, bounded response, no-store, fail-closed 503, and explicit missing-as-null semantics. New `/opportunities/prospective` displays actual persisted horizon states and marks return only when COMPLETE with valid numeric value; no trading claims.
- Does not alter backend or Muse Spark P1-14B worktree. Existing Opportunities DEMO and saved observations pages remain isolated.
- TypeScript PASS, ESLint PASS, Vitest 48/48 PASS, Next.js build PASS. Browser QA separately verified.

## DASH-V2-15 — Unified research navigation (2026-10-08)

- Added consistent responsive navigation among setup explorer DEMO, saved Python observations READ ONLY, and prospective outcome research READ ONLY. Explicitly distinguish sources; each view marks the active route accessibly.
- Backend P1-14B untouched; no execution routes or invented outcomes. TypeScript PASS, ESLint PASS, Vitest 49/49 PASS, Next build PASS. Browser/CSS preview smoke to verify separately.

## DASH-V2-16 — Movers visual parity round 1 (2026-10-08)

- True target asset: `design/references/v2-approved/movers.png` (1672x941). Actual browser before/after captured at 1672x941 using Chrome: `movers-before-parity.png` and `movers-after-parity.png` (untracked local QA evidence).
- Comparison BEFORE: market table was pushed below rankings and coverage, partially off first viewport. AFTER: table follows filters and precedes rankings; tighter card/panel/table spacing; table now visible in first viewport with 8 paginated rows.
- Visual parity remains PARTIAL. Major gaps: approved mockup uses top horizontal terminal navigation rather than shared side shell, richer column set/sparklines and multiple four-column research leaderboards; current DEMO source does not supply real price series. Preserve data integrity, do not draw invented sparklines or mix discovery/live metrics.
- Provenance: all metric values remain DEMO-only; no new backend reads. Responsive table remains horizontally scrollable. TypeScript, ESLint, Vitest 49/49 and Next build PASS; preview `http://127.0.0.1:3022/movers` and both CSS assets HTTP 200.
- Asset blocker: approved `opportunities.png` is mislabeled Token Detail; exact Opportunities visual target missing. Resolve official asset manifest before claiming Opportunities visual parity.

## DASH-V2-17 — Movers full research-terminal composition, visual QA (2026-10-08)

- True approved visual target: `design/references/v2-approved/movers.png` (1672x941). Captured actual browser at target desktop resolution before DASH-V2-17 (`movers-after-parity.png`, local QA) and after (`movers-v2-17-qa-desktop.png`), plus narrow Chrome capture (`movers-v2-17-qa-mobile.png`). Files are untracked local QA, not approved mockups.
- Integrated eight genuine client-side DEMO leaderboards derived from available fixture fields: top gainers, top losers, 24h quote volume, positive and negative velocity, acceleration and deceleration, and deep-coverage velocity. Missing metrics excluded, no invented sparklines/history. Separate discovery REST 24h metrics from subscribed deep velocity, and retain explicit DEMO source label. No numerical predictive probability.
- Added eight usable top quick-filter tabs (All, Hot, Gainers, Losers, Positive Flow [velocity+accel proxy], Negative Flow [velocity+accel proxy], Volume, Exhaustion research [extreme gainers proxy]) using existing deterministic filters; tabs are research-interest proxies, not actual independently measured aggressive flow or exhaustive exhaustion assessment.
- Retained market-table-first hierarchy and deep/discovery capability tags; added responsive 4/2/1 leaderboard columns. Main desktop viewport now shows tabs, metrics, screener, table, and start of leaderboards. Target mockup remains a visual PRODUCT GOAL, not an exact delivered replica.
- Technical checks: TypeScript PASS, ESLint PASS, Vitest 49/49 PASS, Next production build PASS. On isolated `http://127.0.0.1:3023/movers`, HTML/CSS requests HTTP 200; Chrome QA desktop 1672x941 and narrow 390x850.
- Honest outstanding UI parity: approved reference uses horizontal terminal header, richer per-symbol numeric metrics and mini-trend charts, denser rows, and four board rows; actual desktop fidelity IMPROVED / PARTIAL, not full. Mobile screenshot still exhibits horizontal overflow in shared shell/header/summary at 390 viewport and needs a separate full responsive correction. No real candle/velocity series supplied to draw sparklines, no new Python API.

## DASH-V2-18 — Desktop terminal shell structural parity (2026-10-08)

- Desktop-only priority confirmed: no tablet/mobile scope for this slice. Audited approved `design/references/v2-approved/movers.png` against real Chrome screenshot at 1672x941. Biggest global discrepancy: 226px sidebar and restricted main width versus full-width horizontal trading-terminal reference.
- Changed shared shell desktop >=1025px to full-width top navigation, compact branded terminal header, navigation emphasis, and full-width content. All existing routes retain their own datasets/DEMO versus READ ONLY distinctions. Corrected outdated global banner which claimed no API integration even though partial read-only research adapters exist.
- Browser smoke on http://127.0.0.1:3024 checked /movers, /overview, /opportunities, /system, /symbol/BTCUSDT: all HTTP 200; CSS assets returned 200. Captured `v2-18-desktop-shell.png` (untracked QA) at reference resolution and visually inspected. Shared desktop shell now materially closer to approved target.
- Remaining differences are substantial: missing true time-series sparklines, richer market columns, dense panels and some typography and status-line alignment. Do NOT declare pixel parity or display invented market data. Approved Opportunities PNG mislabel issue remains independently documented.
- Frontend checks: TypeScript PASS, ESLint PASS, Vitest 49/49 PASS, production build PASS prior to global copy-only correction. Keep future commits scoped; do not alter backend/Muse Spark P1-14B.

## DASH-V2-19 — Desktop market breadth visual component (2026-10-08)

- Compared actual Chrome 1672x941 Movers with approved target and introduced a horizontal market-breadth research panel (positive/negative/flat/missing buckets) from existing DEMO fixture only. Explicitly distinguishes 14 measured of 16 fixtures and 2 UNKNOWN, with coverage disclaimer. No invented time series, real feed status or market-wide claim.
- Desktop structure: branded horizontal terminal, quick filters, summary, market breadth strip, screener, central table and research leaderboards. This is incremental parity improvement, not full match with approved design.
- Verification: TypeScript PASS, ESLint PASS, Vitest 50/50 PASS, production build PASS; isolated preview 3025/movers HTML/CSS HTTP 200. Screenshot `movers-v2-19-qa.png` (local QA, untracked) visually inspected at 1672x941.
- Future priority: high-value additional table metrics based on verified live API schema and genuine as-of price time series for sparklines; avoid fabricated flow, probabilities or price traces.

## DASH-V2-20 — Movers market-table numeric correction and honest trend slot (2026-10-08)

- Audited desktop Movers table against reference and found the Price column was bound to symbol sorting rather than numeric price. Extended `SortKey` with `price`, retained null-last behavior, and enabled genuine numeric Price sorting.
- Added explicit 1h trend slot per symbol showing `NO SERIES` until as-of-aligned verified price history exists. Never invent sparklines or mistake present 24h value for historical series. Sticky symbol column and refined table-header contrast support dense desktop reading.
- Verified frontend TypeScript, ESLint, Vitest 50/50 PASS and Next production build PASS; Chrome screenshot `movers-v2-20-qa.png` at approved 1672x941 shows all table columns, no fake trends. HTML/CSS both HTTP 200 on isolated `http://127.0.0.1:3026/movers`.
- Fidelity remains PARTIAL: dense authentic time-series mini charts and broader market metrics require future versioned data contract. Backend P1-14B untouched.

## DASH-V2-21 — Verified mark-price chart read path (2026-10-08)

- Contract-audited canonical Python `GET /api/symbol/{symbol}/price?range=1h` which reads persisted 10s markPrice buckets and returns timestamp/price points. Added fixed-loopback, read-only, bounded and no-cache Next BFF `GET /api/v1/price-series/[symbol]` with symbol validation, abort timeout, source/range checks and explicit 503 fallback.
- Added client-only `VerifiedPriceChart` in Token Detail Price and structure section: a real SVG line only when >=3 valid as-of points, rejecting future/out-of-window/invalid prices and preserving source timestamps. No fake sparkline from one 24h return. Removed duplicate placeholder.
- Python backend on port 8091 was unreachable during this round: live API check returned BFF 503 as designed, screenshot of BTC Token Detail at 1672x941 confirmed unchanged authoritative classifier UNKNOWN. No verified live price-series demonstrated. No backend mutation or process restart.
- Frontend TypeScript/ESLint PASS, Vitest 52/52 PASS, Next build PASS (pre duplicate-placeholder removal); TypeScript/ESLint and Vitest 52/52 rerun after final edit. HTML+CSS both HTTP 200 in isolated preview 3027. Still NOT full design parity or live system.

## DASH-V2-22 — Movers verified 1h sparkline integration (2026-10-08)

- Added `VerifiedSparkline` to each visible paginated Movers row. Reads already-versioned same-origin `/api/v1/price-series/[symbol]` for time-ordered persisted markPrice samples; only draws a line on >=3 valid points, never derives a fabricated trend from static daily percent changes. Unavailable/unpopulated responses retain `NO SERIES`.
- UI still labels core Movers fixture metrics DEMO. A real historical line, when present, is explicitly labeled by accessible markPrice provenance, not conflated with the fictional demo values.
- No Python code/process modifications, no active Muse Spark P1-14B interference. Frontend validation TypeScript/ESLint PASS, Vitest 52/52 PASS, Next production build PASS. Isolated preview `http://127.0.0.1:3028/movers` HTML and two CSS HTTP 200, headless Chrome 1672x941 screenshot `movers-v2-22-qa.png` reviewed. Python source unavailable, BFF returned HTTP 503 and honest `NO SERIES` displayed. No actual chart-data success demonstrated.
- Remaining: real deep series coverage + coherence of current/demo market rows, browser interaction tests for asynchronous sparkline, official design fidelity audit.

## DASH-V2-23 — Enforced source segregation in Movers (2026-10-08)

- Architectural correction: removed Python historical sparkline from the per-row DEMO fixture table. It was unsafe to juxtapose actual persisted price history with fictional price, returns, momentum and fixture freshness in the same row. Restored DEMO screener to a homogeneous fixture-only table.
- New standalone `VerifiedHistoryPanel` with BTCUSDT/ETHUSDT/SOLUSDT historical markPrice 1h sparklines independently from demo rankings. Shows explicit read-only historical provenance and warns against comparing or correlating them with DEMO metrics. Existing BFF returns 503 when Python unavailable; no invented curves.
- QA: TypeScript PASS, ESLint PASS, Vitest 53/53 PASS, Next build PASS. Chrome 1672x941 screenshot `movers-v2-23-qa.png` confirms table-only fixtures; historical panel follows table (below first viewport), available on scroll. Preview `http://127.0.0.1:3029/movers` HTML/CSS 200. No backend P1-14B interference.
- Next requirement: eventually replace entire Movers DEMO universe with an authoritative time-aligned backend read model and show historical series only in compatible provenance context; do not mix until validated.

## DASH-V2-24 — Independent persisted Movers BFF and table (2026-10-08)

- Audited backend routes `/api/discovery`, `/api/features/momentum`; no consolidated public Movers JSON endpoint exists. Created same-origin read-only `/api/v1/live-movers` adapter that fetches both independently, merges only by canonical symbol, preserves null values, and distinguishes discovery-only vs deep subscribed coverage. Explicitly declares source as persisted Python and warns about unaligned as-of clocks; no synchronous/live-market claim.
- New standalone `/movers/verified` page and navigation link from DEMO `/movers`. No DEMO numbers used in verified read model. Core / HOT proposal tiers drawn only from discovery; subscribed flag requires momentum source. Missing data remains missing. Not yet suitable for combined charts/profit interpretation.
- Python port 8091 was offline: read-only BFF returned 503, verified Chrome screenshot at 1672x941 shows fail-closed UI alert, not fictitious market entries. Main /movers and new /movers/verified and CSS returned HTTP 200 on isolated 3030 preview.
- Frontend TypeScript, ESLint, Vitest 55/55 and Next build PASS. Does not touch backend P1-14B or other branch. Next audit must validate exact momentum shape, timestamps and full observation coverage with actual backend before elevating confidence.

## DASH-V2-25 — Field-level source provenance and temporal honesty (2026-10-08)

- Hardened the independent persisted Movers adapter/view. Each row now distinguishes discovery evidence versus subscribed momentum evidence, tracks priceSource (`discovery` / `momentum` / `unknown`) and marks data-source clocks/freshness as UNVERIFIED until matched observed as-of times are available. Adapter response `generated_at` is retrieval-time, explicitly NOT exchange observation time.
- Fixed invalid/nonpositive price handling; missing data remains null. Never presents momentum-only rows as having a discovery 24h return or volume. No unsupported timestamp synchronization, probabilities or live-execution statements.
- Tests expanded to 57/57 PASS; TypeScript, ESLint and production Next build PASS. Isolated preview http://127.0.0.1:3031/movers and /movers/verified HTML and CSS 200; Python backend remains offline, read API 503 and no fabricated records. Browser Chrome captured `movers-v2-25-qa.png` (untracked local QA). Backend worktree remains untouched while agent recovers P1-14B.
- NEXT: integrate actual backend only after source as-of age and synchronization contracts can be verified; do not consolidate DEMO and observed market data into one table prematurely.

## DASH-V2-26 — Desktop Movers terminal density and structure (2026-10-08)

- Re-audited official `design/references/v2-approved/movers.png` against Chrome desktop 1672x941. Implemented terminal integrity strip with explicit fixture-only posture, desktop table-first hierarchy, advanced filters in a collapsed details panel, compact financial metric/table styling, and moved market-breadth analysis below the primary table.
- At 1672x941 screenshot `movers-v2-26-qa.png` shows header/navigation, quick tabs, six fixture KPIs, the eight-row table, pager and breadth strip above the fold. Historical Python charts remain a separate panel below, never mixed with DEMO fixture values.
- Visual fidelity improved but PARTIAL: mockup's extensive verified metrics and sparklines not present, and eight leaderboards fall below the first viewport. No fictitious price series or unsupported trading signals added.
- Frontend TypeScript PASS, ESLint PASS, Vitest 57/57 PASS, Next.js production build exit 0. Isolated preview `http://127.0.0.1:3032/movers` HTML and two CSS 200, screenshot visually inspected.
- Agent P1-14B backend worktree untouched. Local QA PNGs remain untracked; do not stage them.

## DASH-V2-27 — Desktop four-column research leaderboard density (2026-10-08)

- Compared actual Chrome 1672x941 output to approved `design/references/v2-approved/movers.png`. Moved four-column research leaderboards immediately below the market table, ahead of secondary breadth and historical source-separated panels. Optimized board typography, row spacing and card contrast for dense desktop terminal layout.
- New screenshot `movers-v2-27-qa.png` locally reviewed: first leaderboard row now begins within reference-sized viewport below table; full target parity still PARTIAL (more market columns / documented as-of verified series are absent). No synthetic sparklines or mixed DEMO and persisted data.
- TypeScript, ESLint PASS; 57/57 Vitest PASS; production build exit 0. Preview `http://127.0.0.1:3033/movers` and CSS HTTP 200. Backend P1-14B untouched. Untracked QA PNGs preserved outside Git.

## DASH-V2-28 — Market Movers per-symbol provenance inspector (2026-10-08)

- Extended desktop market table with keyboard-accessible per-symbol +/− inspection toggles. Expanded row details show field value, fixture provenance, coverage state, missing evidence and precise fixture timestamp; UNKNOWN is never backfilled. Preserves full-width table, 4-column rank boards, and separate Python historical panels.
- Approved visual target remains `design/references/v2-approved/movers.png` at 1672x941. Before/after Chrome screenshots `movers-v2-28-qa.png` and `movers-v2-28-final.png` (untracked local QA) manually reviewed; fixture detail interaction's expanded browser screenshot not yet captured; semantics covered by component tests, not full browser click automation.
- TypeScript PASS, ESLint PASS, Vitest 58/58 PASS, production Next build exit 0. Isolated preview `http://127.0.0.1:3035/movers` HTML and both CSS HTTP 200. Source claims remain explicitly DEMO; backend not touched.
- Visual parity still PARTIAL; missing actual depth, OI, volume-z and live time-series metrics cannot be added to DEMO without grounded source fields. Next improve authoritative read contract and visual parity once backend evidence is available.

## DASH-V2-29 — Dense desktop table capacity and pagination (2026-10-08)

- Desktop Movers table now shows 16 fixture contracts by default (previously 8) with an explicit accessible rows-per-page selector (8/16/32). Sorting, filtering and pagination reset remain state-consistent; selector is covered by updated interactive pagination test.
- Desktop table gains capped internal scrolling, sticky table heading, stripe/hover contrast for high-density research. This fits all 16 DEMO fixture entries in one logical research table without forcing rankings and other panels to scroll away indefinitely.
- Verified screenshot at 1672x941 saved locally as `movers-v2-29-qa.png` (untracked QA; not part of Git). HTML and two CSS responses HTTP 200 on isolated preview `http://127.0.0.1:3036/movers`. Table and fixture labels display correctly.
- TypeScript PASS, ESLint PASS, Vitest 58/58 PASS, Next production build PASS. Initial old pagination test failed when changing the default from 8 to 16; updated to exercise explicit 8-row selection and full pagination, then reran green. No Python backend files or live engine processes touched.
- Visual parity with approved `design/references/v2-approved/movers.png` remains PARTIAL; this is a desktop data-density improvement, not complete visual parity. Source metrics still DEMO.

## DASH-V2-30 — Desktop financial card/leaderboard visual refinement (2026-10-08)

- Re-audited Movers desktop layout with approved reference. Redesigned 6 market KPI cards using subdued layered surfaces, thin status rails and positive/negative accent typography. Strengthened eight research leaderboard panels with denser rank rows, typography and left guide rail; no source data changes.
- Captured and reviewed 1672x941 screenshot `movers-v2-30-qa.png` in Chrome: cards and full-width primary table remain legible. Rankings remain below table due to 16-row default/570px internal scroll, so visual parity remains PARTIAL and approved target is not achieved.
- Verification: TypeScript PASS, ESLint PASS, Vitest 58/58 PASS, Next production build PASS, isolated `http://127.0.0.1:3037/movers` HTML and 2 CSS assets HTTP 200. QA screenshot is local untracked evidence only. P1-14B backend untouched.

## DASH-V2-31 — Integrated desktop table + leaderboard terminal (2026-10-08)

- Changed Movers primary workspace at >=1450px desktop to a two-column layout: main 16-row (scrollable) market table left and an always-visible eight-board research ranking rail right. This is a structural response to the approved terminal reference, not just cosmetic styling.
- First real Chrome screenshot `movers-v2-31-qa.png` showed illegibly squeezed four-column rankings. Corrected to two readable columns in the research rail, rebuilt and inspected final `movers-v2-31-final.png` at 1672x941. Final capture shows both primary table and first four leaderboards within viewport simultaneously.
- No change to DEMO market figures, backend, provenance or trade execution. Actual price series remain separate from illustrative fixture metrics. Frontend TypeScript, ESLint, Vitest 58/58 PASS, Next production build PASS; preview `http://127.0.0.1:3039/movers` HTML and CSS 200. Target visual fidelity improved but still PARTIAL.
- Local QA screenshots are intentionally untracked. Muse Spark backend worktree untouched.

## DASH-V2-32 — Prospective outcomes ledger and horizon research view (2026-10-08)

- Expanded existing `/opportunities/prospective` from basic latest-records table to a desktop-oriented research workspace with explicit source/provenance banner, setup/outcome counts, five horizon summaries (1m/5m/15m/1h/4h) over latest-returned rows only, and detailed observation ledger including detected/observed mark prices, observed UTC and recorded return. Never infer a complete historic cohort or an execution P&L from latest_outcomes.
- Explicitly refuses to compute maturity lateness because the current exposed outcome normalization lacks `detected_at_ms`; backend must provide verified detection/maturity timestamps before implementing that measure. No statistical success rates, probability or trade advice fabricated.
- TypeScript, ESLint, frontend Vitest 58/58 and production Next build PASS. Isolated `http://127.0.0.1:3040/opportunities/prospective` HTML/CSS HTTP 200. Python source unreachable; BFF returns 503. Headless Chrome QA screenshot `prospective-v2-32-qa.png` verifies honest fail-closed unavailable screen, NOT data-populated layout; future real-data visual verification still required. No Python backend worktree changes.

## DASH-V2-33 — Prospective ledger filtering (2026-10-08)

- Added interactive symbol substring, horizon (1m/5m/15m/1h/4h), and outcome-state filters to the recent prospective observation ledger. Counts reflect only filtered `latest_outcomes` rows, while headline metrics and horizon summary remain explicitly latest-returned data. No inference of full-cohort denominators or realized P&L.
- Desktop filter styling integrated into existing research table. TypeScript and ESLint PASS, Vitest 58/58 PASS, production build PASS. Isolated `/opportunities/prospective` page returned 200 at 3041; Python backend unavailable, BFF 503 and intentional fail-closed notice. Chrome generated `prospective-v2-33-qa.png`; populated-data visual interaction remains unverified until upstream is online.
- Separate V2 worktree only; no backend files/process changes. Local untracked QA screenshots preserved.

## DASH-V2-34 — Prospective evidence quality + safe research CSV (2026-10-09)

- Added deterministic field-level research quality classification to `latest_outcomes`: `COMPLETE_BUT_UNAUDITED` explicitly means basic price/return fields exist but source freshness, true event time and maturity lateness remain unverified; distinguishes non-complete rows, invalid timestamps, missing return and invalid price.
- Prospective Research ledger now shows quality per returned observation and exports only currently filtered recent rows as CSV, using formula-injection-resistant escaping. Never claims this recent-list CSV is a full research cohort or profitable trading history.
- Added 4 pure-helper tests including missing information, timestamp sanity and CSV escaping. TypeScript/ESLint PASS, Vitest 62/62 PASS, production build PASS. Isolated preview `http://127.0.0.1:3042/opportunities/prospective` HTML 200, BFF 503 because Python backend unreachable; Chrome screenshot `prospective-v2-34-qa.png` generated. Populated-data UI remains not verified, not simulated as live.
- Backend worktree/P1-14B.3 untouched. Future: full-cohort quality requires provenance timestamps from Python and audit of 68 stored outcomes before any statistical conclusions.

## DASH-V2-35 — Correct Prospective UI hidden by backend 503 (2026-10-09)

- User could not see DASH-V2-34 updates: verified root cause in ProspectiveView early `if(failure)return ...` prevented all panels/filters/CSV and quality column from rendering whenever Python BFF returned 503.
- Changed fail-closed handling to render the entire interactive research shell when backend is unavailable, with conspicuous `BACKEND UNAVAILABLE — UI PREVIEW` warning and UNKNOWN (not 0) for source-dependent headline and horizon counts. Empty outcome ledger is explicitly not evidence of zero returns.
- Re-tested TypeScript + ESLint, Vitest full suite, production Next build exit 0. Isolated preview `/opportunities/prospective` at 3043 returned HTTP 200, Python BFF 503; inspected Chrome screenshot `prospective-v2-35-offline-qa.png` at 1672x941 proving visible layout/panels despite backend offline. Data-populated functionality is still not verified.
- No Python backend or P1-14B.3 runtime changes. QA PNG remains local untracked.

## DASH-V2-36 — Canonical single-port runtime + QA consolidation (2026-10-09)

- Established **one canonical local frontend port: http://127.0.0.1:3020**; Python engine remains 8091, unmanaged. Frontend `dev`/`start` scripts now target 3020. Added `scripts/dashboard-v2.ps1` with start/status/stop/restart and fail-closed identity checks against PID registry on port 3020. PID registry and launcher log ignored. Future changes must rebuild and restart the SAME port, not proliferate sequential previews.
- Verified 3020 was free before start; new managed listener PID 4144 at QA time. Ten frontend URLs returned HTTP 200: /overview, /movers, /movers/verified, /symbol/BTCUSDT, /opportunities, /opportunities/observations, /opportunities/prospective, /system, /backtest, /paper-lab. Python-powered BFFs /api/v1/prospective, /api/v1/live-movers, /api/v1/price-series/BTCUSDT returned HTTP 503 because Python port 8091 was not listening; do not mark live integration PASS.
- Chrome captured **actual** screenshot `dashboard-v2-36-port3020-qa.png` at 1672x941 from canonical port and reviewed it. UI is visible even with backend offline and honestly shows UNKNOWN.
- Initial Vitest run failed due UTF-8 BOM accidentally introduced by PowerShell JSON rewrite to frontend/package.json; corrected BOM, reran TypeScript, ESLint, complete Vitest suite and Next build successfully. Do not use encoding-BOM when writing config files.
- No Python worktree/process modifications. Old legacy frontend previews may still listen on other ports; unverified process identities were not killed. They are obsolete and not user-facing; use 3020 for all QA, links and further work.

## DASH-V2-37 — Prospective source recovery on canonical 3020 (2026-10-09)

- Prospective Research now offers an explicit **Retry Python connection** button. It re-fetches the same-origin read-only API without replacing unavailable records with DEMO. On recovery it clears previous error state; on failure it maintains visible controls and UNKNOWN counts.
- Added `prospective-recovery.test.tsx` testing offline shell controls and user-initiated retry; existing source separation maintained. TypeScript PASS, ESLint PASS, Vitest 63/63 PASS, Next production build PASS.
- Rebuilt and safely restarted ONLY launcher-owned V2 Node server on canonical port 3020 (old PID 4144, new PID 4860); `/opportunities/prospective` HTTP 200. Backend Python on 8091 not started or modified; data-populated UI remains unverified. No new preview ports.

## DASH-V2-38 — Prospective v1.1 recorder counters (2026-10-10)

- Prospective model BFF now passes through optional numeric recorder `completed`, `pending`, `insufficient`, `in_grace` keys from `/api/prospective`, preserving null/UNKNOWN when keys are absent. No fabricated source freshness or fabricated full historical denominators.
- Prospective Research includes dedicated `Recorder lifecycle · contract v1.1` panel with COMPLETE/PENDING/INSUFFICIENT_HISTORY emission counters and in-memory recovery grace size; labels distinguish process counters from full-cohort storage. PENDING remains terminal only once grace expires; rows not emitted during grace.
- TypeScript PASS, ESLint PASS, Vitest 63/63 PASS, Next production build PASS; canonical launcher safely restarted only owned V2 server on port 3020. Prospective UI HTTP 200, Python data unverified while offline.
- Separate bot code and runtime untouched; no new Next preview ports created.

## DASH-V2-40 — Historical market and runtime archive (2026-10-10)

- Added `/market-archive` with saved SQLite `return_features`, `state_features`, and latest `telemetry_snapshots`. Shows stored mark, source quote age at capture, state/direction, raw return 1m, UTC timestamp; bot-mode/keys/orders/capital are historic snapshot ONLY, explicitly not current runtime health.
- Navigation now links `Market Archive`; all reads via existing `historicalRead` with Node DatabaseSync readOnly=true. No engine commands, no DB writes, no extra preview ports.
- Frontend typecheck, lint, Vitest 63/63, Next build PASS; restart only V2 owned listener at port 3020; GET `/market-archive` 200 and stored feature table visible in rendered HTML. Python port 8091 was not started or interrupted.

## DASH-V2-41 — Historical Market Lab (2026-10-10)

- New `/market-lab` desktop route with interactive symbol selection, saved-time windows (1h/6h/24h/all), comparison with a second symbol, recorded mark-price SVG plot, descriptive observed changes and coverage diagnostics.
- SQLite read-only `price_samples` queries, mapped to plain React-serializable objects, never synthetic/forward-filled. Gaps greater than two minutes break the SVG stroke (do not connect distant observations). Time windows explicitly anchored at latest saved sample, not current time.
- QA: actual Chrome screenshot inspected; corrected SQLite row serialization runtime exception; corrected SVG gaps observed visually. Typecheck, lint, 63/63 tests, production build PASS; server restarted on same 3020, `/market-lab` HTTP 200. No bot process or Python dashboard touched.

## DASH-V2-43 — Persisted System Evidence (2026-10-10)

- System now incorporates an actual SQLite read-only operational evidence panel below the canonical Bot Control Center: last recorded expected/active/stale/silent streams, clock offset, saved setups/outcomes/mark samples, events by type, orders, keys and capital at capture.
- Distinguishes process RUNNING (current PID-verified status from controller) from PERSISTED NOT LIVE telemetry with explicit UTC snapshot provenance; legacy placeholder panels remain marked pending. No inference that historic stream health represents current feed health.
- QA: TypeScript, ESLint, 66/66 tests and Next build passed; canonical port 3020 restarted, `/system` HTTP 200, true Chrome screenshot `system-v2-43-evidence-qa.png` inspected. During snapshot 20/20 streams, 0 stale and 0 silent, 57 setups, 202 outcomes, 2031 price samples, 1181 extreme-funding-rate observations and 11 volume-spike detections. Counts dynamic, not fixed. No engine process was started/stopped.

## DASH-V2-46 — Supervised launch readiness (2026-10-10)

- Audited canonical Python controller and new sentinel (P1-14B.8 work in progress). Existing `start_probe()` launches only the probe; it does not guarantee atomic supervisor+sentinel registration. The V2 observe-start endpoint stays blocked deliberately, not bypassed.
- Added read-only `/api/v1/runtime/readiness` (canonical status + SQLite quick_check + mode + active-run check + explicit atomic-launch blocker), and a `Supervised launch readiness` checklist in System. Reports exact blockers rather than allowing unsafe process start. Existing stop protection preserved.
- Local QA: typecheck, lint, original full suite 65/66 due unrelated System test timeout; isolated System retry PASS; Next build PASS. Canonical 3020 GET /system 200 and readiness API 200 with `ready:false` and four PASS checks/one BLOCKED. No probe started or stopped, no Python agent worktree edits.
- Remaining: implement a verified, race-safe canonical launch integrating supervisor+sentinel on Python side through its owning agent, then test end-to-end start/abort in a separately authorized window. Do not enable V2 until then.



## DASH-V2-48 — System terminal composition (2026-10-10)

- Compact runtime cards, native supervisor/control disclosure, three-column
  health/integration layout and separate persisted evidence; duplicate tiles removed.
- Approved system.png inspected; actual desktop/mobile Chrome and Overview
  captures reviewed. No page overflow; disclosure/Refresh PASS; browser errors 0.
- Windows: type/lint/build and 86/86 frontend tests PASS; V2 Python snapshot
  496/496 PASS. System unit-test real-source timeout corrected by isolation.
- Compact Overview diagnostics mobile columns repaired during regression QA.
- Canonical V2 3020 updated via identity-verified restart; no probe/V1/backend action.
- Reference parity PARTIAL. Full evidence/closeout:
  DASHBOARD_V2_48_SYSTEM_VISUAL_AUDIT.md.


## 2026-10-10 — DASH-V2-49 all-screen visual cycle

Audited 13 routes and all eight reference PNG contents. Shared desktop sidebar,
keyboard-recoverable mobile menu, dense Overview, responsive archives/lab,
finished unavailable-data views, Backtest/Paper Lab empty compositions and
six-metric Token Detail strip implemented. 90/90 frontend, type/lint/build PASS;
V2 Python snapshot 496/496 PASS. Chrome 39 route/width cases PASS at 1672/1366/390,
no page overflow, one main/h1/active primary parent; 18 provider 503s explicitly
recorded as unavailable data. Full data/pixel parity is not claimed.
References renamed with identical SHA-256: opportunities.png -> token-detail.png,
old token-detail.png -> movers-secondary.png. Correct Opportunities target absent.
Backend safety review and transactional launch remain blocked; no new run or
execution. Canonical roadmap: DASHBOARD_V2_VISUAL_ROADMAP.md. Per-screen evidence,
remaining dependencies and closeout: DASHBOARD_V2_49_VISUAL_VALIDATION.md.


## 2026-10-11 - DASH-V2-50 corrections review and watcher integration
Backend 8648366 exact SHA reviewed; 34/34 contract+sentinel tests PASS.
Freshness/identity/binding predicates accepted. Enforcement fencing NOT accepted:
enforce_abort still writes STOPPING unlocked and calls termination before owner
verification. Synthetic mocked-kill reproductions prove foreign-owner invocation
and terminal/new-lease overwrite; committed heartbeat race test is a no-op.
Full evidence and owner follow-up: DASHBOARD_V2_50_CORRECTIONS_REVIEW.md.

V2 BFF now preserves sentinel and raw evidence for both watchers. System exposes
five independent process/feed/supervisor/sentinel/mode cards and lease details.
Client expires ACTIVE at 90s, rejects invalid/future/mismatched evidence and
clears cached evidence on fetch error. This is observation, not protection proof.
116/116 frontend, type/lint/build PASS; V2 Python snapshot 496/496 PASS.
System+Overview at 1672/1366/390: 6 browser cases PASS, no errors/overflow; expanded
watcher panels and production DTOs captured. Reference fidelity remains PARTIAL.
Start/transactional launch blocked; no market run, backend edit or gate advance.
F-V2-BFF-01 and F-V2-SYSTEM-01 remain PARTIAL. Runtime source shows COMPLETED;
both leases STOPPED, displayed STALE; feed UNKNOWN, recorded evidence separate.


## 2026-10-11 - DASH-V2-51 operation boundary and pure observation
Backend 0786617 exact SHA reviewed; 48/48 targeted regressions PASS.
Locked STOPPING acquisition, final marks, actual abort owner and genuine
thread heartbeat writes accepted. Remaining operation-boundary findings:
post-claim takeover reaches simulated termination; wrong-run owned lease
reaches termination; status() can overwrite ABORTED with stale FAILED.
Independent process-owner concurrency coverage remains absent.

V2 no longer calls mutating status() for GET observation or command preflight.
Requires canonical status_readonly(); missing capability returns explicit
READ_ONLY_STATUS_REQUIRED/UNKNOWN and pauses controls. The source currently
lacks it. Recorded SQLite evidence remains available; Start still blocked.
118/118 frontend/type/lint/build and V2 Python snapshot 496/496 PASS.
Bridge execution against a synthetic active registry preserved its bytes;
canonical registry SHA-256 unchanged. No market run or backend edit.
Full audit/owner follow-up: DASHBOARD_V2_51_FENCING_REVIEW.md.
F-V2-BFF-01 and F-V2-SYSTEM-01 remain PARTIAL; safety gates unchanged.


## 2026-10-11 - DASH-V2-52 pure observation and native boundary review
Backend exact SHA 55efaa2 reviewed; canonical suite independently 826/826 PASS.
V2 bridge status_readonly verified byte-preserving; runtime observation resumes.
Recorded COMPLETED / watcher STALE / feed UNKNOWN are independent observations.
Registry state is not verified target liveness: V2 labels it Recorded process,
uses Elapsed since start, and describes readiness as a registry check.
Two remaining reproductions: native TerminateProcess FALSE accepted as True,
missing native HANDLE signatures; start kills its own child if registration wins
before parent commit. Both are hermetic, without probes or actual OS termination.
Native/start corrections remain owned by backend; full detail and follow-up in
DASHBOARD_V2_52_INTEGRATION_REVIEW.md. Start and operational gates remain blocked.
Frontend 118/118, V2 Python snapshot 496/496; type/build PASS. System/Overview at
1672/1366/390: 6 cases, no browser errors/page overflow. Visual parity PARTIAL.
F-V2-BFF-01 and F-V2-SYSTEM-01 remain PARTIAL. No new supervised run or gate advance.


## DASH-V2-53 — 2026-10-11 — research documentation checkpoint

DONE bounded documentation slice. Evaluated mover/level intent against canonical backend 55efaa2 and V2 base 066577e; registered seven PROPOSED future requirements and reconciled descriptive states, research setup families, endpoint outcomes and future trading rules. No source/UI/runtime changes. Canonical V2 snapshot regression: 496/496, exit 0, 72.304s. Visual verification: NOT APPLICABLE (documentation only). See [DASHBOARD_V2_53_RESEARCH_DOCUMENTATION.md](DASHBOARD_V2_53_RESEARCH_DOCUMENTATION.md). Backend correction task retains priority; no probes/paper/gate advancement.


## DASH-V2-54 - 2026-10-11 - backend correction review
DONE bounded audit of published b801ab0. Isolated backend suite 840/840; exact pure BFF bridge 5/5; no visual/code/runtime change. Original 0-refusal and child-kill race improved; R1 native BOOL width and R2 actual self-registration log association remain backend follow-ups. F-V2-BFF-01/F-V2-SYSTEM-01 remain PARTIAL. See DASHBOARD_V2_54_BACKEND_CORRECTIONS_REVIEW.md and design/qa/v2-54/backend-reproductions.json. No operational gate advanced.

V2-54 snapshot regression: 496/496 OK, 67.975s, exit 0; visual verification NOT APPLICABLE.


## DASH-V2-55 - 2026-10-11 - bounded correction acceptance
Published backend e317569: R1/R2 accepted with exact-source ABI/real-registration reproductions, five handoff boundaries and five pure-status bridge cases. No UI/runtime changes; visual verification NOT APPLICABLE. See DASHBOARD_V2_55_CORRECTIONS_ACCEPTANCE.md and design/qa/v2-55/backend-reproductions.json. Full suite results recorded in the acceptance report. No gate or operational authorization.

V2-55 final suites: published backend archive 850/850 OK (200.210s); V2 snapshot 496/496 OK (94.764s), both exit 0.


## DASH-V2-56 - 2026-10-11 - bounded visual refinement
Overview pulse tiles/title/action alignment; full-width Movers table and four-column rankings below, eight default rows with larger choices preserved. 118 frontend tests and 496 V2 Python snapshot tests pass; type/build pass, lint one existing warning. Before/after 39-route/width cases each, no browser errors/page overflow. Managed V2 PID 35700 -> 18520. Reference fidelity remains PARTIAL. See DASHBOARD_V2_56_VISUAL_REFINEMENT.md and design/qa/v2-56/. Backend preparation prompt is separate; no actual run/Start/gate authorization.


## DASH-V2-57 - 2026-10-11 - autonomous visual control plan
User requested dedicated visual-phase validation and automatic continuation.
Existing DASHBOARD_V2_VISUAL_ROADMAP.md is the single owned frontend control plan;
no duplicate private plan. Added phase matrix, per-round entry/exit checks,
screen fidelity vs round completion, isolated-blocker handling, user feedback
format and bounded cycle finish conditions. Token Detail reference inspected;
Next A READY for implementation, not yet visually completed. No UI/runtime change.

Verification: Python snapshot 496/496 OK, exit 0, 68.411s. See DASHBOARD_V2_57_VISUAL_CONTROL_PLAN.md. UI verification not applicable to this documentation-only round.

## DASH-V2-58 - 2026-10-11 - Token Detail visual round

Token Detail category/status/evidence/metric hierarchy and mobile composition refined. ROUND DONE; fidelity PARTIAL. Frontend 118/118, type/build pass, lint 0 errors (1 existing warning), Python snapshot 496/496; fresh 3 before / 6 after browser cases, no exceptions/overflow, expected price-series unavailable. Production V2 route http://127.0.0.1:3020/symbol/BTCUSDT. See [visual round report](DASHBOARD_V2_58_TOKEN_DETAIL_VISUAL.md). Next Opportunities composition READY; missing exact reference remains isolated. No backend change, Start or gate advance.

## DASH-V2-59 - 2026-10-11 - Research workspace visual round

Research navigation/headings/notices and mobile summary grids refined; literal rendered backslash-n removed. Bounded round DONE; reference fidelity ASSET_MISMATCH (missing dedicated asset). Frontend 118/118, type/build pass, Python snapshot 496/496; 9 before / 9 after browser cases, no exceptions/overflow. Source-unavailable observations retain honest empty state. See [research visual report](DASHBOARD_V2_59_RESEARCH_VISUAL.md). Next C/D scopes ready. Start/gates/backend unchanged.

## DASH-V2-60 - 2026-10-11 - bounded visual cycle checkpoint

Token Detail (V58), research workspace (V59), System/archives/future workspace refinements and final consistency (V60) are DONE within bounded visual scope; exact reference parity remains PARTIAL. All 13 routes / 3 widths = 39 browser cases pass, source-unavailable responses preserved; keyboard table checks pass. Frontend 118/118, types/build pass, Python V2 snapshot 496/496; lint 0 errors / 1 existing warning. Production http://127.0.0.1:3020, managed PID 34380. See [final screen matrix and evidence](DASHBOARD_V2_60_CONSISTENCY_REVIEW.md). Opportunities reference missing; contracts/engines and finer frame fidelity remain separate. Await other owner's published report for exact-SHA integration review. No backend change, Start, probe, trading or SUCCESS_GATES advancement.
