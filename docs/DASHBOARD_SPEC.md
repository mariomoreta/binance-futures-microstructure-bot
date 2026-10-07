# DASHBOARD_SPEC

A dedicated Binance dashboard is mandatory and belongs only to this project
(`C:\proyectos\binance-futures-microstructure-bot`). It must not reuse or
interfere with the Solana/Arbitrum dashboards or ports.

It is a visualization/control surface. The trading engine must NEVER read
decisions from frontend-rendered state.

## Staged delivery (binding order)

### Stage 1 — P1-03 MINIMAL DASHBOARD, first visible here — IMPLEMENTED (PASS)

Stack: stdlib only (`src/microstructure_probe/dashboard.py`, v0.3.0).

Routes: `/overview`, `/system`, plus `/api/health` and `/api/snapshot`
(machine-readable latest snapshot for P1-04 consumers).

Must expose: connection health, stream health, message rates, latency p50/p95,
stale symbols, sequence gaps, reconnects, last update, runtime duration —
plus the safety banner (`BOT_MODE`, keys=0, orders=0). All present and
live-verified; detector counts are labeled telemetry, never signals; no
buttons, controls, or account data.

Health model (display heuristics): `ok` / `degraded` (stale streams, any
reconnects, retained rejection rate >50%) / `stale` (snapshot age >120s) /
`unknown` (no snapshot). Chips shown as HEALTHY / DEGRADED / STALE / UNKNOWN.

Live instance: http://127.0.0.1:8091 (PID in `logs/dashboard.pid`).
CLI: `python -m microstructure_probe.dashboard start|stop|restart|status|
serve|pick-port` (repo root, `PYTHONPATH=src` unless installed).

### P1-04 progressive visibility — IMPLEMENTED (PASS)

/overview gained a read-only **Symbol Returns** section (per active symbol:
price, 1m/3m/5m/15m/1h/4h/24h as signed %, freshness age, n/7 warmup chip;
unavailable horizons show "—" with an insufficient-history note, never 0%).
Machine-readable `GET /api/features/returns` (`generated_at`, `source`,
`semantics`, `features[]`; 404 when empty). Still no `/movers`, no ranking,
no states, no controls.

### P1-05 terminal evolution + intelligence — IMPLEMENTED (PASS)

`/overview` reorganized into three separated blocks — **Dashboard server
health** (process uptime, version, persistence reachability, rows, snapshot
age), **Market feed health** (per-endpoint connections, streams, messages,
gaps, this-run vs retained rejections), **Persistence health** (retained
rows, discovery scan state) — followed by Symbol Returns, **Market
intelligence** (universe tiers, live momentum with tier/velocity/accel/rank/
rank-Δ/freshness/warmup, discovery gainers/losers/most-active labeled
discovery-only, promotion/demotion history), then detector telemetry.
`/system` stays technical ("Rejections / skew" now labeled run-counter vs
retained rows). Machine-readable `GET /api/features/momentum` (velocity/
accel semantics, ranks, per-symbol rows) and `GET /api/discovery`
(architecture note, subscription note, snapshot, events). Health JSON adds
explicit `server` vs `feed` blocks. Dashboard staleness reflects market-data
freshness only — server health stays independently visible.

### P1-06 terminal evolution — IMPLEMENTED (PASS)

`/overview` market-intelligence area gained a **Live trade flow** table
(subscribed symbols only): price, 1m notional, aggressive BUY/SELL split
bar (text blocks, green/red, no heavy framework), signed delta, delta
ratio, trade rate, 1m volume z-score, freshness, n/6 horizon warmup.
Discovery movers tables gained tier (CORE/HOT/DISCOVERY), eligibility, and
live-feed columns — unsubscribed rows read DISCOVERY ONLY — NO LIVE FLOW.
Machine-readable `GET /api/features/flow` (semantics + per-symbol
horizons/baselines/acceleration; 404 when empty) and
`GET /api/features/volume` (baselines + acceleration subset). No signal
labels, no buttons, no controls; `/system` and health separations kept.

### P1-07 book + OI terminal evolution — IMPLEMENTED (PASS)

`/overview` market-intelligence area gained **Live order book** (subscribed
symbols only): bid/ask, spread bps, visible bid/ask notionals, notional
imbalance, microprice displacement, slope asymmetry, 10bps concentration,
integrity (OK/DEGRADED + gaps), freshness — and **Live open interest**:
current OI, 1m/5m deltas, acceleration, descriptive 1m price/OI context,
freshness (+STALE flag). Discovery live-feed cells now read DISCOVERY ONLY
— NO LIVE FLOW/BOOK. Machine-readable `GET /api/features/book` (snapshot
semantics + integrity; 404 when empty) and `GET /api/features/open-interest`
(poll source + deltas + contexts). No signal labels, no buttons, no
controls; `/system` and health separations kept.

### P1-08 structure terminal evolution — IMPLEMENTED (PASS)

`/overview` market-intelligence area gained **VWAP / volatility /
structure** (subscribed symbols only): 1m VWAP + displacement bps,
realized vol 1m/5m, 5m range position + expansion multiple, swing HH/HL
relations, prior-range state, price-data freshness. Machine-readable
`GET /api/features/vwap`, `/api/features/volatility`, `/api/features/
structure` (per-symbol projections of the stored record, ready for
P1-09 `/symbol/:symbol`; 404 when empty). No signal labels, no buttons,
no controls; `/system` and health separations kept.

### Stage 2 — P1-09 MARKET-INTELLIGENCE DASHBOARD — IMPLEMENTED (PASS)

Live v0.8.0. Information architecture: `OVERVIEW` (market summary cards,
top activity, compact live-core rows with token links) → `MOVERS`
(discovery + live workbench) → `/symbol/:symbol` (per-token intelligence)
→ `SYSTEM` (all P1-03…P1-08 diagnostics + machine API index). Search box
in the top bar (`/search`, case-insensitive partial over the persisted
universe: tops + CORE + HOT + live symbols; deterministic; escaped).

- `/movers`: market table (tier + LIVE/DISCOVERY ONLY/WARMING/STALE/DEGRADED
  per row, clickable → `/symbol/:symbol`) + categories: 24h gainers/losers/
  most-active (discovery), HOT proposals, live velocity ±, acceleration,
  volume-expansion, aggressive-flow leaders. Discovery vs live metrics never
  mixed without labels.
- `/movers` category-value contract (P1-11A FIX): each category renders its
  OWN display key (`_v_pct` 24h change `+%.2f%%` / `_v_qvol` quote volume /
  `_v_hot` "proposed" / `_v_vel` `%.3g/s` / `_v_acc` `%.3g/s²` /
  `_v_volz` `%+.2f z` / `_v_flow` `%+.2f`). Source field, sort key, display
  field, unit and formatter are per-category; a shared key across loops is
  forbidden (it mixed scales for symbols present in several tables).
  Regression: `MoversIntegrityTest` (unique fixtures velocity 1.1e-6,
  acceleration 2.2e-8, flow 333333, vol-z 4.4, quote-vol 55555555,
  24h +6.6%; fails 4/5 on the old code, passes 5/5 fixed).
- `/symbol/:symbol`: header (price, 24h %, tier, capability, freshness, feed
  state) + mark-price SVG line chart (5m/15m/1h/4h/24h, honest partial/
  warming) + Momentum + Trade flow (aggressor side only) + Order book
  (integrity copy: HEALTHY / Recovered N gaps / DEGRADED — gap active) +
  Open interest (descriptive contexts with help text) + VWAP/volatility/
  structure (UNKNOWN/WARMING, never blank). Discovery-only symbols show
  REST metrics + DISCOVERY ONLY — NO LIVE DEEP FEATURES; flow/book/OI/
  VWAP/vol/structure never fabricated.
- Machine: `GET /api/symbol/:symbol/price?range=` (bounded ≤1000 points,
  oldest-first, no future samples, downsampled with endpoints kept;
  400 on bad symbol/range, 404 on unknown symbol) + CSV twin
  (`price.csv`, `timestamp,price`) + `GET /api/search?q=`.
- Capability vocabulary (UI-wide, tier orthogonal): LIVE / WARMING /
  DISCOVERY ONLY / STALE / DEGRADED / UNKNOWN. Tiers CORE/HOT/DISCOVERY
  use neutral chips; green/red reserved for signed values; amber for
  warming; stale/degraded warnings separated across server/feed/
  persistence health. No signals, no controls, no private data.

### Stage 3 — P1-13 SIGNAL / EXTREME-MOVE UI

### Stage 3 — P1-13 SIGNAL / EXTREME-MOVE UI

Add: `/signals`, `/extreme-moves`. States shown with evidence vectors;
extreme moves shown with context — never as an entry list.

### Future professional UX (P1-13B plan, NOT implemented)

Navigation: OVERVIEW / MOVERS / OPPORTUNITIES / PAPER LAB / BACKTEST /
SYSTEM. Opportunities rank setup candidates dynamically (never an entry
list). Token page grows (chart, momentum, aggressive-flow split, OI,
liquidity/book, VWAP/volatility/structure, BTC context, historical context,
research setup card) without redesigning the Phase-1 IA. Full plan:
`docs/SIGNAL_RESEARCH_PLAN.md`. No UI rebuilt in P1-11A.

### Later (Phases 2–4)

`/paper`, `/performance`, `/strategies`, `/risk` arrive with their engines.
Every money-like number before Phase 4 is labeled hypothetical/simulated.

## DASHBOARD ACCESS PLAN (binding)

- **Dedicated port policy:** ordered candidate list starting at `8091`
  (8091, 8092, 8093, …). At startup, bind the first FREE port; never reuse
  another project's port, never kill unrelated processes on conflict — pick
  the next free candidate and document the decision in `docs/DECISIONS.md`.
  Evidence 2026-10-06: 8091/8092/8093/18091/18765 probed FREE on 127.0.0.1.
- **Host/bind policy:** `127.0.0.1` by default. No `0.0.0.0` without a dated
  decision entry + human acknowledgment.
- **Health endpoint:** `GET /api/health` (finalized in P1-03; must return
  status, version, uptime, stream summary). Readiness = HTTP 200 with
  `status: ok`.
- **Startup strategy:** start locally after port check; verify via HTTP
  health/readiness request; keep running if safe; return the exact browser URL
  (`http://127.0.0.1:<port>`) plus DASHBOARD_URL/HOST/PORT/PID-or-identity,
  HEALTH_ENDPOINT/STATUS, START/STOP/RESTART commands. Startup/restart must
  never start trading or require Binance private credentials.
- **Process/PID tracking:** PID file at `logs/dashboard.pid` (git-ignored via
  `logs/`); STATUS/RESTART validate the PID is alive AND the health endpoint
  responds before trusting it.
- **Commands (concrete scripts land in P1-03; semantics fixed here):**
  START = port-check → launch bound to 127.0.0.1 → write PID file → health
  check → report URL block. STOP = terminate only the tracked PID, remove PID
  file. RESTART = STOP + START. STATUS = PID-alive + health response + route
  spot-check. All operate ONLY on the Binance dashboard.
- **Conflict handling:** port occupied → next candidate, log + document; PID
  file stale (dead PID or wrong process) → discard, fresh start; health failing
  on a live PID → report unhealthy, do not silently restart during soak runs.
- **Availability requirement:** dashboard must be up during P1-10 soak and
  P1-14 calibration so the operator can inspect live and take screenshots
  while data flows.

## Rules

- Data source is persistence/API, never scraped DOM; engine never consumes
  dashboard output.
- Stack/tech choice is a P1-03 task decision (record in `docs/DECISIONS.md`);
  no framework pre-committed here.
