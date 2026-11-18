# -*- coding: utf-8 -*-
"""Diagnostico de los cuatro casos del patron en la ventana 4 (sin mercado).

Pregunta: que distinguia a STRKUSDT LONG de ARIAUSDT LONG y de los dos
BLESSUSDT SHORT; si esperar la confirmacion de un minuto habria ayudado frente
a continuar inmediatamente.

Reglas fijadas ANTES de calcular:
  - Solo lectura de la captura publicada y de sus derivados ya publicados. Sin
    Binance, sin capturas nuevas, sin ordenes, sin cambios de patron, umbrales,
    horizonte, agrupacion ni estrategia.
  - Los cuatro casos son las 4 anclas con patron del universo igualado de 501
    ternas. Se verifican contra `episodios_patron_originales.jsonl` publicado.
  - Espera = primer minuto exacto posterior a la terna: el que empieza en el
    cierre nominal de la tercera ventana (`fin_c`). Corte tardio =
    max(corte original, fin_c + 60 s, `as_of_ms` del flujo de ese minuto).
    Entrada tardia = primer minuto estrictamente posterior al corte tardio, sin
    saltar huecos. Salida = apertura exactamente 5 minutos despues.
  - Flujo alineado = s * (compras - ventas), s=+1 LONG, -1 SHORT. Positivo ->
    continuacion confirmada; negativo -> candidato experimental a reversion;
    cero -> sin confirmacion. Fila ausente, incompleta (`data_quality` distinto
    de OK) o sin `as_of_ms` posterior al cierre del minuto -> no resoluble.
  - Medicion identica a la publicada: apertura del primer minuto posterior al
    corte y apertura 5 minutos despues; vela exacta obligatoria; sin relleno.
  - Extension previa = avance alineado entre el primer y el tercer cierre de la
    terna. Referencia = mediana de los movimientos absolutos del mismo
    horizonte (3 ventanas) de ternas previas NO solapadas del mismo contrato,
    estrictamente anteriores al inicio de la terna. Ventana historica = la
    propia captura (no se usa historia externa). Minimo fijado: 6 ternas
    previas. Historia insuficiente o referencia cero -> NO_RESOLUBLE.
  - La reversion tardia se mide desde el MISMO corte tardio y con los MISMOS
    precios que la continuacion tardia; nunca reutiliza la entrada original.
  - Minimo de 30 pares resolubles para la conclusion estadistica; por debajo,
    `datos insuficientes`. Los cuatro casos solo formulan hipotesis.
"""

import argparse
import io
import json
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

VERSION_DIAGNOSTICO = "diagnostico-cuatro-casos-v1"
VERSION_ANCLAS = VERSION_COMPARACION

MIN_TERN_PREVIAS = 6
EPS_FLUJO = 1e-9

MOTIVO_ESPERA_AUSENTE = "flujo_espera_ausente"
MOTIVO_ESPERA_INCOMPLETO = "flujo_espera_incompleto"
MOTIVO_ESPERA_SIN_DISPONIBILIDAD = "flujo_espera_sin_disponibilidad"
MOTIVO_ESPERA_INCOHERENTE = "flujo_espera_incoherente"

CONTINUACION = "continuacion_confirmada"
REVERSION = "candidato_a_reversion"
SIN_CONFIRMACION = "sin_confirmacion"


# ---------------------------------------------------------------------------
# Fuente: filas crudas de flujo y libro
# ---------------------------------------------------------------------------

def cargar_filas(
    db_path: Path, run_id: str
) -> Tuple[Dict[Tuple[str, int], Dict[str, Any]],
           Dict[Tuple[str, int], Dict[str, Any]], Dict[str, Any]]:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    flujo: Dict[Tuple[str, int], Dict[str, Any]] = {}
    libro: Dict[Tuple[str, int], Dict[str, Any]] = {}
    audit: Counter = Counter()
    for r in con.execute("select * from research_flow_1m"):
        if r["run_id"] != run_id:
            audit["flujo_otro_run_id"] += 1
            continue
        flujo[(r["symbol"], int(r["bucket_start"]))] = dict(r)
    for r in con.execute("select * from research_book_1m"):
        if r["run_id"] != run_id:
            audit["libro_otro_run_id"] += 1
            continue
        libro[(r["symbol"], int(r["bucket_start"]))] = dict(r)
    con.close()
    return flujo, libro, {
        "filas_flujo": len(flujo),
        "filas_libro": len(libro),
        "flujo_otro_run_id": audit["flujo_otro_run_id"],
        "libro_otro_run_id": audit["libro_otro_run_id"],
    }


def _signo(direccion: str) -> float:
    if direccion == "LONG":
        return 1.0
    if direccion == "SHORT":
        return -1.0
    raise SystemExit(f"direccion desconocida: {direccion}")


def _opuesta(direccion: str) -> str:
    return "SHORT" if direccion == "LONG" else "LONG"


# ---------------------------------------------------------------------------
# Espera de un minuto
# ---------------------------------------------------------------------------

def minuto_de_espera(cierre_nominal_ms: int) -> Tuple[int, int]:
    fin = int(cierre_nominal_ms)
    if fin % VENTANA_MS != 0:
        raise SystemExit(f"cierre nominal no alineado al minuto: {fin}")
    return fin, fin + VENTANA_MS


def clasificar_flujo(alineado: float, eps: float = EPS_FLUJO) -> str:
    if alineado > eps:
        return CONTINUACION
    if alineado < -eps:
        return REVERSION
    return SIN_CONFIRMACION


def evaluar_espera(
    fila: Optional[Dict[str, Any]],
    direccion: str,
    cut_ms: int,
    cierre_nominal_ms: int,
) -> Dict[str, Any]:
    """Clasifica el flujo del primer minuto posterior a la terna.

    No mide precios: solo decide si el flujo confirma, contradice o no informa,
    y fija el corte tardio. Cualquier ausencia o incoherencia deja el caso sin
    resolver con motivo; no se rellena.
    """
    inicio, fin = minuto_de_espera(cierre_nominal_ms)
    base = {
        "espera_inicio_ms": inicio,
        "espera_fin_ms": fin,
        "espera_inicio_iso": utc_iso(inicio),
        "espera_fin_iso": utc_iso(fin),
        "estado": "no_resoluble",
        "motivo": None,
        "cut_tardio_ms": None,
        "entrada_tardia_ms": None,
        "salida_tardia_ms": None,
        "desplazamiento_ms": None,
    }
    if fila is None:
        return {**base, "motivo": MOTIVO_ESPERA_AUSENTE}
    if int(fila.get("bucket_start", -1)) != inicio or int(fila.get("bucket_end", -1)) != fin:
        return {**base, "motivo": MOTIVO_ESPERA_INCOHERENTE,
                "bucket_start": fila.get("bucket_start"),
                "bucket_end": fila.get("bucket_end")}
    if fila.get("buy_notional") is None or fila.get("sell_notional") is None:
        return {**base, "motivo": MOTIVO_ESPERA_INCOMPLETO,
                "data_quality": fila.get("data_quality")}
    calidad = str(fila.get("data_quality"))
    if calidad != "OK":
        as_of = fila.get("as_of_ms")
        return {**base, "motivo": MOTIVO_ESPERA_INCOMPLETO,
                "data_quality": calidad,
                "buy_notional": float(fila["buy_notional"]),
                "sell_notional": float(fila["sell_notional"]),
                "as_of_ms": int(as_of) if as_of is not None else None,
                "as_of_iso": utc_iso(int(as_of)) if as_of is not None else None,
                "flujo_disponible_antes_del_cierre": (
                    as_of is not None and int(as_of) < fin)}
    as_of = fila.get("as_of_ms")
    if as_of is None:
        return {**base, "motivo": MOTIVO_ESPERA_SIN_DISPONIBILIDAD,
                "data_quality": calidad}
    as_of = int(as_of)
    if as_of < fin:
        return {**base, "motivo": MOTIVO_ESPERA_SIN_DISPONIBILIDAD,
                "data_quality": calidad,
                "as_of_ms": as_of,
                "flujo_disponible_antes_del_cierre": True}

    compras = float(fila["buy_notional"])
    ventas = float(fila["sell_notional"])
    neto = compras - ventas
    alineado = _signo(direccion) * neto
    cut_tardio = max(int(cut_ms), fin, as_of)
    entrada_tardia = _referencia_entrada(cut_tardio)
    entrada_original = _referencia_entrada(int(cut_ms))
    return {
        **base,
        "estado": "resoluble",
        "motivo": None,
        "data_quality": calidad,
        "buy_notional": compras,
        "sell_notional": ventas,
        "flujo_neto": neto,
        "flujo_alineado": alineado,
        "clasificacion": clasificar_flujo(alineado),
        "as_of_ms": as_of,
        "as_of_iso": utc_iso(as_of),
        "last_event_ms": fila.get("last_event_ms"),
        "demora_disponibilidad_ms": as_of - fin,
        "cut_tardio_ms": cut_tardio,
        "cut_tardio_iso": utc_iso(cut_tardio),
        "entrada_tardia_ms": entrada_tardia,
        "salida_tardia_ms": entrada_tardia + HORIZONTE_MS,
        "entrada_original_ms": entrada_original,
        "desplazamiento_ms": entrada_tardia - entrada_original,
        "flujo_disponible_antes_del_cierre": False,
    }


# ---------------------------------------------------------------------------
# Extension previa
# ---------------------------------------------------------------------------

def ternas_previas_no_solapadas(
    ventanas: List[Any], t0: int
) -> List[Tuple[Any, Any, Any]]:
    """Ternas contiguas y no solapadas estrictamente anteriores a `t0`.

    Se parte la serie acreditada en tramos contiguos y, en cada tramo, se toman
    ternas desde el final hacia atras de tres en tres. Asi ninguna terna previa
    comparte ventanas con otra ni con la terna evaluada.
    """
    previas = [w for w in ventanas if int(w.ventana_fin_ms) <= int(t0)]
    previas.sort(key=lambda w: int(w.ventana_inicio_ms))
    tramos: List[List[Any]] = []
    for w in previas:
        if tramos and int(w.ventana_inicio_ms) == int(tramos[-1][-1].ventana_fin_ms):
            tramos[-1].append(w)
        else:
            tramos.append([w])
    ternas: List[Tuple[Any, Any, Any]] = []
    for tramo in tramos:
        i = len(tramo) - 1
        while i >= 2:
            ternas.append((tramo[i - 2], tramo[i - 1], tramo[i]))
            i -= 3
    ternas.sort(key=lambda t: int(t[0].ventana_inicio_ms))
    return ternas


def extension_previa(
    ventanas_terna: Tuple[Any, Any, Any],
    previas: List[Tuple[Any, Any, Any]],
    direccion: str,
) -> Dict[str, Any]:
    a, _, c = ventanas_terna
    p1 = float(a.precio_cierre)
    p3 = float(c.precio_cierre)
    bruto = _signo(direccion) * (p3 / p1 - 1.0) * 1e4
    movimientos = [
        abs((float(t[2].precio_cierre) / float(t[0].precio_cierre) - 1.0) * 1e4)
        for t in previas
    ]
    n = len(movimientos)
    referencia = _mediana(movimientos) if movimientos else None
    base = {
        "avance_bruto_bps": _redondear(bruto),
        "ternas_previas_no_solapadas": n,
        "minimo_ternas_previas": MIN_TERN_PREVIAS,
        "referencia_bps": _redondear(referencia),
    }
    if n < MIN_TERN_PREVIAS:
        return {**base, "estado": "no_resoluble", "motivo": "historia_insuficiente"}
    if referencia is None or referencia <= 0:
        return {**base, "estado": "no_resoluble", "motivo": "referencia_cero"}
    return {
        **base,
        "estado": "resoluble",
        "motivo": None,
        "extension_normalizada": _redondear(bruto / referencia),
    }


# ---------------------------------------------------------------------------
# Resultado tardio (continuacion y reversion desde el mismo corte)
# ---------------------------------------------------------------------------

def resolver_tardia(
    alerta: Dict[str, Any],
    espera: Dict[str, Any],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
) -> Dict[str, Any]:
    """Mide continuacion y reversion desde el corte tardio, con los mismos precios."""
    if espera.get("estado") != "resoluble":
        return {
            "estado": "no_resoluble",
            "motivo": espera.get("motivo"),
            "entrada_ms": None,
            "salida_ms": None,
            "continuacion_bps": None,
            "reversion_bps": None,
            "reutiliza_entrada_original": None,
        }
    cut_tardio = int(espera["cut_tardio_ms"])
    pseudo = {
        "symbol": alerta["symbol"],
        "direccion": alerta["direccion"],
        "cut_ms": cut_tardio,
    }
    continuacion = resolver_alerta(pseudo, velas)
    reversion = resolver_alerta({**pseudo, "direccion": _opuesta(alerta["direccion"])}, velas)
    if continuacion["entrada_ms"] != reversion["entrada_ms"]:
        raise SystemExit("continuacion y reversion no comparten entrada")
    if continuacion["salida_ms"] != reversion["salida_ms"]:
        raise SystemExit("continuacion y reversion no comparten salida")
    if continuacion["entrada_ms"] != int(espera["entrada_tardia_ms"]):
        raise SystemExit("la entrada tardia no coincide con el corte tardio")
    entrada_original = _referencia_entrada(int(alerta["cut_ms"]))
    return {
        "estado": continuacion["estado"],
        "motivo": continuacion.get("motivo"),
        "entrada_ms": continuacion["entrada_ms"],
        "salida_ms": continuacion["salida_ms"],
        "precio_entrada": continuacion.get("precio_entrada"),
        "precio_salida": continuacion.get("precio_salida"),
        "continuacion_bps": _redondear(continuacion.get("retorno_bps")),
        "reversion_bps": _redondear(reversion.get("retorno_bps")),
        "adverso_continuacion_bps": continuacion.get("adverso_bps"),
        "favorable_continuacion_bps": continuacion.get("favorable_bps"),
        "trayectoria_completa": continuacion.get("trayectoria_completa"),
        "misma_entrada_continuacion_y_reversion": True,
        "reutiliza_entrada_original": continuacion["entrada_ms"] == entrada_original,
        "demora_total_tardia_ms": continuacion["entrada_ms"] - cut_tardio,
    }


# ---------------------------------------------------------------------------
# Reconstruccion de los cuatro casos
# ---------------------------------------------------------------------------

def _ventana_detalle(
    w: Any,
    direccion: str,
    flujo: Dict[Tuple[str, int], Dict[str, Any]],
    libro: Dict[Tuple[str, int], Dict[str, Any]],
    anterior: Optional[Any],
) -> Dict[str, Any]:
    inicio = int(w.ventana_inicio_ms)
    fin = int(w.ventana_fin_ms)
    f = flujo.get((w.symbol, inicio), {})
    b = libro.get((w.symbol, inicio), {})
    neto = w.flujo_neto
    contraria = w.profundidad_contraria(direccion)
    propia = w.bid_notional_top20 if direccion == "LONG" else w.ask_notional_top20
    variacion = None
    if anterior is not None and int(anterior.ventana_fin_ms) == inicio:
        variacion = _redondear(
            (float(w.precio_cierre) / float(anterior.precio_cierre) - 1.0) * 1e4
        )
    return {
        "ventana": w.observation_id,
        "inicio_ms": inicio,
        "fin_ms": fin,
        "inicio_iso": utc_iso(inicio),
        "fin_iso": utc_iso(fin),
        "buy_notional": _redondear(w.buy_notional),
        "sell_notional": _redondear(w.sell_notional),
        "flujo_neto": _redondear(neto),
        "flujo_alineado": _redondear(_signo(direccion) * neto) if neto is not None else None,
        "q": _redondear(w.q(direccion)),
        "profundidad_contraria": _redondear(contraria),
        "profundidad_propia": _redondear(propia),
        "precio_cierre": float(w.precio_cierre),
        "variacion_cierre_bps": variacion,
        "disponibilidad_ms": int(w.disponibilidad_ms),
        "disponibilidad_iso": w.disponibilidad_iso,
        "demora_disponibilidad_ms": int(w.disponibilidad_ms) - fin,
        "flow_as_of_ms": w.cobertura.get("flow_as_of_ms"),
        "book_as_of_ms": w.cobertura.get("book_as_of_ms"),
        "flow_data_quality": w.cobertura.get("flow_data_quality"),
        "libro_degradado": int(b.get("degraded", -1)) if b else None,
        "libro_huecos_profundidad": int(b.get("depth_gaps", -1)) if b else None,
        "libro_cruzado": int(b.get("crossed", -1)) if b else None,
        "integridad_valida": bool(w.integridad_valida),
        "contigua_anterior": anterior is not None and int(anterior.ventana_fin_ms) == inicio,
        "last_event_ms": f.get("last_event_ms"),
    }


def _minutos_sin_fila(
    flujo: Dict[Tuple[str, int], Dict[str, Any]], symbol: str, desde: int, hasta: int
) -> List[int]:
    return [
        t for t in range(int(desde), int(hasta), VENTANA_MS)
        if (symbol, t) not in flujo
    ]


def _trayectoria(
    velas: Dict[str, Dict[int, Dict[str, Any]]], symbol: str, entrada_ms: int
) -> List[Dict[str, Any]]:
    serie = velas.get(symbol, {})
    filas = []
    for i in range(6):
        t = int(entrada_ms) + i * VENTANA_MS
        v = serie.get(t)
        filas.append({
            "open_time": t,
            "open_time_iso": utc_iso(t),
            "rol": "salida" if i == 5 else f"minuto_{i}",
            "presente": v is not None,
            "open": v["open"] if v else None,
            "high": v["high"] if v else None,
            "low": v["low"] if v else None,
            "close": v["close"] if v else None,
            "final": v["final"] if v else None,
            "conflictiva": v["conflictiva"] if v else None,
        })
    return filas


def reconstruir_caso(
    episodio: Dict[str, Any],
    fila_terna: Dict[str, Any],
    indice: Dict[str, Dict[int, Any]],
    por_symbol: Dict[str, List[Any]],
    flujo: Dict[Tuple[str, int], Dict[str, Any]],
    libro: Dict[Tuple[str, int], Dict[str, Any]],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
) -> Dict[str, Any]:
    symbol = episodio["symbol"]
    direccion = episodio["direccion"]
    inicios = [int(x) for x in fila_terna["ventanas"]]
    a, b, c = (indice[symbol][i] for i in inicios)
    if int(b.ventana_inicio_ms) != int(a.ventana_fin_ms):
        raise SystemExit(f"terna no contigua en {fila_terna['terna']}")
    if int(c.ventana_inicio_ms) != int(b.ventana_fin_ms):
        raise SystemExit(f"terna no contigua en {fila_terna['terna']}")
    corte = corte_de_terna(a, b, c)
    if corte != int(episodio["cut_ms"]) or corte != int(fila_terna["cut_ms"]):
        raise SystemExit(f"corte incoherente en {fila_terna['terna']}")
    if int(c.ventana_fin_ms) != int(episodio["cierre_nominal_ms"]):
        raise SystemExit(f"cierre nominal incoherente en {fila_terna['terna']}")

    ventanas_symbol = por_symbol[symbol]
    posicion = {int(w.ventana_inicio_ms): i for i, w in enumerate(ventanas_symbol)}
    i_a = posicion[int(a.ventana_inicio_ms)]
    anterior_a = ventanas_symbol[i_a - 1] if i_a > 0 else None

    detalle_ventanas = [
        _ventana_detalle(a, direccion, flujo, libro, anterior_a),
        _ventana_detalle(b, direccion, flujo, libro, a),
        _ventana_detalle(c, direccion, flujo, libro, b),
    ]

    previas = ternas_previas_no_solapadas(ventanas_symbol, int(a.ventana_inicio_ms))
    extension = extension_previa((a, b, c), previas, direccion)

    fin_c = int(c.ventana_fin_ms)
    espera = evaluar_espera(
        flujo.get((symbol, fin_c)), direccion, corte, fin_c
    )
    original = resolver_alerta(episodio, velas)
    tardia = resolver_tardia(episodio, espera, velas)

    alineado_3 = _signo(direccion) * (float(c.buy_notional) - float(c.sell_notional))
    alineado_total = sum(
        _signo(direccion) * (float(w.buy_notional) - float(w.sell_notional))
        for w in (a, b, c)
    )
    ratio_fuerza = None
    cambio_porcentual = None
    if espera.get("estado") == "resoluble" and alineado_3 != 0:
        ratio_fuerza = _redondear(espera["flujo_alineado"] / alineado_3)
        cambio_porcentual = _redondear((espera["flujo_alineado"] / alineado_3 - 1.0) * 100.0)

    delta_continuacion = None
    if (original.get("estado") == "resoluble"
            and tardia.get("estado") == "resoluble"
            and tardia.get("continuacion_bps") is not None):
        delta_continuacion = _redondear(
            tardia["continuacion_bps"] - original["retorno_bps"]
        )

    salida_referencia = int(original["salida_ms"])
    hasta = salida_referencia
    if tardia.get("salida_ms"):
        hasta = max(hasta, int(tardia["salida_ms"]))
    ausentes = _minutos_sin_fila(flujo, symbol, int(original["entrada_ms"]), hasta)

    return {
        "symbol": symbol,
        "direccion": direccion,
        "terna": fila_terna["terna"],
        "decision": fila_terna["decision"],
        "cut_ms": corte,
        "cut_iso": utc_iso(corte),
        "cierre_nominal_ms": fin_c,
        "demora_corte_ms": corte - fin_c,
        "senal": {
            "ventanas": detalle_ventanas,
            "cierres": [float(w.precio_cierre) for w in (a, b, c)],
            "avance_bruto_bps": extension["avance_bruto_bps"],
            "q": [d["q"] for d in detalle_ventanas],
            "q_crecimiento": (
                _redondear(detalle_ventanas[2]["q"] / detalle_ventanas[0]["q"])
                if detalle_ventanas[0]["q"] else None
            ),
            "profundidad_contraria_decreciente": (
                detalle_ventanas[0]["profundidad_contraria"] is not None
                and detalle_ventanas[0]["profundidad_contraria"]
                > detalle_ventanas[1]["profundidad_contraria"]
                > detalle_ventanas[2]["profundidad_contraria"]
            ),
            "flujo_alineado_tercera_ventana": _redondear(alineado_3),
            "flujo_alineado_total_terna": _redondear(alineado_total),
            "huecos": {
                "ventanas_contiguas": True,
                "ventana_previa_contigua": bool(detalle_ventanas[0]["contigua_anterior"]),
                "hueco_previo_ms": (
                    None if detalle_ventanas[0]["contigua_anterior"]
                    else int(a.ventana_inicio_ms)
                    - int(ventanas_symbol[i_a - 1].ventana_fin_ms)
                    if i_a > 0 else None
                ),
            },
        },
        "extension_previa": extension,
        "espera": {
            **espera,
            "flujo_alineado_tercera_ventana": _redondear(alineado_3),
            "flujo_alineado_total_terna": _redondear(alineado_total),
            "ratio_fuerza_vs_tercera_ventana": ratio_fuerza,
            "cambio_porcentual_vs_tercera_ventana": cambio_porcentual,
        },
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
        "tardia": tardia,
        "delta_continuacion_bps": delta_continuacion,
        "trayectoria_original": _trayectoria(velas, symbol, int(original["entrada_ms"])),
        "tramo_sin_flujo_persistido": {
            "desde_ms": int(original["entrada_ms"]),
            "hasta_ms": hasta,
            "minutos": ausentes,
            "minutos_iso": [utc_iso(t) for t in ausentes],
        },
    }


# ---------------------------------------------------------------------------
# Controles: 143 anclas comunes
# ---------------------------------------------------------------------------

def diagnostico_ancla(
    episodio: Dict[str, Any],
    fila_terna: Dict[str, Any],
    indice: Dict[str, Dict[int, Any]],
    por_symbol: Dict[str, List[Any]],
    flujo: Dict[Tuple[str, int], Dict[str, Any]],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
) -> Dict[str, Any]:
    symbol = episodio["symbol"]
    direccion = episodio["direccion"]
    inicios = [int(x) for x in fila_terna["ventanas"]]
    a, b, c = (indice[symbol][i] for i in inicios)
    if corte_de_terna(a, b, c) != int(episodio["cut_ms"]):
        raise SystemExit(f"corte incoherente en {fila_terna['terna']}")

    original = resolver_alerta(episodio, velas)
    espera = evaluar_espera(
        flujo.get((symbol, int(c.ventana_fin_ms))),
        direccion,
        int(episodio["cut_ms"]),
        int(c.ventana_fin_ms),
    )
    tardia = resolver_tardia(episodio, espera, velas)
    previas = ternas_previas_no_solapadas(por_symbol[symbol], int(a.ventana_inicio_ms))
    extension = extension_previa((a, b, c), previas, direccion)

    delta = None
    if (original.get("estado") == "resoluble"
            and tardia.get("estado") == "resoluble"
            and tardia.get("continuacion_bps") is not None):
        delta = _redondear(tardia["continuacion_bps"] - original["retorno_bps"])

    alineado_3 = _signo(direccion) * (float(c.buy_notional) - float(c.sell_notional))
    ratio = None
    if espera.get("estado") == "resoluble" and alineado_3 != 0:
        ratio = _redondear(espera["flujo_alineado"] / alineado_3)

    return {
        "symbol": symbol,
        "direccion": direccion,
        "terna": fila_terna["terna"],
        "cut_ms": int(episodio["cut_ms"]),
        "cierre_nominal_ms": int(episodio["cierre_nominal_ms"]),
        "demora_corte_ms": int(episodio["demora_corte_ms"]),
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
            "trayectoria_completa": original.get("trayectoria_completa"),
        },
        "espera": espera,
        "tardia": tardia,
        "extension_previa": extension,
        "delta_continuacion_bps": delta,
        "ratio_fuerza_vs_tercera_ventana": ratio,
    }


# ---------------------------------------------------------------------------
# Agregados
# ---------------------------------------------------------------------------

def _metricas(registros: List[Dict[str, Any]]) -> Dict[str, Any]:
    original_ok = [r for r in registros if r["original"]["estado"] == "resoluble"]
    espera_ok = [r for r in registros if r["espera"]["estado"] == "resoluble"]
    tardia_ok = [r for r in registros if r["tardia"]["estado"] == "resoluble"]
    pares = [r for r in registros
             if r["original"]["estado"] == "resoluble"
             and r["tardia"]["estado"] == "resoluble"
             and r["tardia"]["continuacion_bps"] is not None]
    orig = [float(r["original"]["retorno_bps"]) for r in pares]
    tard = [float(r["tardia"]["continuacion_bps"]) for r in pares]
    delta = [t - o for o, t in zip(orig, tard)]

    negativas = [r for r in pares if r["original"]["retorno_bps"] < 0]
    mejoran_negativas = [r for r in negativas
                         if r["tardia"]["continuacion_bps"] > r["original"]["retorno_bps"]]
    terminan_no_negativas = [r for r in mejoran_negativas
                             if r["tardia"]["continuacion_bps"] >= 0]
    positivas = [r for r in pares if r["original"]["retorno_bps"] > 0]
    empeoran_positivas = [r for r in positivas
                          if r["tardia"]["continuacion_bps"] < r["original"]["retorno_bps"]]

    reversion = [r for r in tardia_ok
                 if r["espera"]["clasificacion"] == REVERSION]
    rev_cont = [float(r["tardia"]["continuacion_bps"]) for r in reversion]
    rev_rev = [float(r["tardia"]["reversion_bps"]) for r in reversion]

    return {
        "anclas": len(registros),
        "original_resolubles": len(original_ok),
        "espera_resolubles": len(espera_ok),
        "tardia_resolubles": len(tardia_ok),
        "pares_comparables": len(pares),
        "clasificacion": dict(Counter(
            r["espera"]["clasificacion"] for r in espera_ok)),
        "original_media_bps": _redondear(_media(orig)),
        "original_mediana_bps": _redondear(_mediana(orig)),
        "tardia_media_bps": _redondear(_media(tard)),
        "tardia_mediana_bps": _redondear(_mediana(tard)),
        "delta_media_bps": _redondear(_media(delta)),
        "delta_mediana_bps": _redondear(_mediana(delta)),
        "delta_positivo": sum(1 for d in delta if d > 0),
        "delta_negativo": sum(1 for d in delta if d < 0),
        "delta_cero": sum(1 for d in delta if d == 0),
        "perdidas_evitadas": {
            "n_mejoran_siendo_negativas": len(mejoran_negativas),
            "de_esas_terminan_no_negativas": len(terminan_no_negativas),
            "mejora_media_bps": _redondear(_media([
                r["tardia"]["continuacion_bps"] - r["original"]["retorno_bps"]
                for r in mejoran_negativas
            ])),
        },
        "oportunidades_perdidas": {
            "n_empeoran_siendo_positivas": len(empeoran_positivas),
            "empeora_media_bps": _redondear(_media([
                r["tardia"]["continuacion_bps"] - r["original"]["retorno_bps"]
                for r in empeoran_positivas
            ])),
        },
        "reversion": {
            "n": len(reversion),
            "continuacion_media_bps": _redondear(_media(rev_cont)),
            "continuacion_mediana_bps": _redondear(_mediana(rev_cont)),
            "reversion_media_bps": _redondear(_media(rev_rev)),
            "reversion_mediana_bps": _redondear(_mediana(rev_rev)),
            "continuacion_positiva": sum(1 for x in rev_cont if x > 0),
            "reversion_positiva": sum(1 for x in rev_rev if x > 0),
        },
        "no_resolubles_espera": dict(Counter(
            r["espera"].get("motivo") for r in registros
            if r["espera"]["estado"] != "resoluble")),
        "no_resolubles_tardia": dict(Counter(
            r["tardia"].get("motivo") for r in registros
            if r["tardia"]["estado"] != "resoluble")),
        "desplazamiento_entrada": dict(Counter(
            r["espera"].get("desplazamiento_ms") for r in espera_ok)),
    }


def _metricas_extension(registros: List[Dict[str, Any]]) -> Dict[str, Any]:
    evaluables = [r for r in registros if r["extension_previa"]["estado"] == "resoluble"]
    normalizadas = [float(r["extension_previa"]["extension_normalizada"])
                    for r in evaluables]
    brutas = [float(r["extension_previa"]["avance_bruto_bps"]) for r in registros]
    return {
        "evaluables": len(evaluables),
        "no_resolubles_por_motivo": dict(Counter(
            r["extension_previa"]["motivo"] for r in registros
            if r["extension_previa"]["estado"] != "resoluble")),
        "mediana_normalizada": _redondear(_mediana(normalizadas)),
        "min_normalizada": _redondear(min(normalizadas)) if normalizadas else None,
        "max_normalizada": _redondear(max(normalizadas)) if normalizadas else None,
        "mediana_avance_bruto_bps": _redondear(_mediana(brutas)),
        "detalle_evaluables": [
            {
                "symbol": r["symbol"],
                "direccion": r["direccion"],
                "terna": r["terna"],
                "avance_bruto_bps": r["extension_previa"]["avance_bruto_bps"],
                "ternas_previas_no_solapadas": r["extension_previa"]["ternas_previas_no_solapadas"],
                "referencia_bps": r["extension_previa"]["referencia_bps"],
                "extension_normalizada": r["extension_previa"]["extension_normalizada"],
                "retorno_original_bps": r["original"]["retorno_bps"],
            }
            for r in evaluables
        ],
    }


def _por_simbolo(registros: List[Dict[str, Any]]) -> Dict[str, Any]:
    por: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in registros:
        por[r["symbol"]].append(r)
    salida = {}
    for symbol, lista in sorted(por.items()):
        m = _metricas(lista)
        salida[symbol] = {
            "anclas": m["anclas"],
            "pares_comparables": m["pares_comparables"],
            "original_media_bps": m["original_media_bps"],
            "tardia_media_bps": m["tardia_media_bps"],
            "delta_media_bps": m["delta_media_bps"],
            "clasificacion": m["clasificacion"],
        }
    return salida


def _cruce_cobertura(registros: List[Dict[str, Any]]) -> Dict[str, int]:
    cruce = Counter()
    for r in registros:
        o = r["original"]["estado"] == "resoluble"
        t = r["tardia"]["estado"] == "resoluble"
        cruce[("original_ok" if o else "original_no",
               "tardia_ok" if t else "tardia_no")] += 1
    return {
        "original_ok_y_tardia_ok": cruce[("original_ok", "tardia_ok")],
        "original_ok_y_tardia_no": cruce[("original_ok", "tardia_no")],
        "original_no_y_tardia_ok": cruce[("original_no", "tardia_ok")],
        "original_no_y_tardia_no": cruce[("original_no", "tardia_no")],
    }


def concluir_espera(metricas: Dict[str, Any],
                    por_direccion: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    n = int(metricas["pares_comparables"])
    base = {
        "minimo_pares_resolubles": MIN_EPISODIOS,
        "pares_comparables": n,
        "regla": "con 30 o mas pares, mejora solo si la media y la mediana del "
                 "delta (tardia - original, misma direccion) son positivas",
    }
    if n < MIN_EPISODIOS:
        return {
            **base,
            "conclusion": "datos insuficientes",
            "motivo": f"pares comparables={n}; minimo fijado={MIN_EPISODIOS}",
        }
    dm = metricas["delta_media_bps"]
    dmed = metricas["delta_mediana_bps"]
    evidencia = [f"delta medio {dm} bps; delta mediano {dmed} bps"]
    for direccion, m in por_direccion.items():
        evidencia.append(
            f"{direccion}: n={m['pares_comparables']}, "
            f"delta medio {m['delta_media_bps']} bps, "
            f"delta mediano {m['delta_mediana_bps']} bps"
        )
    if dm is not None and dmed is not None and dm > 0 and dmed > 0:
        return {
            **base,
            "conclusion": "esperar un minuto muestra mejora media y mediana en esta muestra",
            "motivo": "la continuacion medida desde el corte tardio supera a la "
                      "continuacion original en media y mediana",
            "evidencia": evidencia,
        }
    return {
        **base,
        "conclusion": "esperar un minuto no muestra mejora en esta muestra",
        "motivo": "la continuacion medida desde el corte tardio no supera a la "
                  "original en media y mediana",
        "evidencia": evidencia,
    }


def diagnostico_casos(casos: List[Dict[str, Any]]) -> Dict[str, Any]:
    con_extension = [c for c in casos if c["extension_previa"]["estado"] == "resoluble"]
    sin_extension = [c for c in casos if c["extension_previa"]["estado"] != "resoluble"]
    con_reversion = [c for c in casos
                     if c["espera"].get("clasificacion") == REVERSION]
    con_continuacion = [c for c in casos
                        if c["espera"].get("clasificacion") == CONTINUACION]
    sin_confirmacion = [c for c in casos
                        if c["espera"].get("clasificacion") == SIN_CONFIRMACION]
    sin_resolver = [c for c in casos if c["espera"]["estado"] != "resoluble"]

    def _caso(c: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "symbol": c["symbol"],
            "direccion": c["direccion"],
            "terna": c["terna"],
            "retorno_original_bps": c["original"]["retorno_bps"],
            "clasificacion_espera": c["espera"].get("clasificacion"),
            "motivo_espera": c["espera"].get("motivo"),
            "ratio_fuerza_vs_tercera_ventana": c["espera"].get(
                "ratio_fuerza_vs_tercera_ventana"),
            "continuacion_tardia_bps": c["tardia"].get("continuacion_bps"),
            "reversion_tardia_bps": c["tardia"].get("reversion_bps"),
            "delta_continuacion_bps": c["delta_continuacion_bps"],
            "extension_estado": c["extension_previa"]["estado"],
            "extension_motivo": c["extension_previa"]["motivo"],
            "ternas_previas_no_solapadas": c["extension_previa"][
                "ternas_previas_no_solapadas"],
            "avance_bruto_bps": c["extension_previa"]["avance_bruto_bps"],
            "extension_normalizada": c["extension_previa"].get("extension_normalizada"),
        }

    return {
        "casos": len(casos),
        "extension_evaluable": len(con_extension),
        "extension_no_resoluble": len(sin_extension),
        "presion_continuacion": len(con_continuacion),
        "presion_reversion": len(con_reversion),
        "presion_sin_confirmacion": len(sin_confirmacion),
        "espera_no_resoluble": len(sin_resolver),
        "detalle": [_caso(c) for c in casos],
        "confirmados_con_menos_fuerza": [
            _caso(c) for c in con_continuacion
            if c["espera"].get("ratio_fuerza_vs_tercera_ventana") is not None
            and c["espera"]["ratio_fuerza_vs_tercera_ventana"] < 0.5
        ],
        "extension_insuficiente": [
            _caso(c) for c in sin_extension
        ],
        "hechos": {
            "extension": (
                f"contrastable en {len(con_extension)} de {len(casos)} casos; "
                f"minimo fijado {MIN_TERN_PREVIAS} ternas previas no solapadas"
            ),
            "presion": (
                f"continuacion {len(con_continuacion)}, reversion {len(con_reversion)}, "
                f"sin confirmacion {len(sin_confirmacion)}, "
                f"no resoluble {len(sin_resolver)}"
            ),
            "espera": (
                f"{sum(1 for c in casos if c['delta_continuacion_bps'] is not None)} "
                f"casos con continuacion tardia comparable"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Verificacion contra lo publicado
# ---------------------------------------------------------------------------

def _leer_jsonl(ruta: Path) -> List[Dict[str, Any]]:
    with io.open(ruta, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def verificar_casos_publicados(
    casos: List[Dict[str, Any]], publicados: List[Dict[str, Any]]
) -> Dict[str, Any]:
    por_terna = {p["terna"]: p for p in publicados}
    if len(por_terna) != len(publicados):
        raise SystemExit("episodios del patron publicados duplicados por terna")
    if len(casos) != len(publicados):
        raise SystemExit(
            f"los casos reconstruidos ({len(casos)}) no son los publicados "
            f"({len(publicados)})"
        )
    detalle = []
    for c in casos:
        p = por_terna.get(c["terna"])
        if p is None:
            raise SystemExit(f"caso no publicado: {c['terna']}")
        if p["symbol"] != c["symbol"] or p["direccion"] != c["direccion"]:
            raise SystemExit(f"caso incoherente con lo publicado: {c['terna']}")
        if int(p["cut_ms"]) != int(c["cut_ms"]):
            raise SystemExit(f"corte distinto en {c['terna']}")
        if p["estado"] != c["original"]["estado"]:
            raise SystemExit(f"estado distinto en {c['terna']}")
        if (p["estado"] == "resoluble"
                and abs(float(p["retorno_bps"]) - float(c["original"]["retorno_bps"])) > 1e-3):
            raise SystemExit(f"retorno distinto en {c['terna']}")
        detalle.append({
            "terna": c["terna"],
            "coincide": True,
            "retorno_publicado_bps": p["retorno_bps"],
            "retorno_recalculado_bps": c["original"]["retorno_bps"],
        })
    if set(por_terna) != {c["terna"] for c in casos}:
        raise SystemExit("los casos reconstruidos no cubren los publicados")
    return {"coinciden": len(detalle), "detalle": detalle}


def verificar_anclas_publicadas(
    registros: List[Dict[str, Any]], publicados: List[Dict[str, Any]]
) -> Dict[str, Any]:
    por_terna = {p["terna"]: p for p in publicados}
    if len(por_terna) != len(publicados):
        raise SystemExit("anclas publicadas duplicadas por terna")
    if len(registros) != len(publicados):
        raise SystemExit(
            f"anclas reconstruidas ({len(registros)}) distintas de las publicadas "
            f"({len(publicados)})"
        )
    for r in registros:
        p = por_terna.get(r["terna"])
        if p is None:
            raise SystemExit(f"ancla no publicada: {r['terna']}")
        if p["symbol"] != r["symbol"] or p["direccion"] != r["direccion"]:
            raise SystemExit(f"ancla incoherente con lo publicado: {r['terna']}")
        if int(p["cut_ms"]) != int(r["cut_ms"]):
            raise SystemExit(f"corte distinto en {r['terna']}")
        if p["estado"] != r["original"]["estado"]:
            raise SystemExit(f"estado distinto en {r['terna']}")
        if (p["estado"] == "resoluble"
                and abs(float(p["retorno_bps"]) - float(r["original"]["retorno_bps"])) > 1e-3):
            raise SystemExit(f"retorno distinto en {r['terna']}")
    if set(por_terna) != {r["terna"] for r in registros}:
        raise SystemExit("las anclas reconstruidas no cubren las publicadas")
    return {"coinciden": len(registros)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
            f"{hashes_antes['research.db']} != {db_declarada}"
        )

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

    # Los cuatro casos, reconstruidos desde las anclas y verificados contra lo
    # publicado.
    casos = [
        reconstruir_caso(e, por_terna[e["terna"]], indice, por_symbol, flujo, libro, velas)
        for e in sorted(anclas_con, key=lambda x: (x["cut_ms"], x["symbol"]))
    ]
    publicados_patron = _leer_jsonl(ruta_patron_pub)
    verificacion_casos = verificar_casos_publicados(casos, publicados_patron)

    # Controles: las 143 anclas comunes.
    controles = [
        diagnostico_ancla(e, por_terna[e["terna"]], indice, por_symbol, flujo, velas)
        for e in episodios
    ]
    publicados_anclas = _leer_jsonl(ruta_anclas_pub)
    verificacion_anclas = verificar_anclas_publicadas(controles, publicados_anclas)

    resumen_original_143 = resumir_episodios(episodios, velas)
    detalle_original_143 = resumen_original_143.pop("detalle")

    metricas_todas = _metricas(controles)
    por_direccion = {
        d: _metricas([r for r in controles if r["direccion"] == d])
        for d in ("LONG", "SHORT")
    }
    por_grupo = {
        "todas_las_anclas": metricas_todas,
        "anclas_sin_patron": _metricas([r for r in controles if not r["ancla_patron"]]),
        "anclas_con_patron": _metricas([r for r in controles if r["ancla_patron"]]),
    }
    reversion_total = metricas_todas["reversion"]
    conclusion = concluir_espera(metricas_todas, por_direccion)
    diagnostico = diagnostico_casos(casos)

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
        "pregunta": "que distinguia a STRKUSDT LONG de ARIAUSDT LONG y de los dos "
                    "BLESSUSDT SHORT; si esperar la confirmacion de un minuto "
                    "habria ayudado frente a continuar inmediatamente",
        "reglas_fijadas": {
            "espera": "primer minuto exacto posterior a la terna (inicio = cierre "
                      "nominal de la tercera ventana); corte tardio = max(corte "
                      "original, fin del minuto, as_of_ms del flujo)",
            "entrada": "apertura del primer minuto estrictamente posterior al corte",
            "salida": "apertura exactamente 5 minutos despues de la entrada",
            "flujo_alineado": "s * (compras - ventas), s=+1 LONG, -1 SHORT",
            "clasificacion": {
                "positivo": CONTINUACION,
                "negativo": REVERSION,
                "cero": SIN_CONFIRMACION,
            },
            "no_resoluble": "fila ausente, data_quality distinto de OK o as_of "
                            "anterior al cierre del minuto",
            "reversion": "mismo corte tardio y mismos precios que la continuacion",
            "extension_previa": "avance alineado entre el primer y tercer cierre; "
                                "referencia = mediana de movimientos absolutos de "
                                "ternas previas no solapadas del mismo contrato",
            "minimo_ternas_previas": MIN_TERN_PREVIAS,
            "minimo_pares_conclusion": MIN_EPISODIOS,
            "coste_sensibilidad_bps": COSTE_IDA_VUELTA_BPS,
            "funding": "UNKNOWN",
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
            "filas_crudas": audit_filas,
            "ventanas_validas_detector": audit_ventanas["ventanas_validas_detector"],
        },
        "casos": {
            "verificacion_publicado": verificacion_casos,
            "detalle": casos,
        },
        "controles": {
            "original_143_recalculado": {
                k: v for k, v in resumen_original_143.items() if k != "por_hora_utc"
            },
            "todas": metricas_todas,
            "por_direccion": por_direccion,
            "por_grupo": por_grupo,
            "por_simbolo": _por_simbolo(controles),
            "cruce_cobertura": _cruce_cobertura(controles),
            "extension_previa": _metricas_extension(controles),
        },
        "conclusion_estadistica": conclusion,
        "diagnostico_cuatro_casos": diagnostico,
        "cobertura_de_velas": {
            **{k: v for k, v in audit_velas.items() if k != "simbolos"},
            "simbolos": sorted(velas.keys()),
        },
        "limitaciones": [
            "captura ya usada en el desarrollo del detector: hallazgo exploratorio, no prueba independiente",
            "los cuatro casos formulan hipotesis; no validan una regla",
            "el minuto de espera se mide con el flujo agregado del minuto completo; no es una senal en vivo",
            "entrada y salida son aperturas de velas: no son fills ni incluyen latencia",
            "la reversion tardia comparte entrada y salida con la continuacion: solo cambia el signo",
            "cobertura de velas limitada a los simbolos consultados durante la captura",
            "flujo intermedio ausente en la captura no se rellena ni se atribuye a una causa",
            "funding UNKNOWN; el coste de 16 bps es solo sensibilidad documentada",
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
        {"terna": c["terna"], "symbol": c["symbol"], "direccion": c["direccion"], **v}
        for c in casos for v in c["senal"]["ventanas"]
    ]
    trayectorias = [
        {"terna": c["terna"], "symbol": c["symbol"], "direccion": c["direccion"], **fila}
        for c in casos for fila in c["trayectoria_original"]
    ]
    no_resolubles = [
        r for r in controles if r["espera"]["estado"] != "resoluble"
        or r["tardia"]["estado"] != "resoluble"
    ]

    derivados = {
        "casos_ventanas.jsonl": _jsonl("casos_ventanas.jsonl", ventanas_casos),
        "casos_trayectorias.jsonl": _jsonl("casos_trayectorias.jsonl", trayectorias),
        "casos_detalle.jsonl": _jsonl("casos_detalle.jsonl", casos),
        "anclas_diagnostico.jsonl": _jsonl("anclas_diagnostico.jsonl", controles),
        "anclas_no_resolubles.jsonl": _jsonl("anclas_no_resolubles.jsonl", no_resolubles),
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
        "pares_comparables": metricas_todas["pares_comparables"],
        "clasificacion": metricas_todas["clasificacion"],
        "delta_media_bps": metricas_todas["delta_media_bps"],
        "delta_mediana_bps": metricas_todas["delta_mediana_bps"],
        "conclusion": conclusion["conclusion"],
        "resumen": str(resumen_ruta),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
