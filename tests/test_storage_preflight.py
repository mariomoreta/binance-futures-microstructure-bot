"""Storage preflight: measured-only contract (temp roots, no real paths).

Proves missing inputs become UNKNOWN (never zero-filled), retention
constants come from code, --compare yields a measured delta, and exit 0
carries warnings[] instead of failing. No network, no DB writes.
Run: python run_tests.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / \
    "storage_preflight.py"


def _run(root: Path, *extra: str) -> tuple[int, dict]:
    out = root / "preflight.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root),
         "--out", str(out), *extra],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return proc.returncode, json.loads(out.read_text(encoding="utf-8"))


class PreflightContractTest(unittest.TestCase):
    def test_empty_root_is_unknown_never_zero(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="preflight_"))
        _, report = _run(tmp)
        self.assertIsNone(report["operational_db"]["bytes"])
        self.assertIn("absent", report["operational_db"]["status"])
        self.assertIsNone(report["historical_db"]["bytes"])
        self.assertTrue(report["warnings"])
        self.assertEqual(report["growth"],
                         "UNKNOWN (no --compare snapshot supplied)")

    def test_retention_comes_from_code(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="preflight_"))
        _, report = _run(tmp)
        ret = report["retention_from_code"]
        self.assertEqual(ret["research_retention_days"],
                         {"flow_10s": 7, "flow_1m": 90, "book_1m": 90})
        self.assertEqual(ret["operational_row_caps"]["max_observations"],
                         "10000")
        self.assertEqual(ret["prospective_retention_days"]
                         ["prospective_setups"], "90")

    def test_compare_measures_delta(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="preflight_"))
        data = tmp / "data"
        data.mkdir()
        (data / "microprobe.db").write_bytes(b"x" * 100)
        first_out = tmp / "first.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(tmp),
             "--out", str(first_out)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        (data / "microprobe.db").write_bytes(b"x" * 160)
        # NOTE: --out must differ from --compare (self-overwrite refused).
        second_out = tmp / "second.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(tmp),
             "--out", str(second_out), "--compare", str(first_out)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        second = json.loads(second_out.read_text(encoding="utf-8"))
        comps = second["growth"]["components"]
        self.assertEqual(comps["operational_db"]["delta"], 60)
        self.assertEqual(second["growth"]["basis"],
                         "measured per-component delta vs --compare file")


if __name__ == "__main__":
    unittest.main()
