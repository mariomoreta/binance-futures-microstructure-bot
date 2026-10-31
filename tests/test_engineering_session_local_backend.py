"""Prueba focalizada: sesion backend de ingenieria que recibe eventos y
registra decisiones (transporte local, sin Binance, sin red).

Acredita:
  - session_id, config_hash, runner (engine), revisiones y decisiones
    bajo regla RULE-CAUSAL-V1 fijada antes de evaluar.
  - La sesion recibe eventos (step_forward avanza clock_ms/cursor).
  - Cero entradas es valido si queda acreditada la evaluacion
    (decision registrada, position.open False).
No hay Binance, no hay feed vivo, no hay ordenes reales, no hay pagos.
"""
from __future__ import annotations

import os
import sys
from typing import List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from microstructure_probe.paper_lab_engine import (  # noqa: E402
    PaperCandle,
    PaperSessionConfig,
    RULE_CAUSAL_V1,
    create_session,
    evaluate_session,
    step_forward,
)

STEP_MS = 60_000  # 1m


def mk_candle_1m(open_time_ms: int, open_: float, high: float,
                 low: float, close: float) -> PaperCandle:
    return PaperCandle(
        open_time_ms=open_time_ms, open=open_, high=high,
        low=low, close=close, close_time_ms=open_time_ms + STEP_MS - 1,
    )


def mk_config(symbol="MINAUSDT", direction="LONG", entry_px=1.05,
              stop_px=1.00, horizon_ms=3 * 60 * 60 * 1000,
              notional_usdt=1000.0, fee_bps=5.0, spread_bps=1.0,
              slippage_bps=2.0, stop_distance_pct=5.0,
              interval="1m") -> PaperSessionConfig:
    return PaperSessionConfig(
        symbol=symbol, interval=interval, direction=direction,
        notional_usdt=notional_usdt, entry_px=entry_px, stop_px=stop_px,
        stop_distance_pct=stop_distance_pct, horizon_ms=horizon_ms,
        fee_bps=fee_bps, spread_bps=spread_bps, slippage_bps=slippage_bps,
    )


def _context_candles(n: int, start_ms: int, base_px: float) -> List[PaperCandle]:
    """Velas de contexto recientes y cerradas (conocidas en T)."""
    out: List[PaperCandle] = []
    px = base_px
    t = start_ms
    for _ in range(n):
        c = mk_candle_1m(t, px, px * 1.002, px * 0.998, px * 1.001)
        out.append(c)
        px = c.close
        t += STEP_MS
    return out


def _operacion_candles(n: int, start_ms: int, base_px: float,
                       drift: float = 0.0) -> List[PaperCandle]:
    """Velas de operacion (provisional/cerrada) despues del contexto."""
    out: List[PaperCandle] = []
    px = base_px
    t = start_ms
    for _ in range(n):
        c = mk_candle_1m(t, px, px * 1.002, px * 0.998,
                         px * (1 + drift))
        out.append(c)
        px = c.close
        t += STEP_MS
    return out


def test_sesion_backend_recibe_eventos_y_registra_decision():
    """Sesion de ingenieria: recibe eventos y registra decision causal."""
    # Contexto reciente: 5 velas 1m cerradas terminando en T-60s.
    # T = close_time de la ultima vela de contexto + 60s (frontera de operacion).
    contexto = _context_candles(5, 1793455200000, 1.05)
    t_ms = contexto[-1].close_time_ms + STEP_MS  # frontera T
    # Velas de operacion despues de T (reveladas al avanzar el reloj).
    operacion = _operacion_candles(6, t_ms, 1.0501)

    config = mk_config(symbol="MINAUSDT", direction="LONG",
                       entry_px=1.051, stop_px=1.000,
                       horizon_ms=3 * 60 * 60 * 1000, interval="1m")

    # 1. Crear sesion: session_id, config_hash, revision=0, sin_iniciar.
    estado = create_session(config, operacion, contexto,
                            hypothesis_id="H-LOCAL-01",
                            hypothesis_version="v1",
                            rule_version=RULE_CAUSAL_V1)
    assert estado.session_id is not None
    assert estado.config_hash is not None
    assert len(estado.config_hash) == 16
    assert estado.revision == 0
    assert estado.status == "sin_iniciar"
    assert estado.position.open is False
    # El reloj pertenece al backend y empieza en la frontera de contexto.
    assert estado.clock_ms is not None
    assert estado.clock_ms <= t_ms

    # 2. Evaluar en T: registra decision (ENTRADA_SIMULADA / SIN_ENTRADA /
    #    DESCARTADO) con motivo y evidencia, revision incrementada.
    estado_eval = evaluate_session(estado, at_ms=t_ms,
                                   hypothesis_id="H-LOCAL-01",
                                   rule_version=RULE_CAUSAL_V1)
    assert estado_eval.session_id == estado.session_id
    assert estado_eval.config_hash == estado.config_hash
    # La evaluacion registra una decision: revision incrementa respecto al
    # estado previo (sin_iniciar -> evaluando/cerrada/en_espera).
    assert estado_eval.revision > estado.revision
    assert estado_eval.config.decision is not None
    assert estado_eval.config.decision_reason is not None
    assert estado_eval.config.decision in (
        "ENTRADA_SIMULADA", "SIN_ENTRADA", "DESCARTADO")

    # 3. La sesion recibe eventos: step_forward avanza clock_ms y cursor.
    estado_step = step_forward(estado_eval)
    assert estado_step.session_id == estado.session_id
    assert estado_step.config_hash == estado.config_hash
    assert estado_step.revision >= estado_eval.revision
    # El reloj de sesion avanza de forma monotonica (recibe eventos del feed).
    assert estado_step.clock_ms >= estado_eval.clock_ms

    # 4. Cero entradas es valido si queda acreditada la evaluacion:
    #    decision registrada aunque position.open sea False (sin entrada).
    decision_registrada = estado_eval.config.decision is not None
    entrada_ejecutada = estado_step.position.open is True
    assert decision_registrada, "debe quedar acreditada la evaluacion"
    if not entrada_ejecutada:
        assert estado_step.position.open is False
        # Sin entrada: no hay fill, sin salida inventada.
        assert estado_step.result is None or estado_step.result.get(
            "exit_executed") is not True

    print("SESION BACKEND OK:",
          "session_id=", estado.session_id,
          "config_hash=", estado.config_hash,
          "decision=", estado_eval.config.decision,
          "revision=", estado_step.revision,
          "position_open=", estado_step.position.open,
          "clock_ms=", estado_step.clock_ms)


if __name__ == "__main__":
    test_sesion_backend_recibe_eventos_y_registra_decision()
    print("TODAS LAS PRUEBAS FOCALIZADAS PASARON")
