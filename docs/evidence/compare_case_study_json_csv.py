"""
Comparacion estructurada caso W/LUMIA: originales vs re-ejecucion aislada.

Uso (los originales NO se tocan; ORIG_DIR y REPRO_DIR se pasan por argv):
  $env:PYTHONUTF8='1'
  python docs/evidence/compare_case_study_json_csv.py <ORIG_DIR> <REPRO_DIR>

Compara JSON parseado con tolerancia 1e-12, CSV por forma/columnas y
diferencia numerica maxima, y reporta hashes SHA256 de bytes.
El PNG solo se compara por hash Tamanio; la equivalencia visual NO se
declara (PNG no inspeccionado visualmente).
"""
import json, math, hashlib, pathlib, sys


def compare_values(a, b, path, diffs):
    if isinstance(a, dict) and isinstance(b, dict):
        ka, kb = set(a.keys()), set(b.keys())
        if ka != kb:
            diffs.append(path + ": keys only-orig=" + str(ka - kb) + " only-repro=" + str(kb - ka))
        for k in sorted(ka & kb):
            compare_values(a[k], b[k], path + "." + k, diffs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(path + ": len " + str(len(a)) + " vs " + str(len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            compare_values(x, y, path + "[" + str(i) + "]", diffs)
    elif isinstance(a, float) and isinstance(b, float):
        ok = (a == b) or (math.isfinite(a) and math.isfinite(b)
                          and abs(a - b) <= 1e-12 * max(1, abs(a), abs(b)))
        if not ok:
            diffs.append(path + ": FLOAT DIFF " + repr(a) + " vs " + repr(b))
    else:
        if a != b:
            diffs.append(path + ": DIFF " + repr(a)[:300] + " vs " + repr(b)[:300])
    return diffs


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def main():
    orig = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("binance_case_study")
    repro = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None
    out = {"json": {}, "csv": {}, "png": {}}
    for name in ["analysis_summary.json", "supplemental_analysis.json"]:
        o = json.loads((orig / name).read_text(encoding="utf-8"))
        entry = {"orig_bytes": len((orig / name).read_bytes()), "orig_sha256": sha(orig / name)}
        if repro is not None and (repro / name).exists():
            r = json.loads((repro / name).read_text(encoding="utf-8"))
            diffs = compare_values(o, r, "root", [])
            entry.update({"repro_bytes": len((repro / name).read_bytes()),
                          "repro_sha256": sha(repro / name),
                          "parsed_diffs": len(diffs),
                          "parsed_diff_sample": diffs[:20],
                          "byte_identical": sha(orig / name) == sha(repro / name)})
        out["json"][name] = entry
    try:
        import pandas as pd
        for sym in ["WUSDT", "LUMIAUSDT", "BTCUSDT", "GTCUSDT"]:
            name = sym + "_features_5m.csv"
            a = pd.read_csv(orig / name)
            entry = {"orig_bytes": len((orig / name).read_bytes()), "orig_sha256": sha(orig / name),
                     "orig_shape": list(a.shape), "orig_columns": list(a.columns)}
            if repro is not None and (repro / name).exists():
                b = pd.read_csv(repro / name)
                entry.update({"repro_bytes": len((repro / name).read_bytes()),
                              "repro_sha256": sha(repro / name),
                              "repro_shape": list(b.shape),
                              "columns_match": list(a.columns) == list(b.columns),
                              "byte_identical": sha(orig / name) == sha(repro / name)})
                if list(a.columns) == list(b.columns) and a.shape == b.shape:
                    num = a.select_dtypes("number").columns
                    md = 0.0
                    for c in num:
                        d = (a[c] - b[c]).abs().max(skipna=True)
                        if d == d and d > md:
                            md = float(d)
                    non = [c for c in a.columns if c not in num]
                    exact = all((a[c].fillna("<NA>").astype(str) == b[c].fillna("<NA>").astype(str)).all()
                                for c in non)
                    entry.update({"max_abs_numeric_diff": md, "non_numeric_exact": bool(exact),
                                  "non_numeric_columns": non})
            out["csv"][name] = entry
    except ImportError:
        out["csv"]["note"] = "pandas no disponible; comparacion CSV omitida"
    for name in ["Casos_Binance_W_LUMIA.png"]:
        entry = {}
        if (orig / name).exists():
            entry = {"orig_bytes": len((orig / name).read_bytes()), "orig_sha256": sha(orig / name)}
        if repro is not None and (repro / name).exists():
            entry.update({"repro_bytes": len((repro / name).read_bytes()),
                          "repro_sha256": sha(repro / name),
                          "byte_identical": sha(orig / name) == sha(repro / name),
                          "visual_equivalence": "NOT_ASSESSED (PNG no inspeccionado visualmente)"})
        out["png"][name] = entry
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

