"""Pruebas del motor de ingeniería Paper Lab (backend).

Prueba la orquestación incremental de sesiones sobre fixtures:
creacion, entrada, gestion (stop/horizon), salida manual, reinicio,
detencion, persistencia y validacion de identificadores.

No hay Binance, no hay feed vivo, no hay ordenes reales.
"""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from microstructure_probe.paper_lab_engine import (  # noqa: E402
    ENGINE_VERSION_PAPER,
    PaperCandle,
    PaperSessionConfig,
    create_session,
    list_sessions,
    load_session,
    manual_exit,
    restart_session,
    save_session,
    session_to_dict,
    session_from_dict,
    step_forward,
    stop_session,
)

# --- helpers ----------------------------------------------------------------

def mk_candle(open_time_ms, open_, high, low, close):
    return PaperCandle(
        open_time_ms=open_time_ms, open=open_, high=high,
        low=low, close=close, close_time_ms=open_time_ms + 15 * 60 * 1000 - 1,
    )


def mk_config(symbol="BTCUSDT", direction="LONG", entry_px=100.0, stop_px=95.0,
              horizon_ms=3 * 60 * 60 * 1000, notional_usdt=1000.0,
              fee_bps=5.0, spread_bps=1.0, slippage_bps=2.0,
              stop_distance_pct=5.0):
    return PaperSessionConfig(
        symbol=symbol, interval="15m", direction=direction,
        notional_usdt=notional_usdt, entry_px=entry_px, stop_px=stop_px,
        stop_distance_pct=stop_distance_pct, horizon_ms=horizon_ms,
        fee_bps=fee_bps, spread_bps=spread_bps, slippage_bps=slippage_bps,
    )


def up_candles(n=3, start=0, base=100.0, drift=0.01):
    """Velas que suben levemente (favorable para LONG)."""
    out = []
    px = base
    for i in range(n):
        c = mk_candle(start + i * 15 * 60 * 1000, px, px * 1.02, px * 0.99,
                      px * (1 + drift))
        out.append(c)
        px = c.close
    return out


# --- pruebas ----------------------------------------------------------------

def test_create_session_sin_iniciar():
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    assert s.status == "sin_iniciar"
    assert s.position.open is False
    assert s.result is None
    assert s.cursor == 0
    assert s.config_hash is not None
    assert len(s.config_hash) == 16
    assert s.engine_version == ENGINE_VERSION_PAPER


def test_step_forward_applies_entrada():
    """De en_espera, el primer step_forward ejecuta la entrada."""
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    s.status = "en_espera"  # decision ENTRADA_SIMULADA ya tomada
    r = step_forward(s)
    assert r.status == "abierta"
    assert r.position.open is True
    assert r.position.entry_px == 100.0
    assert r.position.entry_qty == 1000.0 / 100.0  # 10.0
    assert r.position.mark_px == 100.0  # marca = precio de entrada
    assert any(e.kind == "entry" for e in r.events)
    assert r.clock_ms == candles[0].close_time_ms


def test_step_forward_actualiza_marca_y_pnl():
    """Avance con posición abierta actualiza marca y P&L no realizado."""
    config = mk_config()
    candles = up_candles(3)  # 100 -> 101 -> 102
    s = create_session(config, candles)
    s.status = "en_espera"
    r = step_forward(s)  # entrada en vela 0
    assert r.status == "abierta"
    r = step_forward(r)  # avance a vela 1
    r = step_forward(r)  # avance a vela 2
    assert abs(r.position.mark_px - 102.01) < 0.01  # close de vela 1
    assert r.position.unrealized_gross is not None
    assert r.position.unrealized_gross > 0  # favorable para LONG
    assert any(e.kind == "mark" for e in r.events)


def test_salida_por_stop():
    """Vela cuyo low toca el stop cierra al precio de stop."""
    config = mk_config(stop_px=95.0)
    candles = [
        mk_candle(0, 100, 102, 99, 101),
        mk_candle(900000, 101, 101, 94, 100),  # low=94 <= stop=95
    ]
    s = create_session(config, candles)
    s.status = "en_espera"
    r = step_forward(s)  # entrada en vela 0
    r = step_forward(r)  # gestion vela 0 (sin stop aun)
    r = step_forward(r)  # gestion vela 1: stop hit (low=94 <= 95)
    assert r.status == "cerrada"
    assert r.position.open is False
    assert r.position.mark_px == 95.0
    assert r.result.exit_reason == "stop"
    assert r.result.exit_executed is True
    assert r.result.gross_pnl == (95.0 - 100.0) * 10.0  # -50
    assert r.result.net_pnl < -50  # menos costes


def test_salida_por_horizonte():
    """Al alcanzar entry_ms + horizon_ms cierra al precio de marca."""
    config = mk_config(horizon_ms=15 * 60 * 1000)  # 1 vela
    candles = up_candles(3)
    s = create_session(config, candles)
    s.status = "en_espera"
    r = step_forward(s)  # entrada en vela 0
    r = step_forward(r)  # gestion vela 0
    r = step_forward(r)  # gestion vela 1: clock >= horizon
    assert r.status == "cerrada"
    assert r.result.exit_reason == "horizon"
    assert r.result.exit_executed is True


def test_salida_manual():
    """Cierre manual congela el resultado."""
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    s.status = "en_espera"
    r = step_forward(s)  # entrada
    r = step_forward(r)  # avance, marca 101
    m = manual_exit(r)
    assert m.status == "cerrada"
    assert m.position.open is False
    assert m.result.exit_reason == "manual"
    assert m.result.exit_executed is True


def test_open_at_end_sin_salida_ejecutada():
    """Agotamiento de datos: posicion permanece abierta, no realizada."""
    config = mk_config(horizon_ms=999999999)  # nunca alcanza horizonte
    candles = up_candles(2)  # solo 2 velas
    s = create_session(config, candles)
    s.status = "en_espera"
    r = step_forward(s)  # entrada en vela 0
    r = step_forward(r)  # gestion vela 0
    r = step_forward(r)  # gestion vela 1 (ultima) -> open_at_end
    assert r.status == "cerrada"
    assert r.result.open_at_end is True
    assert r.result.exit_executed is False
    assert r.result.exit_reason is None


def test_restart_restaura_sin_iniciar():
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    s.status = "en_espera"
    r = step_forward(s)  # abierta
    rs = restart_session(r)
    assert rs.status == "sin_iniciar"
    assert rs.position.open is False
    assert rs.result is None
    assert rs.cursor == 0


def test_stop_congelar_abierta():
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    s.status = "en_espera"
    r = step_forward(s)  # abierta
    st = stop_session(r)
    assert st.status == "detenida"
    assert st.position.open is True


def test_save_y_carga_sesion():
    """Persistencia: guardar y recargar conserva el estado."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = mk_config()
        candles = up_candles(3)
        s = create_session(config, candles)
        s.status = "en_espera"
        r = step_forward(s)  # abierta
        save_session(r, tmpdir)
        loaded = load_session(r.session_id, tmpdir)
        assert loaded is not None
        assert loaded.session_id == r.session_id
        assert loaded.status == "abierta"
        assert loaded.position.open is True
        assert loaded.position.entry_px == 100.0
        assert loaded.config_hash == r.config_hash


def test_session_id_traversal_rechazado():
    """Identificadores con traversal deben ser rechazados."""
    from microstructure_probe.paper_lab_engine import _safe_session_id
    import pytest  # noqa: F841
    try:
        _safe_session_id("../../../etc/passwd")
        assert False, "deberia haber lanzado ValueError"
    except ValueError:
        pass
    try:
        _safe_session_id("..")
        assert False, "deberia haber lanzado ValueError"
    except ValueError:
        pass
    # Valido
    assert _safe_session_id("PL-BTCUSDT-LONG-1234567890-abcd1234") == \
        "PL-BTCUSDT-LONG-1234567890-abcd1234"


def test_list_sessions_vacio():
    with tempfile.TemporaryDirectory() as tmpdir:
        summaries = list_sessions(tmpdir)
        assert summaries == []


def test_serializacion_roundtrip():
    config = mk_config()
    candles = up_candles(2)
    s = create_session(config, candles)
    s.status = "en_espera"
    r = step_forward(s)
    d = session_to_dict(r)
    r2 = session_from_dict(d)
    assert r2.session_id == r.session_id
    assert r2.status == r.status
    assert r2.position.open == r.position.open
    assert r2.config_hash == r.config_hash


def test_horizon_salida_con_precio_distinto_de_marca():
    """Salida por stop con precio distinto de la marca (reconciliación)."""
    config = mk_config(entry_px=100.0, stop_px=90.0)  # stop lejano
    candles = [
        mk_candle(0, 100, 102, 99, 101),
        mk_candle(900000, 101, 101, 85, 100),  # low=85 <= stop=90
    ]
    s = create_session(config, candles)
    s.status = "en_espera"
    r = step_forward(s)  # entrada en vela 0
    r = step_forward(r)  # gestion vela 0
    r = step_forward(r)  # gestion vela 1: stop hit (low=85 <= 90)
    assert r.status == "cerrada"
    assert r.result.exit_reason == "stop"
    assert r.position.mark_px == 90.0  # salida al stop, no a la marca
    assert r.result.exit_px == 90.0
    assert r.result.gross_pnl == (90.0 - 100.0) * 10.0  # -100


if __name__ == "__main__":
    test_create_session_sin_iniciar()
    test_step_forward_applies_entrada()
    test_step_forward_actualiza_marca_y_pnl()
    test_salida_por_stop()
    test_salida_por_horizonte()
    test_salida_manual()
    test_open_at_end_sin_salida_ejecutada()
    test_restart_restaura_sin_iniciar()
    test_stop_congelar_abierta()
    test_save_y_carga_sesion()
    test_session_id_traversal_rechazado()
    test_list_sessions_vacio()
    test_serializacion_roundtrip()
    test_horizon_salida_con_precio_distinto_de_marca()
    print("Todas las pruebas del motor de ingeniería pasaron.")
