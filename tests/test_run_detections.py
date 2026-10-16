"""read_run_detections: recorded-run funding evidence, grouped (read-only).

Temp registry + temp logs only. Never touches the canonical log,
never writes, never spawns.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="rundet_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    path = tmp / "probe_runtime.json"
    os.environ["MICROPROBE_RUNTIME_FILE"] = str(path)
    testcase.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
    return path, tmp


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


def _record(log=None, **extra):
    rec = {"schema": 1, "writer": "control/1", "state": "COMPLETED",
           "pid": 111, "create_time": "C1",
           "started_at": "2026-10-16T00:00:00+00:00", "mode": "observe",
           "command": ["python", "-m", "microstructure_probe"],
           "duration_seconds": 600, "expected_end_at": None,
           "launcher": "dashboard", "preset": "observation-10m",
           "evidence": ({"dir": "x", "log": log} if log else None),
           "last_exit": {"code": 0, "reason": "duration-reached",
                         "at": "2026-10-16T00:10:10+00:00"}}
    rec.update(extra)
    return rec


def _funding_line(ts, symbol, rate, samples):
    return "2026-10-16 00:00:00,000 INFO " + json.dumps({
        "kind": "detected_event", "timestamp": ts, "symbol": symbol,
        "event_type": "extreme_funding_rate", "magnitude": rate,
        "details": {"funding_rate": rate, "lower_percentile_value": rate,
                    "upper_percentile_value": rate,
                    "history_samples": samples}})


class RunDetectionsTest(unittest.TestCase):
    def test_no_record_is_unavailable(self) -> None:
        _temp_registry(self)
        out = pc.read_run_detections()
        self.assertFalse(out["available"])
        self.assertEqual(out["limitation"], "no-recorded-run")

    def test_missing_evidence_log_is_unavailable(self) -> None:
        path, _ = _temp_registry(self)
        path.write_text(json.dumps(_record()), encoding="utf-8")
        out = pc.read_run_detections()
        self.assertFalse(out["available"])
        self.assertEqual(out["limitation"], "no-evidence-log")

    def test_absent_log_file_is_unavailable_with_run_id(self) -> None:
        path, tmp = _temp_registry(self)
        path.write_text(json.dumps(
            _record(log=str(tmp / "probe-missing.log"))), encoding="utf-8")
        out = pc.read_run_detections()
        self.assertFalse(out["available"])
        self.assertEqual(out["limitation"], "log-unavailable")
        self.assertEqual(out["run_id"], "probe-missing")

    def test_groups_recorded_run_and_ignores_other_kinds(self) -> None:
        path, tmp = _temp_registry(self)
        log = tmp / "probe-test.log"
        lines = [
            _funding_line("2026-10-16T00:00:01Z", "BTCUSDT", 5e-05, 100),
            _funding_line("2026-10-16T00:00:02Z", "BTCUSDT", 5e-05, 101),
            "2026-10-16 00:00:03,000 INFO " + json.dumps(
                {"kind": "summary", "runtimeSeconds": 3}),
            "not json at all",
            "2026-10-16 00:00:04,000 INFO " + json.dumps(
                {"kind": "detected_event", "timestamp": "2026-10-16T00:00:04Z",
                 "symbol": "ETHUSDT", "event_type": "volume_spike",
                 "details": {}}),
            _funding_line("2026-10-16T00:00:30Z", "BTCUSDT", 5e-05, 102),
        ]
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        path.write_text(json.dumps(
            _record(log=str(log), probe_run_id="c" * 32)), encoding="utf-8")
        out = pc.read_run_detections()
        self.assertTrue(out["available"])
        self.assertEqual(out["run_id"], "probe-test")
        self.assertEqual(out["probe_run_id"], "c" * 32)
        self.assertEqual(out["events_total"], 3)
        self.assertEqual(out["episodes_total"], 2)
        self.assertEqual(out["grouping_version"], "v1")
        first, second = out["episodes"]
        self.assertEqual((first["repetitions"], first["symbol"]), (2, "BTCUSDT"))
        self.assertEqual(second["open_reason"], "gap-exceeded")
        self.assertIsNone(out["limitation"])

    def test_empty_evidence_reports_limitation(self) -> None:
        path, tmp = _temp_registry(self)
        log = tmp / "probe-empty.log"
        log.write_text("2026-10-16 00:00:01,000 INFO " +
                       json.dumps({"kind": "summary"}) + "\n",
                       encoding="utf-8")
        path.write_text(json.dumps(_record(log=str(log))), encoding="utf-8")
        out = pc.read_run_detections()
        self.assertTrue(out["available"])
        self.assertEqual(out["events_total"], 0)
        self.assertEqual(out["episodes_total"], 0)
        self.assertEqual(out["limitation"], "no-funding-events-in-evidence")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
