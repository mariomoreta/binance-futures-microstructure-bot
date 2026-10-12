# P1 — Backtest corrective report (v2 2026-10-12, CORRECTED 2026-10-13 → v3)

Engine: `src/microstructure_probe/backtest_offline.py`
(`backtest-offline/v3`). History preserved: the v2 report below this
addendum claimed sequential causality, horizon closes and open-time gap
fills; independent review (R1–R5) refuted those guarantees with
reproductions. They are WITHDRAWN. The motor is NOT causally verified —
only covered by the regression battery named here. No strategy invented;
H1/H2/H3 entries untouched.

## V2 claims withdrawn

- "Stops evaluated against the position as of each candle" — v2
  consulted low/high before verifying close_time <= horizon (R1).
- "Horizon exits at last close with exit_ms=horizon" — invented an
  executable close at the rule time (R2).
- "Gap exits at open via in-range test" — a recovering range masked the
  gap and improved the fill retrospectively (R3).
- "Fills then stop-check per candle" — a new fill could dilute the
  average and dodge the existing stop (R4).
- "MFE/MAE over usable candles" — the break ran before metrics, leaving
  mae 0 on stop exits, and extremes were credited without order (R5).

## V3 policies (chosen, tested, labeled)

- R1 knowledge times: OPEN known at open_time; high/low/close ONLY at
  close_time (next same-symbol open, else UNKNOWN; a following open never
  proves the prior candle's duration). Stops/metrics/exits consume a range
  only when close_time is known AND <= horizon_end.
- R2 marks vs executions: candles past the window contribute nothing. Data
  past the window → rule closes, marked at last knowledge (reason
  "horizon"). Data ended first → OPEN position marked at last known
  price/time (reason "open_at_end", flagged). No invented duration,
  funding, close, or capacity release beyond knowledge.
- R3 gap-first: existing position resolves against the KNOWN open before
  any fill; open through the stop exits AT the open (LONG and SHORT,
  recovery or further traversal irrelevant afterwards).
- R4 ordering per candle: (1) resolve existing stop on the open, cancel
  remainder on exit; (2) new fills only while open and in-window, with
  recomputed average/stop from that moment; (3) range evaluation only on
  known closes. Capacity intervals commit at signal time.
- R5 metrics: MFE/MAE from demonstrated prints (prior candles + current
  OPEN while holding); favorable extremes excluded (order unknown); the
  exit move always feeds MAE. Documents what stays unknown intra-candle.
- Unchanged and re-verified: P1.1–P1.7 mechanics, expiry counting,
  overlap skips, quantity accounting (price vs friction), signed funding
  (single-rate limitation kept), realized-only drawdown, mismatch
  skip+count, unsupported-knob rejection, input_hash + cutoff_ms.
- cutoff_ms is REPORTED, not credited: it does not purge overlaps and
  does not validate OOS. OOS by event time stays a documented limitation.

## Regression evidence

`tests/test_corrective_r1r7.py` (21 tests): 17 FAIL + 1 ERROR + 3
documented guards (boundary usability, empty-series expiry, safe-open
fill) on pristine 906c271; 21/21 PASS on v3
(`docs/evidence/CORRECTIVE_R1R7_FAIL_BEFORE_906c271.txt`,
`CORRECTIVE_R1R7_PASS_AFTER_v3.txt`). Prior battery
(`test_backtest_offline*`, 26 tests) still green.

## Scope after v3

Chronological replay under the availability contract above;
reproducible (config/input hashes); fixture smoke only. Still NOT
validation: no real dataset run, no OOS evidence, no venue-measured
costs, no signals. Read contract v3, still UNWIRED.
