# -*- coding: utf-8 -*-
"""Pruebas focalizadas del analisis contrafactual offline de la ventana 4.

- Denominador: las 161 observaciones aptas se evaluan todas; ninguna se pierde
  ni se convierte en cero.
- Aislamiento de escenarios: cada senal evaluada con capacidad 1 aislada; las 2
  operaciones historicas conservan sus valores numericos (control de coherencia).
- Causalidad: el stop se fija desde el precio de referencia en T (ref_close),
  nunca desde el fill de entrada.
- Contabilidad: neto CONDICIONADO = bruto - comisiones - spread/slip; funding
  desconocido (UNKNOWN, nunca cero) para todas las entradas.

Reutiliza `scripts/analisis_contrafactual_ventana4.py` (pipeline existente) y
lee los derivados que genera. Ejecutar con: PYTHONPATH=src pytest
tests/test_analisis_contrafactual_ventana4.py
"""
import json
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(r"C:\proyectos\binance-futures-microstructure-bot")
DATA = Path(r"C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a")
DERIVED = Path(
    r"C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-analisis-contrafactual-20261116"
)
SCRIPT = ROOT / "scripts" / "analisis_contrafactual_ventana4.py"


def _asegurar_derivados():
    """Ejecuta el pipeline de analisis si los derivados no existen."""
    resumen = DERIVED / "resumen_ejecutivo.json"
    escenarios = DERIVED / "escenarios_por_fila.jsonl"
    if not (resumen.exists() and escenarios.exists()):
        r = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=str(ROOT),
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-2000:]
        assert resumen.exists() and escenarios.exists()


def _cargar_escenarios():
    _asegurar_derivados()
    filas = []
    with io.open(DERIVED / "escenarios_por_fila.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                filas.append(json.loads(line))
    return filas


def _cargar_resumen():
    _asegurar_derivados()
    with io.open(DERIVED / "resumen_ejecutivo.json", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- denominador

def test_denominador_161_aptas_todas_evaluadas():
    filas = _cargar_escenarios()
    assert len(filas) == 161, len(filas)
    # Ninguna observation_id desaparece ni se duplica en el escenario.
    oids = [f["observation_id"] for f in filas]
    assert len(set(oids)) == 161
    # Todas tienen decision contrafactual definida (ninguna se convierte en cero/ausente).
    for f in filas:
        assert f["decision_cf"] in (
            "ENTRADA_EJECUTADA", "RECHAZADA_CAPACIDAD", "SIN_ENTRADA",
            "DESCARTADO"), f["observation_id"]


def test_denominador_coincide_con_observaciones_aptas():
    aptas = 0
    with io.open(DATA / "observaciones.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            if o.get("kind") == "observacion" and o.get("apto_para_evaluacion") is True:
                aptas += 1
    assert aptas == 161
    filas = _cargar_escenarios()
    assert len(filas) == aptas


# ------------------------------------------------------- aislamiento / coherencia

def test_aislamiento_capacidad_1_por_escenario():
    resumen = _cargar_resumen()
    assert resumen["contrafactual_aislado"]["entradas_simulables"] == 124
    assert resumen["contrafactual_aislado"]["abstenciones"] == 0
    assert resumen["contrafactual_aislado"]["descartes"] == 37


def test_dos_operaciones_historicas_conservan_valores_aisladas():
    filas = _cargar_escenarios()
    esperadas = {
        "AAVEUSDT|1794857301800": {
            "entry_px": 107.18000000000002, "stop_px": 107.6556,
            "exit_px": 107.7159, "exit_reason": "stop",
            "net_pnl": -6.603999999999848, "funding_desconocido": True},
        "4USDT|1794859045223": {
            "entry_px": 0.008583, "stop_px": 0.008527149999999999,
            "exit_px": 0.008594, "exit_reason": "horizon",
            "net_pnl": -0.31942211348026817, "funding_desconocido": True},
    }
    for f in filas:
        if f["observation_id"] in esperadas:
            ev = esperadas[f["observation_id"]]
            assert f["decision_cf"] == "ENTRADA_EJECUTADA", f["observation_id"]
            assert abs(f["entry_px_cf"] - ev["entry_px"]) < 1e-9
            assert abs(f["stop_px_cf"] - ev["stop_px"]) < 1e-9
            assert abs(f["exit_px_cf"] - ev["exit_px"]) < 1e-9
            assert f["exit_reason_cf"] == ev["exit_reason"]
            assert abs(f["net_pnl_cf"] - ev["net_pnl"]) < 1e-9
            assert "UNKNOWN" in (f["funding_estado_cf"] or "")


# ----------------------------------------------------------- causalidad (stop)

def test_stop_usa_referencia_causal_no_el_fill():
    """stop_px = ref_close x (1 -/+ 0,5%). El fill (open de la primera vela
    post-T) NO es la base del stop."""
    casos = {
        "AAVEUSDT|1794857301800": ("SHORT", 107.120, 107.6556),
        "4USDT|1794859045223": ("LONG", 0.008570, 0.008527149999999999),
    }
    filas = {f["observation_id"]: f for f in _cargar_escenarios()}
    for oid, (direccion, ref_close, stop_esperado) in casos.items():
        f = filas[oid]
        assert f["direction"] == direccion
        assert abs(f["stop_px_cf"] - stop_esperado) < 1e-9
        # El fill (entry_px) es distinto de la referencia causal.
        assert f["entry_px_cf"] != ref_close
        # El stop nunca se calcula como entry_px x (1 -/+ 0,005).
        if direccion == "LONG":
            stop_sobre_fill = f["entry_px_cf"] * (1 - 0.005)
        else:
            stop_sobre_fill = f["entry_px_cf"] * (1 + 0.005)
        assert abs(f["stop_px_cf"] - stop_sobre_fill) > 1e-9


# ------------------------------------------------------------ contabilidad

def test_contabilidad_neto_condicionado_es_bruto_menos_costes():
    filas = _cargar_escenarios()
    comprobadas = 0
    for f in filas:
        if f["decision_cf"] != "ENTRADA_EJECUTADA":
            continue
        bruto = f["gross_pnl_cf"]
        fees = f["fees_cf"]
        slip = f["spread_slip_cf"]
        neto = f["net_pnl_cf"]
        assert bruto is not None and fees is not None and slip is not None
        assert neto is not None
        assert abs(neto - (bruto - fees - slip)) < 1e-6, f["observation_id"]
        # funding desconocido para todas (metodo observed-settlements, sin calendario en resolucion).
        assert "UNKNOWN" in (f["funding_estado_cf"] or "")
        comprobadas += 1
    assert comprobadas == 124, comprobadas


def test_no_hay_neto_completo_acreditado():
    resumen = _cargar_resumen()
    assert resumen["resultado_usdt_contrafactual"]["neto_completo"]["n"] == 0
    assert resumen["resultado_usdt_contrafactual"]["funding_completo_n"] == 0
    assert resumen["resultado_usdt_contrafactual"]["funding_desconocido_n"] == 124
