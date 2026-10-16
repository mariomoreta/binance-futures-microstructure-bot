"""Offline-eval aggregation (bundling manifests -> artifact).

Temp fixtures only (never canonical DBs, never the network).
Run: python run_tests.py
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from aggregate_offline_eval import (  # noqa: E402
    GROUPS,
    build,
    main as aggregate_main,
)


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


def _cell(n_events=4, n_trades=3, scale=1.0):
    return {
        "n_events": n_events, "n_trades": n_trades, "n_expired": 0,
        "n_mismatched": 0, "skipped_overlap": n_events - n_trades,
        "n_realized": n_trades, "n_open": 0,
        "exit_reasons": {"horizon": 3, "stop": 0, "open_at_end": 0},
        "expectancy_net": 0.5, "expectancy_gross": 2.0,
        "total_net": 1.5 * scale, "total_net_realized": 1.5 * scale,
        "total_fees": 3.0 * scale, "total_funding": 0.0,
        "max_drawdown": 1.0, "max_drawdown_realized": 1.0,
        "mfe_mean": 0.3, "mae_mean": 0.1, "config_hash": "abcd1234",
        "funding_quality": {
            "settled_events": 0, "unknown_excluded": 0, "gap_ms": 0,
            "uncovered_ms": 0, "accounting_complete_trades": n_trades,
            "note": "x",
        },
    }


def _fixture_inputs(tmp: Path, cutoff=1790010000000):
    symbols = {}
    for sym, n_in, n_dev, purged in (("BTCUSDT", 10, 6, 0),
                                     ("ETHUSDT", 10, 5, 1)):
        manifest = {
            "input_hash": "hash_%s" % sym, "cutoff_ms": cutoff,
            "groups": {g: {seg: {s: _cell(scale=float(s))
                                 for s in ("1.0", "2.0", "3.0")}
                           for seg in ("dev", "oos")} for g in GROUPS},
        }
        meta = {
            "interval": "15m", "n_candles": 100,
            "coverage": {"window_open_ms": 1, "window_close_ms": 2,
                         "null_close_time": 0, "close_chain_violations": 0},
            "n_events": n_in,
            "discarded": {"unmapped-definition": 0, "bad-direction": 0,
                          "bad-price": 0, "bad-time": 0,
                          "symbol-filtered": 5, "open-after-asof": 0},
        }
        selection = {
            "cutoff_ms": cutoff, "horizon_ms": 3600000, "n_in": n_in,
            "n_dev": n_dev, "n_oos": n_in - n_dev - purged,
            "n_purged_dev_crossing": purged, "note": "n",
        }
        calendar = {
            "version": "FUNDING-CAL-v1", "source": "s", "interval_ms": 1,
            "symbol": sym,
            "settlements": [{"settlement_ms": 10, "rate_bps": 0.5},
                            {"settlement_ms": 20, "rate_bps": 0.1}],
            "provenance": {"response_sha256": "00" * 32},
        }
        paths = {}
        for name, payload in (("manifest", manifest), ("meta", meta),
                              ("selection", selection),
                              ("calendar", calendar)):
            p = tmp / ("%s_%s.json" % (sym, name))
            p.write_text(json.dumps(payload), encoding="utf-8")
            paths[name] = str(p)
        symbols[sym] = paths
    return {"cutoff_ms": cutoff, "horizon_ms": 3600000, "symbols": symbols}


class AggregateOfflineEvalTest(unittest.TestCase):
    def test_bundles_cells_symbols_and_pooled(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="aggeval_"))
        self.addCleanup(lambda: _rmtree(tmp))
        art = build(_fixture_inputs(tmp))
        self.assertEqual(art["schema_version"], 1)
        self.assertEqual(art["artifact_version"], "OFFLINE-EVAL-V1")
        self.assertEqual(art["cutoff_ms"], 1790010000000)
        self.assertEqual(art["symbols"]["BTCUSDT"]["n_events"], 10)
        self.assertEqual(art["symbols"]["ETHUSDT"]["selection"][
            "n_purged_dev_crossing"], 1)
        self.assertEqual(art["cells"]["BTCUSDT"]["continuation"]["dev"][
            "1.0"]["n_trades"], 3)
        # Pooled = arithmetic sums over directional groups only.
        n_dir = len([g for g in GROUPS if g in (
            "continuation", "correction-exhaustion",
            "correction-reversal", "bearish-continuation")])
        # Fixture cells carry n_events=4 per (symbol, directional group):
        # pooled dev = (BTC 4 + ETH 4) x 4 groups.
        self.assertEqual(art["pooled_reference"]["dev"]["1.0"][
            "n_events"], (4 + 4) * n_dir)
        self.assertAlmostEqual(art["pooled_reference"]["dev"]["1.0"][
            "expectancy_net"],
            art["pooled_reference"]["dev"]["1.0"]["total_net"] /
            art["pooled_reference"]["dev"]["1.0"]["n_trades"])

    def test_cutoff_mismatch_rejected(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="aggeval_"))
        self.addCleanup(lambda: _rmtree(tmp))
        inputs = _fixture_inputs(tmp)
        inputs["cutoff_ms"] = 123
        with self.assertRaises(ValueError):
            build(inputs)

    def test_selection_must_add_up(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="aggeval_"))
        self.addCleanup(lambda: _rmtree(tmp))
        inputs = _fixture_inputs(tmp)
        sel_path = Path(inputs["symbols"]["BTCUSDT"]["selection"])
        sel = json.loads(sel_path.read_text(encoding="utf-8"))
        sel["n_purged_dev_crossing"] = 99
        sel_path.write_text(json.dumps(sel), encoding="utf-8")
        with self.assertRaises(ValueError):
            build(inputs)

    def test_foreign_calendar_rejected(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="aggeval_"))
        self.addCleanup(lambda: _rmtree(tmp))
        inputs = _fixture_inputs(tmp)
        cal_path = Path(inputs["symbols"]["BTCUSDT"]["calendar"])
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
        cal["symbol"] = "SOLUSDT"
        cal_path.write_text(json.dumps(cal), encoding="utf-8")
        with self.assertRaises(ValueError):
            build(inputs)

    def test_byte_stable_output(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="aggeval_"))
        self.addCleanup(lambda: _rmtree(tmp))
        inputs = _fixture_inputs(tmp)
        first = json.dumps(build(inputs), indent=1)
        second = json.dumps(build(inputs), indent=1)
        self.assertEqual(
            hashlib.sha256(first.encode()).hexdigest(),
            hashlib.sha256(second.encode()).hexdigest())


class AggregateCliTest(unittest.TestCase):
    def test_cli_writes_artifact(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="aggeval_"))
        self.addCleanup(lambda: _rmtree(tmp))
        inp = tmp / "inputs.json"
        inp.write_text(json.dumps(_fixture_inputs(tmp)), encoding="utf-8")
        out = tmp / "artifact.json"
        code = aggregate_main(["--inputs", str(inp), "--out", str(out)])
        self.assertEqual(code, 0)
        art = json.loads(out.read_bytes().decode("utf-8"))
        self.assertEqual(art["artifact_version"], "OFFLINE-EVAL-V1")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
