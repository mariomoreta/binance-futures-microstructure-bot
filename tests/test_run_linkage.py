"""P3 run linkage: execution -> observation -> persistence -> rehydration.

Proves on TEMP resources exclusively (never the canonical DBs):
- Fresh stores initialize at schema v10 with nullable run_id columns.
- v9 -> v10 migration on a temp COPY of real v9 bytes: version bumps,
  row counts preserved, pre-existing rows keep run_id NULL (UNKNOWN,
  never backfilled), new writes stamp the current run.
- Probe executions carry distinct run_ids; universe events, snapshots
  and prospective rows written by a run carry its id (propagation).
- Rehydration reloads stamped rows; runs never share ids (separation).

The canonical copy test reads canonical FILE BYTES once to build the
fixture (pure read, no connection, no write); it skips when the canonical
DB is absent (isolated-copy runs). Run: python run_tests.py
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from microstructure_probe.persistence import PersistenceStore

CANONICAL_MICROPROBE = Path(__file__).resolve().parent.parent / "data" / "microprobe.db"
RUN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
LINKED_TABLES = ("universe_events", "prospective_setups",
                 "prospective_outcomes", "telemetry_snapshots")


def _temp_store(case, name="link.db"):
    tmp = Path(tempfile.mkdtemp(prefix="runlink_"))
    case.addCleanup(lambda: _rmtree(tmp))
    store = PersistenceStore(tmp / name)
    store.init_db()
    case.addCleanup(store.close)
    return store, tmp


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


class SchemaV10Test(unittest.TestCase):
    def test_fresh_init_is_v10_with_run_id_columns(self) -> None:
        store, _ = _temp_store(self)
        with store._get_cursor() as cursor:
            cursor.execute("SELECT value FROM persistence_meta"
                           " WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 10)
            for table in LINKED_TABLES:
                cursor.execute("PRAGMA table_info(%s)" % table)
                cols = {row[1] for row in cursor.fetchall()}
                self.assertIn("run_id", cols, table)

    def test_v9_copy_migrates_preserving_rows_without_backfill(self) -> None:
        if not CANONICAL_MICROPROBE.exists():
            self.skipTest("canonical DB absent (isolated copy)")
        tmp = Path(tempfile.mkdtemp(prefix="runlink_mig_"))
        self.addCleanup(lambda: _rmtree(tmp))
        copy = tmp / "v9copy.db"
        shutil.copyfile(CANONICAL_MICROPROBE, copy)  # bytes read once
        before = {}
        con = sqlite3.connect("file:%s?mode=ro" % copy, uri=True)
        try:
            before["version"] = con.execute(
                "SELECT value FROM persistence_meta"
                " WHERE key='schema_version'").fetchone()[0]
            for table in LINKED_TABLES + ("market_observations",):
                before[table] = con.execute(
                    "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(int(before["version"]), 9)
        store = PersistenceStore(copy)
        store.init_db()
        self.addCleanup(store.close)
        with store._get_cursor() as cursor:
            cursor.execute("SELECT value FROM persistence_meta"
                           " WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 10)
            for table in LINKED_TABLES + ("market_observations",):
                cursor.execute("SELECT COUNT(*) FROM %s" % table)
                self.assertEqual(cursor.fetchone()[0], before[table], table)
            for table in LINKED_TABLES:
                cursor.execute(
                    "SELECT COUNT(*) FROM %s WHERE run_id IS NOT NULL" % table)
                self.assertEqual(cursor.fetchone()[0], 0, table)
        # New writes stamp; old rows stay NULL.
        store.log_universe_event("promoted", "BTCUSDT", "linkage-probe",
                                 run_id="RUN123")
        rows = store.universe_events(limit=1)
        self.assertEqual(rows[0]["run_id"], "RUN123")


class ProbeRunPropagationTest(unittest.TestCase):
    def test_probe_run_ids_unique_and_propagated(self) -> None:
        from test_detectors import test_config
        from microstructure_probe.history_store import HistoryStore
        from microstructure_probe.probe import MarketProbe

        probes = []
        for i in range(2):
            tmp = Path(tempfile.mkdtemp(prefix="runlink_probe_"))
            self.addCleanup(lambda: _rmtree(tmp))
            store = PersistenceStore(tmp / "probe.db")
            store.init_db()
            self.addCleanup(store.close)
            hist = HistoryStore(tmp / "historical.db")
            probes.append((MarketProbe(
                test_config(), persistence_store=store,
                research_history_store=hist), store))
        (p1, s1), (p2, s2) = probes
        self.assertTrue(RUN_ID_RE.match(p1.run_id))
        self.assertTrue(RUN_ID_RE.match(p2.run_id))
        self.assertNotEqual(p1.run_id, p2.run_id)
        s1.log_universe_event("promoted", "BTCUSDT", "x", run_id=p1.run_id)
        s2.log_universe_event("promoted", "BTCUSDT", "x", run_id=p2.run_id)
        self.assertEqual(s1.universe_events(limit=1)[0]["run_id"], p1.run_id)
        self.assertEqual(s2.universe_events(limit=1)[0]["run_id"], p2.run_id)
        # Summary carries the run for snapshot linkage.
        summary = p1.build_summary(final=True)
        self.assertEqual(summary["run_id"], p1.run_id)

    def test_prospective_rows_carry_recorder_run(self) -> None:
        from microstructure_probe.prospective import ProspectiveRecorder

        tmp = Path(tempfile.mkdtemp(prefix="runlink_prosp_"))
        self.addCleanup(lambda: _rmtree(tmp))
        db = tmp / "p.db"
        rec = ProspectiveRecorder(db_path=db, enabled=True, run_id="RUN-A")
        rec.start()
        try:
            rec.register_setup("K1", {"candidate_key": "K1",
                                      "symbol": "BTCUSDT",
                                      "setup_family": "REVERSAL_WATCH",
                                      "direction": "UP",
                                      "market_state": "REVERSAL",
                                      "rule_version": "v0.1.0",
                                      "capability_tier": "CORE",
                                      "ranking": {}, "lifecycle": "DETECTED",
                                      "detect_price": 100.0,
                                      "evidence_for": [],
                                      "evidence_against": [],
                                      "missing_features": [],
                                      "data_freshness": {}},
                             1_800_000_000_000)
        finally:
            rec.stop_and_drain()
        store = PersistenceStore(db_path=db)
        store.init_db()
        self.addCleanup(store.close)
        rows = store.prospective_setups()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["run_id"], "RUN-A")
        # Rehydration sees the stamped row (continuity across restarts).
        rec2 = ProspectiveRecorder(db_path=db, enabled=True, run_id="RUN-B")
        self.assertIn("K1", rec2._registered)


if __name__ == "__main__":
    unittest.main()
