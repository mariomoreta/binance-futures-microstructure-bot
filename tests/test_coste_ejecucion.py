"""Pruebas enfocadas del inventario de coste de ejecucion.

Cubren la definicion predeclarada: congelacion de extremos, ventana de
cercania, disponibilidad sin adelanto, calidad, C0 (bid/ask observados),
conteos por captura, veredicto por suficiencia y la correccion de etiqueta.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import coste_ejecucion_inventario as ci  # noqa: E402

PUBLICADO = RAIZ / "docs" / "evidence" / "extension-previa-20261119" / "C-resumen.json"
COMPACTO = RAIZ / "docs" / "evidence" / "coste-ejecucion-20261119" / "C-inventario.json"
COMPLETO = Path(r"C:\proyectos\binance-futures-data\coste-ejecucion-v1\inventario.json")
DATOS = Path(r"C:\proyectos\binance-futures-data")


def _episodio(symbol: str, cut: int, grupo: str = "EXTENDIDO") -> dict:
    return {
        "captura": "cap-a",
        "symbol": symbol,
        "direccion": "LONG",
        "cut_ms": cut,
        "precio_entrada": 100.0,
        "precio_salida": 101.0,
        "retorno_bruto_bps": 100.0,
        "retorno_neto_bps": 84.0,
        "grupo": grupo,
    }


def _crear_captura(tmp_path: Path, episodios: list, snapshots: list,
                   con_bid_ask: bool = False) -> tuple:
    cap = tmp_path / "cap-a"
    cap.mkdir()
    db = cap / "research.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE research_book_1m ("
        "symbol TEXT, bucket_start INTEGER, bucket_end INTEGER, sample_count INTEGER, "
        "spread_min REAL, spread_mean REAL, spread_max REAL, degraded INTEGER, "
        "crossed INTEGER, first_event_ms INTEGER, last_event_ms INTEGER, as_of_ms INTEGER, "
        "PRIMARY KEY (symbol, bucket_start))")
    for e in episodios:
        entrada = (e["cut_ms"] // ci.VENTANA_MS + 1) * ci.VENTANA_MS
        for ms in (entrada, entrada + ci.HORIZONTE_MS):
            con.execute(
                "INSERT INTO research_book_1m VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (e["symbol"], ms, ms + 60_000, 100, 1.0, 2.0, 3.0, 0, 0,
                 ms + 100, ms + 59_000, ms + 60_100))
    con.commit()
    con.close()

    with (cap / "observaciones.jsonl").open("w", encoding="utf-8") as f:
        for s in snapshots:
            f.write(json.dumps({
                "symbol": s["symbol"],
                "precio_base": s["mid"],
                "integridad": {"libro_degradado": False, "libro_cruzado": False},
                "libro": {
                    "event_ms": s["event_ms"],
                    "received_ms": s["received_ms"],
                    "spread_bps": s["spread_bps"],
                    "bid_levels": 20,
                    "ask_levels": 20,
                    **({"best_bid": s["bid"], "best_ask": s["ask"]} if con_bid_ask else {}),
                },
            }) + "\n")

    epis_dir = tmp_path / "episodios.json"
    epis_dir.write_text(json.dumps({"primaria_solo_precio": {"detalle": episodios}}),
                        encoding="utf-8")
    return str(tmp_path), str(epis_dir)


def _snap(symbol: str, instante: int, delta: int = -1_000, bid=None, ask=None) -> dict:
    return {
        "symbol": symbol,
        "event_ms": instante + delta,
        "received_ms": instante + delta + 100,
        "spread_bps": 4.0,
        "mid": 100.0,
        "bid": bid,
        "ask": ask,
    }


# ---------------------------------------------------------------------------
# Extremos y etiqueta
# ---------------------------------------------------------------------------

def test_cargar_episodios_congela_entrada_y_salida(tmp_path: Path) -> None:
    cut = 1_700_000_000_123
    ruta = tmp_path / "e.json"
    ruta.write_text(json.dumps({"primaria_solo_precio": {"detalle": [_episodio("AAAUSDT", cut)]}}),
                    encoding="utf-8")
    episodios = ci.cargar_episodios(str(ruta))
    entrada = (cut // 60_000 + 1) * 60_000
    assert episodios[0]["entrada_ms"] == entrada
    assert episodios[0]["salida_ms"] == entrada + 300_000
    assert episodios[0]["precio_entrada"] == 100.0


def test_efecto_filtro_separa_suma_y_cambio() -> None:
    detalle = [
        {"grupo": "EXTENDIDO", "retorno_neto_bps": -10.0},
        {"grupo": "EXTENDIDO", "retorno_neto_bps": -5.0},
        {"grupo": "NORMAL", "retorno_neto_bps": 2.0},
    ]
    r = ci.efecto_filtro(detalle)
    assert r["descartados"] == 2
    assert r["suma_descartados_bps"] == -15.0
    assert r["cambio_de_suma_al_abstenerse_bps"] == 15.0
    assert r["suma_retenidos_bps"] == 2.0
    assert r["suma_sin_filtro_bps"] == -13.0


def test_efecto_filtro_valores_publicados() -> None:
    if not PUBLICADO.exists():
        pytest.skip("evidencia anterior no disponible")
    detalle = json.loads(PUBLICADO.read_text(encoding="utf-8"))["primaria_solo_precio"]["detalle"]
    r = ci.efecto_filtro(detalle)
    assert r["descartados"] == 193
    assert round(r["suma_descartados_bps"], 2) == -1506.08
    assert round(r["cambio_de_suma_al_abstenerse_bps"], 2) == 1506.08
    assert round(r["media_retenidos_bps"], 2) == -17.84


# ---------------------------------------------------------------------------
# Criterios
# ---------------------------------------------------------------------------

def test_c1_ventana_exacta_y_un_ms_fuera() -> None:
    s = {"event_ms": 1_000, "received_ms": 900}
    assert ci._c1(s, 6_000)
    assert not ci._c1(s, 6_001)


def test_c1_exige_disponibilidad_sin_adelanto() -> None:
    s = {"event_ms": 1_000, "received_ms": 1_001}
    assert not ci._c1(s, 1_000)


def test_c1_sin_evento() -> None:
    assert not ci._c1({"event_ms": None, "received_ms": 1}, 1_000)


def test_c2_degradado_cruzado_y_niveles() -> None:
    base = {"degradado": False, "cruzado": False, "bid_levels": 20, "ask_levels": 20}
    assert ci._c2(base)
    assert not ci._c2({**base, "degradado": True})
    assert not ci._c2({**base, "cruzado": True})
    assert not ci._c2({**base, "bid_levels": 0})
    assert not ci._c2({**base, "ask_levels": None})


def test_c0_requiere_precios_explicitos_y_coherentes() -> None:
    assert not ci._cotizacion_observada({"best_bid": None, "best_ask": 101.0})
    assert not ci._cotizacion_observada({"best_bid": 101.0, "best_ask": 100.0})
    assert ci._cotizacion_observada({"best_bid": 99.9, "best_ask": 100.1})


def test_campos_bid_ask_rechaza_agregados_de_profundidad() -> None:
    bid, ask = ci._campos_bid_ask([
        "bid5_mean", "ask5_mean", "bid_base_top20", "ask_base_top20",
        "bid_levels", "ask_levels", "spread_mean"])
    assert bid == [] and ask == []


def test_campos_bid_ask_acepta_nombres_explicitos() -> None:
    bid, ask = ci._campos_bid_ask(["best_bid", "BEST_ASK", "bid5_mean"])
    assert bid == ["best_bid"]
    assert ask == ["best_ask"]


def test_stats_mediana_y_cuartiles() -> None:
    assert ci._stats([5.0])["mediana"] == 5.0
    assert ci._stats([5.0])["p25"] is None
    assert ci._stats([1.0, 2.0, 3.0, 4.0])["mediana"] == 2.5


# ---------------------------------------------------------------------------
# Inventario sintetico
# ---------------------------------------------------------------------------

def test_inventario_sintetico_sin_bid_ask(tmp_path: Path) -> None:
    cut = 1_700_000_000_123
    entrada = (cut // 60_000 + 1) * 60_000
    episodio = _episodio("AAAUSDT", cut)
    snaps = [_snap("AAAUSDT", entrada), _snap("AAAUSDT", entrada + 300_000)]
    datos, ruta_episodios = _crear_captura(tmp_path, [episodio], snaps)
    r = ci.inventariar(datos, ci.cargar_episodios(ruta_episodios))
    assert r["total"]["episodios"] == 1
    assert r["total"]["bucket_ambos"] == 1
    assert r["total"]["bucket_entrada_disponible_al_instante"] == 0
    assert r["total"]["obs_ambos_5s"] == 1
    assert r["total"]["pares_c0"] == 0
    assert r["total"]["pares_c3"] == 0
    assert r["veredicto"] == "DATOS_INSUFICIENTES"
    assert r["descomposicion_coste"]["spread"] == "NO_VERIFICABLE"


def test_inventario_sintetico_con_bid_ask_observados(tmp_path: Path) -> None:
    cut = 1_700_000_000_123
    entrada = (cut // 60_000 + 1) * 60_000
    episodio = _episodio("AAAUSDT", cut)
    snaps = [
        _snap("AAAUSDT", entrada, bid=99.9, ask=100.1),
        _snap("AAAUSDT", entrada + 300_000, bid=100.9, ask=101.1),
    ]
    datos, ruta_episodios = _crear_captura(tmp_path, [episodio], snaps, con_bid_ask=True)
    r = ci.inventariar(datos, ci.cargar_episodios(ruta_episodios))
    assert r["total"]["pares_c0"] == 1
    assert r["total"]["pares_c3"] == 1
    assert r["veredicto"] == "DATOS_INSUFICIENTES"  # 1 < 30
    assert r["descomposicion_coste"]["spread"] == "OBSERVADO"


def test_compacto_reduce_registros(tmp_path: Path) -> None:
    cut = 1_700_000_000_123
    entrada = (cut // 60_000 + 1) * 60_000
    snaps = [_snap("AAAUSDT", entrada), _snap("AAAUSDT", entrada + 300_000)]
    datos, ruta = _crear_captura(tmp_path, [_episodio("AAAUSDT", cut)], snaps)
    completo = ci.inventariar(datos, ci.cargar_episodios(ruta))
    compacto = ci._compacto(completo)
    assert len(compacto["episodios"]) == 1
    assert compacto["total"] == completo["total"]
    assert "best_bid" not in compacto["episodios"][0]


# ---------------------------------------------------------------------------
# Evidencia publicada
# ---------------------------------------------------------------------------

def test_compacto_publicado_cobertura_cero() -> None:
    if not COMPACTO.exists():
        pytest.skip("inventario compacto no disponible")
    d = json.loads(COMPACTO.read_text(encoding="utf-8"))
    t = d["total"]
    assert t["episodios"] == 278
    assert (t["bucket_entrada"], t["bucket_salida"], t["bucket_ambos"]) == (277, 273, 272)
    assert t["obs_ambos_5s"] == 2
    assert t["pares_c0"] == 0 and t["pares_c3"] == 0
    assert d["veredicto"] == "DATOS_INSUFICIENTES"
    assert d["descomposicion_coste"]["funding"] == "UNKNOWN"


def test_no_se_publica_neto_ajustado() -> None:
    if not COMPACTO.exists():
        pytest.skip("inventario compacto no disponible")
    d = json.loads(COMPACTO.read_text(encoding="utf-8"))
    assert "retorno_ajustado_bps" not in d
    assert "neto_ajustado_bps" not in d
    assert "no se usa para calcular retornos" in d["margen"]["nota"]


def test_verificador_independiente_sin_fallos() -> None:
    if not COMPLETO.exists() or not PUBLICADO.exists() or not DATOS.exists():
        pytest.skip("datos completos no disponibles")
    ruta = RAIZ / "scripts" / "verificar_coste_ejecucion.py"
    spec = importlib.util.spec_from_file_location("verificar_coste_ejecucion", str(ruta))
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    inv = json.loads(COMPLETO.read_text(encoding="utf-8"))
    pub = json.loads(PUBLICADO.read_text(encoding="utf-8"))
    compacto = json.loads(COMPACTO.read_text(encoding="utf-8"))
    c = modulo.verificar(inv, pub, str(DATOS), compacto)
    assert c.total > 10_000
    assert c.fallos == []
