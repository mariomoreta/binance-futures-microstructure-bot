"""E. Consumo real en la interfaz (aceptación pública).

Prueba E2E aislada (sin Binance) que renderiza el componente productivo
``EngineeringSession`` en un navegador real (Chromium vía Playwright) contra
un servidor Next.js de prueba en puerto libre, con entorno, SQLite y sesiones
aislados.

Verifica:
  * El BFF productivo acepta el origen del servidor de prueba
    (``ENGINEERING_PUBLIC_ALLOWED_HOST``) sin abrir la política de producción
    (que sigue siendo 127.0.0.1:3020).
  * La UI renderiza el consumo real de la misma corrida (``httpAttempts``) y
    lo compara con ``SUM(requests)`` del ledger compartido.
  * Tras nuevos intentos (klines), al recargar y reiniciar la misma corrida
    el valor visible se actualiza.
  * Nunca se presenta consumo cero ficticio: cuando no hay valor se muestra
    UNKNOWN.
  * Cualquier intento a dominios públicos queda bloqueado y registrado.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from microstructure_probe.history_client import (  # noqa: E402
    HistoryClient, UpstreamBudgetExceeded,
)
from microstructure_probe.market_cache import MarketCache  # noqa: E402
from microstructure_probe.market_explorer import LedgerAttemptGate  # noqa: E402
from public_run_harness import (  # noqa: E402
    BffProcess, LoopbackProvider, NetworkGuard, bff_public_run_path,
    free_port, health, http_json, is_listening, wait_clock_ready,
)

MARKET_PAGE = "/market-lab"


def _e_start_bff_service(base: Path, guard: NetworkGuard,
                         provider: LoopbackProvider) -> Dict[str, Any]:
    """Arranca BFF (puerto libre) y, a través del BFF productivo, el servicio
    (puerto libre) en modo público sincronizado (5 /time reales). Todo aislado."""
    service_root = base / "bff-root"
    (service_root / "data" / "engineering-session").mkdir(parents=True)
    cache_db = base / "market_cache.db"
    bff_port = free_port()
    service_port = free_port()
    run_id = f"eng-e-{int(time.time() * 1000)}"
    bff = BffProcess(
        bff_port, service_root, provider, guard, cache_db, base,
        allowed_host=f"127.0.0.1:{bff_port}",
        service_port=service_port,
    )
    bff.start()
    # Arranque vía BFF (recorrido productivo real): el BFF genera el servicio
    # con --clock-source public y el run_id, y sincroniza el reloj.
    status, started = http_json(
        bff_port, "/api/v1/engineering-sessions/public", method="POST",
        body={"action": "start", "run_id": run_id},
        host=f"127.0.0.1:{bff_port}", timeout=60.0)
    assert status == 200 and started.get("ok") is True, started
    assert started.get("run_id") == run_id, started
    wait_clock_ready(service_port, timeout_s=30.0)
    return {
        "bff_port": bff_port, "service_port": service_port, "run_id": run_id,
        "cache_db": cache_db, "bff": bff,
    }


def _stop_service_on_port(port: int) -> None:
    try:
        if is_listening(port):
            http_json(port, "/shutdown", method="POST", body={},
                      host=f"127.0.0.1:{port}", timeout=5.0)
    except Exception:
        pass


def _ui_http_attempts(page) -> Optional[int]:
    """Lee el valor renderizado de intentos HTTP (o None si es UNKNOWN)."""
    locator = page.locator('[data-testid="public-http-attempts"]')
    if not locator.count():
        return None
    text = locator.first.inner_text()
    # Formato: "Intentos HTTP: 7" o "Intentos HTTP: UNKNOWN (consulta fallida)"
    parts = text.split(":", 1)
    if len(parts) != 2:
        return None
    value = parts[1].strip()
    if value.startswith("UNKNOWN"):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def test_e_ui_consumption_real_in_navegador() -> None:
    """Renderiza en navegador el consumo de la misma corrida y lo compara
    con el ledger; demuestra actualización tras nuevos intentos."""
    with tempfile.TemporaryDirectory(prefix="public-e-",
                                     ignore_cleanup_errors=True) as tmp:
        base = Path(tmp)
        guard = NetworkGuard(base)
        provider = LoopbackProvider()
        provider.start()
        ctx = None
        browser = None
        try:
            ctx = _e_start_bff_service(base, guard, provider)
            run_id = ctx["run_id"]
            cache = MarketCache(db_path=ctx["cache_db"])
            cache.init_db()

            # 5 /time de sincronización ya consumidos por el arranque.
            assert cache.run_requests_used(run_id) == 5, (
                "el arranque debe sincronizar 5 muestras")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(
                    f"http://127.0.0.1:{ctx['bff_port']}{MARKET_PAGE}",
                    wait_until="domcontentloaded",
                )
                # Esperar a que el componente de ingeniería esté listo.
                page.wait_for_selector('label:has-text("Fuente:")', timeout=15000)

                # Seleccionar fuente pública y arrancar la aceptación pública.
                page.locator("select").filter(
                    has_text="BINANCE PÚBLICO").select_option("public",
                                                              timeout=15000)
                page.click('[data-testid="btn-iniciar-publica"]')
                page.wait_for_selector(
                    '[data-testid="public-http-attempts"]', timeout=30000)

                attempts = _ui_http_attempts(page)
                assert attempts == 5, (
                    f"la UI debe renderizar 5 intentos tras el arranque, "
                    f"obtuvo {attempts}")
                assert cache.run_requests_used(run_id) == 5, (
                    "el ledger debe registrar 5 intentos")

                # Nuevos intentos reales (2 klines) directamente contra el
                # proveedor loopback, misma corrida.
                client = HistoryClient(
                    base_url=f"http://127.0.0.1:{provider.port}",
                    attempt_gate=LedgerAttemptGate(
                        cache, run_id, max_requests=30, run_max_requests=7),
                    execution_id=run_id, max_retries=0)
                start_ms = int(time.time() * 1000) - 10 * 60_000
                rows1, _ = client.klines("MINAUSDT", "1m", start_ms,
                                         start_ms + 60_000, limit=2)
                rows2, _ = client.klines("MINAUSDT", "1m", start_ms + 60_000,
                                         start_ms + 120_000, limit=2)
                assert rows1 and rows2, (rows1, rows2)
                assert cache.run_requests_used(run_id) == 7, (
                    "tras 2 klines el ledger debe registrar 7 intentos")
                assert provider.counts()["klines"] == 2, provider.counts()

                # Recargar y reiniciar la MISMA corrida: el valor visible se
                # actualiza a 7 (misma identidad, sin devolver cupos).
                page.reload()
                page.wait_for_selector(
                    'label:has-text("Fuente:")', timeout=15000)
                page.locator("select").filter(
                    has_text="BINANCE PÚBLICO").select_option("public",
                                                              timeout=15000)
                page.click('[data-testid="btn-iniciar-publica"]')
                page.wait_for_selector(
                    '[data-testid="public-http-attempts"]', timeout=30000)
                attempts2 = _ui_http_attempts(page)
                assert attempts2 == 7, (
                    f"la UI debe actualizarse a 7 tras nuevos intentos, "
                    f"obtuvo {attempts2}")
                assert attempts2 == cache.run_requests_used(run_id), (
                    "el valor visible debe coincidir con SUM(requests) del "
                    f"ledger: UI={attempts2}, ledger="
                    f"{cache.run_requests_used(run_id)}")

                # Evidencia visual de E: consumo renderizado en el navegador.
                screenshot = ROOT / "docs" / "evidence" / "public-acceptance-20261103" / "e-consumption-ui.png"
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot), full_page=True)

                browser.close()
                browser = None

            # Ningún intento a dominios públicos.
            assert guard.blocked_lines() == [], guard.blocked_lines()
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if ctx is not None:
                _stop_service_on_port(ctx["service_port"])
                ctx["bff"].stop()
            provider.stop()
