"""Registro acotado y opcional de cotizaciones para investigacion local.

Reutiliza las features que ``BookEngine`` ya calcula. No guarda el libro
completo: solo mejor bid/ask, cantidad visible en la punta, timestamps y
calidad. Desactivado por defecto; nunca participa en una decision.

Criterios congelados en
``docs/evidence/cotizaciones-local-20261119/PREDECLARACION.md``.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "cotizaciones-local-v1"
NOMBRE_ARCHIVO = "cotizaciones_investigacion.jsonl"
MAX_EDAD_MS = 5_000
CADENCIA_MS = 1_000
TAMANO_SIMULADO = 1.0
LIMITE_FILAS = 20_000
LIMITE_BYTES = 4 * 1024 * 1024
BYTES_POR_FILA_ESTIMADOS = 512

CODIGOS_INVALIDOS = (
    "LIBRO_CRUZADO",
    "SALTO_SECUENCIA",
    "LIBRO_DEGRADADO",
    "PRECIO_NO_VALIDO",
    "CANTIDAD_NO_VALIDA",
    "SIN_NIVELES",
)


# ---------------------------------------------------------------------------
# Escritura acotada
# ---------------------------------------------------------------------------


class QuoteTape:
    """Escritor acotado sobre el ``PilotStore`` ya existente."""

    def __init__(self, store: Any, run_id: str, *,
                 max_rows: int = LIMITE_FILAS,
                 max_bytes: int = LIMITE_BYTES,
                 cadencia_ms: int = CADENCIA_MS) -> None:
        self.store = store
        self.run_id = str(run_id)
        self.max_rows = max(1, int(max_rows))
        self.max_bytes = max(0, int(max_bytes))
        self.cadencia_ms = max(1, int(cadencia_ms))
        self.rows_written = 0
        self.bytes_written = 0
        self.cap_reached = False
        self.cap_reason: Optional[str] = None
        self.quotes_written = 0
        self.missing_written = 0
        self.duplicated_seconds = 0
        self._segundo_por_simbolo: Dict[str, int] = {}
        self._seq = 0
        self._cerrando = False
        self._limite_escrito = False

    def _escribir(self, row: Dict[str, Any], *, marca: bool = False) -> bool:
        if self.cap_reached and not (marca and self._cerrando):
            return False
        self._seq += 1
        completo = dict(row)
        completo["seq"] = self._seq
        payload = json.dumps(completo, ensure_ascii=False,
                             sort_keys=True) + "\n"
        encoded = len(payload.encode("utf-8"))
        if not marca:
            if self.rows_written >= self.max_rows:
                self._cerrar("limite_filas", received_ms=row.get("received_ms"))
                return False
            if self.max_bytes and self.bytes_written + encoded > self.max_bytes:
                self._cerrar("limite_bytes", received_ms=row.get("received_ms"))
                return False
        elif self.max_bytes and self.bytes_written + encoded > self.max_bytes:
            return False
        try:
            ok = bool(self.store.write(completo))
        except Exception:
            if not marca:
                self._cerrar("error_escritura")
            return False
        if not ok:
            if not marca:
                self._cerrar("presupuesto_global")
            return False
        self.rows_written += 1
        self.bytes_written += encoded
        return True

    def _cerrar(self, motivo: str, received_ms: Optional[int] = None) -> None:
        if self.cap_reached:
            return
        self.cap_reached = True
        self.cap_reason = motivo
        if self._limite_escrito or self._cerrando:
            return
        self._limite_escrito = True
        self._cerrando = True
        try:
            self._escribir({
                "kind": "limite",
                "version": VERSION,
                "run_id": self.run_id,
                "received_ms": int(received_ms or time.time() * 1000),
                "motivo": motivo,
                "filas_escritas": self.rows_written,
                "bytes_escritos": self.bytes_written,
            }, marca=True)
        finally:
            self._cerrando = False

    @staticmethod
    def _finotos(features: Dict[str, Any], degraded: bool,
                 gap: bool) -> List[str]:
        motivos: List[str] = []
        try:
            bid = float(features.get("best_bid"))
            ask = float(features.get("best_ask"))
        except (TypeError, ValueError):
            bid, ask = float("nan"), float("nan")
        precios_ok = (math.isfinite(bid) and math.isfinite(ask)
                      and bid > 0 and ask > 0 and ask > bid)
        if bool(features.get("crossed")) or (math.isfinite(bid)
                                             and math.isfinite(ask)
                                             and bid >= ask > 0):
            motivos.append("LIBRO_CRUZADO")
        if degraded:
            motivos.append("LIBRO_DEGRADADO")
        if gap:
            motivos.append("SALTO_SECUENCIA")
        if not precios_ok and "LIBRO_CRUZADO" not in motivos:
            motivos.append("PRECIO_NO_VALIDO")
        try:
            qbid = float(features.get("top_bid_qty"))
            qask = float(features.get("top_ask_qty"))
            cantidades_ok = (math.isfinite(qbid) and math.isfinite(qask)
                             and qbid > 0 and qask > 0)
        except (TypeError, ValueError):
            qbid, qask, cantidades_ok = 0.0, 0.0, False
        if not cantidades_ok:
            motivos.append("CANTIDAD_NO_VALIDA")
        try:
            niveles_ok = (int(features.get("bid_levels") or 0) >= 1
                          and int(features.get("ask_levels") or 0) >= 1)
        except (TypeError, ValueError):
            niveles_ok = False
        if not niveles_ok:
            motivos.append("SIN_NIVELES")
        return [m for m in CODIGOS_INVALIDOS if m in motivos]

    def record_quote(self, symbol: str, event_ms: int, received_ms: int,
                     features: Dict[str, Any], *, degraded: bool = False,
                     gap: bool = False, crossed: bool = False) -> bool:
        """Guarda la primera punta aceptada de cada segundo de recepcion.

        Una cotizacion valida en segundo X no se duplica dentro del mismo
        segundo, pero una invalidacion posterior (rotacion, salto de
        secuencia o perdida de calidad) dentro de ese mismo segundo SÍ se
        escribe: el muestreo de una fila por segundo no debe ocultar que la
        cobertura se rompio antes de cerrar el segundo.
        """
        if self.cap_reached:
            return False
        try:
            sym = str(symbol).upper()
            ev = int(event_ms)
            recv = int(received_ms)
            segundo = recv // self.cadencia_ms
            mismo_segundo = self._segundo_por_simbolo.get(sym) == segundo
            feat = dict(features or {})
            if crossed:
                feat["crossed"] = True
            motivos = self._finotos(feat, bool(degraded), bool(gap))
            if mismo_segundo and not motivos:
                # Duplicado valido dentro del mismo segundo: no se reescribe.
                self.duplicated_seconds += 1
                return False
            fila = {
                "kind": "cotizacion",
                "version": VERSION,
                "run_id": self.run_id,
                "symbol": sym,
                "event_ms": ev,
                "received_ms": recv,
                "best_bid": feat.get("best_bid"),
                "best_ask": feat.get("best_ask"),
                "bid_qty": feat.get("top_bid_qty"),
                "ask_qty": feat.get("top_ask_qty"),
                "bid_levels": feat.get("bid_levels"),
                "ask_levels": feat.get("ask_levels"),
                "mid": feat.get("mid"),
                "spread_bps": feat.get("spread_bps"),
                "degraded": bool(degraded),
                "gap": bool(gap),
                "crossed": bool(feat.get("crossed")),
                "valida": not motivos,
                "motivos_invalidez": motivos,
                "cadencia_ms": self.cadencia_ms,
            }
            if self._escribir(fila):
                self._segundo_por_simbolo[sym] = segundo
                self.quotes_written += 1
                return True
            return False
        except Exception:
            return False

    def record_missing(self, symbol: str, received_ms: int,
                       motivo: str, detalle: Optional[str] = None) -> bool:
        """Marca explicitamente un extremo sin cotizacion por rotation/hueco."""
        if self.cap_reached:
            return False
        fila = {
            "kind": "faltante",
            "version": VERSION,
            "run_id": self.run_id,
            "symbol": str(symbol).upper(),
            "event_ms": None,
            "received_ms": int(received_ms),
            "motivo": str(motivo),
            "detalle": detalle,
            "cadencia_ms": self.cadencia_ms,
        }
        if self._escribir(fila):
            self.missing_written += 1
            return True
        return False

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "version": VERSION,
            "archivo": NOMBRE_ARCHIVO,
            "cadencia_ms": self.cadencia_ms,
            "max_rows": self.max_rows,
            "max_bytes": self.max_bytes,
            "rows_written": self.rows_written,
            "bytes_written": self.bytes_written,
            "quotes_written": self.quotes_written,
            "missing_written": self.missing_written,
            "filas_datos": self.quotes_written + self.missing_written,
            "duplicated_seconds": self.duplicated_seconds,
            "cap_reached": self.cap_reached,
            "cap_reason": self.cap_reason,
        }


def status_desactivado() -> Dict[str, Any]:
    return {
        "enabled": False,
        "version": VERSION,
        "archivo": NOMBRE_ARCHIVO,
        "rows_written": 0,
        "bytes_written": 0,
        "cap_reached": False,
        "cap_reason": None,
    }


# ---------------------------------------------------------------------------
# Lectura y evaluacion desde lo persistido
# ---------------------------------------------------------------------------


def leer_tape(path: Path) -> List[Dict[str, Any]]:
    filas: List[Dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for linea in fh:
            if linea.strip():
                filas.append(json.loads(linea))
    return filas


def _clave_orden(fila: Dict[str, Any]) -> Tuple[int, int, int]:
    return (int(fila.get("received_ms") or 0),
            int(fila.get("event_ms") or 0),
            int(fila.get("seq") or 0))


def _motivo_invalido(fila: Dict[str, Any]) -> str:
    """Extrae el primer codigo de invalidez de una fila cotizacion invalida."""
    motivos = [str(m) for m in (fila.get("motivos_invalidez") or [])]
    return motivos[0] if motivos else "CALIDAD_NO_VALIDA"


def seleccionar(symbol: str, instante_ms: int, filas: Iterable[Dict[str, Any]],
                *, run_id: Optional[str] = None,
                max_edad_ms: int = MAX_EDAD_MS) -> Dict[str, Any]:
    """Ultimo estado de cobertura conocido en ``instante_ms``.

    Recorre las filas en orden cronologico hasta el instante y mantiene un
    automa de cobertura: una cotizacion valida establece cobertura, una
    invalidez (rotacion, salto de secuencia, perdida de calidad o fila
    ``faltante``) la rompe, y solo una cotizacion valida posterior la
    restablece. Nunca se retrocede a una cotizacion previa despues de una
    invalidez. Nunca se usa una fila recibida despues del instante.
    """
    instante = int(instante_ms)
    simbolo = str(symbol).upper()

    # Recopilar y ordenar cronologicamente todas las filas relevantes hasta T.
    eventos: List[Tuple[int, int, int, Dict[str, Any]]] = []
    futuras = 0
    for fila in filas:
        if run_id is not None and fila.get("run_id") != run_id:
            continue
        if fila.get("symbol") != simbolo:
            # Las filas 'limite' son globales (sin symbol) y aplican a todos
            # los simbolos; no se filtran por symbol.
            if fila.get("kind") != "limite":
                continue
        kind = fila.get("kind")
        if kind in ("faltante", "limite"):
            try:
                recv = int(fila.get("received_ms") or 0)
            except (TypeError, ValueError):
                continue
            if recv <= instante:
                eventos.append((recv, 0, int(fila.get("seq") or 0), fila))
            continue
        if kind != "cotizacion":
            continue
        try:
            recv = int(fila["received_ms"])
            ev = int(fila["event_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        if recv > instante or ev > instante:
            futuras += 1
            continue
        eventos.append((recv, ev, int(fila.get("seq") or 0), fila))
    eventos.sort(key=lambda e: (e[0], e[1], e[2]))

    # Automata de cobertura: estado actual al llegar al instante.
    cotizacion_actual: Optional[Dict[str, Any]] = None
    motivo_actual: Optional[str] = None
    for _recv, _ev, _seq, fila in eventos:
        kind = fila.get("kind")
        if kind == "cotizacion":
            if fila.get("valida") is True:
                cotizacion_actual = fila
                motivo_actual = None
            else:
                cotizacion_actual = None
                motivo_actual = _motivo_invalido(fila)
        elif kind == "faltante":
            cotizacion_actual = None
            motivo_actual = str(fila.get("motivo")
                                or "SIMBOLO_FUERA_DE_SEGUIMIENTO").upper()
        elif kind == "limite":
            cotizacion_actual = None
            motivo_actual = "LIMITE_ALCANZADO"

    rech_viejas = 0
    for _recv, ev, _seq, fila in eventos:
        if fila.get("kind") == "cotizacion" and instante - int(fila["event_ms"]) > max_edad_ms:
            rech_viejas += 1

    if cotizacion_actual is not None:
        ev = int(cotizacion_actual["event_ms"])
        recv = int(cotizacion_actual["received_ms"])
        if ev > instante or recv > instante:
            return {"cotizacion": None, "motivo": "COTIZACION_FUTURA",
                    "candidatas": 0,
                    "rechazadas_posteriores": futuras,
                    "rechazadas_viejas": rech_viejas}
        if instante - ev > max_edad_ms:
            return {"cotizacion": None, "motivo": "COTIZACION_VIEJA",
                    "candidatas": 0,
                    "rechazadas_posteriores": futuras,
                    "rechazadas_viejas": rech_viejas}
        return {"cotizacion": cotizacion_actual, "motivo": None,
                "candidatas": 1,
                "rechazadas_posteriores": futuras,
                "rechazadas_viejas": rech_viejas}

    if motivo_actual is not None:
        return {"cotizacion": None, "motivo": motivo_actual,
                "candidatas": 0,
                "rechazadas_posteriores": futuras,
                "rechazadas_viejas": rech_viejas}

    if futuras:
        return {"cotizacion": None, "motivo": "COTIZACION_FUTURA",
                "candidatas": 0,
                "rechazadas_posteriores": futuras,
                "rechazadas_viejas": rech_viejas}
    return {"cotizacion": None, "motivo": "SIN_COTIZACION",
            "candidatas": 0,
            "rechazadas_posteriores": 0,
            "rechazadas_viejas": 0}


def evaluar_episodio(
    symbol: str, entrada_ms: int, salida_ms: int, lado: str,
    size: float, filas: Iterable[Dict[str, Any]], *,
    run_id: Optional[str] = None, max_edad_ms: int = MAX_EDAD_MS,
    precio_ref_entrada: Optional[float] = None,
    precio_ref_salida: Optional[float] = None,
) -> Dict[str, Any]:
    """Compara retorno de referencia y retorno cruzando el spread, una vez."""
    lado = str(lado).upper()
    if lado not in ("LONG", "SHORT"):
        raise ValueError("lado debe ser LONG o SHORT")
    size_f = float(size)
    entradas = seleccionar(symbol, entrada_ms, filas, run_id=run_id,
                           max_edad_ms=max_edad_ms)
    salidas = seleccionar(symbol, salida_ms, filas, run_id=run_id,
                          max_edad_ms=max_edad_ms)
    resultado: Dict[str, Any] = {
        "version": VERSION,
        "symbol": str(symbol).upper(),
        "lado": lado,
        "entrada_ms": int(entrada_ms),
        "salida_ms": int(salida_ms),
        "size": size_f,
        "max_edad_ms": int(max_edad_ms),
        "fila_entrada": entradas.get("cotizacion"),
        "fila_salida": salidas.get("cotizacion"),
        "motivo_entrada": entradas.get("motivo"),
        "motivo_salida": salidas.get("motivo"),
        "evaluable": False,
        "motivo": None,
        "precio_entrada": None,
        "precio_salida": None,
        "cantidad_entrada": None,
        "cantidad_salida": None,
        "retorno_referencia_precio_bps": None,
        "retorno_referencia_mid_bps": None,
        "retorno_cruce_bps": None,
        "coste_spread_bps": None,
        "comision_bps": "UNKNOWN",
        "slippage_adicional_bps": "UNKNOWN",
        "funding_bps": "UNKNOWN",
        "retorno_neto_bps": "UNKNOWN",
        "precios_son_fills": False,
    }
    if entradas.get("motivo"):
        resultado["motivo"] = f"SIN_COTIZACION_ENTRADA:{entradas['motivo']}"
        return resultado
    if salidas.get("motivo"):
        resultado["motivo"] = f"SIN_COTIZACION_SALIDA:{salidas['motivo']}"
        return resultado

    cin = entradas["cotizacion"]
    cout = salidas["cotizacion"]
    if lado == "LONG":
        pin, qin = cin["best_ask"], cin["ask_qty"]
        pout, qout = cout["best_bid"], cout["bid_qty"]
    else:
        pin, qin = cin["best_bid"], cin["bid_qty"]
        pout, qout = cout["best_ask"], cout["ask_qty"]
    resultado.update({
        "precio_entrada": float(pin), "precio_salida": float(pout),
        "cantidad_entrada": float(qin), "cantidad_salida": float(qout),
    })
    if float(qin) < size_f or float(qout) < size_f:
        resultado["motivo"] = "TAMANO_INSUFICIENTE"
        return resultado

    signo = 1.0 if lado == "LONG" else -1.0
    mid_in, mid_out = float(cin["mid"]), float(cout["mid"])
    ref_mid = signo * (mid_out / mid_in - 1.0) * 10_000.0
    cruce = signo * (float(pout) / float(pin) - 1.0) * 10_000.0
    resultado.update({
        "evaluable": True,
        "retorno_referencia_mid_bps": ref_mid,
        "retorno_cruce_bps": cruce,
        "coste_spread_bps": ref_mid - cruce,
    })
    if precio_ref_entrada is not None and precio_ref_salida is not None:
        resultado["retorno_referencia_precio_bps"] = signo * (
            float(precio_ref_salida) / float(precio_ref_entrada) - 1.0
        ) * 10_000.0
    return resultado
