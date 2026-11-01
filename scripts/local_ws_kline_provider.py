"""Proveedor local integrado de klines para el arnés de sesión de ingeniería.

Sirve, sobre loopback (cero Binance):
  * HTTP ``GET /fapi/v1/klines`` para cargar el contexto reciente vía
    ``HistoryClient`` (mismos modos que ``local_kline_provider``).
  * WS que emite mensajes de kline en formato combined stream de Binance
    (``{"stream": "<symbol>@kline_<interval>", "data": {...}}``) para que el
    servicio ``market-stream --transport local`` los reciba, los parsee y los
    reparta como frames SSE a la sesión de ingeniería.

El WS admite una secuencia programable de velas (abierta/provisional/cerradas)
para reproducir el recorrido completo: contexto reciente cerrado, vela
provisional y dos cierres nuevos posteriores, con identidad separada por símbolo.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

STEP_MS = 60_000
BASE_PRICE = {"BTCUSDT": 100000.0, "MINAUSDT": 1.05}

# Un mensaje de kline en formato combined stream de Binance.
def kline_message(
    symbol: str,
    interval: str,
    open_ms: int,
    close: float,
    high: Optional[float] = None,
    low: Optional[float] = None,
    volume: float = 100.0,
    trades: int = 42,
    closed: bool = False,
    event_ms: Optional[int] = None,
) -> str:
    step = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
            "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}.get(
                interval, 60_000)
    open_px = BASE_PRICE.get(symbol, 100.0)
    high_px = high if high is not None else open_px * 1.001
    low_px = low if low is not None else open_px * 0.999
    close_px = close
    event = event_ms if event_ms is not None else open_ms + 1000
    return json.dumps({
        "stream": f"{symbol.lower()}@kline_{interval}",
        "data": {
            "e": "kline", "E": event, "s": symbol,
            "k": {
                "t": open_ms, "T": open_ms + step - 1, "s": symbol,
                "i": interval,
                "o": f"{open_px:.8f}", "c": f"{close_px:.8f}",
                "h": f"{high_px:.8f}", "l": f"{low_px:.8f}",
                "v": f"{volume:.8f}", "q": f"{close_px * volume:.8f}",
                "n": trades, "x": bool(closed),
            },
        },
    })


class _HttpHandler(BaseHTTPRequestHandler):
    provider: "LocalWsklineProvider"

    def log_message(self, format, *args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        url = urlsplit(self.path)
        if url.path != "/fapi/v1/klines":
            self._send(404, {"code": -404, "msg": "path not found"})
            return
        params = parse_qs(url.query)
        symbol = (params.get("symbol") or [""])[0].upper()
        start_time = int((params.get("startTime") or [0])[0])
        end_time = int((params.get("endTime") or [0])[0])
        limit = int((params.get("limit") or [500])[0])
        mode = self.provider.mode_for(symbol)
        if mode == "json_error":
            self._send(200, {"code": -1003, "msg": "Invalid parameter."})
            return
        if mode == "non_json":
            self._send_raw(200, "esto no es json en absoluto", "text/plain")
            return
        if mode == "empty":
            self._send(200, [])
            return
        bars = []
        px = BASE_PRICE.get(symbol, 100.0)
        ot = start_time - STEP_MS
        count = 0
        while ot <= end_time and count < limit:
            close = px * (1.0 + 0.0002 * count)
            bars.append([
                ot, f"{px:.8f}", f"{px * 1.001:.8f}", f"{px * 0.999:.8f}",
                f"{close:.8f}", "100.0", ot + STEP_MS - 1, "10000.0", 42,
                "90.0", "9000.0", "0",
            ])
            px = close
            ot += STEP_MS
            count += 1
        self._send(200, bars)

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_raw(self, status: int, text: str, content_type: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LocalWsklineProvider:
    """Servidor HTTP (/fapi/v1/klines) + WS (stream de klines) en loopback."""

    def __init__(
        self,
        http_port: int,
        ws_port: int,
        klines_modes: Optional[Dict[str, str]] = None,
        sequence: Optional[List[Dict[str, Any]]] = None,
        repeat: bool = True,
    ) -> None:
        self.http_port = int(http_port)
        self.ws_port = int(ws_port)
        self.klines_modes = dict(klines_modes or {})
        self.sequence = sequence  # lista de dicts para kline_message
        self.repeat = bool(repeat)
        self.http_server: Optional[ThreadingHTTPServer] = None
        self.ws_server: Any = None
        self.http_thread: Optional[threading.Thread] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.ready = threading.Event()
        self.ws_connections: list = []
        self.lock = threading.Lock()

    def mode_for(self, symbol: str) -> str:
        return self.klines_modes.get(symbol, "ok")

    def _default_sequence(self, start_ms: int) -> List[Dict[str, Any]]:
        """Secuencia por defecto: contexto reciente cerrado para ambos
        símbolos, una vela provisional y dos cierres nuevos posteriores."""
        seq: List[Dict[str, Any]] = []
        now = int(time.time() * 1000)
        base = start_ms or now
        # Velas cerradas recientes (contexto de mercado) para ambos símbolos.
        for i in range(4):
            ot = base - 4 * STEP_MS + i * STEP_MS
            for sym, px in (("BTCUSDT", 100000.0), ("MINAUSDT", 1.05)):
                seq.append({
                    "symbol": sym, "interval": "1m", "open_ms": ot,
                    "close": px * (1.0 + 0.0001 * i),
                    "closed": True, "event_ms": ot + 1000,
                })
        # Vela provisional (no cerrada) de MINAUSDT.
        seq.append({
            "symbol": "MINAUSDT", "interval": "1m", "open_ms": base,
            "close": 1.05 * 1.0002, "closed": False, "event_ms": base + 500,
        })
        # Dos cierres nuevos posteriores (uno por símbolo).
        seq.append({
            "symbol": "MINAUSDT", "interval": "1m", "open_ms": base + STEP_MS,
            "close": 1.05 * 1.0004, "closed": True, "event_ms": base + 60000,
        })
        seq.append({
            "symbol": "BTCUSDT", "interval": "1m", "open_ms": base + STEP_MS,
            "close": 100000.0 * 1.0005, "closed": True,
            "event_ms": base + 60000,
        })
        return seq

    # --- HTTP -----------------------------------------------------------
    def _start_http(self) -> None:
        _HttpHandler.provider = self
        self.http_server = ThreadingHTTPServer(
            ("127.0.0.1", self.http_port), _HttpHandler)
        self.http_thread = threading.Thread(
            target=self.http_server.serve_forever,
            name="local-ws-kline-http", daemon=True)
        self.http_thread.start()

    def _stop_http(self) -> None:
        if self.http_server is not None:
            try:
                self.http_server.shutdown()
                self.http_server.server_close()
            except Exception:
                pass

    # --- WS -------------------------------------------------------------
    async def _ws_handler(self, websocket, path):  # type: ignore[no-untyped-def]
        """Acepta una conexión WS, drena mensajes de control y emite la
        secuencia programada de klines."""
        self.ws_connections.append(websocket)
        try:
            # Drenar mensajes de control (SUBSCRIBE/UNSUBSCRIBE) sin bloquear
            # la emisión de la secuencia.
            async def _drain() -> None:
                try:
                    async for _raw in websocket:
                        pass
                except Exception:
                    pass

            drain_task = None
            try:
                import asyncio as _asyncio
                drain_task = _asyncio.ensure_future(_drain())
            except Exception:
                drain_task = None

            import asyncio as _asyncio

            async def _emit(item: Dict[str, Any]) -> None:
                await websocket.send(kline_message(
                    item["symbol"], item["interval"], int(item["open_ms"]),
                    float(item["close"]),
                    high=float(item.get("high", 0) or 0) or None,
                    low=float(item.get("low", 0) or 0) or None,
                    volume=float(item.get("volume", 100.0)),
                    trades=int(item.get("trades", 42)),
                    closed=bool(item.get("closed", False)),
                    event_ms=int(item.get("event_ms", 0) or 0) or None,
                ))

            sequence = self.sequence or self._default_sequence(None)
            # Emite la secuencia una vez; si repeat, la repite periodicamente
            # para que cualquier consumidor que se suscriba tarde reciba los
            # eventos (sin Binance). Las repeticiones de un mismo open_time se
            # descartan como duplicado (motivo visible en el hub).
            try:
                for item in sequence:
                    await _emit(item)
                    await _asyncio.sleep(0.05)
                if self.repeat:
                    while True:
                        await _asyncio.sleep(2.0)
                        for item in sequence:
                            await _emit(item)
                            await _asyncio.sleep(0.05)
                else:
                    # Mantener la conexión abierta sin repetir: el drive no
                    # detecta TRANSPORT_LOST prematuramente.
                    while True:
                        await _asyncio.sleep(3600)
            except Exception:
                pass  # cliente desconectado: se cierra esta conexión WS
        finally:
            if drain_task is not None:
                drain_task.cancel()
            with self.lock:
                if websocket in self.ws_connections:
                    self.ws_connections.remove(websocket)

    def _start_ws(self) -> None:
        import websockets  # tipo: depende del entorno de prueba

        async def _handler(websocket):  # websockets 15: solo connection
            await self._ws_handler(websocket, None)

        self.ws_thread = threading.Thread(target=self._run_ws,
                                          name="local-ws-kline-ws",
                                          args=(websockets, _handler),
                                          daemon=True)
        self.ws_thread.start()

    def _run_ws(self, websockets_mod, handler) -> None:
        import asyncio as _asyncio
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._ws_serve(websockets_mod, handler))
        except Exception:  # noqa: BLE001 - hilo auxiliar
            pass
        finally:
            loop.close()

    async def _ws_serve(self, websockets_mod, handler) -> None:
        async with websockets_mod.serve(handler, "127.0.0.1", self.ws_port) as server:
            self.ws_server = server
            self.ready.set()  # el WS ya escucha
            await server.wait_closed()

    def _stop_ws(self) -> None:
        if self.ws_server is not None:
            try:
                self.ws_server.close_servers()
            except Exception:
                pass

    # --- ciclo de vida --------------------------------------------------
    def start(self) -> None:
        self._start_http()
        self._start_ws()
        self.ready.wait(10.0)

    def stop(self) -> None:
        self._stop_ws()
        self._stop_http()
        if self.ws_thread is not None:
            self.ws_thread.join(timeout=5.0)
        if self.http_thread is not None:
            self.http_thread.join(timeout=5.0)
