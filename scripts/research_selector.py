"""Autoseleccion de candidatos PARA INVESTIGACION sobre el universo elegible.

Este modulo NO autoriza operar. Es un protocolo reproducible de seleccion de
candidatos que el sistema puede estudiar sin seleccion manual posterior de
monedas ganadoras.

Reutiliza (delta minimo, sin segundo motor paralelo):
- discovery.build_candidates: elegibilidad (PERPETUAL/TRADING/USDT/volumen)
  + tabla bilateral (ganadores/perdedores) + puntuacion de movimiento.
- universe.SymbolUniverse: conjunto explicit de simbolos que el pipeline
  puede observar y modelar (sin expansion silenciosa).
- universe_manager: vocabulario de ciclo de vida CORE/HOT y puntuacion
  deterministica como etiquetas de seleccion (sin conexiones gestionadas).
- extreme_selector.select: puntuacion de un dict de caracteristicas
  prefix-causal; veredicto WATCH/DESCARTADO, ranking != entrada.

Diseno:
- Politica versionada y explicita (invariante durante un ciclo).
- Exploracion amplia: todos los contratos elegibles del catalogo son
  considerados; no se eligen seis monedas porque tengan datos ni los
  ganadores finales de un periodo.
- Seleccion de un conjunto acotado para analisis profundo (bounded set).
- Candidatos de ambos lados del movimiento (UP y DOWN).
- Criterios disponibles en T: movimiento, aceleracion, volumen, cobertura;
  liquidez SOLO cuando esta realmente observada (nunca fabricada).
- Limites de candidatos, permanencia/rotacion y motivos de exclusión.
- Separacion entre prioridad de captura y aptitud operativa: todavia no
  se autoriza operar.

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
from microstructure_probe import extreme_selector  # noqa: E402
from microstructure_probe.universe import SymbolInfo, SymbolUniverse  # noqa: E402

POLICY_VERSION = "research-selector-v1"


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
    # Exploracion amplia: todos los elegibles son considerados inicialmente.
    max_candidates_total: int = 500  # tope de descubrimiento, no de operacion
    # Seleccion acotada para analisis profundo (bounded set).
    max_deep_analysis: int = 20
    max_per_side: int = 10  # 10 UP + 10 DOWN como tope de estudio
    # Criterios disponibles en T (movimiento, aceleracion, volumen, cobertura).
    move_24h_min_abs: float = 0.02      # |retorno 24h| minimo para entrar en ranking
    move_recent_1h_min_abs: float = 0.002  # |retorno 1h| minimo
    volume_percentile_min: float = 0.5  # percentil de volumen vs propia historia
    # Liquidez solo cuando realmente observada (nunca fabricada).
    require_liquidity_observed: bool = False  # False hoy: liquidez UNKNOWN
    # Permanencia / rotacion
    min_dwell_cycles: int = 1
    max_cycles_per_symbol: int = 5
    # Semilla del comparador (reproducible).
    comparator_seed: int = 42
    comparator_share: float = 0.25  # 25% del universo elegible como comparador

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "venue": self.venue,
            "contract_type": self.contract_type,
            "quote_asset": self.quote_asset,
            "status_required": self.status_required,
            "max_candidates_total": self.max_candidates_total,
            "max_deep_analysis": self.max_deep_analysis,
            "max_per_side": self.max_per_side,
            "move_24h_min_abs": self.move_24h_min_abs,
            "move_recent_1h_min_abs": self.move_recent_1h_min_abs,
            "volume_percentile_min": self.volume_percentile_min,
            "require_liquidity_observed": self.require_liquidity_observed,
            "min_dwell_cycles": self.min_dwell_cycles,
            "max_cycles_per_symbol": self.max_cycles_per_symbol,
            "comparator_seed": self.comparator_seed,
            "comparator_share": self.comparator_share,
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of_ms": self.as_of_ms,
            "source": self.source,
            "n_total_catalog": self.n_total_catalog,
            "n_eligible": self.n_eligible,
            "eligible_symbols": sorted(self.eligible_symbols),
            "exclusion_summary": self.exclusion_summary,
            "procedence": self.procedence,
        }


def build_observed_universe(catalog_rows: List[Dict[str, Any]],
                            as_of_ms: Optional[int] = None) -> ObservedUniverse:
    """Construye el universo observado desde filas del catalogo.

    Distingue catalogo actual de universo historico conocido en T: el
    catalogo actual es una referencia estatica; no hay snapshot de universo
    en T (procedencia UNKNOWN para el universo historico en T).
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
        reasons = []
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
    # El catalogo actual es referencia estatica con procedencia REAL.
    return ObservedUniverse(
        as_of_ms=as_of_ms,
        source="contract_catalog",
        n_total_catalog=n_total,
        n_eligible=len(eligible),
        eligible_symbols=eligible,
        exclusion_summary=exclusion_summary,
        procedence="REAL (catalogo estatico; universo en T = UNKNOWN)",
    )


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
    exclusion_reasons: List[str] = field(default_factory=list)
    priority: float = 0.0  # puntuacion de prioridad de estudio (no entrada)
    state: str = "pending"  # pending / evaluable / insufficient / error


def select_candidates(
        candidates: List[discovery.Candidate],
        universe: ObservedUniverse,
        policy: ResearchPolicy,
        reference_ms: Optional[int] = None,
) -> Tuple[List[CandidateSelection], List[Dict[str, Any]], Dict[str, Any]]:
    """Selecciona candidatos para investigacion siguiendo la politica.

    Devuelve (seleccionados, comparador_no_incluido, resumen_ciclo).
    El comparador se construye aparte con build_comparator.

    Reglas de negocio (hipotesis de investigacion, sin optimizar por
    rentabilidad):
    - Solo simbolos elegibles en el universo observado (exclusion explicita
      si no). El catalogo actual NO se usa como historia de universo en T.
    - Ambos lados del movimiento: UP si cambio_24h >= umbral positivo;
      DOWN si cambio_24h <= umbral negativo.
    - Criterios disponibles en T: movimiento (cambio_24h_pct), volumen
      (quote_volume_24h) y cobertura (ticker 24h disponible).
    - Aceleracion (move_1h), percentil de volumen vs propia historia y
      liquidez NO estan disponibles en discovery.Candidate: se marcan como
      datos faltantes (UNKNOWN, nunca fabricados).
    - Liquidez solo si require_liquidity_observed y esta realmente
      observada (nunca fabricada).
    - Limite max_deep_analysis en total, max_per_side por lado.
    - No se usa ningun resultado forward para seleccionar.
    """
    if reference_ms is None:
        reference_ms = int(time.time() * 1000)

    eligible_set = set(universe.eligible_symbols)
    selected: List[CandidateSelection] = []
    exclusions: List[Dict[str, Any]] = []

    up_pool: List[CandidateSelection] = []
    down_pool: List[CandidateSelection] = []

    for c in candidates:
        sym = str(c.symbol).upper()
        reasons: List[str] = []

        # 1. Elegibilidad en universo observado (no catalogo actual como
        #    historia; si no esta en el universo observado, exclusión).
        if sym not in eligible_set:
            reasons.append("not_in_observed_universe")
            exclusions.append({"symbol": sym, "reason": "not_in_observed_universe",
                               "move_24h": c.change_24h_pct})
            continue

        # Datos disponibles en T desde discovery.Candidate.
        move24 = _num(c.change_24h_pct)          # disponible
        volume_24h = _num(c.quote_volume_24h)    # disponible
        coverage_ok = c.ticker_close_ms is not None  # disponible

        # Datos NO disponibles en discovery.Candidate (marcar como faltantes,
        # nunca inventar).
        move1h = None  # aceleracion 1h: no disponible en discovery
        vol_pct = None  # percentil de volumen vs propia historia: no disponible
        liquidity_observed = False  # liquidez en T: no disponible hoy

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

        # 3. Lado del movimiento (solo con cambio_24h disponible).
        side = None
        if move24 is not None:
            if move24 >= policy.move_24h_min_abs:
                side = "UP"
            elif move24 <= -policy.move_24h_min_abs:
                side = "DOWN"

        state = "pending"
        if reasons:
            state = "insufficient"

        # Prioridad de estudio (movimiento, volumen; NO entrada, NO rentabilidad).
        priority = 0.0
        if move24 is not None:
            priority += abs(move24) * 3.0
        if volume_24h is not None:
            priority += min(volume_24h / 1e6, 1.0) * 1.0  # normalizado a MM USDT

        sel = CandidateSelection(
            symbol=sym, side=side, move_24h=move24, move_1h=move1h,
            volume_percentile=vol_pct, coverage_ok=coverage_ok,
            liquidity_observed=liquidity_observed,
            exclusion_reasons=reasons, priority=priority, state=state,
        )

        # Registro de no seleccionados y datos faltantes (punto 6):
        # todo candidato evaluado con motivos de exclusión se anota aquí.
        if reasons:
            exclusions.append({
                "symbol": sym,
                "reason": "; ".join(reasons),
                "move_24h": move24,
                "side": side,
            })

        if side == "UP":
            up_pool.append(sel)
        elif side == "DOWN":
            down_pool.append(sel)

    # Ranking determinista por prioridad (movimiento, volumen).
    def rank_key(s: CandidateSelection):
        return (-(s.priority or 0.0), s.symbol)

    up_pool.sort(key=rank_key)
    down_pool.sort(key=rank_key)

    # 4. Limites: por lado y total (bounded set para analisis profundo).
    selected_up = up_pool[:policy.max_per_side]
    selected_down = down_pool[:policy.max_per_side]
    selected = selected_up + selected_down
    selected = selected[:policy.max_deep_analysis]

    for s in selected:
        s.state = "evaluable" if not s.exclusion_reasons else "insufficient"

    # Resumen del ciclo (trazabilidad).
    cycle_summary = {
        "reference_ms": reference_ms,
        "policy_version": policy.version,
        "n_candidates_evaluated": len(candidates),
        "n_eligible_universe": universe.n_eligible,
        "n_selected": len(selected),
        "n_up": len(selected_up),
        "n_down": len(selected_down),
        "n_excluded": len(exclusions),
        "max_deep_analysis": policy.max_deep_analysis,
        "max_per_side": policy.max_per_side,
        "liquidity_required": policy.require_liquidity_observed,
        "n_insufficient": sum(1 for s in selected if s.state == "insufficient"),
        "data_available_at_T": {
            "movement_24h": "disponible (change_24h_pct)",
            "acceleration_1h": "UNKNOWN (no en discovery.Candidate)",
            "volume_24h": "disponible (quote_volume_24h)",
            "volume_percentile_vs_own_history": "UNKNOWN (no serie propia)",
            "liquidity_spread_depth": "UNKNOWN (no historia de libro)",
        },
    }
    return selected, exclusions, cycle_summary


# ---------------------------------------------------------------------------
# Comparador reproducible (seleccion sencilla con semilla fijada)
# ---------------------------------------------------------------------------

def build_comparator(eligible_symbols: List[str],
                     policy: ResearchPolicy,
                     reference_ms: int) -> List[Dict[str, Any]]:
    """Comparador: muestreo con semilla fijada del mismo universo disponible
    en T, con condiciones de observacion comparables.

    No afirma representatividad por observar "decenas de simbolos"; registra
    probabilidad de muestreo y mecanismo.
    """
    rng = random.Random(policy.comparator_seed)
    pool = sorted(eligible_symbols)
    n = max(1, int(len(pool) * policy.comparator_share))
    chosen = rng.sample(pool, min(n, len(pool)))
    return [
        {
            "symbol": s,
            "role": "comparator",
            "sampling_mechanism": "seeded_random_sample",
            "seed": policy.comparator_seed,
            "share": policy.comparator_share,
            "reference_ms": reference_ms,
            "selection_probability": policy.comparator_share,
        }
        for s in chosen
    ]


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
                    "exclusion_reasons": s.exclusion_reasons,
                    "priority": s.priority, "state": s.state,
                }
                for s in self.selected
            ],
            "comparator": self.comparator,
            "exclusions": self.exclusions,
            "cycle_summary": self.cycle_summary,
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
    comparator = build_comparator(universe.eligible_symbols, policy,
                                  reference_ms)

    # Estado del ciclo: insuficiente si no hay universo elegible ni candidatos
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
        exclusions=exclusions, cycle_summary=cycle_summary, state=state,
    )
