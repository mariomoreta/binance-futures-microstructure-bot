# DASH-V2-53 — Mover/level research documentation

**Result:** DONE bounded documentation; no general strategy PASS.
**Date:** 2026-10-11.
**Branch:** dash-v2-03-token-detail.
**V2 starting SHA:** 066577e75c9bc9a8f6d05e33b822481650ab2c7e.
**Canonical backend reviewed read-only:** 55efaa2b171c83701f6736ab6e6374869a733af1.
Backend had active owner edits in control.py; no backend worktree mutation.
This report belongs to the documentation commit; its containing Git commit is the ending checkpoint.

## AUDIT

Compared strategy intent with classifier, opportunity rules, historical event studies, prospective contract v1.1 and aggregate recorder. Read-only SQLite snapshot at 2026-10-11T15:11:20.522359+00:00: 66 setups / 228 COMPLETE endpoint rows / 11 symbols. Multiple horizons are dependent; setup keys are not demonstrated independent episodes. No profitability, small-cap membership or exhaustive horizon coverage inferred.

Identified dated documentation conflicts: classifier/persistence described as absent; extreme-move prose differed from actual return-based rule; descriptive direction/lifecycle mixed with trading; historical-bar paths and prospective endpoints conflated; win-rate-only rejection omitted payoff/costs. Reconciled current capability with source SHA and retained historical evidence.

## PLAN / IMPLEMENT

Central specification: [MOVER_LEVEL_STRATEGY_RESEARCH.md](MOVER_LEVEL_STRATEGY_RESEARCH.md).
Updated STRATEGY_THESIS, SIGNAL_RESEARCH_PLAN and EVENT_LABELING; added source-scoped OPPORTUNITY_ENGINE_SPEC. Added research requirements to FEATURE_MODEL, HISTORICAL_RESEARCH_PLAN, CLASSIFIER_SPEC, MARKET_STATES, POSITION_MANAGEMENT, PAPER_TRADING and RISK_RULES. Updated MASTER_PLAN, ROADMAP, ARCHITECTURE, FEATURE_BACKLOG, CURRENT_STATE and TASK_QUEUE. Appended decisions and V2 design/API/progress/visual-roadmap dependencies.

Primary proposed studies: H-A1 long breakout/retest continuation; H-B1 short confirmed reversal. Secondary H-A2/C1; deferred H-D1. Percentage cohorts are hypotheses, not triggers. Seven backlog proposals describe as-of cohorts, frozen levels, snapshot/path adequacy, participation/context, optional catalysts, costed validation and truthful V2 presentation. Numeric parameters remain open pending preregistration.

## TEST / VISUAL VERIFY

Canonical V2 snapshot regression: python run_tests.py — 496/496, exit 0, 72.304s.
This validates the existing V2 Python snapshot, not backend owner's dirty worktree or strategy profitability.
Documentation checks: new content UTF-8 (historical mixed-encoding sections preserved), explicit docs-only change set, required relative links, unique canonical proposal headings, count totals, forbidden stale claims removed, unchanged SUCCESS_GATES and git diff --check.
Visual verification: NOT APPLICABLE; no frontend or runtime change.
No probes, downloads/backfills, paper, live orders, Start activation or gate advancement.

## DOCUMENT / CHECKPOINT / NEXT

Research implementation remains PROPOSED / NOT IMPLEMENTED. Existing backend correction ownership retains priority. Follow dependency sequence in the central specification after separate scope/contract decisions; this checkpoint does not schedule market runs. Main and backend branch are outside this commit. Preserve database/logs/evidence and pre-existing untracked files.

- DECISIONS_REVIEWED: project/V2 decisions, thesis, research/labeling/features/risk/phase docs and V2 workflow.
- NEW_DECISIONS_RECORDED: discussion preserved; H-A1/H-B1 and seven implementation requirements PROPOSED; no calibrated rule or execution approval.
- FEATURES_IMPLEMENTED: documentation and traceability only.
- FEATURES_VERIFIED: docs consistency and existing V2 snapshot regression; no strategy/UI feature verified.
- DEFERRED_FEATURES: F-RES-MOVERS-01, F-RES-LEVELS-01, F-RES-PATH-01, F-RES-CONTEXT-01, F-RES-CATALYST-01, F-RES-VALIDATION-01, F-V2-RESEARCH-01; existing CMC/backtest/paper dependencies.
- BACKLOG_UPDATED: seven stable proposals with ownership, dependencies and acceptance criteria.
- DOCUMENTATION_CONFLICTS: current absence claims corrected; dated branch-specific inventories qualified; current families and endpoint/path limitations explicit.
