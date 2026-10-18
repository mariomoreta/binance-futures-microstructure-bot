"""Verificador de regresiones EVAL-CENSUS-V2 basado en unittest.

Ejecuta la suite de tests/test_audit_offline_eval_traceability.py y reporta
conteos reales (tests ejecutados, fallos, errores). No usa contadores
ficticios tipo len(errores)+20.

Uso:
    python scripts/audit_offline_eval_checks.py
    python run_tests.py -q   (descubre todo tests/, incluido este verificador)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"
for p in (str(SRC), str(TESTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

TESTS = Path(__file__).resolve().parent.parent / "tests"


def main(argv=None):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    # Añade explícitamente el módulo de trazabilidad.
    import test_audit_offline_eval_traceability as mod  # noqa: E402
    suite.addTests(loader.loadTestsFromModule(mod))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n=== RESUMEN VERIFICADOR ===")
    print("tests ejecutados: %d" % result.testsRun)
    print("fallos: %d" % len(result.failures))
    print("errores: %d" % len(result.errors))
    print("exitosos: %d" % (result.testsRun - len(result.failures) - len(result.errors)))

    if result.failures:
        print("\n--- FALLOS ---")
        for test, tb in result.failures:
            print(" -", test)
    if result.errors:
        print("\n--- ERRORES ---")
        for test, tb in result.errors:
            print(" -", test)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
