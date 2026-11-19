"""Verificador independiente de la evaluacion de extension previa.

Reimplementa desde cero, con solo la biblioteca estandar, el embudo, la
definicion de extension y los retornos, leyendo directamente cada
`research.db`. No importa el modulo evaluado.

Uso:
    python scripts/verificar_extension_previa_v1.py <resumen.json>

Sale con 0 si todas las comprobaciones coinciden, 1 si alguna falla.
"""

from __future__ import annotations

import io
import json
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

VENTANA = 60_000
HORIZONTE = 5 * 60_000
GRUPO = 5 * 60_000
COSTE = 16.0
BLOQUES = 6
MINUTOS_BLOQUE = 3
MINUTOS_PREVIOS = BLOQUES * MINUTOS_BLOQUE
UMBRAL = 1.0

CAPTURAS = [
    (r"C:\proyectos\binance-futures-data\exp-v2-ventana-1-20261112a\research.db",
     "exp-v2-ventana-1-20261112a"),
    (r"C:\proyectos\binance-futures-data\exp-v2-ventana-2-20261112a\research.db",
     "exp-v2-ventana-2-20261112a"),
    (r"C:\proyectos\binance-futures-data\exp-v2-ventana-3-20261115a\research.db",
     "exp-v2-ventana-3-20261115a"),
    (r"C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\research.db",
     "public-pilot-1h-20261105a"),
    (r"C:\proyectos\binance-futures-data\public-pilot-1h-20261106a\research.db",
     "public-pilot-1h-20261106a"),
]

checks = 0
fallos = []


def check(ok: bool, etiqueta: str, detalle: str = "") -> None:
    global checks
    checks += 1
    if not ok:
        fallos.append(f"{etiqueta}: {detalle}")


def igual(a, b, tol=1e-9) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)), abs(float(b)))


def igual4(x, y) -> bool:
    """Compara con el redondeo a 4 decimales que publica el modulo."""
    if x is None or y is None:
        return x is None and y is None
    return abs(round(float(x), 4) - float(y)) <= 1e-9


def leer(db: str):
    con = sqlite3.connect("file:" + Path(db).as_posix() + "?mode=ro", uri=True)
    filas = defaultdict(list)
    for symbol, inicio, fin, po, pc, as_of, dq in con.execute(
        "select symbol, bucket_start, bucket_end, price_open, price_close, as_of_ms, data_quality "
        "from research_flow_1m"
    ):
        filas[symbol].append({
            "inicio": int(inicio), "fin": int(fin),
            "open": float(po), "close": float(pc),
            "as_of": int(as_of), "dq": dq,
        })
    con.close()
    for lista in filas.values():
        lista.sort(key=lambda f: f["inicio"])
    return dict(filas)


def alertas_solo_precio(filas):
    salida = []
    for symbol, lista in filas.items():
        for i in range(len(lista) - 2):
            a, b, c = lista[i], lista[i + 1], lista[i + 2]
            if not (a["fin"] == b["inicio"] and b["fin"] == c["inicio"]):
                continue
            if a["close"] < b["close"] < c["close"]:
                direccion = "LONG"
            elif a["close"] > b["close"] > c["close"]:
                direccion = "SHORT"
            else:
                continue
            cut = max(c["fin"], a["as_of"], b["as_of"], c["as_of"])
            salida.append({
                "symbol": symbol, "direccion": direccion,
                "terna": f"{symbol}|{c['inicio']}",
                "cut": cut, "cierre_nominal": c["fin"],
            })
    salida.sort(key=lambda x: (x["cut"], x["symbol"], x["direccion"], x["terna"]))
    return salida


def agrupar(alertas):
    por_clave = defaultdict(list)
    for a in alertas:
        por_clave[(a["symbol"], a["direccion"])].append(a)
    episodios = []
    for (symbol, direccion), lista in por_clave.items():
        lista.sort(key=lambda x: (x["cut"], x["terna"]))
        actual = None
        for a in lista:
            if actual is None or a["cut"] >= actual["cut"] + GRUPO:
                actual = {"symbol": symbol, "direccion": direccion,
                          "cut": a["cut"], "cierre_nominal": a["cierre_nominal"]}
                episodios.append(actual)
    episodios.sort(key=lambda e: (e["cut"], e["symbol"], e["direccion"]))
    return episodios


def evaluar(ep, filas):
    symbol, direccion, cut = ep["symbol"], ep["direccion"], ep["cut"]
    lista = filas.get(symbol) or []
    por_inicio = {f["inicio"]: f for f in lista}
    t3 = ep["cierre_nominal"] - VENTANA
    t1 = t3 - 2 * VENTANA
    v1 = por_inicio.get(t1)
    v3 = por_inicio.get(t3)
    if v1 is None or v3 is None or v1["close"] <= 0 or v3["close"] <= 0:
        return {"estado": "no_evaluable", "motivo": "cierre_de_senal_ausente", "bloques": 0}
    minutos = []
    t = t1 - VENTANA
    motivo_hist = None
    while len(minutos) < MINUTOS_PREVIOS:
        f = por_inicio.get(t)
        if f is None:
            motivo_hist = "minuto_previo_ausente"; break
        if f["dq"] != "OK":
            motivo_hist = "minuto_previo_no_ok"; break
        if f["open"] <= 0 or f["close"] <= 0:
            motivo_hist = "minuto_previo_sin_precio"; break
        if f["as_of"] > cut:
            motivo_hist = "minuto_previo_no_disponible_al_corte"; break
        minutos.append(t)
        t -= VENTANA
    minutos.reverse()
    if len(minutos) < MINUTOS_PREVIOS:
        return {"estado": "no_evaluable", "motivo": "historia_previa_insuficiente",
                "detalle_motivo": motivo_hist,
                "bloques": len(minutos) // MINUTOS_BLOQUE}
    avances = []
    for i in range(BLOQUES):
        bloque = minutos[i * MINUTOS_BLOQUE:(i + 1) * MINUTOS_BLOQUE]
        ci = por_inicio[bloque[0]]["close"]
        cf = por_inicio[bloque[-1]]["close"]
        if ci <= 0 or cf <= 0:
            return {"estado": "no_evaluable", "motivo": "bloque_previo_sin_precio",
                    "bloques": BLOQUES}
        avances.append(abs(cf / ci - 1.0))
    mediana = statistics.median(avances)
    if mediana <= 0:
        return {"estado": "no_evaluable", "motivo": "mediana_previa_nula",
                "bloques": BLOQUES}
    avance_senal = abs(v3["close"] / v1["close"] - 1.0)
    extension = avance_senal / mediana
    entrada_ms = (cut // VENTANA + 1) * VENTANA
    v_in = por_inicio.get(entrada_ms)
    if v_in is None or v_in["open"] <= 0:
        return {"estado": "no_evaluable", "motivo": "vela_entrada_ausente",
                "bloques": BLOQUES}
    v_out = por_inicio.get(entrada_ms + HORIZONTE)
    if v_out is None or v_out["open"] <= 0:
        return {"estado": "no_evaluable", "motivo": "vela_salida_ausente",
                "bloques": BLOQUES}
    signo = 1.0 if direccion == "LONG" else -1.0
    bruto = signo * (v_out["open"] / v_in["open"] - 1.0) * 1e4
    return {
        "estado": "evaluable", "bloques": BLOQUES,
        "extension": extension,
        "grupo": "EXTENDIDO" if extension > UMBRAL else "NORMAL",
        "retorno_bruto": bruto, "retorno_neto": bruto - COSTE,
    }


def main(argv):
    if len(argv) != 2:
        print("uso: verificar_extension_previa_v1.py <resumen.json>")
        return 2
    publicado = json.load(io.open(argv[1], encoding="utf-8"))
    primaria = publicado["primaria_solo_precio"]

    det_eval = {(d["symbol"], d["direccion"], d["cut_ms"]): d
                for d in primaria["detalle"]}
    det_no = {(d["symbol"], d["direccion"], d["cut_ms"]): d
              for d in primaria["detalle_no_evaluables"]}

    mis_evaluables = []
    por_captura = {}
    for db, run_id in CAPTURAS:
        if not Path(db).exists():
            check(False, f"captura_presente:{run_id}", "no existe research.db")
            continue
        filas = leer(db)
        al = alertas_solo_precio(filas)
        eps = agrupar(al)
        por_captura[run_id] = {"alertas": len(al), "episodios": len(eps)}
        check(len(al) == publicado["capturas"].get(run_id, {}).get("alertas_solo_precio_brutas", -1),
              f"alertas:{run_id}", f"{len(al)} != publicado")
        check(len(eps) == publicado["capturas"].get(run_id, {}).get("episodios_solo_precio", -1),
              f"episodios:{run_id}", f"{len(eps)} != publicado")
        for ep in eps:
            r = evaluar(ep, filas)
            clave = (ep["symbol"], ep["direccion"], ep["cut"])
            if r["estado"] == "evaluable":
                check(clave in det_eval, f"evaluable_publicado:{clave}", "falta en el resumen")
                pub = det_eval.get(clave)
                if pub is not None:
                    check(igual(r["extension"], pub["extension"], 1e-9),
                          f"extension:{clave}", f"{r['extension']} != {pub['extension']}")
                    check(r["grupo"] == pub["grupo"], f"grupo:{clave}",
                          f"{r['grupo']} != {pub['grupo']}")
                    check(igual(r["retorno_neto"], pub["retorno_neto_bps"], 1e-9),
                          f"neto:{clave}", f"{r['retorno_neto']} != {pub['retorno_neto_bps']}")
                mis_evaluables.append({**ep, **r})
            else:
                check(clave in det_no, f"no_evaluable_publicado:{clave}", "falta en el resumen")
                pub = det_no.get(clave)
                if pub is not None:
                    check(r["motivo"] == pub["motivo"], f"motivo:{clave}",
                          f"{r['motivo']} != {pub['motivo']}")
                    check((r.get("detalle_motivo") or None) == (pub.get("detalle_motivo") or None),
                          f"detalle_motivo:{clave}",
                          f"{r.get('detalle_motivo')} != {pub.get('detalle_motivo')}")
                    check((r.get("bloques") or 0) == (pub.get("bloques_previos") or 0),
                          f"bloques:{clave}", f"{r.get('bloques')} != {pub.get('bloques_previos')}")

    check(len(mis_evaluables) == primaria["evaluables"],
          "total_evaluables", f"{len(mis_evaluables)} != {primaria['evaluables']}")
    check(sum(v["episodios"] for v in por_captura.values()) == primaria["episodios"],
          "total_episodios", f"{sum(v['episodios'] for v in por_captura.values())} != {primaria['episodios']}")

    ext = [e for e in mis_evaluables if e["grupo"] == "EXTENDIDO"]
    nor = [e for e in mis_evaluables if e["grupo"] == "NORMAL"]
    check(len(ext) == primaria["grupos"]["EXTENDIDO"]["episodios"], "n_extendido",
          f"{len(ext)} != {primaria['grupos']['EXTENDIDO']['episodios']}")
    check(len(nor) == primaria["grupos"]["NORMAL"]["episodios"], "n_normal",
          f"{len(nor)} != {primaria['grupos']['NORMAL']['episodios']}")

    net_ext = [e["retorno_neto"] for e in ext]
    net_nor = [e["retorno_neto"] for e in nor]
    for nombre, valores, pub in (
        ("ext", net_ext, primaria["grupos"]["EXTENDIDO"]),
        ("nor", net_nor, primaria["grupos"]["NORMAL"]),
    ):
        check(igual4(statistics.fmean(valores), pub["neto_medio_bps"]),
              f"media:{nombre}", f"{statistics.fmean(valores)} != {pub['neto_medio_bps']}")
        check(igual4(statistics.median(valores), pub["neto_mediano_bps"]),
              f"mediana:{nombre}", f"{statistics.median(valores)} != {pub['neto_mediano_bps']}")
        check(igual4(sum(valores), pub["neto_suma_bps"]),
              f"suma:{nombre}", f"{sum(valores)} != {pub['neto_suma_bps']}")

    check(igual4(statistics.fmean(net_nor) - statistics.fmean(net_ext),
                 primaria["diferencia_normal_menos_extendido"]["neto_medio_bps"]),
          "diferencia_media", "no coincide")
    check(igual4(statistics.median(net_nor) - statistics.median(net_ext),
                 primaria["diferencia_normal_menos_extendido"]["neto_mediano_bps"]),
          "diferencia_mediana", "no coincide")

    f = primaria["filtro_descarta_extendido"]
    check(f["descartados"] == len(ext), "filtro_descartados", f"{len(ext)} != {f['descartados']}")
    check(igual4(sum(x for x in net_ext if x < 0), f["perdidas_evitadas_bps"]),
          "perdidas_evitadas", "no coincide")
    check(igual4(sum(x for x in net_ext if x > 0), f["ganancias_dejadas_pasar_bps"]),
          "ganancias_dejadas", "no coincide")
    check(igual4(sum(net_ext), f["neto_del_filtro_bps"]), "neto_filtro", "no coincide")

    motivos = Counter(d["motivo"] for d in primaria["detalle_no_evaluables"])
    check(dict(motivos) == primaria["motivos_excluyentes"], "motivos",
          f"{dict(motivos)} != {primaria['motivos_excluyentes']}")

    c = primaria["criterio"]
    check(c["aplica"] is True, "criterio_aplica", "no aplica")
    if c["aplica"]:
        med_nor = statistics.median(net_nor)
        med_ext = statistics.median(net_ext)
        check(c["condiciones"]["1_mediana_normal_supera_extendido"] == (med_nor > med_ext),
              "cond1", "no coincide")
        check(c["condiciones"]["2_media_normal_supera_extendido"] ==
              (statistics.fmean(net_nor) > statistics.fmean(net_ext)), "cond2", "no coincide")
        esperado = "APORTA EVIDENCIA" if c["todas"] else "NO APORTA"
        check(primaria["veredicto"] == esperado, "veredicto", f"{primaria['veredicto']} != {esperado}")

    print(f"capturas: {json.dumps(por_captura, ensure_ascii=False)}")
    print(f"evaluables verificados: {len(mis_evaluables)}")
    print(f"comprobaciones: {checks} | fallos: {len(fallos)}")
    for fallo in fallos[:20]:
        print("  FALLO", fallo)
    return 0 if not fallos else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
