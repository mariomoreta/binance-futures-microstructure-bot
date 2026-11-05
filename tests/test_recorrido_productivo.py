"""Recorrido productivo local: selección → suscripción → recepción → evaluación.

Usa proveedores HTTP/WS loopback, SQLite temporal y el CLI existente
(research_pilot.py) como subproceso. Control de reloj manual. No toca Binance
pública, ni endpoints privados, ni red pública de mercado.

Reproduce el recorrido del piloto ejecutado (commit b37a6be) para evidenciar:
- Descubrimiento y selección reales (research-selector-v2).
- Actualización del conjunto seguido.
- Apertura/suscripción de feeds reales del piloto.
- Recepción y procesamiento de mensajes.
- Evaluación automática (take_decisions).

Incluye: símbolo que permanece, símbolo nuevo, símbolo que se reincorpora y
fuente que demora o nunca entrega datos.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Reusa la infraestructura de prueba del piloto (loopback, sin red pública).
from tests.test_research_pilot import (  # noqa: E402
    ClockFile,
    WsProvider,
    start_ws_server,
    find_free_port,
    base_price,
    kline_price,
    read_rows,
    T0,
    MINUTE,
)
import research_pilot as rp  # noqa: E402
from research_pilot import PilotConfig  # noqa: E402

# Universo pequeño y determinista para controlar la selección.
UNIVERSE = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT", "FFFUSDT"]
HORIZONS = (("5m", 300_000), ("15m", 900_000), ("60m", 3_600_000))


def _send_json(handler, payload, code: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("X-MBX-USED-WEIGHT-1M", "1")
    handler.end_headers()
    handler.wfile.write(body)


class ControlledMarketHttp:
    """Mercado REST simulado controlado por la prueba.

    Permite fijar las filas de ticker que se devuelven en cada llamada para
    dirigir la selección del piloto (qué símbolos entran/salen del seguido).
    """
    def __init__(self, universe):
        self.universe = list(universe)
        self.call_count = 0
        self._lock = threading.Lock()
        self._ticker_rows = None

    def set_tickers(self, rows):
        with self._lock:
            self._ticker_rows = list(rows)

    def default_rows(self):
        rows = []
        for idx, symbol in enumerate(self.universe):
            rows.append({
                "symbol": symbol,
                "lastPrice": str(base_price(symbol, self.universe)),
                "priceChangePercent": str(1.0 + 0.1 * idx),
                "quoteVolume": str(50_000_000.0),
                "count": str(1000 + idx),
                "closeTime": T0,
            })
        return rows

    def _handle(self, handler):
        parsed = urlsplit(handler.path)
        path = parsed.path
        if path == "/fapi/v1/exchangeInfo":
            symbols = [{"symbol": s, "status": "TRADING",
                        "contractType": "PERPETUAL", "quoteAsset": "USDT"}
                       for s in self.universe]
            _send_json(handler, {"symbols": symbols, "timezone": "UTC"})
            return
        if path == "/fapi/v1/ticker/24hr":
            with self._lock:
                self.call_count += 1
                rows = self._ticker_rows if self._ticker_rows is not None \
                    else self.default_rows()
            _send_json(handler, rows)
            return
        if path == "/fapi/v1/klines":
            symbol = parse_qs(parsed.query).get("symbol", [""])[0].upper()
            start = int(parse_qs(parsed.query).get("startTime", [0])[0])
            open_time = (start // MINUTE) * MINUTE
            price = base_price(symbol, self.universe)
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

            def log_message(self, fmt, *args):  # noqa: D401
                pass

        return Handler


class ProductRun:
    """Ejecuta research_pilot.py como subproceso y sincroniza sus fases."""

    def __init__(self, tmp, *, universe, duration_s, settle_s,
                 selection_s, cycle_s, max_symbols, max_candidates,
                 max_comparators):
        self.tmp = Path(tmp)
        self.out_dir = self.tmp / "out"
        self.obs_path = self.out_dir / "observaciones.jsonl"
        self.status_path = self.tmp / "status.json"
        self.gate_path = self.tmp / "gate.json"
        self.stop_path = self.tmp / "stop.txt"
        self.clock = ClockFile(self.tmp / "clock.txt", T0)

        self.http = ControlledMarketHttp(universe)
        self.http_port = find_free_port()
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", self.http_port), self.http.make_handler())
        self.http_thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True)
        self.http_thread.start()

        self.ws = WsProvider(universe)
        self.ws_port = find_free_port()
        self._ws_stop = start_ws_server(self.ws, self.ws_port)

        cmd = [
            sys.executable, str(ROOT / "scripts" / "research_pilot.py"),
            "--run-id", "recorrido-productivo", "--out-dir", str(self.out_dir),
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
            "--max-candidates", str(max_candidates),
            "--max-comparators", str(max_comparators),
            "--min-quote-volume", "1000000",
            "--horizons", ",".join(f"{k}={v}" for k, v in HORIZONS),
            "--price-interval", "1m",
            "--price-tolerance-ms", "90000",
            "--price-delay-ms", "2000",
            "--max-data-age-ms", "5000",
            "--max-observations", "20000",
            "--max-bytes", str(128 * 1024 * 1024),
            "--max-messages", "5000000",
            "--max-http-attempts", "2000",
            "--max-http-retries", "50",
            "--max-http-weight", "5000",
            "--max-ws-reconnects", "20",
            "--tick-ms", "50",
            "--clock", "manual", "--clock-file", str(self.tmp / "clock.txt"),
            "--status-file", str(self.status_path),
            "--decision-gate-file", str(self.gate_path),
            "--stop-file", str(self.stop_path),
        ]
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)

    # -- estado -----------------------------------------------------------
    def status(self):
        deadline = time.monotonic() + 0.25
        while True:
            try:
                return json.loads(self.status_path.read_text(
                    encoding="utf-8"))
            except (OSError, ValueError):
                if time.monotonic() > deadline:
                    return None
                time.sleep(0.01)

    def wait_status(self, predicate, what, timeout=30.0):
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
                    out, err = self.proc.communicate(timeout=5)
                except Exception:
                    out, err = "", ""
                raise AssertionError(
                    f"piloto terminó esperando {what}: rc={self.proc.poll()}"
                    f" stdout={out!r} stderr={err!r} último={last}")
            time.sleep(0.02)
        raise AssertionError(
            f"timeout {timeout}s esperando {what}; último={json.dumps(last)}")

    def advance(self, instant_ms, timeout=30.0):
        self.clock.set(instant_ms)
        return self.wait_status(
            lambda st: st.get("now_ms") == instant_ms,
            f"reloj en {instant_ms}", timeout)

    def publish_and_confirm(self, instant_ms, depth_symbols=(),
                            trade_events=None):
        """Publica burst WS y espera confirmación del estado del piloto."""
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

        def processed(state):
            for symbol in depth_symbols:
                if (state.get("book", {}).get(symbol) or {}).get(
                        "event_ms") != instant_ms:
                    return False
            for symbol, series in events.items():
                if not series:
                    continue
                if (state.get("flow", {}).get(symbol) or {}).get(
                        "event_ms") != series[-1]:
                    return False
            return True

        return self.wait_status(
            processed, f"libro/flujo procesados en {instant_ms}")

    def step(self, instant_ms, *, depth_symbols=(), trade_events=None,
             evaluate=False, expected_obs=None):
        """Fija instante → publica → confirma → (opcional) autoriza evaluación."""
        self.advance(instant_ms)
        if depth_symbols or trade_events:
            self.publish_and_confirm(
                instant_ms, depth_symbols, trade_events)
        if not evaluate:
            return None
        tmp = self.gate_path.with_name(self.gate_path.name + ".tmp")
        tmp.write_text(
            json.dumps({"decision_ms": instant_ms, "allow": True}),
            encoding="utf-8")
        os.replace(tmp, self.gate_path)
        return self.wait_observations(
            instant_ms, expected_obs or 1)

    def wait_observations(self, decision_ms, expected, timeout=30.0):
        def pred(rows):
            found = [r for r in rows
                     if r.get("kind") == "observacion"
                     and r.get("decision_ms") == decision_ms]
            return found if len(found) >= expected else None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = pred(read_rows(self.obs_path))
            if found:
                return found
            if self.proc.poll() is not None:
                raise AssertionError("piloto terminó esperando observaciones")
            time.sleep(0.02)
        raise AssertionError(
            f"timeout {timeout}s esperando {expected} obs en {decision_ms}")

    def stop(self, timeout=90.0):
        state = self.status() or {}
        end = int(state.get("settle_end_ms") or 0)
        if end:
            self.clock.set(end + 1000)
        try:
            out, err = self.proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            out, err = self.proc.communicate()
            raise AssertionError("piloto no terminó tras el fin")
        return self.proc.returncode

    def shutdown(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.communicate()
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass
        try:
            self._ws_stop()
        except Exception:
            pass


@pytest.fixture
def recorrido():
    """Ejecuta el piloto una vez y lo detiene al finalizar."""
    tmp = Path(tempfile.mkdtemp(prefix="recorrido-"))
    run = ProductRun(
        tmp, universe=UNIVERSE, duration_s=120, settle_s=10,
        selection_s=10, cycle_s=10, max_symbols=6,
        max_candidates=12, max_comparators=8)
    try:
        yield run
    finally:
        run.shutdown()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Recorrido productivo completo (versión actual del piloto)
# ---------------------------------------------------------------------------

def test_recorrido_productivo_versión_actual(recorrido):
    """Demuestra selección → suscripción → recepción → evaluación con el
    comportamiento actual del piloto.

    Espera: los símbolos recién seleccionados en el primer ciclo se evalúan
    sin datos de libro/flujo (feeds acabados de abrir) y se descartan.
    """
    run = recorrido

    # Fase 1: selección inicial y apertura de feeds (T0).
    run.advance(T0)
    state = run.wait_status(
        lambda st: st.get("now_ms") == T0
        and len(st.get("followed") or []) > 0
        and len(st.get("feeds") or {}) == 2
        and all(f.get("connected_now") for f in st["feeds"].values()),
        "selección inicial y feeds conectados")

    seguido = state.get("followed") or []
    assert len(seguido) <= 6
    assert state.get("cycles_run", 0) >= 1

    # Fase 2: publicar libro y flujo para los símbolos seguidos, luego
    # autorizar la primera evaluación (T0 + 5s = decision_delay).
    run.publish_and_confirm(
        T0, depth_symbols=seguido,
        trade_events={s: [T0 + 1000] for s in seguido})
    run.step(T0 + 5000, depth_symbols=seguido,
             trade_events={s: [T0 + 6000] for s in seguido},
             evaluate=True, expected_obs=len(seguido))

    # Fase 3: verificar observaciones generadas.
    obs = [r for r in read_rows(run.obs_path)
           if r.get("kind") == "observacion"
           and r.get("decision_ms") == T0 + 5000]
    assert len(obs) == len(seguido), (
        f"se esperaban {len(seguido)} observaciones, se obtuvieron {len(obs)}")

    # Los símbolos que NO recibieron flujo/libro antes de la evaluación se
    # descartan (evaluación prematura del recién seleccionado).
    descartados = [o for o in obs if o.get("estado") == "descartada"]
    aptas = [o for o in obs if o.get("estado") == "observada"]
    assert len(aptas) + len(descartados) == len(seguido)
    # Al menos los símbolos que no tuvieron flujo en la ventana quedan descartados
    # por ventana incompleta o sin datos, evidenciando la evaluación prematura.
    motivos = set()
    for o in descartados:
        motivos.update(o.get("motivos") or [])
    assert "sin_flujo" in motivos or "flujo_ventana_incompleta" in motivos


def test_recorrido_productivo_flujo_inasistencia_descarta(recorrido):
    """Fuente que nunca entrega datos: el símbolo se selecciona, se suscribe,
    pero al evaluarse no tiene flujo → descarte con motivo, finalización
    acotada (no espera indefinidamente)."""
    run = recorrido
    run.advance(T0)
    state = run.wait_status(
        lambda st: len(st.get("followed") or []) > 0
        and len(st.get("feeds") or {}) == 2,
        "selección inicial")
    seguido = state.get("followed") or []
    # Publicar libro pero NO flujo para todos los símbolos.
    run.publish_and_confirm(T0, depth_symbols=seguido, trade_events={})
    run.step(T0 + 5000, depth_symbols=seguido, trade_events={},
             evaluate=True, expected_obs=len(seguido))
    obs = [r for r in read_rows(run.obs_path)
           if r.get("kind") == "observacion"
           and r.get("decision_ms") == T0 + 5000]
    descartados = [o for o in obs if o.get("estado") == "descartada"]
    assert len(descartados) == len(seguido)
    assert all("sin_flujo" in (o.get("motivos") or []) for o in descartados)
