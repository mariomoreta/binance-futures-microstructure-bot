"""Evaluacion de la hipotesis de extension previa (predeclarada).

Pregunta: cuando aparece una senal de continuacion, medir cuanto se ha
extendido el movimiento frente a la historia del propio contrato, permite
evitar entradas peores que las de una regla de solo precio?

La definicion, los grupos, el minimo evaluable y el criterio de decision estan
fijados en `docs/evidence/extension-previa-20261119/PREDECLARACION.md`,
publicado en el commit `561d0b953cf665cab83047f90003bc37d1b28a99` antes de
calcular cualquier retorno. Este modulo no ajusta nada a los resultados.

Solo lectura de las capturas. Salida fuera de Git.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secuencia_presion_v1 import detectar_secuencias, utc_iso  # noqa: E402
from replay_patron_ventana4 import (  # noqa: E402
    HORIZONTE_MS,
    VENTANA_MS,
    agrupar_episodios,
    alertas_solo_precio,
    ternas_contiguas,
)
from extension_previa_inventario import (  # noqa: E402
    CAPTURAS,
    _precios_desde_flujo,
    _ventanas_desde_db,
)

VERSION = "extension-previa-v1"
COSTE_IDA_VUELTA_BPS = 16.0
MIN_POR_GRUPO = 30
BLOQUES_PREVIOS = 6
MINUTOS_POR_BLOQUE = 3
MINUTOS_PREVIOS = BLOQUES_PREVIOS * MINUTOS_POR_BLOQUE
UMBRAL_EXTENSION = 1.0
SEMILLA = 42
RESAMPLES = 1000
BASE_COMMIT = "91e16671ca6492316023f1c9a7ac6c06149333ee"
COMMIT_PREDECLARACION = "561d0b953cf665cab83047f90003bc37d1b28a99"


# ---------------------------------------------------------------------------
# Metricas basicas
# ---------------------------------------------------------------------------

def _media(valores: List[float]) -> Optional[float]:
    return statistics.fmean(valores) if valores else None


def _mediana(valores: List[float]) -> Optional[float]:
    return statistics.median(valores) if valores else None


def _redondear(valor: Optional[float]) -> Optional[float]:
    return None if valor is None else round(float(valor), 4)


def _ic_media_bootstrap(a: List[float], b: List[float]) -> Optional[List[float]]:
    """IC95 descriptivo de media(a) - media(b). No forma parte del criterio."""
    if len(a) < 2 or len(b) < 2:
        return None
    rnd = random.Random(SEMILLA)
    difs: List[float] = []
    for _ in range(RESAMPLES):
        ma = statistics.fmean(rnd.choices(a, k=len(a)))
        mb = statistics.fmean(rnd.choices(b, k=len(b)))
        difs.append(ma - mb)
    difs.sort()
    return [_redondear(difs[int(0.025 * RESAMPLES)]),
            _redondear(difs[int(0.975 * RESAMPLES) - 1])]


# ---------------------------------------------------------------------------
# Extension previa de un episodio
# ---------------------------------------------------------------------------

def _minutos_previos(
    serie: Dict[int, Dict[str, Any]],
    primer_minuto_ms: int,
    cut_ms: int,
) -> Tuple[List[int], Optional[str]]:
    """18 minutos contiguos inmediatamente anteriores, conocidos en el corte.

    Devuelve (minutos, motivo_de_corte). El motivo no es None cuando la cadena
    se rompe antes de completar los 18 minutos.
    """
    validos: List[int] = []
    t = primer_minuto_ms - VENTANA_MS
    motivo: Optional[str] = None
    while len(validos) < MINUTOS_PREVIOS:
        vela = serie.get(t)
        if vela is None:
            motivo = "minuto_previo_ausente"
            break
        if vela.get("data_quality") != "OK":
            motivo = "minuto_previo_no_ok"
            break
        if vela["conflictiva"]:
            motivo = "minuto_previo_contradictorio"
            break
        if not (vela["open"] > 0 and vela.get("close", 0) > 0):
            motivo = "minuto_previo_sin_precio"
            break
        if int(vela.get("adquirido_ms") or 0) > cut_ms:
            motivo = "minuto_previo_no_disponible_al_corte"
            break
        validos.append(t)
        t -= VENTANA_MS
    validos.reverse()
    return validos, motivo


def _grupo(extension: float) -> str:
    return "EXTENDIDO" if extension > UMBRAL_EXTENSION else "NORMAL"


def _precio(serie: Dict[int, Dict[str, Any]], t: int, campo: str) -> Optional[float]:
    """Precio de un minuto. El requisito de `data_quality = OK` se aplica en
    `_minutos_previos` a los 18 minutos de historia; la senal y la entrada/salida
    solo exigen precio positivo y no contradictorio, como fija la predeclaracion.
    """
    vela = serie.get(t)
    if vela is None or vela["conflictiva"]:
        return None
    valor = vela.get(campo)
    if valor is None or valor <= 0:
        return None
    return float(valor)


def evaluar_episodio(
    episodio: Dict[str, Any],
    serie: Dict[str, Dict[int, Dict[str, Any]]],
    captura: str,
) -> Dict[str, Any]:
    """Aplica la definicion predeclarada a un episodio."""
    symbol = episodio["symbol"]
    direccion = episodio["direccion"]
    cut = int(episodio["cut_ms"])
    fin_3 = int(episodio["cierre_nominal_ms"])
    t3 = fin_3 - VENTANA_MS
    t2 = t3 - VENTANA_MS
    t1 = t2 - VENTANA_MS
    fila = serie.get(symbol) or {}
    base = {
        "captura": captura,
        "symbol": symbol,
        "direccion": direccion,
        "cut_ms": cut,
        "cut_iso": episodio.get("cut_iso"),
        "terna": episodio.get("terna"),
        "tambien_patron": bool(episodio.get("tambien_patron")),
    }

    c1 = _precio(fila, t1, "close")
    c3 = _precio(fila, t3, "close")
    if c1 is None or c3 is None:
        return {**base, "estado": "no_evaluable", "motivo": "cierre_de_senal_ausente"}

    minutos, motivo_hist = _minutos_previos(fila, t1, cut)
    if len(minutos) < MINUTOS_PREVIOS:
        return {**base, "estado": "no_evaluable",
                "motivo": "historia_previa_insuficiente",
                "detalle_motivo": motivo_hist,
                "bloques_previos": len(minutos) // MINUTOS_POR_BLOQUE}

    avances: List[float] = []
    for i in range(BLOQUES_PREVIOS):
        bloque = minutos[i * MINUTOS_POR_BLOQUE:(i + 1) * MINUTOS_POR_BLOQUE]
        ci = _precio(fila, bloque[0], "close")
        cf = _precio(fila, bloque[-1], "close")
        if ci is None or cf is None or ci <= 0:
            return {**base, "estado": "no_evaluable",
                    "motivo": "bloque_previo_sin_precio",
                    "bloques_previos": BLOQUES_PREVIOS}
        avances.append(abs(cf / ci - 1.0))

    mediana_previa = statistics.median(avances)
    if mediana_previa <= 0:
        return {**base, "estado": "no_evaluable", "motivo": "mediana_previa_nula",
                "bloques_previos": BLOQUES_PREVIOS,
                "avances_bloques": avances}

    avance_senal = abs(c3 / c1 - 1.0)
    extension = avance_senal / mediana_previa

    entrada_ms = (cut // VENTANA_MS + 1) * VENTANA_MS
    salida_ms = entrada_ms + HORIZONTE_MS
    entrada = _precio(fila, entrada_ms, "open")
    if entrada is None:
        return {**base, "estado": "no_evaluable", "motivo": "vela_entrada_ausente",
                "bloques_previos": BLOQUES_PREVIOS}
    salida = _precio(fila, salida_ms, "open")
    if salida is None:
        return {**base, "estado": "no_evaluable", "motivo": "vela_salida_ausente",
                "bloques_previos": BLOQUES_PREVIOS, "precio_entrada": entrada}

    signo = 1.0 if direccion == "LONG" else -1.0
    bruto = signo * (salida / entrada - 1.0) * 1e4
    neto = bruto - COSTE_IDA_VUELTA_BPS
    return {
        **base,
        "estado": "evaluable",
        "bloques_previos": BLOQUES_PREVIOS,
        "avance_senal": avance_senal,
        "avances_bloques": avances,
        "mediana_previa": mediana_previa,
        "extension": extension,
        "grupo": _grupo(extension),
        "entrada_ms": entrada_ms,
        "salida_ms": salida_ms,
        "precio_entrada": entrada,
        "precio_salida": salida,
        "retorno_bruto_bps": bruto,
        "retorno_neto_bps": neto,
    }


# ---------------------------------------------------------------------------
# Agregados
# ---------------------------------------------------------------------------

def _resumen_grupo(eps: List[Dict[str, Any]]) -> Dict[str, Any]:
    netos = [e["retorno_neto_bps"] for e in eps]
    brutos = [e["retorno_bruto_bps"] for e in eps]
    return {
        "episodios": len(eps),
        "neto_medio_bps": _redondear(_media(netos)),
        "neto_mediano_bps": _redondear(_mediana(netos)),
        "bruto_medio_bps": _redondear(_media(brutos)),
        "bruto_mediano_bps": _redondear(_mediana(brutos)),
        "neto_suma_bps": _redondear(sum(netos)) if netos else None,
        "positivos": sum(1 for x in netos if x > 0),
        "negativos": sum(1 for x in netos if x < 0),
        "iguales": sum(1 for x in netos if x == 0),
        "extension_mediana": _redondear(_mediana([e["extension"] for e in eps])),
        "por_direccion": {
            d: {
                "episodios": len(sub),
                "neto_medio_bps": _redondear(_media([e["retorno_neto_bps"] for e in sub])),
                "neto_mediano_bps": _redondear(_mediana([e["retorno_neto_bps"] for e in sub])),
            }
            for d in ("LONG", "SHORT")
            for sub in [[e for e in eps if e["direccion"] == d]]
        },
    }


def _por_captura(eps: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for cap in sorted({e["captura"] for e in eps}):
        sub = [e for e in eps if e["captura"] == cap]
        ext = [e for e in sub if e["grupo"] == "EXTENDIDO"]
        nor = [e for e in sub if e["grupo"] == "NORMAL"]
        out[cap] = {
            "episodios": len(sub),
            "extendido": {"n": len(ext), "neto_mediano_bps": _redondear(_mediana([e["retorno_neto_bps"] for e in ext]))},
            "normal": {"n": len(nor), "neto_mediano_bps": _redondear(_mediana([e["retorno_neto_bps"] for e in nor]))},
            "normal_supera_extendido": (
                (_mediana([e["retorno_neto_bps"] for e in nor]) or 0) >
                (_mediana([e["retorno_neto_bps"] for e in ext]) or 0)
                if ext and nor else None
            ),
        }
    return out


def _por_simbolo(eps: List[Dict[str, Any]]) -> Dict[str, Any]:
    conteo = Counter(e["symbol"] for e in eps)
    out: Dict[str, Any] = {}
    for symbol, n in conteo.most_common():
        sub = [e for e in eps if e["symbol"] == symbol]
        ext = [e for e in sub if e["grupo"] == "EXTENDIDO"]
        nor = [e for e in sub if e["grupo"] == "NORMAL"]
        out[symbol] = {
            "episodios": n,
            "cuota": _redondear(n / len(eps)),
            "extendido_n": len(ext),
            "normal_n": len(nor),
            "neto_medio_bps": _redondear(_media([e["retorno_neto_bps"] for e in sub])),
        }
    return out


def _terciles(eps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Descriptivo secundario, sin valor de decision."""
    orden = sorted(eps, key=lambda e: e["extension"])
    n = len(orden)
    cortes = [0, n // 3, 2 * n // 3, n]
    out = []
    for i in range(3):
        sub = orden[cortes[i]:cortes[i + 1]]
        out.append({
            "tercil": i + 1,
            "n": len(sub),
            "extension_min": _redondear(sub[0]["extension"]) if sub else None,
            "extension_max": _redondear(sub[-1]["extension"]) if sub else None,
            "neto_medio_bps": _redondear(_media([e["retorno_neto_bps"] for e in sub])),
            "neto_mediano_bps": _redondear(_mediana([e["retorno_neto_bps"] for e in sub])),
        })
    return out


def _criterio(eps: List[Dict[str, Any]]) -> Dict[str, Any]:
    ext = [e for e in eps if e["grupo"] == "EXTENDIDO"]
    nor = [e for e in eps if e["grupo"] == "NORMAL"]
    if len(ext) < MIN_POR_GRUPO or len(nor) < MIN_POR_GRUPO:
        return {
            "aplica": False,
            "motivo": "grupo_menor_que_30",
            "n_extendido": len(ext),
            "n_normal": len(nor),
        }
    med_ext = _mediana([e["retorno_neto_bps"] for e in ext])
    med_nor = _mediana([e["retorno_neto_bps"] for e in nor])
    med_bruta_ext = _mediana([e["retorno_bruto_bps"] for e in ext])
    med_bruta_nor = _mediana([e["retorno_bruto_bps"] for e in nor])

    dominante = Counter(e["symbol"] for e in eps).most_common(1)[0][0]
    sin_dom = [e for e in eps if e["symbol"] != dominante]
    med_nor_sd = _mediana([e["retorno_neto_bps"] for e in sin_dom if e["grupo"] == "NORMAL"])
    med_ext_sd = _mediana([e["retorno_neto_bps"] for e in sin_dom if e["grupo"] == "EXTENDIDO"])

    por_cap = _por_captura(eps)
    capturas_a_favor = [c for c, v in por_cap.items() if v["normal_supera_extendido"] is True]

    mas_extremo = max(eps, key=lambda e: abs(e["retorno_neto_bps"]))
    sin_extremo = [e for e in eps if e is not mas_extremo]
    med_nor_se = _mediana([e["retorno_neto_bps"] for e in sin_extremo if e["grupo"] == "NORMAL"])
    med_ext_se = _mediana([e["retorno_neto_bps"] for e in sin_extremo if e["grupo"] == "EXTENDIDO"])

    cond1 = med_nor > med_ext
    cond2 = (_media([e["retorno_neto_bps"] for e in nor]) or 0) > (_media([e["retorno_neto_bps"] for e in ext]) or 0)
    cond3 = (med_nor_sd is not None and med_ext_sd is not None and med_nor_sd > med_ext_sd)
    cond4 = len(capturas_a_favor) >= 2
    cond5 = (med_nor_se is not None and med_ext_se is not None and med_nor_se > med_ext_se)
    return {
        "aplica": True,
        "condiciones": {
            "1_mediana_normal_supera_extendido": bool(cond1),
            "2_media_normal_supera_extendido": bool(cond2),
            "3_mediana_se_mantiene_sin_contrato_dominante": bool(cond3),
            "4_mediana_se_mantiene_en_2_capturas": bool(cond4),
            "5_mediana_se_mantiene_sin_episodio_extremo": bool(cond5),
        },
        "detalle": {
            "mediana_neta_normal": _redondear(med_nor),
            "mediana_neta_extendido": _redondear(med_ext),
            "mediana_bruta_normal": _redondear(med_bruta_nor),
            "mediana_bruta_extendido": _redondear(med_bruta_ext),
            "contrato_dominante": dominante,
            "mediana_neta_normal_sin_dominante": _redondear(med_nor_sd),
            "mediana_neta_extendido_sin_dominante": _redondear(med_ext_sd),
            "capturas_a_favor": capturas_a_favor,
            "episodio_extremo": {
                "symbol": mas_extremo["symbol"],
                "captura": mas_extremo["captura"],
                "cut_iso": mas_extremo["cut_iso"],
                "retorno_neto_bps": _redondear(mas_extremo["retorno_neto_bps"]),
            },
            "mediana_neta_normal_sin_extremo": _redondear(med_nor_se),
            "mediana_neta_extendido_sin_extremo": _redondear(med_ext_se),
        },
        "todas": bool(cond1 and cond2 and cond3 and cond4 and cond5),
    }


def _veredicto(criterio: Dict[str, Any]) -> str:
    if not criterio.get("aplica"):
        return "DATOS INSUFICIENTES"
    return "APORTA EVIDENCIA" if criterio.get("todas") else "NO APORTA"


def _agregar(episodios: List[Dict[str, Any]], etiqueta: str) -> Dict[str, Any]:
    evaluables = [e for e in episodios if e["estado"] == "evaluable"]
    ext = [e for e in evaluables if e["grupo"] == "EXTENDIDO"]
    nor = [e for e in evaluables if e["grupo"] == "NORMAL"]

    motivos = Counter(e["motivo"] for e in episodios if e["estado"] != "evaluable")
    # Primer motivo excluyente, en el orden del embudo.
    orden = [
        "historia_previa_insuficiente",
        "mediana_previa_nula",
        "cierre_de_senal_ausente",
        "vela_entrada_ausente",
        "vela_salida_ausente",
        "bloque_previo_sin_precio",
    ]
    excluyente: Counter = Counter()
    for e in episodios:
        if e["estado"] == "evaluable":
            continue
        for m in orden:
            if e["motivo"] == m:
                excluyente[m] += 1
                break
        else:
            excluyente[e["motivo"]] += 1

    netos_ext = [e["retorno_neto_bps"] for e in ext]
    netos_nor = [e["retorno_neto_bps"] for e in nor]
    descartados_neg = [x for x in netos_ext if x < 0]
    descartados_pos = [x for x in netos_ext if x > 0]

    criterio = _criterio(evaluables)
    return {
        "familia": etiqueta,
        "episodios": len(episodios),
        "evaluables": len(evaluables),
        "no_evaluables": len(episodios) - len(evaluables),
        "motivos_no_excluyentes": dict(motivos),
        "motivos_excluyentes": dict(excluyente),
        "grupos": {"EXTENDIDO": _resumen_grupo(ext), "NORMAL": _resumen_grupo(nor)},
        "diferencia_normal_menos_extendido": {
            "neto_medio_bps": _redondear((_media(netos_nor) or 0) - (_media(netos_ext) or 0)),
            "neto_mediano_bps": _redondear((_mediana(netos_nor) or 0) - (_mediana(netos_ext) or 0)),
            "ic95_bootstrap_neto_medio_bps": _ic_media_bootstrap(netos_nor, netos_ext),
        },
        "filtro_descarta_extendido": {
            "descartados": len(ext),
            "cuota_descartada": _redondear(len(ext) / len(evaluables)) if evaluables else None,
            "perdidas_evitadas_bps": _redondear(sum(descartados_neg)),
            "perdidas_evitadas_n": len(descartados_neg),
            "ganancias_dejadas_pasar_bps": _redondear(sum(descartados_pos)),
            "ganancias_dejadas_pasar_n": len(descartados_pos),
            "neto_del_filtro_bps": _redondear(sum(netos_ext)),
        },
        "por_direccion": {
            d: {
                "n": len(sub),
                "extendido": {
                    "n": len([e for e in sub if e["grupo"] == "EXTENDIDO"]),
                    "neto_medio_bps": _redondear(_media([e["retorno_neto_bps"] for e in sub if e["grupo"] == "EXTENDIDO"])),
                    "neto_mediano_bps": _redondear(_mediana([e["retorno_neto_bps"] for e in sub if e["grupo"] == "EXTENDIDO"])),
                },
                "normal": {
                    "n": len([e for e in sub if e["grupo"] == "NORMAL"]),
                    "neto_medio_bps": _redondear(_media([e["retorno_neto_bps"] for e in sub if e["grupo"] == "NORMAL"])),
                    "neto_mediano_bps": _redondear(_mediana([e["retorno_neto_bps"] for e in sub if e["grupo"] == "NORMAL"])),
                },
            }
            for d in ("LONG", "SHORT")
            for sub in [[e for e in evaluables if e["direccion"] == d]]
        },
        "por_captura": _por_captura(evaluables),
        "por_simbolo": _por_simbolo(evaluables),
        "terciles": _terciles(evaluables),
        "criterio": criterio,
        "veredicto": _veredicto(criterio),
        "detalle": evaluables,
        "detalle_no_evaluables": [
            {
                "symbol": e["symbol"],
                "direccion": e["direccion"],
                "cut_ms": e["cut_ms"],
                "motivo": e["motivo"],
                "detalle_motivo": e.get("detalle_motivo"),
                "bloques_previos": e.get("bloques_previos"),
            }
            for e in episodios
            if e["estado"] != "evaluable"
        ],
    }


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------

def _episodios_de_captura(captura: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    db = Path(captura["db"])
    run_id = captura["run_id"]
    if not db.exists():
        return {}, {"run_id": run_id, "estado": "sin_db", "patron": [], "solo_precio": []}
    por_symbol, audit_ventanas = _ventanas_desde_db(db, run_id)
    serie = _precios_desde_flujo(db)

    decisiones = {}
    for symbol, ventanas in por_symbol.items():
        for r in detectar_secuencias(ventanas, symbol):
            decisiones[r.observation_id] = r

    patron_alertas: List[Dict[str, Any]] = []
    for symbol, ventanas in por_symbol.items():
        for a, b, c in ternas_contiguas(ventanas):
            r = decisiones.get(c.observation_id)
            if r is None or r.decision not in ("LONG_EXPERIMENTAL", "SHORT_EXPERIMENTAL"):
                continue
            cut = max(int(c.ventana_fin_ms), int(a.disponibilidad_ms or 0),
                      int(b.disponibilidad_ms or 0), int(c.disponibilidad_ms or 0))
            patron_alertas.append({
                "symbol": symbol,
                "direccion": r.direccion_candidata,
                "terna": f"{symbol}|{c.ventana_inicio_ms}",
                "cut_ms": cut,
                "cut_iso": utc_iso(cut),
                "cierre_nominal_ms": int(c.ventana_fin_ms),
                "demora_corte_ms": cut - int(c.ventana_fin_ms),
                "decision": r.decision,
                "tambien_patron": True,
            })

    ternas_patron = {f"{p['symbol']}|{p['cierre_nominal_ms'] - VENTANA_MS}": p for p in patron_alertas}
    solo_alertas, audit_sp = alertas_solo_precio(db, run_id, ternas_patron)

    audit = {
        "run_id": run_id,
        "ventanas": audit_ventanas,
        "solo_precio": audit_sp,
        "alertas_patron_brutas": len(patron_alertas),
        "alertas_solo_precio_brutas": len(solo_alertas),
        "serie_simbolos": len(serie),
        "serie_velas": sum(len(v) for v in serie.values()),
    }
    return (
        {
            "serie": serie,
            "patron": agrupar_episodios(patron_alertas),
            "solo_precio": agrupar_episodios(solo_alertas),
        },
        audit,
    )


def _compacto(resultado: Dict[str, Any]) -> Dict[str, Any]:
    """Version publicable: agregados completos, detalle minimo por episodio."""
    campos = ("captura", "symbol", "direccion", "cut_ms", "cut_iso", "extension",
              "grupo", "precio_entrada", "precio_salida", "retorno_bruto_bps",
              "retorno_neto_bps", "tambien_patron")
    salida = {k: v for k, v in resultado.items()
              if k not in ("primaria_solo_precio", "secundaria_patron")}
    for clave in ("primaria_solo_precio", "secundaria_patron"):
        bloque = dict(resultado[clave])
        bloque.pop("detalle_no_evaluables", None)
        bloque["detalle"] = [
            {k: e.get(k) for k in campos} for e in bloque.get("detalle", [])
        ]
        salida[clave] = bloque
    return salida


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--compacto", action="store_true",
                    help="omite el detalle de los no evaluables")
    args = ap.parse_args(argv)

    por_captura: Dict[str, Any] = {}
    auditorias: List[Dict[str, Any]] = []
    eps_solo: List[Dict[str, Any]] = []
    eps_patron: List[Dict[str, Any]] = []
    for cap in CAPTURAS:
        print(f"evaluando {cap['run_id']} ...", flush=True)
        datos, audit = _episodios_de_captura(cap)
        auditorias.append(audit)
        if not datos:
            continue
        serie = datos["serie"]
        for e in datos["solo_precio"]:
            eps_solo.append(evaluar_episodio(e, serie, cap["run_id"]))
        for e in datos["patron"]:
            eps_patron.append(evaluar_episodio(e, serie, cap["run_id"]))
        por_captura[cap["run_id"]] = {
            "episodios_solo_precio": len(datos["solo_precio"]),
            "episodios_patron": len(datos["patron"]),
            "alertas_solo_precio_brutas": audit["alertas_solo_precio_brutas"],
            "alertas_patron_brutas": audit["alertas_patron_brutas"],
        }

    primaria = _agregar(eps_solo, "solo_precio")
    secundaria = _agregar(eps_patron, "patron")

    resultado = {
        "version": VERSION,
        "base_commit": BASE_COMMIT,
        "commit_predeclaracion": COMMIT_PREDECLARACION,
        "parametros": {
            "coste_ida_vuelta_bps": COSTE_IDA_VUELTA_BPS,
            "min_por_grupo": MIN_POR_GRUPO,
            "bloques_previos": BLOQUES_PREVIOS,
            "minutos_por_bloque": MINUTOS_POR_BLOQUE,
            "umbral_extension": UMBRAL_EXTENSION,
            "funding": "UNKNOWN",
        },
        "auditorias": auditorias,
        "capturas": por_captura,
        "primaria_solo_precio": primaria,
        "secundaria_patron": secundaria,
    }
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    a_publicar = _compacto(resultado) if args.compacto else resultado
    with io.open(salida, "w", encoding="utf-8", newline="\n") as f:
        json.dump(a_publicar, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    for nombre, bloque in (("solo_precio", primaria), ("patron", secundaria)):
        print(f"{nombre}: episodios={bloque['episodios']} evaluables={bloque['evaluables']} "
              f"EXT={bloque['grupos']['EXTENDIDO']['episodios']} "
              f"NOR={bloque['grupos']['NORMAL']['episodios']} "
              f"veredicto={bloque['veredicto']}")
    print(f"resumen={salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
