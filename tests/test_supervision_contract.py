"""P1-14B.8 corrections: verified verdicts, honest contracts, ownership fencing.

Regression tests for the frontend-review findings (HIGH/HIGH/HIGH/PROBABLE):
  V1  _supervision_verdict requires ACTIVE + fresh + identity-verified +
      run-bound supervision (STOPPED-fresh, mismatched, future, dead all
      lose; ok needs every condition).
  V2  established-but-malformed heartbeat is LOSS (abort), never
      "unsupervised"; never-established stays a no-op.
  C1  _sentinel_block publishes active protection only when verified
      (freshness + identity + association); raw lease lifecycle evidence
      stays published separately; future/2020 heartbeats read STALE.
  C2  same verified-display treatment for _supervisor_block.
  F1  concurrent supervisor/sentinel heartbeats never lose each other's
      fields (mutual exclusion, threaded proof).
  F2  a replaced watcher's heartbeat/finalization is a no-op (ownership
      fencing by lease pid).
  F3  enforce superseded (run left the watched state) claims nothing.
  F4  racing claims elect exactly one winner.

Deterministic, hermetic registries. No live probe. Run: python run_tests.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="vfix_"))
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


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _iso_age(seconds_ago):
    return datetime.fromtimestamp(time.time() - seconds_ago,
                                 tz=timezone.utc).isoformat()


def _iso_future(seconds_ahead):
    return datetime.fromtimestamp(time.time() + seconds_ahead,
                                 tz=timezone.utc).isoformat()


def _run_record(pid=424243, state="RUNNING"):
    return {"schema": 1, "writer": "control/1", "state": state,
            "pid": pid, "create_time": "STAMP",
            "started_at": "2026-10-10T10:00:00+00:00", "mode": "observe",
            "command": [sys.executable, "-m", "microstructure_probe"],
            "duration_seconds": 2100, "expected_end_at": None,
            "launcher": "agent", "preset": "standard",
            "evidence": {"dir": "ev", "log": "run.log"},
            "last_exit": None}


def _sup_lease(state="ACTIVE", age_s=10.0, watched=424243, pid=424244):
    return {"pid": pid, "create_time": "C", "started_at": _iso_age(300.0),
            "last_check_at": _iso_age(age_s) if age_s is not None else "bad-stamp",
            "state": state, "consecutive_failures": 0,
            "prev_supervisor_pid": None, "watched_pid": watched,
            "streaks": {"persistence": 0, "clock": 0, "db": 0},
            "abort": None}


def _sen_lease(state="ACTIVE", age_s=10.0, watched=424243, pid=424245):
    return {"pid": pid, "create_time": "C", "started_at": _iso_age(300.0),
            "last_check_at": _iso_age(age_s) if age_s is not None else "bad-stamp",
            "state": state, "consecutive_failures": 0,
            "prev_sentinel_pid": None, "watched_pid": watched,
            "action": None}


def _write(record):
    pc._write_registry(record)


# ------------------------------------------------------------------
# V1: verified verdicts
# ------------------------------------------------------------------

class VerdictHardeningTest(unittest.TestCase):
    def _rec(self, lease):
        rec = _run_record()
        rec["supervisor"] = lease
        return rec

    def test_stopped_fresh_is_not_ok(self):
        out = pc._supervision_verdict(
            self._rec(_sup_lease(state="STOPPED", age_s=5.0)),
            120.0, watcher_alive=True)
        self.assertEqual(out, "stopped-supervision")

    def test_mismatched_watched_pid_is_not_ok(self):
        out = pc._supervision_verdict(
            self._rec(_sup_lease(state="ACTIVE", age_s=5.0, watched=999999)),
            120.0, watcher_alive=True)
        self.assertEqual(out, "mismatched-supervision")

    def test_future_heartbeat_is_not_fresh(self):
        rec = _run_record()
        lease = _sup_lease(state="ACTIVE", age_s=10.0)
        lease["last_check_at"] = _iso_future(60.0)
        rec["supervisor"] = lease
        out = pc._supervision_verdict(rec, 120.0, watcher_alive=True)
        self.assertEqual(out, "stale-supervision")

    def test_dead_watcher_is_not_ok(self):
        out = pc._supervision_verdict(
            self._rec(_sup_lease(state="ACTIVE", age_s=5.0)),
            120.0, watcher_alive=False)
        self.assertEqual(out, "dead-supervision")

    def test_ok_requires_everything(self):
        out = pc._supervision_verdict(
            self._rec(_sup_lease(state="ACTIVE", age_s=5.0)),
            120.0, watcher_alive=True)
        self.assertEqual(out, "ok-supervised")

    def test_malformed_established_is_loss_not_absence(self):
        rec = _run_record()
        lease = _sup_lease(state="ACTIVE", age_s=10.0)
        lease["last_check_at"] = "not-a-timestamp"
        rec["supervisor"] = lease
        out = pc._supervision_verdict(rec, 120.0, watcher_alive=True)
        self.assertEqual(out, "stale-supervision")

    def test_never_established_is_noop(self):
        rec = _run_record()
        if "supervisor" in rec:
            del rec["supervisor"]
        out = pc._supervision_verdict(rec, 120.0, watcher_alive=True)
        self.assertEqual(out, "unsupervised")

    def test_failed_is_loss(self):
        out = pc._supervision_verdict(
            self._rec(_sup_lease(state="FAILED", age_s=5.0)),
            120.0, watcher_alive=True)
        self.assertEqual(out, "failed-supervision")


# ------------------------------------------------------------------
# C1/C2: verified display contracts
# ------------------------------------------------------------------

class DisplayContractTest(unittest.TestCase):
    def _rec(self, sup_lease=None, sen_lease=None):
        rec = _run_record()
        if sup_lease is not None:
            rec["supervisor"] = sup_lease
        if sen_lease is not None:
            rec["sentinel"] = sen_lease
        return rec

    def test_sentinel_active_requires_verification(self):
        rec = self._rec(sen_lease=_sup_lease(state="ACTIVE", age_s=5.0))
        with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                         return_value=True):
            block = pc._sentinel_block(rec)
        self.assertEqual(block["state"], "SENTINEL_ACTIVE")
        self.assertEqual(block["lease_state"], "ACTIVE")

    def test_sentinel_2020_heartbeat_is_stale(self):
        lease = _sup_lease(state="ACTIVE", age_s=10.0)
        lease["last_check_at"] = "2020-01-01T00:00:00+00:00"
        rec = self._rec(sen_lease=lease)
        with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                         return_value=True):
            block = pc._sentinel_block(rec)
        self.assertEqual(block["state"], "SENTINEL_STALE")
        self.assertEqual(block["lease_state"], "ACTIVE")

    def test_sentinel_dead_watcher_is_stale(self):
        rec = self._rec(sen_lease=_sup_lease(state="ACTIVE", age_s=5.0))
        with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                         return_value=False):
            block = pc._sentinel_block(rec)
        self.assertEqual(block["state"], "SENTINEL_STALE")

    def test_sentinel_mismatched_run_is_stale(self):
        lease = _sup_lease(state="ACTIVE", age_s=5.0, watched=999999)
        rec = self._rec(sen_lease=lease)
        with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                         return_value=True):
            block = pc._sentinel_block(rec)
        self.assertEqual(block["state"], "SENTINEL_STALE")

    def test_sentinel_missing_is_unknown(self):
        block = pc._sentinel_block(self._rec())
        self.assertEqual(block["state"], "SENTINEL_UNKNOWN")
        self.assertIsNone(block["lease_state"])

    def test_supervisor_active_requires_verification(self):
        rec = self._rec(sup_lease=_sup_lease(state="ACTIVE", age_s=5.0))
        with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                         return_value=True):
            block = pc._supervisor_block(rec)
        self.assertEqual(block["state"], "SUPERVISOR_ACTIVE")

    def test_supervisor_stopped_fresh_is_not_active(self):
        rec = self._rec(sup_lease=_sup_lease(state="STOPPED", age_s=5.0))
        with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                         return_value=True):
            block = pc._supervisor_block(rec)
        self.assertEqual(block["state"], "SUPERVISOR_STALE")


# ------------------------------------------------------------------
# F1-F4: fencing + ownership
# ------------------------------------------------------------------

class FencingTest(unittest.TestCase):
    def test_concurrent_heartbeats_keep_both_fields(self):
        # Genuine owners: both leases belong to this process, so every
        # heartbeat performs a real locked write (the old fixture used
        # foreign PIDs 424244/424245 and every heartbeat silently no-op'd,
        # leaving a byte-equivalent record).
        _temp_registry(self)
        rec = _run_record()
        rec["supervisor"] = _sup_lease(age_s=200.0, pid=os.getpid())
        rec["sentinel"] = _sen_lease(age_s=200.0, pid=os.getpid())
        _write(rec)
        sup_before = rec["supervisor"]["last_check_at"]
        sen_before = rec["sentinel"]["last_check_at"]
        errors = []

        def beat_sup():
            try:
                for _ in range(25):
                    pc._heartbeat_lease(
                        consecutive_failures=11,
                        streaks={"persistence": 1, "clock": 2, "db": 3})
            except Exception as exc:  # noqa: BLE001 - collected below
                errors.append(exc)

        def beat_sen():
            try:
                for _ in range(25):
                    pc._heartbeat_sentinel(
                        failures=22,
                        action={"rule": "none", "at": "t", "aborted": False})
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=beat_sup) for _ in range(2)]
        threads += [threading.Thread(target=beat_sen) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        # All workers exit; no failure hidden behind the threads.
        for t in threads:
            self.assertFalse(t.is_alive())
        self.assertEqual(errors, [])
        final = pc.read_registry()
        self.assertIn("supervisor", final)
        self.assertIn("sentinel", final)
        self.assertEqual(final["state"], "RUNNING")
        self.assertEqual(final["pid"], 424243)
        # Both heartbeats really advanced (writes happened, not no-ops).
        self.assertNotEqual(final["supervisor"]["last_check_at"], sup_before)
        self.assertNotEqual(final["sentinel"]["last_check_at"], sen_before)
        # Distinctive updates from each owner survive the race.
        self.assertEqual(final["supervisor"]["consecutive_failures"], 11)
        self.assertEqual(final["supervisor"]["streaks"],
                         {"persistence": 1, "clock": 2, "db": 3})
        self.assertEqual(final["sentinel"]["consecutive_failures"], 22)
        self.assertEqual(final["sentinel"]["action"],
                         {"rule": "none", "at": "t", "aborted": False})

    def test_takeover_then_old_heartbeat_noop(self):
        _temp_registry(self)
        rec = _run_record()
        rec["supervisor"] = _sup_lease(age_s=5.0, pid=111)
        _write(rec)
        # Takeover by a new owner.
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch("microstructure_probe.dashboard.pid_is_ours",
                             return_value=False):
                take = pc.claim_supervision()
        self.assertTrue(take["supervised"])
        new_pid = take["pid"]
        # Old owner's heartbeat must not touch the new lease. Patch only
        # getpid (never the whole os module: registry_path needs the real
        # environ, otherwise heartbeats write into garbage paths).
        with mock.patch.object(pc.os, "getpid", return_value=111):
            pc._heartbeat_lease()
        final = pc.read_registry()
        self.assertEqual(final["supervisor"]["pid"], new_pid)
        self.assertNotEqual(final["supervisor"]["pid"], 111)

    def test_enforce_superseded_no_mark(self):
        _temp_registry(self)
        rec = _run_record()
        _write(rec)
        decision = {"rule": "timestamp-reject-rate", "reason": "t",
                    "threshold": 0.05, "observed": 0.06}
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            with mock.patch.object(pc, "_terminate_verified_pid") as term:
                # Run leaves the watched state before enforce runs.
                live = pc.read_registry()
                live["state"] = "STOPPED"
                _write(live)
                out = pc.enforce_abort(decision)
        term.assert_not_called()
        self.assertFalse(out["aborted"])
        self.assertEqual(pc.read_registry().get("state"), "STOPPED")

    def test_racing_claims_single_winner(self):
        _temp_registry(self)
        _write(_run_record())
        winners = []
        errors = []

        def claim():
            try:
                out = pc.claim_supervision()
                if out.get("supervised"):
                    winners.append(out.get("pid"))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        # One patch lifetime spanning all threads: per-thread patch
        # objects would nest and leak a stale mock on racy exits, while
        # the real race under test (registry mutual exclusion) is intact.
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            threads = [threading.Thread(target=claim) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)
        for t in threads:
            self.assertFalse(t.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(winners), 1)

    def test_racing_sentinel_claims_single_winner(self):
        _temp_registry(self)
        _write(_run_record())
        winners = []
        errors = []

        def claim():
            try:
                out = pc.claim_sentinel()
                if out.get("watching"):
                    winners.append(out.get("pid"))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            threads = [threading.Thread(target=claim) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)
        for t in threads:
            self.assertFalse(t.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(winners), 1)
