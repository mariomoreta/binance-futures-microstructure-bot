"""Old-HTTP GET observation stays pure (DASH-V2-64 backend handoff).

Pinning regressions: the browser-polled DashboardState.probe_status() path
must never reconcile, write, or mutate through the legacy control.status().
A future edit reintroducing the mutating call into this GET path must fail
here (verified once by temporarily restoring control.status: G1 then reports
FAILED and rewrites the registry).

  G1  stale RUNNING record: probe_status reports stored RUNNING (never the
      reconciled FAILED), registry bytes identical, control.status /
      _write_registry / update_registry / _close_log_handles uncalled, no
      process action.
  G2  absent registry: STOPPED shape, file never created.
  G3  process/feed separation: old snapshot + RUNNING record reports
      process RUNNING alongside feed STALE, bytes identical.

No live server, no probe, no market I/O. Run: python run_tests.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc
from microstructure_probe.dashboard import DashboardState
from microstructure_probe.persistence import PersistenceStore


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="getpure_reg_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    path = tmp / "probe_runtime.json"
    os.environ["MICROPROBE_RUNTIME_FILE"] = str(path)
    testcase.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
    return path


def _temp_store(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="getpure_db_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    store = PersistenceStore(db_path=tmp / "dash.db")
    store.init_db()
    testcase.addCleanup(store.close)
    return store


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


def _run_record(state="RUNNING"):
    return {"schema": 1, "writer": "control/1", "state": state,
            "pid": 424243, "create_time": "STAMP",
            "started_at": "2026-10-10T10:00:00+00:00", "mode": "observe",
            "command": [sys.executable, "-m", "microstructure_probe"],
            "duration_seconds": 2100, "expected_end_at": None,
            "launcher": "agent", "preset": "standard",
            "evidence": {"dir": "ev", "log": "run.log"},
            "last_exit": None}


def _old_snapshot():
    return {
        "runtimeSeconds": 100.0,
        "safety": {"BOT_MODE": "observe", "apiKeysUsed": 0,
                   "realOrdersSent": 0},
        "clock": {"clockOffsetMs": -100.0},
        "dataQuality": {
            "expectedStreams": 11, "activeStreams": 11,
            "missingStreams": [], "staleStreams": [], "silentStreams": [],
            "messagesByStream": {"btcusdt@bookTicker": 1000},
            "maxObservedSilenceMsByStream": {"btcusdt@bookTicker": 500.0},
            "reconnections": {"public": 0, "market": 0},
            "timestampRejected": 0,
            "connectivityObservationSeconds": 100.0,
        },
    }


class GetPurityTest(unittest.TestCase):
    def test_stale_running_never_reconciled(self):
        reg_path = _temp_registry(self)
        reg_path.write_text(json.dumps(_run_record("RUNNING")),
                            encoding="utf-8")
        before = reg_path.read_bytes()
        state = DashboardState(_temp_store(self))
        with mock.patch.object(pc, "status") as legacy:
            with mock.patch.object(pc, "_write_registry") as wr:
                with mock.patch.object(pc, "update_registry") as up:
                    with mock.patch.object(pc, "_close_log_handles") as cl:
                        with mock.patch.object(
                                pc, "_terminate_verified_pid") as term:
                            out = state.probe_status()
        self.assertEqual(out["state"], "RUNNING")
        self.assertTrue(out["running"])
        legacy.assert_not_called()
        wr.assert_not_called()
        up.assert_not_called()
        cl.assert_not_called()
        term.assert_not_called()
        self.assertEqual(reg_path.read_bytes(), before)

    def test_absent_registry_is_stopped_without_creating(self):
        reg_path = _temp_registry(self)
        state = DashboardState(_temp_store(self))
        out = state.probe_status()
        self.assertEqual(out["state"], "STOPPED")
        self.assertFalse(out["running"])
        self.assertFalse(reg_path.exists())

    def test_process_and_feed_reported_separately(self):
        reg_path = _temp_registry(self)
        reg_path.write_text(json.dumps(_run_record("RUNNING")),
                            encoding="utf-8")
        store = _temp_store(self)
        store.store_telemetry_snapshot(_old_snapshot())
        with store._get_cursor() as cursor:
            cursor.execute("UPDATE telemetry_snapshots SET timestamp = ?",
                           (time.time() - 600.0,))
        before = reg_path.read_bytes()
        out = DashboardState(store).probe_status()
        self.assertEqual(out["state"], "RUNNING")
        self.assertEqual(out["feed_health"], "STALE")
        self.assertEqual(reg_path.read_bytes(), before)
