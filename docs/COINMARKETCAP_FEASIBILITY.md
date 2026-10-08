# CoinMarketCap Feasibility

**Purpose:** determine whether CoinMarketCap (CMC) can add honest contextual
data to Dashboard V2 without displacing Binance USD-M Futures as canonical
venue data.  
**Status:** ARCHITECTURE APPROVED; INTEGRATION NOT IMPLEMENTED.  
**Evidence date:** 2026-10-07. Official documentation plus two bounded public
GET probes; no account, key, subscription, or billing action was used.

## Verified service tiers

- Keyless base: `https://pro-api.coinmarketcap.com/public-api`.
- Keyless uses GET, no signup, key, or auth header. It has a shared IP rate
  pool; CMC publishes no numeric keyless quota and instructs clients to back
  off on 429. A live probe returned HTTP 200 for the ID map and metadata, then
  HTTP 429 on a third immediate request. Therefore the sustainable keyless
  request rate is **UNKNOWN**, not inferred from this tiny sample.
- Basic is free, requires signup/key, and currently advertises 15,000 monthly
  call credits, 50 requests/minute, 60+ endpoints, one key, 60-second update
  frequency, and commercial use rights.
- CMC's published commercial terms summary says Basic through Professional
  are limited, non-exclusive, non-transferable licenses for one integrated
  product up to 100k users; standalone redistribution/resale is prohibited.
  Legal review remains required before public distribution.

Official sources: [Keyless Public API](https://coinmarketcap.com/api/documentation/pro-api-reference/keyless-public-api),
[pricing](https://coinmarketcap.com/api/pricing/), and
[FAQ](https://coinmarketcap.com/api/faq/).

## Endpoint matrix

`Credit` is the keyed-plan formula published on the endpoint page. Keyless
has no monthly credit ledger but still returns the standard envelope.

| Endpoint | Principal fields | Key? / free? | Rate / credit | Depth / update | License / provenance | Recommended use | Status |
|---|---|---|---|---|---|---|---|
| `/v1/cryptocurrency/map` | stable CMC id, name, symbol, slug, platform/contract, active state, first/last historical time | No; keyless + Basic | keyless numeric rate UNKNOWN; 0 keyed credits | mapping as needed; cache 30s | CMC reference data | identity candidate generation only; never silent ticker match | VERIFIED |
| `/v2/cryptocurrency/info` | id, logo, description, URLs, tags, platform, dates | No; keyless + Basic | 1/250 assets | static/as-needed; cache 30s | CMC metadata | profile after verified mapping | VERIFIED; live HTTP 200 |
| `/v3/cryptocurrency/quotes/latest` | aggregate price, market cap, supply, volume, changes, rank, timestamps | No; keyless + Basic | 1/250 assets + converts | latest; 60s | multi-market CMC aggregate | contextual market cap/rank; source label mandatory | VERIFIED |
| `/v3/cryptocurrency/listings/latest` | ranked active assets plus latest quotes | No; keyless + Basic | 1/250 assets + converts | latest; 60s | CMC ranking methodology | broad market-cap context, not Binance liquidity | VERIFIED |
| `/v1/cryptocurrency/categories` | categories and aggregate/category quotes | No; keyless + Basic | 1/request + 1/200 assets + converts | latest; as-needed/30s | CMC taxonomy | optional category labels | VERIFIED |
| `/v1/cryptocurrency/category` | one category and paged constituents | No; keyless + Basic | 1/250 assets + converts | latest; as-needed/30s | CMC taxonomy | optional category context | VERIFIED |
| `/v1/global-metrics/quotes/latest` | total market cap/volume, dominance and aggregate counts | No; keyless + Basic | 1/request + converts | latest; 5m | CMC aggregate | overview context | VERIFIED |
| `/v3/fear-and-greed/latest` | timestamp, value, classification | No; keyless + Basic | 1/request | latest; 15m | CMC proprietary index | clearly labeled sentiment context | VERIFIED; live probe rate-limited |
| `/v3/fear-and-greed/historical` | daily timestamp/value/classification | No; keyless + Basic | 1/request | daily values; up to 500/page; cache 15s | CMC proprietary index | historical regime context, not a signal | VERIFIED |
| `/v1/altcoin-season-index/latest` | 0-100 index, market cap, snapshot, yearly extrema | No; keyless + Basic | 1/request | latest; 15m | CMC proprietary index | overview context | VERIFIED |
| `/v1/altcoin-season-index/historical` | 7d/30d/90d points | No; keyless + Basic | 1/request | max 90d; 15m | CMC proprietary index | bounded context | VERIFIED |
| `/v3/index/cmc100-*`, `/v3/index/cmc20-*` | index value, constituents/weights; historical points | No; keyless + Basic | 1/request | 5m; historical intervals 5m/15m/daily with query bounds | CMC proprietary indices | broad benchmark context | VERIFIED |
| `/v1/cryptocurrency/trending/latest` | search-volume trending assets | Key required; Startup+ | 1/250 assets + converts | windows 24h/7d/30d; 10m | CMC ranking | defer; keyless/Basic unavailable | PAID |
| `/v1/cryptocurrency/trending/gainers-losers` | aggregate gainers/losers | Key required; Startup+ | 1/250 assets + converts | 1h/24h/7d/30d; 10m | aggregate spot markets | Binance discovery already covers venue movers | PAID / REJECTED NOW |
| `/v2/cryptocurrency/market-pairs/latest` | exchange/pair/category, reported and converted price/volume | Key required; Growth+ | 1/250 pairs + converts | latest; 1m | CMC market aggregation | unnecessary for current Futures terminal | PAID / REJECTED NOW |
| `/v2/cryptocurrency/ohlcv/historical` | daily/hourly OHLCV + market cap | Key required; Startup+ | 1/100 points + converts | Startup: intraday 1mo, daily from 2010; more on higher plans; hourly ready ~5m after hour | aggregate CMC market, not Binance perpetual | never execution/PnL; no current need because Binance history is canonical | PAID / REJECTED NOW |
| Keyless DEX endpoints incl. `/v1/k-line/candles` | contract/pool price, liquidity, transactions, security, candles | No; keyless subset | shared rate UNKNOWN; endpoint-specific credits when keyed | pool/chain-specific | CMC DEX aggregation | only after a verified chain contract maps to research need | VERIFIED BUT DEFERRED |

The standard CEX historical OHLCV endpoint is not in the 18-endpoint keyless
list and its endpoint page excludes Basic and Builder. Keyless DEX candles do
not change that conclusion.

## Request-budget policy

For a future `CMC-01` keyless metadata pilot:

- default disabled; backend only;
- at most 1 request/second and 20 requests/hour process-wide until measured;
- ID map cache 24h, metadata 7d, quotes/listings 60s, global metrics 5m,
  sentiment/indices 15m;
- exponential backoff with jitter on 429/5xx; honor `Retry-After`; circuit
  open after three consecutive failures; no retry from the WebSocket path;
- store observed status/headers and expose provider freshness, but never
  claim a numeric provider quota unless CMC publishes one;
- if a keyed plan is ever proposed, require a separate authorization for
  credentials and billing. This document does not authorize either.

## Decision

Approve only a future bounded metadata/context adapter after `CMC-00` mapping
fixtures prove identity handling. Prefer ID map + metadata first. Quotes,
rankings and indices are optional context. Reject CMC as a Binance Futures
price, liquidity, fill, PnL, or backtest source.

## Deferred decisions and dependencies

- Exact terms/legal review for the intended distribution model.
- Whether the keyless rate is stable enough for even low-frequency polling.
- Whether category/sentiment context improves research outcomes.
- A separately authorized Basic key is optional, not assumed.

## Acceptance criteria for CMC-01

Verified stable-ID mapping; fixtures for ambiguity/429/outage/stale data;
provider cache/budget telemetry; Binance-only execution-price calculations;
and no impact on MarketProbe availability or latency.
