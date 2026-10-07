# SIGNAL_RESEARCH_PLAN

Future setup/signal research (P1-12 → P1-16 consumers). Design only — NOT
implemented in P1-11A. No thresholds tuned, no signals emitted, no trading
logic added. Raw features validated in P1-11A are the only inputs referenced.

## BTC context features (design — to be built, not yet built)

For every alt symbol S, alongside its own validated features, compute:

- BTC return / velocity / acceleration (same horizons, same math).
- BTC aggressive flow (delta, ratio, z) and BTC OI (deltas, contexts).
- BTC volatility and BTC structure state (range position, breakout state).

Derived research quantities (all timestamped, no lookahead):

- Relative return vs BTC: R_S(h) − R_BTC(h) per horizon.
- Rolling correlation: corr of 10s-bucket log returns over trailing windows
  (window lengths are a P1-11C decision, not fixed here).
- Beta-adjusted residual: R_S − β·R_BTC with β from trailing regression.
- Lead/lag: cross-correlation of BTC flow/velocity vs S returns at small
  lags (descriptive first; predictive claims require P1-11C samples).

## Exhaustion / reversal watch (research hypotheses, NOT signals)

An EXTENDED GAINER is a continuation candidate AND an exhaustion/reversal
watch simultaneously. Potential short-side evidence to study (each must
earn its place in P1-11C event studies before any weight):

- Velocity deceleration (positive but falling 1m velocity).
- Negative 1m acceleration while price still pushes high.
- Failed high / lower high (confirmed pivots, 30s delay applies).
- VWAP loss (displacement turning negative after premium).
- Aggressive buy share falling / aggressive sell rising (flow horizons).
- Signed delta turning negative across 1m→5m→15m.
- Price failing to respond to buy aggression (see absorption).
- OI regime change (e.g. PRICE_UP_OI_UP → PRICE_DOWN_OI_UP with falling delta).
- Book imbalance flipping ask-heavy into the push.
- BTC context deteriorating (BTC velocity/accel rolling over).

Mirror set applies to extended losers. None of these is a trigger today.

## Absorption (measurable concept, design)

- BUY ABSORPTION: large aggressive buy flow + weak/no upward price response
  (upper-tail buy notional or +z with ≤0 contemporaneous displacement and
  flat/negative short-horizon return).
- SELL ABSORPTION: large aggressive sell flow + weak/no downward response.

Current data sufficiency: trailing-window flow aggregates (notional, delta,
z per 10s…15m) + mark returns + VWAP displacement already allow a first
descriptive definition. What is missing for rigorous study: retained
per-trade (or finer-bucket) flow history to test threshold stability, and
book depth history for the liquidity side of the absorption claim
(Phase 2 retention scope).

## Market-state classifier (P1-12, still BLOCKED until P1-11 passes)

States NORMAL / IGNITION / EXPANSION / EXHAUSTION / REVERSAL
(`docs/MARKET_STATES.md`). All thresholds HYPOTHESIS. May only consume
P1-11A-validated raw features + UNKNOWN/staleness as first-class input
(degradation starves features honestly — the classifier must not treat
starved UNKNOWN as calm). Dynamic live universe (P1-12B) and the
opportunity/setup engine (P1-13A) follow the classifier, never precede it.

## Opportunity lifecycle (P1-13A design)

DISCOVERED → WATCH → DEVELOPING → CONFIRMED → PAPER ENTRY → HOLD →
DETERIORATING → INVALIDATED / EXIT. A future opportunity output may carry
direction, historical confidence + sample size, entry zone,
invalidation/stop, target zones, expected horizon, reasons, risks.
Opportunities UX (P1-13B): OVERVIEW / MOVERS / OPPORTUNITIES / PAPER LAB /
BACKTEST / SYSTEM nav; ranking is dynamic and evidence-linked, never an
entry list.

## Backtest vs forward paper (P1-14 / P1-15 design)

- Historical backtest replays retained bars/events with the event clock
  frozen at T (no future leakage by construction — same as-of discipline
  as the live engines).
- Forward paper test simulates live entry against the real feed with the
  validated feature pipeline.
- Both must eventually account for spread, fees, slippage, latency,
  funding where relevant, entry price, stop, target, and dynamic exit.
  No real orders at any stage without explicit human authorization.
