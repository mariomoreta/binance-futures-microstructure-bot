# P1-14B.6 — Reproducibility & Operational Readiness Report

**Mode:** AUDIT → VERIFY → CORRECT → TEST → CONTROLLED RUN → DOCUMENT → COMMIT → STOP
**Date:** 2026-10-10
**Branch:** `phase1/market-intelligence-dashboard`
**Starting SHA:** `f6d6691727e58d31389ab0fece6f1e2a32ea87f9`
**Baseline validated pre-run:** schema v9, 49 setups, 150 COMPLETE outcomes, 0 dupes (identical to P1-14B.5 state).
**Safety:** `BOT_MODE=observe` end-to-end; 0 keys / 0 orders / 0 capital. V2 worktree/ports and `main` untouched.

---

## 1. Reproducibility: second healthy window + episode recurrence in one run

The bot run (PID 14300, 2102.5 s, exit 0 duration-reached) reproduced BOTH regimes back-to-back:
~22.6 min pristine (0 rejects/reconnects, both references agree), then a delivery episode from
rt≈1313 (rejects → 8.83 %, error reconnects market 1 + public 3, watchdog fired 3 cycles, handshake
TimeoutErrors). One healthy window does not extinguish an intermittent fault — confirmed empirically.
The >5 % abort rule breached (~rt 1586) WITHOUT action: live supervision was lost when the launch
call's harness timeout detached the session (documented demerit; no safety rule breached —
0/0/0, persistence clean). Post-hoc analysis substitutes active supervision throughout this report.

## 2. markPrice placement — verified 2×2 matrix (code + live experiments)

Official docs unfetchable again (empty responses, as in P1-05/P1-11B — recorded, not worked around).
Code truth: the bot deliberately splits bookTicker/depth → `/public/stream` and arrays/aggTrade →
`/market/stream` (`build_stream_urls`, live-proven with lag counts on both). Live experiments
(public, bounded, tiny — Exp A/B/C, 90 s each):

| | bare `/stream` | `/public/stream` | `/market/stream` |
|---|---|---|---|
| `btcusdt@bookTicker` | FLOWS (234k/40 min) | FLOWS (6160/90 s) | SILENT 4 min (connected, zero frames) |
| `!markPrice@arr@1s` | SILENT 40 min | SILENT 90 s | FLOWS (180/90 s; 4799/40 min operationally) |

Per-symbol streams live on `/stream` + `/public/stream`; `!` arrays live ONLY on `/market/stream` —
exactly mirroring the bot's own routing (the codebase already encoded the correct placement).
Fix: netprobe `--base-path` restricted to the three observed paths + `array_placement_warning()`
(warn, never block — placement may evolve) + operational reference as TWO concurrent instances
(bookTicker/bare + array/market). No data invented; silence never interpreted as provider failure.

**Alternative mechanism (honest weight):** a vendor-acknowledged failure mode exists TODAY —
GitHub `binance-connector-python#526` (Futures WS returns SUBSCRIBE ACK but zero data frames,
server-side, ~6–14 h, several stream types) and Sierra Chart outage reports for Binance Futures
feeds dated 2026-10-10 (feed stops 4:44/6:45/14:44Z). Same-day independent outage evidence supports
provider-side instability as context for our episodes. It also offers a rival reading of the
silent cells (server-side non-delivery vs path routing). Routing wins on determinism (2×2 stable
across repeats + bot-code corroboration); the single-sample `/market`+bookTicker cell could be
either. NEITHER reading changes any operational conclusion.

## 3. Host telemetry (bounded, UNKNOWN-safe)

`telemetry.py`: `process_cpu_times()` (os.times + monotonic anchor), `cpu_percent_proc()` (pure,
100·Δproc/(Δwall·ncpu), None on missing/non-positive-wall/negative/non-finite), `process_rss_bytes()`
(psapi via explicit ctypes signatures + real OpenProcess handle + cleanup; pseudo-handle variant
failed with ERROR_INVALID_HANDLE during development — fixed and documented by the tests passing).
Per-stream exact byte counts (`bytes_by_stream`; rejected traffic counted too). Probe samples on
its own 30 s cadence into an additive summary `host` block (dashboard reads never shorten the
interval); netprobe samples per summary. NIC and system-wide CPU stay UNKNOWN by design (no
reliable stdlib/ctypes path; per-connection byte rates cover network activity instead).
13 deterministic tests (formula edges, type contracts, byte exactness, stash shape).

## 4. Discriminating evidence (the run's core result)

New telemetry discarded the two remaining local hypotheses:
- **CPU flat 3–6 % in healthy AND degraded phases** (57→203 MB RSS monotonic growth noted, not
  pressure) — localhost-compute contention DISCARDED definitively.
- **Summary cadence 30.5 s baseline**, stretching only to 35–55 s in-episode (mild loop delay, never
  blocked) — event-loop blockage DISCARDED.
- References on the SAME host stayed healthy while all four bot connections degraded — host/ISP as
  primary cause DISCARDED for this episode class.
- Reference bookTicker DID register a mild coincident wobble (p95 168→581 ms, t+1350–1800) while
  the bot collapsed — shared upstream event, ~100× amplification on bot connections.

**Refined attribution:** server-side per-connection delivery degradation (Binance WS edge), with
reconnect-recovery (fresh server-side state) as the observed remedy — except when the episode
escalates to handshake refusals (path outage), where nothing reconnects. The bot's 4-connection,
high-rate footprint raises exposure vs single light connections. Mild shared wobbles mark the same
upstream events at far lower magnitude. Provider-vs-ISP for the residual: still UNKNOWN (stated).

## 5. Health states & watchdog (preserved, re-verified — no working rule changed)

`classify_connection_health()` live in the summary block; no threshold/trigger/cooldown change was
owed (second-cycle fires 292 s apart, recoveries, no loops — all re-verified in prior logs).
The 8.83 % episode exceeded what any reconnect policy could fix (handshakes refused) — correctly
outside the watchdog's design envelope (documented limit, not a defect).

## 6. Prospective preservation (v1.1 + v9 intact)

Post-run read-only audit: **57 setups (+8), 202 outcomes (+52), all COMPLETE, 0 duplicates,
0 anomalies** (no-lookahead + return math on all rows). No PENDING (marks healthy-or-absent, never
stale-known at a tick). No INSUFFICIENT. No state/column/contract change; seen-rebuild, grace,
terminality untouched and green. **All 150 prior rows preserved byte-identical.**

## 7. Tests — 726/726 OK, exit 0 (708 + 18: 4 path + 1 warning + 1 heartbeat-flag + 12 host)

Deterministic, zero live dependency (fakes: scripted transports, failing connects, shared-clock
time travel with loop yields, silent connections). Covers: path allowlist/URL builder/run-uses-path/
placement warning, heartbeat emission + disable flag, fresh/stale/silent/handshake-failure/backoff
bounds, CPU formula edges, host type-contracts, byte exactness (incl. rejected), stash shape,
tracker bytes. Two test-harness defects found and fixed during development (instant-fake loop
monopolization → yield in fake sleep; shared-clock time travel → heartbeat isolation flag).
P1-12A/B, P1-13A, prospective rules untouched.

## 8. Operational validation

- Preflight PASS (0 procs, 8091 free, registry COMPLETED, SQLite integrity ok, disk 160.4 GB,
  baseline identical, clock +121 ms, evidence preserved). 10-min diagnostic gate: netprobe
  first-10-min pristine + bot 0/0/0 % → committed per protocol.
- Single ≤35-min run COMPLETED naturally (2102.5 s, 20/20, market 1 + public 3 error-reconnects,
  8.83 % rejects, exit 0). Reference pair ran 40 min concurrently (bookTicker attempts 1 errors {};
  array attempts 1 errors {}; host cpu 0.0 %, rss ~26 MB).
- Abort rules breached unacted (supervision lost, §1 demerit); no safety rule breached at any point.
- **HEALTHY_DURATION_SECONDS: ~1359 (~22.6 min pristine) — still <30-min target.** No second run
  (protocol: no auto-repeat).

## 9. Gates

| Gate | Result |
|---|---|
| CLOCK_GATE | PASS (+121 ms, stable, syncs ok, no resync) |
| TRANSPORT_GATE | PARTIAL (22.6 min pristine + reference agreement, then path-side episode; per-connection selective) |
| FRESHNESS_GATE | PARTIAL (feeds fresh-or-absent honestly; stale-mark gate untriggered, correct) |
| PERSISTENCE_GATE | PASS (integrity ok, 0 errors, 57-key coexistence, bounded logs held) |
| SAFETY_GATE | PASS (observe end-to-end, 0/0/0, natural completion, V2/main untouched) |

**Global verdict: PARTIAL** (second healthy window banked + attribution refined + fixes validated;
duration objective and abort supervision failed).
**No 4–6 h run authorized. P1-14C not started.**

## 10. Files & traceability

- Changed: `src/microstructure_probe/netprobe.py` (paths, heartbeat, bytes, host, warning),
  `src/microstructure_probe/probe.py` (receipt stamps, classifier, health block, byte counters,
  host sampling), `src/microstructure_probe/telemetry.py` (CPU/RSS helpers),
  `tests/test_netprobe.py`, new `tests/test_host_telemetry.py`, this report.
- Updated: `CURRENT_STATE.md`, `TASK_QUEUE.md`, `FEATURE_BACKLOG.md` (F-P14A-01),
  `DECISIONS.md` (append-only), `ARCHITECTURE.md` (netprobe + health rows).
- `PROSPECTIVE_EVALUATION_SPEC.md` / `SUCCESS_GATES.md`: intentionally unchanged (no contract
  or gate-advancement change — that IS the correspondence).
- Evidence (uncommitted, preserved): `logs/probe-runs/probe-20261010T110753Z.log`,
  `logs/netprobe/` (operational pair + Exp A/B/C), `data/microprobe.db` (57/202).
  Temp scripts deleted. No logs/DB/captures committed; no secrets anywhere.
