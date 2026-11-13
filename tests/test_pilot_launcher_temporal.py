"""Control temporal del lanzador y parada por senal del piloto.

Verifica el contrato temporal implementado en ``scripts/run_pilot_window.py``:

A. finalizacion normal con codigo 0,
B. finalizacion normal con codigo no cero,
C. plazo vencido con parada limpia efectiva,
D. hijo que ignora la parada y exige terminacion forzada,
E. hijo que devuelve 0 tras el timeout (el incumplimiento no desaparece),
F. proceso ajeno conservado,
G. argumentos y directorios compatibles en ambos modos del lanzador,
H. evidencia persistida y ausencia de procesos propios residuales,

mas el lado del piloto: tras la parada no se inicia trabajo nuevo (seleccion,
entrada ni consulta) y los pendientes se conservan CON SU CAUSA.

Solo procesos locales triviales: sin red, sin mercado, sin cuentas ni datasets.
La plataforma del proyecto es Windows y las pruebas se ejecutan aqui.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LANZADOR = ROOT / "scripts" / "run_pilot_window.py"

# Codigos del LANZADOR (no son codigos del hijo).
CODIGO_TIMEOUT_PARADA_LIMPIA = 124
CODIGO_TIMEOUT_TERMINACION_FORZADA = 125


# ---------------------------------------------------------------------------
# Hijos locales triviales
# ---------------------------------------------------------------------------

HITO_NORMAL = "import sys; sys.exit({codigo})"

HITO_PARADA_LIMPIA = """
import signal, sys, time
def _parada(signum, frame):
    print('parada limpia recibida', flush=True)
    sys.exit(0)
signal.signal(signal.SIGINT, _parada)
if hasattr(signal, 'SIGBREAK'):
    signal.signal(signal.SIGBREAK, _parada)
try:
    signal.signal(signal.SIGTERM, _parada)
except Exception:
    pass
print('trabajando', flush=True)
fin = time.monotonic() + 60
while time.monotonic() < fin:
    time.sleep(0.2)
print('termino por su cuenta', flush=True)
"""

HITO_IGNORA_PARADA = """
import signal, sys, time
for _nombre in ('SIGINT', 'SIGTERM', 'SIGBREAK'):
    _senal = getattr(signal, _nombre, None)
    if _senal is not None:
        try:
            signal.signal(_senal, signal.SIG_IGN)
        except Exception:
            pass
print('trabajando e ignora cualquier parada', flush=True)
time.sleep(60)
print('termino por su cuenta', flush=True)
"""

HITO_CERO_TARDIO = """
import signal, sys, time
def _parada(signum, frame):
    print('parada recibida; sale con 0', flush=True)
    time.sleep(0.3)
    sys.exit(0)
signal.signal(signal.SIGINT, _parada)
if hasattr(signal, 'SIGBREAK'):
    signal.signal(signal.SIGBREAK, _parada)
print('trabajando', flush=True)
fin = time.monotonic() + 60
while time.monotonic() < fin:
    time.sleep(0.2)
"""

HITO_CON_PID = """
import os, signal, sys, time
for _nombre in ('SIGINT', 'SIGTERM', 'SIGBREAK'):
    _senal = getattr(signal, _nombre, None)
    if _senal is not None:
        try:
            signal.signal(_senal, signal.SIG_IGN)
        except Exception:
            pass
pathlib_pid = sys.argv[1]
with open(pathlib_pid, 'w', encoding='utf-8') as fh:
    fh.write(str(os.getpid()))
print('pid registrado', flush=True)
time.sleep(60)
"""


def _hijo(tmp_path: Path, nombre: str, cuerpo: str) -> Path:
    destino = tmp_path / nombre
    destino.write_text(cuerpo, encoding="utf-8")
    return destino


def _lanzar(tmp_path: Path, nombre: str, cuerpo: str, *,
            trabajo: float | None = None, margen: float | None = None,
            timeout: int = 120) -> tuple[subprocess.CompletedProcess, Path]:
    """Ejecuta el lanzador con un hijo trivial y devuelve (proceso, directorio)."""
    out = tmp_path / nombre
    hijo = _hijo(tmp_path, f"{nombre}_hijo.py", cuerpo)
    cmd = [sys.executable, str(LANZADOR), "--out-dir", str(out)]
    if trabajo is not None:
        cmd += ["--work-timeout-seconds", str(trabajo)]
    if margen is not None:
        cmd += ["--shutdown-grace-seconds", str(margen)]
    cmd += ["--", sys.executable, str(hijo)]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          timeout=timeout)
    return proc, out


def _estado(out: Path) -> dict:
    return json.loads((out / "estado_lanzador.json").read_text(encoding="utf-8"))


def _meta(out: Path) -> dict:
    return json.loads((out / "launcher.json").read_text(encoding="utf-8"))


def _vivo(pid: int) -> bool:
    """El proceso sigue vivo (Windows: tasklist; POSIX: signal 0)."""
    if os.name == "nt":
        res = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True, errors="replace")
        return str(pid) in res.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# A y B: finalizacion normal
# ---------------------------------------------------------------------------

def test_a_finalizacion_normal_codigo_cero(tmp_path: Path) -> None:
    proc, out = _lanzar(tmp_path, "normal_cero", HITO_NORMAL.format(codigo=0))
    assert proc.returncode == 0, proc.stderr
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "0"
    estado = _estado(out)
    assert estado["resultado"] == "normal"
    assert estado["cumplimiento_normal"] is True
    assert estado["codigo_lanzador"] == 0
    assert estado["causa_terminacion"] == "terminacion_natural"
    assert estado["cierre"]["terminacion_forzada_solicitada"] is False
    assert estado["cierre"]["terminacion_hijo_observada"] is True
    assert estado["cierre"]["codigo_salida_observado"] == 0
    # El lanzador no certifica los sockets del hijo.
    assert estado["cierre"]["recursos_hijo"] == "UNKNOWN"
    assert estado["cierre"]["alimentaciones_lanzador_cerradas"] is True


def test_b_finalizacion_normal_codigo_no_cero(tmp_path: Path) -> None:
    proc, out = _lanzar(tmp_path, "normal_siete", HITO_NORMAL.format(codigo=7))
    # Sin contrato temporal el lanzador devuelve el codigo del hijo.
    assert proc.returncode == 7, proc.stderr
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "7"
    estado = _estado(out)
    assert estado["resultado"] == "normal"
    assert estado["cumplimiento_normal"] is True
    assert estado["codigo_lanzador"] == 7


# ---------------------------------------------------------------------------
# C: plazo vencido con parada limpia efectiva
# ---------------------------------------------------------------------------

def test_c_plazo_vencido_parada_limpia_efectiva(tmp_path: Path) -> None:
    proc, out = _lanzar(tmp_path, "limpio", HITO_PARADA_LIMPIA,
                        trabajo=1, margen=8)
    assert proc.returncode == CODIGO_TIMEOUT_PARADA_LIMPIA, proc.stderr
    estado = _estado(out)
    assert estado["resultado"] == "timeout_trabajo_parada_limpia"
    assert estado["causa_terminacion"] == "plazo_trabajo_vencido"
    assert estado["cumplimiento_normal"] is False
    assert estado["cierre"]["parada_solicitada"] is True
    assert estado["cierre"]["terminacion_forzada_solicitada"] is False
    assert estado["cierre"]["terminacion_hijo_observada"] is True
    # El codigo real del hijo se conserva; el veredicto del lanzador es otro.
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "0"
    assert estado["cierre"]["codigo_salida_observado"] == 0
    # El hijo recibio la parada (SIGBREAK en Windows).
    assert "parada limpia recibida" in (out / "stdout.log").read_text(
        encoding="utf-8")
    # No se espera al ultimo instante del maximo total y la duracion
    # publicada incluye la persistencia del lanzador.
    assert estado["tiempos"]["duracion_total_s"] <= 1 + 8 + 1.0
    assert estado["tiempos"]["duracion_total_s"] >= estado["tiempos"][
        "duracion_hasta_fin_del_hijo_s"]
    assert estado["tiempos"]["exceso_maximo_total_s"] == 0.0
    assert estado["tiempos"]["incumplimiento_plazo_global"] is False


# ---------------------------------------------------------------------------
# D: terminacion forzada
# ---------------------------------------------------------------------------

def test_d_hijo_que_ignora_la_parada_exige_terminacion_forzada(
        tmp_path: Path) -> None:
    proc, out = _lanzar(tmp_path, "forzado", HITO_IGNORA_PARADA,
                        trabajo=1, margen=4)
    assert proc.returncode == CODIGO_TIMEOUT_TERMINACION_FORZADA, proc.stderr
    estado = _estado(out)
    assert estado["resultado"] == "timeout_trabajo_terminacion_forzada"
    assert estado["causa_terminacion"] == "plazo_trabajo_vencido"
    assert estado["cumplimiento_normal"] is False
    assert estado["cierre"]["parada_solicitada"] is True
    assert estado["cierre"]["terminacion_forzada_solicitada"] is True
    # En Windows, taskkill termina el arbol propio y la salida del hijo QUEDA
    # observada: ahi si puede afirmarse la terminacion (no solo la solicitud).
    assert estado["cierre"]["terminacion_hijo_observada"] is True
    assert estado["cierre"]["codigo_salida_estado"] == "observado"
    assert estado["cierre"]["recursos_hijo"] == "UNKNOWN"
    # El proceso se mata ANTES del maximo total: queda margen para persistir.
    assert estado["tiempos"]["duracion_total_s"] <= 1 + 4 + 1.0
    assert estado["tiempos"]["exceso_maximo_total_s"] == 0.0
    assert estado["tiempos"]["incumplimiento_plazo_global"] is False
    assert estado["limites"]["total_max_seconds"] == 5.0
    # Ninguna espera concedida supera el restante del limite duro.
    concedidos = estado["cierre"]["tiempo_concedido_taskkill_s"]
    assert concedidos is not None
    assert concedidos <= (estado["tiempos"]["deadline_limpieza_relativo_s"]
                          - estado["tiempos"]["deadline_forzada_relativo_s"])


# ---------------------------------------------------------------------------
# E: hijo que devuelve 0 tras el timeout
# ---------------------------------------------------------------------------

def test_e_hijo_que_devuelve_cero_tras_el_timeout_no_cumple(
        tmp_path: Path) -> None:
    proc, out = _lanzar(tmp_path, "cero_tardio", HITO_CERO_TARDIO,
                        trabajo=1, margen=8)
    # El codigo del hijo es 0, pero el lanzador NO declara cumplimiento normal.
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "0"
    assert proc.returncode == CODIGO_TIMEOUT_PARADA_LIMPIA, proc.stderr
    assert proc.returncode != 0
    estado = _estado(out)
    assert estado["resultado"] == "timeout_trabajo_parada_limpia"
    assert estado["cumplimiento_normal"] is False
    assert estado["causa_terminacion"] == "plazo_trabajo_vencido"
    meta = _meta(out)
    assert meta["codigo_lanzador"] == CODIGO_TIMEOUT_PARADA_LIMPIA
    assert meta["exit_code"] == 0
    assert meta["codigo_hijo_observado"] == 0


# ---------------------------------------------------------------------------
# F: proceso ajeno conservado
# ---------------------------------------------------------------------------

def test_f_proceso_ajeno_conservado(tmp_path: Path) -> None:
    ajeno = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert _vivo(ajeno.pid)
        proc, out = _lanzar(tmp_path, "ajeno", HITO_IGNORA_PARADA,
                            trabajo=1, margen=3)
        assert proc.returncode in (CODIGO_TIMEOUT_PARADA_LIMPIA,
                                   CODIGO_TIMEOUT_TERMINACION_FORZADA)
        # El proceso ajeno sigue vivo: no se hacen busquedas globales.
        assert _vivo(ajeno.pid)
    finally:
        ajeno.terminate()
        try:
            ajeno.wait(timeout=15)
        except subprocess.TimeoutExpired:
            ajeno.kill()
            ajeno.wait(timeout=15)


# ---------------------------------------------------------------------------
# G: argumentos y directorios en ambos modos
# ---------------------------------------------------------------------------

_ARGS_PILOTO_BUDGET = [
    "--mode", "local", "--run-id", "lanzador-temporal", "--budget-only",
    "--duration-seconds", "60", "--settle-seconds", "60",
    "--cycle-seconds", "60", "--selection-seconds", "60",
    "--max-symbols", "5", "--max-candidates", "2", "--max-comparators", "1",
]


def test_g1_opciones_del_lanzador_no_llegan_al_piloto(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    out = tmp_path / "piloto"
    rc = run_pilot_window.main([
        "--out-dir", str(out),
        "--work-timeout-seconds", "60",
        "--shutdown-grace-seconds", "10",
        *_ARGS_PILOTO_BUDGET])
    assert rc == 0
    # El piloto acepto el plan: las opciones del lanzador NO son suyas.
    assert (out / "presupuesto.json").exists()
    meta = _meta(out)
    comando = meta["comando"]
    assert "--work-timeout-seconds" not in comando
    assert "--shutdown-grace-seconds" not in comando
    # El directorio sigue propagado una sola vez.
    assert comando.count("--out-dir") == 1
    assert comando[comando.index("--out-dir") + 1] == str(out.resolve())


def test_g2_tras_guion_guion_los_argumentos_son_del_hijo(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    out = tmp_path / "hijo"
    marca = tmp_path / "argv.txt"
    script = ("import sys,pathlib;"
              "pathlib.Path(sys.argv[1]).write_text('|'.join(sys.argv[2:]));"
              "sys.exit(4)")
    rc = run_pilot_window.main([
        "--out-dir", str(out),
        "--work-timeout-seconds", "30",
        "--shutdown-grace-seconds", "5",
        "--", sys.executable, "-c", script, str(marca),
        "--work-timeout-seconds", "999"])
    assert rc == 4
    # Tras '--' los argumentos se respetan tal cual: la opcion es del hijo.
    assert marca.read_text(encoding="utf-8").split("|") == [
        "--work-timeout-seconds", "999"]
    meta = _meta(out)
    assert meta["comando"][-2:] == ["--work-timeout-seconds", "999"]


def test_g3_directorios_contradictorios_se_rechazan(tmp_path: Path,
                                                     capsys) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    out = tmp_path / "a"
    otro = tmp_path / "b"
    rc = run_pilot_window.main([
        "--out-dir", str(out), "--out-dir", str(otro),
        "--work-timeout-seconds", "30", "--shutdown-grace-seconds", "5",
        *_ARGS_PILOTO_BUDGET])
    assert rc == 2
    assert "contradictorios" in capsys.readouterr().err
    assert not (out / "launcher.json").exists()
    assert not (otro / "presupuesto.json").exists()


def test_g4_plazo_sin_margen_se_rechaza(tmp_path: Path, capsys) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    rc = run_pilot_window.main([
        "--out-dir", str(tmp_path / "sin-margen"),
        "--work-timeout-seconds", "30", *_ARGS_PILOTO_BUDGET])
    assert rc == 2
    assert "shutdown-grace-seconds" in capsys.readouterr().err


def test_g5_margen_sin_plazo_se_rechaza(tmp_path: Path, capsys) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    rc = run_pilot_window.main([
        "--out-dir", str(tmp_path / "sin-plazo"),
        "--shutdown-grace-seconds", "5", *_ARGS_PILOTO_BUDGET])
    assert rc == 2
    assert "work-timeout-seconds" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# H: evidencia persistida y sin procesos propios residuales
# ---------------------------------------------------------------------------

def test_h_evidencia_persistida_sin_residuales(tmp_path: Path) -> None:
    pid_file = tmp_path / "hijo.pid"
    hijo = _hijo(tmp_path, "con_pid.py", HITO_CON_PID)
    out = tmp_path / "evidencia"
    cmd = [sys.executable, str(LANZADOR), "--out-dir", str(out),
           "--work-timeout-seconds", "1", "--shutdown-grace-seconds", "4",
           "--", sys.executable, str(hijo), str(pid_file)]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == CODIGO_TIMEOUT_TERMINACION_FORZADA, proc.stderr

    for nombre in ("stdout.log", "stderr.log", "exit_code.txt",
                   "launcher.json", "estado_lanzador.json", "cierre.json"):
        assert (out / nombre).exists(), nombre
    estado = _estado(out)
    # Cierre basado en evidencia: la terminacion del hijo se afirma solo si se
    # observo su salida; el lanzador no certifica los sockets del hijo.
    assert estado["cierre"]["terminacion_hijo_observada"] is True
    assert estado["cierre"]["codigo_salida_estado"] == "observado"
    assert estado["cierre"]["alimentaciones_lanzador_cerradas"] is True
    assert estado["cierre"]["recursos_hijo"] == "UNKNOWN"
    # El veredicto final y su codigo viven aparte del codigo del hijo.
    cierre = json.loads((out / "cierre.json").read_text(encoding="utf-8"))
    assert cierre["codigo_hijo_observado"] is not None
    assert cierre["duracion_total_s"] >= estado["tiempos"][
        "duracion_hasta_fin_del_hijo_s"]
    assert cierre["incumplimiento_plazo_global"] is False

    # El proceso propio ya no existe (el hijo se registro con su PID).
    pid = int(pid_file.read_text(encoding="utf-8").strip())
    time.sleep(0.5)
    assert not _vivo(pid)


# ---------------------------------------------------------------------------
# Defectos materiales del 2026-11-13: plazo global y cierre con evidencia
#
# Los casos I y J son SIMULACIONES deterministas (dobles de taskkill, de
# proceso y de persistencia): no son ejecucion real en Windows. La
# acreditacion en Windows de la parada limpia, la terminacion forzada y la
# ausencia de residuales esta en los casos C, D y H, que si usan procesos
# reales de esta plataforma.
# ---------------------------------------------------------------------------

CODIGO_EXCESO_PLAZO_GLOBAL = 126


def _modulo_lanzador():
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    return run_pilot_window


def _cierre_final(out: Path) -> dict:
    return json.loads((out / "cierre.json").read_text(encoding="utf-8"))


def test_i_taskkill_que_agota_su_espera_se_detecta_y_se_publica(
        tmp_path: Path, monkeypatch) -> None:
    """taskkill que responde MAS tarde de lo concedido: se detecta."""
    rp = _modulo_lanzador()
    run_real = subprocess.run
    concedidos: list = []

    def _run_lento(cmd, **kwargs):
        timeout = kwargs.get("timeout")
        concedidos.append(timeout)
        # Ignora su propio timeout: consume el doble de lo concedido.
        time.sleep((timeout or 0.0) * 2 + 0.2)
        kwargs.pop("timeout", None)
        return run_real(cmd, **kwargs)

    monkeypatch.setattr(rp.subprocess, "run", _run_lento)
    out = tmp_path / "taskkill_lento"
    hijo = _hijo(tmp_path, "ignora.py", HITO_IGNORA_PARADA)
    rc = rp.ejecutar([sys.executable, str(hijo)], out,
                     work_timeout_seconds=0.5, shutdown_grace_seconds=1.5)
    assert rc in (CODIGO_TIMEOUT_TERMINACION_FORZADA,
                  CODIGO_EXCESO_PLAZO_GLOBAL), rc
    estado = _estado(out)
    final = _cierre_final(out)
    # La concesion se agoto: el exceso se detecta midiendo el tiempo real.
    assert estado["cierre"]["excedio_la_concesion"] is True
    assert concedidos and concedidos[0] is not None
    # Y el exceso sobre el plazo global se PUBLICA como incumplimiento.
    assert final["exceso_maximo_total_s"] > 0.0
    assert final["incumplimiento_plazo_global"] is True
    assert estado["cumplimiento_normal"] is False
    assert final["cumplimiento_normal"] is False


def test_j_hijo_salida_no_confirmada_no_se_declara_terminado(
        tmp_path: Path, monkeypatch) -> None:
    """Un hijo cuya salida no se puede confirmar NO se marca como terminado."""
    rp = _modulo_lanzador()

    class _ProcesoFalso:
        """Nunca confirma su salida: wait() siempre agota el tiempo."""

        pid = 2147483647

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="falso", timeout=timeout)

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    monkeypatch.setattr(rp, "_crear_proceso",
                        lambda *a, **k: _ProcesoFalso())
    monkeypatch.setattr(rp.os, "kill", lambda pid, sig: None)
    out = tmp_path / "sin_confirmar"
    rc = rp.ejecutar([sys.executable, "-c", "print('nunca corre')"], out,
                     work_timeout_seconds=0.5, shutdown_grace_seconds=1.5)
    assert rc in (CODIGO_TIMEOUT_TERMINACION_FORZADA,
                  CODIGO_EXCESO_PLAZO_GLOBAL), rc
    estado = _estado(out)
    # Se distingue lo solicitado de lo observado.
    assert estado["cierre"]["parada_solicitada"] is True
    assert estado["cierre"]["terminacion_forzada_solicitada"] is True
    assert estado["cierre"]["terminacion_hijo_observada"] is False
    assert estado["cierre"]["codigo_salida_estado"] == "UNKNOWN"
    assert estado["cierre"]["codigo_salida_observado"] is None
    assert estado["cierre"]["recursos_hijo"] == "UNKNOWN"
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "UNKNOWN"
    # La afirmacion falsa del esquema anterior desaparece del estado.
    assert "proceso_hijo_terminado" not in json.dumps(estado, ensure_ascii=False)


def test_k_la_persistencia_consume_parte_de_la_reserva_y_se_publica(
        tmp_path: Path, monkeypatch) -> None:
    """La duracion publicada INCLUYE la persistencia (no se midio antes)."""
    rp = _modulo_lanzador()
    original = rp._escribir_atomico

    def _escritura_lenta(destino, texto):
        time.sleep(0.25)
        original(destino, texto)

    monkeypatch.setattr(rp, "_escribir_atomico", _escritura_lenta)
    out = tmp_path / "persistencia_lenta"
    hijo = _hijo(tmp_path, "normal.py", HITO_NORMAL.format(codigo=0))
    rc = rp.ejecutar([sys.executable, str(hijo)], out,
                     work_timeout_seconds=5, shutdown_grace_seconds=3)
    assert rc == 0, rc
    estado = _estado(out)
    final = _cierre_final(out)
    assert estado["tiempos"]["duracion_persistencia_s"] >= 0.25
    assert (estado["tiempos"]["duracion_total_s"]
            >= estado["tiempos"]["duracion_hasta_fin_del_hijo_s"] + 0.25)
    assert final["duracion_total_s"] >= estado["tiempos"]["duracion_total_s"]
    assert final["incumplimiento_plazo_global"] is False


def test_l_exceso_temporal_registrado_honestamente(
        tmp_path: Path, monkeypatch) -> None:
    """Si la persistencia lleva el reloj mas alla del plazo, se publica."""
    rp = _modulo_lanzador()
    original = rp._escribir_atomico

    def _escritura_muy_lenta(destino, texto):
        time.sleep(0.6)
        original(destino, texto)

    monkeypatch.setattr(rp, "_escribir_atomico", _escritura_muy_lenta)
    out = tmp_path / "exceso"
    hijo = _hijo(tmp_path, "normal.py", HITO_NORMAL.format(codigo=0))
    rc = rp.ejecutar([sys.executable, str(hijo)], out,
                     work_timeout_seconds=0.5, shutdown_grace_seconds=0.5)
    # El exceso NO se oculta: es un incumplimiento con codigo propio.
    assert rc == CODIGO_EXCESO_PLAZO_GLOBAL, rc
    estado = _estado(out)
    final = _cierre_final(out)
    assert estado["resultado"] == "plazo_global_excedido"
    assert estado["causa_terminacion"] == "exceso_del_plazo_global"
    assert estado["cumplimiento_normal"] is False
    assert final["exceso_maximo_total_s"] > 0.0
    assert final["incumplimiento_plazo_global"] is True
    assert final["codigo_lanzador"] == CODIGO_EXCESO_PLAZO_GLOBAL


def test_m_ninguna_espera_recibe_mas_tiempo_que_el_restante(
        tmp_path: Path) -> None:
    """Ninguna espera concedida supera el restante del limite duro."""
    # Ejecucion real en Windows: hijo que ignora la parada.
    proc, out = _lanzar(tmp_path, "restante", HITO_IGNORA_PARADA,
                        trabajo=1, margen=4)
    assert proc.returncode == CODIGO_TIMEOUT_TERMINACION_FORZADA, proc.stderr
    estado = _estado(out)
    tiempos = estado["tiempos"]
    concedidos = estado["cierre"]["tiempo_concedido_taskkill_s"]
    assert concedidos is not None
    ventana = (tiempos["deadline_limpieza_relativo_s"]
               - tiempos["deadline_forzada_relativo_s"])
    assert concedidos <= ventana
    # El acumulado no pasa del limite duro de limpieza.
    assert (tiempos["deadline_forzada_relativo_s"] + concedidos
            <= tiempos["deadline_limpieza_relativo_s"])
    # Y el total medido (con persistencia) cabe en el plazo global.
    assert estado["tiempos"]["duracion_total_s"] <= 1 + 4 + 0.5
    assert estado["tiempos"]["exceso_maximo_total_s"] == 0.0


# ---------------------------------------------------------------------------
# Lado del piloto: la parada impide iniciar trabajo nuevo y conserva la causa
# ---------------------------------------------------------------------------

class _RelojFijo:
    def __init__(self, ms: int) -> None:
        self.ms = int(ms)

    def now_ms(self) -> int:
        return self.ms


class _RestQueNoDeberiaLlamarse:
    """REST falso: si se llama tras la parada, el fallo del test es explicito."""

    def __init__(self) -> None:
        self.llamadas = 0

    def exchange_info(self, *args, **kwargs):
        self.llamadas += 1
        raise AssertionError("adquisicion no permitida tras la parada")

    def get(self, *args, **kwargs):
        self.llamadas += 1
        raise AssertionError("adquisicion no permitida tras la parada")


def _pilot_local(tmp_path: Path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import research_pilot as rp  # noqa: E402

    cfg = rp.PilotConfig(
        run_id="temporal-local",
        out_dir=tmp_path / "piloto",
        mode="local",
        duration_seconds=60,
        settle_seconds=60,
        cycle_seconds=60,
        selection_seconds=60,
        max_symbols=5,
        max_candidates=2,
        max_comparators=1,
        funding_source="none",
    )
    return rp, rp.ResearchPilot(cfg, clock=_RelojFijo(1_735_689_605_000))


def _cerrar(pilot) -> None:
    for cierre in ("store", "operativo", "funding_log_fh", "history"):
        obj = getattr(pilot, cierre, None)
        if obj is not None and hasattr(obj, "close"):
            try:
                obj.close()
            except Exception:
                pass


def test_piloto_la_parada_impide_iniciar_trabajo_nuevo(tmp_path: Path) -> None:
    rp, pilot = _pilot_local(tmp_path)
    try:
        falso = _RestQueNoDeberiaLlamarse()
        pilot.rest = falso
        pilot.request_stop("senal_externa")
        assert pilot._terminal_stop() is True
        ciclo = pilot.run_cycle()
        # Ni seleccion ni consulta: no se acquires nada nuevo.
        assert falso.llamadas == 0
        assert ciclo == {}
        assert not pilot.obs_path.exists() or pilot.obs_path.stat().st_size == 0
    finally:
        _cerrar(pilot)


def test_piloto_los_pendientes_se_conservan_con_su_causa(tmp_path: Path) -> None:
    rp, pilot = _pilot_local(tmp_path)
    try:
        oid = "AAAUSDT|1735689605000"
        pilot.operativo_pendientes[oid] = {
            "observation_id": oid,
            "symbol": "AAAUSDT",
            "role": "candidate",
            "observacion": {
                "observation_id": oid,
                "symbol": "AAAUSDT",
                "role": "candidate",
                "decision_ms": 1_735_689_605_000,
            },
            "resuelta": False,
            "consultas": 0,
            "motivo": None,
        }
        pilot.request_stop("senal_externa")
        pilot.finalize_operativos_pendientes(1_735_689_605_000)

        filas = [json.loads(line) for line in
                 pilot.operativo.store_path.read_text(
                     encoding="utf-8").splitlines() if line.strip()]
        assert len(filas) == 1
        fila = filas[0]
        # El pendiente se conserva como PENDIENTE CON SU CAUSA, no se inventa
        # un resultado ni se convierte en cero.
        assert fila["decision"] == "PENDIENTE"
        assert "senal_externa" in fila["funding_estado"]
        assert fila["net_pnl"] is None
        assert fila["neto_estado"] == "UNKNOWN"
        assert fila["entry_px"] is None
        assert fila["exit_executed"] is False
    finally:
        _cerrar(pilot)
