# -*- coding: utf-8 -*-
"""Pruebas focalizadas del contraste flujo/profundidad de la ventana 4.

- Denominador: las 161 observaciones aptas se evalúan todas; ninguna se pierde
  ni se convierte en cero.
- Grupos: flujo_a_favor + flujo_contrario + insuficiente = 161.
- Ratio: (buy_notional - sell_notional) / (bid_notional_top20 + ask_notional_top20)
  calculado desde los cuerpos originales; denominador finito y > 0.
- Horizonte 60 min resoluble para todas las 161.
- Regla sencilla (signo move_24h_pct): 106/161 = 65.8% de retorno alineado > 0.

Reutiliza scripts/contraste_flujo_profundidad.py (pipeline existente) y lee los
derivados que genera. Ejecutar con: PYTHONPATH=src pytest
tests/test_contraste_flujo_profundidad.py
"""
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\proyectos\binance-futures-microstructure-bot")
DATA = Path(r"C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a")
DERIVED = Path(
    r"C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-contraste-flujo-profundidad-20261116"
)
SCRIPT = ROOT / "scripts" / "contraste_flujo_profundidad.py"


def _ejecutar_script(run_dir: Path, out_dir: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         "--run-dir", str(run_dir), "--out-dir", str(out_dir)],
        cwd=str(ROOT), capture_output=True, text=True)


def _leer_resumen(out_dir: Path):
    with io.open(out_dir / "contraste_flujo_profundidad.json", encoding="utf-8") as f:
        return json.load(f)


def _leer_filas(out_dir: Path):
    filas = []
    with io.open(out_dir / "contraste_filas.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                filas.append(json.loads(line))
    return filas


# ---------------------------------------------------------------- derivados

def test_salida_inexistente_genera_derivados(tmp_path):
    out_dir = tmp_path / "nuevo_derivado"
    assert not out_dir.exists()
    r = _ejecutar_script(DATA, out_dir)
    assert r.returncode == 0, r.stderr[-2000:]
    assert (out_dir / "contraste_flujo_profundidad.json").exists()
    assert (out_dir / "contraste_filas.jsonl").exists()


# ------------------------------------------------------- denominador y grupos

def test_denominador_161_aptas_todas_evaluadas():
    r = _ejecutar_script(DATA, DERIVED)
    assert r.returncode == 0, r.stderr[-2000:]
    res = _leer_resumen(DERIVED)
    d = res["denominador"]
    assert d["observaciones_aptas"] == 161
    assert d["filas_evaluadas"] == 161
    assert d["grupo_datos_insuficientes"] == 0
    assert d["exclusiones"]["horizonte_no_resoluble"] == 0
    assert d["exclusiones"]["ratio_invalido"] == 0
    assert d["exclusiones"]["move_24h_invalido"] == 0
    assert d["exclusiones"]["sin_klines"] == 0


def test_grupos_suman_161_sin_ceros_artificiales():
    r = _ejecutar_script(DATA, DERIVED)
    assert r.returncode == 0, r.stderr[-2000:]
    res = _leer_resumen(DERIVED)
    g = res["resultado_por_grupo_ratio"]
    n_favor = g["flujo_a_favor"]["n"]
    n_contrario = g["flujo_contrario"]["n"]
    n_insuf = g["datos_insuficientes"]["n"]
    assert n_favor + n_contrario + n_insuf == 161, (n_favor, n_contrario, n_insuf)
    assert n_insuf == 0
    # Ningún grupo convierte UNKNOWN en cero: retorno_alineado n debe coincidir con n del grupo.
    assert g["flujo_a_favor"]["continuacion"]["n"] + \
        g["flujo_a_favor"]["reversion"]["n"] + \
        g["flujo_a_favor"]["neutral"]["n"] == n_favor
    assert g["flujo_contrario"]["continuacion"]["n"] + \
        g["flujo_contrario"]["reversion"]["n"] + \
        g["flujo_contrario"]["neutral"]["n"] == n_contrario


# ------------------------------------------------------------ ratio y horizonte

def test_ratio_denominador_finito_positivo():
    r = _ejecutar_script(DATA, DERIVED)
    assert r.returncode == 0, r.stderr[-2000:]
    filas = _leer_filas(DERIVED)
    reconstruidas = [f for f in filas if f.get("reconstruido")]
    assert len(reconstruidas) == 161
    for f in reconstruidas:
        den = (f.get("bid_notional_top20") or 0) + (f.get("ask_notional_top20") or 0)
        assert isinstance(den, (int, float)) and den > 0, f["observation_id"]
        assert isinstance(f.get("ratio_alineado"), (int, float)), f["observation_id"]
        # precio inicial y final resueltos (horizonte 60 min causal)
        assert f.get("precio_inicial_ref_close") is not None, f["observation_id"]
        assert f.get("precio_final_60m") is not None, f["observation_id"]
        assert isinstance(f.get("retorno_alineado"), (int, float)), f["observation_id"]
        assert f["resultado"] in ("continuacion", "reversion", "neutral")


def test_regla_sencilla_referencia_106_161():
    r = _ejecutar_script(DATA, DERIVED)
    assert r.returncode == 0, r.stderr[-2000:]
    res = _leer_resumen(DERIVED)
    rs = res["regla_sencilla_referencia"]
    assert rs["n"] == 161
    assert rs["aciertos_retorno_alineado_positivo"] == 106
    assert abs(rs["proporcion_aciertos"] - 0.658385) < 1e-6


def test_no_desaparecen_descartes_stop():
    """Las 37 observaciones descartadas por la regla de stop siguen en el
    denominador del contraste si tienen datos de flujo/profundidad y precio
    final (no se convierten en cero ni se eliminan en silencio)."""
    r = _ejecutar_script(DATA, DERIVED)
    assert r.returncode == 0, r.stderr[-2000:]
    res = _leer_resumen(DERIVED)
    d = res["denominador"]
    # Todas las 161 aptas se evaluaron (incluidas las 37 descartadas por stop
    # de la regla operativa, que aquí son solo observaciones de precio).
    assert d["filas_evaluadas"] == 161
