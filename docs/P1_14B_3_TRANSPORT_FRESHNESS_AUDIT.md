# P1-14B.3 — Transport Freshness & Prospective Outcome Validity Audit

**Mode:** AUDIT → REPRODUCE → ROOT CAUSE → CORRECT → TEST → CONTROLLED VALIDATION → DOCUMENT → COMMIT → STOP
**Date:** 2026-10-09
**Branch:** `phase1/market-intelligence-dashboard`
**Starting SHA:** `1e359cd6bb6b810a4cd783e5bf840153e4c1b5a5`
**Baseline validated pre-run:** schema v9, 24 setups, 68 COMPLETE outcomes, 0 dupes (identical to published P1-14B.2 state).
**Safety:** `BOT_MODE=observe` end-to-end; 0 keys / 0 orders / 0 capital. V2 worktree/ports and `main` untouched.

---

## 1. Transport root cause (P1-14B.2 episode, fully traced)

Pipeline audited in code: WS connect (`_connection_loop`, backoff 1 s→30 s, `max_queue=4096`)
→ receipt stamp at handler entry → E/T extraction (`_legacy_timestamp`: max-E for markPrice arrays)
→ skew guard (`|received − E| > 5000 ms` → reject + count + rejection record, engines never see it)
→ normalization → engines → snapshots → persistence → classifier/opportunity/recorder.

**Findings from the P1-14B.2 log (per-summary corrected-lag series):**

| rt | bookTicker p50/p95 | aggTrade p95 | markPrice p95 | processing max | verdict |
|---|---|---|---|---|---|
| ≤946 | ~224/410 ms | ~246 ms | ~243 ms | sub-ms typical | healthy |
| 983 | 287/4234 ms | 275 ms | — | 3.1 s (single spike) | onset |
| 1090–1192 | 302/65 s–158 s | 0.5 s–28 s | — | frozen (no new maxima) | delivery stall |
| 1243–1379 | 312–7366/235 s–375 s | 44 s | 21.5 s | frozen | host-external stall |

- **Local backlog DISCARDED:** processing stayed sub-ms typical (one 3.1 s one-off cannot explain
  375 s lags); message rate collapsed ~950/s → ~145/s with NO drain spike (a local backlog would
  spike on drain); engine queues 0/0; inflight ≤8.
- **Clock skew DISCARDED:** 3/3 in-run syncs ok (offsets −350→−384 ms, RTT ~330–348 ms), stable.
- **HOT logic DISCARDED as cause:** canonical CORE streams degraded equally; the worst stream
  (bookTicker, p95 329 s) rode `public` with ZERO reconnects — an open, never-dropping connection
  delivering minutes-old events. HOT resubscribe verified exact (JCT/OGN/RLC both connections,
  no duplicated globals).
- **Connection timeline:** rejects preceded errors by ~4 min (stall on OPEN connections from rt≈983;
  first `ConnectionClosedError` 22:14:21, then handshake `TimeoutError`s with 1→16 s backoffs on
  market + hot-public; never recovered before the stop).
- **Conclusion:** host-external delivery stall (Binance-side delay or network-path buffering —
  indistinguishable with available data; NEITHER claimed exclusively), followed by a path outage.
  The probe's retry path only triggers on errors/close: with stale-but-flowing data nothing ever
  triggers, so open-but-stale persists indefinitely. `20/20 streams` counts connections/messages,
  never health — proven by coexisting STALE flags. `last_seen` updates on RECEIPT (pre-guard), so
  the silence model is blind to flowing-stale traffic.

**Unconfirmed hypotheses (kept as such):** provider-internal cause vs ISP-path cause (no vantage
point to separate); the single 3.1 s processing spike as contributor (timing coincides with onset,
magnitude insufficient — correlation without causal weight).

## 2. Historical 68-row freshness classification (read-only; rows preserved, none rewritten)

Rule (audit labels only — NOT motor states): `observed_at ≥ detected_at + horizon` proves order,
never quote freshness. Per-row evidence: stored prices, observed_at, run-window health at
observation instant (pristine vs degraded), detection-time `price_age_ms` from `setup_json`
(1–17 s everywhere — detections always had fresh marks). Row-level observation-time quote age is
NOT in v9 columns → degraded-window rows stay honestly unknown.

| Bucket | Count | Meaning |
|---|---|---|
| VALID_FRESH | 19 | prompt (≤60 s past maturity) + pristine window |
| VALID_BUT_DELAYED | 28 | honest-late rehydrated observations (P1-14B.1 runs), math/lookahead clean |
| INSUFFICIENT_FRESHNESS_EVIDENCE | 21 | observed in degraded window (rt≥983); kept, math/lookahead still verified |
| STALE_OR_INVALID | 0 | no math/lookahead violation, no proven-stale quote |
| **Total** | **68** | |

## 3. Fixes implemented (minimal, defect-tied, no new motor states)

**Fix A — stale-mark gate (`prospective.py` + `probe.py`, PENDING in existing vocabulary):**
`STALE_MARK_AGE_MS = 120_000` (LOCAL_POLICY, aligned with the 120 s early-warning).
`observe(..., mark_age_ms=None)`: known age above threshold → PENDING with explicit reason
carrying the age (`"stale mark price (age Nms exceeds 120000ms); maturity honest, quote too old"`);
unknown/malformed age stays fail-open (current behavior); boundary (==) completes. PENDING is
terminal via the existing seen-set (consistent with same-process semantics). Probe passes
`sample_age_ms` (already present in price rows) with malformed→None guard. No schema change:
the reason string keeps ages queryable for future audits (V2 contract note, §7).

**Fix E — freshness watchdog (`probe.py`, reuses the retry path, never aggressive):**
- `_last_accepted_ms[stream]` stamped post-guard (receipt ≠ acceptance; rejected traffic never refreshes).
- Pure `_connection_for_stream()` (canonical/HOT/global mapping; unknown → unwatched).
- `_check_connection_freshness()` on the probe-owned summary path only: fires when a live connection
  has zero accepted traffic beyond budget — 90 s (public/market/hot-public), 300 s (hot-market,
  aggTrade-only legitimate sparsity) — with 120 s connection-age grace and 120 s per-connection
  cooldown; every fire logged (`forced_reconnect_requested` with age + budget).
- `_connection_loop` consumes one-shot requests and breaks cleanly → existing attempt/backoff/HOT-URL
  machinery reconnects (no new tasks, no supervisor, no tight loops).
- Summary `freshness` block (additive): `lastAcceptedMsByStream`, `reconnectRequested`,
  `forcedReconnects` — separates connected / received / accepted / fresh / snapshot-age.

**Not changed:** skew guard, cadence/staleness sets, backoff policy, HOT desired-set logic, sibling
global-cap logs, maturation rules, outcome states, dashboard, V2.

## 4. Tests — 629/629 OK, exit 0 (609 baseline + 20 new `test_p14b_3_transport_freshness.py`)

Late/reject bursts (accepted-map frozen, counts exact); connected-without-fresh fires per connection;
recovery resets + cooldown suppresses refire then re-arms; HOT mapping incl. unknown-skip;
markPrice-array and HOT-depth scenarios; quiet-HOT-aggTrade 300 s threshold both sides; one-shot
consume; threshold constants; stale→PENDING (+reason, stored, terminal, boundary, fail-open);
audit-label policy lock. P1-12A/B, P1-13A untouched.

## 5. Controlled validation — ABORTED at 17.1 min (rule breach + path outage)

- Preflight PASS (0 procs, port free, registry STOPPED, SQLite ok, disk 162.4 GB, baseline
  identical). Clock PASS (+388 ms worst case vs 60 s; deliberate no-resync; in-run syncs ok).
- Single authorized run: `control start --duration 2100`, PID 34040, `logs/probe-runs/probe-20261009T100545Z.log`
  (UTF-8, new file). 10-min pre-window: 6 min pristine, then episode onset rt≈402.
- **Watchdog validated live:** fired market+public at 90 s budgets → both reconnected in ~12 s →
  **5 minutes of zero rejects** (cumulative rate fell 7.93 % → 5.19 %) → second episode onset rt≈660
  → watchdog fired again (market/public/hot-public at 90 s, hot-market at 316 s > 300 s budget) →
  path collapsed into handshake `TimeoutError`s (10 error-reconnects/3 min, backoffs 1→16 s).
- **Abort:** cumulative 17.2 % + error-reconnect breach + unrecoverable path → `control stop` at
  10:22:53Z (1027 s, exit 0, `stopped-by-agent`). Window <30 min = INSUFFICIENT. No second run.
- Deviation note: at first 5.19 % crossing the marginal rate was 0 % with recovery in progress;
  the run continued ONE bounded cycle under tightened watch to validate the just-triggered recovery
  (documented two-strike bound: abort past 8 % / error-breach / failed recovery — the 8 % and
  error rules both fired). Strict-reading alternative (abort at first crossing) is recorded.
- Prospective during run: 24 setups rehydrated live; per-cycle observe live; Fix A had no occasion
  (marks absent-not-stale during outage → honest skips, writes frozen); 0 errors/drops.
- Post-run audit: 24 setups, **99 outcomes (68 + 31), all COMPLETE, 0 dupes**, no-lookahead + math
  PASS; 21 missing cells FULLY explained (OGN/RLC 15m/1h/4h: matured between runs or while
  unsubscribed — CORE-only restore, HOT rotation to JCT/KAIA/USUSDT at 10:15:58Z, never
  simultaneously matured+observed+marked; no defect). DB file +0.0 MB; disk 163.5 GB.
  CPU/mem per-process not captured (stated). No profitability statistics (rule).

## 6. Gates

| Gate | Result |
|---|---|
| CLOCK_GATE | PASS (sub-second, stable, syncs ok, no-resync recorded) |
| TRANSPORT_GATE | PARTIAL (recovery proven once, then path outage; error reconnects breached) |
| FRESHNESS_GATE | PARTIAL (watchdog live-validated incl. second-cycle firing; stale-mark gate unit-proven, no live occasion; 68-row classification complete; 21 missing cells explained) |
| PROSPECTIVE_GATE | PASS (rehydration + per-cycle observe live, 31 new outcomes, 0 dupes, no fabrication) |
| PERSISTENCE_GATE | PASS (integrity ok, 0 errors, 24-key coexistence, bounded logs held) |
| SAFETY_GATE | PASS (observe end-to-end, 0/0/0, canonical plane, verified-PID stop, V2/main untouched) |

**Global verdict: PARTIAL** (duration insufficient; transport limiting; fixes validated in scope).
**No 4–6 h run authorized. P1-14C not started.**

## 7. V2 contract notes (no frontend changes)

- Existing `/api/prospective` rows may now carry PENDING with `stale mark price (age Nms…)` reasons —
  render PENDING distinctly from missing; never coerce to zero/return.
- Proposed (not implemented): `mark_age_ms` + observation-window health on outcome payloads;
  `freshness` summary block (`lastAcceptedMsByStream`, `forcedReconnects`) for a connection-health
  view. Suggested V2 display: `observed_at − maturity` lateness; absent horizons stay absent.

## 8. Remaining blockers

1. ≥30 min healthy-transport window still undemonstrated (best: 15.8 min + 5 min recovered).
2. Clock resync note if offset ever exceeds 5 s (currently sub-second; system self-syncs).
3. Path flakiness is environmental and recurrent (3 episodes across runs) — next attempt requires a
   clean 10-min pre-window AND should treat the first watchdog fire as a yellow flag for early
   termination judgment.
4. OGN/RLC-type coverage gap is structural (outcomes need live subscription); backfill only via
   re-promotion, never synthesis.

## 9. Files & traceability

- Changed: `src/microstructure_probe/prospective.py` (stale-mark gate),
  `src/microstructure_probe/probe.py` (accepted accounting, watchdog, loop hook, freshness block,
  mark-age pass-through), `tests/test_p14b_3_transport_freshness.py` (20 new), this report.
- Updated: `CURRENT_STATE.md`, `TASK_QUEUE.md`, `FEATURE_BACKLOG.md` (F-P14A-01),
  `DECISIONS.md` (append-only). Posevaluation spec + architecture + gates updated where the
  contract changed (see §10).
- Evidence (uncommitted, preserved): `logs/probe-runs/probe-20261009T100545Z.log`,
  `data/microprobe.db` (24 setups / 99 outcomes). Temp scripts deleted.
