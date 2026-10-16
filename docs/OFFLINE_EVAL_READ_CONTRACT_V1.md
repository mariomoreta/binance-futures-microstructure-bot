# Offline-eval read contract v1 (`offline-eval/v1`)

Extension (explicit) of `docs/BACKTEST_READ_CONTRACT_V1.md`: that contract
covers single `run_backtest` result envelopes. This contract covers the
AGGREGATED multi-symbol evaluation artifact consumed by Dashboard V2.
Nothing here executes, signals, or paper-trades.

## Artifact (`frontend/src/data/offline-eval-v1.json`, versioned)

- `schema_version: 1`, `artifact_version: "OFFLINE-EVAL-V1"`,
  `engine_version: "backtest-offline/v4.2"`,
  `formation_method: "PROPOSED-P1-11C-map-v1 (caller-declared, NOT approved)"`.
- `cutoff_ms` (global event-time frontier) + `horizon_ms` (1h purge horizon).
- `cost_assumption` (COST-ASSUME-v1: fee/spread/slippage assumed + scales).
- `symbols{}`: venue/interval/candles/window/chain checks/event counts/
  input hashes/purge selection/funding calendar identity per symbol.
- `cells[symbol][group][segment][scale]`: flow (events→trades→overlap→
  expired→mismatched), realized/open split, exit reasons, gross/net/fees/
  funding splits, realized drawdown, MFE/MAE, config hash, funding quality.
- `pooled_reference[segment][scale]`: arithmetic sums over directional
  groups (NOT a strategy, NOT a benchmark).
- `limits[]`: rendered verbatim by any consumer.

## Adapter (`frontend/src/lib/offline-eval.ts`, read-only)

- Parses + validates the bundled artifact only. No engine import, no DB,
  no network, no mutation. Unknown schema → `UNSUPPORTED_OFFLINE_EVAL_SCHEMA`;
  missing/corrupt → `OFFLINE_EVAL_UNAVAILABLE` (never fabricated).
- `GET /api/v1/offline-eval` serves the parsed view-model `no-store`;
  503 with `available:false` when the artifact cannot be parsed.

## Consumer rules (binding)

- Render `label` + `limits` verbatim; H2 cells carry their INSUFFICIENT
  sample fence; rebound/baseline EMPTY cells render as excluded/empty.
- Realized-only metrics primary; legacy totals that include open marks are
  never cited as performance (the artifact exposes both; the UI shows
  realized with the open count beside it).
- Costs from the artifact's own `cost_assumption` only; labeled assumed.
- No execution buttons, no tradable signals, monitor controls untouched.

## Status

WIRED read-only in this task: artifact + lib + route + research-page
section, covered by `frontend/src/test/offline-eval.test.ts` (+ route test) and the
page's existing visual QA. Regenerating the artifact requires re-running
the documented offline pipeline (exporter → selection → runner →
`scripts/aggregate_offline_eval.py`); the artifact hash pins the exact
run. The artifact file itself is committed (force-added past the `data/`
ignore) so clean checkouts build and test without it being generated;
a clean checkout CANNOT regenerate it from scratch (canonical
`data/historical/historical.db` unpublished — see the dataset limitation
in `docs/OFFLINE_EVAL_REPORT_V1.md` §10).
