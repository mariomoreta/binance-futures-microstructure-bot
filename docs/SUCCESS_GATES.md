# SUCCESS_GATES

## Aplicación al trabajo vigente — 2026-11-06

Estos gates siguen rigiendo la promoción formal; esta actualización no marca
ninguno como cumplido ni modifica sus umbrales. La prioridad del agente está en
`PRODUCT_GOAL.md` y el bloque vigente de `TASK_QUEUE.md`: diseñar una comprobación
operativa independiente y acotada sobre selección de perpetuos extremos,
entrada, stop, salida y riesgo, reutilizando los componentes existentes.

Recepción de datos, aceptación UI, tests, mayor movimiento o retorno bruto no
demuestran rentabilidad. Separar asociación exploratoria, resultado de una regla
causal y evidencia neta independiente. La planificación de investigación no
autoriza capturas, despliegue paper ni ejecución real por sí misma. No convertir
listas históricas en ampliaciones de infraestructura sin necesidad económica
demostrada ni declarar una fase promovida porque exista código de esa fase.

Objective advancement criteria. A phase is complete only when ALL its gates
pass with linked evidence. `UNKNOWN` beats optimistic.

Gates keep their IDs; their evidence order now follows the P1-00…P1-14
dependency chain (dashboard-progressive, classifier-after-validation).

## PHASE 1 — Market Intelligence + Dashboard

- [ ] G0 Tooling: canonical `python run_tests.py` green from repo root
      (evidence: P1-00, 28/28). Must stay green for every later task.
- [ ] G1 Safety: observe-only enforced, static no-order-paths test green,
      0 keys / 0 orders / 0 capital in every summary. Never loosened.
- [ ] G2 Connectivity: short validation run (P1-01, 30–60 min) + prolonged
      soak (P1-10, ≥6h, dashboard live): WS coverage sustained, reconnects
      counted, uptime % reported, no unexplained outages.
- [ ] G3 Data quality: staleness/gap/rejection telemetry understood across
      both runs; event-driven silence correctly not-stale; depth gaps
      characterized; P1-11 validation (distributions, missingness, freshness,
      measurement errors) passed.
- [ ] G4 Latency: raw/corrected/processing distributions characterized per
      stream/symbol over the runs; visible on `/system`; no legacy-metric claims.
- [ ] G5 Persistence: P1-02 foundation stores raw market data/features locally,
      dashboard reads from it (observe-only; no trading data, no keys).
- [ ] G6 Dashboard progressive: P1-03 (`/overview`, `/system` with connection/
      stream health, rates, p50/p95, stale, gaps, reconnects, last update,
      runtime) live on real data with browser URL + health check; P1-09 adds
      `/movers`, `/symbol/:symbol` showing raw features; P1-13 adds `/signals`,
      `/extreme-moves`. Engine demonstrably independent of frontend throughout.
- [ ] G7 Features: returns (all TFs) + velocity/accel + rank/velocity/accel +
      VWAP + realized vol/range + flow + book/OI live with warm-up + near-miss,
      validated per P1-11 BEFORE any classifier consumes them.
- [ ] G8 States: classifier v0 (P1-12, only after P1-11) emitting timestamped
      states with evidence vectors; no flapping pathology; thresholds labeled
      hypothesis.
- [ ] G9 Calibration evidence: 24h observation captured (P1-14); detector/state
      thresholds reviewed against real crossings (tune or justify).
- [ ] G10 Tests: full suite green + new feature/state/dashboard tests; static
      checks clean.

Advance to Phase 2 only on all-green + human acknowledgment.

## PHASE 2 — Persistent Dataset + Event Labeling

- [ ] Snapshots persisted per `docs/EVENT_LABELING.md` (schema + config hash),
      building on the P1-02 foundation.
- [ ] Forward outcomes (30s→60m, MFE/MAE, peak/trough, continuation/reversal)
      computed without lookahead; gaps flagged.
- [ ] Dataset queryable for research (documented access path).

## PHASE 3 — Strategy Discovery + Backtesting

- [ ] ≥1 candidate strategy with full cost/slippage accounting.
- [ ] Out-of-sample validation + sensitivity (1x/2x/3x costs).
- [ ] Expectancy report with distributions, not point promises.

## PHASE 4 — Live Paper Trading + Position Management

- [ ] Paper engine with state-driven exits live ≥ defined window.
- [ ] Risk limits enforced, unbypassable; halts/kills exercised or reasoned.
- [ ] Paper-vs-backtest divergence within tolerance, or investigated.

## PHASE 5 — Controlled Execution

- [ ] Requires: proven paper profitability + explicit human authorization.
- [ ] Small size, kill-switch, full audit trail. Authorized separately, never
      implied by Phase 4 success.
