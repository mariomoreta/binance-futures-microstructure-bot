"""Regresión del defecto terminal del deadline de la corrida pública.

Reproduce la contradicción: el watcher establecía ``state=deadline_exceeded``
y ``is_deadline_exceeded()`` devolvía False en ese mismo estado, de modo que el
bucle principal nunca cerraba el servidor. Estos tests fallan con el código
anterior y pasan con la semántica corregida (plazo / terminal / limpieza).

Cubre además la verificación de PROCESO y PUERTO (no solo el JSON), y que
reiniciar la misma corrida vencida no la reactiva ni ejecuta adquisiciones.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from microstructure_probe.engineering_session_service import (  # noqa: E402
    EngineeringSessionController,
    PublicRunRecord,
)
from public_run_harness import (  # noqa: E402
    LoopbackProvider, NetworkGuard, entry_payload, free_port, is_listening,
    pid_alive, start_engineering_service, wait_health, wait_port_free,
)


# ---------------------------------------------------------------------------
# 1. Semántica: plazo vencido vs estado terminal vs limpieza
# ---------------------------------------------------------------------------

def test_terminal_deadline_state_reports_exceeded() -> None:
    """El estado terminal deadline_exceeded DEBE contar como vencido."""
    with tempfile.TemporaryDirectory(prefix="deadline-unit-") as tmp:
        pr = PublicRunRecord(Path(tmp))
        pr.run_id = "run-unit"
        pr.state = "preparing"
        pr.started_at_ms = int(time.time() * 1000)
        pr.deadline_ms = pr.started_at_ms + 180_000

        # Plazo en curso: no vencido, no terminal.
        assert pr.deadline_passed() is False
        assert pr.is_terminal() is False
        assert pr.is_deadline_exceeded() is False

        pr.mark_deadline_exceeded()

        # Contradicción reproducida: con el código anterior esto era False.
        assert pr.state == "deadline_exceeded"
        assert pr.is_deadline_exceeded() is True
        assert pr.is_terminal() is True
        # El deadline persistido NO se reescribe al marcar el terminal.
        assert pr.deadline_ms == pr.started_at_ms + 180_000
        assert pr.cause == "PUBLIC_RUN_DEADLINE_EXCEEDED"


def test_deadline_passed_is_a_time_fact_not_a_state() -> None:
    """``deadline_passed`` distingue el hecho temporal del estado terminal."""
    with tempfile.TemporaryDirectory(prefix="deadline-unit-") as tmp:
        now = int(time.time() * 1000)
        pr = PublicRunRecord(Path(tmp))
        pr.run_id = "run-time"
        pr.state = "preparing"
        pr.started_at_ms = now - 10_000
        pr.deadline_ms = now - 1

        assert pr.deadline_passed() is True
        assert pr.is_terminal() is False
        assert pr.is_deadline_exceeded() is True

        # Parada normal (limpieza) no es un vencimiento ni un terminal.
        pr.mark_stopped("SERVICE_SHUTDOWN")
        assert pr.state == "stopped"
        assert pr.is_terminal() is False
        assert pr.is_deadline_exceeded() is False
        assert pr.cleanup_cause == "SERVICE_SHUTDOWN"

        # La limpieza de una corrida vencida conserva causa terminal.
        pr2 = PublicRunRecord(Path(tmp))
        pr2.run_id = "run-cleanup"
        pr2.state = "preparing"
        pr2.deadline_ms = now + 1_000
        pr2.mark_deadline_exceeded()
        pr2.mark_stopped("SERVICE_SHUTDOWN")
        assert pr2.cause == "PUBLIC_RUN_DEADLINE_EXCEEDED"
        assert pr2.cleanup_cause == "SERVICE_SHUTDOWN"
        assert pr2.is_deadline_exceeded() is True


def test_restart_of_terminal_run_does_not_reactivate() -> None:
    """Persistir terminal y recargar: begin() rechaza, sin devolver plazo."""
    with tempfile.TemporaryDirectory(prefix="deadline-unit-") as tmp:
        sessions = Path(tmp)
        pr = PublicRunRecord(sessions)
        pr.run_id = "run-terminal"
        pr.state = "preparing"
        pr.started_at_ms = 1_700_000_000_000
        pr.deadline_ms = 1_700_000_180_000
        pr.mark_deadline_exceeded()

        reloaded = PublicRunRecord(sessions)
        reloaded._load()
        assert reloaded.state == "deadline_exceeded"
        assert reloaded.deadline_ms == 1_700_000_180_000

        with pytest.raises(ValueError):
            reloaded.begin("run-terminal", "public", "MINAUSDT", "1m", 1, 1)

        assert reloaded.state == "deadline_exceeded"
        assert reloaded.started_at_ms == 1_700_000_000_000
        assert reloaded.deadline_ms == 1_700_000_180_000
        assert reloaded.is_deadline_exceeded() is True


# ---------------------------------------------------------------------------
# 2. Tras vencer: ninguna adquisición ni conducción nueva
# ---------------------------------------------------------------------------

def test_expired_run_blocks_new_session_and_new_drive() -> None:
    with tempfile.TemporaryDirectory(prefix="deadline-guard-") as tmp:
        sessions = Path(tmp)
        pr = PublicRunRecord(sessions)
        pr.run_id = "run-guard"
        pr.state = "preparing"
        pr.started_at_ms = int(time.time() * 1000)
        pr.deadline_ms = pr.started_at_ms + 180_000
        ctl = EngineeringSessionController(
            sessions, cadence_ms=200.0, now_ms=lambda: int(time.time() * 1000),
            public_run=pr)

        payload = entry_payload(int(time.time() * 1000), "guard-create-1")
        created = ctl.create_session(payload)
        sid = created["session"]["session_id"]

        # Venció el plazo mientras el watcher aún no había hecho su tick.
        pr.deadline_ms = int(time.time() * 1000) - 1

        with pytest.raises(RuntimeError) as exc_create:
            ctl.create_session(entry_payload(int(time.time() * 1000),
                                             "guard-create-2"))
        assert "PUBLIC_RUN_DEADLINE_EXCEEDED" in str(exc_create.value)

        with pytest.raises(RuntimeError) as exc_start:
            ctl.control(sid, {"action": "start"})
        assert "PUBLIC_RUN_DEADLINE_EXCEEDED" in str(exc_start.value)

        # La parada de limpieza sigue permitida: terminar no es trabajo nuevo.
        ctl.control(sid, {"action": "stop"})
        assert pr.state == "deadline_exceeded"
        closed = ctl.control(sid, {"action": "stop_session"})
        assert closed["session"]["status"] in ("cerrada", "detenida"), closed
        assert pr.state == "deadline_exceeded"
        assert pr.is_deadline_exceeded() is True


# ---------------------------------------------------------------------------
# 3. Proceso y puerto: el servidor propio termina sin navegador ni Next.js
# ---------------------------------------------------------------------------

def test_short_deadline_terminates_process_and_port() -> None:
    with tempfile.TemporaryDirectory(prefix="deadline-proc-") as tmpdir:
        base = Path(tmpdir)
        sessions = base / "sessions"
        cache_db = base / "market_cache.db"
        guard = NetworkGuard(base)
        provider = LoopbackProvider()
        provider.start()
        port = free_port()
        run_id = f"deadline-proc-{int(time.time() * 1000)}"
        proc = None
        try:
            proc = start_engineering_service(
                port, sessions, run_id, guard, time_url=provider.time_url,
                deadline_s=2, cache_db=cache_db)
            h = wait_health(port, timeout_s=30.0)
            assert h is not None and h.get("service") == (
                "engineering-session-service/v1"), h
            owner_pid = int(h["pid"])

            # El watcher vence a los ~2 s; el bucle principal debe cerrar el
            # servidor por sí mismo (sin React, sin navegador, sin Next.js).
            proc.wait(timeout=25.0)
            assert proc.returncode == 0
            wait_port_free(port, timeout_s=15.0)
            assert is_listening(port) is False
            assert pid_alive(owner_pid) is False

            record = json.loads(
                (sessions / "public-run.json").read_text(encoding="utf-8"))
            assert record["run_id"] == run_id
            assert record["state"] == "deadline_exceeded"
            assert record["cause"] == "PUBLIC_RUN_DEADLINE_EXCEEDED"
            assert record["started_at_ms"] is not None
            assert record["deadline_ms"] == record["started_at_ms"] + 2_000
            assert record["pid"] == owner_pid
            assert record["port"] == port
            assert (sessions / "service.json").exists() is False

            # La sincronización del reloj consumió exactamente 5 /time reales.
            counts = provider.counts()
            assert counts["time"] == 5, counts
            assert counts["other"] == 0, counts
            assert guard.blocked_lines() == []

            # Reiniciar la MISMA corrida vencida: no reactiva ni adquiere.
            proc2 = start_engineering_service(
                port, sessions, run_id, guard, time_url=provider.time_url,
                deadline_s=2, cache_db=cache_db)
            try:
                proc2.wait(timeout=20.0)
            finally:
                if proc2.poll() is None:
                    proc2.kill()
                    proc2.wait(timeout=5.0)
            assert proc2.returncode == 2
            wait_port_free(port, timeout_s=15.0)
            assert provider.counts()["time"] == 5  # ninguna adquisición nueva
            record2 = json.loads(
                (sessions / "public-run.json").read_text(encoding="utf-8"))
            assert record2["state"] == "deadline_exceeded"
            assert record2["cause"] == "PUBLIC_RUN_DEADLINE_EXCEEDED"
            assert record2["started_at_ms"] == record["started_at_ms"]
            assert record2["deadline_ms"] == record["deadline_ms"]
            assert guard.blocked_lines() == []
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5.0)
            provider.stop()
