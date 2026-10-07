# HISTORICAL_RESEARCH_PLAN

Future phases P1-11B (Historical Data Foundation) and P1-11C (Historical
Event Studies). Design only — NOT implemented in P1-11A. No backfill was run.

## P1-11B — Historical Data Foundation — IMPLEMENTED (PASS 2026-10-07)

Separate research store `data/historical/historical.db` (git-ignored;
never the live `data/microprobe.db` — constructor refuses it), schema v1:
`history_meta`, `historical_klines` (WITH volume fields), separate
`historical_mark_klines` (NO volume columns by schema — provenance is
structural), `historical_oi` (as-served sumOpenInterest/sumOpenInterestValue
+ ts), `historical_coverage` (requested/actual start, first/last open,
expected/actual, ratio), `historical_ingestion_runs` (append-only ledger),
`historical_gaps` (UNKNOWN/GAP ranges).

Client (`history_client.py`, stdlib urllib): conservative assumed weights
(klines/mark 10, aggTrades 20, oi_hist 5, exchangeInfo 20) + adaptive
`x-mbx-used-weight-1m` hard pause at 2000/2400 pool; retries 5xx+network
(budget 5, exp backoff 1–16s + jitter); 429 honors Retry-After (budget 2,
then abort); 418 aborts immediately. Forward pagination by
last_open + interval (overlap raises, skips recorded); OI paginated by
timestamp; aggTrades fromId helper (recent-only, not stored).

Ingestion (`history.py`): resume from coverage last_open; listing-aware
earliest-bar probe (startTime=0, no endTime) with requested/actual start
recorded (measured geneses: BTC klines Sep-2019, ETH 2020, SOL 2020,
MINA Feb-2023, ORCA Dec-2024); CLOSED candles only (partial final excluded,
never stored); quality validation (expected/actual, duplicates, missing
grid ranges → gaps table, malformed OHLC, non-positive, high<low,
o/c-outside-h/l, misaligned close_time, future ts). No zeros, no
forward-fill, no interpolation — P1-11C excludes events spanning gaps.

CLI: `status` / `fetch` / `verify` with safe defaults (explicit symbols,
7d, 25 requests; no bulk mode exists). Machine APIs: `/api/history/status`
+ `/api/history/:symbol` (404 when empty/unknown, 400 malformed) and a
small HISTORICAL COVERAGE card on `/symbol/:symbol`.

Pilot (bounded, ~35 requests total): 1h×30d klines ×5 syms (719 bars each,
ratio 1.0, 0 gaps), 15m×30d ×3 (2879 each), 1m×3d BTC (4319), 1h×30d mark
×3 (719 each), 5m×7d OI BTC (500 rows = availability cap, ~41.6h span),
aggTrades shape probe (recent-only confirmed). Resume re-run wrote 0 rows
in 1 request (idempotent). 13 series, all coverage ratio 1.0.

Storage reality (measured row ≈200B incl. index): 1m×90d ≈129.6k
bars/symbol → ~26MB/symbol; ×500 syms ≈13GB — NOT adopted. Tier policy:
ALL eligible: 1h (1–2y) + 4h/1d full life (~1.5–3GB at 500 syms);
research universe (~50): +15m×1y (~350MB); HOT/LIVE (~10): +1m×90d
(~260MB) +5m×1y. Start smaller; expand per P1-11C need.

Prospective microstructure retention (design, not enabled): flow 1m+
buckets long-term (1440/day/symbol) with 10s trailing 7d only; book 1m
snapshots (spread/imbalance/microprice/conc/integrity ≈100B →
1440/day/symbol ≈ 50MB/y/symbol). Estimates before enabling; nothing
auto-retained.

Fidelity contract: mark klines ↔ live mark returns (best match); regular
taker-buy volume = flow proxy/context, NOT identical to the live aggTrade
engine; OHLC cannot reconstruct books (no historical book — depth REST is
present-only); 5m OI cannot recreate 1m live OI (and only ~42h exists).

BTC readiness: time-aligned lookup by (symbol, interval, open_time) serves
token+BTC bars at T without lookahead (relative return, correlation,
beta, lead/lag — models NOT built). Level queries (30d/90d/1y/prev
day/week/month highs-lows, distances, percentiles) are PK-efficient —
targets NOT predicted.

## P1-11C — Historical Event Studies (planned)

Event formation with NO lookahead: an event is defined at time T using only
data ≤ T (returns/velocity/flow/book/OI/structure/BTC context as validated
in P1-11A). Outcomes measured forward from T:

- Fixed horizons: 1m / 3m / 5m / 15m / 30m / 1h (mark-price log return sign
  and magnitude).
- Path outcomes: MFE / MAE / time-to-MFE / time-to-MAE / invalidation time
  (invalidation = first touch of a pre-declared level fixed at T, e.g.
  back-through-VWAP or swing break — never refit after seeing the path).

Candidate event families (hypotheses, not signals): extended-gainer
continuation vs exhaustion, buy/sell absorption (see
`docs/SIGNAL_RESEARCH_PLAN.md`), velocity-deceleration + failed-high,
VWAP-loss after aggressive-buy dominance, OI-regime flips, book-imbalance
persistence. Each family needs a pre-registered definition + minimum sample
size before any confidence is quoted.

## What current data already supports

- 10s mark-price buckets with honest gaps (grid fill measured 31.7% in a
  degraded window) — the event clock and return math already handle sparsity.
- Completed-bucket-only baselines and tolerance anchors — reusable unchanged
  on historical bars.
- UNKNOWN-first rendering — event studies must keep, not impute.

## What is still missing (P1-11C must build on P1-11B)

- P1-11C event definitions + outcome measurement (planned, not started).
- Retained per-trade flow history (only aggregates + 600 bounded buckets
  per size/symbol persist live) — absorption-threshold stability needs
  denser retained flow or re-derivable bucket detail.
- Book depth history (latest snapshot only) — resilience/recovery-time
  metrics need a new retained series (prospective recorder designed
  above, not enabled).

## P1-11C implementation (2026-10-07, PASS)

- Engine src/microstructure_probe/events.py: T-formation / T+outcome split, mark-vs-regular labeling, fixed 1m�1h horizons, direction-oriented MFE/MAE + time-to, predeclared invalidation, COMPLETE/PARTIAL/INVALID_GAP/INSUFFICIENT_HISTORY, BTC sync + relative return, as-of 30d levels, HISTORICAL_TAKER_BUY_PROXY + ABSORPTION_PROXY labels, quantity-only sample tiers.
- Six versioned HYPOTHESIS families; CLI events definitions|run|summary; 38 bounded pilot runs stored (see CURRENT_STATE for counts; sub-1h-on-1h resolution limit documented).
- Prospective recorder esearch_recorder.py ENABLED inside MarketProbe (flow 10s/1m, book 1m; 7d/90d/90d retention; ~200B/row estimate); replaces the 'not enabled' design note above � the retention-gap items (per-trade flow, depth history) are now covered prospectively, never historically fabricated.
