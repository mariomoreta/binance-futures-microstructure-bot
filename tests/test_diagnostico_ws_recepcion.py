"""Diagnostico de recepcion WS: verificacion local en loopback.

El diagnostico esta PREPARADO para una comprobacion publica minima que NO se
ejecuta en este bloque. Aqui se ejercita solo contra 127.0.0.1 con los
proveedores loopback existentes: no se abre ningun socket publico, no se
consulta mercado, no se generan ordenes ni dataset de investigacion.

Verifica:
A. Con loopback que publica frames validos, los dos motores reciben y
   procesan sus datos (BookEngine y FlowEngine) y el veredicto es PASS.
B. Sin frames, el veredicto es INSUFICIENTE (no FAIL).
C. La evidencia compacta distingue conexion, frames de datos, frames de
   control, eventos validos y eventos procesados.
D. Contra el venue publico exige --autorizar-publico y no abre conexiones.
E. Duracion, simbolo y base se validan antes de conectar.
F. Los sockets propios quedan cerrados al terminar.
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
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.test_research_pilot import (  # noqa: E402
    T0,
    UNIVERSE,
    WsProvider,
    find_free_port,
    start_ws_server,
)

DIAGNOSTICO = ROOT / "scripts" / "diagnostico_ws_recepcion.py"
SIMBOLO = UNIVERSE[0]


def _entorno() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{ROOT / 'src'};{ROOT / 'scripts'};{ROOT}"
    return env


def _lanzar(args, timeout: float = 120.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DIAGNOSTICO), *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
        env=_entorno())


def _esperar_conexiones(provider: WsProvider, attendu: int,
                         timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if provider.open_connections >= attendu:
            return
        time.sleep(0.05)
    raise AssertionError(
        f"el diagnostico no abrio {attendu} conexiones "
        f"(vivas={provider.open_connections})")


def test_diagnostico_loopback_pasa_y_procesa_en_ambos_motores(
        tmp_path: Path) -> None:
    provider = WsProvider(UNIVERSE)
    port = find_free_port()
    stop = start_ws_server(provider, port)
    out = tmp_path / "diag"
    try:
        proc = subprocess.Popen(
            [sys.executable, str(DIAGNOSTICO),
             "--diagnostico-id", "diag-loopback",
             "--simbolo", SIMBOLO,
             "--duracion-seconds", "3",
             "--out-dir", str(out),
             "--ws-public-base", f"ws://127.0.0.1:{port}/public",
             "--ws-market-base", f"ws://127.0.0.1:{port}/market"],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=_entorno())
        _esperar_conexiones(provider, 2)
        instante = T0 + 60_000
        serie = list(range(instante - 62_000, instante + 1, 1_000))
        provider.publish(instante, depth_symbols=[SIMBOLO],
                         trade_events={SIMBOLO: serie})
        salida, error = proc.communicate(timeout=60)
        assert proc.returncode == 0, (salida, error)
    finally:
        stop()

    evidencia = json.loads((out / "diagnostico.json").read_text(encoding="utf-8"))
    assert evidencia["veredicto"] == "PASS", evidencia["motivos"]
    assert evidencia["simbolo"] == SIMBOLO
    assert evidencia["modo"] == "loopback"
    assert evidencia["rest"] == "ninguna peticion REST"
    # Escalera de evidencia: conexion, frames de datos, eventos validos y
    # eventos procesados por cada motor.
    feeds = evidencia["resultado"]["feeds"]
    assert feeds["market"]["connections"] == 1
    assert feeds["public"]["connections"] == 1
    assert feeds["market"]["reconnects"] == 0
    assert feeds["public"]["reconnects"] == 0
    assert feeds["market"]["errors"] == 0
    assert feeds["public"]["errors"] == 0
    ev = evidencia["resultado"]["evidencia"]
    assert ev["market"]["frames_datos"] >= len(serie)
    assert ev["market"]["eventos_validos"] >= len(serie)
    assert ev["public"]["frames_datos"] >= 1
    assert ev["public"]["eventos_validos"] >= 1
    procesados = evidencia["resultado"]["eventos_procesados"]
    assert procesados["flow_events"][SIMBOLO] >= len(serie)
    assert procesados["book_events"][SIMBOLO] >= 1
    # URLs efectivas y limites declarados.
    assert evidencia["urls"]["market"].endswith(
        f"/market/stream?streams={SIMBOLO.lower()}@aggTrade")
    assert evidencia["urls"]["public"].endswith(
        f"/public/stream?streams={SIMBOLO.lower()}@depth20@100ms")
    assert evidencia["limites"]["duracion_max_s"] == 60.0
    assert evidencia["limites"]["aperturas_iniciales"] == 2
    assert evidencia["limites"]["reconexiones_automaticas"] == 0
    # Evidencia compacta: un solo JSON, sin dataset de investigacion.
    assert sorted(p.name for p in out.iterdir()) == ["diagnostico.json"]


def test_diagnostico_sin_frames_es_insuficiente(tmp_path: Path) -> None:
    provider = WsProvider(UNIVERSE)
    port = find_free_port()
    stop = start_ws_server(provider, port)
    out = tmp_path / "diag-vacio"
    try:
        proc = _lanzar([
            "--diagnostico-id", "diag-vacio", "--simbolo", SIMBOLO,
            "--duracion-seconds", "2", "--out-dir", str(out),
            "--ws-public-base", f"ws://127.0.0.1:{port}/public",
            "--ws-market-base", f"ws://127.0.0.1:{port}/market"])
    finally:
        stop()
    assert proc.returncode == 10, proc.stderr
    evidencia = json.loads((out / "diagnostico.json").read_text(encoding="utf-8"))
    assert evidencia["veredicto"] == "INSUFICIENTE"
    assert evidencia["resultado"]["feeds"]["market"]["connections"] == 1
    assert evidencia["resultado"]["evidencia"]["market"]["eventos_validos"] == 0


def test_diagnostico_exige_autorizacion_para_el_venue_publico(
        tmp_path: Path) -> None:
    out = tmp_path / "diag-publico"
    proc = _lanzar([
        "--diagnostico-id", "diag-publico", "--simbolo", SIMBOLO,
        "--duracion-seconds", "5", "--out-dir", str(out)])
    assert proc.returncode == 2, proc.stdout
    assert "--autorizar-publico" in proc.stderr
    # No se abre ninguna conexion ni se escribe evidencia.
    assert not (out / "diagnostico.json").exists()


def test_diagnostico_rechaza_uso_invalido(tmp_path: Path) -> None:
    out = tmp_path / "diag-uso"
    # Duracion por encima del maximo global.
    proc = _lanzar(["--simbolo", SIMBOLO, "--duracion-seconds", "61",
                    "--out-dir", str(out)])
    assert proc.returncode == 2
    assert "duracion" in proc.stderr
    # Simbolo no explicito/valido.
    proc = _lanzar(["--simbolo", "no-es-un-simbolo", "--out-dir", str(out)])
    assert proc.returncode == 2
    assert "simbolo invalido" in proc.stderr
    # Base WS incompatible (prefijo adicional): se rechaza antes de conectar.
    proc = _lanzar([
        "--simbolo", SIMBOLO, "--out-dir", str(out),
        "--ws-public-base", "ws://127.0.0.1:1/otra/public",
        "--ws-market-base", "ws://127.0.0.1:1/market"])
    assert proc.returncode == 2
    assert "base WS invalida" in proc.stderr
    assert not (out / "diagnostico.json").exists()


def test_diagnostico_cierra_los_sockets_propios(tmp_path: Path) -> None:
    provider = WsProvider(UNIVERSE)
    port = find_free_port()
    stop = start_ws_server(provider, port)
    out = tmp_path / "diag-cierre"
    try:
        proc = subprocess.Popen(
            [sys.executable, str(DIAGNOSTICO),
             "--simbolo", SIMBOLO, "--duracion-seconds", "2",
             "--out-dir", str(out),
             "--ws-public-base", f"ws://127.0.0.1:{port}/public",
             "--ws-market-base", f"ws://127.0.0.1:{port}/market"],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=_entorno())
        _esperar_conexiones(provider, 2)
        proc.communicate(timeout=60)
        assert proc.returncode in (0, 10)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and provider.open_connections:
            time.sleep(0.05)
        assert provider.open_connections == 0
    finally:
        stop()


def test_comando_completo_lanzador_mas_diagnostico(tmp_path: Path) -> None:
    """La forma exacta del comando propuesto, ejecutada solo en loopback.

    Comprueba que el lanzador y el diagnostico comparten directorio, que el
    codigo real de salida se conserva y que el lanzador no inyecta opciones
    del piloto en modo comando explicito.
    """
    provider = WsProvider(UNIVERSE)
    port = find_free_port()
    stop = start_ws_server(provider, port)
    out = tmp_path / "diag-completo"
    comando = [
        sys.executable, str(DIAGNOSTICO),
        "--diagnostico-id", "diag-loopback",
        "--simbolo", SIMBOLO,
        "--duracion-seconds", "2",
        "--out-dir", str(out),
        "--ws-public-base", f"ws://127.0.0.1:{port}/public",
        "--ws-market-base", f"ws://127.0.0.1:{port}/market",
    ]
    try:
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "run_pilot_window.py"),
             "--out-dir", str(out), "--", *comando],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=_entorno())
        _esperar_conexiones(provider, 2)
        instante = T0 + 60_000
        serie = list(range(instante - 62_000, instante + 1, 1_000))
        provider.publish(instante, depth_symbols=[SIMBOLO],
                         trade_events={SIMBOLO: serie})
        salida, error = proc.communicate(timeout=60)
        assert proc.returncode == 0, (salida, error)
    finally:
        stop()

    # Evidencia del diagnostico y evidencia del lanzador, en el mismo sitio.
    assert (out / "diagnostico.json").exists()
    assert (out / "exit_code.txt").read_text(encoding="utf-8").strip() == "0"
    assert (out / "stdout.log").exists()
    assert (out / "stderr.log").exists()
    meta = json.loads((out / "launcher.json").read_text(encoding="utf-8"))
    assert meta["returncode"] == 0
    # El lanzador no inyecto nada: el comando es el del hijo, tal cual.
    assert meta["comando"] == comando
    evidencia = json.loads((out / "diagnostico.json").read_text(encoding="utf-8"))
    assert evidencia["veredicto"] == "PASS"
