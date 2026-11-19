# -*- coding: utf-8 -*-
"""Pruebas focalizadas de la salida temprana por primer cambio observable.

Cubren los cinco escenarios exigidos por la tarea:

  1. cambio conocido despues del cierre de su bloque (la salida usa la
     disponibilidad, no el cierre del bloque);
  2. cambio demasiado tarde para adelantar (se conserva la salida original);
  3. vela exacta de salida alternativa ausente (no evaluable, sin saltar);
  4. hueco que impide conocer el primer cambio (no evaluable, no "sin cambio");
  5. calculo LONG/SHORT con la misma entrada.

Ademas: prioridad publicada, bloques b_4/b_5 irrelevantes, invariancia del
delta con 16 bps iguales en ambos lados y umbral de 30 pares.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from salida_temprana_ventana4 import (  # noqa: E402
    ESTADO_ADELANTADA,
    ESTADO_CONSERVADA,
    ESTADO_NO_EVALUABLE,
    MOTIVO_COINCIDE,
    MOTIVO_HUECO,
    MOTIVO_SIN_CAMBIO,
    MOTIVO_SIN_TIEMPO,
    MOTIVO_VELA_ALT_AUSENTE,
    MOTIVO_ORIGINAL_NO_RESOLUBLE,
    TIPOS_PRIORIDAD,
    _resumen_niveles,
    agregados,
    disponibilidad_acreditante,
    evaluar_ancla,
)

T3 = 1_800_000_000_000          # multiplo exacto de 60_000
CUT = T3 + 61_500               # corte: cierre nominal + 1,5 s
B0 = T3 + 60_000                # minuto del corte
ENTRADA = T3 + 120_000          # apertura del primer minuto tras el corte
SALIDA_ORIG = ENTRADA + 300_000
SYMBOL = "XUSDT"
TERNA = f"{SYMBOL}|{T3}"


class Ventana(object):
    def __init__(self, inicio, fin, buy, sell, cierre, disp, prof):
        self.ventana_inicio_ms = inicio
        self.ventana_fin_ms = fin
        self.buy_notional = buy
        self.sell_notional = sell
        self.precio_cierre = cierre
        self.disponibilidad_ms = disp
        self.observation_id = f"obs-{inicio}"
        self._prof = prof

    def profundidad_contraria(self, direccion):
        return self._prof


def _ventanas(direccion, alineado_3=5000.0, d3=500.0, cierre=100.0):
    if direccion == "LONG":
        buy, sell = 1000.0 + alineado_3, 1000.0
    else:
        buy, sell = 1000.0, 1000.0 + alineado_3
    a = Ventana(T3 - 120_000, T3 - 60_000, 0.0, 0.0, cierre, T3 - 60_000,
                d3)
    b = Ventana(T3 - 60_000, T3, 0.0, 0.0, cierre, T3, d3)
    c = Ventana(T3, T3 + 60_000, buy, sell, cierre, CUT, d3)
    return {"a": a, "b": b, "c": c}


def _fila_flujo(t, buy, sell, cierre, as_of=None, quality="OK"):
    fin = t + 60_000
    return {
        "symbol": SYMBOL,
        "bucket_start": t,
        "bucket_end": fin,
        "buy_notional": buy,
        "sell_notional": sell,
        "price_close": cierre,
        "data_quality": quality,
        "as_of_ms": fin + 100 if as_of is None else as_of,
        "run_id": "test",
    }


def _fila_libro(t, bid, ask, as_of=None):
    fin = t + 60_000
    return {
        "symbol": SYMBOL,
        "bucket_start": t,
        "bucket_end": fin,
        "bid20_mean": bid,
        "ask20_mean": ask,
        "degraded": 0,
        "depth_gaps": 0,
        "crossed": 0,
        "as_of_ms": fin + 100 if as_of is None else as_of,
        "run_id": "test",
    }


def _vela(apertura, final=True, conflictiva=False):
    return {
        "open": apertura,
        "high": apertura,
        "low": apertura,
        "close": apertura,
        "final": final,
        "conflictiva": conflictiva,
    }


def _mundo(
    direccion="LONG",
    bloques=None,
    alineado_3=5000.0,
    d3=500.0,
    velas_extra=None,
    libro=True,
    episodio_extra=None,
):
    """Mundo sintetico minimo para `evaluar_ancla`.

    `bloques`: {k: None | dict(buy=, sell=, cierre=, as_of=, quality=)}.
    Un k ausente del dict equivale a una fila de flujo inexistente.
    """
    ventanas = _ventanas(direccion, alineado_3=alineado_3, d3=d3)
    indice = {
        SYMBOL: {
            T3 - 120_000: ventanas["a"],
            T3 - 60_000: ventanas["b"],
            T3: ventanas["c"],
        }
    }
    flujo = {}
    book = {}
    for k, spec in (bloques or {}).items():
        if spec is None:
            continue
        t = B0 + k * 60_000
        flujo[(SYMBOL, t)] = _fila_flujo(
            t, spec.get("buy", 0.0), spec.get("sell", 0.0),
            spec.get("cierre", 100.0), as_of=spec.get("as_of"),
            quality=spec.get("quality", "OK"))
        if libro:
            book[(SYMBOL, t)] = _fila_libro(
                t, spec.get("bid", 100.0), spec.get("ask", 100.0),
                as_of=spec.get("as_of_libro"))
    velas = {SYMBOL: {
        ENTRADA: _vela(100.0),
        ENTRADA + 60_000: _vela(105.0),
        ENTRADA + 120_000: _vela(107.0),
        ENTRADA + 180_000: _vela(108.0),
        SALIDA_ORIG: _vela(110.0),
    }}
    for k, v in (velas_extra or {}).items():
        if v is None:
            velas[SYMBOL].pop(k, None)
        else:
            velas[SYMBOL][k] = v
    episodio = {
        "symbol": SYMBOL,
        "direccion": direccion,
        "cut_ms": CUT,
        "terna": TERNA,
        "ancla_patron": False,
    }
    episodio.update(episodio_extra or {})
    fila_terna = {"terna": TERNA,
                  "ventanas": [T3 - 120_000, T3 - 60_000, T3]}
    return episodio, fila_terna, indice, flujo, book, velas


def _evaluar(mundo):
    episodio, fila_terna, indice, flujo, book, velas = mundo
    return evaluar_ancla(episodio, fila_terna, indice, flujo, book, velas)


def _sin_cambio(direccion="LONG"):
    """Bloques b_0..b_3 utiles y sin ningun tipo de cambio."""
    buy, sell = (7000.0, 1000.0) if direccion == "LONG" else (1000.0, 7000.0)
    return {k: {"buy": buy, "sell": sell, "cierre": 100.0 + (k + 1)}
            for k in range(4)}


def _giro(direccion="LONG", **kw):
    buy, sell = (1000.0, 2000.0) if direccion == "LONG" else (2000.0, 1000.0)
    spec = {"buy": buy, "sell": sell, "cierre": 100.0}
    spec.update(kw)
    return spec


# ---------------------------------------------------------------------------
# 1. Cambio conocido despues del cierre de su bloque
# ---------------------------------------------------------------------------

def test_giro_en_b0_usa_la_disponibilidad_no_el_cierre_del_bloque():
    # as_of 500 ms despues de la entrada: el primer minuto posterior es
    # ENTRADA+1min, no ENTRADA.
    ficha = _evaluar(_mundo(bloques={0: _giro(as_of=ENTRADA + 500)}))
    assert ficha["estado"] == ESTADO_ADELANTADA
    assert ficha["primer_cambio_tipo"] == "giro"
    assert ficha["primer_cambio_k"] == 0
    assert ficha["disponibilidad_ms"] == ENTRADA + 500
    assert ficha["salida_alternativa_ms"] == ENTRADA + 60_000
    assert ficha["salida_alternativa_ms"] < SALIDA_ORIG
    assert ficha["minutos_adelanto"] == 4


def test_as_of_que_cruza_el_minuto_retrasa_la_salida_un_minuto_mas():
    # El bloque cierra en ENTRADA, pero el dato solo esta disponible 500 ms
    # despues del minuto siguiente: la salida se resuelve en el minuto
    # posterior a esa disponibilidad, no en el cierre del bloque.
    ficha = _evaluar(_mundo(bloques={0: _giro(as_of=ENTRADA + 60_500)}))
    assert ficha["estado"] == ESTADO_ADELANTADA
    assert ficha["disponibilidad_ms"] == ENTRADA + 60_500
    assert ficha["salida_alternativa_ms"] == ENTRADA + 120_000
    assert ficha["salida_alternativa_ms"] != ENTRADA + 60_000


def test_disponibilidad_nunca_es_solo_el_cierre_del_bloque():
    bloque = {"fin_ms": B0 + 60_000, "as_of_flow_ms": B0 + 60_000 + 900,
              "as_of_book_ms": None}
    assert disponibilidad_acreditante(bloque, "giro", None) == B0 + 60_000 + 900


# ---------------------------------------------------------------------------
# 2. Cambio demasiado tarde para adelantar
# ---------------------------------------------------------------------------

def test_cambio_que_coincide_con_la_salida_original_se_conserva():
    bloques = _sin_cambio()
    # b_3 cierra en ENTRADA+4min; un as_of que cae en el minuto de salida
    # empuja la salida alternativa justo a la salida original.
    bloques[3] = _giro(as_of=SALIDA_ORIG - 60_000 + 500)
    ficha = _evaluar(_mundo(bloques=bloques))
    assert ficha["estado"] == ESTADO_CONSERVADA
    assert ficha["motivo"] == MOTIVO_COINCIDE
    assert ficha["salida_alternativa_ms"] == SALIDA_ORIG
    assert ficha["delta_bps"] is None


def test_cambio_posterior_a_la_salida_original_se_conserva():
    bloques = _sin_cambio()
    bloques[3] = _giro(as_of=SALIDA_ORIG + 500)
    ficha = _evaluar(_mundo(bloques=bloques))
    assert ficha["estado"] == ESTADO_CONSERVADA
    assert ficha["motivo"] == MOTIVO_SIN_TIEMPO
    assert ficha["salida_alternativa_ms"] > SALIDA_ORIG


def test_sin_cambio_utilizable_se_conserva_la_salida_original():
    ficha = _evaluar(_mundo(bloques=_sin_cambio()))
    assert ficha["estado"] == ESTADO_CONSERVADA
    assert ficha["motivo"] == MOTIVO_SIN_CAMBIO
    assert ficha["delta_bps"] is None


def test_bloques_b4_y_b5_no_pueden_adelantar():
    bloques = _sin_cambio()
    bloques[4] = _giro()
    ficha = _evaluar(_mundo(bloques=bloques))
    assert ficha["estado"] == ESTADO_CONSERVADA
    assert ficha["motivo"] == MOTIVO_SIN_CAMBIO


def test_hueco_en_b4_no_afecta_a_la_conservacion():
    bloques = _sin_cambio()
    bloques[4] = None
    ficha = _evaluar(_mundo(bloques=bloques))
    assert ficha["estado"] == ESTADO_CONSERVADA
    assert ficha["motivo"] == MOTIVO_SIN_CAMBIO


# ---------------------------------------------------------------------------
# 3. Vela exacta de salida alternativa ausente
# ---------------------------------------------------------------------------

def test_vela_alternativa_ausente_es_no_evaluable_sin_saltar():
    ficha = _evaluar(_mundo(
        bloques={0: _giro(as_of=ENTRADA + 500)},
        velas_extra={ENTRADA + 60_000: None}))
    assert ficha["estado"] == ESTADO_NO_EVALUABLE
    assert ficha["motivo"] == MOTIVO_VELA_ALT_AUSENTE
    assert ficha["salida_alternativa_ms"] == ENTRADA + 60_000
    assert ficha["delta_bps"] is None


def test_vela_alternativa_contradictoria_es_no_evaluable():
    ficha = _evaluar(_mundo(
        bloques={0: _giro(as_of=ENTRADA + 500)},
        velas_extra={ENTRADA + 60_000: _vela(105.0, conflictiva=True)}))
    assert ficha["estado"] == ESTADO_NO_EVALUABLE
    assert ficha["motivo"] == "vela_salida_alternativa_contradictoria"


# ---------------------------------------------------------------------------
# 4. Hueco que impide conocer el primer cambio
# ---------------------------------------------------------------------------

def test_hueco_en_b0_no_se_convierte_en_sin_cambio():
    ficha = _evaluar(_mundo(
        bloques={0: _giro(quality="PARTIAL_OK"),
                 1: {"buy": 7000.0, "sell": 1000.0, "cierre": 101.0}}))
    assert ficha["estado"] == ESTADO_NO_EVALUABLE
    assert ficha["motivo"] == MOTIVO_HUECO
    assert ficha["hueco_k"] == 0
    assert ficha["delta_bps"] is None


def test_hueco_tras_un_bloque_sin_cambio_es_no_evaluable():
    bloques = _sin_cambio()
    del bloques[1]
    ficha = _evaluar(_mundo(bloques=bloques))
    assert ficha["estado"] == ESTADO_NO_EVALUABLE
    assert ficha["motivo"] == MOTIVO_HUECO
    assert ficha["hueco_k"] == 1


def test_bloque_ausente_del_todo_es_hueco():
    ficha = _evaluar(_mundo(bloques={}))
    assert ficha["estado"] == ESTADO_NO_EVALUABLE
    assert ficha["motivo"] == MOTIVO_HUECO
    assert ficha["hueco_k"] == 0


# ---------------------------------------------------------------------------
# 5. LONG y SHORT con la misma entrada
# ---------------------------------------------------------------------------

def test_long_y_short_comparten_entrada_y_salidas_con_signo_opuesto():
    largo = _evaluar(_mundo(direccion="LONG",
                            bloques={0: _giro("LONG", as_of=ENTRADA + 500)}))
    corto = _evaluar(_mundo(direccion="SHORT",
                            bloques={0: _giro("SHORT", as_of=ENTRADA + 500)}))
    assert largo["precio_entrada"] == corto["precio_entrada"] == 100.0
    assert largo["salida_alternativa_ms"] == corto["salida_alternativa_ms"]
    assert largo["precio_salida_original"] == 110.0
    assert corto["precio_salida_original"] == 110.0
    # LONG: 100 -> 110 = +1000 bps; salida en 105 = +500 bps; delta -500.
    assert largo["retorno_original_bps"] == pytest.approx(1000.0)
    assert largo["retorno_alternativo_bps"] == pytest.approx(500.0)
    assert largo["delta_bps"] == pytest.approx(-500.0)
    # SHORT: 100 -> 110 = -1000 bps; salida en 105 = -500 bps; delta +500.
    assert corto["retorno_original_bps"] == pytest.approx(-1000.0)
    assert corto["retorno_alternativo_bps"] == pytest.approx(-500.0)
    assert corto["delta_bps"] == pytest.approx(500.0)
    assert largo["delta_bps"] == pytest.approx(-corto["delta_bps"])


def test_short_que_recorta_perdida_da_delta_positivo():
    # SHORT con precio subiendo: la salida temprana recorta la perdida.
    ficha = _evaluar(_mundo(direccion="SHORT",
                            bloques={0: _giro("SHORT", as_of=ENTRADA + 500)}))
    assert ficha["retorno_original_bps"] < 0
    assert ficha["delta_bps"] > 0


# ---------------------------------------------------------------------------
# Prioridad publicada
# ---------------------------------------------------------------------------

def test_prioridad_giro_sobre_profundidad():
    # giro (alineado <= 0) y profundidad contraria por encima de d3.
    ficha = _evaluar(_mundo(
        bloques={0: _giro("LONG", ask=5000.0, as_of=ENTRADA + 500)},
        d3=500.0))
    assert ficha["primer_cambio_tipos"] == ["giro",
                                          "profundidad_deja_de_caer"]
    assert ficha["primer_cambio_tipo"] == "giro"


def test_prioridad_debilitamiento_sobre_precio_sin_avance():
    # alineado positivo menor que el de la tercera ventana y cierre que baja.
    ficha = _evaluar(_mundo(
        bloques={0: {"buy": 3000.0, "sell": 1000.0, "cierre": 99.0,
                     "as_of": ENTRADA + 500}}))
    assert ficha["primer_cambio_tipos"] == ["debilitamiento",
                                          "precio_sin_avance"]
    assert ficha["primer_cambio_tipo"] == "debilitamiento"


def test_orden_de_prioridad_declarado():
    assert TIPOS_PRIORIDAD == ("giro", "debilitamiento", "precio_sin_avance",
                               "profundidad_deja_de_caer")


# ---------------------------------------------------------------------------
# Coste simulado y umbral
# ---------------------------------------------------------------------------

def test_coste_igual_en_ambos_lados_no_cambia_el_delta():
    pares = [
        {"retorno_original_bps": -100.0, "retorno_alternativo_bps": -50.0},
        {"retorno_original_bps": 200.0, "retorno_alternativo_bps": 120.0},
    ]
    niveles = _resumen_niveles(pares)
    assert niveles["coste_ida_vuelta_bps"] == 16.0
    # Brutos: original medio 50, alternativa media 35.
    assert niveles["original_bruto_media_bps"] == pytest.approx(50.0)
    assert niveles["alternativa_bruto_media_bps"] == pytest.approx(35.0)
    # Netos: ambos lados pagan los mismos 16 bps.
    assert niveles["original_neto_media_bps"] == pytest.approx(34.0)
    assert niveles["alternativa_neto_media_bps"] == pytest.approx(19.0)
    # El delta es invariante al coste igual.
    assert niveles["delta_media_bps"] == pytest.approx(-15.0)


def _ficha_sintetica(direccion, estado, delta, original, tipo=None, k=0):
    return {
        "estado": estado,
        "motivo": None,
        "ancla_patron": False,
        "original_estado": "resoluble",
        "direccion": direccion,
        "primer_cambio_tipo": tipo,
        "primer_cambio_k": k,
        "delta_bps": delta,
        "retorno_original_bps": original,
        "retorno_alternativo_bps": (None if delta is None else original + delta),
        "disponibilidad_antes_de_entrada": False,
        "minuto_distinto_por_definicion": False,
    }


def test_agregados_separan_perdidas_recortadas_y_ganancias_sacrificadas():
    fichas = [
        _ficha_sintetica("LONG", ESTADO_ADELANTADA, 50.0, -100.0, "giro"),
        _ficha_sintetica("SHORT", ESTADO_ADELANTADA, -50.0, 100.0, "giro"),
        _ficha_sintetica("LONG", ESTADO_ADELANTADA, 0.0, 10.0, "giro"),
        _ficha_sintetica("LONG", ESTADO_CONSERVADA, None, 10.0),
        _ficha_sintetica("LONG", ESTADO_NO_EVALUABLE, None, 10.0),
    ]
    m = agregados(fichas, {})
    assert m["embudo"]["anclas"] == 5
    assert m["embudo"]["adelantada_resoluble"] == 3
    assert m["embudo"]["original_conservada"] == 1
    assert m["embudo"]["no_evaluable"] == 1
    assert m["embudo"]["pares_evaluables"] == 4
    assert m["embudo"]["pares_con_salida_adelantada"] == 3
    pr = m["pares_adelantados"]["perdidas_recortadas"]
    gs = m["pares_adelantados"]["ganancias_sacrificadas"]
    assert pr["n"] == 1 and pr["suma_bps"] == pytest.approx(50.0)
    assert gs["n"] == 1 and gs["suma_bps"] == pytest.approx(-50.0)
    assert m["pares_adelantados"]["iguales"] == 1
    assert m["pares_adelantados"]["original_negativo"] == 1
    assert m["pares_adelantados"]["original_positivo"] == 2
    assert m["pares_adelantados"]["original_cero"] == 0


def test_descomposicion_de_perdidas_y_ganancias_es_exhaustiva():
    fichas = [
        _ficha_sintetica("LONG", ESTADO_ADELANTADA, 50.0, -100.0, "giro"),
        _ficha_sintetica("LONG", ESTADO_ADELANTADA, -30.0, -100.0, "giro"),
        _ficha_sintetica("LONG", ESTADO_ADELANTADA, -40.0, 100.0, "giro"),
        _ficha_sintetica("LONG", ESTADO_ADELANTADA, 20.0, 100.0, "giro"),
        _ficha_sintetica("LONG", ESTADO_ADELANTADA, 7.0, 0.0, "giro"),
    ]
    m = agregados(fichas, {})
    p = m["pares_adelantados"]
    suma_cubos = (p["perdidas_recortadas"]["suma_bps"]
                  + p["ganancias_sacrificadas"]["suma_bps"]
                  + p["perdidas_empeoradas"]["suma_bps"]
                  + p["ganancias_extra"]["suma_bps"]
                  + p["original_neutro"]["suma_bps"])
    assert suma_cubos == pytest.approx(p["suma_bps"])
    assert p["original_neutro"]["n"] == 1
    assert p["original_negativo"] == 2
    assert p["original_positivo"] == 2
    assert p["original_cero"] == 1


def test_menos_de_30_pares_adelantados_es_insuficiente():
    fichas = [_ficha_sintetica("LONG", ESTADO_ADELANTADA, 10.0, -10.0, "giro")
              for _ in range(29)]
    m = agregados(fichas, {})
    assert m["veredicto"]["veredicto"] == "INSUFICIENTE"


def test_treinta_pares_no_declaran_insuficiencia_por_conteo():
    fichas = [_ficha_sintetica("LONG", ESTADO_ADELANTADA, 10.0, -10.0, "giro")
              for _ in range(30)]
    m = agregados(fichas, {})
    assert m["veredicto"]["veredicto"] != "INSUFICIENTE"
    assert m["veredicto"]["pares_adelantados"] == 30


def test_original_no_resoluble_es_no_evaluable():
    episodio, fila_terna, indice, flujo, book, velas = _mundo(
        bloques={0: _giro(as_of=ENTRADA + 500)})
    velas[SYMBOL].pop(ENTRADA)
    ficha = evaluar_ancla(episodio, fila_terna, indice, flujo, book, velas)
    assert ficha["estado"] == ESTADO_NO_EVALUABLE
    assert ficha["motivo"] == MOTIVO_ORIGINAL_NO_RESOLUBLE
    assert ficha["delta_bps"] is None


def test_dos_bloques_con_tipos_no_adelantan_el_orden():
    # Un cambio en b_1 no se usa si b_0 ya tenia cambio.
    bloques = {0: _giro(as_of=ENTRADA + 500),
               1: {"buy": 1000.0, "sell": 9000.0, "cierre": 90.0}}
    ficha = _evaluar(_mundo(bloques=bloques))
    assert ficha["primer_cambio_k"] == 0
    assert ficha["salida_alternativa_ms"] == ENTRADA + 60_000


def test_ficha_del_patron_se_marca_sin_duplicar():
    ficha = _evaluar(_mundo(
        bloques={0: _giro(as_of=ENTRADA + 500)},
        episodio_extra={"ancla_patron": True}))
    assert ficha["ancla_patron"] is True
