"""Cadena completa local del piloto prospectivo (research-pilot-v1).

Prueba el comando productivo completo contra proveedores HTTP/WS loopback
(cero Binance) y un reloj manual. Valida:

- Universo > techo de seguimiento, seleccion reproducible, union <= 20.
- Libro y flujo con disponibilidad distinta; decision >= disponibilidad.
- Rotacion con observaciones y resultados pendientes conservados.
- Resolucion de precios posteriores con reloj de prueba (no esperas reales).
- Duplicados sin multiplicacion; hueco/desconexion con motivo.
- Parada por duracion con limpieza; resumen generado desde lo persistido.

No tocan DBs canónicas, ni endpoints privados, ni red pública de mercado.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
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
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import research_pilot  # noqa: E402
from research_pilot import ceil_ms  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture de simbolos y mercado simulado (loopback)
# ---------------------------------------------------------------------------

SYMBOLS = [f"SYM{i:02d}USDT" for i in range(40)]  # 40 elegibles > techo 20
T0 = 1_735_689_600_000  # alineado a minuto (epoch ms)
STEP_MS = 60_000

# Simbolos especiales (deben ser candidatos en el ciclo 2 para probar casos):
# SYM20 = sin flujo agresor -> descarte "sin_flujo"
# SYM21 = libro con huecos de secuencia -> descarte "libro_degradado_por_hueco"
# SYM22 = trades duplicados (mismo id) -> dedupe sin multiplicacion
SPECIAL_NO_FLOW = "SYM20USDT"
SPECIAL_GAP = "SYM21USDT"
SPECIAL_DUP = "SYM22USDT"


def base_price(symbol: str) -> float:
    idx = SYMBOLS.index(symbol)
    return 1000.0 + idx * 10.0


def kline_price(symbol: str, open_time_ms: int) -> float:
    """Precio deterministico de la vela 1m que abre en open_time_ms."""
    minute_index = (open_time_ms - T0) // STEP_MS
    return base_price(symbol) * (1.0 + 0.0001 * (minute_index % 7))


# ---------------------------------------------------------------------------
# Reloj manual compartido (fichero) entre hilos de prueba y piloto
# ---------------------------------------------------------------------------


class ManualClockFile:
    def __init__(self, path: Path, start_ms: int, step_ms: int,
                 real_period_s: float, stop_at_ms: int) -> None:
        self.path = Path(path)
        self.step_ms = step_ms
        self.real_period_s = real_period_s
        self.stop_at_ms = stop_at_ms
        self._lock = threading.Lock()
        self._value = int(start_ms)
        self._stop = False
        self.path.write_text(str(self._value), encoding="utf-8")

    def value(self) -> int:
        with self._lock:
            return self._value

    def now_ms(self) -> int:
        return self.value()

    def set(self, ms: int) -> None:
        with self._lock:
            self._value = int(ms)
        # Escritura directa al fichero compartido (entero pequeno, una sola
        # operacion de escritura; las lecturas reintentan si cruzan con ella).
        self.path.write_text(str(self._value), encoding="utf-8")

    def run(self) -> None:
        while not self._stop and self._value < self.stop_at_ms:
            time.sleep(self.real_period_s)
            self.set(self.value() + self.step_ms)

    def stop(self) -> None:
        self._stop = True


# ---------------------------------------------------------------------------
# Proveedor HTTP loopback (exchangeInfo, ticker/24hr, klines, time)
# ---------------------------------------------------------------------------


class HttpHandler(BaseHTTPRequestHandler):
    ticker_call = 0  # cambia de mercado en la segunda consulta (rotacion)
    log_to_stderr = False

    def _send_json(self, payload: Any, code: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-MBX-USED-WEIGHT-1M", "1")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # silencia ruido
        if self.log_to_stderr:
            super().log_message(fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/fapi/v1/exchangeInfo":
            symbols = []
            for s in SYMBOLS:
                symbols.append({
                    "symbol": s, "status": "TRADING",
                    "contractType": "PERPETUAL", "quoteAsset": "USDT",
                })
            self._send_json({"symbols": symbols, "timezone": "UTC"})
            return

        if path == "/fapi/v1/ticker/24hr":
            HttpHandler.ticker_call += 1
            call = HttpHandler.ticker_call
            rows = []
            for s in SYMBOLS:
                idx = SYMBOLS.index(s)
                # Rotacion de grupos entre llamadas para forzar entradas/salidas
                # del seguimiento en distintos ciclos.
                if call == 1:
                    big, ineligible = set(range(0, 12)), set()
                elif call == 2:
                    big, ineligible = set(range(20, 32)), set(range(0, 12))
                elif call == 3:
                    big, ineligible = set(range(12, 20)), set(range(20, 32))
                else:  # call >= 4
                    big, ineligible = set(range(32, 40)), set(range(12, 20))
                if idx in ineligible:
                    volume, move = 100_000.0, 0.0  # debajo del piso -> no elegible
                elif idx in big:
                    volume, move = 50_000_000.0, 1.5 * (1 if idx % 2 else -1)
                else:
                    volume, move = 20_000_000.0, 0.001  # elegante, sin senal
                rows.append({
                    "symbol": s, "lastPrice": str(base_price(s)),
                    "priceChangePercent": str(move), "quoteVolume": str(volume),
                    "count": str(1000 + idx), "closeTime": T0,
                })
            self._send_json(rows)
            return

        if path == "/fapi/v1/klines":
            symbol = params.get("symbol", [""])[0].upper()
            start = int(params.get("startTime", [0])[0])
            # Vela unica alineada al alza (open_time == start cuando esta alineada).
            open_time = ceil_ms(start, STEP_MS)
            price = kline_price(symbol, open_time)
            row = [
                open_time, f"{price:.8f}", f"{price * 1.001:.8f}",
                f"{price * 0.999:.8f}", f"{price:.8f}", "100",
                open_time + STEP_MS - 1, "100000", "10", "50", "50000", "0",
            ]
            self._send_json([row])
            return

        if path == "/fapi/v1/time":
            self._send_json({"serverTime": T0})
            return

        self._send_json({"code": -1, "msg": "not found"}, code=404)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Proveedor WS loopback (public depth20@100ms + market aggTrade)
# ---------------------------------------------------------------------------


class WsHandler:
    def __init__(self, clock: ManualClockFile) -> None:
        self.clock = clock
        self.connections = 0
        self.messages_sent = 0
        self.errors = 0
        self.last_u: dict = {}
        self.trade_id: dict = {}
        self.depth_seq: dict = {}
        self._lock = threading.Lock()

    async def __call__(self, websocket) -> None:  # websockets 15 handler
        path = getattr(websocket, "request", None)
        path = getattr(path, "path", "") if path is not None else ""
        query = urlsplit(path).query
        streams = parse_qs(query).get("streams", [""])[0].split("/")
        streams = [s for s in streams if s]
        with self._lock:
            self.connections += 1
        stop = asyncio.Event()

        async def sender() -> None:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=0.08)
                except asyncio.TimeoutError:
                    pass
                if stop.is_set():
                    break
                now_ms = self.clock.value() if self.clock is not None else 0
                for stream in streams:
                    symbol = stream.split("@")[0].upper()
                    kind = stream.split("@", 1)[1] if "@" in stream else ""
                    try:
                        if kind.startswith("depth20"):
                            await self._send_depth(websocket, symbol, now_ms)
                        elif kind == "aggTrade":
                            await self._send_trade(websocket, symbol, now_ms)
                        self.messages_sent += 1
                    except Exception:
                        return  # conexion cerrada

        sender_task = asyncio.create_task(sender())
        try:
            # Mantiene la conexion abierta hasta que el cliente se desconecta.
            async for _ in websocket:
                pass
        except Exception:
            pass
        finally:
            stop.set()
            sender_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass

    async def _send_depth(self, websocket, symbol: str, now_ms: int) -> None:
        try:
            import websockets  # noqa: F401
        except Exception:
            pass
        base = base_price(symbol)
        with self._lock:
            last_u = self.last_u.get(symbol, 1000)
            uid = last_u + 1
            prev = last_u
            self.last_u[symbol] = uid
            self.depth_seq[symbol] = self.depth_seq.get(symbol, 0) + 1
            seq = self.depth_seq[symbol]
        # GAP cada actualizacion de SYM21: pu nunca encadena -> degrade estable.
        if symbol == SPECIAL_GAP:
            prev = last_u + 999
        bids = [[str(base * 0.999), "10.0"], [str(base * 0.998), "5.0"]]
        asks = [[str(base * 1.001), "10.0"], [str(base * 1.002), "5.0"]]
        payload = {
            "stream": f"{symbol.lower()}@depth20@100ms",
            "data": {
                "e": "depthUpdate", "E": now_ms, "T": now_ms, "s": symbol,
                "U": uid, "u": uid, "pu": prev, "b": bids, "a": asks,
            },
        }
        try:
            await websocket.send(json.dumps(payload))
        except Exception:
            pass

    async def _send_trade(self, websocket, symbol: str, now_ms: int) -> None:
        with self._lock:
            self.trade_id[symbol] = self.trade_id.get(symbol, 0) + 1
            tid = self.trade_id[symbol]
        base = base_price(symbol)
        maker = (tid % 2 == 0)
        # SYM20: nunca envia trades (flujo ausente).
        if symbol == SPECIAL_NO_FLOW:
            return
        # SYM22: siempre reenvia el mismo id de trade -> duplicados continuos
        # que el piloto debe dedupear (trade_count no se multiplica).
        if symbol == SPECIAL_DUP:
            tid = 777
        payload = {
            "stream": f"{symbol.lower()}@aggTrade",
            "data": {
                "e": "aggTrade", "E": now_ms, "T": now_ms, "s": symbol,
                "a": tid, "p": f"{base:.8f}", "q": "1.0", "m": maker,
                "nq": "1.0",
            },
        }
        try:
            await websocket.send(json.dumps(payload))
        except Exception:
            pass


def start_ws_server_in_thread(clock: ManualClockFile, port: int):
    """Arranca un servidor WS loopback en su propio hilo + bucle asyncio.

    Devuelve (handler, stop_callable). El handler expone contadores y su
    atributo .clock puede reasignarse antes de que lleguen clientes.
    """
    import websockets

    handler = WsHandler(clock)

    async def ws_handler(websocket):
        await handler(websocket)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _start():
        return await websockets.serve(ws_handler, "127.0.0.1", port)

    server = loop.run_until_complete(_start())

    def _run() -> None:
        loop.run_forever()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    def stop() -> None:
        loop.call_soon_threadsafe(server.close)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)

    return handler, stop


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

    def test_compute_budget_shape(self):
        cfg = research_pilot.PilotConfig(
            run_id="t", out_dir=Path(tempfile.mkdtemp()),
            duration_seconds=14400, settle_seconds=4200,
            cycle_seconds=60, selection_seconds=300,
            max_symbols=20, max_candidates=12, max_comparators=8,
        )
        b = research_pilot.compute_budget(cfg)
        self.assertIn("rest", b)
        self.assertIn("ws", b)
        self.assertIn("almacenamiento", b)
        self.assertGreater(b["rest"]["peso_total_con_reintentos"],
                          b["rest"]["peso_total"])
        self.assertEqual(b["ws"]["conexiones_simultaneas"], 2)
        self.assertEqual(b["ws"]["limite_streams_por_conexion"], 1024)

    def test_build_summary_empty(self):
        summary = research_pilot.build_summary([])
        self.assertEqual(summary["n_observaciones"], 0)
        self.assertEqual(summary["horizontes"], {})


# ---------------------------------------------------------------------------
# Prueba de integracion: comando productivo completo
# ---------------------------------------------------------------------------


class TestFullChainLocal(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pilot-test-"))
        self.clock_file = self.tmp / "clock.txt"
        self.http_port = find_free_port()
        self.ws_port = find_free_port()
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", self.http_port), HttpHandler)
        self.http_thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True)
        self.http_thread.start()
        self.ws_handler, self.ws_stop = start_ws_server_in_thread(
            None, self.ws_port)  # .clock se asigna antes de cada corrida

    def _run_pilot(self, clock: ManualClockFile, duration_s: int,
                   settle_s: int) -> tuple:
        """Lanza el CLI como subprocesso y avanza el reloj en paralelo."""
        self.ws_handler.clock = clock
        clock.set(T0)
        # El hilo del reloj avanza el simulado mientras el piloto corre.
        clock_thread = threading.Thread(
            target=clock.run, daemon=True)
        clock_thread.start()

        cmd = [
            sys.executable, str(ROOT / "scripts" / "research_pilot.py"),
            "--run-id", "pilot-local-test",
            "--out-dir", str(self.tmp / "out"),
            "--rest-base", f"http://127.0.0.1:{self.http_port}",
            "--ws-public-base", f"ws://127.0.0.1:{self.ws_port}",
            "--ws-market-base", f"ws://127.0.0.1:{self.ws_port}",
            "--duration-seconds", str(duration_s),
            "--settle-seconds", str(settle_s),
            "--cycle-seconds", "60",
            "--selection-seconds", "60",
            "--decision-delay-seconds", "5",
            "--max-symbols", "20", "--max-candidates", "12",
            "--max-comparators", "8", "--min-quote-volume", "1000000",
            "--horizons", "30s=30000,60s=60000,120s=120000",
            "--price-interval", "1m", "--price-tolerance-ms", "90000",
            "--price-delay-ms", "2000", "--max-data-age-ms", "5000",
            "--max-observations", "20000", "--max-bytes",
            str(128 * 1024 * 1024), "--max-messages", "5000000",
            "--tick-ms", "100",
            "--clock", "manual", "--clock-file", str(self.clock_file),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=str(ROOT))
        clock.stop()
        clock_thread.join(timeout=5)
        self.ws_stop()
        return proc

    def _read_jsonl(self, path: Path):
        rows = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def test_full_chain(self):
        clock = ManualClockFile(
            self.clock_file, T0, step_ms=500, real_period_s=0.05,
            stop_at_ms=T0 + (240 + 30) * 1000 + 60000)
        proc = self._run_pilot(clock, duration_s=240, settle_s=30)

        self.assertEqual(proc.returncode, 0, f"stderr={proc.stderr}")
        out_dir = self.tmp / "out"
        obs_path = out_dir / "observaciones.jsonl"
        summary_path = out_dir / "resumen.json"
        manifest_path = out_dir / "manifiesto.json"
        for p in (obs_path, summary_path, manifest_path):
            self.assertTrue(p.exists(), f"falta {p}")

        obs = self._read_jsonl(obs_path)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        # ---- Estructura basica ----
        cycles = [r for r in obs if r.get("kind") == "ciclo"]
        observations = [r for r in obs if r.get("kind") == "observacion"]
        outcomes = [r for r in obs if r.get("kind") == "resultado"]

        self.assertGreater(len(cycles), 0, "debe haber al menos un ciclo")
        self.assertGreater(len(observations), 0, "debe haber observaciones")

        # Techo de union <= 20 en cada ciclo; candidatos <= 12; comparadores <= 8
        for c in cycles:
            seguidos = c.get("seguimiento", {}).get("seguidos", [])
            self.assertLessEqual(len(seguidos), 20,
                                 f"union supera 20: {len(seguidos)}")
            sel = c.get("selected", [])
            comp = c.get("comparator", [])
            self.assertLessEqual(len(sel), 12)
            self.assertLessEqual(len(comp), 8)

        # Rotacion: al menos un simbolo salio del seguimiento
        salidas = []
        for c in cycles:
            salidas.extend(c.get("seguimiento", {}).get("salidas", []))
        self.assertGreater(len(salidas), 0, "debe haber rotacion (salidas)")

        # ---- Decision >= disponibilidad de todos los datos ----
        for o in observations:
            disp = o.get("disponibilidad", {})
            dec = o["decision_ms"]
            for key in ("libro_ms", "flujo_ms"):
                v = disp.get(key)
                if v is not None:
                    self.assertGreaterEqual(dec, v,
                                            f"decision {dec} < {key} {v}")
            self.assertEqual(disp.get("max_ms"), dec)

        # ---- Estados y motivos de datos incompletos ----
        estados = {o["estado"] for o in observations}
        self.assertIn("observada", estados)
        self.assertIn("descartada", estados)
        motivos = set()
        for o in observations:
            motivos.update(o.get("motivos") or [])
        self.assertIn("sin_flujo", motivos)
        self.assertIn("libro_degradado_por_hueco", motivos)

        # Sin flujo: SYM20 descarta con motivo sin_flujo
        no_flow_obs = [o for o in observations
                       if o["symbol"] == SPECIAL_NO_FLOW]
        self.assertTrue(any("sin_flujo" in (o.get("motivos") or [])
                            for o in no_flow_obs))

        # Hueco: SYM21 descarta por libro degradado
        gap_obs = [o for o in observations if o["symbol"] == SPECIAL_GAP]
        self.assertTrue(any("libro_degradado_por_hueco" in
                            (o.get("motivos") or []) for o in gap_obs))

        # Duplicados sin multiplicacion: SYM22 dedupea y no duplica trades
        dup_obs = [o for o in observations if o["symbol"] == SPECIAL_DUP]
        self.assertTrue(dup_obs, "SYM22 debe ser observado")
        self.assertGreaterEqual(
            int(dup_obs[0].get("integridad", {}).get("dedupe_flujo", 0)), 1,
            "debe haber detectado duplicados de flujo")
        self.assertEqual(int(dup_obs[0]["flujo"]["trade_count"]), 1,
                         "los duplicados no deben multiplicar trades")

        # ---- Resultado: decision >= evento y cobertura ----
        for o in observations:
            libro = o.get("libro", {})
            flujo = o.get("flujo", {})
            if libro.get("event_ms") is not None:
                self.assertGreaterEqual(o["decision_ms"], libro["event_ms"])
            if flujo.get("event_ms") is not None:
                self.assertGreaterEqual(o["decision_ms"], flujo["event_ms"])

        # ---- Resultados por horizonte: al menos uno resuelto y encadenado ----
        resolved = [o for o in outcomes if o.get("estado") == "resuelto"]
        self.assertGreater(len(resolved), 0, "debe resolverse al menos un precio")
        # Verifica encadenamiento de precio para cada resuelto
        obs_by_id = {o["observation_id"]: o for o in observations}
        for r in resolved:
            parent_obs = obs_by_id.get(r["observation_id"])
            self.assertIsNotNone(parent_obs, "resultado sin observacion padre")
            precio_base = parent_obs["precio_base"]
            self.assertIsNotNone(precio_base)
            step = 60000
            price_ts = ceil_ms(r["target_ms"], step)
            expected = kline_price(r["symbol"], price_ts)
            self.assertAlmostEqual(float(r["precio"]), expected, places=6)
            self.assertAlmostEqual(
                float(r["retorno"]), (expected - precio_base) / precio_base,
                places=6)
            self.assertGreaterEqual(r["price_ts_ms"], r["target_ms"])
            self.assertEqual(r["neto_estado"], "UNKNOWN")

        # ---- Resultado pendiente conservado tras rotacion ----
        pendientes = [o for o in outcomes if o.get("estado") == "pendiente"]
        self.assertGreater(len(pendientes), 0,
                           "debe haber resultados pendientes")
        # Ningun pendiente borra su observacion padre
        for r in pendientes:
            self.assertIn(r["observation_id"], obs_by_id)
        # Al menos un pendiente pertenece a un simbolo que salio del seguimiento
        simbolos_salida = {s["symbol"] for s in salidas}
        pend_salida = [r for r in pendientes
                       if obs_by_id[r["observation_id"]]["symbol"]
                       in simbolos_salida]
        self.assertGreater(len(pend_salida), 0,
                           "resultado pendiente de simbolo retirado conservado")

        # ---- Resumen regenerable desde lo persistido ----
        rebuilt = research_pilot.build_summary(obs)
        self.assertEqual(rebuilt["n_observaciones"],
                         summary["n_observaciones"])
        self.assertEqual(rebuilt["n_resultados"], summary["n_resultados"])

        # ---- Manifiesto y hashes ----
        self.assertEqual(manifest["run_id"], "pilot-local-test")
        self.assertIn("observaciones.jsonl", manifest["files"])
        self.assertIn("resumen.json", manifest["files"])
        for name, info in manifest["files"].items():
            digest = hashlib.sha256(
                (out_dir / name).read_bytes()).hexdigest()
            self.assertEqual(digest, info["sha256"])

        # ---- Websocket: dos conexiones (public/market) y reconexion por rotacion
        self.assertGreaterEqual(
            summary.get("ws_connections_total", 0), 4,
            "se esperaba al menos una nueva conexion WS por rotacion del seguido")
        ws_status = summary.get("ws", {})
        self.assertIn("public", ws_status)
        self.assertIn("market", ws_status)

        # ---- Limpieza: el proceso termino por duracion ----
        self.assertEqual(summary.get("stop_reason"), "duracion")

        # Presupuesto calculable sin red
        cfg = research_pilot.PilotConfig(
            run_id="b", out_dir=self.tmp / "budget",
            duration_seconds=14400, settle_seconds=4200,
            cycle_seconds=60, selection_seconds=300,
            max_symbols=20, max_candidates=12, max_comparators=8,
        )
        budget = research_pilot.compute_budget(cfg)
        self.assertGreater(budget["rest"]["peso_total"], 0)
        self.assertEqual(budget["ws"]["conexiones_simultaneas"], 2)


if __name__ == "__main__":
    unittest.main()
