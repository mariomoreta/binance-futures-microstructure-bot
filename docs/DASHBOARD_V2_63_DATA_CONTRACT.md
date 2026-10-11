# Canonical persisted data contracts — DASH-V2-63
Date: 2026-10-11. Implemented read-only presentation contract; no operational gate.

## Source boundary
Next.js node runtime reads C:/proyectos/binance-futures-microstructure-bot/data/microprobe.db with DatabaseSync readOnly:true. Missing DB is not created. Reads close their connection; main market snapshot uses one read transaction. Allowed feature tables are literal server constants. SQLite and original Python code/data are not migrated or copied.

## Market snapshot v1
GET /api/v1/market-snapshot returns schema_version:1, source:PERSISTED_SQLITE_READONLY, available, readAt, discoveryAsOf, eligibleCount, rows, counts and latestSampleAsOf. Features maps remain server-side.
Success is HTTP 200; unreadable source is 503. readAt is response read time, not observation time.
Rows carry priceSource/observedAt (price), discoveryAsOf (24h context), featureAsOf (velocity/acceleration). Numbers are finite or null. Unsupported/malformed/future timestamps do not become fresh. Captured sample_age_ms and validity.fresh are not current health.
Price selection uses the newest valid observed price among discovery and stored returns, preserving its source; discovery 24h measures remain discovery context. No synchronized-sample claim.
Capability is STALE after 300s, otherwise UNKNOWN: recency alone does not certify LIVE. subscribed is a legacy field here denoting retained deep evidence only; UI labels it accordingly. Tier is recorded coverage, not verified present subscriptions.
Rows are bounded to 500 retained symbols; discovery tops to 50 per group. eligibleCount is the saved scan's eligible population, not the retained row count. Broad-market activity/context unavailable from these sources stays null.

## Research adapters
/api/v1/opportunities now reads opportunity_candidates directly, source:persisted-sqlite-readonly; schema_version:"1", existing normalized shape. Limit 200. Future observations rejected without former 60s tolerance; saved lifecycle/ranking are not current setups.
/api/v1/prospective reads canonical historical rows and counts, source:persisted-sqlite-readonly, schema_version:9, HISTORICAL_ONLY. Latest outcomes limit 50. Process lifetime counters stay null.
/api/v1/live-movers retains its observational shape with source:persisted-sqlite-readonly and independent row dates. Alignment/freshness UNVERIFIED. All three routes are independent of the old HTTP/HTML dashboard.

## Price series schema 2
/api/v1/price-series/{symbol} keeps symbol/source:markPrice/range:1h/points/status/note and increments schema_version to 2 because the window anchor changes. Adds window_anchor:LAST_RETAINED_SAMPLE and read_at. generated_at is last valid sample time.
Read at most 600 saved buckets; normalize to the historical hour ending at the last valid retained sample. Reject invalid/future/negative prices. Never imply this is the current hour. Plot x by actual timestamp, begin a new segment across gaps over 60s; no filled gaps or fabricated series. Old pure normalizePriceSeries remains v1 for its existing current-window contract.

## Token feature presentation
Python's stored state/evidence/version and previous state are displayed with evaluationAsOf. No browser classification.
Fractional returns, OI delta_pct and realized volatility convert once to %. VWAP displacement_pct is already %. Spread remains bps; aggressive delta remains USDT; momentum /s and /s². Very small nonzero measures use scientific notation rather than rounding to zero.
Unknown token has null prices/metrics and UNKNOWN state; no default BTC fixture.

## Refresh
Read-only poll every 15s while visible, no overlap; 5s fetch timeout, exponential failure retry up to 60s, abort/listener/timer cleanup. Visibility resumes promptly. API client views clear old success on failure. Server-rendered screens retain dated evidence and visibly report polling failure; their source dates never advance merely from readAt.
Manual filters/selection remain client state across server refresh. Main candidate table uses 12 rows/page and inspector stays on visible candidates.

## Deliberate non-parity
No new collector, depth reconstruction, live liveness check, calibrated signals, economic validation, study mapping, timeline engine, external provider or operation is introduced. Missing full legacy parity remains tracked; old SSR retirement is not accepted.
