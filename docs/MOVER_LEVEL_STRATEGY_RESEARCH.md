# Movers and Levels - Strategy Research Specification

**Status:** PROPOSED research design; NOT IMPLEMENTED as entry/position rules.
**Recorded:** 2026-10-11, following the user's strategy discussion and request to
preserve/evaluate it in documentation. Documentation authorization does not
authorize market runs, gate advancement, paper trading or execution.
**Owning backlog:** F-RES-MOVERS-01 through F-RES-VALIDATION-01; F-V2-RESEARCH-01.
**Source scope:** backend 55efaa2b171c83701f6736ab6e6374869a733af1,
read without changing its worktree; V2 documentation base
066577e75c9bc9a8f6d05e33b822481650ab2c7e. The two source trees are different.
Backend implementation statements below do not mean code was imported into V2.

## 1. Research objective and boundaries

Study Binance USD-M perpetual movers, with a separately verified small-market-cap
cohort, to determine whether level-based continuation and confirmed reversal
yield positive net expectancy with controllable losses. The +5%, +15% and
+20%-70% moves discussed by the user are observations/hypothesis cohorts,
not calibrated thresholds, price targets or expected profits.
Ranking selects research candidates; it never directly activates entry.
Watch emerging movers below +5% too, to avoid selecting only already-extended winners.
Compare small-cap and broader eligible cohorts; cheap unit price is not market cap.
Small-cap cutoffs, timeframes, level rules, confirmation duration, risk limits and
sample-size criteria remain OPEN and must be frozen before evaluation.

Distinguish: rolling 24h change; return since first known detection; retracement
from a known running peak; return after a simulated executable entry.
100 -> 170 is +70%; a 20% drop from 170 leaves 136, still +36% from 100.
Normalize arithmetic percentages versus internal log returns explicitly
(arithmetic return = exp(log_return)-1); never compare raw units silently.

## 2. What exists, and what the evidence does not prove

| Capability | Current evidence | Limit |
|---|---|---|
| Live return/momentum/flow/book/OI/VWAP/structure inputs | P1-04..P1-08, FEATURE_MODEL.md | Warm-up, freshness, coverage and units remain binding |
| State classifier | P1-12A v0.1.0, CLASSIFIER_SPEC.md | Descriptive hypothesis thresholds, no entry accuracy claim |
| Research setups | Backend opportunity.py v0.1.0 | Research priority and observed direction, no trade plan |
| Historical event path studies | P1-11C events.py | Bar/proxy resolution, gaps and ambiguity; not historical full book |
| Prospective setup outcomes | P1-14A/P1-14B contract v1.1, backend prospective.py | Endpoint mark returns, no simulated fills or prospective path MFE/MAE |
| Prospective flow/book aggregates | P1-11C research_recorder.py | Bounded aggregates; not full event-by-event executable depth history |
| External identity/market cap/catalyst adapters | Designs documented | NOT IMPLEMENTED/validated for this research |
| Entry, position manager, full cost backtest, paper | Phase 3/4 plans | NOT IMPLEMENTED/validated as these strategies |

Read-only SQLite snapshot at 2026-10-11T15:11:20.522359+00:00:
66 prospective setups, 228 COMPLETE outcome rows, 11 symbols.
Families: IGNITION_WATCH 19, MOMENTUM_CONTINUATION 7, EXHAUSTION_WATCH 13,
REVERSAL_WATCH 21, EXTREME_MOVE_RESEARCH 6.
Horizons: 1m 63, 5m 59, 15m 44, 1h 35, 4h 27.
Rows at different horizons of one setup are dependent. 228 rows are not 228
trades, 66 setups are not proven independent episodes, and COMPLETE rows do not
mean every setup has every horizon. No small-cap membership or profitability
is inferred from these counts. Historical windows remain historical; corrected
runtime longevity remains UNDEMONSTRATED.

## 3. Candidate research definitions

These are definitions to preregister and test, not added setup-family outputs.

| ID / priority | Hypothesis | Level and activation to study | Invalidation to freeze at T |
|---|---|---|---|
| H-A1 / FIRST | Long continuation after breakout/retest | Prior completed range resistance breaks; retest holds; renewed buying produces advance | Return into prior range / failure of the frozen retest support |
| H-B1 / FIRST | Short reversal after an extended rally | Failed high plus support loss; rebound cannot reclaim it; selling produces downside follow-through | Reclaim/acceptance above the frozen failed-rebound structure |
| H-A2 / SECOND | Long continuation after a trend pullback | Confirmed support/previous breakout; selling no longer produces downside displacement; buying resumes | Break of the frozen support/pullback low |
| H-C1 / SECOND | Short continuation in losers | Support breaks; weak rebound fails below it; renewed selling produces displacement | Acceptance back inside the prior range |
| H-D1 / DEFERRED | Long rebound in extreme losers | Selling absorption plus confirmed upward structure | Loss of the frozen recovery level |

Primary comparison is H-A1 versus H-B1 in their respective eligible episodes.
Do not demand a fixed NORMAL->IGNITION->EXPANSION sequence; actual classification
can overlap/skip states. Keep current engine rules/version unchanged.
EXHAUSTION UP describes the preceding up move losing strength. REVERSAL direction
describes the new confirmed direction. Neither is an executable LONG/SHORT.
Separate observed_move_direction from proposed_trade_side in future research;
the proposed side stays null until its preregistered strategy conditions pass.

Levels must be known at decision time: prior completed ranges, confirmed pivots,
previous completed day/week levels, or other explicitly frozen definitions.
Store source, timeframe, price basis, formation time, confirmation/available time
and invalidation. A pivot requiring right-side bars is available only after those
bars arrive (current live pivot design has a 30s confirmation delay).
Rolling VWAP windows currently available are 1m/3m/5m/15m; session/anchored VWAP
is a separate proposed feature, not existing under another label.

## 4. Evidence groups, not arbitrary indicator votes

| Group | Proposed research measurements | Interpretation guard |
|---|---|---|
| Discovery | 24h rank/change, short-window momentum, relative volume, time first selected | Rolling-window rank is not fresh acceleration or permission to enter |
| Participation | Aggressor buy/sell notional, delta, volume relative to trailing completed buckets | Correlated flow metrics are not independent votes |
| Price response | Displacement per executed aggressive flow near a level, failed high/low | Absorption is a hypothesis; weak response alone does not establish reversal |
| Positioning | OI quantity change versus value change, funding and interval | OI growth is not directional buying; value can rise because price rose |
| Liquidity | Spread, covered depth, persistence/recovery, estimated impact for proposed size | Visible walls may cancel; depth20 is bounded and cannot cover arbitrary size |
| Market context | Aligned BTC/market returns, relative return, later beta/correlation models | Beta-adjusted strength and causal lead/lag are not currently validated |
| External catalysts | Official event/source, announcement/first-seen/effective times, type | Only information available by T; no retrospective news attribution |

Compare complete feature groups incrementally against simple baselines.
Do not add RSI/MACD or a composite confidence score without incremental evidence.
Funding events must be deduplicated by distinct economic updates; repeated samples
are not independent evidence. Funding cost uses the actual contract interval.
Liquidation streams are partial snapshots, not exhaustive liquidation totals.

## 5. Proposed research-plan record (not a current API/schema)

Identity/strategy version/config hash; episode key; observed direction;
nullable proposed side; detection/decision/activation times; feature as-ofs;
data quality/missingness; immutable level definitions; entry condition/zone;
maximum chase price and expiry; frozen invalidation/stop; target zones;
maximum exposure duration and evidence-driven exit hypotheses; proposed
order type and limit-fill timeout; risk budget/size; spread/depth coverage;
cost model/version; evidence for/against; and explicit rejection/no-trade reason.

Separate discovery -> eligibility -> setup -> activation -> risk approval
-> simulated fill -> management -> exit. Existing DETECTED/WATCHING/
ACTIVE_RESEARCH are research lifecycle states; never reinterpret them as fills.
For a future signal, execution-grade data gates must be separately validated;
the current ~30s summary/classifier cadence and minimum-data gates do not
certify fast entry timing. No dashboard-rendered state feeds the engine.

## 6. Dataset and evaluation requirements

1. Preregister the primary definitions, cohort selection, parameter budget,
   horizons, minimum useful effect, precision criterion and rejection rules.
2. Capture all eligible candidates, rejected candidates and non-events/control
   windows; reconstruct universe eligibility as-of T, including delisted assets
   where data exists. Preserve selection bias if unavailable; do not use today's
   winners or today's market cap to relabel past cohorts.
3. Freeze full feature/quality/context/level snapshots at decision time.
   Existing prospective setup_json has evidence/missingness/freshness fields,
   not a demonstrated complete strategy feature vector.
4. Retain a path with declared sampling/coverage to calculate MFE/MAE, first
   stop/target touch and time-to-invalidation. Current endpoint-only prospective
   outcomes cannot supply this. Preserve contract v1.1; any extension requires
   a separate contract/schema decision and tests.
5. Record actual outcome observation time and lateness, separate nominal horizon.
   Endpoint COMPLETE is not proof of exact-time measurement or executable P&L.
   Missing/censored/grace outcomes never become zero or disappear from denominators.
6. Simulate executable entry/exit with spread, fees, impact, latency, funding
   when applicable, limit orders not filled, and gap/stop slippage. Mark price
   remains research context, not a fill. If depth coverage or intrabar order is
   insufficient, classify unavailable/ambiguous or apply a preregistered
   conservative assumption; never invent the missing path or liquidity.
7. Compare ranking-only, level-only and level-plus-evidence baselines; use
   chronological out-of-sample evaluation and episode clustering. Purge overlapping
   labels and use an embargo that accounts for actual late observation/holding
   windows. Hold out symbols/regimes where feasible; report concentration.
8. Report net expectancy and uncertainty, payoff distribution, drawdown,
   MAE/MFE capture, no-fill/rejection rate and exposure. Win rate below 50%
   alone does not kill a strategy. Stress costs at 1x/2x/3x per RISK_RULES.md.
9. Paper validation remains a later phase with its own authorization/gates;
   the retrospective maximum is never an attainable target by assumption.

## 7. Implementation sequence and unresolved work

| Order | Work / backlog | Completion evidence needed |
|---|---|---|
| 1 | Reconcile definitions/statuses and register proposals / this slice | Linked docs and bounded source evidence; no gate advance |
| 2 | As-of mover/identity/cohort contract / F-RES-MOVERS-01, F-CMC-01 | Stable asset mapping incl. contract multipliers, market-cap source/time and UNKNOWN tests |
| 3 | Frozen level definitions / F-RES-LEVELS-01 | Availability timestamps, pivot delay, no future leakage |
| 4 | Snapshot/path adequacy / F-RES-PATH-01 | Actual coverage, endpoint/path separation, missing/censored/ambiguous outcomes |
| 5 | BTC/participation/absorption studies / F-RES-CONTEXT-01 | Incremental out-of-sample improvement, source/unit alignment |
| 6 | Optional official catalyst ledger / F-RES-CATALYST-01 | First-available timing, stable identity, source attribution; no feed blocking |
| 7 | Costed H-A1/H-B1 comparison / F-RES-VALIDATION-01, F-BT-01 | Preregistered rules, executable simulation, grouped uncertainty and cost stress |
| 8 | Research UI / F-V2-RESEARCH-01 | Canonical read-only contracts, nullable unimplemented plan fields, visual verification |
| 9 | Later paper / F-PAPER-01 | Existing phase gates plus independently validated strategy; separate instruction |

Orders 2..9 are future proposals/dependencies, not the active backend correction
task and not permission to run probes. No new probability, sample cutoff,
capitalization cutoff, numeric risk limit or trigger is selected by this document.
Open decisions: executable instrument universe, market-cap definition/cutoff,
level basis, confirmation duration, desired holding horizon, path sampling,
costs/order types, acceptable risk budget and statistical precision.

## 8. Documentation ownership and official data references

STRATEGY_THESIS.md: objective and falsifiable A/B hypotheses.
SIGNAL_RESEARCH_PLAN.md: measurement/experiment definitions.
EVENT_LABELING.md: event clocks, endpoints, paths and denominators.
FEATURE_MODEL.md: feature units/availability; HISTORICAL_RESEARCH_PLAN.md: fidelity.
POSITION_MANAGEMENT.md / PAPER_TRADING.md / RISK_RULES.md: future simulation/limits.
FEATURE_BACKLOG.md: approvals, implementation and dependencies.
DASHBOARD_V2_DESIGN_SPEC.md / DASHBOARD_V2_API_CONTRACTS.md: proposed presentation.
CURRENT_STATE.md / TASK_QUEUE.md: factual checkpoint and operational boundaries.
SUCCESS_GATES.md is unchanged; no phase is completed by documenting a proposal.

Official references checked 2026-10-11 during the strategy review:
- [Binance rolling 24h ticker](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics)
- [Binance OI statistics](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics)
- [Binance liquidation snapshot stream](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams)
- [Binance funding](https://www.binance.com/en/support/faq/detail/360033525031)
External endpoint access/quotas and identity mapping need their own verified
integration; this documentation adds no requests, credentials or paid service.
