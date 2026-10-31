"""Prueba de integración real: sesión nueva con contexto reciente sobre
servidores HTTP y WS locales (sin Binance pública).

Demuestra el camino productivo, SIN llamar a métodos internos del motor
(nunca _consume_snapshot, _consume_market_closed ni _load_state):

  * Datos de mercado: CLI ``scripts/market_explorer.py`` (HistoryClient +
    puerta de presupuesto LedgerAttemptGate) contra un servidor HTTP de
    klines LOCAL en puerto efímero. Es el mismo camino que el BFF
    (``/api/v1/market-series`` -> ``explorer-bridge.runMarketExplorer``).
  * Servicio de mercado: ``market_stream_service`` (SSE) con transporte
    local contra un servidor WS local en puerto efímero.
  * Sesión: ``EngineeringSessionController`` expuesto por
    ``EngineeringHTTPServer`` (el mismo objeto que proxyea el BFF
    ``/api/v1/engineering-sessions``), consumido por HTTP real
    (POST /sessions, POST /sessions/{id}/control, GET /sessions/{id}).

Aislamiento:
  * Las sesiones y la SQLite de prueba viven en una ``TemporaryDirectory``;
    nunca se toca ``data/engineering-session/sessions`` (canónica).
  * La caché de prueba se inicializa con velas de 4 días atrás (se conserva,
    NO se backfillea; el rango pedido es reciente).
  * El HTTP de klines devuelve solo el rango reciente (últimas ~300 velas
    cerradas) de MINAUSDT y BTCUSDT.
  * Cero llamadas a Binance pública; cero escrituras en DBs canónicas.

El log de solicitudes recibidas por el HTTP local y de frames enviados por
el WS local se publica junto con el test para acreditar:
  - rangos recientes (no backfill de cuatro días);
  - presupuesto aplicado (filas del ledger compartido);
  - snapshot unido al primer cierre nuevo, sin huecos ni duplicados;
  - sesión preparada.

Todas las velas cerradas tienen cierre conocido en el reloj de la prueba
(close_time_ms <= now_ms).
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import websockets

ROOT = Path(r"C:\proyectos\binance-futures-microstructure-bot")
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.engineering_session_service import (  # noqa: E402
    EngineeringHTTPServer,
    EngineeringSessionController,
)
from microstructure_probe.market_cache import MarketCache  # noqa: E402

STEP_MS = 60_000  # 1m
CONTEXT_COUNT = 20
BACKFILL_BARS = 300
N_STREAM = 10
SYMBOLS = ("MINAUSDT", "BTCUSDT")
BASE_PX = {"MINAUSDT": 0.06285, "BTCUSDT": 65000.0}

# Evidencia publicada junto al test (fuera del TemporaryDirectory, sobrevive
# a la corrida).
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "test_session_new_public_market_local"
REQUEST_LOG_PATH = EVIDENCE_DIR / "request-log.jsonl"
RESULT_PATH = EVIDENCE_DIR / "result.json"

REQUEST_LOG: list[dict[str, Any]] = []   # peticiones HTTP recibidas (klines)
WS_FRAMES_LOG: list[dict[str, Any]] = []  # frames enviados por el WS local


def _log(kind: str, **fields: Any) -> None:
    entry = {"t": time.time(), "level": kind, **fields}
    if kind == "http":
        REQUEST_LOG.append(entry)
    else:
        WS_FRAMES_LOG.append(entry)


# ---------------------------------------------------------------------------
# Reloj y generación de velas (todas cerradas, cierre conocido en el reloj).
# ---------------------------------------------------------------------------

def _floor_to_step(ms: int, step: int = STEP_MS) -> int:
    return (ms // step) * step


def _generate_closed_candles(
    symbol: str,
    start_ms: int,
    count: int,
    base_px: float,
) -> list[dict[str, Any]]:
    """Velas cerradas consecutivas de 1m."""
    candles: list[dict[str, Any]] = []
    px = base_px
    for i in range(count):
        ot = start_ms + i * STEP_MS
        ct = ot + STEP_MS - 1
        close = round(px * (1 + 0.0005 * (i % 5 - 2)), 8)
        o = round(px, 8)
        h = round(max(o, close) * 1.0005, 8)
        l = round(min(o, close) * 0.9995, 8)
        candles.append({
            "open_time_ms": ot, "open": o, "high": h, "low": l, "close": close,
            "close_time_ms": ct, "base_volume": 10.0, "closed": True,
        })
        px = close
    return candles


# ---------------------------------------------------------------------------
# 1. Aislamiento: auditoría de la ruta canónica y TemporaryDirectory.
# ---------------------------------------------------------------------------

CANONICAL_SESSIONS = (
    ROOT / "data" / "engineering-session" / "sessions" / "paper-lab-sessions"
)


def _audit_canonical_own_artifacts() -> dict[str, Any]:
    """Inspecciona la ruta canónica e identifica únicamente los artefactos
    propios de este test (hypothesis_id == ENG-MINA-01) dejados por corridas
    previas. Los propios se eliminan (sesión + lock); las sesiones
    desconocidas (unknown) nunca se tocan."""
    found: list[dict[str, Any]] = []
    deleted: list[str] = []
    unknown: list[str] = []
    if CANONICAL_SESSIONS.exists():
        for path in sorted(CANONICAL_SESSIONS.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                unknown.append(path.name)
                continue
            cfg = payload.get("config", {}) if isinstance(payload, dict) else {}
            if isinstance(cfg, dict) and cfg.get("hypothesis_id") == "ENG-MINA-01":
                found.append({
                    "file": path.name,
                    "session_id": payload.get("session_id"),
                    "symbol": cfg.get("symbol"),
                    "status": payload.get("status"),
                    "created_at_ms": payload.get("created_at_ms"),
                })
                lock = CANONICAL_SESSIONS / f".{path.stem}.lock"
                for p in (path, lock):
                    try:
                        p.unlink(missing_ok=True)
                    except OSError:
                        pass
                deleted.append(path.name)
            else:
                unknown.append(path.name)
    return {"found": found, "deleted": deleted, "unknown": unknown}


# ---------------------------------------------------------------------------
# Servidor HTTP local de klines (puerto efímero). Sirve solo el rango reciente.
# ---------------------------------------------------------------------------

def _kline_array(c: dict[str, Any]) -> list[Any]:
    close = c["close"]
    return [
        int(c["open_time_ms"]), str(c["open"]), str(c["high"]), str(c["low"]),
        str(close), "10.0", int(c["close_time_ms"]), "628.5", 100,
        "5.0", "314.25", "0",
    ]


class _KlinesHandler(BaseHTTPRequestHandler):
    KLINE_BY_SYMBOL: dict[str, list[dict[str, Any]]] = {}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path.rstrip("/")
        params = urllib.parse.parse_qs(parsed.query)
        symbol = (params.get("symbol", [""])[0] or "").upper()
        start_raw = params.get("startTime")
        end_raw = params.get("endTime")
        try:
            limit = int(params.get("limit", ["500"])[0])
        except ValueError:
            limit = 500
        start_ms = int(start_raw[0]) if start_raw else None
        end_ms = int(end_raw[0]) if end_raw else None
        entry: dict[str, Any] = {
            "path": path, "symbol": symbol,
            "interval": params.get("interval", ["1m"])[0],
            "start_ms": start_ms, "end_ms": end_ms, "limit": limit,
        }
        try:
            if path not in ("/fapi/v1/klines", "/fapi/v1/markPriceKlines"):
                self._respond(404, {"error": "NOT_FOUND"})
                return
            rows = []
            for c in self.KLINE_BY_SYMBOL.get(symbol, []):
                ot = int(c["open_time_ms"])
                if start_ms is not None and ot < start_ms:
                    continue
                if end_ms is not None and ot > end_ms:
                    continue
                rows.append(_kline_array(c))
            rows.sort(key=lambda r: r[0])
            rows = rows[: max(1, min(limit, 1000))]
            # Binance /fapi/v1/klines devuelve una LISTA de arrays de 12 campos.
            entry["status"] = 200
            entry["returned"] = len(rows)
            self._respond(200, rows)
        except Exception as exc:  # noqa: BLE001
            entry["status"] = 500
            entry["error"] = str(exc)
            self._respond(500, {"error": str(exc)})
        finally:
            _log("http", **entry)

    def _respond(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def _start_http_server() -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _KlinesHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.server_address[1]


# ---------------------------------------------------------------------------
# Servidor WS local (puerto efímero). Reenvía cierres nuevos en bucle mientras
# la conexión esté abierta; el hub del servicio de mercado descarta duplicados
# por marca de agua, por lo que el reenvío es seguro y elimina carreras de
# arranque entre la conducción y el envío de frames.
# ---------------------------------------------------------------------------

def _make_ws_handler(stream_candles: dict[str, list[dict[str, Any]]],
                     first_open_ms: int):
    async def _handler(ws) -> None:
        # Reenvía las velas cerradas de ambos símbolos en ciclo mientras la
        # conexión esté abierta. El transporte puede conectar antes de que
        # exista consumidor (esos frames se descartan como unrouted) y el hub
        # deduplica los repetidos por marca de agua, por lo que el reenvío es
        # seguro y elimina la carrera de arranque con la suscripción.
        end_at = time.monotonic() + 45.0
        while time.monotonic() < end_at:
            for i in range(N_STREAM):
                ot = first_open_ms + i * STEP_MS
                for symbol in SYMBOLS:
                    c = stream_candles[symbol][i]
                    frame = {
                        "stream": f"{symbol.lower()}@kline_1m",
                        "data": {
                            "e": "kline", "E": int(c["close_time_ms"]),
                            "k": {
                                "s": symbol, "i": "1m",
                                "t": int(c["open_time_ms"]),
                                "T": int(c["close_time_ms"]),
                                "o": str(c["open"]), "h": str(c["high"]),
                                "l": str(c["low"]), "c": str(c["close"]),
                                "x": True, "v": str(c["base_volume"]),
                                "q": "628.5", "n": 100,
                            },
                        },
                    }
                    await ws.send(json.dumps(frame))
                    _log("ws", symbol=symbol, open_time_ms=int(c["open_time_ms"]),
                         close_time_ms=int(c["close_time_ms"]),
                         close=str(c["close"]))
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.4)
            except asyncio.TimeoutError:
                continue  # ciclo de reenvío
            except (ConnectionError, OSError,
                    websockets.exceptions.ConnectionClosed):
                return
    return _handler


def _start_ws_server(handler) -> tuple[asyncio.AbstractEventLoop, int, threading.Thread, dict[str, Any]]:
    box: dict[str, Any] = {"server": None, "port": None, "stop": asyncio.Event()}

    async def _main() -> None:
        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            box["server"] = server
            box["port"] = server.sockets[0].getsockname()[1]
            await box["stop"].wait()  # parada ordenada desde _stop_ws

    loop = asyncio.new_event_loop()

    def _run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_main())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    while box["port"] is None:
        time.sleep(0.01)
    return loop, box["port"], thread, box


def _stop_ws(box: dict[str, Any], thread: threading.Thread) -> None:
    # box["stop"].set() es thread-safe y reanuda _main, que cierra el servidor.
    box["stop"].set()
    thread.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Cliente del servicio de sesiones sobre HTTP real (camino productivo BFF).
# ---------------------------------------------------------------------------

def _http_post(port: int, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(port: int, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}{path}", timeout=15,
    ) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_health(port: int, timeout_s: float = 25.0) -> None:
    deadline = time.time() + timeout_s
    last: str | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=2.0,
            ) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = str(exc)
        time.sleep(0.2)
    raise AssertionError(f"servicio en {port} no puso /health a tiempo: {last}")


# ---------------------------------------------------------------------------
# CLI del explorador (camino productivo BFF -> CLI -> HistoryClient).
# ---------------------------------------------------------------------------

def _run_cli_series(
    symbol: str,
    cache_db: Path,
    history_db: Path,
    http_port: int,
    from_ms: int,
    to_ms: int,
    execution_id: str,
    now_ms: int,
) -> dict[str, Any]:
    """Ejecuta scripts/market_explorer.py --action series contra el HTTP local.

    Sin --no-fetch: activación EXPRESA de adquisición con presupuesto
    (LedgerAttemptGate reserva 1 cupo ANTES del transporte).
    """
    cmd = [
        sys.executable, str(ROOT / "scripts" / "market_explorer.py"),
        "--action", "series",
        "--symbol", symbol, "--interval", "1m", "--source", "klines",
        "--from-ms", str(from_ms), "--to-ms", str(to_ms),
        "--pages", "1", "--page-limit", "300",
        "--execution-id", execution_id,
        "--now-ms", str(now_ms),
        "--cache-db", str(cache_db),
        "--history-db", str(history_db),
        "--api-base", f"http://127.0.0.1:{http_port}",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=90, env=env,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"CLI series {symbol} falló (rc={proc.returncode}): "
            f"stdout={proc.stdout[-500:]!r} stderr={proc.stderr[-500:]!r}")
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Prueba
# ---------------------------------------------------------------------------

def main() -> int:
    # ==================================================================
    # 1. Aislamiento: auditar canónico y usar TemporaryDirectory.
    # ==================================================================
    canonical = _audit_canonical_own_artifacts()
    print(
        "Canonical sessions audit: own={d} deleted, unknown={u} untouched".format(
            d=len(canonical["deleted"]), u=len(canonical["unknown"]))
    )
    for item in canonical["deleted"]:
        print(f"  borrado artefacto propio (canonical): {item}")
    # Las sesiones desconocidas (canonical["unknown"]) NO se tocan.

    tmp = tempfile.TemporaryDirectory(prefix="eng-integration-")
    tmp_path = Path(tmp.name)
    sessions_dir = tmp_path / "sessions"
    cache_db = tmp_path / "market-cache" / "market_cache.db"
    history_db = tmp_path / "historical" / "historical.db"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    cache_db.parent.mkdir(parents=True, exist_ok=True)

    # ==================================================================
    # Reloj de la prueba y ventanas: todos los cierres <= now_ms.
    # ==================================================================
    now_ms = _floor_to_step(int(time.time() * 1000))
    four_days_ago_ms = now_ms - 4 * 24 * 60 * 60 * 1000

    # Dejamos N_STREAM velas cerradas entre el final del contexto y el reloj,
    # de modo que TODAS las velas (contexto + stream) cierren <= now_ms.
    last_context_open = now_ms - (N_STREAM + 1) * STEP_MS
    last_context_close = last_context_open + STEP_MS - 1
    context_start_open = last_context_open - (BACKFILL_BARS - 1) * STEP_MS
    first_stream_open = last_context_open + STEP_MS  # == last_context_close + 1
    assert last_context_close <= now_ms
    assert first_stream_open + (N_STREAM - 1) * STEP_MS + STEP_MS - 1 <= now_ms
    assert four_days_ago_ms < context_start_open

    # ==================================================================
    # 2. SQLite inicial: caché de 4 días (se conserva, NO se backfillea).
    # ==================================================================
    cache = MarketCache(cache_db)
    cache.init_db()
    now_for_seed = four_days_ago_ms
    for symbol in SYMBOLS:
        old_candles = _generate_closed_candles(
            symbol, four_days_ago_ms, 60, BASE_PX[symbol])
        rows = [dict(
            open_time=int(c["open_time_ms"]), open=str(c["open"]),
            high=str(c["high"]), low=str(c["low"]), close=str(c["close"]),
            base_volume=str(c["base_volume"]), quote_volume="628.5",
            trade_count=100, close_time=int(c["close_time_ms"]),
            fetched_at=now_for_seed,
        ) for c in old_candles]
        cache.upsert_klines(symbol, "1m", "klines", rows, now_for_seed)
    print(
        f"Caché de prueba inicial: {four_days_ago_ms} (~4 días atrás), "
        f"60 velas x {len(SYMBOLS)} símbolos, conservadas (no backfill)."
    )

    # ==================================================================
    # 3. Servidores HTTP (klines) y WS locales en puertos efímeros.
    # ==================================================================
    recent_candles: dict[str, list[dict[str, Any]]] = {}
    for symbol in SYMBOLS:
        recent_candles[symbol] = _generate_closed_candles(
            symbol, context_start_open, BACKFILL_BARS, BASE_PX[symbol])
    _KlinesHandler.KLINE_BY_SYMBOL = recent_candles
    http_server, http_thread, http_port = _start_http_server()

    stream_candles: dict[str, list[dict[str, Any]]] = {}
    for symbol in SYMBOLS:
        stream_candles[symbol] = _generate_closed_candles(
            symbol, first_stream_open, N_STREAM, BASE_PX[symbol])
    ws_loop, ws_port, ws_thread, ws_box = _start_ws_server(
        _make_ws_handler(stream_candles, first_stream_open))

    # ==================================================================
    # 4. Servicio de mercado (SSE, transporte local contra el WS local).
    # Puerto efímero (--port 0); puerto real leído del pid-file.
    # ==================================================================
    pid_file = tmp_path / "market-stream" / "service.json"
    env = dict(os.environ)
    env["MICROPROBE_MARKET_CACHE_DB"] = str(cache_db)
    env["MICROPROBE_MARKET_STREAM_PID"] = str(pid_file)
    m_proc = subprocess.Popen(
        [
            sys.executable, str(ROOT / "scripts" / "market_stream_service.py"),
            "--host", "127.0.0.1", "--port", "0", "--transport", "local",
            "--base-url", f"ws://127.0.0.1:{ws_port}",
            "--max-seconds", "120",
        ],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    m_port: int | None = None
    deadline = time.time() + 15.0
    while time.time() < deadline:
        try:
            info = json.loads(pid_file.read_text(encoding="utf-8"))
            m_port = int(info["port"])
            break
        except (OSError, ValueError, KeyError):
            if m_proc.poll() is not None:
                break
            time.sleep(0.1)
    if m_port is None:
        raise AssertionError(
            "el servicio de mercado no escribió el pid-file con el puerto: "
            f"stdout={m_proc.stdout.read() if m_proc.stdout else ''!r}")
    _wait_health(m_port)
    print(f"Servicio de mercado listo: 127.0.0.1:{m_port} (WS local :{ws_port})")

    # ==================================================================
    # 5. Backend de sesión expuesto por HTTP real (mismo objeto que el BFF).
    # ==================================================================
    controller = EngineeringSessionController(
        sessions_dir=sessions_dir, cadence_ms=1000.0,
        market_url=f"http://127.0.0.1:{m_port}", market_bars=300,
        live_silence_ms=120000.0,
    )
    eng_server = EngineeringHTTPServer("127.0.0.1", 0, controller)
    eng_thread = threading.Thread(target=eng_server.serve_forever, daemon=True)
    eng_thread.start()
    eng_port = eng_server.server_address[1]
    print(f"Backend de sesión (camino BFF) en 127.0.0.1:{eng_port}")

    session_ids: dict[str, str] = {}
    stream_opens_by_symbol: dict[str, list[int]] = {}

    try:
        # ---- 5a/5b. Adquisición (CLI/HistoryClient) + creación de sesiones ----
        for symbol in SYMBOLS:
            print(f"\n=== {symbol} ===")
            execution_id = (
                f"bff-integration-{symbol}-{int(time.time()*1000)}")

            series = _run_cli_series(
                symbol, cache_db, history_db, http_port,
                context_start_open, last_context_open, execution_id, now_ms,
            )
            assert series.get("ok") is True, series
            data = series["data"]
            observed = data.get("observed") or {}
            fetch_info = data.get("fetch") or {}
            budget = data.get("budget") or {}
            candles = data.get("candles") or []
            print(
                f"  serie: {len(candles)} velas, "
                f"observed={observed.get('start_ms')}..{observed.get('end_ms')}, "
                f"fetch={fetch_info.get('status')} requests={fetch_info.get('requests')}"
            )

            # Rangos recientes, NO backfill de cuatro días (acreditado por el
            # log de peticiones HTTP y por el observado del payload).
            assert int(observed.get("start_ms")) == context_start_open, observed
            assert int(observed.get("end_ms")) == last_context_open, observed
            # El contexto termina exactamente en la frontera diseñada
            # (now_ms - 11 pasos: reciente, nunca el rango de 4 dias atras).
            assert now_ms - int(observed["end_ms"]) == (N_STREAM + 1) * STEP_MS, (
                "el contexto no termina en la frontera esperada")
            http_requests = [e for e in REQUEST_LOG if e.get("symbol") == symbol]
            assert any(
                e.get("start_ms") == context_start_open
                and e.get("end_ms") == last_context_open
                for e in http_requests
            ), f"no hay petición HTTP al rango reciente para {symbol}"
            assert not any(
                e.get("start_ms") == four_days_ago_ms
                for e in REQUEST_LOG
            ), "se pidió el rango de 4 días atrás (backfill prohibido)"

            # Presupuesto aplicado: acreditado con filas del ledger, no con prints.
            assert fetch_info.get("performed") is True, fetch_info
            assert fetch_info.get("status") == "ok", fetch_info
            assert int(fetch_info.get("requests")) >= 1, fetch_info
            assert data.get("coverage", {}).get("state") in ("COVERED", "PARTIAL"), data.get("coverage")

            context_rows = candles[-CONTEXT_COUNT:]
            assert len(context_rows) == CONTEXT_COUNT, len(context_rows)
            for c in context_rows:
                assert c.get("provisional") is False, c
                assert c.get("close_time_ms") is not None, c
                assert int(c["close_time_ms"]) <= now_ms, c

            entry_px = float(context_rows[-1]["close"])
            config = {
                "symbol": symbol, "interval": "1m", "direction": "LONG",
                "notional_usdt": 1000.0,
                "entry_px": entry_px,
                "stop_px": round(entry_px * 0.985, 8),
                "stop_distance_pct": 1.5, "horizon_ms": 30 * 60 * 1000,
                "fee_bps": 5.0, "spread_bps": 1.0, "slippage_bps": 2.0,
                "hypothesis_id": "ENG-MINA-01",
                "hypothesis_version": "v1",
                "rule_version": "ENGINEERING-MINA-1M-v1",
            }
            payload = {
                "config": config, "candles": [], "context": context_rows,
                "transport": "market_stream",
                "from_ms": first_stream_open,
                "to_ms": now_ms,
                "request_id": f"integ-create-{symbol}-{int(time.time()*1000)}",
                "hypothesis_id": "ENG-MINA-01",
                "hypothesis_version": "v1",
                "rule_version": "ENGINEERING-MINA-1M-v1",
            }
            created = _http_post(eng_port, "/sessions", payload)
            assert created.get("session"), created
            session = created["session"]
            session_id = session["session_id"]
            session_ids[symbol] = session_id
            assert created.get("transport") == "market_stream", created

            got = _http_get(eng_port, f"/sessions/{session_id}")
            state = got["session"]
            assert state["status"] in ("sin_iniciar", "evaluando"), state
            assert int(state["clock_ms"]) == last_context_close, (state, last_context_close)
            assert int(state["cursor"]) == 0, state
            assert len(state.get("context_candles") or []) == CONTEXT_COUNT, state
            drive = got.get("drive") or {}
            assert drive.get("runner") == "market_stream", drive
            print(
                f"  sesión preparada: {session_id} clock={state['clock_ms']} "
                f"context={len(state.get('context_candles') or [])} "
                f"runner={drive.get('runner')}"
            )

        # ---- 5c. Iniciar ambas conducciones (control start) ----
        for symbol in SYMBOLS:
            session_id = session_ids[symbol]
            _http_post(eng_port, f"/sessions/{session_id}/control",
                       {"action": "start",
                        "request_id": f"integ-start-{symbol}-{int(time.time()*1000)}"})

        # ---- 5d. Esperar a que el stream una snapshot + cierres nuevos ----
        expected_opens = [
            first_stream_open + i * STEP_MS for i in range(N_STREAM)
        ]
        for symbol in SYMBOLS:
            session_id = session_ids[symbol]
            deadline = time.time() + 30.0
            processed = False
            final_state: dict[str, Any] | None = None
            last_got: dict[str, Any] | None = None
            while time.time() < deadline:
                got = _http_get(eng_port, f"/sessions/{session_id}")
                state = got["session"]
                final_state = state
                last_got = got
                public_opens = sorted(
                    int(c["open_time_ms"]) for c in (state.get("candles") or [])
                    if int(c["open_time_ms"]) > last_context_close
                )
                if public_opens == expected_opens:
                    processed = True
                    break
                time.sleep(0.25)
            assert processed, (
                f"{symbol}: stream no procesado. esperado={expected_opens} "
                f"visto={sorted(int(c['open_time_ms']) for c in ((final_state or {}).get('candles') or []) if int(c['open_time_ms']) > last_context_close)} "
                f"drive={((last_got or {}).get('drive') or {})}"
            )

            state = final_state
            drive = got.get("drive") or {}
            public_opens = sorted(
                int(c["open_time_ms"]) for c in (state.get("candles") or [])
                if int(c["open_time_ms"]) > last_context_close
            )
            # Sin duplicados.
            assert len(public_opens) == len(set(public_opens)), public_opens
            # Contiguidad con el contexto: primera vela de operación abre
            # donde el contexto cerró (+1 ms).
            assert public_opens[0] == last_context_close + 1, public_opens
            for i in range(1, len(public_opens)):
                assert public_opens[i] == public_opens[i - 1] + STEP_MS, public_opens
            # Sin huecos en la puerta de evaluación del feed.
            gate = drive.get("last_gate") or {}
            assert gate.get("grid_gap") is None, (symbol, gate)
            assert int(state["clock_ms"]) == expected_opens[-1], state
            # Todas las velas de operación publicadas: si el cierre ya es
            # conocido (causal, la última vela aún no lo tiene), es <= now_ms.
            for c in state.get("candles") or []:
                if int(c["open_time_ms"]) > last_context_close:
                    ct = c.get("close_time_ms")
                    if ct is not None:
                        assert int(ct) <= now_ms, (symbol, c)
            stream_opens_by_symbol[symbol] = public_opens
            print(
                f"  stream unido al contexto: {len(public_opens)} cierres nuevos, "
                f"sin huecos ni duplicados, clock={state['clock_ms']}, "
                f"gate cause={gate.get('cause')} ok={gate.get('ok')}"
            )

        # ---- 5e. Cerrar ambas sesiones durante la adquisición ----
        # Primero se para la conducción (stop) y luego la sesión (stop_session):
        # stop_session rechaza con DRIVE_ACTIVE si la conducción sigue viva.
        for symbol in SYMBOLS:
            session_id = session_ids[symbol]
            _http_post(eng_port, f"/sessions/{session_id}/control",
                       {"action": "stop",
                        "request_id": f"integ-drive-stop-{symbol}-{int(time.time()*1000)}"})
            _http_post(eng_port, f"/sessions/{session_id}/control",
                       {"action": "stop_session",
                        "request_id": f"integ-stop-{symbol}-{int(time.time()*1000)}"})
            got = _http_get(eng_port, f"/sessions/{session_id}")
            assert got["session"]["status"] == "detenida", got["session"]
            print(f"  sesión {symbol} detenida: status={got['session']['status']}")
    finally:
        # Parada ordenada: sesiones, servicio de mercado, servidores HTTP/WS.
        # Nunca se dejan listeners ni procesos huérfanos.
        try:
            eng_server.shutdown()
        except Exception:
            pass
        try:
            eng_server.server_close()
        except Exception:
            pass
        eng_thread.join(timeout=5.0)
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{m_port}/shutdown",
                data=b"", timeout=5.0,
            )
        except Exception:
            pass
        try:
            m_proc.terminate()
            m_proc.wait(timeout=5.0)
        except Exception:
            try:
                m_proc.kill()
            except Exception:
                pass
        try:
            http_server.shutdown()
        except Exception:
            pass
        try:
            http_server.server_close()
        except Exception:
            pass
        http_thread.join(timeout=5.0)
        _stop_ws(ws_box, ws_thread)

    # ==================================================================
    # 6. Presupuesto aplicado (acreditado desde el ledger compartido).
    # ==================================================================
    ledger_cache = MarketCache(cache_db)
    used_in_window = ledger_cache.requests_in_window(now_ms)
    all_rows = ledger_cache.fetch_ledger(limit=200)
    our_rows = [
        r for r in all_rows
        if r.get("execution_id") and str(r.get("execution_id")).startswith("bff-integration-")
    ]
    assert len(our_rows) >= len(SYMBOLS), our_rows
    for r in our_rows:
        assert int(r.get("requests") or 0) >= 1, r
        assert r.get("status") == "ok", r
    assert used_in_window >= len(our_rows), (used_in_window, our_rows)
    print(
        f"  Presupuesto: {len(our_rows)} intento(s) reservado(s) y enviado(s), "
        f"used_in_window={used_in_window} "
        f"(enforcement=ledger_shared_reserve_before_send)"
    )

    # ==================================================================
    # Resultado publicado.
    # ==================================================================
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    combined_log = REQUEST_LOG + WS_FRAMES_LOG
    REQUEST_LOG_PATH.write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in combined_log),
        encoding="utf-8",
    )
    result = {
        "test": "test_session_new_public_market_local",
        "verdict": "PASS",
        "now_ms": now_ms,
        "symbols": list(SYMBOLS),
        "context_count": CONTEXT_COUNT,
        "stream_candles_per_symbol": N_STREAM,
        "four_days_ago_ms": four_days_ago_ms,
        "canonical_audit": canonical,
        "budget": {
            "used_in_window": used_in_window,
            "ledger_rows_this_run": len(our_rows),
            "enforcement": "ledger_shared_reserve_before_send",
        },
        "requests_logged_http": len([e for e in combined_log if e.get("level") == "http"]),
        "ws_frames_sent": len([e for e in combined_log if e.get("level") == "ws"]),
        "results": [
            {
                "symbol": s,
                "session_id": session_ids[s],
                "stream_opens": stream_opens_by_symbol[s],
            }
            for s in SYMBOLS
        ],
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== INTEGRACIÓN SUPERADA ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    tmp.cleanup()
    return 0


def test_session_new_public_market_prepares_without_backfill() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
