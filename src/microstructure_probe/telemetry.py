from __future__ import annotations

import math
import os
import time
from collections import deque


class RunningDistribution:
    """Estadisticas acumuladas con una ventana acotada para cuantiles.

    count/min/max/mean cubren toda la corrida. Los cuantiles usan las muestras
    mas recientes para mantener memoria acotada durante soaks prolongados.
    """

    def __init__(self, max_samples: int = 20_000) -> None:
        if max_samples <= 0:
            raise ValueError("max_samples debe ser mayor que cero")
        self._samples: deque[float] = deque(maxlen=max_samples)
        self.count = 0
        self.non_finite_count = 0
        self._sum = 0.0
        self._min: float | None = None
        self._max: float | None = None

    def add(self, value: float) -> None:
        number = float(value)
        if not math.isfinite(number):
            self.non_finite_count += 1
            return
        self.count += 1
        self._sum += number
        self._min = number if self._min is None else min(self._min, number)
        self._max = number if self._max is None else max(self._max, number)
        self._samples.append(number)

    def snapshot(self) -> dict[str, float | int | str | None]:
        ordered = sorted(self._samples)
        return {
            "count": self.count,
            "retainedCount": len(ordered),
            "retention": f"latest_{self._samples.maxlen}",
            "nonFiniteCount": self.non_finite_count,
            "min": self._rounded(self._min),
            "p50": self._quantile(ordered, 0.50),
            "p90": self._quantile(ordered, 0.90),
            "p95": self._quantile(ordered, 0.95),
            "p99": self._quantile(ordered, 0.99),
            "max": self._rounded(self._max),
            "mean": self._rounded(self._sum / self.count) if self.count else None,
        }

    @staticmethod
    def _quantile(ordered: list[float], probability: float) -> float | None:
        if not ordered:
            return None
        index = max(0, math.ceil(probability * len(ordered)) - 1)
        return RunningDistribution._rounded(ordered[index])

    @staticmethod
    def _rounded(value: float | None) -> float | None:
        return None if value is None else round(value, 6)


class NearMissCounter:
    LEVELS = (0.50, 0.75, 0.90, 1.00)

    def __init__(self) -> None:
        self.observations = 0
        self.maximum_ratio: float | None = None
        self._counts = {level: 0 for level in self.LEVELS}

    def observe(self, ratio: float) -> None:
        value = float(ratio)
        self.observations += 1
        self.maximum_ratio = value if self.maximum_ratio is None else max(self.maximum_ratio, value)
        for level in self.LEVELS:
            if value >= level:
                self._counts[level] += 1

    def snapshot(self) -> dict[str, float | int | dict[str, int] | None]:
        return {
            "observations": self.observations,
            "maxRatio": None if self.maximum_ratio is None else round(self.maximum_ratio, 6),
            "atOrAbove": {
                "50pct": self._counts[0.50],
                "75pct": self._counts[0.75],
                "90pct": self._counts[0.90],
                "100pct": self._counts[1.00],
            },
        }


def process_cpu_times() -> tuple | None:
    """Own-process CPU times (user_s, system_s) + monotonic s, or None.

    os.times() is available on Windows (user/system CPU seconds,
    children excluded by construction). Monotonic anchors the interval
    (immune to wall-clock steps). Any failure -> None (UNKNOWN).
    """
    try:
        t = os.times()
        return (float(t.user), float(t.system), time.monotonic())
    except Exception:
        return None


def cpu_percent_proc(prev: tuple | None, cur: tuple | None,
                     cpu_count: int | None) -> float | None:
    """Process CPU % between two samples. Pure, testable.

    100 * dProc / (dWall * ncpu); None on missing/invalid input or
    non-positive wall delta (never zero-filled, never negative).
    May exceed 100 with threads (documented, not clamped).
    """
    try:
        if prev is None or cur is None:
            return None
        ncpu = int(cpu_count) if cpu_count else 0
        if ncpu <= 0:
            return None
        dproc = (float(cur[0]) + float(cur[1])) - (float(prev[0]) + float(prev[1]))
        dwall = float(cur[2]) - float(prev[2])
        if not (dwall > 0) or not math.isfinite(dproc) or not math.isfinite(dwall):
            return None
        if dproc < 0:
            return None
        return round(100.0 * dproc / (dwall * ncpu), 3)
    except (TypeError, ValueError, IndexError):
        return None


def process_rss_bytes() -> int | None:
    """Own-process RSS bytes, or None (UNKNOWN).

    Windows-only capability: OpenProcess (real handle) +
    psapi.GetProcessMemoryInfo (WorkingSetSize), with explicit ctypes
    signatures and handle cleanup. Stdlib ctypes only, no new
    dependencies. Any failure (non-Windows included) -> None.
    Per-process only: NIC and system-wide counters are NOT available
    through this path and stay UNKNOWN by design.
    """
    handle = None
    try:
        if os.name != "nt":
            return None
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool,
                                         ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetCurrentProcessId.restype = ctypes.c_ulong
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

        class _Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong),
                        ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        pid = kernel32.GetCurrentProcessId()
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p,
                                               ctypes.c_void_p,
                                               ctypes.c_ulong]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_bool
        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters),
                                          counters.cb):
            return None
        rss = int(counters.WorkingSetSize)
        return rss if rss > 0 else None
    except Exception:
        return None
    finally:
        try:
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            pass

