"""Ventana viva acotada de ``market-stream/v1`` por el camino real — PREPARADA, NO EJECUTADA.

Este script **no** construye otro servicio ni otro gestor: arranca el servicio
existente (``scripts/market_stream_service.py``) y se conecta a él como un
consumidor SSE más, de modo que la ventana recorre exactamente la misma cadena
que usa el navegador::

    Binance (wss publico) -> hub -> servicio SSE -> BFF (/api/v1/market-stream) -> /market-lab

Sin ``--execute`` solo imprime el plan (presupuesto, reglas de parada,
aceptacion, comandos y limpieza) y no abre ninguna conexion.

Con ``--execute`` (requiere autorizacion humana separada):

  * comprueba el preflight (puerto libre, dashboard servido, DBs canonicas);
  * arranca el servicio en ``--port`` (por defecto 8791, el que usa el BFF) y
    espera ``/health``; el socket de Binance NO se abre hasta que hay un
    consumidor;
  * abre un consumidor SSE directo al servicio por simbolo y uno a traves del
    BFF para el simbolo primario (el del grafico);
  * mide mensajes, vela provisional, cierre, vela siguiente, huecos,
    reconexiones, errores y crecimiento en disco;
  * captura ``/health`` antes de retirar consumidores y despues de retirarlos;
  * para el servicio y comprueba que no queda proceso, listener ni PID file;
  * escribe un JSON de evidencia con checks y veredicto.

El veredicto (``PASS`` / ``FAIL`` / ``UNKNOWN``) se calcula aparte de la
adquisicion. Cero mensajes o una cadena incompleta nunca producen ``PASS``.
La evidencia del navegador (DOM y revision visual) se captura por separado y se
incorpora con ``--finalize``; sin ella el veredicto es ``UNKNOWN``.

Uso::

    python -X utf8 scripts/market_stream_window.py
    python -X utf8 scripts/market_stream_window.py --execute --out docs/evidence/run.json
    python -X utf8 scripts/market_stream_window.py --finalize docs/evidence/run.json \
        --dom-first dom-1.json --dom-last dom-2.json --dom-after-stop dom-stop.json \
        --out docs/evidence/run.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.market_stream import (  # noqa: E402
    EXPLORABLE_INTERVALS,
    MAX_CONSUMERS_PER_STREAM,
    MAX_SUBSCRIPTIONS,
    RING_SIZE,
    STREAM_CONTRACT_VERSION,
    interval_ms,
)
from microstructure_probe.kline_btc_context import BTC_BENCHMARK_SYMBOL

SERVICE_SCRIPT = ROOT / "scripts" / "market_stream_service.py"
SERVICE_VERSION = "market-stream-service/v1"
VENUE = "binance"
MARKET_TYPE = "usd_m_futures"

DEFAULT_SYMBOLS = "BTCUSDT,MINAUSDT"
DEFAULT_INTERVAL = "1m"
DEFAULT_PORT = 8791
DEFAULT_DASHBOARD = "http://127.0.0.1:3020"
DEFAULT_DURATION_S = 180.0
DEFAULT_HOLD_S = 20.0
DEFAULT_MAX_MESSAGES = 1200
DEFAULT_MAX_EVENTS = 6000
DEFAULT_MAX_RECONNECTS = 3
DEFAULT_BARS = 300

CANONICAL_DBS = (
    Path("data") / "microprobe.db",
    Path("data") / "historical" / "historical.db",
)
CACHE_DB = Path("data") / "market-cache" / "market_cache.db"

#: Estados que declara el servicio (contrato MARKET_STREAM_CONTRACT_V1.md).
STATES = ("CONNECTING", "RECEIVING", "STALE", "DISCONNECTED", "RECOVERING")
ABORT_REASONS = {
    "MAX_RECONNECTS", "TRANSPORT_ENDED", "SERVICE_EXIT", "INTERRUPTED",
    "HEALTH_UNREACHABLE", "MAX_EVENTS", "BROWSER_NOT_ATTACHED",
}
HARD_FAIL_REASONS = {
    "PREFLIGHT_FAILED", "SERVICE_START_FAILED", "IDENTITY_MISMATCH",
    "SUBSCRIBE_FAILED", "BROWSER_NOT_ATTACHED",
}

ISO_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)")
AGE_RE = re.compile(r"hace\s+(\d+)\s*s")


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# utilidades de proceso / HTTP
# ---------------------------------------------------------------------------
def parse_symbols(raw: str) -> List[str]:
    out: List[str] = []
    for part in str(raw or "").split(","):
        symbol = part.strip().upper()
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def _host_header(url: str) -> str:
    return urlsplit(url).netloc or "127.0.0.1"


def _dashboard_endpoint(url: str) -> Tuple[str, int]:
    """Host/puerto reales del dashboard: el consumidor BFF del script debe
    hablar con la misma instancia que el navegador (no un 3020 fijo)."""
    parts = urlsplit(url)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return host, int(port)


def _service_env(base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Entorno del servicio conservando el PYTHONPATH existente.

    El arnes local antepone un directorio con `sitecustomize` que bloquea
    conexiones publicas; sobrescribir PYTHONPATH lo desactivaria en el hijo.
    """
    env = dict(os.environ if base is None else base)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (existing, str(ROOT / "src")) if part)
    return env


def hold_signal_ready(path: Optional[str]) -> bool:
    """Coordinacion por condicion: el arnes escribe el fichero tras capturar
    el DOM #2 y el script avanza sin esperar el maximo fijo."""
    if not path:
        return False
    try:
        return Path(path).exists()
    except OSError:
        return False


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, int(port))) == 0


def _http_request(url: str, *, method: str = "GET", timeout: float = 5.0,
                  headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    request = urllib.request.Request(url, method=method, data=(b"" if method == "POST" else None),
                                     headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            return {"ok": 200 <= response.status < 300, "status": response.status,
                    "text": raw, "error": None}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        return {"ok": False, "status": exc.code, "text": body, "error": None}
    except Exception as exc:  # noqa: BLE001 - red local
        return {"ok": False, "status": None, "text": "",
                "error": f"{type(exc).__name__}: {exc}"}


def _http_json(url: str, **kwargs: Any) -> Dict[str, Any]:
    result = _http_request(url, **kwargs)
    payload = None
    if result["text"]:
        try:
            payload = json.loads(result["text"])
        except ValueError:
            payload = None
    result["json"] = payload
    return result


def _file_state(path: Path) -> Dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "exists": False, "size": None, "mtime_ms": None}
    return {"path": str(path), "exists": True, "size": stat.st_size,
            "mtime_ms": int(stat.st_mtime * 1000)}


def _db_snapshot() -> Dict[str, Any]:
    return {
        "canonical": [_file_state(ROOT / path) for path in CANONICAL_DBS],
        "cache": _file_state(ROOT / CACHE_DB),
    }


def _iso_ms(text: str) -> Optional[int]:
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


# ---------------------------------------------------------------------------
# cliente SSE (solo consumo; no es un servicio)
# ---------------------------------------------------------------------------
class SseError(RuntimeError):
    pass


def _parse_sse_frame(frame: str) -> Optional[Tuple[str, Any]]:
    event = "message"
    data: List[str] = []
    for line in frame.split("\n"):
        if not line or line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)
    if not data:
        return None
    try:
        return event, json.loads("\n".join(data))
    except ValueError:
        return None


class SseClient:
    """Consumidor SSE sobre HTTP/1.1 (chunked o longitud conocida)."""

    def __init__(self, host: str, port: int, path: str, *, label: str,
                 host_header: Optional[str] = None, timeout: float = 20.0) -> None:
        self.host = host
        self.port = int(port)
        self.path = path
        self.label = label
        self.host_header = host_header or f"{host}:{port}"
        self.timeout = timeout
        self.status_line: Optional[str] = None
        self.headers: Dict[str, str] = {}
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._chunked = False
        self._remaining = 0

    async def open(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port, limit=2 ** 20)
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host_header}\r\n"
            "Accept: text/event-stream\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: keep-alive\r\n\r\n"
        )
        self._writer.write(request.encode("ascii"))
        await self._writer.drain()
        head = await asyncio.wait_for(self._reader.readuntil(b"\r\n\r\n"), self.timeout)
        text = head.decode("latin-1")
        self.status_line = text.split("\r\n", 1)[0]
        if " 200 " not in f"{self.status_line} ":
            raise SseError(f"HTTP {self.status_line}")
        for line in text.split("\r\n")[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                self.headers[key.strip().lower()] = value.strip()
        self._chunked = "chunked" in self.headers.get("transfer-encoding", "").lower()

    def close(self) -> None:
        try:
            if self._writer is not None:
                self._writer.close()
        except Exception:  # noqa: BLE001 - cierre defensivo
            pass
        self._writer = None
        self._reader = None

    async def events(self) -> Any:
        buffer = ""
        while True:
            chunk = await self._read_bytes()
            if chunk is None:
                return
            buffer = (buffer + chunk.decode("utf-8", "replace")).replace("\r\n", "\n")
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                parsed = _parse_sse_frame(frame)
                if parsed is not None:
                    yield parsed[0], parsed[1]

    async def _read_bytes(self) -> Optional[bytes]:
        assert self._reader is not None
        try:
            if not self._chunked:
                data = await asyncio.wait_for(self._reader.read(65536), self.timeout)
                return data or None
            if self._remaining == 0:
                line = await asyncio.wait_for(self._reader.readuntil(b"\r\n"), self.timeout)
                size = int(line.split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while True:
                        trailer = await asyncio.wait_for(
                            self._reader.readuntil(b"\r\n"), self.timeout)
                        if trailer == b"\r\n":
                            return None
                self._remaining = size
            data = await asyncio.wait_for(
                self._reader.readexactly(self._remaining), self.timeout)
            self._remaining = 0
            await asyncio.wait_for(self._reader.readexactly(2), self.timeout)
            return data
        except (asyncio.IncompleteReadError, ConnectionError):
            return None


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------
def _consumer_allocation(symbols: List[str], no_bff: bool,
                         browser: bool) -> Dict[str, Any]:
    """Reparto de consumidores: el navegador cuenta en el mismo presupuesto.

    Con BFF el simbolo primario se consume por el BFF (el mismo camino que usa
    el grafico) y el servicio directo atiende los secundarios; asi el total
    propio es 2 y con el navegador se llega a 3, sin duplicar el primario.

    Además se cuentan las SUSCRIPCIONES INTERNAS del contexto BTC
    compartido: por cada consumidor propio cuyo simbolo no es el benchmark,
    el servicio añade exactamente una suscripcion interna al benchmark
    (BTCUSDT) para sustentar el bloque ``context_btc``. El presupuesto
    declarado y el pico ``consumers`` de /health se comparan en la MISMA
    unidad (consumidores del hub), incluidas las internas.
    """
    service = (symbols if no_bff else (symbols[1:] or symbols[:1]))
    bff = [] if no_bff else symbols[:1]
    browser_consumers = 1 if browser else 0
    per_stream: Dict[str, int] = {}
    for symbol in service:
        per_stream[symbol] = per_stream.get(symbol, 0) + 1
    for symbol in bff:
        per_stream[symbol] = per_stream.get(symbol, 0) + 1
    for symbol in bff:
        per_stream[symbol] += browser_consumers
    internal_benchmark = sum(
        1 for symbol in service + bff if symbol != BTC_BENCHMARK_SYMBOL)
    if internal_benchmark:
        per_stream[BTC_BENCHMARK_SYMBOL] = (per_stream.get(
            BTC_BENCHMARK_SYMBOL, 0) + internal_benchmark)
    total = len(service) + len(bff) + browser_consumers + internal_benchmark
    return {
        "service": len(service),
        "bff": len(bff),
        "browser": browser_consumers,
        "internal_benchmark": internal_benchmark,
        "total": total,
        "service_symbols": service,
        "bff_symbols": bff,
        "per_stream": per_stream,
    }


def plan(args: argparse.Namespace) -> Dict[str, Any]:
    symbols = parse_symbols(args.symbols)
    interval = args.interval
    duration = float(args.duration)
    browser = bool(getattr(args, "browser_consumer", False))
    dashboard_url = str(getattr(args, "dashboard_url", DEFAULT_DASHBOARD)).rstrip("/")
    allocation = _consumer_allocation(symbols, bool(args.no_bff), browser)
    return {
        "contract_version": STREAM_CONTRACT_VERSION,
        "mode": "LIVE_WINDOW_PLAN" if not args.execute else "LIVE_WINDOW_EXECUTE",
        "authorization": ("REQUIERE AUTORIZACION HUMANA" if not args.execute
                          else "AUTORIZADA POR EL OPERADOR"),
        "chain": [
            "binance: wss://fstream.binance.com/market/stream?streams=... (una conexion combinada)",
            f"hub+servicio: {SERVICE_VERSION} en http://127.0.0.1:{args.port} (reutilizado, no recreado)",
            f"bff: {dashboard_url}/api/v1/market-stream (proxy SSE)",
            "grafico: /market-lab -> panel explorer-stream + vela provisional",
        ],
        "symbols": symbols,
        "interval": interval,
        "primary_symbol": symbols[0] if symbols else None,
        "transport": getattr(args, "base_url", None)
        or "wss://fstream.binance.com/market (por defecto)",
        "budget": {
            "duration_s": duration,
            "hold_after_acceptance_s": float(args.hold_seconds),
            "hold_signal": getattr(args, "hold_signal", None),
            "dashboard_url": dashboard_url,
            "max_messages": int(args.max_messages),
            "max_events": int(args.max_events),
            "max_reconnects": int(args.max_reconnects),
            "ws_connections": 1,
            "sse_consumers": allocation,
            "browser_consumers": allocation["browser"],
            "max_subscriptions": MAX_SUBSCRIPTIONS,
            "max_consumers_per_stream": MAX_CONSUMERS_PER_STREAM,
            "bars_per_consumer": DEFAULT_BARS,
            "await_browser_consumers": int(getattr(args, "await_consumers", 0) or 0),
            "await_browser_timeout_s": float(getattr(args, "await_timeout", 0) or 0),
            "release_browser": bool(getattr(args, "release_browser", False)),
            "release_timeout_s": float(getattr(args, "release_timeout", 0) or 0),
            "reconnect_timeout_s": float(getattr(args, "reconnect_timeout", 0) or 0),
            "rest": ("snapshot desde el almacen existente (allow_fetch=False); "
                     "paginacion manual 1 peticion <=1000 velas; reparacion de huecos "
                     "<=2 paginas x 500 velas y <=6/min"),
            "persistence": "NONE (anillo en memoria, 300 velas cerradas por stream)",
            "ring_size": RING_SIZE,
        },
        "stop_rules": [
            "aceptacion de cadena alcanzada (provisional+cierre+siguiente) tras la espera de captura",
            "duracion o max_messages/max_events alcanzados",
            "reconexiones > max_reconnects",
            "el navegador no se adjunta antes de abrir los consumidores propios "
            "(BROWSER_NOT_ATTACHED, sin contacto con Binance)",
            "identity_mismatch o simbolo/intervalo distinto del solicitado",
            "servicio caido o transporte sin consumidores",
            "cualquier senal de credenciales, orden o escritura en DB canonica",
        ],
        "acceptance": [
            "A1 identidad exacta venue=binance / market_type=usd_m_futures / symbol / interval",
            "A2 actualizaciones de la vela provisional (>=2 para la misma apertura)",
            "A3 cierre confirmado con close_time_ms == open_time_ms + intervalo - 1",
            "A4 aparicion de la vela siguiente (open_time == cerrada + intervalo)",
            "A5 LIVE solo con RECEIVING + socket + identidad + age <= fresh_ms",
            "A6 paginacion conserva historico (DOM: velas crecen, misma identidad)",
            "A7 servicio detenido: DOM pasa a DESCONECTADO, LIVE desaparece y el historico sigue visible",
            "A8 (--release-browser) consumidores=0 con el servicio vivo y reconexion=1 verificada",
        ],
        "browser_evidence": [
            "captura DOM #1 tras ver LIVE (snippet documentado, no inventado)",
            "captura DOM #2 tras el cambio de minuto y una paginacion",
            "captura DOM tras detener el servicio (<=40 s de reintentos)",
            "revision visual separada (opcional, nunca sustituye a DOM ni a Binance)",
        ],
        "metrics": [
            "mensajes por stream y simbolo; provisionales vs cerradas",
            "primera/ultima recepcion (ms UTC) y edad; cadencia medida por event_ms",
            "huecos detectados/reparados/parciales y contadores invalid/identity_mismatch",
            "reconexiones, ultimo error de socket y motivo de parada",
            "health antes de retirar consumidores y despues (queda solo el navegador)",
            "maximo de consumidores observado frente al presupuesto declarado",
            "tamano/mtime de DBs canonicas y cache antes/despues",
        ],
        "commands": {
            "plan": "python -X utf8 scripts/market_stream_window.py",
            "dashboard": "cd frontend; npm run start -- -p 3020  # instancia ya construida",
            "execute": ("python -X utf8 scripts/market_stream_window.py --execute "
                        "--out docs/evidence/market-stream-window-<fecha>.json"),
            "finalize": ("python -X utf8 scripts/market_stream_window.py --finalize "
                         "docs/evidence/market-stream-window-<fecha>.json "
                         "--dom-first dom-1.json --dom-last dom-2.json "
                         "--dom-after-stop dom-stop.json --out <mismo JSON>"),
            "cleanup": "python -X utf8 scripts/market_stream_service.py --port 8791 --stop",
        },
        "writes": "solo el JSON de evidencia (docs/evidence); sin DB canonica, sin cache, sin sesiones paper",
        "bot": "no arranca ni modifica el monitor; suscripcion canonica intacta",
    }


# ---------------------------------------------------------------------------
# checks puros (reutilizados por la ventana y por --finalize)
# ---------------------------------------------------------------------------
def _step_ms(interval: Optional[str]) -> Optional[int]:
    if not interval or interval not in EXPLORABLE_INTERVALS:
        return None
    return interval_ms(interval)


def provisional_counts(events: Iterable[Dict[str, Any]], symbol: str) -> Dict[int, int]:
    seen: Dict[int, set] = {}
    for event in events:
        if event.get("symbol") != symbol or event.get("closed") is not False:
            continue
        open_ms = event.get("open_time_ms")
        if not isinstance(open_ms, int):
            continue
        seen.setdefault(open_ms, set()).add(event.get("seq"))
    return {open_ms: len(values) for open_ms, values in seen.items()}


def stream_acceptance(service: Dict[str, Any], symbols: List[str],
                      interval: Optional[str]) -> Dict[str, Any]:
    events = service.get("events") or []
    primary = symbols[0] if symbols else None
    step = _step_ms(interval)
    counts = provisional_counts(events, primary or "")
    messages = sum(1 for e in events if e.get("symbol") == primary)
    provisional = max(counts.values()) if counts else 0

    closed = None
    if step:
        for event in events:
            if event.get("symbol") != primary or not event.get("closed"):
                continue
            open_ms = event.get("open_time_ms")
            close_ms = event.get("close_time_ms")
            if isinstance(open_ms, int) and close_ms == open_ms + step - 1:
                closed = event
                break
    following = None
    if closed is not None and step:
        for event in events:
            if event.get("symbol") != primary or event.get("closed") is not False:
                continue
            if event.get("open_time_ms") != closed["open_time_ms"] + step:
                continue
            seq, closed_seq = event.get("seq"), closed.get("seq")
            if isinstance(seq, int) and isinstance(closed_seq, int) and seq > closed_seq:
                following = event
                break

    return {
        "messages": messages,
        "provisional_max": provisional,
        "provisional_counts": counts,
        "close": closed,
        "following": following,
        "ok": bool(messages > 0 and provisional >= 2 and closed is not None
                   and following is not None),
        "closed_provisional": bool(closed is not None
                                   and counts.get(closed.get("open_time_ms"), 0) > 0),
    }


def _merge_consumers(run: Dict[str, Any]) -> Dict[str, Any]:
    """Une la evidencia de todos los consumidores SSE del script.

    Con ``--browser-consumer`` el primario llega por el BFF y el secundario por
    el servicio; sumar los dos estados (sin duplicar eventos) permite evaluar
    identidad, ciclo de vela, huecos y estado con una sola vista.
    """
    states = [state for state in (run.get("consumers") or {}).values()
              if isinstance(state, dict)]
    events: List[Dict[str, Any]] = []
    seen = set()
    for state in states:
        for event in state.get("events") or []:
            key = (event.get("symbol"), event.get("open_time_ms"),
                   event.get("closed"), event.get("seq"))
            if key in seen:
                continue
            seen.add(key)
            events.append(event)
    events.sort(key=lambda event: int(event.get("recv_ms") or 0))
    statuses = [(int(state.get("last_status_recv_ms") or 0), state.get("last_status"))
                for state in states if state.get("last_status")]
    statuses.sort(key=lambda item: item[0])
    firsts = [int(s["first_event_ms"]) for s in states if s.get("first_event_ms")]
    lasts = [int(s["last_event_ms"]) for s in states if s.get("last_event_ms")]
    return {
        "events": events,
        "hello": [item for state in states for item in (state.get("hello") or [])],
        "gaps": [item for state in states for item in (state.get("gaps") or [])],
        "last_status": statuses[-1][1] if statuses else None,
        "first_event_ms": min(firsts) if firsts else None,
        "last_event_ms": max(lasts) if lasts else None,
    }


LABEL_TO_STATE = {
    "CONECTANDO": "CONNECTING", "RECIBIENDO": "RECEIVING", "OBSOLETO": "STALE",
    "DESCONECTADO": "DISCONNECTED", "RECUPERANDO": "RECOVERING",
}


def _dom_metrics(dom: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(dom, dict):
        return None
    try:
        candles = int(dom.get("candles") or 0)
    except (TypeError, ValueError):
        candles = 0
    try:
        provisional = int(dom.get("provisional") or 0)
    except (TypeError, ValueError):
        provisional = 0
    updated = str(dom.get("updated") or "")
    match = ISO_RE.search(updated)
    age = AGE_RE.search(updated)
    state_text = str(dom.get("state") or "")
    state_code = next((code for label, code in LABEL_TO_STATE.items()
                       if state_text.startswith(label)), state_text)
    pagination = dom.get("pagination") if isinstance(dom.get("pagination"), dict) else {}
    return {
        "captured_at_ms": dom.get("captured_at_ms"),
        "url": dom.get("url"),
        "identity": str(dom.get("identity") or ""),
        "state": state_code,
        "state_text": state_text,
        "live": str(dom.get("live") or ""),
        "updated": updated,
        "updated_ms": _iso_ms(match.group(1)) if match else None,
        "age_ms": int(age.group(1)) * 1000 if age else None,
        "candles": candles,
        "provisional": provisional,
        "down": dom.get("down"),
        "error": dom.get("error"),
        "navigation_count": dom.get("navigation_count"),
        "reload_count": dom.get("reload_count"),
        "pagination": {
            "before": pagination.get("candles_before"),
            "after": pagination.get("candles_after"),
            "same_identity": pagination.get("same_identity"),
            "error": pagination.get("error"),
            "exhausted": bool(pagination.get("exhausted")),
        },
    }


def evaluate_acceptance(run: Dict[str, Any], dom: Optional[Dict[str, Any]] = None,
                        visual: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Calcula checks y veredicto. Funcion pura: no abre red ni escribe.

    ``dom`` contiene ``first``/``last``/``after`` (capturas del navegador) y
    ``errors`` (problemas al cargar la evidencia). Sin ellas el veredicto nunca
    puede ser ``PASS``.
    """
    dom = dom or {}
    target = run.get("target") or {}
    symbols = list(target.get("symbols") or [])
    interval = target.get("interval")
    primary = symbols[0] if symbols else None
    step = _step_ms(interval)
    budget = run.get("budget") or {}
    transport = run.get("transport") or {}
    service = _merge_consumers(run)
    bff = (run.get("consumers") or {}).get("bff")
    run_service = run.get("service") or {}
    acceptance = stream_acceptance(service, symbols, interval)
    events = service.get("events") or []
    stop_reason = run.get("stop_reason")
    aborted = stop_reason in ABORT_REASONS
    gaps = list(service.get("gaps") or [])
    unresolved_gaps = [g for g in gaps if g.get("status") in {"partial", "failed"}
                       or g.get("reason") == "BUFFER_OVERFLOW"]
    counters = (run_service.get("health_before_close") or {}).get("counters") or {}
    checks: List[Dict[str, Any]] = []

    def add(check_id: str, ok: Optional[bool], detail: str, *,
            required: bool = True, source: str = "script") -> None:
        checks.append({"id": check_id, "ok": ok, "required": required,
                       "source": source, "detail": detail})

    # --- cadena backend -------------------------------------------------
    add("preflight", run.get("preflight", {}).get("ok") is True,
        f"preflight={run.get('preflight', {}).get('error') or 'ok'}")
    add("service_started", run_service.get("started") is True,
        f"pid={run_service.get('pid')} port={run_service.get('port')}")
    before = run_service.get("health_before_consumer") or {}
    socket_before = before.get("socket") or before
    add("no_socket_without_consumer",
        socket_before.get("connected") is False
        and int(socket_before.get("attempts") or 0) == 0
        and int(before.get("consumers") or 0) == 0,
        f"connected={socket_before.get('connected')} "
        f"attempts={socket_before.get('attempts')}")
    samples = run_service.get("health_samples") or []
    add("socket_connected", any((s.get("connected") is True) for s in samples),
        f"muestras={len(samples)} conectadas="
        f"{sum(1 for s in samples if s.get('connected'))}")
    add("messages_primary", acceptance["messages"] > 0,
        f"simbolo={primary} eventos={acceptance['messages']}")
    if len(symbols) > 1:
        secondary = symbols[1]
        secondary_events = sum(1 for e in events if e.get("symbol") == secondary)
        add("messages_secondary", True if secondary_events > 0
            else (None if aborted else False),
            f"simbolo={secondary} eventos={secondary_events}")
    else:
        add("messages_secondary", None, "sin segundo simbolo", required=False)

    hello = service.get("hello") or []
    identities: Dict[str, Dict[str, Any]] = {}
    for item in hello:
        identity = item.get("identity") or {}
        if identity.get("symbol"):
            identities[str(identity["symbol"])] = identity
    identity_ok = bool(hello) and set(identities) == set(symbols)
    for symbol in symbols:
        identity = identities.get(symbol) or {}
        if (identity.get("venue") != VENUE
                or identity.get("market_type") != MARKET_TYPE
                or identity.get("interval") != interval):
            identity_ok = False
    stray = sorted({e.get("symbol") for e in events
                    if e.get("symbol") not in symbols or e.get("interval") != interval})
    add("identity_exact", identity_ok and not stray,
        f"hello={sorted(identities)} fuera_de_identidad={stray}")
    identity_errors = int((counters or {}).get("identity_mismatch") or 0)
    invalid = int((counters or {}).get("invalid") or 0)
    add("no_protocol_errors", bool(run_service.get("health_before_close"))
        and identity_errors == 0 and invalid == 0,
        f"identity_mismatch={identity_errors} invalid={invalid}")

    lifecycle_state = True if acceptance["ok"] else (None if aborted else False)
    add("provisional_updates", True if acceptance["provisional_max"] >= 2
        else (None if aborted else False),
        f"max_actualizaciones_misma_apertura={acceptance['provisional_max']}")
    add("close_confirmed", True if acceptance["close"] else
        (None if aborted else False),
        f"close_time_ms/candle={(acceptance['close'] or {}).get('open_time_ms')}")
    add("next_candle", True if acceptance["following"] else
        (None if aborted else False),
        f"next_open_ms={(acceptance['following'] or {}).get('open_time_ms')}")
    live_seen = bool((service.get("last_status") or {}).get("live") is True)
    for sample in samples:
        for stream in sample.get("streams") or []:
            if stream.get("live") is True and stream.get("state") == "RECEIVING":
                live_seen = True
    add("live_status_seen", live_seen,
        f"ultimo_estado={((service.get('last_status') or {}).get('connection') or {}).get('state')}")

    bff_required = bool(budget.get("bff"))
    if bff_required:
        bff_counts = (bff or {}).get("counts") or {}
        bff_events = int(bff_counts.get("candle") or 0) + int(bff_counts.get("closed") or 0)
        bff_hello = (bff or {}).get("hello") or []
        bff_identity = (bff_hello[0].get("identity") if bff_hello else {}) or {}
        bff_snapshot = (bff or {}).get("snapshot")
        bff_ok = bool(bff) and bff_identity.get("symbol") == primary \
            and bff_identity.get("interval") == interval \
            and bff_snapshot is not None and bff_events > 0
        add("bff_delivered", bff_ok,
            f"eventos_vela={bff_events} identidad={bff_identity.get('symbol')}/"
            f"{bff_identity.get('interval')}")
    else:
        add("bff_delivered", None, "BFF deshabilitado (--no-bff)", required=True)

    add("coverage_intact", not unresolved_gaps,
        f"huecos={len(gaps)} sin_resolver="
        f"{[g.get('status') or g.get('reason') for g in unresolved_gaps]}")

    after_close = run_service.get("health_after_close") or {}
    release_browser = bool(budget.get("release_browser"))
    expected_after = 0 if release_browser else int(budget.get("browser_consumers") or 0)
    add("consumers_released", bool(after_close)
        and int(after_close.get("consumers") or 0) == expected_after,
        f"consumers_tras_cerrar={after_close.get('consumers')} esperado={expected_after}")
    if release_browser:
        reconnected = run_service.get("health_after_reconnect") or {}
        released = bool(after_close) and int(after_close.get("consumers") or 0) == 0
        add("browser_reconnected", released and bool(reconnected)
            and int(reconnected.get("consumers") or 0) == 1,
            f"liberado={released} consumers_tras_cerrar={after_close.get('consumers')} "
            f"consumers_tras_reconectar={reconnected.get('consumers')} esperado=1")
    else:
        add("browser_reconnected", None,
            "no aplica (sin --release-browser)", required=False)
    declared = int((budget.get("sse_consumers") or {}).get("total") or 0)
    peak = max([int(s.get("consumers") or 0) for s in samples]
               + [int(before.get("consumers") or 0),
                  int((run_service.get("health_before_close") or {}).get("consumers") or 0)]
               + [0])
    before_close_consumers = int(
        (run_service.get("health_before_close") or {}).get("consumers") or 0)
    budget_ok = peak <= declared
    if int(budget.get("browser_consumers") or 0) > 0:
        budget_ok = budget_ok and before_close_consumers == declared
    add("consumer_budget", budget_ok,
        f"pico={peak} declarado={declared} antes_de_cerrar={before_close_consumers}")
    stopped = run_service.get("after_stop") or {}
    add("service_stopped", bool(stopped.get("process_exited"))
        and bool(stopped.get("port_closed")) and bool(stopped.get("pidfile_removed")),
        f"exited={stopped.get('process_exited')} port_closed={stopped.get('port_closed')} "
        f"pidfile_removed={stopped.get('pidfile_removed')}")
    storage = run.get("storage") or {}
    add("canonical_dbs_unchanged", bool(storage.get("canonical_dbs_unchanged")),
        f"cambiadas={storage.get('canonical_changed')}")
    add("transport_origin", transport.get("origin") == "binance",
        f"origen={transport.get('origin')} base_url={transport.get('base_url')}",
        required=False)

    # --- cadena navegador (DOM) ----------------------------------------
    first = _dom_metrics(dom.get("first"))
    last = _dom_metrics(dom.get("last"))
    after = _dom_metrics(dom.get("after"))
    dom_identity = lambda item: bool(item) and (  # noqa: E731
        "Binance USD-M" in item["identity"] and primary is not None
        and primary in item["identity"] and f"· {interval} ·" in item["identity"])

    add("dom_identity", None if not (first and last) else
        dom_identity(first) and dom_identity(last),
        "identidad DOM no disponible" if not (first and last) else
        f"first={first['identity']!r} last={last['identity']!r}", source="browser")
    add("dom_state_live", None if not (first and last) else
        (first["state"] == "RECEIVING" and first["live"] == "LIVE"
         and last["state"] == "RECEIVING" and last["live"] == "LIVE"),
        "estados DOM no disponibles" if not (first and last) else
        f"first={first['state']}/{first['live']} last={last['state']}/{last['live']}",
        source="browser")

    finished = run.get("finished_at_ms") or now_ms()
    first_event_ms = service.get("first_event_ms")
    fresh = None
    if first and last and first["updated_ms"] and last["updated_ms"]:
        fresh = (last["updated_ms"] >= first["updated_ms"]
                 and last["updated_ms"] <= finished + 5000
                 and (first_event_ms is None or first["updated_ms"] >= first_event_ms - 5000)
                 and (last["age_ms"] is None or last["age_ms"] <= 15000))
    add("dom_update_fresh", fresh, "sin marca de actualizacion parseable" if fresh is None else
        f"first={first['updated_ms']} last={last['updated_ms']} age_ms={last['age_ms']}",
        source="browser")
    close_event = acceptance["close"] or {}
    brackets_close = None
    if first and last and first["updated_ms"] and last["updated_ms"] \
            and isinstance(close_event.get("recv_ms"), int):
        brackets_close = (first["updated_ms"] <= close_event["recv_ms"]
                          <= last["updated_ms"])
    grew = None
    if first and last:
        if not brackets_close:
            grew = None
        else:
            grew = last["candles"] > first["candles"] and last["provisional"] >= 1
    add("dom_candles_grew", grew,
        "sin capturas" if not (first and last) else
        ("las capturas no rodean el cierre" if grew is None else
         f"{first['candles']}->{last['candles']} provisional={last['provisional']}"),
        source="browser")
    pagination = (last or {}).get("pagination") or {}
    if last and first and not pagination.get("before") and not pagination.get("after"):
        pagination = first.get("pagination") or {}
    pag_ok = None
    if last:
        try:
            before_n = int(pagination.get("before") or 0)
            after_n = int(pagination.get("after") or 0)
            grew_or_exhausted = (after_n > before_n
                                 or (bool(pagination.get("exhausted")) and after_n >= before_n))
            pag_ok = (grew_or_exhausted and pagination.get("same_identity") is True
                      and not pagination.get("error"))
        except (TypeError, ValueError):
            pag_ok = False
    add("dom_pagination_preserved", pag_ok,
        f"antes={pagination.get('before')} despues={pagination.get('after')} "
        f"misma_identidad={pagination.get('same_identity')} error={pagination.get('error')} "
        f"agotado={bool(pagination.get('exhausted'))}",
        source="browser")
    nav_ok = None
    if first and last:
        nav_ok = (first.get("navigation_count") == 1 and last.get("navigation_count") == 1
                  and (last.get("reload_count") == 0) and (first.get("reload_count") == 0))
    add("dom_no_reload", nav_ok,
        "sin capturas" if nav_ok is None else
        f"nav={last.get('navigation_count')} reload={last.get('reload_count')}",
        source="browser")
    add("dom_after_stop", None if not (last and after) else
        (after["state"] == "DISCONNECTED" and after["live"] == "no LIVE"
         and after["candles"] >= last["candles"] and dom_identity(after)
         and bool(after.get("down"))),
        "sin captura posterior" if not (last and after) else
        f"estado={after['state_text']!r} live={after['live']!r} "
        f"velas={after['candles']} aviso={bool(after.get('down'))}", source="browser")

    # --- veredicto ------------------------------------------------------
    failed = [c["id"] for c in checks if c["required"] and c["ok"] is False]
    missing = [c["id"] for c in checks if c["required"] and c["ok"] is None]
    dom_errors = list(dom.get("errors") or [])
    if failed:
        verdict = "FAIL"
    elif missing:
        verdict = "UNKNOWN"
    else:
        verdict = "PASS"
    reasons = [f"CHECK_FAILED:{item}" for item in failed]
    reasons += [f"EVIDENCE_MISSING:{item}" for item in missing]
    reasons += dom_errors
    if verdict == "PASS" and lifecycle_state is not True:
        verdict = "UNKNOWN"
        reasons.append("LIFECYCLE_INCOMPLETE")

    acquisition_finished = (lifecycle_state is True and acceptance["messages"] > 0
                            and bool(stopped.get("process_exited")))

    return {
        "checks": checks,
        "failed": failed,
        "missing": missing,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "acquisition_finished": acquisition_finished,
        "stop_reason": stop_reason,
        "visual_review": (visual or {}).get("review") or "NOT_REVIEWED",
        "visual_screenshots": (visual or {}).get("screenshots") or [],
    }


# ---------------------------------------------------------------------------
# ejecucion de la ventana
# ---------------------------------------------------------------------------
def _progress(message: str) -> None:
    print(f"[window] {message}", file=sys.stderr, flush=True)


def _compact_health(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not payload:
        return {}
    socket_state = payload.get("socket") or {}
    streams = [{
        "symbol": item.get("symbol"),
        "interval": item.get("interval"),
        "consumers": item.get("consumers"),
        "state": item.get("state"),
        "live": item.get("live"),
        "age_ms": item.get("age_ms"),
        "gaps": item.get("gaps"),
        "recoveries": item.get("recoveries"),
    } for item in payload.get("streams") or []]
    return {
        "connected": socket_state.get("connected"),
        "attempts": socket_state.get("attempts"),
        "reconnects": socket_state.get("reconnects"),
        "last_error": socket_state.get("last_error"),
        "consumers": payload.get("consumers"),
        "streams": streams,
        "counters": payload.get("counters") or {},
        "generated_at_ms": payload.get("generated_at_ms"),
    }


async def _preflight(args: argparse.Namespace) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False, "error": None,
                           "port_free": not _port_open(args.host, args.port),
                           "dashboard": None, "build": None, "db_before": _db_snapshot()}
    if not out["port_free"]:
        out["error"] = f"PORT_IN_USE:{args.port}"
        return out
    if args.no_bff:
        out["dashboard"] = {"skipped": True}
        out["ok"] = True
        return out
    base = args.dashboard_url.rstrip("/")
    host = _host_header(base)
    status = await asyncio.to_thread(
        _http_json, f"{base}/api/v1/market-stream/status", headers={"Host": host})
    out["dashboard"] = {"status": status["status"], "error": status["error"],
                        "available": (status.get("json") or {}).get("available")
                        if isinstance(status.get("json"), dict) else None}
    if status["status"] != 200:
        out["error"] = "DASHBOARD_UNREACHABLE"
        return out
    page = await asyncio.to_thread(_http_request, f"{base}/market-lab",
                                   headers={"Host": host})
    build_file = ROOT / "frontend" / ".next" / "BUILD_ID"
    file_build = build_file.read_text(encoding="utf-8").strip() if build_file.exists() else None
    out["build"] = {"file": file_build, "page_status": page["status"],
                    "served": (file_build in page["text"]) if (file_build and page["ok"]) else None}
    if not out["build"]["served"]:
        out["error"] = "BUILD_MISMATCH"
        return out
    out["ok"] = True
    return out


async def _pump(client: SseClient, queue: "asyncio.Queue[Tuple[str, str, Any, int]]") -> None:
    try:
        async for event, payload in client.events():
            await queue.put((client.label, event, payload, now_ms()))
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - transporte local
        await queue.put((client.label, "transport_error",
                         {"detail": f"{type(exc).__name__}: {exc}"[:300]}, now_ms()))
    finally:
        await queue.put((client.label, "transport_closed", {}, now_ms()))


def _new_consumer_state() -> Dict[str, Any]:
    return {"hello": [], "snapshot": None, "snapshots": {}, "events": [], "gaps": [],
            "last_status": None, "last_status_recv_ms": None,
            "counts": {"candle": 0, "closed": 0, "status": 0,
                       "heartbeat": 0, "gap": 0, "error": 0},
            "first_event_ms": None, "last_event_ms": None, "errors": []}


def _apply_event(state: Dict[str, Any], event: str, payload: Any, recv_ms: int,
                 keep_events: bool) -> None:
    if event in ("candle", "closed"):
        state["counts"][event] += 1
        state["first_event_ms"] = state["first_event_ms"] or recv_ms
        state["last_event_ms"] = recv_ms
        if keep_events:
            state["events"].append({
                "event": event, "recv_ms": recv_ms,
                "symbol": payload.get("symbol"), "interval": payload.get("interval"),
                "open_time_ms": payload.get("open_time_ms"),
                "close_time_ms": payload.get("close_time_ms"),
                "closed": event == "closed" or payload.get("closed") is True,
                "event_ms": payload.get("event_ms"),
                "received_ms": payload.get("received_ms"),
                "seq": payload.get("seq"),
            })
    elif event == "hello":
        state["hello"].append({"recv_ms": recv_ms,
                               "identity": payload.get("identity") or {},
                               "policy": payload.get("policy") or {},
                               "limits": payload.get("limits") or {}})
    elif event == "snapshot":
        summary = {
            "recv_ms": recv_ms,
            "symbol": payload.get("symbol"), "interval": payload.get("interval"),
            "candles": len(payload.get("candles") or []),
            "observed": payload.get("observed") or {},
            "coverage": payload.get("coverage") or {},
            "volume_available": bool((payload.get("volume") or {}).get("available")),
            "source": payload.get("source"),
        }
        state["snapshot"] = summary
        state["snapshots"][str(payload.get("symbol"))] = summary
    elif event == "gap":
        state["counts"]["gap"] += 1
        state["gaps"].append({key: payload.get(key) for key in (
            "symbol", "interval", "reason", "status", "expected_from_ms",
            "expected_to_ms", "recovered_bars", "missing", "requests", "detail")})
    elif event == "status":
        state["counts"]["status"] += 1
        state["last_status"] = payload
        state["last_status_recv_ms"] = recv_ms
    elif event == "heartbeat":
        state["counts"]["heartbeat"] += 1
    elif event == "error":
        state["counts"]["error"] += 1
        state["errors"].append({"recv_ms": recv_ms, "payload": payload})
    elif event == "transport_error":
        state["errors"].append({"recv_ms": recv_ms, "payload": payload})
    if event not in ("status", "heartbeat"):
        state["last_event_ms"] = recv_ms


def _db_changes(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    changed = []
    for old, new in zip(before.get("canonical") or [], after.get("canonical") or []):
        if (old.get("size"), old.get("mtime_ms")) != (new.get("size"), new.get("mtime_ms")):
            changed.append(new.get("path"))
    cache_before = before.get("cache") or {}
    cache_after = after.get("cache") or {}
    return {
        "canonical_dbs_unchanged": not changed,
        "canonical_changed": changed,
        "cache_changed": (cache_before.get("size"), cache_before.get("mtime_ms"))
        != (cache_after.get("size"), cache_after.get("mtime_ms")),
        "before": before, "after": after,
    }


async def _wait_health(base_url: str, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = await asyncio.to_thread(_http_json, f"{base_url}/health", timeout=3.0)
        if result["ok"] and isinstance(result.get("json"), dict):
            return result["json"]
        await asyncio.sleep(0.25)
    return None


def consumer_wait_ready(payload: Optional[Dict[str, Any]], expected: int,
                        primary: Optional[str]) -> Optional[bool]:
    """El navegador esta adjunto y en el simbolo primario.

    ``None`` = el payload no detalla streams (se acepta el conteo). Exigir que
    el unico consumidor sea el primario evita arrancar durante el cambio de
    contrato del operador (MINAUSDT transitorio) y mantiene el pico en 3.
    """
    if not isinstance(payload, dict):
        return False
    if int(payload.get("consumers") or 0) != expected:
        return False
    streams = payload.get("streams")
    if not isinstance(streams, list) or not streams:
        return None
    active = [item for item in streams if int(item.get("consumers") or 0) > 0]
    if len(active) != expected:
        return False
    return all(item.get("symbol") == primary for item in active)


async def run_window(args: argparse.Namespace) -> Dict[str, Any]:
    symbols = parse_symbols(args.symbols)
    started = now_ms()
    base_url = f"http://{args.host}:{args.port}"
    run: Dict[str, Any] = {
        "contract_version": STREAM_CONTRACT_VERSION,
        "mode": "LIVE_WINDOW_EXECUTE",
        "authorization": "AUTORIZADA POR EL OPERADOR",
        "started_at_ms": started,
        "finished_at_ms": None,
        "duration_s": None,
        "target": {"symbols": symbols, "interval": args.interval,
                   "primary": symbols[0] if symbols else None,
                   "bars": DEFAULT_BARS, "port": args.port},
        "transport": {
            "origin": "loopback_test" if args.base_url else "binance",
            "base_url": args.base_url,
        },
        "budget": plan(args)["budget"] | {"bff": not args.no_bff},
        "preflight": {},
        "service": {"pid": None, "port": args.port, "started": False,
                    "health_before_consumer": None, "health_samples": [],
                    "browser_wait": None, "health_after_browser_wait": None,
                    "health_before_close": None, "health_after_close": None,
                    "health_after_reconnect": None,
                    "after_stop": None, "stderr_tail": None},
        "consumers": {},
        "stop_reason": None,
        "storage": {},
        "limitations": [
            "una ventana de pocos minutos no generaliza al universo ni a otros intervalos",
            "la cadencia se mide, no se asume (la documentacion publica es contradictoria)",
            "el DOM se captura por el operador; sin esa evidencia el veredicto es UNKNOWN",
            "la revision visual es evidencia distinta y no prueba por si sola la cadena",
            "no valida rentabilidad, senal, indicadores ni ejecucion",
        ],
    }
    stops = run["service"]
    proc: Optional[asyncio.subprocess.Process] = None
    clients: List[SseClient] = []
    pumps: List[asyncio.Task] = []
    queue: "asyncio.Queue[Tuple[str, str, Any, int]]" = asyncio.Queue()
    stop_reason = "INTERRUPTED"
    health_failures = 0

    class _Abort(RuntimeError):
        """Salida controlada: el veredicto se calcula despues del cierre."""

    try:
        preflight = await _preflight(args)
        run["preflight"] = preflight
        if not preflight["ok"]:
            stop_reason = "PREFLIGHT_FAILED"
            raise _Abort
        if args.base_url and not re.match(
                r"^ws://(127\.0\.0\.1|localhost)(:\d+)?(/|$)", args.base_url):
            stop_reason = "INVALID_BASE_URL"
            raise _Abort
        if args.base_url:
            _progress("AVISO: transporte loopback de prueba; este JSON NO acredita "
                      "recepcion de Binance")

        env = _service_env()
        safety = float(args.duration) + float(args.hold_seconds) + 60.0
        argv = [sys.executable, "-X", "utf8", str(SERVICE_SCRIPT),
                "--port", str(args.port), "--max-seconds", str(safety)]
        if args.base_url:
            argv.extend(["--transport", "local", "--base-url", args.base_url])
        else:
            # Ventana public: desactivar recuperacion REST para respetar el
            # presupuesto compartido de max 2 solicitudes de velas. Cualquier
            # hueco de cobertura impide PASS (check coverage_intact).
            argv.extend(["--transport", "public", "--no-recovery"])
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=str(ROOT), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stops["pid"] = proc.pid
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=20.0)
        except asyncio.TimeoutError:
            line = b""
        try:
            banner = json.loads(line.decode("utf-8", "replace") or "{}")
        except ValueError:
            banner = {}
        stops["banner"] = banner
        health = await _wait_health(base_url)
        if health is None:
            stderr = b""
            try:
                stderr = await asyncio.wait_for(proc.stderr.read(4096), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            stops["stderr_tail"] = stderr.decode("utf-8", "replace")[-1000:]
            stop_reason = "SERVICE_START_FAILED"
            raise _Abort
        stops["started"] = True
        stops["health_before_consumer"] = _compact_health(health)
        _progress(f"servicio PID {proc.pid} en {base_url}; "
                  f"socket.connected={stops['health_before_consumer'].get('connected')}")

        await_consumers = int(getattr(args, "await_consumers", 0) or 0)
        if await_consumers > 0:
            wait: Dict[str, Any] = {"expected": await_consumers, "samples": [],
                                    "ok": False, "waited_ms": None}
            wait_started = time.monotonic()
            await_timeout = float(getattr(args, "await_timeout", 90.0) or 0)
            wait_deadline = wait_started + await_timeout
            stable = 0
            while time.monotonic() < wait_deadline:
                probe = await asyncio.to_thread(_http_json, f"{base_url}/health", timeout=3.0)
                payload = probe.get("json") if probe["ok"] else None
                observed = (int((payload or {}).get("consumers") or 0)
                            if isinstance(payload, dict) else None)
                ready = consumer_wait_ready(payload, await_consumers, symbols[0])
                wait["samples"].append({
                    "t_ms": now_ms(),
                    "consumers": observed,
                    "streams": [{"symbol": item.get("symbol"),
                                 "consumers": item.get("consumers")}
                                for item in ((payload or {}).get("streams") or [])]
                    if isinstance(payload, dict) else [],
                    "ready": ready,
                })
                if ready is not False:
                    stable += 1
                    if stable >= 2:
                        wait["ok"] = True
                        break
                else:
                    stable = 0
                await asyncio.sleep(1.0)
            wait["waited_ms"] = int((time.monotonic() - wait_started) * 1000)
            stops["browser_wait"] = wait
            if not wait["ok"]:
                _progress(f"el navegador no se adjunto en {await_timeout:.0f} s: "
                          "se para antes de abrir consumidores propios")
                stop_reason = "BROWSER_NOT_ATTACHED"
                raise _Abort
            _progress(f"navegador adjunto (consumers={await_consumers}); "
                      f"abriendo consumidores propios")
            stops["health_after_browser_wait"] = _compact_health(
                (await asyncio.to_thread(_http_json, f"{base_url}/health", timeout=3.0)).get("json"))

        run["consumers"]["service"] = _new_consumer_state()
        service_symbols = _consumer_allocation(
            symbols, bool(args.no_bff), bool(getattr(args, "browser_consumer", False))
        )["service_symbols"]
        for symbol in service_symbols:
            client = SseClient(args.host, args.port,
                               f"/stream?symbol={symbol}&interval={args.interval}"
                               f"&bars={DEFAULT_BARS}", label="service")
            try:
                await client.open()
            except (SseError, OSError) as exc:
                run["consumers"]["service"]["errors"].append(
                    {"recv_ms": now_ms(), "payload": {"detail": f"{symbol}: {exc}"}})
                stop_reason = "SUBSCRIBE_FAILED"
                raise _Abort
            clients.append(client)
        if not args.no_bff:
            primary = symbols[0]
            bff_state = _new_consumer_state()
            run["consumers"]["bff"] = bff_state
            bff_host, bff_port = _dashboard_endpoint(args.dashboard_url)
            client = SseClient(bff_host, bff_port,
                               f"/api/v1/market-stream?symbol={primary}"
                               f"&interval={args.interval}&bars={DEFAULT_BARS}",
                               label="bff", host_header=_host_header(args.dashboard_url))
            try:
                await client.open()
                clients.append(client)
            except (SseError, OSError) as exc:
                bff_state["errors"].append(
                    {"recv_ms": now_ms(), "payload": {"detail": f"bff: {exc}"}})
        _progress("consumidores SSE abiertos: "
                  + ", ".join(sorted({c.label for c in clients}))
                  + f"; espera de captura {int(args.hold_seconds)} s tras aceptar")

        pumps = [asyncio.create_task(_pump(client, queue)) for client in clients]
        deadline = time.monotonic() + float(args.duration)
        next_health = 0.0
        accepted_at: Optional[float] = None
        hold_signal = getattr(args, "hold_signal", None)
        processed = 0
        stop_reason = "DURATION"

        while True:
            try:
                label, event, payload, recv_ms = await asyncio.wait_for(
                    queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                label = None
            if label is not None:
                state = run["consumers"].setdefault(label, _new_consumer_state())
                _apply_event(state, event, payload, recv_ms, keep_events=True)
                if event in ("candle", "closed"):
                    processed += 1
                if event in ("hello", "candle", "closed"):
                    identity = (payload.get("identity") if event == "hello"
                                else {"symbol": payload.get("symbol"),
                                      "interval": payload.get("interval")})
                    if (identity.get("symbol") and identity.get("symbol") not in symbols) or \
                            (identity.get("interval") and identity.get("interval") != args.interval):
                        stop_reason = "IDENTITY_MISMATCH"
                        break

            now = time.monotonic()
            if now >= next_health:
                next_health = now + 2.0
                result = await asyncio.to_thread(_http_json, f"{base_url}/health", timeout=3.0)
                if result["ok"] and isinstance(result.get("json"), dict):
                    health_failures = 0
                    sample = _compact_health(result["json"])
                    sample["t_ms"] = now_ms()
                    stops["health_samples"].append(sample)
                    if int(sample.get("reconnects") or 0) > int(args.max_reconnects):
                        stop_reason = "MAX_RECONNECTS"
                        break
                else:
                    health_failures += 1
                    if health_failures >= 5:
                        stop_reason = "HEALTH_UNREACHABLE"
                        break

            if proc.returncode is not None:
                stop_reason = "SERVICE_EXIT"
                break
            if processed >= int(args.max_messages):
                stop_reason = "MAX_MESSAGES"
                break
            total = sum(int(value) for state in run["consumers"].values()
                        for value in (state.get("counts") or {}).values())
            if total >= int(args.max_events):
                stop_reason = "MAX_EVENTS"
                break

            bff_counts = ((run["consumers"].get("bff") or {}).get("counts") or {})
            bff_updates = (int(bff_counts.get("candle") or 0)
                           + int(bff_counts.get("closed") or 0))
            if accepted_at is None \
                    and stream_acceptance(_merge_consumers(run), symbols,
                                          args.interval)["ok"] \
                    and (args.no_bff or bff_updates > 0):
                accepted_at = now
                _progress("ACEPTACION DE CADENA ALCANZADA (provisional + cierre + "
                          f"siguiente); captura el DOM ahora: quedan "
                          f"{int(args.hold_seconds)} s")
            if accepted_at is not None:
                signal_ready = hold_signal_ready(hold_signal)
                elapsed = now - accepted_at
                if signal_ready or elapsed >= float(args.hold_seconds):
                    stops["hold_signal_seen"] = signal_ready
                    stops["hold_elapsed_ms"] = int(elapsed * 1000)
                    stop_reason = "ACCEPTANCE_REACHED"
                    break
            if now >= deadline:
                stop_reason = "DURATION"
                break
            if pumps and all(pump.done() for pump in pumps):
                stop_reason = "TRANSPORT_ENDED"
                break

        # Evidencia antes de retirar consumidores, y despues de retirarlos.
        stops["health_before_close"] = _compact_health(
            (await asyncio.to_thread(_http_json, f"{base_url}/health", timeout=4.0)).get("json"))
        for client in clients:
            client.close()
        release_browser = bool(getattr(args, "release_browser", False))
        expected_after_close = 0 if release_browser else (
            1 if getattr(args, "browser_consumer", False) else 0)
        release_limit = (float(getattr(args, "release_timeout", 0) or 30.0)
                         if release_browser else 8.0)
        if release_browser:
            _progress("desconecta la suscripcion del navegador ahora; "
                      "esperando consumers=0 con el servicio vivo")
        release_started = time.monotonic()
        health_after = {}
        while time.monotonic() - release_started < release_limit:
            candidate = await asyncio.to_thread(_http_json, f"{base_url}/health", timeout=4.0)
            health_after = _compact_health(candidate.get("json"))
            if int(health_after.get("consumers") or 0) == expected_after_close:
                break
            await asyncio.sleep(0.25)
        stops["health_after_close"] = health_after
        stops["release_wait_ms"] = int((time.monotonic() - release_started) * 1000)
        stops["consumers_expected_after_close"] = expected_after_close
        stops["consumers_released"] = int(
            (stops["health_after_close"] or {}).get("consumers") or 0) == expected_after_close
        _progress(f"parada: {stop_reason}; consumidores_tras_cerrar="
                  f"{(stops['health_after_close'] or {}).get('consumers')} "
                  f"(esperado {expected_after_close})")
        if release_browser:
            _progress("reconecta la suscripcion del navegador ahora; "
                      "esperando consumers=1")
            reconnect_limit = float(getattr(args, "reconnect_timeout", 0) or 30.0)
            reconnect_started = time.monotonic()
            health_reconnect = {}
            while time.monotonic() - reconnect_started < reconnect_limit:
                candidate = await asyncio.to_thread(
                    _http_json, f"{base_url}/health", timeout=4.0)
                health_reconnect = _compact_health(candidate.get("json"))
                if int(health_reconnect.get("consumers") or 0) == 1:
                    break
                await asyncio.sleep(0.25)
            stops["health_after_reconnect"] = health_reconnect
            stops["reconnect_wait_ms"] = int(
                (time.monotonic() - reconnect_started) * 1000)
            stops["consumers_reconnected"] = int(
                (stops["health_after_reconnect"] or {}).get("consumers") or 0) == 1
            _progress("consumidores_tras_reconectar="
                      f"{(stops['health_after_reconnect'] or {}).get('consumers')} "
                      "(esperado 1)")
            post_signal = getattr(args, "post_reconnect_signal", None)
            if post_signal and stops.get("consumers_reconnected"):
                hold_started = time.monotonic()
                held = False
                while time.monotonic() - hold_started < reconnect_limit:
                    if Path(post_signal).exists():
                        held = True
                        break
                    await asyncio.sleep(0.1)
                stops["post_reconnect_signal_seen"] = held
                stops["post_reconnect_hold_ms"] = int(
                    (time.monotonic() - hold_started) * 1000)
    except _Abort:
        pass
    except asyncio.CancelledError:
        stop_reason = "INTERRUPTED"
        raise
    except Exception as exc:  # noqa: BLE001 - la evidencia debe persistirse igual
        stop_reason = "WINDOW_ERROR"
        run["error"] = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        for pump in pumps:
            pump.cancel()
        if pumps:
            await asyncio.gather(*pumps, return_exceptions=True)
        for client in clients:
            client.close()
        if proc is not None:
            shutdown = await asyncio.to_thread(_http_request, f"{base_url}/shutdown",
                                               method="POST", timeout=5.0)
            stops["shutdown"] = {"status": shutdown["status"], "error": shutdown["error"]}
        exited = False
        if proc is not None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=10.0)
                exited = proc.returncode is not None
            except asyncio.TimeoutError:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                    exited = True
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    exited = True
            if proc.stderr is not None:
                try:
                    tail = await asyncio.wait_for(proc.stderr.read(4096), timeout=1.0)
                    stops["stderr_tail"] = tail.decode("utf-8", "replace")[-1000:]
                except asyncio.TimeoutError:
                    pass
        closed = False
        for _ in range(20):
            if not _port_open(args.host, args.port):
                closed = True
                break
            await asyncio.sleep(0.25)
        pid_path = Path(os.environ.get("MICROPROBE_MARKET_STREAM_PID")
                        or (ROOT / "data" / "market-stream" / "service.json"))
        health_after = await asyncio.to_thread(_http_request, f"{base_url}/health", timeout=2.0)
        stops["after_stop"] = {
            "process_exited": exited,
            "exit_code": proc.returncode if proc is not None else None,
            "port_closed": closed,
            "pidfile_removed": not pid_path.exists(),
            "health_refused": health_after["status"] is None,
        }
        run["storage"] = _db_changes(run.get("preflight", {}).get("db_before") or {},
                                     _db_snapshot())
    return _close_run(run, stop_reason, args)


def _close_run(run: Dict[str, Any], stop_reason: str, args: argparse.Namespace) -> Dict[str, Any]:
    finished = now_ms()
    run["stop_reason"] = stop_reason
    run["finished_at_ms"] = finished
    run["duration_s"] = round((finished - int(run.get("started_at_ms") or finished)) / 1000, 2)
    run["target"]["cadence"] = _cadence(_merge_consumers(run))
    dom, visual = _load_browser_evidence(
        getattr(args, "dom_first", None), getattr(args, "dom_last", None),
        getattr(args, "dom_after_stop", None), getattr(args, "visual_review", None),
        getattr(args, "screenshot", None))
    evaluation = evaluate_acceptance(run, dom, visual)
    run.update({key: evaluation[key] for key in (
        "checks", "failed", "missing", "verdict", "verdict_reasons",
        "acquisition_finished", "visual_review", "visual_screenshots")})
    return run


def _cadence(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    events = (state or {}).get("events") or []
    by_open: Dict[Tuple[str, int], List[int]] = {}
    for event in events:
        if event.get("closed") is True:
            continue
        if not isinstance(event.get("event_ms"), int):
            continue
        by_open.setdefault((event.get("symbol"), event.get("open_time_ms")), []).append(
            event["event_ms"])
    deltas: List[int] = []
    for values in by_open.values():
        values.sort()
        deltas.extend(b - a for a, b in zip(values, values[1:]) if b > a)
    if not deltas:
        return {"updates": 0, "median_delta_ms": None, "min_delta_ms": None,
                "max_delta_ms": None}
    deltas.sort()
    return {"updates": len(deltas), "median_delta_ms": deltas[len(deltas) // 2],
            "min_delta_ms": deltas[0], "max_delta_ms": deltas[-1]}


def _read_json(path: Optional[str]) -> Any:
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_browser_evidence(first: Optional[str], last: Optional[str],
                           after: Optional[str], review: Optional[str],
                           screenshots: Optional[List[str]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    errors: List[str] = []
    dom: Dict[str, Any] = {"errors": errors}
    for key, path in (("first", first), ("last", last), ("after", after)):
        if not path:
            continue
        payload = _read_json(path)
        if not isinstance(payload, dict):
            errors.append(f"DOM_EVIDENCE_INVALID:{key}")
            continue
        dom[key] = payload
    missing = [key for key in ("first", "last", "after") if key not in dom]
    if missing:
        errors.append("DOM_EVIDENCE_MISSING:" + ",".join(missing))
    visual: Dict[str, Any] = {"review": "NOT_REVIEWED", "screenshots": []}
    if review in ("pass", "fail"):
        visual["review"] = "PASS" if review == "pass" else "FAIL"
        for path in screenshots or []:
            if Path(path).exists():
                visual["screenshots"].append(path)
            else:
                errors.append(f"VISUAL_SCREENSHOT_MISSING:{path}")
    return dom, visual


def finalize(args: argparse.Namespace) -> int:
    path = Path(args.finalize)
    run = _read_json(str(path))
    if not isinstance(run, dict):
        print(json.dumps({"ok": False, "error": "EVIDENCE_NOT_READABLE",
                          "path": str(path)}, ensure_ascii=False))
        return 1
    dom, visual = _load_browser_evidence(
        args.dom_first, args.dom_last, args.dom_after_stop,
        args.visual_review, args.screenshot)
    evaluation = evaluate_acceptance(run, dom, visual)
    run.update({key: evaluation[key] for key in (
        "checks", "failed", "missing", "verdict", "verdict_reasons",
        "acquisition_finished", "visual_review", "visual_screenshots")})
    run["finalized_at_ms"] = now_ms()
    out = Path(args.out or str(path))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True, "written": str(out), "verdict": run["verdict"],
        "acquired": run["acquisition_finished"], "reasons": run["verdict_reasons"],
        "failed": run["failed"], "missing": run["missing"],
        "visual_review": run["visual_review"],
    }, ensure_ascii=False, indent=2))
    return _exit_code(run["verdict"])


def _exit_code(verdict: str) -> int:
    return {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}.get(verdict, 2)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ventana viva acotada market-stream/v1 por el camino real")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS,
                        help="uno del trio canonico y otro elegible fuera del trio")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_S)
    parser.add_argument("--hold-seconds", type=float, default=DEFAULT_HOLD_S,
                        help="maximo tras aceptar para capturar el DOM; con "
                             "--hold-signal se avanza al aparecer el fichero")
    parser.add_argument("--max-messages", type=int, default=DEFAULT_MAX_MESSAGES)
    parser.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS)
    parser.add_argument("--max-reconnects", type=int, default=DEFAULT_MAX_RECONNECTS)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--dashboard-url", default=DEFAULT_DASHBOARD)
    parser.add_argument("--base-url", default=None,
                        help="solo pruebas controladas: ws://127.0.0.1:PUERTO "
                             "(nunca acredita Binance)")
    parser.add_argument("--no-bff", action="store_true",
                        help="omite el BFF (el veredicto nunca podra ser PASS)")
    parser.add_argument("--browser-consumer", action="store_true",
                        help="el navegador ocupa uno de los 3 consumidores SSE; "
                             "deja libre su plaza y esperalo antes de abrir los propios")
    parser.add_argument("--await-consumers", type=int, default=0,
                        help="espera a que /health muestre N consumidores antes de "
                             "abrir los del script (0 = no espera)")
    parser.add_argument("--await-timeout", type=float, default=90.0,
                        help="segundos maximos de espera del navegador")
    parser.add_argument("--release-browser", action="store_true",
                        help="tras cerrar los consumidores propios espera a que el "
                             "navegador se desconecte (consumers=0) y reconecte "
                             "(consumers=1) antes de parar el servicio")
    parser.add_argument("--release-timeout", type=float, default=30.0,
                        help="segundos maximos esperando consumers=0")
    parser.add_argument("--reconnect-timeout", type=float, default=30.0,
                        help="segundos maximos esperando consumers=1 tras reconectar")
    parser.add_argument("--hold-signal", default=None,
                        help="fichero de coordinacion: al existir se avanza sin "
                             "esperar el maximo de --hold-seconds (lo escribe el arnes)")
    parser.add_argument("--post-reconnect-signal", default=None,
                        help="fichero de coordinacion: tras consumers=1 el servicio "
                             "sigue vivo hasta que exista (captura DOM de reconexion)")
    parser.add_argument("--out", default=None, help="ruta JSON de evidencia")
    parser.add_argument("--execute", action="store_true",
                        help="abre la conexion real (requiere autorizacion)")
    parser.add_argument("--finalize", default=None,
                        help="recalcula el veredicto de un JSON ya adquirido")
    parser.add_argument("--dom-first", default=None)
    parser.add_argument("--dom-last", default=None)
    parser.add_argument("--dom-after-stop", default=None)
    parser.add_argument("--visual-review", choices=["pass", "fail", "not-reviewed"],
                        default=None)
    parser.add_argument("--screenshot", action="append", default=None)
    args = parser.parse_args(argv)

    if args.finalize:
        return finalize(args)
    if not args.execute:
        print(json.dumps(plan(args), ensure_ascii=False, indent=2))
        return 0

    if not args.out:
        parser.error("--execute requiere --out (la evidencia debe persistirse)")
    try:
        run = asyncio.run(run_window(args))
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "INTERRUPTED"}, ensure_ascii=False))
        return 130
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": run.get("stop_reason") not in HARD_FAIL_REASONS,
        "written": str(out), "stop_reason": run.get("stop_reason"),
        "duration_s": run.get("duration_s"), "verdict": run.get("verdict"),
        "acquired": run.get("acquisition_finished"),
        "transport": (run.get("transport") or {}).get("origin"),
        "reasons": run.get("verdict_reasons"),
    }, ensure_ascii=False, indent=2))
    return _exit_code(run.get("verdict") or "UNKNOWN")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
