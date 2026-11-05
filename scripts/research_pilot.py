"""Piloto prospectivo de investigacion (solo lectura de datos publicos, sin ordenes).

Objetivo: producir observaciones con tiempos, cobertura y precios honestos para
la hipotesis "liquidez disponible frente a flujo agresor -> movimiento posterior".
NO es un motor nuevo, ni un supervisor, ni un servicio residente: es un CLI
acotado que coordina componentes existentes.

Reutilizacion (delta minimo):
- ``discovery.build_candidates``: elegibilidad (PERPETUAL/TRADING/USDT/volumen)
  y tabla de movimiento 24h.
- ``research_selector``: universo observado + politica research-selector-v2 +
  seleccion de candidatos y comparadores con techo conjunto (<= 20).
- ``book.BookEngine``: features de libro top-20 (spread, imbalance, microprice,
  profundidad base/notional, bandas realmente cubiertas, huecos/cruzados).
- ``flow.FlowEngine``: flujo agresor por ventana trailing (delta, delta_ratio,
  volumen base/notional, trades, calentamiento de ventana).
- ``history_client.HistoryClient``: REST publico con limitador, reintentos,
  contabilidad de peso y puerta de presupuesto (``attempt_gate``).
- ``history_store.HistoryStore`` + ``research_recorder.ResearchRecorder``:
  agregados 1m/10s completos y parciales en SQLite (buckets parciales marcados).
- ``universe.SymbolUniverse``: conjunto explicito de simbolos seguidos.

Protocolo fijado antes de capturar (ver docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md
seccion 9):
- Universo: catalogo publico (PERPETUAL/TRADING/USDT) + tickers 24h; snapshot
  con ``as_of_ms`` y procedencia; el catalogo NO acredita universo historico.
- Seleccion cada ``selection_seconds`` (research-selector-v2, umbral 0.02 pp
  como HIPOTESIS, no se ajusta aqui). Candidatos <= 12, comparadores <= 8,
  union <= 20. Sin resultados futuros.
- Decisiones cada ``cycle_seconds``: el instante de decision es el instante
  REAL en que se construyen las variables (el reloj del piloto), nunca
  ``bucket_end`` y nunca retrotraido. Las disponibilidades de libro, flujo y
  seleccion se registran por separado y todas deben ser <= decision_ms.
- Horizontes de resultado: 5m/15m/60m por defecto, medidos desde decision_ms.
- Frescura independiente por fuente: un flujo reciente no rejuvenece un libro
  antiguo, ni al contrario. Antiguedad de evento y de recepción registradas por
  separado. Ausencia, obsolescencia, reloj incoherente y cobertura insuficiente
  tienen motivos diferenciados.
- Ventana completa: para apto_para_evaluacion se exige calentamiento y
  cobertura suficientes (ventana de 1m completa). Las observaciones parciales
  se conservan con motivo explicito pero quedan excluidas del conjunto apto.
- Precios honestos: precio_base = mid del libro (libro_mid) y precio posterior
  = apertura de vela 1m (klines_apertura_1m). Es un proxy de fuentes mixtas,
  NO mark-to-mid ni P&L ejecutable. Se registran fuente, timestamp,
  disponibilidad, desfase y horizonte efectivo de ambos.
- Duracion = captura + settle; el settle permite madurar resultados. Durante el
  settle siguen vigentes presupuesto, plazo y cancelacion.
- Presupuesto EFECTIVO (no solo estimado): HistoryClient reserva cada intento
  HTTP antes del transporte mediante una puerta de presupuesto con maximos
  explícitos de intentos totales, reintentos totales y peso acumulado.
  Agotar una cota produce parada con causa y limpieza. El almacenamiento
  contempla JSONL + SQLite + archivos auxiliares.

Reloj: ``--clock system`` (produccion) o ``--clock manual --clock-file PATH``
(solo pruebas). No se inventan timestamps: un dato sin marca de disponibilidad
queda UNKNOWN.

Sincronizacion de pruebas (solo con ``--clock manual``):
- ``--status-file PATH``: el piloto publica de forma atomica un snapshot de
  progreso (instante simulado, fuentes seguidas, contadores aceptados por
  fuente, ultima disponibilidad por fuente, feeds, fase y motivo de parada).
  No altera el camino productivo.
- ``--decision-gate-file PATH``: barrera explicita de evaluacion. Si se indica,
  una decision solo se toma cuando el fichero contiene el mismo instante que el
  reloj (``{"decision_ms": <ms>}`` o el entero). Permite fijar el instante,
  publicar los eventos, esperar confirmacion de procesamiento y AUTORIZAR la
  evaluacion en ese instante; nunca adelanta ni retrasa el reloj.
- ``--stop-file PATH``: parada explicita del operador para pruebas. Al existir,
  el piloto deja de adquirir datos, no consulta mas precios, conserva lo ya
  escrito y persiste los resultados pendientes con causa ``parada_operador``.

Politica de pendientes:
- Fin normal de captura: se deja de seleccionar/capturar y SOLO se maduran los
  resultados ya programados durante el settle acotado; presupuesto, plazo y
  cancelacion siguen vigentes.
- Fin del settle: lo no resuelto se persiste como ``pendiente`` con causa
  (``ventana_de_settle_agotada`` u otra parada); no se inventan precios ni se
  prorroga el plazo.
- Parada explicita: se detiene la adquisicion, no se consultan mas precios y se
  conservan observaciones y pendientes.
- Presupuesto agotado o fallo que impide continuar: no se hacen mas accesos
  afectados y se persisten pendientes con causa.
- El settle no devuelve cupos, no crea otro run_id y no abre prorroga.

Modo de ejecucion:
- ``--mode local`` (por defecto): requiere endpoints loopback explicitos
  (127.0.0.1/localhost) y RECHAZA endpoints publicos antes de cualquier envio.
- ``--mode public``: requiere activacion adicional ``--activar-publico``.
- ``--budget-only``: no realiza acceso de red ni de mercado.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from microstructure_probe import discovery  # noqa: E402
from microstructure_probe.book import BookEngine  # noqa: E402
from microstructure_probe.flow import FlowEngine  # noqa: E402
from microstructure_probe.history_client import (  # noqa: E402
    ASSUMED_WEIGHTS,
    INTERVAL_MS,
    HistoryClient,
    RateLimitExceeded,
    UpstreamBudgetExceeded,
)
from microstructure_probe.history_store import HistoryStore  # noqa: E402
from microstructure_probe.research_recorder import ResearchRecorder  # noqa: E402
from microstructure_probe.universe import SymbolUniverse  # noqa: E402

import research_selector  # noqa: E402

PILOT_VERSION = "research-pilot-v1"
PROTOCOL_VERSION = "prospective-protocol-v1"
POLICY_VERSION = research_selector.POLICY_VERSION

DEFAULT_HORIZONS: Tuple[Tuple[str, int], ...] = (
    ("5m", 300_000),
    ("15m", 900_000),
    ("60m", 3_600_000),
)

# Pesos oficiales usados por el presupuesto (ver doc, seccion 9.7):
# exchangeInfo=1, ticker/24hr sin symbol=40, klines limit<100=1.
WEIGHT_EXCHANGE_INFO = 1
WEIGHT_TICKER_24H = 40
WEIGHT_KLINES = 1

STATE_OBSERVADA = "observada"
STATE_DESCARTADA = "descartada"

OUTCOME_RESUELTO = "resuelto"
OUTCOME_NO_EVALUABLE = "no_evaluable"
OUTCOME_PENDIENTE = "pendiente"

# Tolerancia de coherencia de reloj: un evento adelantado mas de esto al reloj
# del piloto se registra como patologia, nunca se recorta en silencio.
FUTURE_EVENT_TOLERANCE_MS = 1_000

# Hosts considerados loopback para el modo local.
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


# ---------------------------------------------------------------------------
# Utilidades puras (probadas sin red)
# ---------------------------------------------------------------------------

def ceil_ms(value_ms: int, step_ms: int) -> int:
    """Primer multiplo de ``step_ms`` >= ``value_ms`` (alineacion al alza)."""
    if step_ms <= 0:
        raise ValueError("step_ms must be positive")
    return -(-int(value_ms) // int(step_ms)) * int(step_ms)


def iso_utc(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()


def parse_horizons(spec: str) -> Tuple[Tuple[str, int], ...]:
    """``"5m=300000,15m=900000"`` -> ((label, ms), ...). Orden estable."""
    out: List[Tuple[str, int]] = []
    for chunk in str(spec).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(f"horizonte invalido (falta '='): {chunk}")
        label, raw = chunk.split("=", 1)
        label = label.strip()
        try:
            ms = int(raw)
        except ValueError as exc:
            raise ValueError(f"horizonte invalido (ms): {chunk}") from exc
        if not label or ms <= 0:
            raise ValueError(f"horizonte invalido: {chunk}")
        out.append((label, ms))
    if not out:
        raise ValueError("se requiere al menos un horizonte")
    return tuple(out)


def horizons_to_spec(horizons: Tuple[Tuple[str, int], ...]) -> str:
    return ",".join(f"{label}={ms}" for label, ms in horizons)


def build_observation_id(symbol: str, decision_ms: int) -> str:
    return f"{str(symbol).upper()}|{int(decision_ms)}"


def classify_event_clock(event_ms: Optional[int], reference_ms: int) -> str:
    """Coherencia evento/reloj: 'ok' | 'desconocido' | 'evento_futuro'."""
    if event_ms is None:
        return "desconocido"
    if int(event_ms) > int(reference_ms) + FUTURE_EVENT_TOLERANCE_MS:
        return "evento_futuro"
    return "ok"


def es_loopback(url: Optional[str]) -> bool:
    """True si el host de la URL es loopback (127.0.0.1/localhost/::1)."""
    if not url:
        return False
    try:
        host = urlsplit(url).hostname
    except Exception:
        return False
    return host in LOOPBACK_HOSTS


# ---------------------------------------------------------------------------
# Reloj
# ---------------------------------------------------------------------------

class SystemClock:
    mode = "system"

    def now_ms(self) -> int:
        return int(time.time() * 1000)


class ManualClock:
    """Reloj de prueba: lee el instante de un fichero (ms epoch).

    Solo para pruebas de cadena completa; no se usa en produccion. Un fichero
    ausente o ilegible es un error explicito (nunca un instante inventado).
    """

    mode = "manual"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def now_ms(self) -> int:
        last_error: Optional[Exception] = None
        for _ in range(5):
            try:
                raw = self.path.read_text(encoding="utf-8").strip()
                return int(raw)
            except (OSError, ValueError) as exc:
                last_error = exc
                time.sleep(0.02)
        raise RuntimeError(f"reloj manual ilegible: {self.path}") from last_error


def build_clock(mode: str, clock_file: Optional[str]) -> Any:
    if mode == "system":
        return SystemClock()
    if mode == "manual":
        if not clock_file:
            raise ValueError("--clock manual requiere --clock-file")
        return ManualClock(Path(clock_file))
    raise ValueError(f"modo de reloj desconocido: {mode}")


# ---------------------------------------------------------------------------
# Puerta de presupuesto efectiva (HistoryClient.attempt_gate)
# ---------------------------------------------------------------------------

class RunBudget:
    """Puerta de presupuesto efectiva para HistoryClient.attempt_gate.

    Reserva cada intento HTTP ANTES del transporte. Impone maximos explicitos
    de intentos totales, reintentos totales y peso acumulado. Cuando se agota
    alguna cota, bloquea antes de enviar y el siguiente intento se rechaza
    sin abrir conexion.
    """

    def __init__(
        self,
        max_attempts: int,
        max_retries: int,
        max_weight: int,
    ) -> None:
        self.max_attempts = max(0, int(max_attempts))
        self.max_retries = max(0, int(max_retries))
        self.max_weight = max(0, int(max_weight))
        self.attempts = 0
        self.retries = 0
        self.weight = 0
        self.blocked = False
        self.reason: Optional[str] = None

    def weight_of(self, endpoint: str) -> int:
        ep = (endpoint or "").lower()
        if "/fapi/v1/ticker/24hr" in ep:
            return 40
        if "/fapi/v1/exchangeinfo" in ep:
            return 1
        if "/fapi/v1/time" in ep:
            return 1
        if "/fapi/v1/klines" in ep or "/fapi/v1/markpriceklines" in ep:
            return 1
        return 1

    def before_send(self, entry: Dict[str, Any]) -> None:
        if self.blocked:
            raise UpstreamBudgetExceeded(self.reason or "presupuesto_agotado")
        ep = str(entry.get("endpoint", ""))
        w = self.weight_of(ep)
        if self.attempts + 1 > self.max_attempts:
            self.blocked = True
            self.reason = "presupuesto_intentos_agotado"
            raise UpstreamBudgetExceeded(self.reason)
        if self.weight + w > self.max_weight:
            self.blocked = True
            self.reason = "presupuesto_peso_agotado"
            raise UpstreamBudgetExceeded(self.reason)
        # Reservar ANTES del transporte.
        self.attempts += 1
        self.weight += w
        entry["_reserved_weight"] = w
        entry["_attempt_no"] = self.attempts

    def after_send(self, entry: Dict[str, Any]) -> None:
        result = str(entry.get("result", ""))
        if "retry" in result:
            self.retries += 1
            if self.retries > self.max_retries:
                self.blocked = True
                self.reason = "presupuesto_reintentos_agotado"

    def status(self) -> Dict[str, Any]:
        return {
            "attempts": self.attempts,
            "retries": self.retries,
            "weight": self.weight,
            "max_attempts": self.max_attempts,
            "max_retries": self.max_retries,
            "max_weight": self.max_weight,
            "blocked": self.blocked,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Almacenamiento acotado (JSONL + resumen desde lo persistido)
# ---------------------------------------------------------------------------

class PilotStore:
    """Append-only JSONL con tope de bytes. Sin base de datos nueva."""

    def __init__(self, path: Path, max_bytes: int) -> None:
        self.path = Path(path)
        self.max_bytes = max(0, int(max_bytes))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.bytes_written = 0
        self.rows_written = 0
        self.cap_reached = False
        self._fh = self.path.open("a", encoding="utf-8", newline="\n")

    def write(self, row: Dict[str, Any]) -> bool:
        if self.cap_reached:
            return False
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        encoded = len(payload.encode("utf-8"))
        if self.max_bytes and self.bytes_written + encoded > self.max_bytes:
            self.cap_reached = True
            return False
        self._fh.write(payload)
        self._fh.flush()
        self.bytes_written += encoded
        self.rows_written += 1
        return True

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _atomic_write(path: Path, text: str) -> None:
    """Escritura atomica (tmp + replace) para ficheros de sincronizacion."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0, "min": None, "max": None, "mean": None}
    return {
        "n": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


def build_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resumen calculado EXCLUSIVAMENTE desde las filas persistidas."""
    cycles = [r for r in rows if r.get("kind") == "ciclo"]
    obs = [r for r in rows if r.get("kind") == "observacion"]
    outs = [r for r in rows if r.get("kind") == "resultado"]

    by_motivo: Dict[str, int] = {}
    by_symbol: Dict[str, int] = {}
    by_estado: Dict[str, int] = {}
    apto = 0
    no_apto = 0
    for r in obs:
        estado = r.get("estado")
        by_estado[estado] = by_estado.get(estado, 0) + 1
        if r.get("apto_para_evaluacion"):
            apto += 1
        else:
            no_apto += 1
        for motivo in r.get("motivos") or []:
            by_motivo[motivo] = by_motivo.get(motivo, 0) + 1
        by_symbol[r["symbol"]] = by_symbol.get(r["symbol"], 0) + 1

    horizons: Dict[str, Dict[str, Any]] = {}
    for r in outs:
        h = r["horizon"]
        bucket = horizons.setdefault(
            h, {"resueltos": 0, "no_evaluable": 0, "pendiente": 0,
                "retornos": [], "desfases_ms": []})
        state = r.get("estado")
        if state == OUTCOME_RESUELTO:
            bucket["resueltos"] += 1
            if r.get("retorno") is not None:
                bucket["retornos"].append(float(r["retorno"]))
            if r.get("desfase_ms") is not None:
                bucket["desfases_ms"].append(float(r["desfase_ms"]))
        elif state == OUTCOME_NO_EVALUABLE:
            bucket["no_evaluable"] += 1
        else:
            bucket["pendiente"] += 1

    horizon_summary: Dict[str, Dict[str, Any]] = {}
    for h, bucket in horizons.items():
        horizon_summary[h] = {
            "resueltos": bucket["resueltos"],
            "no_evaluable": bucket["no_evaluable"],
            "pendiente": bucket["pendiente"],
            "retorno_fraccion": _stats(bucket["retornos"]),
            "desfase_ms": _stats(bucket["desfases_ms"]),
            "neto": "UNKNOWN (sin supuestos de ejecucion/costes)",
        }

    seguidos_peak = 0
    rotaciones = 0
    for c in cycles:
        seg = (c.get("seguimiento") or {})
        seguidos_peak = max(seguidos_peak, len(seg.get("seguidos") or []))
        rotaciones += len(seg.get("salidas") or [])

    return {
        "pilot_version": PILOT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "policy_version": POLICY_VERSION,
        "n_ciclos": len(cycles),
        "n_observaciones": len(obs),
        "n_observadas": by_estado.get(STATE_OBSERVADA, 0),
        "n_descartadas": by_estado.get(STATE_DESCARTADA, 0),
        "n_aptas_para_evaluacion": apto,
        "n_no_aptas_para_evaluacion": no_apto,
        "n_resultados": len(outs),
        "motivos": dict(sorted(by_motivo.items())),
        "por_simbolo": dict(sorted(by_symbol.items())),
        "por_estado": dict(sorted(by_estado.items())),
        "horizontes": horizon_summary,
        "seguidos_peak": seguidos_peak,
        "n_rotaciones_salida": rotaciones,
        "dedupe": {
            "flujo_duplicados": sum(
                int((r.get("integridad") or {}).get("dedupe_flujo") or 0)
                for r in obs),
            "libro_duplicados": sum(
                int((r.get("integridad") or {}).get("dedupe_libro") or 0)
                for r in obs),
        },
        "retorno_unidades": (
            "fraccion (0.01 = 1%); precio_base = libro_mid y "
            "precio_posterior = klines_apertura_1m (proxy de fuentes mixtas; "
            "no mark-to-mid, no P&L ejecutable)"
        ),
    }


# ---------------------------------------------------------------------------
# Transporte WS (fino, con reconexion; sin supervisor)
# ---------------------------------------------------------------------------

def build_stream_url(base: str, streams: List[str]) -> str:
    base = str(base).rstrip("/")
    joined = "/".join(streams)
    return f"{base}/stream?streams={joined}"


class StreamFeed:
    """Una conexion WS combinada con reconexion y contadores."""

    def __init__(self, name: str, url: str,
                 on_message: Callable[[str], None]) -> None:
        self.name = name
        self.url = url
        self.on_message = on_message
        self.connections = 0
        self.disconnects = 0
        self.reconnects = 0
        self.errors = 0
        self.messages = 0
        self.last_error: Optional[str] = None
        self.connected_now = False

    async def run(self, stop: asyncio.Event) -> None:
        import websockets

        delay = 1.0
        while not stop.is_set():
            try:
                async with websockets.connect(
                    self.url, open_timeout=10, close_timeout=5,
                    ping_interval=20, ping_timeout=20, max_queue=2048,
                ) as ws:
                    self.connections += 1
                    self.connected_now = True
                    delay = 1.0
                    async for raw in ws:
                        if stop.is_set():
                            break
                        self.messages += 1
                        try:
                            self.on_message(raw)
                        except Exception as exc:  # un mensaje malo no tumba el feed
                            self.errors += 1
                            self.last_error = f"handler: {type(exc).__name__}: {exc}"
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.errors += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
            finally:
                self.connected_now = False
                self.disconnects += 1
            if stop.is_set():
                break
            self.reconnects += 1
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            delay = min(delay * 2, 10.0)

    def status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "connections": self.connections,
            "disconnects": self.disconnects,
            "reconnects": self.reconnects,
            "errors": self.errors,
            "messages": self.messages,
            "last_error": self.last_error,
            "connected_now": self.connected_now,
            "url_shape": self.url.split("?")[0],
        }


# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

@dataclass
class PilotConfig:
    run_id: str
    out_dir: Path
    mode: str = "local"                 # "local" | "public"
    activar_publico: bool = False       # requerida para mode=="public"
    rest_base: str = "http://127.0.0.1"
    ws_public_base: str = "ws://127.0.0.1"
    ws_market_base: str = "ws://127.0.0.1"
    duration_seconds: float = 14_400.0   # 4 h de captura
    settle_seconds: float = 4_200.0      # 70 min para madurar 60m del ultimo ciclo
    cycle_seconds: float = 60.0
    selection_seconds: float = 300.0
    decision_delay_seconds: float = 5.0
    max_symbols: int = 20
    max_candidates: int = 12
    max_comparators: int = 8
    min_quote_volume_usdt: float = 1_000_000.0
    horizons: Tuple[Tuple[str, int], ...] = DEFAULT_HORIZONS
    price_interval: str = "1m"
    price_tolerance_ms: int = 90_000
    price_delay_ms: int = 2_000
    max_data_age_ms: int = 5_000
    max_observations: int = 20_000
    max_bytes: int = 128 * 1024 * 1024   # almacenamiento TOTAL (JSONL+SQLite+aux)
    max_messages: int = 5_000_000
    max_http_attempts: int = 2000
    max_http_retries: int = 50
    max_http_weight: int = 5000
    max_ws_reconnects: int = 20
    tick_ms: int = 500
    clock_mode: str = "system"
    clock_file: Optional[str] = None
    # Solo pruebas (requieren clock_mode == "manual"): observabilidad de
    # progreso y barrera explicita de evaluacion. Jamas alteran tolerancias.
    status_file: Optional[str] = None
    decision_gate_file: Optional[str] = None
    stop_file: Optional[str] = None
    keep_research_db: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "out_dir": str(self.out_dir),
            "mode": self.mode,
            "activar_publico": self.activar_publico,
            "rest_base": self.rest_base,
            "ws_public_base": self.ws_public_base,
            "ws_market_base": self.ws_market_base,
            "duration_seconds": self.duration_seconds,
            "settle_seconds": self.settle_seconds,
            "cycle_seconds": self.cycle_seconds,
            "selection_seconds": self.selection_seconds,
            "decision_delay_seconds": self.decision_delay_seconds,
            "max_symbols": self.max_symbols,
            "max_candidates": self.max_candidates,
            "max_comparators": self.max_comparators,
            "min_quote_volume_usdt": self.min_quote_volume_usdt,
            "horizons": horizons_to_spec(self.horizons),
            "price_interval": self.price_interval,
            "price_tolerance_ms": self.price_tolerance_ms,
            "price_delay_ms": self.price_delay_ms,
            "max_data_age_ms": self.max_data_age_ms,
            "max_observations": self.max_observations,
            "max_bytes": self.max_bytes,
            "max_messages": self.max_messages,
            "max_http_attempts": self.max_http_attempts,
            "max_http_retries": self.max_http_retries,
            "max_http_weight": self.max_http_weight,
            "max_ws_reconnects": self.max_ws_reconnects,
            "tick_ms": self.tick_ms,
            "clock_mode": self.clock_mode,
            "clock_file": self.clock_file,
            "status_file": self.status_file,
            "decision_gate_file": self.decision_gate_file,
            "stop_file": self.stop_file,
            "policy_version": POLICY_VERSION,
            "pilot_version": PILOT_VERSION,
            "protocol_version": PROTOCOL_VERSION,
        }


# ---------------------------------------------------------------------------
# Presupuesto (calculo puro, sin red)
# ---------------------------------------------------------------------------

def compute_budget(cfg: PilotConfig) -> Dict[str, Any]:
    """Presupuesto concreto de una corrida; distingue pico y acumulado.

    No presupuesta llamadas /time que el programa no realiza. Las cotas
    efectivas (intentos, reintentos, peso, WS, almacenamiento) se imponen
    en tiempo de ejecucion mediante RunBudget y los controles del piloto.
    """
    duration = max(0.0, float(cfg.duration_seconds))
    settle = max(0.0, float(cfg.settle_seconds))
    total_s = duration + settle
    cycles = int(math.ceil(duration / max(cfg.cycle_seconds, 1e-9))) if duration else 0
    selections = int(math.ceil(duration / max(cfg.selection_seconds, 1e-9))) if duration else 0
    symbols = int(cfg.max_symbols)
    n_horizons = len(cfg.horizons)

    observations_max = cycles * symbols
    klines_requests = observations_max * n_horizons

    weight_catalog = selections * WEIGHT_EXCHANGE_INFO
    weight_tickers = selections * WEIGHT_TICKER_24H
    weight_klines = klines_requests * WEIGHT_KLINES
    weight_total = weight_catalog + weight_tickers + weight_klines

    # Almacenamiento: JSONL + SQLite (buckets 1m/10s) + auxiliares (WAL/SHM).
    bytes_obs = 1_600
    bytes_outcome = 500
    bytes_bucket_row = 200
    bucket_rows = symbols * int(duration / 60.0) if duration else 0
    bucket_rows_10s = symbols * int(duration / 10.0) if duration else 0
    storage_jsonl = observations_max * bytes_obs + klines_requests * bytes_outcome
    storage_db = (bucket_rows * 2 + bucket_rows_10s) * bytes_bucket_row
    storage_aux = 2 * 65_536  # WAL + SHM aproximado
    storage_total = storage_jsonl + storage_db + storage_aux

    ws_streams_peak = symbols * 2  # depth20@100ms + aggTrade por simbolo
    ws_connections = 2             # /public (depth) + /market (aggTrade)
    rotations = selections
    ws_reconnects = ws_connections + rotations  # peor caso: cambio de set

    return {
        "version": PILOT_VERSION,
        "mode": cfg.mode,
        "supuestos": {
            "duracion_captura_s": duration,
            "periodo_settle_s": settle,
            "total_s": total_s,
            "ciclos_decision": cycles,
            "selecciones": selections,
            "simbolos_simultaneos_max": symbols,
            "horizontes": [label for label, _ in cfg.horizons],
            "pesos_oficiales": {
                "exchangeInfo": WEIGHT_EXCHANGE_INFO,
                "ticker_24hr_sin_symbol": WEIGHT_TICKER_24H,
                "klines_limit_1_100": WEIGHT_KLINES,
            },
            "pool_referencia": (
                "REQUEST_WEIGHT publicado en exchangeInfo.rateLimits y cabecera "
                "X-MBX-USED-WEIGHT-1M; medido previamente 2400/min (referencia, "
                "no garantia)"
            ),
            "nota": (
                "No se presupuestan llamadas /time (el programa no las realiza). "
                "El 5 % de reintentos es solo una referencia; el limite efectivo "
                "es max_http_retries."
            ),
        },
        "limites_efectivos": {
            "max_http_attempts": cfg.max_http_attempts,
            "max_http_retries": cfg.max_http_retries,
            "max_http_weight": cfg.max_http_weight,
            "max_ws_reconnects": cfg.max_ws_reconnects,
            "max_messages": cfg.max_messages,
            "max_bytes_almacenamiento": cfg.max_bytes,
        },
        "rest": {
            "endpoints": {
                "/fapi/v1/exchangeInfo": {
                    "llamadas": selections, "peso_unitario": WEIGHT_EXCHANGE_INFO,
                    "peso_total": weight_catalog},
                "/fapi/v1/ticker/24hr": {
                    "llamadas": selections, "peso_unitario": WEIGHT_TICKER_24H,
                    "peso_total": weight_tickers},
                "/fapi/v1/klines": {
                    "llamadas": klines_requests, "peso_unitario": WEIGHT_KLINES,
                    "peso_total": weight_klines,
                    "nota": "1 por observacion y horizonte; interval 1m, limit=1"},
            },
            "peso_total_estimado": weight_total,
        },
        "ws": {
            "conexiones_simultaneas": ws_connections,
            "endpoints": [cfg.ws_public_base, cfg.ws_market_base],
            "streams_pico": ws_streams_peak,
            "limite_streams_por_conexion": 1024,
            "limite_mensajes_entrantes_por_s": 10,
            "vida_maxima_conexion_s": 86_400,
            "reconexiones_acumuladas_previstas": ws_reconnects,
            "nota": (
                "depth20@100ms pertenece a /public; aggTrade a /market: son dos "
                "conexiones distintas (docs oficiales, aviso de rutas). "
                "El costo de rotacion cuenta dos conexiones por cambio de set."
            ),
        },
        "simbolos": {
            "simultaneos_max": symbols,
            "incluye_pendientes": True,
            "nota": ("los resultados pendientes no abren WS; solo consumen "
                     "consultas de klines sujetas al presupuesto HTTP"),
        },
        "almacenamiento": {
            "jsonl_bytes_previstos": storage_jsonl,
            "sqlite_bytes_previstos": storage_db,
            "auxiliares_bytes_previstos": storage_aux,
            "total_bytes_previstos": storage_total,
            "tope_configurado_bytes": cfg.max_bytes,
            "nota": (
                "El tope incluye JSONL, SQLite y sus archivos auxiliares. "
                "No se anuncia 128 MB totales si solo se limita el JSONL."
            ),
        },
        "interrupcion_y_limpieza": {
            "condiciones": [
                "duracion de captura agotada",
                "max_observaciones alcanzado",
                "tope de bytes (almacenamiento total) alcanzado",
                "max_mensajes WS alcanzado",
                "reconexiones WS acumuladas agotadas",
                "presupuesto HTTP agotado (intentos/peso/reintentos)",
                "senal externa (SIGINT/SIGTERM)",
            ],
            "limpieza": [
                "cancelar feeds WS y cerrar conexiones",
                "drenar ResearchRecorder (buckets abiertos como PARTIAL)",
                "escribir resultados pendientes como PENDING con motivo",
                "escribir manifiesto y resumen desde lo persistido",
            ],
        },
        "no_incluye": [
            "adquisicion de order book historico",
            "backfill de huecos",
            "ordenes, claves o endpoints privados",
            "llamadas /time (no realizadas por el programa)",
        ],
    }


# ---------------------------------------------------------------------------
# Piloto
# ---------------------------------------------------------------------------

class ResearchPilot:
    def __init__(self, cfg: PilotConfig, clock: Any = None) -> None:
        self.cfg = cfg
        self.clock = clock or build_clock(cfg.clock_mode, cfg.clock_file)
        self.out_dir = Path(cfg.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.obs_path = self.out_dir / "observaciones.jsonl"
        self.store = PilotStore(self.obs_path, cfg.max_bytes)
        self.db_path = self.out_dir / "research.db"
        self.history = HistoryStore(self.db_path)
        self.recorder = ResearchRecorder(
            db_path=self.db_path, run_id=cfg.run_id, enabled=True,
            clock_ms=self.clock.now_ms,
        )
        # Puerta de presupuesto efectiva: reserva cada intento HTTP antes del
        # transporte. Reutiliza HistoryClient y su attempt_gate existente.
        self.budget = RunBudget(
            cfg.max_http_attempts, cfg.max_http_retries, cfg.max_http_weight,
        )
        self.rest = HistoryClient(base_url=cfg.rest_base,
                                  attempt_gate=self.budget)
        self.policy = research_selector.ResearchPolicy(
            max_candidatos=cfg.max_candidates,
            max_comparadores=cfg.max_comparators,
            max_deep_analysis_total=cfg.max_symbols,
        )
        self.book: Optional[BookEngine] = None
        self.flow: Optional[FlowEngine] = None
        self.followed: List[str] = []
        self.roles: Dict[str, str] = {}
        self.selection_meta: Dict[str, Dict[str, Any]] = {}
        self.last_selection_reference_ms: Optional[int] = None
        self.last_book_recv: Dict[str, int] = {}
        self.last_flow_recv: Dict[str, int] = {}
        self.last_book_event: Dict[str, int] = {}
        self.last_flow_event: Dict[str, int] = {}
        self.last_book_u: Dict[str, int] = {}
        # Contadores ACEPTADOS por fuente (confirmacion de procesamiento).
        self.book_events: Dict[str, int] = {}
        self.flow_events: Dict[str, int] = {}
        self.flow_seen_ids: Dict[str, set] = {}
        self.flow_seen_order: Dict[str, List[int]] = {}
        self.dedupe_flow: Dict[str, int] = {}
        self.dedupe_book: Dict[str, int] = {}
        self.book_gaps: Dict[str, int] = {}
        self.pending: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._seen_observation_ids: set = set()
        self.outcomes_written = 0
        self.observations_written = 0
        self.cycles_run = 0
        self.evaluations_run = 0
        self.stop_reason: Optional[str] = None
        # Solo pruebas: snapshot de progreso y barrera de evaluacion.
        self.status_path: Optional[Path] = (
            Path(cfg.status_file) if cfg.status_file else None)
        self.gate_path: Optional[Path] = (
            Path(cfg.decision_gate_file) if cfg.decision_gate_file else None)
        self.stop_path: Optional[Path] = (
            Path(cfg.stop_file) if cfg.stop_file else None)
        self._phase = "captura"
        self.feeds: Dict[str, StreamFeed] = {}
        self.feed_tasks: List[asyncio.Task] = []
        self.feed_stop = asyncio.Event()
        self.feed_signature: Optional[Tuple[Tuple[str, ...], Tuple[str, ...]]] = None
        # Contadores acumulados de WS (no se reseten al reemplazar StreamFeed).
        self.ws_total_connections = 0
        self.ws_messages_total = 0
        self.ws_reconnects_total = 0
        self.started_ms = self.clock.now_ms()
        self.ended_ms: Optional[int] = None
        self.capture_end_ms = self.started_ms + int(cfg.duration_seconds * 1000)
        self.settle_end_ms = self.capture_end_ms + int(cfg.settle_seconds * 1000)

    # -- almacenamiento total ----------------------------------------------

    def _sqlite_bytes(self) -> int:
        total = 0
        for p in (self.db_path,
                  Path(str(self.db_path) + "-wal"),
                  Path(str(self.db_path) + "-shm")):
            try:
                if p.exists():
                    total += p.stat().st_size
            except OSError:
                pass
        return total

    def storage_bytes_total(self) -> int:
        """Almacenamiento total: JSONL + SQLite + archivos auxiliares."""
        return self.store.bytes_written + self._sqlite_bytes()

    def _storage_ok(self, extra_bytes: int = 0) -> bool:
        return (not self.cfg.max_bytes
                or self.storage_bytes_total() + extra_bytes <= self.cfg.max_bytes)

    # -- mensajes WS -------------------------------------------------------

    def _is_duplicate_trade(self, symbol: str, trade_id: Any) -> bool:
        try:
            tid = int(trade_id)
        except (TypeError, ValueError):
            return False
        seen = self.flow_seen_ids.setdefault(symbol, set())
        if tid in seen:
            self.dedupe_flow[symbol] = self.dedupe_flow.get(symbol, 0) + 1
            return True
        seen.add(tid)
        order = self.flow_seen_order.setdefault(symbol, [])
        order.append(tid)
        if len(order) > 50_000:  # cota de memoria; nunca crece sin limite
            old = order.pop(0)
            seen.discard(old)
        return False

    def handle_message(self, raw: Any) -> None:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            return
        stream = str(envelope.get("stream") or "")
        data = envelope.get("data")
        if not isinstance(data, dict):
            return
        symbol = str(data.get("s") or "").upper()
        if not symbol:
            return
        if symbol not in self.followed:
            return
        recv_ms = self.clock.now_ms()

        if stream.endswith("@aggTrade"):
            if self._is_duplicate_trade(symbol, data.get("a")):
                return
            event_ms = data.get("E")
            price = data.get("p")
            qty = data.get("q")
            maker = data.get("m")
            if self.flow is not None:
                accepted = self.flow.ingest(symbol, event_ms, float(price),
                                            float(qty), maker, data.get("nq"))
                if accepted:
                    self.last_flow_recv[symbol] = recv_ms
                    self.last_flow_event[symbol] = int(event_ms)
                    self.flow_events[symbol] = self.flow_events.get(symbol, 0) + 1
                    self.recorder.record_trade(symbol, int(event_ms),
                                               float(price), float(qty), maker)
            return

        if "@depth" in stream:
            update_id = data.get("u")
            prev_id = data.get("pu")
            try:
                uid = int(update_id)
            except (TypeError, ValueError):
                uid = None
            last = self.last_book_u.get(symbol)
            if uid is not None and last is not None and uid <= last:
                self.dedupe_book[symbol] = self.dedupe_book.get(symbol, 0) + 1
                return
            gap = (prev_id is not None and last is not None
                   and int(prev_id) != last)
            if gap:
                self.book_gaps[symbol] = self.book_gaps.get(symbol, 0) + 1
            if self.book is not None:
                accepted = self.book.ingest(symbol, data.get("E"), update_id,
                                            prev_id, data.get("b"), data.get("a"))
                if accepted:
                    if uid is not None:
                        self.last_book_u[symbol] = uid
                    self.last_book_recv[symbol] = recv_ms
                    self.last_book_event[symbol] = int(data.get("E"))
                    self.book_events[symbol] = self.book_events.get(symbol, 0) + 1
                    state = self.book._books.get(symbol)
                    features = state.features if state is not None else None
                    if features:
                        self.recorder.record_book(
                            symbol, int(data.get("E")), features,
                            degraded=bool(state.degraded), gap=bool(gap),
                            crossed=bool(features.get("crossed")))

    # -- feeds ---------------------------------------------------------

    def _desired_streams(self) -> Tuple[List[str], List[str]]:
        public: List[str] = []
        market: List[str] = []
        for sym in sorted(self.followed):
            low = sym.lower()
            public.append(f"{low}@depth20@100ms")
            market.append(f"{low}@aggTrade")
        return public, market

    async def _stop_feeds(self) -> None:
        self.feed_stop.set()
        for task in self.feed_tasks:
            task.cancel()
        if self.feed_tasks:
            await asyncio.gather(*self.feed_tasks, return_exceptions=True)
        self.feed_tasks = []
        self.feed_stop = asyncio.Event()

    async def _restart_feeds(self) -> None:
        public, market = self._desired_streams()
        signature = (tuple(public), tuple(market))
        if signature == self.feed_signature:
            return
        # Acumular contadores del feed que se reemplaza (no se reseten).
        self.ws_total_connections += sum(
            f.connections for f in self.feeds.values())
        self.ws_messages_total += sum(
            f.messages for f in self.feeds.values())
        self.ws_reconnects_total += sum(
            f.reconnects for f in self.feeds.values())
        await self._stop_feeds()
        if not public:
            self.feed_signature = signature
            return
        self.feeds = {
            "public": StreamFeed("public", build_stream_url(
                self.cfg.ws_public_base, public), self.handle_message),
            "market": StreamFeed("market", build_stream_url(
                self.cfg.ws_market_base, market), self.handle_message),
        }
        for feed in self.feeds.values():
            self.feed_tasks.append(asyncio.create_task(
                feed.run(self.feed_stop), name=f"pilot-{feed.name}"))
        self.feed_signature = signature

    # -- seleccion -----------------------------------------------------

    def run_cycle(self) -> Dict[str, Any]:
        now = self.clock.now_ms()
        exchange_info, _ = self.rest.exchange_info()
        tickers, _ = self.rest.get("/fapi/v1/ticker/24hr", {},
                                   WEIGHT_TICKER_24H)
        if not isinstance(tickers, list):
            raise ValueError("ticker/24hr inesperado")
        candidates = discovery.build_candidates(
            exchange_info, tickers, self.cfg.min_quote_volume_usdt,
            discovered_at_ms=self.clock.now_ms())
        catalog_rows = [{
            "symbol": c.symbol, "status": c.status,
            "contract_type": c.contract_type, "quote_asset": c.quote_asset,
            "eligible": c.eligible,
        } for c in candidates]
        cycle = research_selector.run_research_cycle(
            catalog_rows, candidates, self.policy,
            reference_ms=self.clock.now_ms())
        self.last_selection_reference_ms = cycle.reference_ms

        selected = [s.symbol for s in cycle.selected]
        comparators = [c["symbol"] for c in cycle.comparator]
        new_followed = sorted(set(selected) | set(comparators))
        if len(new_followed) > self.cfg.max_symbols:
            new_followed = new_followed[:self.cfg.max_symbols]

        # Conjunto explicito (sin expansion silenciosa).
        SymbolUniverse.from_list(
            new_followed, source="research_pilot_selection",
            reason=f"cycle {cycle.cycle_id}")

        prev = set(self.followed)
        new_set = set(new_followed)
        entradas = []
        for sym in sorted(new_set - prev):
            role = "candidate" if sym in selected else "comparator"
            entradas.append({"symbol": sym, "motivo": f"entra_{role}"})
        salidas = []
        for sym in sorted(prev - new_set):
            pending = sum(1 for (o, _h) in self.pending if o.startswith(f"{sym}|"))
            salidas.append({"symbol": sym, "motivo": "fuera_de_seleccion",
                            "decisiones_pendientes": pending})

        self.roles = {sym: ("candidate" if sym in selected else "comparator")
                      for sym in new_followed}
        self.selection_meta = {}
        for s in cycle.selected:
            self.selection_meta[s.symbol] = {
                "role": "candidate", "side": s.side,
                "priority": s.priority, "move_24h_pct": s.move_24h,
                "classification": s.classification,
            }
        for c in cycle.comparator:
            self.selection_meta[c["symbol"]] = {
                "role": "comparator", "side": None, "priority": None,
                "selection_probability": c.get("selection_probability"),
                "sampling_mechanism": c.get("sampling_mechanism"),
            }

        # Engines: alta/baja explicita; nunca se amplian solos.
        if self.book is None:
            self.book = BookEngine(symbols=tuple(new_followed))
            self.flow = FlowEngine(symbols=tuple(new_followed))
        else:
            for sym in new_followed:
                self.book.allow([sym])
                self.flow.allow([sym])
        for sym in sorted(prev - new_set):
            self.recorder.finalize_symbol(sym)
            self.book.forget(sym)
            self.flow.forget(sym)
            for cache in (self.last_book_recv, self.last_flow_recv,
                          self.last_book_event, self.last_flow_event,
                          self.last_book_u):
                cache.pop(sym, None)

        self.followed = new_followed
        self.cycles_run += 1

        row = {
            "kind": "ciclo",
            "cycle_id": cycle.cycle_id,
            "reference_ms": cycle.reference_ms,
            "reference_iso": cycle.reference_iso,
            "policy_version": cycle.policy_version,
            "universe": cycle.universe.to_dict(),
            "selected": cycle.to_dict()["selected"],
            "comparator": cycle.comparator,
            "exclusions": cycle.exclusions,
            "cycle_summary": cycle.cycle_summary,
            "seguimiento": {
                "entradas": entradas,
                "salidas": salidas,
                "seguidos": list(self.followed),
                "roles": dict(self.roles),
            },
            "datos_usados": {
                "catalogo": "/fapi/v1/exchangeInfo",
                "tickers": "/fapi/v1/ticker/24hr",
                "reference_ms": cycle.reference_ms,
                "catalog_is_historical_snapshot": False,
            },
            "state": cycle.state,
        }
        if not self.store.write(row):
            self.stop_reason = "presupuesto_bytes"
        return row

    # -- decisiones --------------------------------------------------------

    def _book_records(self, now: int) -> Dict[str, Dict[str, Any]]:
        if self.book is None:
            return {}
        return {r["symbol"]: r for r in self.book.snapshot_all(now)}

    def _flow_records(self, now: int) -> Dict[str, Dict[str, Any]]:
        if self.flow is None:
            return {}
        return {r["symbol"]: r for r in self.flow.snapshot_all(now)}

    def _frescura_fuente(self, recv_ms: Optional[int], event_ms: Optional[int],
                         now: int) -> bool:
        """True si la fuente está obsoleta respecto al instante real now."""
        if recv_ms is None:
            return True
        if (now - int(recv_ms)) > self.cfg.max_data_age_ms:
            return True
        if event_ms is not None and (now - int(event_ms)) > self.cfg.max_data_age_ms:
            return True
        return False

    def build_observation(self, symbol: str, now: int,
                          book_rec: Optional[Dict[str, Any]],
                          flow_rec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        # now es el instante REAL de evaluacion (decision_ms), nunca retrotraido.
        decision_ms = int(now)
        book_recv = self.last_book_recv.get(symbol)
        flow_recv = self.last_flow_recv.get(symbol)
        book_event = self.last_book_event.get(symbol)
        flow_event = self.last_flow_event.get(symbol)
        motivos: List[str] = []

        # Disponibilidad por fuente (registrada por separado, <= decision_ms).
        if book_recv is None:
            motivos.append("sin_libro")
        if flow_recv is None:
            motivos.append("sin_flujo")

        # Frescura INDEPENDIENTE por fuente: flujo reciente no rejuvenece libro
        # antiguo, ni al contrario.
        if book_recv is not None and self._frescura_fuente(book_recv, book_event, decision_ms):
            motivos.append("dato_obsoleto_libro")
        if flow_recv is not None and self._frescura_fuente(flow_recv, flow_event, decision_ms):
            motivos.append("dato_obsoleto_flujo")

        # Coherencia de reloj por fuente.
        if classify_event_clock(book_event, decision_ms) == "evento_futuro":
            motivos.append("evento_de_libro_posterior_al_reloj")
        if classify_event_clock(flow_event, decision_ms) == "evento_futuro":
            motivos.append("evento_de_flujo_posterior_al_reloj")

        # Calidad del libro.
        book_features = (book_rec or {}).get("book") or {}
        if book_rec and book_rec.get("degraded"):
            motivos.append("libro_degradado_por_hueco")
        if book_features.get("crossed"):
            motivos.append("libro_cruzado")
        mid = book_features.get("mid")
        if mid is None and book_recv is not None:
            motivos.append("libro_sin_mid")

        # Flujo: ventana completa y eventos en ventana.
        flow_h = (((flow_rec or {}).get("horizons") or {}).get("1m") or {})
        window_complete = bool(flow_h.get("warmup_complete")) if flow_rec is not None else False
        trades = int(flow_h.get("trades") or 0)
        if flow_rec is not None and not window_complete:
            motivos.append("flujo_ventana_incompleta")
        if flow_rec is not None and trades <= 0:
            motivos.append("flujo_sin_eventos_en_ventana")

        fatal = {
            "sin_libro", "sin_flujo",
            "dato_obsoleto_libro", "dato_obsoleto_flujo",
            "evento_de_libro_posterior_al_reloj",
            "evento_de_flujo_posterior_al_reloj",
            "libro_degradado_por_hueco", "libro_cruzado", "libro_sin_mid",
            "flujo_ventana_incompleta", "flujo_sin_eventos_en_ventana",
        }
        apto = not any(m in fatal for m in motivos) and mid is not None

        # Antiguedad de evento Y de recepción por fuente.
        age_book_event = (decision_ms - book_event) if book_event is not None else None
        age_book_recv = (decision_ms - book_recv) if book_recv is not None else None
        age_flow_event = (decision_ms - flow_event) if flow_event is not None else None
        age_flow_recv = (decision_ms - flow_recv) if flow_recv is not None else None

        depth = book_features.get("depth") or {}
        top20 = depth.get("top20") or {}
        conc = book_features.get("concentration") or {}
        bid_conc = conc.get("bid") or {}
        ask_conc = conc.get("ask") or {}

        meta = self.selection_meta.get(symbol) or {}
        seleccion_disponibilidad = self.last_selection_reference_ms
        return {
            "kind": "observacion",
            "observation_id": build_observation_id(symbol, decision_ms),
            "symbol": symbol,
            "role": meta.get("role", self.roles.get(symbol, "comparator")),
            "side": meta.get("side"),
            "seleccion": {
                "priority": meta.get("priority"),
                "move_24h_pct": meta.get("move_24h_pct"),
                "selection_probability": meta.get("selection_probability"),
                "policy_version": POLICY_VERSION,
                "disponibilidad_ms": seleccion_disponibilidad,
            },
            # Instante REAL de decision (evaluacion), no bucket_end.
            "decision_ms": decision_ms,
            "decision_iso": iso_utc(decision_ms),
            "regla_decision": (
                "decision_ms = instante real de evaluacion (reloj del piloto); "
                "todas las disponibilidades <= decision_ms; nunca bucket_end; "
                "nunca retrotraido"),
            "disponibilidad": {
                "libro_ms": book_recv,
                "flujo_ms": flow_recv,
                "seleccion_ms": seleccion_disponibilidad,
                "max_ms": decision_ms,
            },
            "estado": STATE_OBSERVADA if apto else STATE_DESCARTADA,
            "apto_para_evaluacion": apto,
            "motivos": motivos,
            # Precio inicial: mid del libro (fuente libro). Precio posterior:
            # apertura de vela 1m (fuente klines). Proxy de fuentes mixtas,
            # NO mark-to-mid ni P&L.
            "precio_base": mid,
            "precio_base_fuente": "libro_mid",
            "precio_base_event_ms": book_event,
            "precio_base_disponibilidad_ms": book_recv,
            "libro": {
                "event_ms": book_event,
                "received_ms": book_recv,
                "age_event_ms": age_book_event,
                "age_received_ms": age_book_recv,
                "spread_bps": book_features.get("spread_bps"),
                "imbalance_notional": book_features.get("imbalance_notional"),
                "imbalance_qty": book_features.get("imbalance_qty"),
                "microprice_displacement_bps": book_features.get(
                    "microprice_displacement_bps"),
                "bid_notional_top20": top20.get("bid_notional"),
                "ask_notional_top20": top20.get("ask_notional"),
                "bid_base_top20": top20.get("bid_base"),
                "ask_base_top20": top20.get("ask_base"),
                "bid_levels": top20.get("bid_levels"),
                "ask_levels": top20.get("ask_levels"),
                "bandas_cubiertas_bps": {
                    "bid": bid_conc.get("coverage_max_dist_bps"),
                    "ask": ask_conc.get("coverage_max_dist_bps"),
                },
            },
            "flujo": {
                "event_ms": flow_event,
                "received_ms": flow_recv,
                "age_event_ms": age_flow_event,
                "age_received_ms": age_flow_recv,
                "window_ms": flow_h.get("window_ms"),
                "buy_notional": flow_h.get("buy_notional"),
                "sell_notional": flow_h.get("sell_notional"),
                "delta": flow_h.get("signed_delta"),
                "delta_ratio": flow_h.get("delta_ratio"),
                "base_volume": flow_h.get("base_volume"),
                "trade_count": flow_h.get("trades"),
                "ventana_completa": window_complete,
                "source": "aggTrade",
            },
            "cobertura": {
                "libro_presente": bool(book_features),
                "flujo_presente": flow_rec is not None,
                "flujo_ventana_completa": window_complete,
                "libro_banda_5bps_cubierta": (
                    (bid_conc.get("coverage_max_dist_bps") or 0) >= 5.0
                    and (ask_conc.get("coverage_max_dist_bps") or 0) >= 5.0),
            },
            "integridad": {
                "libro_degradado": bool((book_rec or {}).get("degraded")),
                "libro_huecos": int((book_rec or {}).get("sequence_gaps") or 0),
                "libro_invalid_updates": int(
                    (book_rec or {}).get("invalid_updates") or 0),
                "libro_cruzado": bool(book_features.get("crossed")),
                "flujo_tarde": int((flow_rec or {}).get("dropped_late") or 0),
                "flujo_invalidos": int(
                    (flow_rec or {}).get("dropped_invalid") or 0),
                "dedupe_flujo": int(self.dedupe_flow.get(symbol, 0)),
                "dedupe_libro": int(self.dedupe_book.get(symbol, 0)),
                "huecos_detectados_en_feed": int(self.book_gaps.get(symbol, 0)),
            },
        }

    def take_decisions(self, now: int) -> int:
        """now es el instante real de evaluacion; decision_ms = now."""
        book_records = self._book_records(now)
        flow_records = self._flow_records(now)
        written = 0
        for symbol in list(self.followed):
            if self.store.cap_reached:
                self.stop_reason = "presupuesto_bytes"
                break
            if not self._storage_ok():
                self.stop_reason = "presupuesto_bytes"
                break
            obs = self.build_observation(symbol, now,
                                         book_records.get(symbol),
                                         flow_records.get(symbol))
            obs_id = obs["observation_id"]
            if obs_id in self._seen_observation_ids:
                continue
            if not self.store.write(obs):
                self.stop_reason = "presupuesto_bytes"
                break
            self._seen_observation_ids.add(obs_id)
            self.observations_written += 1
            written += 1
            if obs["apto_para_evaluacion"]:
                for label, horizon_ms in self.cfg.horizons:
                    target = int(obs["decision_ms"]) + int(horizon_ms)
                    self.pending[(obs_id, label)] = {
                        "observation_id": obs_id,
                        "symbol": symbol,
                        "horizon": label,
                        "horizon_ms": horizon_ms,
                        "decision_ms": int(obs["decision_ms"]),
                        "target_ms": target,
                        "precio_base": obs["precio_base"],
                    }
            if self.observations_written >= self.cfg.max_observations:
                self.stop_reason = "max_observaciones"
                break
        return written

    # -- resultados --------------------------------------------------------

    def _fetch_price(self, symbol: str, price_ts_ms: int) -> Optional[float]:
        step = INTERVAL_MS[self.cfg.price_interval]
        rows, _ = self.rest.klines(
            symbol, self.cfg.price_interval, price_ts_ms,
            price_ts_ms + step - 1, limit=1)
        if not rows:
            return None
        row = rows[0]
        try:
            open_time = int(row[0])
            price = float(row[1])
        except (TypeError, ValueError, IndexError):
            return None
        if open_time != price_ts_ms:
            return None
        if not math.isfinite(price) or price <= 0:
            return None
        return price

    async def resolve_due(self, now: int) -> int:
        if not self.pending:
            return 0
        step = INTERVAL_MS[self.cfg.price_interval]
        resolved = 0
        for key in list(self.pending):
            if self._terminal_stop():
                break
            if not self._storage_ok():
                self.stop_reason = "presupuesto_bytes"
                break
            item = self.pending[key]
            target = int(item["target_ms"])
            price_ts = ceil_ms(target, step)
            desfase = price_ts - target
            if now < price_ts + self.cfg.price_delay_ms:
                continue
            if desfase > self.cfg.price_tolerance_ms:
                self._write_outcome(item, OUTCOME_NO_EVALUABLE, {
                    "motivo": "desfase_sobre_tolerancia",
                    "price_ts_ms": price_ts, "desfase_ms": desfase,
                    "tolerancia_ms": self.cfg.price_tolerance_ms,
                })
                del self.pending[key]
                resolved += 1
                continue
            try:
                price = await asyncio.to_thread(
                    self._fetch_price, item["symbol"], price_ts)
            except RateLimitExceeded as exc:
                # Presupuesto HTTP agotado: no se envia nada mas. El resultado
                # queda PENDIENTE (finalize_pending) con causa, sin inventar
                # precio ni convertirlo en no evaluable.
                self.stop_reason = f"presupuesto_agotado: {exc}"
                break
            except Exception as exc:
                self._write_outcome(item, OUTCOME_NO_EVALUABLE, {
                    "motivo": f"error_consulta_precio: {type(exc).__name__}",
                    "price_ts_ms": price_ts, "desfase_ms": desfase,
                })
                del self.pending[key]
                resolved += 1
                continue
            if price is None:
                if now > target + self.cfg.price_tolerance_ms + step:
                    self._write_outcome(item, OUTCOME_NO_EVALUABLE, {
                        "motivo": "sin_vela_para_el_objetivo",
                        "price_ts_ms": price_ts, "desfase_ms": desfase,
                    })
                    del self.pending[key]
                    resolved += 1
                continue
            base = item.get("precio_base")
            ret = (price - base) / base if base else None
            self._write_outcome(item, OUTCOME_RESUELTO, {
                "price_ts_ms": price_ts,
                "precio": price,
                "desfase_ms": desfase,
                "antiguedad_ms": now - price_ts,
                "horizonte_efectivo_ms": price_ts - int(item["decision_ms"]),
                "retorno": ret,
                "retorno_unidades": "fraccion",
                "precio_base": base,
                "precio_base_fuente": "libro_mid",
                "precio_posterior": price,
                "precio_posterior_fuente": "klines_apertura_1m",
                "precio_posterior_ts_ms": price_ts,
                "neto": None,
                "neto_estado": "UNKNOWN",
                "neto_motivo": "sin supuestos de ejecucion ni costes",
            })
            del self.pending[key]
            resolved += 1
        return resolved

    def _write_outcome(self, item: Dict[str, Any], estado: str,
                       extra: Dict[str, Any]) -> None:
        if not self._storage_ok():
            self.stop_reason = "presupuesto_bytes"
            return
        row = {
            "kind": "resultado",
            "observation_id": item["observation_id"],
            "symbol": item["symbol"],
            "horizon": item["horizon"],
            "horizon_ms": item["horizon_ms"],
            "decision_ms": item["decision_ms"],
            "target_ms": item["target_ms"],
            "estado": estado,
        }
        row.update(extra)
        if self.store.write(row):
            self.outcomes_written += 1
        else:
            self.stop_reason = "presupuesto_bytes"

    def finalize_pending(self, now: int) -> None:
        cause = self._pending_cause()
        for key in list(self.pending):
            item = self.pending[key]
            step = INTERVAL_MS[self.cfg.price_interval]
            self._write_outcome(item, OUTCOME_PENDIENTE, {
                "motivo": cause,
                "price_ts_previsto_ms": ceil_ms(item["target_ms"], step),
            })
        self.pending.clear()

    def _pending_cause(self) -> str:
        """Causa real de los pendientes al cerrar (sin inventar estados)."""
        reason = self.stop_reason or ""
        if reason == "parada_operador":
            return "parada_operador"
        if reason.startswith("presupuesto_agotado"):
            return "presupuesto_agotado"
        if reason and reason != "duracion":
            return reason
        return "ventana_de_settle_agotada"

    def _terminal_stop(self) -> bool:
        """Parada que impide seguir madurando (duracion no es terminal)."""
        return bool(self.stop_reason) and self.stop_reason != "duracion"

    def request_stop(self, reason: str) -> None:
        """Registra una parada explicita; prevalece sobre el fin por duracion."""
        if self.stop_reason in (None, "duracion"):
            self.stop_reason = reason

    def _stop_file_requested(self) -> bool:
        return self.stop_path is not None and self.stop_path.exists()

    # -- sincronizacion de pruebas ----------------------------------------

    def _gate_decision_ms(self) -> Optional[int]:
        """Instante autorizado por la barrera (None si no hay/no es valida)."""
        if self.gate_path is None:
            return None
        try:
            raw = self.gate_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not raw:
            return None
        try:
            if raw.startswith("{"):
                return int(json.loads(raw)["decision_ms"])
            return int(raw)
        except (KeyError, TypeError, ValueError):
            return None

    def _fuente_status(self, cache_event: Dict[str, int],
                       cache_recv: Dict[str, int], now: int) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for sym in self.followed:
            event_ms = cache_event.get(sym)
            recv_ms = cache_recv.get(sym)
            out[sym] = {
                "event_ms": event_ms,
                "received_ms": recv_ms,
                "age_event_ms": (now - event_ms) if event_ms is not None else None,
                "age_received_ms": (now - recv_ms) if recv_ms is not None else None,
            }
        return out

    def _write_status(self) -> None:
        """Snapshot atomico de progreso (solo si --status-file esta definido)."""
        if self.status_path is None:
            return
        now = self.clock.now_ms()
        status = {
            "phase": self._phase,
            "now_ms": now,
            "started_ms": self.started_ms,
            "capture_end_ms": self.capture_end_ms,
            "settle_end_ms": self.settle_end_ms,
            "followed": list(self.followed),
            "roles": dict(self.roles),
            "cycles_run": self.cycles_run,
            "evaluations_run": self.evaluations_run,
            "observations_written": self.observations_written,
            "outcomes_written": self.outcomes_written,
            "pending": len(self.pending),
            "stop_reason": self.stop_reason,
            "gate_decision_ms": self._gate_decision_ms(),
            "book_events": dict(self.book_events),
            "flow_events": dict(self.flow_events),
            "book": self._fuente_status(
                self.last_book_event, self.last_book_recv, now),
            "flow": self._fuente_status(
                self.last_flow_event, self.last_flow_recv, now),
            "feeds": {
                name: {
                    "connected_now": feed.connected_now,
                    "connections": feed.connections,
                    "messages": feed.messages,
                }
                for name, feed in self.feeds.items()
            },
        }
        try:
            _atomic_write(self.status_path, json.dumps(
                status, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            # La observabilidad de prueba nunca detiene la captura.
            pass

    # -- bucle ---------------------------------------------------------

    async def run(self) -> Dict[str, Any]:
        self.recorder.start()
        next_selection = self.started_ms
        next_decision = self.started_ms + int(
            self.cfg.decision_delay_seconds * 1000)
        skipped_selections = 0
        tick_s = max(0.01, self.cfg.tick_ms / 1000.0)
        try:
            while True:
                if self._stop_file_requested():
                    self.request_stop("parada_operador")
                    break
                now = self.clock.now_ms()
                if now >= self.capture_end_ms:
                    self.stop_reason = self.stop_reason or "duracion"
                    break
                if self.stop_reason:
                    break
                if now >= next_selection:
                    try:
                        await asyncio.to_thread(self.run_cycle)
                    except RateLimitExceeded as exc:
                        self.stop_reason = f"presupuesto_agotado: {exc}"
                        break
                    if self._terminal_stop():
                        break
                    now = self.clock.now_ms()
                    await self._restart_feeds()
                    next_selection = now + int(self.cfg.selection_seconds * 1000)
                if now >= next_decision and self.followed:
                    # Barrera de evaluacion (solo pruebas con clock manual):
                    # sin barrera se mantiene el comportamiento productivo.
                    if self.gate_path is None or self._gate_decision_ms() == now:
                        self.take_decisions(now)
                        self.evaluations_run += 1
                        next_decision = now + int(self.cfg.cycle_seconds * 1000)
                if self.stop_reason:
                    break
                # Limites WS acumulados (incluidos feeds reemplazados).
                if (self.ws_messages_total
                        + sum(f.messages for f in self.feeds.values())
                        > self.cfg.max_messages):
                    self.stop_reason = "max_mensajes"
                    break
                if self.ws_reconnects_total + sum(
                        f.reconnects for f in self.feeds.values()
                    ) > self.cfg.max_ws_reconnects:
                    self.stop_reason = "max_reconexiones_ws"
                    break
                await self.resolve_due(now)
                self._write_status()
                await asyncio.sleep(tick_s)
            # Settle: presupuesto, plazo y cancelacion siguen vigentes.
            await self._stop_feeds()
            self._phase = "settle"
            while (self.clock.now_ms() < self.settle_end_ms
                   and self.pending
                   and not self._terminal_stop()):
                if self._stop_file_requested():
                    self.request_stop("parada_operador")
                    break
                await self.resolve_due(self.clock.now_ms())
                self._write_status()
                await asyncio.sleep(tick_s)
            self.finalize_pending(self.clock.now_ms())
        finally:
            await self._stop_feeds()
            try:
                self.recorder.stop_and_drain(timeout=10.0)
            except Exception:
                pass
            self.store.close()
            self.ended_ms = self.clock.now_ms()
            self._phase = "fin"
            self._write_status()
        summary = self._write_outputs(skipped_selections)
        return summary

    # -- salidas -------------------------------------------------------

    def _write_outputs(self, skipped_selections: int) -> Dict[str, Any]:
        rows = read_jsonl(self.obs_path)
        summary = build_summary(rows)
        summary.update({
            "run_id": self.cfg.run_id,
            "started_ms": self.started_ms,
            "started_iso": iso_utc(self.started_ms),
            "ended_ms": self.ended_ms,
            "ended_iso": iso_utc(self.ended_ms or self.started_ms),
            "stop_reason": self.stop_reason,
            "config": self.cfg.to_dict(),
            "rest": {
                "requests": self.rest.stats.requests,
                "retries": self.rest.stats.retries,
                "failures": self.rest.stats.failures,
                "weight_spent": self.rest.stats.weight_spent,
            },
            "presupuesto_http": self.budget.status(),
            "ws_connections_total": self.ws_total_connections + sum(
                f.connections for f in self.feeds.values()),
            "ws_messages_total": self.ws_messages_total + sum(
                f.messages for f in self.feeds.values()),
            "ws_reconnects_total": self.ws_reconnects_total + sum(
                f.reconnects for f in self.feeds.values()),
            "ws": {name: feed.status() for name, feed in self.feeds.items()},
            "almacenamiento": {
                "jsonl_bytes": self.store.bytes_written,
                "jsonl_rows": self.store.rows_written,
                "sqlite_bytes": self._sqlite_bytes(),
                "storage_bytes_total": self.storage_bytes_total(),
                "tope_bytes": self.cfg.max_bytes,
                "research_db": str(self.db_path) if self.cfg.keep_research_db else None,
            },
            "recorder": self.recorder.status(),
            "ciclos_saltados": skipped_selections,
            "estado": ("completo" if summary["n_observaciones"] > 0
                       else "insuficiente"),
            "limites": [
                "precio_base = libro_mid; precio_posterior = klines_apertura_1m; "
                "proxy de fuentes mixtas, no mark-to-mid, no P&L ejecutable",
                "sin supuestos de costes el neto es UNKNOWN",
                "no se declara ventaja, rentabilidad ni representatividad",
                "presupuesto HTTP efectivo (intentos/peso/reintentos) y "
                "almacenamiento total (JSONL+SQLite+aux)",
            ],
        })
        summary_path = self.out_dir / "resumen.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n", encoding="utf-8", newline="\n")

        manifest = {
            "run_id": self.cfg.run_id,
            "pilot_version": PILOT_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "policy_version": POLICY_VERSION,
            "config": self.cfg.to_dict(),
            "files": {},
            "git_head": _git_head(),
            "dataset_location": str(self.out_dir),
            "nota": ("dataset fuera de Git; se publican manifiesto, hashes y "
                     "muestra pequena"),
        }
        for name in ("observaciones.jsonl", "resumen.json"):
            path = self.out_dir / name
            if path.exists():
                manifest["files"][name] = {
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
        (self.out_dir / "manifiesto.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n", encoding="utf-8", newline="\n")
        summary["manifiesto"] = manifest
        return summary


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
            text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Piloto prospectivo de investigacion (sin ordenes, sin "
                    "endpoints privados)")
    p.add_argument("--run-id", default=None)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--mode", choices=("local", "public"), default="local",
                   help="modo local (loopback, default) o publico "
                   "(requiere --activar-publico)")
    p.add_argument("--activar-publico", action="store_true",
                   help="habilita modo publico (endpoints Binance)")
    p.add_argument("--rest-base", default="http://127.0.0.1")
    p.add_argument("--ws-public-base", default="ws://127.0.0.1")
    p.add_argument("--ws-market-base", default="ws://127.0.0.1")
    p.add_argument("--duration-seconds", type=float, default=14_400.0)
    p.add_argument("--settle-seconds", type=float, default=4_200.0)
    p.add_argument("--cycle-seconds", type=float, default=60.0)
    p.add_argument("--selection-seconds", type=float, default=300.0)
    p.add_argument("--decision-delay-seconds", type=float, default=5.0)
    p.add_argument("--max-symbols", type=int, default=20)
    p.add_argument("--max-candidates", type=int, default=12)
    p.add_argument("--max-comparators", type=int, default=8)
    p.add_argument("--min-quote-volume", type=float, default=1_000_000.0)
    p.add_argument("--horizons", default=horizons_to_spec(DEFAULT_HORIZONS))
    p.add_argument("--price-interval", default="1m")
    p.add_argument("--price-tolerance-ms", type=int, default=90_000)
    p.add_argument("--price-delay-ms", type=int, default=2_000)
    p.add_argument("--max-data-age-ms", type=int, default=5_000)
    p.add_argument("--max-observations", type=int, default=20_000)
    p.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    p.add_argument("--max-messages", type=int, default=5_000_000)
    p.add_argument("--max-http-attempts", type=int, default=2000)
    p.add_argument("--max-http-retries", type=int, default=50)
    p.add_argument("--max-http-weight", type=int, default=5000)
    p.add_argument("--max-ws-reconnects", type=int, default=20)
    p.add_argument("--tick-ms", type=int, default=500)
    p.add_argument("--clock", choices=("system", "manual"), default="system")
    p.add_argument("--clock-file", default=None)
    p.add_argument("--status-file", default=None,
                   help="snapshot de progreso (solo --clock manual)")
    p.add_argument("--decision-gate-file", default=None,
                   help="barrera de evaluacion (solo --clock manual)")
    p.add_argument("--stop-file", default=None,
                   help="parada explicita del operador (solo --clock manual)")
    p.add_argument("--budget-only", action="store_true",
                   help="calcula y escribe el presupuesto sin red")
    return p


def config_from_args(args: argparse.Namespace) -> PilotConfig:
    run_id = args.run_id or time.strftime("pilot-%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = Path(args.out_dir) if args.out_dir else (
        ROOT / "data" / "research_pilot" / run_id)

    # Separacion explicita local/publico.
    if args.mode == "local":
        for nombre, valor in (("rest-base", args.rest_base),
                              ("ws-public-base", args.ws_public_base),
                              ("ws-market-base", args.ws_market_base)):
            if not es_loopback(valor):
                raise ValueError(
                    f"modo local rechaza endpoint publico en --{nombre}: {valor}"
                )
    else:  # public
        if not args.activar_publico:
            raise ValueError(
                "modo publico requiere --activar-publico (activacion adicional)"
            )

    # Instrumentacion de sincronizacion: solo con reloj manual (pruebas).
    if args.clock != "manual" and (
            args.status_file or args.decision_gate_file or args.stop_file):
        raise ValueError(
            "--status-file/--decision-gate-file/--stop-file requieren "
            "--clock manual"
        )

    return PilotConfig(
        run_id=run_id,
        out_dir=out_dir,
        mode=args.mode,
        activar_publico=args.activar_publico,
        rest_base=args.rest_base,
        ws_public_base=args.ws_public_base,
        ws_market_base=args.ws_market_base,
        duration_seconds=args.duration_seconds,
        settle_seconds=args.settle_seconds,
        cycle_seconds=args.cycle_seconds,
        selection_seconds=args.selection_seconds,
        decision_delay_seconds=args.decision_delay_seconds,
        max_symbols=args.max_symbols,
        max_candidates=args.max_candidates,
        max_comparators=args.max_comparators,
        min_quote_volume_usdt=args.min_quote_volume,
        horizons=parse_horizons(args.horizons),
        price_interval=args.price_interval,
        price_tolerance_ms=args.price_tolerance_ms,
        price_delay_ms=args.price_delay_ms,
        max_data_age_ms=args.max_data_age_ms,
        max_observations=args.max_observations,
        max_bytes=args.max_bytes,
        max_messages=args.max_messages,
        max_http_attempts=args.max_http_attempts,
        max_http_retries=args.max_http_retries,
        max_http_weight=args.max_http_weight,
        max_ws_reconnects=args.max_ws_reconnects,
        tick_ms=args.tick_ms,
        clock_mode=args.clock,
        clock_file=args.clock_file,
        status_file=args.status_file,
        decision_gate_file=args.decision_gate_file,
        stop_file=args.stop_file,
    )


def _install_stop_handlers(pilot: "ResearchPilot") -> Dict[int, Any]:
    """SIGINT/SIGTERM/SIGBREAK -> parada limpia (sin KeyboardInterrupt)."""
    previous: Dict[int, Any] = {}

    def handler(signum, frame):  # noqa: ARG001
        pilot.request_stop("senal_externa")

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            previous[sig] = signal.signal(sig, handler)
        except (ValueError, OSError):
            continue
    return previous


def _restore_stop_handlers(previous: Dict[int, Any]) -> None:
    for sig, prev in previous.items():
        try:
            signal.signal(sig, prev)
        except (ValueError, OSError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = config_from_args(args)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    if args.budget_only:
        # No realiza acceso de red ni de mercado.
        budget = compute_budget(cfg)
        Path(cfg.out_dir).mkdir(parents=True, exist_ok=True)
        path = Path(cfg.out_dir) / "presupuesto.json"
        path.write_text(json.dumps(budget, ensure_ascii=False, indent=2,
                                   sort_keys=True) + "\n", encoding="utf-8",
                        newline="\n")
        print(json.dumps({"presupuesto": str(path),
                          "peso_total_estimado": budget["rest"]["peso_total_estimado"]},
                         ensure_ascii=False))
        return 0
    try:
        clock = build_clock(cfg.clock_mode, cfg.clock_file)
        pilot = ResearchPilot(cfg, clock=clock)
        previous = _install_stop_handlers(pilot)
        try:
            summary = asyncio.run(pilot.run())
        finally:
            _restore_stop_handlers(previous)
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
              file=sys.stderr)
        return 2
    print(json.dumps({
        "run_id": summary["run_id"],
        "estado": summary["estado"],
        "stop_reason": summary["stop_reason"],
        "observaciones": summary["n_observaciones"],
        "aptas": summary["n_aptas_para_evaluacion"],
        "no_aptas": summary["n_no_aptas_para_evaluacion"],
        "resultados": summary["n_resultados"],
        "out_dir": str(cfg.out_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
