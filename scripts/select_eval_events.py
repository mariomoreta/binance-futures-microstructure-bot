"""Purge-aware event selection for offline evaluation (harness, not engine).

Reads an exporter `events.json`, a global `cutoff_ms` and a horizon, and
writes two files: dev events (window fully before the cutoff) and eval
events (formation at/after the cutoff). Dev events whose horizon window
crosses the cutoff are PURGED (counted, never silently kept).

The engine's split_by_time is credited with no purging power (its own
contract); this selection runs BEFORE the runner, so every replayed cell
is already purge-clean. Never touches the network, live modules, or
canonical DBs. Reads/writes caller-given paths only.

Usage:
  python scripts/select_eval_events.py --events events.json \\
      --cutoff-ms 1790010000000 --horizon-ms 3600000 \\
      --dev-out dev.json --oos-out oos.json --report selection.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Purge-aware dev/eval selection.")
    ap.add_argument("--events", required=True)
    ap.add_argument("--cutoff-ms", required=True, type=int)
    ap.add_argument("--horizon-ms", required=True, type=int)
    ap.add_argument("--dev-out", required=True)
    ap.add_argument("--oos-out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)

    rows = json.loads(Path(args.events).read_text(encoding="utf-8"))
    cutoff = int(args.cutoff_ms)
    horizon = int(args.horizon_ms)
    dev, oos, purged = [], [], 0
    for row in rows:
        t = int(row["event_time_ms"])
        if t >= cutoff:
            oos.append(row)
        elif t + horizon <= cutoff:
            dev.append(row)
        else:
            purged += 1
    Path(args.dev_out).write_text(json.dumps(dev), encoding="utf-8")
    Path(args.oos_out).write_text(json.dumps(oos), encoding="utf-8")
    report = {
        "cutoff_ms": cutoff,
        "horizon_ms": horizon,
        "n_in": len(rows),
        "n_dev": len(dev),
        "n_oos": len(oos),
        "n_purged_dev_crossing": purged,
        "note": "dev windows never cross the cutoff; "
                "eval = time-held-out (non-pristine, see design doc)",
    }
    Path(args.report).write_text(json.dumps(report, indent=1),
                                 encoding="utf-8")
    print("in=%d dev=%d oos=%d purged=%d" % (len(rows), len(dev), len(oos),
                                            purged))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
