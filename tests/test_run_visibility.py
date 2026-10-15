"""V2 global run visibility: any project run (agent/dashboard) is observable
and stoppable through the canonical controller only.

Fixtures + isolated test processes only. No Binance traffic, no probe
launches, no real monitor runs. Real subprocesses used here are bare
`sleep` helpers, never the market probe.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from microstructure_probe import control as pc


def _temp_registry(tc):
    tmp = Path(tempfile.mkdtemp(prefix="runvis_"))
    tc.addCleanup(lambda: _rmtree(tmp))
    path = tmp / "probe_runtime.json"
    os.environ["MICROPROBE_RUNTIME_FILE"] = str(path)
    tc.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
    return path


def _rmtree(path: Path):
    try:
        for child in sorted(path.rglob("*"), reverse=True):
            try:
                if child.is_file() or child.is_symlink():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            except OSError:
                pass
        path.rmdir()
    except OSError:
        pass


def _record(pid=999999, state="RUNNING", created="STAMP-1",
            launcher="agent", duration=120, started="2026-10-15T10:25:20+00:00",
            exit_at=None, exit_reason=None, exit_code=None):
    rec = {"schema": 1, "writer": "control/1", "state": state,
           "pid": pid, "create_time": created, "started_at": started,
           "mode": "observe",
           "command": [sys.executable, "-m", "microstructure_probe"],
           "duration_seconds": duration, "expected_end_at": None,
           "launcher": launcher, "preset": "brief",
           "evidence": {"dir": "x", "log": "C:/tmp/probe-20261015T102519Z.log"},
           "last_exit": None}
    if exit_at is not None or exit_reason is not None:
        rec["last_exit"] = {"code": exit_code, "reason": exit_reason,
                            "at": exit_at}
    return rec


def _sleep_proc(seconds=30):
    proc = subprocess.Popen([sys.executable, "-c",
                             "import time; time.sleep(%s)" % seconds])
    return proc


class RunVisibilityTest(unittest.TestCase):
    def test_both_origins_expose_run_identity(self):
        for launcher in ("agent", "dashboard"):
            with self.subTest(launcher=launcher):
                _temp_registry(self)
                rec = _record(launcher=launcher)
                out = pc._status_view(rec, {"feed_health": "UNKNOWN",
                                            "latest_snapshot_age": None})
                self.assertEqual(out["launcher"], launcher)
                self.assertEqual(out["run_id"], "probe-20261015T102519Z")
                self.assertEqual(out["started_at"],
                                 "2026-10-15T10:25:20+00:00")
                self.assertEqual(out["duration_seconds"], 120)
                self.assertIn("process_state", out)
                self.assertIn("process_verified", out)

    def test_registered_vs_verified_distinct(self):
        _temp_registry(self)
        # Dead PID: recorded RUNNING but verified dead.
        rec = _record(pid=999998, created="STAMP-DEAD")
        with mock.patch.object(pc, "is_canonical_pid", return_value=False), \
             mock.patch.object(pc, "_default_process_state",
                               return_value="gone"):
            out = pc._status_view(rec, pc._feed_unknown())
        self.assertEqual(out["state"], "RUNNING")
        self.assertEqual(out["process_state"], "gone")
        self.assertFalse(out["process_verified"])

    def test_incomplete_identity_never_claims_owned(self):
        _temp_registry(self)
        # Live process with missing creation time: the display state is
        # unknown (no owned claim). Verification falls back to
        # handle-liveness only (documented residual in control.py), so the
        # test pins the display contract, not a silent ownership pass.
        proc = _sleep_proc(30)
        self.addCleanup(lambda: (proc.kill() if proc.poll() is None else None,
                                 proc.wait()))
        rec = _record(pid=proc.pid, created=None)
        rec.pop("create_time", None)
        out = pc._status_view(rec, pc._feed_unknown())
        self.assertEqual(out["process_state"], "unknown")
        self.assertNotEqual(out["process_state"], "owned")
        # Dead PID with missing identity is gone (absence proved) but
        # still never verified-owned.
        rec2 = _record(pid=999997, created=None)
        rec2.pop("create_time", None)
        out2 = pc._status_view(rec2, pc._feed_unknown())
        self.assertIn(out2["process_state"], ("gone", "unknown"))
        self.assertFalse(out2["process_verified"])

    def test_replaced_run_reports_replaced_and_refuses_stop(self):
        path = _temp_registry(self)
        path.write_text(json.dumps(_record(pid=424242, created="STAMP-OLD")),
                        encoding="utf-8")
        with mock.patch.object(pc, "is_canonical_pid", return_value=False), \
             mock.patch.object(pc, "_default_process_state",
                               return_value="replaced"):
            out = pc.status_readonly()
        self.assertEqual(out["process_state"], "replaced")
        self.assertFalse(out["process_verified"])
        with mock.patch.object(pc, "is_canonical_pid", return_value=False):
            res = pc.stop_probe(requester="dashboard-v2")
        self.assertFalse(res.get("stopped"))
        # Replaced identity is never terminated: stale recovery, not a kill.
        self.assertIn(res.get("error"), ("stale-probe-record-recovered",
                                         "stale-record-not-touched",
                                         "run-replaced"))

    def test_stop_verified_project_run_agent(self):
        _temp_registry(self)
        proc = _sleep_proc(30)
        self.addCleanup(lambda: (proc.kill() if proc.poll() is None else None,
                                 proc.wait()))
        try:
            ctime = pc.own_creation_time(proc.pid)
        except Exception:
            ctime = None
        self.assertIsNotNone(ctime)
        path = Path(os.environ["MICROPROBE_RUNTIME_FILE"])
        path.write_text(json.dumps(_record(pid=proc.pid, created=ctime,
                                           launcher="agent")),
                        encoding="utf-8")
        out = pc.status_readonly()
        self.assertEqual(out["launcher"], "agent")
        self.assertTrue(out["process_verified"])
        self.assertEqual(out["process_state"], "owned")
        res = pc.stop_probe(requester="dashboard-v2")
        self.assertTrue(res.get("stopped"))
        self.assertIsNotNone(proc.poll())

    def test_stop_verified_project_run_dashboard(self):
        _temp_registry(self)
        proc = _sleep_proc(30)
        self.addCleanup(lambda: (proc.kill() if proc.poll() is None else None,
                                 proc.wait()))
        ctime = pc.own_creation_time(proc.pid)
        path = Path(os.environ["MICROPROBE_RUNTIME_FILE"])
        path.write_text(json.dumps(_record(pid=proc.pid, created=ctime,
                                           launcher="dashboard")),
                        encoding="utf-8")
        res = pc.stop_probe(requester="dashboard-v2")
        self.assertTrue(res.get("stopped"))

    def test_stop_timeout_when_process_survives(self):
        _temp_registry(self)
        proc = _sleep_proc(30)
        self.addCleanup(lambda: (proc.kill() if proc.poll() is None else None,
                                 proc.wait()))
        ctime = pc.own_creation_time(proc.pid)
        path = Path(os.environ["MICROPROBE_RUNTIME_FILE"])
        path.write_text(json.dumps(_record(pid=proc.pid, created=ctime)),
                        encoding="utf-8")
        with mock.patch.object(pc, "_terminate_verified_pid",
                               return_value=True), \
             mock.patch.object(pc, "pid_is_ours", return_value=True):
            res = pc.stop_probe(requester="dashboard-v2")
        self.assertFalse(res.get("stopped"))
        self.assertEqual(res.get("error"), "stop-timeout")
        kept = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(kept["state"], "FAILED")

    def test_disconnection_registry_unavailable(self):
        _temp_registry(self)
        proc = _sleep_proc(30)
        self.addCleanup(lambda: (proc.kill() if proc.poll() is None else None,
                                 proc.wait()))
        ctime = pc.own_creation_time(proc.pid)
        path = Path(os.environ["MICROPROBE_RUNTIME_FILE"])
        path.write_text(json.dumps(_record(pid=proc.pid, created=ctime)),
                        encoding="utf-8")
        with mock.patch("microstructure_probe.control.update_registry",
                        side_effect=OSError("locked")):
            res = pc.stop_probe(requester="dashboard-v2")
        self.assertFalse(res.get("stopped"))
        self.assertEqual(res.get("error"), "registry-unavailable")

    def test_natural_close_freezes_duration_with_reason_and_time(self):
        _temp_registry(self)
        rec = _record(pid=492, state="COMPLETED", created="C1",
                      launcher="dashboard",
                      exit_at="2026-10-15T10:27:33+00:00",
                      exit_reason="duration-reached", exit_code=0)
        with mock.patch.object(pc, "_default_process_state",
                               return_value="gone"), \
             mock.patch.object(pc, "is_canonical_pid", return_value=False):
            out = pc._status_view(rec, pc._feed_unknown())
        self.assertEqual(out["state"], "COMPLETED")
        self.assertEqual(out["last_exit_reason"], "duration-reached")
        self.assertEqual(out["last_exit_at"], "2026-10-15T10:27:33+00:00")
        self.assertEqual(out["elapsed_seconds"], 133.0)
        self.assertIsNone(out["remaining_seconds"])
        self.assertFalse(out["process_verified"])
        # Frozen: a second read does not advance the clock.
        time.sleep(0.05)
        with mock.patch.object(pc, "_default_process_state",
                               return_value="gone"), \
             mock.patch.object(pc, "is_canonical_pid", return_value=False):
            out2 = pc._status_view(rec, pc._feed_unknown())
        self.assertEqual(out2["elapsed_seconds"], out["elapsed_seconds"])

    def test_abort_close_carries_rule_and_freezes(self):
        _temp_registry(self)
        rec = _record(pid=21252, state="ABORTED", created="C2",
                      launcher="dashboard",
                      exit_at="2026-10-15T00:08:34+00:00",
                      exit_reason="aborted-timestamp-reject-rate",
                      exit_code=0)
        rec["abort_rule"] = "timestamp-reject-rate"
        with mock.patch.object(pc, "_default_process_state",
                               return_value="gone"), \
             mock.patch.object(pc, "is_canonical_pid", return_value=False):
            out = pc._status_view(rec, pc._feed_unknown())
        self.assertEqual(out["state"], "ABORTED")
        self.assertEqual(out["last_exit_reason"],
                         "aborted-timestamp-reject-rate")
        self.assertEqual(out["last_exit_at"], "2026-10-15T00:08:34+00:00")
        self.assertFalse(out["running"])
        self.assertFalse(out["process_verified"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
