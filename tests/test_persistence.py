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
        # Full fidelity by default here: sampling has dedicated tests below.
        self.store.sample_interval_ms = {}
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
        """Schema version is tracked in persistence_meta (currently v7)."""
        with self.store._get_cursor() as cursor:
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key = 'schema_version'"
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row[0]), 7)

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


class ObservationSamplingTest(unittest.TestCase):
    """P1-04 bounded sampling gate: backpressure remedy with visible counts."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="sample_test_")
        self.db_path = Path(self.temp_dir) / "sample.db"
        self.store = PersistenceStore(db_path=self.db_path)
        self.store.init_db()

    def tearDown(self) -> None:
        self.store.close()
        try:
            self.db_path.unlink(missing_ok=True)
            self.db_path.parent.rmdir()
        except OSError:
            pass

    def _obs(self, event_ms: int, symbol: str = "BTCUSDT",
             stream: str = "btcusdt@bookTicker") -> None:
        self.store.store_market_observation(
            symbol=symbol, stream_type=stream,
            payload={"s": symbol, "E": event_ms}, event_time_ms=event_ms,
            is_valid=True)

    def _count_obs(self) -> int:
        with self.store._get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM market_observations")
            return cursor.fetchone()[0]

    def test_first_sighting_always_accepted(self) -> None:
        self._obs(1_000_000)
        self.assertEqual(self._count_obs(), 1)

    def test_within_interval_dropped_and_counted(self) -> None:
        self._obs(1_000_000)
        self._obs(1_000_100)  # +100ms < 1000ms gate
        self._obs(1_000_200)
        self.assertEqual(self._count_obs(), 1)
        stats = self.store.sample_stats()
        self.assertEqual(stats["accepted"]["bookTicker"], 1)
        self.assertEqual(stats["dropped"]["bookTicker"], 2)

    def test_after_interval_accepted(self) -> None:
        self._obs(1_000_000)
        self._obs(1_001_000)  # exactly one interval later
        self.assertEqual(self._count_obs(), 2)

    def test_per_symbol_independence(self) -> None:
        self._obs(1_000_000, symbol="BTCUSDT")
        self._obs(1_000_100, symbol="ETHUSDT")  # other symbol: accepted
        self.assertEqual(self._count_obs(), 2)

    def test_ungated_kinds_always_persist(self) -> None:
        for i in range(5):
            self.store.store_market_observation(
                symbol="MULTI", stream_type="!markPrice@arr@1s",
                payload={"items": []}, event_time_ms=1_000_000 + i,
                is_valid=True)
        with self.store._get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM market_observations")
            self.assertEqual(cursor.fetchone()[0], 5)

    def test_gate_disabled_by_empty_map(self) -> None:
        self.store.sample_interval_ms = {}
        for i in range(5):
            self._obs(2_000_000 + i)
        self.assertEqual(self._count_obs(), 5)

    def test_configure_sampling_override_and_disable(self) -> None:
        self.store.configure_sampling({"bookTicker": 5000})
        self.assertEqual(self.store.sample_interval_ms["bookTicker"], 5000)
        self.store.configure_sampling({"bookTicker": 0})
        self.assertNotIn("bookTicker", self.store.sample_interval_ms)
        for i in range(5):
            self._obs(3_000_000 + i)
        self.assertEqual(self._count_obs(), 5)

    def test_inflight_high_water_tracked(self) -> None:
        self._obs(4_000_000)
        stats = self.store.sample_stats()
        self.assertGreaterEqual(stats["inflight_high_water"], 1)
        self.assertEqual(stats["inflight"], 0)


class SchemaV3Test(unittest.TestCase):
    """P1-04+P1-05 tables: version gate, samples, features, discovery, ranks."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="v2_test_")
        self.db_path = Path(self.temp_dir) / "v2.db"
        self.store = PersistenceStore(db_path=self.db_path)
        self.store.sample_interval_ms = {}
        self.store.init_db()

    def tearDown(self) -> None:
        self.store.close()
        try:
            self.db_path.unlink(missing_ok=True)
            self.db_path.parent.rmdir()
        except OSError:
            pass

    def test_schema_version_is_7_with_feature_tables(self) -> None:
        with self.store._get_cursor() as cursor:
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 7)
            for table in ("price_samples", "return_features",
                          "discovery_snapshots", "universe_events",
                          "rank_snapshots", "flow_features", "flow_buckets",
                          "book_features", "oi_samples", "oi_features",
                          "structure_features", "state_features",
                          "state_transitions"):
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,))
                self.assertIsNotNone(cursor.fetchone(), table)

    def test_v1_database_migrates_to_v7(self) -> None:
        # Simulate a pre-P1-04 database: v1 tables only, version marker 1.
        legacy = Path(self.temp_dir) / "legacy.db"
        conn = __import__("sqlite3").connect(str(legacy))
        conn.execute("CREATE TABLE persistence_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO persistence_meta VALUES ('schema_version', '1')")
        conn.execute("CREATE TABLE telemetry_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL)")
        conn.commit()
        conn.close()
        migrated = PersistenceStore(db_path=legacy)
        migrated.init_db()
        with migrated._get_cursor() as cursor:
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 7)
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='price_samples'")
            self.assertIsNotNone(cursor.fetchone())
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='discovery_snapshots'")
            self.assertIsNotNone(cursor.fetchone())
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='flow_features'")
            self.assertIsNotNone(cursor.fetchone())
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='flow_buckets'")
            self.assertIsNotNone(cursor.fetchone())
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='book_features'")
            self.assertIsNotNone(cursor.fetchone())
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='oi_samples'")
            self.assertIsNotNone(cursor.fetchone())
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='oi_features'")
            self.assertIsNotNone(cursor.fetchone())
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='structure_features'")
            self.assertIsNotNone(cursor.fetchone())
        # Legacy column repair still applied on the v1 path.
        with migrated._get_cursor() as cursor:
            cursor.execute("PRAGMA table_info(telemetry_snapshots)")
            columns = {row[1] for row in cursor.fetchall()}
            self.assertIn("spread_bps_json", columns)
        migrated.close()

    def test_v2_database_migrates_to_v7_preserving_rows(self) -> None:
        import time as _time

        base = (int(_time.time() * 1000) // 10_000) * 10_000 - 30_000
        self.store.store_price_samples([("BTCUSDT", base, 99.0)])
        self.store.close()
        with self.store._get_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES ('schema_version', '2')")
        reopened = PersistenceStore(db_path=self.db_path)
        reopened.init_db()
        with reopened._get_cursor() as cursor:
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 7)
        self.assertEqual(reopened.load_price_samples("BTCUSDT"),
                         [("BTCUSDT", base, 99.0)])
        reopened.close()

    def test_v3_database_migrates_to_v7_preserving_rows(self) -> None:
        # Simulate a P1-05 database: full v3 tables, version marker 3.
        self.store.store_return_features([{"symbol": "BTCUSDT"}])
        self.store.close()
        with self.store._get_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES ('schema_version', '3')")
        reopened = PersistenceStore(db_path=self.db_path)
        reopened.init_db()
        with reopened._get_cursor() as cursor:
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 7)
            for table in ("flow_features", "flow_buckets",
                          "book_features", "oi_samples", "oi_features",
                          "structure_features"):
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,))
                self.assertIsNotNone(cursor.fetchone(), table)
        # P1-05 rows survive the migration.
        self.assertEqual(len(reopened.latest_return_features()), 1)
        reopened.close()

    def test_v4_database_migrates_to_v7_preserving_rows(self) -> None:
        # Simulate a P1-06 database: v4 tables with flow rows, marker 4.
        self.store.store_flow_features([{"symbol": "BTCUSDT"}])
        self.store.close()
        with self.store._get_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES ('schema_version', '4')")
        reopened = PersistenceStore(db_path=self.db_path)
        reopened.init_db()
        with reopened._get_cursor() as cursor:
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 7)
            for table in ("book_features", "oi_samples", "oi_features",
                          "structure_features"):
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,))
                self.assertIsNotNone(cursor.fetchone(), table)
        # P1-06 rows survive the migration.
        self.assertEqual(len(reopened.latest_flow_features()), 1)
        reopened.close()

    def test_v5_database_migrates_to_v7_preserving_rows(self) -> None:
        # Simulate a P1-07 database: v5 tables with book rows, marker 5.
        self.store.store_book_features([{"symbol": "BTCUSDT"}])
        self.store.close()
        with self.store._get_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES ('schema_version', '5')")
        reopened = PersistenceStore(db_path=self.db_path)
        reopened.init_db()
        with reopened._get_cursor() as cursor:
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 7)
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                ("structure_features",))
            self.assertIsNotNone(cursor.fetchone())
        # P1-07 rows survive the migration.
        self.assertEqual(len(reopened.latest_book_features()), 1)
        reopened.close()

    def test_v6_database_migrates_to_v7_preserving_rows(self) -> None:
        # Simulate a P1-11C database: v6 tables with structure rows, marker 6.
        self.store.store_structure_features([{"symbol": "BTCUSDT"}])
        self.store.close()
        with self.store._get_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES ('schema_version', '6')")
        reopened = PersistenceStore(db_path=self.db_path)
        reopened.init_db()
        with reopened._get_cursor() as cursor:
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 7)
            for table in ("state_features", "state_transitions"):
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,))
                self.assertIsNotNone(cursor.fetchone(), table)
        # P1-11C rows survive the migration.
        self.assertEqual(len(reopened.latest_structure_features()), 1)
        reopened.close()

    def test_state_features_replace_and_transitions_bounded(self) -> None:
        self.store.store_state_features([
            {"symbol": "BTCUSDT", "state": "NORMAL",
             "direction": "NONE"}])
        self.store.store_state_features([
            {"symbol": "BTCUSDT", "state": "IGNITION",
             "direction": "UP"}])
        rows = self.store.latest_state_features()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["state"], "IGNITION")
        for _ in range(5):
            self.store.log_state_transition(
                "BTCUSDT", "NORMAL", "IGNITION", "NONE", "UP", "test")
        self.assertEqual(len(self.store.state_transitions(limit=50)), 5)

    def test_discovery_snapshot_replace_and_read(self) -> None:
        self.assertIsNone(self.store.latest_discovery())
        payload = {"eligible_count": 500, "hot_dynamic": ["XRPUSDT"]}
        self.store.store_discovery_snapshot(payload)
        self.assertEqual(self.store.latest_discovery(), payload)
        payload2 = {"eligible_count": 501, "hot_dynamic": []}
        self.store.store_discovery_snapshot(payload2)
        self.assertEqual(self.store.latest_discovery(), payload2)

    def test_universe_events_bounded_log(self) -> None:
        for i in range(505):
            self.store.log_universe_event("promoted", f"S{i}USDT", "test")
        events = self.store.universe_events(limit=600)
        self.assertEqual(len(events), 500)
        self.assertEqual(events[0]["symbol"], "S504USDT")
        self.assertEqual(events[0]["kind"], "promoted")

    def test_rank_snapshots_replace_per_metric(self) -> None:
        self.assertEqual(self.store.latest_ranks(), {})
        self.store.store_rank_snapshot("velocity_1m", {"A": {"rank": 1}})
        self.store.store_rank_snapshot("velocity_1m", {"A": {"rank": 2}})
        ranks = self.store.latest_ranks()
        self.assertEqual(ranks, {"velocity_1m": {"A": {"rank": 2}}})

    def test_price_samples_round_trip_and_restart(self) -> None:
        import time as _time

        base = (int(_time.time() * 1000) // 10_000) * 10_000 - 30_000
        rows = [("BTCUSDT", base, 100.5), ("BTCUSDT", base + 10_000, 101.0)]
        self.store.store_price_samples(rows)
        self.assertEqual(self.store.load_price_samples("BTCUSDT"), rows)
        self.store.close()
        reopened = PersistenceStore(db_path=self.db_path)
        reopened.init_db()
        self.assertEqual(reopened.load_price_samples("BTCUSDT"), rows)
        reopened.close()

    def test_return_features_replace_per_symbol(self) -> None:
        self.store.store_return_features([
            {"symbol": "BTCUSDT", "current_price": 100.0, "returns": {"1m": 0.01}}])
        self.store.store_return_features([
            {"symbol": "BTCUSDT", "current_price": 101.0, "returns": {"1m": 0.02}},
            {"symbol": "ETHUSDT", "current_price": 50.0, "returns": {"1m": None}}])
        latest = self.store.latest_return_features()
        by_symbol = {f["symbol"]: f for f in latest}
        self.assertEqual(set(by_symbol), {"BTCUSDT", "ETHUSDT"})
        self.assertEqual(by_symbol["BTCUSDT"]["current_price"], 101.0)
        self.assertIsNone(by_symbol["ETHUSDT"]["returns"]["1m"])


if __name__ == "__main__":
    unittest.main()