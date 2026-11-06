# MASTER_PLAN

## Prioridad operativa vigente — 2026-11-06

`docs/PRODUCT_GOAL.md` fija el objetivo: autoselección e investigación de
futuros con movimientos extremos (perpetuos y con vencimiento) → decisión LONG/SHORT/abstención → entrada,
stop-loss, gestión y salida → comprobación de expectativa neta y riesgo →
paper validado → ejecución solo con autorización específica.

La rama de investigación no tiene pendiente otra expansión de dashboard ni
otra reconciliación general de la captura. El siguiente entregable es el
cierre/revisión del protocolo operativo propuesto en
`docs/EXPERIMENTO_OPERATIVO_V1.md`, ya entregado por el agente (no ejecutado).
Infraestructura y simulación existentes se reutilizan; ni una prueba funcional
ni diferencias de retornos brutos avanzan gates económicos. Las fases inferiores
siguen siendo referencias de promoción, no una lista para rehacer capacidades.

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

**Investigación económica orientada a operación, con protocolo independiente
propuesto y pendiente de revisión/cierre.** La captura y análisis exploratorios
están cerrados con limitaciones; no hay rentabilidad acreditada. Priorizar la
propuesta ya entregada en `docs/EXPERIMENTO_OPERATIVO_V1.md` y el bloque vigente
de `docs/TASK_QUEUE.md`. La antigua etiqueta «PHASE 1 — MARKET INTELLIGENCE +
DASHBOARD» describe la secuencia histórica, no una orden de reabrir desarrollo
UI. No se promueven fases formales ni se habilitan capturas, paper o ejecución
por este cambio documental.

## Alcance estrategico preservado — 2026-10-16
El producto final evalua movimientos extremos de ambos lados en el universo
Futures elegible. BTC/ETH/SOL son un subconjunto de verificacion, no prueba
de cobertura de esa estrategia. El seguimiento incremental y aceptacion
estan en docs/EXTREME_MOVERS_OBJECTIVE.md (F-EXTREME-OBJECTIVE-01).
Se conserva la secuencia vigente: auditoria causal/costes → selector evaluable
→ backtest → paper → ejecucion autorizada. Sin cambio de gates.
(Integracion 2026-10-17 desde review/extreme-movers-objective-20261016
hasta 7a4e872, portada sin sobrescribir la evolucion actual.)
