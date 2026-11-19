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
        self.cap_instante_ms: Optional[int] = None
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
        self.cap_instante_ms = int(received_ms or time.time() * 1000)
        if self._limite_escrito or self._cerrando:
            return
        self._limite_escrito = True
        self._cerrando = True
        try:
            self._escribir({
                "kind": "limite",
                "version": VERSION,
                "run_id": self.run_id,
                "received_ms": self.cap_instante_ms,
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
            "cap_instante_ms": self.cap_instante_ms,
            "run_id": self.run_id,
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


def _clave_orden(fila: Dict[str, Any]) -> Tuple[int, int]:
    """Orden de replay: primero received_ms, desempate por seq persistido.

    event_ms solo se usa para comprobar disponibilidad y frescura, nunca
    para ordenar retroactivamente las marcas.
    """
    return (int(fila.get("received_ms") or 0),
            int(fila.get("seq") or 0))


def _motivo_invalido(fila: Dict[str, Any]) -> str:
    """Extrae el primer codigo de invalidez de una fila cotizacion invalida."""
    motivos = [str(m) for m in (fila.get("motivos_invalidez") or [])]
    return motivos[0] if motivos else "CALIDAD_NO_VALIDA"


def seleccionar(symbol: str, instante_ms: int, filas: Iterable[Dict[str, Any]],
                *, run_id: Optional[str] = None,
                max_edad_ms: int = MAX_EDAD_MS,
                agotamiento: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Ultimo estado de cobertura conocido en ``instante_ms``.

    Recorre las filas en orden cronologico hasta el instante y mantiene un
    automa de cobertura: una cotizacion valida establece cobertura, una
    invalidez (rotacion, salto de secuencia, perdida de calidad o fila
    ``faltante``) la rompe, y solo una cotizacion valida posterior la
    restablece. Nunca se retrocede a una cotizacion previa despues de una
    invalidez. Nunca se usa una fila recibida despues del instante.

    ``agotamiento`` (opcional) es la evidencia de agotamiento de la cinta
    leida de un artefacto persistido del piloto (resumen.json/estado.json):
      - {"instante_ms": int, "motivo": str}: la cinta se agoto en ese
        instante; consultas en o despues de ese instante devuelven
        LIMITE_ALCANZADO, consultas antes conservan su resultado valido.
      - {"instante_ms": None, "motivo": str}: se sabe que se agoto pero no
        se acredita cuando; se declara cobertura UNKNOWN para el tramo
        afectado.
    """
    instante = int(instante_ms)
    simbolo = str(symbol).upper()

    # Recopilar y ordenar cronologicamente todas las filas relevantes hasta T.
    # Orden: received_ms primero, desempate por seq persistido.
    eventos: List[Tuple[int, int, Dict[str, Any]]] = []
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
                eventos.append((recv, int(fila.get("seq") or 0), fila))
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
        eventos.append((recv, int(fila.get("seq") or 0), fila))
    eventos.sort(key=lambda e: (e[0], e[1]))

    # Automata de cobertura: estado actual al llegar al instante.
    cotizacion_actual: Optional[Dict[str, Any]] = None
    motivo_actual: Optional[str] = None
    for _recv, _seq, fila in eventos:
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
    for _recv, _seq, fila in eventos:
        if fila.get("kind") == "cotizacion" and instante - int(fila["event_ms"]) > max_edad_ms:
            rech_viejas += 1

    # --- Agotamiento de la cinta (evidencia persistida, fuera del JSONL) ---
    ag_instante: Optional[int] = None
    ag_motivo: Optional[str] = None
    if agotamiento is not None:
        try:
            ag_instante = agotamiento.get("instante_ms")
            ag_instante = int(ag_instante) if ag_instante is not None else None
        except (TypeError, ValueError):
            ag_instante = None
        ag_motivo = str(agotamiento.get("motivo") or "LIMITE_ALCANZADO")

    if ag_instante is not None and instante >= ag_instante:
        # La cinta ya se agoto antes o en este instante (instante conocido).
        return {"cotizacion": None, "motivo": "LIMITE_ALCANZADO",
                "candidatas": 0,
                "rechazadas_posteriores": futuras,
                "rechazadas_viejas": rech_viejas,
                "agotamiento": ag_motivo}

    if motivo_actual is not None:
        # Razones concretas de libro invalido en el ultimo estado conocido.
        return {"cotizacion": None, "motivo": motivo_actual,
                "candidatas": 0,
                "rechazadas_posteriores": futuras,
                "rechazadas_viejas": rech_viejas}

    if agotamiento is not None and ag_instante is None:
        # Sabemos que la cinta se agoto pero no cuando: la frescura de una
        # cita no equivale a cobertura, no se puede acreditar que la cita
        # valida prediga al agotamiento. Declaramos UNKNOWN para el tramo.
        return {"cotizacion": None, "motivo": "COBERTURA_UNKNOWN",
                "candidatas": 0,
                "rechazadas_posteriores": futuras,
                "rechazadas_viejas": rech_viejas,
                "agotamiento": ag_motivo}

    if cotizacion_actual is not None:
        # Solo se usa una cita valida cuando no hay incertidumbre de
        # agotamiento (o cuando se sabe que predice al corte conocido).
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
    agotamiento: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compara retorno de referencia y retorno cruzando el spread, una vez.

    ``agotamiento`` es la evidencia de agotamiento de la cinta leida de un
    artefacto persistido del piloto (resumen.json). Se aplica a ambos
    extremos: la entrada anterior al corte se conserva, la salida posterior
    se rechaza con LIMITE_ALCANZADO.
    """
    lado = str(lado).upper()
    if lado not in ("LONG", "SHORT"):
        raise ValueError("lado debe ser LONG o SHORT")
    size_f = float(size)
    entradas = seleccionar(symbol, entrada_ms, filas, run_id=run_id,
                           max_edad_ms=max_edad_ms,
                           agotamiento=agotamiento)
    salidas = seleccionar(symbol, salida_ms, filas, run_id=run_id,
                          max_edad_ms=max_edad_ms,
                          agotamiento=agotamiento)
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


def _resultado_no_evaluable(
    symbol: str, entrada_ms: int, salida_ms: int, lado: str,
    size: float, motivo: str, *,
    max_edad_ms: int = MAX_EDAD_MS,
    detalle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resultado base no evaluable (misma forma que ``evaluar_episodio``)."""
    size_f = float(size)
    return {
        "version": VERSION,
        "symbol": str(symbol).upper(),
        "lado": str(lado).upper(),
        "entrada_ms": int(entrada_ms),
        "salida_ms": int(salida_ms),
        "size": size_f,
        "max_edad_ms": int(max_edad_ms),
        "fila_entrada": None,
        "fila_salida": None,
        "motivo_entrada": motivo,
        "motivo_salida": None,
        "evaluable": False,
        "motivo": motivo,
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
        "detalle_replay": detalle or {},
    }


def replay_episodio_desde_corrida(
    run_dir: Path,
    symbol: str,
    entrada_ms: int,
    salida_ms: int,
    lado: str,
    size: float,
    *,
    run_id: Optional[str] = None,
    max_edad_ms: int = MAX_EDAD_MS,
    precio_ref_entrada: Optional[float] = None,
    precio_ref_salida: Optional[float] = None,
) -> Dict[str, Any]:
    """Replay de un episodio desde los archivos de una corrida de piloto.

    Lee ``cotizaciones_investigacion.jsonl`` y ``resumen.json`` de
    ``run_dir``, comprueba que pertenecen al mismo ``run_id`` y construye
    internamente la evidencia de agotamiento (el llamador no la pasa).
    Reutiliza ``evaluar_episodio()``.

    Casos:
      - Corte conocido (``cap_instante_ms`` en resumen): conserva la entrada
        acreditada anterior al corte; desde el corte inclusive devuelve
        ``LIMITE_ALCANZADO`` aunque la ultima cita siga fresca y no haya
        cabido la marca final en el JSONL.
      - Agotamiento sin instante verificable: devuelve
        ``COBERTURA_UNKNOWN`` en el tramo cuya cobertura no se pueda
        acreditar. La frescura no equivale a cobertura.
      - run_id distinto, resumen ausente o invalido: devuelve un resultado
        explicito y no evaluable. Nunca se interpreta la ausencia de datos
        como prueba de que la cinta nunca se agoto.
    """
    run_dir = Path(run_dir)
    resumen_path = run_dir / "resumen.json"
    tape_path = run_dir / NOMBRE_ARCHIVO

    # --- Leer resumen.json (evidencia de agotamiento fuera del JSONL) -----
    resumen = None
    if resumen_path.exists():
        try:
            resumen = json.loads(resumen_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            resumen = None
    if not isinstance(resumen, dict):
        # Resumen ausente, no es JSON, o su raiz no es un objeto: no se puede
        # construir agotamiento, no se interpreta como ausencia de
        # agotamiento.
        return _resultado_no_evaluable(
            symbol, entrada_ms, salida_ms, lado, size,
            "RESUMEN_AUSENTE",
            max_edad_ms=max_edad_ms,
            detalle={"archivo": str(resumen_path),
                     "razon": "resumen_json_no_es_objeto_o_esta_ausente"})

    cinta = resumen.get("cotizaciones_investigacion")
    if not isinstance(cinta, dict):
        return _resultado_no_evaluable(
            symbol, entrada_ms, salida_ms, lado, size,
            "RESUMEN_INVALIDO",
            max_edad_ms=max_edad_ms,
            detalle={"razon": "cotizaciones_investigacion_ausente_o_no_es_dict"})

    # --- run_id del resumen: cadena no vacia ------------------------------
    cinta_run_id = cinta.get("run_id")
    if not isinstance(cinta_run_id, str) or not cinta_run_id:
        return _resultado_no_evaluable(
            symbol, entrada_ms, salida_ms, lado, size,
            "RESUMEN_INVALIDO",
            max_edad_ms=max_edad_ms,
            detalle={"razon": "run_id_resumen_faltante_o_no_es_cadena_no_vacia"})

    # --- Leer JSONL y sus run_ids -----------------------------------------
    filas: List[Dict[str, Any]] = []
    jsonl_run_ids: List[str] = []
    if tape_path.exists():
        try:
            filas = leer_tape(tape_path)
        except (OSError, ValueError):
            filas = []
        for f in filas:
            rid = f.get("run_id")
            if isinstance(rid, str) and rid:
                jsonl_run_ids.append(rid)

    # El run_id del resumen debe coincidir con el de la cinta (JSONL).
    if jsonl_run_ids:
        ajenos = {r for r in jsonl_run_ids if r != cinta_run_id}
        if ajenos:
            return _resultado_no_evaluable(
                symbol, entrada_ms, salida_ms, lado, size,
                "RUN_ID_DISTINTO",
                max_edad_ms=max_edad_ms,
                detalle={"run_id_solicitado": cinta_run_id,
                         "run_ids_ajenos_en_jsonl": sorted(ajenos)})

    # El run_id del resumen debe coincidir con el solicitado, si se propuso.
    if run_id is not None and run_id != cinta_run_id:
        return _resultado_no_evaluable(
            symbol, entrada_ms, salida_ms, lado, size,
            "RUN_ID_DISTINTO",
            max_edad_ms=max_edad_ms,
            detalle={"run_id_solicitado": run_id,
                     "run_id_resumen": cinta_run_id})

    efectivo_run_id = cinta_run_id

    # --- cap_reached: booleano JSON explicito -----------------------------
    # No usar bool(): ausente, null, 0, 1 y "false" son invalidos. Solo
    # false explícito acredita que no hubo agotamiento.
    cap_reached_raw = cinta.get("cap_reached")
    if cap_reached_raw is True:
        cap_reached = True
    elif cap_reached_raw is False:
        cap_reached = False
    else:
        return _resultado_no_evaluable(
            symbol, entrada_ms, salida_ms, lado, size,
            "RESUMEN_INVALIDO",
            max_edad_ms=max_edad_ms,
            detalle={"razon": "cap_reached_no_es_booleano_json_explicito",
                     "valor": cap_reached_raw})

    # --- Construir agotamiento a partir del resumen (el llamador no lo pasa
    #     a evaluar_episodio) --------------------------------------------
    agotamiento: Optional[Dict[str, Any]] = None
    if cap_reached:
        cap_instante_ms = cinta.get("cap_instante_ms")
        try:
            cap_instante_ms = (int(cap_instante_ms)
                               if cap_instante_ms is not None else None)
        except (TypeError, ValueError):
            cap_instante_ms = None
        cap_reason = cinta.get("cap_reason") or "LIMITE_ALCANZADO"
        agotamiento = {"instante_ms": cap_instante_ms,
                       "motivo": str(cap_reason)}

    return evaluar_episodio(
        symbol, entrada_ms, salida_ms, lado, size, filas,
        run_id=efectivo_run_id, max_edad_ms=max_edad_ms,
        precio_ref_entrada=precio_ref_entrada,
        precio_ref_salida=precio_ref_salida,
        agotamiento=agotamiento,
    )
