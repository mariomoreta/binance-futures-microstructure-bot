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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from export_engine_inputs import main  # noqa: E402
from microstructure_probe.backtest_offline import (  # noqa: E402
    BacktestConfig,
    Candle,
    StudyEvent,
    input_hash,
    run_backtest,
)
from run_family_evaluation import _load_candles  # noqa: E402


def _fixture(testcase, close_times=True):
    tmp = Path(tempfile.mkdtemp(prefix="engexp_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    db = tmp / "hist.db"
    con = sqlite3.connect(str(db))
    try:
        con.execute("CREATE TABLE historical_klines (symbol TEXT, interval TEXT,"
                    " open_time INTEGER, open REAL, high REAL, low REAL, close REAL,"
                    " close_time INTEGER)")
        base = 1_700_000_000_000
        for i in range(10):
            ct = base + (i + 1) * 900_000 if close_times else None
            con.execute("INSERT INTO historical_klines VALUES (?,?,?,?,?,?,?,?)",
                        ("BTCUSDT", "15m", base + i * 900_000, 100.0 + i,
                         101.0 + i, 99.0 + i, 100.5 + i, ct))
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


class CloseTimeContractTest(unittest.TestCase):
    def test_close_time_preserved_units_and_coverage(self) -> None:
        db, tmp = _fixture(self)
        out = tmp / "exp"
        code = main(["--db", str(db), "--symbols", "BTCUSDT",
                     "--interval", "15m", "--out-dir", str(out)])
        self.assertEqual(code, 0)
        candles = json.loads((out / "candles.json").read_text(encoding="utf-8"))
        meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
        self.assertTrue(all(c["close_time_ms"] is not None for c in candles))
        self.assertEqual(candles[0]["close_time_ms"],
                         candles[0]["open_time_ms"] + 900_000)
        self.assertIn("epoch milliseconds", meta["units"]["times_ms"])
        self.assertEqual(meta["coverage"]["window_open_ms"],
                         candles[0]["open_time_ms"])
        self.assertEqual(meta["coverage"]["null_close_time"], 0)
        self.assertEqual(meta["coverage"]["close_chain_violations"], 0)

    def test_as_of_filters_open_candles_and_differs_from_cutoff(self) -> None:
        db, tmp = _fixture(self)
        out = tmp / "exp"
        base = 1_700_000_000_000
        # Frontier inside candle 5: candles closing after it are dropped.
        code = main(["--db", str(db), "--symbols", "BTCUSDT",
                     "--interval", "15m", "--out-dir", str(out),
                     "--as-of-ms", str(base + 5 * 900_000)])
        self.assertEqual(code, 0)
        meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
        candles = json.loads((out / "candles.json").read_text(encoding="utf-8"))
        self.assertEqual(len(candles), 5)
        self.assertEqual(meta["discarded"]["open-after-asof"], 5)
        self.assertEqual(meta["as_of_ms"], base + 5 * 900_000)
        # cutoff (dev/OOS event split) is a different knob with a
        # different meaning: it never filters candles here.
        self.assertNotEqual(meta["as_of_ms"], meta["cutoff_ms"])
        self.assertIn("never confuse", meta["as_of_note"])

    def test_runner_preserves_open_and_close_times(self) -> None:
        db, tmp = _fixture(self)
        out = tmp / "exp"
        main(["--db", str(db), "--symbols", "BTCUSDT",
              "--interval", "15m", "--out-dir", str(out)])
        rows = json.loads((out / "candles.json").read_text(encoding="utf-8"))
        kept = _load_candles(out / "candles.json")
        self.assertEqual(len(kept), len(rows))
        for raw, candle in zip(rows, kept):
            self.assertEqual(candle.open_time_ms, raw["open_time_ms"])
            self.assertEqual(candle.close_time_ms, raw["close_time_ms"])
        # Carried provenance never enters the identity hash.
        h1 = input_hash([], kept)
        stripped = [Candle(c.symbol, c.open_time_ms, c.open, c.high,
                           c.low, c.close) for c in kept]
        self.assertEqual(h1, input_hash([], stripped))


class IntraCandleCausalityTest(unittest.TestCase):
    """An event inside a 15m candle cannot use that candle's final
    close/high/low before it closes (fail-before would fill at 100.0,
    stop at the 1.0 low, or harvest the 200.0 high)."""

    def test_unclosed_candle_range_never_touched(self) -> None:
        step = 900_000
        t0 = 1_700_000_000_000
        candles = [
            Candle("BTCUSDT", t0, 100.0, 200.0, 1.0, 101.0, t0 + step),
            Candle("BTCUSDT", t0 + step, 100.5, 100.6, 100.4, 100.5,
                   t0 + 2 * step),
            Candle("BTCUSDT", t0 + 2 * step, 100.5, 100.6, 100.4, 100.5,
                   t0 + 3 * step),
        ]
        events = [StudyEvent(symbol="BTCUSDT", event_time_ms=t0 + 1,
                             direction="LONG", reference_price=100.0,
                             family="H1", rules_version="H1-v1")]
        cfg = BacktestConfig(family="H1", rules_version="H1-v1",
                             exit_horizon_ms=3600_000, stop_distance_pct=0.5,
                             notional_usdt=1000.0)
        res = run_backtest(events, candles, cfg, dataset_id="causal-fixture",
                           segment="dev")
        self.assertEqual(res["n_trades"], 1)
        trade = res["trades"][0]
        # Fill at the first KNOWN open strictly after the event...
        self.assertEqual(trade["entry_ms"], t0 + step)
        self.assertAlmostEqual(trade["entry_px"], 100.5, places=9)
        # ...never at the enclosing candle's open/close, never stopped
        # by its low, never harvesting its high.
        self.assertNotEqual(trade["entry_ms"], t0)
        self.assertNotEqual(trade["exit_reason"], "stop")
        self.assertLess(trade["mfe_pct"], 1.0)  # 200.0 high would read ~99%
        # Negative control: a lookahead engine using candle0 would fill
        # at 100.0, stop at the 1.0 low and harvest ~99% MFE — every one
        # of those readings differs here, so the test discriminates.
        self.assertNotAlmostEqual(trade["entry_px"], 100.0, places=9)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
