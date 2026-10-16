"""Explicit stem<->UUID correspondence (link_probe_run_id).

No temporal derivation, no backfill: historic records without a link
stay absent (UNKNOWN). Never touches foreign or terminal records.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc

UUID_A = "a" * 32
UUID_B = "b" * 32


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="runlink_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    path = tmp / "probe_runtime.json"
    os.environ["MICROPROBE_RUNTIME_FILE"] = str(path)
    testcase.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
    return path


def _rmtree(path: Path) -> None:
    try:
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
    except OSError:
        pass


def _own_active(testcase, pid=None, **extra):
    import microstructure_probe.control as c
    pid = os.getpid() if pid is None else pid
    rec = {"schema": 1, "writer": "control/1", "state": "RUNNING",
           "pid": pid, "create_time": c.own_creation_time(pid),
           "started_at": "2026-10-16T00:00:00+00:00", "mode": "observe",
           "command": ["python", "-m", "microstructure_probe"],
           "duration_seconds": 600, "expected_end_at": None,
           "launcher": "dashboard", "preset": "observation-10m",
           "evidence": None, "last_exit": None}
    rec.update(extra)
    return rec


class RunLinkageTest(unittest.TestCase):
    def test_links_own_active_record(self) -> None:
        path = _temp_registry(self)
        path.write_text(json.dumps(_own_active(self)), encoding="utf-8")
        out = pc.link_probe_run_id(UUID_A)
        self.assertTrue(out["linked"])
        kept = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(kept["probe_run_id"], UUID_A)
        self.assertEqual(kept["state"], "RUNNING")

    def test_same_value_idempotent(self) -> None:
        path = _temp_registry(self)
        path.write_text(json.dumps(_own_active(self, probe_run_id=UUID_A)),
                        encoding="utf-8")
        before = path.read_bytes()
        out = pc.link_probe_run_id(UUID_A)
        self.assertTrue(out["linked"])
        self.assertEqual(path.read_bytes(), before)

    def test_different_existing_link_never_overwritten(self) -> None:
        path = _temp_registry(self)
        path.write_text(json.dumps(_own_active(self, probe_run_id=UUID_A)),
                        encoding="utf-8")
        out = pc.link_probe_run_id(UUID_B)
        self.assertFalse(out["linked"])
        self.assertEqual(out["reason"], "already-linked")
        kept = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(kept["probe_run_id"], UUID_A)

    def test_refuses_foreign_pid(self) -> None:
        path = _temp_registry(self)
        path.write_text(json.dumps(_own_active(self, pid=999998)),
                        encoding="utf-8")
        out = pc.link_probe_run_id(UUID_A)
        self.assertFalse(out["linked"])
        self.assertEqual(out["reason"], "not-ours")
        kept = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("probe_run_id", kept)

    def test_refuses_terminal_record(self) -> None:
        path = _temp_registry(self)
        rec = _own_active(self)
        rec["state"] = "COMPLETED"
        path.write_text(json.dumps(rec), encoding="utf-8")
        out = pc.link_probe_run_id(UUID_A)
        self.assertFalse(out["linked"])
        kept = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("probe_run_id", kept)

    def test_refuses_missing_record_and_bad_shapes(self) -> None:
        _temp_registry(self)
        out = pc.link_probe_run_id(UUID_A)
        self.assertFalse(out["linked"])
        for bad in (None, "", "xyz", "A" * 32, "g" * 32, 123, ["a" * 32]):
            out = pc.link_probe_run_id(bad)
            self.assertFalse(out["linked"])

    def test_status_exposes_link_and_absent_is_unknown(self) -> None:
        _temp_registry(self)
        rec = _own_active(self, probe_run_id=UUID_A)
        with mock.patch.object(pc, "_default_process_state",
                               return_value="owned"):
            out = pc._status_view(rec, pc._feed_unknown())
        self.assertEqual(out["probe_run_id"], UUID_A)
        rec2 = _own_active(self)
        with mock.patch.object(pc, "_default_process_state",
                               return_value="owned"):
            out2 = pc._status_view(rec2, pc._feed_unknown())
        self.assertIsNone(out2["probe_run_id"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
