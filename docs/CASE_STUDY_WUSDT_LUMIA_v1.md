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
