# -*- coding: utf-8 -*-
"""Pruebas del diagnostico de los cuatro casos (ventana 4, offline).

Cubren lo exigido por el bloque:
  1. un dato tardio desplaza la entrada (uno y dos minutos);
  2. un minuto de espera faltante o incompleto queda sin resolver, con motivo;
  3. la reversion tardia nunca reutiliza la entrada original y comparte precios
     con la continuacion tardia;
  4. la extension previa no se inventa: sin historia o con referencia cero es
     NO_RESOLUBLE, y las ternas previas no se solapan.

Ademas:
  5. la clasificacion del flujo (continuacion / reversion / sin confirmacion);
  6. los denominadores de los controles solo cuentan pares resolubles;
  7. la verificacion contra lo publicado aborta si algo difiere.

Sin red, sin Binance y sin datos reales: ventanas, filas y velas sinteticas.
Ejecutar con: pytest tests/test_diagnostico_cuatro_casos_ventana4.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import diagnostico_cuatro_casos_ventana4 as D  # noqa: E402
from secuencia_presion_v1 import VentanaPresion, utc_iso  # noqa: E402

T0 = 1794857160000
MIN = 60_000


def _ventana(
    symbol: str,
    inicio: int,
    precio: float,
    disp_extra: int = 0,
    buy: float = 10.0,
    sell: float = 3.0,
    bid: float = 100.0,
    ask: float = 100.0,
) -> VentanaPresion:
    fin = inicio + MIN
    disp = fin + disp_extra
    return VentanaPresion(
        symbol=symbol,
        observation_id=f"{symbol}|{inicio}",
        decision_ms=fin,
        decision_iso=utc_iso(fin),
        ventana_inicio_ms=inicio,
        ventana_fin_ms=fin,
        evento_ms=fin,
        evento_iso=utc_iso(fin),
        disponibilidad_ms=disp,
        disponibilidad_iso=utc_iso(disp),
        ventana_completa=True,
        ventana_ms=MIN,
        buy_notional=buy,
        sell_notional=sell,
        bid_notional_top20=bid,
        ask_notional_top20=ask,
        precio_cierre=precio,
        precio_fuente="aggTrade",
        precio_event_ms=fin,
        precio_event_iso=utc_iso(fin),
        integridad_valida=True,
        cobertura={
            "flow_as_of_ms": disp,
            "book_as_of_ms": fin,
            "flow_data_quality": "OK",
        },
    )


def _fila_flujo(
    symbol: str,
    inicio: int,
    buy: float = 20.0,
    sell: float = 5.0,
    as_of_extra: int = 150,
    calidad: str = "OK",
):
    return {
        "symbol": symbol,
        "bucket_start": inicio,
        "bucket_end": inicio + MIN,
        "buy_notional": buy,
        "sell_notional": sell,
        "as_of_ms": inicio + MIN + as_of_extra,
        "data_quality": calidad,
        "last_event_ms": inicio + MIN - 10,
        "run_id": "r",
    }


def _velas(symbol: str, entrada: int, aperturas):
    serie = {}
    for i, px in aperturas.items():
        t = entrada + i * MIN
        serie[t] = {
            "open": px,
            "high": px,
            "low": px,
            "close": px,
            "final": True,
            "conflictiva": False,
        }
    return {symbol: serie}


# ---------------------------------------------------------------------------
# 1. El dato tardio desplaza la entrada
# ---------------------------------------------------------------------------

def test_espera_desplaza_entrada_un_minuto():
    fin_c = T0
    fila = _fila_flujo("X", fin_c, as_of_extra=150)
    r = D.evaluar_espera(fila, "LONG", fin_c, fin_c)
    assert r["estado"] == "resoluble"
    assert r["cut_tardio_ms"] == fin_c + MIN + 150
    assert r["entrada_tardia_ms"] == fin_c + 2 * MIN
    assert r["desplazamiento_ms"] == MIN
    assert r["clasificacion"] == D.CONTINUACION


def test_espera_con_disponibilidad_muy_tardia_desplaza_dos_minutos():
    fin_c = T0
    fila = _fila_flujo("X", fin_c, as_of_extra=MIN + 500)
    r = D.evaluar_espera(fila, "LONG", fin_c, fin_c)
    assert r["estado"] == "resoluble"
    assert r["entrada_tardia_ms"] == fin_c + 3 * MIN
    assert r["desplazamiento_ms"] == 2 * MIN


def test_espera_no_desplaza_si_el_corte_ya_era_posterior():
    fin_c = T0
    cut = fin_c + MIN + 30_000
    fila = _fila_flujo("X", fin_c, as_of_extra=200)
    r = D.evaluar_espera(fila, "LONG", cut, fin_c)
    assert r["estado"] == "resoluble"
    assert r["cut_tardio_ms"] == cut
    assert r["entrada_tardia_ms"] == D._referencia_entrada(cut)
    assert r["desplazamiento_ms"] == 0


def test_minuto_de_espera_exige_alineacion():
    with pytest.raises(SystemExit):
        D.minuto_de_espera(T0 + 1)


# ---------------------------------------------------------------------------
# 2. Minuto faltante, incompleto o sin disponibilidad: no resoluble
# ---------------------------------------------------------------------------

def test_espera_ausente_no_resoluble():
    r = D.evaluar_espera(None, "LONG", T0, T0)
    assert r["estado"] == "no_resoluble"
    assert r["motivo"] == D.MOTIVO_ESPERA_AUSENTE
    assert r["entrada_tardia_ms"] is None


def test_espera_incompleta_no_resoluble():
    fila = _fila_flujo("X", T0, calidad="PARTIAL_OK")
    r = D.evaluar_espera(fila, "LONG", T0, T0)
    assert r["estado"] == "no_resoluble"
    assert r["motivo"] == D.MOTIVO_ESPERA_INCOMPLETO
    assert r["data_quality"] == "PARTIAL_OK"


def test_espera_sin_disponibilidad_no_resoluble():
    fila = _fila_flujo("X", T0)
    fila["as_of_ms"] = T0 + 100  # antes del cierre del minuto
    r = D.evaluar_espera(fila, "LONG", T0, T0)
    assert r["estado"] == "no_resoluble"
    assert r["motivo"] == D.MOTIVO_ESPERA_SIN_DISPONIBILIDAD
    assert r["flujo_disponible_antes_del_cierre"] is True


def test_espera_incoherente_no_resoluble():
    fila = _fila_flujo("X", T0)
    fila["bucket_end"] = T0 + 2 * MIN
    r = D.evaluar_espera(fila, "LONG", T0, T0)
    assert r["estado"] == "no_resoluble"
    assert r["motivo"] == D.MOTIVO_ESPERA_INCOHERENTE


# ---------------------------------------------------------------------------
# 3. Clasificacion del flujo
# ---------------------------------------------------------------------------

def test_clasificacion_flujo():
    assert D.clasificar_flujo(1.0) == D.CONTINUACION
    assert D.clasificar_flujo(-1.0) == D.REVERSION
    assert D.clasificar_flujo(0.0) == D.SIN_CONFIRMACION
    assert D.clasificar_flujo(1e-12) == D.SIN_CONFIRMACION


def test_flujo_alineado_depende_de_la_direccion():
    fila = _fila_flujo("X", T0, buy=20.0, sell=5.0)
    largo = D.evaluar_espera(fila, "LONG", T0, T0)
    corto = D.evaluar_espera(fila, "SHORT", T0, T0)
    assert largo["flujo_alineado"] == 15.0
    assert corto["flujo_alineado"] == -15.0
    assert largo["clasificacion"] == D.CONTINUACION
    assert corto["clasificacion"] == D.REVERSION


# ---------------------------------------------------------------------------
# 4. La reversion tardia no reutiliza la entrada original
# ---------------------------------------------------------------------------

def test_reversion_tardia_no_reutiliza_la_entrada_original():
    symbol = "X"
    fin_c = T0 - MIN
    cut = T0 - MIN + 200
    alerta = {"symbol": symbol, "direccion": "LONG", "cut_ms": cut}
    fila = _fila_flujo(symbol, fin_c, buy=20.0, sell=5.0, as_of_extra=200)
    espera = D.evaluar_espera(fila, "LONG", cut, fin_c)
    assert espera["entrada_tardia_ms"] == T0 + MIN

    velas = _velas(symbol, T0, {
        0: 100.0, 1: 110.0, 2: 108.0, 3: 107.0, 4: 106.0,
        5: 101.0, 6: 105.0,
    })
    r = D.resolver_tardia(alerta, espera, velas)
    assert r["estado"] == "resoluble"
    assert r["entrada_ms"] == T0 + MIN
    assert r["salida_ms"] == T0 + 6 * MIN
    # Entrada tardia 110, salida 105: continuacion LONG negativa.
    assert r["continuacion_bps"] == pytest.approx((105.0 / 110.0 - 1.0) * 1e4, abs=1e-4)
    assert r["reversion_bps"] == pytest.approx(-(105.0 / 110.0 - 1.0) * 1e4, abs=1e-4)
    # Si se hubiera reutilizado la entrada original (100), el retorno seria +500.
    assert r["continuacion_bps"] != pytest.approx(500.0, abs=1e-6)
    assert r["reutiliza_entrada_original"] is False
    assert r["misma_entrada_continuacion_y_reversion"] is True


def test_reversion_tardia_con_espera_no_resoluble():
    espera = D.evaluar_espera(None, "LONG", T0, T0)
    r = D.resolver_tardia({"symbol": "X", "direccion": "LONG", "cut_ms": T0},
                          espera, {})
    assert r["estado"] == "no_resoluble"
    assert r["motivo"] == D.MOTIVO_ESPERA_AUSENTE
    assert r["continuacion_bps"] is None


# ---------------------------------------------------------------------------
# 5. Extension previa: sin historia o con referencia cero, NO_RESOLUBLE
# ---------------------------------------------------------------------------

def _terna_previas(n_ventanas: int, precios, symbol="X", inicio=T0):
    return [_ventana(symbol, inicio + i * MIN, precios[i]) for i in range(n_ventanas)]


def test_extension_no_resoluble_sin_historia():
    ventanas = _terna_previas(8, [100, 101, 102, 103, 104, 105, 106, 107])
    terna = (ventanas[5], ventanas[6], ventanas[7])
    previas = D.ternas_previas_no_solapadas(ventanas[:5], terna[0].ventana_inicio_ms)
    assert len(previas) == 1  # 5 ventanas previas -> 1 terna no solapada
    r = D.extension_previa(terna, previas, "LONG")
    assert r["estado"] == "no_resoluble"
    assert r["motivo"] == "historia_insuficiente"
    assert r["ternas_previas_no_solapadas"] == 1


def test_extension_no_resoluble_referencia_cero():
    precios = [100.0] * 21
    ventanas = _terna_previas(21, precios)
    terna = (ventanas[18], ventanas[19], ventanas[20])
    previas = D.ternas_previas_no_solapadas(
        ventanas[:18], terna[0].ventana_inicio_ms)
    assert len(previas) == 6
    r = D.extension_previa(terna, previas, "LONG")
    assert r["estado"] == "no_resoluble"
    assert r["motivo"] == "referencia_cero"
    assert r["referencia_bps"] == 0.0


def test_extension_mediana_y_ternas_no_solapadas():
    # 21 ventanas: 18 previas -> 6 ternas de 3 en 3, sin compartir ventanas.
    precios = [100.0]
    for i in range(20):
        precios.append(precios[-1] * (1.0 + 0.001 * (i + 1)))
    ventanas = _terna_previas(21, precios)
    terna = (ventanas[18], ventanas[19], ventanas[20])
    previas = D.ternas_previas_no_solapadas(
        ventanas[:18], terna[0].ventana_inicio_ms)
    assert len(previas) == 6
    inicios = [int(t[0].ventana_inicio_ms) for t in previas]
    assert inicios == sorted(inicios)
    # Sin solapamiento: ninguna terna comparte ventana con la siguiente.
    for anterior, siguiente in zip(previas, previas[1:]):
        assert int(siguiente[0].ventana_inicio_ms) >= int(anterior[2].ventana_fin_ms)
    movimientos = sorted(
        abs((t[2].precio_cierre / t[0].precio_cierre - 1.0) * 1e4) for t in previas
    )
    esperado = (movimientos[2] + movimientos[3]) / 2.0
    r = D.extension_previa(terna, previas, "LONG")
    assert r["estado"] == "resoluble"
    assert r["referencia_bps"] == pytest.approx(round(esperado, 4), abs=1e-4)
    assert r["extension_normalizada"] == pytest.approx(
        r["avance_bruto_bps"] / r["referencia_bps"], abs=1e-3)


def test_extension_alineada_por_direccion():
    ventanas = _terna_previas(21, [100.0 + i for i in range(21)])
    terna = (ventanas[18], ventanas[19], ventanas[20])
    previas = D.ternas_previas_no_solapadas(
        ventanas[:18], terna[0].ventana_inicio_ms)
    largo = D.extension_previa(terna, previas, "LONG")
    corto = D.extension_previa(terna, previas, "SHORT")
    assert largo["avance_bruto_bps"] == pytest.approx(-corto["avance_bruto_bps"], abs=1e-9)


# ---------------------------------------------------------------------------
# 6. Denominadores de los controles
# ---------------------------------------------------------------------------

def _registro(orig, tard, clasificacion=D.CONTINUACION, rev=None):
    return {
        "symbol": "X",
        "direccion": "LONG",
        "original": {"estado": "resoluble" if orig is not None else "no_resoluble",
                     "retorno_bps": orig},
        "espera": {"estado": "resoluble", "clasificacion": clasificacion},
        "tardia": {"estado": "resoluble" if tard is not None else "no_resoluble",
                   "continuacion_bps": tard,
                   "reversion_bps": rev if rev is not None else (-tard if tard is not None else None)},
        "extension_previa": {"estado": "no_resoluble", "motivo": "historia_insuficiente"},
    }


def test_metricas_solo_cuentan_pares_resolubles():
    registros = [
        _registro(100.0, 50.0),
        _registro(-100.0, 20.0, clasificacion=D.REVERSION),
        _registro(None, 30.0),
        _registro(40.0, None),
    ]
    m = D._metricas(registros)
    assert m["anclas"] == 4
    assert m["original_resolubles"] == 3
    assert m["tardia_resolubles"] == 3
    assert m["pares_comparables"] == 2
    assert m["delta_media_bps"] == pytest.approx(35.0)
    assert m["delta_mediana_bps"] == pytest.approx(35.0)
    assert m["delta_positivo"] == 1
    assert m["delta_negativo"] == 1
    assert m["perdidas_evitadas"]["n_mejoran_siendo_negativas"] == 1
    assert m["perdidas_evitadas"]["de_esas_terminan_no_negativas"] == 1
    assert m["perdidas_evitadas"]["mejora_media_bps"] == pytest.approx(120.0)
    assert m["oportunidades_perdidas"]["n_empeoran_siendo_positivas"] == 1
    assert m["oportunidades_perdidas"]["empeora_media_bps"] == pytest.approx(-50.0)
    assert m["reversion"]["n"] == 1
    assert m["reversion"]["continuacion_media_bps"] == pytest.approx(20.0)
    assert m["reversion"]["reversion_media_bps"] == pytest.approx(-20.0)


def test_conclusion_exige_treinta_pares():
    m = D._metricas([_registro(10.0, 20.0)])
    c = D.concluir_espera(m, {"LONG": m, "SHORT": m})
    assert c["conclusion"] == "datos insuficientes"
    assert c["pares_comparables"] == 1


def test_conclusion_mejora_solo_si_media_y_mediana_son_positivas():
    registros = [_registro(0.0, 10.0), _registro(0.0, 20.0)]
    m = D._metricas(registros)
    m["pares_comparables"] = 30
    c = D.concluir_espera(m, {"LONG": m, "SHORT": m})
    assert c["conclusion"].startswith("esperar un minuto muestra mejora")
    registros = [_registro(0.0, 10.0), _registro(0.0, -20.0)]
    m = D._metricas(registros)
    m["pares_comparables"] = 30
    c = D.concluir_espera(m, {"LONG": m, "SHORT": m})
    assert c["conclusion"].startswith("esperar un minuto no muestra mejora")


# ---------------------------------------------------------------------------
# 7. Verificacion contra lo publicado
# ---------------------------------------------------------------------------

def _caso_minimo(terna="X|1", symbol="X", direccion="LONG", cut=1, estado="resoluble",
                 retorno=10.0):
    return {
        "terna": terna,
        "symbol": symbol,
        "direccion": direccion,
        "cut_ms": cut,
        "original": {"estado": estado, "retorno_bps": retorno},
    }


def test_verificar_casos_publicados_ok():
    casos = [_caso_minimo()]
    publicados = [{"terna": "X|1", "symbol": "X", "direccion": "LONG",
                   "cut_ms": 1, "estado": "resoluble", "retorno_bps": 10.0}]
    r = D.verificar_casos_publicados(casos, publicados)
    assert r["coinciden"] == 1


def test_verificar_casos_publicados_aborta_si_difiere():
    casos = [_caso_minimo(retorno=10.0)]
    publicados = [{"terna": "X|1", "symbol": "X", "direccion": "LONG",
                   "cut_ms": 1, "estado": "resoluble", "retorno_bps": 11.0}]
    with pytest.raises(SystemExit):
        D.verificar_casos_publicados(casos, publicados)


def test_verificar_casos_publicados_aborta_si_falta_un_caso():
    casos = [_caso_minimo()]
    with pytest.raises(SystemExit):
        D.verificar_casos_publicados(casos, [])


# ---------------------------------------------------------------------------
# 8. Diagnostico de los cuatro casos
# ---------------------------------------------------------------------------

def test_diagnostico_casos_cuenta_extension_presion_y_espera():
    def caso(symbol, clasificacion, estado_espera="resoluble", ext="resoluble",
             ratio=0.1, delta=5.0):
        return {
            "symbol": symbol,
            "direccion": "LONG",
            "terna": f"{symbol}|1",
            "original": {"retorno_bps": -100.0},
            "espera": {"estado": estado_espera, "clasificacion": clasificacion,
                       "motivo": None if estado_espera == "resoluble" else "flujo_espera_incompleto",
                       "ratio_fuerza_vs_tercera_ventana": ratio},
            "tardia": {"continuacion_bps": -50.0, "reversion_bps": 50.0},
            "delta_continuacion_bps": delta,
            "extension_previa": {
                "estado": ext,
                "motivo": None if ext == "resoluble" else "historia_insuficiente",
                "ternas_previas_no_solapadas": 6 if ext == "resoluble" else 2,
                "avance_bruto_bps": 100.0,
                "extension_normalizada": 2.0 if ext == "resoluble" else None,
            },
        }

    casos = [
        caso("A", D.CONTINUACION),
        caso("B", D.REVERSION),
        caso("C", D.CONTINUACION),
        caso("D", None, estado_espera="no_resoluble", ext="no_resoluble"),
    ]
    d = D.diagnostico_casos(casos)
    assert d["casos"] == 4
    assert d["extension_evaluable"] == 3
    assert d["extension_no_resoluble"] == 1
    assert d["presion_continuacion"] == 2
    assert d["presion_reversion"] == 1
    assert d["espera_no_resoluble"] == 1
    assert len(d["confirmados_con_menos_fuerza"]) == 2
    assert len(d["extension_insuficiente"]) == 1
