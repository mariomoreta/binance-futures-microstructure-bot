"""Verificacion independiente del inventario de coste de ejecucion.

Reimplementa el calculo con la biblioteca estandar, sin importar el modulo que
genero la salida. No escribe en las capturas y no calcula retornos ajustados.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sqlite3
import statistics
from typing import Any, Dict, List, Optional, Tuple

V = 60_000
H = 300_000
W = 5_000
MIN_PARES = 30

BID_NOMBRES = {"best_bid", "bidprice", "bid_price", "bid_px", "bestbid", "bid"}
ASK_NOMBRES = {"best_ask", "askprice", "ask_price", "ask_px", "bestask", "ask"}


class Comprobaciones:
    def __init__(self) -> None:
        self.total = 0
        self.fallos: List[str] = []

    def check(self, condicion: bool, mensaje: str) -> None:
        self.total += 1
        if not condicion:
            self.fallos.append(mensaje)

    def cerca(self, a: Any, b: Any, mensaje: str, tol: float = 1e-9) -> None:
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            self.check(math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol),
                       "%s: %r != %r" % (mensaje, a, b))
        else:
            self.check(a == b, "%s: %r != %r" % (mensaje, a, b))


def _json(ruta: str) -> Any:
    with io.open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _snapshots(ruta: str) -> Dict[str, List[Dict[str, Any]]]:
    por_simbolo: Dict[str, List[Dict[str, Any]]] = {}
    if not os.path.exists(ruta):
        return por_simbolo
    with io.open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            o = json.loads(linea)
            lib = o.get("libro")
            if not isinstance(lib, dict) or not o.get("symbol"):
                continue
            integ = o.get("integridad") or {}
            por_simbolo.setdefault(o["symbol"], []).append({
                "event_ms": lib.get("event_ms"),
                "received_ms": lib.get("received_ms"),
                "spread_bps": lib.get("spread_bps"),
                "mid": o.get("precio_base"),
                "degradado": bool(integ.get("libro_degradado")),
                "cruzado": bool(integ.get("libro_cruzado")),
                "bid_levels": lib.get("bid_levels"),
                "ask_levels": lib.get("ask_levels"),
                "best_bid": lib.get("best_bid"),
                "best_ask": lib.get("best_ask"),
                "claves": sorted(lib.keys()),
            })
    return por_simbolo


def _mas_cercano(snaps: List[Dict[str, Any]], instante: int
                 ) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    mejor = None
    dist = None
    for s in snaps:
        if s["event_ms"] is None:
            continue
        d = abs(int(s["event_ms"]) - instante)
        if dist is None or d < dist:
            mejor, dist = s, d
    return mejor, dist


def _c1(s: Optional[Dict[str, Any]], instante: int) -> bool:
    return bool(s and s["event_ms"] is not None and s["received_ms"] is not None
                and abs(int(s["event_ms"]) - instante) <= W
                and int(s["received_ms"]) <= instante)


def _c2(s: Optional[Dict[str, Any]]) -> bool:
    return bool(s and not s["degradado"] and not s["cruzado"]
                and int(s["bid_levels"] or 0) >= 1 and int(s["ask_levels"] or 0) >= 1)


def _c0(s: Optional[Dict[str, Any]]) -> bool:
    return bool(s and s["best_bid"] is not None and s["best_ask"] is not None
                and float(s["best_bid"]) > 0 and float(s["best_ask"]) > float(s["best_bid"]))


def _conteos(regs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "episodios": len(regs),
        "bucket_entrada": sum(1 for e in regs if e["bucket_entrada"] is not None),
        "bucket_salida": sum(1 for e in regs if e["bucket_salida"] is not None),
        "bucket_ambos": sum(1 for e in regs if e["bucket_entrada"] is not None
                            and e["bucket_salida"] is not None),
        "bucket_entrada_disponible_al_instante": sum(
            1 for e in regs if e["bucket_entrada"] is not None
            and e["bucket_entrada"]["as_of_ms"] <= e["entrada_ms"]),
        "bucket_salida_disponible_al_instante": sum(
            1 for e in regs if e["bucket_salida"] is not None
            and e["bucket_salida"]["as_of_ms"] <= e["salida_ms"]),
        "obs_entrada_5s": sum(1 for e in regs if e["c1_entrada"]),
        "obs_salida_5s": sum(1 for e in regs if e["c1_salida"]),
        "obs_ambos_5s": sum(1 for e in regs if e["c1_entrada"] and e["c1_salida"]),
        "obs_ambos_5s_calidad_ok": sum(
            1 for e in regs if e["c1_entrada"] and e["c1_salida"]
            and e["c2_entrada"] and e["c2_salida"]),
        "pares_c0": sum(1 for e in regs if e["c0"]),
        "pares_c3": sum(1 for e in regs if e["c3"]),
        "degradados": sum(
            1 for e in regs for k in ("bucket_entrada", "bucket_salida")
            if e[k] is not None and e[k]["degraded"]),
        "cruzados": sum(
            1 for e in regs for k in ("bucket_entrada", "bucket_salida")
            if e[k] is not None and e[k]["crossed"]),
    }


def _comprobar_resumen(c: Comprobaciones, real: Dict[str, Any], esperado: Dict[str, Any],
                       etiqueta: str) -> None:
    for clave, valor in esperado.items():
        c.check(real.get(clave) == valor, "%s.%s: %r != %r" % (etiqueta, clave, real.get(clave), valor))


def verificar(inventario: Dict[str, Any], publicado: Dict[str, Any],
              base_datos: str, compacto: Optional[Dict[str, Any]] = None,
              umbral_cercania: int = W) -> Comprobaciones:
    global W
    W = umbral_cercania
    c = Comprobaciones()

    c.check(inventario.get("version") == "coste-ejecucion-inventario-v1", "version")
    c.check(inventario.get("base_commit") ==
            "2be0e1fcc97ff58b1db0b6e59a8684c789debd07", "base_commit")
    p = inventario.get("parametros", {})
    c.check(p.get("ventana_ms") == V, "ventana_ms")
    c.check(p.get("horizonte_ms") == H, "horizonte_ms")
    c.check(p.get("ventana_cercania_ms") == W, "ventana_cercania_ms")
    c.check(p.get("min_pares") == MIN_PARES, "min_pares")

    detalle = publicado["primaria_solo_precio"]["detalle"]
    c.check(len(detalle) == 278, "detalle publicado = 278")
    c.check(len(inventario["episodios"]) == len(detalle), "episodios inventariados")

    capturas = sorted({e["captura"] for e in detalle})
    conn = {}
    snaps = {}
    for cap in capturas:
        db = os.path.join(base_datos, cap, "research.db")
        conn[cap] = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
        snaps[cap] = _snapshots(os.path.join(base_datos, cap, "observaciones.jsonl"))

    columnas = [f[1] for f in conn[capturas[0]].execute("PRAGMA table_info(research_book_1m)")]
    bid_cols = sorted(set(x.lower() for x in columnas) & BID_NOMBRES)
    ask_cols = sorted(set(x.lower() for x in columnas) & ASK_NOMBRES)
    claves_libro = set()
    for cap in capturas:
        for lista in snaps[cap].values():
            if lista:
                claves_libro = set(lista[0]["claves"])
                break
        if claves_libro:
            break
    c.check(bid_cols == [] and ask_cols == [], "sin campos bid/ask en research_book_1m")
    c.check(not (set(x.lower() for x in claves_libro) & BID_NOMBRES), "sin best_bid en libro")
    c.check(not (set(x.lower() for x in claves_libro) & ASK_NOMBRES), "sin best_ask en libro")

    for e in inventario["episodios"]:
        cap, sym = e["captura"], e["symbol"]
        cut = int(e["cut_ms"])
        entrada = (cut // V + 1) * V
        salida = entrada + H
        tag = "%s|%d" % (sym, cut)
        c.check(e["entrada_ms"] == entrada, tag + ".entrada_ms")
        c.check(e["salida_ms"] == salida, tag + ".salida_ms")

        for clave, ms in (("bucket_entrada", entrada), ("bucket_salida", salida)):
            fila = conn[cap].execute(
                "SELECT bucket_end, sample_count, spread_mean, degraded, crossed, as_of_ms "
                "FROM research_book_1m WHERE symbol=? AND bucket_start=?", (sym, ms)).fetchone()
            real = e[clave]
            c.check((real is not None) == (fila is not None), tag + "." + clave + ".presencia")
            if fila and real:
                c.check(real["bucket_end"] == fila[0], tag + "." + clave + ".bucket_end")
                c.check(real["sample_count"] == fila[1], tag + "." + clave + ".sample_count")
                c.cerca(real["spread_mean_bps"], fila[2], tag + "." + clave + ".spread")
                c.check(real["degraded"] == bool(fila[3]), tag + "." + clave + ".degraded")
                c.check(real["crossed"] == bool(fila[4]), tag + "." + clave + ".crossed")
                c.check(real["as_of_ms"] == fila[5], tag + "." + clave + ".as_of_ms")
                c.check(fila[5] > ms, tag + "." + clave + ".publicado_despues")

        for clave, ms in (("obs_entrada", entrada), ("obs_salida", salida)):
            s, d = _mas_cercano(snaps[cap].get(sym, []), ms)
            real = e[clave]
            c.check((real is not None) == (s is not None), tag + "." + clave + ".presencia")
            if s and real:
                c.check(real["event_ms"] == s["event_ms"], tag + "." + clave + ".event_ms")
                c.check(real["distancia_ms"] == d, tag + "." + clave + ".distancia")
                c.check(real["received_ms"] == s["received_ms"], tag + "." + clave + ".received_ms")
                c.cerca(real["spread_bps"], s["spread_bps"], tag + "." + clave + ".spread")
                c.cerca(real["mid"], s["mid"], tag + "." + clave + ".mid")

        se, de = _mas_cercano(snaps[cap].get(sym, []), entrada)
        sx, dx = _mas_cercano(snaps[cap].get(sym, []), salida)
        c.check(e["c1_entrada"] == _c1(se, entrada), tag + ".c1_entrada")
        c.check(e["c1_salida"] == _c1(sx, salida), tag + ".c1_salida")
        c.check(e["c2_entrada"] == _c2(se), tag + ".c2_entrada")
        c.check(e["c2_salida"] == _c2(sx), tag + ".c2_salida")
        c0 = _c0(se) and _c0(sx)
        c.check(e["c0"] == c0, tag + ".c0")
        c.check(e["c3"] == (c0 and _c1(se, entrada) and _c1(sx, salida)
                            and _c2(se) and _c2(sx)), tag + ".c3")

    for cap in capturas:
        regs = [e for e in inventario["episodios"] if e["captura"] == cap]
        _comprobar_resumen(c, inventario["capturas"][cap], _conteos(regs), "capturas." + cap)
    _comprobar_resumen(c, inventario["total"], _conteos(inventario["episodios"]), "total")

    spread_e = [e["bucket_entrada"]["spread_mean_bps"] for e in inventario["episodios"]
                if e["bucket_entrada"]]
    spread_s = [e["bucket_salida"]["spread_mean_bps"] for e in inventario["episodios"]
                if e["bucket_salida"]]
    c.cerca(inventario["total"]["spread_entrada_bps"]["mediana"], statistics.median(spread_e),
            "spread entrada mediana")
    c.cerca(inventario["total"]["spread_salida_bps"]["mediana"], statistics.median(spread_s),
            "spread salida mediana")
    c.cerca(inventario["margen"]["spread_agregado_mediano_bps"],
            statistics.median(spread_e + spread_s), "spread combinado mediano")

    falt = inventario["faltantes_exactos"]
    c.check(falt["episodios_sin_bucket_entrada"] == 278 - inventario["total"]["bucket_entrada"],
            "faltantes entrada")
    c.check(falt["episodios_sin_bucket_salida"] == 278 - inventario["total"]["bucket_salida"],
            "faltantes salida")
    c.check(falt["episodios_sin_cotizacion_instantanea_ambos_extremos_5s"] ==
            278 - inventario["total"]["obs_ambos_5s"], "faltantes cotizacion")
    c.check(falt["episodios_con_mid_y_spread_instantaneo_ambos_extremos_5s"] ==
            inventario["total"]["obs_ambos_5s_calidad_ok"], "candidatos mid+spread")

    brutos = [float(e["retorno_bruto_bps"]) for e in detalle]
    c.cerca(inventario["margen"]["bruto_medio_278_bps"], statistics.fmean(brutos),
            "bruto medio 278")
    c.cerca(inventario["margen"]["coste_adicional_maximo_bps"], statistics.fmean(brutos),
            "coste adicional maximo")

    desc = [e for e in detalle if e.get("grupo") == "EXTENDIDO"]
    ret = [e for e in detalle if e.get("grupo") != "EXTENDIDO"]
    suma_desc = sum(float(e["retorno_neto_bps"]) for e in desc)
    suma_ret = sum(float(e["retorno_neto_bps"]) for e in ret)
    et = inventario["correccion_etiqueta"]
    c.check(et["descartados"] == len(desc) == 193, "etiqueta descartados")
    c.cerca(et["suma_descartados_bps"], suma_desc, "etiqueta suma descartados")
    c.cerca(et["cambio_de_suma_al_abstenerse_bps"], -suma_desc, "etiqueta cambio de suma")
    c.cerca(et["suma_retenidos_bps"], suma_ret, "etiqueta suma retenidos")
    c.cerca(et["suma_sin_filtro_bps"], suma_desc + suma_ret, "etiqueta suma sin filtro")
    c.check(et["cambio_de_suma_al_abstenerse_bps"] > 0, "etiqueta signo positivo")

    c.check(inventario["veredicto"] ==
            ("DATOS_INSUFICIENTES" if inventario["total"]["pares_c3"] < MIN_PARES else "CON_COBERTURA"),
            "veredicto")
    c.check(inventario["descomposicion_coste"]["comision"] == "UNKNOWN", "comision UNKNOWN")
    c.check(inventario["descomposicion_coste"]["funding"] == "UNKNOWN", "funding UNKNOWN")
    c.check(inventario["descomposicion_coste"]["slippage_adicional"] == "UNKNOWN", "slippage UNKNOWN")

    if compacto is not None:
        c.check(len(compacto["episodios"]) == len(inventario["episodios"]), "compacto episodios")
        _comprobar_resumen(c, compacto["total"], inventario["total"], "compacto.total")
        c.check(compacto["veredicto"] == inventario["veredicto"], "compacto.veredicto")

    for con in conn.values():
        con.close()
    return c


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventario", required=True)
    parser.add_argument("--compacto", default=None)
    parser.add_argument("--publicado", default="docs/evidence/extension-previa-20261119/C-resumen.json")
    parser.add_argument("--datos", default=r"C:\proyectos\binance-futures-data")
    args = parser.parse_args(argv)

    inv = _json(args.inventario)
    publicado = _json(args.publicado)
    compacto = _json(args.compacto) if args.compacto else None
    c = verificar(inv, publicado, args.datos, compacto)
    print("comprobaciones: %d | fallos: %d" % (c.total, len(c.fallos)))
    for f in c.fallos[:30]:
        print("FALLO: " + f)
    return 0 if not c.fallos else 1


if __name__ == "__main__":
    raise SystemExit(main())
