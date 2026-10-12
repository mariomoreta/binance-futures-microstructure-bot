"""ETAPA 1 regression: test fixtures must never reach canonical resources.

Locks the fixture isolation for the Route-A helpers (test_probe,
test_host_telemetry, test_p14b_3_transport_freshness) and the Route-E
evidence-dir discipline (start_probe / watcher spawner):

- With the default persistence factory forbidden, helper-built probes run
  message traffic with zero factory calls and land rows in their OWN temp
  store (fail-before: the pre-fix bodies call the factory 61 times per
  full-suite audit; see docs/evidence/TEST_ISOLATION_AUDIT_PREFIX.json and
  scripts/repro_default_store_writes.py).
- start_probe / _default_watcher_spawner write evidence logs under the
  given temp dir, never under canonical logs/probe-runs/.

Hermetic: temp dirs/files only, mocked spawns, no market traffic.
Run: python run_tests.py
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_detectors import test_config
from test_host_telemetry import make_isolated_probe as make_probe_host
from test_p14b_3_transport_freshness import (
    make_isolated_probe as make_probe_p14b3)
from test_probe import make_isolated_probe as make_probe_test


def _live_book_ticker() -> str:
    now_ms = int(time.time() * 1000)
    return json.dumps({
        "stream": "btcusdt@bookTicker",
        "data": {"E": now_ms, "T": now_ms, "s": "BTCUSDT",
                 "b": "100", "a": "100.01", "u": 1, "pu": 0},
    })


class DefaultFactoryForbiddenTest(unittest.TestCase):
    def _check_helper(self, make) -> None:
        from microstructure_probe import probe as probe_mod

        with mock.patch.object(
                probe_mod, "get_persistence_store",
                side_effect=AssertionError(
                    "canonical store forbidden")) as default:
            probe = make(self)
            self.assertTrue(
                str(probe.persistence.db_path).startswith(
                    tempfile.gettempdir()))
            probe._handle_message(_live_book_ticker())
            default.assert_not_called()
            rows = probe.persistence.latest_observations(limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["symbol"], "BTCUSDT")

    def test_probe_helper_never_uses_default(self) -> None:
        self._check_helper(make_probe_test)

    def test_host_telemetry_helper_never_uses_default(self) -> None:
        self._check_helper(make_probe_host)

    def test_p14b3_helper_never_uses_default(self) -> None:
        self._check_helper(make_probe_p14b3)


class TempEvidenceDirTest(unittest.TestCase):
    def _temp_registry(self):
        tmp = Path(tempfile.mkdtemp(prefix="isolation_reg_"))
        self.addCleanup(lambda: self._rmtree(tmp))
        path = tmp / "probe_runtime.json"
        os.environ["MICROPROBE_RUNTIME_FILE"] = str(path)
        self.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
        return tmp

    @staticmethod
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

    def test_start_probe_log_lands_in_evidence_dir(self) -> None:
        from microstructure_probe import control as pc

        tmp = self._temp_registry()

        class FakeProc:
            pid = 31337

        with mock.patch.object(pc, "status_readonly",
                               return_value={"running": False,
                                             "state": "STOPPED"}), \
             mock.patch("subprocess.Popen", return_value=FakeProc()), \
             mock.patch.object(pc, "own_creation_time",
                               return_value="STAMP"):
            out = pc.start_probe(60, launcher="test",
                                 evidence_dir=str(tmp / "evidence"))
        log = Path(str(out["evidence"]["log"]))
        self.assertTrue(str(log).startswith(str(tmp)))
        self.assertTrue(log.is_file())
        pc._close_log_handles(31337)

    def test_default_watcher_spawner_log_lands_under_tmp_root(self) -> None:
        from microstructure_probe import control as pc

        tmp = Path(tempfile.mkdtemp(prefix="isolation_watch_"))
        self.addCleanup(lambda: self._rmtree(tmp))
        with mock.patch.object(pc, "repo_root", return_value=tmp), \
             mock.patch.object(pc.subprocess, "Popen",
                               side_effect=lambda argv, **kw: SimpleNamespace(
                                   pid=4242)):
            pc._default_watcher_spawner("supervisor")(100)
        logs = list((tmp / "logs" / "probe-runs").glob("watcher-*"))
        self.assertEqual(len(logs), 1)
        pc._LOG_HANDLES.pop(4242).close()


class NoDefaultConstructionTest(unittest.TestCase):
    """P2: injected probes build zero default stores (isolated only).

    Guards PersistenceStore/HistoryStore construction itself: any
    default-path (None or canonical-resolving) construction raises, while
    explicit temp paths delegate. Helper-built probes, summaries included,
    must construct nothing default. Temp resources exclusively — the
    canonical DBs are never present in this test's paths.
    """

    def _guarded(self):
        from microstructure_probe import persistence as persist_mod
        from microstructure_probe import history_store as hist_mod

        real_ps = persist_mod.PersistenceStore
        real_hs = hist_mod.HistoryStore
        canon = ("microprobe.db", "historical.db")

        def _is_default(path):
            if path is None:
                return True
            try:
                resolved = str(Path(path).resolve())
            except OSError:
                return False
            return ("data" in resolved and
                    any(resolved.endswith(c) for c in canon))

        class GuardedPS(real_ps):
            def __init__(self, db_path=None, *a, **k):
                if _is_default(db_path):
                    raise AssertionError(
                        "default PersistenceStore forbidden: %r" % (db_path,))
                super().__init__(db_path, *a, **k)

        class GuardedHS(real_hs):
            def __init__(self, db_path=None, *a, **k):
                if db_path is None or _is_default(db_path):
                    raise AssertionError(
                        "default HistoryStore forbidden: %r" % (db_path,))
                super().__init__(db_path, *a, **k)

        return (mock.patch.object(persist_mod, "PersistenceStore", GuardedPS),
                mock.patch.object(hist_mod, "HistoryStore", GuardedHS))

    def _check_probe(self, make) -> None:
        ps_guard, hs_guard = self._guarded()
        with ps_guard, hs_guard:
            probe = make(self)
            probe._handle_message(_live_book_ticker())
            summary = probe.build_summary(final=False)
            self.assertIn("research", summary)
            probe.log_summary(final=False)

    def test_probe_helper_builds_no_default_store(self) -> None:
        self._check_probe(make_probe_test)

    def test_host_telemetry_helper_builds_no_default_store(self) -> None:
        self._check_probe(make_probe_host)

    def test_p14b3_helper_builds_no_default_store(self) -> None:
        self._check_probe(make_probe_p14b3)

    def test_dashboard_state_uses_injected_history(self) -> None:
        import tempfile as _tf
        from microstructure_probe.dashboard import DashboardState
        from microstructure_probe.history_store import HistoryStore
        from microstructure_probe.persistence import PersistenceStore

        tmp = Path(_tf.mkdtemp(prefix="isolation_dash_"))
        self.addCleanup(lambda: self._rmtree_tmp(tmp))
        store = PersistenceStore(tmp / "probe.db")
        store.init_db()
        self.addCleanup(store.close)
        ps_guard, hs_guard = self._guarded()
        with ps_guard, hs_guard:
            hist = HistoryStore(tmp / "historical.db")
            state = DashboardState(store, history_store=hist)
            self.assertEqual(state.history_coverage(), [])
            status = state.research_status()
            self.assertEqual(status["flow_10s_rows"], 0)
            self.assertEqual(status["flow_1m_rows"], 0)
            self.assertEqual(status["book_1m_rows"], 0)
            studies = state.event_studies()
            self.assertEqual(len(studies), 6)
            for entry in studies:
                self.assertEqual(entry["horizons"], [])
            self.assertEqual(state.event_symbol("BTCUSDT"), [])

    @staticmethod
    def _rmtree_tmp(path: Path) -> None:
        try:
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main()
