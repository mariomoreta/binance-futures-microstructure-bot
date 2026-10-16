# Offline entry/exit evaluation — design V1 (fixed BEFORE results)

Status: design record. Economics are read ONLY after this design is
committed to a doc. No threshold is tuned at any point.

## 1. Chronological cut + held-out reserve

- Global event-time cutoff: `cutoff_ms = 1790010000000` (same frontier as the
  prior mechanical prep, kept for comparability; ≈ mid-window 2026-09-22).
  One global frontier keeps BTC/ETH/SOL periods aligned.
- `dev`: formation events with `event_time_ms + horizon_ms <= cutoff`
  (horizon 1h = 3600000ms → `event_time_ms <= 1790006400000`).
- `eval` (held-out): `event_time_ms >= cutoff`. Called `oos` in engine
  output (engine vocabulary); read as time-held-out, see §6.
- Purge: dev events whose 1h window crosses the cutoff are EXCLUDED from dev
  (their outcomes consume held-out data). Implementation: pre-selection
  filter on exported events (harness-level, engine untouched), recorded in
  the dataset manifest with counts (`n_purged_dev_crossing`).
- No embargo beyond the purge (single 1h horizon; stated, not modeled).
- The engine's `split_by_time` is NOT credited with purging (per its own
  contract); the purge above is applied BEFORE the runner sees the events,
  so each runner cell is already purge-clean.

## 2. Overlap / simultaneous exposure

- Engine `max_concurrent = 1` (default, untouched): overlapping
  signal-to-exit intervals compete deterministically in time order; losers
  counted as `skipped_overlap`, never silently dropped.
- Scope (binding): the limit applies INSIDE one `run_backtest` invocation =
  one (symbol-run, group, segment, scale) cell. Symbols replay in separate
  processes with symbol-pinned calendars (foreign symbol REJECTED
  fail-closed); groups and dev/oos replay in separate calls with separate
  open-interval ledgers. Cross-group/cross-symbol overlaps never compete.
  Combined results across cells must never be presented as a portfolio with
  a single simultaneous position.
- Dense 15m events under 1h horizons overlap heavily by construction;
  overlap rate is REPORTED per cell (admissible → discarded → traded flow).
  No portfolio/exposure model beyond this; simultaneous-exposure P&L is
  explicitly unmodeled (limitation).

## 3. Baseline + comparability

- Reference baseline (mechanical, not a strategy): pooled aggregate across
  the three directional groups under their own configs, per segment and
  cost scale, plus per-symbol aggregates. It answers "what did the
  mechanical replay produce overall", never "strategy vs market". On its
  own it is not a comparable alternative strategy (no buy-and-hold,
  time-placebo, or random-entry model exists in V1).
- No buy-and-hold / time-placebo / random-entry baseline is modeled in V1
  (would require new methodology; recorded as future protocol, not
  improvised here).
- Comparability limits: per-symbol calendars differ (rates are
  symbol-specific); H2 cells are INSUFFICIENT; bounce/baseline groups are
  EMPTY by construction; costs are assumed (§4). Cross-family ranking on
  conditioned net is NOT a selection.

## 4. Costs (versioned assumptions, NOT measurements)

- `COST-ASSUME-v1`: taker fee 5bps, spread 1bps, slippage 2bps (engine
  defaults, untouched), funding = REALIZED venue calendar per symbol
  (`FUNDING-CAL-v1`, Binance `fapi/v1/fundingRate`, 90 settlements/symbol,
  8h nominal cadence, acquisition 2026-10-16, 3 requests).
- Sensitivity: every cell at cost scales 1x/2x/3x (runner `--scales`).
- NOT measured: venue spread/depth history is absent → slippage is an
  ASSUMED drag, never "measured slippage". The trading account (fee tier)
  is unknown → commissions are assumed, never "applicable fees". If a
  datum is missing it is excluded or conditioned; nothing missing is
  zeroed (funding outside calendar span = `uncovered`, never 0%).

## 5. Entry / stop / exit / open-position policy

- Entry: next known open after event time (engine; causal per chain check).
- Stop: 0.5% distance stop, gap-first at open (engine default; methodology
  unvalidated — a placeholder, never presented as a validated stop).
- Time exit: 1h horizon at last knowledge (reason `horizon`); data-end
  positions are MARKED `open_at_end` (never executed).
- Accounting: realized-only metrics primary (`total_net_realized`,
  `expectancy_net_realized`, `max_drawdown_realized`); legacy totals that
  include open marks are NEVER cited as performance. Realized drawdown is
  separated from open-mark valuation. Duration, MFE/MAE (demonstrated
  prints only), exit reasons, and funding quality reported per cell.
- Open positions carry hypothetical exit costs separated from executed
  costs (`costs_exit_hypothetical` vs `costs_executed`).

## 6. OOS labeling (honest)

- The eval segment is time-held-out under frozen v1 rules with zero tuning
  in this task. It is NOT a pristine reserve: descriptive P1-11C outcome
  summaries pre-exist on the same window, and the window itself is the only
  retained history. Label: `time-held-out (non-pristine)` — never "clean
  OOS". No positive conditioned result is read as demonstrated edge.
- Protocol for a future separate evaluation (not started): freeze rules +
  acquire a forward window never summarized before first replay + pre-commit
  the purge/cutoff + replay once.

## 7. Families executed

- Executed: `continuation` (H1), `correction-exhaustion` +
  `correction-reversal` (H2 legs, reported; INSUFFICIENT expected),
  `bearish-continuation` (H3). Per symbol (BTC/ETH/SOL) with pinned
  realized funding calendars (fail-closed identity).
- Excluded: `rebound-variant` (0 events, untestable), `baseline` pooled
  group (empty by construction; pooled reference computed in aggregation).
