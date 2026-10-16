"""P1-11B.1 canonical market-probe lifecycle manager.

Single source of truth: ``logs/probe_runtime.json`` (git-ignored). Three
launch paths — AGENT (``control start`` CLI), TERMINAL (direct
``python -m microstructure_probe``), DASHBOARD (control API) — converge
here: the probe self-registers on start, so the dashboard discovers an
externally launched probe without having launched it.

Identity model (same as the dashboard's own PID safety): PID + python
image check + recorded creation time. Never trust PID alone; never touch
unrelated processes. STOP terminates ONLY the verified canonical probe
PID (SIGTERM on POSIX, TerminateProcess on Windows after revalidation).

Observe-only: every started probe is forced BOT_MODE=observe via the child
environment (the probe itself aborts on any other mode). No trading,
account, key, order, leverage or position functionality exists here.

Process states: STOPPED / STARTING / RUNNING / STOPPING / COMPLETED /
FAILED. Process state never implies feed health (HEALTHY / DEGRADED /
STALE / UNKNOWN stays a separate feed concern for the dashboard).
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import json
import math
import tempfile
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Shared host-process helpers (repo_root, process_info, pid_is_ours,
# no_window_flags) live in host_process (stdlib only, no HTTP) so this
# controller never imports the dashboard server module. Test patch targets
# for controller behavior are microstructure_probe.control.<name>.
from .host_process import (
    no_window_flags,
    pid_is_ours,
    process_info,
    repo_root,
)

REGISTRY_NAME = "probe_runtime.json"
REGISTRY_SCHEMA = 1

MIN_DURATION_SECONDS = 60
MAX_DURATION_SECONDS = 86400
SIX_HOURS = 21600
OBSERVATION_10M_SECONDS = 600

# Presets recorded verbatim in the registry. Any other preset string keeps
# the historical behavior (recorded as "standard"; the child carries its
# own MICROPROBE_PRESET env value on self-registration). Existing presets
# are untouched: adding a name here only preserves it, never remaps it.
_RECORDED_PRESETS = ("validation-6h", "observation-10m")


def _recorded_preset(preset: Any) -> str:
    """Registry preset label: verbatim for known presets, else standard."""
    return preset if preset in _RECORDED_PRESETS else "standard"

STATES = ("STOPPED", "STARTING", "RUNNING", "STOPPING",
          "COMPLETED", "FAILED")

_LOG_HANDLES: Dict[int, Any] = {}

# Bounded native-API diagnostic (V2-52 H1): last Windows termination refusal
# (GetLastError code + UTC timestamp). Single entry, overwritten on each
# refusal; never PII, never a process list. Empty when no refusal recorded.
_LAST_NATIVE_ERROR: Dict[str, Any] = {}

# Exact Win32 declarations (V2-54 R1): Windows BOOL is a 32-bit int, not a
# one-byte C bool -- ctypes.c_bool (1 byte) misreads any nonzero native
# return whose low byte is zero (e.g. 256 -> 0x00). HANDLE is
# pointer-width (c_void_p: 8 bytes on 64-bit; a >32-bit handle such as
# 0x100000123 must survive argument passing intact).
try:
    from ctypes import wintypes as _wintypes
    _WIN_BOOL = _wintypes.BOOL
    _WIN_DWORD = _wintypes.DWORD
    _WIN_HANDLE = _wintypes.HANDLE
except Exception:  # non-Windows import fallback (nt branch never runs)
    _WIN_BOOL = ctypes.c_int32
    _WIN_DWORD = ctypes.c_uint32
    _WIN_HANDLE = ctypes.c_void_p


class _FILETIME(ctypes.Structure):
    """Windows FILETIME for GetProcessTimes (bound once, not per call)."""

    _fields_ = [("dwLowDateTime", ctypes.c_ulong),
                ("dwHighDateTime", ctypes.c_ulong)]


def _configure_kernel_signatures(kernel32: Any) -> None:
    """Bind exact native prototypes (V2-54 R1, no silent setup).

    Assigns directly so a binding failure raises instead of silently
    keeping a wrong-width default. Callers pass the real windll kernel32
    or a signature-recording fake (tests assert exact type identity).
    """
    kernel32.OpenProcess.argtypes = [_WIN_DWORD, _WIN_BOOL, _WIN_DWORD]
    kernel32.OpenProcess.restype = _WIN_HANDLE
    kernel32.TerminateProcess.argtypes = [_WIN_HANDLE, ctypes.c_uint]
    kernel32.TerminateProcess.restype = _WIN_BOOL
    kernel32.CloseHandle.argtypes = [_WIN_HANDLE]
    kernel32.CloseHandle.restype = _WIN_BOOL
    kernel32.GetProcessTimes.argtypes = [_WIN_HANDLE,
                                         ctypes.POINTER(_FILETIME),
                                         ctypes.POINTER(_FILETIME),
                                         ctypes.POINTER(_FILETIME),
                                         ctypes.POINTER(_FILETIME)]
    kernel32.GetProcessTimes.restype = _WIN_BOOL
    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = _WIN_DWORD


def registry_path() -> Path:
    """Registry file, overridable for hermetic tests."""
    override = os.environ.get("MICROPROBE_RUNTIME_FILE")
    if override:
        return Path(override)
    return repo_root() / "logs" / REGISTRY_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_registry() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_registry(record: Dict[str, Any]) -> None:
    """Write the whole registry atomically (tmp + rename: no torn reads
    for concurrent readers). Does NOT prevent lost updates between
    concurrent writers -- use update_registry for read-modify-write."""
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _clean_stale_tmps(path)
    tmp = path.with_name("%s.tmp-%d" % (path.name, os.getpid()))
    tmp.write_text(json.dumps(record, indent=1), encoding="utf-8")
    os.replace(tmp, path)


@contextlib.contextmanager
def _locked_registry():
    """Exclusive advisory lock via a sidecar lockfile (fail-closed).

    The lock lives on `<registry>.lock`, NEVER on the registry file
    itself: on Windows an open handle without share-delete blocks the
    atomic rename used for writes, and mandatory byte-locks deny even
    our own second handle (proven live: EACCES on replace). The sidecar
    sidesteps both: writers serialize on it while the registry file
    itself is only ever replaced atomically (readers never see torn
    content). OS releases the lock if the holder dies, so no dead holder
    can wedge writers; the lockfile carries no state, so nothing goes
    stale. Lock errors raise OSError (callers treat as
    registry-unavailable; heartbeats skip, claims refuse).
    """
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    try:
        fh = open(str(lock_path), "a+b")
    except OSError as exc:
        raise OSError("registry lock unavailable: %s" % exc)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    except Exception as exc:
        try:
            fh.close()
        except Exception:
            pass
        raise OSError("registry lock unavailable: %s" % exc)
    try:
        yield lock_path
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            fh.close()
        except Exception:
            pass


def _clean_stale_tmps(path: Path) -> None:
    """Best-effort removal of our own orphaned tmp files (failed replaces)."""
    try:
        for stale in path.parent.glob(path.name + ".tmp-*"):
            try:
                if stale.is_file():
                    stale.unlink()
            except OSError:
                pass
    except OSError:
        pass


def update_registry(transform):
    """Locked read-modify-write: transform(record|None) -> (new|None, value).

    Returns (wrote: bool, value). Returning None as the record skips the
    write (refusals/no-ops without touching the file). The transform runs
    under the exclusive lock, so concurrent writers serialize instead of
    clobbering each other; the final write uses atomic rename so readers
    outside the lock never see torn content.
    NOTE (Windows): the lock lives on a sidecar file, so plain path reads
    and the temp-file strategy are safe here (proven live: mandatory locks
    deny even our own second handle on the same file, and open handles
    without share-delete block atomic rename).
    """
    path = registry_path()
    with _locked_registry():
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raw = ""
        except OSError:
            raise
        except Exception:
            raw = ""
        try:
            record = json.loads(raw) if raw.strip() else None
        except ValueError:
            record = None
        new_record, value = transform(record)
        if new_record is None:
            return (False, value)
        _clean_stale_tmps(path)
        tmp = path.with_name("%s.tmp-%d" % (path.name, os.getpid()))
        tmp.write_bytes(json.dumps(new_record, indent=1).encode("utf-8"))
        os.replace(tmp, path)
        return (True, value)


def _owns_lease(record: Any, kind: str) -> bool:
    """True iff this process holds the lease block for kind.

    PID equality only: a live holder's PID cannot be reused out from under
    it. Creation-time is enforced at claim/enforce boundaries (which verify
    liveness too); heartbeats only need to prove non-replacement.
    """
    try:
        lease = (record or {}).get(kind)
        if not isinstance(lease, dict):
            return False
        return int(lease.get("pid")) == os.getpid()
    except Exception:
        return False


def _owner_lease_valid(record: Any, kind: str, target_pid: int) -> bool:
    """Enforcement-grade owner validation (V2-51): PID + run binding.

    Stronger than _owns_lease (which heartbeats keep using): the lease must
    be ACTIVE, owned by this process, bound to the target run
    (watched_pid == run PID), and ctime-bound when determinable on both
    sides. Either side None (indeterminable identity, e.g. non-Windows
    fallback) skips only the ctime comparison -- documented residual, never
    a silent pass on pid/watched/state.
    """
    try:
        lease = (record or {}).get(kind)
        if not isinstance(lease, dict):
            return False
        if str(lease.get("state", "")).upper() != "ACTIVE":
            return False
        if int(lease.get("pid")) != os.getpid():
            return False
        if int(lease.get("watched_pid")) != int(target_pid):
            return False
    except Exception:
        return False
    try:
        mine = own_creation_time()
    except Exception:
        mine = None
    theirs = lease.get("create_time")
    if mine is not None and theirs is not None and theirs != mine:
        return False
    return True


def own_creation_time(pid: Optional[int] = None) -> Optional[str]:
    """Recorded creation-time string for pid (None when indeterminable)."""
    target = int(pid) if pid is not None else os.getpid()
    try:
        _, creation = process_info(target)
    except Exception:
        return None
    return creation


def is_canonical_pid(record: Optional[Dict[str, Any]]) -> bool:
    """True only if the registry PID is alive, python, and ctime-matched."""
    if not record or not record.get("pid"):
        return False
    try:
        return bool(pid_is_ours(int(record["pid"]),
                                record.get("create_time")))
    except (TypeError, ValueError):
        return False


def _is_active_state(state: Optional[str]) -> bool:
    return state in ("STARTING", "RUNNING", "STOPPING")


def _frozen_terminal_elapsed(record: Optional[Dict[str, Any]],
                             started_at: Any) -> Optional[float]:
    """Frozen elapsed seconds for a terminal record, or None when the
    terminal time was never recorded (legacy rows keep live-tick display,
    documented as unknown-terminal-time)."""
    try:
        last_exit = (record or {}).get("last_exit") or {}
        at = last_exit.get("at")
        if not at or not started_at:
            return None
        end_ts = datetime.fromisoformat(at).timestamp()
        start_ts = datetime.fromisoformat(started_at).timestamp()
        return max(0.0, end_ts - start_ts)
    except (TypeError, ValueError):
        return None


def _feed_unknown() -> Dict[str, Any]:
    return {"feed_health": "UNKNOWN", "latest_snapshot_age": None}


DETECTIONS_TAIL_BYTES = 262144
DETECTIONS_MAX_EVENTS = 5000


def read_run_detections() -> Dict[str, Any]:
    """Raw funding detections of the recorded run, grouped (read-only).

    Reads ONLY the registry evidence log (never user input, never a live
    probe): parses detected_event/extreme_funding_rate records from the
    tail and groups them with event_episodes v1. Returns an envelope with
    separate raw-event and grouped-episode counts plus provenance
    (log-stem run_id, linked probe UUID when present, grouping version).
    Missing log/records surface as available:false or zero counts with a
    limitation note — episodes are never invented from aggregates.
    Never writes the registry, never touches processes.
    """
    from . import event_episodes as _episodes

    def _unavailable(reason: str) -> Dict[str, Any]:
        return {"schema_version": 1, "available": False,
                "generated_at": _utc_now_iso(), "run_id": None,
                "probe_run_id": None, "grouping_version":
                _episodes.GROUPING_VERSION, "events_total": None,
                "episodes_total": None, "episodes": [],
                "limitation": reason}

    try:
        record = read_registry()
    except Exception:
        return _unavailable("registry-unreadable")
    if not record:
        return _unavailable("no-recorded-run")
    evidence = record.get("evidence") or {}
    log_path = evidence.get("log") if isinstance(evidence, dict) else None
    if not isinstance(log_path, str) or not log_path.strip():
        return _unavailable("no-evidence-log")
    run_id = None
    try:
        run_id = Path(log_path).stem or None
    except (TypeError, ValueError):
        run_id = None
    probe_uuid = record.get("probe_run_id")
    if not isinstance(probe_uuid, str) or not probe_uuid:
        probe_uuid = None
    try:
        size = os.path.getsize(log_path)
    except OSError:
        out = _unavailable("log-unavailable")
        out["run_id"] = run_id
        out["probe_run_id"] = probe_uuid
        return out
    events: List[Any] = []
    truncated = False
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            if size > DETECTIONS_TAIL_BYTES:
                fh.seek(max(0, size - DETECTIONS_TAIL_BYTES))
                fh.readline()
                truncated = True
            for line in fh:
                if len(events) >= DETECTIONS_MAX_EVENTS:
                    truncated = True
                    break
                brace = line.find("{")
                if brace < 0 or '"detected_event"' not in line:
                    continue
                try:
                    payload = json.loads(line[brace:])
                except ValueError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if payload.get("event_type") != "extreme_funding_rate":
                    continue
                details = payload.get("details")
                if not isinstance(details, dict):
                    continue
                events.append({
                    "timestamp": payload.get("timestamp"),
                    "symbol": payload.get("symbol"),
                    "funding_rate": details.get("funding_rate"),
                    "history_samples": details.get("history_samples"),
                    "lower": details.get("lower_percentile_value"),
                    "upper": details.get("upper_percentile_value"),
                })
    except OSError:
        out = _unavailable("log-unreadable")
        out["run_id"] = run_id
        out["probe_run_id"] = probe_uuid
        return out
    grouped = _episodes.group_funding_episodes(events)
    out_episodes = []
    for ep in grouped["episodes"]:
        out_episodes.append({
            "episode_id": ep["episode_id"],
            "symbol": ep["symbol"],
            "funding_rate": ep["funding_rate"],
            "repetitions": ep["repetitions"],
            "duplicate_records": ep["duplicate_records"],
            "first_observed_at": ep["first_observed_at"],
            "last_observed_at": ep["last_observed_at"],
            "duration_s": ep["duration_s"],
            "samples_first": ep["samples_first"],
            "samples_last": ep["samples_last"],
            "open_reason": ep["open_reason"],
            "close_reason": ep["close_reason"],
        })
    limitation = None
    if truncated:
        limitation = "evidence-tail-truncated"
    elif not events:
        limitation = "no-funding-events-in-evidence"
    return {"schema_version": 1, "available": True,
            "generated_at": _utc_now_iso(), "run_id": run_id,
            "probe_run_id": probe_uuid,
            "grouping_version": grouped["grouping_version"],
            "events_total": len(events),
            "episodes_total": len(out_episodes),
            "skipped_records": grouped["skipped"],
            "episodes": out_episodes, "limitation": limitation}


def _run_id_from_record(record: Optional[Dict[str, Any]]) -> Optional[str]:
    """Project run identifier for V2 visibility (no I/O).

    Derived from the evidence log stem (probe-*.log -> probe-*) when
    present, falling back to the supervisor lease run_id. None when
    unknown. Never invented.
    """
    try:
        evidence = (record or {}).get("evidence") or {}
        log = evidence.get("log") if isinstance(evidence, dict) else None
        if isinstance(log, str) and log.strip():
            return Path(log).stem or None
    except (TypeError, ValueError):
        pass
    try:
        lease = (record or {}).get("supervisor")
        if isinstance(lease, dict):
            rid = lease.get("run_id")
            if isinstance(rid, str) and rid.strip():
                return rid
    except (TypeError, ValueError):
        pass
    return None


def _process_state_for_record(record: Optional[Dict[str, Any]]) -> str:
    """Verified OS liveness distinct from the recorded registry state.

    Returns owned/gone/replaced/unknown via the canonical identity check.
    Read-only (handle query / kill-0 probe); never terminates. Unknown when
    the record carries no PID or identity is indeterminable. A recorded
    RUNNING with process_state != owned must be presented as unverified.
    """
    try:
        if not isinstance(record, dict) or record.get("pid") is None:
            return "unknown"
        return _default_process_state(record.get("pid"),
                                      record.get("create_time"))
    except Exception:
        return "unknown"


def _status_view(record: Optional[Dict[str, Any]],
                 feed: Dict[str, Any]) -> Dict[str, Any]:
    """Pure status projection (no I/O, no writes, no handle mutation).

    Shared by status() and status_readonly() so shape and nullability stay
    identical; only the reconciliation step differs.

    Visibility contract (V2 global bar): recorded registry state stays in
    `state`, while verified OS liveness rides in `process_state` +
    `process_verified`. Callers must never present `state` as liveness
    proof. Terminal rows also carry `last_exit_at` (close time) and the
    frozen `elapsed/uptime` duration. `probe_run_id` carries the probe
    UUID linked via link_probe_run_id (None = unlinked historic row =
    UNKNOWN downstream, never backfilled).
    """
    if not record:
        out: Dict[str, Any] = {"running": False, "state": "STOPPED",
                                 "pid": None, "started_at": None,
                                 "uptime_seconds": 0.0, "mode": "observe",
                                 "duration_seconds": None,
                                 "elapsed_seconds": 0.0,
                                 "remaining_seconds": None,
                                 "expected_end_at": None, "launcher": None,
                                 "preset": "standard",
                                 "run_id": None,
                                 "probe_run_id": None,
                                 "last_exit_code": None,
                                 "last_exit_reason": None,
                                 "last_exit_at": None,
                                 "process_state": "unknown",
                                 "process_verified": False,
                                 "supervisor": _supervisor_block(None),
                                 "sentinel": _sentinel_block(None)}
        out.update(feed)
        return out
    state = record.get("state", "STOPPED")
    pid = record.get("pid")
    started_at = record.get("started_at")
    uptime = 0.0
    elapsed = 0.0
    if started_at:
        try:
            start_ts = datetime.fromisoformat(started_at).timestamp()
            elapsed = max(0.0, time.time() - start_ts)
            uptime = elapsed
        except (TypeError, ValueError):
            pass
    if not _is_active_state(state):
        # 2026-10-15 (pilot probe-20261015T000730Z): a terminal session
        # ticked elapsed/uptime with the wall clock forever (ABORTED at
        # 00:08:34Z still counting minutes later), looking alive in V2.
        # Freeze at the recorded terminal time; unknown when unrecorded.
        frozen = _frozen_terminal_elapsed(record, started_at)
        if frozen is not None:
            elapsed = frozen
            uptime = frozen
    duration = record.get("duration_seconds")
    remaining = (max(0.0, duration - elapsed)
                 if isinstance(duration, (int, float)) and state == "RUNNING"
                 else None)
    last_exit = record.get("last_exit") or {}
    # Verified liveness WITHOUT calling is_canonical_pid: status_readonly
    # must stay free of the enforcement identity hook (call-count coupled
    # tests mock is_canonical with sequences; an extra call shifts them).
    # owned via _default_process_state is the strictest proof (alive +
    # ctime-matched; missing identity never owned), so verified == owned.
    try:
        proc_state = _process_state_for_record(record)
    except Exception:
        proc_state = "unknown"
    verified = proc_state == "owned"
    out = {
        "running": state == "RUNNING",
        "state": state,
        "pid": pid,
        "started_at": started_at,
        "uptime_seconds": round(uptime, 1),
        "mode": record.get("mode", "observe"),
        "duration_seconds": duration,
        "elapsed_seconds": round(elapsed, 1),
        "remaining_seconds": (round(remaining, 1)
                              if remaining is not None else None),
        "expected_end_at": record.get("expected_end_at"),
        "launcher": record.get("launcher"),
        "preset": record.get("preset", "standard"),
        "evidence": record.get("evidence"),
        "run_id": _run_id_from_record(record),
        "probe_run_id": record.get("probe_run_id")
        if isinstance(record.get("probe_run_id"), str) else None,
        "last_exit_code": last_exit.get("code"),
        "last_exit_reason": last_exit.get("reason"),
        "last_exit_at": last_exit.get("at"),
        "process_state": proc_state,
        "process_verified": verified,
        # P1-14B.7 additive supervisor contract (always present; UNKNOWN
        # when never supervised). Flows to /api/control/probe/status.
        "supervisor": _supervisor_block(record),
        # P1-14B.8 additive sentinel contract (always present; UNKNOWN
        # when never watched). Same API flow, same None-safe rules.
        "sentinel": _sentinel_block(record),
    }
    out.update(feed)
    return out


def _reconcile_stale_record() -> Optional[Dict[str, Any]]:
    """Fenced stale-record reconciliation (V2-51, mutating).

    Locked read-modify-write that transitions a stuck active record with a
    dead PID to FAILED. Fences: never touches terminal states (STOPPED /
    COMPLETED / FAILED / ABORTED), never touches STOPPING with a
    stopping_by marker (an enforcement operation owns it), never touches a
    live canonical PID. Returns (fresh record or None, wrote flag).
    OSError propagates (callers treat as unavailable).
    """
    def _reconcile(rec):
        if not rec:
            return None, False
        state = rec.get("state", "STOPPED")
        if not _is_active_state(state):
            return None, False
        if state == "STOPPING" and rec.get("stopping_by"):
            return None, False
        if is_canonical_pid(rec):
            return None, False
        rec["state"] = "FAILED"
        rec["last_exit"] = {
            "code": None,
            "reason": "terminated-externally (no exit record)",
            "at": _utc_now_iso(),
        }
        return rec, True
    try:
        wrote, _ = update_registry(_reconcile)
    except OSError:
        raise
    return read_registry(), wrote


def status(feed_provider: Optional[Callable[[], Dict[str, Any]]] = None
           ) -> Dict[str, Any]:
    """Machine-readable probe status; stale/dead PIDs reconciled safely.

    Mutating reconciliation is fenced (locked, terminal-preserving, never
    stealing an enforcement STOPPING marker). V2 GET observation must use
    status_readonly() instead -- a method name or HTTP GET does not make
    this controller pure.
    """
    feed = feed_provider() if feed_provider else _feed_unknown()
    try:
        record, wrote = _reconcile_stale_record()
    except OSError:
        record, wrote = read_registry(), False
    if wrote:
        try:
            _close_log_handles(int(record["pid"]) if record and record.get("pid") else -1)
        except (TypeError, ValueError):
            pass
    return _status_view(record, feed)


def status_readonly(feed_provider: Optional[Callable[[], Dict[str, Any]]] = None
                    ) -> Dict[str, Any]:
    """Pure runtime observation for V2 GET paths (V2-51 required).

    Same nullable shape as status(). Never writes the registry, never
    reconciles stale records, never closes or mutates log handles, never
    starts, stops or otherwise modifies processes. A dead or reused PID is
    reported as stored (caller decides); terminal races are preserved
    byte-for-byte because nothing is written.
    """
    feed = feed_provider() if feed_provider else _feed_unknown()
    record = read_registry()
    return _status_view(record, feed)


def try_register(duration_seconds: Optional[float] = None,
                 launcher: Optional[str] = None) -> Dict[str, Any]:
    """Probe-side self-registration (called by EVERY canonical launch).

    Refuses (registered=False) when a DIFFERENT live probe already holds
    the registry — the caller must exit without touching it. Registry
    write failures never break the probe: warn and run unregistered.
    """
    # Locked registration (V2-51): the live-run check and the RUNNING
    # write are one atomic update -- a concurrent enforcement terminal
    # commit is observed fresh and never silently overwritten, and an
    # enforcement STOPPING marker is never stolen (refuse while held).
    def _register(current):
        if current and _is_active_state(current.get("state")) \
                and is_canonical_pid(current) \
                and int(current.get("pid") or -1) != os.getpid():
            return None, {"registered": False, "reason": "already-running"}
        if current and current.get("state") == "STOPPING" \
                and current.get("stopping_by"):
            return None, {"registered": False, "reason": "already-stopping"}
        # P1-14B.7: a control-started child self-registers over its own
        # STARTING record — carry the evidence path forward so supervision
        # keeps its log-derived rules (UNKNOWN-safe skip otherwise). Never
        # invent evidence: only preserve what the same PID already recorded.
        preserved_evidence = None
        try:
            if current and int(current.get("pid") or -1) == os.getpid():
                preserved_evidence = current.get("evidence")
        except (TypeError, ValueError):
            preserved_evidence = None
        record = {
            "schema": REGISTRY_SCHEMA,
            "writer": "control/1",
            "state": "RUNNING",
            "pid": os.getpid(),
            "create_time": own_creation_time(),
            "started_at": _utc_now_iso(),
            "mode": os.environ.get("BOT_MODE", "observe"),
            "command": [sys.executable, "-m", "microstructure_probe"] + sys.argv[1:],
            "duration_seconds": duration_seconds,
            "expected_end_at": None,
            "launcher": launcher or os.environ.get("MICROPROBE_LAUNCHER",
                                                   "direct"),
            "preset": os.environ.get("MICROPROBE_PRESET", "standard"),
            "evidence": preserved_evidence,
            "last_exit": None,
        }
        if isinstance(duration_seconds, (int, float)):
            try:
                end_ts = (datetime.now(timezone.utc).timestamp()
                          + float(duration_seconds))
                record["expected_end_at"] = datetime.fromtimestamp(
                    end_ts, timezone.utc).isoformat(timespec="seconds")
            except (TypeError, ValueError):
                pass
        return record, {"registered": True, "record": record}
    try:
        wrote, value = update_registry(_register)
    except OSError as exc:
        return {"registered": True, "degraded": f"registry-unavailable: {exc}"}
    if not wrote:
        reason = (value or {}).get("reason", "refused")
        if reason == "already-running":
            return {"registered": False,
                    "already_running": status_readonly(),
                    "reason": "another canonical probe is already running"}
        return {"registered": False,
                "already_running": status_readonly(),
                "reason": reason}
    return value


def mark_completed(exit_code: int = 0) -> None:
    _mark_terminal("COMPLETED", exit_code, "duration-reached")


def mark_stopped(reason: str, exit_code: int = 0) -> None:
    _mark_terminal("STOPPED", exit_code, reason)


def mark_failed(reason: str, exit_code: Optional[int] = 1) -> None:
    _mark_terminal("FAILED", exit_code, reason)


def _mark_terminal(state: str, exit_code: Optional[int],
                   reason: str) -> None:
    # Fenced self-marking (V2-51): locked, same-PID only, never overwrites
    # a terminal state committed by someone else (ABORTED/STOPPED/COMPLETED
    # /FAILED wins over a late natural mark; enforcement markers included).
    def _mark(rec):
        if not rec:
            return None, False
        try:
            if int(rec.get("pid") or -1) != os.getpid():
                return None, False
        except (TypeError, ValueError):
            return None, False
        if not _is_active_state(rec.get("state")):
            return None, False
        if rec.get("state") == "STOPPING" and rec.get("stopping_by"):
            return None, False
        rec["state"] = state
        rec["last_exit"] = {"code": exit_code, "reason": reason,
                            "at": _utc_now_iso()}
        return rec, True
    try:
        update_registry(_mark)
    except (OSError, TypeError, ValueError):
        pass
    finally:
        _close_log_handles(os.getpid())


def _valid_probe_run_id(value: Any) -> bool:
    """Probe UUID shape: 32 lowercase hex chars (uuid4().hex)."""
    if not isinstance(value, str) or len(value) != 32:
        return False
    try:
        return all(c in "0123456789abcdef" for c in value.lower()) \
            and value == value.lower()
    except Exception:
        return False


def link_probe_run_id(probe_run_id: Any) -> Dict[str, Any]:
    """Bind the probe UUID to its registry record (explicit correspondence).

    The controller identifies a run by the evidence-log stem; the probe
    identifies itself by UUID. This call writes the UUID into the record so
    readers never derive identity by temporal coincidence. Fenced: the
    record must exist, be active, and belong to this process (same PID);
    an existing DIFFERENT link is never overwritten (refused) and terminal
    or foreign records are never touched. Historical records without a
    link stay absent (UNKNOWN downstream); nothing is backfilled.
    Registry failures return degraded refusals, never raise.
    """
    if not _valid_probe_run_id(probe_run_id):
        return {"linked": False, "reason": "invalid-run-id"}

    def _link(rec):
        if not rec:
            return None, {"linked": False, "reason": "no-record"}
        if not _is_active_state(rec.get("state")):
            return None, {"linked": False, "reason": "no-active-run",
                           "state": rec.get("state")}
        try:
            if int(rec.get("pid") or -1) != os.getpid():
                return None, {"linked": False, "reason": "not-ours"}
        except (TypeError, ValueError):
            return None, {"linked": False, "reason": "not-ours"}
        existing = rec.get("probe_run_id")
        if isinstance(existing, str) and existing:
            if existing == probe_run_id:
                return None, {"linked": True, "duplicate": True}
            return None, {"linked": False, "reason": "already-linked"}
        rec["probe_run_id"] = probe_run_id
        return rec, {"linked": True}
    try:
        wrote, value = update_registry(_link)
    except OSError as exc:
        return {"linked": False, "reason": "registry-unavailable: %s" % exc}
    except (TypeError, ValueError) as exc:
        return {"linked": False, "reason": "link-failed: %s" % exc}
    if not wrote:
        return value if isinstance(value, dict) else {"linked": False,
                                                      "reason": "refused"}
    return value if isinstance(value, dict) else {"linked": True}


def validate_duration(value: Any) -> Optional[int]:
    """None (continuous) or int seconds in [60, 86400]; else ValueError."""
    if value is None or value == "":
        return None
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        raise ValueError(f"invalid duration {value!r}")
    if seconds < MIN_DURATION_SECONDS or seconds > MAX_DURATION_SECONDS:
        raise ValueError(f"duration {seconds}s outside"
                         f" [{MIN_DURATION_SECONDS},{MAX_DURATION_SECONDS}]")
    return seconds


def _probe_env(launcher: str) -> Dict[str, str]:
    env = dict(os.environ)
    env["BOT_MODE"] = "observe"  # forced: observe-only, always
    env["MICROPROBE_LAUNCHER"] = launcher
    src = str(repo_root() / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    return env


def _valid_evidence(evidence: Any) -> bool:
    """A log association is usable only with a non-empty log-path string.

    Anything else (absent block, null log, blank string) means the run has
    no discoverable evidence log -- never treated as associated.
    """
    return (isinstance(evidence, dict)
            and isinstance(evidence.get("log"), str)
            and bool(evidence["log"].strip()))


def start_probe(duration_seconds: Optional[int] = None,
                launcher: str = "agent",
                preset: str = "standard",
                evidence_dir: Optional[Path] = None,
                _on_spawn: Any = None) -> Dict[str, Any]:
    """Start one canonical probe; refuse when one is already running."""
    # Pure preflight (V2-51): observation never mutates; liveness is decided
    # on a fresh read so a stale RUNNING record (dead PID) does not block a
    # new launch, while a live run or a held enforcement STOPPING does.
    live = status_readonly()
    fresh = read_registry()
    if (live["running"] and is_canonical_pid(fresh)) or \
            (live["state"] in ("STARTING", "STOPPING") and is_canonical_pid(fresh)):
        return {"started": False, "already_running": True,
                "pid": live["pid"], "uptime_seconds": live["uptime_seconds"],
                "mode": live.get("mode", "observe"), "state": live["state"]}
    duration = validate_duration(duration_seconds)
    if preset == "validation-6h":
        duration = SIX_HOURS
    elif preset == "observation-10m":
        duration = OBSERVATION_10M_SECONDS
    argv = [sys.executable, "-m", "microstructure_probe"]
    if duration is not None:
        argv += ["--duration", str(duration)]
    env = _probe_env(launcher)
    # EVERY control-started probe gets merged UTF-8 file logging (never
    # inherits the launcher console: keeps agent harnesses non-blocking
    # and satisfies the P1-10R evidence-logging contract by construction).
    if preset == "validation-6h":
        ev_dir = Path(evidence_dir) if evidence_dir else (
            repo_root() / "logs" / "p1-10r")
    else:
        ev_dir = Path(evidence_dir) if evidence_dir else (
            repo_root() / "logs" / "probe-runs")
    ev_dir.mkdir(parents=True, exist_ok=True)
    log_path = ev_dir / ("probe-%s.log" % datetime.now(timezone.utc)
                         .strftime("%Y%m%dT%H%M%SZ"))
    evidence = {"dir": str(ev_dir), "log": str(log_path)}
    env["MICROPROBE_PRESET"] = preset
    stdout_fh = open(str(log_path), "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(argv, cwd=str(repo_root()), env=env,
                                stdout=stdout_fh,
                                stderr=subprocess.STDOUT,
                                creationflags=no_window_flags())
    except OSError as exc:
        try:
            stdout_fh.close()
        except OSError:
            pass
        return {"started": False, "error": f"spawn failed: {exc}"}
    _LOG_HANDLES[proc.pid] = stdout_fh
    # Identity of OUR just-spawned child, captured once (V2-52 H2): if the
    # child self-registers RUNNING before our STARTING commit lands, the
    # commit must recognize it by PID + creation-time instead of mistaking
    # it for a foreign run. PID reuse within microseconds of our own spawn
    # is implausible; equal ctime (including None == None) is required.
    try:
        child_ctime = own_creation_time(proc.pid)
    except Exception:
        child_ctime = None
    if _on_spawn is not None:
        _on_spawn(proc, child_ctime)
    # Locked STARTING commit (V2-51): refuse a live run or a held
    # enforcement STOPPING observed fresh; terminal/stale records yield to
    # the new launch. A spawn failure after Popen is the caller's orphan to
    # reap -- the record below is rolled back to FAILED only when it is
    # still our STARTING (never stealing another writer's state).
    def _commit_start(rec):
        if rec and _is_active_state(rec.get("state")) and is_canonical_pid(rec):
            # Same-child adoption (V2-52 H2): our own spawn already
            # self-registered RUNNING (or STARTING). Adopt it verbatim --
            # no kill, no STARTING overwrite, evidence preserved. A held
            # enforcement marker on it is NOT adopted (refuse instead).
            try:
                same = (int(rec.get("pid")) == int(proc.pid)
                        and rec.get("create_time") == child_ctime)
            except (TypeError, ValueError):
                same = False
            if same and rec.get("state") in ("STARTING", "RUNNING") \
                    and not rec.get("stopping_by"):
                return None, {"started": True, "adopted": True,
                              "evidence": rec.get("evidence"),
                              "state": rec.get("state")}
            return None, {"started": False}
        if rec and rec.get("state") == "STOPPING" and rec.get("stopping_by"):
            return None, {"started": False}
        return {
            "schema": REGISTRY_SCHEMA,
            "writer": "control/1",
            "state": "STARTING",
            "pid": proc.pid,
            "create_time": child_ctime,
            "started_at": _utc_now_iso(),
            "mode": "observe",
            "command": argv,
            "duration_seconds": duration,
            "expected_end_at": None,
            "launcher": launcher,
            "preset": _recorded_preset(preset),
            "evidence": evidence,
            "last_exit": None,
        }, {"started": True, "adopted": False}
    try:
        wrote, outcome = update_registry(_commit_start)
    except OSError:
        wrote, outcome = False, {}
    if isinstance(outcome, dict) and outcome.get("adopted"):
        stored_ev = outcome.get("evidence")
        if _valid_evidence(stored_ev):
            # Own child already carries a usable log: preserve it verbatim
            # (byte-preserving -- nothing is written). No kill.
            return {"started": True, "pid": proc.pid, "mode": "observe",
                    "duration_seconds": duration,
                    "preset": _recorded_preset(preset),
                    "evidence": stored_ev,
                    "adopted_child_registration": True,
                    "evidence_associated": stored_ev == evidence}
        # Evidence handoff (V2-54 R2): the child self-registered with no
        # log, while this controlled start created one. Bind OUR log to
        # the SAME child via a conditional locked update that revalidates
        # PID + creation-time + active state on fresh state. Anything else
        # (foreign run, terminal state, enforcement hold) refuses without
        # touching the record -- and a refused/failed handoff never
        # reports a confirmed association.
        def _associate_log(rec):
            if not rec:
                return None, {"associated": False,
                              "reason": "no-record"}
            try:
                same = (int(rec.get("pid")) == int(proc.pid)
                        and rec.get("create_time") == child_ctime)
            except (TypeError, ValueError):
                same = False
            if not same:
                return None, {"associated": False,
                              "reason": "not-ours-anymore"}
            if not _is_active_state(rec.get("state")):
                return None, {"associated": False,
                              "reason": "terminal-now"}
            if rec.get("stopping_by"):
                return None, {"associated": False,
                              "reason": "enforcement-hold"}
            if _valid_evidence(rec.get("evidence")):
                return None, {"associated": False,
                              "reason": "evidence-present",
                              "evidence": rec.get("evidence")}
            rec["evidence"] = evidence
            return rec, {"associated": True}
        try:
            wrote_ev, assoc = update_registry(_associate_log)
        except OSError:
            wrote_ev, assoc = False, {"associated": False,
                                      "reason": "registry-unavailable"}
        if isinstance(assoc, dict) and assoc.get("associated") and wrote_ev:
            return {"started": True, "pid": proc.pid, "mode": "observe",
                    "duration_seconds": duration,
                    "preset": _recorded_preset(preset),
                    "evidence": evidence,
                    "adopted_child_registration": True,
                    "evidence_associated": True}
        reason = (assoc or {}).get("reason", "refused")
        if reason == "evidence-present":
            # A usable log raced in: preserve it, report as stored. It is
            # only "associated" when it is byte-identical to our log.
            raced_ev = (assoc or {}).get("evidence")
            return {"started": True, "pid": proc.pid, "mode": "observe",
                    "duration_seconds": duration,
                    "preset": _recorded_preset(preset),
                    "evidence": raced_ev,
                    "adopted_child_registration": True,
                    "evidence_associated": raced_ev == evidence}
        if reason == "registry-unavailable":
            # Verified live child keeps running (never destroy it over a
            # transient registry failure); the association is UNCONFIRMED.
            return {"started": True, "pid": proc.pid, "mode": "observe",
                    "duration_seconds": duration,
                    "preset": _recorded_preset(preset),
                    "evidence": None,
                    "adopted_child_registration": True,
                    "evidence_associated": False,
                    "evidence_result": reason}
        if reason == "not-ours-anymore":
            # A foreign/different record now holds the registry: our spawn
            # is redundant -- orphan cleanup exactly once, foreign kept.
            try:
                stdout_fh.close()
            except OSError:
                pass
            _LOG_HANDLES.pop(proc.pid, None)
            try:
                proc.kill()
            except Exception:
                pass
            return {"started": False, "already_running": True,
                    "pid": None, "state": status_readonly().get("state"),
                    "adopted_child_registration": True,
                    "evidence_associated": False,
                    "evidence_result": reason}
        # Same child turned terminal or fell under an enforcement hold:
        # do not interfere with it and do not kill it.
        return {"started": False, "pid": proc.pid,
                "reason": "adopted-record-superseded",
                "adopted_child_registration": True,
                "evidence_associated": False,
                "evidence_result": reason}
    if not wrote:
        try:
            stdout_fh.close()
        except OSError:
            pass
        _LOG_HANDLES.pop(proc.pid, None)
        try:
            proc.kill()
        except Exception:
            pass
        return {"started": False, "already_running": True,
                "pid": None, "state": status_readonly().get("state")}
    # The child self-registers RUNNING on entry (self-registration flips
    # STARTING → RUNNING within seconds, incl. externally launched probes
    # that never pass through here).
    return {"started": True, "pid": proc.pid, "mode": "observe",
            "duration_seconds": duration,
            "preset": _recorded_preset(preset),
            "evidence": evidence}


def stop_probe(requester: str = "agent") -> Dict[str, Any]:
    """Terminate ONLY the verified canonical probe PID (bounded wait).

    V2-51 hardening: STOPPING acquisition refuses a held enforcement
    marker (already-stopping) and terminal states; the final
    verification-plus-handle-kill runs under the registry lock so a
    takeover cannot interleave; STOPPED/FAILED marks are fenced against
    run replacement and foreign markers and never overwrite ABORTED.
    """
    record = read_registry()
    if not record or not _is_active_state(record.get("state")):
        return {"stopped": False, "error": "no-active-probe",
                "state": (record or {}).get("state", "STOPPED")}
    try:
        pid = int(record.get("pid"))
    except (TypeError, ValueError):
        return {"stopped": False, "error": "bad-record-pid"}
    expected_ctime = record.get("create_time")
    stop_marker = "stop:%s:%d" % (requester, os.getpid())

    def _claim_stop(rec):
        if not rec or not _is_active_state(rec.get("state")):
            return None, {"proceed": False, "reason": "no-active-probe"}
        try:
            fresh_pid = int(rec.get("pid"))
        except (TypeError, ValueError):
            return None, {"proceed": False, "reason": "bad-record-pid"}
        if fresh_pid != pid or rec.get("create_time") != expected_ctime:
            return None, {"proceed": False, "reason": "run-replaced"}
        if not is_canonical_pid(rec):
            # Fenced stale recovery: only from a non-marker active state;
            # never steals an enforcement STOPPING or a terminal record.
            if rec.get("state") == "STOPPING" and rec.get("stopping_by"):
                return None, {"proceed": False, "reason": "already-stopping"}
            rec["state"] = "FAILED"
            rec["last_exit"] = {
                "code": None,
                "reason": "stale-record-recovered-on-stop (pid dead/mismatched)",
                "at": _utc_now_iso()}
            return rec, {"proceed": False, "reason": "stale-probe-record-recovered"}
        if rec.get("state") == "STOPPING":
            if rec.get("stopping_by"):
                return None, {"proceed": False, "reason": "already-stopping"}
            rec["state"] = "STOPPING"
            rec["stopping_by"] = stop_marker
            return rec, {"proceed": True}
        rec["state"] = "STOPPING"
        rec["stopping_by"] = stop_marker
        return rec, {"proceed": True}

    try:
        wrote, gate = update_registry(_claim_stop)
    except OSError:
        return {"stopped": False, "error": "registry-unavailable"}
    if not wrote or not gate.get("proceed"):
        reason = (gate or {}).get("reason", "refused")
        if reason == "stale-probe-record-recovered":
            return {"stopped": False, "error": reason, "state": "FAILED"}
        return {"stopped": False, "error": reason, "pid": pid}

    def _verify_and_kill(rec):
        if not rec or not _is_active_state(rec.get("state")):
            return None, {"proceed": False, "reason": "no-active-probe"}
        if rec.get("state") != "STOPPING" or rec.get("stopping_by") != stop_marker:
            return None, {"proceed": False, "reason": "takeover-after-claim"}
        try:
            fresh_pid = int(rec.get("pid"))
        except (TypeError, ValueError):
            return None, {"proceed": False, "reason": "bad-record-pid"}
        if fresh_pid != pid or rec.get("create_time") != expected_ctime:
            return None, {"proceed": False, "reason": "run-replaced"}
        if not is_canonical_pid(rec):
            return None, {"proceed": False, "reason": "stale-record-not-touched"}
        if not _terminate_verified_pid(pid, expected_ctime):
            return None, {"proceed": False, "reason": "handle-identity-refused"}
        return None, {"proceed": True}

    try:
        _, gate2 = update_registry(_verify_and_kill)
    except OSError:
        return {"stopped": False, "error": "registry-unavailable", "pid": pid}
    if not gate2.get("proceed"):
        return {"stopped": False, "error": gate2.get("reason", "refused"), "pid": pid}
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not pid_is_ours(pid, expected_ctime):
            break
        time.sleep(0.2)
    if pid_is_ours(pid, expected_ctime):
        def _fail_mark(rec):
            if not rec or rec.get("state") != "STOPPING":
                return None, False
            if rec.get("stopping_by") != stop_marker:
                return None, False
            try:
                if int(rec.get("pid")) != pid:
                    return None, False
            except (TypeError, ValueError):
                return None, False
            if rec.get("create_time") != expected_ctime:
                return None, False
            rec["state"] = "FAILED"
            rec["last_exit"] = {"code": None, "reason": "stop-timeout"
                               " (process survived bounded wait)",
                               "at": _utc_now_iso()}
            return rec, True
        try:
            update_registry(_fail_mark)
        except OSError:
            pass
        return {"stopped": False, "error": "stop-timeout", "pid": pid}

    def _stop_mark(rec):
        # Never overwrite ABORTED or any other terminal state.
        if not rec or rec.get("state") != "STOPPING":
            return None, False
        if rec.get("stopping_by") != stop_marker:
            return None, False
        try:
            if int(rec.get("pid")) != pid:
                return None, False
        except (TypeError, ValueError):
            return None, False
        if rec.get("create_time") != expected_ctime:
            return None, False
        rec["state"] = "STOPPED"
        rec["last_exit"] = {"code": 0,
                            "reason": f"stopped-by-{requester}",
                            "at": _utc_now_iso()}
        return rec, True
    try:
        wrote, _ = update_registry(_stop_mark)
    except OSError:
        return {"stopped": False, "error": "registry-unavailable", "pid": pid}
    if not wrote:
        return {"stopped": False, "error": "superseded", "pid": pid}
    _close_log_handles(pid)
    return {"stopped": True, "pid": pid}


def _record_native_error() -> None:
    """Store one bounded Windows error code (GetLastError + timestamp)."""
    try:
        import ctypes as _ct
        code = int(_ct.windll.kernel32.GetLastError())
    except Exception:
        code = -1
    try:
        _LAST_NATIVE_ERROR.clear()
        _LAST_NATIVE_ERROR.update({"code": code, "at": _utc_now_iso()})
    except Exception:
        pass


def _terminate_verified_pid(pid: int,
                              expected_ctime: Optional[str] = None) -> bool:
    """Terminate ONLY the verified OS process; False when refused.

    Handle-bound identity (V2-51): on Windows the same OpenProcess handle
    is used to read creation time (GetProcessTimes) and to terminate, so a
    PID reused between verification and kill cannot be hit. Native
    signatures (V2-52 H1, exact in V2-54 R1) are explicit HANDLE-width with
    32-bit Win32 BOOL results checked: a TerminateProcess refusal
    (0/exception) returns False with a bounded GetLastError record -- never
    reported as success. The handle is closed on success, refusal and
    exception paths alike.
    Missing expected_ctime falls back to handle-liveness only (open +
    queryable times): PID-reuse is then NOT excluded -- documented
    residual, not complete protection. On POSIX the pre-kill recheck
    (pid_is_ours immediately before os.kill) narrows the reuse window to
    microseconds -- documented residual, no handle API.
    Callers must hold the registry lock across their final verification and
    this call so a registry takeover cannot interleave at the boundary.
    Returns True when termination was issued, False when identity failed or
    the native API refused (nothing terminated).
    """
    try:
        target = int(pid)
    except (TypeError, ValueError):
        return False
    if os.name == "nt":
        try:
            import ctypes as _ct
            kernel32 = _ct.windll.kernel32  # type: ignore[attr-defined]
        except Exception:
            return False
        _configure_kernel_signatures(kernel32)
        handle = None
        try:
            access = 0x0001 | 0x1000  # TERMINATE | QUERY_LIMITED
            handle = kernel32.OpenProcess(access, False, target)
            if not handle:
                return False
            if expected_ctime is not None:
                # Verify creation time on THIS handle (no reopen: no reuse).
                try:
                    ft_c, ft_e, ft_k, ft_u = (_FILETIME() for _ in range(4))
                    ok = kernel32.GetProcessTimes(
                        handle, _ct.byref(ft_c), _ct.byref(ft_e),
                        _ct.byref(ft_k), _ct.byref(ft_u))
                    if not ok:
                        return False
                    ticks = (int(ft_c.dwHighDateTime) << 32) + int(ft_c.dwLowDateTime)
                    epoch_us = ticks // 10 - 11644473600000000
                    if epoch_us <= 0:
                        return False
                    from datetime import datetime as _dt, timezone as _tz
                    actual = _dt.fromtimestamp(epoch_us / 1_000_000,
                                               tz=_tz.utc).isoformat()
                    if actual != expected_ctime:
                        return False
                except Exception:
                    return False
            else:
                # Documented fallback: no expected creation time, so only
                # handle queryability is verified (live-handle proof).
                try:
                    q_c, q_e, q_k, q_u = (_FILETIME() for _ in range(4))
                    if not kernel32.GetProcessTimes(
                            handle, _ct.byref(q_c), _ct.byref(q_e),
                            _ct.byref(q_k), _ct.byref(q_u)):
                        return False
                except Exception:
                    return False
            try:
                issued = kernel32.TerminateProcess(handle, 0)
            except Exception:
                _record_native_error()
                return False
            if not issued:
                _record_native_error()
                return False
            return True
        finally:
            try:
                if handle:
                    import ctypes as _ct2
                    _ct2.windll.kernel32.CloseHandle(handle)
            except Exception:
                pass
    else:
        try:
            if expected_ctime is not None:
                if not bool(pid_is_ours(target, expected_ctime)):
                    return False
            os.kill(target, signal.SIGTERM)
        except (OSError, ProcessLookupError, ValueError, TypeError):
            # Process already gone counts as terminated for abort purposes,
            # but only after the identity check above passed.
            return True
        return True


def _close_log_handles(pid: int) -> None:
    fh = _LOG_HANDLES.pop(int(pid), None) if pid and pid > 0 else None
    if fh is not None:
        try:
            fh.close()
        except OSError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Canonical market-probe lifecycle (observe-only)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="read-only probe status")
    start = sub.add_parser("start", help="start one observe-mode probe")
    start.add_argument("--duration", default=None,
                       help="seconds in [60,86400]; omit for continuous")
    start.add_argument("--preset", default="standard",
                       choices=["standard", "validation-6h",
                                "observation-10m"],
                       help="validation-6h forces 21600s + evidence wrapper; "
                            "observation-10m forces 600s")
    sub.add_parser("stop", help="stop the verified canonical probe")
    sup = sub.add_parser("supervise",
                         help="watch the active run and enforce abort gates")
    sup.add_argument("--interval", default=30.0,
                     help="seconds between checks (5..300)")
    sup.add_argument("--timeout", default=None,
                     help="max watch seconds (60..86400); omit to watch "
                          "until the run ends")
    sen = sub.add_parser("sentinel",
                         help="watch the supervision itself; safe-stop the "
                              "run if supervision goes stale")
    sen.add_argument("--interval", default=30.0,
                     help="seconds between checks (5..300)")
    sen.add_argument("--timeout", default=None,
                     help="max watch seconds (60..86400); omit to watch "
                          "until the run ends")
    sen.add_argument("--stale-after", default=120.0,
                     help="supervision staleness seconds triggering safe-stop")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "status":
        print(json.dumps(status(), indent=1))
        return 0
    if args.cmd == "start":
        try:
            result = start_probe(args.duration, launcher="agent",
                                 preset=args.preset)
        except ValueError as exc:
            print(json.dumps({"started": False, "error": str(exc)}))
            return 2
        print(json.dumps(result, indent=1))
        return 0 if result.get("started") else 1
    if args.cmd == "stop":
        result = stop_probe(requester="agent")
        print(json.dumps(result, indent=1))
        return 0 if result.get("stopped") else 1
    if args.cmd == "supervise":
        try:
            result = supervise(interval_s=float(args.interval),
                               timeout_s=(float(args.timeout)
                                          if args.timeout else None))
        except ValueError as exc:
            print(json.dumps({"supervised": False, "error": str(exc)}))
            return 2
        print(json.dumps(result, indent=1, default=str))
        return 0 if result.get("ok", False) else 1
    if args.cmd == "sentinel":
        try:
            result = sentinel(interval_s=float(args.interval),
                              timeout_s=(float(args.timeout)
                                         if args.timeout else None),
                              stale_after_s=float(args.stale_after))
        except ValueError as exc:
            print(json.dumps({"watching": False, "error": str(exc)}))
            return 2
        print(json.dumps(result, indent=1, default=str))
        return 0 if result.get("ok", False) else 1
    return 2


# ------------------------------------------------------------------
# P1-14B.7 persistent supervision & enforced abort gates.
#
# A supervisor independent of any agent session watches ONE authorized
# run via this canonical registry. It evaluates the documented abort
# rules every cycle from probe-produced evidence and enforces a one-shot
# verified-PID stop with persisted reason. It never starts or restarts
# runs, never touches foreign processes, and never acts on UNKNOWN
# (explicit safe policy per rule: missing telemetry skips the rule,
# never reads as zero).
#
# Survival model: the supervisor is an ordinary detached process (same
# launch pattern as control-started probes); agent disconnects, closed
# terminals, and harness timeouts do not affect it. A registry lease
# (freshness-checked) serializes supervisors: live lease -> second
# supervisor refuses; stale lease -> recorded takeover. Streak counters
# persist in the lease so a restarted supervisor continues counting.
# ------------------------------------------------------------------

ABORTED = "ABORTED"

SUPERVISOR_CHECK_DEFAULT_S = 30.0
SUPERVISOR_INTERVAL_MIN_S = 5.0
SUPERVISOR_INTERVAL_MAX_S = 300.0
SUPERVISOR_MAX_FAILURES = 5
SUPERVISOR_LEASE_FRESH_S = 90.0

# Abort rules (exact semantics; thresholds are LOCAL_POLICY except the 5 %
# reject rule, which follows the official cumulative methodology):
REJECT_ABORT_RATE = 0.05          # cumulative rejected/total, latest summary
RECONNECT_ABORT_COUNT = 5         # error-reconnect events in trailing window
RECONNECT_ABORT_WINDOW_S = 600.0
PERSIST_EVENTS_ABORT_MIN = 2      # persistence_error events in trailing window
PERSIST_ABORT_PRIOR = 1           # ...seen on the previous check too (2 straight)
CLOCK_ABORT_MS = 30000.0          # |host-Binance| sustained...
CLOCK_ABORT_PRIOR = 2             # ...on 3 straight checks (noisy single samples)
DB_ABORT_STREAK = 5               # consecutive unreadable-DB checks (lock transients)
WATCHDOG_FORCED_MIN = 3           # compound backstop-loss signal...
WATCHDOG_ERRORS_MIN = 3           # ...with rising reject rate
EVIDENCE_TAIL_BYTES = 131072
EVIDENCE_TAIL_LINES = 400


def _abort(rule: str, reason: str, threshold: Any,
           observed: Any) -> Dict[str, Any]:
    return {"rule": rule, "reason": reason, "threshold": threshold,
            "observed": observed}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def evaluate_supervision(snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pure abort decision from one evidence snapshot (no I/O).

    Every metric arrives Optional; missing/non-numeric input skips its
    rule (UNKNOWN policy — never silent zero). First breach in priority
    order wins (safety > rejects > reconnects > persistence > clock >
    db > watchdog-overwhelm); streak inputs count CONSECUTIVE PRIOR
    breaching checks (loop-maintained, lease-persisted).
    """
    if not isinstance(snapshot, dict):
        return None
    mode = snapshot.get("mode")
    if mode is not None and str(mode) != "observe":
        return _abort("safety-violation", "mode != observe", "observe", mode)
    safety = snapshot.get("safety")
    if isinstance(safety, dict):
        try:
            keys = int(safety.get("apiKeysUsed") or 0)
        except (TypeError, ValueError):
            keys = 0
        try:
            orders = int(safety.get("realOrdersSent") or 0)
        except (TypeError, ValueError):
            orders = 0
        if keys > 0 or orders > 0 or bool(safety.get("orderExecutionPathPresent")):
            return _abort("safety-violation",
                          "observe-only invariant broken", "0/0/false",
                          {"apiKeysUsed": keys, "realOrdersSent": orders,
                           "orderExecutionPathPresent": bool(
                               safety.get("orderExecutionPathPresent"))})
    rate = snapshot.get("reject_rate")
    if _is_number(rate) and rate == rate and rate > REJECT_ABORT_RATE:
        return _abort("timestamp-reject-rate",
                      "cumulative reject rate above limit", REJECT_ABORT_RATE,
                      float(rate))
    now_s = snapshot.get("now_s")
    events = snapshot.get("reconnect_events")
    if isinstance(events, list) and _is_number(now_s):
        recent = 0
        for item in events:
            try:
                ts = float(item[0]) if isinstance(item, (list, tuple)) else float("nan")
            except (TypeError, ValueError, IndexError):
                continue
            if ts == ts and 0 <= now_s - ts <= RECONNECT_ABORT_WINDOW_S:
                recent += 1
        if recent > RECONNECT_ABORT_COUNT:
            return _abort("reconnect-storm",
                          "error reconnects in trailing 10 min",
                          ">%d/600s" % RECONNECT_ABORT_COUNT, recent)
    perr = snapshot.get("persistence_errors_10m")
    pstreak = snapshot.get("persistence_streak", 0)
    prosp_deg = snapshot.get("prospective_degraded", False)
    perr_n = perr if _is_number(perr) and perr == perr else 0
    try:
        pstreak_n = int(pstreak or 0)
    except (TypeError, ValueError):
        pstreak_n = 0
    if (perr_n >= PERSIST_EVENTS_ABORT_MIN or prosp_deg is True) and pstreak_n >= PERSIST_ABORT_PRIOR:
        return _abort("persistence-errors",
                      "critical persistence failures sustained", ">=2 events/10min x2 checks",
                      {"events_10m": perr_n, "prospective_degraded": bool(prosp_deg)})
    clk = snapshot.get("clock_offset_ms")
    cstreak = snapshot.get("clock_streak", 0)
    try:
        cstreak_n = int(cstreak or 0)
    except (TypeError, ValueError):
        cstreak_n = 0
    if _is_number(clk) and clk == clk and abs(float(clk)) > CLOCK_ABORT_MS and cstreak_n >= CLOCK_ABORT_PRIOR:
        return _abort("clock-skew", "host clock beyond limit, sustained",
                      ">%dms x3" % int(CLOCK_ABORT_MS), float(clk))
    db_ok = snapshot.get("db_readable")
    dstreak = snapshot.get("db_fail_streak", 0)
    try:
        dstreak_n = int(dstreak or 0)
    except (TypeError, ValueError):
        dstreak_n = 0
    if db_ok is False and dstreak_n >= DB_ABORT_STREAK:
        return _abort("db-unreadable", "operational DB unreadable, sustained",
                      ">=%d straight checks" % (DB_ABORT_STREAK + 1), dstreak_n)
    try:
        forced = int(snapshot.get("forced_reconnects") or 0)
    except (TypeError, ValueError):
        forced = 0
    try:
        err_total = int(snapshot.get("error_reconnects") or 0)
    except (TypeError, ValueError):
        err_total = 0
    rate_prev = snapshot.get("reject_rate_prev")
    rising = (_is_number(rate) and _is_number(rate_prev)
              and rate == rate and rate_prev == rate_prev
              and float(rate) > float(rate_prev))
    if forced >= WATCHDOG_FORCED_MIN and err_total >= WATCHDOG_ERRORS_MIN and rising:
        return _abort("watchdog-overwhelmed",
                      "forced recoveries keep firing while errors and rejects climb",
                      "forced>=3, errors>=3, rising", float(rate))
    return None


def _parse_log_timestamp(prefix: str) -> Optional[float]:
    try:
        return datetime.strptime(prefix.strip(), "%Y-%m-%d %H:%M:%S,%f").timestamp()
    except (TypeError, ValueError):
        return None


def collect_supervision_snapshot(record: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble one evidence snapshot from the run's evidence log tail.

    Read-only. Tolerates missing/truncated/unparsable logs by returning
    UNKNOWN (None) fields — the decision core then skips those rules.
    Single-line JSON records (canonical UTF-8 evidence contract); wrapped
    lines are skipped, never rejoined (UNKNOWN-safe direction).
    """
    now_s = time.time()
    snapshot: Dict[str, Any] = {
        "now_s": now_s,
        "mode": (record or {}).get("mode"),
        "safety": None,
        "reject_rate": None,
        "total_messages": None,
        "reconnect_events": [],
        "persistence_errors_10m": 0,
        "prospective_degraded": False,
        "clock_offset_ms": None,
        "forced_reconnects": None,
        "error_reconnects": None,
        "reject_rate_prev": None,
    }
    evidence = (record or {}).get("evidence") or {}
    log_path = evidence.get("log")
    if not log_path:
        return snapshot
    try:
        size = os.path.getsize(log_path)
    except OSError:
        return snapshot
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            if size > EVIDENCE_TAIL_BYTES:
                fh.seek(max(0, size - EVIDENCE_TAIL_BYTES))
                fh.readline()
            lines = fh.read().splitlines()[-EVIDENCE_TAIL_LINES:]
    except OSError:
        return snapshot
    latest = None
    latest_rt = -1.0
    reconnect_events: List[Any] = []
    persist_ts: List[float] = []
    for line in lines:
        ts = _parse_log_timestamp(line[:23])
        brace = line.find("{")
        if brace < 0:
            continue
        try:
            payload = json.loads(line[brace:])
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        kind = payload.get("kind")
        if kind in ("summary", "final_summary"):
            try:
                rt = float(payload.get("runtimeSeconds", -1))
            except (TypeError, ValueError):
                rt = -1.0
            if rt >= latest_rt:
                latest_rt = rt
                latest = payload
        elif kind == "connection_error":
            if ts is not None:
                reconnect_events.append((ts, str(payload.get("endpoint", "?"))))
        elif kind == "persistence_error":
            if ts is not None and now_s - ts <= 600.0:
                persist_ts.append(ts)
    snapshot["reconnect_events"] = reconnect_events[-200:]
    snapshot["persistence_errors_10m"] = len(persist_ts)
    if latest is not None:
        dq = latest.get("dataQuality") or {}
        if isinstance(dq, dict):
            msgs = dq.get("messagesByStream") or {}
            if isinstance(msgs, dict):
                try:
                    total = sum(int(v) for v in msgs.values())
                except (TypeError, ValueError):
                    total = None
                snapshot["total_messages"] = total
                rej = dq.get("timestampRejected")
                if _is_number(rej) and isinstance(total, int) and total > 0:
                    snapshot["reject_rate"] = float(rej) / float(total)
            reconn = dq.get("reconnections") or {}
            if isinstance(reconn, dict):
                try:
                    snapshot["error_reconnects"] = sum(
                        int(v) for v in reconn.values())
                except (TypeError, ValueError):
                    pass
        safety = latest.get("safety")
        if isinstance(safety, dict):
            snapshot["safety"] = safety
        clock = latest.get("clock") or {}
        if isinstance(clock, dict) and _is_number(clock.get("clockOffsetMs")):
            snapshot["clock_offset_ms"] = float(clock.get("clockOffsetMs"))
        fresh = latest.get("freshness") or {}
        if isinstance(fresh, dict):
            forced = fresh.get("forcedReconnects") or {}
            if isinstance(forced, dict):
                try:
                    snapshot["forced_reconnects"] = sum(
                        int(v) for v in forced.values())
                except (TypeError, ValueError):
                    pass
        prosp = latest.get("prospective") or {}
        if isinstance(prosp, dict) and prosp.get("state") == "DEGRADED":
            snapshot["prospective_degraded"] = True
    return snapshot


def _default_db_path() -> Optional[Path]:
    """Operational DB path (config carries no db_path — P1-14B.1 proof)."""
    try:
        return repo_root() / "data" / "microprobe.db"
    except Exception:
        return None


def probe_db_readable() -> Optional[bool]:
    """Read-only open of the operational DB. None when unresolvable."""
    import sqlite3
    path = _default_db_path()
    if path is None:
        return None
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5.0)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return True
    except Exception:
        return False


def read_supervision() -> Optional[Dict[str, Any]]:
    """Current supervisor lease block, or None."""
    record = read_registry()
    if not record:
        return None
    lease = record.get("supervisor")
    return dict(lease) if isinstance(lease, dict) else None


def _lease_live(lease: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(lease, dict):
        return False
    try:
        pid = int(lease.get("pid"))
    except (TypeError, ValueError):
        return False
    try:
        alive = bool(pid_is_ours(pid, lease.get("create_time")))
    except Exception:
        return False
    if not alive:
        return False
    try:
        last = datetime.fromisoformat(str(lease.get("last_check_at")))
        age = (datetime.now(timezone.utc) - last).total_seconds()
    except (TypeError, ValueError):
        return False
    return 0 <= age <= SUPERVISOR_LEASE_FRESH_S


def claim_supervision() -> Dict[str, Any]:
    """Claim the active run for supervision (lease). Refuses when another
    live supervisor holds a fresh lease, when no run is active, or when
    the record is stale. Never starts, stops, or otherwise touches runs."""
    record = read_registry()
    if not record or not _is_active_state(record.get("state")):
        return {"supervised": False, "reason": "no-active-run",
                "state": (record or {}).get("state", "STOPPED")}
    if not is_canonical_pid(record):
        return {"supervised": False, "reason": "stale-record"}
    def _claim(record):
        if not record or not _is_active_state(record.get("state")):
            return None, {"supervised": False, "reason": "no-active-run",
                          "state": (record or {}).get("state", "STOPPED")}
        # Authoritative liveness recheck INSIDE the lock: a racing claim
        # that won between our read and our write is observed here, so
        # exactly one claimant wins (probes_racing_claims_single_winner).
        if not is_canonical_pid(record):
            return None, {"supervised": False, "reason": "stale-record"}
        lease = record.get("supervisor")
        if isinstance(lease, dict) and str(lease.get("state", "")).upper() == "ACTIVE" \
                and _lease_live(lease):
            return None, {"supervised": False, "reason": "already-supervised",
                          "supervisor_pid": lease.get("pid")}
        prev = lease.get("pid") if isinstance(lease, dict) else None
        now_iso = _utc_now_iso()
        record["supervisor"] = {
            "pid": os.getpid(), "create_time": own_creation_time(),
            "started_at": now_iso, "last_check_at": now_iso,
            "state": "ACTIVE", "consecutive_failures": 0,
            "prev_supervisor_pid": prev, "watched_pid": record.get("pid"),
            "streaks": {"persistence": 0, "clock": 0, "db": 0},
            "abort": None,
        }
        return record, {"supervised": True, "pid": os.getpid(),
                        "watched_pid": record.get("pid"),
                        "prev_supervisor_pid": prev}
    try:
        _, value = update_registry(_claim)
    except OSError as exc:
        return {"supervised": False, "reason": "registry-unavailable: %s" % exc}
    return value


def _heartbeat_lease(consecutive_failures: int = 0,
                     streaks: Optional[Dict[str, int]] = None) -> bool:
    """Heartbeat the supervisor lease. Fenced: a replaced watcher (lease
    pid != self) is a silent no-op -- it must not touch the new lease.
    Returns True when the heartbeat was effectively written, False on
    refusal or registry failure (callers counting effective writes)."""
    def _beat(record):
        if not record or not isinstance(record.get("supervisor"), dict):
            return None, False
        if not _owns_lease(record, "supervisor"):
            return None, False
        record["supervisor"]["last_check_at"] = _utc_now_iso()
        record["supervisor"]["consecutive_failures"] = consecutive_failures
        if streaks is not None:
            record["supervisor"]["streaks"] = dict(streaks)
        return record, True
    try:
        wrote, _ = update_registry(_beat)
    except OSError:
        return False
    return bool(wrote)


def _fail_lease() -> bool:
    def _fail(record):
        if not record or not isinstance(record.get("supervisor"), dict):
            return None, False
        if not _owns_lease(record, "supervisor"):
            return None, False
        record["supervisor"]["state"] = "FAILED"
        record["supervisor"]["last_check_at"] = _utc_now_iso()
        return record, True
    try:
        wrote, _ = update_registry(_fail)
    except OSError:
        return False
    return bool(wrote)


def _owner_refusal_reason(rec: Any, kind: str, target_pid: int) -> str:
    """Specific refusal reason for an invalid enforcement lease."""
    try:
        lease = (rec or {}).get(kind)
        if not isinstance(lease, dict):
            return "replaced-owner"
        if int(lease.get("pid")) != os.getpid():
            return "replaced-owner"
        if int(lease.get("watched_pid")) != int(target_pid):
            return "wrong-run-lease"
    except Exception:
        return "replaced-owner"
    return "owner-lease-invalid"


def enforce_abort(decision: Dict[str, Any],
                  owner_kind: Optional[str] = None) -> Dict[str, Any]:
    """Execute one verified abort: re-validate identity, stop via the
    canonical path, mark ABORTED with reason. Never touches foreign PIDs,
    never claims ABORTED unless the watched process is confirmed dead.
    owner_kind ("supervisor"|"sentinel") requires an ACTIVE lease owned by
    this process AND bound to the target run (watched_pid == run PID) with
    matching creation time when determinable: a replaced watcher, a
    wrong-run lease, or a run that left the watched state is reported
    refused/superseded, never ABORTED.
    Fencing (V2-51 operation boundary): STOPPING acquisition AND the final
    verification-plus-termination both happen under the registry lock on
    fresh state, and termination itself runs while the lock is held via a
    handle-verified kill (same OS handle verifies creation time and
    terminates: PID reuse cannot interleave, registry takeover cannot
    interleave). A refused/failed gate never reaches termination; checking
    ownership only after a kill is insufficient.
    """
    record = read_registry()
    if not record or not _is_active_state(record.get("state")):
        return {"aborted": False, "reason": "no-active-run"}
    try:
        pid = int(record.get("pid"))
    except (TypeError, ValueError):
        return {"aborted": False, "reason": "bad-record-pid"}
    if not is_canonical_pid(record):
        return {"aborted": False, "reason": "stale-record-not-touched"}
    try:
        expected_ctime = record.get("create_time")
    except AttributeError:
        expected_ctime = None
    stopping_marker = ("enforce:%s:%d" % (owner_kind or "direct", os.getpid()))

    def _claim_stop(rec):
        # Locked acquisition gate: re-verify EVERYTHING on fresh state.
        # Any refusal returns without touching the record -- and crucially
        # without terminating anything afterwards.
        if not rec or not _is_active_state(rec.get("state")):
            return None, {"proceed": False, "reason": "no-active-run"}
        try:
            fresh_pid = int(rec.get("pid"))
        except (TypeError, ValueError):
            return None, {"proceed": False, "reason": "bad-record-pid"}
        if fresh_pid != pid or rec.get("create_time") != expected_ctime:
            return None, {"proceed": False, "reason": "run-replaced"}
        if not is_canonical_pid(rec):
            return None, {"proceed": False, "reason": "stale-record-not-touched"}
        if owner_kind is not None and not _owner_lease_valid(rec, owner_kind, fresh_pid):
            return None, {"proceed": False,
                           "reason": _owner_refusal_reason(rec, owner_kind, fresh_pid)}
        if rec.get("state") == "STOPPING":
            # Marker acquisition: a foreign STOPPING transition already
            # holds the run -- back off without touching it and without
            # terminating. Our own marker (same process retry) may resume.
            if rec.get("stopping_by") != stopping_marker:
                return None, {"proceed": False, "reason": "already-stopping"}
            return rec, {"proceed": True}
        rec["state"] = "STOPPING"
        rec["stopping_by"] = stopping_marker
        return rec, {"proceed": True}

    try:
        wrote, gate = update_registry(_claim_stop)
    except OSError:
        return {"aborted": False, "reason": "registry-unavailable"}
    if not wrote or not gate.get("proceed"):
        return {"aborted": False,
                "reason": gate.get("reason", "refused"),
                "pid": pid}

    def _verify_and_kill(rec):
        # Runs INSIDE the registry lock: final re-verification and the
        # handle-verified kill are atomic -- no takeover can interleave
        # between validation and the irreversible operation. Returns
        # (None, gate): never writes here (STOPPING already acquired).
        if not rec or not _is_active_state(rec.get("state")):
            return None, {"proceed": False, "reason": "no-active-run"}
        if rec.get("state") != "STOPPING" or rec.get("stopping_by") != stopping_marker:
            return None, {"proceed": False, "reason": "takeover-after-claim"}
        try:
            fresh_pid = int(rec.get("pid"))
        except (TypeError, ValueError):
            return None, {"proceed": False, "reason": "bad-record-pid"}
        if fresh_pid != pid or rec.get("create_time") != expected_ctime:
            return None, {"proceed": False, "reason": "run-replaced"}
        if not is_canonical_pid(rec):
            return None, {"proceed": False, "reason": "stale-record-not-touched"}
        if owner_kind is not None and not _owner_lease_valid(rec, owner_kind, fresh_pid):
            return None, {"proceed": False,
                           "reason": _owner_refusal_reason(rec, owner_kind, fresh_pid)}
        killed = _terminate_verified_pid(pid, expected_ctime)
        if not killed:
            return None, {"proceed": False, "reason": "handle-identity-refused"}
        return None, {"proceed": True}

    try:
        _, gate2 = update_registry(_verify_and_kill)
    except OSError:
        return {"aborted": False, "reason": "registry-unavailable", "pid": pid}
    if not gate2.get("proceed"):
        return {"aborted": False,
                "reason": gate2.get("reason", "refused"),
                "pid": pid}
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not pid_is_ours(pid, expected_ctime):
            break
        time.sleep(0.2)
    if pid_is_ours(pid, expected_ctime):
        def _fail_mark(rec):
            # Fenced: same run (pid+ctime), still OUR stopping marker, and
            # (when given) still our run-bound lease. A foreign STOPPING
            # marker, a replaced run, a wrong-run lease or a lost lease all
            # refuse without touching.
            if not rec or rec.get("state") not in ("STOPPING",):
                return None, False
            if rec.get("stopping_by") != stopping_marker:
                return None, False
            try:
                if int(rec.get("pid")) != pid:
                    return None, False
            except (TypeError, ValueError):
                return None, False
            if rec.get("create_time") != expected_ctime:
                return None, False
            if owner_kind is not None and not _owner_lease_valid(rec, owner_kind, pid):
                return None, False
            rec["state"] = "FAILED"
            rec["last_exit"] = {
                "code": None,
                "reason": "abort stop-timeout (process survived bounded wait)",
                "at": _utc_now_iso()}
            return rec, True
        try:
            update_registry(_fail_mark)
        except OSError:
            pass
        return {"aborted": False, "reason": "stop-timeout", "pid": pid}

    def _abort_mark(rec):
        # Fenced terminal marking: only when the run is still in OUR
        # STOPPING state (not someone else's STOPPED/COMPLETED/FAILED) and
        # -- when an owner kind is given -- our run-bound lease still owns
        # it. Anything else reports superseded without touching the record.
        # Run identity (pid + creation-time) is rechecked against the
        # pre-terminate snapshot: a replaced run is never marked.
        if not rec or rec.get("state") != "STOPPING":
            return None, False
        if rec.get("stopping_by") != stopping_marker:
            return None, False
        try:
            if int(rec.get("pid")) != pid:
                return None, False
        except (TypeError, ValueError):
            return None, False
        if rec.get("create_time") != expected_ctime:
            return None, False
        if owner_kind is not None and not _owner_lease_valid(rec, owner_kind, pid):
            return None, False
        rec["state"] = ABORTED
        rec["aborted_by"] = owner_kind if owner_kind else "direct"
        rec["abort_rule"] = decision.get("rule")
        rec["abort_reason"] = decision.get("reason")
        rec["abort_threshold"] = decision.get("threshold")
        rec["abort_observed"] = decision.get("observed")
        rec["abort_at"] = _utc_now_iso()
        rec["last_exit"] = {"code": 0,
                            "reason": "aborted-%s" % decision.get("rule"),
                            "at": _utc_now_iso()}
        return rec, True

    try:
        wrote, _ = update_registry(_abort_mark)
    except OSError:
        return {"aborted": False, "reason": "registry-unavailable"}
    if not wrote:
        return {"aborted": False, "reason": "superseded"}
    _close_log_handles(pid)
    return {"aborted": True, "pid": pid, "rule": decision.get("rule"),
            "reason": decision.get("reason")}


def supervise_once() -> Dict[str, Any]:
    """One supervision cycle: terminal/identity/snapshot/decision/enforce.

    Returns an outcome dict; mutates only the supervisor lease block (or
    the ABORTED terminal marking after a confirmed kill). Never starts,
    restarts, or touches foreign processes.
    """
    record = read_registry()
    if not record:
        return {"outcome": "no-active-run"}
    state = record.get("state")
    if state == ABORTED or not _is_active_state(state):
        return {"outcome": "already-terminal" if state == ABORTED else "no-active-run",
                "state": state}
    if not is_canonical_pid(record):
        return {"outcome": "stale-record"}
    lease = record.get("supervisor") if isinstance(record.get("supervisor"), dict) else {}
    streaks = dict(lease.get("streaks") or {})
    failures = 0
    try:
        failures = int((lease.get("consecutive_failures") or 0))
    except (TypeError, ValueError):
        failures = 0
    try:
        snapshot = collect_supervision_snapshot(record)
    except Exception as exc:
        failures += 1
        _heartbeat_lease(consecutive_failures=failures, streaks=streaks)
        if failures >= SUPERVISOR_MAX_FAILURES:
            _fail_lease()
            return {"outcome": "supervisor-failed", "error": str(exc)[:200]}
        return {"outcome": "check-failed", "error": str(exc)[:200],
                "consecutive_failures": failures}
    try:
        db_ok = probe_db_readable()
    except Exception:
        db_ok = None
    snapshot["db_readable"] = db_ok
    db_streak = int(streaks.get("db", 0) or 0)
    if db_ok is False:
        db_streak += 1
    elif db_ok is True:
        db_streak = 0
    snapshot["db_fail_streak"] = db_streak
    decision = evaluate_supervision(snapshot)
    perr_now = snapshot.get("persistence_errors_10m")
    clk = snapshot.get("clock_offset_ms")
    new_streaks = {
        "persistence": (int(streaks.get("persistence", 0) or 0) + 1
                        if isinstance(perr_now, (int, float)) and perr_now >= 2
                        else 0),
        "clock": (int(streaks.get("clock", 0) or 0) + 1
                  if isinstance(clk, (int, float)) and abs(float(clk)) > CLOCK_ABORT_MS
                  else 0),
        "db": db_streak,
    }
    if decision is None:
        _heartbeat_lease(consecutive_failures=0, streaks=new_streaks)
        return {"outcome": "ok", "streaks": new_streaks}
    result = enforce_abort(decision, owner_kind="supervisor")
    _heartbeat_lease(consecutive_failures=0, streaks=new_streaks)
    if result.get("aborted"):
        return {"outcome": "aborted", "decision": decision, "result": result}
    return {"outcome": "abort-failed", "decision": decision, "result": result}


def supervise(interval_s: float = SUPERVISOR_CHECK_DEFAULT_S,
              timeout_s: Optional[float] = None) -> Dict[str, Any]:
    """Watch the active run until terminal/timeout. Detached-safe: no
    stdin/stdout dependency beyond an optional evidence log; agent
    disconnects do not affect it. Never starts or restarts runs."""
    try:
        interval = float(interval_s)
    except (TypeError, ValueError):
        raise ValueError("invalid interval %r" % (interval_s,))
    if not (SUPERVISOR_INTERVAL_MIN_S <= interval <= SUPERVISOR_INTERVAL_MAX_S):
        raise ValueError("interval %ss outside [%s,%s]" % (
            interval_s, SUPERVISOR_INTERVAL_MIN_S, SUPERVISOR_INTERVAL_MAX_S))
    timeout = None
    if timeout_s is not None and timeout_s != "":
        timeout = validate_duration(timeout_s)
        if timeout is None:
            raise ValueError("invalid timeout %r" % (timeout_s,))
    claim = claim_supervision()
    if not claim.get("supervised"):
        return {"ok": False, "aborted": False, "cycles": 0,
                "refused": claim.get("reason"), "claim": claim}
    print(json.dumps({"supervising": True, "pid": os.getpid(),
                      "watched_pid": claim.get("watched_pid")}), flush=True)
    cycles = 0
    outcome: Dict[str, Any] = {"outcome": "timeout"}
    start = time.monotonic()
    try:
        while True:
            if timeout is not None and time.monotonic() - start >= timeout:
                outcome = {"outcome": "timeout"}
                break
            outcome = supervise_once()
            cycles += 1
            if outcome.get("outcome") in ("aborted", "already-terminal",
                                          "no-active-run", "stale-record",
                                          "abort-failed", "supervisor-failed"):
                break
            time.sleep(interval)
    finally:
        def _finish_supervisor(record):
            if not record or not isinstance(record.get("supervisor"), dict):
                return None, False
            if not _owns_lease(record, "supervisor"):
                return None, False
            if outcome.get("outcome") not in ("aborted",):
                record["supervisor"]["state"] = (
                    "FAILED" if outcome.get("outcome") == "supervisor-failed"
                    else "STOPPED")
                record["supervisor"]["last_check_at"] = _utc_now_iso()
                return record, True
            return None, False
        try:
            update_registry(_finish_supervisor)
        except OSError:
            pass
    ok = outcome.get("outcome") in ("aborted", "already-terminal",
                                    "no-active-run", "stale-record", "timeout")
    return {"ok": ok, "aborted": outcome.get("outcome") == "aborted",
            "cycles": cycles, "outcome": outcome.get("outcome"),
            "decision": outcome.get("decision"),
            "claim": {"watched_pid": claim.get("watched_pid")}}


def _supervisor_block(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Additive V2 status contract (always present, None-safe).

    Display contract (P1-14B.8, documented for V2 integration):
      SUPERVISOR_ACTIVE -- lease ACTIVE + heartbeat in [0, 90 s] + watcher
        identity verified + run associated. A point-in-time observation,
        NOT proof of protection.
      SUPERVISOR_STALE  -- established lease failing any check above.
      SUPERVISOR_UNKNOWN -- no lease block ever (never supervised).
    Raw evidence rides alongside (lease_state, lease_last_check_at,
    watcher_pid, watcher_create_time). Terminal ABORTED state still maps
    to ABORT_TRIGGERED with rule/reason/threshold/observed. V2 must not
    turn the label into proof.
    """
    block: Dict[str, Any] = {
        "state": "SUPERVISOR_UNKNOWN",
        "watched_pid": None,
        "run_id": None,
        "last_check_at": None,
        "abort_triggered": False,
        "abort_reason": None,
        "abort_rule": None,
        "abort_threshold": None,
        "abort_observed": None,
        "supervision_source": None,
        "lease_state": None,
        "lease_last_check_at": None,
        "watcher_pid": None,
        "watcher_create_time": None,
    }
    if not isinstance(record, dict):
        return block
    lease = record.get("supervisor")
    if not isinstance(lease, dict):
        lease = None
    if isinstance(lease, dict):
        block["lease_state"] = lease.get("state")
        block["lease_last_check_at"] = lease.get("last_check_at")
        block["watched_pid"] = lease.get("watched_pid")
        block["watcher_pid"] = lease.get("pid")
        block["watcher_create_time"] = lease.get("create_time")
        block["last_check_at"] = lease.get("last_check_at")
        block["supervision_source"] = "supervisor:control-supervise"
    if _supervisor_lease_verified(record):
        block["state"] = "SUPERVISOR_ACTIVE"
    elif isinstance(lease, dict):
        block["state"] = "SUPERVISOR_STALE"
    evidence = record.get("evidence") or {}
    if isinstance(evidence, dict) and evidence.get("log"):
        try:
            block["run_id"] = Path(evidence["log"]).stem
        except (TypeError, ValueError):
            block["run_id"] = None
    if block["watched_pid"] is None:
        block["watched_pid"] = record.get("pid")
    if record.get("state") == ABORTED:
        block["abort_triggered"] = True
        block["abort_reason"] = record.get("abort_reason")
        block["abort_rule"] = record.get("abort_rule")
        block["abort_threshold"] = record.get("abort_threshold")
        block["abort_observed"] = record.get("abort_observed")
    return block


def _supervisor_lease_verified(record: Dict[str, Any]) -> bool:
    """Display-time verification (no state change): ACTIVE + fresh + alive + bound."""
    try:
        lease = (record or {}).get("supervisor")
        if not isinstance(lease, dict):
            return False
        if str(lease.get("state", "")).upper() != "ACTIVE":
            return False
        try:
            watched = int(lease.get("watched_pid"))
            run_pid = int((record or {}).get("pid"))
        except (TypeError, ValueError):
            return False
        if watched != run_pid:
            return False
        age = _supervision_age_s(lease)
        if age is None or not (0 <= age <= SUPERVISOR_LEASE_FRESH_S):
            return False
        return bool(pid_is_ours(int(lease.get("pid")), lease.get("create_time")))
    except Exception:
        return False


# ------------------------------------------------------------------
# P1-14B.8 sentinel: supervision-liveness watchdog with enforced stop.
#
# The supervisor (P1-14B.7) watches the run; the sentinel watches the
# SUPERVISION ITSELF. If an established supervision goes stale (or
# reports FAILED) while its run is still active, the sentinel enforces a
# safe stop through the canonical verified-PID path (enforce_abort) and
# persists the reason. It never starts runs, never touches foreign
# processes, and never acts on missing supervision (continuity guard
# only -- run supervision existing in the first place belongs to the
# launcher, which starts the supervisor before/with the run).
# ------------------------------------------------------------------

SENTINEL_CHECK_DEFAULT_S = 30.0
SENTINEL_STALE_AFTER_S = 120.0

_SENTINEL_FAILURES: Dict[str, int] = {}


def _sentinel_failure_key() -> str:
    try:
        return str(registry_path())
    except Exception:
        return "unknown-registry"


def claim_sentinel() -> Dict[str, Any]:
    """Claim a sentinel lease for the active run. Refuses on no run,
    stale record, or a live fresh lease (second sentinel). Takeover of
    stale/corrupt leases is recorded. Never touches runs."""
    record = read_registry()
    if not record or not _is_active_state(record.get("state")):
        return {"watching": False, "reason": "no-active-run",
                "state": (record or {}).get("state", "STOPPED")}
    if not is_canonical_pid(record):
        return {"watching": False, "reason": "stale-record"}
    def _claim(record):
        if not record or not _is_active_state(record.get("state")):
            return None, {"watching": False, "reason": "no-active-run",
                          "state": (record or {}).get("state", "STOPPED")}
        if not is_canonical_pid(record):
            return None, {"watching": False, "reason": "stale-record"}
        lease = record.get("sentinel")
        if isinstance(lease, dict) and str(lease.get("state", "")).upper() == "ACTIVE" \
                and _lease_live(lease):
            return None, {"watching": False, "reason": "already-watched",
                          "sentinel_pid": lease.get("pid")}
        prev = lease.get("pid") if isinstance(lease, dict) else None
        now_iso = _utc_now_iso()
        record["sentinel"] = {
            "pid": os.getpid(), "create_time": own_creation_time(),
            "started_at": now_iso, "last_check_at": now_iso,
            "state": "ACTIVE", "consecutive_failures": 0,
            "prev_sentinel_pid": prev, "watched_pid": record.get("pid"),
            "action": None,
        }
        return record, {"watching": True, "pid": os.getpid(),
                        "watched_pid": record.get("pid"),
                        "prev_sentinel_pid": prev}
    try:
        _, value = update_registry(_claim)
    except OSError as exc:
        return {"watching": False,
                "reason": "registry-unavailable: %s" % exc}
    return value


def _heartbeat_sentinel(failures: int = 0, action: Optional[Dict[str, Any]] = None) -> bool:
    """Heartbeat the sentinel lease. Fenced like _heartbeat_lease.

    Returns True when effectively written, False on refusal/failure."""
    def _beat(record):
        if not record or not isinstance(record.get("sentinel"), dict):
            return None, False
        if not _owns_lease(record, "sentinel"):
            return None, False
        record["sentinel"]["last_check_at"] = _utc_now_iso()
        record["sentinel"]["consecutive_failures"] = failures
        if action is not None:
            record["sentinel"]["action"] = action
        return record, True
    try:
        wrote, _ = update_registry(_beat)
    except Exception:
        return False
    return bool(wrote)


def _fail_sentinel() -> bool:
    def _fail(record):
        if not record or not isinstance(record.get("sentinel"), dict):
            return None, False
        if not _owns_lease(record, "sentinel"):
            return None, False
        record["sentinel"]["state"] = "FAILED"
        record["sentinel"]["last_check_at"] = _utc_now_iso()
        return record, True
    try:
        wrote, _ = update_registry(_fail)
    except Exception:
        return False
    return bool(wrote)


def _supervision_age_s(lease: Any) -> Optional[float]:
    """Seconds since the supervisor lease heartbeat (None when unknown)."""
    if not isinstance(lease, dict):
        return None
    try:
        last = datetime.fromisoformat(str(lease.get("last_check_at")))
        return (datetime.now(timezone.utc) - last).total_seconds()
    except (TypeError, ValueError):
        return None


def _supervision_verdict(record: Dict[str, Any],
                         stale_after_s: float,
                         *,
                         watcher_alive: bool) -> str:
    """Verified supervision verdict (P1-14B.8 hardening).

    ok-supervised requires EVERYTHING, evaluated in order: an ACTIVE lease,
    a parseable heartbeat inside [0, stale_after_s] (future timestamps and
    malformed stamps are never fresh), a watcher identity match, and
    association with this run (lease watched_pid == record pid).
    Anything established-but-inapplicable is LOSS (abort), never absence:
      stopped-supervision  -- lease STOPPED (orderly exit) while run active
      dead-supervision     -- watcher PID/image/ctime check fails
      mismatched-supervision -- lease covers a different run
      failed-supervision   -- lease FAILED
      stale-supervision    -- heartbeat missing/malformed/old/future
    unsupervised is returned ONLY when no lease block ever existed
    (continuity guard: existence belongs to the launcher).
    watcher_alive is REQUIRED (no default): callers must verify identity
    explicitly; there is no lenient path.
    """
    lease = record.get("supervisor")
    if not isinstance(lease, dict):
        return "unsupervised"
    state = str(lease.get("state", "")).upper()
    if state == "FAILED":
        return "failed-supervision"
    if state != "ACTIVE":
        return "stopped-supervision"
    try:
        watched = int(lease.get("watched_pid"))
        run_pid = int((record or {}).get("pid"))
    except (TypeError, ValueError):
        return "mismatched-supervision"
    if watched != run_pid:
        return "mismatched-supervision"
    age = _supervision_age_s(lease)
    if age is None or not (0 <= age <= float(stale_after_s)):
        return "stale-supervision"
    if watcher_alive is not True:
        return "dead-supervision"
    return "ok-supervised"


def _verify_supervisor_lease(record: Dict[str, Any]) -> bool:
    """Watcher identity for the supervisor lease: PID alive + python image
    + creation-time match. True/False only (never None): unverifiable means
    dead for abort purposes. Failures resolve to False, never raise."""
    try:
        lease = (record or {}).get("supervisor")
        if not isinstance(lease, dict):
            return False
        return bool(pid_is_ours(int(lease.get("pid")),
                                lease.get("create_time")))
    except Exception:
        return False


def _supervision_verdict_requires_abort(verdict: str) -> bool:
    return verdict not in ("ok-supervised", "unsupervised")


def sentinel_once(stale_after_s: float = SENTINEL_STALE_AFTER_S) -> Dict[str, Any]:
    """One sentinel cycle (public): evaluate, then heartbeat the lease.

    Heartbeats advance on EVERY cycle outcome (including ok/unsupervised/
    terminal reads) so a live sentinel never looks stale; failures to
    persist the heartbeat never mask the cycle outcome.
    """
    outcome = _sentinel_cycle(stale_after_s)
    # Fenced heartbeat: locked read-modify-write that only touches OUR
    # sentinel lease. A replaced sentinel no-ops; concurrent supervisor
    # heartbeats serialize on the lock instead of being clobbered by an
    # unlocked read-modify-write. Failures never mask the cycle outcome.
    def _touch(rec):
        if not rec or not isinstance(rec.get("sentinel"), dict):
            return None, False
        if not _owns_lease(rec, "sentinel"):
            return None, False
        rec["sentinel"]["last_check_at"] = _utc_now_iso()
        if outcome.get("outcome") == "aborted-supervision-lost":
            decision = outcome.get("decision") or {}
            rec["sentinel"]["action"] = {
                "rule": decision.get("rule", "supervision-lost"),
                "at": _utc_now_iso(),
                "aborted": True,
            }
        return rec, True
    try:
        update_registry(_touch)
    except OSError:
        pass
    return outcome


def _sentinel_cycle(stale_after_s: float) -> Dict[str, Any]:
    """One sentinel cycle. Returns an outcome dict; enforces a safe stop
    only when an ESTABLISHED supervision went stale/FAILED while its run is
    active. Never starts runs, never touches foreign processes."""
    key = _sentinel_failure_key()
    try:
        record = read_registry()
        if not record:
            return {"outcome": "no-active-run"}
        state = record.get("state")
        if state == ABORTED or not _is_active_state(state):
            return {"outcome": "already-terminal"
                    if state == ABORTED else "no-active-run",
                    "state": state}
        if not is_canonical_pid(record):
            return {"outcome": "stale-record"}
        verdict = _supervision_verdict(
            record, float(stale_after_s),
            watcher_alive=_verify_supervisor_lease(record))
        if verdict == "ok-supervised":
            _heartbeat_sentinel()
            _SENTINEL_FAILURES.pop(key, None)
            return {"outcome": "ok-supervised"}
        if verdict == "unsupervised":
            _heartbeat_sentinel()
            _SENTINEL_FAILURES.pop(key, None)
            return {"outcome": "unsupervised"}
        decision = {
            "rule": "supervision-lost",
            "reason": ("supervisor %s while run active; no verifiable "
                       "supervision" % verdict.replace("-", " ")),
            "threshold": "<=%ss since heartbeat" % stale_after_s,
            "observed": _supervision_age_s(record.get("supervisor")),
        }
        result = enforce_abort(decision, owner_kind="sentinel")
        _heartbeat_sentinel(action={"rule": decision["rule"],
                                    "at": _utc_now_iso(),
                                    "aborted": bool(result.get("aborted"))})
        _SENTINEL_FAILURES.pop(key, None)
        if result.get("aborted"):
            return {"outcome": "aborted-supervision-lost",
                    "decision": decision, "result": result}
        return {"outcome": "abort-failed", "decision": decision,
                "result": result}
    except Exception as exc:
        n = _SENTINEL_FAILURES.get(key, 0) + 1
        _SENTINEL_FAILURES[key] = n
        try:
            _heartbeat_sentinel(failures=n)
        except Exception:
            pass
        if n >= SUPERVISOR_MAX_FAILURES:
            try:
                _fail_sentinel()
            except Exception:
                pass
            return {"outcome": "sentinel-failed", "error": str(exc)[:200]}
        return {"outcome": "check-failed", "error": str(exc)[:200],
                "consecutive_failures": n}


def sentinel(interval_s: float = SUPERVISOR_CHECK_DEFAULT_S,
             timeout_s: Optional[float] = None,
             stale_after_s: float = SENTINEL_STALE_AFTER_S) -> Dict[str, Any]:
    """Watch the supervision until terminal/timeout. Detached-safe (no
    stdin/stdout needs beyond dev output); agent disconnects do not affect
    it. Never starts runs, never touches foreign processes."""
    try:
        interval = float(interval_s)
    except (TypeError, ValueError):
        raise ValueError("invalid interval %r" % (interval_s,))
    if not (SUPERVISOR_INTERVAL_MIN_S <= interval <= SUPERVISOR_INTERVAL_MAX_S):
        raise ValueError("interval %ss outside [%s,%s]" % (
            interval_s, SUPERVISOR_INTERVAL_MIN_S,
            SUPERVISOR_INTERVAL_MAX_S))
    try:
        stale_after = float(stale_after_s)
    except (TypeError, ValueError):
        raise ValueError("invalid stale_after %r" % (stale_after_s,))
    if stale_after <= 0:
        raise ValueError("stale_after must be positive")
    timeout = None
    if timeout_s is not None and timeout_s != "":
        timeout = validate_duration(timeout_s)
        if timeout is None:
            raise ValueError("invalid timeout %r" % (timeout_s,))
    claim = claim_sentinel()
    if not claim.get("watching"):
        return {"ok": False, "aborted": False, "cycles": 0,
                "refused": claim.get("reason"), "claim": claim}
    print(json.dumps({"watching": True, "pid": os.getpid(),
                      "watched_pid": claim.get("watched_pid")}), flush=True)
    cycles = 0
    outcome: Dict[str, Any] = {"outcome": "timeout"}
    start = time.monotonic()
    try:
        while True:
            if timeout is not None and time.monotonic() - start >= timeout:
                outcome = {"outcome": "timeout"}
                break
            outcome = sentinel_once(stale_after_s=stale_after)
            cycles += 1
            if outcome.get("outcome") in ("aborted-supervision-lost",
                                          "already-terminal",
                                          "no-active-run",
                                          "stale-record",
                                          "abort-failed",
                                          "sentinel-failed"):
                break
            time.sleep(interval)
    finally:
        def _finish_sentinel(record):
            if not record or not isinstance(record.get("sentinel"), dict):
                return None, False
            if not _owns_lease(record, "sentinel"):
                return None, False
            if outcome.get("outcome") not in ("aborted-supervision-lost",):
                record["sentinel"]["state"] = (
                    "FAILED" if outcome.get("outcome") == "sentinel-failed"
                    else "STOPPED")
                record["sentinel"]["last_check_at"] = _utc_now_iso()
                return record, True
            return None, False
        try:
            update_registry(_finish_sentinel)
        except OSError:
            pass
    ok = outcome.get("outcome") in ("aborted-supervision-lost",
                                    "already-terminal", "no-active-run",
                                    "stale-record", "timeout")
    return {"ok": ok, "aborted": outcome.get("outcome") == "aborted-supervision-lost",
            "cycles": cycles, "outcome": outcome.get("outcome"),
            "decision": outcome.get("decision"),
            "claim": {"watched_pid": claim.get("watched_pid")}}


def _sentinel_block(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Additive sentinel status (always present, None-safe).

    Display contract (P1-14B.8, documented for V2 integration):
      SENTINEL_ACTIVE -- lease ACTIVE + heartbeat in [0, 90 s] + watcher
        identity verified + run associated. A point-in-time observation,
        NOT proof of protection.
      SENTINEL_STALE  -- established lease failing any check above
        (stale/missing/malformed/future heartbeat, dead watcher,
        mismatched run, non-ACTIVE state).
      SENTINEL_UNKNOWN -- no lease block ever (never supervised).
    Raw evidence rides alongside for independent verification
    (lease_state, lease_last_check_at, watcher_pid, watcher_create_time).
    Nullability: every value key may be None when unknown; state never None.
    Timestamps: ISO UTC strings exactly as stored. Freshness bound:
    SUPERVISOR_LEASE_FRESH_S. V2 must not turn the label into proof.
    """
    block: Dict[str, Any] = {
        "state": "SENTINEL_UNKNOWN",
        "watched_pid": None,
        "run_id": None,
        "last_check_at": None,
        "action_taken": None,
        "action_reason": None,
        "supervision_source": None,
        "lease_state": None,
        "lease_last_check_at": None,
        "watcher_pid": None,
        "watcher_create_time": None,
    }
    if not isinstance(record, dict):
        return block
    lease = record.get("sentinel")
    if not isinstance(lease, dict):
        evidence = record.get("evidence") or {}
        if isinstance(evidence, dict) and evidence.get("log"):
            try:
                block["run_id"] = Path(evidence["log"]).stem
            except (TypeError, ValueError):
                block["run_id"] = None
        if block["watched_pid"] is None:
            block["watched_pid"] = record.get("pid")
        return block
    block["lease_state"] = lease.get("state")
    block["lease_last_check_at"] = lease.get("last_check_at")
    block["watched_pid"] = lease.get("watched_pid")
    block["watcher_pid"] = lease.get("pid")
    block["watcher_create_time"] = lease.get("create_time")
    block["last_check_at"] = lease.get("last_check_at")
    block["supervision_source"] = "sentinel:control-sentinel"
    action = lease.get("action")
    if isinstance(action, dict):
        block["action_taken"] = "aborted-supervision-lost" if action.get("aborted") else "none"
        block["action_reason"] = action.get("rule", "supervision-lost")
    evidence = record.get("evidence") or {}
    if isinstance(evidence, dict) and evidence.get("log"):
        try:
            block["run_id"] = Path(evidence["log"]).stem
        except (TypeError, ValueError):
            block["run_id"] = None
    if block["watched_pid"] is None:
        block["watched_pid"] = record.get("pid")
    if _sentinel_lease_verified(record, lease):
        block["state"] = "SENTINEL_ACTIVE"
    else:
        block["state"] = "SENTINEL_STALE"
    return block


def _sentinel_lease_verified(record: Dict[str, Any], lease: Dict[str, Any]) -> bool:
    """Display-time verification (no state change): ACTIVE + fresh + alive + bound."""
    try:
        if str(lease.get("state", "")).upper() != "ACTIVE":
            return False
        try:
            watched = int(lease.get("watched_pid"))
            run_pid = int((record or {}).get("pid"))
        except (TypeError, ValueError):
            return False
        if watched != run_pid:
            return False
        age = _supervision_age_s(lease)
        if age is None or not (0 <= age <= SUPERVISOR_LEASE_FRESH_S):
            return False
        return bool(pid_is_ours(int(lease.get("pid")), lease.get("create_time")))
    except Exception:
        return False


# ------------------------------------------------------------------
# Supervised transactional launch (ENABLED through the verified chain).
#
# Contract: docs/SUPERVISED_LAUNCH_CONTRACT.md. A single operation that
# starts the probe plus both watchers, verifies every component against
# the run inside a finite budget, and rolls back EVERYTHING it launched
# on any failure. Enabled 2026-10-13 (O1 observacion conjunta V2) ONLY
# with the full chain, never as a bare flag flip: V2 readiness-green +
# confirmation token + preset allowlist + verified identity/heartbeat +
# stop wiring (frontend runtime-control.ts + launch-readiness.ts),
# observe-only enforced by the probe itself, failure matrix + isolated
# tests green (V2PathTest pins the fixed dashboard call: confirm,
# association, rollback, stop). Decision recorded in docs/DECISIONS.md (no anonymous
# launches; kill-only rollback; foreign/terminal never touched).
# Reuses start_probe / leases / identity / verified termination / the
# registry lock; no parallel controller exists.
# ------------------------------------------------------------------

SUPERVISED_LAUNCH_ENABLED = True

SUPERVISED_LAUNCH_VERIFY_BUDGET_S = 60.0
SUPERVISED_LAUNCH_POLL_S = 2.0
_SUPERVISED_LAUNCH_SCOPE = ("point-in-time confirmation, "
                            "not future protection")
_SUPERVISED_LAUNCH_FUTURE_TOL_S = 0.0


def _default_watcher_alive(pid: Any, ctime: Any) -> bool:
    """Launch-only strict identity; missing times never confirm."""
    return _default_process_state(pid, ctime) == "owned"


def _default_identity() -> Dict[str, Any]:
    """Production identity bundle (injectable fakes in tests)."""
    return {
        "is_canonical": is_canonical_pid,
        "watcher_alive": _default_watcher_alive,
        "terminate": _terminate_verified_pid,
        "proc_ctime": own_creation_time,
        "read_record": read_registry,
        "process_state": _default_process_state,
    }


def _default_watcher_spawner(kind: str) -> Any:
    """Production watcher spawner (dormant while disabled).

    Popens the canonical `control supervise` / `control sentinel` entry
    point with merged UTF-8 logging, mirroring start_probe conventions.
    Returns the Popen object (pid + kill). Never runs in tests.
    """
    def _spawn(run_pid: int) -> Any:
        command = {"supervisor": "supervise", "sentinel": "sentinel"}[kind]
        argv = [sys.executable, "-m", "microstructure_probe.control", command,
                "--interval", str(SUPERVISOR_CHECK_DEFAULT_S)]
        log_dir = repo_root() / "logs" / "probe-runs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / ("watcher-%s-%s.log" % (
            kind, datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")))
        fh = open(str(log_path), "w", encoding="utf-8")
        try:
            proc = subprocess.Popen(argv, cwd=str(repo_root()),
                                    stdout=fh, stderr=subprocess.STDOUT,
                                    creationflags=no_window_flags())
        except OSError:
            try:
                fh.close()
            except OSError:
                pass
            raise
        _LOG_HANDLES[proc.pid] = fh
        return proc
    return _spawn


def _verify_watcher_lease(record: Any, kind: str, watcher_pid: Any,
                          watcher_ctime: Any, run_pid: Any,
                          watcher_alive: Any) -> Any:
    """Pure per-watcher confirmation (contract §4).

    Returns (ok, detail). Never touches the registry, processes, or the
    clock beyond reading it. `watcher_alive` is injected (production:
    PID+image+ctime liveness).
    """
    detail: Dict[str, Any] = {"kind": kind}
    lease = (record or {}).get(kind) if isinstance(record, dict) else None
    if not isinstance(lease, dict):
        return False, {**detail, "reason": "lease-absent"}
    if str(lease.get("state", "")).upper() != "ACTIVE":
        return False, {**detail, "reason": "lease-not-active",
                       "state": lease.get("state")}
    try:
        if int(lease.get("pid")) != int(watcher_pid):
            return False, {**detail, "reason": "owner-changed"}
    except (TypeError, ValueError):
        return False, {**detail, "reason": "lease-bad-pid"}
    if not watcher_ctime:
        return False, {**detail, "reason": "watcher-identity-unknown"}
    if lease.get("create_time") != watcher_ctime:
        return False, {**detail, "reason": "watcher-replaced"}
    try:
        if int(lease.get("watched_pid")) != int(run_pid):
            return False, {**detail, "reason": "wrong-run-lease"}
    except (TypeError, ValueError):
        return False, {**detail, "reason": "lease-bad-watched"}
    try:
        alive = bool(watcher_alive(watcher_pid, watcher_ctime))
    except Exception:
        alive = False
    if not alive:
        return False, {**detail, "reason": "watcher-dead"}
    try:
        last = datetime.fromisoformat(str(lease.get("last_check_at")))
        age = (datetime.now(timezone.utc) - last).total_seconds()
    except (TypeError, ValueError):
        return False, {**detail, "reason": "malformed-heartbeat"}
    if age < 0 \
            or age > SUPERVISOR_LEASE_FRESH_S:
        return False, {**detail, "reason": "stale-heartbeat", "age_s": age}
    return True, {**detail, "reason": "verified", "age_s": age}


def _verify_launch_state(record: Any, run: Dict[str, Any],
                         watchers: Dict[str, Dict[str, Any]],
                         identity: Dict[str, Any]) -> Any:
    """Pure launch-state evaluation (contract §4/§5).

    No registry writes, no process actions. Returns (ok, detail) where a
    falsy ok carries a `reason` in: no-record, terminal-found,
    run-replaced, takeover, stale-run, lease-<kind>-<lease-reason>.
    """
    if not isinstance(record, dict):
        return False, {"reason": "no-record"}
    state = record.get("state")
    if not _is_active_state(state):
        return False, {"reason": "terminal-found", "state": state}
    try:
        if int(record.get("pid")) != int(run["pid"]) \
                or record.get("create_time") != run["create_time"]:
            return False, {"reason": "run-replaced"}
    except (TypeError, ValueError, KeyError):
        return False, {"reason": "run-replaced"}
    if state == "STOPPING":
        # Launch never writes STOPPING: any hold here is foreign.
        return False, {"reason": "takeover",
                       "stopping_by": record.get("stopping_by")}
    try:
        live = bool(identity["is_canonical"](record))
    except Exception:
        live = False
    if not live:
        return False, {"reason": "stale-run"}
    if identity.get("process_state") and _launch_process_state(
            identity, run["pid"], run["create_time"]) != "owned":
        return False, {"reason": "stale-run"}
    ages = {}
    for kind in ("supervisor", "sentinel"):
        info = (watchers or {}).get(kind) or {}
        ok, detail = _verify_watcher_lease(
            record, kind, info.get("pid"), info.get("create_time"),
            run["pid"], identity["watcher_alive"])
        if not ok:
            return False, {"reason": "lease-%s-%s" % (kind, detail["reason"]),
                           kind: detail}
        ages[kind] = detail.get("age_s")
    return True, {"reason": "verified", "supervisor_age_s": ages["supervisor"],
                  "sentinel_age_s": ages["sentinel"]}


def _default_process_state(pid: Any, expected_ctime: Any) -> str:
    """owned/gone/replaced/unknown. Identity failure is never absence proof."""
    try:
        target = int(pid)
        if target <= 0:
            return "unknown"
    except (TypeError, ValueError):
        return "unknown"
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        _configure_kernel_signatures(kernel)
        kernel.GetExitCodeProcess.argtypes = [_WIN_HANDLE, ctypes.POINTER(_WIN_DWORD)]
        kernel.GetExitCodeProcess.restype = _WIN_BOOL
        kernel.GetLastError.argtypes = []
        kernel.GetLastError.restype = _WIN_DWORD
        handle = kernel.OpenProcess(0x1000, False, target)
        if not handle:
            return "gone" if kernel.GetLastError() == 87 else "unknown"
        try:
            exit_code = _WIN_DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return "unknown"
            if exit_code.value != 259:  # STILL_ACTIVE
                return "gone"
            if not expected_ctime:
                return "unknown"
            created, exited, cpu_kernel, cpu_user = (_FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, ctypes.byref(created),
                    ctypes.byref(exited), ctypes.byref(cpu_kernel), ctypes.byref(cpu_user)):
                return "unknown"
            ticks = (int(created.dwHighDateTime) << 32) + int(created.dwLowDateTime)
            epoch_us = ticks // 10 - 11644473600000000
            if epoch_us <= 0:
                return "unknown"
            actual = datetime.fromtimestamp(epoch_us / 1_000_000, tz=timezone.utc).isoformat()
            return "owned" if actual == expected_ctime else "replaced"
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(target, 0)  # POSIX liveness query only.
    except ProcessLookupError:
        return "gone"
    except (OSError, ValueError):
        return "unknown"
    if not expected_ctime:
        return "unknown"
    actual = own_creation_time(target)
    if not actual:
        return "unknown"
    return "owned" if actual == expected_ctime else "replaced"


def _launch_process_state(identity: Dict[str, Any], pid: Any, ctime: Any) -> str:
    try:
        check = identity.get("process_state")
        if check:
            state = check(pid, ctime)
            return state if state in ("owned", "gone", "replaced", "unknown") else "unknown"
        # Old injected bundles can prove identity, but False cannot prove death.
        return "owned" if ctime and identity["watcher_alive"](pid, ctime) else "unknown"
    except Exception:
        return "unknown"


def _rollback_transaction(launched: Any, identity: Dict[str, Any]) -> Dict[str, Any]:
    """Kill-only owned rollback; retain unknown/replaced identities as pending."""
    cleaned, pending = [], []
    for role, pid, ctime in list(launched or []):
        state = _launch_process_state(identity, pid, ctime)
        if state == "gone":
            cleaned.append({"role": role, "pid": pid, "note": "already-gone"})
            continue
        if state != "owned" or not ctime:
            pending.append({"role": role, "pid": pid, "reason": "identity-" + state})
            continue
        try:
            # Native termination itself binds PID+ctime to one Windows handle.
            issued = bool(identity["terminate"](pid, ctime))
        except Exception:
            issued = False
        final = _launch_process_state(identity, pid, ctime)
        if final == "gone":
            cleaned.append({"role": role, "pid": pid, "note": "terminated"})
        else:
            pending.append({"role": role, "pid": pid,
                            "reason": "terminate-refused" if not issued else
                            ("still-alive" if final == "owned" else "identity-" + final)})
    return {"attempted": bool(launched), "cleaned": cleaned, "pending": pending}


def _launch_envelope(outcome: str, reason: str, run: Any,
                     watchers: Dict[str, Any], verification: Dict[str, Any],
                     rollback: Dict[str, Any], evidence: Any) -> Dict[str, Any]:
    return {"outcome": outcome, "reason": reason,
            "scope": _SUPERVISED_LAUNCH_SCOPE, "run": run,
            "watchers": watchers, "verification": verification,
            "rollback": rollback, "evidence": evidence}


def _watcher_slot(pid: Any, ctime: Any, confirmed: bool) -> Dict[str, Any]:
    return {"pid": pid, "create_time": ctime, "confirmed": bool(confirmed)}


def launch_supervised_transaction(duration_seconds: Optional[float] = None,
                                  launcher: str = "agent",
                                  preset: str = "standard",
                                  evidence_dir: Optional[Path] = None,
                                  verify_budget_s: float = 60.0,
                                  poll_interval_s: float = 2.0,
                                  spawners: Optional[Dict[str, Any]] = None,
                                  identity: Optional[Dict[str, Any]] = None
                                  ) -> Dict[str, Any]:
    """Supervised transactional launch (ENABLED through the verified chain).

    Contract: docs/SUPERVISED_LAUNCH_CONTRACT.md. While
    SUPERVISED_LAUNCH_ENABLED is False this refuses with
    `supervised-launch-disabled` and performs no spawn, write, or process
    action. Enablement (True) is the CONSEQUENCE of the V2 fixed-call
    path tests (V2PathTest: brief-allowlisted dashboard launch confirms
    with supervisor+sentinel bound to the run, sentinel failure rolls
    back everything, dashboard-owned stop lands) — never a bare flag
    flip. The only wired caller is the V2 BFF fixed-code path
    (readiness-green + START_OBSERVE_2100 + preset allowlist).
    """
    if not SUPERVISED_LAUNCH_ENABLED:
        return _launch_envelope(
            "rejected", "supervised-launch-disabled", None,
            {"supervisor": _watcher_slot(None, None, False),
             "sentinel": _watcher_slot(None, None, False)},
            {"polls": 0, "budget_s": verify_budget_s},
            {"attempted": False, "cleaned": [], "pending": []}, None)
    return _launch_supervised_impl(
        duration_seconds=duration_seconds, launcher=launcher, preset=preset,
        evidence_dir=evidence_dir, verify_budget_s=verify_budget_s,
        poll_interval_s=poll_interval_s, spawners=spawners, identity=identity)


def _launch_supervised_impl(duration_seconds: Optional[float] = None,
                            launcher: str = "agent",
                            preset: str = "standard",
                            evidence_dir: Optional[Path] = None,
                            verify_budget_s: float = 60.0,
                            poll_interval_s: float = 2.0,
                            spawners: Optional[Dict[str, Any]] = None,
                            identity: Optional[Dict[str, Any]] = None
                            ) -> Dict[str, Any]:
    """Disabled transaction engine; verification budget excludes blocking IO/spawn."""
    ident = _default_identity()
    if identity:
        ident.update(identity)
    sp = dict(spawners or {})
    watchers = {role: _watcher_slot(None, None, False)
                for role in ("supervisor", "sentinel")}
    launched = []
    run = None
    evidence = None

    def finish(reason, verification=None):
        rb = _rollback_transaction(list(reversed(launched)), ident) if launched else {
            "attempted": False, "cleaned": [], "pending": []}
        if launched:
            try:
                final = ident["read_record"]()
                if final is not None and not isinstance(final, dict):
                    raise ValueError("malformed final registry")
            except Exception:
                rb["pending"].append({"role": "registry", "pid": (run or {}).get("pid"),
                                      "reason": "final-registry-unreadable"})
                final = None
            # Read only: a dead process may leave its historical RUNNING record.
            # Do not reconcile or overwrite foreign/terminal evidence.
        outcome = "uncertain" if rb["pending"] else "rejected"
        info = dict(verification or {"polls": 0, "budget_s": verify_budget_s})
        if launched:
            info["final_record_state"] = final.get("state") if isinstance(final, dict) else None
        return _launch_envelope(outcome, reason, run, dict(watchers), info, rb, evidence)

    # Validate before any process, lock or evidence preparation effect.
    try:
        if isinstance(verify_budget_s, bool) or isinstance(poll_interval_s, bool):
            raise ValueError("boolean timing")
        budget, interval = float(verify_budget_s), float(poll_interval_s)
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError("budget must be finite and positive")
        if not math.isfinite(interval) or interval < 0:
            raise ValueError("interval must be finite and nonnegative")
    except (TypeError, ValueError, OverflowError):
        return finish("bad-verification-timing")
    if not isinstance(launcher, str) or not launcher.strip():
        return finish("bad-launcher")
    try:
        current = ident["read_record"]()
    except Exception:
        return finish("registry-unavailable")
    if current is not None and not isinstance(current, dict):
        return finish("registry-unavailable")
    if isinstance(current, dict) and _is_active_state(current.get("state")):
        try:
            live = bool(ident["is_canonical"](current))
        except Exception:
            # Unverifiable active identity cannot authorize a new spawn.
            return finish("preflight-identity-unknown")
        if live:
            return finish("already-running")
        if _launch_process_state(ident, current.get("pid"), current.get("create_time")) != "gone":
            return finish("preflight-identity-unknown")
    try:
        with _locked_registry():
            pass  # P2: no registry record transform/write.
    except Exception:
        return finish("registry-unavailable")
    try:
        ev_dir = Path(evidence_dir) if evidence_dir else (
            repo_root() / "logs" / ("p1-10r" if preset == "validation-6h" else "probe-runs"))
        ev_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".launch-check-", dir=str(ev_dir)):
            pass  # P4: own exclusive file, closed/removed; no registry write.
    except (OSError, TypeError, ValueError):
        return finish("evidence-unavailable")

    def capture_child(proc, ctime):
        nonlocal run
        run = {"pid": int(proc.pid), "create_time": ctime}
        launched.append(("probe", run["pid"], ctime))

    try:
        start = start_probe(duration_seconds, launcher, preset, ev_dir,
                            _on_spawn=capture_child)
    except Exception as exc:
        return finish("probe-spawn-failed", {"polls": 0, "budget_s": budget,
                                            "error": str(exc)[:120]})
    if not isinstance(start, dict) or not start.get("started"):
        detail = start if isinstance(start, dict) else {}
        reason = "probe-spawn-failed" if "spawn failed" in str(detail.get("error", "")) else "start-refused"
        return finish(reason)
    if not launched or run is None:
        # The adapter did not supply ownership: no PID-only cleanup guess.
        return _launch_envelope("uncertain", "spawn-identity-unavailable", None,
            dict(watchers), {"polls": 0, "budget_s": budget},
            {"attempted": False, "cleaned": [], "pending": [
                {"role": "probe", "pid": start.get("pid"), "reason": "spawn-identity-unavailable"}]}, None)
    if not run["create_time"]:
        return finish("run-identity-unknown")
    if start.get("pid") != run["pid"]:
        return finish("start-identity-mismatch")
    try:
        fresh = ident["read_record"]()
    except Exception:
        return finish("run-unestablished")
    if not isinstance(fresh, dict):
        return finish("run-unestablished")
    if fresh.get("pid") != run["pid"] or fresh.get("create_time") != run["create_time"]:
        return finish("run-replaced")
    if fresh.get("state") not in ("STARTING", "RUNNING") or fresh.get("stopping_by"):
        return finish("run-unestablished")
    evidence = fresh.get("evidence")

    for role in ("supervisor", "sentinel"):
        try:
            proc = (sp.get(role) or _default_watcher_spawner(role))(run["pid"])
        except Exception as exc:
            return finish(role + "-spawn-failed", {"polls": 0, "budget_s": budget,
                                                   "error": str(exc)[:120]})
        if proc is None or getattr(proc, "pid", None) is None:
            return finish(role + "-spawn-failed")
        try:
            ctime = ident["proc_ctime"](proc.pid)
        except Exception:
            ctime = None
        watchers[role] = _watcher_slot(proc.pid, ctime, False)
        launched.append((role, proc.pid, ctime))
        if not ctime:
            return finish(role + "-identity-unknown")

    polls = 0
    good_polls = 0
    last_detail = {"reason": "no-poll"}
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        polls += 1
        try:
            rec = ident["read_record"]()
        except Exception:
            rec = None
        if time.monotonic() >= deadline:
            last_detail = {"reason": "verify-timeout"}
            break
        if not isinstance(rec, dict):
            last_detail = {"reason": "poll-unreadable"}
        else:
            good_polls += 1
            ok, last_detail = _verify_launch_state(rec, run, watchers, ident)
            if time.monotonic() >= deadline:
                last_detail = {"reason": "verify-timeout"}
                break
            if ok:
                for role in watchers:
                    watchers[role]["confirmed"] = True
                return _launch_envelope("confirmed", "all-components-verified", run,
                    dict(watchers), {"polls": polls, "budget_s": budget,
                    "supervisor_age_s": last_detail.get("supervisor_age_s"),
                    "sentinel_age_s": last_detail.get("sentinel_age_s")},
                    {"attempted": False, "cleaned": [], "pending": []}, evidence)
            if last_detail.get("reason") not in (
                    "lease-supervisor-lease-absent", "lease-sentinel-lease-absent",
                    "no-record", "poll-unreadable"):
                break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if interval > 0:
            time.sleep(min(interval, remaining))
    reason = last_detail.get("reason")
    if good_polls == 0 and reason != "verify-timeout":
        reason = "verify-unreadable"
    elif reason in ("no-poll", "no-record", "poll-unreadable",
                    "lease-supervisor-lease-absent", "lease-sentinel-lease-absent"):
        reason = "verify-timeout"
    return finish(reason, {"polls": polls, "budget_s": budget, "detail": last_detail})


if __name__ == "__main__":
    raise SystemExit(main())
