"""Observation-run usage cycle, verified with isolated processes/DBs.

Proves the cycle contract WITHOUT starting any real run: opening the
dashboard (read-only status) never starts the bot; the disabled
supervised launch refuses with zero side effects; stopping with no run
is harmless; every step runs against temp registries/DBs, never the
canonical paths. Run: python run_tests.py
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class IsolatedCycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="obs_cycle_"))
        self._old = os.environ.get("MICROPROBE_RUNTIME_FILE")
        os.environ["MICROPROBE_RUNTIME_FILE"] = str(
            self.tmp / "probe_runtime.json")

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("MICROPROBE_RUNTIME_FILE", None)
        else:
            os.environ["MICROPROBE_RUNTIME_FILE"] = self._old

    def test_open_dashboard_starts_nothing(self) -> None:
        # Reading status (what opening the dashboard does) creates no
        # registry, no processes, no DBs: dashboard-open != bot-start.
        from microstructure_probe import control as pc
        before = set(self.tmp.iterdir())
        first = pc.status_readonly()
        second = pc.status_readonly()
        self.assertEqual(first, second)
        self.assertIn("supervisor", first)
        self.assertIn("sentinel", first)
        self.assertEqual(first.get("running"), False)
        self.assertEqual(set(self.tmp.iterdir()), before)
        self.assertFalse((self.tmp / "probe_runtime.json").exists())

    def test_disabled_launch_refuses_with_zero_side_effects(self) -> None:
        from microstructure_probe import control as pc
        out = pc.launch_supervised_transaction(duration_seconds=60.0,
                                               launcher="cycle-test")
        self.assertNotEqual(out.get("outcome"), "confirmed")
        self.assertFalse((self.tmp / "probe_runtime.json").exists())
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_stop_with_no_run_is_harmless(self) -> None:
        from microstructure_probe import control as pc
        out = pc.stop_probe(requester="cycle-test")
        self.assertEqual(out.get("stopped"), False)
        self.assertEqual(out.get("error"), "no-active-probe")
        # No run existed: nothing terminated, nothing created.
        self.assertFalse((self.tmp / "probe_runtime.json").exists())

    def test_temp_db_never_touches_canonical(self) -> None:
        # Constructing a store never touches the filesystem (documented):
        # temp target recorded, canonical mtime untouched, nothing created.
        from microstructure_probe import persistence as ps
        canonical = Path("data/microprobe.db")
        before = (canonical.stat().st_mtime_ns if canonical.exists()
                  else None)
        db = self.tmp / "cycle.db"
        store = ps.PersistenceStore(str(db))
        self.assertEqual(store.db_path, db)
        self.assertFalse(db.exists())
        if before is not None:
            self.assertEqual(canonical.stat().st_mtime_ns, before)


if __name__ == "__main__":
    unittest.main()
