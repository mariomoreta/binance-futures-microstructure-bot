# -*- coding: utf-8 -*-
"""Verificacion independiente del diagnostico de factores (ventana 4).

No importa el modulo diagnosticado. Recalcula desde `research.db` (solo
lectura), `consultas_klines.jsonl` y los derivados publicados:

  * geometria de las 4 ternas: flujo alineado, profundidad contraria, cierres,
    Q y su descomposicion importe/profundidad;
  * impacto marginal por tramo (impacto_2, impacto_3, relativo);
  * ultimos 30 s y concentracion de los 6 buckets de 10 s;
  * primer cambio posterior: bloque alineado al reloj, motivos de descarte,
    disponibilidad, corte y entrada del cambio (nunca la entrada original);
  * la misma capa at_cut para las 143 anclas publicadas;
  * entrada/salida y retorno originales de los 4 casos desde las velas
    persistidas.

Uso:
  python scripts/verificar_factores_ventana4.py \
      --db <research.db> --anclas <dir anclas> --derivados <dir derivados> \
      --klines <consultas_klines.jsonl> --resumen <C-resumen.json>

Salida: una linea por check y un resumen final. Codigo 0 si todo coincide.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VERSION = "verificacion-factores-v1"
MIN = 60_000
S = 10_000
TOL = 1.1e-4

FALLOS: List[str] = []
CHECKS = [0]


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    CHECKS[0] += 1
    if not ok:
        FALLOS.append(f"{nombre} {detalle}".strip())


def cerca(a: Any, b: Any, tol: float = TOL) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def leer_jsonl(ruta: Path) -> List[Dict[str, Any]]:
    with io.open(ruta, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def signo(direccion: str) -> float:
    return 1.0 if direccion == "LONG" else -1.0


def fila_flujo(con, symbol: str, inicio: int, run_id: str):
    return con.execute(
        "SELECT buy_notional, sell_notional, price_open, price_close, "
        "bucket_start, bucket_end, as_of_ms, data_quality, last_event_ms "
        "FROM research_flow_1m WHERE symbol=? AND bucket_start=? AND run_id=?",
        (symbol, inicio, run_id),
    ).fetchone()


def fila_libro(con, symbol: str, inicio: int, run_id: str):
    return con.execute(
        "SELECT bid20_mean, ask20_mean, bucket_start, bucket_end, as_of_ms, "
        "degraded, depth_gaps, crossed "
        "FROM research_book_1m WHERE symbol=? AND bucket_start=? AND run_id=?",
        (symbol, inicio, run_id),
    ).fetchone()


def fila_10s(con, symbol: str, inicio: int, run_id: str):
    return con.execute(
        "SELECT buy_notional, sell_notional, price_open, price_close, "
        "bucket_start, bucket_end, as_of_ms, data_quality "
        "FROM research_flow_10s WHERE symbol=? AND bucket_start=? AND run_id=?",
        (symbol, inicio, run_id),
    ).fetchone()


def flujo_util(f) -> Optional[str]:
    if f is None:
        return "flujo_ausente"
    # Mismo orden que la definicion congelada: calidad, disponibilidad, coherencia.
    if f["data_quality"] != "OK":
        return "flujo_incompleto"
    if int(f["as_of_ms"]) < int(f["bucket_end"]):
        return "flujo_sin_disponibilidad"
    if int(f["bucket_start"]) != int(f["bucket_end"]) - MIN:
        return "flujo_incoherente"
    return None


def libro_util(b) -> Optional[str]:
    if b is None:
        return "libro_ausente"
    if int(b["as_of_ms"]) < int(b["bucket_end"]):
        return "libro_sin_disponibilidad"
    if int(b["degraded"]) or int(b["depth_gaps"]) or int(b["crossed"]):
        return "libro_incompleto"
    return None


def terna_geometria(con, symbol: str, tercer_inicio: int, direccion: str,
                    run_id: str) -> Dict[str, Any]:
    s = signo(direccion)
    ventanas = []
    for k in (2, 1, 0):
        inicio = tercer_inicio - k * MIN
        f = fila_flujo(con, symbol, inicio, run_id)
        b = fila_libro(con, symbol, inicio, run_id)
        if f is None or b is None:
            return {"estado": "UNKNOWN", "motivo": "ventana_incompleta"}
        alineado = s * (float(f["buy_notional"]) - float(f["sell_notional"]))
        prof = float(b["bid20_mean"]) if direccion == "SHORT" else float(b["ask20_mean"])
        ventanas.append({
            "flujo": alineado,
            "profundidad": prof,
            "cierre": float(f["price_close"]),
        })
    return {"estado": "resoluble", "ventanas": ventanas}


def delta_bps(nuevo: float, base: float, direccion: str) -> float:
    return signo(direccion) * (nuevo / base - 1.0) * 1e4


def descomponer(f1: float, f3: float, d1: float, d3: float) -> Dict[str, Any]:
    if f1 <= 0 or f3 <= 0 or d1 <= 0 or d3 <= 0:
        return {"estado": "UNKNOWN", "motivo": "presion_o_profundidad_no_positiva"}
    q1 = f1 / d1
    q3 = f3 / d3
    if not q3 > q1:
        return {"estado": "UNKNOWN", "motivo": "q_no_crece"}
    dlq = math.log(q3 / q1)
    dlf = math.log(f3 / f1)
    dld = math.log(d3 / d1)
    return {
        "estado": "resoluble",
        "aporte_importe_pct": 100.0 * dlf / dlq,
        "aporte_profundidad_pct": -100.0 * dld / dlq,
        "profundidad_cae_pct": (d3 / d1 - 1.0) * 100.0,
        "q_crecimiento": q3 / q1,
    }


def impacto(f2: float, f3: float, c1: float, c2: float, c3: float,
            direccion: str) -> Dict[str, Any]:
    if f2 <= 0 or f3 <= 0:
        return {"estado": "UNKNOWN", "motivo": "presion_o_profundidad_no_positiva"}
    d2 = delta_bps(c2, c1, direccion)
    d3 = delta_bps(c3, c2, direccion)
    if d2 <= 0:
        return {"estado": "UNKNOWN", "motivo": "impacto_2_no_positivo"}
    i2 = d2 / (f2 / 1000.0)
    i3 = d3 / (f3 / 1000.0)
    return {
        "estado": "resoluble",
        "delta_2_bps": d2,
        "delta_3_bps": d3,
        "impacto_2": i2,
        "impacto_3": i3,
        "impacto_relativo": i3 / i2,
    }


def ultimos_30s(con, symbol: str, fin: int, direccion: str, run_id: str):
    s = signo(direccion)
    filas = []
    faltantes = []
    for k in (3, 2, 1):
        inicio = fin - k * S
        f = fila_10s(con, symbol, inicio, run_id)
        if f is None:
            faltantes.append({"inicio_ms": inicio, "motivo": "bucket_10s_ausente"})
            continue
        if int(f["as_of_ms"]) < int(f["bucket_end"]):
            faltantes.append({"inicio_ms": inicio,
                              "motivo": "bucket_10s_sin_disponibilidad"})
            continue
        if f["data_quality"] != "OK":
            faltantes.append({"inicio_ms": inicio, "motivo": "bucket_10s_incompleto"})
            continue
        filas.append(f)
    if faltantes:
        return {"estado": "UNKNOWN", "faltantes": faltantes}
    alineado = sum(s * (float(f["buy_notional"]) - float(f["sell_notional"]))
                   for f in filas)
    cambio = delta_bps(float(filas[-1]["price_close"]), float(filas[0]["price_open"]),
                       direccion)
    return {"estado": "resoluble", "flujo": alineado, "delta_bps": cambio}


def concentracion(con, symbol: str, fin: int, run_id: str):
    deltas = []
    for k in range(6):
        inicio = fin - MIN + k * S
        f = fila_10s(con, symbol, inicio, run_id)
        if f is None or int(f["as_of_ms"]) < int(f["bucket_end"]) \
                or f["data_quality"] != "OK":
            return {"estado": "UNKNOWN"}
        deltas.append(float(f["sell_notional"]) - float(f["buy_notional"]))
    total = sum(deltas)
    if total == 0:
        return {"estado": "UNKNOWN"}
    mayor = max(range(6), key=lambda i: abs(deltas[i]))
    return {"estado": "resoluble", "concentracion": abs(deltas[mayor]) / abs(total),
            "dominante_ms": fin - MIN + mayor * S}


def primer_cambio(con, symbol: str, direccion: str, cut: int, f3: float, d3: float,
                  c3: float, run_id: str):
    s = signo(direccion)
    b0 = (cut // MIN) * MIN
    no_usables = []
    anterior_cierre = None
    anterior_usable = None
    for k in range(6):
        inicio = b0 + k * MIN
        f = fila_flujo(con, symbol, inicio, run_id)
        b = fila_libro(con, symbol, inicio, run_id)
        motivo = flujo_util(f)
        if motivo is not None:
            no_usables.append({"k": k, "motivo": motivo})
            continue
        alineado = s * (float(f["buy_notional"]) - float(f["sell_notional"]))
        # Delta de cierre solo contra el bloque inmediatamente anterior; b_0 contra
        # el cierre de la tercera ventana. Tras un hueco queda UNKNOWN.
        if k == 0:
            base = c3
        elif anterior_usable == k - 1:
            base = anterior_cierre
        else:
            base = None
        cambio = (delta_bps(float(f["price_close"]), base, direccion)
                  if base is not None else None)
        anterior_cierre = float(f["price_close"])
        anterior_usable = k
        motivo_libro = libro_util(b)
        prof = None
        if motivo_libro is None:
            prof = float(b["bid20_mean"]) if direccion == "SHORT" else float(b["ask20_mean"])
        tipos = []
        if alineado <= 0:
            tipos.append("giro")
        elif alineado < f3:
            tipos.append("debilitamiento")
        if alineado > 0 and cambio is not None and cambio <= 0:
            tipos.append("precio_sin_avance")
        if prof is not None and prof > d3:
            tipos.append("profundidad_deja_de_caer")
        if not tipos:
            continue
        disp = max(int(f["bucket_end"]), int(f["as_of_ms"]))
        if motivo_libro is None:
            disp = max(disp, int(b["as_of_ms"]))
        return {
            "k": k,
            "tipo": tipos[0],
            "tipos": tipos,
            "disponibilidad_ms": disp,
            "flujo": alineado,
            "delta_bps": cambio,
            "profundidad": prof,
            "no_usables": no_usables,
        }
    return {"k": None, "tipo": None, "no_usables": no_usables}


def verificar_caso(con, caso: Dict[str, Any], run_id: str) -> None:
    symbol = caso["symbol"]
    direccion = caso["direccion"]
    tercer = int(caso["terna"].split("|")[1])
    geo = terna_geometria(con, symbol, tercer, direccion, run_id)
    check(f"{symbol}/geometria", geo["estado"] == "resoluble")
    if geo["estado"] != "resoluble":
        return
    v = geo["ventanas"]
    for i, ventana in enumerate(v):
        ref = caso["at_cut"]["ventanas"][i]
        check(f"{symbol}/v{i}/flujo", cerca(ventana["flujo"], ref["flujo_alineado"]),
              f"{ventana['flujo']} vs {ref['flujo_alineado']}")
        check(f"{symbol}/v{i}/profundidad",
              cerca(ventana["profundidad"], ref["profundidad_contraria"]),
              f"{ventana['profundidad']} vs {ref['profundidad_contraria']}")
        check(f"{symbol}/v{i}/cierre", cerca(ventana["cierre"], ref["precio_cierre"]),
              f"{ventana['cierre']} vs {ref['precio_cierre']}")

    q = descomponer(v[0]["flujo"], v[2]["flujo"],
                    v[0]["profundidad"], v[2]["profundidad"])
    ref_q = caso["at_cut"]["q_descomposicion"]
    check(f"{symbol}/q/estado", q["estado"] == ref_q["estado"])
    if q["estado"] == "resoluble":
        check(f"{symbol}/q/importe", cerca(q["aporte_importe_pct"],
                                           ref_q["aporte_importe_pct"]),
              f"{q['aporte_importe_pct']} vs {ref_q['aporte_importe_pct']}")
        check(f"{symbol}/q/profundidad", cerca(q["aporte_profundidad_pct"],
                                               ref_q["aporte_profundidad_pct"]))
        check(f"{symbol}/q/cae", cerca(q["profundidad_cae_pct"],
                                       ref_q["profundidad_cae_pct"]))

    im = impacto(v[1]["flujo"], v[2]["flujo"], v[0]["cierre"], v[1]["cierre"],
                 v[2]["cierre"], direccion)
    ref_im = caso["at_cut"]["impacto"]
    check(f"{symbol}/impacto/estado", im["estado"] == ref_im["estado"])
    if im["estado"] == "resoluble":
        check(f"{symbol}/impacto/2", cerca(im["impacto_2"],
                                           ref_im["impacto_2_bps_por_1k"], 1e-3))
        check(f"{symbol}/impacto/3", cerca(im["impacto_3"],
                                           ref_im["impacto_3_bps_por_1k"], 1e-3))
        check(f"{symbol}/impacto/rel", cerca(im["impacto_relativo"],
                                             ref_im["impacto_relativo"], 2e-3))

    u = ultimos_30s(con, symbol, tercer + MIN, direccion, run_id)
    ref_u = caso["at_cut"]["ultimos_30s"]
    check(f"{symbol}/u30/estado", u["estado"] == ref_u["estado"])
    if u["estado"] == "resoluble":
        check(f"{symbol}/u30/flujo", cerca(u["flujo"], ref_u["flujo_alineado_30s"]))
        check(f"{symbol}/u30/delta", cerca(u["delta_bps"],
                                           ref_u["delta_precio_30s_bps"]))

    c = concentracion(con, symbol, tercer + MIN, run_id)
    ref_c = caso["at_cut"]["concentracion_10s"]
    check(f"{symbol}/conc/estado", c["estado"] == ref_c["estado"])
    if c["estado"] == "resoluble":
        check(f"{symbol}/conc/valor", cerca(c["concentracion"], ref_c["concentracion"]))
        check(f"{symbol}/conc/dominante", c["dominante_ms"] == ref_c["bucket_dominante_ms"])

    pc = primer_cambio(con, symbol, direccion, int(caso["cut_ms"]),
                       v[2]["flujo"], v[2]["profundidad"], v[2]["cierre"], run_id)
    ref_pc = caso["post"]["primer_cambio"]
    check(f"{symbol}/cambio/k", pc["k"] == ref_pc["k"],
          f"{pc['k']} vs {ref_pc['k']}")
    check(f"{symbol}/cambio/tipo", pc["tipo"] == ref_pc["tipo"],
          f"{pc['tipo']} vs {ref_pc['tipo']}")
    if pc["k"] is not None:
        check(f"{symbol}/cambio/disp", pc["disponibilidad_ms"] == ref_pc["disponibilidad_ms"],
              f"{pc['disponibilidad_ms']} vs {ref_pc['disponibilidad_ms']}")
        check(f"{symbol}/cambio/flujo", cerca(pc["flujo"], ref_pc["flujo_alineado"]))
        check(f"{symbol}/cambio/delta", cerca(pc["delta_bps"],
                                              ref_pc["delta_cierre_bps"]))
        check(f"{symbol}/cambio/no_usables",
              [x["motivo"] for x in pc["no_usables"]]
              == [x["motivo"] for x in ref_pc["bloques_no_usables_antes"]])
        entrada = (pc["disponibilidad_ms"] // MIN + 1) * MIN
        check(f"{symbol}/cambio/entrada", entrada == caso["post"]["resultado"]["entrada_ms"],
              f"{entrada} vs {caso['post']['resultado']['entrada_ms']}")
        original = caso["original"]["entrada_ms"]
        check(f"{symbol}/cambio/entrada_no_original", entrada != original)


def verificar_ancla(con, ancla: Dict[str, Any], run_id: str) -> None:
    symbol = ancla["symbol"]
    direccion = ancla["direccion"]
    tercer = int(ancla["terna"].split("|")[1])
    geo = terna_geometria(con, symbol, tercer, direccion, run_id)
    check(f"ancla {symbol}@{tercer}/geometria", geo["estado"] == "resoluble")
    if geo["estado"] != "resoluble":
        return
    v = geo["ventanas"]
    q = descomponer(v[0]["flujo"], v[2]["flujo"],
                    v[0]["profundidad"], v[2]["profundidad"])
    ref_q = ancla["at_cut"]["q_descomposicion"]
    check(f"ancla {symbol}@{tercer}/q/estado", q["estado"] == ref_q["estado"])
    if q["estado"] == "resoluble" and ref_q["estado"] == "resoluble":
        check(f"ancla {symbol}@{tercer}/q/importe",
              cerca(q["aporte_importe_pct"], ref_q["aporte_importe_pct"]))
        check(f"ancla {symbol}@{tercer}/q/profundidad",
              cerca(q["aporte_profundidad_pct"], ref_q["aporte_profundidad_pct"]))
    im = impacto(v[1]["flujo"], v[2]["flujo"], v[0]["cierre"], v[1]["cierre"],
                 v[2]["cierre"], direccion)
    ref_im = ancla["at_cut"]["impacto"]
    check(f"ancla {symbol}@{tercer}/impacto/estado", im["estado"] == ref_im["estado"])
    if im["estado"] == "resoluble" and ref_im["estado"] == "resoluble":
        check(f"ancla {symbol}@{tercer}/impacto/rel",
              cerca(im["impacto_relativo"], ref_im["impacto_relativo"], 2e-3))


def cargar_velas(ruta: Path, run_id: str) -> Dict[str, Dict[int, Dict[str, Any]]]:
    """Aperturas de velas 1 m desde las consultas persistidas (sin reusar el modulo).

    Una vela es definitiva si la consulta se adquirio despues de su cierre. Si dos
    instantaneas definitivas discrepan en la apertura, la vela se marca
    contradictoria y no se usa.
    """
    velas: Dict[str, Dict[int, Dict[str, Any]]] = {}
    with io.open(ruta, encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            d = json.loads(linea)
            if d.get("kind") != "consulta_klines_trayectoria":
                continue
            if d.get("run_id") != run_id:
                continue
            if d.get("interval") != "1m" or d.get("http_status") != 200:
                continue
            symbol = d["symbol"]
            adquirido = int(d.get("adquirido_ms") or 0)
            try:
                cuerpo = json.loads(d["cuerpo"])
            except Exception:  # noqa: BLE001
                continue
            for fila in cuerpo:
                if len(fila) < 7:
                    continue
                ot = int(fila[0])
                if ot % MIN != 0 or int(fila[6]) != ot + MIN - 1:
                    continue
                nueva = {
                    "open": float(fila[1]),
                    "final": adquirido > int(fila[6]),
                    "conflictiva": False,
                }
                serie = velas.setdefault(symbol, {})
                previa = serie.get(ot)
                if previa is None:
                    serie[ot] = nueva
                    continue
                if previa["open"] != nueva["open"]:
                    previa["conflictiva"] = True
                    continue
                if nueva["final"] and not previa["final"]:
                    serie[ot] = nueva
    return velas


def verificar_originales(casos: List[Dict[str, Any]], velas) -> None:
    for caso in casos:
        symbol = caso["symbol"]
        s = signo(caso["direccion"])
        entrada = int(caso["original"]["entrada_ms"])
        salida = int(caso["original"]["salida_ms"])
        check(f"{symbol}/orig/entrada", entrada == (int(caso["cut_ms"]) // MIN + 1) * MIN)
        check(f"{symbol}/orig/salida", salida == entrada + 5 * MIN)
        serie = velas.get(symbol, {})
        v_entrada = serie.get(entrada)
        v_salida = serie.get(salida)
        check(f"{symbol}/orig/velas",
              v_entrada is not None and v_salida is not None
              and not v_entrada["conflictiva"] and not v_salida["conflictiva"])
        if v_entrada is not None and v_salida is not None:
            retorno = s * (v_salida["open"] / v_entrada["open"] - 1.0) * 1e4
            check(f"{symbol}/orig/retorno",
                  cerca(retorno, caso["original"]["retorno_bps"], 1e-3),
                  f"{retorno} vs {caso['original']['retorno_bps']}")
            check(f"{symbol}/orig/precio_entrada",
                  cerca(v_entrada["open"], caso["original"]["precio_entrada"], 1e-12))
            check(f"{symbol}/orig/precio_salida",
                  cerca(v_salida["open"], caso["original"]["precio_salida"], 1e-12))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--anclas", required=True)
    ap.add_argument("--derivados", required=True)
    ap.add_argument("--klines", required=True)
    ap.add_argument("--resumen", required=True)
    ap.add_argument("--run-id", default="exp-v2-ventana-4-20261116a")
    args = ap.parse_args()

    con = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True)
    con.row_factory = sqlite3.Row

    casos = leer_jsonl(Path(args.derivados) / "casos_factores.jsonl")
    anclas = leer_jsonl(Path(args.derivados) / "anclas_factores.jsonl")
    publicados = leer_jsonl(Path(args.anclas) / "episodios_patron_originales.jsonl")
    referencias = leer_jsonl(Path(args.anclas) / "episodios_referencia_universo_igual.jsonl")
    resumen = json.load(io.open(args.resumen, encoding="utf-8"))

    check("version", resumen.get("version_diagnostico") == "diagnostico-factores-v1")
    check("casos_n", len(casos) == 4)
    check("anclas_n", len(anclas) == 143)
    check("casos_publicados_n", len(publicados) == 4)
    check("anclas_publicadas_n", len(referencias) == 143)
    check("anclas_publicadas_ternas",
          {a["terna"] for a in referencias} == {a["terna"] for a in anclas})

    for caso in casos:
        verificar_caso(con, caso, args.run_id)
    for ancla in anclas:
        verificar_ancla(con, ancla, args.run_id)
    verificar_originales(casos, cargar_velas(Path(args.klines), args.run_id))

    # Los agregados del resumen deben salir de los mismos derivados.
    q_res = sum(1 for a in anclas if a["at_cut"]["q_descomposicion"]["estado"] == "resoluble")
    im_res = sum(1 for a in anclas if a["at_cut"]["impacto"]["estado"] == "resoluble")
    u_res = sum(1 for a in anclas if a["at_cut"]["ultimos_30s"]["estado"] == "resoluble")
    c_res = sum(1 for a in anclas
                if a["at_cut"]["concentracion_10s"]["estado"] == "resoluble")
    check("resumen/q_resoluble", resumen["controles"]["at_cut"]["q_descomposicion"]
          ["estados"].get("resoluble") == q_res, f"{q_res}")
    check("resumen/impacto_resoluble", resumen["controles"]["at_cut"]["impacto"]
          ["estados"].get("resoluble") == im_res, f"{im_res}")
    check("resumen/u30_resoluble", resumen["controles"]["at_cut"]["ultimos_30s"]
          ["estados"].get("resoluble") == u_res, f"{u_res}")
    check("resumen/conc_resoluble", resumen["controles"]["at_cut"]["concentracion_10s"]
          ["estados"].get("resoluble") == c_res, f"{c_res}")
    check("resumen/giro30",
          resumen["controles"]["at_cut"]["ultimos_30s"]["giro_30s"]
          == sum(1 for a in anclas if a["at_cut"]["ultimos_30s"].get("giro_30s") is True))
    check("resumen/psa30",
          resumen["controles"]["at_cut"]["ultimos_30s"]["presion_sin_avance_30s"]
          == sum(1 for a in anclas
                 if a["at_cut"]["ultimos_30s"].get("presion_sin_avance_30s") is True))
    check("resumen/reutiliza_entrada",
          resumen["controles"]["cambios"]["reutiliza_entrada_original"] == 0)

    print(f"version={VERSION}")
    print(f"checks={CHECKS[0]} fallos={len(FALLOS)}")
    for f in FALLOS[:40]:
        print("  FALLO", f)
    print("RESULTADO:", "OK" if not FALLOS else "FALLO")
    return 0 if not FALLOS else 1


if __name__ == "__main__":
    raise SystemExit(main())
