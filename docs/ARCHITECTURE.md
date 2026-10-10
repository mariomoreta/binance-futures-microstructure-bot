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
| Transport (2 routed WS + reconnect) | `probe.py` | Implemented + P1-14B.3 freshness watchdog (post-guard accepted-traffic accounting per stream, pure stream→connection mapping, 90 s / 300 s budgets with 120 s grace + cooldown, one-shot forced reconnect through the normal retry path, additive summary `freshness` block; LOCAL_POLICY, no aggressive loops) + P1-14B.5 diagnostic health (`classify_connection_health`: socket vs FLOWING_FRESH/STALE/SILENT/RECONNECTING/UNAVAILABLE + evidence, additive `connectionHealth` block; shared with netprobe) + P1-14B.6 host telemetry (process CPU% via os.times deltas, RSS via psapi with real-handle fix, exact per-stream received bytes; additive summary `host` block sampled on the probe-owned cadence only; NIC/system-wide UNKNOWN by design) |
| Independent transport reference | `netprobe.py` (stdlib + existing websockets dep; host-pinned read-only single connection, mirrored params, E/lag/reorder/error-class tracking, UTF-8 JSONL, bounded duration) | P1-14B.5 DONE (17 tests; bookTicker-only limitation documented: bare `/stream` path does not serve `!` arrays) + P1-14B.6 (`--base-path` allowlist {/stream,/public/stream,/market/stream} + placement warning; heartbeat summaries so total silence is observable; per-stream bytes + host sample per record; verified 2×2 placement matrix; two-instance operational reference) |
| Normalization + skew rejection | `probe.py` (`_handle_message`) | Implemented |
| Clock sync | `clock.py` | Implemented |
| Detectors (liq/funding/volume) | `detectors.py` | Implemented (hypothesis thresholds) |
| Metrics (spread, imbalance, z-score, percentile) | `metrics.py` | Implemented |
| Telemetry/distributions | `telemetry.py` | Implemented + P1-14B.6 host helpers (`process_cpu_times`, `cpu_percent_proc` pure, `process_rss_bytes` with UNKNOWN-safe contract; shared by probe + netprobe) |
| Feature engine (multi-TF returns, rank, VWAP, vol, OI, flow) | `returns.py` + `universe.py` + `momentum.py` + `flow.py` + `book.py` + `open_interest.py` + `market_structure.py` | Returns P1-04 DONE; velocity/accel/live-ranks P1-05 DONE; aggressive flow + volume baselines P1-06 DONE; order-book + OI P1-07 DONE; VWAP + realized-vol + range + structure P1-08 DONE (stateless over peer state; book resilience deferred) |
| Discovery layer (public REST scan → HOT proposal) | `discovery.py` | P1-05 DONE (exchangeInfo + 24hr tickers, filters, hysteresis selection; no WS changes) |
| Historical research store (REST bootstrap, separate DB) | `history_client.py` + `history_store.py` + `history.py` (CLI: status/fetch/verify) | P1-11B DONE (schema v1: klines / mark-klines-without-volume / OI / coverage / runs / gaps; bounded pagination + resume + idempotency + adaptive rate limit; pilot 13 series ratio 1.0; machine APIs `/api/history/status`, `/api/history/:symbol` + token coverage card) |
| Probe run control (observe-only operator surface) | `control.py` (registry `logs/probe_runtime.json`, CLI status/start/stop) + probe self-registration in `__main__` + dashboard control APIs/UI | P1-11B.1 DONE (single registry for agent/terminal/dashboard launches; PID+image+ctime identity with ctypes fallback; single-instance refusal; merged UTF-8 file logging per run; POST-only localhost mutations with nonce+Origin; header ENGINE control with polling on all pages; 6H validation preset for P1-10R mechanics — audit still required for PASS) + P1-14B.7 persistent supervision (`control supervise`: detached registry-leased watcher, documented abort rules with UNKNOWN-safe semantics, one-shot verified-PID abort with persisted reason/threshold/observed, lease takeover + failure budget, additive `supervisor` block in control status → API; never starts/restarts runs, never touches foreign PIDs) + P1-14B.8 sentinel (`control sentinel`: watches supervision liveness via lease age, enforces safe stop on stale/FAILED supervision through the canonical path, own lease + failure budget, additive `sentinel` block; flushed startup prints for launch forensics) |
| State classifier | `classifier.py` (ClassifierEngine + pure classify_symbol, rules v0.1.0 HYPOTHESIS) | P1-12A DONE (NORMAL/IGNITION/EXPANSION/EXHAUSTION/REVERSAL + UNKNOWN with evidence/validity/transitions; hysteresis + reversal confirmation; evaluated per summary over peer rows; token-page panel; spec `docs/CLASSIFIER_SPEC.md`) |
| Dynamic universe (HOT subscriptions) | `universe_manager.py` (pure selection + lifecycle) + managed `hot-public`/`hot-market` connections in `probe.py` | P1-12B DONE (3 HOT slots, fail-closed budgets, dwell/cooldown, CORE protected; engine allow/forget; overview subscribed-vs-proposed display; spec `docs/UNIVERSE_SPEC.md`; transport caps UNVERIFIED) |
| Persistence foundation | `persistence.py` | v8 (v7 + opportunity_candidates REPLACE-per-key + opportunity_events append-only ≤500 + migrations v1–v8); sampling gate + dedicated snapshot writer |
| Dashboard | `dashboard.py` + `dashboard_data.py` + `dashboard_components.py` + `dashboard_views.py` | LIVE v0.9.0 terminal (P1-09 PASS: OVERVIEW/MOVERS/SYSTEM + `/symbol/:symbol` + search + mark-price chart/CSV APIs; P1-03…P1-08 diagnostics kept under `/system`; `dashboard.py` keeps routing/health/lifecycle, views/components/data split by responsibility); P1-13A opportunity read surface + `/api/opportunities` JSON contract |

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
→ opportunity/setup engine (P1-13A V0 IMPLEMENTED: DETECTED→WATCHING→
     ACTIVE_RESEARCH→INVALIDATED/EXPIRED→UNKNOWN, research-only, no
     entry/stop/targets/confidence; full lifecycle with paper entry
     gate remains design-only for P1-13B+)
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

## Dashboard V2 parallel frontend — planned, not implemented (2026-10-07)

The current Python SSR dashboard remains the verified production surface.
Dashboard V2 is a staged parallel frontend proposal: Next.js App Router with
strict TypeScript consumes versioned Python JSON contracts through a
same-origin server-side BFF. Python remains the only market/research/control
backend and SQLite remains server-side. The browser never opens the database,
starts a second engine, or becomes a decision source.

The boundary, folders, security posture, schemas, migration stages, and
rollback gates are defined in `docs/DASHBOARD_V2_FRONTEND_ARCHITECTURE.md`,
`docs/DASHBOARD_V2_API_CONTRACTS.md`, and
`docs/DASHBOARD_V2_MIGRATION_PLAN.md`. No V2 application code exists at this
checkpoint.

## P1-11C prospective path (2026-10-07)

`	ext
MarketProbe -> validated engine state -> ResearchRecorder (bounded queue, worker thread) -> data/historical/historical.db (research_flow_10s/1m, research_book_1m)
`

Single process, single registry (logs/probe_runtime.json), single launcher family. Dashboard reads research depth via /api/research/status and studies via /api/events/*; ENGINE/FEED/RESEARCH states are reported separately and never conflated.
