# Offline entry/exit evaluation — report V1 (conditioned, NOT validation)

Design: `docs/OFFLINE_EVAL_DESIGN_V1.md` (fixed before results).
Mapping candidate: `docs/HYPOTHESIS_ENTRY_MAPPING_CANDIDATE.md`
(MAP-CANDIDATE-v1, NOT approved). Funding: `docs/evidence/FUNDING_ACQUISITION_V1.md`.
Read contract: `docs/OFFLINE_EVAL_READ_CONTRACT_V1.md`. V2 view: research
archive section + `GET /api/v1/offline-eval`.
Per-trade audit (this closeout): `docs/evidence/OFFLINE_EVAL_AUDIT_V1.json`
(1412 operations with formation_time / available_at / entry_time, count flow,
funding classification, exposure scope, units).

Engine reused WITHOUT changes (`backtest-offline/v4.2`); runner reused
without changes; only harness additions (purge selection, calendar builder).
No threshold was optimized (engine defaults untouched).

## 1. Event flow (source → mapped → excluded → purged → overlap → closed/open)

Source = retained `event_instances` rows mapped by MAP-CANDIDATE-v1
(2831 rows total; per-symbol exports report symbol-filtered discards against
that full table; unmapped/bad-direction/bad-price/bad-time all 0):

| Symbol | Source (H1/H3/H2) | Purged (dev-crossing) | Admitted dev+oos |
|---|---|---|---|
| BTCUSDT | 476 (251/220/5) | 0 | 476 (224 dev + 252 oos) |
| ETHUSDT | 498 (260/235/3) | 1 (continuation LONG @1790007300000) | 497 (256 dev + 241 oos) |
| SOLUSDT | 584 (321/257/6) | 0 | 584 (297 dev + 287 oos) |
| Total | **1558** | **1** | **1557** (dev 777 + oos 780) |

Corrections to the previous draft: ETH source is 498 (not 497); 497 is the
admitted figure after the 1 purge. SOL H2 is 6 (not 7): 321+257+6=584.
Equation: 476 + 497 + 584 = **1557 admitted** = 1558 source − 1 purged.

Replay flow @1x (dev+oos, directional groups, per-cell single position):
1557 admitted − 145 overlap skips (`max_concurrent=1` within same
symbol+group+segment, deterministic time order) − 0 expired − 0 mismatched
= **1412 trades** (BTC 452 + ETH 457 + SOL 503) = **1410 realized +
2 open marks** (ETH/SOL continuation-oos, data-end marks, excluded from
realized metrics). Rebound-variant and baseline groups EMPTY by construction
(excluded).

## 2. Conditioned economics @1x (USDT per $1000 fixed notional per trade; COST-ASSUME-v1)

H1 continuation (LONG):

| Cell | n_tr | E[net]R | TotalR | Fees | Funding | DD_R | Stops | MFE/MAE |
|---|---|---|---|---|---|---|---|---|
| BTC dev | 105 | +0.48 | +50.83 | 105.11 | 0.00 | 26.04 | 6 | 0.38/0.14 |
| BTC oos | 122 | +0.34 | +41.14 | 122.12 | 0.00 | 17.08 | 2 | 0.32/0.11 |
| ETH dev | 115 | +1.03 | +118.03 | 115.15 | +0.09 (1 settled) | 22.37 | 11 | 0.55/0.19 |
| ETH oos | 114R+1open | +0.42R | +47.48R | 115.11 | 0.00 | 23.64 | 6 | 0.37/0.14 |
| SOL dev | 115 | +1.50 | +172.95 | 115.18 | 0.00 | 29.80 | 12 | 0.61/0.20 |
| SOL oos | 137R+1open | +1.13R | +155.11R | 138.19 | 0.00 | 33.92 | 15 | 0.52/0.18 |

H3 bearish continuation (SHORT):

| Cell | n_tr | E[net]R | TotalR | Fees | Funding | DD_R | Stops |
|---|---|---|---|---|---|---|---|
| BTC dev | 101 | +0.28 | +28.48 | 100.91 | 0.00 | 13.81 | 1 |
| BTC oos | 119 | +0.57 | +67.26 | 118.87 | 0.00 | 14.02 | 3 |
| ETH dev | 107 | +0.58 | +61.57 | 106.88 | 0.00 | 19.22 | 9 |
| ETH oos | 117 | +0.73 | +85.71 | 116.86 | 0.00 | 12.53 | 7 |
| SOL dev | 114 | +0.66 | +75.10 | 113.87 | 0.00 | 36.71 | 12 |
| SOL oos | 130 | +1.46 | +189.59 | 129.80 | 0.00 | 18.86 | 16 |

Units (binding): E[net]/E[gross] are USDT per trade on **$1000 fixed
notional @1x** (R-suffix = realized-only, open marks excluded). Gross
(pre-friction) E per trade spans **+1.88…+3.11** across the 12 H1/H3 cells
(prose "+1.9…+3.1/op"). Friction @1x ≈ **1.60/trade** (commissions ~1.00 at
5bps × 2 legs on ~$1000 + assumed spread/slip ~0.60 at 3bps × 2 legs) —
the draft "~1.0" covered commissions only and is corrected here. Costs
5/1/2bps are versioned **assumptions** (COST-ASSUME-v1, engine defaults
untouched): fee tier unknown, no spread/depth history — never measurements.
Sample: per-cell n above; H2 legs §4; held-out is time-held-out
(non-pristine, §6); pooled reference §3 is arithmetic aggregation, not a
comparable alternative strategy.

## 3. Sensitivity (the binding constraint)

Every directional cell turns NEGATIVE at 2x costs and deeply negative at 3x
(e.g. SOL H1-oos +1.11 → −0.49 → −2.09; BTC H3-oos +0.57 → −1.03 → −2.63).
Pooled reference: dev +0.80 → −0.80 → −2.40; oos +0.83R → −0.77R → −2.37R.
Per the paper-trading rule, an edge that dies at 2x is NOTED as fragile —
and here the 1x margin (≈0.3–1.5 USDT/trade) is thinner than the uncertainty
inside the cost assumptions themselves (slippage unmeasured, fee tier
unknown). No positive conditioned cell is read as demonstrated edge.

## 4. H2 legs (fenced: INSUFFICIENT, no reading)

14 trio events total (BTC 5, ETH 3, SOL 6; all cells n ≤ 4). Single-trade
anecdotes (SOL exhaustion-oos +21.67 on n=1 with MFE 2.50%; SOL
reversal-oos +10.05 on n=1) are REPORTED in cells but explicitly fenced as
non-evidence. Rebound variant: 0 events, excluded as untestable.

## 5. Causality (per-operation proof, not "next open" by assertion)

`event_time` = formation-bar OPEN; the condition is knowable only at the
formation bar's `close_time` (= `available_at`); the engine fills at the
first candle `open_time > event_time` (= `entry_time`). The audit replays
all 1412 trades and conserves the triple per operation in
`docs/evidence/OFFLINE_EVAL_AUDIT_V1.json` (`causality.trades`):
**1412/1412 with `available_at` present and `entry_time >= available_at`,
0 violations, 0 null**. Gap `entry − available` is uniformly 1ms (venue
`close_time` = next open − 1ms on the intact chain: 2879 closed
candles/symbol, `null_close_time` 0, `close_chain_violations` 0 — so no
gap or misalignment exists to survive on assertion alone). On a gapped
chain the rule still fills at the next *known* open (≥ available_at by
construction) with gap-first exits; `reference_price` never prices a fill.
What this does NOT prove: live-signal availability at that instant stays
UNKNOWN (no streaming-formation proof) — mechanical causality, not
tradability.

## 6. Funding (measured where covered, UNKNOWN where not)

Calendars FUNDING-CAL-v1 per symbol: 90 realized settlements,
1788825600004 → 1791388800000, nominal 8h, no interior gaps. Candle window
1788816600000 → 1791407699999: head holdings before the first settlement
and tail holdings after the last are **uncovered (UNKNOWN, never zeroed)**.
Classification over the 1412 trades:

- Fully covered, no settlement in `[entry, exit)`: **1403 trades**,
  `accounting_complete=true`, funding 0 by absence of settlement (correct —
  no payment due), not by assumption.
- Covered with settlement applied: **1 trade** (ETH continuation-dev LONG,
  entry 1790006400000 → exit 1790009100000, settlement 1790006400002,
  **+0.0894 USDT**).
- Uncovered/UNKNOWN: **8 trades** (6 closed tails + 2 open-end marks, each
  `uncovered_ms=2700000`): BTC cont-oos 1, ETH cont-oos 1 + 1 open,
  ETH bear-oos 1, SOL cont-oos 1 + 1 open, SOL bear-oos 2.
  Total: 1404/1412 accounting-complete.

Note: 179 event-horizons `[event_time, event_time+1h)` contain a settlement
(BTC 53, ETH 57, SOL 69), but all except the one above fall *before entry*
and are correctly not held through. The draft phrase "4 qualifying windows"
is STRUCK and replaced by these audited figures. Sensitivity without
calendar (synthetic fallback): ETH continuation-dev funding 0.0894 →
0.0000 (delta +0.0894 total, ~0.0008/trade), all else identical. Magnitude
negligible AND coverage incomplete for 8 trades — "immaterial" is not
concluded for the uncovered set.

## 7. Exposure (scope of max_concurrent=1; pooled is not a portfolio)

`max_concurrent=1` applies INSIDE one `run_backtest` invocation = one
(symbol-run, group, segment, scale) cell. Symbols replay in separate
processes with symbol-pinned calendars (a foreign symbol is REJECTED
fail-closed); groups replay in separate calls with separate open-interval
ledgers; dev/oos replay separately. Overlapping events from different
groups (e.g. H1 LONG vs H3 SHORT) or symbols NEVER compete — both trade.
The 145 skips are strictly within same symbol+group+segment (worst case
SOL continuation-dev 52/167 = 31%). `pooled_reference` is the arithmetic
sum over independent single-position replays: NOT a portfolio with one
simultaneous position (it can imply concurrent positions across
symbols/groups; no cross-margin, no portfolio concurrency limit, no
simultaneous-exposure P&L — unmodeled).

## 8. What we learned about entries/exits

- Entries: next-open fills are causal on intact chains (per-trade proof §5);
  `reference_price` never priced a fill. Availability of a LIVE signal at
  that instant remains UNKNOWN (no streaming-formation proof).
- Stops: the 0.5% placeholder rarely binds (2–12% of trades); MAE
  (0.11–0.23%) sits well inside it, so exits are horizon-driven, not
  stop-driven. Any future stop methodology starts from this measurement,
  not from the placeholder.
- Exits: ~90% of trades close at the 1h horizon mark; MFE (0.32–0.61%)
  shows favorable excursion exists but capture is an exit-rule question the
  fixed horizon does not answer.
- Overlap: up to 31% skips (SOL H1-dev) under single-position discipline
  *per cell*; cross-cell simultaneity is unmodeled and would only add
  friction.
- Funding: 1 settlement applied (+0.0894), 1403 covered-quiet, 8 uncovered
  UNKNOWN (§6); per-settlement causal accounting held (0 invented).

## 9. What is missing for prospective simulation (not started)

Approved mapping, live-signal availability proof, measured costs (fee tier +
spread/depth history), a pristine forward window with the §6 protocol
(frozen rules + pre-committed cut/purge + single replay), and a
position/exposure model. The next concrete step is acquiring that forward
window and pre-committing its protocol — NOT replaying again on this one.

## 10. Reproduction (isolated, canonical untouched)

```
python scripts/export_engine_inputs.py --symbols BTCUSDT --interval 15m --out-dir <tmp_btc>   # x3 symbols
python scripts/select_eval_events.py --events <tmp>/events.json --cutoff-ms 1790010000000 --horizon-ms 3600000 --dev-out <dev> --oos-out <oos> --report <sel>
python scripts/run_family_evaluation.py --events <dev+oos> --candles <tmp>/candles.json --calendar docs/evidence/FUNDING_CALENDAR_<SYM>_V1.json --cutoff-ms 1790010000000 --out <manifest> --formation-method PROPOSED-P1-11C-map-v1
python scripts/aggregate_offline_eval.py --inputs <inputs.json> --out frontend/src/data/offline-eval-v1.json
```

`<inputs.json>` maps each symbol to its `{manifest, meta, selection,
calendar}` paths (cutoff/horizon echoed at top level). The aggregator is
bundling-only (fail-closed on cutoff/selection/calendar mismatches; pooled
= arithmetic sums over directional groups) and regenerates the published
artifact byte-identically (sha256 below).

Re-executed 2026-10-16 into temp dirs (audit_btc/eth/sol): exports
476/498/584 events, selections 224+252/0, 256+241/1, 297+287/0,
`input_hash` identical to the bundled artifact per symbol
(BTC 31c100e2…, ETH 7643681e…, SOL d784680b…), replayed trades
452+457+503=1412, aggregation byte-identical. Funding re-acquisition: 3
GETs documented in `FUNDING_ACQUISITION_V1.md` (verifiable provenance
hashes there) + `scripts/build_funding_calendar.py`. Bulky JSON
(candles/events/raw) lives outside Git; manifests/hashes/commands above
reproduce them. Audit: `docs/evidence/OFFLINE_EVAL_AUDIT_V1.json`.
Artifact: `frontend/src/data/offline-eval-v1.json` (committed, force-added
past the `data/` ignore; sha256
`c051e88841754668a02a6d92db02ccdcb97fd16e45a08671022a370576287b3a`).

Dataset limitation (binding): the export step reads the local canonical
`data/historical/historical.db` (read-only), which is NOT published and is
absent from a clean checkout. Commands + hashes alone do NOT reconstruct
its 2879 candles/symbol + 2831 event rows. What a clean checkout CAN verify
without it: the committed artifact (parsed content + pinned sha),
aggregation determinism from fixtures (`tests/test_offline_eval_aggregation.py`),
the UI adapter/route, and the full frontend suite + typecheck + build.
