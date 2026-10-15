"""Hot-journal recovery: rehearse on copies, apply only with backup + proof.

MODES (never touch the canonical pair without explicit user
authorization; see docs/DB_MAINTENANCE_RECOVERY.md):

  rehearse (default): copy <db> + <db>-journal to temp, recover the COPY,
    assert integrity/schema/tables/counts/origin-preservation. The source
    pair is only read (stat/copy); nothing is created beside it.
  --apply: same verifications PLUS a mandatory restorable backup of the
    pair OUTSIDE the repo, hash-verified on both copies, and a restore
    rehearsal from that backup — before opening the target read-write.
    Requires --backup-dir, --expect-db-sha256 and --expect-journal-sha256
    (the operator binds the exact reviewed state; any drift refuses).

PROTECTIONS (exit 2, nothing written): --out or --backup-dir resolving
(realpath: symlinks/hardlinks included) to the db, the journal, the
data dir, each other, or a *.db/*.db-wal/*.db-shm/*.db-journal path is
refused; existing backup files are never overwritten; existing --out is
never overwritten.

FAIL CONDITIONS (exit 1, nothing applied): integrity_check != ["ok"],
schema != --expect-schema (when given), any expected table missing or
unreadable, --expect-counts mismatch, backup hash mismatch, source pair
changed mid-operation, restore rehearsal mismatch, pre-apply hash drift,
applied-vs-restored schema/counts discrepancy (automatic, even without
--expect-counts). Maintenance-window REFUSALS (exit 2, nothing touched):
--apply requires a non-ACTIVE registry record (pure JSON read, zero
SQLite) plus re-verified expected hashes at entry AND immediately
before the target write. No SQLite open with recovery capacity touches
the original before the verified backup exists; no step claims
sustained exclusion — every gate re-proves the window.

Usage:
  rehearse: python scripts/recover_hot_journal.py --db <db>
      --out report.json [--expect-schema 10]
      [--expect-counts counts.json]
  apply:    ... --apply --backup-dir <outside-repo-dir>
      --expect-db-sha256 <hex> --expect-journal-sha256 <hex>
      [--expect-schema 10] [--expect-counts counts.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


COUNT_TABLES = ("telemetry_snapshots", "market_observations",
                "rejected_observations", "price_samples", "flow_buckets",
                "prospective_setups", "prospective_outcomes",
                "universe_events", "state_transitions")
META_TABLES = ("persistence_meta",)
PROTECTED_SUFFIXES = (".db", ".db-wal", ".db-shm", ".db-journal")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


ROLLBACK_MAGIC = "d9d505f920a163d7"


def _hashes_match(db: Path, journal: Path, exp_db: str | None,
                  exp_journal: str | None) -> str | None:
    """None when both live hashes equal the expected hex (case-insensitive),
    else an error string. Used at entry AND immediately before the target
    write: any drift refuses without applying."""
    try:
        got_db, got_journal = _sha(db), _sha(journal)
    except OSError as exc:
        return "cannot hash source pair: %s" % str(exc)[:120]
    if got_db != (exp_db or "").lower() or \
            got_journal != (exp_journal or "").lower():
        return ("source hashes differ from expected (state changed;"
                " rehearsal no longer applies)")
    return None


ACTIVE_REGISTRY_STATES = ("STARTING", "RUNNING", "STOPPING")
# Mirrors control._is_active_state (documented copy; terminal states
# ABORTED/STOPPED/COMPLETED/FAILED are inactive).


def _registry_state() -> tuple:
    """Recorded runtime state from the JSON registry (pure file read).

    Returns (state, note). No SQLite, no processes, no writes — safe at
    any point, including before the backup. Absent/unreadable registry
    is UNKNOWN (proceeding; the hash gates remain the hard net), never
    a proof of anything.
    """
    override = os.environ.get("MICROPROBE_RUNTIME_FILE")
    path = Path(override) if override else (
        Path(__file__).resolve().parent.parent / "logs" / "probe_runtime.json")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "registry unreadable/absent: %s" % path
    if not isinstance(record, dict):
        return None, "registry malformed (not an object)"
    return record.get("state"), "recorded state via %s" % path


def _refuse_active_registry(report: dict) -> str | None:
    """Error string when the registry records an ACTIVE run, else None.

    Maintenance window, first net: a recorded active run means a project
    writer may be live — refuse without touching anything. This detects
    RECORDED activity only; it never claims sustained exclusion (a writer
    without a record is outside this net). The hash re-verification
    immediately before the target write is the second net: any writer
    commit changes bytes and refuses there.
    """
    state, note = _registry_state()
    report["registry_check"] = {"state": state, "note": note}
    if state in ACTIVE_REGISTRY_STATES:
        return ("maintenance window blocked: registry records ACTIVE run"
                " (state=%s); stop it and re-run" % state)
    return None


def _compare_records(name: str, got: dict, want: dict) -> list:
    """Field-wise schema+counts comparison; any difference is a failure."""
    failures = []
    if got.get("schema_version") != want.get("schema_version"):
        failures.append("%s schema %r != %r"
                        % (name, got.get("schema_version"),
                           want.get("schema_version")))
    for table, want_n in (want.get("counts") or {}).items():
        got_n = (got.get("counts") or {}).get(table)
        if got_n != want_n:
            failures.append("%s count %s: got %r, expected %r"
                            % (name, table, got_n, want_n))
    return failures


def _journal_kind(journal: Path) -> dict:
    """Classify the sidecar by read-only magic sniffing (never modifies).

    hot-rollback: valid rollback-journal magic — SQLite rolls it back on
      the first write transaction and refuses readOnly opens until then.
    stale-or-foreign: anything else (zeroed/partial/foreign files).
      Proven 2026-10-15: SQLite ignores such files; readOnly opens work
      with them present, and no write transaction consumes them. They
      are reported, never deleted, never required gone.
    """
    try:
        magic = journal.read_bytes()[:8].hex()
    except OSError:
        magic = ""
    kind = "hot-rollback" if magic == ROLLBACK_MAGIC else "stale-or-foreign"
    return {"kind": kind, "magic": magic,
            "bytes": journal.stat().st_size
            if journal.exists() else None}


def _real(path: Path) -> str:
    return os.path.realpath(os.path.abspath(path))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _counts(con: sqlite3.Connection) -> dict:
    out = {}
    for table in COUNT_TABLES + META_TABLES:
        try:
            out[table] = con.execute(
                "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
        except sqlite3.Error as exc:
            out[table] = "ERR %s" % str(exc)[:80]
    return out


def _immutable_counts(db_path: Path) -> dict:
    con = sqlite3.connect("file:%s?immutable=1" % db_path, uri=True)
    try:
        return _counts(con)
    finally:
        con.close()


def _recover(path: Path) -> None:
    # A hot journal rolls back when a WRITE transaction takes RESERVED;
    # reads (and PRAGMA journal_mode) never trigger it (proven 2026-10-15:
    # the canonical journal survived opens, SELECTs and the mode setter,
    # and vanished on the first write). The no-op UPDATE writes identical
    # values: zero data change, full recovery. Runs on copies/target only,
    # never on a read-only source. Any sqlite/OSError becomes a clean
    # FAIL at the caller (never a traceback).
    try:
        con = sqlite3.connect(str(path))
    except (sqlite3.Error, OSError) as exc:
        raise RuntimeError("cannot open for recovery: %s" % str(exc)[:120])
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for meta in ("persistence_meta", "history_meta"):
            if meta in tables:
                con.execute("UPDATE %s SET value=value"
                            " WHERE key='schema_version'" % meta)
                con.commit()
                return
        raise RuntimeError("no known meta table for no-op write")
    except (sqlite3.Error, OSError) as exc:
        raise RuntimeError("recovery write failed: %s" % str(exc)[:160])
    finally:
        try:
            con.close()
        except (sqlite3.Error, OSError):
            pass


def _verify(path: Path) -> dict:
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        integrity = [r[0] for r in
                     con.execute("PRAGMA integrity_check").fetchall()]
        try:
            schema = con.execute("SELECT value FROM persistence_meta"
                                 " WHERE key='schema_version'").fetchone()
            schema = schema[0] if schema else None
        except sqlite3.Error:
            schema = None
        return {"integrity_check": integrity, "schema_version": schema,
                "counts": _counts(con)}
    finally:
        con.close()


def _fail(report: dict, out: Path, reasons: list) -> int:
    report["verdict"] = "FAIL"
    report["failures"] = reasons
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    for reason in reasons:
        print("FAIL: " + reason, file=sys.stderr)
    return 1


def _protect(args, db: Path, journal: Path, out: Path,
             report: dict) -> list:
    problems = []
    if out.exists():
        problems.append("refusing to overwrite existing --out: %s" % out)
    if str(out).endswith(PROTECTED_SUFFIXES):
        problems.append("refusing protected --out suffix: %s" % out)
    targets = {"db": _real(db), "journal": _real(journal),
               "out": _real(out)}
    if targets["out"] in (targets["db"], targets["journal"]):
        problems.append("--out resolves to the db/journal (alias incl.): %s"
                        % out)
    repo_data = os.path.join(
        _real(Path(__file__).resolve().parent.parent), "data")
    if targets["out"] == repo_data or \
            targets["out"].startswith(repo_data + os.sep):
        problems.append("--out inside the repo data dir: %s" % out)
    if args.apply:
        backup = Path(args.backup_dir)
        targets["backup"] = _real(backup)
        repo = _real(Path(__file__).resolve().parent.parent)
        if targets["backup"] == repo or targets["backup"].startswith(repo + os.sep):
            problems.append("--backup-dir inside the repo (must be outside git): %s" % backup)
        for name in ("backup",):
            if targets[name] in (targets["db"], targets["journal"],
                                 targets["out"]):
                problems.append("--backup-dir collides with inputs: %s"
                                % backup)
        for sidecar in ("copy.db", "copy.db-journal"):
            if (backup / sidecar).exists():
                problems.append("refusing to overwrite existing backup file: %s"
                                % (backup / sidecar))
    if problems:
        report["protections"] = problems
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect-schema", default=None)
    ap.add_argument("--expect-counts", default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup-dir", default=None)
    ap.add_argument("--expect-db-sha256", default=None)
    ap.add_argument("--expect-journal-sha256", default=None)
    args = ap.parse_args()

    db = Path(args.db)
    out = Path(args.out)
    journal = Path(str(db) + "-journal")
    report = {
        "label": "HOT-JOURNAL recovery",
        "mode": "apply" if args.apply else "rehearse",
        "measured_at": _utc_now(),
        "source": str(db),
        "reproduce": "python scripts/recover_hot_journal.py --db %s --out %s%s%s" % (
            db, out,
            (" --expect-schema %s" % args.expect_schema)
            if args.expect_schema else "",
            " --apply --backup-dir <outside-repo> --expect-db-sha256 <hex>"
            " --expect-journal-sha256 <hex>" if args.apply else ""),
    }
    if not db.is_file() or not journal.is_file():
        report["verdict"] = "REFUSED"
        report["protections"] = ["need <db> + <db>-journal pair"]
        print("REFUSED: need <db> + <db>-journal pair", file=sys.stderr)
        return 2
    problems = _protect(args, db, journal, out, report)
    if problems:
        report["verdict"] = "REFUSED"
        for problem in problems:
            print("REFUSED: " + problem, file=sys.stderr)
        return 2
    if args.apply:
        if not args.backup_dir or not args.expect_db_sha256 \
                or not args.expect_journal_sha256:
            report["verdict"] = "REFUSED"
            report["protections"] = [
                "--apply needs --backup-dir + --expect-db-sha256 +"
                " --expect-journal-sha256"]
            print("REFUSED: " + report["protections"][0], file=sys.stderr)
            return 2

    before = {"db": _sha(db), "journal": _sha(journal),
              "db_bytes": db.stat().st_size,
              "journal_bytes": journal.stat().st_size}
    report["source_hashes_before"] = before
    report["journal"] = _journal_kind(journal)
    if args.apply:
        drift = _hashes_match(db, journal, args.expect_db_sha256,
                              args.expect_journal_sha256)
        if drift is not None:
            report["verdict"] = "REFUSED"
            report["protections"] = [drift]
            for problem in report["protections"]:
                print("REFUSED: " + problem, file=sys.stderr)
            return 2
    if args.apply:
        blocked = _refuse_active_registry(report)
        if blocked is not None:
            report["verdict"] = "REFUSED"
            print("REFUSED: " + blocked, file=sys.stderr)
            return 2
    try:
        pre = _immutable_counts(db)
    except sqlite3.Error as exc:
        return _fail(report, out,
                     ["pre-recovery immutable read failed: %s" % str(exc)[:120]])
    report["pre_recovery_counts"] = pre

    try:
        if args.apply:
            return _apply(args, db, journal, out, report, before, pre)
        return _rehearse(args, db, journal, out, report, before, pre)
    except (sqlite3.Error, OSError, RuntimeError) as exc:
        return _fail(report, out, ["recovery failed: %s" % str(exc)[:160]])


def _check_expectations(args, verified: dict) -> list:
    failures = []
    if verified["integrity_check"] != ["ok"]:
        failures.append("integrity_check != [ok]: %r"
                        % (verified["integrity_check"],))
    if args.expect_schema is not None and \
            str(verified["schema_version"]) != str(args.expect_schema):
        failures.append("schema %r != expected %r"
                        % (verified["schema_version"], args.expect_schema))
    if args.expect_counts:
        try:
            expected = json.loads(Path(args.expect_counts).read_text(
                encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return ["unreadable --expect-counts: %s" % str(exc)[:120]]
        for table, want in expected.items():
            got = verified["counts"].get(table)
            if got != want:
                failures.append("count %s: got %r, expected %r"
                                % (table, got, want))
    for table, value in verified["counts"].items():
        if not isinstance(value, int):
            failures.append("table %s unreadable: %r" % (table, value))
    return failures


def _rehearse(args, db, journal, out, report, before, pre) -> int:
    work = Path(tempfile.mkdtemp(prefix="journal-recovery-"))
    report["workdir"] = str(work)
    copy = work / "copy.db"
    shutil.copyfile(db, copy)
    shutil.copyfile(journal, Path(str(copy) + "-journal"))
    if _sha(db) != before["db"] or _sha(journal) != before["journal"]:
        return _fail(report, out, ["source pair changed mid-copy"])
    _recover(copy)
    verified = _verify(copy)
    report["recovered_counts"] = verified["counts"]
    report["integrity_check"] = verified["integrity_check"]
    report["schema_version"] = verified["schema_version"]
    kind = report["journal"]["kind"]
    if kind == "hot-rollback":
        report["journal_consumed"] = (
            not Path(str(copy) + "-journal").exists()
            or Path(str(copy) + "-journal").stat().st_size == 0)
        if not report["journal_consumed"]:
            return _fail(report, out, ["journal not consumed on the copy"])
    else:
        # Stale/foreign sidecar: SQLite demonstrably ignores it (readOnly
        # opens succeed with it present); the read-only _verify above is
        # the proof. Reported, never deleted, never required gone.
        report["journal_consumed"] = False
        report["journal_stale_ignored"] = True
    failures = _check_expectations(args, verified)
    for table in COUNT_TABLES:
        if isinstance(pre.get(table), int) and \
                isinstance(verified["counts"].get(table), int) and \
                pre[table] != verified["counts"][table]:
            failures.append("row drift on %s: pre %r vs recovered %r"
                            % (table, pre[table],
                               verified["counts"][table]))
    after = {"db": _sha(db), "journal": _sha(journal)}
    report["source_hashes_after"] = after
    report["canonical_untouched"] = (
        after == {"db": before["db"], "journal": before["journal"]})
    if not report["canonical_untouched"]:
        failures.append("source pair changed during rehearsal")
    if failures:
        return _fail(report, out, failures)
    report["verdict"] = "PASS"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("rehearsal PASS; canonical untouched: %s"
          % report["canonical_untouched"])
    return 0


def _apply(args, db, journal, out, report, before, pre) -> int:
    # Stage 1 (temp only): recover a scratch copy and check every
    # expectation BEFORE any backup or target write. Failures here leave
    # zero side effects behind.
    stage = Path(tempfile.mkdtemp(prefix="journal-apply-stage-"))
    report["stage_workdir"] = str(stage)
    sdb = stage / "copy.db"
    shutil.copyfile(db, sdb)
    shutil.copyfile(journal, Path(str(sdb) + "-journal"))
    _recover(sdb)
    staged = _verify(sdb)
    report["stage_verification"] = {
        "integrity_check": staged["integrity_check"],
        "schema_version": staged["schema_version"],
        "counts": staged["counts"]}
    failures = _check_expectations(args, staged)
    for table in COUNT_TABLES:
        if isinstance(pre.get(table), int) and \
                isinstance(staged["counts"].get(table), int) and \
                pre[table] != staged["counts"][table]:
            failures.append("stage drift on %s: pre %r vs staged %r"
                            % (table, pre[table],
                               staged["counts"][table]))
    if failures:
        return _fail(report, out, failures)
    # Stage 2: restorable backup outside the repo, hash-verified both ways.
    backup = Path(args.backup_dir)
    try:
        backup.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        pass
    except OSError as exc:
        return _fail(report, out,
                     ["cannot create --backup-dir: %s" % str(exc)[:120]])
    for name in ("copy.db", "copy.db-journal"):
        if (backup / name).exists():
            return _fail(report, out,
                         ["backup file already exists (refusing overwrite): %s"
                          % (backup / name)])
    shutil.copyfile(db, backup / "copy.db")
    shutil.copyfile(journal, backup / "copy.db-journal")
    backup_hashes = {"db": _sha(backup / "copy.db"),
                     "journal": _sha(backup / "copy.db-journal")}
    report["backup_dir"] = str(backup)
    report["backup_hashes"] = backup_hashes
    if backup_hashes != {"db": before["db"], "journal": before["journal"]}:
        return _fail(report, out, ["backup hashes differ from source"])
    # Stage 3: restore rehearsal FROM the backup (proves it restores).
    restore = Path(tempfile.mkdtemp(prefix="journal-restore-"))
    report["restore_workdir"] = str(restore)
    rdb = restore / "copy.db"
    shutil.copyfile(backup / "copy.db", rdb)
    shutil.copyfile(backup / "copy.db-journal",
                    Path(str(rdb) + "-journal"))
    _recover(rdb)
    restored = _verify(rdb)
    report["restore_verification"] = {
        "integrity_check": restored["integrity_check"],
        "schema_version": restored["schema_version"],
        "counts": restored["counts"]}
    failures = _check_expectations(args, restored)
    for table in COUNT_TABLES:
        if isinstance(pre.get(table), int) and \
                isinstance(restored["counts"].get(table), int) and \
                pre[table] != restored["counts"][table]:
            failures.append("restore drift on %s: pre %r vs restored %r"
                            % (table, pre[table],
                               restored["counts"][table]))
    if failures:
        return _fail(report, out, failures)
    # Stage 4 (the only target write): re-verify hashes AND the
    # registry IMMEDIATELY before touching the target. Any drift, or a
    # newly ACTIVE record, refuses without applying. Together with the
    # entry checks this is the maintenance window: no step claims
    # sustained exclusion, every step re-proves it.
    pre_apply = {"db": _sha(db), "journal": _sha(journal)}
    report["pre_apply_hashes"] = pre_apply
    if pre_apply != {"db": before["db"], "journal": before["journal"]}:
        return _fail(report, out,
                     ["pre-apply drift: source pair changed since entry;"
                      " refusing without applying"])
    blocked = _refuse_active_registry(report)
    report["pre_apply_registry"] = report.pop("registry_check")
    if blocked is not None:
        return _fail(report, out, ["pre-apply " + blocked.lower()])
    _recover(db)
    applied = _verify(db)
    report["applied_verification"] = {
        "integrity_check": applied["integrity_check"],
        "schema_version": applied["schema_version"],
        "counts": applied["counts"]}
    failures = _check_expectations(args, applied)
    # Automatic post-recovery comparison against the restored backup
    # result — enforced even when the operator passed no --expect-counts.
    failures.extend(_compare_records(
        "applied-vs-restored",
        {"schema_version": applied["schema_version"],
         "counts": applied["counts"]},
        {"schema_version": restored["schema_version"],
         "counts": restored["counts"]}))
    if report["journal"]["kind"] == "hot-rollback":
        journal_gone = (not journal.exists()) or journal.stat().st_size == 0
        report["journal_consumed"] = journal_gone
        if not journal_gone:
            failures.append("journal not consumed on the target")
    else:
        report["journal_consumed"] = False
        report["journal_stale_ignored"] = True
    if failures:
        return _fail(report, out, failures)
    report["verdict"] = "PASS"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("apply PASS; backup at %s; journal %s"
          % (backup, "consumed" if report.get("journal_consumed")
             else "stale-ignored"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
