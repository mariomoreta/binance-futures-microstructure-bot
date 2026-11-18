# -*- coding: utf-8 -*-
"""Verificacion independiente del diagnostico de los cuatro casos.

No importa el modulo diagnosticado: recalcula desde los derivados publicados,
las velas y los hashes, y compara con `C-resumen.json`.

Comprueba:
  1. las fuentes conservan el SHA256 registrado (db, cobertura, klines,
     episodios publicados);
  2. los agregados de los 143 controles se reproducen desde
     `anclas_diagnostico.jsonl` (pares, media/mediana del delta, clasificacion,
     subconjunto de reversion y extension previa);
  3. los cuatro casos se reproducen desde las velas originales (retorno
     original, continuacion tardia y reversion tardia);
  4. la reversion tardia es exactamente el negativo de la continuacion tardia
     (misma entrada y misma salida) y no reutiliza la entrada original;
  5. los cuatro casos coinciden con el derivado publicado del patron.

Uso:
  python docs/evidence/diagnostico-cuatro-casos-ventana4-20261118/D-verificacion.py \
    --resumen docs/evidence/diagnostico-cuatro-casos-ventana4-20261118/C-resumen.json \
    --derivados C:/proyectos/binance-futures-data/exp-v2-ventana-4-20261116a-diagnostico-cuatro-casos-v1
"""

import argparse
import hashlib
import io
import json
import statistics
from collections import Counter
from pathlib import Path

TOL = 1e-3


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def leer_jsonl(ruta):
    with io.open(ruta, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def cargar_velas(ruta):
    velas = {}
    with io.open(ruta, encoding="utf-8") as f:
        for linea in f:
            q = json.loads(linea)
            if q.get("kind") != "consulta_klines_trayectoria":
                continue
            if q.get("http_status") != 200:
                continue
            symbol = q["symbol"]
            for c in json.loads(q["cuerpo"]):
                velas.setdefault(symbol, {})[int(c[0])] = {
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                }
    return velas


def retorno(velas, symbol, entrada_ms, salida_ms, direccion):
    e = velas[symbol][int(entrada_ms)]["open"]
    s = velas[symbol][int(salida_ms)]["open"]
    signo = 1.0 if direccion == "LONG" else -1.0
    return round(signo * (s / e - 1.0) * 1e4, 4)


def aprox(a, b, tol=TOL):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resumen", required=True)
    ap.add_argument("--derivados", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--cobertura", required=True)
    ap.add_argument("--klines", required=True)
    ap.add_argument("--anclas-publicadas", required=True)
    ap.add_argument("--patron-publicado", required=True)
    args = ap.parse_args()

    resumen = json.load(io.open(args.resumen, encoding="utf-8"))
    derivados = Path(args.derivados)
    anclas = leer_jsonl(derivados / "anclas_diagnostico.jsonl")
    casos = leer_jsonl(derivados / "casos_detalle.jsonl")
    velas = cargar_velas(args.klines)

    fallos = []

    def check(nombre, ok, detalle=""):
        print(("OK   " if ok else "FALLO") + "  " + nombre + ("  " + detalle if detalle else ""))
        if not ok:
            fallos.append(nombre)

    # 1. Fuentes intactas
    hashes = {
        "research.db": sha256(args.db),
        "cobertura_json": sha256(args.cobertura),
        "consultas_klines.jsonl": sha256(args.klines),
        "episodios_patron_originales.jsonl": sha256(args.patron_publicado),
        "episodios_referencia_universo_igual.jsonl": sha256(args.anclas_publicadas),
    }
    check("fuentes con el SHA256 registrado", hashes == resumen["origen"]["hashes_despues"])
    check("fuentes intactas durante el diagnostico", resumen["origen"]["fuentes_intactas"] is True)

    # 2. Agregados de los 143 controles
    todas = resumen["controles"]["todas"]
    check("143 anclas en el derivado", len(anclas) == 143, f"n={len(anclas)}")

    pares = [r for r in anclas
             if r["original"]["estado"] == "resoluble"
             and r["tardia"]["estado"] == "resoluble"
             and r["tardia"]["continuacion_bps"] is not None]
    deltas = [r["tardia"]["continuacion_bps"] - r["original"]["retorno_bps"] for r in pares]
    check("pares comparables", len(pares) == todas["pares_comparables"],
          f"{len(pares)} vs {todas['pares_comparables']}")
    check("delta medio", aprox(statistics.fmean(deltas), todas["delta_media_bps"]),
          f"{round(statistics.fmean(deltas), 4)} vs {todas['delta_media_bps']}")
    check("delta mediano", aprox(statistics.median(deltas), todas["delta_mediana_bps"]),
          f"{round(statistics.median(deltas), 4)} vs {todas['delta_mediana_bps']}")

    clasif = Counter(r["espera"]["clasificacion"] for r in anclas
                     if r["espera"]["estado"] == "resoluble")
    check("clasificacion del flujo", dict(clasif) == todas["clasificacion"],
          str(dict(clasif)))

    reversion = [r for r in anclas
                 if r["espera"]["estado"] == "resoluble"
                 and r["tardia"]["estado"] == "resoluble"
                 and r["espera"]["clasificacion"] == "candidato_a_reversion"]
    cont = [r["tardia"]["continuacion_bps"] for r in reversion]
    rev = [r["tardia"]["reversion_bps"] for r in reversion]
    check("subconjunto de reversion: n", len(reversion) == todas["reversion"]["n"],
          f"{len(reversion)} vs {todas['reversion']['n']}")
    check("subconjunto de reversion: continuacion media",
          aprox(statistics.fmean(cont), todas["reversion"]["continuacion_media_bps"]))
    check("subconjunto de reversion: reversion = -continuacion",
          all(aprox(r["tardia"]["reversion_bps"], -r["tardia"]["continuacion_bps"], 1e-6)
              for r in reversion))

    evaluables = [r for r in anclas if r["extension_previa"]["estado"] == "resoluble"]
    check("extension previa evaluable", len(evaluables) == resumen["controles"]["extension_previa"]["evaluables"],
          f"{len(evaluables)} vs {resumen['controles']['extension_previa']['evaluables']}")
    check("extension previa: minimo 6 ternas previas",
          all(r["extension_previa"]["ternas_previas_no_solapadas"] >= 6 for r in evaluables))
    check("extension previa: historia insuficiente por debajo del minimo",
          all(r["extension_previa"]["ternas_previas_no_solapadas"] < 6
              for r in anclas
              if r["extension_previa"]["motivo"] == "historia_insuficiente"))

    # 3. Los cuatro casos desde las velas
    check("cuatro casos en el derivado", len(casos) == 4, f"n={len(casos)}")
    for c in casos:
        symbol = c["symbol"]
        direccion = c["direccion"]
        original = retorno(velas, symbol, c["original"]["entrada_ms"],
                           c["original"]["salida_ms"], direccion)
        check(f"{symbol} {direccion} retorno original",
              aprox(original, c["original"]["retorno_bps"]),
              f"{original} vs {c['original']['retorno_bps']}")
        if c["tardia"]["estado"] == "resoluble":
            tardia = retorno(velas, symbol, c["tardia"]["entrada_ms"],
                             c["tardia"]["salida_ms"], direccion)
            inversa = retorno(velas, symbol, c["tardia"]["entrada_ms"],
                              c["tardia"]["salida_ms"],
                              "SHORT" if direccion == "LONG" else "LONG")
            check(f"{symbol} {direccion} continuacion tardia",
                  aprox(tardia, c["tardia"]["continuacion_bps"]),
                  f"{tardia} vs {c['tardia']['continuacion_bps']}")
            check(f"{symbol} {direccion} reversion tardia",
                  aprox(inversa, c["tardia"]["reversion_bps"]),
                  f"{inversa} vs {c['tardia']['reversion_bps']}")
            check(f"{symbol} {direccion} reversion no reutiliza entrada original",
                  c["tardia"]["reutiliza_entrada_original"] is False)
        else:
            check(f"{symbol} {direccion} espera no resoluble sin inventar precios",
                  c["tardia"]["continuacion_bps"] is None
                  and c["tardia"]["estado"] == "no_resoluble",
                  c["espera"]["motivo"] or "")

    # 4. Ningun caso con espera desplazada reutiliza la entrada original
    desplazados = [r for r in anclas
                   if r["espera"]["estado"] == "resoluble"
                   and r["espera"]["desplazamiento_ms"] == 60000
                   and r["tardia"]["estado"] == "resoluble"]
    check("espera desplaza la entrada en todos los casos usables",
          len(desplazados) == todas["tardia_resolubles"],
          f"{len(desplazados)} vs {todas['tardia_resolubles']}")
    check("ninguna entrada tardia reutiliza la original",
          all(r["tardia"]["reutiliza_entrada_original"] is False for r in desplazados))

    # 5. Los cuatro casos coinciden con lo publicado
    publicados = leer_jsonl(args.patron_publicado)
    por_terna = {p["terna"]: p for p in publicados}
    ok_publicado = True
    for c in casos:
        p = por_terna.get(c["terna"])
        if (p is None or p["symbol"] != c["symbol"]
                or p["direccion"] != c["direccion"]
                or int(p["cut_ms"]) != int(c["cut_ms"])
                or p["estado"] != c["original"]["estado"]
                or not aprox(p.get("retorno_bps"), c["original"]["retorno_bps"])):
            ok_publicado = False
    check("los cuatro casos coinciden con el derivado publicado", ok_publicado)

    print()
    if fallos:
        print(f"VERIFICACION FALLIDA: {len(fallos)} comprobaciones")
        return 1
    print("VERIFICACION OK: todas las comprobaciones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
