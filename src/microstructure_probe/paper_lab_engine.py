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
import sys
import time
import uuid
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

ENGINE_VERSION_PAPER = "paper-lab-engine/v1.2"
SESSION_DIR_NAME = "paper-lab-sessions"

# --- Regla experimental causal, versionada y fijada antes de ejecutar -------
# RULE-CAUSAL-V1: la decision de entrada se toma SOLO con informacion
# disponible en/before T (prefijo conocido). Nunca usa velas futuras,
# existencia de trade, salida, P&L ni comisiones como confirmacion.
# Parametros no optimizados; no se declara ventaja.
RULE_CAUSAL_V1 = "RULE-CAUSAL-V1"

# Identidad de peticion para idempotencia (se inyecta desde el CLI/API).
REQUEST_ID_HEADER = "X-Request-Id"

# --- Politica de frescura real (Item 3) -----------------------------------
# Fin de datos, dato obsoleto y desconexion son escenarios distintos.
# La frescura se juzga contra el reloj de simulacion T (at_ms),
# no contra fechas históricas del calendario.

# Edad maxima admisible de un dato respecto de T (ms). Un dato mas viejo
# que esto se considera obsoleto (stale) respecto de T.
STALE_MAX_AGE_MS = 5 * 60 * 60 * 1000  # 5 horas de tolerancia

# Umbral de desconexión: sin recibo de nuevas velas durante este lapso
# se considera interrupción del feed.
DISCONNECT_MAX_SILENCE_MS = 10 * 60 * 1000  # 10 minutos


def evaluate_freshness_at(
    candles: List[PaperCandle], at_ms: int,
) -> Dict[str, Any]:
    """Evalúa la frescura de los datos respecto al reloj de simulación T.

    Devuelve un diccionario con:
      - fresh: bool, todos los datos conocidos en T son frescos.
      - stale_candles: velas conocidas en T pero obsoletas (received_at
        muy anterior a T o disponible mucho antes sin actualización).
      - disconnect: bool, hay indicio de interrupción del feed (silencio
        prolongado sin recibir nuevas velas).
      - end_of_data: bool, no hay más velas después de T (fin de fixture).
      - newest_received_at: el received_at más reciente entre velas conocidas.
      - reason: motivo legible; evidence: detalles comprobables.
    """
    prefix = _known_prefix_at(candles, at_ms)
    if not prefix:
        return {
            "fresh": False, "stale_candles": [], "disconnect": False,
            "end_of_data": False, "newest_received_at": None,
            "reason": "NO_DATA_EN_T",
            "evidence": {"at_ms": at_ms, "n_known": 0},
        }

    newest_received = max(
        (c.received_at for c in prefix if c.received_at is not None),
        default=None,
    )

    # Dato obsoleto: una vela conocida en T cuyo received_at es mucho más
    # antiguo que T (el feed no la actualizó a tiempo).
    stale: List[Dict[str, Any]] = []
    for c in prefix:
        if c.received_at is not None and (at_ms - c.received_at) > STALE_MAX_AGE_MS:
            stale.append({
                "open_time_ms": c.open_time_ms,
                "received_at": c.received_at,
                "age_ms": at_ms - c.received_at,
            })

    # Desconexión: silencio prolongado sin recibir nada nuevo.
    disconnect = False
    if newest_received is not None and (at_ms - newest_received) > DISCONNECT_MAX_SILENCE_MS:
        disconnect = True

    # Fin de datos: no hay velas con open_time_ms > T en la fixture.
    end_of_data = not any(c.open_time_ms > at_ms for c in candles)

    fresh = (not stale) and (not disconnect) and (not end_of_data)

    if stale:
        reason = "DATA_STALE"
    elif disconnect:
        reason = "FEED_INTERRUPTED"
    elif end_of_data:
        reason = "END_OF_DATA"
    else:
        reason = "FRESH"

    return {
        "fresh": fresh, "stale_candles": stale, "disconnect": disconnect,
        "end_of_data": end_of_data, "newest_received_at": newest_received,
        "reason": reason,
        "evidence": {
            "at_ms": at_ms, "n_known": len(prefix),
            "newest_received_at": newest_received,
            "stale_max_age_ms": STALE_MAX_AGE_MS,
            "disconnect_max_silence_ms": DISCONNECT_MAX_SILENCE_MS,
        },
    }


def _request_id() -> str:
    return uuid.uuid4().hex


# --- Disponibilidad causal de velas ----------------------------------------
# Contrato de conocimiento (backtest-offline v4.2):
#   - El open de una vela se conoce en su open_time_ms.
#   - high/low/close solo se conocen en su close_time_ms (el siguiente
#     open_time_ms del mismo simbolo, o None para la ultima / huecos).
# En T solo son "conocidas" las velas con open_time_ms <= T. Son "plenamente
# conocidas" (OHLC) las que ademas tienen close_time_ms <= T.


def _known_prefix_at(candles: List[PaperCandle], at_ms: int) -> List[PaperCandle]:
    """Velas cuyo open se conoce en/before at_ms (prefijo causal en T)."""
    return [c for c in candles if c.open_time_ms <= at_ms]


def _fully_known_at(candles: List[PaperCandle], at_ms: int) -> List[PaperCandle]:
    """Velas cuyo OHLC completo se conoce en/before at_ms."""
    return [
        c for c in candles
        if c.close_time_ms is not None and c.close_time_ms <= at_ms
    ]


def _merge_candles(
    context_candles: List[PaperCandle], candles: List[PaperCandle],
) -> List[PaperCandle]:
    """Serie unica contexto+operacion, ordenada y sin duplicados por open."""
    seen = set()
    merged: List[PaperCandle] = []
    for c in sorted(list(context_candles) + list(candles),
                    key=lambda c: c.open_time_ms):
        if c.open_time_ms not in seen:
            seen.add(c.open_time_ms)
            merged.append(c)
    return merged


# --- Regla de senal causal (senal, no admision, no simulacion) -------------


def _evaluate_signal_causal_v1(
    state: PaperSessionState, at_ms: int,
) -> Tuple[str, str, Dict[str, Any]]:
    """RULE-CAUSAL-V1: senal de entrada usando solo el prefijo conocido en T.

    Devuelve (decision, motivo, evidencia). decision en
    {SIN_ENTRADA, DESCARTADO, ENTRADA_SIMULADA}. Nunca usa velas futuras,
    existencia de trade, salida, P&L o comisiones como confirmacion.

    Logica:
      - Sin velas conocidas en T -> SIN_ENTRADA (evidencia insuficiente).
      - Velas conocidas pero ninguna plenamente conocida (close desconocido)
        -> VIGILANDO-equivalente: SIN_ENTRADA con motivo de espera.
      - Ultima vela plenamente conocida: si close opera a favor de la
        direccion vs entry_px y el stop no esta vulnerado en T ->
        ENTRADA_SIMULADA (senal, sujeto a admision de riesgo y simulacion).
      - Si el stop ya esta vulnerado en T -> DESCARTADO.
      - En cualquier otro caso -> SIN_ENTRADA.
    """
    config = state.config
    prefix = _known_prefix_at(state.candles, at_ms)
    fully = _fully_known_at(state.candles, at_ms)

    evidence: Dict[str, Any] = {
        "rule_version": RULE_CAUSAL_V1,
        "at_ms": at_ms,
        "n_prefix_candles": len(prefix),
        "n_fully_known_candles": len(fully),
        "candles": [
            {
                "open_time_ms": c.open_time_ms,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "close_time_ms": c.close_time_ms,
                "open_known": c.open_time_ms <= at_ms,
                "ohlc_known": (c.close_time_ms is not None
                               and c.close_time_ms <= at_ms),
            }
            for c in prefix
        ],
    }

    if not prefix:
        return ("SIN_ENTRADA",
                "Sin velas conocidas en T: prefijo vacio, no hay evidencia para decidir.",
                evidence)

    if not fully:
        # Hay velas con open conocido pero ninguna con close conocido:
        # aun no se puede confirmar direccion -> abstencion.
        last = prefix[-1]
        evidence["awaiting_close_of"] = last.open_time_ms
        return ("SIN_ENTRADA",
                f"Velas abiertas en T pero close todavia desconocido (ultima abierta @ {last.open_time_ms}): senal no confirmada, abstencion.",
                evidence)

    last = fully[-1]
    is_long = config.direction == "LONG"
    px = last.close
    stop_px = config.stop_px
    entry_px = config.entry_px

    # Stop ya vulnerado en T (conocido por close <= T): descarte.
    if is_long and last.low is not None and last.low <= stop_px:
        evidence.update({
            "trigger_px": px, "entry_px": entry_px,
            "stop_px": stop_px, "breach_px": last.low,
            "breach_candle_open_time_ms": last.open_time_ms,
        })
        return ("DESCARTADO",
                f"Stop ya vulnerado en T (low={last.low} <= stop={stop_px} @ close_time={last.close_time_ms}): entrada descartada.",
                evidence)
    if (not is_long) and last.high is not None and last.high >= stop_px:
        evidence.update({
            "trigger_px": px, "entry_px": entry_px,
            "stop_px": stop_px, "breach_px": last.high,
            "breach_candle_open_time_ms": last.open_time_ms,
        })
        return ("DESCARTADO",
                f"Stop ya vulnerado en T (high={last.high} >= stop={stop_px} @ close_time={last.close_time_ms}): entrada descartada.",
                evidence)

    # Senal de direccion: precio a favor vs entry_px en la vela plenamente conocida.
    if is_long:
        if px >= entry_px:
            evidence.update({
                "trigger_px": px, "entry_px": entry_px,
                "stop_px": stop_px, "signal_candle_close_time_ms": last.close_time_ms,
            })
            return ("ENTRADA_SIMULADA",
                    f"Senal RULE-CAUSAL-V1 en T: close={px} >= entry_px={entry_px}, stop no vulnerado.",
                    evidence)
        return ("SIN_ENTRADA",
                f"Sin senal de entrada en T: close={px} < entry_px={entry_px} (LONG).",
                evidence)
    else:
        if px <= entry_px:
            evidence.update({
                "trigger_px": px, "entry_px": entry_px,
                "stop_px": stop_px, "signal_candle_close_time_ms": last.close_time_ms,
            })
            return ("ENTRADA_SIMULADA",
                    f"Senal RULE-CAUSAL-V1 en T: close={px} <= entry_px={entry_px}, stop no vulnerado.",
                    evidence)
        return ("SIN_ENTRADA",
                f"Sin senal de entrada en T: close={px} > entry_px={entry_px} (SHORT).",
                evidence)


def _admit_risk(config: PaperSessionConfig) -> Tuple[bool, str]:
    """Admision por riesgo: comprueba parametros de entrada antes de simular.

    No usa informacion de mercado futura. Solo reglas de admision estaticas.
    """
    if config.notional_usdt <= 0:
        return False, "Notional no positivo: admision denegada."
    if config.entry_px <= 0:
        return False, "Precio de entrada no positivo: admision denegada."
    if config.stop_px <= 0:
        return False, "Precio de stop no positivo: admision denegada."
    if config.stop_distance_pct <= 0:
        return False, "stop_distance_pct no positivo: admision denegada."
    if config.direction not in ("LONG", "SHORT"):
        return False, "Direccion invalida: admision denegada."
    # Stop debe estar alejado del precio de entrada (distancia minima).
    if config.direction == "LONG" and config.stop_px >= config.entry_px:
        return False, "Stop de LONG no por debajo del entry_px: admision denegada."
    if config.direction == "SHORT" and config.stop_px <= config.entry_px:
        return False, "Stop de SHORT no por encima del entry_px: admision denegada."
    return True, "Admision de riesgo OK."


# --- Adaptador a backtest_offline.run_backtest (mecánica compartida) -------


def _build_study_event(state: PaperSessionState) -> StudyEvent:
    """Construye un StudyEvent a partir de la configuracion de sesion."""
    config = state.config
    return StudyEvent(
        symbol=config.symbol,
        event_time_ms=state.clock_ms or 0,
        direction=config.direction,
        reference_price=config.entry_px,
        family="H1",
        rules_version="H1-v1",
    )


def _build_backtest_config(state: PaperSessionState) -> BacktestConfig:
    """Construye un BacktestConfig a partir de la configuracion de sesion.

    No se inyecta FundingCalendar a menos que exista uno real: si no hay
    calendario de funding, run_backtest usaria el fallback sintético (8h).
    Para cumplir "funding ausente = UNKNOWN", no se pasa calendario y el
    resultado se sobrescribe despues.
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
        funding_calendar=None,  # sin calendario real -> funding = UNKNOWN
        funding_estimated_bps=None,  # contexto solo, nunca contabiliza
    )


def _to_bt_candles(candles: List[PaperCandle], symbol: str) -> List[Candle]:
    """Convierte PaperCandle en Candle de backtest_offline."""
    return [
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


def _run_backtest_on_prefix(
    state: PaperSessionState, prefix: List[PaperCandle],
    event_time_ms: int,
    known_close_cutoff: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Ejecuta run_backtest SOLO sobre el prefijo conocido en T.

    run_backtest es la autoridad economica (entradas, salidas, costes,
    funding, stops, horizonte), pero recibe unicamente velas disponibles
    en/before T. Nunca ve velas futuras de la fixture.
    """
    config = state.config
    if not prefix:
        return None

    # run_backtest requiere c.open_time_ms > ev.event_time_ms para el fill.
    # El evento se situa en T. Como el prefijo solo contiene velas con
    # open_time_ms <= T, nunca hay fill en el instante de la senal: el fill
    # queda pendiente hasta que un avance revele el open de una vela
    # posterior. run_backtest recibe EXCLUSIVAMENTE el prefijo conocido en T;
    # nunca ve velas futuras de la fixture. known_close_cutoff solo restringe
    # close/alta/baja a velas cuyo cierre se conoce en T, nunca filtra opens
    # futuros (de hecho no los ve).
    event = StudyEvent(
        symbol=config.symbol,
        event_time_ms=event_time_ms,
        direction=config.direction,
        reference_price=config.entry_px,
        family="H1",
        rules_version="H1-v1",
    )
    bt_config = _build_backtest_config(state)
    seen_opens_bt = set()
    merged_candles_for_bt = []
    for c in sorted(prefix, key=lambda c: c.open_time_ms):
        if c.open_time_ms not in seen_opens_bt:
            seen_opens_bt.add(c.open_time_ms)
            merged_candles_for_bt.append(c)
    bt_candles = _to_bt_candles(merged_candles_for_bt, config.symbol)

    result = run_backtest(
        [event], bt_candles, bt_config,
        dataset_id="paper-lab-fixture", segment="dev",
        known_close_cutoff=known_close_cutoff,
    )
    trades = result.get("trades", [])
    if not trades:
        return None
    return trades[0]

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
    # --- Frescura real (Item 3) -------------------------------------------
    # available_at: momento en que la vela esta disponible para lectura
    #               (open conocido en open_time_ms; OHLC en close_time_ms).
    # received_at:  momento en que el feed entrego la vela al sistema.
    #               None si no se ha recibido (futuro/reserva de la fixture).
    available_at: Optional[int] = None
    received_at: Optional[int] = None


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


# _run_backtest_authoritative reemplazado por _run_backtest_on_prefix:
# este recibe un prefijo conocido en T y un event_time_ms causales,
# sin acceso a la reserva de futuros de la fixture.


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

    # Reloj de simulacion: se establece al close_time de la ULTIMA vela de
    # CONTEXTO (frontera inicial), no al cierre de toda la fixture. De este
    # modo la primera evaluacion solo conoce el contexto ya disponible y no
    # los datos posteriores que se revelaran al avanzar. El reloj pertenece al
    # backend y avanza de forma monotonica con cada step_forward.
    initial_clock_ms: Optional[int] = None
    if context_candles:
        last_ctx_close = context_candles[-1].close_time_ms
        if last_ctx_close is not None:
            initial_clock_ms = last_ctx_close
    elif candles:
        initial_clock_ms = candles[0].open_time_ms

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
        clock_ms=initial_clock_ms,
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
    at_ms: Optional[int] = None,
) -> PaperSessionState:
    """Evalúa la evidencia disponible en T y retorna una decisión causal.

    Tres fases separadas, sin superposición de responsabilidades:
      1. Señal (RULE-CAUSAL-V1): solo información disponible en/before T.
      2. Admisión por riesgo: parámetros estáticos, sin mercado.
      3. Simulación económica: run_backtest sobre el prefijo conocido en T.

    Nunca usa velas futuras, existencia de trade, salida, P&L ni comisiones
    como confirmación. run_backtest recibe únicamente velas conocidas en T.

    Transiciones:
      sin_iniciar → evaluando → en_espera (ENTRADA_SIMULADA)
      sin_iniciar → evaluando → cerrada (SIN_ENTRADA / DESCARTADO, sin posición)

    Parametros:
      at_ms: tiempo de evaluacion T. Si es None, usa state.clock_ms o _now_ms().
    """
    if state.status not in ("sin_iniciar", "evaluando"):
        return state

    now = _now_ms()

    # --- Modo de reloj de simulación --------------------------------------
    # El backend posee el reloj de simulación. Se usa at_ms si se proporciona;
    # en caso contrario, el reloj válido de la sesión (state.clock_ms). Nunca
    # se recurre a la hora actual, lo cual consideraría todo el histórico
    # como conocido y rompería la causalidad.
    if at_ms is not None:
        # Modo causal: T explícito, prefijo conocido en T.
        signal_at_ms = at_ms
    elif state.clock_ms is not None:
        # Reloj válido de la sesión (establecido en create_session).
        signal_at_ms = state.clock_ms
    else:
        raise ValueError(
            "CLOCK_REQUIRED: se requiere at_ms o un clock_ms válido en la "
            "sesión para evaluar causalmente. No se puede usar la hora actual "
            "porque consideraría todo el histórico conocido."
        )

    # Prefijo conocido en T: fusion de contexto y velas de operacion,
    # ordenados y sin duplicados por open_time_ms.
    merged_candles = _merge_candles(state.context_candles, state.candles)
    prefix = _known_prefix_at(merged_candles, signal_at_ms)
    # El evento se sitúa en T (tiempo de la señal), no antes de la primera
    # vela. Esto garantiza entry_ms >= signal_at_ms (no entrada retroactiva).
    event_time_ms = signal_at_ms
    clock_for_state = signal_at_ms

    # Copia de trabajo en estado evaluando.
    next_state = PaperSessionState(
        session_id=state.session_id,
        created_at_ms=state.created_at_ms,
        updated_at_ms=now,
        status="evaluando",
        config=state.config,
        candles=state.candles,
        context_candles=state.context_candles,
        cursor=state.cursor,
        position=state.position,
        costs=state.costs,
        events=list(state.events),
        result=state.result,
        clock_ms=clock_for_state,
        config_hash=state.config_hash,
        input_hash=state.input_hash,
        engine_version=state.engine_version,
        limitations=list(state.limitations),
        revision=state.revision + 1,
        authoritative=None,
    )

    # ---- Fase 1: Señal causal (solo prefijo conocido en T) ----
    signal, signal_reason, signal_evidence = _evaluate_signal_causal_v1(
        next_state, signal_at_ms)

    # ---- Fase 2: Admisión por riesgo (estática, sin mercado) ----
    risk_ok, risk_reason = _admit_risk(next_state.config)

    # ---- Fase 3: Simulación económica (run_backtest sobre prefijo conocido) ----
    bt_result: Optional[Dict[str, Any]] = None
    fill_entry_px = next_state.config.entry_px
    fill_entry_ms = None
    fill_qty = None
    fill_cost = None
    entry_fees = 0.0
    entry_spread_slip = 0.0

    if signal == "ENTRADA_SIMULADA" and risk_ok:
        prefix = _known_prefix_at(merged_candles, signal_at_ms)
        # El evento se sitúa en T: el primer fill posible es una vela del
        # prefijo con open_time_ms > event_time_ms, nunca una vela anterior.
        bt_result = _run_backtest_on_prefix(
            next_state, prefix, event_time_ms=event_time_ms,
            known_close_cutoff=signal_at_ms)
        if bt_result is not None:
            fill_entry_px = bt_result["entry_px"]
            fill_entry_ms = bt_result["entry_ms"]
            fill_qty = bt_result["filled_qty"]
            fill_cost = bt_result["filled_cost"]
            entry_fees = bt_result.get("entry_fees", 0.0)
            entry_spread_slip = bt_result.get("entry_spread_slip", 0.0)

    # Construir decision final.
    if bt_result is not None:
        # Entrada admitida: senal + riesgo + fill posible en prefijo conocido.
        decision = "ENTRADA_SIMULADA"
        reason = (
            f"Senal {RULE_CAUSAL_V1} confirmada en T y fill posible en el "
            f"prefijo conocido (entry_ms={fill_entry_ms}): entrada ejecutable."
        )
        evidence = dict(signal_evidence)
        evidence.update({
            "evaluated_at_ms": now,
            "at_ms": signal_at_ms,
            "decision_at_ms": signal_at_ms,
            "available_at_ms": fill_entry_ms if fill_entry_ms is not None else signal_at_ms,
            "rule_version": rule_version or RULE_CAUSAL_V1,
            "admit_risk": risk_ok,
            "risk_reason": risk_reason,
            "entry_fill_px": fill_entry_px,
            "entry_fill_ms": fill_entry_ms,
            "entry_fill_qty": fill_qty,
            "entry_fill_cost": fill_cost,
        })
        status = "en_espera"
        next_state = PaperSessionState(
            session_id=next_state.session_id,
            created_at_ms=next_state.created_at_ms,
            updated_at_ms=now,
            status=status,
            config=PaperSessionConfig(
                symbol=next_state.config.symbol,
                interval=next_state.config.interval,
                direction=next_state.config.direction,
                notional_usdt=next_state.config.notional_usdt,
                entry_px=fill_entry_px,
                stop_px=next_state.config.stop_px,
                stop_distance_pct=next_state.config.stop_distance_pct,
                horizon_ms=next_state.config.horizon_ms,
                fee_bps=next_state.config.fee_bps,
                spread_bps=next_state.config.spread_bps,
                slippage_bps=next_state.config.slippage_bps,
                hypothesis_id=hypothesis_id,
                hypothesis_version=hypothesis_version,
                rule_version=rule_version or RULE_CAUSAL_V1,
                decision=decision,
                decision_reason=reason,
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
                    at_ms=fill_entry_ms if fill_entry_ms is not None else now,
                    label=f"Decisión: ENTRADA_SIMULADA @ {fill_entry_px:.2f}",
                    kind="protection",
                    detail=(f"qty={fill_qty:.8f} notional={next_state.config.notional_usdt} "
                            f"entry_ms={fill_entry_ms} rule={rule_version or RULE_CAUSAL_V1} "
                            f"at_ms={signal_at_ms}"),
                )
            ],
            result=None,
            clock_ms=clock_for_state,
            config_hash=next_state.config_hash,
            input_hash=next_state.input_hash,
            engine_version=next_state.engine_version,
            limitations=list(next_state.limitations),
            revision=next_state.revision + 1,
            authoritative=bt_result,
        )
        return next_state

    # No hay entrada.
    if signal == "ENTRADA_SIMULADA":
        # Senal confirmada pero sin fill posible en el prefijo conocido:
        # permanece en en_espera (pendiente de fill), no cierra.
        decision = "ENTRADA_SIMULADA"
        reason = ("Senal de entrada en T pero sin fill posible en el "
                  "prefijo conocido: run_backtest no admite operacion con "
                  "datos disponibles en T. Senal pendiente de fill.")
        # decision_at = instante de la senal (T). available_at = open_time
        # de la primera vela cuya apertura aun no se conoce (la vela donde
        # podra ejecutarse el fill una vez que el avance la revele). Nunca
        # se publica el precio de una vela futura como "entrada pendiente".
        siguiente = [c for c in merged_candles if c.open_time_ms > signal_at_ms]
        available_at_ms = min((c.open_time_ms for c in siguiente), default=None)
        evidence = dict(signal_evidence)
        evidence.update({
            "evaluated_at_ms": now,
            "at_ms": signal_at_ms,
            "decision_at_ms": signal_at_ms,
            "available_at_ms": available_at_ms,
            "rule_version": rule_version or RULE_CAUSAL_V1,
            "admit_risk": risk_ok,
            "risk_reason": risk_reason,
            "entry_fill_px": None,
            "entry_fill_ms": None,
            "entry_fill_qty": None,
            "entry_fill_cost": None,
        })
        next_state = PaperSessionState(
            session_id=next_state.session_id,
            created_at_ms=next_state.created_at_ms,
            updated_at_ms=now,
            status="en_espera",  # pendiente de fill, no cierra
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
                rule_version=rule_version or RULE_CAUSAL_V1,
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
                    at_ms=now,
                    label=f"Decision: {decision} (pendiente de fill)",
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

    # Senal SIN_ENTRADA porque no hay evidencia suficiente EN LAS VELAS DE
    # OPERACION (que son las que evalua la senal): sesion temporal, no cierra.
    # Espera a que el reloj revele mas velas de operacion.
    #
    # Importante: el gate usa el prefijo de operacion, no el fusionado con el
    # contexto. Con contexto presente y cero velas de operacion conocidas, el
    # prefijo fusionado no esta vacio y la sesion se cerraba en la primera
    # evaluacion (sin evidencia real), dejando el escenario sin "Paso a paso".
    op_prefix = _known_prefix_at(next_state.candles, signal_at_ms)
    op_fully = _fully_known_at(next_state.candles, signal_at_ms)
    if not op_prefix or not op_fully:
        decision = signal
        reason = signal_reason
        evidence = dict(signal_evidence)
        evidence.update({
            "evaluated_at_ms": now,
            "at_ms": signal_at_ms,
            "rule_version": rule_version or RULE_CAUSAL_V1,
            "admit_risk": risk_ok,
            "risk_reason": risk_reason,
        })
        next_state = PaperSessionState(
            session_id=next_state.session_id,
            created_at_ms=next_state.created_at_ms,
            updated_at_ms=now,
            status="sin_iniciar",  # sesion temporal, espera mas datos
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
                rule_version=rule_version or RULE_CAUSAL_V1,
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
                    at_ms=now,
                    label=f"Decision: {decision} (esperando datos)",
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

    # Senal SIN_ENTRADA definitiva (stop vulnerado o precio no a favor):
    # cierra sesion con motivo.
    decision = signal
    reason = signal_reason
    evidence = dict(signal_evidence)
    evidence.update({
        "evaluated_at_ms": now,
        "at_ms": signal_at_ms,
        "rule_version": rule_version or RULE_CAUSAL_V1,
        "admit_risk": risk_ok,
        "risk_reason": risk_reason,
    })

    next_state = PaperSessionState(
        session_id=next_state.session_id,
        created_at_ms=next_state.created_at_ms,
        updated_at_ms=now,
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
            rule_version=rule_version or RULE_CAUSAL_V1,
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
                at_ms=now,
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


def _apply_entry(state: PaperSessionState) -> PaperSessionState:
    """Ejecuta la entrada en la vela actual (cursor) usando la autoridad de
    run_backtest (state.authoritative). No duplica si ya hay posición."""
    if state.position.open:
        return state
    config = state.config
    candles = state.candles
    cursor = state.cursor
    candle = candles[cursor] if 0 <= cursor < len(candles) else None

    # Usar la entrada autoritativa de run_backtest si existe. El fill puede
    # haber avanzado el cursor mas alla de la ultima vela conocida al entrar;
    # eso no invalida la entrada, que ya tiene entry_ms/entry_px de run_backtest.
    bt = state.authoritative
    entry_px = bt["entry_px"] if bt else config.entry_px
    entry_ms = bt["entry_ms"] if bt else (candle.close_time_ms or candle.open_time_ms if candle else 0)
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


def _run_backtest_at_clock(
    state: PaperSessionState, clock_ms: int,
) -> Optional[Dict[str, Any]]:
    """Re-ejecuta run_backtest con el prefijo conocido en clock_ms para
    resolver la salida (stop / horizonte) a medida que se revelan velas.

    Solo usa informacion disponible en clock_ms: velas con
    open_time_ms <= clock_ms, y close/alta/baja solo de las que tienen
    close_time_ms <= clock_ms (known_close_cutoff). Nunca consulta velas
    futuras.
    """
    config = state.config
    ev = state.config.decision_evidence or {}
    event_time_ms = ev.get("at_ms")
    if event_time_ms is None:
        event_time_ms = state.position.entry_ms or 0
    if not event_time_ms:
        return None
    merged = _merge_candles(state.context_candles, state.candles)
    prefix = [c for c in merged if c.open_time_ms <= clock_ms]
    return _run_backtest_on_prefix(state, prefix, event_time_ms=event_time_ms,
                                   known_close_cutoff=clock_ms or 0)


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
    # Si authoritative es None (fill todavía no disponible), re-ejecutar
    # run_backtest con el reloj avanzado para ver si ahora se puede llenar.
    if state.status == "en_espera" and not state.position.open:
        ev_time = state.config.decision_evidence.get("at_ms") if state.config.decision_evidence else None
        bt_result = state.authoritative
        # Reloj y cursor del paso siguiente (se avanzan solo si se revela una
        # vela nueva; el reloj nunca retrocede).
        next_cursor = state.cursor
        next_clock_ms = state.clock_ms
        if bt_result is None and ev_time is not None:
            # Revelar la siguiente vela de operación cuyo open aún no se
            # conoce (open_time_ms > reloj). El cursor indexa las velas de
            # operación (state.candles), no la serie fusionada con el
            # contexto: usar el índice fusionado dejaba cursor=50 sobre 8
            # velas y desactivaba can_step justo al abrir la posición.
            base_clock = state.clock_ms if state.clock_ms is not None else ev_time
            reveal_idx = next(
                (i for i in range(state.cursor, len(state.candles))
                 if state.candles[i].open_time_ms > base_clock),
                None,
            )
            if reveal_idx is not None:
                revealed = state.candles[reveal_idx]
                next_cursor = max(state.cursor + 1, reveal_idx + 1)
                next_clock_ms = revealed.close_time_ms if revealed.close_time_ms is not None \
                    else revealed.open_time_ms
                merged_candles = _merge_candles(state.context_candles, state.candles)
                prefix = [c for c in merged_candles if c.open_time_ms <= next_clock_ms]
                bt_result = _run_backtest_on_prefix(state, prefix, event_time_ms=ev_time,
                                                    known_close_cutoff=next_clock_ms or 0)
        if bt_result is not None:
            state_with_bt = PaperSessionState(
                session_id=state.session_id,
                created_at_ms=state.created_at_ms,
                updated_at_ms=state.updated_at_ms,
                status=state.status,
                config=state.config,
                candles=state.candles,
                context_candles=state.context_candles,
                cursor=next_cursor,
                position=state.position,
                costs=state.costs,
                events=list(state.events),
                result=state.result,
                clock_ms=next_clock_ms,
                config_hash=state.config_hash,
                input_hash=state.input_hash,
                engine_version=state.engine_version,
                limitations=list(state.limitations),
                revision=state.revision,
                authoritative=bt_result,
            )
            return _apply_entry(state_with_bt)
        # Fill aun no disponible: permanecer en en_espera (reloj y cursor ya
        # avanzaron si se revelo una vela; si no, el estado no cambia).
        return state

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

        # --- Detección de stop con la vela actual (conocida en T) ---
        # run_backtest no puede confirmar el stop durante evaluate si la
        # vela de salida aún no está plenamente conocida. Al avanzar, la
        # vela actual sí tiene open conocido: si atraviesa el stop, salida.
        # Politica de gap (run_backtest): una apertura que atraviesa el stop
        # sale AL OPEN (primer precio disponible); una recuperacion posterior
        # no lo mejora. Luego, si el close se conoce, cruce normal del rango
        # (low/low toca el stop). Usa el mismo stop dinamico que run_backtest
        # (entry × (1 ∓ pct)), no el stop_px estatico del config, para
        # conservar la mecanica economica compartida.
        # No se inventa precision intrabar: el fill de gap usa el open y su
        # open_time_ms; el fill de rango usa el stop_px y el close_time_ms.
        if candle is not None and next_state.position.entry_px is not None:
            entry_px = next_state.position.entry_px
            pct = config.stop_distance_pct / 100.0
            if config.direction == "LONG":
                dynamic_stop = entry_px * (1.0 - pct)
                # Gap: la apertura esta por debajo del stop -> salida al open.
                if candle.open <= dynamic_stop:
                    return _finalize_stop_exit(
                        next_state, candle, dynamic_stop,
                        exit_px=candle.open, exit_ms=candle.open_time_ms)
                # Cruce normal del rango: el low toca/cruza el stop (close
                # conocido) -> salida al stop con tiempo de cierre.
                if (candle.close_time_ms is not None and candle.low is not None
                        and candle.low <= dynamic_stop):
                    return _finalize_stop_exit(next_state, candle, dynamic_stop)
            else:  # SHORT
                dynamic_stop = entry_px * (1.0 + pct)
                # Gap: la apertura esta por encima del stop -> salida al open.
                if candle.open >= dynamic_stop:
                    return _finalize_stop_exit(
                        next_state, candle, dynamic_stop,
                        exit_px=candle.open, exit_ms=candle.open_time_ms)
                if (candle.close_time_ms is not None and candle.high is not None
                        and candle.high >= dynamic_stop):
                    return _finalize_stop_exit(next_state, candle, dynamic_stop)

        # Evaluar salida con la autoridad de run_backtest sobre el prefijo
        # conocido en el reloj actual. Al avanzar se revelan velas y puede
        # confirmarse stop o horizonte (sin usar velas futuras).
        bt = _run_backtest_at_clock(next_state, clock_ms) \
            if clock_ms is not None else next_state.authoritative
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


def _finalize_exit(
    state: PaperSessionState, exit_px: float, exit_ms: int,
    exit_reason: str, exit_executed: bool,
    funding: Optional[float] = None,
) -> PaperSessionState:
    """Ejecuta una salida con la mecanica economica canonica de
    backtest_offline (compartida por stop, gap y run_backtest).

    - Costes de salida SOLO sobre el valor efectivamente ejecutado
      (exit_px x qty x fee/spread/slip), nunca sobre el mark.
    - funding ausente -> UNKNOWN (None), nunca cero por defecto.
    - Construye PaperTradeResult (realizado solo si salida ejecutada) y el
      estado cerrado con la posicion sin abrir y la marca congelada al precio
      de salida.
    """
    config = state.config
    position = state.position
    entry_px = position.entry_px or 0.0
    qty = position.entry_qty or 0.0

    gross = _gross_pnl(config.direction, entry_px, exit_px, qty)
    entry_fees_executed = state.costs.entry_fees_executed
    entry_spread_slip_executed = state.costs.entry_spread_slip_executed
    if exit_executed:
        exit_fees_executed = exit_px * qty * (config.fee_bps / 10000.0)
        exit_spread_slip_executed = exit_px * qty * (
            (config.spread_bps + config.slippage_bps) / 10000.0
        )
    else:
        exit_fees_executed = 0.0
        exit_spread_slip_executed = 0.0
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
        detail=f"razon={exit_reason} P&L neto={net:.2f}",
    ))

    result = PaperTradeResult(
        symbol=config.symbol, direction=config.direction,
        entry_px=entry_px, exit_px=exit_px,
        entry_ms=position.entry_ms or 0, exit_ms=exit_ms,
        exit_reason=exit_reason, exit_executed=exit_executed, qty=qty,
        filled_cost=position.entry_cost or 0.0,
        gross_pnl=gross,
        fees=entry_fees_executed + exit_fees_executed,
        spread_slip=entry_spread_slip_executed + exit_spread_slip_executed,
        funding=funding,
        friction=friction_executed,
        net_pnl=net,
        realized_net=net if exit_executed else None,
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


def _finalize_stop_exit(
    state: PaperSessionState, candle: PaperCandle, stop_px: float,
    exit_px: Optional[float] = None, exit_ms: Optional[int] = None,
) -> PaperSessionState:
    """Finaliza la sesión con salida ejecutada por stop detectado en la
    vela actual (OHLC conocido en T). Reutiliza _finalize_exit (mecanica
    canonica de backtest_offline).

    exit_px/exit_ms permiten distinguir:
      - gap: salida AL OPEN (precio de apertura, tiempo open_time_ms);
      - cruce de rango: salida al stop_px (tiempo close_time_ms).
    funding ausente -> UNKNOWN."""
    config = state.config
    final_exit_px = exit_px if exit_px is not None else stop_px
    final_exit_ms = exit_ms if exit_ms is not None else (
        candle.close_time_ms if candle.close_time_ms is not None
        else candle.open_time_ms)
    return _finalize_exit(state, final_exit_px, final_exit_ms, "stop",
                          True, funding=None)


def _finalize_exit_from_bt(
    state: PaperSessionState, bt: Dict[str, Any],
) -> PaperSessionState:
    """Finaliza la sesión con salida ejecutada usando el resultado de
    run_backtest (mecánica compartida). Reutiliza _finalize_exit."""
    config = state.config
    position = state.position
    exit_px = bt.get("exit_px", 0.0)
    exit_ms = bt.get("exit_ms", 0)
    exit_reason = bt.get("exit_reason", "desconocido")
    funding = bt.get("funding")
    if bt.get("funding_model") != "settlement-calendar":
        funding = None  # UNKNOWN sin calendario real
    return _finalize_exit(state, exit_px, exit_ms, exit_reason, True,
                          funding=funding)


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
    position = state.position
    exit_px = position.mark_px or position.entry_px or 0.0
    exit_ms = position.mark_ms or state.clock_ms or 0
    return _finalize_exit(state, exit_px, exit_ms, "manual", True,
                          funding=None)


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
                "available_at": c.available_at,
                "received_at": c.received_at,
            } for c in state.candles
        ],
        "context_candles": [
            {
                "open_time_ms": c.open_time_ms, "open": c.open,
                "high": c.high, "low": c.low, "close": c.close,
                "close_time_ms": c.close_time_ms,
                "available_at": c.available_at,
                "received_at": c.received_at,
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


def session_to_public_dict(
    state: PaperSessionState, at_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Serializa la sesión para respuesta pública (API/evidencia/gráfico).

    Solo incluye información disponible en T:
      - Velas con open_time_ms <= T (conocidas en T).
      - Para velas aún abiertas (close_time_ms > T o close_time_ms None),
        solo se publican open_time_ms y open; nunca high/low/close finales.
      - decision_evidence y authoritative se filtran para no revelar futuros.
      - clock_ms se publica como T (reloj de simulación).

    El almacenamiento interno sigue usando session_to_dict (con todas las
    velas necesarias para avanzar la fixture).
    """
    if at_ms is None:
        at_ms = state.clock_ms
    # Si no hay reloj de simulación, ninguna vela se considera conocida.
    if at_ms is None:
        at_ms = -1

    # Velas conocidas en T (open disponible).
    known_candles = [c for c in state.candles if c.open_time_ms <= at_ms]

    def _public_candle(c: PaperCandle) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "open_time_ms": c.open_time_ms,
            "open": c.open,
            "available_at": c.available_at,
            "received_at": c.received_at,
        }
        # Solo publicar OHLC si la vela está plenamente conocida en T.
        if c.close_time_ms is not None and c.close_time_ms <= at_ms:
            entry["high"] = c.high
            entry["low"] = c.low
            entry["close"] = c.close
            entry["close_time_ms"] = c.close_time_ms
        else:
            entry["high"] = None
            entry["low"] = None
            entry["close"] = None
            entry["close_time_ms"] = None
        return entry

    # Filtrar authoritative: no publicar datos de trades futuros.
    authoritative_public: Optional[Dict[str, Any]] = None
    if state.authoritative is not None:
        auth = state.authoritative
        if at_ms is not None:
            # Solo incluir fills/exits con entry_ms <= T y exit_ms <= T.
            if auth.get("entry_ms", 0) > at_ms:
                authoritative_public = None  # entrada futura, no revelar
            else:
                authoritative_public = dict(auth)
                if auth.get("exit_ms") is not None and auth["exit_ms"] > at_ms:
                    authoritative_public["exit_px"] = None
                    authoritative_public["exit_ms"] = None
                    authoritative_public["exit_reason"] = None
                    authoritative_public["exit_executed"] = False
        else:
            authoritative_public = dict(auth)

    return {
        "session_id": state.session_id,
        "created_at_ms": state.created_at_ms,
        "updated_at_ms": state.updated_at_ms,
        "status": state.status,
        "revision": state.revision,
        "clock_ms": at_ms,
        "config_hash": state.config_hash,
        "input_hash": state.input_hash,
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
        "candles": [_public_candle(c) for c in known_candles],
        "context_candles": [_public_candle(c) for c in state.context_candles
                            if c.open_time_ms <= at_ms],
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
        "engine_version": state.engine_version,
        "limitations": list(state.limitations),
        # El backend informa si se puede avanzar (sin revelar datos futuros):
        # hay velas internas por revelar y el escenario no esta terminado.
        # La UI no debe derivarlo de candles.length de la respuesta filtrada.
        "can_step": (
            state.status in ("sin_iniciar", "en_espera", "abierta")
            and state.status not in ("cerrada", "detenida")
            and state.cursor < len(state.candles)
        ),
        "authoritative": authoritative_public,
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
    # _request_id y _content_hash son campos internos de idempotencia:
    # nunca forman parte del estado hidratado.
    candles = [
        PaperCandle(
            open_time_ms=c["open_time_ms"], open=c["open"],
            high=c["high"], low=c["low"], close=c["close"],
            close_time_ms=c["close_time_ms"],
            available_at=c.get("available_at"),
            received_at=c.get("received_at"),
        ) for c in d.get("candles", [])
    ]
    context = [
        PaperCandle(
            open_time_ms=c["open_time_ms"], open=c["open"],
            high=c["high"], low=c["low"], close=c["close"],
            close_time_ms=c["close_time_ms"],
            available_at=c.get("available_at"),
            received_at=c.get("received_at"),
        ) for c in d.get("context_candles", [])
    ]
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


# --- Persistencia atomica por sesion (Item 2) -----------------------------
# Cargar -> validar revision -> aplicar acción -> persistir como operación
# indivisible. File lock para exclusión del ciclo completo entre procesos.
# Temp únicos por (sesion, PID, token) para evitar colisiones. Falla explícita
# ante archivo ilegible, revisión incompatible o identidad incierta.
# Idempotencia por identidad de petición (request_id).

_IS_WINDOWS = os.name == "nt"


class _FileLock:
    """Lock de exclusión mutua entre procesos sobre un archivo auxiliar.

    Windows: msvcrt.locking (exclusivo, bloqueante con reintentos).
    POSIX: fcntl.flock (exclusivo, no bloqueante con reintentos).
    """

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._fd = None
        self._owned = False

    def acquire(self, timeout_s: float = 10.0) -> bool:
        import time
        deadline = time.time() + timeout_s
        while True:
            try:
                if _IS_WINDOWS:
                    import msvcrt
                    self._fd = os.open(str(self.lock_path),
                                       os.O_CREAT | os.O_RDWR,
                                       0o644)
                    # msvcrt.locking: bloqueante, espera hasta liberarse.
                    msvcrt.locking(self._fd, msvcrt.LK_LOCK, 1)
                    self._owned = True
                    return True
                else:
                    import fcntl
                    self._fd = os.open(str(self.lock_path),
                                       os.O_CREAT | os.O_RDWR,
                                       0o644)
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._owned = True
                    return True
            except (OSError, IOError):
                pass
            if time.time() >= deadline:
                return False
            time.sleep(0.05)

    def release(self):
        if self._fd is not None:
            try:
                if _IS_WINDOWS:
                    import msvcrt
                    if self._owned:
                        msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            self._owned = False


def _session_lock_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f".{session_id}.lock"


def _session_lock(sessions_dir: Path, session_id: str) -> _FileLock:
    return _FileLock(_session_lock_path(sessions_dir, session_id))


def _sessions_dir(root: str | Path) -> Path:
    return Path(root) / SESSION_DIR_NAME


def _session_path(sessions_dir: Path, session_id: str) -> Path:
    _safe_session_id(session_id)
    return sessions_dir / f"{session_id}.json"


def _unique_tmp_path(path: Path) -> Path:
    """Nombre de temporal único: sesion + PID + token aleatorio."""
    token = uuid.uuid4().hex[:12]
    pid = os.getpid()
    return path.with_name(f"{path.stem}.{pid}.{token}.json.tmp")


@dataclass
class SessionSaveResult:
    ok: bool
    state: PaperSessionState
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    # Idempotencia: si la petición ya fue procesada, se devuelve el estado
    # almacenado sin repetir efectos.
    idempotent_repeat: bool = False


def _read_stored_revision(path: Path) -> Tuple[Optional[int], Optional[Dict[str, Any]], Optional[str]]:
    """Lee la revisión almacenada y el payload completo.

    Devuelve (revision, payload, error_code). Si el archivo es ilegible,
    devuelve (None, None, "UNREADABLE_FILE").
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None, None
    except Exception:
        return None, None, "UNREADABLE_FILE"
    try:
        d = json.loads(raw)
    except Exception:
        return None, None, "UNREADABLE_FILE"
    return d.get("revision", 0), d, None


def _content_hash(state: PaperSessionState) -> str:
    """Hash del contenido económico de la sesión para idempotencia."""
    payload = json.dumps(
        {
            "session_id": state.session_id,
            "status": state.status,
            "revision": state.revision,
            "config": {
                "symbol": state.config.symbol,
                "direction": state.config.direction,
                "decision": state.config.decision,
                "decision_reason": state.config.decision_reason,
                "rule_version": state.config.rule_version,
                "entry_px": state.config.entry_px,
                "stop_px": state.config.stop_px,
                "horizon_ms": state.config.horizon_ms,
            },
            "position": {
                "open": state.position.open,
                "entry_px": state.position.entry_px,
                "entry_qty": state.position.entry_qty,
                "entry_ms": state.position.entry_ms,
            },
            "result": None if state.result is None else {
                "exit_executed": state.result.exit_executed,
                "exit_reason": state.result.exit_reason,
                "net_pnl": state.result.net_pnl,
                "realized_net": state.result.realized_net,
                "open_at_end": state.result.open_at_end,
            },
            "events_count": len(state.events),
        },
        sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def save_session(
    state: PaperSessionState,
    root: str | Path = ".",
    expected_revision: Optional[int] = None,
    request_id: Optional[str] = None,
) -> SessionSaveResult:
    """Guarda la sesión de forma atomica con control de revisión e idempotencia.

    Operación indivisible (cargar → validar revisión → aplicar → persistir)
    protegida por file lock por sesión.

    Parámetros:
      expected_revision: revisión esperada (optimistic locking). Si no
         coincide con la almacenada → REVISION_CONFLICT.
      request_id: identidad de petición para idempotencia.
         - Misma request_id + mismo contenido → mismo resultado, sin repetir
           efectos (devuelve el estado ya persistido, idempotent_repeat=True).
         - Misma request_id + contenido distinto → REQUEST_CONTENT_CONFLICT.
         - Diferente request_id → guarda normalmente.

    Falla explícitamente (ok=False) ante:
      - Archivo ilegible → UNREADABLE_FILE
      - Revisión incompatible → REVISION_CONFLICT
      - Identidad incierta / contenido no coincide con request_id →
        REQUEST_CONTENT_CONFLICT o IDENTITY_UNCERTAIN
    """
    sessions_dir = _sessions_dir(root)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = _session_path(sessions_dir, state.session_id)
    lock_path = _session_lock_path(sessions_dir, state.session_id)

    lock = _FileLock(lock_path)
    if not lock.acquire(timeout_s=10.0):
        return SessionSaveResult(
            ok=False, state=state,
            error_code="LOCK_TIMEOUT",
            error_detail=f"No se pudo adquirir el lock de sesión: {state.session_id}",
        )

    try:
        # --- Leer estado almacenado (bajo lock) -------------------------
        stored_rev, stored_payload, read_error = _read_stored_revision(path)

        if read_error is not None:
            return SessionSaveResult(
                ok=False, state=state,
                error_code=read_error,
                error_detail=f"No se puede leer la sesión almacenada: {path}",
            )

        # --- Control de revisión ---------------------------------------
        if expected_revision is not None and stored_rev is not None:
            if stored_rev != expected_revision:
                return SessionSaveResult(
                    ok=False, state=state,
                    error_code="REVISION_CONFLICT",
                    error_detail=(
                        f"Revisión incompatible: almacenada={stored_rev}, "
                        f"esperada={expected_revision}"),
                )

        # --- Idempotencia por identidad de petición --------------------
        if request_id is not None and stored_payload is not None:
            stored_req_id = stored_payload.get("_request_id")
            stored_content_hash = stored_payload.get("_content_hash")
            if stored_req_id == request_id:
                if stored_content_hash == _content_hash(state):
                    # Misma petición, mismo contenido: idempotente.
                    # No repetir efectos: devolver el estado almacenado.
                    try:
                        stored_state = session_from_dict(stored_payload)
                    except Exception:
                        stored_state = state
                    return SessionSaveResult(
                        ok=True, state=stored_state,
                        idempotent_repeat=True,
                    )
                else:
                    # Misma clave, contenido distinto: conflicto explícito.
                    return SessionSaveResult(
                        ok=False, state=state,
                        error_code="REQUEST_CONTENT_CONFLICT",
                        error_detail=(
                            f"Idempotencia: misma request_id={request_id} "
                            f"con contenido distinto al ya procesado."),
                    )

        # --- Escritura atómica (temporal único + os.replace) -----------
        # Marcar identidad de petición y hash de contenido en el payload.
        payload_dict = session_to_dict(state)
        if request_id is not None:
            payload_dict["_request_id"] = request_id
            payload_dict["_content_hash"] = _content_hash(state)

        tmp = _unique_tmp_path(path)
        try:
            payload_text = json.dumps(payload_dict, indent=1, default=str)
            tmp.write_text(payload_text, encoding="utf-8")
            os.replace(tmp, path)
        except Exception as exc:
            # Limpiar temporal si queda; no dejar estado parcial.
            try:
                tmp.unlink(missing_ok=True)  # type: ignore[attr-defined]
            except Exception:
                pass
            return SessionSaveResult(
                ok=False, state=state,
                error_code="WRITE_FAILED",
                error_detail=f"No se pudo persistir la sesión: {exc}",
            )

        # Devolver el estado guardado (con revision actualizada del payload).
        try:
            saved_state = session_from_dict(payload_dict)
        except Exception:
            saved_state = state
        return SessionSaveResult(ok=True, state=saved_state)
    finally:
        lock.release()


def load_session(session_id: str,
                 root: str | Path = ".") -> Optional[PaperSessionState]:
    """Carga una sesión completa por ID. Devuelve None si no existe.

    Falla explícitamente (lanza ValueError) si el archivo existe pero es
    ilegible: nunca se devuelve un estado fabricado a partir de datos
    corruptos.
    """
    sessions_dir = _sessions_dir(root)
    path = _session_path(sessions_dir, session_id)
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return session_from_dict(d)
    except Exception as exc:
        raise ValueError(
            f"IDENTITY_UNCERTAIN: sesión {session_id} ilegible: {exc}")


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
