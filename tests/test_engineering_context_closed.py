"""Regresiones del contexto CERRADO y del aislamiento de pid-files.

Cubre el camino productivo del arnés existente sin Binance y sin ventana
pública (proveedores loopback):

1. Una respuesta REST que incluye la vela en curso se filtra: nunca entra OHLC
   no cerrado al contexto y la ventana pedida termina en la última vela cuyo
   cierre ya ocurrió respecto de la referencia.
2. Una vela cuyo cierre coincide EXACTAMENTE con la referencia se admite (sin
   tolerancia positiva de un intervalo).
3. Si tras filtrar falta contexto, se aborta con motivo explícito, sin
   descargas automáticas adicionales y sin crear sesión.
4. Un proveedor local que respeta el rango solicitado demuestra contexto
   reciente, cerrado y contiguo por símbolo.
5. Cada servicio recibe un ``--pid-file`` explícito y exclusivo de la corrida;
   un pid-file ajeno preexistente queda idéntico antes y después, incluso ante
   fallo de arranque.

Se conserva intacta la validación defensiva del backend (``CONTEXTO_*``): el
arnés la replica antes de crear la sesión, nunca la relaja.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
_SCRIPTS_DIR = ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import engineering_live_window as elw_mod  # noqa: E402
from local_ws_kline_provider import LocalWsklineProvider  # noqa: E402

STEP_MS = 60_000
# Referencia en el pasado remoto: la caché canónica real no tiene velas en
# esa ventana, así que el proveedor loopback es la única fuente.
REF = 1_600_000_000_475
SYMBOLS = ("MINAUSDT", "BTCUSDT")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _kline_row(open_time: int, price: float) -> List[Any]:
    return [
        open_time, f"{price:.8f}", f"{price * 1.001:.8f}",
        f"{price * 0.999:.8f}", f"{price * 1.0002:.8f}", "100.0",
        open_time + STEP_MS - 1, "10000.0", 42, "90.0", "9000.0", "0",
    ]


def _rows_in_range(symbol: str, start: int, end: int, limit: int,
                   extra_in_progress: bool = False,
                   only_in_progress: bool = False) -> List[List[Any]]:
    price = 100.0 if symbol == "BTCUSDT" else 0.01
    rows: List[List[Any]] = []
    if not only_in_progress:
        ot = start
        while ot <= end and len(rows) < limit:
            rows.append(_kline_row(ot, price))
            ot += STEP_MS
    if extra_in_progress or only_in_progress:
        ot = end + 1  # apertura de la vela en curso
        rows.append(_kline_row(ot, price))
    return rows


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        url = urlsplit(self.path)
        provider = self.server.provider  # type: ignore[attr-defined]
        if url.path != elw_mod.KLINES_PATH:
            self._send(404, {"code": -404, "msg": "path not found"})
            return
        params = parse_qs(url.query)
        provider.requests.append(params)
        symbol = (params.get("symbol") or [""])[0].upper()
        start = int((params.get("startTime") or [0])[0])
        end = int((params.get("endTime") or [0])[0])
        limit = int((params.get("limit") or [500])[0])
        rows = provider.rows_fn(symbol, start, end, limit)
        self._send(200, rows)

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _KlinesProvider:
    """Proveedor REST loopback de klines (cero red pública)."""

    def __init__(self, rows_fn) -> None:
        self.rows_fn = rows_fn
        self.requests: List[Dict[str, List[str]]] = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.provider = self  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)

    @property
    def base_url(self) -> str:
        return "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def __enter__(self) -> "_KlinesProvider":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5.0)


def _health(available: bool = True, source: str = "public_sincronizado",
            offset_ms: Optional[float] = 0.0,
            age_ms: Optional[float] = 10.0) -> Dict[str, Any]:
    return {"clock": {"source": source, "available": available,
                      "offset_ms": offset_ms, "age_ms": age_ms,
                      "reason": None}}


def _orchestrator(tmp: Path, *, transport: str = "public",
                  provider_port: int = 0,
                  rest_base_url: Optional[str] = None,
                  clock_source: Optional[str] = None,
                  run_id: Optional[str] = "eng-run-context-test") -> Any:
    a = argparse.Namespace()
    a.transport = transport
    a.execute = False
    a.service_port = _free_port()
    a.engineering_port = _free_port()
    a.provider_port = provider_port
    a.ws_port = _free_port()
    a.dashboard = "http://127.0.0.1:3020"
    a.build_id = "test-build-id"
    a.symbols = "MINAUSDT,BTCUSDT"
    a.interval = "1m"
    a.bars = 300
    a.duration = 60.0
    a.deadline = 60.0
    a.sessions_dir = str(tmp / "sessions")
    a.clock_source = clock_source
    a.clock_readiness_timeout_s = 5.0
    a.run_id = run_id
    a.rest_base_url = rest_base_url
    return elw_mod.WindowOrchestrator(a)


class _FakeProc:
    pid = 0

    def __init__(self) -> None:
        self._stdout_file = None
        self._stderr_file = None

    def terminate(self) -> None:
        return None

    def wait(self, timeout: Optional[float] = None) -> int:
        return 0

    def kill(self) -> None:
        return None


class ContextoCerradoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="eng-ctx-test-"))
        self._cache_db_original = elw_mod.CACHE_DB
        elw_mod.CACHE_DB = self.tmp / "cache.db"

    def tearDown(self) -> None:
        elw_mod.CACHE_DB = self._cache_db_original

    def _fixed_reference(self, orch) -> None:
        orch._reference_now_ms = lambda: REF  # type: ignore[assignment]

    def test_referencia_publica_requiere_reloj_valido(self):
        orch = _orchestrator(self.tmp)
        with self.assertRaisesRegex(RuntimeError, "CLOCK_SOURCE_AUSENTE"):
            orch._reference_now_ms()
        orch.ultima_salud_ingenieria = _health(available=False)
        with self.assertRaisesRegex(RuntimeError,
                                    "CLOCK_REFERENCIA_NO_DISPONIBLE"):
            orch._reference_now_ms()
        orch.ultima_salud_ingenieria = _health(offset_ms=None)
        with self.assertRaisesRegex(RuntimeError,
                                    "CLOCK_REFERENCIA_INCIERTA"):
            orch._reference_now_ms()

    def test_vela_en_curso_excluida_y_ventana_cerrada(self):
        with _KlinesProvider(
                lambda s, a, b, l: _rows_in_range(s, a, b, l, True)) as prov:
            orch = _orchestrator(self.tmp, rest_base_url=prov.base_url)
            orch.ultima_salud_ingenieria = _health()
            self._fixed_reference(orch)
            start_open, end_open = orch._context_window(REF)
            ctx = orch._prepare_context()

        self.assertEqual(len(ctx), 600)
        self.assertEqual(len(prov.requests), 2)
        self.assertTrue(all(c["close_time_ms"] <= REF for c in ctx))
        for sym in SYMBOLS:
            velas = [c for c in ctx if c["symbol"] == sym]
            self.assertEqual(len(velas), 300, sym)
            self.assertEqual(velas[0]["open_time_ms"], start_open, sym)
            self.assertEqual(velas[-1]["open_time_ms"], end_open, sym)
            self.assertEqual(velas[-1]["close_time_ms"],
                             end_open + STEP_MS - 1, sym)
        ev = orch.evidence["contexto"]
        self.assertIsNone(ev["motivo"])
        self.assertEqual(ev["ventana"], [start_open, end_open])
        ok = {d["symbol"]: d for d in ev["parse_diag"]
              if d.get("result") == "ok"}
        for sym in SYMBOLS:
            self.assertEqual(ok[sym]["cierre_no_ocurrido"], 1, sym)
            self.assertEqual(ok[sym]["admitidas"], 300, sym)
        for params in prov.requests:
            self.assertEqual(int(params["startTime"][0]), start_open)
            self.assertEqual(int(params["endTime"][0]),
                             end_open + STEP_MS - 1)
            self.assertEqual(int(params["limit"][0]), 300)

    def test_cierre_exactamente_en_la_referencia_se_admite(self):
        base_open = (REF // STEP_MS) * STEP_MS
        exact_ref = base_open + STEP_MS - 1
        with _KlinesProvider(
                lambda s, a, b, l: _rows_in_range(s, a, b, l)) as prov:
            orch = _orchestrator(self.tmp, rest_base_url=prov.base_url)
            orch.ultima_salud_ingenieria = _health()
            orch._reference_now_ms = lambda: exact_ref  # type: ignore
            start_open, end_open = orch._context_window(exact_ref)
            self.assertEqual(end_open, base_open)
            ctx = orch._prepare_context()

        for sym in SYMBOLS:
            velas = [c for c in ctx if c["symbol"] == sym]
            self.assertEqual(velas[-1]["open_time_ms"], base_open, sym)
            self.assertEqual(velas[-1]["close_time_ms"], exact_ref, sym)
        self.assertIsNone(orch.evidence["contexto"]["motivo"])

    def test_contexto_insuficiente_no_crea_sesion(self):
        with _KlinesProvider(
                lambda s, a, b, l: _rows_in_range(
                    s, a, b, l, only_in_progress=True)) as prov:
            orch = _orchestrator(self.tmp, rest_base_url=prov.base_url)
            orch.ultima_salud_ingenieria = _health()
            self._fixed_reference(orch)

            def _no_crear(_ctx):
                raise AssertionError("no debe crearse sesion")

            orch._create_session = _no_crear  # type: ignore[assignment]
            with self.assertRaisesRegex(RuntimeError,
                                        "CONTEXTO_INSUFICIENTE"):
                orch._prepare_context()

        self.assertIsNone(orch.session_id)
        self.assertEqual(len(prov.requests), 2)  # una por símbolo, sin extra
        ev = orch.evidence["contexto"]
        self.assertEqual(ev["velas"], 0)
        self.assertIn("CONTEXTO_INSUFICIENTE", ev["motivo"])
        self.assertFalse([c for c in orch.checks
                          if c["id"] == "contexto_cargado"][0]["ok"])

    def test_proveedor_local_respeta_rango_y_contexto_cerrado(self):
        http_port = _free_port()
        prov = LocalWsklineProvider(http_port, _free_port(),
                                    {s: "ok" for s in SYMBOLS})
        prov.start()
        try:
            orch = _orchestrator(self.tmp, transport="local",
                                 provider_port=http_port,
                                 clock_source="local")
            self._fixed_reference(orch)
            start_open, end_open = orch._context_window(REF)
            ctx = orch._prepare_context()
        finally:
            prov.stop()

        self.assertEqual(len(ctx), 600)
        ev = orch.evidence["contexto"]
        self.assertIsNone(ev["motivo"])
        for sym in SYMBOLS:
            velas = [c for c in ctx if c["symbol"] == sym]
            self.assertEqual(len(velas), 300, sym)
            self.assertEqual(velas[0]["open_time_ms"], start_open, sym)
            self.assertEqual(velas[-1]["open_time_ms"], end_open, sym)
            self.assertTrue(all(
                b["open_time_ms"] - a["open_time_ms"] == STEP_MS
                for a, b in zip(velas, velas[1:])), sym)
            self.assertTrue(ev["por_simbolo"][sym]["contiguo"], sym)
            self.assertTrue(ev["por_simbolo"][sym]["alcanza_ultima_cerrada"],
                            sym)

    def test_pid_files_explicitos_y_ajenos_intactos_ante_fallo(self):
        sessions_dir = self.tmp / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        ajeno = self.tmp / "data" / "market-stream" / "service.json"
        ajeno.parent.mkdir(parents=True, exist_ok=True)
        contenido_ajeno = b'{"pid": 31124, "port": 8792}'
        ajeno.write_bytes(contenido_ajeno)

        orch = _orchestrator(self.tmp, rest_base_url="http://127.0.0.1:9")
        capturados: List[Tuple[List[str], str]] = []

        def _spawn(argv, label, stdout_path=None, stderr_path=None):
            capturados.append((list(argv), label))
            return _FakeProc()

        orch._spawn = _spawn  # type: ignore[assignment]
        orch._http_get = lambda url, timeout=8.0: {  # type: ignore
            "ok": True, "status": 200,
            "text": json.dumps({"pid": 111, "port": orch.service_port,
                                "transport": {"mode": "public"}}),
            "error": None}
        orch._wait_for_engineering_readiness = (  # type: ignore
            lambda eng_url, sd: {"pid": 222, "port": orch.engineering_port})
        orch._start_services()

        mercados = [argv for argv, label in capturados
                    if label == "market-stream-service"]
        ingenierias = [argv for argv, label in capturados
                       if label == "engineering-session"]
        self.assertEqual(len(mercados), 1)
        self.assertEqual(len(ingenierias), 1)
        self.assertIn("--pid-file", mercados[0])
        self.assertEqual(
            mercados[0][mercados[0].index("--pid-file") + 1],
            str(sessions_dir / "market-service.json"))
        self.assertIn("--pid-file", ingenierias[0])
        self.assertEqual(
            ingenierias[0][ingenierias[0].index("--pid-file") + 1],
            str(sessions_dir / "engineering-service.json"))
        self.assertNotEqual(str(ajeno), mercados[0][-1])

        # La limpieza borra SOLO los pid-files propios.
        orch.market_pid_path.write_text("propio", encoding="utf-8")
        orch.engineering_pid_path.write_text("propio", encoding="utf-8")
        orch._cleanup()
        self.assertFalse(orch.market_pid_path.exists())
        self.assertFalse(orch.engineering_pid_path.exists())
        self.assertEqual(ajeno.read_bytes(), contenido_ajeno)

        # Fallo de arranque: el pid-file ajeno tampoco se toca.
        orch2 = _orchestrator(self.tmp, rest_base_url="http://127.0.0.1:9")
        orch2._spawn = _spawn  # type: ignore[assignment]
        orch2._http_get = lambda url, timeout=8.0: {  # type: ignore
            "ok": False, "status": None, "text": "", "error": "sin servicio"}
        orch2.deadline_monotonic = time.monotonic() + 0.8
        capturados.clear()
        with self.assertRaises(Exception):
            orch2._start_services()
        self.assertEqual(ajeno.read_bytes(), contenido_ajeno)

    def test_servicio_real_escribe_pid_file_exclusivo(self):
        """El CLI acepta --pid-file y no reconstruye el pid-file por defecto."""
        cwd = self.tmp / "cwd_servicio"
        (cwd / "data" / "market-stream").mkdir(parents=True, exist_ok=True)
        ajeno = cwd / "data" / "market-stream" / "service.json"
        contenido_ajeno = b'{"pid": 31124, "port": 8792}'
        ajeno.write_bytes(contenido_ajeno)
        pid_file = self.tmp / "exclusivo" / "market-service.json"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        port = _free_port()
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8",
             str(ROOT / "scripts" / "market_stream_service.py"),
             "--port", str(port), "--transport", "local",
             "--base-url", "ws://127.0.0.1:9",
             "--pid-file", str(pid_file)],
            cwd=str(cwd), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            limite = time.monotonic() + 15.0
            while time.monotonic() < limite and not pid_file.exists():
                time.sleep(0.1)
            self.assertTrue(pid_file.exists(), "pid-file exclusivo no creado")
            datos = json.loads(pid_file.read_text(encoding="utf-8"))
            self.assertEqual(datos["pid"], proc.pid)
            self.assertEqual(datos["port"], port)
            self.assertEqual(ajeno.read_bytes(), contenido_ajeno)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10.0)
            except subprocess.TimeoutExpired:  # pragma: no cover
                proc.kill()
                proc.wait(timeout=5.0)

        # Configuración inválida (fallo): tampoco escribe pid-files.
        pid_file2 = self.tmp / "exclusivo" / "market-service-fallo.json"
        fallo = subprocess.run(
            [sys.executable, "-X", "utf8",
             str(ROOT / "scripts" / "market_stream_service.py"),
             "--port", str(_free_port()), "--transport", "local",
             "--pid-file", str(pid_file2)],
            cwd=str(cwd), env=env, capture_output=True, timeout=30)
        self.assertEqual(fallo.returncode, 2)
        self.assertFalse(pid_file2.exists())
        self.assertEqual(ajeno.read_bytes(), contenido_ajeno)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
