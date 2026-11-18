# -*- coding: utf-8 -*-
"""Evaluación offline del patrón SECUENCIA-PRESION-V1 sobre la ventana 4.

Pregunta única:
  cuando el detector reconoce el patrón, ¿el precio se mueve en esa dirección
  durante los cinco minutos siguientes a un punto de entrada causal? ¿El patrón
  selecciona casos mejores que mirar solo la secuencia de precios?

Naturaleza de este script (fijada ANTES de mirar resultados):
  - Exploratorio. La captura `exp-v2-ventana-4-20261116a` ya se usó en el
    desarrollo del detector; no es una prueba independiente.
  - Solo lectura sobre las fuentes persistidas. Sin red, sin Binance, sin
    capturas, sin órdenes.
  - No modifica el detector ni sus condiciones LONG/SHORT. Solo convierte la
    salida acreditada del extractor (`C-cobertura-real.json` + `research.db`)
    en las ventanas que el detector ya sabe evaluar.
  - No ajusta umbrales, horizonte, agrupación ni universo después de ver los
    resultados.

Reglas causales (congeladas):
  - Corte de una terna = max(cierre nominal de la 3ª ventana, disponibilidad de
    sus componentes). Es tiempo RECONSTRUIDO: la captura no ejecutó el detector
    en vivo.
  - Referencia de entrada = apertura de la vela de 1 minuto que empieza
    ESTRICTAMENTE después del corte. Se exige esa vela exacta; un hueco no se
    salta buscando otro precio.
  - Referencia de salida = apertura de la vela exactamente 5 minutos después
    de la entrada.
  - Episodios: se ordenan las alertas por disponibilidad; para cada
    (contrato, dirección) la primera alerta abre episodio y las alertas de esa
    misma dirección con corte dentro de los 5 minutos siguientes son
    repetidas. Sin selección retrospectiva.

Criterio de conclusión (fijado antes de calcular):
  MIN_EPISODIOS = 30 para poder concluir algo distinto de "datos insuficientes".
  - "datos insuficientes" si el grupo del patrón o el grupo de solo precio sin
    patrón tiene menos de 30 episodios resolubles, o si la ventaja de la media
    cambia de signo al excluir el símbolo con más episodios.
  - "merece una prueba independiente" si la media y la mediana alineadas del
    patrón superan a las de la referencia de solo precio y la ventaja es
    robusta a la exclusión del símbolo dominante.
  - "no muestra mejora en esta muestra" en el resto.

Costes (sensibilidad aparte, documentados en
`docs/evidence/exp-v2-ventana-4-20261116a-analisis-contrafactual/RECTIFICACION-ANALISIS.md`):
  fee_bps 5.0 por lado + spread_bps 1.0 + slippage_bps 2.0 por lado
  => 16 bps de ida y vuelta sobre el valor de la posición. Funding UNKNOWN.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secuencia_presion_v1 import (  # noqa: E402
    CONFIG_HASH,
    CONFIG_VERSION,
    VentanaPresion,
    _evaluar_terna,
    detectar_secuencias,
    utc_iso,
)

VERSION_EVALUACION = "patron-ventana4-v1"
VENTANA_MS = 60_000
HORIZONTE_MS = 5 * 60_000
GRUPO_REPETICION_MS = 5 * 60_000
COSTE_IDA_VUELTA_BPS = 16.0
MIN_EPISODIOS = 30
SEMILLA_BOOTSTRAP = 42
RESAMPLES_BOOTSTRAP = 1000

MOTIVO_SIN_VELAS = "sin_velas_para_simbolo"
MOTIVO_ENTRADA_AUSENTE = "vela_entrada_ausente"
MOTIVO_SALIDA_AUSENTE = "vela_salida_ausente"
MOTIVO_CONTRADICTORIA = "vela_contradictoria"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _dia_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _hora_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%H")


def _media(valores: List[float]) -> Optional[float]:
    return sum(valores) / len(valores) if valores else None


def _mediana(valores: List[float]) -> Optional[float]:
    if not valores:
        return None
    orden = sorted(valores)
    n = len(orden)
    if n % 2:
        return orden[n // 2]
    return (orden[n // 2 - 1] + orden[n // 2]) / 2.0


def _redondear(valor: Optional[float]) -> Optional[float]:
    if valor is None or not math.isfinite(valor):
        return None
    return round(valor, 4)


def _ic_media_bootstrap(valores: List[float]) -> Optional[List[float]]:
    """IC95% de la media por bootstrap de episodios, semilla fija."""
    if len(valores) < 2:
        return None
    rnd = random.Random(SEMILLA_BOOTSTRAP)
    medias = []
    n = len(valores)
    for _ in range(RESAMPLES_BOOTSTRAP):
        muestra = [valores[rnd.randrange(n)] for _ in range(n)]
        medias.append(sum(muestra) / n)
    medias.sort()
    return [_redondear(medias[int(0.025 * RESAMPLES_BOOTSTRAP)]),
            _redondear(medias[int(0.975 * RESAMPLES_BOOTSTRAP) - 1])]


# ---------------------------------------------------------------------------
# Cobertura publicada
# ---------------------------------------------------------------------------

def cargar_cobertura(ruta: Path) -> Dict[str, Any]:
    with io.open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    pob = datos.get("poblacion_b_agregados_1m")
    if not pob:
        raise SystemExit("cobertura sin poblacion_b_agregados_1m: no se puede acreditar")
    return datos


# ---------------------------------------------------------------------------
# Conversión: filas de research.db -> VentanaPresion
# ---------------------------------------------------------------------------

def _fila(con: sqlite3.Connection, tabla: str, symbol: str, inicio: int) -> Dict[str, Any]:
    cur = con.execute(
        'select * from "%s" where symbol=? and bucket_start=?' % tabla, (symbol, inicio)
    )
    fila = cur.fetchone()
    if fila is None:
        raise SystemExit(f"falta {tabla} para {symbol}@{inicio}")
    return dict(fila)


def _verificar_igual(etiqueta: str, publicado: Any, db: Any) -> None:
    if isinstance(publicado, float) or isinstance(db, float):
        if publicado is None or db is None or abs(float(publicado) - float(db)) > 1e-9:
            raise SystemExit(
                f"discrepancia {etiqueta}: cobertura={publicado!r} db={db!r}"
            )
        return
    if publicado != db:
        raise SystemExit(f"discrepancia {etiqueta}: cobertura={publicado!r} db={db!r}")


def construir_ventanas(
    db_path: Path,
    cobertura: Dict[str, Any],
    run_id: str,
) -> Tuple[Dict[str, List[VentanaPresion]], Dict[str, Any]]:
    """Convierte las 1005 ventanas acreditadas en VentanaPresion.

    Exige que cada valor publicado coincida con la fila original. Si algo no
    coincide, aborta: no se fuerza la cifra.
    """
    pob = cobertura["poblacion_b_agregados_1m"]
    detalle = pob["ventanas_detalle"]
    if len(detalle) != pob["ventanas_acreditadas"]:
        raise SystemExit("ventanas_detalle no coincide con ventanas_acreditadas")

    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    por_symbol: Dict[str, List[VentanaPresion]] = defaultdict(list)
    auditoria = {
        "ventanas_convertidas": 0,
        "flujo_as_of_anterior_al_cierre": 0,
        "run_id_mismatch": 0,
        "procedencia": Counter(),
        "data_quality": Counter(),
        "observaciones": [],
    }
    for w in detalle:
        symbol = w["symbol"]
        inicio = int(w["ventana_inicio_ms"])
        fin = int(w["ventana_fin_ms"])
        if fin - inicio != VENTANA_MS:
            raise SystemExit(f"ventana no de 60s: {symbol}@{inicio}")
        f = _fila(con, "research_flow_1m", symbol, inicio)
        b = _fila(con, "research_book_1m", symbol, inicio)

        if f.get("run_id") != run_id or b.get("run_id") != run_id:
            auditoria["run_id_mismatch"] += 1
            raise SystemExit(f"run_id distinto en {symbol}@{inicio}")
        if f.get("price_source") != "aggTrade":
            raise SystemExit(f"procedencia de flujo distinta en {symbol}@{inicio}")
        if b.get("price_source") != "depth20":
            raise SystemExit(f"procedencia de libro distinta en {symbol}@{inicio}")

        _verificar_igual(f"{symbol}@{inicio} bucket_end", w["ventana_fin_ms"], f["bucket_end"])
        _verificar_igual(f"{symbol}@{inicio} book bucket_end", w["ventana_fin_ms"], b["bucket_end"])
        _verificar_igual(f"{symbol}@{inicio} buy", w["buy_notional"], f["buy_notional"])
        _verificar_igual(f"{symbol}@{inicio} sell", w["sell_notional"], f["sell_notional"])
        _verificar_igual(f"{symbol}@{inicio} bid20", w["bid_notional_top20"], b["bid20_mean"])
        _verificar_igual(f"{symbol}@{inicio} ask20", w["ask_notional_top20"], b["ask20_mean"])
        _verificar_igual(f"{symbol}@{inicio} precio", w["precio_cierre"], f["price_close"])
        _verificar_igual(
            f"{symbol}@{inicio} disponibilidad", w["disponibilidad_ms"], max(
                int(f["as_of_ms"]), int(b["as_of_ms"])
            )
        )

        disp = int(w["disponibilidad_ms"])
        if disp < fin:
            raise SystemExit(f"disponibilidad anterior al cierre en {symbol}@{inicio}")
        if int(f["as_of_ms"]) < fin:
            auditoria["flujo_as_of_anterior_al_cierre"] += 1

        integridad_ok = (
            int(b["degraded"]) == 0
            and int(b["depth_gaps"]) == 0
            and int(b["crossed"]) == 0
            and f["data_quality"] in ("OK",)
        )
        evento = max(int(f["last_event_ms"]), int(b["last_event_ms"]))
        ventana = VentanaPresion(
            symbol=symbol,
            observation_id=f"{symbol}|{inicio}",
            decision_ms=fin,
            decision_iso=utc_iso(fin),
            ventana_inicio_ms=inicio,
            ventana_fin_ms=fin,
            evento_ms=evento,
            evento_iso=utc_iso(evento),
            disponibilidad_ms=disp,
            disponibilidad_iso=utc_iso(disp),
            ventana_completa=True,
            ventana_ms=VENTANA_MS,
            buy_notional=float(f["buy_notional"]),
            sell_notional=float(f["sell_notional"]),
            bid_notional_top20=float(b["bid20_mean"]),
            ask_notional_top20=float(b["ask20_mean"]),
            precio_cierre=float(f["price_close"]),
            precio_fuente="aggTrade",
            precio_event_ms=int(f["last_event_ms"]),
            precio_event_iso=utc_iso(int(f["last_event_ms"])),
            integridad_valida=integridad_ok,
            fuente="research.db (research_flow_1m + research_book_1m) via C-cobertura-real.json",
            cobertura={
                "run_id": run_id,
                "flow_data_quality": f["data_quality"],
                "flow_as_of_ms": int(f["as_of_ms"]),
                "book_as_of_ms": int(b["as_of_ms"]),
                "price_source": "aggTrade",
                "depth_source": "depth20",
            },
        )
        por_symbol[symbol].append(ventana)
        auditoria["ventanas_convertidas"] += 1
        auditoria["procedencia"][f"{f['price_source']}/{b['price_source']}"] += 1
        auditoria["data_quality"][f["data_quality"]] += 1
        auditoria["observaciones"].append(
            {
                "window": ventana.observation_id,
                "valida_detector": ventana.esta_valida(),
                "motivos": _motivos_detector(ventana),
            }
        )

    con.close()
    for lista in por_symbol.values():
        lista.sort(key=lambda v: (v.ventana_inicio_ms, v.observation_id))
    auditoria["motivos_invalidez"] = Counter(
        m for o in auditoria["observaciones"] for m in o["motivos"]
    )
    auditoria["ventanas_validas_detector"] = sum(
        1 for o in auditoria["observaciones"] if o["valida_detector"]
    )
    auditoria.pop("observaciones")
    return dict(por_symbol), auditoria


def _motivos_detector(v: VentanaPresion) -> List[str]:
    motivos: List[str] = []
    if v.ventana_completa is not True:
        motivos.append("ventana_incompleta")
    if v.ventana_ms != VENTANA_MS:
        motivos.append("ventana_ms_distinta")
    if v.integridad_valida is not True:
        motivos.append("integridad_invalida")
    if v.disponibilidad_ms is None:
        motivos.append("sin_disponibilidad")
    if v.evento_ms is None:
        motivos.append("sin_evento")
    if v.bid_notional_top20 is None or not (v.bid_notional_top20 > 0):
        motivos.append("profundidad_bid_no_positiva")
    if v.ask_notional_top20 is None or not (v.ask_notional_top20 > 0):
        motivos.append("profundidad_ask_no_positiva")
    if v.precio_cierre is None or not (v.precio_cierre > 0):
        motivos.append("precio_no_positivo")
    return motivos


# ---------------------------------------------------------------------------
# Ternas y detector
# ---------------------------------------------------------------------------

def ternas_contiguas(ventanas: List[VentanaPresion]) -> List[Tuple[VentanaPresion, ...]]:
    ternas = []
    for i in range(len(ventanas) - 2):
        a, b, c = ventanas[i], ventanas[i + 1], ventanas[i + 2]
        if b.es_contigua_con(a) and c.es_contigua_con(b):
            ternas.append((a, b, c))
    return ternas


def verificar_universo(
    por_symbol: Dict[str, List[VentanaPresion]],
    cobertura: Dict[str, Any],
) -> Dict[str, Any]:
    pob = cobertura["poblacion_b_agregados_1m"]
    total_ventanas = sum(len(v) for v in por_symbol.values())
    ternas = {s: ternas_contiguas(v) for s, v in por_symbol.items()}
    total_ternas = sum(len(t) for t in ternas.values())
    simbolos = len(por_symbol)
    por_symbol_ternas = {s: len(t) for s, t in ternas.items() if t}

    esperado = {
        "ventanas": pob["ventanas_acreditadas"],
        "ternas": pob["ternas"]["ternas"],
        "simbolos": pob["ternas"]["simbolos_con_ternas"],
    }
    obtenido = {"ventanas": total_ventanas, "ternas": total_ternas, "simbolos": simbolos}
    if esperado != obtenido:
        raise SystemExit(
            f"el universo no se conserva hasta la entrada del detector: "
            f"esperado={esperado} obtenido={obtenido}"
        )
    if por_symbol_ternas != pob["ternas"]["ternas_por_simbolo"]:
        raise SystemExit("ternas por símbolo distintas de las publicadas")
    return {
        "esperado": esperado,
        "obtenido": obtenido,
        "conservado": True,
        "ternas_por_simbolo": por_symbol_ternas,
    }


def evaluar_detector(
    por_symbol: Dict[str, List[VentanaPresion]],
) -> Dict[str, Dict[str, Any]]:
    decisiones: Dict[str, Dict[str, Any]] = {}
    for symbol, ventanas in por_symbol.items():
        for r in detectar_secuencias(ventanas, symbol):
            clave = f"{r.symbol}|{r.observation_id}" if "|" not in r.observation_id else r.observation_id
            if clave in decisiones:
                raise SystemExit(f"decisión duplicada para {clave}")
            decisiones[clave] = {
                "symbol": r.symbol,
                "observation_id": r.observation_id,
                "decision": r.decision,
                "direccion": r.direccion_candidata,
                "motivo": r.motivo,
                "motivo_codigo": r.motivo_codigo,
                "condiciones_faltantes": r.condiciones_faltantes,
                "instante_deteccion_ms": r.instante_deteccion_ms,
                "instante_deteccion_iso": r.instante_deteccion_iso,
                "ventanas": [w.get("observation_id") for w in r.ventanas],
            }
    return decisiones


# ---------------------------------------------------------------------------
# Velas de 1 minuto
# ---------------------------------------------------------------------------

def cargar_velas(ruta: Path, run_id: str) -> Tuple[Dict[str, Dict[int, Dict[str, Any]]], Dict[str, Any]]:
    """Carga velas de 1 minuto desde las consultas persistidas.

    Una misma vela aparece en varias consultas. Solo se considera definitiva
    cuando la consulta se adquirió después de su cierre; una instantánea tomada
    con la vela aún abierta es provisional (su apertura es válida e inmutable,
    su máximo/mínimo puede estar incompleto). Dos instantáneas definitivas que
    discrepan son una incoherencia real: la vela se marca contradictoria y no
    se usa.
    """
    velas: Dict[str, Dict[int, Dict[str, Any]]] = defaultdict(dict)
    audit = {
        "consultas": 0,
        "consultas_rechazadas": [],
        "simbolos": set(),
        "filas_leidas": 0,
        "velas_unicas": 0,
        "duplicadas_identicas": 0,
        "duplicadas_contradictorias": 0,
        "provisional_reemplazada_por_final": 0,
        "provisional_actualizada": 0,
        "provisional_ignorada": 0,
        "velas_provisionales_finales": 0,
        "velas_contradictorias": 0,
        "ejemplos_contradiccion": [],
        "run_id_distinto": 0,
    }
    with io.open(ruta, encoding="utf-8") as f:
        for linea in f:
            d = json.loads(linea)
            if d.get("kind") != "consulta_klines_trayectoria":
                continue
            audit["consultas"] += 1
            if d.get("run_id") != run_id:
                audit["run_id_distinto"] += 1
                continue
            if d.get("interval") != "1m" or d.get("http_status") != 200:
                audit["consultas_rechazadas"].append(
                    {"consulta": d.get("consulta_numero"), "motivo": "intervalo_o_http"}
                )
                continue
            symbol = d["symbol"]
            adquirido = int(d.get("adquirido_ms") or 0)
            try:
                cuerpo = json.loads(d["cuerpo"])
            except Exception as exc:  # noqa: BLE001
                audit["consultas_rechazadas"].append(
                    {"consulta": d.get("consulta_numero"), "motivo": f"cuerpo_ilegible: {exc}"}
                )
                continue
            if len(cuerpo) != d.get("filas"):
                audit["consultas_rechazadas"].append(
                    {"consulta": d.get("consulta_numero"), "motivo": "filas_no_coinciden"}
                )
                continue
            audit["simbolos"].add(symbol)
            for fila in cuerpo:
                if len(fila) < 7:
                    continue
                ot = int(fila[0])
                if ot % VENTANA_MS != 0:
                    audit["consultas_rechazadas"].append(
                        {"consulta": d.get("consulta_numero"), "motivo": f"open_time_no_alineado:{ot}"}
                    )
                    continue
                close_time = int(fila[6])
                if close_time != ot + VENTANA_MS - 1:
                    audit["consultas_rechazadas"].append(
                        {"consulta": d.get("consulta_numero"), "motivo": f"close_time_incoherente:{ot}"}
                    )
                    continue
                vela = {
                    "open": float(fila[1]),
                    "high": float(fila[2]),
                    "low": float(fila[3]),
                    "close": float(fila[4]),
                    "close_time": close_time,
                    "final": adquirido > close_time,
                    "adquirido_ms": adquirido,
                    "conflictiva": False,
                }
                audit["filas_leidas"] += 1
                previa = velas[symbol].get(ot)
                if previa is None:
                    velas[symbol][ot] = vela
                    continue
                if previa["open"] != vela["open"]:
                    audit["duplicadas_contradictorias"] += 1
                    audit["velas_contradictorias"] += 1
                    if len(audit["ejemplos_contradiccion"]) < 5:
                        audit["ejemplos_contradiccion"].append(
                            {"symbol": symbol, "open_time": ot,
                             "previa": {k: previa[k] for k in ("open", "high", "low", "close")},
                             "nueva": {k: vela[k] for k in ("open", "high", "low", "close")}}
                        )
                    previa["conflictiva"] = True
                    continue
                if previa["final"] and vela["final"]:
                    iguales = all(
                        abs(previa[k] - vela[k]) < 1e-12
                        for k in ("open", "high", "low", "close")
                    )
                    if iguales:
                        audit["duplicadas_identicas"] += 1
                    else:
                        audit["duplicadas_contradictorias"] += 1
                        audit["velas_contradictorias"] += 1
                        if len(audit["ejemplos_contradiccion"]) < 5:
                            audit["ejemplos_contradiccion"].append(
                                {"symbol": symbol, "open_time": ot,
                                 "previa": {k: previa[k] for k in ("open", "high", "low", "close")},
                                 "nueva": {k: vela[k] for k in ("open", "high", "low", "close")}}
                            )
                        previa["conflictiva"] = True
                    continue
                if vela["final"] and not previa["final"]:
                    audit["provisional_reemplazada_por_final"] += 1
                    velas[symbol][ot] = vela
                    continue
                if previa["final"] and not vela["final"]:
                    audit["provisional_ignorada"] += 1
                    continue
                # Ambas provisionales: se conserva la instantánea más reciente.
                audit["provisional_actualizada"] += 1
                if vela["adquirido_ms"] >= previa["adquirido_ms"]:
                    velas[symbol][ot] = vela
    audit["velas_unicas"] = sum(len(v) for v in velas.values())
    audit["velas_provisionales_finales"] = sum(
        1 for serie in velas.values() for v in serie.values() if not v["final"]
    )
    audit["simbolos"] = sorted(audit["simbolos"])
    return dict(velas), audit


# ---------------------------------------------------------------------------
# Alerta -> resultado
# ---------------------------------------------------------------------------

def _referencia_entrada(cut_ms: int) -> int:
    return (int(cut_ms) // VENTANA_MS + 1) * VENTANA_MS


def resolver_alerta(
    alerta: Dict[str, Any],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
) -> Dict[str, Any]:
    symbol = alerta["symbol"]
    direccion = alerta["direccion"]
    cut = int(alerta["cut_ms"])
    entrada_ms = _referencia_entrada(cut)
    base = {
        "entrada_ms": entrada_ms,
        "salida_ms": entrada_ms + HORIZONTE_MS,
        "demora_total_ms": entrada_ms - cut,
    }
    serie = velas.get(symbol)
    if not serie:
        return {**base, "estado": "no_resoluble", "motivo": MOTIVO_SIN_VELAS}
    v_entrada = serie.get(entrada_ms)
    if v_entrada is None:
        return {**base, "estado": "no_resoluble", "motivo": MOTIVO_ENTRADA_AUSENTE}
    if v_entrada["conflictiva"]:
        return {**base, "estado": "no_resoluble", "motivo": MOTIVO_CONTRADICTORIA}
    v_salida = serie.get(entrada_ms + HORIZONTE_MS)
    if v_salida is None:
        return {**base, "estado": "no_resoluble", "motivo": MOTIVO_SALIDA_AUSENTE,
                "precio_entrada": v_entrada["open"]}
    if v_salida["conflictiva"]:
        return {**base, "estado": "no_resoluble", "motivo": MOTIVO_CONTRADICTORIA,
                "precio_entrada": v_entrada["open"]}
    entrada = v_entrada["open"]
    salida = v_salida["open"]
    if not (entrada > 0 and salida > 0):
        return {**base, "estado": "no_resoluble", "motivo": "precio_no_positivo"}
    signo = 1.0 if direccion == "LONG" else -1.0
    retorno = signo * (salida / entrada - 1.0) * 1e4

    # La trayectoria solo se considera completa si las 5 velas están cerradas
    # (no provisionales) y no son contradictorias. La apertura de una vela
    # provisional es válida; su máximo/mínimo puede estar incompleto.
    trayectoria = [serie.get(entrada_ms + i * VENTANA_MS) for i in range(5)]
    completa = all(
        c is not None and not c["conflictiva"] and c["final"] for c in trayectoria
    )
    adverso = None
    favorable = None
    if completa:
        if direccion == "LONG":
            adverso = min((c["low"] / entrada - 1.0) * 1e4 for c in trayectoria)
            favorable = max((c["high"] / entrada - 1.0) * 1e4 for c in trayectoria)
        else:
            adverso = min(-(c["high"] / entrada - 1.0) * 1e4 for c in trayectoria)
            favorable = max(-(c["low"] / entrada - 1.0) * 1e4 for c in trayectoria)
    return {
        **base,
        "estado": "resoluble",
        "precio_entrada": entrada,
        "precio_salida": salida,
        "retorno_bps": retorno,
        "adverso_bps": adverso,
        "favorable_bps": favorable,
        "trayectoria_completa": completa,
        "entrada_provisional": not v_entrada["final"],
        "salida_provisional": not v_salida["final"],
    }


def agrupar_episodios(
    alertas: List[Dict[str, Any]],
    grupo_ms: int = GRUPO_REPETICION_MS,
) -> List[Dict[str, Any]]:
    """Primera alerta por (contrato, dirección); repetidas dentro de 5 min."""
    por_clave: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for a in alertas:
        por_clave[(a["symbol"], a["direccion"])].append(a)
    episodios: List[Dict[str, Any]] = []
    for (symbol, direccion), lista in por_clave.items():
        lista.sort(key=lambda a: (a["cut_ms"], a["terna"]))
        actual: Optional[Dict[str, Any]] = None
        for a in lista:
            if actual is None or a["cut_ms"] >= actual["cut_ms"] + grupo_ms:
                actual = {
                    "symbol": symbol,
                    "direccion": direccion,
                    "cut_ms": a["cut_ms"],
                    "cut_iso": a["cut_iso"],
                    "cierre_nominal_ms": a["cierre_nominal_ms"],
                    "demora_corte_ms": a["demora_corte_ms"],
                    "terna": a["terna"],
                    "tambien_patron": a.get("tambien_patron"),
                    "decision": a.get("decision"),
                    "repetidas": [],
                }
                episodios.append(actual)
            else:
                actual["repetidas"].append(a["terna"])
    episodios.sort(key=lambda e: (e["cut_ms"], e["symbol"], e["direccion"]))
    return episodios


# ---------------------------------------------------------------------------
# Construcción de alertas
# ---------------------------------------------------------------------------

def alertas_patron(
    por_symbol: Dict[str, List[VentanaPresion]],
    decisiones: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    alertas: List[Dict[str, Any]] = []
    por_decision = Counter()
    ternas_detalle: List[Dict[str, Any]] = []
    sin_decision = 0
    funnel = {
        d: {"ternas": 0, "precio_avanza": 0, "q_positivo_creciente": 0,
            "profundidad_decreciente": 0, "precio_y_q": 0,
            "precio_y_q_y_profundidad": 0, "cumple": 0, "faltantes": Counter()}
        for d in ("LONG", "SHORT")
    }
    for symbol, ventanas in por_symbol.items():
        for a, b, c in ternas_contiguas(ventanas):
            for direccion in ("LONG", "SHORT"):
                evaluacion = _evaluar_terna(a, b, c, direccion)
                f = funnel[direccion]
                cumplidas = set(evaluacion["condiciones_cumplidas"])
                precio_ok = "precio_avanza_en_direccion" in cumplidas
                q_ok = "q_positivo_creciente" in cumplidas
                d_ok = "profundidad_contraria_decreciente" in cumplidas
                f["ternas"] += 1
                f["precio_avanza"] += int(precio_ok)
                f["q_positivo_creciente"] += int(q_ok)
                f["profundidad_decreciente"] += int(d_ok)
                f["precio_y_q"] += int(precio_ok and q_ok)
                f["precio_y_q_y_profundidad"] += int(precio_ok and q_ok and d_ok)
                f["cumple"] += int(evaluacion["cumple"])
                for motivo in evaluacion["condiciones_faltantes"]:
                    f["faltantes"][motivo] += 1
            clave = c.observation_id
            d = decisiones.get(clave)
            corte = max(int(c.ventana_fin_ms), int(c.disponibilidad_ms or 0),
                        int(b.disponibilidad_ms or 0), int(a.disponibilidad_ms or 0))
            fila = {
                "ternas": 1,
                "terna": f"{symbol}|{c.ventana_inicio_ms}",
                "symbol": symbol,
                "ventanas": [a.ventana_inicio_ms, b.ventana_inicio_ms, c.ventana_inicio_ms],
                "cierre_nominal_ms": c.ventana_fin_ms,
                "cut_ms": corte,
                "cut_iso": utc_iso(corte),
                "demora_corte_ms": corte - c.ventana_fin_ms,
                "decision": d["decision"] if d else "DATOS_INSUFICIENTES",
                "direccion": d["direccion"] if d else None,
                "motivo": (d["motivo"] if d else
                           "terna acreditada por el extractor sin decisión del detector"),
                "motivo_codigo": d.get("motivo_codigo") if d else "sin_decision",
                "instante_deteccion_ms": d.get("instante_deteccion_ms") if d else None,
            }
            por_decision[fila["decision"]] += 1
            ternas_detalle.append(fila)
            if d is None:
                sin_decision += 1
                continue
            if fila["decision"] in ("LONG_EXPERIMENTAL", "SHORT_EXPERIMENTAL"):
                alertas.append({
                    "symbol": symbol,
                    "direccion": fila["direccion"],
                    "terna": fila["terna"],
                    "cut_ms": corte,
                    "cut_iso": utc_iso(corte),
                    "cierre_nominal_ms": c.ventana_fin_ms,
                    "demora_corte_ms": corte - c.ventana_fin_ms,
                    "decision": fila["decision"],
                    "origen": "patron",
                    "tambien_patron": True,
                })
    alertas.sort(key=lambda a: (a["cut_ms"], a["symbol"], a["direccion"]))
    resumen = {
        "ternas": len(ternas_detalle),
        "por_decision": dict(por_decision),
        "sin_decision": sin_decision,
        "alertas_brutas": len(alertas),
        "funnel_por_direccion": {
            d: {**{k: v for k, v in f.items() if k != "faltantes"},
                "faltantes": dict(f["faltantes"])}
            for d, f in funnel.items()
        },
        "ternas_detalle": ternas_detalle,
    }
    return alertas, resumen


def alertas_solo_precio(
    db_path: Path,
    run_id: str,
    ternas_patron: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Ternas de 3 cierres estrictamente monótonos, sin condiciones de flujo
    ni profundidad. Mismo corte causal basado en la disponibilidad del precio.
    """
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    filas: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for symbol, inicio, fin, cierre, as_of in con.execute(
        "select symbol, bucket_start, bucket_end, price_close, as_of_ms "
        "from research_flow_1m"
    ):
        filas[symbol].append(
            {"symbol": symbol, "inicio": int(inicio), "fin": int(fin),
             "cierre": float(cierre), "as_of": int(as_of)}
        )
    con.close()
    alertas: List[Dict[str, Any]] = []
    ternas = 0
    por_simbolo_ventanas = Counter()
    for symbol, lista in filas.items():
        lista.sort(key=lambda f: f["inicio"])
        por_simbolo_ventanas[symbol] = len(lista)
        for i in range(len(lista) - 2):
            a, b, c = lista[i], lista[i + 1], lista[i + 2]
            if not (a["fin"] == b["inicio"] and b["fin"] == c["inicio"]):
                continue
            ternas += 1
            direccion = None
            if a["cierre"] < b["cierre"] < c["cierre"]:
                direccion = "LONG"
            elif a["cierre"] > b["cierre"] > c["cierre"]:
                direccion = "SHORT"
            if direccion is None:
                continue
            cut = max(c["fin"], a["as_of"], b["as_of"], c["as_of"])
            terna = f"{symbol}|{c['inicio']}"
            patron = ternas_patron.get(terna)
            alertas.append({
                "symbol": symbol,
                "direccion": direccion,
                "terna": terna,
                "cut_ms": cut,
                "cut_iso": utc_iso(cut),
                "cierre_nominal_ms": c["fin"],
                "demora_corte_ms": cut - c["fin"],
                "decision": None,
                "origen": "solo_precio",
                "tambien_patron": bool(patron and patron["direccion"] == direccion),
            })
    alertas.sort(key=lambda a: (a["cut_ms"], a["symbol"], a["direccion"]))
    resumen = {
        "ternas_solo_precio": ternas,
        "alertas_brutas": len(alertas),
        "alertas_por_direccion": dict(Counter(a["direccion"] for a in alertas)),
        "alertas_tambien_patron": sum(1 for a in alertas if a["tambien_patron"]),
        "ventanas_por_simbolo": dict(por_simbolo_ventanas),
    }
    return alertas, resumen


# ---------------------------------------------------------------------------
# Resumen de resultados
# ---------------------------------------------------------------------------

def resumir_episodios(
    episodios: List[Dict[str, Any]],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
) -> Dict[str, Any]:
    resultados = []
    motivos = Counter()
    for e in episodios:
        r = resolver_alerta(e, velas)
        motivo = r.get("motivo")
        if motivo:
            motivos[motivo] += 1
        resultados.append({**e, **r})
    resolubles = [r for r in resultados if r["estado"] == "resoluble"]
    retornos = [r["retorno_bps"] for r in resolubles]
    adversos = [r["adverso_bps"] for r in resolubles if r.get("adverso_bps") is not None]
    aciertos = sum(1 for x in retornos if x > 0)
    fallos = sum(1 for x in retornos if x < 0)
    neutrales = sum(1 for x in retornos if x == 0)
    conteo_simbolo = Counter(r["symbol"] for r in resolubles)
    total = len(resolubles)
    dominante = conteo_simbolo.most_common(1)[0] if conteo_simbolo else (None, 0)
    horas = defaultdict(list)
    for r in resolubles:
        horas[_hora_utc(r["cut_ms"])].append(r["retorno_bps"])
    return {
        "episodios": len(resultados),
        "resolubles": total,
        "no_resolubles": len(resultados) - total,
        "motivos_no_resoluble": dict(motivos),
        "aciertos": aciertos,
        "fallos": fallos,
        "neutrales": neutrales,
        "tasa_acierto": _redondear(aciertos / total) if total else None,
        "retorno_medio_bps": _redondear(_media(retornos)),
        "retorno_mediano_bps": _redondear(_mediana(retornos)),
        "ic95_media_bps": _ic_media_bootstrap([float(x) for x in retornos]),
        "adverso_medio_bps": _redondear(_media(adversos)),
        "adverso_mediano_bps": _redondear(_mediana(adversos)),
        "adverso_sobre": len(adversos),
        "resolubles_con_trayectoria_completa": sum(
            1 for r in resolubles if r.get("trayectoria_completa")),
        "resolubles_con_entrada_provisional": sum(
            1 for r in resolubles if r.get("entrada_provisional")),
        "resolubles_con_salida_provisional": sum(
            1 for r in resolubles if r.get("salida_provisional")),
        "simbolo_dominante": {
            "symbol": dominante[0],
            "episodios": dominante[1],
            "cuota": _redondear(dominante[1] / total) if total else None,
        },
        "simbolos": dict(conteo_simbolo.most_common()),
        "por_hora_utc": {
            h: {"episodios": len(v), "retorno_medio_bps": _redondear(_media(v))}
            for h, v in sorted(horas.items())
        },
        "detalle": resultados,
    }


def _media_sin_simbolo(episodios: List[Dict[str, Any]], symbol: str) -> Optional[float]:
    valores = [e["retorno_bps"] for e in episodios
               if e["estado"] == "resoluble" and e["symbol"] != symbol]
    return _media(valores)


def concluir(
    patron: Dict[str, Any],
    referencia: Dict[str, Any],
    solo_precio_sin_patron: Dict[str, Any],
    detalle_patron: List[Dict[str, Any]],
) -> Dict[str, Any]:
    n_patron = patron["resolubles"]
    n_ref = referencia["resolubles"]
    n_sin = solo_precio_sin_patron["resolubles"]
    evidencia: List[str] = []
    if n_patron < MIN_EPISODIOS or n_sin < MIN_EPISODIOS:
        return {
            "conclusion": "datos insuficientes",
            "motivo": (
                f"episodios resolubles: patrón={n_patron}, referencia={n_ref}, "
                f"solo precio sin patrón={n_sin}; mínimo fijado={MIN_EPISODIOS}"
            ),
            "evidencia": [],
        }
    media_p = patron["retorno_medio_bps"]
    media_r = referencia["retorno_medio_bps"]
    mediana_p = patron["retorno_mediano_bps"]
    mediana_r = referencia["retorno_mediano_bps"]
    dominante = patron["simbolo_dominante"]["symbol"]
    media_robusta = _media_sin_simbolo(detalle_patron, dominante) if dominante else None
    evidencia.append(f"media patrón {media_p} bps vs referencia {media_r} bps")
    evidencia.append(f"mediana patrón {mediana_p} bps vs referencia {mediana_r} bps")
    mejora = (media_p is not None and media_r is not None and media_p > media_r
              and mediana_p is not None and mediana_r is not None and mediana_p > mediana_r)
    robusta = True
    if media_robusta is not None and media_r is not None:
        robusta = media_robusta > media_r
        evidencia.append(
            f"media patrón sin el símbolo dominante ({dominante}): "
            f"{_redondear(media_robusta)} bps vs referencia {media_r} bps"
        )
    if mejora and robusta:
        return {
            "conclusion": "merece una prueba independiente",
            "motivo": "la media y la mediana del patrón superan a la referencia de "
                      "solo precio y la ventaja no depende del símbolo dominante",
            "evidencia": evidencia,
        }
    if media_p is not None and media_r is not None and media_p > media_r and not robusta:
        return {
            "conclusion": "datos insuficientes",
            "motivo": "la ventaja de la media desaparece al excluir el símbolo dominante",
            "evidencia": evidencia,
        }
    return {
        "conclusion": "no muestra mejora en esta muestra",
        "motivo": "el patrón no supera a la referencia de solo precio en media y mediana",
        "evidencia": evidencia,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resumen_grupo(
    etiqueta: str,
    episodios: List[Dict[str, Any]],
    velas: Dict[str, Dict[int, Dict[str, Any]]],
    ternas: Optional[int] = None,
) -> Dict[str, Any]:
    por_direccion = {}
    for direccion in ("LONG", "SHORT"):
        sub = [e for e in episodios if e["direccion"] == direccion]
        r = resumir_episodios(sub, velas)
        r.pop("detalle")
        por_direccion[direccion] = r
    global_ = resumir_episodios(episodios, velas)
    detalle = global_.pop("detalle")
    alertas_por_direccion = {
        direccion: sum(1 + len(e["repetidas"]) for e in episodios
                       if e["direccion"] == direccion)
        for direccion in ("LONG", "SHORT")
    }
    neto = [
        e["retorno_bps"] - COSTE_IDA_VUELTA_BPS
        for e in detalle if e["estado"] == "resoluble"
    ]
    return {
        "grupo": etiqueta,
        "ternas_evaluadas": ternas,
        "alertas_brutas": sum(alertas_por_direccion.values()),
        "alertas_por_direccion": alertas_por_direccion,
        "global": global_,
        "por_direccion": por_direccion,
        "sensibilidad_coste_documentado": {
            "coste_ida_vuelta_bps": COSTE_IDA_VUELTA_BPS,
            "supuestos": "fee_bps 5.0 por lado + spread_bps 1.0 + slippage_bps 2.0 por lado; funding UNKNOWN",
            "neto_medio_bps": _redondear(_media(neto)),
            "neto_mediano_bps": _redondear(_mediana(neto)),
        },
        "detalle": detalle,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--cobertura", required=True)
    ap.add_argument("--klines", required=True)
    ap.add_argument("--salida", required=True, help="directorio para derivados voluminosos")
    ap.add_argument("--resumen", required=True, help="JSON compacto (apto para Git)")
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

    hashes = {
        "research.db": _sha256_archivo(db),
        "cobertura_json": _sha256_archivo(cobertura_ruta),
        "consultas_klines.jsonl": _sha256_archivo(klines_ruta),
    }

    cobertura = cargar_cobertura(cobertura_ruta)
    pob = cobertura["poblacion_b_agregados_1m"]
    db_declarada = str(cobertura.get("origen", {}).get("db_sha256", "")).lower()
    if db_declarada and db_declarada != hashes["research.db"].lower():
        raise SystemExit(
            f"research.db no coincide con el hash declarado en la cobertura: "
            f"{hashes['research.db']} != {db_declarada}"
        )

    por_symbol, audit_ventanas = construir_ventanas(db, cobertura, args.run_id)
    universo = verificar_universo(por_symbol, cobertura)

    decisiones = evaluar_detector(por_symbol)
    alertas_p, resumen_p = alertas_patron(por_symbol, decisiones)
    ternas_patron = {
        t["terna"]: t for t in resumen_p["ternas_detalle"]
        if t["decision"] in ("LONG_EXPERIMENTAL", "SHORT_EXPERIMENTAL")
    }
    alertas_r, resumen_r = alertas_solo_precio(db, args.run_id, ternas_patron)

    velas, audit_velas = cargar_velas(klines_ruta, args.run_id)

    episodios_p = agrupar_episodios(alertas_p)
    episodios_r = agrupar_episodios(alertas_r)
    episodios_r_mas = [e for e in episodios_r if e["tambien_patron"]]
    episodios_r_menos = [e for e in episodios_r if not e["tambien_patron"]]

    grupos = {
        "patron": _resumen_grupo("patron", episodios_p, velas, resumen_p["ternas"]),
        "referencia_solo_precio": _resumen_grupo(
            "referencia_solo_precio", episodios_r, velas, resumen_r["ternas_solo_precio"]),
        "referencia_tambien_patron": _resumen_grupo(
            "referencia_tambien_patron", episodios_r_mas, velas),
        "referencia_solo_precio_sin_patron": _resumen_grupo(
            "referencia_solo_precio_sin_patron", episodios_r_menos, velas),
    }

    conclusion = concluir(
        grupos["patron"]["global"],
        grupos["referencia_solo_precio"]["global"],
        grupos["referencia_solo_precio_sin_patron"]["global"],
        grupos["patron"]["detalle"],
    )

    simbolos_con_velas = set(velas.keys())
    ternas_patron_por_simbolo = Counter(t["symbol"] for t in resumen_p["ternas_detalle"])
    ternas_sin_velas = {
        s: n for s, n in ternas_patron_por_simbolo.items()
        if s not in simbolos_con_velas
    }
    # Episodios sin velas: solo cuando el símbolo no aparece en ninguna consulta.
    episodios_sin_velas = [
        e for e in grupos["patron"]["detalle"]
        if e["estado"] == "no_resoluble" and e["motivo"] == MOTIVO_SIN_VELAS
    ]

    resumen = {
        "version_evaluacion": VERSION_EVALUACION,
        "run_id": args.run_id,
        "origen": {
            "db": str(db),
            "cobertura": str(cobertura_ruta),
            "klines": str(klines_ruta),
            "hashes_sha256": hashes,
            "db_sha256_declarada_en_cobertura": db_declarada or None,
        },
        "configuracion_detector": {
            "version": CONFIG_VERSION,
            "hash": CONFIG_HASH,
            "condiciones_congeladas": True,
        },
        "universo": {
            "publicado": universo["esperado"],
            "hasta_entrada_detector": universo["obtenido"],
            "conservado": universo["conservado"],
            "ventanas_validas_para_el_detector": audit_ventanas["ventanas_validas_detector"],
            "motivos_invalidez": dict(audit_ventanas["motivos_invalidez"]),
            "flujo_as_of_anterior_al_cierre": audit_ventanas["flujo_as_of_anterior_al_cierre"],
            "procedencia": dict(audit_ventanas["procedencia"]),
            "data_quality_flujo": dict(audit_ventanas["data_quality"]),
        },
        "cadena_publicada": {
            "parejas_iniciales": pob["parejas_iniciales"],
            "ternas_sobre_parejas": pob["cadena"][0]["ternas_tras_requisito"],
            "ternas_tras_integridad": next(
                c["ternas_tras_requisito"] for c in pob["cadena"]
                if c["etapa"] == "integridad_por_intervalo"),
            "ternas_finales": pob["ternas"]["ternas"],
        },
        "detector": {
            "ternas_evaluadas": resumen_p["ternas"],
            "por_decision": resumen_p["por_decision"],
            "funnel_por_direccion": resumen_p["funnel_por_direccion"],
            "alertas_brutas": resumen_p["alertas_brutas"],
            "alertas_por_direccion": dict(Counter(a["direccion"] for a in alertas_p)),
            "episodios": len(episodios_p),
            "episodios_por_direccion": dict(Counter(e["direccion"] for e in episodios_p)),
            "repetidas_agrupadas": sum(len(e["repetidas"]) for e in episodios_p),
            "demora_corte_ms": {
                "min": min((t["demora_corte_ms"] for t in resumen_p["ternas_detalle"]), default=None),
                "max": max((t["demora_corte_ms"] for t in resumen_p["ternas_detalle"]), default=None),
                "mediana": _mediana([t["demora_corte_ms"] for t in resumen_p["ternas_detalle"]]),
            },
        },
        "referencia": {
            **resumen_r,
            "episodios": len(episodios_r),
            "episodios_por_direccion": dict(Counter(e["direccion"] for e in episodios_r)),
            "episodios_tambien_patron": len(episodios_r_mas),
            "episodios_solo_precio_sin_patron": len(episodios_r_menos),
            "repetidas_agrupadas": sum(len(e["repetidas"]) for e in episodios_r),
        },
        "grupos": {k: {kk: vv for kk, vv in v.items() if kk != "detalle"}
                   for k, v in grupos.items()},
        "conclusion": conclusion,
        "cobertura_de_velas": {
            **{k: v for k, v in audit_velas.items() if k != "simbolos"},
            "simbolos": sorted(velas.keys()),
            "simbolos_con_ternas_sin_velas": ternas_sin_velas,
            "episodios_patron_sin_velas": len(episodios_sin_velas),
        },
        "limitaciones": [
            "captura ya usada en el desarrollo del detector: hallazgo exploratorio, no prueba independiente",
            "corte reconstruido: la captura no ejecutó el detector en vivo",
            "entrada = apertura de la vela siguiente al corte; no es un fill ejecutado ni incluye latencia",
            "salida = apertura a 5 minutos; no hay stop ni salida intravela",
            "funding UNKNOWN; costes aplicados solo como sensibilidad documentada",
            "episodios de distintos símbolos pueden solaparse en el tiempo: no son independientes",
            "cobertura de velas limitada a los símbolos consultados durante la captura",
        ],
    }

    # Derivados voluminosos fuera de Git.
    def _jsonl(nombre: str, filas: Iterable[Dict[str, Any]]) -> str:
        ruta = salida / nombre
        with io.open(ruta, "w", encoding="utf-8", newline="\n") as f:
            for fila in filas:
                f.write(json.dumps(fila, ensure_ascii=False, sort_keys=True) + "\n")
        return _sha256_archivo(ruta)

    derivados = {
        "ternas_patron.jsonl": _jsonl("ternas_patron.jsonl", resumen_p["ternas_detalle"]),
        "alertas_patron.jsonl": _jsonl("alertas_patron.jsonl", alertas_p),
        "alertas_referencia.jsonl": _jsonl("alertas_referencia.jsonl", alertas_r),
        "episodios_patron.jsonl": _jsonl("episodios_patron.jsonl", grupos["patron"]["detalle"]),
        "episodios_referencia.jsonl": _jsonl(
            "episodios_referencia.jsonl", grupos["referencia_solo_precio"]["detalle"]),
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
        "universo": universo["obtenido"],
        "alertas_patron": resumen_p["alertas_brutas"],
        "episodios_patron": len(episodios_p),
        "alertas_referencia": resumen_r["alertas_brutas"],
        "episodios_referencia": len(episodios_r),
        "conclusion": conclusion["conclusion"],
        "resumen": str(resumen_ruta),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
