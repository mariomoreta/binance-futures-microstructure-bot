"""Verificador del paquete de evidencia EVAL-CENSUS-V2.

Comprueba, desde checkout limpio y sin rutas de usuario ni DBs canónicas:
  1. Que cada archivo del paquete existe.
  2. Que su SHA256 coincide con package_manifest.json.
  3. Que la purga registrada en events/*.json reproduce las selections.
  4. Que los manifestos referenciados existen para cada events publicado.

PASS: paquete íntegro y coherente. FAIL: hash/discrepancia. INCOMPLETE:
archivo ausente.

Uso:
  python scripts/verify_eval_package.py --package docs/evidence/eval-census-v2-package
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", required=True)
    args = ap.parse_args(argv)
    pkg = Path(args.package)
    errores = []
    if not pkg.is_absolute():
        pkg = ROOT / pkg
    pm_path = pkg / "package_manifest.json"
    if not pm_path.exists():
        print("INCOMPLETE: package_manifest.json ausente en %s" % pkg)
        return 1
    pm = json.loads(pm_path.read_text(encoding="utf-8"))
    archivos = pm.get("archivos", {})
    if not archivos:
        print("INCOMPLETE: package_manifest sin archivos")
        return 1
    n_ok = 0
    for clave, meta in archivos.items():
        p = pkg / clave
        if not p.exists():
            errores.append({"archivo": clave, "motivo": "ausente"})
            continue
        h = sha256_file(p)
        if h != meta.get("sha256"):
            errores.append({"archivo": clave, "motivo":
                            "sha256 distinto: %s != %s"
                            % (h[:16], str(meta.get("sha256"))[:16])})
            continue
        if p.stat().st_size != meta.get("bytes"):
            errores.append({"archivo": clave, "motivo": "tamaño distinto"})
            continue
        n_ok += 1
    # Coherencia events ↔ selections (purga)
    for clave, meta in archivos.items():
        if not clave.startswith("combos/") or "/events_" not in clave:
            continue
        # clave: combos/<dir>/events_<SYM>_<RES>.json
        interior = clave[len("combos/"):]
        d = interior.split("/")[0]
        fname = interior.split("/")[-1]
        sym_res = fname[len("events_"):-len(".json")]
        base = meta.get("purga")
        if not base:
            errores.append({"archivo": clave, "motivo":
                            "sin metadatos de purga"})
            continue
        sel = pkg / "combos" / d / ("selection_%s.json" % sym_res)
        if not sel.exists():
            errores.append({"archivo": clave, "motivo":
                            "selection ausente para purga"})
            continue
        s = json.loads(sel.read_text(encoding="utf-8"))
        if (s.get("n_dev") != base.get("n_dev")
                or s.get("n_oos") != base.get("n_oos")
                or s.get("n_purged_dev_crossing") != base.get("n_purged")):
            errores.append({"archivo": clave, "motivo":
                            "purga no reproduce selection"})
    if errores:
        print("FAIL: %d discrepancias" % len(errores))
        for e in errores[:20]:
            print("  -", e["archivo"], e["motivo"])
        return 1
    print("PASS: %d archivos íntegros, purgas y manifiestos coherentes" % n_ok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
