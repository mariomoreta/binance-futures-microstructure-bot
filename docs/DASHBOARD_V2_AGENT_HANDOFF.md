## Direccion vigente — 2026-10-13
El destino aprobado es operar el bot mediante Dashboard V2 como interfaz principal.
Inventario, brechas y aceptacion: [OPERATIONAL_READINESS_INVENTORY.md](OPERATIONAL_READINESS_INVENTORY.md).
La ruta es O1 integracion/captura -> O2 estrategia/replay -> O3 paper/posiciones/riesgo
-> O4 adaptador de ejecucion probado -> O5 operacion controlada.
Los pasos documentan trabajo a completar; no declaran funciones implementadas ni avanzan gates.
Agentes IA/noticias y Kronos: [FUTURE_RESEARCH_OPTIONS.md](FUTURE_RESEARCH_OPTIONS.md), diferidos.
Las notas antiguas siguientes conservan historia; este bloque rige la prioridad actual.

V2 de referencia 27b7af59cb1e313169f49655161d66e043b5412d: hay rutas BFF/lectores reales.
No seguir el encabezado historico "static/no BFF" como estado presente.
Backend de referencia 3cbbb1c9290e252ee18d6f0a466898f2f7b7dfee. No unir ramas ciegamente:
comparar fuentes/contratos, preservar correcciones y publicar SHAs separados si aplica.
Prioridad: paridad necesaria, schemas 10/3, supervision segura, observabilidad y
superficies de backtest/paper cuando sus motores existan; evitar pulido sin dependencia.
Destino aprobado: V2 principal; SSR conservado como legado/rollback hasta demostrar corte.

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
CoinGecko adapter exists. The P1-12A classifier v0 exists (observed
states + evidence, HYPOTHESIS); no opportunity engine, backtester
or paper engine exists. P1-10R is PASS (completed 2026-10-08);
P1-12B is the next candidate (explicit instruction required). Do not
disturb running processes, databases, registry, or evidence.

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

/overview is now a professional terminal composition (TopBar, metric grid, pulse, movers snapshot, extreme watch, research health, market context) on labeled fixtures. Preview: http://127.0.0.1:3000/overview (server PID 28552). Next: DASH-V2-02 only on explicit authorization. P1-10R still RUNNING � do not disturb.

## DASH-V2-02 landed (2026-10-07)

/movers is a professional, fixture-isolated screener: 16 records, summary, combined filters/search, stable nulls-last sorting, filtered rankings, coverage/data-quality aggregation, empty/reset states and 8-row pagination. All values remain visibly DEMO - NOT LIVE; no API/BFF exists. TypeScript, ESLint, 24/24 Vitest and production build pass (re-verified by the recovery agent after removing the staged route templates and fixing a summary unit bug). Browser QA covers desktop 1440 + mobile 390 with interactive checks; reference comparison is NOT EVALUABLE because mockups are absent. Next: DASH-V2-03 only on explicit authorization.

Keep PID 19084 and all P1-10R evidence untouched. Before any future preview restart, reverify the exact Node PID/command/creation time. Current production preview URL remains http://127.0.0.1:3000/movers.

Future live integration needs a versioned Movers view model carrying raw numbers, source, observed_at, freshness, tier, capability, nullability and pagination metadata.

## Traceability update (2026-10-08)

Operational lines above naming P1-10R RUNNING, PID 19084, or P1-12 blocked are superseded: P1-10R PASS (2026-10-08), P1-12A DONE. Current truth lives in docs/CURRENT_STATE.md + docs/TASK_QUEUE.md; feature/decision traceability (F-STATE-V2-*, F-V2-BFF-01, F-CMC-01) lives in docs/FEATURE_BACKLOG.md.
