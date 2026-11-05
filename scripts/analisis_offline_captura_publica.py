"""Análisis OFFLINE y solo lectura de la captura pública public-pilot-1h-20261105a.

Lee únicamente el JSONL del dataset original sin modificarlo y escribe tablas
pequeñas para publicación en Git. Los derivados detallados se dejan fuera de Git.
No conecta a Binance, no adquiere datos nuevos, no cambia reglas ni tolerancias.

Salidas:
- Derivados detallados (fuera de Git):
  C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\derivados\analisis_v2\analisis_completo.json
- Tablas pequeñas (Git):
  docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas/resumen_analisis_offline_v2.json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DATASET_JSONL = Path(
    r"C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\observaciones.jsonl"
)
DERIVADOS_DETALLADOS = Path(
    r"C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\derivados\analisis_v2"
)
TABLAS_GIT = Path(
    r"docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas"
)

HORIZONTES = ("5m", "15m", "60m")
HORIZONTES_EVALUABLES = ("5m", "15m")
ROLES = ("candidate", "comparator")


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


def _direccion_desde_move24h(move24h: float | None) -> str | None:
    """Proxy de la dirección que motivó la selección.

    Las observaciones individuales de este dataset no traen campo `side`
    acreditado en la selección original; `move_24h_pct` se usa como proxy
    expreso y se declara aquí. No es una orden de compra ni venta.
    """
    if move24h is None:
        return None
    if move24h > 0:
        return "UP_like"
    if move24h < 0:
        return "DOWN_like"
    return None


def _pearson(xs: list[float], ys: list[float]) -> dict[str, Any]:
    """Correlación de Pearson. Nunca devuelve cero inventado."""
    pares = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pares)
    if n < 2:
        return {
            "n_pares_validos": n,
            "pearson": None,
            "motivo": "muestra_insuficiente_menor_a_2",
        }
    xs_f = [x for x, _ in pares]
    ys_f = [y for _, y in pares]
    mx = statistics.fmean(xs_f)
    my = statistics.fmean(ys_f)
    sx2 = sum((x - mx) ** 2 for x in xs_f) / n
    sy2 = sum((y - my) ** 2 for y in ys_f) / n
    if sx2 == 0.0 or sy2 == 0.0:
        return {
            "n_pares_validos": n,
            "pearson": None,
            "motivo": "varianza_cero_en_una_variable",
        }
    cov = sum((x - mx) * (y - my) for x, y in pares) / n
    return {
        "n_pares_validos": n,
        "pearson": cov / (math.sqrt(sx2) * math.sqrt(sy2)),
        "motivo": None,
    }


def _terciles(
    pares: list[tuple[float | None, float | None]],
) -> dict[str, Any]:
    """Terciles de delta_ratio (primera variable) frente a retorno (segunda).

    Corte por posición ordenada: bajo <= t1, t1 < x <= t2, alto > t2.
    Empates en el corte: se asignan según la posición ordenada (estable).
    """
    validos = [(x, y) for x, y in pares if x is not None and y is not None]
    n = len(validos)
    if n < 3:
        return {
            "n_validos": n,
            "metodo": "posicion_ordenada_terciles",
            "cortes": None,
            "motivo": "muestra_insuficiente_menor_a_3",
            "terciles": {},
        }
    xs_ordenados = sorted(x for x, _ in validos)
    t1 = xs_ordenados[n // 3]
    t2 = xs_ordenados[2 * n // 3]

    grupos: dict[str, list[float]] = {"bajo": [], "medio": [], "alto": []}
    for x, y in validos:
        if x <= t1:
            grupos["bajo"].append(y)
        elif x <= t2:
            grupos["medio"].append(y)
        else:
            grupos["alto"].append(y)

    return {
        "n_validos": n,
        "metodo": "posicion_ordenada_terciles",
        "cortes": {"t1": t1, "t2": t2},
        "regla_empates": "posicion_ordenada_estable: bajo<=t1, t1<x<=t2, alto>t2",
        "motivo": None,
        "terciles": {
            nombre: {
                "n": len(vals),
                "media_retorno": statistics.fmean(vals) if vals else None,
                "mediana_retorno": statistics.median(vals) if vals else None,
            }
            for nombre, vals in grupos.items()
        },
    }


def analizar(jsonl: Path = DATASET_JSONL) -> dict[str, Any]:
    objetos = _cargar_jsonl(jsonl)
    ciclos = [o for o in objetos if o.get("kind") == "ciclo"]
    observaciones = [o for o in objetos if o.get("kind") == "observacion"]
    resultados = [o for o in objetos if o.get("kind") == "resultado"]

    # Índice de ciclos por reference_ms (clave precisa).
    ciclos_por_ref: dict[int, dict[str, Any]] = {}
    for c in ciclos:
        rm = c.get("reference_ms")
        if isinstance(rm, int):
            ciclos_por_ref[rm] = c
    ciclos_ordenados = sorted(ciclos, key=lambda c: c.get("reference_ms", 0))

    # Índice de resultados por observation_id.
    resultados_por_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in resultados:
        oid = r.get("observation_id")
        if oid:
            resultados_por_id[str(oid)].append(r)

    def ciclo_de_observacion(obs: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None]:
        disp = obs.get("disponibilidad") or {}
        sel_ms = disp.get("seleccion_ms")
        if isinstance(sel_ms, int) and sel_ms in ciclos_por_ref:
            c = ciclos_por_ref[sel_ms]
            return ciclos_ordenados.index(c), c
        return None, None

    # ---- Embudo por rol ----
    seleccionadas_por_rol: dict[str, int] = Counter()
    aptas_por_rol: dict[str, int] = Counter()
    descartes_por_rol_motivo: dict[str, Counter] = defaultdict(Counter)
    descartes_por_rol: dict[str, int] = Counter()
    simbolos_por_rol_ciclo: dict[tuple[str, int | None], set[str]] = defaultdict(set)
    primer_ciclo_por_simbolo: dict[str, int | None] = {}
    ciclos_por_simbolo: dict[str, set[int | None]] = defaultdict(set)
    rol_por_simbolo_ciclo: dict[tuple[str, int | None], str] = {}

    for obs in observaciones:
        rol = obs.get("role") or "desconocido"
        seleccionadas_por_rol[rol] += 1
        ciclo_idx, ciclo_obj = ciclo_de_observacion(obs)
        simbolo = obs.get("symbol")
        estado = obs.get("estado")
        motivos = obs.get("motivos") or []

        if simbolo:
            ciclos_por_simbolo[simbolo].add(ciclo_idx)
            if simbolo not in primer_ciclo_por_simbolo or (
                ciclo_idx is not None
                and primer_ciclo_por_simbolo[simbolo] is not None
                and ciclo_idx < primer_ciclo_por_simbolo[simbolo]
            ):
                primer_ciclo_por_simbolo[simbolo] = ciclo_idx
            clave = (rol, ciclo_idx)
            simbolos_por_rol_ciclo[clave].add(simbolo)
            rol_por_simbolo_ciclo[clave] = rol

        if estado == "observada":
            aptas_por_rol[rol] += 1
        elif estado == "descartada":
            descartes_por_rol[rol] += 1
            for m in motivos:
                descartes_por_rol_motivo[rol][m] += 1

    # ---- Tabla por rol, ciclo y horizonte (cobertura) ----
    por_ciclo_rol_horizonte: dict[tuple[int | None, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "observaciones": 0,
            "aptas": 0,
            "descartadas": 0,
            "resultado_registrado": 0,
            "resultado_faltante": 0,
            "simbolos": set(),
            "motivos_descartes": Counter(),
        }
    )

    for obs in observaciones:
        ciclo_idx, _ = ciclo_de_observacion(obs)
        rol = obs.get("role") or "desconocido"
        simbolo = obs.get("symbol")
        estado = obs.get("estado")
        motivos = obs.get("motivos") or []

        clave_base = (ciclo_idx, rol, "todas")
        ent = por_ciclo_rol_horizonte[clave_base]
        ent["observaciones"] += 1
        if simbolo:
            ent["simbolos"].add(simbolo)
        if estado == "observada":
            ent["aptas"] += 1
        elif estado == "descartada":
            ent["descartadas"] += 1
            for m in motivos:
                ent["motivos_descartes"][m] += 1

        if estado == "observada":
            oid = obs.get("observation_id")
            for h in HORIZONTES:
                clave_h = (ciclo_idx, rol, h)
                ent_h = por_ciclo_rol_horizonte[clave_h]
                ent_h["observaciones"] += 1
                ent_h["aptas"] += 1
                if simbolo:
                    ent_h["simbolos"].add(simbolo)
                res_h = [
                    r
                    for r in resultados_por_id.get(str(oid), [])
                    if r.get("horizon") == h
                ]
                if res_h:
                    ent_h["resultado_registrado"] += 1
                else:
                    ent_h["resultado_faltante"] += 1

    filas_cobertura = []
    for (ciclo_idx, rol, horizonte), ent in sorted(
        por_ciclo_rol_horizonte.items(),
        key=lambda x: (x[0][0] if x[0][0] is not None else 999, x[0][1], x[0][2]),
    ):
        filas_cobertura.append(
            {
                "ciclo_idx": ciclo_idx,
                "rol": rol,
                "horizonte": horizonte,
                "seleccionadas": ent["observaciones"],
                "aptas": ent["aptas"],
                "descartadas": ent["descartadas"],
                "resultado_registrado": ent["resultado_registrado"],
                "resultado_faltante": ent["resultado_faltante"],
                "tasa_cobertura_sobre_seleccionadas": (
                    ent["resultado_registrado"] / ent["observaciones"]
                    if ent["observaciones"]
                    else None
                ),
                "tasa_cobertura_sobre_aptas": (
                    ent["resultado_registrado"] / ent["aptas"] if ent["aptas"] else None
                ),
                "n_simbolos_distintos": len(ent["simbolos"]),
                "motivos_descartes": dict(ent["motivos_descartes"]),
            }
        )

    # ---- Comparación candidatos vs comparadores por horizonte ----
    comparacion_por_horizonte: dict[str, dict[str, Any]] = {}
    detalle_ciclo: dict[str, list[dict[str, Any]]] = {}

    for h in HORIZONTES_EVALUABLES:
        grupo_cand: list[float] = []
        grupo_comp: list[float] = []
        simbolos_cand: set[str] = set()
        simbolos_comp: set[str] = set()
        ciclos_cand: set[int | None] = set()
        ciclos_comp: set[int | None] = set()

        for obs in observaciones:
            if obs.get("estado") != "observada":
                continue
            rol = obs.get("role")
            simbolo = obs.get("symbol")
            oid = obs.get("observation_id")
            ciclo_idx, _ = ciclo_de_observacion(obs)
            res_h = [r for r in resultados_por_id.get(str(oid), []) if r.get("horizon") == h]
            if not res_h:
                continue
            r = res_h[0]
            retorno = _seguro_float(r.get("retorno"))
            if retorno is None:
                continue
            registro = {
                "simbolo": simbolo,
                "ciclo_idx": ciclo_idx,
                "retorno": retorno,
                "retorno_pct": _pct(retorno),
                "decision_ms": obs.get("decision_ms"),
                "observation_id": oid,
                "precio_base": r.get("precio_base"),
                "precio_posterior": r.get("precio_posterior"),
                "precio_base_fuente": r.get("precio_base_fuente"),
                "precio_posterior_fuente": r.get("precio_posterior_fuente"),
                "horizonte_efectivo_ms": r.get("horizonte_efectivo_ms"),
            }
            if rol == "candidate":
                grupo_cand.append(retorno)
                simbolos_cand.add(simbolo)
                ciclos_cand.add(ciclo_idx)
            elif rol == "comparator":
                grupo_comp.append(retorno)
                simbolos_comp.add(simbolo)
                ciclos_comp.add(ciclo_idx)

        ciclos_comunes = ciclos_cand & ciclos_comp

        # Diferencia por ciclo (mismo peso a cada ciclo con ambos grupos).
        diferencias_por_ciclo: list[dict[str, Any]] = []
        for ci in sorted(ciclos_comunes, key=lambda x: (x is None, x if x is not None else -1)):
            cand_ci = [
                r.get("retorno")
                for obs in observaciones
                if obs.get("estado") == "observada"
                and obs.get("role") == "candidate"
                and ciclo_de_observacion(obs)[0] == ci
                for r in resultados_por_id.get(str(obs.get("observation_id")), [])
                if r.get("horizon") == h and _seguro_float(r.get("retorno")) is not None
            ]
            comp_ci = [
                r.get("retorno")
                for obs in observaciones
                if obs.get("estado") == "observada"
                and obs.get("role") == "comparator"
                and ciclo_de_observacion(obs)[0] == ci
                for r in resultados_por_id.get(str(obs.get("observation_id")), [])
                if r.get("horizon") == h and _seguro_float(r.get("retorno")) is not None
            ]
            cand_ci = [v for v in cand_ci if v is not None]
            comp_ci = [v for v in comp_ci if v is not None]
            if cand_ci and comp_ci:
                mc = statistics.fmean(cand_ci)
                mc_pct = _pct(mc)
                mco = statistics.fmean(comp_ci)
                mco_pct = _pct(mco)
                diferencias_por_ciclo.append(
                    {
                        "ciclo_idx": ci,
                        "n_candidatos": len(cand_ci),
                        "n_comparadores": len(comp_ci),
                        "media_candidatos": mc,
                        "media_candidatos_pct": mc_pct,
                        "media_comparadores": mco,
                        "media_comparadores_pct": mco_pct,
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

        media_agrupada_cand = _stats(grupo_cand)
        media_agrupada_comp = _stats(grupo_comp)
        diff_agrupada = None
        diff_agrupada_puntos = None
        if media_agrupada_cand["media"] is not None and media_agrupada_comp["media"] is not None:
            diff_agrupada = media_agrupada_cand["media"] - media_agrupada_comp["media"]
            diff_agrupada_puntos = _pct(diff_agrupada)

        comparacion_por_horizonte[h] = {
            "candidatos": {
                "n_resultados": len(grupo_cand),
                "n_simbolos": len(simbolos_cand),
                "n_ciclos": len(ciclos_cand),
                **media_agrupada_cand,
                "media_pct": media_agrupada_cand["media"] and _pct(media_agrupada_cand["media"]),
                "mediana_pct": media_agrupada_cand["mediana"] and _pct(media_agrupada_cand["mediana"]),
                "min_pct": media_agrupada_cand["min"] and _pct(media_agrupada_cand["min"]),
                "max_pct": media_agrupada_cand["max"] and _pct(media_agrupada_cand["max"]),
                "proporcion_positivos": (
                    sum(1 for v in grupo_cand if v > 0) / len(grupo_cand) if grupo_cand else None
                ),
            },
            "comparadores": {
                "n_resultados": len(grupo_comp),
                "n_simbolos": len(simbolos_comp),
                "n_ciclos": len(ciclos_comp),
                **media_agrupada_comp,
                "media_pct": media_agrupada_comp["media"] and _pct(media_agrupada_comp["media"]),
                "mediana_pct": media_agrupada_comp["mediana"] and _pct(media_agrupada_comp["mediana"]),
                "min_pct": media_agrupada_comp["min"] and _pct(media_agrupada_comp["min"]),
                "max_pct": media_agrupada_comp["max"] and _pct(media_agrupada_comp["max"]),
                "proporcion_positivos": (
                    sum(1 for v in grupo_comp if v > 0) / len(grupo_comp) if grupo_comp else None
                ),
            },
            "diferencia_medias_agrupada": diff_agrupada,
            "diferencia_medias_agrupada_puntos_porcentuales": diff_agrupada_puntos,
            "media_de_diferencias_por_ciclo": media_diferencias_por_ciclo,
            "media_de_diferencias_por_ciclo_puntos_porcentuales": media_diferencias_por_ciclo_puntos,
            "ciclos_con_ambos_grupos": len(ciclos_comunes),
            "diferencias_por_ciclo": diferencias_por_ciclo,
            "ciclos_sin_grupo_comparable": sorted(
                (ciclos_cand | ciclos_comp) - ciclos_comunes,
                key=lambda x: (x is None, x if x is not None else -1),
            ),
        }
        detalle_ciclo[h] = diferencias_por_ciclo

    # ---- UP / DOWN por horizonte (candidatos, dirección por move_24h_pct proxy) ----
    updown_por_horizonte: dict[str, dict[str, Any]] = {}
    for h in HORIZONTES_EVALUABLES:
        grupos: dict[str, list[float]] = {"UP_like": [], "DOWN_like": []}
        for obs in observaciones:
            if obs.get("estado") != "observada" or obs.get("role") != "candidate":
                continue
            oid = obs.get("observation_id")
            direccion = _direccion_desde_move24h(
                _seguro_float((obs.get("seleccion") or {}).get("move_24h_pct"))
            )
            if direccion not in grupos:
                continue
            for r in resultados_por_id.get(str(oid), []):
                if r.get("horizon") != h:
                    continue
                retorno = _seguro_float(r.get("retorno"))
                if retorno is None:
                    continue
                grupos[direccion].append(retorno)
        updown_por_horizonte[h] = {}
        for lado in ("UP_like", "DOWN_like"):
            vals = grupos[lado]
            st = _stats(vals)
            updown_por_horizonte[h][lado] = {
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
                "proporcion_positivos": sum(1 for v in vals if v > 0) / len(vals) if vals else None,
            }

    # ---- Asociaciones reproducibles (líquidez/flujo vs retorno) ----
    metrica_flujo = "delta_ratio"
    metrica_libro = "profundidad_notional_top20"

    filas_asoc: list[dict[str, Any]] = []
    for obs in observaciones:
        if obs.get("estado") != "observada":
            continue
        flujo = obs.get("flujo") or {}
        libro = obs.get("libro") or {}
        delta_ratio = _seguro_float(flujo.get("delta_ratio"))
        bid_not = _seguro_float(libro.get("bid_notional_top20"))
        ask_not = _seguro_float(libro.get("ask_notional_top20"))
        profundidad = None
        if bid_not is not None and ask_not is not None:
            profundidad = bid_not + ask_not
        oid = obs.get("observation_id")
        ciclo_idx, _ = ciclo_de_observacion(obs)
        for r in resultados_por_id.get(str(oid), []):
            h = r.get("horizon")
            if h not in HORIZONTES_EVALUABLES:
                continue
            retorno = _seguro_float(r.get("retorno"))
            filas_asoc.append(
                {
                    "horizonte": h,
                    "simbolo": obs.get("symbol"),
                    "ciclo_idx": ciclo_idx,
                    "rol": obs.get("role"),
                    "delta_ratio": delta_ratio,
                    "profundidad_notional_top20_USDT": profundidad,
                    "retorno": retorno,
                    "retorno_pct": _pct(retorno),
                    "ventana_flujo_ms": flujo.get("window_ms"),
                    "ventana_flujo_completa": flujo.get("ventana_completa"),
                    "libro_banda_5bps_cubierta": (obs.get("cobertura") or {}).get(
                        "libro_banda_5bps_cubierta"
                    ),
                    "direccion_proxy": _direccion_desde_move24h(
                        _seguro_float((obs.get("seleccion") or {}).get("move_24h_pct"))
                    ),
                }
            )

    asociaciones: dict[str, Any] = {
        "metrica_flujo": metrica_flujo,
        "metrica_libro": metrica_libro,
        "n_filas_totales": len(filas_asoc),
        "por_horizonte": {},
    }
    for h in HORIZONTES_EVALUABLES:
        f = [x for x in filas_asoc if x["horizonte"] == h]
        pares_dr = [(x["delta_ratio"], x["retorno"]) for x in f if x["delta_ratio"] is not None and x["retorno"] is not None]
        pares_prof = [
            (x["profundidad_notional_top20_USDT"], x["retorno"])
            for x in f
            if x["profundidad_notional_top20_USDT"] is not None and x["retorno"] is not None
        ]
        simbolos_h = sorted({x["simbolo"] for x in f if x["simbolo"]})
        ciclos_h = sorted({x["ciclo_idx"] for x in f if x["ciclo_idx"] is not None})
        asociaciones["por_horizonte"][h] = {
            "n_filas": len(f),
            "delta_ratio": {
                "n_pares_validos": len(pares_dr),
                "simbolos": simbolos_h,
                "ciclos": ciclos_h,
                "valores_excluidos_delta_ratio_none": sum(
                    1 for x in f if x["delta_ratio"] is None
                ),
                "valores_excluidos_retorno_none": sum(1 for x in f if x["retorno"] is None),
                **_pearson([a for a, _ in pares_dr], [b for _, b in pares_dr]),
            },
            "profundidad_notional_top20": {
                "n_pares_validos": len(pares_prof),
                "simbolos": simbolos_h,
                "ciclos": ciclos_h,
                "valores_excluidos_profundidad_none": sum(
                    1 for x in f if x["profundidad_notional_top20_USDT"] is None
                ),
                "valores_excluidos_retorno_none": sum(1 for x in f if x["retorno"] is None),
                **_pearson([a for a, _ in pares_prof], [b for _, b in pares_prof]),
            },
            "terciles_delta_ratio": _terciles([(x["delta_ratio"], x["retorno"]) for x in f]),
        }

    # ---- Resumen por símbolo (media y mediana por símbolo, horizonte, rol) ----
    por_simbolo_horizonte_rol: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"valores": [], "ciclos": set()}
    )
    rol_por_simbolo_ciclo_global: dict[tuple[str, int | None], str] = {}

    for r in resultados:
        simbolo = r.get("symbol")
        h = r.get("horizon")
        oid = r.get("observation_id", "")
        obs_origen = next((o for o in observaciones if o.get("observation_id") == oid), None)
        if not obs_origen or simbolo is None or h is None:
            continue
        ciclo_idx, _ = ciclo_de_observacion(obs_origen)
        rol = obs_origen.get("role") or "desconocido"
        retorno = _seguro_float(r.get("retorno"))
        if retorno is None:
            continue
        clave = (simbolo, h, rol)
        por_simbolo_horizonte_rol[clave]["valores"].append(retorno)
        if ciclo_idx is not None:
            por_simbolo_horizonte_rol[clave]["ciclos"].add(ciclo_idx)
            rol_por_simbolo_ciclo_global[(simbolo, ciclo_idx)] = rol

    resumen_simbolos: dict[str, Any] = {}
    for simbolo in sorted({s for (s, _, _) in por_simbolo_horizonte_rol}):
        entrada: dict[str, Any] = {"por_horizonte_rol": {}, "cambia_de_rol": False}
        roles_vistos: set[str] = set()
        for h in HORIZONTES_EVALUABLES:
            for rol in ROLES:
                clave = (simbolo, h, rol)
                if clave not in por_simbolo_horizonte_rol:
                    continue
                vals = por_simbolo_horizonte_rol[clave]["valores"]
                st = _stats(vals)
                roles_vistos.add(rol)
                entrada["por_horizonte_rol"][f"{h}|{rol}"] = {
                    "n": st["n"],
                    "media": st["media"],
                    "media_pct": _pct(st["media"]),
                    "mediana": st["mediana"],
                    "mediana_pct": _pct(st["mediana"]),
                    "desv": st["desv"],
                    "min": st["min"],
                    "max": st["max"],
                    "n_ciclos": len(por_simbolo_horizonte_rol[clave]["ciclos"]),
                }
        if len(roles_vistos) > 1:
            entrada["cambia_de_rol"] = True
        # Ponderación igual por símbolo: promedio de las medias de cada símbolo (se declara abajo).
        resumen_simbolos[simbolo] = entrada

    # Ponderación igual por símbolo: media de las medias por símbolo.
    ponderacion_por_simbolo: dict[str, Any] = {}
    for h in HORIZONTES_EVALUABLES:
        for rol in ROLES:
            medias_simbolo = []
            for simbolo, entrada in resumen_simbolos.items():
                clave_h = f"{h}|{rol}"
                if clave_h in entrada["por_horizonte_rol"]:
                    medias_simbolo.append(entrada["por_horizonte_rol"][clave_h]["media"])
            if medias_simbolo:
                m = statistics.fmean(medias_simbolo)
                ponderacion_por_simbolo[f"{h}|{rol}"] = {
                    "n_simbolos": len(medias_simbolo),
                    "media_de_medias_por_simbolo": m,
                    "media_de_medias_por_simbolo_pct": _pct(m),
                    "regla_ponderacion": "igual_peso_por_simbolo_promedio_de_medias_simbolo",
                }

    # ---- Dependencia ----
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
            por_simbolo[simbolo]["ciclos"].add(ciclo_idx)
            por_simbolo[simbolo]["horizontes"][r.get("horizon")] += 1
        if ciclo_idx is not None:
            por_ciclo_res[ciclo_idx]["n_resultados"] += 1
            por_ciclo_res[ciclo_idx]["simbolos"].add(simbolo or "desconocido")
            if rol == "candidate":
                por_ciclo_res[ciclo_idx]["candidatos"] += 1
            elif rol == "comparator":
                por_ciclo_res[ciclo_idx]["comparadores"] += 1

    resumen_simbolos_dep = {
        s: {
            "n_resultados": v["n_resultados"],
            "n_ciclos": len(v["ciclos"]),
            "horizontes": dict(v["horizontes"]),
        }
        for s, v in sorted(por_simbolo.items())
    }
    resumen_ciclos = {
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

    # ---- Precios y costes ----
    precios_fuentes: set[str] = set()
    for r in resultados:
        if r.get("precio_base_fuente"):
            precios_fuentes.add(r.get("precio_base_fuente"))
        if r.get("precio_posterior_fuente"):
            precios_fuentes.add(r.get("precio_posterior_fuente"))

    return {
        "total_lineas": len(objetos),
        "ciclos": len(ciclos),
        "observaciones_total": len(observaciones),
        "observaciones_aptas": sum(1 for o in observaciones if o.get("estado") == "observada"),
        "observaciones_descartadas": sum(1 for o in observaciones if o.get("estado") == "descartada"),
        "resultados_total": len(resultados),
        "resultados_por_horizonte": {h: sum(1 for r in resultados if r.get("horizon") == h) for h in HORIZONTES},
        "seleccionadas_por_rol": dict(seleccionadas_por_rol),
        "aptas_por_rol": dict(aptas_por_rol),
        "descartes_por_rol": dict(descartes_por_rol),
        "descartes_por_rol_motivo": {k: dict(v) for k, v in descartes_por_rol_motivo.items()},
        "cobertura_tabla": filas_cobertura,
        "comparacion": comparacion_por_horizonte,
        "updown": updown_por_horizonte,
        "asociaciones": asociaciones,
        "resumen_por_simbolo": resumen_simbolos,
        "ponderacion_por_simbolo": ponderacion_por_simbolo,
        "resumen_por_simbolo_dependencia": resumen_simbolos_dep,
        "resumen_por_ciclo": resumen_ciclos,
        "ciclos_con_ambos_grupos_total": max(
            (v["ciclos_con_ambos_grupos"] for v in comparacion_por_horizonte.values()), default=0
        ),
        "precios_fuentes_detectadas": sorted(precios_fuentes),
        "nota_dependencia": "206 resultados no son 206 muestras independientes: una observación puede aportar dos horizontes y un símbolo puede repetirse entre ciclos.",
    }


def _escribir_json(ruta: Path, datos: Any) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Análisis offline de captura pública (v2).")
    parser.add_argument("--jsonl", default=str(DATASET_JSONL), help="Ruta del JSONL del dataset.")
    args = parser.parse_args()

    jsonl = Path(args.jsonl)
    res = analizar(jsonl)

    # Derivados detallados fuera de Git.
    _escribir_json(DERIVADOS_DETALLADOS / "analisis_completo_v2.json", res)

    # Tablas pequeñas para Git.
    tablas_publicar: dict[str, Any] = {
        "run_id": "public-pilot-1h-20261105a",
        "base_commit": "5a404219d45d1584e085ac2208718bccdcb269fe",
        "estado_corrida": "corrida_interrumpida_o_cierre_no_acreditado",
        "causa_parada": "UNKNOWN",
        "resumen_global": {
            k: v
            for k, v in res.items()
            if k
            not in (
                "comparacion",
                "updown",
                "asociaciones",
                "cobertura_tabla",
                "resumen_por_simbolo",
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
                },
                "comparadores": {
                    "n_resultados": v["comparadores"]["n_resultados"],
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
                },
                "diferencia_medias_agrupada": v["diferencia_medias_agrupada"],
                "diferencia_medias_agrupada_puntos_porcentuales": v[
                    "diferencia_medias_agrupada_puntos_porcentuales"
                ],
                "media_de_diferencias_por_ciclo": v["media_de_diferencias_por_ciclo"],
                "media_de_diferencias_por_ciclo_puntos_porcentuales": v[
                    "media_de_diferencias_por_ciclo_puntos_porcentuales"
                ],
                "ciclos_con_ambos_grupos": v["ciclos_con_ambos_grupos"],
                "diferencias_por_ciclo": v["diferencias_por_ciclo"],
                "ciclos_sin_grupo_comparable": v["ciclos_sin_grupo_comparable"],
            }
            for h, v in res["comparacion"].items()
        },
        "updown_candidatos": res["updown"],
        "asociaciones_reproducibles": {
            h: {
                "n_filas": v["n_filas"],
                "delta_ratio": {
                    "n_pares_validos": v["delta_ratio"]["n_pares_validos"],
                    "pearson": v["delta_ratio"]["pearson"],
                    "motivo": v["delta_ratio"]["motivo"],
                    "simbolos": v["delta_ratio"]["simbolos"],
                    "ciclos": v["delta_ratio"]["ciclos"],
                    "valores_excluidos_delta_ratio_none": v["delta_ratio"][
                        "valores_excluidos_delta_ratio_none"
                    ],
                    "valores_excluidos_retorno_none": v["delta_ratio"][
                        "valores_excluidos_retorno_none"
                    ],
                },
                "profundidad_notional_top20": {
                    "n_pares_validos": v["profundidad_notional_top20"]["n_pares_validos"],
                    "pearson": v["profundidad_notional_top20"]["pearson"],
                    "motivo": v["profundidad_notional_top20"]["motivo"],
                    "simbolos": v["profundidad_notional_top20"]["simbolos"],
                    "ciclos": v["profundidad_notional_top20"]["ciclos"],
                    "valores_excluidos_profundidad_none": v["profundidad_notional_top20"][
                        "valores_excluidos_profundidad_none"
                    ],
                    "valores_excluidos_retorno_none": v["profundidad_notional_top20"][
                        "valores_excluidos_retorno_none"
                    ],
                },
                "terciles_delta_ratio": v["terciles_delta_ratio"],
            }
            for h, v in res["asociaciones"]["por_horizonte"].items()
        },
        "resumen_por_simbolo": res["resumen_por_simbolo"],
        "ponderacion_por_simbolo": res["ponderacion_por_simbolo"],
        "dependencia": {
            "resumen_por_simbolo": res["resumen_por_simbolo_dependencia"],
            "resumen_por_ciclo": res["resumen_por_ciclo"],
            "ciclos_con_ambos_grupos_total": res["ciclos_con_ambos_grupos_total"],
            "nota": res["nota_dependencia"],
        },
        "precios_y_costes": {
            "fuentes_detectadas": res["precios_fuentes_detectadas"],
            "nota": "proxy de fuentes mixtas: precio inicial del libro (libro_mid) frente a precio posterior de apertura de vela 1m (klines_apertura_1m). No es retorno mid-to-mid ni P&L.",
        },
    }
    _escribir_json(TABLAS_GIT / "resumen_analisis_offline_v2.json", tablas_publicar)
    print("Derivados detallados escritos en", DERIVADOS_DETALLADOS / "analisis_completo_v2.json")
    print("Tablas pequeñas para Git escritas en", TABLAS_GIT / "resumen_analisis_offline_v2.json")


if __name__ == "__main__":
    main()
