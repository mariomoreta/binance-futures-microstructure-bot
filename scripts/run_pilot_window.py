"""Envoltorio de lanzamiento del piloto: captura del codigo de salida REAL y
control temporal efectivo del proceso.

Corre ``scripts/research_pilot.py`` (o el comando que se indique tras ``--``),
espera su finalizacion real y persiste en el directorio de la corrida:

  - ``stdout.log`` / ``stderr.log``: salida del proceso hijo,
  - ``exit_code.txt``: codigo numerico real, leido del proceso terminado,
  - ``launcher.json``: comando, returncode, inicio, duracion hasta su propia
    escritura y, cuando aplica, el contrato temporal y su veredicto,
  - ``estado_lanzador.json``: veredicto del LANZADOR, separado del codigo del
    hijo (causa de terminacion, parada solicitada, terminacion forzada
    solicitada, cierre basado en evidencia, limites y tiempos),
  - ``cierre.json``: medicion definitiva del fin de la corrida (incluye la
    persistencia) y exceso sobre el plazo global, si lo hay.

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

Alcance real del control (lo que el codigo puede y no puede demostrar):
  - TODA espera y TODA llamada de terminacion se acotan al tiempo restante
    del MISMO deadline absoluto. No hay esperas fijas que se sumen al plazo
    global.
  - El plazo global acota el TIEMPO que el lanzador espera y concede; no es
    una garantia del sistema operativo: una llamada del sistema que ignore
    su propio timeout puede prolongar la operacion mas alla del deadline. En
    ese caso el exceso se MIDE y se publica como incumplimiento, no se
    oculta ni se compensa reiniciando el reloj.
  - El cierre se publica segun EVIDENCIA: se distingue la parada
    solicitada, la terminacion forzada solicitada, la terminacion del hijo
    observada y el codigo de salida observado. No se marca al hijo como
    terminado solo porque se intento matarlo, y el lanzador no certifica los
    sockets del hijo: su estado de cierre es ``UNKNOWN`` y el estado del
    piloto se conserva como evidencia separada.

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
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
PILOTO = ROOT / "scripts" / "research_pilot.py"

# Codigos del LANZADOR. No son codigos del hijo y solo aparecen cuando el
# contrato temporal venció: un hijo que devuelve 0 tras el plazo NO es
# cumplimiento normal.
CODIGO_TIMEOUT_PARADA_LIMPIA = 124
CODIGO_TIMEOUT_TERMINACION_FORZADA = 125
CODIGO_EXCESO_PLAZO_GLOBAL = 126

# Granularidad de sondeo del hijo y tolerancias asociadas.
INTERVALO_ESPERA_S = 0.2
TOLERANCIA_FIN_S = 0.5
# Reparto explicito del margen de cierre (--shutdown-grace-seconds):
#   - reserva de persistencia: tiempo que el lanzador se reserva a si mismo
#     para escribir la evidencia final;
#   - reserva de reap: tiempo que se deja al hijo para que confirme su
#     salida despues de la terminacion forzada;
#   - el resto: ventana de la parada limpia y de la terminacion forzada.
# Ninguna espera se concede fuera del plazo global: todas se acotan al
# restante del MISMO deadline absoluto.
RESERVA_PERSISTENCIA_MAX_S = 5.0
RESERVA_PERSISTENCIA_FRACCION = 0.25
RESERVA_REAP_MAX_S = 2.0
# Sin contrato temporal no hay plazo global; la espera de la interrupcion
# del operador queda acotada por este valor.
ESPERA_INTERRUPCION_MAX_S = 30.0

# Artefactos del piloto que el lanzador se limita a LISTAR como evidencia
# separada: no los interpreta ni certifica su contenido.
ARTEFACTOS_PILOTO = (
    "estado.json",
    "manifiesto.json",
    "resumen.json",
    "observaciones.jsonl",
    "resultado_operativo.jsonl",
    "funding_adquisicion.jsonl",
)

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


def _artefactos_piloto(out_dir: Path) -> List[Dict[str, Any]]:
    """Lista los artefactos del piloto presentes, SIN interpretarlos.

    Es evidencia diferenciada: el lanzador no certifica el cierre de los
    sockets del hijo ni el contenido de estos ficheros.
    """
    encontrados: List[Dict[str, Any]] = []
    for nombre in ARTEFACTOS_PILOTO:
        ruta = out_dir / nombre
        if ruta.is_file():
            try:
                tamano: Optional[int] = ruta.stat().st_size
            except OSError:
                tamano = None
            encontrados.append({"nombre": nombre, "bytes": tamano})
    return encontrados


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


def _terminar_forzado(proc: subprocess.Popen,
                      deadline: Optional[float] = None,
                      ) -> Tuple[str, Optional[float], bool]:
    """Terminacion forzada del hijo y de sus descendientes propios.

    Windows: ``taskkill /F /T /PID`` sobre el PID del hijo (arbol propio, no
    una busqueda global). POSIX: SIGKILL al grupo propio. Si la via principal
    falla, se recurre a ``Popen.kill()`` sobre el propio hijo.

    ``deadline`` es el instante ABSOLUTO (reloj monotonico) hasta el que se
    permite esta operacion: el tiempo concedido a la llamada externa se
    descuenta del restante, nunca es un valor fijo. Si la llamada externa
    ignora su propio timeout, el exceso se detecta midiendo el tiempo real y
    se publica como incumplimiento (no se oculta ni se reinicia el reloj).

    Devuelve ``(metodo, timeout_concedido_s, excedio_la_concesion)``.
    """
    restante = (None if deadline is None
                else max(0.0, deadline - time.monotonic()))
    if os.name == "nt":
        cmd = ["taskkill", "/F", "/T", "/PID", str(proc.pid)]
        inicio = time.monotonic()
        try:
            if restante is not None and restante <= 0.0:
                raise subprocess.TimeoutExpired(cmd, restante)
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 errors="replace", timeout=restante)
            elapsed = time.monotonic() - inicio
            excedio = (restante is not None
                       and elapsed > restante + TOLERANCIA_FIN_S)
            if res.returncode == 0:
                return "taskkill_arbol_propio", restante, excedio
            proc.kill()
            return (f"kill_proceso (taskkill rc={res.returncode})", restante,
                    excedio)
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - inicio
            excedio = (restante is not None
                       and elapsed > restante + TOLERANCIA_FIN_S)
            proc.kill()
            return "kill_proceso (taskkill agoto la espera)", restante, excedio
        except (OSError, subprocess.SubprocessError):
            proc.kill()
            return "kill_proceso", restante, False
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        return "sigkill_grupo", restante, False
    except (OSError, ProcessLookupError):
        proc.kill()
        return "kill_proceso", restante, False


def _estado_hijo_vacio() -> Dict[str, Any]:
    """Estado de terminacion del hijo, inicialmente sin evidencia."""
    return {
        "codigo": None,
        "parada_solicitada": False,
        "parada_mecanismo": None,
        "terminacion_forzada_solicitada": False,
        "terminacion_forzada_mecanismo": None,
        "tiempo_concedido_taskkill_s": None,
        "excedio_la_concesion": False,
        "fin_hijo_monotono_s": None,
    }


def _esperar_hijo(proc: subprocess.Popen,
                  work_deadline: Optional[float],
                  deadline_forzada: Optional[float],
                  deadline_limpieza: Optional[float],
                  ) -> Dict[str, Any]:
    """Espera al hijo con deadlines ABSOLUTOS (reloj monotonico).

    - ``work_deadline``: al vencerlo se solicita la parada limpia.
    - ``deadline_forzada``: al vencerlo se solicita la terminacion forzada.
    - ``deadline_limpieza``: limite duro de TODA operacion sobre el hijo
      (taskkill + confirmacion de salida). Pasado ese instante no se espera
      mas: se persiste la evidencia y se publica el exceso si lo hay.

    Ninguna espera se concede con un valor fijo: todas se acotan al
    restante del deadline aplicable. El codigo del hijo es ``None`` si no se
    pudo observar (``UNKNOWN``): nunca se inventa.
    """
    estado = _estado_hijo_vacio()
    while True:
        proximo: Optional[float] = None
        if work_deadline is not None and not estado["parada_solicitada"]:
            proximo = work_deadline
        elif (deadline_forzada is not None
                and not estado["terminacion_forzada_solicitada"]):
            proximo = deadline_forzada
        elif deadline_limpieza is not None:
            proximo = deadline_limpieza
        espera = INTERVALO_ESPERA_S
        if proximo is not None:
            espera = max(0.01, min(espera, proximo - time.monotonic()))
        try:
            codigo = proc.wait(timeout=espera)
            estado["codigo"] = codigo
            estado["fin_hijo_monotono_s"] = time.monotonic()
            return estado
        except subprocess.TimeoutExpired:
            pass
        now = time.monotonic()
        if (work_deadline is not None and not estado["parada_solicitada"]
                and now >= work_deadline):
            _entregada, mecanismo = _solicitar_parada_limpia(proc)
            estado["parada_solicitada"] = True
            estado["parada_mecanismo"] = mecanismo
            continue
        if (estado["parada_solicitada"]
                and deadline_forzada is not None
                and not estado["terminacion_forzada_solicitada"]
                and now >= deadline_forzada):
            metodo, concedido, excedio = _terminar_forzado(proc, deadline_limpieza)
            estado["terminacion_forzada_solicitada"] = True
            estado["terminacion_forzada_mecanismo"] = metodo
            estado["tiempo_concedido_taskkill_s"] = concedido
            estado["excedio_la_concesion"] = excedio
            # La confirmacion de salida usa lo que quede hasta el limite duro.
            restante = (None if deadline_limpieza is None
                        else max(0.0, deadline_limpieza - time.monotonic()))
            try:
                estado["codigo"] = proc.wait(timeout=restante)
            except subprocess.TimeoutExpired:
                estado["codigo"] = None
            estado["fin_hijo_monotono_s"] = time.monotonic()
            return estado
        if (deadline_limpieza is not None and estado["parada_solicitada"]
                and now >= deadline_limpieza):
            # Limite duro alcanzado sin confirmacion de salida: no se espera mas.
            estado["fin_hijo_monotono_s"] = time.monotonic()
            return estado


def _cerrar_hijo_por_excepcion(proc: subprocess.Popen, grupo_propio: bool,
                                deadline: Optional[float], causa: str,
                                ) -> Dict[str, Any]:
    """Cierre de emergencia: interrupcion del operador o error del lanzador.

    Pide la parada limpia (si hay grupo propio), espera hasta ``deadline`` y,
    si el hijo no confirma su salida, solicita la terminacion forzada y vuelve
    a esperar **dentro del mismo deadline**. Sin plazo global (uso sin
    timeout) el limite es ``ESPERA_INTERRUPCION_MAX_S``.
    """
    estado = _estado_hijo_vacio()
    limite = (deadline if deadline is not None
              else time.monotonic() + ESPERA_INTERRUPCION_MAX_S)
    if grupo_propio:
        entregada, mecanismo = _solicitar_parada_limpia(proc)
        estado["parada_solicitada"] = True
        estado["parada_mecanismo"] = f"{causa}:{mecanismo}"
        if not entregada:
            proc.terminate()
    else:
        proc.terminate()
        estado["parada_solicitada"] = True
        estado["parada_mecanismo"] = f"{causa}:terminate"
    try:
        estado["codigo"] = proc.wait(timeout=max(0.0, limite - time.monotonic()))
        estado["fin_hijo_monotono_s"] = time.monotonic()
        return estado
    except subprocess.TimeoutExpired:
        pass
    metodo, concedido, excedio = _terminar_forzado(proc, limite)
    estado["terminacion_forzada_solicitada"] = True
    estado["terminacion_forzada_mecanismo"] = metodo
    estado["tiempo_concedido_taskkill_s"] = concedido
    estado["excedio_la_concesion"] = excedio
    try:
        estado["codigo"] = proc.wait(timeout=max(0.0, limite - time.monotonic()))
    except subprocess.TimeoutExpired:
        estado["codigo"] = None
    estado["fin_hijo_monotono_s"] = time.monotonic()
    return estado


def ejecutar(comando: Sequence[str], out_dir: Path,
             cwd: Optional[Path] = None,
             work_timeout_seconds: Optional[float] = None,
             shutdown_grace_seconds: float = 0.0) -> int:
    """Ejecuta el comando, espera su finalizacion real y persiste la evidencia.

    Devuelve el codigo de salida del LANZADOR. Sin contrato temporal es el
    codigo real del hijo (compatibilidad). Con contrato temporal viciado es
    un codigo propio e inequivoco del lanzador (124 parada limpia, 125
    terminacion forzada, 126 exceso del plazo global), aunque el hijo haya
    devuelto 0.

    Plazos: un solo reloj monotonico y un solo deadline global. Todas las
    esperas y llamadas de terminacion se acotan al restante de ese deadline;
    no hay esperas fijas que se sumen al plazo. El tiempo total publicado
    incluye la persistencia del lanzador.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = out_dir / "stdout.log"
    stderr_path = out_dir / "stderr.log"
    exit_path = out_dir / "exit_code.txt"
    meta_path = out_dir / "launcher.json"
    estado_path = out_dir / "estado_lanzador.json"
    cierre_path = out_dir / "cierre.json"

    inicio_wall = time.time()
    inicio_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(inicio_wall))
    t0 = time.monotonic()

    work_timeout = (None if work_timeout_seconds is None
                    else float(work_timeout_seconds))
    grace = max(0.0, float(shutdown_grace_seconds))
    work_deadline = (t0 + work_timeout) if work_timeout is not None else None
    deadline_global = (work_deadline + grace) if work_deadline is not None else None
    # Reparto explicito del margen de cierre:
    #   - reserva de persistencia: para que el lanzador escriba su evidencia;
    #   - reserva de reap: para que el hijo confirme su salida tras la
    #     terminacion forzada;
    #   - el resto: parada limpia y terminacion forzada.
    if deadline_global is not None:
        reserva_persistencia = min(RESERVA_PERSISTENCIA_MAX_S,
                                   grace * RESERVA_PERSISTENCIA_FRACCION)
        disponible = max(0.0, grace - reserva_persistencia)
        reserva_reap = min(RESERVA_REAP_MAX_S, disponible / 2.0)
        deadline_limpieza = deadline_global - reserva_persistencia
        deadline_forzada = deadline_limpieza - reserva_reap
    else:
        reserva_persistencia = 0.0
        reserva_reap = 0.0
        deadline_limpieza = None
        deadline_forzada = None

    interrumpido = False
    error_lanzador: Optional[str] = None
    alimentaciones_cerradas = False
    estado_hijo = _estado_hijo_vacio()

    with open(stdout_path, "wb") as fout, open(stderr_path, "wb") as ferr:
        grupo_propio = work_timeout is not None
        proc: Optional[subprocess.Popen] = None
        try:
            try:
                proc = _crear_proceso(comando, cwd, fout, ferr,
                                       grupo_propio=grupo_propio)
            except Exception as exc:  # noqa: BLE001
                error_lanzador = f"lanzamiento: {type(exc).__name__}: {exc}"
            if proc is not None:
                try:
                    estado_hijo = _esperar_hijo(
                        proc, work_deadline, deadline_forzada, deadline_limpieza)
                except KeyboardInterrupt:
                    interrumpido = True
                    estado_hijo = _cerrar_hijo_por_excepcion(
                        proc, grupo_propio, deadline_limpieza,
                        "interrupcion_operador")
                except Exception as exc:  # noqa: BLE001
                    error_lanzador = f"espera: {type(exc).__name__}: {exc}"
                    estado_hijo = _cerrar_hijo_por_excepcion(
                        proc, grupo_propio, deadline_limpieza, "error_lanzador")
        finally:
            try:
                fout.flush()
                ferr.flush()
                fout.close()
                ferr.close()
                alimentaciones_cerradas = True
            except (OSError, ValueError):
                alimentaciones_cerradas = False

    codigo_hijo = estado_hijo["codigo"]
    codigo_hijo_observado = codigo_hijo is not None
    fin_hijo = estado_hijo["fin_hijo_monotono_s"] or time.monotonic()
    # --- Clasificacion del resultado, segun la EVIDENCIA observada --------
    # El deadline es ABSOLUTO (monotonico) y se compara contra el instante en
    # que se observo el fin del hijo. Si hubo que pedir la parada, el plazo de
    # trabajo se alcanzo: el hijo no termino por su cuenta y su codigo
    # (incluso 0) NO es cumplimiento normal. La tolerancia solo cubre el
    # borde en que el hijo termino solo dentro de la granularidad de sondeo.
    excedio_plazo_trabajo = bool(
        (work_deadline is not None and estado_hijo["parada_solicitada"])
        or (work_deadline is not None
            and fin_hijo > work_deadline + TOLERANCIA_FIN_S))
    if error_lanzador:
        resultado = "error_lanzador"
        causa = error_lanzador
        codigo_lanzador = 2
        cumplimiento_normal = False
    elif interrumpido:
        resultado = "interrupcion_operador"
        causa = "interrupcion_operador"
        codigo_lanzador = (int(codigo_hijo) if codigo_hijo is not None else 2)
        cumplimiento_normal = False
    elif excedio_plazo_trabajo:
        if estado_hijo["terminacion_forzada_solicitada"]:
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

    # --- Cierre basado en evidencia ----------------------------------------
    # Se distinguen: parada SOLICITADA, terminacion forzada SOLICITADA,
    # terminacion del hijo OBSERVADA y codigo de salida OBSERVADO. No se
    # marca al hijo como terminado solo porque se intento matarlo, y el
    # lanzador no certifica los sockets del hijo.
    cierre = {
        "parada_solicitada": bool(estado_hijo["parada_solicitada"]),
        "parada_mecanismo": estado_hijo["parada_mecanismo"],
        "terminacion_forzada_solicitada": bool(
            estado_hijo["terminacion_forzada_solicitada"]),
        "terminacion_forzada_mecanismo": estado_hijo[
            "terminacion_forzada_mecanismo"],
        "terminacion_hijo_observada": bool(codigo_hijo_observado),
        "codigo_salida_observado": (int(codigo_hijo)
                                    if codigo_hijo_observado else None),
        "codigo_salida_estado": ("observado" if codigo_hijo_observado
                                 else "UNKNOWN"),
        "alimentaciones_lanzador_cerradas": bool(alimentaciones_cerradas),
        "recursos_hijo": "UNKNOWN",
        "recursos_hijo_nota": ("el lanzador generico no puede certificar los "
                               "sockets ni el teardown del hijo: no se afirma "
                               "su cierre"),
        "tiempo_concedido_taskkill_s": estado_hijo["tiempo_concedido_taskkill_s"],
        "excedio_la_concesion": bool(estado_hijo["excedio_la_concesion"]),
        "evidencia_piloto": {
            "artefactos_observados": _artefactos_piloto(out_dir),
            "nota": ("estado del piloto como evidencia diferenciada: el "
                     "lanzador lo lista pero no lo interpreta ni lo certifica"),
        },
        "alcance": ("propio: el hijo y el arbol de descendientes del grupo "
                    "propio; nunca busquedas globales"),
    }

    limites = {
        "work_timeout_seconds": work_timeout,
        "shutdown_grace_seconds": grace,
        "total_max_seconds": (work_timeout + grace
                               if work_timeout is not None else None),
        "reserva_persistencia_seconds": round(reserva_persistencia, 3),
        "reserva_reap_seconds": round(reserva_reap, 3),
        "tolerancia_fin_seconds": TOLERANCIA_FIN_S,
        "sondeo_seconds": INTERVALO_ESPERA_S,
        "reloj": "monotonico",
        "deadlines": ("absolutos (no se reinician al esperar o senalar); "
                      "toda espera se acota al restante del MISMO deadline"),
        "alcance_del_control": ("acota el tiempo que el lanzador espera y "
                                "concede; no es una garantia del sistema "
                                "operativo: si una llamada ignora su timeout, "
                                "el exceso se mide y se publica"),
    }

    # --- Persistencia de la evidencia -------------------------------------
    # El codigo historico del hijo conserva su significado: es el codigo real
    # del proceso. Si no se pudo observar, queda UNKNOWN (no se inventa).
    inicio_persistencia = time.monotonic()
    _escribir_atomico(exit_path,
                      f"{codigo_hijo}\n" if codigo_hijo_observado else "UNKNOWN\n")

    tiempos_pre = {
        "inicio_monotono_s": round(t0, 3),
        "fin_hijo_monotono_s": round(fin_hijo, 3),
        "duracion_hasta_fin_del_hijo_s": round(fin_hijo - t0, 3),
        "work_deadline_relativo_s": work_timeout,
        "deadline_limpieza_relativo_s": (
            round(deadline_limpieza - t0, 3)
            if deadline_limpieza is not None else None),
        "deadline_forzada_relativo_s": (
            round(deadline_forzada - t0, 3)
            if deadline_forzada is not None else None),
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
        "fin_iso_utc": time.strftime("%Y-%m-%dT%H:%M:%S",
                                     time.gmtime(time.time())),
        "duracion_s": round(time.time() - inicio_wall, 3),
        "duracion_s_semantica": ("duración hasta la escritura de launcher.json; "
                                 "la duración TOTAL con persistencia está en "
                                 "estado_lanzador.json y cierre.json"),
        "interrumpido": interrumpido,
        # Contrato temporal: veredicto del lanzador, separado.
        "resultado_lanzador": resultado,
        "causa_terminacion": causa,
        "cumplimiento_normal": cumplimiento_normal,
        "codigo_lanzador": codigo_lanzador,
        "codigo_hijo_observado": (int(codigo_hijo) if codigo_hijo_observado
                                  else None),
        "codigo_hijo_estado": "observado" if codigo_hijo_observado else "UNKNOWN",
        "parada_solicitada": bool(estado_hijo["parada_solicitada"]),
        "mecanismo_parada": estado_hijo["parada_mecanismo"],
        "terminacion_forzada_solicitada": bool(
            estado_hijo["terminacion_forzada_solicitada"]),
        "mecanismo_terminacion_forzada": estado_hijo[
            "terminacion_forzada_mecanismo"],
        "limites_temporal": limites,
        "tiempos_monotonos": tiempos_pre,
        "cierre": cierre,
        "veredicto_definitivo": "cierre.json",
    }
    _escribir_atomico(meta_path, json.dumps(meta, ensure_ascii=False, indent=1))

    # --- Medicion final: INCLUYE la persistencia --------------------------
    # Se mide DESPUES de escribir la evidencia principal: la duracion
    # publicada no es una medicion tomada antes de escribir los artefactos.
    fin_persistencia = time.monotonic()
    duracion_total = fin_persistencia - t0
    duracion_persistencia = fin_persistencia - inicio_persistencia
    exceso_total = 0.0
    if deadline_global is not None:
        exceso_total = max(0.0, duracion_total - (deadline_global - t0))
    incumplio_plazo_global = exceso_total > 0.0
    if incumplio_plazo_global and resultado == "normal":
        resultado = "plazo_global_excedido"
        causa = "exceso_del_plazo_global"
        codigo_lanzador = CODIGO_EXCESO_PLAZO_GLOBAL
        cumplimiento_normal = False

    tiempos = dict(tiempos_pre)
    tiempos.update({
        "fin_monotono_s": round(fin_persistencia, 3),
        "duracion_total_s": round(duracion_total, 3),
        "duracion_persistencia_s": round(duracion_persistencia, 3),
        "exceso_maximo_total_s": round(exceso_total, 3),
        "incumplimiento_plazo_global": incumplio_plazo_global,
    })
    veredicto = {
        "resultado": resultado,
        "causa_terminacion": causa,
        "cumplimiento_normal": cumplimiento_normal,
        "codigo_lanzador": codigo_lanzador,
        "limites": limites,
        "tiempos": tiempos,
        "cierre": cierre,
        "veredicto_definitivo": "cierre.json",
        "nota": ("El codigo del lanzador y el codigo del hijo son cosas "
                 "distintas: un hijo que devuelve 0 tras vencer el plazo NO "
                 "es cumplimiento normal y el lanzador no lo declara."),
        "nota_medicion": ("duracion_total_s se mide despues de escribir "
                          "exit_code.txt y launcher.json (incluye la "
                          "persistencia); la escritura atomica de este "
                          "veredicto es la unica operacion posterior no "
                          "incluida; cierre.json publica la medicion "
                          "definitiva"),
    }
    _escribir_atomico(estado_path,
                      json.dumps(veredicto, ensure_ascii=False, indent=1))

    # --- Medicion definitiva ------------------------------------------------
    # Se vuelve a medir DESPUES de escribir el veredicto: si la persistencia
    # ha llevado el reloj mas alla del plazo global, el exceso se detecta
    # aqui, se corrige el veredicto y se devuelve ese codigo.cierre.json
    # publica la medicion definitiva (incluye la persistencia de todos los
    # artefactos); lo unico excluido es su propia escritura atomica.
    fin_definitivo = time.monotonic()
    duracion_definitiva = fin_definitivo - t0
    exceso_definitivo = 0.0
    if deadline_global is not None:
        exceso_definitivo = max(
            0.0, duracion_definitiva - (deadline_global - t0))
    if exceso_definitivo > 0.0 and resultado == "normal":
        resultado = "plazo_global_excedido"
        causa = "exceso_del_plazo_global"
        codigo_lanzador = CODIGO_EXCESO_PLAZO_GLOBAL
        cumplimiento_normal = False
    _escribir_atomico(cierre_path, json.dumps({
        "resultado": resultado,
        "causa_terminacion": causa,
        "cumplimiento_normal": cumplimiento_normal,
        "codigo_lanzador": codigo_lanzador,
        "codigo_hijo_observado": (int(codigo_hijo)
                                  if codigo_hijo_observado else None),
        "codigo_hijo_estado": ("observado" if codigo_hijo_observado
                               else "UNKNOWN"),
        "terminacion_hijo_observada": bool(codigo_hijo_observado),
        "recursos_hijo": "UNKNOWN",
        "duracion_total_s": round(duracion_definitiva, 3),
        "duracion_persistencia_s": round(duracion_persistencia, 3),
        "exceso_maximo_total_s": round(exceso_definitivo, 3),
        "incumplimiento_plazo_global": exceso_definitivo > 0.0,
        "fin_iso_utc": time.strftime("%Y-%m-%dT%H:%M:%S",
                                     time.gmtime(time.time())),
        "nota": ("medicion definitiva: incluye la persistencia de todos los "
                 "artefactos; solo queda fuera la escritura atomica de este "
                 "archivo"),
    }, ensure_ascii=False, indent=1))
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
Dentro del margen se reservan dos tramos: la reserva de persistencia (para
escribir la evidencia) y la reserva de reap (para que el hijo confirme su
salida tras la terminacion forzada). TODA espera y llamada de terminacion se
acota al restante del MISMO deadline: no hay esperas fijas que se sumen al
plazo global.
Codigos del lanzador: 0 = finalizacion normal; el codigo del hijo cuando no
hay contrato temporal; 124 = plazo de trabajo vencido con parada limpia;
125 = plazo de trabajo vencido con terminacion forzada; 126 = exceso del plazo
global. El codigo del hijo conserva su significado en exit_code.txt y en
launcher.json, y el veredicto del lanzador se publica por separado.
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
