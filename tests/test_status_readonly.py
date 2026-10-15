"""P1-14B.8 V2-51: pure status_readonly() + fenced reconciliation.

Fail-before regressions (deterministic temp registries, no live probe):

  S1  status_readonly exists with the same nullable shape as status().
  S2  missing record: STOPPED shape, no file created.
  S3  dead/reused PID: state preserved as-is, file bytes identical.
  S4  STOPPING/ABORTED races: stored state preserved, bytes identical.
  S5  no writes, no reconciliation, no log-handle mutation, no process
      action (all destructive surface mocked and asserted uncalled).
  S6  legacy status() never overwrites a terminal record with FAILED,
      even when its initial read is stale (locked fenced reconciliation).

On 0786617 S1 fails (AttributeError), S3-S4 mutate, S6 overwrites ABORTED
with FAILED. Run: python run_tests.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="readonly_"))
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


def _run_record(pid=424243, state="RUNNING", ctime="STAMP"):
    return {"schema": 1, "writer": "control/1", "state": state,
            "pid": pid, "create_time": ctime,
            "started_at": "2026-10-10T10:00:00+00:00", "mode": "observe",
            "command": [sys.executable, "-m", "microstructure_probe"],
            "duration_seconds": 2100, "expected_end_at": None,
            "launcher": "agent", "preset": "standard",
            "evidence": {"dir": "ev", "log": "run.log"},
            "last_exit": None}


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReadonlyShapeTest(unittest.TestCase):
    def test_method_exists_with_same_shape(self):
        _temp_registry(self)
        self.assertTrue(callable(getattr(pc, "status_readonly", None)))
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            full = pc.status()
            pure = pc.status_readonly()
        self.assertEqual(set(pure.keys()), set(full.keys()))
        for key in ("running", "state", "pid", "started_at", "uptime_seconds",
                    "mode", "duration_seconds", "elapsed_seconds",
                    "remaining_seconds", "expected_end_at", "launcher",
                    "preset", "last_exit_code", "last_exit_reason",
                    "supervisor", "sentinel"):
            self.assertIn(key, pure)
        for block in (pure["supervisor"], pure["sentinel"]):
            self.assertIsInstance(block, dict)
            self.assertIn("state", block)
        # Non-empty records carry evidence in both views identically.
        pc._write_registry(_run_record(state="RUNNING"))
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            full = pc.status()
            pure = pc.status_readonly()
        self.assertEqual(set(pure.keys()), set(full.keys()))
        self.assertIn("evidence", pure)
        self.assertEqual(pure["evidence"], full["evidence"])

    def test_missing_record_no_file_created(self):
        path = _temp_registry(self)
        out = pc.status_readonly()
        self.assertEqual(out["state"], "STOPPED")
        self.assertFalse(out["running"])
        self.assertIsNone(out["pid"])
        self.assertEqual(out["supervisor"]["state"], "SUPERVISOR_UNKNOWN")
        self.assertEqual(out["sentinel"]["state"], "SENTINEL_UNKNOWN")
        self.assertFalse(path.exists())


class ReadonlyPreservationTest(unittest.TestCase):
    def _bytes(self, path):
        return path.read_bytes()

    def test_dead_pid_preserved(self):
        path = _temp_registry(self)
        rec = _run_record(state="RUNNING")
        path.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        before = self._bytes(path)
        with mock.patch.object(pc, "is_canonical_pid", return_value=False):
            with mock.patch.object(pc, "_write_registry") as wr:
                with mock.patch.object(pc, "update_registry") as up:
                    with mock.patch.object(pc, "_close_log_handles") as cl:
                        out = pc.status_readonly()
        self.assertEqual(out["state"], "RUNNING")
        wr.assert_not_called()
        up.assert_not_called()
        cl.assert_not_called()
        self.assertEqual(self._bytes(path), before)

    def test_stopping_preserved(self):
        path = _temp_registry(self)
        rec = _run_record(state="STOPPING")
        rec["stopping_by"] = "enforce:supervisor:123"
        path.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        before = self._bytes(path)
        out = pc.status_readonly()
        self.assertEqual(out["state"], "STOPPING")
        self.assertEqual(self._bytes(path), before)

    def test_aborted_preserved(self):
        path = _temp_registry(self)
        rec = _run_record(state="ABORTED")
        rec["abort_reason"] = "preserve-me"
        path.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        before = self._bytes(path)
        out = pc.status_readonly()
        self.assertEqual(out["state"], "ABORTED")
        self.assertEqual(out["last_exit_reason"], None)
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored.get("abort_reason"), "preserve-me")
        self.assertEqual(self._bytes(path), before)

    def test_no_process_action(self):
        _temp_registry(self)
        rec = _run_record(state="RUNNING")
        pc._write_registry(rec)
        with mock.patch.object(pc, "_terminate_verified_pid") as term:
            with mock.patch("os.kill") as kill:
                with mock.patch.object(pc, "is_canonical_pid",
                                       return_value=False):
                    pc.status_readonly()
        term.assert_not_called()
        kill.assert_not_called()


class TerminalCounterTest(unittest.TestCase):
    def _aborted(self):
        rec = _run_record(state="ABORTED")
        rec["started_at"] = "2026-10-15T00:07:31+00:00"
        rec["last_exit"] = {"code": 0,
                            "reason": "aborted-timestamp-reject-rate",
                            "at": "2026-10-15T00:08:34+00:00"}
        return rec

    def test_terminal_elapsed_freezes_at_recorded_exit(self) -> None:
        # Pilot probe-20261015T000730Z: ABORTED at 00:08:34Z kept ticking
        # elapsed/uptime with the wall clock, looking alive in V2.
        out = pc._status_view(self._aborted(), {})
        self.assertFalse(out["running"])
        self.assertEqual(out["state"], "ABORTED")
        self.assertEqual(out["elapsed_seconds"], 63.0)
        self.assertEqual(out["uptime_seconds"], 63.0)
        self.assertIsNone(out["remaining_seconds"])

    def test_active_run_still_ticks(self) -> None:
        out = pc._status_view(_run_record(state="RUNNING"), {})
        self.assertTrue(out["elapsed_seconds"] > 0.0)
        self.assertTrue(out["running"])

    def test_terminal_without_recorded_exit_never_crashes(self) -> None:
        rec = self._aborted()
        rec["last_exit"] = {"code": 0, "reason": "legacy", "at": None}
        out = pc._status_view(rec, {})
        self.assertEqual(out["state"], "ABORTED")
        self.assertTrue(out["elapsed_seconds"] >= 0.0)


class FencedReconciliationTest(unittest.TestCase):
    def test_status_never_overwrites_terminal(self):
        _temp_registry(self)
        old = _run_record(state="RUNNING")
        new = _run_record(state="ABORTED")
        new["abort_reason"] = "preserve-me"
        pc._write_registry(new)
        before = _sha(Path(os.environ["MICROPROBE_RUNTIME_FILE"]))
        with mock.patch.object(pc, "read_registry", return_value=dict(old)):
            with mock.patch.object(pc, "is_canonical_pid",
                                   return_value=False):
                out = pc.status()
        # Legacy mutating status must not convert its stale RUNNING view
        # into a FAILED write that clobbers the stored ABORTED record.
        self.assertNotEqual(out.get("state"), "FAILED")
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "ABORTED")
        self.assertEqual(final.get("abort_reason"), "preserve-me")
        self.assertEqual(_sha(Path(os.environ["MICROPROBE_RUNTIME_FILE"])),
                         before)
