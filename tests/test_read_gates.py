"""Read gates: explicit table/column/version contracts (temp DBs only).

Proves absent tables/columns/versions fail closed naming them, v10/v3
pass, provenance absences stay UNKNOWN, and nothing here migrates or
writes. Run: python run_tests.py
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from microstructure_probe import read_gates as rg


def _db() -> sqlite3.Connection:
    path = Path(tempfile.mkdtemp(prefix="gates_")) / "g.db"
    con = sqlite3.connect(str(path))
    con.execute("create table persistence_meta(key text, value text)")
    con.execute("insert into persistence_meta values "
                "('schema_version', '10')")
    con.execute("create table return_features(symbol text, x real)")
    return con


class TableGateTest(unittest.TestCase):
    def test_present_tables_pass(self) -> None:
        con = _db()
        try:
            rg.require_tables(con, ["return_features"], "op")
        finally:
            con.close()

    def test_absent_table_names_it(self) -> None:
        con = _db()
        try:
            with self.assertRaises(rg.ReadGateError) as ctx:
                rg.require_tables(con, ["return_features", "nope"], "op")
            self.assertIn("nope", str(ctx.exception))
        finally:
            con.close()

    def test_absent_column_names_it(self) -> None:
        con = _db()
        try:
            rg.require_columns(con, "return_features", ["symbol"], "op")
            with self.assertRaises(rg.ReadGateError) as ctx:
                rg.require_columns(con, "return_features",
                                   ["symbol", "run_id"], "op")
            self.assertIn("run_id", str(ctx.exception))
        finally:
            con.close()


class VersionGateTest(unittest.TestCase):
    def test_v10_v3_pass(self) -> None:
        self.assertEqual(rg.check_operational_version("10"), "10")
        self.assertEqual(rg.check_historical_version("3"), "3")

    def test_old_and_absent_fail_closed(self) -> None:
        for bad in ("9", "2", None, "99"):
            with self.subTest(bad=bad):
                with self.assertRaises(rg.ReadGateError):
                    rg.check_operational_version(bad)
                with self.assertRaises(rg.ReadGateError):
                    rg.check_historical_version(bad)

    def test_meta_lookup_never_raises(self) -> None:
        con = _db()
        try:
            self.assertEqual(rg.meta_value(con, "persistence_meta",
                                          "schema_version"), "10")
            self.assertIsNone(rg.meta_value(con, "missing", "schema_version"))
        finally:
            con.close()


class ProvenanceTest(unittest.TestCase):
    def test_absent_stays_unknown(self) -> None:
        p = rg.provenance()
        self.assertTrue(all(v == "UNKNOWN" for v in p.values()))

    def test_present_preserved(self) -> None:
        p = rg.provenance(run_id="r1", rules_version="H1-v1", as_of_ms=7,
                          source="m", dataset_id="d")
        self.assertEqual(p["run_id"], "r1")
        self.assertEqual(p["as_of_ms"], 7)


if __name__ == "__main__":
    unittest.main()
