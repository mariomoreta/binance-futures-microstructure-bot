"""Autoseleccion de candidatos PARA INVESTIGACION sobre el universo elegible.

Este modulo NO autoriza operar. Es un protocolo reproducible de seleccion de
candidatos que el sistema puede estudiar sin seleccion manual posterior de
monedas ganadoras.

Reutilizacion (delta minimo, sin segundo motor paralelo):
- discovery.build_candidates: elegibilidad (PERPETUAL/TRADING/USDT/volumen)
  + tabla bilateral (ganadores/perdedores) + puntuacion de movimiento.
- universe.SymbolUniverse: conjunto explicit de simbolos que el pipeline
  puede observar y modelar (sin expansion silenciosa).
- universe_manager: vocabulario de ciclo de vida CORE/HOT reutilizado solo
  como tipo/estado de etiqueta (sin conexiones gestionadas ni gestor de
  rotacion).
- extreme_selector: NO se invoca su calculo. Solo se reutilizan los
  verbos de veredicto WATCH/DESCARTADO como lenguaje. No se afirma
  reutilizacion del calculo de extreme_selector.

Disenio:
- Politica versionada y explicita (invariante durante un ciclo).
- Exploracion amplia: todos los contratos elegibles del catalogo son
  considerados inicialmente; no se eligen seis monedas porque tengan datos
  ni los ganadores finales de un periodo.
- Seleccion de un conjunto acotado para analisis profundo (bounded set).
- Candidatos de ambos lados del movimiento (UP y DOWN).
- Criterios disponibles en T: movimiento, aceleracion, volumen, cobertura;
  liquidez SOLO cuando esta realmente observada (nunca fabricada).
- Limites de candidatos, permanencia/rotacion y motivos de exclusión.
- Separacion entre prioridad de captura y aptitud operativa: todavia no
  se autoriza operar.

Disponibilidad temporal (reference_ms controla lo que puede usarse):
- Un dato cuya marca de disponibilidad (discovered_at_ms o ticker_close_ms)
  sea mayor que reference_ms se excluye de ese ciclo: no se puede usar en T
  informacion que aun no estaba disponible.
- Disponibilidad desconocida -> UNKNOWN; no se afirma seleccion historica
  causal.
- El catalogo estatico actual NO acredita elegibilidad historica en T: se
  trata como referencia estatica, nunca como snapshot de universo en T.
- Se distingue ciclo contemporaneo de prueba de prueba historica: la
  seleccion solo es valida para el instante de referencia dado.

Trazabilidad por ciclo:
- cycle_id, instante de referencia, version de politica.
- Universo observado y su procedencia.
- Candidatos seleccionados y comparadores.
- Variables disponibles, motivos de eleccion/exclusion y datos faltantes.
- Timestamps de disponibilidad.
- Estado: pendiente / evaluable / insuficiente / error.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Reutilizacion de componentes existentes (import bajo demanda para no
# acoplar modulos que el entorno de pruebas pueda no tener listos).
from microstructure_probe import discovery  # noqa: E402
from microstructure_probe.universe import SymbolInfo, SymbolUniverse  # noqa: E402

POLICY_VERSION = "research-selector-v2"

# ---------------------------------------------------------------------------
# Unidades declaradas (punto 2 del mandato)
# ---------------------------------------------------------------------------

# change_24h_pct proviene de discovery.Candidate.change_24h_pct, a su vez de
# Binance priceChangePercent, que se expresa en PUNTOS PORCENTUALES
# (ej. 5.0 = 5%). move_24h_min_abs = 0.02 se interpreta como 0.02 puntos
# porcentuales (hipotesis no validada). La ambigüedad previa (0.02% vs 2%)
# queda documentada aqui como hipotesis; no se cambia el segun resultados.
UNIT_NOTE = (
    "change_24h_pct: puntos porcentuales (convencion Binance priceChangePercent, "
    "5.0 = 5%). move_24h_min_abs = 0.02 puntos porcentuales "
    "(hipotesis no validada; ambiguidad 0.02% vs 2% documentada)."
)


def _num(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _ms(ts: Any) -> Optional[int]:
    try:
        return int(ts)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Politica versionada (fijada antes de resultados nuevos)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResearchPolicy:
    """Politica de autoseleccion de investigacion, version e invariante.

    Ningun umbral aqui autoriza entradas. Son hipotesis de investigacion.
    """

    version: str = POLICY_VERSION
    # Universo: venue/tipo/estado. USD-M perpetuos elegibles segun el
    # catalogo (status TRADING, contractType PERPETUAL, quoteAsset USDT).
    venue: str = "Binance USD-M Futures"
    contract_type: str = "PERPETUAL"
    quote_asset: str = "USDT"
    status_required: str = "TRADING"

    # Exploracion amplia: todo el universo elegible se considera para
    # descubrimiento. max_candidatos es un tope de RECURSOS para el
    # seguimiento profundo, NO un recorte silencioso del universo a los
    # primeros 500. El descubrimiento considera todos los elegibles; el
    # limite aplica a cuantos pasan a analisis profundo.
    max_candidatos: int = 12

    # Seleccion acotada para analisis profundo (bounded set).
    # max_deep_analysis_total es el techo TOTAL de la union candidatos +
    # comparadores (punto 3 del mandato). Se distribuye documentadamente:
    # hasta max_candidatos candidatos (max_per_side por lado) y el resto
    # para comparadores.
    max_deep_analysis_total: int = 20  # hipotesis de capacidad del prototipo
    max_comparadores: int = 8  # reserva explicita para comparadores
    max_per_side: int = 10  # tope por lado (UP / DOWN)

    # Criterios disponibles en T (movimiento, aceleracion, volumen, cobertura).
    # move_24h_min_abs en PUNTOS PORCENTUALES (ver UNIT_NOTE).
    move_24h_min_abs: float = 0.02
    move_recent_1h_min_abs: float = 0.002
    volume_percentile_min: float = 0.5

    # Liquidez solo cuando realmente observada (nunca fabricada).
    require_liquidity_observed: bool = False

    # Permanencia / rotacion: DIFERIDOS. No existe gestor de rotacion en este
    # prototipo; no se construye uno solo para justificar estos campos. Se
    # conservan como estado minimo documentado pero NO se aplican en la
    # seleccion actual.
    min_dwell_cycles: int = 1
    max_cycles_per_symbol: int = 5

    # Semilla del comparador (reproducible).
    comparator_seed: int = 42
    comparator_share: float = 0.25

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "venue": self.venue,
            "contract_type": self.contract_type,
            "quote_asset": self.quote_asset,
            "status_required": self.status_required,
            "max_candidatos": self.max_candidatos,
            "max_comparadores": self.max_comparadores,
            "max_deep_analysis_total": self.max_deep_analysis_total,
            "max_per_side": self.max_per_side,
            "move_24h_min_abs": self.move_24h_min_abs,
            "move_24h_unit": "puntos_porcentuales (Binance priceChangePercent)",
            "move_recent_1h_min_abs": self.move_recent_1h_min_abs,
            "volume_percentile_min": self.volume_percentile_min,
            "require_liquidity_observed": self.require_liquidity_observed,
            "min_dwell_cycles": self.min_dwell_cycles,
            "max_cycles_per_symbol": self.max_cycles_per_symbol,
            "rotation_note": "diferido: no hay gestor de rotacion; no se aplica",
            "comparator_seed": self.comparator_seed,
            "comparator_share": self.comparator_share,
            "unit_note": UNIT_NOTE,
        }


# ---------------------------------------------------------------------------
# Universo observado (desde datos, no desde catalogo actual como historia)
# ---------------------------------------------------------------------------

@dataclass
class ObservedUniverse:
    """Universo observado en un instante T con procedencia."""

    as_of_ms: int
    source: str  # "contract_catalog" / "discovery_snapshot" / "UNKNOWN"
    n_total_catalog: int
    n_eligible: int
    eligible_symbols: List[str]
    exclusion_summary: Dict[str, int]
    procedence: str  # REAL / FIXTURE / UNKNOWN
    # indicador de que el catalogo estatico NO acredita elegibilidad en T
    catalog_is_historical_snapshot: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of_ms": self.as_of_ms,
            "source": self.source,
            "n_total_catalog": self.n_total_catalog,
            "n_eligible": self.n_eligible,
            "eligible_symbols": sorted(self.eligible_symbols),
            "exclusion_summary": self.exclusion_summary,
            "procedence": self.procedence,
            "catalog_is_historical_snapshot": self.catalog_is_historical_snapshot,
        }


def build_observed_universe(catalog_rows: List[Dict[str, Any]],
                            as_of_ms: Optional[int] = None) -> ObservedUniverse:
    """Construye el universo observado desde filas del catalogo.

    Distingue catalogo actual de universo historico conocido en T: el
    catalogo actual es una referencia estatica; no hay snapshot de universo
    en T. catalog_is_historical_snapshot = False: el catalogo no acredita
    elegibilidad historica.
    """
    if as_of_ms is None:
        as_of_ms = int(time.time() * 1000)
    n_total = len(catalog_rows)
    exclusion_summary: Dict[str, int] = {}
    eligible: List[str] = []
    for r in catalog_rows:
        status = r.get("status")
        contract_type = r.get("contract_type")
        quote_asset = r.get("quote_asset")
        eligible_flag = str(r.get("eligible")).lower() in ("1", "true")
        reasons: List[str] = []
        if contract_type != "PERPETUAL":
            reasons.append(f"contract_type={contract_type}")
        if status != "TRADING":
            reasons.append(f"status={status}")
        if quote_asset != "USDT":
            reasons.append(f"quote_asset={quote_asset}")
        if not eligible_flag:
            reasons.append("eligible=0")
        for reason in reasons:
            exclusion_summary[reason] = exclusion_summary.get(reason, 0) + 1
        if not reasons:
            eligible.append(str(r["symbol"]).upper())
    # El universo historico en T es UNKNOWN (no hay snapshot por instante).
    return ObservedUniverse(
        as_of_ms=as_of_ms,
        source="contract_catalog",
        n_total_catalog=n_total,
        n_eligible=len(eligible),
        eligible_symbols=eligible,
        exclusion_summary=exclusion_summary,
        procedence="REAL (catalogo estatico; universo en T = UNKNOWN)",
        catalog_is_historical_snapshot=False,
    )


# ---------------------------------------------------------------------------
# Clasificacion honesta de resultados (punto 4 del mandato)
# ---------------------------------------------------------------------------

CLASS_EXCLUDED_MANDATORY = "excluded_mandatory"
CLASS_ELIGIBLE_MISSING_DATA = "eligible_missing_data"
CLASS_SELECTED_FOR_RESEARCH = "selected_for_research"
CLASS_ELIGIBLE_NOT_SELECTED_QUOTA = "eligible_not_selected_quota"
CLASS_SUITABLE_FOR_ANALYSIS = "suitable_for_analysis"


# ---------------------------------------------------------------------------
# Seleccion automatica de candidatos (ambos lados, bounded set)
# ---------------------------------------------------------------------------

@dataclass
class CandidateSelection:
    """Resultado de seleccion de un candidato para investigacion."""

    symbol: str
    side: str  # "UP" | "DOWN" | None
    move_24h: Optional[float]
    move_1h: Optional[float]
    volume_percentile: Optional[float]
    coverage_ok: bool
    liquidity_observed: bool
    # Clasificacion honesta (una sola, mutuamente exclusiva):
    classification: str = CLASS_ELIGIBLE_MISSING_DATA
    exclusion_reasons: List[str] = field(default_factory=list)
    priority: float = 0.0  # puntuacion de prioridad de estudio (no entrada)
    available_at_ms: Optional[int] = None  # marca de disponibilidad del dato


def _data_available_at_or_before(available_ms: Optional[int],
                                 reference_ms: int) -> bool:
    """Un dato es usable en T solo si su marca de disponibilidad <= reference_ms."""
    if available_ms is None:
        return False  # disponibilidad desconocida -> UNKNOWN, no usable
    return int(available_ms) <= int(reference_ms)


def select_candidates(
        candidates: List[discovery.Candidate],
        universe: ObservedUniverse,
        policy: ResearchPolicy,
        reference_ms: Optional[int] = None,
) -> Tuple[List[CandidateSelection], List[Dict[str, Any]], Dict[str, Any]]:
    """Selecciona candidatos para investigacion siguiendo la politica.

    Devuelve (seleccionados_para_investigacion, exclusiones,
    resumen_ciclo). El comparador se construye aparte con
    build_comparator bajo un techo conjunto candidatos + comparadores.

    Reglas de negocio (hipotesis de investigacion, sin optimizar por
    rentabilidad):
    - Solo simbolos elegibles en el universo observado (exclusion explicita
      si no). El catalogo actual NO se usa como historia de universo en T.
    - Disponibilidad temporal: candidato excluido si su marca de
      disponibilidad > reference_ms; desconocida -> UNKNOWN.
    - Ambos lados del movimiento: UP si cambio_24h >= umbral positivo;
      DOWN si cambio_24h <= umbral negativo.
    - Criterios disponibles en T: movimiento (cambio_24h_pct), volumen
      (quote_volume_24h) y cobertura (ticker 24h disponible).
    - Aceleracion (move_1h), percentil de volumen vs propia historia y
      liquidez NO estan disponibles en discovery.Candidate: se marcan como
      datos faltantes (UNKNOWN, nunca fabricados).
    - Liquidez solo si require_liquidity_observed y esta realmente
      observada (nunca fabricada).
    - Techo TOTAL max_deep_analysis_total para la union candidatos +
      comparadores; max_per_side es techo por lado (no objetivo).
    - No se usa ningun resultado forward para seleccionar.
    """
    if reference_ms is None:
        reference_ms = int(time.time() * 1000)

    eligible_set = set(universe.eligible_symbols)

    # Clasificaciones mutuamente exclusivas:
    # - CLASS_EXCLUDED_MANDATORY: regla obligatoria impide participar
    #   (move_24h desconocido, movimiento por debajo del umbral, no esta en
    #   el universo, dato no disponible en T). Va a exclusiones, NO al pool.
    # - CLASS_ELIGIBLE_MISSING_DATA: lado valido pero faltan datos
    #   (volumen desconocido, percentil desconocido, aceleracion desconocida,
    #   liquidez requerida no observada). Puede ir al pool si tiene lado.
    # - CLASS_SUITABLE_FOR_ANALYSIS: lado valido y sin datos faltantes.
    #   Va al pool; luego puede ser seleccionado o no por cupo.
    obligatoria_reasons = {
        "move_24h_desconocido",
        "not_in_observed_universe",
        "dato_no_disponible_en_T",
    }

    up_pool: List[CandidateSelection] = []
    down_pool: List[CandidateSelection] = []
    all_evaluated: List[CandidateSelection] = []
    exclusions: List[Dict[str, Any]] = []

    for c in candidates:
        sym = str(c.symbol).upper()
        reasons: List[str] = []

        # 0. Disponibilidad temporal: no usar datos disponibles despues de T.
        available_at = _ms(c.discovered_at_ms)
        ticker_close = _ms(c.ticker_close_ms)
        data_available = _data_available_at_or_before(available_at,
                                                      reference_ms) and \
            _data_available_at_or_before(ticker_close, reference_ms)
        if not data_available:
            exclusions.append({
                "symbol": sym,
                "reason": "dato_no_disponible_en_T",
                "classification": CLASS_EXCLUDED_MANDATORY,
                "move_24h": c.change_24h_pct,
                "side": None,
                "available_at_ms": available_at,
                "ticker_close_ms": ticker_close,
                "reference_ms": reference_ms,
            })
            continue

        # 1. Elegibilidad en universo observado.
        if sym not in eligible_set:
            exclusions.append({
                "symbol": sym,
                "reason": "not_in_observed_universe",
                "classification": CLASS_EXCLUDED_MANDATORY,
                "move_24h": c.change_24h_pct,
                "side": None,
                "available_at_ms": available_at,
            })
            continue

        # Datos disponibles en T desde discovery.Candidate.
        move24 = _num(c.change_24h_pct)
        volume_24h = _num(c.quote_volume_24h)
        coverage_ok = c.ticker_close_ms is not None and \
            _data_available_at_or_before(c.ticker_close_ms, reference_ms)

        # Datos NO disponibles en discovery.Candidate (marcar como faltantes,
        # nunca inventar).
        move1h = None
        vol_pct = None
        liquidity_observed = False

        # 2. Criterios de movimiento y volumen (disponibles en T).
        if move24 is None:
            reasons.append("move_24h_desconocido")
        elif abs(move24) < policy.move_24h_min_abs:
            reasons.append(f"movimiento_24h_por_debajo_de_{policy.move_24h_min_abs}")
        if volume_24h is None:
            reasons.append("volumen_24h_desconocido")
        if move1h is None:
            reasons.append("move_1h_desconocido")
        if vol_pct is None:
            reasons.append("volumen_percentil_desconocido")
        if policy.require_liquidity_observed and not liquidity_observed:
            reasons.append("liquidez_no_observada")

        # 3. Lado del movimiento (solo con cambio_24h disponible y suficiente).
        side = None
        if move24 is not None:
            if move24 >= policy.move_24h_min_abs:
                side = "UP"
            elif move24 <= -policy.move_24h_min_abs:
                side = "DOWN"

        # Clasificacion honesta (mutuamente exclusiva).
        tiene_obligatoria = any(
            r in obligatoria_reasons for r in reasons)
        if tiene_obligatoria:
            classification = CLASS_EXCLUDED_MANDATORY
            exclusions.append({
                "symbol": sym,
                "reason": "; ".join(reasons),
                "classification": CLASS_EXCLUDED_MANDATORY,
                "move_24h": move24,
                "side": side,
                "available_at_ms": available_at,
            })
            continue  # no entra al pool
        elif reasons:
            # Datos faltantes que no impiden el lado (volumen, percentil,
            # aceleracion, liquidez).
            classification = CLASS_ELIGIBLE_MISSING_DATA
        else:
            classification = CLASS_SUITABLE_FOR_ANALYSIS

        # Prioridad de estudio (movimiento, volumen; NO entrada, NO rentabilidad).
        priority = 0.0
        if move24 is not None:
            priority += abs(move24) * 3.0
        if volume_24h is not None:
            priority += min(volume_24h / 1e6, 1.0) * 1.0

        sel = CandidateSelection(
            symbol=sym, side=side, move_24h=move24, move_1h=move1h,
            volume_percentile=vol_pct, coverage_ok=coverage_ok,
            liquidity_observed=liquidity_observed,
            classification=classification,
            exclusion_reasons=reasons, priority=priority,
            available_at_ms=available_at,
        )
        all_evaluated.append(sel)

        if side == "UP":
            up_pool.append(sel)
        elif side == "DOWN":
            down_pool.append(sel)

    # Ranking determinista por prioridad (movimiento, volumen).
    def rank_key(s: CandidateSelection):
        return (-(s.priority or 0.0), s.symbol)

    up_pool.sort(key=rank_key)
    down_pool.sort(key=rank_key)

    # 4. Techo TOTAL de union candidatos + comparadores, con limite por lado.
    #    Mezclar ambos pools ordenados por prioridad global y tomar hasta
    #    max_deep_analysis_total, respetando max_per_side como techo por lado.
    all_pool = sorted(up_pool + down_pool, key=rank_key)
    selected_pool: List[CandidateSelection] = []
    count_up = 0
    count_down = 0
    for s in all_pool:
        if len(selected_pool) >= policy.max_candidatos:
            break
        if s.side == "UP" and count_up < policy.max_per_side:
            selected_pool.append(s)
            count_up += 1
        elif s.side == "DOWN" and count_down < policy.max_per_side:
            selected_pool.append(s)
            count_down += 1

    for s in selected_pool:
        s.classification = CLASS_SELECTED_FOR_RESEARCH

    # Los del pool no seleccionados por cupo quedan como
    # CLASS_ELIGIBLE_NOT_SELECTED_QUOTA (mantienen su clasificacion original
    # de ELIGIBLE_MISSING_DATA o SUITABLE si no entraron por cupo).
    selected_set = set(id(s) for s in selected_pool)
    for s in all_evaluated:
        if id(s) not in selected_set and \
                s.classification in (CLASS_SUITABLE_FOR_ANALYSIS,
                                     CLASS_ELIGIBLE_MISSING_DATA):
            s.classification = CLASS_ELIGIBLE_NOT_SELECTED_QUOTA

    # Resumen del ciclo (trazabilidad).
    cycle_summary = {
        "reference_ms": reference_ms,
        "policy_version": policy.version,
        "n_candidates_evaluated": len(candidates),
        "n_eligible_universe": universe.n_eligible,
        "n_selected": len(selected_pool),
        "n_up": count_up,
        "n_down": count_down,
        "n_excluded_mandatory": len([e for e in exclusions
                                     if e["classification"]
                                     == CLASS_EXCLUDED_MANDATORY]),
        "n_eligible_missing_data": len([s for s in all_evaluated
                                        if s.classification
                                        == CLASS_ELIGIBLE_MISSING_DATA]),
        "n_eligible_not_selected_quota": len([s for s in all_evaluated
                                              if s.classification
                                              == CLASS_ELIGIBLE_NOT_SELECTED_QUOTA]),
        "max_candidatos": policy.max_candidatos,
        "max_comparadores": policy.max_comparadores,
        "max_deep_analysis_total": policy.max_deep_analysis_total,
        "max_per_side": policy.max_per_side,
        "liquidity_required": policy.require_liquidity_observed,
        "data_available_at_T": {
            "movement_24h": "disponible (change_24h_pct)",
            "acceleration_1h": "UNKNOWN (no en discovery.Candidate)",
            "volume_24h": "disponible (quote_volume_24h)",
            "volume_percentile_vs_own_history": "UNKNOWN (no serie propia)",
            "liquidity_spread_depth": "UNKNOWN (no historia de libro)",
        },
    }
    return selected_pool, exclusions, cycle_summary


# ---------------------------------------------------------------------------
# Comparador reproducible bajo techo conjunto (punto 3 del mandato)
# ---------------------------------------------------------------------------

def build_comparator(eligible_symbols: List[str],
                     policy: ResearchPolicy,
                     reference_ms: int,
                     already_selected_symbols: Optional[List[str]] = None,
                     total_budget: Optional[int] = None) -> Tuple[
        List[Dict[str, Any]], Dict[str, Any]]:
    """Comparador: muestreo con semilla fijada del mismo universo disponible
    en T, con condiciones de observacion comparables.

    Respeta el techo TOTAL de la union candidatos + comparadores
    (max_deep_analysis_total). Los simbolos ya seleccionados como candidatos
    se deduplican del comparador (no se cuenta dos veces un mismo simbolo
    para contabilizar recursos). No afirma representatividad por tamaño;
    registra probabilidad de muestreo y mecanismo real.

    Devuelve (comparador_list, resumen_comparador).
    """
    rng = random.Random(policy.comparator_seed)
    pool = sorted(set(eligible_symbols))
    already = set(str(s).upper() for s in (already_selected_symbols or []))
    pool_for_comparator = [s for s in pool if s not in already]

    if total_budget is None:
        total_budget = policy.max_deep_analysis_total

    # Probabilidad efectiva del muestreo desde su mecanismo real:
    # seeded random sample sin reemplazo de pool_for_comparator.
    n_available = len(pool_for_comparator)
    n_to_draw = max(0, min(total_budget, n_available))
    chosen = rng.sample(pool_for_comparator, n_to_draw) if n_to_draw > 0 else []

    effective_probability = (n_to_draw / n_available) if n_available > 0 else 0.0

    return [
        {
            "symbol": s,
            "role": "comparator",
            "sampling_mechanism": "seeded_random_sample_without_replacement",
            "seed": policy.comparator_seed,
            "share": policy.comparator_share,
            "reference_ms": reference_ms,
            "selection_probability": effective_probability,
            "n_draw": n_to_draw,
            "n_available": n_available,
        }
        for s in chosen
    ], {
        "n_available": n_available,
        "n_draw": n_to_draw,
        "effective_probability": effective_probability,
        "seed": policy.comparator_seed,
        "mechanism": "seeded_random_sample_without_replacement",
        "budget_total": total_budget,
    }


# ---------------------------------------------------------------------------
# Ciclo de autoseleccion (trazabilidad completa)
# ---------------------------------------------------------------------------

@dataclass
class ResearchCycle:
    """Un ciclo de autoseleccion de investigacion con trazabilidad completa."""

    cycle_id: str
    reference_ms: int
    reference_iso: str
    policy_version: str
    universe: ObservedUniverse
    selected: List[CandidateSelection]
    comparator: List[Dict[str, Any]]
    exclusions: List[Dict[str, Any]]
    cycle_summary: Dict[str, Any]
    comparator_summary: Dict[str, Any]
    state: str  # pending / evaluable / insufficient / error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "reference_ms": self.reference_ms,
            "reference_iso": self.reference_iso,
            "policy_version": self.policy_version,
            "universe": self.universe.to_dict(),
            "selected": [
                {
                    "symbol": s.symbol, "side": s.side,
                    "move_24h": s.move_24h, "move_1h": s.move_1h,
                    "volume_percentile": s.volume_percentile,
                    "coverage_ok": s.coverage_ok,
                    "liquidity_observed": s.liquidity_observed,
                    "classification": s.classification,
                    "exclusion_reasons": s.exclusion_reasons,
                    "priority": s.priority,
                    "available_at_ms": s.available_at_ms,
                }
                for s in self.selected
            ],
            "comparator": self.comparator,
            "exclusions": self.exclusions,
            "cycle_summary": self.cycle_summary,
            "comparator_summary": self.comparator_summary,
            "state": self.state,
        }


def run_research_cycle(catalog_rows: List[Dict[str, Any]],
                       discovery_candidates: List[discovery.Candidate],
                       policy: Optional[ResearchPolicy] = None,
                       reference_ms: Optional[int] = None) -> ResearchCycle:
    """Ejecuta un ciclo completo de autoseleccion de investigacion.

    Produce trazabilidad completa (cycle_id, instante, politica, universo,
    candidatos, comparador, exclusiones, estado).
    """
    if policy is None:
        policy = ResearchPolicy()
    if reference_ms is None:
        reference_ms = int(time.time() * 1000)
    cycle_id = hashlib.sha256(
        f"{policy.version}:{reference_ms}:{len(catalog_rows)}".encode()
    ).hexdigest()[:16]
    reference_iso = datetime.fromtimestamp(reference_ms / 1000,
                                           tz=timezone.utc).isoformat()

    universe = build_observed_universe(catalog_rows, reference_ms)
    selected, exclusions, cycle_summary = select_candidates(
        discovery_candidates, universe, policy, reference_ms)

    # Comparador bajo techo conjunto (candidatos + comparadores <= total).
    # El presupuesto restante es el total menos lo ya usado por candidatos.
    selected_symbols = [s.symbol for s in selected]
    remaining_budget = max(0, min(policy.max_comparadores,
                                policy.max_deep_analysis_total - len(selected)))
    comparator, comparator_summary = build_comparator(
        universe.eligible_symbols, policy, reference_ms,
        already_selected_symbols=selected_symbols,
        total_budget=remaining_budget)

    # Estado del ciclo:
    # - insufficient: sin universo elegible, o no hay ni candidatos ni
    #   comparadores (no hay nada que evaluar).
    # - evaluable: hay al menos un candidato seleccionado O un comparador;
    #   se especifica en cycle_summary lo que se puede evaluar.
    if universe.n_eligible == 0:
        state = "insufficient"
    elif not selected and not comparator:
        state = "insufficient"
    else:
        state = "evaluable"

    return ResearchCycle(
        cycle_id=cycle_id, reference_ms=reference_ms,
        reference_iso=reference_iso, policy_version=policy.version,
        universe=universe, selected=selected, comparator=comparator,
        exclusions=exclusions, cycle_summary=cycle_summary,
        comparator_summary=comparator_summary, state=state,
    )
