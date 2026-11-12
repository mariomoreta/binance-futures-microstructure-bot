"""Envoltorio de lanzamiento: captura del codigo de salida real.

Verifica que el envoltorio (a) espera la finalizacion real del proceso,
(b) lee el codigo numerico de la plataforma, (c) persiste ese codigo y los
logs, y (d) NO infiere '0' desde stdout, desde ``phase=fin`` ni desde un
stderr vacio.

Solo procesos locales triviales: no toca red, mercado, cuentas ni datasets.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANZADOR = ROOT / "scripts" / "run_pilot_window.py"


def _lanzar(tmp: Path, codigo: int, *,
            stdout_texto: str = "") -> subprocess.CompletedProcess:
    """Ejecuta el envoltorio con un hijo trivial que termina con `codigo`."""
    script = (
        "import sys;"
        f"sys.stdout.write({stdout_texto!r});"
        "sys.stderr.write('stderr del hijo\\n');"
        f"sys.exit({codigo})"
    )
    cmd = [sys.executable, str(LANZADOR), "--out-dir", str(tmp),
           "--", sys.executable, "-c", script]
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          timeout=120)


def test_codigo_cero_se_persiste(tmp_path: Path) -> None:
    out = tmp_path / "cero"
    proc = _lanzar(out, 0)
    assert proc.returncode == 0, proc.stderr
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "0"
    meta = json.loads((out / "launcher.json").read_text(encoding="utf-8"))
    assert meta["returncode"] == 0
    assert meta["exit_code"] == 0
    assert meta["fuente_del_codigo"].startswith("Popen.wait()")
    assert (out / "stdout.log").exists()
    assert (out / "stderr.log").exists()
    assert "stderr del hijo" in (out / "stderr.log").read_text(encoding="utf-8")


def test_codigo_distinto_de_cero_se_persiste(tmp_path: Path) -> None:
    out = tmp_path / "siete"
    proc = _lanzar(out, 7)
    # El envoltorio devuelve el codigo del hijo.
    assert proc.returncode == 7, proc.stderr
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "7"
    meta = json.loads((out / "launcher.json").read_text(encoding="utf-8"))
    assert meta["returncode"] == 7
    assert meta["exit_code"] == 7


def test_no_infiere_cero_desde_stdout(tmp_path: Path) -> None:
    """Un stdout que declara 'completo' NO convierte un fallo en exito."""
    out = tmp_path / "falso_completo"
    falso = json.dumps({"estado": "completo", "stop_reason": "duracion"})
    proc = _lanzar(out, 3, stdout_texto=falso)
    assert proc.returncode == 3, proc.stderr
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "3"
    meta = json.loads((out / "launcher.json").read_text(encoding="utf-8"))
    assert meta["returncode"] == 3
    assert falso in (out / "stdout.log").read_text(encoding="utf-8")


def test_espera_a_la_finalizacion_real(tmp_path: Path) -> None:
    """El envoltorio no devuelve antes de que el hijo termine."""
    out = tmp_path / "espera"
    script = ("import time,sys; time.sleep(1.2); sys.exit(5)")
    cmd = [sys.executable, str(LANZADOR), "--out-dir", str(out),
           "--", sys.executable, "-c", script]
    inicio = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          timeout=120)
    duracion = time.monotonic() - inicio
    assert proc.returncode == 5, proc.stderr
    assert duracion >= 1.0, duracion
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "5"
    meta = json.loads((out / "launcher.json").read_text(encoding="utf-8"))
    assert meta["duracion_s"] >= 1.0


def test_comando_por_defecto_es_el_piloto() -> None:
    """Sin '--' el envoltorio lanza el CLI real del piloto."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    comando = run_pilot_window.construir_comando(["--run-id", "x", "--help"])
    assert comando[0] == sys.executable
    assert Path(comando[1]).name == "research_pilot.py"
    assert comando[2:] == ["--run-id", "x", "--help"]

    propio = run_pilot_window.construir_comando(["--", "python", "-c", "pass"])
    assert propio == ["python", "-c", "pass"]


# ---------------------------------------------------------------------------
# Directorio de salida: main() (no solo construir_comando)
# ---------------------------------------------------------------------------

# Prefijo minimo para que el piloto acepte el plan sin tocar red ni mercado.
_ARGS_PILOTO_BUDGET = [
    "--mode", "local", "--run-id", "lanzador-dir", "--budget-only",
    "--duration-seconds", "60", "--settle-seconds", "60",
    "--cycle-seconds", "60", "--selection-seconds", "60",
    "--max-symbols", "5", "--max-candidates", "2", "--max-comparators", "1",
]


def test_main_propaga_el_out_dir_al_piloto(tmp_path: Path) -> None:
    """main() da al piloto el mismo directorio que usa para los logs."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    out = tmp_path / "corrida"
    rc = run_pilot_window.main(["--out-dir", str(out), *_ARGS_PILOTO_BUDGET])
    assert rc == 0
    # El piloto escribio SU artefacto en el directorio del lanzador.
    assert (out / "presupuesto.json").exists()
    # Y la evidencia del lanzador esta en ese mismo directorio.
    assert (out / "stdout.log").exists()
    assert (out / "stderr.log").exists()
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "0"
    meta = json.loads((out / "launcher.json").read_text(encoding="utf-8"))
    comando = meta["comando"]
    assert Path(comando[1]).name == "research_pilot.py"
    assert comando.count("--out-dir") == 1
    assert comando[comando.index("--out-dir") + 1] == str(out.resolve())


def test_main_modo_comando_no_inyecta_opciones(tmp_path: Path) -> None:
    """Tras '--' los argumentos del hijo se respetan tal cual."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    out = tmp_path / "hijo"
    marca = tmp_path / "argv.txt"
    script = ("import sys,pathlib;"
              "pathlib.Path(sys.argv[1]).write_text('|'.join(sys.argv[2:]));"
              "sys.exit(4)")
    rc = run_pilot_window.main([
        "--out-dir", str(out), "--", sys.executable, "-c", script,
        str(marca), "--out-dir", "otro"])
    assert rc == 4
    # El hijo ve exactamente lo que se le paso: no se inyecta nada del piloto.
    assert marca.read_text(encoding="utf-8").split("|") == ["--out-dir", "otro"]
    meta = json.loads((out / "launcher.json").read_text(encoding="utf-8"))
    assert meta["comando"][-2:] == ["--out-dir", "otro"]
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "4"


def test_main_rechaza_directorios_contradictorios(tmp_path: Path,
                                                   capsys) -> None:
    """Dos directorios distintos: error explicito y ningun hijo lanzado."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    out = tmp_path / "a"
    otro = tmp_path / "b"
    rc = run_pilot_window.main([
        "--out-dir", str(out), "--out-dir", str(otro), *_ARGS_PILOTO_BUDGET])
    assert rc == 2
    assert "contradictorios" in capsys.readouterr().err
    # No se ejecuto nada: no hay logs ni artefactos del piloto.
    assert not (out / "launcher.json").exists()
    assert not (otro / "presupuesto.json").exists()
    assert not (out / "presupuesto.json").exists()


def test_main_acepta_mismo_directorio_repetido(tmp_path: Path) -> None:
    """El mismo directorio repetido no es ambiguo: se propaga una sola vez."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    out = tmp_path / "corrida"
    rc = run_pilot_window.main([
        "--out-dir", str(out), "--out-dir", str(out), *_ARGS_PILOTO_BUDGET])
    assert rc == 0
    assert (out / "presupuesto.json").exists()
    meta = json.loads((out / "launcher.json").read_text(encoding="utf-8"))
    assert meta["comando"].count("--out-dir") == 1


def test_main_exige_out_dir(capsys) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_pilot_window  # noqa: E402

    assert run_pilot_window.main([]) == 2
    assert "--out-dir" in capsys.readouterr().err
