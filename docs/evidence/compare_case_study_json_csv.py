"""
Comparacion estructurada caso W/LUMIA: originales vs re-ejecucion aislada.

Uso (los originales NO se tocan; ORIG_DIR y REPRO_DIR se pasan por argv):
  $env:PYTHONUTF8='1'
  python docs/evidence/compare_case_study_json_csv.py <ORIG_DIR> <REPRO_DIR> [--out SALIDA.json]

Reglas:
- Compara mascaras de valores ausentes ANTES que diferencias numericas.
- Detecta cambios de tipo y valores especiales (NaN/inf/-inf/None).
- No omite silenciosamente archivos, columnas ni comparaciones: todo lo
  esperado ausente o ilegible se registra como INCOMPLETE.
- Codigo de salida: 0 comparacion completa sin diferencias; 1 diferencias;
  2 comparacion incompleta (archivos ausentes, JSON ilegible, pandas
  ausente). El PNG se reporta por hash/tamanio pero NO cuenta para el exit
  (render dependiente del entorno; equivalencia visual NOT_ASSESSED).
- Salida JSON textual en UTF-8 (stdout y --out con ensure_ascii=False).
"""
import json, math, hashlib, pathlib, sys

EXPECTED_JSON = ["analysis_summary.json", "supplemental_analysis.json"]
EXPECTED_CSV = ["WUSDT_features_5m.csv", "LUMIAUSDT_features_5m.csv",
                "BTCUSDT_features_5m.csv", "GTCUSDT_features_5m.csv"]
EXPECTED_PNG = ["Casos_Binance_W_LUMIA.png"]
TOL = 1e-12


def type_name(x):
    if x is None:
        return "NoneType"
    if isinstance(x, bool):
        return "bool"
    if isinstance(x, int):
        return "int"
    if isinstance(x, float):
        if math.isnan(x):
            return "float(NaN)"
        if math.isinf(x):
            return "float(inf)" if x > 0 else "float(-inf)"
        return "float"
    if isinstance(x, str):
        return "str"
    if isinstance(x, list):
        return "list"
    if isinstance(x, dict):
        return "dict"
    return type(x).__name__


def compare_values(a, b, path, diffs):
    ta, tb = type_name(a), type_name(b)
    if ta != tb:
        diffs.append(path + ": TYPE_CHANGE " + ta + " vs " + tb
                     + " (" + repr(a)[:160] + " vs " + repr(b)[:160] + ")")
        return diffs
    if isinstance(a, dict):
        ka, kb = set(a.keys()), set(b.keys())
        if ka != kb:
            diffs.append(path + ": keys only-orig=" + str(sorted(ka - kb))
                         + " only-repro=" + str(sorted(kb - ka)))
        for k in sorted(ka & kb):
            compare_values(a[k], b[k], path + "." + k, diffs)
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(path + ": len " + str(len(a)) + " vs " + str(len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            compare_values(x, y, path + "[" + str(i) + "]", diffs)
    elif isinstance(a, float):
        if math.isnan(a) and math.isnan(b):
            return diffs
        ok = (a == b) or (math.isfinite(a) and math.isfinite(b)
                          and abs(a - b) <= TOL * max(1, abs(a), abs(b)))
        if not ok:
            diffs.append(path + ": FLOAT_DIFF " + repr(a) + " vs " + repr(b))
    else:
        if a != b:
            diffs.append(path + ": DIFF " + repr(a)[:300] + " vs " + repr(b)[:300])
    return diffs


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def main():
    raw = sys.argv[1:]
    out_path = None
    args = []
    i = 0
    while i < len(raw):
        if raw[i] == "--out" and i + 1 < len(raw):
            out_path = pathlib.Path(raw[i + 1])
            i += 2
        else:
            args.append(raw[i])
            i += 1
    orig = pathlib.Path(args[0]) if len(args) > 0 else pathlib.Path("binance_case_study")
    repro = pathlib.Path(args[1]) if len(args) > 1 else None
    out = {"json": {}, "csv": {}, "png": {},
           "summary": {"differences": 0, "incomplete": []}}
    n_diffs = 0

    for name in EXPECTED_JSON:
        entry = {}
        po = orig / name
        pr = (repro / name) if repro is not None else None
        if not po.exists():
            entry["status"] = "INCOMPLETE_ORIG_MISSING"
            out["summary"]["incomplete"].append("orig/" + name)
            out["json"][name] = entry
            continue
        try:
            o = json.loads(po.read_text(encoding="utf-8"))
        except Exception as e:
            entry["status"] = "INCOMPLETE_ORIG_UNREADABLE"
            entry["error"] = str(e)[:300]
            out["summary"]["incomplete"].append("orig/" + name + " unreadable")
            out["json"][name] = entry
            continue
        entry = {"orig_bytes": len(po.read_bytes()), "orig_sha256": sha(po)}
        if pr is None or not pr.exists():
            entry["status"] = "INCOMPLETE_REPRO_MISSING"
            out["summary"]["incomplete"].append("repro/" + name + " missing")
            out["json"][name] = entry
            continue
        try:
            r = json.loads(pr.read_text(encoding="utf-8"))
        except Exception as e:
            entry["status"] = "INCOMPLETE_REPRO_UNREADABLE"
            entry["error"] = str(e)[:300]
            out["summary"]["incomplete"].append("repro/" + name + " unreadable")
            out["json"][name] = entry
            continue
        diffs = compare_values(o, r, "root", [])
        entry.update({"repro_bytes": len(pr.read_bytes()),
                      "repro_sha256": sha(pr),
                      "parsed_diffs": len(diffs),
                      "parsed_diff_sample": diffs[:20],
                      "byte_identical": sha(po) == sha(pr),
                      "status": "MATCH" if not diffs else "DIFFERENT"})
        n_diffs += len(diffs)
        out["json"][name] = entry

    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        out["csv"]["status"] = "INCOMPLETE_PANDAS_MISSING"
        out["summary"]["incomplete"].append("pandas missing: CSV comparison impossible")
        pd = None

    if pd is not None:
        for name in EXPECTED_CSV:
            entry = {}
            po = orig / name
            pr = (repro / name) if repro is not None else None
            if not po.exists():
                entry["status"] = "INCOMPLETE_ORIG_MISSING"
                out["summary"]["incomplete"].append("orig/" + name)
                out["csv"][name] = entry
                continue
            try:
                a = pd.read_csv(po)
            except Exception as e:
                entry["status"] = "INCOMPLETE_ORIG_UNREADABLE"
                entry["error"] = "csv unreadable/empty: " + str(e)[:200]
                out["summary"]["incomplete"].append("orig/" + name + " unreadable")
                out["csv"][name] = entry
                continue
            if a.shape[1] == 0:
                entry["status"] = "INCOMPLETE_ORIG_EMPTY"
                entry["error"] = "csv has no columns"
                out["summary"]["incomplete"].append("orig/" + name + " empty")
                out["csv"][name] = entry
                continue
            entry = {"orig_bytes": len(po.read_bytes()), "orig_sha256": sha(po),
                     "orig_shape": list(a.shape), "orig_columns": list(a.columns)}
            if pr is None or not pr.exists():
                entry["status"] = "INCOMPLETE_REPRO_MISSING"
                out["summary"]["incomplete"].append("repro/" + name + " missing")
                out["csv"][name] = entry
                continue
            try:
                b = pd.read_csv(pr)
            except Exception as e:
                entry["status"] = "INCOMPLETE_REPRO_UNREADABLE"
                entry["error"] = "csv unreadable/empty: " + str(e)[:200]
                out["summary"]["incomplete"].append("repro/" + name + " unreadable")
                out["csv"][name] = entry
                continue
            if b.shape[1] == 0:
                entry["status"] = "INCOMPLETE_REPRO_EMPTY"
                entry["error"] = "csv has no columns"
                out["summary"]["incomplete"].append("repro/" + name + " empty")
                out["csv"][name] = entry
                continue
            entry.update({"repro_bytes": len(pr.read_bytes()),
                          "repro_sha256": sha(pr),
                          "repro_shape": list(b.shape),
                          "columns_match": list(a.columns) == list(b.columns),
                          "byte_identical": sha(po) == sha(pr)})
            file_diffs = []
            if list(a.columns) != list(b.columns):
                file_diffs.append("COLUMNS orig=" + str(list(a.columns))
                                  + " repro=" + str(list(b.columns)))
            if a.shape != b.shape:
                file_diffs.append("SHAPE " + str(a.shape) + " vs " + str(b.shape))
            if file_diffs:
                entry.update({"status": "DIFFERENT", "structure_diffs": file_diffs})
                n_diffs += len(file_diffs)
                out["csv"][name] = entry
                continue
            mask_report, mask_diffs = {}, []
            for c in a.columns:
                ma, mb = a[c].isna(), b[c].isna()
                ca, cb = int(ma.sum()), int(mb.sum())
                pos = [int(idx) for idx in (ma != mb)[(ma != mb)].index.tolist()[:10]]
                mask_report[c] = {"orig_missing": ca, "repro_missing": cb,
                                  "positions_differ": bool(pos), "sample_rows": pos}
                if ca != cb or pos:
                    mask_diffs.append("MISSING_MASK " + c + ": orig_na=" + str(ca)
                                      + " repro_na=" + str(cb) + " rows=" + str(pos))
            type_diffs, special_report = [], {}
            for c in a.columns:
                da, db = str(a[c].dtype), str(b[c].dtype)
                row = {"orig_dtype": da, "repro_dtype": db}
                if da != db:
                    type_diffs.append("DTYPE_CHANGE " + c + ": " + da + " vs " + db)
                if pd.api.types.is_numeric_dtype(a[c]):
                    an = pd.to_numeric(a[c], errors="coerce").to_numpy(dtype="float64")
                    bn = pd.to_numeric(b[c], errors="coerce").to_numpy(dtype="float64")
                    pa = set(int(idx) for idx in np.where(np.isposinf(an))[0].tolist())
                    pb = set(int(idx) for idx in np.where(np.isposinf(bn))[0].tolist())
                    na = set(int(idx) for idx in np.where(np.isneginf(an))[0].tolist())
                    nb = set(int(idx) for idx in np.where(np.isneginf(bn))[0].tolist())
                    fa = set(int(idx) for idx in np.where(np.isfinite(an))[0].tolist())
                    fb = set(int(idx) for idx in np.where(np.isfinite(bn))[0].tolist())
                    row.update({"orig_pos_inf": len(pa), "repro_pos_inf": len(pb),
                                "orig_neg_inf": len(na), "repro_neg_inf": len(nb)})
                    if pa != pb or na != nb:
                        type_diffs.append(
                            "SPECIAL_INF " + c + ": orig(+inf@%s,-inf@%s) repro(+inf@%s,-inf@%s)"
                            % (sorted(pa)[:10], sorted(na)[:10],
                               sorted(pb)[:10], sorted(nb)[:10]))
                    if fa != fb:
                        type_diffs.append(
                            "FINITE_MASK " + c + ": finite-position sets differ "
                            "(orig_only=%s repro_only=%s)"
                            % (sorted(fa - fb)[:10], sorted(fb - fa)[:10]))
                special_report[c] = row
            md, md_col = 0.0, None
            for c in a.columns:
                if not pd.api.types.is_numeric_dtype(a[c]):
                    continue
                an = pd.to_numeric(a[c], errors="coerce").to_numpy(dtype="float64")
                bn = pd.to_numeric(b[c], errors="coerce").to_numpy(dtype="float64")
                both = ~(np.isnan(an) | np.isnan(bn)) & np.isfinite(an) & np.isfinite(bn)
                if both.any():
                    d = float(np.abs(an[both] - bn[both]).max())
                    if d > md:
                        md, md_col = d, c
            num_diffs = []
            if md > TOL * max(1.0, md):
                num_diffs.append("NUMERIC_DIFF max_abs=" + repr(md) + " col=" + str(md_col))
            non = [c for c in a.columns if not pd.api.types.is_numeric_dtype(a[c])]
            exact = all((a[c].fillna("<NA>").astype(str) == b[c].fillna("<NA>").astype(str)).all()
                        for c in non) if non else True
            if not exact:
                num_diffs.append("NON_NUMERIC_MISMATCH")
            all_diffs = mask_diffs + type_diffs + num_diffs
            entry.update({"missing_masks": mask_report,
                          "dtype_special": special_report,
                          "max_abs_numeric_diff": md,
                          "max_abs_numeric_diff_col": md_col,
                          "non_numeric_exact": bool(exact),
                          "non_numeric_columns": non,
                          "csv_diffs": len(all_diffs),
                          "csv_diff_sample": all_diffs[:20],
                          "status": "MATCH" if not all_diffs else "DIFFERENT"})
            n_diffs += len(all_diffs)
            out["csv"][name] = entry

    for name in EXPECTED_PNG:
        entry = {}
        po = orig / name
        pr = (repro / name) if repro is not None else None
        if po.exists():
            entry = {"orig_bytes": len(po.read_bytes()), "orig_sha256": sha(po)}
        else:
            entry = {"status": "ORIG_MISSING"}
        if pr is not None and pr.exists():
            entry.update({"repro_bytes": len(pr.read_bytes()),
                          "repro_sha256": sha(pr),
                          "byte_identical": sha(po) == sha(pr) if po.exists() else False,
                          "visual_equivalence": "NOT_ASSESSED (PNG no inspeccionado visualmente)",
                          "note": "PNG excluido del exit code (render dependiente del entorno)"})
        out["png"][name] = entry

    out["summary"]["differences"] = n_diffs
    out["summary"]["verdict"] = ("INCOMPLETE" if out["summary"]["incomplete"]
                                 else ("DIFFERENT" if n_diffs else "MATCH"))
    text = json.dumps(out, indent=2, ensure_ascii=False)
    if out_path is not None:
        out_path.write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")
    if out["summary"]["incomplete"]:
        return 2
    return 1 if n_diffs else 0


if __name__ == "__main__":
    sys.exit(main())
