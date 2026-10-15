"""Hot-journal recovery script: rehearsal + --apply on TEMP fixtures only.

Covers (2026-10-15): rehearsal PASS with journal consumption and origin
preservation; rehearsal FAIL on schema/count/table violations; --out and
--backup-dir protections incl. symlink aliases; full --apply (backup +
hash proof + restore rehearsal + target recovery) on a temp hot-journal
DB; --apply refusals (hashes, in-repo backup, missing flags, existing
backup). The canonical pair is never referenced here.
Run: python run_tests.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "recover_hot_journal.py"


def _script_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "recover_hot_journal", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

TABLES = ("telemetry_snapshots", "market_observations",
          "rejected_observations", "price_samples", "flow_buckets",
          "prospective_setups", "prospective_outcomes",
          "universe_events", "state_transitions")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*extra: str, cwd: Path | None = None):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *extra],
        capture_output=True, text=True, timeout=180,
        cwd=str(cwd) if cwd else None)
    return proc.returncode, proc.stdout, proc.stderr


def _hot_fixture(tmp: Path) -> Path:
    """Build a temp DB with a genuine hot journal (child dies mid-txn)."""
    db = tmp / "fix.db"
    con = sqlite3.connect(str(db))
    try:
        con.execute("CREATE TABLE persistence_meta (key TEXT PRIMARY KEY,"
                    " value TEXT NOT NULL)")
        con.execute("INSERT INTO persistence_meta VALUES"
                    " ('schema_version', '10')")
        for table in TABLES:
            con.execute("CREATE TABLE %s (id INTEGER PRIMARY KEY,"
                        " v TEXT)" % table)
            con.executemany("INSERT INTO %s (v) VALUES (?)" % table,
                            [("a%d" % n,) for n in range(3)])
        con.commit()
    finally:
        con.close()
    killer = ("import sqlite3, os; con = sqlite3.connect(%r);"
              " con.execute('BEGIN IMMEDIATE');"
              " con.execute(\"INSERT INTO telemetry_snapshots (v) VALUES"
              " ('doomed')\"); os._exit(0)" % str(db))
    proc = subprocess.run([sys.executable, "-c", killer],
                          capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert (tmp / "fix.db-journal").exists(), "no hot journal produced"
    return db


class RehearseTest(unittest.TestCase):
    def test_rehearse_passes_and_preserves_origin(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_rehearse_"))
        db = _hot_fixture(tmp)
        journal = Path(str(db) + "-journal")
        before = (_sha(db), _sha(journal))
        out = tmp / "report.json"
        code, _, _ = _run("--db", str(db), "--out", str(out),
                          "--expect-schema", "10")
        self.assertEqual(code, 0)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["integrity_check"], ["ok"])
        # Fixture sidecars carry no valid journal magic on this stack
        # (proven): reported stale-ignored, demonstrably harmless —
        # the read-only verify above is the proof.
        self.assertEqual(report["journal"]["kind"], "stale-or-foreign")
        self.assertTrue(report["journal_stale_ignored"])
        self.assertTrue(report["canonical_untouched"])
        self.assertEqual((_sha(db), _sha(journal)), before)
        for table in TABLES:
            self.assertEqual(report["recovered_counts"][table], 3)

    def test_rehearse_consumes_magic_valid_journal(self) -> None:
        # White-box branch coverage for kind==hot-rollback: a synthetic
        # valid magic is patched onto the fixture sidecar (this stack
        # never produces one; construction documented, NOT evidence).
        # The genuine hot path is proven by the canonical-copy rehearsal
        # in docs/evidence (real magic, real consumption).
        tmp = Path(tempfile.mkdtemp(prefix="jr_hot_"))
        db = _hot_fixture(tmp)
        journal = Path(str(db) + "-journal")
        raw = bytearray(journal.read_bytes())
        raw[:8] = bytes.fromhex("d9d505f920a163d7")
        journal.write_bytes(bytes(raw))
        out = tmp / "report.json"
        code, _, _ = _run("--db", str(db), "--out", str(out),
                          "--expect-schema", "10")
        self.assertEqual(code, 0)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["journal"]["kind"], "hot-rollback")
        self.assertTrue(report["journal_consumed"])

    def test_rehearse_fails_on_schema_mismatch(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_schema_"))
        db = _hot_fixture(tmp)
        out = tmp / "report.json"
        code, _, err = _run("--db", str(db), "--out", str(out),
                            "--expect-schema", "99")
        self.assertEqual(code, 1)
        self.assertIn("schema", err)
        self.assertTrue((tmp / "fix.db-journal").exists())

    def test_rehearse_fails_on_missing_table(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_table_"))
        db = _hot_fixture(tmp)
        con = sqlite3.connect(str(db))
        try:
            con.execute("DROP TABLE flow_buckets")
            con.commit()
        finally:
            con.close()
        # Re-kill mid-txn to keep the journal hot after the DDL change.
        killer = ("import sqlite3, os; con = sqlite3.connect(%r);"
                  " con.execute('BEGIN IMMEDIATE');"
                  " con.execute(\"INSERT INTO telemetry_snapshots (v)"
                  " VALUES ('doomed')\"); os._exit(0)" % str(db))
        subprocess.run([sys.executable, "-c", killer], check=True,
                       capture_output=True, timeout=60)
        out = tmp / "report.json"
        code, _, _ = _run("--db", str(db), "--out", str(out),
                          "--expect-schema", "10")
        self.assertEqual(code, 1)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "FAIL")

    def test_rehearse_fails_on_expect_counts_mismatch(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_counts_"))
        db = _hot_fixture(tmp)
        want = tmp / "want.json"
        want.write_text(json.dumps({"telemetry_snapshots": 999}),
                        encoding="utf-8")
        out = tmp / "report.json"
        code, _, _ = _run("--db", str(db), "--out", str(out),
                          "--expect-schema", "10",
                          "--expect-counts", str(want))
        self.assertEqual(code, 1)


class ProtectionTest(unittest.TestCase):
    def test_out_equal_to_db_is_refused(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_prot_"))
        db = _hot_fixture(tmp)
        code, _, _ = _run("--db", str(db), "--out", str(db))
        self.assertEqual(code, 2)
        self.assertTrue((tmp / "fix.db-journal").exists())

    def test_out_via_symlink_to_db_is_refused(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_link_"))
        db = _hot_fixture(tmp)
        link = tmp / "out.json"
        try:
            link.symlink_to(db)
        except OSError:
            self.skipTest("symlinks unavailable")
        code, _, _ = _run("--db", str(db), "--out", str(link))
        self.assertEqual(code, 2)

    def test_out_with_db_suffix_is_refused(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_suf_"))
        db = _hot_fixture(tmp)
        code, _, _ = _run("--db", str(db),
                          "--out", str(tmp / "evil.db-journal"))
        self.assertEqual(code, 2)

    def test_existing_out_is_never_overwritten(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_exist_"))
        db = _hot_fixture(tmp)
        out = tmp / "report.json"
        out.write_text("PREVIOUS", encoding="utf-8")
        code, _, _ = _run("--db", str(db), "--out", str(out))
        self.assertEqual(code, 2)
        self.assertEqual(out.read_text(encoding="utf-8"), "PREVIOUS")


class ApplyTest(unittest.TestCase):
    def _hashes(self, db: Path):
        return (_sha(db), _sha(Path(str(db) + "-journal")))

    def test_apply_full_cycle_on_temp_fixture(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_apply_"))
        db = _hot_fixture(tmp)
        backup = Path(tempfile.mkdtemp(prefix="jr_backup_"))
        before = self._hashes(db)
        out = tmp / "report.json"
        code, _, _ = _run(
            "--db", str(db), "--out", str(out), "--expect-schema", "10",
            "--apply", "--backup-dir", str(backup),
            "--expect-db-sha256", before[0],
            "--expect-journal-sha256", before[1])
        self.assertEqual(code, 0)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "PASS")
        # Backup restorable + verified both ways.
        self.assertEqual(report["backup_hashes"],
                         {"db": before[0], "journal": before[1]})
        self.assertEqual(report["restore_verification"]["integrity_check"],
                         ["ok"])
        # Target recovered (stale sidecar reported, rows preserved).
        self.assertEqual(report["journal"]["kind"], "stale-or-foreign")
        self.assertTrue(report["journal_stale_ignored"])
        for table in TABLES:
            self.assertEqual(report["applied_verification"]["counts"][table],
                             3)
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        try:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM telemetry_snapshots")
                .fetchone()[0], 3)
        finally:
            con.close()

    def test_apply_refuses_hash_mismatch(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_hm_"))
        db = _hot_fixture(tmp)
        backup = Path(tempfile.mkdtemp(prefix="jr_hmb_"))
        out = tmp / "report.json"
        code, _, _ = _run(
            "--db", str(db), "--out", str(out), "--apply",
            "--backup-dir", str(backup),
            "--expect-db-sha256", "0" * 64,
            "--expect-journal-sha256", "0" * 64)
        self.assertEqual(code, 2)
        # Nothing applied: journal still hot, no backup files.
        self.assertTrue((tmp / "fix.db-journal").exists())
        self.assertFalse((backup / "copy.db").exists())

    def test_apply_refuses_in_repo_backup(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_repo_"))
        db = _hot_fixture(tmp)
        before = self._hashes(db)
        out = tmp / "report.json"
        code, _, _ = _run(
            "--db", str(db), "--out", str(out), "--apply",
            "--backup-dir", str(ROOT / "tmp_backup_probe"),
            "--expect-db-sha256", before[0],
            "--expect-journal-sha256", before[1])
        self.assertEqual(code, 2)
        self.assertFalse((ROOT / "tmp_backup_probe").exists())

    def test_apply_needs_flags(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_flags_"))
        db = _hot_fixture(tmp)
        out = tmp / "report.json"
        code, _, _ = _run("--db", str(db), "--out", str(out), "--apply",
                          "--backup-dir", str(tmp / "b"))
        self.assertEqual(code, 2)

    def test_apply_refuses_existing_backup(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_re_"))
        db = _hot_fixture(tmp)
        backup = Path(tempfile.mkdtemp(prefix="jr_reb_"))
        (backup / "copy.db").write_bytes(b"old-backup")
        (backup / "copy.db-journal").write_bytes(b"old-journal")
        before = self._hashes(db)
        out = tmp / "report.json"
        code, _, _ = _run(
            "--db", str(db), "--out", str(out), "--expect-schema", "10",
            "--apply", "--backup-dir", str(backup),
            "--expect-db-sha256", before[0],
            "--expect-journal-sha256", before[1])
        self.assertEqual(code, 2)
        # Previous backup preserved byte-for-byte, fixture untouched.
        self.assertEqual((backup / "copy.db").read_bytes(), b"old-backup")
        self.assertEqual((backup / "copy.db-journal").read_bytes(),
                         b"old-journal")
        self.assertTrue((tmp / "fix.db-journal").exists())
        self.assertEqual(self._hashes(db), before)


class DriftRegressionTest(unittest.TestCase):
    """Pre-apply drift + post-apply discrepancy (module-level, exact
    helpers used by --apply; CLI wiring proven by ApplyTest runs)."""

    def test_hashes_match_accepts_exact_pair(self) -> None:
        mod = _script_module()
        tmp = Path(tempfile.mkdtemp(prefix="jr_drift_ok_"))
        db = _hot_fixture(tmp)
        journal = Path(str(db) + "-journal")
        self.assertIsNone(mod._hashes_match(
            db, journal, _sha(db), _sha(journal)))

    def test_hashes_match_rejects_drift(self) -> None:
        mod = _script_module()
        tmp = Path(tempfile.mkdtemp(prefix="jr_drift_bad_"))
        db = _hot_fixture(tmp)
        journal = Path(str(db) + "-journal")
        err = mod._hashes_match(db, journal, "0" * 64, _sha(journal))
        self.assertIsNotNone(err)
        self.assertIn("differ", err)
        # Missing files are drift too, never a crash.
        missing = tmp / "absent.db"
        self.assertIn("cannot hash", mod._hashes_match(
            missing, journal, "0" * 64, _sha(journal)) or "")

    def test_compare_records_accepts_identical(self) -> None:
        mod = _script_module()
        snap = {"schema_version": "10",
                "counts": {"telemetry_snapshots": 1000}}
        self.assertEqual(mod._compare_records("x", snap, dict(snap)), [])

    def test_compare_records_rejects_schema_and_count_drift(self) -> None:
        mod = _script_module()
        want = {"schema_version": "10",
                "counts": {"telemetry_snapshots": 1000, "price_samples": 12}}
        got = {"schema_version": "9",
               "counts": {"telemetry_snapshots": 999, "price_samples": 12}}
        failures = mod._compare_records("applied-vs-restored", got, want)
        self.assertEqual(len(failures), 2)
        self.assertTrue(any("schema" in f for f in failures))
        self.assertTrue(any("telemetry_snapshots" in f for f in failures))

    def test_no_live_writer_probe_is_lock_only(self) -> None:
        mod = _script_module()
        tmp = Path(tempfile.mkdtemp(prefix="jr_lockfree_"))
        db = _hot_fixture(tmp)
        journal = Path(str(db) + "-journal")
        before = (_sha(db), _sha(journal))
        self.assertIsNone(mod._assert_no_live_writer(db))
        # The probe itself writes nothing (hashes identical after).
        self.assertEqual((_sha(db), _sha(journal)), before)

    def test_live_writer_is_detected(self) -> None:
        mod = _script_module()
        tmp = Path(tempfile.mkdtemp(prefix="jr_locked_"))
        db = _hot_fixture(tmp)
        holder = sqlite3.connect(str(db), timeout=30)
        self.addCleanup(holder.close)
        holder.execute("BEGIN IMMEDIATE")
        err = mod._assert_no_live_writer(db, timeout_s=2.0)
        self.assertIsNotNone(err)
        self.assertIn("writer", err)


class WriterExclusionTest(unittest.TestCase):
    def test_apply_refuses_while_writer_holds_lock(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_wexcl_"))
        db = _hot_fixture(tmp)
        holder = sqlite3.connect(str(db), timeout=30)
        self.addCleanup(holder.close)
        holder.execute("BEGIN IMMEDIATE")
        before = (_sha(db), _sha(Path(str(db) + "-journal")))
        backup = Path(tempfile.mkdtemp(prefix="jr_wexclb_"))
        out = tmp / "report.json"
        code, _, err = _run(
            "--db", str(db), "--out", str(out), "--expect-schema", "10",
            "--apply", "--backup-dir", str(backup),
            "--expect-db-sha256", before[0],
            "--expect-journal-sha256", before[1])
        self.assertEqual(code, 2)
        self.assertIn("writer", err)
        # Refused before any backup or target write.
        self.assertFalse((backup / "copy.db").exists())
        self.assertFalse(out.exists())
        self.assertEqual(
            (_sha(db), _sha(Path(str(db) + "-journal"))), before)

    def test_successful_apply_records_pre_apply_hashes(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="jr_pah_"))
        db = _hot_fixture(tmp)
        backup = Path(tempfile.mkdtemp(prefix="jr_pahb_"))
        before = (_sha(db), _sha(Path(str(db) + "-journal")))
        out = tmp / "report.json"
        code, _, _ = _run(
            "--db", str(db), "--out", str(out), "--expect-schema", "10",
            "--apply", "--backup-dir", str(backup),
            "--expect-db-sha256", before[0],
            "--expect-journal-sha256", before[1])
        self.assertEqual(code, 0)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["pre_apply_hashes"],
                         {"db": before[0], "journal": before[1]})
        self.assertEqual(report["writer_check"], "excluded")


if __name__ == "__main__":
    unittest.main()
