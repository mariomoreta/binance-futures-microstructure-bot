#!/usr/bin/env python
"""Contraste antes/despues: mismo dataset y mismas mutaciones, dos replay.

- 'antes': replay publicado (12024146), resultados_publicado.json
- 'despues': replay corregido (repo), ejecutado AHORA sobre las mismas copias
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(r"C:\proyectos\binance-futures-microstructure-bot")
REPLAY_NUEVO = REPO / "scripts" / "research_operativo_replay.py"
ANTES = Path(r"C:\Users\adonm\AppData\Local\Temp\opencode\repro"
             r"\resultados_publicado.json")
DESPUES = ANES = ANES_PATH = Path(
    r"C:\Users\adonm\AppData\Local\Temp\opencode\repro\resultados_corregido.json")

orden = ["control", "A", "A-manif", "B", "B-manif", "C"]


def main() -> int:
    antes_rows = {r["caso"]: r for r in json.loads(
        ANTES.read_text(encoding="utf-8"))}
    despues_rows = []
    for caso in orden:
        fila = antes_rows[caso]
        run_dir = Path(fila["run_dir"])
        assert run_dir.exists(), run_dir
        report = run_dir.parent / ("replay_corregido_%s.json" % caso)
        proc = subprocess.run(
            [sys.executable, str(REPLAY_NUEVO), "--run-dir", str(run_dir),
             "--out", str(report)],
            capture_output=True, text=True, timeout=300)
        informe = (json.loads(report.read_text(encoding="utf-8"))
                   if report.exists() else {})
        ver = informe.get("veredicto", {})
        despues_rows.append({
            "caso": caso,
            "run_dir": str(run_dir),
            "returncode": proc.returncode,
            "estado": ver.get("estado"),
            "coincidentes": ver.get("coincidentes"),
            "diferentes": ver.get("diferentes"),
            "limitadas": ver.get("limitadas"),
            "motivos": sorted({l.get("motivo")
                               for l in informe.get("limitaciones", [])}),
        })
    DESPUES.write_text(
        json.dumps(despues_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print("%-9s | %-28s | %-28s" % ("caso", "ANTES (12024146)", "DESPUES (corregido)"))
    for a, d in zip([antes_rows[c] for c in orden], despues_rows):
        print("%-9s | rc=%s %s | rc=%s %s" % (
            a["caso"], a["returncode"], a["estado"],
            d["returncode"], d["estado"]))
        if d["motivos"]:
            print("          motivos despues: %s" % ", ".join(d["motivos"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
