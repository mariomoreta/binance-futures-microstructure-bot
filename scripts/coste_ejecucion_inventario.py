"""Coste de ejecucion con las capturas existentes (offline, solo lectura).

Version: coste-ejecucion-inventario-v1

Parte de los 278 episodios evaluables de solo precio ya publicados y responde
una sola pregunta: existen cotizaciones bid/ask observadas en la entrada y en
la salida de esos episodios?

No calcula retornos ajustados por spread. Si no hay cotizaciones, publica el
faltante exacto. No abre mercado, no escribe en las capturas y no toca la
estrategia.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import statistics
from typing import Any, Dict, List, Optional, Tuple

VERSION = "coste-ejecucion-inventario-v1"
BASE_COMMIT = "2be0e1fcc97ff58b1db0b6e59a8684c789debd07"
EPISODIOS_POR_DEFECTO = "docs/evidence/extension-previa-20261119/C-resumen.json"

VENTANA_MS = 60_000
HORIZONTE_MS = 300_000
VENTANA_CERCANIA_MS = 5_000
MIN_PARES = 30
COSTE_IDA_VUELTA_PREVIO_BPS = 16.0

# Nombres exactos que si serian una cotizacion observada. No se aceptan
# variantes de profundidad (bid5_mean, bid_levels, bid_base_top20...).
_NOMBRES_BID = frozenset({"best_bid", "bidprice", "bid_price", "bid_px", "bestbid", "bid"})
_NOMBRES_ASK = frozenset({"best_ask", "askprice", "ask_price", "ask_px", "bestask", "ask"})

_FUENTES = {
    "research_book_1m": "tabla de research.db; agregados por minuto",
    "observaciones_jsonl": "snapshots de libro en instantes de decision",
    "resultado_operativo_jsonl": "ejecuciones simuladas del motor de papel",
    "http_requests_jsonl": "peticiones REST registradas",
    "consultas_klines_jsonl": "velas OHLC consultadas (solo ventana 3)",
}


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def cargar_episodios(ruta: str) -> List[Dict[str, Any]]:
    """Lee los 278 episodios publicados y congela entrada y salida."""
    with io.open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    detalle = datos["primaria_solo_precio"]["detalle"]
    episodios: List[Dict[str, Any]] = []
    for e in detalle:
        cut = int(e["cut_ms"])
        entrada = (cut // VENTANA_MS + 1) * VENTANA_MS
        episodios.append({
            "captura": e["captura"],
            "symbol": e["symbol"],
            "direccion": e["direccion"],
            "cut_ms": cut,
            "entrada_ms": entrada,
            "salida_ms": entrada + HORIZONTE_MS,
            "precio_entrada": e["precio_entrada"],
            "precio_salida": e["precio_salida"],
            "retorno_bruto_bps": e["retorno_bruto_bps"],
            "retorno_neto_bps": e["retorno_neto_bps"],
            "grupo": e.get("grupo"),
        })
    return episodios


def efecto_filtro(detalle: List[Dict[str, Any]],
                  grupo_descartado: str = "EXTENDIDO") -> Dict[str, Any]:
    """Separa la suma descartada del cambio de suma al abstenerse.

    El valor negativo publicado (-1 506.08 bps) es la suma de los retornos de
    los episodios descartados, no el efecto de abstenerse. Abstenerse cambia la
    suma en el signo opuesto.
    """
    descartados = [e for e in detalle if e.get("grupo") == grupo_descartado]
    retenidos = [e for e in detalle if e.get("grupo") != grupo_descartado]
    suma_desc = sum(float(e["retorno_neto_bps"]) for e in descartados)
    suma_ret = sum(float(e["retorno_neto_bps"]) for e in retenidos)
    return {
        "grupo_descartado": grupo_descartado,
        "descartados": len(descartados),
        "suma_descartados_bps": suma_desc,
        "cambio_de_suma_al_abstenerse_bps": -suma_desc,
        "suma_retenidos_bps": suma_ret,
        "suma_sin_filtro_bps": suma_desc + suma_ret,
        "media_descartados_bps": suma_desc / len(descartados) if descartados else None,
        "media_retenidos_bps": suma_ret / len(retenidos) if retenidos else None,
        "media_sin_filtro_bps": ((suma_desc + suma_ret) / len(detalle)) if detalle else None,
    }


def _conectar(db_path: str) -> sqlite3.Connection:
    uri = "file:%s?mode=ro" % db_path.replace("\\", "/")
    return sqlite3.connect(uri, uri=True)


def _columnas(con: sqlite3.Connection, tabla: str) -> List[str]:
    return [f[1] for f in con.execute("PRAGMA table_info(%s)" % tabla).fetchall()]


def _bucket(con: sqlite3.Connection, symbol: str, bucket_start: int,
            campos_bid: List[str], campos_ask: List[str]) -> Optional[Dict[str, Any]]:
    """Agregado del minuto. Nunca contiene best bid/ask en estas capturas."""
    columnas = [
        "bucket_end", "sample_count", "spread_min", "spread_mean", "spread_max",
        "degraded", "crossed", "first_event_ms", "last_event_ms", "as_of_ms",
    ]
    extra = campos_bid[:1] + campos_ask[:1]
    fila = con.execute(
        "SELECT %s FROM research_book_1m WHERE symbol = ? AND bucket_start = ?"
        % ", ".join(columnas + extra),
        (symbol, bucket_start),
    ).fetchone()
    if fila is None:
        return None
    registro = {
        "bucket_end": fila[0],
        "sample_count": fila[1],
        "spread_min_bps": fila[2],
        "spread_mean_bps": fila[3],
        "spread_max_bps": fila[4],
        "degraded": bool(fila[5]),
        "crossed": bool(fila[6]),
        "first_event_ms": fila[7],
        "last_event_ms": fila[8],
        "as_of_ms": fila[9],
        "best_bid": fila[10] if len(campos_bid[:1]) == 1 else None,
        "best_ask": fila[10 + len(campos_bid[:1])] if len(campos_ask[:1]) == 1 else None,
    }
    return registro


def cargar_observaciones(ruta: str) -> List[Dict[str, Any]]:
    """Snapshots de libro: mid y spread en un instante, nunca bid/ask."""
    if not os.path.exists(ruta):
        return []
    snapshots: List[Dict[str, Any]] = []
    with io.open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            registro = json.loads(linea)
            libro = registro.get("libro")
            if not isinstance(libro, dict) or not registro.get("symbol"):
                continue
            integridad = registro.get("integridad") or {}
            snapshots.append({
                "symbol": registro["symbol"],
                "event_ms": libro.get("event_ms"),
                "received_ms": libro.get("received_ms"),
                "decision_ms": registro.get("decision_ms"),
                "spread_bps": libro.get("spread_bps"),
                "mid": registro.get("precio_base"),
                "mid_fuente": registro.get("precio_base_fuente"),
                "bid_levels": libro.get("bid_levels"),
                "ask_levels": libro.get("ask_levels"),
                "degradado": bool(integridad.get("libro_degradado")),
                "cruzado": bool(integridad.get("libro_cruzado")),
                "best_bid": libro.get("best_bid"),
                "best_ask": libro.get("best_ask"),
                "claves_libro": sorted(libro.keys()),
            })
    return snapshots


def _claves_linea(ruta: str) -> List[str]:
    """Claves del primer objeto JSON de un jsonl, para el escaneo de fuentes."""
    if not os.path.exists(ruta) or os.path.getsize(ruta) == 0:
        return []
    with io.open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            registro = json.loads(linea)
            if isinstance(registro, dict):
                return sorted(registro.keys())
    return []


def _campos_bid_ask(nombres: List[str]) -> Tuple[List[str], List[str]]:
    minusculas = {n.lower() for n in nombres}
    return sorted(minusculas & _NOMBRES_BID), sorted(minusculas & _NOMBRES_ASK)


# ---------------------------------------------------------------------------
# Criterios
# ---------------------------------------------------------------------------

def _c1(snapshot: Optional[Dict[str, Any]], instante: int,
        ventana_ms: int = VENTANA_CERCANIA_MS) -> bool:
    """Cercania: mismo instante a +/- ventana_ms y disponible sin adelanto."""
    if snapshot is None or snapshot.get("event_ms") is None:
        return False
    if abs(int(snapshot["event_ms"]) - instante) > ventana_ms:
        return False
    recibido = snapshot.get("received_ms")
    return recibido is not None and int(recibido) <= instante


def _c2(snapshot: Optional[Dict[str, Any]]) -> bool:
    """Calidad: no cruzado, no degradado, al menos un nivel por lado."""
    if snapshot is None:
        return False
    return (
        not snapshot.get("degradado")
        and not snapshot.get("cruzado")
        and int(snapshot.get("bid_levels") or 0) >= 1
        and int(snapshot.get("ask_levels") or 0) >= 1
    )


def _cotizacion_observada(snapshot: Optional[Dict[str, Any]]) -> bool:
    """C0: precios de mejor bid y mejor ask explicitos y coherentes."""
    if snapshot is None:
        return False
    bid = snapshot.get("best_bid")
    ask = snapshot.get("best_ask")
    return bid is not None and ask is not None and float(bid) > 0 and float(ask) > float(bid)


def _cercana(snapshots: List[Dict[str, Any]], symbol: str, instante: int
             ) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    mejor: Optional[Dict[str, Any]] = None
    mejor_dist: Optional[int] = None
    for s in snapshots:
        if s["symbol"] != symbol or s.get("event_ms") is None:
            continue
        dist = abs(int(s["event_ms"]) - instante)
        if mejor_dist is None or dist < mejor_dist:
            mejor, mejor_dist = s, dist
    return mejor, mejor_dist


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------

def _stats(valores: List[float]) -> Optional[Dict[str, Any]]:
    if not valores:
        return None
    ordenados = sorted(valores)
    n = len(ordenados)
    if n >= 4:
        cuartiles = statistics.quantiles(ordenados, n=4)
        p25, p75 = cuartiles[0], cuartiles[2]
    else:
        p25 = p75 = None
    return {
        "n": n,
        "min": ordenados[0],
        "p25": p25,
        "mediana": statistics.median(ordenados),
        "p75": p75,
        "max": ordenados[-1],
        "media": statistics.fmean(ordenados),
    }


def _resumen_captura(registros: List[Dict[str, Any]]) -> Dict[str, Any]:
    spread_entrada = [r["bucket_entrada"]["spread_mean_bps"] for r in registros
                      if r["bucket_entrada"] and r["bucket_entrada"]["spread_mean_bps"] is not None]
    spread_salida = [r["bucket_salida"]["spread_mean_bps"] for r in registros
                     if r["bucket_salida"] and r["bucket_salida"]["spread_mean_bps"] is not None]
    lags = []
    for r in registros:
        for clave, instante in (("bucket_entrada", r["entrada_ms"]), ("bucket_salida", r["salida_ms"])):
            b = r[clave]
            if b and b.get("as_of_ms") is not None:
                lags.append(float(b["as_of_ms"] - instante))
    faltantes = [
        {"symbol": r["symbol"], "extremo": extremo, "direccion": r["direccion"]}
        for r in registros
        for extremo, clave in (("entrada", "bucket_entrada"), ("salida", "bucket_salida"))
        if r[clave] is None
    ]
    return {
        "episodios": len(registros),
        "bucket_entrada": sum(1 for r in registros if r["bucket_entrada"]),
        "bucket_salida": sum(1 for r in registros if r["bucket_salida"]),
        "bucket_ambos": sum(1 for r in registros if r["bucket_entrada"] and r["bucket_salida"]),
        "bucket_entrada_disponible_al_instante": sum(
            1 for r in registros
            if r["bucket_entrada"] and r["bucket_entrada"]["as_of_ms"] is not None
            and r["bucket_entrada"]["as_of_ms"] <= r["entrada_ms"]),
        "bucket_salida_disponible_al_instante": sum(
            1 for r in registros
            if r["bucket_salida"] and r["bucket_salida"]["as_of_ms"] is not None
            and r["bucket_salida"]["as_of_ms"] <= r["salida_ms"]),
        "obs_entrada_5s": sum(1 for r in registros if r["c1_entrada"]),
        "obs_salida_5s": sum(1 for r in registros if r["c1_salida"]),
        "obs_ambos_5s": sum(1 for r in registros if r["c1_entrada"] and r["c1_salida"]),
        "obs_ambos_5s_calidad_ok": sum(
            1 for r in registros
            if r["c1_entrada"] and r["c1_salida"] and r["c2_entrada"] and r["c2_salida"]),
        "pares_c0": sum(1 for r in registros if r["c0"]),
        "pares_c3": sum(1 for r in registros if r["c3"]),
        "spread_entrada_bps": _stats(spread_entrada),
        "spread_salida_bps": _stats(spread_salida),
        "lag_disponibilidad_bucket_ms": _stats(lags),
        "degradados": sum(
            1 for r in registros
            for clave in ("bucket_entrada", "bucket_salida")
            if r[clave] and r[clave]["degraded"]),
        "cruzados": sum(
            1 for r in registros
            for clave in ("bucket_entrada", "bucket_salida")
            if r[clave] and r[clave]["crossed"]),
        "faltantes": faltantes,
    }


def inventariar(base_datos: str, episodios: List[Dict[str, Any]],
                ventana_cercania_ms: int = VENTANA_CERCANIA_MS,
                episodios_fuente: str = EPISODIOS_POR_DEFECTO) -> Dict[str, Any]:
    """Construye el inventario completo a partir de los episodios congelados."""
    capturas = sorted({e["captura"] for e in episodios})
    por_captura: Dict[str, List[Dict[str, Any]]] = {c: [] for c in capturas}
    fuentes: Dict[str, Any] = {}
    columnas_book: List[str] = []
    campos_bid_book: List[str] = []
    campos_ask_book: List[str] = []
    claves_libro: List[str] = []
    campos_bid_libro: List[str] = []
    campos_ask_libro: List[str] = []

    for captura in capturas:
        db_path = os.path.join(base_datos, captura, "research.db")
        obs_path = os.path.join(base_datos, captura, "observaciones.jsonl")
        con = _conectar(db_path)
        try:
            if not columnas_book:
                columnas_book = _columnas(con, "research_book_1m")
                campos_bid_book, campos_ask_book = _campos_bid_ask(columnas_book)
            snapshots = cargar_observaciones(obs_path)
            if not claves_libro:
                claves_libro = snapshots[0]["claves_libro"] if snapshots else []
                campos_bid_libro, campos_ask_libro = _campos_bid_ask(claves_libro)
            for e in episodios:
                if e["captura"] != captura:
                    continue
                b_entrada = _bucket(con, e["symbol"], e["entrada_ms"], campos_bid_book, campos_ask_book)
                b_salida = _bucket(con, e["symbol"], e["salida_ms"], campos_bid_book, campos_ask_book)
                s_entrada, d_entrada = _cercana(snapshots, e["symbol"], e["entrada_ms"])
                s_salida, d_salida = _cercana(snapshots, e["symbol"], e["salida_ms"])
                c1_entrada = _c1(s_entrada, e["entrada_ms"], ventana_cercania_ms)
                c1_salida = _c1(s_salida, e["salida_ms"], ventana_cercania_ms)
                c2_entrada = _c2(s_entrada)
                c2_salida = _c2(s_salida)
                c0 = (_cotizacion_observada(s_entrada) and _cotizacion_observada(s_salida))
                por_captura[captura].append({
                    **e,
                    "bucket_entrada": b_entrada,
                    "bucket_salida": b_salida,
                    "obs_entrada": _snapshot_minimo(s_entrada, d_entrada),
                    "obs_salida": _snapshot_minimo(s_salida, d_salida),
                    "c1_entrada": c1_entrada,
                    "c1_salida": c1_salida,
                    "c2_entrada": c2_entrada,
                    "c2_salida": c2_salida,
                    "c0": c0,
                    "c3": bool(c0 and c1_entrada and c1_salida and c2_entrada and c2_salida),
                })
            fuentes[captura] = {
                "research_book_1m_columnas": sorted(_columnas(con, "research_book_1m")),
                "observaciones_libro_claves": claves_libro,
                "resultado_operativo_claves": _claves_linea(
                    os.path.join(base_datos, captura, "resultado_operativo.jsonl")),
                "http_requests_claves": _claves_linea(
                    os.path.join(base_datos, captura, "http_requests.jsonl")),
                "consultas_klines_claves": _claves_linea(
                    os.path.join(base_datos, captura, "consultas_klines.jsonl")),
                "snapshots_libro": len(snapshots),
            }
        finally:
            con.close()

    campos_bid = sorted(set(campos_bid_book) | set(campos_bid_libro))
    campos_ask = sorted(set(campos_ask_book) | set(campos_ask_libro))
    hay_cotizacion = bool(campos_bid and campos_ask)

    resumen_capturas = {c: _resumen_captura(regs) for c, regs in por_captura.items()}
    todos = [r for regs in por_captura.values() for r in regs]
    total = _resumen_captura(todos)

    brutos = [e["retorno_bruto_bps"] for e in episodios]
    bruto_medio = statistics.fmean(brutos)
    spread_buckets = [
        r[clave]["spread_mean_bps"]
        for r in todos
        for clave in ("bucket_entrada", "bucket_salida")
        if r[clave] and r[clave]["spread_mean_bps"] is not None
    ]

    faltantes_exactos = {
        "campo_mejor_bid": (
            "ausente: research_book_1m no guarda precios de nivel y "
            "observaciones.jsonl.libro guarda mid y spread, no bid/ask"
        ),
        "campo_mejor_ask": (
            "ausente: mismo motivo; solo existen spread_bps, mid y agregados de profundidad"
        ),
        "campos_bid_detectados": campos_bid,
        "campos_ask_detectados": campos_ask,
        "episodios_sin_bucket_entrada": total["episodios"] - total["bucket_entrada"],
        "episodios_sin_bucket_salida": total["episodios"] - total["bucket_salida"],
        "episodios_sin_par_de_buckets": total["episodios"] - total["bucket_ambos"],
        "episodios_sin_cotizacion_instantanea_ambos_extremos_5s":
            total["episodios"] - total["obs_ambos_5s"],
        "episodios_con_mid_y_spread_instantaneo_ambos_extremos_5s":
            total["obs_ambos_5s_calidad_ok"],
        "funding": "UNKNOWN: funding_adquisicion.jsonl vacio o ausente en las 4 capturas",
        "comision": "UNKNOWN: no hay tarifa acreditada en los artefactos",
        "slippage_adicional": "UNKNOWN: sin fills, cola ni consumo de profundidad",
    }

    descomposicion = {
        "spread": "NO_VERIFICABLE" if not hay_cotizacion else "OBSERVADO",
        "comision": "UNKNOWN",
        "slippage_adicional": "UNKNOWN",
        "funding": "UNKNOWN",
    }

    margen = {
        "bruto_medio_278_bps": bruto_medio,
        "coste_adicional_maximo_bps": bruto_medio,
        "spread_agregado_mediano_bps": (statistics.median(spread_buckets)
                                        if spread_buckets else None),
        "spread_agregado_n": len(spread_buckets),
        "nota": (
            "El umbral bruto descriptivo es la media de los 278 y no es "
            "rentabilidad. El spread agregado es una media por minuto, no una "
            "cotizacion, y ademas se publica despues del instante: no se usa "
            "para calcular retornos."
        ),
    }

    veredicto = "DATOS_INSUFICIENTES" if total["pares_c3"] < MIN_PARES else "CON_COBERTURA"

    return {
        "version": VERSION,
        "base_commit": BASE_COMMIT,
        "episodios_fuente": episodios_fuente,
        "parametros": {
            "ventana_ms": VENTANA_MS,
            "horizonte_ms": HORIZONTE_MS,
            "ventana_cercania_ms": ventana_cercania_ms,
            "min_pares": MIN_PARES,
            "coste_ida_vuelta_previo_bps": COSTE_IDA_VUELTA_PREVIO_BPS,
        },
        "criterios": {
            "C0": "bid y ask observados en ambos extremos; mid, spread por minuto, OHLC y fills simulados no cuentan",
            "C1": "|event_ms - instante| <= 5000 ms y received_ms <= instante",
            "C2": "no cruzado, no degradado, >= 1 nivel por lado",
            "C3": "C0 + C1 + C2 en entrada y salida",
            "C4": "minimo 30 pares para publicar un agregado ajustado por spread",
        },
        "fuentes": {
            "descripcion": _FUENTES,
            "por_captura": fuentes,
        },
        "capturas": resumen_capturas,
        "total": total,
        "faltantes_exactos": faltantes_exactos,
        "descomposicion_coste": descomposicion,
        "margen": margen,
        "correccion_etiqueta": efecto_filtro(episodios),
        "veredicto": veredicto,
        "episodios": todos,
    }


def _snapshot_minimo(snapshot: Optional[Dict[str, Any]],
                     distancia: Optional[int]) -> Optional[Dict[str, Any]]:
    if snapshot is None:
        return None
    return {
        "event_ms": snapshot["event_ms"],
        "received_ms": snapshot["received_ms"],
        "distancia_ms": distancia,
        "spread_bps": snapshot["spread_bps"],
        "mid": snapshot["mid"],
        "degradado": snapshot["degradado"],
        "cruzado": snapshot["cruzado"],
        "bid_levels": snapshot["bid_levels"],
        "ask_levels": snapshot["ask_levels"],
        "best_bid": snapshot["best_bid"],
        "best_ask": snapshot["best_ask"],
    }


def _compacto(inventario: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce los registros por episodio para la copia publicada."""
    compacto = dict(inventario)
    compacto["episodios"] = [
        {
            "captura": e["captura"],
            "symbol": e["symbol"],
            "direccion": e["direccion"],
            "cut_ms": e["cut_ms"],
            "entrada_ms": e["entrada_ms"],
            "salida_ms": e["salida_ms"],
            "bucket_entrada": e["bucket_entrada"] is not None,
            "bucket_salida": e["bucket_salida"] is not None,
            "obs_entrada_ms": e["obs_entrada"]["event_ms"] if e["obs_entrada"] else None,
            "obs_salida_ms": e["obs_salida"]["event_ms"] if e["obs_salida"] else None,
            "c1_entrada": e["c1_entrada"],
            "c1_salida": e["c1_salida"],
            "c2_entrada": e["c2_entrada"],
            "c2_salida": e["c2_salida"],
            "c0": e["c0"],
            "c3": e["c3"],
        }
        for e in inventario["episodios"]
    ]
    return compacto


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datos", default=r"C:\proyectos\binance-futures-data")
    parser.add_argument("--episodios", default=EPISODIOS_POR_DEFECTO)
    parser.add_argument("--salida", required=True)
    parser.add_argument("--compacto", action="store_true")
    args = parser.parse_args(argv)

    episodios = cargar_episodios(args.episodios)
    inventario = inventariar(args.datos, episodios,
                             episodios_fuente=args.episodios)
    if args.compacto:
        inventario = _compacto(inventario)

    texto = json.dumps(inventario, ensure_ascii=False, indent=1) + "\n"
    carpeta = os.path.dirname(os.path.abspath(args.salida))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    with io.open(args.salida, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)

    total = inventario["total"]
    print("episodios: %d" % total["episodios"])
    print("bucket entrada/salida/ambos: %d/%d/%d" % (
        total["bucket_entrada"], total["bucket_salida"], total["bucket_ambos"]))
    print("bucket disponible al instante: entrada %d salida %d" % (
        total["bucket_entrada_disponible_al_instante"],
        total["bucket_salida_disponible_al_instante"]))
    print("obs a +/-5 s: entrada %d salida %d ambos %d (calidad ok %d)" % (
        total["obs_entrada_5s"], total["obs_salida_5s"],
        total["obs_ambos_5s"], total["obs_ambos_5s_calidad_ok"]))
    print("pares C0: %d | pares C3: %d | minimo: %d" % (
        total["pares_c0"], total["pares_c3"], MIN_PARES))
    etiqueta = inventario["correccion_etiqueta"]
    print("etiqueta: suma descartados %.4f bps | cambio de suma al abstenerse %+.4f bps" % (
        etiqueta["suma_descartados_bps"], etiqueta["cambio_de_suma_al_abstenerse_bps"]))
    print("veredicto: %s" % inventario["veredicto"])
    print("salida: %s" % args.salida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
