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

## REST (minimal)

- `GET /fapi/v1/time` — clock sync only (5 samples, midpoint, median offset/RTT).
- Future Phase 1 candidates (public only): exchangeInfo (symbol universe),
  open-interest endpoint, funding history, klines for multi-timeframe returns
  bootstrap. Each addition needs a task in `docs/TASK_QUEUE.md` first.

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
