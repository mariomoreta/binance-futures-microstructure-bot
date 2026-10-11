"""P1-14B.8 V2-52 H1: Windows native termination must propagate refusal.

Fail-before regressions (hermetic fake kernel32, no canonical processes):

  N1  matching creation time + API success -> True, same 64-bit handle
      used for GetProcessTimes and TerminateProcess, handle closed,
      TerminateProcess/CloseHandle signatures explicitly configured.
  N2  mismatched creation time -> False, TerminateProcess never called,
      handle closed.
  N3  GetProcessTimes failure -> False, TerminateProcess never called,
      handle closed.
  N4  TerminateProcess returning 0 -> False (never True), bounded Windows
      error recorded, handle closed.
  N5  TerminateProcess raising -> False, handle closed.
  N6  OpenProcess failure -> False, TerminateProcess never called.
  N7  missing expected ctime -> documented liveness-only fallback
      (queryable handle terminates; unqueryable refuses).

On 55efaa2 N1 fails (signatures unconfigured), N4 fails (True despite 0).
The demonstrated fault is accepting native refusal as success -- NOT a
false ABORTED marking (callers still verify disappearance). Run:
python run_tests.py
"""

from __future__ import annotations

import ctypes
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc

_WIN = os.name == "nt"
STAMP = "2026-10-11T00:00:00+00:00"


def _ticks(stamp):
    return int(datetime.fromisoformat(stamp).timestamp() * 10000000) + 116444736000000000


class _Native:
    """Fake native entry point recording signature config and calls."""

    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.callback(*args)


def _fill_times(stamp):
    def _times(handle, created, *unused):
        ticks = _ticks(stamp)
        created._obj.dwLowDateTime = ticks & 0xFFFFFFFF
        created._obj.dwHighDateTime = ticks >> 32
        return 1
    return _times


def _kernel(open_ret=0x100000123, times_cb=None, term_ret=1,
            term_cb=None, last_error=0):
    def _term(*args):
        if term_cb is not None:
            return term_cb(*args)
        return term_ret
    k = SimpleNamespace(
        OpenProcess=_Native(lambda *a: open_ret),
        GetProcessTimes=_Native(times_cb or _fill_times(STAMP)),
        TerminateProcess=_Native(_term),
        CloseHandle=_Native(lambda *a: 1),
        GetLastError=_Native(lambda *a: last_error),
    )
    return k


def _run(pid, stamp, kernel):
    with mock.patch.object(ctypes, "windll",
                           SimpleNamespace(kernel32=kernel)):
        return pc._terminate_verified_pid(pid, stamp)


@unittest.skipUnless(_WIN, "Windows native HANDLE boundary")
class NativeTerminateTest(unittest.TestCase):
    def test_matching_ctime_terminates_on_same_handle(self):
        k = _kernel()
        self.assertTrue(_run(424243, STAMP, k))
        # Same full-width handle verifies and terminates (no 32-bit cut).
        self.assertEqual(len(k.TerminateProcess.calls), 1)
        self.assertEqual(k.TerminateProcess.calls[0][0], 0x100000123)
        self.assertEqual(k.TerminateProcess.calls[0][1], 0)
        self.assertEqual(len(k.CloseHandle.calls), 1)
        self.assertEqual(k.CloseHandle.calls[0][0], 0x100000123)
        # Explicit pointer-width signatures (HANDLE-width, BOOL-checked).
        self.assertIsNotNone(k.TerminateProcess.argtypes)
        self.assertIsNotNone(k.TerminateProcess.restype)
        self.assertIsNotNone(k.CloseHandle.argtypes)
        self.assertIsNotNone(k.CloseHandle.restype)

    def test_mismatched_ctime_refuses_without_terminating(self):
        k = _kernel(times_cb=_fill_times("2020-01-01T00:00:00+00:00"))
        self.assertFalse(_run(424243, STAMP, k))
        self.assertEqual(k.TerminateProcess.calls, [])
        self.assertEqual(len(k.CloseHandle.calls), 1)

    def test_getprocesstimes_failure_refuses(self):
        k = _kernel(times_cb=lambda *a: 0)
        self.assertFalse(_run(424243, STAMP, k))
        self.assertEqual(k.TerminateProcess.calls, [])
        self.assertEqual(len(k.CloseHandle.calls), 1)

    def test_terminate_zero_returns_false_and_records_error(self):
        pc._LAST_NATIVE_ERROR.clear()
        k = _kernel(term_ret=0, last_error=5)
        self.assertFalse(_run(424243, STAMP, k))
        self.assertEqual(len(k.TerminateProcess.calls), 1)
        self.assertEqual(len(k.CloseHandle.calls), 1)
        self.assertEqual(pc._LAST_NATIVE_ERROR.get("code"), 5)

    def test_terminate_exception_closes_and_returns_false(self):
        def _boom(*args):
            raise RuntimeError("native boom")
        k = _kernel(term_cb=_boom)
        self.assertFalse(_run(424243, STAMP, k))
        self.assertEqual(len(k.CloseHandle.calls), 1)

    def test_open_failure_refuses(self):
        k = _kernel(open_ret=0)
        self.assertFalse(_run(424243, STAMP, k))
        self.assertEqual(k.TerminateProcess.calls, [])
        self.assertEqual(k.CloseHandle.calls, [])

    def test_missing_ctime_is_liveness_only_fallback(self):
        # Documented fallback: without expected ctime only handle
        # queryability is verified (PID-reuse NOT excluded -- residual).
        k = _kernel()
        self.assertTrue(_run(424243, None, k))
        self.assertEqual(len(k.TerminateProcess.calls), 1)
        k2 = _kernel(open_ret=0)
        self.assertFalse(_run(424243, None, k2))


class PosixTerminateTest(unittest.TestCase):
    def _posix(self):
        return mock.patch.object(pc.os, "name", "posix")

    def test_verified_kill(self):
        with self._posix():
            with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                             return_value=True):
                with mock.patch.object(pc.os, "kill") as kill:
                    self.assertTrue(pc._terminate_verified_pid(424242, "STAMP"))
        kill.assert_called_once()

    def test_unverified_refuses_without_kill(self):
        with self._posix():
            with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                             return_value=False):
                with mock.patch.object(pc.os, "kill") as kill:
                    self.assertFalse(pc._terminate_verified_pid(424242, "STAMP"))
        kill.assert_not_called()
