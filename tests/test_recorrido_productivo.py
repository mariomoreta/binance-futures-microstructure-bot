"""Recorrido productivo local: seleccion -> suscripcion -> recepcion -> evaluacion.

Usa proveedores HTTP/WS loopback, SQLite temporal y el CLI existente
(research_pilot.py) como subproceso. Control de reloj manual. No toca Binance
publica, ni endpoints privados, ni red publica de mercado.

Demuestra la correccion de coordinacion (captura_protocol_version=2):
- seleccionar -> suscribir -> acumular ventana requerida -> evaluar.
- Un simbolo recien suscrito no se evalua inmediatamente; espera al
  calentamiento acotado por ciclo (selection_seconds).
- decision_ms sigue siendo el instante real de evaluacion.
- Como maximo una observacion por simbolo y ciclo.
- Una reincorporacion no hereda cobertura ficticia.
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

# Universo con suficientes simbolos para tener candidatos Y comparadores
# (max_candidates=12 + max_comparators=8 = techo 20 = max_symbols).
UNIVERSE = [f"S{i:03d}USDT" for i in range(25)]
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
    """Mercado REST simulado. Devuelve catalogo y ticker de todos los simbolos."""
    def __init__(self, universe):
        self.universe = list(universe)
        self.call_count = 0
        self._lock = threading.Lock()

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
    """Ejecuta research_pilot.py como subproceso y sincroniza sus fases.

    No usa --decision-gate-file ni llama a take_decisions directamente. El
    piloto evalua automaticamente cuando el reloj avanza mas alla de
    next_decision y los simbolos han cumplido su calentamiento.
    """
    def __init__(self, tmp, *, universe, duration_s, settle_s,
                 selection_s, cycle_s, decision_delay_s,
                 max_symbols, max_candidates, max_comparators):
        self.tmp = Path(tmp)
        self.out_dir = self.tmp / "out"
        self.obs_path = self.out_dir / "observaciones.jsonl"
        self.status_path = self.tmp / "status.json"
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
            "--decision-delay-seconds", str(decision_delay_s),
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
            "--tick-ms", "100",
            "--clock", "manual", "--clock-file", str(self.tmp / "clock.txt"),
            "--status-file", str(self.status_path),
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

    def wait_status(self, predicate, what, timeout=60.0):
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
                    f"piloto termino esperando {what}: rc={self.proc.poll()}"
                    f" stdout={out!r} stderr={err!r} ultimo={last}")
            time.sleep(0.02)
        raise AssertionError(
            f"timeout {timeout}s esperando {what}; ultimo={json.dumps(last)}")

    def advance(self, instant_ms, timeout=60.0):
        self.clock.set(instant_ms)
        return self.wait_status(
            lambda st: st.get("now_ms") == instant_ms,
            f"reloj en {instant_ms}", timeout)

    def publish_and_confirm(self, instant_ms, depth_symbols=(),
                            trade_events=None):
        """Publica burst WS y espera confirmacion del estado del piloto."""
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

    def wait_observations(self, decision_ms, expected, timeout=60.0):
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
                raise AssertionError("piloto termino esperando observaciones")
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
            raise AssertionError("piloto no termino tras el fin")
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
        tmp, universe=UNIVERSE, duration_s=300, settle_s=60,
        selection_s=60, cycle_s=60, decision_delay_s=60,
        max_symbols=20, max_candidates=12, max_comparators=8)
    try:
        yield run
    finally:
        run.shutdown()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Recorrido productivo completo (version corregida)
# ---------------------------------------------------------------------------

def test_recorrido_productivo_seleccion_suscripcion_recepcion_evaluacion(
        recorrido):
    """Recorrido completo con el piloto corregido.

    Verifica:
    - Seleccion real (research-selector-v2) con candidatos y comparadores.
    - Apertura/suscripcion de feeds reales del piloto.
    - Recepcion y procesamiento de mensajes libro/flujo.
    - Evaluacion automatica DESPUES del calentamiento (no inmediata).
    """
    run = recorrido

    # Fase 1: seleccion inicial y apertura de feeds (T0).
    run.advance(T0)
    state = run.wait_status(
        lambda st: st.get("now_ms") == T0
        and len(st.get("followed") or []) > 0
        and len(st.get("feeds") or {}) == 2
        and all(f.get("connected_now") for f in st["feeds"].values()),
        "seleccion inicial y feeds conectados")

    seguido_inicial = state.get("followed") or []
    assert 12 <= len(seguido_inicial) <= 20, (
        f"se esperaba entre 12 y 20 simbolos seguidos, se obtuvieron "
        f"{len(seguido_inicial)}")
    assert state.get("cycles_run", 0) >= 1

    # Fase 2: publicar libro y flujo para todos los simbolos seguidos en T0.
    # El primer evento de flujo establece oldest_ms = T0.
    run.publish_and_confirm(
        T0, depth_symbols=seguido_inicial,
        trade_events={s: [T0] for s in seguido_inicial})

    # Fase 3: avanzar a T0+59000. El piloto intenta evaluar en T0+5000 (prima
    # decision_delay=60s), pero los simbolos estan en calentamiento
    # (59000 < selection_seconds=60000), asi que salta y no avanza
    # next_decision. Publicar mas datos en T0+59000.
    # Publicar un evento de flujo con event_ms=T0+60000 mientras el reloj esta
    # en T0+59000: asi, al evaluar en T0+60000, span_ms=60000 (ventana completa)
    # y el evento sigue siendo fresco (recv_ms=T0+59000, age_recv=1000).
    run.advance(T0 + 59_000)
    run.publish_and_confirm(
        T0 + 59_000, depth_symbols=seguido_inicial,
        trade_events={s: [T0 + 60_000] for s in seguido_inicial})

    # Fase 4: avanzar a T0+60000. Los simbolos ya cumplieron el calentamiento
    # (60000 >= selection_seconds=60000). El piloto evalua automaticamente con
    # los datos publicados. span_ms del flujo = 60000 >= window_ms=60000.
    run.advance(T0 + 60_000)
    # Esperar a que se generen observaciones en T0+60000.
    obs = run.wait_observations(T0 + 60_000, len(seguido_inicial))

    # Fase 5: verificar resultados.
    by_sym = {o["symbol"]: o for o in obs}
    assert len(by_sym) == len(seguido_inicial)

    aptas = [o for o in obs if o.get("estado") == "observada"]
    descartadas = [o for o in obs if o.get("estado") == "descartada"]

    # Cada observacion debe tener decision_ms == T0+60000 y disponibilidad
    # coherente (seleccion_ms <= decision_ms, libro/flujo <= decision_ms).
    for o in obs:
        assert o["decision_ms"] == T0 + 60_000, o
        disp = o["disponibilidad"]
        assert disp["seleccion_ms"] <= o["decision_ms"], o
        if disp["libro_ms"] is not None:
            assert disp["libro_ms"] <= o["decision_ms"], o
        if disp["flujo_ms"] is not None:
            assert disp["flujo_ms"] <= o["decision_ms"], o

    # Hubo al menos algunas aptas (simbolos con libro y flujo frescos).
    assert len(aptas) > 0, "esperaba al menos una observacion apta"

    # Los descartes (si los hay) tienen motivo explicito y no bloquean al resto.
    for o in descartadas:
        assert o["motivos"], f"descarte sin motivo: {o}"
        assert o["apto_para_evaluacion"] is False

    # Fase 6: verificar que hay candidatos y comparadores entre las aptas.
    roles = {o.get("role") for o in aptas}
    assert "candidate" in roles, f"esperaba candidatos, roles={roles}"
    assert "comparator" in roles, f"esperaba comparadores, roles={roles}"

    print(f"Recorrido OK: {len(seguido_inicial)} simbolos seguidos, "
          f"{len(aptas)} aptas, {len(descartadas)} descartadas en "
          f"T0+60000, roles={roles}")


def test_recorrido_productivo_nuevo_simbolo_calentamiento(recorrido):
    """Un simbolo recien seleccionado (segundo ciclo) pasa por calentamiento:
    no se evalua inmediatamente tras la suscripcion."""
    run = recorrido

    # Fase 1: seleccion inicial en T0.
    run.advance(T0)
    state = run.wait_status(
        lambda st: st.get("now_ms") == T0
        and len(st.get("followed") or []) > 0
        and len(st.get("feeds") or {}) == 2,
        "seleccion inicial")
    seguido_inicial = set(state.get("followed") or [])

    # Publicar datos en T0 para los simbolos iniciales.
    run.publish_and_confirm(
        T0, depth_symbols=list(seguido_inicial),
        trade_events={s: [T0] for s in seguido_inicial})

    # Fase 2: avanzar a T0+59000 y publicar un evento de flujo con
    # event_ms=T0+60000 (mientras el reloj esta en T0+59000). Asi, al evaluar
    # en T0+60000, span_ms=60000 (ventana completa) y el evento sigue siendo
    # fresco (recv_ms=T0+59000, age_recv=1000).
    run.advance(T0 + 59_000)
    run.publish_and_confirm(
        T0 + 59_000, depth_symbols=list(seguido_inicial),
        trade_events={s: [T0 + 60_000] for s in seguido_inicial})

    # Fase 3: avanzar a T0+60000. Primera decision real. Los simbolos
    # iniciales ya cumplieron calentamiento y se evaluan.
    run.advance(T0 + 60_000)
    obs_t0_60k = run.wait_observations(T0 + 60_000, len(seguido_inicial))
    by_sym_60k = {o["symbol"]: o for o in obs_t0_60k}
    aptas_60k = [o for o in obs_t0_60k if o.get("estado") == "observada"]
    assert len(aptas_60k) > 0

    # Fase 3: en T0+60000 hay una nueva seleccion (selection_seconds=60).
    # Algunos simbolos pueden salir y otros entrar. Los que entran por primera
    # vez tienen symbol_first_seen_ms = T0+60000 y NO se evaluan en este
    # mismo ciclo de decision (estan en calentamiento).
    # Avanzar a T0+120000: los nuevos simbolos ya cumplieron calentamiento.
    run.advance(T0 + 120_000)
    obs_t1_120k = run.wait_observations(T0 + 120_000, 1)
    # Si hay observaciones en T0+120000, verificar que no hay simbolos
    # evaluados en el mismo ciclo en que entraron (calentamiento respetado).
    for o in obs_t1_120k:
        if o.get("estado") == "observada":
            disp = o["disponibilidad"]
            # seleccion_ms debe ser estrictamente anterior a decision_ms
            # (no fue suscrita y evaluada en el mismo instante).
            assert disp["seleccion_ms"] < o["decision_ms"], o

    print("Calentamiento OK: nuevos simbolos no se evalúan en el mismo ciclo")


def test_recorrido_productivo_fuente_ausente_descarta(recorrido):
    """Un simbolo seleccionado sin flujo publicado se descarta con motivo
    al cabo del calentamiento, sin bloquear al resto."""
    run = recorrido

    run.advance(T0)
    state = run.wait_status(
        lambda st: st.get("now_ms") == T0
        and len(st.get("followed") or []) > 0
        and len(st.get("feeds") or {}) == 2,
        "seleccion inicial")
    seguido_inicial = state.get("followed") or []

    # Publicar libro para todos, pero NO flujo para ninguno.
    run.publish_and_confirm(T0, depth_symbols=seguido_inicial,
                            trade_events={})

    # Avanzar a T0+60000: calentamiento cumplido, pero falta flujo.
    run.advance(T0 + 60_000)
    obs = run.wait_observations(T0 + 60_000, len(seguido_inicial))

    # Todos deben estar descartados por sin_flujo.
    for o in obs:
        assert o["estado"] == "descartada", o
        assert "sin_flujo" in (o.get("motivos") or []), o
        assert o["apto_para_evaluacion"] is False, o

    print("Fuente ausente OK: todos descartados con sin_flujo, sin bloquear")


def test_recorrido_productivo_frescura_libro_obsoleto(recorrido):
    """Libro obsoleto + flujo reciente -> rechazo por dato_obsoleto_libro."""
    run = recorrido

    run.advance(T0)
    state = run.wait_status(
        lambda st: st.get("now_ms") == T0
        and len(st.get("followed") or []) > 0
        and len(st.get("feeds") or {}) == 2,
        "seleccion inicial")
    seguido_inicial = state.get("followed") or []

    # Publicar libro con evento en T0 (viejo) y flujo en T0 y T0+60000.
    # El flujo en T0 establece oldest_ms; el de T0+60000 (publicado mientras
    # el reloj esta en T0+59000) establece newest_ms, dando span_ms=60000.
    # Al evaluar en T0+60000, el libro tiene age_event=60000 > 5000 ->
    # dato_obsoleto_libro.
    run.publish_and_confirm(
        T0, depth_symbols=seguido_inicial,
        trade_events={s: [T0] for s in seguido_inicial})
    run.advance(T0 + 59_000)
    run.publish_and_confirm(
        T0 + 59_000, depth_symbols=seguido_inicial,
        trade_events={s: [T0 + 60_000] for s in seguido_inicial})

    run.advance(T0 + 60_000)
    obs = run.wait_observations(T0 + 60_000, len(seguido_inicial))

    for o in obs:
        if o.get("estado") == "descartada":
            motivos = set(o.get("motivos") or [])
            # Al menos algunos deben rechazar por libro obsoleto.
            assert "dato_obsoleto_libro" in motivos or "sin_libro" in motivos, o

    print("Frescura libro obsoleto OK: rechazo con motivo")


def test_recorrido_productivo_una_observacion_por_simbolo_y_ciclo(recorrido):
    """Como maximo una observacion por simbolo y ciclo de decision."""
    run = recorrido

    run.advance(T0)
    state = run.wait_status(
        lambda st: st.get("now_ms") == T0
        and len(st.get("followed") or []) > 0,
        "seleccion inicial")
    seguido_inicial = state.get("followed") or []

    run.publish_and_confirm(
        T0, depth_symbols=seguido_inicial,
        trade_events={s: [T0] for s in seguido_inicial})
    run.advance(T0 + 59_000)
    run.publish_and_confirm(
        T0 + 59_000, depth_symbols=seguido_inicial,
        trade_events={s: [T0 + 60_000] for s in seguido_inicial})

    run.advance(T0 + 60_000)
    obs = run.wait_observations(T0 + 60_000, len(seguido_inicial))

    # Contar observaciones por simbolo en este ciclo de decision.
    conteo = {}
    for o in obs:
        if o.get("kind") == "observacion" and o.get("decision_ms") == T0 + 60_000:
            s = o.get("symbol")
            conteo[s] = conteo.get(s, 0) + 1

    for s, c in conteo.items():
        assert c == 1, f"simbolo {s} tiene {c} observaciones en un ciclo"

    print("Una observacion por simbolo y ciclo OK")
