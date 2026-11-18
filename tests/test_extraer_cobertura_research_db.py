# -*- coding: utf-8 -*-
"""Pruebas del extractor offline de cobertura (`scripts/extraer_cobertura_research_db.py`).

Ejecutan el CLI real contra una SQLite temporal construida por la prueba, con
expectativas calculadas de forma independiente (conteos escritos a mano, no
reutilizando el algoritmo del extractor). Sin red, sin Binance, sin datos
reales: la corrida sobre `research.db` se documenta aparte.

Casos incluidos en la SQLite temporal:
- terna válida (3 ventanas contiguas completas)
- hueco entre ventanas del mismo símbolo (3 ventanas, 0 ternas)
- falta de contraparte (flujo sin fila de libro)
- ventana parcial (intervalo de 90 s)
- precio ausente (`price_close` NULL)
- un lado sin operaciones (`buy_notional = 0` registrado, admisible)
- `as_of_ms` ausente SOLO en flujo (no debe tomar prestado el de libro)
- `as_of_ms` ausente SOLO en libro (no debe tomar prestado el de flujo)
- clave duplicada contradictoria (no se sustituye en silencio)
- corrida distinta entre flujo y libro (no se mezclan corridas)
- símbolo con ventanas acreditadas pero sin ternas (no cuenta en
  `simbolos_con_ternas`)

Ejecutar con: pytest tests/test_extraer_cobertura_research_db.py
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "extraer_cobertura_research_db.py"

T0 = 1794857160000  # inicio de minuto (T0 % 60000 == 0)
RUN = "exp-v2-ventana-4-20261116a"
MIN = 60_000

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


def _flujo(symbol: str, inicio: int, **extra) -> dict:
    fila = {
        "symbol": symbol,
        "bucket_start": inicio,
        "bucket_end": inicio + MIN,
        "bucket_size_s": 60,
        "buy_notional": 100.0,
        "sell_notional": 20.0,
        "price_close": 1.5,
        "first_event_ms": inicio + 1000,
        "last_event_ms": inicio + MIN - 1000,
        "data_quality": "OK",
        "run_id": RUN,
        "as_of_ms": inicio + MIN + 111,
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
        "sample_count": 300,
        "bid20_mean": 5000.0,
        "ask20_mean": 4800.0,
        "depth_gaps": 0,
        "degraded": 0,
        "crossed": 0,
        "first_event_ms": inicio + 1200,
        "last_event_ms": inicio + MIN - 1200,
        "run_id": RUN,
        "as_of_ms": inicio + MIN + 222,
        "price_source": "depth20",
        "dataset_id": "ds",
    }
    fila.update(extra)
    return fila


def _dataset():
    """Construye las filas de la SQLite temporal (expectativas a mano)."""
    flujo = []
    libro = []

    # 1) TERNA3: 3 minutos contiguos, todo acreditado -> 1 terna.
    for k in range(3):
        inicio = T0 + k * MIN
        flujo.append(_flujo("TERNA3", inicio))
        libro.append(_libro("TERNA3", inicio))

    # 2) HUECO: 3 ventanas válidas, la tercera separada por un minuto -> 0 ternas.
    for inicio in (T0, T0 + MIN, T0 + 3 * MIN):
        flujo.append(_flujo("HUECO", inicio))
        libro.append(_libro("HUECO", inicio))

    # 3) SINCONTRAPARTE: 3 filas de flujo, 2 de libro -> 1 clave sin contraparte.
    for k in range(3):
        flujo.append(_flujo("SINCONTRAPARTE", T0 + k * MIN))
    for k in range(2):
        libro.append(_libro("SINCONTRAPARTE", T0 + k * MIN))

    # 4) PARCIAL: tercera ventana de 90 s (no es un minuto completo).
    for k in range(2):
        flujo.append(_flujo("PARCIAL", T0 + k * MIN))
        libro.append(_libro("PARCIAL", T0 + k * MIN))
    inicio = T0 + 2 * MIN
    flujo.append(
        _flujo(
            "PARCIAL",
            inicio,
            bucket_end=inicio + MIN + 30_000,
            bucket_size_s=90,
            last_event_ms=inicio + MIN + 29_000,
        )
    )
    libro.append(
        _libro(
            "PARCIAL",
            inicio,
            bucket_end=inicio + MIN + 30_000,
            last_event_ms=inicio + MIN + 29_000,
        )
    )

    # 5) SINPRECIO: precio ausente en la ventana del medio.
    for k in range(3):
        inicio = T0 + k * MIN
        flujo.append(_flujo("SINPRECIO", inicio, price_close=None if k == 1 else 1.5))
        libro.append(_libro("SINPRECIO", inicio))

    # 6) CERO: compra agresora = 0 REGISTRADA (admisible, no es dato ausente).
    for k in range(3):
        inicio = T0 + k * MIN
        flujo.append(_flujo("CERO", inicio, buy_notional=0.0))
        libro.append(_libro("CERO", inicio))

    # 7) SINASOF_FLUJO: as_of_ms ausente SOLO en flujo, ventana del medio.
    for k in range(3):
        inicio = T0 + k * MIN
        flujo.append(_flujo("SINASOF_FLUJO", inicio, as_of_ms=None if k == 1 else inicio + MIN + 111))
        libro.append(_libro("SINASOF_FLUJO", inicio))

    # 8) SINASOF_LIBRO: as_of_ms ausente SOLO en libro, ventana del medio.
    for k in range(3):
        inicio = T0 + k * MIN
        flujo.append(_flujo("SINASOF_LIBRO", inicio))
        libro.append(
            _libro("SINASOF_LIBRO", inicio, as_of_ms=None if k == 1 else inicio + MIN + 222)
        )

    # 9) DUPLICADA: clave contradictoria en la ventana del medio.
    for k in range(3):
        inicio = T0 + k * MIN
        flujo.append(_flujo("DUPLICADA", inicio))
        libro.append(_libro("DUPLICADA", inicio))
    flujo.append(_flujo("DUPLICADA", T0 + MIN, buy_notional=999.0))

    # 10) CORRIDA: el libro de la ventana del medio viene de otra corrida.
    for k in range(3):
        inicio = T0 + k * MIN
        flujo.append(_flujo("CORRIDA", inicio))
        libro.append(
            _libro("CORRIDA", inicio, run_id="otra-corrida" if k == 1 else RUN)
        )

    return flujo, libro


def _crear_db(ruta: Path) -> None:
    con = sqlite3.connect(str(ruta))
    try:
        cur = con.cursor()
        cur.execute(ESQUEMA_FLUJO)
        cur.execute(ESQUEMA_LIBRO)
        flujo, libro = _dataset()
        for fila in flujo:
            cur.execute(
                "INSERT INTO research_flow_1m VALUES "
                "(:symbol,:bucket_start,:bucket_end,:bucket_size_s,:buy_notional,"
                ":sell_notional,:price_close,:first_event_ms,:last_event_ms,"
                ":data_quality,:run_id,:as_of_ms,:price_source,:dataset_id)",
                fila,
            )
        for fila in libro:
            cur.execute(
                "INSERT INTO research_book_1m VALUES "
                "(:symbol,:bucket_start,:bucket_end,:sample_count,:bid20_mean,"
                ":ask20_mean,:depth_gaps,:degraded,:crossed,:first_event_ms,"
                ":last_event_ms,:run_id,:as_of_ms,:price_source,:dataset_id)",
                fila,
            )
        con.commit()
    finally:
        con.close()


def _ejecutar(db: Path, salida: Path, observaciones: Path = None):
    comando = [
        sys.executable,
        str(SCRIPT),
        "--db",
        str(db),
        "--salida",
        str(salida),
    ]
    if observaciones is not None:
        comando += ["--observaciones", str(observaciones)]
    return subprocess.run(
        comando, cwd=str(ROOT), capture_output=True, text=True
    )


def _cargar(salida: Path) -> dict:
    return json.loads(salida.read_text(encoding="utf-8"))


def test_cli_acredita_solo_lo_que_cuenta(tmp_path):
    db = tmp_path / "research.db"
    salida = tmp_path / "cobertura.json"
    _crear_db(db)
    hash_antes = hashlib.sha256(db.read_bytes()).hexdigest()

    res = _ejecutar(db, salida)
    assert res.returncode == 0, res.stderr
    assert res.stderr == ""
    salida_json = _cargar(salida)

    # La DB temporal no se modifica (mode=ro).
    assert hashlib.sha256(db.read_bytes()).hexdigest() == hash_antes

    pob = salida_json["poblacion_b_agregados_1m"]

    # Parejas: 3+3+2+3+3+3+3+3+3+3 = 29 claves presentes en ambas tablas.
    assert pob["parejas_iniciales"] == 29
    # 2 parejas no acreditadas: 1 clave duplicada y 1 corrida distinta.
    assert pob["parejas_no_acreditadas"]["total"] == 2
    assert pob["parejas_no_acreditadas"]["motivos_solapables"] == {
        "clave_duplicada": 1,
        "corrida_distinta": 1,
    }
    assert pob["parejas_acreditadas"] == 27
    assert pob["sin_contraparte"]["flujo_sin_libro"] == 1
    assert pob["sin_contraparte"]["libro_sin_flujo"] == 0

    etapas = {e["requisito"]: e for e in pob["requisitos"]}
    assert etapas["completitud"]["entrada"] == 27
    assert etapas["completitud"]["excluidas"] == 1
    assert etapas["integridad_por_intervalo"]["excluidas"] == 0
    assert etapas["valores_validos"]["excluidas"] == 0
    assert etapas["precio"]["excluidas"] == 1
    assert etapas["disponibilidad_acreditada"]["excluidas"] == 2
    assert etapas["disponibilidad_acreditada"]["supervivientes"] == 23

    # Motivos solapables: la ventana parcial incumple varios criterios a la vez.
    assert etapas["completitud"]["motivos_solapables"] == {
        "flujo_intervalo_no_es_un_minuto": 1,
        "flujo_tamano_distinto_de_60s": 1,
        "libro_intervalo_no_es_un_minuto": 1,
    }
    assert etapas["precio"]["motivos_solapables"] == {"precio_ausente": 1}
    assert etapas["disponibilidad_acreditada"]["motivos_solapables"] == {
        "as_of_flujo_ausente": 1,
        "as_of_libro_ausente": 1,
    }

    # Exclusiones únicas (1 ventana por requisito) frente a motivos solapables.
    assert pob["exclusiones"]["ventanas_excluidas_total"] == 4
    assert pob["exclusiones"]["claves_duplicadas"] == 1
    assert sum(pob["motivos_totales"]["motivos_solapables"].values()) > 4

    # Ventanas acreditadas y ternas: TERNA3 y CERO aportan 1 cada una.
    assert pob["ventanas_acreditadas"] == 23
    assert len(pob["ventanas_detalle"]) == 23
    assert pob["ternas"]["ternas"] == 2
    assert pob["ternas"]["ternas_por_simbolo"] == {"CERO": 1, "TERNA3": 1}
    # Solo 2 símbolos tienen terna; 8 símbolos más tienen ventanas sin terna.
    assert pob["ternas"]["simbolos_con_ternas"] == 2
    assert salida_json["resumen"]["simbolos_con_ternas"] == 2
    assert salida_json["resumen"]["ventanas_acreditadas"] == 23

    # La cadena declarada no puede divergir de las etapas ni del recuento final.
    cadena = {c["etapa"]: c for c in pob["cadena"]}
    assert cadena["parejas_iniciales"]["ternas_tras_requisito"] is not None
    for nombre, etapa in etapas.items():
        assert cadena[nombre]["entrada"] == etapa["entrada"], nombre
        assert cadena[nombre]["excluidas"] == etapa["excluidas"], nombre
        assert cadena[nombre]["supervivientes"] == etapa["supervivientes"], nombre
    assert cadena["disponibilidad_acreditada"]["supervivientes"] == 23
    assert cadena["disponibilidad_acreditada"]["ternas_tras_requisito"] == 2
    assert cadena["disponibilidad_acreditada"]["ternas_tras_requisito"] == pob["ternas"]["ternas"]
    assert sum(pob["ternas"]["ternas_por_simbolo"].values()) == pob["ternas"]["ternas"]


def test_cli_no_toma_prestado_as_of_de_la_otra_fuente(tmp_path):
    """Si falta `as_of_ms` en una fuente, la disponibilidad conjunta es UNKNOWN
    y la ventana no se acredita. Si el extractor tomara prestado el timestamp
    de la otra fuente, SINASOF_FLUJO/SINASOF_LIBRO tendrían 3 ventanas y 1 terna cada
    uno: la prueba fallaría."""
    db = tmp_path / "research.db"
    salida = tmp_path / "cobertura.json"
    _crear_db(db)
    res = _ejecutar(db, salida)
    assert res.returncode == 0, res.stderr
    pob = _cargar(salida)["poblacion_b_agregados_1m"]

    simbolos = {v["symbol"] for v in pob["ventanas_detalle"]}
    assert "SINASOF_FLUJO" in simbolos and "SINASOF_LIBRO" in simbolos
    assert "SINASOF_FLUJO" not in pob["ternas"]["ternas_por_simbolo"]
    assert "SINASOF_LIBRO" not in pob["ternas"]["ternas_por_simbolo"]
    assert pob["ternas"]["ternas"] == 2, "se tomaron prestados timestamps ajenos"

    ventanas_sinasoff = [
        v for v in pob["ventanas_detalle"] if v["symbol"] == "SINASOF_FLUJO"
    ]
    ventanas_sinasoffb = [
        v for v in pob["ventanas_detalle"] if v["symbol"] == "SINASOF_LIBRO"
    ]
    assert len(ventanas_sinasoff) == 2
    assert len(ventanas_sinasoffb) == 2
    # La ventana del medio no aparece acreditada en ninguno de los dos casos.
    starts_sinasoff = {v["ventana_inicio_ms"] for v in ventanas_sinasoff}
    assert T0 + MIN not in starts_sinasoff
    starts_sinasoffb = {v["ventana_inicio_ms"] for v in ventanas_sinasoffb}
    assert T0 + MIN not in starts_sinasoffb

    etapas = {e["requisito"]: e for e in pob["requisitos"]}
    assert etapas["disponibilidad_acreditada"]["motivos_solapables"] == {
        "as_of_flujo_ausente": 1,
        "as_of_libro_ausente": 1,
    }


def test_cli_disponibilidad_es_el_maximo_y_no_el_cierre_nominal(tmp_path):
    db = tmp_path / "research.db"
    salida = tmp_path / "cobertura.json"
    _crear_db(db)
    res = _ejecutar(db, salida)
    assert res.returncode == 0, res.stderr
    pob = _cargar(salida)["poblacion_b_agregados_1m"]

    inicio = T0 + MIN
    ventana = next(
        v
        for v in pob["ventanas_detalle"]
        if v["symbol"] == "TERNA3" and v["ventana_inicio_ms"] == inicio
    )
    as_of_flujo = inicio + MIN + 111
    as_of_libro = inicio + MIN + 222
    assert ventana["disponibilidad_ms"] == max(as_of_flujo, as_of_libro)
    assert ventana["disponibilidad_ms"] != inicio + MIN  # no es bucket_end
    assert ventana["disponibilidad_ms"] != as_of_flujo  # no es el mínimo
    assert ventana["disponibilidad_conocida"] is True
    assert "no es el cierre nominal" in ventana["disponibilidad_definicion"]


def test_cli_precio_es_cierre_de_aggTrade_no_libro_mid(tmp_path):
    db = tmp_path / "research.db"
    salida = tmp_path / "cobertura.json"
    _crear_db(db)
    res = _ejecutar(db, salida)
    assert res.returncode == 0, res.stderr
    datos = _cargar(salida)
    ventana = datos["poblacion_b_agregados_1m"]["ventanas_detalle"][0]
    assert ventana["precio_fuente"] == "aggTrade"
    assert "aggTrade" in ventana["precio_definicion"]
    assert "no es libro_mid" in ventana["precio_definicion"]
    assert "aggTrade" in datos["definiciones"]["precio"]


def test_cli_cero_registrado_es_admisible_ausente_no(tmp_path):
    db = tmp_path / "research.db"
    salida = tmp_path / "cobertura.json"
    _crear_db(db)
    res = _ejecutar(db, salida)
    assert res.returncode == 0, res.stderr
    pob = _cargar(salida)["poblacion_b_agregados_1m"]

    cero = [v for v in pob["ventanas_detalle"] if v["symbol"] == "CERO"]
    assert len(cero) == 3
    assert all(v["buy_notional"] == 0.0 for v in cero)
    assert pob["ternas"]["ternas_por_simbolo"].get("CERO") == 1
    # El precio ausente sí excluye (no se interpreta como cero).
    etapas = {e["requisito"]: e for e in pob["requisitos"]}
    assert etapas["valores_validos"]["excluidas"] == 0
    assert etapas["precio"]["motivos_solapables"] == {"precio_ausente": 1}


def test_cli_poblacion_piloto_separa_y_no_inventa(tmp_path):
    db = tmp_path / "research.db"
    salida = tmp_path / "cobertura.json"
    _crear_db(db)

    # Sin --observaciones: poblacion A UNKNOWN, sin cifras inventadas.
    res = _ejecutar(db, salida)
    assert res.returncode == 0, res.stderr
    piloto = _cargar(salida)["poblacion_a_observaciones_piloto"]
    assert piloto["acreditado"] is False
    assert "total" not in piloto

    # Con --observaciones: se acredita por separado (2 aptas + 1 descartada).
    obs = tmp_path / "observaciones.jsonl"
    filas = [
        {"kind": "observacion", "symbol": "A", "estado": "observada",
         "apto_para_evaluacion": True, "motivos": []},
        {"kind": "observacion", "symbol": "B", "estado": "observada",
         "apto_para_evaluacion": True, "motivos": []},
        {"kind": "observacion", "symbol": "C", "estado": "descartada",
         "apto_para_evaluacion": False, "motivos": ["flujo_ventana_incompleta"]},
        {"kind": "resultado", "symbol": "A"},
    ]
    with io.open(obs, "w", encoding="utf-8", newline="\n") as f:
        for fila in filas:
            f.write(json.dumps(fila) + "\n")

    salida2 = tmp_path / "cobertura2.json"
    res2 = _ejecutar(db, salida2, observaciones=obs)
    assert res2.returncode == 0, res2.stderr
    piloto2 = _cargar(salida2)["poblacion_a_observaciones_piloto"]
    assert piloto2["acreditado"] is True
    assert piloto2["total"] == 3
    assert piloto2["aptas"] == 2
    assert piloto2["descartadas"] == 1
    assert piloto2["simbolos"] == 3
    assert piloto2["motivos_descarte_solapables"] == {"flujo_ventana_incompleta": 1}
    # No se mezcla con los agregados de un minuto.
    assert _cargar(salida2)["poblacion_b_agregados_1m"]["parejas_iniciales"] == 29


def test_cli_error_si_la_db_no_existe(tmp_path):
    salida = tmp_path / "cobertura.json"
    res = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(tmp_path / "no-existe.db"),
            "--salida",
            str(salida),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 3
    assert "no existe" in res.stderr
    assert not salida.exists()
