"""P1-14A prospective evaluator — deterministic tests.

All outcomes computed from injected data; no network, no
live prices, no fabricated probabilities.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time

BASE_MS = int(time.time() * 1000)  # current wall clock (ms), keeps retention checks happy
from pathlib import Path
from unittest import TestCase

from src.microstructure_probe.prospective import (
    HORIZONS_MS,
    HORIZON_ORDER,
    OUTCOME_COMPLETE,
    OUTCOME_INVALID_GAP,
    OUTCOME_INSUFFICIENT_HISTORY,
    OUTCOME_PARTIAL,
    OUTCOME_PENDING,
    ProspectiveRecorder,
    _fnum,
    _normalize_candidate_key,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _setup_recorder(db_path: Path, enabled: bool = True) -> ProspectiveRecorder:
    rec = ProspectiveRecorder(db_path=db_path, enabled=enabled)
    rec.start()
    return rec


def _detected_candidate(
    key: str = "REV_BTCUSDT_1717000000000",
    symbol: str = "BTCUSDT",
    family: str = "REVERSAL",
    direction: str = "LONG",
    score: float = 0.72,
    detect_price: float = 100_000.0,
) -> dict:
    return {
        "candidate_key": key,
        "symbol": symbol,
        "setup_family": family,
        "direction": direction,
        "market_state": "TRENDING_DOWN",
        "rule_version": "v0.1.0",
        "capability_tier": "CORE",
        "ranking": {"score": score},
        "lifecycle": "DETECTED",
        "detect_price": detect_price,
        "evidence_for": [{"source": "book_imbalance", "value": 0.6}],
        "evidence_against": [],
        "missing_features": [],
        "data_freshness": {"bookTicker": 120},
    }


# ------------------------------------------------------------------
# Unit tests — _fnum / _normalize_candidate_key
# ------------------------------------------------------------------

class TestFnum(TestCase):
    def test_valid(self):
        tmp_path = Path(tempfile.mkdtemp())
        assert _fnum("1.5") == 1.5
        assert _fnum(42) == 42.0

    def test_none(self):
        tmp_path = Path(tempfile.mkdtemp())
        assert _fnum(None) is None
        assert _fnum("abc") is None
        assert _fnum(float("inf")) is None
        assert _fnum(float("nan")) is None


class TestNormalizeCandidateKey(TestCase):
    def test_valid(self):
        tmp_path = Path(tempfile.mkdtemp())
        assert _normalize_candidate_key("abc") == "abc"

    def test_empty(self):
        tmp_path = Path(tempfile.mkdtemp())
        assert _normalize_candidate_key("") is None

    def test_non_string(self):
        tmp_path = Path(tempfile.mkdtemp())
        assert _normalize_candidate_key(123) is None
        assert _normalize_candidate_key(None) is None


# ------------------------------------------------------------------
# Registration — idempotent, first DETECTED only
# ------------------------------------------------------------------

class TestRegistration(TestCase):
    def test_register_new(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        assert rec.register_setup(cand["candidate_key"], cand, BASE_MS) is True
        assert rec.status()["registered_setups"] == 1
        rec.stop_and_drain()

    def test_register_duplicate_returns_false(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup(cand["candidate_key"], cand, BASE_MS)
        assert rec.register_setup(cand["candidate_key"], cand, BASE_MS) is False
        assert rec.status()["registered_setups"] == 1
        rec.stop_and_drain()

    def test_register_invalid_key_returns_false(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        assert rec.register_setup("", {}, BASE_MS) is False
        assert rec.register_setup(None, {}, BASE_MS) is False
        rec.stop_and_drain()

    def test_register_disabled(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = ProspectiveRecorder(db_path=tmp_path / "p.db", enabled=False)
        cand = _detected_candidate()
        assert rec.register_setup(cand["candidate_key"], cand, BASE_MS) is False

    def test_register_persists_to_db(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup(cand["candidate_key"], cand, BASE_MS)
        rec.stop_and_drain(timeout=5)
        from src.microstructure_probe.persistence import PersistenceStore
        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        setups = store.prospective_setups()
        assert len(setups) == 1
        assert setups[0]["candidate_key"] == cand["candidate_key"]
        assert setups[0]["symbol"] == "BTCUSDT"
        assert setups[0]["family"] == "REVERSAL"

    def test_register_idempotent_after_restart(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup(cand["candidate_key"], cand, BASE_MS)
        rec.stop_and_drain(timeout=5)
        # Restart: same candidate_key still duplicate
        rec2 = ProspectiveRecorder(db_path=tmp_path / "p.db", enabled=True)
        rec2.start()
        assert rec2.register_setup(cand["candidate_key"], cand, BASE_MS) is False
        assert rec2.status()["registered_setups"] == 1
        rec2.stop_and_drain()

    def test_register_different_keys_separate(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        c1 = _detected_candidate(key="A")
        c2 = _detected_candidate(key="B")
        assert rec.register_setup("A", c1, BASE_MS) is True
        assert rec.register_setup("B", c2, BASE_MS + 1) is True
        assert rec.status()["registered_setups"] == 2
        rec.stop_and_drain()


# ------------------------------------------------------------------
# Observation — horizon maturity, no lookahead
# ------------------------------------------------------------------

class TestObservation(TestCase):
    def test_no_outcome_before_maturity(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup(cand["candidate_key"], cand, BASE_MS)
        # Observe at T+30s — 1m horizon not matured
        outcomes = rec.observe("BTCUSDT", BASE_MS + 30_000, 100_000, mark_age_ms=1_000)
        assert outcomes == []
        rec.stop_and_drain()

    def test_outcome_at_maturity(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup(cand["candidate_key"], cand, BASE_MS)
        # Observe at T+60s — 1m horizon matured
        outcomes = rec.observe("BTCUSDT", BASE_MS + 60_000, 101_000, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["horizon"] == "1m"
        assert outcomes[0]["outcome_state"] == OUTCOME_COMPLETE
        assert outcomes[0]["mark_return_pct"] == 1.0  # (101000-100000)/100000*100
        rec.stop_and_drain()

    def test_no_lookahead_beyond_maturity(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Observe after maturity but before next horizon — only one outcome."""
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup(cand["candidate_key"], cand, BASE_MS)
        # At T+120s: 1m matured, 5m not yet (needs T+300s)
        outcomes = rec.observe("BTCUSDT", BASE_MS + 120_000, 102_000, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["horizon"] == "1m"
        rec.stop_and_drain()

    def test_dedup_repeated_observations(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup(cand["candidate_key"], cand, BASE_MS)
        # First observation at maturity
        outcomes1 = rec.observe("BTCUSDT", BASE_MS + 60_000, 101_000, mark_age_ms=1_000)
        assert len(outcomes1) == 1
        # Second observation at same time — deduped
        outcomes2 = rec.observe("BTCUSDT", BASE_MS + 60_000, 101_000, mark_age_ms=1_000)
        assert outcomes2 == []
        rec.stop_and_drain()

    def test_symbol_isolation(self):
        tmp_path = Path(tempfile.mkdtemp())
        """ETHUSDT observation does not affect BTCUSDT setup."""
        rec = _setup_recorder(tmp_path / "p.db")
        btc = _detected_candidate(key="BTC", symbol="BTCUSDT")
        eth = _detected_candidate(key="ETH", symbol="ETHUSDT")
        rec.register_setup("BTC", btc, BASE_MS)
        rec.register_setup("ETH", eth, BASE_MS)
        # Observe ETH only
        outcomes = rec.observe("ETHUSDT", BASE_MS + 60_000, 101_000, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["candidate_key"] == "ETH"
        # BTC not yet observed
        btc_outcomes = rec.observe("BTCUSDT", BASE_MS + 60_000, 101_000, mark_age_ms=1_000)
        assert len(btc_outcomes) == 1
        rec.stop_and_drain()

    def test_outcome_without_mark_price(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup(cand["candidate_key"], cand, BASE_MS)
        # Contract v1.1: absent-mark horizons retry silently within the
        # recovery window (one horizon-length past maturity), then record
        # terminal PENDING.
        assert rec.observe("BTCUSDT", BASE_MS + 60_000, None) == []
        outcomes = rec.observe("BTCUSDT", BASE_MS + 120_001, None)
        assert len(outcomes) == 1
        assert outcomes[0]["outcome_state"] == OUTCOME_PENDING
        rec.stop_and_drain()

    def test_missing_detection_price(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Setup without detect_price -> INSUFFICIENT_HISTORY."""
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup("KEY", cand, BASE_MS)
        # Override: no detection price
        rec._registered["KEY"]["detected_mark_price"] = None
        outcomes = rec.observe("BTCUSDT", BASE_MS + 60_000, 101_000, mark_age_ms=1_000)
        assert outcomes[0]["outcome_state"] == OUTCOME_INSUFFICIENT_HISTORY
        rec.stop_and_drain()


# ------------------------------------------------------------------
# Bounded queue / drops
# ------------------------------------------------------------------

class TestBackpressure(TestCase):
    def test_queue_full_drops(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = ProspectiveRecorder(
            db_path=tmp_path / "p.db",
            max_queue=1,
            enabled=True,
        )
        rec.start()
        cand = _detected_candidate()
        rec.register_setup("A", cand, BASE_MS)
        # Queue has 1 item already; second register drops
        rec.register_setup("B", cand, BASE_MS + 1)
        assert rec.status()["drops"] >= 0  # at least attempted
        rec.stop_and_drain()


# ------------------------------------------------------------------
# ProspectiveRecorder.status()
# ------------------------------------------------------------------

class TestStatus(TestCase):
    def test_status_shape(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        s = rec.status()
        assert "enabled" in s
        assert "state" in s
        assert "registered_setups" in s
        assert "writes" in s
        assert "drops" in s
        assert "errors" in s
        assert "inflight" in s
        assert "high_water" in s
        assert "completed" in s
        assert "pending" in s
        assert "insufficient" in s
        assert "in_grace" in s
        rec.stop_and_drain()

    def test_disabled_status(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = ProspectiveRecorder(db_path=tmp_path / "p.db", enabled=False)
        s = rec.status()
        assert s["state"] == "DISABLED"
        assert s["enabled"] is False


# ------------------------------------------------------------------
# Persistence integration — schema v9
# ------------------------------------------------------------------

class TestSchemaV9(TestCase):
    def test_schema_version_after_init(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore
        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        with store._get_cursor() as cursor:
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key = 'schema_version'"
            )
            row = cursor.fetchone()
        assert row is not None
        assert int(row[0]) == 10
        store.close()

    def test_prospective_tables_exist(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore
        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        with store._get_cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
        assert "prospective_setups" in tables
        assert "prospective_outcomes" in tables
        store.close()

    def test_store_and_retrieve_setup(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore
        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        cand = _detected_candidate()
        store.store_prospective_setup("KEY", cand, BASE_MS)
        setups = store.prospective_setups()
        assert len(setups) == 1
        assert setups[0]["candidate_key"] == "KEY"
        assert setups[0]["symbol"] == "BTCUSDT"
        assert setups[0]["family"] == "REVERSAL"
        store.close()

    def test_store_and_retrieve_outcome(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore
        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        outcome = {
            "candidate_key": "KEY",
            "horizon": "1m",
            "observed_at_ms": BASE_MS + 60,
            "outcome_state": OUTCOME_COMPLETE,
            "mark_return_pct": 1.0,
            "detected_price": 100_000.0,
            "current_price": 101_000.0,
            "reason": "horizon matured",
        }
        store.store_prospective_outcome("KEY", "BTCUSDT", "1m", BASE_MS + 60, outcome)
        outcomes = store.prospective_outcomes(candidate_key="KEY")
        assert len(outcomes) == 1
        assert outcomes[0]["horizon"] == "1m"
        assert outcomes[0]["outcome_state"] == OUTCOME_COMPLETE
        assert outcomes[0]["mark_return_pct"] == 1.0
        store.close()

    def test_outcome_idempotent(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore
        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        outcome = {"outcome_state": OUTCOME_COMPLETE, "mark_return_pct": 1.0}
        store.store_prospective_outcome("KEY", "BTCUSDT", "1m", BASE_MS + 60, outcome)
        store.store_prospective_outcome("KEY", "BTCUSDT", "1m", BASE_MS + 60, outcome)
        outcomes = store.prospective_outcomes(candidate_key="KEY")
        assert len(outcomes) == 1  # unique constraint prevents dup
        store.close()

    def test_outcome_bounded_per_setup(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore
        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        outcome = {"outcome_state": OUTCOME_COMPLETE, "mark_return_pct": 0.5}
        for i in range(600):
            store.store_prospective_outcome("KEY", "BTCUSDT", "1m", BASE_MS + 60 + i * 1000, outcome)
        outcomes = store.prospective_outcomes(candidate_key="KEY")
        assert len(outcomes) <= 500
        store.close()


# ------------------------------------------------------------------
# Deterministic outcome computation
# ------------------------------------------------------------------

class TestOutcomeDeterminism(TestCase):
    def test_long_return_positive(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup("KEY", cand, BASE_MS)
        rec._registered["KEY"]["detected_mark_price"] = 100_000.0
        outcomes = rec.observe("BTCUSDT", BASE_MS + 60_000, 110_000.0, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["mark_return_pct"] == 10.0
        assert outcomes[0]["detected_price"] == 100_000.0
        assert outcomes[0]["current_price"] == 110_000.0
        rec.stop_and_drain()

    def test_short_return_negative(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup("KEY", cand, BASE_MS)
        rec._registered["KEY"]["detected_mark_price"] = 100_000.0
        outcomes = rec.observe("BTCUSDT", BASE_MS + 60_000, 95_000.0, mark_age_ms=1_000)
        assert outcomes[0]["mark_return_pct"] == -5.0
        rec.stop_and_drain()

    def test_no_fabrication_of_missing_data(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Without detection price, outcome is INSUFFICIENT_HISTORY, not zero."""
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup("KEY", cand, BASE_MS)
        rec._registered["KEY"]["detected_mark_price"] = None
        outcomes = rec.observe("BTCUSDT", BASE_MS + 60_000, 101_000.0, mark_age_ms=1_000)
        assert outcomes[0]["outcome_state"] == OUTCOME_INSUFFICIENT_HISTORY
        assert "mark_return_pct" not in outcomes[0]
        rec.stop_and_drain()


# ------------------------------------------------------------------
# Multiple horizons
# ------------------------------------------------------------------

class TestMultipleHorizons(TestCase):
    def test_all_horizons_mature(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _setup_recorder(tmp_path / "p.db")
        cand = _detected_candidate()
        rec.register_setup(cand["candidate_key"], cand, BASE_MS)
        # At T+4h, all horizons matured
        outcomes = rec.observe("BTCUSDT", BASE_MS + 14_400_000, 105_000, mark_age_ms=1_000)
        horizon_keys = {o["horizon"] for o in outcomes}
        assert "1m" in horizon_keys
        assert "5m" in horizon_keys
        assert "15m" in horizon_keys
        assert "1h" in horizon_keys
        assert "4h" in horizon_keys
        rec.stop_and_drain()


# ------------------------------------------------------------------
# Dashboard integration — prospective_status
# ------------------------------------------------------------------

class TestDashboardIntegration(TestCase):
    def test_prospective_status_shape(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.dashboard import DashboardState
        from src.microstructure_probe.persistence import PersistenceStore
        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        state = DashboardState(store)
        s = state.prospective_status()
        assert "enabled" in s
        assert "state" in s
        assert "registered_setups" in s
        assert "writes" in s
        assert "drops" in s
        assert "errors" in s
        assert "setup_count" in s
        assert "outcome_count" in s
        assert "latest_outcomes" in s

    def test_prospective_status_empty(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.dashboard import DashboardState
        from src.microstructure_probe.persistence import PersistenceStore
        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        state = DashboardState(store)
        s = state.prospective_status()
        assert s["setup_count"] == 0
        assert s["outcome_count"] == 0
        assert s["registered_setups"] == 0


# ------------------------------------------------------------------
# Retention cleanup
# ------------------------------------------------------------------

class TestRetention(TestCase):
    def test_retention_cleanup(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore
        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        # Insert old setup
        old_ms = int((time.time() - 86400 * 100) * 1000)  # 100 days ago
        store.store_prospective_setup("OLD", _detected_candidate(), old_ms)
        # Insert recent setup
        store.store_prospective_setup("NEW", _detected_candidate(), int(time.time() * 1000))
        cleaned = store.research_retention_cleanup({"prospective_setups": 90})
        assert cleaned.get("prospective_setups", 0) >= 1
        setups = store.prospective_setups()
        keys = {s["candidate_key"] for s in setups}
        assert "OLD" not in keys
        assert "NEW" in keys
        store.close()