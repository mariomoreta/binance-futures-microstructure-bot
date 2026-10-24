"""Pruebas controladas del camino completo de la ventana `market-stream/v1`.

Cubren tres piezas que no necesitan Binance:

  * el evaluador puro de aceptacion (cero mensajes o cadena incompleta nunca
    producen PASS; cada eslabon ausente se declara);
  * el cliente SSE del script contra el servicio real en un puerto efimero con
    transporte simulado (hello/snapshot/provisional/cierre/siguiente, liberacion
    de consumidores y parada limpia);
  * `--finalize`, que incorpora la evidencia DOM sin abrir red.

Lo que NO cubren: recepcion real de Binance ni el grafico en el navegador. Esas
quedan como `UNKNOWN` hasta la ventana autorizada y la captura DOM del operador.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from microstructure_probe.market_cache import MarketCache
from microstructure_probe.market_stream import KlineStreamHub
from microstructure_probe.market_stream_service import MarketStreamService

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "market_stream_window", str(ROOT / "scripts" / "market_stream_window.py"))
window = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(window)

T0 = 1_761_200_000_000
STEP = 60_000
ISO = lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc) \
    .strftime("%Y-%m-%dT%H:%M:%S.000Z")  # noqa: E731


def _event(symbol: str, open_ms: int, *, closed: bool = False, seq: int = 1,
           event_ms: int | None = None) -> dict:
    return {
        "event": "closed" if closed else "candle",
        "recv_ms": open_ms + 2000,
        "symbol": symbol,
        "interval": "1m",
        "open_time_ms": open_ms,
        "close_time_ms": open_ms + STEP - 1 if closed else None,
        "closed": closed,
        "event_ms": event_ms if event_ms is not None else open_ms + 1000,
        "received_ms": open_ms + 1800,
        "seq": seq,
    }


def _identity(symbol: str, interval: str = "1m") -> dict:
    return {"symbol": symbol, "symbol_canonical": symbol, "interval": interval,
            "venue": "binance", "market_type": "usd_m_futures", "source": "ws_kline"}


def _dom(candles: int, *, state: str = "RECIBIENDO", live: str = "LIVE",
         updated_ms: int = T0 + 1000, age_s: int = 3,
         pagination: dict | None = None) -> dict:
    payload = {
        "captured_at_ms": updated_ms + 500,
        "url": "http://127.0.0.1:3020/market-lab",
        "identity": "Binance USD-M · BTCUSDT · 1m · market-stream/v1",
        "state": state,
        "live": live,
        "updated": f"{ISO(updated_ms)} · hace {age_s} s",
        "candles": candles,
        "provisional": 1,
        "down": None,
        "error": None,
        "navigation_count": 1,
        "reload_count": 0,
    }
    if pagination is not None:
        payload["pagination"] = pagination
    return payload


def _run_fixture() -> dict:
    bff_events = [
        _event("BTCUSDT", T0, seq=1),
        _event("BTCUSDT", T0, seq=2),
        _event("BTCUSDT", T0, seq=3),
        _event("BTCUSDT", T0, closed=True, seq=4),
        _event("BTCUSDT", T0 + STEP, seq=5),
        _event("BTCUSDT", T0 + STEP, seq=6),
    ]
    service_events = [
        _event("MINAUSDT", T0, seq=1),
        _event("MINAUSDT", T0 + STEP, seq=2),
    ]
    return {
        "contract_version": "market-stream/v1",
        "mode": "LIVE_WINDOW_EXECUTE",
        "started_at_ms": T0,
        "finished_at_ms": T0 + 180_000,
        "duration_s": 180.0,
        "stop_reason": "ACCEPTANCE_REACHED",
        "target": {"symbols": ["BTCUSDT", "MINAUSDT"], "interval": "1m",
                   "primary": "BTCUSDT"},
        "budget": {"bff": True, "duration_s": 180.0, "max_messages": 1200,
                   "sse_consumers": {"service": 1, "bff": 1, "browser": 1,
                                     "total": 3, "service_symbols": ["MINAUSDT"],
                                     "bff_symbols": ["BTCUSDT"],
                                     "per_stream": {"BTCUSDT": 2, "MINAUSDT": 1}},
                   "browser_consumers": 1},
        "preflight": {"ok": True, "error": None, "port_free": True},
        "service": {
            "pid": 4242,
            "port": 8791,
            "started": True,
            "health_before_consumer": {"connected": False, "attempts": 0,
                                       "consumers": 0, "counters": {}},
            "health_samples": [{"connected": True, "reconnects": 0,
                                "consumers": 3, "counters": {},
                                "streams": [{"symbol": "BTCUSDT", "interval": "1m",
                                             "live": True, "state": "RECEIVING"}]}],
            "health_before_close": {"consumers": 3,
                                    "counters": {"invalid": 0, "identity_mismatch": 0}},
            "health_after_close": {"consumers": 1, "counters": {}},
            "consumers_expected_after_close": 1,
            "after_stop": {"process_exited": True, "exit_code": 0,
                           "port_closed": True, "pidfile_removed": True,
                           "health_refused": True},
        },
        "consumers": {
            "service": {
                "hello": [{"identity": _identity("MINAUSDT")}],
                "snapshot": {"symbol": "MINAUSDT", "interval": "1m", "candles": 299},
                "snapshots": {"MINAUSDT": {"symbol": "MINAUSDT", "candles": 299}},
                "events": service_events,
                "gaps": [],
                "last_status": {"live": False, "connection": {"state": "RECEIVING"}},
                "last_status_recv_ms": T0 + 400,
                "counts": {"candle": 1, "closed": 1, "status": 8, "heartbeat": 2,
                           "gap": 0, "error": 0},
                "first_event_ms": T0 + 500,
                "last_event_ms": T0 + STEP + 2500,
                "errors": [],
            },
            "bff": {
                "hello": [{"identity": _identity("BTCUSDT")}],
                "snapshot": {"symbol": "BTCUSDT", "interval": "1m", "candles": 299},
                "snapshots": {"BTCUSDT": {"symbol": "BTCUSDT", "candles": 299}},
                "events": bff_events,
                "gaps": [],
                "last_status": {"live": True},
                "last_status_recv_ms": T0 + 900,
                "counts": {"candle": 6, "closed": 1, "status": 6, "heartbeat": 2,
                           "gap": 0, "error": 0},
                "first_event_ms": T0 + 500,
                "last_event_ms": T0 + STEP + 500,
                "errors": [],
            },
        },
        "storage": {"canonical_dbs_unchanged": True, "canonical_changed": [],
                    "cache_changed": False},
        "limitations": [],
    }


def _dom_bundle() -> dict:
    return {
        "errors": [],
        "first": _dom(300, updated_ms=T0 + 1000),
        "last": _dom(301, updated_ms=T0 + STEP + 2000, age_s=2,
                     pagination={"candles_before": 300, "candles_after": 598,
                                 "same_identity": True, "error": None}),
        "after": _dom(301, state="DESCONECTADO · servicio detenido",
                      live="no LIVE", updated_ms=T0 + STEP + 3000,
                      pagination={"candles_before": 300, "candles_after": 598,
                                  "same_identity": True, "error": None}),
    }


def _after() -> dict:
    bundle = _dom_bundle()
    bundle["after"]["down"] = ("Servicio de datos detenido: se conserva el histórico "
                               "ya cargado y no se declara LIVE.")
    return bundle


class AcceptanceTests(unittest.TestCase):
    def test_plan_declares_chain_budget_and_stop_rules(self):
        import argparse
        args = argparse.Namespace(
            symbols="BTCUSDT,MINAUSDT", interval="1m", duration=180.0,
            hold_seconds=20.0, max_messages=1200, max_events=6000,
            max_reconnects=3, port=8791, no_bff=False, execute=False)
        payload = window.plan(args)
        self.assertEqual(payload["mode"], "LIVE_WINDOW_PLAN")
        self.assertIn("REQUIERE AUTORIZACION", payload["authorization"])
        self.assertEqual(payload["chain"][1].split(":")[0], "hub+servicio")
        self.assertGreaterEqual(payload["budget"]["duration_s"], 120.0)
        consumers = payload["budget"]["sse_consumers"]
        self.assertEqual(consumers["total"], 2)
        self.assertEqual(consumers["service"], 1)
        self.assertEqual(consumers["bff"], 1)
        self.assertEqual(consumers["browser"], 0)
        self.assertEqual(consumers["per_stream"], {"BTCUSDT": 1, "MINAUSDT": 1})
        self.assertGreaterEqual(len(payload["acceptance"]), 7)
        self.assertIn("--finalize", payload["commands"]["finalize"])

    def test_plan_counts_browser_inside_consumer_budget(self):
        import argparse
        args = argparse.Namespace(
            symbols="BTCUSDT,MINAUSDT", interval="1m", duration=180.0,
            hold_seconds=20.0, max_messages=1200, max_events=6000,
            max_reconnects=3, port=8791, no_bff=False, execute=False,
            browser_consumer=True, await_consumers=1, await_timeout=90.0)
        consumers = window.plan(args)["budget"]["sse_consumers"]
        self.assertEqual(consumers["total"], 3)
        self.assertEqual(consumers["service"], 1)
        self.assertEqual(consumers["bff"], 1)
        self.assertEqual(consumers["browser"], 1)
        self.assertEqual(consumers["per_stream"], {"BTCUSDT": 2, "MINAUSDT": 1})
        self.assertEqual(consumers["service_symbols"], ["MINAUSDT"])
        self.assertEqual(consumers["bff_symbols"], ["BTCUSDT"])
        self.assertLessEqual(consumers["total"], window.MAX_CONSUMERS_PER_STREAM * 2)

    def test_browser_wait_requires_primary_symbol_only(self):
        ready = window.consumer_wait_ready
        self.assertFalse(ready(None, 1, "BTCUSDT"))
        self.assertFalse(ready({"consumers": 0, "streams": []}, 1, "BTCUSDT"))
        # Cambio de contrato en curso: el consumidor aun es MINAUSDT.
        self.assertFalse(ready({"consumers": 1, "streams": [
            {"symbol": "MINAUSDT", "consumers": 1}]}, 1, "BTCUSDT"))
        # Transitorio: el anterior no se ha liberado y el nuevo ya esta.
        self.assertFalse(ready({"consumers": 2, "streams": [
            {"symbol": "MINAUSDT", "consumers": 1},
            {"symbol": "BTCUSDT", "consumers": 1}]}, 1, "BTCUSDT"))
        self.assertTrue(ready({"consumers": 1, "streams": [
            {"symbol": "BTCUSDT", "consumers": 1},
            {"symbol": "MINAUSDT", "consumers": 0}]}, 1, "BTCUSDT"))
        # Sin detalle de streams se acepta el conteo.
        self.assertIsNone(ready({"consumers": 1}, 1, "BTCUSDT"))

    def test_zero_messages_never_passes(self):
        run = _run_fixture()
        run["consumers"]["service"]["events"] = []
        run["consumers"]["bff"]["events"] = []
        run["stop_reason"] = "DURATION"
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("messages_primary", result["failed"])
        self.assertFalse(result["acquisition_finished"])

    def test_budget_exhausted_without_close_fails(self):
        run = _run_fixture()
        run["consumers"]["bff"]["events"] = [
            _event("BTCUSDT", T0, seq=1), _event("BTCUSDT", T0, seq=2),
        ]
        run["stop_reason"] = "DURATION"
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("close_confirmed", result["failed"])
        self.assertIn("next_candle", result["failed"])

    def test_aborted_acquisition_is_unknown_not_pass(self):
        run = _run_fixture()
        run["consumers"]["bff"]["events"] = [_event("BTCUSDT", T0, seq=1)]
        run["stop_reason"] = "MAX_RECONNECTS"
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertIn("provisional_updates", result["missing"])
        self.assertFalse(result["acquisition_finished"])

    def test_full_chain_with_dom_passes(self):
        result = window.evaluate_acceptance(_run_fixture(), _after())
        self.assertEqual(result["verdict"], "PASS", result["verdict_reasons"])
        self.assertTrue(result["acquisition_finished"])
        self.assertEqual(result["visual_review"], "NOT_REVIEWED")

    def test_chain_without_dom_is_unknown(self):
        result = window.evaluate_acceptance(_run_fixture(), {"errors": [
            "DOM_EVIDENCE_MISSING:first,last,after"]})
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertIn("dom_state_live", result["missing"])
        self.assertIn("EVIDENCE_MISSING:dom_state_live", result["verdict_reasons"])

    def test_dom_not_growing_fails(self):
        run = _run_fixture()
        dom = _after()
        dom["last"] = _dom(300, updated_ms=T0 + STEP + 2000,
                           pagination={"candles_before": 300, "candles_after": 598,
                                       "same_identity": True, "error": None})
        result = window.evaluate_acceptance(run, dom)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("dom_candles_grew", result["failed"])

    def test_dom_after_stop_live_fails(self):
        dom = _after()
        dom["after"] = _dom(301, state="RECIBIENDO", live="LIVE")
        result = window.evaluate_acceptance(_run_fixture(), dom)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("dom_after_stop", result["failed"])

    def test_partial_gap_blocks_pass(self):
        run = _run_fixture()
        run["consumers"]["service"]["gaps"] = [{
            "symbol": "BTCUSDT", "interval": "1m", "reason": "SEQUENCE",
            "status": "partial", "expected_from_ms": T0, "expected_to_ms": T0 + STEP,
        }]
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("coverage_intact", result["failed"])

    def test_identity_mismatch_fails(self):
        run = _run_fixture()
        run["consumers"]["bff"]["hello"] = [{"identity": _identity("BTCUSDT", "5m")}]
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("identity_exact", result["failed"])

    def test_bff_disabled_is_unknown(self):
        run = _run_fixture()
        run["budget"]["bff"] = False
        run["budget"]["browser_consumers"] = 0
        run["budget"]["sse_consumers"] = {
            "service": 2, "bff": 0, "browser": 0, "total": 2,
            "service_symbols": ["BTCUSDT", "MINAUSDT"], "bff_symbols": [],
            "per_stream": {"BTCUSDT": 1, "MINAUSDT": 1},
        }
        service = run["consumers"].pop("bff")
        run["consumers"]["service"]["events"] = service["events"] + run["consumers"]["service"]["events"]
        run["consumers"]["service"]["hello"] = [
            {"identity": _identity("BTCUSDT")}, {"identity": _identity("MINAUSDT")}]
        run["service"]["health_before_close"]["consumers"] = 2
        run["service"]["health_samples"][0]["consumers"] = 2
        run["service"]["health_after_close"]["consumers"] = 0
        run["service"]["consumers_expected_after_close"] = 0
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "UNKNOWN", result["verdict_reasons"])
        self.assertIn("bff_delivered", result["missing"])

    def test_bff_without_updates_fails(self):
        run = _run_fixture()
        run["consumers"]["bff"]["counts"]["candle"] = 0
        run["consumers"]["bff"]["counts"]["closed"] = 0
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("bff_delivered", result["failed"])

    def test_service_not_stopped_fails(self):
        run = _run_fixture()
        run["service"]["after_stop"]["pidfile_removed"] = False
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("service_stopped", result["failed"])

    def test_browser_slot_must_be_free_after_script_closes(self):
        run = _run_fixture()
        run["service"]["health_after_close"]["consumers"] = 0
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("consumers_released", result["failed"])

    def test_consumer_peak_above_budget_fails(self):
        run = _run_fixture()
        run["service"]["health_samples"][0]["consumers"] = 4
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("consumer_budget", result["failed"])

    def test_canonical_db_change_fails(self):
        run = _run_fixture()
        run["storage"]["canonical_dbs_unchanged"] = False
        run["storage"]["canonical_changed"] = ["data/microprobe.db"]
        result = window.evaluate_acceptance(run, _after())
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("canonical_dbs_unchanged", result["failed"])

    def test_stream_acceptance_rejects_wrong_close_time(self):
        service = {"events": [
            _event("BTCUSDT", T0, seq=1), _event("BTCUSDT", T0, seq=2),
            {**_event("BTCUSDT", T0, seq=3, closed=True), "close_time_ms": T0 + 5},
            _event("BTCUSDT", T0 + STEP, seq=4),
        ]}
        result = window.stream_acceptance(service, ["BTCUSDT"], "1m")
        self.assertFalse(result["ok"])
        self.assertIsNone(result["close"])
        self.assertFalse(result["closed_provisional"])


class FinalizeTests(unittest.TestCase):
    def test_finalize_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            run_path = path / "run.json"
            run_path.write_text(json.dumps(_run_fixture()), encoding="utf-8")
            dom = _after()
            (path / "dom-1.json").write_text(json.dumps(dom["first"]), encoding="utf-8")
            (path / "dom-2.json").write_text(json.dumps(dom["last"]), encoding="utf-8")
            (path / "dom-stop.json").write_text(json.dumps(dom["after"]), encoding="utf-8")
            code = window.main([
                "--finalize", str(run_path),
                "--dom-first", str(path / "dom-1.json"),
                "--dom-last", str(path / "dom-2.json"),
                "--dom-after-stop", str(path / "dom-stop.json"),
            ])
            self.assertEqual(code, 0)
            saved = json.loads(run_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["verdict"], "PASS")
            self.assertTrue(saved["acquisition_finished"])

    def test_finalize_missing_evidence_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            run_path = path / "run.json"
            run_path.write_text(json.dumps(_run_fixture()), encoding="utf-8")
            code = window.main(["--finalize", str(run_path)])
            self.assertEqual(code, 2)
            saved = json.loads(run_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["verdict"], "UNKNOWN")


class Clock:
    def __init__(self, start_ms: int = T0) -> None:
        self.ms = int(start_ms)

    def __call__(self) -> float:
        return self.ms / 1000.0

    def advance(self, ms: int) -> None:
        self.ms += int(ms)


def _kline(*, symbol: str = "BTCUSDT", open_ms: int = T0, closed: bool = False,
           event_ms: int | None = None, close: str = "100.5") -> str:
    return json.dumps({
        "stream": f"{symbol.lower()}@kline_1m",
        "data": {
            "e": "kline",
            "E": int(event_ms if event_ms is not None else open_ms + 1000),
            "s": symbol,
            "k": {"t": open_ms, "T": open_ms + STEP - 1, "s": symbol, "i": "1m",
                  "o": "100.0", "c": close, "h": "101.0", "l": "99.0",
                  "v": "12.5", "q": "1250.0", "n": 7, "x": bool(closed)},
        },
    })


class ServiceChainTests(unittest.TestCase):
    """Cliente SSE del script contra el servicio real (transporte simulado)."""

    def test_sse_client_sees_lifecycle_and_releases_consumers(self):
        class NullTransport:
            async def run(self, stop):
                await stop.wait()

        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                cache = MarketCache(Path(tmp) / "cache.db")
                cache.init_db()
                hub = KlineStreamHub(clock=Clock())
                service = MarketStreamService(
                    hub=hub, transport=NullTransport(), cache=cache,
                    port=0, pid_path=Path(tmp) / "service.json")
                await service.start()
                port = service.port
                client = window.SseClient("127.0.0.1", port,
                                          "/stream?symbol=BTCUSDT&interval=1m&bars=5",
                                          label="service")
                await client.open()
                stream = client.events()
                try:
                    collected = []
                    while True:
                        event, payload = await asyncio.wait_for(anext(stream), timeout=5.0)
                        collected.append(event)
                        if event == "snapshot":
                            break
                    self.assertIn("hello", collected)
                    hub.on_socket_open()
                    hub.on_message(_kline())
                    hub.on_message(_kline(event_ms=T0 + 1500, close="100.7"))
                    hub.on_message(_kline(closed=True, event_ms=T0 + STEP,
                                          close="100.9"))
                    hub.on_message(_kline(open_ms=T0 + STEP, event_ms=T0 + STEP + 1000,
                                          close="101.2"))
                    events = []
                    while len([e for e in events if e in ("candle", "closed")]) < 4:
                        event, payload = await asyncio.wait_for(anext(stream), timeout=5.0)
                        events.append(event)
                        if event == "closed":
                            self.assertEqual(payload["close_time_ms"], T0 + STEP - 1)
                            self.assertTrue(payload["closed"])
                    self.assertGreaterEqual(events.count("candle"), 3)
                    self.assertIn("closed", events)
                    self.assertTrue(window._port_open("127.0.0.1", port))
                finally:
                    client.close()
                    for _ in range(80):
                        if hub.total_consumers() == 0:
                            break
                        await asyncio.sleep(0.1)
                self.assertEqual(hub.total_consumers(), 0)
                await service.stop()
                self.assertFalse((Path(tmp) / "service.json").exists())
                self.assertFalse(window._port_open("127.0.0.1", port))

        asyncio.run(scenario())

    def test_sse_client_reads_chunked_bff_like_proxy(self):
        """Un proxy que reenvia chunked (como el BFF) se parsea igual."""
        async def handler(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                         b"Transfer-Encoding: chunked\r\n\r\n")
            await writer.drain()
            for frame in (b"event: hello\ndata: {\"a\":1}\n\n",
                          b"event: candle\ndata: {\"b\":2}\n\n"):
                writer.write(f"{len(frame):X}\r\n".encode() + frame + b"\r\n")
                await writer.drain()
            writer.write(b"0\r\n\r\n")
            await writer.drain()
            writer.close()

        async def scenario():
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            client = window.SseClient("127.0.0.1", port, "/stream", label="bff")
            await client.open()
            seen = []
            async for event, payload in client.events():
                seen.append((event, payload))
            client.close()
            server.close()
            await server.wait_closed()
            self.assertEqual([name for name, _ in seen], ["hello", "candle"])
            self.assertEqual(seen[1][1], {"b": 2})

        asyncio.run(scenario())


class OrchestrationTests(unittest.TestCase):
    """Cadena completa controlada: WS local -> servicio real -> SSE -> evaluador.

    El WS local imita la forma del mensaje combinado de Binance. NO acredita
    recepcion real: el JSON resultante queda con ``transport.origin`` =
    ``loopback_test`` y sin evidencia DOM, por lo que el veredicto es UNKNOWN.
    """

    def test_window_orchestrates_service_and_detects_close_without_bff(self):
        from urllib.parse import parse_qs, urlsplit

        from websockets.asyncio.server import serve

        async def fake_exchange(ws):
            request = getattr(ws, "request", None)
            path = getattr(request, "path", "") or getattr(ws, "path", "")
            streams = (parse_qs(urlsplit(path).query).get("streams") or [""])[0]
            symbols = [item.split("@")[0].upper() for item in streams.split("/")
                       if "@kline_" in item]
            now = window.now_ms()
            base = now - (now % STEP)
            try:
                for index, symbol in enumerate(symbols):
                    for step, close in enumerate(("100.1", "100.5", "100.9")):
                        await ws.send(_kline(symbol=symbol, open_ms=base, close=close,
                                             event_ms=base + 10 + step * 20))
                        await asyncio.sleep(0.03)
                    if index == 0:
                        await ws.send(_kline(symbol=symbol, open_ms=base, closed=True,
                                             close="101.0", event_ms=base + STEP))
                        await ws.send(_kline(symbol=symbol, open_ms=base + STEP,
                                             close="101.4", event_ms=base + STEP + 50))
                await ws.wait_closed()
            except asyncio.CancelledError:
                raise

        def free_port() -> int:
            import socket as _socket
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                return int(sock.getsockname()[1])

        import argparse
        import os

        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                cached_env = {key: os.environ.get(key) for key in (
                    "MICROPROBE_MARKET_CACHE_DB", "MICROPROBE_MARKET_STREAM_PID")}
                os.environ["MICROPROBE_MARKET_CACHE_DB"] = str(Path(tmp) / "cache.db")
                os.environ["MICROPROBE_MARKET_STREAM_PID"] = str(Path(tmp) / "service.json")
                MarketCache(Path(tmp) / "cache.db").init_db()
                ws_server = await serve(fake_exchange, "127.0.0.1", 0)
                ws_port = ws_server.sockets[0].getsockname()[1]
                port = free_port()
                args = argparse.Namespace(
                    symbols="BTCUSDT,MINAUSDT", interval="1m", duration=20.0,
                    hold_seconds=0.5, max_messages=40, max_events=400,
                    max_reconnects=1, port=port, host="127.0.0.1",
                    dashboard_url="http://127.0.0.1:3020", no_bff=True,
                    base_url=f"ws://127.0.0.1:{ws_port}", execute=True,
                    out=None, dom_first=None, dom_last=None, dom_after_stop=None,
                    visual_review=None, screenshot=None, finalize=None)
                try:
                    run = await window.run_window(args)
                finally:
                    ws_server.close()
                    await ws_server.wait_closed()
                    for key, value in cached_env.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value

                self.assertEqual(run["stop_reason"], "ACCEPTANCE_REACHED")
                self.assertTrue(run["acquisition_finished"])
                self.assertEqual(run["transport"]["origin"], "loopback_test")
                self.assertEqual(run["verdict"], "UNKNOWN")
                self.assertIn("dom_state_live", run["missing"])
                events = run["consumers"]["service"]["events"]
                closed = [e for e in events if e.get("closed")]
                self.assertTrue(closed)
                self.assertEqual(closed[0]["close_time_ms"] % STEP, STEP - 1)
                self.assertTrue(any(e["symbol"] == "MINAUSDT" for e in events))
                after = run["service"]["after_stop"]
                self.assertTrue(after["process_exited"])
                self.assertTrue(after["port_closed"])
                self.assertTrue(after["pidfile_removed"])
                self.assertFalse(window._port_open("127.0.0.1", port))
                self.assertFalse((Path(tmp) / "service.json").exists())
                evidence_dir = os.environ.get("MARKET_STREAM_WINDOW_EVIDENCE_DIR")
                if evidence_dir:
                    target = Path(evidence_dir)
                    target.mkdir(parents=True, exist_ok=True)
                    (target / "market-stream-window-loopback.json").write_text(
                        json.dumps(run, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

        asyncio.run(scenario())

    def test_missing_browser_aborts_before_opening_own_consumers(self):
        """Con `--await-consumers 1` y sin navegador, para sin contactar Binance."""
        import argparse
        import os

        def free_port() -> int:
            import socket as _socket
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                return int(sock.getsockname()[1])

        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                cached_env = {key: os.environ.get(key) for key in (
                    "MICROPROBE_MARKET_CACHE_DB", "MICROPROBE_MARKET_STREAM_PID")}
                os.environ["MICROPROBE_MARKET_CACHE_DB"] = str(Path(tmp) / "cache.db")
                os.environ["MICROPROBE_MARKET_STREAM_PID"] = str(Path(tmp) / "service.json")
                MarketCache(Path(tmp) / "cache.db").init_db()
                port = free_port()
                args = argparse.Namespace(
                    symbols="BTCUSDT,MINAUSDT", interval="1m", duration=20.0,
                    hold_seconds=0.5, max_messages=40, max_events=400,
                    max_reconnects=1, port=port, host="127.0.0.1",
                    dashboard_url="http://127.0.0.1:3020", no_bff=False,
                    base_url="ws://127.0.0.1:1", execute=True,
                    out=None, dom_first=None, dom_last=None, dom_after_stop=None,
                    visual_review=None, screenshot=None, finalize=None,
                    browser_consumer=True, await_consumers=1, await_timeout=3.0)
                try:
                    run = await window.run_window(args)
                finally:
                    for key, value in cached_env.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value
                self.assertEqual(run["stop_reason"], "BROWSER_NOT_ATTACHED")
                self.assertFalse(run["acquisition_finished"])
                self.assertEqual(run["consumers"], {})
                wait = run["service"]["browser_wait"]
                self.assertFalse(wait["ok"])
                self.assertLessEqual(wait["waited_ms"], 8000)
                self.assertTrue(run["service"]["after_stop"]["process_exited"])
                self.assertTrue(run["service"]["after_stop"]["port_closed"])

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
