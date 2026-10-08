# Dashboard V2 Codex Audit — 2026-10-07

**Purpose:** durable evidence-backed reconstruction of the Dashboard V2 audit
inputs available in this task.  
**Status:** COMPLETE FOR ARCHITECTURE; ORIGINAL PRIOR AUDIT SOURCE ABSENT.  
**Baseline:** branch `phase1/market-intelligence-dashboard`, commit
`6270be29a5444e56d4fac9e51f04d5882bc5554b`.

## Source limitation

At task start, this file and the other named V2 documents did not exist in the
repository. No original prior-audit text or four mockup files were present in
the supplied attachment. Therefore this file does not claim to reproduce a
missing artifact verbatim. It faithfully preserves the findings explicitly
named in the master task and reconciles them against current code/docs.

## Verified architecture

- Python stdlib `ThreadingHTTPServer` SSR at v0.8.0, loopback-only.
- Persistence-backed views; dashboard does not scrape DOM or feed the engine.
- Routes: Overview, Movers, Search, Symbol, System plus 24 machine/control
  endpoints inventoried in `DASHBOARD_V2_API_CONTRACTS.md`.
- Existing `control.py` is the single probe registry/manager. Mutations are
  POST-only with localhost Host/Origin, per-process nonce, fixed argv and
  forced observe mode.
- Historical DB, event studies and prospective recorder exist; Opportunities,
  state classifier, backtest and paper engines do not.

## Carried-forward findings

1. **ORCAUSDT historical-only routing gap — CONFIRMED BY CODE.** Symbol route
   knownness comes from live feature/discovery sets; historical coverage is
   rendered only after route admission. A historical-only contract can 404.
   V2 facade must union Binance-known/history-known symbols.
2. **Capability semantics — CONFIRMED.** `LIVE/WARMING/DISCOVERY ONLY/STALE/
   DEGRADED/UNKNOWN` are shared UI states; tier is orthogonal. Missing values
   remain null/`—`, never zero.
3. **Movers formatting/filtering — CONFIRMED.** Current composed rows hold raw
   numbers. P1-11A fixed per-category display-key contamination; P1-11A.1
   enforces finite sign-specific velocity membership. V2 must retain those
   invariants and format only at render time.
4. **Historical research limitations — CONFIRMED.** Binance mark vs regular
   provenance, no historical book reconstruction, bounded OI history and
   recent-only aggTrades remain explicit. Event studies are research-only and
   have resolution limits.
5. **Opportunities future-only — CONFIRMED.** No classifier/setup engine or
   validated probabilities exist. Navigation copy in existing docs is a plan,
   not a route or data product.
6. **Market Engine integration — CONFIRMED.** Existing UI/API safely controls
   the canonical manager; Next.js must proxy it without leaking nonce or
   weakening Python checks.

## Additional findings

- Current APIs are unversioned and many nested feature payloads are raw
  persistence pass-through. A typed view-model facade is needed before an
  independent frontend.
- Current search universe is compact persisted discovery/live data, not all
  exchange contracts.
- API responses do not use one universal provenance/freshness/error envelope.
- Provider data is absent today; no fictional mockup numbers are in code.
- Existing docs contain historical wording/encoding inconsistencies, but this
  task intentionally avoids broad cleanup unrelated to V2.
- P1-10R remains the current operational gate; P1-12 remains blocked.

## Recommendation

Parallel Next.js + same-origin BFF, Python backend preserved, versioned view
models first, then screen slices. CMC metadata/context is optional and must be
stable-ID mapped. No migration, provider integration or runtime change in this
architecture checkpoint.

## Acceptance evidence

See `DASHBOARD_V2_PROGRESS.md` for files/tests/checkpoint. External claims and
official sources are captured in `COINMARKETCAP_FEASIBILITY.md`,
`EXTERNAL_MARKET_DATA_EVALUATION.md` and
`DASHBOARD_V2_FRONTEND_ARCHITECTURE.md`.
