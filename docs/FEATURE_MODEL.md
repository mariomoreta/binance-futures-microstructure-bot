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

## Book

- Spread (bps, exists), depth totals, book imbalance (exists).
- Extend: depth slope/concentration, microprice, book resilience after sweeps.

## Positioning / carry

- Open interest, OI delta, OI acceleration (NOT YET SOURCED — needs public
  OI endpoint task). Price-up + OI-up vs price-up + OI-down distinguish very
  different regimes; do not model ignition without it long-term.
- Funding rate extremes (exists, percentile-based) + funding momentum.
- Basis (spot vs futures) where useful; needs spot feed — optional Phase 1
  stretch, default OFF unless a task authorizes it.

## Volatility / structure

- Realized volatility (multi-horizon), range expansion (current range vs
  trailing baseline).
- VWAP (session/rolling) + VWAP displacement (z or % dev).
- Local highs/lows, breakouts, structure breaks (define swing lookback
  explicitly; no будущего — no lookahead).

## Feature discipline

- Every feature: pure function + unit test on known values (follow
  `metrics.py` / `test_metrics.py` pattern).
- Every threshold lives in `config/probe.json`, never hardcoded.
- Near-miss + warm-up telemetry for every detector (follow `detectors.py` pattern).
- Repeated stream samples are not independent evidence (funding caveat applies
  generally).
