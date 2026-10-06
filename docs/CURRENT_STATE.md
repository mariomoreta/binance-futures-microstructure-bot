# CURRENT_STATE

Factual state as of 2026-10-06 (order refinement). Historical evidence:
`docs/PHASE_1_REPORT.md` (do not rewrite).

## Baseline (audited, preserved)

- Codebase: `src/microstructure_probe/` — `probe.py`, `detectors.py`, `metrics.py`,
  `telemetry.py`, `clock.py`, `config.py`, `models.py`, `__main__.py`.
  Plus root `run_tests.py` (P1-00; test tooling only, no app behavior change).
- Version: 0.2.0 (`pyproject.toml`). History: `157e85e` baseline + `d6801a5`
  brain checkpoint, branch `phase1/market-intelligence-dashboard`, published to
  private `mariomoreta/binance-futures-microstructure-bot` (origin/main +
  origin/phase1 in sync). Repo-local git identity configured per operator
  authorization; nothing global was changed.
- Mode: OBSERVE ONLY. `BOT_MODE=observe` enforced in code; any other value aborts.
  No authenticated clients, no order paths (covered by static test).
- Feeds (public, routed endpoints): `/public` (bookTicker, depth20@100ms),
  `/market` (aggTrade, `!markPrice@arr@1s`, `!forceOrder@arr`).
  Symbols: BTCUSDT, ETHUSDT, SOLUSDT (`config/probe.json`).
- Implemented: clock sync (5-sample midpoint median, ~10 min), gap/staleness
  detection (staleness only on cadenced streams; event-driven silence ≠ stale),
  raw/corrected event+transaction latency per stream/symbol, monotonic processing
  latency split (parse/metrics/detector), liquidation individual+10s-window
  detectors, funding percentile extremes with warm-up + non-independence note,
  10s-bucket volume z-score with warm-up + near-miss, telemetry
  (quantiles over last 20k samples; exact count/min/max/mean), JSON logs +
  `final_summary`.
- Phase 1B semantics: `E` = event time; `T` = trade/transaction time except
  markPrice where `T` = next funding time (NOT latency). Legacy global clamped
  lag kept labeled as legacy, not a gate metric.

## Verification (2026-10-06)

- Canonical: `python run_tests.py` from repo root → **28/28 PASS** (before and
  after P1-01; no code changes).
- `--show-streams` → correct routed `/public` + `/market` URLs.
- Port candidates 8091/8092/8093/18091/18765 probed FREE on 127.0.0.1
  (dashboard port-policy evidence; selection happens at P1-03 startup).

## P1-01 short transport validation — RESULT: PARTIAL (2026-10-06)

Run: `python -m microstructure_probe --duration 1800`, BOT_MODE=observe,
`runtimeSeconds: 1804.969`, exit 0. Evidence log (local, git-ignored):
`logs/p1-01/probe-1800s.log`. No keys, no orders, no capital, no private APIs.

Measured (from `final_summary`):

- Coverage: 11/11 streams active, `missingStreams: []`, `staleStreams: []`.
- Uptime: market 98.51% (1773.3s/1800.1s), public 95.05% (1711.0s).
  Attempts 60 (public 46, market 14), all succeeded.
- Reconnects: 58 total (public 45, market 13) — every one
  `ConnectionClosedError: no close frame received or sent`, retry 1s
  (backoff resets on success, so it never grew). ~1 drop per 31s average.
- Messages: 172,906 total. bookTicker 32.2/31.5/17.9 msg/s (BTC/ETH/SOL);
  depth ~2/s per symbol (cadence allows ~10/s); markPrice arrays 1563 of ~1800
  expected; forceOrder 421; aggTrade 5466/4709/3205.
- Delivery lag (corrected event lag): bookTicker p50 14.8–19.2s / p95
  45.6–53.8s; depth p50 ~14.7s / p95 ~50.4s; aggTrade p50 31.6–38.1s / p95
  73.5–75.6s; markPrice p50 35.0s / p95 75.9s; forceOrder p50 38.5s / p95 69.0s;
  max ~127s. Exchange-side E−T deltas are milliseconds (bookTicker p50 0ms),
  so the delay is entirely in the delivery path to this host, not Binance.
  Clock sync 3/3 ok (15/15 samples); offset drifted −231ms → −475ms; RTT
  610–943ms — slow/lossy path confirmed.
- Skew guard: `timestampRejected: 147417` (~85% of messages, |received−E| >
  5000ms, degraded from the first 30s summary onward). Rejected messages skip
  metrics+detectors, so detectors operated on survivors only.
- Gaps/silence: depth sequence gaps 50/49/49 (reconnect-driven, expected).
  Max observed silence: depth ≤28s, bookTicker ≤21.5s, aggTrade ≤16s,
  markPrice 12s. forceOrder silent up to 111s — event-driven, correctly NOT
  reported stale (Phase 1B fix works in practice).
- Errors: parse 0, payload 0, websocket errors = reconnects (58).
  Processing latency sub-ms (p50 ≤0.17ms) — probe CPU is fine.
- Detectors: 26 `extreme_funding_rate`, 0 liquidation, 0 volume. The 26 funding
  events are sampling artifacts (near-constant series ±1e-7…1e-5 evaluated on
  sparse post-rejection arrivals, first firing at the 30-sample warm-up edge),
  NOT signal validation. No threshold conclusion may be drawn from this run.
- Safety block in every summary: observe, 0 keys, 0 orders, 0 capital,
  no authenticated clients, no order paths.

Verdict reasoning: P1-01 as a measurement exercise succeeded (full
characterization obtained), but transport in THIS environment is unhealthy
(reconnect storm + 15–75s delivery lags + 85% skew-rejection). Therefore
PARTIAL: evidence recorded, P1-02/P1-03 (local builds) may proceed, but gates
G2–G4 cannot pass on this evidence and P1-10/P1-14 require re-validation in a
healthy network (tracked as `P1-01R` in `docs/TASK_QUEUE.md`).
`docs/PHASE_1_REPORT.md` historical evidence untouched.

## Phase 1 execution order (binding, refined 2026-10-06)

`P1-00` tooling ✅ → `P1-01` short transport validation (30–60 min, NOT 6h) →
`P1-02` persistence foundation → `P1-03` minimal dashboard (`/overview`,
`/system`) → `P1-04` universe+returns → `P1-05` velocity/rank → `P1-06`
volume/flow → `P1-07` book/OI → `P1-08` VWAP/vol/structure → `P1-09`
intelligence dashboard (`/movers`, `/symbol/:symbol`, raw features first) →
`P1-10` ≥6h soak with dashboard live → `P1-11` raw feature validation →
`P1-12` classifier v0 (BLOCKED until P1-11) → `P1-13` signal/extreme-move UI →
`P1-14` 24h calibration + gate evaluation. Full detail: `docs/TASK_QUEUE.md`.

Superseded: the earlier "soak first, persist nothing in Phase 1" sketch.
Persistence foundation is now explicitly a Phase 1 task (local, observe-only,
dashboard-feeding) — see `docs/DECISIONS.md`.

## Project brain

- `AGENTS.md` + 20 docs under `docs/`. No strategy, engine, or safety code
  touched. `docs/PHASE_1_REPORT.md` preserved as-is.

## Known gaps (Phase 1 work ahead, in order)

Persistence foundation, minimal dashboard, open interest, multi-timeframe
return engine, velocity/acceleration, ranking + rank velocity/acceleration,
VWAP + displacement, realized volatility/range expansion, structure primitives,
richer aggressive-flow metrics, state classifier, intelligence + signal UI,
soak + calibration evidence.

## Blockers / issues

- Transport unhealthy in this environment (P1-01 PARTIAL): reconnect storm +
  15–75s delivery lags. Re-validation in a healthy network (`P1-01R`) required
  before P1-10 soak / P1-14 calibration gates. P1-02/P1-03 (local builds) NOT
  blocked.
- No dashboard running yet (first visible at P1-03). No secrets, keys, or
  account access exist or are needed.
