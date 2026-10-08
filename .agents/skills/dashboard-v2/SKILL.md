---
name: dashboard-v2
description: Implement or review Dashboard V2 slices in this Binance Futures repository while preserving the Python backend, real-data contracts, visual verification, and observe-only safety.
---

# Dashboard V2

Use this skill only for Dashboard V2 architecture, design, API-contract,
migration, or implementation work in this repository.

## Start here

1. Read `AGENTS.md`, `docs/CURRENT_STATE.md`, and `docs/TASK_QUEUE.md`.
2. Read `docs/DASHBOARD_V2_PROGRESS.md` and
   `docs/DASHBOARD_V2_DECISIONS.md` before changing the V2 plan.
3. Check `docs/FEATURE_BACKLOG.md` for the relevant feature IDs (V2 state
   presentation, BFF, CMC) and their approval vs implementation status.
4. Route the task to the narrowest relevant source:
   - UI and visual behavior: `docs/DASHBOARD_V2_DESIGN_SPEC.md`
   - frontend boundaries: `docs/DASHBOARD_V2_FRONTEND_ARCHITECTURE.md`
   - data shapes: `docs/DASHBOARD_V2_API_CONTRACTS.md`
   - sequencing and gates: `docs/DASHBOARD_V2_MIGRATION_PLAN.md`
   - external data: `docs/COINMARKETCAP_FEASIBILITY.md`,
     `docs/TOKEN_IDENTITY_MAPPING.md`, and
     `docs/EXTERNAL_MARKET_DATA_EVALUATION.md`

## Required loop

`AUDIT -> PLAN -> IMPLEMENT -> TEST -> VISUAL VERIFY -> DOCUMENT -> CHECKPOINT -> NEXT`

- Preserve the Python market-data and research engines as the source of truth.
- Treat the frontend as a visualization/control client; it must never make
  trading decisions or bypass backend risk controls.
- Render only real API data. Preserve `UNKNOWN`, stale, partial, warming, and
  unavailable states instead of inventing values or demo rows.
- Keep units, formatting, nullability, provenance, and capability semantics
  explicit. Use stable external IDs for enrichment joins, never symbols alone.
- For visual slices, compare fresh browser captures against the approved
  reference before declaring PASS. Do not infer a visual PASS from tests.
- Run targeted checks and `python run_tests.py`; update factual docs; stage
  only the coherent files for the slice.

Stop when a task requires live trading, secrets, a strategy/methodology
change, an unapproved destructive migration, or evidence contradicts the plan.


## Binding visual targets — approved 2026-10-08

Before implementing, open `design/references/v2-approved/README.md` and the matching PNG reference. These eight image assets are the intended UI outcome, not optional inspiration. Compare fresh browser screenshots at desktop and narrow width with the approved target, record discrepancies and deliberate departures. Figures/graphs/states depicted in the mockups are illustrative; source-backed data, timestamp, freshness, coverage, safety and missing-data discipline override visual parity. Only claim design fidelity to the extent verified.
