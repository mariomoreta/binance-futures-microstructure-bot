# P1-14B.1 — Time Integrity, Data Quality & Prospective Readiness Audit

**Mode:** AUDIT → REPRODUCE → CORRECT → TEST → VALIDATE → DOCUMENT → COMMIT → STOP
**Date:** 2026-10-09
**Branch:** `phase1/market-intelligence-dashboard`
**Starting SHA:** `18c639b3311e675d6d32dc19ad31781664097196`
**Safety:** `BOT_MODE=observe` enforced; zero orders, zero capital, zero keys.
No live trading, no execution paths touched. Dashboard V2 worktree untouched.

---

## 1. Clock taxonomy (verified in code)

Five distinct time sources exist. They are never mixed; each timestamp below
names its unit and origin.

| # | Clock | Unit | Source | Used for |
|---|---|---|---|---|
| 1 | Exchange event time (E) | ms epoch | Binance WS payload `E` (bookTicker/depth/aggTrade/markPrice/forceOrder) | skew guard, engine ordering, lag metrics |
| 2 | Exchange transaction time (T) | ms epoch | Binance WS payload `T`/`t` (trade time; markPrice: next funding time, NOT latency) | E−T exchange-side delta only |
| 3 | Host receive time | ms epoch | `time.time_ns() / 1_000_000` at message receipt | delivery-lag metrics, skew guard minuend |
| 4 | Probe wall clock (`as_of_ms`) | ms epoch | `time.time_ns() / 1_000_000` once per summary tick (`probe.py:1433`) | `detected_at_ms`, `observed_at_ms`, maturity arithmetic — the prospective time base |
| 5 | Monotonic clock | seconds (float, differences only) | `time.monotonic()` / `perf_counter_ns()` | durations, gap detection, silence, queue cleanup throttle (`prospective.py` worker), never persisted as an event stamp |

**Binance native units:** `serverTime` (REST `/fapi/v1/time`), WS `E`/`T` are
all millisecond epochs — verified in `clock.py` (`int(payload["serverTime"])`,
midpoint arithmetic in ms) and live (single public probe 2026-10-09:
`serverTime_ms=1791508700285`, host ahead by 448 ms incl. path RTT).

**Host clock status (2026-10-09):** `w32tm` reports Leap Indicator 3 (not
synchronized), stratum 0, last successful sync 2026-10-08 18:35 local, root
dispersion 9.02 s. Single-shot host−Binance offset +448 ms (host ahead).
In-probe syncs during this task's runs: 1/1 ok each (−283 ms / −304 ms,
RTT ~340 ms). Verdict: host wall time is sub-second-aligned at probe instants
but NOT tightly disciplined (unsynchronized flag, 9 s dispersion, drift
−120 ms → +448 ms across runs). The core design is correct to use exchange E
for ordering/skew decisions and host wall only as a self-consistent
`as_of_ms` anchor (detection and observation share the same clock, so
maturities measure true host-elapsed durations; a host jump would shift
firing time but can never look ahead). The 60 s upstream freshness gate
tolerates the observed skew scale (≪ 60 s).

---

## 2. Anomaly A — pilot `elapsed=-1789712305900s` (monitor-side, CONFIRMED)

**Location:** `logs/p14b_pilot.log` (Run A, executed 2026-10-08T23:56:49Z,
38 polls × 10 s, killed externally — no `finally`, no `EXITED`, no audit).

**Mechanism (proven, exact-constant reproduction):** the executed monitor
computed `elapsed = time.time() [seconds] − t0 [millisecond epoch]`.

- Magnitude proof: Oct-2026 `time.time()` ≈ 1.79e9 s; ms epoch ≈ 1.79e12.
  Only an s−ms subtraction yields ≈ −1.79e12. No other unit error
  (s−µs, ms−ns, timezone, DST) produces this magnitude.
- Tick proof: consecutive polls advance exactly +10/poll — live seconds
  ticking from a fixed wrong base (constant ms `t0`, live seconds minuend).
- Constant proof: with `t0_ms = 1791503809710` (`now_ms()` captured ~8 ms
  after the start line) and poll-1 wall `1791503809.713313`,
  `f"{wall − t0:.0f}"` renders **exactly** `-1789712305900`; poll 2 renders
  exactly `-1789712305890`. Locked by
  `tests/test_p14b_1_time_integrity.py::TestElapsedAnomalyForensics`.
- Consequence: the monitor's `elapsed > 200` hard-timeout safety could never
  fire (elapsed deeply negative), so it polled until externally killed —
  consistent with the "interrupted session" record.

**Scope:** monitor auxiliary ONLY. The core engine never performs this
subtraction (`prospective.py`: zero `time.time()` calls; `probe.py` wall
source is `time.time_ns()/1_000_000` used consistently in ms; `clock.py`
all-ms). No core change owed to Anomaly A.

**Executed-script gap:** the preserved `p14b_pilot_monitor.py` (Run B,
`[poll N]` format, clean seconds elapsed, EXITED=0, AUDIT COMPLETE) is
statically unit-clean (`t0 = time.time()`, `now_ms()` only in ms contexts,
all `fromtimestamp()` args in seconds) and is NOT the version that produced
`logs/p14b_pilot.log` (`[ts]` format, different header). The executed buggy
version was never preserved — its source is UNKNOWN. Preserved pilot scripts
are kept byte-identical as evidence; monitor hygiene items below are
documented, not patched into evidence files.

**Monitor hygiene defects (both versions, display/methodology only):**
1. Counters start at 0 while the DB is cumulative across runs → pre-existing
   rows reported as "NEW" on poll 1 (both runs: `setups=6 (was 0)` with a
   DB that already held 6 rows + 1 outcome). First-seen timestamps from
   poll 1 are spurious. Recommendation: baseline counters from the first
   query.
2. `fmtsetup` displays `setup_json['detect_price']`, but the stored key is
   `detected_mark_price` (Run B poll 1 shows `detect_price=None` for rows
   whose reference price 2477.50 demonstrably exists in the outcome row).
   Display-only; no data impact. Recommendation: read `detected_mark_price`.
3. Run A reused `logs/p14b_pilot_run.out`; Run B's script truncates that
   path on start (`open(OUTLOG, "w")`), destroying Run A's probe evidence.
   Recommendation: never truncate shared evidence logs (append + run tag).

---

## 3. Defect B — restart rehydration dead on the production path (CORE, FIXED)

**Chain (proven end-to-end):** `config/probe.json` carries no `db_path` →
`ProbeConfig` has no `db_path` attribute → `probe.py:227`
`ProspectiveRecorder(db_path=None)` → `_load_from_db` early-returned on
`self.db_path is None` → production restarts NEVER rehydrated the registry,
while the worker/read paths fell back to the default store and worked.
Live proof: Run B summaries show `registered_setups: 0` with 6 setup rows
in the DB; post-fix controlled run shows `registered_setups: 7` from the
first summary.

**Consequence:** every probe restart orphaned all registered setups with
unmatured horizons — their horizons could never be observed post-restart.
This (not only the clock-anomalous window) explains the missing 15 m
outcomes during the pilots: three 15 m maturities (23:57:04, 23:58:04,
23:58:34) passed during Run A with a recorder holding zero setups.

**Fix (`prospective.py::_load_from_db`):** use the default store when
`db_path is None`, mirroring `_worker`/`outcomes_for`; rebuild
`_seen_outcomes` from stored outcome rows so already-observed horizons
never re-emit after a restart (exact cross-restart idempotency — required
companion, otherwise enabling rehydration would duplicate horizons at new
`observed_at_ms`, which the `UNIQUE(key, horizon, observed_at_ms)`
constraint cannot catch); warn-and-continue on load failure instead of
silent `pass` (the silence hid this defect in production — Run B logged
nothing about its empty registry).

**Historical impact:** none — no stored row rewritten; only future restarts
see pre-existing setups and observe their matured horizons (the specified
behavior). Late-but-honest emissions carry the true `observed_at_ms`;
lateness is auditable as `observed_at_ms − (detected_at_ms + horizon_ms)`.

---

## 4. Defect C — outcome store wiped other setups' rows (CORE, FIXED)

**Root cause (`persistence.py::store_prospective_outcome`):** the per-setup
500-row bounding DELETE lacked a key filter on the outer statement, so every
outcome store for key K deleted ALL rows not among K's newest 500 — i.e.,
every other setup's outcome history. Scratch reproduction (tmp DB):
after A×2 rows, one store for B left `total=1, A=0, B=1`.

**Live proof:** controlled run #2 emitted 27 outcomes (`writes=27`,
exactly the 28 matured cells minus 1 already-seen) yet only 4 rows survived
(last-stored key wins). The P1-14B "single outcome" evidence shape was
partly this bug's artifact: matured horizons WERE observed during the
pilots and their rows were subsequently eaten by later stores — the
"horizons never matured" reading in `docs/P1_14B_VALIDATION_REPORT.md` §3/§6
is therefore only partial. Corrected denominators are in §6 below.

**Fix:** scope the outer DELETE with `AND candidate_key = ?` (per-setup
500 bound, as specified). Sibling bounded logs (`opportunity_events`,
`state_transitions`, `universe_events`) use intentional global caps and are
unaffected. Post-fix controlled run #3: 24 emissions → **28 coexisting
rows (4/key × 7 keys), 0 duplicates, all COMPLETE**.

**Historical impact:** rows already deleted are unrecoverable (4-row state
observed before run #3 is documented, not reconstructed). No surviving row
was modified. Going forward, outcomes accumulate per the specified
append-only bounded log.

---

## 5. Change D — per-cycle observation independent of matches (CORE, FIXED)

**Divergence (demonstrated):** the spec Observation section mandates
"`observe()` called once per summary cycle"; the implementation called it
inside `for cand in opp_matched` — with zero matched candidates (quiet
ticks), registered setups were never observed even with healthy marks.
Controlled run #1 proof: 7 setups rehydrated, 4 summaries, `writes=0`,
`tracked=0/detected=0` (marks gated the first tick, matches empty all run).

**Fix (`probe.py` summary path):** registration stays in the candidate loop;
observation moved to a per-symbol loop over `opp_bundles` (same mark source,
`features.price.current_price`, same `as_of_ms`), skipping `None` marks as
before. No maturation rule, formula, or state changed; multi-candidate
ticks now observe once instead of redundantly. Live proof: run #2 emitted
27 outcomes on the first marked summary; run #3 emitted the remaining 24.

---

## 6. Corrected evidence denominators (read-only audits, no rewrites)

DB `data/microprobe.db`, schema v9, cumulative across ≥4 runs
(pre-pilot ~23:42–23:43, Run A 23:56–00:02, Run B 00:04–00:07 + readtest,
P1-14B.1 controlled runs). Prospective tables carry no run ledger, so
per-run attribution below comes from log cross-referencing, stated as such.

| Denominator | Value |
|---|---|
| setups_registered (unique keys) | 7 |
| setups from pre-pilot run (23:42:04–23:43:34) | 5 |
| setups first seen during Run A window | 1 (key later re-registered; REPLACE semantics) |
| setups detected during Run B (00:06:30.106, same tick) | 2 (1 new key + 1 re-registration) |
| horizon cells possible (7 × 5) | 35 |
| cells matured as of run #3 | 28 (4h cells: 0/7 matured — genuinely future) |
| COMPLETE outcomes stored (post-fix accumulation) | 28 |
| PENDING / INSUFFICIENT_HISTORY / PARTIAL rows | 0 (absent, never fabricated) |
| duplicate (key, horizon) pairs | 0 |
| no-lookahead (`obs ≥ det + horizon`, return math to 6dp) | PASS on all rows |
| rows lost to Defect C (unrecoverable) | ≥ the Run-A-era observations overwritten before run #2 (exact count unknowable; the 1 pre-existing UP-1m row survived until run #2) |

Stored timestamps are unambiguously ms epochs (all 8 recovered values in
[1.79e12, 1.80e12); locked by test). The single original outcome
(`REVERSAL_WATCH:ETHUSDT:UP → 1 m`, `mark_return_pct=-0.037134`,
observed 552 ms after maturity) was recorded by the pre-pilot run, NOT the
pilot — the pilot monitors' poll-1 "NEW OUTCOME" was a stale pre-existing
row (Defect: stale-as-new, §2).

---

## 7. Tests

Full suite `python run_tests.py`: **609/609 OK** (593 baseline + 16 new),
exit 0. New file `tests/test_p14b_1_time_integrity.py` (16 tests):

- T1 forensics (3): exact-constant `elapsed` reproduction, s−ms signature,
  +10/poll tick.
- T2 stored-unit locks (2): ms-epoch discrimination, obs−det arithmetic.
- T3 default-path rehydration (2): registry + detected-price carried
  (FAILED pre-fix, PASS post-fix).
- T4 cross-restart duplicate suppression (1): later-tick re-observe emits
  nothing, storage stays 1 row (FAILED pre-fix).
- T5 pending-horizon restart (1), T6 late-observation honesty incl. 4-horizon
  fan-out (1), T7 exact maturity boundary (1), T8 no wall-clock read inside
  `observe()` via module-clock mock (1), T9 horizon constants (1),
  T10 `prospective_outcome_keys` (1) + store-isolation (1) + per-key-500
  bound (1).

Updated `tests/test_p14b_validation.py::test_rehydrate_rebuilds_seen_outcomes_set`
to the hardened contract (no re-emission incl. later tick; storage stays one
COMPLETE row with the original `observed_at_ms`; registry still carries
`detected_mark_price`). P1-12A/P1-12B/P1-13A untouched.

Live validation (all `BOT_MODE=observe`, blocking, exit 0):
- Run #1 (120 s, pre-hoist): reg=7 from summary #1 (Defect B fix proven),
  0 emissions (Defect D demonstrated), safety 0/0/0.
- Run #2 (120 s): 27 emissions on first marked summary (Defect D fix
  proven), 4 rows survived (Defect C demonstrated live).
- Run #3 (120 s): 24 emissions → 28 coexisting rows, 0 dupes (Defects B+C
  fixes proven together). Transport: 11/11 streams, 0 reconnects,
  0 rejects, uptime ~98.9 %, 0 gaps, clock 1/1 ok (−304 ms / 349 ms RTT).

---

## 8. Prolonged-run readiness (assessment ONLY — no long run started)

Readiness criteria for a future window covering 4 h horizons (≥5 h wall):

| Criterion | PASS threshold | Current evidence |
|---|---|---|
| WS transport health | 0 reconnects, <1 % rejects over a 30+ min window | Run #3 120 s: 0/0/0 % (short window — NOT sufficient alone) |
| Data freshness | mark `current_price` present every summary | Runs #2–3: present after ~60 s warmup |
| Timestamp integrity | all persisted stamps ms-epoch; no s−ms mixing in core | Locked by tests; monitor hygiene items documented |
| Recorder continuity | rehydration + seen-rebuild + per-cycle observe | Proven live (reg=7, 28 rows, 0 dupes) |
| Storage boundedness | per-key 500 cap scoped; retention 90 d | Proven by test (505-insert cap test) |
| Resources | DB growth pace known; disk headroom | DB 238.9 MB; free 163.6 GB; inflight high-water ≤8 |
| Safe lifecycle | canonical control plane, merged UTF-8 logs, registry COMPLETED | Used for all three runs (exit 0) |
| Abort conditions | any reconnect storm (>5/10 min), reject rate >5 %, clock sync fail, persistence errors >0, disk <10 GB | Defined; none triggered |

**Blockers before authorizing a 4–6 h run:** (1) a 30+ min healthy-transport
window has not yet been demonstrated post-fix (120 s windows are
insufficient); (2) host clock discipline is weak (`w32tm` unsynchronized —
tolerated by design, but a pre-run `w32tm /resync` + offset note is
required); (3) evidence-log hygiene (UTF-16 PowerShell capture recurred —
use `Out-File -Encoding utf8` or the canonical merged-UTF-8 run logs;
never truncate shared outlogs). **No prolonged run started in this task.**

---

## 9. Dashboard V2 coordination (no changes made)

V2 worktree (`dash-v2-03-token-detail`) untouched; its ports untouched.
Real `/api/prospective` contract (unchanged code path, current data):
`{generated_at, note (RESEARCH ONLY), schema_version: 9,
prospective: {enabled, state, registered_setups, setup_count: 7,
outcome_count: 28, latest_outcomes[:10]}}` — outcome rows carry
`candidate_key/symbol/horizon/observed_at_ms/outcome_state/mark_return_pct/
detected_price/current_price/reason`. No new endpoints created. Suggested
V2-side follow-ups (not implemented): display `observed_at_ms − maturity`
lateness; never render absent horizons as zero.

---

## 10. Files changed

- `src/microstructure_probe/prospective.py` — default-store rehydration,
  seen-set rebuild, load-failure warning, dead-constant removal.
- `src/microstructure_probe/persistence.py` — scoped per-key 500 bound;
  new `prospective_outcome_keys()`.
- `src/microstructure_probe/probe.py` — per-cycle per-symbol observation
  (registration untouched).
- `tests/test_p14b_1_time_integrity.py` — 16 new tests.
- `tests/test_p14b_validation.py` — 1 test hardened to the new contract.
- Docs: this file (new); `CURRENT_STATE.md`, `TASK_QUEUE.md`,
  `DECISIONS.md` (append-only), `FEATURE_BACKLOG.md` (F-P14A-01),
  `PROSPECTIVE_EVALUATION_SPEC.md` (observation/rehydration/lateness notes),
  `P1_14B_VALIDATION_REPORT.md` (addendum pointer).

Evidence preserved, uncommitted: `.firecrawl/`, `analyze_p13a_run.py`,
`p14b_dashboard_readtest.py`, `p14b_pilot_monitor.py`,
`logs/p14b_pilot.log`, `logs/p14b_pilot_log.txt`,
`logs/p14b_pilot_run.out` (Run B only — Run A output lost to truncation),
`logs/p14b_1_validation_run.out`, `logs/p14b_1_observe_run.out`,
`logs/p14b_1_accumulate_run.out`, `data/microprobe.db`.
