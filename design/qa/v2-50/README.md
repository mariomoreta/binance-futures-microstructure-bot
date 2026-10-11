# DASH-V2-50 evidence
Backend reviewed: 8648366ec5ea82a46e4573cf81a53546f666d8d6.
Frontend baseline: e201dfa607e462cda87a781737da4c8c5c45c6bc.

- backend-reproductions.json: temporary registries / termination mocked only.
  Existing heartbeat fixture does not write; owned heartbeat replay does.
  Foreign-owner enforce and terminal-takeover race reach termination.
- results.json: 6 System/Overview cases at 1672/1366/390, no browser errors
  or page overflow. UI checks include sentinel evidence and Start disabled.
- system-*.png, overview-*.png: viewport screenshots.
- system-expanded-*.png: full expanded watcher evidence at all three widths.
- runtime-*.json: production read-only BFF DTO with raw watcher evidence.
- mobile-navigation.png: shared navigation capture.
- Current raw leases STOPPED, display STALE; process COMPLETED; feed UNKNOWN.
  These are observations from the archived session, not an active market run.
- Approved comparison: ../../references/v2-approved/system.png.
  Full visual parity PARTIAL; see corrections review for deliberate departures.

Reproduce from V2 root: node scripts/qa-dashboard-all.mjs system-50
Backend reproduction: set PYTHONPATH to audited backend src;tests and run
scripts/review-p1-14b8-corrections.py from that backend checkout.
No Start/Stop/monitor/runtime mutations are performed by browser QA.
