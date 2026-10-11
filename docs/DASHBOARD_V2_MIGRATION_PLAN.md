# Dashboard V2 Migration Plan


## Current implementation checkpoint — 2026-10-11
The 2026-10-07 plan below is historical. V2 is implemented at loopback port 3020; main persisted-data migration is DASH-V2-63. See its migration matrix/report and canonical data contract. Old SSR retained; full cutover gate NOT accepted. The backend/control authority and collector remain unchanged. The next migration phase is an exhaustive legacy-function coverage audit, not another demo scaffold.


**Purpose:** migrate presentation in parallel while preserving the verified
Python backend and current dashboard.  
**Status at 2026-10-07:** PLAN APPROVED; NO MIGRATION IMPLEMENTED (historical; current checkpoint above).
**Date:** 2026-10-07.

## Invariants

- Existing Python dashboard stays available at `http://127.0.0.1:8091` unless
  its own safe first-free policy selects another port.
- Proposed Next.js default `127.0.0.1:3000` is checked before use; no process is
  killed for a conflict.
- No MarketProbe/formula/history/recorder/registry/control behavior changes as
  a side effect of frontend work.
- No second process manager, browser SQLite, credentials, live trading or
  dashboard-to-engine decision path.
- Every slice is independently reversible and keeps Python SSR usable.

## Stages

### DASH-V2-ARCH — this documentation checkpoint

Architecture, design tokens, current/missing API contracts, provider study,
identity policy, migration gates, agent handoff and project-local skill.
Acceptance: docs/link/path checks; full Python suite green; no production code,
runtime or dependency change.

### DASH-V2-00 — scaffold and primitives

Create `frontend/`, strict TypeScript/App Router, shell, tokens, status/source/
freshness components, test harness and an allowlisted read-only BFF skeleton.
No live controls. Acceptance: build/lint/type/unit/E2E shell checks, screenshot
comparison with supplied references, Python suite green.

### DASH-V2-01 — Overview

Implement versioned overview facade/BFF, real health/pulse blocks and honest
external-context placeholders. Acceptance covers all capability/freshness
states, real-data screenshot and no fabricated metrics.

### DASH-V2-02 — Movers

Typed paginated/filterable table, real sparklines and numeric contracts.
Acceptance re-proves category field/unit isolation and sign-filtered velocity.

### DASH-V2-03 — Symbol Detail

Chart and feature/research panels, history-only routes, identity/profile
surface. Acceptance includes `ORCAUSDT` historical-only and `龙虾USDT`
unknown-mapping fixtures, partial/warming/stale/degraded/unknown states.

### DASH-V2-04 — System and control

Diagnostics plus secure BFF integration with the existing control plane.
Acceptance: nonce never reaches browser; Origin/Host/CSRF/allowlist tests;
short bounded observe start/status/stop only when explicitly authorized; no
runtime interruption during ordinary tests.

### DASH-V2-05 — Opportunities shell

Explanatory capability/blocked shell and future typed contract. No candidates,
probabilities or trade fields until P1-12/P1-13A provide them.

### DASH-V2-06 — advanced charting/history

Incremental chart series, comparable source-labeled context and historical
projections. Add TradingView attribution if Lightweight Charts is adopted.

### CMC-00 / CMC-01 / CMC-02

- CMC-00: provider feasibility fixtures + identity mapping persistence design.
- CMC-01: bounded keyless ID/metadata adapter only after approval.
- CMC-02: optional quotes/indices/context only if measured research value and
  licensing/budget remain acceptable.

No provider work is required to deliver core Binance screens.

## Slice workflow

`AUDIT -> PLAN -> IMPLEMENT -> TEST -> VISUAL VERIFY -> DOCUMENT -> CHECKPOINT -> NEXT`

Each slice records starting/ending SHA, files, exact commands/results,
screenshots, known gaps and the next gate in `DASHBOARD_V2_PROGRESS.md`.
Stage only coherent intended files. Stop on unresolved tests, security
weakening, missing reference decisions, provider/legal uncertainty, engine
methodology change or need for credentials/runtime disruption.

## Cutover gate

Do not retire Python SSR until V2 covers Overview, Movers, Symbol Detail and
System/control with parity tests; survives a bounded parallel observation;
passes security/accessibility/visual checks; and the operator explicitly
approves cutover. Retirement is a later task, not implied by V2 completion.

## Phase dependencies

P1-10R is PASS (2026-10-08); P1-12A classifier v0 is DONE. P1-12B and
functional Opportunities, Backtest and Paper Lab remain bound to their
engine phases (see `docs/FEATURE_BACKLOG.md` F-UNI-01, F-OPP-01,
F-BT-01, F-PAPER-01). Documentation work does not advance those gates.

## DASH-V2-64 - next coverage sequence
Current exhaustive coverage assessment and retirement criteria: DASHBOARD_V2_64_CUTOVER_AUDIT.md. Search/token fields -> ranges/exports -> historical studies/diagnostics -> reversible presentation cutover. Start/operating readiness and future research are separate gates. Backend contract/deployment handoff: DASHBOARD_V2_64_BACKEND_HANDOFF.md.
