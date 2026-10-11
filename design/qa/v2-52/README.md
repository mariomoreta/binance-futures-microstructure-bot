# V2-52 evidence

Backend reviewed: 55efaa2b171c83701f6736ab6e6374869a733af1.
Report: docs/DASHBOARD_V2_52_INTEGRATION_REVIEW.md.

- backend-reproductions.json: exact bridge byte preservation, simulated same-child
  start race, simulated native API refusal. No real spawn/kill of a probe.
- results.json and screenshots: System/Overview 1672/1366/390, viewport and
  expanded watcher evidence, mobile navigation, actual read-only runtime DTOs.
- Approved System reference inspected; fidelity remains PARTIAL.

Rerun from V2 root: node scripts/qa-dashboard-all.mjs system-52.
Hermetic audit: python scripts/review-p1-14b8-v2-52.py (pinned backend SHA).
Canonical backend run_tests.py: 826 tests; V2 snapshot: 496 tests.
