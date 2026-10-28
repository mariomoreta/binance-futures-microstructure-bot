"""Demo publica del bloque market-indicators/v1 con transporte local.

Sustituye SOLO el dashboard identificado en 127.0.0.1:3020 (`next start`,
PID previo capturado y detenido). Cero solicitudes publicas: cache temporal
sembrada + wrapper `--no-fetch` + sitecustomize que bloquea sockets
no-loopback + guardia de rutas del navegador. Comprueba en DOM:

  * indicadores y unidades visibles en el badge;
  * valor bajo el cursor == salida del backend (payload market-series y
    frame SSE `indicators` del servicio para el cierre en vivo);
  * cierre de vela actualiza valores SIN recarga;
  * la vela provisional no altera el ultimo valor confirmado;
  * hueco/calentamiento muestran UNKNOWN con motivo;
  * cambiar simbolo/intervalo elimina los valores anteriores.

Uso (PowerShell, raiz del repositorio):
  $env:PYTHONPATH="src"; python scripts/indicators_v1_public_demo.py

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
EVIDENCE_DIRNAME = "indicators-v1-public-2026-10-25"

# Selectores de la demo (identificadores estables del contrato DOM).
BADGE = '[data-testid="market-chart-indicators"]'
CURSOR = '[data-testid="market-chart-cursor"]'
CHART = '[data-testid="market-chart"]'

# El badge solo imprime los "supported" del backend con su unidad.
LABELS = {"log_return_bps": "ret", "velocity_bps_5": "vel",
          "rel_volume_10": "relvol", "vwap_dev_bps_10": "vwapdev"}
UNITS = {"log_return_bps": "bps", "velocity_bps_5": "bps",
         "rel_volume_10": "x", "vwap_dev_bps_10": "bps"}
DECIMALS = {"log_return_bps": 2, "velocity_bps_5": 2,
            "rel_volume_10": 3, "vwap_dev_bps_10": 2}


class DemoError(RuntimeError):
    pass


OPS: List[Dict[str, Any]] = []


def log(msg: str) -> None:
    print(f"[indicators-demo] {msg}", flush=True)


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


def wait_until(predicate: Callable[[], Any], timeout: float, interval: float,
               what: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except DemoError:
            raise
        except Exception:  # noqa: BLE001 - sondeo
            pass
        time.sleep(interval)
    raise DemoError(f"TIMEOUT_WAITING_{what}")


# ---------------------------------------------------------------------------
# Build y servido del dashboard
# ---------------------------------------------------------------------------

def build_dashboard(evidence_dir: Path) -> str:
    log("construyendo dashboard publicado (npm run build)...")
    build_log = evidence_dir / "next-build.log"
    with open(build_log, "w", encoding="utf-8") as handle:
        proc = subprocess.run(
            ["cmd", "/c", "npm", "run", "build"], cwd=str(FRONTEND_DIR),
            stdout=handle, stderr=subprocess.STDOUT, timeout=1200)
    if proc.returncode != 0:
        raise DemoError(f"NEXT_BUILD_FAILED (ver {build_log})")
    build_id = (FRONTEND_DIR / ".next" / "BUILD_ID").read_text(
        encoding="utf-8").strip()
    log(f"build OK BUILD_ID={build_id}")
    return build_id


def dashboard_pid_on_3020() -> Optional[int]:
    # Windows en espanol emite bytes no-UTF8 (OEM/cp1252): decodificar con
    # reemplazo para que -X utf8 no mate el sondeo.
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=30)
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1] == f"127.0.0.1:{DASHBOARD_PORT}" \
                and parts[3] == "LISTENING":
            try:
                return int(parts[4])
            except ValueError:
                continue
    return None


def process_name(pid: int) -> str:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=30)
    lines = [line for line in out.stdout.splitlines() if line.strip()]
    if len(lines) >= 4:
        return lines[3].split()[0]
    return "UNKNOWN"


def stop_dashboard(pid: int) -> bool:
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                   text=True, timeout=30)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if dashboard_pid_on_3020() is None:
            return True
        time.sleep(0.5)
    return False


def start_dashboard(env: Dict[str, str], run_log: Path) -> subprocess.Popen:
    zombie = dashboard_pid_on_3020()
    if zombie is not None:
        # Un servidor ajeno en 3020 responderia 200 con SU cache env: la demo
        # entera se compararia contra datos de otra ejecucion. Abortar.
        raise DemoError(f"PORT_3020_OCCUPIED (pid {zombie}, "
                        f"{process_name(zombie)}) antes de next start")
    with open(run_log, "w", encoding="utf-8") as handle:
        proc = subprocess.Popen(["cmd", "/c", "npm", "run", "start"],
                                cwd=str(FRONTEND_DIR), env=env,
                                stdout=handle, stderr=subprocess.STDOUT)
    wait_until(lambda: http_status(DASHBOARD_URL) == 200, 90.0, 0.5,
               "dashboard_200")
    try:
        text = run_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    # El 200 solo vale si NUESTRO next start confirmo el bind: un servidor
    # ajeno en 3020 daria 200 con SU env/cache mientras el nuestro muere con
    # EADDRINUSE en el log de la corrida.
    if "EADDRINUSE" in text or "address already in use" in text.lower():
        raise DemoError("NEXT_START_BIND_FAILED (EADDRINUSE en el log de "
                        "next start): el 200 OK vino de otro servidor")
    if "Ready in" not in text and "Local:" not in text:
        raise DemoError("NEXT_START_NOT_CONFIRMED (sin banner Ready/Local en "
                        "el log): identidad del servidor 200 no verificada")
    log(f"dashboard 200 OK (pid {proc.pid}; Ready confirmado en el log)")
    return proc


# ---------------------------------------------------------------------------
# Servicio SSE + captura del frame indicators por cierre
# ---------------------------------------------------------------------------

def safe_health() -> Optional[Dict[str, Any]]:
    try:
        return http_json(f"http://127.0.0.1:{SERVICE_PORT}/health")
    except Exception:  # noqa: BLE001
        return None


class IndicatorsSseWatcher:
    """Consumidor SSE loopback que solo registra frames `indicators`."""

    def __init__(self, symbol: str, interval: str,
                 payload: Dict[str, Any]) -> None:
        requested = payload.get("requested") or {}
        self.path = (f"/stream?symbol={symbol}&interval={interval}"
                     f"&from_ms={int(requested.get('from_ms') or 0)}"
                     f"&to_ms={int(requested.get('to_ms') or 0)}&bars=300")
        self.frames: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="sse-watcher")

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
                if text == "event: indicators" and raw.startswith("data:"):
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


# ---------------------------------------------------------------------------
# Sembrado con hueco real declarado (borrado SQL en la cache temporal)
# ---------------------------------------------------------------------------

def seed_with_gap(cache_db: Path) -> Dict[str, Any]:
    info = seed_cache(cache_db, now_ms())
    # Hueco real: 3 velas 1m de BTCUSDT eliminadas ~40 barras atras. Las
    # ventanas (5/10 velas cerradas) de las filas posteriores incluyen el
    # hueco -> UNKNOWN(GAP_IN_WINDOW), nunca cero ni posicion de arreglo.
    connection = sqlite3.connect(str(cache_db))
    try:
        last_1m = int(info["last_closed_1m"])
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


# ---------------------------------------------------------------------------
# Playwright: DOM
# ---------------------------------------------------------------------------

def badge_text(page) -> str:
    return page.locator(BADGE).inner_text().strip()


def cursor_ms(page) -> Optional[int]:
    text = page.locator(CURSOR).inner_text().strip()
    match = re.match(r"Cursor (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", text)
    if not match:
        return None
    stamp = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S")
    return int(stamp.replace(tzinfo=timezone.utc).timestamp() * 1000)


def chart_box(page):
    # Elijo el canvas del panel de precios (NO el del eje temporal) y
    # lo bajo/traigo a la vista: el gráfico puede quedar fuera del viewport.
    canvas = page.locator(CHART).locator("canvas").first
    canvas.scroll_into_view_if_needed()
    return canvas.bounding_box()


def new_axis(page, label: str = "") -> "Axis":
    """Calibra el eje esperando el canvas estable (los cierres lo desplazan)."""
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
    """Mapa lineal px -> ms calibrado con dos puntos DEL AREA DE DATOS.

    Los píxeles extremos del canvas pueden estar fuera del rango visible de
    velas (margen blanco: time undefined, crosshair sin valor), asi que se
    que barrer hacia dentro desde cada borde hasta que el crosshair devuelva
    un tiempo definido; el reloj de barras su espacio es lineal y el mapa
    extrapolable a los extremos.
    """

    PANES_IN_STEP = 0.06

    def __init__(self, page) -> None:
        self.page = page
        box = chart_box(page)
        if box is None:
            raise DemoError("NO_CHART_CANVAS")
        self.x_left = box["x"] + 2
        self.x_right = box["x"] + box["width"] - 2
        self.y = box["y"] + box["height"] * 0.45
        left_x, ms_min = self._scan_ms(self.x_left, +1)
        right_x, ms_max = self._scan_ms(self.x_right, -1)
        if ms_min is None or ms_max is None or right_x is None or left_x is None:
            raise DemoError("AXIS_NOT_CALIBRATED")
        if right_x <= left_x or ms_max <= ms_min:
            raise DemoError("AXIS_NOT_CALIBRATED")
        # ms(x) = ms_min + (x - left_x) * ms_per_px
        self.ms_min = int(ms_min)
        self.ms_per_px = (ms_max - ms_min) / (right_x - left_x)
        self.left_x = left_x

    def _scan_ms(self, start: float, direction: int):
        step = max(4.0, (self.x_right - self.x_left) * self.PANES_IN_STEP)
        pos = start
        for _ in range(14):
            self._move(pos)
            ms = wait_cursor(self.page, 1.2)
            if ms is not None:
                return pos, ms
            pos += direction * step
            if pos < self.x_left or pos > self.x_right:
                break
        return None, None

    def _move(self, x: float) -> None:
        self.page.mouse.move(max(self.x_left, min(self.x_right, x)), self.y)

    def x_for(self, target_ms: int) -> float:
        return self.left_x + (target_ms - self.ms_min) / self.ms_per_px


def wait_cursor(page, timeout: float = 2.5) -> Optional[int]:
    deadline = time.monotonic() + timeout
    value = None
    while time.monotonic() < deadline:
        value = cursor_ms(page)
        if value is not None:
            return value
        time.sleep(0.05)
    return value


def hover_at_axis(axis: Axis, target_ms: int,
                  step_ms: int) -> Optional[int]:
    """Mueve el cursor a la vela exacta (px predichos + correccion local)."""
    page = axis.page
    x = axis.x_for(target_ms)
    page.mouse.move(x, axis.y)
    current = wait_cursor(page)
    if current is not None and current == target_ms:
        return current
    px_per_bar = max(0.6, axis.ms_per_px * step_ms)
    for attempt in range(-4, 5):
        probe_x = x + attempt * px_per_bar * 0.8
        if probe_x < axis.x_left or probe_x > axis.x_right:
            continue
        page.mouse.move(probe_x, axis.y)
        current = wait_cursor(page)
        if current == target_ms:
            return current
    return current


def fetch_series_payload(page, url: str) -> Optional[Dict[str, Any]]:
    try:
        return page.evaluate(
            "async (u) => {const r = await fetch(u, {cache:'no-store'});"
            "return await r.json();}", url)
    except Exception:  # noqa: BLE001
        return None


def fetch_series_payload_http(url: str) -> Optional[Dict[str, Any]]:
    """Fallback loopback: la misma URL del BFF via urllib (solo local)."""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log(f"payload fetch (http) fallo {url[:90]}: {exc}")
        return None


def row_at(payload: Optional[Dict[str, Any]], open_ms: int):
    block = (payload or {}).get("indicators") or {}
    for row in block.get("series") or []:
        if int(row.get("open_time_ms") or 0) == int(open_ms):
            return row
    return None


def compare_row(text: str, row: Dict[str, Any]) -> Optional[str]:
    """Devuelve None si el badge refleja la fila, o un error descriptivo."""
    values = row.get("values") or {}
    unknowns = row.get("unknown") or {}
    for name in list(values):
        label = LABELS.get(name)
        if label is None:
            continue  # vwap_typical_10 no es supported: no se imprime
        want = (f"{label} {values[name]:.{DECIMALS[name]}f}"
                f"{UNITS[name]}")
        if want not in text:
            return f"missing_value:{want}"
    for name, reason in unknowns.items():
        if name in values:
            continue
        if f"UNKNOWN({reason})" not in text:
            return f"missing_unknown:{name}:{reason}"
    # Unidad visible: bps y x cuando la fila tiene valores completos.
    if values and (set(values) & set(UNITS)):
        if "bps" not in text:
            return "unit_bps_not_visible"
        if any(name == "rel_volume_10" for name in values) and "x" not in text:
            return "unit_x_not_visible"
    return None


def check_row(page, axis: Axis, row: Dict[str, Any], step_ms: int,
              label: str) -> Tuple[bool, Any]:
    open_ms = int(row["open_time_ms"])
    reached = hover_at_axis(axis, open_ms, step_ms)
    text = badge_text(page)
    detail = {"open_time_ms": open_time_ms(row), "cursor_ms": reached,
              "badge": text, "backend": {"values": row.get("values"),
                                         "unknown": row.get("unknown")}}
    if reached != open_ms:
        detail["error"] = "cursor_not_at_target"
        return False, detail
    error = compare_row(text, row)
    if error:
        detail["error"] = error
        return False, detail
    return True, detail


def open_time_ms(row: Dict[str, Any]) -> int:
    return int(row.get("open_time_ms") or 0)


def screenshot(page, path: Path) -> None:
    try:
        page.screenshot(path=str(path), full_page=True)
        log(f"captura visual: {path.name}")
    except Exception as exc:  # noqa: BLE001
        log(f"captura fallo {path.name}: {exc}")


def browser_flow(result: Dict[str, Any], evidence_dir: Path) -> None:
    from playwright.sync_api import sync_playwright

    external: List[Dict[str, Any]] = []
    series_urls: List[str] = []
    navigations = {"count": 0}

    with sync_playwright() as playwright:
        # Guard de 0 publicas SIN interceptar trafico: la intercepcion de
        # Playwright (`page.route`) detiene peticiones del navegador en este
        # Chromium/Windows (verificado con probe: la misma URL sirve por
        # urllib en 0.6 s y desde el navegador queda colgada). El bloqueo se
        # aplica a NIVEL DE RESOLVEDOR del navegador (todo lo que no sea
        # loopback mapea a NOTFOUND); los intentos externos igual quedan
        # listados por el listener de peticiones (la prueba sigue siendo
        # `external == []`).
        browser = playwright.chromium.launch(headless=True, args=[
            "--host-resolver-rules=MAP * ~NOTFOUND, "
            "EXCLUDE 127.0.0.1, EXCLUDE localhost",
        ])
        context = browser.new_context(viewport={"width": 1280, "height": 960},
                                      locale="es-ES")
        page = context.new_page()

        def on_request(request) -> None:
            # Registro de intentos externos: guard sin interceptar.
            url = request.url
            if "/api/v1/market-series?" in url:
                series_urls.append(url)
            if url.startswith(DASHBOARD_URL) or url.startswith(
                    "http://localhost:3020") or url.startswith(
                    ("data:", "blob:", "about:", ":")):
                return
            external.append({"url": url, "at_ms": now_ms()})

        def on_response(response) -> None:
            if "/api/v1/market-series?" in response.url:
                series_urls.append(response.url)

        def on_load(_) -> None:
            # Solo se cuenta cargas REALES del documento (recargas = 1 extra).
            navigations["count"] += 1

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("load", on_load)
        page.add_init_script("window.__demoMounted = true;")

        def debug_state(tag: str) -> Dict[str, Any]:
            try:
                value = page.evaluate(
                    "() => {"
                    " const sel = document.querySelector("
                    "'[data-testid=\"explorer-interval\"]');"
                    " return {select_value: sel ? sel.value : null,"
                    " focus: document.activeElement ?"
                    " document.activeElement.tagName : null};}")
            except Exception as exc:  # noqa: BLE001
                value = {"evaluate_error": str(exc)}
            return {"tag": tag, "select": value,
                    "series_urls": len(series_urls),
                    "console": diagnostics[-4:], "page_errors": errors[-4:]}

        diagnostics: List[Dict[str, Any]] = []
        errors: List[str] = []
        page.on("console", lambda msg: diagnostics.append(
            {"type": msg.type, "text": msg.text[:160]}))
        page.on("pageerror", lambda exc: errors.append(str(exc)[:200]))

        page.goto(f"{DASHBOARD_URL}/market-lab", wait_until="domcontentloaded",
                  timeout=60_000)
        page.wait_for_selector('[data-testid="explorer-catalog-state"]',
                               timeout=60_000)
        if not dom_check("initial_navigation_single_load",
                         navigations["count"] == 1,
                         {"loads": navigations["count"]}):
            raise DemoError("unexpected extra document load at start")

        page.fill('[data-testid="explorer-query"]', "BTCUSDT")
        page.click('[data-testid="explorer-search"]')
        page.wait_for_selector('[data-testid="explorer-open-BTCUSDT"]',
                               timeout=60_000)
        page.click('[data-testid="explorer-open-BTCUSDT"]')
        page.wait_for_selector(CHART, timeout=60_000)
        wait_until(lambda: series_urls and "interval=1h" in series_urls[-1],
                   60.0, 0.3, "series_1h")
        payload_1h = fetch_series_payload_http(series_urls[-1])
        if not payload_1h:
            raise DemoError("1h payload fetch failed")
        dom_check("payload_indicators_v1",
                  (payload_1h.get("indicators") or {}).get("contract_version")
                  == "market-indicators/v1",
                  {"identity": payload_1h["indicators"]["identity"]})
        axis = new_axis(page)

        # (a) filas completas: unidades visibles y valor == backend (1h).
        series_1h = payload_1h["indicators"]["series"]
        ok_a, detail_a = check_row(page, axis, series_1h[-1], H_STEP_MS,
                                   "1h_end")
        dom_check("units_and_values_match_backend_1h", ok_a, detail_a)

        # (b) calentamiento: UNKNOWN(INSUFICIENT_CANDLES) hacia el inicio de
        # la ventana; la ULTIMA fila insuficiente es la mas clara de posar.
        warm_rows = [row for row in series_1h
                     if (row.get("unknown") or {}).get("rel_volume_10")
                     == "INSUFICIENT_CANDLES"]
        warm_row = warm_rows[-1] if warm_rows else None
        if not dom_check("backend_declares_insufficient_warmup",
                         warm_row is not None,
                         {"insufficient_rows": len(warm_rows)}):
            raise DemoError("no INSUFICIENT_CANDLES rows in 1h block")
        ok_b, detail_b = check_row(page, axis, warm_row, H_STEP_MS, "1h_warm")
        dom_check("warmup_over_shows_unknown_reason", ok_b, detail_b)

        screenshot(page, evidence_dir / "shot-1h-values.png")

        # (c) cambio de intervalo: identidad nueva, valores previos no
        # sobreviven (nueva ventana/payload).
        page.select_option('[data-testid="explorer-interval"]', "1m")
        time.sleep(0.5)
        log(f"post-select: {debug_state('after_select')}")
        try:
            wait_until(lambda: series_urls
                       and "interval=1m" in series_urls[-1], 60.0, 0.3,
                       "series_1m")
        except DemoError as exc:
            time.sleep(3.0)
            log(f"post-select-3s: {debug_state('late_after_select')}")
            raise
        payload_1m = fetch_series_payload_http(series_urls[-1])
        if not payload_1m:
            raise DemoError("1m payload fetch failed")
        dom_check("interval_change_payload_identity",
                  (payload_1m.get("indicators") or {}).get("identity", {})
                  .get("interval") == "1m",
                  {"identity": payload_1m["indicators"]["identity"]})
        axis = new_axis(page)

        # (d) hueco: fila posterior al hueco declarado = GAP en ventanas.
        block_1m = payload_1m["indicators"]
        gap_rows = [row for row in block_1m["series"]
                    if (row.get("unknown") or {}).get("rel_volume_10")
                    == "GAP_IN_WINDOW"]
        if not dom_check("backend_declares_gap_in_window", bool(gap_rows),
                         {"gap_rows": len(gap_rows)}):
            raise DemoError("no GAP_IN_WINDOW rows in 1m block")
        gap_row = gap_rows[len(gap_rows) // 2]
        ok_d, detail_d = check_row(page, axis, gap_row, STEP_MS, "1m_gap")
        dom_check("gap_shows_unknown_gap_in_window", ok_d, detail_d)

        # --- Consumidor SSE del servicio (loopback) para el cierre vivo ----
        watcher = IndicatorsSseWatcher("BTCUSDT", "1m", payload_1m)
        watcher.start()

        # (e) cierre en vivo sin recarga ------------------------------------
        result["close_request"] = "waiting minute boundary"
        close_ms = wait_minute_boundary()
        wait_until(lambda: watcher.row_for(close_ms) is not None, 120.0, 0.5,
                   "indicators_frame_after_close")
        captured = watcher.row_for(close_ms)
        frame_row = captured["row"]
        # La vela cerrada llega por stream (no hay REST nuevo): el DOM la
        # recibe con mergeCandleRows + applyStreamIndicators, sin recarga.
        # Reintento con recalibracion: la barra nueva puede desplazar el eje.
        ok_e, detail_e = False, {"wait": "first_hover_attempt"}
        for attempt in range(6):
            axis = new_axis(page, f"close{attempt}")
            ok_e, detail_e = check_row(page, axis, frame_row, STEP_MS,
                                       "1m_close")
            if ok_e:
                break
            time.sleep(2.0)
        dom_check("close_updates_values_without_reload", ok_e, detail_e)
        dom_check("no_reload_across_close",
                  navigations["count"] == 1, navigations)

        # (f) vela provisional: no altera el ultimo confirmado --------------
        stable_before = badge_text(page)
        time.sleep(6.0)  # ~2 ticks del proveedor ficticio sobre la provisional
        stable_now = badge_text(page)
        dom_check("provisional_tick_does_not_change_confirmed",
                  stable_before == stable_now,
                  {"before": stable_before, "after": stable_now})
        provisional_ms = close_ms + STEP_MS
        axis = new_axis(page, "provisional")
        provisional_reached = hover_at_axis(axis, provisional_ms, STEP_MS)
        text_provisional = badge_text(page)
        dom_check("provisional_candle_excluded_from_block",
                  provisional_reached == provisional_ms
                  and "vela provisional excluida" in text_provisional,
                  {"cursor_ms": provisional_reached, "badge": text_provisional})

        screenshot(page, evidence_dir / "shot-1m-close.png")

        # (g) cambio de simbolo: los valores anteriores desaparecen ---------
        page.fill('[data-testid="explorer-query"]', "MINAUSDT")
        page.click('[data-testid="explorer-search"]')
        page.wait_for_selector('[data-testid="explorer-open-MINAUSDT"]',
                               timeout=60_000)
        page.click('[data-testid="explorer-open-MINAUSDT"]')
        wait_until(lambda: series_urls
                   and "symbol=MINAUSDT" in series_urls[-1], 60.0, 0.3,
                   "series_mina")
        payload_mina = fetch_series_payload_http(series_urls[-1])
        if not payload_mina:
            raise DemoError("MINA payload fetch failed")
        dom_check("symbol_change_payload_identity",
                  payload_mina.get("symbol") == "MINAUSDT"
                  and ((payload_mina.get("indicators") or {}).get("identity")
                       or {}).get("symbol") == "MINAUSDT",
                  {"identity": payload_mina["indicators"].get("identity")})
        axis = new_axis(page)
        series_mina = payload_mina["indicators"]["series"]
        ok_g, detail_g = check_row(page, axis, series_mina[-1], STEP_MS,
                                   "mina_end")
        dom_check("symbol_change_clears_previous_values", ok_g, detail_g)
        dom_check("no_reload_after_symbol_change",
                  navigations["count"] == 1, navigations)

        screenshot(page, evidence_dir / "shot-mina-values.png")

        result["browser_external_requests"] = external
        result["series_urls"] = series_urls
        result["sse_frames"] = len(watcher.frames)
        result["sse_errors"] = watcher.errors
        result["navigator_loads"] = navigations["count"]
        watcher.stop()
        browser.close()


def wait_minute_boundary() -> int:
    """open_time de la vela 1m que CIERRA al cruzar el limite del minuto."""
    now = now_ms()
    current_open = (now // STEP_MS) * STEP_MS
    next_boundary = current_open + STEP_MS
    wait_until(lambda: now_ms() >= next_boundary, 95.0, 0.5,
               "minute_boundary")
    return current_open


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def main() -> int:
    evidence_dir = ROOT / "docs" / "evidence" / EVIDENCE_DIRNAME
    evidence_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="indicators_public_demo_"))

    result: Dict[str, Any] = {"evidence_dir": str(evidence_dir)}
    processes: List[subprocess.Popen] = []
    fake: Optional[FakeKlineServer] = None
    try:
        sha = git_sha()

        # Sustitucion ANTES del build: el dashboard identificado en 3020 se
        # detiene para que `next build`/`next start` trabajen sobre `.next`
        # sin servidor activo leyendo el mismo directorio.
        replacement: Dict[str, Any] = {"old_pid": None, "old_process": None,
                                       "stopped": None}
        old_pid = dashboard_pid_on_3020()
        if old_pid is not None:
            replacement["old_pid"] = old_pid
            replacement["old_process"] = process_name(old_pid)
            replacement["stopped"] = stop_dashboard(old_pid)
            log(f"dashboard sustituido: pid {old_pid} "
                f"({replacement['old_process']}) detenido={replacement['stopped']}")
            if not replacement["stopped"]:
                raise DemoError(
                    f"OLD_DASHBOARD_ALIVE (pid {old_pid}): 3020 no quedo libre"
                    " y la demo compararia contra su cache de otra ejecucion")
        result["dashboard_replacement"] = replacement

        build_id = build_dashboard(evidence_dir)

        cache_db = workdir / "market_cache.db"
        seed_info = seed_with_gap(cache_db)
        log(f"cache sembrada en {cache_db}; hueco {seed_info['deleted_rows']}"
            " velas borradas")
        shadow = prepare_shadow(workdir)

        fake_port = free_port()
        fake = FakeKlineServer(fake_port, Path(shadow["fake_log"]))
        fake.start()
        log(f"fake kline ws loopback:{fake_port} arriba")

        service_log = evidence_dir / "market-stream-service.log"
        env = os.environ.copy()
        env.update({
            "PYTHONPATH": str(ROOT / "src"),
            "MICROPROBE_MARKET_CACHE_DB": str(cache_db),
            "MICROPROBE_MARKET_STREAM_PID": str(workdir / "service.json"),
            "MICROPROBE_STREAM_URL": f"http://127.0.0.1:{SERVICE_PORT}",
        })
        with open(service_log, "w", encoding="utf-8") as handle:
            service = subprocess.Popen(
                [sys.executable,
                 str(ROOT / "scripts" / "market_stream_service.py"),
                 "--port", str(SERVICE_PORT),
                 "--transport", "local",
                 "--base-url", f"ws://127.0.0.1:{fake_port}",
                 "--max-seconds", "1500"],
                cwd=str(ROOT), env=env, stdout=handle,
                stderr=subprocess.STDOUT)
        processes.append(service)
        wait_until(lambda: (safe_health() or {}).get("transport", {})
                   .get("mode") == "local", 30.0, 0.3, "service_health")
        log(f"servicio {SERVICE_PORT} arriba (transport local)")

        dashboard_env = env.copy()
        dashboard_env.update({
            "MARKET_EXPLORER_ROOT": shadow["root"],
            "MICROPROBE_TEST_CANON_SRC": shadow["canon_src"],
            "MICROPROBE_TEST_CANON_SCRIPT": shadow["canon_script"],
            "MICROPROBE_TEST_CONN_LOG": shadow["conn_log"],
        })
        dashboard_log = evidence_dir / "next-start.log"
        dashboard = start_dashboard(dashboard_env, dashboard_log)
        processes.append(dashboard)

        flow: Dict[str, Any] = {}
        browser_flow(flow, evidence_dir)
        result.update(flow)

        zero = check_zero_public(cache_db, Path(shadow["conn_log"]))
        zero["browser_external_requests"] = len(
            result.get("browser_external_requests") or [])
        ok_zero = (zero["browser_external_requests"] == 0
                   and not zero["python_denied_attempts"]
                   and zero["ledger"]["requests"] == 0)
        result["zero_public"] = zero

        all_ok = all(check["ok"] for check in OPS) and ok_zero
        result["dom_checks"] = OPS
        result["final"] = {
            "verdict": "PASS" if all_ok else "FAIL",
            "sha": sha,
            "build_id": build_id,
            "url": DASHBOARD_URL,
            "service_port": SERVICE_PORT,
            "fake_ws_port": fake_port,
            "transport": "local loopback (0 publicas; FAIL 2026-10-24 sin tocar)",
            "dom_vs_visual": {
                "dom": "selectores exactos+valores comparados contra el "
                       "backend (dom_checks, todos PASS/FAIL)",
                "visual": "capturas para revision aparte: shot-1h-values.png,"
                          " shot-1m-close.png, shot-mina-values.png "
                          "(la demo no reemplaza la revision visual)",
            },
            "seed": seed_info,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        (evidence_dir / "evidence.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8")
        log(f"veredicto {result['final']['verdict']}; evidencia: "
            f"{evidence_dir / 'evidence.json'}")
        return 0 if all_ok else 1
    except DemoError as exc:
        result["error"] = str(exc)
        result["dom_checks"] = OPS
        (evidence_dir / "evidence.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8")
        log(f"FALLO demo: {exc}; evidencia parcial en {evidence_dir}")
        return 1
    finally:
        for process in processes:
            try:
                # Terminate solo mata el hijo directo (cmd/npm); el nieto
                # node (next start) sobrevive y quedaria sirviendo un build
                # con cache de ESTA corrida en 3020: exactamente el escenario
                # de servidor ajeno del 2026-10-25. Tree-kill exactivo.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T",
                                "/F"], capture_output=True, timeout=30)
            except Exception:  # noqa: BLE001
                try:
                    process.terminate()
                    process.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    try:
                        process.kill()
                    except Exception:  # noqa: BLE001
                        pass
        if fake is not None:
            try:
                fake.stop()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    sys.exit(main())
