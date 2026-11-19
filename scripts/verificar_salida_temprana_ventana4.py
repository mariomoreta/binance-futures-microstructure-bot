# -*- coding: utf-8 -*-
"""Verificacion independiente de la salida temprana (ventana 4).

No importa el modulo evaluado ni los modulos del proyecto: solo stdlib. Vuelve a
leer las velas desde `consultas_klines.jsonl`, recalcula precios, retornos y
agregados, y contrasta el resumen publicado. Tambien comprueba los hashes de las
fuentes y la aritmetica del embudo.

Uso:
    python scripts/verificar_salida_temprana_ventana4.py \
        --resumen <C-resumen.json> --derivados <dir anclas_salida_temprana.jsonl> \
        --anclas-publicadas <episodios_referencia_universo_igual.jsonl> \
        --klines <consultas_klines.jsonl> --db <research.db> \
        --cobertura <cobertura.json> --anclas-cambios <anclas_cambios.jsonl>
"""

import argparse
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

VERSION_VERIFICACION = "verificacion-salida-temprana-v1"
VENTANA_MS = 60_000
HORIZONTE_MS = 5 * 60_000
COSTE_BPS = 16.0
MIN_PARES = 30
TOL = 1e-6

MOTIVOS_NO_EVALUABLE = {
    "resultado_original_no_resoluble",
    "hueco_antes_del_primer_cambio",
    "vela_salida_alternativa_ausente",
    "vela_salida_alternativa_contradictoria",
    "precio_salida_alternativa_no_positivo",
    "sin_velas_para_simbolo",
    "sin_bloques_relevantes",
}
VEREDICTOS = {"INSUFICIENTE", "MEJORA_EN_ESTA_MUESTRA",
              "EMPEORA_EN_ESTA_MUESTRA", "SIN_DIRECCION_CLARA"}


class Verificador(object):
    def __init__(self):
        self.checks = 0
        self.fallos = []

    def check(self, condicion, mensaje):
        self.checks += 1
        if not condicion:
            self.fallos.append(mensaje)

    def igual(self, obtenido, esperado, mensaje, tol=TOL):
        self.check(abs(float(obtenido) - float(esperado)) <= tol,
                   f"{mensaje}: {obtenido} != {esperado}")


def _sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _leer_jsonl(ruta):
    with io.open(ruta, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _cargar_velas(klines_ruta, run_id):
    """Aperturas definitivas por simbolo y minuto, sin usar el cargador del bot.

    Una instantanea es definitiva si se adquirio despues del cierre de la vela.
    Dos definitivas que discrepan en la apertura marcan la vela contradictoria.
    """
    aperturas = {}
    contradictorias = set()
    for consulta in _leer_jsonl(klines_ruta):
        if str(consulta.get("run_id")) != run_id:
            continue
        if "kline" not in str(consulta.get("kind", "")):
            continue
        if str(consulta.get("interval")) != "1m":
            continue
        if int(consulta.get("http_status", 0)) != 200:
            continue
        symbol = consulta["symbol"]
        adquirido = int(consulta["adquirido_ms"])
        for fila in json.loads(consulta["cuerpo"]):
            inicio = int(fila[0])
            cierre_ms = int(fila[6])
            if adquirido <= cierre_ms:
                continue
            apertura = float(fila[1])
            clave = (symbol, inicio)
            previa = aperturas.get(clave)
            if previa is None:
                aperturas[clave] = apertura
            elif abs(previa - apertura) > 1e-12:
                contradictorias.add(clave)
    return aperturas, contradictorias


def _media(valores):
    return sum(valores) / len(valores) if valores else None


def _mediana(valores):
    if not valores:
        return None
    orden = sorted(valores)
    n = len(orden)
    if n % 2:
        return orden[n // 2]
    return (orden[n // 2 - 1] + orden[n // 2]) / 2.0


def _referencia_entrada(ms):
    return (int(ms) // VENTANA_MS + 1) * VENTANA_MS


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--resumen", required=True)
    ap.add_argument("--derivados", required=True)
    ap.add_argument("--anclas-publicadas", required=True)
    ap.add_argument("--klines", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--cobertura", required=True)
    ap.add_argument("--anclas-cambios", required=True)
    args = ap.parse_args(argv)

    v = Verificador()
    resumen = json.load(io.open(args.resumen, encoding="utf-8"))
    fichas = _leer_jsonl(Path(args.derivados) / "anclas_salida_temprana.jsonl")
    publicadas = _leer_jsonl(args.anclas_publicadas)
    cambios = _leer_jsonl(args.anclas_cambios)

    v.check(resumen.get("version") == "salida-temprana-v1",
            "version del resumen inesperada")
    v.check(len(fichas) == 143, f"fichas {len(fichas)} != 143")
    v.check(len(publicadas) == 143, "anclas publicadas != 143")
    v.check(len(cambios) == 143, "anclas_cambios != 143")

    # --- Universo: las 4 del patron dentro de las 143, sin duplicar ---------
    ternas = [f["terna"] for f in fichas]
    v.check(len(set(ternas)) == 143, "ternas duplicadas en el derivado")
    patron = [f for f in fichas if f["ancla_patron"]]
    v.check(len(patron) == 4, f"anclas del patron {len(patron)} != 4")
    pub_patron = {p["terna"] for p in publicadas if p["ancla_patron"]}
    v.check({f["terna"] for f in patron} == pub_patron,
            "las 4 anclas del patron no coinciden con las publicadas")
    v.check(resumen["embudo"]["anclas_patron"] == 4,
            "el resumen no declara 4 anclas del patron")

    # --- Aritmetica del embudo --------------------------------------------
    e = resumen["embudo"]
    v.check(e["anclas"] == e["original_resoluble"] + e["original_no_resoluble"],
            "embudo: anclas != resoluble + no resoluble")
    v.check(e["anclas"] == (e["adelantada_resoluble"] + e["original_conservada"]
                            + e["no_evaluable"]),
            "embudo: estados no suman las anclas")
    v.check(e["pares_evaluables"] == (e["adelantada_resoluble"]
                                      + e["original_conservada"]),
            "embudo: pares evaluables incoherentes")
    v.check(e["pares_con_salida_adelantada"] == e["adelantada_resoluble"],
            "embudo: pares adelantados incoherentes")
    v.check(sum(e["motivos"].values()) == e["no_evaluable"],
            "embudo: motivos no suman los no evaluables")
    v.check(e["cambios_disponibles_antes_de_la_entrada"] == 0,
            "hay cambios disponibles antes de la entrada (look-ahead)")
    v.check(sum(e["cambios_por_bloque"].values()) == e["adelantada_resoluble"],
            "embudo: cambios por bloque no suman")

    # --- Velas independientes ---------------------------------------------
    aperturas, contradictorias = _cargar_velas(args.klines, resumen["run_id"])
    v.check(len(aperturas) > 0, "no se leyeron velas")

    por_terna = {p["terna"]: p for p in publicadas}
    adelantadas = [f for f in fichas if f["estado"] == "adelantada_resoluble"]
    deltas = []
    for f in fichas:
        v.check(f["estado"] in ("adelantada_resoluble", "original_conservada",
                                "no_evaluable"),
                f"estado desconocido en {f['terna']}: {f['estado']}")
        v.check(f["salida_original_ms"] == f["entrada_ms"] + HORIZONTE_MS,
                f"salida original no es entrada+5min en {f['terna']}")
        v.check(f["entrada_ms"] == _referencia_entrada(f["cut_ms"]),
                f"entrada no es el primer minuto tras el corte en {f['terna']}")

        p = por_terna.get(f["terna"])
        v.check(p is not None, f"ancla no publicada: {f['terna']}")
        if p is not None:
            v.check(p["estado"] == f["original_estado"],
                    f"estado original distinto en {f['terna']}")
            v.check(p["symbol"] == f["symbol"]
                    and p["direccion"] == f["direccion"],
                    f"contrato/direccion distintos en {f['terna']}")
            if p["estado"] == "resoluble":
                v.igual(p["retorno_bps"], f["retorno_original_bps"],
                        f"retorno original distinto en {f['terna']}", 1e-3)

        if f["estado"] == "no_evaluable":
            v.check(f["motivo"] in MOTIVOS_NO_EVALUABLE,
                    f"motivo no evaluable desconocido en {f['terna']}")
            v.check(f["delta_bps"] is None,
                    f"no evaluable con delta en {f['terna']}")
            if f["motivo"] == "hueco_antes_del_primer_cambio":
                v.check(0 <= int(f["hueco_k"]) <= 3,
                        f"hueco fuera de b_0..b_3 en {f['terna']}")
            continue

        if f["estado"] == "original_conservada":
            v.check(f["delta_bps"] is None,
                    f"conservada con delta en {f['terna']}")
            continue

        # adelantada resoluble
        v.check(f["salida_alternativa_ms"] < f["salida_original_ms"],
                f"salida no adelantada en {f['terna']}")
        v.check(f["disponibilidad_ms"] > f["entrada_ms"],
                f"cambio no posterior a la entrada en {f['terna']}")
        v.check(f["salida_alternativa_ms"]
                == _referencia_entrada(f["disponibilidad_ms"]),
                f"salida no es el primer minuto tras la disponibilidad en "
                f"{f['terna']}")
        v.check(f["minutos_adelanto"] == (
            f["salida_original_ms"] - f["salida_alternativa_ms"]) // VENTANA_MS,
            f"minutos de adelanto incoherentes en {f['terna']}")

        clave_e = (f["symbol"], f["entrada_ms"])
        clave_a = (f["symbol"], f["salida_alternativa_ms"])
        clave_o = (f["symbol"], f["salida_original_ms"])
        for clave, etiqueta in ((clave_e, "entrada"), (clave_a, "alternativa"),
                                (clave_o, "original")):
            v.check(clave in aperturas,
                    f"vela {etiqueta} ausente en {f['terna']}")
            v.check(clave not in contradictorias,
                    f"vela {etiqueta} contradictoria en {f['terna']}")
        if clave_e in aperturas and clave_a in aperturas and clave_o in aperturas:
            entrada = aperturas[clave_e]
            alt = aperturas[clave_a]
            orig = aperturas[clave_o]
            v.igual(entrada, f["precio_entrada"],
                    f"precio de entrada distinto en {f['terna']}", 1e-12)
            v.igual(alt, f["precio_salida_alternativa"],
                    f"precio alternativo distinto en {f['terna']}", 1e-12)
            v.igual(orig, f["precio_salida_original"],
                    f"precio original distinto en {f['terna']}", 1e-12)
            signo = 1.0 if f["direccion"] == "LONG" else -1.0
            ret_orig = signo * (orig / entrada - 1.0) * 1e4
            ret_alt = signo * (alt / entrada - 1.0) * 1e4
            v.igual(ret_orig, f["retorno_original_bps"],
                    f"retorno original recalculado en {f['terna']}", 1e-6)
            v.igual(ret_alt, f["retorno_alternativo_bps"],
                    f"retorno alternativo recalculado en {f['terna']}", 1e-6)
            v.igual(ret_alt - ret_orig, f["delta_bps"],
                    f"delta recalculado en {f['terna']}", 1e-6)
            deltas.append(ret_alt - ret_orig)

    # --- Agregados ---------------------------------------------------------
    v.check(len(deltas) == e["adelantada_resoluble"],
            "deltas recalculados != adelantadas")
    pa = resumen["pares_adelantados"]
    if deltas:
        v.igual(_media(deltas), pa["media_bps"], "media del delta", 1e-4)
        v.igual(_mediana(deltas), pa["mediana_bps"], "mediana del delta", 1e-4)
        v.igual(sum(deltas), pa["suma_bps"], "suma del delta", 1e-4)
        v.check(pa["mejoran"] == sum(1 for d in deltas if d > 1e-9),
                "contador de mejoras")
        v.check(pa["empeoran"] == sum(1 for d in deltas if d < -1e-9),
                "contador de empeoramientos")
        v.check(pa["iguales"] == sum(1 for d in deltas if abs(d) <= 1e-9),
                "contador de iguales")

    cubos = (pa["perdidas_recortadas"]["suma_bps"]
             + pa["ganancias_sacrificadas"]["suma_bps"]
             + pa["perdidas_empeoradas"]["suma_bps"]
             + pa["ganancias_extra"]["suma_bps"]
             + pa["original_neutro"]["suma_bps"])
    v.igual(cubos, pa["suma_bps"], "descomposicion de perdidas y ganancias",
            1e-4)
    v.check(pa["perdidas_recortadas"]["n"] + pa["ganancias_sacrificadas"]["n"]
            + pa["perdidas_empeoradas"]["n"] + pa["ganancias_extra"]["n"]
            + pa["original_neutro"]["n"] + pa["iguales"] == pa["n"],
            "los cubos no cubren todos los pares")

    # Por direccion
    for d in ("LONG", "SHORT"):
        grupo = [f["delta_bps"] for f in adelantadas if f["direccion"] == d]
        esperado = resumen["por_direccion_adelantados"][d]
        v.check(esperado["n"] == len(grupo), f"n por direccion {d}")
        if grupo:
            v.igual(_media(grupo), esperado["media_bps"],
                    f"media por direccion {d}", 1e-4)
            v.igual(_mediana(grupo), esperado["mediana_bps"],
                    f"mediana por direccion {d}", 1e-4)
    v.check(sum(resumen["por_direccion_adelantados"][d]["n"]
                for d in ("LONG", "SHORT")) == len(adelantadas),
            "las direcciones no suman las adelantadas")

    # Por tipo
    tipos = Counter(f["primer_cambio_tipo"] for f in adelantadas)
    v.check(set(tipos) == set(resumen["por_tipo_adelantados"]),
            "tipos del resumen distintos de los del derivado")
    for tipo, n in tipos.items():
        v.check(resumen["por_tipo_adelantados"][tipo]["n"] == n,
                f"n del tipo {tipo}")
    v.check(sum(tipos.values()) == len(adelantadas),
            "los tipos no suman las adelantadas")

    # Coste 16 bps igual en ambos lados: el delta no cambia
    niveles = resumen["niveles_adelantados"]
    v.igual(niveles["delta_media_bps"], pa["media_bps"],
            "el delta cambia con el coste igual", 1e-4)
    v.igual(niveles["original_neto_media_bps"],
            niveles["original_bruto_media_bps"] - COSTE_BPS,
            "nivel neto original", 1e-4)
    v.igual(niveles["alternativa_neto_media_bps"],
            niveles["alternativa_bruto_media_bps"] - COSTE_BPS,
            "nivel neto alternativo", 1e-4)

    # Veredicto
    n = pa["n"]
    if n < MIN_PARES:
        v.check(resumen["veredicto"]["veredicto"] == "INSUFICIENTE",
                "menos de 30 pares deberia ser INSUFICIENTE")
    v.check(resumen["veredicto"]["veredicto"] in VEREDICTOS,
            "veredicto desconocido")
    v.check(resumen["veredicto"]["pares_adelantados"] == n,
            "pares del veredicto incoherentes")

    # --- Hashes de las fuentes --------------------------------------------
    hashes = resumen["origen"]["hashes"]
    v.check(resumen["origen"]["fuentes_intactas"] is True,
            "el resumen no declara fuentes intactas")
    for clave, ruta in (("research.db", args.db),
                        ("cobertura_json", args.cobertura),
                        ("consultas_klines.jsonl", args.klines),
                        ("anclas_cambios.jsonl", args.anclas_cambios),
                        ("episodios_referencia_universo_igual.jsonl",
                         args.anclas_publicadas)):
        v.check(_sha256(ruta) == hashes.get(clave),
                f"hash distinto de {clave}")

    print(f"version={VERSION_VERIFICACION}")
    print(f"checks={v.checks} fallos={len(v.fallos)}")
    for fallo in v.fallos[:40]:
        print("FALLO:", fallo)
    print("RESULTADO:", "OK" if not v.fallos else "FALLOS")
    return 0 if not v.fallos else 1


if __name__ == "__main__":
    sys.exit(main())
