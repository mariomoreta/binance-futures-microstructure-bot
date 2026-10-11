"""P1-14B.8 V2-51: operation boundary through termination + lease-vs-run.

Fail-before regressions for the 0786617 HIGH findings (deterministic temp
registries, mocked termination only):

  B1  post-claim takeover (owner pid swap after STOPPING acquisition)
      must NOT reach termination (supervisor + sentinel).
  B2  post-claim run replacement (pid/ctime swap after acquisition)
      must NOT reach termination (supervisor + sentinel).
  B3  owned lease bound to another run (watched_pid mismatch) must NOT
      reach termination (supervisor + sentinel).
  B4  owned associated lease in non-ACTIVE state must NOT terminate.

On 0786617 all of B1-B4 reach termination (terminate_called=true); B3 even
returns aborted=true. Run: python run_tests.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="opbound_"))
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


def _owned_lease(kind, watched=424243, state="ACTIVE"):
    # Owner ctime tracks this process so strengthened identity checks pass;
    # own_creation_time is patched to the same value in every test below.
    base = {"pid": os.getpid(), "create_time": "C-OWNER",
            "started_at": "2026-10-10T10:00:00+00:00",
            "last_check_at": "2026-10-10T10:00:10+00:00",
            "state": state, "consecutive_failures": 0,
            "watched_pid": watched}
    if kind == "supervisor":
        base.update({"prev_supervisor_pid": None,
                     "streaks": {"persistence": 0, "clock": 0, "db": 0},
                     "abort": None})
    else:
        base.update({"prev_sentinel_pid": None, "action": None})
    return base


def _write(record):
    pc._write_registry(record)


def _decision():
    return {"rule": "timestamp-reject-rate", "reason": "t",
            "threshold": 0.05, "observed": 0.06}


def _patched_owner():
    # Run identity is faked (is_canonical mocked True); owner identity uses
    # the patched own_creation_time so "C-OWNER" verifies without subprocess.
    return (mock.patch.object(pc, "is_canonical_pid", return_value=True),
            mock.patch.object(pc, "own_creation_time", return_value="C-OWNER"))


class PostClaimTakeoverTest(unittest.TestCase):
    def _after_claim_case(self, kind, swap):
        _temp_registry(self)
        rec = _run_record()
        rec[kind] = _owned_lease(kind)
        _write(rec)
        canon, owner_ctime = _patched_owner()
        original = pc.update_registry
        calls = [0]

        def swap_after_claim(transform):
            result = original(transform)
            calls[0] += 1
            if calls[0] == 1 and result[0]:
                def _swap(live):
                    swap(live)
                    return live, True
                original(_swap)
            return result

        with canon, owner_ctime:
            with mock.patch.object(pc, "update_registry",
                                   side_effect=swap_after_claim):
                with mock.patch.object(pc, "_terminate_verified_pid") as term:
                    with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                                     return_value=False):
                        out = pc.enforce_abort(_decision(), owner_kind=kind)
        term.assert_not_called()
        self.assertFalse(out["aborted"])

    def test_supervisor_owner_swap_after_claim(self):
        def _swap(live):
            live["supervisor"]["pid"] = 999999
        self._after_claim_case("supervisor", _swap)

    def test_sentinel_owner_swap_after_claim(self):
        def _swap(live):
            live["sentinel"]["pid"] = 999999
        self._after_claim_case("sentinel", _swap)

    def test_supervisor_run_swap_after_claim(self):
        def _swap(live):
            live["pid"] = 999999
            live["create_time"] = "NEWSTAMP"
        self._after_claim_case("supervisor", _swap)

    def test_sentinel_run_swap_after_claim(self):
        def _swap(live):
            live["pid"] = 999999
            live["create_time"] = "NEWSTAMP"
        self._after_claim_case("sentinel", _swap)


class WrongRunLeaseTest(unittest.TestCase):
    def _wrong_run_case(self, kind):
        _temp_registry(self)
        rec = _run_record(pid=424243)
        rec[kind] = _owned_lease(kind, watched=999999)
        _write(rec)
        canon, owner_ctime = _patched_owner()
        with canon, owner_ctime:
            with mock.patch.object(pc, "_terminate_verified_pid") as term:
                out = pc.enforce_abort(_decision(), owner_kind=kind)
        term.assert_not_called()
        self.assertFalse(out["aborted"])
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "RUNNING")
        self.assertNotIn("stopping_by", final)

    def test_supervisor_wrong_run_lease(self):
        self._wrong_run_case("supervisor")

    def test_sentinel_wrong_run_lease(self):
        self._wrong_run_case("sentinel")

    def test_supervisor_inactive_lease_refused(self):
        _temp_registry(self)
        rec = _run_record()
        rec["supervisor"] = _owned_lease("supervisor", state="FAILED")
        _write(rec)
        canon, owner_ctime = _patched_owner()
        with canon, owner_ctime:
            with mock.patch.object(pc, "_terminate_verified_pid") as term:
                out = pc.enforce_abort(_decision(), owner_kind="supervisor")
        term.assert_not_called()
        self.assertFalse(out["aborted"])

    def test_sentinel_inactive_lease_refused(self):
        _temp_registry(self)
        rec = _run_record()
        rec["sentinel"] = _owned_lease("sentinel", state="STOPPED")
        _write(rec)
        canon, owner_ctime = _patched_owner()
        with canon, owner_ctime:
            with mock.patch.object(pc, "_terminate_verified_pid") as term:
                out = pc.enforce_abort(_decision(), owner_kind="sentinel")
        term.assert_not_called()
        self.assertFalse(out["aborted"])
