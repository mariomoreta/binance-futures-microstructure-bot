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
  el test publica y confirma el procesamiento de libro y flujo con
  event_ms=corte MIENTRAS el reloj esta antes del corte; solo despues alcanza
  el corte. La barrera decision-gate-file es un control explicito de estas
  pruebas; el camino productivo automatico (sin barrera) se demuestra en
  tests/test_recorrido_productivo.py.
- Calentamiento independiente de selection_seconds: ventana de flujo 1m.
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
from typing import Optional
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
from microstructure_probe.history_client import (  # noqa: E402
    HistoryClient, UpstreamBudgetExceeded,
)

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
    """Mercado REST simulado y explicito (sin red publica).

    Respeta el reloj de prueba si se provee: no devuelve aperturas de velas
    posteriores al reloj ni publica OHLC final de una vela cuyo cierre aun
    no ocurrio (close=None para velas abiertas provisionales).
    """

    def __init__(
        self,
        universe,
        rotation: bool = False,
        clock_ms_fn=None,
        moves=None,
        funding_rows_fn=None,
    ) -> None:
        self.universe = list(universe)
        self.rotation = rotation
        self.clock_ms_fn = clock_ms_fn
        self.moves = dict(moves or {})
        # Proveedor de funding programable: recibe (symbol, startTime,
        # endTime, now_ms) y devuelve las filas YA PUBLICADAS por la venue.
        # Sin esta funcion se conserva el comportamiento historico (tres
        # liquidaciones fijas alrededor de T0).
        self.funding_rows_fn = funding_rows_fn
        self.ticker_calls = 0
        self.klines_calls = 0
        self.exchange_info_calls = 0
        self.funding_calls = 0
        # Klines se clasifican por el limite pedido: la consulta de
        # TRAYECTORIA operativa pide la ventana del horizonte (limit>1) y la
        # consulta de precio por horizonte pide una sola vela (limit=1).
        self.klines_calls_trajectory = 0
        self.klines_calls_precio = 0
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
            if symbol in self.moves:
                move = float(self.moves[symbol])
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
            with self._lock:
                self.exchange_info_calls += 1
            symbols = [{"symbol": s, "status": "TRADING",
                        "contractType": "PERPETUAL", "quoteAsset": "USDT"}
                       for s in self.universe]
            _send_json(handler, {"symbols": symbols, "timezone": "UTC"})
            return

        if path == "/fapi/v1/ticker/24hr":
            _send_json(handler, self.ticker_rows())
            return

        if path == "/fapi/v1/fundingRate":
            with self._lock:
                self.funding_calls += 1
            symbol = params.get("symbol", [""])[0].upper()
            start = int(params.get("startTime", ["0"])[0])
            end = int(params.get("endTime", ["0"])[0])
            now_ms = int(self.clock_ms_fn()) if self.clock_ms_fn else None
            if self.funding_rows_fn is not None:
                rows = self.funding_rows_fn(symbol, start, end, now_ms)
                _send_json(handler, rows)
                return
            rows = [
                {"symbol": symbol, "fundingTime": T0 - 16 * 3_600_000,
                 "fundingRate": "0.0001", "markPrice": str(base_price(symbol))},
                {"symbol": symbol, "fundingTime": T0 - 8 * 3_600_000,
                 "fundingRate": "0.0002", "markPrice": str(base_price(symbol))},
                {"symbol": symbol, "fundingTime": T0,
                 "fundingRate": "0.0003", "markPrice": str(base_price(symbol))},
            ]
            _send_json(handler, rows)
            return

        if path == "/fapi/v1/klines":
            with self._lock:
                self.klines_calls += 1
                limit = int(params.get("limit", ["0"])[0] or 0)
                if limit > 1:
                    self.klines_calls_trajectory += 1
                else:
                    self.klines_calls_precio += 1
            symbol = params.get("symbol", [""])[0].upper()
            start = int(params.get("startTime", [0])[0])
            end = int(params.get("endTime", [0])[0])
            now_ms = int(self.clock_ms_fn()) if self.clock_ms_fn else None
            open_time = ceil_ms(start, MINUTE)
            rows = []
            t = open_time
            while t <= end:
                price = kline_price(symbol, t, self.universe)
                close_time = t + MINUTE - 1
                # Una vela cuya apertura ocurre despues del reloj no se conoce.
                if now_ms is not None and t > now_ms:
                    break
                # Si el cierre de la vela aun no ocurrio respecto al reloj,
                # reportamos close=None (vela abierta provisional) para no
                # presentar como definitivo un high/low/close que no se sabe.
                close_price = f"{price:.8f}"
                close_ts = close_time
                if now_ms is not None and close_time > now_ms:
                    close_price = None
                    close_ts = None
                rows.append([t, f"{price:.8f}", f"{price * 1.001:.8f}",
                             f"{price * 0.999:.8f}", close_price, "100",
                             close_ts, "100000", "10", "50", "50000", "0"])
                t += MINUTE
            _send_json(handler, rows)
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
                 cycle_s=60, horizons=HORIZONS, max_http_attempts=2000,
                 funding_calendars_path: Optional[str] = None,
                 funding_source: Optional[str] = None,
                 funding_method: Optional[str] = None,
                 funding_wait_seconds: Optional[float] = None,
                 funding_wait_max_queries: Optional[int] = None,
                 funding_rows_fn=None) -> None:
        self.tmp = Path(tmp)
        self.universe = list(universe)
        self.out_dir = self.tmp / "out"
        self.obs_path = self.out_dir / "observaciones.jsonl"
        self.status_path = self.tmp / "status.json"
        self.gate_path = self.tmp / "gate.json"
        self.stop_path = self.tmp / "stop.txt"
        self.clock = ClockFile(self.tmp / "clock.txt", T0)

        def _clock_ms() -> int:
            try:
                return int(self.clock.read())
            except PermissionError:
                # El piloto esta leyendo el reloj; devolvemos el ultimo conocido.
                return int(self.clock.path.read_text(encoding="utf-8").strip())

        self.http = MarketHttp(
            self.universe, rotation=rotation, clock_ms_fn=_clock_ms,
            funding_rows_fn=funding_rows_fn)
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
            "--max-http-attempts", str(max_http_attempts),
            "--max-http-retries", "50",
            "--max-http-weight", "5000",
            "--max-ws-reconnects", "20",
            "--tick-ms", "20",
            "--clock", "manual", "--clock-file", str(self.tmp / "clock.txt"),
            "--status-file", str(self.status_path),
            "--decision-gate-file", str(self.gate_path),
            "--stop-file", str(self.stop_path),
        ]
        if funding_calendars_path:
            cmd.extend(["--funding-calendars", funding_calendars_path])
        if funding_source:
            cmd.extend(["--funding-source", funding_source])
        if funding_method:
            cmd.extend(["--funding-method", funding_method])
        if funding_wait_seconds is not None:
            cmd.extend(["--funding-wait-seconds", str(funding_wait_seconds)])
        if funding_wait_max_queries is not None:
            cmd.extend(["--funding-wait-max-queries",
                        str(funding_wait_max_queries)])
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        self.stdout = ""
        self.stderr = ""

    # -- estado / esperas explicitas ------------------------------------

    def status(self):
        # os.replace atomico puede coincidir con la lectura: se reintenta un
        # plazo corto para no confundir "aun no escrito" con "no existe".
        deadline = time.monotonic() + 0.25
        while True:
            try:
                return json.loads(self.status_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                if time.monotonic() > deadline:
                    return None
                time.sleep(0.01)

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
        """Publica y confirma ANTES del corte; luego alcanza ``instant_ms``.

        El reloj se coloca un segundo antes del corte, se publican los eventos
        con event_ms=instant_ms y se espera confirmacion de procesamiento. Solo
        despues se alcanza el instante de decision, de modo que la evaluacion
        no puede ocurrir antes de recibir los datos. Cuando ``evaluate`` es
        True se autoriza la barrera de prueba en ese mismo instante.
        """
        base = self.advance(instant_ms - 1_000)
        if depth_symbols or trade_events:
            self.publish_and_confirm(
                base, instant_ms, depth_symbols, trade_events)
        if not evaluate:
            return None
        tmp = self.gate_path.with_name(self.gate_path.name + ".tmp")
        tmp.write_text(json.dumps({"decision_ms": instant_ms, "allow": True}),
                       encoding="utf-8")
        os.replace(tmp, self.gate_path)
        self.advance(instant_ms)
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

    def wait_exit(self, timeout: float = 90.0) -> int:
        """Espera el cierre limpio sin forzar el reloj."""
        try:
            self.stdout, self.stderr = self.proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.stdout, self.stderr = self.proc.communicate()
            raise AssertionError(
                f"el piloto no termino por si solo: {self._exit_diagnostic()}")
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

    def test_reintento_fuera_de_cota_bloquea_antes_del_transporte(self):
        b = RunBudget(max_attempts=10, max_retries=1, max_weight=10)
        b.before_send({"endpoint": "http://127.0.0.1/fapi/v1/klines",
                       "retry": 1})
        with self.assertRaises(UpstreamBudgetExceeded):
            b.before_send({"endpoint": "http://127.0.0.1/fapi/v1/klines",
                           "retry": 2})
        self.assertEqual(b.reason, "presupuesto_reintentos_agotado")
        self.assertEqual(b.attempts, 1)
        self.assertEqual(b.retries, 1)

    def test_reintentos_comparten_cota_global_entre_peticiones(self):
        b = RunBudget(max_attempts=10, max_retries=1, max_weight=10)
        b.before_send({"endpoint": "http://127.0.0.1/fapi/v1/klines",
                       "retry": 0})
        b.before_send({"endpoint": "http://127.0.0.1/fapi/v1/klines",
                       "retry": 1})
        b.before_send({"endpoint": "http://127.0.0.1/fapi/v1/klines",
                       "retry": 0})
        with self.assertRaises(UpstreamBudgetExceeded):
            b.before_send({"endpoint": "http://127.0.0.1/fapi/v1/klines",
                           "retry": 1})
        self.assertEqual(b.reason, "presupuesto_reintentos_agotado")
        self.assertEqual(b.attempts, 3)
        self.assertEqual(b.retries, 1)

    def test_storage_budget_rechaza_antes_de_la_frontera(self):
        budget = rp.RunStorageBudget(10)
        self.assertTrue(budget.reserve("a", 5))
        self.assertTrue(budget.can_fit(5))
        self.assertFalse(budget.can_fit(6))
        self.assertFalse(budget.reserve("b", 6))
        budget.commit("a", 5)
        self.assertEqual(budget.used_bytes, 5)
        self.assertFalse(budget.reserve("b", 6))
        self.assertTrue(budget.reserve("b", 5))
        budget.commit("b", 5)
        self.assertEqual(budget.accounted_bytes, 10)

    def test_intento_bloqueado_no_consume_limite_compartido_funding(self):
        b = RunBudget(max_attempts=0, max_retries=50, max_weight=5_000)
        with self.assertRaises(UpstreamBudgetExceeded):
            b.before_send({
                "endpoint": "http://127.0.0.1/fapi/v1/fundingRate"})
        self.assertEqual(b.status()["funding_rate_attempts_5m"], 0)

    def test_errores_de_conexion_consumen_reintento_global(self):
        class Response:
            def read(self):
                return b"[]"

            @property
            def headers(self):
                return {"x-mbx-used-weight-1m": "1"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        failed = set()

        def opener(req, timeout=None):
            symbol = req.full_url.split("symbol=")[-1]
            if symbol not in failed:
                failed.add(symbol)
                raise ConnectionError("simulated disconnect")
            return Response()

        budget = RunBudget(max_attempts=10, max_retries=2, max_weight=100)
        client = HistoryClient(
            opener=opener,
            attempt_gate=budget,
            sleep=lambda _seconds: None,
        )
        for symbol in ("AAAUSDT", "BBBUSDT"):
            client.get("/fapi/v1/klines", {"symbol": symbol}, weight=1)

        self.assertEqual(budget.attempts, 4)
        self.assertEqual(budget.retries, 2)
        self.assertEqual(
            [entry["result"] for entry in client.upstream_requests],
            ["connection_error", "ok", "connection_error", "ok"],
        )

    def test_ledger_registra_bloqueo_antes_del_transporte(self):
        budget = RunBudget(max_attempts=0, max_retries=50, max_weight=100)
        client = HistoryClient(
            opener=lambda *_args, **_kwargs: self.fail("no debe abrir transporte"),
            attempt_gate=budget,
            sleep=lambda _seconds: None,
        )
        with self.assertRaises(UpstreamBudgetExceeded):
            client.get("/fapi/v1/klines", {"symbol": "AAAUSDT"}, weight=1)

        self.assertEqual(len(client.upstream_requests), 1)
        entry = client.upstream_requests[0]
        self.assertEqual(entry["result"], "blocked_before_send")
        self.assertIsNone(entry["sent_at_ms"])
        self.assertIsNotNone(entry["blocked_at_ms"])
        self.assertIn("presupuesto_intentos_agotado", entry["block_reason"])
        self.assertIsNone(entry.get("_reserved_weight"))


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

    def test_funding_source_exchange_llega_a_la_configuracion(self):
        cfg = rp.config_from_args(rp.build_parser().parse_args([
            "--mode", "local", "--funding-source", "exchange"]))
        self.assertEqual(cfg.funding_source, "exchange")
        self.assertEqual(cfg.to_dict()["funding_source"], "exchange")

    def test_funding_source_exchange_excluye_calendarios_externos(self):
        with self.assertRaises(ValueError) as ctx:
            rp.config_from_args(rp.build_parser().parse_args([
                "--mode", "local", "--funding-source", "exchange",
                "--funding-calendars", "calendarios.json"]))
        self.assertIn("excluyentes", str(ctx.exception))

    def test_budget_only_sin_red(self):
        tmp = Path(tempfile.mkdtemp(prefix="budget-only-"))
        cfg = rp.PilotConfig(run_id="b", out_dir=tmp)
        budget = rp.compute_budget(cfg)
        self.assertNotIn("/fapi/v1/time", budget["rest"]["endpoints"])
        self.assertIn("limites_efectivos", budget)
        self.assertGreater(budget["limites_efectivos"]["max_http_attempts"], 0)

    def test_budget_cuenta_dos_aperturas_por_rotacion(self):
        tmp = Path(tempfile.mkdtemp(prefix="budget-rot-"))
        cfg = rp.PilotConfig(
            run_id="b", out_dir=tmp,
            duration_seconds=3_600, settle_seconds=4_200,
            cycle_seconds=300, selection_seconds=300, max_symbols=20)
        budget = rp.compute_budget(cfg)
        rest = budget["rest"]
        # Estimacion BASE: preparacion (24) + trayectoria operativa (240) +
        # resultados por horizonte (720). Una consulta de trayectoria por
        # observacion apta (no dos: la serie cubre entrada, gestion y salida).
        self.assertEqual(rest["intentos_base"], 984)
        self.assertEqual(rest["peso_base"], 1_452)
        self.assertEqual(rest["intentos_base_mas_reintentos"], 1_034)
        self.assertEqual(rest["peso_base_mas_reintentos_max"], 3_452)
        # Reservas: peticiones repetidas (1 por observacion) y reintentos por
        # fallo (50), contabilizados aparte de la estimacion base.
        reservas = rest["reservas"]
        self.assertEqual(
            reservas["peticiones_repetidas_por_observacion"]["llamadas"], 240)
        self.assertEqual(
            reservas["peticiones_repetidas_por_observacion"][
                "max_por_observacion"], 1)
        self.assertEqual(reservas["reintentos_por_fallo"]["llamadas"], 50)
        self.assertEqual(rest["intentos_base_mas_reservas"], 1_274)
        self.assertEqual(rest["peso_base_mas_reservas_max"], 3_692)
        # La estimacion base NO se presenta como maximo garantizado: el
        # limite efectivo son los topes configurados.
        self.assertEqual(rest["intentos_techo_efectivo"], 2_000)
        self.assertEqual(rest["peso_techo_efectivo"], 5_000)
        self.assertTrue(rest["cabe_en_limites"])
        ws = budget["ws"]
        self.assertEqual(ws["rotaciones_previstas"], 11)
        self.assertEqual(ws["aperturas_iniciales"], 2)
        self.assertEqual(ws["aperturas_por_rotacion_max"], 22)
        self.assertEqual(ws["reaperturas_tras_desconexion_tope"], 20)
        self.assertEqual(ws["sobregiro_reaperturas_por_tick_max"], 2)
        self.assertEqual(ws["aperturas_totales_max"], 46)
        self.assertEqual(ws["streams_pico_por_conexion"], 20)
        self.assertEqual(ws["streams_pico_total"], 40)
        storage = budget["almacenamiento"]
        self.assertEqual(storage["total_bytes_previstos"], 4_094_872)
        self.assertEqual(storage["margen_bytes"], 130_122_856)

    def test_presupuesto_funding_real_no_amplia_cupos(self):
        tmp = Path(tempfile.mkdtemp(prefix="budget-funding-"))
        cfg = rp.PilotConfig(
            run_id="b", out_dir=tmp,
            duration_seconds=3_600, settle_seconds=4_200,
            cycle_seconds=300, selection_seconds=300, max_symbols=20,
            max_candidates=12, max_comparators=8,
            max_http_attempts=2_000, max_http_retries=50,
            max_http_weight=5_000, max_bytes=128 * 1024 * 1024,
            funding_source="exchange")
        budget = rp.compute_budget(cfg)
        rest = budget["rest"]
        self.assertEqual(rest["intentos_base"], 1_224)
        self.assertEqual(rest["peso_base"], 1_692)
        self.assertEqual(rest["intentos_base_mas_reintentos"], 1_274)
        self.assertEqual(rest["peso_base_mas_reintentos_max"], 3_692)
        self.assertEqual(rest["intentos_base_mas_reservas"], 1_754)
        self.assertEqual(rest["peso_base_mas_reservas_max"], 4_172)
        self.assertTrue(rest["cabe_en_limites"])
        self.assertEqual(rest["intentos_techo_efectivo"], 2_000)
        self.assertEqual(rest["peso_techo_efectivo"], 5_000)
        self.assertEqual(
            rest["endpoints"]["/fapi/v1/fundingRate"]["llamadas"], 240)
        storage = budget["almacenamiento"]
        self.assertEqual(storage["total_bytes_previstos"], 7_310_872)
        self.assertEqual(storage["margen_bytes"], 126_906_856)
        self.assertTrue(budget["gate"]["cabe_en_limites"])
        self.assertEqual(
            budget["gate"]["funding_maximo_concentrado_5m"], 90)

    def test_budget_only_falla_cerrado_con_plan_sobre_presupuesto(self):
        tmp = Path(tempfile.mkdtemp(prefix="budget-only-invalid-"))
        code = rp.main([
            "--mode", "local", "--budget-only",
            "--run-id", "invalid", "--out-dir", str(tmp),
        ])
        self.assertEqual(code, 3)
        budget = json.loads(
            (tmp / "presupuesto.json").read_text(encoding="utf-8"))
        self.assertFalse(budget["gate"]["cabe_en_limites"])
        self.assertFalse(
            budget["gate"]["comprobaciones"][
                "intentos_plan_dentro_del_techo"])


class TestFundingRealComparadoresYEconomia(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="funding-real-"))
        self.http = MarketHttp(
            UNIVERSE,
            moves={"EEEUSDT": -0.5},
        )
        self.port = find_free_port()
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", self.port), self.http.make_handler())
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def _pilot(self, **overrides) -> rp.ResearchPilot:
        params = {
            "run_id": "funding-real",
            "out_dir": self.tmp / "out",
            "mode": "local",
            "duration_seconds": 3_600,
            "settle_seconds": 4_200,
            "cycle_seconds": 300,
            "selection_seconds": 300,
            "max_symbols": 5,
            "max_candidates": 2,
            "max_comparators": 3,
            "funding_source": "exchange",
        }
        params.update(overrides)
        return rp.ResearchPilot(
            rp.PilotConfig(**params),
            clock=StaticClock(T0 + 61 * MINUTE),
        )

    def test_cadencia_regular_mixta_falla_cerrada(self):
        rows = [
            {"symbol": "AAAUSDT", "fundingTime": 0,
             "fundingRate": "0.0001", "markPrice": "100"},
            {"symbol": "AAAUSDT", "fundingTime": 4 * 3_600_000,
             "fundingRate": "0.0001", "markPrice": "101"},
            {"symbol": "AAAUSDT", "fundingTime": 12 * 3_600_000,
             "fundingRate": "0.0001", "markPrice": "102"},
            {"symbol": "AAAUSDT", "fundingTime": 20 * 3_600_000,
             "fundingRate": "0.0001", "markPrice": "103"},
        ]
        calendar = rp._funding_calendar_from_rows("AAAUSDT", rows)
        self.assertIsNone(calendar.interval_ms)
        self.assertEqual(
            rp._funding_delta_distribution("AAAUSDT", rows),
            {"14400000": 1, "28800000": 2},
        )

    def test_hash_calendario_compromete_proveniencia_de_settlement(self):
        base = {
            "symbol": "AAAUSDT", "fundingTime": 0,
            "fundingRate": "0.0001", "markPrice": "100",
            "rateType": "Regular",
        }
        first = rp._funding_calendar_from_rows("AAAUSDT", [base])
        changed = rp._funding_calendar_from_rows(
            "AAAUSDT", [{**base, "markPrice": "101"}])
        self.assertNotEqual(first.calendar_hash(), changed.calendar_hash())
        self.assertEqual(first.settlements[0].rate_type, "regular")
        self.assertEqual(first.settlements[0].mark_price, 100.0)

    def test_funding_real_por_simbolo_observado_persiste_trazabilidad(self):
        pilot = self._pilot(out_dir=self.tmp / "funding")
        pilot.rest = HistoryClient(
            base_url=f"http://127.0.0.1:{self.port}",
            attempt_gate=pilot.budget)
        obs = {
            "observation_id": "AAAUSDT|1735689605000",
            "symbol": "AAAUSDT",
            "decision_ms": T0 + 5 * MINUTE,
        }
        now = T0 + 61 * MINUTE
        calendar = pilot._ensure_funding_calendar("AAAUSDT", obs, now)
        self.assertIsNotNone(calendar)
        self.assertEqual(calendar.symbol, "AAAUSDT")
        self.assertEqual(calendar.interval_ms, 8 * 3_600_000)
        self.assertEqual(len(calendar.settlements), 3)
        self.assertIsNotNone(calendar.coverage)
        self.assertEqual(calendar.coverage.status, "unknown")
        self.assertEqual(calendar.coverage.symbol, "AAAUSDT")
        self.assertEqual(
            calendar.coverage.request["params"]["startTime"],
            int(obs["decision_ms"]) - rp.FUNDING_HISTORY_LOOKBACK_MS)
        self.assertEqual(
            calendar.coverage.request["params"]["endTime"], now)
        self.assertEqual(self.http.funding_calls, 1)

        log_rows = read_rows(pilot.funding_log_path)
        self.assertEqual(len(log_rows), 1)
        self.assertEqual(log_rows[0]["estado"], "OK")
        self.assertEqual(
            log_rows[0]["calendar"]["provenance"]["configured_weight"], 1)

        pilot.ended_ms = now
        pilot._write_outputs(0)
        ledger = read_rows(pilot.out_dir / "http_requests.jsonl")
        self.assertEqual(len(ledger), 1)
        self.assertIn("/fapi/v1/fundingRate", ledger[0]["endpoint"])
        self.assertEqual(ledger[0]["params"]["symbol"], "AAAUSDT")
        self.assertEqual(
            ledger[0]["params"]["startTime"],
            int(obs["decision_ms"]) - rp.FUNDING_HISTORY_LOOKBACK_MS)
        self.assertEqual(ledger[0]["params"]["endTime"], now)
        self.assertEqual(ledger[0]["response_item_count"], 3)
        self.assertEqual(ledger[0]["http_status"], 200)
        self.assertEqual(ledger[0]["configured_weight"], 1)
        self.assertEqual(ledger[0]["reserved_weight"], 1)
        self.assertIn(
            "x-mbx-used-weight-1m", ledger[0]["observed_headers"])
        self.assertEqual(len(ledger[0]["response_sha256"]), 64)

        data_paths = [
            pilot.obs_path,
            pilot.operativo.store_path,
            pilot.funding_log_path,
            pilot.out_dir / "http_requests.jsonl",
            *sorted((pilot.out_dir / "funding").glob("*.json")),
            pilot.db_path,
            Path(str(pilot.db_path) + "-wal"),
            Path(str(pilot.db_path) + "-shm"),
        ]
        expected = sum(path.stat().st_size for path in data_paths
                       if path.exists())
        self.assertEqual(pilot.storage_bytes_total(), expected)

        pilot.store.close()
        pilot.operativo.close()
        pilot.funding_log_fh.close()
        pilot.history.close()

    def test_comparador_persiste_movimiento_real_y_misma_regla_de_senal(self):
        pilot = self._pilot(
            out_dir=self.tmp / "comparator",
            max_symbols=5,
            max_candidates=2,
            max_comparators=3,
            funding_source="none",
        )
        pilot.rest = HistoryClient(
            base_url=f"http://127.0.0.1:{self.port}",
            attempt_gate=pilot.budget)
        cycle = pilot.run_cycle()
        rows = read_rows(pilot.obs_path)
        cycle_rows = [row for row in rows if row.get("kind") == "ciclo"]
        self.assertEqual(len(cycle_rows), 1)
        comparator = {
            row["symbol"]: row for row in cycle_rows[0]["comparator"]
        }
        self.assertIn("EEEUSDT", comparator)
        self.assertEqual(comparator["EEEUSDT"]["move_24h"], -0.5)
        self.assertEqual(comparator["EEEUSDT"]["side"], "DOWN")
        self.assertEqual(comparator["EEEUSDT"]["ticker_close_ms"], T0)
        self.assertEqual(
            comparator["EEEUSDT"]["selection_reference_ms"],
            cycle_rows[0]["reference_ms"])
        self.assertEqual(
            pilot.selection_meta["EEEUSDT"]["move_24h_pct"], -0.5)
        self.assertEqual(pilot.selection_meta["EEEUSDT"]["role"], "comparator")

        pilot.store.close()
        pilot.operativo.close()
        pilot.funding_log_fh.close()
        pilot.history.close()

    def test_resumen_economico_no_convierte_unknown_en_cero(self):
        persisted = [
            {"kind": "ciclo", "reference_ms": 100,
             "selected": [{"symbol": "AAAUSDT"}],
             "comparator": [{"symbol": "BBBUSDT"}]},
            {"kind": "observacion", "role": "candidate",
             "apto_para_evaluacion": True,
             "disponibilidad": {"seleccion_ms": 100}},
            {"kind": "observacion", "role": "comparator",
             "apto_para_evaluacion": True,
             "disponibilidad": {"seleccion_ms": 100}},
        ]
        operational = [
            {"role": "candidate", "decision": "ENTRADA_EJECUTADA",
             "direction": "LONG", "exit_executed": True,
             "entry_ms": 10, "exit_ms": 20, "gross_pnl": 2.0,
             "fees": 0.5, "spread_slip": 0.5, "funding": 0.0,
             "net_pnl": 1.0, "neto_estado": "COMPLETO"},
            {"role": "comparator", "decision": "ENTRADA_EJECUTADA",
             "direction": "SHORT", "exit_executed": True,
             "entry_ms": 10, "exit_ms": 20, "gross_pnl": -1.0,
             "fees": 0.5, "spread_slip": 0.5, "funding": 0.0,
             "net_pnl": -2.0, "neto_estado": "COMPLETO"},
            {"role": "candidate", "decision": "ENTRADA_EJECUTADA",
             "direction": "LONG", "exit_executed": True,
             "entry_ms": 30, "exit_ms": 40, "gross_pnl": 4.0,
             "fees": 0.5, "spread_slip": 0.5, "funding": None,
             "net_pnl": 3.0,
             "neto_estado": "CONDICIONADO_SIN_FUNDING_COMPLETO"},
            {"role": "candidate", "decision": "SIN_ENTRADA",
             "direction": None, "exit_executed": False,
             "entry_ms": None, "exit_ms": None, "gross_pnl": 0.0,
             "fees": 0.0, "spread_slip": 0.0, "funding": None,
             "net_pnl": None, "neto_estado": "UNKNOWN"},
        ]
        summary = rp.build_operational_economic_summary(
            persisted, operational)
        result = summary["resultado_usdt"]
        self.assertEqual(result["neto_completo"]["n"], 2)
        self.assertEqual(result["neto_completo"]["suma_usdt"], -1.0)
        self.assertEqual(
            result["neto_conditionado_sin_funding_completo"]["n"], 1)
        self.assertEqual(
            result["neto_conditionado_sin_funding_completo"]["suma_usdt"], 3.0)
        comparison = summary["comparacion_candidate_comparator"]
        self.assertEqual(comparison["estado"], "COMPARABLE")
        self.assertEqual(
            comparison["operaciones_completas_candidate"], 1)
        self.assertEqual(
            comparison["operaciones_completas_comparator"], 1)
        self.assertEqual(
            comparison["neto_por_operacion_candidate"]["media_usdt"], 1.0)
        self.assertEqual(
            comparison["neto_por_operacion_comparator"]["media_usdt"], -2.0)

    def test_resumen_economico_deduplica_operaciones(self):
        persisted = [{"kind": "ciclo", "reference_ms": 100,
                      "selected": [], "comparator": []}]
        operation = {
            "observation_id": "AAAUSDT|1", "role": "candidate",
            "decision": "ENTRADA_EJECUTADA", "direction": "LONG",
            "exit_executed": True, "entry_ms": 10, "exit_ms": 20,
            "gross_pnl": 1.0, "fees": 0.0, "spread_slip": 0.0,
            "funding": 0.0, "net_pnl": 1.0, "neto_estado": "COMPLETO",
        }
        summary = rp.build_operational_economic_summary(
            persisted, [operation, dict(operation)])
        self.assertEqual(summary["resultado_usdt"]["neto_completo"]["n"], 1)
        self.assertEqual(
            summary["diagnosticos"]["duplicados_operativos_descartados"], 1)

    def test_comparacion_no_se_publica_sin_operaciones_completas(self):
        persisted = [{"kind": "ciclo", "reference_ms": 100,
                      "selected": [], "comparator": []}]
        operational = [{
            "role": "candidate", "decision": "ENTRADA_EJECUTADA",
            "direction": "LONG", "exit_executed": True,
            "entry_ms": 10, "exit_ms": 20, "gross_pnl": 1.0,
            "fees": 0.0, "spread_slip": 0.0, "funding": None,
            "net_pnl": 1.0,
            "neto_estado": "CONDICIONADO_SIN_FUNDING_COMPLETO",
        }]
        summary = rp.build_operational_economic_summary(
            persisted, operational)
        comparison = summary["comparacion_candidate_comparator"]
        self.assertEqual(comparison["estado"], "INSUFICIENTE")
        self.assertIn("sin_operaciones_completas_candidate",
                      comparison["motivos"])
        self.assertNotIn("neto_por_operacion_candidate", comparison)


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
            # El libro se publica/confirma un segundo antes del corte; la
            # disponibilidad real es <= decision_ms.
            self.assertEqual(by_sym[symbol]["disponibilidad"]["libro_ms"],
                             e0 - 1_000, diag0)

        for symbol in (SYM_APTA, SYM_LIBRO, SYM_FLUJO):
            self.assertTrue(by_sym[symbol]["apto_para_evaluacion"], diag0)
            self.assertEqual(by_sym[symbol]["motivos"], [], diag0)
            self.assertEqual(by_sym[symbol]["libro"]["age_event_ms"], 0,
                             diag0)
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
        self.assertEqual(by_sym1[SYM_APTA]["libro"]["age_event_ms"], 0,
                         diag1)
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

    # -- 3. politica de pendientes: settle, parada y presupuesto ---------

    def test_fin_normal_maduran_resultados_durante_el_settle(self):
        run = self._start(universe=UNIVERSE, duration_s=180, settle_s=300,
                          selection_s=3_600, max_symbols=5)
        run.wait_ready(expected_followed=5)

        e0 = T0 + MINUTE
        full = _full_window(e0)
        obs = run.step(
            e0,
            depth_symbols=UNIVERSE,
            trade_events={s: full for s in UNIVERSE},
            evaluate=True, expected_obs=5)
        apta = next(o for o in obs if o["symbol"] == SYM_APTA)
        oid = apta["observation_id"]

        # Fin normal de captura: se deja de capturar pero el settle sigue.
        run.advance(T0 + 180_000)
        state = run.wait_status(
            lambda st: st.get("phase") == "settle", "settle iniciado")
        self.assertEqual(state["stop_reason"], "duracion")
        self.assertGreater(state["pending"], 0)
        rows = read_rows(run.obs_path)
        self.assertFalse([r for r in rows
                          if r.get("kind") == "resultado"
                          and r.get("observation_id") == oid], rows)

        # Solo madura lo ya programado; no hay nuevas decisiones.
        target = e0 + 300_000
        run.advance(target + MINUTE + 2_000)
        outcome = run.wait_outcome(oid, "5m")
        self.assertEqual(outcome["estado"], "resuelto")
        self.assertEqual(outcome["desfase_ms"], 0)
        self.assertEqual(outcome["horizonte_efectivo_ms"], 300_000)

        observations, outcomes = self._finish(run)
        summary = run.summary()
        self.assertEqual(summary["stop_reason"], "duracion")
        self.assertEqual(summary["horizontes"]["5m"]["resueltos"], 5)
        self.assertEqual(summary["horizontes"]["5m"]["pendiente"], 0)
        self.assertEqual(len(observations), 5)
        self.assertGreaterEqual(len(outcomes), 5)

    def test_fin_de_settle_conserva_pendientes_con_causa(self):
        run = self._start(universe=UNIVERSE, duration_s=180, settle_s=60,
                          selection_s=3_600, max_symbols=5)
        run.wait_ready(expected_followed=5)

        e0 = T0 + MINUTE
        full = _full_window(e0)
        run.step(
            e0,
            depth_symbols=UNIVERSE,
            trade_events={s: full for s in UNIVERSE},
            evaluate=True, expected_obs=5)

        run.advance(T0 + 180_000)
        run.wait_status(lambda st: st.get("phase") == "settle",
                        "settle iniciado")
        # El settle termina antes del objetivo de 5m (e0+300000).
        run.advance(T0 + 180_000 + 60_000 + 1_000)

        rows = read_rows(run.obs_path)
        pend = [r for r in rows if r.get("kind") == "resultado"]
        self.assertEqual(len(pend), 15, pend)
        self.assertEqual({r["estado"] for r in pend}, {"pendiente"})
        self.assertEqual({r["motivo"] for r in pend},
                         {"ventana_de_settle_agotada"})

        self._finish(run)
        summary = run.summary()
        self.assertEqual(summary["stop_reason"], "duracion")
        self.assertEqual(summary["horizontes"]["5m"]["resueltos"], 0)
        self.assertEqual(summary["horizontes"]["5m"]["pendiente"], 5)

    def test_parada_operador_no_consulta_mas_precios(self):
        run = self._start(universe=UNIVERSE, duration_s=4_000, settle_s=300,
                          selection_s=7_200, max_symbols=5)
        run.wait_ready(expected_followed=5)

        e0 = T0 + MINUTE
        full = _full_window(e0)
        obs = run.step(
            e0,
            depth_symbols=UNIVERSE,
            trade_events={s: full for s in UNIVERSE},
            evaluate=True, expected_obs=5)
        oid = obs[0]["observation_id"]
        consultas = run.http.klines_calls

        # Parada explicita ANTES de que venza ningun objetivo.
        run.stop_path.write_text("stop\n", encoding="utf-8")
        rc = run.wait_exit()
        self.assertEqual(rc, 0, run.stderr)
        # Aunque el objetivo ya no se persigue, no hubo nuevas consultas.
        self.assertEqual(run.http.klines_calls, consultas)

        rows = read_rows(run.obs_path)
        pend = [r for r in rows
                if r.get("kind") == "resultado"
                and r.get("observation_id") == oid]
        self.assertEqual(len(pend), 3, pend)
        self.assertEqual({r["estado"] for r in pend}, {"pendiente"})
        self.assertEqual({r["motivo"] for r in pend}, {"parada_operador"})
        summary = run.summary()
        self.assertEqual(summary["stop_reason"], "parada_operador")
        self.assertEqual(summary["n_observaciones"], 5)

    def test_presupuesto_agotado_bloquea_el_siguiente_envio(self):
        run = self._start(universe=UNIVERSE, duration_s=4_000, settle_s=300,
                          selection_s=7_200, max_symbols=5,
                          max_http_attempts=2)
        run.wait_ready(expected_followed=5)

        e0 = T0 + MINUTE
        full = _full_window(e0)
        run.step(
            e0,
            depth_symbols=UNIVERSE,
            trade_events={s: full for s in UNIVERSE},
            evaluate=True, expected_obs=5)

        # La seleccion consumio 2 intentos; el primer klines se bloquea ANTES
        # del transporte y no llega al proveedor loopback.
        run.advance(e0 + 300_000 + 2_000)
        run.wait_status(
            lambda st: str(st.get("stop_reason") or "").startswith(
                "presupuesto_agotado"), "presupuesto agotado")
        rc = run.wait_exit()
        self.assertEqual(rc, 0, run.stderr)
        self.assertEqual(run.http.klines_calls, 0)

        rows = read_rows(run.obs_path)
        pend = [r for r in rows if r.get("kind") == "resultado"]
        self.assertEqual(len(pend), 15, pend)
        self.assertEqual({r["estado"] for r in pend}, {"pendiente"})
        self.assertEqual({r["motivo"] for r in pend}, {"presupuesto_agotado"})

        summary = run.summary()
        self.assertTrue(summary["stop_reason"].startswith(
            "presupuesto_agotado"))
        presupuesto = summary["presupuesto_http"]
        self.assertEqual(presupuesto["attempts"], 2)
        self.assertTrue(presupuesto["blocked"])
        self.assertEqual(presupuesto["reason"], "presupuesto_intentos_agotado")

    # -- 4. rotacion sin perder el resultado del simbolo retirado -------

    def test_rotacion_conserva_resultados_y_acumulados_ws(self):
        run = self._start(universe=ROTATION_UNIVERSE, duration_s=600,
                          settle_s=40, selection_s=120, max_symbols=4,
                          rotation=True)
        run.wait_ready(expected_followed=4)
        first = set(run.status()["followed"])
        self.assertEqual(len(first), 4)

        # Primer corte de decision DESPUES del calentamiento (60s de flujo 1m).
        # Los eventos se publican/confirman un segundo antes del corte.
        e0 = T0 + 60_000
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

        # Segunda seleccion: rota el conjunto seguido (mitades disjuntas).
        e1 = T0 + 120_000
        run.advance(e1)
        state = run.wait_status(
            lambda st: st.get("cycles_run", 0) >= 2,
            "segunda seleccion aplicada")
        second = set(state["followed"])
        self.assertTrue(second.isdisjoint(first))

        # Sembrar la ventana de flujo del nuevo conjunto tras suscribirlo y
        # publicar el libro; el corte real es e2, un segundo despues de los
        # datos frescos finales.
        seed = list(range(e1 - 60_000, e1 + 1, 1_000))
        run.publish_and_confirm(
            state, e1, depth_symbols=sorted(second),
            trade_events={s: seed for s in second})
        e2 = T0 + 180_000
        obs1 = run.step(
            e2,
            depth_symbols=sorted(second),
            trade_events={s: [e2] for s in second},
            evaluate=True, expected_obs=4)
        self.assertTrue(all(o["decision_ms"] == e2 for o in obs1), obs1)
        self.assertGreaterEqual(
            len([o for o in obs1 if o["apto_para_evaluacion"]]), 1, obs1)
        self._evidence(run, obs0 + obs1)

        # El simbolo retirado conserva su resultado pendiente y se resuelve.
        target = e0 + 300_000 + MINUTE
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
