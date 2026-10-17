"""Causal census: deterministic IDs, prefix/invariance, close_time availability.

Synthetic temp-DB fixtures only (never the canonical DBs).
Run: python run_tests.py
"""

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import reconstruct_causal_census as census  # noqa: E402

STEP = 900_000
BASE = 1_780_000_000_000


def _prices(n=40):
    """Engineered drift: mild rise, spike high at bar 22, closebacks 23-25."""
    closes = []
    c = 100.0
    for i in range(n):
        g = 0.0008 if i < 22 else 0.003
        c = c * (1 + g)
        closes.append(c)
    spike = closes[21] * 1.01
    for i in (23, 24, 25):
        closes[i] = spike * 0.9985
    highs = [max(closes[i], closes[i - 1] if i else closes[i]) * 1.0005
             for i in range(n)]
    lows = [min(closes[i], closes[i - 1] if i else closes[i]) * 0.9995
            for i in range(n)]
    highs[22] = spike
    lows[22] = closes[21] * 0.999
    return closes, highs, lows


def _fixture(testcase, close_fn=None, with_original=False):
    tmp = Path(tempfile.mkdtemp(prefix="census_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    db = tmp / "hist.db"
    closes, highs, lows = _prices()
    con = sqlite3.connect(str(db))
    try:
        con.execute("CREATE TABLE historical_klines (symbol TEXT, interval TEXT,"
                    " open_time INTEGER, open REAL, high REAL, low REAL,"
                    " close REAL, close_time INTEGER, quote_volume REAL,"
                    " taker_buy_base REAL, taker_buy_quote REAL)")
        for i in range(40):
            ot = BASE + i * STEP
            ct = close_fn(ot, i) if close_fn else ot + STEP - 1
            con.execute("INSERT INTO historical_klines VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        ("BTCUSDT", "15m", ot, closes[i], highs[i], lows[i],
                         closes[i], ct, 1_000_000.0, 500.0, 500_000.0))
        con.execute("CREATE TABLE event_instances (event_id TEXT,"
                    " definition_name TEXT, definition_version INTEGER,"
                    " symbol TEXT, event_time INTEGER, source_interval TEXT)")
        if with_original:
            con.execute("INSERT INTO event_instances VALUES (?,?,?,?,?,?)",
                        ("ORIG-1", "FAILED_HIGH_CANDIDATE", 1, "BTCUSDT",
                         BASE + 23 * STEP, "15m"))
        con.commit()
    finally:
        con.close()
    return db, tmp


def _rmtree(path: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        try:
            child.unlink() if child.is_file() else child.rmdir()
        except OSError:
            pass
    try:
        path.rmdir()
    except OSError:
        pass


def _run(db, tmp, extra=()):
    out = tmp / "out"
    rc = census.main(["--symbols", "BTCUSDT", "--intervals", "15m",
                      "--out-dir", str(out), "--db", str(db), *extra])
    assert rc == 0, rc
    dets = [json.loads(line) for line in
            (out / "detections.jsonl").read_text().splitlines() if line.strip()]
    summary = json.loads((out / "summary.json").read_text())
    return dets, summary


class CausalCensusTest(unittest.TestCase):
    def test_fires_and_deterministic_ids(self):
        db, tmp = _fixture(self)
        d1, _ = _run(db, tmp)
        d2, _ = _run(db, tmp)
        self.assertGreater(len(d1), 0)
        self.assertEqual([d["census_id"] for d in d1],
                         [d["census_id"] for d in d2])
        fams = {d["definition_name"] for d in d1}
        self.assertIn("FAILED_HIGH_CANDIDATE", fams)
        self.assertIn("MOMENTUM_ACCELERATION_UP", fams)

    def test_prefix_and_invariance_on_fixture(self):
        db, tmp = _fixture(self)
        _, summary = _run(db, tmp, ("--prefix-check",))
        self.assertGreater(len(summary["prefix_report"]), 0)
        for cell, rep in summary["prefix_report"].items():
            self.assertTrue(rep["prefix_equal"], cell)
            self.assertTrue(rep["later_mutation_invariant"], cell)

    def test_available_from_close_time_same_grid_entry(self):
        db, tmp = _fixture(self)
        dets, _ = _run(db, tmp)
        for d in dets:
            self.assertIsNotNone(d["available_at"])
            self.assertEqual(d["available_at"], d["formation_time"] + STEP - 1)
            self.assertIsNone(d["decision_time"])
            if d["entry_time_same_grid"] is not None:
                self.assertEqual(d["entry_time_same_grid"] % STEP, BASE % STEP)
                self.assertGreaterEqual(d["entry_time_same_grid"],
                                        d["available_at"])

    def test_chain_violation_discarded_with_reason(self):
        def late_close(ot, i):
            if i == 23:
                return ot + STEP + 5000  # past the next open
            return ot + STEP - 1
        db, tmp = _fixture(self, close_fn=late_close)
        dets, summary = _run(db, tmp)
        self.assertGreater(summary["n_discarded"], 0)
        reasons = set()
        for d in dets:
            if not d["chain_ok"]:
                reasons.add(d["chain_reason"])
                self.assertEqual(d["formation_time"], BASE + 23 * STEP)
        self.assertIn("chain-violation", reasons)

    def test_no_cross_resolution_without_rule(self):
        db, tmp = _fixture(self)  # fixture carries 15m rows only
        out = tmp / "out1h"
        rc = census.main(["--symbols", "BTCUSDT", "--intervals", "1h",
                          "--out-dir", str(out), "--db", str(db)])
        self.assertEqual(rc, 0)
        summary = json.loads((out / "summary.json").read_text())
        self.assertEqual(summary["n_detections"], 0)
        self.assertEqual(summary["per_cell"]["BTCUSDT/1h"]["status"], "no-series")

    def test_originals_preserved_and_duplicates_counted(self):
        db, tmp = _fixture(self, with_original=True)
        dets, summary = _run(db, tmp)
        matched = [d for d in dets if d["original_event_id"] == "ORIG-1"]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["definition_name"], "FAILED_HIGH_CANDIDATE")
        # MOM_UP + FAILED_HIGH share formation bar 23 -> duplicate group
        self.assertGreaterEqual(summary["duplicate_groups"], 1)


if __name__ == "__main__":
    unittest.main()
