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
                                 "last_exit_reason": None,
                                 "supervisor": _supervisor_block(None),
                                 "sentinel": _sentinel_block(None)}
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
        # P1-14B.7 additive supervisor contract (always present; UNKNOWN
        # when never supervised). Flows to /api/control/probe/status.
        "supervisor": _supervisor_block(record),
        # P1-14B.8 additive sentinel contract (always present; UNKNOWN
        # when never watched). Same API flow, same None-safe rules.
        "sentinel": _sentinel_block(record),
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
    # P1-14B.7: a control-started child self-registers over its own STARTING
    # record — carry the evidence path forward so supervision keeps its
    # log-derived rules (UNKNOWN-safe skip otherwise). Never invent evidence:
    # only preserve what the same PID already recorded.
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
        from .dashboard import repo_root
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
        from .dashboard import pid_is_ours
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
    lease = record.get("supervisor")
    if isinstance(lease, dict) and str(lease.get("state", "")).upper() == "ACTIVE" \
            and _lease_live(lease):
        return {"supervised": False, "reason": "already-supervised",
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
    try:
        _write_registry(record)
    except OSError as exc:
        return {"supervised": False, "reason": "registry-unavailable: %s" % exc}
    return {"supervised": True, "pid": os.getpid(),
            "watched_pid": record.get("pid"),
            "prev_supervisor_pid": prev}


def _heartbeat_lease(consecutive_failures: int = 0,
                     streaks: Optional[Dict[str, int]] = None) -> None:
    try:
        record = read_registry()
        if not record or not isinstance(record.get("supervisor"), dict):
            return
        record["supervisor"]["last_check_at"] = _utc_now_iso()
        record["supervisor"]["consecutive_failures"] = consecutive_failures
        if streaks is not None:
            record["supervisor"]["streaks"] = dict(streaks)
        _write_registry(record)
    except OSError:
        pass


def _fail_lease() -> None:
    try:
        record = read_registry()
        if not record or not isinstance(record.get("supervisor"), dict):
            return
        record["supervisor"]["state"] = "FAILED"
        record["supervisor"]["last_check_at"] = _utc_now_iso()
        _write_registry(record)
    except OSError:
        pass


def enforce_abort(decision: Dict[str, Any]) -> Dict[str, Any]:
    """Execute one verified abort: re-validate identity, stop via the
    canonical path, mark ABORTED with reason. Never touches foreign PIDs,
    never claims ABORTED unless the watched process is confirmed dead."""
    record = read_registry()
    if not record or not _is_active_state(record.get("state")):
        return {"aborted": False, "reason": "no-active-run"}
    pid = record.get("pid")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return {"aborted": False, "reason": "bad-record-pid"}
    if not is_canonical_pid(record):
        return {"aborted": False, "reason": "stale-record-not-touched"}
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
            record["last_exit"] = {
                "code": None,
                "reason": "abort stop-timeout (process survived bounded wait)",
                "at": _utc_now_iso()}
            _write_registry(record)
        except OSError:
            pass
        return {"aborted": False, "reason": "stop-timeout", "pid": pid}
    try:
        record["state"] = ABORTED
        record["aborted_by"] = "supervisor"
        record["abort_rule"] = decision.get("rule")
        record["abort_reason"] = decision.get("reason")
        record["abort_threshold"] = decision.get("threshold")
        record["abort_observed"] = decision.get("observed")
        record["abort_at"] = _utc_now_iso()
        record["last_exit"] = {"code": 0,
                               "reason": "aborted-%s" % decision.get("rule"),
                               "at": _utc_now_iso()}
        _write_registry(record)
    except OSError:
        pass
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
    result = enforce_abort(decision)
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
        try:
            record = read_registry()
            if record and isinstance(record.get("supervisor"), dict):
                if outcome.get("outcome") not in ("aborted",):
                    record["supervisor"]["state"] = (
                        "FAILED" if outcome.get("outcome") == "supervisor-failed"
                        else "STOPPED")
                    record["supervisor"]["last_check_at"] = _utc_now_iso()
                    _write_registry(record)
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

    Maps: ACTIVE->SUPERVISOR_ACTIVE, FAILED->SUPERVISOR_FAILED,
    missing/stale lease->SUPERVISOR_UNKNOWN; terminal ABORTED state ->
    ABORT_TRIGGERED with rule/reason/threshold/observed.
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
    }
    if not isinstance(record, dict):
        return block
    lease = record.get("supervisor")
    if isinstance(lease, dict):
        state = str(lease.get("state", "")).upper()
        if state == "ACTIVE":
            block["state"] = "SUPERVISOR_ACTIVE"
        elif state == "FAILED":
            block["state"] = "SUPERVISOR_FAILED"
        block["watched_pid"] = lease.get("watched_pid")
        block["last_check_at"] = lease.get("last_check_at")
        block["supervision_source"] = "supervisor:control-supervise"
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
    lease = record.get("sentinel")
    if isinstance(lease, dict) and str(lease.get("state", "")).upper() == "ACTIVE" \
            and _lease_live(lease):
        return {"watching": False, "reason": "already-watched",
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
    try:
        _write_registry(record)
    except OSError as exc:
        return {"watching": False,
                "reason": "registry-unavailable: %s" % exc}
    return {"watching": True, "pid": os.getpid(),
            "watched_pid": record.get("pid"),
            "prev_sentinel_pid": prev}


def _heartbeat_sentinel(failures: int = 0, action: Optional[Dict[str, Any]] = None) -> None:
    try:
        record = read_registry()
        if not record or not isinstance(record.get("sentinel"), dict):
            return
        record["sentinel"]["last_check_at"] = _utc_now_iso()
        record["sentinel"]["consecutive_failures"] = failures
        if action is not None:
            record["sentinel"]["action"] = action
        _write_registry(record)
    except Exception:
        pass


def _fail_sentinel() -> None:
    try:
        record = read_registry()
        if not record or not isinstance(record.get("sentinel"), dict):
            return
        record["sentinel"]["state"] = "FAILED"
        record["sentinel"]["last_check_at"] = _utc_now_iso()
        _write_registry(record)
    except Exception:
        pass


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
                         stale_after_s: float) -> str:
    """Fresh supervision state: ok-supervised | stale-supervision |
    failed-supervision | unsupervised (no lease ever)."""
    lease = record.get("supervisor")
    if not isinstance(lease, dict):
        return "unsupervised"
    state = str(lease.get("state", "")).upper()
    if state == "FAILED":
        return "failed-supervision"
    age = _supervision_age_s(lease)
    if age is None:
        return "unsupervised"
    if age <= stale_after_s:
        return "ok-supervised"
    return "stale-supervision"


def sentinel_once(stale_after_s: float = SENTINEL_STALE_AFTER_S) -> Dict[str, Any]:
    """One sentinel cycle (public): evaluate, then heartbeat the lease.

    Heartbeats advance on EVERY cycle outcome (including ok/unsupervised/
    terminal reads) so a live sentinel never looks stale; failures to
    persist the heartbeat never mask the cycle outcome.
    """
    outcome = _sentinel_cycle(stale_after_s)
    try:
        record = read_registry()
        if record and isinstance(record.get("sentinel"), dict):
            record["sentinel"]["last_check_at"] = _utc_now_iso()
            if outcome.get("outcome") == "aborted-supervision-lost":
                decision = outcome.get("decision") or {}
                record["sentinel"]["action"] = {
                    "rule": decision.get("rule", "supervision-lost"),
                    "at": _utc_now_iso(),
                    "aborted": True,
                }
            _write_registry(record)
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
        verdict = _supervision_verdict(record, float(stale_after_s))
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
        result = enforce_abort(decision)
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
        try:
            record = read_registry()
            if record and isinstance(record.get("sentinel"), dict):
                if outcome.get("outcome") not in ("aborted-supervision-lost",):
                    record["sentinel"]["state"] = (
                        "FAILED" if outcome.get("outcome") == "sentinel-failed"
                        else "STOPPED")
                    record["sentinel"]["last_check_at"] = _utc_now_iso()
                    _write_registry(record)
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

    Maps: ACTIVE->SENTINEL_ACTIVE, FAILED->SENTINEL_FAILED,
    missing/stale lease->SENTINEL_UNKNOWN. The last enforced action
    (if any) rides along for audit.
    """
    block: Dict[str, Any] = {
        "state": "SENTINEL_UNKNOWN",
        "watched_pid": None,
        "run_id": None,
        "last_check_at": None,
        "action_taken": None,
        "action_reason": None,
        "supervision_source": None,
    }
    if not isinstance(record, dict):
        return block
    lease = record.get("sentinel")
    if isinstance(lease, dict):
        state = str(lease.get("state", "")).upper()
        if state == "ACTIVE":
            block["state"] = "SENTINEL_ACTIVE"
        elif state == "FAILED":
            block["state"] = "SENTINEL_FAILED"
        block["watched_pid"] = lease.get("watched_pid")
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
    return block


if __name__ == "__main__":
    raise SystemExit(main())
