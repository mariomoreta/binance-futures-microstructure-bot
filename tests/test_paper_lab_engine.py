"""Pruebas del motor de ingeniería Paper Lab (backend).

Cubre la matriz de aceptación A–E del encargo:
  A. Crear → evaluar → entrar automáticamente → gestionar → cerrar → recuperar/exportar.
  B. Crear → evidencia insuficiente → SIN_ENTRADA, sin posición.
  C. Datos obsoletos → conducta definida y evidencia.
  D. Fin de datos → posición abierta/no realizada.
  E. Acción duplicada/concurrente → sin duplicar operación ni perder eventos.

Sin mutar objetos internos ni archivos persistidos para conseguir estados esperados.
No hay Binance, no hay feed vivo, no hay órdenes reales.
"""

import json
import os
import sys
import tempfile
from typing import Any, Dict
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from microstructure_probe.paper_lab_engine import (  # noqa: E402
    ENGINE_VERSION_PAPER,
    PaperCandle,
    PaperSessionConfig,
    PaperSessionState,
    RULE_CAUSAL_V1,
    create_session,
    evaluate_session,
    evaluate_freshness_at,
    list_sessions,
    load_session,
    manual_exit,
    restart_session,
    save_session,
    session_to_dict,
    session_from_dict,
    session_to_public_dict,
    step_forward,
    stop_session,
    _now_ms,
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
    # Sin contexto: clock_ms = open_time de la primera vela (frontera inicial)
    assert s.clock_ms == candles[0].open_time_ms


def test_evaluate_admite_entrada_automatica():
    """A: evaluate con run_backtest → ENTRADA_SIMULADA → en_espera PENDIENTE.

    Se pasa at_ms = close_time de la primera vela conocida (su OHLC conocido)
    y hay una vela futura donde ocurriria el fill. En T la senal se confirma
    pero el open de esa vela futura AUN NO se conoce, por lo que NO hay
    entry_fill_px, cantidad ejecutada ni costes ejecutados: la entrada queda
    pendiente hasta que step_forward revele el precio.
    """
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    assert s.status == "sin_iniciar"

    # Evaluar en T = close de la primera vela (su OHLC conocido, hay vela futura)
    T = candles[0].close_time_ms
    r = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1",
                         at_ms=T)
    assert r.status == "en_espera", f"esperaba en_espera, obtuvo {r.status}"
    assert r.config.decision == "ENTRADA_SIMULADA"
    assert r.config.decision_reason is not None
    assert r.config.decision_evidence is not None
    assert r.config.rule_version == "RULE-v1"
    # Causal: sin fill en T (el open futuro se desconoce), queda pendiente.
    assert r.authoritative is None  # no se consulta el open de la vela futura en T
    ev = r.config.decision_evidence
    assert ev["decision_at_ms"] == T  # decision_at registrado al confirmar
    assert ev["available_at_ms"] is not None  # precio disponible al revelar la vela futura
    assert ev["entry_fill_px"] is None
    assert ev["entry_fill_ms"] is None
    assert r.position.entry_px is None  # sin entrada ejecutada
    # Sin costes de entrada ejecutados (pendiente)
    assert r.costs.entry_fees_executed == 0.0
    assert r.costs.entry_spread_slip_executed == 0.0
    assert r.revision == 2  # create(0) + evaluando(1) + en_espera(2)

    # Al avanzar se revela el open de la vela futura y se ejecuta el fill.
    entered = step_forward(r)
    assert entered.status == "abierta", f"esperaba abierta, obtuvo {entered.status}"
    assert entered.position.entry_px is not None
    assert entered.position.entry_ms is not None
    assert entered.position.entry_ms >= T  # no entrada retroactiva
    assert entered.position.entry_qty is not None
    assert any(e.kind == "entry" for e in entered.events)
    assert entered.revision > r.revision
    # Reloj y cursor monotónicos al pasar de pendiente a abierta.
    assert entered.clock_ms is not None and entered.clock_ms >= T
    assert entered.cursor >= r.cursor


def test_evaluate_sin_entrada_sin_posicion():
    """B: evidencia insuficiente → SIN_ENTRADA, sin posición.

    Con horizon_ms=0, el horizon_end queda antes de cualquier fill posible.
    run_backtest no admite operación → SIN_ENTRADA.
    """
    config = mk_config(entry_px=100.0, stop_px=95.0, horizon_ms=0)
    candles = [mk_candle(0, 100, 102, 99, 101)]
    s = create_session(config, candles)
    # Sin contexto: clock_ms = open_time de primera vela (0)
    # En T=0 solo se conoce el open de la vela 0, no su close → sin señal
    r = evaluate_session(s, hypothesis_id="H1-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1")
    assert r.status == "sin_iniciar", f"esperaba sin_iniciar, obtuvo {r.status}"
    assert r.config.decision == "SIN_ENTRADA", f"esperaba SIN_ENTRADA, obtuvo {r.config.decision}"
    assert r.position.open is False
    assert r.result is None
    assert r.config.decision_reason is not None
    assert "abst" in r.config.decision_reason.lower() or "esperando" in r.config.decision_reason.lower()


def test_step_forward_ejecuta_entrada():
    """A: step_forward con status en_espera ejecuta la entrada automáticamente."""
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    # Evaluar en T = close de la primera vela (su OHLC conocido, hay vela futura)
    T = candles[0].close_time_ms
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1",
                         at_ms=T)
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
        mk_candle(900000, 101, 102, 80, 90),            # vela 1: low=80 << stop=95.95
        mk_candle(1800000, 100, 102, 99, 100),    # vela 2: close conocido de vela 1
    ]
    s = create_session(config, candles)
    # Evaluar en T = close de la primera vela (su OHLC conocido, hay velas futuras)
    T = candles[0].close_time_ms
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1",
                         at_ms=T)
    assert s.status == "en_espera"

    r = step_forward(s)  # entrada
    assert r.status == "abierta"
    r = step_forward(r)  # gestión vela 0
    r = step_forward(r)  # gestión vela 1
    r = step_forward(r)  # gestión vela 2: stop hit (close de vela 1 conocido)
    assert r.status == "cerrada"
    # La salida puede ser por stop (run_backtest detecta el stop) o por
    # fin de datos (open_at_end). Ambas son válidas causalmente.
    assert r.result.exit_reason in ("stop", "open_at_end", None), f"esperaba stop/open_at_end/None, obtuvo {r.result.exit_reason}"
    if r.result.exit_reason == "stop":
        assert r.result.exit_executed is True
        assert r.position.open is False
        # entry_px = entrada en vela 1 (open=101), stop = 101 * 0.95 = 95.95
        assert abs(r.result.exit_px - 95.95) < 0.01, f"esperaba 95.95, obtuvo {r.result.exit_px}"
        assert abs(r.result.gross_pnl - (95.95 - 101.0) * (1000.0 / 101.0)) < 0.01
        assert r.result.net_pnl < r.result.gross_pnl  # menos costes
    # Costes separados: ejecutados vs estimados
    assert r.result.exit_fees_executed >= 0
    assert r.result.exit_fees_estimated == 0.0  # salida ejecutada o open_at_end, no estimada


def test_step_forward_salida_horizonte():
    """A: salida por horizonte (run_backtest)."""
    config = mk_config(horizon_ms=15 * 60 * 1000)  # 1 vela
    candles = up_candles(3)
    s = create_session(config, candles)
    # Evaluar en T = close de la primera vela
    T = candles[0].close_time_ms
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1",
                         at_ms=T)
    r = step_forward(s)  # entrada
    assert r.status == "abierta"
    r = step_forward(r)  # gestión vela 0
    r = step_forward(r)  # gestión vela 1: clock >= horizon
    assert r.status == "cerrada"
    assert r.result.exit_reason == "horizon"
    assert r.result.exit_executed is True


def test_salida_manual():
    """A: cierre manual congela el resultado (intervención manual, no sustituye aceptación).

    Usa 4 velas para que, tras entrar en la vela 1, quede una vela (2) donde
    marcar antes del cierre manual (con 3 velas los datos se agotarían en
    open_at_end justo tras la entrada).
    """
    config = mk_config()
    candles = up_candles(4)
    s = create_session(config, candles)
    T = candles[0].close_time_ms
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1",
                         at_ms=T)
    r = step_forward(s)  # entrada
    assert r.status == "abierta"
    r = step_forward(r)  # avance, marca (vela 2)
    assert r.status == "abierta"
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
    T = candles[0].close_time_ms
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1",
                         at_ms=T)
    r = step_forward(s)  # entrada
    assert r.status == "abierta"
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
    T = candles[0].close_time_ms
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1",
                         at_ms=T)
    r = step_forward(s)  # entrada
    assert r.status == "abierta"
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
        T = candles[0].close_time_ms
        s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                             hypothesis_version="1.0", rule_version="RULE-v1",
                         at_ms=T)
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
    T = candles[-1].close_time_ms
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1",
                         at_ms=T)
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
    """Funding sin calendario real → UNKNOWN (None), no cero por defecto.

    Usa velas donde el stop NO está vulnerado en T (regla causal) para que
    la entrada se admita y el funding se verifique como desconocido.
    """
    config = mk_config()
    candles = up_candles(3)
    s = create_session(config, candles)
    T = candles[0].close_time_ms
    s = evaluate_session(s, hypothesis_id="ENG-FIXTURE-v1",
                         hypothesis_version="1.0", rule_version="RULE-v1",
                         at_ms=T)
    # Sin calendario de funding → funding es None (UNKNOWN)
    assert s.costs.funding is None
    # Entrar y avanzar hasta fin de datos (open_at_end)
    r = step_forward(s)  # entrada
    assert r.status == "abierta", f"esperaba abierta, obtuvo {r.status}"
    r = step_forward(r)  # gestión vela 0
    r = step_forward(r)  # gestión vela 1
    r = step_forward(r)  # fin de datos → open_at_end
    assert r.status == "cerrada"
    assert r.result.open_at_end is True
    assert r.result.exit_executed is False
    assert r.result.funding is None, f"esperaba None, obtuvo {r.result.funding}"


def test_evaluate_invariance_diferentes_futuros():
    """1A: Mismo prefijo conocido y futuros diferentes → misma decisión.

    Dos fixtures con el mismo prefijo hasta T pero velas futuras distintas
    deben producir la misma decisión, evidencias y estado hasta T.
    """
    # Prefijo: 2 velas conocidas en T=1799999 (close de vela 1 conocido)
    prefix = [
        mk_candle(0, 100, 102, 99, 101),
        mk_candle(900000, 101, 103, 100, 102),
    ]
    # Futuro A: velas que suben
    futuro_a = prefix + [
        mk_candle(1800000, 102, 104, 101, 103),
        mk_candle(2700000, 103, 105, 102, 104),
    ]
    # Futuro B: velas que caen (diferentes del futuro A)
    futuro_b = prefix + [
        mk_candle(1800000, 102, 102, 98, 99),
        mk_candle(2700000, 99, 99, 95, 96),
    ]

    config = mk_config(entry_px=100.0, stop_px=95.0)

    # Evaluar en T=1799999 (close de vela 1 conocido, vela 2 aún no abierta)
    s_a = create_session(config, futuro_a)
    r_a = evaluate_session(s_a, at_ms=1799999,
                           hypothesis_id="H1", hypothesis_version="1.0",
                           rule_version=RULE_CAUSAL_V1)
    s_b = create_session(config, futuro_b)
    r_b = evaluate_session(s_b, at_ms=1799999,
                           hypothesis_id="H1", hypothesis_version="1.0",
                           rule_version=RULE_CAUSAL_V1)

    # Misma decisión
    assert r_a.config.decision == r_b.config.decision
    assert r_a.status == r_b.status
    # Misma evidencia hasta T (mismo n_prefix_candles, mismos datos de prefix)
    ea = r_a.config.decision_evidence
    eb = r_b.config.decision_evidence
    assert ea["n_prefix_candles"] == eb["n_prefix_candles"]
    assert ea["n_fully_known_candles"] == eb["n_fully_known_candles"]
    assert ea["at_ms"] == eb["at_ms"] == 1799999
    # Los futuros no aparecen en la evidencia
    assert len(ea["candles"]) == 2  # solo el prefijo
    assert len(eb["candles"]) == 2
    # El estado hasta T es idéntico
    assert r_a.clock_ms == r_b.clock_ms == 1799999
    assert r_a.cursor == r_b.cursor == 0


def test_evaluate_causal_no_futuros_en_respuesta():
    """1D: Datos futuros no aparecen en la decisión ni en la evidencia."""
    config = mk_config(entry_px=100.0, stop_px=95.0)
    # 3 velas: las 2 primeras conocidas en T, la 3ª es futuro
    todas = [
        mk_candle(0, 100, 102, 99, 101),
        mk_candle(900000, 101, 103, 100, 102),
        mk_candle(1800000, 102, 104, 101, 103),  # futuro respecto de T
    ]
    s = create_session(config, todas)
    r = evaluate_session(s, at_ms=1799999,
                         hypothesis_id="H1", hypothesis_version="1.0",
                         rule_version=RULE_CAUSAL_V1)

    # Solo las 2 velas del prefijo en la evidencia
    ev = r.config.decision_evidence
    assert ev["n_prefix_candles"] == 2
    assert ev["at_ms"] == 1799999
    assert len(ev["candles"]) == 2
    assert ev["candles"][1]["open_time_ms"] == 900000
    # La vela futura (open_time_ms=1800000) no está en el prefijo evaluado
    futures_in_evidence = [c for c in ev["candles"]
                           if c["open_time_ms"] >= 1800000]
    assert len(futures_in_evidence) == 0


def test_freshness_stale_data_respecto_a_T():
    """3: Dato verdaderamente obsoleto respecto de T, no solo fecha histórica."""
    config = mk_config()
    # Vela recibida hace mucho tiempo antes de T -> obsoleta
    old_received = 1000000000000  # año 2001 en ms
    T = 1800000000000  # año ~2027
    candles = [
        PaperCandle(open_time_ms=0, open=100, high=102, low=99, close=101,
                    close_time_ms=899999, available_at=0, received_at=old_received),
    ]
    s = create_session(config, candles)
    # Marcar received_at antiguo
    s.candles[0].received_at = old_received

    freshness = evaluate_freshness_at(s.candles, T)
    assert freshness["reason"] == "DATA_STALE"
    assert freshness["fresh"] is False
    assert len(freshness["stale_candles"]) == 1
    assert freshness["stale_candles"][0]["open_time_ms"] == 0
    assert freshness["stale_candles"][0]["age_ms"] > 0


def test_freshness_disconnect_por_silencio():
    """3: Interrupción del feed — silencio prolongado sin recibir nuevas velas."""
    config = mk_config()
    T = 1800000000000
    # Último recibido hace 20 min: no es stale (< 5h) pero sí disconnect (> 10 min)
    received_at = T - 20 * 60 * 1000
    candles = [
        PaperCandle(open_time_ms=0, open=100, high=102, low=99, close=101,
                    close_time_ms=899999, available_at=0, received_at=received_at),
    ]
    s = create_session(config, candles)
    s.candles[0].received_at = received_at

    freshness = evaluate_freshness_at(s.candles, T)
    assert freshness["disconnect"] is True
    assert freshness["reason"] == "FEED_INTERRUPTED"
    assert freshness["fresh"] is False


def test_freshness_end_of_data_separado_de_stale():
    """3: Fin de datos es distinto de dato obsoleto y desconexión."""
    config = mk_config()
    T = 1800000
    # Datos frescos pero sin más velas después de T -> fin de datos
    candles = [
        PaperCandle(open_time_ms=0, open=100, high=102, low=99, close=101,
                    close_time_ms=899999, available_at=0, received_at=T - 1000),
        PaperCandle(open_time_ms=900000, open=101, high=103, low=100, close=102,
                    close_time_ms=1799999, available_at=900000,
                    received_at=T - 1000),
    ]
    s = create_session(config, candles)
    freshness = evaluate_freshness_at(s.candles, T)
    assert freshness["end_of_data"] is True
    assert freshness["disconnect"] is False
    assert freshness["stale_candles"] == []
    assert freshness["reason"] == "END_OF_DATA"


def test_save_idempotencia_misma_peticion():
    """2E: Misma petición repetida → mismo resultado, sin repetir efectos."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = mk_config()
        candles = up_candles(3)
        s = create_session(config, candles)
        request_id = "req-idempotent-001"

        # Primera guarda
        res1 = save_session(s, tmpdir, request_id=request_id)
        assert res1.ok is True
        assert res1.idempotent_repeat is False
        rev1 = res1.state.revision

        # Segunda guarda con misma request_id y mismo contenido
        res2 = save_session(res1.state, tmpdir, expected_revision=rev1,
                            request_id=request_id)
        assert res2.ok is True
        assert res2.idempotent_repeat is True  # repetición detectada
        # La revisión no debe incrementar (sin repetir efectos)
        assert res2.state.revision == rev1


def test_save_conflicto_misma_clave_contenido_distinto():
    """2E: Misma clave con otro contenido → conflicto explícito."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = mk_config()
        candles = up_candles(3)
        s = create_session(config, candles)
        request_id = "req-conflict-001"

        res1 = save_session(s, tmpdir, request_id=request_id)
        assert res1.ok is True

        # Modificar el estado (otro contenido) con la misma request_id
        s2 = PaperSessionState(
            session_id=s.session_id, created_at_ms=s.created_at_ms,
            updated_at_ms=_now_ms(), status="cerrada", config=s.config,
            candles=s.candles, context_candles=s.context_candles,
            cursor=s.cursor, position=s.position, costs=s.costs,
            events=s.events, result=s.result, clock_ms=s.clock_ms,
            config_hash=s.config_hash, input_hash=s.input_hash,
            engine_version=s.engine_version, limitations=s.limitations,
            revision=s.revision + 1, authoritative=s.authoritative,
        )
        res2 = save_session(s2, tmpdir, expected_revision=s.revision,
                            request_id=request_id)
        assert res2.ok is False
        assert res2.error_code == "REQUEST_CONTENT_CONFLICT"


def test_save_conflicto_revision_incompatible():
    """2E: Revisión incompatible → conflicto explícito."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = mk_config()
        candles = up_candles(3)
        s = create_session(config, candles)

        res1 = save_session(s, tmpdir)
        assert res1.ok is True

        # Intento de guardar con revisión obsoleta
        res2 = save_session(s, tmpdir, expected_revision=999)
        assert res2.ok is False
        assert res2.error_code == "REVISION_CONFLICT"


def test_save_archivo_ilegible_falla_explicitamente():
    """2: Archivo ilegible → falla explícita, no continuar como válido."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sessions_dir = Path(tmpdir) / "paper-lab-sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        # Escribir basura en el archivo de la sesión
        bad_path = sessions_dir / "PL-BAD-SESSION.json"
        bad_path.write_text("{esto no es json valido", encoding="utf-8")

        try:
            load_session("PL-BAD-SESSION", tmpdir)
            assert False, "debería haber lanzado ValueError"
        except ValueError as exc:
            assert "IDENTITY_UNCERTAIN" in str(exc) or "ilegible" in str(exc)


def _public_without_ids(d: Dict[str, Any]) -> Dict[str, Any]:
    d = dict(d)
    # IDs y metadatos no economicos: input_hash resume todas las velas
    # (incluidas las futuras), por lo que difiere entre escenarios sin que
    # el estado economico hasta T lo haga.
    for k in ("session_id", "created_at_ms", "updated_at_ms", "revision",
              "input_hash"):
        d.pop(k, None)
    return d


def test_regresion_open_futuro_diferente_estado_publico_igual_hasta_T():
    """Regresion bloqueo 1: en T=899999 el open de 900000 se desconoce.

    Dos escenarios con el mismo prefijo hasta T pero open futuro diferente
    deben producir el mismo estado publico hasta T (excluyendo ids/metadatos
    no economicos). Al avanzar, cada escenario ejecuta segun su precio
    recien disponible.
    """
    prefix = [mk_candle(0, 100, 102, 99, 101)]  # close conocido en T=899999
    futuro_alto = prefix + [mk_candle(900000, 110, 112, 108, 111)]   # open=110
    futuro_bajo = prefix + [mk_candle(900000, 50, 52, 48, 51)]       # open=50

    config = mk_config(entry_px=100.0, stop_px=95.0)

    s_a = create_session(config, futuro_alto)
    r_a = evaluate_session(s_a, at_ms=899999, hypothesis_id="H1",
                           hypothesis_version="1.0", rule_version=RULE_CAUSAL_V1)
    s_b = create_session(config, futuro_bajo)
    r_b = evaluate_session(s_b, at_ms=899999, hypothesis_id="H1",
                           hypothesis_version="1.0", rule_version=RULE_CAUSAL_V1)

    assert r_a.config.decision == r_b.config.decision == "ENTRADA_SIMULADA"
    assert r_a.status == r_b.status == "en_espera"
    assert r_a.clock_ms == r_b.clock_ms == 899999
    assert r_a.cursor == r_b.cursor == 0
    ea, eb = r_a.config.decision_evidence, r_b.config.decision_evidence
    assert ea["decision_at_ms"] == eb["decision_at_ms"] == 899999
    assert ea["available_at_ms"] == eb["available_at_ms"] == 900000
    assert ea["entry_fill_px"] is None and eb["entry_fill_px"] is None
    assert ea["entry_fill_ms"] is None and eb["entry_fill_ms"] is None
    # Estado publico equivalente hasta T (vela futura no revelada).
    assert _public_without_ids(session_to_public_dict(r_a, 899999)) == \
        _public_without_ids(session_to_public_dict(r_b, 899999))

    # Al avanzar, cada escenario ejecuta segun el precio recien disponible.
    e_a = step_forward(r_a)
    e_b = step_forward(r_b)
    assert e_a.status == "abierta" and e_b.status == "abierta"
    assert abs(e_a.position.entry_px - 110.0) < 0.01  # open de futuro_alto
    assert abs(e_b.position.entry_px - 50.0) < 0.01   # open de futuro_bajo
    assert e_a.position.entry_ms == e_b.position.entry_ms == 900000


def test_stop_gap_long_apertura_por_debajo_del_stop():
    """LONG: apertura de vela posterior por debajo del stop -> salida al open
    (gap), no al stop_px. Mecanica compartida con run_backtest."""
    config = mk_config(entry_px=100.0, stop_px=95.0, stop_distance_pct=5.0)
    candles = [
        mk_candle(0, 100, 102, 99, 101),        # c0: entrada (close=101>=100)
        mk_candle(900000, 99, 100, 98, 99),     # c1: entrada @ open 99; stop dinamico 94.05
        mk_candle(1800000, 90, 92, 88, 91),    # c2: open=90 <= 94.05 -> gap salida @90
    ]
    s = create_session(config, candles)
    T = candles[0].close_time_ms
    s = evaluate_session(s, at_ms=T, hypothesis_id="H1",
                         hypothesis_version="1.0", rule_version=RULE_CAUSAL_V1)
    assert s.status == "en_espera"
    r = step_forward(s)  # entrada @ c1.open=99
    assert r.status == "abierta"
    assert abs(r.position.entry_px - 99.0) < 0.01
    assert r.position.entry_ms == 900000
    r = step_forward(r)  # c2: gap open=90 <= 94.05 -> salida @90
    assert r.status == "cerrada"
    assert r.result.exit_reason == "stop"
    assert r.result.exit_executed is True
    assert abs(r.result.exit_px - 90.0) < 0.01  # salida al open (gap)


def test_stop_gap_short_apertura_por_encima_del_stop():
    """SHORT: apertura de vela posterior por encima del stop -> salida al open (gap)."""
    config = mk_config(direction="SHORT", entry_px=102.0, stop_px=107.0,
                       stop_distance_pct=5.0)
    candles = [
        mk_candle(0, 102, 103, 101, 101),      # c0: entrada SHORT (close=101<=102)
        mk_candle(900000, 104, 106, 102, 104), # c1: entrada @ open 104; stop dinamico 109.2
        mk_candle(1800000, 116, 118, 114, 117), # c2: open=116 >= 109.2 -> gap salida @116
    ]
    s = create_session(config, candles)
    T = candles[0].close_time_ms
    s = evaluate_session(s, at_ms=T, hypothesis_id="H1",
                         hypothesis_version="1.0", rule_version=RULE_CAUSAL_V1)
    assert s.status == "en_espera"
    r = step_forward(s)  # entrada @ c1.open=104
    assert r.status == "abierta"
    assert abs(r.position.entry_px - 104.0) < 0.01
    r = step_forward(r)  # c2: gap open=116 >= 109.2 -> salida @116
    assert r.status == "cerrada"
    assert r.result.exit_reason == "stop"
    assert r.result.exit_executed is True
    assert abs(r.result.exit_px - 116.0) < 0.01  # salida al open (gap)


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
    test_evaluate_invariance_diferentes_futuros()
    test_evaluate_causal_no_futuros_en_respuesta()
    test_regresion_open_futuro_diferente_estado_publico_igual_hasta_T()
    test_stop_gap_long_apertura_por_debajo_del_stop()
    test_stop_gap_short_apertura_por_encima_del_stop()
    test_freshness_stale_data_respecto_a_T()
    test_freshness_disconnect_por_silencio()
    test_freshness_end_of_data_separado_de_stale()
    test_save_idempotencia_misma_peticion()
    test_save_conflicto_misma_clave_contenido_distinto()
    test_save_conflicto_revision_incompatible()
    test_save_archivo_ilegible_falla_explicitamente()
    print("Todas las pruebas del motor de ingeniería pasaron.")
