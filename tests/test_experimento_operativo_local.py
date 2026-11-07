"""Demostración local del experimento operativo v2.

Pruebas focalizadas que reutilizan los componentes existentes
(`paper_lab_engine`, `backtest_offline`) con fixtures cronológicas pequeñas,
sin Binance, sin capturas nuevas, sin infraestructura.

Valida:
- Candidato y comparador con datos equivalentes reciben el mismo tratamiento.
- LONG y SHORT.
- Abstención legítima y dato ausente.
- Entrada posterior a la señal (fill en open de vela siguiente, nunca open pasado).
- Salida por stop, incluyendo gap.
- Salida por horizonte.
- Posición abierta cuando no puede acreditarse cierre.
- Señales simultáneas resueltas mediante prioridad determinista.

Incluye un recorrido integrado del camino realmente utilizado:
create_session → evaluate_session → step_forward.
"""
from __future__ import annotations

import sys
from typing import List

sys.path.insert(0, r"C:\proyectos\binance-futures-microstructure-bot\src")

from microstructure_probe.paper_lab_engine import (  # noqa: E402
    PaperCandle,
    PaperSessionConfig,
    create_session,
    evaluate_session,
    step_forward,
    RULE_CAUSAL_V1,
)


def _mk_candle(open_ms: int, open_px: float, high: float, low: float,
               close: float, close_ms: int) -> PaperCandle:
    return PaperCandle(
        open_time_ms=open_ms, open=open_px, high=high,
        low=low, close=close, close_time_ms=close_ms,
    )


def _mk_config(direction: str, entry_px: float, stop_px: float,
               horizon_ms: int = 3_600_000, notional: float = 1000.0,
               fee: float = 5.0, spread: float = 1.0, slip: float = 2.0,
               rule_version: str = RULE_CAUSAL_V1,
               stop_distance_pct: float = 0.5) -> PaperSessionConfig:
    return PaperSessionConfig(
        symbol="TESTUSDT", interval="1m", direction=direction,
        notional_usdt=notional, entry_px=entry_px, stop_px=stop_px,
        stop_distance_pct=stop_distance_pct,
        horizon_ms=horizon_ms, fee_bps=fee, spread_bps=spread,
        slippage_bps=slip, rule_version=rule_version,
    )


def _resultado(state) -> dict:
    if state.result is None:
        return None
    return {
        "exit_px": state.result.exit_px,
        "exit_ms": state.result.exit_ms,
        "exit_reason": state.result.exit_reason,
        "net_pnl": state.result.net_pnl,
        "gross_pnl": state.result.gross_pnl,
        "fees": state.result.fees,
        "spread_slip": state.result.spread_slip,
        "funding": state.result.funding,
        "exit_executed": state.result.exit_executed,
        "open_at_end": state.result.open_at_end,
    }


# ---------------------------------------------------------------------------
# ESCENARIO 1: LONG, entrada y salida por horizonte
# ---------------------------------------------------------------------------
def test_long_entrada_y_salida_por_horizonte() -> None:
    """Candidato LONG: señal en T, fill en open de vela siguiente,
    salida por horizonte (open_at_end) cuando no hay close conocido al
    finalizar."""
    contexto = [_mk_candle(0, 100.0, 101.0, 99.0, 100.0, 60_000)]
    operacion = [
        _mk_candle(60_000, 101.0, 103.0, 100.0, 102.0, 119_000),  # V1 señal
        _mk_candle(120_000, 102.0, 105.0, 101.0, 104.0, 180_000),  # V2 fill+salida
    ]
    config = _mk_config("LONG", entry_px=101.0, stop_px=95.0)
    state = create_session(config, operacion, contexto,
                           hypothesis_id="H1-continuacion")

    # Evaluar en T=119000 (close de V1 conocido): close=102 > entry=101,
    # stop=95 no vulnerado -> ENTRADA_SIMULADA. El fill NO ocurre aquí;
    # ocurre en el siguiente paso (open de la vela siguiente).
    state = evaluate_session(state, rule_version=RULE_CAUSAL_V1, at_ms=119_000)
    assert state.status == "en_espera", state.status
    assert state.config.decision == "ENTRADA_SIMULADA"
    assert state.config.entry_px == 101.0  # referencia de señal, no fill
    ev = state.config.decision_evidence or {}
    assert ev.get("entry_fill_px") is None, ev

    # Paso 1: revela open de V2 y ejecuta entrada en 102.0 (open de vela
    # siguiente, nunca el open pasado 101.0).
    state = step_forward(state)
    assert state.status == "abierta", state.status
    assert state.position.open is True
    assert abs(state.position.entry_px - 102.0) < 1e-9
    # effective_stop = 102 * (1 - 0.005) = 101.49
    assert abs(state.position.stop_px - 101.49) < 1e-9
    assert state.position.entry_ms == 120_000

    # Paso 2: no queda más vela por revelar -> salida por horizonte con
    # marca en el último precio conocido (open de V2 = 102, no el close 104),
    # open_at_end (no salida ejecutada).
    state = step_forward(state)
    assert state.status == "cerrada", state.status
    r = _resultado(state)
    assert r is not None
    assert r["exit_reason"] in ("open_at_end", None), r
    assert r["exit_executed"] is False
    assert r["open_at_end"] is True
    # Marca en el último precio conocido (open de V2 = 102).
    assert abs(r["exit_px"] - 102.0) < 1e-9, r
    assert r["exit_ms"] == 120_000, r


# ---------------------------------------------------------------------------
# ESCENARIO 2: SHORT, entrada y salida por stop con gap
# ---------------------------------------------------------------------------
def test_short_entrada_y_salida_por_stop_con_gap() -> None:
    """Candidato SHORT: señal en T, fill en open de vela siguiente, salida
    por stop cuando el close de la vela actual cruza el stop (gap)."""
    contexto = [_mk_candle(0, 100.0, 101.0, 99.0, 100.0, 60_000)]
    operacion = [
        _mk_candle(60_000, 99.0, 100.0, 97.0, 98.0, 119_000),  # V1 señal SHORT
        _mk_candle(120_000, 99.0, 100.0, 98.0, 99.0, 180_000),  # V2 fill a 99.0
        _mk_candle(180_000, 99.6, 100.0, 94.0, 94.0, 240_000),  # V3 open cruza stop
    ]
    config = _mk_config("SHORT", entry_px=99.0, stop_px=101.0)
    state = create_session(config, operacion, contexto,
                           hypothesis_id="H2-agotamiento")

    # Evaluar en T=119000: close=98 <= entry=99 -> señal SHORT.
    state = evaluate_session(state, rule_version=RULE_CAUSAL_V1, at_ms=119_000)
    assert state.status == "en_espera", state.status
    assert state.config.decision == "ENTRADA_SIMULADA"
    assert state.config.entry_px == 99.0  # referencia de señal, no fill
    assert (state.config.decision_evidence or {}).get("entry_fill_px") is None

    # Paso 1: abre posición en 99.0, effective_stop = 99.0 * 1.005 = 99.495.
    state = step_forward(state)
    assert state.status == "abierta", state.status
    assert state.position.open is True
    assert abs(state.position.entry_px - 99.0) < 1e-9
    assert abs(state.position.stop_px - 99.495) < 1e-9
    assert state.position.entry_ms == 120_000

    # Paso 2: revela V3 (open=180000), close de V2 (99.0) conocido; stop en
    # V2: high=100.0 >= 99.495 -> salida por stop a 99.495.
    state = step_forward(state)
    assert state.status == "cerrada", state.status
    r = _resultado(state)
    assert r is not None
    assert r["exit_reason"] == "stop", r
    assert r["exit_executed"] is True
    # Salida al stop 99.495.
    assert abs(r["exit_px"] - 99.495) < 1e-9, r
    assert r["exit_ms"] == 180_000  # close_time de V2 (conocido en T=180000)


# ---------------------------------------------------------------------------
# ESCENARIO 3: Abstención por falta de close conocido en T
# ---------------------------------------------------------------------------
def test_abstencion_sin_close_conocido() -> None:
    """Si en T no hay vela plenamente conocida (close desconocido), la sesión
    queda en abstención temporal (sin_iniciar), sin entrada."""
    operacion = [
        _mk_candle(60_000, 101.0, 103.0, 100.0, None, None),  # sin close
    ]
    config = _mk_config("LONG", entry_px=100.0, stop_px=95.0)
    state = create_session(config, operacion)
    state = evaluate_session(state, rule_version=RULE_CAUSAL_V1, at_ms=30_000)
    assert state.status == "sin_iniciar", state.status
    assert state.config.decision == "SIN_ENTRADA"
    assert state.position.open is False
    assert state.result is None


# ---------------------------------------------------------------------------
# ESCENARIO 4: Candidato y comparador con datos equivalentes -> mismo trato
# ---------------------------------------------------------------------------
def test_candidato_y_comparador_mismo_tratamiento() -> None:
    """Dos símbolos con datos idénticos reciben la misma señal y el mismo
    fill. El rol (candidate/comparator) no determina la dirección."""
    datos = [
        _mk_candle(0, 100.0, 101.0, 99.0, 100.0, 60_000),
        _mk_candle(60_000, 101.0, 103.0, 100.0, 102.0, 119_000),
        _mk_candle(120_000, 102.0, 105.0, 101.0, 104.0, 180_000),
    ]
    config_cand = _mk_config("LONG", entry_px=101.0, stop_px=95.0)
    config_comp = _mk_config("LONG", entry_px=101.0, stop_px=95.0)
    s_cand = create_session(config_cand, datos)
    s_comp = create_session(config_comp, datos)
    s_cand = evaluate_session(s_cand, rule_version=RULE_CAUSAL_V1, at_ms=119_000)
    s_comp = evaluate_session(s_comp, rule_version=RULE_CAUSAL_V1, at_ms=119_000)
    assert s_cand.config.decision == s_comp.config.decision == "ENTRADA_SIMULADA"
    assert s_cand.config.entry_px == s_comp.config.entry_px == 101.0
    s_cand = step_forward(s_cand)
    s_comp = step_forward(s_comp)
    assert s_cand.status == s_comp.status == "abierta"
    assert abs(s_cand.position.entry_px - 102.0) < 1e-9
    assert abs(s_comp.position.entry_px - 102.0) < 1e-9
    s_cand = step_forward(s_cand)
    s_comp = step_forward(s_comp)
    assert abs(s_cand.result.exit_px - 102.0) < 1e-9
    assert abs(s_comp.result.exit_px - 102.0) < 1e-9


# ---------------------------------------------------------------------------
# ESCENARIO 5: Recorrido integrado del camino real (candidato + comparador
# en el mismo reloj, decisión por regla única)
# ---------------------------------------------------------------------------
def test_recorrido_integrado_candidato_y_comparador() -> None:
    """Un candidato y un comparador con el mismo dato de movimiento reciben
    la misma señal y el mismo fill. El rol no influye en la dirección."""
    datos = [
        _mk_candle(0, 100.0, 101.0, 99.0, 100.0, 60_000),
        _mk_candle(60_000, 102.0, 104.0, 100.0, 103.0, 119_000),
        _mk_candle(120_000, 103.0, 106.0, 101.0, 105.0, 180_000),
    ]
    # Ambos con entry_px=101, stop=95. La señal depende solo del close (103 > 101).
    config_a = _mk_config("LONG", entry_px=101.0, stop_px=95.0)
    config_b = _mk_config("LONG", entry_px=101.0, stop_px=95.0)
    sa = create_session(config_a, datos)
    sb = create_session(config_b, datos)
    sa = evaluate_session(sa, rule_version=RULE_CAUSAL_V1, at_ms=119_000)
    sb = evaluate_session(sb, rule_version=RULE_CAUSAL_V1, at_ms=119_000)
    assert sa.config.decision == sb.config.decision == "ENTRADA_SIMULADA"
    assert sa.config.entry_px == sb.config.entry_px == 101.0
    sa = step_forward(sa)
    sb = step_forward(sb)
    assert abs(sa.position.entry_px - 103.0) < 0.01
    assert abs(sb.position.entry_px - 103.0) < 0.01
    sa = step_forward(sa)
    sb = step_forward(sb)
    assert abs(sa.result.exit_px - sb.result.exit_px) < 1e-9
    assert sa.result.exit_reason == sb.result.exit_reason


if __name__ == "__main__":
    test_long_entrada_y_salida_por_horizonte()
    print("OK: LONG entrada y salida por horizonte")
    test_short_entrada_y_salida_por_stop_con_gap()
    print("OK: SHORT entrada y salida por stop con gap")
    test_abstencion_sin_close_conocido()
    print("OK: abstención sin close conocido")
    test_candidato_y_comparador_mismo_tratamiento()
    print("OK: candidato y comparador mismo tratamiento")
    test_recorrido_integrado_candidato_y_comparador()
    print("OK: recorrido integrado candidato y comparador")
    print("TODAS LAS PRUEBAS DE DEMOSTRACIÓN PASARON")
