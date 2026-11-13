"""Ejecucion REAL en Windows del lanzador ya corregido (casos cortos).

Genera la evidencia de la correccion de los dos defectos materiales:

- plazo global: toda espera se acota al restante del MISMO deadline y la
  duracion publicada incluye la persistencia del lanzador;
- cierre con evidencia: se separa lo SOLICITADO (parada, terminacion
  forzada) de lo OBSERVADO (terminacion del hijo, codigo de salida) y el
  lanzador no certifica los sockets del hijo.

Procesos locales triviales: sin red, sin mercado, sin cuentas ni datasets.
Duraciones de segundos (NO son las de produccion).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
LANZADOR = RAIZ / "scripts" / "run_pilot_window.py"
DESTINO = Path(__file__).resolve().parent / "windows_real"

HITO_NORMAL = "import sys; sys.exit({codigo})"

HITO_PARADA_LIMPIA = """
import signal, sys, time
def _parada(signum, frame):
    print('parada limpia recibida', flush=True)
    sys.exit(0)
signal.signal(signal.SIGINT, _parada)
if hasattr(signal, 'SIGBREAK'):
    signal.signal(signal.SIGBREAK, _parada)
print('trabajando', flush=True)
fin = time.monotonic() + 60
while time.monotonic() < fin:
    time.sleep(0.2)
"""

HITO_IGNORA = """
import signal, time
for _nombre in ('SIGINT', 'SIGTERM', 'SIGBREAK'):
    _senal = getattr(signal, _nombre, None)
    if _senal is not None:
        try:
            signal.signal(_senal, signal.SIG_IGN)
        except Exception:
            pass
print('trabajando e ignora cualquier parada', flush=True)
time.sleep(60)
"""


def _vivo(pid: int) -> bool:
    if os.name == "nt":
        res = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True, errors="replace")
        return str(pid) in res.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _caso(nombre: str, cuerpo: str, trabajo: float | None,
          margen: float | None) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="win-real-"))
    try:
        hijo = tmp / "hijo.py"
        hijo.write_text(cuerpo, encoding="utf-8")
        out = DESTINO / nombre
        if out.exists():
            shutil.rmtree(out)
        cmd = [sys.executable, str(LANZADOR), "--out-dir", str(out)]
        if trabajo is not None:
            cmd += ["--work-timeout-seconds", str(trabajo),
                    "--shutdown-grace-seconds", str(margen)]
        cmd += ["--", sys.executable, str(hijo)]
        inicio = time.monotonic()
        proc = subprocess.run(cmd, cwd=str(RAIZ), capture_output=True,
                              text=True, timeout=180)
        elapsed = time.monotonic() - inicio
        estado = json.loads((out / "estado_lanzador.json").read_text(
            encoding="utf-8"))
        final = json.loads((out / "cierre.json").read_text(encoding="utf-8"))
        return {
            "caso": nombre,
            "codigo_lanzador_observado": proc.returncode,
            "stderr_del_lanzador": proc.stderr,
            "duracion_real_de_pared_s": round(elapsed, 3),
            "resultado": estado["resultado"],
            "causa_terminacion": estado["causa_terminacion"],
            "cumplimiento_normal": estado["cumplimiento_normal"],
            "cierre": estado["cierre"],
            "tiempos": estado["tiempos"],
            "cierre_definitivo": final,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    casos = [
        _caso("normal", HITO_NORMAL.format(codigo=0), None, None),
        _caso("limpio", HITO_PARADA_LIMPIA, 1, 8),
        _caso("forzado", HITO_IGNORA, 1, 4),
    ]
    (DESTINO / "resultados.json").write_text(
        json.dumps({"casos": casos}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for caso in casos:
        print(json.dumps({
            "caso": caso["caso"],
            "codigo_lanzador_observado": caso["codigo_lanzador_observado"],
            "resultado": caso["resultado"],
            "cumplimiento_normal": caso["cumplimiento_normal"],
            "duracion_total_s": caso["cierre_definitivo"]["duracion_total_s"],
            "duracion_persistencia_s": caso["cierre_definitivo"][
                "duracion_persistencia_s"],
            "exceso_maximo_total_s": caso["cierre_definitivo"][
                "exceso_maximo_total_s"],
            "incumplimiento_plazo_global": caso["cierre_definitivo"][
                "incumplimiento_plazo_global"],
            "terminacion_hijo_observada": caso["cierre"][
                "terminacion_hijo_observada"],
            "codigo_salida_estado": caso["cierre"]["codigo_salida_estado"],
            "recursos_hijo": caso["cierre"]["recursos_hijo"],
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
