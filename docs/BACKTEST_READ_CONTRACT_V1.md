# Backtest read contract v4 (prep — UNWIRED)

Purpose: let a future Dashboard V2 System/Research panel consume offline
backtest results WITHOUT touching the engine. Nothing serves this schema
yet; no route, no UI change, no fictitious results are connected.
Supersedes v3 (funding reworked; v3 history preserved in git).

## Result envelope (`backtest_result/v4`)

Produced by `backtest_offline.run_backtest` (`ENGINE_VERSION =
backtest-offline/v4`). All money in USDT; all times integer ms;
all times are KNOWLEDGE/decision times, never tick times.

| Field | Type | Meaning |
|---|---|---|
| `engine_version` | string | `backtest-offline/v4` |
| `config_hash` / `config` | string(16) / object | full `BacktestConfig` incl. funding calendar + estimate (context) + unsupported knobs (always null in a valid run) |
| `dataset_id` / `input_hash` | strings | caller label + sha256 of canonical event/candle tuples |
| `segment` | `dev`\|`oos` | event-time segment (limitation, see below) |
| `label` / `limitations` / `drawdown_scope` | strings | smoke guard; unmodeled effects (incl. `funding-calendar-or-interval-fallback`); `realized-only` |
| `n_events` / `n_trades` / `skipped_overlap` / `n_expired` / `n_mismatched` | integers | overlaps skipped, out-of-window expired, family/version mismatches — counted, never silent |
| `expectancy_net` / `expectancy_gross`, `total_net` / `total_fees` / `total_funding` | floats | mean/additive splits; funding = SETTLED only (per-settlement, direction-signed, cost-basis exposure) |
| `funding_calendar` | object\|null | version/source/nominal-interval/n/hash of the calendar used; null = interval fallback |
| `funding_estimated_bps_context` | float\|null | quoted estimate echoed as context; provably excluded from accounting |
| `max_drawdown`, `mfe_mean` / `mae_mean` | floats | realized equity peak-to-trough; excursions over demonstrated prints only (favorable extremes excluded, exit move feeds MAE) |
| `exit_reasons` | {horizon, stop, open_at_end} | rule-close marks vs stop executions vs data-end marks (`open_at_end` trades carry the flag + `cancelled_notional`) |
| `equity_curve` / `trades` | arrays | cumulative net; per-trade symbol/direction/family/rules, event/entry/exit ms (`exit_ms` ≥ `entry_ms`, knowledge-based), cost/qty average entry, filled_qty/filled_cost, gross/friction/net, `funding_events[]` {settlement_ms, rate_bps, held_cost, amount}, `funding_uncovered_ms`, `funding_model`, fills |

Funding semantics (binding): a settlement applies iff
entry_ms ≤ settlement_ms < exit_ms; exposure = cost filled at times ≤
settlement; holding time outside the calendar span is `uncovered`
(unknown cadence, never zero-rate); inter-settlement spans are cadence.

Guarantees a consumer may rely on: sequential fills; stops evaluated on
known closes only; gap-first open resolution; no post-window data use;
overlapping capacity committed at signal time.

## Sensitivity envelope

`run_sensitivity` returns `{engine_version, dataset_id, input_hash,
cutoff_ms, segments: {dev: {"1.0"|"2.0"|"3.0": <result>}, oos: {...}}}`.
`cutoff_ms` is REPORTED for reproducibility; it is NOT credited with
purging overlaps and does NOT validate out-of-sample.

## Consumer rules (binding on any future integration)

- Render `label` + `limitations` verbatim; fixture results never under a
  performance heading. Costs from the result's own `config` only.
- `dataset_id == synthetic-fixture` results are MECHANICS proofs only.
- Read time is never evidence. `exit_ms` is knowledge/decision time.

## Status

UNWIRED on purpose for the engine envelope above. Wiring needs: a versioned
real dataset id, an authorized study run, and frontend review of the exact
backend SHA.

## Amendment — WIRED via dashboard executor (2026-10-20, additive)

The read path is now wired for a bounded, allowlisted offline experiment,
WITHOUT changing engine semantics or the `backtest_result/v4.x` envelope.

- Executor: `scripts/run_dashboard_backtest.py` (`dashboard-backtest-executor/v1`).
  Allowlist `eval-census-v2-trio` over the published package
  `docs/evidence/eval-census-v2-package/` (EVAL-CENSUS-V2, 33 files,
  sha256-verified before any run). Client never supplies paths, symbols,
  shell or code.
- BFF (Dashboard V2, separate identity/state from the Binance monitor):
  `frontend/src/lib/backtest-control.ts` + routes under
  `frontend/src/app/api/v1/backtest/{run,status,results,replay}`.
- Results live in `<repo>/backtest-results/<experiment>/<run_id>/`
  (gitignored; canonical location, see Amendment Bloque B):
  `job_state.json`, `job_pid.json`, `current.json`, `summary.json`,
  `trades.json`, `reconciliation.json`, `replay_<hash>.json`.- `trades.json` is deterministic (byte-identical across runs);
  `reconciliation.json` proves per-cell `Σ net_pnl == total_net` within
  1e-9 for all 56 cells. `summary.json` differs only in wall-clock
  metadata (`generated_at_ms`, `duration_ms`) — accepted and documented.
- Operation → Paper Lab link: `build_paper_lab_replay.py --trades-json`
  materializes PAPER-LAB-REPLAY-V1 for the EXACT operation
  (event_id, group, segment, scale), preserving availability-time
  revelation, formation-as-metadata and realized/open separation.

This does not validate profitability, ranking or a full strategy. It only
makes a versioned offline experiment reproducible and inspectable from V2.

### Amendment — portable serialization of the evidence package (2026-10-20)

The published package is a **sha256-verified artifact**; the verification
read bytes, so those bytes must survive a clean checkout on any platform.

- `.gitattributes` (repo root) marks
  `docs/evidence/eval-census-v2-package/**` and its `package_manifest.json`
  as `-text` (binary): git stores and delivers the EXACT bytes it hashed, with
  no line-ending translation. Without this, `core.autocrlf=true` rewrote LF in
  the blob and a clean checkout delivered different bytes (21/33 files failed
  verification). Re-apply after editing: `git add --renormalize .`.
- `verify_eval_package.py` and the executor keep STRICT raw-byte sha256
  comparison: no normalization, no hash-ignoring. A real one-byte alteration
  still fails verification (exit 1) and the executor fails closed
  (`PACKAGE_VERIFICATION_FAILED`, no results written).
- Distinguish numeric reproducibility (same trades/nets) from byte equality
  (same file sha256). The portability fix concerns the latter.
- Verified: a clean checkout with `core.autocrlf=false` reproduces the
  manifest hashes 33/33 and the run (`trades=15765`, `n_trades_1x=5255`,
  reconciliation True, `trades.json` sha256 `815b8a65...`).

### Amendment — execution identity, run-bound results and canonical location (2026-10-20, Bloque B)

Defects found by an independent audit, all fixed:

- **Unique run identity.** Each request mints a `run_id`
  (`bt-<experiment>-<ts>-<rnd>`) SEPARATE from `experiment_id`. `job_id` is
  the run id, not the experiment. State lives at
  `backtest-results/<experiment>/<run_id>/job_state.json`; a stable
  `current.json` pointer names the active/latest run.
- **Inter-process exclusion.** Single-flight is enforced with an EXCLUSIVE
  lock file (`O_EXCL`), not in-process state, so two BFF processes (or a
  double click racing a restart) cannot launch two runs. An abandoned lock
  (dead owner pid or expired budget) is closed WITHOUT relaunching.
- **Verifiable executor identity.** Ownership is proven only by
  `executor_token` + `executor_pid` + `started_at_ms` together. A live-but-
  unverifiable (foreign or recycled) PID is reported as `UNKNOWN`
  (`PROCESS_IDENTITY_UNKNOWN`), never as `ejecutando`, and is never killed.
- **Reconciliation without auto-relaunch.** A `pendiente`/`ejecutando`
  state whose process is gone becomes `fallido` (`PROCESS_INTERRUPTED`).
- **Effective budget.** `BACKTEST_BUDGET_MS` is enforced both in the
  executor (deadline checks → `TIMEOUT`, fail-closed, no results) and at read
  time (a live verified run past budget is closed `TIMEOUT`).
- **Async spawn errors** are persisted (`SPAWN_FAILED`), never lost.
- **Run-bound, integrity-verified results.** `readResults`/`readRunResults`
  verify the declared `result_hashes` before serving; altered
  (`RESULT_INTEGRITY_FAILED`) or incomplete (`RESULT_INCOMPLETE`) results fail
  explicitly. Routes accept `?run=<run_id>` to target a specific execution.
- **Run-bound replay cache.** The replay artifact name is derived from
  `run_id` + result hash + operation identity, and the operation must belong
  to that run's trades (`TARGET_NOT_IN_RUN`), so a new run never silently
  reuses a previous run's replay.
- **Canonical location.** Results live in `<repo>/backtest-results/`
  (gitignored), matching this contract, not `frontend/.backtest-runs/`. The
  prior evidence was preserved (copied to `backtest-results/_legacy/`) and the
  old path kept gitignored; nothing was deleted.
- **Bounded retention** never removes a run that is active (live lock or
  `pendiente`/`ejecutando`); when it only reports, it never claims cleanup.
- **Operation switching in Paper Lab** no longer keeps the previous operation
  visible while a new identity loads or fails.

## Amendment v4.1 — realized/open/marks split + funding assessment (2026-10-13, additive, engine still `backtest-offline/v4`)

History above preserved. New fields are ADDITIVE; legacy
`total_net`/`expectancy_net`/`equity_curve`/`max_drawdown` still include
open marks (do not cite them as realized performance).

| Field | Type | Meaning |
|---|---|---|
| `n_realized` / `n_open` / `open_positions[]` | integers/array | closed trades vs data-end marks; marks carry mark_ms/mark_px/qty/cost and feed NOTHING realized |
| `total_net_realized` / `expectancy_net_realized` | floats | realized-only sums (open marks excluded) |
| `equity_curve_realized[]` | {exit_ms, equity} | realized equity in effective-close-time order |
| `max_drawdown_realized` | float | realized-only peak-to-trough |
| `exit_executed` / `realized_net` (per trade) | bool/float\|null | executed flag; null when open |
| `entry_spread_slip` / `exit_spread_slip`, `entry_fees` / `exit_fees` | floats | exit leg on an open mark is hypothetical |
| `costs_executed` / `costs_exit_hypothetical` (+ totals) | floats | hypothetical exit costs separated from executed |
| funding events | objects | `basis`: `settled` (qty x causal candle-open mark, with contract identity) \| `unknown-excluded` (no covering candle) \| `synthetic-fallback` (interval path marker) |
| `funding_gap_ms` / `funding_unknown` (per trade) | integer | interior-gap overlap with holding; unresolvable settlements |
| `funding_calendar` += `symbol`, `duplicates_deduped`, `complete`, `completeness_basis`, `gaps[]` | mixed | identity, exact-duplicate count, cadence-gap assessment (never first/last-inferred) |

Funding exposure is now CURRENT QUANTITY x SETTLEMENT MARK (flat-price
fixtures unchanged). Same-ms same-rate duplicates dedup (counted);
same-ms different-rate REJECTS the run. Runner manifest: per-group
`family`/`rules_version` (H1/H2/H3 map; baseline uses CLI default),
`event_ids[]` (index-based identity), `n_realized`/`n_open`,
`total_net_realized`, `max_drawdown_realized`.

## Amendment v4.2 — caps, pins, stale marks, exit-value fees (2026-10-13, additive)

- Unknown coverage is capped at the holding (`uncovered <= exit-entry`):
  a 100ms holding never reports more than 100ms unknown.
- A symbol-pinned calendar settles ONE contract: any foreign event symbol
  REJECTS the run (fail-closed; LUMIAUSDT calendar never settles BTCUSDT).
  Unpinned (`symbol: null`) calendars keep legacy multi-symbol behavior,
  recorded as UNKNOWN identity.
- Settlement marks carry `mark_age_ms` + `mark_freshness`. A covering print
  older than the nominal cadence (or any aged print without a cadence) is
  STALE: excluded as `unknown-excluded`, never settled as proxy.
- Commissions: entry leg on executed notional, exit leg on exit value
  (10u 100->120 @10bps = 1.00 entry / 1.20 exit). Symmetric halves were a
  bug; one legacy assertion updated to the corrected split (documented).
- Runner preserves calendar `symbol` verbatim into the manifest
  (`funding_calendar.symbol`); absent stays null (UNKNOWN, never invented).

## Amendment v4.3 — engine v4.1 + proxy freshness + accounting verdict (2026-10-13)

- `ENGINE_VERSION` is `backtest-offline/v4.1` (exit-value commissions,
  qty-x-mark exposure, data-step freshness, per-position accounting
  verdict); `config_hash` embeds the engine version, so v4 and v4.1
  result hashes never compare equal (v4 `fees=2.0/net=198.0` vs v4.1
  `fees=2.2/net=197.8` on the reference fixture is EXPECTED drift from
  the corrected fee leg, not a regression).
- Settlement marks: `mark_age_ms` + `data_step_ms` + `mark_freshness` in
  {fresh (observed, age 0), proxy (aged within one data step, settles
  flagged), stale (excluded as unknown)}. Freshness never uses the
  funding cadence.
- Per-trade `funding_accounting_complete` (+ basis): every in-window
  settlement fresh-or-proxy AND no gap overlap AND no uncovered holding.
  Calendar `complete` never implies it. Manifest cells carry
  `funding_quality` {settled, unknown, gap_ms, uncovered_ms,
  accounting_complete_trades}.

## Amendment v4.3.1 — causal data step (2026-10-14, review dcb2e32)

- The data step and settlement marks use the candle prefix known at
  `exit_ms`: candles printed later never reclassify earlier settlements
  (0/12/24/36h + entry 12h/exit 24h + calendar 12/16/20/24h settles
  12/16/20 identically with or without 37-48h hourly candles; the
  full-series median flipped 16h/20h to stale, 3 -> 1 — R8 regression
  `R8FundingHorizonCausalityTest`). `ENGINE_VERSION` unchanged (v4.1).

## Amendment v4.4 — engine v4.2 + per-settlement causality (2026-10-14,
review 4f1d92e)

- `ENGINE_VERSION` is `backtest-offline/v4.2`. The v4.1 exit_ms prefix was
  still retrospective inside the holding (0/12/24/36h + 21/22/23h flipped
  16h/20h proxy -> stale, 3 -> 1); each settlement now computes its data
  step AND its mark from the candle prefix known at its own
  `settlement_ms` (R9 `R9InHoldingCausalityTest` beside R8). Behavior
  change is versioned in results: `engine_version` reads v4.2 and
  `config_hash` embeds it, so v4.1 and v4.2 executions never compare
  equal (a contract note alone does not distinguish runs).
