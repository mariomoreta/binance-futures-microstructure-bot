# -*- coding: utf-8 -*-
"""Pruebas focalizadas del analisis contrafactual offline de la ventana 4.

- Denominador: las 161 observaciones aptas se evalúan todas; ninguna se pierde
  ni se convierte en cero.
- Aislamiento de escenarios: cada señal evaluada con capacidad 1 aislada; las 2
  operaciones históricas conservan sus valores numéricos (control de coherencia).
- Causalidad del stop: pruebas LONG y SHORT donde el precio posterior al fill
  atraviesa el stop EFECTIVO (desde el fill) pero NO el stop de REFERENCIA
  (desde ref_close), demostrando cuál gobierna realmente la salida.
- Contabilidad: neto CONDICIONADO = bruto - comisiones - spread/slip; funding
  desconocido (UNKNOWN, nunca cero).
- Configuración: carga y valida config_inicial.json (hash); rechaza config
  ausente/incompleta/inválida; sin OperativoConfig() por defecto.

Reutiliza scripts/analisis_contrafactual_ventana4.py (pipeline existente) y
backtest_offline (motor real). Ejecutar con: PYTHONPATH=src pytest
tests/test_analisis_contrafactual_ventana4.py
"""
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(r"C:\proyectos\binance-futures-microstructure-bot")
DATA = Path(r"C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a")
SCRIPT = ROOT / "scripts" / "analisis_contrafactual_ventana4.py"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from microstructure_probe.backtest_offline import (  # noqa: E402
    BacktestConfig, Candle, StudyEvent, run_backtest,
)

CONFIG_FUNDING_NONE = None


def _ejecutar_script(run_dir: Path, out_dir: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         "--run-dir", str(run_dir), "--out-dir", str(out_dir)],
        cwd=str(ROOT), capture_output=True, text=True)


def _run_dir_valido(tmp_path: Path) -> Path:
    """Copia los archivos fuente del run real a un directorio temporal."""
    destino = tmp_path / "run"
    shutil.copytree(DATA, destino)
    return destino


def _leer_resumen(out_dir: Path):
    with io.open(out_dir / "resumen_ejecutivo.json", encoding="utf-8") as f:
        return json.load(f)


def _leer_escenarios(out_dir: Path):
    filas = []
    with io.open(out_dir / "escenarios_por_fila.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                filas.append(json.loads(line))
    return filas


# ---------------------------------------------------------------- derivados

def test_salida_inexistente_genera_derivados(tmp_path):
    """Al comenzar con out-dir inexistente, el script genera los derivados."""
    out_dir = tmp_path / "nuevo_derivado"
    assert not out_dir.exists()
    r = _ejecutar_script(DATA, out_dir)
    assert r.returncode == 0, r.stderr[-2000:]
    assert (out_dir / "resumen_ejecutivo.json").exists()
    assert (out_dir / "escenarios_por_fila.jsonl").exists()


# ------------------------------------------------------- configuración

def test_config_valida_reconstruye(tmp_path):
    """Configuración válida → reconstrucción de los 161 escenarios."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(DATA, out_dir)
    assert r.returncode == 0, r.stderr[-2000:]
    res = _leer_resumen(out_dir)
    assert res["denominador"]["observaciones_aptas"] == 161
    assert res["denominador"]["reconstruidas"] == 161
    assert res["denominador"]["sin_fuente_klines"] == 0
    assert res["control_coherencia"]["coherentes_numericamente"] == 2
    assert res["control_coherencia"]["con_diferencia_numerica"] == 0
    # Config acreditada (no OperativoConfig por defecto).
    ca = res["config_acreditada"]
    assert ca["operativo_config_sha256"] == (
        "d1423709f4d45207cea601f1aad11742c70f7dfdee44ee69a75701fba60be8ed")
    assert res["config_operativa"]["stop_distance_pct"] == 0.5
    assert res["config_operativa"]["fee_bps"] == 5.0
    assert res["config_operativa"]["max_concurrent"] == 1


def _run_dir_sin_config(tmp_path) -> Path:
    d = _run_dir_valido(tmp_path)
    (d / "config_inicial.json").unlink()
    return d


def test_config_ausente_rechaza_sin_reconstruccion(tmp_path):
    """Configuracion ausente → rechazo (salida no exitosa, sin economia)."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(_run_dir_sin_config(tmp_path), out_dir)
    assert r.returncode == 3, r.stderr[-2000:]
    assert "config_inicial" in r.stderr
    assert not (out_dir / "resumen_ejecutivo.json").exists()


def _run_dir_config_alterada(tmp_path) -> Path:
    d = _run_dir_valido(tmp_path)
    cfg_path = d / "config_inicial.json"
    with io.open(cfg_path, encoding="utf-8") as f:
        datos = json.load(f)
    # Alterar un valor de operativo_config SIN actualizar el hash.
    datos["operativo_config"]["fee_bps"] = 99.0
    with io.open(cfg_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2, sort_keys=True)
    return d


def test_config_alterada_rechaza(tmp_path):
    """Configuracion con hash no coincidente → rechazo."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(_run_dir_config_alterada(tmp_path), out_dir)
    assert r.returncode == 3, r.stderr[-2000:]
    assert "hash" in r.stderr.lower()
    assert not (out_dir / "resumen_ejecutivo.json").exists()


def _run_dir_sin_klines(tmp_path) -> Path:
    d = _run_dir_valido(tmp_path)
    (d / "consultas_klines.jsonl").unlink()
    return d


def test_fuente_klines_ausente_limitacion(tmp_path):
    """Fuente necesaria ausente → limitación (sin reconstrucción económica)."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(_run_dir_sin_klines(tmp_path), out_dir)
    assert r.returncode == 3, r.stderr[-2000:]
    assert "fuente necesaria ausente" in r.stderr
    assert not (out_dir / "resumen_ejecutivo.json").exists()


# ------------------------------------------------------ aislamiento y denominador

def test_aislamiento_entre_escenarios(tmp_path):
    """Cada escenario se reconstruye con su propio adaptador (capacidad 1
    aislada); no hay contaminación entre escenarios ni duplicidad de ids."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(DATA, out_dir)
    assert r.returncode == 0, r.stderr[-2000:]
    filas = _leer_escenarios(out_dir)
    oids = [f["observation_id"] for f in filas]
    assert len(oids) == len(set(oids))  # sin duplicidad
    reconstruidos = [f for f in filas if f.get("reconstruido")]
    assert len(reconstruidos) == 161
    # Cada escenario reconstruido tiene su propia decision propia (no heredada).
    for f in reconstruidos:
        assert f["decision_cf"] in (
            "ENTRADA_EJECUTADA", "RECHAZADA_CAPACIDAD", "SIN_ENTRADA",
            "DESCARTADO"), f["observation_id"]


def test_denominador_completo_sin_ceros(tmp_path):
    """El denominador son las 161 aptas; ninguna se pierde ni se vuelve cero."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(DATA, out_dir)
    assert r.returncode == 0, r.stderr[-2000:]
    res = _leer_resumen(out_dir)
    assert res["denominador"]["observaciones_aptas"] == 161
    assert res["denominador"]["reconstruidas"] == 161
    total = (res["contrafactual_aislado"]["entradas_simulables"]
             + res["contrafactual_aislado"]["abstenciones"]
             + res["contrafactual_aislado"]["descartes"])
    assert total == 161, total


# ----------------------------------------------------------- stop efectivo

def _backtest_long_stop_desde_fill():
    """LONG: precio post-fill toca el stop EFECTIVO (desde fill) pero no el
    stop de REFERENCIA (desde ref_close). Debe salir por stop al nivel
    efectivo, demostrando que gobierna el calculado desde el fill."""
    T = 1700000000000
    ref_close = 100.0                # vela plenamente conocida en T
    stop_referencia = ref_close * 0.995   # 99.5 (NO debe tocarse)
    fill = 101.0                     # precio de entrada (open post-T, open_time_ms > T)
    stop_efectivo = fill * 0.995     # 100.495 (DEBE tocarse y gobernar)
    velas = [
        Candle("TESTUSDT", T - 60000, 99.0, 100.0, 99.0, 100.0, T),        # ref_close
        Candle("TESTUSDT", T + 60000, 101.0, 101.0, 100.9, 100.95,
               T + 120000),                                               # fill (open post-T, > T)
        Candle("TESTUSDT", T + 120000, 100.5, 100.6, 100.4, 100.5,
               T + 180000),                                               # toca stop efectivo (close conocida por vela 3)
        Candle("TESTUSDT", T + 180000, 100.5, 100.5, 100.5, 100.5, None),  # provee close de vela 2
    ]
    config = BacktestConfig(
        family="H1", rules_version="H1-v1", exit_horizon_ms=3_600_000,
        stop_distance_pct=0.5, notional_usdt=1000.0, fee_bps=5.0,
        spread_bps=1.0, slippage_bps=2.0, funding_calendar=CONFIG_FUNDING_NONE,
        max_concurrent=1, partial_fill_notional_cap=None,
        latency_ms=None, tick_size=None, lot_step=None, min_notional_usdt=None,
    )
    evento = StudyEvent("TESTUSDT", T, "LONG", ref_close, "H1", "H1-v1")
    res = run_backtest([evento], velas, config)
    trades = res.get("trades", [])
    assert len(trades) == 1, trades
    tr = trades[0]
    assert tr["exit_reason"] == "stop", tr
    assert tr["entry_px"] == fill, tr
    assert abs(tr["exit_px"] - stop_efectivo) < 1e-9, (tr, stop_efectivo)
    assert abs(tr["exit_px"] - stop_referencia) > 1e-9, (tr, stop_referencia)
    return tr


def _backtest_short_stop_desde_fill():
    """SHORT: precio post-fill toca el stop EFECTIVO (desde fill) pero no el
    stop de REFERENCIA (desde ref_close). Debe salir por stop al nivel
    efectivo, demostrando que gobierna el calculado desde el fill."""
    T = 1700000000000
    ref_close = 100.0                # vela plenamente conocida en T
    stop_referencia = ref_close * 1.005   # 100.5 (NO debe tocarse)
    fill = 99.0                      # precio de entrada (open post-T, open_time_ms > T)
    stop_efectivo = fill * 1.005     # 99.495 (DEBE tocarse y gobernar)
    velas = [
        Candle("TESTUSDT", T - 60000, 100.0, 100.0, 100.0, 100.0, T),     # ref_close
        Candle("TESTUSDT", T + 60000, 99.0, 99.4, 98.9, 99.2,
               T + 120000),                                               # fill (open post-T, > T)
        Candle("TESTUSDT", T + 120000, 99.45, 99.6, 99.4, 99.55,
               T + 180000),                                               # toca stop efectivo (close conocida por vela 3)
        Candle("TESTUSDT", T + 180000, 99.5, 99.5, 99.5, 99.5, None),     # provee close de vela 2
    ]
    config = BacktestConfig(
        family="H1", rules_version="H1-v1", exit_horizon_ms=3_600_000,
        stop_distance_pct=0.5, notional_usdt=1000.0, fee_bps=5.0,
        spread_bps=1.0, slippage_bps=2.0, funding_calendar=CONFIG_FUNDING_NONE,
        max_concurrent=1, partial_fill_notional_cap=None,
        latency_ms=None, tick_size=None, lot_step=None, min_notional_usdt=None,
    )
    evento = StudyEvent("TESTUSDT", T, "SHORT", ref_close, "H1", "H1-v1")
    res = run_backtest([evento], velas, config)
    trades = res.get("trades", [])
    assert len(trades) == 1, trades
    tr = trades[0]
    assert tr["exit_reason"] == "stop", tr
    assert tr["entry_px"] == fill, tr
    assert abs(tr["exit_px"] - stop_efectivo) < 1e-9, (tr, stop_efectivo)
    assert abs(tr["exit_px"] - stop_referencia) > 1e-9, (tr, stop_referencia)
    return tr


def test_stop_long_efectivo_desde_fill_gobierna_sobre_referencia():
    tr = _backtest_long_stop_desde_fill()
    assert abs(tr["exit_px"] - 100.495) < 1e-9, tr
    assert tr["exit_reason"] == "stop"


def test_stop_short_efectivo_desde_fill_gobierna_sobre_referencia():
    tr = _backtest_short_stop_desde_fill()
    assert abs(tr["exit_px"] - 99.495) < 1e-9, tr
    assert tr["exit_reason"] == "stop"


# ------------------------------------------------------- contabilidad

def test_contabilidad_neto_condicionado_es_bruto_menos_costes(tmp_path):
    """Cada entrada reconstruida: neto = bruto - comisiones - spread/slip;
    funding UNKNOWN (nunca cero) para todas."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(DATA, out_dir)
    assert r.returncode == 0, r.stderr[-2000:]
    filas = _leer_escenarios(out_dir)
    comprobadas = 0
    for f in filas:
        if not f.get("reconstruido") or f["decision_cf"] != "ENTRADA_EJECUTADA":
            continue
        bruto = f["gross_pnl_cf"]
        fees = f["fees_cf"]
        slip = f["spread_slip_cf"]
        neto = f["net_pnl_cf"]
        assert bruto is not None and fees is not None and slip is not None
        assert neto is not None
        assert abs(neto - (bruto - fees - slip)) < 1e-6, f["observation_id"]
        assert "UNKNOWN" in (f["funding_estado_cf"] or "")
        comprobadas += 1
    assert comprobadas == 124, comprobadas


def test_no_neto_completo_acreditado(tmp_path):
    out_dir = tmp_path / "out"
    r = _ejecutar_script(DATA, out_dir)
    assert r.returncode == 0, r.stderr[-2000:]
    res = _leer_resumen(out_dir)
    assert res["resultado_usdt_contrafactual"]["neto_completo"]["n"] == 0
    assert res["resultado_usdt_contrafactual"]["funding_completo_n"] == 0
    assert res["resultado_usdt_contrafactual"]["funding_desconocido_n"] == 124


# -------------------------------------------------------------- hash obligatorio

def _run_dir_con_config_alterada(tmp_path, modificar):
    """Copia el run real a temp y aplica `modificar` a config_inicial.json."""
    destino = tmp_path / "run"
    shutil.copytree(DATA, destino)
    cfg_path = destino / "config_inicial.json"
    with io.open(cfg_path, encoding="utf-8") as f:
        datos = json.load(f)
    modificar(datos)
    with io.open(cfg_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2, sort_keys=True)
    return destino


def test_config_hash_valido_reconstruye(tmp_path):
    """Hash valido (run real) -> reconstruye sin rechazar."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(DATA, out_dir)
    assert r.returncode == 0, r.stderr[-2000:]
    res = _leer_resumen(out_dir)
    ca = res["config_acreditada"]
    assert ca["operativo_config_sha256"] == (
        "d1423709f4d45207cea601f1aad11742c70f7dfdee44ee69a75701fba60be8ed")
    assert res["denominador"]["reconstruidas"] == 161


def _modificar_quitar_hash(datos):
    datos.pop("operativo_config_sha256", None)


def test_config_hash_ausente_rechaza(tmp_path):
    """Hash ausente -> rechazo antes de reconstruir."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(_run_dir_con_config_alterada(tmp_path, _modificar_quitar_hash), out_dir)
    assert r.returncode == 3, r.stderr[-2000:]
    assert "ausente o vacio" in r.stderr
    assert not (out_dir / "resumen_ejecutivo.json").exists()


def _modificar_hash_vacio(datos):
    datos["operativo_config_sha256"] = ""


def test_config_hash_vacio_rechaza(tmp_path):
    """Hash vacio -> rechazo antes de reconstruir."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(_run_dir_con_config_alterada(tmp_path, _modificar_hash_vacio), out_dir)
    assert r.returncode == 3, r.stderr[-2000:]
    assert "ausente o vacio" in r.stderr
    assert not (out_dir / "resumen_ejecutivo.json").exists()


def _modificar_hash_invalido(datos):
    datos["operativo_config_sha256"] = "no-es-un-sha256-valido"


def test_config_hash_invalido_rechaza(tmp_path):
    """Hash mal formado -> rechazo antes de reconstruir (se trata como discordante)."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(_run_dir_con_config_alterada(tmp_path, _modificar_hash_invalido), out_dir)
    assert r.returncode == 3, r.stderr[-2000:]
    assert "hash" in r.stderr.lower()
    assert not (out_dir / "resumen_ejecutivo.json").exists()


def _modificar_hash_discordante(datos):
    datos["operativo_config_sha256"] = "0" * 64


def test_config_hash_discordante_rechaza(tmp_path):
    """Hash discordante con el calculado -> rechazo antes de reconstruir."""
    out_dir = tmp_path / "out"
    r = _ejecutar_script(_run_dir_con_config_alterada(tmp_path, _modificar_hash_discordante), out_dir)
    assert r.returncode == 3, r.stderr[-2000:]
    assert "no coincide" in r.stderr
    assert not (out_dir / "resumen_ejecutivo.json").exists()
