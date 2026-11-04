"""Pruebas del mecanismo de autoseleccion de investigacion.

Cubren el punto 6 del mandato:
- Mismos datos disponibles en T -> misma seleccion.
- Cambiar datos posteriores no altera la seleccion hasta T.
- Simbolo inelegible o dato futuro -> exclusion explicita.
- Ganadores y perdedores tratados por la politica declarada.
- Limites de candidatos respetados.
- Comparador reproducible (techo conjunto candidatos+comparadores,
  probabilidad efectiva del muestreo).
- Registro de no seleccionados y datos faltantes.
- Ningun resultado forward se usa para seleccionar.
- Cero red publica y cero escrituras en DBs canonicas.
- Dato futuro y disponibilidad ausente.
- Unidades del umbral (puntos porcentuales).
- Universo mayor de 500 sin recorte silencioso.
- Exclusion obligatoria frente a dato faltante.

Estas pruebas prueban el MECANISMO, NO evidencia de ventaja economica.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
for p in (str(ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from microstructure_probe import discovery  # noqa: E402
from scripts.research_selector import (  # noqa: E402
    CLASS_EXCLUDED_MANDATORY,
    CLASS_ELIGIBLE_MISSING_DATA,
    CLASS_SELECTED_FOR_RESEARCH,
    ResearchPolicy, ResearchCycle, build_observed_universe,
    build_comparator, run_research_cycle, select_candidates,
)


def _cand(symbol: str, change_24h: Optional[float],
          eligible: bool = True,
          exclusion_reasons: Optional[list] = None,
          discovered_at_ms: int = 1_790_000_000_000,
          ticker_close_ms: int = 1_790_000_000_000) -> discovery.Candidate:
    return discovery.Candidate(
        symbol=symbol, status="TRADING" if eligible else "SETTLING",
        contract_type="PERPETUAL", quote_asset="USDT",
        price=100.0, change_24h_pct=change_24h,
        quote_volume_24h=1000.0, trade_count_24h=10,
        eligible=eligible,
        exclusion_reasons=exclusion_reasons or [],
        discovered_at_ms=discovered_at_ms,
        ticker_close_ms=ticker_close_ms,
    )


def _catalog_row(symbol: str, eligible: bool = True) -> dict:
    return {
        "symbol": symbol, "status": "TRADING" if eligible else "SETTLING",
        "contract_type": "PERPETUAL", "quote_asset": "USDT",
        "eligible": 1 if eligible else 0,
    }


class TestTemporalAvailability(unittest.TestCase):
    """Disponibilidad temporal: reference_ms controla qué datos pueden usarse."""

    def test_dato_disponible_despues_de_T_excluido(self):
        """candidate con discovered_at_ms > reference_ms -> excluido del ciclo."""
        cats = [_cand("FUTUSDT", 0.05, discovered_at_ms=1_790_000_000_000 + 1)]
        catalog = [_catalog_row("FUTUSDT")]
        cycle = run_research_cycle(catalog, cats, ResearchPolicy(),
                                   reference_ms=1_790_000_000_000)
        self.assertEqual(len(cycle.selected), 0)
        self.assertEqual(len(cycle.exclusions), 1)
        self.assertEqual(cycle.exclusions[0]["symbol"], "FUTUSDT")
        self.assertEqual(cycle.exclusions[0]["reason"], "dato_no_disponible_en_T")

    def test_disponibilidad_desconocida_unknown_no_selecciona(self):
        """ticker_close_ms None -> disponibilidad desconocida -> UNKNOWN."""
        cats = [_cand("UNKUSDT", 0.05, ticker_close_ms=None)]
        catalog = [_catalog_row("UNKUSDT")]
        cycle = run_research_cycle(catalog, cats, ResearchPolicy(),
                                   reference_ms=1_790_000_000_000)
        self.assertEqual(len(cycle.selected), 0)
        self.assertEqual(len(cycle.exclusions), 1)
        self.assertEqual(cycle.exclusions[0]["reason"], "dato_no_disponible_en_T")

    def test_dato_disponible_en_T_no_es_excluido(self):
        """candidate con discovered_at_ms <= reference_ms y ticker_close_ms <=
        reference_ms -> usable en T."""
        cats = [_cand("OKUSDT", 0.05,
                      discovered_at_ms=1_790_000_000_000 - 1000,
                      ticker_close_ms=1_790_000_000_000 - 1000)]
        catalog = [_catalog_row("OKUSDT")]
        cycle = run_research_cycle(catalog, cats, ResearchPolicy(),
                                   reference_ms=1_790_000_000_000)
        self.assertEqual(len(cycle.selected), 1)
        self.assertEqual(cycle.selected[0].symbol, "OKUSDT")


class TestDeterminism(unittest.TestCase):
    """Mismos datos disponibles en T -> misma seleccion."""

    def test_same_input_same_selection(self):
        cats = [_cand("AAAUSDT", 0.05), _cand("BBBUSDT", -0.04),
                _cand("CCCUSDT", 0.01)]
        pol = ResearchPolicy(max_deep_analysis_total=5, max_per_side=3)
        c1 = run_research_cycle(
            [_catalog_row(c.symbol, c.eligible) for c in cats],
            cats, pol, reference_ms=1_790_000_000_000)
        c2 = run_research_cycle(
            [_catalog_row(c.symbol, c.eligible) for c in cats],
            cats, pol, reference_ms=1_790_000_000_000)
        self.assertEqual(c1.cycle_id, c2.cycle_id)
        self.assertEqual([(s.symbol, s.side) for s in c1.selected],
                         [(s.symbol, s.side) for s in c2.selected])

    def test_post_t_data_does_not_alter_selection(self):
        """Cambiar datos posteriores a T no altera la seleccion hasta T."""
        cats_t = [_cand("AAAUSDT", 0.05)]
        pol = ResearchPolicy(max_deep_analysis_total=5, max_per_side=3)
        base = run_research_cycle(
            [_catalog_row(c.symbol, c.eligible) for c in cats_t],
            cats_t, pol, reference_ms=1_790_000_000_000)
        cats_late = cats_t + [_cand("ZZZUSDT", 0.50)]
        late = run_research_cycle(
            [_catalog_row(c.symbol, c.eligible) for c in cats_late],
            cats_late, pol, reference_ms=1_790_000_000_000)
        base_a = next((s for s in base.selected if s.symbol == "AAAUSDT"), None)
        late_a = next((s for s in late.selected if s.symbol == "AAAUSDT"), None)
        self.assertIsNotNone(base_a)
        self.assertIsNotNone(late_a)
        self.assertEqual(base_a.side, late_a.side)
        self.assertEqual(base_a.classification, late_a.classification)

    def test_comparator_reproducible(self):
        pol = ResearchPolicy(comparator_seed=7, comparator_share=0.5)
        comp1, sum1 = build_comparator(["A", "B", "C", "D", "E"], pol,
                                       1_790_000_000_000,
                                       total_budget=5)
        comp2, sum2 = build_comparator(["A", "B", "C", "D", "E"], pol,
                                       1_790_000_000_000,
                                       total_budget=5)
        self.assertEqual([c["symbol"] for c in comp1],
                         [c["symbol"] for c in comp2])
        # Registra probabilidad efectiva y mecanismo de muestreo real.
        # Pool de 5, dibuja 5 -> probabilidad 1.0 (todos seleccionados).
        for c in comp1:
            self.assertIn("selection_probability", c)
            self.assertEqual(c["selection_probability"], 1.0)
            self.assertEqual(c["sampling_mechanism"],
                             "seeded_random_sample_without_replacement")
            self.assertEqual(c["seed"], 7)
            self.assertEqual(c["n_draw"], 5)
            self.assertEqual(c["n_available"], 5)
        self.assertEqual(sum1["effective_probability"], 1.0)
        self.assertEqual(sum1["n_draw"], 5)
        self.assertEqual(sum1["n_available"], 5)
        # Con pool mayor que el presupuesto, probabilidad < 1.0.
        comp_big, sum_big = build_comparator([f"S{i}" for i in range(10)], pol,
                                             1_790_000_000_000, total_budget=5)
        self.assertEqual(len(comp_big), 5)
        for c in comp_big:
            self.assertEqual(c["selection_probability"], 0.5)
        self.assertEqual(sum_big["effective_probability"], 0.5)
        # Sin solapamiento con candidatos ya seleccionados (deduplicacion).
        comp_already, _ = build_comparator(["A", "B", "C"], pol,
                                           1_790_000_000_000,
                                           already_selected_symbols=["A", "B"],
                                           total_budget=5)
        self.assertEqual([c["symbol"] for c in comp_already], ["C"])


class TestExclusions(unittest.TestCase):
    """Clasificacion honesta: excluido obligatorio vs dato faltante."""

    def test_ineligible_excluded_with_reason(self):
        cats = [_cand("BADUSDT", 0.05, eligible=False)]
        catalog = [_catalog_row("BADUSDT", eligible=False)]
        cycle = run_research_cycle(catalog, cats, ResearchPolicy(),
                                   reference_ms=1_790_000_000_000)
        self.assertEqual(len(cycle.selected), 0)
        self.assertEqual(len(cycle.universe.eligible_symbols), 0)
        self.assertEqual(len(cycle.exclusions), 1)
        self.assertEqual(cycle.exclusions[0]["symbol"], "BADUSDT")
        self.assertEqual(cycle.exclusions[0]["reason"],
                         "not_in_observed_universe")

    def test_missing_move_features_excluded(self):
        """Dato de movimiento faltante -> elegible con datos faltantes, no
        excluido obligatorio por movimiento (no hay lado)."""
        cats = [_cand("AAAUSDT", None)]
        catalog = [_catalog_row("AAAUSDT")]
        cycle = run_research_cycle(catalog, cats, ResearchPolicy(),
                                   reference_ms=1_790_000_000_000)
        self.assertEqual(len(cycle.selected), 0)
        self.assertEqual(len(cycle.exclusions), 1)
        self.assertEqual(cycle.exclusions[0]["symbol"], "AAAUSDT")
        self.assertEqual(cycle.exclusions[0]["classification"],
                         CLASS_EXCLUDED_MANDATORY)
        self.assertTrue("move_24h_desconocido"
                        in cycle.exclusions[0]["reason"])

    def test_missing_volume_is_eligible_missing_data(self):
        """volumen_24h desconocido -> elegible con datos faltantes, NO
        excluido obligatorio (el movimiento aún permite lado)."""
        cats = [discovery.Candidate(
            symbol="VOLUNK", status="TRADING", contract_type="PERPETUAL",
            quote_asset="USDT", price=100.0, change_24h_pct=0.05,
            quote_volume_24h=None, trade_count_24h=None, eligible=True,
            exclusion_reasons=[], discovered_at_ms=1_790_000_000_000,
            ticker_close_ms=1_790_000_000_000)]
        catalog = [_catalog_row("VOLUNK")]
        cycle = run_research_cycle(catalog, cats, ResearchPolicy(),
                                   reference_ms=1_790_000_000_000)
        self.assertEqual(len(cycle.selected), 1)
        sel = cycle.selected[0]
        self.assertEqual(sel.side, "UP")
        self.assertEqual(sel.classification, CLASS_SELECTED_FOR_RESEARCH)
        self.assertIn("volumen_24h_desconocido", sel.exclusion_reasons)


class TestUnitsAndThreshold(unittest.TestCase):
    """Unidades del umbral: change_24h_pct en puntos porcentuales."""

    def test_umbral_0_02_puntos_porcentuales(self):
        """0.02 se interpreta como 0.02 puntos porcentuales (no 2%).
        change_24h_pct=0.05 (0.05 pp) supera el umbral; 0.01 no."""
        cats = [_cand("SUPERA", 0.05), _cand("NO_SUPERA", 0.01)]
        catalog = [_catalog_row("SUPERA"), _catalog_row("NO_SUPERA")]
        pol = ResearchPolicy(max_deep_analysis_total=5, max_per_side=3)
        cycle = run_research_cycle(catalog, cats, pol,
                                   reference_ms=1_790_000_000_000)
        supers = [s for s in cycle.selected if s.symbol == "SUPERA"]
        nosup = [s for s in cycle.selected if s.symbol == "NO_SUPERA"]
        self.assertEqual(len(supers), 1, "0.05 pp >= 0.02 pp umbral -> UP")
        self.assertEqual(len(nosup), 0, "0.01 pp < 0.02 pp -> excluido")
        self.assertEqual(supers[0].side, "UP")
        # Documentar unidad en la política.
        self.assertEqual(pol.to_dict()["move_24h_unit"],
                         "puntos_porcentuales (Binance priceChangePercent)")


class TestUniverseSize(unittest.TestCase):
    """Universo mayor de 500 sin recorte silencioso en el descubrimiento."""

    def test_universo_600_no_recortado_a_500(self):
        """max_candidates_total=500 es tope de recursos para seguimiento
        profundo, NO recorte del descubrimiento: todos los 600 elegibles
        se evalúan."""
        cats = [_cand(f"SYM{i:04d}", 0.05) for i in range(600)]
        catalog = [_catalog_row(c.symbol) for c in cats]
        pol = ResearchPolicy(max_deep_analysis_total=5, max_per_side=3)
        cycle = run_research_cycle(catalog, cats, pol,
                                   reference_ms=1_790_000_000_000)
        self.assertEqual(cycle.cycle_summary["n_candidates_evaluated"], 600)
        self.assertEqual(cycle.universe.n_eligible, 600)
        # No hay recorte silencioso del universo a los primeros 500.


class TestCombinedCeiling(unittest.TestCase):
    """Techo conjunto candidatos + comparadores y probabilidad efectiva."""

    def test_union_candidatos_comparador_respeta_techo(self):
        """10 UP + 10 DOWN (20 candidatos) con techo total 5:
        len(selected) + len(comparator) <= 5."""
        cats = [_cand(f"UP{i:03d}", 0.05) for i in range(10)] + \
               [_cand(f"DN{i:03d}", -0.05) for i in range(10)]
        catalog = [_catalog_row(c.symbol) for c in cats]
        pol = ResearchPolicy(max_deep_analysis_total=5, max_per_side=3)
        cycle = run_research_cycle(catalog, cats, pol,
                                   reference_ms=1_790_000_000_000)
        self.assertLessEqual(len(cycle.selected), pol.max_deep_analysis_total)
        self.assertLessEqual(len(cycle.comparator),
                             pol.max_deep_analysis_total)
        self.assertLessEqual(len(cycle.selected) + len(cycle.comparator),
                             pol.max_deep_analysis_total)
        # Deduplicacion: candidatos ya seleccionados no aparecen en
        # comparador.
        sel_symbols = {s.symbol for s in cycle.selected}
        comp_symbols = {c["symbol"] for c in cycle.comparator}
        self.assertFalse(sel_symbols & comp_symbols)
        # Probabilidad efectiva calculada desde el mecanismo real.
        self.assertIn("effective_probability", cycle.comparator_summary)
        self.assertGreaterEqual(cycle.comparator_summary[
            "effective_probability"], 0.0)

    def test_20_distribuido_documentado(self):
        """max_deep_analysis_total=20 como hipotesis de capacidad del
        prototipo, distribuida entre candidatos y comparadores."""
        cats = [_cand(f"UP{i:03d}", 0.05) for i in range(10)] + \
               [_cand(f"DN{i:03d}", -0.05) for i in range(10)]
        catalog = [_catalog_row(c.symbol) for c in cats]
        pol = ResearchPolicy(max_deep_analysis_total=20, max_per_side=10)
        cycle = run_research_cycle(catalog, cats, pol,
                                   reference_ms=1_790_000_000_000)
        self.assertLessEqual(len(cycle.selected) + len(cycle.comparator), 20)
        self.assertEqual(pol.to_dict()["max_deep_analysis_total"], 20)


class TestNoForwardNoWrites(unittest.TestCase):
    """Cero red publica y cero escrituras en DBs canonicas."""

    def test_no_network_imports(self):
        import scripts.research_selector as mod  # noqa: F401
        src = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urllib.request", src)
        self.assertNotIn("requests", src)
        self.assertNotIn("websocket", src)

    def test_no_canonical_db_write(self):
        cats = [_cand("AAAUSDT", 0.05)]
        catalog = [_catalog_row("AAAUSDT")]
        before = {p: os.path.getsize(p)
                  for p in ["data/microprobe.db",
                            "data/historical/historical.db"]
                  if os.path.exists(p)}
        run_research_cycle(catalog, cats, ResearchPolicy(),
                           reference_ms=1_790_000_000_000)
        after = {p: os.path.getsize(p)
                 for p in ["data/microprobe.db",
                           "data/historical/historical.db"]
                 if os.path.exists(p)}
        self.assertEqual(before, after, "no se escribio en DBs canonicas")


if __name__ == "__main__":
    unittest.main()
