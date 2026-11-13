"""Reproduccion determinista de los DOS defectos publicados del lanzador.

Se ejecuta contra el codigo PUBLICADO de ``scripts/run_pilot_window.py``
(commit d53d8ad) y se puede volver a ejecutar contra el codigo corregido
pasando la ruta del modulo como argumento.

Que reproduce:

A. LAS ESPERAS DE TERMINACION PUEDEN SUPERAR EL PLAZO GLOBAL.
   El caso de referencia es el del enunciado: trabajo 1 s, margen 4 s,
   total 5 s, ``taskkill`` que no responde y un hijo que no confirma su
   salida. La ruta publicada concede a ``taskkill`` hasta 30 s y despues
   espera hasta 10 s mas al hijo: 3 s (hasta el deadline de terminacion
   forzada) + 30 s + 10 s = **43 s simulados** frente a un plazo global
   de 5 s.

B. EL LANZADOR ACREDITA RECURSOS CERRADOS SIN EVIDENCIA SUFICIENTE.
   Cuando el codigo del hijo NO se observa, el estado publicado sigue
   declarando ``proceso_hijo_terminado: true`` (porque se *"intento"* matar)
   y ``alimentaciones_cerradas: true`` (incondicional), aunque el proceso
   pueda seguir vivo y el lanzador no pueda certificar los sockets del hijo.

Como se simula: se sustituyen ``subprocess.Popen``, ``subprocess.run`` y
``os.kill`` por dobles que REGISTRAN el tiempo concedido a cada espera y
nunca esperan de verdad. Por eso la simulacion es instantanea y
determinista: **no es una ejecucion real en Windows** (la ejecucion real
esta en los casos D y H de ``tests/test_pilot_launcher_temporal.py``).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
LANZADOR_POR_DEFECTO = RAIZ / "scripts" / "run_pilot_window.py"


class _HijoFalso:
    """Proceso simulado: nunca confirma su salida."""

    def __init__(self) -> None:
        self.pid = 424242
        self.esperas: list = []
        self.terminate_llamado = False
        self.kill_llamado = False

    def wait(self, timeout=None):
        self.esperas.append(timeout)
        raise subprocess.TimeoutExpired(cmd="hijo-simulado", timeout=timeout)

    def terminate(self) -> None:
        self.terminate_llamado = True

    def kill(self) -> None:
        self.kill_llamado = True


class _SubprocessShim:
    def __init__(self, real) -> None:
        self._real = real
        self.hijos: list = []
        self.taskkill: list = []

    def __getattr__(self, name):
        return getattr(self._real, name)

    def Popen(self, *args, **kwargs):  # noqa: N802
        hijo = _HijoFalso()
        self.hijos.append(hijo)
        return hijo

    def run(self, cmd, **kwargs):
        # taskkill que NO responde: se agota el tiempo concedido.
        self.taskkill.append({"cmd": list(cmd),
                              "timeout_concedido_s": kwargs.get("timeout")})
        raise self._real.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))


class _OsShim:
    def __init__(self, real) -> None:
        self._real = real
        self.kill_llamadas: list = []

    def __getattr__(self, name):
        return getattr(self._real, name)

    def kill(self, pid, sig) -> None:
        self.kill_llamadas.append({"pid": pid, "senal": int(sig)})


def _cargar_lanzador(ruta: Path):
    spec = importlib.util.spec_from_file_location("lanzador_bajo_prueba", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def reproducir(ruta_lanzador: Path, trabajo: float = 1.0, margen: float = 4.0) -> dict:
    modulo = _cargar_lanzador(ruta_lanzador)
    shim_sub = _SubprocessShim(subprocess)
    shim_os = _OsShim(os)
    modulo.subprocess = shim_sub
    modulo.os = shim_os

    tmp = Path(tempfile.mkdtemp(prefix="repro-defectos-"))
    out = tmp / "corrida"
    inicio_real = time.monotonic()
    try:
        codigo = modulo.ejecutar(
            [sys.executable, "-c", "print('hijo simulado')"],
            out,
            work_timeout_seconds=trabajo,
            shutdown_grace_seconds=margen,
        )
        elapsed_real = time.monotonic() - inicio_real
        estado = json.loads((out / "estado_lanzador.json").read_text(encoding="utf-8"))
        meta = json.loads((out / "launcher.json").read_text(encoding="utf-8"))
        exit_code = (out / "exit_code.txt").read_text(encoding="utf-8").strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    hijo = shim_sub.hijos[0]
    esperas_concedidas = [e for e in hijo.esperas if e is not None]
    espera_maxima = max(esperas_concedidas) if esperas_concedidas else 0.0
    taskkill_timeout = (shim_sub.taskkill[0]["timeout_concedido_s"]
                        if shim_sub.taskkill else None)
    tarea_reap = espera_maxima if hijo.kill_llamado else 0.0

    total_max = trabajo + margen
    tiempos = estado.get("tiempos", {})
    limites = estado.get("limites", {})
    # El codigo publicado (d53d8ad) no publicaba limite duro de limpieza: sus
    # esperas fijas (taskkill 30 s + reap 10 s) se sumaban al plazo global.
    t_forzada = (tiempos.get("deadline_forzada_relativo_s")
                 if tiempos.get("deadline_forzada_relativo_s") is not None
                 else tiempos.get("forced_deadline_relativo_s"))
    t_limpieza = tiempos.get("deadline_limpieza_relativo_s")
    reserva = float(limites.get("reserva_persistencia_seconds") or 0.0)
    if t_limpieza is None:
        # Sin limite duro: el peor caso es la suma de las esperas fijas.
        acumulado_hasta_persistencia = (t_forzada or 0.0) + (taskkill_timeout or 0.0) \
            + tarea_reap
    else:
        fin_taskkill = (t_forzada or 0.0) + (taskkill_timeout or 0.0)
        reap_maximo = max(0.0, t_limpieza - fin_taskkill)
        acumulado_hasta_persistencia = fin_taskkill + reap_maximo
    # La persistencia final esta acotada por su reserva.
    acumulado_con_persistencia = acumulado_hasta_persistencia + reserva
    restante_en_forzada = total_max - (t_forzada or 0.0)

    bloque = estado.get("cierre") or estado.get("limpieza") or {}
    defecto_b = {
        "esquema": "cierre" if "cierre" in estado else "limpieza",
        "codigo_hijo_estado": (bloque.get("codigo_salida_estado")
                               or bloque.get("codigo_hijo_estado")),
        "proceso_hijo_terminado": bloque.get("proceso_hijo_terminado"),
        "terminacion_hijo_observada": bloque.get("terminacion_hijo_observada"),
        "alimentaciones_cerradas": (bloque.get("alimentaciones_cerradas")
                                    if "alimentaciones_cerradas" in bloque
                                    else bloque.get("alimentaciones_lanzador_cerradas")),
        "recursos_hijo": bloque.get("recursos_hijo"),
        "exit_code_txt": exit_code,
        "codigo_hijo_observado": meta.get("codigo_hijo_observado"),
        "incoherencia_terminacion": (
            (bloque.get("codigo_salida_estado") or bloque.get("codigo_hijo_estado"))
            == "UNKNOWN"
            and (bloque.get("proceso_hijo_terminado") is True
                 or bloque.get("terminacion_hijo_observada") is True)),
        "afirmacion_incondicional_de_cierre": (
            bloque.get("alimentaciones_cerradas") is True
            or (bloque.get("recursos_hijo") == "UNKNOWN"
                and bloque.get("alimentaciones_lanzador_cerradas") is True
                and "recursos_hijo" in bloque
                and bloque.get("recursos_hijo") is None)),
    }

    return {
        "lanzador_bajo_prueba": str(ruta_lanzador),
        "parametros": {"trabajo_s": trabajo, "margen_s": margen,
                       "total_max_s": total_max},
        "defecto_a_esperas": {
            "deadline_terminacion_forzada_relativo_s": t_forzada,
            "limite_duro_de_limpieza_relativo_s": t_limpieza,
            "tiempo_concedido_a_taskkill_s": taskkill_timeout,
            "tiempo_concedido_al_reap_del_hijo_s": tarea_reap,
            "reserva_de_persistencia_s": reserva,
            "restante_hasta_el_plazo_global_s": round(restante_en_forzada, 3),
            "acumulado_hasta_la_persistencia_s": round(
                acumulado_hasta_persistencia, 3),
            "acumulado_con_persistencia_s": round(acumulado_con_persistencia, 3),
            "excede_el_plazo_global": acumulado_con_persistencia > total_max,
            "elapsed_real_de_la_simulacion_s": round(elapsed_real, 3),
        },
        "defecto_b_cierre": defecto_b,
        "estado_publicado": {
            "resultado": estado.get("resultado"),
            "causa_terminacion": estado.get("causa_terminacion"),
            "cumplimiento_normal": estado.get("cumplimiento_normal"),
            "codigo_lanzador": estado.get("codigo_lanzador"),
            "bloque_de_cierre": bloque,
        },
        "codigo_lanzador_observado": codigo,
        "nota": ("Simulacion determinista con dobles de Popen/run/os.kill: "
                 "registra el tiempo CONCEDIDO a cada espera sin esperar de "
                 "verdad. No es una ejecucion real en Windows."),
    }


def main() -> int:
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else LANZADOR_POR_DEFECTO
    resultado = reproducir(ruta)
    texto = json.dumps(resultado, ensure_ascii=False, indent=2)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(texto + "\n", encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
