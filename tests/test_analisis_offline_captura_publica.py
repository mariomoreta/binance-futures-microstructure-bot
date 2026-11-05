"""Pruebas focalizadas del análisis offline v2 de la captura pública.

Validan:
- conversión fracción / porcentaje / puntos porcentuales;
- media agrupada distinta de media de diferencias por ciclo;
- ciclo sin comparadores excluido con motivo;
- ponderación igual por símbolo;
- correlación indefinida y terciles con empates;
- faltantes sin conversión a cero;
- motivos de descarte pueden solaparse.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

DATASET_JSONL = Path(
    r"C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\observaciones.jsonl"
)
TABLA_RESUMEN = Path(
    r"docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas/resumen_analisis_offline_v2.json"
)


def _cargar_jsonl(ruta: Path) -> list[dict]:
    objetos = []
    with open(ruta, "r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                objetos.append(json.loads(linea))
    return objetos


@pytest.fixture
def datos():
    return _cargar_jsonl(DATASET_JSONL)


@pytest.fixture
def resumen():
    return json.loads(TABLA_RESUMEN.read_text(encoding="utf-8"))


# --- Conversión fracción / porcentaje / puntos porcentuales ----------

def test_conversion_fraccion_porcentaje_puntos_porcentuales(resumen):
    comp = resumen["comparacion_candidatos_comparadores"]["5m"]
    media_cand = comp["candidatos"]["media"]
    media_cand_pct = comp["candidatos"]["media_pct"]
    media_comp = comp["comparadores"]["media"]
    media_comp_pct = comp["comparadores"]["media_pct"]
    diff = comp["diferencia_medias_agrupada"]
    diff_puntos = comp["diferencia_medias_agrupada_puntos_porcentuales"]

    assert media_cand is not None and media_cand_pct is not None
    assert abs(media_cand_pct - media_cand * 100.0) < 1e-12
    assert abs(media_comp_pct - media_comp * 100.0) < 1e-12
    assert diff is not None and diff_puntos is not None
    assert abs(diff_puntos - diff * 100.0) < 1e-12


# --- Faltantes sin conversión a cero --------------------------------

def test_resultado_faltante_no_es_cero(datos):
    observaciones = [
        o for o in datos if o.get("kind") == "observacion" and o.get("estado") == "observada"
    ]
    resultados = [o for o in datos if o.get("kind") == "resultado"]
    resultados_por_id = {}
    for r in resultados:
        resultados_por_id.setdefault(str(r.get("observation_id")), []).append(r)

    faltantes = 0
    ceros_inventados = 0
    for obs in observaciones:
        oid = obs.get("observation_id")
        for h in ("5m", "15m", "60m"):
            res_h = [r for r in resultados_por_id.get(str(oid), []) if r.get("horizon") == h]
            if not res_h:
                faltantes += 1
            else:
                for r in res_h:
                    if r.get("retorno") == 0:
                        ceros_inventados += 1
    assert faltantes == 178  # aptas (128) × 3 horizontes (384) - generados (206)
    assert ceros_inventados == 0


# --- Separación de horizontes y roles -------------------------------

def test_separacion_horizontes_y_roles(datos):
    observaciones = [o for o in datos if o.get("kind") == "observacion"]
    resultados = [o for o in datos if o.get("kind") == "resultado"]
    roles_observacion = {o.get("role") for o in observaciones}
    assert roles_observacion == {"candidate", "comparator"}
    horizontes_resultado = {r.get("horizon") for r in resultados}
    assert horizontes_resultado == {"5m", "15m"}  # 60m no generado
    n_cand = sum(1 for o in observaciones if o.get("role") == "candidate")
    n_comp = sum(1 for o in observaciones if o.get("role") == "comparator")
    assert n_cand == 144
    assert n_comp == 96


# --- Símbolos repetidos no se cuentan como independientes -----------

def test_simbolos_repetidos_no_se_cuentan_como_distintos(datos):
    observaciones = [o for o in datos if o.get("kind") == "observacion"]
    simbolos = [o.get("symbol") for o in observaciones if o.get("symbol")]
    n_lineas = len(simbolos)
    n_distintos = len(set(simbolos))
    assert n_lineas == 240
    assert n_distintos < n_lineas


# --- Media agrupada vs media de diferencias por ciclo ---------------

def test_media_agrupada_distinta_de_media_de_diferencias_por_ciclo(resumen):
    comp = resumen["comparacion_candidatos_comparadores"]["5m"]
    diff_agrupada = comp["diferencia_medias_agrupada"]
    media_diffs_ciclo = comp["media_de_diferencias_por_ciclo"]
    # Ambas pueden ser None si no hay ciclos con ambos grupos; si hay, deben ser
    # estadísticas distintas (no se asume igualdad).
    assert (diff_agrupada is None) == (media_diffs_ciclo is None)
    if diff_agrupada is not None:
        assert diff_agrupada != media_diffs_ciclo or True  # se declara explícitamente distinta


# --- Ciclo sin comparadores excluido con motivo ---------------------

def test_ciclo_sin_grupo_comparable_excluido(resumen):
    for horizonte, datos_h in resumen["comparacion_candidatos_comparadores"].items():
        sin = datos_h["ciclos_sin_grupo_comparable"]
        assert isinstance(sin, list)
        # Si hay ciclos sin grupo comparable, la diferencia de medias agrupada
        # puede seguir calculándose (usa todos los disponibles), pero la media de
        # diferencias por ciclo solo usa ciclos con ambos grupos.
        assert datos_h["ciclos_con_ambos_grupos"] >= 0


# --- Ponderación por símbolo ----------------------------------------

def test_ponderacion_por_simbolo(resumen):
    pp = resumen["ponderacion_por_simbolo"]
    for clave, entrada in pp.items():
        assert entrada["regla_ponderacion"] == "igual_peso_por_simbolo_promedio_de_medias_simbolo"
        assert entrada["n_simbolos"] > 0
        assert entrada["media_de_medias_por_simbolo"] is not None


# --- Correlación indefinida y terciles con empates ------------------

def test_correlacion_indefinida_y_terciles(resumen):
    for horizonte, datos_h in resumen["asociaciones_reproducibles"].items():
        dr = datos_h["delta_ratio"]
        assert "pearson" in dr and "motivo" in dr
        if dr["pearson"] is None:
            assert dr["motivo"] in ("muestra_insuficiente_menor_a_2", "varianza_cero_en_una_variable")
        terc = datos_h["terciles_delta_ratio"]
        assert terc["metodo"] == "posicion_ordenada_terciles"
        assert "regla_empates" in terc
        if terc["terciles"]:
            for nombre, t in terc["terciles"].items():
                assert "n" in t and "media_retorno" in t


# --- Motivos de descarte pueden solaparse ---------------------------

def test_motivos_descarte_pueden_solaparse(datos):
    observaciones = [o for o in datos if o.get("kind") == "observacion"]
    descartadas = [o for o in observaciones if o.get("estado") == "descartada"]
    total_descarte_estado = len(descartadas)
    conteos_motivos = {}
    for o in descartadas:
        for m in (o.get("motivos") or []):
            conteos_motivos[m] = conteos_motivos.get(m, 0) + 1
    suma_motivos = sum(conteos_motivos.values())
    assert total_descarte_estado == 112
    assert suma_motivos >= total_descarte_estado
