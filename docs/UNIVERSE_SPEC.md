# UNIVERSE_SPEC — dynamic live universe v0 (P1-12B)

Status: **IMPLEMENTED. Budgets are conservative local policy; transport
caps are UNVERIFIED assumptions (official USD-M websocket docs were not
fetchable from this environment).** Research coverage only — never trading.

## Universes

- DISCOVERY: every eligible contract from cheap public REST scans
  (exchangeInfo + 24h tickers; no flow/book/OI assumed).
- CORE: `config.symbols` (BTC/ETH/SOLUSDT) on the two canonical
  connections. Protected: never evicted by HOT rotation; a failed HOT
  promotion never touches a CORE subscription.
- HOT: ≤ `max_hot_slots` (default 3) discovery candidates with real
  deep subscriptions on managed connections.

## Lifecycle (subscription/capability — NOT P1-12A market states)

`DISCOVERY_ONLY → PROMOTION_PENDING → SUBSCRIBING → WARMING → LIVE`
(`DEGRADED` on silent streams), with `DEMOTION_PENDING → UNSUBSCRIBING →
UNKNOWN` on the way out plus `STALE`. EXPANSION must never be confused
with LIVE; no LIVE before deep data actually flows.

## Selection (explainable, pre-subscription only)

Consumes the hysteresis-filtered `select_hot` proposals (votes ≥
min_votes) — never classifier output (no circularity). Rank: |24h%|
desc, quote-volume desc, symbol asc; missing change sorts last, missing
volume after measured (never zero-filled). Promotion requires: eligible
+ fresh ticker (`ticker_close_ms` within `max_discovery_age_seconds`,
default 1800s) + free slot + stream/connection budget OK + transport
healthy. Ineligible symbols never promote; stale discovery is skipped
with a logged reason.

## Budgets (fail closed — no promotion when any would break)

Defaults: 3 HOT slots; 60 total streams; 50 streams/connection
(UNVERIFIED); 6 connections; promotion cadence = discovery interval
(600s); min dwell 1800s; demotion cooldown 3600s; demote after 2 missed
scans; ≤10 HOT reconnects/hour. Actual footprint at defaults: 4
connections, ≤32 streams (17 canonical + 15 HOT). CORE streams: 3
symbols × (bookTicker + depth + aggTrade) + 2 global array feeds.
HOT streams: 3/symbol (bookTicker + depth + aggTrade); markPrice (!arr)
and forceOrder (!arr) are global and never duplicated.

## Transport (managed connection groups)

The canonical public/market pair is never touched by HOT logic. HOT
rides `hot-public` (bookTicker + depth) + `hot-market` (aggTrade),
rebuilt from the desired set on change only (60s anti-flap guard):
cancel exactly the two managed tasks (awaited, no orphans), drain-then-
forget demoted engine state (no closed-bucket loss), admit promoted
symbols everywhere, respawn (none when desired is empty — zero extra
connections). `_connection_loop` accepts a URL callable resolved per
(re)connect, so any reconnect restores exactly the desired set; a
reconnect never implies healthy delivery (verified separately via
message flow). Partial failure (desired symbol with no streams after a
grace window) is reported via lifecycle + universe events, never
silently LIVE. Demotion: drop from desired → reconnect without it →
forget engine memory (persisted rows age out honestly) → cooldown.

## Promotion → data → readiness

Probe tracks first valid post-skew message per HOT symbol
(`PROMOTION_PENDING` → `WARMING`) and marks `LIVE` only after mark +
trade + depth all observed. Recorder buckets open on first trade;
demotion finalizes them as explicitly PARTIAL (idempotent keys, no
double-count on re-promotion; book partials discarded per policy).
Classifier P1-12A rules unchanged: warming rows hit its minimum-data
gate → UNKNOWN until sufficient; demoted symbols leave its inputs and
go STALE honestly. OI poller covers CORE + HOT (≤8 requests/round).

## Dashboard (minimal, truthful)

Overview universe table distinguishes proposals (`HOT dynamic`) from
actual subscriptions (`HOT subscribed (deep)`) plus per-symbol
lifecycle/reason and recent `hot_*` universe events. Token Detail
opens for any symbol with live rows (HOT symbols join live sets
automatically); discovery-only symbols keep the honest no-deep panel.
No redesign, no Next.js changes, CREATE_NO_WINDOW fix intact.

## Validation (2026-10-08)

- 31 unit/integration tests (selection, freshness, ranking/ties,
  missing metrics, cooldowns, dwell, CORE protection, slot/stream
  budgets, no-dup URLs, sync spawn/cancel/allow/forget, WARMING→LIVE,
  degradation, invalidation, cooldown, recorder isolation, classifier
  UNKNOWN, safety surface). Full suite 478/478.
- Controlled 300s observe-only run (temp config: 60s scans, min_votes 2;
  repo config untouched): 6 proposals → 3 promotions (OGN/MET/
  GRIFFAINUSDT), both HOT connections up, all 3 reached LIVE, 0
  demotions/failures/refusals, 0 reconnects, 0 rejects, recorder
  captured HOT buckets (24/4/3 each), classifier evaluated all 6
  symbols, safety 0/0/0, COMPLETED naturally.

## Limitations

- HOT funding-rate detector events stay CORE-configured (threshold maps
  are per-trio); HOT flow/volume math is unaffected.
- OI warms on the 60s poll cadence (slower than WS features).
- Re-promotion rebuilds strictly from fresh observations (no history
  inheritance); demoted rows persist STALE until retention caps.
- Transport caps remain UNVERIFIED — re-check against official docs when
  reachable before raising any budget.
