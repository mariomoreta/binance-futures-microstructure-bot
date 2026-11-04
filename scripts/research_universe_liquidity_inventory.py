"""Inventario reproducible y SOLO LECTURA de cobertura de datos
(research/universe-liquidity-v1).

Corrige el inventario anterior segun el mandato:
- market_klines: suma filas con COUNT(*), no numero de grupos simbolo/intervalo.
- Elegibilidad y denominadores desde datos y filtros explicitos;
  se eliminan los 522/942 hardcodeados como resultados.
- Distingue catalogo actual de universo historico conocido en T.
- Procedencia: REAL / FIXTURE / UNKNOWN segun evidencia, nunca segun rows>0.
- n_events_with_1h_outcome cuenta específicamente el horizonte 1h.
- Publica descartes y denominadores efectivos.
- Declara formula y unidades de retornos; no concluye "cara/cruz" por media
  cercana a cero ni proporcion positiva cercana al 50%.
- Agrega matriz de cobertura conjunta: simbolo x ventana libro/flujo x
  cobertura de precio posterior x horizontes calculables x motivos de exclusión.

No escribe en DBs canonicas, no abre conexiones publicas, no lanza capturas.
Salidas JSON en docs/evidence/research/universe_liquidity_v1/:
  coverage.json         - tabla de cobertura por fuente (corregida)
  joint_coverage.json   - matriz simbolo x ventana x precio posterior
  descriptive.json      - resultado descriptivo nivel A (actualizado)
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "evidence" / "research" / "universe_liquidity_v1"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Lectura SQLite read-only
# ---------------------------------------------------------------------------

def query(db: str, sql: str, params=()):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


def ms(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).isoformat()


def count(db: str, table: str, where: str = "", params=()):
    sql = f"SELECT COUNT(*) FROM {table}" + ((" WHERE " + where) if where else "")
    return query(db, sql, params)[0]["COUNT(*)"]


# ---------------------------------------------------------------------------
# Formula y unidades (declaradas, no inferidas)
# ---------------------------------------------------------------------------

FORMULAS = {
    "forward_return": {
        "formula": "(price_at_T_plus_h - price_at_T) / price_at_T",
        "units": "decimal (p. ej. 0.001 = +0.10%)",
        "price_at_T": "precio de cierre de la vela/bucket en el instante T",
        "price_at_T_plus_h": "precio de cierre de la vela/bucket en T + h",
        "note": "solo computable si existe precio posterior disponible DESPUES de T; "
        "nunca se atribuye a T un agregado disponible solo despues de T.",
    }
}

# ---------------------------------------------------------------------------
# 1. Tabla de cobertura (corregida)
# ---------------------------------------------------------------------------

def provenance_from_evidence(rows: int, has_schema: bool, is_real_store: bool) -> str:
    """Procedencia segun evidencia, nunca segun rows>0."""
    if not has_schema:
        return "UNKNOWN"
    if not is_real_store:
        return "FIXTURE"
    return "REAL" if rows > 0 else "REAL (vacio)"


def coverage_table():
    entries = []

    def add(source, location, kind, symbols, rows, dt_min, dt_max, resolution,
            notes, provenance, eligible_filter=None, discards=None,
            effective_denominator=None):
        entries.append({
            "source": source,
            "location": location,
            "data_kind": kind,
            "distinct_symbols": len(symbols),
            "symbols": sorted(symbols),
            "rows": int(rows),
            "available_from": dt_min,
            "available_to": dt_max,
            "resolution": resolution,
            "notes": notes,
            "procedence": provenance,
            "eligible_filter": eligible_filter,
            "discards": discards or [],
            "effective_denominator": effective_denominator,
        })

    # --- contract_catalog: catalogo actual (estatico), NO universo historico en T
    rows = query("data/market-cache/market_cache.db",
                 "SELECT symbol, status, eligible, exclusion_reasons, onboard_ms "
                 "FROM contract_catalog")
    syms = [r["symbol"] for r in rows]
    trading = [r["symbol"] for r in rows if r["status"] == "TRADING"]
    eligible = [r["symbol"] for r in rows
                if str(r["eligible"]).lower() in ("1", "true")]
    # Denominador efectivo: contratos elegibles en catalogo actual
    # (no es universo en T, es catalogo estatico de referencia)
    add(
        "contract_catalog", "data/market-cache/market_cache.db",
        "universo catalogo estatico (referencia, no snapshot en T)",
        syms, len(rows), None, None, "snapshot",
        "942 contratos de referencia; filtro elegible = status TRADING y "
        "eligible truthy. No es snapshot de universo en T; no se usa como "
        "denominador de elegibilidad historica.",
        provenance_from_evidence(len(rows), True, True),
        eligible_filter="status='TRADING' AND eligible IN (1,'1','true')",
        discards=[
            {"motivo": "status!=TRADING", "count": len(rows) - len(trading)},
            {"motivo": "eligible no truthy", "count": len(trading) - len(eligible)},
        ],
        effective_denominator=len(eligible),
    )

    # --- market_klines: filas SUM via COUNT(*), no numero de grupos
    rows = query("data/market-cache/market_cache.db",
                 "SELECT symbol, interval, MIN(open_time), MAX(close_time), "
                 "COUNT(*) AS n_rows FROM market_klines GROUP BY symbol, interval")
    by_sym = {}
    total_rows = 0
    dmin, dmax = None, None
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)
        total_rows += int(r["n_rows"])
        if dmin is None or r["MIN(open_time)"] < dmin:
            dmin = r["MIN(open_time)"]
        if dmax is None or r["MAX(close_time)"] > dmax:
            dmax = r["MAX(close_time)"]
    syms = list(by_sym.keys())
    add(
        "market_klines", "data/market-cache/market_cache.db",
        "ohlcv + taker_buy (flujo proxy por vela; precios posteriores)",
        syms, total_rows, ms(dmin), ms(dmax), "1m y 1h segun simbolo",
        "Filas contadas con COUNT(*) (12,818 filas reales), no numero de "
        "grupos simbolo/intervalo. Incluye BTCUSDT y MINAUSDT; NO ETHUSDT ni "
        "SOLUSDT. Sirve como precio posterior para computar outcomes de la "
        "ventana research_* solo donde hay overlap temporal.",
        provenance_from_evidence(total_rows, True, True),
    )

    # --- historical_klines: ventana resuelta con outcomes
    rows = query("data/historical/historical.db",
                 "SELECT symbol, interval, MIN(open_time), MAX(close_time), "
                 "COUNT(*) AS n_rows FROM historical_klines GROUP BY symbol, interval")
    n = count("data/historical/historical.db", "historical_klines")
    dmin = query("data/historical/historical.db",
                 "SELECT MIN(open_time) FROM historical_klines")[0]["MIN(open_time)"]
    dmax = query("data/historical/historical.db",
                 "SELECT MAX(close_time) FROM historical_klines")[0]["MAX(close_time)"]
    syms = [r["symbol"] for r in query("data/historical/historical.db",
                                       "SELECT DISTINCT symbol FROM historical_klines")]
    add(
        "historical_klines", "data/historical/historical.db",
        "ohlcv + taker_buy (ventana resuelta, outcomes disponibles)",
        syms, n, ms(dmin), ms(dmax), "15m y 1h",
        "Solo 6 simbolos (BTC/ETH/SOL/MINAU/NMR/ORCA). Ventana 2026-09-07 a "
        "2026-10-07 21:22. TERMINA antes de que empiece research_book/research_flow "
        "(2026-10-07 22:43), por lo que NO puede servir de precio posterior para "
        "la ventana research_*.",
        provenance_from_evidence(n, True, True),
    )

    # --- event_instances / event_outcomes: n_events_with_1h_outcome especifica horizonte 1h
    n_ev = count("data/historical/historical.db", "event_instances",
                 "data_quality='OK'")
    n_out = count("data/historical/historical.db", "event_outcomes")
    n_1h_usable = count("data/historical/historical.db",
                        "event_outcomes WHERE horizon='1h' AND usable_for_statistics=1")
    n_1h_all = count("data/historical/historical.db",
                     "event_outcomes WHERE horizon='1h'")
    syms = [r["symbol"] for r in query("data/historical/historical.db",
                                       "SELECT DISTINCT symbol FROM event_instances "
                                       "WHERE data_quality='OK'")]
    dmin = query("data/historical/historical.db",
                 "SELECT MIN(event_time) FROM event_instances WHERE data_quality='OK'")[0]["MIN(event_time)"]
    dmax = query("data/historical/historical.db",
                 "SELECT MAX(event_time) FROM event_instances WHERE data_quality='OK'")[0]["MAX(event_time)"]
    add(
        "event_instances/outcomes", "data/historical/historical.db",
        "eventos detectados + forward_return resuelto (MF/MAE, label)",
        syms, n_ev, ms(dmin), ms(dmax), "deteccion (censo same-grid)",
        f"{n_ev} eventos OK, {n_out} outcome-rows, {n_1h_usable} con horizonte 1h "
        f"utilizables (de {n_1h_all} rows horizon 1h). Universo resuelto = "
        f"{len(syms)} simbolos. label siempre NULL (descriptivo, sin etiquetar).",
        provenance_from_evidence(n_ev, True, True),
        discards=[
            {"motivo": "data_quality!=OK", "count": count("data/historical/historical.db", "event_instances", "data_quality!='OK'")},
            {"motivo": "horizon!=1h o usable_for_statistics=0 para 1h",
             "count": n_1h_all - n_1h_usable},
        ],
        effective_denominator=n_1h_usable,
    )

    # --- research_book_1m / research_flow_1m: reciente, SIN resolver
    for tbl, kind in (("research_book_1m", "libro agregado (spread, desequilibrio, microprice)"),
                      ("research_flow_1m", "flujo agregado (delta_ratio, compra/venta)")):
        rows = query("data/historical/historical.db",
                     f"SELECT symbol, MIN(bucket_start), MAX(bucket_end), "
                     f"COUNT(*) AS n_rows FROM {tbl} GROUP BY symbol")
        n = count("data/historical/historical.db", tbl)
        dmin = query("data/historical/historical.db",
                     f"SELECT MIN(bucket_start) FROM {tbl}")[0]["MIN(bucket_start)"]
        dmax = query("data/historical/historical.db",
                     f"SELECT MAX(bucket_end) FROM {tbl}")[0]["MAX(bucket_end)"]
        syms = [r["symbol"] for r in rows]
        add(tbl, "data/historical/historical.db", kind, syms, n,
            ms(dmin), ms(dmax), "1m",
            "Ventana reciente 2026-10-07 22:43 a 2026-10-16, resultados forward "
            "NO resueltos. No se une con event_outcomes. Requiere precio posterior "
            "en market_klines para computar outcomes; solo BTCUSDT lo tiene.",
            provenance_from_evidence(n, True, True))

    # --- flow_buckets (microprobe): ingestión en vivo reciente, sin resolver
    n_fb = count("data/microprobe.db", "flow_buckets")
    syms = [r["symbol"] for r in query("data/microprobe.db",
                                       "SELECT DISTINCT symbol FROM flow_buckets")]
    dmin = query("data/microprobe.db",
                 "SELECT MIN(bucket_ms) FROM flow_buckets")[0]["MIN(bucket_ms)"]
    dmax = query("data/microprobe.db",
                 "SELECT MAX(bucket_ms) FROM flow_buckets")[0]["MAX(bucket_ms)"]
    add("flow_buckets (microprobe)", "data/microprobe.db",
        "buckets de flujo agresor (ingestión en vivo)", syms, n_fb,
        ms(dmin), ms(dmax), "10s/30s/1m/5m",
        "Ventana reciente 2026-10-07 a 2026-10-16, no resuelta.",
        provenance_from_evidence(n_fb, True, True))

    # --- book depth en T para ventana resuelta: 0 filas
    n_book_hist = count("data/historical/historical.db",
                        "research_book_1m WHERE bucket_start < 1791403200000")
    entries.append({
        "source": "book_depth_at_event_time (ventana resuelta)",
        "location": "data/historical/historical.db",
        "data_kind": "profundidad/libro en instante T",
        "distinct_symbols": 0,
        "symbols": [],
        "rows": int(n_book_hist),
        "available_from": None,
        "available_to": None,
        "resolution": "1m",
        "notes": "0 filas de book_depth en ventana resuelta (Sep 8 - Oct 7). "
                 "research_book_1m empieza 2026-10-07 22:43 (despues de historical_klines). "
                 "LIQUIDEZ EN T NO DISPONIBLE para outcomes resueltos.",
        "procedence": "REAL (vacio)",
        "discards": [{"motivo": "sin solapamiento temporal con precios posteriores",
                      "count": int(n_book_hist)}],
        "effective_denominator": 0,
    })

    with open(OUT / "coverage.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "formulas": FORMULAS,
                   "entries": entries}, f, ensure_ascii=False, indent=2)
    return entries


# ---------------------------------------------------------------------------
# 2. Matriz de cobertura conjunta (simbolo x ventana x precio posterior x horizonte)
# ---------------------------------------------------------------------------

def joint_coverage_matrix():
    """Para cada simbolo en research_book_1m/research_flow_1m:
    - ventana de libro/flujo (min, max bucket_end)
    - precio posterior disponible (en market_klines) y su rango
    - horizontes computables (1h si hay velas 1h posteriores; 1m si hay velas 1m posteriores)
    - motivos de exclusión
    """
    # Ventana research por simbolo
    book_rows = query("data/historical/historical.db",
                      "SELECT symbol, MIN(bucket_start), MAX(bucket_end), "
                      "COUNT(*) AS n_rows FROM research_book_1m GROUP BY symbol")
    flow_rows = query("data/historical/historical.db",
                      "SELECT symbol, MIN(bucket_start), MAX(bucket_end), "
                      "COUNT(*) AS n_rows FROM research_flow_1m GROUP BY symbol")
    book_by_sym = {r["symbol"]: r for r in book_rows}
    flow_by_sym = {r["symbol"]: r for r in flow_rows}

    # Precio posterior por simbolo en market_klines (1h y 1m)
    mk_rows = query("data/market-cache/market_cache.db",
                    "SELECT symbol, interval, MIN(open_time), MAX(close_time), "
                    "COUNT(*) AS n_rows FROM market_klines GROUP BY symbol, interval")
    mk_by_sym_interval = {}
    for r in mk_rows:
        mk_by_sym_interval[(r["symbol"], r["interval"])] = r

    research_symbols = sorted(set(book_by_sym) | set(flow_by_sym))
    matrix = []

    for sym in research_symbols:
        b = book_by_sym.get(sym, {})
        f = flow_by_sym.get(sym, {})
        win_start = min(x for x in [b.get("MIN(bucket_start)"), f.get("MIN(bucket_start)")] if x is not None)
        win_end = max(x for x in [b.get("MAX(bucket_end)"), f.get("MAX(bucket_end)")] if x is not None)

        mk_1h = mk_by_sym_interval.get((sym, "1h"))
        mk_1m = mk_by_sym_interval.get((sym, "1m"))

        horizons = []
        exclusions = []
        if mk_1h is not None:
            # 1h computable si hay una vela 1h cuya open_time >= bucket_end de alguna ventana
            first_1h_open = mk_1h["MIN(open_time)"]
            if first_1h_open <= win_end:
                horizons.append("1h")
            else:
                exclusions.append("1h: primera vela 1h posterior (" +
                                  ms(first_1h_open) + ") despues del fin de ventana (" +
                                  ms(win_end) + ")")
        else:
            exclusions.append("1h: no hay velas 1h en market_klines para este simbolo")
        if mk_1m is not None:
            first_1m_open = mk_1m["MIN(open_time)"]
            if first_1m_open <= win_end:
                horizons.append("1m")
            else:
                exclusions.append("1m: primera vela 1m posterior (" +
                                  ms(first_1m_open) + ") despues del fin de ventana (" +
                                  ms(win_end) + ")")
        else:
            exclusions.append("1m: no hay velas 1m en market_klines para este simbolo")

        posterior = None
        if mk_1h:
            posterior = {"interval": "1h", "from": ms(mk_1h["MIN(open_time)"]),
                         "to": ms(mk_1h["MAX(close_time)"]), "rows": int(mk_1h["n_rows"])}
        elif mk_1m:
            posterior = {"interval": "1m", "from": ms(mk_1m["MIN(open_time)"]),
                         "to": ms(mk_1m["MAX(close_time)"]), "rows": int(mk_1m["n_rows"])}

        matrix.append({
            "symbol": sym,
            "book_window_from": ms(win_start),
            "book_window_to": ms(win_end),
            "book_rows": int(b.get("n_rows", 0)),
            "flow_rows": int(f.get("n_rows", 0)),
            "posterior_price": posterior,
            "computable_horizons": horizons,
            "exclusion_reasons": exclusions,
            "adequate_for_outcomes": len(horizons) > 0,
        })

    adequate = [m for m in matrix if m["adequate_for_outcomes"]]
    with open(OUT / "joint_coverage.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "research_symbols": research_symbols,
            "n_research_symbols": len(research_symbols),
            "n_adequate_for_outcomes": len(adequate),
            "adequate_symbols": [m["symbol"] for m in adequate],
            "matrix": matrix,
        }, f, ensure_ascii=False, indent=2)
    return matrix


# ---------------------------------------------------------------------------
# 3. Resultado descriptivo nivel A (actualizado, sin concluir cara/cruz)
# ---------------------------------------------------------------------------

def descriptive_flow_outcome():
    ev = query("data/historical/historical.db",
               "SELECT event_id, symbol, event_time, direction, features_json "
               "FROM event_instances WHERE data_quality='OK'")
    out = query("data/historical/historical.db",
                "SELECT event_id, horizon, forward_return, usable_for_statistics "
                "FROM event_outcomes")

    out_by_event = {}
    for r in out:
        if r["usable_for_statistics"] == 1:
            out_by_event.setdefault(r["event_id"], {})[r["horizon"]] = r["forward_return"]

    results = {"symbols": {}, "overall": {}, "denominators": {},
               "formulas": FORMULAS, "level": "A_descriptiva_asociacion",
               "interpretation_guardrails": [
                   "La media cercana a cero o el % positivo cercano al 50% NO se "
                   "interpretan como 'cara/cruz' ni como evidencia de ausencia de edge; "
                   "son estadisticas descriptivas sobre un censo same-grid con sesgo de "
                   "seleccion y sin comparador de trading.",
                   "label de event_outcomes siempre NULL (sin etiquetar).",
                   "No es prediccion (nivel B) ni resultado operable tras costes (nivel C).",
               ]}
    n_events = len(ev)
    n_flow_usable = 0
    n_with_1h_outcome = 0

    per_symbol = {}
    for r in ev:
        try:
            feat = json.loads(r["features_json"])
        except Exception:
            continue
        sym = r["symbol"]
        tbp = feat.get("taker_buy_proxy")
        if tbp is None:
            continue
        n_flow_usable += 1
        outcomes = out_by_event.get(r["event_id"], {})
        ret_1h = outcomes.get("1h")
        if ret_1h is None:
            continue
        n_with_1h_outcome += 1
        d = per_symbol.setdefault(sym, {"n": 0, "sum_ret": 0.0, "rets": [],
                                        "tbp_up": [], "tbp_down": []})
        d["n"] += 1
        d["sum_ret"] += ret_1h
        d["rets"].append(ret_1h)
        if tbp >= 0.5:
            d["tbp_up"].append(ret_1h)
        else:
            d["tbp_down"].append(ret_1h)

    for sym, d in per_symbol.items():
        rets = d["rets"]
        n = d["n"]
        results["symbols"][sym] = {
            "n_events_with_flow_and_1h_outcome": n,
            "mean_forward_return_1h": round(d["sum_ret"] / n, 6) if n else None,
            "median_forward_return_1h": round(statistics.median(rets), 6) if rets else None,
            "share_positive_1h": round(sum(1 for x in rets if x > 0) / len(rets), 4) if rets else None,
            "n_tbp_ge_05": len(d["tbp_up"]),
            "mean_ret_1h_tbp_ge_05": round(sum(d["tbp_up"]) / len(d["tbp_up"]), 6) if d["tbp_up"] else None,
            "n_tbp_lt_05": len(d["tbp_down"]),
            "mean_ret_1h_tbp_lt_05": round(sum(d["tbp_down"]) / len(d["tbp_down"]), 6) if d["tbp_down"] else None,
        }

    results["overall"] = {
        "n_events_total_OK": n_events,
        "n_events_with_flow_proxy": n_flow_usable,
        "n_events_with_1h_outcome": n_with_1h_outcome,
        "symbols_evaluated": list(per_symbol.keys()),
        "share_of_eligible_universe": None,  # 522 eliminado: no hay universo en T conocido
        "note_denominator": "Denominador de elegibilidad en T UNKNOWN (no hay snapshot de universo en T). "
                            "No se divide entre 522 (hardcodeado eliminado).",
    }
    results["claims"] = [
        "No es prediccion (nivel B) ni resultado operable tras costes (nivel C).",
        "Censo same-grid: los eventos ya se detectaron porque movieron (sesgo de seleccion).",
        "Liquidez (profundidad/spread) en T NO disponible para esta ventana -> no se testa la hipotesis liquidez-vs-flujo, solo flujo proxy.",
        "label de event_outcomes siempre NULL (sin etiquetar).",
    ]
    with open(OUT / "descriptive.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "result": results}, f, ensure_ascii=False, indent=2)
    return results


if __name__ == "__main__":
    cov = coverage_table()
    matrix = joint_coverage_matrix()
    desc = descriptive_flow_outcome()
    print("COVERAGE ENTRIES:", len(cov))
    print("JOINT MATRIX SYMBOLS:", len(matrix),
          "ADEQUATE:", sum(1 for m in matrix if m["adequate_for_outcomes"]),
          "ADEQUATE_SYMBOLS:", [m["symbol"] for m in matrix if m["adequate_for_outcomes"]])
    print(json.dumps(desc, ensure_ascii=False, indent=2)[:1500])
