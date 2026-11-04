"""Aceptación integrada LOCAL del camino productivo público (sin Binance).

Cada criterio ejecuta lo que afirma, con los procesos reales:
  * BFF productivo de Next.js (build existente) escuchando en un puerto
    alterno y recibiendo el ``Host`` canónico 127.0.0.1:3020;
  * servicio canónico ``engineering-session-service/v1``;
  * proveedores HTTP/WS loopback configurables (``/time`` y klines).

Aislamiento total: sesiones, SQLite, pid-files y logs en un
``TemporaryDirectory`` por sesión de pruebas. Guardas de red registran
cualquier intento a dominios públicos.

Criterios:
  A. Primer inicio sin corrida previa: una corrida, un run_id, identidad.
  B. Doble POST start concurrente: una corrida, un run_id, un proceso.
  C. BFF -> servicio -> reloj -> contexto cerrado -> sesión -> cierre nuevo
     -> evaluación vinculada.
  D. 5 /time + 2 klines reales (HistoryClient + LedgerAttemptGate) = 7; el
     8.º queda bloqueado ANTES del transporte.
  E. Consumo en interfaz: NO ACREDITADO (el valor no se renderiza; además el
     BFF productivo solo admite Host 127.0.0.1:3020 y 3020 se preserva).
  F. Reinicio de la misma corrida: NO ACREDITADO (el pre-chequeo de
     presupuesto rechaza cualquier reanudación tras consumir 5/7).
  H. Parada con run_id ajeno rechazada y proceso/puerto intactos; identidad
     incierta cubierta con proveedor local controlado. NO ACREDITADO: la
     parada de la corrida propia no detiene el servicio (el gestor BFF lee el
     registro en una ruta distinta de la que escribe el backend).
  I. Entrada real por la secuencia/regla existentes; tras detener, entrada y
     posición conservadas, sin salida/comisión/realizado inventados.
  J. Fallo de preparación: causa visible, /health honesto y limpieza.

G (deadline) se ejecuta en ``tests/test_public_run_deadline.py`` (proceso y
puerto reales, plazo corto).

Los criterios E, F y H se reportan como NO ACREDITADO: el runner sale con
código distinto de cero; no se cambia la descripción para simular un PASS.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from microstructure_probe import paper_lab_engine as engine  # noqa: E402
from microstructure_probe.history_client import (  # noqa: E402
    HistoryClient, UpstreamBudgetExceeded,
)
from microstructure_probe.market_cache import MarketCache  # noqa: E402
from microstructure_probe.market_explorer import LedgerAttemptGate  # noqa: E402
from public_run_harness import (  # noqa: E402
    BffProcess, LoopbackProvider, NetworkGuard, bff_manager_run_record_path,
    bff_pid_file, bff_public_run_path, entry_payload, free_port, health,
    http_json, is_listening, pid_alive, public_run, start_engineering_service,
    wait_clock_ready, wait_health, wait_port_free, wait_port_listening,
)

CANONICAL_HOST = "127.0.0.1:3020"
SERVICE_PORT = 8797  # puerto del contrato del BFF público (route.ts)


# ---------------------------------------------------------------------------
# Contexto de la corrida pública de aceptación (BFF + servicio reales)
# ---------------------------------------------------------------------------

@dataclass
class Acceptance:
    base: Path
    guard: NetworkGuard
    provider: LoopbackProvider
    bff: BffProcess
    run_id: str
    service_root: Path
    cache_db: Path
    start_responses: List[Dict[str, Any]] = field(default_factory=list)
    service_pid: Optional[int] = None
    session_id: Optional[str] = None
    session_at_creation: Dict[str, Any] = field(default_factory=dict)
    final_session: Dict[str, Any] = field(default_factory=dict)
    ledger_counts: Dict[str, int] = field(default_factory=dict)
    clock_observed: Dict[str, Any] = field(default_factory=dict)


@pytest.fixture(scope="module")
def acceptance() -> Acceptance:
    if is_listening(SERVICE_PORT):
        pytest.fail(
            f"el puerto {SERVICE_PORT} (contrato del BFF público) está ocupado "
            "por otro proceso; la prueba no lo reutiliza ni lo detiene")
    tmp = tempfile.TemporaryDirectory(
        prefix="public-acceptance-", ignore_cleanup_errors=True)
    base = Path(tmp.name)
    service_root = base / "bff-root"
    (service_root / "data" / "engineering-session").mkdir(parents=True)
    cache_db = base / "market_cache.db"
    guard = NetworkGuard(base)
    provider = LoopbackProvider()
    provider.start()
    bff = BffProcess(free_port(), service_root, provider, guard, cache_db, base)
    ctx = Acceptance(
        base=base, guard=guard, provider=provider, bff=bff,
        run_id=f"eng-acceptance-{int(time.time() * 1000)}",
        service_root=service_root, cache_db=cache_db)
    try:
        try:
            bff.start()
        except Exception as exc:  # build/Next ausente o no arranca
            pytest.fail(f"BFF productivo no arrancó: {exc}")
        yield ctx
    finally:
        # Detener SOLO procesos propios (servicio del BFF + BFF + proveedor).
        # Primero el servicio, para que ningún handle suyo impida limpiar el
        # directorio temporal; después el BFF y el proveedor.
        own_pid = ctx.service_pid
        if own_pid is None:
            record = public_run(SERVICE_PORT) or {}
            own_pid = record.get("pid") if isinstance(record.get("pid"), int) else None
        if is_listening(SERVICE_PORT):
            try:
                http_json(SERVICE_PORT, "/shutdown", method="POST", body={},
                          host=f"127.0.0.1:{SERVICE_PORT}", timeout=5.0)
            except Exception:
                pass
            try:
                wait_port_free(SERVICE_PORT, timeout_s=15.0)
            except TimeoutError:
                pass
        if isinstance(own_pid, int) and pid_alive(own_pid):
            import subprocess
            subprocess.run(["taskkill", "/PID", str(own_pid), "/F"],
                           capture_output=True, check=False)
            time.sleep(0.5)
        bff.stop()
        provider.stop()
        if is_listening(SERVICE_PORT):
            raise RuntimeError(
                f"el servicio propio dejó el puerto {SERVICE_PORT} ocupado")
        tmp.cleanup()


def _bff_public(ctx: Acceptance, method: str = "GET",
                body: Optional[Dict[str, Any]] = None,
                timeout: float = 60.0):
    return http_json(
        ctx.bff.port, "/api/v1/engineering-sessions/public",
        method=method, body=body, host=CANONICAL_HOST, timeout=timeout)


def _wait_until(predicate, timeout_s: float, interval_s: float = 0.2) -> Any:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            last = predicate()
        except Exception as exc:  # noqa: BLE001
            last = exc
        if last:
            return last
        time.sleep(interval_s)
    return last


# ---------------------------------------------------------------------------
# A. Primer inicio sin corrida previa
# ---------------------------------------------------------------------------

def test_a_first_start_creates_single_identity(acceptance: Acceptance) -> None:
    ctx = acceptance
    read_path = bff_public_run_path(ctx.service_root)
    assert read_path.exists() is False, "no debe existir registro previo"

    status, payload = _bff_public(
        ctx, "POST", {"action": "start", "run_id": ctx.run_id})
    assert status == 200, payload
    assert payload.get("ok") is True, payload
    assert payload.get("run_id") == ctx.run_id, payload

    service = payload.get("service") or {}
    assert isinstance(service.get("pid"), int) and service["pid"] > 0, payload
    ctx.service_pid = int(service["pid"])

    direct = public_run(SERVICE_PORT)
    assert direct is not None, "el registro persistente debe existir"
    assert direct["run_id"] == ctx.run_id
    assert direct["pid"] == ctx.service_pid
    assert direct["port"] == SERVICE_PORT
    assert direct["deadline_ms"] is not None
    assert direct["started_at_ms"] is not None
    assert direct["deadline_exceeded"] is False

    record = json.loads(read_path.read_text(encoding="utf-8"))
    assert record["run_id"] == ctx.run_id
    assert record["pid"] == ctx.service_pid
    assert record["deadline_ms"] == direct["deadline_ms"]

    h = wait_clock_ready(SERVICE_PORT, timeout_s=30.0)
    assert h is not None
    clock = h.get("clock") or {}
    assert clock.get("source") == "public_sincronizado", clock
    assert clock.get("available") is True, clock
    assert int(clock.get("samples_valid") or 0) > 0, clock
    assert ctx.provider.counts()["time"] == 5, ctx.provider.counts()


# ---------------------------------------------------------------------------
# B. Doble POST start concurrente (BFF productivo)
# ---------------------------------------------------------------------------

def test_b_concurrent_double_start_is_idempotent(acceptance: Acceptance) -> None:
    ctx = acceptance
    assert ctx.service_pid is not None, "A debe haber iniciado la corrida"
    time_before = ctx.provider.counts()["time"]
    results: List[Any] = []
    barrier = threading.Barrier(2)

    def fire() -> None:
        barrier.wait(timeout=10)
        results.append(_bff_public(
            ctx, "POST", {"action": "start", "run_id": ctx.run_id}))

    threads = [threading.Thread(target=fire) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    assert len(results) == 2, results

    for status, payload in results:
        assert status == 200, payload
        assert payload.get("ok") is True, payload
        assert payload.get("run_id") == ctx.run_id, payload
        assert (payload.get("service") or {}).get("pid") == ctx.service_pid

    # Una sola corrida, una sola identidad, sin recursos duplicados.
    direct = public_run(SERVICE_PORT)
    assert direct["run_id"] == ctx.run_id
    assert direct["pid"] == ctx.service_pid
    assert direct["deadline_ms"] is not None
    assert (ctx.provider.counts()["time"] - time_before) == 0, (
        "un segundo arranque habría repetido la sincronización y consumido "
        f"más /time: {ctx.provider.counts()}")

    status, sessions = http_json(
        ctx.bff.port, "/api/v1/engineering-sessions", host=CANONICAL_HOST)
    assert status == 200, sessions
    assert sessions.get("sessions") == [], (
        "el arranque no debe crear sesiones por sí mismo")


# ---------------------------------------------------------------------------
# C. Recorrido completo: BFF -> servicio -> reloj -> contexto -> sesión ->
#    cierre nuevo -> evaluación vinculada
# ---------------------------------------------------------------------------

def test_c_full_path_session_new_close_and_linked_evaluation(
        acceptance: Acceptance) -> None:
    ctx = acceptance
    h = wait_clock_ready(SERVICE_PORT, timeout_s=30.0)
    assert h is not None and (h.get("clock") or {}).get("available") is True, h

    now_ms = int(time.time() * 1000)
    payload = entry_payload(now_ms, request_id=f"acceptance-{ctx.run_id}")
    status, created = http_json(
        ctx.bff.port, "/api/v1/engineering-sessions", method="POST",
        body=payload, host=CANONICAL_HOST, timeout=30.0)
    assert status == 200, created
    session = created.get("session") or {}
    sid = session.get("session_id")
    assert sid, created
    ctx.session_id = sid
    ctx.session_at_creation = session

    # Contexto cerrado: todas las velas tienen cierre y el reloj T inicial es
    # el cierre de la última vela de contexto.
    ctx_close = [c.get("close_time_ms") for c in session.get("context_candles", [])]
    assert ctx_close and all(v is not None for v in ctx_close), session.get(
        "context_candles")
    expected_clock = max(ctx_close)
    assert session.get("clock_ms") == expected_clock, session.get("clock_ms")
    config_hash = session.get("config_hash")
    assert config_hash, session
    revision_at_creation = int(session.get("revision") or 0)

    status, started = http_json(
        ctx.bff.port,
        f"/api/v1/engineering-sessions/{sid}/control",
        method="POST", body={"action": "start"}, host=CANONICAL_HOST,
        timeout=30.0)
    assert status == 200, started

    def fetch() -> Optional[Dict[str, Any]]:
        st, body = http_json(
            ctx.bff.port, f"/api/v1/engineering-sessions/{sid}",
            host=CANONICAL_HOST, timeout=30.0)
        if st != 200 or not isinstance(body, dict):
            return None
        drive = body.get("drive") or {}
        sess = body.get("session") or {}
        if (sess.get("position") or {}).get("open") is True and \
                int(drive.get("events_processed") or 0) >= 3:
            return body
        return None

    final = _wait_until(fetch, timeout_s=40.0)
    assert isinstance(final, dict), (
        "la conducción no produjo posición abierta tras cierres nuevos: "
        f"{final}")
    ctx.final_session = final
    session = final["session"]
    drive = final["drive"]

    # Cierre nuevo: el reloj avanzó más allá del cierre de contexto y el
    # transporte procesó aperturas nuevas.
    assert session["clock_ms"] > expected_clock, session["clock_ms"]
    assert int(drive.get("events_processed") or 0) >= 3, drive
    assert session["revision"] > revision_at_creation, session["revision"]

    # Evaluación vinculada: misma sesión/config_hash, regla causal y T del
    # evento posterior al contexto (no un simple clock.available).
    config = session.get("config") or {}
    assert session.get("config_hash") == config_hash, session.get("config_hash")
    assert config.get("decision") == "ENTRADA_SIMULADA", config
    evidence = config.get("decision_evidence") or {}
    assert evidence.get("rule_version") == engine.RULE_CAUSAL_V1, evidence
    assert int(evidence.get("at_ms") or 0) > expected_clock, evidence

    # Entrada materializada por la autoridad económica (evento entry).
    events = session.get("events") or []
    kinds = [e.get("kind") for e in events]
    assert "entry" in kinds, kinds
    position = session.get("position") or {}
    assert position.get("open") is True, position
    assert float(position.get("entry_px") or 0) > 0, position

    # Una única sesión para el recorrido (sin duplicados del doble inicio).
    status, listing = http_json(
        ctx.bff.port, "/api/v1/engineering-sessions", host=CANONICAL_HOST)
    assert status == 200, listing
    ids = [s.get("session_id") for s in listing.get("sessions") or []]
    assert ids == [sid], ids


# ---------------------------------------------------------------------------
# D. Presupuesto: 5 /time + 2 klines REALES = 7; el 8.º no llega al transporte
# ---------------------------------------------------------------------------

def test_d_budget_seven_real_requests_then_blocked(acceptance: Acceptance) -> None:
    ctx = acceptance
    counts = ctx.provider.counts()
    assert counts["time"] == 5, counts
    assert counts["klines"] == 0, counts

    cache = MarketCache(db_path=ctx.cache_db)
    cache.init_db()
    assert cache.run_requests_used(ctx.run_id) == 5

    gate = LedgerAttemptGate(
        cache, ctx.run_id, max_requests=30, run_max_requests=7)
    client = HistoryClient(
        base_url=f"http://127.0.0.1:{ctx.provider.port}",
        attempt_gate=gate, execution_id=ctx.run_id, max_retries=0)

    start_ms = int(time.time() * 1000) - 10 * 60_000
    rows1, _ = client.klines("MINAUSDT", "1m", start_ms,
                             start_ms + 60_000, limit=2)
    rows2, _ = client.klines("MINAUSDT", "1m", start_ms + 60_000,
                             start_ms + 120_000, limit=2)
    assert rows1 and rows2, (rows1, rows2)

    counts = ctx.provider.counts()
    assert counts["time"] == 5, counts
    assert counts["klines"] == 2, counts
    assert counts["total"] == 7, counts
    assert cache.run_requests_used(ctx.run_id) == 7

    # El 8.º intento se reserva ANTES del envío y muere sin abrir socket.
    with pytest.raises(UpstreamBudgetExceeded):
        client.klines("MINAUSDT", "1m", start_ms + 120_000,
                      start_ms + 180_000, limit=1)
    assert ctx.provider.counts()["total"] == 7, (
        f"el intento bloqueado llegó al transporte: {ctx.provider.counts()}")
    assert ctx.provider.counts()["time"] == 5

    ledger = cache.fetch_rows_by_execution(ctx.run_id)
    assert len(ledger) == 8, [r.get("status") for r in ledger]
    assert [r for r in ledger if r.get("status") == "budget_blocked"], ledger
    ctx.ledger_counts = {
        "time": 5, "klines": 2, "total_provider": 7,
        "ledger_rows": len(ledger),
    }


# ---------------------------------------------------------------------------
# E. Consumo en la interfaz -> NO ACREDITADO (no se simula un PASS)
# ---------------------------------------------------------------------------

def test_e_ui_consumption_is_not_accredited(acceptance: Acceptance) -> None:
    ctx = acceptance
    # 1) El backend SÍ expone el consumo real del ledger (mismo run_id de la
    #    corrida que acaba de consumir 7 intentos). Eso es dato, no interfaz.
    status, body = _bff_public(ctx)
    assert status == 200, body
    run = body.get("publicRun") or {}
    assert run.get("run_id") == ctx.run_id, run
    assert run.get("http_attempts") == 7, run
    assert ctx.ledger_counts.get("total_provider") == 7, ctx.ledger_counts

    # 2) La interfaz NO lee el consumo ni el deadline: sólo los escribe en el
    #    estado React. `publicRun.httpAttempts` / `publicRun.deadlineExceeded`
    #    no aparecen en ninguna expresión renderizada (el panel muestra
    #    únicamente `publicRun.runId`).
    component = (ROOT / "frontend" / "src" / "components" / "session-lab" /
                 "EngineeringSession.tsx").read_text(encoding="utf-8")
    assert "publicRun.httpAttempts" not in component, (
        "el componente ahora lee el consumo: revisar si se renderiza")
    assert "publicRun.deadlineExceeded" not in component, (
        "el componente ahora lee el deadline: revisar si se renderiza")
    assert "publicRun.runId" in component  # lo único que sí se pinta

    # 3) El BFF productivo sólo admite Host 127.0.0.1:3020 (originAllowed) y
    #    3020 se preserva con el dashboard del operador: un navegador no puede
    #    ejercer la UI en el puerto aislado de la prueba.
    route = (ROOT / "frontend" / "src" / "app" / "api" / "v1" /
             "engineering-sessions" / "public" / "route.ts").read_text(
                 encoding="utf-8")
    assert 'host === "127.0.0.1:3020"' in route
    pytest.fail(
        "E NO ACREDITADO: el consumo real del ledger "
        f"(run {ctx.run_id}, {ctx.ledger_counts}) no se renderiza en la UI "
        "(el componente sólo lo guarda en estado) y la interfaz productiva no "
        "puede ejercerse en un puerto aislado (guardia de Host 3020, que se "
        "preserva). Un GET al backend prueba dato, no presentación ni "
        "actualización de UI.")


# ---------------------------------------------------------------------------
# F. Reinicio de la misma corrida -> NO ACREDITADO (bloqueado por presupuesto)
# ---------------------------------------------------------------------------

def test_f_restart_same_run_is_not_accredited(acceptance: Acceptance) -> None:
    ctx = acceptance
    # Mata el servicio propio (caída simulada) y reintenta la MISMA corrida
    # por el BFF. El pre-chequeo de presupuesto del backend exige 5 intentos
    # libres para sincronizar y ya hay 7 consumidos: la reanudación se
    # rechaza; no se otorga tiempo ni identidad nueva.
    pid = ctx.service_pid
    assert isinstance(pid, int) and pid_alive(pid)
    import subprocess
    subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                   capture_output=True, check=False)
    wait_port_free(SERVICE_PORT, timeout_s=15.0)
    record_before = json.loads(
        bff_public_run_path(ctx.service_root).read_text(encoding="utf-8"))
    time_before = ctx.provider.counts()["time"]

    status, payload = _bff_public(
        ctx, "POST", {"action": "start", "run_id": ctx.run_id})
    # Lo observable SÍ se conserva: no hay adquisiciones nuevas y el registro
    # persistente mantiene identidad, plazo y consumo (sin reactivarse).
    assert ctx.provider.counts()["time"] == time_before, (
        "la reanudación ejecutó adquisiciones nuevas")
    record_after = json.loads(
        bff_public_run_path(ctx.service_root).read_text(encoding="utf-8"))
    assert record_after["run_id"] == record_before["run_id"]
    assert record_after["started_at_ms"] == record_before["started_at_ms"]
    assert record_after["deadline_ms"] == record_before["deadline_ms"]
    assert is_listening(SERVICE_PORT) is False

    assert status == 503, payload
    assert payload.get("ok") is False, payload
    assert payload.get("error") == "ENGINEERING_SERVICE_EXITED", payload
    # La consulta del BFF ya no puede leer la corrida: sin backend vivo
    # informa "idle", perdiendo la identidad persistida en la interfaz.
    status_code, run = _bff_public(ctx)
    assert status_code == 200, run
    current = run.get("publicRun") or {}
    assert current.get("run_id") is None, current
    ctx.service_pid = None
    pytest.fail(
        "F NO ACREDITADO: la misma corrida no puede rearrancar tras consumir "
        "el presupuesto. El servicio sale con código 2 por el pre-chequeo "
        "(5/7 ya usados en sincronización) antes de escribir cualquier estado, "
        "así que no hay servicio vivo que conserve identidad/consumo/plazo; "
        "el BFF además pasa a informar run_id=null (idle). Reanudar una "
        "corrida ya sincronizada exigiría reutilizar su reloj, no volver a "
        "pedir 5 /time.")


# ---------------------------------------------------------------------------
# H. Parada con run_id ajeno y con identidad incierta
# ---------------------------------------------------------------------------

class _FakeCanonicalService:
    """Servicio local CONTROLADO con /health canónico y PID no verificable."""

    def __init__(self) -> None:
        outer = self
        self.shutdown_calls = 0
        self.health_calls = 0

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: N802
                return

            def do_GET(self) -> None:  # noqa: N802
                outer.health_calls += 1
                body = json.dumps({
                    "service": "engineering-session-service/v1",
                    "pid": 999_999,  # no coincide con el pid-file
                    "port": SERVICE_PORT,
                    "sessions_dir": str(outer.sessions_dir),
                    "clock": {"source": "public_sincronizado",
                              "available": True},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:  # noqa: N802
                outer.shutdown_calls += 1
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.sessions_dir = Path(tempfile.mkdtemp(prefix="fake-service-"))
        self.server = ThreadingHTTPServer(("127.0.0.1", SERVICE_PORT), Handler)
        self.server.daemon_threads = True
        self.server.handle_error = lambda *args: None  # cierres de keep-alive
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        try:
            self.server.shutdown()
        finally:
            self.server.server_close()


def test_h_stop_rejects_foreign_run_and_uncertain_identity(
        acceptance: Acceptance) -> None:
    ctx = acceptance
    record_path = bff_public_run_path(ctx.service_root)
    # Corrida propia viva: la de A si el servicio sigue en pie, o una nueva
    # (identidad y presupuesto propios) si F ya lo derribó.
    run_id = ctx.run_id
    if is_listening(SERVICE_PORT):
        existing = json.loads(record_path.read_text(encoding="utf-8"))
        assert existing["run_id"] == run_id, existing
        pid = int(existing["pid"])
        assert pid_alive(pid)
        ctx.service_pid = pid
    else:
        run_id = f"{ctx.run_id}-h"
        status, started = _bff_public(
            ctx, "POST", {"action": "start", "run_id": run_id})
        assert status == 200 and started.get("ok") is True, started
        assert started.get("run_id") == run_id, started
        pid = int((started.get("service") or {})["pid"])
        ctx.service_pid = pid
    assert pid_alive(pid)
    # H no juzga la sincronización del reloj: sólo la identidad del proceso y
    # la pertenencia de la corrida. Se registra el estado real del reloj como
    # observación (puede quedar no disponible si la ventana tiene actividad;
    # eso no altera la parada).
    ready = wait_health(SERVICE_PORT, timeout_s=30.0)
    assert ready is not None and ready.get("pid") == pid, ready
    clock_state = ready.get("clock") or {}
    ctx.clock_observed = {
        "available": clock_state.get("available"),
        "samples_valid": clock_state.get("samples_valid"),
        "samples_failed": clock_state.get("samples_failed"),
    }
    before = health(SERVICE_PORT)
    assert before is not None and before.get("pid") == pid

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["run_id"] == run_id, record
    assert record["pid"] == pid, record
    # El gestor BFF consulta OTRA ruta para verificar pertenencia (defecto
    # reproducido: falta el segmento "sessions").
    manager_record_path = bff_manager_run_record_path(ctx.service_root)
    manager_sees_record = manager_record_path.exists()

    def stop(run: str) -> Any:
        return _bff_public(ctx, "POST", {"action": "stop", "run_id": run})

    # --- H1: run_id ajeno sobre un servicio vivo identificado --------------
    status, foreign = stop("eng-run-ajena-000")
    assert status == 200, foreign
    assert foreign.get("service_stopped") is False, foreign
    assert is_listening(SERVICE_PORT) is True
    assert pid_alive(pid) is True
    after_foreign = health(SERVICE_PORT)
    assert after_foreign is not None and after_foreign.get("pid") == pid
    unchanged = json.loads(record_path.read_text(encoding="utf-8"))
    assert unchanged["run_id"] == run_id and unchanged["pid"] == pid

    # --- H2: parada legítima de la corrida propia --------------------------
    status, own = stop(run_id)
    assert status == 200, own
    own_stopped = own.get("service_stopped") is True
    if own_stopped:
        wait_port_free(SERVICE_PORT, timeout_s=20.0)
        assert is_listening(SERVICE_PORT) is False
        assert pid_alive(pid) is False
    else:
        # Sin parada: el proceso y el puerto siguen intactos (no se apagó
        # nada ajeno). Se detiene a mano para poder seguir con la prueba.
        assert is_listening(SERVICE_PORT) is True
        assert pid_alive(pid) is True
        assert http_json(SERVICE_PORT, "/shutdown", method="POST", body={},
                         host=f"127.0.0.1:{SERVICE_PORT}")[0] == 200
        wait_port_free(SERVICE_PORT, timeout_s=20.0)

    # --- H3: identidad incierta (proveedor local controlado) --------------
    fake = _FakeCanonicalService()
    try:
        fake.start()
        wait_port_listening(SERVICE_PORT, timeout_s=10.0)
        bff_pid_file(ctx.service_root).write_text(json.dumps({
            "pid": 888_888, "port": SERVICE_PORT, "host": "127.0.0.1",
            "service": "engineering-session-service/v1",
        }), encoding="utf-8")
        status, payload = stop(run_id)
        assert status == 200, payload
        assert payload.get("service_stopped") is False, payload
        detail = str(payload.get("detail") or "")
        assert ("no está en estado ready" in detail
                or "identidad" in detail.lower()), payload
        # No se tocó el proceso ajeno/incierto: ni shutdown ni muerte.
        assert fake.shutdown_calls == 0, fake.shutdown_calls
        assert is_listening(SERVICE_PORT) is True
    finally:
        fake.stop()
        wait_port_free(SERVICE_PORT, timeout_s=10.0)
        try:
            bff_pid_file(ctx.service_root).unlink(missing_ok=True)
        except OSError:
            pass
    ctx.service_pid = None

    if not own_stopped:
        pytest.fail(
            "H NO ACREDITADO: la parada con run_id ajeno se rechaza y no toca "
            "proceso/puerto (verificado), y la identidad incierta tampoco se "
            "apaga, pero la parada de la corrida PROPIA tampoco detiene el "
            "servicio: el gestor busca el registro en "
            f"{manager_record_path} (existe={manager_sees_record}) mientras el "
            f"backend lo persiste en {record_path} (run_id={run_id}, "
            f"pid={pid}). Sin ese registro no puede verificar pertenencia: "
            f"responde {own.get('detail')!r}. La corrida sólo se detiene a "
            "mano contra el backend. Reloj observado en esta corrida: "
            f"{ctx.clock_observed}.")


# ---------------------------------------------------------------------------
# I. Entrada real + parada conservando posición (sin salida inventada)
# ---------------------------------------------------------------------------

def test_i_stop_preserves_open_entry(acceptance: Acceptance) -> None:
    # Servicio REAL en modo local (sin reloj público: la secuencia local no
    # necesita adquisiciones) en puerto y directorios exclusivos.
    tmp = tempfile.TemporaryDirectory(prefix="entry-stop-")
    base = Path(tmp.name)
    guard = NetworkGuard(base)
    sessions = base / "sessions"
    port = free_port()
    proc = None
    try:
        proc = start_engineering_service(
            port, sessions, "entry-stop-run", guard, time_url=None,
            cache_db=base / "market_cache.db")
        h = wait_health(port, timeout_s=30.0)
        assert h is not None and h.get("service") == (
            "engineering-session-service/v1"), h

        now_ms = int(time.time() * 1000)
        payload = entry_payload(now_ms, "entry-stop-request")
        status, created = http_json(
            port, "/sessions", method="POST", body=payload,
            host=f"127.0.0.1:{port}", timeout=30.0)
        assert status == 200, created
        sid = created["session"]["session_id"]
        status, _ = http_json(
            port, f"/sessions/{sid}/control", method="POST",
            body={"action": "start"}, host=f"127.0.0.1:{port}", timeout=30.0)
        assert status == 200

        def opened() -> Optional[Dict[str, Any]]:
            st, body = http_json(
                port, f"/sessions/{sid}", host=f"127.0.0.1:{port}",
                timeout=20.0)
            if st != 200 or not isinstance(body, dict):
                return None
            position = (body.get("session") or {}).get("position") or {}
            events = (body.get("session") or {}).get("events") or []
            if position.get("open") is True and any(
                    e.get("kind") == "entry" for e in events):
                return body
            return None

        live = _wait_until(opened, timeout_s=40.0)
        assert isinstance(live, dict), (
            f"la secuencia local no produjo entrada real: {live}")
        session = live["session"]
        position = session["position"]
        assert session["config"]["decision"] == "ENTRADA_SIMULADA"
        assert float(position["entry_px"]) > 0
        assert position["entry_qty"] is not None and float(position["entry_qty"]) > 0
        assert session.get("result") is None, session.get("result")
        revision_before_stop = int(session["revision"])
        events_kinds = [e.get("kind") for e in session.get("events") or []]
        assert "entry" in events_kinds and "exit" not in events_kinds

        # Detener la conducción y después el servicio propio. El stop es
        # asíncrono (la conducción termina en el próximo límite de evento):
        # se espera el estado real, no se asume.
        status, stopped = http_json(
            port, f"/sessions/{sid}/control", method="POST",
            body={"action": "stop"}, host=f"127.0.0.1:{port}", timeout=20.0)
        assert status == 200, stopped

        def drive_stopped() -> Any:
            st, body = http_json(
                port, f"/sessions/{sid}", host=f"127.0.0.1:{port}",
                timeout=20.0)
            drive = (body or {}).get("drive") or {}
            return drive if st == 200 and drive.get("state") != "running" else None

        halted = _wait_until(drive_stopped, timeout_s=15.0)
        assert isinstance(halted, dict), halted
        assert halted.get("cause") in ("OPERATOR_STOP", "END_OF_TRANSPORT"), halted
        assert http_json(port, "/shutdown", method="POST", body={},
                         host=f"127.0.0.1:{port}")[0] == 200
        proc.wait(timeout=20.0)
        wait_port_free(port, timeout_s=15.0)
        owner = int(h["pid"])
        assert pid_alive(owner) is False

        # Estado persistido tras la parada: entrada y posición conservadas,
        # sin exit, salida, comisión de salida ni realizado inventados.
        state = engine.load_session(sid, str(sessions))
        assert state is not None, "la sesión debe persistir tras la parada"
        pub = engine.session_to_public_dict(state, state.clock_ms)
        assert pub["position"]["open"] is True, pub["position"]
        assert pub["position"]["entry_px"] == position["entry_px"]
        kinds = [e["kind"] for e in pub["events"]]
        assert kinds.count("entry") == 1, kinds
        assert "exit" not in kinds, kinds
        assert pub["result"] is None, pub["result"]
        assert float(pub["costs"]["exit_fees"]) == 0.0, pub["costs"]
        assert float(pub["costs"]["exit_fees_executed"]) == 0.0, pub["costs"]
        assert float(pub["costs"]["exit_spread_slip_executed"]) == 0.0, pub["costs"]
        assert int(pub["revision"]) == revision_before_stop, (
            "la parada no debe añadir revisiones/salidas nuevas")
        assert guard.blocked_lines() == []
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5.0)
        tmp.cleanup()


# ---------------------------------------------------------------------------
# J. Fallo de preparación: causa visible y limpieza efectiva
# ---------------------------------------------------------------------------

def test_j_preparation_failure_is_visible_and_cleaned() -> None:
    tmp = tempfile.TemporaryDirectory(prefix="prep-failure-")
    base = Path(tmp.name)
    guard = NetworkGuard(base)
    sessions = base / "sessions"
    port = free_port()
    proc = None
    try:
        proc = start_engineering_service(
            port, sessions, "prep-failure-run", guard,
            time_url="http://127.0.0.1:1/time",  # loopback sin escucha
            cache_db=base / "market_cache.db")
        h = wait_health(port, timeout_s=30.0)
        assert h is not None and h.get("service") == (
            "engineering-session-service/v1"), h
        clock = h.get("clock") or {}
        assert clock.get("available") is False, clock
        assert clock.get("source") == "public_sincronizado", clock
        record = public_run(port)
        assert record is not None and record.get("run_id") == "prep-failure-run"
        assert record.get("state") in ("preparing", "ready", "active"), record
        assert record.get("deadline_ms") is not None
        # Causa visible: la sincronización fallida no se disfraza de reloj ok.
        assert (base / f"service-{port}.err.log").exists()

        assert http_json(port, "/shutdown", method="POST", body={},
                         host=f"127.0.0.1:{port}")[0] == 200
        proc.wait(timeout=20.0)
        wait_port_free(port, timeout_s=15.0)
        assert is_listening(port) is False
        assert (sessions / "service.json").exists() is False
        assert guard.blocked_lines() == []
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5.0)
        tmp.cleanup()
