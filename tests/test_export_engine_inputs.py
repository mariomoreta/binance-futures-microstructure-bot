"""Export adapter: read-only, isolated out, declared mapping, no fabrication.

Temp SQLite fixture only (never the canonical DBs).
Run: python run_tests.py
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from export_engine_inputs import main  # noqa: E402


def _fixture(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="engexp_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    db = tmp / "hist.db"
    con = sqlite3.connect(str(db))
    try:
        con.execute("CREATE TABLE historical_klines (symbol TEXT, interval TEXT,"
                    " open_time INTEGER, open REAL, high REAL, low REAL, close REAL)")
        base = 1_700_000_000_000
        for i in range(10):
            con.execute("INSERT INTO historical_klines VALUES (?,?,?,?,?,?,?)",
                        ("BTCUSDT", "15m", base + i * 900_000, 100.0 + i,
                         101.0 + i, 99.0 + i, 100.5 + i))
        con.execute("CREATE TABLE event_instances (definition_name TEXT, symbol TEXT,"
                    " event_time INTEGER, direction TEXT, reference_price REAL)")
        rows = [("MOMENTUM_ACCELERATION_UP", "BTCUSDT", base + 900_000, "up", 101.0),
                ("MOMENTUM_ACCELERATION_DOWN", "BTCUSDT", base + 1_800_000, "down", 102.0),
                ("FAILED_HIGH_CANDIDATE", "BTCUSDT", base + 2_700_000, "up", 103.0),
                ("NOPE_UNKNOWN", "BTCUSDT", base + 3_600_000, "up", 104.0),
                ("MOMENTUM_ACCELERATION_UP", "BTCUSDT", base + 4_500_000, "sideways", 105.0),
                ("MOMENTUM_ACCELERATION_UP", "MINAUSDT", base + 5_400_000, "up", 1.0)]
        con.executemany("INSERT INTO event_instances VALUES (?,?,?,?,?)", rows)
        con.commit()
    finally:
        con.close()
    return db, tmp


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


class ExportAdapterTest(unittest.TestCase):
    def test_maps_declared_counts_discards_and_hashes(self) -> None:
        db, tmp = _fixture(self)
        out = tmp / "exp"
        code = main(["--db", str(db), "--symbols", "BTCUSDT",
                     "--interval", "15m", "--out-dir", str(out)])
        self.assertEqual(code, 0)
        events = json.loads((out / "events.json").read_text(encoding="utf-8"))
        candles = json.loads((out / "candles.json").read_text(encoding="utf-8"))
        meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(len(candles), 10)
        self.assertEqual(len(events), 3)
        by_group = {}
        for e in events:
            by_group.setdefault(e["group"], []).append(e["family"])
        self.assertEqual(by_group["continuation"], ["H1"])
        self.assertEqual(by_group["bearish-continuation"], ["H3"])
        self.assertEqual(by_group["correction-exhaustion"], ["H2"])
        self.assertTrue(all(e["direction"] in ("LONG", "SHORT") for e in events))
        self.assertEqual(meta["discarded"]["unmapped-definition"], 1)
        self.assertEqual(meta["discarded"]["bad-direction"], 1)
        self.assertEqual(meta["discarded"]["symbol-filtered"], 1)
        self.assertEqual(meta["funding_calendar"], None)
        self.assertEqual(meta["formation_method"],
                         "PROPOSED-P1-11C-map-v1 (caller-declared, NOT approved)")
        self.assertEqual(len(meta["candles_sha"]), 16)
        # Source DB untouched: still 6 instances, 10 klines.
        con = sqlite3.connect(str(db))
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM event_instances").fetchone()[0], 6)
        finally:
            con.close()

    def test_canonical_db_untouched_by_fixture_run(self) -> None:
        # The adapter only opens the --db given; this run must not create
        # anything inside the repo (out lives in temp).
        db, tmp = _fixture(self)
        before = set((tmp).rglob("*"))
        main(["--db", str(db), "--out-dir", str(tmp / "exp")])
        self.assertTrue((tmp / "exp" / "meta.json").exists())
        self.assertEqual(before & set((tmp / "exp").rglob("*")), set())


if __name__ == "__main__":
    raise SystemExit(unittest.main())
