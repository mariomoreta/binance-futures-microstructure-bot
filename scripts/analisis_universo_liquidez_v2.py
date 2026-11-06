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

    # Ciclos de decisión ordenados por decision_ms (momento de evaluación).
    decision_ms_ordenados = sorted(
        {o.get("decision_ms") for o in observaciones if isinstance(o.get("decision_ms"), int)}
    )

    # Pareado reference_ms (selección) -> decision_ms (decisión) por posición ordenada.
    # Son 12 de cada uno; se asume pareado por orden cronológico.
    seleccion_a_decision: dict[int, int] = {}
    for i, c in enumerate(ciclos_ordenados):
        ref = c.get("reference_ms")
        if isinstance(ref, int) and i < len(decision_ms_ordenados):
            seleccion_a_decision[ref] = decision_ms_ordenados[i]

    # Selección por ciclo (reference_ms) y rol: símbolos seleccionados.
    seleccion_por_ciclo_rol: dict[int, dict[str, list[str]]] = {}
    seleccion_simbolo_rol_por_ciclo: dict[int, dict[str, str]] = {}
    for c in ciclos_ordenados:
        ref = c.get("reference_ms")
        rol_map: dict[str, list[str]] = {"candidate": [], "comparator": []}
        simbolo_rol: dict[str, str] = {}
        for entry in (c.get("selected") or []):
            sym = entry.get("symbol")
            if sym:
                rol_map["candidate"].append(sym)
                simbolo_rol[sym] = "candidate"
        for entry in (c.get("comparator") or []):
            sym = entry.get("symbol")
            if sym:
                rol_map["comparator"].append(sym)
                simbolo_rol[sym] = "comparator"
        if isinstance(ref, int):
            seleccion_por_ciclo_rol[ref] = rol_map
            seleccion_simbolo_rol_por_ciclo[ref] = simbolo_rol

    # Índice de resultados por observation_id.
    resultados_por_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in resultados:
        oid = r.get("observation_id")
        if oid:
            resultados_por_id[str(oid)].append(r)

    def ciclo_de_observacion(
        obs: dict[str, Any],
    ) -> tuple[int | None, dict[str, Any] | None]:
        """Devuelve (índice de ciclo de decisión, objeto ciclo) usando decision_ms."""
        dm = obs.get("decision_ms")
        if isinstance(dm, int) and dm in decision_ms_ordenados:
            return decision_ms_ordenados.index(dm), {
                "reference_ms": None,
                "decision_ms": dm,
                "tipo": "decision",
            }
        return None, None

    return {
        "ciclos": ciclos_ordenados,
        "observaciones": observaciones,
        "resultados": resultados,
        "decision_ms_ordenados": decision_ms_ordenados,
        "seleccion_a_decision": seleccion_a_decision,
        "seleccion_por_ciclo_rol": seleccion_por_ciclo_rol,
        "seleccion_simbolo_rol_por_ciclo": seleccion_simbolo_rol_por_ciclo,
        "resultados_por_id": resultados_por_id,
        "ciclo_de_observacion": ciclo_de_observacion,
    }


def analizar(jsonl: Path, run_id: str | None = None) -> dict[str, Any]:
    """Ejecuta el análisis completo y devuelve un dict serializable."""
    objetos = _cargar_jsonl(jsonl)
    idx = _indexar(objetos)
    ciclos = idx["ciclos"]
    observaciones = idx["observaciones"]
    resultados = idx["resultados"]
    decision_ms_ordenados = idx["decision_ms_ordenados"]
    seleccion_a_decision = idx["seleccion_a_decision"]
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

    for i, c in enumerate(ciclos):
        ref = c.get("reference_ms")
        ciclo_idx = i
        dm = seleccion_a_decision.get(ref) if isinstance(ref, int) else None
        ciclo_dec_idx = decision_ms_ordenados.index(dm) if isinstance(dm, int) and dm in decision_ms_ordenados else None

        sel_rol = seleccion_por_ciclo_rol.get(ref, {"candidate": [], "comparator": []}) if isinstance(ref, int) else {"candidate": [], "comparator": []}
        for rol in ROLES:
            n_sel = len(sel_rol.get(rol, []))
            total_seleccionados += n_sel
            total_seleccionados_por_rol[rol] += n_sel
            # observaciones emitidas para este ciclo de decisión y rol
            obs_rol = [o for o in observaciones
                       if (o.get("role") == rol)
                       and (o.get("decision_ms") == dm)]
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
            filas_embudo.append({
                "ciclo_idx": ciclo_dec_idx,
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
            ciclo_idx, _ = ciclo_de_observacion(obs)
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

    # ============ Asociación: flujo agresor neto / profundidad top-20 ============
    filas_asoc: list[dict[str, Any]] = []
    n_campos_ausentes = 0
    n_profundidad_cero_invalida = 0
    n_ventana_incompleta = 0
    for obs in observaciones:
        if obs.get("estado") != "observada":
            continue
        flujo = obs.get("flujo") or {}
        libro = obs.get("libro") or {}
        cobertura = obs.get("cobertura") or {}
        buy_notional = _seguro_float(flujo.get("buy_notional"))
        sell_notional = _seguro_float(flujo.get("sell_notional"))
        flujo_neto_notional = None
        if buy_notional is not None and sell_notional is not None:
            flujo_neto_notional = buy_notional - sell_notional
        ventana_flujo_ms = flujo.get("window_ms")
        ventana_completa = flujo.get("ventana_completa")
        if not ventana_completa:
            n_ventana_incompleta += 1
        bid_not = _seguro_float(libro.get("bid_notional_top20"))
        ask_not = _seguro_float(libro.get("ask_notional_top20"))
        profundidad = None
        profundidad_cero_o_invalida = False
        if bid_not is None or ask_not is None:
            profundidad_cero_o_invalida = True
        else:
            profundidad = bid_not + ask_not
        ciclo_idx, _ = ciclo_de_observacion(obs)
        for r in resultados_por_id.get(str(obs.get("observation_id")), []):
            h = r.get("horizon")
            if h not in HORIZONTES_EVALUABLES:
                continue
            retorno = _seguro_float(r.get("retorno"))
            campos_ausentes = (
                buy_notional is None or sell_notional is None
                or bid_not is None or ask_not is None
            )
            if campos_ausentes:
                n_campos_ausentes += 1
            if profundidad is not None and profundidad <= 0:
                n_profundidad_cero_invalida += 1
            filas_asoc.append({
                "horizonte": h,
                "simbolo": obs.get("symbol"),
                "ciclo_idx": ciclo_idx,
                "rol": obs.get("role") or "desconocido",
                "lado": _lado_desde_side(obs),
                "flujo_neto_notional_USDT": flujo_neto_notional,
                "profundidad_notional_top20_USDT": profundidad,
                "profundidad_cero_o_invalida": profundidad_cero_o_invalida,
                "flujo_sobre_profundidad": (
                    (flujo_neto_notional / profundidad)
                    if (flujo_neto_notional is not None and profundidad not in (None, 0))
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
            1 for x in f if x["flujo_sobre_profundidad"] is not None and x["retorno"] is not None
        )

    # Asociaciones por horizonte con una única definición principal y corte fijo.
    asociaciones: dict[str, Any] = {
        "metrica_principal": (
            "flujo_agresor_neto_notional / profundidad_notional_top20 "
            "(buy_notional - sell_notional) / (bid_notional_top20 + ask_notional_top20)"
        ),
        "unidades": "flujo y profundidad en USDT; ratio adimensional; retorno en fracción",
        "ventana_flujo_ms": 60000,
        "regla_denominador_cero": "si profundidad == 0 o None -> ratio None (no se convierte en cero)",
        "n_filas_totales": len(filas_asoc),
        "n_campos_ausentes_o_no_finitos": n_campos_ausentes,
        "n_profundidad_cero_o_invalida": n_profundidad_cero_invalida,
        "n_ventana_incompleta": n_ventana_incompleta,
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
        ciclo_idx, _ = ciclo_de_observacion(obs_origen) if obs_origen else (None, None)
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
            "n_filas_totales": res["asociaciones"]["n_filas_totales"],
            "n_campos_ausentes_o_no_finitos": res["asociaciones"]["n_campos_ausentes_o_no_finitos"],
            "n_profundidad_cero_o_invalida": res["asociaciones"]["n_profundidad_cero_o_invalida"],
            "n_ventana_incompleta": res["asociaciones"]["n_ventana_incompleta"],
            "parejas_validas_por_horizonte": res["asociaciones"]["parejas_validas_por_horizonte"],
            "por_horizonte": res["asociaciones"]["por_horizonte"],
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

