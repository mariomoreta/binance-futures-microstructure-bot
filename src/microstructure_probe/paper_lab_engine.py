"""Paper Lab motor de ingeniería — orquestación incremental sobre fixtures.

Backend como fuente de verdad: posee reloj de sesión, configuración versionada,
decisiones, posiciones, fills, costes, eventos y resultados. El navegador
solicita acciones acotadas y presenta estados recibidos.

Reutiliza las primitivas de ``backtest_offline.py`` (BacktestConfig, Candle,
StudyEvent, run_backtest, input_hash, costes, funding) sin crear un segundo
motor económico independiente. No hay Binance, no hay feed vivo, no hay
ordenes reales, no hay capital real.

Sesiones de ingeniería (este módulo) están separadas de futuras sesiones
prospectivas: distinto directorio de persistencia, distinto identificador.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from microstructure_probe.backtest_offline import (  # noqa: E402
    BacktestConfig,
    Candle,
    ENGINE_VERSION,
    FundingCalendar,
    FundingSettlement,
    StudyEvent,
    input_hash,
    run_backtest,
)

ENGINE_VERSION_PAPER = "paper-lab-engine/v1.0"
SESSION_DIR_NAME = "paper-lab-sessions"

# --- Estados de sesión (ingeniería) ---------------------------------------
# sin_iniciar  → evaluando → en_espera → abierta → cerrada / detenida
SessionStatus = str  # "sin_iniciar" | "evaluando" | "en_espera" |
#                    "abierta" | "cerrada" | "detenida"

# --- Decisiones de candidato -----------------------------------------------
# VIGILANDO / SIN_ENTRADA / DESCARTADO / ENTRADA_SIMULADA
CandidateDecision = str


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_session_id(symbol: str, direction: str) -> str:
    ts = _now_ms()
    rnd = hashlib.sha256(os.urandom(8)).hexdigest()[:8]
    return f"PL-{symbol}-{direction}-{ts}-{rnd}"[:64]


def _safe_session_id(session_id: str) -> str:
    """Valida que session_id sea un identificador seguro (no traversal)."""
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("SESSION_ID_REQUIRED")
    if session_id != os.path.basename(session_id):
        raise ValueError("SESSION_ID_INVALID")
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        raise ValueError("SESSION_ID_INVALID")
    if not session_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("SESSION_ID_INVALID")
    return session_id


@dataclass
class PaperCandle:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    close_time_ms: int


@dataclass
class PaperPosition:
    open: bool = False
    direction: Optional[str] = None
    entry_px: Optional[float] = None
    entry_qty: Optional[float] = None
    entry_cost: Optional[float] = None
    entry_ms: Optional[int] = None
    stop_px: Optional[float] = None
    mark_px: Optional[float] = None
    mark_ms: Optional[int] = None
    unrealized_gross: Optional[float] = None
    unrealized_net: Optional[float] = None
    mfe_pct: Optional[float] = None
    mae_pct: Optional[float] = None


@dataclass
class PaperCosts:
    fee_bps: float = 0.0
    spread_bps: float = 0.0
    entry_fees: float = 0.0
    exit_fees: float = 0.0
    entry_spread_slip: float = 0.0
    exit_spread_slip: float = 0.0
    funding: float = 0.0
    friction: float = 0.0


@dataclass
class PaperEvent:
    at_ms: int
    label: str
    kind: str  # "entry" | "exit" | "stop" | "protection" | "mark" | "horizon"
    detail: Optional[str] = None


@dataclass
class PaperTradeResult:
    symbol: str
    direction: str
    entry_px: float
    exit_px: Optional[float]
    entry_ms: int
    exit_ms: Optional[int]
    exit_reason: Optional[str]
    exit_executed: bool
    qty: float
    filled_cost: float
    gross_pnl: float
    fees: float
    spread_slip: float
    funding: float
    friction: float
    net_pnl: float
    realized_net: Optional[float]
    open_at_end: bool


@dataclass
class PaperSessionConfig:
    symbol: str
    interval: str
    direction: str
    notional_usdt: float
    entry_px: float
    stop_px: float
    stop_distance_pct: float
    horizon_ms: int
    fee_bps: float
    spread_bps: float
    slippage_bps: float
    # Hypothesis / rule identity (versioned, fixed before execution)
    hypothesis_id: Optional[str] = None
    hypothesis_version: Optional[str] = None
    decision: Optional[CandidateDecision] = None
    decision_reason: Optional[str] = None


@dataclass
class PaperSessionState:
    session_id: str
    created_at_ms: int
    updated_at_ms: int
    status: SessionStatus
    config: PaperSessionConfig
    candles: List[PaperCandle]
    context_candles: List[PaperCandle]
    cursor: int
    position: PaperPosition
    costs: PaperCosts
    events: List[PaperEvent]
    result: Optional[PaperTradeResult]
    clock_ms: Optional[int]
    # Provenance / versioning
    config_hash: Optional[str] = None
    input_hash: Optional[str] = None
    engine_version: str = ENGINE_VERSION_PAPER
    limitations: List[str] = field(default_factory=list)


# --- Helpers de cálculo (reutilizan la mecánica de backtest_offline) ------

def _gross_pnl(direction: str, entry_px: float, mark_px: float, qty: float) -> float:
    if direction == "LONG":
        return (mark_px - entry_px) * qty
    return (entry_px - mark_px) * qty


def _excursion_pct(direction: str, entry_px: float, mark_px: float) -> float:
    if entry_px <= 0:
        return 0.0
    if direction == "LONG":
        return ((mark_px - entry_px) / entry_px) * 100.0
    return ((entry_px - mark_px) / entry_px) * 100.0


def _entry_fees_amount(config: PaperSessionConfig) -> float:
    return config.notional_usdt * (config.fee_bps / 10000.0)


def _entry_spread_slip_amount(config: PaperSessionConfig) -> float:
    return config.notional_usdt * (
        (config.spread_bps + config.slippage_bps) / 10000.0
    )


def _exit_fees_amount(notional_exit_usdt: float,
                      config: PaperSessionConfig) -> float:
    return notional_exit_usdt * (config.fee_bps / 10000.0)


def _exit_spread_slip_amount(notional_exit_usdt: float,
                             config: PaperSessionConfig) -> float:
    return notional_exit_usdt * (
        (config.spread_bps + config.slippage_bps) / 10000.0
    )


# --- Sesión ---------------------------------------------------------------

def create_session(config: PaperSessionConfig,
                   candles: List[PaperCandle],
                   context_candles: List[PaperCandle] = None,
                   hypothesis_id: Optional[str] = None,
                   hypothesis_version: Optional[str] = None,
                   decision: Optional[CandidateDecision] = None,
                   decision_reason: Optional[str] = None) -> PaperSessionState:
    """Crea una sesión de ingeniería en estado sin_iniciar.

    No ejecuta entrada: solo prepara el escenario. La entrada ocurre tras
    una decisión válida (ENTRADA_SIMULADA).
    """
    if context_candles is None:
        context_candles = []
    entry_fees = _entry_fees_amount(config)
    entry_spread_slip = _entry_spread_slip_amount(config)
    now = _now_ms()
    session_id = _new_session_id(config.symbol, config.direction)

    # Config hash y input hash para trazabilidad/versionado
    cfg_dict = {
        "symbol": config.symbol, "interval": config.interval,
        "direction": config.direction, "notional_usdt": config.notional_usdt,
        "entry_px": config.entry_px, "stop_px": config.stop_px,
        "stop_distance_pct": config.stop_distance_pct,
        "horizon_ms": config.horizon_ms, "fee_bps": config.fee_bps,
        "spread_bps": config.spread_bps, "slippage_bps": config.slippage_bps,
        "hypothesis_id": hypothesis_id,
        "hypothesis_version": hypothesis_version,
        "decision": decision,
        "decision_reason": decision_reason,
        "engine_version": ENGINE_VERSION_PAPER,
    }
    config_hash = hashlib.sha256(
        json.dumps(cfg_dict, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]

    in_hash = input_hash(
        [StudyEvent(symbol=config.symbol, event_time_ms=0,
                    direction=config.direction, reference_price=config.entry_px,
                    family="H1", rules_version="H1-v1")],
        [Candle(symbol=config.symbol, open_time_ms=c.open_time_ms,
                open=c.open, high=c.high, low=c.low, close=c.close,
                close_time_ms=c.close_time_ms)
         for c in candles],
    ) if candles else None

    session = PaperSessionState(
        session_id=session_id,
        created_at_ms=now,
        updated_at_ms=now,
        status="sin_iniciar",
        config=PaperSessionConfig(
            symbol=config.symbol, interval=config.interval,
            direction=config.direction, notional_usdt=config.notional_usdt,
            entry_px=config.entry_px, stop_px=config.stop_px,
            stop_distance_pct=config.stop_distance_pct,
            horizon_ms=config.horizon_ms, fee_bps=config.fee_bps,
            spread_bps=config.spread_bps, slippage_bps=config.slippage_bps,
            hypothesis_id=hypothesis_id,
            hypothesis_version=hypothesis_version,
            decision=decision,
            decision_reason=decision_reason,
        ),
        candles=candles,
        context_candles=context_candles,
        cursor=0,
        position=PaperPosition(
            open=False, direction=None, entry_px=None, entry_qty=None,
            entry_cost=None, entry_ms=None, stop_px=config.stop_px,
            mark_px=None, mark_ms=None, unrealized_gross=None,
            unrealized_net=None, mfe_pct=None, mae_pct=None,
        ),
        costs=PaperCosts(
            fee_bps=config.fee_bps, spread_bps=config.spread_bps,
            entry_fees=entry_fees, exit_fees=0.0,
            entry_spread_slip=entry_spread_slip, exit_spread_slip=0.0,
            funding=0.0, friction=entry_fees + entry_spread_slip,
        ),
        events=[],
        result=None,
        clock_ms=None,
        config_hash=config_hash,
        input_hash=in_hash,
        engine_version=ENGINE_VERSION_PAPER,
        limitations=[
            "no-latency-model",
            "no-tick-lot-rounding",
            "no-min-notional-gate",
            "realized-only-drawdown",
            "engineering-fixture-only",
        ],
    )
    return session


def _apply_entry(state: PaperSessionState) -> PaperSessionState:
    """Ejecuta la entrada en la vela actual (cursor) y abre la posición."""
    config = state.config
    candles = state.candles
    cursor = state.cursor
    if cursor < 0 or cursor >= len(candles):
        return state
    candle = candles[cursor]
    entry_px = config.entry_px
    qty = config.notional_usdt / entry_px
    filled_cost = entry_px * qty
    entry_ms = candle.close_time_ms if candle.close_time_ms is not None \
        else candle.open_time_ms

    next_state = PaperSessionState(
        session_id=state.session_id,
        created_at_ms=state.created_at_ms,
        updated_at_ms=_now_ms(),
        status="abierta",
        config=state.config,
        candles=state.candles,
        context_candles=state.context_candles,
        cursor=cursor,
        position=PaperPosition(
            open=True, direction=config.direction, entry_px=entry_px,
            entry_qty=qty, entry_cost=filled_cost, entry_ms=entry_ms,
            stop_px=config.stop_px, mark_px=entry_px, mark_ms=entry_ms,
            unrealized_gross=0.0,
            unrealized_net=0.0 - state.costs.friction,
            mfe_pct=0.0, mae_pct=0.0,
        ),
        costs=PaperCosts(
            fee_bps=state.costs.fee_bps, spread_bps=state.costs.spread_bps,
            entry_fees=state.costs.entry_fees, exit_fees=0.0,
            entry_spread_slip=state.costs.entry_spread_slip,
            exit_spread_slip=0.0, funding=0.0,
            friction=state.costs.entry_fees + state.costs.entry_spread_slip,
        ),
        events=list(state.events) + [
            PaperEvent(
                at_ms=entry_ms,
                label=f"Entrada {config.direction} @ {entry_px:.2f}",
                kind="entry",
                detail=(f"qty={qty:.8f} notional={config.notional_usdt} "
                        f"stop={config.stop_px}"),
            )
        ],
        result=None,
        clock_ms=entry_ms,
        config_hash=state.config_hash,
        input_hash=state.input_hash,
        engine_version=state.engine_version,
        limitations=list(state.limitations),
    )
    return next_state


def step_forward(state: PaperSessionState) -> PaperSessionState:
    """Avanza un paso (vela cerrada conocida), actualiza marca y evalúa salida.

    Reglas causales (reutilizan backtest_offline):
    - Solo velas cerradas conocidas hasta el cursor.
    - Stop: vela cuya low (LONG) / high (SHORT) toca el stop.
    - Horizonte: entry_ms + horizon_ms alcanzado.
    - Sin salida al agotar datos → posición permanece abierta (open_at_end).
    """
    if state.status in ("cerrada", "detenida"):
        return state

    # Si está en_espera (decisión ENTRADA_SIMULADA pero no entrada ejecutada),
    # el primer paso ejecuta la entrada.
    if state.status == "en_espera" and not state.position.open:
        return _apply_entry(state)

    config = state.config
    candles = state.candles
    n = len(candles)
    next_cursor = min(n, state.cursor + 1)
    candle = candles[next_cursor - 1] if next_cursor > 0 else None
    clock_ms = (candle.close_time_ms if candle and candle.close_time_ms
                is not None else candle.open_time_ms) if candle else None

    next_state = PaperSessionState(
        session_id=state.session_id,
        created_at_ms=state.created_at_ms,
        updated_at_ms=_now_ms(),
        status=state.status,
        config=state.config,
        candles=state.candles,
        context_candles=state.context_candles,
        cursor=next_cursor,
        position=state.position,
        costs=state.costs,
        events=list(state.events),
        result=state.result,
        clock_ms=clock_ms,
        config_hash=state.config_hash,
        input_hash=state.input_hash,
        engine_version=state.engine_version,
        limitations=list(state.limitations),
    )

    # Si hay posición abierta, actualizar marca y evaluar salidas.
    if (next_state.position.open
            and next_state.position.entry_px is not None
            and next_state.position.entry_qty is not None):
        px = candle.close if candle else None
        mark_px = px if px is not None \
            else (next_state.position.mark_px or 0.0)
        mark_ms = clock_ms if clock_ms is not None \
            else (next_state.position.mark_ms or 0)
        qty = next_state.position.entry_qty
        entry_px = next_state.position.entry_px

        gross = _gross_pnl(config.direction, entry_px, mark_px, qty)
        mfe_pct = _excursion_pct(config.direction, entry_px, mark_px)

        prev_mae = next_state.position.mae_pct or 0.0
        mae_pct = min(prev_mae,
                      _excursion_pct(config.direction, entry_px, mark_px))

        notional_exit = mark_px * qty
        exit_fees = _exit_fees_amount(notional_exit, config)
        exit_spread_slip = _exit_spread_slip_amount(notional_exit, config)
        friction = (next_state.costs.entry_fees + exit_fees
                    + next_state.costs.entry_spread_slip
                    + exit_spread_slip + next_state.costs.funding)
        unrealized_net = gross - friction

        # Reemplazar evento de marca anterior
        events = [e for e in next_state.events if e.kind != "mark"]
        events.append(PaperEvent(
            at_ms=mark_ms,
            label=f"Marca {mark_px:.2f}",
            kind="mark",
            detail=f"P&L no realizado {unrealized_net:.2f}",
        ))

        next_state = PaperSessionState(
            session_id=next_state.session_id,
            created_at_ms=next_state.created_at_ms,
            updated_at_ms=_now_ms(),
            status=next_state.status,
            config=next_state.config,
            candles=next_state.candles,
            context_candles=next_state.context_candles,
            cursor=next_state.cursor,
            position=PaperPosition(
                open=next_state.position.open,
                direction=next_state.position.direction,
                entry_px=next_state.position.entry_px,
                entry_qty=next_state.position.entry_qty,
                entry_cost=next_state.position.entry_cost,
                entry_ms=next_state.position.entry_ms,
                stop_px=next_state.position.stop_px,
                mark_px=mark_px, mark_ms=mark_ms,
                unrealized_gross=gross, unrealized_net=unrealized_net,
                mfe_pct=max(next_state.position.mfe_pct or 0.0, mfe_pct),
                mae_pct=mae_pct,
            ),
            costs=PaperCosts(
                fee_bps=next_state.costs.fee_bps,
                spread_bps=next_state.costs.spread_bps,
                entry_fees=next_state.costs.entry_fees,
                exit_fees=exit_fees,
                entry_spread_slip=next_state.costs.entry_spread_slip,
                exit_spread_slip=exit_spread_slip,
                funding=next_state.costs.funding, friction=friction,
            ),
            events=events,
            result=next_state.result,
            clock_ms=next_state.clock_ms,
            config_hash=next_state.config_hash,
            input_hash=next_state.input_hash,
            engine_version=next_state.engine_version,
            limitations=list(next_state.limitations),
        )

        # Evaluar stop
        stop_px = next_state.position.stop_px or 0.0
        hit_stop = (candle is not None and (
            (config.direction == "LONG" and candle.low <= stop_px)
            or (config.direction == "SHORT" and candle.high >= stop_px)
        ))

        # Evaluar horizonte
        horizon_end = (next_state.position.entry_ms
                       + config.horizon_ms
                       if next_state.position.entry_ms is not None else None)
        hit_horizon = (horizon_end is not None and clock_ms is not None
                       and clock_ms >= horizon_end)

        if hit_stop:
            return _finalize_exit(next_state, "stop", stop_px,
                                  clock_ms or mark_ms)
        if hit_horizon:
            return _finalize_exit(next_state, "horizon", mark_px,
                                  clock_ms or mark_ms)

    # Agotamiento de datos sin salida ejecutada → open_at_end
    if (next_cursor >= n and next_state.position.open
            and next_state.result is None):
        return _finalize_open_at_end(next_state)

    return next_state


def _finalize_exit(state: PaperSessionState, reason: str,
                   exit_px: float, exit_ms: int) -> PaperSessionState:
    """Finaliza la sesión con salida ejecutada. Costes consistentes."""
    config = state.config
    position = state.position
    entry_px = position.entry_px or 0.0
    qty = position.entry_qty or 0.0

    gross = _gross_pnl(config.direction, entry_px, exit_px, qty)
    exit_fees = _exit_fees_amount(exit_px * qty, config)
    exit_spread_slip = _exit_spread_slip_amount(exit_px * qty, config)
    friction = (state.costs.entry_fees + exit_fees
                + state.costs.entry_spread_slip
                + exit_spread_slip + state.costs.funding)
    net = gross - friction

    events = list(state.events)
    events.append(PaperEvent(
        at_ms=exit_ms,
        label=f"Salida {reason} @ {exit_px:.2f}",
        kind="exit",
        detail=f"razon={reason} P&L neto={net:.2f}",
    ))

    result = PaperTradeResult(
        symbol=config.symbol, direction=config.direction,
        entry_px=entry_px, exit_px=exit_px,
        entry_ms=position.entry_ms or 0, exit_ms=exit_ms,
        exit_reason=reason, exit_executed=True, qty=qty,
        filled_cost=position.entry_cost or 0.0,
        gross_pnl=gross, fees=state.costs.entry_fees + exit_fees,
        spread_slip=state.costs.entry_spread_slip + exit_spread_slip,
        funding=state.costs.funding, friction=friction,
        net_pnl=net, realized_net=net, open_at_end=False,
    )

    return PaperSessionState(
        session_id=state.session_id,
        created_at_ms=state.created_at_ms,
        updated_at_ms=_now_ms(),
        status="cerrada",
        config=state.config,
        candles=state.candles,
        context_candles=state.context_candles,
        cursor=state.cursor,
        position=PaperPosition(
            open=False, direction=position.direction,
            entry_px=position.entry_px, entry_qty=position.entry_qty,
            entry_cost=position.entry_cost, entry_ms=position.entry_ms,
            stop_px=position.stop_px, mark_px=exit_px, mark_ms=exit_ms,
            unrealized_gross=gross, unrealized_net=net,
            mfe_pct=position.mfe_pct, mae_pct=position.mae_pct,
        ),
        costs=PaperCosts(
            fee_bps=state.costs.fee_bps,
            spread_bps=state.costs.spread_bps,
            entry_fees=state.costs.entry_fees,
            exit_fees=exit_fees,
            entry_spread_slip=state.costs.entry_spread_slip,
            exit_spread_slip=exit_spread_slip,
            funding=state.costs.funding, friction=friction,
        ),
        events=events,
        result=result,
        clock_ms=exit_ms,
        config_hash=state.config_hash,
        input_hash=state.input_hash,
        engine_version=state.engine_version,
        limitations=list(state.limitations),
    )


def _finalize_open_at_end(state: PaperSessionState) -> PaperSessionState:
    """Agotamiento de datos: posición permanece abierta, no realizada."""
    config = state.config
    position = state.position
    entry_px = position.entry_px or 0.0
    qty = position.entry_qty or 0.0
    exit_px = position.mark_px
    exit_ms = position.mark_ms

    gross = _gross_pnl(config.direction, entry_px, exit_px or entry_px,
                       qty) if exit_px is not None else 0.0
    friction = state.costs.friction  # sin costes de salida (no ejecutada)
    net = gross - friction if exit_px is not None else 0.0

    result = PaperTradeResult(
        symbol=config.symbol, direction=config.direction,
        entry_px=entry_px, exit_px=exit_px,
        entry_ms=position.entry_ms or 0, exit_ms=exit_ms,
        exit_reason=None, exit_executed=False, qty=qty,
        filled_cost=position.entry_cost or 0.0,
        gross_pnl=gross, fees=state.costs.entry_fees,
        spread_slip=state.costs.entry_spread_slip,
        funding=state.costs.funding, friction=friction,
        net_pnl=net, realized_net=None, open_at_end=True,
    )

    return PaperSessionState(
        session_id=state.session_id,
        created_at_ms=state.created_at_ms,
        updated_at_ms=_now_ms(),
        status="cerrada",
        config=state.config,
        candles=state.candles,
        context_candles=state.context_candles,
        cursor=state.cursor,
        position=PaperPosition(
            open=False, direction=position.direction,
            entry_px=position.entry_px, entry_qty=position.entry_qty,
            entry_cost=position.entry_cost, entry_ms=position.entry_ms,
            stop_px=position.stop_px, mark_px=exit_px, mark_ms=exit_ms,
            unrealized_gross=gross, unrealized_net=net,
            mfe_pct=position.mfe_pct, mae_pct=position.mae_pct,
        ),
        costs=state.costs,
        events=list(state.events),
        result=result,
        clock_ms=state.clock_ms,
        config_hash=state.config_hash,
        input_hash=state.input_hash,
        engine_version=state.engine_version,
        limitations=list(state.limitations),
    )


def manual_exit(state: PaperSessionState) -> PaperSessionState:
    """Cierre manual de la posición por el usuario."""
    if state.status != "abierta" or not state.position.open:
        return state
    config = state.config
    position = state.position
    # Usar la marca actual como precio de salida (vela conocida)
    exit_px = position.mark_px or position.entry_px or 0.0
    exit_ms = position.mark_ms or state.clock_ms or 0
    return _finalize_exit(state, "manual", exit_px, exit_ms)


def restart_session(state: PaperSessionState) -> PaperSessionState:
    """Reinicia la sesión al estado sin_iniciar (sin entrada)."""
    fresh = create_session(
        state.config, state.candles, state.context_candles,
        hypothesis_id=state.config.hypothesis_id,
        hypothesis_version=state.config.hypothesis_version,
        decision=state.config.decision,
        decision_reason=state.config.decision_reason,
    )
    fresh.created_at_ms = state.created_at_ms
    fresh.updated_at_ms = _now_ms()
    return fresh


def stop_session(state: PaperSessionState) -> PaperSessionState:
    """Detiene la sesión sin cerrar la posición (congela estado)."""
    return PaperSessionState(
        session_id=state.session_id,
        created_at_ms=state.created_at_ms,
        updated_at_ms=_now_ms(),
        status="detenida",
        config=state.config,
        candles=state.candles,
        context_candles=state.context_candles,
        cursor=state.cursor,
        position=state.position,
        costs=state.costs,
        events=list(state.events),
        result=state.result,
        clock_ms=state.clock_ms,
        config_hash=state.config_hash,
        input_hash=state.input_hash,
        engine_version=state.engine_version,
        limitations=list(state.limitations),
    )


def session_to_dict(state: PaperSessionState) -> Dict[str, Any]:
    """Serializa la sesión a dict para API/respuesta/almacenamiento."""
    return {
        "session_id": state.session_id,
        "created_at_ms": state.created_at_ms,
        "updated_at_ms": state.updated_at_ms,
        "status": state.status,
        "config": {
            "symbol": state.config.symbol,
            "interval": state.config.interval,
            "direction": state.config.direction,
            "notional_usdt": state.config.notional_usdt,
            "entry_px": state.config.entry_px,
            "stop_px": state.config.stop_px,
            "stop_distance_pct": state.config.stop_distance_pct,
            "horizon_ms": state.config.horizon_ms,
            "fee_bps": state.config.fee_bps,
            "spread_bps": state.config.spread_bps,
            "slippage_bps": state.config.slippage_bps,
            "hypothesis_id": state.config.hypothesis_id,
            "hypothesis_version": state.config.hypothesis_version,
            "decision": state.config.decision,
            "decision_reason": state.config.decision_reason,
        },
        "candles": [
            {
                "open_time_ms": c.open_time_ms, "open": c.open,
                "high": c.high, "low": c.low, "close": c.close,
                "close_time_ms": c.close_time_ms,
            } for c in state.candles
        ],
        "context_candles": [
            {
                "open_time_ms": c.open_time_ms, "open": c.open,
                "high": c.high, "low": c.low, "close": c.close,
                "close_time_ms": c.close_time_ms,
            } for c in state.context_candles
        ],
        "cursor": state.cursor,
        "position": {
            "open": state.position.open,
            "direction": state.position.direction,
            "entry_px": state.position.entry_px,
            "entry_qty": state.position.entry_qty,
            "entry_cost": state.position.entry_cost,
            "entry_ms": state.position.entry_ms,
            "stop_px": state.position.stop_px,
            "mark_px": state.position.mark_px,
            "mark_ms": state.position.mark_ms,
            "unrealized_gross": state.position.unrealized_gross,
            "unrealized_net": state.position.unrealized_net,
            "mfe_pct": state.position.mfe_pct,
            "mae_pct": state.position.mae_pct,
        },
        "costs": {
            "fee_bps": state.costs.fee_bps,
            "spread_bps": state.costs.spread_bps,
            "entry_fees": state.costs.entry_fees,
            "exit_fees": state.costs.exit_fees,
            "entry_spread_slip": state.costs.entry_spread_slip,
            "exit_spread_slip": state.costs.exit_spread_slip,
            "funding": state.costs.funding,
            "friction": state.costs.friction,
        },
        "events": [
            {"at_ms": e.at_ms, "label": e.label, "kind": e.kind,
             "detail": e.detail} for e in state.events
        ],
        "result": (None if state.result is None else {
            "symbol": state.result.symbol,
            "direction": state.result.direction,
            "entry_px": state.result.entry_px,
            "exit_px": state.result.exit_px,
            "entry_ms": state.result.entry_ms,
            "exit_ms": state.result.exit_ms,
            "exit_reason": state.result.exit_reason,
            "exit_executed": state.result.exit_executed,
            "qty": state.result.qty,
            "filled_cost": state.result.filled_cost,
            "gross_pnl": state.result.gross_pnl,
            "fees": state.result.fees,
            "spread_slip": state.result.spread_slip,
            "funding": state.result.funding,
            "friction": state.result.friction,
            "net_pnl": state.result.net_pnl,
            "realized_net": state.result.realized_net,
            "open_at_end": state.result.open_at_end,
        }),
        "clock_ms": state.clock_ms,
        "config_hash": state.config_hash,
        "input_hash": state.input_hash,
        "engine_version": state.engine_version,
        "limitations": list(state.limitations),
    }


def session_from_dict(d: Dict[str, Any]) -> PaperSessionState:
    """Rehidrata una sesión desde dict (persistencia/recarga tras refresco)."""
    cfg = d["config"]
    config = PaperSessionConfig(
        symbol=cfg["symbol"], interval=cfg["interval"],
        direction=cfg["direction"], notional_usdt=cfg["notional_usdt"],
        entry_px=cfg["entry_px"], stop_px=cfg["stop_px"],
        stop_distance_pct=cfg["stop_distance_pct"],
        horizon_ms=cfg["horizon_ms"], fee_bps=cfg["fee_bps"],
        spread_bps=cfg["spread_bps"], slippage_bps=cfg["slippage_bps"],
        hypothesis_id=cfg.get("hypothesis_id"),
        hypothesis_version=cfg.get("hypothesis_version"),
        decision=cfg.get("decision"),
        decision_reason=cfg.get("decision_reason"),
    )
    candles = [PaperCandle(**c) for c in d.get("candles", [])]
    context = [PaperCandle(**c) for c in d.get("context_candles", [])]
    pos = d["position"]
    position = PaperPosition(
        open=pos["open"], direction=pos.get("direction"),
        entry_px=pos.get("entry_px"), entry_qty=pos.get("entry_qty"),
        entry_cost=pos.get("entry_cost"), entry_ms=pos.get("entry_ms"),
        stop_px=pos.get("stop_px"), mark_px=pos.get("mark_px"),
        mark_ms=pos.get("mark_ms"), unrealized_gross=pos.get(
            "unrealized_gross"), unrealized_net=pos.get("unrealized_net"),
        mfe_pct=pos.get("mfe_pct"), mae_pct=pos.get("mae_pct"),
    )
    costs = PaperCosts(
        fee_bps=d["costs"]["fee_bps"], spread_bps=d["costs"]["spread_bps"],
        entry_fees=d["costs"]["entry_fees"], exit_fees=d["costs"]["exit_fees"],
        entry_spread_slip=d["costs"]["entry_spread_slip"],
        exit_spread_slip=d["costs"]["exit_spread_slip"],
        funding=d["costs"]["funding"], friction=d["costs"]["friction"],
    )
    events = [
        PaperEvent(at_ms=e["at_ms"], label=e["label"], kind=e["kind"],
                   detail=e.get("detail")) for e in d.get("events", [])
    ]
    result = None
    if d.get("result") is not None:
        r = d["result"]
        result = PaperTradeResult(
            symbol=r["symbol"], direction=r["direction"],
            entry_px=r["entry_px"], exit_px=r.get("exit_px"),
            entry_ms=r["entry_ms"], exit_ms=r.get("exit_ms"),
            exit_reason=r.get("exit_reason"),
            exit_executed=r.get("exit_executed", False), qty=r["qty"],
            filled_cost=r["filled_cost"], gross_pnl=r["gross_pnl"],
            fees=r["fees"], spread_slip=r["spread_slip"],
            funding=r["funding"], friction=r["friction"],
            net_pnl=r["net_pnl"],
            realized_net=r.get("realized_net"),
            open_at_end=r.get("open_at_end", False),
        )
    return PaperSessionState(
        session_id=d["session_id"], created_at_ms=d["created_at_ms"],
        updated_at_ms=d["updated_at_ms"], status=d["status"],
        config=config, candles=candles, context_candles=context,
        cursor=d["cursor"], position=position, costs=costs,
        events=events, result=result, clock_ms=d.get("clock_ms"),
        config_hash=d.get("config_hash"), input_hash=d.get("input_hash"),
        engine_version=d.get("engine_version", ENGINE_VERSION_PAPER),
        limitations=list(d.get("limitations", [])),
    )


# --- Persistencia (directorio aislado, fuera de datos operacionales) -----

def _sessions_dir(root: str | Path) -> Path:
    return Path(root) / SESSION_DIR_NAME


def _session_path(sessions_dir: Path, session_id: str) -> Path:
    _safe_session_id(session_id)
    return sessions_dir / f"{session_id}.json"


def save_session(state: PaperSessionState,
                 root: str | Path = ".") -> None:
    """Guarda la sesión de forma atómica en el directorio aislado."""
    sessions_dir = _sessions_dir(root)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = _session_path(sessions_dir, state.session_id)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(session_to_dict(state), indent=1, default=str)
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def load_session(session_id: str,
                 root: str | Path = ".") -> Optional[PaperSessionState]:
    """Carga una sesión completa por ID. Devuelve None si no existe."""
    sessions_dir = _sessions_dir(root)
    path = _session_path(sessions_dir, session_id)
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return session_from_dict(d)
    except Exception:
        return None


def list_sessions(root: str | Path = ".") -> List[Dict[str, Any]]:
    """Lista resúmenes de sesiones (sin velas completas ni eventos)."""
    sessions_dir = _sessions_dir(root)
    if not sessions_dir.exists():
        return []
    summaries: List[Dict[str, Any]] = []
    for f in sorted(sessions_dir.iterdir(), key=lambda p: p.name,
                    reverse=True):
        if not f.is_file() or not f.name.endswith(".json"):
            continue
        if f.name.endswith(".json.tmp"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            cfg = d.get("config", {})
            summaries.append({
                "session_id": d.get("session_id", f.stem),
                "status": d.get("status", "desconocido"),
                "created_at_ms": d.get("created_at_ms", 0),
                "updated_at_ms": d.get("updated_at_ms", 0),
                "symbol": cfg.get("symbol", "—"),
                "direction": cfg.get("direction", "—"),
                "config_hash": d.get("config_hash"),
                "has_result": d.get("result") is not None,
            })
        except Exception:
            summaries.append({
                "session_id": f.stem,
                "status": "ilegible",
                "created_at_ms": 0,
                "updated_at_ms": 0,
                "symbol": "—",
                "direction": "—",
                "config_hash": None,
                "has_result": False,
            })
    return summaries
