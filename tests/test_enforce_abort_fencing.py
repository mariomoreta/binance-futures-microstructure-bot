"""P1-14B.8 follow-up: enforce_abort fencing regressions.

Covers the frontend-review HIGH findings with deterministic temporary
registries and mocked termination (no live probe, no market I/O):

  R1  foreign owner: termination never invoked (supervisor + sentinel).
  R2  COMPLETED + takeover between read and STOPPING: preserve both.
  R3  STOPPING write failure: termination never invoked.
  R4  PID/ctime replacement + foreign STOPPING marker during timeout:
      ABORTED/FAILED marks fenced (supervisor + sentinel).
  R5  successful abort persists the real owner (supervisor/sentinel).
  R6  foreign STOPPING marker acquisition refused (already-stopping).

On the pre-fix HEAD (8648366) R1-R4 fail: termination is invoked despite
a foreign lease / failed marker, stale snapshots overwrite COMPLETED, and
terminal marks ignore run replacement. Run: python run_tests.py
"""

from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="enffence_"))
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


def _owned_lease(kind, watched=424243):
    # Owner ctime tracks this process so enforcement-grade identity
    # (watched binding + ctime when determinable) verifies without mocks.
    try:
        ctime = pc.own_creation_time()
    except Exception:
        ctime = None
    base = {"pid": os.getpid(), "create_time": ctime,
            "started_at": "2026-10-10T10:00:00+00:00",
            "last_check_at": "2026-10-10T10:00:10+00:00",
            "state": "ACTIVE", "consecutive_failures": 0,
            "watched_pid": watched}
    if kind == "supervisor":
        base.update({"prev_supervisor_pid": None,
                     "streaks": {"persistence": 0, "clock": 0, "db": 0},
                     "abort": None})
    else:
        base.update({"prev_sentinel_pid": None, "action": None})
    return base


def _foreign_lease(kind, watched=424243):
    lease = _owned_lease(kind, watched=watched)
    lease["pid"] = 999999
    return lease


def _write(record):
    pc._write_registry(record)


def _decision():
    return {"rule": "timestamp-reject-rate", "reason": "t",
            "threshold": 0.05, "observed": 0.06}


class ForeignOwnerNoTerminateTest(unittest.TestCase):
    def test_supervisor_foreign_never_terminates(self):
        _temp_registry(self)
        rec = _run_record()
        rec["supervisor"] = _foreign_lease("supervisor")
        _write(rec)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "_terminate_verified_pid") as term:
                out = pc.enforce_abort(_decision(), owner_kind="supervisor")
        term.assert_not_called()
        self.assertFalse(out["aborted"])
        self.assertEqual(out["reason"], "replaced-owner")
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "RUNNING")
        self.assertNotIn("stopping_by", final)

    def test_sentinel_foreign_never_terminates(self):
        _temp_registry(self)
        rec = _run_record()
        rec["sentinel"] = _foreign_lease("sentinel")
        _write(rec)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "_terminate_verified_pid") as term:
                out = pc.enforce_abort(_decision(), owner_kind="sentinel")
        term.assert_not_called()
        self.assertFalse(out["aborted"])
        self.assertEqual(out["reason"], "replaced-owner")
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "RUNNING")
        self.assertNotIn("stopping_by", final)


class CompletedTakeoverPreservedTest(unittest.TestCase):
    def _takeover_case(self, owner_kind):
        _temp_registry(self)
        old = _run_record(pid=424243, state="RUNNING", ctime="STAMP")
        old[owner_kind] = _owned_lease(owner_kind, watched=424243)
        _write(old)
        old_copy = copy.deepcopy(old)
        # Takeover lands between the caller's read and the locked STOPPING
        # transition: new run, new identity, new owner, terminal state.
        new = _run_record(pid=999999, state="COMPLETED", ctime="NEWSTAMP")
        new[owner_kind] = _foreign_lease(owner_kind, watched=999999)
        _write(new)
        with mock.patch.object(pc, "read_registry", return_value=copy.deepcopy(old_copy)):
            with mock.patch.object(pc, "is_canonical_pid", return_value=True):
                with mock.patch.object(pc, "_terminate_verified_pid") as term:
                    out = pc.enforce_abort(_decision(), owner_kind=owner_kind)
        term.assert_not_called()
        self.assertFalse(out["aborted"])
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "COMPLETED")
        self.assertEqual(final.get("pid"), 999999)
        self.assertEqual(final.get("create_time"), "NEWSTAMP")

    def test_supervisor_completed_takeover_preserved(self):
        self._takeover_case("supervisor")

    def test_sentinel_completed_takeover_preserved(self):
        self._takeover_case("sentinel")


class StoppingWriteFailureNoTerminateTest(unittest.TestCase):
    def _failure_case(self, owner_kind):
        _temp_registry(self)
        rec = _run_record()
        rec[owner_kind] = _owned_lease(owner_kind)
        _write(rec)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "update_registry",
                                   side_effect=OSError("disk")):
                with mock.patch.object(pc, "_terminate_verified_pid") as term:
                    out = pc.enforce_abort(_decision(), owner_kind=owner_kind)
        term.assert_not_called()
        self.assertFalse(out["aborted"])
        self.assertEqual(out["reason"], "registry-unavailable")
        # Failed marker leaves no STOPPING behind.
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "RUNNING")
        self.assertNotIn("stopping_by", final)

    def test_supervisor_write_failure_never_terminates(self):
        self._failure_case("supervisor")

    def test_sentinel_write_failure_never_terminates(self):
        self._failure_case("sentinel")


class TerminalMarkFencingTest(unittest.TestCase):
    def _inject_takeover(self, foreign_marker="enforce:supervisor:999999"):
        rec = pc.read_registry()
        rec["pid"] = 999999
        rec["create_time"] = "NEWSTAMP"
        rec["state"] = "STOPPING"
        rec["stopping_by"] = foreign_marker
        # New owner holds the lease now; our PID no longer owns it.
        for kind in ("supervisor", "sentinel"):
            if isinstance(rec.get(kind), dict):
                rec[kind] = dict(rec[kind])
                rec[kind]["pid"] = 999999
        pc._write_registry(rec)

    def _abort_fenced_case(self, owner_kind):
        _temp_registry(self)
        rec = _run_record()
        rec[owner_kind] = _owned_lease(owner_kind)
        _write(rec)

        def _kill_and_takeover(pid, *args):
            self._inject_takeover(
                foreign_marker=("enforce:%s:999999" % owner_kind))
            return True

        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "_terminate_verified_pid",
                                   side_effect=_kill_and_takeover) as term:
                with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                                 return_value=False):
                    out = pc.enforce_abort(_decision(), owner_kind=owner_kind)
        self.assertTrue(term.called)
        self.assertFalse(out["aborted"])
        self.assertEqual(out["reason"], "superseded")
        final = pc.read_registry()
        # Replacement preserved: new identity + foreign marker untouched,
        # never re-marked ABORTED with the old owner.
        self.assertEqual(final.get("pid"), 999999)
        self.assertEqual(final.get("create_time"), "NEWSTAMP")
        self.assertNotEqual(final.get("state"), "ABORTED")

    def test_supervisor_abort_mark_fenced(self):
        self._abort_fenced_case("supervisor")

    def test_sentinel_abort_mark_fenced(self):
        self._abort_fenced_case("sentinel")

    def _timeout_fenced_case(self, owner_kind):
        _temp_registry(self)
        rec = _run_record()
        rec[owner_kind] = _owned_lease(owner_kind)
        _write(rec)

        def _kill_and_foreign_marker(pid, *args):
            cur = pc.read_registry()
            cur["stopping_by"] = "enforce:%s:999999" % owner_kind
            if isinstance(cur.get(owner_kind), dict):
                cur[owner_kind] = dict(cur[owner_kind])
                cur[owner_kind]["pid"] = 999999
            pc._write_registry(cur)
            return True

        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "_terminate_verified_pid",
                                   side_effect=_kill_and_foreign_marker) as term:
                with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                                 return_value=True):
                    out = pc.enforce_abort(_decision(), owner_kind=owner_kind)
        self.assertTrue(term.called)
        self.assertFalse(out["aborted"])
        self.assertEqual(out["reason"], "stop-timeout")
        final = pc.read_registry()
        # Foreign STOPPING marker + lost lease: FAILED must not be claimed.
        self.assertEqual(final.get("state"), "STOPPING")
        self.assertEqual(final.get("stopping_by"),
                         "enforce:%s:999999" % owner_kind)

    def test_supervisor_timeout_mark_fenced(self):
        self._timeout_fenced_case("supervisor")

    def test_sentinel_timeout_mark_fenced(self):
        self._timeout_fenced_case("sentinel")


class OwnerPersistedTest(unittest.TestCase):
    def _success_case(self, owner_kind):
        _temp_registry(self)
        rec = _run_record()
        rec[owner_kind] = _owned_lease(owner_kind)
        _write(rec)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "_terminate_verified_pid"):
                with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                                 return_value=False):
                    out = pc.enforce_abort(_decision(), owner_kind=owner_kind)
        self.assertTrue(out["aborted"])
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "ABORTED")
        self.assertEqual(final.get("aborted_by"), owner_kind)

    def test_supervisor_owner_persisted(self):
        self._success_case("supervisor")

    def test_sentinel_owner_persisted(self):
        self._success_case("sentinel")


class AlreadyStoppingTest(unittest.TestCase):
    def test_foreign_stopping_marker_refused(self):
        _temp_registry(self)
        rec = _run_record()
        rec["supervisor"] = _owned_lease("supervisor")
        rec["state"] = "STOPPING"
        rec["stopping_by"] = "enforce:supervisor:999999"
        _write(rec)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "_terminate_verified_pid") as term:
                out = pc.enforce_abort(_decision(), owner_kind="supervisor")
        term.assert_not_called()
        self.assertFalse(out["aborted"])
        self.assertEqual(out["reason"], "already-stopping")
        final = pc.read_registry()
        self.assertEqual(final.get("stopping_by"),
                         "enforce:supervisor:999999")
