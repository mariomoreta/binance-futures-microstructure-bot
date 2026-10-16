# Hypothesis → engine mapping CANDIDATE (research only, NOT approved)

Version: `PROPOSED-P1-11C-map-v1` (unchanged semantics, versioned here as
`MAP-CANDIDATE-v1`). Status: caller-declared research candidate. It is NOT
an approved methodology, NOT a signal definition, and NOT statistically
validated. No threshold was optimized against any evaluation set in this
task (engine defaults untouched; see §5).

Originals: P1-11C descriptive families in
`src/microstructure_probe/events.py` (`EVENT_FAMILIES`, `default_definition`
v1, `DESCRIPTIVE_RESEARCH_ONLY_HYPOTHESIS`); study hypotheses H1/H2/H3 in
`docs/RESEARCH_BACKTEST_CONTRACT_ETAPA3.md`. This file maps the former onto
the latter for MECHANICAL replay only.

## Retrospective-label audit (binding)

P1-11C formation (`formation_features`, `detect_events`):

- `event_time` = OPEN time of the formation bar (the last closed bar at/before
  the scan index). The firing condition needs that bar's CLOSE, so the
  condition is knowable only at the bar's `close_time` (next same-symbol
  open on an intact chain). It is NOT knowable at `event_time`.
- `direction` (`up`/`down`) = side of the already-realized drift used by the
  descriptive definition (e.g. prior 24h/1h return sign, accel-proxy sign).
  It is a retrospective descriptor, NOT a live signal available at the
  instant. Nothing in P1-11C proves a live detector could have fired there.
- `reference_price` = formation-bar close (mark preferred, labeled). Known
  only at `close_time`. The engine never fills at this price.

Engine consequence (verified in `backtest_offline.py::run_backtest`): fills
occur at the first candle with `open_time > event_time_ms`, i.e. exactly the
formation bar's close moment on an intact chain. The replay is therefore
causally aligned (entry at first knowable instant), PROVIDED the chain holds
(close_time <= next open; 0 violations on trio 15m, see dataset manifest).
Per-operation proof for the V1 evaluation window: `docs/evidence/
OFFLINE_EVAL_AUDIT_V1.json` conserves `formation_time_ms` (= event_time),
`available_at_ms` (= formation-bar close_time) and `entry_time_ms` for all
1412 trades — 1412/1412 with entry >= available (gap uniformly 1ms), 0 null.
`reference_price` is metadata only; entry price is the next open. Any gap
between formation close and next open is handled gap-first by the engine
(exit at open, no upgrade on recovery).

What the mapping does NOT claim: live-signal availability (no formation
proof from streaming features exists — availability stays UNKNOWN per the
inventory), statistical independence (grouped/overlapping events are
correlated by construction; dense 15m events under 1h horizons overlap —
overlap is counted via `skipped_overlap` under `max_concurrent=1`, never
purged by the engine), or trade direction validity (direction preserved
verbatim from the descriptive label; see per-family notes).

## H1 — bullish continuation (LONG)

- Source definitions: `MOMENTUM_ACCELERATION_UP`, `EXTENDED_GAINER`
  (descriptive `direction = up` → engine `LONG`).
- Engine group/family: `continuation` / `H1` / `H1-v1`.
- Knowable instant: formation-bar `close_time` (≈ next 15m open on trio).
- Entry reference: next known open (engine fill; never `reference_price`).
- Invalidation/stop (mechanical placeholders, unvalidated): 0.5% distance
  stop on known closes, gap-first at open; study invalidation per Etapa-3
  contract (level loss on closed bars, opposite REVERSAL x2, UNKNOWN/stale).
- Horizon: 1h time exit (engine default; unvalidated choice).
- Required data: closed trio 15m klines with intact close chain; symbol
  subscribed in replay (BTC/ETH/SOL).
- Exclude when: chain violation at formation, symbol missing from candles,
  `formation_gap` rows (kept out of statistics, never deleted), funding
  calendar missing for the symbol (position flagged funding-unknown unless
  a realized calendar is attached — in this task all three symbols carry
  one), costs unmeasured (results are cost-conditioned, never measured).

## H2 — exhaustion / reversal (includes bounce variant)

- Source definitions: `FAILED_HIGH_CANDIDATE` → `correction-exhaustion`
  (`H2`/`H2-v1`); `FAILED_LOW_CANDIDATE` → `correction-reversal`
  (`H2`/`H2-v1`). Descriptive direction preserved verbatim
  (`FAILED_HIGH` = up → LONG; `FAILED_LOW` = down → SHORT).
- CAUTION: preserving the realized-drift side is a mechanical convention,
  not a validated trade direction. A true exhaustion fade would trade
  AGAINST the drift; this candidate does NOT do that and must never be
  read as a fade methodology. Any reading is mechanics-only.
- Bounce variant (`rebound-variant` / `H2` / `H2-v1-rebound`): NO source
  definition exists in P1-11C v1. The group replays EMPTY (0 events) and is
  EXCLUDED as untestable until a bounce definition is specified. Nothing
  was invented to fill it.
- Knowable instant / entry / horizon / exclusions: same mechanics as H1.
- Sample note: trio 15m yields 9 + 5 = 14 events (INSUFFICIENT tier <30 by
  `sample_size_label`). Per-symbol cells are 1–5 events. No conclusion of
  any sign may be drawn; cells are reported for completeness only.

## H3 — bearish continuation (SHORT; NOT loser recovery)

- Source definitions: `MOMENTUM_ACCELERATION_DOWN`, `EXTENDED_LOSER`
  (descriptive `direction = down` → engine `SHORT`).
- Engine group/family: `bearish-continuation` / `H3` / `H3-v1`.
- Separation (binding, from Etapa-3 contract): H3 is DOWN continuation after
  support loss. Loser recovery (down move followed by UP reversal) is a
  DIFFERENT hypothesis belonging to H2's reversal leg. Results are never
  pooled across H2/H3; the runner replays each group under its own contract
  (`GROUP_FAMILY`) and mismatches are counted, never silently pooled.
- Knowable instant / entry / horizon / exclusions: same mechanics as H1.

## Data exigibility per hypothesis (summary)

| Requirement | H1 | H2 legs | H3 | Bounce variant |
|---|---|---|---|---|
| Closed klines, intact chain | yes | yes | yes | yes (if defined) |
| Realized funding calendar | attached (this task) | attached | attached | n/a (excluded) |
| Measured costs | NO → conditioned | NO → conditioned | NO → conditioned | n/a |
| Availability proof | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Min sample (≥30) | met (trio) | NOT met → descriptive only | met (trio) | 0 → excluded |

## Versioning rule

Any change to definition membership, direction convention, or entry timing
forks the version (`MAP-CANDIDATE-v2`). This task performs no such change.
