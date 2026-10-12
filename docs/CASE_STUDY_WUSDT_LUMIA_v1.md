# Case-study protocol v1 — WUSDT / LUMIAUSDT 4h-funding evidence

Status: METHODOLOGY + ABSENCE RECORD. No case package was available in
this worktree at the time of writing (no archive, no hashes, no
per-ticker/per-candle tables found; searched worktree excluding
`.git/`, build outputs and the preserved preexisting untracked files,
which were not modified). Nothing below reconstructs supposed results:
any number not computed here is UNKNOWN, never filled in.

## 0. Package absence (verified 2026-10-13)

- Searched: `*.zip`, `*.tar*`, case JSON/CSV, `WUSDT`, `LUMIAUSDT`
  outside prior HOT-rotation mentions. Found: none.
- Consequence: selection method, cutoff, formulas, horizons, observed
  results and ticker/candle discrepancies CANNOT be verified. The
  reported "funding every 4h" claim is NOT treated as evidence on its
  own (unverified report ≠ source). Venue funding calendars must come
  from exchange funding-history endpoints at research time, per symbol.

## 1. Selection method and time cutoff (binding when the package lands)

- Universe: symbols named in the package only; no substitution, no
  extension to "similar" symbols.
- Cutoff: package end timestamp; analysis window frozen there. Any data
  after the cutoff is excluded (no peeking). Dev/OOS split from §6
  applies only with a predeclared cutoff inside the package window.

## 2. Source, formulas, horizons

- Source hierarchy: venue funding-history (settlements: timestamp +
  realized rate) > persisted markPrice arrays (quoted rate + next time,
  as-of) > dashboard estimates (context only). Never mixed silently.
- Formulas: replay engine `backtest-offline/v4` (per-settlement,
  boundary entry ≤ t < exit, cost-basis exposure, direction sign).
- Horizons: study contract horizons (1m/3m/5m/15m/30m/1h/4h); 4h funding
  cadence (if verified per symbol) enters ONLY via the versioned
  calendar — never as a global interval swap.

## 3. Observed results and discrepancies (to fill on arrival)

- Recompute every figure from the original files; report ticker-level
  and candle-level mismatches verbatim (wrong symbol, shifted
  timestamps, adjusted closes, missing intervals). A mismatch stops
  promotion of that figure; it never gets "cleaned".

## 4. Bias, latency, coverage

- Retrospective bias: symbols were selected AFTER moving (survivorship/
  attention bias stated, not corrected away).
- Latency unknown: execution lags are venue+path dependent; replay uses
  knowledge-time fills with explicit limitations, never assumed fills.
- Coverage: universe history, availability proof, and measured costs
  required before any validation claim; gaps stay UNKNOWN/GAP.

## 5. Data vs interpretation vs pending hypotheses

- Data: settled funding rows + candle closes (mechanical).
- Interpretation: what the replay shows under stated assumptions.
- Pending: H1 continuation, H2 exhaustion/reversal legs, H3 bearish
  continuation — SEPARATE, never pooled. Rebounds after drops are an
  EXPLICIT H2-reversal-variant study, never a silent H3 redefinition
  ("loser recovery" stays out of H3 by contract).
- No threshold calibration on these two symbols; no OOS validation
  claims from them. RSI/ATR remain research candidates, not rules.

## Versioning

v1 (2026-10-13): protocol + absence record. On package arrival: v2 with
hashes, recomputation, and a discrepancy log — or a renewed absence
note. Never backdate validation.

## Addendum v2 — package receipt + isolated reproduction (2026-10-13)

Status: DESCRIPTIVE / IN-SAMPLE reproduction record. The v1 absence act
above is preserved as history; it is not rewritten. No OOS, no
calibration, no profitability claim. No SUCCESS_GATES advancement.

- Receipt: untracked package found at relative path `binance_case_study/`
  (12 files; see `binance_case_study/SHA256SUMS.txt`). The v1 search
  predates this receipt; this addendum records arrival, not a correction
  of the v1 method.
- Hashes: 12/12 OK against `SHA256SUMS.txt` (method: SHA256 over exact
  bytes, HEAD `6f8bd204c3a0622a90288fa49c656a232f9d7c24`).
  Evidence: `docs/evidence/CASE_STUDY_WUSDT_LUMIA_HASHES.txt`.
- Reproduction effectively performed: isolated copy in
  `%TEMP%/lumia_repro/binance_case_study` (originals intact, no staging
  of `binance_case_study/`, no voluminous data published).
- Environment: Windows win32, Python 3.14.3, pandas 3.0.3, numpy 2.5.1,
  matplotlib 3.11.2, `PYTHONUTF8=1`. No network, no Binance, no
  canonical DB. Evidence: `docs/evidence/CASE_STUDY_WUSDT_LUMIA_ENV.json`.
- Exact commands (PowerShell, repo root, `PYTHONUTF8=1`):
  `python "<copia>/binance_case_study/analyze.py"`,
  `python "<copia>/binance_case_study/finish.py"`,
  `python docs/evidence/compare_case_study_json_csv.py "binance_case_study" "<copia>/binance_case_study"`.
  Exit codes: analyze 0, finish 0, compare 0.
  Evidence: `docs/evidence/CASE_STUDY_WUSDT_LUMIA_REPRO_LOGS.txt`.
- Numeric coincidence: parsed `analysis_summary.json` 0 diffs (tolerance
  1e-12); parsed `supplemental_analysis.json` 0 diffs; 4 CSVs same shape
  (W/LUMIA 1499x42, BTC/GTC 1499x35), same columns, max abs numeric diff
  0.0, non-numeric columns exact.
- Serialization differences (not numeric): regenerated bytes differ
  (`analysis_summary.json` 90371 vs 92559,
  `supplemental_analysis.json` 5365 vs 5516, CSVs +~1500 bytes each,
  PNG 354372 vs 351462 with distinct SHA256). Values coincide; byte
  identity is NOT claimed.
- Visual comparison: `Casos_Binance_W_LUMIA.png` was NOT inspected
  visually here; visual equivalence is NOT declared (NOT_ASSESSED).
  Structured evidence: `docs/evidence/CASE_STUDY_WUSDT_LUMIA_COMPARISON.json`
  + script `docs/evidence/compare_case_study_json_csv.py`.
- Limits preserved: temporal availability ~5.2d (1499 closed 5m bars per
  series; cutoff 2026-10-12T10:57:19.690Z), retrospective selection bias,
  in-sample only. Without OOS, calibration, or profitability. Funding 4h
  is a replay-fidelity requirement per contract, not an edge.

## Addendum v2.1 — V2 correction + strengthened comparator (2026-10-13, review branch)

History preserved: v1 and v2 above are untouched. This addendum corrects
the V2 sentence in v2 and records the strengthened comparator.

- V2 correction: `27b7af59cb1e313169f49655161d66e043b5412d`
  ("Integrate recorded System panels...", rama `dash-v2-03-token-detail`)
  DOES contain BFF routes (`frontend/src/app/api/v1/`: live-movers,
  market-snapshot, opportunities, price-series, prospective,
  historical-coverage/research, runtime, system-evidence) and SQLite read
  adapters (`frontend/src/lib/canonical-market.ts`: `historicalRead` over
  discovery_snapshots, return/flow/book/oi/structure/state_features,
  price_samples, prospective, opportunity_candidates; BEGIN/COMMIT with
  ROLLBACK and `available:false` fallback). Reviewed from Git only
  (`git show 27b7af5:...`), no checkout touched. The v2 phrase "sin
  BFF/datos vivos" was wrong and is replaced by: integration PARTIALLY
  implemented (BFF read path exists) but live feed/operation NOT verified
  — the route itself returns alignment/freshness UNVERIFIED with warnings
  ("Read time is not observation time", "Retained coverage and captured
  freshness do not certify present feed liveness"). Partial integration
  is not verified live operation. No paper/orders/gates.
- Comparator hardened: `docs/evidence/compare_case_study_json_csv.py`
  now compares missing-masks BEFORE numerics, detects type changes and
  special values (NaN/inf/None), never silently omits expected files,
  columns or comparisons, and exits 1 on differences / 2 on incomplete
  comparison (PNG hash-only, excluded from exit; visual NOT_ASSESSED).
  Output JSON textual UTF-8 (`--out`, ensure_ascii=False).
- Regression proof (temp copies, originals intact): value->missing,
  missing->value, numeric change and structure change each exit 1;
  missing file exits 2. The reported rsi14=51.06347303475749 (WUSDT row
  100) -> missing case now yields
  `MISSING_MASK rsi14: orig_na=14 repro_na=15 rows=[100]` instead of the
  old silent 0.0/exit 0. Fresh legitimate re-run (analyze 0, finish 0)
  still exits 0 with verdict MATCH. Evidence:
  `docs/evidence/CASE_STUDY_WUSDT_LUMIA_REGRESSIONS.txt` +
  regenerated `docs/evidence/CASE_STUDY_WUSDT_LUMIA_COMPARISON.json`.


