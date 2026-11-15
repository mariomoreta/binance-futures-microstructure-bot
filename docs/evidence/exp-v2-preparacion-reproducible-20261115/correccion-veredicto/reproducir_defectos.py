#!/usr/bin/env python
"""Reproduccion de los tres defectos del replay publicado (12024146).

Genera una corrida loopback real con el CLI productivo, DETIENE los
proveedores, trabaja sobre copias independientes y ejecuta el replay
PUBLICADO (extraido de git, sin red) contra:
  control   -> copia intacta (debe dar EQUIVALENTE)
  A         -> entry_ms del resultado de ejecucion desplazado +1000 ms
  A-manif   -> A con el hash del manifiesto recalculado (integridad ok)
  B         -> run_id, symbol y startTime de las consultas cambiados
               (cuerpo y hash conservados)
  B-manif   -> B con el hash del manifiesto recalculado
  C         -> operativo_config eliminado del manifiesto

Publica los veredictos del codigo PUBLICADO en resultados_publicado.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(r"C:\proyectos\binance-futures-microstructure-bot")
REPLAY_PUBLICADO = Path(
    r"C:\Users\adonm\AppData\Local\Temp\opencode\repro\replay_publicado.py")
SALIDA = Path(
    r"C:\Users\adonm\AppData\Local\Temp\opencode\repro\resultados_publicado.json")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import tests.test_operativo_replay_offline as ro  # noqa: E402

ENV = dict(os.environ)
ENV["PYTHONPATH"] = os.pathsep.join([
    str(ROOT), str(ROOT / "src"), str(ROOT / "scripts"),
    ENV.get("PYTHONPATH", "")])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def leer_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def escribir_jsonl(path: Path, filas) -> None:
    texto = "".join(
        json.dumps(f, ensure_ascii=False, sort_keys=True) + "\n"
        for f in filas)
    path.write_text(texto, encoding="utf-8", newline="\n")


def copiar(out_dir: Path, nombre: str) -> Path:
    destino = Path(tempfile.mkdtemp(prefix="repro-defectos-")) / nombre
    shutil.copytree(out_dir, destino)
    return destino


def actualizar_hash_manifiesto(run_dir: Path, nombre: str) -> None:
    """Recalcula el hash del manifiesto para un fichero (integridad 'ok')."""
    mp = run_dir / "manifiesto.json"
    manifiesto = json.loads(mp.read_text(encoding="utf-8"))
    manifiesto["files"][nombre]["sha256"] = sha256_file(run_dir / nombre)
    mp.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2,
                             sort_keys=True) + "\n",
                  encoding="utf-8", newline="\n")


def ejecutar_replay_publicado(run_dir: Path, etiqueta: str):
    report = run_dir.parent / ("replay_%s.json" % etiqueta)
    proc = subprocess.run(
        [sys.executable, str(REPLAY_PUBLICADO),
         "--run-dir", str(run_dir), "--out", str(report)],
        capture_output=True, text=True, timeout=300, env=ENV)
    informe = None
    if report.exists():
        informe = json.loads(report.read_text(encoding="utf-8"))
    return {
        "caso": etiqueta,
        "run_dir": str(run_dir),
        "returncode": proc.returncode,
        "estado": (informe or {}).get("veredicto", {}).get("estado"),
        "coincidentes": (informe or {}).get("veredicto", {}).get(
            "coincidentes"),
        "limitaciones": [l.get("motivo")
                         for l in (informe or {}).get("limitaciones", [])],
        "stdout": proc.stdout.strip()[:400],
        "stderr": proc.stderr.strip()[:400],
    }


def main() -> int:
    print("== generando corrida loopback (CLI productivo) ==")
    datos = ro._ejecutar_cli(ro.MOVES_LONG)
    run = datos["run"]
    out_dir = datos["out_dir"]
    try:
        run.shutdown()
        resultados = []

        # control
        control = copiar(out_dir, "control")
        resultados.append(ejecutar_replay_publicado(control, "control"))

        # A: entry_ms +1000 ms en el resultado de ejecucion
        copia_a = copiar(out_dir, "A")
        path = copia_a / "resultado_operativo.jsonl"
        filas = list(leer_jsonl(path))
        n_cambiados = 0
        for f in filas:
            if f.get("entry_ms") is not None:
                f["entry_ms"] = int(f["entry_ms"]) + 1000
                n_cambiados += 1
        escribir_jsonl(path, filas)
        print("A: entry_ms desplazado en %d filas" % n_cambiados)
        resultados.append(ejecutar_replay_publicado(copia_a, "A"))
        copia_a2 = copiar(out_dir, "A_manifiesto_ok")
        path = copia_a2 / "resultado_operativo.jsonl"
        filas = list(leer_jsonl(path))
        for f in filas:
            if f.get("entry_ms") is not None:
                f["entry_ms"] = int(f["entry_ms"]) + 1000
        escribir_jsonl(path, filas)
        actualizar_hash_manifiesto(copia_a2, "resultado_operativo.jsonl")
        resultados.append(ejecutar_replay_publicado(copia_a2, "A-manif"))

        # B: run_id, symbol y startTime de las consultas cambiados
        copia_b = copiar(out_dir, "B")
        path = copia_b / "consultas_klines.jsonl"
        filas = list(leer_jsonl(path))
        n_cambiadas = 0
        for f in filas:
            if f.get("kind") != "consulta_klines_trayectoria":
                continue
            f["run_id"] = "corrida-distinta"
            f["symbol"] = "ZZZUSDT"
            f["params"]["startTime"] = int(f["params"]["startTime"]) + 123
            n_cambiadas += 1
        escribir_jsonl(path, filas)
        print("B: consultas alteradas: %d" % n_cambiadas)
        resultados.append(ejecutar_replay_publicado(copia_b, "B"))
        copia_b2 = copiar(out_dir, "B_manifiesto_ok")
        path = copia_b2 / "consultas_klines.jsonl"
        filas = list(leer_jsonl(path))
        for f in filas:
            if f.get("kind") != "consulta_klines_trayectoria":
                continue
            f["run_id"] = "corrida-distinta"
            f["symbol"] = "ZZZUSDT"
            f["params"]["startTime"] = int(f["params"]["startTime"]) + 123
        escribir_jsonl(path, filas)
        actualizar_hash_manifiesto(copia_b2, "consultas_klines.jsonl")
        resultados.append(ejecutar_replay_publicado(copia_b2, "B-manif"))

        # C: operativo_config eliminado del manifiesto
        copia_c = copiar(out_dir, "C")
        mp = copia_c / "manifiesto.json"
        manifiesto = json.loads(mp.read_text(encoding="utf-8"))
        manifiesto.pop("operativo_config", None)
        mp.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2,
                                 sort_keys=True) + "\n",
                      encoding="utf-8", newline="\n")
        resultados.append(ejecutar_replay_publicado(copia_c, "C"))

        SALIDA.write_text(
            json.dumps(resultados, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
        print("\n== veredictos del replay PUBLICADO (12024146) ==")
        for r in resultados:
            print("%-9s returncode=%d estado=%s" % (
                r["caso"], r["returncode"], r["estado"]))
        return 0
    finally:
        run.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
