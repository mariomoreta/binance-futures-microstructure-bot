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


def _return_feature(symbol="BTCUSDT", price=100.0, returns=None):
    all_none = {tf: None for tf in
                ("1m", "3m", "5m", "15m", "1h", "4h", "24h")}
    if returns:
        all_none.update(returns)
    return {
        "symbol": symbol,
        "current_price": price,
        "source": "markPrice",
        "source_timestamp_ms": 1_700_000_000_000,
        "sample_age_ms": 5_000,
        "history_span_ms": 120_000,
        "returns": all_none,
        "anchor_ms": {tf: None for tf in all_none},
        "available_tfs": [tf for tf, v in all_none.items() if v is not None],
        "warmup_complete": all(v is not None for v in all_none.values()),
    }


class ReturnsSectionTest(unittest.TestCase):
    """P1-04 progressive dashboard: Symbol Returns section + feature API."""

    def setUp(self) -> None:
        self.store = _temp_store(self)
        self.server = DashboardServer(host="127.0.0.1", port=0,
                                      db_path=self.store.db_path).start()
        self.addCleanup(self.server.stop)
        self.base = f"http://127.0.0.1:{self.server.bound_port()}"

    def _get(self, path: str):
        with urllib.request.urlopen(self.base + path, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")

    def test_no_features_yet_honest_note(self) -> None:
        self.store.store_telemetry_snapshot(_summary())
        code, body = self._get("/overview")
        self.assertEqual(code, 200)
        self.assertIn("Symbol Returns", body)
        self.assertIn("insufficient history", body)

    def test_partial_warmup_renders_values_and_gaps(self) -> None:
        self.store.store_telemetry_snapshot(_summary())
        self.store.store_return_features([
            _return_feature("BTCUSDT", 100.0, {"1m": 0.001234, "3m": -0.002})])
        code, body = self._get("/overview")
        self.assertEqual(code, 200)
        self.assertIn("BTCUSDT", body)
        self.assertIn("+0.123%", body)
        self.assertIn("-0.200%", body)
        self.assertIn("insufficient history", body)  # unavailable horizons
        self.assertIn("WARMING", body)
        for forbidden in ("IGNITION", "EXPANSION", "place_order", "<button"):
            self.assertNotIn(forbidden, body)

    def test_movers_route_exists_p109(self) -> None:
        code, body = self._get("/movers")
        self.assertEqual(code, 200)
        self.assertIn("MOVERS", body)

    def test_features_api_shape(self) -> None:
        self.store.store_return_features([
            _return_feature("BTCUSDT", 100.0, {"1m": 0.01}),
            _return_feature("ETHUSDT", 50.0, {})])
        code, body = self._get("/api/features/returns")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertIn("generated_at", payload)
        self.assertEqual(payload["source"], "markPrice")
        by_symbol = {f["symbol"]: f for f in payload["features"]}
        self.assertEqual(by_symbol["BTCUSDT"]["returns"]["1m"], 0.01)
        self.assertIsNone(by_symbol["ETHUSDT"]["returns"]["1m"])
        self.assertIsNone(by_symbol["BTCUSDT"]["returns"]["24h"])

    def test_features_api_empty_is_404(self) -> None:
        try:
            self._get("/api/features/returns")
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

    def test_restart_parser_accepts_port_args(self) -> None:
        """Regression: restart must parse like start (AttributeError once)."""
        args = dashboard.build_parser().parse_args(["restart", "--port", "8099"])
        self.assertEqual(args.command, "restart")
        self.assertEqual(args.port, 8099)


def _return_feature(symbol="BTCUSDT", price=100.0, returns=None,
                    momentum=None, tier="CORE"):
    all_none = {tf: None for tf in
                ("1m", "3m", "5m", "15m", "1h", "4h", "24h")}
    if returns:
        all_none.update(returns)
    return {
        "symbol": symbol,
        "current_price": price,
        "source": "markPrice",
        "source_timestamp_ms": 1_700_000_000_000,
        "sample_age_ms": 5_000,
        "history_span_ms": 120_000,
        "returns": all_none,
        "anchor_ms": {tf: None for tf in all_none},
        "available_tfs": [tf for tf, v in all_none.items() if v is not None],
        "warmup_complete": all(v is not None for v in all_none.values()),
        "tier": tier,
        "momentum": momentum or {"velocity": {}, "acceleration": {}},
        "ranks": {},
    }


class IntelSectionTest(unittest.TestCase):
    """P1-05 market-intelligence area + health separation + reject labels."""

    def setUp(self) -> None:
        self.store = _temp_store(self)
        self.server = DashboardServer(host="127.0.0.1", port=0,
                                      db_path=self.store.db_path).start()
        self.addCleanup(self.server.stop)
        self.base = f"http://127.0.0.1:{self.server.bound_port()}"

    def _get(self, path: str):
        with urllib.request.urlopen(self.base + path, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")

    def test_health_sections_separated(self) -> None:
        self.store.store_telemetry_snapshot(_summary())
        _, body = self._get("/overview")
        for section in ("Dashboard server health", "Market feed health",
                        "Persistence health", "Market intelligence"):
            self.assertIn(section, body)

    def test_server_ok_while_feed_unknown(self) -> None:
        code, body = self._get("/api/health")
        payload = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(payload["server"]["status"], "ok")
        self.assertEqual(payload["status"], "unknown")

    def test_reject_labels_current_vs_retained(self) -> None:
        summary = _summary()
        summary["dataQuality"]["timestampRejected"] = 7
        self.store.store_telemetry_snapshot(summary)
        self.store.store_rejection_record(
            symbol="BTCUSDT", stream_type="btcusdt@aggTrade",
            payload={"s": "BTCUSDT"}, rejection_reason="timestamp_skew")
        _, overview = self._get("/overview")
        self.assertIn("this run", overview)
        self.assertIn("retained", overview)
        _, system = self._get("/system")
        self.assertIn("run counter vs retained rows", system)

    def test_intel_tiers_and_momentum_rendered(self) -> None:
        self.store.store_telemetry_snapshot(_summary())
        self.store.store_return_features([
            _return_feature("BTCUSDT", 100.0, {"1m": 0.005},
                            {"velocity": {"1m": 1e-05},
                             "acceleration": {"1m": 2e-09}})])
        self.store.store_discovery_snapshot({
            "generated_at_ms": 1_700_000_000_000,
            "eligible_count": 500, "seen_count": 520, "filtered_count": 20,
            "core": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "hot_dynamic": ["XRPUSDT"],
            "tops": {
                "gainers": [{"symbol": "XRPUSDT", "change_24h_pct": 25.0,
                             "price": 2.5, "quote_volume_24h": 5e6}],
                "losers": [{"symbol": "DOGEUSDT", "change_24h_pct": -18.0,
                            "price": 0.2, "quote_volume_24h": 4e6}],
                "most_active": []},
        })
        _, body = self._get("/overview")
        for marker in ("Universe tiers", "CORE", "HOT", "XRPUSDT",
                       "Live momentum", "Discovery movers",
                       "Top gainers 24h", "Top losers 24h",
                       "discovery only, NOT live", "DOGEUSDT"):
            self.assertIn(marker, body)
        for forbidden in ("IGNITION", "place_order", "<button"):
            self.assertNotIn(forbidden, body)

    def test_momentum_api_shape(self) -> None:
        self.store.store_return_features([
            _return_feature("BTCUSDT", 100.0, {"1m": 0.005},
                            {"velocity": {"1m": 1e-05},
                             "acceleration": {"1m": None}})])
        code, body = self._get("/api/features/momentum")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertIn("velocity_semantics", payload)
        self.assertIn("ranks", payload)
        row = payload["features"][0]
        self.assertEqual(row["tier"], "CORE")
        self.assertEqual(row["momentum"]["velocity"]["1m"], 1e-05)

    def test_momentum_api_empty_is_404(self) -> None:
        try:
            self._get("/api/features/momentum")
            self.fail("expected HTTPError")
        except Exception as exc:
            self.assertIn("404", str(exc))

    def test_discovery_api_shape_and_empty(self) -> None:
        try:
            self._get("/api/discovery")
            self.fail("expected HTTPError")
        except Exception as exc:
            self.assertIn("404", str(exc))
        self.store.store_discovery_snapshot({
            "generated_at_ms": 1, "eligible_count": 10, "seen_count": 12,
            "filtered_count": 2, "core": ["BTCUSDT"], "hot_dynamic": [],
            "tops": {}})
        self.store.log_universe_event("promoted", "XRPUSDT", "top_mover_2_votes")
        code, body = self._get("/api/discovery")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertIn("CORE pinned benchmarks", payload["universe_architecture"])
        self.assertIn("only CORE symbols subscribed",
                      payload["subscription_note"])
        self.assertEqual(payload["discovery"]["eligible_count"], 10)
        self.assertEqual(payload["events"][0]["symbol"], "XRPUSDT")


class ProbeHealthSemanticsTest(unittest.TestCase):
    """forceOrder silence is normal: never missing, never stale."""

    def test_forceorder_never_missing(self) -> None:
        from microstructure_probe.probe import MarketProbe
        from test_detectors import test_config

        probe = MarketProbe(test_config(), wall_clock_ms=lambda: 11_000.0,
                            monotonic=lambda: 11.0)
        # Only forceOrder seen; everything else absent.
        probe.stats.last_seen_monotonic["!forceOrder@arr"] = 10.0
        probe.stats.first_seen_monotonic["!forceOrder@arr"] = 10.0
        summary = probe.build_summary(final=False)
        dq = summary["dataQuality"]
        self.assertNotIn("!forceOrder@arr", dq["missingStreams"])
        self.assertNotIn("!forceOrder@arr", dq["staleStreams"])
        # Genuinely absent cadenced streams are still reported missing.
        self.assertIn("!markPrice@arr@1s", dq["missingStreams"])


if __name__ == "__main__":
    unittest.main()
