# FEATURE_MODEL

Features to develop in Phase 1. Each needs: exact definition, update cadence,
warm-up rule, normalization, and telemetry — before any threshold is trusted.
Thresholds are HYPOTHESIS until Phase 2–3 statistics exist.

## Price — IMPLEMENTED P1-04 (returns only; velocity/acceleration → P1-05)

- Canonical source: **mark price** (`markPrice` stream, field `p`).
  Deviation from the earlier aggTrade/klines sketch recorded in
  `docs/DECISIONS.md` (regularity + boundedness rationale).
- Semantics: **log returns** r = ln(current/anchor) for
  1m / 3m / 5m / 15m / 1h / 4h / 24h on 10s event-time buckets (last wins).
- Anchor policy: latest sample at-or-before (current − tf) within
  max(60s, tf/20); otherwise UNKNOWN (`null`, shown as "—", never 0%).
- No lookahead (queries never see samples newer than as-of); no interpolation;
  out-of-order samples dropped and counted; invalid prices refused.
- Engine: `src/microstructure_probe/returns.py` (`ReturnEngine`,
  per-symbol `SymbolPriceSeries`, ≤9180 buckets ≈ 25.5h); universe:
  `src/microstructure_probe/universe.py` (active trio BTC/ETH/SOLUSDT,
  explicit metadata, no silent expansion, no ranking yet).
- Record per symbol: current_price, source_timestamp_ms, sample_age_ms,
  history_span_ms, returns/anchor_ms per TF, available_tfs, warmup_complete.
- 24h stays unavailable until ~24h of real bucketed history exists (or a
  justified public bootstrap — none implemented; short runs honestly show it
  unavailable).
- Velocity/acceleration (first/second return derivatives) belong to P1-05 —
  not implemented. Rank velocity/acceleration likewise P1-05.
- P1-09 UI read contract (no engine change): token charts/CSV read the same
  persisted 10s mark-price buckets (`price_samples`) via bounded,
  oldest-first, window-filtered (never future) queries (≤1000 points,
  endpoints kept on downsample). Ranges 5m/15m/1h/4h/24h only.

## Velocity / acceleration / ranking — IMPLEMENTED P1-05

- velocity(h;b) = [R_h(t) − R_h(t−b)] / b_seconds (default b = h), computed
  from the P1-04 bucketed series via timestamped return evaluations — no
  grid assumption, no lookahead (each evaluation uses samples ≤ its as-of).
  Preferred horizons 1m/3m/5m/15m. A flat high return yields ~zero velocity
  (return-momentum, not renamed return). Unavailable until two evaluations
  span h+b (+tolerances) — else None, never 0.
- acceleration(h;b;c) = [v(t) − v(t−c)] / c_seconds (defaults b = c = h;
  1m acceleration needs ~3min of span). Timestamp-aware, deterministic,
  unavailable until three evaluations exist — else None.
- Ranking per metric (velocity_1m, velocity_5m, acceleration_1m): value
  descending, ties by (value desc, symbol asc). rank_change = prev − rank
  (+ = climbed); rank_velocity = change/elapsed_s (≥2 evals);
  rank_acceleration = Δrank_velocity/elapsed_s (≥3 evals). Missing values
  excluded, never zero-filled.
- Live ranks cover subscribed symbols (n=3 today — honest, grows with HOT
  subscriptions); broad discovery movers (top gainers/losers/most-active)
  come from 24h REST stats and are labeled discovery-only.
- Tiers: CORE (pinned trio) / DISCOVERY (eligible scan) / HOT (core + ≤N
  dynamic by movement score with vote/dwell hysteresis). HOT is proposed
  only in P1-05 — no dynamic websocket resubscription yet.

## Cross-sectional rank

- Gainer/loser ranking over the monitored universe per timeframe.
- Rank velocity: rank change per unit time (climbing fast?).
- Rank acceleration: Δ rank velocity.
- Requires universe expansion beyond 3 symbols; rank is meaningless on n=3.

## Volume / flow — IMPLEMENTED P1-06 (detector thresholds still HYPOTHESIS)

- Engine: `src/microstructure_probe/flow.py` (`FlowEngine`, per-symbol
  `SymbolFlowSeries`), fed by every VALID aggTrade pre-sampling (post-skew
  guard only). Aggressor from `m` (true→SELL, false→BUY); per-trade base +
  notional split; RPI transparency via `nq`.
- Horizons (trailing event-time windows): 10s/30s/1m/3m/5m/15m, each with
  trades, base/notional totals, buy/sell base+notional, signed delta,
  delta_ratio ([−1,+1], null on zero), buy/sell %, trade/notional rate,
  freshness, warmup. No lookahead (completed-buckets-only baselines;
  strictly-older drops, same-E accepted in arrival order).
- Volume baselines 10s/30s/1m/5m on completed-bucket notionals: current,
  mean, std, z, sample count, warmup; skipped buckets counted, never
  fabricated; insufficient history or zero variance → UNKNOWN (null).
- Acceleration (canonical 1m, timestamp-aware): notional/trade/delta rate
  changes vs last completed bucket; null until one bucket closes.
- Live scope: subscribed symbols only (BTC/ETH/SOLUSDT today); HOT and
  discovery symbols show REST 24h metrics labeled DISCOVERY ONLY.
- Pre-existing 10s volume-spike detector (`detectors.py`) unchanged; its
  z-threshold stays HYPOTHESIS until P1-11/P1-14.
- Liquidations: individual + window notionals exist; add cascade rate,
  long-vs-short liquidation imbalance (still pending).

## Book — IMPLEMENTED P1-07 (no thresholds, no composite score)

- Engine: `src/microstructure_probe/book.py` (`BookEngine`, per-symbol
  `SymbolBookState`), fed by every VALID depth20@100ms snapshot
  pre-sampling (post-skew guard only). Full-snapshot semantics verified
  (docs + live `pu`-chain).
- Per snapshot: best bid/ask, mid, spread abs/bps, top-1/5/10/20 base +
  notional sums per side (level counts exposed), qty/notional imbalance
  ([−1,+1], null on zero), microprice + displacement bps (null on zero
  top qty), LS-through-origin depth slope per side + asymmetry,
  concentration within 5/10/25bps (null when the book does not span the
  band, coverage exposed), crossed-top flag, sequence integrity
  (gap count, last `u`, DEGRADED-until-chained), freshness.
- Invalid books dropped + counted (previous retained); strictly-older `E`
  dropped, same-E accepted; only subscribed symbols tracked.
- Still pending: book resilience after sweeps (P1-08 territory).

## Positioning / carry — OI IMPLEMENTED P1-07 (descriptive only)

- Source: public `GET /fapi/v1/openInterest`, 60s bounded poller
  (`OpenInterestPoller`: one sequential round/tick, worker thread,
  failures counted, WS never blocked). `openInterestHist` deferred.
- Tracker (`OpenInterestTracker`, 2000 samples/symbol): current OI +
  exchange/fetch timestamps, deltas abs/% + rates over 1m/5m/15m vs
  actual-timestamp anchors (tolerance max(60s,h/20)), 1m acceleration;
  UNKNOWN until warmed, never 0; staleness flagged, never hidden.
- Price/OI context per horizon (`PRICE_UP_OI_UP` etc., `MIXED`,
  `UNKNOWN`) — descriptive regime tags only, no signal/bullish/bearish
  claims. Price-up + OI-up vs price-up + OI-down regimes are now
  observable raw inputs for P1-11/P1-12.
- Funding rate extremes (exists, percentile-based) + funding momentum.
- Basis (spot vs futures) where useful; needs spot feed — optional Phase 1
  stretch, default OFF unless a task authorizes it.

## Volatility / structure — IMPLEMENTED P1-08 (descriptive only, no signals)

- Engine: `src/microstructure_probe/market_structure.py`
  (`MarketStructureEngine`, stateless compute over peer-engine state —
  no new ingest path, no new endpoint, no kline bootstrap).
- VWAP from P1-06 flow aggregates (`notional/base` per trailing window
  1m/3m/5m/15m; 30m/1h not offered — provenance ends at 15m). Reference
  price is P1-04 mark-price `current_price` (labeled, never mixed);
  displacement abs/%/bps; zero base volume → UNKNOWN.
- Realized volatility (raw, non-annualized `sqrt(sum(r²))` over
  consecutive 10s-bucket log returns) for 1m/5m/15m/1h; value needs
  ≥5 returns spanning window−10s; `warmed` adds full grid coverage;
  otherwise UNKNOWN (measured flat zero stays 0.0 — distinct from missing).
- Range 1m/5m/15m: high/low, abs/%, position in [0,1] (null on flat);
  expansion = current range / trailing median of ≤10 prior completed
  blocks (+z when ≥10 blocks and variance > 0, else null).
- Structure (method A, confirmed pivots, L=R=3 buckets = 30s delay):
  strict local max/min, last-two swing relations (HH/LH/HL/LL, null
  until two pivots), signed distance bps, breakout vs prior completed
  15m block (`ABOVE/BELOW/INSIDE_PRIOR_RANGE`, else `UNKNOWN`).
- Book resilience from P1-07: DEFERRED — spread/depth event history is
  not retained; a P1-11 modeling task, not a freebie (see DECISIONS).

## P1-11B historical/live fidelity contract (binding for research)

- Mark-price klines ↔ live mark-price returns: BEST match (same source
  semantics; historical counterpart of the P1-04 engine).
- Regular-klines taker-buy volume: flow PROXY/context only — NOT identical
  to the live aggTrade flow engine (different aggregation, no RPI split).
- OHLC bars: CANNOT reconstruct order books (no historical book exists;
  depth REST is present-only — documented limitation, not a gap to fill
  speculatively).
- 5m historical OI: CANNOT recreate 1m live OI contexts; only ~42h of 5m
  history is served (500-row cap measured) — store only what is served.
- aggTrades REST: most-recent only (probe: 0.1-min-old) — no multi-year
  flow backfill is designed around it; bounded recent capability only.
- Gaps stay UNKNOWN/GAP in both worlds; P1-11C excludes events spanning
  invalid gaps (ranges persisted in `historical_gaps`).

## Feature discipline

- Every feature: pure function + unit test on known values (follow
  `metrics.py` / `test_metrics.py` pattern).
- Every threshold lives in `config/probe.json`, never hardcoded.
- Near-miss + warm-up telemetry for every detector (follow `detectors.py` pattern).
- Repeated stream samples are not independent evidence (funding caveat applies
  generally).

## P1-11A validation — MEASURED 2026-10-07 (P1-10 4.91h evidence, END state)

All families below are mathematically and operationally trustworthy as RAW
inputs for research. No threshold was tuned; categorical states were not
percentiled. n=3 symbols throughout (percentiles across symbols are
illustrative, not statistical).

- Returns (log, mark-price 10s buckets): 1m/3m/5m/4h available at END
  (15m/1h/24h honestly UNKNOWN — degraded final hour starved fresh buckets
  past the max(60s,tf/20) anchor tolerance; warmup_complete=False overall).
  Scales sane: 1m −8.8e-4…−2.0e-4, 4h −1.05e-2…−3.1e-3. Signs mixed across
  horizons (1m/3m/4h negative, 5m positive) — consistent with a down-drift
  afternoon, not a sign bug. No lookahead (queries ≤ as-of), late =
  strictly-older dropped + counted (0 late), restored history extends span
  (58.83M ms / 16.34h) without fabrication. Grid fill 31.7% (degraded-env
  starvation, counted) — longer horizons go UNKNOWN instead of interpolating.
- Momentum: velocity_1m −2.4e-5…−4.4e-6 /s, acceleration_1m −8.2e-7…−9.3e-8
  /s² (return-change-per-second scales, NOT renamed returns — flat trends
  ≈ 0 proven by unit test). velocity_5m+ and accel_3m+ honestly None until
  3 evaluations. Ranks ±/ties/change/velocity/accel deterministic; missing
  excluded, never zero.
- Flow (every valid aggTrade pre-sampling): all 6 horizons + 4 baselines +
  1m accel present. 1m notionals BTC $12.7M / ETH $5.8M / SOL $1.3M
  (ordering BTC>ETH>SOL correct). Ratios inside [−1,+1]; END state
  sell-dominated on all horizons (10s ratio −0.43…−0.72) — market condition,
  not a bug. z-scores finite (no zero-variance fabrication). Rule preserved:
  aggressive BUY 70% does NOT mean 70% LONG probability.
- Book (every valid depth snapshot): spread 0.012/0.039/0.862 bps,
  imbalances in [−1,+1], microprice ≈ mid, live, freshness ~1.2s, 0 crossed,
  33/32/32 gaps all recovered (degraded:false). Recovered gaps vs active
  degradation are distinguished by the gap→DEGRADED-until-chained flag.
- OI (60s bounded polls, WS isolated): current BTC 95703.6 / ETH 2425831.8
  / SOL 8487893.6 base units; 1m/5m/15m deltas + rates + 1m accel all
  present with mixed signs (1m positive, 5m/15m negative — not stuck);
  anchors 62s/315s/922s back within tolerance; stale=false; timestamps
  coherent (exchange/fetch/last-fetch). Units verified: base units, NOT
  notional.
- VWAP: 1m/3m/5m/15m displacement −4.5…+4.6 bps, sane, sign-mixed.
- Volatility (raw sqrt(sum(r²)), non-annualized): 1m 4.4e-4…6.5e-4,
  5m 1.5e-3…2.1e-3, warmed=true; 15m/1h honestly UNKNOWN (warmed=false) —
  UNKNOWN vs true zero is distinguished (flat zero stays 0.0).
- Range: 5m/15m position in [0,1], expansion 0.57…1.76; 1h UNKNOWN (needs
  10 prior blocks). No impossible values.
- Structure: 1659 evals, pivots/HH-LH/HL-LL/breakout tags evaluating on the
  16.34h span; availability inherited, never fabricated.
- Freshness/missingness: LIVE/WARMING/DISCOVERY ONLY/STALE/DEGRADED/UNKNOWN
  vocabulary holds end-to-end (dashboard renders "—", never 0).
- Transport impact (healthy T+2h→T+3h vs degraded T+4h→END): healthy
  918 msg/s, 0% rejects, 0 reconnects, 0 gaps; degraded 867 msg/s, 12.9%
  rejects, 29 reconnects, 64 new gaps. Feature effect: returns span kept
  growing (+360 vs +129 samples); flow −6.5%; book ingest −64%
  (depth starved by rejects, integrity still HEALTHY); structure −19%;
  OI ISOLATED (0 failures both windows — REST path independent of WS
  degradation). Degradation starves features honestly; it does not corrupt
  them. Classifiers must treat UNKNOWN/staleness as first-class input.
- Constant/near-constant flags (expected, not bugs): funding rate series
  (175–176 valueChanges / 13519 samples → 16.5k artifact crossings, same
  hypothesis class as P1-01/P1-05); no other family is constant.
- No unit mismatches, no malformed state transitions, no suspicious spikes
  beyond absorbed processing maxima (queues stayed 0/0).
- BTC-context / exhaustion / absorption / historical designs live in
  `docs/SIGNAL_RESEARCH_PLAN.md` and `docs/HISTORICAL_RESEARCH_PLAN.md`
  (design only — nothing implemented in P1-11A beyond the Movers fix).

## P1-12B dynamic universe (2026-10-08, budgets conservative/UNVERIFIED)

- HOT symbols, once subscribed, produce the same raw families as CORE
  (returns/velocity/accel, flow + baselines, book, OI polls, VWAP/vol/
  range/structure) through identical code paths; funding-rate detector
  events stay CORE-configured (threshold maps are per-trio).
- Warm-up is per symbol/feature (no inheritance across lifecycles);
  lifecycle WARMING/LIVE/DEGRADED is tracked separately from feature
  UNKNOWN; classifier P1-12A consumes HOT rows unchanged (UNKNOWN until
  its own minimum-data gate passes).
- Recorder buckets for HOT open on first trade; demotion closes them
  PARTIAL with idempotent keys (no double-count on re-promotion).

## P1-12A classifier outputs (2026-10-08, rules v0.1.0 HYPOTHESIS)

- Observed states NORMAL/IGNITION/EXPANSION/EXHAUSTION/REVERSAL + UNKNOWN,
  directions UP/DOWN/NONE/UNKNOWN, per symbol per ~30s summary; every
  record carries evidence_for/against, missing_features, validity, rules
  version, and transition {previous, changed, since, duration, reasons}.
- Rule inputs and units: velocity_1m (1/s), accel_1m (1/s²), log returns
  (15m/1h), 1m flow signed_delta (USDT) + delta_ratio, 1m vol z,
  15m expansion_ratio + range_position, breakout_state, 15m realized vol,
  book imbalance, 1m OI delta. UNKNOWN/stale/discovery-only short-circuit
  before any rule; missing never becomes zero.
- Measured live cost 0.16–0.20ms per 3-symbol batch; cold-restart memory;
  no probabilities anywhere; full spec in `docs/CLASSIFIER_SPEC.md`.

## P1-11C research features (2026-10-07)

- Event formation features (T-known only): prior 1h/4h/24h log returns, trailing-96 range position + high/low distances, as-of 30d high/low, volume percentile, realized |return| vol + percentile, HISTORICAL_TAKER_BUY_PROXY (+ implied sell share), HISTORICAL_MOMENTUM_PROXY accel, BTC 5m/15m/1h sync + 1h relative return.
- Outcome features per horizon: forward return, direction-oriented MFE/MAE, time-to-MFE/MAE, predeclared invalidation time, path state + gap flags + usability, continuation/reversal label (CONTINUED_UP/REVERSED_DOWN/CONTINUED_DOWN/REVERSED_UP/MIXED/INSUFFICIENT_DATA).
- Prospective capture schemas: flow buckets (buy/sell notional+base, delta/ratio, OHLC, trade counts, quality) and book 1m summaries (spread/imbalance/microprice min-mean-max, top5/20 notionals, gap/degraded/crossed counts).


## 2026-10-11 - Proposed mover/level research measurements
Detailed definitions and gap register: [Movers and Levels](MOVER_LEVEL_STRATEGY_RESEARCH.md).
New measurements below are PROPOSED / NOT IMPLEMENTED, not added engine outputs:
- As-of small-cap cohort: stable asset mapping, contract multiplier, circulating
  supply/market-cap definition, provider/source time; UNKNOWN stays unknown.
- Separate rolling 24h arithmetic change, internal log returns, return since
  first detection and drawdown from the then-known running peak; explicit units.
- Frozen levels: source/timeframe/price basis, formation and confirmation/available
  time, prior completed range/confirmed pivot/day-week anchors, invalidation.
- Strategy snapshot/path: full feature vectors at decision T, chosen research side,
  path coverage/MAE/MFE/first touches and clock bases, separate endpoint lateness.
- Incremental BTC-relative and price-response-to-aggressive-flow measurements;
  do not count correlated flow/volume transforms as independent confirmations.
- Funding economic updates/actual interval and OI quantity versus OI value;
  repeated funding samples do not add independent information.
- Covered liquidity/impact for proposed size; depth20 coverage cannot justify
  arbitrary fill sizes or event-level recovery claims from 1m summaries.
Current VWAP is rolling 1m/3m/5m/15m; session/anchored VWAP remains a separate
proposal. Current classifier cadence/gates are descriptive, not execution-grade.
Backlog: F-RES-MOVERS-01 / F-RES-LEVELS-01 / F-RES-PATH-01 / F-RES-CONTEXT-01.
