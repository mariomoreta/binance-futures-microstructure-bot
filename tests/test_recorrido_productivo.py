"""Recorrido productivo local: seleccion -> suscripcion -> recepcion -> evaluacion.

Usa proveedores HTTP/WS loopback, SQLite temporal y el CLI existente
(research_pilot.py) como subproceso. Control de reloj manual. No toca Binance
publica, ni endpoints privados, ni red publica de mercado.

Demuestra la correccion de coordinacion (captura_protocol_version=2):
- seleccionar -> suscribir -> acumular ventana requerida -> evaluar.
- Un simbolo recien suscrito no se evalua inmediatamente; espera al
  calentamiento acotado por ciclo (ventana de flujo = 60s, no selection_seconds
  = 300s).
- decision_ms sigue siendo el instante real de evaluacion.
- Como maximo una observacion por simbolo y ciclo.
- Una reincorporacion reinicia su calentamiento; no hereda cobertura ficticia.
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

# Universo suficiente para candidatos (12) + comparadores (8) = techo 20.
UNIVERSE = [f"S{i:03d}USDT" for i in range(25)]
# Dos mitades disjuntas de 12: la seleccion rota por llamada y luego reincorpora.
ROTATION_UNIVERSE = [f"R{i:03d}USDT" for i in range(24)]
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
    """Mercado REST simulado. Devuelve catalogo y ticker de todos los simbolos.

    Con ``rotation=True`` cada llamada a ticker/24hr destaca una mitad disjunta
    del universo, de modo que la seleccion rota y luego reincorpora simbolos.
    """
    def __init__(self, universe, rotation=False):
        self.universe = list(universe)
        self.rotation = rotation
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
                call = self.call_count
            half = len(self.universe) // 2
            rows = []
            for idx, symbol in enumerate(self.universe):
                if self.rotation:
                    high = (idx < half) if call % 2 == 1 else (idx >= half)
                    volume = 50_000_000.0 if high else 2_000_000.0
                    move = 1.0 if high else 0.05
                else:
                    volume = 50_000_000.0
                    move = 1.0 + 0.1 * idx
                rows.append({
                    "symbol": symbol,
                    "lastPrice": str(base_price(symbol, self.universe)),
                    "priceChangePercent": str(move),
                    "quoteVolume": str(volume),
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
                 max_symbols, max_candidates, max_comparators,
                 rotation=False):
        self.tmp = Path(tmp)
        self.out_dir = self.tmp / "out"
        self.obs_path = self.out_dir / "observaciones.jsonl"
        self.status_path = self.tmp / "status.json"
        self.clock = ClockFile(self.tmp / "clock.txt", T0)

        self.http = ControlledMarketHttp(universe, rotation=rotation)
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
        tmp, universe=UNIVERSE, duration_s=900, settle_s=60,
        selection_s=300, cycle_s=300, decision_delay_s=0,
        max_symbols=20, max_candidates=12, max_comparators=8)
    try:
        yield run
    finally:
        run.shutdown()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def recorrido_rotacion():
    """Piloto con seleccion rotatoria: mitades disjuntas y reincorporacion."""
    tmp = Path(tempfile.mkdtemp(prefix="recorrido-rot-"))
    run = ProductRun(
        tmp, universe=ROTATION_UNIVERSE, duration_s=600, settle_s=60,
        selection_s=120, cycle_s=60, decision_delay_s=0,
        max_symbols=12, max_candidates=12, max_comparators=0,
        rotation=True)
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
    # (59000 < symbol_warmup_ms=60000), asi que salta y no avanza
    # next_decision. Publicar mas datos en T0+59000.
    # Publicar un evento de flujo con event_ms=T0+60000 mientras el reloj esta
    # en T0+59000: asi, al evaluar en T0+60000, span_ms=60000 (ventana completa)
    # y el evento sigue siendo fresco (recv_ms=T0+59000, age_recv=1000).
    run.advance(T0 + 59_000)
    run.publish_and_confirm(
        T0 + 59_000, depth_symbols=seguido_inicial,
        trade_events={s: [T0 + 60_000] for s in seguido_inicial})

    # Fase 4: avanzar a T0+60000. Los simbolos ya cumplieron el calentamiento
    # (60000 >= symbol_warmup_ms=60000). El piloto evalua automaticamente con
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
    """Un simbolo recien seleccionado pasa por calentamiento:
    no se evalua inmediatamente tras la suscripcion, solo despues de
    acumular la ventana requerida."""
    run = recorrido

    # Fase 1: seleccion inicial en T0.
    run.advance(T0)
    state = run.wait_status(
        lambda st: st.get("now_ms") == T0
        and len(st.get("followed") or []) > 0
        and len(st.get("feeds") or {}) == 2,
        "seleccion inicial")
    seguido_inicial = state.get("followed") or []
    assert 12 <= len(seguido_inicial) <= 20

    # Publicar datos en T0 para los simbolos iniciales.
    run.publish_and_confirm(
        T0, depth_symbols=list(seguido_inicial),
        trade_events={s: [T0] for s in seguido_inicial})

    # Fase 2: avanzar a T0+5000. Los simbolos llevan solo 5s de calentamiento,
    # menos de los 60s requeridos. No debe haber evaluacion en este instante.
    run.advance(T0 + 5_000)
    obs_5k = [r for r in read_rows(run.obs_path)
              if r.get("kind") == "observacion"
              and r.get("decision_ms") == T0 + 5_000]
    assert len(obs_5k) == 0, (
        f"no debe haber evaluacion antes del calentamiento, se encontraron "
        f"{len(obs_5k)} observaciones en T+5000")

    # Fase 3: avanzar a T0+59000 y publicar flujo con event_ms=T0+60000
    # (mientras el reloj esta en T0+59000). Asi, al evaluar en T0+60000,
    # span_ms=60000 (ventana completa) y el evento sigue siendo fresco.
    run.advance(T0 + 59_000)
    run.publish_and_confirm(
        T0 + 59_000, depth_symbols=list(seguido_inicial),
        trade_events={s: [T0 + 60_000] for s in seguido_inicial})

    # Fase 4: avanzar a T0+60000. Los simbolos ya cumplieron el calentamiento
    # (60000 >= symbol_warmup_ms=60000). El piloto evalua automaticamente.
    run.advance(T0 + 60_000)
    obs_t0_60k = run.wait_observations(T0 + 60_000, len(seguido_inicial))

    # Verificar que cada simbolo tiene exactamente una observacion en T0+60000.
    conteo = {}
    for o in obs_t0_60k:
        if o.get("kind") == "observacion" and o.get("decision_ms") == T0 + 60_000:
            s = o.get("symbol")
            conteo[s] = conteo.get(s, 0) + 1
    for s, c in conteo.items():
        assert c == 1, f"simbolo {s} tiene {c} observaciones en un ciclo"

    # Verificar que hay al menos algunas aptas (simbolos con datos frescos).
    aptas = [o for o in obs_t0_60k if o.get("estado") == "observada"]
    assert len(aptas) > 0, "esperaba al menos una observacion apta tras calentamiento"

    print("Calentamiento OK: simbolos nuevos no se evaluan antes de los 60s, "
          "solo despues de cumplir la ventana")


def test_recorrido_productivo_reincorporacion_nuevo_periodo(
        recorrido_rotacion):
    """Un simbolo que sale y reincorpora espera un periodo nuevo.

    El calentamiento es la ventana de flujo 1m (60s), independiente de
    selection_seconds (120s). La reincorporacion renueva first_seen y la
    evaluacion ocurre despues de esa ventana y antes de la siguiente seleccion,
    sin barrera manual de decision.
    """
    run = recorrido_rotacion

    run.advance(T0)
    state = run.wait_status(
        lambda st: st.get("now_ms") == T0
        and len(st.get("followed") or []) >= 8
        and len(st.get("feeds") or {}) == 2,
        "seleccion inicial")
    first = set(state["followed"])
    assert 8 <= len(first) <= 12
    assert state.get("symbol_warmup_ms") == 60_000
    assert set(state["symbol_first_seen_ms"]) == first

    # Primer corte: exactamente al completar la ventana de 60s.
    e0 = T0 + 60_000
    run.advance(e0 - 1_000)
    run.publish_and_confirm(
        e0 - 1_000, depth_symbols=sorted(first),
        trade_events={s: list(range(T0 - 2_000, e0 + 1, 1_000))
                      for s in first})
    run.advance(e0)
    obs0 = run.wait_observations(e0, len(first))
    assert all(o["decision_ms"] == e0 for o in obs0), obs0
    assert all(o["apto_para_evaluacion"] for o in obs0), obs0

    # Segunda seleccion (120s): rota a la mitad disjunta. No se evalua en el
    # mismo instante de la suscripcion.
    e1 = T0 + 120_000
    run.advance(e1)
    state = run.wait_status(
        lambda st: st.get("cycles_run", 0) >= 2,
        "segunda seleccion")
    second = set(state["followed"])
    assert second.isdisjoint(first)
    assert not [r for r in read_rows(run.obs_path)
                if r.get("kind") == "observacion"
                and r.get("decision_ms") == e1]

    # Sembrar la ventana del nuevo conjunto y evaluarlo en e2 (tras 60s).
    run.publish_and_confirm(
        e1, depth_symbols=sorted(second),
        trade_events={s: list(range(e1 - 60_000, e1 + 1, 1_000))
                      for s in second})
    e2 = T0 + 180_000
    run.advance(e2 - 1_000)
    run.publish_and_confirm(
        e2 - 1_000, depth_symbols=sorted(second),
        trade_events={s: [e2] for s in second})
    run.advance(e2)
    obs1 = run.wait_observations(e2, len(second))
    assert all(o["decision_ms"] == e2 for o in obs1), obs1
    assert any(o["apto_para_evaluacion"] for o in obs1), obs1

    # Tercera seleccion (240s): reincorpora el primer conjunto con periodo
    # nuevo; no hereda la cobertura del periodo anterior.
    e3 = T0 + 240_000
    run.advance(e3)
    state = run.wait_status(
        lambda st: st.get("cycles_run", 0) >= 3,
        "tercera seleccion")
    third = set(state["followed"])
    assert third == first
    assert all(state["symbol_first_seen_ms"][s] == e3 for s in third)
    assert not [r for r in read_rows(run.obs_path)
                if r.get("kind") == "observacion"
                and r.get("decision_ms") == e3]

    # Evaluacion en e4: 60s despues de reincorporar y antes de la siguiente
    # seleccion (e3 + 120s).
    run.publish_and_confirm(
        e3, depth_symbols=sorted(third),
        trade_events={s: list(range(e3 - 60_000, e3 + 1, 1_000))
                      for s in third})
    e4 = T0 + 300_000
    assert e4 < e3 + 120_000
    run.advance(e4 - 1_000)
    run.publish_and_confirm(
        e4 - 1_000, depth_symbols=sorted(third),
        trade_events={s: [e4] for s in third})
    run.advance(e4)
    obs2 = run.wait_observations(e4, len(third))
    for o in obs2:
        assert o["decision_ms"] == e4, o
        disp = o["disponibilidad"]
        assert disp["seleccion_ms"] == e3, o
        assert disp["seleccion_ms"] < o["decision_ms"], o
    assert any(o["apto_para_evaluacion"] for o in obs2), obs2

    # El ciclo registra la salida y la reincorporacion (trazabilidad).
    ciclos = [r for r in read_rows(run.obs_path) if r.get("kind") == "ciclo"]
    salidas = [s["symbol"] for c in ciclos
               for s in (c.get("seguimiento") or {}).get("salidas", [])]
    entradas = [s["symbol"] for c in ciclos
                for s in (c.get("seguimiento") or {}).get("entradas", [])]
    assert first & set(salidas), "el primer conjunto debe registrar salida"
    assert first & set(entradas), "el primer conjunto debe registrar entrada"

    print(f"Reincorporacion OK: {len(first)} simbolos con periodo nuevo en "
          f"e3={e3}, evaluados en e4={e4} antes de la siguiente seleccion")


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
    run.publish_and_confirm(
        T0 + 60_000, depth_symbols=seguido_inicial,
        trade_events={})
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
    # No se refresca el libro: al evaluar en T0+60000 su age_event=60000
    # supera max_data_age_ms -> dato_obsoleto_libro.
    run.publish_and_confirm(
        T0, depth_symbols=seguido_inicial,
        trade_events={s: [T0] for s in seguido_inicial})
    run.advance(T0 + 59_000)
    run.publish_and_confirm(
        T0 + 59_000, depth_symbols=(),
        trade_events={s: [T0 + 60_000] for s in seguido_inicial})

    run.advance(T0 + 60_000)
    obs = run.wait_observations(T0 + 60_000, len(seguido_inicial))

    rechazadas = [o for o in obs if o.get("estado") == "descartada"]
    assert rechazadas, obs
    for o in rechazadas:
        motivos = set(o.get("motivos") or [])
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
