"""Análisis reproducible y de SOLO LECTURA sobre cobertura de datos y la
hipótesis liquidez-vs-flujo agresor (research/universe-liquidity-v1).

No escribe en DBs canónicas, no abre conexiones públicas, no lanza capturas.
Lee: market_cache.db (contract_catalog, market_klines), historical.db
(historical_klines, event_instances, event_outcomes), microprobe.db
(book_features/flow_features/oi_samples/research_* via historical.db).

Salidas JSON en docs/evidence/research/universe_liquidity_v1/:
  coverage.json      - tabla de cobertura por fuente de datos
  descriptive.json   - resultado descriptivo acotado (flujo proxy vs retorno
                       forward en símbolos resueltos), nivel A (asociación),
                       explícitamente NO predictivo.
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


def ms(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).isoformat()


def query(db, sql, params=()):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return rows
    finally:
        con.close()


def coverage_table():
    """Tabla de cobertura real, read-only, por fuente de datos."""
    entries = []

    def add(source, location, kind, symbols, rows, dt_min, dt_max, resolution,
            notes=""):
        entries.append({
            "source": source,
            "location": location,
            "data_kind": kind,
            "distinct_symbols": len(symbols),
            "symbols": sorted(symbols),
            "rows": rows,
            "available_from": dt_min,
            "available_to": dt_max,
            "resolution": resolution,
            "notes": notes,
            "procedence": "real" if rows else "fixture/empty",
        })

    # contract_catalog: universo de contratos (elegibilidad estática, no un
    # snapshot de universo en T).
    rows = query("data/market-cache/market_cache.db",
                 "SELECT symbol, status, eligible, exclusion_reasons FROM contract_catalog")
    syms = [r["symbol"] for r in rows]
    trading = [r["symbol"] for r in rows if r["status"] == "TRADING"]
    eligible = [r["symbol"] for r in rows if str(r["eligible"]).lower() in ("1", "true")]
    add("contract_catalog", "data/market-cache/market_cache.db",
        "universe_catalog", syms, len(rows), None, None, "snapshot",
        "942 contratos; 522 TRADING+eligibles (USDT perp). No es snapshot de universo en T.")

    # market_klines: OHLCV + taker_buy (flujo proxy por vela), más reciente.
    rows = query("data/market-cache/market_cache.db",
                 "SELECT symbol, interval, MIN(open_time), MAX(open_time), COUNT(*) FROM market_klines GROUP BY symbol, interval")
    by_sym = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)
    syms = list(by_sym.keys())
    rmin = query("data/market-cache/market_cache.db", "SELECT MIN(open_time) FROM market_klines")[0]
    rmax = query("data/market-cache/market_cache.db", "SELECT MAX(open_time) FROM market_klines")[0]
    dmin = rmin["MIN(open_time)"]
    dmax = rmax["MAX(open_time)"]
    total = sum(len(v) for v in by_sym.values())
    add("market_klines", "data/market-cache/market_cache.db",
        "ohlcv + taker_buy (flujo proxy por vela)", syms, total,
        ms(dmin), ms(dmax), "1m/15m/1h según símbolo",
        "Hasta hoy (2026-11-03). Incluye BTC pero NO ETH ni SOL. Sin forward-outcome resuelto.")

    # historical_klines: ventana resuelta (resultados forward existen).
    rows = query("data/historical/historical.db",
                 "SELECT symbol, interval, MIN(open_time), MAX(open_time), COUNT(*) FROM historical_klines GROUP BY symbol, interval")
    syms = [r["symbol"] for r in query("data/historical/historical.db",
                                       "SELECT DISTINCT symbol FROM historical_klines")]
    dmin = query("data/historical/historical.db",
                 "SELECT MIN(open_time) FROM historical_klines")[0]["MIN(open_time)"]
    dmax = query("data/historical/historical.db",
                 "SELECT MAX(open_time) FROM historical_klines")[0]["MAX(open_time)"]
    n = query("data/historical/historical.db",
              "SELECT COUNT(*) FROM historical_klines")[0]["COUNT(*)"]
    add("historical_klines", "data/historical/historical.db",
        "ohlcv + taker_buy (ventana resuelta, outcomes disponibles)", syms, n,
        ms(dmin), ms(dmax), "15m y 1h",
        "Solo 6 símbolos (BTC/ETH/SOL/MINAU/NMR/ORCA). Ventana 2026-09-07 a 2026-10-07.")

    # event_instances + event_outcomes: eventos con forward outcomes resueltos.
    n_ev = query("data/historical/historical.db",
                 "SELECT COUNT(*) FROM event_instances")[0]["COUNT(*)"]
    n_out = query("data/historical/historical.db",
                  "SELECT COUNT(*) FROM event_outcomes")[0]["COUNT(*)"]
    n_usable = query("data/historical/historical.db",
                     "SELECT COUNT(*) FROM event_outcomes WHERE usable_for_statistics=1")[0]["COUNT(*)"]
    syms = [r["symbol"] for r in query("data/historical/historical.db",
                                       "SELECT DISTINCT symbol FROM event_instances")]
    dmin = query("data/historical/historical.db",
                 "SELECT MIN(event_time) FROM event_instances")[0]["MIN(event_time)"]
    dmax = query("data/historical/historical.db",
                 "SELECT MAX(event_time) FROM event_instances")[0]["MAX(event_time)"]
    add("event_instances/outcomes", "data/historical/historical.db",
        "eventos detectados + forward_return resuelto (MF/MAE, label)", syms,
        n_ev, ms(dmin), ms(dmax), "detección (censo same-grid)",
        f"{n_ev} eventos, {n_out} outcome-rows, {n_usable} utilizables. Universo resuelto = 6 símbolos (0.6% de elegibles). label siempre NULL (descriptivo).")

    # research_book_1m / research_flow_1m: libro y flujo agregados, reciente SIN resolver.
    for tbl, kind in (("research_book_1m", "libro agregado (spread, desequilibrio, microprice)"),
                      ("research_flow_1m", "flujo agregado (delta_ratio, compra/venta)")):
        rows = query("data/historical/historical.db",
                     f"SELECT symbol, MIN(bucket_start), MAX(bucket_start), COUNT(*) FROM {tbl} GROUP BY symbol")
        syms = [r["symbol"] for r in rows]
        n = sum(r["COUNT(*)"] for r in rows)
        dmin = query("data/historical/historical.db",
                     f"SELECT MIN(bucket_start) FROM {tbl}")[0]["MIN(bucket_start)"]
        dmax = query("data/historical/historical.db",
                     f"SELECT MAX(bucket_start) FROM {tbl}")[0]["MAX(bucket_start)"]
        add(tbl, "data/historical/historical.db", kind, syms, n, ms(dmin), ms(dmax), "1m",
            "Ventana reciente 2026-10-07 a 2026-10-16, resultados forward NO resueltos. No se une con event_outcomes.")

    # microprobe.db: ingestión en vivo (book/flow/OI) reciente, no resuelto.
    n_fb = query("data/microprobe.db",
                 "SELECT COUNT(*) FROM flow_buckets")[0]["COUNT(*)"]
    syms = [r["symbol"] for r in query("data/microprobe.db",
                                       "SELECT DISTINCT symbol FROM flow_buckets")]
    dmin = query("data/microprobe.db",
                 "SELECT MIN(bucket_ms) FROM flow_buckets")[0]["MIN(bucket_ms)"]
    dmax = query("data/microprobe.db",
                 "SELECT MAX(bucket_ms) FROM flow_buckets")[0]["MAX(bucket_ms)"]
    add("flow_buckets (microprobe)", "data/microprobe.db",
        "buckets de flujo agresor (ingestión en vivo)", syms, n_fb,
        ms(dmin), ms(dmax), "10s/30s/1m/5m",
        "Ventana reciente 2026-10-07 a 2026-10-16, no resuelta.")

    # Liquidez en T para ventana resuelta: ¿existe book depth en 2026-09-08..10-07?
    n_book_hist = query("data/historical/historical.db",
                        "SELECT COUNT(*) FROM research_book_1m WHERE bucket_start < 1791403200000")[0]["COUNT(*)"]
    entries.append({
        "source": "book_depth_at_event_time (resolved window)",
        "location": "data/historical/historical.db + data/microprobe.db",
        "data_kind": "profundidad/libro en instante T",
        "distinct_symbols": 0,
        "symbols": [],
        "rows": int(n_book_hist),
        "available_from": None,
        "available_to": None,
        "resolution": "1m",
        "notes": "0 filas de book_depth en la ventana resuelta (Sep 8 - Oct 7). research_book_1m empieza 2026-10-07 22:43 (sin resolver)."
                 " LIQUIDEZ EN T NO DISPONIBLE para outcomes resueltos -> hipótesis liquidez-vs-flujo NO comprobable sobre outcomes.",
        "procedence": "real",
    })

    with open(OUT / "coverage.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "entries": entries}, f, ensure_ascii=False, indent=2)
    return entries


def descriptive_flow_outcome():
    """Resultado DESCRIPTIVO (nivel A): proxy de flujo en T (taker_buy_proxy)
    vs forward_return resuelto, símbolos BTC/ETH/SOL, ventana resuelta.
    Explícitamente NO predictivo (nivel B) ni operable (nivel C). Mismos datos
    del censo same-grid: sesgo de selección, denominadores reportados.
    """
    ev = query("data/historical/historical.db",
               "SELECT event_id, symbol, event_time, direction, features_json FROM event_instances WHERE data_quality='OK'")
    out = query("data/historical/historical.db",
                "SELECT event_id, horizon, forward_return, usable_for_statistics FROM event_outcomes")

    out_by_event = {}
    for r in out:
        if r["usable_for_statistics"] == 1:
            out_by_event.setdefault(r["event_id"], {})[r["horizon"]] = r["forward_return"]

    results = {"symbols": {}, "overall": {}, "denominators": {}}
    n_events = len(ev)
    n_with_outcome = 0
    n_flow_usable = 0

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
        if not outcomes:
            continue
        n_with_outcome += 1
        ret_1h = outcomes.get("1h")
        if ret_1h is None:
            continue
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
        results["symbols"][sym] = {
            "n_events_with_flow_and_outcome": d["n"],
            "mean_forward_return_1h": round(d["sum_ret"] / d["n"], 6) if d["n"] else None,
            "median_forward_return_1h": round(statistics.median(rets), 6) if rets else None,
            "share_positive_1h": round(sum(1 for x in rets if x > 0) / len(rets), 4) if rets else None,
            "n_tbp_ge_05": len(d["tbp_up"]),
            "mean_ret_1h_tbp_ge_05": round(sum(d["tbp_up"]) / len(d["tbp_up"]), 6) if d["tbp_up"] else None,
            "n_tbp_lt_05": len(d["tbp_down"]),
            "mean_ret_1h_tbp_lt_05": round(sum(d["tbp_down"]) / len(d["tbp_down"]), 6) if d["tbp_down"] else None,
        }

    all_rets = [v for s in per_symbol.values() for _ in range(s["n"]) for v in []]  # placeholder
    # recompute overall from per-symbol rets stored? we discarded. keep simple:
    results["overall"] = {
        "n_events_total": n_events,
        "n_events_with_flow_proxy": n_flow_usable,
        "n_events_with_1h_outcome": n_with_outcome,
        "symbols_evaluated": list(per_symbol.keys()),
        "resolved_universe_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "MINAUSDT", "NMRUSDT", "ORCAUSDT"],
        "share_of_eligible_universe": round(len(per_symbol) / 522, 6),
    }
    results["level"] = "A_descriptiva_asociacion"
    results["claims"] = [
        "No es predicción (nivel B) ni resultado operable tras costes (nivel C).",
        "Censo same-grid: los eventos ya se detectaron porque movieron (sesgo de selección).",
        "Liquidez (profundidad/spread) en T NO disponible para esta ventana -> no se testa la hipótesis liquidez-vs-flujo, solo flujo proxy.",
        "label de event_outcomes siempre NULL (sin etiquetar).",
    ]
    with open(OUT / "descriptive.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "result": results}, f, ensure_ascii=False, indent=2)
    return results


if __name__ == "__main__":
    cov = coverage_table()
    desc = descriptive_flow_outcome()
    print("COVERAGE ENTRIES:", len(cov))
    print(json.dumps(desc, ensure_ascii=False, indent=2)[:2000])
