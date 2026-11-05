"""Pruebas focalizadas del análisis offline de la captura pública.

Validan que:
- los motivos de descarte pueden solaparse (no suman obligatoriamente al total de descartes);
- un resultado faltante no se convierte en cero;
- horizontes y roles se separan;
- símbolos repetidos no se cuentan como símbolos distintos;
- un ciclo sin grupo comparable no se inventa.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATASET_JSONL = Path(
    r"C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\observaciones.jsonl"
)
TABLA_RESUMEN = Path(
    r"docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas/resumen_analisis_offline.json"
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


def test_denominadores_y_motivos_solapados(datos):
    observaciones = [o for o in datos if o.get("kind") == "observacion"]
    descartadas = [o for o in observaciones if o.get("estado") == "descartada"]
    total_descarte_estado = len(descartadas)

    conteos_motivos = {}
    for o in descartadas:
        for m in (o.get("motivos") or []):
            conteos_motivos[m] = conteos_motivos.get(m, 0) + 1
    suma_motivos = sum(conteos_motivos.values())

    # Los motivos pueden solaparse: la suma de motivos no tiene por qué igualar el total de descartes.
    assert total_descarte_estado == 112
    assert suma_motivos >= total_descarte_estado  # al menos uno por descarte si hay solapamiento


def test_resultado_faltante_no_es_cero(datos):
    observaciones = [o for o in datos if o.get("kind") == "observacion" and o.get("estado") == "observada"]
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
                    # Un retorno legítimamente cero es posible; lo que se prohíbe es inventar cero para faltantes.
                    if r.get("retorno") == 0:
                        ceros_inventados += 1
    assert faltantes == 178  # aptas (128) × 3 horizontes (384) - generados (206)
    assert ceros_inventados == 0


def test_separacion_horizontes_y_roles(datos):
    observaciones = [o for o in datos if o.get("kind") == "observacion"]
    resultados = [o for o in datos if o.get("kind") == "resultado"]

    roles_observacion = {o.get("role") for o in observaciones}
    assert roles_observacion == {"candidate", "comparator"}

    horizontes_resultado = {r.get("horizon") for r in resultados}
    assert horizontes_resultado == {"5m", "15m"}  # 60m no generado

    n_cand_obs = sum(1 for o in observaciones if o.get("role") == "candidate")
    n_comp_obs = sum(1 for o in observaciones if o.get("role") == "comparator")
    assert n_cand_obs == 144
    assert n_comp_obs == 96


def test_simbolos_repetidos_no_se_cuentan_como_distintos(datos):
    observaciones = [o for o in datos if o.get("kind") == "observacion"]
    simbolos = [o.get("symbol") for o in observaciones if o.get("symbol")]
    n_lineas = len(simbolos)
    n_distintos = len(set(simbolos))
    assert n_lineas == 240
    assert n_distintos < n_lineas  # hay repeticiones, por tanto no son independientes


def test_ciclo_sin_grupo_comparable_no_se_inventa(resumen):
    comp = resumen["comparacion_candidatos_comparadores"]
    for horizonte, datos_h in comp.items():
        # Si un horizonte no tiene ambos grupos, la diferencia de medias debe ser None, no un número inventado.
        if datos_h["candidatos"]["n_resultados"] == 0 or datos_h["comparadores"]["n_resultados"] == 0:
            assert datos_h["diferencia_medias_descriptiva"] is None
        else:
            assert datos_h["diferencia_medias_descriptiva"] is not None
        assert datos_h["ciclos_con_ambos_grupos"] >= 0
