# Backtest read contract v2 (prep — UNWIRED)

Purpose: let a future Dashboard V2 System/Research panel consume offline
backtest results WITHOUT touching the engine. Nothing serves this schema
yet; no route, no UI change, no fictitious results are connected.
Supersedes the v1 draft (engine `backtest-offline/v1` never ran on real
data; v2 mechanics differ — see P1 corrections evidence).

## Result envelope (`backtest_result/v2`)

Produced by `backtest_offline.run_backtest` (`ENGINE_VERSION =
backtest-offline/v2`). All money in USDT; all times integer ms.

| Field | Type | Meaning |
|---|---|---|
| `engine_version` | string | `backtest-offline/v2` |
| `config_hash` | string(16) | sha256 of the config JSON, truncated |
| `config` | object | full `BacktestConfig`, incl. unsupported knobs (always null in a valid run) |
| `dataset_id` / `input_hash` | strings | caller dataset label + sha256 of the canonical event/candle tuples replayed |
| `segment` | `dev`\|`oos` | temporal segment (split by event time) |
| `label` | string | interpretation guard; fixture runs carry `MECHANICS-SMOKE — fixture replay, NOT performance` |
| `limitations` | string[] | unmodeled effects (latency, tick/lot, min-notional, realized-only drawdown, single funding rate, event-time OOS split) |
| `drawdown_scope` | string | `realized-only` (mark-to-market explicitly NOT modeled) |
| `n_events` / `n_trades` / `skipped_overlap` / `n_expired` / `n_mismatched` | integers | flow accounting: overlaps skipped, out-of-window events expired, family/version mismatches skipped — all counted, never silent |
| `expectancy_net` / `expectancy_gross` | float | mean per-trade net / pure-price-gross |
| `total_net` / `total_fees` / `total_funding` | float | additive splits |
| `max_drawdown` | float ≥ 0 | peak-to-trough on realized net equity |
| `mfe_mean` / `mae_mean` | float % | over closed trades, usable candles only |
| `exit_reasons` | {horizon, stop, open_at_end} | closing-reason histogram; `open_at_end` trades carry per-trade `open_at_end: true` + `cancelled_notional` |
| `equity_curve` / `trades` | array | cumulative net; per-trade: symbol/direction/family/rules_version, event/entry/exit ms (`exit_ms` ≥ `entry_ms` always), entry_px = cost/qty average, filled_qty/filled_cost, gross_pnl (price only), spread_slip_cost/fees/funding/friction/net, mfe/mae %, exit_reason, fills |

Causality guarantees a consumer may rely on: fills sequential in time;
stops evaluated against the position as of each candle; stop fills at the
stop price when the level traded else at the candle open (gap); candle
high/low/close only usable once known within the horizon; overlapping
capacity commits at signal time.

## Sensitivity envelope

`run_sensitivity` returns `{engine_version, dataset_id, input_hash,
cutoff_ms, segments: {dev: {"1.0"|"2.0"|"3.0": <result>}, oos: {...}}}`.

## Consumer rules (binding on any future integration)

- Render `label` + `limitations` verbatim next to every number;
  fixture-labeled results must never appear under a performance heading.
- Costs shown must come from the result's own `config`; `funding` is
  direction-signed under a single-rate assumption (see limitations).
- `dataset_id == synthetic-fixture` results are MECHANICS proofs only.
- Timestamps are observation/event/knowledge times; read time is never
  evidence. `exit_ms` is a knowledge/decision time, not a tick time.

## Status

UNWIRED on purpose. Wiring needs: a versioned real dataset id, an
authorized study run, and frontend review of the exact backend SHA.
