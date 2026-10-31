"""Proveedor HTTP local de klines para pruebas del arnés de ingeniería (sin Binance).

Sirve ``GET /fapi/v1/klines`` con cuatro comportamientos configurables por
símbolo para ejercitar el arnés sin tocar la red pública:

* ``ok``      : lista válida de klines cerradas (12 campos), precios muy
                distintos por símbolo, contexto reciente, cierre conocido en T.
* ``json_error`` : cuerpo JSON válido pero no lista (ej. error de Binance).
* ``non_json`` : cuerpo que no es JSON.
* ``empty``   : lista vacía ``[]``.

Solo se usa en modo ``local`` (preflight/pruebas). Nunca se conecta a Binance.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlsplit

STEP_MS = 60_000

# Precios muy distintos por símbolo (para no confundir identidades).
BASE_PRICE = {"BTCUSDT": 100000.0, "MINAUSDT": 1.05}


class _Handler(BaseHTTPRequestHandler):
    provider: "LocalKlineProvider"  # set by the server

    def log_message(self, format, *args):  # noqa: A002
        return  # silencioso en pruebas

    def do_GET(self):  # noqa: N802
        url = urlsplit(self.path)
        path = url.path
        params = parse_qs(url.query)
        symbol = (params.get("symbol") or [""])[0].upper()
        interval = (params.get("interval") or ["1m"])[0]
        start_time = int((params.get("startTime") or [0])[0])
        end_time = int((params.get("endTime") or [0])[0])
        limit = int((params.get("limit") or [500])[0])

        mode = self.provider.mode_for(symbol)
        now = int(time.time() * 1000)

        if path != "/fapi/v1/klines":
            self._send(404, {"code": -404, "msg": "path not found"})
            return

        if mode == "json_error":
            self._send(200, {"code": -1003, "msg": "Invalid parameter."})
            return
        if mode == "non_json":
            self._send_raw(200, "esto no es json en absoluto", "text/plain")
            return
        if mode == "empty":
            self._send(200, [])
            return

        # modo "ok": klines cerradas recientes, una por minuto, cierre conocido.
        bars = []
        px = BASE_PRICE.get(symbol, 100.0)
        # Empezamos justo antes de start_time y cubrimos hasta end_time.
        ot = start_time - STEP_MS
        count = 0
        while ot <= end_time and count < limit:
            close = px * (1.0 + 0.0002 * count)
            bars.append([
                ot,                              # 0 open_time
                f"{px:.8f}",                     # 1 open
                f"{px * 1.001:.8f}",             # 2 high
                f"{px * 0.999:.8f}",             # 3 low
                f"{close:.8f}",                  # 4 close
                "100.0",                         # 5 volume
                ot + STEP_MS - 1,                # 6 close_time (cerrada)
                "10000.0",                       # 7 quote_volume
                42,                              # 8 trade_count
                "90.0",                          # 9 taker_buy_base
                "9000.0",                        # 10 taker_buy_quote
                "0",                             # 11 ignore
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


class LocalKlineProvider:
    """Servidor HTTP local (un hilo) que emula /fapi/v1/klines por símbolo."""

    def __init__(self, port: int, modes: Optional[Dict[str, str]] = None) -> None:
        self.port = int(port)
        self.modes = dict(modes or {})
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.ready = threading.Event()
        self.requests: list = []

    def mode_for(self, symbol: str) -> str:
        return self.modes.get(symbol, "ok")

    def start(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)
        _Handler.provider = self
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True, name="local-kline-provider")
        self.thread.start()
        self.ready.wait(10.0)

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5.0)

    def iso(self, ms: int) -> str:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


if __name__ == "__main__":  # pragma: no cover
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18799
    prov = LocalKlineProvider(port, {"BTCUSDT": "ok", "MINAUSDT": "ok"})
    prov.start()
    print("provider en", port, flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        prov.stop()
