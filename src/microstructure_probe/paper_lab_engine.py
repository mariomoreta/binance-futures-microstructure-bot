"""Paper Lab motor de ingeniería — orquestación incremental sobre fixtures.

Backend como fuente de verdad. La mecánica económica (entradas, salidas,
costes, funding, stops, horizonte) se delega a
``microstructure_probe.backtest_offline.run_backtest`` para no crear un
segundo motor económico independiente. El navegador solicita acciones
acotadas y presenta estados recibidos.

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

ENGINE_VERSION_PAPER = "paper-lab-engine/v1.1"
SESSION_DIR_NAME = "paper-lab-sessions"

# Estados de sesión (ingeniería) --------------------------------------------
# sin_iniciar → evaluando → en_espera → abierta → cerrada | detenida
#   - sin_iniciar: creada, aún no se evaluó evidencia.
#   - evaluando: se está evaluando la evidencia en T (acción pública).
#   - en_espera: decisión ENTRADA_SIMULADA tomada, entrada no ejecutada.
#   - abierta: posición abierta, pendiente de salida.
#   - cerrada: escenario terminado (salida ejecutada O fin de datos con
#              posición abierta/no realizada).
#   - detenida: detenida por el usuario, posición congelada.
SessionStatus = str
CandidateDecision = str  # VIGILANDO / SIN_ENTRADA / DESCARTADO / ENTRADA_SIMULADA


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


# --- Tipos de datos --------------------------------------------------------

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
    entry_fees: float = 0.0      # ejecutados
    exit_fees: float = 0.0       # ejecutados (0 si no hay salida)
    entry_spread_slip: float = 0.0  # ejecutados
    exit_spread_slip: float = 0.0   # ejecutados (0 si no hay salida)
    funding: Optional[float] = None   # devengado (None = UNKNOWN sin calendario)
    friction: float = 0.0           # total (entry + exit ejecutados + funding)
    # Costes separados: ejecutados vs hipotéticos de salida
    entry_fees_executed: float = 0.0
    exit_fees_executed: float = 0.0
    entry_spread_slip_executed: float = 0.0
    exit_spread_slip_executed: float = 0.0
    exit_fees_estimated: float = 0.0  # hipotéticos salida (no ejecutados)
    exit_spread_slip_estimated: float = 0.0  # hipotéticos salida


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
    fees: float           # ejecutados (entry + exit si ejecutado)
    spread_slip: float    # ejecutados
    funding: Optional[float]  # devengado (None = UNKNOWN)
    friction: float       # total ejecutado
    net_pnl: float
    realized_net: Optional[float]  # None si no ejecutado
    open_at_end: bool
    # Costes separados: ejecutados vs hipotéticos salida
    entry_fees_executed: float
    exit_fees_executed: float
    entry_spread_slip_executed: float
    exit_spread_slip_executed: float
    exit_fees_estimated: float
    exit_spread_slip_estimated: float


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
    hypothesis_id: Optional[str] = None
    hypothesis_version: Optional[str] = None
    rule_version: Optional[str] = None  # regla experimental versionada
    decision: Optional[CandidateDecision] = None
    decision_reason: Optional[str] = None
    decision_evidence: Optional[Dict[str, Any]] = None  # evidencia en T


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
    config_hash: Optional[str] = None
    input_hash: Optional[str] = None
    engine_version: str = ENGINE_VERSION_PAPER
    limitations: List[str] = field(default_factory=list)
    revision: int = 0  # idempotencia: se incrementa en cada modificación
    authoritative: Optional[Dict[str, Any]] = None  # resultado run_backtest


# --- Adaptador a backtest_offline.run_backtest (mecánica compartida) -------

def _build_study_event(state: PaperSessionState) -> StudyEvent:
    """Construye un StudyEvent a partir de la configuración de sesión."""
    config = state.config
    return StudyEvent(
        symbol=config.symbol,
        event_time_ms=state.clock_ms or config.entry_px and 0 or 0,
        direction=config.direction,
        reference_price=config.entry_px,
        family="H1",
        rules_version="H1-v1",
    )


def _build_backtest_config(state: PaperSessionState) -> BacktestConfig:
    """Construye un BacktestConfig a partir de la configuración de sesión.

    No se inyecta FundingCalendar a menos que exista uno real: si no hay
    calendario de funding, run_backtest usaría el fallback sintético (8h).
    Para cumplir "funding ausente = UNKNOWN", no se pasa calendario y el
    resultado se sobrescribe después.
    """
    config = state.config
    return BacktestConfig(
        family="H1",
        rules_version="H1-v1",
        exit_horizon_ms=config.horizon_ms,
        stop_distance_pct=config.stop_distance_pct,
        notional_usdt=config.notional_usdt,
        fee_bps=config.fee_bps,
        spread_bps=config.spread_bps,
        slippage_bps=config.slippage_bps,
        cost_scale=1.0,
        max_concurrent=1,
        funding_calendar=None,  # sin calendario real → funding = UNKNOWN
        funding_estimated_bps=None,  # contexto solo, nunca contabiliza
    )


def _to_bt_candles(candles: List[PaperCandle]) -> List[Candle]:
    return [
        Candle(
            symbol=c.context_candles and "UNKNOWN" or "PL",  # placeholder, se fija abajo
            open_time_ms=c.open_time_ms,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            close_time_ms=c.close_time_ms,
        )
        for c in candles
    ]


def _run_backtest_authoritative(
    state: PaperSessionState, symbol: str,
) -> Optional[Dict[str, Any]]:
    """Ejecuta run_backtest sobre las velas de la sesión y devuelve el
    resultado autoritativo (primera trade admitida o None).

    Esta es la fuente de verdad económica: entradas, salidas, costes,
    funding, stops y horizonte se derivan de run_backtest, no de lógica
    duplicada en este módulo.
    """
    config = state.config
    candles = state.candles
    if not candles:
        return None

    # run_backtest requiere c.open_time_ms > ev.event_time_ms para el fill.
    # El evento (detección) ocurre antes de la primera vela de la ventana.
    event_time_ms = candles[0].open_time_ms - 1 if candles else 0

    event = StudyEvent(
        symbol=symbol,
        event_time_ms=event_time_ms,
        direction=config.direction,
        reference_price=config.entry_px,
        family="H1",
        rules_version="H1-v1",
    )
    bt_config = _build_backtest_config(state)
    bt_candles = [
        Candle(
            symbol=symbol,
            open_time_ms=c.open_time_ms,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            close_time_ms=c.close_time_ms,
        )
        for c in candles
    ]

    result = run_backtest(
        [event], bt_candles, bt_config,
        dataset_id="paper-lab-fixture", segment="dev",
    )

    trades = result.get("trades", [])
    if not trades:
        return None
    return trades[0]


def _map_bt_trade_to_paper_result(
    bt_trade: Dict[str, Any],
    state: PaperSessionState,
) -> PaperTradeResult:
    """Mapea un trade dict de run_backtest a PaperTradeResult.

    Separa costes ejecutados de estimaciones de salida y marca funding como
    UNKNOWN (None) cuando no hubo calendario real.
    """
    config = state.config
    funding = bt_trade.get("funding")
    funding_model = bt_trade.get("funding_model")
    # Funding ausente (sin calendario real) → UNKNOWN, no cero por defecto.
    if funding_model != "settlement-calendar":
        funding = None

    exit_fees_executed = bt_trade.get("exit_fees", 0.0) if bt_trade.get("exit_executed") else 0.0
    exit_spread_slip_executed = bt_trade.get("exit_spread_slip", 0.0) if bt_trade.get("exit_executed") else 0.0
    exit_fees_estimated = bt_trade.get("exit_fees", 0.0) if not bt_trade.get("exit_executed") else 0.0
    exit_spread_slip_estimated = bt_trade.get("exit_spread_slip", 0.0) if not bt_trade.get("exit_executed") else 0.0

    # Friction ejecutado: entry fees + entry spread/slip + (exit fees si ejecutado) + funding
    entry_fees_executed = bt_trade.get("entry_fees", 0.0)
    entry_spread_slip_executed = bt_trade.get("entry_spread_slip", 0.0)
    friction_executed = (
        entry_fees_executed + exit_fees_executed +
        entry_spread_slip_executed + exit_spread_slip_executed
    )
    if funding is not None:
        friction_executed += funding

    return PaperTradeResult(
        symbol=bt_trade["symbol"],
        direction=bt_trade["direction"],
        entry_px=bt_trade["entry_px"],
        exit_px=bt_trade.get("exit_px"),
        entry_ms=bt_trade["entry_ms"],
        exit_ms=bt_trade.get("exit_ms"),
        exit_reason=bt_trade.get("exit_reason"),
        exit_executed=bt_trade.get("exit_executed", False),
        qty=bt_trade["filled_qty"],
        filled_cost=bt_trade["filled_cost"],
        gross_pnl=bt_trade["gross_pnl"],
        fees=bt_trade.get("fees", 0.0) if bt_trade.get("exit_executed") else entry_fees_executed,
        spread_slip=bt_trade.get("spread_slip_cost", 0.0) if bt_trade.get("exit_executed") else entry_spread_slip_executed,
        funding=funding,
        friction=friction_executed,
        net_pnl=bt_trade["net_pnl"],
        realized_net=bt_trade.get("realized_net"),
        open_at_end=bt_trade.get("open_at_end", False),
        entry_fees_executed=entry_fees_executed,
        exit_fees_executed=exit_fees_executed,
        entry_spread_slip_executed=entry_spread_slip_executed,
        exit_spread_slip_executed=exit_spread_slip_executed,
        exit_fees_estimated=exit_fees_estimated,
        exit_spread_slip_estimated=exit_spread_slip_estimated,
    )


# --- Sesión ----------------------------------------------------------------

def create_session(
    config: PaperSessionConfig,
    candles: List[PaperCandle],
    context_candles: List[PaperCandle] = None,
    hypothesis_id: Optional[str] = None,
    hypothesis_version: Optional[str] = None,
    rule_version: Optional[str] = None,
) -> PaperSessionState:
    """Crea una sesión de ingeniería en estado sin_iniciar.

    No ejecuta entrada ni acepta decisión del cliente: solo prepara el
    escenario. La decisión se obtiene posteriormente mediante evaluate_session.
    """
    if context_candles is None:
        context_candles = []
    entry_fees = config.notional_usdt * (config.fee_bps / 10000.0)
    entry_spread_slip = config.notional_usdt * (
        (config.spread_bps + config.slippage_bps) / 10000.0
    )
    now = _now_ms()
    session_id = _new_session_id(config.symbol, config.direction)

    cfg_dict = {
        "symbol": config.symbol, "interval": config.interval,
        "direction": config.direction, "notional_usdt": config.notional_usdt,
        "entry_px": config.entry_px, "stop_px": config.stop_px,
        "stop_distance_pct": config.stop_distance_pct,
        "horizon_ms": config.horizon_ms, "fee_bps": config.fee_bps,
        "spread_bps": config.spread_bps, "slippage_bps": config.slippage_bps,
        "hypothesis_id": hypothesis_id,
        "hypothesis_version": hypothesis_version,
        "rule_version": rule_version,
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
            rule_version=rule_version,
            decision=None,
            decision_reason=None,
            decision_evidence=None,
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
            funding=None,  # UNKNOWN hasta que se evalúe con calendario real
            friction=entry_fees + entry_spread_slip,
            exit_fees_estimated=0.0,
            exit_spread_slip_estimated=0.0,
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
        revision=0,
        authoritative=None,
    )
    return session


def evaluate_session(
    state: PaperSessionState,
    hypothesis_id: Optional[str] = None,
    hypothesis_version: Optional[str] = None,
    rule_version: Optional[str] = None,
) -> PaperSessionState:
    """Evalúa la evidencia disponible en T y retorna una decisión.

    Usa run_backtest como autoridad económica: si se admite una operación
    → ENTRADA_SIMULADA y se avanza a en_espera. Si no se admite → SIN_ENTRADA
    o DESCARTADO con motivo registrado, sin abrir posición.

    Transiciones:
      sin_iniciar → evaluando → en_espera (ENTRADA_SIMULADA)
      sin_iniciar → evaluando → cerrada (SIN_ENTRADA / DESCARTADO, sin posición)
    """
    if state.status not in ("sin_iniciar", "evaluando"):
        return state

    next_state = PaperSessionState(
        session_id=state.session_id,
        created_at_ms=state.created_at_ms,
        updated_at_ms=_now_ms(),
        status="evaluando",
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
        revision=state.revision + 1,
        authoritative=None,
    )

    # Ejecutar run_backtest para decidir si la entrada es admisible.
    bt_result = _run_backtest_authoritative(next_state, next_state.config.symbol)

    evidence: Dict[str, Any] = {
        "evaluated_at_ms": _now_ms(),
        "rule_version": rule_version,
        "n_candles": len(next_state.candles),
        "horizon_ms": next_state.config.horizon_ms,
        "stop_distance_pct": next_state.config.stop_distance_pct,
    }

    if bt_result is None:
        # No se admitió ninguna operación. run_backtest ya filtró por
        # familia/regla/horizonte; si no hay trade, no hay fill posible
        # con los datos disponibles → SIN_ENTRADA.
        decision = "SIN_ENTRADA"
        reason = "No hay fill posible con los datos disponibles: run_backtest no admitió ninguna operación."

        next_state = PaperSessionState(
            session_id=next_state.session_id,
            created_at_ms=next_state.created_at_ms,
            updated_at_ms=_now_ms(),
            status="cerrada",
            config=PaperSessionConfig(
                symbol=next_state.config.symbol,
                interval=next_state.config.interval,
                direction=next_state.config.direction,
                notional_usdt=next_state.config.notional_usdt,
                entry_px=next_state.config.entry_px,
                stop_px=next_state.config.stop_px,
                stop_distance_pct=next_state.config.stop_distance_pct,
                horizon_ms=next_state.config.horizon_ms,
                fee_bps=next_state.config.fee_bps,
                spread_bps=next_state.config.spread_bps,
                slippage_bps=next_state.config.slippage_bps,
                hypothesis_id=hypothesis_id,
                hypothesis_version=hypothesis_version,
                rule_version=rule_version,
                decision=decision,
                decision_reason=reason,
                decision_evidence=evidence,
            ),
            candles=next_state.candles,
            context_candles=next_state.context_candles,
            cursor=next_state.cursor,
            position=next_state.position,
            costs=next_state.costs,
            events=list(next_state.events) + [
                PaperEvent(
                    at_ms=_now_ms(),
                    label=f"Decisión: {decision}",
                    kind="protection",
                    detail=reason,
                )
            ],
            result=None,
            clock_ms=next_state.clock_ms,
            config_hash=next_state.config_hash,
            input_hash=next_state.input_hash,
            engine_version=next_state.engine_version,
            limitations=list(next_state.limitations),
            revision=next_state.revision + 1,
            authoritative=None,
        )
        return next_state

    # Operación admitida → ENTRADA_SIMULADA, avanzar a en_espera.
    entry_px = bt_result["entry_px"]
    entry_ms = bt_result["entry_ms"]
    qty = bt_result["filled_qty"]
    entry_cost = bt_result["filled_cost"]

    entry_fees = bt_result.get("entry_fees", 0.0)
    entry_spread_slip = bt_result.get("entry_spread_slip", 0.0)

    next_state = PaperSessionState(
        session_id=next_state.session_id,
        created_at_ms=next_state.created_at_ms,
        updated_at_ms=_now_ms(),
        status="en_espera",
        config=PaperSessionConfig(
            symbol=next_state.config.symbol,
            interval=next_state.config.interval,
            direction=next_state.config.direction,
            notional_usdt=next_state.config.notional_usdt,
            entry_px=entry_px,
            stop_px=next_state.config.stop_px,
            stop_distance_pct=next_state.config.stop_distance_pct,
            horizon_ms=next_state.config.horizon_ms,
            fee_bps=next_state.config.fee_bps,
            spread_bps=next_state.config.spread_bps,
            slippage_bps=next_state.config.slippage_bps,
            hypothesis_id=hypothesis_id,
            hypothesis_version=hypothesis_version,
            rule_version=rule_version,
            decision="ENTRADA_SIMULADA",
            decision_reason="run_backtest admitió la operación: entrada ejecutable tras el evento en T.",
            decision_evidence=evidence,
        ),
        candles=next_state.candles,
        context_candles=next_state.context_candles,
        cursor=0,
        position=next_state.position,
        costs=PaperCosts(
            fee_bps=next_state.config.fee_bps,
            spread_bps=next_state.config.spread_bps,
            entry_fees=entry_fees,
            exit_fees=0.0,
            entry_spread_slip=entry_spread_slip,
            exit_spread_slip=0.0,
            funding=None,
            friction=entry_fees + entry_spread_slip,
            exit_fees_estimated=0.0,
            exit_spread_slip_estimated=0.0,
        ),
        events=list(next_state.events) + [
            PaperEvent(
                at_ms=entry_ms,
                label=f"Decisión: ENTRADA_SIMULADA @ {entry_px:.2f}",
                kind="protection",
                detail=(f"qty={qty:.8f} notional={next_state.config.notional_usdt} "
                        f"entry_ms={entry_ms} rule={rule_version}"),
            )
        ],
        result=None,
        clock_ms=entry_ms,
        config_hash=next_state.config_hash,
        input_hash=next_state.input_hash,
        engine_version=next_state.engine_version,
        limitations=list(next_state.limitations),
        revision=next_state.revision + 1,
        authoritative=bt_result,
    )
    return next_state


def _apply_entry(state: PaperSessionState) -> PaperSessionState:
    """Ejecuta la entrada en la vela actual (cursor) usando la autoridad de
    run_backtest (state.authoritative). No duplica si ya hay posición."""
    if state.position.open:
        return state
    config = state.config
    candles = state.candles
    cursor = state.cursor
    if cursor < 0 or cursor >= len(candles):
        return state
    candle = candles[cursor]

    # Usar la entrada autoritativa de run_backtest si existe.
    bt = state.authoritative
    entry_px = bt["entry_px"] if bt else config.entry_px
    entry_ms = bt["entry_ms"] if bt else (candle.close_time_ms or candle.open_time_ms)
    qty = bt["filled_qty"] if bt else (config.notional_usdt / entry_px)
    filled_cost = bt["filled_cost"] if bt else (entry_px * qty)
    entry_fees = bt.get("entry_fees", 0.0) if bt else config.notional_usdt * (config.fee_bps / 10000.0)
    entry_spread_slip = bt.get("entry_spread_slip", 0.0) if bt else config.notional_usdt * (
        (config.spread_bps + config.slippage_bps) / 10000.0
    )

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
            entry_fees=entry_fees, exit_fees=0.0,
            entry_spread_slip=entry_spread_slip, exit_spread_slip=0.0,
            funding=None,
            friction=entry_fees + entry_spread_slip,
            entry_fees_executed=entry_fees,
            exit_fees_executed=0.0,
            entry_spread_slip_executed=entry_spread_slip,
            exit_spread_slip_executed=0.0,
            exit_fees_estimated=0.0,
            exit_spread_slip_estimated=0.0,
        ),
        events=list(state.events) + [
            PaperEvent(
                at_ms=entry_ms,
                label=f"Entrada {config.direction} @ {entry_px:.2f}",
                kind="entry",
                detail=(f"qty={qty:.8f} notional={config.notional_usdt} "
                        f"stop={config.stop_px} source={'run_backtest' if bt else 'config'}"),
            )
        ],
        result=None,
        clock_ms=entry_ms,
        config_hash=state.config_hash,
        input_hash=state.input_hash,
        engine_version=state.engine_version,
        limitations=list(state.limitations),
        revision=state.revision + 1,
        authoritative=state.authoritative,
    )
    return next_state


def step_forward(state: PaperSessionState) -> PaperSessionState:
    """Avanza un paso (vela cerrada conocida), actualiza marca y evalúa salida.

    Reglas causales (mecánica compartida con run_backtest):
    - Solo velas cerradas conocidas hasta el cursor.
    - La entrada se ejecuta al pasar de en_espera a abierta (primer paso).
    - La salida (stop/horizon) se confirma con la autoridad de run_backtest.
    - Fin de datos sin salida: posición permanece abierta (open_at_end), no
      se inventa cierre ni comisión de salida.
    """
    if state.status in ("cerrada", "detenida"):
        return state

    # Si está en_espera, el primer paso ejecuta la entrada.
    if state.status == "en_espera" and not state.position.open:
        return _apply_entry(state)

    config = state.config
    candles = state.candles
    n = len(candles)
    next_cursor = min(n, state.cursor + 1)
    candle = candles[next_cursor - 1] if next_cursor > 0 else None
    clock_ms = (candle.close_time_ms if candle and candle.close_time_ms
                is not None else candle.open_time_ms) if candle else None

    # Estado base del paso siguiente.
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
        revision=state.revision + 1,
        authoritative=state.authoritative,
    )

    # Si hay posición abierta, actualizar marca y evaluar salida con run_backtest.
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

        # Costes ejecutados hasta ahora (sin salida ejecutada aún).
        entry_fees_executed = next_state.costs.entry_fees_executed
        entry_spread_slip_executed = next_state.costs.entry_spread_slip_executed
        friction_executed = entry_fees_executed + entry_spread_slip_executed
        unrealized_net = gross - friction_executed

        # Reemplazar evento de marca anterior.
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
                exit_fees=0.0,
                entry_spread_slip=next_state.costs.entry_spread_slip,
                exit_spread_slip=0.0,
                funding=None,
                friction=friction_executed,
                entry_fees_executed=entry_fees_executed,
                exit_fees_executed=0.0,
                entry_spread_slip_executed=entry_spread_slip_executed,
                exit_spread_slip_executed=0.0,
                exit_fees_estimated=0.0,
                exit_spread_slip_estimated=0.0,
            ),
            events=events,
            result=next_state.result,
            clock_ms=next_state.clock_ms,
            config_hash=next_state.config_hash,
            input_hash=next_state.input_hash,
            engine_version=next_state.engine_version,
            limitations=list(next_state.limitations),
            revision=next_state.revision,
            authoritative=next_state.authoritative,
        )

        # Evaluar salida con la autoridad de run_backtest.
        bt = next_state.authoritative
        if bt and bt.get("exit_executed"):
            exit_ms = bt.get("exit_ms")
            exit_px = bt.get("exit_px")
            if exit_ms is not None and clock_ms is not None and clock_ms >= exit_ms:
                return _finalize_exit_from_bt(next_state, bt)

    # Agotamiento de datos sin salida ejecutada → posición permanece abierta.
    if (next_cursor >= n and next_state.position.open
            and next_state.result is None):
        return _finalize_open_at_end(next_state)

    return next_state


def _finalize_exit_from_bt(
    state: PaperSessionState, bt: Dict[str, Any],
) -> PaperSessionState:
    """Finaliza la sesión con salida ejecutada usando el resultado de
    run_backtest (mecánica compartida). Costes ejecutados consistentes."""
    config = state.config
    position = state.position
    entry_px = position.entry_px or 0.0
    qty = position.entry_qty or 0.0

    exit_px = bt.get("exit_px", 0.0)
    exit_ms = bt.get("exit_ms", 0)
    exit_reason = bt.get("exit_reason", "desconocido")

    gross = _gross_pnl(config.direction, entry_px, exit_px, qty)
    entry_fees_executed = bt.get("entry_fees", 0.0)
    entry_spread_slip_executed = bt.get("entry_spread_slip", 0.0)
    exit_fees_executed = bt.get("exit_fees", 0.0)
    exit_spread_slip_executed = bt.get("exit_spread_slip", 0.0)
    funding = bt.get("funding")
    if bt.get("funding_model") != "settlement-calendar":
        funding = None  # UNKNOWN sin calendario real

    friction_executed = (
        entry_fees_executed + exit_fees_executed +
        entry_spread_slip_executed + exit_spread_slip_executed
    )
    if funding is not None:
        friction_executed += funding
    net = gross - friction_executed

    events = list(state.events)
    events.append(PaperEvent(
        at_ms=exit_ms,
        label=f"Salida {exit_reason} @ {exit_px:.2f}",
        kind="exit",
        detail=f"razon={exit_reason} P&L neto={net:.2f} (run_backtest)",
    ))

    result = PaperTradeResult(
        symbol=config.symbol, direction=config.direction,
        entry_px=entry_px, exit_px=exit_px,
        entry_ms=position.entry_ms or 0, exit_ms=exit_ms,
        exit_reason=exit_reason, exit_executed=True, qty=qty,
        filled_cost=position.entry_cost or 0.0,
        gross_pnl=gross,
        fees=entry_fees_executed + exit_fees_executed,
        spread_slip=entry_spread_slip_executed + exit_spread_slip_executed,
        funding=funding,
        friction=friction_executed,
        net_pnl=net,
        realized_net=net,
        open_at_end=False,
        entry_fees_executed=entry_fees_executed,
        exit_fees_executed=exit_fees_executed,
        entry_spread_slip_executed=entry_spread_slip_executed,
        exit_spread_slip_executed=exit_spread_slip_executed,
        exit_fees_estimated=0.0,
        exit_spread_slip_estimated=0.0,
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
            entry_fees=entry_fees_executed,
            exit_fees=exit_fees_executed,
            entry_spread_slip=entry_spread_slip_executed,
            exit_spread_slip=exit_spread_slip_executed,
            funding=funding,
            friction=friction_executed,
            entry_fees_executed=entry_fees_executed,
            exit_fees_executed=exit_fees_executed,
            entry_spread_slip_executed=entry_spread_slip_executed,
            exit_spread_slip_executed=exit_spread_slip_executed,
            exit_fees_estimated=0.0,
            exit_spread_slip_estimated=0.0,
        ),
        events=events,
        result=result,
        clock_ms=exit_ms,
        config_hash=state.config_hash,
        input_hash=state.input_hash,
        engine_version=state.engine_version,
        limitations=list(state.limitations),
        revision=state.revision + 1,
        authoritative=state.authoritative,
    )


def _finalize_open_at_end(state: PaperSessionState) -> PaperSessionState:
    """Agotamiento de datos: posición permanece abierta y no realizada.

    El escenario pasa a cerrada (no hay más velas) pero la posición sigue
    abierta. No se inventa cierre, ni comisión de salida, ni marcador de
    cierre. El resultado tiene open_at_end=True y exit_executed=False.
    """
    config = state.config
    position = state.position
    entry_px = position.entry_px or 0.0
    qty = position.entry_qty or 0.0
    exit_px = position.mark_px
    exit_ms = position.mark_ms

    gross = _gross_pnl(config.direction, entry_px, exit_px or entry_px,
                       qty) if exit_px is not None else 0.0
    # Sin costes de salida (no ejecutada): solo costes de entrada ejecutados.
    friction_executed = (
        state.costs.entry_fees_executed +
        state.costs.entry_spread_slip_executed
    )
    net = gross - friction_executed if exit_px is not None else 0.0

    result = PaperTradeResult(
        symbol=config.symbol, direction=config.direction,
        entry_px=entry_px, exit_px=exit_px,
        entry_ms=position.entry_ms or 0, exit_ms=exit_ms,
        exit_reason=None, exit_executed=False, qty=qty,
        filled_cost=position.entry_cost or 0.0,
        gross_pnl=gross,
        fees=state.costs.entry_fees_executed,
        spread_slip=state.costs.entry_spread_slip_executed,
        funding=None,  # UNKNOWN
        friction=friction_executed,
        net_pnl=net,
        realized_net=None,  # no realizado
        open_at_end=True,
        entry_fees_executed=state.costs.entry_fees_executed,
        exit_fees_executed=0.0,
        entry_spread_slip_executed=state.costs.entry_spread_slip_executed,
        exit_spread_slip_executed=0.0,
        exit_fees_estimated=0.0,
        exit_spread_slip_estimated=0.0,
    )

    return PaperSessionState(
        session_id=state.session_id,
        created_at_ms=state.created_at_ms,
        updated_at_ms=_now_ms(),
        status="cerrada",  # escenario terminado, pero posición sigue abierta
        config=state.config,
        candles=state.candles,
        context_candles=state.context_candles,
        cursor=state.cursor,
        position=PaperPosition(
            open=True,  # posición sigue abierta
            direction=position.direction,
            entry_px=position.entry_px, entry_qty=position.entry_qty,
            entry_cost=position.entry_cost, entry_ms=position.entry_ms,
            stop_px=position.stop_px, mark_px=exit_px, mark_ms=exit_ms,
            unrealized_gross=gross, unrealized_net=net,
            mfe_pct=position.mfe_pct, mae_pct=position.mae_pct,
        ),
        costs=PaperCosts(
            fee_bps=state.costs.fee_bps,
            spread_bps=state.costs.spread_bps,
            entry_fees=state.costs.entry_fees_executed,
            exit_fees=0.0,
            entry_spread_slip=state.costs.entry_spread_slip_executed,
            exit_spread_slip=0.0,
            funding=None,
            friction=friction_executed,
            entry_fees_executed=state.costs.entry_fees_executed,
            exit_fees_executed=0.0,
            entry_spread_slip_executed=state.costs.entry_spread_slip_executed,
            exit_spread_slip_executed=0.0,
            exit_fees_estimated=0.0,
            exit_spread_slip_estimated=0.0,
        ),
        events=list(state.events),
        result=result,
        clock_ms=state.clock_ms,
        config_hash=state.config_hash,
        input_hash=state.input_hash,
        engine_version=state.engine_version,
        limitations=list(state.limitations),
        revision=state.revision + 1,
        authoritative=state.authoritative,
    )


def manual_exit(state: PaperSessionState) -> PaperSessionState:
    """Cierre manual de la posición por el usuario.

    Distingue una intervención manual de una entrada automática; la manual
    no sustituye la aceptación por run_backtest. Usa la marca actual como
    precio de salida y costes ejecutados de la mecánica compartida.
    """
    if state.status != "abierta" or not state.position.open:
        return state
    config = state.config
    position = state.position
    exit_px = position.mark_px or position.entry_px or 0.0
    exit_ms = position.mark_ms or state.clock_ms or 0

    entry_px = position.entry_px or 0.0
    qty = position.entry_qty or 0.0
    gross = _gross_pnl(config.direction, entry_px, exit_px, qty)
    entry_fees_executed = state.costs.entry_fees_executed
    entry_spread_slip_executed = state.costs.entry_spread_slip_executed
    exit_fees_executed = exit_px * qty * (config.fee_bps / 10000.0)
    exit_spread_slip_executed = exit_px * qty * (
        (config.spread_bps + config.slippage_bps) / 10000.0
    )
    friction_executed = (
        entry_fees_executed + exit_fees_executed +
        entry_spread_slip_executed + exit_spread_slip_executed
    )
    net = gross - friction_executed

    events = list(state.events)
    events.append(PaperEvent(
        at_ms=exit_ms,
        label=f"Cierre manual @ {exit_px:.2f}",
        kind="exit",
        detail=f"razon=manual P&L neto={net:.2f}",
    ))

    result = PaperTradeResult(
        symbol=config.symbol, direction=config.direction,
        entry_px=entry_px, exit_px=exit_px,
        entry_ms=position.entry_ms or 0, exit_ms=exit_ms,
        exit_reason="manual", exit_executed=True, qty=qty,
        filled_cost=position.entry_cost or 0.0,
        gross_pnl=gross,
        fees=entry_fees_executed + exit_fees_executed,
        spread_slip=entry_spread_slip_executed + exit_spread_slip_executed,
        funding=None,
        friction=friction_executed,
        net_pnl=net,
        realized_net=net,
        open_at_end=False,
        entry_fees_executed=entry_fees_executed,
        exit_fees_executed=exit_fees_executed,
        entry_spread_slip_executed=entry_spread_slip_executed,
        exit_spread_slip_executed=exit_spread_slip_executed,
        exit_fees_estimated=0.0,
        exit_spread_slip_estimated=0.0,
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
            entry_fees=entry_fees_executed,
            exit_fees=exit_fees_executed,
            entry_spread_slip=entry_spread_slip_executed,
            exit_spread_slip=exit_spread_slip_executed,
            funding=None,
            friction=friction_executed,
            entry_fees_executed=entry_fees_executed,
            exit_fees_executed=exit_fees_executed,
            entry_spread_slip_executed=entry_spread_slip_executed,
            exit_spread_slip_executed=exit_spread_slip_executed,
            exit_fees_estimated=0.0,
            exit_spread_slip_estimated=0.0,
        ),
        events=events,
        result=result,
        clock_ms=exit_ms,
        config_hash=state.config_hash,
        input_hash=state.input_hash,
        engine_version=state.engine_version,
        limitations=list(state.limitations),
        revision=state.revision + 1,
        authoritative=state.authoritative,
    )


def restart_session(state: PaperSessionState) -> PaperSessionState:
    """Reinicia la sesión al estado sin_iniciar (sin entrada)."""
    fresh = create_session(
        state.config, state.candles, state.context_candles,
        hypothesis_id=state.config.hypothesis_id,
        hypothesis_version=state.config.hypothesis_version,
        rule_version=state.config.rule_version,
    )
    fresh.created_at_ms = state.created_at_ms
    fresh.updated_at_ms = _now_ms()
    fresh.revision = state.revision + 1
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
        revision=state.revision + 1,
        authoritative=state.authoritative,
    )


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


# --- Serialización ---------------------------------------------------------

def session_to_dict(state: PaperSessionState) -> Dict[str, Any]:
    """Serializa la sesión a dict para API/respuesta/almacenamiento."""
    return {
        "session_id": state.session_id,
        "created_at_ms": state.created_at_ms,
        "updated_at_ms": state.updated_at_ms,
        "status": state.status,
        "revision": state.revision,
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
            "rule_version": state.config.rule_version,
            "decision": state.config.decision,
            "decision_reason": state.config.decision_reason,
            "decision_evidence": state.config.decision_evidence,
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
            "entry_fees_executed": state.costs.entry_fees_executed,
            "exit_fees_executed": state.costs.exit_fees_executed,
            "entry_spread_slip_executed": state.costs.entry_spread_slip_executed,
            "exit_spread_slip_executed": state.costs.exit_spread_slip_executed,
            "exit_fees_estimated": state.costs.exit_fees_estimated,
            "exit_spread_slip_estimated": state.costs.exit_spread_slip_estimated,
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
            "entry_fees_executed": state.result.entry_fees_executed,
            "exit_fees_executed": state.result.exit_fees_executed,
            "entry_spread_slip_executed": state.result.entry_spread_slip_executed,
            "exit_spread_slip_executed": state.result.exit_spread_slip_executed,
            "exit_fees_estimated": state.result.exit_fees_estimated,
            "exit_spread_slip_estimated": state.result.exit_spread_slip_estimated,
        }),
        "clock_ms": state.clock_ms,
        "config_hash": state.config_hash,
        "input_hash": state.input_hash,
        "engine_version": state.engine_version,
        "limitations": list(state.limitations),
        "authoritative": state.authoritative,
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
        rule_version=cfg.get("rule_version"),
        decision=cfg.get("decision"),
        decision_reason=cfg.get("decision_reason"),
        decision_evidence=cfg.get("decision_evidence"),
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
        entry_fees_executed=d["costs"].get("entry_fees_executed",
                                           d["costs"]["entry_fees"]),
        exit_fees_executed=d["costs"].get("exit_fees_executed",
                                          d["costs"]["exit_fees"]),
        entry_spread_slip_executed=d["costs"].get(
            "entry_spread_slip_executed", d["costs"]["entry_spread_slip"]),
        exit_spread_slip_executed=d["costs"].get(
            "exit_spread_slip_executed", d["costs"]["exit_spread_slip"]),
        exit_fees_estimated=d["costs"].get("exit_fees_estimated", 0.0),
        exit_spread_slip_estimated=d["costs"].get(
            "exit_spread_slip_estimated", 0.0),
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
            entry_fees_executed=r.get("entry_fees_executed",
                                      r.get("entry_fees", 0.0)),
            exit_fees_executed=r.get("exit_fees_executed",
                                     r.get("exit_fees", 0.0)),
            entry_spread_slip_executed=r.get(
                "entry_spread_slip_executed",
                r.get("entry_spread_slip", 0.0)),
            exit_spread_slip_executed=r.get(
                "exit_spread_slip_executed",
                r.get("exit_spread_slip", 0.0)),
            exit_fees_estimated=r.get("exit_fees_estimated", 0.0),
            exit_spread_slip_estimated=r.get(
                "exit_spread_slip_estimated", 0.0),
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
        revision=d.get("revision", 0),
        authoritative=d.get("authoritative"),
    )


# --- Persistencia (directorio aislado, fuera de datos operacionales) -----

def _sessions_dir(root: str | Path) -> Path:
    return Path(root) / SESSION_DIR_NAME


def _session_path(sessions_dir: Path, session_id: str) -> Path:
    _safe_session_id(session_id)
    return sessions_dir / f"{session_id}.json"


def save_session(state: PaperSessionState,
                 root: str | Path = ".",
                 expected_revision: Optional[int] = None) -> None:
    """Guarda la sesión de forma atómica con control de revisión.

    Si se pasa expected_revision y no coincide con la revisión almacenada,
    se lanza ValueError (optimistic locking: evitar pérdida de eventos por
    carga→modificar→guardar concurrente).
    """
    sessions_dir = _sessions_dir(root)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = _session_path(sessions_dir, state.session_id)

    # Control de revisión: leer la revisión almacenada si existe.
    if expected_revision is not None and path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored_rev = stored.get("revision", 0)
            if stored_rev != expected_revision:
                raise ValueError(
                    f"REVISION_CONFLICT: almacenada={stored_rev}, "
                    f"esperada={expected_revision}")
        except ValueError:
            raise
        except Exception:
            pass  # si no se puede leer, continuar con escritura atómica

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
                "revision": d.get("revision", 0),
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
                "revision": 0,
                "created_at_ms": 0,
                "updated_at_ms": 0,
                "symbol": "—",
                "direction": "—",
                "config_hash": None,
                "has_result": False,
            })
    return summaries
