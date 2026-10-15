"""Recover a hot-journal SQLite DB on a TEMP COPY (never the canonical).

Procedure (tested, 2026-10-15; canonical application needs explicit
user authorization, see docs/DB_MAINTENANCE_RECOVERY.md):
  1. Copy <db> + <db>-journal together into a temp dir (hashes recorded
     before/after; abort if the source pair changes mid-copy).
  2. Open the COPY read-write (mode=rw): SQLite auto-recovers the hot
     journal on first write-capable open. No manual SQL, no deletes.
  3. Verify on the copy: PRAGMA integrity_check, schema_version,
     per-table counts, and that the journal is consumed.
  4. Report only. The canonical pair is never opened, never written.

Usage:
  python scripts/recover_hot_journal.py --db data/microprobe.db
      --out <temp>/recovery_report.json
Exit 0 with report; exit 2 on unusable invocation or hash mismatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


COUNT_TABLES = ("telemetry_snapshots", "market_observations",
                "rejected_observations", "price_samples", "flow_buckets",
                "prospective_setups", "prospective_outcomes",
                "universe_events", "state_transitions")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    src = Path(args.db)
    journal = Path(str(src) + "-journal")
    if not src.is_file() or not journal.is_file():
        print("need <db> + <db>-journal pair", file=sys.stderr)
        return 2
    before = {"db": _sha(src), "journal": _sha(journal),
              "db_bytes": src.stat().st_size,
              "journal_bytes": journal.stat().st_size}
    work = Path(tempfile.mkdtemp(prefix="journal-recovery-"))
    copy = work / "copy.db"
    copy_journal = Path(str(copy) + "-journal")
    shutil.copyfile(src, copy)
    shutil.copyfile(journal, copy_journal)
    if _sha(src) != before["db"] or _sha(journal) != before["journal"]:
        print("source pair changed mid-copy; aborting", file=sys.stderr)
        return 2
    report = {
        "label": "HOT-JOURNAL recovery rehearsal (temp copy only)",
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(src),
        "source_hashes_before": before,
        "workdir": str(work),
    }
    con = sqlite3.connect(str(copy))
    try:
        # A write-capable open recovers the hot journal automatically.
        con.execute("PRAGMA journal_mode=DELETE")
        integrity = con.execute("PRAGMA integrity_check").fetchall()
        schema = con.execute("SELECT value FROM persistence_meta"
                             " WHERE key='schema_version'").fetchone()
        counts = {}
        for table in COUNT_TABLES:
            try:
                counts[table] = con.execute(
                    "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
            except sqlite3.Error as exc:
                counts[table] = "ERR %s" % str(exc)[:80]
        con.commit()
    finally:
        con.close()
    report["integrity_check"] = [r[0] for r in integrity]
    report["schema_version"] = schema[0] if schema else None
    report["counts"] = counts
    report["journal_consumed"] = (not copy_journal.exists()
                                  or copy_journal.stat().st_size == 0)
    report["copy_db_bytes"] = copy.stat().st_size
    report["source_hashes_after"] = {"db": _sha(src),
                                     "journal": _sha(journal)}
    report["canonical_untouched"] = (
        report["source_hashes_after"] == {k: before[k] for k in
                                          ("db", "journal")})
    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
