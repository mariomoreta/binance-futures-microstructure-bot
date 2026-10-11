# SIGNAL_RESEARCH_PLAN

**Current foundations exist; strategy signals do not.** Updated 2026-10-11.
Detailed proposed experiment: [Movers and Levels](MOVER_LEVEL_STRATEGY_RESEARCH.md).
Current backend evidence is at 55efaa2, separate from the V2 source snapshot.

## Existing versus future
P1-12A classifier, P1-12B dynamic universe and P1-13A research opportunities
exist in the canonical backend. P1-11C historical events/path outcomes and
prospective flow/book aggregates exist; P1-14 prospective contract v1.1 records
setup endpoint mark returns. These do not constitute validated trading signals.
The older "classifier blocked", "nothing persisted" and lifecycle mixing below
are replaced by this current/future separation; no source behavior is changed.

## Preregistered primary questions
- H-A1: does breakout/retest continuation outperform ranking-only and level-only
  baselines after costs, including failed breakouts and unfilled orders?
- H-B1: does support loss plus failed reclaim after an extended rally produce
  tradable downside with tolerable MAE, outperforming simply fading high 24h gains?
Secondary: H-A2 trend pullback, H-C1 loser continuation. H-D1 loser rebound deferred.
Freeze cohort selection, definitions, features, units, availability, activation,
invalidation, exits, parameter budget and precision criterion before testing.

## Context and absorption
Existing BTC raw returns/flow/OI/structure may be time-aligned. Historical P1-11C
already supplies limited relative-return context; a complete live BTC-relative
strategy contract, rolling beta/correlation and predictive lead/lag remain proposals.
Do not label design-level BTC models implemented because raw BTC data exists.

Buy absorption hypothesis: aggressive buying with weak upward response near
known resistance. Sell absorption: aggressive selling with weak downward
response near known support. Test persistence and subsequent structure; neither
is automatically a reversal. Aggregated prospective flow/book retention does
not recreate event-level liquidity, queue position or sweep recovery.
OI quantity and value differ; OI increase is not a directional long signal.
Funding repeated samples are not independent updates; use actual funding intervals.
Order-book walls alone are insufficient corroboration.

## Selection and experiment control
Broad discovery and subscribed CORE/HOT data stay distinct. Freeze eligible
universe/rank/market-cap identity as-of T and retain rejects/control windows.
Missing market cap cannot silently enter a small-cap cohort. Preserve missing
history/delistings as a study limitation, not survivorship-filtered confidence.
Prevent double-counting correlated indicators and multiple horizons of one setup.
Compare incremental feature groups and record conflicting evidence.

## Lifecycle separation
Existing research: DETECTED -> WATCHING -> ACTIVE_RESEARCH ->
INVALIDATED/EXPIRED/UNKNOWN.
Proposed future strategy: discovery -> eligibility -> setup -> activation ->
risk approval -> simulated fill -> management -> exit.
These are separate records/state machines. Research activation is not a fill.
observed_move_direction and nullable proposed_trade_side are separate concepts.
No proposed field here changes a current API or adds LONG/SHORT recommendations.

## Required measurements and validation
- Full frozen feature/quality/level snapshots plus actual availability times.
- Path MFE/MAE, first stop/target touch and time-to-invalidation with gap/coverage
  flags; ambiguity/unavailable when sampling cannot decide the path.
- Executable entry/exit simulation, spread/fees/impact/latency/funding, no-fills.
- Endpoint actual observed time/lateness; no implicit exact-horizon assumption.
- Chronological out-of-sample and episode grouping; purge overlapping labels,
  embargo accounting for actual observed/holding windows; concentration reports.
- Net expectancy with uncertainty, drawdown, payoff tails and 1x/2x/3x cost stress.
No universal sample count or probability is invented. Paper remains Phase 4.

## Ownership and dependencies
F-RES-MOVERS-01: eligibility/identity; F-RES-LEVELS-01: frozen levels;
F-RES-PATH-01: full snapshots and paths; F-RES-CONTEXT-01: incremental evidence;
F-RES-CATALYST-01: optional timestamped official events; F-RES-VALIDATION-01:
costed comparisons; F-V2-RESEARCH-01: read-only presentation.
See FEATURE_BACKLOG.md, EVENT_LABELING.md, HISTORICAL_RESEARCH_PLAN.md,
POSITION_MANAGEMENT.md, PAPER_TRADING.md and RISK_RULES.md.
All new implementation work remains PROPOSED / NOT IMPLEMENTED. Current backend
corrections and phase gates remain separate; no new run is authorized.
