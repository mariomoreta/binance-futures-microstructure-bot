"""Servicio local de datos ``market-stream/v1`` (SSE sobre loopback).

Arranque/parada explicitos. NO arranca el monitor del bot, NO toca el trio
canonico y NO escribe velas: el estado vive en memoria y el snapshot se lee del
almacen existente en modo lectura.

Uso (PowerShell, desde la raiz del repositorio):

    python scripts/market_stream_service.py --port 8791
    python scripts/market_stream_service.py --port 8791 --stop

Endpoints (solo 127.0.0.1):

    GET  /health          estado de conexion, streams, contadores y limites
    GET  /stream?...      SSE: hello, snapshot, candle, closed, indicators,
                          context, gap, status, heartbeat
    POST /shutdown        parada ordenada (loopback; token opcional)

El servidor HTTP es de biblioteca estandar (``asyncio.start_server``) para no
anadir dependencias: solo se necesita ``websockets``, ya declarado.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qs, urlsplit

from .flow import FlowEngine
from .kline_btc_context import (
    BTC_BENCHMARK_SYMBOL,
    compute_btc_context,
)
from .kline_indicators import compute_kline_indicators
from .market_cache import MarketCache
from .market_explorer import EXPLORABLE_INTERVALS, series_payload
from .market_stream import (
    FRESH_MS,
    STALE_MS,
    STREAM_CONTRACT_VERSION,
    BinanceKlineTransport,
    KlineStreamHub,
    build_recovery,
    interval_ms,
)

DEFAULT_PORT = 8791
DEFAULT_HOST = "127.0.0.1"
MAX_REQUEST_BYTES = 16 * 1024
MAX_BARS = 1000
MIN_BARS = 1
SERVICE_VERSION = "market-stream-service/v1"
TRANSPORT_LOCAL = "local"

# --- Flujo comprador/vendedor (market-flow/v1) -----------------------------
# Presupuesto de memoria para IDs deduplicados (LRU acotado por simbolo).
FLOW_MAX_EVENT_IDS = 10_000
MARKET_FLOW_CONTRACT_VERSION = "market-flow/v1"
FLOW_AVAILABILITY = "LIVE_CAPTURE_ONLY"
NO_COVERAGE = "NO_COVERAGE_BEFORE_FIRST_EVENT"
# Symbolos permitidos para ingesta de flujo. Por defecto vacia (ningun simbolo
# aceptado = endpoint de escritura cerrado por defecto). Para pruebas locales
# se puede poblar con MICROPROBE_FLOW_SYMBOLS="BTCUSDT,ETHUSDT".
_FLOW_SYMBOLS_ENV = os.environ.get("MICROPROBE_FLOW_SYMBOLS", "")
FLOW_SYMBOLS: Tuple[str, ...] = tuple(
    s.strip().upper() for s in _FLOW_SYMBOLS_ENV.split(",") if s.strip()
)
TRANSPORT_PUBLIC = "public"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


class TransportConfigError(ValueError):
    """Configuracion de transporte ausente o invalida: el servicio no arranca."""


def resolve_transport(mode: Optional[str], base_url: Optional[str]) -> Dict[str, Any]:
    """Valida el transporte **sin abrir conexiones** (falla cerrado).

    - ``local``: exige un ``--base-url`` ws:// loopback; nunca cae al endpoint
      publico y desactiva la reparacion REST.
    - ``public``: activacion explicita del WS publico de Binance (sin base_url).
    Cualquier otra combinacion lanza ``TransportConfigError`` antes de crear el
    servicio, de modo que una configuracion ausente o incorrecta produce cero
    conexiones publicas.
    """

    if mode == TRANSPORT_LOCAL:
        if not base_url:
            raise TransportConfigError(
                "transporte local sin --base-url: no se usa el endpoint publico "
                "como respaldo")
        parts = urlsplit(base_url)
        hostname = (parts.hostname or "").lower()
        if parts.scheme != "ws" or hostname not in LOOPBACK_HOSTS:
            raise TransportConfigError(
                f"--base-url no es un WS loopback valido: {base_url!r} "
                "(se espera ws://127.0.0.1:<puerto>)")
        if not parts.port:
            raise TransportConfigError(
                "--base-url local requiere puerto explicito")
        return {"mode": TRANSPORT_LOCAL, "base_url": base_url, "recovery": False}

    if mode == TRANSPORT_PUBLIC:
        if base_url:
            raise TransportConfigError(
                "--transport public no admite --base-url")
        return {"mode": TRANSPORT_PUBLIC, "base_url": None, "recovery": True}

    raise TransportConfigError(
        "transporte no especificado: use --transport local --base-url "
        "ws://127.0.0.1:<puerto> o --transport public (conexion publica explicita)")


def _pid_path() -> Path:
    override = os.environ.get("MICROPROBE_MARKET_STREAM_PID")
    return Path(override) if override else Path("data/market-stream/service.json")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _chunked(data: bytes) -> bytes:
    return f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n"


# Tope de espera del drain SSE: si el receptor no drena en ese tiempo, la
# conexión se corta (consumidor liberado) en lugar de colgar el stream sin
# heartbeats. Solo afecta a la conexión en problema, no al bucle de eventos.
SSE_WRITE_DRAIN_TIMEOUT_S = 30.0


def _sse_frame(event: str, payload: Dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n".encode("utf-8")


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _parse_bars(values: Dict[str, list]) -> Optional[int]:
    raw = (values.get("bars") or [None])[0]
    if raw is None:
        return None
    try:
        bars = int(raw)
    except (TypeError, ValueError):
        return None
    if bars < MIN_BARS or bars > MAX_BARS:
        return None
    return bars


def _parse_ms(values: Dict[str, list], key: str) -> Optional[int]:
    raw = (values.get(key) or [None])[0]
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _session_candle(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Vela cerrada del snapshot en formato de calculo (open_time, OHLCV)."""
    try:
        open_ms = int(result.get("open_time_ms"))
    except (TypeError, ValueError):
        return None
    if result.get("closed") is not True:
        return None
    return {
        "open_time": open_ms,
        "high": result.get("high"),
        "low": result.get("low"),
        "close": result.get("close"),
        "base_volume": result.get("base_volume"),
    }


def _merge_closed(candles: list, payload: Dict[str, Any]) -> list:
    """Fusiona una vela cerrada del stream en la ventana de la sesion.

    La fila del mismo ``open_time_ms`` se reemplaza; el orden queda por
    ``open_time`` (continuidad temporal, no posiciones del arreglo).
    """
    try:
        open_ms = int(payload["open_time_ms"])
    except (KeyError, TypeError, ValueError):
        return candles
    candle = _session_candle({
        "open_time_ms": open_ms,
        "closed": True,
        "high": payload.get("high"),
        "low": payload.get("low"),
        "close": payload.get("close"),
        "base_volume": payload.get("base_volume"),
    })
    if candle is None:
        return candles
    kept = [c for c in candles if c["open_time"] != open_ms]
    kept.append(candle)
    kept.sort(key=lambda c: c["open_time"])
    return kept


def _session_indicators(symbol: str, interval: str,
                        candles: list) -> Optional[Dict[str, Any]]:
    """Recalcula el bloque versionado sobre la ventana de la sesion.

    La vela provisional NUNCA entra: esta lista solo contiene velas cerradas.
    Un fallo de calculo no rompe el stream: se omite el frame y se conserva
    el ultimo bloque publicado en el cliente.
    """
    step = interval_ms(interval)
    if not step:
        return None
    try:
        return compute_kline_indicators(
            candles, int(step), _now_ms(), symbol=symbol, interval=interval,
            source="ws_kline")
    except Exception:  # pragma: no cover - calculo defensivo
        return None


def _session_context(symbol: str, interval: str, session_candles: list,
                     btc_candles: list, token_block: Dict[str, Any],
                     btc_sources: Sequence[str],
                     btc_subscription: Dict[str, Any],
                     rest_upstream_requests: int = 0,
                     btc_symbol: str = BTC_BENCHMARK_SYMBOL,
                     ) -> Optional[Dict[str, Any]]:
    """Recalcula el bloque de contexto BTC de la sesion.

    Solo velas cerradas de la ventana AMBAS series; los unknown con motivo
    declaran la falta, nunca arrastran valores viejos como nuevos.
    """
    step = interval_ms(interval)
    if not step:
        return None
    try:
        return compute_btc_context(
            session_candles, btc_candles, int(step), _now_ms(),
            symbol=symbol, interval=interval, token_source="ws_kline",
            token_indicators=(token_block.get("series")
                              if token_block else None),
            btc_sources=btc_sources,
            btc_subscription=btc_subscription,
            rest_upstream_requests=rest_upstream_requests,
            btc_symbol=btc_symbol)
    except Exception:  # pragma: no cover - calculo defensivo
        return None


class MarketStreamService:
    """Servidor SSE + hub + transporte, con parada ordenada."""

    def __init__(
        self,
        *,
        hub: Optional[KlineStreamHub] = None,
        transport: Optional[BinanceKlineTransport] = None,
        cache: Optional[MarketCache] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        transport_mode: Optional[str] = None,
        pid_path: Optional[Path] = None,
        max_seconds: Optional[float] = None,
        no_recovery: bool = False,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.token = token or os.environ.get("MICROPROBE_STREAM_TOKEN") or None
        self.cache = cache or MarketCache()
        if transport is not None:
            # Transporte inyectado (pruebas): no se crea ninguna conexion.
            self.hub = hub or KlineStreamHub()
            self.transport = transport
            self.transport_mode = transport_mode or "injected"
            self.transport_base_url = base_url
        else:
            # Sin transporte inyectado el modo es obligatorio y se valida antes
            # de abrir nada: no existe fallback al endpoint publico.
            plan = resolve_transport(transport_mode, base_url)
            self.transport_mode = plan["mode"]
            self.transport_base_url = plan["base_url"]
            self.hub = hub or KlineStreamHub(
                recovery=(build_recovery(_rest_client())
                          if plan["recovery"] and not no_recovery else None))
            kwargs = {"base_url": plan["base_url"]} if plan["base_url"] else {}
            self.transport = BinanceKlineTransport(self.hub, **kwargs)
        self.pid_path = Path(pid_path) if pid_path is not None else _pid_path()
        self.max_seconds = max_seconds
        self.started_at_ms = _now_ms()
        self.stop_event = asyncio.Event()
        self._server: Optional[asyncio.AbstractServer] = None
        self._tasks: list[asyncio.Task] = []
        self._client_tasks: set[asyncio.Task] = set()
        self.consumers_served = 0
        self.requests_total = 0

        # --- Flujo comprador/vendedor (estado del servicio, no del BFF) -----
        self.flow_engine = FlowEngine(symbols=FLOW_SYMBOLS,
                                      min_baseline_buckets=5)
        # Deduplicacion acotada: symbol -> set de event_ids ya vistos.
        self.flow_seen_ids: Dict[str, Set[str]] = {}
        # Consumidores SSE del flujo (symbol -> set de writers).
        self.flow_consumers: Dict[str, Set[asyncio.StreamWriter]] = {}
        self.flow_events_received = 0
        self.flow_events_ingested = 0
        self.flow_events_duplicate = 0
        self.flow_events_dropped_late = 0
        self.flow_events_dropped_invalid = 0

    # --- ciclo de vida ---------------------------------------------------
    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port,
            limit=MAX_REQUEST_BYTES, reuse_address=True,
        )
        sockets = self._server.sockets or ()
        if sockets:
            self.port = sockets[0].getsockname()[1]
        self._write_pidfile()
        self._tasks.append(asyncio.create_task(self.transport.run(self.stop_event),
                                               name="kline-transport"))
        self._tasks.append(asyncio.create_task(self._idle_reaper(), name="idle-reaper"))
        if self.max_seconds is not None:
            self._tasks.append(asyncio.create_task(self._stop_after(self.max_seconds),
                                                   name="duration-stop"))

    async def stop(self) -> None:
        self.stop_event.set()
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:  # pragma: no cover - cierre defensivo
                pass
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        for task in list(self._client_tasks):
            task.cancel()
        if self._client_tasks:
            await asyncio.gather(*self._client_tasks, return_exceptions=True)
        # Cerrar consumidores SSE del flujo
        for symbol, writers in self.flow_consumers.items():
            for writer in list(writers):
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
            writers.clear()
        self.flow_consumers.clear()
        self._remove_pidfile()

    async def serve_forever(self) -> None:
        await self.start()
        try:
            await self.stop_event.wait()
        finally:
            await self.stop()

    async def _stop_after(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=float(seconds))
        except asyncio.TimeoutError:
            self.stop_event.set()

    async def _idle_reaper(self) -> None:
        while not self.stop_event.is_set():
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            if self.stop_event.is_set():
                return
            released = self.hub.release_idle()
            if released:
                self.hub.changed.set()

    # --- PID --------------------------------------------------------------
    def _write_pidfile(self) -> None:
        try:
            self.pid_path.parent.mkdir(parents=True, exist_ok=True)
            self.pid_path.write_text(json.dumps({
                "service": SERVICE_VERSION,
                "contract_version": STREAM_CONTRACT_VERSION,
                "pid": os.getpid(),
                "host": self.host,
                "port": self.port,
                "started_at_ms": self.started_at_ms,
            }), encoding="utf-8")
        except OSError:
            pass

    def _remove_pidfile(self) -> None:
        try:
            if self.pid_path.exists():
                stored = json.loads(self.pid_path.read_text(encoding="utf-8"))
                if int(stored.get("pid") or 0) == os.getpid():
                    self.pid_path.unlink()
        except (OSError, ValueError):
            pass

    # --- HTTP -------------------------------------------------------------
    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._client_tasks.add(task)
        self.requests_total += 1
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10.0)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError,
                asyncio.LimitOverrunError, ConnectionError):
            await _close_writer(writer)
            if task is not None:
                self._client_tasks.discard(task)
            return
        try:
            parsed = _parse_request(request)
        except ValueError:
            await self._send_json(writer, 400, {"error": "BAD_REQUEST"})
            await _close_writer(writer)
            if task is not None:
                self._client_tasks.discard(task)
            return
        if parsed is None:
            await self._send_json(writer, 400, {"error": "BAD_REQUEST"})
            await _close_writer(writer)
            if task is not None:
                self._client_tasks.discard(task)
            return
        method, target, headers = parsed
        split = urlsplit(target)
        path = split.path
        query = parse_qs(split.query)
        try:
            if path == "/health" and method == "GET":
                await self._send_json(writer, 200, self._health_payload())
            elif path == "/stream" and method == "GET":
                await self._serve_stream(reader, writer, query)
            elif path == "/flow" and method == "GET":
                await self._flow_query(writer, query)
            elif path == "/flow" and method == "POST":
                await self._flow_ingest(reader, writer, headers)
            elif path == "/flow/stream" and method == "GET":
                await self._flow_stream(reader, writer, query)
            elif path == "/shutdown" and method == "POST":
                await self._shutdown(writer, headers)
            else:
                await self._send_json(writer, 404, {"error": "NOT_FOUND"})
        except (ConnectionError, asyncio.CancelledError):
            pass
        except Exception as exc:  # pragma: no cover - defensivo
            try:
                await self._send_json(writer, 500, {
                    "error": "SERVICE_ERROR", "detail": f"{type(exc).__name__}: {exc}"[:300],
                })
            except Exception:
                pass
        finally:
            await _close_writer(writer)
            if task is not None:
                self._client_tasks.discard(task)

    async def _send_json(self, writer: asyncio.StreamWriter, status: int,
                         payload: Dict[str, Any]) -> None:
        body = _json_bytes(payload)
        reason = {200: "OK", 400: "Bad Request", 403: "Forbidden",
                  404: "Not Found", 405: "Method Not Allowed",
                  429: "Too Many Requests", 500: "Internal Server Error"}.get(status, "OK")
        head = (
            f"HTTP/1.1 {status} {reason}\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        writer.write(head + body)
        await writer.drain()

    async def _serve_stream(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter,
                            query: Dict[str, list]) -> None:
        symbol = str((query.get("symbol") or [""])[0]).strip().upper()
        interval = str((query.get("interval") or [""])[0]).strip()
        from_ms = _parse_ms(query, "from_ms")
        to_ms = _parse_ms(query, "to_ms")
        bars = _parse_bars(query) or 300
        consumer, error = self.hub.subscribe(
            symbol, interval,
            consumer_id=f"sse-{os.getpid()}-{self.consumers_served + 1}-{_now_ms()}",
        )
        if consumer is None:
            status = 429 if error in {"MAX_CONSUMERS", "MAX_SUBSCRIPTIONS"} else 400
            await self._send_json(writer, status, {"error": error, "symbol": symbol,
                                                   "interval": interval})
            return
        self.consumers_served += 1
        # Contexto BTC compartido: la suscripcion del benchmark vive en el
        # MISMO hub combinado (refcount por simbolo/intervalo, un solo
        # socket). Cuando el token ES el benchmark no se abre ninguna
        # segunda suscripcion: la propia sesion del token es la serie BTC.
        btc_consumer = None
        btc_error: Optional[str] = None
        btc_shared = False
        btc_sources: list = []
        if symbol != BTC_BENCHMARK_SYMBOL:
            before = self.hub.subscription_info(BTC_BENCHMARK_SYMBOL, interval)
            btc_consumer, btc_error = self.hub.subscribe(
                BTC_BENCHMARK_SYMBOL, interval,
                consumer_id=(f"sse-btc-{os.getpid()}-"
                             f"{self.consumers_served + 1}-{_now_ms()}"))
            if btc_consumer is not None:
                btc_shared = before["consumers"] > 0
        head = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/event-stream; charset=utf-8\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: keep-alive\r\n"
            "Transfer-Encoding: chunked\r\n"
            "X-Accel-Buffering: no\r\n\r\n"
        ).encode("ascii")
        writer.write(head)
        await writer.drain()
        disconnected = asyncio.create_task(_wait_eof(reader))
        self._client_tasks.add(disconnected)

        def _wake_on_disconnect(_task: "asyncio.Task[None]") -> None:
            # El cliente cerro: despierta el bucle del consumidor en vez de
            # esperar al timeout del heartbeat. La liberacion es inmediata.
            try:
                consumer.queue.put_nowait(None)
            except asyncio.QueueFull:  # pragma: no cover - cola llena
                pass

        disconnected.add_done_callback(_wake_on_disconnect)
        token_task: Optional[asyncio.Task] = None
        btc_task: Optional[asyncio.Task] = None
        try:
            await self._write_sse(writer, "retry: 5000\n\n")
            health = self._health_payload()
            await self._write_sse(writer, _sse_frame("hello", {
                "contract_version": STREAM_CONTRACT_VERSION,
                "service": SERVICE_VERSION,
                "identity": {
                    "symbol": symbol,
                    "symbol_canonical": symbol,
                    "interval": interval,
                    "venue": "binance",
                    "market_type": "usd_m_futures",
                    "source": "ws_kline",
                },
                "policy": {
                    "fresh_ms": FRESH_MS,
                    "stale_ms": STALE_MS,
                    "live_requires": "RECEIVING + socket + identidad + age<=fresh_ms",
                },
                "limits": health["limits"],
                "pid": os.getpid(),
                "started_at_ms": self.started_at_ms,
            }))
            snapshot = await self._snapshot(symbol, interval, from_ms, to_ms, bars)
            if snapshot is None:
                snapshot = {
                    "symbol": symbol, "interval": interval,
                    "candles": [], "observed": {"start_ms": None, "end_ms": None},
                    "coverage": {"state": "NO_COVERAGE", "exhausted_before": False,
                                 "gaps": [], "reason": "ALMACEN_NO_DISPONIBLE"},
                    "volume": {"available": False, "reason": "SIN_SNAPSHOT"},
                    "indicators": None,
                    "context_btc": None,
                    "source": "cache", "generated_at_ms": _now_ms(),
                }
            # Ventana de la sesion: velas cerradas del snapshot (la provisional
            # queda excluida) que los cierres del stream iran actualizando.
            session_candles = [
                bar for bar in (
                    _session_candle(c) for c in snapshot.get("candles") or [])
                if bar is not None
            ]
            # Serie BTC de la sesion: mismas reglas (solo cerradas del cache
            # al abrir; los cierres del stream compartido las actualizan).
            btc_snapshot = None
            btc_candles: list = []
            if btc_consumer is not None or btc_error is not None:
                btc_sources = ["cache"]
                btc_snapshot = await self._snapshot(
                    BTC_BENCHMARK_SYMBOL, interval, from_ms, to_ms, bars)
                if btc_snapshot is not None:
                    btc_candles = [
                        bar for bar in (
                            _session_candle(c)
                            for c in btc_snapshot.get("candles") or [])
                        if bar is not None
                    ]
            await self._write_sse(writer, _sse_frame("snapshot", snapshot))
            # deliver_from_ms: desde where empezar a entregar frames al
            # consumidor. Preferimos el from_ms explícito (frontera de
            # operación, coherente con el contexto) para no entregar velas
            # ya cubiertas; si no hay, usamos el fin del snapshot.
            snapshot_end_ms = int(
                (snapshot.get("observed") or {}).get("end_ms") or 0) or None
            deliver_from_ms = from_ms if from_ms is not None else snapshot_end_ms
            self.hub.ready(consumer, deliver_from_ms)
            last_block = snapshot.get("indicators") or None
            if btc_consumer is not None:
                btc_last_open = None
                if btc_snapshot is not None:
                    btc_last_open = int(
                        (btc_snapshot.get("observed") or {}).get("end_ms") or 0
                    ) or None
                self.hub.ready(btc_consumer, btc_last_open)
            status = self.hub.consumer_status(consumer)
            if status is not None:
                await self._write_sse(writer, _sse_frame("status", status))

            def _btc_subscription_info() -> Dict[str, Any]:
                if btc_consumer is None:
                    return {"shared": False, "live": False,
                            "reason": btc_error or None}
                live = not btc_consumer.closed \
                    and self.hub.subscription_info(
                        BTC_BENCHMARK_SYMBOL, interval)["consumers"] > 0
                return {"shared": btc_shared, "live": live}

            token_task = asyncio.ensure_future(consumer.queue.get())
            btc_task = (asyncio.ensure_future(btc_consumer.queue.get())
                        if btc_consumer is not None else None)
            while not consumer.closed and not self.stop_event.is_set():
                if disconnected.done():
                    break
                wait = {token_task}
                if btc_task is not None:
                    wait.add(btc_task)
                done, _pending = await asyncio.wait(
                    wait, timeout=5.0, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    current = self.hub.consumer_status(consumer)
                    if current is None:
                        break
                    await self._write_sse(writer, _sse_frame("heartbeat", {
                        "now_ms": _now_ms(),
                        "connection": current["connection"],
                        "age_ms": current["age_ms"],
                        "live": current["live"],
                        "last_message_ms": current["last_message_ms"],
                        "last_kline_open_ms": current["last_kline_open_ms"],
                    }))
                    continue
                if token_task in done:
                    item = token_task.result()
                    token_task = asyncio.ensure_future(consumer.queue.get())
                    if item is None:
                        break
                    event, payload = item
                    if event == "closed":
                        # Recalculo incremental: al confirmarse una vela, el
                        # bloque versionado se vuelve a emitir desde el backend
                        # (la vela provisional nunca entra en la ventana). Es
                        # aditivo: no cambia el frame `closed` que le sigue.
                        session_candles = _merge_closed(session_candles, payload)
                        block = _session_indicators(symbol, interval,
                                                    session_candles)
                        if block is not None:
                            await self._write_sse(
                                writer, _sse_frame("indicators", block))
                            last_block = block
                        if symbol != BTC_BENCHMARK_SYMBOL:
                            ctx = _session_context(
                                symbol, interval, session_candles, btc_candles,
                                last_block, btc_sources,
                                _btc_subscription_info())
                            if ctx is not None:
                                await self._write_sse(
                                    writer, _sse_frame("context", ctx))
                    await self._write_sse(writer, _sse_frame(event, payload))
                elif btc_task is not None and btc_task in done:
                    item = btc_task.result()
                    btc_task = asyncio.ensure_future(btc_consumer.queue.get())
                    if item is None:
                        break
                    event, payload = item
                    if event == "closed":
                        btc_candles = _merge_closed(btc_candles, payload)
                        if "ws_kline" not in btc_sources:
                            btc_sources.append("ws_kline")
                        if last_block is not None:
                            ctx = _session_context(
                                symbol, interval, session_candles, btc_candles,
                                last_block, btc_sources,
                                _btc_subscription_info())
                            if ctx is not None:
                                await self._write_sse(
                                    writer, _sse_frame("context", ctx))
                    # Los frames de BTC (candle/status/gap) no se reenvian:
                    # solo su efecto sobre el bloque `context`.
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self.hub.unsubscribe(consumer)
            if btc_consumer is not None:
                self.hub.unsubscribe(btc_consumer)
            for drain_task in (token_task, btc_task):
                if drain_task is not None and not drain_task.done():
                    drain_task.cancel()
            disconnected.cancel()
            self._client_tasks.discard(disconnected)

    async def _write_sse(self, writer: asyncio.StreamWriter, frame: bytes | str) -> None:
        data = frame.encode("utf-8") if isinstance(frame, str) else frame
        writer.write(_chunked(data))
        try:
            await asyncio.wait_for(writer.drain(),
                                   timeout=SSE_WRITE_DRAIN_TIMEOUT_S)
        except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
            # El receptor no drena (colgado o conexión muerta): cierra el
            # stream en vez de dejarlo colgado sin heartbeats. El finally del
            # handler libera el consumidor y el observador de desconexión
            # despierta el bucle: sin bloquear el bucle de eventos ni
            # estancar los heartbeats de los demás receptores.
            raise ConnectionError(
                "SSE_WRITE_STALL: no drain en "
                f"{SSE_WRITE_DRAIN_TIMEOUT_S:.0f}s") from exc

    async def _snapshot(self, symbol: str, interval: str, from_ms: Optional[int],
                        to_ms: Optional[int], bars: int) -> Optional[Dict[str, Any]]:
        def _read() -> Optional[Dict[str, Any]]:
            try:
                payload = series_payload(
                    cache=self.cache, client=None, symbol=symbol, interval=interval,
                    from_ms=from_ms, to_ms=to_ms, allow_fetch=False, bars=bars,
                    now_ms=_now_ms(),
                )
            except Exception:
                return None
            candles = [{
                "open_time_ms": int(c["open_time_ms"]),
                "close_time_ms": c.get("close_time_ms"),
                "open": c.get("open"), "high": c.get("high"),
                "low": c.get("low"), "close": c.get("close"),
                "base_volume": c.get("base_volume"),
                "quote_volume": c.get("quote_volume"),
                "trade_count": c.get("trade_count"),
                "closed": bool(c.get("closed", True)),
            } for c in payload.get("candles") or []]
            return {
                "symbol": payload.get("symbol") or symbol,
                "interval": payload.get("interval") or interval,
                "window": payload.get("requested") or {},
                "candles": candles,
                "observed": payload.get("observed") or {},
                "coverage": payload.get("coverage") or {},
                "volume": payload.get("volume") or {},
                "freshness": payload.get("freshness") or {},
                # market-indicators/v1: mismo bloque del payload REST, ya
                # calculado con client=None (allow_fetch=False): cero upstream.
                "indicators": payload.get("indicators"),
                # market-btc-context/v1: bloque hermano aditivo (solo cuando
                # el token no es BTC); cero upstream ademas.
                "context_btc": payload.get("context_btc"),
                "source": "cache",
                "generated_at_ms": payload.get("generated_at_ms") or _now_ms(),
            }

        return await asyncio.to_thread(_read)

    async def _shutdown(self, writer: asyncio.StreamWriter,
                        headers: Dict[str, str]) -> None:
        peer = writer.get_extra_info("peername") or ("", 0)
        if str(peer[0]) not in {"127.0.0.1", "::1"}:
            await self._send_json(writer, 403, {"error": "FORBIDDEN_PEER"})
            return
        if self.token and headers.get("x-service-token") != self.token:
            await self._send_json(writer, 403, {"error": "FORBIDDEN_TOKEN"})
            return
        await self._send_json(writer, 200, {"ok": True, "pid": os.getpid()})
        self.stop_event.set()

    def _health_payload(self) -> Dict[str, Any]:
        payload = self.hub.health()
        payload.update({
            "service": SERVICE_VERSION,
            "pid": os.getpid(),
            "host": self.host,
            "port": self.port,
            "uptime_ms": _now_ms() - self.started_at_ms,
            "consumers_served": self.consumers_served,
            "requests_total": self.requests_total,
            "intervals": list(EXPLORABLE_INTERVALS),
            "persistence": "MEMORY_ONLY",
            "transport": {"mode": self.transport_mode,
                          "base_url": self.transport_base_url},
            "generated_at_ms": _now_ms(),
            "times": {"unit": "ms", "epoch": "unix_utc"},
            "flow": {
                "events_received": self.flow_events_received,
                "events_ingested": self.flow_events_ingested,
                "events_duplicate": self.flow_events_duplicate,
                "events_dropped_late": self.flow_events_dropped_late,
                "events_dropped_invalid": self.flow_events_dropped_invalid,
                "symbols": sorted(self.flow_engine._series.keys()),
                "sse_consumers": {
                    s: len(c) for s, c in self.flow_consumers.items() if c
                },
            },
        })
        return payload

    # --- Flujo comprador/vendedor (endpoints del servicio) -----------------

    def _flow_block(self, symbol: str, as_of_ms: Optional[int] = None) -> Dict[str, Any]:
        """Construye el bloque market-flow/v1 para un simbolo.

        Sin eventos para el simbolo: coverage NO_COVERAGE, valores
        desconocidos, live=False. Nunca genera datos sinteticos.
        """
        if as_of_ms is None:
            as_of_ms = _now_ms()
        series = self.flow_engine._series.get(symbol)
        if series is None or series.trades_total == 0:
            return {
                "contract_version": "market-flow/v1",
                "availability": "LIVE_CAPTURE_ONLY",
                "coverage": "NO_COVERAGE_BEFORE_FIRST_EVENT",
                "identity": {"symbol": symbol, "venue": "binance",
                             "market_type": "usd_m_futures",
                             "source": "aggTrade_local_transport"},
                "as_of_ms": as_of_ms,
                "freshness_ms": None,
                "live": False,
                "trades_total": 0,
                "rpi_base_total": None,
                "rpi_notional_total": None,
                "rpi_trades": None,
                "dropped_late": 0,
                "dropped_invalid": 0,
                "horizons": {},
                "baselines": {},
                "acceleration": {},
                "deduplication": {"seen_event_ids": 0,
                                  "max_event_ids": FLOW_MAX_EVENT_IDS},
                "notes": ["Sin eventos de captura para este simbolo: sin "
                          "cobertura, sin valores ni ceros inventados."],
            }
        snap = series.snapshot(symbol, as_of_ms, subscribed=True)
        # Mapear snapshot a formato del panel (agregar coverage a cada horizonte)
        horizons = {}
        for h_name, h_data in snap["horizons"].items():
            horizons[h_name] = {
                "trades": h_data["trades"],
                "base_volume": h_data["base_volume"],
                "notional": h_data["notional"],
                "buy_base": h_data["buy_base"],
                "sell_base": h_data["sell_base"],
                "buy_notional": h_data["buy_notional"],
                "sell_notional": h_data["sell_notional"],
                "signed_delta": h_data["signed_delta"],
                "delta_ratio": h_data["delta_ratio"],
                "buy_pct": h_data["buy_pct"],
                "sell_pct": h_data["sell_pct"],
                "trade_rate": h_data["trade_rate"],
                "notional_rate": h_data["notional_rate"],
                "warmup_complete": h_data["warmup_complete"],
                "window_ms": h_data["window_ms"],
                "as_of_ms": h_data["as_of_ms"],
                "coverage": "LIVE" if h_data["trades"] > 0 else NO_COVERAGE,
            }
        return {
            "contract_version": MARKET_FLOW_CONTRACT_VERSION,
            "availability": FLOW_AVAILABILITY,
            "coverage": "LIVE" if series.trades_total > 0 else NO_COVERAGE,
            "identity": {
                "symbol": symbol,
                "venue": "binance",
                "market_type": "usd_m_futures",
                "source": "aggTrade_local_transport",
            },
            "as_of_ms": as_of_ms,
            "freshness_ms": snap["freshness_ms"],
            "live": snap["live"],
            "trades_total": snap["trades_total"],
            "rpi_base_total": snap["rpi_base_total"],
            "rpi_notional_total": snap["rpi_notional_total"],
            "rpi_trades": snap["rpi_trades"],
            "dropped_late": snap["dropped_late"],
            "dropped_invalid": snap["dropped_invalid"],
            "horizons": horizons,
            "baselines": snap["baselines"],
            "acceleration": snap["acceleration"],
            "deduplication": {
                "seen_event_ids": len(self.flow_seen_ids.get(symbol, set())),
                "max_event_ids": FLOW_MAX_EVENT_IDS,
            },
            "notes": ["Delta positivo no es señal alcista automática: solo describe "
                      "el saldo de volumen agresor en ventana."],
        }

    def _flow_register_event_id(self, symbol: str, event_id: str) -> bool:
        """Devuelve True si el event_id es nuevo (no duplicado), False si ya
        se vio. Presupuesto acotado (LRU) por simbolo."""
        seen = self.flow_seen_ids.setdefault(symbol, set())
        if event_id in seen:
            return False
        seen.add(event_id)
        if len(seen) > FLOW_MAX_EVENT_IDS:
            # Evicta el mas antiguo (set no ordenado; se elimina uno arbitrario,
            # suficiente para mantener el presupuesto acotado).
            seen.pop()
        return True

    async def _flow_query(self, writer: asyncio.StreamWriter,
                          query: Dict[str, list]) -> None:
        symbol = str((query.get("symbol") or [""])[0]).strip().upper()
        if not symbol:
            await self._send_json(writer, 400, {"error": "INVALID_SYMBOL",
                                                "detail": "symbol requerido"})
            return
        as_of_ms = _parse_ms(query, "as_of_ms") or _now_ms()
        block = self._flow_block(symbol, as_of_ms)
        await self._send_json(writer, 200, {"ok": True, "data": block})

    async def _flow_ingest(self, reader: asyncio.StreamWriter,
                           writer: asyncio.StreamWriter,
                           headers: Dict[str, str]) -> None:
        """Ingesta un evento aggTrade del transporte local.

        Body JSON: {symbol, event_id, event_ms, price, quantity,
        buyer_is_maker, normal_quantity?}

        Este es el UNICO endpoint de escritura del flujo. No hay escritura
        abierta por defecto: requiere cuerpo JSON completo y simbolo valido.
        """
        try:
            length = int(headers.get("content-length", "0") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_BYTES:
            await self._send_json(writer, 400, {"error": "INVALID_BODY",
                                                "detail": "cuerpo JSON requerido"})
            return
        body = await reader.readexactly(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            await self._send_json(writer, 400, {"error": "INVALID_JSON",
                                                "detail": "cuerpo no es JSON"})
            return
        if not isinstance(payload, dict):
            await self._send_json(writer, 400, {"error": "INVALID_PAYLOAD",
                                                "detail": "cuerpo debe ser objeto"})
            return

        symbol = str(payload.get("symbol") or "").strip().upper()
        event_id = str(payload.get("event_id") or "").strip()
        event_ms = payload.get("event_ms")
        price = payload.get("price")
        quantity = payload.get("quantity")
        buyer_is_maker = payload.get("buyer_is_maker")
        normal_quantity = payload.get("normal_quantity")

        if not symbol:
            await self._send_json(writer, 400, {"error": "INVALID_SYMBOL",
                                                "detail": "symbol requerido"})
            return
        if not event_id:
            await self._send_json(writer, 400, {"error": "MISSING_EVENT_ID",
                                                "detail": "event_id requerido"})
            return
        try:
            event_ms = int(event_ms)
        except (TypeError, ValueError):
            await self._send_json(writer, 400, {"error": "INVALID_EVENT_MS",
                                                "detail": "event_ms invalido"})
            return
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            await self._send_json(writer, 400, {"error": "INVALID_PRICE",
                                                "detail": "price invalido"})
            return
        if not isinstance(quantity, (int, float)) or isinstance(quantity, bool):
            await self._send_json(writer, 400, {"error": "INVALID_QUANTITY",
                                                "detail": "quantity invalida"})
            return
        if not isinstance(buyer_is_maker, bool):
            await self._send_json(writer, 400, {"error": "INVALID_MAKER",
                                                "detail": "buyer_is_maker debe ser booleano"})
            return

        self.flow_events_received += 1

        # Deduplicacion por identidad (symbol + event_id)
        if not self._flow_register_event_id(symbol, event_id):
            self.flow_events_duplicate += 1
            await self._send_json(writer, 200, {
                "ok": True, "duplicate": True, "event_id": event_id,
                "detail": "identificador repetido: no suma volumen",
            })
            return

        accepted = self.flow_engine.ingest(
            symbol, event_ms, float(price), float(quantity),
            buyer_is_maker,
            normal_quantity if isinstance(normal_quantity, (int, float))
            and not isinstance(normal_quantity, bool) else None,
        )
        if not accepted:
            series = self.flow_engine._series.get(symbol)
            newest = series.newest_ms if series else None
            if newest is not None and event_ms < newest:
                self.flow_events_dropped_late += 1
            else:
                self.flow_events_dropped_invalid += 1
            await self._send_json(writer, 200, {
                "ok": False, "duplicate": False, "event_id": event_id,
                "detail": "evento descartado (tardio o invalido)",
            })
            return

        self.flow_events_ingested += 1
        block = self._flow_block(symbol, event_ms)
        # Publicar a consumidores SSE del flujo
        await self._flow_publish(symbol, {
            "event": "update",
            "symbol": symbol,
            "event_id": event_id,
            "block": block,
        })

        await self._send_json(writer, 200, {
            "ok": True, "duplicate": False, "event_id": event_id,
            "symbol": symbol, "block": block,
        })

    async def _flow_publish(self, symbol: str, frame: Dict[str, Any]) -> None:
        """Envía un frame SSE a los consumidores del flujo para un simbolo."""
        data = _sse_frame(frame["event"], {k: v for k, v in frame.items()
                                           if k != "event"})
        dead = []
        for writer in list(self.flow_consumers.get(symbol, set())):
            try:
                writer.write(data)
                await writer.drain()
            except (ConnectionError, OSError, asyncio.CancelledError):
                dead.append(writer)
        for writer in dead:
            self.flow_consumers.get(symbol, set()).discard(writer)

    async def _flow_stream(self, reader: asyncio.StreamWriter,
                           writer: asyncio.StreamWriter,
                           query: Dict[str, list]) -> None:
        symbol = str((query.get("symbol") or [""])[0]).strip().upper()
        if not symbol:
            await self._send_json(writer, 400, {"error": "INVALID_SYMBOL",
                                                "detail": "symbol requerido"})
            return
        writer.write(b"HTTP/1.1 200 OK\r\n"
                     b"Content-Type: text/event-stream; charset=utf-8\r\n"
                     b"Cache-Control: no-store\r\n"
                     b"Connection: keep-alive\r\n\r\n")
        await writer.drain()
        # Registrar consumidor
        self.flow_consumers.setdefault(symbol, set()).add(writer)
        # Enviar snapshot inicial
        block = self._flow_block(symbol)
        await self._write_sse(writer, _sse_frame("hello", {
            "contract_version": "market-flow/v1",
            "symbol": symbol,
            "at_ms": _now_ms(),
        }))
        await self._write_sse(writer, _sse_frame("snapshot", {
            "symbol": symbol,
            "block": block,
        }))
        disconnected = asyncio.create_task(_wait_eof(reader))
        self._client_tasks.add(disconnected)
        try:
            while not self.stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(reader.read(1), timeout=5.0)
                    if not chunk:
                        break
                except asyncio.TimeoutError:
                    continue  # heartbeat implícito: cliente sigue conectado
                except (ConnectionError, asyncio.CancelledError, OSError):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            disconnected.cancel()
            self.flow_consumers.get(symbol, set()).discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass



def _parse_request(raw: bytes) -> Optional[Tuple[str, str, Dict[str, str]]]:
    try:
        text = raw.decode("latin-1")
    except UnicodeDecodeError:
        raise ValueError("bad request encoding")
    lines = text.split("\r\n")
    if not lines or len(lines[0].split(" ")) != 3:
        raise ValueError("bad request line")
    method, target, _version = lines[0].split(" ")
    headers: Dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise ValueError("bad header")
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return method.upper(), target, headers


async def _wait_eof(reader: asyncio.StreamReader) -> None:
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                return
    except (ConnectionError, asyncio.CancelledError):
        return


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    try:
        writer.close()
    except Exception:
        pass
    try:
        await writer.wait_closed()
    except Exception:
        pass


def _rest_client():
    from .market_explorer import build_client

    return build_client()


def stop_running(port: int, token: Optional[str] = None, timeout: float = 5.0) -> Dict[str, Any]:
    """Pide la parada ordenada del servicio en ``127.0.0.1:port``."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{int(port)}/shutdown", method="POST", data=b"",
        headers=({"X-Service-Token": token} if token else {}),
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"ok": True, "status": response.status,
                    "body": response.read().decode("utf-8", "replace")[:500]}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code,
                "body": exc.read().decode("utf-8", "replace")[:500]}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Servicio local market-stream/v1 (SSE)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MICROPROBE_STREAM_PORT", DEFAULT_PORT)))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--transport", choices=(TRANSPORT_LOCAL, TRANSPORT_PUBLIC),
                       default=None,
                       help="transporte explicito: local (requiere --base-url "
                            "loopback) o public (WS publico de Binance)")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--pid-file", default=None,
                        help="ruta explicita del pid-file (aislada por corrida; "
                             "por defecto data/market-stream/service.json)")
    parser.add_argument("--max-seconds", type=float, default=None,
                       help="parada automatica (solo ventana acotada autorizada)")
    parser.add_argument("--no-recovery", action="store_true",
                       help="desactiva la reparacion REST (recomendado para "
                            "ventana publica con presupuesto de REST limitado)")
    parser.add_argument("--stop", action="store_true", help="detiene el servicio en --port")
    args = parser.parse_args(argv)

    if args.stop:
        result = stop_running(args.port)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    try:
        plan = resolve_transport(args.transport, args.base_url)
    except TransportConfigError as exc:
        print(json.dumps({"service": SERVICE_VERSION,
                          "error": "TRANSPORT_CONFIG",
                          "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    service = MarketStreamService(
        host=args.host, port=args.port, base_url=plan["base_url"],
        transport_mode=plan["mode"], max_seconds=args.max_seconds,
        no_recovery=args.no_recovery,
        pid_path=Path(args.pid_file) if args.pid_file else None,
    )

    async def _main() -> None:
        await service.start()
        print(json.dumps({
            "service": SERVICE_VERSION, "pid": os.getpid(),
            "url": f"http://{service.host}:{service.port}",
            "contract_version": STREAM_CONTRACT_VERSION,
            "transport": {"mode": service.transport_mode,
                          "base_url": service.transport_base_url},
        }, ensure_ascii=False), flush=True)
        try:
            await service.stop_event.wait()
        finally:
            await service.stop()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:  # pragma: no cover - parada manual
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
