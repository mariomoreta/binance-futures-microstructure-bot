# External Market Data Evaluation

**Purpose:** select only external providers that add useful, verifiable and
legally usable context at acceptable cost and maintenance burden.  
**Status:** CMC METADATA PILOT RECOMMENDED LATER; COINGECKO FALLBACK DEFERRED;
NO ADAPTER IMPLEMENTED.  
**Evidence date:** 2026-10-07.

## Canonical-source policy

Binance USD-M Futures remains authoritative for contract identity/status,
mark price, trades, aggressive flow, book, OI, funding, Futures klines,
historical venue data, and future cost/fill/latency models. External provider
prices are aggregate context. They must carry a visible source and must never
feed Binance paper PnL, fills, liquidity claims, or execution decisions.

## Provider comparison

| Dimension | Binance | CoinMarketCap | CoinGecko / GeckoTerminal |
|---|---|---|---|
| Primary value | target-venue microstructure and history | stable IDs, metadata, rankings, proprietary broad indices | alternate stable IDs, metadata, broad market/trending and keyless history/DEX context |
| Keyless | public venue endpoints | 18 Standard + 17 DEX curated endpoints | 50+ market + 20 onchain endpoints |
| Keyless rate | endpoint-specific Binance limits | shared IP pool; numeric limit UNKNOWN | dynamic ~10–30/min; GeckoTerminal ~10/min |
| Free keyed tier | not applicable to public endpoints | Basic: 15k credits/mo, 50/min | Demo: 10k credits/mo, 100/min, 60s+ freshness |
| Free historical | canonical Futures klines; bounded OI/aggTrade realities documented | indices/sentiment keyless; standard CEX OHLCV paid Startup+ | market chart/OHLC keyless; Demo lists daily/hourly up to 1y and 5m 1d |
| License | Binance terms require separate review | Basic commercial integration allowed with restrictions; no standalone resale | Demo attribution required; commercial license begins on paid plans per pricing table |
| Adopt now? | yes, already canonical | future metadata/context pilot | no; fallback only if a concrete CMC/Binance gap justifies it |

Official CoinGecko sources: [keyless API](https://docs.coingecko.com/docs/keyless-public-api),
[Demo endpoint overview](https://docs.coingecko.com/demo/reference/endpoint-overview),
and [pricing](https://www.coingecko.com/en/api/pricing).

## Provider-selection decision

1. Do not add both aggregators by default.
2. Prefer CMC for `CMC-00/01` because its stable ID map, metadata and
   proprietary indices match the immediate Dashboard V2 context requirement.
3. Keep CoinGecko as a documented fallback when it uniquely resolves an
   identity, provides legally acceptable history CMC cannot provide at the
   approved tier, or supplies a required DEX/network view.
4. A provider comparison must use the same timestamp/currency and preserve
   distinct fields; it must not average provider prices into a pseudo-venue
   price.

## Backend-only adapter proposal

```text
src/microstructure_probe/external_data/
  __init__.py
  models.py              # value + source + observed/fetched timestamps
  provider.py            # interface and typed provider errors
  identity.py            # stable-ID mapping and ambiguity workflow
  cache.py               # TTL/freshness, no SQLite access from browser
  budget.py              # request budget, Retry-After, circuit breaker
  coinmarketcap.py        # optional CMC implementation
  coingecko.py            # only if separately approved
```

This is a future proposal, not present code. External calls run outside the
WebSocket critical path and outside the probe's feature calculations.

Every normalized value carries:

```text
value | provider | provider_asset_id | provider_endpoint | source_timestamp
fetched_at | expires_at | freshness(FRESH|STALE|EXPIRED|UNKNOWN)
quality_flags[] | license_class | raw_version
```

Provider outage behavior: serve last cache only while within its explicit
stale allowance, mark it `STALE`, then return unavailable/null. Never block,
restart or degrade MarketProbe; never fail over one price into another source
without changing provenance.

## Suggested TTLs

Identity map 24h; static metadata 7d; categories 24h; latest quotes/listings
60s; global metrics 5m; sentiment/indices 15m. Contract mapping validation
30d or immediately after a detected listing/identity change.

## Dependencies and next action

`TOKEN_IDENTITY_MAPPING.md` and `COINMARKETCAP_FEASIBILITY.md` are binding.
Next authorized provider task is documentation/test-fixture work in `CMC-00`,
not network integration. Credentials, subscriptions and paid data require
separate human authorization.
