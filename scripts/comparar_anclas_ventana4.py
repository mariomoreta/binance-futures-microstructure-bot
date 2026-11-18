# -*- coding: utf-8 -*-
"""Comparacion en condiciones iguales: filtro de flujo/profundidad vs solo precio.

Pregunta: sobre las MISMAS 501 ternas acreditadas de la ventana 4 y con la MISMA
informacion disponible al decidir (mismo corte causal), que episodios retiene
el patron SECUENCIA-PRESION-V1 frente a la regla de solo precio, y que paso
despues.

Reglas fijadas:
  - Mismo universo: las 501 ternas acreditadas. La referencia de solo precio NO
    puede incorporar ternas de fuera de ese universo ni evaluar antes del corte.
  - Mismo reloj: corte = max(cierre nominal de la tercera ventana, disponibilidad
    de las tres ventanas). Identico en ambos metodos.
  - Referencia de solo precio: solo exige tres cierres estrictamente ascendentes
    (LONG) o descendentes (SHORT).
  - Agrupacion de episodios ya publicada: primera alerta por contrato+dir;
    repetidas con corte dentro de los 5 minutos siguientes. El ancla del episodio
    es la primera alerta y NO se reclasifica si una alerta del patron aparece
    despues dentro del episodio: se registra aparte como tardia, con su propio
    corte y su propio resultado.
  - Medicion identica: entrada = apertura del primer minuto estrictamente
    posterior al corte; salida = apertura exactamente 5 minutos despues; solo
    velas originales; si falta la vela exacta o hay contradiccion, el episodio
    queda no resoluble con motivo. Retorno bruto, no P&L.

Solo lectura sobre la captura. Sin Binance, sin capturas nuevas, sin cambios de
patron, umbrales ni estrategia.
"""

import argparse
import io
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secuencia_presion_v1 import _evaluar_terna  # noqa: E402
from replay_patron_ventana4 import (  # noqa: E402
    GRUPO_REPETICION_MS,
    MIN_EPISODIOS,
    _redondear,
    _resumen_grupo,
    _sha256_archivo,
    agrupar_episodios,
    alertas_patron,
    cargar_cobertura,
    cargar_velas,
    construir_ventanas,
    evaluar_detector,
    resumir_episodios,
    resolver_alerta,
    verificar_universo,
)

VERSION_COMPARACION = "anclas-comunes-ventana4-v1"
VERSION_REFERENCIA_PUBLICADA = "patron-ventana4-v1"
DECISIONES_PATRON = ("LONG_EXPERIMENTAL", "SHORT_EXPERIMENTAL")


# ---------------------------------------------------------------------------
# Universo y corte unicos
# ---------------------------------------------------------------------------

def corte_de_terna(a: Any, b: Any, c: Any) -> int:
    """Corte causal unico para ambos metodos.

    Maximo entre el cierre nominal de la tercera ventana y la disponibilidad de
    las tres ventanas. Es exactamente la formula ya usada por el detector.
    """
    fin = int(c.ventana_fin_ms)
    disponibilidades = [
        int(v.disponibilidad_ms)
        for v in (a, b, c)
        if v.disponibilidad_ms is not None
    ]
    if len(disponibilidades) != 3:
        raise SystemExit(f"ternas sin disponibilidad completa en {c.observation_id}")
    return max([fin] + disponibilidades)


def _direccion_por_cierres(p1: float, p2: float, p3: float) -> Optional[str]:
    if p1 < p2 < p3:
        return "LONG"
    if p1 > p2 > p3:
        return "SHORT"
    return None


def construir_alertas_referencia(
    ternas_detalle: List[Dict[str, Any]],
    por_symbol: Dict[str, List[Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Alertas de solo precio sobre EXACTAMENTE las ternas recibidas.

    No recorre ventanas por su cuenta: itera las filas publicadas por el replay
    (una por terna acreditada) y exige que el corte recalculado coincida con el
    del detector. Cualquier discrepancia aborta.
    """
    indice = {
        symbol: {int(v.ventana_inicio_ms): v for v in ventanas}
        for symbol, ventanas in por_symbol.items()
    }
    alertas: List[Dict[str, Any]] = []
    audit = Counter()
    for fila in ternas_detalle:
        symbol = fila["symbol"]
        inicios = [int(x) for x in fila["ventanas"]]
        if len(inicios) != 3:
            raise SystemExit(f"terna sin tres ventanas: {fila['terna']}")
        try:
            a, b, c = (indice[symbol][i] for i in inicios)
        except KeyError as exc:
            raise SystemExit(f"ventana inexistente en {fila['terna']}: {exc}") from exc

        corte = corte_de_terna(a, b, c)
        if corte != int(fila["cut_ms"]):
            raise SystemExit(
                f"corte distinto entre metodos en {fila['terna']}: "
                f"detector={fila['cut_ms']} referencia={corte}"
            )
        audit["ternas_recibidas"] += 1
        audit["cortes_verificados"] += 1

        direccion = _direccion_por_cierres(
            float(a.precio_cierre), float(b.precio_cierre), float(c.precio_cierre)
        )
        if direccion is None:
            audit["ternas_no_monotonas"] += 1
            continue
        audit["ternas_monotonas"] += 1

        es_patron = (
            fila["decision"] in DECISIONES_PATRON
            and fila["direccion"] == direccion
        )
        evaluacion = _evaluar_terna(a, b, c, direccion)
        if bool(evaluacion["cumple"]) != bool(es_patron):
            raise SystemExit(
                f"clasificacion de patron incoherente en {fila['terna']} "
                f"{direccion}: detector={es_patron} evaluacion={evaluacion['cumple']}"
            )

        alertas.append({
            "symbol": symbol,
            "direccion": direccion,
            "terna": fila["terna"],
            "cut_ms": corte,
            "cut_iso": fila["cut_iso"],
            "cierre_nominal_ms": int(fila["cierre_nominal_ms"]),
            "demora_corte_ms": corte - int(fila["cierre_nominal_ms"]),
            "decision": fila["decision"],
            "origen": "solo_precio_universo_igual",
            "tambien_patron": bool(es_patron),
            "corte_coincide_con_detector": True,
        })
        audit[f"alertas_{direccion.lower()}"] += 1
        audit["alertas_con_patron"] += int(es_patron)

    alertas.sort(key=lambda a: (a["cut_ms"], a["symbol"], a["direccion"], a["terna"]))
    audit["alertas_brutas"] = len(alertas)
    audit["ternas_fuera_del_universo"] = 0
    return alertas, dict(audit)


# ---------------------------------------------------------------------------
# Episodios: ancla congelada y alertas tardias
# ---------------------------------------------------------------------------

def agrupar_con_tardias(
    alertas: List[Dict[str, Any]],
    alertas_patron_lista: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Agrupa la referencia y adjunta alertas del patron posteriores al ancla.

    El ancla es la primera alerta del episodio y conserva su clasificacion
    (con o sin patron) en ese instante. Las alertas del patron que caen despues
    dentro del episodio se registran aparte y NO cambian el ancla ni heredan el
    retorno de la entrada anterior.
    """
    episodios = agrupar_episodios(alertas)
    por_terna_patron = {a["terna"]: a for a in alertas_patron_lista}
    if len(por_terna_patron) != len(alertas_patron_lista):
        raise SystemExit("alertas del patron duplicadas por terna")

    audit = Counter()
    for e in episodios:
        e["ancla_patron"] = bool(e.get("tambien_patron"))
        e["tardias"] = []
        for terna in list(e["repetidas"]):
            p = por_terna_patron.get(terna)
            if p is None:
                continue
            if p["symbol"] != e["symbol"] or p["direccion"] != e["direccion"]:
                raise SystemExit(f"alerta tardia incoherente en {terna}")
            if not (e["cut_ms"] <= p["cut_ms"] < e["cut_ms"] + GRUPO_REPETICION_MS):
                raise SystemExit(f"alerta del patron fuera de la ventana del episodio: {terna}")
            e["tardias"].append({
                "terna": terna,
                "cut_ms": p["cut_ms"],
                "cut_iso": p["cut_iso"],
                "cierre_nominal_ms": p["cierre_nominal_ms"],
                "demora_corte_ms": p["demora_corte_ms"],
                "decision": p["decision"],
            })
        audit["anclas_con_patron"] += int(e["ancla_patron"])
        audit["anclas_sin_patron"] += int(not e["ancla_patron"])
        audit["alertas_tardias"] += len(e["tardias"])
        audit["repetidas_agrupadas"] += len(e["repetidas"])

    # Toda alerta del patron debe ser ancla de un episodio o tardia en uno.
    anclas = {e["terna"] for e in episodios if e["ancla_patron"]}
    tardias = {t["terna"] for e in episodios for t in e["tardias"]}
    if anclas & tardias:
        raise SystemExit("una alerta del patron es ancla y tardia a la vez")
    if anclas | tardias != set(por_terna_patron):
        raise SystemExit(
            "alertas del patron sin asignar: "
            f"anclas={sorted(anclas)} tardias={sorted(tardias)} "
            f"patron={sorted(por_terna_patron)}"
        )
    audit["alertas_patron_asignadas"] = len(anclas | tardias)
    return episodios, dict(audit)


def mapear_episodios_patron(
    episodios_patron: List[Dict[str, Any]],
    episodios_referencia: List[Dict[str, Any]],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Explica cada episodio original del patron frente a las anclas comunes."""
    ancla_por_terna = {(e["symbol"], e["direccion"], e["terna"]): e
                       for e in episodios_referencia}
    absorbente_por_terna = {}
    for e in episodios_referencia:
        for terna in e["repetidas"]:
            absorbente_por_terna.setdefault((e["symbol"], e["direccion"], terna), e)

    filas = []
    for ep in episodios_patron:
        clave = (ep["symbol"], ep["direccion"], ep["terna"])
        resultado = resolver_alerta(ep, velas)
        fila = {
            "symbol": ep["symbol"],
            "direccion": ep["direccion"],
            "terna": ep["terna"],
            "cut_ms": ep["cut_ms"],
            "cut_iso": ep["cut_iso"],
            "demora_corte_ms": ep["demora_corte_ms"],
            "estado": resultado.get("estado"),
            "motivo": resultado.get("motivo"),
            "retorno_bps": _redondear(resultado.get("retorno_bps")),
            "coincide_con_ancla_comun": clave in ancla_por_terna,
            "motivo_coincidencia": None,
            "episodio_absorbente": None,
        }
        if clave in ancla_por_terna:
            fila["motivo_coincidencia"] = "ancla_comun"
            fila["episodio_absorbente"] = {
                "terna": ep["terna"],
                "cut_ms": ep["cut_ms"],
                "cut_iso": ep["cut_iso"],
            }
        else:
            absorbente = absorbente_por_terna.get(clave)
            fila["motivo_coincidencia"] = (
                "absorbida_por_ancla_anterior" if absorbente else "sin_ancla_comun"
            )
            if absorbente is not None:
                fila["episodio_absorbente"] = {
                    "terna": absorbente["terna"],
                    "cut_ms": absorbente["cut_ms"],
                    "cut_iso": absorbente["cut_iso"],
                    "symbol": absorbente["symbol"],
                    "direccion": absorbente["direccion"],
                }
        filas.append(fila)
    return filas


def resumen_tardias(
    episodios: List[Dict[str, Any]],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
) -> Dict[str, Any]:
    """Resultado propio de cada alerta tardia, sin mezclarla con el ancla."""
    pseudo = []
    for e in episodios:
        for t in e["tardias"]:
            pseudo.append({
                "symbol": e["symbol"],
                "direccion": e["direccion"],
                "terna": t["terna"],
                "cut_ms": t["cut_ms"],
                "cut_iso": t["cut_iso"],
                "cierre_nominal_ms": t["cierre_nominal_ms"],
                "demora_corte_ms": t["demora_corte_ms"],
                "decision": t["decision"],
                "repetidas": [],
            })
    r = resumir_episodios(pseudo, velas)
    detalle = r.pop("detalle")
    return {**r, "detalle": detalle}


# ---------------------------------------------------------------------------
# Conclusion con la regla ya fijada
# ---------------------------------------------------------------------------

def concluir_anclas(
    con_patron: Dict[str, Any],
    sin_patron: Dict[str, Any],
    detalle_sin_patron: List[Dict[str, Any]],
    reduccion: Dict[str, Any],
) -> Dict[str, Any]:
    n_con = int(con_patron["resolubles"])
    n_sin = int(sin_patron["resolubles"])
    base = {
        "minimo_episodios_resolubles": MIN_EPISODIOS,
        "episodios_resolubles_con_patron": n_con,
        "episodios_resolubles_sin_patron": n_sin,
        "reduccion_oportunidades": reduccion,
    }
    if n_con < MIN_EPISODIOS or n_sin < MIN_EPISODIOS:
        return {
            **base,
            "conclusion": "datos insuficientes",
            "motivo": (
                "anclas resolubles con patron="
                f"{n_con}, sin patron={n_sin}; minimo fijado={MIN_EPISODIOS}"
            ),
            "evidencia": [],
        }
    media_con = con_patron["retorno_medio_bps"]
    media_sin = sin_patron["retorno_medio_bps"]
    mediana_con = con_patron["retorno_mediano_bps"]
    mediana_sin = sin_patron["retorno_mediano_bps"]
    evidencia = [
        f"media con patron {media_con} bps vs sin patron {media_sin} bps",
        f"mediana con patron {mediana_con} bps vs sin patron {mediana_sin} bps",
    ]
    dominante = con_patron["simbolo_dominante"]["symbol"]
    if dominante:
        valores = [e["retorno_bps"] for e in detalle_sin_patron
                   if e["estado"] == "resoluble" and e["symbol"] != dominante]
        media_robusta = _redondear(sum(valores) / len(valores)) if valores else None
        evidencia.append(
            f"media con patron sin {dominante}: {media_robusta} bps vs sin patron {media_sin} bps"
        )
        robusta = (media_robusta is not None and media_sin is not None
                   and media_robusta > media_sin)
    else:
        robusta = False
    mejora = (media_con is not None and media_sin is not None and media_con > media_sin
              and mediana_con is not None and mediana_sin is not None
              and mediana_con > mediana_sin)
    if mejora and robusta:
        return {**base, "conclusion": "merece una prueba independiente",
                "motivo": "las anclas con patron superan a las anclas sin patron en "
                          "media y mediana, y la ventaja no depende del simbolo dominante",
                "evidencia": evidencia}
    return {**base, "conclusion": "no muestra mejora en esta muestra",
            "motivo": "las anclas con patron no superan a las anclas sin patron en "
                      "media y mediana",
            "evidencia": evidencia}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _contexto_publicado(ruta: Optional[Path]) -> Optional[Dict[str, Any]]:
    if ruta is None or not ruta.exists():
        return None
    with io.open(ruta, encoding="utf-8") as f:
        d = json.load(f)
    ref = d.get("grupos", {}).get("referencia_solo_precio", {})
    return {
        "fuente": str(ruta),
        "sha256": _sha256_archivo(ruta),
        "version": d.get("version_evaluacion"),
        "coincide_version_publicada": d.get("version_evaluacion") == VERSION_REFERENCIA_PUBLICADA,
        "etiqueta": "contexto secundario publicado previamente; no se sobrescribe",
        "universo_acreditado": d.get("universo", {}).get("hasta_entrada_detector"),
        "ternas_solo_precio": (d.get("referencia", {}) or {}).get("ternas_solo_precio"),
        "alertas": (d.get("referencia", {}) or {}).get("alertas_brutas"),
        "episodios": (d.get("referencia", {}) or {}).get("episodios"),
        "resolubles": ref.get("global", {}).get("resolubles"),
        "media_bps": ref.get("global", {}).get("retorno_medio_bps"),
        "mediana_bps": ref.get("global", {}).get("retorno_mediano_bps"),
    }


def _reduccion(
    ternas: int,
    alertas: int,
    episodios: int,
    con_patron: int,
) -> Dict[str, Any]:
    return {
        "ternas": ternas,
        "alertas_solo_precio": alertas,
        "episodios": episodios,
        "anclas_con_patron": con_patron,
        "anclas_sin_patron": episodios - con_patron,
        "tasa_alerta_por_terna": _redondear(alertas / ternas) if ternas else None,
        "tasa_episodio_por_alerta": _redondear(episodios / alertas) if alertas else None,
        "tasa_retencion_del_filtro": _redondear(con_patron / episodios) if episodios else None,
        "episodios_descartados_por_el_filtro": episodios - con_patron,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--cobertura", required=True)
    ap.add_argument("--klines", required=True)
    ap.add_argument("--salida", required=True, help="directorio para derivados voluminosos")
    ap.add_argument("--resumen", required=True, help="JSON compacto (apto para Git)")
    ap.add_argument("--contexto", default=None,
                    help="resumen JSON publicado antes; se incluye como contexto secundario")
    ap.add_argument("--run-id", default="exp-v2-ventana-4-20261116a")
    args = ap.parse_args(argv)

    db = Path(args.db)
    cobertura_ruta = Path(args.cobertura)
    klines_ruta = Path(args.klines)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    for ruta in (db, cobertura_ruta, klines_ruta):
        if not ruta.exists():
            raise SystemExit(f"no existe la fuente: {ruta}")

    hashes_antes = {
        "research.db": _sha256_archivo(db),
        "cobertura_json": _sha256_archivo(cobertura_ruta),
        "consultas_klines.jsonl": _sha256_archivo(klines_ruta),
    }

    cobertura = cargar_cobertura(cobertura_ruta)
    pob = cobertura["poblacion_b_agregados_1m"]
    db_declarada = str(cobertura.get("origen", {}).get("db_sha256", "")).lower()
    if db_declarada and db_declarada != hashes_antes["research.db"].lower():
        raise SystemExit(
            "research.db no coincide con el hash declarado en la cobertura: "
            f"{hashes_antes['research.db']} != {db_declarada}"
        )

    por_symbol, audit_ventanas = construir_ventanas(db, cobertura, args.run_id)
    universo = verificar_universo(por_symbol, cobertura)

    decisiones = evaluar_detector(por_symbol)
    alertas_p, resumen_p = alertas_patron(por_symbol, decisiones)
    ternas_detalle = resumen_p["ternas_detalle"]

    alertas_ref, audit_ref = construir_alertas_referencia(ternas_detalle, por_symbol)
    if len({a["terna"] for a in alertas_ref}) != len(alertas_ref):
        raise SystemExit("ternas duplicadas entre alertas de referencia")

    velas, audit_velas = cargar_velas(klines_ruta, args.run_id)

    episodios_p = agrupar_episodios(alertas_p)
    episodios_ref, audit_agrup = agrupar_con_tardias(alertas_ref, alertas_p)

    anclas_con = [e for e in episodios_ref if e["ancla_patron"]]
    anclas_sin = [e for e in episodios_ref if not e["ancla_patron"]]

    grupos = {
        "referencia_universo_igual": _resumen_grupo(
            "referencia_universo_igual", episodios_ref, velas, len(ternas_detalle)),
        "anclas_con_patron": _resumen_grupo(
            "anclas_con_patron", anclas_con, velas),
        "anclas_sin_patron": _resumen_grupo(
            "anclas_sin_patron", anclas_sin, velas),
    }
    tardias = resumen_tardias(episodios_ref, velas)
    tardias_grupo = {
        "grupo": "alertas_patron_tardias",
        "alertas": tardias["episodios"],
        "resolubles": tardias["resolubles"],
        "no_resolubles": tardias["no_resolubles"],
        "motivos_no_resoluble": tardias["motivos_no_resoluble"],
        "aciertos": tardias["aciertos"],
        "fallos": tardias["fallos"],
        "neutrales": tardias["neutrales"],
        "retorno_medio_bps": tardias["retorno_medio_bps"],
        "retorno_mediano_bps": tardias["retorno_mediano_bps"],
        "simbolos": tardias["simbolos"],
        "detalle": tardias["detalle"],
    }

    map_patron = mapear_episodios_patron(episodios_p, episodios_ref, velas)
    coinciden = sum(1 for f in map_patron if f["coincide_con_ancla_comun"])
    absorbidas = sum(1 for f in map_patron
                     if f["motivo_coincidencia"] == "absorbida_por_ancla_anterior")

    reduccion = _reduccion(
        ternas=len(ternas_detalle),
        alertas=len(alertas_ref),
        episodios=len(episodios_ref),
        con_patron=len(anclas_con),
    )
    conclusion = concluir_anclas(
        grupos["anclas_con_patron"]["global"],
        grupos["anclas_sin_patron"]["global"],
        grupos["anclas_sin_patron"]["detalle"],
        reduccion,
    )

    hashes_despues = {
        "research.db": _sha256_archivo(db),
        "cobertura_json": _sha256_archivo(cobertura_ruta),
        "consultas_klines.jsonl": _sha256_archivo(klines_ruta),
    }
    if hashes_antes != hashes_despues:
        raise SystemExit("las fuentes cambiaron durante la comparacion; abortado")

    def _cadena(grupo: Dict[str, Any], ternas: Optional[int] = None) -> Dict[str, Any]:
        g = grupo["global"]
        return {
            "ternas": ternas,
            "anclas": g["episodios"],
            "alertas_en_el_grupo": grupo["alertas_brutas"],
            "episodios": g["episodios"],
            "resolubles": g["resolubles"],
            "no_resolubles": g["no_resolubles"],
            "aciertos": g["aciertos"],
            "fallos": g["fallos"],
            "neutrales": g["neutrales"],
            "media_bps": g["retorno_medio_bps"],
            "mediana_bps": g["retorno_mediano_bps"],
        }

    resumen = {
        "version_comparacion": VERSION_COMPARACION,
        "referencia_publicada": VERSION_REFERENCIA_PUBLICADA,
        "run_id": args.run_id,
        "pregunta": "que episodios retiene el filtro de flujo y profundidad frente "
                    "a la regla de solo precio, sobre las mismas 501 ternas y con "
                    "el mismo corte causal, y que paso despues",
        "origen": {
            "db": str(db),
            "cobertura": str(cobertura_ruta),
            "klines": str(klines_ruta),
            "db_sha256_declarada_en_cobertura": db_declarada or None,
            "hashes_antes": hashes_antes,
            "hashes_despues": hashes_despues,
            "fuentes_intactas": hashes_antes == hashes_despues,
        },
        "universo_igual": {
            "publicado": universo["esperado"],
            "hasta_entrada_detector": universo["obtenido"],
            "conservado": universo["conservado"],
            "ternas_evaluadas_por_ambos_metodos": len(ternas_detalle),
            "cortes_verificados_identicos": audit_ref["cortes_verificados"],
            "ternas_no_monotonas": audit_ref["ternas_no_monotonas"],
            "alertas_con_patron_en_el_mismo_instante": audit_ref["alertas_con_patron"],
            "ventanas_validas_detector": audit_ventanas["ventanas_validas_detector"],
            "procedencia": dict(audit_ventanas["procedencia"]),
        },
        "embudo": {
            "ternas": len(ternas_detalle),
            "alertas_solo_precio": len(alertas_ref),
            "alertas_solo_precio_por_direccion": dict(
                Counter(a["direccion"] for a in alertas_ref)),
            "episodios": len(episodios_ref),
            "episodios_por_direccion": dict(
                Counter(e["direccion"] for e in episodios_ref)),
            "anclas_con_patron": len(anclas_con),
            "anclas_sin_patron": len(anclas_sin),
            "resolubles_con_patron": grupos["anclas_con_patron"]["global"]["resolubles"],
            "resolubles_sin_patron": grupos["anclas_sin_patron"]["global"]["resolubles"],
            "alertas_patron_tardias": tardias["episodios"],
            "alertas_patron_ancla": len(anclas_con),
            "patron_alertas": len(alertas_p),
            "patron_episodios": len(episodios_p),
            "reduccion": reduccion,
        },
        "grupos": {k: {kk: vv for kk, vv in v.items() if kk != "detalle"}
                   for k, v in grupos.items()},
        "alertas_patron_tardias": {k: v for k, v in tardias_grupo.items() if k != "detalle"},
        "episodios_patron_originales": {
            "episodios": len(episodios_p),
            "alertas": len(alertas_p),
            "coinciden_con_ancla_comun": coinciden,
            "absorbidas_por_ancla_anterior": absorbidas,
            "detalle": map_patron,
        },
        "conclusion": conclusion,
        "cadena": {
            "referencia_universo_igual": _cadena(
                grupos["referencia_universo_igual"], len(ternas_detalle)),
            "anclas_con_patron": _cadena(grupos["anclas_con_patron"]),
            "anclas_sin_patron": _cadena(grupos["anclas_sin_patron"]),
        },
        "cobertura_de_velas": {
            **{k: v for k, v in audit_velas.items() if k != "simbolos"},
            "simbolos": sorted(velas.keys()),
        },
        "contexto_publicado": _contexto_publicado(
            Path(args.contexto) if args.contexto else None),
        "limitaciones": [
            "captura ya usada en el desarrollo del detector: hallazgo exploratorio, no prueba independiente",
            "corte reconstruido: la captura no ejecuto el detector en vivo",
            "entrada = apertura de la vela siguiente al corte; no es un fill ni incluye latencia",
            "salida = apertura a 5 minutos; sin stop ni salida intravela",
            "funding UNKNOWN; costes solo como sensibilidad documentada",
            "anclas de distintos simbolos pueden solaparse en el tiempo: no son independientes",
            "una alerta del patron posterior al ancla no reclasifica el episodio ni hereda su entrada",
            "cobertura de velas limitada a los simbolos consultados durante la captura",
        ],
    }

    def _jsonl(nombre: str, filas: List[Dict[str, Any]]) -> str:
        ruta = salida / nombre
        with io.open(ruta, "w", encoding="utf-8", newline="\n") as f:
            for fila in filas:
                f.write(json.dumps(fila, ensure_ascii=False, sort_keys=True) + "\n")
        return _sha256_archivo(ruta)

    derivados = {
        "alertas_referencia_universo_igual.jsonl": _jsonl(
            "alertas_referencia_universo_igual.jsonl", alertas_ref),
        "episodios_referencia_universo_igual.jsonl": _jsonl(
            "episodios_referencia_universo_igual.jsonl",
            grupos["referencia_universo_igual"]["detalle"]),
        "anclas_con_patron.jsonl": _jsonl(
            "anclas_con_patron.jsonl", grupos["anclas_con_patron"]["detalle"]),
        "anclas_sin_patron.jsonl": _jsonl(
            "anclas_sin_patron.jsonl", grupos["anclas_sin_patron"]["detalle"]),
        "alertas_patron_tardias.jsonl": _jsonl(
            "alertas_patron_tardias.jsonl", tardias["detalle"]),
        "episodios_patron_originales.jsonl": _jsonl(
            "episodios_patron_originales.jsonl", map_patron),
    }
    resumen["derivados_fuera_de_git"] = {
        "directorio": str(salida),
        "archivos_sha256": derivados,
    }

    resumen_ruta = Path(args.resumen)
    resumen_ruta.parent.mkdir(parents=True, exist_ok=True)
    with io.open(resumen_ruta, "w", encoding="utf-8", newline="\n") as f:
        json.dump(resumen, f, ensure_ascii=False, sort_keys=True, indent=1)
        f.write("\n")

    print(json.dumps({
        "estado": "ok",
        "ternas": len(ternas_detalle),
        "alertas_solo_precio": len(alertas_ref),
        "episodios": len(episodios_ref),
        "anclas_con_patron": len(anclas_con),
        "anclas_sin_patron": len(anclas_sin),
        "resolubles_con_patron": grupos["anclas_con_patron"]["global"]["resolubles"],
        "resolubles_sin_patron": grupos["anclas_sin_patron"]["global"]["resolubles"],
        "conclusion": conclusion["conclusion"],
        "resumen": str(resumen_ruta),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
