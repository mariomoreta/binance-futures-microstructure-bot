# FEATURE_MODEL

Features to develop in Phase 1. Each needs: exact definition, update cadence,
warm-up rule, normalization, and telemetry — before any threshold is trusted.
Thresholds are HYPOTHESIS until Phase 2–3 statistics exist.

## Price

- Returns: 1m / 3m / 5m / 15m / 1h / 4h / 24h (log returns; source: aggTrade /
  klines bootstrap; track staleness per timeframe).
- Velocity: first derivative of returns (e.g. Δ 1m-return over trailing window).
- Acceleration: second derivative (Δ velocity). Noise-sensitive — smooth first,
  document smoothing.

## Cross-sectional rank

- Gainer/loser ranking over the monitored universe per timeframe.
- Rank velocity: rank change per unit time (climbing fast?).
- Rank acceleration: Δ rank velocity.
- Requires universe expansion beyond 3 symbols; rank is meaningless on n=3.

## Volume / flow

- Volume acceleration, volume z-score (10s-bucket detector exists; extend to
  multiple bucket sizes).
- Aggressive buy/sell imbalance, trade delta (taker-side proxy from aggTrade;
  document approximation limits).
- Liquidations: individual + window notionals exist; add cascade rate,
  long-vs-short liquidation imbalance.

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
