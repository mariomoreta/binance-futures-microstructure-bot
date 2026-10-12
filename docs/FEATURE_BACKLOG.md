
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
- **Approval status:** PROPOSED (operational enablement needs explicit
  authorization + V2 review of the exact SHA).
- **Implementation status:** PARTIAL (contract + disabled backend
  preparation: `control.launch_supervised_transaction` refuses while
  disabled; no HTTP route, CLI subcommand, or Start wiring).
- **Target phase:** future (V2 enablement review first).
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
- **Evidence:** `tests/test_supervised_launch.py` (23 tests), 873/873 suite,
  `docs/SUPERVISED_LAUNCH_CONTRACT.md`.
- **Docs:** `docs/SUPERVISED_LAUNCH_CONTRACT.md`, `docs/ARCHITECTURE.md`,
  `docs/CURRENT_STATE.md`, `docs/DECISIONS.md`.
- **Open questions:** enablement authorization; exact V2 Start preflight UX.
- **Last update:** 2026-10-11.

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


## DASH-V2-62 reconciliation - 2026-10-11

F-LAUNCH-SUP-01 remains PROPOSED for enablement / PARTIAL overall. The five new implementation findings and two contract notes are corrected in disabled preparation; 29 new tests, 902/902 canonical and 52/52 targeted OK. Report: DASH_V2_62_SUPERVISED_LAUNCH_CORRECTIONS.md. Operational readiness, real watcher startup binding, enabled access and longevity remain unverified/deferred. F-P14A-01 historical windows unchanged; no new run or gate advancement. User-authorized direct backend correction replaces the V2-61 handoff for these findings; no need for the other agent to repeat them.
