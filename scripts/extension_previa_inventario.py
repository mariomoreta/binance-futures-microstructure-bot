"""Inventario de cobertura para la hipotesis de extension previa.

Pregunta: cuando aparece una senal de continuacion, medir cuanto se ha
extendido el movimiento frente a la historia del propio contrato, permite
evitar entradas peores que una regla de solo precio?

Este modulo SOLO inventaria. No fija umbrales ni compara retornos: cuenta,
por captura distinta de la ventana 4, cuantos casos tienen

  1. historia previa valida del mismo contrato (6 bloques de 3 minutos
     contiguos, no solapados, inmediatamente anteriores a la senal, con
     precio conocido en el corte),
  2. dato disponible al corte (sin usar informacion posterior),
  3. precios verificables de entrada (apertura del minuto siguiente al corte)
     y de salida a cinco minutos (apertura de entrada + 5 min).

Reutiliza el detector publicado sin tocar reglas ni umbrales:
`secuencia_presion_v1.detectar_secuencias` y la construccion de ventanas de
`replay_patron_ventana4.construir_ventanas` (sin el contraste contra
`C-cobertura-real.json`, que solo existe para la ventana 4).

Solo lectura de las capturas. Salida fuera de Git.
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secuencia_presion_v1 import (  # noqa: E402
    VentanaPresion,
    detectar_secuencias,
    utc_iso,
)
from replay_patron_ventana4 import (  # noqa: E402
    HORIZONTE_MS,
    VENTANA_MS,
    _referencia_entrada,
    agrupar_episodios,
    alertas_solo_precio,
    cargar_velas,
    ternas_contiguas,
)

VERSION = "extension-previa-inventario-v1"
BLOQUES_PREVIOS_EXIGIDOS = 6
MINUTOS_POR_BLOQUE = 3

CAPTURAS = [
    {
        "run_id": "exp-v2-ventana-1-20261112a",
        "db": r"C:\proyectos\binance-futures-data\exp-v2-ventana-1-20261112a\research.db",
        "klines": None,
    },
    {
        "run_id": "exp-v2-ventana-2-20261112a",
        "db": r"C:\proyectos\binance-futures-data\exp-v2-ventana-2-20261112a\research.db",
        "klines": None,
    },
    {
        "run_id": "exp-v2-ventana-3-20261115a",
        "db": r"C:\proyectos\binance-futures-data\exp-v2-ventana-3-20261115a\research.db",
        "klines": r"C:\proyectos\binance-futures-data\exp-v2-ventana-3-20261115a\consultas_klines.jsonl",
    },
    {
        "run_id": "public-pilot-1h-20261105a",
        "db": r"C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\research.db",
        "klines": None,
    },
    {
        "run_id": "public-pilot-1h-20261106a",
        "db": r"C:\proyectos\binance-futures-data\public-pilot-1h-20261106a\research.db",
        "klines": None,
    },
]


# ---------------------------------------------------------------------------
# Ventanas desde research.db (mismas reglas que construir_ventanas)
# ---------------------------------------------------------------------------

def _ventanas_desde_db(db_path: Path, run_id: str) -> Tuple[Dict[str, List[VentanaPresion]], Dict[str, Any]]:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    flujo = {}
    for r in con.execute(
        "select * from research_flow_1m order by symbol, bucket_start"
    ):
        flujo[(r["symbol"], int(r["bucket_start"]))] = dict(r)
    libro = {}
    for r in con.execute(
        "select * from research_book_1m order by symbol, bucket_start"
    ):
        libro[(r["symbol"], int(r["bucket_start"]))] = dict(r)
    con.close()

    por_symbol: Dict[str, List[VentanaPresion]] = defaultdict(list)
    faltan_libro = 0
    for (symbol, inicio), f in flujo.items():
        b = libro.get((symbol, inicio))
        if b is None:
            faltan_libro += 1
            continue
        fin = int(f["bucket_end"])
        disp = max(int(f["as_of_ms"]), int(b["as_of_ms"]))
        integridad_ok = (
            int(b["degraded"]) == 0
            and int(b["depth_gaps"]) == 0
            and int(b["crossed"]) == 0
            and f["data_quality"] in ("OK",)
        )
        evento = max(int(f["last_event_ms"]), int(b["last_event_ms"]))
        por_symbol[symbol].append(
            VentanaPresion(
                symbol=symbol,
                observation_id=f"{symbol}|{inicio}",
                decision_ms=fin,
                decision_iso=utc_iso(fin),
                ventana_inicio_ms=inicio,
                ventana_fin_ms=fin,
                evento_ms=evento,
                evento_iso=utc_iso(evento),
                disponibilidad_ms=disp,
                disponibilidad_iso=utc_iso(disp),
                ventana_completa=True,
                ventana_ms=VENTANA_MS,
                buy_notional=float(f["buy_notional"]),
                sell_notional=float(f["sell_notional"]),
                bid_notional_top20=float(b["bid20_mean"]),
                ask_notional_top20=float(b["ask20_mean"]),
                precio_cierre=float(f["price_close"]),
                precio_fuente="aggTrade",
                precio_event_ms=int(f["last_event_ms"]),
                precio_event_iso=utc_iso(int(f["last_event_ms"])),
                integridad_valida=integridad_ok,
                fuente="research.db (research_flow_1m + research_book_1m)",
                cobertura={"run_id": run_id, "flow_data_quality": f["data_quality"]},
            )
        )
    for lista in por_symbol.values():
        lista.sort(key=lambda v: v.ventana_inicio_ms)
    audit = {
        "filas_flujo": len(flujo),
        "filas_libro": len(libro),
        "flujo_sin_libro": faltan_libro,
        "simbolos": len(por_symbol),
        "ventanas": sum(len(v) for v in por_symbol.values()),
        "ventanas_validas": sum(1 for v in por_symbol.values() for w in v if w.esta_valida()),
        "data_quality": dict(Counter(f["data_quality"] for f in flujo.values())),
    }
    return dict(por_symbol), audit


def _precios_desde_flujo(db_path: Path) -> Dict[str, Dict[int, Dict[str, Any]]]:
    """Serie de precios con la misma forma que `cargar_velas`.

    Solo se usa cuando la captura no persistio `consultas_klines.jsonl`.
    La apertura del minuto es el primer precio de aggTrade de ese minuto,
    inmutable; el cierre no se usa para entrada/salida.
    """
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    serie: Dict[str, Dict[int, Dict[str, Any]]] = defaultdict(dict)
    for r in con.execute(
        "select symbol, bucket_start, bucket_end, price_open, price_close, as_of_ms, data_quality "
        "from research_flow_1m"
    ):
        ot = int(r["bucket_start"])
        serie[r["symbol"]][ot] = {
            "open": float(r["price_open"]),
            "close": float(r["price_close"]),
            "close_time": int(r["bucket_end"]) - 1,
            "final": True,
            "adquirido_ms": int(r["as_of_ms"]),
            "conflictiva": False,
            "fuente": "research_flow_1m.price_open",
            "data_quality": r["data_quality"],
        }
    con.close()
    return dict(serie)


# ---------------------------------------------------------------------------
# Historia previa: 6 bloques de 3 minutos contiguos, no solapados
# ---------------------------------------------------------------------------

def _minutos_previos_validos(
    serie: Dict[int, Dict[str, Any]],
    primer_minuto_senal: int,
    cut_ms: int,
) -> List[int]:
    """Minutos contiguos inmediatamente anteriores a la senal, con precio
    conocido en el corte. Devuelve la lista de inicios en orden ascendente."""
    validos: List[int] = []
    t = primer_minuto_senal - VENTANA_MS
    while True:
        vela = serie.get(t)
        if vela is None:
            break
        if vela["conflictiva"]:
            break
        if vela.get("data_quality") not in (None, "OK"):
            break
        if not (vela["open"] > 0 and vela.get("close", 0) > 0):
            break
        if int(vela.get("adquirido_ms") or 0) > cut_ms:
            break
        validos.append(t)
        t -= VENTANA_MS
    validos.reverse()
    return validos


def _bloques_previos(
    serie: Dict[int, Dict[str, Any]],
    primer_minuto_senal: int,
    cut_ms: int,
) -> int:
    """Numero de bloques completos de 3 minutos contiguos y no solapados que
    caben inmediatamente antes de la senal, disponibles en el corte."""
    minutos = _minutos_previos_validos(serie, primer_minuto_senal, cut_ms)
    return len(minutos) // MINUTOS_POR_BLOQUE


def _resultado_precios(
    serie: Dict[str, Dict[int, Dict[str, Any]]],
    symbol: str,
    cut_ms: int,
    direccion: str,
) -> Dict[str, Any]:
    entrada_ms = _referencia_entrada(cut_ms)
    salida_ms = entrada_ms + HORIZONTE_MS
    fila = serie.get(symbol) or {}
    v_in = fila.get(entrada_ms)
    v_out = fila.get(salida_ms)
    base = {"entrada_ms": entrada_ms, "salida_ms": salida_ms}
    if v_in is None:
        return {**base, "estado": "no_resoluble", "motivo": "vela_entrada_ausente"}
    if v_in["conflictiva"]:
        return {**base, "estado": "no_resoluble", "motivo": "vela_contradictoria"}
    if v_out is None:
        return {**base, "estado": "no_resoluble", "motivo": "vela_salida_ausente",
                "precio_entrada": v_in["open"]}
    if v_out["conflictiva"]:
        return {**base, "estado": "no_resoluble", "motivo": "vela_contradictoria",
                "precio_entrada": v_in["open"]}
    entrada, salida = v_in["open"], v_out["open"]
    if not (entrada > 0 and salida > 0):
        return {**base, "estado": "no_resoluble", "motivo": "precio_no_positivo"}
    signo = 1.0 if direccion == "LONG" else -1.0
    return {
        **base,
        "estado": "resoluble",
        "precio_entrada": entrada,
        "precio_salida": salida,
        "retorno_bps": signo * (salida / entrada - 1.0) * 1e4,
    }


# ---------------------------------------------------------------------------
# Inventario por captura
# ---------------------------------------------------------------------------

def inventariar(captura: Dict[str, Any]) -> Dict[str, Any]:
    db = Path(captura["db"])
    run_id = captura["run_id"]
    out: Dict[str, Any] = {"run_id": run_id, "db_existe": db.exists()}
    if not db.exists():
        out["estado"] = "sin_db"
        return out

    por_symbol, audit = _ventanas_desde_db(db, run_id)
    out["auditoria_ventanas"] = audit

    if captura.get("klines") and Path(captura["klines"]).exists():
        velas_kl, audit_velas = cargar_velas(Path(captura["klines"]), run_id)
        serie = _precios_desde_flujo(db)
        # Contraste: apertura de flujo vs apertura de vela donde ambas existen.
        comp = iguales = 0
        difs: List[float] = []
        for symbol, minutos in velas_kl.items():
            for t, v in minutos.items():
                f = serie.get(symbol, {}).get(t)
                if f is None:
                    continue
                comp += 1
                d = abs(f["open"] - v["open"]) / v["open"]
                difs.append(d)
                if d <= 1e-12:
                    iguales += 1
        difs.sort()
        out["contraste_klines"] = {
            "comparadas": comp,
            "identicas": iguales,
            "distintas": comp - iguales,
            "dif_rel_max": difs[-1] if difs else None,
            "dif_rel_mediana": difs[len(difs) // 2] if difs else None,
            "velas_unicas": audit_velas["velas_unicas"],
            "velas_contradictorias": audit_velas["velas_contradictorias"],
        }
        out["fuente_precios"] = (
            "research_flow_1m.price_open/price_close (uniforme); "
            "consultas_klines.jsonl solo como contraste"
        )
    else:
        serie = _precios_desde_flujo(db)
        out["fuente_precios"] = "research_flow_1m.price_open/price_close (captura sin consultas_klines.jsonl)"
    out["auditoria_velas"] = {"simbolos": len(serie),
                              "velas_unicas": sum(len(v) for v in serie.values())}

    # --- senales del patron (detector publicado, sin cambios) ---
    decisiones: Dict[str, Any] = {}
    for symbol, ventanas in por_symbol.items():
        for r in detectar_secuencias(ventanas, symbol):
            decisiones[r.observation_id] = r

    patron: List[Dict[str, Any]] = []
    ternas = 0
    for symbol, ventanas in por_symbol.items():
        for a, b, c in ternas_contiguas(ventanas):
            ternas += 1
            r = decisiones.get(c.observation_id)
            if r is None or r.decision not in ("LONG_EXPERIMENTAL", "SHORT_EXPERIMENTAL"):
                continue
            cut = max(int(c.ventana_fin_ms), int(a.disponibilidad_ms or 0),
                      int(b.disponibilidad_ms or 0), int(c.disponibilidad_ms or 0))
            patron.append({
                "symbol": symbol,
                "direccion": r.direccion_candidata,
                "terna": f"{symbol}|{c.ventana_inicio_ms}",
                "primer_minuto_ms": int(a.ventana_inicio_ms),
                "cierre_nominal_ms": int(c.ventana_fin_ms),
                "cut_ms": cut,
                "cut_iso": utc_iso(cut),
                "demora_corte_ms": cut - int(c.ventana_fin_ms),
                "tambien_patron": True,
                "decision": r.decision,
            })

    # --- senales de solo precio (misma regla publicada) ---
    ternas_patron = {f"{p['symbol']}|{p['cierre_nominal_ms'] - VENTANA_MS}": p for p in patron}
    solo_precio, resumen_sp = alertas_solo_precio(db, run_id, ternas_patron)

    # Episodios: primera alerta por (contrato, direccion) dentro de 5 minutos,
    # regla publicada, para no contar la misma senal deslizante muchas veces.
    patron_eps = agrupar_episodios(patron)
    solo_eps = agrupar_episodios(solo_precio)

    def _evaluar(lista: List[Dict[str, Any]], etiqueta: str) -> Dict[str, Any]:
        con_historia = 0
        con_precios = 0
        completos = 0
        por_bloques = Counter()
        faltantes = Counter()
        detalle: List[Dict[str, Any]] = []
        for a in lista:
            symbol = a["symbol"]
            fila = serie.get(symbol) or {}
            primer_minuto = a.get("primer_minuto_ms")
            if primer_minuto is None:
                primer_minuto = int(a["cierre_nominal_ms"]) - MINUTOS_POR_BLOQUE * VENTANA_MS
            bloques = _bloques_previos(fila, primer_minuto, a["cut_ms"])
            por_bloques[bloques] += 1
            tiene_historia = bloques >= BLOQUES_PREVIOS_EXIGIDOS
            res = _resultado_precios(serie, symbol, a["cut_ms"], a["direccion"])
            tiene_precios = res["estado"] == "resoluble"
            con_historia += int(tiene_historia)
            con_precios += int(tiene_precios)
            ok = tiene_historia and tiene_precios
            completos += int(ok)
            if not ok:
                if not tiene_historia:
                    faltantes["historia_previa_insuficiente"] += 1
                if not tiene_precios:
                    faltantes[res["motivo"]] += 1
            detalle.append({
                "symbol": symbol,
                "direccion": a["direccion"],
                "cut_iso": utc_iso(a["cut_ms"]),
                "bloques_previos": bloques,
                "historia_ok": tiene_historia,
                "precios_estado": res["estado"],
                "precios_motivo": res.get("motivo"),
            })
        return {
            "etiqueta": etiqueta,
            "senales": len(lista),
            "con_historia_previa_6_bloques": con_historia,
            "con_precios_entrada_salida": con_precios,
            "completos": completos,
            "por_bloques_previos": {str(k): v for k, v in sorted(por_bloques.items())},
            "faltantes": dict(faltantes),
            "por_simbolo_completos": dict(Counter(
                d["symbol"] for d in detalle if d["historia_ok"] and d["precios_estado"] == "resoluble"
            )),
            "detalle": detalle,
        }

    out["ternas_contiguas"] = ternas
    out["patron_alertas_brutas"] = len(patron)
    out["solo_precio_alertas_brutas"] = len(solo_precio)
    out["patron"] = _evaluar(patron_eps, "patron_episodios")
    out["solo_precio"] = _evaluar(solo_eps, "solo_precio_episodios")
    out["solo_precio_resumen_publicado"] = resumen_sp
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    args = ap.parse_args(argv)

    resultado = {"version": VERSION, "bloques_previos_exigidos": BLOQUES_PREVIOS_EXIGIDOS,
                 "capturas": []}
    for cap in CAPTURAS:
        print(f"inventariando {cap['run_id']} ...", flush=True)
        resultado["capturas"].append(inventariar(cap))

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with io.open(salida, "w", encoding="utf-8", newline="\n") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    for c in resultado["capturas"]:
        p = c.get("patron", {})
        s = c.get("solo_precio", {})
        print(f"{c['run_id']}: ternas={c.get('ternas_contiguas')} "
              f"patron={p.get('senales')} completos={p.get('completos')} | "
              f"solo_precio={s.get('senales')} completos={s.get('completos')}")
    print(f"resumen={salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
