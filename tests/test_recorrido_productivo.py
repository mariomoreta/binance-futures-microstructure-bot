"""Recorrido productivo local: seleccion -> suscripcion -> recepcion -> evaluacion.

Usa proveedores HTTP/WS loopback, SQLite temporal y el CLI existente
(research_pilot.py) como subproceso. Control de reloj manual. No toca Binance
publica, ni endpoints privados, ni red publica de mercado.

Demuestra la correccion de coordinacion (captura_protocol_version=3):
- seleccionar -> suscribir -> recibir eventos -> ventana observada completa ->
  evaluar. Cada evento se publica con event_ms <= reloj: no hay fechas futuras
  ni historia precargada.
- Un simbolo recien suscrito no se evalua inmediatamente; el corte nominal
  (suscripcion + 60 s) no consume la oportunidad si la ventana observada aun es
  menor. Se espera cobertura real, con espera maxima acotada (+60 s).
- decision_ms sigue siendo el instante real de evaluacion.
- Como maximo una observacion por simbolo y ciclo.
- Una reincorporacion reinicia su calentamiento; no hereda cobertura ni usa
  eventos anteriores al nuevo periodo.
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
                 rotation=False, run_id="recorrido-productivo"):
        self.tmp = Path(tmp)
        self.out_dir = self.tmp / "out"
        self.obs_path = self.out_dir / "observaciones.jsonl"
        self.status_path = self.tmp / "status.json"
        self.clock = ClockFile(self.tmp / "clock.txt", T0)
        # Auditoria de cronologia: cada evento publicado con su reloj.
        self.published = []

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
            "--run-id", run_id, "--out-dir", str(self.out_dir),
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
        self.cmd = cmd

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
        """Publica burst WS y espera confirmacion del estado del piloto.

        Exige cronologia real: ``event_ms <= reloj`` en el momento de publicar.
        Se registra cada publicacion para auditarla al final.
        """
        self.wait_status(
            lambda st: bool(st.get("feeds")) and all(
                f.get("connected_now") for f in st["feeds"].values()),
            "feeds conectados antes de publicar")
        events = {k: list(v) for k, v in (trade_events or {}).items()}
        clock_now = self.clock.read()
        for symbol in depth_symbols:
            self.published.append({"symbol": symbol, "kind": "libro",
                                   "event_ms": int(instant_ms),
                                   "clock_ms": clock_now})
        for symbol, series in events.items():
            for event_ms in series:
                self.published.append({"symbol": symbol, "kind": "flujo",
                                       "event_ms": int(event_ms),
                                       "clock_ms": clock_now})
        futuros = [p for p in self.published if p["event_ms"] > p["clock_ms"]]
        if futuros:
            raise AssertionError(
                f"evento con fecha futura al publicar: {futuros[:3]}")
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

    def wait_first_cut(self, after_ms, expected, before_ms, timeout=90.0):
        """Primer corte automatico con decision_ms en (after, before)."""
        def pred(rows):
            found = [r for r in rows
                     if r.get("kind") == "observacion"
                     and after_ms < int(r.get("decision_ms") or 0) < before_ms]
            return found if len(found) >= expected else None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = pred(read_rows(self.obs_path))
            if found:
                return found
            if self.proc.poll() is not None:
                raise AssertionError("piloto termino esperando el primer corte")
            time.sleep(0.02)
        raise AssertionError(
            f"timeout {timeout}s esperando {expected} obs con decision_ms en "
            f"({after_ms}, {before_ms})")

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
# Recorrido productivo con recepcion cronologica (sin fechas futuras)
# ---------------------------------------------------------------------------

# Primera recepcion DESPUES de la suscripcion: el corte nominal
# (suscripcion + 60 s) nunca puede coincidir con una ventana ya completa.
PRIMERA_RECEPCION_MS = 1_000
# Ultima recepcion del primer corte: 61_000 - 1_000 = 60_000 de ventana
# observada real, construida durante el minuto de seguimiento.
VENTANA_OBSERVADA_MS = 61_000
PASO_MS = 5_000


def seleccion_inicial(run, minimo=1):
    run.advance(T0)
    return run.wait_status(
        lambda st: st.get("now_ms") == T0
        and len(st.get("followed") or []) >= minimo
        and len(st.get("feeds") or {}) == 2
        and all(f.get("connected_now") for f in st["feeds"].values()),
        "seleccion inicial y feeds conectados")


def publicar_cronologico(run, symbols, *, desde_ms=PRIMERA_RECEPCION_MS,
                         hasta_ms=VENTANA_OBSERVADA_MS, paso_ms=PASO_MS,
                         sin_flujo=(), sin_libro=(), base_ms=T0):
    """Publica libro y flujo con ``event_ms == reloj`` en orden temporal.

    No publica fechas futuras ni precarga historia: cada evento existe cuando
    el reloj ya lo admite. Los simbolos de ``sin_flujo`` reciben solo libro y
    los de ``sin_libro`` solo flujo.
    """
    sin_flujo = set(sin_flujo)
    sin_libro = set(sin_libro)
    for offset in range(desde_ms, hasta_ms + 1, paso_ms):
        t = base_ms + offset
        run.advance(t)
        run.publish_and_confirm(
            t,
            depth_symbols=[s for s in symbols if s not in sin_libro],
            trade_events={s: [t] for s in symbols if s not in sin_flujo})


def observaciones_desde(run, decision_min_ms):
    return [r for r in read_rows(run.obs_path)
            if r.get("kind") == "observacion"
            and int(r.get("decision_ms") or 0) >= decision_min_ms]


def test_recorrido_productivo_seleccion_suscripcion_recepcion_evaluacion(
        recorrido):
    """Cadena completa: seleccion -> suscripcion -> recepcion -> evaluacion.

    La ventana se construye con eventos recibidos cronologicamente: a T0+60 s
    la cobertura observada es 55 s (primera recepcion T0+1 s), asi que el corte
    no puede consumirse; la evaluacion llega al completarse la ventana real y
    antes de la siguiente seleccion (T0+300 s).
    """
    run = recorrido
    state = seleccion_inicial(run)
    seguido = state.get("followed") or []
    assert 12 <= len(seguido) <= 20, seguido
    roles_seleccion = set((state.get("roles") or {}).values())
    assert {"candidate", "comparator"} <= roles_seleccion, roles_seleccion

    # Recepcion cronologica hasta T0+60000: ventana observada = 55 s.
    publicar_cronologico(run, seguido, hasta_ms=60_000)
    run.advance(T0 + 60_000)
    assert not observaciones_desde(run, T0 + 60_000), (
        "no debe evaluarse con ventana observada incompleta")
    estado_60 = run.status() or {}
    assert estado_60.get("evaluations_run") == 0, estado_60
    assert estado_60.get("warmup_deferrals", 0) >= 1, estado_60
    assert estado_60.get("warmup_pending"), estado_60

    # Completar la ventana observada (60 s reales) y dejar correr el corte.
    publicar_cronologico(run, seguido, desde_ms=VENTANA_OBSERVADA_MS,
                         hasta_ms=VENTANA_OBSERVADA_MS)
    run.advance(T0 + 62_000)
    obs = run.wait_first_cut(T0 + 60_000, len(seguido), T0 + 300_000)

    by_sym = {o["symbol"]: o for o in obs}
    assert set(by_sym) == set(seguido), (set(by_sym) ^ set(seguido))
    decisiones = {o["decision_ms"] for o in obs}
    assert len(decisiones) == 1, decisiones
    decision = decisiones.pop()
    assert T0 + 60_000 < decision < T0 + 300_000, decision

    for o in obs:
        assert o["estado"] == "observada", o
        assert o["apto_para_evaluacion"] is True, o
        assert o["motivos"] == [], o
        cobertura = o["cobertura"]
        assert cobertura["flujo_presente"] is True, o
        assert cobertura["flujo_ventana_completa"] is True, o
        assert cobertura["libro_presente"] is True, o
        disp = o["disponibilidad"]
        assert disp["seleccion_ms"] <= o["decision_ms"], o
        assert disp["libro_ms"] <= o["decision_ms"], o
        assert disp["flujo_ms"] <= o["decision_ms"], o

    # Exactamente una observacion por simbolo en el corte.
    conteo = {}
    for r in read_rows(run.obs_path):
        if r.get("kind") == "observacion":
            key = (r["symbol"], r["decision_ms"])
            conteo[key] = conteo.get(key, 0) + 1
    assert all(c == 1 for c in conteo.values()), conteo

    roles = {o["role"] for o in obs}
    assert roles == {"candidate", "comparator"}, roles

    estado = run.status() or {}
    assert estado.get("last_nominal_cut_ms") == T0 + 60_000, estado
    assert estado.get("last_cut_ms") == decision, estado
    assert estado.get("last_cut_reason") == "cobertura_completa", estado

    # Cronologia: ningun evento se publico con fecha futura.
    assert run.published, "no se registro ninguna publicacion"
    assert all(p["event_ms"] <= p["clock_ms"] for p in run.published)

    print(f"Recorrido OK: {len(seguido)} simbolos, corte nominal "
          f"{estado.get('last_nominal_cut_ms')}, evaluacion efectiva "
          f"{decision}, roles={roles}")


def test_recorrido_productivo_nuevo_simbolo_calentamiento(recorrido):
    """Un simbolo recien suscrito no se evalua hasta tener cobertura real."""
    run = recorrido
    state = seleccion_inicial(run)
    seguido = state.get("followed") or []
    assert 12 <= len(seguido) <= 20, seguido

    # A T0+5000 no hay ventana ni evaluacion.
    publicar_cronologico(run, seguido, hasta_ms=5_000)
    assert not observaciones_desde(run, T0 + 5_000), (
        "no debe haber evaluacion antes del calentamiento")

    # A T0+60000 la ventana observada es 55 s: sigue sin ser evaluable.
    publicar_cronologico(run, seguido, desde_ms=10_000, hasta_ms=60_000)
    run.advance(T0 + 60_000)
    assert not observaciones_desde(run, T0 + 5_000)

    publicar_cronologico(run, seguido, desde_ms=VENTANA_OBSERVADA_MS,
                         hasta_ms=VENTANA_OBSERVADA_MS)
    run.advance(T0 + 62_000)
    obs = run.wait_first_cut(T0 + 60_000, len(seguido), T0 + 300_000)

    conteo = {}
    for o in obs:
        conteo[o["symbol"]] = conteo.get(o["symbol"], 0) + 1
    assert set(conteo) == set(seguido), (set(conteo) ^ set(seguido))
    for symbol, cuenta in conteo.items():
        assert cuenta == 1, f"{symbol} tiene {cuenta} observaciones"
    assert any(o["apto_para_evaluacion"] for o in obs), obs

    print("Calentamiento OK: sin evaluacion antes de cobertura real")


def test_recorrido_productivo_reincorporacion_nuevo_periodo(
        recorrido_rotacion):
    """Un simbolo que sale y vuelve espera un periodo nuevo sin historia.

    No se precarga el minuto anterior: la primera recepcion de cada periodo
    ocurre despues de la nueva suscripcion, y la evaluacion llega al completar
    la ventana observada, antes de la siguiente seleccion.
    """
    run = recorrido_rotacion
    state = seleccion_inicial(run, minimo=8)
    first = set(state["followed"])
    assert 8 <= len(first) <= 12, first
    assert state.get("symbol_warmup_ms") == 60_000, state
    assert set(state["symbol_first_seen_ms"]) == first
    assert state.get("symbol_first_flow_ms") == {}

    # Periodo 1: recepcion cronologica desde T0+1000 (sin evento en T0).
    publicar_cronologico(run, sorted(first))
    run.advance(T0 + 62_000)
    obs0 = run.wait_first_cut(T0 + 60_000, len(first), T0 + 120_000)
    assert all(o["apto_para_evaluacion"] for o in obs0), obs0
    corte0 = obs0[0]["decision_ms"]

    # Segunda seleccion (120 s): rota a la mitad disjunta.
    e1 = T0 + 120_000
    run.advance(e1)
    state = run.wait_status(
        lambda st: st.get("cycles_run", 0) >= 2, "segunda seleccion")
    second = set(state["followed"])
    assert second.isdisjoint(first), (second & first)
    assert not observaciones_desde(run, e1)[:1] or all(
        o["decision_ms"] != e1 for o in observaciones_desde(run, e1))

    # Periodo 2: primera recepcion DESPUES de suscribir (e1+1000).
    publicar_cronologico(run, sorted(second), base_ms=e1)
    run.advance(e1 + 62_000)
    obs1 = run.wait_first_cut(e1 + 60_000, len(second), e1 + 120_000)
    assert all(o["decision_ms"] > e1 for o in obs1), obs1
    assert any(o["apto_para_evaluacion"] for o in obs1), obs1

    # Tercera seleccion (240 s): reincorpora el primer conjunto.
    e3 = T0 + 240_000
    run.advance(e3)
    state = run.wait_status(
        lambda st: st.get("cycles_run", 0) >= 3, "tercera seleccion")
    third = set(state["followed"])
    assert third == first, (third ^ first)
    assert all(state["symbol_first_seen_ms"][s] == e3 for s in third)
    # Sin cobertura heredada: la primera recepcion del periodo es posterior.
    for symbol in third:
        assert symbol not in state["symbol_first_flow_ms"] or (
            state["symbol_first_flow_ms"][symbol] > e3), state
    assert not [o for o in observaciones_desde(run, e3)
                if o["decision_ms"] == e3]

    # Periodo 3: recepcion cronologica nueva, sin precarga.
    publicar_cronologico(run, sorted(third), base_ms=e3)
    run.advance(e3 + 62_000)
    obs2 = run.wait_first_cut(e3 + 60_000, len(third), e3 + 120_000)
    for o in obs2:
        assert o["decision_ms"] > e3, o
        disp = o["disponibilidad"]
        assert disp["seleccion_ms"] == e3, o
        assert disp["seleccion_ms"] < o["decision_ms"], o
        assert disp["flujo_ms"] > e3, o
    assert any(o["apto_para_evaluacion"] for o in obs2), obs2

    # El ciclo registra salida y reincorporacion.
    ciclos = [r for r in read_rows(run.obs_path) if r.get("kind") == "ciclo"]
    salidas = [s["symbol"] for c in ciclos
               for s in (c.get("seguimiento") or {}).get("salidas", [])]
    entradas = [s["symbol"] for c in ciclos
                for s in (c.get("seguimiento") or {}).get("entradas", [])]
    assert first & set(salidas), "el primer conjunto debe registrar salida"
    assert first & set(entradas), "el primer conjunto debe registrar entrada"

    print(f"Reincorporacion OK: {len(first)} simbolos con periodo nuevo en "
          f"{e3}, evaluados en {obs2[0]['decision_ms']} (periodo 1: {corte0})")


def test_recorrido_productivo_fuente_ausente_descarta(recorrido):
    """Un simbolo sin flujo espera el maximo acotado y se descarta con motivo.

    Los demas siguen siendo evaluables cuando la espera vence; ninguno queda
    marcado como apto sin datos.
    """
    run = recorrido
    state = seleccion_inicial(run)
    seguido = state.get("followed") or []
    assert 12 <= len(seguido) <= 20, seguido
    sin_flujo = seguido[-1]

    publicar_cronologico(run, seguido, sin_flujo=[sin_flujo])
    # A T0+60000 el resto ya tiene ventana; el simbolo sin flujo no.
    assert not observaciones_desde(run, T0 + 60_000)
    # Sigue sin evaluarse durante la espera acotada.
    run.advance(T0 + 120_000)
    assert not observaciones_desde(run, T0 + 60_000)

    # Antes del vencimiento se refrescan las fuentes del resto.
    run.publish_and_confirm(
        T0 + 120_000,
        depth_symbols=[s for s in seguido if s != sin_flujo],
        trade_events={s: [T0 + 120_000] for s in seguido
                      if s != sin_flujo})
    run.advance(T0 + 121_000)
    obs = run.wait_first_cut(T0 + 60_000, len(seguido), T0 + 300_000)

    estado = run.status() or {}
    assert estado.get("last_cut_reason") == "espera_maxima_agotada", estado

    by_sym = {o["symbol"]: o for o in obs}
    assert set(by_sym) == set(seguido)
    retrasado = by_sym[sin_flujo]
    assert retrasado["estado"] == "descartada", retrasado
    assert "sin_flujo" in (retrasado.get("motivos") or []), retrasado
    assert retrasado["apto_para_evaluacion"] is False, retrasado
    for symbol, o in by_sym.items():
        if symbol == sin_flujo:
            continue
        assert o["apto_para_evaluacion"] is True, o
        assert o["estado"] == "observada", o

    print(f"Fuente ausente OK: {sin_flujo} descartado con sin_flujo tras "
          f"espera acotada; {len(seguido) - 1} evaluados")


def test_recorrido_productivo_frescura_libro_obsoleto(recorrido):
    """Libro obsoleto con flujo fresco: espera acotada y rechazo con motivo."""
    run = recorrido
    state = seleccion_inicial(run)
    seguido = state.get("followed") or []
    assert 12 <= len(seguido) <= 20, seguido

    # Solo el primer libro; el flujo se mantiene cronologico.
    publicar_cronologico(run, seguido, hasta_ms=1_000)
    publicar_cronologico(run, seguido, desde_ms=6_000,
                         hasta_ms=VENTANA_OBSERVADA_MS, sin_libro=seguido)

    # La espera maxima (60 s extra) vence en T0+121000.
    run.advance(T0 + 120_000)
    run.publish_and_confirm(
        T0 + 120_000, depth_symbols=(),
        trade_events={s: [T0 + 120_000] for s in seguido})
    run.advance(T0 + 121_000)
    obs = run.wait_first_cut(T0 + 60_000, len(seguido), T0 + 300_000)

    estado = run.status() or {}
    assert estado.get("last_cut_reason") == "espera_maxima_agotada", estado

    rechazadas = [o for o in obs if o["estado"] == "descartada"]
    assert len(rechazadas) == len(obs), obs
    for o in rechazadas:
        motivos = set(o.get("motivos") or [])
        assert "dato_obsoleto_libro" in motivos, o
        assert o["apto_para_evaluacion"] is False, o

    print("Frescura libro obsoleto OK: espera acotada y rechazo con motivo")


def test_recorrido_productivo_una_observacion_por_simbolo_y_ciclo(recorrido):
    """Como maximo una observacion por simbolo y ciclo de decision."""
    run = recorrido
    state = seleccion_inicial(run)
    seguido = state.get("followed") or []

    publicar_cronologico(run, seguido)
    run.advance(T0 + 62_000)
    obs = run.wait_first_cut(T0 + 60_000, len(seguido), T0 + 300_000)
    decision = obs[0]["decision_ms"]

    conteo = {}
    for o in obs:
        conteo[o["symbol"]] = conteo.get(o["symbol"], 0) + 1
    assert set(conteo) == set(seguido)
    assert all(c == 1 for c in conteo.values()), conteo

    # Avanzar y publicar dentro del mismo ciclo no duplica observaciones.
    publicar_cronologico(run, seguido, desde_ms=decision - T0 + 1_000,
                         hasta_ms=decision - T0 + 1_000)
    run.advance(decision + 5_000)
    repetidas = [o for o in observaciones_desde(run, T0 + 60_000)
                 if o["decision_ms"] != decision]
    assert not repetidas, repetidas

    estado = run.status() or {}
    assert estado.get("evaluations_run") == 1, estado

    print("Una observacion por simbolo y ciclo OK")
