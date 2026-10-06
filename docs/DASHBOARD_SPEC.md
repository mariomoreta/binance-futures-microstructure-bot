# DASHBOARD_SPEC

A dedicated Binance dashboard is mandatory and belongs only to this project
(`C:\proyectos\binance-futures-microstructure-bot`). It must not reuse or
interfere with the Solana/Arbitrum dashboards or ports.

It is a visualization/control surface. The trading engine must NEVER read
decisions from frontend-rendered state.

## Staged delivery (binding order)

### Stage 1 — P1-03 MINIMAL DASHBOARD, first visible here

Routes: `/overview`, `/system`.

Must expose: connection health, stream health, message rates, latency p50/p95,
stale symbols, sequence gaps, reconnects, last update, runtime duration —
plus the safety banner (`BOT_MODE`, keys=0, orders=0).

### Stage 2 — P1-09 MARKET-INTELLIGENCE DASHBOARD

Add: `/movers`, `/symbol/:symbol`. Show raw features BEFORE classifier scores.
Per-symbol: price, returns, velocity, rank, volume/flow, book, OI, funding,
VWAP displacement, volatility. Operator keeps working browser access through
this and all later live stages.

### Stage 3 — P1-13 SIGNAL / EXTREME-MOVE UI

Add: `/signals`, `/extreme-moves`. States shown with evidence vectors;
extreme moves shown with context — never as an entry list.

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
