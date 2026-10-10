# P1-14B.7 — Persistent Supervision & Enforced Abort Gates Audit

**Mode:** AUDIT → REPRODUCE → DESIGN → IMPLEMENT → TEST → VALIDATE → DOCUMENT → COMMIT → STOP
**Date:** 2026-10-10
**Branch:** `phase1/market-intelligence-dashboard`
**Starting SHA:** `d7859643e34997ddb0817cc63fededda3328543f`
**Safety:** `BOT_MODE=observe` end-to-end; 0 keys / 0 orders / 0 capital. V2 worktree/ports and `main` untouched.

---

## 1. Root cause (P1-14B.6 supervision loss)

Abort evaluation lived exclusively in the agent's live tool session: polling scripts run
foreground in the harness, so a harness timeout kills the watcher while the detached probe
keeps running. No in-band mechanism evaluated the rules after that point (the probe kept
logging evidence nobody read until post-mortem). The fix moves evaluation into a process that
shares the probe's lifecycle independence: a detached supervisor coordinated through the
canonical registry — the same survival pattern as control-started probes.

## 2. Architecture (integrated into the canonical controller — no second controller)

`control supervise` (new CLI: `--interval` 5–300 s, `--timeout` 60–86400 s optional) lives in
`control.py` alongside start/stop/status and shares the registry, identity model, and stop path:
- **Claim/lease:** watches ONE active canonical run; refuses on no-run, stale record, or a live
  fresh (<90 s) lease from another supervisor; stale/corrupt leases are taken over with the prior
  PID recorded. No start/restart path exists anywhere in the supervisor code (asserted by test).
- **Cycle:** terminal? → identity revalidated (mismatch = exit, no touch) → evidence snapshot
  (read-only tail of the run's evidence log + read-only DB probe) → pure decision → one-shot
  enforce → lease heartbeat (streaks persisted, so a restarted supervisor continues counting).
- **Enforce:** re-read + re-validate → STOPPING → canonical terminate → bounded 10 s wait →
  ABORTED + rule/reason/threshold/observed/at (+ `last_exit: aborted-<rule>`) only on confirmed
  death; stop-timeout → FAILED (honest, no ABORTED claim); already-dead → no-touch.
- **Failure budget:** 5 consecutive check failures → lease FAILED + exit (detectable); the probe is
  never touched on supervisor failure (explicit UNKNOWN policy — a blind watcher must not kill a
  healthy run; the in-probe freshness watchdog remains the backstop layer).
- **Process model:** ordinary detached process, no stdin/stdout needs, exits on run-terminal /
  timeout / failure-budget; registry lease goes stale → next supervisor takes over. Survives
  agent disconnects, closed terminals, and harness timeouts by construction (same detachment as
  probes; verified pattern, not re-proven here — the mechanism tests below are the evidence).

## 3. Abort rules (exact semantics; LOCAL_POLICY except the cumulative 5 % rejects rule)

| Rule | Fires when | Window/counting |
|---|---|---|
| safety-violation | mode ≠ observe, or apiKeysUsed/realOrdersSent > 0, or order path present | immediate, priority-first |
| timestamp-reject-rate | cumulative rejected/total of latest summary > 0.05 | official cumulative methodology |
| reconnect-storm | >5 error-reconnect events in trailing 600 s (log timestamps) | sliding, per-event |
| persistence-errors | ≥2 persistence_error events/10 min on 2 straight checks, or prospective DEGRADED ×2 | streaked |
| clock-skew | \|offset\| > 30000 ms on 3 straight checks (noisy single samples) | streaked |
| db-unreadable | operational DB unreadable 6 straight checks (lock transients) | streaked |
| watchdog-overwhelmed | forced ≥3 AND error ≥3 AND rising rejects | compound backstop-loss |

UNKNOWN policy: any missing/non-numeric input skips its rule (never silent zero); streaks count
consecutive PRIOR breaching checks. Freshness-absence as such reduces to these rules (stale →
rejected/reconnect/forced signals) — documented, no redundant rule. Thresholds LOCAL_POLICY
except rejects; changing any threshold needs evidence + docs (no arbitrary tuning).

## 4. Identity, races, failure handling (verified, not assumed)

- PID + python-image + creation-time on every touch (reused canonical model). Stale PID and
  PID-reuse (ctime mismatch) → exit with zero process interaction (tested).
- Enforce re-validates between evaluate and kill; bounded wait re-checks identity (matches
  canonical risk posture; mid-kill reuse is a stated residual, same as `stop`).
- One-shot: ABORTED terminal + second cycle no-op (tested, incl. no restart: watched PID stays
  dead, no start path exists).
- Supervisor restart: dead-PID lease → recorded takeover with continued streaks (tested).
- Two supervisors: live lease → refuse with reason (tested).
- V2/agent/direct launchers: supervised identically (launcher never overwritten — tested for
  agent/dashboard/direct); origin fields preserved.
- Natural end / no run / corrupt lease: clean exits, no-ops (tested).
- **wmic absent on this host class** (verified: `tasklist.exe` present, `wmic` gone): creation
  time previously always None here, degrading identity to image-only. Fixed with a ctypes
  `GetProcessTimes` fallback (real OpenProcess handle, explicit signatures, cleanup) — PID+ctime
  identity fully operational again (proven live: ISO `create_time` stamps in registries).

## 5. Dashboard/V2 contract (additive, no frontend changes)

`control.status()` (hence `GET /api/control/probe/status`) always carries a `supervisor` block:
state SUPERVISOR_ACTIVE / SUPERVISOR_FAILED / SUPERVISOR_UNKNOWN (never supervised), watched_pid,
run_id (evidence-log stem), last_check_at, abort_triggered, abort_reason/rule/threshold/observed,
supervision_source (`supervisor:control-supervise`). V2 mapping: SUPERVISOR_ACTIVE/UNKNOWN/FAILED
← lease state; ABORT_TRIGGERED ← terminal ABORTED; ABORT_REASON/LAST_CHECK_AT/RUN_ID/WATCHED_PID/
ABORT_THRESHOLD/OBSERVED_VALUE/SUPERVISION_SOURCE ← same-named keys. Process/feed/supervisor stay
three separate axes (Bot Control Center pattern preserved). Unknown states render via existing
opaque strings (no color-map to break; dashboard/control suites green).

## 6. Validation

- **Deterministic:** 34 supervisor tests (decision matrix incl. boundaries, UNKNOWN skips, priority,
  windows; lease claim/refuse/takeover/corrupt; stale/reuse no-touch; terminal/no-op; launcher
  preservation; failure budget; status contract keys; no-start-path assertion; prospective-store
  isolation assertion) — all green. Full suite **760/760 OK**, exit 0 (726 + 34).
- **Real-PID integration (controlled destructive):** breaching evidence (6 % rejects) against a
  REAL sleeper child in an isolated registry → supervisor killed exactly it, foreign sleeper
  survived, registry ABORTED + rule/threshold/observed/launcher preserved, second cycle no-op.
- **Brief live mechanism validation:** 150 s probe (PID 35236) + foreground supervisor (12 cycles):
  claimed, heartbeated to completion, exited clean on COMPLETED, zero false aborts; probe-side
  11/11, 0/0, reg=57, DB byte-identical (57/202). **Finding:** self-registration wiped the control
  plane's evidence path (`evidence: null`), blinding log-derived rules — fixed by preserving the
  same-PID evidence block in `try_register` (other-PID and direct-launch behavior unchanged),
  with 2 tests. No 35-min run (per task bounds).

## 7. Prospective preservation (v1.1 + v9 intact)

Supervisor imports no stores and writes no prospective state (asserted in-suite); operational DB
touched read-only (`SELECT 1` probes) or not at all. Post-validation audit: 57 setups, 202 outcomes,
all COMPLETE, 0 dupes, 0 anomalies. **All rows preserved byte-identical.**

## 8. Gates & verdict

CLOCK (implied PASS, offsets sub-second in validation) / PROSPECTIVE PASS (untouched, green) /
PERSISTENCE PASS (untouched, 0 errors) / SAFETY PASS (observe, 0/0/0, verified-PID discipline,
V2/main untouched). TRANSPORT/FRESHNESS not re-rated (no long run). **Global verdict: PASS**
(mechanism delivered + validated; the P1-14B.6 supervision gap is closed by architecture, not
by agent instructions).
**No 4–6 h run authorized. P1-14C not started.**

## 9. Remaining blockers & files

1. ≥30 min healthy window still undemonstrated (unchanged; next attempt runs WITH a supervisor).
2. Clock note if offset >5 s (unchanged).
3. Supervisor itself needs a supervised maiden voyage on a real run (brief validation covered
   mechanics; a full supervised window is the next evidence step, needs explicit instruction).
4. SUCCESS_GATES checkboxes unchanged (no gate advancement — stated correspondence).
- New: `tests/test_supervisor.py` (34), this report. Changed: `control.py` (supervisor engine +
  evidence preservation + status contract + CLI), `dashboard.py` (creation-time fallback only).
- Updated: CURRENT_STATE, TASK_QUEUE, FEATURE_BACKLOG (F-P14A-01), DECISIONS (append-only),
  ARCHITECTURE (supervisor row). Evidence (uncommitted, preserved): validation run log
  `logs/probe-runs/probe-20261010T122756Z.log`, `data/microprobe.db` (57/202). Temp scripts: none
  remain (all helpers inline-deleted after use).
