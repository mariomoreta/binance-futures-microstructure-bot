# MARKET_DATA

Observe-only public sources. No private/account endpoints. Ever (without
explicit human authorization).

## WebSocket (live)

Routed endpoints (`probe.py::build_stream_urls`, base `wss://fstream.binance.com`):

| Endpoint | Streams | Cadence | Notes |
|---|---|---|---|
| `/public` | `{sym}@bookTicker` | event | Best bid/ask per symbol; spread + top-of-book |
| `/public` | `{sym}@depth20@100ms` | 100 ms | 20-level book; imbalance, sequence gaps via `pu`/`u` |
| `/market` | `{sym}@aggTrade` | event | Price/qty/time; volume buckets, flow proxy |
| `/market` | `!markPrice@arr@1s` | 1 s | Mark price + funding rate per symbol |
| `/market` | `!forceOrder@arr` | event | Liquidations only; silence is normal, NOT stale |

Current symbols: BTCUSDT, ETHUSDT, SOLUSDT. Universe expansion (full Futures
gainer/loser coverage) is a Phase 1 task — required for ranking features.

## aggTrade payload semantics (verified P1-06, 2026-10-07)

Primary source: current official USD-M Futures docs ("Aggregate Trade
Streams", copyright 2026) + live WS/REST payloads captured from
`fstream.binance.com` / `fapi.binance.com` in this environment.

- Aggregation: fills with the SAME price and SAME taking side, pushed every
  100ms. Only market trades are aggregated — insurance-fund and ADL trades
  are excluded.
- Fields (WS `data` object): `e`="aggTrade", `E` event time, `s` symbol,
  `a` aggregate trade ID, `p` price, `q` quantity, `nq` normal quantity,
  `f` first trade ID, `l` last trade ID, `T` trade time, `m` buyer-is-maker,
  `st` symbol type (1 = UM after CM migration; observed live `st: 1`).
- `m` ("Is the buyer the market maker?"): `true` → buyer is maker, so the
  aggressive (taker) side is SELL; `false` → buyer is taker, aggressive BUY.
  The maker side is never the aggressor.
- `q` = base quantity WITH all market trades INCLUDING RPI fills;
  `nq` = normal quantity WITHOUT RPI fills (observed live, usually `nq=q`).
  Per docs, RPI orders are aggregated into `q` without distinguishing tags.
  Flow totals use `q`; `rpi_qty = q − nq` is tracked for transparency when
  `nq` is present and sane.
- Ordering/bucketing key is `E` (event time); `T` is trade time. Observed
  live E−T deltas were ~150–350ms. Skew-guard semantics unchanged
  (|received − E| > 5000ms → reject).
- One 100ms push carries several distinct aggregates with identical `E`;
  the stream never redelivers, so same-E messages are new volume.
  The P1-06 engine accepts them in arrival order (strictly-older `E` is
  late-dropped, never revises history).

## Depth stream semantics (verified P1-07, 2026-10-08)

Primary source: current official USD-M Futures docs (Partial Book Depth
Streams page + catalog schema, copyright 2026) + live WS captures from
`fstream.binance.com` in this environment.

- `{symbol}@depth20@100ms` pushes a FULL top-20 snapshot every 100ms
  (not diffs). Valid levels are 5/10/20; `/public` endpoint.
- Fields: `e`="depthUpdate", `E` event time, `T` transaction time,
  `s` symbol, `ps` pair symbol, `U` first update ID in event, `u` final
  update ID, `pu` previous final update ID (continuity: `pu` must equal
  the last seen `u`), `b`/`a` bid/ask levels as [price, qty] strings,
  `st` symbol type (1 = UM; observed live `st: 1`).
- Live continuity confirmed: consecutive pushes chain `pu == last u`.
  A mismatch means intermediate snapshots were missed (gap) — the
  current push is still a complete picture.
- After CM migration the payload also carries `ps` (observed live).

## Open Interest endpoints (verified P1-07, 2026-10-08)

Primary source: current official USD-M Futures market-data REST docs
(copyright 2026) + live responses from `fapi.binance.com`.

- `GET /fapi/v1/openInterest?symbol=<SYM>` — present OI. Public, no key.
  Response: `{"symbol", "openInterest" (base-asset units, string),
  "time" (exchange ms)}`. Verified live (BTCUSDT → 95643.451 base).
  Request weight 1 (legacy page; current page excerpt omits it — our
  cadence of 3 req/min is negligible under the 1000 req/5min IP limit
  either way).
- `GET /futures/data/openInterestHist` — OI statistics history
  (periods 5m/15m/30m/1h/2h/4h/6h/12h/1d, default limit 30, max 500,
  latest 1 month). Evaluated and deliberately DEFERRED in P1-07
  (single-provenance polled history; see `docs/DECISIONS.md`).
- Futures historical-data note: third-party collectors poll the same
  REST OI endpoint about every 6s per instrument — our 60s cadence is
  conservative by comparison.

## P1-08 source reuse (verified 2026-10-09 — no new endpoints)

VWAP, realized volatility, range, and structure introduce NO new data
source: VWAP reads P1-06 flow aggregates (`notional/base`, same
pre-sampling provenance); volatility/range/structure read the P1-04 10s
mark-price buckets (persisted `price_samples`, ~25.5h coverage — a 1h
volatility horizon fits with margin); reference price is P1-04
`current_price`. aggTrade price/qty, mark-price, and depth semantics are
the P1-06/P1-07 verified ones above. No kline endpoint, no bootstrap,
no new dependency was necessary — documented here instead of added.

## REST (public only — verified live 2026-10-06)

- `GET /fapi/v1/time` — clock sync only (5 samples, midpoint, median offset/RTT).
- `GET /fapi/v1/exchangeInfo` — P1-05 discovery: contract status/type/quote
  asset per symbol (live: 924 symbols; TRADING 789; PERPETUAL 703).
- `GET /fapi/v1/ticker/24hr` — P1-05 discovery: lastPrice, priceChangePercent,
  quoteVolume, count per symbol (live: 789 rows). No key, ~15s timeout,
  failures logged and never break the probe.
- (Official docs site was unfetchable from this environment; endpoint paths
  match the documented USD-M Futures market-data REST API on the same host
  family as the existing clock sync. Behavior verified against live responses
  instead — shapes recorded in `docs/DECISIONS.md`.)

## Event-driven stream semantics (finalized P1-05)

- `!forceOrder@arr` publishes only on liquidations: silence is normal. It is
  NEVER listed as missing and NEVER stale; it appears under silent streams
  with that semantic. Probe enforces this in `build_summary` (missing set
  excludes event-driven streams); dashboard health does not penalize it.

## Timestamp semantics (audited, Phase 1B)

- `E` = event time. `T` = trade/transaction time for aggTrade, bookTicker,
  depth, forceOrder (`o.T`).
- markPrice `T` = next funding time — NOT a latency timestamp.
- `rawEventLagMs = localReceive - E`; corrected variant applies clock offset.
- Messages beyond `max_event_clock_skew_ms` (5000 ms) are discarded + counted.
- Legacy global clamped lag retained, labeled legacy — not a gate metric.

## Quality signals (already emitted in summaries)

Active/missing/silent/stale streams (staleness only on cadenced streams),
per-stream message counts, max inter-message silence, depth sequence gaps,
timestamp rejections, parse/payload/websocket errors, reconnects, per-endpoint
uptime %, latency + processing distributions, detector near-miss/warm-up.
