"""Paquete compacto de evidencia EVAL-CENSUS-V2 (verificable sin temp).

Copia al out_dir, con estructura clara, los inputs externos necesarios
para verificar la auditoría y regenerar el ledger y las trazas SIN
depender de rutas del usuario adonm ni de canónicos locales:

  package_manifest.json   hashes SHA256, versiones, comandos, tamaños
  manifests/              manifiestos del runner (post-corrida)
  events/                 events POST-purge (entrada real del runner;
                          la purga de select_eval_events.py se replica
                          determinísticamente desde events pre-purge)
  selections/             informes de selección/purga
  build_reports/          conteos del builder (admitidas/descartadas)
  funding/                calendarios funding por símbolo
  detections/             detecciones del reconstruct (censo causal)
  candles/                barras mismas-grid (input del replay)

Los trades reconstruidos (trades_*.json) NO se publican: son salida
determinista de scripts/reconstruct_replay_traces.py desde
events+candles+manifests+funding (comando documentado en el manifiesto).

Excluye por diseño: DBs canónicas, secretos, backups, logs, archivos
ajenos y el árbol completo de temp/opencode.

Uso:
  python scripts/build_eval_package.py --temp-dir <dir> --out-dir <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COMBOS = [
    ("eval15_btc", "BTCUSDT", "15m"),
    ("eval15_ethsol", "ETHUSDT", "15m"),
    ("eval15_ethsol", "SOLUSDT", "15m"),
    ("eval1h_trio", "BTCUSDT", "1h"),
    ("eval1h_trio", "ETHUSDT", "1h"),
    ("eval1h_trio", "SOLUSDT", "1h"),
]
CENSUS_DIRS = ["census_btc15", "census_ethsol15", "census_1h"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _copiar(origen: Path, destino: Path, clave: str, registro: dict) -> bool:
    if not origen.exists():
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origen, destino)
    registro[clave] = {
        "bytes": origen.stat().st_size,
        "sha256": sha256_file(origen),
    }
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--temp-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    temp = Path(args.temp_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    registro = {}
    omitidos = []
    for d, sym, res in COMBOS:
        base = temp / d
        cdir = out / "combos" / d
        man_p = base / ("manifest_%s_%s.json" % (sym, res))
        if not man_p.exists():
            omitidos.append(str(man_p.relative_to(temp)))
            continue
        man = json.loads(man_p.read_text(encoding="utf-8"))
        cutoff = int(man["cutoff_ms"])
        horizon = int(man["exit_horizon_ms"])
        # events pre-purge → post-purge (réplica determinista de
        # select_eval_events.py)
        ep = base / ("events_%s_%s.json" % (sym, res))
        rows = json.loads(ep.read_text(encoding="utf-8"))
        dev = [r for r in rows if int(r["event_time_ms"]) + horizon <= cutoff]
        oos = [r for r in rows if int(r["event_time_ms"]) >= cutoff]
        post = dev + oos
        destino_ev = cdir / ("events_%s_%s.json" % (sym, res))
        destino_ev.parent.mkdir(parents=True, exist_ok=True)
        destino_ev.write_text(json.dumps(post), encoding="utf-8")
        registro["combos/%s/events_%s_%s.json" % (d, sym, res)] = {
            "bytes": destino_ev.stat().st_size,
            "sha256": sha256_file(destino_ev),
            "purga": {"n_in": len(rows), "n_dev": len(dev),
                      "n_oos": len(oos),
                      "n_purged": len(rows) - len(dev) - len(oos)},
        }
        _copiar(base / ("manifest_%s_%s.json" % (sym, res)),
                cdir / ("manifest_%s_%s.json" % (sym, res)),
                "combos/%s/manifest_%s_%s.json" % (d, sym, res), registro)
        for sub, fname in [("selections", "selection_%s_%s.json" % (sym, res)),
                           ("candles", "candles_%s_%s.json" % (sym, res))]:
            p = base / fname
            if p.exists():
                _copiar(p, cdir / fname, "combos/%s/%s" % (d, fname),
                        registro)
            else:
                omitidos.append(str(p.relative_to(temp)))
        br = base / "build_report.json"
        if br.exists():
            _copiar(br, cdir / "build_report.json",
                    "combos/%s/build_report.json" % d, registro)
        fp = temp / ("funding_%s.json" % sym)
        if fp.exists():
            _copiar(fp, out / "funding" / ("funding_%s.json" % sym),
                    "funding/funding_%s.json" % sym, registro)
        else:
            omitidos.append(str(fp.relative_to(temp)))
    for dname in CENSUS_DIRS:
        cp = temp / dname / "detections.jsonl"
        if cp.exists():
            _copiar(cp, out / "detections" / ("%s_detections.jsonl" % dname),
                    "detections/%s_detections.jsonl" % dname, registro)
        else:
            omitidos.append(str(cp.relative_to(temp)))

    manif = {
        "paquete": "EVAL-CENSUS-V2 evidence package",
        "generado_por": "scripts/build_eval_package.py",
        "raiz_repo": "docs/evidence/eval-census-v2-package",
        "archivos": registro,
        "omitidos": omitidos,
        "comandos": {
            "verificar_paquete": "python scripts/verify_eval_package.py "
                                 "--package docs/evidence/eval-census-v2-package",
            "regenerar_ledger": "python scripts/audit_offline_eval_ledger.py "
                                "--package docs/evidence/eval-census-v2-package "
                                "--out docs/evidence/audit_offline_eval_ledger.json",
            "reconstruir_trazas": "python scripts/reconstruct_replay_traces.py "
                                  "--package docs/evidence/eval-census-v2-package "
                                  "--out-dir <dir-temp>",
        },
        "depende_de": "inputs públicos de Binance (klines, funding) y del "
                     "censo reconstruido; NO depende de rutas de usuario "
                     "ni de DBs canónicas locales.",
    }
    (out / "package_manifest.json").write_text(
        json.dumps(manif, indent=1, default=str), encoding="utf-8")
    print("paquete: %d archivos, omitidos=%d, verificación=%s"
          % (len(registro), len(omitidos),
             "pendiente (usar verify_eval_package.py)"))
    return 0 if not omitidos else 1


if __name__ == "__main__":
    raise SystemExit(main())
