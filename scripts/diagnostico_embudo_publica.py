"""Diagnóstico OFFLINE y solo lectura del embudo de la captura pública
public-pilot-1h-20261105a.

Lee únicamente el JSONL del dataset original sin modificarlo. Reconstruye el
embudo por rol (candidate / comparator) sin mezclar ni solapar observaciones
entre roles. Los motivos de descarte pueden solaparse dentro de una misma
observación, pero las observaciones por rol son mutuamente excluyentes.

Salidas:
- Derivados detallados (fuera de Git):
  C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\derivados\embudo\diagnostico_embudo.json
- Tablas pequeñas (Git):
  docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas/embudo_publica.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DATASET_JSONL = Path(
    r"C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\observaciones.jsonl"
)
DERIVADOS_DETALLADOS = Path(
    r"C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\derivados\embudo"
)
TABLAS_GIT = Path(
    r"docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas"
)

ROLES = ("candidate", "comparator")
ESTADO_OBSERVADA = "observada"
ESTADO_DESCARTADA = "descartada"


def _cargar_jsonl(ruta: Path) -> list[dict[str, Any]]:
    objetos: list[dict[str, Any]] = []
    with open(ruta, "r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            objetos.append(json.loads(linea))
    return objetos


def _seguro_int(valor: Any) -> int | None:
    if valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _seguro_float(valor: Any) -> float | None:
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _tasa(num: int | None, den: int | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def analizar(jsonl: Path = DATASET_JSONL) -> dict[str, Any]:
    objetos = _cargar_jsonl(jsonl)
    ciclos = [o for o in objetos if o.get("kind") == "ciclo"]
    observaciones = [o for o in objetos if o.get("kind") == "observacion"]
    resultados = [o for o in objetos if o.get("kind") == "resultado"]

    # Índice de ciclos por reference_ms (clave precisa para mapear observaciones).
    ciclos_por_ref: dict[int, dict[str, Any]] = {}
    for c in ciclos:
        rm = c.get("reference_ms")
        if isinstance(rm, int):
            ciclos_por_ref[rm] = c
    ciclos_ordenados = sorted(ciclos, key=lambda c: c.get("reference_ms", 0))

    def ciclo_de_observacion(obs: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None]:
        disp = obs.get("disponibilidad") or {}
        sel_ms = disp.get("seleccion_ms")
        if isinstance(sel_ms, int) and sel_ms in ciclos_por_ref:
            c = ciclos_por_ref[sel_ms]
            return ciclos_ordenados.index(c), c
        return None, None

    # ---- Embudo por rol (sin solapamiento entre roles) ----
    seleccionadas_por_rol: dict[str, int] = Counter()
    aptas_por_rol: dict[str, int] = Counter()
    descartadas_por_rol: dict[str, int] = Counter()
    motivos_por_rol: dict[str, Counter] = defaultdict(Counter)

    for obs in observaciones:
        rol = obs.get("role") or "desconocido"
        estado = obs.get("estado")
        seleccionadas_por_rol[rol] += 1
        if estado == ESTADO_OBSERVADA:
            aptas_por_rol[rol] += 1
        elif estado == ESTADO_DESCARTADA:
            descartadas_por_rol[rol] += 1
            for m in (obs.get("motivos") or []):
                motivos_por_rol[rol][m] += 1

    # ---- Diagnóstico de incorporación al seguimiento ----
    # Símbolo -> lista de (ciclo_idx, reference_ms) ordenados por referencia.
    apariciones_por_simbolo: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for obs in observaciones:
        simbolo = obs.get("symbol")
        ciclo_idx, ciclo_obj = ciclo_de_observacion(obs)
        if simbolo is not None and ciclo_idx is not None:
            rm = ciclo_obj.get("reference_ms") if ciclo_obj else None
            apariciones_por_simbolo[simbolo].append((ciclo_idx, rm or 0))
    for simbolo in apariciones_por_simbolo:
        apariciones_por_simbolo[simbolo].sort(key=lambda x: (x[0], x[1]))

    conjunto_simbolos_por_ciclo: dict[int, set[str]] = defaultdict(set)
    for simbolo, apariciones in apariciones_por_simbolo.items():
        for ciclo_idx, _ in apariciones:
            conjunto_simbolos_por_ciclo[ciclo_idx].add(simbolo)

    def condicion_incorporacion(obs: dict[str, Any]) -> str | None:
        """primera_vez / permanece / reincorpora / desconocido."""
        simbolo = obs.get("symbol")
        ciclo_idx, _ = ciclo_de_observacion(obs)
        if simbolo is None or ciclo_idx is None:
            return None
        apariciones = apariciones_por_simbolo.get(simbolo, [])
        # ¿Es esta la primera aparición del símbolo?
        primera = apariciones[0]
        if primera[0] == ciclo_idx:
            return "primera_vez"
        # ¿Apareció en el ciclo anterior inmediato?
        ciclos_simbolo = {c for c, _ in apariciones}
        if (ciclo_idx - 1) in ciclos_simbolo:
            return "permanece"
        # Apareció antes pero no en el ciclo anterior inmediato.
        return "reincorpora"

    # ---- Tabla por rol, condición e horizonte ----
    filas_condicion: list[dict[str, Any]] = []
    detalle_observaciones: list[dict[str, Any]] = []

    # Índice de resultados por observation_id y horizonte.
    resultados_por_id_h: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in resultados:
        oid = r.get("observation_id")
        h = r.get("horizon")
        if oid and h:
            resultados_por_id_h[(str(oid), h)].append(r)

    for obs in observaciones:
        rol = obs.get("role") or "desconocido"
        estado = obs.get("estado")
        simbolo = obs.get("symbol")
        ciclo_idx, ciclo_obj = ciclo_de_observacion(obs)
        condicion = condicion_incorporacion(obs)
        referencia_ms = ciclo_obj.get("reference_ms") if ciclo_obj else None
        referencia_iso = ciclo_obj.get("reference_iso") if ciclo_obj else None
        seleccion = obs.get("seleccion") or {}
        disponibilidad = obs.get("disponibilidad") or {}
        libro = obs.get("libro") or {}
        flujo = obs.get("flujo") or {}
        cobertura = obs.get("cobertura") or {}
        motivos = obs.get("motivos") or []
        decision_ms = obs.get("decision_ms")

        fila: dict[str, Any] = {
            "rol": rol,
            "ciclo_idx": ciclo_idx,
            "referencia_ms": referencia_ms,
            "referencia_iso": referencia_iso,
            "simbolo": simbolo,
            "condicion_incorporacion": condicion,
            "estado": estado,
            "motivos": list(motivos),
            "decision_ms": decision_ms,
            "seleccion_disponibilidad_ms": disponibilidad.get("seleccion_ms"),
            "libro_ms": disponibilidad.get("libro_ms"),
            "flujo_ms": disponibilidad.get("flujo_ms"),
            "disponibilidad_max_ms": disponibilidad.get("max_ms"),
            "libro_event_ms": libro.get("event_ms"),
            "libro_received_ms": libro.get("received_ms"),
            "flujo_event_ms": flujo.get("event_ms"),
            "flujo_received_ms": flujo.get("received_ms"),
            "flujo_ventana_completa": flujo.get("ventana_completa"),
            "libro_banda_5bps_cubierta": cobertura.get("libro_banda_5bps_cubierta"),
            "flujo_ventana_completa_cob": cobertura.get("flujo_ventana_completa"),
        }

        # Tiempo disponible entre incorporación y evaluación, cuando sea
        # acreditable: decision_ms - reference_ms del ciclo de primera
        # aparición del símbolo (inicio del seguimiento del símbolo).
        apariciones_simbolo = apariciones_por_simbolo.get(simbolo, [])
        if apariciones_simbolo and decision_ms is not None:
            primera_referencia = apariciones_simbolo[0][1]
            fila["tiempo_incorporacion_a_evaluacion_ms"] = decision_ms - primera_referencia
        else:
            fila["tiempo_incorporacion_a_evaluacion_ms"] = None

        detalle_observaciones.append(fila)

        # Filas agregadas por condición × rol (sobre observaciones, sin solapamiento).
        if condicion is not None:
            clave = (rol, condicion)
            agregado = next(
                (f for f in filas_condicion
                 if f["rol"] == rol and f["condicion_incorporacion"] == condicion),
                None,
            )
            if agregado is None:
                agregado = {
                    "rol": rol,
                    "condicion_incorporacion": condicion,
                    "seleccionadas": 0,
                    "aptas": 0,
                    "descartadas": 0,
                    "sin_libro": 0,
                    "sin_flujo": 0,
                    "obsoleto_libro": 0,
                    "obsoleto_flujo": 0,
                    "ventana_incompleta": 0,
                    "tiempo_incorporacion_a_evaluacion_ms_validos": 0,
                }
                filas_condicion.append(agregado)
            agregado["seleccionadas"] += 1
            if estado == ESTADO_OBSERVADA:
                agregado["aptas"] += 1
            elif estado == ESTADO_DESCARTADA:
                agregado["descartadas"] += 1
            if fila["libro_ms"] is None:
                agregado["sin_libro"] += 1
            if fila["flujo_ms"] is None:
                agregado["sin_flujo"] += 1
            if "dato_obsoleto_libro" in motivos:
                agregado["obsoleto_libro"] += 1
            if "dato_obsoleto_flujo" in motivos:
                agregado["obsoleto_flujo"] += 1
            if not cobertura.get("flujo_ventana_completa"):
                agregado["ventana_incompleta"] += 1
            if fila["tiempo_incorporacion_a_evaluacion_ms"] is not None:
                agregado["tiempo_incorporacion_a_evaluacion_ms_validos"] += 1

    filas_condicion.sort(key=lambda f: (f["rol"], f["condicion_incorporacion"]))

    # ---- Resultados por rol y horizonte (para tasas de cobertura) ----
    resultados_por_rol_h: dict[tuple[str, str], int] = Counter()
    for obs in observaciones:
        if obs.get("estado") != ESTADO_OBSERVADA:
            continue
        rol = obs.get("role") or "desconocido"
        oid = obs.get("observation_id")
        for h in ("5m", "15m", "60m"):
            if resultados_por_id_h.get((str(oid), h)):
                resultados_por_rol_h[(rol, h)] += 1

    # ---- Tasas de cobertura ----
    aptas_candidate = aptas_por_rol.get("candidate", 0)
    aptas_comparator = aptas_por_rol.get("comparator", 0)
    sel_candidate = seleccionadas_por_rol.get("candidate", 0)
    sel_comparator = seleccionadas_por_rol.get("comparator", 0)

    tasas_cobertura = {
        "candidate": {
            "seleccionadas": sel_candidate,
            "aptas": aptas_candidate,
            "descartadas": descartadas_por_rol.get("candidate", 0),
            "resultados_5m": resultados_por_rol_h.get(("candidate", "5m"), 0),
            "resultados_15m": resultados_por_rol_h.get(("candidate", "15m"), 0),
            "resultados_60m": resultados_por_rol_h.get(("candidate", "60m"), 0),
            "tasa_5m_sobre_aptas": _tasa(resultados_por_rol_h.get(("candidate", "5m"), 0), aptas_candidate),
            "tasa_15m_sobre_aptas": _tasa(resultados_por_rol_h.get(("candidate", "15m"), 0), aptas_candidate),
            "tasa_5m_sobre_seleccionadas": _tasa(resultados_por_rol_h.get(("candidate", "5m"), 0), sel_candidate),
            "tasa_15m_sobre_seleccionadas": _tasa(resultados_por_rol_h.get(("candidate", "15m"), 0), sel_candidate),
        },
        "comparator": {
            "seleccionadas": sel_comparator,
            "aptas": aptas_comparator,
            "descartadas": descartadas_por_rol.get("comparator", 0),
            "resultados_5m": resultados_por_rol_h.get(("comparator", "5m"), 0),
            "resultados_15m": resultados_por_rol_h.get(("comparator", "15m"), 0),
            "resultados_60m": resultados_por_rol_h.get(("comparator", "60m"), 0),
            "tasa_5m_sobre_aptas": _tasa(resultados_por_rol_h.get(("comparator", "5m"), 0), aptas_comparator),
            "tasa_15m_sobre_aptas": _tasa(resultados_por_rol_h.get(("comparator", "15m"), 0), aptas_comparator),
            "tasa_5m_sobre_seleccionadas": _tasa(resultados_por_rol_h.get(("comparator", "5m"), 0), sel_comparator),
            "tasa_15m_sobre_seleccionadas": _tasa(resultados_por_rol_h.get(("comparator", "15m"), 0), sel_comparator),
        },
    }

    # ---- Comprobación de consistencia (impedir publicar totales contradictorios) ----
    total_seleccionadas = seleccionadas_por_rol.get("candidate", 0) + seleccionadas_por_rol.get("comparator", 0)
    total_aptas = aptas_por_rol.get("candidate", 0) + aptas_por_rol.get("comparator", 0)
    total_descartadas = descartadas_por_rol.get("candidate", 0) + descartadas_por_rol.get("comparator", 0)
    total_observaciones = len(observaciones)
    consistencia = {
        "seleccionadas_por_rol_suma_coincide_total": total_seleccionadas == total_observaciones,
        "aptas_por_rol_suma_coincide_total": total_aptas == total_observaciones - total_descartadas,
        "descartadas_por_rol_suma_coincide_total": total_descartadas == total_observaciones - total_aptas,
        "candidate_seleccionadas": seleccionadas_por_rol.get("candidate", 0),
        "candidate_aptas": aptas_por_rol.get("candidate", 0),
        "candidate_descartadas": descartadas_por_rol.get("candidate", 0),
        "comparator_seleccionadas": seleccionadas_por_rol.get("comparator", 0),
        "comparator_aptas": aptas_por_rol.get("comparator", 0),
        "comparator_descartadas": descartadas_por_rol.get("comparator", 0),
        "total_observaciones": total_observaciones,
        "total_aptas": total_aptas,
        "total_descartadas": total_descartadas,
        "motivos_pueden_solaparse": True,
        "roles_no_se_solapan": True,
    }

    # ---- Descartes de comparadores por motivo (para diagnóstico) ----
    descartes_comparador_por_motivo = dict(motivos_por_rol.get("comparator", Counter()))
    descartes_candidate_por_motivo = dict(motivos_por_rol.get("candidate", Counter()))

    # ---- Resumen por símbolo: primera aparición, rol por ciclo ----
    primer_ciclo_por_simbolo: dict[str, int | None] = {}
    roles_por_simbolo_ciclo: dict[tuple[str, int], str] = {}
    for obs in observaciones:
        simbolo = obs.get("symbol")
        ciclo_idx, _ = ciclo_de_observacion(obs)
        if simbolo is None or ciclo_idx is None:
            continue
        clave = (simbolo, ciclo_idx)
        roles_por_simbolo_ciclo[clave] = obs.get("role") or "desconocido"
        actual = primer_ciclo_por_simbolo.get(simbolo)
        if actual is None or ciclo_idx < actual:
            primer_ciclo_por_simbolo[simbolo] = ciclo_idx

    simbolos_cambian_rol: list[str] = []
    roles_distintos_por_simbolo: dict[str, set[str]] = defaultdict(set)
    for (simbolo, ciclo_idx), rol in roles_por_simbolo_ciclo.items():
        roles_distintos_por_simbolo[simbolo].add(rol)
    for simbolo, roles in roles_distintos_por_simbolo.items():
        if len(roles) > 1:
            simbolos_cambian_rol.append(simbolo)

    return {
        "total_lineas": len(objetos),
        "ciclos": len(ciclos),
        "observaciones_total": total_observaciones,
        "seleccionadas_por_rol": dict(seleccionadas_por_rol),
        "aptas_por_rol": dict(aptas_por_rol),
        "descartadas_por_rol": dict(descartadas_por_rol),
        "resultados_por_rol_horizonte": {f"{k[0]}|{k[1]}": v for k, v in resultados_por_rol_h.items()},
        "tasas_cobertura": tasas_cobertura,
        "consistencia": consistencia,
        "motivos_por_rol": {k: dict(v) for k, v in motivos_por_rol.items()},
        "descartes_comparador_por_motivo": descartes_comparador_por_motivo,
        "descartes_candidate_por_motivo": descartes_candidate_por_motivo,
        "filas_condicion": filas_condicion,
        "detalle_observaciones": detalle_observaciones,
        "primer_ciclo_por_simbolo": primer_ciclo_por_simbolo,
        "simbolos_cambian_rol": simbolos_cambian_rol,
        "n_simbolos_distintos": len(primer_ciclo_por_simbolo),
        "nota_consistencia": (
            "Los totales por rol (candidate + comparator) deben coincidir con el total de "
            "observaciones del JSONL. Los motivos de descarte pueden solaparse dentro de una "
            "misma observación; las observaciones por rol no se solapan."
        ),
    }


def _escribir_json(ruta: Path, datos: Any) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico de embudo de captura pública.")
    parser.add_argument("--jsonl", default=str(DATASET_JSONL), help="Ruta del JSONL del dataset.")
    args = parser.parse_args()

    jsonl = Path(args.jsonl)
    res = analizar(jsonl)

    # Comprobación de consistencia: si falla, no se publica nada.
    c = res["consistencia"]
    assert c["seleccionadas_por_rol_suma_coincide_total"], "Totales de seleccionadas por rol contradictorios"
    assert c["aptas_por_rol_suma_coincide_total"], "Totales de aptas por rol contradictorios"
    assert c["descartadas_por_rol_suma_coincide_total"], "Totales de descartadas por rol contradictorios"

    # Derivados detallados fuera de Git.
    _escribir_json(DERIVADOS_DETALLADOS / "diagnostico_embudo.json", res)

    # Tablas pequeñas para Git.
    tablas_publicar = {
        "run_id": "public-pilot-1h-20261105a",
        "estado_corrida": "corrida_interrumpida_o_cierre_no_acreditado",
        "causa_parada": "UNKNOWN",
        "embudo_por_rol": {
            "seleccionadas_por_rol": res["seleccionadas_por_rol"],
            "aptas_por_rol": res["aptas_por_rol"],
            "descartadas_por_rol": res["descartadas_por_rol"],
            "total_observaciones": res["consistencia"]["total_observaciones"],
            "total_aptas": res["consistencia"]["total_aptas"],
            "total_descartadas": res["consistencia"]["total_descartadas"],
        },
        "tasas_cobertura": res["tasas_cobertura"],
        "consistencia": res["consistencia"],
        "motivos_por_rol": res["motivos_por_rol"],
        "descartes_comparador_por_motivo": res["descartes_comparador_por_motivo"],
        "descartes_candidate_por_motivo": res["descartes_candidate_por_motivo"],
        "cobertura_por_condicion_rol": res["filas_condicion"],
        "n_simbolos_distintos": res["n_simbolos_distintos"],
        "simbolos_cambian_rol": res["simbolos_cambian_rol"],
        "nota": res["nota_consistencia"],
    }
    _escribir_json(TABLAS_GIT / "embudo_publica.json", tablas_publicar)
    print("Diagnóstico de embudo escrito en", DERIVADOS_DETALLADOS / "diagnostico_embudo.json")
    print("Tabla pequeña para Git escrita en", TABLAS_GIT / "embudo_publica.json")
    print(json.dumps(tablas_publicar["embudo_por_rol"], ensure_ascii=False, indent=2))
    print(json.dumps(tablas_publicar["tasas_cobertura"], ensure_ascii=False, indent=2))
    print(json.dumps(tablas_publicar["consistencia"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
