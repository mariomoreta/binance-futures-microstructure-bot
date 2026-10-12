# ETAPA 5 — Paper Lab plan (2026-10-12, DESIGN ONLY)

No paper engine is implemented, started, or authorized here. Operational
implementation depends on validating Etapas 1–4 plus explicit human
authorization per `docs/PAPER_TRADING.md` + `docs/RISK_RULES.md` +
`docs/SAFETY_RULES.md`. This file designs the work breakdown only.

## 1. Simulation engine + fill model (pending)

- Consume live public streams through the existing probe path (no new
  venue); paper fills simulated at touch-adjusted prices from bookTicker/
  depth snapshots with the Etapa-4 cost stack (fees, funding, spread,
  slippage) plus a latency distribution from measured corrected lags.
- Partial fills against sampled depth levels; unfilled remainder rests or
  cancels per versioned policy (no silent full-fill assumption).
- Deterministic seed + config/version recording per session; replayable
  from persisted snapshots for divergence forensics.

## 2. Position manager (pending)

- State-driven, evidence-driven exits (classifier states, invalidation
  levels from the Etapa-3 contract); fixed-time exits as baseline
  comparator only. Mirrors backtest exit semantics so paper-vs-backtest
  comparison is apples-to-apples.
- One authoritative position ledger (paper-only store, separate from
  research DBs); every action timestamped with event-time + receive-time.

## 3. Cash / fees / funding / P&L accounting (pending)

- Paper cash ledger: starting equity (fictitious, labeled), per-fill fee
  debits, 8h funding accruals while open, realized/unrealized P&L split,
  exposure-time-weighted returns. All cost inputs versioned per session.

## 4. Risk: per-position + portfolio (pending)

- Per-trade MAE stop, max concurrent positions, max notional/position,
  max total exposure, daily loss limit — tighten-only starting values
  from `docs/RISK_RULES.md`; any loosening needs a DECISIONS entry.
- Risk engine unbypassable by signal/position logic (architectural
  invariant, tested before any session).

## 5. Exposure limits, halts, kill-switch (pending)

- Halts: daily-loss breach, cost-sensitivity failure, version/config
  mismatch → new entries stop, opens go to protect/exit mode.
- Kill-switch: data staleness beyond tolerance, WS outage, clock-sync
  failure → immediate halt + human review. Halt/kill events are
  first-class persisted records.

## 6. Paper-vs-backtest comparison (pending)

- Same H-family, same config hash class, same horizons: compare fill
  prices, exit timing, cost drag, expectancy distributions, drawdown.
- Tolerance band predeclared per study; breach stops promotion and opens
  an investigation task — never adjust the backtest to match (per
  PAPER_TRADING rules).

## 7. Entry gates (all must hold before implementation)

Etapa-1 barrier green on the implementation SHA; Etapa-2 dataset fit for
the traded family (costs + versions + OOS exist — they do not today);
Etapa-3 contract accepted per family; Etapa-4 engine validated on a real
versioned dataset; explicit human authorization; dashboard embodies the
read contract (reviewed, unwired until then).

## Closeout (seven fields)

- `DECISIONS_REVIEWED`: PAPER_TRADING, RISK_RULES, POSITION_MANAGEMENT
  (pending doc), Etapa-3 contract, Etapa-4 read contract.
- `NEW_DECISIONS_RECORDED`: paper-lab work breakdown + entry gates above
  — appended to `docs/DECISIONS.md`.
- `FEATURES_IMPLEMENTED`: this design (no backlog ID).
- `FEATURES_VERIFIED`: none (nothing built).
- `DEFERRED_FEATURES`: all six build items; live validation; sizing/risk
  contract values; dashboard wiring.
- `BACKLOG_UPDATED`: Etapa-5 line (design only).
- `DOCUMENTATION_CONFLICTS`: none.
