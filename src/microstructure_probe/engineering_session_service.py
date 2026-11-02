"""Servicio de sesión de ingeniería autónoma (solo loopback).

Mantiene la sesión del lado backend y conduce el avance mediante EVENTOS del
transporte. Dos transportes, un solo controlador y un solo motor:

  * ``local_replay`` (default): un reproductor con cadencia publica solo
    eventos de revelado (uno por vela) y el controlador los interpreta con
    el motor existente ``paper_lab_engine`` — autoridad económica única —
    paso a paso incrementalmente.
  * ``market_stream`` (live de ingeniería): un adaptador cliente SSE consume
    los eventos publicados por el servicio de mercado EXISTENTE
    (``market-stream-service/v1``, solo loopback, fail-closed). Solo velas
    CERRADAS conducen; la provisional es contador; duplicados/huecos/silencio
    se traducen en dedupe o abstención con causa explícita.

El navegador inicia (create + control start), observa (GET del estado) y
detiene (control stop); cerrar la pestaña NO detiene la sesión.

No hay Binance, no hay feed público, no hay órdenes reales, no hay capital
real. No hay un proceso Python por tick ni un gestor paralelo: un solo
proceso de servicio reutiliza el motor y los mecanismos de persistencia
existentes (escritura atómica + revisión optimista + lock por archivo).

El evaluador solo recibe el prefijo revelado: el dict público del motor no
publica velas futuras y el reproductor no entrega OHLC, solo el avance
(evento de revelado) que la conducción traduce en llamadas del motor.

Contrato (``engineering-session-service/v1``):
  GET  /health
  GET  /sessions                       -> lista resumida
  POST /sessions                       -> crea sesión {config, candles, ...}
  GET  /sessions/{id}                  -> estado público (prefijo revelado)
  POST /sessions/{id}/control          -> {"action": start|stop|step|exit|
                                          restart|stop_session|evaluate,
                                          "expected_revision"?,
                                          "request_id"?}
  POST /shutdown

Acciones del control:
  start        : comienza la conducción autónoma del backend.
  stop         : detiene la conducción; la sesión queda como está (sin
                 cierre inventado); reanudar con otra llamada start.
  step         : un avance manual (el mismo tipo de evento que produce el
                 transporte local; sin repetición por reloj).
  exit         : salida manual (manual_exit del motor).
  restart      : reinicio de sesión (motor).
  stop_session : detiene la conducción y congela la sesión (detenida).
  evaluate     : reevalua en T cuando el estado lo admite.

Escribe SOLO en el directorio de sesiones configurado (aislado en pruebas;
sin tocar bases canónicas).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import replace as dc_replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, quote, urlsplit

# Raíz del repositorio: src/microstructure_probe/este_archivo.py → 3 arriba.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from microstructure_probe import paper_lab_engine as engine  # noqa: E402
from microstructure_probe.clock import (  # noqa: E402
    ClockSynchronizer,
    SERVER_TIME_URL,
)
from microstructure_probe.history_client import UpstreamBudgetExceeded  # noqa: E402
from microstructure_probe.market_cache import (  # noqa: E402
    MAX_FETCH_REQUESTS_PER_RUN,
    MAX_FETCH_REQUESTS_PER_WINDOW,
    MarketCache,
)

SERVICE_VERSION = "engineering-session-service/v1"
# Directorio de sesiones DEDICADO del servicio de ingeniería: no colisiona
# con el raíz canónico del controlador anterior (`paper-lab-sessions/`);
# las sesiones existentes se conservan sin migración (el motor anida
# `paper-lab-sessions/` debajo del raíz dado).
SESSIONS_DEFAULT = (ROOT / "data" / "engineering-session" / "sessions")
PID_DEFAULT = ROOT / "data" / "engineering-session" / "service.json"
DEFAULT_PORT = 8797
DEFAULT_HOST = "127.0.0.1"
DEFAULT_CADENCE_MS = 700.0
# Techo de seguridad por conducción: nº máximo de eventos consumidos.
DRIVE_MAX_EVENTS = 4096

# --- Transporte market_stream (sesión live de ingeniería) -------------------
# Segundo transporte: el servicio de mercado EXISTENTE (market-stream/v1)
# publica eventos SSE y este adaptador los consume. Sin Binance directo en
# este proceso, sin otro colector ni gestor: solo un cliente SSE loopback.
TRANSPORT_LOCAL_REPLAY = "local_replay"
TRANSPORT_MARKET_STREAM = "market_stream"
ALLOWED_TRANSPORTS = {TRANSPORT_LOCAL_REPLAY, TRANSPORT_MARKET_STREAM}
MARKET_STREAM_PATH = "/stream"
# Default del URL del servicio de mercado (solo loopback; el adaptador
# rechaza fail-closed cualquier host no loopback).
DEFAULT_MARKET_URL = "http://127.0.0.1:8791"
DEFAULT_MARKET_BARS = 300
# Techo de nocional simulado por sesión live (tope explícito, no estrategia).
MAX_NOTIONAL_MARKET_STREAM = 1000.0
# Silencio del feed live (ms) a partir del cual la puerta de evaluación
# obliga a abstenerse con causa explícita.
LIVE_SILENCE_MS_DEFAULT = 120_000.0
# Tope de pasos de catch-up por evento de mercado (protección de bucle).
CATCH_UP_MAX_STEPS = 256
# Lectura del SSE: el servicio de mercado emite heartbeats ~cada 5 s; un
# silencio mayor aquí significa conexión muerta → reconexión con backoff.
# El timeout también cubre el connect.
SSE_READ_TIMEOUT_S = 10.0
SSE_BACKOFF_MAX_S = 5.0
# Paso de rejilla por intervalo (validación de huecos en la ventana).
INTERVAL_MS_MAP = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}
# Hosts aceptados para conexiones de datos (fail-closed).
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
# Registro de transporte por sesión (sobrevive reinicios del servicio).
# Vive en sessions_dir (FUERA de paper-lab-sessions/ para no interferir con
# el escaneo de sesiones del motor).
REGISTRY_FILENAME = "drive-registry.json"

ALLOWED_ACTIONS = {
    "start", "stop", "step", "exit", "restart", "stop_session", "evaluate",
}

CONFLICT_CODES = {"REVISION_CONFLICT", "SESSION_NOT_DRIVEABLE", "DRIVE_ACTIVE"}


def _now_ms() -> int:
    return int(time.time() * 1000)


# Máxima antigüedad admitida de la sincronización del reloj de referencia.
# Una sincronización más antigua que esto = referencia expirada: ahora_ms
# devuelve None y el llamador debe abstenerse (sin avanzar watermark ni
# evaluar). No existe fallback silencioso al reloj de pared no validado.
CLOCK_REFERENCE_MAX_AGE_MS = 60 * 60 * 1000  # 1 hora


def make_synced_now_ms(
    synchronizer: ClockSynchronizer,
    max_age_ms: float = CLOCK_REFERENCE_MAX_AGE_MS,
) -> Callable[[], Optional[int]]:
    """Devuelve el tiempo del backend sincronizado (pared + offset) o None.

    Devuelve None cuando no hay sincronización válida (offset ausente,
    sincronización expirada o nunca realizada). Nunca cae silenciosamente al
    reloj de pared no validado: ante incertidumbre devuelve None y el
    llamador abstiene.
    """
    def now() -> Optional[int]:
        if synchronizer.offset_ms is None \
                or synchronizer.last_sync_timestamp is None:
            return None
        try:
            last = datetime.fromisoformat(
                str(synchronizer.last_sync_timestamp))
        except ValueError:
            return None
        age_ms = (datetime.now(timezone.utc) - last).total_seconds() * 1000.0
        if age_ms > max_age_ms:
            return None
        return int(synchronizer._wall_clock_ms() + synchronizer.offset_ms)
    return now


# Presupuesto por defecto para sincronización de reloj público. Debe caber
# dentro de MAX_FETCH_REQUESTS_PER_WINDOW de la ventana de ledger compartida.
CLOCK_PUBLIC_MAX_REQUESTS = 5  # == ClockSynchronizer.sample_count por defecto


def _fetch_binance_server_time(timeout_seconds: float = 5.0) -> int:
    """Lee serverTime de Binance fapi (mismo contrato que ClockSynchronizer,
    sin modificar esa clase)."""
    request = urllib.request.Request(SERVER_TIME_URL, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read())
    return int(payload["serverTime"])


def _fetch_server_time_from_url(
        url: str, timeout_seconds: float = 5.0) -> int:
    """Lee serverTime de una URL dada (servidor loopback en pruebas).
    Mismo contrato que _fetch_binance_server_time (devuelve int de ms)."""
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read())
    return int(payload["serverTime"])


def _fetch_public_server_time(
        public_fetch_url: Optional[str] = None) -> Callable[[], int]:
    """Devuelve un fetch de serverTime sin argumentos.

    Si ``public_fetch_url`` se indica, llama a esa URL (servidor loopback en
    pruebas). De lo contrario, llama a Binance fapi.v1/time (produccion).
    """
    if public_fetch_url:
        return lambda: _fetch_server_time_from_url(public_fetch_url)
    return _fetch_binance_server_time


def _make_budgeted_time_fetch(
    cache: MarketCache,
    execution_id: str,
    max_requests: int,
    real_fetch: Callable[[], int],
    run_max_requests: Optional[int] = None,
) -> Callable[[], int]:
    """Devuelve un fetch de /time que RESERVA presupuesto ANTES de enviar.

    Cada intento (incluidos fallos) se contabiliza en
    ``market_fetch_ledger`` ANTES de abrir socket. Si la ventana o el
    presupuesto total de la corrida no permiten el intento, lanza
    ``UpstreamBudgetExceeded`` sin tocar la red.
    ClockSynchronizer cuenta una excepción como muestra fallida (no hay
    offset, por tanto ahora_ms -> None y abstención).
    """
    def fetch() -> int:
        row_id = cache.reserve_fetch_attempt(
            _now_ms(), symbol=None,
            detail=json.dumps(
                {"endpoint": "fapi_time", "source": SERVER_TIME_URL},
                sort_keys=True),
            max_requests=max_requests, execution_id=execution_id,
            run_max_requests=run_max_requests,
        )
        if row_id is None:
            raise UpstreamBudgetExceeded(
                "clock /time bloqueado antes del envio: presupuesto publico "
                "agotado")
        try:
            value = real_fetch()
        except Exception as exc:  # noqa: BLE001 - registrar y propagar
            cache.complete_fetch_row(
                row_id, status="connection_error", retries=0,
                note=json.dumps({"endpoint": "fapi_time", "error": str(exc)}))
            raise
        cache.complete_fetch_row(row_id, status="ok", retries=0,
                                 note=json.dumps({"endpoint": "fapi_time"}))
        return value
    return fetch


class LocalReplayTransport:
    """Reproductor local con cadencia: emite eventos de REVELADO.

    Cada evento comunica únicamente que la vela ``index`` de la ventana de
    operación se abre (su open pasa a conocerse en el reloj del motor). NO
    lleva OHLC: el precio es propiedad del estado del motor y el evaluador
    solo recibe el prefijo revelado por el motor tras interpretar cada evento.

    ``schedule`` son los ``open_time_ms`` de la ventana de operación (futuro
    oculto del transporte). Al final emite ``EOF`` para cerrar el transporte
    con causa visible; ``STOPPED`` si la conducción se pide parar.
    """

    def __init__(self, schedule: List[int],
                 event_queue: "queue.Queue[Dict[str, Any]]",
                 cadence_ms: float,
                 stop_event: threading.Event,
                 started_event: threading.Event) -> None:
        self.schedule = list(schedule)
        self.event_queue = event_queue
        self.cadence_ms = max(float(cadence_ms), 0.0)
        self.stop_event = stop_event
        self.started_event = started_event
        self.thread: Optional[threading.Thread] = None
        self.emitted = 0

    def start(self) -> None:
        self.thread = threading.Thread(
            target=self._run, name="local-replay-transport", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        self.started_event.set()
        cadence_s = self.cadence_ms / 1000.0
        for index, open_time_ms in enumerate(self.schedule):
            if self.stop_event.is_set():
                self.event_queue.put({"type": "STOPPED", "index": index})
                return
            self.event_queue.put({
                "type": "REVEAL",
                "index": index,
                "open_time_ms": open_time_ms,
            })
            self.emitted += 1
            if cadence_s > 0:
                end = time.monotonic() + cadence_s
                while time.monotonic() < end:
                    if self.stop_event.is_set():
                        self.event_queue.put({
                            "type": "STOPPED", "index": index})
                        return
                    time.sleep(min(0.02, cadence_s))
        self.event_queue.put({"type": "EOF"})


def _candle_from_frame(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extrae una vela cerrada de un frame del stream (o None si es inválida).

    Campos mínimos: open_time_ms + OHLC numéricos. ``close_time_ms`` es
    opcional (si falta se deriva del intervalo en el controlador).
    """
    try:
        open_ms = int(payload["open_time_ms"])
        o = float(payload["open"])
        h = float(payload["high"])
        l = float(payload["low"])
        c = float(payload["close"])
    except (KeyError, TypeError, ValueError):
        return None
    close_ms = payload.get("close_time_ms")
    try:
        close_ms = int(close_ms) if close_ms is not None else None
    except (TypeError, ValueError):
        close_ms = None
    return {
        "open_time_ms": open_ms, "open": o, "high": h, "low": l,
        "close": c, "close_time_ms": close_ms,
        "base_volume": payload.get("base_volume"),
    }


class MarketServiceStreamAdapter:
    """Cliente SSE contra el servicio de mercado EXISTENTE (market-stream/v1).

    Restricción fail-closed: SOLO acepta URLs ``http://127.0.0.1:<puerto>`` o
    ``http://localhost:<puerto>`` (loopback). Cualquier otro host se rechaza
    en construcción y la sesión no arranca.

    Responsabilidad única: traducir frames SSE en eventos de una cola. NO
    toca el estado de la sesión (el controlador, con el motor, es el único
    mutador). Reconecta con backoff ante caídas; los frames desconocidos se
    ignoran con contador; la vela provisional (frame ``candle``) solo se
    reporta como contador, nunca conduce.
    """

    def __init__(self, base_url: str, symbol: str, interval: str, bars: int,
                 event_queue: "queue.Queue[Dict[str, Any]]",
                 stop_event: threading.Event,
                 started_event: threading.Event,
                 from_ms: Optional[int] = None,
                 to_ms: Optional[int] = None) -> None:
        parsed = urlsplit(str(base_url or ""))
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "http" or host not in LOOPBACK_HOSTS:
            raise ValueError(
                f"MARKET_URL_NOT_LOOPBACK: {base_url!r} no es un URL de "
                "loopback (solo http://127.0.0.1:<puerto> o "
                "http://localhost:<puerto>)")
        port = parsed.port if parsed.port else 80
        self.base_url = f"http://{host}:{port}"
        self.symbol = str(symbol).upper()
        self.interval = str(interval)
        self.bars = max(int(bars), 1)
        self.from_ms = from_ms
        self.to_ms = to_ms
        params = [
            f"symbol={quote(self.symbol)}",
            f"interval={quote(self.interval)}",
            f"bars={self.bars}",
        ]
        if self.from_ms is not None:
            params.append(f"from_ms={int(self.from_ms)}")
        if self.to_ms is not None:
            params.append(f"to_ms={int(self.to_ms)}")
        self.stream_url = (
            self.base_url + MARKET_STREAM_PATH + "?" + "&".join(params))
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.started_event = started_event
        self.thread: Optional[threading.Thread] = None
        self.stats: Dict[str, Any] = {
            "frames": 0, "bad_frames": 0, "unknown_frames": 0,
            "provisional_frames": 0, "disconnects": 0, "reconnects": 0,
            "connect_errors": 0, "last_error": None,
            "last_frame_at_ms": None, "connected_at_ms": None,
            "started_at_ms": None,
        }

    @property
    def identity(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol, "interval": self.interval,
            "bars": self.bars, "base_url": self.base_url,
        }

    def start(self) -> None:
        self.thread = threading.Thread(
            target=self._run, name="market-stream-adapter", daemon=True)
        self.thread.start()

    # --- hilo del cliente SSE ------------------------------------------------
    def _run(self) -> None:
        self.started_event.set()
        self.stats["started_at_ms"] = _now_ms()
        while not self.stop_event.is_set():
            try:
                req = urllib.request.Request(
                    self.stream_url,
                    headers={"Accept": "text/event-stream"})
                resp = urllib.request.urlopen(
                    req, timeout=SSE_READ_TIMEOUT_S)
            except Exception as exc:  # noqa: BLE001 - superficie real
                self.stats["last_error"] = f"{type(exc).__name__}: {exc}"
                self.stats["connect_errors"] += 1
                self._put({
                    "type": "CONNECT_ERROR",
                    "detail": self.stats["last_error"],
                    "received_at_ms": _now_ms(),
                })
                if not self._backoff_wait():
                    return
                continue
            self.stats["connected_at_ms"] = _now_ms()
            try:
                self._read_stream(resp)
            except Exception as exc:  # noqa: BLE001 - timeout/conexión caída
                self.stats["last_error"] = f"{type(exc).__name__}: {exc}"
            finally:
                try:
                    resp.close()
                except OSError:  # pragma: no cover
                    pass
            if self.stop_event.is_set():
                return
            self.stats["disconnects"] += 1
            self.stats["reconnects"] += 1
            self._put({
                "type": "DISCONNECTED",
                "detail": self.stats["last_error"],
                "received_at_ms": _now_ms(),
            })
            if not self._backoff_wait():
                return

    def _backoff_wait(self) -> bool:
        """Espera con backoff exponencial acotado; False si hay parada."""
        attempt = max(int(self.stats.get("reconnects", 0)) - 1, 0)
        delay = min(0.5 * (2 ** attempt), SSE_BACKOFF_MAX_S)
        end = time.monotonic() + delay
        while time.monotonic() < end:
            if self.stop_event.is_set():
                return False
            time.sleep(min(0.05, delay))
        return not self.stop_event.is_set()

    def _read_stream(self, resp: Any) -> None:
        event_name: Optional[str] = None
        data_lines: List[str] = []
        while not self.stop_event.is_set():
            raw = resp.readline()
            if not raw:
                raise ConnectionError(
                    "SSE EOF (stream cerrado por el servicio)")
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line == "":
                if event_name is not None:
                    self._dispatch(event_name, "\n".join(data_lines))
                event_name = None
                data_lines = []
                continue
            if line.startswith(":"):
                continue  # comentario SSE
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
            # retry:/id:/otros campos: ignorados

    def _dispatch(self, name: str, data_text: str) -> None:
        self.stats["frames"] = int(self.stats["frames"]) + 1
        self.stats["last_frame_at_ms"] = _now_ms()
        try:
            payload = json.loads(data_text) if data_text else {}
        except json.JSONDecodeError:
            self.stats["bad_frames"] = int(self.stats["bad_frames"]) + 1
            return
        if not isinstance(payload, dict):
            self.stats["bad_frames"] = int(self.stats["bad_frames"]) + 1
            return
        received = _now_ms()
        if name == "hello":
            self._put({
                "type": "HELLO", "identity": payload.get("identity") or {},
                "service": payload.get("service"),
                "received_at_ms": received,
            })
        elif name == "snapshot":
            candles: List[Dict[str, Any]] = []
            for row in payload.get("candles") or []:
                if not isinstance(row, dict) or row.get("closed") is not True:
                    continue  # SOLO velas cerradas del snapshot
                candle = _candle_from_frame(row)
                if candle is not None:
                    candles.append(candle)
            self._put({
                "type": "SNAPSHOT", "candles": candles,
                "observed": payload.get("observed"),
                "received_at_ms": received,
            })
        elif name == "candle":
            # Vela provisional del feed: SOLO contador; nunca conduce.
            self.stats["provisional_frames"] = int(
                self.stats["provisional_frames"]) + 1
            self._put({
                "type": "PROVISIONAL",
                "open_time_ms": payload.get("open_time_ms"),
                "received_at_ms": received,
            })
        elif name == "closed":
            candle = _candle_from_frame(payload)
            if candle is None:
                self.stats["bad_frames"] = int(
                    self.stats["bad_frames"]) + 1
                return
            self._put({
                "type": "MARKET_CLOSED", "candle": candle,
                "received_at_ms": received,
            })
        elif name == "indicators":
            self._put({
                "type": "EVIDENCE", "evidence_kind": "indicators",
                "block": payload, "received_at_ms": received,
            })
        elif name == "context":
            self._put({
                "type": "EVIDENCE", "evidence_kind": "context_btc",
                "block": payload, "received_at_ms": received,
            })
        elif name == "gap":
            self._put({
                "type": "DATA_GAP", "detail": payload,
                "received_at_ms": received,
            })
        elif name == "status":
            self._put({
                "type": "STATUS", "block": payload,
                "received_at_ms": received,
            })
        elif name == "heartbeat":
            pass  # señal de vida; last_frame_at_ms ya quedó actualizado
        else:
            self.stats["unknown_frames"] = int(
                self.stats["unknown_frames"]) + 1

    def _put(self, event: Dict[str, Any]) -> None:
        self.event_queue.put(event)


class EngineeringSessionController:
    """Mantiene las sesiones y conduce el avance por eventos del transporte."""

    def __init__(self, sessions_dir: Path, cadence_ms: float,
                 market_url: Optional[str] = None,
                 market_bars: int = DEFAULT_MARKET_BARS,
                 live_silence_ms: float = LIVE_SILENCE_MS_DEFAULT,
                 now_ms: Optional[Callable[[], Optional[int]]] = None,
                 clock_sync: Optional[ClockSynchronizer] = None,
                 clock_source: Optional[str] = None) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.cadence_ms = float(cadence_ms)
        # Config live (transporte market_stream): URL del servicio de mercado
        # EXISTENTE (solo loopback; el adaptador valida fail-closed),
        # ventana del snapshot y silencio del feed para la puerta.
        self.market_url = (market_url
                           or os.environ.get("ENGINEERING_MARKET_SERVICE_URL")
                           or DEFAULT_MARKET_URL)
        self.market_bars = max(int(market_bars), 1)
        self.live_silence_ms = float(live_silence_ms)
        self._lock = threading.Lock()
        self._drives: Dict[str, Dict[str, Any]] = {}
        self._events: Dict[str, Dict[str, Any]] = {}
        # Dedupe de creación por request_id (idempotencia backend del POST
        # create; el guardia de React solo cubre el doble clic del navegador).
        self._create_results: Dict[str, Dict[str, Any]] = {}
        # Reloj de referencia independiente (contrato temporal de creación y
        # admisión de cierres). Tres estados explícitos:
        #   - referencia local controlada: now_ms inyectado (transporte de
        #     prueba).
        #   - referencia pública validada: clock_sync (ClockSynchronizer) con
        #     offset + RTT + estado de sincronización; ahora_ms devuelve None
        #     si no está sincronizado o la sincronización expiró.
        #   - referencia no disponible: ahora_ms devuelve None → abstención.
        # No existe fallback silencioso al reloj de pared no validado.
        self._clock_sync = clock_sync
        if clock_sync is not None:
            self._now_ms = make_synced_now_ms(
                clock_sync, CLOCK_REFERENCE_MAX_AGE_MS)
            self._clock_source = clock_source or "public_sincronizado"
        else:
            # Referencia local explícita (reloj de pared local o reloj
            # inyectado por pruebas). Cero solicitudes públicas. Nunca se usa
            # como si fuera tiempo validado de Binance.
            self._now_ms = now_ms or _now_ms
            if clock_source is not None:
                self._clock_source = clock_source
            elif now_ms is not None:
                # Reloj inyectado/controlado de prueba (no el pared del
                # sistema): identidad explícita para el observador.
                self._clock_source = "local_inyectado"
            else:
                self._clock_source = "local_sistema"

    # --- estado público del reloj de referencia -----------------------------
    def _clock_public_state(self) -> Dict[str, Any]:
        """Fuente, última sincronización, offset, RTT y estado de validez.

        Cuatro estados explícitos:
          - local_sistema: reloj de pared del servicio, cero públicas.
          - local_inyectado: reloj controlado por pruebas, cero públicas.
          - public_sincronizado: ClockSynchronizer sincronizado y vigente.
          - referencia no disponible/expirada: available False.
        """
        sync = self._clock_sync
        if sync is None:
            # Referencia local (sistema o inyectado): disponible por
            # definición, cero solicitudes públicas.
            return {
                "source": self._clock_source,
                "available": True,
                "reason": None,
            }
        snap = sync.snapshot()
        offset = snap.get("clockOffsetMs")
        ts = snap.get("lastClockSyncTimestamp")
        available = offset is not None and ts is not None
        age_ms: Optional[float] = None
        if available:
            try:
                last = datetime.fromisoformat(str(ts))
                age_ms = (
                    datetime.now(timezone.utc) - last
                ).total_seconds() * 1000.0
                if age_ms > CLOCK_REFERENCE_MAX_AGE_MS:
                    available = False
            except (ValueError, TypeError):
                available = False
        return {
            "source": self._clock_source,
            "available": available,
            "offset_ms": offset,
            "rtt_ms": snap.get("serverTimeRttMs"),
            "last_sync_timestamp": ts,
            "age_ms": None if age_ms is None else round(age_ms, 6),
            "sync_successful": snap.get("clockSyncSuccessful"),
            "sync_failed": snap.get("clockSyncFailed"),
            "samples_valid": snap.get("clockSamplesValid"),
            "samples_failed": snap.get("clockSamplesFailed"),
        }

    # --- utilidades ---------------------------------------------------------
    def _load_state(self, session_id: str):
        if not engine._safe_session_id(session_id):
            raise ValueError("session_id inválido")
        return engine.load_session(session_id, str(self.sessions_dir))

    @staticmethod
    def _parse_config(raw: Dict[str, Any]) -> engine.PaperSessionConfig:
        return engine.PaperSessionConfig(
            symbol=str(raw["symbol"]), interval=str(raw["interval"]),
            direction=str(raw["direction"]),
            notional_usdt=float(raw["notional_usdt"]),
            entry_px=float(raw["entry_px"]), stop_px=float(raw["stop_px"]),
            stop_distance_pct=float(raw["stop_distance_pct"]),
            horizon_ms=int(raw["horizon_ms"]), fee_bps=float(raw["fee_bps"]),
            spread_bps=float(raw["spread_bps"]),
            slippage_bps=float(raw["slippage_bps"]),
            hypothesis_id=raw.get("hypothesis_id"),
            hypothesis_version=raw.get("hypothesis_version"),
            rule_version=raw.get("rule_version"),
            # create NO acepta decision: viene de evaluate (motor).
            decision=None,
            decision_reason=None,
            decision_evidence=None,
        )

    def _save(self, state, expected_revision: Optional[int],
              request_id: Optional[str]):
        res = engine.save_session(
            state, str(self.sessions_dir),
            expected_revision=expected_revision,
            request_id=request_id)
        if not res.ok:
            raise RuntimeError(
                res.error_code or "SAVE_FAILED",
                res.error_detail or "fallo al guardar")
        return res.state

    # --- registro de transporte live (persistente) ---------------------------
    def _registry_path(self) -> Path:
        return self.sessions_dir / REGISTRY_FILENAME

    def _load_registry(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = json.loads(
                self._registry_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        sessions = data.get("sessions") if isinstance(data, dict) else None
        return sessions if isinstance(sessions, dict) else {}

    def _registry_entry(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._load_registry().get(session_id)

    def _register_live_session(self, session_id: str,
                               entry: Dict[str, Any]) -> None:
        sessions = self._load_registry()
        sessions[session_id] = entry
        self._write_registry(sessions)

    def _unregister_session(self, session_id: str) -> None:
        sessions = self._load_registry()
        if session_id in sessions:
            del sessions[session_id]
            self._write_registry(sessions)

    def _write_registry(self, sessions: Dict[str, Dict[str, Any]]) -> None:
        path = self._registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps({"version": 1, "sessions": sessions},
                       ensure_ascii=False, indent=1),
            encoding="utf-8")
        os.replace(tmp, path)

    def drive_view(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            drive = self._drives.get(session_id)
            info = self._events.get(session_id)
        if drive is None:
            # Sin drive en memoria: el transporte persistido (registro) da
            # la identidad del transporte para que el observador (UI) sepa
            # cómo se conduce esta sesión tras un reinicio del servicio.
            registry = self._registry_entry(session_id)
            if registry:
                return {
                    "state": "idle",
                    "session_id": session_id,
                    "runner": registry.get("transport"),
                    "market_url": registry.get("market_url"),
                    "bars": registry.get("bars"),
                }
            return {"state": "idle", "session_id": session_id}
        return self._drive_public(drive, info)

    def _drive_public(self, drive: Optional[Dict[str, Any]],
                      info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if drive is None:
            return {"state": "idle"}
        runner = drive.get("runner", TRANSPORT_LOCAL_REPLAY)
        out: Dict[str, Any] = {
            "state": drive["state"],
            "cause": drive.get("cause"),
            "started_at_ms": drive.get("started_at_ms"),
            "finished_at_ms": drive.get("finished_at_ms"),
            "events_processed": drive.get("events_processed", 0),
            "transport_events": (info or {}).get("transport_events", 0),
            "cadence_ms": drive.get("cadence_ms"),
            "runner": runner,
            "evaluacion_contador": int(drive.get("evaluacion_contador", 0)),
            "evaluaciones": list(drive.get("evaluaciones") or []),
        }
        if runner == TRANSPORT_MARKET_STREAM:
            adapter = drive.get("transport")
            out.update({
                "market_url": drive.get("market_url"),
                "bars": drive.get("bars"),
                "live_silence_ms": drive.get("live_silence_ms"),
                "watermark": drive.get("watermark"),
                "last_trigger": drive.get("last_trigger"),
                "last_gate": drive.get("last_gate"),
                "last_gap": drive.get("last_gap"),
                "last_status": drive.get("last_status"),
                "evidence": drive.get("evidence") or {},
                "stats": dict(adapter.stats) if adapter is not None else {},
            })
        return out

    # --- endpoints ----------------------------------------------------------
    def list_sessions(self) -> List[Dict[str, Any]]:
        rows = engine.list_sessions(str(self.sessions_dir))
        with self._lock:
            drives = {sid: self._drive_public(d, self._events.get(sid))
                      for sid, d in self._drives.items()}
        for row in rows:
            sid = row.get("session_id")
            if sid is not None and sid in drives:
                row["drive"] = drives[sid]
        return rows

    # --- validación de contexto contra el reloj de referencia --------------
    def _validar_contexto_temporal(
        self, raw_context: List[Dict[str, Any]], step: int,
        default_symbol: str,
    ) -> None:
        """Valida el contexto de creación contra el reloj de referencia.

        Rechaza ANTES de crear/iniciar: contexto insuficiente, cierre futuro
        (``close_time`` posterior a la referencia, sin tolerancia positiva de
        un intervalo), vela no cerrada y serie discontinua. Ante incertidumbre
        del reloj de referencia se abstiene con motivo: no se crea la sesión
        ni se fija T desde un cierre no acreditado como ocurrido.
        """
        now = self._now_ms()
        if now is None:
            raise ValueError(
                "RELOJ_REFERENCIA_INCERTO: no hay tiempo de referencia "
                "validado para admitir el contexto cerrado (sincronización "
                "del backend pendiente o fallida)")
        if len(raw_context) < 1:
            raise ValueError(
                "CONTEXTO_INSUFICIENTE: se requiere al menos una vela de "
                "contexto para fijar el reloj T inicial")
        por_simbolo: Dict[str, List[Dict[str, Any]]] = {}
        for c in raw_context:
            por_simbolo.setdefault(
                str(c.get("symbol") or default_symbol), []).append(c)
        for simbolo, velas in por_simbolo.items():
            velas.sort(key=lambda c: int(c["open_time_ms"]))
            prev_open: Optional[int] = None
            for c in velas:
                ot = int(c["open_time_ms"])
                ct = int(c.get("close_time_ms") or (ot + step - 1))
                if ct is None or ct <= ot:
                    raise ValueError(
                        f"CONTEXTO_NO_CERRADO: {simbolo} vela open_time {ot} "
                        f"no tiene cierre disponible (close_time={ct})")
                if ct > now:
                    raise ValueError(
                        f"CONTEXTO_FUTURO: {simbolo} vela open_time {ot} "
                        f"cierra en {ct}, posterior a la referencia {now}; "
                        f"el cierre todavía no ocurrió (no se fija T desde "
                        f"un cierre no acreditado)")
                if prev_open is not None and ot - prev_open != step:
                    raise ValueError(
                        f"CONTEXTO_DISCONTINUO: {simbolo} hueco entre "
                        f"{prev_open} y {ot} (delta {ot - prev_open} ms, se "
                        f"esperaba {step} ms)")
                prev_open = ot

    def create_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_id = payload.get("request_id")
        if request_id:
            cached = self._create_results.get(str(request_id))
            if cached is not None:
                # Idempotencia backend: el mismo request_id devuelve la MISMA
                # sesión creada (sin duplicar).
                return cached
        transport = str(payload.get("transport") or TRANSPORT_LOCAL_REPLAY)
        if transport not in ALLOWED_TRANSPORTS:
            raise ValueError(
                f"transporte no permitido: {transport} (permitidos: "
                f"{sorted(ALLOWED_TRANSPORTS)})")
        config = self._parse_config(payload["config"])
        if transport == TRANSPORT_MARKET_STREAM:
            # Live: la ventana de operación llega por eventos del servicio de
            # mercado; create SOLO lleva contexto (candles=[] obligatorio).
            if payload.get("candles"):
                raise ValueError(
                    "LIVE_CANDLES_FORBIDDEN: en transporte market_stream la "
                    "ventana de operación la produce el feed; create solo "
                    "acepta contexto (candles=[])")
            candles: List[Dict[str, Any]] = []
            raw_context = payload.get("context") or []
            if not raw_context:
                raise ValueError(
                    "LIVE_CONTEXT_REQUIRED: la sesión live necesita contexto "
                    "(ventana de velas cerradas conocidas) para fijar el "
                    "reloj T inicial")
            step = INTERVAL_MS_MAP.get(str(config.interval))
            if step is None:
                raise ValueError(
                    f"INTERVALO_NO_SOPORTADO: {config.interval}")
            # Validación de contexto contra el reloj de referencia (antes de
            # crear/iniciar): rechaza cierre futuro, vela no cerrada o
            # serie discontinua con motivo explícito. No se fija T desde un
            # cierre cuyo close_time sea futuro respecto a la referencia.
            self._validar_contexto_temporal(raw_context, step, config.symbol)
            from_ms = payload.get("from_ms")
            to_ms = payload.get("to_ms")
            if config.notional_usdt > MAX_NOTIONAL_MARKET_STREAM:
                raise ValueError(
                    f"NOTIONAL_CAP: nocional {config.notional_usdt} USDT "
                    f"supera el tope live {MAX_NOTIONAL_MARKET_STREAM} USDT")
        else:
            candles = [engine.PaperCandle(
                open_time_ms=int(r["open_time_ms"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]),
                close_time_ms=int(r["close_time_ms"]),
            ) for r in payload.get("candles") or []]
            raw_context = payload.get("context") or []
        context = [engine.PaperCandle(
            open_time_ms=int(r["open_time_ms"]), open=float(r["open"]),
            high=float(r["high"]), low=float(r["low"]),
            close=float(r["close"]),
            close_time_ms=int(r["close_time_ms"]),
        ) for r in raw_context]
        state = engine.create_session(
            config, candles, context,
            hypothesis_id=payload.get("hypothesis_id"),
            hypothesis_version=payload.get("hypothesis_version"),
            rule_version=payload.get("rule_version"),
        )
        state = self._save(state, None, request_id)
        result: Dict[str, Any] = {
            "session": engine.session_to_public_dict(state),
            "transport": transport,
        }
        if transport == TRANSPORT_MARKET_STREAM:
            self._register_live_session(state.session_id, {
                "transport": transport,
                "symbol": config.symbol,
                "interval": config.interval,
                "bars": self.market_bars,
                "market_url": self.market_url,
                "live_silence_ms": self.live_silence_ms,
                "from_ms": from_ms,
                "to_ms": to_ms,
            })
        if request_id:
            self._create_results[str(request_id)] = result
        return result

    def get_session(self, session_id: str) -> Dict[str, Any]:
        state = self._load_state(session_id)
        if state is None:
            raise KeyError("SESSION_NOT_FOUND")
        public = engine.session_to_public_dict(state, state.clock_ms)
        # Forma uniforme con el control: {session, drive} (drive como
        # hermano, no anidado dentro del estado del motor).
        return {"session": public, "drive": self.drive_view(session_id)}

    # --- acciones -----------------------------------------------------------
    def control(self, session_id: str, payload: Dict[str, Any]):
        action = str(payload.get("action") or "")
        if action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"acción no permitida: {action} (permitidas: "
                f"{sorted(ALLOWED_ACTIONS)})")
        expected_revision = payload.get("expected_revision")
        request_id = payload.get("request_id")
        if action in ("start", "stop"):
            with self._lock:
                if action == "start":
                    return self._start_drive(session_id, expected_revision)
                return self._stop_drive(session_id)
        return self._advance_action(
            session_id, action, expected_revision, request_id)

    # --- conducción ---------------------------------------------------------
    def _start_drive(self, session_id: str,
                     expected_revision: Optional[int]) -> Dict[str, Any]:
        state = self._load_state(session_id)
        if state is None:
            raise KeyError("SESSION_NOT_FOUND")
        drive = self._drives.get(session_id)
        if drive is not None and drive["state"] == "running":
            # Idempotencia: start repetido no crea un segundo reproductor.
            return {
                "session": engine.session_to_public_dict(state, state.clock_ms),
                "drive": self._drive_public(drive, self._events.get(session_id)),
            }
        if state.status in ("cerrada", "detenida"):
            raise RuntimeError(
                "SESSION_NOT_DRIVEABLE",
                f"estado {state.status} no admite conducción")
        if expected_revision is not None and state.revision != expected_revision:
            raise RuntimeError(
                "REVISION_CONFLICT",
                f"revision {state.revision} != esperada {expected_revision}")

        stop_event = threading.Event()
        started_event = threading.Event()
        event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        registry = self._registry_entry(session_id)
        transport_kind = ((registry or {}).get("transport")
                          or TRANSPORT_LOCAL_REPLAY)
        if transport_kind == TRANSPORT_MARKET_STREAM:
            if state.config.notional_usdt > MAX_NOTIONAL_MARKET_STREAM:
                raise RuntimeError(
                    "NOTIONAL_CAP",
                    f"nocional {state.config.notional_usdt} USDT supera el "
                    f"tope live {MAX_NOTIONAL_MARKET_STREAM} USDT")
            market_url = str((registry or {}).get("market_url")
                             or self.market_url)
            bars = int((registry or {}).get("bars") or self.market_bars)
            silence = float((registry or {}).get("live_silence_ms")
                            or self.live_silence_ms)
            from_ms = (registry or {}).get("from_ms")
            to_ms = (registry or {}).get("to_ms")
            try:
                transport_obj: Any = MarketServiceStreamAdapter(
                    market_url, state.config.symbol,
                    state.config.interval, bars, event_queue, stop_event,
                    started_event, from_ms=from_ms, to_ms=to_ms)
            except ValueError as exc:
                raise RuntimeError("MARKET_URL_NOT_LOOPBACK", str(exc))
            drive = {
                "state": "running",
                "started_at_ms": _now_ms(),
                "finished_at_ms": None,
                "events_processed": 0,
                "cause": None,
                "stop_event": stop_event,
                "queue": event_queue,
                "transport": transport_obj,
                "runner": TRANSPORT_MARKET_STREAM,
                "market_url": transport_obj.base_url,
                "bars": bars,
                "live_silence_ms": silence,
                "symbol": state.config.symbol,
                "interval": state.config.interval,
                "watermark": None,
                "last_trigger": None,
                "last_gate": None,
                "last_gap": None,
                "last_status": None,
                "last_heartbeat_at_ms": None,
                "evidence": {},
                "cadence_ms": None,
                # Registro de evaluaciones ejecutadas por el evaluador (motor).
                # Cada entrada: evaluacion_num, evento_disparador, T, config,
                # resultado (decisión/motivo), evaluado_en_ms.
                "evaluaciones": [],
                "evaluacion_contador": 0,
            }
            self._drives[session_id] = drive
            self._events[session_id] = {"transport_events": 0}
            transport_obj.start()
            thread = threading.Thread(
                target=self._run_drive_market, args=(session_id,),
                name=f"drive-live-{session_id[:24]}", daemon=True)
        else:
            schedule = [c.open_time_ms for c in state.candles]
            transport_obj = LocalReplayTransport(
                schedule, event_queue, self.cadence_ms, stop_event,
                started_event)
            drive = {
                "state": "running",
                "started_at_ms": _now_ms(),
                "finished_at_ms": None,
                "events_processed": 0,
                "cause": None,
                "stop_event": stop_event,
                "queue": event_queue,
                "transport": transport_obj,
                "runner": TRANSPORT_LOCAL_REPLAY,
                "cadence_ms": self.cadence_ms,
            }
            self._drives[session_id] = drive
            self._events[session_id] = {"transport_events": 0}
            transport_obj.start()
            thread = threading.Thread(
                target=self._run_drive, args=(session_id,),
                name=f"drive-{session_id[:24]}", daemon=True)
        thread.start()
        started_event.wait(timeout=2.0)
        return {
            "session": engine.session_to_public_dict(state, state.clock_ms),
            "drive": self._drive_public(drive, self._events.get(session_id)),
        }

    def _stop_drive(self, session_id: str) -> Dict[str, Any]:
        state = self._load_state(session_id)
        if state is None:
            raise KeyError("SESSION_NOT_FOUND")
        drive = self._drives.get(session_id)
        if drive is not None and drive["state"] == "running":
            drive["stop_requested"] = True
            drive["queue"].put({"type": "STOPPED"})
            # El hilo de conducción termina en el próximo límite de evento.
        return {
            "session": engine.session_to_public_dict(state, state.clock_ms),
            "drive": self._drive_public(drive, self._events.get(session_id)),
        }

    def _stop_drive_quiet(self, session_id: str) -> None:
        with self._lock:
            drive = self._drives.get(session_id)
        if drive is not None and drive["state"] == "running":
            drive["stop_requested"] = True
            drive["queue"].put({"type": "STOPPED"})

    def _advance_action(self, session_id: str, action: str,
                        expected_revision: Optional[int],
                        request_id: Optional[str]) -> Dict[str, Any]:
        state = self._load_state(session_id)
        if state is None:
            raise KeyError("SESSION_NOT_FOUND")
        with self._lock:
            drive = self._drives.get(session_id)
            drive_running = drive is not None and drive["state"] == "running"
        if drive_running:
            raise RuntimeError(
                "DRIVE_ACTIVE",
                "la conducción autónoma está activa; pásela a stop antes de "
                "una acción manual")
        if expected_revision is not None and state.revision != expected_revision:
            raise RuntimeError(
                "REVISION_CONFLICT",
                f"revision {state.revision} != esperada {expected_revision}")
        if action == "step":
            state = self.advance_once(state, request_id=request_id)
        elif action == "exit":
            state = engine.manual_exit(state)
            state = self._save(state, expected_revision, request_id)
        elif action == "restart":
            state = engine.restart_session(state)
            state = self._save(state, expected_revision, request_id)
        elif action == "stop_session":
            self._stop_drive_quiet(session_id)
            state = self._load_state(session_id) or state
            if state.status not in ("cerrada", "detenida"):
                state = engine.stop_session(state)
                state = self._save(state, expected_revision, request_id)
        elif action == "evaluate":
            state = engine.evaluate_session(
                state,
                hypothesis_id=state.config.hypothesis_id,
                hypothesis_version=state.config.hypothesis_version,
                rule_version=state.config.rule_version,
                at_ms=state.clock_ms,
            )
            state = self._save(state, expected_revision, request_id)
        return {
            "session": engine.session_to_public_dict(state, state.clock_ms),
            "drive": self.drive_view(session_id),
        }

    def advance_once(self, state, request_id: Optional[str] = None):
        """Un evento del transporte interpretado por el motor Python.

        El motor es la única autoridad económica: cada evento de revelado
        avanza exactamente un paso (step_forward) y, si la única decisión
        vigente es abstención temporal, reevalua en el reloj recién conocido.
        Descartes terminales y sesiones cerradas no se reevaluan.
        """
        if state.status in ("cerrada", "detenida"):
            return state
        prev_revision = state.revision
        next_state = engine.step_forward(state)
        if next_state.status == state.status and \
                next_state.clock_ms == state.clock_ms and \
                next_state.cursor == state.cursor:
            # Sin vela por revelar: fin del transporte local (sin cambios).
            return state
        if next_state.status in ("sin_iniciar", "evaluando") and (
                next_state.config.decision in (None, "SIN_ENTRADA")):
            next_state = engine.evaluate_session(
                next_state,
                hypothesis_id=next_state.config.hypothesis_id,
                hypothesis_version=next_state.config.hypothesis_version,
                rule_version=next_state.config.rule_version or engine.RULE_CAUSAL_V1,
                at_ms=next_state.clock_ms,
            )
        return self._save(next_state, prev_revision, request_id)

    # --- hilo de conducción -------------------------------------------------
    def _run_drive(self, session_id: str) -> None:
        drive = self._drives.get(session_id)
        if drive is None:  # pragma: no cover
            return
        stop_event: threading.Event = drive["stop_event"]
        event_queue = drive["queue"]
        with self._lock:
            info = self._events.setdefault(
                session_id, {"transport_events": 0})
        while True:
            if stop_event.is_set():
                self._finish_drive(session_id, drive, "OPERATOR_STOP")
                break
            try:
                event = event_queue.get(
                    timeout=max(self.cadence_ms / 1000.0, 0.05))
            except queue.Empty:
                continue
            ev_type = event.get("type")
            with self._lock:
                if drive["state"] != "running":
                    continue
                if ev_type == "STOPPED":
                    self._finish_drive(session_id, drive, "OPERATOR_STOP")
                    break
                if ev_type == "EOF":
                    # El transporte local terminó: la sesión queda como está
                    # (sin cierre inventado); causa visible en la conducción.
                    self._finish_drive(session_id, drive, "END_OF_TRANSPORT")
                    break
                if ev_type != "REVEAL":
                    continue
                info["transport_events"] = int(info.get(
                    "transport_events", 0)) + 1
            drive["events_processed"] += 1
            try:
                state = self.advance_once(
                    self._load_state(session_id),
                    request_id=(f"drive-{session_id}-"
                                f"{drive['events_processed']}-{_now_ms()}"))
            except Exception as exc:  # noqa: BLE001 - superficie real
                self._finish_drive(
                    session_id, drive,
                    f"DRIVE_ERROR:{type(exc).__name__}: {exc}")
                break
            if state is None:
                self._finish_drive(session_id, drive, "SESSION_NOT_FOUND")
                break
            if state.status in ("cerrada", "detenida"):
                cause = ("SESSION_CLOSED" if state.status == "cerrada"
                         else "SESSION_STOPPED")
                self._finish_drive(session_id, drive, cause)
                break
            if drive["events_processed"] >= DRIVE_MAX_EVENTS:  # pragma: no cover
                self._finish_drive(
                    session_id, drive,
                    f"DRIVE_EVENT_LIMIT ({DRIVE_MAX_EVENTS})")
                break

    # --- conducción live (transporte market_stream) --------------------------
    def _run_drive_market(self, session_id: str) -> None:
        """Conducción por eventos del servicio de mercado (SSE traducido).

        El adaptador SOLO publica eventos en la cola; este bucle es el único
        mutador del estado (vía el motor). La vela provisional y los frames
        desconocidos no conducen; los duplicados se ignoran por marca de
        agua (open_time) sin duplicar decisiones, fills ni cierres.
        """
        drive = self._drives.get(session_id)
        if drive is None:  # pragma: no cover
            return
        stop_event: threading.Event = drive["stop_event"]
        event_queue = drive["queue"]
        adapter = drive["transport"]
        with self._lock:
            info = self._events.setdefault(
                session_id, {"transport_events": 0})
        while True:
            if stop_event.is_set():
                self._finish_drive(session_id, drive, "OPERATOR_STOP")
                break
            try:
                event = event_queue.get(timeout=0.5)
            except queue.Empty:
                if not adapter.thread.is_alive() and event_queue.empty():
                    self._finish_drive(session_id, drive, "TRANSPORT_LOST")
                    break
                # Feed en silencio (sin frames): señal VISIBLE en la puerta
                # sin tocar la sesión (no se inventan decisiones).
                last_frame = adapter.stats.get("last_frame_at_ms")
                limit = float(drive.get("live_silence_ms")
                              or self.live_silence_ms)
                if last_frame is not None \
                        and _now_ms() - int(last_frame) > limit \
                        and (drive.get("last_gate") or {}).get("cause") \
                        != "FEED_SILENCE":
                    drive["last_gate"] = {
                        "evaluated_at_ms": _now_ms(),
                        "clock_ms": None,
                        "silence_ms": _now_ms() - int(last_frame),
                        "live_silence_ms": limit,
                        "ok": False,
                        "cause": "FEED_SILENCE",
                        "note": "feed en silencio (sin frames); la sesión "
                                "conserva su última decisión sin reevaluar",
                    }
                continue
            ev_type = event.get("type")
            with self._lock:
                if drive["state"] != "running":
                    continue
                if ev_type == "STOPPED":
                    self._finish_drive(session_id, drive, "OPERATOR_STOP")
                    break
            info["transport_events"] = int(
                info.get("transport_events", 0)) + 1
            received_at = int(event.get("received_at_ms") or _now_ms())
            state = None
            finish_cause: Optional[str] = None
            try:
                if ev_type == "HELLO":
                    identity = event.get("identity") or {}
                    if (str(identity.get("symbol") or "").upper()
                            != str(drive["symbol"]).upper()
                            or str(identity.get("interval") or "")
                            != str(drive["interval"])):
                        finish_cause = "IDENTITY_MISMATCH"
                    else:
                        drive["hello"] = {
                            "identity": identity,
                            "service": event.get("service"),
                            "received_at_ms": received_at,
                        }
                elif ev_type == "SNAPSHOT":
                    state = self._consume_snapshot(
                        session_id, drive,
                        event.get("candles") or [], received_at)
                elif ev_type == "MARKET_CLOSED":
                    state = self._consume_market_closed(
                        session_id, drive, event.get("candle"), received_at)
                elif ev_type == "PROVISIONAL":
                    # Solo contador: la vela provisional nunca conduce.
                    info["provisional_ignored"] = int(
                        info.get("provisional_ignored", 0)) + 1
                elif ev_type == "EVIDENCE":
                    drive["evidence"][event.get("evidence_kind") or ""] = {
                        "block": event.get("block"),
                        "received_at_ms": received_at,
                    }
                elif ev_type == "DATA_GAP":
                    drive["last_gap"] = {
                        "detail": event.get("detail"),
                        "received_at_ms": received_at,
                    }
                elif ev_type == "STATUS":
                    drive["last_status"] = {
                        "block": event.get("block"),
                        "received_at_ms": received_at,
                    }
                elif ev_type == "HEARTBEAT":
                    drive["last_heartbeat_at_ms"] = received_at
                elif ev_type in ("DISCONNECTED", "CONNECT_ERROR"):
                    info["disconnects"] = int(
                        info.get("disconnects", 0)) + 1
                    drive["last_disconnect"] = {
                        "type": ev_type, "detail": event.get("detail"),
                        "received_at_ms": received_at,
                    }
                # Otros tipos: ignorados (fail-safe).
            except KeyError as exc:
                finish_cause = (str(exc).strip("'\" ()")
                                or "SESSION_NOT_FOUND")
            except Exception as exc:  # noqa: BLE001 - superficie real
                finish_cause = f"DRIVE_ERROR:{type(exc).__name__}: {exc}"
            if finish_cause is not None:
                self._finish_drive(session_id, drive, finish_cause)
                break
            if state is None:
                continue
            if state.status in ("cerrada", "detenida"):
                cause = ("SESSION_CLOSED" if state.status == "cerrada"
                         else "SESSION_STOPPED")
                self._finish_drive(session_id, drive, cause)
                break

    def _consume_snapshot(self, session_id: str, drive: Dict[str, Any],
                          rows: List[Any], received_at: int):
        """Fusiona velas cerradas de un snapshot (reconexión / arranque).

        Solo velas con open_time > reloj de la sesión (el resto es contexto
        ya conocido); marca de agua evita reprocesar tras reconexión.
        """
        state = self._load_state(session_id)
        if state is None:
            raise KeyError("SESSION_NOT_FOUND")
        if state.status in ("cerrada", "detenida"):
            return state
        appended = 0
        max_admitted_open = 0
        with self._lock:
            watermark = int(drive.get("watermark") or 0)
        # Referencia temporal independiente: un cierre del snapshot cuya
        # disponibilidad no queda acreditada (futuro o referencia incierta)
        # no se admite ni avanza la marca de agua.
        now = self._now_ms()
        for row in rows:
            candle = row if isinstance(row, dict) else None
            if candle is None or candle.get("open_time_ms") is None:
                with self._lock:
                    info = self._events.setdefault(session_id, {})
                    info["bad_candles"] = int(
                        info.get("bad_candles", 0)) + 1
                continue
            ot = int(candle["open_time_ms"])
            if ot <= watermark or ot <= (state.clock_ms or 0):
                with self._lock:
                    info = self._events.setdefault(session_id, {})
                    info["duplicates_ignored"] = int(
                        info.get("duplicates_ignored", 0)) + 1
                continue
            paper = self._paper_candle_from_frame(
                state, candle, received_at)
            if paper is None:
                with self._lock:
                    info = self._events.setdefault(session_id, {})
                    info["bad_candles"] = int(
                        info.get("bad_candles", 0)) + 1
                continue
            if now is None or paper.close_time_ms > now:
                # Cierre futuro o referencia incierta: no admitir el cierre,
                # no avanzar watermark; el mismo cierre puede reenviarse cuando
                # la referencia acredite que ocurrió.
                with self._lock:
                    info = self._events.setdefault(session_id, {})
                    info["snapshot_cierre_no_acreditado"] = int(
                        info.get("snapshot_cierre_no_acreditado", 0)) + 1
                continue
            max_admitted_open = max(max_admitted_open, ot)
            state = dc_replace(
                state,
                candles=self._merge_operation_candle(state.candles, paper),
                revision=state.revision + 1)
            appended += 1
        with self._lock:
            drive["watermark"] = max(int(drive.get("watermark") or 0),
                                     max_admitted_open)
        if appended == 0:
            return None
        self._record_feed_gap(drive, received_at)
        drive["last_trigger"] = {
            "frame": "snapshot", "appended": appended,
            "received_at_ms": received_at,
        }
        return self._live_advance(session_id, state, drive,
                                  drive["last_trigger"],
                                  expected_revision=state.revision - appended)

    def _consume_market_closed(self, session_id: str, drive: Dict[str, Any],
                               candle: Optional[Dict[str, Any]],
                               received_at: int):
        """Consume una vela CERRADA del feed: fusiona, avanza y evalúa.

        Dedupe por marca de agua (open_time) y por reloj de la sesión: un
        duplicado o una vela vieja no produce segunda decisión, fill ni
        cierre (revisión sin cambios).
        """
        if not candle or candle.get("open_time_ms") is None:
            with self._lock:
                info = self._events.setdefault(session_id, {})
                info["bad_candles"] = int(info.get("bad_candles", 0)) + 1
            return None
        ot = int(candle["open_time_ms"])
        with self._lock:
            watermark = int(drive.get("watermark") or 0)
            if ot <= watermark:
                info = self._events.setdefault(session_id, {})
                info["duplicates_ignored"] = int(
                    info.get("duplicates_ignored", 0)) + 1
                return None
        state = self._load_state(session_id)
        if state is None:
            raise KeyError("SESSION_NOT_FOUND")
        if state.status in ("cerrada", "detenida"):
            return state
        if ot <= (state.clock_ms or 0):
            # Vela del contexto o ya conocida: sin efecto en la sesión.
            with self._lock:
                drive["watermark"] = max(watermark, ot)
                info = self._events.setdefault(session_id, {})
                info["duplicates_ignored"] = int(
                    info.get("duplicates_ignored", 0)) + 1
            return None
        paper = self._paper_candle_from_frame(state, candle, received_at)
        if paper is None:
            with self._lock:
                drive["watermark"] = max(watermark, ot)
                info = self._events.setdefault(session_id, {})
                info["bad_candles"] = int(info.get("bad_candles", 0)) + 1
            return None
        now = self._now_ms()
        if now is None or paper.close_time_ms > now:
            # Cierre no acreditado como ocurrido (referencia incierta o cierre
            # futuro sin tolerancia positiva de intervalo): provisional. No se
            # fusiona ni avanza el reloj ni la marca de agua; el mismo cierre
            # puede reenviarse cuando la referencia acredite que ocurrió.
            return None
        with self._lock:
            drive["watermark"] = max(watermark, ot)
        self._record_feed_gap(drive, received_at)
        drive["last_trigger"] = {
            "frame": "closed", "open_time_ms": ot,
            "close_time_ms": paper.close_time_ms,
            "received_at_ms": received_at,
            "available_at_ms": ot,
        }
        state = dc_replace(
            state,
            candles=self._merge_operation_candle(state.candles, paper),
            revision=state.revision + 1)
        return self._live_advance(session_id, state, drive,
                                  drive["last_trigger"],
                                  expected_revision=state.revision - 1)

    @staticmethod
    def _record_feed_gap(drive: Dict[str, Any], received_at: int) -> None:
        """Hueco de silencio del feed ENTRE disparos (ms de pared).

        El frame recién llegado resetea el reloj del adaptador: el silencio
        relevante para la puerta es el tiempo transcurrido SIN datos entre
        el disparo anterior y este. Si supera ``live_silence_ms``, la puerta
        abstiene ESTA evaluación con causa FEED_SILENCE.
        """
        prev = drive.get("last_trigger_received_at_ms")
        drive["feed_gap_ms"] = (
            (received_at - int(prev)) if prev is not None else None)
        drive["last_trigger_received_at_ms"] = received_at

    @staticmethod
    def _merge_operation_candle(candles: List, paper: Any) -> List:
        """Ventana de operación ordenada, sin duplicar open_time."""
        kept = [c for c in candles if c.open_time_ms != paper.open_time_ms]
        kept.append(paper)
        kept.sort(key=lambda c: c.open_time_ms)
        return kept

    def _paper_candle_from_frame(self, state, candle: Dict[str, Any],
                                 received_at: int):
        try:
            ot = int(candle["open_time_ms"])
            o = float(candle["open"])
            h = float(candle["high"])
            l = float(candle["low"])
            c = float(candle["close"])
        except (KeyError, TypeError, ValueError):
            return None
        step = INTERVAL_MS_MAP.get(str(state.config.interval))
        close_ms = candle.get("close_time_ms")
        try:
            close_ms = int(close_ms) if close_ms is not None else None
        except (TypeError, ValueError):
            close_ms = None
        if close_ms is None:
            close_ms = (ot + step - 1) if step else None
        # Causalidad: el open se conoce en open_time_ms; el OHLC completo
        # (vela cerrada del feed) se recibe en received_at (hora de pared).
        return engine.PaperCandle(
            open_time_ms=ot, open=o, high=h, low=l, close=c,
            close_time_ms=close_ms or ot,
            available_at=ot, received_at=received_at,
        )

    def _live_advance(self, session_id: str, state, drive: Dict[str, Any],
                      trigger: Dict[str, Any],
                      expected_revision: Optional[int] = None):
        """Catch-up del reloj + UNA evaluación con puerta + un solo guardado.

        El catch-up corta ANTES de quedarse sin aperturas por revelar:
        llamar ``step_forward`` con posición abierta y ``_next_reveal_index``
        None cerraría la sesión por open_at_end (cierre falso en live).
        ``expected_revision`` es la revisión ANTES de la fusión de la vela
        (la mutación en memoria ya trae sus bumps acumulados).
        """
        if expected_revision is None:
            expected_revision = state.revision
        prev_revision = state.revision
        steps = 0
        while steps < CATCH_UP_MAX_STEPS:
            if engine._next_reveal_index(state) is None:
                break
            state = engine.step_forward(state)
            steps += 1
            if state.status in ("cerrada", "detenida"):
                break
        drive["last_catch_up_steps"] = steps
        if steps == 0:
            # Nada por revelar ni decidir: sin guardado (sin revisión nueva).
            return state
        state = self._tag_fill_basis(state)
        gate = self._evaluation_gate(state, drive)
        drive["last_gate"] = gate
        evaluacion_ejecutada = False
        decision_antes = state.config.decision
        motivo_antes = state.config.decision_reason
        if gate["ok"] and state.status in ("sin_iniciar", "evaluando") and (
                state.config.decision in (None, "SIN_ENTRADA")):
            estado_antes = state
            state = engine.evaluate_session(
                state,
                hypothesis_id=state.config.hypothesis_id,
                hypothesis_version=state.config.hypothesis_version,
                rule_version=state.config.rule_version or engine.RULE_CAUSAL_V1,
                at_ms=state.clock_ms,
            )
            # Se contó como evaluación ejecutada solo si el evaluador produjo
            # una decisión (cambio de None -> decisión o reafirmación de
            # SIN_ENTRADA con motivo). decision=null o puerta cerrada no son
            # evaluación ejecutada: se clasifican separadamente.
            evaluacion_ejecutada = (
                estado_antes.config.decision != state.config.decision
                or estado_antes.config.decision_reason
                != state.config.decision_reason
            )
            state = self._augment_live_evidence(state, drive, trigger, gate)
        if evaluacion_ejecutada:
            evaluaciones = drive.setdefault("evaluaciones", [])
            contador = int(drive.get("evaluacion_contador", 0)) + 1
            drive["evaluacion_contador"] = contador
            evaluaciones.append({
                "evaluacion_num": contador,
                "evento_disparador": {
                    "frame": trigger.get("frame"),
                    "open_time_ms": trigger.get("open_time_ms"),
                    "close_time_ms": trigger.get("close_time_ms"),
                    "received_at_ms": trigger.get("received_at_ms"),
                },
                "T": state.clock_ms,
                "config": {
                    "rule_version": state.config.rule_version,
                    "hypothesis_id": state.config.hypothesis_id,
                    "hypothesis_version": state.config.hypothesis_version,
                    "symbol": state.config.symbol,
                    "interval": state.config.interval,
                    "notional_usdt": state.config.notional_usdt,
                },
                "resultado": {
                    "decision": state.config.decision,
                    "decision_reason": state.config.decision_reason,
                    "abstencion_sin_entrada": state.config.decision
                    == "SIN_ENTRADA"
                    and state.config.decision_reason is not None,
                    "decision_antes": decision_antes,
                    "motivo_antes": motivo_antes,
                },
                "evaluado_en_ms": _now_ms(),
            })
        # UN solo guardado para todo el avance (fusion + catch-up + evaluación
        # acumulados en memoria); request_id determinista por disparo.
        request_id = (f"market-{session_id}-"
                      f"{trigger.get('open_time_ms') or trigger.get('frame')}"
                      f"-{expected_revision}")
        return self._save(state, expected_revision, request_id)

    def _evaluation_gate(self, state, drive: Dict[str, Any]) -> Dict[str, Any]:
        """Puerta de evaluación live: frescura, silencio del feed y huecos.

        Distinción explícita de relojes: hora del evento (open/close del
        feed), hora de recepción (received_at, pared) y reloj de evaluación
        (state.clock_ms). En live, ``end_of_data`` del evaluador de frescura
        solo significa "aún no llegó la próxima vela cerrada" (espera
        normal); el bloqueo real es silencio del feed u obsolescencia.
        """
        wall = _now_ms()
        merged = engine._merge_candles(state.context_candles, state.candles)
        at_ms = state.clock_ms if state.clock_ms is not None else wall
        fr = engine.evaluate_freshness_at(merged, at_ms)
        adapter = drive.get("transport")
        # Silencio del feed medido ENTRE disparos (hueco sin datos hasta el
        # disparo actual); el frame recién llegado no lo enmascara.
        silence_ms = drive.get("feed_gap_ms")
        limit = float(drive.get("live_silence_ms") or self.live_silence_ms)
        holes = self._grid_holes(state)
        stale = bool(fr.get("stale_candles"))
        silence_ok = silence_ms is None or silence_ms <= limit
        ok = (not stale and silence_ok and holes is None
              and state.status not in ("cerrada", "detenida"))
        cause = None
        if not ok:
            if stale:
                cause = "DATA_STALE"
            elif not silence_ok:
                cause = "FEED_SILENCE"
            elif holes is not None:
                cause = "GRID_GAP"
            else:
                cause = "SESSION_NOT_EVALUABLE"
        return {
            "evaluated_at_ms": wall,
            "clock_ms": at_ms,
            "freshness": {
                "reason": fr.get("reason"),
                "stale_candles": fr.get("stale_candles"),
                "end_of_data": fr.get("end_of_data"),
                "note": ("end_of_data en live = sin vela cerrada posterior "
                         "aún (espera normal del feed; no bloquea)"),
            },
            "silence_ms": silence_ms,
            "live_silence_ms": limit,
            "adapter_last_frame_at_ms": (
                adapter.stats.get("last_frame_at_ms")
                if adapter is not None else None),
            "grid_gap": holes,
            "ok": ok,
            "cause": cause,
        }

    def _grid_holes(self, state) -> Optional[List[str]]:
        step = INTERVAL_MS_MAP.get(str(state.config.interval))
        if step is None:
            return [f"intervalo {state.config.interval} sin paso de rejilla "
                    "conocido"]
        holes: List[str] = []
        candles = sorted(state.candles, key=lambda c: c.open_time_ms)
        if state.context_candles and candles:
            last_ctx = max(
                (c.close_time_ms or (c.open_time_ms + step - 1))
                for c in state.context_candles)
            if candles[0].open_time_ms != last_ctx + 1:
                holes.append(
                    f"frontera contexto→operación: primera vela "
                    f"{candles[0].open_time_ms} != {last_ctx + 1} (continuidad)")
        for prev, cur in zip(candles, candles[1:]):
            if cur.open_time_ms - prev.open_time_ms != step:
                holes.append(
                    f"hueco {prev.open_time_ms}→{cur.open_time_ms} "
                    f"(paso {cur.open_time_ms - prev.open_time_ms} != {step})")
        return holes or None

    def _tag_fill_basis(self, state):
        """Etiqueta el último evento entry/exit/stop como aproximación.

        Sin bid/ask/profundidad observados en T, el fill usa el precio
        conocido tras la decisión (open de la vela revelada): es una
        APROXIMACIÓN DEL MODELO, no liquidez inventada.
        """
        events = list(state.events)
        for i in range(len(events) - 1, -1, -1):
            ev = events[i]
            if ev.kind in ("entry", "exit", "stop"):
                if ev.detail and "fill_basis=" in ev.detail:
                    return state
                tag = ("fill_basis=model_approximation (fill con precio "
                       "conocido tras la decisión; bid/ask/profundidad no "
                       "observados; funding/costes no observados=UNKNOWN)")
                events[i] = dataclasses.replace(
                    ev, detail=((ev.detail + " | ") if ev.detail else "")
                    + tag)
                return dc_replace(state, events=events)
        return state

    def _augment_live_evidence(self, state, drive: Dict[str, Any],
                               trigger: Dict[str, Any],
                               gate: Dict[str, Any]):
        """Enriquece la evidencia de la decisión con identidad y 3 relojes.

        Nivel de servicio (el motor no se toca): session_id, config_hash,
        identidad de mercado, evento disparador, bloques de evidencia del
        adaptador y la distinción evento/recibido/reloj de evaluación.
        """
        evidence = state.config.decision_evidence
        if not isinstance(evidence, dict):
            return state
        adapter = drive.get("transport")
        augmented = dict(evidence)
        augmented["adapter"] = {
            "runner": TRANSPORT_MARKET_STREAM,
            "market_url": drive.get("market_url"),
            "market_service": (adapter.stats if adapter is not None
                               else None) and dict(adapter.stats) or None,
            "symbol": state.config.symbol,
            "interval": state.config.interval,
            "trigger": trigger,
            "clocks": {
                "trigger_open_ms": trigger.get("open_time_ms"),
                "trigger_received_at_ms": trigger.get("received_at_ms"),
                "evaluation_clock_ms": state.clock_ms,
                "evaluation_wall_ms": _now_ms(),
            },
            "evidence_blocks": {
                kind: entry.get("block")
                for kind, entry in (drive.get("evidence") or {}).items()
            },
            "gate": gate,
        }
        return dc_replace(
            state,
            config=dc_replace(state.config, decision_evidence=augmented))

    def _finish_drive(self, session_id: str, drive: Dict[str, Any],
                      cause: str) -> None:
        if drive["state"] == "running":
            drive["state"] = "stopped"
            drive["finished_at_ms"] = _now_ms()
            drive["cause"] = cause
        if drive.get("stop_event") is not None:
            drive["stop_event"].set()
        if cause in ("SESSION_CLOSED", "SESSION_STOPPED"):
            try:
                self._unregister_session(session_id)
            except OSError:  # pragma: no cover
                pass

    # --- parada -------------------------------------------------------------
    def shutdown(self) -> None:
        with self._lock:
            drives = list(self._drives.values())
        for drive in drives:
            if drive.get("stop_event") is not None:
                drive["stop_event"].set()


class _EngineeringHTTPHandler(BaseHTTPRequestHandler):
    server: "EngineeringHTTPServer"
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_guard(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        origin = self.headers.get("Origin")
        host_ok = host.startswith("127.0.0.1") or host.startswith("localhost")
        origin_ok = origin is None or origin.startswith("http://127.0.0.1") \
            or origin.startswith("http://localhost")
        return host_ok and origin_ok

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 16 * 1024 * 1024))
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            raise ValueError("JSON inválido en el cuerpo de la petición")
        if not isinstance(body, dict):
            raise ValueError("el cuerpo debe ser un objeto JSON")
        return body

    # --- verbos -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        world = self.server.world
        url = urlsplit(self.path)
        path = url.path.rstrip("/") or "/"
        try:
            if not self._auth_guard():
                self._send_json(403, {"error": "FORBIDDEN"})
                return
            if path == "/health":
                self._send_json(200, self.server.health_payload())
                return
            if path == "/sessions":
                self._send_json(200, {"sessions": world.list_sessions()})
                return
            if path.startswith("/sessions/"):
                sid = path[len("/sessions/"):]
                if "/" in sid:
                    self._send_json(404, {"error": "NOT_FOUND"})
                    return
                self._send_json(200, world.get_session(sid))
                return
            self._send_json(404, {"error": "NOT_FOUND", "path": path})
        except KeyError as exc:
            code = str(exc.__str__())
            code = code.strip("'\" ()")
            self._send_json(404, {"error": code or "NOT_FOUND"})
        except ValueError as exc:
            self._send_json(400, {"error": f"VALIDATION_ERROR: {exc}"})
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                500, {"error": "INTERNAL_ERROR",
                      "detail": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:  # noqa: N802
        world = self.server.world
        path = urlsplit(self.path).path.rstrip("/")
        try:
            if not self._auth_guard():
                self._send_json(403, {"error": "FORBIDDEN"})
                return
            if path == "/shutdown":
                self._send_json(200, {"ok": True, "pid": os.getpid()})
                self.server.stop_event.set()
                return
            if path == "/sessions":
                payload = self._read_json()
                self._send_json(200, world.create_session(payload))
                return
            if path.startswith("/sessions/"):
                parts = path[len("/sessions/"):].split("/")
                if len(parts) != 2 or parts[1] != "control":
                    self._send_json(404, {"error": "NOT_FOUND"})
                    return
                payload = self._read_json()
                self._send_json(200, world.control(parts[0], payload))
                return
            self._send_json(404, {"error": "NOT_FOUND", "path": path})
        except KeyError as exc:
            code = str(exc).strip("'\" ()")
            self._send_json(404, {"error": code or "NOT_FOUND"})
        except RuntimeError as exc:
            if len(exc.args) == 2:
                code, detail = exc.args
            else:
                code, detail = str(exc), None
            status = 409 if code in CONFLICT_CODES else (
                404 if code == "SESSION_NOT_FOUND" else 500)
            self._send_json(status, {"error": code, "detail": detail})
        except ValueError as exc:
            self._send_json(400, {"error": f"VALIDATION_ERROR: {exc}"})
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                500, {"error": "INTERNAL_ERROR",
                      "detail": f"{type(exc).__name__}: {exc}"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


class EngineeringHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        # Windows: el cierre del observador/proxy aborta conexiones (10054).
        # Ruido esperado; no polluye el stderr del servicio.
        import socketserver
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
            return
        socketserver.BaseServer.handle_error(self, request, client_address)

    def __init__(self, host: str, port: int,
                 world: EngineeringSessionController) -> None:
        super().__init__((host, port), _EngineeringHTTPHandler)
        self.world = world
        self.stop_event = threading.Event()

    def health_payload(self) -> Dict[str, Any]:
        with self.world._lock:
            drives = [self.world._drive_public(
                d, self.world._events.get(sid))
                for sid, d in self.world._drives.items()]
        return {
            "service": SERVICE_VERSION,
            "engine_version": engine.ENGINE_VERSION_PAPER,
            "pid": os.getpid(),
            "host": self.server_address[0],
            "port": self.server_address[1],
            "sessions_dir": str(self.world.sessions_dir),
            "cadence_ms": self.world.cadence_ms,
            "market": {
                "url": self.world.market_url,
                "bars": self.world.market_bars,
                "live_silence_ms": self.world.live_silence_ms,
                "max_notional_usdt": MAX_NOTIONAL_MARKET_STREAM,
                "transports": sorted(ALLOWED_TRANSPORTS),
            },
            "clock": self.world._clock_public_state(),
            "drives": drives,
            "generated_at_ms": _now_ms(),
        }


def stop_running(port: Optional[int] = None,
                 pid_path: Optional[Path] = None) -> Dict[str, Any]:
    """Detiene el servicio (endpoint /shutdown o pid file)."""
    if port is None and pid_path is not None:
        info = _read_pid_info(Path(pid_path))
        port = info.get("port")
    if not port:
        return {"ok": False, "error": "SERVICE_INFO_UNAVAILABLE"}
    import urllib.error
    import urllib.request
    url = f"http://127.0.0.1:{int(port)}/shutdown"
    try:
        req = urllib.request.Request(url, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=5.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {"ok": False, "error": "SHUTDOWN_REQUEST_FAILED",
                "detail": str(exc)}
    if pid_path is not None:
        try:
            Path(pid_path).unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass
    return {"ok": True, "shutdown": payload}


def _read_pid_info(pid_path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(Path(pid_path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _run_id_path(sessions_dir: Path) -> Path:
    """Ruta del archivo que persiste el run_id de la corrida activa."""
    return sessions_dir / "run-id.json"


def _read_run_id(sessions_dir: Path) -> Optional[str]:
    """Lee el run_id persistido de una corrida previa, si existe."""
    try:
        data = json.loads(_run_id_path(sessions_dir).read_text(encoding="utf-8"))
        return data.get("run_id") if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_run_id(sessions_dir: Path, run_id: str) -> None:
    """Persiste el run_id de la corrida para que un reinicio lo reutilice."""
    _run_id_path(sessions_dir).parent.mkdir(parents=True, exist_ok=True)
    _run_id_path(sessions_dir).write_text(
        json.dumps({"run_id": run_id}, ensure_ascii=False) + "\n",
        encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Servicio de sesiones de ingeniería (loopback)")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--sessions-dir", default=None,
                        help="directorio de sesiones (default: "
                             "data/engineering-session/sessions, dedicado — "
                             "NO colisiona con el controlador anterior; el "
                             "motor anida paper-lab-sessions/ debajo; se crea "
                             "si no existe)")
    parser.add_argument("--cadence-ms", type=float,
                        default=DEFAULT_CADENCE_MS,
                        help="cadencia del transporte local (ms por vela)")
    parser.add_argument("--market-url", default=None,
                        help="URL del servicio de mercado market-stream/v1 "
                             "para transporte market_stream (SOLO loopback; "
                             "default: env ENGINEERING_MARKET_SERVICE_URL o "
                             f"{DEFAULT_MARKET_URL})")
    parser.add_argument("--market-bars", type=int, default=DEFAULT_MARKET_BARS,
                        help="ventana (velas) solicitada al snapshot del "
                             "servicio de mercado")
    parser.add_argument("--live-silence-ms", type=float,
                        default=LIVE_SILENCE_MS_DEFAULT,
                        help="silencio del feed live (ms) que fuerza la "
                             "puerta de abstención con causa FEED_SILENCE")
    parser.add_argument("--clock-source", choices=["local", "public"],
                        default="local",
                        help="fuente del reloj de referencia: 'local' (reloj de "
                             "pared local, cero solicitudes publicas) o "
                             "'public' (ClockSynchronizer sincronizado contra "
                             "el backend publico, bajo presupuesto).")
    parser.add_argument("--public-max-requests", type=int, default=None,
                        help="tope de intentos /time para sincronizacion "
                             "publica (default: sample_count del "
                             "sincronizador, 5).")
    parser.add_argument("--public-fetch-url", default=None,
                        help="URL del endpoint de tiempo para sincronizacion "
                             "publica (default: Binance fapi.v1/time). Solo se "
                             "usa en pruebas con servidor loopback; en "
                             "produccion se usa Binance real.)")
    parser.add_argument("--run-id", default=None,
                        help="identificador estable de la corrida de "
                             "presupuesto. Requerido en modo publico; se "
                             "persiste y se reutiliza al reiniciar la misma "
                             "corrida. En modo local es opcional.")
    parser.add_argument("--pid-file", default=None)
    parser.add_argument("--stop", action="store_true",
                        help="detiene el servicio estrictamente en --port")
    args = parser.parse_args(argv)

    if args.stop:
        pid_file = Path(args.pid_file) if args.pid_file else PID_DEFAULT
        result = stop_running(args.port, pid_file)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    sessions_dir = Path(args.sessions_dir) if args.sessions_dir \
        else SESSIONS_DEFAULT
    sessions_dir.mkdir(parents=True, exist_ok=True)
    # Seleccion EXPLICITA de la referencia temporal. Nunca se ejecuta
    # ClockSynchronizer.sync() contra Binance en arranque local/demo: por
    # defecto se usa el reloj de pared local (cero solicitudes publicas).
    # El modo publico requiere activacion expresa en backend y presupuesto
    # suficiente para su politica de sincronizacion (intentos /time
    # contabilizados ANTES de enviar, incluido fallos).
    synchronizer: Optional[ClockSynchronizer] = None
    now_ms: Optional[Callable[[], Optional[int]]] = None
    clock_source_label: Optional[str] = None
    if args.clock_source == "public":
        max_req = args.public_max_requests
        if max_req is None:
            max_req = CLOCK_PUBLIC_MAX_REQUESTS
        # Presupuesto publico ANTES de habilitar el modo publico: si no
        # alcanza para la politica de sincronizacion, no se habilita. Se
        # comprueban AMBOS limites: la ventana movil (30/60 s) y el presupuesto
        # total de la corrida (7), compartido entre /time, klines, catalogo,
        # reintentos y recuperacion. El servicio no sustituye el total de la
        # corrida por el limite general.
        cache = MarketCache()
        try:
            cache.init_db()
        except Exception:
            cache = None
        if cache is None:
            print(json.dumps({
                "error": "PUBLIC_CLOCK_CACHE_UNAVAILABLE",
                "detail": "no se pudo inicializar la caché de presupuesto",
            }, ensure_ascii=False), flush=True)
            return 2
        # run_id estable para toda la corrida. En modo publico es obligatorio
        # (--run-id); no se genera desde la hora actual. Al reiniciar la misma
        # corrida se reutiliza el valor persistido en sessions_dir.
        run_id = args.run_id
        if run_id is None:
            persisted = _read_run_id(sessions_dir)
            if persisted is not None:
                run_id = persisted
            elif args.clock_source == "public":
                print(json.dumps({
                    "error": "PUBLIC_RUN_ID_REQUIRED",
                    "detail": "modo publico requiere --run-id para atribuir "
                              "el presupuesto de la corrida a una identidad "
                              "estable.",
                }, ensure_ascii=False), flush=True)
                return 2
        if run_id is not None:
            _write_run_id(sessions_dir, run_id)
        now_start = _now_ms()
        window_used = cache.requests_in_window(now_start)
        run_used = cache.run_requests_used(run_id)
        if window_used + max_req > MAX_FETCH_REQUESTS_PER_WINDOW \
                or run_used + max_req > MAX_FETCH_REQUESTS_PER_RUN:
            print(json.dumps({
                "error": "PUBLIC_CLOCK_BUDGET_INSUFICIENTE",
                "detail": ("se requieren "
                           f"{max_req} intentos /time pero el presupuesto "
                           "publico no permite la politica de "
                           "sincronizacion del reloj "
                           f"(ventana {window_used}/{MAX_FETCH_REQUESTS_PER_WINDOW}, "
                           f"corrida {run_used}/{MAX_FETCH_REQUESTS_PER_RUN})"),
            }, ensure_ascii=False), flush=True)
            return 2
        synchronizer = ClockSynchronizer(
            sample_count=max_req,
            fetch_server_time=_make_budgeted_time_fetch(
                cache, run_id, max_req,
                _fetch_public_server_time(args.public_fetch_url),
                run_max_requests=MAX_FETCH_REQUESTS_PER_RUN),
            request_timeout_seconds=5.0,
        )
        # NO se ejecuta synchronizer.sync() aqui: primero se levanta el
        # servidor HTTP para que /health responda NOT_READY
        # (available=False) durante la preparacion del reloj. La sincronizacion
        # se ejecuta despues de thread.start(), fuera de esta rama.
        clock_source_label = "public_sincronizado"
    else:
        # Modo local: reloj de pared local, cero solicitudes publicas,
        # referencia explícitamente local (no se simula tiempo de Binance).
        now_ms = _now_ms
        clock_source_label = "local_sistema"
    world = EngineeringSessionController(
        sessions_dir, args.cadence_ms, market_url=args.market_url,
        market_bars=args.market_bars, live_silence_ms=args.live_silence_ms,
        now_ms=now_ms, clock_sync=synchronizer,
        clock_source=clock_source_label)
    server = EngineeringHTTPServer(args.host, args.port, world)
    pid_file = Path(args.pid_file) if args.pid_file else PID_DEFAULT
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(json.dumps({
        "pid": os.getpid(),
        "port": server.server_address[1],
        "host": server.server_address[0],
        "service": SERVICE_VERSION,
        "started_at_ms": _now_ms(),
    }) + "\n", encoding="utf-8")
    print(json.dumps({
        "service": SERVICE_VERSION,
        "pid": os.getpid(),
        "url": f"http://{server.server_address[0]}:{server.server_address[1]}",
        "sessions_dir": str(sessions_dir),
        "cadence_ms": world.cadence_ms,
        "market_url": world.market_url,
        "market_bars": world.market_bars,
        "live_silence_ms": world.live_silence_ms,
    }, ensure_ascii=False), flush=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Sincronizacion del reloj despues de levantar /health: durante la
    # preparacion (sync en curso contra Binance), /health responde
    # NOT_READY (available=False) y nunca se admite crear sesion.
    # Si el sync falla, available=False se mantiene y el servicio sigue
    # operativo pero sin reloj valido.
    if synchronizer is not None:
        try:
            asyncio.run(synchronizer.sync())
        except Exception:  # noqa: BLE001 - referencia no disponible -> abstencion
            pass
    try:
        while not server.stop_event.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        world.shutdown()
        server.shutdown()
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
