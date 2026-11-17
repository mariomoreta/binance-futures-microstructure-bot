# -*- coding: utf-8 -*-
"""Detector experimental SECUENCIA-PRESION-V1 (local, sin mercado).

Reconoce una secuencia temporal de presión agresora creciente, reducción de
liquidez contraria y avance del precio, sobre tres ventanas consecutivas y
completas de un minuto.

Estado: EXPERIMENTAL, sin validación económica. No conecta al camino
productivo ni recibe autorización para operar. La regla operativa actual
permanece congelada como referencia.

Definición mecánica (fijada antes de cualquier evaluación económica):

Para cada ventana k (1 minuto completa):
  F_k = compras_agresoras_k - ventas_agresoras_k   (USDT)
  D_k = profundidad contraria                      (USDT)
        LONG  -> ask_notional_top20
        SHORT -> bid_notional_top20
  Q_k = s * F_k / D_k, con s = +1 (LONG) / -1 (SHORT)

Primera definición mecánica:
  - 0 < Q_1 < Q_2 < Q_3
  - D_1 > D_2 > D_3 > 0
  - los cierres conocidos de las tres ventanas avanzan en la dirección
    candidata (LONG: cierre creciente; SHORT: cierre decreciente)

Salidas: LONG_EXPERIMENTAL | SHORT_EXPERIMENTAL | SIN_PATRON | DATOS_INSUFICIENTES.

Cada salida incluye: condiciones cumplidas/faltantes, las tres ventanas
usadas, F_k, D_k, Q_k, precios, timestamps, procedencia, versión y hash de
configuración, motivo explícito.

Ausentes, no finitos, importes inválidos, profundidad no positiva, ventanas
incompletas o huecos impiden acreditar el patrón. Nunca UNKNOWN -> cero.
No se mezclan "no se cumple el patrón" con "no podemos evaluarlo".
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuración congelada (sin defaults en el camino productivo)
# ---------------------------------------------------------------------------

CONFIG_VERSION = "SECUENCIA-PRESION-V1"

CONFIG: Dict[str, Any] = {
    "version": CONFIG_VERSION,
    "ventana_ms": 60_000,              # 1 minuto
    "num_ventanas": 3,                 # tres ventanas consecutivas
    "profundidad_niveles": 20,         # top-20
    "profundidad_lado_contrario": True,  # LONG->ask, SHORT->bid
    "requiere_ventana_completa": True,
    "requiere_integridad_valida": True,
    "requiere_desfase_valido": True,
    "condiciones": {
        "q_positivo_creciente": True,
        "profundidad_contraria_decreciente": True,
        "precio_avanza_en_direccion": True,
    },
    "flujo_fuente": "aggTrade",
    "profundidad_fuente": "depth20@100ms",
}

CONFIG_HASH = hashlib.sha256(
    json.dumps(CONFIG, sort_keys=True).encode("utf-8")
).hexdigest()


def utc_iso(ms: Optional[int]) -> Optional[str]:
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Ventana de un minuto
# ---------------------------------------------------------------------------

@dataclass
class VentanaPresion:
    """Una ventana de 1 minuto con flujo agresor y profundidad contraria.

    Los datos provienen exclusivamente de los cuerpos persistidos
    (observaciones.jsonl). No se reconstruyen ni se infieren valores.
    """

    symbol: str
    observation_id: str
    decision_ms: int
    decision_iso: Optional[str]
    ventana_inicio_ms: Optional[int]   # inicio de la ventana de 1 min
    ventana_fin_ms: Optional[int]      # fin de la ventana (decision_ms o max_ms)
    evento_ms: Optional[int]           # instante del evento (event_ms del flujo/libro)
    evento_iso: Optional[str]
    disponibilidad_ms: Optional[int]   # instante en que toda la evidencia
                                       # necesaria estaba disponible (max de
                                       # disponibilidad por fuente)
    disponibilidad_iso: Optional[str]
    ventana_completa: bool
    ventana_ms: int
    buy_notional: Optional[float]      # USDT, compras agresoras
    sell_notional: Optional[float]     # USDT, ventas agresoras
    bid_notional_top20: Optional[float]  # USDT, profundidad de compra top-20
    ask_notional_top20: Optional[float]  # USDT, profundidad de venta top-20
    precio_cierre: Optional[float]     # precio_base (mid del libro conocido)
    precio_fuente: Optional[str]
    precio_event_ms: Optional[int]
    precio_event_iso: Optional[str]
    integridad_valida: bool            # sin huecos, sin duplicados, sin invalidos
    fuente: str = "observaciones.jsonl"
    cobertura: Optional[Dict[str, Any]] = None

    # ---- propiedades derivadas (no inventan valores) ----

    @property
    def flujo_neto(self) -> Optional[float]:
        """F_k = compras_agresoras - ventas_agresoras (USDT)."""
        if self.buy_notional is None or self.sell_notional is None:
            return None
        return float(self.buy_notional) - float(self.sell_notional)

    def profundidad_contraria(self, direccion: str) -> Optional[float]:
        """D_k: profundidad del lado contrario a la posición candidata."""
        if direccion == "LONG":
            return self.ask_notional_top20
        if direccion == "SHORT":
            return self.bid_notional_top20
        return None

    def q(self, direccion: str) -> Optional[float]:
        """Q_k = s * F_k / D_k."""
        f = self.flujo_neto
        d = self.profundidad_contraria(direccion)
        if f is None or d is None or d <= 0:
            return None
        s = 1.0 if direccion == "LONG" else -1.0
        return s * f / d

    def esta_valida(self) -> bool:
        """Ventana utilizable: completa, con integridad, evidencia disponible
        y profundidad de ambos lados positiva y finita (se necesita cualquiera
        de los dos lados para evaluar LONG o SHORT)."""
        bid = self.bid_notional_top20
        ask = self.ask_notional_top20
        compra = self.buy_notional
        venta = self.sell_notional
        precio = self.precio_cierre
        return (
            self.ventana_completa is True
            and self.ventana_ms == 60_000
            and self.integridad_valida is True
            and self.disponibilidad_ms is not None
            and self.evento_ms is not None
            and _es_finito_positivo(bid)
            and _es_finito_positivo(ask)
            and (compra is None or _es_finito(compra) and compra >= 0.0)
            and (venta is None or _es_finito(venta) and venta >= 0.0)
            and (precio is None or _es_finito_positivo(precio))
        )


@dataclass
class ResultadoSecuencia:
    """Resultado de la detección para un símbolo."""

    symbol: str
    observation_id: str  # última ventana de la secuencia evaluada
    decision: str  # LONG_EXPERIMENTAL | SHORT_EXPERIMENTAL | SIN_PATRON | DATOS_INSUFICIENTES
    direccion_candidata: Optional[str]  # LONG | SHORT | None
    ventanas: List[Dict[str, Any]]  # las tres ventanas usadas (o menos si insuficiente)
    condiciones_cumplidas: List[str]
    condiciones_faltantes: List[str]
    motivo: str
    config_version: str
    config_hash: str
    instante_deteccion_ms: Optional[int]  # disponibilidad_ms de la última ventana usada
    instante_deteccion_iso: Optional[str]
    procedencia: str = "observaciones.jsonl (ventana 4)"


# ---------------------------------------------------------------------------
# Detección
# ---------------------------------------------------------------------------

def _es_finito_positivo(valor: Optional[float]) -> bool:
    if valor is None:
        return False
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v > 0.0


def _es_finito(valor: Optional[float]) -> bool:
    if valor is None:
        return False
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


# --- helper corregido para evento_ms ---

def _evento_ms_de_observacion(o: Dict[str, Any]) -> Optional[int]:
    """Instante del evento más reciente entre flujo y libro."""
    flujo = o.get("flujo") or {}
    libro = o.get("libro") or {}
    candidatos: List[int] = []
    for fuente in (flujo, libro):
        v = fuente.get("event_ms")
        if v is not None:
            try:
                candidatos.append(int(v))
            except (TypeError, ValueError):
                pass
    return max(candidatos) if candidatos else None


def ventana_desde_observacion(o: Dict[str, Any]) -> Optional[VentanaPresion]:
    """Construye una VentanaPresion a partir de una observación persistida."""
    simbolo = o.get("symbol")
    oid = o.get("observation_id")
    decision_ms = o.get("decision_ms")
    flujo = o.get("flujo") or {}
    libro = o.get("libro") or {}
    disponibilidad = o.get("disponibilidad") or {}
    integridad = o.get("integridad") or {}

    if simbolo is None or oid is None or decision_ms is None:
        return None

    try:
        decision_ms_int = int(decision_ms)
    except (TypeError, ValueError):
        return None

    ventana_ms = flujo.get("window_ms")
    ventana_inicio_ms = None
    if ventana_ms is not None:
        try:
            ventana_inicio_ms = decision_ms_int - int(ventana_ms)
        except (TypeError, ValueError):
            ventana_inicio_ms = None

    disp_flujo_ms = disponibilidad.get("flujo_ms")
    disp_libro_ms = disponibilidad.get("libro_ms")
    disp_max_ms = disponibilidad.get("max_ms")
    disp_sel_ms = disponibilidad.get("seleccion_ms")
    disp_candidatos: List[int] = []
    for v in (disp_flujo_ms, disp_libro_ms, disp_max_ms, disp_sel_ms):
        if v is not None:
            try:
                disp_candidatos.append(int(v))
            except (TypeError, ValueError):
                pass
    disponibilidad_ms = max(disp_candidatos) if disp_candidatos else None

    evento_ms = _evento_ms_de_observacion(o)

    precio_cierre = o.get("precio_base")
    precio_fuente = o.get("precio_base_fuente")
    precio_event_ms = o.get("precio_base_event_ms")
    precio_event_iso = None
    if precio_event_ms is not None:
        try:
            precio_event_iso = utc_iso(int(precio_event_ms))
        except (TypeError, ValueError):
            precio_event_iso = None

    integ = integridad or {}
    invalidos = (
        (integ.get("flujo_invalidos") or 0)
        + (integ.get("libro_invalid_updates") or 0)
    )
    huecos = (
        (integ.get("huecos_detectados_en_feed") or 0)
        + (integ.get("libro_huecos") or 0)
    )
    duplicados = (
        (integ.get("dedupe_flujo") or 0)
        + (integ.get("dedupe_libro") or 0)
    )
    integridad_valida = (
        invalidos == 0
        and huecos == 0
        and duplicados == 0
        and (integ.get("flujo_tarde") or 0) == 0
        and integ.get("libro_cruzado") is False
        and integ.get("libro_degradado") is False
    )

    cobertura = o.get("cobertura") or {}

    return VentanaPresion(
        symbol=str(simbolo),
        observation_id=str(oid),
        decision_ms=decision_ms_int,
        decision_iso=o.get("decision_iso"),
        ventana_inicio_ms=ventana_inicio_ms,
        ventana_fin_ms=decision_ms_int,
        evento_ms=evento_ms,
        evento_iso=utc_iso(evento_ms) if evento_ms is not None else None,
        disponibilidad_ms=disponibilidad_ms,
        disponibilidad_iso=utc_iso(disponibilidad_ms) if disponibilidad_ms is not None else None,
        ventana_completa=bool(flujo.get("ventana_completa")) if "ventana_completa" in flujo else None,
        ventana_ms=int(ventana_ms) if ventana_ms is not None else None,
        buy_notional=float(flujo["buy_notional"]) if flujo.get("buy_notional") is not None else None,
        sell_notional=float(flujo["sell_notional"]) if flujo.get("sell_notional") is not None else None,
        bid_notional_top20=float(libro["bid_notional_top20"]) if libro.get("bid_notional_top20") is not None else None,
        ask_notional_top20=float(libro["ask_notional_top20"]) if libro.get("ask_notional_top20") is not None else None,
        precio_cierre=float(precio_cierre) if precio_cierre is not None else None,
        precio_fuente=str(precio_fuente) if precio_fuente is not None else None,
        precio_event_ms=int(precio_event_ms) if precio_event_ms is not None else None,
        precio_event_iso=precio_event_iso,
        integridad_valida=integridad_valida,
        fuente="observaciones.jsonl",
        cobertura=dict(cobertura) if cobertura else None,
    )


def _evaluar_direccion(
    ventanas: List[VentanaPresion], direccion: str
) -> Dict[str, Any]:
    """Evalúa si las últimas 3 ventanas válidas cumplen el patrón para
    la dirección dada (LONG o SHORT)."""

    validas = [v for v in ventanas if v.esta_valida()]
    if len(validas) < 3:
        return {
            "cumple": False,
            "motivo": f"solo {len(validas)} ventana(s) válida(s) de 3 necesarias",
            "condiciones_cumplidas": [],
            "condiciones_faltantes": ["tres_ventanas_validas"],
            "ventanas_usadas": [
                {
                    "observation_id": v.observation_id,
                    "decision_ms": v.decision_ms,
                    "motivo_exclusione": "ventana_no_valida_o_insuficiente",
                }
                for v in ventanas[-3:]
            ],
        }

    # Se toman las PRIMERAS 3 ventanas válidas en orden cronológico. Una vez
    # emitida una decisión sobre ellas, datos futuros no la cambian.
    v1, v2, v3 = validas[0], validas[1], validas[2]

    condiciones_cumplidas: List[str] = []
    condiciones_faltantes: List[str] = []

    # --- D_k: profundidad contraria, decreciente y positiva ---
    d1 = v1.profundidad_contraria(direccion)
    d2 = v2.profundidad_contraria(direccion)
    d3 = v3.profundidad_contraria(direccion)

    if d1 is None or d2 is None or d3 is None:
        condiciones_faltantes.append("profundidad_contraria_disponible")
    elif not (_es_finito_positivo(d1) and _es_finito_positivo(d2) and _es_finito_positivo(d3)):
        condiciones_faltantes.append("profundidad_contraria_positiva_finita")
    elif not (d1 > d2 > d3):
        condiciones_faltantes.append("profundidad_contraria_decreciente")
    else:
        condiciones_cumplidas.append("profundidad_contraria_decreciente")

    # --- Q_k: s * F_k / D_k, positivo y creciente ---
    f1 = v1.flujo_neto
    f2 = v2.flujo_neto
    f3 = v3.flujo_neto

    qs: List[Optional[float]] = []
    if f1 is None or f2 is None or f3 is None or d1 is None or d2 is None or d3 is None:
        condiciones_faltantes.append("flujo_neto_o_profundidad_disponible")
        qs = [None, None, None]
    elif not (_es_finito_positivo(d1) and _es_finito_positivo(d2) and _es_finito_positivo(d3)):
        condiciones_faltantes.append("profundidad_contraria_no_positiva")
        qs = [None, None, None]
    else:
        s = 1.0 if direccion == "LONG" else -1.0
        qs = [
            s * f1 / d1,
            s * f2 / d2,
            s * f3 / d3,
        ]
        if not all(_es_finito_positivo(q) for q in qs):
            condiciones_faltantes.append("q_positivo_finito")
        elif not (qs[0] < qs[1] < qs[2]):
            condiciones_faltantes.append("q_creciente")
        else:
            condiciones_cumplidas.append("q_positivo_creciente")

    # --- Precio de cierre avanza en la dirección candidata ---
    p1 = v1.precio_cierre
    p2 = v2.precio_cierre
    p3 = v3.precio_cierre

    if p1 is None or p2 is None or p3 is None:
        condiciones_faltantes.append("precio_cierre_disponible")
    elif not (_es_finito(p1) and _es_finito(p2) and _es_finito(p3)):
        condiciones_faltantes.append("precio_cierre_finito")
    elif direccion == "LONG" and not (p1 < p2 < p3):
        condiciones_faltantes.append("precio_avanza_en_direccion_long")
    elif direccion == "SHORT" and not (p1 > p2 > p3):
        condiciones_faltantes.append("precio_avanza_en_direccion_short")
    else:
        condiciones_cumplidas.append("precio_avanza_en_direccion")

    cumple = len(condiciones_faltantes) == 0

    return {
        "cumple": cumple,
        "motivo": "patron_cumplido" if cumple else "patron_no_cumplido",
        "condiciones_cumplidas": condiciones_cumplidas,
        "condiciones_faltantes": condiciones_faltantes,
        "ventanas_usadas": [
            {
                "observation_id": v.observation_id,
                "symbol": v.symbol,
                "decision_ms": v.decision_ms,
                "decision_iso": v.decision_iso,
                "ventana_inicio_ms": v.ventana_inicio_ms,
                "ventana_fin_ms": v.ventana_fin_ms,
                "evento_ms": v.evento_ms,
                "evento_iso": v.evento_iso,
                "disponibilidad_ms": v.disponibilidad_ms,
                "disponibilidad_iso": v.disponibilidad_iso,
                "ventana_completa": v.ventana_completa,
                "ventana_ms": v.ventana_ms,
                "buy_notional": v.buy_notional,
                "sell_notional": v.sell_notional,
                "flujo_neto": v.flujo_neto,
                "bid_notional_top20": v.bid_notional_top20,
                "ask_notional_top20": v.ask_notional_top20,
                "profundidad_contraria": v.profundidad_contraria(direccion),
                "q_k": v.q(direccion),
                "precio_cierre": v.precio_cierre,
                "precio_fuente": v.precio_fuente,
                "precio_event_ms": v.precio_event_ms,
                "precio_event_iso": v.precio_event_iso,
                "integridad_valida": v.integridad_valida,
                "ventana_valida": v.esta_valida(),
            }
            for v in (v1, v2, v3)
        ],
        "valores": {
            "f1": f1,
            "f2": f2,
            "f3": f3,
            "d1": d1,
            "d2": d2,
            "d3": d3,
            "q1": qs[0],
            "q2": qs[1],
            "q3": qs[2],
            "p1": p1,
            "p2": p2,
            "p3": p3,
        },
    }


def detectar_secuencia(
    ventanas: List[VentanaPresion],
    symbol: str,
) -> ResultadoSecuencia:
    """Evalúa LONG y SHORT sobre las ventanas de un símbolo y emite una
    única decisión.

    Orden de prioridad:
      1. Si hay menos de 3 ventanas válidas -> DATOS_INSUFICIENTES.
      2. Si LONG cumple -> LONG_EXPERIMENTAL.
      3. Si SHORT cumple -> SHORT_EXPERIMENTAL.
      4. Si hay 3 válidas pero ninguna cumple -> SIN_PATRON.
    """

    validas = [v for v in ventanas if v.esta_valida()]

    # Contar ventanas con algún dato (para distinguir insuficiente de sin patrón)
    ventanas_con_dato = [
        v for v in ventanas
        if v.flujo_neto is not None
        or v.profundidad_contraria("LONG") is not None
        or v.profundidad_contraria("SHORT") is not None
        or v.precio_cierre is not None
    ]

    if len(validas) < 3:
        motivo = (
            f"solo {len(validas)} ventana(s) válida(s) de 3 necesarias "
            f"({len(ventanas_con_dato)} con algún dato)"
        )
        return ResultadoSecuencia(
            symbol=symbol,
            observation_id=ventanas[-1].observation_id if ventanas else "",
            decision="DATOS_INSUFICIENTES",
            direccion_candidata=None,
            ventanas=[
                {
                    "observation_id": v.observation_id,
                    "decision_ms": v.decision_ms,
                    "motivo_exclusione": "ventana_no_valida_o_datos_insuficientes",
                }
                for v in ventanas[-3:]
            ],
            condiciones_cumplidas=[],
            condiciones_faltantes=["tres_ventanas_validas"],
            motivo=motivo,
            config_version=CONFIG_VERSION,
            config_hash=CONFIG_HASH,
            instante_deteccion_ms=ventanas[-1].disponibilidad_ms if ventanas else None,
            instante_deteccion_iso=utc_iso(ventanas[-1].disponibilidad_ms) if ventanas and ventanas[-1].disponibilidad_ms is not None else None,
        )

    # Evaluar LONG y SHORT sobre las últimas 3 válidas
    res_long = _evaluar_direccion(validas, "LONG")
    res_short = _evaluar_direccion(validas, "SHORT")

    instant = validas[-1].disponibilidad_ms

    # Instante de detección: disponibilidad de la 3ra ventana (cuando se
    # completa la secuencia). Datos futuros no cambian esta decisión.
    instant = validas[2].disponibilidad_ms

    if res_long["cumple"]:
        return ResultadoSecuencia(
            symbol=symbol,
            observation_id=validas[2].observation_id,
            decision="LONG_EXPERIMENTAL",
            direccion_candidata="LONG",
            ventanas=res_long["ventanas_usadas"],
            condiciones_cumplidas=res_long["condiciones_cumplidas"],
            condiciones_faltantes=res_long["condiciones_faltantes"],
            motivo=res_long["motivo"],
            config_version=CONFIG_VERSION,
            config_hash=CONFIG_HASH,
            instante_deteccion_ms=instant,
            instante_deteccion_iso=utc_iso(instant) if instant is not None else None,
        )
    if res_short["cumple"]:
        return ResultadoSecuencia(
            symbol=symbol,
            observation_id=validas[2].observation_id,
            decision="SHORT_EXPERIMENTAL",
            direccion_candidata="SHORT",
            ventanas=res_short["ventanas_usadas"],
            condiciones_cumplidas=res_short["condiciones_cumplidas"],
            condiciones_faltantes=res_short["condiciones_faltantes"],
            motivo=res_short["motivo"],
            config_version=CONFIG_VERSION,
            config_hash=CONFIG_HASH,
            instante_deteccion_ms=instant,
            instante_deteccion_iso=utc_iso(instant) if instant is not None else None,
        )

    # Ninguna dirección cumplió, pero hay 3 válidas -> SIN_PATRON
    # Unir condiciones faltantes de ambas para diagnóstico
    faltantes = sorted(
        set(res_long["condiciones_faltantes"])
        | set(res_short["condiciones_faltantes"])
    )
    return ResultadoSecuencia(
        symbol=symbol,
        observation_id=validas[2].observation_id,
        decision="SIN_PATRON",
        direccion_candidata=None,
        ventanas=res_long["ventanas_usadas"],
        condiciones_cumplidas=[],
        condiciones_faltantes=faltantes,
        motivo=(
            "ninguna dirección cumple el patrón mecánico; "
            + "; ".join(faltantes)
            if faltantes
            else "ninguna dirección cumple el patrón mecánico"
        ),
        config_version=CONFIG_VERSION,
        config_hash=CONFIG_HASH,
        instante_deteccion_ms=instant,
        instante_deteccion_iso=utc_iso(instant) if instant is not None else None,
    )


# ---------------------------------------------------------------------------
# Procesamiento de observaciones persistidas
# ---------------------------------------------------------------------------

def cargar_observaciones(ruta_archivo: Path) -> List[Dict[str, Any]]:
    """Carga observaciones de tipo 'observación' desde un JSONL."""
    obs: List[Dict[str, Any]] = []
    with io.open(ruta_archivo, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                o = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if o.get("kind") == "observacion":
                obs.append(o)
    return obs


def agrupar_por_simbolo(
    observaciones: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Agrupa observaciones por símbolo y las ordena por tiempo de decisión."""
    por_simbolo: Dict[str, List[Dict[str, Any]]] = {}
    for o in observaciones:
        simbolo = o.get("symbol")
        if simbolo is None:
            continue
        por_simbolo.setdefault(str(simbolo), []).append(o)
    for simbolo in por_simbolo:
        por_simbolo[simbolo].sort(key=lambda o: int(o["decision_ms"]))
    return por_simbolo


def ventana_desde_observacion_publica(o: Dict[str, Any]) -> Optional[VentanaPresion]:
    """Punto de entrada público para construir una VentanaPresion."""
    return ventana_desde_observacion(o)


def detectar_en_observaciones(
    observaciones: List[Dict[str, Any]],
) -> List[ResultadoSecuencia]:
    """Ejecuta el detector sobre todas las observaciones, agrupadas por símbolo.

    Devuelve una decisión por símbolo (la más reciente secuencia evaluada).
    """
    por_simbolo = agrupar_por_simbolo(observaciones)
    resultados: List[ResultadoSecuencia] = []
    for simbolo in sorted(por_simbolo.keys()):
        obs_simbolo = por_simbolo[simbolo]
        ventanas: List[VentanaPresion] = []
        for o in obs_simbolo:
            v = ventana_desde_observacion(o)
            if v is not None:
                ventanas.append(v)
        if not ventanas:
            continue
        resultado = detectar_secuencia(ventanas, simbolo)
        resultados.append(resultado)
    return resultados


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resultado_a_dict(r: ResultadoSecuencia) -> Dict[str, Any]:
    return {
        "symbol": r.symbol,
        "observation_id": r.observation_id,
        "decision": r.decision,
        "direccion_candidata": r.direccion_candidata,
        "ventanas": r.ventanas,
        "condiciones_cumplidas": r.condiciones_cumplidas,
        "condiciones_faltantes": r.condiciones_faltantes,
        "motivo": r.motivo,
        "config_version": r.config_version,
        "config_hash": r.config_hash,
        "instante_deteccion_ms": r.instante_deteccion_ms,
        "instante_deteccion_iso": r.instante_deteccion_iso,
        "procedencia": r.procedencia,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = __import__("argparse").ArgumentParser(
        description="Detector experimental SECUENCIA-PRESION-V1 (local, sin mercado)."
    )
    parser.add_argument(
        "--fuente",
        required=True,
        help="ruta al JSONL de observaciones (observaciones.jsonl)",
    )
    parser.add_argument(
        "--salida",
        required=True,
        help="ruta al JSONL de salida con las decisiones",
    )
    args = parser.parse_args(argv)

    ruta_fuente = Path(args.fuente)
    if not ruta_fuente.exists():
        print(json.dumps({"error": f"fuente no existe: {ruta_fuente}"}), file=sys.stderr)
        return 3

    observaciones = cargar_observaciones(ruta_fuente)
    resultados = detectar_en_observaciones(observaciones)

    ruta_salida = Path(args.salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    with io.open(ruta_salida, "w", encoding="utf-8", newline="\n") as f:
        for r in resultados:
            f.write(json.dumps(_resultado_a_dict(r), ensure_ascii=False, sort_keys=True) + "\n")

    resumen = {
        "estado": "ok",
        "symboles_procesados": len(resultados),
        "detecciones_long": sum(1 for r in resultados if r.decision == "LONG_EXPERIMENTAL"),
        "detecciones_short": sum(1 for r in resultados if r.decision == "SHORT_EXPERIMENTAL"),
        "sin_patron": sum(1 for r in resultados if r.decision == "SIN_PATRON"),
        "datos_insuficientes": sum(1 for r in resultados if r.decision == "DATOS_INSUFICIENTES"),
        "salida": str(ruta_salida),
    }
    print(json.dumps(resumen, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
