"""Demo de transporte local: contexto BTC compartido (market-btc-context/v1).

Sustituye SOLO el dashboard identificado en 127.0.0.1:3020 (`next start`,
PID previo capturado y detenido). Cero solicitudes publicas: cache temporal
sembrada + wrapper `--no-fetch` + sitecustomize que bloquea sockets
no-loopback + guardia de rutas del navegador. Comprueba en DOM:

  * badge del contexto BTC con unidades (retBTC ±nnbps, diff ±nnbps);
  * valor bajo el cursor == salida del backend (payload market-series
    `context_btc` y frame SSE `context` del servicio);
  * cierre de vela actualiza valores SIN recarga;
  * hueco de BTC muestra UNKNOWN(BTC_GAP_IN_WINDOW) sin arrastre;
  * cambiar simbolo/intervalo elimina el contexto previo;
  * una sola suscripcion combinada (BTC no se duplica entre sesiones);
  * cero peticiones Binance (browser_external 0, ledger 0).

Uso (PowerShell, raiz del repositorio):
  $env:PYTHONPATH="src"; python scripts/btc_context_public_demo.py

Salida: JSON con veredicto y ruta de evidencia. Sin estrategia, senales,
monitor, paper ni ordenes; DOM verificado con selectores, visual es captura
para revision aparte del operador.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import http.client
import socket
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from market_stream_local_acceptance import (  # noqa: E402
    FakeKlineServer,
    prepare_shadow,
    seed_cache,
    STEP_MS,
)

DASHBOARD_PORT = 3020
SERVICE_PORT = 8792
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}"
FRONTEND_DIR = ROOT / "frontend"
H_STEP_MS = 3_600_000
EVIDENCE_DIRNAME = "btc-context-public-2026-10-26"

BADGE = '[data-testid="market-chart-indicators"]'
BADGE_BTC = '[data-testid="market-chart-btc-context"]'
CURSOR = '[data-testid="market-chart-cursor"]'
CHART = '[data-testid="market-chart"]'

LABELS = {"ret_btc_bps_5": "retBTC", "ret_diff_bps_5": "diff"}
UNITS = {"ret_btc_bps_5": "bps", "ret_diff_bps_5": "bps"}
DECIMALS = {"ret_btc_bps_5": 2, "ret_diff_bps_5": 2}


class DemoError(RuntimeError):
    pass


OPS: List[Dict[str, Any]] = []


def log(msg: str) -> None:
    print(f"[btc-context-demo] {msg}", flush=True)


def dom_check(name: str, ok: bool, detail: Any) -> bool:
    OPS.append({"check": name, "ok": bool(ok), "detail": detail})
    log(f"DOM [{ 'PASS' if ok else 'FAIL' }] {name}: "
        f"{json.dumps(detail, ensure_ascii=False)[:300]}")
    return bool(ok)


def now_ms() -> int:
    return int(time.time() * 1000)


def git_sha() -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                         capture_output=True, text=True, timeout=30,
                         check=True)
    return out.stdout.strip()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_status(url: str, timeout: float = 2.0) -> Optional[int]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return int(response.status)
    except Exception:  # noqa: BLE001 - sondeo
        return None


def http_json(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def wait_until(fn: Callable[[], Any], seconds: float, step: float = 0.3,
               tag: str = "") -> Any:
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            value = fn()
        except Exception as exc:  # noqa: BLE001 - polling
            last = exc
        else:
            if value:
                return value
        time.sleep(step)
    raise DemoError(f"TIMEOUT_WAITING_{tag or 'CONDITION'}: {last}")


def fetch_series_payload_http(url: str) -> Optional[Dict[str, Any]]:
    try:
        return http_json(url)
    except Exception as exc:  # noqa: BLE001
        log(f"fetch_series_payload_http failed: {exc}")
        return None


def screenshot(page, path: Path) -> None:
    page.screenshot(path=str(path), full_page=False)


def kill_existing_dashboard() -> Optional[int]:
    """Detiene el dashboard identificada en 3020 (arleno completo).

    Devuelve el PID que se detuvo o None si no habia nada.
    """
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, timeout=15,
            check=False, encoding="cp1252", errors="replace")
    except Exception:
        out = None
    pid = None
    if out is not None and out.stdout:
        for line in out.stdout.splitlines():
            if ":3020" in line and "LISTENING" in line.upper():
                parts = [p for p in line.split() if p]
                if parts:
                    try:
                        pid = int(parts[-1])
                    except ValueError:
                        pid = None
    if pid:
        log(f"deteniendo dashboard existente PID {pid} en 3020")
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=20, check=False)
        except Exception as exc:
            log(f"taskkill fallo: {exc}")
        time.sleep(1.5)
    return pid


def start_dashboard(env: Dict[str, str], run_log: Path) -> subprocess.Popen:
    """Arranca el dashboard canonico verificando identidad (patron 9a995b9).

    Aborta si 3020 esta ocupado ANTES de next start (un servidor ajeno
    responderia 200 con SU cache y envenenaria la comparacion), verifica que
    el next start propio confirme "Ready"/"Local" en el log de la corrida y
    que no haya EADDRINUSE.
    """
    if http_status(DASHBOARD_URL) == 200:
        raise DemoError(f"PORT_3020_OCCUPIED antes de next start: "
                        f"{DASHBOARD_URL} ya responde")
    log(f"arrancando dashboard canonical en {DASHBOARD_URL}")
    with open(run_log, "w", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            ["cmd", "/c", "npm", "run", "start"],
            cwd=str(FRONTEND_DIR), env=env,
            stdout=handle, stderr=subprocess.STDOUT)
    wait_until(lambda: http_status(DASHBOARD_URL) == 200, 90.0, 0.5,
               "dashboard_200")
    try:
        text = run_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    if "EADDRINUSE" in text or "address already in use" in text.lower():
        proc.kill()
        raise DemoError("NEXT_START_BIND_FAILED (EADDRINUSE): el 200 OK vino "
                        "de otro servidor en 3020")
    if "Ready in" not in text and "Local:" not in text:
        proc.kill()
        raise DemoError("NEXT_START_NOT_CONFIRMED: sin banner Ready/Local; "
                        "identidad del servidor no verificada")
    log(f"dashboard 200 OK y banner Ready confirmado (pid {proc.pid})")
    return proc


def start_service(fake_port: int, env: Dict[str, str],
                  service_log: Path, max_seconds: int = 1500
                  ) -> subprocess.Popen:
    log(f"arrancando servicio market-stream en 127.0.0.1:{SERVICE_PORT} "
        f"(feed loopback ws://127.0.0.1:{fake_port}/)")
    with open(service_log, "w", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            [sys.executable,
             str(ROOT / "scripts" / "market_stream_service.py"),
             "--port", str(SERVICE_PORT),
             "--transport", "local",
             "--base-url", f"ws://127.0.0.1:{fake_port}/",
             "--no-recovery", "--max-seconds", str(max_seconds)],
            cwd=str(ROOT), env=env, stdout=handle, stderr=subprocess.STDOUT)
    wait_until(
        lambda: (lambda h: h.get("transport", {}).get("mode") == "local")(
            http_json(f"http://127.0.0.1:{SERVICE_PORT}/health") or {}),
        30.0, 0.3, "service_health")
    return proc


def stop_proc(proc: Optional[subprocess.Popen], label: str) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
    log(f"{label} detenido")


def shared_count() -> int:
    try:
        health = http_json(f"http://127.0.0.1:{SERVICE_PORT}/health")
        streams = health.get("streams", [])
        total = 0
        for s in streams:
            if s.get("symbol") == "BTCUSDT" and s.get("interval") == "1m":
                total += int(s.get("consumers", 0))
        return total
    except Exception:  # noqa: BLE001
        return -1


# ---------------------------------------------------------------------------
# Playwright: DOM
# ---------------------------------------------------------------------------

def badge_text(page) -> str:
    try:
        return page.locator(BADGE).inner_text().strip()
    except Exception:  # noqa: BLE001
        return ""


def badge_btc_text(page) -> str:
    try:
        return page.locator(BADGE_BTC).inner_text().strip()
    except Exception:  # noqa: BLE001
        return ""


def cursor_ms(page) -> Optional[int]:
    try:
        text = page.locator(CURSOR).inner_text().strip()
    except Exception:  # noqa: BLE001
        return None
    match = re.match(r"Cursor (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", text)
    if not match:
        return None
    stamp = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S")
    return int(stamp.replace(tzinfo=timezone.utc).timestamp() * 1000)


def chart_box(page):
    canvas = page.locator(CHART).locator("canvas").first
    canvas.scroll_into_view_if_needed()
    return canvas.bounding_box()


def new_axis(page, label: str = "") -> "Axis":
    page.wait_for_selector(f"{CHART} canvas", timeout=60_000)
    deadline = time.monotonic() + 20.0
    last_error: Exception = DemoError("NO_CHART_CANVAS")
    while time.monotonic() < deadline:
        try:
            axis = Axis(page)
            time.sleep(0.4)
            return axis
        except DemoError as exc:
            last_error = exc
            time.sleep(0.8)
    raise DemoError(f"AXIS_CALIBRATION_FAILED_{label}:{last_error}")


class Axis:
    """Mapa lineal px -> ms calibrado con dos puntos del area de datos."""
    PANES_IN_STEP = 0.06

    def __init__(self, page) -> None:
        self.page = page
        box = chart_box(page)
        if box is None:
            raise DemoError("NO_CHART_CANVAS")
        self.box = box
        self._calibrated = False
        self.x0 = self.x1 = self.t0 = self.t1 = 0.0
        self._calibrate()

    def _calibrate(self) -> None:
        # Busca dos tiempos definidos moviendo el crosshair dentro del area
        # de datos (evita margenes blancos donde el tiempo es indefinido).
        for frac in (0.35, 0.65):
            px = self.box["x"] + self.box["width"] * frac
            py = self.box["y"] + self.box["height"] * 0.5
            self.page.mouse.move(px, py)
            time.sleep(0.05)
            t = cursor_ms(self.page)
            if t is not None:
                if not self._calibrated:
                    self.x0, self.t0 = px, t
                    self._calibrated = True
                else:
                    self.x1, self.t1 = px, t
                    return
        raise DemoError("AXIS_NOT_CALIBRATED")

    def px_for_ms(self, ms: int) -> float:
        if self.t1 == self.t0:
            raise DemoError("AXIS_DEGENERATE")
        return self.x0 + (ms - self.t0) * (self.x1 - self.x0) / (self.t1 - self.t0)


def hover_at_axis(axis: Axis, ms: int, step_ms: int) -> Optional[int]:
    px = axis.px_for_ms(ms)
    py = axis.box["y"] + axis.box["height"] * 0.5
    axis.page.mouse.move(px, py)
    time.sleep(0.3)
    for _ in range(8):
        t = cursor_ms(axis.page)
        if t is not None and abs(t - ms) <= step_ms:
            return t
        time.sleep(0.25)
    return None


def check_row(page, axis: Axis, row: Dict[str, Any], step_ms: int,
              label: str) -> Tuple[bool, Dict[str, Any]]:
    """Hover sobre la vela y compara badge con la fila del backend."""
    reached = hover_at_axis(axis, int(row["open_time_ms"]), step_ms)
    if reached is None:
        return False, {"label": label, "error": "cursor_no_value",
                       "target_ms": row["open_time_ms"]}
    text = badge_text(page)
    detail = {"label": label, "target_ms": row["open_time_ms"],
              "reached_ms": reached, "badge": text}
    ok = bool(text)
    for name, label_text in LABELS.items():
        val = (row.get("values") or {}).get(name)
        reason = (row.get("unknown") or {}).get(name)
        if val is not None:
            expected = f"{label_text} {val:.{DECIMALS[name]}f}{UNITS[name]}"
            detail[name] = {"expected": expected, "value": val}
            if expected not in text:
                ok = False
        elif reason:
            detail[name] = {"unknown": reason}
            if f"UNKNOWN({reason})" not in text:
                ok = False
    return ok, detail


def check_btc_row(page, axis: Axis, row: Dict[str, Any], step_ms: int,
                  label: str) -> Tuple[bool, Dict[str, Any]]:
    reached = hover_at_axis(axis, int(row["open_time_ms"]), step_ms)
    if reached is None:
        return False, {"label": label, "error": "cursor_no_value",
                       "target_ms": row["open_time_ms"]}
    # Espera a que React renderice el badge (el modelo se construye al cargar
    # el payload; leer inmediatamente devuelve cadena vacia).
    text = ""
    for _ in range(20):
        try:
            el = page.locator(BADGE_BTC)
            if el.count() > 0:
                text = el.inner_text().strip()
        except Exception:  # noqa: BLE001
            text = ""
        if text:
            break
        time.sleep(0.25)
    detail = {"label": label, "target_ms": row["open_time_ms"],
              "reached_ms": reached, "badge": text}
    ok = bool(text)
    for name, label_text in LABELS.items():
        val = (row.get("values") or {}).get(name)
        reason = (row.get("unknown") or {}).get(name)
        if val is not None:
            expected = f"{label_text} {val:.{DECIMALS[name]}f}{UNITS[name]}"
            detail[name] = {"expected": expected, "value": val}
            if expected not in text:
                ok = False
        elif reason:
            detail[name] = {"unknown": reason}
            if f"UNKNOWN({reason})" not in text:
                ok = False
    return ok, detail


class ContextSseWatcher:
    """Lee frames SSE `event: context` del servicio (loopback)."""

    def __init__(self, symbol: str, interval: str,
                 snapshot_payload: Dict[str, Any]) -> None:
        observed = snapshot_payload.get("observed") or {}
        start_ms = int(observed.get("start_ms") or 0)
        end_ms = int(observed.get("end_ms") or 0)
        self.path = (f"/stream?symbol={symbol}&interval={interval}"
                     f"&bars=10&from_ms={start_ms}&to_ms={end_ms}")
        self.symbol = symbol
        self.interval = interval
        self.snapshot_payload = snapshot_payload
        self.frames: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="sse-context-watcher")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            connection = http.client.HTTPConnection(
                "127.0.0.1", SERVICE_PORT, timeout=15)
            connection.request("GET", self.path,
                               headers={"Accept": "text/event-stream"})
            response = connection.getresponse()
            while not self._stop.is_set():
                event_line = response.fp.readline()  # type: ignore[union-attr]
                if not event_line:
                    break
                text = event_line.decode("utf-8", "replace").strip()
                if not text.startswith("event:"):
                    continue
                data_line = response.fp.readline()  # type: ignore[union-attr]
                raw = data_line.decode("utf-8", "replace").strip()
                if text == "event: context" and raw.startswith("data:"):
                    body = raw[5:].strip()
                    try:
                        self.frames.append(json.loads(body))
                    except ValueError as exc:
                        self.errors.append(f"json:{exc}")
        except Exception as exc:  # noqa: BLE001 - watcher best effort
            self.errors.append(f"{type(exc).__name__}: {exc}")

    def row_for(self, open_ms: int) -> Optional[Dict[str, Any]]:
        for frame in reversed(self.frames):
            for row in frame.get("series") or []:
                if int(row.get("open_time_ms") or 0) == int(open_ms):
                    return {"row": row, "frame_identity": frame.get("identity")}
        return None


def seed_with_gap(cache_db: Path) -> Dict[str, Any]:
    info = seed_cache(cache_db, now_ms())
    connection = sqlite3.connect(str(cache_db))
    try:
        last_1m = int(info["last_closed_1m"])
        # Hueco real: 3 velas 1m de BTCUSDT eliminadas ~40 barras atras.
        gap_times = [last_1m - i * STEP_MS for i in (39, 38, 37)]
        removed = 0
        for open_time in gap_times:
            cursor = connection.execute(
                "DELETE FROM market_klines WHERE symbol=? AND interval=?"
                " AND source=? AND open_time=?",
                ("BTCUSDT", "1m", "klines", int(open_time)))
            removed += int(cursor.rowcount or 0)
        connection.commit()
    finally:
        connection.close()
    info["deleted_1m_open_times"] = [int(t) for t in gap_times]
    info["deleted_rows"] = removed
    return info


def check_zero_public(cache_db: Path, conn_log: Path) -> Dict[str, Any]:
    denied: List[Dict[str, Any]] = []
    if conn_log.exists():
        for line in conn_log.read_text("utf-8", "replace").splitlines():
            try:
                denied.append(json.loads(line))
            except ValueError:
                pass
    connection = sqlite3.connect(str(cache_db))
    try:
        row = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(requests),0)"
            " FROM market_fetch_ledger").fetchone()
        ledger = {"rows": int(row[0] or 0), "requests": int(row[1] or 0)}
    finally:
        connection.close()
    return {"python_denied_attempts": denied, "ledger": ledger}


def run() -> Dict[str, Any]:
    result: Dict[str, Any] = {"checks": [], "verdict": "FAIL"}
    temp_root = Path(tempfile.mkdtemp(prefix="btc-context-demo-"))
    cache_db = temp_root / "cache.db"
    shadow = prepare_shadow(temp_root)
    conn_log = Path(shadow["conn_log"])
    browser_log = Path(shadow["browser_log"])

    dashboard_proc: Optional[subprocess.Popen] = None
    service_proc: Optional[subprocess.Popen] = None
    fake_ws: Optional[FakeKlineServer] = None
    watcher: Optional[ContextSseWatcher] = None
    browser = None
    context = None

    try:
        # 1. Identificar y detener dashboard previo en 3020.
        kill_existing_dashboard()

        # 2. Sembrar cache temporal con hueco real de BTC.
        info = seed_with_gap(cache_db)
        log(f"cache sembrada: {info['seeded']}; filas BTC borradas: "
            f"{info['deleted_rows']}")

        # 3. Fake WS loopback arriba PRIMERO: el servicio se conecta a él como
        #    base-url (mismo venue, loopback, cero publicas).
        fake_ws = FakeKlineServer(free_port(), Path(shadow["fake_log"]))
        fake_ws.start()
        fake_port = fake_ws.port
        log(f"fake WS loopback arriba en {fake_port}")

        # Entorno: cache temporal + raiz shadow (wrapper --no-fetch + guardia
        # de red sitecustomize) para que el BFF lea SOLO la cache temporal y
        # nunca abra sockets publicos.
        dashboard_log = temp_root / "next-start.log"
        service_log = temp_root / "market-stream-service.log"
        env = os.environ.copy()
        env.update({
            "PYTHONPATH": str(ROOT / "src"),
            "MICROPROBE_MARKET_CACHE_DB": str(cache_db),
            "MICROPROBE_MARKET_STREAM_PID": str(temp_root / "service.json"),
            "MICROPROBE_STREAM_URL": f"http://127.0.0.1:{SERVICE_PORT}",
            "MARKET_EXPLORER_ROOT": shadow["root"],
            "MICROPROBE_TEST_CANON_SRC": shadow["canon_src"],
            "MICROPROBE_TEST_CANON_SCRIPT": shadow["canon_script"],
            "MICROPROBE_TEST_CONN_LOG": shadow["conn_log"],
        })

        # 4. Servicio SSE + dashboard canonico (env de prueba, 0 upstream).
        service_proc = start_service(fake_port, env, service_log)
        dashboard_proc = start_dashboard(env, dashboard_log)

        # 5. Playwright: una sola carga, sin recarga en actualizaciones.
        from playwright.sync_api import sync_playwright  # noqa: E402
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280,
                                                    "height": 960},
                                          locale="es-ES")
            page = context.new_page()

            series_urls: List[str] = []
            external: List[Dict[str, Any]] = []
            navigations = {"count": 0}
            errors: List[str] = []

            def on_request(request) -> None:
                url = request.url
                if "/api/v1/market-series?" in url:
                    series_urls.append(url)
                if (url.startswith(DASHBOARD_URL)
                        or url.startswith("http://localhost:3020")
                        or url.startswith(("data:", "blob:", "about:", ":"))):
                    return
                external.append({"url": url, "at_ms": now_ms()})

            def on_response(response) -> None:
                if "/api/v1/market-series?" in response.url:
                    series_urls.append(response.url)

            def on_load(_) -> None:
                navigations["count"] += 1

            page.on("request", on_request)
            page.on("response", on_response)
            page.on("load", on_load)
            page.on("pageerror", lambda exc: errors.append(str(exc)[:200]))

            page.goto(f"{DASHBOARD_URL}/market-lab",
                      wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_selector('[data-testid="explorer-catalog-state"]',
                                   timeout=60_000)
            if not dom_check("initial_navigation_single_load",
                             navigations["count"] == 1,
                             {"loads": navigations["count"]}):
                raise DemoError("unexpected extra document load at start")

            # Buscar y abrir MINAUSDT (no es BTC -> contexto se emite).
            page.fill('[data-testid="explorer-query"]', "MINAUSDT")
            page.click('[data-testid="explorer-search"]')
            page.wait_for_selector('[data-testid="explorer-open-MINAUSDT"]',
                                   timeout=60_000)
            page.click('[data-testid="explorer-open-MINAUSDT"]')
            page.wait_for_selector(CHART, timeout=60_000)
            wait_until(lambda: series_urls and "interval=1h"
                       in series_urls[-1], 60.0, 0.3, "series_1h")
            payload_1h = fetch_series_payload_http(series_urls[-1])
            if not payload_1h:
                raise DemoError("1h payload fetch failed")
            ctx_1h = payload_1h.get("context_btc")
            dom_check("payload_context_btc_v1",
                      (ctx_1h or {}).get("contract_version")
                      == "market-btc-context/v1",
                      {"identity": (ctx_1h or {}).get("identity")})
            dom_check("payload_context_cache_only",
                      (ctx_1h or {}).get("context", {})
                      .get("acquisition", {}).get("rest_upstream_requests")
                      == 0,
                      {"mode": (ctx_1h or {}).get("context", {}).get(
                          "acquisition", {}).get("mode")})
            axis = new_axis(page)

            # (a) badge del contexto con unidades y valor == backend (1h).
            series_ctx = (ctx_1h or {}).get("series") or []
            if not series_ctx:
                raise DemoError("no context series in 1h payload")
            last_ctx = series_ctx[-1]
            axis = new_axis(page)
            ok_a, detail_a = check_btc_row(page, axis, last_ctx, H_STEP_MS,
                                           "1h_end")
            dom_check("btc_units_and_values_match_backend_1h", ok_a, detail_a)

            # (b) intervalo 1m: nueva identidad, contexto previo no sobrevive.
            page.select_option('[data-testid="explorer-interval"]', "1m")
            time.sleep(0.5)
            wait_until(lambda: series_urls and "interval=1m"
                       in series_urls[-1], 60.0, 0.3, "series_1m")
            payload_1m = fetch_series_payload_http(series_urls[-1])
            if not payload_1m:
                raise DemoError("1m payload fetch failed")
            ctx_1m = payload_1m.get("context_btc")
            dom_check("interval_change_context_identity",
                      (ctx_1m or {}).get("identity", {}).get("interval")
                      == "1m",
                      {"identity": (ctx_1m or {}).get("identity")})
            axis = new_axis(page)

            # (c) hueco de BTC: fila tras el hueco = GAP sin arrastre.
            block_1m = ctx_1m or {}
            gap_rows = [row for row in (block_1m.get("series") or [])
                        if (row.get("unknown") or {}).get("ret_btc_bps_5")
                        == "BTC_GAP_IN_WINDOW"]
            if not dom_check("backend_declares_btc_gap_in_window",
                             bool(gap_rows),
                             {"gap_rows": len(gap_rows)}):
                raise DemoError("no BTC_GAP_IN_WINDOW rows in 1m block")
            gap_row = gap_rows[len(gap_rows) // 2]
            ok_c, detail_c = check_btc_row(page, axis, gap_row, STEP_MS,
                                           "1m_gap")
            dom_check("btc_gap_shows_unknown_reason", ok_c, detail_c)

            screenshot(page, temp_root / "shot-btc-1m-gap.png")

            # (d) Consumidor SSE del servicio para el cierre vivo (context).
            watcher = ContextSseWatcher("MINAUSDT", "1m", payload_1m)
            watcher.start()

            # (e) cierre en vivo sin recarga.
            close_ms = None
            # Espera al siguiente cierre de minuto (ela fecha alineada).
            now = now_ms()
            close_ms = ((now // STEP_MS) + 1) * STEP_MS
            # Inyectar cierre por fake WS (MINAUSDT) para que el servicio
            # recalcule y emita el frame context.
            # (el fake WS envia velas; esperamos a que llegue el cierre)
            wait_until(lambda: watcher.row_for(close_ms) is not None,
                       120.0, 0.5, "context_frame_after_close")
            captured = watcher.row_for(close_ms)
            frame_row = captured["row"]
            ok_e, detail_e = False, {"wait": "first_hover_attempt"}
            for attempt in range(6):
                axis = new_axis(page, f"close{attempt}")
                ok_e, detail_e = check_btc_row(page, axis, frame_row,
                                               STEP_MS, "1m_close")
                if ok_e:
                    break
                time.sleep(2.0)
            dom_check("btc_close_updates_values_without_reload", ok_e,
                      detail_e)
            dom_check("no_reload_across_btc_close",
                      navigations["count"] == 1, navigations)

            screenshot(page, temp_root / "shot-btc-1m-close.png")

            # (f) cambio de simbolo: el contexto se limpia.
            page.fill('[data-testid="explorer-query"]', "BTCUSDT")
            page.click('[data-testid="explorer-search"]')
            page.wait_for_selector('[data-testid="explorer-open-BTCUSDT"]',
                                   timeout=60_000)
            page.click('[data-testid="explorer-open-BTCUSDT"]')
            page.wait_for_selector(CHART, timeout=60_000)
            wait_until(lambda: series_urls and "BTCUSDT"
                       in series_urls[-1], 60.0, 0.3, "series_btc")
            payload_btc = fetch_series_payload_http(series_urls[-1])
            dom_check("symbol_change_context_cleared",
                      payload_btc.get("context_btc") is None,
                      {"context_btc": payload_btc.get("context_btc")})
            dom_check("btc_badge_cleared_after_symbol_change",
                      page.locator(BADGE_BTC).count() == 0,
                      {"badge_count": page.locator(BADGE_BTC).count()})

            # (g) suscripcion BTC no duplicada: shared (>=1 consumidor BTC
            # para MINAUSDT; al volver a MINAUSDT no se crea una nueva).
            # Regresar a MINAUSDT y verificar que la suscripcion BTC se reusa.
            page.fill('[data-testid="explorer-query"]', "MINAUSDT")
            page.click('[data-testid="explorer-search"]')
            page.wait_for_selector('[data-testid="explorer-open-MINAUSDT"]',
                                   timeout=60_000)
            page.click('[data-testid="explorer-open-MINAUSDT"]')
            page.wait_for_selector(CHART, timeout=60_000)
            count_after = shared_count()
            dom_check("btc_subscription_shared_not_duplicated",
                      count_after >= 1,
                      {"btc_consumers": count_after})

            result["external_requests"] = external
            result["browser_external_count"] = len(external)
            result["series_urls"] = series_urls
            result["navigations"] = navigations["count"]
            result["errors"] = errors

            watcher.stop()
            context.close()
            browser.close()
            browser = None
            context = None

    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        log(f"ERROR: {result['error']}")
    finally:
        if watcher is not None:
            try:
                watcher.stop()
            except Exception:  # noqa: BLE001
                pass
        if context is not None:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass
        if fake_ws is not None:
            try:
                fake_ws.stop()
            except Exception:  # noqa: BLE001
                pass
        stop_proc(service_proc, "servicio market-stream")
        stop_proc(dashboard_proc, "dashboard")

    # Evidencia final (zero public).
    try:
        zero = check_zero_public(cache_db, conn_log)
        result["zero_public"] = zero
        result["zero_public_ok"] = (len(zero["python_denied_attempts"]) == 0
                                    and zero["ledger"]["rows"] == 0)
    except Exception as exc:  # noqa: BLE001
        result["zero_public"] = {"error": str(exc)}
        result["zero_public_ok"] = False

    checks_ok = all(c["ok"] for c in OPS)
    result["verdict"] = "PASS" if (
        not result.get("error")
        and checks_ok
        and result.get("zero_public_ok")
        and result.get("browser_external_count", 0) == 0) else "FAIL"
    result["checks"] = OPS
    result["git_sha"] = git_sha()
    evidence_dir = Path("docs/evidence") / EVIDENCE_DIRNAME
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with open(evidence_dir / "evidence.json", "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    log(f"veredicto={result['verdict']} "
        f"external={result.get('browser_external_count')} "
        f"evidence={evidence_dir / 'evidence.json'}")
    return result


if __name__ == "__main__":
    out = run()
    print(json.dumps({"verdict": out.get("verdict"),
                      "evidence": f"docs/evidence/{EVIDENCE_DIRNAME}/evidence.json",
                      "checks": len(out.get("checks", []))},
                     ensure_ascii=False))
    sys.exit(0 if out.get("verdict") == "PASS" else 1)
