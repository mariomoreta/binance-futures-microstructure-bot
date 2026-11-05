"""Análisis OFFLINE y solo lectura de la captura pública public-pilot-1h-20261105a.

Lee unicamente el JSONL del dataset original sin modificarlo y escribe tablas
pequeñas (derivados) para publicación en Git. Los derivados detallados se dejan
fuera de Git. No conecta a Binance, no adquiere datos nuevos, no cambia reglas.
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
    r"C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\derivados"
)
TABLAS_GIT = Path(
    r"docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas"
)

HORIZONTES = ("5m", "15m", "60m")


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
    limpios = [v for v in valores if v is not None]
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


def _direccion_desde_move24h(move24h: float | None) -> str | None:
    """Proxy de la dirección que motivó la selección.

    Las observaciones individuales no traen campo `side`; usan `move_24h_pct`
    como indicador del movimiento previo. Se declara explícitamente como proxy
    y no se usa para inventar órdenes.
    """
    if move24h is None:
        return None
    if move24h > 0:
        return "UP_like"
    if move24h < 0:
        return "DOWN_like"
    return None


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

    # Índice de resultados por observation_id.
    resultados_por_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in resultados:
        oid = r.get("observation_id")
        if oid:
            resultados_por_id[str(oid)].append(r)

    # Mapeo observación -> ciclo por disponibilidad.seleccion_ms == ciclo.reference_ms.
    def ciclo_de_observacion(obs: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None]:
        disp = obs.get("disponibilidad") or {}
        sel_ms = disp.get("seleccion_ms")
        if isinstance(sel_ms, int) and sel_ms in ciclos_por_ref:
            c = ciclos_por_ref[sel_ms]
            return ciclos_ordenados.index(c), c
        return None, None

    # --- Tabla por rol, ciclo y horizonte ---
    por_ciclo_rol_horizonte: dict[tuple[int | None, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "observaciones": 0,
            "aptas": 0,
            "descartadas": 0,
            "resultados_disponibles": 0,
            "resultados_faltantes": 0,
            "simbolos": set(),
            "motivos_descartes": Counter(),
        }
    )
    motivos_por_rol: dict[str, Counter] = defaultdict(Counter)
    motivos_por_ciclo: dict[int | None, Counter] = defaultdict(Counter)

    for obs in observaciones:
        ciclo_idx, ciclo_obj = ciclo_de_observacion(obs)
        rol = obs.get("role") or "desconocido"
        simbolo = obs.get("symbol")
        estado = obs.get("estado")
        motivos = obs.get("motivos") or []

        clave_base = (ciclo_idx, rol, "todas")
        entrada = por_ciclo_rol_horizonte[clave_base]
        entrada["observaciones"] += 1
        if simbolo:
            entrada["simbolos"].add(simbolo)
        if estado == "observada":
            entrada["aptas"] += 1
        elif estado == "descartada":
            entrada["descartadas"] += 1
            for m in motivos:
                entrada["motivos_descartes"][m] += 1
                motivos_por_rol[rol][m] += 1
                motivos_por_ciclo[ciclo_idx][m] += 1

        if estado == "observada":
            for h in HORIZONTES:
                clave_h = (ciclo_idx, rol, h)
                ent_h = por_ciclo_rol_horizonte[clave_h]
                ent_h["observaciones"] += 1
                ent_h["aptas"] += 1
                if simbolo:
                    ent_h["simbolos"].add(simbolo)
                oid = obs.get("observation_id")
                res_h = [r for r in resultados_por_id.get(str(oid), []) if r.get("horizon") == h]
                if res_h:
                    ent_h["resultados_disponibles"] += 1
                else:
                    ent_h["resultados_faltantes"] += 1

    filas_cobertura = []
    for (ciclo_idx, rol, horizonte), ent in sorted(
        por_ciclo_rol_horizonte.items(), key=lambda x: (x[0][0] if x[0][0] is not None else 999, x[0][1], x[0][2])
    ):
        filas_cobertura.append(
            {
                "ciclo_idx": ciclo_idx,
                "rol": rol,
                "horizonte": horizonte,
                "observaciones": ent["observaciones"],
                "aptas": ent["aptas"],
                "descartadas": ent["descartadas"],
                "resultados_disponibles": ent["resultados_disponibles"],
                "resultados_faltantes": ent["resultados_faltantes"],
                "n_simbolos_distintos": len(ent["simbolos"]),
                "motivos_descartes": dict(ent["motivos_descartes"]),
            }
        )

    # --- Comparación candidatos vs comparadores por horizonte ---
    comparacion_por_horizonte: dict[str, dict[str, Any]] = {}
    filas_fuera_grupo: list[dict[str, Any]] = []

    for h in ("5m", "15m"):
        grupo_cand: list[float] = []
        grupo_comp: list[float] = []
        det_cand: list[dict[str, Any]] = []
        det_comp: list[dict[str, Any]] = []
        simbolos_cand: set[str] = set()
        simbolos_comp: set[str] = set()
        ciclos_cand: set[int | None] = set()
        ciclos_comp: set[int | None] = set()
        obs_cand_n = 0
        obs_comp_n = 0

        for obs in observaciones:
            if obs.get("estado") != "observada":
                continue
            rol = obs.get("role")
            simbolo = obs.get("symbol")
            oid = obs.get("observation_id")
            ciclo_idx, _ = ciclo_de_observacion(obs)
            res_h = [r for r in resultados_por_id.get(str(oid), []) if r.get("horizon") == h]
            if not res_h:
                filas_fuera_grupo.append(
                    {
                        "horizonte": h,
                        "rol": rol,
                        "simbolo": simbolo,
                        "ciclo_idx": ciclo_idx,
                        "motivo": "resultado_no_registrado_causa_UNKNOWN",
                    }
                )
                continue
            r = res_h[0]
            retorno = _seguro_float(r.get("retorno"))
            if retorno is None:
                continue
            registro = {
                "simbolo": simbolo,
                "ciclo_idx": ciclo_idx,
                "retorno": retorno,
                "decision_ms": obs.get("decision_ms"),
                "observation_id": oid,
                "precio_base": r.get("precio_base"),
                "precio_posterior": r.get("precio_posterior"),
                "precio_base_fuente": r.get("precio_base_fuente"),
                "precio_posterior_fuente": r.get("precio_posterior_fuente"),
                "horizonte_efectivo_ms": r.get("horizonte_efectivo_ms"),
                "direccion_proxy": _direccion_desde_move24h(
                    _seguro_float((obs.get("seleccion") or {}).get("move_24h_pct"))
                ),
            }
            if rol == "candidate":
                grupo_cand.append(retorno)
                det_cand.append(registro)
                obs_cand_n += 1
                simbolos_cand.add(simbolo)
                ciclos_cand.add(ciclo_idx)
            elif rol == "comparator":
                grupo_comp.append(retorno)
                det_comp.append(registro)
                obs_comp_n += 1
                simbolos_comp.add(simbolo)
                ciclos_comp.add(ciclo_idx)

        ciclos_comunes = ciclos_cand & ciclos_comp
        comparacion_por_horizonte[h] = {
            "candidatos": {
                "n_resultados": len(grupo_cand),
                "n_observaciones_originales": obs_cand_n,
                "n_simbolos": len(simbolos_cand),
                "n_ciclos": len(ciclos_cand),
                **_stats(grupo_cand),
                "proporcion_positivos": (
                    sum(1 for v in grupo_cand if v > 0) / len(grupo_cand) if grupo_cand else None
                ),
                "detalle": det_cand,
            },
            "comparadores": {
                "n_resultados": len(grupo_comp),
                "n_observaciones_originales": obs_comp_n,
                "n_simbolos": len(simbolos_comp),
                "n_ciclos": len(ciclos_comp),
                **_stats(grupo_comp),
                "proporcion_positivos": (
                    sum(1 for v in grupo_comp if v > 0) / len(grupo_comp) if grupo_comp else None
                ),
                "detalle": det_comp,
            },
            "diferencia_medias_descriptiva": (
                (statistics.fmean(grupo_cand) - statistics.fmean(grupo_comp))
                if grupo_cand and grupo_comp
                else None
            ),
            "ciclos_con_ambos_grupos": len(ciclos_comunes),
            "observaciones_fuera_de_grupo": len([f for f in filas_fuera_grupo if f["horizonte"] == h]),
        }

    # --- UP / DOWN por horizonte (candidatos, dirección por move_24h_pct proxy) ---
    updown_por_horizonte: dict[str, dict[str, Any]] = {}
    for h in ("5m", "15m"):
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
        updown_por_horizonte[h] = {
            lado: {
                "n": len(vals),
                **_stats(vals),
                "proporcion_positivos": sum(1 for v in vals if v > 0) / len(vals) if vals else None,
            }
            for lado, vals in grupos.items()
        }

    # --- Métricas exploratorias de liquidez/flujo (solo variables al decidir) ---
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
        for r in resultados_por_id.get(str(oid), []):
            h = r.get("horizon")
            if h not in ("5m", "15m"):
                continue
            retorno = _seguro_float(r.get("retorno"))
            filas_asoc.append(
                {
                    "horizonte": h,
                    "simbolo": obs.get("symbol"),
                    "rol": obs.get("role"),
                    "delta_ratio": delta_ratio,
                    "profundidad_notional_top20_USDT": profundidad,
                    "retorno": retorno,
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
    asociacion = {
        "metrica_flujo": metrica_flujo,
        "metrica_libro": metrica_libro,
        "n_filas": len(filas_asoc),
        "cobertura_profundidad_not_none": sum(
            1 for f in filas_asoc if f["profundidad_notional_top20_USDT"] is not None
        ),
        "cobertura_delta_ratio_not_none": sum(
            1 for f in filas_asoc if f["delta_ratio"] is not None
        ),
        "filas": filas_asoc,
    }

    # --- Dependencia: resumen por símbolo y por ciclo ---
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

    resumen_simbolos = {
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
        for c, v in sorted(por_ciclo_res.items(), key=lambda x: (x[0] is None, x[0] if x[0] is not None else -1))
    }

    # --- Precios y costes ---
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
        "cobertura_tabla": filas_cobertura,
        "comparacion": comparacion_por_horizonte,
        "updown": updown_por_horizonte,
        "asociacion_liquidez_flujo": asociacion,
        "resumen_por_simbolo": resumen_simbolos,
        "resumen_por_ciclo": resumen_ciclos,
        "ciclos_con_ambos_grupos_total": max(
            (v["ciclos_con_ambos_grupos"] for v in comparacion_por_horizonte.values()), default=0
        ),
        "motivos_por_rol": {k: dict(v) for k, v in motivos_por_rol.items()},
        "motivos_por_ciclo": {str(k) if k is not None else "desconocido": dict(v) for k, v in motivos_por_ciclo.items()},
        "precios_fuentes_detectadas": sorted(precios_fuentes),
        "nota_dependencia": "206 resultados no son 206 muestras independientes: una observación puede aportar dos horizontes y un símbolo puede repetirse entre ciclos.",
    }


def _escribir_json(ruta: Path, datos: Any) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Análisis offline de captura pública.")
    parser.add_argument("--jsonl", default=str(DATASET_JSONL), help="Ruta del JSONL del dataset.")
    args = parser.parse_args()

    jsonl = Path(args.jsonl)
    res = analizar(jsonl)

    # Derivados detallados fuera de Git.
    _escribir_json(DERIVADOS_DETALLADOS / "analisis_completo.json", res)

    # Tablas pequeñas para Git (sin detalle fila a fila de todas las observaciones).
    tablas_publicar: dict[str, Any] = {
        "run_id": "public-pilot-1h-20261105a",
        "base_commit": "f6eb22afa3e35f7e1ed0305e184bec81881b7991",
        "estado_corrida": "corrida_interrumpida_o_cierre_no_acreditado",
        "causa_parada": "UNKNOWN",
        "resumen_global": {
            k: v
            for k, v in res.items()
            if k
            not in (
                "comparacion",
                "updown",
                "asociacion_liquidez_flujo",
                "cobertura_tabla",
                "resumen_por_simbolo",
                "resumen_por_ciclo",
            )
        },
        "comparacion_candidatos_comparadores": {
            h: {
                "candidatos": {
                    "n_resultados": v["candidatos"]["n_resultados"],
                    "n_observaciones_originales": v["candidatos"]["n_observaciones_originales"],
                    "n_simbolos": v["candidatos"]["n_simbolos"],
                    "n_ciclos": v["candidatos"]["n_ciclos"],
                    "media": v["candidatos"]["media"],
                    "mediana": v["candidatos"]["mediana"],
                    "desv": v["candidatos"]["desv"],
                    "min": v["candidatos"]["min"],
                    "max": v["candidatos"]["max"],
                    "proporcion_positivos": v["candidatos"]["proporcion_positivos"],
                },
                "comparadores": {
                    "n_resultados": v["comparadores"]["n_resultados"],
                    "n_observaciones_originales": v["comparadores"]["n_observaciones_originales"],
                    "n_simbolos": v["comparadores"]["n_simbolos"],
                    "n_ciclos": v["comparadores"]["n_ciclos"],
                    "media": v["comparadores"]["media"],
                    "mediana": v["comparadores"]["mediana"],
                    "desv": v["comparadores"]["desv"],
                    "min": v["comparadores"]["min"],
                    "max": v["comparadores"]["max"],
                    "proporcion_positivos": v["comparadores"]["proporcion_positivos"],
                },
                "diferencia_medias_descriptiva": v["diferencia_medias_descriptiva"],
                "ciclos_con_ambos_grupos": v["ciclos_con_ambos_grupos"],
                "observaciones_fuera_de_grupo": v["observaciones_fuera_de_grupo"],
            }
            for h, v in res["comparacion"].items()
        },
        "updown_candidatos": res["updown"],
        "asociacion_liquidez_flujo_resumen": {
            "metrica_flujo": res["asociacion_liquidez_flujo"]["metrica_flujo"],
            "metrica_libro": res["asociacion_liquidez_flujo"]["metrica_libro"],
            "n_filas": res["asociacion_liquidez_flujo"]["n_filas"],
            "cobertura_profundidad_not_none": res["asociacion_liquidez_flujo"][
                "cobertura_profundidad_not_none"
            ],
            "cobertura_delta_ratio_not_none": res["asociacion_liquidez_flujo"][
                "cobertura_delta_ratio_not_none"
            ],
        },
        "dependencia": {
            "resumen_por_simbolo": res["resumen_por_simbolo"],
            "resumen_por_ciclo": res["resumen_por_ciclo"],
            "ciclos_con_ambos_grupos_total": res["ciclos_con_ambos_grupos_total"],
            "nota": res["nota_dependencia"],
        },
        "precios_y_costes": {
            "fuentes_detectadas": res["precios_fuentes_detectadas"],
            "nota": "proxy de fuentes mixtas: precio inicial del libro (libro_mid) frente a precio posterior de apertura de vela 1m (klines_apertura_1m). No es retorno mid-to-mid ni P&L.",
        },
    }
    _escribir_json(TABLAS_GIT / "resumen_analisis_offline.json", tablas_publicar)
    print("Análisis completo escrito en", DERIVADOS_DETALLADOS / "analisis_completo.json")
    print("Tablas pequeñas para Git escritas en", TABLAS_GIT / "resumen_analisis_offline.json")


if __name__ == "__main__":
    main()
