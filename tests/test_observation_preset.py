"""observation-10m preset (600s) via the canonical mechanism.

Additive: existing presets keep byte-identical behavior (validation-6h
forces 21600s + p1-10r evidence dir; brief/standard collapse to the
"standard" registry label on the STARTING commit). No probes launched:
spawn is mocked, registry is a temp file.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="obs10m_"))
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


class _FakeProc:
    def __init__(self, pid):
        self.pid = pid
        self.kill_calls = 0

    def kill(self):
        self.kill_calls += 1


class ObservationPresetTest(unittest.TestCase):
    def test_recorded_preset_preserves_new_name_only(self) -> None:
        self.assertEqual(pc._recorded_preset("observation-10m"),
                         "observation-10m")
        # Existing presets byte-identical: validation-6h verbatim,
        # everything else collapses to standard (unchanged behavior).
        self.assertEqual(pc._recorded_preset("validation-6h"),
                         "validation-6h")
        self.assertEqual(pc._recorded_preset("brief"), "standard")
        self.assertEqual(pc._recorded_preset("standard"), "standard")
        self.assertEqual(pc._recorded_preset("rocket"), "standard")

    def test_cli_accepts_observation_10m(self) -> None:
        args = pc.build_parser().parse_args(["start", "--preset",
                                             "observation-10m"])
        self.assertEqual(args.preset, "observation-10m")

    def test_start_probe_forces_600s_and_records_preset(self) -> None:
        _, tmp = _temp_registry(self)
        proc = _FakeProc(555)
        seen = {}

        class _SpyPopen:
            def __init__(self, argv, **kwargs):
                seen["argv"] = argv
                seen["env_preset"] = (kwargs.get("env") or {}).get(
                    "MICROPROBE_PRESET")
                self.pid = proc.pid

            def kill(self):
                proc.kill()

        with mock.patch.object(pc.subprocess, "Popen", _SpyPopen):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="C555"):
                # Caller asks 120s but observation-10m forces 600s.
                out = pc.start_probe(duration_seconds=120,
                                     launcher="dashboard",
                                     preset="observation-10m",
                                     evidence_dir=str(tmp / "evidence"))
        self.assertTrue(out["started"])
        self.assertEqual(out["duration_seconds"], 600)
        self.assertIn("--duration", seen["argv"])
        self.assertIn("600", seen["argv"])
        self.assertEqual(seen["env_preset"], "observation-10m")
        record = pc.read_registry()
        self.assertEqual(record["duration_seconds"], 600)
        self.assertEqual(record["preset"], "observation-10m")
        self.assertEqual(record["launcher"], "dashboard")
        # Default evidence branch (explicit dir in this test, but the
        # preset must not route to the validation-6h p1-10r wrapper).
        self.assertNotIn("p1-10r", record["evidence"]["log"])
        self.assertEqual(proc.kill_calls, 0)
        pc._close_log_handles(555)

    def test_existing_presets_unchanged(self) -> None:
        _, tmp = _temp_registry(self)
        proc = _FakeProc(556)

        class _SpyPopen:
            def __init__(self, argv, **kwargs):
                seen_argv = argv
                self.pid = proc.pid
                self._argv = seen_argv

            def kill(self):
                proc.kill()

        with mock.patch.object(pc.subprocess, "Popen", _SpyPopen):
            with mock.patch.object(pc, "own_creation_time",
                                   return_value="C556"):
                # Caller asks 60s but validation-6h forces 21600s
                # (historical behavior, unchanged).
                out = pc.start_probe(duration_seconds=60,
                                     launcher="dashboard",
                                     preset="validation-6h",
                                     evidence_dir=str(tmp / "evidence"))
        self.assertTrue(out["started"])
        self.assertEqual(out["duration_seconds"], 21600)
        record = pc.read_registry()
        self.assertEqual(record["duration_seconds"], 21600)
        self.assertEqual(record["preset"], "validation-6h")
        pc._close_log_handles(556)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
