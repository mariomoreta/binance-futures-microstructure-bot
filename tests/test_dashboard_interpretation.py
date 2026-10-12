"""Dashboard interpretation: data-backed fields, honest UNKNOWNs.

Proves on TEMP stores exclusively: funding snapshot from persisted
markPrice arrays (quoted context vs UNKNOWN settled/calendar), row
as_of on return features, state evidence + phase timing, OI base-unit
labeling, VWAP window/anchor rows, live 24h rows, and the absence of
normative RSI labels and execution buttons. Run: python run_tests.py
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from microstructure_probe.dashboard import DashboardState
from microstructure_probe.dashboard_data import funding_snapshot
from microstructure_probe.persistence import PersistenceStore


def _rmtree(path: Path) -> None:
    try:
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
    except OSError:
        pass


def _temp_store(case):
    tmp = Path(tempfile.mkdtemp(prefix="interp_"))
    case.addCleanup(lambda: _rmtree(tmp))
    store = PersistenceStore(tmp / "probe.db")
    store.init_db()
    case.addCleanup(store.close)
    return store


def _t0():
    return 1_700_000_000_000


class FundingSnapshotTest(unittest.TestCase):
    def _seed_multi(self, store, items):
        store.store_market_observation(
            symbol="MULTI", stream_type="!markPrice@arr@1s",
            payload={"items": items},
            normalized={"symbol": "MULTI", "stream": "!markPrice@arr@1s",
                        "count": len(items)},
            event_time_ms=None, transaction_time_ms=None, is_valid=True)

    def test_quoted_fields_from_latest_array(self) -> None:
        store = _temp_store(self)
        self._seed_multi(store, [
            {"s": "BTCUSDT", "E": _t0(), "T": _t0() + 3600_000,
             "p": "50000", "r": "0.0001"},
            {"s": "ETHUSDT", "E": _t0(), "T": _t0() + 7200_000,
             "p": "3000", "r": "-0.0002"},
        ])
        snap = funding_snapshot(store, "BTCUSDT")
        self.assertEqual(snap["next_funding_time_ms"], _t0() + 3600_000)
        self.assertAlmostEqual(snap["funding_rate"], 0.0001)
        self.assertIsNotNone(snap["observation_ms"])
        self.assertEqual(snap["settled_history"], "UNKNOWN")
        self.assertEqual(snap["calendar"], "UNKNOWN")
        eth = funding_snapshot(store, "ethusdt")
        self.assertEqual(eth["next_funding_time_ms"], _t0() + 7200_000)
        self.assertAlmostEqual(eth["funding_rate"], -0.0002)

    def test_absent_data_is_unknown(self) -> None:
        store = _temp_store(self)
        snap = funding_snapshot(store, "BTCUSDT")
        self.assertEqual(snap["symbol"], "BTCUSDT")
        self.assertIsNone(snap["next_funding_time_ms"])
        self.assertIsNone(snap["funding_rate"])
        self.assertIsNone(snap["observation_ms"])

    def test_malformed_items_never_raise(self) -> None:
        store = _temp_store(self)
        self._seed_multi(store, [{"s": "BTCUSDT", "p": "x"},
                                 "garbage", {"s": "BTCUSDT", "T": "nan",
                                             "r": "inf"}])
        snap = funding_snapshot(store, "BTCUSDT")
        self.assertIsNone(snap["next_funding_time_ms"])
        self.assertIsNone(snap["funding_rate"])


class ReturnAsOfTest(unittest.TestCase):
    def test_reader_attaches_updated_ms(self) -> None:
        store = _temp_store(self)
        store.store_return_features([{
            "symbol": "BTCUSDT", "current_price": 50000.0,
            "returns": {"1m": 0.001}, "momentum": {"velocity": {},
                                                   "acceleration": {}},
            "tier": "CORE"}])
        rows = store.latest_return_features()
        self.assertEqual(len(rows), 1)
        self.assertIn("updated_ms", rows[0])
        self.assertGreater(rows[0]["updated_ms"], 0)


class TokenViewTest(unittest.TestCase):
    def _state(self, seed_oi=True):
        from microstructure_probe.dashboard_views import render_symbol
        from microstructure_probe.history_store import HistoryStore

        store = _temp_store(self)
        now_ms = int(time.time() * 1000)
        store.store_return_features([{
            "symbol": "BTCUSDT", "current_price": 50000.0,
            "source": "markPrice", "source_timestamp_ms": now_ms - 5000,
            "sample_age_ms": 5000, "history_span_ms": 25 * 3600_000,
            "returns": {"1m": 0.001, "3m": 0.002, "5m": 0.003,
                        "15m": 0.004, "1h": 0.005, "4h": 0.006,
                        "24h": 0.05},
            "anchor_ms": {"1m": now_ms - 60000, "3m": now_ms - 180000,
                          "5m": now_ms - 300000, "15m": now_ms - 900000,
                          "1h": now_ms - 3600000, "4h": now_ms - 14400000,
                          "24h": now_ms - 86400000},
            "available_tfs": ["1m", "3m", "5m", "15m", "1h", "4h", "24h"],
            "warmup_complete": True, "tier": "CORE",
            "momentum": {"velocity": {"1m": 1e-6},
                         "acceleration": {"1m": None}},
            "ranks": {"velocity_1m": {"rank": 1, "change": 0}}}])
        store.store_state_features([{
            "symbol": "BTCUSDT", "state": "EXPANSION", "direction": "UP",
            "observed_at_ms": now_ms - 2000, "rules_version": "v0.1.0",
            "evidence_for": ["range_expansion_15m 2.10"],
            "evidence_against": ["flow contradicts (ratio -0.40 vs UP)"],
            "missing_features": ["oi_divergence"],
            "features_used": ["velocity_1m", "return_15m"],
            "validity": {"reasons": ["fresh"]},
            "transition": {"previous_state": "IGNITION",
                           "previous_direction": "UP", "changed": True,
                           "state_since_ms": now_ms - 60_000,
                           "duration_ms": 58_000, "reasons": ["confirmed"]}}])
        if seed_oi:
            store.store_oi_features([{
                "symbol": "BTCUSDT", "current_oi": 1000.0,
                "current_fetch_ms": now_ms - 1000,
                "freshness_ms": 1000, "stale": False,
                "acceleration_per_s2": 0.0,
                "horizons": {"1m": {"delta": 10.0, "rate": 0.5},
                             "5m": {"delta": 20.0},
                             "15m": {"delta": 30.0}},
                "price_oi_context": {"1m": "PRICE_UP_OI_UP"}}])
        state = DashboardState(
            store,
            history_store=HistoryStore(
                store.db_path.parent / "historical.db"))
        html = render_symbol(state, "BTCUSDT")
        self.assertIsNotNone(html)
        return html

    def test_reference_and_anchor_rendered(self) -> None:
        html = self._state()
        self.assertIn("Reference", html)
        self.assertIn("24h anchor time", html)
        self.assertIn("row as-of (persisted)", html)
        self.assertIn("UNKNOWN", html)  # attribution split unknown
        self.assertIn("24h change (REST discovery)", html)

    def test_state_evidence_and_phase_timing(self) -> None:
        html = self._state()
        self.assertIn("range_expansion_15m 2.10", html)
        self.assertIn("flow contradicts", html)
        self.assertIn("oi_divergence", html)
        self.assertIn("phase since (transition time)", html)
        self.assertIn("phase duration", html)
        self.assertIn("IGNITION", html)

    def test_oi_units_and_unknowns_labeled(self) -> None:
        html = self._state()
        self.assertIn("base units", html)
        self.assertIn("Valued (notional) OI: UNKNOWN", html)
        self.assertIn("Long/short account ratios", html)

    def test_no_normative_labels_no_buttons(self) -> None:
        html = self._state()
        lowered = html.lower()
        self.assertNotIn("debe corregir", lowered)
        self.assertNotIn("debe recuperar", lowered)
        self.assertNotIn("must correct", lowered)
        self.assertNotIn("must recover", lowered)
        self.assertNotIn("<button", lowered)
        self.assertNotIn("probability of winning", lowered)

    def test_funding_panel_unknowns(self) -> None:
        html = self._state()
        self.assertIn("Funding (quoted context", html)
        self.assertIn("settled history", html)
        self.assertIn("no venue calendar stored", html)


if __name__ == "__main__":
    unittest.main()
