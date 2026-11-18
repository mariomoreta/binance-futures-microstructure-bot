#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extractor offline de cobertura desde research.db (modo solo lectura).

Acredita lo que cuenta: cada pareja (contrato, intervalo de un minuto) debe
superar verificaciones explícitas antes de aportar una ventana; cada ventana
debe superar completitud, integridad por intervalo, valores válidos, precio y
disponibilidad antes de aportar una terna. Los motivos de exclusión se
devuelven en el JSON en lugar de calcularse y perderse.

Alcance y límites:
  - Abre la base con `file:...?mode=ro` (URI). No crea, no migra, no escribe.
  - No usa red ni Binance. Solo lee las tablas de agregados de un minuto.
  - No mezcla corridas: una pareja exige el mismo `run_id` no vacío en ambas
    fuentes. Una fila contradictoria con la misma clave no se sustituye en
    silencio: la clave queda excluida y el conflicto se cuenta.
  - `as_of_ms` se exige por fuente. Si falta uno, la disponibilidad conjunta
    es UNKNOWN (nunca se toma prestado el de la otra fuente). Si ambos están
    acreditados se usa el máximo. No es el cierre nominal (`bucket_end`) ni el
    instante efectivo de detección.
  - `price_close` de `research_flow_1m` es el cierre del agregado de
    operaciones (`price_source='aggTrade'`), NO el mid del libro ni un precio
    ejecutable. Así se identifica en el JSON.

Uso:
  python scripts/extraer_cobertura_research_db.py \\
    --db C:\\proyectos\\binance-futures-data\\exp-v2-ventana-4-20261116a\\research.db \\
    --salida C:\\proyectos\\binance-futures-data\\exp-v2-ventana-4-20261116a-cobertura\\cobertura.json \\
    [--observaciones <observaciones.jsonl>]

`--observaciones` es opcional y solo se usa para acreditar, por separado, las
observaciones del piloto (no se derivan de research.db).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION_EXTRACTOR = "cobertura-research-db/v2"

VENTANA_MS = 60_000
PRECIO_SOURCE_FLUJO = "aggTrade"
PRECIO_SOURCE_LIBRO = "depth20"
MAX_EJEMPLOS = 5

# Cadena publicada el 2026-11-16 (referencia para contraste, NO objetivo).
CADENA_PUBLICADA = {
    "ternas_solo_flujo": 1107,
    "ternas_parejas": 1032,
    "ternas_integridad": 501,
    "ternas_precio": 501,
    "ternas_finales_declaradas": 0,
}

COLUMNAS_FLUJO = [
    "symbol",
    "bucket_start",
    "bucket_end",
    "bucket_size_s",
    "buy_notional",
    "sell_notional",
    "price_close",
    "first_event_ms",
    "last_event_ms",
    "data_quality",
    "run_id",
    "as_of_ms",
    "price_source",
    "dataset_id",
]

COLUMNAS_LIBRO = [
    "symbol",
    "bucket_start",
    "bucket_end",
    "sample_count",
    "bid20_mean",
    "ask20_mean",
    "depth_gaps",
    "degraded",
    "crossed",
    "first_event_ms",
    "last_event_ms",
    "run_id",
    "as_of_ms",
    "price_source",
    "dataset_id",
]


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


def _es_entero(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _es_entero_positivo(valor: Any) -> bool:
    return _es_entero(valor) and valor > 0


def _es_numero_finito(valor: Any) -> bool:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return False
    return math.isfinite(float(valor))


def _es_numero_positivo(valor: Any) -> bool:
    return _es_numero_finito(valor) and float(valor) > 0.0


def _intervalo(symbol: Any, inicio: Any, fin: Any) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "ventana_inicio_ms": inicio,
        "ventana_fin_ms": fin,
        "ventana_inicio_iso": utc_iso(inicio) if _es_entero(inicio) else None,
        "ventana_fin_iso": utc_iso(fin) if _es_entero(fin) else None,
    }


def _sumar_motivo(acc: Dict[str, Any], codigo: str, ejemplo: Dict[str, Any]) -> None:
    """Acumula un motivo solapable (una ventana puede tener varios)."""
    acc["motivos_solapables"][codigo] = acc["motivos_solapables"].get(codigo, 0) + 1
    lista = acc["ejemplos"].setdefault(codigo, [])
    if len(lista) < MAX_EJEMPLOS and ejemplo not in lista:
        lista.append(ejemplo)


def _nuevo_acumulador() -> Dict[str, Any]:
    return {"motivos_solapables": {}, "ejemplos": {}}


def _serializar_acumulador(acc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "motivos_solapables": dict(sorted(acc["motivos_solapables"].items())),
        "motivos_distintos": len(acc["motivos_solapables"]),
        "suma_motivos": sum(acc["motivos_solapables"].values()),
        "ejemplos": {k: acc["ejemplos"][k] for k in sorted(acc["ejemplos"])},
    }


def _ternas_contiguas(
    ventanas: Iterable[Dict[str, Any]],
) -> Tuple[int, int, Dict[str, int]]:
    """Cuenta ternas contiguas deslizantes y secuencias por símbolo.

    Contigüidad: mismo contrato y `ventana_inicio_ms[k+1] == ventana_fin_ms[k]`
    con duración de un minuto ya validada aguas arriba.
    """
    por_simbolo: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
    for v in ventanas:
        por_simbolo[str(v["symbol"])].append(
            (int(v["ventana_inicio_ms"]), int(v["ventana_fin_ms"]))
        )
    total_ternas = 0
    total_secuencias = 0
    ternas_por_simbolo: Dict[str, int] = {}
    for symbol in sorted(por_simbolo):
        tramos = sorted(por_simbolo[symbol])
        secuencias: List[int] = []
        actual = 1
        for prev, act in zip(tramos, tramos[1:]):
            if act[0] == prev[1]:
                actual += 1
            else:
                secuencias.append(actual)
                actual = 1
        secuencias.append(actual)
        ternas = sum(n - 2 for n in secuencias if n >= 3)
        total_ternas += ternas
        total_secuencias += len(secuencias)
        if ternas:
            ternas_por_simbolo[symbol] = ternas
    return total_ternas, total_secuencias, ternas_por_simbolo


# ---------------------------------------------------------------------------
# Lectura en solo lectura
# ---------------------------------------------------------------------------

def conectar_solo_lectura(ruta_db: Path) -> sqlite3.Connection:
    """Abre la base de datos en modo solo lectura (URI file:...?mode=ro)."""
    uri = f"file:{ruta_resuelta(ruta_db)}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def ruta_resuelta(ruta: Path) -> str:
    return str(ruta.resolve())


def _cargar_tabla(
    cur: sqlite3.Cursor, tabla: str, columnas: List[str]
) -> Tuple[Dict[Tuple[str, int], Dict[str, Any]], Dict[str, Any]]:
    """Carga una tabla indexada por (symbol, bucket_start).

    Detecta claves duplicadas (idénticas o contradictorias). Una clave
    duplicada queda fuera del mapa y se reporta: nunca se sustituye la fila
    anterior en silencio.
    """
    cur.execute(f"SELECT {','.join(columnas)} FROM {tabla}")
    filas: Dict[Tuple[str, int], Dict[str, Any]] = {}
    claves_duplicadas: List[Tuple[str, int]] = []
    ya_marcadas: set = set()
    duplicadas: Dict[str, Any] = {
        "identicas": 0,
        "contradictorias": 0,
        "claves": claves_duplicadas,
    }
    for valores in cur.fetchall():
        fila = dict(zip(columnas, valores))
        clave = (fila["symbol"], fila["bucket_start"])
        if clave in ya_marcadas:
            # Tercera o posterior fila con la misma clave: se cuenta, no se usa.
            duplicadas["contradictorias"] += 1
            continue
        if clave in filas:
            previa = filas[clave]
            if previa == fila:
                duplicadas["identicas"] += 1
            else:
                duplicadas["contradictorias"] += 1
            claves_duplicadas.append(clave)
            ya_marcadas.add(clave)
            # La fila previa se conserva solo como referencia: la clave queda
            # marcada y ninguna pareja que la use se acredita.
            continue
        filas[clave] = fila
    duplicadas["ejemplos"] = [
        {"symbol": symbol, "bucket_start": inicio}
        for symbol, inicio in claves_duplicadas[:MAX_EJEMPLOS]
    ]
    return filas, duplicadas


# ---------------------------------------------------------------------------
# Acreditación
# ---------------------------------------------------------------------------

def _motivos_pareja(
    f: Dict[str, Any], l: Dict[str, Any]
) -> List[str]:
    """Defectos que impiden contar la pareja como (contrato, minuto).

    Solo valida identidad y procedencia de la pareja: mismo contrato (clave),
    ambos límites presentes, cierre nominal coincidente, misma corrida y
    procedencia declarada. La forma del minuto (duración/completitud) se
    acredita después, como requisito propio.
    """
    motivos: List[str] = []
    for nombre, fila in (("flujo", f), ("libro", l)):
        if not _es_entero(fila["bucket_start"]) or not _es_entero(fila["bucket_end"]):
            motivos.append(f"{nombre}_limites_no_enteros")
    if (
        _es_entero(f["bucket_start"])
        and _es_entero(f["bucket_end"])
        and _es_entero(l["bucket_start"])
        and _es_entero(l["bucket_end"])
        and f["bucket_end"] != l["bucket_end"]
    ):
        motivos.append("cierre_nominal_distinto")
    if f["run_id"] is None or l["run_id"] is None:
        motivos.append("corrida_ausente")
    elif f["run_id"] != l["run_id"]:
        motivos.append("corrida_distinta")
    if f["price_source"] != PRECIO_SOURCE_FLUJO:
        motivos.append("procedencia_flujo_no_acreditada")
    if l["price_source"] != PRECIO_SOURCE_LIBRO:
        motivos.append("procedencia_libro_no_acreditada")
    return motivos


def _motivos_completitud(f: Dict[str, Any], l: Dict[str, Any]) -> List[str]:
    """Completitud temporal: el minuto está íntegro como intervalo."""
    motivos: List[str] = []
    if f["bucket_size_s"] != 60:
        motivos.append("flujo_tamano_distinto_de_60s")
    for nombre, fila in (("flujo", f), ("libro", l)):
        if fila["bucket_end"] - fila["bucket_start"] != VENTANA_MS:
            motivos.append(f"{nombre}_intervalo_no_es_un_minuto")
        if fila["bucket_start"] % VENTANA_MS != 0:
            motivos.append(f"{nombre}_inicio_no_alineado")
        primero = fila["first_event_ms"]
        ultimo = fila["last_event_ms"]
        if not _es_entero(primero) or not _es_entero(ultimo):
            motivos.append(f"{nombre}_eventos_ausentes")
            continue
        if not (fila["bucket_start"] <= primero <= ultimo <= fila["bucket_end"]):
            motivos.append(f"{nombre}_eventos_fuera_del_intervalo")
    return motivos


def _motivos_integridad(f: Dict[str, Any], l: Dict[str, Any]) -> List[str]:
    """Integridad por intervalo de cada fuente.

    Un valor ausente/desconocido no se interpreta como integridad válida.
    """
    motivos: List[str] = []
    if f["data_quality"] != "OK":
        motivos.append("flujo_data_quality_no_ok")
    if l["degraded"] != 0:
        motivos.append("libro_degradado")
    if l["crossed"] != 0:
        motivos.append("libro_cruzado")
    if l["depth_gaps"] != 0:
        motivos.append("libro_huecos_profundidad")
    if not _es_entero(l["sample_count"]) or l["sample_count"] <= 0:
        motivos.append("libro_sin_muestras")
    return motivos


def _motivos_valores(f: Dict[str, Any], l: Dict[str, Any]) -> List[str]:
    """Valores válidos. Un cero REGISTRADO por la fuente es admisible; un dato
    ausente no es cero."""
    motivos: List[str] = []
    for nombre in ("buy_notional", "sell_notional"):
        valor = f[nombre]
        if valor is None:
            motivos.append(f"flujo_{nombre}_ausente")
        elif not _es_numero_finito(valor) or float(valor) < 0.0:
            motivos.append(f"flujo_{nombre}_invalido")
    for nombre in ("bid20_mean", "ask20_mean"):
        valor = l[nombre]
        if valor is None:
            motivos.append(f"libro_{nombre}_ausente")
        elif not _es_numero_positivo(valor):
            motivos.append(f"libro_{nombre}_no_positivo")
    return motivos


def _motivos_precio(f: Dict[str, Any]) -> List[str]:
    precio = f["price_close"]
    if precio is None:
        return ["precio_ausente"]
    if not _es_numero_finito(precio):
        return ["precio_no_finito"]
    if float(precio) <= 0.0:
        return ["precio_no_positivo"]
    return []


def _disponibilidad(
    f: Dict[str, Any], l: Dict[str, Any]
) -> Tuple[Optional[int], List[str]]:
    """Disponibilidad conjunta: exige `as_of_ms` válido en CADA fuente.

    Si falta uno, la disponibilidad conjunta es UNKNOWN (None) y la ventana no
    se acredita. Si ambos están acreditados, se usa el máximo. Nunca se toma
    prestado el timestamp de la otra fuente.
    """
    motivos: List[str] = []
    as_of_flujo = f["as_of_ms"]
    as_of_libro = l["as_of_ms"]
    if not _es_entero_positivo(as_of_flujo):
        motivos.append("as_of_flujo_ausente" if as_of_flujo is None else "as_of_flujo_invalido")
    if not _es_entero_positivo(as_of_libro):
        motivos.append("as_of_libro_ausente" if as_of_libro is None else "as_of_libro_invalido")
    if motivos:
        return None, motivos
    return max(int(as_of_flujo), int(as_of_libro)), []


def _ventana_acreditada(
    symbol: str,
    f: Dict[str, Any],
    l: Dict[str, Any],
    disponibilidad_ms: int,
) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "observation_id": f"{symbol}|{f['bucket_start']}",
        "ventana_inicio_ms": f["bucket_start"],
        "ventana_fin_ms": f["bucket_end"],
        "ventana_ms": VENTANA_MS,
        "buy_notional": float(f["buy_notional"]),
        "sell_notional": float(f["sell_notional"]),
        "bid_notional_top20": float(l["bid20_mean"]),
        "ask_notional_top20": float(l["ask20_mean"]),
        "precio_cierre": float(f["price_close"]),
        "precio_definicion": (
            "price_close de research_flow_1m: cierre del agregado de "
            "operaciones aggTrade del minuto; no es libro_mid ni precio "
            "ejecutable"
        ),
        "precio_fuente": f["price_source"],
        "precio_event_ms": f["last_event_ms"],
        "precio_event_iso": utc_iso(f["last_event_ms"]),
        "disponibilidad_ms": disponibilidad_ms,
        "disponibilidad_iso": utc_iso(disponibilidad_ms),
        "disponibilidad_conocida": True,
        "disponibilidad_definicion": (
            "max(as_of_ms flujo, as_of_ms libro), ambos acreditados; no es el "
            "cierre nominal bucket_end ni el instante efectivo de deteccion"
        ),
        "run_id": f["run_id"],
        "ventana_completa": True,
        "integridad_valida": True,
        "fuente": "research_flow_1m / research_book_1m",
    }


# ---------------------------------------------------------------------------
# Población A: observaciones del piloto (opcional, por separado)
# ---------------------------------------------------------------------------

def leer_observaciones_piloto(ruta: Path) -> Dict[str, Any]:
    """Acredita el conteo de observaciones del piloto desde su JSONL.

    No se deriva de research.db ni se mezcla con los agregados de un minuto.
    """
    if not ruta.exists():
        return {
            "acreditado": False,
            "motivo": f"archivo de observaciones no existe: {ruta}",
        }
    total = 0
    aptas = 0
    simbolos = set()
    estados: Counter = Counter()
    motivos_descarte: Counter = Counter()
    with io.open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                o = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if o.get("kind") != "observacion":
                continue
            total += 1
            simbolos.add(o.get("symbol"))
            estados[str(o.get("estado"))] += 1
            if o.get("apto_para_evaluacion") is True:
                aptas += 1
            else:
                for motivo in o.get("motivos") or []:
                    motivos_descarte[str(motivo)] += 1
    return {
        "acreditado": True,
        "fuente": str(ruta),
        "total": total,
        "aptas": aptas,
        "descartadas": total - aptas,
        "simbolos": len(simbolos),
        "estados": dict(sorted(estados.items())),
        "motivos_descarte_solapables": dict(sorted(motivos_descarte.items())),
        "nota": (
            "observaciones.jsonl del piloto: no son agregados de un minuto y "
            "no se mezclan con la poblacion B"
        ),
    }


# ---------------------------------------------------------------------------
# Extracción
# ---------------------------------------------------------------------------

def extraer_cobertura(
    ruta_db: Path,
    ruta_observaciones: Optional[Path] = None,
) -> Dict[str, Any]:
    """Extrae y acredita cobertura de flujo y libro desde research.db."""
    sha_db = sha256_archivo(ruta_db)
    bytes_db = ruta_db.stat().st_size

    con = conectar_solo_lectura(ruta_db)
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tablas = {r[0] for r in cur.fetchall()}
        tablas_necesarias = {"research_flow_1m", "research_book_1m"}
        faltantes = tablas_necesarias - tablas
        if faltantes:
            raise ValueError(f"Tablas ausentes en la BD: {sorted(faltantes)}")

        flujo, dup_flujo = _cargar_tabla(cur, "research_flow_1m", COLUMNAS_FLUJO)
        libro, dup_libro = _cargar_tabla(cur, "research_book_1m", COLUMNAS_LIBRO)
    finally:
        con.close()

    claves_duplicadas = set()
    for dup in (dup_flujo, dup_libro):
        for symbol, inicio in dup["claves"]:
            claves_duplicadas.add((symbol, inicio))

    claves_flujo = set(flujo)
    claves_libro = set(libro)
    claves_pareja = claves_flujo & claves_libro
    solo_flujo = claves_flujo - claves_libro
    solo_libro = claves_libro - claves_flujo

    acc_pareja = _nuevo_acumulador()
    parejas_acreditadas: List[Tuple[str, int]] = []
    for symbol, inicio in sorted(claves_pareja):
        ejemplo = _intervalo(symbol, inicio, flujo[(symbol, inicio)]["bucket_end"])
        if (symbol, inicio) in claves_duplicadas:
            _sumar_motivo(acc_pareja, "clave_duplicada", ejemplo)
            continue
        motivos = _motivos_pareja(flujo[(symbol, inicio)], libro[(symbol, inicio)])
        if motivos:
            for motivo in sorted(set(motivos)):
                _sumar_motivo(acc_pareja, motivo, ejemplo)
            continue
        parejas_acreditadas.append((symbol, inicio))

    # Etapas: cada ventana se excluye en el primer requisito que no supera.
    etapas: List[Dict[str, Any]] = []
    supervivientes_pareja = list(parejas_acreditadas)

    def _ejecutar_etapa(
        nombre: str,
        claves: List[Tuple[str, int]],
        evaluador,
    ) -> List[Tuple[str, int]]:
        acc = _nuevo_acumulador()
        siguientes: List[Tuple[str, int]] = []
        for symbol, inicio in claves:
            f = flujo[(symbol, inicio)]
            l = libro[(symbol, inicio)]
            ejemplo = _intervalo(symbol, inicio, f["bucket_end"])
            motivos = evaluador(f, l)
            if motivos:
                for motivo in sorted(set(motivos)):
                    _sumar_motivo(acc, motivo, ejemplo)
                continue
            siguientes.append((symbol, inicio))
        etapas.append(
            {
                "orden": len(etapas) + 1,
                "requisito": nombre,
                "entrada": len(claves),
                "excluidas": len(claves) - len(siguientes),
                "supervivientes": len(siguientes),
                **_serializar_acumulador(acc),
            }
        )
        return siguientes

    supervivientes_pareja = _ejecutar_etapa("completitud", supervivientes_pareja, _motivos_completitud)
    supervivientes_pareja = _ejecutar_etapa("integridad_por_intervalo", supervivientes_pareja, _motivos_integridad)
    supervivientes_pareja = _ejecutar_etapa("valores_validos", supervivientes_pareja, _motivos_valores)
    supervivientes_pareja = _ejecutar_etapa(
        "precio", supervivientes_pareja, lambda f, l: _motivos_precio(f)
    )

    # Disponibilidad: etapa propia; devuelve (entrada, motivos, disponibilidad).
    acc_disp = _nuevo_acumulador()
    ventanas: List[Dict[str, Any]] = []
    for symbol, inicio in supervivientes_pareja:
        f = flujo[(symbol, inicio)]
        l = libro[(symbol, inicio)]
        ejemplo = _intervalo(symbol, inicio, f["bucket_end"])
        disponibilidad_ms, motivos = _disponibilidad(f, l)
        if motivos:
            for motivo in sorted(set(motivos)):
                _sumar_motivo(acc_disp, motivo, ejemplo)
            continue
        ventanas.append(_ventana_acreditada(symbol, f, l, int(disponibilidad_ms)))
    etapas.append(
        {
            "orden": len(etapas) + 1,
            "requisito": "disponibilidad_acreditada",
            "entrada": len(supervivientes_pareja),
            "excluidas": len(supervivientes_pareja) - len(ventanas),
            "supervivientes": len(ventanas),
            **_serializar_acumulador(acc_disp),
        }
    )

    ternas, secuencias, ternas_por_simbolo = _ternas_contiguas(ventanas)

    # Referencias no acreditadas (solo trazabilidad de la cadena publicada).
    ventanas_flujo_ref = [
        {
            "symbol": symbol,
            "ventana_inicio_ms": f["bucket_start"],
            "ventana_fin_ms": f["bucket_end"],
        }
        for (symbol, _), f in sorted(flujo.items())
    ]
    ternas_solo_flujo, _, _ = _ternas_contiguas(ventanas_flujo_ref)
    ventanas_pareja_ref = [
        {
            "symbol": symbol,
            "ventana_inicio_ms": flujo[(symbol, inicio)]["bucket_start"],
            "ventana_fin_ms": flujo[(symbol, inicio)]["bucket_end"],
        }
        for symbol, inicio in sorted(claves_pareja)
    ]
    ternas_parejas, _, _ = _ternas_contiguas(ventanas_pareja_ref)

    # Cadena: ternas que sobreviven a cada requisito. Se recalcula de forma
    # independiente acumulando las etapas sobre las claves acreditadas.
    cadena: List[Dict[str, Any]] = [
        {
            "etapa": "parejas_iniciales",
            "entrada": len(claves_pareja),
            "excluidas": 0,
            "supervivientes": len(claves_pareja),
            "ternas_tras_requisito": ternas_parejas,
            "acreditado": False,
            "nota": "parejas sin acreditar por requisito (referencia)",
        }
    ]
    claves_actuales = list(parejas_acreditadas)
    evaluadores = [
        ("completitud", _motivos_completitud),
        ("integridad_por_intervalo", _motivos_integridad),
        ("valores_validos", _motivos_valores),
        ("precio", lambda f, l: _motivos_precio(f)),
        (
            "disponibilidad_acreditada",
            lambda f, l: _disponibilidad(f, l)[1],
        ),
    ]
    etapa_por_nombre = {e["requisito"]: e for e in etapas}
    for nombre, evaluador in evaluadores:
        claves_actuales = [
            (symbol, inicio)
            for symbol, inicio in claves_actuales
            if not evaluador(flujo[(symbol, inicio)], libro[(symbol, inicio)])
        ]
        ref = [
            {
                "symbol": symbol,
                "ventana_inicio_ms": flujo[(symbol, inicio)]["bucket_start"],
                "ventana_fin_ms": flujo[(symbol, inicio)]["bucket_end"],
            }
            for symbol, inicio in claves_actuales
        ]
        t, _, _ = _ternas_contiguas(ref)
        etapa = etapa_por_nombre[nombre]
        cadena.append(
            {
                "etapa": nombre,
                "entrada": etapa["entrada"],
                "excluidas": etapa["excluidas"],
                "supervivientes": etapa["supervivientes"],
                "ternas_tras_requisito": t,
                "acreditado": True,
            }
        )

    # Exclusiones únicas y motivos solapables de todas las etapas.
    acc_total = _nuevo_acumulador()
    for etapa in etapas:
        for motivo, cuenta in etapa["motivos_solapables"].items():
            acc_total["motivos_solapables"][motivo] = (
                acc_total["motivos_solapables"].get(motivo, 0) + cuenta
            )
        for motivo, ejemplos in etapa["ejemplos"].items():
            lista = acc_total["ejemplos"].setdefault(motivo, [])
            for ejemplo in ejemplos:
                if len(lista) < MAX_EJEMPLOS and ejemplo not in lista:
                    lista.append(ejemplo)
    for motivo, cuenta in acc_pareja["motivos_solapables"].items():
        acc_total["motivos_solapables"][motivo] = (
            acc_total["motivos_solapables"].get(motivo, 0) + cuenta
        )
    for motivo, ejemplos in acc_pareja["ejemplos"].items():
        lista = acc_total["ejemplos"].setdefault(motivo, [])
        for ejemplo in ejemplos:
            if len(lista) < MAX_EJEMPLOS and ejemplo not in lista:
                lista.append(ejemplo)

    exclusiones_unicas = {
        "parejas_no_acreditadas": len(claves_pareja) - len(parejas_acreditadas),
        "ventanas_excluidas_por_requisito": {
            etapa["requisito"]: etapa["excluidas"] for etapa in etapas
        },
        "ventanas_excluidas_total": sum(e["excluidas"] for e in etapas),
        "claves_flujo_sin_contraparte": len(solo_flujo),
        "claves_libro_sin_contraparte": len(solo_libro),
        "claves_duplicadas": len(claves_duplicadas),
    }

    return {
        "version_extractor": VERSION_EXTRACTOR,
        "origen": {
            "db": str(ruta_db),
            "db_sha256": sha_db,
            "db_bytes": bytes_db,
            "modo": "sqlite mode=ro (solo lectura, sin red)",
        },
        "metodo": {
            "emparejamiento": "(symbol, bucket_start) presente en ambas tablas, "
                              "mismo run_id y mismo bucket_end",
            "ventana": "intervalo completo de un minuto por contrato",
            "contigüidad": "ventana_inicio_ms[k+1] == ventana_fin_ms[k], "
                           "mismo symbol, ventana_ms=60000",
            "terna": "3 ventanas acreditadas consecutivas que cumplen contigüidad",
        },
        "definiciones": {
            "precio": (
                "precio_cierre = price_close de research_flow_1m, cierre del "
                "agregado de operaciones (price_source='aggTrade'). NO es "
                "libro_mid y NO es un precio ejecutable."
            ),
            "disponibilidad": (
                "disponibilidad_ms = max(as_of_ms flujo, as_of_ms libro) con "
                "AMBOS acreditados; si falta uno, UNKNOWN y la ventana no se "
                "acredita. No es bucket_end ni el instante efectivo de deteccion."
            ),
            "cero_registrado": (
                "buy_notional/sell_notional = 0 registrado por la fuente es "
                "admisible; NULL (ausente) no es cero y excluye la ventana."
            ),
            "acreditacion": (
                "una ventana aporta a una terna solo si supera completitud, "
                "integridad por intervalo, valores validos, precio y "
                "disponibilidad; una terna acreditada NO es patron detectado "
                "ni rentabilidad"
            ),
        },
        "poblacion_a_observaciones_piloto": (
            leer_observaciones_piloto(ruta_observaciones)
            if ruta_observaciones is not None
            else {
                "acreditado": False,
                "motivo": (
                    "no se paso --observaciones: research.db no contiene las "
                    "observaciones del piloto; poblacion A UNKNOWN"
                ),
            }
        ),
        "poblacion_b_agregados_1m": {
            "fuentes": {
                "research_flow_1m": {
                    "filas": len(flujo),
                    "claves_unicas": len(claves_flujo),
                    "claves_duplicadas": {
                        "identicas": dup_flujo["identicas"],
                        "contradictorias": dup_flujo["contradictorias"],
                        "ejemplos": dup_flujo["ejemplos"],
                    },
                },
                "research_book_1m": {
                    "filas": len(libro),
                    "claves_unicas": len(claves_libro),
                    "claves_duplicadas": {
                        "identicas": dup_libro["identicas"],
                        "contradictorias": dup_libro["contradictorias"],
                        "ejemplos": dup_libro["ejemplos"],
                    },
                },
            },
            "parejas_iniciales": len(claves_pareja),
            "parejas_no_acreditadas": {
                "total": len(claves_pareja) - len(parejas_acreditadas),
                **_serializar_acumulador(acc_pareja),
            },
            "parejas_acreditadas": len(parejas_acreditadas),
            "sin_contraparte": {
                "flujo_sin_libro": len(solo_flujo),
                "libro_sin_flujo": len(solo_libro),
                "ejemplos_flujo_sin_libro": [
                    _intervalo(s, i, flujo[(s, i)]["bucket_end"])
                    for s, i in sorted(solo_flujo)[:MAX_EJEMPLOS]
                ],
                "ejemplos_libro_sin_flujo": [
                    _intervalo(s, i, libro[(s, i)]["bucket_end"])
                    for s, i in sorted(solo_libro)[:MAX_EJEMPLOS]
                ],
            },
            "requisitos": etapas,
            "ventanas_acreditadas": len(ventanas),
            "exclusiones": exclusiones_unicas,
            "motivos_totales": _serializar_acumulador(acc_total),
            "ternas": {
                "secuencias_contiguas": secuencias,
                "ternas": ternas,
                "simbolos_con_ternas": len(ternas_por_simbolo),
                "ternas_por_simbolo": dict(sorted(ternas_por_simbolo.items())),
                "definicion": (
                    "terna acreditada = 3 ventanas acreditadas contiguas; no "
                    "implica patron detectado ni rentabilidad"
                ),
            },
            "cadena": cadena,
            "referencia_no_acreditada": {
                "ternas_solo_flujo": ternas_solo_flujo,
                "ternas_parejas_iniciales": ternas_parejas,
                "nota": (
                    "solo trazabilidad de la cadena publicada; estas ternas no "
                    "usan contraparte de libro ni acreditacion completa, por lo "
                    "que no cuentan como evaluables"
                ),
            },
            "ventanas_detalle": ventanas,
        },
        "comparacion_cadena_publicada": {
            "publicada_20261116": dict(CADENA_PUBLICADA),
            "regenerada": {
                "ternas_solo_flujo": ternas_solo_flujo,
                "ternas_parejas": ternas_parejas,
                "ternas_integridad": next(
                    (
                        e["ternas_tras_requisito"]
                        for e in cadena
                        if e["etapa"] == "integridad_por_intervalo"
                    ),
                    None,
                ),
                "ternas_precio": next(
                    (e["ternas_tras_requisito"] for e in cadena if e["etapa"] == "precio"),
                    None,
                ),
                "ternas_finales": ternas,
            },
            "nota": (
                "las cifras publicadas son referencia de contraste, no objetivo; "
                "prevalece la salida regenerada con acreditacion por requisito"
            ),
        },
        "resumen": {
            "simbolos_con_datos": len({s for s, _ in claves_flujo | claves_libro}),
            "parejas_iniciales": len(claves_pareja),
            "ventanas_acreditadas": len(ventanas),
            "ternas_acreditadas": ternas,
            "simbolos_con_ternas": len(ternas_por_simbolo),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extrae y acredita cobertura de flujo/profundidad desde research.db "
            "(modo solo lectura, sin red)."
        )
    )
    parser.add_argument("--db", required=True, help="ruta al archivo research.db")
    parser.add_argument(
        "--salida", required=True, help="ruta al JSON de salida con la cobertura"
    )
    parser.add_argument(
        "--observaciones",
        default=None,
        help=(
            "opcional: observaciones.jsonl del piloto para acreditar la "
            "poblacion A por separado (no se deriva de research.db)"
        ),
    )
    args = parser.parse_args(argv)

    ruta_db = Path(args.db)
    if not ruta_db.is_file():
        print(json.dumps({"error": f"base de datos no existe o no es un archivo: {ruta_db}"}), file=sys.stderr)
        return 3

    ruta_salida = Path(args.salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)

    try:
        resumen = extraer_cobertura(
            ruta_db,
            Path(args.observaciones) if args.observaciones else None,
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 3
    except sqlite3.Error as exc:
        print(json.dumps({"error": f"error de SQLite: {exc}"}), file=sys.stderr)
        return 3

    with io.open(ruta_salida, "w", encoding="utf-8", newline="\n") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1, sort_keys=True)

    print(
        json.dumps(
            {
                "estado": "ok",
                "salida": str(ruta_salida),
                "resumen": resumen["resumen"],
                "db_sha256": resumen["origen"]["db_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
