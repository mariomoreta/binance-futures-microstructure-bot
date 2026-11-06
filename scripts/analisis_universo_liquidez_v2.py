"""Análisis OFFLINE y solo lectura de la captura pública public-pilot-1h-20261106a.

Versión identificable v2 del bloque research/universe-liquidez-v1. Corrige
afirmaciones no respaldadas del análisis anterior y determina cuánto depende
la diferencia candidatos/comparadores de la cobertura y de símbolos concretos.

Reconstruye la selección desde los registros de ciclo (kind="ciclo", campos
`selected` y `comparator`) y la separa de las observaciones emitidas
(kind="observacion"). Distingue ciclo de selección (reference_ms) y ciclo de
decisión (decision_ms).

Lee únicamente el JSONL del dataset original sin modificarlo. No conecta a
Binance, no adquiere datos nuevos, no cambia reglas ni tolerancias.

Argumentos explícitos:
  --jsonl        Ruta del JSONL del dataset (obligatorio).
  --out-derivados Directorio de derivados detallados (fuera de Git).
  --out-tablas   Directorio de tablas pequeñas para Git.
  --run_id       Identificador de corrida (se publica en las tablas).

Código de salida del proceso: se mantiene UNKNOWN (no recuperable
retrospectivamente). neto_estado se mantiene UNKNOWN donde no existan costes
ni ejecución acreditados.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HORIZONTES = ("5m", "15m", "60m")
HORIZONTES_EVALUABLES = ("5m", "15m", "60m")
ROLES = ("candidate", "comparator")
LADOS = ("UP", "DOWN")


def _cargar_jsonl(ruta: Path) -> list[dict[str, Any]]:
    objetos: list[dict[str, Any]] = []
    with open(ruta, "r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            objetos.append(json.loads(linea))
    return objetos


def _seguro_float(valor: Any) -> float | None:
    if valor is None:
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _stats(valores: list[float]) -> dict[str, float | None]:
    limpios = [v for v in valores if v is not None and math.isfinite(v)]
    if not limpios:
        return {"n": 0, "media": None, "mediana": None, "desv": None, "min": None, "max": None}
    n = len(limpios)
    return {
        "n": n,
        "media": statistics.fmean(limpios),
        "mediana": statistics.median(limpios),
        "desv": statistics.pstdev(limpios) if n > 1 else 0.0,
        "min": min(limpios),
        "max": max(limpios),
    }


def _pct(valor: float | None) -> float | None:
    if valor is None:
        return None
    return valor * 100.0


def _lado_desde_side(obs: dict[str, Any]) -> str | None:
    """Clasificación disponible al seleccionar: campo `side` (UP/DOWN)."""
    lado = obs.get("side")
    if lado in LADOS:
        return lado
    return None


def _indexar(objetos: list[dict[str, Any]]) -> dict[str, Any]:
    """Indexa ciclos, observaciones y resultados; reconstruye selección desde ciclos."""
    ciclos = [o for o in objetos if o.get("kind") == "ciclo"]
    observaciones = [o for o in objetos if o.get("kind") == "observacion"]
    resultados = [o for o in objetos if o.get("kind") == "resultado"]

    ciclos_ordenados = sorted(ciclos, key=lambda c: c.get("reference_ms", 0))
    ciclos_por_ref: dict[int, dict[str, Any]] = {}
    for c in ciclos_ordenados:
        ref = c.get("reference_ms")
        if isinstance(ref, int):
            ciclos_por_ref[ref] = c

    # Ciclos de decisión ordenados por decision_ms (momento de evaluación),
    # obtenido de las observaciones (cada ciclo tiene un decision_ms único).
    decision_ms_ordenados = sorted(
        {o.get("decision_ms") for o in observaciones if isinstance(o.get("decision_ms"), int)}
    )

    # Selección por ciclo (reference_ms) y rol: símbolos seleccionados.
    seleccion_por_ciclo_rol: dict[int, dict[str, list[str]]] = {}
    seleccion_simbolo_rol_por_ciclo: dict[int, dict[str, str]] = {}
    seleccionados_por_ciclo_rol: dict[int, dict[str, int]] = {}
    for c in ciclos_ordenados:
        ref = c.get("reference_ms")
        rol_map: dict[str, list[str]] = {"candidate": [], "comparator": []}
        simbolo_rol: dict[str, str] = {}
        n_por_rol: dict[str, int] = {"candidate": 0, "comparator": 0}
        for entry in (c.get("selected") or []):
            sym = entry.get("symbol")
            if sym:
                rol_map["candidate"].append(sym)
                simbolo_rol[sym] = "candidate"
                n_por_rol["candidate"] += 1
        for entry in (c.get("comparator") or []):
            sym = entry.get("symbol")
            if sym:
                rol_map["comparator"].append(sym)
                simbolo_rol[sym] = "comparator"
                n_por_rol["comparator"] += 1
        if isinstance(ref, int):
            seleccion_por_ciclo_rol[ref] = rol_map
            seleccion_simbolo_rol_por_ciclo[ref] = simbolo_rol
            seleccionados_por_ciclo_rol[ref] = n_por_rol

    # Índice de resultados por observation_id.
    resultados_por_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in resultados:
        oid = r.get("observation_id")
        if oid:
            resultados_por_id[str(oid)].append(r)

    def ciclo_de_observacion(
        obs: dict[str, Any],
    ) -> tuple[int | None, dict[str, Any] | None, str | None]:
        """Devuelve (índice de ciclo de selección, objeto ciclo, motivo de vínculo).

        El vínculo selecciÃ³nÂ→decisión se construye sobre el identificador
        persistido: observacion.disponibilidad.seleccion_ms == ciclo.reference_ms.
        Nunca se usa orden cronológico ni proximidad temporal.
        """
        disp = obs.get("disponibilidad") or {}
        sel_ms = disp.get("seleccion_ms")
        if isinstance(sel_ms, int) and sel_ms in ciclos_por_ref:
            return ciclos_ordenados.index(ciclos_por_ref[sel_ms]), ciclos_por_ref[sel_ms], None
        # Observación sin vínculo acreditado a un ciclo de selección.
        return None, None, "sin_vinculo_seleccion"

    def pertenece_a_seleccion(
        obs: dict[str, Any], ciclo: dict[str, Any] | None
    ) -> tuple[bool, str | None]:
        """Verifica que el símbolo y rol de la observación estén en la selección
        del ciclo vinculado. Devuelve (pertenece, motivo)."""
        if ciclo is None:
            return False, "sin_ciclo_vinculado"
        disp = obs.get("disponibilidad") or {}
        sel_ms = disp.get("seleccion_ms")
        rol = obs.get("role")
        sym = obs.get("symbol")
        if not isinstance(sel_ms, int) or sel_ms not in seleccion_por_ciclo_rol:
            return False, "seleccion_no_encontrada_para_ciclo"
        simbolos_rol = seleccion_por_ciclo_rol[sel_ms].get(rol, [])
        if sym not in simbolos_rol:
            return (
                False,
                "simbolo_no_en_rol_seleccionado",
            )
        return True, None

    return {
        "ciclos": ciclos_ordenados,
        "ciclos_por_ref": ciclos_por_ref,
        "observaciones": observaciones,
        "resultados": resultados,
        "decision_ms_ordenados": decision_ms_ordenados,
        "seleccion_por_ciclo_rol": seleccion_por_ciclo_rol,
        "seleccion_simbolo_rol_por_ciclo": seleccion_simbolo_rol_por_ciclo,
        "seleccionados_por_ciclo_rol": seleccionados_por_ciclo_rol,
        "resultados_por_id": resultados_por_id,
        "ciclo_de_observacion": ciclo_de_observacion,
        "pertenece_a_seleccion": pertenece_a_seleccion,
    }


def analizar(jsonl: Path, run_id: str | None = None) -> dict[str, Any]:
    """Ejecuta el análisis completo y devuelve un dict serializable."""
    objetos = _cargar_jsonl(jsonl)
    idx = _indexar(objetos)
    ciclos = idx["ciclos"]
    observaciones = idx["observaciones"]
    resultados = idx["resultados"]
    decision_ms_ordenados = idx["decision_ms_ordenados"]
    seleccion_por_ciclo_rol = idx["seleccion_por_ciclo_rol"]
    seleccion_simbolo_rol_por_ciclo = idx["seleccion_simbolo_rol_por_ciclo"]
    resultados_por_id = idx["resultados_por_id"]
    ciclo_de_observacion = idx["ciclo_de_observacion"]

    # ============ Embudo reconstruido desde registros de ciclo ============
    # Cada ciclo de selección (reference_ms) declara cuántos símbolos se
    # seleccionaron por rol. Las observaciones (decision_ms) son lo que se
    # emitió realmente. La diferencia son selecciones sin observación.
    filas_embudo: list[dict[str, Any]] = []
    total_seleccionados = 0
    total_seleccionados_por_rol: dict[str, int] = {"candidate": 0, "comparator": 0}
    total_observadas = 0
    total_sin_observacion = 0

    # Vínculo selección→decisión sobre el identificador persistido:
    # observacion.disponibilidad.seleccion_ms == ciclo.reference_ms.
    # Nunca se usa orden cronológico ni proximidad temporal.
    observaciones_por_ciclo_rol: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    observaciones_sin_vinculo: list[dict[str, Any]] = []
    for o in observaciones:
        ciclo_idx, ciclo_obj, motivo_vinculo = ciclo_de_observacion(o)
        if ciclo_idx is None:
            observaciones_sin_vinculo.append(o)
            continue
        ref = ciclo_obj.get("reference_ms")
        rol = o.get("role") or "desconocido"
        observaciones_por_ciclo_rol[ref][rol].append(o)

    filas_embudo: list[dict[str, Any]] = []
    total_seleccionados = 0
    total_seleccionados_por_rol: dict[str, int] = {"candidate": 0, "comparator": 0}
    total_observadas = 0
    total_sin_observacion = 0

    for i, c in enumerate(ciclos):
        ref = c.get("reference_ms")
        ciclo_idx = i

        sel_rol = seleccion_por_ciclo_rol.get(ref, {"candidate": [], "comparator": []}) if isinstance(ref, int) else {"candidate": [], "comparator": []}
        for rol in ROLES:
            n_sel = len(sel_rol.get(rol, []))
            total_seleccionados += n_sel
            total_seleccionados_por_rol[rol] += n_sel
            # observaciones emitidas vinculadas a este ciclo de selección y rol
            obs_rol = observaciones_por_ciclo_rol.get(ref, {}).get(rol, [])
            n_emit = len(obs_rol)
            n_aptas = sum(1 for o in obs_rol if o.get("estado") == "observada")
            n_desc = sum(1 for o in obs_rol if o.get("estado") == "descartada")
            total_observadas += n_emit
            total_sin_observacion += (n_sel - n_emit)
            # motivos de descarte (pueden solaparse)
            motivos = Counter()
            for o in obs_rol:
                if o.get("estado") == "descartada":
                    for m in (o.get("motivos") or []):
                        motivos[m] += 1
            # cobertura de resultados por horizonte
            cov_h = {}
            for h in HORIZONTES:
                n_res = 0; n_falt = 0
                for o in obs_rol:
                    if o.get("estado") != "observada":
                        continue
                    oid = str(o.get("observation_id"))
                    rh = [r for r in resultados_por_id.get(oid, []) if r.get("horizon") == h]
                    if rh:
                        n_res += 1
                    else:
                        n_falt += 1
                cov_h[h] = {"resultado_registrado": n_res, "resultado_faltante": n_falt}
            # decision_ms del ciclo (momento de evaluación) para referencia informativa
            dm = None
            if isinstance(ref, int) and c.get("decision_ms") is not None:
                dm = c.get("decision_ms")
            filas_embudo.append({
                "ciclo_idx": ciclo_idx,
                "reference_ms": ref,
                "decision_ms": dm,
                "rol": rol,
                "seleccionados": n_sel,
                "observaciones_emitidas": n_emit,
                "seleccion_sin_observacion": n_sel - n_emit,
                "aptas": n_aptas,
                "descartadas": n_desc,
                "motivos_descartes": dict(motivos),
                "cobertura_por_horizonte": cov_h,
                "simbolos_seleccionados": list(sel_rol.get(rol, [])),
            })

    # ============ Comparación candidatos vs comparadores por horizonte ============
    def grupo_retornos(h: str, rol: str) -> list[dict[str, Any]]:
        filas = []
        for obs in observaciones:
            if obs.get("role") != rol or obs.get("estado") != "observada":
                continue
            oid = str(obs.get("observation_id"))
            ciclo_idx, _, _ = ciclo_de_observacion(obs)
            for r in resultados_por_id.get(oid, []):
                if r.get("horizon") != h:
                    continue
                retorno = _seguro_float(r.get("retorno"))
                if retorno is None:
                    continue
                filas.append({
                    "simbolo": obs.get("symbol"),
                    "ciclo_idx": ciclo_idx,
                    "decision_ms": obs.get("decision_ms"),
                    "retorno": retorno,
                    "observation_id": oid,
                    "lado": _lado_desde_side(obs),
                    "precio_base": r.get("precio_base"),
                    "precio_posterior": r.get("precio_posterior"),
                    "precio_base_fuente": r.get("precio_base_fuente"),
                    "precio_posterior_fuente": r.get("precio_posterior_fuente"),
                    "horizonte_efectivo_ms": r.get("horizonte_efectivo_ms"),
                })
        return filas

    comparacion_por_horizonte: dict[str, dict[str, Any]] = {}
    for h in HORIZONTES_EVALUABLES:
        filas_cand = grupo_retornos(h, "candidate")
        filas_comp = grupo_retornos(h, "comparator")
        grupo_cand = [f["retorno"] for f in filas_cand]
        grupo_comp = [f["retorno"] for f in filas_comp]
        simbolos_cand = {f["simbolo"] for f in filas_cand if f["simbolo"]}
        simbolos_comp = {f["simbolo"] for f in filas_comp if f["simbolo"]}
        ciclos_cand = {f["ciclo_idx"] for f in filas_cand if f["ciclo_idx"] is not None}
        ciclos_comp = {f["ciclo_idx"] for f in filas_comp if f["ciclo_idx"] is not None}
        ciclos_comunes = ciclos_cand & ciclos_comp

        # Comparadores aptos por ciclo (para destacar ciclos con uno solo)
        comp_aptos_por_ciclo: dict[int, int] = {}
        for ci in sorted(ciclos_comp):
            comp_aptos_por_ciclo[ci] = sum(1 for f in filas_comp if f["ciclo_idx"] == ci)

        # Diferencia por ciclo (mismo peso a cada ciclo con ambos grupos).
        diferencias_por_ciclo: list[dict[str, Any]] = []
        for ci in sorted(ciclos_comunes):
            cand_ci = [f["retorno"] for f in filas_cand if f["ciclo_idx"] == ci]
            comp_ci = [f["retorno"] for f in filas_comp if f["ciclo_idx"] == ci]
            if cand_ci and comp_ci:
                mc = statistics.fmean(cand_ci)
                mco = statistics.fmean(comp_ci)
                diferencias_por_ciclo.append({
                    "ciclo_idx": ci,
                    "n_candidatos": len(cand_ci),
                    "n_comparadores": len(comp_ci),
                    "media_candidatos": mc,
                    "media_candidatos_pct": _pct(mc),
                    "media_comparadores": mco,
                    "media_comparadores_pct": _pct(mco),
                    "diferencia_ciclo": mc - mco,
                    "diferencia_ciclo_puntos_porcentuales": _pct(mc - mco),
                })

        media_diferencias_por_ciclo = None
        media_diferencias_por_ciclo_puntos = None
        if diferencias_por_ciclo:
            diffs = [d["diferencia_ciclo"] for d in diferencias_por_ciclo]
            media_diferencias_por_ciclo = statistics.fmean(diffs)
            media_diferencias_por_ciclo_puntos = _pct(media_diferencias_por_ciclo)

        st_cand = _stats(grupo_cand)
        st_comp = _stats(grupo_comp)
        diff_agrupada = None
        diff_agrupada_puntos = None
        if st_cand["media"] is not None and st_comp["media"] is not None:
            diff_agrupada = st_cand["media"] - st_comp["media"]
            diff_agrupada_puntos = _pct(diff_agrupada)

        # Ponderación igual por símbolo: promedio de medias por símbolo.
        def media_por_simbolo(filas: list[dict[str, Any]]) -> float | None:
            por_simb: dict[str, list[float]] = defaultdict(list)
            for f in filas:
                if f["simbolo"]:
                    por_simb[f["simbolo"]].append(f["retorno"])
            medias = [statistics.fmean(v) for v in por_simb.values() if v]
            return statistics.fmean(medias) if medias else None

        media_cand_por_simbolo = media_por_simbolo(filas_cand)
        media_comp_por_simbolo = media_por_simbolo(filas_comp)

        # UP / DOWN por separado (solo candidatos, clasificación `side`).
        updown: dict[str, dict[str, Any]] = {}
        for lado in LADOS:
            vals = [f["retorno"] for f in filas_cand if f["lado"] == lado]
            st = _stats(vals)
            updown[lado] = {
                "n": st["n"],
                "media": st["media"],
                "media_pct": _pct(st["media"]),
                "mediana": st["mediana"],
                "mediana_pct": _pct(st["mediana"]),
                "desv": st["desv"],
                "min": st["min"],
                "min_pct": _pct(st["min"]),
                "max": st["max"],
                "max_pct": _pct(st["max"]),
                "proporcion_positivos": (
                    sum(1 for v in vals if v > 0) / len(vals) if vals else None
                ),
            }

        comparacion_por_horizonte[h] = {
            "candidatos": {
                "n_resultados": len(grupo_cand),
                "n_simbolos": len(simbolos_cand),
                "n_ciclos": len(ciclos_cand),
                **st_cand,
                "media_pct": _pct(st_cand["media"]),
                "mediana_pct": _pct(st_cand["mediana"]),
                "min_pct": _pct(st_cand["min"]),
                "max_pct": _pct(st_cand["max"]),
                "proporcion_positivos": (
                    sum(1 for v in grupo_cand if v > 0) / len(grupo_cand) if grupo_cand else None
                ),
                "media_por_simbolo": media_cand_por_simbolo,
                "media_por_simbolo_pct": _pct(media_cand_por_simbolo),
            },
            "comparadores": {
                "n_resultados": len(grupo_comp),
                "n_simbolos": len(simbolos_comp),
                "n_ciclos": len(ciclos_comp),
                **st_comp,
                "media_pct": _pct(st_comp["media"]),
                "mediana_pct": _pct(st_comp["mediana"]),
                "min_pct": _pct(st_comp["min"]),
                "max_pct": _pct(st_comp["max"]),
                "proporcion_positivos": (
                    sum(1 for v in grupo_comp if v > 0) / len(grupo_comp) if grupo_comp else None
                ),
                "media_por_simbolo": media_comp_por_simbolo,
                "media_por_simbolo_pct": _pct(media_comp_por_simbolo),
            },
            "diferencia_medias_agrupada": diff_agrupada,
            "diferencia_medias_agrupada_puntos_porcentuales": diff_agrupada_puntos,
            "diferencia_medias_agrupada_por_simbolo": (
                (media_cand_por_simbolo - media_comp_por_simbolo)
                if (media_cand_por_simbolo is not None and media_comp_por_simbolo is not None)
                else None
            ),
            "media_de_diferencias_por_ciclo": media_diferencias_por_ciclo,
            "media_de_diferencias_por_ciclo_puntos_porcentuales": media_diferencias_por_ciclo_puntos,
            "ciclos_con_ambos_grupos": len(ciclos_comunes),
            "ciclos_sin_grupo_comparable": sorted(
                (ciclos_cand | ciclos_comp) - ciclos_comunes
            ),
            "comp_aptos_por_ciclo": {str(k): v for k, v in sorted(comp_aptos_por_ciclo.items())},
            "ciclos_con_un_solo_comparador": sorted(
                [ci for ci, v in comp_aptos_por_ciclo.items() if v == 1]
            ),
            "updown_candidatos": updown,
        }

    # ============ Sensibilidad por símbolo (exclusión uno por uno) ============
    def _comparacion_para_conjunto(
        filas_cand: list[dict[str, Any]], filas_comp: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Calcula medias y diferencia para un conjunto dado de filas (ya filtradas)."""
        grupo_cand = [f["retorno"] for f in filas_cand]
        grupo_comp = [f["retorno"] for f in filas_comp]
        st_cand = _stats(grupo_cand)
        st_comp = _stats(grupo_comp)
        diff = None
        diff_puntos = None
        if st_cand["media"] is not None and st_comp["media"] is not None:
            diff = st_cand["media"] - st_comp["media"]
            diff_puntos = _pct(diff)
        return {
            "candidatos_n": len(grupo_cand),
            "candidatos_media": st_cand["media"],
            "candidatos_media_pct": _pct(st_cand["media"]),
            "comparadores_n": len(grupo_comp),
            "comparadores_media": st_comp["media"],
            "comparadores_media_pct": _pct(st_comp["media"]),
            "diferencia": diff,
            "diferencia_puntos_porcentuales": diff_puntos,
        }

    # Índice de retornos por símbolo y horizonte (sobre observaciones aptas con resultado).
    retornos_por_simbolo_h: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for h in HORIZONTES_EVALUABLES:
        for obs in observaciones:
            if obs.get("role") not in ROLES or obs.get("estado") != "observada":
                continue
            oid = str(obs.get("observation_id"))
            for r in resultados_por_id.get(oid, []):
                if r.get("horizon") != h:
                    continue
                retorno = _seguro_float(r.get("retorno"))
                if retorno is None:
                    continue
                sym = obs.get("symbol") or "desconocido"
                rol = obs.get("role")
                retornos_por_simbolo_h[sym][h][rol].append(retorno)

    simbolos_ordenados = sorted(retornos_por_simbolo_h.keys())
    sensibilidad_por_simbolo: list[dict[str, Any]] = []
    diferencia_base_por_h: dict[str, float | None] = {}
    for h in HORIZONTES_EVALUABLES:
        base_cand = []
        base_comp = []
        for obs in observaciones:
            if obs.get("estado") != "observada":
                continue
            oid = str(obs.get("observation_id"))
            for r in resultados_por_id.get(oid, []):
                if r.get("horizon") != h:
                    continue
                retorno = _seguro_float(r.get("retorno"))
                if retorno is None:
                    continue
                if obs.get("role") == "candidate":
                    base_cand.append(retorno)
                elif obs.get("role") == "comparator":
                    base_comp.append(retorno)
        base = _comparacion_para_conjunto(
            [{"retorno": v} for v in base_cand],
            [{"retorno": v} for v in base_comp],
        )
        diferencia_base_por_h[h] = base["diferencia"]

    for sym in simbolos_ordenados:
        entrada: dict[str, Any] = {"simbolo": sym, "por_horizonte": {}}
        for h in HORIZONTES_EVALUABLES:
            # Construir conjuntos excluyendo este símbolo.
            filas_cand: list[dict[str, Any]] = []
            filas_comp: list[dict[str, Any]] = []
            for obs in observaciones:
                if obs.get("estado") != "observada":
                    continue
                if (obs.get("symbol") or "desconocido") == sym:
                    continue
                oid = str(obs.get("observation_id"))
                for r in resultados_por_id.get(oid, []):
                    if r.get("horizon") != h:
                        continue
                    retorno = _seguro_float(r.get("retorno"))
                    if retorno is None:
                        continue
                    fila = {"retorno": retorno}
                    if obs.get("role") == "candidate":
                        filas_cand.append(fila)
                    elif obs.get("role") == "comparator":
                        filas_comp.append(fila)
            comp = _comparacion_para_conjunto(filas_cand, filas_comp)
            base_diff = diferencia_base_por_h.get(h)
            cambio = None
            signo_cambia = None
            if comp["diferencia"] is not None and base_diff is not None:
                cambio = comp["diferencia"] - base_diff
                signo_base = (base_diff > 0) - (base_diff < 0)
                signo_nuevo = (comp["diferencia"] > 0) - (comp["diferencia"] < 0)
                signo_cambia = signo_base != signo_nuevo
            entrada["por_horizonte"][h] = {
                "candidatos_n": comp["candidatos_n"],
                "comparadores_n": comp["comparadores_n"],
                "candidatos_media": comp["candidatos_media"],
                "candidatos_media_pct": comp["candidatos_media_pct"],
                "comparadores_media": comp["comparadores_media"],
                "comparadores_media_pct": comp["comparadores_media_pct"],
                "diferencia": comp["diferencia"],
                "diferencia_puntos_porcentuales": comp["diferencia_puntos_porcentuales"],
                "diferencia_base": base_diff,
                "diferencia_base_puntos_porcentuales": _pct(base_diff) if base_diff is not None else None,
                "cambio_frente_base": cambio,
                "cambio_frente_base_puntos_porcentuales": _pct(cambio) if cambio is not None else None,
                "signo_cambia": signo_cambia,
                "motivo": (
                    "grupo_vacio_o_sin_resultados"
                    if comp["diferencia"] is None
                    else None
                ),
            }
        sensibilidad_por_simbolo.append(entrada)

    # ============ Asociación: flujo agresor neto / profundidad top-20 ============
    # Validación de identidad de corrida:
    # - observation_id únicos entre observaciones (no deben repetirse).
    # - pares (observation_id, horizon) únicos entre resultados (un resultado por
    #   observación y horizonte; repetir observation_id entre horizontes es normal).
    observation_ids_obs = [str(o.get("observation_id")) for o in observaciones if o.get("observation_id")]
    ids_duplicados_obs = [k for k, v in Counter(observation_ids_obs).items() if v > 1]
    pares_res = [(str(r.get("observation_id")), str(r.get("horizon"))) for r in resultados if r.get("observation_id") and r.get("horizon")]
    ids_duplicados_res = [k for k, v in Counter(pares_res).items() if v > 1]
    ids_duplicados_res = [oid for (oid, _h) in ids_duplicados_res]
    mezcla_run_id_detectada = bool(ids_duplicados_obs or ids_duplicados_res)

    filas_asoc: list[dict[str, Any]] = []
    n_campos_ausentes = 0
    n_profundidad_cero_o_invalida = 0
    n_ventana_incompleta = 0
    n_valor_negativo_flujo = 0
    n_valor_negativo_profundidad = 0
    n_fila_invalida_asoc = 0
    VENTANA_FLUJO_ESPERADA_MS = 60000
    for obs in observaciones:
        if obs.get("estado") != "observada":
            continue
        flujo = obs.get("flujo") or {}
        libro = obs.get("libro") or {}
        cobertura = obs.get("cobertura") or {}
        buy_notional = _seguro_float(flujo.get("buy_notional"))
        sell_notional = _seguro_float(flujo.get("sell_notional"))
        # Validar importes finitos y no negativos.
        flujo_invalido = False
        if buy_notional is None or sell_notional is None:
            flujo_invalido = True
        elif buy_notional < 0 or sell_notional < 0:
            flujo_invalido = True
            n_valor_negativo_flujo += 1
        flujo_neto_notional = None
        if not flujo_invalido:
            flujo_neto_notional = buy_notional - sell_notional
        ventana_flujo_ms = flujo.get("window_ms")
        ventana_completa = flujo.get("ventana_completa")
        ventana_valida = (
            ventana_completa is True
            and ventana_flujo_ms == VENTANA_FLUJO_ESPERADA_MS
        )
        bid_not = _seguro_float(libro.get("bid_notional_top20"))
        ask_not = _seguro_float(libro.get("ask_notional_top20"))
        profundidad = None
        profundidad_invalida = False
        if bid_not is None or ask_not is None:
            profundidad_invalida = True
        elif bid_not < 0 or ask_not < 0:
            profundidad_invalida = True
            n_valor_negativo_profundidad += 1
        else:
            profundidad = bid_not + ask_not
            if profundidad <= 0:
                profundidad_invalida = True
        fila_valida_asoc = (
            not flujo_invalido
            and not profundidad_invalida
            and ventana_valida
        )
        if not fila_valida_asoc:
            n_fila_invalida_asoc += 1
        ciclo_idx, _, _ = ciclo_de_observacion(obs)
        campos_ausentes = (
            buy_notional is None or sell_notional is None
            or bid_not is None or ask_not is None
        )
        for r in resultados_por_id.get(str(obs.get("observation_id")), []):
            h = r.get("horizon")
            if h not in HORIZONTES_EVALUABLES:
                continue
            retorno = _seguro_float(r.get("retorno"))
            if profundidad_invalida:
                n_profundidad_cero_o_invalida += 1
            if not ventana_valida:
                n_ventana_incompleta += 1
            if campos_ausentes:
                n_campos_ausentes += 1
            filas_asoc.append({
                "horizonte": h,
                "simbolo": obs.get("symbol"),
                "ciclo_idx": ciclo_idx,
                "rol": obs.get("role") or "desconocido",
                "lado": _lado_desde_side(obs),
                "flujo_neto_notional_USDT": flujo_neto_notional,
                "profundidad_notional_top20_USDT": profundidad,
                "profundidad_invalida": profundidad_invalida,
                "flujo_invalido": flujo_invalido,
                "ventana_invalida": not ventana_valida,
                "fila_valida_asociacion": fila_valida_asoc,
                "flujo_sobre_profundidad": (
                    (flujo_neto_notional / profundidad)
                    if fila_valida_asoc and profundidad not in (None, 0)
                    else None
                ),
                "ventana_flujo_ms": ventana_flujo_ms,
                "ventana_flujo_completa": ventana_completa,
                "campos_ausentes_o_no_finitos": campos_ausentes,
                "retorno": retorno,
                "retorno_pct": _pct(retorno),
            })

    parejas_validas_por_h = {}
    for h in HORIZONTES_EVALUABLES:
        f = [x for x in filas_asoc if x["horizonte"] == h]
        parejas_validas_por_h[h] = sum(
            1 for x in f if x["fila_valida_asociacion"] and x["flujo_sobre_profundidad"] is not None and x["retorno"] is not None
        )

    # Asociaciones por horizonte con una única definición principal y corte fijo.
    asociaciones: dict[str, Any] = {
        "metrica_principal": (
            "flujo_agresor_neto_notional / profundidad_notional_top20 "
            "(buy_notional - sell_notional) / (bid_notional_top20 + ask_notional_top20)"
        ),
        "unidades": "flujo y profundidad en USDT; ratio adimensional; retorno en fracción",
        "ventana_flujo_ms": VENTANA_FLUJO_ESPERADA_MS,
        "regla_denominador_cero": "si profundidad == 0 o None -> ratio None (no se convierte en cero)",
        "mezcla_run_id_detectada": mezcla_run_id_detectada,
        "ids_duplicados_observacion": ids_duplicados_obs,
        "ids_duplicados_resultado": ids_duplicados_res,
        "n_filas_totales": len(filas_asoc),
        "n_campos_ausentes_o_no_finitos": n_campos_ausentes,
        "n_valor_negativo_flujo": n_valor_negativo_flujo,
        "n_valor_negativo_profundidad": n_valor_negativo_profundidad,
        "n_profundidad_cero_o_invalida": n_profundidad_cero_o_invalida,
        "n_ventana_incompleta": n_ventana_incompleta,
        "n_fila_invalida_asociacion": n_fila_invalida_asoc,
        "parejas_validas_por_horizonte": parejas_validas_por_h,
        "por_horizonte": {},
    }
    for h in HORIZONTES_EVALUABLES:
        f = [x for x in filas_asoc if x["horizonte"] == h]
        pares = [
            (x["flujo_sobre_profundidad"], x["retorno"])
            for x in f
            if x["flujo_sobre_profundidad"] is not None and x["retorno"] is not None
        ]
        n = len(pares)
        mx = statistics.fmean([a for a, _ in pares]) if pares else None
        my = statistics.fmean([b for _, b in pares]) if pares else None
        pearson = None
        motivo = None
        if n < 2:
            motivo = "muestra_insuficiente_menor_a_2"
        else:
            sx2 = sum((a - mx) ** 2 for a, _ in pares) / n
            sy2 = sum((b - my) ** 2 for _, b in pares) / n
            if sx2 == 0.0 or sy2 == 0.0:
                motivo = "varianza_cero_en_una_variable"
            else:
                cov = sum((a - mx) * (b - my) for a, b in pares) / n
                pearson = cov / (math.sqrt(sx2) * math.sqrt(sy2))

        # Corte fijo: tercil superior de |ratio| del dataset (no umbral operativo validado).
        alto_f = [x for x in f if x["flujo_sobre_profundidad"] is not None]
        corte_fijo = None
        if alto_f:
            vals_abs = sorted(abs(x["flujo_sobre_profundidad"]) for x in alto_f)
            corte_fijo = vals_abs[int(len(vals_abs) * 2 / 3)]
        grupo_alto = [x for x in alto_f if abs(x["flujo_sobre_profundidad"]) >= (corte_fijo or 0)]
        grupo_bajo = [x for x in alto_f if abs(x["flujo_sobre_profundidad"]) < (corte_fijo or 0)]

        def _st_retorno(xs: list[dict[str, Any]]) -> dict[str, Any]:
            vals = [x["retorno"] for x in xs if x["retorno"] is not None]
            return _stats(vals)

        asociaciones["por_horizonte"][h] = {
            "n_filas": len(f),
            "n_pares_validos": n,
            "pearson": pearson,
            "motivo": motivo,
            "corte_fijo_abs": corte_fijo,
            "corte_fijo_regla": "tercil_superior_de_valor_absoluto_del_ratio_obtenido_del_dataset_no_umbral_validado",
            "grupo_ratio_alto": {
                "n": len(grupo_alto),
                "retorno": _st_retorno(grupo_alto),
                "magnitud_media_abs": (
                    statistics.fmean([abs(x["retorno"]) for x in grupo_alto if x["retorno"] is not None])
                    if grupo_alto else None
                ),
            },
            "grupo_ratio_bajo": {
                "n": len(grupo_bajo),
                "retorno": _st_retorno(grupo_bajo),
                "magnitud_media_abs": (
                    statistics.fmean([abs(x["retorno"]) for x in grupo_bajo if x["retorno"] is not None])
                    if grupo_bajo else None
                ),
            },
        }

    # ============ Resumen por símbolo y dependencia ============
    por_simbolo: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"n_resultados": 0, "ciclos": set(), "horizontes": Counter()}
    )
    por_ciclo_res: dict[int | None, dict[str, Any]] = defaultdict(
        lambda: {"n_resultados": 0, "simbolos": set(), "candidatos": 0, "comparadores": 0}
    )
    for r in resultados:
        simbolo = r.get("symbol")
        oid = r.get("observation_id", "")
        obs_origen = next((o for o in observaciones if o.get("observation_id") == oid), None)
        ciclo_idx, _, _ = ciclo_de_observacion(obs_origen) if obs_origen else (None, None)
        rol = obs_origen.get("role") if obs_origen else None
        if simbolo:
            por_simbolo[simbolo]["n_resultados"] += 1
            if ciclo_idx is not None:
                por_simbolo[simbolo]["ciclos"].add(ciclo_idx)
            por_simbolo[simbolo]["horizontes"][r.get("horizon")] += 1
        if ciclo_idx is not None:
            por_ciclo_res[ciclo_idx]["n_resultados"] += 1
            por_ciclo_res[ciclo_idx]["simbolos"].add(simbolo or "desconocido")
            if rol == "candidate":
                por_ciclo_res[ciclo_idx]["candidatos"] += 1
            elif rol == "comparator":
                por_ciclo_res[ciclo_idx]["comparadores"] += 1

    resumen_por_simbolo_dependencia = {
        s: {
            "n_resultados": v["n_resultados"],
            "n_ciclos": len(v["ciclos"]),
            "horizontes": dict(v["horizontes"]),
        }
        for s, v in sorted(por_simbolo.items())
    }
    resumen_por_ciclo = {
        str(c) if c is not None else "desconocido": {
            "n_resultados": v["n_resultados"],
            "n_simbolos": len(v["simbolos"]),
            "candidatos": v["candidatos"],
            "comparadores": v["comparadores"],
        }
        for c, v in sorted(
            por_ciclo_res.items(), key=lambda x: (x[0] is None, x if x[0] is not None else -1)
        )
    }

    # ============ Precios y costes ============
    precios_fuentes: set[str] = set()
    for r in resultados:
        if r.get("precio_base_fuente"):
            precios_fuentes.add(r.get("precio_base_fuente"))
        if r.get("precio_posterior_fuente"):
            precios_fuentes.add(r.get("precio_posterior_fuente"))
    neto_estados = Counter(r.get("neto_estado") for r in resultados)

    return {
        "run_id": run_id,
        "total_lineas": len(objetos),
        "ciclos": len(ciclos),
        "observaciones_total": len(observaciones),
        "observaciones_aptas": sum(1 for o in observaciones if o.get("estado") == "observada"),
        "observaciones_descartadas": sum(1 for o in observaciones if o.get("estado") == "descartada"),
        "resultados_total": len(resultados),
        "resultados_por_horizonte": {
            h: sum(1 for r in resultados if r.get("horizon") == h) for h in HORIZONTES
        },
        "seleccionados_total": total_seleccionados,
        "seleccionados_por_rol": total_seleccionados_por_rol,
        "total_sin_observacion": total_sin_observacion,
        "embudo_tabla": filas_embudo,
        "comparacion": comparacion_por_horizonte,
        "asociaciones": asociaciones,
        "sensibilidad_por_simbolo": sensibilidad_por_simbolo,
        "resumen_por_simbolo_dependencia": resumen_por_simbolo_dependencia,
        "resumen_por_ciclo": resumen_por_ciclo,
        "precios_y_costes": {
            "fuentes_detectadas": sorted(precios_fuentes),
            "neto_estados": dict(neto_estados),
            "nota": "precio_base = libro_mid; precio_posterior = klines_apertura_1m; proxy de fuentes mixtas, no mark-to-mid, no P&L ejecutable; neto_estado=UNKNOWN sin costes ni ejecución acreditados.",
        },
    }


def _escribir_json(ruta: Path, datos: Any) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Análisis offline universo-liquidez-v1 v2 de la captura pública 20261106a."
    )
    parser.add_argument(
        "--jsonl", required=True, help="Ruta del JSONL del dataset (obligatorio)."
    )
    parser.add_argument(
        "--out-derivados",
        required=True,
        help="Directorio de derivados detallados (fuera de Git).",
    )
    parser.add_argument(
        "--out-tablas",
        required=True,
        help="Directorio de tablas pequeñas para Git.",
    )
    parser.add_argument(
        "--run_id",
        required=True,
        help="Identificador de corrida (se publica en las tablas).",
    )
    args = parser.parse_args()

    jsonl = Path(args.jsonl)
    out_derivados = Path(args.out_derivados)
    out_tablas = Path(args.out_tablas)

    res = analizar(jsonl, run_id=args.run_id)

    # Derivados detallados (fuera de Git).
    _escribir_json(out_derivados / "analisis_completo_v2.json", res)

    # Tablas pequeñas para Git (sin derivados voluminosos).
    tablas_publicar: dict[str, Any] = {
        "run_id": args.run_id,
        "version_analisis": "v2_embudo_desde_ciclos",
        "codigo_salida_proceso": "UNKNOWN",
        "nota_codigo_salida": "no recuperable retrospectivamente; finalización inferida del resumen de corrida, no evidencia directa del SO",
        "resumen_global": {
            k: v
            for k, v in res.items()
            if k
            not in (
                "comparacion",
                "asociaciones",
                "embudo_tabla",
                "resumen_por_simbolo_dependencia",
                "resumen_por_ciclo",
                "sensibilidad_por_simbolo",
            )
        },
        "embudo_desde_ciclos": {
            "seleccionados_total": res["seleccionados_total"],
            "seleccionados_por_rol": res["seleccionados_por_rol"],
            "total_sin_observacion": res["total_sin_observacion"],
            "observaciones_emitidas_total": res["observaciones_total"],
            "observaciones_aptas": res["observaciones_aptas"],
            "observaciones_descartadas": res["observaciones_descartadas"],
            "resultados_total": res["resultados_total"],
            "resultados_por_horizonte": res["resultados_por_horizonte"],
            "filas_por_ciclo_rol": res["embudo_tabla"],
        },
        "comparacion_candidatos_comparadores": {
            h: {
                "candidatos": {
                    "n_resultados": v["candidatos"]["n_resultados"],
                    "n_simbolos": v["candidatos"]["n_simbolos"],
                    "n_ciclos": v["candidatos"]["n_ciclos"],
                    "media": v["candidatos"]["media"],
                    "media_pct": v["candidatos"]["media_pct"],
                    "mediana": v["candidatos"]["mediana"],
                    "mediana_pct": v["candidatos"]["mediana_pct"],
                    "desv": v["candidatos"]["desv"],
                    "min": v["candidatos"]["min"],
                    "min_pct": v["candidatos"]["min_pct"],
                    "max": v["candidatos"]["max"],
                    "max_pct": v["candidatos"]["max_pct"],
                    "proporcion_positivos": v["candidatos"]["proporcion_positivos"],
                    "media_por_simbolo": v["candidatos"]["media_por_simbolo"],
                    "media_por_simbolo_pct": v["candidatos"]["media_por_simbolo_pct"],
                },
                "comparadores": {
                    "n_resultados": v["comparadores"]["n_resultados"],
                    "n_simbolos": v["comparadores"]["n_simbolos"],
                    "n_ciclos": v["comparadores"]["n_ciclos"],
                    "media": v["comparadores"]["media"],
                    "media_pct": v["comparadores"]["media_pct"],
                    "mediana": v["comparadores"]["mediana"],
                    "mediana_pct": v["comparadores"]["mediana_pct"],
                    "desv": v["comparadores"]["desv"],
                    "min": v["comparadores"]["min"],
                    "min_pct": v["comparadores"]["min_pct"],
                    "max": v["comparadores"]["max"],
                    "max_pct": v["comparadores"]["max_pct"],
                    "proporcion_positivos": v["comparadores"]["proporcion_positivos"],
                    "media_por_simbolo": v["comparadores"]["media_por_simbolo"],
                    "media_por_simbolo_pct": v["comparadores"]["media_por_simbolo_pct"],
                },
                "diferencia_medias_agrupada": v["diferencia_medias_agrupada"],
                "diferencia_medias_agrupada_puntos_porcentuales": v[
                    "diferencia_medias_agrupada_puntos_porcentuales"
                ],
                "diferencia_medias_agrupada_por_simbolo": v[
                    "diferencia_medias_agrupada_por_simbolo"
                ],
                "media_de_diferencias_por_ciclo": v["media_de_diferencias_por_ciclo"],
                "media_de_diferencias_por_ciclo_puntos_porcentuales": v[
                    "media_de_diferencias_por_ciclo_puntos_porcentuales"
                ],
                "ciclos_con_ambos_grupos": v["ciclos_con_ambos_grupos"],
                "ciclos_sin_grupo_comparable": v["ciclos_sin_grupo_comparable"],
                "comp_aptos_por_ciclo": v["comp_aptos_por_ciclo"],
                "ciclos_con_un_solo_comparador": v["ciclos_con_un_solo_comparador"],
                "updown_candidatos": v["updown_candidatos"],
            }
            for h, v in res["comparacion"].items()
        },
        "asociaciones_flujo_profundidad": {
            "metrica_principal": res["asociaciones"]["metrica_principal"],
            "unidades": res["asociaciones"]["unidades"],
            "ventana_flujo_ms": res["asociaciones"]["ventana_flujo_ms"],
            "regla_denominador_cero": res["asociaciones"]["regla_denominador_cero"],
            "mezcla_run_id_detectada": res["asociaciones"]["mezcla_run_id_detectada"],
            "ids_duplicados_observacion": res["asociaciones"]["ids_duplicados_observacion"],
            "ids_duplicados_resultado": res["asociaciones"]["ids_duplicados_resultado"],
            "n_filas_totales": res["asociaciones"]["n_filas_totales"],
            "n_campos_ausentes_o_no_finitos": res["asociaciones"]["n_campos_ausentes_o_no_finitos"],
            "n_valor_negativo_flujo": res["asociaciones"]["n_valor_negativo_flujo"],
            "n_valor_negativo_profundidad": res["asociaciones"]["n_valor_negativo_profundidad"],
            "n_profundidad_cero_o_invalida": res["asociaciones"]["n_profundidad_cero_o_invalida"],
            "n_ventana_incompleta": res["asociaciones"]["n_ventana_incompleta"],
            "n_fila_invalida_asociacion": res["asociaciones"]["n_fila_invalida_asociacion"],
            "parejas_validas_por_horizonte": res["asociaciones"]["parejas_validas_por_horizonte"],
            "por_horizonte": res["asociaciones"]["por_horizonte"],
        },
        "sensibilidad_por_simbolo": res["sensibilidad_por_simbolo"],
        "diferencia_base_por_horizonte": {
            h: res["sensibilidad_por_simbolo"][0]["por_horizonte"][h]["diferencia_base"]
            if res["sensibilidad_por_simbolo"]
            else None
            for h in HORIZONTES_EVALUABLES
        },
        "dependencia": {
            "resumen_por_simbolo": res["resumen_por_simbolo_dependencia"],
            "resumen_por_ciclo": res["resumen_por_ciclo"],
            "nota": "Los retornos de tres horizontes sobre una misma observación no son muestras independientes; los símbolos repetidos y las ventanas solapadas tampoco lo son automáticamente.",
        },
        "precios_y_costes": res["precios_y_costes"],
    }
    _escribir_json(out_tablas / "resumen_analisis_universo_liquidez_v2.json", tablas_publicar)
    print("Derivados detallados escritos en", out_derivados / "analisis_completo_v2.json")
    print("Tablas pequeñas para Git escritas en", out_tablas / "resumen_analisis_universo_liquidez_v2.json")


if __name__ == "__main__":
    main()

