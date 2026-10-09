# P1-14B.4 — Prospective Freshness & PENDING Lifecycle Integrity Audit

**Mode:** AUDIT → REPRODUCE → DESIGN → FIX → TEST → VALIDATE → DOCUMENT → COMMIT → STOP
**Date:** 2026-10-09
**Branch:** `phase1/market-intelligence-dashboard`
**Starting SHA:** `d4a8fe2aa40db88c2b0a4fcb15be409d40964030`
**Safety:** `BOT_MODE=observe` end-to-end; 0 keys / 0 orders / 0 capital. V2 worktree/ports and `main` untouched.

---

## 1. UNKNOWN freshness — root cause: fail-open default, production unaffected

End-to-end audit (quote timestamp → `sample_age_ms` → probe → `observe()` → persistence → dashboard):

- `returns.feature()` sets `current_price` and `sample_age_ms = as_of − latest[0]` atomically;
  mark present ⟹ age present, finite, ≥ 0 (buckets are always ≤ as_of). `source_timestamp_ms`
  (the real quote time) exists in every row.
- `probe.py` passes `sample_age_ms` through (malformed → None guard); the call-site mark-None
  guard means `observe()` is never called mark-less from production.
- Dashboard never calls `observe()` (read-only `status()`/`outcomes()`); the only other
  `.observe(` hits are unrelated engines (detectors) or tests.
- **Conclusion:** via the probe, UNKNOWN age with a present mark is IMPOSSIBLE. The fail-open
  `None → COMPLETE-eligible` default served only direct callers (tests, future integrations) —
  exactly the "UNKNOWN interpreted as FRESH" hazard. Propagation defects closed too: `nan`
  slips every comparison silently; `inf` is unbounded; negative age means a quote ahead of the
  observation clock (clock pathology). Precedent supports strictness: classifier and opportunity
  engines already treat price older than 300 s as UNKNOWN/insufficient, and no setup has ever
  been detected on marks older than ~17 s.

**Policy (Contract v1.1):** `_classify_mark_age()` — ok (finite ≥ −1000 ms; tiny negatives clamped
to 0.0 as snapshot/observe skew tolerance) vs unknown (None/malformed) vs nonfinite vs future
(< −1000 ms). Every non-ok verdict records PENDING with a specific reason (grace-deferred, §2).
No ages replaced by zero (clamp only touches sub-millisecond-scale negatives toward 0.0, stated).

## 2. PENDING lifecycle — decision: grace-deferred, then terminal (documented against alternatives)

Historical contract: PENDING meant "matured but no mark", terminal via the seen-set (written in
P1-14B.1/P1-14B.3); in practice 0 PENDING rows ever existed (probe skips mark-less ticks), so the
state was nearly-unused — design freedom with minimal legacy constraint.

**Alternatives contrasted:**
- *Status-quo terminal PENDING:* zero changes, but horizons maturing into stale windows never
  complete even when fresh quotes arrive one tick later (the task's loss case).
- *Recoverable PENDING (upgrade to COMPLETE):* rejected — the `UNIQUE(key, horizon, observed_at)`
  schema cannot express upgrades without either backdating (fabrication-adjacent) or second rows
  (breaks the no-duplicate invariant, dashboard denominators, and all 0-dupe audits); history
  mutation questions; most complexity for marginal gain over grace.
- *Adopted — grace-deferred terminal PENDING:* failed evaluations (mark absent, stale-known,
  unknown, nonfinite, future) emit NOTHING while `now − first_failure ≤ horizon_ms` (recovery
  window = one horizon-length past maturity, i.e. the pre-existing `obs < det + 2H` audit bound,
  now enforced); only after the window exhausts is terminal PENDING recorded with the current
  cause's reason + "; recovery window exhausted". INSUFFICIENT_HISTORY (no reference — nothing
  can ever fix it) stays immediate + terminal. Memory-only `_pending_since` (restart restarts
  grace — bounded to one extra window, documented; cleared on terminal emission). No schema
  change (v9 stays, no migration), no new states, no rewrites, idempotency and restart safety
  preserved. Residual accepted limitation: post-window freshness never upgrades — future coverage
  comes from new setups, and PENDING rows permanently explain why.

## 3. Outcome Contract v1.1 (versioned, in `PROSPECTIVE_CONTRACT_VERSION`)

| Situation | Verdict |
|---|---|
| mark fresh (finite age in [−1000, 120000]) + reference + matured | COMPLETE |
| mark stale-known (>120000) | retry in-window → PENDING(stale…) terminal |
| age unknown / malformed / non-finite / future(<−1000) | retry in-window → PENDING(explicit reason) terminal |
| mark absent | retry in-window (absent) → PENDING(no mark…) terminal |
| not matured | skip (absent) |
| no detected_mark_price | INSUFFICIENT_HISTORY immediate terminal |
| stored terminal row (any state, incl. across restarts) | never re-emitted |
| retention 90 d / bound 500 per setup (scoped) | unchanged |

Telemetry (additive, all real): `status()` gains `completed`, `pending`, `insufficient`
(lifetime emission counters) and `in_grace` (current deferred count); summary/dashboard blocks
pass through (subset-shape tests confirm compatibility).

## 4. Persistence & compatibility audit (v9, no changes)

1. Key `(candidate_key, horizon)` uniqueness is contract-level (seen-set + grace + terminality),
   NOT schema-level — schema dedups per observation event `(key, horizon, observed_at)`. Stated.
2. Update rules: `INSERT OR REPLACE` (same-triple replace; cross-triple append). Unchanged.
3. Transitions: outcome rows ARE the log; one terminal row per (key,horizon) max — no separate
   transition table (documented limitation, unchanged).
4. Restart: seen rebuilt from ALL stored rows (any state); grace memory restarts (bounded).
5. Retention 90 d hourly + per-key 500 bound (scoped P1-14B.1). Unchanged.
6–8. PENDING/COMPLETE/INSUFFICIENT_HISTORY semantics per §3 table.
9. Cross-key protection: scoped bound (tested P1-14B.1, green). Unchanged.
10. Duplicates: 0 across 99 rows, before and after. No destructive test ever touched the
    operational DB (all destructive paths use tmp DBs). **All 99 historical rows preserved
    byte-identical; none rewritten or deleted.**

## 5. Tests — 683/683 OK, exit 0 (648 + 19 new + 16 net from conversion)

- New `tests/test_p14b_4_lifecycle.py` (19): contract version, classifier (6 verdicts incl. clamp),
  boundary, grace deferral per cause (stale/unknown/absent/nonfinite/future), in-grace recovery to
  COMPLETE (UNKNOWN_TO_FRESH), recorded-PENDING terminality (PENDING_TO_COMPLETE guard),
  single-row under repeated evaluations, restart-with-PENDING (no re-emit; new horizons still
  complete), restart-during-grace (grace restarts), rehydrate-COMPLETE, verdict counters.
- **Converted `tests/test_prospective.py` (35):** AUDIT FINDING — the 35 P1-14A tests were bare
  pytest-style functions that the canonical `run_tests.py` (unittest discovery) silently SKIPPED
  (0 executed; verified). Converted to `TestCase` (fixtures → `mkdtemp`, dropped unused
  pytest/mock imports), updated to v1.1 (fresh ages on COMPLETE-intent calls; grace pattern for
  the no-mark test; new telemetry keys in the shape test). All 35 now execute and pass — the
  gate count step 648 → 683 is this conversion coming online, not new coverage claims.
- Updated to v1.1: P1-14B suites (fresh ages on 23 numeric-price calls; grace pattern for the
  no-mark test), P1-14B.1 (seed helper fresh age), P1-14B.3 (stale/unknown/terminal tests to grace
  patterns; fail-open test renamed to the strict expectation). Each change preserves the test's
  original intent under the new contract (timing tests isolate timing via fresh ages).
- Retention/bound/cross-key/lookahead/dupe cases from §7: covered by existing P1-14B/1B.1 suites
  (green, untouched semantics) — mapped, not duplicated. Market-classifier and opportunity rules
  untouched.

## 6. Controlled validation — short regression run, COMPLETED naturally

`control start --duration 120` (PID 10256, preflight clean, clock +508 ms, UTF-8 log
`logs/probe-runs/probe-20261009T110533Z.log`): 11/11 streams, 0 reconnects/rejects, 24 setups
rehydrated from summary 1, 0 writes / 0 errors (no new matured-unseen cells in-window — correct),
new telemetry keys live, STOPPED cleanly, DB byte-identical (24/99). The reworked `observe()`
is regression-clean under production traffic. No stale-mark occasion occurred (marks
fresh-or-absent as historically) — Fix A live-fire still unobserved; unit-proven only (stated).
No 35-min/4–6-h runs, no paper trading (per task bounds).

## 7. Gates & verdict

CLOCK (implied PASS, +508 ms preflight, syncs ok) / PROSPECTIVE PASS (contract enforced,
telemetry live) / PERSISTENCE PASS (untouched, 0 errors) / SAFETY PASS (observe, 0/0/0,
canonical plane, V2/main untouched). No TRANSPORT/FRESHNESS re-rating in this task (no long run).
**Global verdict: PASS** (audit + contract + tests + regression validation complete; residual
limitations documented). P1-14C not started.

## 8. Remaining blockers & V2 notes

1. ≥30 min healthy-transport window still undemonstrated (unchanged).
2. Fix A live-fire unobserved (needs a degraded-marks window; unit-proven).
3. Structural OGN/RLC-type coverage gap (needs live subscription, never synthesis).
4. V2 contract notes (no frontend changes): PENDING rows may now carry stale/unknown/future/no-mark
   reasons with "; recovery window exhausted" — render PENDING distinctly, never coerce; new
   `status()` keys (`completed/pending/insufficient/in_grace`) available on `/api/prospective`
   via the embedded status block; `PROSPECTIVE_CONTRACT_VERSION` ("1.1") proposed for the
   API payload in a future change (not added — contract-only in this task).

## 9. Files & traceability

- Changed: `src/microstructure_probe/prospective.py` (classifier, grace lifecycle, counters,
  contract version); `tests/test_prospective.py` (unittest conversion + v1.1);
  `tests/test_p14b_validation.py`, `tests/test_p14b_1_time_integrity.py`,
  `tests/test_p14b_3_transport_freshness.py` (v1.1 intent-preserving updates);
  `tests/test_p14b_4_lifecycle.py` (19 new); this report.
- Updated: `CURRENT_STATE.md`, `TASK_QUEUE.md`, `FEATURE_BACKLOG.md` (F-P14A-01),
  `DECISIONS.md` (append-only), `PROSPECTIVE_EVALUATION_SPEC.md` (contract v1.1 section).
- `SUCCESS_GATES.md`: intentionally unchanged — PARTIAL/PASS task verdicts advance no gate
  checkboxes (that IS the correspondence).
- Evidence (uncommitted, preserved): `data/microprobe.db` (24/99 intact),
  `logs/probe-runs/probe-20261009T110533Z.log` (new file). Temp scripts deleted.
