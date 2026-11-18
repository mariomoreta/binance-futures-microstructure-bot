# -*- coding: utf-8 -*-
"""Pruebas de la comparacion en condiciones iguales (patron vs solo precio).

Cubren lo exigido por el bloque:
  1. ambos metodos reciben EXACTAMENTE las mismas ternas y los mismos cortes;
  2. la referencia no incorpora ternas ajenas al universo recibido;
  3. una alerta tardia del patron NO cambia el ancla ni hereda su entrada;
  4. una vela faltante deja el episodio sin resolver, con motivo.

Ademas:
  5. un corte recalculado distinto del detector aborta (no se fuerza la cifra);
  6. la clasificacion "con patron" solo se marca si la terna cumple el patron;
  7. el minimo de 30 episodios resolubles se aplica igual que antes.

Sin red, sin Binance y sin datos reales: usa ventanas y velas sinteticas.
Ejecutar con: pytest tests/test_comparar_anclas_ventana4.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import comparar_anclas_ventana4 as C  # noqa: E402
from secuencia_presion_v1 import VentanaPresion, utc_iso  # noqa: E402

T0 = 1794857160000  # alineado a minuto
MIN = 60_000


def _ventana(
    symbol: str,
    inicio: int,
    precio: float,
    disponibilidad_extra: int = 0,
    buy: float = 10.0,
    sell: float = 3.0,
    bid: float = 100.0,
    ask: float = 100.0,
) -> VentanaPresion:
    fin = inicio + MIN
    disp = fin + disponibilidad_extra
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
    )


def _terna(symbol: str, inicio: int, precios, **kw):
    ventanas = [_ventana(symbol, inicio + i * MIN, p, **kw) for i, p in enumerate(precios)]
    return ventanas


def _fila(ventanas, decision="SIN_PATRON", direccion=None):
    a, b, c = ventanas
    corte = C.corte_de_terna(a, b, c)
    return {
        "symbol": a.symbol,
        "terna": f"{a.symbol}|{a.ventana_inicio_ms}",
        "ventanas": [v.ventana_inicio_ms for v in ventanas],
        "cierre_nominal_ms": c.ventana_fin_ms,
        "cut_ms": corte,
        "cut_iso": utc_iso(corte),
        "demora_corte_ms": corte - c.ventana_fin_ms,
        "decision": decision,
        "direccion": direccion,
    }


def _por_symbol(*grupos):
    salida = {}
    for ventanas in grupos:
        salida.setdefault(ventanas[0].symbol, []).extend(ventanas)
    for lista in salida.values():
        lista.sort(key=lambda v: v.ventana_inicio_ms)
    return salida


def _vela(open_px: float, low: float, high: float, final: bool = True, conflictiva: bool = False):
    return {
        "open": open_px,
        "low": low,
        "high": high,
        "final": final,
        "conflictiva": conflictiva,
    }


# ---------------------------------------------------------------------------
# 1-2. Mismo universo, mismo corte, sin ternas ajenas
# ---------------------------------------------------------------------------

def test_mismo_universo_y_mismo_corte_con_fuente_tardia():
    # LONG monotona con una fuente que llega 7 s despues del cierre nominal.
    larga = _terna("AAAUSDT", T0, [1.0, 1.1, 1.2], disponibilidad_extra=7000)
    # SHORT monotona normal.
    corta = _terna("BBBUSDT", T0, [3.0, 2.0, 1.0])
    # No monotona: no debe generar alerta.
    plana = _terna("CCCUSDT", T0, [1.0, 1.2, 1.1])

    filas = [_fila(larga), _fila(corta), _fila(plana)]
    alertas, audit = C.construir_alertas_referencia(filas, _por_symbol(larga, corta, plana))

    assert audit["ternas_recibidas"] == 3
    assert audit["cortes_verificados"] == 3
    assert audit["ternas_no_monotonas"] == 1
    assert len(alertas) == 2
    por_terna = {a["terna"]: a for a in alertas}
    assert por_terna[filas[0]["terna"]]["direccion"] == "LONG"
    assert por_terna[filas[1]["terna"]]["direccion"] == "SHORT"
    # El corte es el mismo en ambos metodos, e incluye la disponibilidad tardia.
    assert por_terna[filas[0]["terna"]]["cut_ms"] == filas[0]["cut_ms"]
    assert por_terna[filas[0]["terna"]]["cut_ms"] == larga[2].ventana_fin_ms + 7000
    assert por_terna[filas[1]["terna"]]["cut_ms"] == filas[1]["cut_ms"]
    # La entrada de referencia es el primer minuto estrictamente posterior al
    # corte, no al cierre nominal: con la fuente tardia cae un minuto despues.
    entrada = (filas[0]["cut_ms"] // MIN + 1) * MIN
    assert entrada == larga[2].ventana_fin_ms + MIN
    velas = {"AAAUSDT": {
        entrada: _vela(1.0, 0.9, 1.1),
        entrada + 5 * MIN: _vela(1.3, 1.1, 1.4),
    }}
    r = C.resolver_alerta(por_terna[filas[0]["terna"]], velas)
    assert r["estado"] == "resoluble"
    assert r["entrada_ms"] == entrada


def test_no_incorpora_ternas_ajenas_al_universo():
    dentro = _terna("AAAUSDT", T0, [1.0, 1.1, 1.2])
    fuera = _terna("ZZZUSDT", T0, [5.0, 4.0, 3.0])
    filas = [_fila(dentro)]
    alertas, audit = C.construir_alertas_referencia(
        filas, _por_symbol(dentro, fuera))
    assert audit["ternas_recibidas"] == 1
    assert len(alertas) == 1
    assert alertas[0]["symbol"] == "AAAUSDT"
    assert all(a["symbol"] != "ZZZUSDT" for a in alertas)


def test_corte_recalculado_distinto_aborta():
    ventanas = _terna("AAAUSDT", T0, [1.0, 1.1, 1.2])
    fila = _fila(ventanas)
    fila["cut_ms"] = fila["cut_ms"] + 1
    with pytest.raises(SystemExit, match="corte distinto"):
        C.construir_alertas_referencia([fila], _por_symbol(ventanas))


def test_clasificacion_patron_exige_cumplir_el_patron():
    # Cierres monotonos pero Q no creciente: la fila dice LONG_EXPERIMENTAL.
    ventanas = _terna("AAAUSDT", T0, [1.0, 1.1, 1.2], buy=10.0, ask=100.0)
    fila = _fila(ventanas, decision="LONG_EXPERIMENTAL", direccion="LONG")
    with pytest.raises(SystemExit, match="clasificacion de patron incoherente"):
        C.construir_alertas_referencia([fila], _por_symbol(ventanas))


def test_patron_real_se_marca_en_el_mismo_instante():
    # Cierres crecientes y Q creciente con profundidad contraria decreciente.
    v1 = _ventana("AAAUSDT", T0, 1.0, buy=10.0, sell=0.0, ask=100.0, bid=100.0)
    v2 = _ventana("AAAUSDT", T0 + MIN, 1.1, buy=20.0, sell=0.0, ask=90.0, bid=100.0)
    v3 = _ventana("AAAUSDT", T0 + 2 * MIN, 1.2, buy=30.0, sell=0.0, ask=80.0, bid=100.0)
    fila = _fila([v1, v2, v3], decision="LONG_EXPERIMENTAL", direccion="LONG")
    alertas, audit = C.construir_alertas_referencia(
        [fila], _por_symbol([v1, v2, v3]))
    assert audit["alertas_con_patron"] == 1
    assert alertas[0]["tambien_patron"] is True
    assert alertas[0]["decision"] == "LONG_EXPERIMENTAL"


# ---------------------------------------------------------------------------
# 3. Alerta tardia: no cambia el ancla ni hereda su entrada
# ---------------------------------------------------------------------------

def test_alerta_tardia_no_cambia_ancla_ni_hereda_entrada():
    ancla = {
        "symbol": "AAAUSDT", "direccion": "LONG", "terna": "AAAUSDT|1000",
        "cut_ms": T0 + 5000, "cut_iso": utc_iso(T0 + 5000),
        "cierre_nominal_ms": T0, "demora_corte_ms": 5000,
        "decision": "SIN_PATRON", "tambien_patron": False,
    }
    tardia = {
        "symbol": "AAAUSDT", "direccion": "LONG", "terna": "AAAUSDT|2000",
        "cut_ms": T0 + 65_000, "cut_iso": utc_iso(T0 + 65_000),
        "cierre_nominal_ms": T0 + MIN, "demora_corte_ms": 5000,
        "decision": "LONG_EXPERIMENTAL", "tambien_patron": True,
    }
    episodios, audit = C.agrupar_con_tardias([ancla, tardia], [tardia])

    assert len(episodios) == 1
    ep = episodios[0]
    assert ep["terna"] == ancla["terna"]
    assert ep["cut_ms"] == ancla["cut_ms"]
    assert ep["ancla_patron"] is False
    assert [t["terna"] for t in ep["tardias"]] == [tardia["terna"]]
    assert audit["anclas_con_patron"] == 0
    assert audit["alertas_tardias"] == 1

    entrada_ancla = (ancla["cut_ms"] // MIN + 1) * MIN
    velas = {
        "AAAUSDT": {
            entrada_ancla: _vela(1.0, 0.9, 1.05),
            entrada_ancla + 5 * MIN: _vela(1.2, 1.1, 1.3),
        }
    }
    r = C.resolver_alerta(ep, velas)
    assert r["estado"] == "resoluble"
    # Si se hubiera usado la alerta tardia (entrada un minuto despues) el
    # resultado no seria resoluble con estas velas: el ancla manda.
    assert r["entrada_ms"] == entrada_ancla
    assert r["retorno_bps"] == pytest.approx(2000.0)


# ---------------------------------------------------------------------------
# 4. Vela faltante: no resoluble con motivo
# ---------------------------------------------------------------------------

def test_vela_faltante_no_resoluble_con_motivo():
    alerta = {
        "symbol": "AAAUSDT", "direccion": "LONG", "terna": "AAAUSDT|1000",
        "cut_ms": T0, "cut_iso": utc_iso(T0),
    }
    entrada = (T0 // MIN + 1) * MIN
    sin_salida = {"AAAUSDT": {entrada: _vela(1.0, 0.9, 1.1)}}
    r = C.resolver_alerta(alerta, sin_salida)
    assert r["estado"] == "no_resoluble"
    assert r["motivo"] == "vela_salida_ausente"

    r2 = C.resolver_alerta(alerta, {"OTROUSDT": {}})
    assert r2["estado"] == "no_resoluble"
    assert r2["motivo"] == "sin_velas_para_simbolo"

    contradictoria = {
        "AAAUSDT": {
            entrada: _vela(1.0, 0.9, 1.1, conflictiva=True),
            entrada + 5 * MIN: _vela(1.2, 1.1, 1.3),
        }
    }
    r3 = C.resolver_alerta(alerta, contradictoria)
    assert r3["estado"] == "no_resoluble"
    assert r3["motivo"] == "vela_contradictoria"


# ---------------------------------------------------------------------------
# 5. Regla de conclusion intacta
# ---------------------------------------------------------------------------

def _grupo(n: int, media: float, mediana: float, dominante: str = "AAAUSDT"):
    return {
        "resolubles": n,
        "retorno_medio_bps": media,
        "retorno_mediano_bps": mediana,
        "simbolo_dominante": {"symbol": dominante},
    }


def test_minimo_de_30_se_aplica():
    detalle = [
        {"estado": "resoluble", "symbol": "BBBUSDT", "retorno_bps": 20.0}
        for _ in range(30)
    ]
    r = C.concluir_anclas(
        _grupo(4, -88.37, -120.53),
        _grupo(30, -5.0, 2.0),
        detalle,
        {"episodios": 143, "anclas_con_patron": 4},
    )
    assert r["conclusion"] == "datos insuficientes"
    assert r["minimo_episodios_resolubles"] == 30

    r2 = C.concluir_anclas(
        _grupo(35, 10.0, 8.0),
        _grupo(40, -5.0, -2.0),
        detalle,
        {"episodios": 143, "anclas_con_patron": 35},
    )
    assert r2["conclusion"] == "merece una prueba independiente"


def test_reduccion_de_oportunidades():
    r = C._reduccion(ternas=501, alertas=211, episodios=143, con_patron=4)
    assert r["episodios_descartados_por_el_filtro"] == 139
    assert r["tasa_retencion_del_filtro"] == pytest.approx(0.028)
    assert r["tasa_alerta_por_terna"] == pytest.approx(0.4212)
