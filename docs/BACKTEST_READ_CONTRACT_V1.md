# Backtest read contract v1 (Etapa 4 prep — UNWIRED)

Purpose: let a future Dashboard V2 System/Research panel consume offline
backtest results WITHOUT touching the engine. Nothing serves this schema
yet; no route, no UI change, no fictitious results are connected.

## Result envelope (`backtest_result/v1`)

Produced by `backtest_offline.run_backtest` (`ENGINE_VERSION =
backtest-offline/v1`). All money in USDT; all times integer ms.

| Field | Type | Nullability | Meaning |
|---|---|---|---|
| `engine_version` | string | never null | `backtest-offline/v1` |
| `config_hash` | string(16) | never null | sha256 of the config JSON, truncated |
| `config` | object | never null | full `BacktestConfig` (family, rules_version, horizons, stops, all cost bps, cost_scale, caps) |
| `dataset_id` | string | never null | dataset identity (`synthetic-fixture` until a versioned dataset exists) |
| `segment` | `dev`\|`oos` | never null | temporal segment of the events replayed |
| `label` | string | never null | interpretation guard; fixture runs carry `MECHANICS-SMOKE — fixture replay, NOT performance` |
| `n_events` / `n_trades` / `skipped_overlap` | integers | never null | flow accounting; overlaps are SKIPPED and counted, never stacked silently |
| `expectancy_net` / `expectancy_gross` | float | never null | mean per-trade net/gross, costs as configured |
| `total_net` / `total_fees` / `total_funding` | float | never null | additive cost split |
| `max_drawdown` | float ≥ 0 | never null | peak-to-trough on the net equity curve |
| `mfe_mean` / `mae_mean` | float % | never null | excursion means over trades |
| `exit_reasons` | {horizon, stop} | never null | closing-reason histogram |
| `equity_curve` | float[] | never null | cumulative net per trade, in execution order |
| `trades` | array | never null | per-trade: symbol/direction/event/entry/exit ms, entry/exit px, gross/fees/funding/net, mfe/mae %, exit_reason, fills |

## Sensitivity envelope

`run_sensitivity` returns `{engine_version, dataset_id, segments:
{dev: {"1.0"|"2.0"|"3.0": <result>}, oos: {...}}}` — dev/OOS split at the
median event time, cost scales 1x/2x/3x. Same per-result schema above.

## Consumer rules (binding on any future integration)

- Render `label` verbatim next to every number; fixture-labeled results
  must never appear under a performance heading.
- Costs shown must come from the result's own `config`; never substitute
  live fee schedules silently.
- `dataset_id == synthetic-fixture` results are MECHANICS proofs only.
- Timestamps are observation/event times; read time is never evidence.

## Status

UNWIRED on purpose. Wiring needs: a versioned real dataset id, an
authorized study run, and frontend review of the exact backend SHA.
