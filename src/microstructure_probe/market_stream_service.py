"""Servicio local de datos ``market-stream/v1`` (SSE sobre loopback).

Arranque/parada explicitos. NO arranca el monitor del bot, NO toca el trio
canonico y NO escribe velas: el estado vive en memoria y el snapshot se lee del
almacen existente en modo lectura.

Uso (PowerShell, desde la raiz del repositorio):

    python scripts/market_stream_service.py --port 8791
    python scripts/market_stream_service.py --port 8791 --stop

Endpoints (solo 127.0.0.1):

    GET  /health          estado de conexion, streams, contadores y limites
    GET  /stream?...      SSE: hello, snapshot, candle, closed, gap, status, heartbeat
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
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from .market_cache import MarketCache
from .market_explorer import EXPLORABLE_INTERVALS, series_payload
from .market_stream import (
    FRESH_MS,
    STALE_MS,
    STREAM_CONTRACT_VERSION,
    BinanceKlineTransport,
    KlineStreamHub,
    build_recovery,
)

DEFAULT_PORT = 8791
DEFAULT_HOST = "127.0.0.1"
MAX_REQUEST_BYTES = 16 * 1024
MAX_BARS = 1000
MIN_BARS = 1
SERVICE_VERSION = "market-stream-service/v1"


def _pid_path() -> Path:
    override = os.environ.get("MICROPROBE_MARKET_STREAM_PID")
    return Path(override) if override else Path("data/market-stream/service.json")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _chunked(data: bytes) -> bytes:
    return f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n"


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
        pid_path: Optional[Path] = None,
        max_seconds: Optional[float] = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.token = token or os.environ.get("MICROPROBE_STREAM_TOKEN") or None
        self.cache = cache or MarketCache()
        self.hub = hub or KlineStreamHub(recovery=build_recovery(_rest_client()))
        self.transport = transport or BinanceKlineTransport(
            self.hub, **({"base_url": base_url} if base_url else {})
        )
        self.pid_path = Path(pid_path) if pid_path is not None else _pid_path()
        self.max_seconds = max_seconds
        self.started_at_ms = _now_ms()
        self.stop_event = asyncio.Event()
        self._server: Optional[asyncio.AbstractServer] = None
        self._tasks: list[asyncio.Task] = []
        self._client_tasks: set[asyncio.Task] = set()
        self.consumers_served = 0
        self.requests_total = 0

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
                    "source": "cache", "generated_at_ms": _now_ms(),
                }
            await self._write_sse(writer, _sse_frame("snapshot", snapshot))
            last_open = int((snapshot.get("observed") or {}).get("end_ms") or 0) or None
            self.hub.ready(consumer, last_open)
            status = self.hub.consumer_status(consumer)
            if status is not None:
                await self._write_sse(writer, _sse_frame("status", status))
            while not consumer.closed and not self.stop_event.is_set():
                if disconnected.done():
                    break
                try:
                    item = await asyncio.wait_for(consumer.queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
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
                if item is None:
                    break
                event, payload = item
                await self._write_sse(writer, _sse_frame(event, payload))
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self.hub.unsubscribe(consumer)
            disconnected.cancel()
            self._client_tasks.discard(disconnected)

    async def _write_sse(self, writer: asyncio.StreamWriter, frame: bytes | str) -> None:
        data = frame.encode("utf-8") if isinstance(frame, str) else frame
        writer.write(_chunked(data))
        await writer.drain()

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
            "generated_at_ms": _now_ms(),
            "times": {"unit": "ms", "epoch": "unix_utc"},
        })
        return payload


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
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--max-seconds", type=float, default=None,
                       help="parada automatica (solo ventana acotada autorizada)")
    parser.add_argument("--stop", action="store_true", help="detiene el servicio en --port")
    args = parser.parse_args(argv)

    if args.stop:
        result = stop_running(args.port)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    service = MarketStreamService(
        host=args.host, port=args.port, base_url=args.base_url,
        max_seconds=args.max_seconds,
    )

    async def _main() -> None:
        await service.start()
        print(json.dumps({
            "service": SERVICE_VERSION, "pid": os.getpid(),
            "url": f"http://{service.host}:{service.port}",
            "contract_version": STREAM_CONTRACT_VERSION,
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
