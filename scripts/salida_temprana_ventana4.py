# -*- coding: utf-8 -*-
"""Salida temprana por primer cambio observable (ventana 4).

Pregunta: manteniendo la entrada original, cerrar al primer cambio observable
recorta mas perdidas de las ganancias que sacrifica?

Reglas fijadas ANTES de calcular (no se ajustan umbrales):

  - Universo: las 143 anclas comunes ya publicadas. Se reconstruyen con el mismo
    pipeline publicado y se verifican contra
    `episodios_referencia_universo_igual.jsonl` (143/143). Las 4 anclas del
    patron estan dentro de esas 143: no se suman otra vez.
  - Entrada original: apertura de la vela del primer minuto estrictamente
    posterior al corte (la regla publicada). No se mueve.
  - Salida original: apertura de la vela 5 minutos despues de la entrada.
  - Cambio observable: el primer bloque b_0..b_5 (minutos alineados al reloj,
    b_0 = minuto del corte) que cumpla la regla publicada, con la prioridad
    publicada giro > debilitamiento > precio_sin_avance >
    profundidad_deja_de_caer. Se reutiliza `analizar_bloques` del modulo
    publicado: mismos umbrales, misma usabilidad y mismo delta de cierre.
  - Un bloque no utilizable ANTES del primer cambio impide conocer el primer
    cambio: el ancla es NO EVALUABLE. Un hueco no es "sin cambio".
  - Solo pueden adelantar la salida los bloques cuyo fin + 1 minuto sea
    estrictamente anterior a la salida original. Con b_0 terminando en la
    entrada, son b_0..b_3.
  - Disponibilidad del cambio = maximo de los tiempos de disponibilidad de los
    datos que lo acreditan, nunca solo el cierre del bloque:
        giro / debilitamiento        -> cierre del bloque y as_of del flujo;
        precio_sin_avance            -> ademas as_of del cierre base;
        profundidad_deja_de_caer     -> ademas as_of del libro.
    Se publica tambien la disponibilidad amplia del bloque (la del diagnostico
    publicado, que incluye el libro siempre que sea util) y se informa si el
    minuto de salida cambia entre ambas definiciones.
  - Salida alternativa: apertura de la vela del primer minuto estrictamente
    posterior a esa disponibilidad. Solo cuenta si es estrictamente anterior a
    la salida original. Si coincide o llega despues, se conserva la original.
  - El minuto es la resolucion del precio, no el disparador: sin cambio
    acreditado no se adelanta la salida. No se invierte la direccion, no se
    mueve la entrada y no se reinicia el horizonte.
  - Delta = retorno de la salida alternativa menos retorno de la salida
    original, alineado por direccion (s = +1 LONG, -1 SHORT). Positivo = la
    salida temprana mejora.
  - Costes: 16 bps ida y vuelta aplicados igual a ambos lados como sensibilidad
    (el delta no cambia). Funding UNKNOWN. Retornos brutos, no P&L.
  - Veredicto predeclarado: menos de 30 pares resolubles con salida
    efectivamente adelantada -> INSUFICIENTE. Alcanzar 30 no valida la regla
    fuera de esta ventana.

Solo lectura de la captura y de los derivados publicados. Sin Binance, sin
capturas nuevas, sin ordenes, sin cambios al detector, al bot ni al dashboard.
"""

import argparse
import io
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comparar_anclas_ventana4 import (  # noqa: E402
    VERSION_COMPARACION,
    agrupar_con_tardias,
    construir_alertas_referencia,
    corte_de_terna,
)
from diagnostico_cuatro_casos_ventana4 import (  # noqa: E402
    cargar_filas,
    verificar_anclas_publicadas,
)
from diagnostico_factores_ventana4 import (  # noqa: E402
    VERSION_DIAGNOSTICO,
    analizar_bloques,
)
from replay_patron_ventana4 import (  # noqa: E402
    COSTE_IDA_VUELTA_BPS,
    HORIZONTE_MS,
    MIN_EPISODIOS,
    VENTANA_MS,
    _mediana,
    _media,
    _referencia_entrada,
    _sha256_archivo,
    alertas_patron,
    cargar_cobertura,
    cargar_velas,
    construir_ventanas,
    evaluar_detector,
    resolver_alerta,
    utc_iso,
    verificar_universo,
)

VERSION_SALIDA = "salida-temprana-v1"

ESTADO_ADELANTADA = "adelantada_resoluble"
ESTADO_CONSERVADA = "original_conservada"
ESTADO_NO_EVALUABLE = "no_evaluable"

MOTIVO_SIN_CAMBIO = "sin_cambio_utilizable"
MOTIVO_SIN_TIEMPO = "cambio_sin_tiempo_para_adelantar"
MOTIVO_COINCIDE = "cambio_coincide_con_salida_original"
MOTIVO_HUECO = "hueco_antes_del_primer_cambio"
MOTIVO_SIN_BLOQUES_RELEVANTES = "sin_bloques_relevantes"
MOTIVO_VELA_ALT_AUSENTE = "vela_salida_alternativa_ausente"
MOTIVO_VELA_ALT_CONTRADICTORIA = "vela_salida_alternativa_contradictoria"
MOTIVO_ORIGINAL_NO_RESOLUBLE = "resultado_original_no_resoluble"
MOTIVO_PRECIO_ALT = "precio_salida_alternativa_no_positivo"
MOTIVO_SIN_VELAS = "sin_velas_para_simbolo"

TIPOS_PRIORIDAD = ("giro", "debilitamiento", "precio_sin_avance",
                   "profundidad_deja_de_caer")

# Tolerancia para comparar precios/retornos reconstruidos con los publicados.
TOL_PRECIO = 1e-12
TOL_RETORNO = 1e-6
TOL_DELTA = 1e-9


# ---------------------------------------------------------------------------
# Disponibilidad del cambio
# ---------------------------------------------------------------------------

def disponibilidad_acreditante(
    bloque: Dict[str, Any],
    tipo: str,
    as_of_base_ms: Optional[int],
) -> int:
    """Maximo de los tiempos de los datos que acreditan ESTE cambio.

    El cierre del bloque por si solo no basta: la fila de flujo tiene su propio
    `as_of_ms` (posterior al cierre por exigencia de usabilidad). El cierre base
    solo cuenta para `precio_sin_avance` y el libro solo para el cambio de
    profundidad.
    """
    disp = max(int(bloque["fin_ms"]), int(bloque["as_of_flow_ms"]))
    if tipo == "precio_sin_avance" and as_of_base_ms is not None:
        disp = max(disp, int(as_of_base_ms))
    if tipo == "profundidad_deja_de_caer":
        as_of_libro = bloque.get("as_of_book_ms")
        if as_of_libro is None:
            raise SystemExit("cambio de profundidad sin as_of de libro")
        disp = max(disp, int(as_of_libro))
    return disp


def _as_of_base(
    bloques: List[Dict[str, Any]], indice: int, cut_ms: int
) -> Optional[int]:
    """as_of del cierre contra el que se mide el delta del bloque `indice`."""
    if indice == 0:
        return int(cut_ms)
    for previo in reversed(bloques[:indice]):
        if previo["estado"] == "resoluble":
            return int(previo["as_of_flow_ms"])
    return None


# ---------------------------------------------------------------------------
# Evaluacion de una ancla
# ---------------------------------------------------------------------------

def evaluar_ancla(
    episodio: Dict[str, Any],
    fila_terna: Dict[str, Any],
    indice: Dict[str, Dict[int, Any]],
    flujo: Dict[Tuple[str, int], Dict[str, Any]],
    libro: Dict[Tuple[str, int], Dict[str, Any]],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
    bloques_publicados: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    symbol = episodio["symbol"]
    direccion = episodio["direccion"]
    inicios = [int(x) for x in fila_terna["ventanas"]]
    a, b, c = (indice[symbol][i] for i in inicios)
    if (int(b.ventana_inicio_ms) != int(a.ventana_fin_ms)
            or int(c.ventana_inicio_ms) != int(b.ventana_fin_ms)):
        raise SystemExit(f"terna no contigua en {fila_terna['terna']}")
    corte = corte_de_terna(a, b, c)
    if corte != int(episodio["cut_ms"]):
        raise SystemExit(f"corte incoherente en {fila_terna['terna']}")

    entrada_ms = _referencia_entrada(corte)
    salida_original_ms = entrada_ms + HORIZONTE_MS
    original = resolver_alerta(episodio, velas)

    post = analizar_bloques(flujo, libro, symbol, corte, direccion, c)
    bloques = post["bloques"]
    if bloques_publicados is not None:
        _verificar_bloques(bloques, bloques_publicados, fila_terna["terna"])

    ficha: Dict[str, Any] = {
        "symbol": symbol,
        "direccion": direccion,
        "terna": fila_terna["terna"],
        "cut_ms": corte,
        "cut_iso": utc_iso(corte),
        "ancla_patron": bool(episodio["ancla_patron"]),
        "entrada_ms": entrada_ms,
        "entrada_iso": utc_iso(entrada_ms),
        "salida_original_ms": salida_original_ms,
        "salida_original_iso": utc_iso(salida_original_ms),
        "precio_entrada": original.get("precio_entrada"),
        "precio_salida_original": original.get("precio_salida"),
        "retorno_original_bps": original.get("retorno_bps"),
        "original_estado": original.get("estado"),
        "original_motivo": original.get("motivo"),
        "bloques_utiles": post["bloques_utiles"],
        "bloques_totales": post["bloques_totales"],
        "primer_cambio_tipo": None,
        "primer_cambio_k": None,
        "primer_cambio_inicio_iso": None,
        "primer_cambio_fin_iso": None,
        "disponibilidad_ms": None,
        "disponibilidad_iso": None,
        "disponibilidad_publicada_ms": None,
        "disponibilidad_antes_de_entrada": None,
        "minuto_distinto_por_definicion": None,
        "salida_alternativa_ms": None,
        "salida_alternativa_iso": None,
        "precio_salida_alternativa": None,
        "retorno_alternativo_bps": None,
        "delta_bps": None,
        "estado": ESTADO_NO_EVALUABLE,
        "motivo": None,
    }

    if original.get("estado") != "resoluble":
        ficha["motivo"] = MOTIVO_ORIGINAL_NO_RESOLUBLE
        return ficha

    # Bloques que pueden adelantar la salida: fin + 1 min < salida original.
    relevantes = [bl for bl in bloques
                  if int(bl["fin_ms"]) + VENTANA_MS < salida_original_ms]
    if not relevantes:
        ficha["estado"] = ESTADO_CONSERVADA
        ficha["motivo"] = MOTIVO_SIN_BLOQUES_RELEVANTES
        return ficha

    primer: Optional[Dict[str, Any]] = None
    for bl in relevantes:
        if bl["estado"] != "resoluble":
            ficha["motivo"] = MOTIVO_HUECO
            ficha["hueco_k"] = bl["k"]
            ficha["hueco_motivo"] = bl["motivo"]
            return ficha
        if bl["tipos"]:
            primer = bl
            break

    if primer is None:
        ficha["estado"] = ESTADO_CONSERVADA
        ficha["motivo"] = MOTIVO_SIN_CAMBIO
        return ficha

    tipo = min(primer["tipos"], key=TIPOS_PRIORIDAD.index)
    if tipo not in TIPOS_PRIORIDAD:
        raise SystemExit(f"tipo de cambio desconocido: {tipo}")
    base_ms = _as_of_base(bloques, int(primer["k"]), corte)
    disp = disponibilidad_acreditante(primer, tipo, base_ms)
    disp_pub = int(primer["disponibilidad_ms"])
    salida_alt_ms = _referencia_entrada(disp)
    salida_alt_pub_ms = _referencia_entrada(disp_pub)

    ficha.update({
        "primer_cambio_tipo": tipo,
        "primer_cambio_tipos": list(primer["tipos"]),
        "primer_cambio_k": primer["k"],
        "primer_cambio_inicio_iso": primer["inicio_iso"],
        "primer_cambio_fin_iso": primer["fin_iso"],
        "flujo_alineado": primer["flujo_alineado"],
        "delta_cierre_bps": primer["delta_cierre_bps"],
        "disponibilidad_ms": disp,
        "disponibilidad_iso": utc_iso(disp),
        "disponibilidad_publicada_ms": disp_pub,
        "disponibilidad_antes_de_entrada": disp < entrada_ms,
        "minuto_distinto_por_definicion": salida_alt_ms != salida_alt_pub_ms,
    })
    if disp < entrada_ms:
        raise SystemExit(
            f"cambio disponible antes de la entrada (look-ahead) en "
            f"{ficha['terna']}")

    if salida_alt_ms >= salida_original_ms:
        ficha["estado"] = ESTADO_CONSERVADA
        ficha["motivo"] = (MOTIVO_COINCIDE if salida_alt_ms == salida_original_ms
                           else MOTIVO_SIN_TIEMPO)
        ficha["salida_alternativa_ms"] = salida_alt_ms
        ficha["salida_alternativa_iso"] = utc_iso(salida_alt_ms)
        return ficha

    serie = velas.get(symbol)
    if not serie:
        ficha["motivo"] = MOTIVO_SIN_VELAS
        return ficha
    vela_alt = serie.get(salida_alt_ms)
    if vela_alt is None:
        ficha["estado"] = ESTADO_NO_EVALUABLE
        ficha["motivo"] = MOTIVO_VELA_ALT_AUSENTE
        ficha["salida_alternativa_ms"] = salida_alt_ms
        ficha["salida_alternativa_iso"] = utc_iso(salida_alt_ms)
        return ficha
    if vela_alt["conflictiva"]:
        ficha["estado"] = ESTADO_NO_EVALUABLE
        ficha["motivo"] = MOTIVO_VELA_ALT_CONTRADICTORIA
        ficha["salida_alternativa_ms"] = salida_alt_ms
        ficha["salida_alternativa_iso"] = utc_iso(salida_alt_ms)
        return ficha
    precio_alt = float(vela_alt["open"])
    if not precio_alt > 0:
        ficha["estado"] = ESTADO_NO_EVALUABLE
        ficha["motivo"] = MOTIVO_PRECIO_ALT
        ficha["salida_alternativa_ms"] = salida_alt_ms
        ficha["salida_alternativa_iso"] = utc_iso(salida_alt_ms)
        return ficha

    entrada = float(original["precio_entrada"])
    salida_orig = float(original["precio_salida"])
    signo = 1.0 if direccion == "LONG" else -1.0
    ret_orig = signo * (salida_orig / entrada - 1.0) * 1e4
    ret_alt = signo * (precio_alt / entrada - 1.0) * 1e4
    if abs(ret_orig - float(original["retorno_bps"])) > TOL_RETORNO:
        raise SystemExit(f"retorno original incoherente en {ficha['terna']}")

    ficha.update({
        "estado": ESTADO_ADELANTADA,
        "motivo": None,
        "salida_alternativa_ms": salida_alt_ms,
        "salida_alternativa_iso": utc_iso(salida_alt_ms),
        "precio_salida_alternativa": precio_alt,
        "retorno_alternativo_bps": ret_alt,
        "delta_bps": ret_alt - ret_orig,
        "minutos_adelanto": (salida_original_ms - salida_alt_ms) // VENTANA_MS,
    })
    return ficha


def _verificar_bloques(
    propios: List[Dict[str, Any]],
    publicados: List[Dict[str, Any]],
    terna: str,
) -> None:
    if len(propios) != len(publicados):
        raise SystemExit(f"numero de bloques distinto en {terna}")
    for p, q in zip(propios, publicados):
        if int(p["k"]) != int(q["k"]):
            raise SystemExit(f"bloque desalineado en {terna}")
        if p["estado"] != q["estado"]:
            raise SystemExit(f"estado de bloque distinto en {terna} k={p['k']}")
        if p["estado"] != "resoluble":
            continue
        for clave in ("flujo_alineado", "precio_cierre", "delta_cierre_bps",
                      "profundidad_contraria", "disponibilidad_ms"):
            if p.get(clave) is None and q.get(clave) is None:
                continue
            if p.get(clave) is None or q.get(clave) is None:
                raise SystemExit(
                    f"bloque {clave} nulo distinto en {terna} k={p['k']}")
            if abs(float(p[clave]) - float(q[clave])) > 1e-6:
                raise SystemExit(
                    f"bloque {clave} distinto en {terna} k={p['k']}: "
                    f"{p[clave]} != {q[clave]}")
        if sorted(p["tipos"]) != sorted(q["tipos"]):
            raise SystemExit(f"tipos de bloque distintos en {terna} k={p['k']}")


# ---------------------------------------------------------------------------
# Agregados
# ---------------------------------------------------------------------------

def _delta(p: Dict[str, Any]) -> float:
    """Delta alineado; una salida conservada vale 0 (misma salida)."""
    return 0.0 if p.get("delta_bps") is None else float(p["delta_bps"])


def _retorno_alternativo(p: Dict[str, Any]) -> float:
    """Retorno alternativo; una salida conservada repite el original."""
    alt = p.get("retorno_alternativo_bps")
    return float(p["retorno_original_bps"]) if alt is None else float(alt)


def _resumen_delta(pares: List[Dict[str, Any]]) -> Dict[str, Any]:
    deltas = [_delta(p) for p in pares]
    if not deltas:
        return {"n": 0, "media_bps": None, "mediana_bps": None,
                "min_bps": None, "max_bps": None, "suma_bps": None,
                "mejoran": 0, "empeoran": 0, "iguales": 0}

    def _cubo(filtro):
        grupo = [p for p in pares if filtro(p)]
        valores = [_delta(p) for p in grupo]
        return {
            "n": len(grupo),
            "suma_bps": round(sum(valores), 4) if valores else 0.0,
            "media_bps": round(_media(valores), 4) if valores else None,
            "mediana_bps": round(_mediana(valores), 4) if valores else None,
        }

    return {
        "n": len(deltas),
        "media_bps": round(_media(deltas), 4),
        "mediana_bps": round(_mediana(deltas), 4),
        "min_bps": round(min(deltas), 4),
        "max_bps": round(max(deltas), 4),
        "suma_bps": round(sum(deltas), 4),
        "mejoran": sum(1 for d in deltas if d > TOL_DELTA),
        "empeoran": sum(1 for d in deltas if d < -TOL_DELTA),
        "iguales": sum(1 for d in deltas if abs(d) <= TOL_DELTA),
        "perdidas_recortadas": _cubo(
            lambda p: float(p["retorno_original_bps"]) < 0
            and _delta(p) > TOL_DELTA),
        "ganancias_sacrificadas": _cubo(
            lambda p: float(p["retorno_original_bps"]) > 0
            and _delta(p) < -TOL_DELTA),
        "perdidas_empeoradas": _cubo(
            lambda p: float(p["retorno_original_bps"]) < 0
            and _delta(p) < -TOL_DELTA),
        "ganancias_extra": _cubo(
            lambda p: float(p["retorno_original_bps"]) > 0
            and _delta(p) > TOL_DELTA),
        "original_neutro": _cubo(
            lambda p: abs(float(p["retorno_original_bps"])) <= TOL_DELTA
            and abs(_delta(p)) > TOL_DELTA),
        "original_negativo": sum(
            1 for p in pares if float(p["retorno_original_bps"]) < -TOL_DELTA),
        "original_positivo": sum(
            1 for p in pares if float(p["retorno_original_bps"]) > TOL_DELTA),
        "original_cero": sum(
            1 for p in pares if abs(float(p["retorno_original_bps"])) <= TOL_DELTA),
    }


def _resumen_niveles(pares: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Niveles brutos y netos de 16 bps en ambos lados (delta invariante)."""
    if not pares:
        return {"n": 0}
    orig = [float(p["retorno_original_bps"]) for p in pares]
    alt = [_retorno_alternativo(p) for p in pares]
    coste = COSTE_IDA_VUELTA_BPS
    return {
        "n": len(pares),
        "coste_ida_vuelta_bps": coste,
        "original_bruto_media_bps": round(_media(orig), 4),
        "original_bruto_mediana_bps": round(_mediana(orig), 4),
        "alternativa_bruto_media_bps": round(_media(alt), 4),
        "alternativa_bruto_mediana_bps": round(_mediana(alt), 4),
        "original_neto_media_bps": round(_media([x - coste for x in orig]), 4),
        "original_neto_mediana_bps": round(_mediana([x - coste for x in orig]), 4),
        "alternativa_neto_media_bps": round(_media([x - coste for x in alt]), 4),
        "alternativa_neto_mediana_bps": round(_mediana([x - coste for x in alt]), 4),
        "original_neto_positivo": sum(1 for x in orig if x - coste > 0),
        "alternativa_neto_positivo": sum(1 for x in alt if x - coste > 0),
        "delta_media_bps": round(_media(
            [a - o for a, o in zip(alt, orig)]), 4),
    }


def _por_direccion(pares: List[Dict[str, Any]]) -> Dict[str, Any]:
    salida = {}
    for d in ("LONG", "SHORT"):
        grupo = [p for p in pares if p["direccion"] == d]
        salida[d] = _resumen_delta(grupo)
    return salida


def _por_tipo(pares: List[Dict[str, Any]]) -> Dict[str, Any]:
    salida = {}
    for tipo in TIPOS_PRIORIDAD:
        grupo = [p for p in pares if p["primer_cambio_tipo"] == tipo]
        if grupo:
            salida[tipo] = _resumen_delta(grupo)
    return salida


def _niveles_por_direccion(pares: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {d: _resumen_niveles([p for p in pares if p["direccion"] == d])
            for d in ("LONG", "SHORT")}


def _ficha_caso(p: Dict[str, Any]) -> Dict[str, Any]:
    claves = (
        "symbol", "direccion", "cut_iso", "entrada_iso", "precio_entrada",
        "salida_original_iso", "precio_salida_original", "retorno_original_bps",
        "primer_cambio_tipo", "primer_cambio_k", "primer_cambio_inicio_iso",
        "primer_cambio_fin_iso", "disponibilidad_iso", "salida_alternativa_iso",
        "precio_salida_alternativa", "retorno_alternativo_bps", "delta_bps",
        "minutos_adelanto", "estado", "motivo", "hueco_k", "hueco_motivo",
    )
    return {k: p.get(k) for k in claves}


def agregados(
    fichas: List[Dict[str, Any]],
    verificacion: Dict[str, Any],
) -> Dict[str, Any]:
    estados = Counter(f["estado"] for f in fichas)
    motivos = Counter(f["motivo"] for f in fichas if f["motivo"])
    adelantadas = [f for f in fichas if f["estado"] == ESTADO_ADELANTADA]
    conservadas = [f for f in fichas if f["estado"] == ESTADO_CONSERVADA]
    no_evaluables = [f for f in fichas if f["estado"] == ESTADO_NO_EVALUABLE]
    evaluables = adelantadas + conservadas

    todos = _resumen_delta(evaluables)
    solo_adelantadas = _resumen_delta(adelantadas)

    n_adel = len(adelantadas)
    if n_adel < MIN_EPISODIOS:
        veredicto = "INSUFICIENTE"
    elif solo_adelantadas["media_bps"] > 0 and solo_adelantadas["mediana_bps"] > 0:
        veredicto = "MEJORA_EN_ESTA_MUESTRA"
    elif solo_adelantadas["media_bps"] < 0 and solo_adelantadas["mediana_bps"] < 0:
        veredicto = "EMPEORA_EN_ESTA_MUESTRA"
    else:
        veredicto = "SIN_DIRECCION_CLARA"

    cambios_identificados = sum(
        1 for f in fichas if f["primer_cambio_tipo"] is not None)
    minuto_distinto = sum(
        1 for f in fichas if f.get("minuto_distinto_por_definicion"))
    anticipados = sum(
        1 for f in fichas if f.get("disponibilidad_antes_de_entrada"))
    if anticipados:
        raise SystemExit(
            f"{anticipados} cambios disponibles antes de la entrada: look-ahead")

    return {
        "embudo": {
            "anclas": len(fichas),
            "anclas_patron": sum(1 for f in fichas if f["ancla_patron"]),
            "original_resoluble": sum(
                1 for f in fichas if f["original_estado"] == "resoluble"),
            "original_no_resoluble": sum(
                1 for f in fichas if f["original_estado"] != "resoluble"),
            "adelantada_resoluble": estados[ESTADO_ADELANTADA],
            "original_conservada": estados[ESTADO_CONSERVADA],
            "no_evaluable": estados[ESTADO_NO_EVALUABLE],
            "cambios_identificados": cambios_identificados,
            "sin_cambio_utilizable": motivos[MOTIVO_SIN_CAMBIO],
            "motivos": dict(sorted(motivos.items())),
            "pares_evaluables": len(evaluables),
            "pares_con_salida_adelantada": n_adel,
            "pares_sin_adelanto": len(evaluables) - n_adel,
            "cambios_disponibles_antes_de_la_entrada": anticipados,
            "cambios_por_bloque": dict(sorted(Counter(
                f["primer_cambio_k"] for f in adelantadas
                if f["primer_cambio_k"] is not None).items())),
        },
        "pares_todos": todos,
        "pares_adelantados": solo_adelantadas,
        "por_direccion_todos": _por_direccion(evaluables),
        "por_direccion_adelantados": _por_direccion(adelantadas),
        "por_tipo_adelantados": _por_tipo(adelantadas),
        "niveles_todos": _resumen_niveles(evaluables),
        "niveles_adelantados": _resumen_niveles(adelantadas),
        "niveles_por_direccion_adelantados": _niveles_por_direccion(adelantadas),
        "verificacion": verificacion,
        "minuto_de_salida_distinto_por_definicion": minuto_distinto,
        "veredicto": {
            "regla": "menos de 30 pares resolubles con salida efectivamente "
                     "adelantada -> INSUFICIENTE",
            "minimo_pares": MIN_EPISODIOS,
            "pares_adelantados": n_adel,
            "veredicto": veredicto,
            "media_bps": solo_adelantadas["media_bps"],
            "mediana_bps": solo_adelantadas["mediana_bps"],
            "mejoran": solo_adelantadas["mejoran"],
            "empeoran": solo_adelantadas["empeoran"],
            "iguales": solo_adelantadas["iguales"],
            "alcance": "esta ventana unicamente; 30 pares no validan la regla",
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _leer_jsonl(ruta: Path) -> List[Dict[str, Any]]:
    with io.open(ruta, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--cobertura", required=True)
    ap.add_argument("--klines", required=True)
    ap.add_argument("--derivados-anclas", required=True,
                    help="directorio con los derivados publicados de anclas")
    ap.add_argument("--derivados-cambios", required=True,
                    help="anclas_cambios.jsonl publicado del diagnostico de factores")
    ap.add_argument("--salida", required=True,
                    help="directorio para derivados voluminosos fuera de Git")
    ap.add_argument("--resumen", required=True,
                    help="JSON compacto apto para Git")
    ap.add_argument("--run-id", default="exp-v2-ventana-4-20261116a")
    args = ap.parse_args(argv)

    db = Path(args.db)
    cobertura_ruta = Path(args.cobertura)
    klines_ruta = Path(args.klines)
    derivados_anclas = Path(args.derivados_anclas)
    cambios_ruta = Path(args.derivados_cambios)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    for ruta in (db, cobertura_ruta, klines_ruta, cambios_ruta):
        if not ruta.exists():
            raise SystemExit(f"no existe la fuente: {ruta}")
    ruta_patron_pub = derivados_anclas / "episodios_patron_originales.jsonl"
    ruta_anclas_pub = derivados_anclas / "episodios_referencia_universo_igual.jsonl"
    for ruta in (ruta_patron_pub, ruta_anclas_pub):
        if not ruta.exists():
            raise SystemExit(f"no existe el derivado publicado: {ruta}")

    hashes_antes = {
        "research.db": _sha256_archivo(db),
        "cobertura_json": _sha256_archivo(cobertura_ruta),
        "consultas_klines.jsonl": _sha256_archivo(klines_ruta),
        "episodios_patron_originales.jsonl": _sha256_archivo(ruta_patron_pub),
        "episodios_referencia_universo_igual.jsonl": _sha256_archivo(ruta_anclas_pub),
        "anclas_cambios.jsonl": _sha256_archivo(cambios_ruta),
    }

    cobertura = cargar_cobertura(cobertura_ruta)
    db_declarada = str(cobertura.get("origen", {}).get("db_sha256", "")).lower()
    if db_declarada and db_declarada != hashes_antes["research.db"].lower():
        raise SystemExit(
            "research.db no coincide con el hash declarado en la cobertura")

    por_symbol, _audit_ventanas = construir_ventanas(db, cobertura, args.run_id)
    verificar_universo(por_symbol, cobertura)
    indice = {
        symbol: {int(v.ventana_inicio_ms): v for v in ventanas}
        for symbol, ventanas in por_symbol.items()
    }
    decisiones = evaluar_detector(por_symbol)
    _alertas_p, resumen_p = alertas_patron(por_symbol, decisiones)
    ternas_detalle = resumen_p["ternas_detalle"]
    por_terna = {t["terna"]: t for t in ternas_detalle}
    if len(por_terna) != len(ternas_detalle):
        raise SystemExit("ternas duplicadas en el detalle del detector")

    alertas_ref, _audit_ref = construir_alertas_referencia(ternas_detalle, por_symbol)
    velas, audit_velas = cargar_velas(klines_ruta, args.run_id)
    episodios, _audit_agrup = agrupar_con_tardias(alertas_ref, _alertas_p)
    if len(episodios) != 143:
        raise SystemExit(f"se esperaban 143 anclas; hay {len(episodios)}")
    anclas_patron = [e for e in episodios if e["ancla_patron"]]
    if len(anclas_patron) != 4:
        raise SystemExit(f"se esperaban 4 anclas con patron; hay {len(anclas_patron)}")

    flujo, libro, audit_filas = cargar_filas(db, args.run_id)

    cambios_pub = {c["terna"]: c for c in _leer_jsonl(cambios_ruta)}
    if len(cambios_pub) != 143:
        raise SystemExit(f"anclas_cambios publicadas incompletas: {len(cambios_pub)}")

    fichas: List[Dict[str, Any]] = []
    for e in episodios:
        pub = cambios_pub.get(e["terna"])
        if pub is None:
            raise SystemExit(f"ancla sin bloques publicados: {e['terna']}")
        fichas.append(evaluar_ancla(
            e, por_terna[e["terna"]], indice, flujo, libro, velas,
            bloques_publicados=pub["bloques"]))
    fichas.sort(key=lambda f: (f["cut_ms"], f["symbol"], f["direccion"]))

    verificacion_anclas = verificar_anclas_publicadas(
        [{"terna": f["terna"], "symbol": f["symbol"],
          "direccion": f["direccion"], "cut_ms": f["cut_ms"],
          "original": {"estado": f["original_estado"],
                       "retorno_bps": f["retorno_original_bps"]}}
         for f in fichas],
        _leer_jsonl(ruta_anclas_pub))
    verificacion = {
        "anclas_publicadas_coinciden": verificacion_anclas["coinciden"],
        "bloques_publicados_coinciden": len(fichas) * 6,
        "disponibilidad_publicada_registrada": len(fichas),
        "velas": {
            "simbolos": len(audit_velas.get("simbolos") or []),
            "velas_unicas": audit_velas.get("velas_unicas"),
            "contradictorias": audit_velas.get("velas_contradictorias"),
        },
        "filas": audit_filas,
    }

    hashes_despues = {
        "research.db": _sha256_archivo(db),
        "cobertura_json": _sha256_archivo(cobertura_ruta),
        "consultas_klines.jsonl": _sha256_archivo(klines_ruta),
        "episodios_patron_originales.jsonl": _sha256_archivo(ruta_patron_pub),
        "episodios_referencia_universo_igual.jsonl": _sha256_archivo(ruta_anclas_pub),
        "anclas_cambios.jsonl": _sha256_archivo(cambios_ruta),
    }
    if hashes_antes != hashes_despues:
        raise SystemExit("las fuentes cambiaron durante la evaluacion; abortado")

    metricas = agregados(fichas, verificacion)
    casos = [_ficha_caso(f) for f in fichas if f["ancla_patron"]]

    with io.open(salida / "anclas_salida_temprana.jsonl", "w",
                 encoding="utf-8", newline="\n") as f:
        for ficha in fichas:
            f.write(json.dumps(ficha, ensure_ascii=False, sort_keys=True) + "\n")
    with io.open(salida / "casos_patron_salida_temprana.jsonl", "w",
                 encoding="utf-8", newline="\n") as f:
        for caso in casos:
            f.write(json.dumps(caso, ensure_ascii=False, sort_keys=True) + "\n")
    with io.open(salida / "no_evaluables_salida_temprana.jsonl", "w",
                 encoding="utf-8", newline="\n") as f:
        for ficha in fichas:
            if ficha["estado"] == ESTADO_NO_EVALUABLE:
                f.write(json.dumps(ficha, ensure_ascii=False, sort_keys=True) + "\n")
    with io.open(salida / "conservadas_salida_temprana.jsonl", "w",
                 encoding="utf-8", newline="\n") as f:
        for ficha in fichas:
            if ficha["estado"] == ESTADO_CONSERVADA:
                f.write(json.dumps(ficha, ensure_ascii=False, sort_keys=True) + "\n")

    resumen = {
        "version": VERSION_SALIDA,
        "version_diagnostico_reutilizado": VERSION_DIAGNOSTICO,
        "version_anclas": VERSION_COMPARACION,
        "run_id": args.run_id,
        "pregunta": "manteniendo la entrada original, cerrar al primer cambio "
                    "observable recorta mas perdidas de las ganancias que "
                    "sacrifica?",
        "reglas_fijadas": {
            "universo": "143 anclas comunes publicadas; las 4 del patron estan "
                        "dentro y no se suman otra vez",
            "entrada": "apertura del primer minuto estrictamente posterior al "
                       "corte; no se mueve",
            "salida_original": "apertura a 5 minutos de la entrada",
            "cambio": "primer bloque b_0..b_5 con la regla publicada y prioridad "
                      "giro > debilitamiento > precio_sin_avance > "
                      "profundidad_deja_de_caer; umbrales sin ajustar",
            "elegibilidad_b_0": "b_0 cubre el primer minuto posterior a la "
                                "ventana de senal y su flujo solo esta "
                                "disponible despues de la entrada: se admite. "
                                "Se verifica que ningun cambio resulte "
                                "disponible antes de la entrada",
            "hueco": "un bloque no utilizable antes del primer cambio deja el "
                     "ancla como no evaluable; un hueco no es sin cambio",
            "bloques_relevantes": "solo los que cumplen fin + 1 min < salida "
                                  "original (b_0..b_3)",
            "disponibilidad": "maximo de los datos que acreditan el cambio: "
                              "cierre del bloque y as_of del flujo; mas as_of del "
                              "cierre base si es precio_sin_avance; mas as_of del "
                              "libro si es profundidad_deja_de_caer",
            "salida_alternativa": "apertura del primer minuto estrictamente "
                                  "posterior a la disponibilidad, solo si es "
                                  "estrictamente anterior a la salida original",
            "delta": "retorno alternativo menos retorno original, alineado por "
                     "direccion; positivo = mejora",
            "coste_sensibilidad_bps": COSTE_IDA_VUELTA_BPS,
            "veredicto": "menos de 30 pares con salida efectivamente adelantada "
                         "-> INSUFICIENTE",
        },
        "origen": {
            "hashes": hashes_antes,
            "fuentes_intactas": hashes_antes == hashes_despues,
        },
        **metricas,
        "casos_patron": casos,
        "limitaciones": [
            "captura ya usada en el desarrollo del detector: hallazgo "
            "exploratorio, no prueba independiente",
            "aperturas de velas como precios simulados: no son fills, no "
            "incluyen latencia ni impacto",
            "los agregados de 1 minuto no se atribuyen a un segundo exacto",
            "una caida o subida de la profundidad media no demuestra retirada "
            "ni reposicion de ordenes",
            "funding UNKNOWN; 16 bps es solo sensibilidad; retornos brutos",
            "la salida alternativa comparte entrada con la original: el delta "
            "mide solo el cambio de salida",
        ],
    }

    destino = Path(args.resumen)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with io.open(destino, "w", encoding="utf-8", newline="\n") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    print(json.dumps({
        "estado": "ok",
        "anclas": len(fichas),
        "anclas_patron": len(casos),
        "original_resoluble": metricas["embudo"]["original_resoluble"],
        "pares_evaluables": metricas["embudo"]["pares_evaluables"],
        "adelantadas": metricas["embudo"]["adelantada_resoluble"],
        "conservadas": metricas["embudo"]["original_conservada"],
        "no_evaluables": metricas["embudo"]["no_evaluable"],
        "motivos": metricas["embudo"]["motivos"],
        "cambios_por_bloque": metricas["embudo"]["cambios_por_bloque"],
        "delta_media_adelantadas": metricas["pares_adelantados"]["media_bps"],
        "delta_mediana_adelantadas": metricas["pares_adelantados"]["mediana_bps"],
        "delta_suma_adelantadas": metricas["pares_adelantados"]["suma_bps"],
        "mejoran": metricas["pares_adelantados"]["mejoran"],
        "empeoran": metricas["pares_adelantados"]["empeoran"],
        "iguales": metricas["pares_adelantados"]["iguales"],
        "veredicto": metricas["veredicto"]["veredicto"],
        "resumen": str(destino),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
