# ETAPA 2 — Dataset readiness report (2026-10-12)

Method: pure reads only (`scripts/audit_dataset_provenance.py`, read-only
SQLite URIs, no probe/store imports). Canonical hashes identical
before/after. Evidence: `docs/evidence/DATASET_PROVENANCE_ETAPA2.json`.
All existing rows retained — nothing deleted, rewritten, reclassified or
silently excluded. COMPLETE describes outcome recording, never a
profitable operation.

## 1. Provenance: universe_events (375)

- **225 rows CONFIRMED fixture leakage.** All are DOGEUSDT
  `hot_subscribed` (152) / `hot_unsubscribed` (73) with `detail='test'`,
  2026-10-08→10-11 (75/57/45/48 per day). Signature matches exactly the
  pre-fix `HotSyncTest` route (`_sync_hot_subscriptions(reason="test")`
  → `detail=reason`; proven writing this shape on temp interception in
  Etapa 1). Exclusion proof: the only other `detail='test'` writers in
  test code use temp stores, and canonical holds 0 `S[0-9]*USDT` rows and
  0 `XRPUSDT/top_mover_2_votes` rows. Disposition: RETAINED, must be
  filtered (`detail != 'test'`) for any research use — explicit, never
  silent.
- **150 rows PROBABLE operational.** `promoted` 89 (`top_mover_2_votes`),
  `demoted` 19 (`absent_2_scans` 17…), `hot_promoted` 21 (`ranked
  proposal`), `hot_subscribed` 21 (`discovery-scan`), `hot_set_cap` 2;
  2026-10-07→10-10, consistent with documented live-run discovery
  activity. Per-row run association is UNKNOWN (no run-id column) —
  BLOCKER for run-linked analysis.
- 0 exact duplicates. Cap 500 not binding.

## 2. Prospective setups/outcomes (66 / 228)

- 66 setups, rules `v0.1.0` ×66, lifecycle all `DETECTED` (static in v0 —
  not positions), families IGNITION 19 / REVERSAL 21 / EXHAUSTION 13 /
  MOMENTUM 7 / EXTREME 6; detected 10-08 (5) / 10-09 (19) / 10-10 (42),
  temporally consistent with the P1-14B live windows. Symbols: 11 live
  names (CORE + HOT rotations); zero fixture markers (no DOGEUSDT, no
  `S*USDT` beyond SOLUSDT false-positive-of-pattern, no `test` keys).
- 228/228 outcomes COMPLETE, 0 null `mark_return_pct`, 0
  (candidate,horizon) dupes; horizons 1m×63 / 5m×59 / 15m×44 / 1h×35 /
  4h×27. 3 orphan young setups (KAIA×2, MAGIC×1, detected 10-10) are
  not-yet-matured absences — legitimate, not missing data.
- BLOCKERS: single rules version (no variation to study); static
  lifecycle; no run linkage; mark returns only — no fees/funding/spread/
  slippage, so no expectancy computation is possible from this table.

## 3. Event studies, historical DB (38 runs / 2831 instances / 16986 outcomes)

- 6 definitions v1, all `DESCRIPTIVE_RESEARCH_ONLY_HYPOTHESIS`; 38 runs
  `done`; instances 1203/1184/318/97/19/10 per family.
- Outcomes = 2831 × 6 horizons exact (no missing cells): 16968 COMPLETE +
  18 INSUFFICIENT_HISTORY; MFE/MAE present except those 18; `gap_crossed`
  0; 16548 usable. The 420 COMPLETE-but-unusable = 70 earliest BTCUSDT
  ACCEL_UP events × 6 horizons with instance
  `data_quality='FORMATION_GAP'` — the documented formation-gap exclusion
  working, not a defect.
- No-lookahead is structural (formation: bars `open_time <= T`; outcomes:
  `open_time > T`; reference = closed-bar close) and pinned by
  `test_future_path_separated_from_feature_snapshot`,
  `test_btc_synchronized_lookup_no_future`, `test_gap_exclusion`,
  `test_formation_gap_exclusion`, MFE/MAE long+short mirror tests.
- BLOCKERS: single ~30d pilot window (09-08→10-08); sub-1h horizons on 1h
  bars share the next-bar outcome (resolution limit, documented);
  FAILED_* tiers INSUFFICIENT/EXPLORATORY by construction; no
  out-of-sample split; no costs.

## 4. Coverage stores

- Historical klines: 13 series at ratio 1.0 (5× 1h, 3× 15m, 1× BTC 1m,
  3× mark 1h); OI capped at 500 rows (~41.6h, served-data limit);
  `historical_gaps` 0 in-window; 10 ingestion runs ledgered; aggTrades
  recent-only (no reconstructed book).
- Research buckets (live-captured): flow_10s 10615 / flow_1m 1855 /
  book_1m 1776; spans not extracted here (UNKNOWN — do not infer).
- Ring buffers, NOT archival: snapshots 1000 (~2.5d span), observations
  10000, rejections 1000, price_samples 3042. Opportunity: 68 candidates
  (rules v0.1.0), 392 events. States: 14 features / 500 transitions.

## 5. Readiness verdict (bounded)

SUFFICIENT FOR: descriptive exploration on exploratory+ tiers with the
225 fixture rows explicitly filtered; mechanism checks (no-lookahead,
gap handling, idempotency) already pinned by tests.
NOT SUFFICIENT FOR: strategy validation or any trading claim — missing
costs, single rule versions, small rare-family samples, no OOS split,
no run linkage, capped buffers. Capitalization source: UNKNOWN (no
validated source; never infer from volume/price).

## 6. Closeout (seven fields)

- `DECISIONS_REVIEWED`: Etapa-1 report + evidence, EVENT_LABELING,
  MARKET_DATA (P1-11B contracts), P1-14B.x run reports.
- `NEW_DECISIONS_RECORDED`: 225-row confirmed-fixture disposition
  (retain + explicit filter); 150-row probable-operational with
  unknown per-row runs; FORMATION_GAP usability Artifact classified as
  designed behavior — appended to `docs/DECISIONS.md`.
- `FEATURES_IMPLEMENTED`: provenance script + this report (research
  enabling; no backlog ID).
- `FEATURES_VERIFIED`: pure-read counts above; evidence JSON linked.
- `DEFERRED_FEATURES`: run-id linkage; OOS spans; cost-bearing outcomes;
  capitalization source; Etapas 3–5.
- `BACKLOG_UPDATED`: Etapa-2 line (enabling work, no ID verified).
- `DOCUMENTATION_CONFLICTS`: none new; prior 366/222 vs 375/225 drift
  explained (leakage accumulated across runs until the aea0376 fix).
