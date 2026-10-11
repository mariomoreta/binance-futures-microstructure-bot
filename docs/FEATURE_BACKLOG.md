# FEATURE BACKLOG — canonical decision traceability & deferred features

> Current reconciliation: DASH-V2-53 (2026-10-11). Original inventories/statuses below are dated historical checkpoints; consult the dated reconciliation section and MOVER_LEVEL_STRATEGY_RESEARCH.md before interpreting implementation status. Backend 55efaa2 and the V2 snapshot are separate source trees.

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
| F-STATE-V2-TK-01 | V2 Token Detail: state explanation panel | DECIDED | PARTIAL (DEMO UI only; no BFF) | DASH-V2-03/05 |
| F-STATE-V2-TL-01 | State timeline visualization | PROPOSED | NOT IMPLEMENTED | Later |
| F-UNI-01 | Dynamic LIVE-universe expansion (P1-12B) | DECIDED | VERIFIED | P1-12B DONE |
| F-OPP-01 | Research-based opportunity engine (P1-13A) | DECIDED | NOT IMPLEMENTED | P1-13A |
| F-OPP-UI-01 | Opportunities dashboard (P1-13B) | DECIDED | PARTIAL (DEMO UI only; no BFF) | DASH-V2-04/05 |
| F-BT-01 | Historical backtesting (P1-14) | DECIDED | NOT IMPLEMENTED | P1-14 |
| F-PAPER-01 | Forward paper validation (P1-15) | DECIDED | NOT IMPLEMENTED | P1-15 |
| F-PORT-01 | Paper portfolio (P1-16) | DECIDED | NOT IMPLEMENTED | P1-16 |
| F-V2-BFF-01 | Next.js API integration (BFF) | DECIDED | PARTIAL (runtime routes; full contract integration unverified) | DASH-V2-47 scoped audit |
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
  PARTIAL — DEMO-only state explanation, UNKNOWN until verified BFF data.
- **Target phase:** DASH-V2-03/05; live-data integration remains deferred.
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
  NOT IMPLEMENTED.
- **Target phase:** P1-13A (after P1-12B).
- **Dependencies:** F-UNI-01, classifier history, P1-11C event outcomes.
- **Affected subsystems:** new engine module, persistence (new tables),
  probe evaluation hook.
- **Required UI locations:** none yet (engine first; UI is F-OPP-UI-01).
- **Data/API requirements:** state history + event-study outcomes +
  BTC context.
- **Acceptance criteria:** candidates explainable; direction/entry/stop/
  targets nullable until validated; no fabricated confidence.
- **Evidence needed:** unit tests + research review (no live orders ever).
- **Docs:** `docs/SIGNAL_RESEARCH_PLAN.md`, `docs/ROADMAP.md`.
- **Open questions:** candidate scoring methodology (research output).
- **Last update:** 2026-10-08.

## F-OPP-UI-01 — Opportunities dashboard (P1-13B)

- **Product objective:** present F-OPP-01 candidates (Python `/signals`,
  `/extreme-moves` per ROADMAP; V2 Opportunities per design spec) with
  empty/blocked shells until candidates exist.
- **Origin / decision date:** `docs/ROADMAP.md`; V2 Opportunities section
  `docs/DASHBOARD_V2_DESIGN_SPEC.md` (empty-shell-first rule).
- **Approval status:** DECIDED (sequenced/designed).
- **Implementation status:** PARTIAL (V2 DEMO screener with filters and inspector; no real-data BFF).
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
  PARTIAL (runtime routes exist; full versioned integration unverified).
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
- **Last update:** 2026-10-08.

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

## DASH-V2-47 scoped BFF evidence update (2026-10-10)

F-V2-BFF-01 is PARTIAL: runtime/readiness handlers exist in this branch.
Unavailable/unknown controller evidence now stays UNKNOWN; start remains
blocked. Evidence: 18 new regression cases, 84/84 full frontend tests,
type/lint/build and unavailable-backend production HTTP smoke.
This does not verify all API schemas, live data, mutation security, Windows
runtime or atomic launch. Older static-only entries remain historical.
See docs/DASHBOARD_V2_47_READINESS_AUDIT.md.

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

### DASH-V2-07 UI evidence addendum (2026-10-08)

- F-OPP-UI-01 remains **PARTIAL (DEMO UI only; no BFF)**. Opportunities now distinguishes lifecycle/direction visually and explicitly identifies fixture provenance, all stale records and zero validated outcomes. Evidence: `frontend/src/test/opportunities.test.tsx` (8 tests), 37/37 frontend suite, `design/qa/v2-07/` screenshots, and `docs/DASHBOARD_V2_PROGRESS.md`.
- F-V2-BFF-01 remains **NOT IMPLEMENTED**. F-STATE-V2-TK-01 remains **PARTIAL**. No live API, outcome validation, or trading capability was introduced.
- Image parity remains **ASSET_MISMATCH** for Opportunities until the correct approved PNG is installed and audited.

### DASH-V2-08 evidence update (2026-10-08)

F-STATE-V2-TK-01 remains PARTIAL (DEMO UI only). Added explicit historical fixture as-of, no-observation fallback and classifier-not-connected state. Evidence: 39/39 frontend tests and `design/qa/v2-08/` browser captures. F-OPP-UI-01 remains PARTIAL; F-V2-BFF-01 remains NOT IMPLEMENTED. Corrected target assets have not yet been installed in the Windows worktree; image parity is not verified.

### DASH-V2-09 evidence update (2026-10-08)

F-STATE-V2-TK-01 remains **PARTIAL (DEMO UI only)**. Observation audit card now displays UNKNOWN previous state and last authoritative evaluation in a fourth desktop evidence panel, rather than implying verified classifier history. Evidence: 40/40 frontend tests, `design/qa/v2-09/` four Chrome captures, and `docs/DASHBOARD_V2_PROGRESS.md`. F-OPP-UI-01 remains PARTIAL; F-V2-BFF-01 NOT IMPLEMENTED. Visual reference correction and GitHub publication are not verified.



## F-V2-SYSTEM-01 — System composition and integration (2026-10-10)

PARTIAL: compact process/feed/supervisor/mode cards, inspectable controls,
transport/readiness panels and separate recorded evidence. Five pipeline/
resource/event contracts pending. Desktop/mobile Chrome, disclosure/Refresh,
fallback and foreign ownership verified; frontend 86/86 and V2 Python snapshot
496/496 PASS on Windows. Full reference/data parity and atomic start NOT VERIFIED.
Evidence: DASHBOARD_V2_48_SYSTEM_VISUAL_AUDIT.md and design/qa/v2-48/.


## 2026-10-10 — P1-14B.8 integration review

Backend babf3ac verified in GitHub; sentinel 15/15 targeted tests rerun, SQLite
66/228 quick_check OK. Long supervisor 70 cycles; three-layer evidence only
brief 14/12 cycles (long sentinel died). Reproduced STOPPED-fresh accepted,
malformed-established heartbeat unprotected, stale sentinel published ACTIVE.
Concurrent registry writes/lease fencing need tests. V2 drops sentinel and
start_probe does not launch watchers: F-V2-BFF-01 remains PARTIAL, start blocked.
Owner feedback and documentation discrepancies: DASHBOARD_V2_P1_14B_8_REVIEW.md.
No new run, backend edit, gate advancement or long-run authorization.


## F-V2-VISUAL-01 — authorized all-screen visual cycle (DASH-V2-49)

Approval: user authorized 2026-10-10. IMPLEMENTED and VERIFIED within bounded
frontend scope: shared frame, responsive/semantic recovery, unavailable views,
future empty compositions and reference identity correction. 13 routes x 3
widths PASS; frontend 90/90 and V2 Python snapshot 496/496. Full pixel/data parity
PARTIAL; correct Opportunities target MISSING. No engine is implemented by
rendering its workspace. F-PAPER-01 and backtest validation stay NOT IMPLEMENTED;
F-V2-BFF-01 and F-V2-SYSTEM-01 stay PARTIAL. Read-only integration resumes at
reviewed backend SHA; Start blocked pending transactional supervised launch.
Evidence: DASHBOARD_V2_49_VISUAL_VALIDATION.md; roadmap and design/qa/v2-49/.


## 2026-10-11 - DASH-V2-50 corrections review and watcher integration
Backend 8648366 exact SHA reviewed; 34/34 contract+sentinel tests PASS.
Freshness/identity/binding predicates accepted. Enforcement fencing NOT accepted:
enforce_abort still writes STOPPING unlocked and calls termination before owner
verification. Synthetic mocked-kill reproductions prove foreign-owner invocation
and terminal/new-lease overwrite; committed heartbeat race test is a no-op.
Full evidence and owner follow-up: DASHBOARD_V2_50_CORRECTIONS_REVIEW.md.

V2 BFF now preserves sentinel and raw evidence for both watchers. System exposes
five independent process/feed/supervisor/sentinel/mode cards and lease details.
Client expires ACTIVE at 90s, rejects invalid/future/mismatched evidence and
clears cached evidence on fetch error. This is observation, not protection proof.
116/116 frontend, type/lint/build PASS; V2 Python snapshot 496/496 PASS.
System+Overview at 1672/1366/390: 6 browser cases PASS, no errors/overflow; expanded
watcher panels and production DTOs captured. Reference fidelity remains PARTIAL.
Start/transactional launch blocked; no market run, backend edit or gate advance.
F-V2-BFF-01 and F-V2-SYSTEM-01 remain PARTIAL. Runtime source shows COMPLETED;
both leases STOPPED, displayed STALE; feed UNKNOWN, recorded evidence separate.


## 2026-10-11 - DASH-V2-51 operation boundary and pure observation
Backend 0786617 exact SHA reviewed; 48/48 targeted regressions PASS.
Locked STOPPING acquisition, final marks, actual abort owner and genuine
thread heartbeat writes accepted. Remaining operation-boundary findings:
post-claim takeover reaches simulated termination; wrong-run owned lease
reaches termination; status() can overwrite ABORTED with stale FAILED.
Independent process-owner concurrency coverage remains absent.

V2 no longer calls mutating status() for GET observation or command preflight.
Requires canonical status_readonly(); missing capability returns explicit
READ_ONLY_STATUS_REQUIRED/UNKNOWN and pauses controls. The source currently
lacks it. Recorded SQLite evidence remains available; Start still blocked.
118/118 frontend/type/lint/build and V2 Python snapshot 496/496 PASS.
Bridge execution against a synthetic active registry preserved its bytes;
canonical registry SHA-256 unchanged. No market run or backend edit.
Full audit/owner follow-up: DASHBOARD_V2_51_FENCING_REVIEW.md.
F-V2-BFF-01 and F-V2-SYSTEM-01 remain PARTIAL; safety gates unchanged.


## 2026-10-11 - DASH-V2-52 pure observation and native boundary review
Backend exact SHA 55efaa2 reviewed; canonical suite independently 826/826 PASS.
V2 bridge status_readonly verified byte-preserving; runtime observation resumes.
Recorded COMPLETED / watcher STALE / feed UNKNOWN are independent observations.
Registry state is not verified target liveness: V2 labels it Recorded process,
uses Elapsed since start, and describes readiness as a registry check.
Two remaining reproductions: native TerminateProcess FALSE accepted as True,
missing native HANDLE signatures; start kills its own child if registration wins
before parent commit. Both are hermetic, without probes or actual OS termination.
Native/start corrections remain owned by backend; full detail and follow-up in
DASHBOARD_V2_52_INTEGRATION_REVIEW.md. Start and operational gates remain blocked.
Frontend 118/118, V2 Python snapshot 496/496; type/build PASS. System/Overview at
1672/1366/390: 6 cases, no browser errors/page overflow. Visual parity PARTIAL.
F-V2-BFF-01 and F-V2-SYSTEM-01 remain PARTIAL. No new supervised run or gate advance.


## DASH-V2-53 research proposals — 2026-10-11

This dated checkpoint supersedes design-era implementation assumptions only where explicitly identified. Backend 55efaa2 implements research opportunities and prospective endpoint persistence; the old F-OPP-01 / F-BT-01 snapshot above is historical, not a current backend absence claim. This does not import that code into V2 or verify a complete costed strategy backtest. Prior VERIFIED evidence remains scoped to its original checkpoint.

The user authorized preservation and evaluation of the strategy discussion. The implementation definitions and unresolved parameters below remain PROPOSED / NOT IMPLEMENTED; recording them does not approve execution, paper, market runs or SUCCESS_GATES advancement. Existing F-CMC-01, F-BT-01 and F-PAPER-01 are dependencies, not duplicated features. Specification: [MOVER_LEVEL_STRATEGY_RESEARCH.md](MOVER_LEVEL_STRATEGY_RESEARCH.md).

### F-RES-MOVERS-01 — As-of movers and verified market-cap cohorts

- Approval: PROPOSED.
- Implementation: NOT IMPLEMENTED for the proposed strategy requirement.
- Owner/dependencies: Research/backend; depends on F-CMC-01 and token identity.
- Scope/acceptance: Preserve first-selection times, rolling-return units, contract multipliers and historical eligibility. Unknown cap stays UNKNOWN; low price never implies small cap. Acceptance: as-of mapping/cohort fixtures, delisted-data limitations and eligible/rejected denominators.
- Evidence: DASH-V2-53 source audit and documentation only; no implementation or strategy performance evidence.

### F-RES-LEVELS-01 — Frozen level and activation definitions

- Approval: PROPOSED.
- Implementation: NOT IMPLEMENTED for the proposed strategy requirement.
- Owner/dependencies: Research/backend; depends on F-RES-MOVERS-01.
- Scope/acceptance: Preregister H-A1 breakout/retest and H-B1 confirmed reversal. Freeze level basis, timeframe, formation/availability, activation, expiry and invalidation. Acceptance: no-lookahead fixtures including delayed pivots; unchanged classifier rules; observed direction separated from proposed side.
- Evidence: DASH-V2-53 source audit and documentation only; no implementation or strategy performance evidence.

### F-RES-PATH-01 — Complete decision snapshots and path adequacy

- Approval: PROPOSED.
- Implementation: NOT IMPLEMENTED for the proposed strategy requirement.
- Owner/dependencies: Research/backend; depends on F-RES-LEVELS-01 and existing prospective contract.
- Scope/acceptance: Document existing endpoint-only outcomes; propose separately versioned snapshot/path extensions without silently changing v1.1. Acceptance: declared sampling/coverage, actual late times, MFE/MAE fidelity, censored/missing/ambiguous labels and full feature/context provenance.
- Evidence: DASH-V2-53 source audit and documentation only; no implementation or strategy performance evidence.

### F-RES-CONTEXT-01 — Participation, absorption and market-context studies

- Approval: PROPOSED.
- Implementation: NOT IMPLEMENTED for the proposed strategy requirement.
- Owner/dependencies: Research/backend; depends on F-RES-PATH-01.
- Scope/acceptance: Compare flow plus price response, OI quantity/value, distinct funding events, bounded depth and aligned BTC context. Acceptance: group ablations against simple baselines out of sample; correlated indicators never count as independent confirmations; unsupported beta/causal claims remain unvalidated.
- Evidence: DASH-V2-53 source audit and documentation only; no implementation or strategy performance evidence.

### F-RES-CATALYST-01 — Optional official catalyst ledger

- Approval: PROPOSED.
- Implementation: NOT IMPLEMENTED for the proposed strategy requirement.
- Owner/dependencies: Research/backend; depends on F-RES-MOVERS-01; optional, not feed-critical.
- Scope/acceptance: Record stable asset identity, official source, announcement/first-seen/effective times and event type. Acceptance: information unavailable at decision time excluded, retrospective attribution flagged, provider outages never block existing market feeds.
- Evidence: DASH-V2-53 source audit and documentation only; no implementation or strategy performance evidence.

### F-RES-VALIDATION-01 — Costed H-A1/H-B1 strategy comparison

- Approval: PROPOSED.
- Implementation: NOT IMPLEMENTED for the proposed strategy requirement.
- Owner/dependencies: Research/backend; depends on F-RES-MOVERS-01, F-RES-LEVELS-01, F-RES-PATH-01 and F-BT-01; F-RES-CONTEXT-01 supplies optional evidence groups.
- Scope/acceptance: Freeze definitions, parameter budget and precision/rejection criteria before experiments. Acceptance: chronological grouped evaluation, overlap purge including late windows, fill/no-fill/latency/fees/funding/impact, 1x/2x/3x cost stress, net expectancy and uncertainty. Win rate below 50% alone is not rejection. No run authorization.
- Evidence: DASH-V2-53 source audit and documentation only; no implementation or strategy performance evidence.

### F-V2-RESEARCH-01 — Truthful mover/level research presentation

- Approval: PROPOSED.
- Implementation: NOT IMPLEMENTED for the proposed strategy requirement.
- Owner/dependencies: V2/frontend; depends on canonical read-only contracts and F-RES-LEVELS-01/F-RES-PATH-01.
- Scope/acceptance: Show provenance, observed direction, frozen levels, evidence for/against, missing coverage and endpoint/path distinction. Future proposed side/entry/stop/target/cost fields stay null or unavailable until canonical data exists. Acceptance: contract tests and visual review, no frontend-generated trading decision, no Start activation.
- Evidence: DASH-V2-53 source audit and documentation only; no implementation or strategy performance evidence.


## DASH-V2-54 review checkpoint - 2026-10-11
F-V2-BFF-01 and F-V2-SYSTEM-01 remain PARTIAL. Published backend b801ab0 passes 840 tests and current pure bridge preserves five synthetic registry cases. R1 exact Win32 BOOL width and R2 absent child-first log association are open backend correction dependencies, not completed V2 capabilities. Transactional supervised launch and new longevity evidence remain deferred. Research proposals registered in DASH-V2-53 are unchanged. Evidence: DASHBOARD_V2_54_BACKEND_CORRECTIONS_REVIEW.md, scripts/review-p1-14b8-v2-54.py and design/qa/v2-54/backend-reproductions.json.


## DASH-V2-55 acceptance checkpoint - 2026-10-11
F-V2-BFF-01/F-V2-SYSTEM-01 remain PARTIAL. R1/R2 backend dependencies from V2-54 are closed within reviewed deterministic Windows scope on e317569. Current pure bridge is compatible in five temporary cases; native/start handoff cases independently reproduced. Transactional launch, OS-liveness evidence, longevity and visual parity remain deferred. Research proposals from V2-53 unchanged. Evidence: DASHBOARD_V2_55_CORRECTIONS_ACCEPTANCE.md, scripts/review-p1-14b8-v2-55.py and design/qa/v2-55/backend-reproductions.json.


## DASH-V2-56 visual checkpoint - 2026-10-11
Existing Overview/Movers presentation and BFF capabilities remain PARTIAL. Bounded layout refinement verified with frontend suite/build and before/after browser cases; no live contract completion or full-reference PASS inferred. F-V2-BFF-01/F-V2-SYSTEM-01 remain PARTIAL; transaction preparation prompt recorded separately, Start disabled. F-V2-RESEARCH-01 remains PROPOSED / NOT IMPLEMENTED. Evidence: DASHBOARD_V2_56_VISUAL_REFINEMENT.md, scripts/qa-dashboard-visual.mjs and design/qa/v2-56/.


## DASH-V2-57 visual workflow checkpoint - 2026-10-11
Autonomous visual round control documented in DASHBOARD_V2_VISUAL_ROADMAP.md.
This verifies workflow documentation only; existing presentation/BFF capabilities
remain PARTIAL and research proposals remain PROPOSED / NOT IMPLEMENTED.
Next Token Detail implementation READY, overall fidelity not yet completed.
No API, engine or operational capability added; SUCCESS_GATES unchanged.

## DASH-V2-58 - 2026-10-11 - Token Detail visual round

Token Detail category/status/evidence/metric hierarchy and mobile composition refined. ROUND DONE; fidelity PARTIAL. Frontend 118/118, type/build pass, lint 0 errors (1 existing warning), Python snapshot 496/496; fresh 3 before / 6 after browser cases, no exceptions/overflow, expected price-series unavailable. Production V2 route http://127.0.0.1:3020/symbol/BTCUSDT. See [visual round report](DASHBOARD_V2_58_TOKEN_DETAIL_VISUAL.md). Next Opportunities composition READY; missing exact reference remains isolated. No backend change, Start or gate advance.

## DASH-V2-59 - 2026-10-11 - Research workspace visual round

Research navigation/headings/notices and mobile summary grids refined; literal rendered backslash-n removed. Bounded round DONE; reference fidelity ASSET_MISMATCH (missing dedicated asset). Frontend 118/118, type/build pass, Python snapshot 496/496; 9 before / 9 after browser cases, no exceptions/overflow. Source-unavailable observations retain honest empty state. See [research visual report](DASHBOARD_V2_59_RESEARCH_VISUAL.md). Next C/D scopes ready. Start/gates/backend unchanged.

## DASH-V2-60 - 2026-10-11 - bounded visual cycle checkpoint

Token Detail (V58), research workspace (V59), System/archives/future workspace refinements and final consistency (V60) are DONE within bounded visual scope; exact reference parity remains PARTIAL. All 13 routes / 3 widths = 39 browser cases pass, source-unavailable responses preserved; keyboard table checks pass. Frontend 118/118, types/build pass, Python V2 snapshot 496/496; lint 0 errors / 1 existing warning. Production http://127.0.0.1:3020, managed PID 34380. See [final screen matrix and evidence](DASHBOARD_V2_60_CONSISTENCY_REVIEW.md). Opportunities reference missing; contracts/engines and finer frame fidelity remain separate. Await other owner's published report for exact-SHA integration review. No backend change, Start, probe, trading or SUCCESS_GATES advancement.
