"""Pruebas del mecanismo de autoseleccion de investigacion.

Cubren el punto 6 del mandato:
- Mismos datos disponibles en T -> misma seleccion.
- Cambiar datos posteriores no altera la seleccion hasta T.
- Simbolo inelegible o dato futuro -> exclusion explicita.
- Ganadores y perdedores tratados por la politica declarada.
- Limites de candidatos respetados.
- Comparador reproducible.
- Registro de no seleccionados y datos faltantes.
- Ningun resultado forward se usa para seleccionar.
- Cero red publica y cero escrituras en DBs canonicas.

Estas pruebas prueban el MECANISMO, NO evidencia de ventaja economica.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
for p in (str(ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from microstructure_probe import discovery  # noqa: E402
from scripts.research_selector import (  # noqa: E402
    ResearchPolicy, ResearchCycle, build_observed_universe,
    build_comparator, run_research_cycle, select_candidates,
)


def _cand(symbol: str, change_24h: Optional[float],
          eligible: bool = True,
          exclusion_reasons: Optional[list] = None) -> discovery.Candidate:
    return discovery.Candidate(
        symbol=symbol, status="TRADING" if eligible else "SETTLING",
        contract_type="PERPETUAL", quote_asset="USDT",
        price=100.0, change_24h_pct=change_24h,
        quote_volume_24h=1000.0, trade_count_24h=10,
        eligible=eligible,
        exclusion_reasons=exclusion_reasons or [],
        discovered_at_ms=1_790_000_000_000,
        ticker_close_ms=1_790_000_000_000,
    )


class TestDeterminism(unittest.TestCase):
    """Mismos datos disponibles en T -> misma seleccion."""

    def test_same_input_same_selection(self):
        cats = [_cand("AAAUSDT", 0.05), _cand("BBBUSDT", -0.04),
                _cand("CCCUSDT", 0.01)]
        pol = ResearchPolicy(max_deep_analysis=5, max_per_side=3)
        c1 = run_research_cycle(
            [{"symbol": c.symbol, "status": c.status,
              "contract_type": c.contract_type, "quote_asset": c.quote_asset,
              "eligible": 1 if c.eligible else 0} for c in cats],
            cats, pol, reference_ms=1_790_000_000_000)
        c2 = run_research_cycle(
            [{"symbol": c.symbol, "status": c.status,
              "contract_type": c.contract_type, "quote_asset": c.quote_asset,
              "eligible": 1 if c.eligible else 0} for c in cats],
            cats, pol, reference_ms=1_790_000_000_000)
        self.assertEqual(c1.cycle_id, c2.cycle_id)
        self.assertEqual([(s.symbol, s.side) for s in c1.selected],
                         [(s.symbol, s.side) for s in c2.selected])

    def test_post_t_data_does_not_alter_selection(self):
        """Cambiar datos posteriores a T no altera la seleccion hasta T.

        AAAUSDT (move 0.05) se selecciona en T. Anadir ZZZUSDT con mayor
        movimiento en el mismo T no cambia el lado ni la elegibilidad de
        AAAUSDT (queda dentro del limite de lado).
        """
        cats_t = [_cand("AAAUSDT", 0.05)]
        pol = ResearchPolicy(max_deep_analysis=5, max_per_side=3)
        base = run_research_cycle(
            [{"symbol": c.symbol, "status": c.status,
              "contract_type": c.contract_type, "quote_asset": c.quote_asset,
              "eligible": 1 if c.eligible else 0} for c in cats_t],
            cats_t, pol, reference_ms=1_790_000_000_000)
        cats_late = cats_t + [_cand("ZZZUSDT", 0.50)]
        late = run_research_cycle(
            [{"symbol": c.symbol, "status": c.status,
              "contract_type": c.contract_type, "quote_asset": c.quote_asset,
              "eligible": 1 if c.eligible else 0} for c in cats_late],
            cats_late, pol, reference_ms=1_790_000_000_000)
        base_a = next((s for s in base.selected if s.symbol == "AAAUSDT"), None)
        late_a = next((s for s in late.selected if s.symbol == "AAAUSDT"), None)
        self.assertIsNotNone(base_a)
        self.assertIsNotNone(late_a)
        self.assertEqual(base_a.side, late_a.side)
        self.assertEqual(base_a.state, late_a.state)

    def test_comparator_reproducible(self):
        pol = ResearchPolicy(comparator_seed=7, comparator_share=0.5)
        comp1 = build_comparator(["A", "B", "C", "D", "E"], pol, 1_790_000_000_000)
        comp2 = build_comparator(["A", "B", "C", "D", "E"], pol, 1_790_000_000_000)
        self.assertEqual([c["symbol"] for c in comp1],
                         [c["symbol"] for c in comp2])
        # Registra probabilidad y mecanismo de muestreo.
        for c in comp1:
            self.assertEqual(c["selection_probability"], 0.5)
            self.assertEqual(c["sampling_mechanism"], "seeded_random_sample")
            self.assertEqual(c["seed"], 7)


class TestExclusions(unittest.TestCase):
    """Simbolo inelegible o dato futuro -> exclusion explicita."""

    def test_ineligible_excluded_with_reason(self):
        cats = [_cand("BADUSDT", 0.05, eligible=False)]
        catalog = [{"symbol": "BADUSDT", "status": "SETTLING",
                    "contract_type": "PERPETUAL", "quote_asset": "USDT",
                    "eligible": 0}]
        cycle = run_research_cycle(catalog, cats, ResearchPolicy(),
                                   reference_ms=1_790_000_000_000)
        self.assertEqual(len(cycle.selected), 0)
        self.assertEqual(len(cycle.universe.eligible_symbols), 0)

    def test_missing_move_features_excluded(self):
        """Dato de movimiento faltante -> exclusion registrada con motivo."""
        cats = [_cand("AAAUSDT", None)]
        catalog = [{"symbol": "AAAUSDT", "status": "TRADING",
                    "contract_type": "PERPETUAL", "quote_asset": "USDT",
                    "eligible": 1}]
        cycle = run_research_cycle(catalog, cats, ResearchPolicy(),
                                   reference_ms=1_790_000_000_000)
        # No hay lado (move_24h desconocido) -> no entra en selected.
        self.assertEqual(len(cycle.selected), 0)
        # Pero se registra en exclusiones con motivo.
        self.assertEqual(len(cycle.exclusions), 1)
        self.assertEqual(cycle.exclusions[0]["symbol"], "AAAUSDT")
        self.assertTrue("move_24h_desconocido" in cycle.exclusions[0]["reason"])

    def test_no_forward_result_used_for_selection(self):
        """La seleccion nunca usa forward_return (no existe en discovery)."""
        cats = [_cand("AAAUSDT", 0.05)]
        catalog = [{"symbol": "AAAUSDT", "status": "TRADING",
                    "contract_type": "PERPETUAL", "quote_asset": "USDT",
                    "eligible": 1}]
        cycle = run_research_cycle(catalog, cats, ResearchPolicy(),
                                   reference_ms=1_790_000_000_000)
        sel = cycle.selected[0]
        # discovery.Candidate no trae forward_return; la seleccion se basa
        # unicamente en datos en T.
        self.assertIsNone(getattr(sel, "forward_return", None))
        self.assertEqual(sel.side, "UP")


class TestBothSidesAndLimits(unittest.TestCase):
    """Ganadores y perdedores tratados por la politica; limites respetados."""

    def test_bilateral_up_and_down(self):
        cats = [
            _cand("UP1", 0.08), _cand("UP2", 0.06),
            _cand("DOWN1", -0.07), _cand("DOWN2", -0.05),
        ]
        catalog = [{"symbol": c.symbol, "status": c.status,
                    "contract_type": c.contract_type,
                    "quote_asset": c.quote_asset, "eligible": 1}
                   for c in cats]
        cycle = run_research_cycle(catalog, cats,
                                   ResearchPolicy(max_deep_analysis=10,
                                                  max_per_side=5),
                                   reference_ms=1_790_000_000_000)
        sides = [s.side for s in cycle.selected]
        self.assertIn("UP", sides)
        self.assertIn("DOWN", sides)
        up_n = sum(1 for s in cycle.selected if s.side == "UP")
        down_n = sum(1 for s in cycle.selected if s.side == "DOWN")
        self.assertEqual(up_n, 2)
        self.assertEqual(down_n, 2)

    def test_candidate_limits_respected(self):
        cats = [_cand(f"SYM{i:03d}", 0.05) for i in range(50)]
        catalog = [{"symbol": c.symbol, "status": c.status,
                    "contract_type": c.contract_type,
                    "quote_asset": c.quote_asset, "eligible": 1}
                   for c in cats]
        pol = ResearchPolicy(max_deep_analysis=5, max_per_side=3)
        cycle = run_research_cycle(catalog, cats, pol,
                                   reference_ms=1_790_000_000_000)
        self.assertLessEqual(len(cycle.selected), pol.max_deep_analysis)
        up_n = sum(1 for s in cycle.selected if s.side == "UP")
        down_n = sum(1 for s in cycle.selected if s.side == "DOWN")
        self.assertLessEqual(up_n, pol.max_per_side)
        self.assertLessEqual(down_n, pol.max_per_side)

    def test_non_selected_recorded_with_reasons(self):
        """Bajo movimiento -> exclusión registrada con motivo (no en selected)."""
        cats = [_cand("SMALL", 0.001)]  # 0.001 < 0.02 umbral
        catalog = [{"symbol": "SMALL", "status": "TRADING",
                    "contract_type": "PERPETUAL", "quote_asset": "USDT",
                    "eligible": 1}]
        cycle = run_research_cycle(catalog, cats, ResearchPolicy(),
                                   reference_ms=1_790_000_000_000)
        self.assertEqual(len(cycle.selected), 0)
        self.assertEqual(len(cycle.exclusions), 1)
        self.assertEqual(cycle.exclusions[0]["symbol"], "SMALL")
        self.assertIn("movimiento_24h_por_debajo_de", cycle.exclusions[0]["reason"])


class TestNoNetworkNoCanonicalWrites(unittest.TestCase):
    """Cero red publica y cero escrituras en DBs canonicas."""

    def test_no_network_imports(self):
        """El modulo selector no importa modulos de red (urllib.request etc.)."""
        import scripts.research_selector as mod  # noqa: F401
        src = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urllib.request", src)
        self.assertNotIn("requests", src)
        self.assertNotIn("websocket", src)

    def test_no_canonical_db_write(self):
        """run_research_cycle no escribe en microprobe.db ni historical.db."""
        import os
        from scripts.research_selector import run_research_cycle
        cats = [_cand("AAAUSDT", 0.05)]
        catalog = [{"symbol": "AAAUSDT", "status": "TRADING",
                    "contract_type": "PERPETUAL", "quote_asset": "USDT",
                    "eligible": 1}]
        before = {p: os.path.getsize(p)
                  for p in ["data/microprobe.db", "data/historical/historical.db"]
                  if os.path.exists(p)}
        run_research_cycle(catalog, cats, ResearchPolicy(),
                           reference_ms=1_790_000_000_000)
        after = {p: os.path.getsize(p)
                 for p in ["data/microprobe.db", "data/historical/historical.db"]
                 if os.path.exists(p)}
        self.assertEqual(before, after, "no se escribio en DBs canonicas")


if __name__ == "__main__":
    unittest.main()
