"""Pruebas focalizadas del arnés de sesión de ingeniería con proveedores locales
(sin Binance).

Usan el arnés exacto ``WindowOrchestrator`` (``scripts/engineering_live_window.py``)
con un proveedor HTTP local (``scripts/local_kline_provider.py``) que emula
``/fapi/v1/klines`` con cuatro comportamientos:

* ``ok``      : lista válida de klines cerradas (12 campos, cierre conocido en T).
* ``json_error`` : cuerpo JSON válido pero no lista (ej. error de Binance).
* ``non_json`` : cuerpo que no es JSON.
* ``empty``   : lista vacía ``[]``.

Se prueban ambos símbolos con precios muy distintos (BTCUSDT ~100000, MINAUSDT
~1.05), contexto reciente, símbolos separados, presupuesto preenvío
(LedgerAttemptGate reserva ANTES del transporte) y vencimiento del deadline
monotónico durante la preparación.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from engineering_live_window import (  # noqa: E402
    WindowOrchestrator,
    CACHE_DB,
)
from local_kline_provider import LocalKlineProvider  # noqa: E402
from microstructure_probe.market_cache import MarketCache  # noqa: E402

STEP_MS = 60_000


def _free_port() -> int:
    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_orchestrator(
    provider_port: int,
    symbols: str = "MINAUSDT,BTCUSDT",
    deadline: float = 60.0,
) -> WindowOrchestrator:
    class Args:
        pass
    a = Args()
    a.transport = "local"
    a.execute = False
    a.service_port = _free_port()
    a.engineering_port = _free_port()
    a.provider_port = provider_port
    a.ws_port = provider_port + 1
    a.dashboard = "http://127.0.0.1:3020"
    a.build_id = "test-build-id"
    a.symbols = symbols
    a.interval = "1m"
    a.bars = 300
    a.duration = 60.0
    a.deadline = deadline
    a.sessions_dir = str(
        Path(tempfile.mkdtemp(prefix="eng-live-test-sessions-")) / "sessions"
    )
    return WindowOrchestrator(a)


def _clear_ledger() -> None:
    """Borra las reservas de la ventana reciente para aislar tests."""
    con = sqlite3.connect(str(CACHE_DB))
    try:
        con.execute(
            "DELETE FROM market_fetch_ledger WHERE at_ms > ?",
            (int(time.time() * 1000) - 300_000,),
        )
        con.commit()
    finally:
        con.close()


def test_contexto_ok_ambos_simbolos_precios_distintos():
    """Lista válida de klines para BTCUSDT y MINAUSDT (precios muy distintos),
    contexto reciente, símbolos separados, presupuesto preenvío reservado."""
    port = _free_port()
    prov = LocalKlineProvider(port, {"BTCUSDT": "ok", "MINAUSDT": "ok"})
    prov.start()
    try:
        orch = _make_orchestrator(port)
        orch._validate_config()
        cache = MarketCache(CACHE_DB)
        try:
            cache.init_db()
        except Exception:
            pass
        _clear_ledger()
        antes = cache.requests_in_window(int(time.time() * 1000))
        ctx = orch._load_recent_context()
        despues = cache.requests_in_window(int(time.time() * 1000))

        chk = {c["id"]: c for c in orch.checks}
        assert chk["contexto_cargado"]["ok"] is True, chk["contexto_cargado"]
        ev = orch.evidence["contexto"]
        assert ev["velas"] == 600, ev  # 300 BTC + 300 MINA
        assert set(ev["symbols_seen"]) == {"BTCUSDT", "MINAUSDT"}, ev
        assert ev["rest_usadas"] == 2, ev  # una petición por símbolo
        assert ev["fuente"] == "proveedor_http_local"

        # Separación de identidades: cada vela lleva su symbol.
        simbolos_en_contexto = {c["symbol"] for c in ctx}
        assert simbolos_en_contexto == {"BTCUSDT", "MINAUSDT"}

        # Precios muy distintos preservados (no se confundieron símbolos).
        btc_closes = [c["close"] for c in ctx if c["symbol"] == "BTCUSDT"]
        mina_closes = [c["close"] for c in ctx if c["symbol"] == "MINAUSDT"]
        assert len(btc_closes) == 300, len(btc_closes)
        assert len(mina_closes) == 300, len(mina_closes)
        assert min(btc_closes) > max(mina_closes), (
            "BTCUSDT y MINAUSDT mantienen precios distintos: BTC min=%s, "
            "MINA max=%s" % (min(btc_closes), max(mina_closes)))

        # Presupuesto preenvío: LedgerAttemptGate reservó antes del envío.
        assert despues > antes, "el ledger debe haber crecido (reservas)"
        pd = {d["symbol"]: d for d in ev["parse_diag"]}
        for d in pd.values():
            assert d["result"] == "ok", d
            assert d.get("reserved_before_send") is True, d
            assert d["rows"] == 300, d
    finally:
        prov.stop()


def test_contexto_json_error_no_falla_catastroficamente():
    """JSON de error (no lista) se registra como diagnóstico, sin fallar el
    arnés; el otro símbolo sigue cargando (presupuesto permite 4 intentos)."""
    port = _free_port()
    prov = LocalKlineProvider(port, {"BTCUSDT": "json_error", "MINAUSDT": "ok"})
    prov.start()
    try:
        orch = _make_orchestrator(port)
        orch._validate_config()
        cache = MarketCache(CACHE_DB)
        try:
            cache.init_db()
        except Exception:
            pass
        _clear_ledger()
        ctx = orch._load_recent_context()
        assert orch.checks, "debe haber checks"
        chk = {c["id"]: c for c in orch.checks}
        assert chk["contexto_cargado"]["ok"] is True, chk["contexto_cargado"]
        ev = orch.evidence["contexto"]
        # Con max_retries=0, BTCUSDT gasta 1 intento y falla; MINAUSDT aún tiene
        # presupuesto y carga.
        assert ev["velas"] == 300, ev  # solo MINA
        assert set(ev["symbols_seen"]) == {"MINAUSDT"}, ev
        pd = {d["symbol"]: d for d in ev["parse_diag"]}
        assert pd["BTCUSDT"]["result"] == "exception", pd
        assert pd["MINAUSDT"]["result"] == "ok", pd
        assert pd["MINAUSDT"].get("reserved_before_send") is True
    finally:
        prov.stop()


def test_contexto_cuerpo_no_json_registra_excepcion():
    """Cuerpo no JSON se registra como excepción de parseo, sin fallar el
    arnés; MINAUSDT sigue cargando."""
    port = _free_port()
    prov = LocalKlineProvider(port, {"BTCUSDT": "non_json", "MINAUSDT": "ok"})
    prov.start()
    try:
        orch = _make_orchestrator(port)
        orch._validate_config()
        cache = MarketCache(CACHE_DB)
        try:
            cache.init_db()
        except Exception:
            pass
        _clear_ledger()
        ctx = orch._load_recent_context()
        ev = orch.evidence["contexto"]
        assert ev["velas"] == 300, ev  # solo MINA
        pd = {d["symbol"]: d for d in ev["parse_diag"]}
        assert pd["BTCUSDT"]["result"] == "exception", pd
        assert pd["MINAUSDT"]["result"] == "ok", pd
    finally:
        prov.stop()


def test_contexto_lista_vacia():
    """Lista vacía [] se acepta como contexto válido (0 velas para ese símbolo,
    el otro sigue cargando)."""
    port = _free_port()
    prov = LocalKlineProvider(port, {"BTCUSDT": "empty", "MINAUSDT": "ok"})
    prov.start()
    try:
        orch = _make_orchestrator(port)
        orch._validate_config()
        cache = MarketCache(CACHE_DB)
        try:
            cache.init_db()
        except Exception:
            pass
        _clear_ledger()
        ctx = orch._load_recent_context()
        ev = orch.evidence["contexto"]
        assert ev["velas"] == 300, ev  # solo MINA
        pd = {d["symbol"]: d for d in ev["parse_diag"]}
        assert pd["BTCUSDT"]["result"] == "ok", pd
        assert pd["BTCUSDT"]["rows"] == 0, pd
    finally:
        prov.stop()


def test_presupuesto_preenvio_reserva_antes_del_envio():
    """LedgerAttemptGate reserva 1 intento ANTES del transporte (fila reserved
    con requests=1) y la cierra con el resultado real tras el envío."""
    port = _free_port()
    prov = LocalKlineProvider(port, {"BTCUSDT": "ok", "MINAUSDT": "ok"})
    prov.start()
    try:
        orch = _make_orchestrator(port)
        orch._validate_config()
        cache = MarketCache(CACHE_DB)
        try:
            cache.init_db()
        except Exception:
            pass
        _clear_ledger()
        antes = cache.requests_in_window(int(time.time() * 1000))
        orch._load_recent_context()
        despues = cache.requests_in_window(int(time.time() * 1000))

        ev = orch.evidence["contexto"]
        assert ev["rest_usadas"] <= 4, ev
        assert despues > antes, "reservas registradas en ledger: antes=%s despues=%s" % (antes, despues)

        con = sqlite3.connect(str(CACHE_DB))
        try:
            rows = con.execute(
                "SELECT status, COUNT(*) n FROM market_fetch_ledger "
                "WHERE at_ms > ? GROUP BY status",
                (int(time.time() * 1000) - 300_000,)).fetchall()
        finally:
            con.close()
        estados = {r[0]: r[1] for r in rows}
        assert "ok" in estados, estados  # al menos una completada como ok
    finally:
        prov.stop()


def test_vencimiento_durante_preparacion():
    """Deadline monotónico único: vencido durante la preparación lanza
    GLOBAL_DEADLINE_EXCEEDED."""
    port = _free_port()
    prov = LocalKlineProvider(port, {"BTCUSDT": "ok", "MINAUSDT": "ok"})
    prov.start()
    try:
        orch = _make_orchestrator(port, deadline=0.05)  # 50 ms
        orch._validate_config()
        orch.deadline_monotonic = time.monotonic() - 1.0
        try:
            orch._check_deadline("preparacion")
            assert False, "debió lanzar GLOBAL_DEADLINE_EXCEEDED"
        except RuntimeError as exc:
            assert "GLOBAL_DEADLINE_EXCEEDED" in str(exc), str(exc)
    finally:
        prov.stop()


def test_identidades_no_se_deduplican_por_timestamp():
    """BTCUSDT y MINAUSDT mantienen su símbolo; nunca se dedupe solo por
    timestamp entre símbolos distintos."""
    port = _free_port()
    prov = LocalKlineProvider(port, {"BTCUSDT": "ok", "MINAUSDT": "ok"})
    prov.start()
    try:
        orch = _make_orchestrator(port)
        orch._validate_config()
        cache = MarketCache(CACHE_DB)
        try:
            cache.init_db()
        except Exception:
            pass
        _clear_ledger()
        ctx = orch._load_recent_context()
        claves = [(c["symbol"], c["open_time_ms"]) for c in ctx]
        assert len(claves) == len(set(claves)), "duplicados inesperados"
        btc_times = {c["open_time_ms"] for c in ctx if c["symbol"] == "BTCUSDT"}
        mina_times = {c["open_time_ms"] for c in ctx if c["symbol"] == "MINAUSDT"}
        interseccion = btc_times & mina_times
        assert len(interseccion) > 0, "esperaba tiempos comunes entre símbolos"
        assert sum(1 for c in ctx if c["symbol"] == "BTCUSDT") == 300
        assert sum(1 for c in ctx if c["symbol"] == "MINAUSDT") == 300
    finally:
        prov.stop()


if __name__ == "__main__":  # pragma: no cover
    import traceback
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print("FAIL", t.__name__)
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
