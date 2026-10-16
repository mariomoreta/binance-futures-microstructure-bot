# Event episodes — descriptive grouping contract v1

Status: grouping rule v1 IMPLEMENTED (`event_episodes.py`,
`control.read_run_detections`, BFF `GET /api/v1/detections`, System
panel); detector conditions and thresholds UNCHANGED (hypothesis,
see `config/probe.json` + `detectors.py`).

## Vocabulary (binding)

- Raw event: one original detector emission, preserved verbatim. Never
  mutated, never silently dropped (malformed rows counted as skipped).
- Grouped episode: maximal sequence under the v1 rule. Describes
  repetition; claims NO statistical independence and NO entry signal.
- Update: repetition or evolution inside the episode (same key,
  contiguous in time).
- New episode: the separation rule fires.

Raw-event count and episode count are reported separately, always.
No repetition becomes a new opportunity; opportunities consume
classifications, never raw detector events (verified 2026-10-16:
zero funding/detector references in V2 data paths and opportunity
evidence blocks).

## v1 rule (extreme_funding_rate only)

- Grouping key: (event_type, symbol, funding_rate).
- Order: (symbol, timestamp); input order never assumed.
- Same episode while key equal AND gap <= 5s between consecutive
  observations.
- New episode on: first usable record (`first-event`), symbol change
  (`new-symbol`), rate change (`new-rate`), gap exceeded
  (`gap-exceeded`).
- Close: `superseded` when a new episode opens, `end-of-evidence`
  for the trailing episode.
- Detector condition reviewed (unchanged): fires when the rate falls
  outside [lower, upper] percentiles of its history once
  `minimum_samples` is reached (`detectors.py:119-158`); near-constant
  series re-fire ~1/s while constant — that repetition is exactly what
  episodes describe.

## Episode record

grouping_version, episode_id (`symbol/rate/first-observed`),
event_type, symbol, funding_rate, repetitions (raw count, duplicates
included), duplicate_records, first/last_observed_at, duration_s,
history_samples first->last, open_reason, close_reason, event_indexes
(audit trail to the preserved originals).

## Consumption and limits

- BFF reads ONLY the recorded run's registry evidence log (bounded
  tail, canonical Python grouping); missing log/records surface as
  unavailable/UNKNOWN with a limitation note — episodes are never
  invented from aggregates (telemetry `detectors_json` carries counts
  only and cannot reconstruct episodes).
- V2 System panel shows raw vs grouped counts, repetitions, duration,
  provenance (log-stem run_id + linked probe UUID when present),
  grouping version and freshness, with an explicit research label:
  funding thresholds remain unvalidated hypotheses.
- The two published counts are NOT equivalent measurements and must
  never be presented as such: 98 raw / 4 episodes is the live BFF
  view over the bounded evidence tail (`evidence-tail-truncated`,
  probe link UNKNOWN for the unlinked historic run); 245 raw / 13
  episodes is the complete reconstruction over the frozen fixture
  (`tests/fixtures/funding_245_obs10m.json`, 245/245 records
  verified against the run log) under the same v1 rule.
