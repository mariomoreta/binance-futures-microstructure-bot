## Direccion vigente — 2026-10-13
El destino aprobado es operar el bot mediante Dashboard V2 como interfaz principal.
Inventario, brechas y aceptacion: [OPERATIONAL_READINESS_INVENTORY.md](OPERATIONAL_READINESS_INVENTORY.md).
La ruta es O1 integracion/captura -> O2 estrategia/replay -> O3 paper/posiciones/riesgo
-> O4 adaptador de ejecucion probado -> O5 operacion controlada.
Los pasos documentan trabajo a completar; no declaran funciones implementadas ni avanzan gates.
Agentes IA/noticias y Kronos: [FUTURE_RESEARCH_OPTIONS.md](FUTURE_RESEARCH_OPTIONS.md), diferidos.
Las notas antiguas siguientes conservan historia; este bloque rige la prioridad actual.

La arquitectura objetivo sigue siendo pipeline backend -> decision de estrategia
-> control de riesgo/posiciones -> ejecucion -> reconciliacion/ledger; V2 observa
y solicita acciones autenticadas. Implementar pruebas y piezas aisladas en paralelo
sin omitir validacion economica ni autorizacion concreta de fondos.

# MASTER_PLAN

Stable strategic direction. Factual state lives in `docs/CURRENT_STATE.md`;
operational next work lives in `docs/TASK_QUEUE.md`.

## Direction

Build the Binance Futures market-intelligence system described in
`docs/PRODUCT_GOAL.md`: observe → understand → paper-prove → (only then, with
explicit authorization) consider execution. Final KPI is profitability and
risk-adjusted expectancy.

## Canonical architecture

```text
Binance public market data
  → normalization
  → feature engine
  → market-state / signal engine
  → persistence
```

Persistence feeds dashboard, research, and later paper trading.

Later:

```text
signal engine → position manager → risk engine → execution engine
```

Risk engine can never be bypassed. Dashboard never feeds the engine.

See `docs/ARCHITECTURE.md`.

## Phases and gates

| Phase | Name | Gate summary |
|---|---|---|
| 1 | Market Intelligence + Dashboard | Sustained multi-symbol WS coverage, feature engine (returns/velocity/rank/VWAP/vol), state classifier v0, dashboard routes live, 0 signals treated as entries |
| 2 | Persistent Dataset + Event Labeling | Snapshots persisted, forward outcomes (30s→60m + MFE/MAE) computed, dataset queryable |
| 3 | Strategy Discovery + Backtesting | Candidate strategies with costs/slippage, out-of-sample validation, expectancy report |
| 4 | Live Paper Trading + Position Mgmt | Live paper engine with state-driven exits, risk limits enforced, performance vs backtest |
| 5 | Controlled Execution | Explicit human authorization required. Small-size, kill-switch, full audit trail |

Full criteria: `docs/SUCCESS_GATES.md`. Sequence and dependencies: `docs/ROADMAP.md`.

## Current phase

**PHASE 1 — MARKET INTELLIGENCE + DASHBOARD.** Baseline: audited observe-only
probe (v0.2.0) + canonical `python run_tests.py`. Execution follows the binding
P1-00…P1-14 dependency order in `docs/TASK_QUEUE.md` (dashboard-progressive,
classifier only after raw-feature validation). Persistence foundation is a
Phase 1 task (P1-02); full labeling stays Phase 2. No paper trading and no
execution until their phases and authorizations.
