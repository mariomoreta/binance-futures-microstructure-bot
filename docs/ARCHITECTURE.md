# ARCHITECTURE

## Canonical pipeline (Phase 1–2)

```text
Binance public market data (WS: bookTicker, depth20@100ms, aggTrade,
                             markPrice/funding, forceOrder; REST: server time)
  → normalization (envelope parse, symbol filter, timestamp semantics E vs T,
                   clock-skew rejection, sequence tracking)
  → feature engine (returns, velocity, rank, volume, flow, book, OI, funding,
                    volatility, VWAP, structure, liquidations)
  → persistence foundation (Phase 1, P1-02: local observe-only store feeding
                    the dashboard; full snapshots + outcomes are Phase 2)
  → market-state / signal engine (NORMAL/IGNITION/EXPANSION/EXHAUSTION/REVERSAL,
                    Phase 1 P1-12 — only after raw-feature validation P1-11)
```

Persistence feeds three consumers: **dashboard** (visualization only),
**research** (statistics/discovery), and later **paper trading** (Phase 4).

## Later pipeline (Phase 4–5)

```text
signal engine → position manager → risk engine → execution engine
```

- Entry discovery and position management are separate engines.
- Risk engine can never be bypassed by signal or position engines.
- Execution engine does not exist yet and requires explicit human authorization.

## Hard boundaries

- Dashboard is a visualization/control surface. The trading engine must NEVER
  read decisions from frontend-rendered state (see `docs/DASHBOARD_SPEC.md`).
- No private endpoints, keys, signing, or order paths anywhere in the codebase.
  Static test `test_source_contains_no_order_or_authenticated_client_paths`
  guards this.
- Phase 1 persistence foundation (P1-02) is local and observe-only and exists
  to feed the dashboard progressively. Full event snapshots + forward outcomes
  belong to Phase 2 (`docs/EVENT_LABELING.md`). No trading data, keys, or
  private endpoints in either phase without explicit authorization.

## Current implementation map

| Layer | File | Status |
|---|---|---|
| Transport (2 routed WS + reconnect) | `probe.py` | Implemented |
| Normalization + skew rejection | `probe.py` (`_handle_message`) | Implemented |
| Clock sync | `clock.py` | Implemented |
| Detectors (liq/funding/volume) | `detectors.py` | Implemented (hypothesis thresholds) |
| Metrics (spread, imbalance, z-score, percentile) | `metrics.py` | Implemented |
| Telemetry/distributions | `telemetry.py` | Implemented |
| Feature engine (multi-TF returns, rank, VWAP, vol, OI, flow) | `returns.py` + `universe.py` + `momentum.py` + `flow.py` + `book.py` + `open_interest.py` + `market_structure.py` | Returns P1-04 DONE; velocity/accel/live-ranks P1-05 DONE; aggressive flow + volume baselines P1-06 DONE; order-book + OI P1-07 DONE; VWAP + realized-vol + range + structure P1-08 DONE (stateless over peer state; book resilience deferred) |
| Discovery layer (public REST scan → HOT proposal) | `discovery.py` | P1-05 DONE (exchangeInfo + 24hr tickers, filters, hysteresis selection; no WS changes) |
| Historical research store (REST bootstrap, separate DB) | `history_client.py` + `history_store.py` + `history.py` (CLI: status/fetch/verify) | P1-11B DONE (schema v1: klines / mark-klines-without-volume / OI / coverage / runs / gaps; bounded pagination + resume + idempotency + adaptive rate limit; pilot 13 series ratio 1.0; machine APIs `/api/history/status`, `/api/history/:symbol` + token coverage card) |
| State classifier | — | NOT BUILT until P1-12, BLOCKED on P1-11 validation (`docs/MARKET_STATES.md`) |
| Persistence foundation | `persistence.py` | v6 (v5 + structure_features REPLACE-per-symbol, tested migrations); sampling gate + dedicated snapshot writer |
| Dashboard | `dashboard.py` + `dashboard_data.py` + `dashboard_components.py` + `dashboard_views.py` | LIVE v0.8.0 terminal (P1-09 PASS: OVERVIEW/MOVERS/SYSTEM + `/symbol/:symbol` + search + mark-price chart/CSV APIs; P1-03…P1-08 diagnostics kept under `/system`; `dashboard.py` keeps routing/health/lifecycle, views/components/data split by responsibility); staged P1-13 |

## Subscription posture (P1-05)

Only CORE symbols are subscribed to websocket streams. The HOT set is
computed from cheap REST scans and exposed (dashboard/API/logs) but NOT
subscribed: integrating dynamic stream rebuild on HOT change is the next
explicit step (owned by P1-09 planning, requires P1-01R transport headroom).
No live features are ever shown for unsubscribed symbols.

## Future research pipeline (P1-11B → P1-16, design only — NOT BUILT)

```text
history (P1-11B multi-resolution REST bootstrap: 1m 30–90d, 5m/15m 6–12mo,
         1h 1–2y, 4h/1d full contract life; Binance USD-M docs verified first)
  → event studies (P1-11C: 1m/3m/5m/15m/30m/1h outcomes + MFE/MAE/time-to-MFE/
                   time-to-MAE/invalidation, no lookahead in event formation)
  → validated ≥6h soak re-run (P1-10R, gate still closed after P1-10 FAIL)
  → market-state classifier (P1-12) → dynamic live universe (P1-12B)
  → opportunity/setup engine (P1-13A: DISCOVERED→WATCH→DEVELOPING→CONFIRMED→
     PAPER ENTRY→HOLD→DETERIORATING→INVALIDATED/EXIT with direction,
     historical confidence, sample size, entry zone, stop, targets, horizon,
     reasons, risks)
  → professional UX (P1-13B) → historical backtester (P1-14, replay without
     future leakage) → forward paper trading (P1-15, simulated live entry)
  → paper portfolio / dynamic exit (P1-16)
```

Forward/paper simulation must eventually account for spread, fees,
slippage, latency, funding where relevant, entry price, stop, target, and
dynamic exit. No real orders at any stage without explicit human
authorization. Detail: `docs/SIGNAL_RESEARCH_PLAN.md` (setups, BTC
context, exhaustion/absorption) and `docs/HISTORICAL_RESEARCH_PLAN.md`
(resolutions, event studies).
