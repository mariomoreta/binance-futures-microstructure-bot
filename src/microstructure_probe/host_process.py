"""Host process identity and platform utilities (no HTTP, no dashboard).

Canonical home of the helpers shared by the controller (`control.py`) and
the legacy dashboard (`dashboard.py`, which re-exports them unchanged for
compatibility): repository anchoring, Windows console suppression, OS
process identity (image + creation time) and PID-ownership checks.

Stdlib only. This module imports nothing from `dashboard` or `control`,
so `control` can use it without pulling the HTTP server module. Bodies are
moved verbatim from `dashboard.py` (behavior identical by construction).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def no_window_flags() -> int:
    """Windows console-suppression flags for child diagnostics (P1-10R-FIX-01).

    Returns ``subprocess.CREATE_NO_WINDOW`` on Windows so tasklist/wmic and
    spawned probes never flash a visible console; 0 elsewhere (POSIX
    ignores process windows — behavior there is unchanged).
    """
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)


def process_info(pid: int) -> Tuple[Optional[str], Optional[str]]:
    """(image_name, creation_time) for pid, or (None, None) if not present."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
            creationflags=no_window_flags(),
        ).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return None, None
    image = None
    for line in out:
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].strip() == str(pid):
            image = parts[0].strip('"')
            break
    if image is None:
        return None, None
    creation = None
    try:
        wmic = subprocess.run(
            ["wmic", "process", "where", f"ProcessId={pid}",
             "get", "CreationDate", "/VALUE"],
            capture_output=True, text=True, timeout=10,
            creationflags=no_window_flags(),
        ).stdout
        for line in wmic.splitlines():
            if line.strip().startswith("CreationDate="):
                creation = line.strip().split("=", 1)[1]
                break
    except (OSError, subprocess.SubprocessError):
        creation = None
    if creation is None:
        # P1-14B.7: wmic is absent on recent Windows builds; fall back to
        # GetProcessTimes so PID+creation-time identity keeps working.
        creation = _creation_time_ctypes(pid)
    return image, creation


def _creation_time_ctypes(pid: int) -> Optional[str]:
    """Process creation time via GetProcessTimes (wmic fallback).

    Returns an ISO UTC string, or None on any failure (non-Windows
    included). Equality-compared only, so the format just needs to be
    self-consistent per host.
    """
    handle = None
    try:
        import ctypes
        if os.name != "nt":
            return None
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool,
                                         ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.c_void_p] * 0 + [ctypes.POINTER(ctypes.c_ulonglong)] * 0
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return None

        class _FileTime(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_ulong),
                        ("dwHighDateTime", ctypes.c_ulong)]

        kernel32.GetProcessTimes.argtypes = [ctypes.c_void_p,
                                             ctypes.POINTER(_FileTime),
                                             ctypes.POINTER(_FileTime),
                                             ctypes.POINTER(_FileTime),
                                             ctypes.POINTER(_FileTime)]
        kernel32.GetProcessTimes.restype = ctypes.c_bool
        ft_create, ft_exit, ft_kernel, ft_user = (_FileTime() for _ in range(4))
        ok = kernel32.GetProcessTimes(handle, ctypes.byref(ft_create),
                                      ctypes.byref(ft_exit),
                                      ctypes.byref(ft_kernel),
                                      ctypes.byref(ft_user))
        if not ok:
            return None
        ticks = (int(ft_create.dwHighDateTime) << 32) + int(ft_create.dwLowDateTime)
        epoch_us = ticks // 10 - 11644473600000000
        if epoch_us <= 0:
            return None
        from datetime import datetime, timezone
        return datetime.fromtimestamp(epoch_us / 1_000_000,
                                      tz=timezone.utc).isoformat()
    except Exception:
        return None
    finally:
        try:
            if handle:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            pass


def pid_is_ours(pid: int, expected_creation: Optional[str]) -> bool:
    """True only if pid exists, looks like Python, and matches the recorded
    creation time (when recorded). Stale/reused PIDs return False."""
    image, creation = process_info(pid)
    if image is None or "python" not in image.lower():
        return False
    if expected_creation and creation and creation != expected_creation:
        return False
    return True
