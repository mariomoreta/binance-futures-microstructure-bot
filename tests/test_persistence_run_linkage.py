"""P3 run linkage: execution -> observation -> persistence -> rehydration.

Proves on TEMP resources exclusively (never the canonical DBs):
- Fresh stores initialize at schema v10 with nullable run_id columns.
- v9 -> v10 migration on a synthetic v9-shaped TEMP fixture (built by
  the real v10 DDL, structurally downgraded): version bumps, row counts
  preserved, pre-existing rows keep run_id NULL (UNKNOWN, never
  backfilled), new writes stamp the current run.
- Probe executions carry distinct run_ids; universe events, snapshots
  and prospective rows written by a run carry its id (propagation).
- Rehydration reloads stamped rows; runs never share ids (separation).

2026-10-14: decoupled from canonical evolution — the old temp-copy-of-
canonical test pinned canonical at v9 and broke on the live v10 store.
Versioned fixtures make the suite green on any canonical state without
reading, modifying, or rolling back original databases.
Run: python run_tests.py
"""

from __future__ import annotations

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from microstructure_probe.persistence import PersistenceStore

RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")
LINKED_TABLES = ("universe_events", "prospective_setups",
                 "prospective_outcomes", "telemetry_snapshots")


def _dummy(coltype: str, tag: str, n: int):
    t = (coltype or "").upper()
    if "INT" in t:
        return n + 1
    if "CHAR" in t or "CLOB" in t or "TEXT" in t:
        return "%s-%d" % (tag, n)
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return 1.5 + n
    return None


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

    def test_v9_shape_migrates_preserving_rows_without_backfill(self) -> None:
        # Synthetic v9-shaped fixture on TEMP only: real v10 DDL builds the
        # tables, rows are inserted, then run_id is structurally dropped and
        # the version restamped to 9. init_db must bring it back to v10
        # with counts preserved and pre-existing run_id NULL (no backfill).
        tmp = Path(tempfile.mkdtemp(prefix="runlink_v9shape_"))
        self.addCleanup(lambda: _rmtree(tmp))
        path = tmp / "v9shape.db"
        seed = PersistenceStore(path)
        seed.init_db()
        with seed._get_cursor() as cursor:
            for table in LINKED_TABLES + ("market_observations",):
                cursor.execute("PRAGMA table_info(%s)" % table)
                cols = [(r[1], r[2]) for r in cursor.fetchall()
                        if r[1] != "run_id"]
                for n in range(3):
                    vals = [_dummy(t, table, n) for _, t in cols]
                    cursor.execute(
                        "INSERT INTO %s (%s) VALUES (%s)"
                        % (table, ",".join(c for c, _ in cols),
                           ",".join("?" * len(cols))), vals)
        seed.close()
        con = sqlite3.connect(str(path))
        try:
            for table in LINKED_TABLES:
                con.execute("ALTER TABLE %s DROP COLUMN run_id" % table)
            con.execute("UPDATE persistence_meta SET value='9'"
                        " WHERE key='schema_version'")
            con.commit()
        finally:
            con.close()
        before = {}
        store = PersistenceStore(path)
        store.init_db()
        self.addCleanup(store.close)
        with store._get_cursor() as cursor:
            cursor.execute("SELECT value FROM persistence_meta"
                           " WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 10)
            for table in LINKED_TABLES + ("market_observations",):
                cursor.execute("SELECT COUNT(*) FROM %s" % table)
                n = cursor.fetchone()[0]
                before[table] = n
                self.assertEqual(n, 3, table)
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
