# Dashboard V2 Decisions

Append-only decision register specific to Dashboard V2. Project-wide methods
remain in `docs/DECISIONS.md`.

## 2026-10-07 — Preserve Python backend; parallel Next.js frontend

**Approved.** Python remains the sole owner of acquisition, feature engines,
discovery, historical ingestion, event studies, recorder, runtime control,
quality and SQLite. Dashboard V2 is a separate Next.js App Router + strict
TypeScript presentation/BFF layer. No engine rewrite and no browser SQLite.

## 2026-10-07 — Next.js over Vite, conditional on BFF value

**Approved for planning.** Next.js is preferred for multi-route evolution and
same-origin server proxy/security normalization. Vite remains the lower-cost
fallback if the product becomes permanently static/client-only or the BFF
cannot justify a Node runtime. No package or scaffold is authorized here.

## 2026-10-07 — Keep Python security checks; server-held nonce

**Approved.** BFF is additive defense, not replacement. Python keeps loopback,
Host/Origin/nonce, POST-only mutations and fixed argv. The nonce never reaches
browser code. No wildcard CORS or open proxy.

## 2026-10-07 — Versioned view-model API before screen migration

**Approved.** Existing endpoints remain for SSR. New `/api/v1` view models
carry schema version, provenance, timestamps, freshness, quality and stable
error/null semantics. Frontend does not infer unsupported values.

## 2026-10-07 — Binance canonical; external providers contextual

**Approved.** Binance USD-M Futures owns venue identity/prices/liquidity/
history/PnL/cost models. CMC/CoinGecko are source-labeled aggregate context.
No silent price mixing and no market-cap-as-liquidity claim.

## 2026-10-07 — Stable-ID mapping, no ticker-only join

**Approved.** External profile rendering requires verified provider ID and,
when applicable, network/contract evidence. Unknown/ambiguous stays explicit.
`龙虾USDT` is not mapped by assumption.

## 2026-10-07 — CMC first, CoinGecko fallback

**Approved for future evaluation.** A bounded CMC ID/metadata pilot is the
first candidate. CoinGecko is added only for a concrete unmet gap. Both are
backend-only, cached, budgeted, circuit-broken and outside the WS path.

## 2026-10-07 — Opportunities and universe screens are capability honest

**Approved.** Empty/blocked shells may explain dependencies. No candidates,
direction, entries, confidence, positions or PnL are fabricated. Discovery,
Watch, Hot and Live Tracked remain distinct; no mass live-depth claim.

## 2026-10-07 — TradingView Lightweight Charts allowed with attribution

**Approved for prototype, not installed.** If adopted, include Apache-2.0
materials, NOTICE attribution and a TradingView link, plus accessible text/
table fallbacks. TanStack Table is recommended for Movers, also not installed.

## Pending decisions

- Final reference-mockup measurements and asset/font choices.
- Exact `/api/v1` schema implementation language/validator.
- Whether to use TanStack Query or a smaller polling layer.
- CMC legal review and measured keyless stability.
- Any provider credentials, paid tier or public deployment.
- Python SSR retirement/cutover.

## 2026-10-07 � DASH-V2-00 slice decisions

- tsconfig jsx: react-jsx (not preserve): required so standalone vitest transforms TSX; Next build unaffected (tsc + build verified).
- vitest esolve.alias @ -> src mirrors tsconfig paths (vite does not read them).
- Token-detail route is singular /symbol/[symbol], matching the Python backend; the architecture folder plan sketch shows plural symbols/ � singular wins unless a later slice justifies otherwise.
- eslint flat config (eslint.config.mjs + eslint-config-next); 
ext lint is gone in Next 16, so the lint script is eslint src.
- Minimal icon.svg added to silence favicon 404 (only console error seen).
- No chart/table libraries installed; hand-rolled DataTable/FilterTabs suffice for the foundation.
- Ephemeral 
ext start :3000 used for render/screenshot checks only, then stopped; screenshots recorded without reference comparison (mockups absent).

## 2026-10-07 � DASH-V2-01 slice decisions

- Compact 2-demo-pill replaces large demo banners on Overview (one small RESEARCH ONLY notice retained); DEMO stays permanently visible.
- Breadth rendered as a CSS bar with text counts + aria-label (no chart library; no series impersonation).
- Metric cards carry unit/period/source/freshness/unavailable inline (BFF-forward MetricPoint shape).
- ExtremeMoveWatch Research column links to the symbol page (investigation entry, not a signal).
- Movers snapshot capped at 8 rows with a Full-movers link; full table stays on /movers.
- Preview server renewal verified old-PID identity (31648) before stop; new PID 28552 on the same port/host; Python processes never touched.

## 2026-10-07 - DASH-V2-02 slice decisions

- Keep Movers fully isolated on centralized DEMO fixtures; no BFF, provider or Binance request in this slice.
- Research-interest cutoffs are named fixture criteria for exercising UI states, never validated economic thresholds or signal rules.
- Sort raw values only; stable ties; missing/non-finite values remain last in both directions; zero is observed but neither gainer nor loser.
- Rank panels use the current filtered dataset and state that scope explicitly.
- Bound the table to 8 rendered rows per page and confine narrow-screen overflow to its wrapper.
- Compose the dashboard directly in `app/movers/page.tsx`; no route templates (the staged root CSS-hack suppressor and children-ignoring movers override were removed during recovery). Shell banner replaced by a compact demo strip in AppShell (small shared correction, Overview otherwise untouched).

## 2026-10-10 — DASH-V2-48 bounded System composition

Keep actual runtime states visible; long supervisor/control details use native
disclosure. Archive measurements separately from current health. Replace
duplicate placeholders with one explicit screen-integration list. Preserve
shared top navigation in this slice; omit unsupported charts/performance
figures from the reference. These deliberate departures leave parity PARTIAL.


## 2026-10-10 — DASH-V2-49 common terminal frame

Use the approved sidebar composition for the shared desktop frame and a mobile
menu with Escape recovery. This supersedes DASH-V2-18's horizontal common frame;
Movers' horizontal target differs deliberately for cross-screen consistency.
Use real, disabled/unavailable future-workspace compositions without fabricated
results or graph series. Correct the two misnamed PNGs by byte-preserving rename;
keep originals in Git history and declare Opportunities target missing.
Operational integration and reference parity remain separate acceptance criteria.


## 2026-10-11 - DASH-V2-50 observation-only supervision display
Preserve raw canonical watcher labels and raw lifecycle evidence separately.
The client may downgrade/expire an ACTIVE observation, never certify continuing
OS liveness or protection. Expose sentinel independently from supervisor.
Use the documented 90s display bound and explicit UTC observation time. Keep
Start disabled until canonical transactional launch and enforcement ownership
are independently verified. Read-only integration does not advance safety gates.


## 2026-10-11 - DASH-V2-51 pure runtime observation
GET must not cause lifecycle reconciliation. Require canonical status_readonly()
and explicitly pause observation when absent; never call legacy status() as
fallback or create a second lifecycle manager. Command preflight uses the same
boundary. Recorded evidence remains independent of current runtime availability.
This supersedes DASH-V2-50's direct status() bridge, whose side effect was
confirmed by the owner and reproduced. Start and operational gates stay blocked.


## 2026-10-11 - DASH-V2-52 recorded process semantics
Accept audited canonical status_readonly for observation without lifecycle writes.
Its process state is a registry projection, not a target-process liveness check.
Label it Recorded process, elapsed wall time as Elapsed since start, and readiness
as a registry check. Persisted transport provenance does not certify OS liveness.
Never infer present health from terminal history. Native termination/start ordering
remain owner corrections; no Start enablement or supervised-run authorization.


## 2026-10-11 - DASH-V2-50 observation-only supervision display
Preserve raw canonical watcher labels and raw lifecycle evidence separately.
The client may downgrade/expire an ACTIVE observation, never certify continuing
OS liveness or protection. Expose sentinel independently from supervisor.
Use the documented 90s display bound and explicit UTC observation time. Keep
Start disabled until canonical transactional launch and enforcement ownership
are independently verified. Read-only integration does not advance safety gates.


## 2026-10-11 - DASH-V2-51 pure runtime observation
GET must not cause lifecycle reconciliation. Require canonical status_readonly()
and explicitly pause observation when absent; never call legacy status() as
fallback or create a second lifecycle manager. Command preflight uses the same
boundary. Recorded evidence remains independent of current runtime availability.
This supersedes DASH-V2-50's direct status() bridge, whose side effect was
confirmed by the owner and reproduced. Start and operational gates stay blocked.


## 2026-10-11 - DASH-V2-52 recorded process semantics
Accept audited canonical status_readonly for observation without lifecycle writes.
Its process state is a registry projection, not a target-process liveness check.
Label it Recorded process, elapsed wall time as Elapsed since start, and readiness
as a registry check. Persisted transport provenance does not certify OS liveness.
Never infer present health from terminal history. Native termination/start ordering
remain owner corrections; no Start enablement or supervised-run authorization.


## 2026-10-11 — DASH-V2-53 proposed research presentation

Record F-V2-RESEARCH-01 as PROPOSED / NOT IMPLEMENTED. Canonical backend owns candidate classification, level/strategy definitions and future risk/position logic. V2 projects source/time/quality/coverage and explicit unavailable fields; it never synthesizes trade side, entry, stops, targets or probability from visual badges. ACTIVE_RESEARCH is not a fill. Follow [MOVER_LEVEL_STRATEGY_RESEARCH.md](MOVER_LEVEL_STRATEGY_RESEARCH.md). This slice is documentation only; no screen/code/API change, no Start activation and no new execution authorization.


## 2026-10-11 - DASH-V2-54 bounded correction acceptance
Accept published b801ab0 fixes for original zero-result propagation and same-child survival; retain R1 BOOL marshalling and R2 genuine self-registration log-association follow-ups. Current read-only V2 bridge needs no compatibility change. Describe C1 as bounded shared-start/effective writes/current-window timestamp coverage, not strict monotonic advancement or longevity. No Start/run/gate permission. See DASHBOARD_V2_54_BACKEND_CORRECTIONS_REVIEW.md.


## 2026-10-11 - DASH-V2-55 bounded correction acceptance
Accept R1 Windows BOOL marshalling and R2 child-first log association on e317569 based on exact-source deterministic evidence. Preserve separate recorded-process/read-only semantics and Start restriction. A successful start response with unconfirmed log association is not proof of protection. C1 claims remain bounded. No run/gate permission or strategy implementation approval. See DASHBOARD_V2_55_CORRECTIONS_ACCEPTANCE.md.


## 2026-10-11 - DASH-V2-56 reference composition refinement
Restore full-width Movers table with ranking boards below instead of the old side rail that hid desktop columns. Eight default rows match reference density; preserve selectable 16/32. Compact existing Overview pulse measurements as tiles; preserve content/fixture labels and native table markup. No new market values, graphs, probabilities or trading rules. Overall visual status PARTIAL. Backend supervised-launch preparation remains disabled and separate, per DASHBOARD_V2_56_BACKEND_HANDOFF.md.


## 2026-10-11 - DASH-V2-57 autonomous visual rounds
User authorizes V2 frontend agent to validate and advance ready visual rounds
during the active cycle without repeated continue prompts. Use existing visual
roadmap as the single control plan; keep backend/operational gates separate.
Bounded round completion and overall design fidelity are separate verdicts.
Missing assets/API capabilities block only dependent requirements; preserve
truthful unavailable states and continue independent work. Stop on user steering
to stop, resolved cycle completion or unisolatable regression/ownership/scope
blocker. No background execution or new market/run/Start authority.

## 2026-10-11 - DASH-V2-58 visual state neutrality
Category controls remain descriptive and visually neutral while classifier state is UNKNOWN. Approved-reference ornamental price curves are omitted without a verified series. Token Detail styling preserves source-specific fixture and chart provenance; no classifier or operational capability inferred.

## 2026-10-11 - DASH-V2-59 reference dependency isolation
Missing Opportunities reference blocks exact design fidelity, not independently authorized navigation/readability improvements. Separate route modes and source warnings remain visible; no live observations invented to cover unavailable backend.

## 2026-10-11 - DASH-V2-60 bounded visual cycle
Named focusable scrolling regions preserve table access on narrow screens. Compact recorded coverage and neutral future icons improve hierarchy without creating observations or capabilities. The A/B/C/D bounded composition cycle and final route audit can be DONE while exact fidelity is PARTIAL and contracts/assets remain unavailable. Backend launch/report review stays a separate exact-SHA task; no gate or run authorization inferred.


## DASH-V2-61 - 2026-10-11 - withhold dormant launch acceptance

The newly added disabled engine at backend da231b9 has reproduced ownership, revalidation, command, time-budget and uncertainty discrepancies. Keep Start disabled and withhold integration; accepted prior BOOL/evidence-handoff fixes remain closed. Canonical 873/873 plus V2 496/496 pass but do not establish new launch correctness. Follow DASHBOARD_V2_61_SUPERVISED_LAUNCH_REVIEW.md and bounded backend handoff; no operational or strategy authorization.


## DASH-V2-62 - 2026-10-11 - direct bounded backend correction

The user authorized direct correction on the backend branch. Isolated c635938 resolves the V2-61 R1-R5/C1-C2 request in disabled preparation; 902 canonical and 52 focused tests pass with published code checksum checked. V2-61 handoff is historical; no repetition required. Start and runtime code remain unchanged. Enabled capability, actual watcher startup association/real OS behavior and longevity remain deferred. See DASHBOARD_V2_62_BACKEND_CORRECTIONS_ACCEPTANCE.md.



## DASH-V2-63 — 2026-10-11 — canonical presentation migration
User authorized proceeding with V2 data migration and keeping Python/SQLite authoritative. Decided: main screens replace fixtures with read-only canonical snapshots; no DB copying, collector duplication or operational enablement. Independent source timestamps are mandatory; historic fresh/live flags are not present protection/health.
BFF price-series is schema 2 (historical hour anchored to last retained sample). Discovery tops remain a selected subset; per-row price source and independent feature date are retained. Server-rendered read metadata updates with visible-tab polling, which does not create observations.
Correct misleading legacy UI filter names: positive/negative Flow were velocity/acceleration predicates, now upward/downward acceleration; Exhaustion research predicate was extreme gainers, now labelled extreme gainers. Threshold formulas unchanged and remain descriptive hypotheses.
Main candidates table bounded to 12/page with visible-page evidence; tiny nonzero observations use scientific notation. Full legacy cutover, current liveness, timelines and supervised launches remain separate gates.

## DASH-V2-65 - 2026-10-11
Retained-record search is not an exchange universe or live subscription guarantee; parameterized submitted lookup bounded to 50 output symbols. Saved token projections carry independent family dates and recorded integrity/warmup; no new formulas. ASCII identity boundary stays explicit, coordinated expansion pending.

## DASH-V2-66 - 2026-10-11
Price production model v3 uses explicit historical ranges, last retained valid sample anchor, 10000 raw read budget + overflow sentinel, 1200 actual displayed/exported samples, preserved raw-gap evidence and unverified coverage. Download is a new same-parameter read, not a frozen prior response.
