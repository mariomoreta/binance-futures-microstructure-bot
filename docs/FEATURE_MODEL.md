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
