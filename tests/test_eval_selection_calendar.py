"""Purge selection + realized funding calendar builder (harness tests).

Temp fixtures only (never canonical DBs, never the network).
Run: python run_tests.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build_funding_calendar import main as build_cal  # noqa: E402
from select_eval_events import main as select_events  # noqa: E402


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


class PurgeSelectionTest(unittest.TestCase):
    def test_dev_oos_purge_boundaries(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="selsplit_"))
        self.addCleanup(lambda: _rmtree(tmp))
        cutoff, horizon = 1_790_010_000_000, 3_600_000
        rows = [
            {"event_time_ms": cutoff - horizon - 1},   # dev (window ends <= cutoff)
            {"event_time_ms": cutoff - horizon},       # dev (boundary inclusive)
            {"event_time_ms": cutoff - horizon + 1},   # purged (crosses)
            {"event_time_ms": cutoff - 1},             # purged (crosses)
            {"event_time_ms": cutoff},                 # oos (boundary inclusive)
            {"event_time_ms": cutoff + 1},             # oos
        ]
        src = tmp / "events.json"
        src.write_text(json.dumps(rows), encoding="utf-8")
        code = select_events(["--events", str(src),
                              "--cutoff-ms", str(cutoff),
                              "--horizon-ms", str(horizon),
                              "--dev-out", str(tmp / "dev.json"),
                              "--oos-out", str(tmp / "oos.json"),
                              "--report", str(tmp / "rep.json")])
        self.assertEqual(code, 0)
        dev = json.loads((tmp / "dev.json").read_text(encoding="utf-8"))
        oos = json.loads((tmp / "oos.json").read_text(encoding="utf-8"))
        rep = json.loads((tmp / "rep.json").read_text(encoding="utf-8"))
        self.assertEqual([r["event_time_ms"] for r in dev],
                         [cutoff - horizon - 1, cutoff - horizon])
        self.assertEqual([r["event_time_ms"] for r in oos],
                         [cutoff, cutoff + 1])
        self.assertEqual(rep["n_purged_dev_crossing"], 2)
        self.assertEqual(rep["n_in"], 6)
        # Input untouched (selection never mutates the export).
        self.assertEqual(len(json.loads(src.read_text(encoding="utf-8"))), 6)

    def test_no_dev_window_crosses_cutoff_property(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="selsplit_"))
        self.addCleanup(lambda: _rmtree(tmp))
        cutoff, horizon = 1_790_010_000_000, 3_600_000
        rows = [{"event_time_ms": cutoff - 50_000_000 + i * 900_000}
                for i in range(100)]
        src = tmp / "events.json"
        src.write_text(json.dumps(rows), encoding="utf-8")
        select_events(["--events", str(src), "--cutoff-ms", str(cutoff),
                       "--horizon-ms", str(horizon),
                       "--dev-out", str(tmp / "dev.json"),
                       "--oos-out", str(tmp / "oos.json"),
                       "--report", str(tmp / "rep.json")])
        dev = json.loads((tmp / "dev.json").read_text(encoding="utf-8"))
        oos = json.loads((tmp / "oos.json").read_text(encoding="utf-8"))
        for r in dev:
            self.assertLessEqual(r["event_time_ms"] + horizon, cutoff)
        for r in oos:
            self.assertGreaterEqual(r["event_time_ms"], cutoff)
        rep = json.loads((tmp / "rep.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["n_dev"] + rep["n_oos"] +
                         rep["n_purged_dev_crossing"], 100)


class FundingCalendarBuilderTest(unittest.TestCase):
    def _raw(self, tmp: Path, rows) -> Path:
        p = tmp / "raw.json"
        p.write_text(json.dumps(rows), encoding="utf-8")
        return p

    def test_realized_rates_symbol_pinned_ordered(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="fundcal_"))
        self.addCleanup(lambda: _rmtree(tmp))
        raw = self._raw(tmp, [
            {"symbol": "BTCUSDT", "fundingTime": 2000,
             "fundingRate": "0.00010000"},
            {"symbol": "ETHUSDT", "fundingTime": 1000,
             "fundingRate": "0.00020000"},
            {"symbol": "BTCUSDT", "fundingTime": 1000,
             "fundingRate": "0.00005000"},
        ])
        out = tmp / "cal.json"
        code = build_cal(["--raw", str(raw), "--symbol", "BTCUSDT",
                          "--version", "FUNDING-CAL-v1",
                          "--acquired-utc", "2026-10-16T00:00:00Z",
                          "--out", str(out)])
        self.assertEqual(code, 0)
        cal = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(cal["symbol"], "BTCUSDT")
        self.assertEqual(cal["version"], "FUNDING-CAL-v1")
        self.assertEqual(cal["source"],
                         "exchange-funding-history (Binance USD-M fundingRate)")
        # 1bp = 0.0001 -> 1.0 bps; foreign symbol filtered, time ordered.
        self.assertEqual([(s["settlement_ms"], s["rate_bps"])
                          for s in cal["settlements"]],
                         [(1000, 0.5), (2000, 1.0)])
        self.assertEqual(cal["provenance"]["n_raw"], 3)
        self.assertEqual(cal["provenance"]["n_settlements"], 2)
        self.assertEqual(len(cal["provenance"]["response_sha256"]), 64)

    def test_coverage_schema_is_explicit_and_not_overcredited(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="fundcal_coverage_"))
        self.addCleanup(lambda: _rmtree(tmp))
        raw = self._raw(tmp, [
            {"symbol": "BTCUSDT", "fundingTime": 1000,
             "fundingRate": "0.00010000"},
        ])
        out = tmp / "cal.json"
        code = build_cal(["--raw", str(raw), "--symbol", "BTCUSDT",
                          "--coverage-start-ms", "0",
                          "--coverage-end-ms", "2000",
                          "--acquired-ms", "3000",
                          "--out", str(out)])
        self.assertEqual(code, 0)
        cal = json.loads(out.read_text(encoding="utf-8"))
        coverage = cal["coverage"]
        self.assertEqual(coverage["version"], "funding-coverage/v1")
        self.assertEqual(coverage["status"], "unknown")
        self.assertEqual(coverage["interval_start_ms"], 0)
        self.assertEqual(coverage["interval_end_ms"], 2001)
        self.assertEqual(coverage["request"]["params"]["startTime"], 0)
        self.assertEqual(coverage["request"]["params"]["endTime"], 2000)
        self.assertFalse(coverage["response"]["pagination"]["truncated"])
        self.assertIsNone(coverage["publication_delay_ms"])

    def test_truncated_response_is_incomplete(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="fundcal_truncated_"))
        self.addCleanup(lambda: _rmtree(tmp))
        raw = self._raw(tmp, [
            {"symbol": "BTCUSDT", "fundingTime": 1000,
             "fundingRate": "0.00010000"},
        ])
        out = tmp / "cal.json"
        code = build_cal(["--raw", str(raw), "--symbol", "BTCUSDT",
                          "--coverage-start-ms", "0",
                          "--coverage-end-ms", "2000",
                          "--limit", "1", "--acquired-ms", "3000",
                          "--out", str(out)])
        self.assertEqual(code, 0)
        coverage = json.loads(
            out.read_text(encoding="utf-8"))["coverage"]
        self.assertEqual(coverage["status"], "incomplete")
        self.assertTrue(coverage["response"]["pagination"]["truncated"])

    def test_foreign_symbol_response_is_incomplete(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="fundcal_foreign_"))
        self.addCleanup(lambda: _rmtree(tmp))
        raw = self._raw(tmp, [
            {"symbol": "ETHUSDT", "fundingTime": 1000,
             "fundingRate": "0.00010000"},
        ])
        out = tmp / "cal.json"
        code = build_cal(["--raw", str(raw), "--symbol", "BTCUSDT",
                          "--coverage-start-ms", "0",
                          "--coverage-end-ms", "2000",
                          "--acquired-ms", "3000", "--out", str(out)])
        self.assertEqual(code, 0)
        coverage = json.loads(
            out.read_text(encoding="utf-8"))["coverage"]
        self.assertEqual(coverage["status"], "incomplete")
        self.assertIn("different symbol", coverage["reason"])

    def test_quoted_estimate_never_substituted(self) -> None:
        # A quoted/next rate has no fundingTime settlement shape; rows
        # without one cannot enter the calendar (no fabrication).
        tmp = Path(tempfile.mkdtemp(prefix="fundcal_"))
        self.addCleanup(lambda: _rmtree(tmp))
        raw = self._raw(tmp, [
            {"symbol": "BTCUSDT", "nextFundingRate": "0.00030000"},
        ])
        out = tmp / "cal.json"
        with self.assertRaises((KeyError, TypeError)):
            build_cal(["--raw", str(raw), "--symbol", "BTCUSDT",
                       "--out", str(out)])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
