# P1-14B.8 — Supervised Maiden Voyage & Abort Enforcement Report

**Mode:** AUDIT → PREFLIGHT → SUPERVISOR VERIFICATION → CONTROLLED RUN → EVIDENCE AUDIT → DOCUMENT → COMMIT → STOP
**Date:** 2026-10-10
**Branch:** `phase1/market-intelligence-dashboard`
**Starting SHA:** `9150c743c74a4dceac6f107531c9dac3c91f3bda`
**Baseline validated pre-run (35-min window):** schema v9, 57 setups, 202 COMPLETE
outcomes, 0 dupes. (The brief validation run later started from 66/228 — baselines
distinguished explicitly per §7 corrections.)
**Safety:** `BOT_MODE=observe` end-to-end; 0 keys / 0 orders / 0 capital. V2 worktree/ports and `main` untouched.

---

## 1. Supervision without the agent (the §4 priority, demonstrated twice)

- **35-min window (earlier, post-hoc reconstructed):** probe PID 33292 ran 13:12:44 → 13:47:55Z
  (2102.147 s per final_summary, exit 0 duration-reached) while supervisor PID 25800 ran 70 cycles 13:13:35 →
  13:48:24Z and exited cleanly on no-active-run. Zero false aborts across 70 evaluations
  (post-hoc log audit: 0.00 % rejects, 0 reconnects — nothing to abort, correctly nothing done).
  68 kind=summary + one final_summary, 11→20 streams (HOT ERA/LUMIA/MAGIC), prospective reg 57→66 (+9 setups),
  writes 0→35, errors 0. The supervisor performed its entire mission with zero agent contact
  after launch — session-independence proven by execution, not by assertion. The concurrent
  sentinel did NOT protect this window (died pre-cycles — next bullet); three-layer protection
  was demonstrated in the brief run only.
- **Sentinel gap found honestly:** the concurrently launched sentinel (PID 39244) claimed its
  lease at 13:13:47Z and died within ~30 s with zero cycles, zero output, zero heartbeat. Root
  cause class: silent early death under output buffering (block-buffered stdout lost on kill) —
  exact killer unrecoverable post-hoc (harness timeout overlapped). Buffered output explains the
  missing diagnostics, NOT the death itself — `-u`/flush improve observability, they do not fix
  process lifetime. Lesson encoded: startup prints (flushed) in both mains + `-u` in detached
  launches + lease-presence launch verification as protocol (registry read ≤30 s after spawn).
- **Brief validation (this task, fully observed):** 150 s probe (PID 33300) + supervisor (PID 37176,
  14 cycles) + sentinel (PID 34452, 12 cycles), all launched detached with verified leases:
  both watchers claimed, heartbeated to natural COMPLETED, exited STOPPED cleanly, zero false
  aborts, zero orphans (no python processes remain). Probe-side 11/11, 0/0/0, reg=66 rehydrated,
  0 writes/errors; DB byte-identical (66/228/0 dupes). Sentinel mechanism now proven live
  (claim → heartbeat → clean exit), closing the §4.3/§8F gap at mechanism level.

## 2. What was built (P1-14B.7 implementation, validated here)

`control supervise` + `control sentinel` (canonical plane, no second controller): registry leases
(live→refuse, stale/corrupt→recorded takeover), documented abort rules with UNKNOWN-safe
semantics (safety immediate; rejects >5 % cumulative; >5 reconnects/600 s sliding; persistence
≥2/10 min ×2 checks or recorder DEGRADED; clock >30 s ×3; DB unreadable ×6; watchdog-overwhelm
compound; supervision-lost), streaks lease-persisted (restart-safe), one-shot verified-PID abort
with persisted rule/reason/threshold/observed, failure budgets (probe untouched on watcher
failure), terminal ABORTED, V2 additive `supervisor` + `sentinel` blocks in control status
(flowing to `/api/control/probe/status`; UI renders via existing opaque strings). Self-registration
preserves same-PID evidence paths (found during validation). PID+image+creation-time identity
throughout, with ctypes `GetProcessTimes` fallback (wmic absent on this host class — verified).

## 3. Tests — 775/775 OK, exit 0 (760 + 15 sentinel)

Deterministic, hermetic registries (MICROPROBE_RUNTIME_FILE): claim/refuse/takeover/corrupt,
cycle outcomes (ok/unsupervised/terminal/stale/no-op), failure budgets, status contract keys
(11 supervisor + 7 sentinel), no-start assertions, store-isolation assertion, ctypes fallback
shape, evidence preservation (2), REAL-PID abort integration (breach evidence → sleeper killed,
foreign sleeper alive, ABORTED + rule persisted, launcher preserved, second cycle no-op).
P1-12A/B, P1-13A, prospective rules untouched. Dashboard/control suites green with additive blocks.

## 4. Prospective preservation (v1.1 + v9 intact)

Post-run read-only audits (both runs): 66 setups, 228 outcomes, all COMPLETE, 0 duplicates,
0 anomalies (no-lookahead + return math on all rows). No PENDING/INSUFFICIENT (marks
healthy-or-absent). No state/column/contract change in this task. **All 202 prior rows preserved
byte-identical** (+26 honest new from the 35-min window).

## 5. Gates

| Gate | Result |
|---|---|
| CLOCK_GATE | PASS (offsets sub-second throughout; no resync) |
| TRANSPORT_GATE | PASS (35-min: 0 reconnects, 0.00 % rejects, 20/20; brief: 11/11, 0/0) |
| FRESHNESS_GATE | PASS (feeds fresh-or-absent honestly; no stale-mark occasion) |
| SUPERVISION_GATE | PASS (70-cycle + 14-cycle + 12-cycle supervised windows, heartbeats verified, zero false aborts, clean exits, no orphans) |
| PERSISTENCE_GATE | PASS (integrity ok, 0 errors, coexistence to 66 keys, bounded logs held) |
| SAFETY_GATE | PASS (observe end-to-end, 0/0/0, verified-PID discipline, V2/main untouched) |

**Global verdict: PASS.** Agent-independence demonstrated in execution (35-min unsupervised window
+ verified brief three-layer run); abort enforcement proven on a real process; no-orphan discipline
kept. Qualified: the 35-min window ran WITHOUT sentinel protection (supervisor-only); uninterrupted
three-layer protection is demonstrated by the brief run. The residual P1-14B.6 note stands: one supervised 35-min window does not extinguish an
intermittent fault — but supervision of whatever comes next no longer depends on any session.
**No 4–6 h run authorized. P1-14C not started.**

## 6. Remaining blockers & files

1. ≥30 min healthy window: DEMONSTRATED twice with supervision (P1-14B.5 + this task's 35-min
   window) — recurrence risk only.
2. Supervised full-window abort (real breach under supervision) unobserved — by luck of health,
   not by gap; mechanism proven on synthetic breach + brief runs.
3. Clock note if offset >5 s (unchanged). SUCCESS_GATES checkboxes unchanged (no gate advancement).
- New: `tests/test_sentinel.py` (15), this report. Changed: `control.py` (sentinel engine, status
  blocks, CLI branches, evidence preservation, startup prints).
  (`dashboard.py` creation-time fallback belongs to P1-14B.7/9150c74, not this commit — listed
  here by error in v1, corrected.)
- Updated: CURRENT_STATE, TASK_QUEUE, FEATURE_BACKLOG (F-P14A-01), DECISIONS (append-only),
  ARCHITECTURE (supervisor + sentinel rows).
- Evidence (uncommitted, preserved): `logs/probe-runs/probe-20261010T131243Z.log` (35 min),
  `logs/probe-runs/probe-20261010T140206Z.log` (150 s), supervisor/sentinel stdout logs,
  `data/microprobe.db` (66/228). Temp scripts deleted. No logs/DB committed; no secrets anywhere.

---

## 7. Corrections log (post-review fixes; history above preserved as written)

1. Duration: final `final_summary` reports `runtimeSeconds` 2102.147 (not 2102.5 — a P1-14B.5
   number that contaminated drafts; P1-14B.5 sections keep their own correct 2102.5).
2. Log census: 68 `kind=summary` + one `final_summary` (not "69 summaries + final").
3. Baselines: 35-min preflight was 57 setups / 202 outcomes; 66/228 was the brief run's
   preflight (= 35-min post-state) and end-state (unchanged by the brief run).
4. `dashboard.py` was NOT modified in this task's scope (creation-time fallback is P1-14B.7).
5. Buffered output explains missing sentinel diagnostics, not the watcher's death cause
   (still unknown); `-u`/flush are observability, not lifetime fixes.
6. Global PASS is qualified: the long window ran supervisor-only; three-layer protection
   holds for the brief run. V2 launch stays blocked (start_probe launches no watchers;
   transactional supervised launch with lease verification + rollback is documented pending
   work, not presented as resolved).
