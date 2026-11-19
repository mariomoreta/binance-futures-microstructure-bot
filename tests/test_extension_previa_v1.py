"""Pruebas enfocadas de la evaluacion de extension previa.

Cubren la definicion predeclarada: bloques contiguos no solapados, extension,
disponibilidad al corte, motivos de exclusion, signo LONG/SHORT, coste,
grupos y criterio de decision.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extension_previa_v1 as ev  # noqa: E402

BASE = 60_000 * 28_000_000  # alineado a minuto


def _fila(open_: float, close: float, t: int, dq: str = "OK", as_of: int | None = None):
    return {
        "open": open_,
        "close": close,
        "close_time": t + 59_999,
        "final": True,
        "adquirido_ms": as_of if as_of is not None else t + 100,
        "conflictiva": False,
        "fuente": "test",
        "data_quality": dq,
    }


def _serie_simple(
    symbol: str = "AAAUSDT",
    avance_bloque: float = 0.01,
    avance_senal: float = 0.03,
    entrada: float = 100.0,
    salida: float | None = None,
    dq_previos: str = "OK",
    as_of_previos: int | None = None,
    faltan_previos: int = 0,
    sin_entrada: bool = False,
    sin_salida: bool = False,
):
    """Serie sintetica: 18 minutos previos, 3 de senal, entrada y salida."""
    t1 = BASE
    serie = {}
    # Bloques previos: cada bloque de 3 minutos avanza `avance_bloque`.
    for i in range(18):
        t = t1 - (18 - i) * 60_000
        bloque = i // 3
        pos = i % 3
        close = 100.0 * (1.0 + avance_bloque) ** (bloque + (1 if pos == 2 else 0))
        serie[t] = _fila(close, close, t, dq=dq_previos, as_of=as_of_previos)
    # Senal: tres cierres monotonos con avance total `avance_senal`.
    paso = (1.0 + avance_senal) ** (1 / 2)
    c1 = 100.0
    c2 = c1 * paso
    c3 = c2 * paso
    for k, close in enumerate((c1, c2, c3)):
        t = t1 + k * 60_000
        serie[t] = _fila(close, close, t)
    # Entrada y salida.
    entrada_ms = (BASE + 180_000 + 400) // 60_000 * 60_000 + 60_000
    if not sin_entrada:
        serie[entrada_ms] = _fila(entrada, entrada, entrada_ms)
    if not sin_salida:
        serie[entrada_ms + 300_000] = _fila(
            salida if salida is not None else entrada * 1.01,
            salida if salida is not None else entrada * 1.01,
            entrada_ms + 300_000,
        )
    if faltan_previos:
        for i in range(faltan_previos):
            t = t1 - (i + 1) * 60_000
            serie.pop(t, None)
    return serie


def _episodio(direccion: str = "LONG", cut: int | None = None):
    return {
        "symbol": "AAAUSDT",
        "direccion": direccion,
        "cut_ms": cut if cut is not None else BASE + 180_400,
        "cut_iso": "2026-11-06T05:52:00.400000+00:00",
        "cierre_nominal_ms": BASE + 180_000,
        "terna": f"AAAUSDT|{BASE + 120_000}",
        "tambien_patron": False,
    }


def _evaluar(serie, direccion="LONG", cut=None):
    return ev.evaluar_episodio(_episodio(direccion, cut), {"AAAUSDT": serie}, "test")


# ---------------------------------------------------------------------------
# Definicion
# ---------------------------------------------------------------------------

def test_extension_es_cociente_entre_avance_senal_y_mediana_previa():
    r = _evaluar(_serie_simple(avance_bloque=0.01, avance_senal=0.03))
    assert r["estado"] == "evaluable"
    assert r["bloques_previos"] == 6
    assert r["mediana_previa"] == pytest.approx(0.01, rel=1e-9)
    assert r["extension"] == pytest.approx(3.0, rel=1e-6)
    assert r["grupo"] == "EXTENDIDO"


def test_umbral_uno_es_normal_y_por_encima_es_extendido():
    assert ev._grupo(1.0) == "NORMAL"
    assert ev._grupo(0.9999999) == "NORMAL"
    assert ev._grupo(1.0000001) == "EXTENDIDO"
    igual = _evaluar(_serie_simple(avance_bloque=0.02, avance_senal=0.02))
    assert igual["extension"] == pytest.approx(1.0, rel=1e-6)
    assert igual["grupo"] == ev._grupo(igual["extension"])
    encima = _evaluar(_serie_simple(avance_bloque=0.02, avance_senal=0.0201))
    assert encima["grupo"] == "EXTENDIDO"


def test_bloques_previos_son_contiguos_y_no_solapan():
    serie = _serie_simple()
    minutos, motivo = ev._minutos_previos(serie, BASE, BASE + 180_400)
    assert motivo is None
    assert len(minutos) == 18
    assert minutos == [BASE - (18 - i) * 60_000 for i in range(18)]
    for a, b in zip(minutos, minutos[1:]):
        assert b - a == 60_000


def test_mediana_previa_nula_no_es_evaluable():
    r = _evaluar(_serie_simple(avance_bloque=0.0, avance_senal=0.03))
    assert r["estado"] == "no_evaluable"
    assert r["motivo"] == "mediana_previa_nula"


# ---------------------------------------------------------------------------
# Disponibilidad al corte y huecos
# ---------------------------------------------------------------------------

def test_minuto_previo_no_disponible_al_corte_rompe_la_historia():
    cut = BASE + 180_400
    serie = _serie_simple(as_of_previos=cut + 1)
    r = _evaluar(serie, cut=cut)
    assert r["estado"] == "no_evaluable"
    assert r["motivo"] == "historia_previa_insuficiente"
    assert r["detalle_motivo"] == "minuto_previo_no_disponible_al_corte"


def test_minuto_previo_partial_ok_rompe_la_historia():
    r = _evaluar(_serie_simple(dq_previos="PARTIAL_OK"))
    assert r["estado"] == "no_evaluable"
    assert r["motivo"] == "historia_previa_insuficiente"
    assert r["detalle_motivo"] == "minuto_previo_no_ok"


def test_hueco_en_la_historia_no_se_rellena_con_minutos_anteriores():
    serie = _serie_simple()
    serie.pop(BASE - 16 * 60_000)
    r = _evaluar(serie)
    assert r["estado"] == "no_evaluable"
    assert r["motivo"] == "historia_previa_insuficiente"
    assert r["bloques_previos"] == 5


# ---------------------------------------------------------------------------
# Precios de entrada y salida
# ---------------------------------------------------------------------------

def test_vela_de_entrada_ausente_no_es_evaluable():
    r = _evaluar(_serie_simple(sin_entrada=True))
    assert r["estado"] == "no_evaluable"
    assert r["motivo"] == "vela_entrada_ausente"


def test_vela_de_salida_ausente_no_es_evaluable():
    r = _evaluar(_serie_simple(sin_salida=True))
    assert r["estado"] == "no_evaluable"
    assert r["motivo"] == "vela_salida_ausente"
    assert r["precio_entrada"] == pytest.approx(100.0)


def test_entrada_es_la_apertura_del_minuto_siguiente_al_corte():
    serie = _serie_simple()
    r = _evaluar(serie)
    assert r["entrada_ms"] == BASE + 240_000
    assert r["salida_ms"] == BASE + 540_000


# ---------------------------------------------------------------------------
# Retorno y coste
# ---------------------------------------------------------------------------

def test_long_y_short_con_la_misma_entrada_tienen_signo_opuesto():
    serie = _serie_simple(entrada=100.0, salida=101.0)
    largo = _evaluar(serie, "LONG")
    corto = _evaluar(serie, "SHORT")
    assert largo["retorno_bruto_bps"] == pytest.approx(100.0, rel=1e-9)
    assert corto["retorno_bruto_bps"] == pytest.approx(-100.0, rel=1e-9)
    assert largo["retorno_neto_bps"] == pytest.approx(84.0, rel=1e-9)
    assert corto["retorno_neto_bps"] == pytest.approx(-116.0, rel=1e-9)


def test_coste_simulado_es_16_bps_en_ambos_grupos():
    serie = _serie_simple(avance_bloque=0.01, avance_senal=0.03)
    r = _evaluar(serie)
    assert r["retorno_neto_bps"] == pytest.approx(r["retorno_bruto_bps"] - 16.0, rel=1e-12)


# ---------------------------------------------------------------------------
# Agregados y criterio predeclarado
# ---------------------------------------------------------------------------

def _ep(symbol, direccion, grupo, neto, captura="cap1", extension=None):
    return {
        "captura": captura,
        "symbol": symbol,
        "direccion": direccion,
        "estado": "evaluable",
        "grupo": grupo,
        "extension": extension if extension is not None else (2.0 if grupo == "EXTENDIDO" else 0.5),
        "retorno_neto_bps": neto,
        "retorno_bruto_bps": neto + 16.0,
        "cut_iso": "2026-11-06T05:52:00+00:00",
    }


def test_criterio_requiere_media_y_mediana_y_falla_si_la_media_empeora():
    eps = []
    # NORMAL: mediana y media +10.
    for i in range(40):
        eps.append(_ep(f"N{i}", "LONG", "NORMAL", 10.0))
    # EXTENDIDO: mediana +5 pero un outlier enorme sube la media.
    for i in range(39):
        eps.append(_ep(f"E{i}", "LONG", "EXTENDIDO", 5.0))
    eps.append(_ep("EOUT", "LONG", "EXTENDIDO", 5000.0))
    bloque = ev._agregar(eps, "test")
    assert bloque["criterio"]["condiciones"]["1_mediana_normal_supera_extendido"] is True
    assert bloque["criterio"]["condiciones"]["2_media_normal_supera_extendido"] is False
    assert bloque["veredicto"] == "NO APORTA"


def test_criterio_datos_insuficientes_con_menos_de_30_en_un_grupo():
    eps = [_ep(f"N{i}", "LONG", "NORMAL", 10.0) for i in range(40)]
    eps += [_ep(f"E{i}", "LONG", "EXTENDIDO", 5.0) for i in range(29)]
    bloque = ev._agregar(eps, "test")
    assert bloque["criterio"]["aplica"] is False
    assert bloque["veredicto"] == "DATOS INSUFICIENTES"


def test_criterio_aporta_evidencia_si_se_cumplen_las_cinco_condiciones():
    eps = []
    for i in range(40):
        eps.append(_ep(f"N{i}", "LONG", "NORMAL", 20.0))
    for i in range(40):
        eps.append(_ep(f"E{i}", "LONG", "EXTENDIDO", -20.0))
    # Dos capturas a favor.
    for i in range(10):
        eps.append(_ep(f"N2{i}", "SHORT", "NORMAL", 20.0, captura="cap2"))
        eps.append(_ep(f"E2{i}", "SHORT", "EXTENDIDO", -20.0, captura="cap2"))
    bloque = ev._agregar(eps, "test")
    assert bloque["criterio"]["todas"] is True
    assert bloque["veredicto"] == "APORTA EVIDENCIA"


def test_criterio_exige_que_la_mediana_aguante_sin_el_contrato_dominante():
    eps = []
    # El contrato dominante sostiene la mediana con retornos NORMAL altos.
    for i in range(40):
        eps.append(_ep("DOMINANTE", "LONG", "NORMAL", 100.0))
    for i in range(30):
        eps.append(_ep(f"N{i}", "LONG", "NORMAL", -50.0))
    for i in range(30):
        eps.append(_ep(f"E{i}", "LONG", "EXTENDIDO", 0.0))
    # Segunda captura a favor, con NORMAL por encima de EXTENDIDO.
    for i in range(10):
        eps.append(_ep(f"N2{i}", "SHORT", "NORMAL", -50.0, captura="cap2"))
        eps.append(_ep(f"E2{i}", "SHORT", "EXTENDIDO", -100.0, captura="cap2"))
    bloque = ev._agregar(eps, "test")
    c = bloque["criterio"]
    assert c["detalle"]["contrato_dominante"] == "DOMINANTE"
    assert c["condiciones"]["1_mediana_normal_supera_extendido"] is True
    assert c["condiciones"]["4_mediana_se_mantiene_en_2_capturas"] is True
    assert c["condiciones"]["3_mediana_se_mantiene_sin_contrato_dominante"] is False
    assert bloque["veredicto"] == "NO APORTA"


def test_filtro_cuenta_perdidas_evitadas_y_ganancias_dejadas_pasar():
    eps = [_ep("A", "LONG", "NORMAL", 10.0), _ep("B", "LONG", "EXTENDIDO", -50.0),
           _ep("C", "SHORT", "EXTENDIDO", 30.0)]
    bloque = ev._agregar(eps, "test")
    f = bloque["filtro_descarta_extendido"]
    assert f["descartados"] == 2
    assert f["perdidas_evitadas_bps"] == pytest.approx(-50.0)
    assert f["ganancias_dejadas_pasar_bps"] == pytest.approx(30.0)
    assert f["neto_del_filtro_bps"] == pytest.approx(-20.0)


def test_terciles_cubren_todos_los_episodios():
    eps = [_ep(f"S{i}", "LONG", "NORMAL" if i % 2 else "EXTENDIDO", float(i)) for i in range(30)]
    bloque = ev._agregar(eps, "test")
    assert sum(t["n"] for t in bloque["terciles"]) == 30


def test_bootstrap_es_reproducible():
    a = [float(i) for i in range(40)]
    b = [float(i) * 2 for i in range(40)]
    assert ev._ic_media_bootstrap(a, b) == ev._ic_media_bootstrap(a, b)


def test_veredicto_datos_insuficientes_si_no_hay_evaluables():
    bloque = ev._agregar([], "test")
    assert bloque["evaluables"] == 0
    assert bloque["veredicto"] == "DATOS INSUFICIENTES"
