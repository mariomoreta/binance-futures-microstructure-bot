# STRATEGY_THESIS

Status: **HYPOTHESIS ONLY.** Nothing below is statistically validated.
No threshold here authorizes entries, paper or live.

## Hypothesis A — Momentum / Continuation

```text
NORMAL → IGNITION → EXPANSION → CONTINUATION
```

A move ignites (rank velocity + volume acceleration + aggressive-flow imbalance),
expands (range expansion + realized-volatility lift + OI confirmation), and in a
subset of cases continues long enough to be exploitable after costs.

What would confirm it: forward-return distributions conditioned on
IGNITION/EXPANSION features skew positive at 1m–15m horizons after fees/slippage,
with out-of-sample stability. See `docs/EVENT_LABELING.md`.

What would kill it: continuation rate ≈ coin flip after costs, or continuation
concentrated in untradeable micro-windows (spread + slippage > edge).

## Hypothesis B — Exhaustion / Reversal

```text
EXPANSION → EXHAUSTION → REVERSAL CONFIRMATION
```

After violent expansion, a subset of moves exhausts (velocity decay, volume climax,
book-imbalance flip, liquidation cascade, funding extreme) and reverses.

What would confirm it: negative forward returns conditioned on EXHAUSTION
features, with MFE/MAE asymmetry favoring fade entries after confirmation —
never anticipatory catching of falling knives.

What would kill it: reversals unpredictable from observable features, or
reversal-window volatility making risk-adjusted expectancy negative.

## How hypotheses become strategies

1. Phase 1: measure the features (`docs/FEATURE_MODEL.md`).
2. Phase 2: persist snapshots + forward outcomes (`docs/EVENT_LABELING.md`).
3. Phase 3: statistical discovery + backtesting with costs (`docs/PAPER_TRADING.md`).
4. Phase 4: live paper trading + position management (`docs/POSITION_MANAGEMENT.md`).
5. Phase 5: controlled execution — only with explicit human authorization.

## Rules

- A large 24h move alone is NEVER an entry signal.
- `HUMAN_STRATEGY_HYPOTHESIS` (trade strong movers, hold minutes-to-an-hour
  dynamically) is input to research, not a conclusion.
- Initial market-state thresholds are hypothesis-only until evidence exists
  (`docs/MARKET_STATES.md`).
- The system must learn position duration from post-entry feature evolution,
  not from a universal fixed number of minutes (`docs/POSITION_MANAGEMENT.md`).
