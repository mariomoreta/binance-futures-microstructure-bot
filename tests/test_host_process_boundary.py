"""Host-process helper extraction boundary (DASH-V2-67 backend handoff).

`control.py` must not depend on the HTTP `dashboard.py` module: shared
`repo_root / process_info / pid_is_ours / no_window_flags`
(+ `_creation_time_ctypes`) live in `host_process` (stdlib only), with
`dashboard` keeping compatible re-exports and no duplicated identity
logic. Failing-first: on the pre-extraction tree H1 finds 16 dashboard
imports in control, H2 raises ImportError, H3 cannot import host_process.

  H1  control.py source contains no dashboard import (static boundary).
  H2  fresh-subprocess isolation: with `microstructure_probe.dashboard`
      blocked by a find_spec hook (negative control proves the blocker),
      `control` imports and
      `own_creation_time()` resolves without touching the HTTP module.
  H3  compatibility: dashboard.X IS host_process.X (same function object,
      no second implementation) for all five helpers.
  H4  behavioral parity spot-checks through both namespaces.

Run: python run_tests.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc
from microstructure_probe import host_process as hp

_HELPERS = ("repo_root", "no_window_flags", "process_info",
            "_creation_time_ctypes", "pid_is_ours")


class ImportBoundaryTest(unittest.TestCase):
    def test_control_source_has_no_dashboard_import(self):
        src = Path(pc.__file__).read_text(encoding="utf-8")
        hits = re.findall(
            r"from\s+(?:\.dashboard|microstructure_probe\.dashboard)\s+import"
            r"|from\s+\.\s+import\s+dashboard|import\s+dashboard\b", src)
        self.assertEqual(hits, [])

    def test_control_usable_without_http_module(self):
        repo = Path(pc.__file__).resolve().parent.parent.parent
        registry = os.environ.get("MICROPROBE_RUNTIME_FILE", "")
        script = (
            "import sys, importlib, importlib.abc\n"
            "class _Block(importlib.abc.MetaPathFinder):\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name == 'microstructure_probe.dashboard':\n"
            "            raise ImportError('blocked HTTP module: ' + name)\n"
            "sys.meta_path.insert(0, _Block())\n"
            "sys.path.insert(0, %r)\n"
            "try:\n"
            "    importlib.import_module('microstructure_probe.dashboard')\n"
            "except ImportError as error:\n"
            "    assert 'blocked HTTP module' in str(error)\n"
            "else:\n"
            "    raise AssertionError('HTTP import blocker ineffective')\n"
            "print('BLOCK_VERIFIED')\n"
            "import microstructure_probe.host_process as hp\n"
            "import microstructure_probe.control as pc\n"
            "assert 'microstructure_probe.dashboard' not in sys.modules\n"
            "print('ctime:', pc.own_creation_time())\n"
            "print('root:', hp.repo_root())\n"
            "assert 'microstructure_probe.dashboard' not in sys.modules\n"
            "print('OK')\n" % str(repo / "src"))
        proc = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True,
            timeout=60, env={**os.environ,
                             "MICROPROBE_RUNTIME_FILE": registry})
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        self.assertIn("BLOCK_VERIFIED", proc.stdout)
        self.assertIn("OK", proc.stdout)
        self.assertNotIn("blocked HTTP module", proc.stderr)


class CompatibilityTest(unittest.TestCase):
    def test_dashboard_reexports_same_objects(self):
        from microstructure_probe import dashboard as dash
        for name in _HELPERS:
            self.assertIs(getattr(dash, name), getattr(hp, name),
                          "dashboard.%s must be host_process.%s, not a copy"
                          % (name, name))

    def test_behavioral_parity(self):
        from microstructure_probe import dashboard as dash
        self.assertEqual(hp.repo_root(), dash.repo_root())
        self.assertEqual(hp.repo_root().name,
                         Path("C:/proyectos/binance-futures-microstructure-bot").name)
        self.assertEqual(hp.no_window_flags(), dash.no_window_flags())
        self.assertIsInstance(hp.no_window_flags(), int)
        self.assertEqual(hp.process_info(99999999), (None, None))
        self.assertEqual(dash.process_info(99999999), (None, None))
        self.assertFalse(hp.pid_is_ours(99999999, "STAMP"))
        self.assertFalse(dash.pid_is_ours(99999999, "STAMP"))
        self.assertIsNone(hp._creation_time_ctypes(99999999))
