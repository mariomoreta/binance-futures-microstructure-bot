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
| Feature engine (multi-TF returns, rank, VWAP, vol, OI, flow) | `returns.py` + `universe.py` | Returns P1-04 DONE (mark-price log returns, 7 TFs); rank/VWAP/vol/OI/flow pending (P1-05…) |
| State classifier | — | NOT BUILT until P1-12, BLOCKED on P1-11 validation (`docs/MARKET_STATES.md`) |
| Persistence foundation | `persistence.py` | v2 (snapshots/observations/rejections + price_samples/return_features); sampling gate + dedicated snapshot writer |
| Dashboard | `dashboard.py` | LIVE (P1-03 + P1-04 returns section + `/api/features/returns`); staged P1-09 → P1-13 |
