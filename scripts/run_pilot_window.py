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

Directorio de salida:
  - modo predeterminado: el piloto recibe el mismo ``--out-dir`` del
    lanzador, de modo que logs y artefactos del piloto comparten
    directorio; si el hijo trae otro ``--out-dir`` distinto, se falla por
    directorios contradictorios,
  - modo comando explicito (tras ``--``): los argumentos del hijo se
    respetan tal cual y no se le inyecta ninguna opcion de
    ``research_pilot.py``.

Uso:
    python scripts/run_pilot_window.py --out-dir <dir> [args del piloto...]
    python scripts/run_pilot_window.py --out-dir <dir> -- <comando> [args...]
"""
from __future__ import annotations

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


def construir_comando(args_extra: Sequence[str],
                      out_dir: Optional[Path] = None) -> List[str]:
    """Comando a ejecutar: el piloto por defecto, o el indicado tras '--'.

    Modo predeterminado: el piloto recibe ``--out-dir <out_dir>`` para que
    logs y artefactos del piloto compartan el mismo directorio. Si el hijo ya
    trae su propio ``--out-dir``, solo se acepta si es el mismo directorio
    (si no, es contradictorio y se falla).

    Modo comando explicito (tras '--'): los argumentos del hijo se respetan
    tal cual. No se le inyecta ninguna opcion de ``research_pilot.py``.
    """
    if args_extra and args_extra[0] == "--":
        resto = list(args_extra[1:])
        if not resto:
            raise ValueError("no hay comando despues de '--'")
        return resto
    comando = [sys.executable, str(PILOTO), *args_extra]
    if out_dir is not None:
        comando = _propagar_out_dir(comando, out_dir)
    return comando


def _directorio_del_hijo(args: Sequence[str]) -> Optional[str]:
    """Valor de ``--out-dir`` presente en los argumentos del hijo, si lo hay."""
    for i, arg in enumerate(args):
        if arg == "--out-dir":
            if i + 1 >= len(args):
                raise ValueError("--out-dir del hijo sin valor")
            return args[i + 1]
        if arg.startswith("--out-dir="):
            return arg.split("=", 1)[1]
    return None


def _mismo_directorio(a: Path, b: Path) -> bool:
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(
        str(Path(b).resolve()))


def _propagar_out_dir(comando: Sequence[str], out_dir: Path) -> List[str]:
    """Anade ``--out-dir`` al comando del piloto si el hijo no lo fija."""
    args_hijo = list(comando[2:])
    valor = _directorio_del_hijo(args_hijo)
    destino = Path(out_dir)
    if valor is not None:
        if _mismo_directorio(Path(valor), destino):
            return list(comando)
        raise ValueError(
            f"directorios contradictorios: --out-dir del hijo {valor!r} no "
            f"coincide con --out-dir del lanzador {str(out_dir)!r}")
    return [*comando, "--out-dir", str(destino.resolve())]


def _extraer_out_dir_del_lanzador(argv: Sequence[str]) -> tuple:
    """Separa el ``--out-dir`` del lanzador del resto de argumentos.

    El lanzador tiene una sola opcion propia: ``--out-dir`` (el primer
    ``--out-dir`` anterior a '--'). Los ``--out-dir`` posteriores pertenecen al
    hijo y se conservan intactos para poder detectar directorios
    contradictorios. Un '--' previo corta la busqueda: a partir de ahi los
    argumentos son del hijo, no del lanzador.
    """
    corte = argv.index("--") if "--" in argv else len(argv)
    for i, arg in enumerate(argv):
        if i >= corte:
            break
        if arg == "--out-dir":
            if i + 1 >= len(argv):
                raise ValueError("--out-dir sin valor")
            return argv[i + 1], list(argv[:i]) + list(argv[i + 2:])
        if arg.startswith("--out-dir="):
            return arg.split("=", 1)[1], list(argv[:i]) + list(argv[i + 1:])
    return None, list(argv)


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


USO = """Uso:
    python scripts/run_pilot_window.py --out-dir <dir> [args del piloto...]
    python scripts/run_pilot_window.py --out-dir <dir> -- <comando> [args...]

El lanzador tiene una sola opcion propia: --out-dir (logs y exit_code.txt).
En modo predeterminado el piloto recibe ese mismo --out-dir, para que logs y
artefactos compartan directorio. Tras '--' los argumentos son del hijo y se
respetan tal cual: no se le inyecta ninguna opcion de research_pilot.py.
"""


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(USO, end="")
        return 0
    try:
        valor_out_dir, resto = _extraer_out_dir_del_lanzador(argv)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    if valor_out_dir is None:
        print(json.dumps({
            "error": "--out-dir es obligatorio (directorio de logs y "
                     "exit_code.txt)"}), file=sys.stderr)
        return 2
    try:
        comando = construir_comando(resto, out_dir=Path(valor_out_dir))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    return ejecutar(comando, Path(valor_out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
