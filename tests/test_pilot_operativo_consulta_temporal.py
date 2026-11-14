"""Aceptacion local del BORDE TEMPORAL de la consulta operativa.

Alcance: correccion de implementacion y su aceptacion, **sin mercado**. Todo
ocurre en loopback (HTTP y WS), con reloj manual, CLI real como subproceso y
almacenamiento temporal. No se abre ningun socket publico ni se consultan
apis de Binance.

El recorrido que se ejerce es el PRODUCTIVO completo:

    seleccion -> observacion -> consulta de trayectoria -> adaptador -> motor
    -> persistencia

No se llama al adaptador con una lista de velas preparada por el test: las
velas las produce el proveedor loopback, que respeta el filtrado real del
venue (``openTime >= startTime``) y el tope de filas (``limit``).

Defecto que se cubre: con ``start_ms = decision_ms - step_ms`` la vela 1m
plenamente cerrada en T queda EXCLUIDA de la consulta siempre que ``T`` no
este alineado al minuto, y la serie empieza en la vela que CONTIENE a T (su
cierre es posterior a T y no puede ser la referencia). El resultado era una
abstencion artificial ("sin vela 1m plenamente conocida en T") en el 100 % de
las observaciones de la ventana `exp-v2-ventana-2-20261112a`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.test_research_pilot import (  # noqa: E402
    MINUTE,
    T0,
    ClockFile,
    MarketHttp,
    WsProvider,
    find_free_port,
    kline_price,
    read_rows,
    start_ws_server,
)
import research_pilot as rp  # noqa: E402

HORIZON_MS = 3_600_000          # horizonte operativo congelado (60 min)
STEP_MS = 60_000                # paso de la serie 1m
UMBRAL_SIN_VELA = "sin vela 1m plenamente conocida en T"

# Desfases exigidos por la aceptacion (incluidos los publicados en la
# ventana real: 12 527 ms y 19 298 ms) y los bordes de minuto.
DESFAZES_EXIGIDOS = [
    ("exacto_en_el_minuto", 0),
    ("un_ms_despues", 1),
    ("desfase_publicado_12527", 12_527),
    ("desfase_publicado_19298", 19_298),
    ("cerca_del_cierre_59998", 59_998),
    ("cerca_del_cierre_59999", 59_999),
    ("cambio_de_minuto_mas_1ms", MINUTE + 1),
]


# ---------------------------------------------------------------------------
# Proveedor HTTP loopback fiel: filtrado por apertura y tope de filas
# ---------------------------------------------------------------------------


class TrajectoryHttp(MarketHttp):
    """Proveedor REST loopback que reproduce el contrato del venue.

    - ``klines`` devuelve solo velas con ``openTime >= startTime`` (igual que
      el venue) y como mucho ``limit`` filas (la primera vela es la que
      abre en el primer multiplo del paso >= startTime).
    - Registra cada consulta de trayectoria (parametros + filas devueltas)
      para poder verificar el borde, el tope y la cobertura del horizonte.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.trajectory_requests = []
        self._traj_lock = threading.Lock()

    def _handle(self, handler):
        parsed = urlsplit(handler.path)
        if parsed.path == "/fapi/v1/klines":
            params = parse_qs(parsed.query)
            limit = int(params.get("limit", ["0"])[0] or 0)
            symbol = params.get("symbol", [""])[0].upper()
            start = int(params.get("startTime", [0])[0])
            end = int(params.get("endTime", [0])[0])
            now_ms = int(self.clock_ms_fn()) if self.clock_ms_fn else None
            # Filtrado por apertura del venue: la primera fila abre en el
            # primer multiplo del paso que sea >= startTime.
            open_time = rp.ceil_ms(start, STEP_MS)
            rows = []
            t = open_time
            while t <= end:
                price = kline_price(symbol, t, self.universe)
                close_time = t + STEP_MS - 1
                if now_ms is not None and t > now_ms:
                    break
                close_price = f"{price:.8f}"
                close_ts = close_time
                if now_ms is not None and close_time > now_ms:
                    close_price = None
                    close_ts = None
                rows.append([t, f"{price:.8f}", f"{price * 1.001:.8f}",
                             f"{price * 0.999:.8f}", close_price, "100",
                             close_ts, "100000", "10", "50", "50000", "0"])
                t += STEP_MS
                # Tope de filas del venue: como mucho ``limit``.
                if limit > 0 and len(rows) >= limit:
                    break
            if limit > 1:
                with self._traj_lock:
                    self.trajectory_requests.append({
                        "symbol": symbol,
                        "params": {"startTime": start, "endTime": end,
                                   "limit": limit, "interval": "1m"},
                        "n_rows": len(rows),
                        "first_open_ms": rows[0][0] if rows else None,
                        "last_open_ms": rows[-1][0] if rows else None,
                        "rows": rows,
                    })
            self.klines_calls += 1
            if limit > 1:
                self.klines_calls_trajectory += 1
            else:
                self.klines_calls_precio += 1
            body = json.dumps(rows).encode("utf-8")
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.send_header("X-MBX-USED-WEIGHT-1M", "1")
            handler.end_headers()
            handler.wfile.write(body)
            return
        super()._handle(handler)


class MissingReferenceHttp(TrajectoryHttp):
    """Proveedor sin la vela de referencia: el dato falta de verdad.

    Descarta la vela que abre en ``T0`` (la unica plenamente cerrada en T
    para las decisiones de esta aceptacion). Sirve para comprobar que la
    correccion NO fabrica datos: si la referencia no existe, la regla sigue
    absteniendose de forma explicita.
    """

    def _handle(self, handler):
        parsed = urlsplit(handler.path)
        if parsed.path == "/fapi/v1/klines":
            params = parse_qs(parsed.query)
            limit = int(params.get("limit", ["0"])[0] or 0)
            if limit > 1:
                start = int(params.get("startTime", [0])[0])
                end = int(params.get("endTime", [0])[0])
                now_ms = int(self.clock_ms_fn()) if self.clock_ms_fn else None
                rows = []
                t = rp.ceil_ms(start, STEP_MS)
                while t <= end:
                    if t == T0:
                        t += STEP_MS
                        continue
                    price = kline_price(
                        params.get("symbol", [""])[0].upper(), t, self.universe)
                    close_time = t + STEP_MS - 1
                    if now_ms is not None and t > now_ms:
                        break
                    close_price = f"{price:.8f}"
                    close_ts = close_time
                    if now_ms is not None and close_time > now_ms:
                        close_price = None
                        close_ts = None
                    rows.append([t, f"{price:.8f}", f"{price * 1.001:.8f}",
                                 f"{price * 0.999:.8f}", close_price, "100",
                                 close_ts, "100000", "10", "50", "50000", "0"])
                    t += STEP_MS
                    if limit > 0 and len(rows) >= limit:
                        break
                with self._traj_lock:
                    self.trajectory_requests.append({
                        "symbol": params.get("symbol", [""])[0].upper(),
                        "params": {"startTime": start, "endTime": end,
                                   "limit": limit, "interval": "1m"},
                        "n_rows": len(rows),
                        "first_open_ms": rows[0][0] if rows else None,
                        "last_open_ms": rows[-1][0] if rows else None,
                        "rows": rows,
                    })
                body = json.dumps(rows).encode("utf-8")
                handler.send_response(200)
                handler.send_header("Content-Type", "application/json")
                handler.send_header("Content-Length", str(len(body)))
                handler.send_header("X-MBX-USED-WEIGHT-1M", "1")
                handler.end_headers()
                handler.wfile.write(body)
                return
        super()._handle(handler)


# ---------------------------------------------------------------------------
# CLI real con proveedores loopback, reloj manual y almacenamiento temporal
# ---------------------------------------------------------------------------


class OperativeRun:
    """Ejecuta ``scripts/research_pilot.py`` como subproceso real."""

    def __init__(self, tmp, *, universe, moves=None, http_cls=TrajectoryHttp,
                 duration_s=600, settle_s=4_200, selection_s=3_600,
                 cycle_s=300, max_symbols=5, gate=True, run_id="operativo-borde"):
        self.tmp = Path(tmp)
        self.universe = list(universe)
        self.out_dir = self.tmp / "out"
        self.obs_path = self.out_dir / "observaciones.jsonl"
        self.operativo_path = self.out_dir / "resultado_operativo.jsonl"
        self.status_path = self.tmp / "status.json"
        self.gate_path = self.tmp / "gate.json"
        self.stop_path = self.tmp / "stop.txt"
        self.clock = ClockFile(self.tmp / "clock.txt", T0)

        def _clock_ms() -> int:
            return int(self.clock.read())

        self.http = http_cls(self.universe, clock_ms_fn=_clock_ms,
                             moves=moves or {})
        self.http_port = find_free_port()
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", self.http_port), self.http.make_handler())
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

        self.ws = WsProvider(self.universe)
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
            "--decision-delay-seconds", "5",
            "--max-symbols", str(max_symbols),
            "--max-candidates", str(max_symbols),
            "--max-comparators", "0",
            "--min-quote-volume", "1000000",
            "--horizons", "5m=300000,15m=900000,60m=3600000",
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
            "--tick-ms", "20",
            "--clock", "manual", "--clock-file", str(self.tmp / "clock.txt"),
            "--status-file", str(self.status_path),
            "--stop-file", str(self.stop_path),
        ]
        if gate:
            cmd.extend(["--decision-gate-file", str(self.gate_path)])
        self.cmd = cmd
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        self.stdout = ""
        self.stderr = ""

    # -- sincronizacion ---------------------------------------------------

    def status(self):
        deadline = time.monotonic() + 0.25
        while True:
            try:
                return json.loads(self.status_path.read_text(encoding="utf-8"))
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
                raise AssertionError(
                    f"el piloto termino esperando {what}: rc={self.proc.poll()} "
                    f"stdout={self.stdout!r} stderr={self.stderr!r}")
            time.sleep(0.02)
        raise AssertionError(f"timeout esperando {what}; ultimo status={last}")

    def advance(self, instant_ms, timeout=60.0):
        self.clock.set(instant_ms)
        return self.wait_status(
            lambda st: st.get("now_ms") == instant_ms,
            f"reloj en {instant_ms}", timeout)

    def wait_ready(self, expected_followed, timeout=60.0):
        def ready(state):
            feeds = state.get("feeds") or {}
            return (state.get("now_ms") == T0
                    and len(state.get("followed") or []) == expected_followed
                    and len(feeds) == 2
                    and all(f.get("connected_now") for f in feeds.values()))
        return self.wait_status(ready, "seleccion inicial y feeds", timeout)

    def publish_and_confirm(self, base_state, instant_ms, depth_symbols,
                            trade_events):
        self.wait_status(
            lambda st: bool(st.get("feeds")) and all(
                f.get("connected_now") for f in st["feeds"].values()),
            "feeds conectados antes de publicar")
        sent = self.ws.publish(instant_ms, depth_symbols, trade_events)
        for symbol in depth_symbols:
            if sent["depth"].get(symbol, 0) != 1:
                raise AssertionError(
                    f"libro no publicado para {symbol}: {sent}")
        for symbol, series in trade_events.items():
            if series and sent["trades"].get(symbol, 0) != len(series):
                raise AssertionError(
                    f"flujo no publicado para {symbol}: {sent}")

        def processed(state):
            for symbol in depth_symbols:
                if (state.get("book_events") or {}).get(symbol, 0) < (
                        base_state.get("book_events") or {}).get(symbol, 0) + 1:
                    return False
                if (state.get("book") or {}).get(symbol, {}).get(
                        "event_ms") != instant_ms:
                    return False
            for symbol, series in trade_events.items():
                if series and (state.get("flow_events") or {}).get(symbol, 0) < (
                        base_state.get("flow_events") or {}).get(symbol, 0) + len(series):
                    return False
                if series and (state.get("flow") or {}).get(symbol, {}).get(
                        "event_ms") != instant_ms:
                    return False
            return True

        return self.wait_status(processed, f"libro/flujo en {instant_ms}")

    def step(self, instant_ms, *, depth_symbols, trade_events, expected_obs):
        """Publica, confirma y alcanza el instante de decision."""
        base = self.advance(instant_ms - 1_000)
        self.publish_and_confirm(base, instant_ms, depth_symbols, trade_events)
        tmp = self.gate_path.with_name(self.gate_path.name + ".tmp")
        tmp.write_text(json.dumps({"decision_ms": instant_ms, "allow": True}),
                       encoding="utf-8")
        os.replace(tmp, self.gate_path)
        self.advance(instant_ms)
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            found = [r for r in read_rows(self.obs_path)
                     if r.get("kind") == "observacion"
                     and r.get("decision_ms") == instant_ms]
            if len(found) >= expected_obs:
                return found
            if self.proc.poll() is not None:
                raise AssertionError(
                    f"el piloto termino: stdout={self.stdout!r} "
                    f"stderr={self.stderr!r}")
            time.sleep(0.02)
        raise AssertionError(f"timeout esperando observaciones en {instant_ms}")

    def wait_operativas(self, expected, timeout=120.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = self.operative_rows()
            if len(rows) >= expected:
                return rows
            if self.proc.poll() is not None:
                raise AssertionError(
                    f"el piloto termino: stdout={self.stdout!r} "
                    f"stderr={self.stderr!r}")
            time.sleep(0.05)
        raise AssertionError(
            f"timeout esperando {expected} filas operativas; hay "
            f"{len(self.operative_rows())}")

    def operative_rows(self):
        if not self.operativo_path.exists():
            return []
        return [json.loads(l) for l in
                self.operativo_path.read_text(encoding="utf-8").splitlines()
                if l.strip()]

    def stop(self, timeout=120.0):
        state = self.status() or {}
        end = int(state.get("settle_end_ms") or 0)
        if end:
            self.clock.set(end + 1_000)
        try:
            self.stdout, self.stderr = self.proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.stdout, self.stderr = self.proc.communicate()
            raise AssertionError("el piloto no termino tras alcanzar el fin")
        return self.proc.returncode

    def summary(self):
        return json.loads((self.out_dir / "resumen.json").read_text(
            encoding="utf-8"))

    def shutdown(self):
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.stdout, self.stderr = self.proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.communicate()
        finally:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            try:
                self._ws_stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Utilidades de verificacion
# ---------------------------------------------------------------------------


def _ventana_flujo(instant_ms, span_ms=62_000):
    return list(range(instant_ms - span_ms, instant_ms + 1, 1_000))


def _vela_referencia(decision_ms):
    """Apertura de la ULTIMA vela 1m cuyo cierre es <= decision_ms.

    ``close_time_ms = open_time_ms + step_ms - 1``: la vela abre en
    ``floor((T+1)/step)*step - step``.
    """
    return rp.floor_ms(decision_ms + 1, STEP_MS) - STEP_MS


def _precio_referencia(symbol, decision_ms, universe):
    """Close de la ultima vela 1m plenamente cerrada en T (la referencia)."""
    ref_open = _vela_referencia(decision_ms)
    return kline_price(symbol, ref_open, universe), ref_open


def _resumen_de_motivos(rows):
    out = {}
    for r in rows:
        out[r.get("decision")] = out.get(r.get("decision"), 0) + 1
    return out


# ---------------------------------------------------------------------------
# 1) El borde publicado (codigo del 2026-11-14) y el borde corregido
# ---------------------------------------------------------------------------


def test_borde_publicado_excluye_la_vela_de_referencia():
    """Reproduce la aritmetica del defecto con los desfases reales.

    El proveedor filtra ``openTime >= startTime``. Con el borde publicado
    (``decision_ms - step_ms``) la vela de referencia (abre en
    ``floor(T/step)*step - step``) queda fuera cuando T no esta alineado, y
    la serie empieza en la vela que CONTIENE a T, cuyo cierre es posterior a
    T: no hay referencia conocida en el instante de la decision.
    """
    for etiqueta, desfase in DESFAZES_EXIGIDOS:
        T = T0 + MINUTE + desfase
        publicado = T - STEP_MS
        corregido = rp.inicio_trayectoria_operativa(T, STEP_MS)
        ref_open = rp.floor_ms(T, STEP_MS) - STEP_MS
        primera_publicada = rp.ceil_ms(publicado, STEP_MS)
        primera_corregida = rp.ceil_ms(corregido, STEP_MS)
        publicada_excluye = primera_publicada > ref_open
        if desfase % STEP_MS == 0:
            # T alineado: el borde publicado ya incluia la referencia.
            assert not publicada_excluye, (etiqueta, T)
            assert primera_corregida == ref_open, (etiqueta, T)
        else:
            assert publicada_excluye, (etiqueta, T)
            assert primera_publicada > ref_open, (etiqueta, T)
            assert primera_corregida == ref_open, (etiqueta, T)
        # El borde corregido nunca empieza despues de la referencia.
        assert primera_corregida <= ref_open, (etiqueta, T)


def test_borde_corregido_no_altera_la_extremidad_final():
    """El inicio se corrige; el final de la serie no se toca."""
    for etiqueta, desfase in DESFAZES_EXIGIDOS:
        T = T0 + MINUTE + desfase
        corregido = rp.inicio_trayectoria_operativa(T, STEP_MS)
        # El borde corregido esta entre la referencia y el borde publicado:
        # como mucho un paso antes que ``T - step_ms`` (T alineado) y nunca
        # despues de la vela cerrada en T.
        assert T - 2 * STEP_MS <= corregido <= T - STEP_MS, (etiqueta, corregido)
        # decision_ms no se redondea ni se retrotrae.
        assert rp.inicio_trayectoria_operativa(T, STEP_MS) == \
            rp.floor_ms(T, STEP_MS) - STEP_MS


def test_proveedor_loopback_respeta_el_filtrado_por_apertura():
    """El proveedor de la aceptacion reproduce el filtro del venue.

    Peticion real al servidor loopback: con un ``startTime`` desalineado, la
    primera fila abre en el multiplo del paso que sea >= startTime (la vela
    anterior queda fuera) y el numero de filas respeta ``limit``.
    """
    import urllib.request  # noqa: E402

    http = TrajectoryHttp(["AAAUSDT"], clock_ms_fn=lambda: T0 + 10 * MINUTE)
    port = find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), http.make_handler())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        start = T0 + 25_000          # desalineado a proposito
        url = ("http://127.0.0.1:%d/fapi/v1/klines?symbol=AAAUSDT"
               "&interval=1m&startTime=%d&endTime=%d&limit=3"
               % (port, start, T0 + 5 * MINUTE))
        with urllib.request.urlopen(url, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        assert rows, "el proveedor no devolvio velas"
        # openTime >= startTime: la vela anterior al multiplo queda fuera.
        assert rows[0][0] >= start, rows[0]
        assert rows[0][0] == rp.ceil_ms(start, STEP_MS), rows[0]
        # Tope de filas del venue.
        assert len(rows) == 3, len(rows)
        # Y la vela previa (que-si cierra antes de T) no esta en la serie.
        assert all(r[0] >= rp.ceil_ms(start, STEP_MS) for r in rows), rows
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# 2) Aceptacion por el recorrido productivo real (CLI, loopback, reloj)
# ---------------------------------------------------------------------------


def _run_decision(tmp, universe, moves, decision_ms, http_cls=TrajectoryHttp,
                  max_symbols=None, run_id="operativo-borde"):
    """Ejecuta una decision operativa real y devuelve (run, filas)."""
    run = OperativeRun(
        tmp, universe=universe, moves=moves, http_cls=http_cls,
        max_symbols=max_symbols or len(universe), run_id=run_id)
    try:
        run.wait_ready(expected_followed=len(universe))
        eventos = {s: _ventana_flujo(decision_ms) for s in universe}
        run.step(decision_ms, depth_symbols=list(universe),
                 trade_events=eventos, expected_obs=len(universe))
        # El reloj llega al horizonte + un paso: la trayectoria ya existe.
        run.advance(decision_ms + HORIZON_MS + STEP_MS + 2_000)
        filas = run.wait_operativas(expected=len(universe))
        return run, filas
    except Exception:
        run.shutdown()
        raise


def test_aceptacion_decisiones_no_alineadas_recuperan_la_referencia():
    """T no alineado al minuto: la referencia se recupera y el fill es posterior.

    Para cada desfase exigido se comprueba, sobre el recorrido real:
      - la consulta de trayectoria empieza en la vela cerrada en T;
      - la serie llega hasta la vela del horizonte (sin truncar el final);
      - la fila operativa NO dice "sin vela 1m plenamente conocida en T";
      - si hubo entrada, el fill es POSTERIOR a T y el dato de decision no
        usa velas futuras.
    """
    universo = ["AAAUSDT", "BBBUSDT"]
    for etiqueta, desfase in DESFAZES_EXIGIDOS:
        tmp = Path(tempfile.mkdtemp(prefix="borde-%s-" % etiqueta))
        T = T0 + MINUTE + desfase
        try:
            run, filas = _run_decision(
                tmp, universo, {"AAAUSDT": 1.0, "BBBUSDT": -1.0}, T,
                run_id="borde-%s" % etiqueta)
            try:
                assert len(filas) == len(universo), (etiqueta, filas)
                por_simbolo = {f["symbol"]: f for f in filas}
                for simbolo in universo:
                    fila = por_simbolo[simbolo]
                    assert fila["funding_estado"] != UMBRAL_SIN_VELA, (
                        etiqueta, simbolo, fila)
                    ref_px, ref_open = _precio_referencia(
                        simbolo, T, universo)
                    # La referencia usada es la vela que CIERRA en T: su
                    # cierre es anterior o igual a T (ningun dato futuro).
                    assert ref_open + STEP_MS - 1 <= T, (etiqueta, ref_open)
                    fill_open = rp.floor_ms(T, STEP_MS) + STEP_MS
                    fill_px = kline_price(simbolo, fill_open, universo)
                    if fila.get("decision") == "ENTRADA_EJECUTADA":
                        # El fill ocurre en la apertura POSTERIOR a T.
                        assert fila["entry_ms"] == fill_open, (etiqueta, fila)
                        assert fila["entry_ms"] > T, (etiqueta, fila)
                        assert abs(fila["entry_px"] - fill_px) < 1e-9, (
                            etiqueta, simbolo, fila["entry_px"], fill_px)
                        assert fila["qty"] > 0, (etiqueta, fila)
                        assert fila["exit_executed"] is True, (etiqueta, fila)
                        assert fila["exit_ms"] >= fila["entry_ms"], (
                            etiqueta, fila)
                    else:
                        # Sin fill: lo que se muestra es la referencia
                        # conocida en T, no una vela posterior.
                        if fila.get("entry_px") is not None:
                            assert abs(fila["entry_px"] - ref_px) < 1e-9, (
                                etiqueta, simbolo, fila["entry_px"], ref_px)
                        assert fila.get("entry_ms") in (None, fill_open), (
                            etiqueta, fila)
                    # El stop se deriva de la referencia conocida en T.
                    if fila.get("stop_px") is not None:
                        stop = (ref_px * (1.0 - 0.005)
                                if fila["direction"] == "LONG"
                                else ref_px * (1.0 + 0.005))
                        assert abs(fila["stop_px"] - stop) < 1e-9, (
                            etiqueta, simbolo, fila["stop_px"], stop)
                # Borde de la consulta y cobertura del horizonte.
                peticiones = [p for p in run.http.trajectory_requests
                              if p["symbol"] in universo]
                assert peticiones, (etiqueta, run.http.trajectory_requests)
                for p in peticiones:
                    # El borde de la consulta es el documentado y la serie
                    # incluye la vela cerrada en T.
                    inicio = rp.inicio_trayectoria_operativa(T, STEP_MS)
                    assert p["first_open_ms"] == inicio, (etiqueta, p)
                    assert p["first_open_ms"] <= _vela_referencia(T), (
                        etiqueta, p)
                    # La serie pasa del horizonte: la ultima vela abre DESPUES
                    # de T + horizonte (si no, el motor marca open_at_end).
                    assert p["last_open_ms"] == rp.floor_ms(
                        T + HORIZON_MS, STEP_MS) + STEP_MS, (etiqueta, p)
                    assert p["n_rows"] == p["params"]["limit"], (etiqueta, p)
                    assert p["params"]["limit"] == 63, (etiqueta, p)
            finally:
                run.shutdown()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def test_recorrido_long_y_short_con_datos_sinteticos():
    """LONG y SHORT recorren el camino completo con el mismo criterio."""
    universo = ["AAAUSDT", "BBBUSDT"]
    tmp = Path(tempfile.mkdtemp(prefix="borde-long-short-"))
    T = T0 + MINUTE + 12_527
    try:
        run, filas = _run_decision(
            tmp, universo, {"AAAUSDT": 2.5, "BBBUSDT": -2.5}, T,
            run_id="borde-long-short")
        try:
            por_simbolo = {f["symbol"]: f for f in filas}
            assert por_simbolo["AAAUSDT"]["direction"] == "LONG", filas
            assert por_simbolo["BBBUSDT"]["direction"] == "SHORT", filas
            for simbolo in universo:
                fila = por_simbolo[simbolo]
                assert fila["funding_estado"] != UMBRAL_SIN_VELA, fila
                if fila["decision"] == "ENTRADA_EJECUTADA":
                    assert fila["entry_ms"] > T, fila
                    # Mismo criterio para ambos roles: no hay reglas por rol.
                    assert fila["role"] == "candidate", fila
        finally:
            run.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_capacidad_compartida_limitada_a_una_posicion():
    """Con dos senales en el mismo instante, la segunda se rechaza."""
    universo = ["AAAUSDT", "BBBUSDT"]
    tmp = Path(tempfile.mkdtemp(prefix="borde-capacidad-"))
    T = T0 + MINUTE + 19_298
    try:
        run, filas = _run_decision(
            tmp, universo, {"AAAUSDT": 2.0, "BBBUSDT": 2.0}, T,
            run_id="borde-capacidad")
        try:
            por_simbolo = {f["symbol"]: f for f in filas}
            decisiones = {s: f["decision"] for s, f in por_simbolo.items()}
            ejecutadas = [s for s, d in decisiones.items()
                          if d == "ENTRADA_EJECUTADA"]
            rechazadas = [s for s, d in decisiones.items()
                          if d == "RECHAZADA_CAPACIDAD"]
            assert len(ejecutadas) == 1, decisiones
            assert len(rechazadas) == 1, decisiones
            # El rechazo NO describe una posicion abierta.
            rechazo = por_simbolo[rechazadas[0]]
            assert rechazo["qty"] == 0, rechazo
            assert rechazo["open_at_end"] is False, rechazo
            assert rechazo["neto_estado"] == "UNKNOWN", rechazo
            assert "posicion abierta" not in rechazo["neto_motivo"], rechazo
            assert "rechazo por capacidad" in rechazo["neto_motivo"], rechazo
        finally:
            run.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_datos_realmente_ausentes_producen_abstencion_explicita():
    """Si la vela de referencia NO existe, la regla se abstiene (no inventa)."""
    universo = ["AAAUSDT"]
    tmp = Path(tempfile.mkdtemp(prefix="borde-ausente-"))
    T = T0 + MINUTE + 12_527
    try:
        run = OperativeRun(tmp, universe=universo,
                           moves={"AAAUSDT": 1.0},
                           http_cls=MissingReferenceHttp,
                           max_symbols=1, run_id="borde-ausente")
        try:
            run.wait_ready(expected_followed=1)
            run.step(T, depth_symbols=universo,
                     trade_events={s: _ventana_flujo(T) for s in universo},
                     expected_obs=1)
            run.advance(T + HORIZON_MS + STEP_MS + 2_000)
            filas = run.wait_operativas(expected=1)
            fila = filas[0]
            assert fila["decision"] == "SIN_ENTRADA", fila
            assert fila["funding_estado"] == UMBRAL_SIN_VELA, fila
            assert fila["entry_px"] is None, fila
            assert fila["qty"] == 0, fila
            assert fila["open_at_end"] is False, fila
            assert fila["neto_estado"] == "UNKNOWN", fila
            assert "abstencion sin posicion" in fila["neto_motivo"], fila
            assert "posicion abierta" not in fila["neto_motivo"], fila
        finally:
            run.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_etiqueta_economica_distingue_los_cuatro_estados():
    """``neto_motivo`` describe el estado REAL de cada fila.

    1. AbstENCION sin posicion (no hubo entrada).
    2. Rechazo por capacidad sin posicion (no se admitio la entrada).
    3. Posicion realmente abierta sin salida.
    4. Operacion cerrada con funding incompleto (neto CONDICIONADO).

    Una abstENCION con ``qty = 0`` NO puede describirse como "posicion
    abierta", y un desconocimiento sigue siendo UNKNOWN (nunca cero).
    """
    from research_operativo_adapter import (  # noqa: E402
        OperativoAdapter,
        OperativoTradeResult,
    )

    def _resultado(**kwargs):
        base = dict(
            observation_id=kwargs.pop("observation_id", "obs-1"),
            symbol="AAAUSDT", role="candidate", direction="LONG",
            decision="SIN_ENTRADA", decision_ms=T0 + 60_000,
            entry_px=None, entry_ms=None, stop_px=None, exit_px=None,
            exit_ms=None, exit_reason=None, exit_executed=False,
            open_at_end=False, qty=0.0, gross_pnl=0.0, fees=0.0,
            spread_slip=0.0, funding=None, net_pnl=None,
            funding_estado="sin_dato_de_referencia_en_T",
            config_hash="cfg", engine_version="engine")
        base.update(kwargs)
        return OperativoTradeResult(**base)

    tmp = Path(tempfile.mkdtemp(prefix="borde-etiqueta-"))
    try:
        store = tmp / "resultado_operativo.jsonl"
        adapter = OperativoAdapter(store_path=store)

        # 1) AbstENCION sin posicion.
        adapter.persistir(_resultado(
            observation_id="obs-abstencion", decision="SIN_ENTRADA",
            funding_estado="sin vela 1m plenamente conocida en T"))
        # 2) Rechazo por capacidad sin posicion.
        adapter.persistir(_resultado(
            observation_id="obs-capacidad", decision="RECHAZADA_CAPACIDAD",
            entry_px=1000.0, entry_ms=T0 + 120_000, stop_px=995.0,
            funding_estado="rechazada_por_capacidad"))
        # 3) Posicion realmente abierta sin salida.
        adapter.persistir(_resultado(
            observation_id="obs-abierta", decision="ENTRADA_EJECUTADA",
            entry_px=1000.0, entry_ms=T0 + 120_000, stop_px=995.0,
            qty=1.0, open_at_end=True, exit_executed=False,
            funding_estado="posicion abierta"))
        # 4) Operacion cerrada con funding incompleto.
        adapter.persistir(_resultado(
            observation_id="obs-cerrada", decision="ENTRADA_EJECUTADA",
            entry_px=1000.0, entry_ms=T0 + 120_000, stop_px=995.0,
            exit_px=1010.0, exit_ms=T0 + 3_660_000, exit_reason="horizon",
            exit_executed=True, qty=1.0, gross_pnl=10.0, fees=1.0,
            spread_slip=0.3, net_pnl=8.7, funding=None,
            funding_estado="settlement-calendar incompleto"))

        filas = {r["observation_id"]: r for r in read_rows(store)}
        assert len(filas) == 4, filas

        abst = filas["obs-abstencion"]
        assert abst["neto_estado"] == "UNKNOWN", abst
        assert abst["net_pnl"] is None, abst
        assert "abstencion sin posicion" in abst["neto_motivo"], abst
        assert "posicion abierta" not in abst["neto_motivo"], abst

        cap = filas["obs-capacidad"]
        assert cap["neto_estado"] == "UNKNOWN", cap
        assert cap["net_pnl"] is None, cap
        assert cap["qty"] == 0, cap
        assert "rechazo por capacidad" in cap["neto_motivo"], cap
        assert "posicion abierta" not in cap["neto_motivo"], cap

        abierta = filas["obs-abierta"]
        assert abierta["neto_estado"] == "UNKNOWN", abierta
        assert abierta["net_pnl"] is None, abierta
        assert "posicion abierta" in abierta["neto_motivo"], abierta

        cerrada = filas["obs-cerrada"]
        assert cerrada["neto_estado"] == "CONDICIONADO_SIN_FUNDING_COMPLETO", \
            cerrada
        assert cerrada["net_pnl"] == 8.7, cerrada
        assert "funding incompleto" in cerrada["neto_motivo"], cerrada
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_persistencia_y_resumen_coherentes():
    """La fila persistida y el resumen del piloto cuentan lo mismo."""
    universo = ["AAAUSDT", "BBBUSDT"]
    tmp = Path(tempfile.mkdtemp(prefix="borde-resumen-"))
    T = T0 + MINUTE + 12_527
    try:
        run, filas = _run_decision(
            tmp, universo, {"AAAUSDT": 2.0, "BBBUSDT": -2.0}, T,
            run_id="borde-resumen")
        try:
            rc = run.stop()
            assert rc == 0, run.stderr
            resumen = run.summary()
            eco = resumen.get("economia_operativa_v2") or {}
            decisiones = eco.get("decisiones") or {}
            por_decision = decisiones.get("por_decision") or {}
            assert sum(por_decision.values()) == len(filas), (por_decision,
                                                              filas)
            for decision, n in por_decision.items():
                assert n == sum(1 for f in filas
                                if f["decision"] == decision), decision
            # Los netos completos y conditioned se contabilizan por separado
            # y las filas sin net (UNKNOWN) no entran en ninguno.
            completas = sum(1 for f in filas
                            if f["neto_estado"] == "COMPLETO")
            condicionadas = sum(1 for f in filas if f["neto_estado"] ==
                                "CONDICIONADO_SIN_FUNDING_COMPLETO")
            desconocidas = sum(1 for f in filas
                               if f["neto_estado"] == "UNKNOWN")
            assert eco.get("resultado_usdt", {}).get(
                "neto_completo", {}).get("n") == completas, eco.get(
                    "resultado_usdt")
            assert eco.get("resultado_usdt", {}).get(
                "neto_conditionado_sin_funding_completo", {}).get(
                    "n") == condicionadas, eco.get("resultado_usdt")
            # Un UNKNOWN nunca se convierte en cero ni se cuela en un neto.
            assert (completas + condicionadas + desconocidas) == len(filas), (
                filas)
            for f in filas:
                if f["neto_estado"] == "UNKNOWN":
                    assert f["net_pnl"] is None, f
                else:
                    assert f["net_pnl"] is not None, f
        finally:
            run.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
