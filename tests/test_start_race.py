"""P1-14B.8 V2-52 H2: parent start vs own-child self-registration race.

Fail-before regressions (simulated spawn/kill, temp registries):

  R1  parent-first (empty registry): STARTING committed, started=True,
      kill never called.
  R2  child-first (own child RUNNING with same PID+ctime before the
      parent commit): adoption -- started=True, kill never called,
      child's RUNNING record + evidence preserved byte-for-byte
      (never overwritten with STARTING).
  R3  foreign winner (live foreign RUNNING): started=False, orphan
      cleanup kills exactly once, foreign record preserved.
  R4  same PID with different creation time (reused PID): refused as
      foreign, kill called once.
  R5  registry write failure: started=False, kill called once.

On 55efaa2 R2 fails (own child killed once, started=False). This task
does NOT extend to the V2 supervised transactional launch. Run:
python run_tests.py
"""

from __future__ import annotations

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
    tmp = Path(tempfile.mkdtemp(prefix="startrace_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    path = tmp / "probe_runtime.json"
    os.environ["MICROPROBE_RUNTIME_FILE"] = str(path)
    testcase.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
    return path, tmp


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


class _FakeProc:
    def __init__(self, pid):
        self.pid = pid
        self.kill_calls = 0

    def kill(self):
        self.kill_calls += 1


def _child_record(pid, ctime, evidence_log="child-evidence.log"):
    return {"schema": 1, "writer": "control/1", "state": "RUNNING",
            "pid": pid, "create_time": ctime,
            "started_at": "2026-10-11T00:00:00+00:00", "mode": "observe",
            "command": [sys.executable, "-m", "microstructure_probe"],
            "duration_seconds": 60, "expected_end_at": None,
            "launcher": "agent", "preset": "standard",
            "evidence": {"dir": "ev", "log": evidence_log},
            "last_exit": None}


class StartRaceTest(unittest.TestCase):
    def test_parent_first_commits_starting(self):
        _temp_registry(self)
        proc = _FakeProc(555)
        with mock.patch.object(pc.subprocess, "Popen", return_value=proc):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="C555"):
                out = pc.start_probe(duration_seconds=60,
                                     evidence_dir=Path(tempfile.mkdtemp()))
        self.assertTrue(out["started"])
        self.assertEqual(out["pid"], 555)
        self.assertEqual(proc.kill_calls, 0)
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "STARTING")
        self.assertEqual(final.get("pid"), 555)
        pc._close_log_handles(555)

    def test_child_first_adopts_running_record(self):
        path, tmp = _temp_registry(self)
        proc = _FakeProc(555)

        def _spawn_first(*args, **kwargs):
            # The child wins the race: self-registers RUNNING before the
            # parent's STARTING commit runs.
            pc._write_registry(_child_record(555, "C555"))
            return proc

        with mock.patch.object(pc.subprocess, "Popen",
                               side_effect=_spawn_first):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="C555"):
                with mock.patch.object(pc, "is_canonical_pid",
                                       return_value=True):
                    before = None
                    orig_commit = pc.update_registry

                    def _capture_before(transform):
                        nonlocal before
                        try:
                            before = path.read_bytes()
                        except OSError:
                            before = None
                        return orig_commit(transform)

                    with mock.patch.object(pc, "update_registry",
                                           side_effect=_capture_before):
                        out = pc.start_probe(
                            duration_seconds=60,
                            evidence_dir=str(tmp / "evidence"))
        self.assertTrue(out["started"])
        self.assertEqual(out["pid"], 555)
        self.assertEqual(proc.kill_calls, 0)
        final = pc.read_registry()
        # Same child's registration preserved: RUNNING + its evidence.
        self.assertEqual(final.get("state"), "RUNNING")
        self.assertEqual(final.get("pid"), 555)
        self.assertEqual(final.get("create_time"), "C555")
        self.assertEqual((final.get("evidence") or {}).get("log"),
                         "child-evidence.log")
        pc._close_log_handles(555)

    def test_foreign_winner_refused_and_orphan_cleaned(self):
        # Preflight passes on an empty registry; a genuinely foreign run
        # lands before the STARTING commit. The commit must refuse it
        # (not ours by PID+ctime), clean up exactly our own orphan spawn,
        # and preserve the foreign record.
        _, tmp = _temp_registry(self)
        proc = _FakeProc(555)
        foreign = _child_record(999, "FOREIGN-C")
        orig = pc.update_registry

        def _foreign_wins_first(transform):
            orig(lambda _: (dict(foreign), True))
            return orig(transform)

        with mock.patch.object(pc.subprocess, "Popen", return_value=proc):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="C555"):
                with mock.patch.object(pc, "is_canonical_pid",
                                       return_value=True):
                    with mock.patch.object(pc, "update_registry",
                                           side_effect=_foreign_wins_first):
                        out = pc.start_probe(
                            duration_seconds=60,
                            evidence_dir=str(tmp / "evidence"))
        self.assertFalse(out["started"])
        self.assertTrue(out["already_running"])
        self.assertEqual(proc.kill_calls, 1)
        final = pc.read_registry()
        self.assertEqual(final.get("pid"), 999)
        self.assertEqual(final.get("state"), "RUNNING")
        self.assertEqual(final.get("create_time"), "FOREIGN-C")

    def test_reused_pid_refused(self):
        # Same PID but a different creation time is NOT our child (PID
        # reuse): refuse and clean up our own spawn exactly once.
        _, tmp = _temp_registry(self)
        proc = _FakeProc(555)
        stale_same_pid = _child_record(555, "OLD-C")
        orig = pc.update_registry

        def _stale_wins_first(transform):
            orig(lambda _: (dict(stale_same_pid), True))
            return orig(transform)

        with mock.patch.object(pc.subprocess, "Popen", return_value=proc):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="NEW-C"):
                with mock.patch.object(pc, "is_canonical_pid",
                                       return_value=True):
                    with mock.patch.object(pc, "update_registry",
                                           side_effect=_stale_wins_first):
                        out = pc.start_probe(
                            duration_seconds=60,
                            evidence_dir=str(tmp / "evidence"))
        self.assertFalse(out["started"])
        self.assertEqual(proc.kill_calls, 1)
        final = pc.read_registry()
        self.assertEqual(final.get("pid"), 555)
        self.assertEqual(final.get("create_time"), "OLD-C")

    def test_write_failure_cleans_up(self):
        _, tmp = _temp_registry(self)
        proc = _FakeProc(555)
        with mock.patch.object(pc.subprocess, "Popen", return_value=proc):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="C555"):
                with mock.patch.object(pc, "update_registry",
                                       side_effect=OSError("disk")):
                    out = pc.start_probe(duration_seconds=60,
                                         evidence_dir=str(tmp / "evidence"))
        self.assertFalse(out["started"])
        self.assertEqual(proc.kill_calls, 1)
