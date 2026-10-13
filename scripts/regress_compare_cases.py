"""Automated comparator regressions M1-M8 (temp copies; originals intact).

Builds mutant copies of binance_case_study/ in a temp dir, runs
docs/evidence/compare_case_study_json_csv.py (ORIG vs mutant) and asserts
the expected exit codes:
  M1 value->missing exit 1 | M2 missing->value exit 1
  M3 numeric change exit 1 | M4 structure change exit 1
  M5 missing file exit 2 | M6a +inf vs -inf exit 1
  M6b finite vs -inf exit 1 | M7 empty csv exit 2 | M8 garbled csv exit 2

Usage: python scripts/regress_compare_cases.py
Exit 0 iff all 9 cases behave as expected. No network, no DB.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPARE = ROOT / "docs" / "evidence" / "compare_case_study_json_csv.py"
ORIG = ROOT / "binance_case_study"


def _run(orig: Path, repro: Path) -> tuple[int, dict]:
    out = repro.parent / (repro.name + ".result.json")
    proc = subprocess.run(
        [sys.executable, str(COMPARE), str(orig), str(repro),
         "--out", str(out)],
        capture_output=True, text=True, timeout=300)
    data = json.loads(out.read_text(encoding="utf-8"))
    return proc.returncode, data


def main() -> int:
    import pandas as pd
    import numpy as np

    work = Path(tempfile.mkdtemp(prefix="cmp_reg_"))
    base = work / "base"
    shutil.copytree(ORIG, base)
    cases = []

    def mutant(name: str) -> Path:
        dest = work / name
        shutil.copytree(base, dest)
        return dest

    # M1: value -> missing (WUSDT row 100 rsi14 -> NaN).
    m1 = mutant("M1_valor_missing")
    df = pd.read_csv(m1 / "WUSDT_features_5m.csv")
    assert abs(float(df.loc[100, "rsi14"]) - 51.06347303475749) < 1e-9
    df.loc[100, "rsi14"] = float("nan")
    df.to_csv(m1 / "WUSDT_features_5m.csv", index=False)
    cases.append(("M1 value->missing", base, m1, 1))

    # M2: missing -> value (WUSDT row 5 rsi14 NaN -> 50.0).
    m2 = mutant("M2_missing_valor")
    df = pd.read_csv(m2 / "WUSDT_features_5m.csv")
    assert pd.isna(df.loc[5, "rsi14"])
    df.loc[5, "rsi14"] = 50.0
    df.to_csv(m2 / "WUSDT_features_5m.csv", index=False)
    cases.append(("M2 missing->value", base, m2, 1))

    # M3: numeric change (WUSDT row 100 rsi14 + 1.0).
    m3 = mutant("M3_cambio_numerico")
    df = pd.read_csv(m3 / "WUSDT_features_5m.csv")
    df.loc[100, "rsi14"] = float(df.loc[100, "rsi14"]) + 1.0
    df.to_csv(m3 / "WUSDT_features_5m.csv", index=False)
    cases.append(("M3 numeric change", base, m3, 1))

    # M4: structure change (drop column atr_pct from WUSDT).
    m4 = mutant("M4_estructura")
    df = pd.read_csv(m4 / "WUSDT_features_5m.csv")
    df.drop(columns=["atr_pct"]).to_csv(
        m4 / "WUSDT_features_5m.csv", index=False)
    cases.append(("M4 structure change", base, m4, 1))

    # M5: missing file.
    m5 = mutant("M5_archivo_ausente")
    (m5 / "GTCUSDT_features_5m.csv").unlink()
    cases.append(("M5 missing file", base, m5, 2))

    # M6a: +inf (orig-side) vs -inf (repro-side) at same cell.
    m6a_o = mutant("M6a_posinf")
    df = pd.read_csv(m6a_o / "WUSDT_features_5m.csv")
    df.loc[100, "rsi14"] = float("inf")
    df.to_csv(m6a_o / "WUSDT_features_5m.csv", index=False)
    m6a_r = mutant("M6a_neginf")
    df = pd.read_csv(m6a_r / "WUSDT_features_5m.csv")
    df.loc[100, "rsi14"] = float("-inf")
    df.to_csv(m6a_r / "WUSDT_features_5m.csv", index=False)
    cases.append(("M6a +inf vs -inf", m6a_o, m6a_r, 1))

    # M6b: finite (orig) vs -inf (repro) at same cell.
    m6b = mutant("M6b_finite_neginf")
    df = pd.read_csv(m6b / "WUSDT_features_5m.csv")
    df.loc[100, "rsi14"] = float("-inf")
    df.to_csv(m6b / "WUSDT_features_5m.csv", index=False)
    cases.append(("M6b finite vs -inf", base, m6b, 1))

    # M7: empty csv (0 bytes).
    m7 = mutant("M7_csv_vacio")
    (m7 / "WUSDT_features_5m.csv").write_bytes(b"")
    cases.append(("M7 empty csv", base, m7, 2))

    # M8: garbled csv (binary garbage).
    m8 = mutant("M8_csv_ilegible")
    (m8 / "WUSDT_features_5m.csv").write_bytes(
        bytes(range(256)) * 64)
    cases.append(("M8 garbled csv", base, m8, 2))

    failures = []
    for label, o, r, expected in cases:
        code, data = _run(o, r)
        verdict = data.get("summary", {}).get("verdict", "?")
        ok = code == expected
        print("%-22s exit=%d expected=%d verdict=%s %s"
              % (label, code, expected, verdict,
                 "OK" if ok else "FAIL"))
        if not ok:
            failures.append(label)
    # Sanity: pristine self-comparison must MATCH with exit 0.
    code, data = _run(base, base)
    ok = code == 0 and data["summary"]["verdict"] == "MATCH"
    print("%-22s exit=%d expected=0 verdict=%s %s"
          % ("SELF pristine", code,
             data["summary"]["verdict"], "OK" if ok else "FAIL"))
    if not ok:
        failures.append("SELF pristine")
    if failures:
        print("FAILURES: %s" % failures)
        return 1
    print("ALL %d CASES OK" % (len(cases) + 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
