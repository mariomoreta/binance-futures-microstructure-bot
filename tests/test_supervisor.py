"""P1-14B.7 persistent supervision & enforced abort gates.

A supervisor independent of any agent session watches ONE authorized run
via the canonical registry, evaluates the documented abort rules every
cycle, and enforces a one-shot verified-PID stop with persisted reason.
It never starts or restarts runs, never touches foreign processes, and
never acts on UNKNOWN (explicit safe policy per rule).

Isolated registries (MICROPROBE_RUNTIME_FILE) everywhere except the
marked integration test, which aborts a REAL sleeper child process
(verified PID + creation time) while a second unrelated sleeper must
survive. No operational SQLite touched. Run: python run_tests.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="suprun_"))
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


def _run_record(pid=424242, state="RUNNING", launcher="agent"):
    return {"schema": 1, "writer": "control/1", "state": state,
            "pid": pid, "create_time": "STAMP",
            "started_at": "2026-10-10T10:00:00+00:00", "mode": "observe",
            "command": [sys.executable, "-m", "microstructure_probe"],
            "duration_seconds": 2100, "expected_end_at": None,
            "launcher": launcher, "preset": "standard",
            "evidence": {"dir": "ev", "log": "run.log"},
            "last_exit": None}


def _write(record):
    pc._write_registry(record)


def _snap(**over):
    snap = {"now_s": 1_800_000_000.0, "mode": "observe",
            "safety": {"apiKeysUsed": 0, "realOrdersSent": 0,
                       "orderExecutionPathPresent": False},
            "reject_rate": 0.0, "total_messages": 100000,
            "reconnect_events": [], "persistence_errors_10m": 0,
            "persistence_streak": 0, "clock_offset_ms": 100.0,
            "clock_streak": 0, "db_readable": True, "db_fail_streak": 0,
            "forced_reconnects": 0, "error_reconnects": 0,
            "reject_rate_prev": 0.0}
    snap.update(over)
    return snap


# ------------------------------------------------------------------
# Pure decision core
# ------------------------------------------------------------------

class EvaluateTest(unittest.TestCase):
    def test_reject_rate_breach(self):
        d = pc.evaluate_supervision(_snap(reject_rate=0.051))
        self.assertIsNotNone(d)
        self.assertEqual(d["rule"], "timestamp-reject-rate")
        self.assertEqual(d["threshold"], 0.05)
        self.assertEqual(d["observed"], 0.051)

    def test_reject_rate_boundary(self):
        self.assertIsNone(pc.evaluate_supervision(_snap(reject_rate=0.05)))
        self.assertIsNotNone(pc.evaluate_supervision(_snap(reject_rate=0.0501)))

    def test_reject_unknown_skips(self):
        self.assertIsNone(pc.evaluate_supervision(_snap(reject_rate=None)))

    def test_reconnect_storm_windowed(self):
        now = 1_800_000_000.0
        events = [(now - 60.0 * i, "market") for i in range(6)]
        d = pc.evaluate_supervision(_snap(reconnect_events=events, now_s=now))
        self.assertIsNotNone(d)
        self.assertEqual(d["rule"], "reconnect-storm")

    def test_reconnect_five_is_not_breach(self):
        now = 1_800_000_000.0
        events = [(now - 60.0 * i, "market") for i in range(5)]
        self.assertIsNone(pc.evaluate_supervision(_snap(reconnect_events=events, now_s=now)))

    def test_reconnect_old_events_excluded(self):
        now = 1_800_000_000.0
        events = [(now - 3600.0 - 60.0 * i, "market") for i in range(9)]
        self.assertIsNone(pc.evaluate_supervision(_snap(reconnect_events=events, now_s=now)))

    def test_persistence_streak(self):
        self.assertIsNone(pc.evaluate_supervision(_snap(persistence_errors_10m=3, persistence_streak=0)))
        d = pc.evaluate_supervision(_snap(persistence_errors_10m=3, persistence_streak=1))
        self.assertIsNotNone(d)
        self.assertEqual(d["rule"], "persistence-errors")

    def test_clock_streak(self):
        self.assertIsNone(pc.evaluate_supervision(_snap(clock_offset_ms=45000.0, clock_streak=1)))
        d = pc.evaluate_supervision(_snap(clock_offset_ms=45000.0, clock_streak=2))
        self.assertIsNotNone(d)
        self.assertEqual(d["rule"], "clock-skew")
        self.assertIsNone(pc.evaluate_supervision(_snap(clock_offset_ms=None, clock_streak=9)))

    def test_db_unreadable_streak(self):
        self.assertIsNone(pc.evaluate_supervision(_snap(db_readable=False, db_fail_streak=4)))
        d = pc.evaluate_supervision(_snap(db_readable=False, db_fail_streak=5))
        self.assertIsNotNone(d)
        self.assertEqual(d["rule"], "db-unreadable")

    def test_watchdog_overwhelmed_compound(self):
        d = pc.evaluate_supervision(_snap(
            forced_reconnects=3, error_reconnects=3,
            reject_rate=0.04, reject_rate_prev=0.03))
        self.assertIsNotNone(d)
        self.assertEqual(d["rule"], "watchdog-overwhelmed")

    def test_watchdog_compound_needs_rising(self):
        self.assertIsNone(pc.evaluate_supervision(_snap(
            forced_reconnects=5, error_reconnects=5,
            reject_rate=0.04, reject_rate_prev=0.06)))

    def test_safety_wins_over_all(self):
        d = pc.evaluate_supervision(_snap(
            safety={"apiKeysUsed": 1, "realOrdersSent": 0,
                    "orderExecutionPathPresent": False},
            reject_rate=0.99))
        self.assertIsNotNone(d)
        self.assertEqual(d["rule"], "safety-violation")

    def test_mode_violation(self):
        d = pc.evaluate_supervision(_snap(mode="live"))
        self.assertIsNotNone(d)
        self.assertEqual(d["rule"], "safety-violation")

    def test_all_unknown_is_none(self):
        self.assertIsNone(pc.evaluate_supervision(_snap(
            reject_rate=None, reconnect_events=None, persistence_errors_10m=None,
            clock_offset_ms=None, db_readable=None, safety=None, mode=None,
            forced_reconnects=None, error_reconnects=None, reject_rate_prev=None)))


# ------------------------------------------------------------------
# Lease: single supervisor, takeover, restart
# ------------------------------------------------------------------

class LeaseTest(unittest.TestCase):
    def test_first_claim_wins(self):
        _temp_registry(self)
        _write(_run_record())
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            first = pc.claim_supervision()
        self.assertTrue(first["supervised"])
        # Second claim sees our own live lease (real PID identity) -> refuse.
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            second = pc.claim_supervision()
        self.assertFalse(second["supervised"])
        self.assertEqual(second["reason"], "already-supervised")

    def test_stale_lease_takeover(self):
        _temp_registry(self)
        _write(_run_record())
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            pc.claim_supervision()
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch("microstructure_probe.control.pid_is_ours",
                             return_value=False):
                take = pc.claim_supervision()
        self.assertTrue(take["supervised"])
        self.assertIn("prev_supervisor_pid", take)

    def test_corrupt_lease_treated_as_absent(self):
        _temp_registry(self)
        rec = _run_record()
        rec["supervisor"] = {"garbage": True}
        _write(rec)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            out = pc.claim_supervision()
        self.assertTrue(out["supervised"])

    def test_self_registration_preserves_evidence(self):
        _temp_registry(self)
        mine = {"schema": 1, "writer": "control/1", "state": "STARTING",
                "pid": os.getpid(), "create_time": "C",
                "started_at": "2026-10-10T10:00:00+00:00", "mode": "observe",
                "command": [], "duration_seconds": 150,
                "expected_end_at": None, "launcher": "agent",
                "preset": "standard",
                "evidence": {"dir": "ev", "log": "run.log"},
                "last_exit": None}
        _write(mine)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            out = pc.try_register(150, launcher="agent")
        self.assertTrue(out["registered"])
        self.assertEqual(pc.read_registry().get("evidence"),
                         {"dir": "ev", "log": "run.log"})

    def test_direct_launch_without_record_has_no_evidence(self):
        _temp_registry(self)
        with mock.patch.object(pc, "is_canonical_pid", return_value=False):
            out = pc.try_register(150, launcher="direct")
        self.assertTrue(out["registered"])
        self.assertIsNone(pc.read_registry().get("evidence"))

    def test_no_active_run_refuses(self):
        _temp_registry(self)
        _write(_run_record(state="COMPLETED"))
        out = pc.claim_supervision()
        self.assertFalse(out["supervised"])
        self.assertEqual(out["reason"], "no-active-run")


# ------------------------------------------------------------------
# Cycle semantics: identity, one-shot, no-restart, failures
# ------------------------------------------------------------------

class CycleTest(unittest.TestCase):
    def _claimed(self, record):
        _temp_registry(self)
        _write(record)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            pc.claim_supervision()

    def test_stale_pid_no_touch(self):
        self._claimed(_run_record(pid=424242))
        with mock.patch.object(pc, "is_canonical_pid", return_value=False):
            with mock.patch.object(pc, "_terminate_verified_pid") as term:
                out = pc.supervise_once()
        term.assert_not_called()
        self.assertEqual(out["outcome"], "stale-record")
        rec = pc.read_registry()
        self.assertNotEqual(rec.get("state"), "ABORTED")

    def test_pid_reuse_no_touch(self):
        self._claimed(_run_record(pid=424242))
        with mock.patch.object(pc, "is_canonical_pid", return_value=False):
            out = pc.supervise_once()
        self.assertEqual(out["outcome"], "stale-record")

    def test_terminal_exits_without_action(self):
        _temp_registry(self)
        _write(_run_record(state="ABORTED"))
        with mock.patch.object(pc, "_terminate_verified_pid") as term:
            out = pc.supervise_once()
        term.assert_not_called()
        self.assertEqual(out["outcome"], "already-terminal")

    def test_natural_end_noop(self):
        _temp_registry(self)
        _write(_run_record(state="COMPLETED"))
        out = pc.supervise_once()
        self.assertEqual(out["outcome"], "no-active-run")

    def test_launcher_preserved(self):
        for launcher in ("agent", "dashboard", "direct"):
            _temp_registry(self)
            _write(_run_record(launcher=launcher))
            with mock.patch.object(pc, "is_canonical_pid", return_value=True):
                pc.claim_supervision()
            rec = pc.read_registry()
            self.assertEqual(rec.get("launcher"), launcher)

    def test_failure_budget_marks_failed(self):
        self._claimed(_run_record())
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "collect_supervision_snapshot",
                                   side_effect=RuntimeError("boom")):
                out = None
                for _ in range(6):
                    out = pc.supervise_once()
        self.assertEqual(out["outcome"], "supervisor-failed")
        rec = pc.read_registry()
        self.assertEqual((rec.get("supervisor") or {}).get("state"), "FAILED")

    def test_no_start_path_in_supervisor(self):
        import inspect
        for name in ("supervise", "supervise_once", "enforce_abort",
                     "claim_supervision"):
            src = inspect.getsource(getattr(pc, name))
            self.assertNotIn("start_probe", src)


# ------------------------------------------------------------------
# Status contract (V2 additive block)
# ------------------------------------------------------------------

class SupervisorStatusTest(unittest.TestCase):
    def test_unknown_shape(self):
        _temp_registry(self)
        out = pc.status()
        sup = out["supervisor"]
        for key in ("state", "watched_pid", "run_id", "last_check_at",
                    "abort_triggered", "abort_reason", "abort_rule",
                    "abort_threshold", "abort_observed", "supervision_source"):
            self.assertIn(key, sup)
        self.assertEqual(sup["state"], "SUPERVISOR_UNKNOWN")
        self.assertFalse(sup["abort_triggered"])

    def test_active_shape(self):
        _temp_registry(self)
        _write(_run_record())
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            pc.claim_supervision()
        sup = pc.status()["supervisor"]
        self.assertEqual(sup["state"], "SUPERVISOR_ACTIVE")
        self.assertEqual(sup["watched_pid"], 424242)


# ------------------------------------------------------------------
# PID identity (wmic + ctypes fallback)
# ------------------------------------------------------------------

class IdentityTest(unittest.TestCase):
    def test_own_creation_time_available(self):
        import microstructure_probe.dashboard as dash
        ctime = dash.process_info(os.getpid())[1]
        if os.name == "nt":
            self.assertIsNotNone(ctime)
        self.assertTrue(dash.pid_is_ours(os.getpid(), ctime))

    def test_dead_pid_not_ours(self):
        from microstructure_probe import dashboard as dash
        self.assertFalse(dash.pid_is_ours(99999999, "STAMP"))
        self.assertFalse(pc.is_canonical_pid({"pid": 99999999,
                                              "create_time": "STAMP"}))

    def test_ctypes_fallback_shape(self):
        from microstructure_probe.dashboard import _creation_time_ctypes
        ctime = _creation_time_ctypes(os.getpid())
        if os.name == "nt":
            self.assertIsNotNone(ctime)
            self.assertIn("T", ctime)
        self.assertIsNone(_creation_time_ctypes(99999999))


# ------------------------------------------------------------------
# REAL abort integration (controlled destructive test)
# ------------------------------------------------------------------

class AbortIntegrationTest(unittest.TestCase):
    def test_abort_real_sleeper_preserves_foreign(self):
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
            log_path = Path(tempfile.mkdtemp(prefix="supev_")) / "run.log"
            self.addCleanup(_rmtree_parent, log_path)
            # Breaching evidence: one summary with 6% cumulative rejects.
            log_path.write_text(
                "2026-10-10 10:00:00,000 INFO "
                '{"kind": "summary", "runtimeSeconds": 100.0, "dataQuality": {'
                '"messagesByStream": {"a": 100000}, "timestampRejected": 6000, '
                '"reconnections": {"market": 0, "public": 0}, '
                '"staleStreams": [], "missingStreams": []}, '
                '"safety": {"BOT_MODE": "observe", "apiKeysUsed": 0, '
                '"realOrdersSent": 0, "orderExecutionPathPresent": false}, '
                '"prospective": {"errors": 0}}\n', encoding="utf-8")
            rec = _run_record(pid=victim.pid)
            rec["create_time"] = ctime
            rec["evidence"] = {"dir": str(log_path.parent),
                               "log": str(log_path)}
            _write(rec)
            out = pc.supervise(interval_s=5.0, timeout_s=60.0)
            self.assertTrue(out.get("aborted"))
            self.assertIsNotNone(victim.poll())
            self.assertIsNone(foreign.poll())
            final = pc.read_registry()
            self.assertEqual(final.get("state"), "ABORTED")
            self.assertEqual(final.get("abort_rule"), "timestamp-reject-rate")
            self.assertEqual(final.get("aborted_by"), "supervisor")
            self.assertEqual(final.get("launcher"), "agent")
            # Second cycle is a no-op (one-shot, no restart).
            again = pc.supervise_once()
            self.assertEqual(again["outcome"], "already-terminal")
            self.assertIsNone(foreign.poll())
        finally:
            _kill(victim)
            _kill(foreign)

    def test_prospective_store_untouched(self):
        # The supervisor reads probe-produced evidence only: it must never
        # import stores nor write prospective tables (read-only snapshot keys
        # like "prospective_degraded" are fine).
        import inspect
        import microstructure_probe.control as ctrl
        src = inspect.getsource(ctrl)
        self.assertNotIn("PersistenceStore", src)
        self.assertNotIn("store_prospective", src)
        self.assertNotIn("prospective_setups", src)
        self.assertNotIn("prospective_outcomes", src)


def _kill(proc):
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def _rmtree_parent(path: Path) -> None:
    try:
        parent = path.parent
        for child in sorted(parent.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        parent.rmdir()
    except OSError:
        pass
