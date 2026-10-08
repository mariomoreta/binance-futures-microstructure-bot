# Dashboard V2 Agent Handoff

**Purpose:** let Codex, Muse Spark or another agent continue without the
original conversation.  
**Status:** READY AFTER DASH-V2-ARCH CHECKPOINT.  
**Date:** 2026-10-07.

## Read first

1. `AGENTS.md`
2. `docs/CURRENT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/MASTER_PLAN.md`
3. `docs/DASHBOARD_V2_PROGRESS.md`
4. `docs/DASHBOARD_V2_DECISIONS.md`
5. The V2 document matching the requested slice: architecture, contracts,
   design or migration.
6. `docs/DECISIONS.md` before backend/methodology/control changes.

Use the repo-local `dashboard-v2` skill when the environment discovers
`.agents/skills/`; the Markdown documents remain authoritative and portable
when it does not.

## Current truth

Python SSR and all engines remain intact. Next.js exists only as the
DASH-V2-00 static foundation under `frontend/` (no API integration, no
BFF, no live data). No CMC or
CoinGecko adapter exists. No state classifier, opportunity engine, backtester
or paper engine exists. P1-10R is RUNNING (PID 19084, since
2026-10-08T00:48:20Z) â€” do not touch the probe, dashboard, databases,
registry, or evidence. P1-12/P1-12B remain blocked.

## Required workflow

`AUDIT -> PLAN -> IMPLEMENT -> TEST -> VISUAL VERIFY -> DOCUMENT -> CHECKPOINT -> NEXT`

Keep slices small. Before coding, state the screen/data contracts, capability
states, invariants and non-goals. After coding, report exact tests and visual
evidence, update progress/current state/task queue as applicable, inspect the
diff, stage selectively and stop at the next authorization gate.

## Non-negotiable frontend rules

- Real APIs/fixtures derived from contracts; never mockup-fiction in product.
- Null/unknown/stale/degraded are distinct from zero/live.
- Binance mark/trade/book/OI/history is canonical for venue research.
- External aggregate data is labeled and never drives venue PnL/liquidity.
- No ticker-only external identity mapping.
- Browser never reads SQLite, provider credentials or Python control nonce.
- No second process manager; no wildcard CORS; no weakening control checks.
- Maintain P1-11A Movers source/unit/format and velocity-sign invariants.
- Visual PASS requires fresh screenshot comparison, not tests alone.

## First implementation candidate

`DASH-V2-00` only after explicit authorization: create the frontend scaffold,
tokens and shared truthful-state components plus a read-only allowlisted BFF
skeleton. Do not integrate runtime mutation in this slice.

## Stop conditions

Stop for missing material product choice, unavailable reference mockups needed
for visual acceptance, security weakening, engine methodology change, secrets,
paid provider/billing, unresolved tests, runtime interruption or any request
that crosses observe-only boundaries.

## DASH-V2-00 landed (2026-10-07)

Isolated static foundation exists under rontend/ (Next 16.4 + React 19.3, strict TS, tokens, 15 components, 7 static routes + /symbol/[symbol], labeled demo fixtures, no API calls). Python backend untouched (408/408). Next: DASH-V2-01 only on explicit authorization. P1-10R probe (PID 19084) must not be disturbed.

## DASH-V2-01 landed (2026-10-07)

/overview is now a professional terminal composition (TopBar, metric grid, pulse, movers snapshot, extreme watch, research health, market context) on labeled fixtures. Preview: http://127.0.0.1:3000/overview (server PID 28552). Next: DASH-V2-02 only on explicit authorization. P1-10R still RUNNING — do not disturb.
