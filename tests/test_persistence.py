"""Tests for P1-02 persistence foundation."""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Allow `from test_detectors import test_config` (same pattern as test_probe.py)
# regardless of which runner/discovery root is used.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe.persistence import PersistenceStore


class PersistenceStoreTest(unittest.TestCase):
    """Persistence foundation tests."""

    def setUp(self) -> None:
        """Create a fresh temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp(prefix="persist_test_")
        self.db_path = Path(self.temp_dir) / "test.db"
        self.store = PersistenceStore(db_path=self.db_path)
        self.store.init_db()

    def tearDown(self) -> None:
        """Clean up temporary database."""
        self.store.close()
        try:
            self.db_path.unlink(missing_ok=True)
            self.db_path.parent.rmdir()
        except OSError:
            pass

    def test_schema_initialization(self) -> None:
        """Schema initializes correctly with all required tables."""
        tables = [
            "persistence_meta",
            "telemetry_snapshots",
            "market_observations",
            "rejected_observations",
        ]
        for table in tables:
            with self.store._get_cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                )
                self.assertIsNotNone(cursor.fetchone(), f"Table {table} should exist")

    def test_schema_version_tracking(self) -> None:
        """Schema version is tracked in persistence_meta."""
        with self.store._get_cursor() as cursor:
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key = 'schema_version'"
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row[0]), 1)

    def test_telemetry_snapshot_round_trip(self) -> None:
        """Telemetry snapshot can be stored and retrieved."""
        snapshot = {
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
            "clock": {"offset_ms": 0},
            "latency": {"legacyGlobalClampedLagMs": 50.0},
            "processing": {},
            "detectors": {},
            "dataQuality": {
                "timestampRejected": 0,
                "messagesByStream": {"bookTicker": 100},
            },
            "eventsByType": {},
            "spreadBps": {},
            "bookImbalance": {},
        }
        self.store.store_telemetry_snapshot(snapshot)
        latest = self.store.latest_telemetry()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["runtimeSeconds"], 100.0)
        self.assertEqual(latest["safety"]["BOT_MODE"], "observe")
        self.assertEqual(latest["safety"]["apiKeysUsed"], 0)
        self.assertFalse(latest["safety"]["orderExecutionPathPresent"])

    def test_rejected_observation_not_in_valid_records(self) -> None:
        """Skew-invalid observations are counted as rejection telemetry
        but CANNOT become valid feature records."""
        payload = {"s": "BTCUSDT", "E": 1000, "T": 1000}
        # Store as rejected
        self.store.store_rejection_record(
            symbol="BTCUSDT",
            stream_type="btcusdt@aggTrade",
            payload=payload,
            rejection_reason="timestamp_skew",
            event_time_ms=1000,
        )
        # Valid observations should be empty
        valid = self.store.latest_observations(limit=100)
        for obs in valid:
            self.assertEqual(
                obs.get("is_valid", 1), 1,
                "Rejected observation should not appear in valid records"
            )
        # Rejection stats should show the rejected record
        stats = self.store.get_rejection_stats()
        self.assertGreater(stats["total_rejected"], 0)

    def test_restart_reopen(self) -> None:
        """Data persists across store close/reopen."""
        snapshot = {
            "runtimeSeconds": 50.0,
            "safety": {
                "BOT_MODE": "observe",
                "apiKeysUsed": 0,
                "realOrdersSent": 0,
                "realCapitalAtRisk": 0.0,
                "maxDrawdownKillSwitchActive": False,
                "authenticatedClientsPresent": False,
                "orderExecutionPathPresent": False,
            },
            "clock": {},
            "latency": {"legacyGlobalClampedLagMs": 0.0},
            "processing": {},
            "detectors": {},
            "dataQuality": {},
            "eventsByType": {},
            "spreadBps": {},
            "bookImbalance": {},
        }
        self.store.store_telemetry_snapshot(snapshot)
        self.store.close()
        # Reopen with new store instance
        store2 = PersistenceStore(db_path=self.db_path)
        store2.init_db()
        latest = store2.latest_telemetry()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["runtimeSeconds"], 50.0)
        store2.close()

    def test_graceful_close(self) -> None:
        """Close cleans up resources without error."""
        self.store.close()
        # Double-close should not raise
        self.store.close()

    def test_storage_path_is_project_local(self) -> None:
        """Database path is project-local, not system-wide."""
        path_str = str(self.store.db_path)
        self.assertIn("persist_test_", path_str)
        self.assertTrue(path_str.endswith(".db"))

    def test_observe_only_safety(self) -> None:
        """Persistence enforces observe-only: no trading/order paths."""
        # Verify no order/execution/auth keywords in persistence source
        source = Path(__file__).parent.parent / "src" / "microstructure_probe" / "persistence.py"
        content = source.read_text(encoding="utf-8").lower()
        forbidden = [
            "/fapi/v1/order",
            "x-mbx-apikey",
            "create_order",
            "place_order",
            "send_order",
            "api_secret",
            "/private/",
        ]
        for term in forbidden:
            self.assertNotIn(term, content, f"Forbidden term '{term}' in persistence source")

    def test_retention_policy_telemetry(self) -> None:
        """Telemetry snapshots are bounded by retention policy."""
        # Small cap keeps this test fast while proving the bound.
        self.store.max_snapshots = 20
        # Store more than max_snapshots
        for i in range(self.store.max_snapshots + 10):
            snapshot = {
                "runtimeSeconds": float(i),
                "safety": {
                    "BOT_MODE": "observe",
                    "apiKeysUsed": 0,
                    "realOrdersSent": 0,
                    "realCapitalAtRisk": 0.0,
                    "maxDrawdownKillSwitchActive": False,
                    "authenticatedClientsPresent": False,
                    "orderExecutionPathPresent": False,
                },
                "clock": {},
                "latency": {"legacyGlobalClampedLagMs": 0.0},
                "processing": {},
                "detectors": {},
                "dataQuality": {},
                "eventsByType": {},
                "spreadBps": {},
                "bookImbalance": {},
            }
            self.store.store_telemetry_snapshot(snapshot)
        # Count should be bounded
        with self.store._get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM telemetry_snapshots")
            count = cursor.fetchone()[0]
        self.assertLessEqual(count, self.store.max_snapshots)

    def test_retention_policy_observations(self) -> None:
        """Market observations are bounded by retention policy."""
        # Small cap keeps this test fast while proving the bound.
        self.store.max_observations = 50
        # Store more than max_observations
        for i in range(self.store.max_observations + 10):
            self.store.store_market_observation(
                symbol="BTCUSDT",
                stream_type="btcusdt@aggTrade",
                payload={"s": "BTCUSDT", "E": 1000 + i, "T": 1000 + i},
                is_valid=True,
            )
        # Count should be bounded
        with self.store._get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM market_observations")
            count = cursor.fetchone()[0]
        self.assertLessEqual(count, self.store.max_observations)

    def test_invalid_data_excluded_from_valid_feature_records(self) -> None:
        """Timestamp-rejected/skew-invalid observations are NEVER treated
        as valid feature inputs."""
        # Store a rejected observation
        self.store.store_rejection_record(
            symbol="BTCUSDT",
            stream_type="btcusdt@aggTrade",
            payload={"s": "BTCUSDT", "E": 1000, "T": 1000},
            rejection_reason="timestamp_skew",
        )
        # Store a valid observation
        self.store.store_market_observation(
            symbol="ETHUSDT",
            stream_type="ethusdt@aggTrade",
            payload={"s": "ETHUSDT", "E": 2000, "T": 2000},
            is_valid=True,
        )
        # Only valid observations should appear in valid feature records
        valid = self.store.latest_observations(limit=100)
        symbols = {obs["symbol"] for obs in valid}
        self.assertNotIn("BTCUSDT", symbols, "Rejected BTCUSDT should not be in valid records")
        self.assertIn("ETHUSDT", symbols, "Valid ETHUSDT should be in valid records")

    def test_market_observation_round_trip(self) -> None:
        """A valid observation is stored and readable with parsed payload."""
        payload = {"s": "BTCUSDT", "E": 3000, "T": 3000, "p": "100.5", "q": "2"}
        normalized = {"symbol": "BTCUSDT", "price": "100.5"}
        self.store.store_market_observation(
            symbol="BTCUSDT",
            stream_type="btcusdt@aggTrade",
            payload=payload,
            normalized=normalized,
            event_time_ms=3000,
            transaction_time_ms=3000,
            is_valid=True,
        )
        valid = self.store.latest_observations(limit=10)
        self.assertEqual(len(valid), 1)
        obs = valid[0]
        self.assertEqual(obs["symbol"], "BTCUSDT")
        self.assertEqual(obs["payload"], payload)
        self.assertEqual(obs["normalized"], normalized)
        self.assertEqual(obs["event_time_ms"], 3000)

    def test_rejection_record_sync_context_without_event_loop(self) -> None:
        """store_rejection_record works with no running event loop (sync fallback)."""
        self.store.store_rejection_record(
            symbol="BTCUSDT",
            stream_type="btcusdt@bookTicker",
            payload={"s": "BTCUSDT", "E": 4000},
            rejection_reason="timestamp_skew",
            event_time_ms=4000,
        )
        stats = self.store.get_rejection_stats()
        self.assertEqual(stats["total_rejected"], 1)
        self.assertEqual(stats["by_reason"], {"timestamp_skew": 1})
        self.assertEqual(stats["by_stream"], {"btcusdt@bookTicker": 1})
        self.assertEqual(stats["rejection_rate"], 1.0)

    def test_rejection_retention_bounded(self) -> None:
        """Rejected-observation retention keeps the table bounded."""
        self.store.max_rejections = 10
        for i in range(15):
            self.store.store_rejection_record(
                symbol="BTCUSDT",
                stream_type="btcusdt@aggTrade",
                payload={"s": "BTCUSDT", "E": i},
                rejection_reason="timestamp_skew",
            )
        with self.store._get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM rejected_observations")
            count = cursor.fetchone()[0]
        self.assertLessEqual(count, 10)

    def test_snapshot_not_starved_by_observation_flood(self) -> None:
        """Snapshots use a dedicated writer: a bulk observation backlog must
        not delay the dashboard feed (P1-03 live-verification finding)."""
        import asyncio

        async def flood_then_snapshot() -> None:
            for i in range(300):
                self.store.store_market_observation(
                    symbol="BTCUSDT", stream_type="btcusdt@bookTicker",
                    payload={"s": "BTCUSDT", "E": i}, is_valid=True)
            self.store.store_telemetry_snapshot({
                "runtimeSeconds": 1.0,
                "safety": {"BOT_MODE": "observe", "apiKeysUsed": 0,
                           "realOrdersSent": 0, "realCapitalAtRisk": 0.0,
                           "maxDrawdownKillSwitchActive": False,
                           "authenticatedClientsPresent": False,
                           "orderExecutionPathPresent": False},
                "clock": {}, "latency": {"legacyGlobalClampedLagMs": 0.0},
                "processing": {}, "detectors": {}, "dataQuality": {},
                "eventsByType": {}, "spreadBps": {}, "bookImbalance": {},
            })
            await asyncio.sleep(5)

        asyncio.run(flood_then_snapshot())
        latest = self.store.latest_telemetry()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["runtimeSeconds"], 1.0)

    def test_default_path_is_project_local_and_ignored(self) -> None:
        """Default DB lives under project data/ which the repo git-ignores."""
        from microstructure_probe.persistence import PersistenceStore as PS

        default_path = PS().db_path
        self.assertEqual(default_path.name, "microprobe.db")
        self.assertEqual(default_path.parent.name, "data")
        gitignore = Path(__file__).parent.parent / ".gitignore"
        ignored = gitignore.read_text(encoding="utf-8")
        self.assertIn("data/", ignored)
        self.assertTrue("*.db" in ignored or "*.sqlite" in ignored)


class ProbePersistenceTest(unittest.TestCase):
    """Write-path integration: probe messages route to the correct tables."""

    def setUp(self) -> None:
        from microstructure_probe.probe import MarketProbe

        from test_detectors import test_config

        self.temp_dir = tempfile.mkdtemp(prefix="probe_persist_test_")
        self.db_path = Path(self.temp_dir) / "probe.db"
        self.store = PersistenceStore(db_path=self.db_path)
        self.probe = MarketProbe(test_config())
        self.probe.set_persistence(self.store)

    def tearDown(self) -> None:
        self.store.close()
        try:
            self.db_path.unlink(missing_ok=True)
            self.db_path.parent.rmdir()
        except OSError:
            pass

    def test_valid_message_reaches_observations(self) -> None:
        """A fresh valid aggTrade lands in market_observations, not rejections."""
        now_ms = int(time.time() * 1000)
        self.probe._handle_message(json.dumps({
            "stream": "btcusdt@aggTrade",
            "data": {"E": now_ms, "T": now_ms, "s": "BTCUSDT", "p": "100", "q": "1"},
        }))
        valid = self.store.latest_observations(limit=10)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["symbol"], "BTCUSDT")
        stats = self.store.get_rejection_stats()
        self.assertEqual(stats["total_rejected"], 0)

    def test_skew_rejected_message_reaches_only_rejections(self) -> None:
        """A skew-rejected message is rejection telemetry, never a valid record."""
        stale_ms = int(time.time() * 1000) - 6000
        self.probe._handle_message(json.dumps({
            "stream": "btcusdt@aggTrade",
            "data": {"E": stale_ms, "T": stale_ms, "s": "BTCUSDT", "p": "100", "q": "1"},
        }))
        self.assertEqual(self.probe.stats.rejected_timestamp, 1)
        self.assertEqual(self.store.latest_observations(limit=10), [])
        stats = self.store.get_rejection_stats()
        self.assertEqual(stats["total_rejected"], 1)
        self.assertEqual(stats["by_reason"], {"timestamp_skew": 1})

    def test_markprice_array_persisted_as_multi_record(self) -> None:
        """List payloads (markPrice arrays) are preserved, not dropped."""
        now_ms = int(time.time() * 1000)
        self.probe._handle_message(json.dumps({
            "stream": "!markPrice@arr@1s",
            "data": [{"E": now_ms, "T": 999_999, "s": "BTCUSDT", "p": "100", "r": "0.001"}],
        }))
        valid = self.store.latest_observations(limit=10)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["symbol"], "MULTI")
        self.assertIn("items", valid[0]["payload"])

    def test_summary_persisted_for_dashboard(self) -> None:
        """log_summary stores a snapshot the P1-03 dashboard can read back."""
        self.probe.log_summary(final=False)
        latest = self.store.latest_telemetry()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["safety"]["BOT_MODE"], "observe")
        self.assertEqual(latest["safety"]["apiKeysUsed"], 0)
        self.assertIn("dataQuality", latest)


if __name__ == "__main__":
    unittest.main()