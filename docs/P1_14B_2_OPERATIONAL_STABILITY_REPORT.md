# P1-14B.2 — Prospective Operational Stability Gate Report

**Mode:** AUDIT → PREFLIGHT → CONTROLLED OBSERVATION → VERIFY → DOCUMENT → COMMIT → STOP
**Date:** 2026-10-09
**Branch:** `phase1/market-intelligence-dashboard`
**Starting SHA:** `d79cfd9a5baa5b8bbfaaa062542b9b0f96a421fa`
**Baseline validated pre-run:** schema v9, 7 setups, 28 COMPLETE outcomes, 0 dupes (identical to published P1-14B.1 evidence).
**Safety:** `BOT_MODE=observe` end-to-end; 0 keys / 0 orders / 0 capital. No execution paths touched.
Dashboard V2 worktree and ports untouched. `main` untouched.

---

## 1. Preflight — PASS (all items)

| Check | Result |
|---|---|
| Python processes | 0 running |
| Port 8091 | free |
| Control registry | COMPLETED prior run (exit 0, duration-reached, observe) — no active run |
| SQLite `PRAGMA integrity_check` | ok (5.4 s) |
| Disk free | 163.6 GB (abort floor: 10 GB) |
| BOT_MODE | observe (forced by canonical control plane) |
| Concurrent changes | none (tree clean at `d79cfd9`) |
| Evidence preserved | `.firecrawl/`, scripts, logs, DB all present |

## 2. Clock audit — PASS (no resync; decision recorded)

- Host UTC at audit: 2026-10-09T01:53:33.
- `w32tm`: Leap Indicator 3 (not synchronized), stratum 0, last sync 2026-10-08 18:35 local,
  source time.windows.com, dispersion 9.02 s — unchanged vs P1-14B.1 (stable, no drift event).
- Binance contrast (single public `/fapi/v1/time`): host − server = **+517 ms** at 1567 ms RTT
  (one-way delay contaminates; true offset within ±800 ms worst case).
- Engine tolerance: 60 s freshness gate; prospective uses self-consistent `as_of_ms`.
  Margin >70×. In-run syncs: 3/3 ok (−350/−372/−384 ms, RTT ~330–348 ms).
- **Resync decision: NOT performed.** Offset sub-second and stable; a step correction would risk
  a maturity-firing discontinuity for zero benefit at this scale. Revisit only if offset >5 s,
  and only BEFORE (never during) a run.

## 3. Controlled observation — ABORTED per rule at 23.4 min (window INSUFFICIENT)

- **RUN_ID:** `probe-20261009T015411Z` · PID 32532 · canonical plane (`control start --duration 2100
  --preset standard`, launcher `agent`) · mode observe.
- **Start:** 2026-10-09T01:54:12Z. **Controlled stop:** 02:17:27Z (`control stop`, verified PID only).
- **Actual duration:** 1401.7 s (23.36 min) of 2100 s requested. Exit code 0, registry STOPPED
  (`stopped-by-agent`). UTF-8 merged log: `logs/probe-runs/probe-20261009T015411Z.log` (new file,
  nothing truncated or overwritten).
- **Abort trigger (§6 rule "reject rate > 5 %"):** cumulative reject rate crossed **5.15 %**
  at rt≈1334 (52,490/1,019,182); marginal episode rate ≈100 % since rt≈983 (Δmsgs == Δrej ==
  51,044 — every new message arriving >5 s stale), 3 market reconnects, markPrice array + 3 HOT
  depth streams stale, cadenced throughput collapsed ~7×. Reconnect count (3/10 min) stayed below
  its own >5 rule; clock syncs held; persistence errors 0; disk fine; safety clean — the single
  breached rule forced the stop. No second long run started.

### Supervision timeline (all polls read-only; abort flags evaluated each poll)

| Poll (UTC) | rt (s) | streams | reconnects | rejects (rate) | prospective reg/writes/err | DB setups/outcomes | Note |
|---|---|---|---|---|---|---|---|
| 01:55:16 | 34 | 11/11 | 0/0 | 0 (0 %) | 7 / 0 / 0 | 7 / 28 | pristine; rehydration live |
| 02:00:22 | 367 | 11/11 | 0/0 | 0 (0 %) | 12 / 10 / 0 | 12 / 33 | 5 new setups, first new outcomes |
| 02:05:29 | 671 | 20/20 | 0/0 | 0 (0 %) | 13 / 17 / 0 | 13 / 39 | HOT promotions (JCT/OGN/RLC); 2nd clock sync ok |
| 02:10:57 | 984 | 20/20 | 0/0 | 1,446 (0.15 %) | 23 / 35 / 0 | 24 / 48 | mild bookTicker lag episode; rate ≪ 5 % → continue, heightened watch |
| 02:16:31 | 1334 | 20/20 | 3/0 (market) | 52,490 (5.15 %) | 24 / 56 / 0 | 24 / 67 | degradation episode → ABORT via `control stop` |

- Pristine window: rt 0–946 (~15.8 min, 0 rejects, 0 reconnects). Episode onset rt≈983.
- Depth gaps stayed 1/1/1 CORE (early, recovered). ForceOrder silence ≤57 s (event-driven, correct).
- Prospective layer never errored (errors=0, drops=0 every poll) and kept observing through the
  episode with lagged-but-honest marks (no lookahead possible; lag visible in telemetry).

## 4. Post-run prospective audit (read-only; no rows written, modified, or counted twice)

- Schema v9. Setups: **24 unique** (7 pre-existing + 17 new this run, incl. HOT symbols and first
  EXHAUSTION_WATCH / MOMENTUM_CONTINUATION families). Outcomes: **68, all COMPLETE**.
- New this run: 17 setups + 40 outcomes (68 − 28 baseline). Prior 28 rows untouched (no re-emission:
  unique (key,horizon) = 68, dupes = 0 — restart idempotency holds live across the fresh process).
- Cross-key coexistence at 24-key scale (Defect C fix proven in production load).
- No-lookahead PASS on all rows (`obs ≥ det + horizon`); return math exact to 6 dp; prices positive.
- Coverage: **68/68 matured cells COMPLETE (100 %)**; 52 cells unmatured (recent detections + all 4h) —
  absent honestly, never fabricated. Max observation lateness 6732.6 s (rehydrated old setups;
  recorded, not backdated). Zero PENDING/INSUFFICIENT rows.
- DB file size unchanged (238,927,872 B → +0.0 MB; page reuse under retention caps). Disk free 163.5 GB.
- CPU/memory per-process NOT captured (probe has no resource telemetry — stated, not inferred);
  process stable throughout, clean controlled stop. Startup RSS was 63.7 MB.
- No profitability statistics computed (evidence insufficient by rule; single-digit samples per family).

## 5. Tests

`python run_tests.py` → **609/609 OK**, exit 0 (matches P1-14B.1 reference). No new tests added:
no confirmed defect or reproducible gap emerged — the episode is environmental transport
degradation, already covered by existing telemetry/gating tests. P1-12A/B, P1-13A untouched.

## 6. Gate decisions

| Gate | Result | Basis |
|---|---|---|
| CLOCK_GATE | PASS | +517 ms worst case ≪ 60 s tolerance; 3/3 syncs ok; stable; no-resync decision recorded |
| TRANSPORT_GATE | PARTIAL | 15.8 min pristine, then P1-01-grade market-endpoint episode (100 % marginal reject rate, 3 reconnects, markPrice stale); engine behavior correct throughout (counted, labeled, uncorrupted) |
| PERSISTENCE_GATE | PASS | integrity ok; 0 errors; bounded logs held; 24-key coexistence; file size stable |
| PROSPECTIVE_GATE | PASS | rehydration + per-cycle observe live; 40 new outcomes; 100 % matured-cell coverage; 0 dupes; no fabrication |
| RESOURCE_GATE | PASS (with note) | disk 163.5 GB; DB +0.0 MB; CPU/mem per-process not captured; no pressure observed |
| SAFETY_GATE | PASS | observe end-to-end; 0/0/0; canonical plane only; verified-PID stop; V2/main untouched |

**Global verdict: PARTIAL.** The 35-minute duration objective was NOT met (23.4 min < 30 min minimum
per §6 → window INSUFFICIENT, cannot PASS). Transport is the limiting gate. All prospective,
persistence, clock, resource, and safety objectives met. **No 4–6 h run authorized.**

## 7. Files & traceability

- New: this report. Updated: `CURRENT_STATE.md` (P1-14B.2 section), `TASK_QUEUE.md` (NEXT_TASKS +
  LAST_VERIFICATION), `FEATURE_BACKLOG.md` (F-P14A-01), `DECISIONS.md` (append-only),
  `docs/P1_14B_1_TIME_INTEGRITY_AUDIT.md` (pointer addendum below).
- Evidence (uncommitted, preserved): `logs/probe-runs/probe-20261009T015411Z.log` (UTF-8, new file),
  `data/microprobe.db` (24 setups / 68 outcomes), prior pilot logs untouched. Temp supervision
  scripts deleted. No code or test changes in this task (none owed — no confirmed defect).
- V2 coordination: no changes, no new endpoints; `/api/prospective` contract unchanged
  (`setup_count: 24`, `outcome_count: 68` current data).

## 8. Remaining blockers (unchanged + one new)

1. A ≥30 min healthy-transport window is still undemonstrated (this run: 15.8 min pristine, then episode).
2. Pre-run clock resync note still owed if offset ever exceeds 5 s (currently sub-second; no action).
3. NEW: market-endpoint delivery path flaked mid-run (lag + reconnects + markPrice staleness) — next
   attempt should require a clean 10-min pre-window before committing to 35 min, and treat any
   markPrice staleness >120 s as an early-warning (not yet abort) flag.
