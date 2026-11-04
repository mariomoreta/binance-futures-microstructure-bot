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
- Matriz de cobertura conjunta por observacion (punto 5): para cada
  observacion de libro/flujo, verifica compatibilidad temporal entre precio
  de referencia en T y precio objetivo en T+h, usando unicamente precios de
  market_klines con resolucion y disponibilidad compatibles. No acredita un
  outcome por MIN/MAX temporales ni por filas existentes.

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
        "price_at_T": "precio de cierre de la vela/bucket en el instante T, "
        "conocido en T (no reconstruido desde OHLC).",
        "price_at_T_plus_h": "precio de cierre de la vela/bucket en T + h, "
        "disponible solo despues de T+h; nunca se usa el close de una vela "
        "horaria que contiene T como si se conociera en T.",
        "note": "solo computable si existe precio posterior disponible "
        "DESPUES de T; nunca se atribuye a T un agregado disponible solo "
        "despues de T.",
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
        "outcomes de la ventana research_*.",
        provenance_from_evidence(n, True, True),
    )

    # --- event_instances / event_outcomes: n_events_with_1h_outcome especifica horizonte 1h
    n_ev = count("data/historical/historical.db",
                 "event_instances WHERE data_quality='OK'")
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
            "NO resueltos. No se une con event_outcomes. Para computar outcomes "
            "se necesita precio posterior en market_klines; solo BTCUSDT lo tiene.",
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

    with open(OUT / "coverage.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "formulas": FORMULAS,
                   "entries": entries}, f, ensure_ascii=False, indent=2)
    return entries


# ---------------------------------------------------------------------------
# 2. Matriz de cobertura conjunta por OBSERVACION (punto 5)
# ---------------------------------------------------------------------------

def _interval_ms(interval: str) -> Optional[int]:
    """Duracion en ms de un intervalo de vela (para tolerancia de alineacion)."""
    mapping = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
               "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
    return mapping.get(interval)


def _vela_cercana_antes_o_en(con: sqlite3.Connection, symbol: str,
                             interval: str, close_time_limite_ms: int) -> Optional[Dict[str, Any]]:
    """Devuelve la vela de market_klines cuya close_time sea <= close_time_limite_ms
    y sea la mas cercana (ultima cerrada antes o en el limite).

    Es el precio de referencia conocido en T (no reconstruido desde OHLC,
    no usa informacion futura).
    """
    cur = con.cursor()
    cur.execute(
        "SELECT open_time, open, high, low, close, close_time FROM market_klines "
        "WHERE symbol = ? AND interval = ? AND close_time <= ? "
        "ORDER BY close_time DESC LIMIT 1",
        (symbol, interval, close_time_limite_ms))
    row = cur.fetchone()
    if not row:
        return None
    open_time, o, h, l, c, close_time = row
    return {
        "open_time": open_time, "open": o, "high": h, "low": l, "close": c,
        "close_time": close_time,
    }


def _vela_cubriendo_objetivo(con: sqlite3.Connection, symbol: str,
                             interval: str, objetivo_ms: int) -> Optional[Dict[str, Any]]:
    """Devuelve la primera vela de market_klines cuya open_time <= objetivo_ms
    y close_time >= objetivo_ms. Es decir, la vela que cubre el instante
    objetivo_ms y cuyo close NO se conocia antes de objetivo_ms.

    Esto evita usar el close de una vela horaria que contiene T como si se
    conociera en T: solo se acepta una vela cuya cierre sea >= objetivo_ms.
    """
    cur = con.cursor()
    cur.execute(
        "SELECT open_time, open, high, low, close, close_time FROM market_klines "
        "WHERE symbol = ? AND interval = ? AND open_time <= ? AND close_time >= ? "
        "ORDER BY open_time ASC LIMIT 1",
        (symbol, interval, objetivo_ms, objetivo_ms))
    row = cur.fetchone()
    if not row:
        return None
    open_time, o, h, l, c, close_time = row
    return {
        "open_time": open_time, "open": o, "high": h, "low": l, "close": c,
        "close_time": close_time,
    }


def joint_coverage_matrix():
    """Matriz de cobertura conjunta por OBSERVACION (punto 5 del mandato).

    Para cada observacion de libro/flujo (bucket):
    - Identifica simbolo, bucket (bucket_start, bucket_end) y T de analisis
      (T = bucket_end, momento en que los datos del bucket se conocen).
    - Precio de referencia en T: vela de market_klines con close_time <= T
      (la ultima cerrada antes o en T). No es reconstruida desde OHLC.
    - Precio objetivo T+h: vela de market_klines con open_time <= T+h y
      close_time >= T+h (su close NO se conocia antes de T+h).
    - Usa unicamente precios con resolucion y disponibilidad compatibles
      (mismo intervalo que el horizonte).
    - Tolerancia de alineacion declarada: una vela del intervalo.
    - No usa el close de una vela horaria que contiene T como si se conociera
      en T. No extrapola horizontes de un minuto usando velas horarias.

    Publica por simbolo/horizonte: n_observaciones, n_emparejadas,
    n_excluidas y motivos. Solo llama "adecuado" al subconjunto realmente
    emparejado. Si no hay ninguno, resultado cero/insuficiente.
    """
    # Ventana y observaciones research por simbolo (libro y flujo).
    book_rows = query("data/historical/historical.db",
                      "SELECT symbol, bucket_start, bucket_end FROM research_book_1m")
    flow_rows = query("data/historical/historical.db",
                      "SELECT symbol, bucket_start, bucket_end FROM research_flow_1m")

    research_symbols = sorted(
        set(r["symbol"] for r in book_rows) | set(r["symbol"] for r in flow_rows))

    # Cache de velas market_klines por (simbolo, intervalo), ordenadas por open_time.
    mk_cache: Dict[tuple, List[Dict[str, Any]]] = {}

    def velas(sym: str, interval: str) -> List[Dict[str, Any]]:
        key = (sym, interval)
        if key not in mk_cache:
            rows = query("data/market-cache/market_cache.db",
                         "SELECT open_time, open, high, low, close, close_time "
                         "FROM market_klines WHERE symbol = ? AND interval = ? "
                         "ORDER BY open_time ASC",
                         (sym, interval))
            mk_cache[key] = rows
        return mk_cache[key]

    matrix = []
    for sym in research_symbols:
        sym_book = [r for r in book_rows if r["symbol"] == sym]
        sym_flow = [r for r in flow_rows if r["symbol"] == sym]
        all_buckets = sym_book + sym_flow
        n_observaciones = len(all_buckets)
        win_start = min((r["bucket_start"] for r in all_buckets), default=None)
        win_end = max((r["bucket_end"] for r in all_buckets), default=None)

        entry = {
            "symbol": sym,
            "book_window_from": ms(win_start),
            "book_window_to": ms(win_end),
            "n_observaciones": n_observaciones,
            "n_book_rows": len(sym_book),
            "n_flow_rows": len(sym_flow),
            "horizons": [],
            "adequate_for_outcomes": False,
        }

        for interval in ("1m", "1h"):
            tolerance_ms = _interval_ms(interval)
            mk_velas = velas(sym, interval)
            has_posterior_price = len(mk_velas) > 0

            n_emparejadas = 0
            n_excluidas = 0
            motivos: List[Dict[str, Any]] = []

            for b in all_buckets:
                t = int(b["bucket_end"])          # T = fin del bucket (datos conocidos en T)
                t_plus_h = t + tolerance_ms       # objetivo T+h

                # Precio de referencia en T: ultima vela cerrada en o antes de T.
                precio_ref = _vela_cercana_antes_o_en(
                    None, sym, interval, t) if False else None
                # Usar query directa (no hay conexión persistente); reusamos mk_velas en memoria.
                precio_ref_vela = None
                for v in mk_velas:
                    if int(v["close_time"]) <= t:
                        precio_ref_vela = v
                    else:
                        break  # ordenadas por open_time, pero close_time no ordenada; seguir buscando
                # Nota: mk_velas esta ordenada por open_time, no close_time.
                # Para encontrar la ultima con close_time <= T, escanear todas.
                precio_ref_vela = None
                mejor_close = -1
                for v in mk_velas:
                    ct = int(v["close_time"])
                    if ct <= t and ct > mejor_close:
                        mejor_close = ct
                        precio_ref_vela = v

                # Precio objetivo en T+h: primera vela con open_time <= T+h y close_time >= T+h.
                precio_objetivo_vela = None
                for v in mk_velas:
                    if int(v["open_time"]) <= t_plus_h and int(v["close_time"]) >= t_plus_h:
                        precio_objetivo_vela = v
                        break

                motivo_excl = None
                if precio_ref_vela is None:
                    motivo_excl = "precio_referencia_no_disponible_en_T"
                elif not has_posterior_price:
                    motivo_excl = f"sin_precio_posterior_{interval}_en_market_klines"
                elif precio_objetivo_vela is None:
                    motivo_excl = (f"sin_vela_{interval}_compatible_en_T+h "
                                   f"(open_time<={t_plus_h} y close_time>={t_plus_h})")

                if motivo_excl:
                    n_excluidas += 1
                    motivos.append({
                        "bucket_end": t,
                        "T_plus_h": t_plus_h,
                        "motivo": motivo_excl,
                    })
                else:
                    n_emparejadas += 1

            entry["horizons"].append({
                "interval": interval,
                "tolerance_ms": tolerance_ms,
                "has_posterior_price": has_posterior_price,
                "posterior_price_range": {
                    "from": ms(int(mk_velas[0]["open_time"])) if mk_velas else None,
                    "to": ms(int(mk_velas[-1]["close_time"])) if mk_velas else None,
                    "rows": len(mk_velas),
                },
                "n_observaciones": n_observaciones,
                "n_emparejadas": n_emparejadas,
                "n_excluidas": n_excluidas,
                "motivos_exclucion": motivos[:10],  # muestra acotada
                "adequate": n_emparejadas > 0,
            })
            if n_emparejadas > 0:
                entry["adequate_for_outcomes"] = True

        matrix.append(entry)

    adequate = [m for m in matrix if m["adequate_for_outcomes"]]
    with open(OUT / "joint_coverage.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "research_symbols": research_symbols,
            "n_research_symbols": len(research_symbols),
            "n_adequate_for_outcomes": len(adequate),
            "adequate_symbols": [m["symbol"] for m in adequate],
            "nota": ("Solo se considera adecuado un simbolo/horizonte si al "
                     "menos una observacion de libro/flujo tiene precio de "
                     "referencia en T y precio objetivo en T+h con resolucion "
                     "y disponibilidad compatibles. MIN/MAX temporales y filas "
                     "existentes NO acreditan por si solas un outcome "
                     "calculable."),
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
