"""Servicio local de flujo agresivo ``market-flow/v1`` (SSE sobre loopback).

Mantiene una **instancia compartida de ``FlowEngine``** en memoria y recibe
eventos aggTrade del transporte local (POST ``/flow``). Publica
actualizaciones incrementales al panel vía SSE (``GET /flow/stream``).

NO abre conexion a Binance publico. Sin fuente conectada, devuelve
SIN COBERTURA (valores desconocidos, live=false): nunca genera operaciones
ficticias ni reconstruye desde OHLC.

Endpoints (solo 127.0.0.1):

    GET  /health          estado del servicio, simbolos, contadores
    POST /flow            ingest un evento aggTrade del transporte local
    GET  /flow?symbol=    estado actual del simbolo (sin generar datos)
    GET  /flow/stream?symbol=  SSE: hello, snapshot, update, status, heartbeat
    POST /shutdown        parada ordenada (loopback; token opcional)

Deduplicacion por identidad (symbol + event_id):
  - Mismo identificador repetido: no suma volumen.
  - Identificadores distintos con igual timestamp: ambos cuentan.
  - Eventos tardios (event_ms < newest seen) se descartan (dropped_late).
  - Nunca se afirma que el WS no repita: la deduplicacion es por event_id.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set

from .flow import FlowEngine, FLOW_HORIZON_ORDER

DEFAULT_PORT = 8799
DEFAULT_HOST = "127.0.0.1"
MAX_REQUEST_BYTES = 16 * 1024
SERVICE_VERSION = "market-flow-service/v1"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,32}$")

HEARTBEAT_S = 5.0
STALE_MS = 60_000  # frescura caduca aunque no lleguen eventos


def _pid_path() -> Path:
    override = os.environ.get("MICROPROBE_MARKET_FLOW_PID")
    return Path(override) if override else Path("data/market-flow/service.json")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _sse_frame(event: str, payload: Dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n".encode("utf-8")


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _http_response(
    status: int,
    status_text: str,
    headers: Dict[str, str],
    body: bytes,
) -> bytes:
    lines = [f"HTTP/1.1 {status} {status_text}"]
    for k, v in headers.items():
        lines.append(f"{k}: {v}")
    lines.append("")
    return ("\r\n".join(lines)).encode("ascii") + body


def _empty_flow_block(symbol: str, as_of_ms: int) -> Dict[str, Any]:
    """Bloque SIN COBERTURA: valores desconocidos, live=false, sin sinteticos."""
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
        "horizons": {h: _empty_horizon(h, as_of_ms) for h in FLOW_HORIZON_ORDER},
        "baselines": {},
        "acceleration": {},
        "deduplication": {"seen_event_ids": 0},
        "notes": ["Sin eventos de captura para este simbolo: sin cobertura, "
                  "sin valores ni ceros inventados."],
    }


def _empty_horizon(horizon: str, as_of_ms: int) -> Dict[str, Any]:
    from .flow import FLOW_HORIZONS_MS
    return {
        "trades": 0, "base_volume": 0.0, "notional": 0.0,
        "buy_base": 0.0, "sell_base": 0.0,
        "buy_notional": None, "sell_notional": None,
        "signed_delta": None, "delta_ratio": None,
        "buy_pct": None, "sell_pct": None,
        "trade_rate": 0.0, "notional_rate": 0.0,
        "warmup_complete": False,
        "window_ms": FLOW_HORIZONS_MS[horizon],
        "as_of_ms": as_of_ms,
        "coverage": "NO_COVERAGE_BEFORE_FIRST_EVENT",
    }


class FlowService:
    """Servidor HTTP/SSE + FlowEngine compartido + deduplicacion por event_id."""

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        token: Optional[str] = None,
        pid_path: Optional[Path] = None,
        max_seconds: Optional[float] = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.token = token or os.environ.get("MICROPROBE_FLOW_TOKEN") or None
        # Instancia COMPARTIDA de FlowEngine (un solo gestor, no uno por peticion).
        self.engine = FlowEngine(symbols=(), min_baseline_buckets=5)
        # Deduplicacion: symbol -> set de event_ids ya ingestados.
        self.seen_event_ids: Dict[str, Set[str]] = {}
        # Clientes SSE por simbolo (para publicar actualizaciones incrementales).
        self._sse_clients: Dict[str, Set[asyncio.StreamWriter]] = {}
        self.pid_path = Path(pid_path) if pid_path is not None else _pid_path()
        self.max_seconds = max_seconds
        self.started_at_ms = _now_ms()
        self.stop_event = asyncio.Event()
        self._server: Optional[asyncio.AbstractServer] = None
        self._tasks: list[asyncio.Task] = []
        self.consumers_served = 0
        self.events_received = 0
        self.events_ingested = 0
        self.events_duplicate = 0
        self.events_dropped_late = 0
        self.events_dropped_invalid = 0

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
        self._tasks.append(asyncio.create_task(
            self._heartbeat_loop(), name="flow-heartbeat"))
        if self.max_seconds is not None:
            self._tasks.append(asyncio.create_task(
                self._stop_after(self.max_seconds), name="duration-stop"))

    async def stop(self) -> None:
        self.stop_event.set()
        # Cerrar todos los clientes SSE
        for symbol, clients in list(self._sse_clients.items()):
            for writer in list(clients):
                try:
                    writer.close()
                except Exception:  # pragma: no cover
                    pass
            self._sse_clients[symbol].clear()
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:  # pragma: no cover
                pass
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._write_pidfile(remove=True)

    # --- pidfile ---------------------------------------------------------
    def _write_pidfile(self, remove: bool = False) -> None:
        try:
            self.pid_path.parent.mkdir(parents=True, exist_ok=True)
            if remove:
                self.pid_path.unlink(missing_ok=True)
                return
            self.pid_path.write_text(json.dumps({
                "pid": os.getpid(), "port": self.port,
                "started_at_ms": self.started_at_ms,
            }, indent=2))
        except OSError:  # pragma: no cover
            pass

    # --- heartbeats ------------------------------------------------------
    async def _heartbeat_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=HEARTBEAT_S)
            except asyncio.TimeoutError:
                pass  # tick periodico
            if self.stop_event.is_set():
                break
            frame = _sse_frame("heartbeat", {"at_ms": _now_ms()})
            dead = []
            for symbol, clients in self._sse_clients.items():
                for writer in list(clients):
                    try:
                        writer.write(frame)
                        await writer.drain()
                    except Exception:
                        dead.append((symbol, writer))
            for symbol, writer in dead:
                self._sse_clients.get(symbol, set()).discard(writer)

    # --- manejador HTTP/SSE ----------------------------------------------
    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        try:
            data = await reader.readuntil(b"\r\n\r\n")
            header = data.decode("utf-8", errors="replace")
            lines = header.split("\r\n")
            request_line = lines[0]
            parts = request_line.split(" ")
            method = parts[0]
            raw_path = parts[1] if len(parts) > 1 else "/"
            path = raw_path
            query: Dict[str, list] = {}
            if "?" in raw_path:
                path, qs = raw_path.split("?", 1)
                from urllib.parse import parse_qs
                query = parse_qs(qs)
            headers: Dict[str, str] = {}
            for line in lines[1:]:
                if ": " in line:
                    k, v = line.split(": ", 1)
                    headers[k.lower()] = v

            if path == "/flow/stream" and method == "GET":
                await self._sse_stream(reader, writer, query, headers)
                return

            body = b""
            if method == "POST":
                length = int(headers.get("content-length", "0") or "0")
                if length > 0:
                    body = await reader.readexactly(min(length, MAX_REQUEST_BYTES))

            response = await self._dispatch(method, path, query, headers, body)
            writer.write(response)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError,
                BrokenPipeError, OSError):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # pragma: no cover
                pass

    async def _dispatch(
        self,
        method: str,
        path: str,
        query: Dict[str, list],
        headers: Dict[str, str],
        body: bytes,
    ) -> bytes:
        if path == "/health" and method == "GET":
            return self._health()
        if path == "/flow" and method == "POST":
            return self._ingest_event(body)
        if path == "/flow" and method == "GET":
            return self._query_flow(query)
        if path == "/shutdown" and method == "POST":
            return self._shutdown(headers)
        return _json_bytes({"error": "NOT_FOUND", "detail": f"{method} {path}"})

    # --- endpoints HTTP --------------------------------------------------
    def _health(self) -> bytes:
        return _json_bytes({
            "service": SERVICE_VERSION,
            "host": self.host, "port": self.port,
            "uptime_ms": _now_ms() - self.started_at_ms,
            "symbols": sorted(self.engine._series.keys()),  # type: ignore[attr-defined]
            "events_received": self.events_received,
            "events_ingested": self.events_ingested,
            "events_duplicate": self.events_duplicate,
            "events_dropped_late": self.events_dropped_late,
            "events_dropped_invalid": self.events_dropped_invalid,
            "sse_clients": {
                s: len(c) for s, c in self._sse_clients.items() if c
            },
            "stop_event": self.stop_event.is_set(),
        })

    def _ingest_event(self, body: bytes) -> bytes:
        """Ingest un evento aggTrade del transporte local.

        Body JSON: {symbol, event_id, event_ms, price, quantity,
        buyer_is_maker, normal_quantity?}
        """
        self.events_received += 1
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.events_dropped_invalid += 1
            return _json_bytes({"ok": False, "error": "INVALID_JSON",
                                "detail": "cuerpo no es JSON valido"})
        if not isinstance(payload, dict):
            self.events_dropped_invalid += 1
            return _json_bytes({"ok": False, "error": "INVALID_PAYLOAD",
                                "detail": "el cuerpo debe ser un objeto JSON"})
        symbol = str(payload.get("symbol") or "").strip().upper()
        event_id = str(payload.get("event_id") or "").strip()
        event_ms = payload.get("event_ms")
        price = payload.get("price")
        quantity = payload.get("quantity")
        buyer_is_maker = payload.get("buyer_is_maker")
        normal_quantity = payload.get("normal_quantity")
        if not SYMBOL_RE.match(symbol):
            self.events_dropped_invalid += 1
            return _json_bytes({"ok": False, "error": "INVALID_SYMBOL",
                                "detail": f"simbolo invalido: {symbol!r}"})
        if not event_id:
            self.events_dropped_invalid += 1
            return _json_bytes({"ok": False, "error": "MISSING_EVENT_ID",
                                "detail": "event_id es obligatorio"})
        try:
            event_ms = int(event_ms)
        except (TypeError, ValueError):
            self.events_dropped_invalid += 1
            return _json_bytes({"ok": False, "error": "INVALID_EVENT_MS",
                                "detail": "event_ms debe ser un entero"})
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            self.events_dropped_invalid += 1
            return _json_bytes({"ok": False, "error": "INVALID_PRICE",
                                "detail": "price es obligatorio y numerico"})
        if not isinstance(quantity, (int, float)) or isinstance(quantity, bool):
            self.events_dropped_invalid += 1
            return _json_bytes({"ok": False, "error": "INVALID_QUANTITY",
                                "detail": "quantity es obligatoria y numerica"})
        if not isinstance(buyer_is_maker, bool):
            self.events_dropped_invalid += 1
            return _json_bytes({"ok": False, "error": "INVALID_MAKER",
                                "detail": "buyer_is_maker debe ser booleano"})
        # Deduplicacion por identidad (symbol + event_id)
        seen = self.seen_event_ids.setdefault(symbol, set())
        if event_id in seen:
            self.events_duplicate += 1
            return _json_bytes({
                "ok": True, "duplicate": True, "event_id": event_id,
                "detail": "identificador repetido: no suma volumen",
            })
        seen.add(event_id)
        # Ingest en el FlowEngine compartido
        accepted = self.engine.ingest(
            symbol, event_ms, float(price), float(quantity),
            buyer_is_maker,
            normal_quantity if isinstance(normal_quantity, (int, float))
            and not isinstance(normal_quantity, bool) else None,
        )
        if not accepted:
            series = self.engine._series.get(symbol)  # type: ignore[attr-defined]
            if series is not None and event_ms < (series.newest_ms or 0):
                self.events_dropped_late += 1
            else:
                self.events_dropped_invalid += 1
            return _json_bytes({
                "ok": False, "error": "REJECTED_BY_ENGINE",
                "event_id": event_id,
                "detail": "evento descartado (tardio o invalido)",
            })
        self.events_ingested += 1
        # Publicar actualizacion a clientes SSE suscritos a este simbolo
        block = self._build_block(symbol)
        self._publish_to_subscribers(symbol, {
            "event": "update",
            "symbol": symbol,
            "event_id": event_id,
            "block": block,
        })
        return _json_bytes({
            "ok": True, "duplicate": False, "event_id": event_id,
            "symbol": symbol, "block": block,
        })

    def _query_flow(self, query: Dict[str, list]) -> bytes:
        """Consulta el estado actual sin generar datos sinteticos.

        Sin fuente conectada: SIN COBERTURA, valores desconocidos,
        live=false.
        """
        symbol = str((query.get("symbol") or [None])[0] or "").strip().upper()
        if not SYMBOL_RE.match(symbol):
            return _json_bytes({"error": "INVALID_SYMBOL",
                                "detail": "parametro symbol requerido"})
        as_of_ms = int(query.get("as_of_ms", [_now_ms()])[0])
        block = self._build_block(symbol, as_of_ms)
        return _json_bytes({"ok": True, "data": block})

    def _build_block(self, symbol: str, as_of_ms: Optional[int] = None) -> Dict[str, Any]:
        if as_of_ms is None:
            as_of_ms = _now_ms()
        series = self.engine._series.get(symbol)  # type: ignore[attr-defined]
        if series is None or series.trades_total == 0:
            return _empty_flow_block(symbol, as_of_ms)
        snapshot = series.snapshot(symbol, as_of_ms, subscribed=True)
        horizons: Dict[str, Any] = {}
        for h in FLOW_HORIZON_ORDER:
            hf = snapshot["horizons"][h]
            horizons[h] = {
                "trades": hf["trades"],
                "base_volume": hf["base_volume"],
                "notional": hf["notional"],
                "buy_base": hf["buy_base"],
                "sell_base": hf["sell_base"],
                "buy_notional": hf["buy_notional"],
                "sell_notional": hf["sell_notional"],
                "signed_delta": hf["signed_delta"],
                "delta_ratio": hf["delta_ratio"],
                "buy_pct": hf["buy_pct"],
                "sell_pct": hf["sell_pct"],
                "trade_rate": hf["trade_rate"],
                "notional_rate": hf["notional_rate"],
                "warmup_complete": hf["warmup_complete"],
                "window_ms": hf["window_ms"],
                "as_of_ms": hf["as_of_ms"],
                "coverage": "LIVE" if hf["trades"] > 0 else "NO_COVERAGE_BEFORE_FIRST_EVENT",
            }
        return {
            "contract_version": "market-flow/v1",
            "availability": "LIVE_CAPTURE_ONLY",
            "coverage": "LIVE" if series.trades_total > 0 else "NO_COVERAGE_BEFORE_FIRST_EVENT",
            "identity": {"symbol": symbol, "venue": "binance",
                         "market_type": "usd_m_futures",
                         "source": "aggTrade_local_transport"},
            "as_of_ms": as_of_ms,
            "freshness_ms": snapshot["freshness_ms"],
            "live": snapshot["live"],
            "trades_total": snapshot["trades_total"],
            "rpi_base_total": snapshot["rpi_base_total"],
            "rpi_notional_total": snapshot["rpi_notional_total"],
            "rpi_trades": snapshot["rpi_trades"],
            "dropped_late": snapshot["dropped_late"],
            "dropped_invalid": snapshot["dropped_invalid"],
            "horizons": horizons,
            "baselines": {label: snapshot["baselines"][label]
                          for label in snapshot["baselines"]},
            "acceleration": snapshot["acceleration"],
            "deduplication": {"seen_event_ids": len(
                self.seen_event_ids.get(symbol, set()))},
            "notes": ["Delta positivo no es senal alcista automatica: "
                      "solo describe el saldo de volumen agresor en ventana."],
        }

    # --- SSE -------------------------------------------------------------
    async def _sse_stream(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        query: Dict[str, list],
        headers: Dict[str, str],
    ) -> None:
        """SSE: hello, snapshot, update, status, heartbeat."""
        symbol = str((query.get("symbol") or [None])[0] or "").strip().upper()
        if not SYMBOL_RE.match(symbol):
            resp = _json_bytes({"error": "INVALID_SYMBOL",
                                "detail": "parametro symbol requerido"})
            writer.write(resp)
            await writer.drain()
            return
        # Token opcional
        if self.token is not None:
            auth = headers.get("authorization", "")
            if auth != f"Bearer {self.token}":
                resp = _json_bytes({"error": "FORBIDDEN",
                                    "detail": "token invalido o ausente"})
                writer.write(resp)
                await writer.drain()
                return

        # Headers SSE
        writer.write(b"HTTP/1.1 200 OK\r\n")
        writer.write(b"Content-Type: text/event-stream\r\n")
        writer.write(b"Cache-Control: no-cache\r\n")
        writer.write(b"Connection: keep-alive\r\n")
        writer.write(b"\r\n")
        await writer.drain()

        # Registrar cliente
        self._sse_clients.setdefault(symbol, set()).add(writer)
        self.consumers_served += 1

        # Enviar hello + snapshot inicial
        hello = _sse_frame("hello", {
            "symbol": symbol,
            "service": SERVICE_VERSION,
            "at_ms": _now_ms(),
        })
        snapshot_block = self._build_block(symbol)
        snapshot = _sse_frame("snapshot", {
            "symbol": symbol,
            "block": snapshot_block,
        })
        try:
            writer.write(hello)
            writer.write(snapshot)
            await writer.drain()
        except Exception:
            self._sse_clients.get(symbol, set()).discard(writer)
            return

        # Mantener conexion abierta hasta que el cliente se desconecte o se pida parada
        try:
            while not self.stop_event.is_set():
                # Leer cualquier dato del cliente (para detectar desconexion)
                try:
                    chunk = await asyncio.wait_for(reader.read(1), timeout=1.0)
                    if not chunk:
                        break  # cliente desconectado
                except asyncio.TimeoutError:
                    pass  # sin datos, seguir esperando
                except (asyncio.IncompleteReadError, ConnectionResetError,
                        BrokenPipeError, OSError):
                    break  # cliente desconectado
        except asyncio.CancelledError:
            pass
        finally:
            self._sse_clients.get(symbol, set()).discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # pragma: no cover
                pass

    def _publish_to_subscribers(self, symbol: str, frame: Dict[str, Any]) -> None:
        """Envia un frame SSE a todos los clientes suscritos al simbolo."""
        data = _sse_frame(frame["event"], {
            k: v for k, v in frame.items() if k != "event"
        })
        dead = []
        for writer in list(self._sse_clients.get(symbol, set())):
            try:
                writer.write(data)
                # Nota: no hacemos await drain aqui para no bloquear el
                # ingest; el heartbeat loop hace drain periodico.
            except Exception:
                dead.append(writer)
        for writer in dead:
            self._sse_clients[symbol].discard(writer)

    def _shutdown(self, headers: Dict[str, str]) -> bytes:
        if self.token is not None:
            auth = headers.get("authorization", "")
            if auth != f"Bearer {self.token}":
                return _json_bytes({"error": "FORBIDDEN",
                                    "detail": "token invalido o ausente"})
        asyncio.create_task(self.stop())
        return _json_bytes({"ok": True, "detail": "parada solicitada"})

    async def _stop_after(self, max_seconds: float) -> None:
        await asyncio.sleep(max_seconds)
        await self.stop()
