"""Tests for P1-03 minimal live dashboard (routes, health, lifecycle helpers)."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import dashboard
from microstructure_probe.dashboard import (
    DashboardServer,
    DashboardState,
    compute_health,
    find_free_port,
    is_port_free,
    pid_is_ours,
    read_pidfile,
    remove_pidfile,
    write_pidfile,
)
from microstructure_probe.persistence import PersistenceStore


def _summary(**overrides):
    base = {
        "runtimeSeconds": 100.0,
        "safety": {
            "BOT_MODE": "observe",
            "apiKeysUsed": 0,
            "realOrdersSent": 0,
            "realCapitalAtRisk": 0.0,
            "maxDrawdownKillSwitchActive": False,
            "authenticatedClientsPresent": False,
            "orderExecutionPathPresent": False,
        },
        "clock": {"clockOffsetMs": -100.0, "serverTimeRttMs": 200.0,
                  "clockSyncSuccessful": 1, "clockSyncFailed": 0},
        "latency": {"legacyGlobalClampedLagMs": 50.0},
        "processing": {},
        "detectors": {},
        "dataQuality": {
            "expectedStreams": 11,
            "activeStreams": 11,
            "missingStreams": [],
            "staleStreams": [],
            "silentStreams": [],
            "messagesByStream": {"btcusdt@bookTicker": 1000},
            "maxObservedSilenceMsByStream": {"btcusdt@bookTicker": 500.0},
            "reconnections": {"public": 0, "market": 0},
            "depthSequenceGapsBySymbol": {"BTCUSDT": 0},
            "timestampRejected": 0,
            "connectivityObservationSeconds": 100.0,
            "observedUptimePercentByEndpoint": {"public": 100.0, "market": 100.0},
        },
        "eventsByType": {},
        "spreadBps": {"BTCUSDT": 0.01},
        "bookImbalance": {"BTCUSDT": 0.1},
    }
    base.update(overrides)
    return base


class HealthModelTest(unittest.TestCase):
    def test_unknown_with_no_snapshot(self) -> None:
        health = compute_health(None, {"rejection_rate": 0.0})
        self.assertEqual(health["status"], "unknown")

    def test_ok_when_healthy(self) -> None:
        store = _temp_store(self)
        store.store_telemetry_snapshot(_summary())
        snap = store.latest_telemetry()
        health = compute_health(snap, store.get_rejection_stats())
        self.assertEqual(health["status"], "ok")

    def test_stale_when_snapshot_old(self) -> None:
        store = _temp_store(self)
        store.store_telemetry_snapshot(_summary())
        with store._get_cursor() as cursor:
            cursor.execute("UPDATE telemetry_snapshots SET timestamp = ?",
                           (time.time() - 600.0,))
        snap = store.latest_telemetry()
        health = compute_health(snap, store.get_rejection_stats())
        self.assertEqual(health["status"], "stale")

    def test_degraded_on_stale_streams(self) -> None:
        store = _temp_store(self)
        summary = _summary()
        summary["dataQuality"]["staleStreams"] = ["btcusdt@depth20@100ms"]
        store.store_telemetry_snapshot(summary)
        snap = store.latest_telemetry()
        health = compute_health(snap, store.get_rejection_stats())
        self.assertEqual(health["status"], "degraded")

    def test_degraded_on_reconnects(self) -> None:
        store = _temp_store(self)
        summary = _summary()
        summary["dataQuality"]["reconnections"] = {"public": 3, "market": 0}
        store.store_telemetry_snapshot(summary)
        snap = store.latest_telemetry()
        health = compute_health(snap, store.get_rejection_stats())
        self.assertEqual(health["status"], "degraded")

    def test_degraded_on_high_rejection_rate(self) -> None:
        store = _temp_store(self)
        store.store_telemetry_snapshot(_summary())
        for _ in range(3):
            store.store_rejection_record(
                symbol="BTCUSDT", stream_type="btcusdt@aggTrade",
                payload={"s": "BTCUSDT"}, rejection_reason="timestamp_skew")
        snap = store.latest_telemetry()
        health = compute_health(snap, store.get_rejection_stats())
        self.assertEqual(health["status"], "degraded")


def _temp_store(testcase: unittest.TestCase) -> PersistenceStore:
    tmp = Path(tempfile.mkdtemp(prefix="dash_test_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    db_path = tmp / "dash.db"
    store = PersistenceStore(db_path=db_path)
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


class DashboardRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _temp_store(self)
        self.server = DashboardServer(host="127.0.0.1", port=0,
                                      db_path=self.store.db_path).start()
        self.addCleanup(self.server.stop)
        self.base = f"http://127.0.0.1:{self.server.bound_port()}"

    def _get(self, path: str):
        with urllib.request.urlopen(self.base + path, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")

    def test_overview_empty_db_is_unknown_not_error(self) -> None:
        code, body = self._get("/overview")
        self.assertEqual(code, 200)
        self.assertIn("UNKNOWN", body)
        self.assertIn("BOT_MODE", body)
        self.assertNotIn("<button", body)

    def test_system_empty_db_is_unknown_not_error(self) -> None:
        code, body = self._get("/system")
        self.assertEqual(code, 200)
        self.assertIn("UNKNOWN", body)

    def test_health_empty_db(self) -> None:
        code, body = self._get("/api/health")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "unknown")
        self.assertEqual(payload["bot_mode"], "unknown")
        self.assertEqual(payload["safety"]["apiKeysUsed"], 0)
        self.assertEqual(payload["safety"]["realOrdersSent"], 0)
        self.assertEqual(payload["version"], dashboard.DASHBOARD_VERSION)

    def test_overview_shows_safety_banner_and_metrics(self) -> None:
        summary = _summary()
        summary["dataQuality"]["reconnections"] = {"public": 2, "market": 0}
        self.store.store_telemetry_snapshot(summary)
        code, body = self._get("/overview")
        self.assertEqual(code, 200)
        self.assertIn("observe", body)
        self.assertIn("DEGRADED", body)
        self.assertIn("keys=0", body)
        self.assertIn("orders=0", body)
        self.assertIn("NOT trade signals", body)
        self.assertNotIn("<button", body.lower())
        self.assertNotIn("place_order", body)

    def test_system_shows_streams_latency_clock_safety(self) -> None:
        summary = _summary()
        summary["latency"] = {"rawEventLagMs": {"aggTrade/BTCUSDT":
                             {"count": 10, "p50": 100.0, "p95": 200.0, "max": 300.0}}}
        summary["processing"] = {"processingLatencyMs": {"aggTrade/BTCUSDT":
                                 {"count": 10, "p50": 0.01, "p95": 0.02, "max": 0.05}}}
        self.store.store_telemetry_snapshot(summary)
        code, body = self._get("/system")
        self.assertEqual(code, 200)
        for marker in ("btcusdt@bookTicker", "100.0", "200.0", "offset ms",
                       "Rejections", "Persistence", "Safety", "observe"):
            self.assertIn(marker, body)

    def test_health_ok_when_healthy(self) -> None:
        self.store.store_telemetry_snapshot(_summary())
        code, body = self._get("/api/health")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["bot_mode"], "observe")
        self.assertIsNotNone(payload["latest_snapshot_timestamp"])
        self.assertEqual(payload["stream_summary"]["active"], 11)

    def test_unknown_route_404(self) -> None:
        try:
            self._get("/nope")
            self.fail("expected HTTPError")
        except Exception as exc:
            self.assertIn("404", str(exc))


class PortSelectionTest(unittest.TestCase):
    def test_skips_occupied_port(self) -> None:
        import socket

        occupied = None
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            occupied = sock.getsockname()[1]
            self.assertFalse(is_port_free(occupied))
            free = find_free_port([occupied] + dashboard.PORT_CANDIDATES)
            self.assertNotEqual(free, occupied)
            self.assertTrue(is_port_free(free))

    def test_all_busy_raises(self) -> None:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            busy = sock.getsockname()[1]
            with self.assertRaises(RuntimeError):
                find_free_port([busy])


class PidfileTest(unittest.TestCase):
    def test_dead_pid_is_not_ours(self) -> None:
        self.assertFalse(pid_is_ours(999999, None))

    def test_live_python_pid_is_ours(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertTrue(pid_is_ours(proc.pid, None))
        finally:
            proc.terminate()
            proc.wait(timeout=10)
        self.assertFalse(pid_is_ours(proc.pid, None))

    def test_stale_pidfile_round_trip(self) -> None:
        import tempfile as _tf

        with _tf.TemporaryDirectory() as tmp:
            real = dashboard.pidfile_path
            dashboard.pidfile_path = lambda: Path(tmp) / "dashboard.pid"  # type: ignore
            try:
                self.assertIsNone(read_pidfile())
                dashboard.write_pidfile(999999, 8091, "http://127.0.0.1:8091")
                data = read_pidfile()
                self.assertEqual(data["pid"], 999999)
                self.assertFalse(pid_is_ours(int(data["pid"]), data.get("created")))
                remove_pidfile()
                self.assertIsNone(read_pidfile())
            finally:
                dashboard.pidfile_path = real  # type: ignore


if __name__ == "__main__":
    unittest.main()
