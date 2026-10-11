"""P1-14B.8 V2-52/V2-54 H2+R2: parent start vs own-child registration race.

Fail-before regressions (simulated spawn/kill, temp registries; the child
uses the REAL try_register() on an empty registry, so it registers with
evidence=None -- no handcrafted records):

  R1  parent-first (empty registry): STARTING committed, started=True,
      kill never called.
  R2a child-first real (own child RUNNING evidence=None before the parent
      commit): adoption + locked log handoff -- started=True, kill never
      called, final RUNNING carries the parent-created log which exists,
      evidence_associated=True.
  R2b child-first with valid pre-existing evidence: adopted verbatim,
      evidence preserved byte-for-byte, evidence_associated=False
      (not our log), kill never called, zero writes.
  R2c interleaved takeover/STOPPING between adoption and handoff: handoff
      refused -- started=False (adopted-record-superseded), kill never
      called, foreign marker preserved, no log declared associated.
  R2d handoff write failure: started=True (verified live child, never
      destroyed), evidence unconfirmed (associated=False), kill never
      called, child record preserved.
  R3  foreign winner (live foreign RUNNING): started=False, orphan
      cleanup kills exactly once, foreign record preserved.
  R4  same PID with different creation time (reused PID): refused as
      foreign, kill called once.
  R5  registry write failure at commit: started=False, kill called once.

On b801ab0 R2a fails (evidence stays None: log-discovery gap), R2c/R2d
fail (no handoff path). This task does NOT extend to the V2 supervised
transactional launch. Run: python run_tests.py
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

    def test_child_first_real_registration_gets_log(self):
        # The child wins the race via the REAL try_register() on an empty
        # registry (evidence=None, as genuinely self-registered children
        # look). The parent must adopt AND associate its created log.
        _, tmp = _temp_registry(self)
        proc = _FakeProc(555)

        def _spawn_first(*args, **kwargs):
            with mock.patch.object(pc.os, "getpid", return_value=555):
                reg = pc.try_register(duration_seconds=60, launcher="agent")
            self.assertTrue(reg["registered"])
            self.assertIsNone(reg["record"]["evidence"])
            return proc

        with mock.patch.object(pc.subprocess, "Popen",
                               side_effect=_spawn_first):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="C555"):
                with mock.patch.object(pc, "is_canonical_pid",
                                       return_value=True):
                    out = pc.start_probe(
                        duration_seconds=60,
                        evidence_dir=str(tmp / "evidence"))
        self.assertTrue(out["started"])
        self.assertTrue(out.get("adopted_child_registration"))
        self.assertTrue(out.get("evidence_associated"))
        self.assertEqual(out["pid"], 555)
        self.assertEqual(proc.kill_calls, 0)
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "RUNNING")
        self.assertEqual(final.get("pid"), 555)
        self.assertEqual(final.get("create_time"), "C555")
        log_path = (final.get("evidence") or {}).get("log")
        self.assertEqual(log_path, (out.get("evidence") or {}).get("log"))
        self.assertTrue(log_path and Path(log_path).is_file())
        pc._close_log_handles(555)

    def test_child_first_existing_evidence_preserved(self):
        # Same child already carrying a valid log: adopt verbatim, never
        # overwrite it, never write at all (byte-preserving).
        path, tmp = _temp_registry(self)
        path.write_text(json.dumps(_child_record(555, "C555")),
                        encoding="utf-8")
        before = path.read_bytes()
        proc = _FakeProc(555)
        calls = {"n": 0}
        canon = {"n": 0}

        def _stale_then_live(record):
            # Preflight sees a stale record (passes through to spawn);
            # every later check sees the live child.
            canon["n"] += 1
            return canon["n"] > 1

        with mock.patch.object(pc.subprocess, "Popen", return_value=proc):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="C555"):
                with mock.patch.object(pc, "is_canonical_pid",
                                       side_effect=_stale_then_live):
                    orig = pc.update_registry

                    def _count(transform):
                        calls["n"] += 1
                        return orig(transform)

                    with mock.patch.object(pc, "update_registry",
                                           side_effect=_count):
                        out = pc.start_probe(
                            duration_seconds=60,
                            evidence_dir=str(tmp / "evidence"))
        self.assertTrue(out["started"])
        self.assertTrue(out.get("adopted_child_registration"))
        self.assertFalse(out.get("evidence_associated"))
        self.assertEqual(proc.kill_calls, 0)
        self.assertEqual(path.read_bytes(), before)
        final = pc.read_registry()
        self.assertEqual((final.get("evidence") or {}).get("log"),
                         "child-evidence.log")
        pc._close_log_handles(555)

    def test_handoff_refused_on_interleaved_stopping(self):
        # Takeover/STOPPING lands between adoption and the log handoff:
        # no association may be declared, the child must not be killed,
        # and the foreign marker must survive.
        _, tmp = _temp_registry(self)
        proc = _FakeProc(555)
        state = {"spawned": False}

        def _spawn_first(*args, **kwargs):
            with mock.patch.object(pc.os, "getpid", return_value=555):
                reg = pc.try_register(duration_seconds=60, launcher="agent")
            self.assertTrue(reg["registered"])
            state["spawned"] = True
            return proc

        orig = pc.update_registry
        calls = {"n": 0}

        def _takeover_before_handoff(transform):
            # The child's own try_register also flows through here: only
            # intercept the parent's commit (1st post-spawn call) boundary.
            if not state["spawned"]:
                return orig(transform)
            calls["n"] += 1
            if calls["n"] == 2:
                take = pc.read_registry()
                take["state"] = "STOPPING"
                take["stopping_by"] = "enforce:supervisor:999999"
                take["supervisor"] = {"pid": 999999, "state": "ACTIVE"}
                pc._write_registry(take)
            return orig(transform)

        with mock.patch.object(pc.subprocess, "Popen",
                               side_effect=_spawn_first):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="C555"):
                with mock.patch.object(pc, "is_canonical_pid",
                                       return_value=True):
                    with mock.patch.object(pc, "update_registry",
                                           side_effect=_takeover_before_handoff):
                        out = pc.start_probe(
                            duration_seconds=60,
                            evidence_dir=str(tmp / "evidence"))
        self.assertFalse(out["started"])
        self.assertFalse(out.get("evidence_associated", False))
        self.assertEqual(proc.kill_calls, 0)
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "STOPPING")
        self.assertEqual(final.get("stopping_by"),
                         "enforce:supervisor:999999")
        self.assertIsNone(final.get("evidence"))
        pc._close_log_handles(555)

    def test_handoff_write_failure_leaves_child_alive(self):
        # The log handoff itself fails: the verified live child must NOT be
        # destroyed, and no confirmed association may be declared.
        _, tmp = _temp_registry(self)
        proc = _FakeProc(555)
        state = {"spawned": False}

        def _spawn_first(*args, **kwargs):
            with mock.patch.object(pc.os, "getpid", return_value=555):
                reg = pc.try_register(duration_seconds=60, launcher="agent")
            self.assertTrue(reg["registered"])
            state["spawned"] = True
            return proc

        orig = pc.update_registry
        calls = {"n": 0}

        def _fail_handoff(transform):
            if not state["spawned"]:
                return orig(transform)
            calls["n"] += 1
            if calls["n"] >= 2:
                raise OSError("disk")
            return orig(transform)

        with mock.patch.object(pc.subprocess, "Popen",
                               side_effect=_spawn_first):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="C555"):
                with mock.patch.object(pc, "is_canonical_pid",
                                       return_value=True):
                    with mock.patch.object(pc, "update_registry",
                                           side_effect=_fail_handoff):
                        out = pc.start_probe(
                            duration_seconds=60,
                            evidence_dir=str(tmp / "evidence"))
        self.assertTrue(out["started"])
        self.assertTrue(out.get("adopted_child_registration"))
        self.assertFalse(out.get("evidence_associated"))
        self.assertEqual(proc.kill_calls, 0)
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "RUNNING")
        self.assertEqual(final.get("pid"), 555)
        self.assertIsNone(final.get("evidence"))
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
