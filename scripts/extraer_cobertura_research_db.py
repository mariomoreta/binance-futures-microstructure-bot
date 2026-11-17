#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extractor offline de cobertura desde research.db (modo solo lectura).

Extrae ventanas de flujo y libro por símbolo e intervalo desde
research_flow_1m y research_book_1m, las empareja por (symbol, bucket_start),
y reporta ventanas válidas, huecos, ternas contiguas y motivos de limitación.

No modifica la base de datos. Lee en modo solo lectura.

Uso:
  python scripts/extraer_cobertura_research_db.py \\
    --db C:\\proyectos\\binance-futures-data\\exp-v2-ventana-4-20261116a\\research.db \\
    --salida C:\\proyectos\\binance-futures-data\\exp-v2-ventana-4-20261116a-cobertura\\cobertura.json
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def utc_iso(ms: Optional[int]) -> Optional[str]:
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Extracción
# ---------------------------------------------------------------------------

def conectar_solo_lectura(ruta_db: Path) -> sqlite3.Connection:
    """Abre la base de datos en modo solo lectura (URI file:...?mode=ro)."""
    uri = f"file:{ruta_resuelta(ruta_db)}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def ruta_resuelta(ruta: Path) -> str:
    return str(ruta.resolve())


def extraer_cobertura(ruta_db: Path) -> Dict[str, Any]:
    """Extrae cobertura de flujo y libro desde research.db."""
    con = conectar_solo_lectura(ruta_db)
    cur = con.cursor()

    # Verificar que las tablas existen
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tablas = {r[0] for r in cur.fetchall()}
    tablas_necesarias = {"research_flow_1m", "research_book_1m"}
    faltantes = tablas_necesarias - tablas
    if faltantes:
        con.close()
        raise ValueError(f"Tablas ausentes en la BD: {faltantes}")

    # Obtener todos los símbolos presentes en research_flow_1m
    cur.execute("SELECT DISTINCT symbol FROM research_flow_1m ORDER BY symbol")
    simbolos_flujo = {r[0] for r in cur.fetchall()}

    # Obtener todos los símbolos presentes en research_book_1m
    cur.execute("SELECT DISTINCT symbol FROM research_book_1m ORDER BY symbol")
    simbolos_libro = {r[0] for r in cur.fetchall()}

    todos_los_simbolos = sorted(simbolos_flujo | simbolos_libro)

    # Construir mapas por símbolo y bucket_start
    flujo_por_simbolo: Dict[str, Dict[int, Dict[str, Any]]] = {}
    cur.execute(
        "SELECT symbol, bucket_start, bucket_end, buy_notional, sell_notional, "
        "price_open, price_high, price_low, price_close, first_event_ms, "
        "last_event_ms, data_quality, run_id, rules_version, as_of_ms, "
        "price_source, dataset_id FROM research_flow_1m"
    )
    for r in cur.fetchall():
        simbolo = r[0]
        flujo_por_simbolo.setdefault(simbolo, {})[r[1]] = {
            "bucket_start": r[1],
            "bucket_end": r[2],
            "buy_notional": r[3],
            "sell_notional": r[4],
            "price_open": r[5],
            "price_high": r[6],
            "price_low": r[7],
            "price_close": r[8],
            "first_event_ms": r[9],
            "last_event_ms": r[10],
            "data_quality": r[11],
            "run_id": r[12],
            "rules_version": r[13],
            "as_of_ms": r[14],
            "price_source": r[15],
            "dataset_id": r[16],
        }

    libro_por_simbolo: Dict[str, Dict[int, Dict[str, Any]]] = {}
    cur.execute(
        "SELECT symbol, bucket_start, bucket_end, sample_count, spread_min, "
        "spread_mean, spread_max, imb_min, imb_mean, imb_max, micro_min, "
        "micro_mean, micro_max, bid5_mean, ask5_mean, bid20_mean, ask20_mean, "
        "depth_gaps, degraded, crossed, first_event_ms, last_event_ms, "
        "run_id, rules_version, as_of_ms, price_source, dataset_id "
        "FROM research_book_1m"
    )
    for r in cur.fetchall():
        simbolo = r[0]
        libro_por_simbolo.setdefault(simbolo, {})[r[1]] = {
            "bucket_start": r[1],
            "bucket_end": r[2],
            "sample_count": r[3],
            "spread_min": r[4],
            "spread_mean": r[5],
            "spread_max": r[6],
            "imb_min": r[7],
            "imb_mean": r[8],
            "imb_max": r[9],
            "micro_min": r[10],
            "micro_mean": r[11],
            "micro_max": r[12],
            "bid5_mean": r[13],
            "ask5_mean": r[14],
            "bid20_mean": r[15],
            "ask20_mean": r[16],
            "depth_gaps": r[17],
            "degradado": r[18],
            "cruzado": r[19],
            "first_event_ms": r[20],
            "last_event_ms": r[21],
            "run_id": r[22],
            "rules_version": r[23],
            "as_of_ms": r[24],
            "price_source": r[25],
            "dataset_id": r[26],
        }

    con.close()

    # Construir reporte por símbolo
    resultados_por_simbolo: Dict[str, Dict[str, Any]] = {}

    for simbolo in todos_los_simbolos:
        flujo_por_bucket = flujo_por_simbolo.get(simbolo, {})
        libro_por_bucket = libro_por_simbolo.get(simbolo, {})

        buckets_flujo = set(flujo_por_bucket.keys())
        buckets_libro = set(libro_por_bucket.keys())
        buckets_comunes = sorted(flujo_por_bucket.keys() & libro_por_bucket.keys())

        ventanas_validas: List[Dict[str, Any]] = []
        motivos_exclusiones: Dict[str, int] = {}

        for bs in buckets_comunes:
            f = flujo_por_bucket[bs]
            l = libro_por_bucket[bs]

            # Verificar que ambos tengan los datos mínimos
            buy_n = f["buy_notional"]
            sell_n = f["sell_notional"]
            bid20 = l["bid20_mean"]
            ask20 = l["ask20_mean"]
            precio = f["price_close"]

            faltantes_campos = []
            if buy_n is None:
                faltantes_campos.append("buy_notional")
            if sell_n is None:
                faltantes_campos.append("sell_notional")
            if bid20 is None:
                faltantes_campos.append("bid20_mean")
            if ask20 is None:
                faltantes_campos.append("ask20_mean")
            if precio is None:
                faltantes_campos.append("price_close")

            if faltantes_campos:
                motivos_exclusiones[f"campo_faltante:{','.join(sorted(faltantes_campos))}"] = (
                    motivos_exclusiones.get(f"campo_faltante:{','.join(sorted(faltantes_campos))}", 0) + 1
                )
                continue

            # Verificar que los importes son finitos y positivos
            try:
                buy_n = float(buy_n)
                sell_n = float(sell_n)
                bid20 = float(bid20)
                ask20 = float(ask20)
                precio = float(precio)
            except (TypeError, ValueError):
                motivos_exclusiones["valor_no_numerico"] = (
                    motivos_exclusiones.get("valor_no_numerico", 0) + 1
                )
                continue

            if not (math.isfinite(buy_n) and math.isfinite(sell_n) and
                    math.isfinite(bid20) and math.isfinite(ask20) and
                    math.isfinite(precio)):
                motivos_exclusiones["valor_no_finito"] = (
                    motivos_exclusiones.get("valor_no_finito", 0) + 1
                )
                continue

            if buy_n <= 0 or sell_n <= 0 or bid20 <= 0 or ask20 <= 0 or precio <= 0:
                motivos_exclusiones["valor_no_positivo"] = (
                    motivos_exclusiones.get("valor_no_positivo", 0) + 1
                )
                continue

            # Verificar integridad del libro y flujo (no degradado, no cruzado, data_quality OK)
            integridad_valida = (
                f["data_quality"] == "OK"
                and l["degradado"] == 0
                and l["cruzado"] == 0
            )
            if not integridad_valida:
                motivos_exclusiones["integridad_mala"] = (
                    motivos_exclusiones.get("integridad_mala", 0) + 1
                )
                continue

            # Disponibilidad: no convertir None en 0; se reporta como desconocida
            disp_flujo = f["as_of_ms"]
            disp_libro = l["as_of_ms"]
            if disp_flujo is None and disp_libro is None:
                disponibilidad_ms = None
            elif disp_flujo is None:
                disponibilidad_ms = disp_libro
            elif disp_libro is None:
                disponibilidad_ms = disp_flujo
            else:
                disponibilidad_ms = max(disp_flujo, disp_libro)
            disponibilidad_conocida = disponibilidad_ms is not None
            if not disponibilidad_conocida:
                motivos_exclusiones["disponibilidad_desconocida"] = (
                    motivos_exclusiones.get("disponibilidad_desconocida", 0) + 1
                )
                continue

            # Ventana válida
            ventana = {
                "symbol": simbolo,
                "observation_id": f"{simbolo}|{bs}",
                "decision_ms": f["bucket_end"],
                "decision_iso": utc_iso(f["bucket_end"]),
                "ventana_inicio_ms": bs,
                "ventana_fin_ms": f["bucket_end"],
                "ventana_ms": 60_000,
                "evento_ms": f["first_event_ms"] or f["bucket_start"],
                "evento_ms": f["first_event_ms"] or f["bucket_start"],
                "evento_iso": utc_iso(f["first_event_ms"]) if f["first_event_ms"] is not None else None,
                "disponibilidad_ms": disponibilidad_ms,
                "disponibilidad_conocida": disponibilidad_conocida,
                "ventana_completa": True,
                "ventana_ms": 60_000,
                "buy_notional": buy_n,
                "sell_notional": sell_n,
                "bid_notional_top20": bid20,
                "ask_notional_top20": ask20,
                "precio_cierre": precio,
                "precio_fuente": f["price_source"],
                "precio_event_ms": f["last_event_ms"],
                "precio_event_iso": utc_iso(f["last_event_ms"]) if f["last_event_ms"] is not None else None,
                "integridad_valida": True,
                "fuente": "research_flow_1m / research_book_1m",
                "cobertura": {
                    "flujo_presente": True,
                    "libro_presente": True,
                },
            }
            ventanas_validas.append(ventana)

        # Ordenar por decision_ms
        ventanas_validas.sort(key=lambda v: v["decision_ms"])

        # Agrupar en secuencias contiguas
        secuencias_contiguas: List[List[Dict[str, Any]]] = []
        if ventanas_validas:
            actual_seq: List[Dict[str, Any]] = [ventanas_validas[0]]
            for v in ventanas_validas[1:]:
                prev = actual_seq[-1]
                if (v["symbol"] == prev["symbol"] and
                        v["ventana_ms"] == prev["ventana_ms"] and
                        v["ventana_inicio_ms"] == prev["ventana_fin_ms"]):
                    actual_seq.append(v)
                else:
                    secuencias_contiguas.append(actual_seq)
                    actual_seq = [v]
            secuencias_contiguas.append(actual_seq)

        # Contar ternas contiguas
        ternas_contiguas = 0
        for seq in secuencias_contiguas:
            if len(seq) >= 3:
                ternas_contiguas += len(seq) - 2

        resultados_por_simbolo[simbolo] = {
            "filas_flujo": len(flujo_por_bucket),
            "filas_libro": len(libro_por_bucket),
            "buckets_comunes": len(buckets_comunes),
            "ventanas_validas": len(ventanas_validas),
            "ventanas_integridad_mala": sum(
                1 for v in ventanas_validas if not v["integridad_valida"]
            ),
            "ventanas_flujo_incompleto": sum(
                1 for v in ventanas_validas if not v["ventana_completa"]
            ),
            "ternas_contiguas": ternas_contiguas,
            "secuencias_contiguas": len(secuencias_contiguas),
            "ventanas_validas_detalle": ventanas_validas,
        }

    total_ventanas_validas = sum(
        r["ventanas_validas"] for r in resultados_por_simbolo.values()
    )
    total_ternas_contiguas = sum(
        r["ternas_contiguas"] for r in resultados_por_simbolo.values()
    )

    return {
        "source_run_id": "exp-v2-ventana-4-20261116a",
        "origen": "extraccion_offline_de_research.db (modo solo lectura)",
        "metodo": "SQLite modo solo lectura sobre research_flow_1m y research_book_1m",
        "definiciones": {
            "ratio": "(buy_notional - sell_notional) / (bid_notional_top20 + ask_notional_top20)",
            "ratio_alienado": "signo(move_24h_pct) * ratio",
            "ventana_valida": "buy_notional y sell_notional finitos y > 0; "
                              "bid_notional_top20 y ask_notional_top20 finitos y > 0; "
                              "precio_cierre finito y > 0; integridad OK",
            "ventana_contigua": "ventana_inicio_ms[k+1] == ventana_fin_ms[k], "
                                "mismo symbol, misma ventana_ms (60s)",
            "ternas_contiguas": "3 ventanas consecutivas que cumplen contigüidad",
        },
        "resultados_por_simbolo": resultados_por_simbolo,
        "resumen": {
            "simbolos_con_datos": len(resultados_por_simbolo),
            "total_ventanas_validas": total_ventanas_validas,
            "total_ternas_contiguas": total_ternas_contiguas,
            "simbolos_con_ternas": len(resultados_por_simbolo),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = __import__("argparse").ArgumentParser(
        description="Extrae cobertura de flujo/profundidad desde research.db (modo solo lectura)."
    )
    parser.add_argument(
        "--db",
        required=True,
        help="ruta al archivo research.db",
    )
    parser.add_argument(
        "--salida",
        required=True,
        help="ruta al JSON de salida con el reporte de cobertura",
    )
    args = parser.parse_args(argv)

    ruta_db = Path(args.db)
    if not ruta_db.exists():
        print(json.dumps({"error": f"base de datos no existe: {ruta_db}"}), file=sys.stderr)
        return 3

    ruta_salida = Path(args.salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)

    try:
        resumen = extraer_cobertura(ruta_db)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 3

    with io.open(ruta_salida, "w", encoding="utf-8", newline="\n") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1, sort_keys=True)

    print(json.dumps({"estado": "ok", "salida": str(ruta_salida), "resumen": resumen["resumen"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
