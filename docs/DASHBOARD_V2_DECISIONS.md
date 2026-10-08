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
