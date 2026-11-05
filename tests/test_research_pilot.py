"""Regresiones y cadena completa sincronizada del piloto prospectivo.

Pruebas acotadas del camino productivo corregido:
- Frescura INDEPENDIENTE por fuente (libro obsoleto + flujo fresco y el caso
  inverso); nunca se clasifica como apto con datos obsoletos.
- Ventana completa / calentamiento: flujo incompleto no es apto y conserva un
  motivo explicito (fuera del conjunto apto).
- decision_ms = instante real de evaluacion (el reloj del piloto), no
  retrodatado; todas las disponibilidades <= decision_ms.
- Presupuesto HTTP efectivo: siguiente intento bloqueado ANTES del transporte.
- Rotacion de seguimiento sin reiniciar contadores acumulados de WS.
- Modo local rechazando destinos publicos antes del envio.
- Cadena completa HTTP/WS loopback con reloj manual SIN dormir y SIN carreras:
  el test fija el instante, el proveedor publica los eventos, se espera
  confirmacion explicita (status-file) de que el piloto proceso libro y flujo,
  y solo entonces se autoriza la evaluacion (decision-gate-file) en ese mismo
  instante. Despues se avanza al siguiente instante.
- Horizontes productivos 5m/15m/60m demostrados por avance controlado del
  reloj, verificando precio posterior, desfase y horizonte efectivo.

No tocan DBs canonicas, ni endpoints privados, ni red publica de mercado.
No se relajan tolerancias: max_data_age_ms se mantiene en 5000.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import research_pilot as rp  # noqa: E402
from research_pilot import (  # noqa: E402
    RunBudget, ceil_ms, build_summary, es_loopback,
)
from microstructure_probe.history_client import UpstreamBudgetExceeded  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture de simbolos y mercado simulado (loopback)
# ---------------------------------------------------------------------------

# Universo pequeño y determinista: cada simbolo cumple un papel explicito.
UNIVERSE = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT"]
SYM_APTA, SYM_LIBRO, SYM_FLUJO, SYM_CORTA, SYM_SIN_FLUJO = UNIVERSE
ROTATION_UNIVERSE = [f"ROT{i}USDT" for i in range(8)]

T0 = 1_735_689_600_000  # alineado a minuto
MINUTE = 60_000
MAX_DATA_AGE_MS = 5_000
HORIZONS = (("5m", 300_000), ("15m", 900_000), ("60m", 3_600_000))


def base_price(symbol: str, universe=UNIVERSE) -> float:
    return 1000.0 + universe.index(symbol) * 10.0


def kline_price(symbol: str, open_time_ms: int,
                universe=UNIVERSE) -> float:
    minute_index = (open_time_ms - T0) // MINUTE
    return base_price(symbol, universe) * (1.0 + 0.0001 * (minute_index % 7))


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Reloj de prueba (fichero) controlado por el test
# ---------------------------------------------------------------------------


class ClockFile:
    """Reloj manual: el test escribe el instante; el piloto solo lo lee."""

    def __init__(self, path: Path, start_ms: int) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.set(start_ms)

    def read(self) -> int:
        return int(self.path.read_text(encoding="utf-8").strip())

    def set(self, ms: int) -> None:
        payload = str(int(ms))
        tmp = self.path.with_name(self.path.name + ".tmp")
        deadline = time.monotonic() + 5.0
        while True:
            try:
                with self._lock:
                    tmp.write_text(payload, encoding="utf-8")
                    os.replace(tmp, self.path)
                return
            except PermissionError:
                # Windows puede rechazar el replace si el piloto esta leyendo:
                # se reintenta con plazo, nunca se inventa el instante.
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.01)


# ---------------------------------------------------------------------------
# Proveedor HTTP loopback (catalogo, tickers, klines)
# ---------------------------------------------------------------------------


def _send_json(handler: BaseHTTPRequestHandler, payload, code: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("X-MBX-USED-WEIGHT-1M", "1")
    handler.end_headers()
    handler.wfile.write(body)


class MarketHttp:
    """Mercado REST simulado y explicito (sin red publica)."""

    def __init__(self, universe, rotation: bool = False) -> None:
        self.universe = list(universe)
        self.rotation = rotation
        self.ticker_calls = 0
        self.klines_calls = 0
        self._lock = threading.Lock()

    def ticker_rows(self):
        with self._lock:
            self.ticker_calls += 1
            call = self.ticker_calls
        n = len(self.universe)
        half = n // 2
        selected = set(range(half)) if call % 2 == 1 else set(range(half, n))
        rows = []
        for idx, symbol in enumerate(self.universe):
            if self.rotation:
                if idx in selected:
                    vol, move = 50_000_000.0, 1.0
                else:
                    vol, move = 2_000_000.0, 0.05
            else:
                vol, move = 50_000_000.0, 1.0 + 0.1 * idx
            rows.append({
                "symbol": symbol,
                "lastPrice": str(base_price(symbol, self.universe)),
                "priceChangePercent": str(move),
                "quoteVolume": str(vol),
                "count": str(1000 + idx),
                "closeTime": T0,
            })
        return rows

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urlsplit(handler.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/fapi/v1/exchangeInfo":
            symbols = [{"symbol": s, "status": "TRADING",
                        "contractType": "PERPETUAL", "quoteAsset": "USDT"}
                       for s in self.universe]
            _send_json(handler, {"symbols": symbols, "timezone": "UTC"})
            return

        if path == "/fapi/v1/ticker/24hr":
            _send_json(handler, self.ticker_rows())
            return

        if path == "/fapi/v1/klines":
            with self._lock:
                self.klines_calls += 1
            symbol = params.get("symbol", [""])[0].upper()
            start = int(params.get("startTime", [0])[0])
            open_time = ceil_ms(start, MINUTE)
            price = kline_price(symbol, open_time, self.universe)
            row = [open_time, f"{price:.8f}", f"{price * 1.001:.8f}",
                   f"{price * 0.999:.8f}", f"{price:.8f}", "100",
                   open_time + MINUTE - 1, "100000", "10", "50", "50000", "0"]
            _send_json(handler, [row])
            return

        _send_json(handler, {"code": -1, "msg": "not found"}, code=404)

    def make_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer._handle(self)

            def log_message(self, fmt, *args):  # silencia ruido
                pass

        return Handler


# ---------------------------------------------------------------------------
# Proveedor WS loopback dirigido por el test (depth20@100ms + aggTrade)
# ---------------------------------------------------------------------------


class WsProvider:
    """Publica EXACTAMENTE los eventos que el test ordena.

    No hay avance por reloj ni temporizadores: ``publish`` envia un burst
    (libro y/o flujo) y devuelve cuantos frames se escribieron. La confirmacion
    de procesamiento la da el status-file del piloto, no el proveedor.
    """

    def __init__(self, universe) -> None:
        self.universe = list(universe)
        self._lock = threading.Lock()
        self._conns = {}
        self._next_id = 0
        self._u = {}
        self._trade_id = {}
        self._loop = None
        self.connections = 0
        self.depth_sent = 0
        self.trades_sent = 0

    def set_loop(self, loop) -> None:
        self._loop = loop

    async def __call__(self, websocket) -> None:
        request = getattr(websocket, "request", None)
        path = getattr(request, "path", "") if request is not None else ""
        streams = [s for s in parse_qs(
            urlsplit(path).query).get("streams", [""])[0].split("/") if s]
        with self._lock:
            self._next_id += 1
            cid = self._next_id
            self._conns[cid] = (websocket, streams)
            self.connections += 1
        try:
            async for _ in websocket:
                pass
        except Exception:
            pass
        finally:
            with self._lock:
                self._conns.pop(cid, None)

    def publish(self, instant_ms: int, depth_symbols=(),
                trade_events=None, timeout: float = 15.0):
        if self._loop is None:
            raise RuntimeError("loop del proveedor WS no inicializado")
        events = {k: list(v) for k, v in (trade_events or {}).items()}
        future = asyncio.run_coroutine_threadsafe(
            self._publish(int(instant_ms), tuple(depth_symbols), events),
            self._loop)
        return future.result(timeout=timeout)

    async def _publish(self, instant_ms: int, depth_symbols, trade_events):
        depth_set = set(depth_symbols)
        sent = {"depth": {}, "trades": {}, "connections": 0}
        with self._lock:
            conns = list(self._conns.values())
        sent["connections"] = len(conns)
        for websocket, streams in conns:
            for stream in streams:
                symbol = stream.split("@")[0].upper()
                kind = stream.split("@", 1)[1] if "@" in stream else ""
                try:
                    if kind.startswith("depth20") and symbol in depth_set:
                        await self._send_depth(websocket, symbol, instant_ms)
                        sent["depth"][symbol] = sent["depth"].get(symbol, 0) + 1
                        self.depth_sent += 1
                    elif kind == "aggTrade" and trade_events.get(symbol):
                        for event_ms in trade_events[symbol]:
                            await self._send_trade(websocket, symbol, event_ms)
                            sent["trades"][symbol] = (
                                sent["trades"].get(symbol, 0) + 1)
                            self.trades_sent += 1
                except Exception:
                    # Una conexion cerrándose no invalida el resto del burst.
                    continue
        return sent

    async def _send_depth(self, websocket, symbol: str,
                          instant_ms: int) -> None:
        base = base_price(symbol, self.universe)
        with self._lock:
            prev = self._u.get(symbol, 1000)
            uid = prev + 1
            self._u[symbol] = uid
        payload = {
            "stream": f"{symbol.lower()}@depth20@100ms",
            "data": {"e": "depthUpdate", "E": instant_ms, "T": instant_ms,
                     "s": symbol, "U": uid, "u": uid, "pu": prev,
                     "b": [[f"{base * 0.999:.8f}", "10.0"],
                           [f"{base * 0.998:.8f}", "5.0"]],
                     "a": [[f"{base * 1.001:.8f}", "10.0"],
                           [f"{base * 1.002:.8f}", "5.0"]]},
        }
        await websocket.send(json.dumps(payload))

    async def _send_trade(self, websocket, symbol: str,
                          event_ms: int) -> None:
        with self._lock:
            self._trade_id[symbol] = self._trade_id.get(symbol, 0) + 1
            tid = self._trade_id[symbol]
        base = base_price(symbol, self.universe)
        payload = {
            "stream": f"{symbol.lower()}@aggTrade",
            "data": {"e": "aggTrade", "E": int(event_ms),
                     "T": int(event_ms), "s": symbol, "a": tid,
                     "p": f"{base:.8f}", "q": "1.0",
                     "m": (tid % 2 == 0), "nq": "1.0"},
        }
        await websocket.send(json.dumps(payload))


def start_ws_server(provider: WsProvider, port: int):
    import websockets

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _start():
        return await websockets.serve(provider, "127.0.0.1", port)

    server = loop.run_until_complete(_start())
    provider.set_loop(loop)
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    def stop() -> None:
        async def _close() -> None:
            server.close()
            await server.wait_closed()

        try:
            asyncio.run_coroutine_threadsafe(_close(), loop).result(timeout=5)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)

    return stop


# ---------------------------------------------------------------------------
# Utilidades de lectura
# ---------------------------------------------------------------------------


def read_rows(path: Path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue  # fila a medio escribir: se ignora en esta lectura
    return rows


def diagnostico(observations):
    """Edades por fuente, cobertura, instante y motivos (evidencia legible)."""
    return [{
        "symbol": o.get("symbol"),
        "observation_id": o.get("observation_id"),
        "decision_ms": o.get("decision_ms"),
        "apto_para_evaluacion": o.get("apto_para_evaluacion"),
        "estado": o.get("estado"),
        "motivos": o.get("motivos") or [],
        "libro": {
            "event_ms": (o.get("libro") or {}).get("event_ms"),
            "received_ms": (o.get("libro") or {}).get("received_ms"),
            "age_event_ms": (o.get("libro") or {}).get("age_event_ms"),
            "age_received_ms": (o.get("libro") or {}).get("age_received_ms"),
        },
        "flujo": {
            "event_ms": (o.get("flujo") or {}).get("event_ms"),
            "received_ms": (o.get("flujo") or {}).get("received_ms"),
            "age_event_ms": (o.get("flujo") or {}).get("age_event_ms"),
            "age_received_ms": (o.get("flujo") or {}).get("age_received_ms"),
            "ventana_completa": (o.get("flujo") or {}).get("ventana_completa"),
        },
        "cobertura": o.get("cobertura"),
    } for o in observations]


def write_diagnostics(out_dir: Path, observations, outcomes) -> Path:
    path = Path(out_dir) / "diagnostico.json"
    payload = {
        "regla": ("edades por fuente, cobertura, instante de evaluacion y "
                  "motivo de clasificacion por observacion"),
        "observaciones": diagnostico(observations),
        "resultados": outcomes,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Ejecucion del piloto productivo (subproceso real) + sincronizacion
# ---------------------------------------------------------------------------


class PilotRun:
    """Ejecuta ``scripts/research_pilot.py`` y sincroniza con su progreso."""

    def __init__(self, tmp: Path, *, universe, duration_s, settle_s,
                 selection_s, max_symbols, rotation=False,
                 cycle_s=60, horizons=HORIZONS) -> None:
        self.tmp = Path(tmp)
        self.universe = list(universe)
        self.out_dir = self.tmp / "out"
        self.obs_path = self.out_dir / "observaciones.jsonl"
        self.status_path = self.tmp / "status.json"
        self.gate_path = self.tmp / "gate.json"
        self.clock = ClockFile(self.tmp / "clock.txt", T0)

        self.http = MarketHttp(self.universe, rotation=rotation)
        self.http_port = find_free_port()
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", self.http_port), self.http.make_handler())
        self.http_thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True)
        self.http_thread.start()

        self.ws = WsProvider(self.universe)
        self.ws_port = find_free_port()
        self._ws_stop = start_ws_server(self.ws, self.ws_port)

        cmd = [
            sys.executable, str(ROOT / "scripts" / "research_pilot.py"),
            "--run-id", "pilot-sync", "--out-dir", str(self.out_dir),
            "--mode", "local",
            "--rest-base", f"http://127.0.0.1:{self.http_port}",
            "--ws-public-base", f"ws://127.0.0.1:{self.ws_port}",
            "--ws-market-base", f"ws://127.0.0.1:{self.ws_port}",
            "--duration-seconds", str(duration_s),
            "--settle-seconds", str(settle_s),
            "--cycle-seconds", str(cycle_s),
            "--selection-seconds", str(selection_s),
            "--decision-delay-seconds", "5",
            "--max-symbols", str(max_symbols),
            "--max-candidates", str(max_symbols),
            "--max-comparators", "0",
            "--min-quote-volume", "1000000",
            "--horizons", ",".join(f"{k}={v}" for k, v in horizons),
            "--price-interval", "1m",
            "--price-tolerance-ms", "90000",
            "--price-delay-ms", "2000",
            "--max-data-age-ms", str(MAX_DATA_AGE_MS),
            "--max-observations", "20000",
            "--max-bytes", str(128 * 1024 * 1024),
            "--max-messages", "5000000",
            "--max-http-attempts", "2000",
            "--max-http-retries", "50",
            "--max-http-weight", "5000",
            "--max-ws-reconnects", "20",
            "--tick-ms", "20",
            "--clock", "manual", "--clock-file", str(self.tmp / "clock.txt"),
            "--status-file", str(self.status_path),
            "--decision-gate-file", str(self.gate_path),
        ]
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        self.stdout = ""
        self.stderr = ""

    # -- estado / esperas explicitas ------------------------------------

    def status(self):
        try:
            return json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _exit_diagnostic(self) -> str:
        return (f"rc={self.proc.poll()} status={json.dumps(self.status())} "
                f"stdout={self.stdout!r} stderr={self.stderr!r}")

    def wait_status(self, predicate, what: str, timeout: float = 30.0):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            state = self.status()
            if state is not None:
                last = state
                if predicate(state):
                    return state
            if self.proc.poll() is not None:
                try:
                    self.stdout, self.stderr = self.proc.communicate(timeout=5)
                except Exception:
                    pass
                raise AssertionError(
                    f"el piloto termino esperando {what}: {self._exit_diagnostic()}")
            time.sleep(0.02)
        raise AssertionError(
            f"timeout {timeout}s esperando {what}; ultimo status="
            f"{json.dumps(last, ensure_ascii=False)}")

    def wait_ready(self, expected_followed: int, timeout: float = 30.0):
        def ready(state):
            followed = state.get("followed") or []
            feeds = state.get("feeds") or {}
            return (state.get("now_ms") == T0
                    and len(followed) == expected_followed
                    and len(feeds) == 2
                    and all(f.get("connected_now") for f in feeds.values()))

        return self.wait_status(ready, "seleccion inicial y feeds conectados",
                                timeout)

    def advance(self, instant_ms: int, timeout: float = 30.0):
        self.clock.set(instant_ms)
        return self.wait_status(
            lambda state: state.get("now_ms") == instant_ms,
            f"reloj simulado en {instant_ms}", timeout)

    def _wait_rows(self, predicate, what: str, timeout: float = 30.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = predicate(read_rows(self.obs_path))
            if found:
                return found
            if self.proc.poll() is not None:
                raise AssertionError(
                    f"el piloto termino esperando {what}: {self._exit_diagnostic()}")
            time.sleep(0.02)
        raise AssertionError(f"timeout {timeout}s esperando {what}")

    def wait_observations(self, decision_ms: int, expected: int,
                          timeout: float = 30.0):
        def pred(rows):
            found = [r for r in rows
                     if r.get("kind") == "observacion"
                     and r.get("decision_ms") == decision_ms]
            return found if len(found) >= expected else None

        found = self._wait_rows(
            pred, f"{expected} observaciones con decision_ms={decision_ms}",
            timeout)
        return found

    def wait_outcome(self, observation_id: str, horizon: str,
                     estado: str = "resuelto", timeout: float = 30.0):
        def pred(rows):
            for row in rows:
                if (row.get("kind") == "resultado"
                        and row.get("observation_id") == observation_id
                        and row.get("horizon") == horizon
                        and row.get("estado") == estado):
                    return row
            return None

        return self._wait_rows(
            pred, f"resultado {estado} {horizon} de {observation_id}", timeout)

    def publish_and_confirm(self, base_state, instant_ms: int,
                            depth_symbols=(), trade_events=None):
        """Publica el burst y espera confirmacion del piloto por fuente."""
        # Nunca publicar sobre feeds a medio conectar (p.ej. tras rotacion).
        self.wait_status(
            lambda st: bool(st.get("feeds")) and all(
                f.get("connected_now") for f in st["feeds"].values()),
            "feeds conectados antes de publicar")
        events = {k: list(v) for k, v in (trade_events or {}).items()}
        sent = self.ws.publish(instant_ms, depth_symbols, events)
        for symbol in depth_symbols:
            if sent["depth"].get(symbol, 0) != 1:
                raise AssertionError(
                    f"libro no publicado para {symbol} en {instant_ms}: {sent}")
        for symbol, series in events.items():
            if series and sent["trades"].get(symbol, 0) != len(series):
                raise AssertionError(
                    f"flujo no publicado para {symbol} en {instant_ms}: {sent}")

        expect_book = {s: base_state["book_events"].get(s, 0) + 1
                       for s in depth_symbols}
        expect_flow = {s: base_state["flow_events"].get(s, 0) + len(series)
                       for s, series in events.items() if series}

        def processed(state):
            for symbol, minimum in expect_book.items():
                if state["book_events"].get(symbol, 0) < minimum:
                    return False
                if (state["book"].get(symbol) or {}).get("event_ms") != instant_ms:
                    return False
            for symbol, minimum in expect_flow.items():
                if state["flow_events"].get(symbol, 0) < minimum:
                    return False
                if (state["flow"].get(symbol) or {}).get("event_ms") != instant_ms:
                    return False
            return True

        return self.wait_status(
            processed, f"libro/flujo procesados en {instant_ms}")

    def step(self, instant_ms: int, *, depth_symbols=(), trade_events=None,
             evaluate: bool = False, expected_obs: int = None):
        """Fija instante -> publica -> confirma -> (autoriza evaluacion)."""
        base = self.advance(instant_ms)
        if depth_symbols or trade_events:
            self.publish_and_confirm(base, instant_ms, depth_symbols,
                                     trade_events)
        if not evaluate:
            return None
        tmp = self.gate_path.with_name(self.gate_path.name + ".tmp")
        tmp.write_text(json.dumps({"decision_ms": instant_ms, "allow": True}),
                       encoding="utf-8")
        os.replace(tmp, self.gate_path)
        return self.wait_observations(instant_ms, expected_obs or 1)

    # -- cierre ---------------------------------------------------------

    def stop(self, timeout: float = 90.0) -> int:
        state = self.status() or {}
        end = int(state.get("settle_end_ms") or 0)
        if end:
            self.clock.set(end + 1000)
        try:
            self.stdout, self.stderr = self.proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.stdout, self.stderr = self.proc.communicate()
            raise AssertionError(
                f"el piloto no termino tras alcanzar el fin: {self._exit_diagnostic()}")
        return self.proc.returncode

    def shutdown(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.stdout, self.stderr = self.proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.communicate()
        finally:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            try:
                self._ws_stop()
            except Exception:
                pass

    def summary(self):
        return json.loads((self.out_dir / "resumen.json").read_text(
            encoding="utf-8"))


# ---------------------------------------------------------------------------
# Pruebas puras
# ---------------------------------------------------------------------------


class TestPureHelpers(unittest.TestCase):
    def test_ceil_ms(self):
        self.assertEqual(ceil_ms(0, 60000), 0)
        self.assertEqual(ceil_ms(1, 60000), 60000)
        self.assertEqual(ceil_ms(60000, 60000), 60000)
        self.assertEqual(ceil_ms(95000, 60000), 120000)
        with self.assertRaises(ValueError):
            ceil_ms(1, 0)

    def test_es_loopback(self):
        self.assertTrue(es_loopback("http://127.0.0.1:8080/x"))
        self.assertTrue(es_loopback("ws://localhost:9/x"))
        self.assertTrue(es_loopback("http://[::1]/x"))
        self.assertFalse(es_loopback("https://fapi.binance.com/x"))
        self.assertFalse(es_loopback("wss://fstream.binance.com/x"))
        self.assertFalse(es_loopback(None))

    def test_build_summary_empty(self):
        summary = build_summary([])
        self.assertEqual(summary["n_observaciones"], 0)
        self.assertEqual(summary["n_aptas_para_evaluacion"], 0)
        self.assertEqual(summary["horizontes"], {})

    def test_run_budget_bloquea_antes_del_transporte(self):
        b = RunBudget(max_attempts=2, max_retries=5, max_weight=10)
        ep_klines = {"endpoint": "http://127.0.0.1/fapi/v1/klines?symbol=X"}
        ep_ticker = {"endpoint": "http://127.0.0.1/fapi/v1/ticker/24hr"}
        b.before_send(ep_klines)   # intento 1, peso 1
        b.before_send(ep_klines)   # intento 2, peso 2
        self.assertEqual(b.attempts, 2)
        self.assertEqual(b.weight, 2)
        # El tercer intento se rechaza ANTES del transporte.
        with self.assertRaises(UpstreamBudgetExceeded):
            b.before_send(ep_ticker)  # intento 3 > max_attempts=2
        self.assertTrue(b.blocked)
        self.assertEqual(b.reason, "presupuesto_intentos_agotado")

    def test_run_budget_peso_agotado(self):
        b = RunBudget(max_attempts=100, max_retries=5, max_weight=40)
        ep_ticker = {"endpoint": "http://127.0.0.1/fapi/v1/ticker/24hr"}
        b.before_send(ep_ticker)  # peso 40, tope alcanzado
        self.assertEqual(b.weight, 40)
        with self.assertRaises(UpstreamBudgetExceeded):
            b.before_send({"endpoint": "http://127.0.0.1/fapi/v1/exchangeInfo"})
        self.assertEqual(b.reason, "presupuesto_peso_agotado")


# ---------------------------------------------------------------------------
# Pruebas independientes de build_observation
# (frescura, ventana, decision no retrotraida, ausencia y dedupe)
# ---------------------------------------------------------------------------


class StaticClock:
    def __init__(self, ms: int) -> None:
        self.ms = int(ms)

    def now_ms(self) -> int:
        return self.ms


def _book_rec(mid: float = 100.0, degraded: bool = False,
              crossed: bool = False):
    return {
        "symbol": "XUSDT", "subscribed": True, "live": True,
        "degraded": degraded, "sequence_gaps": 1 if degraded else 0,
        "invalid_updates": 0, "crossed_tops": 1 if crossed else 0,
        "book": {
            "mid": mid, "spread_bps": 1.0, "crossed": crossed,
            "depth": {"top20": {"bid_notional": 5000.0, "ask_notional": 5000.0,
                                "bid_base": 50.0, "ask_base": 50.0,
                                "bid_levels": 20, "ask_levels": 20}},
            "concentration": {
                "bid": {"coverage_max_dist_bps": 10.0},
                "ask": {"coverage_max_dist_bps": 10.0},
            },
        },
    }


def _flow_rec(warmup_complete: bool = True, trades: int = 5):
    return {
        "symbol": "XUSDT", "subscribed": True, "live": True,
        "horizons": {
            "1m": {"warmup_complete": warmup_complete, "trades": trades,
                   "window_ms": 60000, "buy_notional": 2500.0,
                   "sell_notional": 2500.0, "signed_delta": 0.0,
                   "delta_ratio": 0.0, "base_volume": 5.0,
                   "as_of_ms": 100000},
        },
    }


def _make_pilot(clock_ms: int, out_dir: Path,
                max_bytes: int = 128 * 1024 * 1024) -> rp.ResearchPilot:
    return rp.ResearchPilot(
        rp.PilotConfig(
            run_id="u", out_dir=out_dir, max_bytes=max_bytes,
            max_data_age_ms=MAX_DATA_AGE_MS, duration_seconds=60,
            settle_seconds=5,
        ),
        clock=StaticClock(clock_ms),
    )


class TestBuildObservation(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="obs-test-"))
        self.clock_file = self.tmp / "clock.txt"
        self.pilot = _make_pilot(100_000, self.tmp)

    def _obs(self, now: int, book_recv: int, libro_event: int,
             flow_recv: int, flujo_event: int,
             book_rec, flow_rec):
        p = self.pilot
        p.last_book_recv["XUSDT"] = book_recv
        p.last_book_event["XUSDT"] = libro_event
        p.last_flow_recv["XUSDT"] = flow_recv
        p.last_flow_event["XUSDT"] = flujo_event
        return p.build_observation("XUSDT", now, book_rec, flow_rec)

    def test_libro_obsoleto_flujo_reciente_no_es_apto(self):
        obs = self._obs(
            now=100_000, book_recv=1_000, libro_event=1_000,
            flow_recv=100_000, flujo_event=100_000,
            book_rec=_book_rec(), flow_rec=_flow_rec())
        self.assertFalse(obs["apto_para_evaluacion"])
        self.assertEqual(obs["estado"], "descartada")
        self.assertIn("dato_obsoleto_libro", obs["motivos"])
        self.assertNotIn("dato_obsoleto_flujo", obs["motivos"])
        self.assertEqual(obs["libro"]["age_event_ms"], 99_000)
        self.assertEqual(obs["flujo"]["age_event_ms"], 0)

    def test_flujo_obsoleto_libro_reciente_no_es_apto(self):
        obs = self._obs(
            now=100_000, book_recv=100_000, libro_event=100_000,
            flow_recv=1_000, flujo_event=1_000,
            book_rec=_book_rec(), flow_rec=_flow_rec())
        self.assertFalse(obs["apto_para_evaluacion"])
        self.assertIn("dato_obsoleto_flujo", obs["motivos"])
        self.assertNotIn("dato_obsoleto_libro", obs["motivos"])
        self.assertEqual(obs["flujo"]["age_event_ms"], 99_000)
        self.assertEqual(obs["libro"]["age_event_ms"], 0)

    def test_flujo_ventana_incompleta_no_es_apto(self):
        obs = self._obs(
            now=100_000, book_recv=100_000, libro_event=100_000,
            flow_recv=100_000, flujo_event=100_000,
            book_rec=_book_rec(), flow_rec=_flow_rec(warmup_complete=False))
        self.assertFalse(obs["apto_para_evaluacion"])
        self.assertIn("flujo_ventana_incompleta", obs["motivos"])
        self.assertFalse(obs["flujo"]["ventana_completa"])
        self.assertFalse(obs["cobertura"]["flujo_ventana_completa"])

    def test_decision_ms_no_es_retrotraido(self):
        obs = self._obs(
            now=50_000, book_recv=49_000, libro_event=49_000,
            flow_recv=49_500, flujo_event=49_500,
            book_rec=_book_rec(), flow_rec=_flow_rec())
        self.assertEqual(obs["decision_ms"], 50_000)
        self.assertEqual(obs["disponibilidad"]["max_ms"], 50_000)
        sm = obs["disponibilidad"]["seleccion_ms"]
        if sm is not None:
            self.assertLessEqual(sm, 50_000)
        self.assertLessEqual(obs["disponibilidad"]["libro_ms"], 50_000)
        self.assertLessEqual(obs["disponibilidad"]["flujo_ms"], 50_000)
        self.assertTrue(obs["apto_para_evaluacion"])

    def test_apto_registra_precio_y_horizonte(self):
        obs = self._obs(
            now=100_000, book_recv=100_000, libro_event=100_000,
            flow_recv=100_000, flujo_event=100_000,
            book_rec=_book_rec(), flow_rec=_flow_rec())
        self.assertTrue(obs["apto_para_evaluacion"])
        self.assertEqual(obs["precio_base"], 100.0)
        self.assertEqual(obs["precio_base_fuente"], "libro_mid")
        self.assertEqual(obs["precio_base_disponibilidad_ms"], 100_000)
        self.assertEqual(obs["estado"], "observada")

    def test_ausencia_de_fuente_tiene_motivo_diferenciado(self):
        obs = self._obs(
            now=100_000, book_recv=None, libro_event=None,
            flow_recv=100_000, flujo_event=100_000,
            book_rec=None, flow_rec=_flow_rec())
        self.assertFalse(obs["apto_para_evaluacion"])
        self.assertIn("sin_libro", obs["motivos"])
        self.assertNotIn("sin_flujo", obs["motivos"])

    def test_dedupe_flujo_no_multiplica(self):
        p = self.pilot
        self.assertFalse(p._is_duplicate_trade("XUSDT", 777))
        self.assertTrue(p._is_duplicate_trade("XUSDT", 777))
        self.assertEqual(p.dedupe_flow["XUSDT"], 1)


# ---------------------------------------------------------------------------
# Presupuesto, almacenamiento y CLI
# ---------------------------------------------------------------------------


class TestBudgetYAlmacenamiento(unittest.TestCase):
    def test_storage_ok_incluye_sqlite(self):
        tmp = Path(tempfile.mkdtemp(prefix="storage-test-"))
        pilot = _make_pilot(100_000, tmp, max_bytes=100)
        self.assertFalse(pilot._storage_ok(extra_bytes=1000))

    def test_config_tiene_cotas_efectivas(self):
        cfg = rp.PilotConfig(run_id="x", out_dir=Path(tempfile.mkdtemp()))
        self.assertGreater(cfg.max_http_attempts, 0)
        self.assertGreater(cfg.max_http_retries, 0)
        self.assertGreater(cfg.max_http_weight, 0)
        self.assertGreater(cfg.max_ws_reconnects, 0)


class TestCLISeparacionLocalPublico(unittest.TestCase):
    def test_modo_local_rechaza_endpoint_publico(self):
        with self.assertRaises(ValueError) as ctx:
            rp.config_from_args(rp.build_parser().parse_args([
                "--mode", "local", "--rest-base",
                "https://fapi.binance.com"]))
        self.assertIn("rechaza endpoint publico", str(ctx.exception))

    def test_modo_local_rechaza_ws_publico(self):
        with self.assertRaises(ValueError) as ctx:
            rp.config_from_args(rp.build_parser().parse_args([
                "--mode", "local", "--ws-public-base",
                "wss://fstream.binance.com/public"]))
        self.assertIn("rechaza endpoint publico", str(ctx.exception))

    def test_modo_local_acepta_loopback(self):
        cfg = rp.config_from_args(rp.build_parser().parse_args([
            "--mode", "local", "--rest-base", "http://127.0.0.1:1",
            "--ws-public-base", "ws://127.0.0.1:1",
            "--ws-market-base", "ws://127.0.0.1:1"]))
        self.assertEqual(cfg.mode, "local")

    def test_modo_publico_requiere_activacion(self):
        with self.assertRaises(ValueError) as ctx:
            rp.config_from_args(rp.build_parser().parse_args([
                "--mode", "public", "--rest-base",
                "https://fapi.binance.com"]))
        self.assertIn("--activar-publico", str(ctx.exception))

    def test_sincronizacion_de_prueba_requiere_reloj_manual(self):
        with self.assertRaises(ValueError) as ctx:
            rp.config_from_args(rp.build_parser().parse_args([
                "--clock", "system",
                "--status-file", "status.json",
                "--decision-gate-file", "gate.json"]))
        self.assertIn("requieren --clock manual", str(ctx.exception))

    def test_budget_only_sin_red(self):
        tmp = Path(tempfile.mkdtemp(prefix="budget-only-"))
        cfg = rp.PilotConfig(run_id="b", out_dir=tmp)
        budget = rp.compute_budget(cfg)
        self.assertNotIn("/fapi/v1/time", budget["rest"]["endpoints"])
        self.assertIn("limites_efectivos", budget)
        self.assertGreater(budget["limites_efectivos"]["max_http_attempts"], 0)


# ---------------------------------------------------------------------------
# Cadena completa sincronizada (comando productivo, loopback)
# ---------------------------------------------------------------------------


def _full_window(instant_ms: int, span_ms: int = 62_000):
    return list(range(instant_ms - span_ms, instant_ms + 1, 1_000))


class TestCadenaSincronizada(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pilot-sync-"))
        self.runs = []

    def tearDown(self) -> None:
        for run in self.runs:
            run.shutdown()

    def _start(self, **kwargs) -> PilotRun:
        run = PilotRun(self.tmp, **kwargs)
        self.runs.append(run)
        return run

    def _finish(self, run: PilotRun):
        rc = run.stop()
        self.assertEqual(rc, 0, f"piloto fallo: {run.stderr}")
        obs = read_rows(run.obs_path)
        observations = [r for r in obs if r.get("kind") == "observacion"]
        outcomes = [r for r in obs if r.get("kind") == "resultado"]
        path = write_diagnostics(run.out_dir, observations, outcomes)
        self.assertTrue(path.exists())

        # Resumen y manifiesto regenerables/verificables desde lo persistido.
        summary = run.summary()
        rebuilt = rp.build_summary(obs)
        self.assertEqual(rebuilt["n_observaciones"], summary["n_observaciones"])
        self.assertEqual(rebuilt["n_resultados"], summary["n_resultados"])
        self.assertEqual(rebuilt["motivos"], summary["motivos"])
        manifest = json.loads((run.out_dir / "manifiesto.json").read_text(
            encoding="utf-8"))
        self.assertEqual(manifest["run_id"], "pilot-sync")
        for name in ("observaciones.jsonl", "resumen.json"):
            self.assertIn(name, manifest["files"])
            digest = hashlib.sha256(
                (run.out_dir / name).read_bytes()).hexdigest()
            self.assertEqual(digest, manifest["files"][name]["sha256"])
        return observations, outcomes

    def _evidence(self, run: PilotRun, observations, outcomes=()):
        """Publica la tabla de diagnostico en cada fase (no solo al final)."""
        return write_diagnostics(run.out_dir, observations, list(outcomes))

    # -- 1. frescura por fuente + ventana completa, con barrera ---------

    def test_frescura_por_fuente_y_ventana_en_cadena_productiva(self):
        run = self._start(universe=UNIVERSE, duration_s=180, settle_s=300,
                          selection_s=3600, max_symbols=5)
        run.wait_ready(expected_followed=5)

        e0 = T0 + MINUTE
        full = _full_window(e0)
        short = list(range(e0 - 4_000, e0 + 1, 1_000))

        # E0: libro fresco para los 5; flujo completo salvo D (corta) y E.
        obs0 = run.step(
            e0,
            depth_symbols=UNIVERSE,
            trade_events={SYM_APTA: full, SYM_LIBRO: full,
                          SYM_FLUJO: full, SYM_CORTA: short},
            evaluate=True, expected_obs=5)
        by_sym = {o["symbol"]: o for o in obs0}
        diag0 = json.dumps(diagnostico(obs0), ensure_ascii=False, indent=2)
        self._evidence(run, obs0)

        for symbol in UNIVERSE:
            self.assertEqual(by_sym[symbol]["decision_ms"], e0, diag0)
            self.assertEqual(by_sym[symbol]["disponibilidad"]["libro_ms"], e0,
                             diag0)

        for symbol in (SYM_APTA, SYM_LIBRO, SYM_FLUJO):
            self.assertTrue(by_sym[symbol]["apto_para_evaluacion"], diag0)
            self.assertEqual(by_sym[symbol]["motivos"], [], diag0)
            self.assertEqual(by_sym[symbol]["libro"]["age_event_ms"], 0, diag0)
            self.assertEqual(by_sym[symbol]["flujo"]["age_event_ms"], 0, diag0)
            self.assertTrue(by_sym[symbol]["cobertura"]["flujo_ventana_completa"],
                            diag0)

        self.assertFalse(by_sym[SYM_CORTA]["apto_para_evaluacion"], diag0)
        self.assertIn("flujo_ventana_incompleta",
                      by_sym[SYM_CORTA]["motivos"], diag0)
        self.assertFalse(
            by_sym[SYM_CORTA]["cobertura"]["flujo_ventana_completa"], diag0)

        self.assertFalse(by_sym[SYM_SIN_FLUJO]["apto_para_evaluacion"], diag0)
        self.assertIn("sin_flujo", by_sym[SYM_SIN_FLUJO]["motivos"], diag0)
        self.assertFalse(by_sym[SYM_SIN_FLUJO]["cobertura"]["flujo_presente"],
                         diag0)

        # E1: B sin libro nuevo (libro obsoleto, flujo fresco); C sin flujo
        # nuevo (flujo obsoleto, libro fresco).
        e1 = e0 + MINUTE
        full1 = list(range(e0 + 1_000, e1 + 1, 1_000))
        obs1 = run.step(
            e1,
            depth_symbols=(SYM_APTA, SYM_FLUJO, SYM_CORTA, SYM_SIN_FLUJO),
            trade_events={SYM_APTA: full1, SYM_LIBRO: full1,
                          SYM_CORTA: full1},
            evaluate=True, expected_obs=5)
        by_sym1 = {o["symbol"]: o for o in obs1}
        diag1 = json.dumps(diagnostico(obs1), ensure_ascii=False, indent=2)
        self._evidence(run, obs0 + obs1)

        # Apta: ambas fuentes frescas, ventana completa.
        self.assertTrue(by_sym1[SYM_APTA]["apto_para_evaluacion"], diag1)
        self.assertEqual(by_sym1[SYM_APTA]["libro"]["age_event_ms"], 0, diag1)
        self.assertEqual(by_sym1[SYM_APTA]["flujo"]["age_event_ms"], 0, diag1)
        self.assertEqual(
            by_sym1[SYM_APTA]["cobertura"]["flujo_ventana_completa"], True,
            diag1)

        # Libro obsoleto aunque el flujo este fresco -> rechazo.
        libro = by_sym1[SYM_LIBRO]
        self.assertFalse(libro["apto_para_evaluacion"], diag1)
        self.assertIn("dato_obsoleto_libro", libro["motivos"], diag1)
        self.assertNotIn("dato_obsoleto_flujo", libro["motivos"], diag1)
        self.assertEqual(libro["libro"]["age_event_ms"], MINUTE, diag1)
        self.assertEqual(libro["flujo"]["age_event_ms"], 0, diag1)
        self.assertGreater(libro["libro"]["age_event_ms"], MAX_DATA_AGE_MS)

        # Flujo obsoleto aunque el libro este fresco -> rechazo.
        flujo = by_sym1[SYM_FLUJO]
        self.assertFalse(flujo["apto_para_evaluacion"], diag1)
        self.assertIn("dato_obsoleto_flujo", flujo["motivos"], diag1)
        self.assertNotIn("dato_obsoleto_libro", flujo["motivos"], diag1)
        self.assertEqual(flujo["flujo"]["age_event_ms"], MINUTE, diag1)
        self.assertEqual(flujo["libro"]["age_event_ms"], 0, diag1)
        self.assertGreater(flujo["flujo"]["age_event_ms"], MAX_DATA_AGE_MS)

        # D recupera la ventana al acumular >= 60s de eventos.
        self.assertTrue(by_sym1[SYM_CORTA]["apto_para_evaluacion"], diag1)
        # E sigue sin flujo (motivo diferenciado, no obsolescencia).
        self.assertIn("sin_flujo", by_sym1[SYM_SIN_FLUJO]["motivos"], diag1)
        self.assertNotIn("dato_obsoleto_flujo",
                         by_sym1[SYM_SIN_FLUJO]["motivos"], diag1)

        observations, _ = self._finish(run)
        summary = run.summary()
        self.assertEqual(summary["n_aptas_para_evaluacion"], 3 + 2,
                         json.dumps(summary["motivos"], sort_keys=True))
        self.assertEqual(summary["motivos"].get("dato_obsoleto_libro"), 1)
        self.assertEqual(summary["motivos"].get("dato_obsoleto_flujo"), 1)
        self.assertEqual(summary["motivos"].get("flujo_ventana_incompleta"), 1)
        self.assertEqual(summary["motivos"].get("sin_flujo"), 2)
        self.assertEqual(summary["stop_reason"], "duracion")
        self.assertLessEqual(len(observations), 10)

    # -- 2. horizontes 5m/15m/60m por avance controlado del reloj -------

    def test_horizontes_5m_15m_60m_por_avance_controlado(self):
        run = self._start(universe=UNIVERSE, duration_s=4_000, settle_s=300,
                          selection_s=7_200, max_symbols=5)
        run.wait_ready(expected_followed=5)

        e0 = T0 + MINUTE
        full = _full_window(e0)
        obs0 = run.step(
            e0,
            depth_symbols=UNIVERSE,
            trade_events={SYM_APTA: full, SYM_LIBRO: full,
                          SYM_FLUJO: full, SYM_CORTA: full},
            evaluate=True, expected_obs=5)
        by_sym = {o["symbol"]: o for o in obs0}
        diag0 = json.dumps(diagnostico(obs0), ensure_ascii=False, indent=2)
        self._evidence(run, obs0)
        for symbol in (SYM_APTA, SYM_LIBRO, SYM_FLUJO, SYM_CORTA):
            self.assertTrue(by_sym[symbol]["apto_para_evaluacion"], diag0)
        self.assertFalse(by_sym[SYM_SIN_FLUJO]["apto_para_evaluacion"], diag0)

        obs = by_sym[SYM_APTA]
        obs_id = obs["observation_id"]
        precio_base = float(obs["precio_base"])

        for label, horizon_ms in HORIZONS:
            instant = e0 + horizon_ms + MINUTE
            self.assertLess(instant, run.status()["capture_end_ms"])
            run.step(instant, depth_symbols=(SYM_APTA,),
                     trade_events={SYM_APTA: [instant]})
            outcome = run.wait_outcome(obs_id, label)
            price_ts = e0 + horizon_ms  # alineado a minuto: desfase 0
            expected_price = kline_price(SYM_APTA, price_ts)
            self.assertEqual(outcome["estado"], "resuelto")
            self.assertEqual(outcome["price_ts_ms"], price_ts)
            self.assertEqual(outcome["desfase_ms"], 0)
            self.assertEqual(outcome["horizonte_efectivo_ms"], horizon_ms)
            self.assertEqual(outcome["precio_base_fuente"], "libro_mid")
            self.assertEqual(outcome["precio_posterior_fuente"],
                             "klines_apertura_1m")
            self.assertAlmostEqual(float(outcome["precio"]), expected_price,
                                   places=6)
            self.assertAlmostEqual(
                float(outcome["retorno"]),
                (expected_price - precio_base) / precio_base, places=9)
            self.assertEqual(outcome["neto_estado"], "UNKNOWN")

        _, outcomes = self._finish(run)
        summary = run.summary()
        self.assertEqual(summary["stop_reason"], "duracion")
        for label, _ in HORIZONS:
            self.assertEqual(summary["horizontes"][label]["resueltos"], 4,
                             json.dumps(summary["horizontes"], indent=2))
            self.assertEqual(summary["horizontes"][label]["pendiente"], 0)
        self.assertEqual(len(outcomes), 12)

    # -- 3. rotacion sin perder el resultado del simbolo retirado -------

    def test_rotacion_conserva_resultados_y_acumulados_ws(self):
        run = self._start(universe=ROTATION_UNIVERSE, duration_s=600,
                          settle_s=40, selection_s=60, max_symbols=4,
                          rotation=True)
        run.wait_ready(expected_followed=4)
        first = set(run.status()["followed"])
        self.assertEqual(len(first), 4)

        e0 = T0 + 5_000  # primer instante de decision (delay=5s)
        full = _full_window(e0)
        obs0 = run.step(
            e0,
            depth_symbols=sorted(first),
            trade_events={s: full for s in first},
            evaluate=True, expected_obs=4)
        aptas = [o for o in obs0 if o["apto_para_evaluacion"]]
        self.assertEqual(len(aptas), 4)
        self._evidence(run, obs0)
        removed_obs = aptas[0]
        self.assertIn(removed_obs["symbol"], first)

        # Segunda seleccion: rota el conjunto seguido.
        e1 = T0 + MINUTE
        run.advance(e1)
        state = run.wait_status(
            lambda st: st.get("cycles_run", 0) >= 2,
            "segunda seleccion aplicada")
        second = set(state["followed"])
        self.assertTrue(second.isdisjoint(first))
        run.publish_and_confirm(
            state, e1, depth_symbols=sorted(second),
            trade_events={s: [e1] for s in second})

        # El simbolo retirado conserva su resultado pendiente y se resuelve.
        target = T0 + 5_000 + 300_000 + MINUTE
        run.advance(target)
        outcome = run.wait_outcome(
            removed_obs["observation_id"], "5m")
        self.assertEqual(outcome["estado"], "resuelto")
        self.assertEqual(outcome["symbol"], removed_obs["symbol"])

        observations, outcomes = self._finish(run)
        summary = run.summary()
        salidas = []
        for row in read_rows(run.obs_path):
            if row.get("kind") == "ciclo":
                salidas.extend((row.get("seguimiento") or {}).get("salidas", []))
        self.assertGreaterEqual(len(salidas), 4)
        removed_in_salidas = {s["symbol"] for s in salidas}
        self.assertIn(removed_obs["symbol"], removed_in_salidas)
        self.assertGreaterEqual(summary.get("ws_connections_total", 0), 2)
        self.assertGreaterEqual(summary.get("ws_messages_total", 0), 1)
        self.assertEqual(summary["stop_reason"], "duracion")
        self.assertNotEqual(summary.get("stop_reason"), "presupuesto_agotado")
        # Almacenamiento total incluye SQLite.
        alm = summary.get("almacenamiento", {})
        self.assertIn("storage_bytes_total", alm)
        self.assertIn("sqlite_bytes", alm)
        self.assertGreaterEqual(alm["storage_bytes_total"],
                                alm.get("jsonl_bytes", 0))


if __name__ == "__main__":
    unittest.main()
