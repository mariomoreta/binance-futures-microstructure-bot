# Token Identity Mapping

**Purpose:** prevent false joins between Binance Futures contracts and
external asset providers.  
**Status:** CONTRACT APPROVED; STORE/ADAPTER NOT IMPLEMENTED.  
**Scope:** Binance USD-M Futures ↔ CMC and optional CoinGecko identities.

## Non-negotiable rule

A ticker is a search hint, never identity. A mapping becomes usable only when
stable provider ID and, where applicable, network + contract address agree
with verified evidence. Ambiguous or insufficient mappings remain `UNKNOWN`.

## Proposed backend record

```text
AssetIdentityMapping
  binance_symbol: string                 # exact Futures contract, PK part
  binance_base_asset: string
  binance_quote_asset: string
  binance_contract_type: string
  binance_status: string
  binance_listing_at: timestamp | null
  binance_listing_source: string | null
  cmc_id: integer | null
  coingecko_id: string | null
  network: string | null
  contract_address: string | null        # normalized per network
  mapping_status: VERIFIED | AMBIGUOUS | UNKNOWN | REJECTED
  confidence: EXACT_CONTRACT | VERIFIED_NATIVE | MANUAL_REVIEW | NONE
  evidence: array<{source, observed_at, fields, reference}>
  last_validated_at: timestamp | null
  invalidated_at: timestamp | null
  notes: string | null
```

Listing time is not inferred from a CMC/CoinGecko date. Prefer Binance
contract metadata if available; otherwise use the first verified Binance
Futures kline/known historical genesis and label that provenance.

## Resolution workflow

1. Read Binance `exchangeInfo` for exact contract/base/quote/status.
2. Generate provider candidates using symbol/name only.
3. Verify CMC ID or CoinGecko ID. For tokens, require network and contract
   address when the provider exposes them. For native assets, require a
   documented native-asset match and manual-review evidence.
4. Reject duplicate-symbol candidates that cannot be disambiguated.
5. Persist evidence and timestamp. Revalidate after listings, migrations,
   redenominations, provider remaps, or a bounded TTL.
6. UI consumes only `VERIFIED`; all other states display `UNKNOWN` or
   `AMBIGUOUS`, never the highest-ranked ticker candidate.

CMC's v2 metadata explicitly returns arrays for symbol lookups because symbols
are not unique. Its ID map recommends CMC IDs and supplies platform/token
address fields. CoinGecko similarly uses coin IDs and contract endpoints.

## Coverage rules

- Recently listed assets: expect delayed or absent external coverage.
- Duplicate names/symbols: block automatic mapping.
- Renames/redenominations: create a new evidence revision; do not mutate
  historical provenance silently.
- Multi-chain tokens: mapping is to provider asset ID plus the specific
  verified contract/network evidence, not to one arbitrary chain.
- `龙虾USDT`: mapping is `UNKNOWN` until the exact Binance base asset is
  verified against a stable provider ID and contract/network evidence. This
  document makes no claim that it corresponds to any particular CMC or
  CoinGecko asset.

## API projection

`GET /api/v1/assets/{binance_symbol}/identity` (future) returns the record
above plus `source_timestamp`, `fetched_at`, `freshness`, and `quality_flags`.
404 means unknown Binance contract; 200 with nullable provider IDs means a
known contract whose external mapping is honestly unresolved.

## Acceptance criteria

Fixtures must cover exact contract match, native asset, duplicate ticker,
multi-chain token, provider disagreement, delisting, stale validation and the
Chinese-character symbol. No external metadata may render without a verified
mapping.

## Deferred decisions

Persistence schema, review UI, revalidation cadence and operator override
mechanism belong to `CMC-00`; no manual override may omit evidence/audit data.
