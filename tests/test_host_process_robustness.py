"""Robustness of host process identity (Windows tasklist/wmic handling).

Fail-before proofs for the pre-pilot review (2026-10-14): on real Windows
with tasklist emitting locale bytes under PYTHONUTF8=1, reader threads die
with UnicodeDecodeError and CompletedProcess.stdout is None, so
process_info() crashed with AttributeError instead of reporting unknown;
and pid_is_ours() returned True when a creation_time was expected but the
real one was unknown (verified identity it never had).

All subprocess contact here is mocked except the two live-PID cases,
which spawn and reap a real sleeper (isolated, foreign-safe).
"""

import subprocess
import sys
import unittest
from unittest import mock

from microstructure_probe import host_process as hp


def _cp(stdout, returncode=0):
    return subprocess.CompletedProcess(
        args=["tasklist"], returncode=returncode, stdout=stdout, stderr="")


PY_LINE = '"python.exe","1234","Console","1","10,000 K"'


class TasklistRobustnessTest(unittest.TestCase):
    def test_stdout_none_reports_unknown_without_raising(self) -> None:
        with mock.patch("subprocess.run", return_value=_cp(None)):
            self.assertEqual(hp.process_info(1234), (None, None))

    def test_decode_error_reports_unknown_without_raising(self) -> None:
        with mock.patch("subprocess.run",
                        side_effect=UnicodeDecodeError(
                            "utf-8", b"\xa0", 0, 1, "bad byte")):
            self.assertEqual(hp.process_info(1234), (None, None))

    def test_missing_tasklist_reports_unknown(self) -> None:
        with mock.patch("subprocess.run",
                        side_effect=FileNotFoundError("tasklist")):
            self.assertEqual(hp.process_info(1234), (None, None))

    def test_nonzero_exit_with_empty_output_reports_unknown(self) -> None:
        with mock.patch("subprocess.run", return_value=_cp("", returncode=1)):
            self.assertEqual(hp.process_info(1234), (None, None))

    def test_unmatched_pid_reports_unknown(self) -> None:
        with mock.patch("subprocess.run",
                        return_value=_cp('"other.exe","9999","x","1","1 K"')):
            self.assertEqual(hp.process_info(1234), (None, None))

    def test_decode_failures_are_neutralized_at_spawn(self) -> None:
        with mock.patch("subprocess.run", return_value=_cp(None)) as run:
            hp.process_info(1234)
            for call in run.call_args_list:
                self.assertEqual(call.kwargs.get("errors"), "replace")


class WmicFallbackTest(unittest.TestCase):
    def _tasklist_ok(self, run):
        run.side_effect = [_cp(PY_LINE), _cp(None)]

    def test_wmic_stdout_none_uses_ctypes_fallback(self) -> None:
        with mock.patch("subprocess.run") as run, \
                mock.patch.object(hp, "_creation_time_ctypes",
                                  return_value="STAMP") as ctime:
            self._tasklist_ok(run)
            self.assertEqual(hp.process_info(1234), ("python.exe", "STAMP"))
            ctime.assert_called_once_with(1234)

    def test_wmic_missing_uses_ctypes_fallback(self) -> None:
        with mock.patch("subprocess.run") as run, \
                mock.patch.object(hp, "_creation_time_ctypes",
                                  return_value="STAMP"):
            run.side_effect = [_cp(PY_LINE),
                               FileNotFoundError("wmic")]
            self.assertEqual(hp.process_info(1234), ("python.exe", "STAMP"))

    def test_wmic_without_creation_date_uses_ctypes_fallback(self) -> None:
        with mock.patch("subprocess.run") as run, \
                mock.patch.object(hp, "_creation_time_ctypes",
                                  return_value="STAMP"):
            run.side_effect = [_cp(PY_LINE), _cp("NoInstance(s) Available.")]
            self.assertEqual(hp.process_info(1234), ("python.exe", "STAMP"))


class OwnershipUnknownTest(unittest.TestCase):
    def _unknown_creation(self, run):
        run.side_effect = [_cp(PY_LINE), _cp(None)]
        patcher = mock.patch.object(hp, "_creation_time_ctypes",
                                    return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_expected_stamp_with_unknown_real_creation_is_not_ours(self) -> None:
        # Core safety fix: an expected creation_time with an UNKNOWN real
        # one must never count as verified identity (was: True).
        with mock.patch("subprocess.run") as run:
            self._unknown_creation(run)
            self.assertFalse(hp.pid_is_ours(1234, "STAMP"))

    def test_matching_creation_is_ours(self) -> None:
        with mock.patch("subprocess.run") as run:
            run.side_effect = [_cp(PY_LINE),
                               _cp("CreationDate=20250101000000.000000+000")]
            self.assertTrue(
                hp.pid_is_ours(1234, "20250101000000.000000+000"))

    def test_mismatched_creation_is_not_ours(self) -> None:
        with mock.patch("subprocess.run") as run:
            run.side_effect = [_cp(PY_LINE),
                               _cp("CreationDate=20250101000000.000000+000")]
            self.assertFalse(hp.pid_is_ours(1234, "OTHER"))

    def test_no_expected_stamp_with_python_image_is_ours(self) -> None:
        with mock.patch("subprocess.run") as run:
            run.side_effect = [_cp(PY_LINE), _cp(None)]
            with mock.patch.object(hp, "_creation_time_ctypes",
                                    return_value=None):
                self.assertTrue(hp.pid_is_ours(1234, None))

    def test_non_python_image_is_not_ours(self) -> None:
        with mock.patch("subprocess.run",
                        return_value=_cp('"notepad.exe","1234","x","1","1 K"')):
            self.assertFalse(hp.pid_is_ours(1234, None))


class LiveIdentityTest(unittest.TestCase):
    def test_live_python_pid_then_dead_pid(self) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertTrue(hp.pid_is_ours(proc.pid, None))
        finally:
            proc.terminate()
            proc.wait(timeout=10)
        self.assertFalse(hp.pid_is_ours(proc.pid, None))


if __name__ == "__main__":
    unittest.main()
