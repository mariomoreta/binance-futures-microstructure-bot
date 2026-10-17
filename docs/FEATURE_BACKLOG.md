
## Bot + Dashboard V2 para corridas de observacion — 2026-10-13 (review/bot-dashboard-v2-observacion, sin push aun)
V2 (checkpoint 27b7af5, rama dash-v2-03-token-detail) como interfaz principal
para observacion/evaluacion; dashboard Python pasa a LEGADO (funcional, no
primario; sin semanticas contradictorias). Agentes IA + Kronos: ver
F-KRONOS-01 (PROPOSED, diferido, fuera de alcance; sin dependencias ni
integraciones; no es requisito de arranque). Pendientes tecnicos previos se
mantienen. Gates sin avance.

## Entrega nueve archivos 6fd6091-base — 2026-10-13 (push review/entrega-nueve-archivos-6fd6091 completado)
Cierres tecnicos (habilitante, sin IDs nuevos): cap holding, calendario
monocontrato, mark stale, fees exit-value (1 assert legacy corregido),
symbol en manifiesto, handoff 27b7af5 real (gates 2/9 vs v10/v3).
R1-R7 + dirigidas + comparador verdes; barrera con 9 preexistentes
contrastados. Distincion: implementacion DONE; validacion financiera NOT
IMPLEMENTED. Gates sin avance.

## Bot + V2 observacion — 2026-10-13 (review/bot-dashboard-v2-observacion, sin push aun)
V2 principal (27b7af5 a continuar) + legado Python (sin contradicciones) +
matriz/ciclo/aceptacion/preflight + F-KRONOS-01 diferido. Sin IDs nuevos de
producto salvo F-KRONOS-01 (PROPOSED). Gates sin avance.

## Correccion tecnica de14ac1-base — 2026-10-13 (review/correccion-tecnica-de14ac1; push 6fd6091 completado)
Motor/contratos (habilitante, sin IDs nuevos): split realizado/abierto
(n_realized/n_open/open_positions; curva realizada; costes hipoteticos),
funding qty x mark + identidad/dedup/gaps (contrato v4.1), runner por
familia H1/H2/H3 + identidad por indice. Comparador M6a/M6b/M7/M8/SELF.
Handoff 27b7af5 (v10/v3 explicito; frontend/ intacto). Incidente v2->v3
reconciliado. Distincion: reproduccion DONE; integracion dashboard
parcial-no-verificada; validacion financiera NOT IMPLEMENTED. Pendientes:
despliegue/operacion de lo corregido, OOS/calibracion/rentabilidad.
Gates sin avance.

## Cierre W/LUMIA documental — 2026-10-13 (push phase1 bc327f1 completado)
Reproduccion de caso (sin ID de producto; habilitante/documental):
addendum v2 en CASE_STUDY + 5 evidencias (hashes, comparacion,
logs, env, script). Distincion: reproduccion DONE; integracion dashboard
(F-STATE-*/F-OPP-UI-01/campos+funding-calendario) NOT IMPLEMENTED;
validacion financiera (F-BT-01/F-PAPER-01, OOS/calibracion/rentabilidad)
NOT IMPLEMENTED. V2 `27b7af59cb1e313169f49655161d66e043b5412d` =
frontend estatico dash-v2-03-token-detail, no SSR backend. Pendientes
correctivos NO resueltos: funding, posiciones abiertas, runner, incidente
de aislamiento, schemas V2. Gates sin avance.

## Correccion V2 + comparador — 2026-10-13 (review/w-lumia-correccion-bc327f1; push de14ac1 completado)
Addendum (historia preservada): V2 `27b7af59cb1e313169f49655161d66e043b5412d`
= rama `dash-v2-03-token-detail` CON rutas BFF (`api/v1/...`) + adapters
SQLite (`canonical-market.ts`, `historicalRead`); integracion parcial,
feed live/operacion NO verificados (UNVERIFIED + warnings en la propia
ruta). Comparador fortalecido con 5 regresiones (temp, originales
intactos). Distincion vigente: reproduccion DONE; integracion dashboard
parcial-no-verificada; validacion financiera NOT IMPLEMENTED. Pendientes:
funding, realizados/marcas, runner, aislamiento, schemas V2. Gates sin avance.

## Mejoras funding/trazabilidad/dashboard/evaluacion — 2026-10-13 (sin push aun)
Ingenieria + docs + evaluacion offline. Sin ordenes/paper/servicios.
Sin rentabilidad ni SUCCESS_GATES. Kronos diferido (fuera de alcance).

## Cierre correctivo R1-R7 — 2026-10-13 (sin push aun)
Motor v3 + migraciones v10 en una init + resolver R7 + 22 regresiones.
Habilitante/correctivo; sin IDs de producto; gates sin avance.

## Cierre correctivo P1-P4 — 2026-10-12 (sin push)
Motor offline v2 + regresiones; inyeccion B/C; linkage run_id v10;
reconciliacion documental. Sin IDs nuevos verificados como feature de
producto; trabajo habilitante + correctivo. Gates sin avance.

## ETAPA-5 Paper Lab plan — 2026-10-12
Design only (no backlog ID): six build items + entry gates. No
implementation, no paper session, no authorization.

## ETAPA-4 offline backtest prep — 2026-10-12
Prep implementation (no backlog ID): isolated engine + 16 tests + unwired
read contract. Mechanics smoke only; strategy validation NOT claimed.

## ETAPA-3 research/backtest contract — 2026-10-12
Contract only (no backlog ID): H1/H2/H3 + cost model + replay limits.
Engine deferred to Etapa 4 prep. No gate advancement.

## ETAPA-2 dataset readiness — 2026-10-12
Enabling research forensics (no backlog ID): pure-read provenance script
(scripts/audit_dataset_provenance.py) + DATASET_READINESS report with
per-population blockers. No data mutation. No gate advancement.

## ETAPA-1 test isolation — 2026-10-12
Enabling test-hygiene (no backlog ID): full-suite write barrier
(scripts/audit_test_isolation.py, PREFIX/POSTFIX evidence), temp-intercepted
repro (scripts/repro_default_store_writes.py), 6 test-file fixture fixes +
tests/test_persistence_isolation.py (5 regressions). 916/916 canonical OK,
zero prohibited writes, stable microprobe hash; Routes B/C residual with
production-side blocker. Report: docs/TEST_ISOLATION_ETAPA1_REPORT.md.
No production change; no gate advancement.
## Final proof and fixture-isolation checkpoint (2026-10-11)
Original proof correction: focused 1/1 and canonical 910/910 exit0 (184.479s).
A subsequent System read found 375 universe rows, 225 tagged detail='test',
rather than the earlier read of 366/222. Earlier canonical-suite preservation
claims do NOT hold across those test runs. Readonly GET hashes are a separate,
bounded check and remain equal.

Root route proven without touching the canonical DB: original HotSyncTest
calls the default persistence factory twice and writes three DOGEUSDT lifecycle
rows to an intercepted temporary store. test_universe_probe.make_probe now
injects a real initialized temporary PersistenceStore with cleanup per testcase.
All 11 module tests pass with the default factory forbidden, zero calls.
One added regression prevents fallback. No application source changes.
This establishes a test contamination route; it does not attribute every
historical tagged row. Existing canonical rows were retained without cleanup.

Final canonical: 911/911 application tests exit0. The preservation wrapper
exits1: microprobe.db SHA256 changed; historical.db and registry hashes equal.
Universe rows stayed375/225: HOT leakage fixed, whole-suite preservation FAILED.
A guarded subset audit (729 tests) records default-store accesses in test_probe,
test_host_telemetry and test_p14b_3_transport_freshness (six errors with factory
forbidden, swallowed persistence errors also observed). These remaining fixtures
are a BLOCKER for whole-suite isolation; no claim of complete purity is made.
See backend-isolated-final.json and default-store-audit.json.
Source notice remains until historical provenance is reviewed.
The 496-test frontend Python snapshot is historical validation, not the
current backend. Its old HOT fixtures must not be rerun against the canonical
store; reconcile the fixture isolation or run it in a fully isolated checkout.
FEATURES_IMPLEMENTED adds temporary HOT fixtures and fallback regression.
FEATURES_VERIFIED final 911 plus isolated original/after negative control.
DEFERRED_FEATURES retains remaining default-store test isolation, historical lineage and complete cutover.
No runs, traffic, orders, Start, retirement, main merge or gate advancement.


# FEATURE BACKLOG — canonical decision traceability & deferred features

## Cierre EVAL-CENSUS-V2 + selector + QA visual — 2026-10-17 (sin corridas)

**1. Title:** Evaluación offline sobre censo causal exhaustivo
(EVAL-CENSUS-V2) + selector extremo (fixtures) + QA visual V2.
**2. Approval status:** DECIDED (criterio pre-fijado del protocolo
prospectivo V1; sin reajustes). H2 fade: HIPTESIS NUEVA (NO aprobada).
**3. Implementation status:** IMPLEMENTED (censo reconstruct_causal_census.py,
selector extreme_selector.py, artefacto census-eval-v2.json force-added,
scripts build_census_eval_inputs.py, tests test_causal_census.py +
test_eval_horizon_grid.py + test_extreme_selector.py + census-eval.test.ts).
**4. Evaluation status:** A) Reglas sobre censo historico: EVALUADO
(0 celdas elegibles, H1/H3 RECHAZADAS, H2 fade RECHAZADO). B)
Selector: MECANISMO probado con fixtures, NO evaluado. C) Estrategia
completa extremos sobre universo/liquidez: NO EVALUADA (faltan datos).
**5. Limitaciones:** in-sample/non-pristine, costes supuestos COST-ASSUME-v1,
mapping candidato MAP-CANDIDATE-v2, sin prueba live, MFE/MAE no capturados,
placebo una realizacion no distribucion, cross-celda no modelada, 6 detecciones
tail-edge sin entry (honesto).
**6. Evidence:** docs/OFFLINE_EVAL_CENSUS_V2.md (seccion 7 matriz A/B/C),
frontend/src/data/census-eval-v2.json (sha256 2b74a841...d37060),
docs/evidence/VISUAL_QA_CENSUS_EVAL_V2.png, suites backend 1202 OK +
frontend 314/314 + typecheck 0 + build OK.
**7. Last update:** 2026-10-17.

## DASH-V2-71B reviewer correction — 2026-10-11
89232f7 independently reviewed: discovery/canonical 910, exit0. Strengthened
existing purity test (missing historical-byte assertion, no new logs, env
restoration); historical-tempfile mutation passed old proof and fails new.
No application source change. Final bytes do not certify readonly mode;
four HistoryStore init calls observed. See DASH_V2_71B_REVIEW_CORRECTIONS.md.
Full cutover/Start/gates unchanged; universe detail=test provenance pending.


## DASH-V2-69 — 2026-10-11 — extraction proof review
Exact c59c5ec extraction reviewed independently. Five helper bodies match; original Python 3.14 find_module blocker was ineffective despite four green tests. Existing H2 strengthened with find_spec plus deliberate negative control; four focused tests pass. No application source edits. V1 contract retirement section now closes extraction prerequisite while retaining parity/review/authorization requirements; no retirement performed. See DASH_V2_69_EXTRACTION_PROOF_REVIEW.md; canonical verification recorded there. Full cutover and operational readiness remain PARTIAL; Start/gates/main/DB/registry preserved.


**Purpose:** durable project-wide record so approved product decisions,
deferred features, design agreements and future dependencies are never lost
between AI agents or development phases. This document indexes decisions;
it does not replace them. Authority stays where it was recorded
(`docs/DECISIONS.md` for methods, `docs/DASHBOARD_V2_DECISIONS.md` for V2,
`docs/TASK_QUEUE.md` for operational sequencing).

**Rules:**

- Statuses: `DECIDED` (approved, binding) / `PROPOSED` (discussed, not
  approved) for approval; `NOT IMPLEMENTED` / `PARTIAL` / `IMPLEMENTED` /
  `VERIFIED` for implementation. A discussed feature is never auto-marked
  IMPLEMENTED or VERIFIED.
- VERIFIED requires linked evidence (tests, logs, screenshots, commits).
- New material decisions needing user approval are recorded as PROPOSED
  first — never treated as binding before approval.
- IDs are stable and unique (`F-<AREA>-<NN>`). Never reuse an ID.

## Status legend (2026-10-08 snapshot)

| ID | Title | Approval | Implementation | Phase |
|---|---|---|---|---|
| F-STATE-PY-01 | Market State Intelligence — Python presentation | DECIDED | VERIFIED (token panel) | P1-12A DONE |
| F-STATE-V2-OV-01 | V2 Overview: state distribution + transitions | DECIDED | NOT IMPLEMENTED | DASH-V2 future |
| F-STATE-V2-MV-01 | V2 Movers: state/direction columns + filters | DECIDED | NOT IMPLEMENTED | DASH-V2 future |
| F-STATE-V2-TK-01 | V2 Token Detail: state explanation panel | DECIDED | NOT IMPLEMENTED | DASH-V2 future |
| F-STATE-V2-TL-01 | State timeline visualization | PROPOSED | NOT IMPLEMENTED | Later |
| F-UNI-01 | Dynamic LIVE-universe expansion (P1-12B) | DECIDED | VERIFIED | P1-12B DONE |
| F-OPP-01 | Research-based opportunity engine (P1-13A) | DECIDED | IMPLEMENTED (pending VERIFIED) | P1-13A DONE |
| F-P14A-01 | Prospective setup outcome evaluation (P1-14A→P1-14B.8) | DECIDED | VERIFIED (contract v1.1; supervised) | P1-14A/P1-14B/P1-14B.1/P1-14B.4/P1-14B.5/P1-14B.7/P1-14B.8 DONE, P1-14B.2/P1-14B.3/P1-14B.6 PARTIAL |
| F-OPP-UI-01 | Opportunities dashboard (P1-13B) | DECIDED | NOT IMPLEMENTED | P1-13B |
| F-BT-01 | Historical backtesting (P1-14) | DECIDED | NOT IMPLEMENTED | P1-14 |
| F-PAPER-01 | Forward paper validation (P1-15) | DECIDED | NOT IMPLEMENTED | P1-15 |
| F-PORT-01 | Paper portfolio (P1-16) | DECIDED | NOT IMPLEMENTED | P1-16 |
| F-V2-BFF-01 | Next.js API integration (BFF) | DECIDED | NOT IMPLEMENTED | DASH-V2 future |
| F-LAUNCH-SUP-01 | Supervised transactional launch | PROPOSED (enablement needs explicit authorization) | PARTIAL (V2-62 corrected disabled preparation; 902 tests; no wiring) | Future (V2 review of exact SHA first) |
| F-CMC-01 | CoinMarketCap supplementary metadata | DECIDED (staged) | NOT IMPLEMENTED | CMC-00/01/02 |
| F-CORE-01 | Completed Phase 1 foundations (index) | DECIDED | VERIFIED | P1-00…P1-11C, P1-10R |

---

## F-KRONOS-01 — Agentes IA + Kronos (investigacion futura)

- **Product objective:** explorar, solo como investigacion futura, si
  agentes IA y la fuente de datos Kronos pueden aportar contexto de
  mercado (metadata agregada, nunca fills, PnL ni backtest de Binance).
- **Origin / decision date:** objetivo Bot+V2 2026-10-13 (propuesta
  registrada, NO aprobada para implementacion).
- **Approval status:** PROPOSED (deferral explicito). **Implementation
  status:** NOT IMPLEMENTED. Cero dependencias instaladas, cero
  integraciones, cero codigo. No es requisito de arranque de ninguna
  corrida de observacion/evaluacion ni del ciclo de uso V2.
- **Target phase:** futura e indefinida (fuera del alcance actual:
  observacion + V2 como interfaz principal).
- **Dependencies:** ninguna (diseno pendiente de aprobacion previa).
- **Acceptance criteria (si algun dia se aprueba):** proveedor etiquetado
  obligatorio; jamas fuente de mark-price, liquidez, fills, PnL o
  backtest; revision legal previa si aplica.
- **Evidence needed:** ninguna aun (nada que probar).
- **Docs:** este backlog (unico registro hasta aprobacion).
- **Open questions:** valor real, estabilidad de acceso, credenciales.
- **Last update:** 2026-10-13 (diferido).

## F-STATE-PY-01 — Market State Intelligence, Python dashboard

- **Product objective:** expose validated classifier output (state,
  direction, timestamp, coverage, evidence) with truthful UNKNOWN/STALE
  behavior; never as LONG/SHORT recommendations, probabilities, or
  profitability claims.
- **Origin / decision date:** `docs/MARKET_STATES.md` (vocabulary + gating);
  phase order decision 2026-10-06 (`docs/DECISIONS.md`); authorized by
  P1-11A/B/C + P1-10R PASS chain; implemented P1-12A 2026-10-08.
- **Approval status:** DECIDED. **Implementation status:** VERIFIED
  (token-page panel; movers/system exposure not built — see F-STATE-V2-MV-01
  for V2-side tracking; no Python movers state column exists).
- **Target phase:** P1-12A DONE.
- **Dependencies:** P1-04…P1-08 engines, P1-09 token page, P1-11A/B/C +
  P1-10R gates (all satisfied).
- **Affected subsystems:** `classifier.py`, `persistence.py` (schema v7),
  `probe.py` (per-summary evaluation), `dashboard.py` + `dashboard_views.py`
  (token panel).
- **Required UI locations:** `/symbol/:symbol` state panel (done).
- **Data/API requirements:** persisted `state_features` rows; no new HTTP
  contract needed (server-rendered from existing store reads).
- **Acceptance criteria:** deterministic versioned rules; evidence
  for/against + missing + validity on every record; hysteresis; no
  probabilities; discovery-only honesty. All met.
- **Evidence:** `tests/test_classifier.py` (25 tests), 447/447 suite,
  120s observe COMPLETED run (9 evals, transitions persisted),
  token-page screenshots in P1-12A report.
- **Docs:** `docs/CLASSIFIER_SPEC.md`, `docs/FEATURE_MODEL.md`,
  `docs/ARCHITECTURE.md`, `docs/MARKET_STATES.md`.
- **Open questions:** none blocking; calibration is P1-14 territory.
- **Last update:** 2026-10-08.

## F-STATE-V2-OV-01 — V2 Overview: state distribution + transitions

- **Product objective:** Overview shows market-state distribution across
  the observed universe (with observed-universe denominator) plus recent
  transitions, all from authoritative Python classifications.
- **Origin / decision date:** `docs/DASHBOARD_V2_DESIGN_SPEC.md` +
  V2 architecture review 2026-10-07.
- **Approval status:** DECIDED (design). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** DASH-V2 future slice (after BFF).
- **Dependencies:** F-V2-BFF-01 (versioned state view-model),
  F-STATE-PY-01 (authoritative values). React must never compute
  authoritative classifications.
- **Affected subsystems:** `frontend/src/app/overview/`, BFF routes.
- **Required UI locations:** `/overview` state distribution + transitions.
- **Data/API requirements:** versioned `/api/v1` state view-model with
  denominator, provenance, freshness.
- **Acceptance criteria:** denominator shown; stale/unknown distinguished;
  zero fabricated states; visual QA vs references.
- **Evidence needed:** BFF contract tests, component tests, screenshots.
- **Docs:** `docs/DASHBOARD_V2_DESIGN_SPEC.md`,
  `docs/DASHBOARD_V2_API_CONTRACTS.md`.
- **Open questions:** exact view-model schema (pending BFF design).
- **Last update:** 2026-10-08.

## F-STATE-V2-MV-01 — V2 Movers: state/direction columns + filters

- **Product objective:** Movers table gains state and direction columns
  with matching filters, sourced from Python classifications.
- **Origin / decision date:** V2 design review 2026-10-07.
- **Approval status:** DECIDED (design). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** DASH-V2 future slice (after BFF).
- **Dependencies:** F-V2-BFF-01, F-STATE-PY-01.
- **Affected subsystems:** `frontend/src/app/movers/`, BFF routes.
- **Required UI locations:** `/movers` columns + filter controls.
- **Data/API requirements:** per-symbol state + direction + freshness in
  the movers view-model.
- **Acceptance criteria:** filters combine with existing ones; nulls stay
  last/empty; no LONG/SHORT language.
- **Evidence needed:** contract + component + interaction tests, screenshots.
- **Docs:** `docs/DASHBOARD_V2_DESIGN_SPEC.md`.
- **Open questions:** none.
- **Last update:** 2026-10-08.

## F-STATE-V2-TK-01 — V2 Token Detail: state explanation panel

- **Product objective:** Token Detail explains the current state with
  supporting evidence, counterevidence, missing inputs, previous
  transitions, and rule version — mirroring F-STATE-PY-01 content.
- **Origin / decision date:** V2 design review 2026-10-07.
- **Approval status:** DECIDED (design). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** DASH-V2-03 or later BFF-backed slice.
- **Dependencies:** F-V2-BFF-01, F-STATE-PY-01.
- **Affected subsystems:** `frontend/src/app/symbol/[symbol]/`, BFF routes.
- **Required UI locations:** `/symbol/[symbol]` state panel.
- **Data/API requirements:** full classification record view-model.
- **Acceptance criteria:** evidence/counterevidence/missing/version all
  visible; discovery-only honesty preserved.
- **Evidence needed:** contract + component tests, screenshots.
- **Docs:** `docs/DASHBOARD_V2_DESIGN_SPEC.md`.
- **Open questions:** none.
- **Last update:** 2026-10-08.

## F-STATE-V2-TL-01 — State timeline visualization

- **Product objective:** visual timeline of state transitions per symbol
  (later enhancement, not existing functionality).
- **Origin / decision date:** governance capture 2026-10-08 from the
  standing "timeline is later" agreement.
- **Approval status:** PROPOSED. **Implementation status:** NOT IMPLEMENTED.
- **Target phase:** Later (after F-STATE-V2-TK-01).
- **Dependencies:** persisted `state_transitions` history, BFF exposure.
- **Affected subsystems:** frontend token/detail views.
- **Required UI locations:** TBD.
- **Data/API requirements:** transition history view-model.
- **Acceptance criteria:** TBD at approval; must never imply prediction.
- **Evidence needed:** design approval + tests + screenshots.
- **Docs:** this backlog (sole record until approved).
- **Open questions:** chart form, time windows, performance budget.
- **Last update:** 2026-10-08.

## F-UNI-01 — Dynamic LIVE-universe expansion (P1-12B)

- **Product objective:** subscribe/unsubscribe WS streams as HOT set
  evolves, with hysteresis and transport headroom.
- **Origin / decision date:** P1-05 left HOT as proposal-only;
  `docs/ROADMAP.md` phase sequence; next candidate per
  `docs/TASK_QUEUE.md` 2026-10-08.
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  VERIFIED (P1-12B PASS 2026-10-08).
- **Target phase:** P1-12B DONE.
- **Dependencies:** P1-12A PASS (satisfied), P1-01R transport headroom.
- **Affected subsystems:** `universe_manager.py`, `probe.py` (managed
  connections + discovery hook), engines (allow/forget), OI poller HOT
  list, recorder `finalize_symbol`, dashboard overview tiers table.
- **Required UI locations:** overview universe tiers + lifecycle (done);
  Token Detail via live sets (done).
- **Data/API requirements:** discovery candidates + select_hot proposals;
  no new HTTP contract (discovery blob extended in place).
- **Acceptance criteria:** no silent resubscription; hysteresis honored;
  live/deep vs discovery-only labeling preserved; transport monitored.
  All met (31 tests + 300s live run: 3 promotions all LIVE).
- **Evidence:** `tests/test_universe.py` + `tests/test_universe_probe.py`
  (31 tests), 478/478 suite, `logs/probe-runs/p12b-300s.log`
  (git-ignored, preserved), `docs/UNIVERSE_SPEC.md`. P1-12B.1 audit
  (2026-10-08): timestamp gate + accounting corrected, 496/496 suite,
  240s observe re-validation (`logs/probe-runs/p12b1-240s.log`).
- **Docs:** `docs/ROADMAP.md`, `docs/TASK_QUEUE.md`, P1-05 decision record,
  `docs/UNIVERSE_SPEC.md`.
- **Open questions:** transport caps stay UNVERIFIED (re-check against
  official docs before raising budgets); resubscribe cadence beyond
  scan-driven sync unevaluated.
- **Last update:** 2026-10-08 (P1-12B.1 corrections applied).

## F-OPP-01 — Research-based opportunity engine (P1-13A)

- **Product objective:** setup candidates from validated states +
  historical analogs with lifecycle, evidence, counterevidence, risks —
  research only, no execution.
- **Origin / decision date:** `docs/ROADMAP.md` phase sequence;
  `docs/SIGNAL_RESEARCH_PLAN.md` (design only).
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  IMPLEMENTED (VERIFIED pending evidence link).
- **Target phase:** P1-13A DONE.
- **Dependencies:** F-UNI-01, classifier history, P1-11C event outcomes.
- **Affected subsystems:** `opportunity.py` (new engine module), persistence (schema v8),
  probe evaluation hook, dashboard `/opportunities` + `/api/opportunities`.
- **Required UI locations:** none yet (engine first; UI is F-OPP-UI-01).
- **Data/API requirements:** candidate lifecycle view-model; no numerical probability claims.
- **Acceptance criteria:** candidates explainable; direction/entry/stop/
  targets nullable until validated; no fabricated confidence;
  cooldown 60 min / max 200 / TTL 24h enforced. All met.
- **Evidence:** `tests/test_opportunity.py` (58 tests), 554/554 suite,
  120s observe COMPLETED run (3 REVERSAL_WATCH candidates stored),
  dashboard live at http://127.0.0.1:8091.
- **Docs:** `docs/OPPORTUNITY_ENGINE_SPEC.md`, `docs/ARCHITECTURE.md`,
  `docs/CURRENT_STATE.md`.
- **Open questions:** candidate scoring methodology (research output).
- **Last update:** 2026-10-08 (P1-13A.1 closeout).

## F-OPP-UI-01 — Opportunities dashboard (P1-13B)

- **Product objective:** present F-OPP-01 candidates (Python `/signals`,
  `/extreme-moves` per ROADMAP; V2 Opportunities per design spec) with
  empty/blocked shells until candidates exist.
- **Origin / decision date:** `docs/ROADMAP.md`; V2 Opportunities section
  `docs/DASHBOARD_V2_DESIGN_SPEC.md` (empty-shell-first rule).
- **Approval status:** DECIDED (sequenced/designed).
- **Implementation status:** NOT IMPLEMENTED (V2 has nav/blocked explanation only).
- **Target phase:** P1-13B.
- **Dependencies:** F-OPP-01.
- **Affected subsystems:** Python dashboard routes; `frontend/src/app/
  opportunities/`.
- **Required UI locations:** `/signals`, `/extreme-moves` (Python);
  `/opportunities` (V2).
- **Data/API requirements:** candidate lifecycle view-model.
- **Acceptance criteria:** honest empty states; no fabricated setups.
- **Evidence needed:** route tests + screenshots.
- **Docs:** `docs/DASHBOARD_V2_DESIGN_SPEC.md`, `docs/ROADMAP.md`.
- **Open questions:** none.
- **Last update:** 2026-10-08.

## F-P14A-01 — Prospective setup outcome evaluation (P1-14A → P1-14B.8)

- **Product objective:** register P1-13A opportunity setups at first DETECTED
  and observe forward mark-price outcomes at versioned horizons (1m/5m/15m/1h
  /4h); research-only: no P&L, no probabilities, no lookahead.
- **Origin / decision date:** `docs/MASTER_PLAN.md` P1-14; `docs/EVENT_LABELING.md`
  forward-outcome concept. Implemented P1-14A 2026-10-08; recovered and re-validated
  P1-14B 2026-10-09 (see P1-14B section in `docs/CURRENT_STATE.md`); time-integrity
  audited and three core defects fixed P1-14B.1 2026-10-09 (see P1-14B.1 section
  in `docs/CURRENT_STATE.md`).
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  IMPLEMENTED + VERIFIED (35 `test_prospective.py` + 39 `test_p14b_validation.py`
  + 16 `test_p14b_1_time_integrity.py` + 20 `test_p14b_3_transport_freshness.py`
  + 19 `test_p14b_4_lifecycle.py`, 683/683 canonical suite green — see P1-14A
  through P1-14B.4 result sections in `docs/CURRENT_STATE.md`; full evidence in
  `docs/P1_14B_VALIDATION_REPORT.md` + `docs/P1_14B_1_TIME_INTEGRITY_AUDIT.md`
  + `docs/P1_14B_3_TRANSPORT_FRESHNESS_AUDIT.md` +
  `docs/P1_14B_4_PROSPECTIVE_LIFECYCLE_AUDIT.md`).
- **Target phase:** P1-14A DONE / P1-14B DONE (recovery) / P1-14B.1 DONE (integrity) /
  P1-14B.2 PARTIAL (stability gate: duration insufficient, prospective layer green) /
  P1-14B.3 PARTIAL (freshness: watchdog + stale-mark gate validated, duration insufficient) /
  P1-14B.4 PASS (contract v1.1: strict unknown-age, grace-deferred terminal PENDING) /
  P1-14B.5 PASS (operational: independent reference + ≥30-min healthy window demonstrated) /
  P1-14B.6 PARTIAL (reproducibility: second window both regimes, attribution refined, fixes validated) /
  P1-14B.7 PASS (persistent supervision: registry-leased abort enforcement, identity restored) /
  P1-14B.8 PASS (supervised maiden voyage: 35-min supervisor window post-audited + sentinel
  layer validated in brief run; V2 launch stays blocked — documented pending).
- **Dependencies:** P1-13A opportunity engine (setups, DETECTED lifecycle,
  candidate_key + setup_family + direction + market_state + rule_version +
  capability_tier fields).
- **Affected subsystems:** `microstructure_probe` (prospective.py, persistence.py
  schema v9), `probe.py` integration, `dashboard.py` (prospective endpoint +
  RESEARCH ONLY banner).
- **Required UI locations:** dashboard prospective tab + `/api/prospective`.
- **Data/API requirements:** schema v9 `prospective_setups` (REPLACE per key) +
  `prospective_outcomes` (append-only, bounded 500/setup); retention max
  hourly, default 90 days on detected_at_ms / observed_at_ms.
- **Acceptance criteria:** idempotent registration (one key = one episode);
  outcome states COMPLETE/PENDING/INSUFFICIENT_HISTORY only (never fabricated);
  UNKNOWN age never FRESH (strict classification); PENDING grace-deferred (recovery
  window = 1 horizon past maturity) then terminal, INSUFFICIENT immediate;
  restart-safe rehydrate from `prospective_setups` (+ seen rebuilt incl. PENDING rows);
  bounded queue + telemetry (writes/drops/errors/inflight/high_water +
  completed/pending/insufficient/in_grace); 4h horizon usable with genuinely
  later data; no orders, keys, P&L, or probabilities.
- **Evidence:** 35 `test_prospective.py` + 39 `test_p14b_validation.py` + 16
  `test_p14b_1_time_integrity.py` (609/609 canonical suite green);
  `/api/prospective` (schema_version 9, RESEARCH ONLY banner); migration chain
  v1–v9; real persisted DB evidence (`data/microprobe.db`, schema v9:
  7 setups, 28 COMPLETE outcomes post-P1-14B.1 fix runs, 0 duplicates,
  event-time/no-lookahead audit PASS — full details in
  `docs/P1_14B_VALIDATION_REPORT.md` + `docs/P1_14B_1_TIME_INTEGRITY_AUDIT.md`).
  Correction: the P1-14B "single outcome" shape was partly an artifact of the
  outcome-store bounding bug (fixed P1-14B.1); rows already deleted are
  unrecoverable and documented, not reconstructed. P1-14B.2 stability run
  (23.4 min, aborted on the >5 % reject rule): 24 setups, 68/68 COMPLETE,
  0 dupes, 100 % matured-cell coverage — full details in
  `docs/P1_14B_2_OPERATIONAL_STABILITY_REPORT.md`. P1-14B.3 freshness work
  (stale-mark gate + watchdog, 20 new tests, 629/629): 24 setups, 99/99 COMPLETE,
  0 dupes; 68-row historical classification (19/28/21/0); 21 missing cells explained
  (unsubscribed OGN/RLC, no defect) — full details in
  `docs/P1_14B_3_TRANSPORT_FRESHNESS_AUDIT.md`. P1-14B.4 contract v1.1 (strict
  unknown-age, grace-deferred terminal PENDING, upgrade rejected with schema
  rationale; 19 new tests; 35 pytest-style tests converted to executing TestCase;
  683/683): 24 setups, 99/99 COMPLETE, 0 dupes, all rows preserved — full details in
  `docs/P1_14B_4_PROSPECTIVE_LIFECYCLE_AUDIT.md`. P1-14B.5 operational PASS
  (independent reference + coincident 35/40-min agreement; 708/708): 49 setups,
  150/150 COMPLETE, 0 dupes, ≥30-min healthy window demonstrated — full details in
  `docs/P1_14B_5_TRANSPORT_RESILIENCE_REPORT.md`. P1-14B.6 PARTIAL (second window
  both regimes; attribution refined to server-side per-connection; abort breached
  unacted — supervision lost; 726/726): 57 setups, 202/202 COMPLETE, 0 dupes —
  full details in `docs/P1_14B_6_REPRODUCIBILITY_READINESS_REPORT.md`. P1-14B.7 PASS
  (supervisor engine + 34 tests incl. real-PID abort; 760/760): 57 setups, 202/202
  COMPLETE, 0 dupes, all rows preserved — full details in
  `docs/P1_14B_7_PERSISTENT_SUPERVISION_AUDIT.md`. P1-14B.8 PASS (35-min supervised
  window post-audited + sentinel layer + brief three-layer validation; 775/775):
  66 setups, 228/228 COMPLETE, 0 dupes, all rows preserved — full details in
  `docs/P1_14B_8_SUPERVISED_RUN_REPORT.md`.
- **Docs:** `docs/PROSPECTIVE_EVALUATION_SPEC.md`, `docs/DECISIONS.md`,
  `docs/CURRENT_STATE.md`, `docs/TASK_QUEUE.md`.
- **Open questions:** MFE/MAE and cohort aggregation deferred to a later
  revision; final horizon list to be frozen once enough 4h data accumulates;
  P1-14B: host-clock skew during the 150s observe window limited outcome
  coverage (documented, not a code defect); P1-14B.1: prolonged-run readiness
  blockers recorded (30+ min healthy window, clock resync note) — no long run
  started; P1-14B.2: 35-min attempt aborted at 23.4 min on transport episode
  (reject rate rule) — duration insufficient, transport limiting, no 4–6 h
  authorization; P1-14B.3: ≤35-min attempt aborted at 17.1 min (second episode
  + path outage after proven watchdog recovery) — duration insufficient,
  transport/freshness limiting, still no 4–6 h authorization; P1-14B.4: contract
  v1.1 enforced (strict unknown-age, grace-deferred terminal PENDING), 120 s
  regression run clean, no long runs; P1-14B.5: ≥30-min healthy window demonstrated
  with reference agreement (repeat advisable);   P1-14B.6: second window both regimes
  (22.6 min healthy), abort breached unacted (supervision lost), attribution refined
  to server-side per-connection — still no 4–6 h authorization; P1-14B.7: abort
  enforcement moved into `control supervise` (registry lease, verified-PID one-shot,
  UNKNOWN-safe) — next supervised window needs explicit instruction, still no 4–6 h;
  P1-14B.8: 35-min supervised window post-audited + sentinel layer validated (brief
  three-layer run) — still no 4–6 h authorization; P1-14B.8-followup (2026-10-11):
  enforce fencing corrected per frontend review `d80fb9b` (locked STOPPING,
  fenced ABORTED/FAILED, real `aborted_by`, owned-lease heartbeat proof, 808/808)
  with no new supervised window on the corrected SHA (historical windows stay
  historical); P1-14B.8-V2-51 (2026-10-11): operation boundary through
  handle-bound termination, run-bound leases, pure `status_readonly()` +
  fenced reconciliation, locked remaining writers, multiprocess proof
  (826/826), no new window; P1-14B.8-V2-52 (2026-10-11): native refusal
  propagation, own-child adoption, C1 barrier+window proof (840/840), no new
  window; P1-14B.8-V2-54 (2026-10-11): exact 32-bit BOOL + ABI proof,
  child-first log handoff on the real-try_register flow, C1 scope qualified
  (850/850), no new window; V2 supervised start still PENDING/separate.
- **Last update:** 2026-10-11 (P1-14B.8 V2-54 BOOL+handoff, DONE acotado).

## F-BT-01 — Historical backtesting (P1-14)

- **Product objective:** replay-based backtester without future leakage;
  24h calibration review of thresholds vs real crossings.
- **Origin / decision date:** `docs/ROADMAP.md` P1-14; SUCCESS_GATES G9.
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** P1-14.
- **Dependencies:** P1-11C outcomes, classifier history, cost model.
- **Affected subsystems:** new backtest module (Phase 2+ overlap noted in
  roadmap — stays research-only).
- **Required UI locations:** V2 Backtest nav/blocked explanation exists;
  results UI TBD.
- **Data/API requirements:** historical bars + outcome tables + fee model.
- **Acceptance criteria:** no-lookahead replay proven; sensitivity noted.
- **Evidence needed:** replay tests + calibration report.
- **Docs:** `docs/ROADMAP.md`, `docs/SUCCESS_GATES.md`.
- **Open questions:** cost/slippage assumptions.
- **Last update:** 2026-10-08.

## F-PAPER-01 — Forward paper validation (P1-15)

- **Product objective:** live paper engine with state-driven exits and
  risk limits; performance vs backtest.
- **Origin / decision date:** `docs/ROADMAP.md`, MASTER_PLAN Phase 4.
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** P1-15.
- **Dependencies:** F-BT-01, risk engine (unbypassable).
- **Affected subsystems:** new paper engine + position manager.
- **Required UI locations:** V2 Paper Lab (blocked explanation exists).
- **Data/API requirements:** live features + state stream + fills sim.
- **Acceptance criteria:** risk limits enforced; halts exercised/reasoned.
- **Evidence needed:** paper-vs-backtest divergence report.
- **Docs:** `docs/PAPER_TRADING.md`, `docs/ROADMAP.md`.
- **Open questions:** none (far horizon).
- **Last update:** 2026-10-08.

## F-PORT-01 — Paper portfolio (P1-16)

- **Product objective:** paper portfolio / dynamic exit management.
- **Origin / decision date:** `docs/ROADMAP.md`, `docs/TASK_QUEUE.md`
  sequence.
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** P1-16.
- **Dependencies:** F-PAPER-01.
- **Affected subsystems:** TBD.
- **Required UI locations:** TBD.
- **Data/API requirements:** TBD.
- **Acceptance criteria:** TBD at phase entry.
- **Evidence needed:** TBD.
- **Docs:** `docs/ROADMAP.md`.
- **Open questions:** scope deferred until P1-15 evidence exists.
- **Last update:** 2026-10-08.

## F-V2-BFF-01 — Next.js API integration (BFF)

- **Product objective:** same-origin BFF proxying allowlisted Python
  endpoints with versioned view-models; browser never touches Python
  directly, SQLite, keys, or the control nonce.
- **Origin / decision date:** `docs/DASHBOARD_V2_FRONTEND_ARCHITECTURE.md`
  + migration plan (DASH-V2-0x slices), 2026-10-07.
- **Approval status:** DECIDED (architecture). **Implementation status:**
  NOT IMPLEMENTED (frontend is static fixtures only).
- **Target phase:** DASH-V2 future slice (explicit authorization).
- **Dependencies:** Python `/api/v1` view-model facade (proposed, not built).
- **Affected subsystems:** `frontend/src/app/api/v1/`, Python API additions.
- **Required UI locations:** all V2 routes (data layer only).
- **Data/API requirements:** envelope (schema_version, provenance,
  freshness, quality flags) per V2 API contracts doc.
- **Acceptance criteria:** BFF security tests (Host/Origin/CSRF/nonce
  non-disclosure/allowlists); no open proxy; Python suite stays green.
- **Evidence needed:** security + contract tests, screenshots.
- **Docs:** `docs/DASHBOARD_V2_FRONTEND_ARCHITECTURE.md`,
  `docs/DASHBOARD_V2_API_CONTRACTS.md`,
  `docs/DASHBOARD_V2_MIGRATION_PLAN.md`.
- **Open questions:** exact `/api/v1` schema validator language.
- **Last update:** 2026-10-11 (DASH-V2-64 backend handoff: reconciled to
  `c635938`; deployed V2 imports this worktree `/src` + `status_readonly()`
  and canonical DB readOnly; legacy read contracts inventoried in
  `docs/DASHBOARD_V1_READ_CONTRACTS.md`; old-UI retirement proposed with
  helper-extraction blocker; GET purity pinned by 3 tests; PARTIAL unchanged,
  no gate advancement. DASH-V2-67 backend: helpers extracted VERBATIM to
  `host_process.py` (stdlib only), `control.py` decoupled from the HTTP
  module, `dashboard.py` re-exports identical objects, boundary tests H1–H4;
  file-level old-UI retirement still NOT executed, pending review.
  DASH-V2-71B backend: System data contracts matrix
  (`docs/DASHBOARD_V2_71_SYSTEM_DATA_CONTRACTS.md`) + read-purity proof
  (1 test, temp fixtures); host resources + ops audit log NOT_AVAILABLE
  (honest absence, future work noted); V2 reads stay on allowlisted
  readers + own readOnly adapter; PARTIAL unchanged, no gate advancement).

## F-LAUNCH-SUP-01 — Supervised transactional launch

- **Product objective:** one atomic operation that starts probe + supervisor
  + sentinel, verifies every component against the run inside a finite
  budget, and rolls back everything launched on any failure. Research and
  operator use only; no trading semantics.
- **Origin / decision date:** V2-55 acceptance checkpoint 2026-10-11
  (enablement NOT authorized); contract `docs/SUPERVISED_LAUNCH_CONTRACT.md`.
- **Approval status:** PROPOSED (pilot brief-120s run needs explicit
  authorization; enablement chain implemented, no run launched).
- **Implementation status:** PARTIAL (contract + enabled backend chain +
  BFF fixed path: readiness-green + START_OBSERVE_2100 + preset allowlist
  + separate status/start/stop budgets + timeout reconcile + capability +
  storage gate + own-keys presets; 2026-10-14, evidence below).
- **Target phase:** O1 pilot (authorized brief run first).
- **Dependencies:** P1-11B.1 run control, P1-14B.7/8 supervision + sentinel,
  registry mutual exclusion, verified termination, pure observation.
- **Affected subsystems:** `control.py` launch section only; dashboard,
  probe, persistence untouched.
- **Required UI locations:** none (BFF renders the outcome envelope only
  after a future enablement review).
- **Data/API requirements:** outcome envelope (outcome/reason/scope/run/
  watchers/verification/rollback/evidence) reusing registry field names,
  nullable-safe; `status_readonly()` stays the GET path.
- **Acceptance criteria:** confirmation only on simultaneous full
  verification (never Popen/lease/heartbeat alone); kill-only rollback of
  transaction PIDs with verified identity; foreign/terminal never touched;
  unverifiable cleanup reported UNCERTAIN with pending evidence.
- **Evidence:** `tests/test_supervised_launch.py` (23 tests + V2PathTest),
  backend directed 143 OK (launch/stop/supervision/abort/identity);
  BFF + UI vitest 255/255 (incl. BotControl 202 x3);
  `docs/evidence/BARRIER_FIX_RESUMEN.json` (barrier 1077 exit 0);
  `docs/evidence/VISUAL_QA_PREPILOTO.txt`.
- **Docs:** `docs/SUPERVISED_LAUNCH_CONTRACT.md`, `docs/ARCHITECTURE.md`,
  `docs/CURRENT_STATE.md`, `docs/DECISIONS.md`,
  `docs/OBSERVATION_RUN_MATRIX.md`.
- **Open questions:** pilot brief-120s authorization (pending user).
- **Last update:** 2026-10-14.

## F-CMC-01 — CoinMarketCap supplementary metadata

- **Product objective:** optional aggregate context (metadata, rankings,
  indices) with mandatory provider labeling; never a Binance mark-price,
  liquidity, fill, PnL, or backtest source.
- **Origin / decision date:** `docs/COINMARKETCAP_FEASIBILITY.md` +
  `docs/EXTERNAL_MARKET_DATA_EVALUATION.md` + `docs/TOKEN_IDENTITY_MAPPING.md`,
  2026-10-07 (staged CMC-00/01/02; legal review still required).
- **Approval status:** DECIDED (staged feasibility; integration NOT
  authorized). **Implementation status:** NOT IMPLEMENTED.
- **Target phase:** CMC-00 (fixtures/mapping) → CMC-01 (bounded keyless
  adapter, needs approval) → CMC-02 (optional).
- **Dependencies:** stable-ID mapping design; legal review; measured
  keyless stability.
- **Affected subsystems:** future backend-only adapter (outside WS path),
  V2 `ProviderAttribution`.
- **Required UI locations:** V2 market context / profiles (when built).
- **Data/API requirements:** ID map + metadata caches with budget TTLs.
- **Acceptance criteria:** verified stable-ID mapping; fixtures for
  ambiguity/429/outage/stale; Binance-only execution math.
- **Evidence needed:** mapping fixtures + adapter tests (none exist).
- **Docs:** as listed under Origin.
- **Open questions:** keyless rate stability, category value, credentials.
- **Last update:** 2026-10-08.

## F-CORE-01 — Completed Phase 1 foundations (evidence index)

- **Product objective:** N/A (index entry — prevents re-planning or
  duplicating finished work).
- **Origin:** phase completion records in `docs/TASK_QUEUE.md`.
- **Approval status:** DECIDED. **Implementation status:** VERIFIED.
- **Target phase:** P1-00…P1-11C, P1-10R (all DONE).
- **Dependencies:** none remaining.
- **Affected subsystems:** N/A (index).
- **Required UI locations:** N/A.
- **Data/API requirements:** N/A.
- **Acceptance criteria:** phase PASS records linked below.
- **Evidence:** COMPLETED section of `docs/TASK_QUEUE.md`; 447/447 suite;
  `logs/p1-10r/` soak evidence (git-ignored, preserved).
- **Docs:** `docs/CURRENT_STATE.md`, `docs/PHASE_1_REPORT.md` (untouchable).
- **Open questions:** none.
- **Last update:** 2026-10-08.

Completed, evidence-linked work:

- P1-00 tooling (`python run_tests.py`) — VERIFIED, 447/447.
- P1-01/P1-01R transport validation — VERIFIED (45min healthy window).
- P1-02 persistence (SQLite, retention-bounded) — VERIFIED.
- P1-03/P1-09 dashboards (Python SSR + terminal) — VERIFIED, live.
- P1-04…P1-08 engines (returns → structure) — VERIFIED (P1-11A scales).
- P1-10R ≥6h soak — PASS (21603.9s, evidence `logs/p1-10r/`).
- P1-10R-FIX-01 console suppression — FIXED.
- P1-11A/B/C research chain — PASS.
- P1-12A classifier v0 — PASS.
- DASH-V2-00/01/02 slices — DONE (static foundation, no integration).

## Mandatory closeout policy

Every future implementation or documentation phase must report these
seven fields in its final report (verbatim names):

- `DECISIONS_REVIEWED` — which decision records were read.
- `NEW_DECISIONS_RECORDED` — what was appended, where.
- `FEATURES_IMPLEMENTED` — backlog IDs completed with evidence.
- `FEATURES_VERIFIED` — backlog IDs verified with evidence links.
- `DEFERRED_FEATURES` — IDs intentionally left not-implemented.
- `BACKLOG_UPDATED` — whether this file changed and why.
- `DOCUMENTATION_CONFLICTS` — contradictions found (fixed or flagged).

If a new material decision needs user approval, record it as PROPOSED
here and request approval before treating it as binding. Never mark
features VERIFIED without evidence.


## F-R3CAP-04 — R3 vivo brief 120s (2026-10-16, autorizada 1x)

- `DECISIONS_REVIEWED` — F-R3CAP-03 (atribucion exacta),
  captura v2, contratos runtime/BFF/detections, readiness.
- `NEW_DECISIONS_RECORDED` — DECISIONS §R3 vivo brief
  (lanzamiento unico reconciliado por GET sin duplicar;
  PASS vivo con triple RUNNING exact-uuid).
- `FEATURES_IMPLEMENTED` — (sin codigo) corrida supervisada
  brief 120s observe-only + captura automatica con ambas
  identidades fijadas.
- `FEATURES_VERIFIED` — capturador: outcome terminal-captured,
  R3 PASS (t0/+30/+60 RUNNING verificados, exact-uuid,
  snapshot coincidente, current, detections atribuidas;
  0 eventos iniciales validos, 18/3 desde +60s); cierre
  COMPLETED exit 0, 133s congelado, 0 python, sin journals,
  filas UUID 4/6/39/9, JSON + resumen + 2 capturas V2.
- `DEFERRED_FEATURES` — trabajo offline de entradas/salidas
  (recomendado, no ejecutado): engine + runner + mapping +
  funding realizado + costes + purga; paper/ejecucion.
- `BACKLOG_UPDATED` — yes: this entry (ID F-R3CAP-04).
- `DOCUMENTATION_CONFLICTS` — none new (respuesta 200 del
  start sin run_id en nivel superior: reconciliacion
  documentada, sin duplicar).

## F-R3CAP-03 — atribucion exacta R3 (2026-10-16, sobre a2aebc5, sin corridas)

- `DECISIONS_REVIEWED` — R3 v2 (veredicto separado, UUID
  tardio, detections verificado), atribucion del feed
  (sin gracia, run_id primero, regresion 20s), identidad
  UNKNOWN + feed estricto, contratos runtime/BFF/detections.
- `NEW_DECISIONS_RECORDED` — DECISIONS §Atribucion exacta R3
  (method/snapshot_run_id/timestamp; PASS solo exact-uuid con
  UUID registro=snapshot; temporal nunca prueba exacto).
- `FEATURES_IMPLEMENTED` — BFF: `feed_attribution_method` +
  `feed_snapshot_run_id` + `feed_snapshot_timestamp` aditivos
  (salud/umbrales/Start-Stop intactos); capturador: conserva
  los tres campos y exige exact-uuid + coincidencia doble +
  resto de identidad para PASS.
- `FEATURES_VERIFIED` — BFF 4 nuevos + capturador 3 nuevos
  (temporal HEALTHY/current sin UUID -> UNKNOWN;
  coincidente+exact -> puede calificar; incompatible ->
  nunca PASS); suites locales frontend 304/304 + capturador
  19/19 + export 6/6 + typecheck; sin Binance.
- `DEFERRED_FEATURES` — R3 vivo, redeploy V2 3020 (build
  anterior intacto), mapping, funding, costes, purga,
  entradas/salidas, paper, ejecucion.
- `BACKLOG_UPDATED` — yes: this entry (ID F-R3CAP-03).
- `DOCUMENTATION_CONFLICTS` — none new (temporal util pero
  no probatorio; PROPOSED + mecanica intactos).

## F-R3CAP-02 + F-ENTRY-PREP-02 — veredicto R3 y causalidad (2026-10-16, sobre 69d55ba, sin corridas)

- `DECISIONS_REVIEWED` — captura v1, contrato de velas real,
  conversion del runner, `input_hash`, reglas de conocimiento v4.2.
- `NEW_DECISIONS_RECORDED` — DECISIONS §R3 v2 + causalidad;
  contrato close_time/as_of en inventario.
- `FEATURES_IMPLEMENTED` — captura: veredicto separado + UUID
  tardio/ausencias + detections verificado + identidades fijadas;
  export/runner: close_time aditivo + as_of + cadena; motor
  intacto (campo solo procedencia).
- `FEATURES_VERIFIED` — 6 R3 (terminal-directo, tardio, incompatible,
  foreign, UNKNOWN-completo, PASS con fijadas) + 4 export/causal
  (close_time, as_of vs cutoff, preservacion, intra-vela con
  control negativo); locales, sin Binance.
- `DEFERRED_FEATURES` — R3 vivo, mapping, funding, costes, purga,
  entradas/salidas, paper, ejecucion.
- `BACKLOG_UPDATED` — yes: this entry (IDs F-R3CAP-02,
  F-ENTRY-PREP-02).
- `DOCUMENTATION_CONFLICTS` — none new (PROPOSED + mecanica
  intactos; prep economico no repetido).

## F-R3CAP-01 + F-ENTRY-PREP-01 — captura R3 + prep offline (2026-10-16, sobre 48445f2, sin corridas)

- `DECISIONS_REVIEWED` — cierre brief R1-R11, contratos runtime/
  detecciones/BFF, motor v4.2 + runner, P1-11C, klines retenidos.
- `NEW_DECISIONS_RECORDED` — DECISIONS §R3 capture + prep;
  `docs/ENGINE_ENTRY_EVAL_INVENTORY.md`; reconciliacion 10+1 y
  UNKNOWN/STALE por capas.
- `FEATURES_IMPLEMENTED` — F-R3CAP-01: `scripts/capture_run_window.py`
  (GET-only, pin, +30/60/90, terminal acotado, salida protegida);
  F-ENTRY-PREP-01: `scripts/export_engine_inputs.py` (PROPOSED map
  no aprobado) + inventario + prep mecanico en temp.
- `FEATURES_VERIFIED` — captura 10 + export 2 (locales, sin Binance);
  prep: 8637 velas/1558 eventos/hash/discartes/versiones; economia
  RETENIDA (no leida, no presentada).
- `DEFERRED_FEATURES` — R3 PASS vivo (proxima ventana autorizada);
  mapping H, funding realizado, costes medidos, purga; entradas/
  salidas, backtests validantes, paper, ejecucion.
- `BACKLOG_UPDATED` — yes: this entry (IDs F-R3CAP-01,
  F-ENTRY-PREP-01).
- `DOCUMENTATION_CONFLICTS` — corregidos aqui: "9 PASS" (10+1) y
  backtests jamas inexistentes (reutilizados v4.2 + runner).

## F-LINK-01 + F-EPISODE-V1-01 — piloto brief 20261016T005550Z (2026-10-16, 1x120s autorizada)

- `DECISIONS_REVIEWED` — trazabilidad stem<->UUID, episodios v1,
  contratos runtime/BFF/detections, reconciliacion OBS10M.
- `NEW_DECISIONS_RECORDED` — DECISIONS §piloto brief; evidencia
  `docs/evidence/RUN_BRIEF120_20261016_CLOSEOUT.json` (+2 capturas V2).
- `FEATURES_IMPLEMENTED` — (sin codigo) prueba viva del enlace
  automatico + agrupacion v1 sobre 10 eventos nuevos.
- `FEATURES_VERIFIED` — matriz R1-R11 en el JSON: 10 PASS
  (R1,R2,R4-R11), R3 UNKNOWN (feed mid-run en vivo no capturado;
  enlace exacto disponible + path probado offline), 0 FAIL
  (correccion: el "9 PASS" anterior era error de conteo); 54 filas
  UUID = research.writes; V2 10/2 con enlace exacto y sin mezcla.
- `DEFERRED_FEATURES` — R3 mid-run (residual), evaluacion de
  entradas/salidas, backtests, paper, ejecucion; resto excluido.
- `BACKLOG_UPDATED` — yes: this entry (IDs F-LINK-01,
  F-EPISODE-V1-01, prueba viva, sin VERIFIED economico).
- `DOCUMENTATION_CONFLICTS` — none new (98/4 parcial vs 245/13
  completo ya distinguidos; filas del run vs delta neto por
  retencion distinguidos aqui).

## F-LINK-01 + F-EPISODE-V1-01 — trazabilidad y episodios (2026-10-16, sobre d7dcc70, sin nuevas corridas)

- `DECISIONS_REVIEWED` — control/registro/leases/identidad,
  detector funding, contratos runtime/BFF, V2 (sin consumo crudo),
  reconciliacion OBS10M.
- `NEW_DECISIONS_RECORDED` — DECISIONS §trazabilidad+episodios;
  `docs/EVENT_EPISODES.md` (contrato v1); contratos runtime/BFF.
- `FEATURES_IMPLEMENTED` — F-LINK-01: link_probe_run_id fenced +
  probe_run_id en status + lector exacto con rechazo incompatible;
  F-EPISODE-V1-01: agrupacion v1 + BFF /detections + panel System.
- `FEATURES_VERIFIED` — linkage 7 + episodios 5 (245 retenidos) +
  detecciones 5 + persistencia-linkage 4 restaurados (P3 v10/propaga-
  cion/rehidratacion, `test_persistence_run_linkage.py` verbatim HEAD)
  + feed/BFF/panel nuevos; Start/Stop/propiedad en
  barrera; suites abajo.
- `DEFERRED_FEATURES` — episodios en otras vistas sin fuente
  reconstruible (limitacion informada, no inventada); resto excluido.
- `BACKLOG_UPDATED` — yes: this entry (IDs F-LINK-01,
  F-EPISODE-V1-01).
- `DOCUMENTATION_CONFLICTS` — corregidos: "episodios independientes"
  (agrupados por regla), "byte-identico" sin hashes (tamano estable
  + contenido modificado).

## O2 reconciliation UUID/persistence/funding - 2026-10-16 (sobre 67472e0, sin nuevas corridas)

- `DECISIONS_REVIEWED` — informe OBS10M, codigo recorder/resolve,
  esquema y contenidos DB, log de la corrida.
- `NEW_DECISIONS_RECORDED` — addendum + JSON de reconciliacion (esta
  entrada los indexa).
- `FEATURES_IMPLEMENTED` — correccion UUID/persistencia/funding en el
  informe + addendum + evidencia estructurada (no codigo).
- `FEATURES_VERIFIED` — UUID exacto (20/20 + final_summary + vecinas),
  246 writes a historical.db con UUID (183+33+30), 245 = 13 episodios;
  Starting/Stop/umbrales/identidad no tocados (sin codigo).
- `DEFERRED_FEATURES` — baseline por tabla pre-run (proxima ventana),
  resto excluido.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — corregidos aqui: UUID quimera del
  informe, "historical.db sin cambios" (contenido nuevo con 0B),
  245 como cruces independientes (son 13 episodios).

## O2 observation-10m run completed - 2026-10-15 (autorizada, sobre 10cad5c, push 67472e0)

- `DECISIONS_REVIEWED` — preset observation-10m, readiness verde 6/6,
  registro terminal previo, DB legible, cadena supervisada.
- `NEW_DECISIONS_RECORDED` — informe RUN_OBS10M_20261015_COMPLETED
  (ventana, metricas, comparacion con piloto, veredicto acotado).
- `FEATURES_IMPLEMENTED` — primera ventana 600s supervisada via V2
  (no codigo).
- `FEATURES_VERIFIED` — arranque confirmado, 0 rechazos, watchers
  22+22, cierre natural, PIDs muertos, COMPLETED 610s, SQLite+V2, sin
  journal, barra fiel inicio/mitad/final; evidencia + 2 capturas.
- `DEFERRED_FEATURES` — validacion economica (dos ventanas no bastan),
  proximas ventanas, resto.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## V2 feed attribution fix - 2026-10-16 (sobre 3f2fcea, sin nuevas corridas)

- `DECISIONS_REVIEWED` — hardening 3f2fcea, id-spaces registry/DB,
  propiedad, umbrales 0.05/0.5.
- `NEW_DECISIONS_RECORDED` — DECISIONS §correccion + contrato feed
  (sin gracia, run_id priorizado, cruce runtime, regresion 20s).
- `FEATURES_IMPLEMENTED` — atribucion estricta (exacta > temporal),
  previous-run nunca HEALTHY, UNKNOWN sin certeza.
- `FEATURES_VERIFIED` — regresion 20s A/B + run_id exacto +
  runtime-inconsistente; Start/Stop/propiedad/umbrales/identidad
  intactos (suites abajo).
- `DEFERRED_FEATURES` — nuevas corridas, resto excluido.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## V2 identity/feed hardening - 2026-10-16 (sobre 3544ad6, sin nuevas corridas)

- `DECISIONS_REVIEWED` — visibilidad 3544ad6, aborto 0.05, display 0.5,
  staleness cadence vs event-driven, propiedad PID+imagen+ctime.
- `NEW_DECISIONS_RECORDED` — DECISIONS §endurecimiento + contratos feed
  (HEALTHY estricto, atribucion, 0.05 vs 0.5, missing/silent/parse).
- `FEATURES_IMPLEMENTED` — display unknown/gone/replaced, terminal
  explicito, expiracion 30s, feed estricto con atribucion previous-run.
- `FEATURES_VERIFIED` — feed 12 nuevos (invalido/cero/faltante/0.06/
  limpio/previous-run/missing/silent/parse + piloto), supervision 3,
  barra 5, BotControl 4; Start/Stop/propiedad intactos (67 backend).
- `DEFERRED_FEATURES` — nuevas corridas, resto excluido.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new (0.05 enforced vs 0.5 display
  reconciliados por escrito; umbrales intactos).

## V2 run visibility - 2026-10-16 (sobre 5d4fef6, sin nuevas corridas)

- `DECISIONS_REVIEWED` — control canonico (start/stop/supervise/sentinel/
  launch), readiness por capability + storage, BotControl 202 + reconcile,
  identidad host PID+imagen+ctime, contratos runtime V2, piloto COMPLETED
  + aborto previo + journal forense.
- `NEW_DECISIONS_RECORDED` — DECISIONS §visibilidad global + §reconciliacion
  piloto; contratos runtime V2 actualizados; reconciliacion en
  `docs/PILOT_BRIEF_20261015_RECONCILIATION.md`.
- `FEATURES_IMPLEMENTED` — barra global RunStatusBar (todas las pantallas),
  stop proyecto verificado (dashboard/agent/direct), campos run_id/
  process_state/verified/last_exit_at + feed enriquecido, BotControl
  registrado-vs-verificado + terminal congelado.
- `FEATURES_VERIFIED` — backend `tests/test_run_visibility.py` 10 OK
  (origenes, stop, identidad incompleta, reemplazo, timeout, desconexion,
  cierre natural, aborto; procesos sleep aislados); frontend 63 OK
  (bot-control/run-status-bar/stop/start/contract); typecheck limpio;
  barrera completa y QA visual pendientes en el cierre.
- `DEFERRED_FEATURES` — nuevas corridas/pilotos, validacion economica,
  resto O2-O5/IA/Kronos (excluidos).
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — corrected: "V2 will not stop agent runs"
  (ahora stop proyecto verificado); "aborto previo = transporte
  concluyente" (ahora origen UNKNOWN con retraso observado);
  feed UNKNOWN permanente en BFF (ahora enriquecido desde telemetry).

## O1 pilot completed - 2026-10-15 (autorizado, sobre 1c566b1)

- `DECISIONS_REVIEWED` — plan brief, readiness verde, plan de captura.
- `NEW_DECISIONS_RECORDED` — DECISIONS §piloto completado (ventana,
  metricas, veredicto acotado).
- `FEATURES_IMPLEMENTED` — primera ventana sana supervisada (no codigo).
- `FEATURES_VERIFIED` — arranque confirmado, 0 rechazos, watchers 6+6,
  cierre natural, PIDs muertos, COMPLETED, SQLite+V2, sin journal;
  evidencia PILOT_BRIEF_20261015_COMPLETED + copia maintenance JSON.
- `DEFERRED_FEATURES` — validacion economica (una ventana no basta),
  proximas ventanas, resto.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 maintenance applied - 2026-10-15 (autorizado, sobre e773e51)

- `DECISIONS_REVIEWED` — procedimiento DB_MAINTENANCE_RECOVERY.md.
- `NEW_DECISIONS_RECORDED` — DECISIONS §mantenimiento aplicado.
- `FEATURES_IMPLEMENTED` — recovery aplicado (no codigo nuevo).
- `FEATURES_VERIFIED` — apply PASS, journal consumido, hash
  byte-identico, readiness 6/6, 5 rutas 200, monitor no arrancado.
- `DEFERRED_FEATURES` — proximo piloto (nueva autorizacion), resto.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 window reconciliation - 2026-10-16 (sobre e0b0141)

- `DECISIONS_REVIEWED` — lock-probe forense, registry states, hot
  fixture recipe, spy design.
- `NEW_DECISIONS_RECORDED` — DECISIONS §ventana por registry (forense
  + ventana + hot real + spy).
- `FEATURES_IMPLEMENTED` — ventana registry, fixture hot, spy test.
- `FEATURES_VERIFIED` — journal 22/22, spy fail-before/passa-after,
  barrera pendiente.
- `DEFERRED_FEATURES` — apply (sin solicitar aun), piloto, resto.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 maintenance reconciliation - 2026-10-16 (sobre 3a55052)

- `DECISIONS_REVIEWED` — backup/rollback, hash binding, writer locks,
  pre/post comparison.
- `NEW_DECISIONS_RECORDED` — DECISIONS §mantenimiento aplicable;
  DB_MAINTENANCE_RECOVERY con backup real + comando definitivo.
- `FEATURES_IMPLEMENTED` — --apply con backup/writer/drift/compare.
- `FEATURES_VERIFIED` — journal 22/22, barrera 1108 exit 0, destino
  verificado fuera/inexistente.
- `DEFERRED_FEATURES` — apply canonico (autorizacion), piloto, resto.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 correction reconciliation - 2026-10-16 (sobre 6264ccc)

- `DECISIONS_REVIEWED` — receive-path stamping order, fixture journal
  forensics (magia cero vs hot real), backup/protecciones.
- `NEW_DECISIONS_RECORDED` — DECISIONS §correccion revision (nombres
  honestos, test ruta real, --apply/backup, informe publicado).
- `FEATURES_IMPLEMENTED` — renombres + RealReceivePathTest + --apply
  completo + 14 tests recover/backup.
- `FEATURES_VERIFIED` — attribution 6/6 (3x ruta real), journal 14/14,
  barrera 1100 exit 0, rehearsal publicado re-ejecutable.
- `DEFERRED_FEATURES` — apply canonico (autorizacion), proximo piloto,
  resto excluido.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new (queue/transit renombrado en
  codigo+tests+docs a dispatch/yield).

## O1 journal/attribution reconciliation - 2026-10-15 (sobre 9b78058)

- `DECISIONS_REVIEWED` — journal/WAL readOnly, `_connection_loop`
  buffering, skew-guard path, telemetry summary shape.
- `NEW_DECISIONS_RECORDED` — `docs/DECISIONS.md` §journal+atribucion;
  `docs/DB_MAINTENANCE_RECOVERY.md` (PROPUESTO, sin aplicar).
- `FEATURES_IMPLEMENTED` — recovery rehearsal script + queue/transit
  instrumentation (threshold untouched).
- `FEATURES_VERIFIED` — rehearsal report (integrity ok, diff 0),
  5 attribution tests, barrier pending (probe.py touched).
- `DEFERRED_FEATURES` — canonical recovery apply (authorization
  pending), next pilot, resto excluido.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 pilot post-mortem reconciliation - 2026-10-15 (sobre 51d6095)

- `DECISIONS_REVIEWED` — abort rule timestamp-reject-rate, `_status_view`
  counters, `_is_active_state`, BFF concurrency check, journal/WAL
  readOnly semantics.
- `NEW_DECISIONS_RECORDED` — `docs/DECISIONS.md` §"Post-mortem piloto
  brief" (cronologia, diagnostico sin tocar umbral, error SQLite exacto,
  congelado de contador, ABORTED terminal).
- `FEATURES_IMPLEMENTED` — congelado de contador terminal + ABORTED
  terminal en readiness (sin otro alcance).
- `FEATURES_VERIFIED` — TerminalCounterTest (fail-before), readiness
  ABORTED test, barrera completa pendiente (control.py tocado),
  evidencia `PILOT_BRIEF_20261015_ABORT.txt`.
- `DEFERRED_FEATURES` — proximo piloto (autorizacion), journal recovery
  (proxima corrida autorizada), resto O2-O5/IA/Kronos (excluidos).
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 defect-fix reconciliation - 2026-10-14 (review/o1-funcional-v2-observacion, sobre 972a19e)

- `DECISIONS_REVIEWED` — 202-chain (BFF 202 + reconcile-before-retry),
  host identity call sites (`pid_is_ours` gates), migration pins v9/v2.
- `NEW_DECISIONS_RECORDED` — `docs/DECISIONS.md` §"Cierre defectos
  pre-piloto" (202-pending + two-read reconcile; `_run_text` UNKNOWN +
  expected-without-real False; versioned temp fixtures).
- `FEATURES_IMPLEMENTED` — F-LAUNCH-SUP-01 UI safety (no new scope).
- `FEATURES_VERIFIED` — BotControl 8/8, robustness 15/15, directed 143
  OK, barrier 1077 exit 0 (`BARRIER_FIX_*`), frontend 255/255.
- `DEFERRED_FEATURES` — pilot brief-120s (authorization pending); test
  redesign beyond fixtures; any O2-O5/IA/Kronos/redesign (excluded).
- `BACKLOG_UPDATED` — yes: this entry + F-LAUNCH-SUP-01 evidence line.
- `DOCUMENTATION_CONFLICTS` — none new; prior MATRIX/handoff fixes stand.

## O1 pre-pilot reconciliation - 2026-10-14 (review/o1-funcional-v2-observacion, sobre e887287)

- `DECISIONS_REVIEWED` — DASH-V2-62/55/51 supervision chain, R8/R9 funding
  causality, 4f1d92e Start-flag record, 207186d operational inventory,
  27b7af5 read handoff, storage preflight docstring + thresholds.
- `NEW_DECISIONS_RECORDED` — `docs/DECISIONS.md` §"Revision independiente
  pre-piloto" (budgets 4200/8000/65000 + START_TIMEOUT_UNCERTAIN/202 +
  ALREADY_RUNNING pre-check; capability-not-callable; storage
  block-256MB/warn-1GB; own-keys presets; compat 9/10+2/3 correction).
- `FEATURES_IMPLEMENTED` — F-LAUNCH-SUP-01 chain (PARTIAL→pilot-ready,
  no run), F-V2-BFF-01 control/data paths (start/stop/readiness +
  supervision/diagnostics/storage-preflight + 9/10 + 2/3 readers).
- `FEATURES_VERIFIED` — vitest 252/252 (232 base + 20 new), typecheck,
  lint 0 errors (1 pre-existing warning), build 31 routes, backend
  directed 49 OK, barrier 1062 (control green; 11 pre-existing contrasted),
  preview QA 10/10 HTTP 200 + 7 captures + 0 overflow + hashes unchanged.
- `DEFERRED_FEATURES` — pilot brief-120s run (needs explicit authorization);
  any other O2-O5 work; migration-pin test redesign (data-state-dependent,
  out of scope, documented).
- `BACKLOG_UPDATED` — yes: F-LAUNCH-SUP-01 status/evidence (this file).
- `DOCUMENTATION_CONFLICTS` — fixed: MATRIX/handoff "v10/v3 incompatible"
  (was 27b7af5-only), prospective hardcoded schema 9, SCHEMA-9 eyebrow,
  `data/historical.db` path, MATRIX dangling STORAGE_PREFLIGHT_CONTRACT ref.

## DASH-V2-62 reconciliation - 2026-10-11

F-LAUNCH-SUP-01 remains PROPOSED for enablement / PARTIAL overall. The five new implementation findings and two contract notes are corrected in disabled preparation; 29 new tests, 902/902 canonical and 52/52 targeted OK. Report: DASH_V2_62_SUPERVISED_LAUNCH_CORRECTIONS.md. Operational readiness, real watcher startup binding, enabled access and longevity remain unverified/deferred. F-P14A-01 historical windows unchanged; no new run or gate advancement. User-authorized direct backend correction replaces the V2-61 handoff for these findings; no need for the other agent to repeat them.

## F-OFFLINE-EVAL-01 — cierre evaluacion offline entradas/salidas V1 (2026-10-16, sin ventana forward, sin simulacion prospectiva)

- `DECISIONS_REVIEWED` — diseno OFFLINE_EVAL_DESIGN_V1 (corte+purga,
  solape, baseline, costes, non-pristine), mapping MAP-CANDIDATE-v1
  (auditoria retrospectiva, H1/H2/H3), contrato de lectura
  OFFLINE_EVAL_READ_CONTRACT_V1, motor v4.2 + runner reutilizados,
  adquisicion FUNDING-CAL-v1, R3 vivo b1f2aaf como alcance previo.
- `NEW_DECISIONS_RECORDED` — DECISIONS (Offline entry/exit closeout V1:
  causalidad por operacion, reconciliacion 1558→1557→1412, funding
  1+1403+8 con "4 ventanas" anulado, exposicion intra-celda, unidades
  USDT/1000 USD con friccion ~1.60, costes supuestos, non-pristine,
  pooled no comparable).
- `FEATURES_IMPLEMENTED` — auditoria reproducible offline (export +
  seleccion + runner re-ejecutados en temp, hashes iguales al artefacto)
  + docs/evidence/OFFLINE_EVAL_AUDIT_V1.json (1412 tripletas
  formation/available/entry) + informe V1 corregido (fuente/admitidas,
  funding, exposicion, unidades) + diseno (alcance intra-celda, pooled no
  comparable) + mapping (puntero a prueba por operacion) + nota de alcance
  en OfflineEvalSection + captura visual 3020.
- `FEATURES_VERIFIED` — backend 1168/1168 OK + barrera exit 0
  (0 prohibidos/bloqueados/efectivos, 1 RO esperado, hashes iguales, sin
  diffs) + frontend 310/310 + typecheck limpio + replays 452+457+503=1412
  con input_hash identicos + causalidad 1412/1412 sin violaciones +
  sensibilidad 12/12 celdas negativas a 2x + QA visual 3020
  (overview + historical-research con seccion, 0 errores consola).
- `DEFERRED_FEATURES` — ventana forward pristina (no adquirida),
  simulacion prospectiva (no iniciada), mapping aprobado, costes medidos,
  modelo de posicion/exposicion, baselines alternativos
  (buy-and-hold/placebo/aleatorio), paper/ejecucion.
- `BACKLOG_UPDATED` — yes: this entry (ID F-OFFLINE-EVAL-01).
- `DOCUMENTATION_CONFLICTS` — corregidos aqui: ETH 497 (admitidas) vs 498
  (fuente), SOL H2 7→6, friccion ~1.0→~1.60/op, "4 ventanas"→1 sostenida,
  pooled-como-cartera (nunca fue cartera), build servido 3020 identificado
  en CURRENT_STATE (sin redeploy en este cierre).

## F-OFFLINE-EVAL-02 — artefacto publicado + generacion determinista (2026-10-16, sin corridas)

- `DECISIONS_REVIEWED` — F-OFFLINE-EVAL-01, contrato de lectura
  OFFLINE_EVAL_READ_CONTRACT_V1, informe §10, adquisicion FUNDING-CAL-v1.
- `NEW_DECISIONS_RECORDED` — DECISIONS (Fix artefacto offline-eval:
  force-add + agregador byte-identico + hashes funding reconciliados +
  limitacion dataset declarada).
- `FEATURES_IMPLEMENTED` — `scripts/aggregate_offline_eval.py`
  (bundling fail-closed) + `tests/test_offline_eval_aggregation.py`
  (6 tests) + artefacto publicado por force-add (pin c051e888… intacto)
  + informe §10 y contrato actualizados + hashes funding reconciliados.
- `FEATURES_VERIFIED` — regeneracion byte-identica del artefacto desde
  replays en temp (mismo sha) + celdas↔manifiestos identicas + nuevo test
  6/6 + checkout limpio (frontend tests + typecheck + build, sin
  data/logs/canonicos; logs abajo).
- `DEFERRED_FEATURES` — mismos que F-OFFLINE-EVAL-01; publicacion del
  historico canonico (no publicado; limitacion declarada).
- `BACKLOG_UPDATED` — yes: this entry (ID F-OFFLINE-EVAL-02).
- `DOCUMENTATION_CONFLICTS` — corregidos aqui: artefacto ausente en Git
  (404 en limpio), ruta de test en contrato (`src/`→`frontend/src/`),
  hashes funding del draft (transitorios → provenance verificables).

## F-OFFLINE-EVAL-03 - paquete reproducible + causalidad + costes + protocolo (2026-10-17, sin corridas, sin push aun)

- DECISIONS_REVIEWED - paquete/artefacto V1, mapping MAP-CANDIDATE-v1, motor v4.2 + runner, contratos offline-eval, funding/calendarios, P1-11C Carteras, backlog F-OFFLINE-EVAL-02.
- NEW_DECISIONS_RECORDED - DECISIONS parrafo 2026-10-17 (paquete/causalidad/costes/protocolo/V2); docs OFFLINE_EVAL_PACKAGE_V1 (manifiesto), OFFLINE_EVAL_CAUSAL_AUDIT_V2 (matriz), OFFLINE_EVAL_COST_BREAKEVEN_V1 (breakeven+exposicion), PROSPECTIVE_PROTOCOL_V1 (preparacion, no ejecutado).
- FEATURES_IMPLEMENTED - paquete temp + zip + event_ids 1:1 + scripts/reproduce_offline_eval.py; 4 docs; V2 OfflineEvalSection (3 bloques lectura); tests breakeven 7 + causalidad 3.
- FEATURES_VERIFIED - replay byte-identico (c051e888) + input_hash x3 + invariancia 18/18 + s*/fragilidad 2x + frontend offline-eval + typecheck; build + QA visual 3020 pendientes al cierre.
- DEFERRED_FEATURES - publicacion DB canonica/zip (fuera de Git; reproduccion externa PENDIENTE); MAP-APPROVED-v1; disponibilidad live; ventana pristina; costes medidos; TIME-PLACEBO-v1; paper/ejecucion; gates.
- BACKLOG_UPDATED - yes: this entry (ID F-OFFLINE-EVAL-03).
- DOCUMENTATION_CONFLICTS - none new (agregacion != replay distinguido; pooled no cartera reiterado; H3 nunca recuperacion).

## F-EXTREME-OBJECTIVE-01 — Objetivo de movimientos extremos preservado (2026-10-16)
Objetivo de producto: REAFIRMADO POR USUARIO. Plan tecnico: DOCUMENTADO,
PENDIENTE DE AUDITORIA/IMPLEMENTACION por componentes. No feature completa.
Fuente: PRODUCT_GOAL + MASTER_PLAN + EXTREME_MOVERS_OBJECTIVE.md.
Aceptacion: selector causal bilateral, denominadores y cobertura fuera del
trio, enlace evidencia-decision-posicion, costes/exposicion y V2 trazable.
No aprobar mapping ni umbrales por registrar este ID. Reutilizar discovery,
classifier, opportunity, motor/runner y contratos existentes.
DECISIONS_REVIEWED: AGENTS, estado/cola/master/decisions/gates/workflow/backlog,
PRODUCT_GOAL y SIGNAL_RESEARCH_PLAN en base b748d22.
NEW_DECISIONS_RECORDED: alcance de producto preservado; no metodologia nueva.
FEATURES_IMPLEMENTED: documentacion y enlaces, ningun codigo de producto.
FEATURES_VERIFIED: contraste documental; sin pruebas de estrategia nuevas.
DEFERRED_FEATURES: delta selector, cobertura, V2 Backtest/Paper, validacion,
ejecucion segun fases/autorizaciones. IA/Kronos siguen diferidos.
BACKLOG_UPDATED: este ID, sin promover implementacion ni gates.
DOCUMENTATION_CONFLICTS: estados historicos desactualizados preservados;
map H2 mecanico no es fade/rebote validado; funding 8h del plan Paper antiguo
debe reconciliarse al implementar, usando calendario por simbolo.
(Integracion 2026-10-17 desde review/extreme-movers-objective-20261016
hasta 7a4e872; implementacion parcial, secuencia conservada.)

## F-STRUCTURE-EXIT-01 — Estructura historica y gestion dinamica (2026-10-16)
Objetivo documentado por solicitud del usuario; implementacion NO declarada.
Spec: HISTORICAL_STRUCTURE_AND_EXIT_PLAN.md. Depende de auditoria causal/costes,
datos multihorizonte y gestion/riesgo segun fases. No parametros aprobados.
DECISIONS_REVIEWED: instrucciones/planes/gates/workflow y documentos de mercado,
posicion y objetivo previamente auditados en esta rama documental.
NEW_DECISIONS_RECORDED: contexto por zonas y retencion compacta; sin regla trading.
FEATURES_IMPLEMENTED: plan y enlaces documentales solamente.
FEATURES_VERIFIED: contraste con MARKET_DATA y POSITION_MANAGEMENT; sin codigo.
DEFERRED_FEATURES: ingestion/cache/pivotes/ajustes/UI/paper segun auditoria y gates.
BACKLOG_UPDATED: este ID; no cambia fase activa ni autorizaciones.
DOCUMENTATION_CONFLICTS: fuentes historicas y paper funding 8h requieren
reconciliacion al implementar; no extrapolar cobertura local a vida del token.
(Integracion 2026-10-17 desde review/extreme-movers-objective-20261016
hasta 7a4e872; diseno, no garantia.)

## F-EVAL-CENSUS-TRACE-01 — Auditoría trazabilidad EVAL-CENSUS-V2 (2026-10-17)
Addendum sobre commit b5cd690 (1385927 = prefijo SHA del commit EVAL-CENSUS-V2, no run_id).
FEATURES_IMPLEMENTED: ledger de flujo reconstruido desde manifiestos ejecutados + artefacto publicado;
verificador reproducible (20 regresiones, todas pasan); corrección 12/12 vs 18/18; funding separado
(741 aplicaciones vs 270 liquidaciones únicas; 0 unknown-excluded ≠ cobertura completa; 24/60 uncovered);
MF/MAE documentadas como excursión no captura; duplicados 594/616 mecanismo verificado (subset BTC15m: 129/135).
FEATURES_VERIFIED: totales y conteos separados (hipótesis 7152/2991/5/4161; placebo 7152/2264/2/4888; total 14304/5255/7/9049) contra manifiestos y artefacto.
DEFERRED_FEATURES: incorporar manifiestos temp/opencode a Git para trazabilidad completa (vínculo detección→operación UNKNOWN); verificación exacta de 594/616 sobre censo completo (reconstruct lento, timeout).
DOCUMENTATION_CONFLICTS: "18/18" del mensaje de commit corregido a "12/12 direccionales"; "0 unknown-excluded" no presentado como cobertura completa.
BACKLOG_UPDATED: este ID; sin cambio de fase activa ni autorizaciones. Gates sin avance.


