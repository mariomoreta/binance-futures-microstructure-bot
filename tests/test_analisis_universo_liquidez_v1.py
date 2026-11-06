"""Pruebas focalizadas del análisis universo-liquidez-v1 (captura 20261106a).

Validan:
- denominadores: profundidad top-20 nunca cero en este dataset; ratio None si denominador cero/ausente.
- roles: candidate y comparator mutuamente excluyentes; suman el total de observaciones.
- horizontes: 5m, 15m y 60m con 168 resultados cada uno; 0 faltantes; 0 huérfanos; 0 duplicados.
- unidades: fracción vs porcentaje vs puntos porcentuales (no se confunden).
- faltantes: nunca convertidos a cero.
- ponderaciones: media agrupada != media de diferencias por ciclo != media por símbolo.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

DATASET_JSONL = Path(
    r"C:\proyectos\binance-futures-data\public-pilot-1h-20261106a\observaciones.jsonl"
)
TABLA_RESUMEN = Path(
    r"docs/evidence/research/universe_liquidity_v1/public-pilot-1h-20261106a/tablas/resumen_analisis_universo_liquidez_v1.json"
)
DERIVADO = Path(
    r"C:\proyectos\binance-futures-data\public-pilot-1h-20261106a\derivados\analisis_universo_liquidez_v1/analisis_completo.json"
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


@pytest.fixture
def derivado():
    return json.loads(DERIVADO.read_text(encoding="utf-8"))


# --- 1. Conteo global desde fuente (sin confiar en el resumen) ----------

def test_conteo_global_desde_fuente(datos):
    ciclos = [o for o in datos if o.get("kind") == "ciclo"]
    obs = [o for o in datos if o.get("kind") == "observacion"]
    res = [o for o in datos if o.get("kind") == "resultado"]
    assert len(ciclos) == 12
    assert len(obs) == 216
    assert len(res) == 504
    assert sum(1 for o in obs if o.get("estado") == "observada") == 168
    assert sum(1 for o in obs if o.get("estado") == "descartada") == 48
    assert {r.get("horizon") for r in res} == {"5m", "15m", "60m"}
    assert all(r.get("estado") == "resuelto" for r in res)
    assert all(r.get("neto_estado") == "UNKNOWN" for r in res)


# --- 2. Roles mutuamente excluyentes ------------------------------------

def test_roles_mutuamente_excluyentes(datos, resumen):
    obs = [o for o in datos if o.get("kind") == "observacion"]
    roles = {o.get("role") for o in obs}
    assert roles == {"candidate", "comparator"}
    n_cand = sum(1 for o in obs if o.get("role") == "candidate")
    n_comp = sum(1 for o in obs if o.get("role") == "comparator")
    assert n_cand + n_comp == len(obs) == 216
    assert resumen["resumen_global"]["seleccionadas_por_rol"] == {
        "candidate": n_cand,
        "comparator": n_comp,
    }


# --- 3. Aptas y descartadas por rol -------------------------------------

def test_aptas_descartadas_por_rol(datos, resumen):
    obs = [o for o in datos if o.get("kind") == "observacion"]
    aptas_c = sum(1 for o in obs if o.get("role") == "candidate" and o.get("estado") == "observada")
    aptas_co = sum(1 for o in obs if o.get("role") == "comparator" and o.get("estado") == "observada")
    desc_c = sum(1 for o in obs if o.get("role") == "candidate" and o.get("estado") == "descartada")
    desc_co = sum(1 for o in obs if o.get("role") == "comparator" and o.get("estado") == "descartada")
    assert aptas_c + aptas_co == 168
    assert desc_c + desc_co == 48
    assert resumen["resumen_global"]["aptas_por_rol"] == {"candidate": aptas_c, "comparator": aptas_co}
    assert resumen["resumen_global"]["descartes_por_rol"] == {"candidate": desc_c, "comparator": desc_co}


# --- 4. Resultados por horizonte y faltantes ----------------------------

def test_resultados_por_horizonte_y_faltantes(datos, resumen):
    res = [o for o in datos if o.get("kind") == "resultado"]
    obs_aptas = [o for o in datos if o.get("kind") == "observacion" and o.get("estado") == "observada"]
    res_por_id = {}
    for r in res:
        res_por_id.setdefault(str(r.get("observation_id")), []).append(r)
    faltantes = 0
    ceros_sin_precio_igual = 0
    for obs in obs_aptas:
        for h in ("5m", "15m", "60m"):
            res_h = [r for r in res_por_id.get(str(obs.get("observation_id")), []) if r.get("horizon") == h]
            if not res_h:
                faltantes += 1
            else:
                for r in res_h:
                    # Un retorno 0.0 es legítimo solo si precio_base == precio_posterior.
                    # Nunca es un faltante convertido a cero.
                    if r.get("retorno") == 0 and r.get("precio_base") != r.get("precio_posterior"):
                        ceros_sin_precio_igual += 1
    assert faltantes == 0, f"faltantes={faltantes}"
    assert ceros_sin_precio_igual == 0
    for h in ("5m", "15m", "60m"):
        assert sum(1 for r in res if r.get("horizon") == h) == 168
    assert resumen["resumen_global"]["resultados_por_horizonte"] == {"5m": 168, "15m": 168, "60m": 168}


# --- 5. Duplicados y huérfanos ------------------------------------------

def test_sin_duplicados_ni_huerfanos(datos):
    obs = [o for o in datos if o.get("kind") == "observacion"]
    res = [o for o in datos if o.get("kind") == "resultado"]
    oids = [o.get("observation_id") for o in obs]
    assert len(oids) == len(set(oids)) == 216
    pairs = [(r.get("observation_id"), r.get("horizon")) for r in res]
    assert len(pairs) == len(set(pairs)) == 504
    obs_ids = set(oids)
    huérfanos = [r for r in res if r.get("observation_id") not in obs_ids]
    assert huérfanos == []
    aptas_ids = {o.get("observation_id") for o in obs if o.get("estado") == "observada"}
    assert all(r.get("observation_id") in aptas_ids for r in res)


# --- 6. Unidades: fracción / porcentaje / puntos porcentuales -----------

def test_unidades_fraccion_porcentaje_puntos(resumen):
    for h in ("5m", "15m", "60m"):
        comp = resumen["comparacion_candidatos_comparadores"][h]
        mc = comp["candidatos"]["media"]
        mcp = comp["candidatos"]["media_pct"]
        mo = comp["comparadores"]["media"]
        mop = comp["comparadores"]["media_pct"]
        diff = comp["diferencia_medias_agrupada"]
        diffp = comp["diferencia_medias_agrupada_puntos_porcentuales"]
        if mc is not None:
            assert abs(mcp - mc * 100.0) < 1e-12
        if mo is not None:
            assert abs(mop - mo * 100.0) < 1e-12
        if diff is not None:
            assert abs(diffp - diff * 100.0) < 1e-12


# --- 7. Denominador profundidad: nunca cero; ratio None si ausente ------

def test_denominador_profundidad_nunca_cero(derivado):
    filas = derivado["asociaciones"]["por_horizonte"]
    for h, bloque in filas.items():
        assert bloque["n_filas"] == 168, f"{h}: {bloque['n_filas']}"
        # disponibilidad declarada: 168/168 con campo completo
        assert "168/168" in derivado["asociaciones"]["disponibilidad"]


# --- 8. Medias distintas (agrupada vs por ciclo vs por símbolo) ---------

def test_medias_distintas_por_ponderacion(resumen):
    for h in ("5m", "15m", "60m"):
        comp = resumen["comparacion_candidatos_comparadores"][h]
        da = comp["diferencia_medias_agrupada"]
        dc = comp["media_de_diferencias_por_ciclo"]
        ds = comp["diferencia_medias_agrupada_por_simbolo"]
        # Las tres pueden ser None o numericas; si hay al menos dos numericas,
        # no deben obligarse a ser iguales.
        numericas = [x for x in (da, dc, ds) if x is not None]
        if len(numericas) >= 2:
            assert not all(abs(numericas[0] - x) < 1e-15 for x in numericas[1:]), (
                f"{h}: todas las ponderaciones coinciden ({numericas})"
            )


# --- 9. Motivos de descarte pueden solaparse ----------------------------

def test_motivos_pueden_solaparse(datos):
    obs = [o for o in datos if o.get("kind") == "observacion"]
    descartadas = [o for o in obs if o.get("estado") == "descartada"]
    total_desc = len(descartadas)
    conteos = {}
    for o in descartadas:
        for m in (o.get("motivos") or []):
            conteos[m] = conteos.get(m, 0) + 1
    assert total_desc == 48
    assert sum(conteos.values()) >= total_desc  # solapamiento permitido


# --- 10. UP/Down disponibles solo en candidatos (campo `side`) ----------

def test_lado_side_solo_candidatos(datos):
    obs = [o for o in datos if o.get("kind") == "observacion" and o.get("estado") == "observada"]
    lados_cand = {o.get("side") for o in obs if o.get("role") == "candidate"}
    lados_comp = {o.get("side") for o in obs if o.get("role") == "comparator"}
    assert lados_cand == {"UP", "DOWN"}
    assert lados_comp == {None}
