"""Research-bucket linkage: run_id, versions, as_of, source, dataset.

Proves on TEMP resources exclusively (never the canonical DBs):
- Fresh stores initialize at history schema v3 with linkage columns.
- v2 -> v3 migration on synthetic v2 and on a synthetic v2-shaped TEMP
  fixture (built by the real v3 DDL, structurally downgraded): version
  bumps, row counts preserved, pre-existing rows keep NULL (= UNKNOWN,
  never backfilled).
- Recorder end-to-end stamps run_id/rules_version/as_of/price_source/
  dataset_id at flush; absent context stays NULL.
- Probe threads its run_id + engine versions into its recorder.
- Event time vs close time vs availability stay distinct (as_of >=
  bucket_end; first/last_event_ms inside the bucket window).

2026-10-14: decoupled from canonical evolution — the old temp-copy-of-
canonical test broke on the live v3 store (linkage rows present). The
v2-shaped fixture makes the suite green on any canonical state without
reading, modifying, or rolling back original databases.
Run: python run_tests.py
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from microstructure_probe.history_store import HistoryStore, SCHEMA_VERSION

LINKED_TABLES = ("research_flow_10s", "research_flow_1m", "research_book_1m")
LINKED_COLS = ("run_id", "rules_version", "as_of_ms", "price_source",
               "dataset_id")


def _dummy(coltype: str, tag: str, n: int):
    t = (coltype or "").upper()
    if "INT" in t:
        return 1000 + n
    if "CHAR" in t or "CLOB" in t or "TEXT" in t:
        return "%s-%d" % (tag, n)
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return 2.5 + n
    return None


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


def _temp_hist(case, name="hist.db"):
    tmp = Path(tempfile.mkdtemp(prefix="reslink_"))
    case.addCleanup(lambda: _rmtree(tmp))
    store = HistoryStore(tmp / name)
    store.init_db()
    return store, tmp


class SchemaV3Test(unittest.TestCase):
    def test_fresh_init_is_v3_with_linkage_columns(self) -> None:
        store, _ = _temp_hist(self)
        self.assertEqual(SCHEMA_VERSION, 3)
        self.assertEqual(store.schema_version(), 3)
        con = sqlite3.connect(str(store.db_path))
        try:
            for table in LINKED_TABLES:
                cols = {r[1] for r in con.execute(
                    "PRAGMA table_info(%s)" % table).fetchall()}
                for col in LINKED_COLS:
                    self.assertIn(col, cols, "%s.%s" % (table, col))
        finally:
            con.close()

    def test_v2_synthetic_migrates_without_backfill(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="reslink_v2_"))
        self.addCleanup(lambda: _rmtree(tmp))
        path = tmp / "v2.db"
        con = sqlite3.connect(str(path))
        try:
            con.execute("CREATE TABLE history_meta (key TEXT PRIMARY KEY,"
                        " value TEXT NOT NULL)")
            con.execute("INSERT INTO history_meta VALUES"
                        " ('schema_version', '2')")
            con.execute("CREATE TABLE research_flow_10s (symbol TEXT NOT"
                        " NULL, bucket_start INTEGER NOT NULL,"
                        " bucket_end INTEGER NOT NULL,"
                        " PRIMARY KEY (symbol, bucket_start))")
            con.execute("INSERT INTO research_flow_10s"
                        " (symbol, bucket_start, bucket_end)"
                        " VALUES ('BTCUSDT', 1000, 11000)")
            con.commit()
        finally:
            con.close()
        store = HistoryStore(path)
        store.init_db()
        self.assertEqual(store.schema_version(), 3)
        con = sqlite3.connect(str(path))
        try:
            row = con.execute("SELECT run_id, rules_version, as_of_ms,"
                              " price_source, dataset_id"
                              " FROM research_flow_10s").fetchone()
            self.assertEqual(row, (None, None, None, None, None))
        finally:
            con.close()

    def test_v2_shape_migrates_preserving_rows(self) -> None:
        # Synthetic v2-shaped fixture on TEMP only: real v3 DDL builds the
        # tables, rows are inserted, then linkage columns are structurally
        # dropped and the version restamped to 2. init_db must bring it
        # back to v3 with counts preserved and pre-existing linkage NULL.
        tmp = Path(tempfile.mkdtemp(prefix="reslink_v2shape_"))
        self.addCleanup(lambda: _rmtree(tmp))
        path = tmp / "v2shape.db"
        seed = HistoryStore(path)
        seed.init_db()
        con = sqlite3.connect(str(path))
        try:
            for table in LINKED_TABLES:
                info = con.execute(
                    "PRAGMA table_info(%s)" % table).fetchall()
                cols = [(r[1], r[2]) for r in info
                        if r[1] not in LINKED_COLS]
                for n in range(3):
                    vals = [_dummy(t, table, n) for _, t in cols]
                    con.execute(
                        "INSERT INTO %s (%s) VALUES (%s)"
                        % (table, ",".join(c for c, _ in cols),
                           ",".join("?" * len(cols))), vals)
            con.commit()
        finally:
            con.close()
        con = sqlite3.connect(str(path))
        try:
            for table in LINKED_TABLES:
                for col in LINKED_COLS:
                    con.execute("ALTER TABLE %s DROP COLUMN %s"
                                % (table, col))
            con.execute("UPDATE history_meta SET value='2'"
                        " WHERE key='schema_version'")
            con.commit()
        finally:
            con.close()
        store = HistoryStore(path)
        store.init_db()
        self.assertEqual(store.schema_version(), 3)
        con = sqlite3.connect(str(path))
        try:
            for table in LINKED_TABLES:
                n = con.execute(
                    "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
                self.assertEqual(n, 3, table)
                leaked = con.execute(
                    "SELECT COUNT(*) FROM %s WHERE run_id IS NOT NULL"
                    " OR rules_version IS NOT NULL OR as_of_ms IS NOT NULL"
                    " OR price_source IS NOT NULL OR dataset_id IS NOT NULL"
                    % table).fetchone()[0]
                self.assertEqual(leaked, 0, table)
        finally:
            con.close()


class RecorderLinkageTest(unittest.TestCase):
    def _recorder(self, **kw):
        import tempfile as _tf
        from microstructure_probe.research_recorder import ResearchRecorder

        tmp = Path(_tf.mkdtemp(prefix="reslink_rec_"))
        self.addCleanup(lambda: _rmtree(tmp))
        db = tmp / "h.db"
        params = dict(db_path=db, enabled=True, run_id="RUN-7",
                      rules_version="classifier-v0.1.0+opportunity-v0.1.0",
                      dataset_id=None)
        params.update(kw)
        return ResearchRecorder(**params), tmp

    def test_flush_stamps_linkage_context(self) -> None:
        rec, tmp = self._recorder()
        base = 1_700_000_000_000 - (1_700_000_000_000 % 60_000)
        rec.record_trade("TSTUSDT", base, 100.0, 1.0, False)
        rec.record_trade("TSTUSDT", base + 15_000, 101.0, 1.0, False)
        rec.start()
        try:
            status = rec.stop_and_drain(timeout=10.0)
        finally:
            if rec._thread is not None:
                rec._thread.join(timeout=5.0)
        self.assertEqual(status["errors"], 0)
        self.assertGreaterEqual(status["writes"], 1)
        con = sqlite3.connect(str(tmp / "h.db"))
        try:
            row = con.execute(
                "SELECT run_id, rules_version, as_of_ms, price_source,"
                " dataset_id, bucket_start, bucket_end, first_event_ms,"
                " last_event_ms FROM research_flow_10s").fetchone()
        finally:
            con.close()
        self.assertIsNotNone(row)
        run_id, rules, as_of, source, ds, bstart, bend, first, last = row
        self.assertEqual(run_id, "RUN-7")
        self.assertEqual(rules, "classifier-v0.1.0+opportunity-v0.1.0")
        self.assertIsNone(ds)  # unbound study: UNKNOWN, not invented
        self.assertEqual(source, "aggTrade")
        # Availability (flush wall time) is at/after bucket close; event
        # times stay inside the bucket window. Distinct quantities.
        self.assertGreaterEqual(as_of, bend)
        self.assertGreaterEqual(first, bstart)
        self.assertLessEqual(last, bend)

    def test_absent_context_stays_null(self) -> None:
        import tempfile as _tf
        from microstructure_probe.research_recorder import ResearchRecorder

        tmp = Path(_tf.mkdtemp(prefix="reslink_null_"))
        self.addCleanup(lambda: _rmtree(tmp))
        rec = ResearchRecorder(db_path=tmp / "h.db", enabled=True)
        base = 1_700_000_000_000 - (1_700_000_000_000 % 60_000)
        rec.record_trade("TSTUSDT", base, 100.0, 1.0, False)
        rec.record_trade("TSTUSDT", base + 15_000, 101.0, 1.0, False)
        rec.start()
        try:
            rec.stop_and_drain(timeout=10.0)
        finally:
            if rec._thread is not None:
                rec._thread.join(timeout=5.0)
        con = sqlite3.connect(str(tmp / "h.db"))
        try:
            row = con.execute("SELECT run_id, rules_version, dataset_id"
                              " FROM research_flow_10s").fetchone()
            src = con.execute("SELECT price_source FROM research_flow_10s"
                              ).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(row, (None, None, None))
        # Price source is mechanical (which stream fed the bucket), not
        # contextual: always stamped.
        self.assertEqual(src, "aggTrade")

    def test_probe_threads_linkage_into_recorder(self) -> None:
        from test_detectors import test_config
        from microstructure_probe.history_store import HistoryStore
        from microstructure_probe.persistence import PersistenceStore
        from microstructure_probe.probe import MarketProbe
        import tempfile as _tf

        tmp = Path(_tf.mkdtemp(prefix="reslink_probe_"))
        self.addCleanup(lambda: _rmtree(tmp))
        store = PersistenceStore(tmp / "probe.db")
        store.init_db()
        self.addCleanup(store.close)
        hist = HistoryStore(tmp / "historical.db")
        probe = MarketProbe(test_config(), persistence_store=store,
                            research_history_store=hist)
        self.assertEqual(probe._research.run_id, probe.run_id)
        self.assertIn("classifier-v0.1.0",
                      probe._research.rules_version or "")
        self.assertIn("opportunity-v0.1.0",
                      probe._research.rules_version or "")
        self.assertIsNone(probe._research.dataset_id)


if __name__ == "__main__":
    unittest.main()
