# P1 — Backtest corrective report (2026-10-12, engine v2)

Engine: `src/microstructure_probe/backtest_offline.py`
(`backtest-offline/v2`). Prior: 16 tests green but 7 causal/accounting
defects + review gaps. Regressions:
`tests/test_backtest_offline_corrections.py` (10 tests) — all 10 FAILED
(8 failures + 2 errors) on audited SHA bdc9ef2, all 10 PASS after.
Existing 16/16 still green (no silent behavior dependency). Mechanics
only; no strategy invented; H1/H2/H3 entries untouched.

## P1.1 partial-fill causality → sequential positions

Problem: entry was a notional-weighted price average over ALL fills, so a
later fill retroactively moved the entry (100→150) and a stop that fired
at t=1000 (90→135). Fix: fills execute in time order as qty =
chunk/fill_price; stops evaluate against the position AS OF each candle;
a stopped position never takes later fills; unfilled remainder past the
last in-window open is CANCELLED (counted per trade). Evidence: P1.1 test
(1 fill, entry 100, stop 90 @ t=2000 knowledge time).

## P1.2 entry after exit → expiry

Problem: horizon t=500 with first candle t=1000 returned entry_ms=1000,
exit_ms=500. Fix: first fillable open past the horizon (or none) expires
the event — `n_expired` counted, no trade, invariant exit_ms ≥ entry_ms.

## P1.3 concurrency → signal-time capacity

Problem: one `open_until` scalar + `max_concurrent <= 1` gate admitted
unlimited overlap at max_concurrent=2. Fix: open intervals
(event_time → exit_ms); an event is skipped when overlapping intervals ≥
max_concurrent. Capacity commits at signal time, so simultaneous events
compete deterministically. `max_concurrent < 1` rejected.

## P1.4 stops through gaps → conservative fill policy (decision)

Problem: gap candle (all 80) below stop 90 exited at 90 — an unavailable
price. Policy: stop level inside candle [low, high] → fill AT stop;
otherwise gap → fill at candle OPEN (first available). Stop-exit time =
candle close_time when known, else its open (knowledge time, never an
invented tick time).

## P1.5 incomplete fills → keep + flag

Problem: 1000 ordered / 500 filled / series ends → zero trades, filled
qty and costs vanished. Fix: the filled position is kept (qty, costs,
friction on filled notional), closed at the last KNOWN price with
`exit_reason: open_at_end` + `open_at_end: true` + `cancelled_notional`.

## P1.6 OHLC timing → knowledge times (decision)

Problem: a candle opening at t=1000 with close 105 counted its gain at
horizon t=1000. Rule: open known at open_time; high/low/close known at
close_time (next same-symbol open, else unknown). Only candles with
close_time ≤ horizon_end contribute moves/exits/MFE/MAE. Boundary case
exits flat at entry (gross 0, mfe 0).

## P1.7 quantity accounting → cost/qty average

Problem: 500@100 + 500@200 averaged to entry 150 and P&L 333.33.
Fix: filled_qty 7.5, filled_cost 1000, avg 133.33, exit 200 → gross 500.
Price P&L (raw) is now separate from friction (spread/slip drag + fees
on filled notional ×2 + signed funding): net = gross − friction.

## Review items closed

- Funding: signed by direction (LONG pays, SHORT receives at positive
  rate), per full 8h held on filled notional. Single-rate assumption is a
  labeled limitation, not a market claim.
- Drawdown: realized-only (`drawdown_scope`), closed-trade net equity.
  Mark-to-market explicitly NOT modeled (no intra-candle paths).
- dev/OOS: split by event time (documented limitation — OOS exposure can
  stem from dev-timed decisions); `cutoff_ms` now reported; median cutoff
  is deterministic per input set.
- Coherence: (family, rules_version) mismatch → skip + `n_mismatched`
  (never pooled).
- Identity: `input_hash` (canonical event/candle tuples) on every result
  + sensitivity envelope.
- Latency/tick/lot/min-notional: new knobs REJECT with ValueError;
  `limitations` list rides every result. No partial support simulated.
- Single rules version does NOT block validation by itself: it requires a
  frozen traceable version + fit data + defensible temporal split. No
  artificial versions were created to lift any gate.

## Scope after fixes

Chronological causal replay with explicit expiry, overlap, gap, timing
and accounting policies; reproducible (byte-identical reruns,
config/input hashes); fixture smoke only. Still NOT validation: no real
dataset run, no OOS evidence, no costs measured from venue, no signals.
Read contract updated to v2 (still UNWIRED).
