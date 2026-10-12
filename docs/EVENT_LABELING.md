# EVENT_LABELING

Historical header note (2026-10-06): this file originally stated that no
persistence or labeling code existed and Phase 1 must not persist events.
That was true at P1-02 planning time and is SUPERSEDED: P1-02 built the
SQLite foundation, P1-11B the historical store, P1-11C the no-lookahead
event-study engine (`events.py`, 38 runs / 2831 instances / 16986 outcomes
in `data/historical/historical.db`), and P1-13A/14A opportunity +
prospective evaluation. In-memory warm-up still applies to detectors;
durable labeling is implemented as specified below (Phase 2 scope
delivered inside the Phase 1 research chain; roadmap phases unchanged).

## Requirement

For every relevant state/signal event, preserve the full feature snapshot and
later calculate forward outcomes at:

`30s, 1m, 3m, 5m, 15m, 30m, 60m`

including, per horizon:

- forward return
- MFE (max favorable excursion)
- MAE (max adverse excursion)
- time_to_peak
- time_to_trough
- max continuation
- max reversal

## Snapshot content (minimum)

Event id, symbol, event timestamp (exchange + local + offset), state/signal
type, full feature vector (`docs/FEATURE_MODEL.md`), market context
(rank snapshot, BTC regime proxy, funding/OI values), data-quality flags
(staleness, gaps, rejections in window), code version + config hash.

## Rules

- Outcomes computed from actually-observed later data, never interpolated
  across gaps; gaps flagged.
- Costs/slippage applied at analysis time (Phase 3), stored separately from
  raw outcomes so assumptions stay auditable.
- This dataset is what turns `HUMAN_STRATEGY_HYPOTHESIS` and hypotheses A/B
  into evidence — or kills them. No labeling, no strategy claims.
