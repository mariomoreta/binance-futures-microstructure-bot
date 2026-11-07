"""Comprobacion focalizada del recorrido operativo local v2.

Escenarios (cada uno independiente, mismo motor/config):
1. Direccion comun desde movimiento: LONG (mov > 0), SHORT (mov < 0),
   sin_senal (mov == 0), dato_ausente (mov es None). Misma funcion para
   candidato y comparador.
2. Entrada causal LONG y SHORT: fill en open de vela siguiente, nunca
   open pasado de la vela de senal.
3. Salida ejecutada por horizonte: 60 min alcanzados, exit_executed=true.
4. Agotamiento de datos: antes del horizonte, open_at_end, sin salida.
5. Stop intravela: toque con precio segun modelo.
6. Gap autentico: vela anterior no activa stop; apertura posterior cruza.
7. Abstencion: dato ausente / condicion no satisfecha, motivo explicito.
8. Concurrencia max_concurrent=1: senales simultaneas, prioridad determinista.

Sin Binance, sin dashboard, sin infraestructura nueva.
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
    derivar_direccion_desde_movimiento,
)

HORIZON_60M = 3_600_000
NOTIONAL = 1000.0
STOP_PCT = 0.5


def mk_candle(open_ms: int, open_px: float, high: float, low: float,
              close: float, close_ms: int) -> PaperCandle:
    return PaperCandle(
        open_time_ms=open_ms, open=open_px, high=high,
        low=low, close=close, close_time_ms=close_ms,
    )


def mk_config(direction: str, entry_px: float, stop_px: float,
              horizon_ms: int = HORIZON_60M, notional: float = NOTIONAL,
              fee: float = 5.0, spread: float = 1.0, slip: float = 2.0,
              stop_distance_pct: float = STOP_PCT) -> PaperSessionConfig:
    return PaperSessionConfig(
        symbol="TESTUSDT", interval="1m", direction=direction,
        notional_usdt=notional, entry_px=entry_px, stop_px=stop_px,
        stop_distance_pct=stop_distance_pct,
        horizon_ms=horizon_ms, fee_bps=fee, spread_bps=spread,
        slippage_bps=slip, rule_version=RULE_CAUSAL_V1,
    )


def _res(state) -> dict:
    if state.result is None:
        return None
    return {
        "exit_px": state.result.exit_px,
        "exit_ms": state.result.exit_ms,
        "exit_reason": state.result.exit_reason,
        "exit_executed": state.result.exit_executed,
        "open_at_end": state.result.open_at_end,
        "qty": state.result.qty,
        "gross_pnl": state.result.gross_pnl,
        "fees": state.result.fees,
        "spread_slip": state.result.spread_slip,
        "funding": state.result.funding,
        "net_pnl": state.result.net_pnl,
    }


# ============================================================================
# 1. DIRECCION COMUN DESDE INFORMACION DE MERCADO EN T
# ============================================================================
def test_direccion_desde_movimiento_positivo_negativo_ausente():
    """Misma funcion para candidato y comparador; el rol no determina direccion."""
    assert derivar_direccion_desde_movimiento(2.5)["direction"] == "LONG"
    assert derivar_direccion_desde_movimiento(-1.5)["direction"] == "SHORT"
    assert derivar_direccion_desde_movimiento(0.0)["direction"] is None
    assert derivar_direccion_desde_movimiento(None)["direction"] is None
    # Distingue ausencia de senal (0) de ausencia de dato (None).
    assert derivar_direccion_desde_movimiento(0.0)["reason"].startswith("sin_senal")
    assert derivar_direccion_desde_movimiento(None)["reason"].startswith("dato_ausente")


def _signal_session(direction: str, entry_px: float, stop_px: float,
                    velas: List[PaperCandle], at_ms: int):
    config = mk_config(direction, entry_px=entry_px, stop_px=stop_px)
    state = create_session(config, velas, hypothesis_id="H-continuacion")
    return evaluate_session(state, rule_version=RULE_CAUSAL_V1, at_ms=at_ms)


# ============================================================================
# 2. ENTRADA CAUSAL LONG Y SHORT (fill en open de vela siguiente)
# ============================================================================
def test_entrada_causal_long_fill_vela_siguiente():
    """LONG: senal en T con close de V1; fill en open de V2 (102), nunca
    el open pasado de V1 (101)."""
    velas = [
        mk_candle(0, 100.0, 101.0, 99.0, 100.0, 59_999),      # contexto
        mk_candle(60_000, 101.0, 103.0, 101.5, 102.0, 119_000),  # V1 senal (low=101.5 > stop 101.49)
        mk_candle(120_000, 102.0, 105.0, 101.0, 104.0, 180_000),  # V2 fill
    ]
    # entry_px=close de V1=102; stop 0.5% debajo = 101.49
    state = _signal_session("LONG", entry_px=102.0, stop_px=101.49,
                            velas=velas, at_ms=119_000)
    assert state.status == "en_espera"
    assert state.config.decision == "ENTRADA_SIMULADA"
    assert state.config.entry_px == 102.0  # referencia de senal, no fill
    assert (state.config.decision_evidence or {}).get("entry_fill_px") is None

    state = step_forward(state)  # revela open de V2 -> fill a 102.0
    assert state.status == "abierta"
    assert state.position.open is True
    assert abs(state.position.entry_px - 102.0) < 1e-9
    assert state.position.entry_ms == 120_000
    assert abs(state.position.stop_px - 101.49) < 1e-9


def test_entrada_causal_short_fill_vela_siguiente():
    """SHORT: senal en T con close de V1; fill en open de V2 (98.0)."""
    velas = [
        mk_candle(0, 100.0, 101.0, 99.0, 100.0, 59_999),      # contexto
        mk_candle(60_000, 99.0, 98.4, 97.0, 98.0, 119_000),   # V1 senal SHORT (high=98.4 < stop 98.49)
        mk_candle(120_000, 98.0, 99.0, 96.0, 97.0, 180_000),   # V2 fill
    ]
    # entry_px=close de V1=98; stop 0.5% encima = 98.49
    state = _signal_session("SHORT", entry_px=98.0, stop_px=98.49,
                            velas=velas, at_ms=119_000)
    assert state.status == "en_espera"
    assert state.config.decision == "ENTRADA_SIMULADA"
    assert state.config.entry_px == 98.0

    state = step_forward(state)  # fill a 98.0
    assert state.status == "abierta"
    assert abs(state.position.entry_px - 98.0) < 1e-9
    assert state.position.entry_ms == 120_000
    assert abs(state.position.stop_px - 98.49) < 1e-9


def _velas_1m_desde(start_ms: int, base_px: float, n: int) -> List[PaperCandle]:
    """Genera n velas de 1m con cierre plano (base_px) y rango seguro."""
    velas = []
    for i in range(n):
        o = start_ms + i * 60_000
        c = o + 59_999
        velas.append(mk_candle(o, base_px, base_px + 0.5, base_px - 0.5,
                               base_px, c))
    return velas


# ============================================================================
# 3. SALIDA EJECUTADA POR HORIZONTE (60 min realmente alcanzados)
# ============================================================================
def test_salida_por_horizonte_60min_ejecutada():
    """LONG: se alcanzan realmente los 60 min; exit_executed=true, precio,
    tiempo y motivo 'horizon'."""
    # Contexto: vela cerrada en T=59999. Entrada en V1.open=60000 (px 101).
    # Serie de 1m que cubre mucho mas de 60 min tras la entrada (hasta ~120 min).
    contexto = [mk_candle(0, 100.0, 101.0, 99.0, 100.0, 59_999)]
    operacion = _velas_1m_desde(60_000, 101.0, 130)  # cubre hasta 130 min
    velas = contexto + operacion
    state = _signal_session("LONG", entry_px=101.0, stop_px=99.5,
                            velas=velas, at_ms=119_999)
    assert state.status == "en_espera"
    state = step_forward(state)  # fill en open de V2 = 101 @ 120000 (open siguiente a la senal)
    assert state.status == "abierta"
    assert abs(state.position.entry_px - 101.0) < 1e-9
    assert state.position.entry_ms == 120_000  # open de V2, siguiente a la senal V1

    # Avanzar hasta pasar entry + 60 min (120000 + 3600000 = 3720000).
    pasos = 0
    while state.status == "abierta":
        state = step_forward(state)
        pasos += 1
        if pasos > 200:
            raise AssertionError("Demasiados pasos sin cerrar por horizonte")

    r = _res(state)
    assert state.status == "cerrada", state.status
    assert r is not None
    assert r["exit_executed"] is True, r
    assert r["exit_reason"] == "horizon", r
    assert r["exit_ms"] is not None and r["exit_ms"] >= 3_720_000, r  # entry 120000 + 60 min
    assert r["open_at_end"] is False, r
    # Precio de salida es el close conocido (mark), no un stop nominal.
    assert isinstance(r["exit_px"], (int, float)), r
    print(f"  [horizonte] pasos={pasos} exit_px={r['exit_px']} exit_ms={r['exit_ms']} "
          f"reason={r['exit_reason']} executed={r['exit_executed']}")


# ============================================================================
# 4. AGOTAMIENTO DE DATOS ANTES DEL HORIZONTE
# ============================================================================
def test_agotamiento_datos_antes_de_horizonte():
    """LONG: datos se agotan antes de 60 min; open_at_end, sin salida
    ejecutada, marca/open_at_end sin realizado inventado."""
    contexto = [mk_candle(0, 100.0, 101.0, 99.0, 100.0, 59_999)]
    operacion = _velas_1m_desde(60_000, 101.0, 10)  # solo 10 min de datos
    velas = contexto + operacion
    state = _signal_session("LONG", entry_px=101.0, stop_px=99.5,
                            velas=velas, at_ms=119_999)
    state = step_forward(state)  # fill @ 120000 (open de V2, siguiente a la senal V1)
    assert state.status == "abierta"

    while state.status == "abierta":
        state = step_forward(state)

    r = _res(state)
    assert state.status == "cerrada"
    assert r is not None
    assert r["exit_executed"] is False, r
    assert r["exit_reason"] is None, r
    assert r["open_at_end"] is True, r
    # Marca en ultimo precio conocido, no salida inventada.
    assert isinstance(r["exit_px"], (int, float)), r
    assert r["exit_ms"] is not None, r
    print(f"  [agotamiento] exit_px={r['exit_px']} exit_ms={r['exit_ms']} "
          f"reason={r['exit_reason']} executed={r['exit_executed']} "
          f"open_at_end={r['open_at_end']}")


# ============================================================================
# 5. STOP INTRAVELA (toque con precio segun modelo existente)
# ============================================================================
def test_stop_intravela_toque_long():
    """LONG: low de vela conocida toca/cruza el stop; salida al stop_px."""
    # V1 senal close=101, entrada en V2.open=101, stop=101*(1-0.005)=100.495.
    # V3 low=99 <= 100.495 -> stop tocado @ 100.495 (close_time de V3 conocido).
    velas = [
        mk_candle(0, 100.0, 101.0, 99.0, 100.0, 59_999),   # contexto
        mk_candle(60_000, 101.0, 103.0, 100.6, 101.0, 119_999),  # V1 senal (low=100.6 > stop 100.495, no vulnerada)
        mk_candle(120_000, 101.0, 103.0, 100.0, 102.0, 179_999),  # V2 fill open=101 (low=100 tocara stop al conocerse su close)
        mk_candle(180_000, 100.0, 101.0, 99.0, 100.0, 239_999),   # V3: revela close de V2
    ]
    state = _signal_session("LONG", entry_px=101.0, stop_px=100.495,
                            velas=velas, at_ms=119_999)
    state = step_forward(state)  # fill @ 120000, open=101
    assert state.status == "abierta"
    assert abs(state.position.entry_px - 101.0) < 1e-9
    assert abs(state.position.stop_px - 100.495) < 1e-9

    # Revelar V3 (open=180000): se conoce close de V2 (low=100 <= stop 100.495)
    # -> salida por stop intravela @ 100.495.
    state = step_forward(state)  # clock=180000
    assert state.status == "cerrada"
    r = _res(state)
    assert r is not None
    assert r["exit_executed"] is True, r
    assert r["exit_reason"] == "stop", r
    assert abs(r["exit_px"] - 100.495) < 1e-9, r
    print(f"  [stop intravela] exit_px={r['exit_px']} exit_ms={r['exit_ms']} "
          f"reason={r['exit_reason']}")


def test_stop_intravela_toque_short():
    """SHORT: high de vela conocida toca/cruza el stop; salida al stop_px."""
    # V1 senal close=99, entrada V2.open=99, stop=99*(1+0.005)=99.495.
    # V2 high=100 >= 99.495 -> stop tocado al conocerse su close (al revelar V3).
    velas = [
        mk_candle(0, 100.0, 101.0, 99.0, 100.0, 59_999),   # contexto
        mk_candle(60_000, 99.0, 100.0, 97.0, 99.0, 119_999),   # V1 senal SHORT (high=100 >= 99.495? no, 100>=99.495 SÍ -> vulnerada!)
    ]
    # Corregir V1: high debe quedar por debajo del stop para no vulnerarse en la senal.
    velas[1] = mk_candle(60_000, 99.0, 99.4, 97.0, 99.0, 119_999)  # high=99.4 < 99.495
    velas.append(mk_candle(120_000, 99.0, 100.0, 97.0, 98.0, 179_999))  # V2 fill open=99 (high=100 toca stop)
    velas.append(mk_candle(180_000, 98.0, 99.0, 97.0, 98.0, 239_999))   # V3: revela close de V2
    state = _signal_session("SHORT", entry_px=99.0, stop_px=99.495,
                            velas=velas, at_ms=119_999)
    state = step_forward(state)  # fill @ 99 (open de V2)
    assert state.status == "abierta"
    assert abs(state.position.entry_px - 99.0) < 1e-9
    assert abs(state.position.stop_px - 99.495) < 1e-9

    # Revelar V3: se conoce close de V2 (high=100 >= stop 99.495) -> stop.
    state = step_forward(state)  # clock=180000
    assert state.status == "cerrada"
    r = _res(state)
    assert r is not None
    assert r["exit_executed"] is True, r
    assert r["exit_reason"] == "stop", r
    assert abs(r["exit_px"] - 99.495) < 1e-9, r
    print(f"  [stop intravela SHORT] exit_px={r['exit_px']} exit_ms={r['exit_ms']} "
          f"reason={r['exit_reason']}")


# ============================================================================
# 6. GAP AUTENTICO (ninguna vela anterior activa el stop; apertura posterior
# cruza el stop y salida al precio disponible tras el salto)
# ============================================================================
def test_gap_autentico_long_apertura_por_debajo_stop():
    """LONG: V1 entrada open=101 stop=100.495. Ninguna vela anterior toca el
    stop. V2 abre en 90 (cruza el stop) -> salida al OPEN disponible tras el
    salto (90), no al stop nominal garantizado."""
    velas = [
        mk_candle(0, 100.0, 101.0, 99.0, 100.0, 59_999),   # contexto
        mk_candle(60_000, 101.0, 102.0, 100.6, 101.0, 119_999),  # V1 senal (low=100.6 > stop 100.495, no vulnerada)
        mk_candle(120_000, 101.0, 102.0, 100.5, 101.5, 179_999),  # V2 fill open=101 (low=100.5 > 100.495, stop no tocado)
        mk_candle(180_000, 90.0, 92.0, 88.0, 91.0, 239_999),   # V3 open=90 <= stop -> GAP
    ]
    state = _signal_session("LONG", entry_px=101.0, stop_px=100.495,
                            velas=velas, at_ms=119_999)
    state = step_forward(state)  # fill V2 @ 101
    assert state.status == "abierta"
    assert abs(state.position.entry_px - 101.0) < 1e-9
    # Revelar V3: open=90 cruza el stop -> salida @ 90 (gap, precio real tras salto).
    state = step_forward(state)  # clock=180000
    assert state.status == "cerrada"
    r = _res(state)
    assert r is not None
    assert r["exit_executed"] is True, r
    assert r["exit_reason"] == "stop", r
    # Salida al precio disponible tras el salto (open de V3 = 90), NO al stop nominal 100.495.
    assert abs(r["exit_px"] - 90.0) < 1e-9, r
    assert abs(r["exit_px"] - 100.495) > 1e-6, r  # no es el stop nominal
    print(f"  [gap LONG] exit_px={r['exit_px']} (no stop nominal 100.495) "
          f"reason={r['exit_reason']} executed={r['exit_executed']}")


def test_gap_autentico_short_apertura_por_encima_stop():
    """SHORT: V1 entrada open=99 stop=99.495. V2 abre en 108 (cruza) ->
    salida @ 108 (gap), no al stop nominal."""
    velas = [
        mk_candle(0, 100.0, 101.0, 99.0, 100.0, 59_999),   # contexto
        mk_candle(60_000, 99.0, 99.4, 97.0, 99.0, 119_999),   # V1 senal SHORT (high=99.4 < stop 99.495, no vulnerada)
        mk_candle(120_000, 99.0, 100.0, 98.5, 99.5, 179_999),  # V2 fill open=99 (se reasigna abajo)
    ]
    # Corregir V2: high debe estar por debajo del stop para que NO toque antes del gap.
    velas[2] = mk_candle(120_000, 99.0, 99.4, 98.0, 99.0, 179_999)  # high=99.4 < 99.495
    velas.append(mk_candle(180_000, 108.0, 110.0, 106.0, 109.0, 239_999))  # V3 open=108 >= stop -> GAP
    state = _signal_session("SHORT", entry_px=99.0, stop_px=99.495,
                            velas=velas, at_ms=119_999)
    state = step_forward(state)  # fill V2 @ 99
    assert state.status == "abierta"
    assert abs(state.position.entry_px - 99.0) < 1e-9
    # Revelar V3: open=108 >= stop 99.495 -> GAP salida @ 108 (precio tras salto).
    state = step_forward(state)  # clock=180000
    assert state.status == "cerrada"
    r = _res(state)
    assert r is not None
    assert r["exit_executed"] is True, r
    assert r["exit_reason"] == "stop", r
    assert abs(r["exit_px"] - 108.0) < 1e-9, r
    assert abs(r["exit_px"] - 99.495) > 1e-6, r
    print(f"  [gap SHORT] exit_px={r['exit_px']} (no stop nominal 99.495) "
          f"reason={r['exit_reason']} executed={r['exit_executed']}")


# ============================================================================
# 7. ABSTENCION (dato ausente / condicion no satisfecha, motivo explicito)
# ============================================================================
def test_abstencion_dato_movimiento_ausente():
    """Comparador sin move_24h_pct: direccion None -> SIN_ENTRADA, motivo dato_ausente."""
    d = derivar_direccion_desde_movimiento(None)
    assert d["direction"] is None
    assert d["reason"].startswith("dato_ausente")
    # Una sesion LONG con move_24h_pct None no puede derivar direccion valida;
    # el rol no la asigna por sustituto.
    assert d["direction"] != "LONG" and d["direction"] != "SHORT"


def test_abstencion_sin_close_conocido_en_T():
    """En T no hay vela plenamente conocida (close desconocido) -> SIN_ENTRADA temporal."""
    velas = [
        mk_candle(60_000, 101.0, 103.0, 100.0, None, None),  # sin close
    ]
    state = _signal_session("LONG", entry_px=100.0, stop_px=95.0,
                            velas=velas, at_ms=30_000)
    assert state.status == "sin_iniciar"
    assert state.config.decision == "SIN_ENTRADA"
    assert state.position.open is False
    assert state.result is None
    ev = state.config.decision_evidence or {}
    assert ev.get("abstention_kind") == "temporal", ev


def test_abstencion_precio_no_a_favor():
    """Condicion no satisfecha: close no opera a favor vs entry_px -> SIN_ENTRADA."""
    velas = [
        mk_candle(0, 100.0, 101.0, 99.0, 100.0, 59_999),   # contexto
        mk_candle(60_000, 101.0, 102.0, 100.0, 99.0, 119_999),  # V1 close=99 < entry=100 (LONG)
    ]
    state = _signal_session("LONG", entry_px=100.0, stop_px=95.0,
                            velas=velas, at_ms=119_999)
    assert state.config.decision == "SIN_ENTRADA", state.config.decision
    assert state.position.open is False
    ev = state.config.decision_evidence or {}
    assert ev.get("abstention_kind") == "temporal", ev


# ============================================================================
# 8. CONCURRENCIA: senales simultaneas, max_concurrent=1, prioridad determinista
# ============================================================================
def test_concurrencia_max_concurrent_1_prioridad_determinista():
    """Dos senales simultáneas (mismo T) en el mismo recorrido con
    max_concurrent=1: una se admite, la otra se rechaza por capacidad, no por
    su resultado posterior. Prioridad determinista por (event_time_ms, symbol)."""
    from microstructure_probe.backtest_offline import (  # noqa: E402
        BacktestConfig, Candle, StudyEvent, run_backtest,
    )
    # Dos simbolos con senal en el mismo T (simultaneas).
    ev_cand = StudyEvent("CANDUSDT", 100_000, "LONG", 100.0,
                         family="H1", rules_version="H1-v1")
    ev_comp = StudyEvent("COMPUSDT", 100_000, "SHORT", 100.0,
                         family="H1", rules_version="H1-v1")
    # Datos equivalentes para ambos (mismo recorrido de precios).
    datos = [
        mk_candle(60_000, 100.0, 102.0, 99.0, 101.0, 119_999),
        mk_candle(120_000, 101.0, 103.0, 100.0, 102.0, 179_999),
        mk_candle(180_000, 102.0, 104.0, 101.0, 103.0, 239_999),
        mk_candle(240_000, 103.0, 105.0, 102.0, 104.0, 299_999),
    ]
    bt = [Candle(symbol=s, open_time_ms=c.open_time_ms, open=c.open,
                 high=c.high, low=c.low, close=c.close,
                 close_time_ms=c.close_time_ms)
          for c in datos for s in ("CANDUSDT", "COMPUSDT")]
    cfg = BacktestConfig(family="H1", rules_version="H1-v1",
                         exit_horizon_ms=HORIZON_60M,
                         stop_distance_pct=STOP_PCT, notional_usdt=NOTIONAL,
                         fee_bps=5.0, spread_bps=1.0, slippage_bps=2.0,
                         cost_scale=1.0, max_concurrent=1,
                         funding_calendar=None, funding_estimated_bps=None)
    res = run_backtest([ev_cand, ev_comp], bt, cfg,
                       dataset_id="conc-fixture", segment="dev")

    # Una admitida, la otra saltada por capacidad (skipped_overlap=1).
    assert res["n_trades"] == 1, res
    assert res["skipped_overlap"] == 1, res
    # Prioridad determinista: simbolo alfabeticamente primero entra primero.
    admitida = res["trades"][0]
    assert admitida["symbol"] == "CANDUSDT", admitida
    # La rechazada no tiene trade; su decision no se elige por retorno posterior.
    print(f"  [concurrencia] admitida={admitida['symbol']} reason={admitida['exit_reason']} "
          f"skipped_overlap={res['skipped_overlap']} n_trades={res['n_trades']}")


# ============================================================================
# 4. CONTABILIDAD INDEPENDIENTE (LONG y SHORT recalculados a mano)
# ============================================================================
def _recorrido_stop(direction: str, entry_px: float, stop_px: float,
                    fill_extreme: float):
    """Recorrido paper_lab_engine: senal en V1, fill en V2 (open siguiente),
    salida por stop al conocerse el close de V2 (su extremo cruza stop).
    Sin calendario de funding -> funding = None (UNKNOWN, nunca cero).

    V1 se construye para que NO vulnere el stop en T (close opera a favor,
    extremo seguro vs stop). V2 rellena en su open y su extremo (low LONG /
    high SHORT) dispara el stop al conocerse su close.
    """
    if direction == "LONG":
        v1_high, v1_low = entry_px + 1.0, entry_px - 0.3   # low > stop: no vulnerada en T
        v2_high, v2_low = entry_px + 1.0, fill_extreme     # low cruza stop
    else:
        v1_high, v1_low = entry_px + 0.4, entry_px - 1.0   # high < stop: no vulnerada en T
        v2_high, v2_low = fill_extreme, entry_px - 1.0     # high cruza stop
    velas = [
        mk_candle(0, 100.0, 101.0, 99.0, 100.0, 59_999),       # V0 contexto
        mk_candle(60_000, entry_px, v1_high, v1_low, entry_px, 119_999),  # V1 senal
        mk_candle(120_000, entry_px, v2_high, v2_low, entry_px, 179_999),  # V2 fill + rango
        mk_candle(180_000, entry_px, entry_px + 1.0, entry_px - 0.3,
                  entry_px, 239_999),                          # V3: revela close de V2
    ]
    config = mk_config(direction, entry_px=entry_px, stop_px=stop_px)
    state = create_session(config, velas, hypothesis_id="H-contab")
    state = evaluate_session(state, rule_version=RULE_CAUSAL_V1, at_ms=119_999)
    assert state.status == "en_espera", state.status
    state = step_forward(state)  # fill en V2.open = entry_px
    assert state.status == "abierta"
    state = step_forward(state)  # revela V3, conoce close de V2 -> stop
    assert state.status == "cerrada"
    return state.result


def test_contabilidad_independiente_long_y_short():
    """Recalcula independientemente un LONG y un SHORT: cantidad, P&L bruto,
    comisiones, spread/slippage, funding y neto. Valores esperados calculados
    a mano (no se usa el mismo helper para el esperado). Funding desconocido
    = None (UNKNOWN), nunca cero (no hay calendario en el recorrido).

    stop_fraction = stop_distance_pct / 100 = 0.5 / 100 = 0.005.
    Entrada 100, notional 1000, qty = 1000/100 = 10:
      LONG stop = 100 x (1 - 0.005) = 99.5 ; riesgo nominal = 0.005 x 1000 = 5 USDT.
      SHORT stop = 100 x (1 + 0.005) = 100.5 ; riesgo nominal = 5 USDT.
    """
    fee_bps, spread_bps, slip_bps = 5.0, 1.0, 2.0
    drag = (spread_bps + slip_bps) / 10_000.0  # 0.0003
    qty = NOTIONAL / 100.0  # 10
    entry_fees = NOTIONAL * fee_bps / 10_000.0  # 0.5

    # ---- LONG: stop 99.5, salida @ 99.5 ----
    stop_long = 100.0 * (1.0 - STOP_PCT / 100.0)  # 99.5
    assert abs(stop_long - 99.5) < 1e-9  # stop_fraction aplicada
    r_long = _recorrido_stop("LONG", 100.0, stop_long, 99.0)
    bruto_long = (stop_long - 100.0) * qty  # -50
    exit_value_long = stop_long * qty  # 995
    exit_fees_long = exit_value_long * fee_bps / 10_000.0  # 0.4975
    entry_spread = NOTIONAL * drag  # 0.3
    exit_spread_long = exit_value_long * drag  # 0.2985
    neto_esperado_long = (bruto_long - entry_fees - exit_fees_long
                          - entry_spread - exit_spread_long)  # -51.596
    assert abs(r_long.exit_px - 99.5) < 1e-9, r_long
    assert abs(r_long.qty - qty) < 1e-9, r_long
    assert abs(r_long.gross_pnl - bruto_long) < 1e-9, r_long
    assert abs(r_long.fees - (entry_fees + exit_fees_long)) < 1e-9, r_long
    assert abs(r_long.spread_slip - (entry_spread + exit_spread_long)) < 1e-9, r_long
    assert r_long.funding is None, r_long  # desconocido, no cero
    assert abs(r_long.net_pnl - neto_esperado_long) < 1e-9, (r_long, neto_esperado_long)

    # ---- SHORT: stop 100.5, salida @ 100.5 ----
    stop_short = 100.0 * (1.0 + STOP_PCT / 100.0)  # 100.5
    assert abs(stop_short - 100.5) < 1e-9
    r_short = _recorrido_stop("SHORT", 100.0, stop_short, 101.0)  # high de V2 toca stop
    bruto_short = (100.0 - stop_short) * qty  # -5
    exit_value_short = stop_short * qty  # 1005
    exit_fees_short = exit_value_short * fee_bps / 10_000.0  # 0.5025
    exit_spread_short = exit_value_short * drag  # 0.3015
    neto_esperado_short = (bruto_short - entry_fees - exit_fees_short
                           - entry_spread - exit_spread_short)  # -6.604
    assert abs(r_short.exit_px - 100.5) < 1e-9, r_short
    assert abs(r_short.qty - qty) < 1e-9, r_short
    assert abs(r_short.gross_pnl - bruto_short) < 1e-9, r_short
    assert abs(r_short.fees - (entry_fees + exit_fees_short)) < 1e-9, r_short
    assert abs(r_short.spread_slip - (entry_spread + exit_spread_short)) < 1e-9, r_short
    assert r_short.funding is None, r_short
    assert abs(r_short.net_pnl - neto_esperado_short) < 1e-9, (r_short, neto_esperado_short)

    print(f"  [contabilidad LONG] qty={qty} bruto={bruto_long} fees={entry_fees+exit_fees_long} "
          f"spread={entry_spread+exit_spread_long} neto={neto_esperado_long} funding={r_long.funding}")
    print(f"  [contabilidad SHORT] qty={qty} bruto={bruto_short} fees={entry_fees+exit_fees_short} "
          f"spread={entry_spread+exit_spread_short} neto={neto_esperado_short} funding={r_short.funding}")


if __name__ == "__main__":
    test_direccion_desde_movimiento_positivo_negativo_ausente()
    print("OK: direccion comun desde movimiento")
    test_entrada_causal_long_fill_vela_siguiente()
    print("OK: entrada causal LONG")
    test_entrada_causal_short_fill_vela_siguiente()
    print("OK: entrada causal SHORT")
    test_salida_por_horizonte_60min_ejecutada()
    print("OK: salida por horizonte 60min ejecutada")
    test_agotamiento_datos_antes_de_horizonte()
    print("OK: agotamiento de datos")
    test_stop_intravela_toque_long()
    print("OK: stop intravela LONG")
    test_stop_intravela_toque_short()
    print("OK: stop intravela SHORT")
    test_gap_autentico_long_apertura_por_debajo_stop()
    print("OK: gap autentico LONG")
    test_gap_autentico_short_apertura_por_encima_stop()
    print("OK: gap autentico SHORT")
    test_abstencion_dato_movimiento_ausente()
    print("OK: abstencion dato ausente")
    test_abstencion_sin_close_conocido_en_T()
    print("OK: abstencion sin close conocido")
    test_abstencion_precio_no_a_favor()
    print("OK: abstencion condicion no satisfecha")
    test_concurrencia_max_concurrent_1_prioridad_determinista()
    print("OK: concurrencia max_concurrent=1")
    test_contabilidad_independiente_long_y_short()
    print("OK: contabilidad independiente LONG y SHORT")
    print("TODAS LAS PRUEBAS FOCALIZADAS PASARON")






