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
