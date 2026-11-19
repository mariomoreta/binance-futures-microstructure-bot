# -*- coding: utf-8 -*-
"""Pruebas del diagnostico de factores (ventana 4, offline).

Cubren lo exigido por el bloque:
  1. el avance normalizado por la historia propia no se inventa: sin tramo
     contiguo, con menos de 6 bloques o con referencia cero queda UNKNOWN;
  2. los bloques de 3 ventanas previos no se solapan;
  3. la descomposicion de Q reparte el crecimiento entre importe y profundidad
     y suma 100;
  4. el impacto marginal detecta frenada y aceleracion, y no divide por cero;
  5. los ultimos 30 s y la concentracion de 10 s quedan UNKNOWN si falta un
     bucket;
  6. el primer cambio posterior usa bloques alineados al reloj, salta bloques
     no utilizables con motivo y distingue giro, debilitamiento, precio sin
     avance y profundidad que deja de caer;
  7. un dato tardio desplaza la entrada del cambio; un minuto ausente no se
     rellena;
  8. la reversion solo se mide si el cambio es un giro y nunca reutiliza la
     entrada original (el modulo aborta si se intenta);
  9. la regla formal de conclusion exige 30 pares y media y mediana positivas.

Sin red, sin Binance y sin datos reales: ventanas, filas y velas sinteticas.
Ejecutar con: pytest tests/test_diagnostico_factores_ventana4.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import diagnostico_factores_ventana4 as D  # noqa: E402
from secuencia_presion_v1 import VentanaPresion, utc_iso  # noqa: E402

T0 = 1794857160000
MIN = 60_000
S = 10_000


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
    precio: float = 100.0,
):
    return {
        "symbol": symbol,
        "bucket_start": inicio,
        "bucket_end": inicio + MIN,
        "bucket_size_s": 60,
        "buy_notional": buy,
        "sell_notional": sell,
        "price_open": precio,
        "price_high": precio,
        "price_low": precio,
        "price_close": precio,
        "as_of_ms": inicio + MIN + as_of_extra,
        "data_quality": calidad,
        "last_event_ms": inicio + MIN - 10,
        "run_id": "r",
    }


def _fila_libro(
    symbol: str,
    inicio: int,
    bid: float = 100.0,
    ask: float = 100.0,
    as_of_extra: int = 200,
    degraded: int = 0,
    depth_gaps: int = 0,
    crossed: int = 0,
):
    return {
        "symbol": symbol,
        "bucket_start": inicio,
        "bucket_end": inicio + MIN,
        "bid20_mean": bid,
        "ask20_mean": ask,
        "degraded": degraded,
        "depth_gaps": depth_gaps,
        "crossed": crossed,
        "as_of_ms": inicio + MIN + as_of_extra,
        "run_id": "r",
    }


def _bucket_10s(
    symbol: str,
    inicio: int,
    buy: float,
    sell: float,
    precio_open: float,
    precio_close: float,
    as_of_extra: int = 120,
    calidad: str = "OK",
):
    return {
        "symbol": symbol,
        "bucket_start": inicio,
        "bucket_end": inicio + S,
        "buy_notional": buy,
        "sell_notional": sell,
        "price_open": precio_open,
        "price_close": precio_close,
        "as_of_ms": inicio + S + as_of_extra,
        "data_quality": calidad,
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
# 1. Avance normalizado por la historia propia
# ---------------------------------------------------------------------------

def test_bloques_3m_no_se_solapan_y_terminan_en_t0():
    symbol = "X"
    filas = {}
    for i in range(7):
        t = T0 - (i + 1) * MIN
        filas[(symbol, t)] = _fila_flujo(symbol, t)
    run, bloques = D.bloques_3m_previos(filas, symbol, T0)
    assert len(run) == 7
    assert len(bloques) == 2
    assert bloques[-1][-1]["bucket_start"] == T0 - MIN
    assert bloques[0][-1]["bucket_start"] < bloques[1][0]["bucket_start"]
    for b in bloques:
        assert b[2]["bucket_start"] - b[0]["bucket_start"] == 2 * MIN


def test_avance_vs_3m_insuficiente():
    symbol = "X"
    filas = {(symbol, T0 - (i + 1) * MIN): _fila_flujo(symbol, T0 - (i + 1) * MIN)
             for i in range(5)}
    r = D.avance_vs_3m_flujo(filas, symbol, T0, 30.0)
    assert r["estado"] == D.ESTADO_UNKNOWN
    assert r["motivo"] == D.MOTIVO_HISTORIA_INSUFICIENTE
    assert r["bloques_disponibles"] == 1


def test_avance_vs_3m_hueco_no_se_rellena():
    symbol = "X"
    filas = {(symbol, T0 - (i + 1) * MIN): _fila_flujo(symbol, T0 - (i + 1) * MIN)
             for i in range(20) if i != 0}
    r = D.avance_vs_3m_flujo(filas, symbol, T0, 30.0)
    assert r["estado"] == D.ESTADO_UNKNOWN
    assert r["bloques_disponibles"] == 0
    assert r["minutos_previos_contiguos"] == 0


def test_avance_vs_3m_ratio():
    symbol = "X"
    filas = {}
    # 18 minutos con +5 bps por minuto: cada bloque de 3 ventanas mueve ~10 bps
    # del primer al tercer cierre.
    for j in range(18):
        t = T0 - (18 - j) * MIN
        precio = 100.0 * (1.0005 ** j)
        filas[(symbol, t)] = _fila_flujo(symbol, t, precio=precio)
    r = D.avance_vs_3m_flujo(filas, symbol, T0, 30.0)
    assert r["estado"] == D.ESTADO_RESOLUBLE
    assert r["bloques_disponibles"] == 6
    assert r["referencia_bps"] == pytest.approx(10.0, abs=0.01)
    assert r["extension_normalizada"] == pytest.approx(3.0, abs=0.01)


def test_avance_vs_3m_referencia_cero():
    symbol = "X"
    filas = {(symbol, T0 - (i + 1) * MIN): _fila_flujo(symbol, T0 - (i + 1) * MIN,
                                                       precio=100.0)
             for i in range(18)}
    r = D.avance_vs_3m_flujo(filas, symbol, T0, 30.0)
    assert r["estado"] == D.ESTADO_UNKNOWN
    assert r["motivo"] == D.MOTIVO_REFERENCIA_CERO


# ---------------------------------------------------------------------------
# 2. Descomposicion de Q
# ---------------------------------------------------------------------------

def test_descomposicion_q_importe_domina():
    a = _ventana("X", T0, 100.0, buy=1000.0, sell=0.0, ask=100.0)
    c = _ventana("X", T0 + 2 * MIN, 100.0, buy=2000.0, sell=0.0, ask=100.0)
    r = D.descomponer_q(a, a, c, "LONG")
    assert r["estado"] == D.ESTADO_RESOLUBLE
    assert r["aporte_importe_pct"] == pytest.approx(100.0, abs=1e-6)
    assert r["aporte_profundidad_pct"] == pytest.approx(0.0, abs=1e-6)
    assert r["profundidad_cae_pct"] == pytest.approx(0.0, abs=1e-6)


def test_descomposicion_q_profundidad_domina():
    a = _ventana("X", T0, 100.0, buy=1000.0, sell=0.0, ask=100.0)
    c = _ventana("X", T0 + 2 * MIN, 100.0, buy=1000.0, sell=0.0, ask=50.0)
    r = D.descomponer_q(a, a, c, "LONG")
    assert r["estado"] == D.ESTADO_RESOLUBLE
    assert r["aporte_importe_pct"] == pytest.approx(0.0, abs=1e-6)
    assert r["aporte_profundidad_pct"] == pytest.approx(100.0, abs=1e-6)
    assert r["profundidad_cae_pct"] == pytest.approx(-50.0, abs=1e-6)


def test_descomposicion_q_suma_100():
    a = _ventana("X", T0, 100.0, buy=1000.0, sell=0.0, ask=100.0)
    c = _ventana("X", T0 + 2 * MIN, 100.0, buy=3000.0, sell=0.0, ask=80.0)
    r = D.descomponer_q(a, a, c, "LONG")
    assert r["aporte_importe_pct"] + r["aporte_profundidad_pct"] == pytest.approx(
        100.0, abs=1e-6)
    assert r["importe_crece"] is True
    assert r["profundidad_cae_pct"] == pytest.approx(-20.0, abs=1e-6)


def test_descomposicion_q_presion_no_positiva():
    a = _ventana("X", T0, 100.0, buy=0.0, sell=1000.0, ask=100.0)
    c = _ventana("X", T0 + 2 * MIN, 100.0, buy=1000.0, sell=0.0, ask=100.0)
    r = D.descomponer_q(a, a, c, "LONG")
    assert r["estado"] == D.ESTADO_UNKNOWN
    assert r["motivo"] == D.MOTIVO_PRESION_NO_POSITIVA


# ---------------------------------------------------------------------------
# 3. Impacto marginal
# ---------------------------------------------------------------------------

def test_impacto_frenada():
    a = _ventana("X", T0, 100.0, buy=1000.0, sell=0.0)
    b = _ventana("X", T0 + MIN, 101.0, buy=1000.0, sell=0.0)
    c = _ventana("X", T0 + 2 * MIN, 101.5, buy=2000.0, sell=0.0)
    r = D.impacto_por_tramo(a, b, c, "LONG")
    assert r["estado"] == D.ESTADO_RESOLUBLE
    assert r["impacto_relativo"] < 1.0
    assert r["frenada_impacto"] is True
    assert r["frenada_avance"] is True


def test_impacto_aceleracion():
    a = _ventana("X", T0, 100.0, buy=1000.0, sell=0.0)
    b = _ventana("X", T0 + MIN, 100.1, buy=1000.0, sell=0.0)
    c = _ventana("X", T0 + 2 * MIN, 101.0, buy=2000.0, sell=0.0)
    r = D.impacto_por_tramo(a, b, c, "LONG")
    assert r["estado"] == D.ESTADO_RESOLUBLE
    assert r["impacto_relativo"] > 1.0
    assert r["frenada_impacto"] is False
    assert r["frenada_avance"] is False


def test_impacto_2_no_positivo():
    a = _ventana("X", T0, 101.0, buy=1000.0, sell=0.0)
    b = _ventana("X", T0 + MIN, 100.0, buy=1000.0, sell=0.0)
    c = _ventana("X", T0 + 2 * MIN, 101.0, buy=2000.0, sell=0.0)
    r = D.impacto_por_tramo(a, b, c, "LONG")
    assert r["estado"] == D.ESTADO_UNKNOWN
    assert r["motivo"] == D.MOTIVO_IMPACTO_2_NO_POSITIVO


# ---------------------------------------------------------------------------
# 4. Ultimos 30 s y concentracion de 10 s
# ---------------------------------------------------------------------------

def test_ultimos_30s_completo_y_giro():
    symbol = "X"
    fin_c = T0
    filas = {
        (symbol, fin_c - 30 * 1000): _bucket_10s(symbol, fin_c - 30 * 1000,
                                                 1.0, 10.0, 100.0, 99.9),
        (symbol, fin_c - 20 * 1000): _bucket_10s(symbol, fin_c - 20 * 1000,
                                                 1.0, 10.0, 99.9, 99.8),
        (symbol, fin_c - 10 * 1000): _bucket_10s(symbol, fin_c - 10 * 1000,
                                                 1.0, 10.0, 99.8, 99.7),
    }
    r = D.ultimos_30s(filas, symbol, fin_c, "LONG")
    assert r["estado"] == D.ESTADO_RESOLUBLE
    assert r["flujo_alineado_30s"] == pytest.approx(-27.0, abs=1e-9)
    assert r["giro_30s"] is True
    assert r["presion_sin_avance_30s"] is False
    assert r["delta_precio_30s_bps"] == pytest.approx(-30.0, abs=1e-6)


def test_ultimos_30s_faltante_es_unknown():
    symbol = "X"
    fin_c = T0
    filas = {
        (symbol, fin_c - 30 * 1000): _bucket_10s(symbol, fin_c - 30 * 1000,
                                                 1.0, 10.0, 100.0, 99.9),
        (symbol, fin_c - 10 * 1000): _bucket_10s(symbol, fin_c - 10 * 1000,
                                                 1.0, 10.0, 99.8, 99.7),
    }
    r = D.ultimos_30s(filas, symbol, fin_c, "LONG")
    assert r["estado"] == D.ESTADO_UNKNOWN
    assert r["motivo"] == D.MOTIVO_BUCKETS_10S
    assert len(r["buckets_faltantes"]) == 1


def test_ultimos_30s_as_of_antes_del_cierre_no_sirve():
    symbol = "X"
    fin_c = T0
    filas = {
        (symbol, fin_c - 30 * 1000): _bucket_10s(symbol, fin_c - 30 * 1000,
                                                 1.0, 10.0, 100.0, 99.9,
                                                 as_of_extra=-500),
        (symbol, fin_c - 20 * 1000): _bucket_10s(symbol, fin_c - 20 * 1000,
                                                 1.0, 10.0, 99.9, 99.8),
        (symbol, fin_c - 10 * 1000): _bucket_10s(symbol, fin_c - 10 * 1000,
                                                 1.0, 10.0, 99.8, 99.7),
    }
    r = D.ultimos_30s(filas, symbol, fin_c, "LONG")
    assert r["estado"] == D.ESTADO_UNKNOWN
    assert r["buckets_faltantes"][0]["motivo"] == "bucket_10s_sin_disponibilidad"


def test_concentracion_10s():
    symbol = "X"
    fin_c = T0
    deltas = [1.0, 1.0, 1.0, 1.0, 1.0, 10.0]
    filas = {}
    for i, delta in enumerate(deltas):
        t = fin_c - MIN + i * S
        buy = 10.0 + delta if delta > 0 else 10.0
        sell = 10.0 if delta > 0 else 10.0 - delta
        filas[(symbol, t)] = _bucket_10s(symbol, t, buy, sell, 100.0, 100.0)
    r = D.concentracion_10s(filas, symbol, fin_c)
    assert r["estado"] == D.ESTADO_RESOLUBLE
    assert r["concentracion"] == pytest.approx(10.0 / 15.0, abs=1e-4)
    assert r["bucket_dominante_ms"] == fin_c - 10 * 1000


def test_concentracion_10s_faltante():
    symbol = "X"
    fin_c = T0
    filas = {(symbol, fin_c - MIN + i * S): _bucket_10s(
        symbol, fin_c - MIN + i * S, 11.0, 10.0, 100.0, 100.0) for i in range(5)}
    r = D.concentracion_10s(filas, symbol, fin_c)
    assert r["estado"] == D.ESTADO_UNKNOWN
    assert r["motivo"] == D.MOTIVO_BUCKETS_10S


# ---------------------------------------------------------------------------
# 5. Primer cambio posterior
# ---------------------------------------------------------------------------

def _terna_short(d3=100.0, f1=10.0, f3=300.0):
    a = _ventana("X", T0, 100.0, buy=0.0, sell=f1, bid=d3)
    b = _ventana("X", T0 + MIN, 99.9, buy=0.0, sell=100.0, bid=d3)
    c = _ventana("X", T0 + 2 * MIN, 99.8, buy=0.0, sell=f3, bid=d3)
    return a, b, c


def _escenario_post(symbol="X", flujos=None, libros=None, precios=None,
                    cut=T0 + 2 * MIN + 1_355):
    flujos = flujos or {}
    libros = libros or {}
    precios = precios or {}
    f = {}
    for k, (buy, sell) in flujos.items():
        t = (cut // MIN) * MIN + k * MIN
        f[(symbol, t)] = _fila_flujo(symbol, t, buy=buy, sell=sell,
                                     precio=precios.get(k, 100.0))
    l = {}
    for k, (bid, ask) in libros.items():
        t = (cut // MIN) * MIN + k * MIN
        l[(symbol, t)] = _fila_libro(symbol, t, bid=bid, ask=ask)
    return f, l


def test_bloque_b0_es_el_minuto_del_corte():
    a, b, c = _terna_short()
    f, l = _escenario_post(flujos={0: (100.0, 0.0)})
    r = D.analizar_bloques(f, l, "X", T0 + 2 * MIN + 1_355, "SHORT", c)
    assert r["bloques"][0]["inicio_ms"] == T0 + 2 * MIN
    assert r["bloques"][1]["inicio_ms"] == T0 + 3 * MIN


def test_bloque_incompleto_se_salta_con_motivo():
    a, b, c = _terna_short()
    f, l = _escenario_post(flujos={0: (100.0, 0.0), 1: (0.0, 0.0)})
    f[("X", T0 + 2 * MIN)]["data_quality"] = "PARTIAL_OK"
    r = D.analizar_bloques(f, l, "X", T0 + 2 * MIN + 1_355, "SHORT", c)
    cambio = r["primer_cambio"]
    assert cambio["estado"] == D.ESTADO_CAMBIO
    assert cambio["k"] == 1
    assert cambio["tipos"] == ["giro"]
    assert cambio["bloques_no_usables_antes"][0]["motivo"] == D.MOTIVO_FLUJO_INCOMPLETO


def test_bloque_debilitamiento():
    a, b, c = _terna_short(f3=300.0)
    # SHORT: vende mas de lo que compra -> flujo alineado positivo pero menor
    # que el de la tercera ventana.
    f, l = _escenario_post(flujos={0: (0.0, 50.0)}, precios={0: 99.5})
    r = D.analizar_bloques(f, l, "X", T0 + 2 * MIN + 1_355, "SHORT", c)
    cambio = r["primer_cambio"]
    assert cambio["estado"] == D.ESTADO_CAMBIO
    assert cambio["tipos"] == ["debilitamiento"]


def test_bloque_precio_sin_avance():
    a, b, c = _terna_short(f3=300.0)
    # SHORT: flujo alineado positivo (vende) pero el precio sube (delta < 0).
    f, l = _escenario_post(flujos={0: (0.0, 50.0)}, precios={0: 100.5})
    r = D.analizar_bloques(f, l, "X", T0 + 2 * MIN + 1_355, "SHORT", c)
    cambio = r["primer_cambio"]
    assert cambio["estado"] == D.ESTADO_CAMBIO
    assert "precio_sin_avance" in cambio["tipos"]
    assert "debilitamiento" in cambio["tipos"]


def test_bloque_profundidad_deja_de_caer():
    a, b, c = _terna_short(d3=100.0, f1=10.0, f3=300.0)
    f, l = _escenario_post(flujos={0: (0.0, 500.0)}, libros={0: (150.0, 100.0)})
    # flujo alineado = -(buy-sell) = 500 > 0, igual que la tercera ventana.
    c.buy_notional = 0.0
    c.sell_notional = 500.0
    r = D.analizar_bloques(f, l, "X", T0 + 2 * MIN + 1_355, "SHORT", c)
    cambio = r["primer_cambio"]
    assert cambio["estado"] == D.ESTADO_CAMBIO
    assert "profundidad_deja_de_caer" in cambio["tipos"]


def test_sin_cambio_en_horizonte():
    a, b, c = _terna_short(f3=300.0)
    # SHORT: vende mas que la tercera ventana y el precio sigue cayendo.
    f, l = _escenario_post(flujos={k: (0.0, 500.0) for k in range(6)},
                           precios={k: 99.0 - 0.1 * k for k in range(6)})
    r = D.analizar_bloques(f, l, "X", T0 + 2 * MIN + 1_355, "SHORT", c)
    assert r["primer_cambio"]["estado"] == D.ESTADO_SIN_CAMBIO
    assert r["primer_cambio"]["bloques_utiles"] == 6


def test_sin_bloques_utiles_es_unknown():
    a, b, c = _terna_short()
    r = D.analizar_bloques({}, {}, "X", T0 + 2 * MIN + 1_355, "SHORT", c)
    assert r["primer_cambio"]["estado"] == D.ESTADO_UNKNOWN
    assert r["primer_cambio"]["motivo"] == D.MOTIVO_SIN_CAMBIO
    assert r["bloques_utiles"] == 0


def test_detalle_10s_marca_buckets_faltantes():
    symbol = "X"
    inicio = T0
    filas = {(symbol, inicio + i * S): _bucket_10s(symbol, inicio + i * S,
                                                  11.0, 10.0, 100.0, 100.0)
             for i in range(6) if i != 3}
    detalle = D.detalle_10s_bloque(filas, symbol, inicio)
    assert len(detalle) == 6
    assert detalle[3]["estado"] == D.ESTADO_UNKNOWN
    assert detalle[0]["estado"] == D.ESTADO_RESOLUBLE


# ---------------------------------------------------------------------------
# 6. Resolucion del cambio: entrada posterior y reversion
# ---------------------------------------------------------------------------

def _cambio(disponibilidad, es_giro=True):
    return {
        "estado": D.ESTADO_CAMBIO,
        "motivo": None,
        "tipo": "giro" if es_giro else "debilitamiento",
        "k": 0,
        "inicio_ms": disponibilidad - MIN,
        "fin_ms": disponibilidad,
        "disponibilidad_ms": disponibilidad,
        "es_giro": es_giro,
    }


def test_cambio_desplaza_entrada_un_minuto():
    episodio = {"symbol": "X", "direccion": "LONG", "cut_ms": T0 + 1_355}
    velas = _velas("X", T0 + 2 * MIN, {0: 100.0, 5: 101.0})
    r = D.resolver_cambio(episodio, _cambio(T0 + MIN + 150), velas)
    assert r["estado"] == "resoluble"
    assert r["entrada_ms"] == T0 + 2 * MIN
    assert r["reutiliza_entrada_original"] is False


def test_cambio_con_disponibilidad_muy_tardia_desplaza_dos_minutos():
    episodio = {"symbol": "X", "direccion": "LONG", "cut_ms": T0 + 1_355}
    velas = _velas("X", T0 + 3 * MIN, {0: 100.0, 5: 101.0})
    r = D.resolver_cambio(episodio, _cambio(T0 + 2 * MIN + 500), velas)
    assert r["entrada_ms"] == T0 + 3 * MIN


def test_cambio_reutilizando_entrada_original_aborta():
    episodio = {"symbol": "X", "direccion": "LONG", "cut_ms": T0 + 1_355}
    velas = _velas("X", T0 + MIN, {0: 100.0, 5: 101.0})
    with pytest.raises(SystemExit):
        D.resolver_cambio(episodio, _cambio(T0 + 30_000), velas)


def test_cambio_sin_velas_no_resoluble_pero_con_entrada():
    episodio = {"symbol": "X", "direccion": "LONG", "cut_ms": T0 + 1_355}
    r = D.resolver_cambio(episodio, _cambio(T0 + MIN + 150), {})
    assert r["estado"] == "no_resoluble"
    assert r["entrada_ms"] == T0 + 2 * MIN


def test_reversion_solo_si_es_giro():
    episodio = {"symbol": "X", "direccion": "LONG", "cut_ms": T0 + 1_355}
    velas = _velas("X", T0 + 2 * MIN, {0: 100.0, 5: 99.0})
    r = D.resolver_cambio(episodio, _cambio(T0 + MIN + 150, es_giro=False), velas)
    assert r["continuacion_bps"] == pytest.approx(-100.0, abs=1e-6)
    assert r["reversion_bps"] is None
    assert r["reversion_motivo"] == D.MOTIVO_NO_APLICA
    r2 = D.resolver_cambio(episodio, _cambio(T0 + MIN + 150, es_giro=True), velas)
    assert r2["reversion_bps"] == pytest.approx(100.0, abs=1e-6)


def test_cambio_sin_evento_es_unknown():
    episodio = {"symbol": "X", "direccion": "LONG", "cut_ms": T0 + 1_355}
    r = D.resolver_cambio(episodio, {"estado": D.ESTADO_SIN_CAMBIO,
                                     "motivo": None}, {})
    assert r["estado"] == D.ESTADO_UNKNOWN
    assert r["motivo"] == D.MOTIVO_SIN_CAMBIO


# ---------------------------------------------------------------------------
# 7. Regla formal de conclusion
# ---------------------------------------------------------------------------

def _registro(original, continuacion, reversion=None, direccion="LONG"):
    return {
        "direccion": direccion,
        "original": {"estado": "resoluble", "retorno_bps": original},
        "post": {
            "resultado": {
                "estado": "resoluble",
                "continuacion_bps": continuacion,
                "reversion_bps": reversion,
            },
            "resultado_giro": {
                "estado": "resoluble",
                "continuacion_bps": continuacion,
                "reversion_bps": reversion,
            },
        },
    }


def test_conclusion_giro_datos_insuficientes():
    registros = [_registro(0.0, 0.0, 10.0) for _ in range(29)]
    r = D.concluir_giro(registros, {})
    assert r["conclusion"] == "datos insuficientes"


def test_conclusion_giro_positiva():
    registros = [_registro(0.0, -10.0, 10.0) for _ in range(30)]
    r = D.concluir_giro(registros, {})
    assert r["conclusion"] == "el giro muestra reversion en esta muestra"


def test_conclusion_giro_negativa():
    registros = [_registro(0.0, 10.0, -10.0) for _ in range(30)]
    r = D.concluir_giro(registros, {})
    assert r["conclusion"] == "el giro no muestra reversion en esta muestra"


def test_conclusion_cambio_mejora():
    registros = [_registro(-50.0, 0.0, None) for _ in range(30)]
    r = D.concluir_cambio(registros, {})
    assert r["conclusion"] == "el primer cambio muestra mejora en esta muestra"


def test_conclusion_cambio_no_mejora():
    registros = [_registro(50.0, 0.0, None) for _ in range(30)]
    r = D.concluir_cambio(registros, {})
    assert r["conclusion"] == "el primer cambio no muestra mejora en esta muestra"


# ---------------------------------------------------------------------------
# 8. Disponibilidad de filas
# ---------------------------------------------------------------------------

def test_fila_flujo_disponibilidad():
    f = _fila_flujo("X", T0, as_of_extra=-1)
    ok, motivo = D._fila_flujo_util(f)
    assert not ok and motivo == D.MOTIVO_FLUJO_SIN_DISPONIBILIDAD
    f = _fila_flujo("X", T0, calidad="PARTIAL_OK")
    ok, motivo = D._fila_flujo_util(f)
    assert not ok and motivo == D.MOTIVO_FLUJO_INCOMPLETO
    ok, motivo = D._fila_flujo_util(None)
    assert not ok and motivo == D.MOTIVO_FLUJO_AUSENTE


def test_fila_libro_degradada_no_sirve():
    b = _fila_libro("X", T0, degraded=1)
    ok, motivo = D._fila_libro_util(b)
    assert not ok and motivo == D.MOTIVO_LIBRO_INCOMPLETO
    b = _fila_libro("X", T0)
    ok, _ = D._fila_libro_util(b)
    assert ok


def test_bucket_10s_disponibilidad():
    f = _bucket_10s("X", T0, 11.0, 10.0, 100.0, 100.0, as_of_extra=-1)
    ok, motivo = D._bucket_10s_util(f)
    assert not ok and motivo == "bucket_10s_sin_disponibilidad"
    f = _bucket_10s("X", T0, 11.0, 10.0, 100.0, 100.0, calidad="PARTIAL_OK")
    ok, motivo = D._bucket_10s_util(f)
    assert not ok and motivo == "bucket_10s_incompleto"
