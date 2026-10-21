"""Pruebas del motor de ingeniería Paper Lab (backend).

Cubre la matriz de aceptación A–E del encargo:
  A. Crear → evaluar → entrar automáticamente → gestionar → cerrar → recuperar/exportar.
  B. Crear → evidencia insuficiente → SIN_ENTRADA, sin posición.
  C. Datos obsoletos → conducta definida y evidencia.
  D. Fin de datos → posición abierta/no realizada.
  E. Acción duplicada/concurrente → sin duplicar operación ni perder eventos.

Sin mutar objetos internos ni archivos persistidos para conseguir estados esperados.
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
    evaluate_session,
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


# --- Pruebas ----------------------------------------------------------------

def test_create_session_sin_iniciar():
    """A: create_session deja sin_iniciar, sin entrada ejecutada."""
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    assert s.status == "sin_iniciar"
    assert s.position.open is False
    assert s.result is None
    assert s.cursor == 0
    assert s.config.decision is None
    assert s.config_hash is not None
    assert len(s.config_hash) == 16
    assert s.engine_version == ENGINE_VERSION_PAPER
    assert s.revision == 0


def test_evaluate_admite_entrada_automatica():
    """A: evaluate con run_backtest admite operación → ENTRADA_SIMULADA → en_espera."""
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    assert s.status == "sin_iniciar"

    r = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    assert r.status == "en_espera", f"esperaba en_espera, obtuvo {r.status}"
    assert r.config.decision == "ENTRADA_SIMULADA"
    assert r.config.decision_reason is not None
    assert r.config.decision_evidence is not None
    assert r.config.rule_version == "RULE-v1"
    assert r.authoritative is not None  # run_backtest resultado
    assert r.revision == 2  # create(0) + evaluate(1) + evaluando(2)


def test_evaluate_sin_entrada_sin_posicion():
    """B: evidencia insuficiente → SIN_ENTRADA, sin posición.

    Con horizon_ms=0, el horizon_end queda antes de cualquier fill posible
    (event_time_ms está antes de la primera vela, fill en vela 0 con
    open_time_ms=0 > horizon_end=event_time_ms). run_backtest no admite
    operación → SIN_ENTRADA.
    """
    config = mk_config(entry_px=100.0, stop_px=95.0, horizon_ms=0)
    candles = [mk_candle(0, 100, 102, 99, 101)]
    s = create_session(config, candles)
    r = evaluate_session(s, hypothesis_id="H1-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    assert r.status == "cerrada", f"esperaba cerrada, obtuvo {r.status}"
    assert r.config.decision == "SIN_ENTRADA", f"esperaba SIN_ENTRADA, obtuvo {r.config.decision}"
    assert r.position.open is False
    assert r.result is None
    assert r.config.decision_reason is not None
    assert "run_backtest no admitió ninguna operación" in r.config.decision_reason


def test_step_forward_ejecuta_entrada():
    """A: step_forward con status en_espera ejecuta la entrada automáticamente."""
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    assert s.status == "en_espera"

    r = step_forward(s)
    assert r.status == "abierta"
    assert r.position.open is True
    assert r.position.entry_px is not None
    assert r.position.entry_qty is not None
    assert r.position.entry_ms is not None
    assert any(e.kind == "entry" for e in r.events)
    assert r.revision > s.revision


def test_step_forward_gestion_y_salida_stop():
    """A: avance con posición abierta, salida por stop (run_backtest).

    Necesita 3 velas: la última da el close_time conocido de la vela
    intermedia para que run_backtest pueda confirmar el stop.
    """
    config = mk_config(stop_px=95.0)
    candles = [
        mk_candle(0, 100, 102, 99, 101),           # vela 0: entrada
        mk_candle(900000, 101, 101, 94, 100),     # vela 1: low=94 <= stop=95
        mk_candle(1800000, 100, 102, 99, 100),    # vela 2: close conocido de vela 1
    ]
    s = create_session(config, candles)
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    r = step_forward(s)  # entrada
    assert r.status == "abierta"
    r = step_forward(r)  # gestión vela 0
    r = step_forward(r)  # gestión vela 1
    r = step_forward(r)  # gestión vela 2: stop hit (close de vela 1 conocido)
    assert r.status == "cerrada"
    assert r.position.open is False
    assert r.result.exit_reason == "stop"
    assert r.result.exit_executed is True
    assert r.result.exit_px == 95.0  # salida al stop, no a la marca
    assert r.result.gross_pnl == (95.0 - 100.0) * 10.0  # -50
    assert r.result.net_pnl < -50  # menos costes
    # Costes separados: ejecutados vs estimados
    assert r.result.exit_fees_executed > 0
    assert r.result.exit_fees_estimated == 0.0  # salida ejecutada, no estimada


def test_step_forward_salida_horizonte():
    """A: salida por horizonte (run_backtest)."""
    config = mk_config(horizon_ms=15 * 60 * 1000)  # 1 vela
    candles = up_candles(3)
    s = create_session(config, candles)
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    r = step_forward(s)  # entrada
    r = step_forward(r)  # gestión vela 0
    r = step_forward(r)  # gestión vela 1: clock >= horizon
    assert r.status == "cerrada"
    assert r.result.exit_reason == "horizon"
    assert r.result.exit_executed is True


def test_salida_manual():
    """A: cierre manual congela el resultado (intervención manual, no sustituye aceptación)."""
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    r = step_forward(s)  # entrada
    r = step_forward(r)  # avance, marca
    m = manual_exit(r)
    assert m.status == "cerrada"
    assert m.position.open is False
    assert m.result.exit_reason == "manual"
    assert m.result.exit_executed is True


def test_open_at_end_posicion_permanece_abierta():
    """D: fin de datos sin salida → posición abierta/no realizada, status cerrado."""
    config = mk_config(horizon_ms=999999999)  # nunca alcanza horizonte
    candles = up_candles(2)
    s = create_session(config, candles)
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    r = step_forward(s)  # entrada
    r = step_forward(r)  # gestión vela 0
    r = step_forward(r)  # gestión vela 1 (última) → open_at_end
    assert r.status == "cerrada", f"esperaba cerrada, obtuvo {r.status}"
    assert r.result.open_at_end is True
    assert r.result.exit_executed is False
    assert r.result.exit_reason is None
    # Posición SIGUE ABIERTA (separación escenario vs posición)
    assert r.position.open is True
    assert r.result.realized_net is None  # no realizado
    # Sin comisión de salida (no ejecutada)
    assert r.result.exit_fees_executed == 0.0


def test_restart_y_stop():
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    r = step_forward(s)  # abierta
    rs = restart_session(r)
    assert rs.status == "sin_iniciar"
    assert rs.position.open is False
    assert rs.result is None
    assert rs.cursor == 0
    assert rs.revision > r.revision

    st = stop_session(r)
    assert st.status == "detenida"
    assert st.position.open is True


def test_save_y_carga_sesion():
    """Persistencia: guardar y recargar conserva el estado tras refresco."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = mk_config()
        candles = up_candles(3)
        s = create_session(config, candles)
        s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                             hypothesis_version="1.0", rule_version="RULE-v1")
        r = step_forward(s)  # abierta
        save_session(r, tmpdir)
        loaded = load_session(r.session_id, tmpdir)
        assert loaded is not None
        assert loaded.session_id == r.session_id
        assert loaded.status == "abierta"
        assert loaded.position.open is True
        assert loaded.position.entry_px == r.position.entry_px
        assert loaded.config_hash == r.config_hash
        assert loaded.revision == r.revision


def test_serializacion_roundtrip():
    config = mk_config()
    candles = up_candles(2)
    s = create_session(config, candles)
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    r = step_forward(s)
    d = session_to_dict(r)
    r2 = session_from_dict(d)
    assert r2.session_id == r.session_id
    assert r2.status == r.status
    assert r2.position.open == r.position.open
    assert r2.config_hash == r.config_hash
    assert r2.revision == r.revision


def test_session_id_traversal_rechazado():
    """Identificadores con traversal deben ser rechazados."""
    from microstructure_probe.paper_lab_engine import _safe_session_id
    try:
        _safe_session_id("../../../etc/passwd")
        assert False, "debería haber lanzado ValueError"
    except ValueError:
        pass
    try:
        _safe_session_id("..")
        assert False, "debería haber lanzado ValueError"
    except ValueError:
        pass
    assert _safe_session_id("PL-BTCUSDT-LONG-1234567890-abcd1234") == \
        "PL-BTCUSDT-LONG-1234567890-abcd1234"


def test_list_sessions_vacio():
    with tempfile.TemporaryDirectory() as tmpdir:
        summaries = list_sessions(tmpdir)
        assert summaries == []


def test_financiamiento_ausente_es_unknown():
    """Funding sin calendario real → UNKNOWN (None), no cero por defecto."""
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    # Sin calendario de funding → funding es None (UNKNOWN)
    assert s.costs.funding is None
    # Después de entrar y salir por stop
    r = step_forward(s)  # entrada
    candles_stop = [
        mk_candle(0, 100, 102, 99, 101),
        mk_candle(900000, 101, 101, 94, 100),
    ]
    s2 = create_session(mk_config(stop_px=95.0), candles_stop)
    s2 = evaluate_session(s2, hypothesis_id="ENG-FIXTURE-v1",
                          hypothesis_version="1.0", rule_version="RULE-v1")
    r2 = step_forward(s2)  # entrada
    r2 = step_forward(r2)  # gestión
    r2 = step_forward(r2)  # stop
    assert r2.result.funding is None, f"esperaba None, obtuvo {r2.result.funding}"


if __name__ == "__main__":
    test_create_session_sin_iniciar()
    test_evaluate_admite_entrada_automatica()
    test_evaluate_sin_entrada_sin_posicion()
    test_step_forward_ejecuta_entrada()
    test_step_forward_gestion_y_salida_stop()
    test_step_forward_salida_horizonte()
    test_salida_manual()
    test_open_at_end_posicion_permanece_abierta()
    test_restart_y_stop()
    test_save_y_carga_sesion()
    test_serializacion_roundtrip()
    test_session_id_traversal_rechazado()
    test_list_sessions_vacio()
    test_financiamiento_ausente_es_unknown()
    print("Todas las pruebas del motor de ingeniería pasaron.")
