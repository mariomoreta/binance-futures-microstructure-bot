# ROADMAP

## Secuencia de trabajo vigente — 2026-11-06

1. Dar por cerrado como exploratorio el análisis de
   `public-pilot-1h-20261106a`, con limitaciones conservadas.
2. Revisar y cerrar la propuesta existente `EXPERIMENTO_OPERATIVO_V1.md`, con
   mapa breve de capacidades, una hipótesis operativa y protocolo independiente con regla de entrada/dirección,
   stop, salida, riesgo, datos y presupuesto definidos antes de ejecutarlo.
3. Revisar ese protocolo y autorizar por separado, si procede, su adquisición y
   evaluación. Una corrida nueva debe resolver una pregunta económica concreta.
4. Decidir continuar, reformular o detener la línea con los criterios fijados.
   Solo una candidata que lo justifique pasa a evaluación de ejecución/costes y
   validación paper usando lo existente; no hay promoción automática.
5. Considerar ejecución real únicamente con gates y autorización específica.

La capacidad final es autoseleccionar y gestionar operaciones en futuros de
Binance, tanto perpetuos como contratos con vencimiento, con movimientos
extremos de ambos lados; detectar volatilidad es una etapa, no el
resultado final. Ver `PRODUCT_GOAL.md` y el bloque vigente de `TASK_QUEUE.md`.
Se congela la expansión de dashboard, Paper Lab, supervisión y conectores.
Las fases y listas históricas inferiores no reactivan esos trabajos ni invalidan
el trabajo económico ya autorizado; sus gates formales no se dan por cumplidos.

Future sequence. Operational now lives in `docs/TASK_QUEUE.md`.
Decision/feature traceability lives in `docs/FEATURE_BACKLOG.md`.

## Phase 1 — Market Intelligence + Dashboard (secuencia histórica)

Dependency order (binding — see `docs/DECISIONS.md` 2026-10-06):

```text
RAW MARKET DATA → RAW FEATURES → PERSISTENCE → DASHBOARD VISIBILITY
  → LIVE FEATURE VALIDATION → STATE CLASSIFIER
```

1. `P1-00` Tooling sanity — canonical `python run_tests.py` ✅ DONE.
2. `P1-01` Short transport validation (30–60 min observe-only; NOT the 6h soak).
3. `P1-02` Persistence foundation (local observe-only store → dashboard).
4. `P1-03` Minimal dashboard (`/overview`, `/system`: connection/stream health,
   message rates, latency p50/p95, stale symbols, gaps, reconnects, last
   update, runtime). Dedicated local port, 127.0.0.1, health endpoint.
5. `P1-04` Symbol universe + multi-timeframe returns.
6. `P1-05` Price velocity/acceleration + ranking.
7. `P1-06` Volume + aggressive trade flow.
8. `P1-07` Order book + open interest.
9. `P1-08` VWAP + volatility + market structure.
10. `P1-09` Market-intelligence dashboard (`/movers`, `/symbol/:symbol`;
    raw features before classifier scores). Browser access maintained live.
11. `P1-10` Prolonged ≥6h soak with dashboard live (screenshots while flowing).
12. `P1-11` Raw feature validation (distributions, missingness, freshness).
13. `P1-12` State classifier v0 (hypothesis thresholds; only after P1-11).
14. `P1-13` Signal / extreme-move UI (`/signals`, `/extreme-moves`).
15. `P1-14` 24h calibration review → Phase 1 gate evaluation.

### Parallel Dashboard V2 lane (architecture foundation complete)

Dashboard V2 does not reorder the market-intelligence dependencies above and
does not unblock P1-12. Its implementation is a reversible parallel lane:
contract normalization → frontend shell → Overview → Movers → token detail →
System/control → parity and cutover. Each slice must pass the gates in
`docs/DASHBOARD_V2_MIGRATION_PLAN.md`; the Python SSR dashboard remains the
rollback surface until parity is evidenced.

## Phase 2 — Persistent Dataset + Event Labeling

Builds on the P1-02 foundation: snapshot schema → outcome calculator
(30s→60m, MFE/MAE, peak/trough, continuation/reversal) → backfill/validation →
research access docs.

## Phase 3 — Strategy Discovery + Backtesting

Hypothesis A/B statistical tests → candidate definitions → cost-aware
backtests → out-of-sample + sensitivity → expectancy reports.

## Phase 4 — Live Paper Trading + Position Management

Paper engine → position manager (HOLD … FULL_EXIT) → risk enforcement →
paper/performance surfaces → divergence monitoring.

## Phase 5 — Controlled Execution

Authorization gate → small-size execution with kill-switch → audit. Not planned
in detail until Phase 4 proves expectancy. No code before authorization.
