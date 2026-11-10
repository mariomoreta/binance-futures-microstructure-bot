"""Adaptador mínimo del camino del experimento operativo v2.

Conecta (sin motor nuevo, sin segundo supervisor):
  seleccion (research_pilot) -> datos de mercado en T ->
  direccion comun (derivar_direccion_desde_movimiento) ->
  senal -> motor existente (paper_lab_engine) ->
  entrada/gestion/salida simuladas -> resultado reproducible.

Reutiliza paper_lab_engine y backtest_offline como unica autoridad
economica. No abre Binance, no envia ordenes, no crea servicios.

El adaptador lee filas JSONL de observacion del piloto (kind=observacion),
procede con la direccion derivada del move_24h_pct y construye una sesion
causal con velas 1m para reconstruir entrada posterior, stops, gaps y
salida durante el horizonte. Los resultados se persisten en JSONL
(kind=resultado_operativo) para replay posterior sin usar resultados
futuros para decidir.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from microstructure_probe.backtest_offline import (  # noqa: E402
    BacktestConfig, Candle, FundingCalendar, FundingSettlement,
    StudyEvent, run_backtest,
)
from microstructure_probe.paper_lab_engine import (  # noqa: E402
    ENGINE_VERSION_PAPER, PaperCandle, PaperSessionConfig,
    RULE_CAUSAL_V1, _next_reveal_index, _run_backtest_on_prefix,
    _to_bt_candles, create_session, derivar_direccion_desde_movimiento,
    evaluate_session, step_forward,
)

# --- Regla congelada (EXPERIMENTO_OPERATIVO_V2 §3) -------------------------
# No se optimizan ni se cambian segun resultados anteriores.
OPERATIVO_VERSION = "research-operativo-v1"
RULE_VERSION = RULE_CAUSAL_V1
STOP_DISTANCE_PCT = 0.5          # 0,5 % -> stop_fraction = 0.005
NOTIONAL_USDT = 1000.0
HORIZON_MS = 3_600_000           # 60 min
FEE_BPS = 5.0
SPREAD_BPS = 1.0
SLIPPAGE_BPS = 2.0
MAX_CONCURRENT = 1
FUNDING_MODEL_DESC = "ninguno (UNKNOWN sin calendario real por simbolo)"

FEE_BPS_ENTRY = FEE_BPS / 10_000.0
SPREAD_SLIP_BPS = (SPREAD_BPS + SLIPPAGE_BPS) / 10_000.0

# Estado de resultado (paralelo al piloto: resuelto / no_evaluable / pendiente)
RESOLVED = "resuelto"
NOT_EVALUABLE = "no_evaluable"
PENDING = "pendiente"

# --- Configuracion del adaptador -------------------------------------------

@dataclass
class OperativoConfig:
    version: str = OPERATIVO_VERSION
    rule_version: str = RULE_VERSION
    stop_distance_pct: float = STOP_DISTANCE_PCT
    notional_usdt: float = NOTIONAL_USDT
    horizon_ms: int = HORIZON_MS
    fee_bps: float = FEE_BPS
    spread_bps: float = SPREAD_BPS
    slippage_bps: float = SLIPPAGE_BPS
    max_concurrent: int = MAX_CONCURRENT
    funding_calendar: Optional[Any] = None  # FundingCalendar o None
    funding_estimated_bps: Optional[float] = None  # contexto solo, nunca contabiliza
    max_symbols: int = 20
    max_candidates: int = 12
    max_comparators: int = 8

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "rule_version": self.rule_version,
            "stop_distance_pct": self.stop_distance_pct,
            "notional_usdt": self.notional_usdt,
            "horizon_ms": self.horizon_ms,
            "fee_bps": self.fee_bps,
            "spread_bps": self.spread_bps,
            "slippage_bps": self.slippage_bps,
            "max_concurrent": self.max_concurrent,
            "max_symbols": self.max_symbols,
            "max_candidates": self.max_candidates,
            "max_comparators": self.max_comparators,
            "funding_calendar": None,
            "funding_estimated_bps": self.funding_estimated_bps,
            "funding_note": FUNDING_MODEL_DESC,
        }


# --- Resultado de una operacion --------------------------------------------

@dataclass
class OperativoTradeResult:
    observation_id: str
    symbol: str
    role: str
    direction: Optional[str]
    decision: str
    decision_ms: int
    entry_px: Optional[float]
    entry_ms: Optional[int]
    exit_px: Optional[float]
    exit_ms: Optional[int]
    exit_reason: Optional[str]
    exit_executed: bool
    open_at_end: bool
    qty: float
    gross_pnl: float
    fees: float
    spread_slip: float
    funding: Optional[float]
    net_pnl: Optional[float]
    funding_estado: str
    config_hash: str
    engine_version: str


# --- Adaptador -------------------------------------------------------------

class OperativoAdapter:
    """Conecta seleccion -> direccion comun -> motor -> resultado reproducible.

    Uso típico:
        adapter = OperativoAdapter(
            store_path=jsonl_path, cfg=OperativoConfig(),
            funding_calendars={symbol: FundingCalendar(...)})
        for obs in read_jsonl(pilot_obs_path):
            tr = adapter.procesar_observacion(obs, velas_1m_por_simbolo,
                                              funding_calendar=cal_por_simbolo)
            adapter.persistir(tr)

    `velas_1m_por_simbolo` es un dict {symbol: [PaperCandle, ...]} con las
    velas 1m conocidas causalmente (open en open_time_ms, OHLC en close_time_ms).
    No se rellenan huecos ni se convierten ausencias en cero.
    """

    def __init__(
        self,
        store_path: Path,
        cfg: Optional[OperativoConfig] = None,
        funding_calendars: Optional[Dict[str, FundingCalendar]] = None,
    ) -> None:
        self.cfg = cfg or OperativoConfig()
        self.funding_calendars: Dict[str, FundingCalendar] = (
            funding_calendars or {})
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.store_path.open("a", encoding="utf-8", newline="\n")
        self._bytes = 0
        self._rows = 0
        self.estado: Dict[str, Any] = {
            "admitidas": 0,
            "rechazadas_capacidad": 0,
            "abstenciones": 0,
            "descartes": 0,
            "operaciones": 0,
            "posiciones_abiertas_final": 0,
        }
        # Capacidad compartida: posiciones abiertas (observation_id -> {entry_ms, exit_ms}).
        # max_concurrent=1 significa una posicion abierta a la vez en todo el experimento.
        # Una posicion solo se libera cuando se conoce su salida real (stop o
        # horizonte). Una posicion open_at_end (sin salida conocida) NO libera
        # capacidad ficticiamente.
        self.open_positions: Dict[str, Dict[str, Optional[int]]] = {}
        # Resultados ya producidos por observation_id, para evitar reprocesar
        # la misma observacion (no bloquea contra si misma, no duplica admisiones
        # ni resultados). open_at_end se mantiene para poder reprocesar cuando
        # lleguen mas velas.
        self._results: Dict[str, OperativoTradeResult] = {}

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    # -- capacidad compartida (max_concurrent=1) -----------------------------

    def _capacidad_disponible_en(self, entry_ms: int,
                                 exclude_oid: Optional[str] = None) -> bool:
        """Devuelve True si no hay ninguna posicion abierta que cubra entry_ms.

        Una posicion cubre entry_ms si su entrada ya ocurrio (entry_ms_pos <= entry_ms)
        y aun no ha salido (exit_ms es None o exit_ms_pos > entry_ms).
        ``exclude_oid`` permite reprocesar la misma observacion sin bloquearla
        contra si misma.
        """
        for pos_oid, pos in self.open_positions.items():
            if pos_oid == exclude_oid:
                continue
            pos_entry = pos["entry_ms"]
            pos_exit = pos["exit_ms"]
            if pos_entry <= entry_ms and (pos_exit is None or pos_exit > entry_ms):
                return False
        return True

    def _registrar_posicion(self, observation_id: str, entry_ms: int, exit_ms: Optional[int]) -> None:
        self.open_positions[observation_id] = {"entry_ms": entry_ms, "exit_ms": exit_ms}

    def _liberar_posicion(self, observation_id: str) -> None:
        self.open_positions.pop(observation_id, None)

    # -- escritura JSONL -----------------------------------------------------

    def _escribir(self, row: Dict[str, Any]) -> bool:
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        encoded = len(payload.encode("utf-8"))
        self._fh.write(payload)
        self._fh.flush()
        self._bytes += encoded
        self._rows += 1
        return True

    # -- procesamiento de una observacion -----------------------------------

    def procesar_observacion(
        self,
        observacion: Dict[str, Any],
        velas_1m: List[PaperCandle],
        funding_calendar: Optional[FundingCalendar] = None,
    ) -> OperativoTradeResult:
        """Procesa una observacion del piloto y devuelve el resultado de la
        operacion simulada (o abstencion/descarte) sin usar datos futuros.

        La direccion se deriva EXCLUSIVAMENTE de move_24h_pct mediante
        derivar_direccion_desde_movimiento; el rol (candidate/comparator)
        NO determina direccion.
        """
        symbol = str(observacion["symbol"]).upper()
        decision_ms = int(observacion["decision_ms"])
        role = str(observacion.get("role", "comparator"))
        move_24h_pct = observacion.get("seleccion", {}).get("move_24h_pct")
        side_selector = observacion.get("side")  # UP/DOWN del selector (referencia)

        traza: Dict[str, Any] = {
            "observation_id": observacion.get("observation_id"),
            "symbol": symbol,
            "role": role,
            "decision_ms": decision_ms,
            "move_24h_pct": move_24h_pct,
            "side_selector": side_selector,
            "direccion_derivada": derivar_direccion_desde_movimiento(move_24h_pct),
        }
        direccion = traza["direccion_derivada"]["direction"]
        # Calendario de funding por simbolo: parametro de llamada o registro
        # del adaptador; nunca se inventa.
        cal = funding_calendar or self.funding_calendars.get(symbol)

        # Reprocesamiento de observacion ya vista: si ya hay resultado previo
        # y ya tiene salida ejecutada, retornar sin efectos duplicados.
        oid = observacion["observation_id"]
        if oid in self._results:
            prev = self._results[oid]
            if prev.exit_executed:
                return prev
            # Si el previo es open_at_end (sin salida conocida), se sigue
            # procesando con las nuevas velas para ver si ahora se conoce la
            # salida. No se retorna el previo directamente.

        # --- Abstencion por dato ausente o sin senal ---------------------
        if direccion is None:
            self.estado["abstenciones"] += 1
            tr = OperativoTradeResult(
                observation_id=traza["observation_id"],
                symbol=symbol, role=role, direction=None,
                decision="SIN_ENTRADA", decision_ms=decision_ms,
                entry_px=None, entry_ms=None,
                exit_px=None, exit_ms=None,
                exit_reason=None, exit_executed=False,
                open_at_end=False, qty=0.0,
                gross_pnl=0.0, fees=0.0, spread_slip=0.0,
                funding=None, net_pnl=None,
                funding_estado=traza["direccion_derivada"]["reason"],
                config_hash=self._config_hash(),
                engine_version=ENGINE_VERSION_PAPER,
            )
            self._results[oid] = tr
            return tr

        # --- Entrada: referencia de senal y configuracion versionada -----
        # entry_px = close de vela 1m plenamente conocida en T (precio
        # conocido en T). stop_px segun regla congelada.
        vela_conocida = _vela_plenamente_conocida_en(velas_1m, decision_ms)
        if vela_conocida is None:
            self.estado["abstenciones"] += 1
            tr = OperativoTradeResult(
                observation_id=traza["observation_id"],
                symbol=symbol, role=role, direction=direccion,
                decision="SIN_ENTRADA", decision_ms=decision_ms,
                entry_px=None, entry_ms=None,
                exit_px=None, exit_ms=None,
                exit_reason=None, exit_executed=False,
                open_at_end=False, qty=0.0,
                gross_pnl=0.0, fees=0.0, spread_slip=0.0,
                funding=None, net_pnl=None,
                funding_estado="sin vela 1m plenamente conocida en T",
                config_hash=self._config_hash(),
                engine_version=ENGINE_VERSION_PAPER,
            )
            self._results[oid] = tr
            return tr

        entry_px_ref = vela_conocida.close
        stop_pct = self.cfg.stop_distance_pct / 100.0
        if direccion == "LONG":
            stop_px = entry_px_ref * (1.0 - stop_pct)
        else:
            stop_px = entry_px_ref * (1.0 + stop_pct)

        # Calcular entry_ms: open de la primera vela despues de decision_ms.
        velas_ordenadas = sorted(velas_1m, key=lambda c: c.open_time_ms)
        entry_ms_calc = None
        for c in velas_ordenadas:
            if c.open_time_ms > decision_ms:
                entry_ms_calc = c.open_time_ms
                break

        # Capacidad compartida (max_concurrent=1): si ya hay una posicion
        # abierta que cubra el entry_ms, rechazar por capacidad. Se excluye la
        # propia observacion para permitir reprocesamiento sin auto-bloqueo.
        if entry_ms_calc is not None and not self._capacidad_disponible_en(
                entry_ms_calc, exclude_oid=oid):
            self.estado["rechazadas_capacidad"] += 1
            tr = OperativoTradeResult(
                observation_id=traza["observation_id"],
                symbol=symbol, role=role, direction=direccion,
                decision="RECHAZADA_CAPACIDAD", decision_ms=decision_ms,
                entry_px=entry_px_ref, entry_ms=entry_ms_calc,
                exit_px=None, exit_ms=None,
                exit_reason=None, exit_executed=False,
                open_at_end=False, qty=0.0,
                gross_pnl=0.0, fees=0.0, spread_slip=0.0,
                funding=None, net_pnl=None,
                funding_estado="rechazada_por_capacidad",
                config_hash=self._config_hash(),
                engine_version=ENGINE_VERSION_PAPER,
            )
            self._results[oid] = tr
            return tr

        config = PaperSessionConfig(
            symbol=symbol, interval="1m", direction=direccion,
            notional_usdt=self.cfg.notional_usdt,
            entry_px=entry_px_ref, stop_px=stop_px,
            stop_distance_pct=self.cfg.stop_distance_pct,
            horizon_ms=self.cfg.horizon_ms,
            fee_bps=self.cfg.fee_bps,
            spread_bps=self.cfg.spread_bps,
            slippage_bps=self.cfg.slippage_bps,
            rule_version=self.cfg.rule_version,
        )

        state = create_session(
            config, velas_1m,
            hypothesis_id="H1-continuacion",
            hypothesis_version="1.0",
            rule_version=self.cfg.rule_version,
        )
        state = evaluate_session(
            state, rule_version=RULE_VERSION, at_ms=decision_ms,
        )

        # Si el motor no admitio entrada (SIN_ENTRADA / DESCARTADO / en_espera
        # sin fill posible), no hay operacion.
        if state.status != "en_espera":
            self.estado["abstenciones"] += 1
            tr = OperativoTradeResult(
                observation_id=traza["observation_id"],
                symbol=symbol, role=role, direction=direccion,
                decision=state.config.decision or "SIN_ENTRADA",
                decision_ms=decision_ms,
                entry_px=entry_px_ref, entry_ms=None,
                exit_px=None, exit_ms=None,
                exit_reason=None, exit_executed=False,
                open_at_end=False, qty=0.0,
                gross_pnl=0.0, fees=0.0, spread_slip=0.0,
                funding=None, net_pnl=None,
                funding_estado=(state.config.decision_evidence or {}).get(
                    "reason", "sin_fill_posible_en_T"),
                config_hash=self._config_hash(),
                engine_version=ENGINE_VERSION_PAPER,
            )
            self._results[oid] = tr
            return tr

        # --- Fill en open de vela siguiente a la senal (causal) ----------
        # Revelar velas sucesivas hasta que se abra la posicion o se agoten
        # los datos. Cada paso revela el open de la siguiente vela; el fill
        # ocurre en el primer open revelado tras la senal (open_time > T).
        pasos_fill = 0
        while state.status == "en_espera" and not state.position.open:
            reveal_idx = _next_reveal_index(state)
            if reveal_idx is None:
                break
            prev_cursor = state.cursor
            state = step_forward(state)
            pasos_fill += 1
            if pasos_fill > 10_000:
                raise AssertionError(
                    f"Demasiados pasos de fill para {symbol} @ {decision_ms}")
            if state.cursor == prev_cursor:
                # No hubo avance: no hay mas velas para revelar.
                break

        if not state.position.open:
            self.estado["abstenciones"] += 1
            tr = OperativoTradeResult(
                observation_id=traza["observation_id"],
                symbol=symbol, role=role, direction=direccion,
                decision="ENTRADA_SIMULADA", decision_ms=decision_ms,
                entry_px=entry_px_ref, entry_ms=None,
                exit_px=None, exit_ms=None,
                exit_reason=None, exit_executed=False,
                open_at_end=False, qty=0.0,
                gross_pnl=0.0, fees=0.0, spread_slip=0.0,
                funding=None, net_pnl=None,
                funding_estado="sin_fill_en_open_de_vela_siguiente",
                config_hash=self._config_hash(),
                engine_version=ENGINE_VERSION_PAPER,
            )
            self._results[oid] = tr
            return tr

        # Registrar posicion abierta para capacidad compartida.
        self._registrar_posicion(
            observacion["observation_id"], state.position.entry_ms, None)

        # --- Gestion y salida (stop / horizonte / agotamiento) -----------
        pasos = 0
        while state.status == "abierta":
            state = step_forward(state)
            pasos += 1
            if pasos > 10_000:
                raise AssertionError(f"Demasiados pasos para {symbol} @ {decision_ms}")

        r = state.result
        # No duplicar el contador si es una actualización de una observacion
        # ya vista (reprocesamiento con mas velas para resolver open_at_end).
        if oid not in self._results:
            self.estado["operaciones"] += 1
        if r.open_at_end:
            self.estado["posiciones_abiertas_final"] += 1
        # Funding: si hay calendario real para este simbolo, recalcular con
        # run_backtest para contabilizar settlements; si no hay calendario,
        # funding = UNKNOWN (None, nunca cero). paper_lab_engine ya fuerza
        # funding=None cuando no hay calendario real.
        funding = r.funding
        funding_estado = "ninguno (UNKNOWN, no cero)"
        if cal is not None:
            bt = _resultado_con_funding(
                symbol, direccion, velas_1m, decision_ms,
                r.entry_px, r.entry_ms, r.exit_px, r.exit_ms,
                cal, self.cfg,
            )
            if bt is not None:
                funding = bt.get("funding")
                funding_estado = bt.get("funding_model", "settlement-calendar")
                # Sobrescribir net_pnl con el calculado por run_backtest
                # (incluye funding real contabilizado).
                r = _replace_result(r, funding=funding, net_pnl=bt.get("net_pnl"))

        # Solo liberar capacidad cuando se conoce la salida real (stop o
        # horizonte alcanzado). Una posicion open_at_end (sin salida conocida)
        # NO libera capacidad ficticiamente; se mantiene hasta que lleguen mas
        # velas y se pueda resolver en una llamada posterior.
        if r.exit_executed:
            self._liberar_posicion(observacion["observation_id"])

        # Guardar resultado final para evitar reprocesamiento duplicado.
        tr = OperativoTradeResult(
            observation_id=traza["observation_id"],
            symbol=symbol, role=role, direction=direccion,
            decision="ENTRADA_EJECUTADA", decision_ms=decision_ms,
            entry_px=r.entry_px, entry_ms=r.entry_ms,
            exit_px=r.exit_px, exit_ms=r.exit_ms,
            exit_reason=r.exit_reason, exit_executed=r.exit_executed,
            open_at_end=r.open_at_end, qty=r.qty,
            gross_pnl=r.gross_pnl, fees=r.fees,
            spread_slip=r.spread_slip, funding=funding,
            net_pnl=r.net_pnl,
            funding_estado=funding_estado,
            config_hash=self._config_hash(),
            engine_version=ENGINE_VERSION_PAPER,
        )
        self._results[oid] = tr
        return tr

    def persistir(self, tr: OperativoTradeResult) -> None:
        row = {
            "kind": "resultado_operativo",
            "observation_id": tr.observation_id,
            "symbol": tr.symbol,
            "role": tr.role,
            "direction": tr.direction,
            "decision": tr.decision,
            "decision_ms": tr.decision_ms,
            "entry_px": tr.entry_px,
            "entry_ms": tr.entry_ms,
            "exit_px": tr.exit_px,
            "exit_ms": tr.exit_ms,
            "exit_reason": tr.exit_reason,
            "exit_executed": tr.exit_executed,
            "open_at_end": tr.open_at_end,
            "qty": tr.qty,
            "gross_pnl": tr.gross_pnl,
            "fees": tr.fees,
            "spread_slip": tr.spread_slip,
            "funding": tr.funding,
            "funding_estado": tr.funding_estado,
            "net_pnl": tr.net_pnl,
            "config_hash": tr.config_hash,
            "engine_version": tr.engine_version,
            "procedencia": "adapter_operativo_v1",
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }
        self._escribir(row)

    def _config_hash(self) -> str:
        payload = json.dumps(self.cfg.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def resumen(self) -> Dict[str, Any]:
        return dict(self.estado)


# --- Helpers puros ---------------------------------------------------------

def _vela_plenamente_conocida_en(
    velas: List[PaperCandle], at_ms: int,
) -> Optional[PaperCandle]:
    """Vela 1m cuyo OHLC completo se conoce en/before at_ms (close_time <= T)."""
    conocidas = [c for c in velas
                 if c.close_time_ms is not None and c.close_time_ms <= at_ms]
    if not conocidas:
        return None
    return max(conocidas, key=lambda c: c.close_time_ms)


def _candles_de_klines(
    rows: List[Tuple[int, float, float, float, float, int]],
) -> List[PaperCandle]:
    """Convierte filas (open_time_ms, open, high, low, close, close_time_ms)
    en PaperCandle. No rellena huebos ni convierte ausencias en cero."""
    out: List[PaperCandle] = []
    for open_ms, o, h, l, c, close_ms in rows:
        out.append(PaperCandle(
            open_time_ms=int(open_ms), open=float(o), high=float(h),
            low=float(l), close=float(c), close_time_ms=int(close_ms),
        ))
    return out


def _replace_result(
    r: Any, funding: Optional[float], net_pnl: Optional[float],
) -> Any:
    """Devuelve una copia del PaperTradeResult con funding y net_pnl ajustados."""
    from dataclasses import replace
    return replace(r, funding=funding, net_pnl=net_pnl or r.net_pnl)


def _resultado_con_funding(
    symbol: str, direction: str, velas_1m: List[PaperCandle],
    decision_ms: int, entry_px_ref: float, entry_ms: Optional[int],
    exit_px: Optional[float], exit_ms: Optional[int],
    calendar: FundingCalendar,
    cfg: OperativoConfig,
) -> Optional[Dict[str, Any]]:
    """Recalcula el trade con run_backtest y FundingCalendar real para
    contabilizar funding. Reutiliza run_backtest (autoridad economica);
    no copia logica economica.

    Usa las mismas velas 1m y la misma decision_ms que paper_lab_engine,
    para que entrada/salida coincidan y solo se añada el funding contabilizado.
    """
    if calendar is None:
        return None
    try:
        bt_candles = _to_bt_candles(velas_1m, symbol)
    except Exception:
        return None
    ev = StudyEvent(
        symbol=symbol, event_time_ms=decision_ms,
        direction=direction, reference_price=entry_px_ref,
        family="H1", rules_version="H1-v1",
    )
    bt_cfg = BacktestConfig(
        family="H1", rules_version="H1-v1",
        exit_horizon_ms=cfg.horizon_ms,
        stop_distance_pct=cfg.stop_distance_pct,
        notional_usdt=cfg.notional_usdt,
        fee_bps=cfg.fee_bps, spread_bps=cfg.spread_bps,
        slippage_bps=cfg.slippage_bps,
        cost_scale=1.0, max_concurrent=cfg.max_concurrent,
        funding_calendar=calendar,
        funding_estimated_bps=cfg.funding_estimated_bps,
    )
    try:
        res = run_backtest(
            [ev], bt_candles, bt_cfg,
            dataset_id="operativo-funding", segment="dev",
        )
    except Exception:
        return None
    trades = res.get("trades", [])
    if not trades:
        return None
    return trades[0]


def validar_ohlc(c: PaperCandle) -> None:
    """Comprueba que el rango OHLC de una vela es coherente antes de ejecutar
    el motor: low <= min(open, close) <= max(open, close) <= high.

    Una vela abierta legítimamente desconocida mantiene close_time_ms=None;
    en ese caso solo se exige low <= open <= high. No se inventan cierres."""
    import math
    for nombre, valor in (("open", c.open), ("high", c.high),
                          ("low", c.low)):
        if valor is None or not math.isfinite(valor):
            raise ValueError(f"OHLC invalido en {c.open_time_ms}: {nombre}={valor}")
    if c.close is not None and c.close_time_ms is not None:
        if not math.isfinite(c.close):
            raise ValueError(f"OHLC invalido en {c.open_time_ms}: close={c.close}")
        lo = min(c.open, c.close)
        hi = max(c.open, c.close)
        if not (c.low <= lo):
            raise ValueError(
                f"OHLC invalido en {c.open_time_ms}: low={c.low} > min(open,close)={lo}")
        if not (hi <= c.high):
            raise ValueError(
                f"OHLC invalido en {c.open_time_ms}: max(open,close)={hi} > high={c.high}")
    else:
        if not (c.low <= c.open <= c.high):
            raise ValueError(
                f"OHLC invalido en {c.open_time_ms}: low={c.low} > open={c.open} "
                f"o open > high={c.high}")
