"""Análisis OFFLINE y solo lectura de la captura pública public-pilot-1h-20261106a.

Objetivo del bloque research/universe-liquidity-v1: determinar qué evidencia
aporta la captura completa sobre la autoselección de tokens y la relación entre
liquidez, flujo agresor y movimiento posterior.

Lee únicamente el JSONL del dataset original sin modificarlo y escribe tablas
pequeñas para publicación en Git. Los derivados detallados se dejan fuera de Git.
No conecta a Binance, no adquiere datos nuevos, no cambia reglas ni tolerancias.

Argumentos explícitos:
  --jsonl        Ruta del JSONL del dataset (obligatorio, sin valor por defecto
                 que dependa de otra captura).
  --out-derivados Directorio de derivados detallados (fuera de Git).
  --out-tablas   Directorio de tablas pequeñas para Git.
  --run_id       Identificador de corrida (se publica en las tablas).

Código de salida del proceso: se mantiene UNKNOWN (no recuperable retrospectivamente).
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
    media = statistics.fmean(limpios)
    mediana = statistics.median(limpios)
    desv = statistics.pstdev(limpios) if n > 1 else 0.0
    return {
        "n": n,
        "media": media,
        "mediana": mediana,
        "desv": desv,
        "min": min(limpios),
        "max": max(limpios),
    }


def _pct(valor: float | None) -> float | None:
    if valor is None:
        return None
    return valor * 100.0


def _lado_desde_side(obs: dict[str, Any]) -> str | None:
    """Clasificación disponible al seleccionar: campo `side` (UP/DOWN).

    No se usa `move_24h_pct` (siempre None en este dataset) como proxy.
    """
    lado = obs.get("side")
    if lado in LADOS:
        return lado
    return None


def _indexar(objetos: list[dict[str, Any]]) -> dict[str, Any]:
    ciclos = [o for o in objetos if o.get("kind") == "ciclo"]
    observaciones = [o for o in objetos if o.get("kind") == "observacion"]
    resultados = [o for o in objetos if o.get("kind") == "resultado"]

    ciclos_por_ref: dict[int, dict[str, Any]] = {}
    for c in ciclos:
        rm = c.get("reference_ms")
        if isinstance(rm, int):
            ciclos_por_ref[rm] = c
    ciclos_ordenados = sorted(ciclos, key=lambda c: c.get("reference_ms", 0))

    resultados_por_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in resultados:
        oid = r.get("observation_id")
        if oid:
            resultados_por_id[str(oid)].append(r)

    def ciclo_de_observacion(
        obs: dict[str, Any],
    ) -> tuple[int | None, dict[str, Any] | None]:
        disp = obs.get("disponibilidad") or {}
        sel_ms = disp.get("seleccion_ms")
        if isinstance(sel_ms, int) and sel_ms in ciclos_por_ref:
            c = ciclos_por_ref[sel_ms]
            return ciclos_ordenados.index(c), c
        return None, None

    return {
        "ciclos": ciclos,
        "ciclos_ordenados": ciclos_ordenados,
        "observaciones": observaciones,
        "resultados": resultados,
        "resultados_por_id": resultados_por_id,
        "ciclo_de_observacion": ciclo_de_observacion,
    }


def analizar(
    jsonl: Path, run_id: str | None = None
) -> dict[str, Any]:
    """Ejecuta el análisis completo y devuelve un dict serializable."""
    objetos = _cargar_jsonl(jsonl)
    idx = _indexar(objetos)
    ciclos = idx["ciclos"]
    ciclos_ordenados = idx["ciclos_ordenados"]
    observaciones = idx["observaciones"]
    resultados = idx["resultados"]
    resultados_por_id = idx["resultados_por_id"]
    ciclo_de_observacion = idx["ciclo_de_observacion"]

    # ============ Embudo por rol (sin solapamiento entre roles) ============
    seleccionadas_por_rol: dict[str, int] = Counter()
    aptas_por_rol: dict[str, int] = Counter()
    descartadas_por_rol: dict[str, int] = Counter()
    motivos_por_rol: dict[str, Counter] = defaultdict(Counter)

    for obs in observaciones:
        rol = obs.get("role") or "desconocido"
        estado = obs.get("estado")
        seleccionadas_por_rol[rol] += 1
        if estado == "observada":
            aptas_por_rol[rol] += 1
        elif estado == "descartada":
            descartadas_por_rol[rol] += 1
            for m in (obs.get("motivos") or []):
                motivos_por_rol[rol][m] += 1

    total_observaciones = len(observaciones)
    total_aptas = aptas_por_rol.get("candidate", 0) + aptas_por_rol.get("comparator", 0)
    total_descartadas = descartadas_por_rol.get("candidate", 0) + descartadas_por_rol.get(
        "comparator", 0
    )

    # ============ Cobertura por ciclo, rol y horizonte ============
    filas_cobertura: list[dict[str, Any]] = []
    for ciclo_idx in range(len(ciclos_ordenados)):
        for rol in ROLES:
            for h in HORIZONTES:
                obs_ciclo_rol = [
                    o
                    for o in observaciones
                    if (o.get("role") or "desconocido") == rol
                    and ciclo_de_observacion(o)[0] == ciclo_idx
                ]
                n_obs = len(obs_ciclo_rol)
                n_aptas = sum(1 for o in obs_ciclo_rol if o.get("estado") == "observada")
                n_desc = sum(1 for o in obs_ciclo_rol if o.get("estado") == "descartada")
                n_res = 0
                n_faltante = 0
                for o in obs_ciclo_rol:
                    if o.get("estado") != "observada":
                        continue
                    oid = str(o.get("observation_id"))
                    res_h = [
                        r
                        for r in resultados_por_id.get(oid, [])
                        if r.get("horizon") == h
                    ]
                    if res_h:
                        n_res += 1
                    else:
                        n_faltante += 1
                motivos = Counter()
                for o in obs_ciclo_rol:
                    if o.get("estado") == "descartada":
                        for m in (o.get("motivos") or []):
                            motivos[m] += 1
                filas_cobertura.append(
                    {
                        "ciclo_idx": ciclo_idx,
                        "rol": rol,
                        "horizonte": h,
                        "seleccionadas": n_obs,
                        "aptas": n_aptas,
                        "descartadas": n_desc,
                        "resultado_registrado": n_res,
                        "resultado_faltante": n_faltante,
                        "tasa_cobertura_sobre_seleccionadas": (
                            n_res / n_obs if n_obs else None
                        ),
                        "tasa_cobertura_sobre_aptas": (
                            n_res / n_aptas if n_aptas else None
                        ),
                        "n_simbolos_distintos": len({o.get("symbol") for o in obs_ciclo_rol if o.get("symbol")}),
                        "motivos_descartes": dict(motivos),
                    }
                )

    # ============ Comparación candidatos vs comparadores por horizonte ============
    comparacion_por_horizonte: dict[str, dict[str, Any]] = {}

    def grupo_retornos(h: str, rol: str) -> list[dict[str, Any]]:
        filas = []
        for obs in observaciones:
            if (o_rol := obs.get("role")) != rol:
                continue
            if obs.get("estado") != "observada":
                continue
            oid = str(obs.get("observation_id"))
            ciclo_idx, _ = ciclo_de_observacion(obs)
            for r in resultados_por_id.get(oid, []):
                if r.get("horizon") != h:
                    continue
                retorno = _seguro_float(r.get("retorno"))
                if retorno is None:
                    continue
                filas.append(
                    {
                        "simbolo": obs.get("symbol"),
                        "ciclo_idx": ciclo_idx,
                        "retorno": retorno,
                        "observation_id": oid,
                        "lado": _lado_desde_side(obs),
                        "precio_base": r.get("precio_base"),
                        "precio_posterior": r.get("precio_posterior"),
                        "precio_base_fuente": r.get("precio_base_fuente"),
                        "precio_posterior_fuente": r.get("precio_posterior_fuente"),
                        "horizonte_efectivo_ms": r.get("horizonte_efectivo_ms"),
                    }
                )
        return filas

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

        # Diferencia por ciclo (mismo peso a cada ciclo con ambos grupos).
        diferencias_por_ciclo: list[dict[str, Any]] = []
        for ci in sorted(ciclos_comunes):
            cand_ci = [f["retorno"] for f in filas_cand if f["ciclo_idx"] == ci]
            comp_ci = [f["retorno"] for f in filas_comp if f["ciclo_idx"] == ci]
            if cand_ci and comp_ci:
                mc = statistics.fmean(cand_ci)
                mco = statistics.fmean(comp_ci)
                diferencias_por_ciclo.append(
                    {
                        "ciclo_idx": ci,
                        "n_candidatos": len(cand_ci),
                        "n_comparadores": len(comp_ci),
                        "media_candidatos": mc,
                        "media_candidatos_pct": _pct(mc),
                        "media_comparadores": mco,
                        "media_comparadores_pct": _pct(mco),
                        "diferencia_ciclo": mc - mco,
                        "diferencia_ciclo_puntos_porcentuales": _pct(mc - mco),
                    }
                )

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
            medias = []
            for vals in por_simb.values():
                if vals:
                    medias.append(statistics.fmean(vals))
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
            "diferencias_por_ciclo": diferencias_por_ciclo,
            "ciclos_sin_grupo_comparable": sorted(
                (ciclos_cand | ciclos_comp) - ciclos_comunes
            ),
            "updown_candidatos": updown,
        }

    # ============ Asociación: flujo agresor neto / profundidad top-20 ============
    filas_asoc: list[dict[str, Any]] = []
    for obs in observaciones:
        if obs.get("estado") != "observada":
            continue
        flujo = obs.get("flujo") or {}
        libro = obs.get("libro") or {}
        buy_notional = _seguro_float(flujo.get("buy_notional"))
        sell_notional = _seguro_float(flujo.get("sell_notional"))
        flujo_neto_notional = None
        if buy_notional is not None and sell_notional is not None:
            flujo_neto_notional = buy_notional - sell_notional
        ventana_flujo_ms = flujo.get("window_ms")
        ventana_completa = flujo.get("ventana_completa")
        bid_not = _seguro_float(libro.get("bid_notional_top20"))
        ask_not = _seguro_float(libro.get("ask_notional_top20"))
        profundidad = None
        if bid_not is not None and ask_not is not None:
            profundidad = bid_not + ask_not
        ciclo_idx, _ = ciclo_de_observacion(obs)
        for r in resultados_por_id.get(str(obs.get("observation_id")), []):
            h = r.get("horizon")
            if h not in HORIZONTES_EVALUABLES:
                continue
            retorno = _seguro_float(r.get("retorno"))
            filas_asoc.append(
                {
                    "horizonte": h,
                    "simbolo": obs.get("symbol"),
                    "ciclo_idx": ciclo_idx,
                    "rol": obs.get("role") or "desconocido",
                    "lado": _lado_desde_side(obs),
                    "flujo_neto_notional_USDT": flujo_neto_notional,
                    "profundidad_notional_top20_USDT": profundidad,
                    "flujo_sobre_profundidad": (
                        (flujo_neto_notional / profundidad)
                        if (flujo_neto_notional is not None and profundidad not in (None, 0))
                        else None
                    ),
                    "ventana_flujo_ms": ventana_flujo_ms,
                    "ventana_flujo_completa": ventana_completa,
                    "retorno": retorno,
                    "retorno_pct": _pct(retorno),
                }
            )

    # Asociaciones por horizonte con una única definición principal y corte fijo.
    CORTE_ABSOLUTO = 0.002  # 0.2% de retorno absoluto = corte fijo de magnitud
    asociaciones: dict[str, Any] = {
        "metrica_principal": (
            "flujo_agresor_neto_notional / profundidad_notional_top20 "
            "(buy_notional - sell_notional) / (bid_notional_top20 + ask_notional_top20)"
        ),
        "unidades": "flujo y profundidad en USDT; ratio adimensional; retorno en fracción",
        "ventana_flujo_ms": 60000,
        "disponibilidad": "168/168 aptas con campo completo; denominador nunca cero en este dataset",
        "regla_denominador_cero": "si profundidad == 0 o None -> ratio None (no se convierte en cero)",
        "n_filas_totales": len(filas_asoc),
        "por_horizonte": {},
    }
    for h in HORIZONTES_EVALUABLES:
        f = [x for x in filas_asoc if x["horizonte"] == h]
        pares = [
            (x["flujo_sobre_profundidad"], x["retorno"])
            for x in f
            if x["flujo_sobre_profundidad"] is not None and x["retorno"] is not None
        ]
        mx = statistics.fmean([a for a, _ in pares]) if pares else None
        my = statistics.fmean([b for _, b in pares]) if pares else None
        n = len(pares)
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

        # Corte fijo: descripción de la asociación con retornos y magnitud.
        alto_f = [x for x in f if x["flujo_sobre_profundidad"] is not None]
        corte_fijo = None
        if alto_f:
            vals_abs = sorted(abs(x["flujo_sobre_profundidad"]) for x in alto_f)
            corte_fijo = vals_abs[int(len(vals_abs) * 2 / 3)]  # tercil superior de |ratio|
        grupo_alto = [
            x for x in alto_f if abs(x["flujo_sobre_profundidad"]) >= (corte_fijo or 0)
        ]
        grupo_bajo = [
            x for x in alto_f if abs(x["flujo_sobre_profundidad"]) < (corte_fijo or 0)
        ]

        def _st_retorno(xs: list[dict[str, Any]]) -> dict[str, Any]:
            vals = [x["retorno"] for x in xs if x["retorno"] is not None]
            return _stats(vals)

        asociaciones["por_horizonte"][h] = {
            "n_filas": len(f),
            "n_pares_validos": n,
            "pearson": pearson,
            "motivo": motivo,
            "corte_fijo_abs": corte_fijo,
            "corte_fijo_regla": "tercil_superior_de_valor_absoluto_del_ratio_fijo_para_todo_el_informe",
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
        "observaciones_total": total_observaciones,
        "observaciones_aptas": total_aptas,
        "observaciones_descartadas": total_descartadas,
        "resultados_total": len(resultados),
        "resultados_por_horizonte": {
            h: sum(1 for r in resultados if r.get("horizon") == h) for h in HORIZONTES
        },
        "seleccionadas_por_rol": dict(seleccionadas_por_rol),
        "aptas_por_rol": dict(aptas_por_rol),
        "descartes_por_rol": dict(descartadas_por_rol),
        "descartes_por_rol_motivo": {k: dict(v) for k, v in motivos_por_rol.items()},
        "cobertura_tabla": filas_cobertura,
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
        description="Análisis offline universo-liquidez-v1 de la captura pública 20261106a."
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
    _escribir_json(out_derivados / "analisis_completo.json", res)

    # Tablas pequeñas para Git (sin derivados voluminosos).
    tablas_publicar: dict[str, Any] = {
        "run_id": args.run_id,
        "codigo_salida_proceso": "UNKNOWN",
        "nota_codigo_salida": "no recuperable retrospectivamente; finalización inferida del resumen de corrida, no evidencia directa del SO",
        "resumen_global": {
            k: v
            for k, v in res.items()
            if k
            not in (
                "comparacion",
                "asociaciones",
                "cobertura_tabla",
                "resumen_por_simbolo_dependencia",
                "resumen_por_ciclo",
            )
        },
        "embudo_cobertura": {
            "seleccionadas_por_rol": res["seleccionadas_por_rol"],
            "aptas_por_rol": res["aptas_por_rol"],
            "descartes_por_rol": res["descartes_por_rol"],
            "descartes_por_rol_motivo": res["descartes_por_rol_motivo"],
            "resultados_por_horizonte": res["resultados_por_horizonte"],
        },
        "cobertura_por_fila": res["cobertura_tabla"],
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
                "diferencias_por_ciclo": v["diferencias_por_ciclo"],
                "ciclos_sin_grupo_comparable": v["ciclos_sin_grupo_comparable"],
                "updown_candidatos": v["updown_candidatos"],
            }
            for h, v in res["comparacion"].items()
        },
        "asociaciones_flujo_profundidad": {
            "metrica_principal": res["asociaciones"]["metrica_principal"],
            "unidades": res["asociaciones"]["unidades"],
            "ventana_flujo_ms": res["asociaciones"]["ventana_flujo_ms"],
            "disponibilidad": res["asociaciones"]["disponibilidad"],
            "regla_denominador_cero": res["asociaciones"]["regla_denominador_cero"],
            "n_filas_totales": res["asociaciones"]["n_filas_totales"],
            "por_horizonte": res["asociaciones"]["por_horizonte"],
        },
        "dependencia": {
            "resumen_por_simbolo": res["resumen_por_simbolo_dependencia"],
            "resumen_por_ciclo": res["resumen_por_ciclo"],
            "nota": "Los retornos de tres horizontes sobre una misma observación no son muestras independientes; los símbolos repetidos y las ventanas solapadas tampoco lo son automáticamente.",
        },
        "precios_y_costes": res["precios_y_costes"],
    }
    _escribir_json(out_tablas / "resumen_analisis_universo_liquidez_v1.json", tablas_publicar)
    print("Derivados detallados escritos en", out_derivados / "analisis_completo.json")
    print("Tablas pequeñas para Git escritas en", out_tablas / "resumen_analisis_universo_liquidez_v1.json")


if __name__ == "__main__":
    main()

