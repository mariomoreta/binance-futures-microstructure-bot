"""Envoltorio de lanzamiento del piloto: captura el codigo de salida REAL.

Corre ``scripts/research_pilot.py`` (o el comando que se indique tras ``--``),
espera su finalizacion real y persiste en el directorio de la corrida:

  - ``stdout.log`` / ``stderr.log``: salida del proceso hijo,
  - ``exit_code.txt``: codigo numerico real, leido del proceso terminado,
  - ``launcher.json``: comando, returncode, inicio, fin y duracion.

Regla: el codigo de salida NUNCA se infiere de ``phase=fin``, de un stdout
con ``"estado": "completo"`` ni de un stderr vacio. Se lee de
``Popen.wait()``, que es el mecanismo de la plataforma que informa del
codigo real de terminacion. Si el proceso muere por una senal, el valor
negativo que reporta la plataforma se conserva tal cual.

Uso:
    python scripts/run_pilot_window.py --out-dir <dir> [args del piloto...]
    python scripts/run_pilot_window.py --out-dir <dir> -- <comando> [args...]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
PILOTO = ROOT / "scripts" / "research_pilot.py"


def _escribir_atomico(destino: Path, texto: str) -> None:
    """Escritura atomica: tmp + os.replace (el lector nunca ve medio fichero)."""
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, destino)


def construir_comando(args_extra: Sequence[str]) -> List[str]:
    """Comando a ejecutar: el piloto por defecto, o el indicado tras '--'."""
    if args_extra and args_extra[0] == "--":
        resto = list(args_extra[1:])
        if not resto:
            raise ValueError("no hay comando despues de '--'")
        return resto
    return [sys.executable, str(PILOTO), *args_extra]


def ejecutar(comando: Sequence[str], out_dir: Path,
             cwd: Optional[Path] = None) -> int:
    """Ejecuta el comando, espera su finalizacion real y persiste la evidencia.

    Devuelve el codigo de salida real del proceso (el mismo que se persiste).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = out_dir / "stdout.log"
    stderr_path = out_dir / "stderr.log"
    exit_path = out_dir / "exit_code.txt"
    meta_path = out_dir / "launcher.json"

    inicio_wall = time.time()
    inicio_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(inicio_wall))
    interrumpido = False
    with open(stdout_path, "wb") as fout, open(stderr_path, "wb") as ferr:
        proc = subprocess.Popen(
            list(comando), cwd=str(cwd or ROOT), stdout=fout, stderr=ferr)
        try:
            # Espera de la finalizacion REAL del proceso: wait() devuelve el
            # codigo de salida numerico de la plataforma.
            returncode = proc.wait()
        except KeyboardInterrupt:
            interrumpido = True
            proc.terminate()
            try:
                returncode = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                returncode = proc.wait()
    fin_wall = time.time()

    _escribir_atomico(exit_path, f"{returncode}\n")
    meta = {
        "comando": list(comando),
        "returncode": returncode,
        "exit_code": returncode,
        "fuente_del_codigo": "Popen.wait() (codigo real del proceso)",
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "inicio_iso_utc": inicio_iso,
        "fin_iso_utc": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(fin_wall)),
        "duracion_s": round(fin_wall - inicio_wall, 3),
        "interrumpido": interrumpido,
    }
    _escribir_atomico(meta_path, json.dumps(meta, ensure_ascii=False, indent=1))
    print(json.dumps(meta, ensure_ascii=False), flush=True)
    return int(returncode)


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Lanza el piloto y persiste el codigo de salida real.")
    parser.add_argument("--out-dir", required=True,
                        help="directorio donde persistir logs y exit_code.txt")
    # Los flags del hijo (piloto) no se interpretan aqui: se reenvian tal cual.
    ns, resto = parser.parse_known_args(argv)
    try:
        comando = construir_comando(resto)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    return ejecutar(comando, Path(ns.out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
