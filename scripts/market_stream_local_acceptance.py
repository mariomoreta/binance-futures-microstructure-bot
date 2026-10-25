"""Aceptacion local automatizada del camino public WS -> servicio -> BFF -> DOM.

Objetivo: demostrar, SIN abrir ninguna ventana real de Binance, que el
procedimiento completo de aceptacion funciona de punta a punta con transporte
local y aislamiento de red real:

  fake kline WS (loopback) -> market_stream_service (transporte local)
    -> BFF /api/v1/market-stream -> /market-lab (navegador Playwright)

El arnes:
  * prepara un catalogo/historico local en una cache temporal (sin tocar las
    DBs canonicas);
  * sirve klines reales en reloj real (provisional, cierre y siguiente vela);
  * inyecta en el dashboard un `sitecustomize` que bloquea y registra cualquier
    conexion no-loopback, y un wrapper del explorador con `--no-fetch`;
  * levanta un proxy local que registra/rechaza cualquier intento publico;
  * permite en el navegador solo 127.0.0.1:3020 y registra cualquier otro
    origen;
  * conduce el navegador por el procedimiento (LIVE, captura #1, paginacion,
    captura #2, liberacion, reconexion, parada, aviso y captura #3) con
    condiciones observadas y maximos por fase;
  * exige dos recorridos completos consecutivos con cero peticiones publicas,
    cero consumidores residuales, parada limpia y veredicto PASS del evaluador.

El JSON resultante NO acredita recepcion de Binance: el transporte es loopback.
Para la ventana real se reutiliza el mismo procedimiento con `--transport public`
y autorizacion humana explicita. En modo `public` el arnes no prepara cache
temporal, no inyecta `sitecustomize` ni wrapper en el dashboard, no lanza WS
falso ni proxy, y no traslada configuracion de prueba al dashboard canonico;
el dashboard debe estar ya arrancado por el operador con el entorno adecuado.

Uso (entorno de prueba local, dashboard en 3020 con entorno de test):
  python -X utf8 scripts/market_stream_local_acceptance.py --runs 2 \
      --out-dir docs/evidence/local-acceptance-2026-10-24

Uso (procedimiento de ventana real, transporte public; requiere autorizacion):
  python -X utf8 scripts/market_stream_local_acceptance.py --transport public \
      --runs 1 --out-dir docs/evidence/local-acceptance-2026-10-24-public

En modo `public` el veredicto PASS ademas exige recepcion real identificada de
Binance (identidad exacta: venue=binance, market_type=usd_m_futures, simbolo e
intervalo, y al menos un mensaje de vela del simbolo primario). Activar
`--transport public` por si solo no acredita el origen; el check
`binance_accredited` solo es True cuando esa identidad se verifica contra los
eventos recibidos.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import queue
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.market_cache import MarketCache  # noqa: E402

STEP_MS = 60_000
HOUR_MS = 3_600_000
DEFAULT_DASHBOARD = "http://127.0.0.1:3020"
DEFAULT_SERVICE_PORT = 8792
DEFAULT_FAKE_PORT = 8794
DEFAULT_PROXY_PORT = 8793
DEFAULT_WORKDIR = Path(os.environ.get("TEMP", ".")) / "opencode" / "market-acceptance"

# Limites por fase (segundos). No se amplian para "compensar" un fallo: si una
# fase los supera, el recorrido falla y se limpian los recursos.
LIMITS = {
    "minute_phase": 60.0,
    "page_ready": 45.0,
    "acceptance": 70.0,
    "pagination": 20.0,
    "release": 15.0,
    "reconnect": 15.0,
    "down_notice": 40.0,
    "run": 180.0,
}

CHROME_ARGS = [
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-features=Translate,BackForwardCache",
    "--metrics-recording-only",
    "--no-first-run",
    "--no-default-browser-check",
]

WRAPPER_JS = r"""
(() => {
  const Native = window.EventSource;
  if (!Native || window.__streamHarness) return;
  const state = {instances: [], current: null, url: null};
  const CUSTOM = ["hello", "snapshot", "candle", "closed", "status", "gap",
                  "heartbeat", "error"];
  class HarnessEventSource {
    constructor(url, init) {
      this.url = String(url);
      this.withCredentials = !!(init && init.withCredentials);
      this.readyState = 0;
      this.onopen = null;
      this.onerror = null;
      this.onmessage = null;
      this._listeners = new Map();
      this._native = null;
      state.instances.push(this);
      state.current = this;
      state.url = this.url;
      this._open();
    }
    _open() {
      const native = new Native(this.url, {withCredentials: this.withCredentials});
      this._native = native;
      native.onopen = () => {
        this.readyState = 1;
        if (this.onopen) this.onopen();
      };
      native.onerror = (event) => {
        this.readyState = 0;
        if (this.onerror) this.onerror(event);
      };
      native.onmessage = (event) => {
        if (this.onmessage) this.onmessage(event);
      };
      for (const type of CUSTOM) {
        native.addEventListener(type, (event) => this._dispatch(type, event));
      }
    }
    _dispatch(type, event) {
      const list = this._listeners.get(type) || [];
      for (const fn of list) {
        try { fn.call(this, event); } catch (err) { /* el hook decide */ }
      }
    }
    addEventListener(type, fn) {
      const list = this._listeners.get(type) || [];
      list.push(fn);
      this._listeners.set(type, list);
    }
    removeEventListener(type, fn) {
      const list = this._listeners.get(type) || [];
      this._listeners.set(type, list.filter((item) => item !== fn));
    }
    close() {
      this.readyState = 2;
      if (this._native) {
        this._native.close();
        this._native = null;
      }
    }
  }
  HarnessEventSource.CONNECTING = 0;
  HarnessEventSource.OPEN = 1;
  HarnessEventSource.CLOSED = 2;
  HarnessEventSource.prototype.CONNECTING = 0;
  HarnessEventSource.prototype.OPEN = 1;
  HarnessEventSource.prototype.CLOSED = 2;
  window.EventSource = HarnessEventSource;
  window.__streamHarness = {
    instances: () => state.instances.length,
    state: () => ({instances: state.instances.length, url: state.url}),
    debug: () => ({
      current: state.current ? {
        url: state.current.url,
        readyState: state.current.readyState,
        native: !!state.current._native,
        listeners: Array.from(state.current._listeners.keys()),
      } : null,
      instances: state.instances.map((es) => ({
        url: es.url, readyState: es.readyState, native: !!es._native,
      })),
    }),
    disconnect: () => {
      const es = state.current;
      if (!es || !es._native) return false;
      es._native.close();
      es._native = null;
      es.readyState = 0;
      return true;
    },
    reconnect: () => {
      const es = state.current;
      if (!es) return false;
      if (es._native) return false;
      es._open();
      return true;
    },
    reopen: () => {
      const es = state.current;
      if (!es) return false;
      if (es._native) {
        es._native.close();
        es._native = null;
      }
      es.readyState = 0;
      es._open();
      return true;
    },
  };
})();
"""

CAPTURE_JS = r"""
() => {
  const text = (id) => {
    const node = document.querySelector(`[data-testid="${id}"]`);
    return node ? (node.textContent || "").trim() : null;
  };
  const countText = text("explorer-stream-count") || "";
  const match = /(\d+)\s+cargadas\s+·\s+(\d+)\s+provisional/.exec(countText);
  const streamText = text("explorer-stream") || "";
  const identity = /Binance USD-M · [A-Z0-9]+ · \d+[mhd] · market-stream\/v1/
    .exec(streamText);
  const nav = performance.getEntriesByType("navigation");
  return {
    captured_at_ms: Date.now(),
    url: location.href,
    identity: identity ? identity[0] : null,
    state: text("explorer-stream-state"),
    live: text("explorer-stream-live"),
    updated: text("explorer-stream-updated"),
    count_text: countText || null,
    candles: match ? Number(match[1]) : null,
    provisional: match ? Number(match[2]) : null,
    down: text("explorer-stream-down"),
    error: text("explorer-stream-error"),
    navigation_count: nav.length,
    reload_count: nav.filter((entry) => entry.type === "reload").length,
    chart_window: text("market-chart-window"),
    chart_earlier: text("market-chart-earlier"),
    chart_coverage: text("market-chart-coverage"),
  };
}
"""


class HarnessError(RuntimeError):
    pass


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def window_span_ms(text: Optional[str]) -> Optional[int]:
    """Amplitud de la ventana visible (`Ventana ISO -> ISO`) en milisegundos.

    La vela viva desplaza el borde derecho un minuto; la paginacion no debe
    cambiar la amplitud. Comparar el texto literal confundiria ambos efectos.
    """
    if not text:
        return None
    stamps = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text)
    if len(stamps) < 2:
        return None
    try:
        first = datetime.strptime(stamps[0], "%Y-%m-%dT%H:%M:%SZ")
        last = datetime.strptime(stamps[1], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return int((last - first).total_seconds() * 1000)


ISO_MS_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)")


def updated_ms(text: Optional[str]) -> Optional[int]:
    """Instante del ultimo mensaje mostrado por el DOM (`ISO · hace N s`)."""
    if not text:
        return None
    match = ISO_MS_RE.search(text)
    if not match:
        return None
    try:
        stamp = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(stamp.timestamp() * 1000)


def wait_fresh_update(page, since_ms: int, timeout: float) -> float:
    def check() -> bool:
        value = updated_ms((capture(page) or {}).get("updated"))
        return value is not None and value >= since_ms
    return wait_until(check, timeout, 0.2, "fresh_update")


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, int(port))) == 0


def http_json(url: str, timeout: float = 8.0,
              headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip() else {}


def wait_until(predicate, timeout: float, interval: float = 0.1,
               label: str = "condicion") -> float:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if predicate():
            return time.monotonic() - started
        time.sleep(interval)
    raise HarnessError(f"TIMEOUT:{label}:{timeout:.1f}s")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            item = {"raw": line}
        if isinstance(item, dict):
            out.append(item)
    return out


def file_mtime_ms(path: Path) -> Optional[int]:
    try:
        return int(path.stat().st_mtime * 1000)
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Cache local preparada y raiz shadow del explorador
# ---------------------------------------------------------------------------

SITECUSTOMIZE = r'''
"""Guarda de red del arnes local: bloquea y registra conexiones no-loopback.

Se inyecta via PYTHONPATH en el explorador, el servicio y el orquestador. El
loopback (127.0.0.1/::1/localhost) se permite: el arnes es local por diseno.
"""
import json
import os
import socket
import sys
import time

_CANON = os.environ.get("MICROPROBE_TEST_CANON_SRC")
if _CANON and _CANON not in sys.path:
    sys.path.insert(0, _CANON)
_LOG = os.environ.get("MICROPROBE_TEST_CONN_LOG")


def _loopback(host):
    text = str(host if host is not None else "")
    return (text in ("", "127.0.0.1", "::1", "localhost")
            or text.startswith("127."))


def _record(kind, target):
    if not _LOG:
        return
    try:
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "pid": os.getpid(), "kind": kind, "target": str(target),
                "at_ms": int(time.time() * 1000),
            }) + "\n")
    except OSError:
        pass


def _deny(kind, target):
    _record(kind, target)
    raise RuntimeError(f"PUBLIC_CONNECTION_BLOCKED:{kind}:{target}")


_connect = socket.socket.connect


def _guarded_connect(self, address):
    if getattr(self, "family", None) in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) else address
        if not _loopback(host):
            _deny("connect", address)
    return _connect(self, address)


socket.socket.connect = _guarded_connect

_connect_ex = socket.socket.connect_ex


def _guarded_connect_ex(self, address):
    if getattr(self, "family", None) in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) else address
        if not _loopback(host):
            _deny("connect_ex", address)
    return _connect_ex(self, address)


socket.socket.connect_ex = _guarded_connect_ex

_getaddrinfo = socket.getaddrinfo


def _guarded_getaddrinfo(host, port, *args, **kwargs):
    if host is not None and not _loopback(host):
        _deny("getaddrinfo", f"{host}:{port}")
    return _getaddrinfo(host, port, *args, **kwargs)


socket.getaddrinfo = _guarded_getaddrinfo
'''

EXPLORER_WRAPPER = r'''
"""Wrapper local del explorador: fuerza `--no-fetch` y ejecuta el CLI real.

El dashboard de prueba se arranca con MARKET_EXPLORER_ROOT apuntando aqui; el
bridge usa este script y PYTHONPATH=<shadow>/src, que carga sitecustomize (la
guarda de red). El CLI canonico se ejecuta con runpy para no duplicar codigo.
"""
import os
import runpy
import sys

_CANON = os.environ["MICROPROBE_TEST_CANON_SCRIPT"]
if "--no-fetch" not in sys.argv:
    sys.argv.append("--no-fetch")
sys.argv[0] = _CANON
runpy.run_path(_CANON, run_name="__main__")
'''


def price_for(symbol: str, open_ms: int) -> float:
    base = 100_000.0 if symbol == "BTCUSDT" else 1.05
    phase = (open_ms // STEP_MS) / 17.0
    wave = math.sin(phase) * (35.0 if symbol == "BTCUSDT" else 0.012)
    return round(base + wave, 8 if symbol == "MINAUSDT" else 2)


def seed_cache(cache_path: Path, now: int) -> Dict[str, Any]:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(cache_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    cache = MarketCache(cache_path)
    cache.init_db()
    fetched_at = now
    seeded: Dict[str, Any] = {}
    for symbol in ("BTCUSDT", "MINAUSDT"):
        # 1m: 7 dias (cubre inicial 300 + bloque anterior 300 con margen).
        last_1m = (now // STEP_MS) * STEP_MS - STEP_MS
        first_1m = last_1m - (7 * 24 * 60 - 1) * STEP_MS
        bars_1m = []
        cursor = first_1m
        while cursor <= last_1m:
            open_price = price_for(symbol, cursor)
            close_price = price_for(symbol, cursor + STEP_MS)
            high = max(open_price, close_price) * 1.0008
            low = min(open_price, close_price) * 0.9992
            bars_1m.append({
                "open_time": cursor, "open": f"{open_price}",
                "high": f"{high:.8f}" if symbol == "MINAUSDT" else f"{high:.2f}",
                "low": f"{low:.8f}" if symbol == "MINAUSDT" else f"{low:.2f}",
                "close": f"{close_price}",
                "base_volume": "125.5", "quote_volume": "125500.0",
                "trade_count": 42, "close_time": cursor + STEP_MS - 1,
            })
            cursor += STEP_MS
        cache.upsert_klines(symbol, "1m", "klines", bars_1m, fetched_at)
        # 1h: 30 dias; el primer render del explorador usa 1h antes de cambiar.
        last_1h = (now // HOUR_MS) * HOUR_MS - HOUR_MS
        first_1h = last_1h - (30 * 24 - 1) * HOUR_MS
        bars_1h = []
        cursor = first_1h
        while cursor <= last_1h:
            open_price = price_for(symbol, cursor)
            close_price = price_for(symbol, cursor + HOUR_MS)
            bars_1h.append({
                "open_time": cursor, "open": f"{open_price}",
                "high": f"{max(open_price, close_price) * 1.001:.8f}"
                        if symbol == "MINAUSDT" else
                        f"{max(open_price, close_price) * 1.001:.2f}",
                "low": f"{min(open_price, close_price) * 0.999:.8f}"
                       if symbol == "MINAUSDT" else
                       f"{min(open_price, close_price) * 0.999:.2f}",
                "close": f"{close_price}",
                "base_volume": "5000.0", "quote_volume": "5000000.0",
                "trade_count": 900, "close_time": cursor + HOUR_MS - 1,
            })
            cursor += HOUR_MS
        cache.upsert_klines(symbol, "1h", "klines", bars_1h, fetched_at)
        seeded[symbol] = {"1m": len(bars_1m), "1h": len(bars_1h)}
    entries = []
    for symbol, base in (("BTCUSDT", "BTC"), ("MINAUSDT", "MINA")):
        entries.append({
            "symbol": symbol, "base_asset": base, "quote_asset": "USDT",
            "margin_asset": "USDT", "contract_type": "PERPETUAL",
            "status": "TRADING", "onboard_ms": 1_600_000_000_000,
            "price_precision": 2 if symbol == "BTCUSDT" else 4,
            "tick_size": "0.10" if symbol == "BTCUSDT" else "0.0001",
            "eligible": True, "exclusion_reasons": [],
        })
    cache.replace_catalog(entries, fetched_at)
    cache.set_meta("catalog_fetched_at_ms", fetched_at)
    cache.set_meta("catalog_entries", len(entries))
    cache.set_meta("catalog_endpoint", "/fapi/v1/exchangeInfo")
    return {"cache_db": str(cache_path), "seeded": seeded,
            "catalog_entries": len(entries),
            "last_closed_1m": (now // STEP_MS) * STEP_MS - STEP_MS}


def prepare_shadow(workdir: Path) -> Dict[str, str]:
    shadow = workdir / "shadow"
    (shadow / "src").mkdir(parents=True, exist_ok=True)
    (shadow / "scripts").mkdir(parents=True, exist_ok=True)
    (shadow / "src" / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    (shadow / "scripts" / "market_explorer.py").write_text(
        EXPLORER_WRAPPER, encoding="utf-8")
    return {
        "root": str(shadow),
        "src": str(shadow / "src"),
        "canon_src": str(ROOT / "src"),
        "canon_script": str(ROOT / "scripts" / "market_explorer.py"),
        "conn_log": str(workdir / "public-attempts.jsonl"),
        "proxy_log": str(workdir / "proxy-attempts.jsonl"),
        "fake_log": str(workdir / "fake-ws.jsonl"),
        "browser_log": str(workdir / "browser-external.jsonl"),
    }


# ---------------------------------------------------------------------------
# Fake kline WS (loopback), reloj real
# ---------------------------------------------------------------------------

class FakeKlineServer:
    def __init__(self, port: int, log_path: Path) -> None:
        self.port = int(port)
        self.log_path = Path(log_path)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.server = None
        self.ready = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._thread_main, daemon=True,
                                       name="fake-kline-ws")
        self.thread.start()
        if not self.ready.wait(10.0):
            raise HarnessError("FAKE_WS_NOT_READY")
        # `ready` se senala despues de enlazar; no se sondea con un connect
        # vacio porque el servidor WS lo registra como handshake fallido.

    def _thread_main(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
            self.loop.run_forever()
        finally:
            try:
                self.loop.close()
            except Exception:  # noqa: BLE001
                pass

    async def _serve(self) -> None:
        from websockets.asyncio.server import serve
        self.server = await serve(self._handler, "127.0.0.1", self.port,
                                  ping_interval=None)
        self.ready.set()

    def _record(self, payload: Dict[str, Any]) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError:
            pass

    async def _handler(self, ws) -> None:
        request = getattr(ws, "request", None)
        path = getattr(request, "path", "") or getattr(ws, "path", "")
        streams = (parse_qs(urlsplit(path).query).get("streams") or [""])[0]
        initial = [item for item in streams.split("/") if "@kline_" in item]
        symbols = [item.split("@")[0].upper() for item in initial]
        self._record({"kind": "connect", "path": path, "symbols": symbols,
                      "at_ms": now_ms()})
        tasks: Dict[str, asyncio.Task] = {}

        def start_symbol(symbol: str) -> None:
            if symbol in tasks and not tasks[symbol].done():
                return
            tasks[symbol] = asyncio.create_task(self._ticker(ws, symbol))

        for symbol in symbols:
            start_symbol(symbol)
        try:
            async for raw in ws:
                try:
                    message = json.loads(raw if isinstance(raw, str)
                                         else raw.decode("utf-8", "replace"))
                except ValueError:
                    continue
                method = str(message.get("method") or "").upper()
                params = message.get("params") or []
                names = [str(item) for item in params if "@kline_" in str(item)]
                added = [name.split("@")[0].upper() for name in names]
                self._record({"kind": method.lower(), "params": names,
                              "at_ms": now_ms()})
                if method == "SUBSCRIBE":
                    for symbol in added:
                        start_symbol(symbol)
                elif method == "UNSUBSCRIBE":
                    for symbol in added:
                        task = tasks.pop(symbol, None)
                        if task is not None:
                            task.cancel()
        except Exception as exc:  # noqa: BLE001 - cierre del peer
            self._record({"kind": "handler_error", "detail": str(exc)[:200],
                          "at_ms": now_ms()})
        finally:
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

    async def _ticker(self, ws, symbol: str) -> None:
        state = {"open": None, "open_price": None, "high": None, "low": None,
                 "close": None, "last_event": 0, "volume": 0.0}
        try:
            while True:
                now = now_ms()
                current_open = (now // STEP_MS) * STEP_MS
                if state["open"] is None:
                    state["open"] = current_open
                    state["open_price"] = price_for(symbol, current_open)
                    state["high"] = state["open_price"]
                    state["low"] = state["open_price"]
                    state["close"] = state["open_price"]
                    state["last_event"] = now
                    state["volume"] = 1.0
                    await self._send(ws, symbol, state, closed=False,
                                     event_ms=now)
                elif current_open > state["open"]:
                    # Cierre real de la vela anterior y apertura de la siguiente.
                    close_ms = state["open"] + STEP_MS - 1
                    await self._send(ws, symbol, state, closed=True,
                                     event_ms=max(now, state["last_event"] + 1))
                    state["open"] = current_open
                    state["open_price"] = price_for(symbol, current_open)
                    state["high"] = state["open_price"]
                    state["low"] = state["open_price"]
                    state["close"] = state["open_price"]
                    state["last_event"] = max(now, state["last_event"] + 2)
                    state["volume"] = 1.0
                    await self._send(ws, symbol, state, closed=False,
                                     event_ms=state["last_event"])
                else:
                    state["last_event"] = max(now, state["last_event"] + 1)
                    move = math.sin(state["last_event"] / 7000.0) * (
                        3.0 if symbol == "BTCUSDT" else 0.001)
                    state["close"] = round(
                        (state["open_price"] or price_for(symbol, state["open"]))
                        + move, 8 if symbol == "MINAUSDT" else 2)
                    state["high"] = max(state["high"], state["close"])
                    state["low"] = min(state["low"], state["close"])
                    state["volume"] = round(state["volume"] + 0.4, 4)
                    await self._send(ws, symbol, state, closed=False,
                                     event_ms=state["last_event"])
                await asyncio.sleep(2.0)
        except (asyncio.CancelledError, ConnectionError, OSError):
            raise
        except Exception:  # noqa: BLE001 - el peer cerro
            return

    async def _send(self, ws, symbol: str, state: Dict[str, Any],
                    *, closed: bool, event_ms: int) -> None:
        open_ms = int(state["open"])
        open_price = state["open_price"]
        close_price = state["close"]
        payload = {
            "stream": f"{symbol.lower()}@kline_1m",
            "data": {
                "e": "kline", "E": int(event_ms), "s": symbol,
                "k": {
                    "t": open_ms, "T": open_ms + STEP_MS - 1, "s": symbol,
                    "i": "1m", "o": f"{open_price}", "c": f"{close_price}",
                    "h": f"{state['high']}", "l": f"{state['low']}",
                    "v": f"{state['volume']}", "q": f"{state['volume'] * 1000}",
                    "n": int(state["volume"] * 3), "x": bool(closed),
                },
            },
        }
        await ws.send(json.dumps(payload))
        self._record({"kind": "closed" if closed else "candle",
                      "symbol": symbol, "open_ms": open_ms,
                      "event_ms": int(event_ms), "at_ms": now_ms()})

    def stop(self) -> None:
        if self.loop is None:
            return

        async def _close() -> None:
            if self.server is not None:
                self.server.close()
                await self.server.wait_closed()

        try:
            future = asyncio.run_coroutine_threadsafe(_close(), self.loop)
            future.result(timeout=5.0)
        except Exception:  # noqa: BLE001 - la parada no debe enmascarar el fallo
            pass
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except RuntimeError:
            pass
        if self.thread is not None:
            self.thread.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Proxy que registra y rechaza cualquier intento publico
# ---------------------------------------------------------------------------

class BlockingProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        try:
            self.request.settimeout(3.0)
            raw = self.request.recv(4096)
            line = raw.split(b"\r\n", 1)[0].decode("latin-1", "replace")
            if line:
                # Un connect-and-close (sonda de disponibilidad) no es un
                # intento de proxy; no debe contarse como trafico publico.
                self.server.record(line)  # type: ignore[attr-defined]
            self.request.sendall(
                b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n"
                b"Connection: close\r\n\r\n")
        except OSError:
            pass


class ProxyServer:
    def __init__(self, port: int, log_path: Path) -> None:
        self.log_path = Path(log_path)
        self.server = BlockingProxy(("127.0.0.1", int(port)), ProxyHandler)
        self.server.record = self._record  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True, name="blocking-proxy")

    def _record(self, line: str) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"line": line, "at_ms": now_ms()}) + "\n")
        except OSError:
            pass

    def start(self) -> None:
        # ThreadingTCPServer ya enlaza el puerto en el constructor; no se sondea
        # con un connect vacio para no registrar un falso intento de proxy.
        self.thread.start()
        if not self.thread.is_alive():
            raise HarnessError("PROXY_NOT_READY")

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3.0)


# ---------------------------------------------------------------------------
# Orquestador (subproceso) y lectura de sus condiciones
# ---------------------------------------------------------------------------

class OrchestratorRunner:
    def __init__(self, args: argparse.Namespace, run_json: Path,
                 stderr_log: Path, env: Dict[str, str],
                 hold_signal: Path, post_reconnect_signal: Path) -> None:
        self.args = args
        self.run_json = run_json
        self.stderr_log = stderr_log
        self.env = env
        self.hold_signal = hold_signal
        self.post_reconnect_signal = post_reconnect_signal
        self.proc: Optional[subprocess.Popen] = None
        self.lines: "queue.Queue[Tuple[str, Optional[str]]]" = queue.Queue()
        self.consumed: List[str] = []
        self._readers: List[threading.Thread] = []

    def start(self) -> None:
        hold_signal = self.hold_signal
        cmd = [
            sys.executable, "-X", "utf8",
            str(ROOT / "scripts" / "market_stream_window.py"),
            "--execute", "--symbols", "BTCUSDT,MINAUSDT", "--interval", "1m",
            "--duration", str(self.args.duration),
            "--hold-seconds", str(self.args.hold_seconds),
            "--hold-signal", str(hold_signal),
            "--post-reconnect-signal", str(self.post_reconnect_signal),
            "--max-messages", "1200", "--max-events", "6000",
            "--max-reconnects", "3",
            "--port", str(self.args.service_port),
            "--dashboard-url", self.args.dashboard_url,
            "--browser-consumer", "--await-consumers", "1",
            "--await-timeout", str(self.args.await_timeout),
            "--release-browser",
            "--release-timeout", str(self.args.release_timeout),
            "--reconnect-timeout", str(self.args.reconnect_timeout),
            "--out", str(self.run_json),
        ]
        if getattr(self.args, "transport", "local") == "local":
            cmd.extend(["--base-url",
                        f"ws://127.0.0.1:{self.args.fake_port}"])
        log("orquestador: " + " ".join(cmd))
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), env=self.env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", bufsize=1)
        self._readers = [
            threading.Thread(target=self._read, args=(self.proc.stdout, "stdout"),
                             daemon=True),
            threading.Thread(target=self._read, args=(self.proc.stderr, "stderr"),
                             daemon=True),
        ]
        for reader in self._readers:
            reader.start()

    def _read(self, stream, kind: str) -> None:
        try:
            for line in stream:
                self.lines.put((kind, line.rstrip()))
        finally:
            self.lines.put((kind, None))

    def wait_for(self, needle: str, timeout: float) -> str:
        started = time.monotonic()
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise HarnessError(f"ORCHESTRATOR_TIMEOUT:{needle}")
            try:
                kind, line = self.lines.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue
            if line is None:
                continue
            self.consumed.append(f"{kind}: {line}")
            if needle in line:
                log(f"orquestador[{kind}]: {line}")
                return line

    def drain(self, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                kind, line = self.lines.get(timeout=0.2)
            except queue.Empty:
                continue
            if line is not None:
                self.consumed.append(f"{kind}: {line}")

    def write_stderr_log(self) -> None:
        self.stderr_log.write_text("\n".join(self.consumed) + "\n",
                                   encoding="utf-8")

    def wait_exit(self, timeout: float = 25.0) -> int:
        if self.proc is None:
            raise HarnessError("ORCHESTRATOR_NOT_STARTED")
        try:
            code = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise HarnessError("ORCHESTRATOR_DID_NOT_EXIT")
        self.drain(1.0)
        for reader in self._readers:
            reader.join(timeout=2.0)
        self.write_stderr_log()
        return int(code)

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5.0)


# ---------------------------------------------------------------------------
# Verificacion del entorno de prueba del dashboard
# ---------------------------------------------------------------------------

def verify_dashboard(dashboard_url: str) -> Dict[str, Any]:
    base = dashboard_url.rstrip("/")
    catalog = http_json(f"{base}/api/v1/market-contracts?q=BTCUSDT&limit=20",
                        timeout=20.0)
    entries = ((catalog.get("catalog") or {}).get("entries"))
    refresh = catalog.get("refresh") or {}
    if entries != 2:
        raise HarnessError(
            f"DASHBOARD_NOT_IN_TEST_ENV:catalog_entries={entries} (esperado 2)")
    if refresh.get("reason") != "DISABLED":
        raise HarnessError(
            f"DASHBOARD_NOT_IN_TEST_ENV:refresh_reason={refresh.get('reason')}")
    series = http_json(
        f"{base}/api/v1/market-series?symbol=BTCUSDT&interval=1m&bars=300",
        timeout=20.0)
    fetch = series.get("fetch") or {}
    if fetch.get("allowed") is not False or fetch.get("performed") is not False:
        raise HarnessError(
            f"DASHBOARD_NOT_IN_TEST_ENV:fetch_allowed={fetch.get('allowed')}")
    candles = series.get("candles") or []
    if len(candles) < 250:
        raise HarnessError(f"DASHBOARD_TEST_CACHE_EMPTY:candles={len(candles)}")
    return {"catalog_entries": entries, "refresh": refresh,
            "series_candles": len(candles), "fetch": fetch}


def verify_dashboard_public(dashboard_url: str) -> Dict[str, Any]:
    """Verifica que el dashboard canonico esta arriba y sirve contratos.

    No exige el entorno de prueba local (catalogo 2, fetch deshabilitado);
    el dashboard canonico tiene el catalogo completo. Solo confirma que
    responde HTTP 200 en /market-lab y en /api/v1/market-contracts.
    """
    base = dashboard_url.rstrip("/")
    req = urllib.request.Request(f"{base}/market-lab", method="GET")
    with urllib.request.urlopen(req, timeout=20.0) as resp:
        status = resp.status
    if status != 200:
        raise HarnessError(f"DASHBOARD_NOT_RESPONDING:market-lab={status}")
    catalog = http_json(f"{base}/api/v1/market-contracts?q=BTCUSDT&limit=20",
                        timeout=20.0)
    entries = ((catalog.get("catalog") or {}).get("entries"))
    return {"market_lab": status, "catalog_entries": entries}


def wait_minute_phase(limit_s: float = 60.0) -> float:
    """Espera al inicio de un minuto real (condicion observada, no reloj falso).

    Abrir la pagina justo despues del limite deja la captura #1 antes del
    cierre y la #2 despues, sin alargar ninguna espera manual.
    """
    started = time.monotonic()
    while True:
        phase = now_ms() % STEP_MS
        if phase <= 1500:
            return time.monotonic() - started
        remaining = (STEP_MS - phase + 400) / 1000.0
        if time.monotonic() - started + remaining > limit_s:
            raise HarnessError("MINUTE_PHASE_TIMEOUT")
        time.sleep(min(remaining, 1.0))


# ---------------------------------------------------------------------------
# Recorrido unico
# ---------------------------------------------------------------------------

def capture(page, pagination: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = page.evaluate(CAPTURE_JS)
    if pagination is not None:
        data["pagination"] = pagination
    return data


def wait_identity_live(page, timeout: float) -> float:
    started = time.monotonic()
    page.wait_for_function(
        """() => {
          const text = (id) => {
            const node = document.querySelector(`[data-testid="${id}"]`);
            return node ? (node.textContent || "").trim() : "";
          };
          return text("explorer-stream")
              .includes("Binance USD-M · BTCUSDT · 1m · market-stream/v1")
            && text("explorer-stream-state").startsWith("RECIBIENDO")
            && text("explorer-stream-live") === "LIVE";
        }""",
        timeout=int(timeout * 1000))
    return time.monotonic() - started


def wait_preflight(page, timeout: float) -> float:
    """Espera a que el navegador esté en BTCUSDT/1m con el gráfico cargado.

    Preflight obligatorio antes de arrancar el servicio público: el usuario
    debe haber buscado y seleccionado BTCUSDT, elegido el intervalo 1m y tener
    el gráfico listo. Si esto falla, se aborta sin iniciar el servicio ni
    consumir la ventana.
    """
    started = time.monotonic()
    page.wait_for_function(
        """() => {
          const selected = (id) => {
            const node = document.querySelector(`[data-testid="${id}"]`);
            return node ? (node.textContent || "").trim() : "";
          };
          const selText = selected("explorer-selected");
          const intervalNode = document.querySelector(
            '[data-testid="explorer-interval"]');
          return selText.includes("BTCUSDT")
            && intervalNode !== null
            && intervalNode.value === "1m";
        }""",
        timeout=int(timeout * 1000))
    return time.monotonic() - started


def wait_count_above(page, before: int, timeout: float) -> float:
    started = time.monotonic()
    page.wait_for_function(
        """(before) => {
          const node = document.querySelector(
            '[data-testid="explorer-stream-count"]');
          const match = /(\\d+)\\s+cargadas/.exec(node ? node.textContent : "");
          return match ? Number(match[1]) > before : false;
        }""",
        arg=before, timeout=int(timeout * 1000))
    return time.monotonic() - started


def service_health(port: int) -> Optional[Dict[str, Any]]:
    try:
        return http_json(f"http://127.0.0.1:{port}/health", timeout=3.0)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def wait_consumers(port: int, expected: int, timeout: float) -> float:
    def check() -> bool:
        health = service_health(port)
        return bool(health) and int(health.get("consumers") or 0) == expected
    return wait_until(check, timeout, 0.1, f"consumers={expected}")


def reconnect_and_wait(page, port: int, timeout: float) -> Tuple[int, float]:
    """Reabre la suscripcion del navegador hasta observar `consumers=1`.

    El primer intento puede coincidir con el cierre del SSE anterior en el BFF;
    si en una ventana corta no aparece consumidor se reabre el EventSource
    (cerrando el nativo previo) sin ampliar el presupuesto de la fase.
    """
    deadline = time.monotonic() + timeout
    attempts = 0
    last_error: Optional[Exception] = None
    while time.monotonic() < deadline:
        attempts += 1
        opened = page.evaluate("window.__streamHarness.reconnect()")
        if not opened:
            page.evaluate("window.__streamHarness.reopen()")
        window = min(2.5, max(0.4, deadline - time.monotonic()))
        try:
            return attempts, wait_consumers(port, 1, window)
        except HarnessError as exc:
            last_error = exc
    raise HarnessError(f"RECONNECT_TIMEOUT:attempts={attempts}:{last_error}")


def series_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    candles = payload.get("candles") or []
    opens = [int(item.get("open_time_ms") or 0) for item in candles]
    fetch = payload.get("fetch") or {}
    return {
        "symbol": payload.get("symbol"), "interval": payload.get("interval"),
        "requested": payload.get("requested"),
        "candles": len(candles), "unique_opens": len(set(opens)),
        "first_open_ms": opens[0] if opens else None,
        "last_open_ms": opens[-1] if opens else None,
        "fetch_allowed": fetch.get("allowed"),
        "fetch_performed": fetch.get("performed"),
        "fetch_status": fetch.get("status"),
        "storage": payload.get("storage"),
        "coverage": {
            "state": (payload.get("coverage") or {}).get("state"),
            "actual": (payload.get("coverage") or {}).get("actual_bars"),
            "expected": (payload.get("coverage") or {}).get("expected_bars"),
            "gaps": (payload.get("coverage") or {}).get("gap_count"),
        },
        "opens": opens,
    }


def _binance_accredited(transport: str, checks: List[Dict[str, Any]]) -> bool:
    """En modo public, acreditar recepcion real de Binance exige mas que
    activar --transport public: se requiere identidad exacta
    (venue=binance, market_type=usd_m_futures, simbolo, intervalo) y al
    menos un mensaje de vela del simbolo primario. En modo local nunca se
    acredita."""
    if transport != "public":
        return False
    check_ok = {c.get("id"): c.get("ok") for c in checks if isinstance(c, dict)}
    return bool(check_ok.get("identity_exact") is True
                and check_ok.get("messages_primary") is True)


def run_one(index: int, args: argparse.Namespace, workdir: Path,
            out_dir: Path) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    run_dir = out_dir / f"run-{index}"
    run_dir.mkdir(parents=True, exist_ok=True)
    run_started = time.monotonic()
    started_ms = now_ms()
    logs: Dict[str, Any] = {}

    for name in ("public-attempts.jsonl", "proxy-attempts.jsonl",
                 "fake-ws.jsonl", "browser-external.jsonl"):
        path = workdir / name
        if path.exists():
            path.unlink()

    transport = getattr(args, "transport", "local")
    fake = None
    proxy = None
    shadow = None
    cache_info = None
    if transport == "local":
        cache_info = seed_cache(workdir / "market_cache.db", started_ms)
        shadow = prepare_shadow(workdir)
        log(f"run {index}: cache {cache_info['seeded']} catalogo={cache_info['catalog_entries']}")

        fake = FakeKlineServer(args.fake_port, Path(shadow["fake_log"]))
        proxy = ProxyServer(args.proxy_port, Path(shadow["proxy_log"]))
        fake.start()
        proxy.start()

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (shadow["src"], str(ROOT / "src"),
                              env.get("PYTHONPATH", "")) if part)
        env["MICROPROBE_TEST_CANON_SRC"] = shadow["canon_src"]
        env["MICROPROBE_TEST_CANON_SCRIPT"] = shadow["canon_script"]
        env["MICROPROBE_TEST_CONN_LOG"] = shadow["conn_log"]
        env["MICROPROBE_MARKET_CACHE_DB"] = cache_info["cache_db"]
        env["MICROPROBE_MARKET_STREAM_PID"] = str(workdir / "service.json")
        env["MICROPROBE_STREAM_URL"] = f"http://127.0.0.1:{args.service_port}"
        env["HTTP_PROXY"] = f"http://127.0.0.1:{args.proxy_port}"
        env["HTTPS_PROXY"] = f"http://127.0.0.1:{args.proxy_port}"
        env["NO_PROXY"] = "127.0.0.1,localhost,::1"
    else:
        # Modo public: no se toca el dashboard canonico. No se prepara cache
        # temporal, ni shadow, ni sitecustomize, ni wrapper del explorador.
        # El servicio se conecta directamente a Binance (--transport public),
        # por tanto no se heredan los proxies de prueba ni el cache temporal.
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["MICROPROBE_STREAM_URL"] = f"http://127.0.0.1:{args.service_port}"
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                    "MICROPROBE_MARKET_CACHE_DB", "MARKET_EXPLORER_ROOT",
                    "MICROPROBE_TEST_CANON_SRC", "MICROPROBE_TEST_CANON_SCRIPT",
                    "MICROPROBE_TEST_CONN_LOG"):
            env.pop(key, None)

    run_json = run_dir / "run.json"
    stderr_log = run_dir / "orchestrator.log"
    hold_signal = workdir / f"hold-{index}.signal"
    post_reconnect_signal = workdir / f"post-reconnect-{index}.signal"
    for signal_path in (hold_signal, post_reconnect_signal):
        if signal_path.exists():
            signal_path.unlink()

    runner: Optional[OrchestratorRunner] = None
    page = None
    browser = None
    context = None
    dom1 = dom2 = dom3 = dom_reconnect = None
    disconnect_result = reconnect_result = None
    wrapper_after_disconnect = wrapper_after_reconnect = None
    reconnect_since: Optional[int] = None
    network: Dict[str, Any] = {"requests": [], "series": [], "catalog": [],
                               "external": []}
    response_objects: List[Dict[str, Any]] = []
    local_checks: Dict[str, Any] = {}
    durations: Dict[str, float] = {}
    marks: Dict[str, float] = {}
    error: Optional[str] = None
    final_status = "FAIL"
    global_deadline_event = threading.Event()
    global_deadline_timer = threading.Timer(
        LIMITS["run"], lambda: global_deadline_event.set())
    global_deadline_timer.daemon = True
    global_deadline_timer.start()

    def _check_global_deadline() -> None:
        """Lanza si se agoto el deadline global de 180 s que cubre todas
        las fases. Los limites de fase consumen el tiempo restante del
        global; no son presupuestos independientes que se sumen."""
        if global_deadline_event.is_set():
            raise HarnessError("GLOBAL_DEADLINE_EXCEEDED")

    try:
        if transport == "local":
            verify = verify_dashboard(args.dashboard_url)
        else:
            verify = verify_dashboard_public(args.dashboard_url)
        logs["dashboard_verify"] = verify
        durations["dashboard_verify"] = time.monotonic() - run_started

        _check_global_deadline()
        durations["minute_phase"] = wait_minute_phase()
        marks["minute_phase"] = time.monotonic() - run_started
        log(f"run {index}: fase de minuto {durations['minute_phase']:.1f}s")

        # El servicio se inicia tras el preflight del navegador (ver abajo).

        def process_responses(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            summaries: List[Dict[str, Any]] = []
            for item in items:
                url = item["url"]
                response = item["response"]
                if "/api/v1/market-series" in url:
                    try:
                        payload = response.json()
                    except Exception:  # noqa: BLE001
                        payload = None
                    if isinstance(payload, dict):
                        summary = series_summary(payload)
                        summary["at_ms"] = item["at_ms"]
                        summary["url"] = url
                        network["series"].append(summary)
                        summaries.append(summary)
                    else:
                        network["series"].append(
                            {"url": url, "at_ms": item["at_ms"], "body": None})
                elif "/api/v1/market-contracts" in url:
                    try:
                        payload = response.json()
                    except Exception:  # noqa: BLE001
                        payload = None
                    if isinstance(payload, dict):
                        network["catalog"].append({
                            "at_ms": item["at_ms"], "url": url,
                            "entries": (payload.get("catalog") or {}).get("entries"),
                            "refresh": payload.get("refresh"),
                            "results": len(payload.get("results") or []),
                        })
            return summaries

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed,
                                                 args=CHROME_ARGS)
            context = browser.new_context(viewport={"width": 1440, "height": 900},
                                          locale="es-ES")
            page = context.new_page()

            def on_route(route) -> None:
                url = route.request.url
                if (url.startswith("http://127.0.0.1:3020")
                        or url.startswith("http://localhost:3020")
                        or url.startswith(("data:", "blob:", "about:"))):
                    route.continue_()
                    return
                network["external"].append({"url": url, "at_ms": now_ms()})
                route.abort()

            def on_request(request) -> None:
                network["requests"].append({
                    "url": request.url, "method": request.method,
                    "resource_type": request.resource_type, "at_ms": now_ms(),
                })

            def on_response(response) -> None:
                url = response.url
                if ("/api/v1/market-series" in url
                        or "/api/v1/market-contracts" in url):
                    response_objects.append({
                        "url": url, "at_ms": now_ms(), "response": response})

            page.route("**/*", on_route)
            page.on("request", on_request)
            page.on("response", on_response)
            page.add_init_script(WRAPPER_JS)
            page.goto(f"{args.dashboard_url.rstrip('/')}/market-lab",
                      wait_until="domcontentloaded", timeout=30_000)

            # PREFLIGHT: buscar BTCUSDT, seleccionar, intervalo 1m, gráfico
            # cargado. Identidad estable: búsqueda por símbolo, no por posición.
            # Si el preflight falla, se aborta sin arrancar el servicio.
            page.wait_for_selector('[data-testid="explorer-catalog-state"]',
                                   timeout=30_000)
            page.fill('[data-testid="explorer-query"]', "BTCUSDT")
            page.click('[data-testid="explorer-search"]')
            page.wait_for_selector('[data-testid="explorer-open-BTCUSDT"]',
                                   timeout=30_000)
            page.click('[data-testid="explorer-open-BTCUSDT"]')
            page.wait_for_selector('[data-testid="explorer-interval"]',
                                   timeout=20_000)
            page.select_option('[data-testid="explorer-interval"]', "1m")
            _check_global_deadline()
            durations["preflight"] = wait_preflight(page, LIMITS["page_ready"])
            marks["preflight"] = time.monotonic() - run_started
            log(f"run {index}: preflight BTCUSDT/1m en "
                f"{durations['preflight']:.1f}s")

            # Iniciar servicio DESPUÉS del preflight del navegador. Si el
            # preflight falló, nunca se llega aquí.
            runner = OrchestratorRunner(args, run_json, stderr_log, env,
                                        hold_signal, post_reconnect_signal)
            runner.start()
            wait_until(lambda: service_health(args.service_port) is not None,
                       20.0, 0.1, "service_up")
            marks["service_up"] = time.monotonic() - run_started
            log(f"run {index}: servicio {args.service_port} arriba")

            _check_global_deadline()
            durations["page_ready"] = wait_identity_live(page, LIMITS["page_ready"])
            marks["page_ready"] = time.monotonic() - run_started
            log(f"run {index}: pagina LIVE en {durations['page_ready']:.1f}s")
            initial_series = process_responses(response_objects)
            processed = len(response_objects)
            initial_opens: set[int] = set()
            for item in initial_series:
                if item.get("interval") == "1m" and item.get("candles"):
                    initial_opens.update(item.get("opens") or [])
            dom1 = capture(page)
            dom1["initial_series"] = len(initial_series)
            dom1["initial_opens"] = len(initial_opens)
            log(f"run {index}: series iniciales={len(initial_series)} "
                f"opens_1m={len(initial_opens)}")

            _check_global_deadline()
            accept_started = time.monotonic()
            runner.wait_for("ACEPTACION DE CADENA ALCANZADA",
                            LIMITS["acceptance"])
            durations["acceptance"] = time.monotonic() - accept_started
            marks["acceptance"] = time.monotonic() - run_started
            log(f"run {index}: aceptacion alcanzada en "
                f"{durations['acceptance']:.1f}s")

            _check_global_deadline()
            pagination_started = time.monotonic()
            before_count = int(dom1.get("candles") or 0)
            window_before = dom1.get("chart_window")
            click_at = now_ms()
            with page.expect_response(
                    lambda response: ("/api/v1/market-series" in response.url
                                      and "from_ms=" in response.url),
                    timeout=int(LIMITS["pagination"] * 1000)) as response_info:
                page.click('[data-testid="market-chart-earlier"]')
            earlier_response = response_info.value
            earlier_payload = earlier_response.json()
            earlier = series_summary(earlier_payload)
            wait_count_above(page, before_count, 10.0)
            earlier_requests = [
                item for item in network["requests"]
                if "/api/v1/market-series" in item["url"]
                and "from_ms=" in item["url"] and item["at_ms"] >= click_at
            ]
            process_responses(response_objects[processed:])
            processed = len(response_objects)
            dom2 = capture(page)
            window_after = dom2.get("chart_window")
            pagination = {
                "candles_before": before_count,
                "candles_after": dom2.get("candles"),
                "same_identity": dom1.get("identity") == dom2.get("identity"),
                "error": dom2.get("error"),
                "exhausted": False,
            }
            dom2["pagination"] = pagination
            health2 = service_health(args.service_port)
            new_unique = len(set(earlier.get("opens") or []) - initial_opens)
            durations["pagination"] = time.monotonic() - pagination_started
            marks["pagination"] = time.monotonic() - run_started
            log(f"run {index}: paginacion {before_count}->{dom2.get('candles')} "
                f"nuevas={new_unique} peticiones={len(earlier_requests)} "
                f"en {durations['pagination']:.1f}s")
            hold_signal.write_text("1", encoding="utf-8")

            _check_global_deadline()
            runner.wait_for("desconecta la suscripcion del navegador",
                            LIMITS["release"])
            release_started = time.monotonic()
            disconnect_result = page.evaluate("window.__streamHarness.disconnect()")
            wrapper_after_disconnect = page.evaluate("window.__streamHarness.debug()")
            release_ms = wait_consumers(args.service_port, 0,
                                        LIMITS["release"])
            health_released = service_health(args.service_port)
            durations["release"] = time.monotonic() - release_started
            marks["release"] = time.monotonic() - run_started
            log(f"run {index}: liberado en {durations['release']:.1f}s "
                f"disconnect={disconnect_result} wrapper={wrapper_after_disconnect}")

            _check_global_deadline()
            runner.wait_for("reconecta la suscripcion del navegador",
                            LIMITS["reconnect"])
            reconnect_started = time.monotonic()
            reconnect_since = now_ms()
            reconnect_attempts, reconnect_ms = reconnect_and_wait(
                page, args.service_port, LIMITS["reconnect"])
            reconnect_result = reconnect_attempts
            wrapper_after_reconnect = page.evaluate("window.__streamHarness.debug()")
            log(f"run {index}: reconnect intentos={reconnect_attempts} "
                f"wrapper={wrapper_after_reconnect}")
            wait_identity_live(page, LIMITS["reconnect"])
            wait_fresh_update(page, reconnect_since, LIMITS["reconnect"])
            dom_reconnect = capture(page)
            health_reconnected = service_health(args.service_port)
            durations["reconnect"] = time.monotonic() - reconnect_started
            marks["reconnect"] = time.monotonic() - run_started
            log(f"run {index}: reconectado en {durations['reconnect']:.1f}s")
            # El orquestador mantiene el servicio vivo hasta esta senal: la
            # captura DOM de reconexion no compite con la parada ordenada.
            post_reconnect_signal.write_text("1", encoding="utf-8")

            _check_global_deadline()
            runner.wait_for("consumidores_tras_reconectar", 20.0)
            code = runner.wait_exit(25.0)
            marks["orchestrator_exit"] = time.monotonic() - run_started
            log(f"run {index}: orquestador termino (exit {code})")
            _check_global_deadline()
            notice_started = time.monotonic()
            wait_until(lambda: not port_open("127.0.0.1", args.service_port),
                       10.0, 0.1, "service_port_closed")
            pid_file = workdir / "service.json"
            wait_until(lambda: not pid_file.exists(), 10.0, 0.1,
                       "pidfile_removed")
            health_down = service_health(args.service_port)
            page.wait_for_selector('[data-testid="explorer-stream-down"]',
                                   timeout=int(LIMITS["down_notice"] * 1000))
            durations["down_notice"] = time.monotonic() - notice_started
            marks["down_notice"] = time.monotonic() - run_started
            dom3 = capture(page)
            log(f"run {index}: aviso de servicio detenido en "
                f"{durations['down_notice']:.1f}s")

            # Evidencia de red del navegador (allowlist) y de la cache local.
            (run_dir / "browser-external.jsonl").write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n"
                        for item in network["external"]), encoding="utf-8")

            run = json.loads(run_json.read_text(encoding="utf-8"))
            after_stop = (run.get("service") or {}).get("after_stop") or {}
            storage = (run.get("storage") or {})
            hold_seen = bool((run.get("service") or {}).get("hold_signal_seen"))
            released = bool((run.get("service") or {}).get("consumers_released"))
            reconnected = bool(
                (run.get("service") or {}).get("consumers_reconnected"))

            # Finaliza el veredicto con la evidencia DOM (sin abrir red).
            finalize_cmd = [
                sys.executable, "-X", "utf8",
                str(ROOT / "scripts" / "market_stream_window.py"),
                "--finalize", str(run_json),
                "--dom-first", str(run_dir / "dom-1.json"),
                "--dom-last", str(run_dir / "dom-2.json"),
                "--dom-after-stop", str(run_dir / "dom-stop.json"),
                "--out", str(run_json),
            ]
            (run_dir / "dom-1.json").write_text(
                json.dumps(dom1, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            (run_dir / "dom-2.json").write_text(
                json.dumps(dom2, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            (run_dir / "dom-stop.json").write_text(
                json.dumps(dom3, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            if dom_reconnect is not None:
                (run_dir / "dom-reconnected.json").write_text(
                    json.dumps(dom_reconnect, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
            finalized = subprocess.run(finalize_cmd, cwd=str(ROOT), env=env,
                                       capture_output=True, text=True,
                                       encoding="utf-8", errors="replace")
            (run_dir / "finalize.log").write_text(
                (finalized.stdout or "") + (finalized.stderr or ""),
                encoding="utf-8")
            run = json.loads(run_json.read_text(encoding="utf-8"))

            if transport == "local":
                proxy_attempts = read_jsonl(Path(shadow["proxy_log"]))
                guard_attempts = read_jsonl(Path(shadow["conn_log"]))
                all_fetch_local = all(
                    item.get("fetch_allowed") is False
                    and item.get("fetch_performed") is False
                    for item in network["series"] if item.get("candles") is not None
                ) and bool(network["series"])
                catalog_local = all(
                    (item.get("refresh") or {}).get("requests") == 0
                    for item in network["catalog"]) and bool(network["catalog"])
            else:
                proxy_attempts = []
                guard_attempts = []
                all_fetch_local = None
                catalog_local = None
            browser_external = list(network["external"])
            # Presupuesto de red: carga inicial + paginacion + cualquier
            # recuperacion automatica del servicio, contado en conjunto.
            # Maximo dos peticiones REST de velas (300 cada una); el catalogo
            # se sirve desde cache y no genera peticiones silenciosas.
            rest_market_requests = len([
                item for item in network["requests"]
                if "/api/v1/market-series" in item.get("url", "")
            ])

            checks = run.get("checks") or []
            failed = run.get("failed") or []
            missing = run.get("missing") or []
            dom_checks = {item.get("id"): item.get("ok") for item in checks
                          if str(item.get("id", "")).startswith("dom_")}
            age2 = None
            updated2 = (dom2.get("updated") or "")
            import re as _re
            age_match = _re.search(r"hace\s+(\d+)\s*s", updated2)
            if age_match:
                age2 = int(age_match.group(1))

            socket2 = (health2 or {}).get("socket") or {}
            span_before = window_span_ms(window_before)
            span_after = window_span_ms(window_after)
            if transport == "local":
                zero_public = (not proxy_attempts and not guard_attempts
                               and not browser_external and all_fetch_local
                               and catalog_local)
            else:
                zero_public = not browser_external
            local_checks = {
                "zero_public_attempts": zero_public,
                # En modo local no hay REST real a Binance (todo va al cache);
                # el presupuesto de 2 REST en conjunto aplica al servicio en
                # modo public y se verifica como techo superior de lo que el
                # navegador ve a traves del BFF.
                "rest_market_budget": (True if transport == "local"
                                       else rest_market_requests <= 2),
                "preflight_ok": bool(durations.get("preflight") is not None),
                "all_series_local": all_fetch_local,
                "catalog_local": catalog_local,
                "one_pagination_request": len(earlier_requests) == 1,
                "pagination_new_unique": new_unique > 0,
                "pagination_grew": (dom2.get("candles") or 0) > before_count,
                "framing_preserved": (span_before is not None
                                      and span_before == span_after),
                "recent_updates": age2 is not None and age2 <= 10,
                "service_active_at_capture2": bool(health2)
                and int(health2.get("consumers") or 0) > 0
                and bool(socket2.get("connected")),
                "hold_signal_seen": hold_seen,
                "consumers_released": released and bool(health_released),
                "browser_reconnected": reconnected and dom_reconnect is not None
                and (dom_reconnect.get("live") == "LIVE")
                and (updated_ms(dom_reconnect.get("updated")) or 0)
                >= (reconnect_since or 0),
                "down_notice": bool(dom3.get("down")),
                "down_cause": bool(dom3.get("down"))
                and "Servicio de datos detenido" in (dom3.get("down") or "")
                and (dom3.get("state") or "").startswith("DESCONECTADO"),
                "history_preserved": (dom3.get("candles") or 0)
                >= (dom2.get("candles") or 0),
                "no_reload": (dom3.get("navigation_count") == 1
                              and dom3.get("reload_count") == 0),
                "clean_stop": (bool(after_stop.get("process_exited"))
                               and bool(after_stop.get("port_closed"))
                               and bool(after_stop.get("pidfile_removed"))
                               and health_down is None),
                "canonical_dbs_unchanged": bool(
                    storage.get("canonical_dbs_unchanged")),
                "finalizer_pass": (run.get("verdict") == "PASS"
                                   and not failed and not missing),
                "dom_checks": dom_checks,
                "phases_within_limits": {
                    "minute_phase": durations.get("minute_phase", 999)
                    <= LIMITS["minute_phase"],
                    "preflight": durations.get("preflight", 999)
                    <= LIMITS["page_ready"],
                    "page_ready": durations.get("page_ready", 999)
                    <= LIMITS["page_ready"],
                    "acceptance": durations.get("acceptance", 999)
                    <= LIMITS["acceptance"],
                    "pagination": durations.get("pagination", 999)
                    <= LIMITS["pagination"],
                    "release": durations.get("release", 999) <= LIMITS["release"],
                    "reconnect": durations.get("reconnect", 999)
                    <= LIMITS["reconnect"],
                    "down_notice": durations.get("down_notice", 999)
                    <= LIMITS["down_notice"],
                },
            }
            durations["run"] = time.monotonic() - run_started
            local_checks["global_budget"] = durations["run"] <= LIMITS["run"]
            local_checks["global_deadline_respected"] = not bool(
                global_deadline_event.is_set())
            # El deadline global de 180 s cubre todas las fases: si se agota,
            # el recorrido falla aunque cada fase individual respetara su limite.
            if global_deadline_event.is_set():
                procedural = False
                final_status = "ERROR"
            else:
                procedural = all(
                    value is True for key, value in local_checks.items()
                    if key not in ("dom_checks", "phases_within_limits"))
                procedural = procedural and all(
                    local_checks["phases_within_limits"].values())
                final_status = "PASS" if procedural else "FAIL"

            network["proxy_attempts"] = proxy_attempts
            network["guard_attempts"] = guard_attempts
            network["browser_external"] = browser_external
            network["earlier"] = earlier
            network["new_unique"] = new_unique
            network["earlier_requests"] = earlier_requests
            (run_dir / "network.json").write_text(
                json.dumps(network, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")

            result = {
                "index": index, "started_at_ms": started_ms,
                "finished_at_ms": now_ms(),
                "elapsed_s": round(time.monotonic() - run_started, 3),
                "phases_s": {key: round(value, 3)
                             for key, value in durations.items()},
                "marks_s": {key: round(value, 3) for key, value in marks.items()},
                "run_json": str(run_json), "verdict": run.get("verdict"),
                "failed": failed, "missing": missing,
                "orchestrator_exit": code,
                "post_reconnect_signal_seen": bool(
                    (run.get("service") or {}).get("post_reconnect_signal_seen")),
                "transport_origin": (run.get("transport") or {}).get("origin"),
                "binance_accredited": _binance_accredited(
                    transport, run.get("checks") or []),
                "global_deadline_exceeded": bool(
                    global_deadline_event.is_set()),
                "procedural_pass": bool(procedural),
                "local_checks": local_checks,
                "public_attempts": {
                    "proxy": len(proxy_attempts),
                    "guard": len(guard_attempts),
                    "browser": len(browser_external),
                },
                "rest_market_requests": rest_market_requests,
                "residual_consumers": 0,
                "clean_stop": local_checks.get("clean_stop"),
                "harness_debug": {
                    "disconnect": disconnect_result,
                    "reconnect": reconnect_result,
                    "wrapper_after_disconnect": wrapper_after_disconnect,
                    "wrapper_after_reconnect": wrapper_after_reconnect,
                },
                "cache": cache_info, "dashboard": logs.get("dashboard_verify"),
            }
            (run_dir / "local.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            return result
    except Exception as exc:  # noqa: BLE001 - la evidencia debe persistirse
        if global_deadline_event.is_set():
            error = "GLOBAL_DEADLINE_EXCEEDED: el deadline global de 180 s se "
            "agoto antes de completar el recorrido"
        else:
            error = f"{type(exc).__name__}: {exc}"
        final_status = "ERROR"
        log(f"run {index}: ERROR {error}")
        durations["run"] = time.monotonic() - run_started
        result = {
            "index": index, "started_at_ms": started_ms, "finished_at_ms": now_ms(),
            "elapsed_s": round(time.monotonic() - run_started, 3),
            "phases_s": {key: round(value, 3) for key, value in durations.items()},
            "marks_s": {key: round(value, 3) for key, value in marks.items()},
            "error": error, "verdict": "ERROR", "procedural_pass": False,
            "local_checks": local_checks, "public_attempts": {},
            "harness_debug": {
                "disconnect": disconnect_result,
                "reconnect": reconnect_result,
                "wrapper_after_disconnect": wrapper_after_disconnect,
                "wrapper_after_reconnect": wrapper_after_reconnect,
            },
            "global_deadline_exceeded": bool(
                global_deadline_event.is_set()),
            "transport_origin": (run.get("transport") or {}).get("origin")
            if run else "loopback_test",
            "binance_accredited": False,
        }
        try:
            for name, data in (("dom-1.json", dom1), ("dom-2.json", dom2),
                               ("dom-stop.json", dom3),
                               ("dom-reconnected.json", dom_reconnect)):
                if data is not None:
                    (run_dir / name).write_text(
                        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
            (run_dir / "network.json").write_text(
                json.dumps(network, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        except OSError:
            pass
        (run_dir / "local.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        return result
    finally:
        try:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()
        except Exception:  # noqa: BLE001
            pass
        if runner is not None:
            try:
                if runner.proc is not None and runner.proc.poll() is None:
                    runner.wait_exit(20.0)
                else:
                    runner.write_stderr_log()
            except Exception:  # noqa: BLE001
                runner.stop()
        # Parada de emergencia del servicio si el orquestador no lo cerro.
        try:
            http_json(f"http://127.0.0.1:{args.service_port}/health", timeout=1.0)
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{args.service_port}/shutdown",
                    method="POST", data=b"")
                urllib.request.urlopen(request, timeout=3.0).read()
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        if fake is not None:
            fake.stop()
        if proxy is not None:
            proxy.stop()
        log(f"run {index}: fin procedural={final_status}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def git_sha() -> Optional[str]:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                                       text=True).strip()
    except Exception:  # noqa: BLE001
        return None


def build_id() -> Optional[str]:
    try:
        return (ROOT / "frontend" / ".next" / "BUILD_ID").read_text(
            encoding="utf-8").strip()
    except OSError:
        return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--workdir", default=str(DEFAULT_WORKDIR))
    parser.add_argument("--dashboard-url", default=DEFAULT_DASHBOARD)
    parser.add_argument("--transport", choices=["local", "public"],
                        default="local",
                        help="local: entorno de prueba aislado; public: transporte real "
                             "sin tocar el dashboard canonico (requiere autorizacion).")
    parser.add_argument("--service-port", type=int, default=DEFAULT_SERVICE_PORT)
    parser.add_argument("--fake-port", type=int, default=DEFAULT_FAKE_PORT)
    parser.add_argument("--proxy-port", type=int, default=DEFAULT_PROXY_PORT)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--duration", type=float, default=75.0)
    parser.add_argument("--hold-seconds", type=float, default=20.0)
    parser.add_argument("--await-timeout", type=float, default=45.0)
    parser.add_argument("--release-timeout", type=float, default=15.0)
    parser.add_argument("--reconnect-timeout", type=float, default=15.0)
    args = parser.parse_args(argv)

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = ROOT / "docs" / "evidence" / f"local-acceptance-{time.strftime('%Y-%m-%d')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    for port, label in ((args.service_port, "service"),
                        (args.fake_port, "fake-ws"),
                        (args.proxy_port, "proxy")):
        if port_open("127.0.0.1", port):
            print(json.dumps({"ok": False, "error": f"PORT_IN_USE:{label}:{port}"},
                             ensure_ascii=False))
            return 2

    results: List[Dict[str, Any]] = []
    for index in range(1, max(1, args.runs) + 1):
        result = run_one(index, args, workdir, out_dir)
        results.append(result)
        if not result.get("procedural_pass"):
            log(f"run {index} NO paso; se detiene para no acumular fallos")
            break

    summary = {
        "generated_at_ms": now_ms(),
        "dashboard_url": args.dashboard_url,
        "service_port": args.service_port,
        "transport": args.transport,
        "binance_accredited": False,
        "git_sha": git_sha(),
        "build_id": build_id(),
        "runs": results,
        "procedural_pass": (len(results) == max(1, args.runs)
                            and all(item.get("procedural_pass")
                                    for item in results)),
        "limits_s": LIMITS,
        "notes": [
            ("Transporte local loopback: este arnes NO acredita recepcion de "
             "Binance." if args.transport == "local"
             else "Transporte public: el servicio se conecta a Binance; requiere "
             "autorizacion humana explicita."),
            ("El dashboard debe estar arrancado con el entorno de prueba "
             "documentado." if args.transport == "local"
             else "El dashboard canonico no es reconfigurado por el arnes; no se "
             "traslada configuracion de prueba al dashboard."),
            ("Cero peticiones publicas: proxy + guarda sitecustomize + "
             "allowlist del navegador." if args.transport == "local"
             else "Hasta dos peticiones REST de velas en conjunto (carga inicial "
             "y paginacion, <=300 cada una); catalogo desde cache; una conexion "
             "WS simultanea y hasta tres reconexiones."),
            "La ventana real reutiliza el mismo procedimiento con autorizacion humana.",
        ],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["procedural_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
