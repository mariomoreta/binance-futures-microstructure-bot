# P1-14B.5 — Transport Resilience & Independent Network Diagnostics Report

**Mode:** AUDIT → MEASURE → REPRODUCE → CORRECT → TEST → CONTROLLED VALIDATION → DOCUMENT → COMMIT → STOP
**Date:** 2026-10-10
**Branch:** `phase1/market-intelligence-dashboard`
**Starting SHA:** `0df2170a273567c708dc1c0f3b0661ab9ba5eece`
**Baseline validated pre-run:** schema v9, 24 setups, 99 COMPLETE outcomes, 0 dupes (identical to P1-14B.4 state).
**Safety:** `BOT_MODE=observe` end-to-end; 0 keys / 0 orders / 0 capital. V2 worktree/ports and `main` untouched.

---

## 1. Root cause (confirmed) and uncertainties (stated)

P1-14B.2/3 episodes: host-external delivery stall (bookTicker p95 0.4 s → 375 s with sub-ms
processing, rate collapse without drain spike, stable clock syncs, worst stall on a
zero-reconnect connection), then handshake-timeout path outage. Local backlog, clock skew, and
HOT logic were discarded with evidence in P1-14B.3. **Provider-internal vs ISP-path remains
unseparated** — no prior vantage point could distinguish them, which is what the independent
reference below resolves to the extent possible: tonight, with identical code/config/host, NO
episode reproduced in 35 + 40 coincident minutes. A persistent host defect or bot defect is
therefore DISCARDED (same host, same binary paths, perfect health); the episodes are
INTERMITTENT path/provider instability. Which of the two (Binance edge vs ISP route) produced
the stalls is still UNKNOWN — reported as uncertainty, not forced.

## 2. Independent probe (implemented, tested, run — verified capability)

`src/microstructure_probe/netprobe.py` (stdlib + existing `websockets` dep; no new dependencies):
single reference connection to `wss://fstream.binance.com` (host pinned; non-public streams
refused by allowlist; read-only — protocol frames only), default streams `btcusdt@bookTicker` +
`!markPrice@arr@1s`, connection parameters mirrored from `probe.py` (timeouts/backoff/queue) so
timing differences isolate host/process variables. Records per message: receive wall time,
exchange E, lag, E-reorders, inter-arrival gaps; per-run: DNS timing, handshake timing,
disconnect/reconnect/error classes, host snapshot. UTF-8 JSONL, unique paths, never truncates;
bounded `--duration` (60–3600); exit 0 on duration-reached. 17 deterministic tests (faked
transports/clocks; stale/silent/handshake-failure/backoff-bounds coverage). Reuses
`RunningDistribution` (identical quantile semantics to the bot) and imports the shared
`classify_connection_health` (single source of truth).

**Tool limitation (honest):** on the bare `/stream` combined path the `!markPrice@arr` array
delivered zero messages in 40 min while bookTicker flowed perfectly — a subscription-path
limitation of the tool (bot's `/market/stream` path serves the array fine; bot-side markPrice
lag stats prove it flowed during the same window), NOT a Binance-health signal. Reference
coverage is therefore bookTicker-only until the tool learns per-path stream placement. No
Binance Spot/COIN-M limits imported; thresholds used are LOCAL_POLICY, documented in code.

## 3. Coincident comparison (bot 03:45–04:20Z vs reference 03:45–04:25Z)

| Signal | Bot (engine) | Reference (independent) | Reading |
|---|---|---|---|
| bookTicker p50 | ~170–187 ms | ~317–375 ms | same sub-second regime (≈150–190 ms inter-connection variance is normal; a 1:1 match would be suspicious) |
| bookTicker p95 | ~217–389 ms | ~345–380 ms | same regime |
| bookTicker max | 4636 ms (single) | 777 ms | both rare-outlier grade |
| markPrice | p50 ~243 ms, p95 ~289 ms, flowing | absent (tool limitation §2) | healthy per bot; no reference claim |
| rejects | 0 (0.00 %) | max lag 777 ms « 5000 ms guard | consistent |
| reconnects / disconnects | 0 / 0 | attempts 1, errors {} | consistent, path stable |
| E-reorders | n/a | 0 | consistent |
| max inter-arrival | cadenced-normal | 919 ms | consistent |

DNS pre-check 8.3 ms; handshake clean; HOT resync mid-run exact (KAIA/MAGIC/USUSDT).
**Attribution verdict:** full agreement on a healthy path — the episode signature did not
reproduce; no host/process fault exists to find tonight.

## 4. Layered diagnosis (host / transport / engine / data)

- **Host:** w32tm unsync-flag persistent but self-syncing on schedule (last sync Oct 9 21:53 local);
  offsets +322 ms (this task) — sub-second, stable; no resync action (documented, repeated).
  CPU/mem per-process and NIC utilization: NOT captured by probe (stated gap since P1-10; startup
  RSS only). No suspension evidence (summary cadence unbroken across all runs). DNS healthy
  (8.3 ms reference resolution; handshake timeouts were post-TCP, i.e. non-DNS).
- **Transport:** handshake TimeoutErrors = path/server slowness (TCP connected, WS handshake stalled
  >15 s); ping 180 s/timeout 600 s leaves silent-dead sockets to the watchdog (by design now);
  error retries bounded 1→30 s, never aggressive (max observed 2 forced + error bursts with
  growing backoff).
- **Engine:** processing sub-ms typical; queues 0/0; inflight ≤8; rejects counted per stream;
  consecutive-run behavior identical (deterministic replays in tests).
- **Data:** this run — markPrice/bookTicker/aggTrade/depth all fresh all run; 0 gaps reported;
  forceOrder event-correct silence; prospective preserved (below).

## 5. Watchdog audit (10/10 verified: code + P1-14B.3 live log)

1. Last received: `last_seen_monotonic` per stream (NEW P1-14B.5 wall parallel `_last_receipt_wall_ms`).
2. Last accepted: `_last_accepted_ms` per stream (post-guard only).
3. Last real update: accepted-with-E via lag distributions + freshness block.
4. Trigger: zero accepted traffic beyond 90 s (300 s hot-market) — fired live 5× with correct ages.
5. Grace: 120 s connection-age — hot tasks (spawned 06:15:58) first eligible ~06:17:58, fired next cycle.
6. Cooldown: 120 s/connection — market/public fires 292 s apart; no refire inside any window.
7. Canonical retry path: break → attempts/successes (attempts 1→2 both, ~12 s recovery, 5 min zero rejects).
8. HOT exact restore: URL callable + resync sets exact; post-reconnect streams flowed with accounting.
9. No aggressive loops: max 2 fires/connection/17 min + error-backoff 1→16 s; bounded counts.
10. Total outage: fires consumed, retries exhausted against refused handshakes, no tight loop, no tight-loop risk by construction (cooldown + backoff + bounded duration).

## 6. Observability (additive, diagnostic vocabulary)

`classify_connection_health()` (pure, probe.py): raw `socket` (CONNECTED/DOWN) reported ALONGSIDE
diagnostic `health` (FLOWING_FRESH / FLOWING_STALE / SILENT / RECONNECTING / UNAVAILABLE) with
evidence (last receipt/accepted ms + ages, budget) — open never implies healthy, by construction.
Missing data stays None (never zero-filled). Low-frequency feeds use the long budget (cadence never
assumed). Summary `freshness.connectionHealth` per live connection; netprobe reuses the same
function (comparability). 8 classifier tests. Disjoint by design from P1-12A market states and
P1-13A lifecycles (stated in code + docs).

## 7. Prospective preservation (contract v1.1 + schema v9 intact)

Post-run read-only audit: 49 setups (+25 new, incl. HOT rotation symbols), **150 outcomes (+51),
all COMPLETE, 0 duplicates, 0 anomalies** (no-lookahead + return math on all rows). No PENDING
(marks healthy all run — stale-mark gate untriggered, correct). No INSUFFICIENT (references
present). No state/column/contract change in this task; seen-rebuild + grace + terminality
untouched and green in suite. **All 99 prior rows preserved byte-identical.**

## 8. Tests — 708/708 OK, exit 0 (683 + 17 netprobe + 8 health)

Deterministic, zero live-Binance dependency: target allowlist refusals, error classes,
event-time extraction (dict/array/missing/malformed), tracker (fresh/stale/reorder/silent),
scripted run_reference (fresh/stale/handshake-failure bounded backoff/silent/array stream),
never-overwrite paths, health-state matrix incl. open-but-stale signature, low-frequency
budgets, malformed-input safety. P1-12A/B, P1-13A, and prospective rules untouched.

## 9. Operational validation — the ≥30-min healthy window is DEMONSTRATED

- Preflight PASS (0 procs, 8091 free, registry COMPLETED, SQLite integrity ok, disk 159.7 GB,
  baseline identical, clock +322 ms, no resync).
- 10-min diagnostic gate: netprobe first-10-min pristine (p50 ~320 ms, 0 errors) + bot 0/0/0% →
  committed to the full window per protocol.
- Single ≤35-min run (bot PID 32940, 2100 s, mode observe): **2102.5 s, 20/20 streams, 0
  reconnects, 0 rejects (0.00 %), 0 errors, exit 0 duration-reached** — no abort (no rule
  breached). Reference ran 40 min concurrently (attempts 1, errors {}).
- Post-run: 49/150/0-dupes as above. **HEALTHY_DURATION_SECONDS: 2102.5 (≥30-min target met).**
- No second run (protocol: no auto-repeat).

## 10. Gates

| Gate | Result |
|---|---|
| TRANSPORT_GATE | **PASS** (35 min, 0 reconnects, 0.00 % rejects, reference-agreed) |
| FRESHNESS_GATE | **PASS** (all feeds fresh all run; no stale-mark occasion; classifier live in summary) |
| PERSISTENCE_GATE | **PASS** (integrity ok, 0 errors, 49-key coexistence, bounded logs held) |
| SAFETY_GATE | **PASS** (observe end-to-end, 0/0/0, canonical plane, natural completion, V2/main untouched) |

**Global verdict: PASS (operational)** — the first ≥30-min healthy window with independent-reference
agreement, full prospective integrity, and green suite. This satisfies the P1-14B.1 readiness
blocker #(1) as far as one window can; recurrence risk (3 prior episodes) keeps a repeat
advisable before any 4–6 h authorization, which is still NOT granted here.

## 11. Files & traceability

- New: `src/microstructure_probe/netprobe.py`, `tests/test_netprobe.py` (17),
  `tests/test_transport_health.py` (8), this report.
- Changed: `src/microstructure_probe/probe.py` (receipt stamps, classifier, health block —
  additive only; no engine/guard/backoff/HOT logic touched).
- Updated: `CURRENT_STATE.md`, `TASK_QUEUE.md`, `FEATURE_BACKLOG.md` (F-P14A-01),
  `DECISIONS.md` (append-only), `ARCHITECTURE.md` (netprobe + health rows).
- `PROSPECTIVE_EVALUATION_SPEC.md` / `SUCCESS_GATES.md`: intentionally unchanged (no contract
  or gate-advancement change in this task — that IS the correspondence).
- Evidence (uncommitted, preserved): `logs/probe-runs/probe-20261010T034509Z.log`,
  `logs/netprobe/netprobe-20261010T034516Z.jsonl`, `data/microprobe.db` (49/150).
  Temp scripts deleted. No logs/DB/captures committed; no secrets anywhere.
