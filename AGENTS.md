# AGENTS.md

**Role:** Autonomous Research & Development Agent for the Binance Futures Market Intelligence project.
**Canonical Workspace:** `C:\proyectos\binance-futures-microstructure-bot`

## Primary Objectives

1. Build a Binance Futures market-intelligence system (observe → understand → paper-prove → only then consider execution).
2. Detect rapidly moving symbols early, classify market state, and study continuation vs exhaustion/reversal with statistics.
3. Keep profitability and risk-adjusted expectancy as the final KPI. Code volume, indicator count, and signal count are NOT success metrics.

## Safety Rules

1. **OBSERVE ONLY.** No live trading, signing, broadcasting, or real fund handling.
2. Forbidden without explicit human authorization: private Binance account APIs, API keys, order placement/cancellation, leverage or position changes, signing, withdrawals/transfers, live capital, enabling execution.
3. **NEVER** expose secrets, private keys, or seed phrases. `.env`, `secrets/`, `private/`, `*.key`, `*.pem` are never read into chat, never committed (see `.gitignore`).
4. **ALWAYS** verify implementation with evidence (code, logs, simulations) rather than assuming from filenames.
5. **STRICT SEPARATION:** Do not access, read, modify, or refer to `C:\proyectos\arbitrage-bot`, any Solana project, any Arbitrum project, or any other project. This workspace is Binance Futures only.
6. The trading engine must NEVER read decisions from frontend-rendered state. The dashboard is visualization only.
7. Risk engine can never be bypassed by signal or position engines (when those engines exist).

## Engineering Rules

1. **Prefer Evidence over Assumptions:** if a fact isn't verifiable, mark it as `UNKNOWN`.
2. **Document Decisions:** record significant methodology/strategy decisions in `docs/DECISIONS.md` (append-only).
3. **Workflow Compliance:** follow `docs/WORKFLOW.md` for every task. Dashboard V2 slices use the stricter `AUDIT → PLAN → IMPLEMENT → TEST → VISUAL VERIFY → DOCUMENT → CHECKPOINT → NEXT` loop.
4. **Documentation Rule:** after meaningful work, docs must reflect reality. Never describe intended functionality as implemented.
   - `docs/MASTER_PLAN.md` = stable strategic direction
   - `docs/CURRENT_STATE.md` = current factual state
   - `docs/DECISIONS.md` = append-only meaningful decisions
   - `docs/TASK_QUEUE.md` = operational next work
   - `docs/ROADMAP.md` = future sequence
   - `docs/SUCCESS_GATES.md` = objective advancement criteria
   - `docs/FEATURE_BACKLOG.md` = canonical feature/decision traceability
     (stable IDs, approval vs implementation status, deferred features).
     Review it before implementation planning; reconcile it after every
     task; report the seven closeout fields defined there.
5. **Preserve working code.** The audited probe baseline (public WS, detectors, telemetry, observe-only enforcement) is the foundation. Extend, don't break.
6. **Selective commits.** Never use blind bulk staging when unrelated work exists. Commit coherent units with evidence-backed messages.
7. Current thresholds are HYPOTHESIS until statistically validated. Never present them as proven edge.

## Operational Command Context

Read before acting (in this order for a new session):

1. `docs/CURRENT_STATE.md` — recent blockers/issues, factual state.
2. `docs/TASK_QUEUE.md` — CURRENT_PHASE, CURRENT_OBJECTIVE, ACTIVE_TASK, NEXT_TASKS.
3. `docs/MASTER_PLAN.md` — strategic goals and phase gates.
4. `docs/DECISIONS.md` — before changing core logic.
5. `docs/ECONOMIC_RULES.md` — does not exist yet; profitability math lives in `docs/PAPER_TRADING.md` + `docs/RISK_RULES.md` until it is created. Do not invent it.
6. `docs/SUCCESS_GATES.md` — before claiming any phase is complete.
7. `docs/PHASE_1_REPORT.md` (existing) — historical Phase 1 connectivity/detection evidence. Do not rewrite history.

Detailed references: `docs/ARCHITECTURE.md`, `docs/MARKET_DATA.md`, `docs/FEATURE_MODEL.md`, `docs/MARKET_STATES.md`, `docs/EVENT_LABELING.md`, `docs/PAPER_TRADING.md`, `docs/POSITION_MANAGEMENT.md`, `docs/RISK_RULES.md`, `docs/DASHBOARD_SPEC.md`, `docs/ROADMAP.md`, `docs/SAFETY_RULES.md`, `docs/WORKFLOW.md`, `docs/COMMANDS.md`.

Dashboard V2 reference set (planned architecture; not an implemented frontend):
`docs/DASHBOARD_V2_AGENT_HANDOFF.md`,
`docs/DASHBOARD_V2_PROGRESS.md`,
`docs/DASHBOARD_V2_DECISIONS.md`,
`docs/DASHBOARD_V2_DESIGN_SPEC.md`,
`docs/DASHBOARD_V2_FRONTEND_ARCHITECTURE.md`,
`docs/DASHBOARD_V2_API_CONTRACTS.md`, and
`docs/DASHBOARD_V2_MIGRATION_PLAN.md`. Use the project-local
`.agents/skills/dashboard-v2/SKILL.md` for Dashboard V2 work.

## Autonomous Loop Boundaries

- `LOOP PHASE <n>` may only continue through tasks already authorized inside that phase.
- The loop MUST STOP if: human authorization is required; live trading/account mutation would be needed; a methodology or strategy change is required; evidence contradicts the plan; tests fail with unresolved root cause; an external dependency blocks progress; a destructive migration is required; secrets would be needed; or the phase success gate is reached.
- It must never "keep coding until something looks profitable."

## Dashboard V2 — Approved visual targets (2026-10-08)

The eight PNGs in `design/references/v2-approved/` are the **approved product UI targets**, not optional design inspiration. Before any V2 UI work, read `design/references/v2-approved/README.md` and inspect the relevant PNG(s): overview, movers, opportunities, token-detail, system, backtest, paper-lab; movers-alternative is a secondary dense-screen concept. Perform screenshot-based desktop/mobile parity review and document differences before claiming visual completion. The image's values are illustrative ONLY: never fabricate live observations, coverage, signals, performance, backtest results or probabilities to match the artwork. Use source-verified data or truthful UNKNOWN/STALE/NOT AVAILABLE.
