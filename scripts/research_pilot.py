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
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from microstructure_probe import discovery  # noqa: E402
from microstructure_probe.book import BookEngine  # noqa: E402
from microstructure_probe.flow import (  # noqa: E402
    FLOW_HORIZONS_MS,
    FlowEngine,
)
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
from research_operativo_adapter import (  # noqa: E402
    OperativoAdapter, OperativoConfig, OperativoTradeResult,
    _vela_plenamente_conocida_en,
)
from microstructure_probe.backtest_offline import (  # noqa: E402
    FundingCalendar,
    FundingCoverage,
    FundingSettlement,
    funding_settlements_sha256,
)
from microstructure_probe.paper_lab_engine import (  # noqa: E402
    ENGINE_VERSION_PAPER, PaperCandle, PaperSessionConfig,
    RULE_CAUSAL_V1, create_session, evaluate_session, step_forward,
)

RULE_VERSION = RULE_CAUSAL_V1

PILOT_VERSION = "research-pilot-v2"
PROTOCOL_VERSION = "prospective-protocol-v1"
POLICY_VERSION = research_selector.POLICY_VERSION
# Horizonte de flujo que exige la observacion (build_observation usa 1m).
DECISION_FLOW_HORIZON = "1m"
# Espera maxima explicita (dentro del periodo de seguimiento) para completar la
# cobertura del primer corte. La ventana se mide con eventos observados, no con
# el instante de suscripcion, asi que el corte nominal puede adelantarse a la
# recepcion real: esta espera acota la reprogramacion sin extender la captura.
WARMUP_MAX_WAIT_MS = 60_000
# Reintento de comprobacion de cobertura dentro del mismo bucle (no hay otro
# planificador): evita evaluar antes de recibir y no consume la oportunidad.
COVERAGE_RECHECK_MS = 250

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
WEIGHT_FUNDING_RATE = 1

# Techos-operative del protocolo v2. ``--budget-only`` falla cerrado si una
# configuracion intenta ampliar cualquiera de estos cupos.
PROTOCOL_MAX_HTTP_ATTEMPTS = 2_000
PROTOCOL_MAX_HTTP_RETRIES = 50
PROTOCOL_MAX_HTTP_WEIGHT = 5_000
PROTOCOL_MAX_STORAGE_BYTES = 128 * 1024 * 1024
PROTOCOL_MAX_WS_RECONNECTS = 20
PROTOCOL_MAX_MESSAGES = 5_000_000
PROTOCOL_MAX_STREAMS_PER_CONNECTION = 1_024

# Reservas fisicas para escritura concurrente y auditoria de frontera.
MAX_HTTP_LEDGER_ROW_BYTES = 8_192
MAX_SQLITE_QUOTA_BYTES = 32 * 1024 * 1024
MAX_HTTP_LEDGER_QUOTA_BYTES = 16 * 1024 * 1024


# Funding real se consulta por observacion operativa apta. Como el simbolo
# seleccionado no se conoce de antemano, la peticion se hace despues de la
# decision y solo se usa para contabilidad. Una segunda consulta por
# observacion queda reservada para una repeticion acotada.
MAX_CONSULTAS_FUNDING_POR_OBS = 2
FUNDING_HISTORY_LOOKBACK_MS = 48 * 60 * 60 * 1000

# --- Metodo de funding: A observado / B contrato de cobertura ---------------
# A (observed-settlements): la contabilidad se completa con liquidaciones
# REALMENTE observadas, despues de una espera maxima acotada. No exige
# garantia de publicacion: exige ver la liquidacion. B (coverage-contract):
# funding-coverage/v1 con prueba de ausencia de venue; se conserva y queda
# diferido. La eleccion es explicita, nunca un fallback silencioso.
FUNDING_METHOD_OBSERVED = "observed-settlements"
FUNDING_METHOD_COVERAGE = "coverage-contract"
FUNDING_METHODS = (FUNDING_METHOD_OBSERVED, FUNDING_METHOD_COVERAGE)

# Espera contable (metodo A): plazo maximo y consultas acotadas.
# El plazo cubre UN intervalo maximo de funding (8 h en USD-M) mas un margen
# de publicacion; no presupone la cadencia de ningun simbolo: cada simbolo
# se planifica con la cadencia OBSERVADA en su propio historico.
FUNDING_ESPERA_MAX_SEGUNDOS = 32_400.0          # 9 h
FUNDING_ESPERA_GRACE_MS = 1_800_000              # 30 min tras el boundary
FUNDING_ESPERA_RECHECK_MS = 1_800_000            # 30 min entre reintentos
MAX_CONSULTAS_FUNDING_ESPERA_POR_SIMBOLO = 3

# /fapi/v1/fundingRate comparte un limite oficial de 500 peticiones cada
# 5 minutos con /fapi/v1/fundingInfo. Es un limite del endpoint, distinto del
# presupuesto general por peso de la ventana.
FUNDING_RATE_SHARED_LIMIT_5M = 500
FUNDING_RATE_SHARED_WINDOW_MS = 5 * 60 * 1000

STATE_OBSERVADA = "observada"
STATE_DESCARTADA = "descartada"

OUTCOME_RESUELTO = "resuelto"
OUTCOME_NO_EVALUABLE = "no_evaluable"
OUTCOME_PENDIENTE = "pendiente"

# Tolerancia de coherencia de reloj: un evento adelantado mas de esto al reloj
# del piloto se registra como patologia, nunca se recorta en silencio.
FUTURE_EVENT_TOLERANCE_MS = 1_000

_INTERVALO_RESOLVER_MS = 60_000  # minimo entre consultas de trayectoria (evita consultas en cada tick)

# Politica de consultas de trayectoria operativa (replay del experimento).
# - Una observacion se consulta cuando la trayectoria NECESARIA puede ya
#   estar disponible: decision_ms + horizon_ms + un paso (la serie 1m debe
#   sobrepasar el cierre del horizonte para que el motor cierre la exposicion
#   en el horizonte y no en open_at_end).
# - MAX_CONSULTAS_TRAYECTORIA_POR_OBS acota las PETICIONES REPETIDAS por
#   observacion (1 planificada + 1 repetida). Los REINTENTOS POR FALLO los
#   cuenta el cliente HTTP (max_http_retries) y se reservan aparte.
MAX_CONSULTAS_TRAYECTORIA_POR_OBS = 2

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
        self._funding_rate_attempts_5m: List[Tuple[float, str]] = []

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
        if "/fapi/v1/fundingrate" in ep:
            return WEIGHT_FUNDING_RATE
        return 1

    def before_send(self, entry: Dict[str, Any]) -> None:
        if self.blocked:
            raise UpstreamBudgetExceeded(self.reason or "presupuesto_agotado")
        ep = str(entry.get("endpoint", ""))
        w = self.weight_of(ep)
        retry_no = int(entry.get("retry") or 0)
        is_retry = retry_no > 0
        # El cupo de reintentos es global para la corrida. ``retry`` es el
        # numero de reintento dentro de una peticion, por lo que no puede
        # consumirse por comparacion directa con el maximo global.
        if is_retry and self.retries >= self.max_retries:
            self.blocked = True
            self.reason = "presupuesto_reintentos_agotado"
            raise UpstreamBudgetExceeded(self.reason)
        if self.attempts + 1 > self.max_attempts:
            self.blocked = True
            self.reason = "presupuesto_intentos_agotado"
            raise UpstreamBudgetExceeded(self.reason)
        if self.weight + w > self.max_weight:
            self.blocked = True
            self.reason = "presupuesto_peso_agotado"
            raise UpstreamBudgetExceeded(self.reason)
        if "/fapi/v1/fundingrate" in ep.lower():
            now = time.monotonic()
            self._funding_rate_attempts_5m = [
                item for item in self._funding_rate_attempts_5m
                if (now - item[0]) * 1000 < FUNDING_RATE_SHARED_WINDOW_MS
            ]
            if len(self._funding_rate_attempts_5m) >= FUNDING_RATE_SHARED_LIMIT_5M:
                self.blocked = True
                self.reason = "presupuesto_funding_rate_5m_agotado"
                raise UpstreamBudgetExceeded(self.reason)
            # Solo cuenta intentos que pueden abrir transporte. Una peticion
            # bloqueada por intento/peso/reintento no consume el limite 5 m.
            self._funding_rate_attempts_5m.append((now, ep))
        # Reservar ANTES del transporte.
        self.attempts += 1
        self.weight += w
        if is_retry:
            self.retries += 1
        entry["_reserved_weight"] = w
        entry["_attempt_no"] = self.attempts
        entry["_retry_reserved"] = is_retry

    def after_send(self, entry: Dict[str, Any]) -> None:
        # Los reintentos se reservan en ``before_send``. Contarlos aqui por
        # texto de resultado omitia los errores de conexion, que si reabren
        # transporte y consumen cupo global.
        return

    def status(self) -> Dict[str, Any]:
        return {
            "attempts": self.attempts,
            "retries": self.retries,
            "weight": self.weight,
            "max_attempts": self.max_attempts,
            "max_retries": self.max_retries,
            "max_weight": self.max_weight,
            "funding_rate_attempts_5m": len(self._funding_rate_attempts_5m),
            "funding_rate_shared_limit_5m": FUNDING_RATE_SHARED_LIMIT_5M,
            "blocked": self.blocked,
            "reason": self.reason,
        }


class RunStorageBudget:
    """Reserva atomica de bytes para todos los datos de una corrida.

    ``used_bytes`` contiene bytes ya persistidos. ``reserved_bytes`` contiene
    espacio separado todavia no escrito. Una reserva se rechaza antes de
    tocar disco si el total contado mas la reserva excede el tope.
    """

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max(0, int(max_bytes))
        self._lock = threading.RLock()
        self._used_bytes = 0
        self._reserved_bytes: Dict[str, int] = {}

    def seed_used(self, used_bytes: int) -> None:
        with self._lock:
            self._used_bytes = max(self._used_bytes, int(used_bytes))

    @property
    def used_bytes(self) -> int:
        with self._lock:
            return self._used_bytes

    @property
    def reserved_bytes(self) -> int:
        with self._lock:
            return sum(self._reserved_bytes.values())

    @property
    def accounted_bytes(self) -> int:
        with self._lock:
            return self._used_bytes + sum(self._reserved_bytes.values())

    def can_fit(self, extra_bytes: int = 0) -> bool:
        extra = max(0, int(extra_bytes))
        with self._lock:
            if not self.max_bytes:
                return True
            return (self._used_bytes + sum(self._reserved_bytes.values())
                    + extra) <= self.max_bytes

    def reserve(self, key: str, delta_bytes: int) -> bool:
        delta = max(0, int(delta_bytes))
        with self._lock:
            if not self.can_fit(delta):
                return False
            self._reserved_bytes[key] = (
                self._reserved_bytes.get(key, 0) + delta)
            return True

    def commit(self, key: str, actual_delta_bytes: int) -> None:
        actual = int(actual_delta_bytes)
        with self._lock:
            reserved = self._reserved_bytes.pop(key, 0)
            if actual > reserved:
                raise ValueError(
                    f"reserva de almacenamiento excedida en {key}: "
                    f"reservado={reserved}, real={actual}")
            self._used_bytes = max(0, self._used_bytes + actual)

    def release(self, key: str) -> None:
        with self._lock:
            self._reserved_bytes.pop(key, None)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "max_bytes": self.max_bytes,
                "used_bytes": self._used_bytes,
                "reserved_bytes": sum(self._reserved_bytes.values()),
                "accounted_bytes": (self._used_bytes
                                    + sum(self._reserved_bytes.values())),
            }


# ---------------------------------------------------------------------------
# Almacenamiento acotado (JSONL + resumen desde lo persistido)
# ---------------------------------------------------------------------------

class PilotStore:
    """Append-only JSONL con tope de bytes. Sin base de datos nueva."""

    def __init__(self, path: Path, max_bytes: int,
                 storage_budget: Optional[RunStorageBudget] = None,
                 storage_key: Optional[str] = None) -> None:
        self.path = Path(path)
        self.max_bytes = max(0, int(max_bytes))
        self.storage_budget = storage_budget
        self.storage_key = storage_key or str(self.path)
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
        if self.storage_budget is not None:
            if not self.storage_budget.reserve(self.storage_key, encoded):
                self.cap_reached = True
                return False
            try:
                self._fh.write(payload)
                self._fh.flush()
            except Exception:
                self.storage_budget.release(self.storage_key)
                raise
            self.storage_budget.commit(self.storage_key, encoded)
        else:
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


def _funding_regular_times(
    symbol: str, rows: List[Dict[str, Any]],
) -> List[int]:
    regular_times = sorted({
        int(row["fundingTime"])
        for row in rows
        if str(row.get("symbol", "")).upper() == symbol.upper()
        and row.get("fundingTime") is not None
        and str(row.get("rateType", "Regular")).lower() == "regular"
    })
    return regular_times


def _funding_delta_distribution(
    symbol: str, rows: List[Dict[str, Any]],
) -> Dict[str, int]:
    regular_times = _funding_regular_times(symbol, rows)
    counts: Dict[str, int] = {}
    for before, after in zip(regular_times, regular_times[1:]):
        delta = int(after - before)
        if delta > 0:
            counts[str(delta)] = counts.get(str(delta), 0) + 1
    return dict(sorted(counts.items(), key=lambda item: int(item[0])))


def _infer_funding_interval_ms(
    symbol: str, rows: List[Dict[str, Any]],
) -> Optional[int]:
    """Infer one nominal cadence from unambiguous REAL regular settlements.

    Special settlements remain chargeable events but do not define cadence.
    At least two equal regular deltas are required. Any conflicting regular
    delta leaves the cadence UNKNOWN, so a changed or skipped schedule cannot
    be certified by the smallest observed interval.
    """
    regular_times = _funding_regular_times(symbol, rows)
    deltas = [
        int(after - before)
        for before, after in zip(regular_times, regular_times[1:])
        if int(after - before) > 0
    ]
    if len(deltas) < 2:
        return None
    counts: Dict[int, int] = {}
    for delta in deltas:
        counts[delta] = counts.get(delta, 0) + 1
    repeated = [delta for delta, count in counts.items() if count >= 2]
    if len(repeated) != 1:
        return None
    interval = repeated[0]
    if any(delta != interval for delta in deltas):
        return None
    return interval


def _funding_calendar_from_rows(
    symbol: str, rows: List[Dict[str, Any]],
    coverage: Optional[FundingCoverage] = None,
) -> FundingCalendar:
    """Build the existing per-symbol FundingCalendar from realized rows."""
    settlements: List[FundingSettlement] = []
    for row in rows:
        if str(row.get("symbol", "")).upper() != symbol.upper():
            continue
        try:
            settlement_ms = int(row["fundingTime"])
            funding_rate = float(row["fundingRate"])
            rate_bps = funding_rate * 10_000.0
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"fila de funding invalida para {symbol}: {row!r}") from exc
        if not math.isfinite(rate_bps):
            raise ValueError(f"tasa de funding no finita para {symbol}")
        mark_price = None
        if row.get("markPrice") is not None:
            try:
                mark_price = float(row["markPrice"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"marca de funding invalida para {symbol}: {row!r}") from exc
            if not math.isfinite(mark_price):
                raise ValueError(f"marca de funding no finita para {symbol}")
        rate_type = (str(row["rateType"]).strip().lower()
                     if row.get("rateType") is not None else None)
        settlements.append(FundingSettlement(
            settlement_ms=settlement_ms,
            rate_bps=rate_bps,
            mark_price=mark_price,
            rate_type=rate_type,
            funding_rate=funding_rate,
        ))
    calendar = FundingCalendar(
        version="exchange-funding-history/v2",
        source="exchange-funding-history (Binance USD-M fundingRate)",
        interval_ms=_infer_funding_interval_ms(symbol, rows),
        settlements=tuple(settlements),
        symbol=symbol.upper(),
        coverage=coverage,
    )
    # normalized() falla cerrado ante el mismo timestamp con tasas distintas.
    calendar.normalized()
    return calendar


def _binance_funding_coverage(
    symbol: str,
    rows: List[Dict[str, Any]],
    start_ms: int,
    end_ms: int,
    request: Dict[str, Any],
    limit: int,
) -> FundingCoverage:
    """Construye la procedencia de una consulta Binance sin sobreacreditarla.

    La documentacion oficial de ``GET /fapi/v1/fundingRate`` no ofrece una
    garantia general de completitud ni un maximo de retraso de publicacion.
    Por eso una respuesta completa y no truncada conserva el estado UNKNOWN:
    acredita las filas observadas, no la ausencia de filas no devueltas.
    """
    provisional = _funding_calendar_from_rows(symbol, rows)
    ordered, _ = provisional.normalized()
    response_sha = request.get("response_sha256")
    if not isinstance(response_sha, str):
        response_sha = None
    row_symbols = sorted({str(row.get("symbol", "")).upper()
                          for row in rows if row.get("symbol")})
    truncated = len(rows) >= int(limit)
    foreign = [item for item in row_symbols if item != symbol.upper()]
    if truncated:
        status = "incomplete"
        reason = "response reached the requested limit and may be truncated"
    elif foreign:
        status = "incomplete"
        reason = "response contains rows for a different symbol: %s" % foreign
    else:
        status = "unknown"
        reason = (
            "Binance documents neither a completeness guarantee for "
            "fundingRate nor a maximum publication delay")
    params = dict(request.get("params") or {})
    params.setdefault("symbol", symbol.upper())
    params.setdefault("startTime", int(start_ms))
    params.setdefault("endTime", int(end_ms))
    params.setdefault("limit", int(limit))
    completed_value = request.get("completed_at_ms")
    completed_at = (int(completed_value)
                    if isinstance(completed_value, int)
                    and not isinstance(completed_value, bool) else None)
    status_value = request.get("http_status")
    http_status = (int(status_value)
                   if isinstance(status_value, int)
                   and not isinstance(status_value, bool) else None)
    coverage = FundingCoverage(
        version="funding-coverage/v1",
        status=status,
        symbol=symbol.upper(),
        venue="binance-usd-m",
        source="exchange-funding-history (Binance USD-M fundingRate)",
        interval_start_ms=int(start_ms),
        interval_end_ms=int(end_ms) + 1,
        acquired_at_ms=completed_at,
        available_at_ms=completed_at,
        method="binance-funding-rate-response",
        evidence={
            "kind": "venue-response",
            "reference": "/fapi/v1/fundingRate",
            "statement": (
                "rows observed for the requested symbol and inclusive time "
                "range; no completeness guarantee is claimed"),
            "sha256": response_sha,
            "valid_from_ms": int(start_ms),
            "valid_until_ms": int(end_ms) + 1,
        },
        request={
            "endpoint": "/fapi/v1/fundingRate",
            "params": params,
            "http_status": http_status,
            "sent_at_ms": request.get("sent_at_ms"),
            "completed_at_ms": request.get("completed_at_ms"),
        },
        response={
            "sha256": response_sha,
            "row_count": len(rows),
            "symbols": row_symbols,
            "pagination": {
                "pages": 1,
                "complete": not truncated,
                "truncated": truncated,
            },
            "settlement_sha256": funding_settlements_sha256(
                provisional.settlements),
            "first_settlement_ms": (
                ordered[0].settlement_ms if ordered else None),
            "last_settlement_ms": (
                ordered[-1].settlement_ms if ordered else None),
        },
        publication_delay_ms=None,
        publication_delay_evidence={
            "kind": "UNKNOWN",
            "reference": "Binance USD-M market-data documentation",
            "statement": (
                "no official maximum publication delay is documented for "
                "funding history"),
            "sha256": response_sha,
        },
        reason=reason,
    )
    return coverage


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


def _net_operating_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    values = [float(row["net_pnl"]) for row in rows
              if row.get("net_pnl") is not None]
    if not values:
        return {"n": 0, "suma_usdt": None, "media_usdt": None,
                "mediana_usdt": None, "min_usdt": None, "max_usdt": None}
    return {
        "n": len(values),
        "suma_usdt": sum(values),
        "media_usdt": sum(values) / len(values),
        "mediana_usdt": median(values),
        "min_usdt": min(values),
        "max_usdt": max(values),
    }


def _realized_drawdown(rows: List[Dict[str, Any]]) -> Optional[float]:
    values = [row for row in rows
              if row.get("net_pnl") is not None and row.get("exit_ms") is not None]
    if not values:
        return None
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for row in sorted(values, key=lambda item: (int(item["exit_ms"]),
                                               str(item.get("observation_id")))):
        equity += float(row["net_pnl"])
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def build_operational_economic_summary(
    persisted_rows: List[Dict[str, Any]],
    operational_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Economic metrics rebuilt only from persisted pilot/operation rows.

    Missing values remain absent. In particular, unknown funding is not added
    as zero and candidate/comparator means are emitted only when both groups
    have complete operations and the frozen cycle-coverage gate is satisfied.
    """
    cycles = [row for row in persisted_rows if row.get("kind") == "ciclo"]
    observations = [row for row in persisted_rows
                    if row.get("kind") == "observacion"]
    roles = ("candidate", "comparator")

    # Las metricas se reconstruyen desde operaciones unicas por observacion.
    # Si un fichero contiene una repeticion, la ultima fila persistida es la
    # autoridad y el duplicado queda contabilizado, no ponderado dos veces.
    operational_by_id: Dict[str, Dict[str, Any]] = {}
    operational_without_id = 0
    for index, row in enumerate(operational_rows):
        oid = str(row.get("observation_id") or "")
        if not oid:
            operational_without_id += 1
            oid = f"__sin_id_{index}"
        operational_by_id[oid] = row
    operational_duplicates = len(operational_rows) - len(operational_by_id)
    operational_rows = list(operational_by_id.values())

    selected = {role: 0 for role in roles}
    for cycle in cycles:
        selected["candidate"] += len(cycle.get("selected") or [])
        selected["comparator"] += len(cycle.get("comparator") or [])

    observed = {role: 0 for role in roles}
    apt = {role: 0 for role in roles}
    discarded = {role: 0 for role in roles}
    for row in observations:
        role = str(row.get("role") or "comparator")
        if role not in observed:
            observed[role] = 0
            apt[role] = 0
            discarded[role] = 0
        observed[role] += 1
        if row.get("apto_para_evaluacion"):
            apt[role] += 1
        else:
            discarded[role] += 1

    decisions = {str(row.get("decision") or "UNKNOWN"): 0
                 for row in operational_rows}
    for row in operational_rows:
        decision = str(row.get("decision") or "UNKNOWN")
        decisions[decision] = decisions.get(decision, 0) + 1
    signals = sum(1 for row in operational_rows
                  if row.get("direction") in ("LONG", "SHORT"))
    abstentions = decisions.get("SIN_ENTRADA", 0)
    capacity_rejections = decisions.get("RECHAZADA_CAPACIDAD", 0)
    simulated_operations = decisions.get("ENTRADA_EJECUTADA", 0)

    executed = [row for row in operational_rows
                if row.get("decision") == "ENTRADA_EJECUTADA"]
    closed = [row for row in executed
              if row.get("exit_executed") is True
              and row.get("entry_ms") is not None
              and row.get("exit_ms") is not None]
    still_open = [row for row in executed if row.get("open_at_end") is True]

    def _sum_field(rows: List[Dict[str, Any]], field: str) -> Optional[float]:
        values = [float(row[field]) for row in rows
                  if row.get(field) is not None]
        return sum(values) if values else None

    complete = [row for row in closed
                if row.get("neto_estado") == "COMPLETO"
                and row.get("net_pnl") is not None]
    conditioned = [row for row in closed
                   if row.get("neto_estado")
                   == "CONDICIONADO_SIN_FUNDING_COMPLETO"
                   and row.get("net_pnl") is not None]
    exposure_ms = sum(int(row["exit_ms"]) - int(row["entry_ms"])
                      for row in closed)

    # Cycle coverage uses the selection reference persisted in each
    # observation, not the later decision instant.
    cycles_both_roles_apt = 0
    for cycle in cycles:
        reference = cycle.get("reference_ms")
        apt_roles = {
            str(row.get("role"))
            for row in observations
            if row.get("apto_para_evaluacion")
            and (row.get("disponibilidad") or {}).get("seleccion_ms")
            == reference
        }
        if {"candidate", "comparator"}.issubset(apt_roles):
            cycles_both_roles_apt += 1
    coverage_ratio = (cycles_both_roles_apt / len(cycles)
                      if cycles else None)

    complete_by_role = {
        role: [row for row in complete if row.get("role") == role]
        for role in roles
    }
    selection_ms_by_oid = {
        str(row.get("observation_id")): (row.get("disponibilidad") or {}).get(
            "seleccion_ms")
        for row in observations
        if row.get("observation_id")
    }
    complete_by_cycle_role: Dict[Any, Dict[str, List[Dict[str, Any]]]] = {}
    for row in complete:
        cycle_reference = selection_ms_by_oid.get(
            str(row.get("observation_id")))
        role = str(row.get("role"))
        complete_by_cycle_role.setdefault(
            cycle_reference, {}).setdefault(role, []).append(row)
    cycles_complete_both_roles = []
    paired_differences = []
    for cycle in cycles:
        reference = cycle.get("reference_ms")
        by_role = complete_by_cycle_role.get(reference, {})
        if all(by_role.get(role) for role in roles):
            cycles_complete_both_roles.append(reference)
            candidate_mean = sum(
                float(row["net_pnl"]) for row in by_role["candidate"]
            ) / len(by_role["candidate"])
            comparator_mean = sum(
                float(row["net_pnl"]) for row in by_role["comparator"]
            ) / len(by_role["comparator"])
            paired_differences.append({
                "reference_ms": reference,
                "candidate_medio_usdt": candidate_mean,
                "comparator_medio_usdt": comparator_mean,
                "diferencia_usdt": candidate_mean - comparator_mean,
            })
    comparison_reasons = []
    if not complete_by_role["candidate"]:
        comparison_reasons.append("sin_operaciones_completas_candidate")
    if not complete_by_role["comparator"]:
        comparison_reasons.append("sin_operaciones_completas_comparator")
    if coverage_ratio is None or coverage_ratio < 0.5:
        comparison_reasons.append("cobertura_de_ciclos_ambos_roles_bajo_50pct")
    comparison: Dict[str, Any] = {
        "estado": "INSUFICIENTE",
        "motivos": comparison_reasons,
        "ciclos_total": len(cycles),
        "ciclos_con_ambos_roles_aptos": cycles_both_roles_apt,
        "cobertura_ciclos_ambos_roles": coverage_ratio,
        "operaciones_completas_candidate": len(complete_by_role["candidate"]),
        "operaciones_completas_comparator": len(complete_by_role["comparator"]),
        "ciclos_con_operaciones_completas_ambos_roles": len(
            cycles_complete_both_roles),
        "diferencias_paired_por_ciclo": paired_differences,
        "diferencia_paired_media_usdt": (
            sum(item["diferencia_usdt"] for item in paired_differences)
            / len(paired_differences) if paired_differences else None),
    }
    if not comparison_reasons:
        comparison["estado"] = "COMPARABLE"
        comparison["neto_por_operacion_candidate"] = _net_operating_stats(
            complete_by_role["candidate"])
        comparison["neto_por_operacion_comparator"] = _net_operating_stats(
            complete_by_role["comparator"])

    return {
        "fuente": ["observaciones.jsonl", "resultado_operativo.jsonl"],
        "diagnosticos": {
            "filas_operativas_leidas": len(operational_rows)
            + operational_duplicates,
            "filas_operativas_unicas": len(operational_rows),
            "duplicados_operativos_descartados": operational_duplicates,
            "filas_operativas_sin_observation_id": operational_without_id,
        },
        "definiciones": {
            "neto_por_operacion": ("net_pnl de operaciones cerradas divided by "
                                   "n; USDT; solo se publica neto COMPLETO o "
                                   "CONDICIONADO por separado"),
            "drawdown": ("max(peak_equity - equity) sobre net_pnl de salidas "
                         "cerradas ordenadas por exit_ms; no mark-to-market"),
            "exposicion": "suma(exit_ms - entry_ms) de operaciones cerradas",
            "comparacion": ("solo si ambos roles tienen operaciones COMPLETO y "
                            ">=50% de ciclos con ambos roles aptos"),
        },
        "embudo_por_rol": {
            role: {
                "seleccionadas": selected[role],
                "observadas": observed[role],
                "aptas": apt[role],
                "descartadas": discarded[role],
            } for role in roles
        },
        "decisiones": {
            "senales_con_direccion": signals,
            "abstenciones": abstentions,
            "rechazos_capacidad": capacity_rejections,
            "operaciones_ejecutadas_simuladas": simulated_operations,
            "por_decision": dict(sorted(decisions.items())),
        },
        "posiciones": {
            "cerradas": len(closed),
            "todavia_abiertas": len(still_open),
            "exposicion_realizada_ms": exposure_ms,
        },
        "resultado_usdt": {
            "bruto_operaciones_cerradas": _sum_field(closed, "gross_pnl"),
            "comisiones_operaciones_cerradas": _sum_field(closed, "fees"),
            "spread_slippage_operaciones_cerradas": _sum_field(
                closed, "spread_slip"),
            "funding_completamente_acreditado": _sum_field(complete, "funding"),
            "neto_completo": _net_operating_stats(complete),
            "neto_conditionado_sin_funding_completo": _net_operating_stats(
                conditioned),
            "drawdown_realizado_neto_completo_usdt": _realized_drawdown(
                complete),
            "drawdown_realizado_neto_conditionado_usdt": _realized_drawdown(
                conditioned),
        },
        "ganancias_perdidas": {
            "ganadoras_neto_completo": sum(
                1 for row in complete if float(row["net_pnl"]) > 0),
            "perdedoras_neto_completo": sum(
                1 for row in complete if float(row["net_pnl"]) < 0),
            "breakeven_neto_completo": sum(
                1 for row in complete if float(row["net_pnl"]) == 0),
            "ganadoras_neto_conditionado": sum(
                1 for row in conditioned if float(row["net_pnl"]) > 0),
            "perdedoras_neto_conditionado": sum(
                1 for row in conditioned if float(row["net_pnl"]) < 0),
            "breakeven_neto_conditionado": sum(
                1 for row in conditioned if float(row["net_pnl"]) == 0),
        },
        "comparacion_candidate_comparator": comparison,
    }


# ---------------------------------------------------------------------------
# Transporte WS (fino, con reconexion; sin supervisor)
# ---------------------------------------------------------------------------

# Categorias de trafico WS (Binance USD-M Futures). Aviso oficial de rutas
# (2026-03-06): '/public' sirve el libro de alta frecuencia (depth/bookTicker)
# y '/market' los datos de mercado (aggTrade, markPrice, kline...). Las URLs
# antiguas (wss://fstream.binance.com/stream) se retiraron el 2026-04-23.
# El mecanismo de suscripcion es por URL en modo stream (?streams=), el
# documentado para suscripciones combinadas: no se mezclan mensajes SUBSCRIBE.
WS_CATEGORIA_LIBRO = "public"
WS_CATEGORIA_FLUJO = "market"
WS_CATEGORIAS = (WS_CATEGORIA_LIBRO, WS_CATEGORIA_FLUJO)
WS_HOST_PUBLICO = "fstream.binance.com"
WS_STREAM_PATH = "/stream"


def normalizar_base_ws(base: str, categoria: str, *, contexto: str) -> str:
    """Valida la base WS y devuelve la base de la categoria esperada.

    Contrato EXACTO (falla cerrado con ValueError antes de abrir sockets):
      - raiz sin ruta ("wss://host" o "wss://host/"): se anade la categoria
        del feed,
      - ruta exacta "/public" o "/market" (barra final opcional): se conserva
        solo si corresponde al feed; la categoria contraria es categoria
        cruzada,
      - se rechazan prefijos o segmentos adicionales ("/otra/market"), rutas
        en mayusculas ("/MARKET"), '/stream' preincluido, query, fragmento y
        credenciales en la base.

    La categoria es intrinseca al feed (libro -> /public, flujo -> /market):
    el operador no puede cambiarla por accidente.
    """
    if categoria not in WS_CATEGORIAS:
        raise ValueError(
            f"{contexto}: categoria WS desconocida {categoria!r}; "
            f"categorias validas {WS_CATEGORIAS}")
    texto = str(base).strip()
    partes = urlsplit(texto)
    if partes.scheme not in ("ws", "wss"):
        raise ValueError(
            f"{contexto}: base WS invalida {texto!r}: se espera ws:// o wss://")
    if partes.username or partes.password or "@" in partes.netloc:
        raise ValueError(
            f"{contexto}: la base WS no puede llevar credenciales: {texto!r}")
    if partes.query:
        raise ValueError(
            f"{contexto}: la base WS no puede llevar query: {texto!r}")
    if partes.fragment:
        raise ValueError(
            f"{contexto}: la base WS no puede llevar fragmento: {texto!r}")
    if not partes.hostname:
        raise ValueError(f"{contexto}: base WS sin host: {texto!r}")
    ruta = partes.path
    # Raiz del host: se anade la categoria del feed.
    if ruta in ("", "/"):
        return f"{partes.scheme}://{partes.netloc}/{categoria}"
    # Ruta exacta de categoria (barra final opcional), en minusculas.
    for cat in WS_CATEGORIAS:
        if ruta in (f"/{cat}", f"/{cat}/"):
            if cat != categoria:
                raise ValueError(
                    f"{contexto}: categoria cruzada: la base {texto!r} es "
                    f"'{cat}' y esta conexion es '{categoria}'")
            return f"{partes.scheme}://{partes.netloc}/{cat}"
    # Diagnostico especifico para los rechazos ya conocidos.
    if ruta.rstrip("/") == WS_STREAM_PATH.strip("/"):
        raise ValueError(
            f"{contexto}: la base ya incluye '/stream' ({texto!r}); el "
            "constructor lo anade: no lo dupliques")
    if ruta.rstrip("/").lower() in WS_CATEGORIAS:
        raise ValueError(
            f"{contexto}: la ruta de la base debe ser exacta y en minusculas "
            f"('/public' o '/market'): {texto!r}")
    raise ValueError(
        f"{contexto}: base WS no compatible {texto!r}: se espera la raiz del "
        f"host o una ruta exacta '/public' o '/market', sin prefijos")


def build_stream_url(base: str, streams: List[str], categoria: str) -> str:
    """URL de stream combinado en la categoria de trafico correcta.

    Mecanismo: suscripcion por URL (modo stream, ``?streams=``), el documentado
    para suscripciones combinadas. No se anaden mensajes SUBSCRIBE.
    """
    base_norm = normalizar_base_ws(base, categoria, contexto="build_stream_url")
    limpio: List[str] = []
    for stream in streams:
        s = str(stream).strip()
        if not s:
            continue
        simbolo = s.split("@", 1)[0]
        if simbolo != simbolo.lower():
            raise ValueError(
                f"stream WS con simbolo no lowercase: {s!r} (se exige minuscula)")
        limpio.append(s)
    joined = "/".join(limpio)
    return f"{base_norm}{WS_STREAM_PATH}?streams={joined}"


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
    max_bytes: int = 128 * 1024 * 1024   # almacenamiento total de datos
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
    # "none": no se-automatico la adquisicion de funding. "exchange": cada
    # observacion operativa apta consulta el historico realizado del simbolo
    # por el mismo cliente, puerta y presupuesto. Un calendario externo solo
    # se usa en pruebas/local y no se mezcla con esta fuente.
    funding_source: str = "none"
    # Metodo de contabilidad de funding. "coverage-contract" (B): contrato
    # funding-coverage/v1, la cobertura se acredita con el veredicto de una
    # cobertura explicita. "observed-settlements" (A): la cobertura se
    # acredita con liquidaciones realmente observadas despues de una espera
    # maxima acotada; el contrato B no se modifica ni se degrada.
    funding_method: str = FUNDING_METHOD_COVERAGE
    # Espera contable (metodo A): plazo maximo en segundos y consultas
    # diferidas maximas por simbolo. 0 desactiva la espera (solo valido con
    # el metodo B o con funding_source="none").
    funding_wait_seconds: float = 0.0
    funding_wait_max_queries: int = MAX_CONSULTAS_FUNDING_ESPERA_POR_SIMBOLO
    # Protocolo de captura: 1 = evaluacion inmediata tras suscripcion;
    # 2 = calentamiento acotado antes de la primera evaluacion de un
    # simbolo (seleccionar -> suscribir -> acumular ventana -> evaluar);
    # 3 = el corte espera cobertura observada real (span de flujo y frescura de
    # ambas fuentes) con espera maxima acotada, sin consumir la oportunidad en
    # el corte nominal prematuro.
    capture_protocol_version: int = 3

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
            "funding_source": self.funding_source,
            "funding_method": self.funding_method,
            "funding_wait_seconds": self.funding_wait_seconds,
            "funding_wait_max_queries": self.funding_wait_max_queries,
            "capture_protocol_version": self.capture_protocol_version,
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
    espera = (max(0.0, float(cfg.funding_wait_seconds))
              if cfg.funding_method == FUNDING_METHOD_OBSERVED else 0.0)
    total_s = duration + settle + espera
    cycles = int(math.ceil(duration / max(cfg.cycle_seconds, 1e-9))) if duration else 0
    selections = int(math.ceil(duration / max(cfg.selection_seconds, 1e-9))) if duration else 0
    symbols = int(cfg.max_symbols)
    n_horizons = len(cfg.horizons)

    observations_max = cycles * symbols
    # Consultas de TRAYECTORIA operativa: UNA por observacion apta. La misma
    # serie 1m cubre entrada, gestion y salida (no hay una consulta de
    # entrada separada en la politica ejecutada). Se programa cuando la
    # trayectoria del horizonte puede estar disponible, no en cada tick.
    # MAX_CONSULTAS_TRAYECTORIA_POR_OBS acota las peticiones repetidas: la
    # reserva adicional se contabiliza aparte de la estimacion base.
    klines_trayectoria = observations_max
    klines_trayectoria_reserva = observations_max * max(
        0, MAX_CONSULTAS_TRAYECTORIA_POR_OBS - 1)
    # Una llamada klines por observacion y horizonte (resolve_due de
    # resultados), una vez por objetivo y no en cada tick.
    klines_requests = observations_max * n_horizons
    klines_total = klines_trayectoria + klines_requests

    # Funding real. Metodo B (coverage-contract): una consulta por observacion
    # operativa apta, porque el simbolo se conoce en ese momento y no se
    # presupone una seleccion futura. Metodo A (observed-settlements): una
    # consulta DIFERIDA por simbolo con posicion abierta, porque el símbolo ya
    # esta observado y la consulta se programa cuando tiene sentido esperar
    # nueva evidencia (boundary posterior a la salida). Ninguno de los dos
    # presupone la cadencia de funding.
    funding_enabled = cfg.funding_source == "exchange"
    metodo_observado = (
        funding_enabled and cfg.funding_method == FUNDING_METHOD_OBSERVED)
    if metodo_observado:
        funding_calls = symbols
        funding_calls_reserve = symbols * max(
            0, int(cfg.funding_wait_max_queries) - 1)
        funding_log_rows = funding_calls + funding_calls_reserve
        funding_calendar_files = symbols
    else:
        funding_calls = observations_max if funding_enabled else 0
        funding_calls_reserve = (observations_max * max(
            0, MAX_CONSULTAS_FUNDING_POR_OBS - 1) if funding_enabled else 0)
        funding_log_rows = funding_calls
        funding_calendar_files = funding_calls

    weight_catalog = selections * WEIGHT_EXCHANGE_INFO
    weight_tickers = selections * WEIGHT_TICKER_24H
    weight_klines = klines_total * WEIGHT_KLINES
    weight_funding = funding_calls * WEIGHT_FUNDING_RATE
    weight_total = (weight_catalog + weight_tickers + weight_klines
                    + weight_funding)

    # Almacenamiento: JSONL de observaciones/resultados/funding, ledger HTTP,
    # SQLite (buckets 1m/10s) y auxiliares (WAL/SHM).
    bytes_obs = 1_600
    bytes_outcome = 500
    bytes_operativo = 1_200
    bytes_funding_log = 8_000
    bytes_funding_calendar = 4_000
    bytes_http_request = 700
    bytes_bucket_row = 200
    bucket_rows = symbols * int(duration / 60.0) if duration else 0
    bucket_rows_10s = symbols * int(duration / 10.0) if duration else 0
    storage_jsonl = (observations_max * bytes_obs
                     + klines_total * bytes_outcome
                     + observations_max * bytes_operativo
                     + funding_log_rows * bytes_funding_log)
    storage_funding_files = funding_calendar_files * bytes_funding_calendar
    storage_http_ledger = ((selections * 2 + klines_total + funding_calls
                            + klines_trayectoria_reserva
                            + funding_calls_reserve + cfg.max_http_retries)
                           * bytes_http_request)
    storage_db = (bucket_rows * 2 + bucket_rows_10s) * bytes_bucket_row
    storage_aux = 2 * 65_536  # WAL + SHM aproximado
    storage_total = (storage_jsonl + storage_funding_files
                     + storage_http_ledger + storage_db + storage_aux)

    # La primera seleccion abre los feeds; cada seleccion posterior puede
    # cambiar el set y reabrir AMBOS feeds (/public y /market).
    ws_connections = 2             # /public (depth) + /market (aggTrade)
    rotations = max(0, selections - 1) if symbols else 0
    ws_initial_openings = ws_connections if symbols else 0
    ws_rotation_openings = 2 * rotations
    ws_reconnect_cap = cfg.max_ws_reconnects
    # El tope se comprueba por tick: cada feed puede cruzarlo una vez antes
    # de la siguiente comprobacion (2 feeds como maximo).
    ws_reconnect_overshoot = min(2, ws_connections) if symbols else 0
    ws_total_openings_max = (ws_initial_openings + ws_rotation_openings
                             + ws_reconnect_cap
                             + ws_reconnect_overshoot)

    attempts_base = selections * 2 + klines_total + funding_calls
    attempts_with_reserves = (
        attempts_base + klines_trayectoria_reserva + funding_calls_reserve
        + cfg.max_http_retries)
    weight_with_reserves = (
        weight_total + klines_trayectoria_reserva * WEIGHT_KLINES
        + funding_calls_reserve * WEIGHT_FUNDING_RATE
        + cfg.max_http_retries * WEIGHT_TICKER_24H)
    funding_concentrated_raw = (
        symbols * max(0, MAX_CONSULTAS_FUNDING_POR_OBS - 1)
        + symbols + cfg.max_http_retries) if funding_enabled else 0
    if metodo_observado:
        # Las consultas diferidas se reparten por simbolo y por boundary
        # observado; el peor caso concentrado se calcula de forma
        # conservadora con todas las consultas de la ventana a la vez.
        funding_concentrated_raw = (
            symbols * max(0, int(cfg.funding_wait_max_queries) - 1)
            + symbols + cfg.max_http_retries)
    if cfg.max_bytes:
        runtime_sqlite_quota = min(
            MAX_SQLITE_QUOTA_BYTES, cfg.max_bytes // 4)
        runtime_ledger_quota = min(
            MAX_HTTP_LEDGER_QUOTA_BYTES, cfg.max_bytes // 4)
    else:
        runtime_sqlite_quota = MAX_SQLITE_QUOTA_BYTES
        runtime_ledger_quota = MAX_HTTP_LEDGER_QUOTA_BYTES
    storage_accounted_max = (
        storage_jsonl + storage_funding_files
        + runtime_sqlite_quota + runtime_ledger_quota)
    gate_checks = {
        "intentos_plan_dentro_del_techo": (
            attempts_with_reserves <= cfg.max_http_attempts),
        "intentos_no_amplian_protocolo": (
            cfg.max_http_attempts <= PROTOCOL_MAX_HTTP_ATTEMPTS),
        "peso_plan_dentro_del_techo": (
            weight_with_reserves <= cfg.max_http_weight),
        "peso_no_amplia_protocolo": (
            cfg.max_http_weight <= PROTOCOL_MAX_HTTP_WEIGHT),
        "reintentos_no_amplian_protocolo": (
            cfg.max_http_retries <= PROTOCOL_MAX_HTTP_RETRIES),
        "funding_rate_5m_dentro_del_limite": (
            funding_concentrated_raw <= FUNDING_RATE_SHARED_LIMIT_5M),
        "almacenamiento_dentro_del_techo": (
            not cfg.max_bytes or storage_total <= cfg.max_bytes),
        "almacenamiento_reservado_dentro_del_techo": (
            not cfg.max_bytes or storage_accounted_max <= cfg.max_bytes),
        "almacenamiento_no_amplia_protocolo": (
            cfg.max_bytes <= PROTOCOL_MAX_STORAGE_BYTES),
        "streams_por_conexion_dentro_del_limite": (
            symbols <= PROTOCOL_MAX_STREAMS_PER_CONNECTION),
        "reconexiones_no_amplian_protocolo": (
            cfg.max_ws_reconnects <= PROTOCOL_MAX_WS_RECONNECTS),
        "mensajes_no_amplian_protocolo": (
            cfg.max_messages <= PROTOCOL_MAX_MESSAGES),
        "cupo_simbolos_coherente": (
            cfg.max_candidates + cfg.max_comparators <= cfg.max_symbols),
    }
    budget_gate = {
        "cabe_en_limites": all(gate_checks.values()),
        "comprobaciones": gate_checks,
        "intentos_plan_con_reservas": attempts_with_reserves,
        "peso_plan_con_reservas": weight_with_reserves,
        "funding_maximo_concentrado_5m": funding_concentrated_raw,
        "almacenamiento_previsto_bytes": storage_total,
        "almacenamiento_reservado_max_bytes": storage_accounted_max,
    }

    return {
        "version": PILOT_VERSION,
        "mode": cfg.mode,
        "gate": budget_gate,
        "supuestos": {
            "duracion_captura_s": duration,
            "periodo_settle_s": settle,
            "espera_contable_max_s": espera,
            "duracion_maxima_total_s": total_s,
            "total_s": total_s,
            "funding_metodo": cfg.funding_method,
            "ciclos_decision": cycles,
            "selecciones": selections,
            "simbolos_simultaneos_max": symbols,
            "horizontes": [label for label, _ in cfg.horizons],
            "pesos_oficiales": {
                "exchangeInfo": WEIGHT_EXCHANGE_INFO,
                "ticker_24hr_sin_symbol": WEIGHT_TICKER_24H,
                "klines_limit_1_100": WEIGHT_KLINES,
                "fundingRate": WEIGHT_FUNDING_RATE,
            },
            "funding_source": cfg.funding_source,
            "pool_referencia": (
                "REQUEST_WEIGHT de exchangeInfo.rateLimits y cabecera "
                "X-MBX-USED-WEIGHT-1M; 2400/min por IP, UM y CM comparten "
                "pool (referencia, no garantia de disponibilidad)"
            ),
            "nota": (
                "No se presupuestan llamadas /time (el programa no las realiza). "
                "Los reintentos se reservan con max_http_retries (50), no con un "
                "5 % fijo; el limite efectivo es max_http_attempts/max_http_weight."
            ),
        },
        "limites_efectivos": {
            "max_http_attempts": cfg.max_http_attempts,
            "max_http_retries": cfg.max_http_retries,
            "max_http_weight": cfg.max_http_weight,
            "max_ws_reconnects": cfg.max_ws_reconnects,
            "max_messages": cfg.max_messages,
            "max_bytes_almacenamiento": cfg.max_bytes,
            "funding_rate_shared_limit_5m": FUNDING_RATE_SHARED_LIMIT_5M,
            "funding_rate_shared_window_ms": FUNDING_RATE_SHARED_WINDOW_MS,
        },
        "rest": {
            "endpoints": {
                "/fapi/v1/exchangeInfo": {
                    "llamadas": selections, "peso_unitario": WEIGHT_EXCHANGE_INFO,
                    "peso_total": weight_catalog},
                "/fapi/v1/ticker/24hr": {
                    "llamadas": selections, "peso_unitario": WEIGHT_TICKER_24H,
                    "peso_total": weight_tickers},
                "/fapi/v1/klines_trayectoria_operativa": {
                    "llamadas": klines_trayectoria, "peso_unitario": WEIGHT_KLINES,
                    "peso_total": klines_trayectoria * WEIGHT_KLINES,
                    "nota": "1 por observacion apta (la serie 1m cubre "
                            "entrada, gestion y salida; interval 1m). Se "
                            "consulta cuando la trayectoria del horizonte "
                            "puede estar disponible (decision + horizonte + "
                            "un paso), no en cada tick"},
                "/fapi/v1/klines_resultado_resolve": {
                    "llamadas": klines_requests, "peso_unitario": WEIGHT_KLINES,
                    "peso_total": klines_requests * WEIGHT_KLINES,
                    "nota": "1 por observacion y horizonte (resolve_due de "
                            "resultados; interval 1m, limit=1)"},
                "/fapi/v1/fundingRate": {
                    "llamadas": funding_calls,
                    "peso_unitario": WEIGHT_FUNDING_RATE,
                    "peso_total": weight_funding,
                    "nota": (
                        "1 por simbolo con posicion abierta cuando "
                        "--funding-method observed-settlements (A): la "
                        "consulta es diferida y se programa con la cadencia "
                        "OBSERVADA de ese simbolo; 1 por observacion "
                        "operativa apta con --funding-method coverage-contract "
                        "(B). En ambos casos consulta el historico realizado "
                        "del simbolo efectivamente investigado, despues de T y "
                        "solo para contabilidad. Limite compartido del "
                        "endpoint: 500/5 min")},
            },
            "estimacion_base": {
                "preparacion": {
                    "llamadas": selections * 2,
                    "peso": weight_catalog + weight_tickers,
                    "nota": "catalogo + tickers por seleccion"},
                "consultas_operativas": {
                    "llamadas": klines_trayectoria,
                    "peso": klines_trayectoria * WEIGHT_KLINES,
                    "nota": "trayectoria completa por observacion apta"},
                "resultados_por_horizonte": {
                    "llamadas": klines_requests,
                    "peso": klines_requests * WEIGHT_KLINES,
                    "nota": "1 precio posterior por observacion y horizonte"},
                "funding_real": {
                    "llamadas": funding_calls,
                    "peso": weight_funding,
                    "nota": ("historial realizado por simbolo observado; "
                             "0 si funding_source=none")},
                "intentos": selections * 2 + klines_total + funding_calls,
                "peso": weight_total,
            },
            "reservas": {
                "peticiones_repetidas_por_observacion": {
                    "max_por_observacion": max(
                        0, MAX_CONSULTAS_TRAYECTORIA_POR_OBS - 1),
                    "llamadas": klines_trayectoria_reserva,
                    "peso": klines_trayectoria_reserva * WEIGHT_KLINES,
                    "nota": "peticion REPETIDA (misma observacion consultada "
                            "en otro intervalo) cuando la trayectoria no fue "
                            "utilizable; distinta del reintento por fallo"},
                "peticiones_repetidas_funding_por_observacion": {
                    "max_por_unidad": (
                        max(0, int(cfg.funding_wait_max_queries) - 1)
                        if metodo_observado
                        else max(0, MAX_CONSULTAS_FUNDING_POR_OBS - 1)),
                    "unidad": "simbolo" if metodo_observado else "observacion",
                    "llamadas": funding_calls_reserve,
                    "peso": funding_calls_reserve * WEIGHT_FUNDING_RATE,
                    "nota": ("peticion repetida del historico real de funding "
                             "(metodo A: una por simbolo con posicion abierta; "
                             "metodo B: una por observacion operativa apta); "
                             "distinta del reintento por fallo")},
                "reintentos_por_fallo": {
                    "max_por_ventana": cfg.max_http_retries,
                    "llamadas": cfg.max_http_retries,
                    "peso_max": cfg.max_http_retries * WEIGHT_TICKER_24H,
                    "nota": "reintento del cliente HTTP ante fallo; se cuenta "
                            "aparte de las peticiones repetidas"},
                "intentos": (klines_trayectoria_reserva
                             + funding_calls_reserve + cfg.max_http_retries),
                "peso": (klines_trayectoria_reserva * WEIGHT_KLINES
                         + funding_calls_reserve * WEIGHT_FUNDING_RATE
                         + cfg.max_http_retries * WEIGHT_TICKER_24H),
            },
            "intentos_base": selections * 2 + klines_total + funding_calls,
            "reintentos_tope": cfg.max_http_retries,
            "intentos_base_mas_reintentos": (
                selections * 2 + klines_total + funding_calls
                + cfg.max_http_retries),
            "peso_base": weight_total,
            "peso_reserva_reintentos_max": (
                cfg.max_http_retries * WEIGHT_TICKER_24H),
            "peso_base_mas_reintentos_max": (
                weight_total + cfg.max_http_retries * WEIGHT_TICKER_24H),
            "peso_total_estimado": weight_total,
            "intentos_techo_efectivo": cfg.max_http_attempts,
            "peso_techo_efectivo": cfg.max_http_weight,
            "intentos_base_mas_reservas": (
                selections * 2 + klines_total + funding_calls
                + klines_trayectoria_reserva + funding_calls_reserve
                + cfg.max_http_retries),
            "peso_base_mas_reservas_max": (
                weight_total + klines_trayectoria_reserva * WEIGHT_KLINES
                + funding_calls_reserve * WEIGHT_FUNDING_RATE
                + cfg.max_http_retries * WEIGHT_TICKER_24H),
            "cabe_en_limites": (
                (selections * 2 + klines_total + funding_calls
                 + klines_trayectoria_reserva + funding_calls_reserve
                 + cfg.max_http_retries) <= cfg.max_http_attempts
                and (weight_total + klines_trayectoria_reserva * WEIGHT_KLINES
                     + funding_calls_reserve * WEIGHT_FUNDING_RATE
                     + cfg.max_http_retries * WEIGHT_TICKER_24H)
                <= cfg.max_http_weight),
            "nota_consultas_repetidas": (
                "La estimacion base cuenta UNA consulta de trayectoria por "
                "observacion apta (la politica las programa cuando la "
                "trayectoria del horizonte puede estar disponible), mas las "
                "consultas de resultados por horizonte y la preparacion. Las "
                "peticiones repetidas y los reintentos por fallo son "
                "reservas aparte: la estimacion base NO es un maximo "
                "garantizado, el limite efectivo es max_http_attempts/"
                "max_http_weight (2000/5000 en la configuracion congelada)."
            ),
        },
        "funding": {
            "fuente": cfg.funding_source,
            "metodo": cfg.funding_method,
            "consultas_base_ventana": funding_calls,
            "consultas_repetidas_reserva": funding_calls_reserve,
            "reintentos_por_fallo_compartidos": cfg.max_http_retries,
            "intentos_totales_reservados": (funding_calls
                                            + funding_calls_reserve
                                            + cfg.max_http_retries),
            "limite_compartido_endpoint_5m": FUNDING_RATE_SHARED_LIMIT_5M,
            "maximo_concentrado_5m_planificado": funding_concentrated_raw,
            "espera_contable_max_s": espera,
            "consultas_maximas_por_simbolo": (
                int(cfg.funding_wait_max_queries) if metodo_observado else 0),
            "nota": (
                "Metodo A (observed-settlements): una consulta diferida por "
                "simbolo con posicion abierta, programada con la cadencia "
                "OBSERVADA de ese simbolo mas un margen de publicacion; las "
                "repetidas quedan reservadas aparte y el plazo maximo de la "
                "espera no se prorroga nunca. Metodo B (coverage-contract): "
                "una consulta por observacion operativa apta con el contrato "
                "funding-coverage/v1. El limite de 500/5 min pertenece al "
                "endpoint; el maximo concentrado se calcula de forma "
                "conservadora. Las tasas se consultan despues de T y no "
                "pueden decidir la entrada."),
        },
        "ws": {
            "conexiones_simultaneas": ws_connections,
            "endpoints": [cfg.ws_public_base, cfg.ws_market_base],
            "categorias": {
                "public": WS_CATEGORIA_LIBRO,
                "market": WS_CATEGORIA_FLUJO,
            },
            "plantilla_url": {
                "public": (f"{cfg.ws_public_base}{WS_STREAM_PATH}"
                           "?streams=<simbolo>@depth20@100ms/..."),
                "market": (f"{cfg.ws_market_base}{WS_STREAM_PATH}"
                           "?streams=<simbolo>@aggTrade/..."),
            },
            "streams_pico_por_conexion": symbols,
            "streams_pico_total": symbols * 2,
            "limite_streams_por_conexion": 1024,
            "limite_mensajes_entrantes_por_s": 10,
            "vida_maxima_conexion_s": 86_400,
            "aperturas_iniciales": ws_initial_openings,
            "rotaciones_previstas": rotations,
            "aperturas_por_rotacion_max": ws_rotation_openings,
            "reaperturas_tras_desconexion_tope": ws_reconnect_cap,
            "sobregiro_reaperturas_por_tick_max": ws_reconnect_overshoot,
            "aperturas_totales_max": ws_total_openings_max,
            "mensajes_datos_tope": cfg.max_messages,
            "nota": (
                "depth20@100ms pertenece a /public; aggTrade a /market: son dos "
                "conexiones distintas (docs oficiales, aviso de rutas). "
                "Cada rotacion reabre ambos feeds: 2 aperturas por cambio. "
                "max_ws_reconnects cuenta reaperturas tras una desconexion o "
                "fallo (incluye cierres normales del servidor); no cuenta la "
                "apertura inicial ni las rotaciones deliberadas, y se comprueba "
                "por tick. max_messages cuenta solo mensajes de datos; los "
                "ping/pong de control no se contabilizan."
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
            "funding_calendar_bytes_previstos": storage_funding_files,
            "http_ledger_bytes_previstos": storage_http_ledger,
            "sqlite_bytes_previstos": storage_db,
            "auxiliares_bytes_previstos": storage_aux,
            "total_bytes_previstos": storage_total,
            "reserva_sqlite_bytes": runtime_sqlite_quota,
            "reserva_http_ledger_bytes": runtime_ledger_quota,
            "total_reservado_con_jsonl_bytes": storage_accounted_max,
            "tope_configurado_bytes": cfg.max_bytes,
            "margen_bytes": (cfg.max_bytes - storage_total
                             if cfg.max_bytes else None),
            "margen_reservado_bytes": (
                cfg.max_bytes - storage_accounted_max
                if cfg.max_bytes else None),
            "margen_porcentaje": (
                round(100.0 * (cfg.max_bytes - storage_total) / cfg.max_bytes, 2)
                if cfg.max_bytes else None),
            "nota": (
                "El tope incluye JSONL de datos, ledger HTTP, calendarios de "
                "funding, SQLite y sus auxiliares. Cada JSONL reserva sus "
                "bytes exactos antes de escribir; SQLite y el ledger tienen "
                "cuotas fisicas reservadas para evitar carreras. Los indices "
                "finales y el estado de progreso no forman parte del tope de "
                "datos de la ventana."
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
    def __init__(
        self,
        cfg: PilotConfig,
        clock: Any = None,
        funding_calendars: Optional[Dict[str, FundingCalendar]] = None,
        operativo_cfg: Optional[OperativoConfig] = None,
    ) -> None:
        self.cfg = cfg
        self.clock = clock or build_clock(cfg.clock_mode, cfg.clock_file)
        self.out_dir = Path(cfg.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.obs_path = self.out_dir / "observaciones.jsonl"
        self.operativo_path = self.out_dir / "resultado_operativo.jsonl"
        self.funding_log_path = self.out_dir / "funding_adquisicion.jsonl"
        self.http_ledger_path = self.out_dir / "http_requests.jsonl"
        self.db_path = self.out_dir / "research.db"
        self.storage_budget = RunStorageBudget(cfg.max_bytes)
        existing_data_bytes = self._existing_counted_bytes()
        self.sqlite_initial_bytes = self._sqlite_bytes()
        self._sqlite_quota_committed = False
        self.storage_budget.seed_used(existing_data_bytes)
        if cfg.max_bytes:
            sqlite_quota = min(MAX_SQLITE_QUOTA_BYTES, cfg.max_bytes // 4)
            ledger_quota = min(MAX_HTTP_LEDGER_QUOTA_BYTES, cfg.max_bytes // 4)
        else:
            sqlite_quota = MAX_SQLITE_QUOTA_BYTES
            ledger_quota = MAX_HTTP_LEDGER_QUOTA_BYTES
        self.sqlite_quota_bytes = sqlite_quota
        self.http_ledger_quota_bytes = ledger_quota
        self.sqlite_main_limit_bytes = (
            max(4_096, (sqlite_quota - 128 * 1024) // 2)
            if sqlite_quota else 0)
        if not self.storage_budget.reserve(
                "sqlite:research.db", sqlite_quota):
            raise ValueError("presupuesto_bytes: no cabe la reserva SQLite")
        if not self.storage_budget.reserve(
                "http:requests", ledger_quota):
            self.storage_budget.release("sqlite:research.db")
            raise ValueError("presupuesto_bytes: no cabe la reserva del ledger")
        self.store = PilotStore(
            self.obs_path, 0,
            storage_budget=self.storage_budget,
            storage_key=f"jsonl:{self.obs_path}",
        )
        self.funding_log_fh = self.funding_log_path.open(
            "a", encoding="utf-8", newline="\n")
        self.funding_log_bytes = 0
        self.funding_queries_by_oid: Dict[str, int] = {}
        self.funding_calendars_by_oid: Dict[str, FundingCalendar] = {}
        self.history = HistoryStore(
            self.db_path, max_db_bytes=self.sqlite_main_limit_bytes)
        self.recorder = ResearchRecorder(
            db_path=self.db_path, run_id=cfg.run_id, enabled=True,
            clock_ms=self.clock.now_ms,
            max_db_bytes=self.sqlite_main_limit_bytes,
        )
        # Puerta de presupuesto efectiva: reserva cada intento HTTP antes del
        # transporte. Reutiliza HistoryClient y su attempt_gate existente.
        self.budget = RunBudget(
            cfg.max_http_attempts, cfg.max_http_retries, cfg.max_http_weight,
        )
        self.rest = HistoryClient(base_url=cfg.rest_base,
                                  attempt_gate=self.budget)
        # Adaptador del camino del experimento: ejecuta la regla operativa
        # (direccion comun, senal, entrada, gestion y salida simuladas) sobre
        # las observaciones del piloto, reutilizando paper_lab_engine.
        self.operativo = OperativoAdapter(
            store_path=self.out_dir / "resultado_operativo.jsonl",
            cfg=operativo_cfg or OperativoConfig(),
            funding_calendars=funding_calendars or {},
            storage_budget=self.storage_budget,
        )
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
        self.operativo_pendientes: Dict[str, Dict[str, Any]] = {}
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
        self._last_resolve_ms: Optional[int] = None
        self._last_resolve_due_ms: Optional[int] = None
        # Última consulta por observation_id (evita reconsultar la misma
        # operación dentro del mismo intervalo de planificación).
        self._last_resolve_by_obs: Dict[str, int] = {}
        # Claves de pending ya consultadas en el intervalo actual de resolve_due.
        self._resolve_due_done_this_interval: set = set()
        self.capture_end_ms = self.started_ms + int(cfg.duration_seconds * 1000)
        self.settle_end_ms = self.capture_end_ms + int(cfg.settle_seconds * 1000)
        # Instante de primera suscripcion de cada simbolo (calentamiento).
        # Un simbolo recién suscrito no se evalua hasta acumular la ventana
        # de flujo 1m requerida por la observacion; el periodo es independiente
        # del intervalo entre selecciones.
        self.symbol_first_seen_ms: Dict[str, int] = {}
        self.symbol_warmup_ms = FLOW_HORIZONS_MS[DECISION_FLOW_HORIZON]
        # Primera recepcion efectiva por fuente (instante del reloj al
        # procesar el evento). La ventana de flujo se mide con eventos
        # observados; la programacion del corte usa esta recepcion, no la
        # suscripcion, y nunca inventa cobertura.
        self.symbol_first_flow_ms: Dict[str, int] = {}
        self.symbol_first_book_ms: Dict[str, int] = {}
        # Simbolos ya evaluados en el ciclo de decision actual (para no
        # re-evaluarlos cuando se disparan evaluaciones acotadas por
        # calentamiento dentro del mismo ciclo).
        self._symbols_evaluated_this_cycle: set[str] = set()
        # Observabilidad del corte (nominal vs efectivo) y esperas acotadas.
        self.next_decision_ms: Optional[int] = None
        self.cut_deadline_ms: Optional[int] = None
        self.last_cut_ms: Optional[int] = None
        self.last_nominal_cut_ms: Optional[int] = None
        self.last_cut_deadline_ms: Optional[int] = None
        self.last_cut_reason: Optional[str] = None
        self.warmup_deferrals = 0
        self._deferral_active = False
        # --- Espera contable (metodo A: liquidaciones observadas) ----------
        # Simbolo -> observation_ids con la contabilidad de funding todavia
        # abierta. No abre seleccion, entrada ni posicion: solo completa la
        # contabilidad de operaciones ya resueltas.
        self.funding_espera_pendientes: Dict[str, List[str]] = {}
        self.funding_espera_consultas: Dict[str, int] = {}
        self.funding_espera_plan_ms: Dict[str, int] = {}
        self.funding_espera_regulares: Dict[str, int] = {}
        self.funding_espera_calendario: Dict[str, Optional[FundingCalendar]] = {}
        self.espera_contable_inicio_ms: Optional[int] = None
        self.espera_contable_fin_ms: Optional[int] = None
        self.espera_contable_cierre: Optional[str] = None
        self.espera_contable_posiciones_creditadas = 0
        self.espera_contable_posiciones_unknown = 0

    # -- metodo de funding ---------------------------------------------------

    def _metodo_funding_observado(self) -> bool:
        """True si la contabilidad se completa con liquidaciones observadas."""
        return (self.cfg.funding_source == "exchange"
                and self.cfg.funding_method == FUNDING_METHOD_OBSERVED)

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

    @staticmethod
    def _file_bytes(path: Path) -> int:
        try:
            return path.stat().st_size if path.exists() else 0
        except OSError:
            return 0

    def _funding_files_bytes(self) -> int:
        funding_dir = self.out_dir / "funding"
        if not funding_dir.exists():
            return 0
        return sum(self._file_bytes(path)
                   for path in funding_dir.glob("*.json"))

    def _existing_counted_bytes(self) -> int:
        funding_dir = self.out_dir / "funding"
        funding_bytes = (
            sum(self._file_bytes(path)
                for path in funding_dir.glob("*.json"))
            if funding_dir.exists() else 0)
        return (
            self._file_bytes(self.obs_path)
            + self._file_bytes(self.operativo_path)
            + self._file_bytes(self.funding_log_path)
            + self._file_bytes(self.http_ledger_path)
            + funding_bytes
            + self._sqlite_bytes()
        )

    def storage_bytes_total(self) -> int:
        """Bytes de datos persistidos, sin doble conteo.

        Incluye los tres JSONL de datos, el ledger HTTP, los calendarios de
        funding, SQLite y sus auxiliares. Los indices finales (``resumen.json``
        y ``manifiesto.json``) no son datos de la ventana y se contabilizan
        aparte del tope de captura.
        """
        http_ledger_path = self.out_dir / "http_requests.jsonl"
        return (
            self._file_bytes(self.obs_path)
            + self._file_bytes(self.operativo.store_path)
            + self._file_bytes(self.funding_log_path)
            + self._file_bytes(http_ledger_path)
            + self._funding_files_bytes()
            + self._sqlite_bytes()
        )

    def _storage_ok(self, extra_bytes: int = 0) -> bool:
        return self.storage_budget.can_fit(extra_bytes)

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
                    self.symbol_first_flow_ms.setdefault(symbol, recv_ms)
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
                    self.symbol_first_book_ms.setdefault(symbol, recv_ms)
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
                self.cfg.ws_public_base, public, WS_CATEGORIA_LIBRO),
                self.handle_message),
            "market": StreamFeed("market", build_stream_url(
                self.cfg.ws_market_base, market, WS_CATEGORIA_FLUJO),
                self.handle_message),
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
        candidate_by_symbol = {c.symbol: c for c in candidates}
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
        comparator_rows = []
        for c in cycle.comparator:
            candidate = candidate_by_symbol.get(c["symbol"])
            ticker_close_ms = (candidate.ticker_close_ms
                               if candidate is not None else None)
            ticker_available = (
                ticker_close_ms is not None
                and int(ticker_close_ms) <= int(cycle.reference_ms))
            move = (candidate.change_24h_pct
                    if candidate is not None and ticker_available else None)
            side = None
            if move is not None:
                side = "UP" if float(move) > 0 else (
                    "DOWN" if float(move) < 0 else None)
            self.selection_meta[c["symbol"]] = {
                "role": "comparator", "side": side, "priority": None,
                "move_24h_pct": move,
                "ticker_close_ms": ticker_close_ms,
                "ticker_discovered_at_ms": (
                    candidate.discovered_at_ms if candidate is not None else None),
                "selection_reference_ms": cycle.reference_ms,
                "selection_probability": c.get("selection_probability"),
                "sampling_mechanism": c.get("sampling_mechanism"),
            }
            comparator_rows.append({
                **c, "side": side, "move_24h": move,
                "ticker_close_ms": ticker_close_ms,
                "ticker_discovered_at_ms": (
                    candidate.discovered_at_ms if candidate is not None else None),
                "selection_reference_ms": cycle.reference_ms,
                "movement_source": "/fapi/v1/ticker/24hr priceChangePercent",
            })
        # Registrar primera suscripcion de simbolos nuevos (calentamiento).
        # Solo las entradas (nuevas o reincorporadas) renuevan el instante; los
        # simbolos que continuan conservan su periodo para no heredar ventaja
        # ni reiniciar su cobertura. Una reincorporacion no hereda cobertura
        # ficticia del periodo desconectado.
        for sym in new_followed:
            if sym not in prev:
                self.symbol_first_seen_ms[sym] = now

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
            self.symbol_first_seen_ms.pop(sym, None)
            self.symbol_first_flow_ms.pop(sym, None)
            self.symbol_first_book_ms.pop(sym, None)
            self._symbols_evaluated_this_cycle.discard(sym)

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
            "comparator": comparator_rows,
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

    def _pending_symbols(self) -> List[str]:
        """Simbolos seguidos que aun no tienen observacion en este ciclo."""
        return [symbol for symbol in self.followed
                if symbol not in self._symbols_evaluated_this_cycle]

    def _first_reception_ms(self, symbol: str) -> Optional[int]:
        """Primera recepcion efectiva (flujo o libro), o suscripcion si no hay."""
        stamps = [stamp for stamp in (
            self.symbol_first_flow_ms.get(symbol),
            self.symbol_first_book_ms.get(symbol)) if stamp is not None]
        if stamps:
            return min(stamps)
        return self.symbol_first_seen_ms.get(symbol)

    def _coverage_ready(self, symbol: str, book_rec: Optional[Dict[str, Any]],
                        flow_rec: Optional[Dict[str, Any]], now: int) -> bool:
        """Cobertura observada real: ventana completa y ambas fuentes frescas.

        La ventana la calcula el motor con eventos recibidos
        (``warmup_complete`` sobre el span observado), nunca con el instante de
        suscripcion. Se exige ademas que el libro tenga mid valido y que ambas
        fuentes esten dentro de ``max_data_age_ms``; mismas reglas para
        candidatos y comparadores.
        """
        if book_rec is None or flow_rec is None:
            return False
        flow_h = ((flow_rec.get("horizons") or {}).get(DECISION_FLOW_HORIZON)
                  or {})
        if not flow_h.get("warmup_complete"):
            return False
        if int(flow_h.get("trades") or 0) <= 0:
            return False
        book_features = book_rec.get("book") or {}
        if book_features.get("mid") is None:
            return False
        if book_rec.get("degraded") or book_features.get("crossed"):
            return False
        if self._frescura_fuente(self.last_book_recv.get(symbol),
                                 self.last_book_event.get(symbol), now):
            return False
        if self._frescura_fuente(self.last_flow_recv.get(symbol),
                                 self.last_flow_event.get(symbol), now):
            return False
        return True

    def _ready_symbols(self, now: int) -> List[str]:
        """Pendientes con cobertura observada real en ``now``."""
        book_records = self._book_records(now)
        flow_records = self._flow_records(now)
        return [symbol for symbol in self._pending_symbols()
                if self._coverage_ready(symbol, book_records.get(symbol),
                                        flow_records.get(symbol), now)]

    def _earliest_ready_ms(self) -> Optional[int]:
        """Estimacion: primera recepcion + ventana de flujo requerida.

        Es solo una cita para reprogramar; la readiness efectiva la decide
        ``_coverage_ready`` con los eventos ya recibidos.
        """
        times = []
        for symbol in self._pending_symbols():
            first = self._first_reception_ms(symbol)
            if first is None:
                continue
            times.append(int(first) + self.symbol_warmup_ms)
        return min(times) if times else None

    def _cut_deadline_ms(self) -> Optional[int]:
        """Espera maxima acotada para el corte pendiente (dentro de captura)."""
        pending = self._pending_symbols()
        if not pending:
            return None
        deadlines = []
        for symbol in pending:
            first = (self._first_reception_ms(symbol)
                     or self.started_ms)
            deadlines.append(int(first) + self.symbol_warmup_ms
                             + WARMUP_MAX_WAIT_MS)
        return min(min(deadlines), self.capture_end_ms - 1)

    def _nominal_cut_ms(self) -> Optional[int]:
        """Corte nominal (suscripcion + ventana), expuesto como referencia."""
        pending = self._pending_symbols()
        seen = [self.symbol_first_seen_ms[symbol] for symbol in pending
                if symbol in self.symbol_first_seen_ms]
        return (min(seen) + self.symbol_warmup_ms) if seen else None

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
            # Calentamiento: simbolo recién suscrito (o reincorporado). No se
            # evalua hasta acumular la ventana requerida (espera acotada, no
            # indefinida). Los que permanecen no reciben ventaja temporal.
            first_seen = self.symbol_first_seen_ms.get(symbol)
            if (
                first_seen is not None
                and now - first_seen < self.symbol_warmup_ms
            ):
                continue
            # No re-evaluar un simbolo ya evaluado en este ciclo de decision.
            if symbol in self._symbols_evaluated_this_cycle:
                continue
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
            self._symbols_evaluated_this_cycle.add(symbol)
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
                # Camino del experimento: registrar trabajo operativo pendiente
                # sin simular inmediatamente. La trayectoria se obtendra cuando
                # el reloj avance y haya velas disponibles. El adaptador se
                # invoca desde _resolver_operativos_pendientes.
                self._registrar_operativo_pendiente(symbol, obs)
            if self.observations_written >= self.cfg.max_observations:
                self.stop_reason = "max_observaciones"
                break
        return written

    def _registrar_operativo_pendiente(
        self, symbol: str, obs: Dict[str, Any],
    ) -> None:
        """Registra trabajo operativo pendiente para una observacion apta.

        Conserva la observacion completa y el dato de movimiento. No simula
        todavia: se resuelve cuando la trayectoria del horizonte pueda estar
        disponible (ver _resolver_operativos_pendientes).
        """
        self.operativo_pendientes[obs["observation_id"]] = {
            "observation_id": obs["observation_id"],
            "symbol": symbol,
            "role": str(obs.get("role", "comparator")),
            "observacion": obs,
            "resuelta": False,
            "consultas": 0,
            "motivo": None,
        }

    @staticmethod
    def _jsonl_payload(row: Dict[str, Any]) -> str:
        return json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"

    def _write_funding_log(self, row: Dict[str, Any]) -> bool:
        payload = self._jsonl_payload(row)
        encoded = len(payload.encode("utf-8"))
        key = f"jsonl:{self.funding_log_path}"
        if not self.storage_budget.reserve(key, encoded):
            self.stop_reason = "presupuesto_bytes"
            return False
        try:
            self.funding_log_fh.write(payload)
            self.funding_log_fh.flush()
        except Exception:
            self.storage_budget.release(key)
            raise
        self.storage_budget.commit(key, encoded)
        self.funding_log_bytes += encoded
        return True

    def _adquirir_funding_venue(
        self, symbol: str, start_ms: int, end_ms: int, now: int, *,
        coverage_builder: Optional[Any], archivo: str,
        log_base: Dict[str, Any],
    ) -> Optional[FundingCalendar]:
        """Consulta y persiste el historico REALIZADO de funding de un simbolo.

        Reutiliza el MISMO cliente, la MISMA puerta de presupuesto y el MISMO
        ledger que el resto de la corrida: no hay segundo camino de acceso a
        la venue. El constructor de cobertura es opcional: el metodo B aporta
        el contrato funding-coverage/v1 y el metodo A persiste el calendario
        OBSERVADO sin reclamar ese contrato.

        La respuesta se conserva con sus parametros, tiempos, hashes y
        procedencia. Un fallo no inventa liquidaciones: se registra como
        ERROR con su motivo y el funding queda UNKNOWN.
        """
        try:
            rows, headers = self.rest.funding_rate(
                symbol, start_ms=start_ms, end_ms=end_ms, limit=1000)
            request = (self.rest.upstream_requests[-1]
                       if self.rest.upstream_requests else {})
            coverage = (coverage_builder(rows, request)
                        if coverage_builder is not None else None)
            calendar = _funding_calendar_from_rows(
                symbol, rows, coverage=coverage)
            ordered, duplicates = calendar.normalized()
            effective_coverage = calendar.effective_coverage()
            regulares = len(_funding_regular_times(symbol, rows))
            provenance = {
                "endpoint": "/fapi/v1/fundingRate",
                "acquired_utc": iso_utc(
                    int(request.get("completed_at_ms") or now)),
                "request_sent_at_ms": request.get("sent_at_ms"),
                "request_completed_at_ms": request.get("completed_at_ms"),
                "query_start_ms": start_ms,
                "query_end_ms": end_ms,
                "response_sha256": request.get("response_sha256"),
                "observed_headers": request.get("observed_headers") or headers,
                "configured_weight": request.get("configured_weight"),
                "n_raw": len(rows),
                "n_settlements": len(ordered),
                "n_duplicates": duplicates,
                "n_regular_settlements": regulares,
                "coverage_ms": ([ordered[0].settlement_ms,
                                 ordered[-1].settlement_ms]
                                if ordered else [None, None]),
                "interval_basis": (
                    "unambiguous_repeated_regular_deltas"
                    if calendar.interval_ms else "UNKNOWN"),
                "regular_delta_distribution_ms": (
                    _funding_delta_distribution(symbol, rows)),
                "calendar_hash": calendar.calendar_hash(),
                "coverage_status": (
                    effective_coverage.status
                    if effective_coverage is not None else None),
                "coverage_hash": (
                    effective_coverage.coverage_hash()
                    if effective_coverage is not None else None),
                "note": ("realized venue rows only; queried after T for "
                         "accounting, never for the decision"),
            }
            calendar_payload = {
                "version": calendar.version,
                "source": calendar.source,
                "interval_ms": calendar.interval_ms,
                "symbol": calendar.symbol,
                "settlements": [
                    {"settlement_ms": item.settlement_ms,
                     "rate_bps": item.rate_bps,
                     "funding_rate": item.funding_rate,
                     "mark_price": item.mark_price,
                     "rate_type": item.rate_type}
                    for item in ordered
                ],
                "provenance": provenance,
            }
            if effective_coverage is not None:
                calendar_payload["coverage"] = effective_coverage.to_dict()
            funding_dir = self.out_dir / "funding"
            funding_dir.mkdir(parents=True, exist_ok=True)
            calendar_path = funding_dir / archivo
            calendar_text = (json.dumps(
                calendar_payload, ensure_ascii=False, indent=2,
                sort_keys=True) + "\n")
            log_row = dict(log_base)
            log_row.update({
                "kind": "funding_adquisicion",
                "symbol": symbol.upper(),
                "estado": "OK",
                "calendar": calendar_payload,
                "calendar_file": str(calendar_path),
            })
            calendar_bytes = len(calendar_text.encode("utf-8"))
            calendar_key = f"file:{calendar_path}"
            old_calendar_bytes = self._file_bytes(calendar_path)
            calendar_growth = max(0, calendar_bytes - old_calendar_bytes)
            if not self.storage_budget.reserve(
                    calendar_key, calendar_growth):
                self.stop_reason = "presupuesto_bytes"
                return None
            try:
                _atomic_write(calendar_path, calendar_text)
            except Exception:
                self.storage_budget.release(calendar_key)
                raise
            self.storage_budget.commit(
                calendar_key, calendar_bytes - old_calendar_bytes)
            if not self._write_funding_log(log_row):
                try:
                    calendar_path.unlink(missing_ok=True)
                except OSError:
                    pass
                self.storage_budget.commit(
                    calendar_key, -calendar_bytes)
                return None
            return calendar
        except RateLimitExceeded:
            raise
        except Exception as exc:
            error_row = dict(log_base)
            error_row.update({
                "kind": "funding_adquisicion",
                "symbol": symbol.upper(),
                "estado": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
                "query_start_ms": start_ms,
                "query_end_ms": end_ms,
                "funding_resultado": "UNKNOWN",
            })
            self._write_funding_log(error_row)
            return None

    def _ensure_funding_calendar(
        self, symbol: str, obs: Dict[str, Any], now: int,
    ) -> Optional[FundingCalendar]:
        """Acquire realized funding history for a symbol actually investigated.

        The query happens only after the operational trajectory is due, uses
        the same HistoryClient and RunBudget, and is never visible to the
        decision at T. Missing or conflicting venue rows fail closed to an
        explicit UNKNOWN funding state.

        Esta es la via B (contrato de cobertura): la cobertura se construye y
        se publica con el contrato funding-coverage/v1. El metodo A no la usa.
        """
        if self.cfg.funding_source != "exchange":
            return self.operativo.funding_calendars.get(symbol.upper())

        oid = str(obs["observation_id"])
        count = int(self.funding_queries_by_oid.get(oid, 0))
        if count >= MAX_CONSULTAS_FUNDING_POR_OBS:
            return self.funding_calendars_by_oid.get(oid)
        self.funding_queries_by_oid[oid] = count + 1
        start_ms = int(obs["decision_ms"]) - FUNDING_HISTORY_LOOKBACK_MS
        end_ms = int(now)
        safe_oid = "".join(ch if ch.isalnum() or ch in "-_" else "_"
                           for ch in oid)
        log_base = {
            "observation_id": oid,
            "decision_ms": int(obs["decision_ms"]),
            "consulta_numero": count + 1,
            "scope": "observacion",
            "funding_metodo": self.cfg.funding_method,
        }

        def _cobertura(rows: List[Dict[str, Any]],
                       request: Dict[str, Any]) -> FundingCoverage:
            return _binance_funding_coverage(
                symbol, rows, start_ms, end_ms, request, limit=1000)

        calendar = self._adquirir_funding_venue(
            symbol, start_ms, end_ms, now, coverage_builder=_cobertura,
            archivo=f"{symbol.upper()}--{safe_oid}.json", log_base=log_base)
        if calendar is not None:
            self.funding_calendars_by_oid[oid] = calendar
        return calendar

    def _consultar_trayectoria_operativa(
        self, symbol: str, obs: Dict[str, Any], now: int,
    ) -> Tuple[Optional[Any], str, List[Any]]:
        """Consulta la trayectoria 1m de una observacion y la procesa.

        UNA consulta cubre entrada, gestion y salida: la serie devuelta va
        desde la vela que cierra en T hasta el reloj actual mas un paso, con
        el limite de la ventana del horizonte. Devuelve (resultado, motivo,
        velas); un motivo no vacio significa que no hubo trayectoria utilizable (no
        se inventa ningun resultado).
        """
        decision_ms = int(obs["decision_ms"])
        step_ms = INTERVAL_MS[self.cfg.price_interval]
        start_ms = decision_ms - step_ms
        end_ms = now + step_ms
        rows, _ = self.rest.klines(
            symbol, self.cfg.price_interval, start_ms, end_ms,
            limit=int(self.operativo.cfg.horizon_ms // 60_000) + 2,
        )
        if not rows:
            return None, "sin_trayectoria_en_la_consulta"
        # Todas las velas devueltas por el proveedor, incluidas las
        # provisionales (close=None o close_time > now). El proveedor
        # identifica las provisionales con close=None; el consumidor nunca
        # trata un close ausente como vela cerrada. Las velas cuya apertura
        # es posterior al reloj se excluyen (no se conocen).
        velas_conocidas = []
        for r in rows:
            open_ms = int(r[0])
            close_ms = int(r[6]) if r[6] is not None else None
            if open_ms > now:
                continue
            velas_conocidas.append(PaperCandle(
                open_time_ms=open_ms, open=float(r[1]),
                high=float(r[2]), low=float(r[3]),
                close=float(r[4]) if r[4] is not None else None,
                close_time_ms=close_ms,
            ))
        if not velas_conocidas:
            return None, "sin_velas_conocidas_en_el_reloj", []
        # Metodo A: la salida se resuelve YA, pero el funding se contabiliza
        # DESPUES, cuando exista evidencia observada de la liquidacion
        # posterior a la salida. No se compra funding durante la resolucion.
        cal = (None if self._metodo_funding_observado()
               else self._ensure_funding_calendar(symbol, obs, now))
        tr = self.operativo.procesar_observacion(
            obs, velas_conocidas, funding_calendar=cal)
        return tr, "", velas_conocidas

    # -- espera contable (metodo A: liquidaciones observadas) ----------------

    def _consultar_funding_diferido(
        self, symbol: str, oids: List[str], now: int,
    ) -> Optional[FundingCalendar]:
        """Consulta diferida del historico OBSERVADO de funding de un simbolo.

        La ventana cubre desde antes de la entrada (mas el lookback) hasta el
        instante actual. El objetivo es OBSERVAR la liquidacion posterior a
        la salida: no se presupone ninguna liquidacion, no se fabrica ninguna
        y `UNKNOWN` nunca se convierte en cero.

        No usa el contrato de cobertura B: el calendario se construye con
        las liquidaciones realmente devueltas por la venue.
        """
        entradas: List[int] = []
        salidas: List[int] = []
        for oid in oids:
            item = self.operativo_pendientes.get(oid) or {}
            tr = item.get("resultado")
            if tr is None or tr.entry_ms is None or tr.exit_ms is None:
                continue
            entradas.append(int(tr.entry_ms))
            salidas.append(int(tr.exit_ms))
        if not entradas:
            return None
        start_ms = min(entradas) - FUNDING_HISTORY_LOOKBACK_MS
        end_ms = int(now)
        n = int(self.funding_espera_consultas.get(symbol, 0)) + 1
        log_base = {
            "scope": "simbolo",
            "observaciones": list(oids),
            "consulta_numero": n,
            "funding_metodo": self.cfg.funding_method,
            "query_start_ms": start_ms,
            "query_end_ms": end_ms,
            "target_exit_ms": max(salidas),
        }
        calendar = self._adquirir_funding_venue(
            symbol, start_ms, end_ms, now, coverage_builder=None,
            archivo=f"{symbol.upper()}--espera-contable.json",
            log_base=log_base)
        if calendar is not None:
            self.funding_espera_calendario[symbol] = calendar
            self.funding_espera_regulares[symbol] = len([
                item for item in calendar.settlements
                if (item.rate_type or "regular").lower() == "regular"])
        return calendar

    def _planificar_consulta_funding(
        self, symbol: str, calendar: FundingCalendar, now: int,
    ) -> None:
        """Programa la siguiente consulta de funding de un simbolo.

        El instante previsto se calcula con la cadencia OBSERVADA en el
        historico de ESE simbolo mas un margen de publicacion. Si la cadencia
        todavia no se puede inferir, se reintenta con un intervalo fijo y
        acotado. Nunca se presupone una cadencia ajena al simbolo.
        """
        ordered, _ = calendar.normalized()
        cadence = calendar.interval_ms
        if cadence and ordered:
            previsto = (int(ordered[-1].settlement_ms) + int(cadence)
                        + FUNDING_ESPERA_GRACE_MS)
        else:
            previsto = now + FUNDING_ESPERA_RECHECK_MS
        # Nunca se sondea en bucle: como minimo un intervalo de reintento.
        self.funding_espera_plan_ms[symbol] = max(
            int(previsto), now + FUNDING_ESPERA_RECHECK_MS)

    def _pendientes_contabilidad(self) -> int:
        """Posiciones con la contabilidad de funding todavia abierta."""
        return sum(len(v) for v in self.funding_espera_pendientes.values())

    def _podar_pendientes_funding(self) -> None:
        """Elimina los simbolos sin posiciones pendientes."""
        for symbol in list(self.funding_espera_pendientes):
            if not self.funding_espera_pendientes.get(symbol):
                self.funding_espera_pendientes.pop(symbol, None)

    def _cerrar_funding_posicion(
        self, oid: str, estado: str, motivo: str,
        resultado: Optional[Any] = None,
    ) -> bool:
        """Publica el cierre de la contabilidad de funding de una posicion."""
        item = self.operativo_pendientes.get(oid) or {}
        tr = resultado if resultado is not None else item.get("resultado")
        if tr is None:
            return True
        if not self._storage_ok():
            self.stop_reason = "presupuesto_bytes"
            return False
        if not self.operativo.persistir(
                tr, contabilidad={"estado": estado, "motivo": motivo}):
            self.stop_reason = "presupuesto_bytes"
            return False
        return True

    def _aplicar_contabilidad_funding(
        self, symbol: str, calendar: FundingCalendar, now: int,
    ) -> None:
        """Aplica el calendario observado a las posiciones pendientes.

        El veredicto canonico por posicion decide: si la cobertura es
        acreditable, la posicion se publica con su funding; si falta solo la
        liquidacion posterior a la salida, se sigue esperando; si el defecto
        es definitivo (hueco interior, cadencia ambigua, marca inservible),
        la posicion se cierra como UNKNOWN con su motivo.
        """
        for oid in list(self.funding_espera_pendientes.get(symbol) or []):
            item = self.operativo_pendientes.get(oid)
            if item is None:
                self.funding_espera_pendientes[symbol].remove(oid)
                continue
            tr = item.get("resultado")
            velas = item.get("velas")
            if tr is None or velas is None:
                continue
            veredicto = self.operativo.reevaluar_funding(tr, velas, calendar)
            if veredicto["creditable"]:
                if not self._cerrar_funding_posicion(
                        oid, "ACREDITADA",
                        "liquidaciones observadas; cobertura completa",
                        veredicto["resultado"]):
                    return
                self.funding_espera_pendientes[symbol].remove(oid)
                self.espera_contable_posiciones_creditadas += 1
                continue
            if veredicto["puede_mejorar"]:
                # Cadencia ambigua con suficiente historia: no mejora nunca.
                if (veredicto["motivo"] == "cadencia_no_inferida"
                        and int(self.funding_espera_regulares.get(
                            symbol, 0)) >= 3):
                    if not self._cerrar_funding_posicion(
                            oid, "UNKNOWN", "cadencia_ambigua"):
                        return
                    self.funding_espera_pendientes[symbol].remove(oid)
                    self.espera_contable_posiciones_unknown += 1
                    continue
                # La cobertura todavia puede mejorar: se publica el
                # diagnostico actual (p. ej. la cola sin liquidacion
                # posterior) SIN acreditar ningun importe. La liquidacion
                # todavia no publicada no se inventa.
                if not self._cerrar_funding_posicion(
                        oid, "PENDIENTE",
                        "espera_contable: %s" % veredicto["motivo"],
                        veredicto["resultado"]):
                    return
                continue
            if not self._cerrar_funding_posicion(
                    oid, "UNKNOWN", str(veredicto["motivo"])):
                return
            self.funding_espera_pendientes[symbol].remove(oid)
            self.espera_contable_posiciones_unknown += 1
        self._podar_pendientes_funding()

    def _resolver_funding_espera(self, now: int) -> int:
        """Ejecuta las consultas de funding diferidas que tocan.

        No sondea en cada tick: cada simbolo tiene su propio instante
        previsto. Cada consulta consume el MISMO presupuesto de la corrida y
        queda registrada en el MISMO ledger.
        """
        consultas = 0
        for symbol in sorted(self.funding_espera_pendientes):
            oids = list(self.funding_espera_pendientes.get(symbol) or [])
            if not oids:
                continue
            if self._terminal_stop():
                break
            plan_ms = self.funding_espera_plan_ms.get(symbol)
            if plan_ms is not None and now < plan_ms:
                continue
            n = int(self.funding_espera_consultas.get(symbol, 0))
            if n >= int(self.cfg.funding_wait_max_queries):
                for oid in oids:
                    if not self._cerrar_funding_posicion(
                            oid, "UNKNOWN", "consultas_de_funding_agotadas"):
                        return consultas
                    self.funding_espera_pendientes[symbol].remove(oid)
                    self.espera_contable_posiciones_unknown += 1
                self._podar_pendientes_funding()
                continue
            try:
                calendar = self._consultar_funding_diferido(symbol, oids, now)
            except RateLimitExceeded as exc:
                self.stop_reason = f"presupuesto_agotado: {exc}"
                break
            self.funding_espera_consultas[symbol] = n + 1
            consultas += 1
            if calendar is None:
                self.funding_espera_plan_ms[symbol] = (
                    now + FUNDING_ESPERA_RECHECK_MS)
                continue
            self._planificar_consulta_funding(symbol, calendar, now)
            self._aplicar_contabilidad_funding(symbol, calendar, now)
        return consultas

    def _cerrar_espera_contable(self, now: int) -> None:
        """Cierra la contabilidad que sigue pendiente con su motivo real.

        Una parada del operador o un presupuesto agotado conservan el
        pendiente (no se convierte en UNKNOWN de evidencia: no se ha
        terminado de buscar). El vencimiento del plazo o una cobertura
        insuficiente cierran como UNKNOWN con su motivo.
        """
        if self._pendientes_contabilidad() == 0:
            return
        parada = (self.stop_reason and self.stop_reason != "duracion")
        if parada:
            estado = "PENDIENTE"
            motivo = str(self.stop_reason)
        else:
            estado = "UNKNOWN"
            motivo = str(self.espera_contable_cierre
                         or "vencimiento_de_la_espera_contable")
        for symbol in sorted(self.funding_espera_pendientes):
            for oid in list(self.funding_espera_pendientes.get(symbol) or []):
                if not self._cerrar_funding_posicion(oid, estado, motivo):
                    return
                self.funding_espera_pendientes[symbol].remove(oid)
                if estado == "UNKNOWN":
                    self.espera_contable_posiciones_unknown += 1
        self._podar_pendientes_funding()

    async def _espera_contable(self) -> None:
        """Fase de espera contable (metodo A).

        No abre seleccion, entrada ni posicion: la exposicion y las salidas
        ya estan resueltas por sus horizontes originales. La unica actividad
        nueva es la consulta diferida de liquidaciones observadas y la
        publicacion de la contabilidad resultante.

        Termina antes si no queda trabajo, al vencer el plazo maximo (sin
        prorroga), o ante parada del operador o presupuesto agotado.
        """
        now = self.clock.now_ms()
        self._phase = "espera_contable"
        self.espera_contable_inicio_ms = now
        self.espera_contable_fin_ms = now + int(
            float(self.cfg.funding_wait_seconds) * 1000)
        tick_s = max(0.01, self.cfg.tick_ms / 1000.0)
        while True:
            now = self.clock.now_ms()
            if now >= self.espera_contable_fin_ms:
                self.espera_contable_cierre = "plazo_maximo_de_espera_agotado"
                break
            if self._terminal_stop():
                self.espera_contable_cierre = str(self.stop_reason)
                break
            if self._stop_file_requested():
                self.request_stop("parada_operador")
                self.espera_contable_cierre = "parada_operador"
                break
            self._resolver_funding_espera(now)
            self._write_status()
            if self._pendientes_contabilidad() == 0:
                self.espera_contable_cierre = "trabajo_resuelto"
                break
            await asyncio.sleep(tick_s)
        self._cerrar_espera_contable(self.clock.now_ms())

    def _resolver_operativos_pendientes(self, now: int) -> int:
        """Resuelve operaciones pendientes cuando la trayectoria puede estar
        disponible.

        Politica de replay (no hay sondeo por tick):
        - Una observacion se consulta cuando la trayectoria NECESARIA puede ya
          estar disponible: ``now >= decision_ms + horizon_ms + step_ms``.
          Antes de ese instante la consulta seria inutil (la serie 1m no
          llega al cierre del horizonte) y el motor no podria cerrar la
          exposicion en el horizonte.
        - Cada observacion admite como maximo
          ``MAX_CONSULTAS_TRAYECTORIA_POR_OBS`` consultas: una planificada y
          una REPETIDA (peticion repetida, no reintento por fallo). Los
          reintentos por fallo los cuenta el cliente HTTP y se reservan
          aparte en el presupuesto.
        - Orden determinista por (decision_ms, symbol, observation_id): el rol
          candidate/comparator no participa y no se mira ningun desenlace
          posterior para decidir.
        - Un bloqueo de presupuesto conserva el pendiente CON SU MOTIVO: no
          inventa resultados ni devuelve cupos.

        Devuelve el numero de operaciones resueltas en esta llamada.
        """
        resueltas = 0
        step_ms = INTERVAL_MS[self.cfg.price_interval]
        horizonte_ms = int(self.operativo.cfg.horizon_ms)
        # Prioridad determinista por tiempo y simbolo (el rol no participa).
        pendientes = sorted(
            self.operativo_pendientes.items(),
            key=lambda kv: (int(kv[1]["observacion"]["decision_ms"]),
                            str(kv[1]["symbol"]).upper(), kv[0]))
        for oid, item in pendientes:
            if item["resuelta"]:
                continue
            if self._terminal_stop():
                break
            decision_ms = int(item["observacion"]["decision_ms"])
            # La trayectoria del horizonte solo puede estar disponible cuando
            # el reloj alcanza el cierre del horizonte mas un paso (para que
            # la serie lo sobrepase y el motor cierre en el horizonte).
            if now < decision_ms + horizonte_ms + step_ms:
                continue
            consultas = int(item.get("consultas", 0))
            if consultas >= MAX_CONSULTAS_TRAYECTORIA_POR_OBS:
                item["motivo"] = item.get("motivo") or (
                    "consultas_maximas_agotadas_sin_trayectoria")
                continue
            # No repetir la misma observacion dentro de un intervalo de
            # planificacion (60 s).
            last = self._last_resolve_by_obs.get(oid)
            if last is not None and now - last < _INTERVALO_RESOLVER_MS:
                continue
            symbol = item["symbol"]
            obs = item["observacion"]
            try:
                tr, motivo, velas = self._consultar_trayectoria_operativa(
                    symbol, obs, now)
            except RateLimitExceeded as exc:
                # Presupuesto agotado: no se envia nada mas. El pendiente se
                # conserva con su motivo real y la corrida se detiene (no se
                # inventan resultados ni se devuelven cupos).
                self.stop_reason = f"presupuesto_agotado: {exc}"
                item["motivo"] = f"presupuesto_agotado: {exc}"
                break
            except Exception as exc:
                item["consultas"] = consultas + 1
                item["motivo"] = (
                    f"error_consulta_trayectoria: {type(exc).__name__}")
                self._last_resolve_by_obs[oid] = now
                continue
            self._last_resolve_by_obs[oid] = now
            item["consultas"] = consultas + 1
            if tr is None:
                item["motivo"] = motivo or "sin_trayectoria"
                continue
            # Resultado terminal: la consulta se hizo cuando la trayectoria
            # del horizonte ya podia estar disponible, de modo que el
            # desenlace (salida ejecutada, agotamiento o abstencion) es
            # definitivo para esta observacion.
            r = tr  # OperativoTradeResult
            terminal = (
                r.exit_executed
                or r.decision in ("SIN_ENTRADA", "RECHAZADA_CAPACIDAD",
                                  "DESCARTADO")
                or r.open_at_end
                or r.decision == "ENTRADA_SIMULADA"
            )
            if terminal:
                if not self._storage_ok():
                    self.stop_reason = "presupuesto_bytes"
                    break
                # Metodo A: la salida ya esta decidida pero la contabilidad de
                # funding sigue pendiente. Se publica con su estado PENDIENTE
                # y se completa mas tarde, con evidencia observada.
                contabilidad = None
                if (self._metodo_funding_observado()
                        and r.decision == "ENTRADA_EJECUTADA"
                        and r.exit_executed and r.exit_ms is not None
                        and r.entry_ms is not None):
                    contabilidad = {
                        "estado": "PENDIENTE",
                        "motivo": "espera_contable: liquidacion posterior a la "
                                  "salida todavia no observada",
                    }
                if not self.operativo.persistir(tr, contabilidad=contabilidad):
                    self.stop_reason = "presupuesto_bytes"
                    break
                item["resuelta"] = True
                item["resultado"] = tr
                item["motivo"] = None
                if contabilidad is not None:
                    item["velas"] = velas
                    self.funding_espera_pendientes.setdefault(
                        str(symbol).upper(), []).append(oid)
                self._last_resolve_by_obs.pop(oid, None)
                resueltas += 1
            else:
                item["motivo"] = "trayectoria_insuficiente"
        return resueltas

    def finalize_operativos_pendientes(self, now: int) -> None:
        """Conserva los pendientes operativos con su motivo real.

        No se inventa ningun resultado: una operacion sin trayectoria
        suficiente queda PENDIENTE con el motivo real (consultas agotadas,
        presupuesto agotado o ventana de settle agotada).
        """
        causa = self._pending_cause()
        for oid, item in sorted(self.operativo_pendientes.items()):
            if item["resuelta"]:
                continue
            motivo = item.get("motivo") or causa
            obs = item["observacion"]
            tr = OperativoTradeResult(
                observation_id=oid,
                symbol=str(item["symbol"]),
                role=str(item.get("role", "comparator")),
                direction=None,
                decision="PENDIENTE",
                decision_ms=int(obs["decision_ms"]),
                entry_px=None, entry_ms=None,
                stop_px=None,
                exit_px=None, exit_ms=None,
                exit_reason=None, exit_executed=False,
                open_at_end=False, qty=0.0,
                gross_pnl=0.0, fees=0.0, spread_slip=0.0,
                funding=None, net_pnl=None,
                funding_estado=f"pendiente: {motivo}",
                config_hash=self.operativo._config_hash(),
                engine_version=ENGINE_VERSION_PAPER,
            )
            if not self._storage_ok():
                self.stop_reason = "presupuesto_bytes"
                break
            if not self.operativo.persistir(tr):
                self.stop_reason = "presupuesto_bytes"
                break
            item["motivo"] = motivo

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
        # Planificacion de consultas: evitar consultas de klines en cada tick.
        if (
            self._last_resolve_due_ms is not None
            and now - self._last_resolve_due_ms < _INTERVALO_RESOLVER_MS
        ):
            return 0
        self._last_resolve_due_ms = now
        # Nueva ventana de planificacion: limpiar claves ya consultadas.
        self._resolve_due_done_this_interval.clear()
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
            # No reconsultar un pending ya atendido en este intervalo.
            if key in self._resolve_due_done_this_interval:
                continue
            self._resolve_due_done_this_interval.add(key)
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
            "run_id": self.cfg.run_id,
            "mode": self.cfg.mode,
            "activar_publico": self.cfg.activar_publico,
            "now_ms": now,
            "started_ms": self.started_ms,
            "capture_end_ms": self.capture_end_ms,
            "settle_end_ms": self.settle_end_ms,
            "followed": list(self.followed),
            "roles": dict(self.roles),
            "cycles_run": self.cycles_run,
            "evaluations_run": self.evaluations_run,
            "symbol_warmup_ms": self.symbol_warmup_ms,
            "symbol_first_seen_ms": dict(self.symbol_first_seen_ms),
            "symbol_first_flow_ms": dict(self.symbol_first_flow_ms),
            "symbol_first_book_ms": dict(self.symbol_first_book_ms),
            "nominal_decision_ms": self._nominal_cut_ms(),
            "last_nominal_cut_ms": self.last_nominal_cut_ms,
            "last_cut_deadline_ms": self.last_cut_deadline_ms,
            "next_decision_ms": self.next_decision_ms,
            "cut_deadline_ms": self.cut_deadline_ms,
            "last_cut_ms": self.last_cut_ms,
            "last_cut_reason": self.last_cut_reason,
            "warmup_deferrals": self.warmup_deferrals,
            "warmup_pending": self._pending_symbols(),
            "symbols_evaluated_this_cycle": sorted(
                self._symbols_evaluated_this_cycle),
            "observations_written": self.observations_written,
            "outcomes_written": self.outcomes_written,
            "pending": len(self.pending),
            "stop_reason": self.stop_reason,
            # Contadores autoritativos de presupuesto: los mismos objetos que
            # gobiernan la puerta en runtime. Solo exposicion; no altera la
            # reserva, el consumo ni ninguna decision.
            "presupuesto": self.budget.status(),
            "almacenamiento": self.storage_budget.status(),
            "duracion_maxima_total_ms": int(
                (self.cfg.duration_seconds + self.cfg.settle_seconds
                 + self.cfg.funding_wait_seconds) * 1000),
            "espera_contable_plazo_max_ms": int(
                self.cfg.funding_wait_seconds * 1000),
            "espera_contable_inicio_ms": self.espera_contable_inicio_ms,
            "espera_contable_fin_ms": self.espera_contable_fin_ms,
            "espera_contable_cierre": self.espera_contable_cierre,
            "espera_contable_pendientes": sum(
                len(v) for v in self.funding_espera_pendientes.values()),
            "funding_consultas_espera": dict(self.funding_espera_consultas),
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
        run_error: Optional[BaseException] = None
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
                    # Una entrada nueva o reincorporada merece su propio corte
                    # dentro de este ciclo: se adelanta el corte vigente a su
                    # ventana nominal; la cobertura observada decide despues.
                    if self._pending_symbols():
                        candidate = now + self.symbol_warmup_ms
                        if candidate < next_decision:
                            next_decision = candidate
                # Evaluacion: un solo camino, con o sin barrera de prueba.
                # - Sin barrera (productivo): el corte espera COBERTURA
                #   OBSERVADA real (ventana de flujo completa y ambas fuentes
                #   frescas). El corte nominal (suscripcion + ventana) puede
                #   adelantarse a la primera recepcion: mientras no haya
                #   cobertura se reprograma dentro del mismo bucle, con espera
                #   maxima acotada, sin escribir un descarte definitivo.
                # - Con barrera (solo pruebas): solo se evalua en el instante
                #   autorizado por decision-gate-file. La barrera no participa
                #   en la coordinacion automatica.
                self.next_decision_ms = next_decision
                self.cut_deadline_ms = self._cut_deadline_ms()
                if self.followed:
                    if self.gate_path is not None:
                        if self._gate_decision_ms() == now:
                            self._symbols_evaluated_this_cycle = set()
                            written = self.take_decisions(now)
                            if written > 0:
                                self.evaluations_run += 1
                                self.last_cut_ms = now
                    elif now >= next_decision:
                        # Nuevo ciclo de decision: los simbolos seguidos
                        # recuperan su oportunidad de evaluacion. El set se
                        # limpia unica y exclusivamente en el limiar del ciclo;
                        # dentro del mismo ciclo los reintentos de calentamiento
                        # no la renuevan, y la seleccion no decide si hay nueva
                        # evaluacion.
                        self._symbols_evaluated_this_cycle = set()
                        pending = self._pending_symbols()
                        if not pending:
                            next_decision = now + int(
                                self.cfg.cycle_seconds * 1000)
                        else:
                            nominal = self._nominal_cut_ms()
                            if nominal is not None:
                                self.last_nominal_cut_ms = nominal
                            ready = self._ready_symbols(now)
                            deadline = self._cut_deadline_ms()
                            if (len(ready) == len(pending)
                                    or (deadline is not None
                                        and now >= deadline)):
                                written = self.take_decisions(now)
                                if written > 0:
                                    self.evaluations_run += 1
                                    self.last_cut_ms = now
                                    self.last_cut_deadline_ms = deadline
                                    self.last_cut_reason = (
                                        "cobertura_completa"
                                        if len(ready) == len(pending)
                                        else "espera_maxima_agotada")
                                    self._deferral_active = False
                                    next_decision = now + int(
                                        self.cfg.cycle_seconds * 1000)
                                else:
                                    earliest = self._earliest_ready_ms()
                                    next_decision = (
                                        earliest if earliest is not None
                                        else now + int(
                                            self.cfg.cycle_seconds * 1000))
                            else:
                                # Corte nominal sin cobertura real: no se
                                # consume la oportunidad. Se reintenta en el
                                # mismo bucle hasta la espera maxima.
                                if not self._deferral_active:
                                    self.warmup_deferrals += 1
                                    self._deferral_active = True
                                self.last_cut_reason = "esperando_cobertura"
                                earliest = self._earliest_ready_ms()
                                target = (earliest if earliest is not None
                                          else now + COVERAGE_RECHECK_MS)
                                if deadline is not None:
                                    target = min(target, deadline)
                                next_decision = max(
                                    now + COVERAGE_RECHECK_MS, target)
                self.next_decision_ms = next_decision
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
                # Resolver operaciones operativas pendientes cuando haya
                # trayectoria disponible (respetando el reloj del proveedor).
                self._resolver_operativos_pendientes(now)
                await self.resolve_due(now)
                self._write_status()
                await asyncio.sleep(tick_s)
            # Settle: presupuesto, plazo y cancelacion siguen vigentes.
            await self._stop_feeds()
            self._phase = "settle"
            while (self.clock.now_ms() < self.settle_end_ms
                   and (self.pending or self.operativo_pendientes)
                   and not self._terminal_stop()):
                if self._stop_file_requested():
                    self.request_stop("parada_operador")
                    break
                now = self.clock.now_ms()
                self._resolver_operativos_pendientes(now)
                await self.resolve_due(now)
                self._write_status()
                await asyncio.sleep(tick_s)
            # Espera contable (metodo A): la captura y el settle ya han
            # resuelto las operaciones por sus horizontes originales. aqui
            # solo se busca evidencia OBSERVADA de las liquidaciones para
            # completar la contabilidad; no hay seleccion, entrada ni
            # posicion nuevas, y el plazo no se prorroga.
            if self._metodo_funding_observado() and self.funding_espera_pendientes:
                await self._espera_contable()
            self.finalize_pending(self.clock.now_ms())
            # Los pendientes operativos que no se resolvieron se conservan
            # PENDIENTES con su motivo real (no se inventan resultados ni se
            # devuelven cupos de presupuesto).
            self.finalize_operativos_pendientes(self.clock.now_ms())
        except BaseException as exc:
            run_error = exc
            self.stop_reason = self.stop_reason or (
                f"error_interno:{type(exc).__name__}")
            raise
        finally:
            await self._stop_feeds()
            try:
                self.recorder.stop_and_drain(timeout=30.0)
            except Exception:
                pass
            self.store.close()
            try:
                self.operativo.close()
            except Exception:
                pass
            try:
                self.funding_log_fh.close()
            except Exception:
                pass
            self.ended_ms = self.clock.now_ms()
            self._phase = "fin"
            self._write_status()
            # El ledger y el resumen se reconstruyen incluso ante una excepcion
            # o senal: el cierre auditable no depende de la salida normal.
            try:
                summary = self._write_outputs(skipped_selections)
            except Exception:
                if run_error is None:
                    raise
                summary = {}
        return summary

    # -- salidas -------------------------------------------------------

    def _write_outputs(self, skipped_selections: int) -> Dict[str, Any]:
        rows = read_jsonl(self.obs_path)
        operational_path = self.out_dir / "resultado_operativo.jsonl"
        operational_rows = (read_jsonl(operational_path)
                            if operational_path.exists() else [])
        http_ledger_path = self.out_dir / "http_requests.jsonl"
        http_ledger = []
        for request in self.rest.upstream_requests:
            http_ledger.append({
                "kind": "http_request",
                "execution_id": request.get("execution_id"),
                "endpoint": request.get("endpoint"),
                "params": request.get("params") or {},
                "symbol": request.get("symbol"),
                "interval": request.get("interval"),
                "range": request.get("range"),
                "page": request.get("page"),
                "retry": request.get("retry"),
                "result": request.get("result"),
                "duration_ms": request.get("duration_ms"),
                "sent_at_ms": request.get("sent_at_ms"),
                "completed_at_ms": request.get("completed_at_ms"),
                "blocked_at_ms": request.get("blocked_at_ms"),
                "block_reason": request.get("block_reason"),
                "configured_weight": request.get("configured_weight"),
                "reserved_weight": request.get("_reserved_weight"),
                "attempt_no": request.get("_attempt_no"),
                "retry_reserved": request.get("_retry_reserved"),
                "observed_headers": request.get("observed_headers") or {},
                "http_status": request.get("http_status"),
                "response_bytes": request.get("response_bytes"),
                "response_item_count": request.get("response_item_count"),
                "response_sha256": request.get("response_sha256"),
            })
        http_ledger_text = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in http_ledger)
        http_ledger_bytes = len(http_ledger_text.encode("utf-8"))
        old_ledger_bytes = self._file_bytes(http_ledger_path)
        ledger_growth = max(0, http_ledger_bytes - old_ledger_bytes)
        if ledger_growth > self.http_ledger_quota_bytes:
            self.stop_reason = "presupuesto_bytes"
        else:
            try:
                _atomic_write(http_ledger_path, http_ledger_text)
            except OSError:
                self.stop_reason = "presupuesto_bytes"
            else:
                self.storage_budget.commit(
                    "http:requests", http_ledger_bytes - old_ledger_bytes)
        if not self._sqlite_quota_committed:
            sqlite_growth = self._sqlite_bytes() - self.sqlite_initial_bytes
            if sqlite_growth > self.sqlite_quota_bytes:
                self.stop_reason = "presupuesto_bytes"
            else:
                self.storage_budget.commit(
                    "sqlite:research.db", sqlite_growth)
                self._sqlite_quota_committed = True
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
                "peso_configurado_cliente_respuestas_ok": (
                    self.rest.stats.weight_spent),
                "peso_reservado_presupuesto_todos_intentos": self.budget.weight,
                "nota_pesos": (
                    "configured_weight es el peso conservador del cliente; "
                    "reserved_weight es el peso oficial reservado por la puerta "
                    "antes de cada transporte. El peso reservado cuenta "
                    "intentos fallidos; el peso del cliente solo respuestas OK."),
                "ledger_file": str(http_ledger_path),
                "ledger_rows": len(http_ledger),
                "cabeceras_peso_observadas": [
                    {"endpoint": row.get("endpoint"),
                     "observed_headers": row.get("observed_headers") or {}}
                    for row in http_ledger
                    if row.get("observed_headers")
                ],
            },
            "presupuesto_http": self.budget.status(),
            # Politica presupuestada de esta corrida (estimacion base, reservas
            # y limite efectivo). Permite contrastar el plan con las llamadas
            # realmente observadas sin recalcular nada a mano.
            "presupuesto_plan": compute_budget(self.cfg),
            "ws_connections_total": self.ws_total_connections + sum(
                f.connections for f in self.feeds.values()),
            "ws_messages_total": self.ws_messages_total + sum(
                f.messages for f in self.feeds.values()),
            "ws_reconnects_total": self.ws_reconnects_total + sum(
                f.reconnects for f in self.feeds.values()),
            "ws": {name: feed.status() for name, feed in self.feeds.items()},
            "economia_operativa_v2": build_operational_economic_summary(
                rows, operational_rows),
            "espera_contable": {
                "metodo": self.cfg.funding_method,
                "plazo_max_ms": int(
                    float(self.cfg.funding_wait_seconds) * 1000),
                "inicio_ms": self.espera_contable_inicio_ms,
                "fin_ms": self.espera_contable_fin_ms,
                "cierre": self.espera_contable_cierre,
                "consultas_por_simbolo": dict(self.funding_espera_consultas),
                "consultas_totales": sum(
                    self.funding_espera_consultas.values()),
                "posiciones_acreditadas": (
                    self.espera_contable_posiciones_creditadas),
                "posiciones_unknown": self.espera_contable_posiciones_unknown,
                "pendientes_finales": sum(
                    len(v) for v in self.funding_espera_pendientes.values()),
                "duracion_total_efectiva_s": (
                    round((self.ended_ms - self.started_ms) / 1000.0, 3)
                    if self.ended_ms is not None else None),
            },
            "almacenamiento": {
                "observaciones_jsonl_bytes": self._file_bytes(self.obs_path),
                "observaciones_jsonl_rows": self.store.rows_written,
                "resultado_operativo_jsonl_bytes": self._file_bytes(
                    self.operativo.store_path),
                "funding_adquisicion_jsonl_bytes": self._file_bytes(
                    self.funding_log_path),
                "funding_calendar_bytes": self._funding_files_bytes(),
                "http_requests_jsonl_bytes": self._file_bytes(http_ledger_path),
                "sqlite_bytes": self._sqlite_bytes(),
                "storage_bytes_total": self.storage_bytes_total(),
                "storage_accounted_bytes": (
                    self.storage_budget.accounted_bytes),
                "storage_budget": self.storage_budget.status(),
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
                "neto COMPLETO solo con funding acreditado por posicion; "
                "sin cobertura completa queda CONDICIONADO, nunca cero",
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
        manifest_names = (
            "observaciones.jsonl", "resultado_operativo.jsonl",
            "funding_adquisicion.jsonl", "http_requests.jsonl",
            "presupuesto.json", "resumen.json", "estado.json",
            "diagnostico.json", "research.db", "research.db-wal",
            "research.db-shm",
        )
        for name in manifest_names:
            path = self.out_dir / name
            if path.exists():
                manifest["files"][name] = {
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
        funding_dir = self.out_dir / "funding"
        if funding_dir.exists():
            for path in sorted(funding_dir.glob("*.json")):
                key = str(path.relative_to(self.out_dir)).replace("\\", "/")
                manifest["files"][key] = {
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
    # Default loopback: el modo local no necesita mas. El modo publico exige
    # bases explicitas del venue (validacion por host y categoria).
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
    p.add_argument("--funding-calendars", default=None,
                   help="ruta a JSON con calendarios de funding por simbolo "
                        "(clave = simbolo, valor = calendario)")
    p.add_argument("--funding-source", choices=("none", "exchange"),
                   default="none",
                   help="none=sin funding automatico; exchange=historial "
                        "realizado por simbolo mediante el cliente HTTP y la "
                        "puerta de presupuesto")
    p.add_argument("--funding-method", choices=FUNDING_METHODS,
                   default=FUNDING_METHOD_COVERAGE,
                   help="coverage-contract=contrato funding-coverage/v1 (B, "
                        "diferido); observed-settlements=contabilidad con "
                        "liquidaciones observadas tras espera acotada (A)")
    p.add_argument("--funding-wait-seconds", type=float, default=0.0,
                   help="espera contable maxima del metodo A (0 = sin espera)")
    p.add_argument("--funding-wait-max-queries", type=int,
                   default=MAX_CONSULTAS_FUNDING_ESPERA_POR_SIMBOLO,
                   help="consultas diferidas de funding maximas por simbolo "
                        "durante la espera contable")
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
        # Base publica incompatible: se exige wss y el host USD-M documentado.
        for nombre, valor in (("ws-public-base", args.ws_public_base),
                              ("ws-market-base", args.ws_market_base)):
            partes = urlsplit(str(valor))
            if partes.scheme != "wss":
                raise ValueError(
                    f"base publica incompatible en --{nombre}: {valor!r}; "
                    f"se exige wss:// (host {WS_HOST_PUBLICO}, categorias "
                    f"{WS_CATEGORIAS})")
            host = (partes.hostname or "").lower()
            if host != WS_HOST_PUBLICO:
                raise ValueError(
                    f"base publica incompatible en --{nombre}: {valor!r}; el "
                    f"host debe ser {WS_HOST_PUBLICO} (categorias "
                    f"{WS_CATEGORIAS})")

    # Categoria de trafico por conexion: se valida ANTES de conectar (base
    # cruzada, '/stream' duplicado o ruta no compatible -> error explicito).
    normalizar_base_ws(args.ws_public_base, WS_CATEGORIA_LIBRO,
                       contexto="--ws-public-base")
    normalizar_base_ws(args.ws_market_base, WS_CATEGORIA_FLUJO,
                       contexto="--ws-market-base")

    if (args.funding_source == "exchange"
            and args.funding_calendars):
        raise ValueError(
            "--funding-source exchange y --funding-calendars son fuentes "
            "excluyentes; no se mezclan calendarios externos con la fuente real")

    # Metodo de funding: la eleccion es explicita y falla cerrada.
    if args.funding_method not in FUNDING_METHODS:
        raise ValueError(
            "--funding-method debe ser %s" % (" o ".join(FUNDING_METHODS),))
    if args.funding_method == FUNDING_METHOD_OBSERVED:
        if args.funding_source != "exchange":
            raise ValueError(
                "--funding-method %s requiere --funding-source exchange: la "
                "contabilidad con liquidaciones observadas necesita la fuente "
                "real" % FUNDING_METHOD_OBSERVED)
        if float(args.funding_wait_seconds) <= 0.0:
            raise ValueError(
                "--funding-method %s requiere --funding-wait-seconds > 0: sin "
                "espera contable no hay liquidacion posterior que observar"
                % FUNDING_METHOD_OBSERVED)
        if float(args.funding_wait_seconds) > FUNDING_ESPERA_MAX_SEGUNDOS:
            raise ValueError(
                "--funding-wait-seconds no puede superar el plazo maximo del "
                "protocolo (%s s)" % FUNDING_ESPERA_MAX_SEGUNDOS)
        if int(args.funding_wait_max_queries) < 1:
            raise ValueError(
                "--funding-wait-max-queries debe ser >= 1")
        if int(args.funding_wait_max_queries) > \
                MAX_CONSULTAS_FUNDING_ESPERA_POR_SIMBOLO:
            raise ValueError(
                "--funding-wait-max-queries no puede superar el tope del "
                "protocolo (%d por simbolo)"
                % MAX_CONSULTAS_FUNDING_ESPERA_POR_SIMBOLO)

    # Instrumentacion de sincronizacion: solo con reloj manual (pruebas).
    # --status-file es puramente observativo: no controla decisiones, por lo que
    # se admite tambien con reloj system (capturas publicas). --decision-gate-file
    # y --stop_file son barreras de prueba y requieren reloj manual.
    if args.clock != "manual" and (
            args.decision_gate_file or args.stop_file):
        raise ValueError(
            "--decision-gate-file/--stop-file requieren --clock manual"
        )

    return PilotConfig(
        run_id=run_id,
        out_dir=out_dir,
        mode=args.mode,
        activar_publico=args.activar_publico,
        rest_base=args.rest_base,
        ws_public_base=normalizar_base_ws(
            args.ws_public_base, WS_CATEGORIA_LIBRO,
            contexto="--ws-public-base"),
        ws_market_base=normalizar_base_ws(
            args.ws_market_base, WS_CATEGORIA_FLUJO,
            contexto="--ws-market-base"),
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
        funding_source=args.funding_source,
        funding_method=args.funding_method,
        funding_wait_seconds=float(args.funding_wait_seconds),
        funding_wait_max_queries=int(args.funding_wait_max_queries),
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
        gate = budget["gate"]
        print(json.dumps({"presupuesto": str(path),
                          "peso_total_estimado": budget["rest"]["peso_total_estimado"],
                          "gate": gate},
                         ensure_ascii=False))
        return 0 if gate["cabe_en_limites"] else 3
    if cfg.mode == "public":
        gate = compute_budget(cfg)["gate"]
        if not gate["cabe_en_limites"]:
            print(json.dumps({
                "error": "presupuesto_no_cerrado",
                "gate": gate,
            }, ensure_ascii=False), file=sys.stderr)
            return 3
    try:
        clock = build_clock(cfg.clock_mode, cfg.clock_file)
        # Cargar calendarios de funding si se especifican (archivo sintetico
        # identificado como tal en pruebas; no se abre adquisicion publica).
        # Si se pide un fichero que no existe o no es valido, el error es
        # explicito: no hay paso silencioso a un calendario vacio.
        funding_calendars: Dict[str, FundingCalendar] = {}
        if args.funding_calendars:
            fc_path = Path(args.funding_calendars)
            if not fc_path.exists():
                raise FileNotFoundError(
                    f"--funding-calendars no existe: {fc_path}")
            try:
                fc_data = json.loads(fc_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(
                    f"--funding-calendars ilegible: {fc_path}: {exc}") from exc
            if not isinstance(fc_data, dict):
                raise ValueError(
                    "--funding-calendars debe ser un objeto {simbolo: calendario}")
            for symbol, fc_dict in fc_data.items():
                if not isinstance(fc_dict, dict):
                    raise ValueError(
                        f"calendario de funding invalido para {symbol}")
                calendar_data = dict(fc_dict)
                calendar_data["symbol"] = str(symbol).upper()
                funding_calendars[str(symbol).upper()] = \
                    FundingCalendar.from_dict(calendar_data)
        pilot = ResearchPilot(
            cfg, clock=clock,
            funding_calendars=funding_calendars,
        )
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
