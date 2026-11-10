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
        # Capacidad compartida (max_concurrent=1) sobre el conjunto del
        # experimento. Cada operacion admitida ocupa el intervalo
        # [entry_ms, exit_ms) (mismo criterio de backtest_offline: s <= t < e).
        # El intervalo se CONSERVA aunque la salida ya sea conocida: la
        # exposicion existio y puede solaparse con una entrada posterior.
        # exit_ms=None significa salida DESCONOCIDA: la ocupacion sigue
        # abierta (nunca se libera de forma inventada).
        self.intervalos_ocupacion: Dict[str, Dict[str, Optional[int]]] = {}
        # Resultados ya producidos por observation_id, para no reprocesar una
        # observacion terminal (no se bloquea contra si misma, no se duplican
        # admisiones ni resultados) y para que una senal rechazada por
        # capacidad no vuelva a admitirse.
        self._results: Dict[str, OperativoTradeResult] = {}
        # Categorias ya contabilizadas por observation_id (idempotencia del
        # resumen al reprocesar una observacion).
        self._categorias: Dict[str, str] = {}
        # Observaciones que pasaron la puerta de capacidad (idempotente).
        self._admitidas: set = set()
        # Detalle de cobertura del funding por observation_id (evidencia de
        # que el importe acreditado es completo o de que es UNKNOWN).
        self._funding_cuenta: Dict[str, Dict[str, Any]] = {}

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    # -- capacidad compartida (max_concurrent=1) -----------------------------

    def _capacidad_disponible_en(self, entry_ms: int,
                                 exclude_oid: Optional[str] = None) -> bool:
        """Devuelve True si ningun intervalo ocupado cubre ``entry_ms``.

        Regla reutilizada de los motores existentes (``backtest_offline``):
        un intervalo [s, e) ocupa el instante t si ``s <= t < e``. Se
        consideran TODOS los intervalos conocidos, incluidos los ya cerrados
        (la exposicion existio) y los de salida desconocida (``e`` es None:
        ocupacion abierta, sin liberacion inventada).

        ``exclude_oid`` permite reprocesar la misma observacion sin bloquearla
        contra si misma.
        """
        for pos_oid, pos in self.intervalos_ocupacion.items():
            if pos_oid == exclude_oid:
                continue
            pos_entry = pos["entry_ms"]
            pos_exit = pos["exit_ms"]
            if pos_entry is None:
                continue
            if pos_entry <= entry_ms and (pos_exit is None or entry_ms < pos_exit):
                return False
        return True

    def _registrar_posicion(self, observation_id: str, entry_ms: int,
                             exit_ms: Optional[int] = None) -> None:
        """Registra/actualiza el intervalo de ocupacion de una observacion."""
        self.intervalos_ocupacion[observation_id] = {
            "entry_ms": entry_ms, "exit_ms": exit_ms}

    def _actualizar_salida(self, observation_id: str, exit_ms: int) -> None:
        """Acredita la salida real: cierra el intervalo SIN borrarlo.

        Conocer la salida permite admitir entradas posteriores; no borra la
        exposicion que existio antes de la salida.
        """
        pos = self.intervalos_ocupacion.get(observation_id)
        if pos is None:
            return
        if pos["exit_ms"] is None:
            pos["exit_ms"] = exit_ms

    def posiciones_abiertas(self) -> Dict[str, Dict[str, Optional[int]]]:
        """Posiciones con exposicion abierta (salida todavia desconocida)."""
        return {oid: dict(pos) for oid, pos in self.intervalos_ocupacion.items()
                if pos["exit_ms"] is None}

    def intervalos_ocupados(self) -> List[Tuple[str, int, Optional[int]]]:
        """Historial de ocupacion: (observation_id, entry_ms, exit_ms)."""
        return [(oid, int(pos["entry_ms"]), pos["exit_ms"])
                for oid, pos in sorted(self.intervalos_ocupacion.items())
                if pos["entry_ms"] is not None]

    # -- contabilidad idempotente -------------------------------------------

    def _contar(self, observation_id: str, categoria: str) -> None:
        """Contabiliza una categoria principal por observacion (sin duplicar).

        Las categorias principales son mutuas: una observacion cuenta como
        operacion, abstincion, descarte o rechazo por capacidad, nunca en
        dos de ellas a la vez.
        """
        anterior = self._categorias.get(observation_id)
        if anterior == categoria:
            return
        if anterior is not None:
            self.estado[anterior] = max(0, self.estado.get(anterior, 0) - 1)
        self.estado[categoria] = self.estado.get(categoria, 0) + 1
        self._categorias[observation_id] = categoria

    def _marcar_admitida(self, observation_id: str) -> None:
        """Marca la observacion como admitida por la puerta de capacidad."""
        if observation_id in self._admitidas:
            return
        self._admitidas.add(observation_id)
        self.estado["admitidas"] = self.estado.get("admitidas", 0) + 1

    @staticmethod
    def _es_terminal(tr: "OperativoTradeResult") -> bool:
        """True si el resultado ya no puede cambiar con mas velas.

        Terminal: salida ejecutada, rechazo por capacidad, abstencion por
        senal/datos y descarte. Reprocesable: posicion abierta (salida
        desconocida) o senal todavia sin fill (pueden llegar mas velas).
        """
        if tr.exit_executed:
            return True
        if tr.decision in ("RECHAZADA_CAPACIDAD", "SIN_ENTRADA", "DESCARTADO"):
            return True
        if tr.decision == "ENTRADA_SIMULADA" and tr.entry_ms is None:
            return False
        if tr.open_at_end and not tr.exit_executed:
            return False
        return True

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

        # Resultado previo de la misma observacion. Un resultado TERMINAL se
        # devuelve tal cual: no se duplican efectos ni contadores, una senal
        # rechazada por capacidad no vuelve a admitirse y una operacion ya
        # cerrada no se reejecuta. Solo se reprocesa lo que aun puede
        # cambiar: una posicion abierta (salida desconocida) o una senal sin
        # fill todavia (pueden llegar mas velas).
        oid = observacion["observation_id"]
        prev = self._results.get(oid)
        if prev is not None and self._es_terminal(prev):
            return prev

        # --- Abstencion por dato ausente o sin senal ---------------------
        if direccion is None:
            self._contar(oid, "abstenciones")
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
            self._contar(oid, "abstenciones")
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

        # Capacidad compartida (max_concurrent=1): si algun intervalo ocupado
        # (abierto o historico) cubre el entry_ms, rechazar por capacidad. Se
        # excluye la propia observacion para permitir reprocesamiento sin
        # auto-bloqueo. Un rechazo es TERMINAL: la senal no puede re-admitirse
        # mas adelante.
        if entry_ms_calc is not None and not self._capacidad_disponible_en(
                entry_ms_calc, exclude_oid=oid):
            self._contar(oid, "rechazadas_capacidad")
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

        # La senal pasa la puerta de capacidad: queda admitida para intentar
        # la entrada (mas abajo aun puede abstenerse o descartarse).
        self._marcar_admitida(oid)

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
            self._contar(oid, "descartes" if (state.config.decision or "")
                         == "DESCARTADO" else "abstenciones")
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
            self._contar(oid, "abstenciones")
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

        # Registrar el intervalo de ocupacion de la posicion admitida. La
        # salida todavia no se conoce: la ocupacion queda ABIERTA (nunca se
        # libera de forma inventada) y se actualiza al acreditarse la salida.
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
        # Contadores idempotentes: una operacion no se cuenta dos veces si la
        # observacion se reprocesa con mas velas.
        self._contar(oid, "operaciones")
        # Posicion con salida desconocida: sigue abierta y ocupa capacidad.
        if r.open_at_end:
            self.estado["posiciones_abiertas_final"] = len(
                self.posiciones_abiertas())
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
                self._funding_cuenta[oid] = _detalle_funding(bt, cal)
                if _funding_acreditable(bt, cal):
                    funding = bt.get("funding")
                    funding_estado = bt.get(
                        "funding_model", "settlement-calendar")
                    # Sobrescribir net_pnl con el calculado por run_backtest
                    # (incluye funding real contabilizado).
                    r = _replace_result(
                        r, funding=funding, net_pnl=bt.get("net_pnl"))
                else:
                    # Cobertura insuficiente: el importe parcial NO se
                    # acredita. Funding = UNKNOWN y el neto se publica
                    # condicionado (sin funding), nunca como cero.
                    funding = None
                    funding_estado = (
                        "settlement-calendar incompleto (UNKNOWN, no cero)")

        # Salida real acreditada: cierra el intervalo de ocupacion SIN
        # borrarlo (la exposicion existio y puede solaparse con una entrada
        # posterior). Una posicion open_at_end (sin salida conocida) mantiene
        # la ocupacion abierta.
        if r.exit_executed and r.exit_ms is not None:
            self._actualizar_salida(observacion["observation_id"], int(r.exit_ms))
        self.estado["posiciones_abiertas_final"] = len(self.posiciones_abiertas())

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

    def procesar_observaciones(
        self,
        observaciones: List[Dict[str, Any]],
        velas_por_observacion: Dict[str, List[PaperCandle]],
        funding_calendar: Optional[FundingCalendar] = None,
    ) -> List[OperativoTradeResult]:
        """Procesa un lote con prioridad determinista.

        Orden: (decision_ms, symbol, observation_id). El rol
        candidate/comparator NO participa del orden ni de la direccion, y no
        se consulta ningun resultado posterior (ni beneficios ni desenlaces)
        para decidir a quien se admite.
        """
        ordenadas = sorted(
            observaciones,
            key=lambda o: (int(o["decision_ms"]),
                           str(o["symbol"]).upper(),
                           str(o["observation_id"])))
        resultados: List[OperativoTradeResult] = []
        for obs in ordenadas:
            oid = str(obs["observation_id"])
            velas = velas_por_observacion.get(oid, [])
            cal = funding_calendar or self.funding_calendars.get(
                str(obs["symbol"]).upper())
            resultados.append(
                self.procesar_observacion(obs, velas, funding_calendar=cal))
        return resultados

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
        detalle = self._funding_cuenta.get(tr.observation_id)
        if detalle:
            row.update(detalle)
        self._escribir(row)

    def _config_hash(self) -> str:
        payload = json.dumps(self.cfg.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def resumen(self) -> Dict[str, Any]:
        out = dict(self.estado)
        # Ocupacion viva: posiciones abiertas (salida desconocida) frente al
        # historial completo de intervalos [entry_ms, exit_ms).
        out["posiciones_abiertas"] = sorted(self.posiciones_abiertas())
        out["intervalos_ocupacion"] = [
            {"observation_id": oid, "entry_ms": entry_ms, "exit_ms": exit_ms}
            for oid, entry_ms, exit_ms in self.intervalos_ocupados()
        ]
        return out


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


def _funding_acreditable(bt: Dict[str, Any], cal: Optional[FundingCalendar]) -> bool:
    """True si el importe de funding puede acreditarse como completo.

    No se acredita un importe parcial: si algun settlement de la exposicion
    quedo sin mark utilizable, si hay huecos interiores sobre la exposicion o
    si el calendario no declara cadencia nominal (integridad interior
    UNKNOWN), el funding queda UNKNOWN (nunca cero ni parcial).
    """
    if cal is None or bt is None:
        return False
    if cal.interval_ms is None:
        return False
    if int(bt.get("funding_unknown") or 0) > 0:
        return False
    if int(bt.get("funding_gap_ms") or 0) > 0:
        return False
    return True


def _detalle_funding(bt: Dict[str, Any], cal: FundingCalendar) -> Dict[str, Any]:
    """Detalle de cobertura del funding para la fila persistida."""
    return {
        "funding_cuenta_completa": bool(bt.get("funding_accounting_complete")),
        "funding_sin_cubrir_ms": int(bt.get("funding_uncovered_ms") or 0),
        "funding_huecos_ms": int(bt.get("funding_gap_ms") or 0),
        "funding_settlements_desconocidos": int(bt.get("funding_unknown") or 0),
        "funding_calendario": {
            "version": cal.version,
            "source": cal.source,
            "symbol": cal.symbol,
            "interval_ms": cal.interval_ms,
            "hash": cal.calendar_hash(),
        },
    }


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
