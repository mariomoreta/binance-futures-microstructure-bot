"""Transporte del servicio market-stream: falla cerrado sin configuracion local.

Una configuracion de transporte ausente o incorrecta debe detener el arranque
con codigo 2 **sin abrir ningun socket**: no existe fallback al endpoint
publico. La activacion publica es explicita (``--transport public``).
"""

from __future__ import annotations

import asyncio
import io
import json
import socket
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from microstructure_probe import market_stream_service as svc
from microstructure_probe.market_cache import MarketCache

try:  # websockets ya es dependencia del transporte real
    import websockets
except Exception:  # pragma: no cover - entorno sin websockets
    websockets = None


class ResolveTransportTests(unittest.TestCase):
    def test_local_requires_base_url(self):
        with self.assertRaises(svc.TransportConfigError):
            svc.resolve_transport("local", None)

    def test_local_rejects_public_and_invalid_urls(self):
        for url in (
            "wss://fstream.binance.com",
            "ws://fstream.binance.com:9443",
            "ws://example.com:80",
            "http://127.0.0.1:8799",
            "https://127.0.0.1:8799",
            "ws://127.0.0.1",
            "ws://10.0.0.1:8799",
        ):
            with self.subTest(url=url):
                with self.assertRaises(svc.TransportConfigError):
                    svc.resolve_transport("local", url)

    def test_local_accepts_only_loopback(self):
        for url in ("ws://127.0.0.1:8799", "ws://localhost:8799",
                    "ws://[::1]:8799"):
            with self.subTest(url=url):
                plan = svc.resolve_transport("local", url)
                self.assertEqual(plan["mode"], svc.TRANSPORT_LOCAL)
                self.assertEqual(plan["base_url"], url)
                self.assertFalse(plan["recovery"])

    def test_public_is_explicit_and_rejects_base_url(self):
        with self.assertRaises(svc.TransportConfigError):
            svc.resolve_transport(None, None)
        with self.assertRaises(svc.TransportConfigError):
            svc.resolve_transport("public", "ws://127.0.0.1:8799")
        plan = svc.resolve_transport("public", None)
        self.assertEqual(plan["mode"], svc.TRANSPORT_PUBLIC)
        self.assertTrue(plan["recovery"])


class ServiceTransportTests(unittest.TestCase):
    def test_missing_transport_does_not_build_public_transport(self):
        with mock.patch.object(svc, "BinanceKlineTransport") as transport:
            with self.assertRaises(svc.TransportConfigError):
                svc.MarketStreamService(port=0)
            transport.assert_not_called()

    def test_local_transport_points_to_loopback_without_recovery(self):
        with mock.patch.object(svc, "_rest_client") as rest:
            service = svc.MarketStreamService(
                port=0, transport_mode="local",
                base_url="ws://127.0.0.1:8799")
            rest.assert_not_called()
        self.assertEqual(service.transport_mode, "local")
        self.assertEqual(service.transport.base_url, "ws://127.0.0.1:8799")
        self.assertIsNone(service.hub._recovery)

    def test_public_transport_is_explicit(self):
        with mock.patch.object(svc, "_rest_client", return_value=object()):
            service = svc.MarketStreamService(
                port=0, transport_mode="public")
        self.assertEqual(service.transport_mode, "public")
        self.assertIsNotNone(service.hub._recovery)
        self.assertIn("binance", service.transport.base_url)

    def test_injected_transport_is_not_touched(self):
        transport = mock.MagicMock()
        service = svc.MarketStreamService(port=0, transport=transport)
        self.assertIs(service.transport, transport)
        self.assertEqual(service.transport_mode, "injected")


class FailClosedCliTests(unittest.TestCase):
    """Configuracion local ausente/incorrecta => exit 2 y cero conexiones."""

    def _run(self, argv):
        err = io.StringIO()
        calls: list = []

        def guard(sock, address):
            calls.append(address)
            raise AssertionError(f"conexion inesperada: {address}")

        with mock.patch.object(socket.socket, "connect", guard), \
                mock.patch("socket.create_connection",
                           side_effect=AssertionError("conexion inesperada")), \
                mock.patch.object(socket.socket, "connect_ex", guard):
            with redirect_stderr(err):
                code = svc.main(argv)
        return code, err.getvalue(), calls

    def test_no_transport_exits_2_without_sockets(self):
        code, err, calls = self._run([])
        self.assertEqual(code, 2)
        self.assertIn("TRANSPORT_CONFIG", err)
        self.assertEqual(calls, [])

    def test_local_without_base_url_exits_2(self):
        code, err, calls = self._run(["--transport", "local"])
        self.assertEqual(code, 2)
        self.assertIn("TRANSPORT_CONFIG", err)
        self.assertEqual(calls, [])

    def test_local_with_public_url_exits_2(self):
        code, err, calls = self._run([
            "--transport", "local",
            "--base-url", "wss://fstream.binance.com"])
        self.assertEqual(code, 2)
        self.assertIn("TRANSPORT_CONFIG", err)
        self.assertEqual(calls, [])

    def test_base_url_without_transport_exits_2(self):
        code, err, calls = self._run([
            "--base-url", "ws://127.0.0.1:8799"])
        self.assertEqual(code, 2)
        self.assertIn("TRANSPORT_CONFIG", err)
        self.assertEqual(calls, [])


class LocalTransportRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Transporte local real: cero resoluciones del host publico."""

    async def test_local_transport_never_resolves_binance(self):
        if websockets is None:  # pragma: no cover
            self.skipTest("websockets no disponible")

        hosts: list[str] = []
        addresses: list = []
        real_getaddrinfo = socket.getaddrinfo
        real_connect = socket.socket.connect

        def spy(host, port, *args, **kwargs):
            hosts.append(str(host))
            return real_getaddrinfo(host, port, *args, **kwargs)

        def spy_connect(sock, address):
            addresses.append(address)
            return real_connect(sock, address)

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        ws_port = probe.getsockname()[1]
        probe.close()
        stop = asyncio.Event()

        async def fake_upstream(websocket):
            request = getattr(websocket, "request", None)
            target = getattr(request, "path", "") or ""
            streams = []
            if "streams=" in target:
                streams = [part for part in
                           target.split("streams=", 1)[1].split("&")[0].split("/")
                           if part]
            try:
                while not stop.is_set():
                    stamp = svc._now_ms()
                    for stream in streams:
                        symbol, _, interval = stream.partition("@kline_")
                        step = 3_600_000
                        open_ms = stamp - stamp % step
                        await websocket.send(json.dumps({
                            "stream": stream,
                            "data": {
                                "e": "kline", "E": stamp,
                                "s": symbol.upper(),
                                "k": {"s": symbol.upper(), "i": interval,
                                      "t": open_ms, "T": open_ms + step - 1,
                                      "o": "100", "h": "101", "l": "99",
                                      "c": "100", "v": "1", "q": "100",
                                      "n": 3, "x": False},
                            },
                        }))
                    await asyncio.sleep(0.1)
            except Exception:
                return

        server = await websockets.serve(fake_upstream, "127.0.0.1", ws_port)
        with tempfile.TemporaryDirectory() as tmp:
            cache = MarketCache(Path(tmp) / "cache.db")
            cache.init_db()
            service = svc.MarketStreamService(
                port=0, transport_mode="local",
                base_url=f"ws://127.0.0.1:{ws_port}",
                cache=cache, pid_path=Path(tmp) / "service.json")
            self.assertIsNone(service.hub._recovery)
            try:
                with mock.patch.object(socket, "getaddrinfo", spy), \
                        mock.patch.object(socket.socket, "connect", spy_connect):
                    await service.start()
                    reader, writer = await asyncio.open_connection(
                        "127.0.0.1", service.port)
                    writer.write((
                        "GET /stream?symbol=ZZZUSDT&interval=1h&bars=5 HTTP/1.1\r\n"
                        "Host: 127.0.0.1\r\nAccept: text/event-stream\r\n\r\n"
                    ).encode("ascii"))
                    await writer.drain()
                    head = b""
                    deadline = asyncio.get_running_loop().time() + 20
                    while b"event: candle" not in head:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            self.fail("no llego ninguna vela del WS local")
                        chunk = await asyncio.wait_for(reader.read(8192),
                                                       timeout=remaining)
                        if not chunk:
                            self.fail("stream cerrado antes de la vela")
                        head += chunk
                    health = service._health_payload()
                    self.assertEqual(health["transport"]["mode"], "local")
                    self.assertIn("127.0.0.1", health["transport"]["base_url"])
                    # 1 consumidor SSE del token + 1 suscripcion interna del
                    # contexto BTC (el simbolo de prueba no es el benchmark).
                    # Consumidores del hub incluidos los internos.
                    self.assertEqual(health["consumers"], 2)

                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                    deadline = asyncio.get_running_loop().time() + 10
                    while service.hub.health().get("consumers") != 0:
                        if asyncio.get_running_loop().time() > deadline:
                            self.fail("el consumidor no se libero")
                        await asyncio.sleep(0.05)
            finally:
                await service.stop()
                stop.set()
                server.close()
                await server.wait_closed()

        public = [host for host in hosts
                  if "binance" in host or "fstream" in host]
        self.assertEqual(public, [], f"resoluciones publicas: {public}")
        # En Windows el Proactor no usa socket.connect de Python; si se
        # registra alguna conexion, debe ser loopback.
        for address in addresses:
            host = address[0] if isinstance(address, tuple) else address
            self.assertIn(str(host), ("127.0.0.1", "::1", "localhost"),
                          f"conexion no loopback: {address}")
        self.assertEqual(service.transport.base_url, f"ws://127.0.0.1:{ws_port}")
        self.assertIsNone(service.hub._recovery)


if __name__ == "__main__":
    unittest.main()
