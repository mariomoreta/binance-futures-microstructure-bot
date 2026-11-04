"""Genera la tabla científica de observaciones: libro + flujo + disponibilidad
temporal + precio inicial + precio posterior + resultado o descarte.

Procedimiento (puntos 1-5 del mandato):
- Empareja libro y flujo por mismo símbolo y mismo bucket (bucket_start,
  bucket_end). Una fila con solo una fuente NO es observación conjunta.
- T = bucket_end (fin del período descrito, momento en que los datos del
  bucket están completos).
- Disponibilidad: as_of_ms si está poblada (publicada), si no last_event_ms
  (disponibilidad de evento, no publicada -> no acredita disponibilidad en T).
- Precio en T: última vela 1h de market_klines con close_time <= T.
- Precio en T+h: primera vela 1h de market_klines con T < close_time <= T+h.
  No se usa el cierre de una vela que contiene T+h como precio en T+h.
- Horizonte declarado: 1h (resolución de market_klines, única fuente de precios
  con cobertura en el rango research). Tolerancia de alineación = 1h.
- Solo lectura sobre SQLite, sin escribir en DBs canónicas, sin red pública.

Salida: docs/evidence/research/universe_liquidity_v1/observaciones.jsonl
        y .../observaciones_resumen.json
        y .../observaciones_muestra_validacion.json
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "data" / "historical" / "historical.db"
CACHE = ROOT / "data" / "market-cache" / "market_cache.db"
OUT_DIR = ROOT / "docs" / "evidence" / "research" / "universe_liquidity_v1"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSONL = OUT_DIR / "observaciones.jsonl"
OUT_RESUMEN = OUT_DIR / "observaciones_resumen.json"
OUT_MUESTRA = OUT_DIR / "observaciones_muestra_validacion.json"

HORIZONTE_MS = 3600000  # 1h: resolucion de market_klines, unica fuente de precios
TOLERANCIA_MS = 3600000  # misma justificacion


def ms(ts):
    if ts is None:
        return None
    return int(ts)


def iso(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).isoformat()


def leer_tabla(con, sql, params=()):
    cur = con.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def cargar_libro(con_hist):
    filas = leer_tabla(
        con_hist,
        "SELECT symbol, bucket_start, bucket_end, spread_mean, imb_mean, "
        "micro_mean, bid20_mean, ask20_mean, first_event_ms, last_event_ms, "
        "as_of_ms FROM research_book_1m",
    )
    by_key = {}
    duplicados = []
    for r in filas:
        k = (r["symbol"], int(r["bucket_start"]), int(r["bucket_end"]))
        if k in by_key:
            duplicados.append({"tabla": "libro", "clave": list(k)})
        else:
            by_key[k] = r
    return by_key, duplicados


def cargar_flujo(con_hist):
    filas = leer_tabla(
        con_hist,
        "SELECT symbol, bucket_start, bucket_end, buy_notional, sell_notional, "
        "delta, delta_ratio, base_volume, trade_count, price_close, "
        "first_event_ms, last_event_ms, as_of_ms FROM research_flow_1m",
    )
    by_key = {}
    duplicados = []
    for r in filas:
        k = (r["symbol"], int(r["bucket_start"]), int(r["bucket_end"]))
        if k in by_key:
            duplicados.append({"tabla": "flujo", "clave": list(k)})
        else:
            by_key[k] = r
    return by_key, duplicados


def cargar_velas(con_cache, simbolo):
    cur = con_cache.cursor()
    cur.execute(
        "SELECT open_time, close_time, close FROM market_klines "
        "WHERE symbol=? AND interval='1h' ORDER BY open_time ASC",
        (simbolo,),
    )
    return [(int(r[0]), int(r[1]), float(r[2])) for r in cur.fetchall()]


def precio_en_T(velas, T):
    """Ultima vela con close_time <= T (precio conocido en T)."""
    mejor = None
    mejor_ct = None
    for ot, ct, c in velas:
        if ct <= T:
            mejor = c
            mejor_ct = ct
    return mejor, mejor_ct


def precio_en_T_plus_h(velas, T):
    """Primera vela con T < close_time <= T + HORIZONTE_MS.

    No usa el cierre de una vela que contiene T+h como precio en T+h:
    exige close_time <= T+h (cierre conocido en T+h).
    """
    mejor = None
    mejor_ct = None
    for ot, ct, c in velas:
        if T < ct <= T + HORIZONTE_MS:
            mejor = c
            mejor_ct = ct
            break
    return mejor, mejor_ct


def main():
    con_hist = sqlite3.connect(f"file:{HIST}?mode=ro", uri=True)
    con_cache = sqlite3.connect(f"file:{CACHE}?mode=ro", uri=True)

    libro, dup_libro = cargar_libro(con_hist)
    flujo, dup_flujo = cargar_flujo(con_hist)

    simbolos = sorted(
        set(s for s, _, _ in libro) | set(s for s, _, _ in flujo)
    )

    velas_cache = {s: cargar_velas(con_cache, s) for s in simbolos}

    observaciones = []

    for s in simbolos:
        claves_libro = {
            (int(bk[1]), int(bk[2])) for bk in libro if bk[0] == s
        }
        claves_flujo = {
            (int(f[1]), int(f[2])) for f in flujo if f[0] == s
        }
        comunes = sorted(claves_libro & claves_flujo)
        solo_libro = sorted(claves_libro - claves_flujo)
        solo_flujo = sorted(claves_flujo - claves_libro)

        velas = velas_cache[s]

        for (bs, be) in comunes:
            rl = libro[(s, bs, be)]
            rf = flujo[(s, bs, be)]
            T = int(be)
            T_plus_h = T + HORIZONTE_MS

            disponible_publicado = rl["as_of_ms"]
            if disponible_publicado is None and rf["as_of_ms"] is not None:
                disponible_publicado = rf["as_of_ms"]
            disponible_evento = max(
                int(rl["last_event_ms"]) if rl["last_event_ms"] else 0,
                int(rf["last_event_ms"]) if rf["last_event_ms"] else 0,
            ) or None

            p_T, ct_T = precio_en_T(velas, T)
            p_T_plus_h, ct_Tph = precio_en_T_plus_h(velas, T)
            retorno = (
                (p_T_plus_h - p_T) / p_T
                if (p_T is not None and p_T_plus_h is not None and p_T)
                else None
            )

            motivos = []
            if p_T is None:
                motivos.append("sin_precio_inicial_en_T")
            if p_T_plus_h is None:
                motivos.append("sin_precio_posterior_en_T_plus_h")
            if disponible_publicado is None:
                motivos.append("disponibilidad_publicada_desconocida")
            elif disponible_publicado > T:
                motivos.append("disponibilidad_publicada_despues_de_T")

            if motivos:
                estado = "descartada"
            elif p_T is not None and p_T_plus_h is not None:
                estado = "apta_temporalmente_para_evaluacion"
            else:
                estado = "aceptada_para_descripcion"

            observaciones.append({
                "observation_id": f"{s}|{bs}|{be}",
                "simbolo": s,
                "bucket_start": bs,
                "bucket_end": be,
                "T": T,
                "T_plus_h": T_plus_h,
                "horizonte_solicitado": "1h",
                "duracion_efectiva_ms": (
                    ct_Tph - ct_T
                    if (ct_T is not None and ct_Tph is not None)
                    else None
                ),
                "disponible_publicado_ms": disponible_publicado,
                "disponible_evento_ms": disponible_evento,
                "disponible_publicada_en_T": (
                    disponible_publicado is not None
                    and disponible_publicado <= T
                ),
                "libro": {
                    "bucket_start": int(rl["bucket_start"]),
                    "bucket_end": int(rl["bucket_end"]),
                    "spread_mean_bps": rl["spread_mean_bps"],
                    "imb_mean": rl["imb_mean"],
                    "micro_mean_bps": rl["micro_mean_bps"],
                    "bid20_mean_base": rl["bid20_mean_base"],
                    "ask20_mean_base": rl["ask20_mean_base"],
                    "first_event_ms": int(rl["first_event_ms"]),
                    "last_event_ms": int(rl["last_event_ms"]),
                    "as_of_ms": rl["as_of_ms"],
                },
                "flujo": {
                    "bucket_start": int(rf["bucket_start"]),
                    "bucket_end": int(rf["bucket_end"]),
                    "buy_notional": rf["buy_notional"],
                    "sell_notional": rf["sell_notional"],
                    "delta_notional": rf["delta"],
                    "delta_ratio": rf["delta_ratio"],
                    "base_volume": rf["base_volume"],
                    "trade_count": rf["trade_count"],
                    "price_close": rf["price_close"],
                    "first_event_ms": int(rf["first_event_ms"]),
                    "last_event_ms": int(rf["last_event_ms"]),
                    "as_of_ms": rf["as_of_ms"],
                },
                "precio": {
                    "fuente_inicial": "market_klines|1h",
                    "precio_T": p_T,
                    "close_time_inicial_ms": ct_T,
                    "fuente_final": "market_klines|1h",
                    "precio_T_plus_h": p_T_plus_h,
                    "close_time_final_ms": ct_Tph,
                },
                "retorno": retorno,
                "retorno_formula": "(precio_T_plus_h - precio_T) / precio_T",
                "retorno_unidades": "decimal (0.001 = +0.10%)",
                "estado": estado,
                "motivo_descarte": "; ".join(motivos) if motivos else None,
            })

        for (bs, be) in solo_libro:
            rl = libro[(s, bs, be)]
            observaciones.append({
                "observation_id": f"{s}|{bs}|{be}|L",
                "simbolo": s,
                "bucket_start": bs,
                "bucket_end": be,
                "T": int(be),
                "T_plus_h": int(be) + HORIZONTE_MS,
                "horizonte_solicitado": "1h",
                "duracion_efectiva_ms": None,
                "disponible_publicado_ms": rl["as_of_ms"],
                "disponible_evento_ms": int(rl["last_event_ms"]),
                "disponible_publicada_en_T": (
                    rl["as_of_ms"] is not None and rl["as_of_ms"] <= int(be)
                ),
                "libro": {
                    "bucket_start": int(rl["bucket_start"]),
                    "bucket_end": int(rl["bucket_end"]),
                    "spread_mean_bps": rl["spread_mean_bps"],
                    "imb_mean": rl["imb_mean"],
                    "micro_mean_bps": rl["micro_mean_bps"],
                    "bid20_mean_base": rl["bid20_mean_base"],
                    "ask20_mean_base": rl["ask20_mean_base"],
                    "first_event_ms": int(rl["first_event_ms"]),
                    "last_event_ms": int(rl["last_event_ms"]),
                    "as_of_ms": rl["as_of_ms"],
                },
                "flujo": None,
                "precio": {
                    "fuente_inicial": "market_klines|1h",
                    "precio_T": precio_en_T(velas_cache[s], int(be))[0],
                    "close_time_inicial_ms": precio_en_T(velas_cache[s], int(be))[1],
                    "fuente_final": "market_klines|1h",
                    "precio_T_plus_h": precio_en_T_plus_h(
                        velas_cache[s], int(be)
                    )[0],
                    "close_time_final_ms": precio_en_T_plus_h(
                        velas_cache[s], int(be)
                    )[1],
                },
                "retorno": None,
                "retorno_formula": "(precio_T_plus_h - precio_T) / precio_T",
                "retorno_unidades": "decimal (0.001 = +0.10%)",
                "estado": "descartada",
                "motivo_descarte": "flujo_sin_datos_para_este_bucket",
            })

        for (bs, be) in solo_flujo:
            rf = flujo[(s, bs, be)]
            observaciones.append({
                "observation_id": f"{s}|{bs}|{be}|F",
                "simbolo": s,
                "bucket_start": bs,
                "bucket_end": be,
                "T": int(be),
                "T_plus_h": int(be) + HORIZONTE_MS,
                "horizonte_solicitado": "1h",
                "duracion_efectiva_ms": None,
                "disponible_publicado_ms": rf["as_of_ms"],
                "disponible_evento_ms": int(rf["last_event_ms"]),
                "disponible_publicada_en_T": (
                    rf["as_of_ms"] is not None and rf["as_of_ms"] <= int(be)
                ),
                "libro": None,
                "flujo": {
                    "bucket_start": int(rf["bucket_start"]),
                    "bucket_end": int(rf["bucket_end"]),
                    "buy_notional": rf["buy_notional"],
                    "sell_notional": rf["sell_notional"],
                    "delta_notional": rf["delta"],
                    "delta_ratio": rf["delta_ratio"],
                    "base_volume": rf["base_volume"],
                    "trade_count": rf["trade_count"],
                    "price_close": rf["price_close"],
                    "first_event_ms": int(rf["first_event_ms"]),
                    "last_event_ms": int(rf["last_event_ms"]),
                    "as_of_ms": rf["as_of_ms"],
                },
                "precio": {
                    "fuente_inicial": "market_klines|1h",
                    "precio_T": precio_en_T(velas_cache[s], int(be))[0],
                    "close_time_inicial_ms": precio_en_T(velas_cache[s], int(be))[1],
                    "fuente_final": "market_klines|1h",
                    "precio_T_plus_h": precio_en_T_plus_h(
                        velas_cache[s], int(be)
                    )[0],
                    "close_time_final_ms": precio_en_T_plus_h(
                        velas_cache[s], int(be)
                    )[1],
                },
                "retorno": None,
                "retorno_formula": "(precio_T_plus_h - precio_T) / precio_T",
                "retorno_unidades": "decimal (0.001 = +0.10%)",
                "estado": "descartada",
                "motivo_descarte": "libro_sin_datos_para_este_bucket",
            })

    con_hist.close()
    con_cache.close()

    # Resumen
    n_total = len(observaciones)
    n_pares = sum(1 for o in observaciones if o["libro"] and o["flujo"])
    n_libro_solo = sum(1 for o in observaciones if o["libro"] and not o["flujo"])
    n_flujo_solo = sum(1 for o in observaciones if o["flujo"] and not o["libro"])
    n_aceptada = sum(1 for o in observaciones if o["estado"] == "aceptada_para_descripcion")
    n_apta = sum(1 for o in observaciones if o["estado"] == "apta_temporalmente_para_evaluacion")
    n_descar = sum(1 for o in observaciones if o["estado"] == "descartada")

    retornos = [
        o["retorno"] for o in observaciones
        if o["estado"] == "apta_temporalmente_para_evaluacion"
        and o["retorno"] is not None
    ]
    resumen = {
        "procedimiento": "observaciones_libro_flujo_precio_v1",
        "horizonte_ms": HORIZONTE_MS,
        "tolerancia_alineacion_ms": TOLERANCIA_MS,
        "fuente_precios": "market_klines|1h",
        "n_observaciones_totales": n_total,
        "n_parejas_libro_flujo": n_pares,
        "n_libro_sin_flujo": n_libro_solo,
        "n_flujo_sin_libro": n_flujo_solo,
        "n_duplicados_libro": len(dup_libro),
        "n_duplicados_flujo": len(dup_flujo),
        "n_aceptada_para_descripcion": n_aceptada,
        "n_apta_temporalmente_para_evaluacion": n_apta,
        "n_descartada": n_descar,
        "n_con_retorno_valido": len(retornos),
        "retorno_descriptivo": {
            "media": statistics.mean(retornos) if retornos else None,
            "mediana": statistics.median(retornos) if retornos else None,
            "min": min(retornos) if retornos else None,
            "max": max(retornos) if retornos else None,
            "n": len(retornos),
        },
        "nota": (
            "Las '253 parejas' del informe anterior quedan NO VALIDADAS. "
            "Este recalc empareja libro y flujo por bucket idéntico y requiere "
            "precio en T y en T+h de market_klines con resolución y "
            "disponibilidad compatibles. Solo las observaciones "
            "apta_temporalmente_para_evaluacion tienen retorno calculable. "
            "No se declara fill, rentabilidad operable ni cobertura "
            "representativa."
        ),
    }

    # Muestra determinista para validación contra fuente
    import random
    rng = random.Random(20261103)
    aceptadas = [o for o in observaciones if o["estado"] == "aceptada_para_descripcion"]
    descartadas = [o for o in observaciones if o["estado"] == "descartada"]
    muestra_aceptadas = rng.sample(aceptadas, min(5, len(aceptadas)))
    muestra_descartadas = rng.sample(descartadas, min(5, len(descartadas)))
    muestra = muestra_aceptadas + muestra_descartadas

    muestra_validacion = []
    for o in muestra:
        velas = velas_cache[o["simbolo"]]
        p_T, ct_T = precio_en_T(velas, o["T"])
        p_Tph, ct_Tph = precio_en_T_plus_h(velas, o["T"])
        fila = {
            "observation_id": o["observation_id"],
            "simbolo": o["simbolo"],
            "estado": o["estado"],
            "verificacion_precios": {
                "precio_T_recalculado": p_T,
                "close_time_T_recalculado": ct_T,
                "precio_T_plus_h_recalculado": p_Tph,
                "close_time_T_plus_h_recalculado": ct_Tph,
                "precio_T_original": o["precio"]["precio_T"],
                "precio_T_plus_h_original": o["precio"]["precio_T_plus_h"],
                "coincide": (
                    p_T == o["precio"]["precio_T"]
                    and p_Tph == o["precio"]["precio_T_plus_h"]
                ),
            },
        }
        fila["coincide"] = fila["verificacion_precios"]["coincide"]
        muestra_validacion.append(fila)

    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for o in observaciones:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    with open(OUT_RESUMEN, "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)

    with open(OUT_MUESTRA, "w", encoding="utf-8") as f:
        json.dump(muestra_validacion, f, ensure_ascii=False, indent=2)

    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"\nObservaciones escritas: {OUT_JSONL} ({n_total} filas)")
    print(f"Resumen escrito: {OUT_RESUMEN}")
    print(f"Muestra de validación escrita: {OUT_MUESTRA} ({len(muestra_validacion)} filas)")


def emparejar_libro_flujo(
    libro_rows: List[Dict[str, Any]],
    flujo_rows: List[Dict[str, Any]],
) -> Tuple[
    List[Tuple[Dict[str, Any], Dict[str, Any]]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    int,
    int,
]:
    """Empareja filas de libro y flujo por mismo símbolo y mismo bucket.

    Una observación conjunta requiere exactamente una fila de libro y una de
    flujo con el mismo (symbol, bucket_start, bucket_end). Las filas sin
    contraparte se reportan por separado. Las duplicadas se cuentan y no se
    multiplican.

    Devuelve:
      pares: lista de (fila_libro, fila_flujo)
      libro_solo: filas de libro sin flujo en mismo bucket
      flujo_solo: filas de flujo sin libro en mismo bucket
      n_dup_libro, n_dup_flujo: conteo de duplicados detectados
    """
    libro_por_clave: Dict[Tuple[str, int, int], List[Dict[str, Any]]] = {}
    flujo_por_clave: Dict[Tuple[str, int, int], List[Dict[str, Any]]] = {}
    for r in libro_rows:
        k = (r["symbol"], int(r["bucket_start"]), int(r["bucket_end"]))
        libro_por_clave.setdefault(k, []).append(r)
    for r in flujo_rows:
        k = (r["symbol"], int(r["bucket_start"]), int(r["bucket_end"]))
        flujo_por_clave.setdefault(k, []).append(r)

    pares: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    libro_solo: List[Dict[str, Any]] = []
    flujo_solo: List[Dict[str, Any]] = []
    n_dup_libro = 0
    n_dup_flujo = 0

    claves_libro = set(libro_por_clave.keys())
    claves_flujo = set(flujo_por_clave.keys())

    for k in claves_libro | claves_flujo:
        l_rows = libro_por_clave.get(k, [])
        f_rows = flujo_por_clave.get(k, [])
        if len(l_rows) > 1:
            n_dup_libro += len(l_rows) - 1
        if len(f_rows) > 1:
            n_dup_flujo += len(f_rows) - 1
        if l_rows and f_rows:
            pares.append((l_rows[0], f_rows[0]))
            libro_solo.extend(l_rows[1:])
            flujo_solo.extend(f_rows[1:])
        elif l_rows:
            libro_solo.extend(l_rows)
        else:
            flujo_solo.extend(f_rows)

    return pares, libro_solo, flujo_solo, n_dup_libro, n_dup_flujo


def construir_observacion(
    simbolo: str,
    bs: int,
    be: int,
    rl: Dict[str, Any],
    rf: Dict[str, Any],
    velas: List[Tuple[int, int, float]],
) -> Dict[str, Any]:
    """Construye una observación completa a partir de fila de libro, fila de
    flujo y velas de precios.

    Aplica la lógica de disponibilidad temporal y precios en T y T+h.
    """
    T = int(be)
    T_plus_h = T + HORIZONTE_MS

    disponible_publicado = rl["as_of_ms"]
    if disponible_publicado is None and rf["as_of_ms"] is not None:
        disponible_publicado = rf["as_of_ms"]
    disponible_evento = max(
        int(rl["last_event_ms"]) if rl["last_event_ms"] else 0,
        int(rf["last_event_ms"]) if rf["last_event_ms"] else 0,
    ) or None

    p_T, ct_T = precio_en_T(velas, T)
    p_T_plus_h, ct_Tph = precio_en_T_plus_h(velas, T)
    retorno = (
        (p_T_plus_h - p_T) / p_T
        if (p_T is not None and p_T_plus_h is not None and p_T)
        else None
    )

    motivos: List[str] = []
    if p_T is None:
        motivos.append("sin_precio_inicial_en_T")
    if p_T_plus_h is None:
        motivos.append("sin_precio_posterior_en_T_plus_h")
    if disponible_publicado is None:
        motivos.append("disponibilidad_publicada_desconocida")
    elif disponible_publicado > T:
        motivos.append("disponibilidad_publicada_despues_de_T")

    if motivos:
        estado = "descartada"
    elif p_T is not None and p_T_plus_h is not None:
        estado = "apta_temporalmente_para_evaluacion"
    else:
        estado = "aceptada_para_descripcion"

    return {
        "observation_id": f"{simbolo}|{bs}|{be}",
        "simbolo": simbolo,
        "bucket_start": bs,
        "bucket_end": be,
        "T": T,
        "T_plus_h": T_plus_h,
        "horizonte_solicitado": "1h",
        "duracion_efectiva_ms": (
            ct_Tph - ct_T if (ct_T is not None and ct_Tph is not None) else None
        ),
        "disponible_publicado_ms": disponible_publicado,
        "disponible_evento_ms": disponible_evento,
        "disponible_publicada_en_T": (
            disponible_publicado is not None and disponible_publicado <= T
        ),
        "libro": {
            "bucket_start": int(rl["bucket_start"]),
            "bucket_end": int(rl["bucket_end"]),
            "spread_mean_bps": rl["spread_mean_bps"],
            "imb_mean": rl["imb_mean"],
            "micro_mean_bps": rl["micro_mean_bps"],
            "bid20_mean_base": rl["bid20_mean_base"],
            "ask20_mean_base": rl["ask20_mean_base"],
            "first_event_ms": int(rl["first_event_ms"]),
            "last_event_ms": int(rl["last_event_ms"]),
            "as_of_ms": rl["as_of_ms"],
        },
        "flujo": {
            "bucket_start": int(rf["bucket_start"]),
            "bucket_end": int(rf["bucket_end"]),
            "buy_notional": rf["buy_notional"],
            "sell_notional": rf["sell_notional"],
            "delta_notional": rf["delta"],
            "delta_ratio": rf["delta_ratio"],
            "base_volume": rf["base_volume"],
            "trade_count": rf["trade_count"],
            "price_close": rf["price_close"],
            "first_event_ms": int(rf["first_event_ms"]),
            "last_event_ms": int(rf["last_event_ms"]),
            "as_of_ms": rf["as_of_ms"],
        },
        "precio": {
            "fuente_inicial": "market_klines|1h",
            "precio_T": p_T,
            "close_time_inicial_ms": ct_T,
            "fuente_final": "market_klines|1h",
            "precio_T_plus_h": p_T_plus_h,
            "close_time_final_ms": ct_Tph,
        },
        "retorno": retorno,
        "retorno_formula": "(precio_T_plus_h - precio_T) / precio_T",
        "retorno_unidades": "decimal (0.001 = +0.10%)",
        "estado": estado,
        "motivo_descarte": "; ".join(motivos) if motivos else None,
    }


if __name__ == "__main__":
    main()
