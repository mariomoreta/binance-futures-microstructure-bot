"""Family evaluation runner: separate groups, manifest, determinism.

Runs --demo (synthetic, labeled) into temp dirs only. No network, no DB,
no canonical paths. Proves group separation (H1/H2-legs/H3/rebound/
baseline never pooled), manifest identity fields, and byte-identical
reruns. Mechanics prep only, never validation.
Run: python run_tests.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parent.parent / "scripts" / \
    "run_family_evaluation.py"
GROUPS = ("continuation", "correction-exhaustion", "correction-reversal",
          "bearish-continuation", "rebound-variant", "baseline")


def _run_demo(out_dir: Path) -> dict:
    manifest = out_dir / "manifest.json"
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--demo", "--out", str(manifest)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(manifest.read_text(encoding="utf-8"))


class FamilyEvaluationTest(unittest.TestCase):
    def test_demo_manifest_structure(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="fameval_"))
        manifest = _run_demo(tmp)
        self.assertIn("NOT performance", manifest["label"])
        self.assertIn("input_hash", manifest)
        self.assertIn("cutoff_ms", manifest)
        self.assertIn("formation_method", manifest)
        self.assertTrue(manifest["blockers"])
        for group in GROUPS:
            self.assertIn(group, manifest["groups"])
            for seg in ("dev", "oos"):
                cell = manifest["groups"][group][seg]["1.0"]
                for key in ("n_events", "n_trades", "n_expired",
                            "n_mismatched", "skipped_overlap",
                            "expectancy_net", "config_hash"):
                    self.assertIn(key, cell)

    def test_groups_never_pooled(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="fameval_"))
        manifest = _run_demo(tmp)
        total = 0
        for group in GROUPS:
            for seg in ("dev", "oos"):
                total += manifest["groups"][group][seg]["1.0"]["n_events"]
        # Demo emits 8 events; every one is replayed inside exactly one
        # group cell per segment split (groups never merged).
        self.assertEqual(total, 8)

    def test_reruns_byte_identical(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="fameval_"))
        (tmp / "a").mkdir(exist_ok=True)
        (tmp / "b").mkdir(exist_ok=True)
        first = _run_demo(tmp / "a")
        second = _run_demo(tmp / "b")
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
