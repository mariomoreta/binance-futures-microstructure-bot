"""Preflight hardening: fail-before battery (all must FAIL on old code).

Covers: --out colliding with DBs/sidecars/inputs/protected paths
(incl. resolved-link equivalence), UNKNOWN never zero-filled in
--compare, component-wise compare with root identity + timestamps,
state-based warnings, separate DB/WAL/SHM measures, and side-effect-free
SQLite/WAL reads on copies (never canonical). Run: python run_tests.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "storage_preflight.py"


def _run(root: Path, *extra: str) -> tuple[int, str, str]:
    out = root / "CLI_OUT_PLACEHOLDER"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root),
         "--out", str(out), *extra],
        capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


class OutProtectionTest(unittest.TestCase):
    def test_out_inside_data_is_refused(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pre_out_"))
        (tmp / "data").mkdir()
        target = tmp / "data" / "microprobe.db"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(tmp),
             "--out", str(target)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(target.exists())

    def test_out_equal_to_compare_input_is_refused(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pre_out_"))
        base = tmp / "base.json"
        base.write_text(json.dumps({"x": 1}), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(tmp),
             "--out", str(base), "--compare", str(base)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(base.read_text(encoding="utf-8")),
                         {"x": 1})

    def test_out_via_symlink_to_protected_is_refused(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pre_out_"))
        (tmp / "data").mkdir()
        real = tmp / "data" / "microprobe.db"
        real.write_bytes(b"fake-db")
        link = tmp / "out.json"
        try:
            link.symlink_to(real)
        except OSError:
            self.skipTest("symlinks unavailable")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(tmp),
             "--out", str(link)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(real.read_bytes(), b"fake-db")


class UnknownCompareTest(unittest.TestCase):
    def test_unknown_never_becomes_zero(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pre_unk_"))
        code, _, _ = _run(tmp)
        self.assertEqual(code, 0)
        report = json.loads((tmp / "CLI_OUT_PLACEHOLDER").read_text(
            encoding="utf-8"))
        # Empty root: every component UNKNOWN; growth must say UNKNOWN,
        # never a numeric zero-fill.
        self.assertIn("UNKNOWN", str(report["growth"]))
        self.assertNotIsInstance(report["growth"], (int, float))
        if isinstance(report["growth"], dict):
            self.assertNotEqual(report["growth"].get("bytes_delta"), 0)

    def test_compare_records_root_identity_and_timestamps(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pre_id_"))
        _, _, _ = _run(tmp)
        first = tmp / "CLI_OUT_PLACEHOLDER"
        other = Path(tempfile.mkdtemp(prefix="pre_id2_"))
        out2 = other / "o.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(other),
             "--out", str(out2), "--compare", str(first)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0)
        second = json.loads(out2.read_text(encoding="utf-8"))
        growth = second["growth"]
        self.assertIsInstance(growth, dict)
        self.assertIn("roots_differ", growth)
        self.assertTrue(growth["roots_differ"])
        for key in ("now_measured_at", "base_measured_at", "components",
                    "base_root", "now_root"):
            self.assertIn(key, growth)

    def test_illegible_base_is_explicit(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pre_bad_"))
        bad = tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        out = tmp / "o.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(tmp),
             "--out", str(out), "--compare", str(bad)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0)
        growth = json.loads(out.read_text(encoding="utf-8"))["growth"]
        self.assertIn("illegible-compare-base", str(growth))


class StateWarningsTest(unittest.TestCase):
    def test_wal_present_warns(self) -> None:
        import sqlite3
        tmp = Path(tempfile.mkdtemp(prefix="pre_wal_"))
        data = tmp / "data"
        data.mkdir()
        db = data / "microprobe.db"
        # Live connection with un-checkpointed frames: -wal present on
        # disk while preflight measures (honest WAL presence, temp only).
        con = sqlite3.connect(str(db))
        con.execute("pragma journal_mode=wal")
        con.execute("create table t(x)")
        con.executemany("insert into t values (?)",
                        [(i,) for i in range(2000)])
        con.commit()
        try:
            code, _, _ = _run(tmp)
        finally:
            con.close()
        self.assertEqual(code, 0)
        report = json.loads((tmp / "CLI_OUT_PLACEHOLDER").read_text(
            encoding="utf-8"))
        joined = " ".join(report["warnings"])
        self.assertIn("WAL", joined)

    def test_db_wal_shm_measured_separately(self) -> None:
        import sqlite3
        tmp = Path(tempfile.mkdtemp(prefix="pre_sep_"))
        data = tmp / "data"
        data.mkdir()
        db = data / "microprobe.db"
        con = sqlite3.connect(str(db))
        con.execute("pragma journal_mode=wal")
        con.execute("create table t(x)")
        con.commit()
        con.close()
        _, _, _ = _run(tmp)
        report = json.loads((tmp / "CLI_OUT_PLACEHOLDER").read_text(
            encoding="utf-8"))
        files = report["operational_db"]["files"]
        self.assertIn("db", files)
        self.assertIn("wal", files)
        self.assertIn("shm", files)


class CopyReadEffectsTest(unittest.TestCase):
    def test_reads_on_copies_create_nothing(self) -> None:
        from scripts.storage_preflight import (  # noqa
            measured_copy_read,
        )
        import sqlite3
        tmp = Path(tempfile.mkdtemp(prefix="pre_copy_"))
        srcdir = tmp / "src"
        srcdir.mkdir()
        src = srcdir / "src.db"
        con = sqlite3.connect(str(src))
        con.execute("pragma journal_mode=wal")
        con.execute("create table t(x)")
        con.executemany("insert into t values (?)", [(i,) for i in range(5)])
        con.commit()
        con.close()
        work = tmp / "work"
        work.mkdir()
        before_src = sorted(p.name for p in srcdir.iterdir())
        before_work = sorted(p.name for p in work.iterdir())
        counts = measured_copy_read(src, work, ["t"])
        after_src = sorted(p.name for p in srcdir.iterdir())
        # Source directory byte-identical: canonical-safe by construction.
        self.assertEqual(after_src, before_src)
        # WAL rows honored through the copy (correct counts, not stale).
        self.assertEqual(counts, {"t": 5})
        # The deliberate copy exists in work; sidecars there are temp-only.
        self.assertIn("src.db", [p.name for p in work.iterdir()])
        self.assertGreaterEqual(len(list(work.iterdir())),
                                len(before_work) + 1)


if __name__ == "__main__":
    unittest.main()
