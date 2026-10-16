# Engine + dataset inventory for entry/exit evaluation (offline, 2026-10-16)

Status: INVENTORY + MECHANICAL PREP ONLY. No validation, no economics,
no threshold work. The H-mapping used below is PROPOSED
(`PROPOSED-P1-11C-map-v1`, caller-declared, NOT approved); H3 keeps its
canonical bearish-continuation meaning (never redefined as recovery).

Engine reused as-is: `src/microstructure_probe/backtest_offline.py`
(`backtest-offline/v4.2`) + `scripts/run_family_evaluation.py`
(per-group replay, dev/OOS split, cost scales, manifest). No engine
change was needed or made.

## Fitness matrix: capability / source / missing / acceptance

| # | Aspect | Existing capability | Available source | Missing / exclusion | Acceptance for eval |
|---|---|---|---|---|---|
| 1 | H1 bullish continuation | Engine replays H1/H1-v1; runner `continuation` group | 832 trio P1-11C instances via PROPOSED map (MOMENTUM_UP, EXTENDED_GAINER) | Mapping approval; proxy (not live) formation | Mechanical prep only |
| 2 | H2 exhaustion/reversal + bounce variant | Engine H2/H2-v1 + H2-v1-rebound; runner `correction-*` + `rebound-variant` groups | 9+5 FAILED_* instances via PROPOSED map | Rebound group EMPTY (0 events): variant untestable on this export; mapping approval | Prep only; rebound excluded until sourced |
| 3 | H3 bearish continuation (not recovery) | Engine H3/H3-v1; runner `bearish-continuation` | 712 trio instances via PROPOSED map | Mapping approval | Prep only |
| 4 | Causality / data availability | Per-settlement causal prefix (R9), close-known rule, gap-first, MFE/MAE on demonstrated prints | Closed klines only (trio 15m x2879/symbol + 1h/1m coverage listed in §A) | Intra-candle timing never attributed (by design); availability proof (query != tradable time) absent | Mechanics hold; availability stays UNKNOWN |
| 5 | Entry | Next-known-open fills from event time, deterministic order | Caller-declared event_time + reference_price | Live signal formation (no caller = no entries; runner invents none) | Prep only |
| 6 | Stop | Distance stop on known ranges, gap exits at open | Same candles as entry | Stop methodology itself unvalidated | Prep only |
| 7 | Time exit | Horizon exit (default 1h), open_at_end marks (never executed) | Config knob, not data | Horizon choice unvalidated | Prep only |
| 8 | Size / open positions | Fixed notional, max_concurrent, partial-fill caps, overlap skips (counted) | Knobs, not a sizing model | Sizing engine, portfolio overlap: absent | Single-position mechanics only |
| 9 | Fees/spread/slippage/funding/fills | fee_bps/spread/slippage knobs + cost scales; realized funding calendar OR labeled synthetic fallback; fills at known opens | ASSUMED knobs (5/1/2bps, funding 1bps/8h); NO measured costs; NO fundingRate history ingested | Measured costs UNKNOWN; realized funding calendar UNKNOWN (acquisition contract §B) | Prep with assumed costs, explicitly labeled |
| 10 | Dev/OOS + purge | split_by_time by event_time, cutoff reported | Median event cutoff (1790010000000 here) | NO purge/embargo (documented in engine + runner blockers); 1h horizons overlap dense 15m events (overlap skips counted, not purged) | Split mechanical only; OOS not defended |
| 11 | Selection bias | Runner replays caller events verbatim; mismatches counted | Retrospective P1-11C instances (2831) + prospective setups (66, unused here) | Winner/loser retrospection guard: absent; prospective forward outcomes exist but unwired to this runner | Stated exclusion; no bias correction claimed |

## §A retained price coverage (read-only audit 2026-10-16)

Regular klines (OHLCV): BTC/ETH/SOL 1h x719 + 15m x2879, BTC 1m x4319,
MINA/NMR/ORCA 1h x719; window ~2026-09-07..2026-10-07. Mark klines
(no volume): trio 1h x719. The klines table carries venue
close_time per candle: the adapter exports it as close_time_ms
(engine Candle carries it as provenance only; close/high/low
knowledge still derives exclusively from the next-open rule).
Contract audit on the trio 15m export (8637 candles): 0 null
close_time, 0 close_chain_violations (no close_time past the next
open). Units: ms epoch times, USDT-quoted prices, no volumes.
as_of_ms (dataset knowledge frontier: only close_time <= as_of
exported) is recorded SEPARATE from cutoff_ms (dev/OOS event-time
split): the two must never be confused.

## §B funding acquisition contract (missing piece)

To replace the synthetic interval fallback with realized accounting,
each future holding needs: (symbol, settlement_ms, rate_bps realized)
from the venue fundingRate history, versioned + sourced per calendar
contract (`FundingCalendar.version/source/interval_ms/symbol`).
Until ingested: funding stays synthetic-fallback (labeled) or the
position is flagged funding-unknown. No rate is ever invented.

## §C mechanical prep run (isolated temp, 2026-10-16)

Adapter: `scripts/export_engine_inputs.py` (read-only canonical DB
-> temp JSON: 8637 candles, 1558 events, 1273 non-trio filtered,
mapping + direction convention echoed, `meta.json` with SHAs).
Runner: `run_family_evaluation.py` on the export, cutoff
1790010000000, formation `PROPOSED-P1-11C-map-v1`.
Causal regression (new, `IntraCandleCausalityTest`): an event
1ms inside a 15m candle fills at the next known open (never the
enclosing open/close), never stops on its low, never harvests its
high — with a negative control against each lookahead reading;
`_load_candles` preserves open_time_ms + close_time_ms and the
carried close_time provably never enters `input_hash`.
Envelope: input_hash `1358c7f05ee8474b`, 6 groups x dev/oos x 3
cost scales, 692 trades @1x. Mechanics (NOT economics):
dev 778 / oos 780 events; n_mismatched 0; n_expired 0;
skipped_overlap heavy in dense groups (continuation 271+220,
bearish 178+197: 1h horizons over 15m-spaced events under
max_concurrent=1); rebound-variant 0 events (excluded, see row 2);
baseline pooled reference empty (needs explicit events).
Economic fields (expectancy, totals, drawdown, MFE/MAE) were
computed by the engine but are WITHHELD here: unapproved mapping +
assumed costs + no purge + synthetic funding = no reading permitted.
Limitations: PROPOSED map unapproved; costs assumed; funding
synthetic; no purge/embargo; no availability proof; selection
retrospective; rebound + baseline empty.

## What can be evaluated next vs missing datum

- CAN (mechanics, after mapping approval): per-group replay
  throughput/discards/versions on retained klines via the adapter.
- MISSING for any entry/exit reading: (a) approved H-mapping,
  (b) realized funding calendar (§B), (c) measured cost basis,
  (d) purge/embargo design, (e) availability proof.
  Next concrete work (on instruction only): ingest fundingRate
  history per §B, then re-run prep with calendar attached.
