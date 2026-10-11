"""P1-10R-FIX-01 regression tests: console-free Windows PID checks.

All subprocess interaction is mocked — these tests never open a real
visible console. They prove CREATE_NO_WINDOW is passed on Windows while
PID identity semantics (image + creation-time + honest failure) hold.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from microstructure_probe import control
from microstructure_probe import dashboard
from microstructure_probe import host_process


def _completed_run(cmd, stdout="", stderr=""):
    m = mock.Mock()
    m.configure_mock(stdout=stdout, stderr=stderr, returncode=0)
    return m


class NoWindowFlagsTest(unittest.TestCase):
    def test_helper_returns_int_flag(self) -> None:
        flags = dashboard.no_window_flags()
        self.assertIsInstance(flags, int)
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            self.assertEqual(flags, int(subprocess.CREATE_NO_WINDOW))
            self.assertNotEqual(flags, 0)
        else:  # non-Windows: POSIX behavior unchanged
            self.assertEqual(flags, 0)

    def test_tasklist_run_suppresses_console(self) -> None:
        csv = '"python.exe","1234","Console","1","10,000 K"\r\n'
        with mock.patch.object(dashboard.subprocess, "run") as run:
            run.return_value = _completed_run("tasklist", stdout=csv)
            # wmic second call returns empty (creation unknown, still honest)
            run.side_effect = [
                _completed_run("tasklist", stdout=csv),
                _completed_run("wmic", stdout=""),
            ]
            image, creation = dashboard.process_info(1234)
        self.assertEqual(image, "python.exe")
        self.assertIsNone(creation)
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            self.assertIn("creationflags", call.kwargs)
            self.assertEqual(call.kwargs["creationflags"],
                             dashboard.no_window_flags())
        first_cmd = run.call_args_list[0].args[0]
        self.assertEqual(first_cmd[0], "tasklist")

    def test_wmic_run_suppresses_console(self) -> None:
        csv = '"python.exe","1234","Console","1","10,000 K"\r\n'
        wmic_out = "CreationDate=20261008004820.000000+000\r\n"
        with mock.patch.object(dashboard.subprocess, "run") as run:
            run.side_effect = [
                _completed_run("tasklist", stdout=csv),
                _completed_run("wmic", stdout=wmic_out),
            ]
            image, creation = dashboard.process_info(1234)
        self.assertEqual(image, "python.exe")
        self.assertEqual(creation, "20261008004820.000000+000")
        second_cmd = run.call_args_list[1].args[0]
        self.assertEqual(second_cmd[0], "wmic")
        self.assertEqual(run.call_args_list[1].kwargs["creationflags"],
                         dashboard.no_window_flags())

    def test_tasklist_failure_returns_honest_unknown(self) -> None:
        with mock.patch.object(dashboard.subprocess, "run",
                               side_effect=OSError("no tasklist")):
            self.assertEqual(dashboard.process_info(99999), (None, None))

    def test_timeouts_and_capture_preserved(self) -> None:
        with mock.patch.object(dashboard.subprocess, "run") as run:
            run.return_value = _completed_run("tasklist", stdout="INFO: No tasks")
            dashboard.process_info(4242)
        kwargs = run.call_args_list[0].kwargs
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["timeout"], 10)


class PidIdentityTest(unittest.TestCase):
    def test_correct_identity_accepted(self) -> None:
        with mock.patch.object(host_process, "process_info",
                               return_value=("python.exe", "CTIME-1")):
            self.assertTrue(dashboard.pid_is_ours(111, "CTIME-1"))

    def test_wrong_image_rejected(self) -> None:
        with mock.patch.object(host_process, "process_info",
                               return_value=("notepad.exe", "CTIME-1")):
            self.assertFalse(dashboard.pid_is_ours(111, "CTIME-1"))

    def test_mismatched_creation_rejected_pid_reuse(self) -> None:
        with mock.patch.object(host_process, "process_info",
                               return_value=("python.exe", "CTIME-2")):
            self.assertFalse(dashboard.pid_is_ours(111, "CTIME-1"))

    def test_missing_process_rejected(self) -> None:
        with mock.patch.object(host_process, "process_info",
                               return_value=(None, None)):
            self.assertFalse(dashboard.pid_is_ours(111, "CTIME-1"))


class StartProbeNoWindowTest(unittest.TestCase):
    def test_spawn_hides_console_and_registers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MICROPROBE_RUNTIME_FILE"] = str(
                Path(tmp) / "probe_runtime.json")
            try:
                fake_proc = mock.Mock()
                fake_proc.pid = 424242
                with mock.patch.object(control.subprocess, "Popen",
                                       return_value=fake_proc) as popen, \
                     mock.patch.object(host_process, "process_info",
                                       return_value=("python.exe", "CT-9")):
                    result = control.start_probe(75, launcher="test",
                                                 preset="standard")
                self.assertTrue(result.get("started"))
                self.assertIn("creationflags", popen.call_args.kwargs)
                self.assertEqual(popen.call_args.kwargs["creationflags"],
                                 dashboard.no_window_flags())
                status = control.status()
                self.assertEqual(status["duration_seconds"], 75)
            finally:
                os.environ.pop("MICROPROBE_RUNTIME_FILE", None)


class LifecycleStatusTest(unittest.TestCase):
    def _record(self, state, pid=777001, ctime="CT-X"):
        return {"schema": 1, "writer": "control/1", "state": state,
                "pid": pid, "create_time": ctime,
                "started_at": "2026-10-08T00:00:00+00:00", "mode": "observe",
                "duration_seconds": 75, "launcher": "test",
                "preset": "standard", "last_exit": None}

    def test_running_completed_stopped_accurate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MICROPROBE_RUNTIME_FILE"] = str(
                Path(tmp) / "probe_runtime.json")
            try:
                with mock.patch.object(host_process, "process_info",
                                       return_value=("python.exe", "CT-X")):
                    control._write_registry(self._record("RUNNING"))
                    self.assertTrue(control.status()["running"])
                    self.assertEqual(control.status()["state"], "RUNNING")
                    control._write_registry(self._record("COMPLETED"))
                    st = control.status()
                    self.assertFalse(st["running"])
                    self.assertEqual(st["state"], "COMPLETED")
                    control._write_registry(self._record("STOPPED"))
                    st = control.status()
                    self.assertFalse(st["running"])
                    self.assertEqual(st["state"], "STOPPED")
            finally:
                os.environ.pop("MICROPROBE_RUNTIME_FILE", None)

    def test_dead_pid_recovers_to_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MICROPROBE_RUNTIME_FILE"] = str(
                Path(tmp) / "probe_runtime.json")
            try:
                with mock.patch.object(host_process, "process_info",
                                       return_value=(None, None)):
                    control._write_registry(self._record("RUNNING"))
                    st = control.status()
                    self.assertFalse(st["running"])
                    self.assertEqual(st["state"], "FAILED")
            finally:
                os.environ.pop("MICROPROBE_RUNTIME_FILE", None)


if __name__ == "__main__":
    unittest.main()
