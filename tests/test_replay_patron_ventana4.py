# -*- coding: utf-8 -*-
"""Pruebas de la evaluación offline del patrón sobre la ventana 4.

Cubren los cuatro controles exigidos por el bloque:
  1. entrada REAL del extractor al detector (SQLite temporal + CLI real);
  2. una fuente tardía retrasa el corte y, con él, la referencia de entrada;
  3. la agrupación por episodio no duplica alertas repetidas;
  4. un precio posterior faltante deja el resultado sin resolver, con motivo,
     sin saltar un hueco para buscar otro precio.

Además:
  5. el universo publicado (ventanas/ternas/símbolos) no se fuerza: si no
     cuadra, la conversión aborta;
  6. una ventana convertida que no coincide con su fila original aborta.

Sin red, sin Binance, sin datos reales: la corrida sobre `research.db` y las
consultas de velas se documentan aparte en la evidencia.

Ejecutar con: pytest tests/test_replay_patron_ventana4.py
"""

from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
EXTRACTOR = SCRIPTS / "extraer_cobertura_research_db.py"

sys.path.insert(0, str(SCRIPTS))

import replay_patron_ventana4 as R  # noqa: E402

T0 = 1794857160000  # alineado a minuto
MIN = 60_000
RUN = "run-test-patron"

ESQUEMA_FLUJO = """
CREATE TABLE research_flow_1m (
    symbol TEXT NOT NULL,
    bucket_start INTEGER NOT NULL,
    bucket_end INTEGER NOT NULL,
    bucket_size_s INTEGER NOT NULL,
    buy_notional REAL,
    sell_notional REAL,
    price_close REAL,
    first_event_ms INTEGER,
    last_event_ms INTEGER,
    data_quality TEXT,
    run_id TEXT,
    as_of_ms INTEGER,
    price_source TEXT,
    dataset_id TEXT
)
"""

ESQUEMA_LIBRO = """
CREATE TABLE research_book_1m (
    symbol TEXT NOT NULL,
    bucket_start INTEGER NOT NULL,
    bucket_end INTEGER NOT NULL,
    sample_count INTEGER,
    bid20_mean REAL,
    ask20_mean REAL,
    depth_gaps INTEGER DEFAULT 0,
    degraded INTEGER DEFAULT 0,
    crossed INTEGER DEFAULT 0,
    first_event_ms INTEGER,
    last_event_ms INTEGER,
    run_id TEXT,
    as_of_ms INTEGER,
    price_source TEXT,
    dataset_id TEXT
)
"""


# ---------------------------------------------------------------------------
# Fixtures de filas (mismas columnas que research.db)
# ---------------------------------------------------------------------------

def _flujo(symbol: str, inicio: int, **extra) -> dict:
    fila = {
        "symbol": symbol,
        "bucket_start": inicio,
        "bucket_end": inicio + MIN,
        "bucket_size_s": 60,
        "buy_notional": 100.0,
        "sell_notional": 20.0,
        "price_close": 1.0,
        "first_event_ms": inicio + 1000,
        "last_event_ms": inicio + MIN - 1000,
        "data_quality": "OK",
        "run_id": RUN,
        "as_of_ms": inicio + MIN + 500,
        "price_source": "aggTrade",
        "dataset_id": "ds",
    }
    fila.update(extra)
    return fila


def _libro(symbol: str, inicio: int, **extra) -> dict:
    fila = {
        "symbol": symbol,
        "bucket_start": inicio,
        "bucket_end": inicio + MIN,
        "sample_count": 200,
        "bid20_mean": 2000.0,
        "ask20_mean": 1000.0,
        "depth_gaps": 0,
        "degraded": 0,
        "crossed": 0,
        "first_event_ms": inicio + 1200,
        "last_event_ms": inicio + MIN - 1200,
        "run_id": RUN,
        "as_of_ms": inicio + MIN + 1500,
        "price_source": "depth20",
        "dataset_id": "ds",
    }
    fila.update(extra)
    return fila


def _terna_larga(symbol: str = "TESTUSDT", libro_as_of_extra: int = 0):
    """Terna LONG que cumple el patrón congelado.

    F = +100 / +200 / +500 ; D(ask) = 1000 / 900 / 800
    Q = +0.1 / +0.2222 / +0.625 (0 < Q1 < Q2 < Q3)
    cierres 1.00 / 1.01 / 1.02 (ascendentes)
    """
    compras = (300.0, 500.0, 900.0)
    ventas = (200.0, 300.0, 400.0)
    ask = (1000.0, 900.0, 800.0)
    bid = (1200.0, 1100.0, 1000.0)
    cierres = (1.00, 1.01, 1.02)
    flujo, libro = [], []
    for k in range(3):
        inicio = T0 + k * MIN
        flujo.append(
            _flujo(
                symbol,
                inicio,
                buy_notional=compras[k],
                sell_notional=ventas[k],
                price_close=cierres[k],
            )
        )
        libro.append(
            _libro(
                symbol,
                inicio,
                bid20_mean=bid[k],
                ask20_mean=ask[k],
                as_of_ms=inicio + MIN + 1500 + (libro_as_of_extra if k == 2 else 0),
            )
        )
    return flujo, libro


def _crear_db(ruta: Path, flujo, libro) -> None:
    con = sqlite3.connect(ruta)
    try:
        con.execute(ESQUEMA_FLUJO)
        con.execute(ESQUEMA_LIBRO)
        for tabla, filas in (("research_flow_1m", flujo), ("research_book_1m", libro)):
            columnas = list(filas[0].keys())
            sql = "INSERT INTO %s (%s) VALUES (%s)" % (
                tabla,
                ",".join(columnas),
                ",".join("?" for _ in columnas),
            )
            con.executemany(sql, [[f[c] for c in columnas] for f in filas])
        con.commit()
    finally:
        con.close()


def _ventana(
    symbol: str,
    inicio: int,
    *,
    buy: float,
    sell: float,
    bid: float,
    ask: float,
    as_of: int,
    precio: float,
) -> R.VentanaPresion:
    return R.VentanaPresion(
        symbol=symbol,
        observation_id=f"{symbol}|{inicio}",
        decision_ms=inicio + MIN,
        decision_iso=R.utc_iso(inicio + MIN),
        ventana_inicio_ms=inicio,
        ventana_fin_ms=inicio + MIN,
        evento_ms=inicio + MIN - 1000,
        evento_iso=R.utc_iso(inicio + MIN - 1000),
        disponibilidad_ms=as_of,
        disponibilidad_iso=R.utc_iso(as_of),
        ventana_completa=True,
        ventana_ms=MIN,
        buy_notional=buy,
        sell_notional=sell,
        bid_notional_top20=bid,
        ask_notional_top20=ask,
        precio_cierre=precio,
        precio_fuente="aggTrade",
        precio_event_ms=inicio + MIN - 1000,
        precio_event_iso=R.utc_iso(inicio + MIN - 1000),
        integridad_valida=True,
        fuente="prueba",
        cobertura={"run_id": RUN},
    )


def _vela(open_: float, *, high: float | None = None, low: float | None = None,
          final: bool = True, conflictiva: bool = False, open_time: int = 0) -> dict:
    return {
        "open": open_,
        "high": high if high is not None else open_,
        "low": low if low is not None else open_,
        "close": open_,
        "close_time": open_time + MIN - 1,
        "final": final,
        "adquirido_ms": open_time + MIN + 10,
        "conflictiva": conflictiva,
    }


def _alerta(symbol: str, direccion: str, cut: int, terna: str | None = None) -> dict:
    return {
        "symbol": symbol,
        "direccion": direccion,
        "terna": terna or f"{symbol}|{cut}",
        "cut_ms": cut,
        "cut_iso": R.utc_iso(cut),
        "cierre_nominal_ms": cut - 1,
        "demora_corte_ms": 1,
        "decision": f"{direccion}_EXPERIMENTAL",
        "origen": "patron",
        "tambien_patron": True,
    }


# ---------------------------------------------------------------------------
# 1. Entrada real del extractor al detector
# ---------------------------------------------------------------------------

def test_extractor_real_alimenta_detector(tmp_path):
    db = tmp_path / "research.db"
    flujo, libro = _terna_larga()
    _crear_db(db, flujo, libro)

    salida = tmp_path / "cobertura.json"
    proceso = subprocess.run(
        [sys.executable, str(EXTRACTOR), "--db", str(db), "--salida", str(salida)],
        capture_output=True,
        text=True,
    )
    assert proceso.returncode == 0, proceso.stderr
    cobertura = json.loads(salida.read_text(encoding="utf-8"))
    pob = cobertura["poblacion_b_agregados_1m"]
    assert len(pob["ventanas_detalle"]) == 3
    assert pob["ternas"]["ternas"] == 1

    por_symbol, auditoria = R.construir_ventanas(db, cobertura, RUN)
    assert auditoria["ventanas_convertidas"] == 3
    assert auditoria["ventanas_validas_detector"] == 3
    assert auditoria["flujo_as_of_anterior_al_cierre"] == 0

    universo = R.verificar_universo(por_symbol, cobertura)
    assert universo["conservado"] is True
    assert universo["obtenido"] == {"ventanas": 3, "ternas": 1, "simbolos": 1}

    decisiones = R.evaluar_detector(por_symbol)
    assert len(decisiones) == 1
    unica = next(iter(decisiones.values()))
    assert unica["decision"] == "LONG_EXPERIMENTAL"
    assert unica["direccion"] == "LONG"

    # El corte usa la disponibilidad (libro, más tardía), no el cierre nominal.
    alertas, resumen = R.alertas_patron(por_symbol, decisiones)
    assert resumen["alertas_brutas"] == 1
    assert alertas[0]["cut_ms"] == T0 + 2 * MIN + MIN + 1500
    assert alertas[0]["cierre_nominal_ms"] == T0 + 3 * MIN
    assert alertas[0]["demora_corte_ms"] == 1500


# ---------------------------------------------------------------------------
# 2. Fuente tardía -> corte más tardío -> entrada más tardía
# ---------------------------------------------------------------------------

def test_fuente_tardia_retrasa_corte_y_entrada():
    symbol = "TESTUSDT"
    inicio3 = T0 + 2 * MIN
    fin3 = inicio3 + MIN

    def _caso(extra_libro: int):
        ventanas = [
            _ventana(symbol, T0, buy=300, sell=200, bid=1200, ask=1000,
                     as_of=T0 + MIN + 1500, precio=1.00),
            _ventana(symbol, T0 + MIN, buy=500, sell=300, bid=1100, ask=900,
                     as_of=T0 + 2 * MIN + 1500, precio=1.01),
            _ventana(symbol, inicio3, buy=900, sell=400, bid=1000, ask=800,
                     as_of=fin3 + 1500 + extra_libro, precio=1.02),
        ]
        decisiones = {
            f"{symbol}|{inicio3}": {
                "symbol": symbol,
                "observation_id": f"{symbol}|{inicio3}",
                "decision": "LONG_EXPERIMENTAL",
                "direccion": "LONG",
                "motivo": "patron",
                "motivo_codigo": None,
                "instante_deteccion_ms": ventanas[2].disponibilidad_ms,
                "ventanas": [v.observation_id for v in ventanas],
            }
        }
        alertas, _ = R.alertas_patron({symbol: ventanas}, decisiones)
        assert len(alertas) == 1
        episodios = R.agrupar_episodios(alertas)
        assert len(episodios) == 1
        return episodios[0], ventanas[2].disponibilidad_ms

    normal, disp_normal = _caso(0)
    tardia, disp_tardia = _caso(90_000)
    assert tardia["cut_ms"] - normal["cut_ms"] == 90_000
    assert disp_tardia - disp_normal == 90_000

    entrada_normal = R._referencia_entrada(normal["cut_ms"])
    entrada_tardia = R._referencia_entrada(tardia["cut_ms"])
    assert entrada_normal == fin3 + MIN
    assert entrada_tardia == fin3 + 2 * MIN  # un minuto más tarde

    velas = {
        symbol: {
            entrada_normal: _vela(1.03, open_time=entrada_normal),
            entrada_normal + 300_000: _vela(1.04, open_time=entrada_normal + 300_000),
            entrada_tardia: _vela(1.05, open_time=entrada_tardia),
            entrada_tardia + 300_000: _vela(1.06, open_time=entrada_tardia + 300_000),
        }
    }
    res_normal = R.resolver_alerta(normal, velas)
    res_tardia = R.resolver_alerta(tardia, velas)
    assert res_normal["precio_entrada"] == 1.03
    assert res_tardia["precio_entrada"] == 1.05
    assert res_tardia["entrada_ms"] == res_normal["entrada_ms"] + MIN
    assert res_tardia["demora_total_ms"] == entrada_tardia - tardia["cut_ms"]


# ---------------------------------------------------------------------------
# 3. Agrupación: repetidas dentro de 5 minutos, sin duplicar episodios
# ---------------------------------------------------------------------------

def test_agrupacion_no_duplica_episodios():
    symbol = "TESTUSDT"
    base = T0
    alertas = [
        _alerta(symbol, "LONG", base, "T1"),
        _alerta(symbol, "LONG", base + 60_000, "T2"),
        _alerta(symbol, "LONG", base + 299_999, "T3"),
        _alerta(symbol, "LONG", base + 300_000, "T4"),   # nuevo episodio
        _alerta(symbol, "SHORT", base + 30_000, "T5"),   # otra dirección
        _alerta("OTROUSDT", "LONG", base + 30_000, "T6"),
    ]
    episodios = R.agrupar_episodios(alertas)
    assert len(episodios) == 4
    long_test = [e for e in episodios if e["symbol"] == symbol and e["direccion"] == "LONG"]
    assert [e["terna"] for e in long_test] == ["T1", "T4"]
    assert long_test[0]["repetidas"] == ["T2", "T3"]
    assert long_test[1]["repetidas"] == []
    cortos = [e for e in episodios if e["direccion"] == "SHORT"]
    assert len(cortos) == 1 and cortos[0]["terna"] == "T5"
    # El ancla es la primera alerta disponible: no se elige retrospectivamente.
    assert long_test[0]["cut_ms"] == base


# ---------------------------------------------------------------------------
# 4. Precio posterior faltante: no resoluble, sin saltar huecos
# ---------------------------------------------------------------------------

def test_precio_posterior_faltante_no_resuelve():
    symbol = "TESTUSDT"
    cut = T0 + 1000
    entrada = R._referencia_entrada(cut)
    assert entrada == T0 + MIN  # primer minuto estrictamente posterior

    alerta = _alerta(symbol, "LONG", cut)

    sin_symbol = R.resolver_alerta(alerta, {})
    assert sin_symbol["estado"] == "no_resoluble"
    assert sin_symbol["motivo"] == R.MOTIVO_SIN_VELAS

    # Hueco: hay una vela dos minutos después, pero no la del minuto exacto.
    solo_hueco = {symbol: {
        entrada + 2 * MIN: _vela(1.10, open_time=entrada + 2 * MIN),
    }}
    faltante_entrada = R.resolver_alerta(alerta, solo_hueco)
    assert faltante_entrada["estado"] == "no_resoluble"
    assert faltante_entrada["motivo"] == R.MOTIVO_ENTRADA_AUSENTE
    assert faltante_entrada["entrada_ms"] == entrada
    assert "precio_entrada" not in faltante_entrada

    # Entrada presente, salida exacta ausente.
    sin_salida = {symbol: {entrada: _vela(1.10, open_time=entrada)}}
    faltante_salida = R.resolver_alerta(alerta, sin_salida)
    assert faltante_salida["estado"] == "no_resoluble"
    assert faltante_salida["motivo"] == R.MOTIVO_SALIDA_AUSENTE
    assert faltante_salida["precio_entrada"] == 1.10

    # Vela contradictoria: no se usa.
    contradictoria = {symbol: {
        entrada: _vela(1.10, open_time=entrada, conflictiva=True),
        entrada + 300_000: _vela(1.20, open_time=entrada + 300_000),
    }}
    res_contra = R.resolver_alerta(alerta, contradictoria)
    assert res_contra["estado"] == "no_resoluble"
    assert res_contra["motivo"] == R.MOTIVO_CONTRADICTORIA

    # Caso completo: retorno alineado, adverso y favorable sobre la trayectoria.
    completa = {symbol: {
        entrada + i * MIN: _vela(
            1.10,
            high=1.10 + 0.01 * i,
            low=1.10 - 0.02,
            open_time=entrada + i * MIN,
        )
        for i in range(6)
    }}
    res = R.resolver_alerta(alerta, completa)
    assert res["estado"] == "resoluble"
    assert res["precio_entrada"] == 1.10
    assert res["precio_salida"] == 1.10
    assert res["retorno_bps"] == pytest.approx(0.0)
    assert res["adverso_bps"] == pytest.approx((1.10 - 0.02) / 1.10 * 1e4 - 1e4)
    assert res["trayectoria_completa"] is True

    # Trayectoria incompleta: el retorno existe, el adverso no se inventa.
    parcial = {symbol: {
        entrada: _vela(1.10, open_time=entrada),
        entrada + 300_000: _vela(1.12, open_time=entrada + 300_000),
    }}
    res_parcial = R.resolver_alerta(alerta, parcial)
    assert res_parcial["estado"] == "resoluble"
    assert res_parcial["retorno_bps"] == pytest.approx((1.12 / 1.10 - 1.0) * 1e4)
    assert res_parcial["adverso_bps"] is None
    assert res_parcial["trayectoria_completa"] is False


# ---------------------------------------------------------------------------
# 5. El universo publicado no se fuerza
# ---------------------------------------------------------------------------

def test_universo_publicado_no_se_fuerza():
    symbol = "TESTUSDT"
    ventanas = [
        _ventana(symbol, T0 + k * MIN, buy=100, sell=20, bid=2000, ask=1000,
                 as_of=T0 + (k + 1) * MIN + 500, precio=1.0)
        for k in range(5)
    ]
    cobertura = {
        "poblacion_b_agregados_1m": {
            "ventanas_acreditadas": 5,
            "ternas": {"ternas": 3, "simbolos_con_ternas": 1,
                       "ternas_por_simbolo": {symbol: 3}},
        }
    }
    ok = R.verificar_universo({symbol: ventanas}, cobertura)
    assert ok["obtenido"] == {"ventanas": 5, "ternas": 3, "simbolos": 1}

    cobertura["poblacion_b_agregados_1m"]["ternas"]["ternas"] = 4
    with pytest.raises(SystemExit):
        R.verificar_universo({symbol: ventanas}, cobertura)

    cobertura["poblacion_b_agregados_1m"]["ternas"]["ternas"] = 3
    cobertura["poblacion_b_agregados_1m"]["ternas"]["ternas_por_simbolo"] = {symbol: 2}
    with pytest.raises(SystemExit):
        R.verificar_universo({symbol: ventanas}, cobertura)


# ---------------------------------------------------------------------------
# 6. Conversión fiel: una discrepancia con la fila original aborta
# ---------------------------------------------------------------------------

def test_conversion_no_sustituye_valores_publicados(tmp_path):
    db = tmp_path / "research.db"
    flujo, libro = _terna_larga()
    _crear_db(db, flujo, libro)

    salida = tmp_path / "cobertura.json"
    proceso = subprocess.run(
        [sys.executable, str(EXTRACTOR), "--db", str(db), "--salida", str(salida)],
        capture_output=True,
        text=True,
    )
    assert proceso.returncode == 0, proceso.stderr
    cobertura = json.loads(salida.read_text(encoding="utf-8"))

    original = json.loads(json.dumps(cobertura))
    cobertura["poblacion_b_agregados_1m"]["ventanas_detalle"][1]["buy_notional"] += 1.0
    with pytest.raises(SystemExit):
        R.construir_ventanas(db, cobertura, RUN)

    cobertura = json.loads(json.dumps(original))
    cobertura["poblacion_b_agregados_1m"]["ventanas_detalle"][2]["disponibilidad_ms"] += 1
    with pytest.raises(SystemExit):
        R.construir_ventanas(db, cobertura, RUN)

    cobertura = json.loads(json.dumps(original))
    cobertura["poblacion_b_agregados_1m"]["ventanas_detalle"][0]["precio_cierre"] = 0.5
    with pytest.raises(SystemExit):
        R.construir_ventanas(db, cobertura, RUN)
