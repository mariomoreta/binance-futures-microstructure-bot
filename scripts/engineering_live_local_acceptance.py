"""Aceptacion local automatizada de la sesion de ingenieria en LIVE.

Camino completo SIN Binance publico (transporte loopback, aislado de red):

  fake kline WS (loopback, precios guionizados)
    -> market-stream-service/v1 (SSE, solo loopback)
    -> engineering-session-service/v1 (adaptador SSE = transporte market_stream)
    -> BFF /api/v1/engineering-sessions
    -> /market-lab (navegador Playwright, seccion Sesion de ingenieria)

El arnes:
  * detiene (y RESTAURA al final) el dashboard identificado en 127.0.0.1:3020;
  * construye el frontend (el drive live consume la UI publicada);
  * siembra una cache temporal (contexto MINA plano en 1.05, BTC en 100000)
    y arranca servicios en puertos EFIMEROS (8792/8797/8791 intocables);
  * bloquea y registra todo intento no-loopback (sitecustomize + proxy +
    guardia de resolucion del navegador): cero peticiones publicas;
  * conduce el flujo real con precios deterministas (relativos al minuto del
    click en "Iniciar sesion"; entry_px = cierre de contexto = 1.05,
    stop_px = 1.03425):
        backfill inicial (fronteras M-3..M-1 cerradas, close 1.0490 sin
        senal; repara el tramo cache->conexion: no hay reparacion REST en
        local) -> abstencion (SIN_ENTRADA: close 1.0490 < entry 1.05)
        pausa del WS (gap ENTRE disparos ~98-102 s > live_silence_ms = 90 s)
        M close 1.0490 tardio -> puerta FEED_SILENCE (evaluacion omitida,
        vela fusionada; visible)
        M+1 close 1.0495 -> reevaluacion sin senal
        M+2 close 1.0520 -> senal: ENTRADA_SIMULADA cuando cierra M+3
        M+4 open 1.0525 (= close de M+3) -> fill en open revelado
        reinicio del servicio de mercado -> reconexion SSE real del adaptador
        M+5 cierra con close(M+4)=1.0300 <= stop 1.03425 -> salida por stop
  * verifica en DOM y contra el estado autoritativo del backend (3 relojes:
    evento, recepcion y evaluacion; bloques de evidencia del stream;
    reconexiones del adaptador) y exige cero peticiones publicas.

El JSON resultante NO acredita recepcion de Binance: todo el transporte es
loopback y el proveedor publico permanece bloqueado durante toda la corrida.

Uso (PowerShell, raiz del repositorio):
  python -X utf8 scripts/engineering_live_local_acceptance.py \
      --out-dir docs/evidence/engineering-live-local-2026-10-28
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from market_stream_local_acceptance import (  # noqa: E402
    STEP_MS, FakeKlineServer, HarnessError, ProxyServer, git_sha, http_json,
    iso, log, now_ms, port_open, prepare_shadow, wait_minute_phase, wait_until,
)

# asyncio lo usa el bucle del servidor WS heredado; importado a nivel de
# modulo para que el import del paquete no dependa del orden de ejecucion.
import asyncio  # noqa: E402

from indicators_v1_public_demo import (  # noqa: E402
    build_dashboard, check_zero_public, dashboard_pid_on_3020, process_name,
    start_dashboard, stop_dashboard,
)

DASHBOARD_PORT = 3020
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}"
FRONTEND_DIR = ROOT / "frontend"
ENGINEERING_SERVICE = "engineering-session-service/v1"

# Guion de precios (LONG, entry_px = cierre de contexto sembrado).
SESSION_SYMBOL = "MINAUSDT"
CONTEXT_CLOSE = 1.05
STOP_PCT = 1.5
STOP_PX = round(CONTEXT_CLOSE * (1.0 - STOP_PCT / 100.0), 8)  # 1.03425
# closes por indice de minuto relativo al minuto del click (M):
#   M+0 abstencion | M+1 puerta | M+2 senal | M+3 fill en open | M+4 stop
SCRIPT_CLOSES = {0: 1.0490, 1: 1.0495, 2: 1.0520, 3: 1.0525, 4: 1.0300}

LIVE_SILENCE_MS = 90_000.0
PAUSE_S = 95.0          # pausa del WS: gap entre disparos ~98-102 s > 90 s
                        # (la abstencion se ve ~2-6 s tras la frontera)
RESTART_DOWN_S = 15.0   # servicio de mercado caido: reconexion SSE real

# Limites por fase (segundos). No se amplian para "compensar" un fallo.
LIMITS = {
    "minute_phase": 60.0,
    "service_ready": 45.0,
    "stream_evidence": 45.0,
    "abstention": 110.0,
    # Tras la puerta FEED_SILENCE la senal llega cuando la vela cuyo close
    # >= entry esta plenamente conocida: 2 fronteras cerradas mas (~125 s
    # con latencia) desde el fin de la pausa. 200 s = cadencia real + margen.
    "gate": 150.0,
    "entrada": 200.0,
    "fill": 100.0,
    "salida": 120.0,
    "cerrada": 90.0,
    "run": 800.0,
}


def free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def tree_kill(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                   capture_output=True, timeout=30)


def _safe_json(url: str) -> Optional[Dict[str, Any]]:
    try:
        return http_json(url, timeout=4.0)
    except Exception:  # noqa: BLE001 - sondeo de salud
        return None


# ---------------------------------------------------------------------------
# Cache temporal sembrada (contexto plano -> entry_px determinista)
# ---------------------------------------------------------------------------

def seed_flat_cache(cache_path: Path) -> Dict[str, Any]:
    from microstructure_probe.market_cache import MarketCache
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(cache_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    cache = MarketCache(cache_path)
    cache.init_db()
    fetched_at = now_ms()
    now = fetched_at
    seeded: Dict[str, Any] = {}
    for symbol, base in (("BTCUSDT", 100000.0), ("MINAUSDT", CONTEXT_CLOSE)):
        last_1m = (now // STEP_MS) * STEP_MS - STEP_MS
        first_1m = last_1m - (7 * 24 * 60 - 1) * STEP_MS
        bars_1m = []
        cursor = first_1m
        while cursor <= last_1m:
            bars_1m.append({
                "open_time": cursor, "open": f"{base}",
                "high": f"{base * 1.0005:.8f}" if base < 10
                        else f"{base * 1.0005:.2f}",
                "low": f"{base * 0.9995:.8f}" if base < 10
                       else f"{base * 0.9995:.2f}",
                "close": f"{base}",
                "base_volume": "125.5", "quote_volume": "125500.0",
                "trade_count": 42, "close_time": cursor + STEP_MS - 1,
            })
            cursor += STEP_MS
        cache.upsert_klines(symbol, "1m", "klines", bars_1m, fetched_at)
        seeded[symbol] = {"1m": len(bars_1m)}
    entries = []
    for symbol, base_asset in (("BTCUSDT", "BTC"), ("MINAUSDT", "MINA")):
        entries.append({
            "symbol": symbol, "base_asset": base_asset, "quote_asset": "USDT",
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
            "context_close": CONTEXT_CLOSE,
            "last_closed_1m": (now // STEP_MS) * STEP_MS - STEP_MS}


# ---------------------------------------------------------------------------
# Fake kline WS con guion determinista + pausa (silencio del feed)
# ---------------------------------------------------------------------------

class ScriptedKlineServer(FakeKlineServer):
    """Ticker por simbolo con closes guionizados y pausa controlable.

    Guion relativo al minuto del click (click_open_ms, fijado por el arnes
    justo antes de pulsar "Iniciar sesion"):
      * idx < 0 (fronteras ANTES del click, backfill inicial): 1.0490 sin
        senal (la continuidad de contexto 1.05 vive en la cache sembrada;
        el backfill del stream repara el tramo cache->conexion y sus
        closes no deben senalizar contra entry_px = 1.05);
      * idx en SCRIPT_CLOSES: close guionizado;
      * resto: 1.0490 (sin senal, low > stop_px).
    BTCUSDT: plano en 100000 (solo contexto BTC). La pausa congela el envio
    (sin frames): el cierre de la vela en frontera llega TARDE y el hueco
    ENTRE disparos supera live_silence_ms -> puerta FEED_SILENCE.
    """

    # Fronteras cerradas entregadas en el backfill de cada PRIMERA conexion.
    # Cubre el desfase siembra-cache -> conexion (~1-3 min); las velas que el
    # cache ya cubre quedan bajo el reloj de la sesion y el adaptador las
    # salta (dedupe por reloj), las intermedias reparan la rejilla.
    BACKFILL_BOUNDARIES = 4

    def __init__(self, port: int, log_path: Path) -> None:
        super().__init__(port, log_path)
        self.click_open_ms: Optional[int] = None
        self.script: Dict[int, float] = {}
        self.pause = threading.Event()
        # Estado por SIMBOLO compartido entre reconexiones: el servicio de
        # mercado recicla su socket cada pocos segundos (churn observado en
        # el log del fake); con estado por conexion la vela en curso se
        # pierde en cada reciclaje y el cierre tardio (pausa del feed)
        # jamas se entregaria (hueco de rejilla permanente, reparacion REST
        # inexistente en local).
        self.shared_state: Dict[str, Dict[str, Any]] = {}

    def close_of(self, symbol: str, open_ms: int) -> float:
        if symbol != SESSION_SYMBOL:
            return 100000.0
        click = self.click_open_ms
        if click is None:
            return CONTEXT_CLOSE
        idx = int((int(open_ms) - click) // STEP_MS)
        # idx < 0 (backfill previo al click): sin senal (1.0490), para no
        # igualar entry_px=1.05 y provocar una senal prematura.
        return self.script.get(idx, 1.0490)

    async def _ticker(self, ws, symbol: str) -> None:  # type: ignore[override]
        state = self.shared_state.setdefault(symbol, {
            "open": None, "open_price": None, "high": None, "low": None,
            "close": None, "last_event": 0, "volume": 0.0})
        try:
            while True:
                if symbol == SESSION_SYMBOL and self.pause.is_set():
                    await asyncio.sleep(1.0)
                    continue
                now = now_ms()
                current_open = (now // STEP_MS) * STEP_MS
                if state["open"] is None:
                    # Arranque en mitad de un minuto: el backfill entrega
                    # las ultimas BACKFILL_BOUNDARIES fronteras cerradas EN
                    # ORDEN. En un exchange real las repararia el backfill
                    # REST del servicio de mercado; en loopback el fake hace
                    # de fuente amable: sin este tramo, las fronteras entre
                    # el fin de la cache sembrada y la conexion serian un
                    # hueco de rejilla permanente (no hay reparacion REST en
                    # local) y la puerta GRID_GAP bloquearia toda evaluacion.
                    ev = now
                    back_open = current_open - (
                        self.BACKFILL_BOUNDARIES * STEP_MS)
                    while back_open < current_open:
                        state["open"] = back_open
                        state["open_price"] = self.close_of(
                            symbol, back_open - STEP_MS)
                        state["close"] = self.close_of(symbol, back_open)
                        state["high"] = max(state["open_price"],
                                            state["close"]) * 1.0005
                        state["low"] = min(state["open_price"],
                                           state["close"]) * 0.9995
                        state["last_event"] = ev
                        state["volume"] = 1.0
                        await self._send(ws, symbol, state, closed=True,
                                         event_ms=ev)
                        ev += 1
                        back_open += STEP_MS
                    state["open"] = current_open
                    state["open_price"] = self.close_of(symbol,
                                                        current_open - STEP_MS)
                    state["close"] = self.close_of(symbol, current_open)
                    state["high"] = max(state["open_price"], state["close"])
                    state["low"] = min(state["open_price"], state["close"])
                    state["last_event"] = max(now, ev)
                    state["volume"] = 1.0
                    await self._send(ws, symbol, state, closed=False,
                                     event_ms=state["last_event"])
                elif current_open > state["open"]:
                    # Cierre real en frontera. Si la pausa (o una caida)
                    # salto VARIAS fronteras, se recuperan TODAS las velas
                    # cerradas omitidas EN ORDEN (tardias pero en secuencia:
                    # el servicio de mercado las fusiona sin hueco y la
                    # primera entrega tardia dispara la puerta FEED_SILENCE).
                    ev = max(now, int(state["last_event"]) + 1)
                    op = int(state["open"])
                    while op < current_open:
                        state["close"] = self.close_of(symbol, op)
                        state["open_price"] = self.close_of(symbol,
                                                            op - STEP_MS)
                        state["high"] = max(state["open_price"],
                                            state["close"]) * 1.0005
                        state["low"] = min(state["open_price"],
                                           state["close"]) * 0.9995
                        state["last_event"] = ev
                        state["volume"] = 1.0
                        await self._send(ws, symbol, state, closed=True,
                                         event_ms=ev)
                        ev += 1
                        op += STEP_MS
                    state["open"] = current_open
                    state["open_price"] = self.close_of(symbol,
                                                        current_open - STEP_MS)
                    state["close"] = self.close_of(symbol, current_open)
                    state["high"] = max(state["open_price"], state["close"])
                    state["low"] = min(state["open_price"], state["close"])
                    state["last_event"] = max(now, state["last_event"] + 2)
                    state["volume"] = 1.0
                    await self._send(ws, symbol, state, closed=False,
                                     event_ms=state["last_event"])
                else:
                    state["last_event"] = max(now, state["last_event"] + 1)
                    state["close"] = self.close_of(symbol, state["open"])
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


# ---------------------------------------------------------------------------
# Fase de navegador: flujo real de la sesion de ingenieria
# ---------------------------------------------------------------------------

def shot(page, path: Path) -> None:
    page.screenshot(path=str(path), full_page=True)


def wait_text(page, needle: str, timeout_s: float) -> float:
    started = time.monotonic()
    page.wait_for_function(
        """(needle) => document.body
            && document.body.innerText.includes(needle)""",
        arg=needle, timeout=int(timeout_s * 1000))
    return time.monotonic() - started


def wait_text_ci(page, needle: str, timeout_s: float) -> float:
    """Igual que wait_text pero case-insensitive: los h3 de .card/.cardFull
    se renderizan con text-transform: uppercase y ``innerText`` devuelve el
    texto TRANSFORMADO (p.ej. "EXPORTACION")."""
    started = time.monotonic()
    page.wait_for_function(
        """(needle) => {
          const t = (document.body && document.body.innerText) || "";
          return t.toLowerCase().includes(needle.toLowerCase());
        }""", arg=needle, timeout=int(timeout_s * 1000))
    return time.monotonic() - started


def wait_testid(page, testid: str, timeout_s: float,
                contains: Optional[str] = None) -> float:
    started = time.monotonic()
    page.wait_for_function(
        """([testid, needle]) => {
          const node = document.querySelector(`[data-testid="${testid}"]`);
          if (!node) return false;
          return needle === null
            || (node.textContent || "").includes(needle);
        }""",
        arg=[testid, contains], timeout=int(timeout_s * 1000))
    return time.monotonic() - started


def browser_flow(server: ScriptedKlineServer, evidence_dir: Path,
                 limits: Dict[str, float],
                 hooks: Dict[str, Callable[[], None]]) -> Dict[str, Any]:
    """Conduce /market-lab: iniciar -> abstencion -> puerta -> entrada ->
    fill -> [hook: reinicio del servicio de mercado] -> salida stop ->
    sesion cerrada. Devuelve tiempos y capturas; FAIL por limite de fase."""
    from playwright.sync_api import sync_playwright

    flow: Dict[str, Any] = {"phases": {}, "screenshots": [],
                            "external_requests": []}
    with sync_playwright() as playwright:
        # Guard sin interceptar: todo lo no-loopback mapea a NOTFOUND a nivel
        # de resolucion del navegador (page.route cuelga peticiones aqui).
        browser = playwright.chromium.launch(headless=True, args=[
            "--host-resolver-rules=MAP * ~NOTFOUND, "
            "EXCLUDE 127.0.0.1, EXCLUDE localhost",
        ])
        context = browser.new_context(viewport={"width": 1280, "height": 960},
                                      locale="es-ES")
        page = context.new_page()
        page.on("request", lambda req: flow["external_requests"].append(
            {"url": req.url, "at_ms": now_ms()})
            if not (req.url.startswith(DASHBOARD_URL)
                    or req.url.startswith("http://localhost:3020")
                    or req.url.startswith(("data:", "blob:", "about:", ":")))
            else None)

        page.goto(DASHBOARD_URL + "/market-lab", wait_until="domcontentloaded")

        # 1) Servicio de ingenieria visible (listo; GET puro no arranca nada).
        page.wait_for_function(
            """() => document.querySelector('[data-testid="service-chip"]')
                ?.dataset.state === 'ready'""",
            timeout=int(limits["service_ready"] * 1000))
        log("chip del servicio: ready")

        # 2) Titulo de transporte live (default del componente).
        wait_text(page, "transporte market_stream", limits["service_ready"])

        # 3) Alineacion al minuto y guion absoluto de closes.
        flow["phases"]["minute_phase_s"] = wait_minute_phase(
            limits["minute_phase"])
        click_open_ms = (now_ms() // STEP_MS) * STEP_MS
        server.click_open_ms = click_open_ms
        server.script = dict(SCRIPT_CLOSES)
        flow["click_open_ms"] = click_open_ms
        log(f"click alineado: vela M open={iso(click_open_ms)}")

        # 4) Iniciar sesion (create live + control start, todo en el backend).
        #    Identidad del panel sobre textContent: el h3 del panel se
        #    renderiza con text-transform: uppercase (innerText daria
        #    "TRANSPORTE MARKET_STREAM") y el primer render puede aun no
        #    traer datos del drive (carrera con el primer poll).
        started = time.monotonic()
        page.click('[data-testid="btn-iniciar-sesion"]')
        wait_testid(page, "stream-evidence", limits["stream_evidence"],
                    contains="market_stream")
        flow["stream_evidence_text"] = page.locator(
            '[data-testid="stream-evidence"]').text_content()
        flow["phases"]["stream_evidence_s"] = time.monotonic() - started
        log("panel de evidencia del stream visible (market_stream)")

        # 5) Abstencion temprana: el backfill inicial (fronteras previas al
        #    click, close 1.0490 sin senal) se fusiona al conectar el feed;
        #    al revelarse su cierre conocida, close < entry 1.05 ->
        #    "Sin senal de entrada" visible en el evaluador.
        elapsed = wait_text(page, "Sin senal de entrada",
                            limits["abstention"])
        flow["phases"]["abstention_s"] = elapsed
        shot(page, evidence_dir / "shot-01-abstencion.png")
        flow["screenshots"].append("shot-01-abstencion.png")
        log(f"abstencion visible ({elapsed:.1f} s tras click)")

        # 6) Silencio del feed: pausa del WS -> puerta FEED_SILENCE. La vela
        #    cerrada de la frontera M llega TARDE (no se pierde: el fake la
        #    recupera al reanudar), la evaluacion se omite con causa visible
        #    (vela fusionada) y el siguiente disparo vuelve a evaluar.
        gate_started = time.monotonic()
        server.pause.set()
        log(f"WS pausado {PAUSE_S:.0f} s (gap entre disparos > "
            f"{LIVE_SILENCE_MS / 1000.0:.0f} s)")
        time.sleep(PAUSE_S)
        server.pause.clear()
        log("WS reanudado; esperando puerta FEED_SILENCE visible")
        wait_testid(page, "session-abstention-gate", limits["gate"],
                    contains="FEED_SILENCE")
        flow["phases"]["gate_s"] = time.monotonic() - gate_started
        flow["gate_text"] = page.locator(
            '[data-testid="session-abstention-gate"]').inner_text()
        shot(page, evidence_dir / "shot-02-puerta-feed-silence.png")
        flow["screenshots"].append("shot-02-puerta-feed-silence.png")
        log(f"puerta FEED_SILENCE visible ({flow['phases']['gate_s']:.1f} s)")

        # 7) Siguiente disparo evaluable: ENTRADA_SIMULADA (close(M+2)=1.0520
        #    >= entry, conocida al llegar la closed de M+3).
        started = time.monotonic()
        wait_text(page, "ENTRADA_SIMULADA", limits["entrada"])
        flow["phases"]["entrada_s"] = time.monotonic() - started
        shot(page, evidence_dir / "shot-03-entrada.png")
        flow["screenshots"].append("shot-03-entrada.png")
        log("ENTRADA_SIMULADA visible")

        # 8) Fill al revelarse el open de M+4 (= close de M+3 = 1.0525),
        #    cuando llega la closed de M+4 en la frontera siguiente.
        started = time.monotonic()
        page.wait_for_function(
            r"""() => /entrada\s+1\.0525/i.test(document.body.innerText)""",
            timeout=int(limits["fill"] * 1000))
        flow["phases"]["fill_s"] = time.monotonic() - started
        shot(page, evidence_dir / "shot-04-fill-gestion.png")
        flow["screenshots"].append("shot-04-fill-gestion.png")
        log("fill en open visible (Entrada 1.0525)")
        if "post_fill" in hooks:
            hooks["post_fill"]()

        # 9) Salida por stop: close(M+4)=1.0300 <= stop 1.03425, revelado al
        #    llegar la closed de M+5.
        started = time.monotonic()
        page.wait_for_function(
            r"""() => /salida\s+1\.0\d*\s+\(stop\)/i.test(
                document.body.innerText)""",
            timeout=int(limits["salida"] * 1000))
        flow["phases"]["salida_s"] = time.monotonic() - started
        shot(page, evidence_dir / "shot-05-salida-stop.png")
        flow["screenshots"].append("shot-05-salida-stop.png")
        log("salida por stop visible")

        # 10) Sesion cerrada + causa de fin de conduccion (SESSION_CLOSED).
        started = time.monotonic()
        wait_testid(page, "session-drive-cause", limits["cerrada"],
                    contains="se cerr")
        flow["phases"]["cerrada_s"] = time.monotonic() - started
        shot(page, evidence_dir / "shot-06-sesion-cerrada.png")
        flow["screenshots"].append("shot-06-sesion-cerrada.png")
        log("sesion cerrada y causa visible (SESSION_CLOSED)")

        # 11) Exportacion visible con la identidad de la sesion (el h3 se
        #     renderiza en mayusculas: comparacion case-insensitive).
        wait_text_ci(page, "Exportacion", limits["cerrada"])
        wait_text(page, "session_id", limits["cerrada"])

        browser.close()
    return flow


# ---------------------------------------------------------------------------
# Verificacion del estado autoritativo del backend (snapshot final)
# ---------------------------------------------------------------------------

def verify_final_state(eng_port: int, session_id: str) -> Dict[str, Any]:
    payload = http_json(f"http://127.0.0.1:{eng_port}/sessions/{session_id}",
                        timeout=15.0)
    session = payload.get("session") or {}
    drive = payload.get("drive") or {}
    checks: Dict[str, Any] = {}

    def check(name: str, ok: bool, detail: Any = None) -> None:
        checks[name] = {"ok": bool(ok), "detail": detail}

    config = session.get("config") or {}
    res = session.get("result") or {}
    events = session.get("events") or []
    stats = drive.get("stats") or {}
    evidence_adapter = ((config.get("decision_evidence") or {})
                        .get("adapter") or {})

    check("status_cerrada", session.get("status") == "cerrada",
          session.get("status"))
    check("decision_entrada", config.get("decision") == "ENTRADA_SIMULADA",
          config.get("decision"))
    check("exit_stop",
          bool(res.get("exit_executed"))
          and str(res.get("exit_reason") or "").lower().startswith("stop"),
          {"exit_executed": res.get("exit_executed"),
           "exit_reason": res.get("exit_reason")})
    kinds = [str(ev.get("kind") or "") for ev in events]
    check("event_entry", "entry" in kinds, kinds)
    check("event_stop_or_exit",
          any(k in ("stop", "exit") for k in kinds), kinds)
    last_fill = next((ev for ev in reversed(events)
                      if "fill_basis=" in str(ev.get("detail") or "")), None)
    check("fill_basis_tag", last_fill is not None and
          "fill_basis=model_approximation" in str(last_fill.get("detail")),
          (last_fill or {}).get("detail"))
    clocks = evidence_adapter.get("clocks") or {}
    check("three_clocks",
          all(clocks.get(k) is not None for k in (
              "trigger_open_ms", "trigger_received_at_ms",
              "evaluation_clock_ms", "evaluation_wall_ms")), clocks)
    blocks = evidence_adapter.get("evidence_blocks") or {}
    check("evidence_blocks_stream",
          "indicators" in blocks and "context_btc" in blocks,
          sorted(blocks.keys()))
    check("adapter_runner", evidence_adapter.get("runner") == "market_stream",
          evidence_adapter.get("runner"))
    check("reconnects", int(stats.get("reconnects") or 0) >= 1,
          {"reconnects": stats.get("reconnects"),
           "disconnects": stats.get("disconnects"),
           "connect_errors": stats.get("connect_errors")})
    check("watermark", drive.get("watermark") is not None,
          drive.get("watermark"))
    check("market_url_loopback",
          str(drive.get("market_url") or "").startswith("http://127.0.0.1"),
          drive.get("market_url"))
    return {"checks": checks,
            "session": session, "drive": drive,
            "ok": all(item["ok"] for item in checks.values())}


# ---------------------------------------------------------------------------
# Corrida unica
# ---------------------------------------------------------------------------

def run_one(args: argparse.Namespace, workdir: Path,
            out_dir: Path) -> Dict[str, Any]:
    run_started = time.monotonic()
    result: Dict[str, Any] = {}
    processes: List[subprocess.Popen] = []
    fake: Optional[ScriptedKlineServer] = None
    proxy: Optional[ProxyServer] = None
    try:
        eng_dir = workdir / "eng"
        (eng_dir / "data" / "engineering-session").mkdir(parents=True,
                                                         exist_ok=True)
        sessions_dir = eng_dir / "data" / "engineering-session" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        # El workdir efimero se REUTILIZA entre corridas: sin esta limpieza el
        # conteo de sesiones de la corrida seria acumulativo (las corridas
        # previas ya dejaron su evidencia extraida). Solo toca el scratch del
        # arnes; el directorio canonico del servicio 8797 jamas se toca aqui.
        pl_dir = sessions_dir / "paper-lab-sessions"
        if pl_dir.exists():
            for stale in list(pl_dir.glob("*.json")) + list(
                    pl_dir.glob("*.lock")):
                stale.unlink()
        registry = sessions_dir / "drive-registry.json"
        if registry.exists():
            registry.unlink()
        pid_file = eng_dir / "data" / "engineering-session" / "service.json"

        fake_port = free_port()
        market_port = free_port()
        eng_port = free_port()
        proxy_port = free_port()
        result["ports"] = {"fake_ws": fake_port,
                           "market_service": market_port,
                           "engineering_service": eng_port,
                           "proxy": proxy_port, "dashboard": DASHBOARD_PORT}

        cache_db = workdir / "market_cache.db"
        result["seed"] = seed_flat_cache(cache_db)
        log(f"cache sembrada (contexto plano {CONTEXT_CLOSE}) en {cache_db}")

        shadow = prepare_shadow(workdir)
        result["shadow"] = {k: shadow[k] for k in
                            ("root", "conn_log", "proxy_log", "fake_log",
                             "browser_log")}

        fake = ScriptedKlineServer(fake_port, Path(shadow["fake_log"]))
        fake.start()
        log(f"fake kline ws loopback:{fake_port} arriba")

        proxy = ProxyServer(proxy_port, Path(shadow["proxy_log"]))
        proxy.start()
        log(f"proxy de registro loopback:{proxy_port} arriba")

        # --- servicio de mercado (SSE, solo loopback, cache temporal) --------
        market_env = os.environ.copy()
        market_env.update({
            "PYTHONPATH": str(ROOT / "src"),
            "MICROPROBE_MARKET_CACHE_DB": str(cache_db),
            "MICROPROBE_MARKET_STREAM_PID":
                str(workdir / "market-service.json"),
        })
        market_holder: Dict[str, Any] = {}

        def start_market() -> subprocess.Popen:
            handle = open(out_dir / "market-service.log", "a",
                          encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, "-X", "utf8",
                 str(ROOT / "scripts" / "market_stream_service.py"),
                 "--port", str(market_port),
                 "--transport", "local",
                 "--base-url", f"ws://127.0.0.1:{fake_port}",
                 "--max-seconds", "1500"],
                cwd=str(ROOT), env=market_env, stdout=handle,
                stderr=subprocess.STDOUT)
            processes.append(proc)
            wait_until(
                lambda: ((_safe_json(
                    f"http://127.0.0.1:{market_port}/health")
                    or {}).get("transport") or {}).get("mode") == "local",
                30.0, 0.3, "market_service_health")
            return proc

        market_holder["proc"] = start_market()
        log(f"servicio de mercado loopback:{market_port} arriba "
            "(transport local)")

        # --- servicio de ingenieria (adaptador market_stream) ----------------
        eng_env = os.environ.copy()
        eng_env.update({"PYTHONPATH": str(ROOT / "src")})
        with open(out_dir / "engineering-service.log", "a",
                  encoding="utf-8") as handle:
            eng_proc = subprocess.Popen(
                [sys.executable, "-X", "utf8",
                 str(ROOT / "scripts" / "engineering_session_service.py"),
                 "--host", "127.0.0.1",
                 "--port", str(eng_port),
                 "--sessions-dir", str(sessions_dir),
                 "--pid-file", str(pid_file),
                 "--market-url", f"http://127.0.0.1:{market_port}",
                 "--market-bars", "60",
                 "--live-silence-ms", str(LIVE_SILENCE_MS)],
                cwd=str(ROOT), env=eng_env, stdout=handle,
                stderr=subprocess.STDOUT)
        processes.append(eng_proc)
        wait_until(lambda: (_safe_json(
            f"http://127.0.0.1:{eng_port}/health") or {}).get(
            "service") == ENGINEERING_SERVICE, 30.0, 0.3,
            "engineering_health")
        log(f"servicio de ingenieria loopback:{eng_port} arriba "
            "(market_stream, live_silence 90 s)")

        # --- dashboard de prueba en 3020 (entorno efimero) -------------------
        dashboard_env = market_env.copy()
        dashboard_env.update({
            "MARKET_EXPLORER_ROOT": shadow["root"],
            "MICROPROBE_TEST_CANON_SRC": shadow["canon_src"],
            "MICROPROBE_TEST_CANON_SCRIPT": shadow["canon_script"],
            "MICROPROBE_TEST_CONN_LOG": shadow["conn_log"],
            "ENGINEERING_SERVICE_URL": f"http://127.0.0.1:{eng_port}",
            "ENGINEERING_SERVICE_PORT": str(eng_port),
            "ENGINEERING_SERVICE_ROOT": str(eng_dir),
        })
        dashboard = start_dashboard(dashboard_env,
                                    out_dir / "next-start.log")
        processes.append(dashboard)
        log("dashboard de prueba 200 OK en 3020")

        # --- flujo del navegador ---------------------------------------------
        def restart_market() -> None:
            log("parada del servicio de mercado (reconexion SSE)...")
            tree_kill(market_holder["proc"].pid)
            processes.remove(market_holder["proc"])
            time.sleep(RESTART_DOWN_S)
            market_holder["proc"] = start_market()
            market_holder["restarted_pid"] = market_holder["proc"].pid
            log("servicio de mercado de vuelta; adaptador reconecta "
                "por backoff (snapshot deduplicado por marca de agua)")

        flow = browser_flow(
            fake, out_dir, LIMITS,
            hooks={"post_fill": restart_market})
        result["flow"] = {
            k: v for k, v in flow.items() if k != "external_requests"}
        result["browser_external_requests"] = flow["external_requests"]
        result["market_restarted_pid"] = market_holder.get("restarted_pid")

        # --- snapshot autoritativo final --------------------------------------
        list_payload = http_json(
            f"http://127.0.0.1:{eng_port}/sessions", timeout=15.0)
        rows = list_payload.get("sessions") or []
        session_ids = [row.get("session_id") for row in rows]
        if len(session_ids) != 1:
            raise HarnessError(f"SESSION_COUNT_UNEXPECTED: {session_ids}")
        session_id = session_ids[0]
        result["session_id"] = session_id
        final = verify_final_state(eng_port, session_id)
        (out_dir / "session-final.json").write_text(
            json.dumps(final, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        result["final_checks"] = final["checks"]
        log(f"estado autoritativo verificado: "
            f"{sum(1 for c in final['checks'].values() if c['ok'])}/"
            f"{len(final['checks'])} checks OK")

        # --- cero publicas ------------------------------------------------------
        zero = check_zero_public(cache_db, Path(shadow["conn_log"]))
        zero["browser_external_requests"] = len(flow["external_requests"])
        result["zero_public"] = zero
        ok_zero = (zero["browser_external_requests"] == 0
                   and not zero["python_denied_attempts"]
                   and zero["ledger"]["requests"] == 0)
        result["ok_zero_public"] = ok_zero

        result["phases_pass"] = all(
            (flow["phases"].get(k) is not None)
            for k in ("stream_evidence_s", "abstention_s", "gate_s",
                      "entrada_s", "fill_s", "salida_s", "cerrada_s"))
        result["run_seconds"] = time.monotonic() - run_started
        result["procedural_pass"] = bool(
            result["phases_pass"] and final["ok"] and ok_zero)
        return result
    finally:
        # Limpieza SIEMPRE: sin procesos residuales ni sesiones de ensayo.
        for proc in list(processes):
            try:
                tree_kill(proc.pid)
            except Exception:  # noqa: BLE001
                try:
                    proc.terminate()
                    proc.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    pass
        if fake is not None:
            try:
                fake.stop()
            except Exception:  # noqa: BLE001
                pass
        if proxy is not None:
            try:
                proxy.stop()
            except Exception:  # noqa: BLE001
                pass
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"http://127.0.0.1:{result.get('ports', {}).get('engineering_service', 0)}/shutdown",
                    data=b'{}', headers={"Content-Type": "application/json"},
                    method="POST"), timeout=3)
        except Exception:  # noqa: BLE001 - ya detenido por taskkill
            pass


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------

def git_build_id() -> Optional[str]:
    try:
        return (FRONTEND_DIR / ".next" / "BUILD_ID").read_text(
            encoding="utf-8").strip()
    except OSError:
        return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None,
                        help="directorio de evidencia (por defecto "
                             "docs/evidence/engineering-live-local-<fecha>)")
    parser.add_argument("--workdir", default=None,
                        help="directorio temporal (por defecto "
                             "<TEMP>/opencode/engineering-live)")
    parser.add_argument("--no-build", action="store_true",
                        help="no reconstruye el frontend (usa .next actual)")
    args = parser.parse_args(argv)

    workdir = Path(args.workdir or (
        Path(os.environ.get("TEMP", ".")) / "opencode"
        / "engineering-live-acceptance"))
    workdir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.out_dir or (
        ROOT / "docs" / "evidence"
        / f"engineering-live-local-{time.strftime('%Y-%m-%d')}"))
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {
        "generated_at_ms": now_ms(),
        "dashboard_url": DASHBOARD_URL,
        "transport": "market_stream (live, loopback)",
        "symbol": SESSION_SYMBOL,
        "script": {"context_close": CONTEXT_CLOSE, "stop_px": STOP_PX,
                   "closes": {f"M+{k}": v for k, v in SCRIPT_CLOSES.items()},
                   "live_silence_ms": LIVE_SILENCE_MS,
                   "pause_s": PAUSE_S, "restart_down_s": RESTART_DOWN_S},
        "git_sha": git_sha(),
        "build_id": git_build_id(),
        "notes": [
            "Transporte loopback: este arnes NO acredita recepcion de "
            "Binance; el proveedor publico permanece bloqueado (sitecustomize "
            "+ guardia de resolucion del navegador + proxy de registro).",
            "8792 (servicio ajeno), 8797 y 8791 canonicos intocables: todos "
            "los servicios de la corrida usan puertos efimeros.",
        ],
    }

    # Sustitucion del dashboard en 3020 (se RESTAURA al final, incluso si la
    # corrida falla: sin servidor de prueba olvidado en 3020).
    old_pid = dashboard_pid_on_3020()
    replacement: Dict[str, Any] = {"old_pid": old_pid}
    if old_pid is not None:
        replacement["old_process"] = process_name(old_pid)
        replacement["stopped"] = stop_dashboard(old_pid)
        if not replacement["stopped"]:
            print(json.dumps({"ok": False,
                              "error": f"OLD_DASHBOARD_ALIVE (pid {old_pid})"},
                             ensure_ascii=False))
            return 2
    summary["dashboard_replacement"] = replacement

    def restore_dashboard() -> Dict[str, Any]:
        """Devuelve 3020 a su estado previo (dashboard canonico o libre)."""
        restore: Dict[str, Any] = {"expected": replacement["old_pid"]}
        if replacement["old_pid"] is None:
            restore["restarted"] = None
            restore["note"] = ("no habia dashboard en 3020 antes de la "
                               "corrida")
            return restore
        with open(out_dir / "canonical-next-start.log", "w",
                  encoding="utf-8") as handle:
            proc = subprocess.Popen(["cmd", "/c", "npm", "run", "start"],
                                    cwd=str(FRONTEND_DIR), stdout=handle,
                                    stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 90.0
        up = False
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(DASHBOARD_URL, timeout=3) as resp:
                    up = resp.status == 200
                    break
            except Exception:  # noqa: BLE001 - aun arrancando
                time.sleep(1.0)
        restore["restarted"] = up
        restore["pid"] = proc.pid
        if not up:
            restore["note"] = ("el dashboard canonico no respondio 200 en "
                               "90 s: arrancarlo manualmente")
        return restore

    try:
        try:
            if not args.no_build:
                summary["build_id"] = build_dashboard(out_dir)
            run = run_one(args, workdir, out_dir)
            summary["runs"] = [run]
        finally:
            summary["dashboard_restore"] = restore_dashboard()
        canonical_sessions = ROOT / "data" / "engineering-session" / "sessions"
        summary["canonical_service_state"] = {
            "note": ("el servicio canonico 8797 no fue tocado; sus sesiones "
                     "de ensayo quedan listadas para revision del operador"),
            "trial_sessions": sorted(
                p.name for p in canonical_sessions.glob("paper-lab-sessions/*")
            ) if canonical_sessions.exists() else [],
        }
        ok = bool(summary["runs"] and summary["runs"][0].get(
            "procedural_pass")) and summary["dashboard_restore"].get(
            "restarted") in (True, None)
        summary["verdict"] = "PASS" if ok else "FAIL"
    except HarnessError as exc:
        summary["error"] = str(exc)
        summary["verdict"] = "FAIL"
    except Exception as exc:  # noqa: BLE001 - superficie del arnes
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["verdict"] = "FAIL"
    finally:
        (out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
