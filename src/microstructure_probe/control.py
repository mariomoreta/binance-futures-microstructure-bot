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
import ctypes
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

REGISTRY_NAME = "probe_runtime.json"
REGISTRY_SCHEMA = 1

MIN_DURATION_SECONDS = 60
MAX_DURATION_SECONDS = 86400
SIX_HOURS = 21600

STATES = ("STOPPED", "STARTING", "RUNNING", "STOPPING",
          "COMPLETED", "FAILED")

_LOG_HANDLES: Dict[int, Any] = {}


def registry_path() -> Path:
    """Registry file, overridable for hermetic tests."""
    override = os.environ.get("MICROPROBE_RUNTIME_FILE")
    if override:
        return Path(override)
    from .dashboard import repo_root
    return repo_root() / "logs" / REGISTRY_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_registry() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_registry(record: Dict[str, Any]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1), encoding="utf-8")


def own_creation_time(pid: Optional[int] = None) -> Optional[str]:
    """Recorded creation-time string for pid (None when indeterminable)."""
    from .dashboard import process_info
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
    from .dashboard import pid_is_ours
    try:
        return bool(pid_is_ours(int(record["pid"]),
                                record.get("create_time")))
    except (TypeError, ValueError):
        return False


def _is_active_state(state: Optional[str]) -> bool:
    return state in ("STARTING", "RUNNING", "STOPPING")


def _feed_unknown() -> Dict[str, Any]:
    return {"feed_health": "UNKNOWN", "latest_snapshot_age": None}


def status(feed_provider: Optional[Callable[[], Dict[str, Any]]] = None
           ) -> Dict[str, Any]:
    """Machine-readable probe status; stale/dead PIDs detected safely.

    A record stuck in an active state whose PID is dead is transitioned to
    FAILED (terminated-externally) and persisted, so the UI is stable.
    """
    record = read_registry()
    feed = feed_provider() if feed_provider else _feed_unknown()
    if not record:
        out: Dict[str, Any] = {"running": False, "state": "STOPPED",
                                "pid": None, "started_at": None,
                                "uptime_seconds": 0.0, "mode": "observe",
                                "duration_seconds": None,
                                "elapsed_seconds": 0.0,
                                "remaining_seconds": None,
                                "expected_end_at": None, "launcher": None,
                                "preset": "standard",
                                "last_exit_code": None,
                                "last_exit_reason": None}
        out.update(feed)
        return out
    state = record.get("state", "STOPPED")
    if _is_active_state(state) and not is_canonical_pid(record):
        record["state"] = "FAILED"
        record["last_exit"] = {
            "code": None,
            "reason": "terminated-externally (no exit record)",
            "at": _utc_now_iso(),
        }
        try:
            _write_registry(record)
        except OSError:
            pass
        _close_log_handles(int(record["pid"]) if record.get("pid") else -1)
        state = "FAILED"
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
    duration = record.get("duration_seconds")
    remaining = (max(0.0, duration - elapsed)
                 if isinstance(duration, (int, float)) and state == "RUNNING"
                 else None)
    last_exit = record.get("last_exit") or {}
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
        "last_exit_code": last_exit.get("code"),
        "last_exit_reason": last_exit.get("reason"),
    }
    out.update(feed)
    return out


def try_register(duration_seconds: Optional[float] = None,
                 launcher: Optional[str] = None) -> Dict[str, Any]:
    """Probe-side self-registration (called by EVERY canonical launch).

    Refuses (registered=False) when a DIFFERENT live probe already holds
    the registry — the caller must exit without touching it. Registry
    write failures never break the probe: warn and run unregistered.
    """
    current = read_registry()
    if current and _is_active_state(current.get("state")) \
            and is_canonical_pid(current) \
            and int(current.get("pid") or -1) != os.getpid():
        return {"registered": False,
                "already_running": status(),
                "reason": "another canonical probe is already running"}
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
        "evidence": None,
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
    try:
        _write_registry(record)
    except OSError as exc:
        return {"registered": True, "degraded": f"registry-unavailable: {exc}",
                "record": record}
    return {"registered": True, "record": record}


def mark_completed(exit_code: int = 0) -> None:
    _mark_terminal("COMPLETED", exit_code, "duration-reached")


def mark_stopped(reason: str, exit_code: int = 0) -> None:
    _mark_terminal("STOPPED", exit_code, reason)


def mark_failed(reason: str, exit_code: Optional[int] = 1) -> None:
    _mark_terminal("FAILED", exit_code, reason)


def _mark_terminal(state: str, exit_code: Optional[int],
                   reason: str) -> None:
    try:
        record = read_registry()
        if not record or int(record.get("pid") or -1) != os.getpid():
            return
        record["state"] = state
        record["last_exit"] = {"code": exit_code, "reason": reason,
                               "at": _utc_now_iso()}
        _write_registry(record)
    except (OSError, TypeError, ValueError):
        pass
    finally:
        _close_log_handles(os.getpid())


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
    from .dashboard import repo_root
    env = dict(os.environ)
    env["BOT_MODE"] = "observe"  # forced: observe-only, always
    env["MICROPROBE_LAUNCHER"] = launcher
    src = str(repo_root() / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    return env


def start_probe(duration_seconds: Optional[int] = None,
                launcher: str = "agent",
                preset: str = "standard",
                evidence_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Start one canonical probe; refuse when one is already running."""
    live = status()
    if live["running"] or (live["state"] in ("STARTING", "STOPPING")
                           and is_canonical_pid(read_registry())):
        return {"started": False, "already_running": True,
                "pid": live["pid"], "uptime_seconds": live["uptime_seconds"],
                "mode": live.get("mode", "observe"), "state": live["state"]}
    from .dashboard import repo_root
    duration = validate_duration(duration_seconds)
    if preset == "validation-6h":
        duration = SIX_HOURS
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
        from .dashboard import no_window_flags
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
    _write_registry({
        "schema": REGISTRY_SCHEMA,
        "writer": "control/1",
        "state": "STARTING",
        "pid": proc.pid,
        "create_time": own_creation_time(proc.pid),
        "started_at": _utc_now_iso(),
        "mode": "observe",
        "command": argv,
        "duration_seconds": duration,
        "expected_end_at": None,
        "launcher": launcher,
        "preset": preset if preset == "validation-6h" else "standard",
        "evidence": evidence,
        "last_exit": None,
    })
    # The child self-registers RUNNING on entry (self-registration flips
    # STARTING → RUNNING within seconds, incl. externally launched probes
    # that never pass through here).
    return {"started": True, "pid": proc.pid, "mode": "observe",
            "duration_seconds": duration,
            "preset": preset if preset == "validation-6h" else "standard",
            "evidence": evidence}


def stop_probe(requester: str = "agent") -> Dict[str, Any]:
    """Terminate ONLY the verified canonical probe PID (bounded wait)."""
    record = read_registry()
    if not record or not _is_active_state(record.get("state")):
        return {"stopped": False, "error": "no-active-probe",
                "state": (record or {}).get("state", "STOPPED")}
    pid = int(record["pid"])
    if not is_canonical_pid(record):
        try:
            record["state"] = "FAILED"
            record["last_exit"] = {
                "code": None,
                "reason": "stale-record-recovered-on-stop (pid dead/mismatched)",
                "at": _utc_now_iso()}
            _write_registry(record)
        except OSError:
            pass
        return {"stopped": False, "error": "stale-probe-record-recovered",
                "state": "FAILED"}
    try:
        record["state"] = "STOPPING"
        _write_registry(record)
    except OSError:
        pass
    _terminate_verified_pid(pid)
    deadline = time.monotonic() + 10.0
    from .dashboard import pid_is_ours
    while time.monotonic() < deadline:
        if not pid_is_ours(pid, record.get("create_time")):
            break
        time.sleep(0.2)
    if pid_is_ours(pid, record.get("create_time")):
        try:
            record["state"] = "FAILED"
            record["last_exit"] = {"code": None, "reason": "stop-timeout"
                                   " (process survived bounded wait)",
                                   "at": _utc_now_iso()}
            _write_registry(record)
        except OSError:
            pass
        return {"stopped": False, "error": "stop-timeout", "pid": pid}
    try:
        record["state"] = "STOPPED"
        record["last_exit"] = {"code": 0,
                               "reason": f"stopped-by-{requester}",
                               "at": _utc_now_iso()}
        _write_registry(record)
    except OSError:
        pass
    _close_log_handles(pid)
    return {"stopped": True, "pid": pid}


def _terminate_verified_pid(pid: int) -> None:
    """SIGTERM on POSIX; TerminateProcess on Windows (no graceful stdlib
    path exists there for detached children — documented, identity already
    revalidated by the caller immediately before this call)."""
    if os.name == "nt":
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(1, False, pid)  # PROCESS_TERMINATE
        if not handle:
            return
        try:
            kernel32.TerminateProcess(handle, 0)
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass


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
                       choices=["standard", "validation-6h"],
                       help="validation-6h forces 21600s + evidence wrapper")
    sub.add_parser("stop", help="stop the verified canonical probe")
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
