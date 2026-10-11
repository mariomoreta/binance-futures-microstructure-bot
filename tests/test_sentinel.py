"""P1-14B.8 sentinel: supervision-liveness watchdog with enforced safe-stop.

The supervisor (P1-14B.7) watches the run; the sentinel watches the
SUPERVISION ITSELF. If an established supervision goes stale (or reports
FAILED) while its run is still active, the sentinel enforces a safe stop
through the canonical verified-PID path and persists the reason. It never
starts runs, never touches foreign processes, never acts on missing
supervision (continuity guard only — existence belongs to the launcher).

Isolated registries (MICROPROBE_RUNTIME_FILE) except the marked
integration test, which kills a REAL sleeper child while a foreign
sleeper must survive. Run: python run_tests.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="sentrun_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    path = tmp / "probe_runtime.json"
    os.environ["MICROPROBE_RUNTIME_FILE"] = str(path)
    testcase.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
    return path


def _rmtree(path: Path) -> None:
    try:
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
    except OSError:
        pass


def _old_iso(seconds_ago):
    return (datetime.now(timezone.utc).timestamp() - seconds_ago)


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _run_record(pid=424243, state="RUNNING", launcher="agent"):
    return {"schema": 1, "writer": "control/1", "state": state,
            "pid": pid, "create_time": "STAMP",
            "started_at": "2026-10-10T10:00:00+00:00", "mode": "observe",
            "command": [sys.executable, "-m", "microstructure_probe"],
            "duration_seconds": 2100, "expected_end_at": None,
            "launcher": launcher, "preset": "standard",
            "evidence": {"dir": "ev", "log": "run.log"},
            "last_exit": None}


def _lease(pid=424244, age_s=10.0, state="ACTIVE"):
    return {"pid": pid, "create_time": "C",
            "started_at": _iso(time.time() - 120.0),
            "last_check_at": _iso(time.time() - age_s),
            "state": state, "consecutive_failures": 0,
            "prev_supervisor_pid": None, "watched_pid": 424243,
            "streaks": {"persistence": 0, "clock": 0, "db": 0},
            "abort": None}


def _write(record):
    pc._write_registry(record)


# ------------------------------------------------------------------
# Claim / lease
# ------------------------------------------------------------------

class SentinelClaimTest(unittest.TestCase):
    def test_first_claim_wins(self):
        _temp_registry(self)
        _write(_run_record())
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            first = pc.claim_sentinel()
        self.assertTrue(first["watching"])
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            second = pc.claim_sentinel()
        self.assertFalse(second["watching"])
        self.assertEqual(second["reason"], "already-watched")

    def test_stale_lease_takeover(self):
        _temp_registry(self)
        rec = _run_record()
        rec["sentinel"] = _lease(pid=111111, age_s=9999.0)
        _write(rec)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                             return_value=False):
                take = pc.claim_sentinel()
        self.assertTrue(take["watching"])
        self.assertEqual(take["prev_sentinel_pid"], 111111)

    def test_no_active_run_refuses(self):
        _temp_registry(self)
        _write(_run_record(state="COMPLETED"))
        out = pc.claim_sentinel()
        self.assertFalse(out["watching"])
        self.assertEqual(out["reason"], "no-active-run")

    def test_stale_run_record_refuses(self):
        _temp_registry(self)
        _write(_run_record())
        with mock.patch.object(pc, "is_canonical_pid", return_value=False):
            out = pc.claim_sentinel()
        self.assertFalse(out["watching"])
        self.assertEqual(out["reason"], "stale-record")


# ------------------------------------------------------------------
# Cycle semantics
# ------------------------------------------------------------------

class SentinelCycleTest(unittest.TestCase):
    def _live_lease(self, age_s=10.0, state="ACTIVE"):
        # The sentinel watches the SUPERVISOR lease (record["supervisor"]).
        _temp_registry(self)
        rec = _run_record()
        rec["supervisor"] = _lease(age_s=age_s, state=state)
        _write(rec)

    def test_fresh_lease_no_action(self):
        self._live_lease(age_s=10.0)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                             return_value=True):
                with mock.patch.object(pc, "enforce_abort") as enf:
                    out = pc.sentinel_once(stale_after_s=120.0)
        enf.assert_not_called()
        self.assertEqual(out["outcome"], "ok-supervised")

    def test_stale_lease_aborts(self):
        self._live_lease(age_s=9999.0)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "enforce_abort",
                                   return_value={"aborted": True}) as enf:
                out = pc.sentinel_once(stale_after_s=120.0)
        enf.assert_called_once()
        decision = enf.call_args[0][0]
        self.assertEqual(decision["rule"], "supervision-lost")
        self.assertEqual(out["outcome"], "aborted-supervision-lost")

    def test_failed_lease_aborts(self):
        self._live_lease(age_s=5.0, state="FAILED")
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "enforce_abort",
                                   return_value={"aborted": True}) as enf:
                out = pc.sentinel_once(stale_after_s=120.0)
        enf.assert_called_once()
        self.assertEqual(out["outcome"], "aborted-supervision-lost")

    def test_missing_lease_no_action(self):
        _temp_registry(self)
        _write(_run_record())
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "enforce_abort") as enf:
                out = pc.sentinel_once(stale_after_s=120.0)
        enf.assert_not_called()
        self.assertEqual(out["outcome"], "unsupervised")

    def test_terminal_noop(self):
        _temp_registry(self)
        _write(_run_record(state="ABORTED"))
        with mock.patch.object(pc, "enforce_abort") as enf:
            out = pc.sentinel_once(stale_after_s=120.0)
        enf.assert_not_called()
        self.assertEqual(out["outcome"], "already-terminal")

    def test_stale_record_no_touch(self):
        self._live_lease(age_s=9999.0)
        with mock.patch.object(pc, "is_canonical_pid", return_value=False):
            with mock.patch.object(pc, "enforce_abort") as enf:
                out = pc.sentinel_once(stale_after_s=120.0)
        enf.assert_not_called()
        self.assertEqual(out["outcome"], "stale-record")

    def test_failure_budget_marks_failed(self):
        _temp_registry(self)
        _write(_run_record())
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            pc.claim_sentinel()
        with mock.patch.object(pc, "is_canonical_pid",
                               side_effect=RuntimeError("boom")):
            out = None
            for _ in range(7):
                out = pc.sentinel_once(stale_after_s=120.0)
        self.assertEqual(out["outcome"], "sentinel-failed")
        rec = pc.read_registry()
        self.assertEqual((rec.get("sentinel") or {}).get("state"), "FAILED")

    def test_no_start_path_in_sentinel(self):
        import inspect
        for name in ("sentinel", "sentinel_once", "claim_sentinel"):
            src = inspect.getsource(getattr(pc, name))
            self.assertNotIn("start_probe", src)


# ------------------------------------------------------------------
# Status contract
# ------------------------------------------------------------------

class SentinelStatusTest(unittest.TestCase):
    def test_unknown_shape(self):
        _temp_registry(self)
        out = pc.status()
        sup = out["sentinel"]
        for key in ("state", "watched_pid", "run_id", "last_check_at",
                    "action_taken", "action_reason", "supervision_source"):
            self.assertIn(key, sup)
        self.assertEqual(sup["state"], "SENTINEL_UNKNOWN")

    def test_active_shape(self):
        _temp_registry(self)
        rec = _run_record()
        rec["sentinel"] = _lease(age_s=10.0)
        _write(rec)
        with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                         return_value=True):
            sup = pc.status()["sentinel"]
        self.assertEqual(sup["state"], "SENTINEL_ACTIVE")
        self.assertEqual(sup["watched_pid"], 424243)


# ------------------------------------------------------------------
# REAL integration (controlled destructive test)
# ------------------------------------------------------------------

class SentinelAbortIntegrationTest(unittest.TestCase):
    def test_stale_supervision_kills_only_watched(self):
        _temp_registry(self)
        victim = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"])
        foreign = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"])
        self.addCleanup(_kill, victim)
        self.addCleanup(_kill, foreign)
        try:
            ctime = pc.own_creation_time(victim.pid)
            self.assertIsNotNone(ctime)
            rec = _run_record(pid=victim.pid)
            rec["create_time"] = ctime
            # Dead SUPERVISOR lease (the watched condition) + stale sentinel
            # lease (takeover path): the run must be stopped.
            rec["supervisor"] = _lease(pid=999997, age_s=9999.0)
            rec["supervisor"]["watched_pid"] = victim.pid
            rec["sentinel"] = _lease(pid=999998, age_s=9999.0)
            rec["sentinel"]["watched_pid"] = victim.pid
            _write(rec)
            out = pc.sentinel(interval_s=5.0, timeout_s=60.0,
                              stale_after_s=1.0)
            self.assertTrue(out.get("aborted"))
            self.assertIsNotNone(victim.poll())
            self.assertIsNone(foreign.poll())
            final = pc.read_registry()
            self.assertEqual(final.get("state"), "ABORTED")
            self.assertEqual(final.get("abort_rule"), "supervision-lost")
            self.assertEqual(final.get("aborted_by"), "sentinel")
            self.assertEqual(final.get("launcher"), "agent")
            again = pc.sentinel_once(stale_after_s=1.0)
            self.assertEqual(again["outcome"], "already-terminal")
            self.assertIsNone(foreign.poll())
        finally:
            _kill(victim)
            _kill(foreign)


def _kill(proc):
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass
