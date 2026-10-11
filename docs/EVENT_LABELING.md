# EVENT_LABELING

**Status:** historical labeling foundations exist; prospective endpoint outcomes
exist in the canonical backend; full strategy snapshot/path/fill evaluation
remains PARTIAL / PROPOSED. Updated 2026-10-11.
This replaces the obsolete statement that no persistence/labeling exists.
No phase gate, schema, horizon list or implementation is changed here.
See [Movers and Levels](MOVER_LEVEL_STRATEGY_RESEARCH.md).

## Distinct implemented measurement surfaces

| Surface | Existing horizon/measurement | Fidelity limit |
|---|---|---|
| P1-11C historical events.py | 1m/3m/5m/15m/30m/1h forward outcomes, direction-oriented MFE/MAE, time-to and frozen invalidation from bars | Bar resolution/proxy labels/gaps; sub-hour outcomes on hour bars are not independent precise intrabar paths |
| P1-14A/P1-14B canonical prospective.py, contract v1.1 | 1m/5m/15m/1h/4h mark-price endpoints after detection | Actual observation may be late; no prospective path MFE/MAE or executable P&L |
| Prospective research_recorder.py | Flow 10s/1m aggregates and book 1m summaries | Bounded aggregates, not historical reconstructed full books or fills |

The original Phase 2 30s/1m/3m/5m/15m/30m/60m requirements are future requirements
where unsupported. They do not silently replace either implemented horizon list.
Canonical backend evidence: 55efaa2; see
[prospective contract v1.1](https://github.com/mariomoreta/binance-futures-microstructure-bot/blob/55efaa2b171c83701f6736ab6e6374869a733af1/docs/PROSPECTIVE_EVALUATION_SPEC.md).
No backend module was imported into the V2 branch by this documentation update.

## Event clock and availability
Freeze decision T using only information available by T. Distinguish exchange
event time, receipt time, clock offset, detection time, decision time, level
confirmation/available time, simulated activation/fill time and actual outcome
observation time. Preserve original time bases; no undocumented host/exchange
conversion or backdated observation. A later-confirmed pivot/news item cannot
appear earlier in a decision snapshot.
Current prospective snapshots retain candidate/evidence/missingness/freshness,
not a proven complete strategy feature vector. A proposed extension must
preserve existing schema/contract and be independently designed/tested.

## Future snapshot requirements - F-RES-PATH-01
Stable episode/candidate/strategy/config identifiers; venue instrument plus
external asset mapping; observed direction and nullable proposed trade side;
eligible universe/rank/market-cap source and as-of; full raw feature vectors
with units/source/warm-up/freshness; contemporaneous BTC context; immutable
level definitions; data gaps and rejected inputs; supporting/conflicting
evidence; catalyst first-available time; rejection/no-trade reason.
Selection, trigger, invalidation and cost assumptions are frozen before outcome.

## Future path and executable labels
Measure forward return, MFE/MAE, time-to-peak/trough, first stop/target touch,
time-to-invalidation, continuation/reversal and time to deterioration from a
path whose sampling/coverage is declared. Orient trade labels by a preregistered
proposed side, never mechanically by EXHAUSTION's observed prior direction.
Raw mark return remains separate from executable net return.

Missing path, unsampled extrema, bar ambiguity or insufficient depth is
UNAVAILABLE/AMBIGUOUS/GAP, not fabricated precision. If both stop and target
fall inside a bar and order is unknown, apply only a preregistered conservative
assumption or exclude with an explicit reason and denominator.
Keep endpoint actual observed_at/lateness alongside nominal horizon. COMPLETE
describes the current endpoint contract, not exact-time fills or full episodes.

## Sample accounting and validation
Record eligible non-events, rejects, unfilled orders and censored outcomes.
Multiple horizons/families of one move are dependent; group symbol/episode
and purge overlap across chronological splits, using actual observed/holding
windows. Report outcomes present/absent per eligible episode; 228 existing
rows are not 228 trades and 66 keys are not proven independent episodes.
Never zero-fill missing returns or silently drop failed/late observations.
Historical OHLC/volume proxies do not recreate live microstructure.
Costs are separate versioned analysis assumptions; strategy gates require net
expectancy, risk and out-of-sample evidence, then later paper verification.
