# -*- coding: utf-8 -*-
"""Diagnostico de factores de los cuatro casos de SECUENCIA-PRESION-V1.

Pregunta: que distinguia a STRKUSDT LONG (unico ganador de la ventana 4) de
ARIAUSDT LONG y de los dos BLESSUSDT SHORT (perdedores), y cuando se podia
conocer cada factor.

Este bloque NO prueba "esperar un minuto" como regla ni invierte senales por
defecto. Mide tres cosas:

  1. En el corte original:
     a) avance del precio frente al comportamiento reciente del mismo token
        (dos normalizaciones independientes);
     b) si la presion agresora neta crecia en importe o si Q subia sobre todo
        porque caia la profundidad contraria (descomposicion aditiva de log Q);
     c) si cada tramo adicional de presion seguia desplazando el precio o si el
        avance se frenaba (impacto marginal por tramo y ultimos 30 s).
  2. Despues de la alerta: el primer cambio respaldado por los datos
     (debilitamiento o giro del flujo, la profundidad contraria deja de caer, o
     el precio deja de avanzar pese a la presion), con el momento en que ocurrio
     y el momento en que estuvo disponible.
  3. Las mismas mediciones sobre las 143 anclas comunes, separando LONG y SHORT
     y mostrando los faltantes. Se distingue lo visible al decidir de lo que solo
     aparecio despues. Si un cambio posterior se mide como senal, se mide desde
     un corte posterior a su disponibilidad, nunca con el precio de entrada
     anterior. El horizonte de medicion sigue siendo 5 minutos.

Reglas fijadas ANTES de calcular:
  - Solo lectura de la captura publicada y de sus derivados ya publicados. Sin
    Binance, sin capturas nuevas, sin ordenes, sin cambios de patron, umbrales,
    horizonte, agrupacion ni estrategia.
  - Los cuatro casos son las 4 anclas con patron del universo igualado de 501
    ternas; se verifican contra `episodios_patron_originales.jsonl`.
  - Las 143 anclas comunes se reconstruyen desde la base y la cobertura y se
    verifican contra `episodios_referencia_universo_igual.jsonl`.
  - Ninguna medida se convierte en condicion de la estrategia. Los cuatro casos
    solo formulan hipotesis.

Normalizacion del avance (dos medidas, fijadas antes de calcular):
  - `avance_vs_3m_flujo`: referencia = mediana de los movimientos absolutos de
    bloques de 3 ventanas contiguas y NO solapadas del mismo simbolo, tomados
    desde el final hacia atras, con filas de flujo OK y `as_of_ms >= bucket_end`,
    terminando exactamente en el inicio de la terna. Minimo 6 bloques (18 min).
    Sin tramo contiguo, menos de 6 bloques o referencia cero -> UNKNOWN.
  - `avance_vs_ternas`: la medida ya publicada (ternas previas no solapadas del
    universo acreditado, minimo 6). Se reutiliza sin cambios.
  - El avance bruto es s*(c3/c1-1)*1e4, s=+1 LONG, -1 SHORT.

Descomposicion de Q (fijada antes de calcular):
  - Q = |F|/D, con F = flujo neto alineado y D = profundidad contraria.
  - dlogQ = log(F3/F1) - log(D3/D1) = log(Q3/Q1).
  - aporte del importe = 100*log(F3/F1)/dlogQ;
    aporte de la profundidad = 100*(-log(D3/D1))/dlogQ. Suman 100.
  - No se atribuye la caida de profundidad media a retirada o reposicion de
    ordenes individuales.

Impacto marginal (fijado antes de calcular):
  - tramo 2: cierre 1 -> cierre 2; tramo 3: cierre 2 -> cierre 3.
  - impacto_k = delta_precio_k_bps / (F_k/1000), bps por 1000 USDT alineados.
  - frenada_impacto = impacto_3 < impacto_2 y F3 >= F2.
  - frenada_avance = |delta_3| < |delta_2| y F3 >= F2.
  - impacto_2 <= 0 -> UNKNOWN (no se divide).
  - Todo esto se conoce en el corte.

Ultimos 30 s de la terna (fijado antes de calcular):
  - Los 3 buckets de 10 s que terminan en el cierre de la tercera ventana, con
    `data_quality == "OK"` y `as_of_ms >= bucket_end`.
  - flujo alineado de 30 s, delta de precio de 30 s, giro_30s (flujo <= 0),
    presion_sin_avance_30s (flujo > 0 y delta <= 0).
  - concentracion_10s = max|delta_i| / |sum delta_i| sobre los 6 buckets de la
    tercera ventana; UNKNOWN si falta alguno. Es descriptiva, sin umbral.

Primer cambio posterior a la alerta (fijado antes de calcular):
  - Bloques de 1 minuto alineados al reloj: b_k = floor(corte/60s)*60s + k*60s,
    k=0..5. b_0 es el minuto en que cae el corte (como maximo 60 s antes del
    corte; en estos casos <= 4.53 s). Se usa el minuto completo como unidad de
    evidencia, igual que la senal.
  - Bloque util: fila de flujo 1m con run_id, `data_quality == "OK"` y
    `as_of_ms >= bucket_end`. Si no, UNKNOWN con motivo y se sigue buscando.
  - Cambios (alineados por direccion):
      giro: flujo <= 0;
      debilitamiento: 0 < flujo < flujo de la tercera ventana;
      precio_sin_avance: flujo > 0 y delta de cierre <= 0;
      profundidad_deja_de_caer: profundidad media del bloque > D3 (libro con
        run_id, sin degraded/depth_gaps/crossed y `as_of_ms >= bucket_end`).
    El delta de cierre se mide contra el cierre del bloque inmediatamente
    anterior; si ese bloque no es util, queda UNKNOWN (no se rellena el hueco).
  - primer_cambio = el primer bloque con algun cambio; prioridad de etiqueta:
    giro, debilitamiento, precio_sin_avance, profundidad.
  - primer_giro, primer_debilitamiento, primer_precio_sin_avance y
    primer_profundidad_deja_de_caer se registran por separado.
  - La disponibilidad del cambio = max(fin del bloque, as_of del flujo, as_of del
    libro si se uso). El corte del cambio es esa disponibilidad. La entrada es la
    apertura del primer minuto estrictamente posterior; la salida, 5 minutos
    despues. La reversion solo se mide si el cambio es un giro, con la MISMA
    entrada y salida que la continuacion; nunca reutiliza la entrada original.
  - Sin bloques utiles -> UNKNOWN. Sin cambio en los 6 bloques -> sin_cambio.
  - Los agregados de 1 minuto y de 10 s no se atribuyen a un segundo exacto.

Controles (143 anclas comunes):
  - Mismas medidas, separadas por direccion, con conteo de faltantes.
  - Se distingue lo visible en el corte (giro_30s, frenada_impacto,
    presion_sin_avance_30s, avance normalizado, aporte del importe,
    concentracion_10s) de lo que solo aparecio despues (primer cambio/giro).
  - Los cruces son descriptivos: no hay umbral ni prueba de seleccion.
  - Regla formal predeclarada: con >= 30 pares comparables, "muestra mejora" solo
    si la media y la mediana del delta son positivas; por debajo, datos
    insuficientes.

Costes: solo la sensibilidad documentada de 16 bps ida y vuelta. Funding
UNKNOWN. Los retornos son brutos, no P&L.
"""

import argparse
import io
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
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
    MIN_TERN_PREVIAS,
    _opuesta,
    _signo,
    _ventana_detalle,
    cargar_filas,
    extension_previa,
    ternas_previas_no_solapadas,
    verificar_anclas_publicadas,
    verificar_casos_publicados,
)
from replay_patron_ventana4 import (  # noqa: E402
    COSTE_IDA_VUELTA_BPS,
    HORIZONTE_MS,
    MIN_EPISODIOS,
    VENTANA_MS,
    _mediana,
    _media,
    _redondear,
    _referencia_entrada,
    _sha256_archivo,
    alertas_patron,
    cargar_cobertura,
    cargar_velas,
    construir_ventanas,
    evaluar_detector,
    resolver_alerta,
    resumir_episodios,
    utc_iso,
    verificar_universo,
)

VERSION_DIAGNOSTICO = "diagnostico-factores-v1"
VERSION_ANCLAS = VERSION_COMPARACION

MIN_BLOQUES_3M = 6          # 18 minutos de historia propia
MAX_BLOQUES_CAMBIO = 6      # b_0..b_5: minuto del corte + 5 siguientes
EPS_FLUJO = 1e-9
BUCKET_10S_MS = 10_000

MOTIVO_HISTORIA_NO_CONTIGUA = "historia_no_contigua"
MOTIVO_HISTORIA_INSUFICIENTE = "historia_insuficiente"
MOTIVO_REFERENCIA_CERO = "referencia_cero"
MOTIVO_FLUJO_AUSENTE = "flujo_ausente"
MOTIVO_FLUJO_INCOMPLETO = "flujo_incompleto"
MOTIVO_FLUJO_SIN_DISPONIBILIDAD = "flujo_sin_disponibilidad"
MOTIVO_FLUJO_INCOHERENTE = "flujo_incoherente"
MOTIVO_LIBRO_AUSENTE = "libro_ausente"
MOTIVO_LIBRO_INCOMPLETO = "libro_incompleto"
MOTIVO_LIBRO_SIN_DISPONIBILIDAD = "libro_sin_disponibilidad"
MOTIVO_BUCKETS_10S = "buckets_10s_incompletos"
MOTIVO_SIN_BLOQUES = "sin_bloques_utilizables"
MOTIVO_SIN_CAMBIO = "sin_cambio_en_horizonte"
MOTIVO_NO_APLICA = "no_aplica"
MOTIVO_PRESION_NO_POSITIVA = "presion_o_profundidad_no_positiva"
MOTIVO_Q_NO_CRECE = "q_no_crece"
MOTIVO_IMPACTO_2_NO_POSITIVO = "impacto_2_no_positivo"
MOTIVO_FLUJO_NETO_CERO = "flujo_neto_cero"

ESTADO_RESOLUBLE = "resoluble"
ESTADO_UNKNOWN = "UNKNOWN"
ESTADO_CAMBIO = "cambio_observado"
ESTADO_SIN_CAMBIO = "sin_cambio"


# ---------------------------------------------------------------------------
# Filas: utilidad, disponibilidad y coherencia
# ---------------------------------------------------------------------------

def _fila_flujo_util(f: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    if f is None:
        return False, MOTIVO_FLUJO_AUSENTE
    if f.get("buy_notional") is None or f.get("sell_notional") is None:
        return False, MOTIVO_FLUJO_INCOMPLETO
    if str(f.get("data_quality")) != "OK":
        return False, MOTIVO_FLUJO_INCOMPLETO
    fin = f.get("bucket_end")
    if fin is None:
        fin = int(f.get("bucket_start", 0)) + VENTANA_MS
    as_of = f.get("as_of_ms")
    if as_of is None:
        return False, MOTIVO_FLUJO_SIN_DISPONIBILIDAD
    if int(as_of) < int(fin):
        return False, MOTIVO_FLUJO_SIN_DISPONIBILIDAD
    return True, None


def _fila_libro_util(b: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    if b is None:
        return False, MOTIVO_LIBRO_AUSENTE
    if b.get("bid20_mean") is None or b.get("ask20_mean") is None:
        return False, MOTIVO_LIBRO_INCOMPLETO
    for clave in ("degraded", "depth_gaps", "crossed"):
        if b.get(clave) is None or int(b[clave]) != 0:
            return False, MOTIVO_LIBRO_INCOMPLETO
    fin = b.get("bucket_end")
    if fin is None:
        fin = int(b.get("bucket_start", 0)) + VENTANA_MS
    as_of = b.get("as_of_ms")
    if as_of is None:
        return False, MOTIVO_LIBRO_SIN_DISPONIBILIDAD
    if int(as_of) < int(fin):
        return False, MOTIVO_LIBRO_SIN_DISPONIBILIDAD
    return True, None


def _bucket_10s_util(f: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    if f is None:
        return False, "bucket_10s_ausente"
    if f.get("buy_notional") is None or f.get("sell_notional") is None:
        return False, "bucket_10s_incompleto"
    if str(f.get("data_quality")) != "OK":
        return False, "bucket_10s_incompleto"
    fin = f.get("bucket_end")
    if fin is None:
        fin = int(f.get("bucket_start", 0)) + BUCKET_10S_MS
    as_of = f.get("as_of_ms")
    if as_of is None:
        return False, "bucket_10s_sin_disponibilidad"
    if int(as_of) < int(fin):
        return False, "bucket_10s_sin_disponibilidad"
    return True, None


def cargar_filas_10s(
    db_path: Path, run_id: str
) -> Tuple[Dict[Tuple[str, int], Dict[str, Any]], Dict[str, Any]]:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    filas: Dict[Tuple[str, int], Dict[str, Any]] = {}
    audit: Counter = Counter()
    for r in con.execute("select * from research_flow_10s"):
        if r["run_id"] != run_id:
            audit["flujo_10s_otro_run_id"] += 1
            continue
        filas[(r["symbol"], int(r["bucket_start"]))] = dict(r)
    con.close()
    return filas, {
        "filas_flujo_10s": len(filas),
        "flujo_10s_otro_run_id": audit["flujo_10s_otro_run_id"],
    }


# ---------------------------------------------------------------------------
# 1a. Avance frente al comportamiento reciente del mismo token
# ---------------------------------------------------------------------------

def bloques_3m_previos(
    flujo: Dict[Tuple[str, int], Dict[str, Any]], symbol: str, t0: int
) -> Tuple[List[Dict[str, Any]], List[List[Dict[str, Any]]]]:
    """Tramo contiguo que termina en `t0` y bloques de 3 ventanas no solapados.

    Se camina hacia atras desde `t0 - 60 s` mientras exista fila util y
    contigua. Los bloques se toman desde el final hacia atras de tres en tres:
    ninguno comparte ventanas con otro ni con la terna evaluada.
    """
    run: List[Dict[str, Any]] = []
    t = int(t0)
    while True:
        f = flujo.get((symbol, t - VENTANA_MS))
        ok, _ = _fila_flujo_util(f)
        if not ok:
            break
        run.append(f)
        t -= VENTANA_MS
    run.reverse()
    bloques: List[List[Dict[str, Any]]] = []
    i = len(run)
    while i >= 3:
        bloques.append(run[i - 3:i])
        i -= 3
    bloques.reverse()
    return run, bloques


def avance_vs_3m_flujo(
    flujo: Dict[Tuple[str, int], Dict[str, Any]],
    symbol: str,
    t0: int,
    avance_bps: float,
) -> Dict[str, Any]:
    run, bloques = bloques_3m_previos(flujo, symbol, t0)
    movimientos: List[float] = []
    for bloque in bloques:
        p0 = float(bloque[0]["price_close"])
        p2 = float(bloque[2]["price_close"])
        movimientos.append(abs(p2 / p0 - 1.0) * 1e4)
    n = len(bloques)
    base = {
        "minimo_bloques": MIN_BLOQUES_3M,
        "bloques_disponibles": n,
        "minutos_previos_contiguos": len(run),
        "rango_previo_ms": [int(run[0]["bucket_start"]), int(t0)] if run else None,
        "referencia_bps": _redondear(_mediana(movimientos)) if movimientos else None,
        "avance_bruto_bps": _redondear(avance_bps),
    }
    if n < MIN_BLOQUES_3M:
        return {**base, "estado": ESTADO_UNKNOWN,
                "motivo": MOTIVO_HISTORIA_INSUFICIENTE}
    referencia = _mediana(movimientos)
    if referencia is None or referencia <= 0:
        return {**base, "estado": ESTADO_UNKNOWN, "motivo": MOTIVO_REFERENCIA_CERO}
    return {
        **base,
        "estado": ESTADO_RESOLUBLE,
        "motivo": None,
        "extension_normalizada": _redondear(abs(avance_bps) / referencia),
        "movimientos_bps": [_redondear(x) for x in movimientos],
    }


def _envolver_extension(ext: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza el vocabulario publicado (`no_resoluble`) a `UNKNOWN`."""
    salida = {k: v for k, v in ext.items() if k not in ("estado", "motivo")}
    salida["estado"] = ESTADO_RESOLUBLE if ext.get("estado") == "resoluble" else ESTADO_UNKNOWN
    salida["motivo"] = ext.get("motivo")
    return salida


# ---------------------------------------------------------------------------
# 1b. Descomposicion de Q: importe frente a profundidad
# ---------------------------------------------------------------------------

def descomponer_q(a: Any, b: Any, c: Any, direccion: str) -> Dict[str, Any]:
    s = _signo(direccion)
    f1 = s * (float(a.buy_notional) - float(a.sell_notional))
    f3 = s * (float(c.buy_notional) - float(c.sell_notional))
    d1 = a.profundidad_contraria(direccion)
    d3 = c.profundidad_contraria(direccion)
    base = {
        "flujo_alineado_1": _redondear(f1),
        "flujo_alineado_3": _redondear(f3),
        "profundidad_1": _redondear(d1),
        "profundidad_3": _redondear(d3),
    }
    if (f1 <= 0 or f3 <= 0 or d1 is None or d3 is None
            or float(d1) <= 0 or float(d3) <= 0):
        return {**base, "estado": ESTADO_UNKNOWN,
                "motivo": MOTIVO_PRESION_NO_POSITIVA}
    d1 = float(d1)
    d3 = float(d3)
    dlq = math.log(f3 / f1) - math.log(d3 / d1)
    if dlq <= 0:
        return {**base, "estado": ESTADO_UNKNOWN, "motivo": MOTIVO_Q_NO_CRECE}
    aporte_importe = 100.0 * math.log(f3 / f1) / dlq
    aporte_profundidad = 100.0 * (-math.log(d3 / d1)) / dlq
    return {
        **base,
        "estado": ESTADO_RESOLUBLE,
        "motivo": None,
        "q_1": _redondear(f1 / d1),
        "q_3": _redondear(f3 / d3),
        "q_crecimiento": _redondear((f3 / d3) / (f1 / d1)),
        "aporte_importe_pct": _redondear(aporte_importe),
        "aporte_profundidad_pct": _redondear(aporte_profundidad),
        "importe_crece": bool(f3 > f1),
        "profundidad_cae_pct": _redondear((d3 / d1 - 1.0) * 100.0),
        "notional_total_crece": bool(
            (float(c.buy_notional) + float(c.sell_notional))
            > (float(a.buy_notional) + float(a.sell_notional))
        ),
    }


# ---------------------------------------------------------------------------
# 1c. Impacto marginal por tramo
# ---------------------------------------------------------------------------

def impacto_por_tramo(a: Any, b: Any, c: Any, direccion: str) -> Dict[str, Any]:
    s = _signo(direccion)
    p1 = float(a.precio_cierre)
    p2 = float(b.precio_cierre)
    p3 = float(c.precio_cierre)
    f2 = s * (float(b.buy_notional) - float(b.sell_notional))
    f3 = s * (float(c.buy_notional) - float(c.sell_notional))
    d2 = s * (p2 / p1 - 1.0) * 1e4
    d3 = s * (p3 / p2 - 1.0) * 1e4
    base = {
        "delta_2_bps": _redondear(d2),
        "delta_3_bps": _redondear(d3),
        "flujo_alineado_2": _redondear(f2),
        "flujo_alineado_3": _redondear(f3),
    }
    if f2 <= 0 or f3 <= 0:
        return {**base, "estado": ESTADO_UNKNOWN,
                "motivo": MOTIVO_PRESION_NO_POSITIVA}
    impacto_2 = d2 / (f2 / 1000.0)
    impacto_3 = d3 / (f3 / 1000.0)
    base.update({
        "impacto_2_bps_por_1k": _redondear(impacto_2),
        "impacto_3_bps_por_1k": _redondear(impacto_3),
    })
    if impacto_2 <= 0:
        return {**base, "estado": ESTADO_UNKNOWN,
                "motivo": MOTIVO_IMPACTO_2_NO_POSITIVO}
    total = d2 + d3
    return {
        **base,
        "estado": ESTADO_RESOLUBLE,
        "motivo": None,
        "impacto_relativo": _redondear(impacto_3 / impacto_2),
        "frenada_impacto": bool(impacto_3 < impacto_2 and f3 >= f2),
        "frenada_avance": bool(abs(d3) < abs(d2) and f3 >= f2),
        "avance_ultima_ventana_pct": (
            _redondear(100.0 * d3 / total) if total != 0 else None),
    }


# ---------------------------------------------------------------------------
# 1d. Ultimos 30 s y concentracion de la tercera ventana
# ---------------------------------------------------------------------------

def ultimos_30s(
    flujo_10s: Dict[Tuple[str, int], Dict[str, Any]],
    symbol: str,
    fin_c: int,
    direccion: str,
) -> Dict[str, Any]:
    inicio = int(fin_c) - 30_000
    filas: List[Dict[str, Any]] = []
    faltantes: List[Dict[str, Any]] = []
    for i in range(3):
        t = inicio + i * BUCKET_10S_MS
        f = flujo_10s.get((symbol, t))
        ok, motivo = _bucket_10s_util(f)
        if not ok:
            faltantes.append({"inicio_ms": t, "motivo": motivo})
        else:
            filas.append(f)
    base = {
        "ventana_ms": [inicio, int(fin_c)],
        "buckets_presentes": len(filas),
        "buckets_faltantes": faltantes,
    }
    if faltantes:
        return {**base, "estado": ESTADO_UNKNOWN, "motivo": MOTIVO_BUCKETS_10S}
    s = _signo(direccion)
    alineado = s * sum(
        float(f["buy_notional"]) - float(f["sell_notional"]) for f in filas)
    p0 = float(filas[0]["price_open"])
    p1 = float(filas[-1]["price_close"])
    delta = s * (p1 / p0 - 1.0) * 1e4
    return {
        **base,
        "estado": ESTADO_RESOLUBLE,
        "motivo": None,
        "flujo_alineado_30s": _redondear(alineado),
        "delta_precio_30s_bps": _redondear(delta),
        "giro_30s": bool(alineado <= EPS_FLUJO),
        "presion_sin_avance_30s": bool(alineado > EPS_FLUJO and delta <= 0),
        "as_of_max_ms": max(int(f["as_of_ms"]) for f in filas),
    }


def concentracion_10s(
    flujo_10s: Dict[Tuple[str, int], Dict[str, Any]], symbol: str, fin_c: int
) -> Dict[str, Any]:
    inicio = int(fin_c) - VENTANA_MS
    filas: List[Dict[str, Any]] = []
    for i in range(6):
        t = inicio + i * BUCKET_10S_MS
        f = flujo_10s.get((symbol, t))
        ok, motivo = _bucket_10s_util(f)
        if not ok:
            return {
                "estado": ESTADO_UNKNOWN,
                "motivo": MOTIVO_BUCKETS_10S,
                "bucket_faltante_ms": t,
                "detalle": motivo,
            }
        filas.append(f)
    deltas = [float(f["buy_notional"]) - float(f["sell_notional"]) for f in filas]
    total = sum(deltas)
    if abs(total) <= EPS_FLUJO:
        return {
            "estado": ESTADO_UNKNOWN,
            "motivo": MOTIVO_FLUJO_NETO_CERO,
            "buckets": [_redondear(x) for x in deltas],
        }
    i_max = max(range(len(deltas)), key=lambda i: abs(deltas[i]))
    return {
        "estado": ESTADO_RESOLUBLE,
        "motivo": None,
        "concentracion": _redondear(max(abs(x) for x in deltas) / abs(total)),
        "bucket_dominante_ms": int(filas[i_max]["bucket_start"]),
        "bucket_dominante_iso": utc_iso(int(filas[i_max]["bucket_start"])),
        "buckets": [_redondear(x) for x in deltas],
    }


# ---------------------------------------------------------------------------
# 2. Primer cambio posterior a la alerta
# ---------------------------------------------------------------------------

def _bloque_post(
    flujo: Dict[Tuple[str, int], Dict[str, Any]],
    libro: Dict[Tuple[str, int], Dict[str, Any]],
    symbol: str,
    t: int,
    direccion: str,
    alineado_3: float,
    d3: Optional[float],
    base_cierre: Optional[float],
) -> Dict[str, Any]:
    fin = int(t) + VENTANA_MS
    f = flujo.get((symbol, int(t)))
    ok, motivo = _fila_flujo_util(f)
    bloque: Dict[str, Any] = {
        "inicio_ms": int(t),
        "fin_ms": fin,
        "inicio_iso": utc_iso(int(t)),
        "fin_iso": utc_iso(fin),
        "estado": ESTADO_UNKNOWN,
        "motivo": motivo,
        "flujo_alineado": None,
        "precio_cierre": None,
        "delta_cierre_bps": None,
        "profundidad_contraria": None,
        "profundidad_estado": ESTADO_UNKNOWN,
        "profundidad_motivo": MOTIVO_LIBRO_AUSENTE,
        "disponibilidad_ms": None,
        "disponibilidad_iso": None,
        "tipos": [],
        "es_giro": False,
        "es_debilitamiento": False,
        "es_precio_sin_avance": False,
        "es_profundidad_deja_de_caer": False,
    }
    if not ok:
        return bloque
    if (int(f.get("bucket_start", -1)) != int(t)
            or int(f.get("bucket_end", -1)) != fin):
        bloque["motivo"] = MOTIVO_FLUJO_INCOHERENTE
        return bloque

    s = _signo(direccion)
    alineado = s * (float(f["buy_notional"]) - float(f["sell_notional"]))
    cierre = float(f["price_close"])
    bloque.update({
        "estado": ESTADO_RESOLUBLE,
        "motivo": None,
        "flujo_alineado": _redondear(alineado),
        "precio_cierre": cierre,
        "as_of_flow_ms": int(f["as_of_ms"]),
    })
    if base_cierre is not None:
        bloque["delta_cierre_bps"] = _redondear(
            s * (cierre / float(base_cierre) - 1.0) * 1e4)

    b = libro.get((symbol, int(t)))
    bok, bmotivo = _fila_libro_util(b)
    if bok:
        d = b["ask20_mean"] if direccion == "LONG" else b["bid20_mean"]
        if d is None or float(d) <= 0:
            bloque["profundidad_motivo"] = MOTIVO_LIBRO_INCOMPLETO
        else:
            bloque["profundidad_contraria"] = _redondear(float(d))
            bloque["profundidad_estado"] = ESTADO_RESOLUBLE
            bloque["profundidad_motivo"] = None
            bloque["as_of_book_ms"] = int(b["as_of_ms"])
    else:
        bloque["profundidad_motivo"] = bmotivo

    tipos: List[str] = []
    if alineado <= EPS_FLUJO:
        tipos.append("giro")
    elif alineado < alineado_3 - EPS_FLUJO:
        tipos.append("debilitamiento")
    if (alineado > EPS_FLUJO
            and bloque["delta_cierre_bps"] is not None
            and bloque["delta_cierre_bps"] <= 0):
        tipos.append("precio_sin_avance")
    if (bloque["profundidad_estado"] == ESTADO_RESOLUBLE
            and d3 is not None
            and bloque["profundidad_contraria"] is not None
            and float(bloque["profundidad_contraria"]) > float(d3)):
        tipos.append("profundidad_deja_de_caer")

    disponibilidad = fin
    disponibilidad = max(disponibilidad, int(f["as_of_ms"]))
    if bloque["profundidad_estado"] == ESTADO_RESOLUBLE:
        disponibilidad = max(disponibilidad, int(b["as_of_ms"]))
    bloque.update({
        "disponibilidad_ms": disponibilidad,
        "disponibilidad_iso": utc_iso(disponibilidad),
        "tipos": tipos,
        "es_giro": "giro" in tipos,
        "es_debilitamiento": "debilitamiento" in tipos,
        "es_precio_sin_avance": "precio_sin_avance" in tipos,
        "es_profundidad_deja_de_caer": "profundidad_deja_de_caer" in tipos,
    })
    return bloque


def _evento(bloque: Dict[str, Any], tipo: str,
            no_usables_antes: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "estado": ESTADO_CAMBIO,
        "motivo": None,
        "tipo": tipo,
        "k": bloque["k"],
        "inicio_ms": bloque["inicio_ms"],
        "fin_ms": bloque["fin_ms"],
        "inicio_iso": bloque["inicio_iso"],
        "fin_iso": bloque["fin_iso"],
        "disponibilidad_ms": bloque["disponibilidad_ms"],
        "disponibilidad_iso": bloque["disponibilidad_iso"],
        "flujo_alineado": bloque["flujo_alineado"],
        "precio_cierre": bloque["precio_cierre"],
        "delta_cierre_bps": bloque["delta_cierre_bps"],
        "profundidad_contraria": bloque["profundidad_contraria"],
        "tipos": list(bloque["tipos"]),
        "es_giro": tipo == "giro",
        "bloques_no_usables_antes": no_usables_antes,
    }


def _sin_evento(bloques: List[Dict[str, Any]], motivo: str) -> Dict[str, Any]:
    usables = [b for b in bloques if b["estado"] == ESTADO_RESOLUBLE]
    estado = ESTADO_SIN_CAMBIO if usables else ESTADO_UNKNOWN
    return {
        "estado": estado,
        "motivo": motivo if estado == ESTADO_UNKNOWN else None,
        "tipo": None,
        "k": None,
        "inicio_ms": None,
        "fin_ms": None,
        "inicio_iso": None,
        "fin_iso": None,
        "disponibilidad_ms": None,
        "disponibilidad_iso": None,
        "flujo_alineado": None,
        "precio_cierre": None,
        "delta_cierre_bps": None,
        "profundidad_contraria": None,
        "tipos": [],
        "es_giro": False,
        "bloques_utiles": len(usables),
        "bloques_totales": len(bloques),
    }


def _primer_evento(
    bloques: List[Dict[str, Any]], campo: str, tipo: str
) -> Dict[str, Any]:
    no_usables: List[Dict[str, Any]] = []
    for b in bloques:
        if b["estado"] != ESTADO_RESOLUBLE:
            no_usables.append({
                "k": b["k"],
                "inicio_ms": b["inicio_ms"],
                "motivo": b["motivo"],
            })
            continue
        if b[campo]:
            return _evento(b, tipo, list(no_usables))
    return _sin_evento(bloques, MOTIVO_SIN_CAMBIO)


def analizar_bloques(
    flujo: Dict[Tuple[str, int], Dict[str, Any]],
    libro: Dict[Tuple[str, int], Dict[str, Any]],
    symbol: str,
    cut: int,
    direccion: str,
    c: Any,
) -> Dict[str, Any]:
    s = _signo(direccion)
    alineado_3 = s * (float(c.buy_notional) - float(c.sell_notional))
    d3 = c.profundidad_contraria(direccion)
    b0 = (int(cut) // VENTANA_MS) * VENTANA_MS
    bloques: List[Dict[str, Any]] = []
    base_cierre: Optional[float] = float(c.precio_cierre)
    for k in range(MAX_BLOQUES_CAMBIO):
        t = b0 + k * VENTANA_MS
        b = _bloque_post(flujo, libro, symbol, t, direccion,
                         alineado_3, d3, base_cierre)
        b["k"] = k
        bloques.append(b)
        base_cierre = b["precio_cierre"] if b["estado"] == ESTADO_RESOLUBLE else None

    primer_cambio = _primer_evento(bloques, "tipos", "")
    if primer_cambio["estado"] == ESTADO_CAMBIO:
        primer_cambio["tipo"] = primer_cambio["tipos"][0]
        primer_cambio["es_giro"] = primer_cambio["tipo"] == "giro"

    return {
        "bloques": bloques,
        "bloques_utiles": sum(1 for b in bloques if b["estado"] == ESTADO_RESOLUBLE),
        "bloques_totales": len(bloques),
        "primer_cambio": primer_cambio,
        "primer_giro": _primer_evento(bloques, "es_giro", "giro"),
        "primer_debilitamiento": _primer_evento(
            bloques, "es_debilitamiento", "debilitamiento"),
        "primer_precio_sin_avance": _primer_evento(
            bloques, "es_precio_sin_avance", "precio_sin_avance"),
        "primer_profundidad_deja_de_caer": _primer_evento(
            bloques, "es_profundidad_deja_de_caer",
            "profundidad_deja_de_caer"),
    }


def detalle_10s_bloque(
    flujo_10s: Dict[Tuple[str, int], Dict[str, Any]],
    symbol: str,
    inicio_ms: int,
) -> List[Dict[str, Any]]:
    filas: List[Dict[str, Any]] = []
    for i in range(6):
        t = int(inicio_ms) + i * BUCKET_10S_MS
        f = flujo_10s.get((symbol, t))
        ok, motivo = _bucket_10s_util(f)
        filas.append({
            "inicio_ms": t,
            "inicio_iso": utc_iso(t),
            "fin_ms": t + BUCKET_10S_MS,
            "estado": ESTADO_RESOLUBLE if ok else ESTADO_UNKNOWN,
            "motivo": motivo,
            "buy_notional": _redondear(f["buy_notional"]) if ok else None,
            "sell_notional": _redondear(f["sell_notional"]) if ok else None,
            "delta": (_redondear(float(f["buy_notional"]) - float(f["sell_notional"]))
                      if ok else None),
            "precio_open": float(f["price_open"]) if ok else None,
            "precio_close": float(f["price_close"]) if ok else None,
            "as_of_ms": int(f["as_of_ms"]) if ok else None,
            "as_of_iso": utc_iso(int(f["as_of_ms"])) if ok else None,
        })
    return filas


def resolver_cambio(
    episodio: Dict[str, Any], cambio: Dict[str, Any],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
) -> Dict[str, Any]:
    if cambio is None or cambio.get("estado") != ESTADO_CAMBIO:
        return {
            "estado": ESTADO_UNKNOWN,
            "motivo": (cambio or {}).get("motivo") or MOTIVO_SIN_CAMBIO,
            "cut_cambio_ms": None,
            "entrada_ms": None,
            "salida_ms": None,
            "continuacion_bps": None,
            "reversion_bps": None,
            "reutiliza_entrada_original": None,
        }
    cut = int(cambio["disponibilidad_ms"])
    entrada = _referencia_entrada(cut)
    pseudo = {
        "symbol": episodio["symbol"],
        "direccion": episodio["direccion"],
        "cut_ms": cut,
    }
    continuacion = resolver_alerta(pseudo, velas)
    reversion = resolver_alerta(
        {**pseudo, "direccion": _opuesta(episodio["direccion"])}, velas)
    if continuacion["entrada_ms"] != reversion["entrada_ms"]:
        raise SystemExit("continuacion y reversion del cambio no comparten entrada")
    if continuacion["salida_ms"] != reversion["salida_ms"]:
        raise SystemExit("continuacion y reversion del cambio no comparten salida")
    if continuacion["entrada_ms"] != entrada:
        raise SystemExit("la entrada del cambio no coincide con su corte")
    entrada_original = _referencia_entrada(int(episodio["cut_ms"]))
    if continuacion["entrada_ms"] == entrada_original:
        raise SystemExit("el cambio reutiliza la entrada original")
    es_giro = bool(cambio.get("es_giro"))
    return {
        "estado": continuacion.get("estado"),
        "motivo": continuacion.get("motivo"),
        "cut_cambio_ms": cut,
        "cut_cambio_iso": utc_iso(cut),
        "entrada_ms": continuacion.get("entrada_ms"),
        "salida_ms": continuacion.get("salida_ms"),
        "precio_entrada": continuacion.get("precio_entrada"),
        "precio_salida": continuacion.get("precio_salida"),
        "continuacion_bps": _redondear(continuacion.get("retorno_bps")),
        "reversion_bps": (_redondear(reversion.get("retorno_bps"))
                          if es_giro else None),
        "reversion_motivo": None if es_giro else MOTIVO_NO_APLICA,
        "adverso_bps": continuacion.get("adverso_bps"),
        "favorable_bps": continuacion.get("favorable_bps"),
        "trayectoria_completa": continuacion.get("trayectoria_completa"),
        "reutiliza_entrada_original": (
            continuacion.get("entrada_ms") == entrada_original),
        "demora_entrada_ms": (
            continuacion.get("entrada_ms") - cut
            if continuacion.get("entrada_ms") is not None else None),
    }


# ---------------------------------------------------------------------------
# Analisis de un ancla (caso o control)
# ---------------------------------------------------------------------------

def analizar_ancla(
    episodio: Dict[str, Any],
    fila_terna: Dict[str, Any],
    indice: Dict[str, Dict[int, Any]],
    por_symbol: Dict[str, List[Any]],
    flujo: Dict[Tuple[str, int], Dict[str, Any]],
    libro: Dict[Tuple[str, int], Dict[str, Any]],
    flujo_10s: Dict[Tuple[str, int], Dict[str, Any]],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
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

    s = _signo(direccion)
    avance = s * (float(c.precio_cierre) / float(a.precio_cierre) - 1.0) * 1e4
    ext_3m = avance_vs_3m_flujo(flujo, symbol, int(a.ventana_inicio_ms), avance)
    previas = ternas_previas_no_solapadas(
        por_symbol[symbol], int(a.ventana_inicio_ms))
    ext_ternas = _envolver_extension(
        extension_previa((a, b, c), previas, direccion))

    original = resolver_alerta(episodio, velas)
    post = analizar_bloques(flujo, libro, symbol, corte, direccion, c)
    resultado = resolver_cambio(episodio, post["primer_cambio"], velas)
    resultado_giro = resolver_cambio(episodio, post["primer_giro"], velas)
    detalle_10s = (
        detalle_10s_bloque(flujo_10s, symbol, post["primer_cambio"]["inicio_ms"])
        if post["primer_cambio"]["estado"] == ESTADO_CAMBIO else []
    )

    return {
        "symbol": symbol,
        "direccion": direccion,
        "terna": fila_terna["terna"],
        "cut_ms": corte,
        "cut_iso": utc_iso(corte),
        "ancla_patron": bool(episodio["ancla_patron"]),
        "original": {
            "estado": original.get("estado"),
            "motivo": original.get("motivo"),
            "entrada_ms": original.get("entrada_ms"),
            "salida_ms": original.get("salida_ms"),
            "precio_entrada": original.get("precio_entrada"),
            "precio_salida": original.get("precio_salida"),
            "retorno_bps": _redondear(original.get("retorno_bps")),
            "adverso_bps": _redondear(original.get("adverso_bps")),
            "favorable_bps": _redondear(original.get("favorable_bps")),
            "trayectoria_completa": original.get("trayectoria_completa"),
        },
        "at_cut": {
            "avance_bps": _redondear(avance),
            "cierres": [float(a.precio_cierre), float(b.precio_cierre),
                        float(c.precio_cierre)],
            "avance_vs_3m_flujo": ext_3m,
            "avance_vs_ternas": ext_ternas,
            "q_descomposicion": descomponer_q(a, b, c, direccion),
            "impacto": impacto_por_tramo(a, b, c, direccion),
            "ultimos_30s": ultimos_30s(
                flujo_10s, symbol, int(c.ventana_fin_ms), direccion),
            "concentracion_10s": concentracion_10s(
                flujo_10s, symbol, int(c.ventana_fin_ms)),
            "ventanas": [
                _ventana_detalle(a, direccion, flujo, libro, None),
                _ventana_detalle(b, direccion, flujo, libro, a),
                _ventana_detalle(c, direccion, flujo, libro, b),
            ],
        },
        "post": {
            **post,
            "resultado": resultado,
            "resultado_giro": resultado_giro,
            "detalle_10s_primer_cambio": detalle_10s,
        },
    }


# ---------------------------------------------------------------------------
# Agregados
# ---------------------------------------------------------------------------

def _stats(valores: List[float]) -> Dict[str, Any]:
    if not valores:
        return {"n": 0, "media": None, "mediana": None, "min": None, "max": None}
    return {
        "n": len(valores),
        "media": _redondear(_media(valores)),
        "mediana": _redondear(_mediana(valores)),
        "min": _redondear(min(valores)),
        "max": _redondear(max(valores)),
    }


def _valores(registros: List[Dict[str, Any]], ruta: List[str]) -> List[float]:
    salida: List[float] = []
    for r in registros:
        actual: Any = r
        for clave in ruta:
            if not isinstance(actual, dict):
                actual = None
                break
            actual = actual.get(clave)
        if actual is not None:
            salida.append(float(actual))
    return salida


def _conteo_estado(registros: List[Dict[str, Any]], ruta: List[str]) -> Dict[str, Any]:
    estados = Counter()
    motivos = Counter()
    for r in registros:
        actual: Any = r
        for clave in ruta:
            actual = actual.get(clave) if isinstance(actual, dict) else None
        if not isinstance(actual, dict):
            estados["falta"] += 1
            continue
        estados[str(actual.get("estado"))] += 1
        if actual.get("motivo"):
            motivos[str(actual.get("motivo"))] += 1
    return {"estados": dict(estados), "motivos": dict(motivos)}


def metricas_at_cut(registros: List[Dict[str, Any]]) -> Dict[str, Any]:
    ext3 = [r for r in registros
            if r["at_cut"]["avance_vs_3m_flujo"]["estado"] == ESTADO_RESOLUBLE]
    extt = [r for r in registros
            if r["at_cut"]["avance_vs_ternas"]["estado"] == ESTADO_RESOLUBLE]
    qd = [r for r in registros
          if r["at_cut"]["q_descomposicion"]["estado"] == ESTADO_RESOLUBLE]
    imp = [r for r in registros
           if r["at_cut"]["impacto"]["estado"] == ESTADO_RESOLUBLE]
    u30 = [r for r in registros
           if r["at_cut"]["ultimos_30s"]["estado"] == ESTADO_RESOLUBLE]
    conc = [r for r in registros
            if r["at_cut"]["concentracion_10s"]["estado"] == ESTADO_RESOLUBLE]

    def _por_direccion(seleccion: List[Dict[str, Any]], ruta: List[str]) -> Dict[str, Any]:
        salida = {}
        for d in ("LONG", "SHORT"):
            vals = _valores([r for r in seleccion if r["direccion"] == d], ruta)
            salida[d] = _stats(vals)
        return salida

    return {
        "avance_vs_3m_flujo": {
            **_conteo_estado(registros, ["at_cut", "avance_vs_3m_flujo"]),
            "normalizada": _stats(_valores(ext3, ["at_cut", "avance_vs_3m_flujo",
                                                  "extension_normalizada"])),
            "referencia_bps": _stats(_valores(ext3, ["at_cut", "avance_vs_3m_flujo",
                                                     "referencia_bps"])),
            "por_direccion": _por_direccion(ext3, ["at_cut", "avance_vs_3m_flujo",
                                                   "extension_normalizada"]),
        },
        "avance_vs_ternas": {
            **_conteo_estado(registros, ["at_cut", "avance_vs_ternas"]),
            "normalizada": _stats(_valores(extt, ["at_cut", "avance_vs_ternas",
                                                  "extension_normalizada"])),
            "por_direccion": _por_direccion(extt, ["at_cut", "avance_vs_ternas",
                                                   "extension_normalizada"]),
        },
        "q_descomposicion": {
            **_conteo_estado(registros, ["at_cut", "q_descomposicion"]),
            "aporte_importe_pct": _stats(_valores(qd, ["at_cut", "q_descomposicion",
                                                       "aporte_importe_pct"])),
            "profundidad_cae_pct": _stats(_valores(qd, ["at_cut", "q_descomposicion",
                                                        "profundidad_cae_pct"])),
            "importe_crece": sum(1 for r in qd
                                 if r["at_cut"]["q_descomposicion"]["importe_crece"]),
            "notional_total_crece": sum(
                1 for r in qd if r["at_cut"]["q_descomposicion"]["notional_total_crece"]),
            "por_direccion": _por_direccion(qd, ["at_cut", "q_descomposicion",
                                                 "aporte_importe_pct"]),
        },
        "impacto": {
            **_conteo_estado(registros, ["at_cut", "impacto"]),
            "impacto_relativo": _stats(_valores(imp, ["at_cut", "impacto",
                                                      "impacto_relativo"])),
            "avance_ultima_ventana_pct": _stats(_valores(
                imp, ["at_cut", "impacto", "avance_ultima_ventana_pct"])),
            "frenada_impacto": sum(1 for r in imp
                                   if r["at_cut"]["impacto"]["frenada_impacto"]),
            "frenada_avance": sum(1 for r in imp
                                  if r["at_cut"]["impacto"]["frenada_avance"]),
            "por_direccion": _por_direccion(imp, ["at_cut", "impacto",
                                                  "impacto_relativo"]),
        },
        "ultimos_30s": {
            **_conteo_estado(registros, ["at_cut", "ultimos_30s"]),
            "flujo_alineado_30s": _stats(_valores(u30, ["at_cut", "ultimos_30s",
                                                        "flujo_alineado_30s"])),
            "delta_precio_30s_bps": _stats(_valores(u30, ["at_cut", "ultimos_30s",
                                                          "delta_precio_30s_bps"])),
            "giro_30s": sum(1 for r in u30
                            if r["at_cut"]["ultimos_30s"]["giro_30s"]),
            "presion_sin_avance_30s": sum(
                1 for r in u30
                if r["at_cut"]["ultimos_30s"]["presion_sin_avance_30s"]),
            "por_direccion": _por_direccion(u30, ["at_cut", "ultimos_30s",
                                                  "flujo_alineado_30s"]),
        },
        "concentracion_10s": {
            **_conteo_estado(registros, ["at_cut", "concentracion_10s"]),
            "concentracion": _stats(_valores(conc, ["at_cut", "concentracion_10s",
                                                    "concentracion"])),
            "por_direccion": _por_direccion(conc, ["at_cut", "concentracion_10s",
                                                   "concentracion"]),
        },
    }


def _pares_resultado(
    registros: List[Dict[str, Any]], ruta: List[str]
) -> List[Dict[str, Any]]:
    pares = []
    for r in registros:
        actual: Any = r
        for clave in ruta:
            actual = actual.get(clave) if isinstance(actual, dict) else None
        if (not isinstance(actual, dict)
                or actual.get("estado") != ESTADO_RESOLUBLE
                or actual.get("continuacion_bps") is None
                or r["original"]["estado"] != ESTADO_RESOLUBLE
                or r["original"]["retorno_bps"] is None):
            continue
        pares.append(r)
    return pares


def _resumen_pares(
    pares: List[Dict[str, Any]], ruta: List[str]
) -> Dict[str, Any]:
    def _get(r: Dict[str, Any], clave: str) -> Optional[float]:
        actual: Any = r
        for c in ruta:
            actual = actual.get(c) if isinstance(actual, dict) else None
        if not isinstance(actual, dict):
            return None
        v = actual.get(clave)
        return float(v) if v is not None else None

    orig = [float(r["original"]["retorno_bps"]) for r in pares]
    cont = [_get(r, "continuacion_bps") for r in pares]
    rev = [_get(r, "reversion_bps") for r in pares]
    delta = [c - o for c, o in zip(cont, orig) if c is not None]
    rev_validos = [x for x in rev if x is not None]
    return {
        "n": len(pares),
        "original_media_bps": _redondear(_media(orig)),
        "original_mediana_bps": _redondear(_mediana(orig)),
        "continuacion_media_bps": _redondear(_media([x for x in cont if x is not None])),
        "continuacion_mediana_bps": _redondear(_mediana([x for x in cont if x is not None])),
        "delta_media_bps": _redondear(_media(delta)),
        "delta_mediana_bps": _redondear(_mediana(delta)),
        "delta_positivo": sum(1 for d in delta if d > 0),
        "delta_negativo": sum(1 for d in delta if d < 0),
        "delta_cero": sum(1 for d in delta if d == 0),
        "reversion_n": len(rev_validos),
        "reversion_media_bps": _redondear(_media(rev_validos)),
        "reversion_mediana_bps": _redondear(_mediana(rev_validos)),
        "reversion_positiva": sum(1 for x in rev_validos if x > 0),
        "continuacion_positiva": sum(1 for x in cont if x is not None and x > 0),
    }


def metricas_cambios(registros: List[Dict[str, Any]]) -> Dict[str, Any]:
    def _evento_de(r: Dict[str, Any], clave: str) -> Dict[str, Any]:
        return r["post"][clave]

    eventos = ["primer_cambio", "primer_giro", "primer_debilitamiento",
               "primer_precio_sin_avance", "primer_profundidad_deja_de_caer"]
    conteo = {}
    for ev in eventos:
        estados = Counter()
        tipos = Counter()
        ks = []
        demoras = []
        for r in registros:
            e = _evento_de(r, ev)
            estados[str(e.get("estado"))] += 1
            if e.get("estado") == ESTADO_CAMBIO:
                tipos[str(e.get("tipo"))] += 1
                if e.get("k") is not None:
                    ks.append(int(e["k"]))
                if e.get("disponibilidad_ms") is not None:
                    demoras.append(int(e["disponibilidad_ms"]) - int(r["cut_ms"]))
        conteo[ev] = {
            "estados": dict(estados),
            "tipos": dict(tipos),
            "k": _stats([float(x) for x in ks]),
            "demora_disponibilidad_ms": _stats([float(x) for x in demoras]),
        }

    def _por_direccion(ruta: List[str]) -> Dict[str, Any]:
        salida = {}
        for d in ("LONG", "SHORT"):
            pares = _pares_resultado(
                [r for r in registros if r["direccion"] == d], ruta)
            salida[d] = _resumen_pares(pares, ruta)
        return salida

    pares_cambio = _pares_resultado(registros, ["post", "resultado"])
    pares_giro = _pares_resultado(registros, ["post", "resultado_giro"])

    por_tipo = {}
    for tipo in ("giro", "debilitamiento", "precio_sin_avance",
                 "profundidad_deja_de_caer"):
        seleccion = [
            r for r in registros
            if r["post"]["primer_cambio"].get("estado") == ESTADO_CAMBIO
            and r["post"]["primer_cambio"].get("tipo") == tipo
        ]
        por_tipo[tipo] = _resumen_pares(
            _pares_resultado(seleccion, ["post", "resultado"]),
            ["post", "resultado"])

    return {
        "eventos": conteo,
        "resultado_primer_cambio": _resumen_pares(pares_cambio,
                                                  ["post", "resultado"]),
        "resultado_primer_giro": _resumen_pares(pares_giro,
                                                ["post", "resultado_giro"]),
        "por_direccion_primer_cambio": _por_direccion(["post", "resultado"]),
        "por_direccion_primer_giro": _por_direccion(["post", "resultado_giro"]),
        "por_tipo_primer_cambio": por_tipo,
        "no_resolubles_resultado": dict(Counter(
            r["post"]["resultado"].get("motivo") for r in registros
            if r["post"]["resultado"].get("estado") != ESTADO_RESOLUBLE)),
        "reutiliza_entrada_original": sum(
            1 for r in registros
            if r["post"]["resultado"].get("reutiliza_entrada_original") is True),
    }


def cruce_visible_vs_resultado(registros: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Cruces descriptivos: factor visible en el corte frente al resultado original.

    No hay umbral ni prueba de seleccion: solo conteos y medianas por grupo.
    """
    base = [r for r in registros
            if r["original"]["estado"] == ESTADO_RESOLUBLE
            and r["original"]["retorno_bps"] is not None]

    def _grupo(r: Dict[str, Any]) -> str:
        v = float(r["original"]["retorno_bps"])
        if v > 0:
            return "positivo"
        if v < 0:
            return "negativo"
        return "cero"

    salida: Dict[str, Any] = {}
    binarios = {
        "giro_30s": lambda r: r["at_cut"]["ultimos_30s"].get("estado") == ESTADO_RESOLUBLE
        and r["at_cut"]["ultimos_30s"].get("giro_30s") is True,
        "presion_sin_avance_30s": lambda r: (
            r["at_cut"]["ultimos_30s"].get("estado") == ESTADO_RESOLUBLE
            and r["at_cut"]["ultimos_30s"].get("presion_sin_avance_30s") is True),
        "frenada_impacto": lambda r: (
            r["at_cut"]["impacto"].get("estado") == ESTADO_RESOLUBLE
            and r["at_cut"]["impacto"].get("frenada_impacto") is True),
    }
    for nombre, fn in binarios.items():
        grupo = {"true": Counter(), "false": Counter(), "UNKNOWN": Counter()}
        for r in base:
            if (r["at_cut"]["ultimos_30s"].get("estado") != ESTADO_RESOLUBLE
                    and nombre != "frenada_impacto"):
                grupo["UNKNOWN"][_grupo(r)] += 1
            elif (r["at_cut"]["impacto"].get("estado") != ESTADO_RESOLUBLE
                  and nombre == "frenada_impacto"):
                grupo["UNKNOWN"][_grupo(r)] += 1
            else:
                grupo["true" if fn(r) else "false"][_grupo(r)] += 1
        salida[nombre] = {k: dict(v) for k, v in grupo.items()}

    continuos = {
        "avance_vs_3m_flujo": ["at_cut", "avance_vs_3m_flujo",
                               "extension_normalizada"],
        "aporte_importe_pct": ["at_cut", "q_descomposicion",
                               "aporte_importe_pct"],
        "concentracion_10s": ["at_cut", "concentracion_10s", "concentracion"],
    }
    for nombre, ruta in continuos.items():
        por_grupo: Dict[str, List[float]] = {"positivo": [], "negativo": [],
                                             "cero": []}
        for r in base:
            actual: Any = r
            for clave in ruta:
                actual = actual.get(clave) if isinstance(actual, dict) else None
            if actual is None:
                continue
            por_grupo[_grupo(r)].append(float(actual))
        salida[nombre] = {k: _stats(v) for k, v in por_grupo.items()}

    return salida


# ---------------------------------------------------------------------------
# Conclusiones formales predeclaradas
# ---------------------------------------------------------------------------

def concluir_giro(registros: List[Dict[str, Any]],
                  por_direccion: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    pares = _pares_resultado(registros, ["post", "resultado_giro"])
    n = len(pares)
    base = {
        "minimo_pares": MIN_EPISODIOS,
        "pares_comparables": n,
        "regla": "con 30 o mas pares, el giro anticipa reversion solo si la "
                 "media y la mediana de la reversion medida desde su "
                 "disponibilidad son positivas",
    }
    if n < MIN_EPISODIOS:
        return {**base, "conclusion": "datos insuficientes",
                "motivo": f"pares comparables={n}; minimo fijado={MIN_EPISODIOS}"}
    rev = [float(r["post"]["resultado_giro"]["reversion_bps"]) for r in pares
           if r["post"]["resultado_giro"]["reversion_bps"] is not None]
    if len(rev) != n:
        return {**base, "conclusion": "datos insuficientes",
                "motivo": f"reversiones resolubles={len(rev)} de {n} pares"}
    media = _media(rev)
    mediana = _mediana(rev)
    evidencia = [f"reversion media {_redondear(media)} bps; "
                 f"mediana {_redondear(mediana)} bps"]
    for d, m in por_direccion.items():
        evidencia.append(
            f"{d}: n={m['reversion_n']}, reversion media {m['reversion_media_bps']} "
            f"bps, mediana {m['reversion_mediana_bps']} bps")
    if media is not None and mediana is not None and media > 0 and mediana > 0:
        return {**base, "conclusion": "el giro muestra reversion en esta muestra",
                "evidencia": evidencia}
    return {**base, "conclusion": "el giro no muestra reversion en esta muestra",
            "evidencia": evidencia}


def concluir_cambio(registros: List[Dict[str, Any]],
                    por_direccion: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    pares = _pares_resultado(registros, ["post", "resultado"])
    n = len(pares)
    base = {
        "minimo_pares": MIN_EPISODIOS,
        "pares_comparables": n,
        "regla": "con 30 o mas pares, la continuacion desde el primer cambio "
                 "muestra mejora solo si la media y la mediana del delta "
                 "(cambio - original) son positivas",
    }
    if n < MIN_EPISODIOS:
        return {**base, "conclusion": "datos insuficientes",
                "motivo": f"pares comparables={n}; minimo fijado={MIN_EPISODIOS}"}
    delta = [
        float(r["post"]["resultado"]["continuacion_bps"])
        - float(r["original"]["retorno_bps"])
        for r in pares
    ]
    media = _media(delta)
    mediana = _mediana(delta)
    evidencia = [f"delta medio {_redondear(media)} bps; "
                 f"mediana {_redondear(mediana)} bps"]
    for d, m in por_direccion.items():
        evidencia.append(
            f"{d}: n={m['n']}, delta medio {m['delta_media_bps']} bps, "
            f"mediana {m['delta_mediana_bps']} bps")
    if media is not None and mediana is not None and media > 0 and mediana > 0:
        return {**base, "conclusion": "el primer cambio muestra mejora en esta muestra",
                "evidencia": evidencia}
    return {**base, "conclusion": "el primer cambio no muestra mejora en esta muestra",
            "evidencia": evidencia}


# ---------------------------------------------------------------------------
# Diagnostico de los cuatro casos
# ---------------------------------------------------------------------------

def _ficha_caso(r: Dict[str, Any]) -> Dict[str, Any]:
    at = r["at_cut"]
    post = r["post"]
    cambio = post["primer_cambio"]
    giro = post["primer_giro"]
    res = post["resultado"]
    res_giro = post["resultado_giro"]
    return {
        "symbol": r["symbol"],
        "direccion": r["direccion"],
        "terna": r["terna"],
        "cut_ms": r["cut_ms"],
        "cut_iso": r["cut_iso"],
        "retorno_original_bps": r["original"]["retorno_bps"],
        "entrada_original_ms": r["original"]["entrada_ms"],
        "salida_original_ms": r["original"]["salida_ms"],
        "avance_bps": at["avance_bps"],
        "avance_vs_3m_flujo": at["avance_vs_3m_flujo"],
        "avance_vs_ternas": at["avance_vs_ternas"],
        "q_descomposicion": at["q_descomposicion"],
        "impacto": at["impacto"],
        "ultimos_30s": at["ultimos_30s"],
        "concentracion_10s": at["concentracion_10s"],
        "primer_cambio": cambio,
        "primer_giro": giro,
        "primer_precio_sin_avance": post["primer_precio_sin_avance"],
        "primer_profundidad_deja_de_caer": post[
            "primer_profundidad_deja_de_caer"],
        "resultado_cambio": res,
        "resultado_giro": res_giro,
        "evidencia_en_tiempo": {
            "cambio_antes_de_entrada_original": (
                cambio.get("disponibilidad_ms") is not None
                and r["original"]["entrada_ms"] is not None
                and int(cambio["disponibilidad_ms"])
                <= int(r["original"]["entrada_ms"])),
            "cambio_antes_de_salida_original": (
                cambio.get("disponibilidad_ms") is not None
                and r["original"]["salida_ms"] is not None
                and int(cambio["disponibilidad_ms"])
                <= int(r["original"]["salida_ms"])),
            "bloques_utiles": post["bloques_utiles"],
            "bloques_totales": post["bloques_totales"],
        },
        "detalle_10s_primer_cambio": post["detalle_10s_primer_cambio"],
    }


def diagnostico_casos(casos: List[Dict[str, Any]]) -> Dict[str, Any]:
    fichas = [_ficha_caso(c) for c in casos]
    return {
        "casos": len(casos),
        "detalle": fichas,
        "factores_no_evaluados_por_el_detector": [
            "tamano del avance frente al comportamiento reciente del mismo "
            "token (normalizado por su propia historia)",
            "descomposicion de Q: importe agresor frente a caida de la "
            "profundidad contraria",
            "impacto marginal por tramo de presion y respuesta de los ultimos "
            "30 s de la tercera ventana",
            "distribucion intra-minuto del flujo (concentracion en un bucket "
            "de 10 s y giro dentro de la tercera ventana)",
            "cualquier cambio posterior al corte (debilitamiento, giro, "
            "precio sin avance, profundidad que deja de caer)",
        ],
        "hechos": {
            "ganador": "STRKUSDT LONG",
            "perdedores": ["ARIAUSDT LONG", "BLESSUSDT SHORT (19:30)",
                           "BLESSUSDT SHORT (20:06)"],
            "extension": "se reporta por caso; UNKNOWN cuando la historia "
                         "comparable es insuficiente",
            "presion": "Q crece sobre todo por importe en los cuatro casos; "
                       "la profundidad contraria cae poco",
            "impacto": "la frenada del impacto aparece en 3 de 4 casos, "
                       "incluido el ganador; no separa por si sola",
            "posterior": "el primer cambio se observa en el minuto del corte "
                         "en los tres perdedores; en el ganador falta el "
                         "flujo de los minutos siguientes",
        },
        "limitaciones": [
            "cuatro casos: solo formulan hipotesis; no validan una regla",
            "la captura ya se uso en el desarrollo del detector: no es una "
            "prueba independiente",
            "los agregados de 1 minuto y de 10 s no se atribuyen a un segundo "
            "exacto",
            "una caida o subida de la profundidad media no demuestra retirada "
            "o reposicion de ordenes individuales",
            "el tramo sin flujo persistido no se rellena ni se atribuye a una "
            "causa",
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _leer_jsonl(ruta: Path) -> List[Dict[str, Any]]:
    with io.open(ruta, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--cobertura", required=True)
    ap.add_argument("--klines", required=True)
    ap.add_argument("--derivados-anclas", required=True,
                    help="directorio con los derivados publicados del bloque de anclas")
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
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    for ruta in (db, cobertura_ruta, klines_ruta):
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
    }

    cobertura = cargar_cobertura(cobertura_ruta)
    db_declarada = str(cobertura.get("origen", {}).get("db_sha256", "")).lower()
    if db_declarada and db_declarada != hashes_antes["research.db"].lower():
        raise SystemExit(
            "research.db no coincide con el hash declarado en la cobertura: "
            f"{hashes_antes['research.db']} != {db_declarada}")

    por_symbol, audit_ventanas = construir_ventanas(db, cobertura, args.run_id)
    universo = verificar_universo(por_symbol, cobertura)
    indice = {
        symbol: {int(v.ventana_inicio_ms): v for v in ventanas}
        for symbol, ventanas in por_symbol.items()
    }

    decisiones = evaluar_detector(por_symbol)
    alertas_p, resumen_p = alertas_patron(por_symbol, decisiones)
    ternas_detalle = resumen_p["ternas_detalle"]
    por_terna = {t["terna"]: t for t in ternas_detalle}
    if len(por_terna) != len(ternas_detalle):
        raise SystemExit("ternas duplicadas en el detalle del detector")

    alertas_ref, audit_ref = construir_alertas_referencia(ternas_detalle, por_symbol)
    velas, audit_velas = cargar_velas(klines_ruta, args.run_id)
    episodios, audit_agrup = agrupar_con_tardias(alertas_ref, alertas_p)
    anclas_con = [e for e in episodios if e["ancla_patron"]]
    if len(anclas_con) != 4:
        raise SystemExit(f"se esperaban 4 anclas con patron; hay {len(anclas_con)}")

    flujo, libro, audit_filas = cargar_filas(db, args.run_id)
    flujo_10s, audit_10s = cargar_filas_10s(db, args.run_id)

    casos = [
        analizar_ancla(e, por_terna[e["terna"]], indice, por_symbol,
                       flujo, libro, flujo_10s, velas)
        for e in sorted(anclas_con, key=lambda x: (x["cut_ms"], x["symbol"]))
    ]
    verificacion_casos = verificar_casos_publicados(
        casos, _leer_jsonl(ruta_patron_pub))

    controles = [
        analizar_ancla(e, por_terna[e["terna"]], indice, por_symbol,
                       flujo, libro, flujo_10s, velas)
        for e in episodios
    ]
    verificacion_anclas = verificar_anclas_publicadas(
        controles, _leer_jsonl(ruta_anclas_pub))

    resumen_original_143 = resumir_episodios(episodios, velas)
    resumen_original_143.pop("detalle", None)

    at_cut = metricas_at_cut(controles)
    cambios = metricas_cambios(controles)
    por_direccion_cambio = cambios["por_direccion_primer_cambio"]
    por_direccion_giro = cambios["por_direccion_primer_giro"]
    conclusion_giro = concluir_giro(controles, por_direccion_giro)
    conclusion_cambio = concluir_cambio(controles, por_direccion_cambio)

    hashes_despues = {
        "research.db": _sha256_archivo(db),
        "cobertura_json": _sha256_archivo(cobertura_ruta),
        "consultas_klines.jsonl": _sha256_archivo(klines_ruta),
        "episodios_patron_originales.jsonl": _sha256_archivo(ruta_patron_pub),
        "episodios_referencia_universo_igual.jsonl": _sha256_archivo(ruta_anclas_pub),
    }
    if hashes_antes != hashes_despues:
        raise SystemExit("las fuentes cambiaron durante el diagnostico; abortado")

    resumen = {
        "version_diagnostico": VERSION_DIAGNOSTICO,
        "version_anclas": VERSION_ANCLAS,
        "run_id": args.run_id,
        "pregunta": "que distinguia a STRKUSDT LONG de ARIAUSDT LONG y de los "
                    "dos BLESSUSDT SHORT, y cuando se podia conocer cada "
                    "factor",
        "reglas_fijadas": {
            "avance_vs_3m_flujo": "mediana de movimientos absolutos de bloques "
                                  "de 3 ventanas no solapadas del mismo simbolo, "
                                  "desde el final hacia atras, terminando en el "
                                  "inicio de la terna",
            "minimo_bloques_3m": MIN_BLOQUES_3M,
            "avance_vs_ternas": "ternas previas no solapadas del universo "
                                "acreditado; minimo 6",
            "minimo_ternas_previas": MIN_TERN_PREVIAS,
            "descomposicion_q": "dlogQ = log(F3/F1) - log(D3/D1); aportes "
                                "porcentuales del importe y de la profundidad",
            "impacto": "bps por 1000 USDT alineados en cada tramo; frenada si "
                       "impacto_3 < impacto_2 y F3 >= F2",
            "ultimos_30s": "3 buckets de 10 s que terminan en el cierre de la "
                           "tercera ventana; giro_30s si el flujo alineado <= 0",
            "bloques_post": "minutos alineados al reloj desde el minuto del "
                            "corte (b_0..b_5); el minuto es la unidad de "
                            "evidencia",
            "cambios": ["giro", "debilitamiento", "precio_sin_avance",
                        "profundidad_deja_de_caer"],
            "entrada_cambio": "apertura del primer minuto estrictamente "
                              "posterior a la disponibilidad del cambio",
            "salida_cambio": "apertura exactamente 5 minutos despues de la "
                             "entrada",
            "reversion_cambio": "solo si el cambio es un giro; misma entrada y "
                                "salida que la continuacion; nunca la entrada "
                                "original",
            "horizonte_ms": HORIZONTE_MS,
            "coste_sensibilidad_bps": COSTE_IDA_VUELTA_BPS,
            "funding": "UNKNOWN",
            "minimo_pares_conclusion": MIN_EPISODIOS,
        },
        "origen": {
            "db": str(db),
            "cobertura": str(cobertura_ruta),
            "klines": str(klines_ruta),
            "derivados_anclas": str(derivados_anclas),
            "db_sha256_declarada_en_cobertura": db_declarada or None,
            "hashes_antes": hashes_antes,
            "hashes_despues": hashes_despues,
            "fuentes_intactas": hashes_antes == hashes_despues,
        },
        "universo": {
            "publicado": universo["esperado"],
            "hasta_entrada_detector": universo["obtenido"],
            "conservado": universo["conservado"],
            "ternas_evaluadas": len(ternas_detalle),
            "cortes_verificados_identicos": audit_ref["cortes_verificados"],
            "alertas_solo_precio": len(alertas_ref),
            "episodios_ancla": len(episodios),
            "anclas_con_patron": len(anclas_con),
            "anclas_sin_patron": len(episodios) - len(anclas_con),
            "verificacion_publicada": {
                "casos": verificacion_casos,
                "anclas": verificacion_anclas,
            },
            "agrupacion": audit_agrup,
            "filas_crudas": {**audit_filas, **audit_10s},
            "ventanas_validas_detector": audit_ventanas["ventanas_validas_detector"],
        },
        "casos": {
            "verificacion_publicado": verificacion_casos,
            "detalle": [_ficha_caso(c) for c in casos],
        },
        "controles": {
            "original_143_recalculado": {
                k: v for k, v in resumen_original_143.items()
                if k != "por_hora_utc"
            },
            "at_cut": at_cut,
            "cambios": cambios,
            "cruce_visible_vs_resultado": cruce_visible_vs_resultado(controles),
        },
        "conclusion_giro": conclusion_giro,
        "conclusion_cambio": conclusion_cambio,
        "diagnostico_cuatro_casos": diagnostico_casos(casos),
        "cobertura_de_velas": {
            **{k: v for k, v in audit_velas.items() if k != "simbolos"},
            "simbolos": sorted(velas.keys()),
        },
        "limitaciones": [
            "captura ya usada en el desarrollo del detector: hallazgo "
            "exploratorio, no prueba independiente",
            "los cuatro casos formulan hipotesis; no validan una regla",
            "los agregados de 1 minuto y de 10 s no se atribuyen a un segundo "
            "exacto",
            "una caida o subida de la profundidad media no demuestra retirada "
            "o reposicion de ordenes individuales",
            "entrada y salida son aperturas de velas: no son fills ni incluyen "
            "latencia",
            "cobertura de velas limitada a los simbolos consultados durante la "
            "captura",
            "flujo intermedio ausente en la captura no se rellena ni se "
            "atribuye a una causa",
            "funding UNKNOWN; el coste de 16 bps es solo sensibilidad "
            "documentada",
            "retorno bruto de referencia, no P&L",
        ],
    }

    def _jsonl(nombre: str, filas: List[Dict[str, Any]]) -> str:
        ruta = salida / nombre
        with io.open(ruta, "w", encoding="utf-8", newline="\n") as f:
            for fila in filas:
                f.write(json.dumps(fila, ensure_ascii=False, sort_keys=True) + "\n")
        return _sha256_archivo(ruta)

    ventanas_casos = [
        {"terna": c["terna"], "symbol": c["symbol"],
         "direccion": c["direccion"], **v}
        for c in casos for v in c["at_cut"]["ventanas"]
    ]
    bloques_casos = [
        {"terna": c["terna"], "symbol": c["symbol"],
         "direccion": c["direccion"], **b}
        for c in casos for b in c["post"]["bloques"]
    ]
    detalle_10s_casos = [
        {"terna": c["terna"], "symbol": c["symbol"],
         "direccion": c["direccion"], **f}
        for c in casos for f in c["post"]["detalle_10s_primer_cambio"]
    ]
    no_resolubles = [
        r for r in controles
        if (r["at_cut"]["avance_vs_3m_flujo"]["estado"] != ESTADO_RESOLUBLE
            or r["post"]["primer_cambio"]["estado"] != ESTADO_CAMBIO)
    ]

    derivados = {
        "casos_factores.jsonl": _jsonl("casos_factores.jsonl", casos),
        "casos_bloques.jsonl": _jsonl("casos_bloques.jsonl", bloques_casos),
        "casos_detalle_10s.jsonl": _jsonl("casos_detalle_10s.jsonl",
                                          detalle_10s_casos),
        "casos_ventanas.jsonl": _jsonl("casos_ventanas.jsonl", ventanas_casos),
        "anclas_factores.jsonl": _jsonl("anclas_factores.jsonl", controles),
        "anclas_cambios.jsonl": _jsonl(
            "anclas_cambios.jsonl",
            [{"terna": r["terna"], "symbol": r["symbol"],
              "direccion": r["direccion"], **r["post"]} for r in controles]),
        "anclas_no_resolubles.jsonl": _jsonl("anclas_no_resolubles.jsonl",
                                             no_resolubles),
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
        "casos": len(casos),
        "verificacion_casos": verificacion_casos["coinciden"],
        "anclas": len(controles),
        "verificacion_anclas": verificacion_anclas["coinciden"],
        "avance_vs_3m_evaluables": at_cut["avance_vs_3m_flujo"]["normalizada"]["n"],
        "primer_cambio_observado": cambios["eventos"]["primer_cambio"]["estados"].get(
            ESTADO_CAMBIO, 0),
        "primer_giro_observado": cambios["eventos"]["primer_giro"]["estados"].get(
            ESTADO_CAMBIO, 0),
        "conclusion_giro": conclusion_giro["conclusion"],
        "conclusion_cambio": conclusion_cambio["conclusion"],
        "resumen": str(resumen_ruta),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
