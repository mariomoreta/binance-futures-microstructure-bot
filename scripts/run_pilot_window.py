"""Envoltorio de lanzamiento del piloto: captura del codigo de salida REAL y
control temporal efectivo del proceso.

Corre ``scripts/research_pilot.py`` (o el comando que se indique tras ``--``),
espera su finalizacion real y persiste en el directorio de la corrida:

  - ``stdout.log`` / ``stderr.log``: salida del proceso hijo,
  - ``exit_code.txt``: codigo numerico real, leido del proceso terminado,
  - ``launcher.json``: comando, returncode, inicio, fin, duracion y,
    cuando aplica, el contrato temporal y su veredicto,
  - ``estado_lanzador.json``: veredicto del LANZADOR, separado del codigo del
    hijo (causa de terminacion, parada solicitada, terminacion forzada,
    limites y tiempos).

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

Control temporal (opciones PROPIAS del lanzador; nunca llegan al parser del
piloto):
  - ``--work-timeout-seconds``: plazo de trabajo del hijo. Al vencerlo se
    solicita la parada limpia por el mecanismo existente y el hijo dispone
    del margen para cerrar y persistir.
  - ``--shutdown-grace-seconds``: margen EXCLUSIVO de parada, cierre y
    persistencia. Dentro de el se reserva un tranche final para la
    terminacion forzada y para escribir la evidencia, de modo que el proceso
    no se mata en el ultimo instante del maximo total.

Sin ``--work-timeout-seconds`` el comportamiento es el de siempre: espera
indefinida y codigo del hijo. Los plazos se calculan con reloj MONOTONICO y
deadline ABSOLUTO: enviar una senal o esperar otra vez no reinicia el
presupuesto temporal.

Uso:
    python scripts/run_pilot_window.py --out-dir <dir> [args del piloto...]
    python scripts/run_pilot_window.py --out-dir <dir> -- <comando> [args...]
    python scripts/run_pilot_window.py --out-dir <dir> \
        --work-timeout-seconds 40200 --shutdown-grace-seconds 300 \
        [args del piloto...]
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
PILOTO = ROOT / "scripts" / "research_pilot.py"

# Codigos del LANZADOR. No son codigos del hijo y solo aparecen cuando el
# contrato temporal venció: un hijo que devuelve 0 tras el plazo NO es
# cumplimiento normal.
CODIGO_TIMEOUT_PARADA_LIMPIA = 124
CODIGO_TIMEOUT_TERMINACION_FORZADA = 125

# Granularidad de sondeo del hijo y tolerancias asociadas.
INTERVALO_ESPERA_S = 0.2
TOLERANCIA_FIN_S = 0.5
# Dentro del margen de cierre se reserva tiempo para la terminacion forzada y
# para persistir la evidencia: el proceso no se mata en el ultimo instante.
RESERVA_PERSISTENCIA_MAX_S = 5.0
ESPERA_REAPER_S = 10.0

OPCIONES_LANZADOR = (
    "--out-dir",
    "--work-timeout-seconds",
    "--shutdown-grace-seconds",
)


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


def _extraer_opciones_del_lanzador(
    argv: Sequence[str],
) -> Tuple[Dict[str, str], List[str]]:
    """Separa las opciones PROPIAS del lanzador de los argumentos del hijo.

    Regla para cada opcion propia: la PRIMERA aparicion anterior a '--'
    pertenece al lanzador y se retira de los argumentos del hijo; las
    apariciones posteriores siguen siendo del hijo (asi se detecta un
    ``--out-dir`` contradictorio). Un '--' previo corta la busqueda: a partir
    de ahi los argumentos son del hijo, no del lanzador.
    """
    corte = argv.index("--") if "--" in argv else len(argv)
    valores: Dict[str, str] = {}
    resto: List[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if i < corte:
            consumo = False
            for opcion in OPCIONES_LANZADOR:
                if arg == opcion and opcion not in valores:
                    if i + 1 >= len(argv):
                        raise ValueError(f"{opcion} sin valor")
                    valores[opcion] = argv[i + 1]
                    i += 2
                    consumo = True
                    break
                if arg.startswith(opcion + "=") and opcion not in valores:
                    valores[opcion] = arg.split("=", 1)[1]
                    i += 1
                    consumo = True
                    break
            if consumo:
                continue
        resto.append(arg)
        i += 1
    return valores, resto


def _extraer_out_dir_del_lanzador(argv: Sequence[str]) -> tuple:
    """Compatibilidad: solo el ``--out-dir`` y el resto de argumentos."""
    valores, resto = _extraer_opciones_del_lanzador(argv)
    return valores.get("--out-dir"), resto


def _float_opcion(opciones: Dict[str, str], nombre: str,
                  defecto: Optional[float] = None) -> Optional[float]:
    """Valor numerico de una opcion propia del lanzador."""
    if nombre not in opciones:
        return defecto
    bruto = str(opciones[nombre]).strip()
    try:
        return float(bruto)
    except (TypeError, ValueError):
        raise ValueError(f"{nombre} no es un numero: {bruto!r}")


def _crear_proceso(comando: Sequence[str], cwd: Optional[Path],
                   stdout, stderr, grupo_propio: bool) -> subprocess.Popen:
    """Lanza el hijo. Con contrato temporal, el hijo va en su propio grupo.

    Windows: ``CREATE_NEW_PROCESS_GROUP`` permite entregar ``CTRL_BREAK``
    (que el piloto traduce a SIGBREAK) al grupo propio sin tocar el resto de
    la consola. POSIX: ``start_new_session`` crea un grupo propio equivalente.
    Sin contrato temporal no se crea grupo nuevo: el comportamiento actual no
    cambia.
    """
    kwargs: Dict[str, object] = {}
    if grupo_propio:
        if os.name == "nt":
            kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
    return subprocess.Popen(list(comando), cwd=str(cwd or ROOT),
                            stdout=stdout, stderr=stderr, **kwargs)


def _solicitar_parada_limpia(proc: subprocess.Popen) -> Tuple[bool, str]:
    """Pide al hijo que pare de forma limpia (sin destruirlo).

    Windows: ``CTRL_BREAK_EVENT`` al grupo propio. El piloto registra
    SIGBREAK como parada limpia (SIGINT/SIGTERM/SIGBREAK) y persiste lo
    pendiente con su causa. ``terminate()`` en Windows es TerminateProcess:
    mata el proceso sin darlo oportunidad de persistir, asi que NO se usa
    como parada limpia. POSIX: SIGTERM al grupo propio.
    """
    if os.name == "nt":
        ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
        if ctrl_break is None:
            return False, "ctrl_break_no_disponible"
        try:
            os.kill(proc.pid, ctrl_break)
            return True, "ctrl_break_event"
        except (OSError, ValueError) as exc:
            return False, f"ctrl_break_no_entregable: {exc}"
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        return True, "sigterm_grupo"
    except (OSError, ProcessLookupError):
        try:
            proc.terminate()
            return True, "sigterm_proceso"
        except OSError as exc:
            return False, f"sigterm_no_entregable: {exc}"


def _terminar_forzado(proc: subprocess.Popen) -> str:
    """Terminacion forzada del hijo y de sus descendientes propios.

    Windows: ``taskkill /F /T /PID`` sobre el PID del hijo (arbol propio, no
    una busqueda global). POSIX: SIGKILL al grupo propio. Si la via principal
    falla, se recurre a ``Popen.kill()`` sobre el propio hijo.
    """
    if os.name == "nt":
        try:
            res = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, text=True, errors="replace", timeout=30)
            if res.returncode == 0:
                return "taskkill_arbol_propio"
            proc.kill()
            return f"kill_proceso (taskkill rc={res.returncode})"
        except (OSError, subprocess.SubprocessError):
            proc.kill()
            return "kill_proceso"
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        return "sigkill_grupo"
    except (OSError, ProcessLookupError):
        proc.kill()
        return "kill_proceso"


def _esperar_hijo(proc: subprocess.Popen,
                  work_deadline: Optional[float],
                  forced_deadline: Optional[float],
                  ) -> Tuple[Optional[int], bool, bool, Optional[str]]:
    """Espera al hijo con deadlines ABSOLUTOS (reloj monotonico).

    Devuelve ``(codigo, parada_solicitada, terminacion_forzada, mecanismo)``.
    El codigo es ``None`` si no se pudo observar (UNKNOWN): nunca se inventa.
    """
    parada_solicitada = False
    terminacion_forzada = False
    mecanismo: Optional[str] = None
    while True:
        proximo: Optional[float] = None
        if work_deadline is not None and not parada_solicitada:
            proximo = work_deadline
        elif forced_deadline is not None:
            proximo = forced_deadline
        espera = INTERVALO_ESPERA_S
        if proximo is not None:
            espera = max(0.01, min(espera, proximo - time.monotonic()))
        try:
            codigo = proc.wait(timeout=espera)
            return codigo, parada_solicitada, terminacion_forzada, mecanismo
        except subprocess.TimeoutExpired:
            pass
        now = time.monotonic()
        if work_deadline is not None and not parada_solicitada \
                and now >= work_deadline:
            entregada, mecanismo = _solicitar_parada_limpia(proc)
            parada_solicitada = True
            # Si la parada limpia no se puede entregar (p. ej. proceso sin
            # consola compartida), el margen sigue siendo la unica ventana de
            # cierre y la terminacion forzada se aplica al final.
            continue
        if parada_solicitada and forced_deadline is not None \
                and now >= forced_deadline:
            metodo = _terminar_forzado(proc)
            mecanismo = f"{mecanismo}+{metodo}" if mecanismo else metodo
            terminacion_forzada = True
            try:
                codigo = proc.wait(timeout=ESPERA_REAPER_S)
            except subprocess.TimeoutExpired:
                codigo = None
            return codigo, parada_solicitada, terminacion_forzada, mecanismo


def ejecutar(comando: Sequence[str], out_dir: Path,
             cwd: Optional[Path] = None,
             work_timeout_seconds: Optional[float] = None,
             shutdown_grace_seconds: float = 0.0) -> int:
    """Ejecuta el comando, espera su finalizacion real y persiste la evidencia.

    Devuelve el codigo de salida del LANZADOR. Sin contrato temporal es el
    codigo real del hijo (compatibilidad). Con contrato temporal viciado es
    un codigo propio e inequivoco del lanzador (124 parada limpia, 125
    terminacion forzada), aunque el hijo haya devuelto 0.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = out_dir / "stdout.log"
    stderr_path = out_dir / "stderr.log"
    exit_path = out_dir / "exit_code.txt"
    meta_path = out_dir / "launcher.json"
    estado_path = out_dir / "estado_lanzador.json"

    inicio_wall = time.time()
    inicio_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(inicio_wall))
    t0 = time.monotonic()

    work_timeout = (None if work_timeout_seconds is None
                    else float(work_timeout_seconds))
    grace = max(0.0, float(shutdown_grace_seconds))
    work_deadline = (t0 + work_timeout) if work_timeout is not None else None
    total_deadline = (work_deadline + grace) if work_deadline is not None else None
    # Dentro del margen: el proceso se mata antes del maximo total y queda
    # un tranche para el cierre y la persistencia de la evidencia.
    reserva = min(RESERVA_PERSISTENCIA_MAX_S, grace / 2.0) if grace > 0 else 0.0
    forced_deadline = (total_deadline - reserva) if total_deadline is not None else None

    interrumpido = False
    codigo_hijo: Optional[int] = None
    parada_solicitada = False
    terminacion_forzada = False
    mecanismo: Optional[str] = None

    with open(stdout_path, "wb") as fout, open(stderr_path, "wb") as ferr:
        grupo_propio = work_timeout is not None
        proc = _crear_proceso(comando, cwd, fout, ferr,
                               grupo_propio=grupo_propio)
        try:
            (codigo_hijo, parada_solicitada, terminacion_forzada,
             mecanismo) = _esperar_hijo(proc, work_deadline, forced_deadline)
        except KeyboardInterrupt:
            interrumpido = True
            if grupo_propio:
                # Con grupo propio se pide la parada limpia: el hijo puede
                # persistir lo pendiente antes de morir.
                entregada, mecanismo_int = _solicitar_parada_limpia(proc)
                mecanismo = f"interrupcion_operador:{mecanismo_int}"
                if not entregada:
                    proc.terminate()
            else:
                proc.terminate()
            try:
                codigo_hijo = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                codigo_hijo = proc.wait()
        finally:
            try:
                fout.flush()
                ferr.flush()
            except (OSError, ValueError):
                pass

    fin_wall = time.time()
    fin_monotono = time.monotonic()
    duracion = fin_monotono - t0

    codigo_hijo_observado = codigo_hijo is not None
    # El deadline es ABSOLUTO (monotonico): se compara contra el instante de
    # fin observado, no contra una duracion relativa. Si hubo que pedir la
    # parada, el plazo de trabajo se alcanzo: el hijo no termino por su cuenta
    # y su codigo (incluso 0) NO es cumplimiento normal. La tolerancia solo
    # cubre el borde en que el hijo termino solo dentro de la granularidad de
    # sondeo.
    excedio_plazo = bool(
        (work_deadline is not None and parada_solicitada)
        or (work_deadline is not None
            and fin_monotono > work_deadline + TOLERANCIA_FIN_S))
    if interrumpido:
        resultado = "interrupcion_operador"
        causa = "interrupcion_operador"
        codigo_lanzador = (int(codigo_hijo) if codigo_hijo is not None else 2)
        cumplimiento_normal = False
    elif excedio_plazo:
        if terminacion_forzada:
            resultado = "timeout_trabajo_terminacion_forzada"
            codigo_lanzador = CODIGO_TIMEOUT_TERMINACION_FORZADA
        else:
            resultado = "timeout_trabajo_parada_limpia"
            codigo_lanzador = CODIGO_TIMEOUT_PARADA_LIMPIA
        causa = "plazo_trabajo_vencido"
        cumplimiento_normal = False
    else:
        resultado = "normal"
        causa = "terminacion_natural"
        codigo_lanzador = (int(codigo_hijo) if codigo_hijo is not None else 2)
        cumplimiento_normal = True

    # El codigo historico del hijo conserva su significado: es el codigo real
    # del proceso. Si no se pudo observar, queda UNKNOWN (no se inventa).
    _escribir_atomico(exit_path,
                      f"{codigo_hijo}\n" if codigo_hijo_observado else "UNKNOWN\n")

    exceso_total = 0.0
    if total_deadline is not None:
        exceso_total = max(0.0, duracion - (total_deadline - t0))

    limites = {
        "work_timeout_seconds": work_timeout,
        "shutdown_grace_seconds": grace,
        "total_max_seconds": (work_timeout + grace
                               if work_timeout is not None else None),
        "reserva_persistencia_seconds": reserva,
        "tolerancia_fin_seconds": TOLERANCIA_FIN_S,
        "sondeo_seconds": INTERVALO_ESPERA_S,
        "reloj": "monotonico",
        "deadlines": "absolutos (no se reinician al esperar o senalar)",
    }
    tiempos = {
        "inicio_monotono_s": round(t0, 3),
        "fin_monotono_s": round(fin_monotono, 3),
        "duracion_monotona_s": round(duracion, 3),
        "work_deadline_relativo_s": work_timeout,
        "forced_deadline_relativo_s": (
            round(forced_deadline - t0, 3) if forced_deadline is not None
            else None),
        "exceso_maximo_total_s": round(exceso_total, 3),
    }
    limpieza = {
        "proceso_hijo_terminado": codigo_hijo_observado or terminacion_forzada,
        "codigo_hijo_observado": (int(codigo_hijo) if codigo_hijo_observado
                                  else None),
        "codigo_hijo_estado": "observado" if codigo_hijo_observado else "UNKNOWN",
        "parada_solicitada": parada_solicitada,
        "mecanismo_parada": mecanismo,
        "terminacion_forzada": terminacion_forzada,
        "alimentaciones_cerradas": True,
        "alcance": ("propio: el hijo y el arbol de descendientes del grupo "
                    "propio; nunca busquedas globales"),
    }
    veredicto = {
        "resultado": resultado,
        "causa_terminacion": causa,
        "cumplimiento_normal": cumplimiento_normal,
        "codigo_lanzador": codigo_lanzador,
        "limites": limites,
        "tiempos": tiempos,
        "limpieza": limpieza,
        "nota": ("El codigo del lanzador y el codigo del hijo son cosas "
                 "distintas: un hijo que devuelve 0 tras vencer el plazo NO "
                 "es cumplimiento normal y el lanzador no lo declara."),
    }

    meta = {
        # Campos historicos (compatibilidad): el codigo real del hijo.
        "comando": list(comando),
        "returncode": codigo_hijo,
        "exit_code": codigo_hijo,
        "fuente_del_codigo": "Popen.wait() (codigo real del proceso)",
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "inicio_iso_utc": inicio_iso,
        "fin_iso_utc": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(fin_wall)),
        "duracion_s": round(fin_wall - inicio_wall, 3),
        "interrumpido": interrumpido,
        # Contrato temporal (nuevo): veredicto del lanzador, separado.
        "resultado_lanzador": resultado,
        "causa_terminacion": causa,
        "cumplimiento_normal": cumplimiento_normal,
        "codigo_lanzador": codigo_lanzador,
        "codigo_hijo_observado": (int(codigo_hijo) if codigo_hijo_observado
                                  else None),
        "codigo_hijo_estado": "observado" if codigo_hijo_observado else "UNKNOWN",
        "parada_solicitada": parada_solicitada,
        "mecanismo_parada": mecanismo,
        "terminacion_forzada": terminacion_forzada,
        "limites_temporal": limites,
        "tiempos_monotonos": tiempos,
        "limpieza": limpieza,
    }
    _escribir_atomico(meta_path, json.dumps(meta, ensure_ascii=False, indent=1))
    _escribir_atomico(estado_path,
                      json.dumps(veredicto, ensure_ascii=False, indent=1))
    print(json.dumps(meta, ensure_ascii=False), flush=True)
    return int(codigo_lanzador)


USO = """Uso:
    python scripts/run_pilot_window.py --out-dir <dir> [args del piloto...]
    python scripts/run_pilot_window.py --out-dir <dir> -- <comando> [args...]
    python scripts/run_pilot_window.py --out-dir <dir> \
        --work-timeout-seconds <s> --shutdown-grace-seconds <s> \
        [args del piloto...]

El lanzador tiene una sola opcion propia obligatoria: --out-dir (logs y
exit_code.txt). Tras '--' los argumentos son del hijo y se respetan tal cual:
no se le inyecta ninguna opcion de research_pilot.py.

Opciones propias del lanzador (NUNCA llegan al parser del piloto):
    --work-timeout-seconds   plazo de trabajo del hijo (reloj monotonico).
                              Al vencerlo se pide la parada limpia y el hijo
                              dispone del margen para cerrar y persistir.
    --shutdown-grace-seconds margen EXCLUSIVO de parada, cierre y persistencia.
                              Dentro de el se reserva un tranche para la
                              terminacion forzada y para escribir la evidencia.

Total maximo = --work-timeout-seconds + --shutdown-grace-seconds.
Codigos del lanzador: 0 = finalizacion normal; el codigo del hijo cuando no
hay contrato temporal; 124 = plazo de trabajo vencido con parada limpia;
125 = plazo de trabajo vencido con terminacion forzada. El codigo del hijo
conserva su significado en exit_code.txt y en launcher.json.
"""


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(USO, end="")
        return 0
    try:
        opciones, resto = _extraer_opciones_del_lanzador(argv)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    valor_out_dir = opciones.get("--out-dir")
    if valor_out_dir is None:
        print(json.dumps({
            "error": "--out-dir es obligatorio (directorio de logs y "
                     "exit_code.txt)"}), file=sys.stderr)
        return 2
    try:
        work_timeout = _float_opcion(opciones, "--work-timeout-seconds")
        grace = _float_opcion(opciones, "--shutdown-grace-seconds", defecto=0.0)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    if work_timeout is None:
        if grace:
            print(json.dumps({
                "error": "--shutdown-grace-seconds requiere "
                         "--work-timeout-seconds (no hay margen sin plazo)"}),
                file=sys.stderr)
            return 2
    else:
        if work_timeout <= 0:
            print(json.dumps({
                "error": "--work-timeout-seconds debe ser > 0"}),
                file=sys.stderr)
            return 2
        if grace <= 0:
            print(json.dumps({
                "error": "con --work-timeout-seconds se exige "
                         "--shutdown-grace-seconds > 0 (margen de parada, "
                         "cierre y persistencia)"}), file=sys.stderr)
            return 2
    try:
        comando = construir_comando(resto, out_dir=Path(valor_out_dir))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    return ejecutar(comando, Path(valor_out_dir),
                    work_timeout_seconds=work_timeout,
                    shutdown_grace_seconds=float(grace or 0.0))


if __name__ == "__main__":
    raise SystemExit(main())
