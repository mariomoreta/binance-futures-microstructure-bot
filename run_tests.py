"""Canonical test entrypoint (P1-00).

Works from the repository root with no install step and no environment setup::

    python run_tests.py        # full suite, verbose
    python run_tests.py -q     # quiet (verbosity 1)

It prepends ``src/`` to ``sys.path`` so the ``microstructure_probe`` package
resolves under the src-layout, then runs unittest discovery over ``tests/``.
Exit code is 0 on success, 1 on any failure/error (safe for autonomous loops).
No application behavior is changed by this file.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"


def main(argv: list[str]) -> int:
    verbosity = 2
    if "-q" in argv or "--quiet" in argv:
        verbosity = 1
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    suite = unittest.TestLoader().discover(start_dir=str(TESTS))
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
