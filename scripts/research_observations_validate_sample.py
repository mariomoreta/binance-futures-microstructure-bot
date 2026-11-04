"""Valida la muestra de observaciones contra los registros fuente.

No reutiliza los helpers del generador: lee los artefactos publicados
(`observaciones.jsonl` y la muestra determinista) y recalcula con SQL
independiente sobre `historical.db` y `market_cache.db` (solo lectura).

Conjunto validado:
- las observaciones de la muestra determinista del generador, más
- un suplemento determinista que cubre todas las combinaciones
  (estado, clase_libro, clase_flujo) presentes en el artefacto, para que
  `publicada_despues_de_T` no quede sin comprobar.

Compara valores NO nulos (precios, retorno, disponibilidad y features de
libro/flujo). Los pares null-null se cuentan aparte y no se presentan como
acreditación. Además comprueba aritmética interna de la fila de flujo de origen
(delta = buy - sell; delta_ratio = delta / (buy + sell); base_volume =
buy_base + sell_base).

Salida: docs/evidence/research/universe_liquidity_v1/validacion_muestra.json
Exit code != 0 si hay cualquier discrepancia en valores comparables.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "data" / "historical" / "historical.db"
CACHE = ROOT / "data" / "market-cache" / "market_cache.db"
EVID = ROOT / "docs" / "evidence" / "research" / "universe_liquidity_v1"
MUESTRA = EVID / "observaciones_muestra_validacion.json"
JSONL = EVID / "observaciones.jsonl"
OUT = EVID / "validacion_muestra.json"

HORIZONTE_MS = 3_600_000
TOL = 1e-12
SUPLEMENTO_POR_CLASE = 2


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _fila(con: sqlite3.Connection, sql: str, params: Tuple) -> Optional[Dict[str, Any]]:
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


def _clase(as_of_ms: Optional[int], T: int) -> Optional[str]:
    if as_of_ms is None:
        return "desconocida"
    return "publicada_en_T" if int(as_of_ms) <= int(T) else "publicada_despues_de_T"


def _igual(a, b) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(a)), abs(float(b)))
    return a == b


def _parse_id(observation_id: str) -> Tuple[str, int, int, str]:
    partes = observation_id.split("|")
    sufijo = ""
    if partes[-1] in ("L", "F"):
        sufijo = partes[-1]
        partes = partes[:-1]
    return partes[0], int(partes[1]), int(partes[2]), sufijo


def _normalizar(o: Dict[str, Any], origen: str) -> Dict[str, Any]:
    return {
        "observation_id": o["observation_id"],
        "estado": o["estado"],
        "precio_T_registrado": o["precio"]["precio_T"],
        "close_time_T_registrado": o["precio"]["close_time_inicial_ms"],
        "precio_T_plus_h_registrado": o["precio"]["precio_T_plus_h"],
        "close_time_T_plus_h_registrado": o["precio"]["close_time_final_ms"],
        "retorno_registrado": o["retorno"],
        "as_of_libro": o["disponibilidad"]["libro"]["as_of_ms"],
        "clase_libro": o["disponibilidad"]["libro"]["clase"],
        "as_of_flujo": o["disponibilidad"]["flujo"]["as_of_ms"],
        "clase_flujo": o["disponibilidad"]["flujo"]["clase"],
        "libro_registrado": o["libro"],
        "flujo_registrado": o["flujo"],
        "origen": origen,
    }


def _componer_conjunto() -> List[Dict[str, Any]]:
    registros = {}
    grupos: Dict[Tuple, List[Dict[str, Any]]] = {}
    with open(JSONL, encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            registros[o["observation_id"]] = o
            clave = (
                o["estado"],
                o["disponibilidad"]["libro"]["clase"],
                o["disponibilidad"]["flujo"]["clase"],
            )
            grupos.setdefault(clave, []).append(o)

    muestra = json.loads(MUESTRA.read_text(encoding="utf-8"))
    conjunto: List[Dict[str, Any]] = []
    vistos = set()
    for m in muestra:
        oid = m["observation_id"]
        if oid not in registros:
            raise SystemExit(f"muestra no encontrada en jsonl: {oid}")
        conjunto.append(_normalizar(registros[oid], "muestra_generador"))
        vistos.add(oid)

    for clave in sorted(grupos, key=lambda k: tuple("" if x is None else x for x in k)):
        for o in grupos[clave][:SUPLEMENTO_POR_CLASE]:
            if o["observation_id"] in vistos:
                continue
            conjunto.append(_normalizar(o, "suplemento_por_clase"))
            vistos.add(o["observation_id"])
    return conjunto


def validar_una(con_hist, con_cache, m: Dict[str, Any]) -> Dict[str, Any]:
    symbol, bs, be, sufijo = _parse_id(m["observation_id"])
    T = int(be)
    T_plus_h = T + HORIZONTE_MS

    libro = _fila(
        con_hist,
        "SELECT symbol, bucket_start, bucket_end, spread_mean, imb_mean, "
        "micro_mean, bid20_mean, ask20_mean, first_event_ms, last_event_ms, "
        "as_of_ms FROM research_book_1m "
        "WHERE symbol=? AND bucket_start=? AND bucket_end=?",
        (symbol, bs, be),
    )
    flujo = _fila(
        con_hist,
        "SELECT symbol, bucket_start, bucket_end, buy_notional, sell_notional, "
        "delta, delta_ratio, buy_base, sell_base, base_volume, trade_count, "
        "price_close, first_event_ms, last_event_ms, as_of_ms "
        "FROM research_flow_1m "
        "WHERE symbol=? AND bucket_start=? AND bucket_end=?",
        (symbol, bs, be),
    )
    p_T = _fila(
        con_cache,
        "SELECT close, close_time FROM market_klines "
        "WHERE symbol=? AND interval='1h' AND close_time <= ? "
        "ORDER BY close_time DESC LIMIT 1",
        (symbol, T),
    )
    p_h = _fila(
        con_cache,
        "SELECT close, close_time FROM market_klines "
        "WHERE symbol=? AND interval='1h' AND close_time > ? AND close_time <= ? "
        "ORDER BY close_time ASC LIMIT 1",
        (symbol, T, T_plus_h),
    )

    precio_T = float(p_T["close"]) if p_T else None
    ct_T = int(p_T["close_time"]) if p_T else None
    precio_h = float(p_h["close"]) if p_h else None
    ct_h = int(p_h["close_time"]) if p_h else None
    retorno = (
        (precio_h - precio_T) / precio_T
        if (precio_T is not None and precio_h is not None and precio_T)
        else None
    )

    comprobaciones: List[Dict[str, Any]] = []

    def check(nombre: str, registrado, fuente) -> None:
        if registrado is None and fuente is None:
            comprobaciones.append({
                "campo": nombre, "registrado": None, "fuente": None,
                "comparable": False, "coincide": None,
            })
            return
        comprobaciones.append({
            "campo": nombre,
            "registrado": registrado,
            "fuente": fuente,
            "comparable": True,
            "coincide": _igual(registrado, fuente),
        })

    check("precio_T", m["precio_T_registrado"], precio_T)
    check("close_time_T", m["close_time_T_registrado"], ct_T)
    check("precio_T_plus_h", m["precio_T_plus_h_registrado"], precio_h)
    check("close_time_T_plus_h", m["close_time_T_plus_h_registrado"], ct_h)
    check("retorno", m["retorno_registrado"], retorno)
    check("as_of_libro", m["as_of_libro"], libro["as_of_ms"] if libro else None)
    check("as_of_flujo", m["as_of_flujo"], flujo["as_of_ms"] if flujo else None)
    check("clase_libro", m["clase_libro"], _clase(libro["as_of_ms"], T) if libro else None)
    check("clase_flujo", m["clase_flujo"], _clase(flujo["as_of_ms"], T) if flujo else None)

    reg_libro = m["libro_registrado"]
    if reg_libro is not None and libro is not None:
        for campo, col in (
            ("spread_mean_bps", "spread_mean"),
            ("imb_mean", "imb_mean"),
            ("micro_mean_bps", "micro_mean"),
            ("bid20_mean_base", "bid20_mean"),
            ("ask20_mean_base", "ask20_mean"),
            ("first_event_ms", "first_event_ms"),
            ("last_event_ms", "last_event_ms"),
        ):
            check(f"libro.{campo}", reg_libro[campo], libro[col])

    reg_flujo = m["flujo_registrado"]
    if reg_flujo is not None and flujo is not None:
        for campo, col in (
            ("buy_notional", "buy_notional"),
            ("sell_notional", "sell_notional"),
            ("delta_notional", "delta"),
            ("delta_ratio", "delta_ratio"),
            ("base_volume", "base_volume"),
            ("trade_count", "trade_count"),
            ("price_close", "price_close"),
            ("first_event_ms", "first_event_ms"),
            ("last_event_ms", "last_event_ms"),
        ):
            check(f"flujo.{campo}", reg_flujo[campo], flujo[col])

        # Aritmética interna de la fila de origen (no copiada del registro).
        delta_calc = float(flujo["buy_notional"]) - float(flujo["sell_notional"])
        denom = float(flujo["buy_notional"]) + float(flujo["sell_notional"])
        ratio_calc = delta_calc / denom if denom else None
        base_calc = float(flujo["buy_base"]) + float(flujo["sell_base"])
        comprobaciones.append({
            "campo": "flujo.delta_vs_buy_menos_sell",
            "registrado": flujo["delta"], "fuente": delta_calc,
            "comparable": True, "coincide": _igual(flujo["delta"], delta_calc),
        })
        comprobaciones.append({
            "campo": "flujo.delta_ratio_vs_delta_sobre_total",
            "registrado": flujo["delta_ratio"], "fuente": ratio_calc,
            "comparable": flujo["delta_ratio"] is not None,
            "coincide": (
                _igual(flujo["delta_ratio"], ratio_calc)
                if flujo["delta_ratio"] is not None else None
            ),
        })
        comprobaciones.append({
            "campo": "flujo.base_volume_vs_buy_base_mas_sell_base",
            "registrado": flujo["base_volume"], "fuente": base_calc,
            "comparable": True, "coincide": _igual(flujo["base_volume"], base_calc),
        })

    comparables = [c for c in comprobaciones if c["comparable"]]
    discrepancias = [c for c in comparables if not c["coincide"]]
    return {
        "observation_id": m["observation_id"],
        "origen": m["origen"],
        "simbolo": symbol,
        "bucket_start": bs,
        "bucket_end": be,
        "sufijo": sufijo,
        "estado": m["estado"],
        "clase_libro": m["clase_libro"],
        "clase_flujo": m["clase_flujo"],
        "fuente_libro_presente": libro is not None,
        "fuente_flujo_presente": flujo is not None,
        "comprobaciones": comprobaciones,
        "n_comparables": len(comparables),
        "n_no_comparables_null_null": len(comprobaciones) - len(comparables),
        "n_discrepancias": len(discrepancias),
    }


def main() -> int:
    conjunto = _componer_conjunto()
    sha_hist_antes = _sha256(HIST)
    sha_cache_antes = _sha256(CACHE)

    con_hist = _ro(HIST)
    con_cache = _ro(CACHE)
    try:
        filas = [validar_una(con_hist, con_cache, m) for m in conjunto]
    finally:
        con_hist.close()
        con_cache.close()

    sha_hist_despues = _sha256(HIST)
    sha_cache_despues = _sha256(CACHE)

    total_comparables = sum(f["n_comparables"] for f in filas)
    total_discrepancias = sum(f["n_discrepancias"] for f in filas)
    total_null_null = sum(f["n_no_comparables_null_null"] for f in filas)
    con_valor_no_nulo = sum(
        1 for f in filas if any(c["comparable"] for c in f["comprobaciones"])
    )
    cobertura = sorted({
        (f["estado"], f["clase_libro"], f["clase_flujo"]) for f in filas
    }, key=lambda k: tuple("" if x is None else x for x in k))

    artefacto = {
        "fuente_muestra": str(MUESTRA.relative_to(ROOT)),
        "fuente_registros": str(JSONL.relative_to(ROOT)),
        "db_sha256_antes": {"historical": sha_hist_antes, "market_cache": sha_cache_antes},
        "db_sha256_despues": {"historical": sha_hist_despues, "market_cache": sha_cache_despues},
        "db_sin_cambios": (
            sha_hist_antes == sha_hist_despues
            and sha_cache_antes == sha_cache_despues
        ),
        "n_observaciones_validadas": len(filas),
        "n_con_al_menos_un_valor_comparable": con_valor_no_nulo,
        "n_comprobaciones_comparables": total_comparables,
        "n_comprobaciones_null_null": total_null_null,
        "n_discrepancias": total_discrepancias,
        "cobertura_estado_clases": [
            {"estado": e, "clase_libro": l, "clase_flujo": f} for e, l, f in cobertura
        ],
        "resultado": "PASS" if total_discrepancias == 0 and total_comparables > 0 else "FAIL",
        "filas": filas,
    }
    OUT.write_text(json.dumps(artefacto, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"observaciones={len(filas)} con_valor_comparable={con_valor_no_nulo} "
        f"comparables={total_comparables} null_null={total_null_null} "
        f"discrepancias={total_discrepancias} resultado={artefacto['resultado']}"
    )
    print(f"combinaciones estado/clase cubiertas: {len(cobertura)}")
    for e, l, f in cobertura:
        print(f"  - {e} | libro={l} | flujo={f}")
    print("DBs sin cambios:", artefacto["db_sin_cambios"])
    print(f"Escrito: {OUT}")
    return 0 if artefacto["resultado"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
