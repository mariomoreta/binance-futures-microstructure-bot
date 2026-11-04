"""Genera la tabla científica de observaciones: libro + flujo + disponibilidad
temporal + precio inicial + precio posterior + resultado o descarte.

Procedimiento:
- Empareja libro y flujo por mismo símbolo y mismo bucket (bucket_start,
  bucket_end). Una fila con solo una fuente NO es observación conjunta: se
  conserva con su motivo explícito.
- T = bucket_end (fin del período descrito).
- Disponibilidad publicada: `as_of_ms` de CADA fuente, clasificado en tres
  clases mutuamente excluyentes:
    * `desconocida`            -> as_of_ms IS NULL (procedencia no registrada)
    * `publicada_en_T`         -> as_of_ms <= bucket_end
    * `publicada_despues_de_T` -> as_of_ms > bucket_end
  No se usa `last_event_ms` como sustituto de disponibilidad publicada ni se
  rellena un `as_of_ms` ausente: la ausencia de trazabilidad se declara.
- Estados separados (no se confunde descripción con causalidad):
    * `descartada`                        -> falta pareja o falta precio.
    * `aceptada_para_descripcion`         -> pareja y precios, pero la
      disponibilidad publicada en T NO está acreditada (desconocida o
      posterior). Es una observación DESCRIPTIVA, no causalmente evaluable.
    * `apta_temporalmente_para_evaluacion` -> pareja, precios y AMBAS fuentes
      con as_of_ms <= T. Solo este estado entra en el agregado evaluable.
- Precio en T: última vela 1h de market_klines con close_time <= T.
- Precio en T+h: primera vela 1h con T < close_time <= T+h. No se usa el
  cierre de una vela que contiene T+h como precio en T+h.
- Horizonte declarado: 1h (resolución de market_klines, única fuente de precios
  con cobertura en el rango research). Tolerancia de alineación = 1h.
- Solo lectura sobre SQLite, sin escribir en DBs canónicas, sin red pública.

Salida: docs/evidence/research/universe_liquidity_v1/observaciones.jsonl
        y .../observaciones_resumen.json
        y .../observaciones_muestra_validacion.json
"""
from __future__ import annotations

import bisect
import json
import sqlite3
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "data" / "historical" / "historical.db"
CACHE = ROOT / "data" / "market-cache" / "market_cache.db"
OUT_DIR = ROOT / "docs" / "evidence" / "research" / "universe_liquidity_v1"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSONL = OUT_DIR / "observaciones.jsonl"
OUT_RESUMEN = OUT_DIR / "observaciones_resumen.json"
OUT_MUESTRA = OUT_DIR / "observaciones_muestra_validacion.json"

HORIZONTE_MS = 3600000  # 1h: resolución de market_klines, única fuente de precios
TOLERANCIA_MS = 3600000  # misma justificación

CLASE_DESCONOCIDA = "desconocida"
CLASE_EN_T = "publicada_en_T"
CLASE_DESPUES_DE_T = "publicada_despues_de_T"

ESTADO_DESCARTADA = "descartada"
ESTADO_DESCRIPTIVA = "aceptada_para_descripcion"
ESTADO_EVALUABLE = "apta_temporalmente_para_evaluacion"


def leer_tabla(con, sql, params=()):
    cur = con.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def cargar_libro(con_hist):
    """Carga filas de libro indexadas por (symbol, bucket_start, bucket_end)."""
    filas = leer_tabla(
        con_hist,
        "SELECT symbol, bucket_start, bucket_end, spread_mean, imb_mean, "
        "micro_mean, bid20_mean, ask20_mean, first_event_ms, last_event_ms, "
        "as_of_ms, run_id, price_source FROM research_book_1m",
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
    """Carga filas de flujo indexadas por (symbol, bucket_start, bucket_end)."""
    filas = leer_tabla(
        con_hist,
        "SELECT symbol, bucket_start, bucket_end, buy_notional, sell_notional, "
        "delta, delta_ratio, base_volume, trade_count, price_close, "
        "first_event_ms, last_event_ms, as_of_ms, run_id, price_source "
        "FROM research_flow_1m",
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
    """Empareja filas de libro y flujo por mismo símbolo y bucket.

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

    for clave in claves_libro | claves_flujo:
        l_rows = libro_por_clave.get(clave, [])
        f_rows = flujo_por_clave.get(clave, [])
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


def cargar_velas(con_cache, simbolo):
    cur = con_cache.cursor()
    cur.execute(
        "SELECT open_time, close_time, close FROM market_klines "
        "WHERE symbol=? AND interval='1h' ORDER BY open_time ASC",
        (simbolo,),
    )
    return [(int(r[0]), int(r[1]), float(r[2])) for r in cur.fetchall()]


class SeriePrecios:
    """Índice ordenado por close_time para búsquedas O(log n) por observación."""

    def __init__(self, velas: List[Tuple[int, int, float]]) -> None:
        ordenadas = sorted(velas, key=lambda v: int(v[1]))
        self._ct = [int(v[1]) for v in ordenadas]
        self._close = [float(v[2]) for v in ordenadas]

    def en_T(self, T: int) -> Tuple[Optional[float], Optional[int]]:
        """Última vela con close_time <= T (precio conocido en T)."""
        i = bisect.bisect_right(self._ct, int(T)) - 1
        if i < 0:
            return None, None
        return self._close[i], self._ct[i]

    def en_T_plus_h(self, T: int) -> Tuple[Optional[float], Optional[int]]:
        """Primera vela con T < close_time <= T + HORIZONTE_MS.

        No usa el cierre de una vela que contiene T+h como precio en T+h.
        """
        i = bisect.bisect_right(self._ct, int(T))
        limite = int(T) + HORIZONTE_MS
        if i < len(self._ct) and self._ct[i] <= limite:
            return self._close[i], self._ct[i]
        return None, None


def precio_en_T(velas, T):
    """Última vela con close_time <= T (precio conocido en T)."""
    return SeriePrecios(velas).en_T(T)


def precio_en_T_plus_h(velas, T):
    """Primera vela con T < close_time <= T + HORIZONTE_MS."""
    return SeriePrecios(velas).en_T_plus_h(T)


def clasificar_disponibilidad(as_of_ms: Optional[int], T: int) -> str:
    """Clase de disponibilidad publicada de UNA fuente respecto de T.

    NULL no se interpreta como disponible ni como posterior: es desconocida.
    """
    if as_of_ms is None:
        return CLASE_DESCONOCIDA
    if int(as_of_ms) <= int(T):
        return CLASE_EN_T
    return CLASE_DESPUES_DE_T


def _velas_o_serie(velas) -> SeriePrecios:
    return velas if isinstance(velas, SeriePrecios) else SeriePrecios(velas)


def construir_observacion(
    simbolo: str,
    bs: int,
    be: int,
    rl: Optional[Dict[str, Any]],
    rf: Optional[Dict[str, Any]],
    velas,
) -> Dict[str, Any]:
    """Construye una observación a partir de fila de libro, fila de flujo y
    precios. Aplica la lógica de disponibilidad temporal y precios en T/T+h.

    `rl` o `rf` pueden ser None: la fila sin contraparte se conserva como
    observación descartada con su motivo, nunca se descarta en silencio.
    """
    T = int(be)
    T_plus_h = T + HORIZONTE_MS
    serie = _velas_o_serie(velas)

    clase_libro = (
        clasificar_disponibilidad(rl.get("as_of_ms"), T) if rl else None
    )
    clase_flujo = (
        clasificar_disponibilidad(rf.get("as_of_ms"), T) if rf else None
    )
    ambas_en_T = clase_libro == CLASE_EN_T and clase_flujo == CLASE_EN_T

    as_of_libro = rl.get("as_of_ms") if rl else None
    as_of_flujo = rf.get("as_of_ms") if rf else None
    disponible_publicado = (
        max(int(as_of_libro), int(as_of_flujo)) if ambas_en_T else None
    )
    eventos = [
        int(r["last_event_ms"])
        for r in (rl, rf)
        if r is not None and r.get("last_event_ms") is not None
    ]
    disponible_evento = max(eventos) if eventos else None

    p_T, ct_T = serie.en_T(T)
    p_T_plus_h, ct_Tph = serie.en_T_plus_h(T)
    retorno = (
        (p_T_plus_h - p_T) / p_T
        if (p_T is not None and p_T_plus_h is not None and p_T)
        else None
    )

    motivos: List[str] = []
    if rl is None:
        motivos.append("libro_sin_datos_para_este_bucket")
    if rf is None:
        motivos.append("flujo_sin_datos_para_este_bucket")
    if p_T is None:
        motivos.append("sin_precio_inicial_en_T")
    if p_T_plus_h is None:
        motivos.append("sin_precio_posterior_en_T_plus_h")
    for fuente, clase in (("libro", clase_libro), ("flujo", clase_flujo)):
        if clase == CLASE_DESCONOCIDA:
            motivos.append("disponibilidad_publicada_desconocida_%s" % fuente)
        elif clase == CLASE_DESPUES_DE_T:
            motivos.append("disponibilidad_publicada_despues_de_T_%s" % fuente)

    falta_pareja_o_precio = (
        rl is None or rf is None or p_T is None or p_T_plus_h is None
    )
    if falta_pareja_o_precio:
        estado = ESTADO_DESCARTADA
    elif ambas_en_T:
        estado = ESTADO_EVALUABLE
    else:
        estado = ESTADO_DESCRIPTIVA

    motivo_descarte = "; ".join(motivos) if estado == ESTADO_DESCARTADA else None
    motivo_no_evaluable = (
        "; ".join(motivos) if estado == ESTADO_DESCRIPTIVA else None
    )

    libro_dict = None
    if rl is not None:
        libro_dict = {
            "bucket_start": int(rl["bucket_start"]),
            "bucket_end": int(rl["bucket_end"]),
            "spread_mean_bps": rl["spread_mean"],
            "imb_mean": rl["imb_mean"],
            "micro_mean_bps": rl["micro_mean"],
            "bid20_mean_base": rl["bid20_mean"],
            "ask20_mean_base": rl["ask20_mean"],
            "first_event_ms": int(rl["first_event_ms"]),
            "last_event_ms": int(rl["last_event_ms"]),
            "as_of_ms": rl["as_of_ms"],
            "run_id": rl.get("run_id"),
            "price_source": rl.get("price_source"),
        }

    flujo_dict = None
    if rf is not None:
        flujo_dict = {
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
            "run_id": rf.get("run_id"),
            "price_source": rf.get("price_source"),
        }

    sufijo = "" if (rl is not None and rf is not None) else (
        "|L" if rl is not None else "|F"
    )

    return {
        "observation_id": f"{simbolo}|{bs}|{be}{sufijo}",
        "simbolo": simbolo,
        "bucket_start": bs,
        "bucket_end": be,
        "T": T,
        "T_plus_h": T_plus_h,
        "horizonte_solicitado": "1h",
        "duracion_efectiva_ms": (
            ct_Tph - ct_T if (ct_T is not None and ct_Tph is not None) else None
        ),
        "disponibilidad": {
            "libro": {"as_of_ms": as_of_libro, "clase": clase_libro},
            "flujo": {"as_of_ms": as_of_flujo, "clase": clase_flujo},
            "ambas_publicadas_en_T": ambas_en_T,
            "disponible_publicado_ms": disponible_publicado,
            "disponible_evento_ms": disponible_evento,
        },
        "disponible_publicado_ms": disponible_publicado,
        "disponible_evento_ms": disponible_evento,
        "disponible_publicada_en_T": ambas_en_T,
        "libro": libro_dict,
        "flujo": flujo_dict,
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
        "evaluable_causalmente": estado == ESTADO_EVALUABLE,
        "motivos": motivos,
        "motivo_descarte": motivo_descarte,
        "motivo_no_evaluable": motivo_no_evaluable,
    }


def _agregado(retornos: List[float]) -> Dict[str, Any]:
    return {
        "n": len(retornos),
        "media": statistics.mean(retornos) if retornos else None,
        "mediana": statistics.median(retornos) if retornos else None,
        "min": min(retornos) if retornos else None,
        "max": max(retornos) if retornos else None,
    }


def _conteo_as_of(filas: List[Dict[str, Any]]) -> Dict[str, int]:
    """Conteo por clase de as_of_ms respecto de su propio bucket_end."""
    conteo = {CLASE_DESCONOCIDA: 0, CLASE_EN_T: 0, CLASE_DESPUES_DE_T: 0}
    for r in filas:
        conteo[clasificar_disponibilidad(r.get("as_of_ms"), int(r["bucket_end"]))] += 1
    return {
        "total": len(filas),
        "as_of_null": conteo[CLASE_DESCONOCIDA],
        "as_of_presente_en_o_antes_del_bucket": conteo[CLASE_EN_T],
        "as_of_posterior_al_bucket": conteo[CLASE_DESPUES_DE_T],
    }


def main():
    con_hist = sqlite3.connect(f"file:{HIST}?mode=ro", uri=True)
    con_cache = sqlite3.connect(f"file:{CACHE}?mode=ro", uri=True)

    libro, dup_libro = cargar_libro(con_hist)
    flujo, dup_flujo = cargar_flujo(con_hist)

    simbolos = sorted(
        set(s for s, _, _ in libro) | set(s for s, _, _ in flujo)
    )
    series = {s: SeriePrecios(cargar_velas(con_cache, s)) for s in simbolos}

    pares, libro_solo, flujo_solo, _, _ = emparejar_libro_flujo(
        list(libro.values()), list(flujo.values())
    )

    observaciones: List[Dict[str, Any]] = []
    for rl, rf in pares:
        observaciones.append(
            construir_observacion(
                rl["symbol"], int(rl["bucket_start"]), int(rl["bucket_end"]),
                rl, rf, series[rl["symbol"]],
            )
        )
    for rl in libro_solo:
        observaciones.append(
            construir_observacion(
                rl["symbol"], int(rl["bucket_start"]), int(rl["bucket_end"]),
                rl, None, series[rl["symbol"]],
            )
        )
    for rf in flujo_solo:
        observaciones.append(
            construir_observacion(
                rf["symbol"], int(rf["bucket_start"]), int(rf["bucket_end"]),
                None, rf, series[rf["symbol"]],
            )
        )
    observaciones.sort(key=lambda o: (o["simbolo"], o["bucket_start"], o["observation_id"]))

    con_hist.close()
    con_cache.close()

    n_total = len(observaciones)
    por_estado = {
        ESTADO_EVALUABLE: [o for o in observaciones if o["estado"] == ESTADO_EVALUABLE],
        ESTADO_DESCRIPTIVA: [o for o in observaciones if o["estado"] == ESTADO_DESCRIPTIVA],
        ESTADO_DESCARTADA: [o for o in observaciones if o["estado"] == ESTADO_DESCARTADA],
    }
    retornos_evaluables = [
        o["retorno"] for o in por_estado[ESTADO_EVALUABLE]
        if o["retorno"] is not None
    ]
    retornos_descriptivos = [
        o["retorno"] for o in por_estado[ESTADO_DESCRIPTIVA]
        if o["retorno"] is not None
    ]

    resumen = {
        "procedimiento": "observaciones_libro_flujo_precio_v2",
        "horizonte_ms": HORIZONTE_MS,
        "tolerancia_alineacion_ms": TOLERANCIA_MS,
        "fuente_precios": "market_klines|1h",
        "n_observaciones_totales": n_total,
        "n_parejas_libro_flujo": len(pares),
        "n_libro_sin_flujo": len(libro_solo),
        "n_flujo_sin_libro": len(flujo_solo),
        "n_duplicados_libro": len(dup_libro),
        "n_duplicados_flujo": len(dup_flujo),
        "n_aceptada_para_descripcion": len(por_estado[ESTADO_DESCRIPTIVA]),
        "n_apta_temporalmente_para_evaluacion": len(por_estado[ESTADO_EVALUABLE]),
        "n_descartada": len(por_estado[ESTADO_DESCARTADA]),
        "disponibilidad_por_fuente": {
            "libro": _conteo_as_of(list(libro.values())),
            "flujo": _conteo_as_of(list(flujo.values())),
        },
        "disponibilidad_observaciones": {
            # Solo observaciones con AMBAS fuentes (pareja conjunta): una fila
            # sin contraparte no tiene clase de disponibilidad conjunta.
            "n_parejas_evaluadas": sum(
                1 for o in observaciones if o["libro"] and o["flujo"]
            ),
            "ambas_publicadas_en_T": sum(
                1 for o in observaciones
                if o["libro"] and o["flujo"]
                and o["disponibilidad"]["ambas_publicadas_en_T"]
            ),
            "alguna_desconocida": sum(
                1 for o in observaciones
                if o["libro"] and o["flujo"]
                and CLASE_DESCONOCIDA in (
                    o["disponibilidad"]["libro"]["clase"],
                    o["disponibilidad"]["flujo"]["clase"],
                )
            ),
            "alguna_posterior_a_T": sum(
                1 for o in observaciones
                if o["libro"] and o["flujo"]
                and CLASE_DESPUES_DE_T in (
                    o["disponibilidad"]["libro"]["clase"],
                    o["disponibilidad"]["flujo"]["clase"],
                )
            ),
        },
        "retorno_evaluable_causalmente": _agregado(retornos_evaluables),
        "retorno_descriptivo_no_evaluable": _agregado(retornos_descriptivos),
        "nota": (
            "Los dos agregados de retorno NO son intercambiables: "
            "retorno_evaluable_causalmente exige as_of_ms de libro y flujo <= T "
            "en la MISMA observación; retorno_descriptivo_no_evaluable agrupa "
            "observaciones con precios pero sin disponibilidad publicada "
            "acreditada en T y no sostiene ninguna conclusión causal. "
            "as_of_ms NULL significa procedencia desconocida: no se rellena, "
            "no se sustituye por last_event_ms y no prueba ausencia de relación "
            "económica."
        ),
    }

    # Muestra determinista para validación contra fuente. Incluye por separado
    # cada estado presente, de modo que la validación no compare null con null.
    import random
    rng = random.Random(20261103)
    muestra = []
    for estado in (ESTADO_EVALUABLE, ESTADO_DESCRIPTIVA, ESTADO_DESCARTADA):
        grupo = por_estado[estado]
        con_retorno = [o for o in grupo if o["retorno"] is not None]
        sin_retorno = [o for o in grupo if o["retorno"] is None]
        muestra.extend(rng.sample(con_retorno, min(4, len(con_retorno))))
        muestra.extend(rng.sample(sin_retorno, min(2, len(sin_retorno))))

    muestra_validacion = []
    for o in muestra:
        serie = series[o["simbolo"]]
        p_T, ct_T = serie.en_T(o["T"])
        p_Tph, ct_Tph = serie.en_T_plus_h(o["T"])
        muestra_validacion.append({
            "observation_id": o["observation_id"],
            "simbolo": o["simbolo"],
            "T": o["T"],
            "estado": o["estado"],
            "as_of_libro": o["disponibilidad"]["libro"]["as_of_ms"],
            "clase_libro": o["disponibilidad"]["libro"]["clase"],
            "as_of_flujo": o["disponibilidad"]["flujo"]["as_of_ms"],
            "clase_flujo": o["disponibilidad"]["flujo"]["clase"],
            "precio_T_registrado": o["precio"]["precio_T"],
            "close_time_T_registrado": o["precio"]["close_time_inicial_ms"],
            "precio_T_plus_h_registrado": o["precio"]["precio_T_plus_h"],
            "close_time_T_plus_h_registrado": o["precio"]["close_time_final_ms"],
            "retorno_registrado": o["retorno"],
            "precio_T_recalculado": p_T,
            "close_time_T_recalculado": ct_T,
            "precio_T_plus_h_recalculado": p_Tph,
            "close_time_T_plus_h_recalculado": ct_Tph,
            "retorno_recalculado": (
                (p_Tph - p_T) / p_T
                if (p_T is not None and p_Tph is not None and p_T)
                else None
            ),
        })

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


if __name__ == "__main__":
    main()
