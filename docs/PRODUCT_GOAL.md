# PRODUCT_GOAL

Build a Binance Futures market-intelligence system that can:

1. Monitor the Futures universe in real time.
2. Identify rapidly moving symbols before/while they become major gainers or losers.
3. Understand the market conditions associated with those moves.
4. Classify market state.
5. Study continuation vs exhaustion/reversal.
6. Persist event snapshots.
7. Calculate forward outcomes statistically.
8. Discover evidence-backed strategies.
9. Paper trade them.
10. Dynamically manage position duration and exits.
11. Only after proven paper profitability, consider controlled automated execution.

## Final KPI

**Profitability and risk-adjusted expectancy.** Nothing else counts as success.

Explicitly NOT success metrics:

- Code volume
- Number of indicators
- Number of detected signals
- Dashboard polish without statistical backing
- Backtest returns without costs, slippage, and out-of-sample validation

## Anti-goals (until proven)

- A large 24h move alone must NEVER be treated as an entry signal.
- Never promise a fixed future profit such as "$30 expected". Future projections must be probabilistic distributions grounded in historical similar cases.
- No fixed holding time (e.g. "always hold 20 minutes"). Trade duration must be evidence-driven and market-state-driven.

## Human strategy hypothesis (unproven)

The user's historical manual approach involved trading unusually strong movers and
holding positions dynamically — roughly several minutes to sometimes around one hour —
depending on how the move evolved.

Status: `HUMAN_STRATEGY_HYPOTHESIS`. It informs what to measure (forward outcomes at
30s→60m, MFE/MAE, time-to-peak/trough, continuation vs reversal), but it is NOT
evidence and NOT an approved strategy. See `docs/STRATEGY_THESIS.md` and
`docs/EVENT_LABELING.md`.
