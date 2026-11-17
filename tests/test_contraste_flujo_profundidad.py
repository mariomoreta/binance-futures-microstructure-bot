# -*- coding: utf-8 -*-
"""Pruebas focalizadas del contraste flujo/profundidad de la ventana 4.

- Denominador: las 161 observaciones aptas se evalúan todas; ninguna se pierde
  ni se convierte en cero.
- Grupos: flujo_a_favor + flujo_contrario + insuficiente = 161.
- Ratio: (buy_notional - sell_notional) / (bid_notional_top20 + ask_notional_top20)
  calculado desde los cuerpos originales; denominador finito y > 0.
- Horizonte 60 min resoluble para todas las 161.
- Regla sencilla (signo move_24h_pct): 106/161 = 65.8% de retorno alineado > 0.
- Seleccion de precios: ultima vela 1m plenamente cerrada en/antes de cada
  objetivo; desfase no negativo y < 60 000 ms; grid del minuto; no se usan
  cierres futuros ni velas antiguas como sustituto silencioso.

Reutiliza scripts/contraste_flujo_profundidad.py (pipeline existente) y lee los
derivados que genera. Ejecutar con: PYTHONPATH=src pytest
tests/test_contraste_flujo_profundidad.py
"""
import io
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\proyectos\binance-futures-microstructure-bot")
DATA = Path(r"C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a")
DERIVED = Path(
    r"C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-contraste-flujo-profundidad-20261116-v3"
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


# ------------------------------------------------------ seleccion de precios

def _importar_seleccionar_vela():
    spec = importlib.util.spec_from_file_location(
        "contraste_flujo_profundidad_mod", str(SCRIPT))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.seleccionar_vela_cerrada


def _klines_json(velas):
    """velas: lista de (open_time_ms, open, high, low, close, close_time_ms)."""
    filas = []
    for ot, o, h, l, c, ct in velas:
        filas.append([ot, str(o), str(h), str(l), str(c), "100.0",
                      str(ct), "1000.0", "10", "50.0", "5000.0", "0"])
    return json.dumps(filas)


def _mkvela(open_ms, precio):
    """Vela 1m valida: open alineado al minuto, close = open + 59999."""
    return (open_ms, precio, precio + 1, precio - 1, precio, open_ms + 59999)


def test_seleccion_vela_trayectoria_completa_valida():
    """Objetivo no alineado al minuto con vela cerrada cercana: se selecciona
    la ultima vela cerrada <= objetivo con desfase < 60 000 ms."""
    seleccionar = _importar_seleccionar_vela()
    objetivo = 1700000000123  # no alineado al minuto
    vela_cerrada = _mkvela(1699999920000, 100.0)  # close = 1699999979999
    vela_posterior = _mkvela(1699999980000, 101.0)  # close = 1699999999999 > objetivo
    cuerpo = _klines_json([vela_cerrada, vela_posterior])
    r = seleccionar(cuerpo, objetivo)
    assert r["valido"] is True, r
    assert r["close_time_ms"] == 1699999979999
    assert r["precio_close"] == 100.0
    assert r["desfase_ms"] == objetivo - 1699999979999  # 124 ms
    assert 0 <= r["desfase_ms"] < 60000


def test_vela_posterior_objetivo_no_se_usa():
    """Hay una vela cerrada antes del objetivo y otra despues: se usa la
    anterior (valida), nunca la posterior aunque este mas cerca del objetivo."""
    seleccionar = _importar_seleccionar_vela()
    objetivo = 1700000000000
    # Vela valida cierra en 1699999979999 (<= objetivo). Vela posterior cierra
    # en 1700000005999 (> objetivo, no debe usarse).
    cuerpo = _klines_json([_mkvela(1699999920000, 50.0), _mkvela(1700000000000, 200.0)])
    r = seleccionar(cuerpo, objetivo)
    assert r["valido"] is True, r
    assert r["close_time_ms"] == 1699999979999  # la anterior, no la posterior
    assert r["precio_close"] == 50.0
    assert r["desfase_ms"] == 20001


def test_solo_vela_posterior_no_se_usa():
    """La unica vela cerrada esta estrictamente posterior al objetivo: no hay
    cierre valido <= objetivo, se marca limitada."""
    seleccionar = _importar_seleccionar_vela()
    objetivo = 1700000000000
    # Unica vela cierra en 1700000005999, posterior al objetivo.
    cuerpo = _klines_json([_mkvela(1700000000000, 200.0)])
    r = seleccionar(cuerpo, objetivo)
    assert r["valido"] is False, r
    assert r["motivo"] == "sin_vela_cerrada_en_objetivo"


def test_solo_vela_inicial_falta_final_limitada():
    """Objetivo tal que la unica vela cerrada disponible queda muy antigua
    (desfase >= 60 000 ms): no es valida, se marca limitada."""
    seleccionar = _importar_seleccionar_vela()
    objetivo = 1700000120000  # a 2 minutos de la vela disponible
    cuerpo = _klines_json([_mkvela(1699999920000, 100.0)])  # close = 1699999979999
    r = seleccionar(cuerpo, objetivo)
    assert r["valido"] is False, r


def test_trayectoria_truncada_antes_horizonte():
    """Las velas disponibles terminan antes del objetivo: no hay cierre valido."""
    seleccionar = _importar_seleccionar_vela()
    objetivo = 1700001000000  # muy despues de la ultima vela disponible
    cuerpo = _klines_json([_mkvela(1699999920000, 100.0)])
    r = seleccionar(cuerpo, objetivo)
    assert r["valido"] is False, r


def test_objetivo_alineado_al_minuto_desfase_cero():
    """Objetivo igual a un close_time: desfase cero, valido."""
    seleccionar = _importar_seleccionar_vela()
    objetivo = 1699999979999  # igual al close de la vela
    cuerpo = _klines_json([_mkvela(1699999920000, 100.0)])
    r = seleccionar(cuerpo, objetivo)
    assert r["valido"] is True, r
    assert r["desfase_ms"] == 0


def test_grid_no_alineado_no_se_usa():
    """Vela cuya apertura no es multiplo de 60 000 ms: no se usa aunque
    tenga close <= objetivo."""
    seleccionar = _importar_seleccionar_vela()
    objetivo = 1700000000000
    # open no alineado al minuto (no es multiplo de 60000)
    cuerpo = _klines_json([(1699999920001, 100.0, 101.0, 99.0, 100.0,
                            1699999979999)])
    r = seleccionar(cuerpo, objetivo)
    assert r["valido"] is False, r


# ------------------------------------------------------ denominador y grupos

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


def _leer_filas(out_dir: Path):
    filas = []
    with io.open(out_dir / "contraste_filas.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                filas.append(json.loads(line))
    return filas


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
    # de la regla operativa, que aqui son solo observaciones de precio).
    assert d["filas_evaluadas"] == 161


def test_horizonte_acreditado_todas_las_filas():
    """Cada fila reconstruida tiene horizonte efectivo = 3 600 000 ms,
    desfases < 60 000 ms y grid del minuto verificado (sin sustitutos
    silenciosos)."""
    r = _ejecutar_script(DATA, DERIVED)
    assert r.returncode == 0, r.stderr[-2000:]
    filas = _leer_filas(DERIVED)
    reconstruidas = [f for f in filas if f.get("reconstruido")]
    assert len(reconstruidas) == 161
    for f in reconstruidas:
        assert f["horizonte_efectivo_ms"] == 3600000, f["observation_id"]
        assert f["horizonte_discrepante"] is False, f["observation_id"]
        assert 0 <= f["inicial_desfase_ms"] < 60000, f["observation_id"]
        assert 0 <= f["final_desfase_ms"] < 60000, f["observation_id"]
        assert (f["inicial_open_ms"] or -1) % 60000 == 0, f["observation_id"]
        assert (f["final_open_ms"] or -2) % 60000 == 0, f["observation_id"]
        assert f["final_close_ms"] == f["final_open_ms"] + 59999, f["observation_id"]
        assert f["inicial_close_ms"] == f["inicial_open_ms"] + 59999, f["observation_id"]
