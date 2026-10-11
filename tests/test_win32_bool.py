"""P1-14B.8 V2-54 R1: exact Win32 BOOL representation.

Fail-before regressions (no canonical processes touched):

  B1  the BOOL type used for native signatures is exactly 32 bits
      (ctypes.wintypes.BOOL or an explicit compatible type), unlike
      ctypes.c_bool (1 byte).
  B2  TerminateProcess/CloseHandle/GetProcessTimes/OpenProcess-inherit
      signatures carry the exact expected types (asserted by identity
      and sizeof, not merely "configured").
  B3  ABI marshalling through a real WINFUNCTYPE callback for native
      returns 0, 1 and 256: 0 is falsy, 1 and 256 are truthy under the
      32-bit BOOL, while c_bool misreads 256 as falsy (the declared
      hazard). Python-level mocks alone cannot prove this conversion.
  B4  end-to-end helper behavior with a 256-returning ABI entry:
      True (success) once signatures are exact.

Scope: declaration/marshalling correctness only. This does NOT prove a
real Windows kill failed or that a live process was falsely marked
ABORTED. Run: python run_tests.py
"""

from __future__ import annotations

import ctypes
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc

_WIN = os.name == "nt"


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


class BoolWidthTest(unittest.TestCase):
    def test_bool_type_is_32_bits(self):
        self.assertEqual(ctypes.sizeof(ctypes.c_bool), 1)
        self.assertEqual(ctypes.sizeof(pc._WIN_BOOL), 4)

    def test_signatures_carry_exact_types(self):
        k = SimpleNamespace(
            OpenProcess=_Native(lambda *a: 0),
            GetProcessTimes=_Native(lambda *a: 0),
            TerminateProcess=_Native(lambda *a: 0),
            CloseHandle=_Native(lambda *a: 0),
            GetLastError=_Native(lambda *a: 0),
        )
        pc._configure_kernel_signatures(k)
        self.assertIs(k.TerminateProcess.argtypes[0], pc._WIN_HANDLE)
        self.assertEqual(ctypes.sizeof(k.TerminateProcess.argtypes[0]), 8
                         if ctypes.sizeof(ctypes.c_void_p) == 8 else 4)
        self.assertIs(k.TerminateProcess.argtypes[1], ctypes.c_uint)
        self.assertIs(k.TerminateProcess.restype, pc._WIN_BOOL)
        self.assertEqual(ctypes.sizeof(k.TerminateProcess.restype), 4)
        self.assertIs(k.CloseHandle.argtypes[0], pc._WIN_HANDLE)
        self.assertIs(k.CloseHandle.restype, pc._WIN_BOOL)
        self.assertEqual(ctypes.sizeof(k.CloseHandle.restype), 4)
        self.assertIs(k.GetProcessTimes.restype, pc._WIN_BOOL)
        self.assertEqual(ctypes.sizeof(k.GetProcessTimes.restype), 4)
        # OpenProcess inherit handle is a Win32 BOOL, not a byte.
        self.assertIs(k.OpenProcess.argtypes[1], pc._WIN_BOOL)
        self.assertEqual(ctypes.sizeof(k.OpenProcess.argtypes[1]), 4)


@unittest.skipUnless(_WIN, "real Win32 ABI marshalling")
class AbiMarshallingTest(unittest.TestCase):
    def _entry(self, restype, value):
        cb = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p,
                                ctypes.c_uint)(lambda *a: value)
        address = ctypes.cast(cb, ctypes.c_void_p).value
        return (ctypes.WINFUNCTYPE(restype, ctypes.c_void_p,
                                   ctypes.c_uint)(address), cb)

    def test_zero_is_falsy(self):
        entry, _keep = self._entry(pc._WIN_BOOL, 0)
        self.assertFalse(entry(0x100000123, 0))

    def test_one_is_truthy(self):
        entry, _keep = self._entry(pc._WIN_BOOL, 1)
        self.assertTrue(entry(0x100000123, 0))

    def test_256_is_truthy_under_32bit_bool(self):
        # Any nonzero native return is success; 256 survives 32-bit BOOL.
        entry, _keep = self._entry(pc._WIN_BOOL, 256)
        observed = entry(0x100000123, 0)
        self.assertTrue(observed)
        self.assertEqual(int(observed), 256)

    def test_256_misreads_under_c_bool(self):
        # The declared hazard, faithfully: a 32-bit native 256 return whose
        # declaration is then narrowed to one byte reads back as 0x00.
        # (A Python-level lambda never truncates on the way in -- only the
        # ABI declaration governs the way back.)
        raw = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                 ctypes.c_uint)(lambda *a: 256)
        address = ctypes.cast(raw, ctypes.c_void_p).value
        entry = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                   ctypes.c_uint)(address)
        entry.restype = ctypes.c_bool  # what the buggy declaration did
        self.assertFalse(entry(0x100000123, 0))

    def test_helper_accepts_256_native_success(self):
        from datetime import datetime
        stamp = "2026-10-11T00:00:00+00:00"
        ticks = int(datetime.fromisoformat(stamp).timestamp() * 10000000) \
            + 116444736000000000

        def _times(handle, created, *unused):
            created._obj.dwLowDateTime = ticks & 0xFFFFFFFF
            created._obj.dwHighDateTime = ticks >> 32
            return 1

        raw = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                 ctypes.c_uint)(lambda *a: 256)
        address = ctypes.cast(raw, ctypes.c_void_p).value
        entry = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                   ctypes.c_uint)(address)
        k = SimpleNamespace(OpenProcess=_Native(lambda *a: 0x100000123),
                            GetProcessTimes=_Native(_times),
                            TerminateProcess=entry,
                            CloseHandle=_Native(lambda *a: 1),
                            GetLastError=_Native(lambda *a: 0))
        with mock.patch.object(ctypes, "windll",
                               SimpleNamespace(kernel32=k)):
            self.assertTrue(pc._terminate_verified_pid(424243, stamp))
