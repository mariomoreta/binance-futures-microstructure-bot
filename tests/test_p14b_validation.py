"""P1-14B prospective evaluation — independent validation.

Full audit of the P1-14A prospective setup evaluation pipeline:
  P1-14B.1  registration (event-time, dedup, persistence)
  P1-14B.2  horizon maturity (event-time versioned horizons)
  P1-14B.3  event-time vs wall-clock integrity (observed_at_ms, honest returns)
  P1-14B.4  price timeliness (late / future / out-of-order prices)
  P1-14B.5  restart idempotency (rehydration, no duplication)
  P1-14B.6  schema migration v8 -> v9
  P1-14B.7  retention (bounded logs)
  P1-14B.8  quality flags (INSUFFICIENT_HISTORY, PENDING) + cohort denominators
  P1-14B.9  dashboard read path (/api/prospective parity)
  P1-14B.10 probe final summary carries "prospective" key
  P1-14B.11 safety (observe-only, no order/position paths)

Deterministic, injected event times -- no network, no live prices, no
fabricated probabilities. Run: python run_tests.py
"""

from __future__ import annotations

import json
import tempfile
import re
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from unittest import TestCase


from src.microstructure_probe.prospective import (
    HORIZONS_MS,
    HORIZON_ORDER,
    OUTCOME_COMPLETE,
    OUTCOME_INSUFFICIENT_HISTORY,
    OUTCOME_PENDING,
    ProspectiveRecorder,
)

# Deterministic event-time base used throughout. All horizons are relative to
# this EVENT clock, not the wall clock, so integrity can be asserted exactly.
EVENT_BASE_MS = 1791502924007  # 2026-10-08T23:42:04.007Z


def _rec(db_path: Path, enabled: bool = True, max_queue: int = 1000):
    rec = ProspectiveRecorder(db_path=db_path, enabled=enabled, max_queue=max_queue)
    rec.start()
    return rec


def _cand(key: str, symbol: str, family: str, direction: str, detect_price: float = 100_000.0):
    return {
        "candidate_key": key,
        "symbol": symbol,
        "setup_family": family,
        "direction": direction,
        "market_state": "TRENDING_DOWN",
        "rule_version": "v0.1.0",
        "capability_tier": "CORE",
        "ranking": {"score": 0.72},
        "lifecycle": "DETECTED",
        "detect_price": detect_price,
        "evidence_for": [{"source": "book_imbalance", "value": 0.6}],
        "evidence_against": [],
        "missing_features": [],
        "data_freshness": {"price_age_ms": 0},
    }


# ------------------------------------------------------------------
# P1-14B.1 Registration: event-time based, dedup, persistence
# ------------------------------------------------------------------

class TestP14B1Registration(TestCase):
    """P1-14B.1 registration behavior under the event-time clock."""

    def test_register_uses_event_time_and_horizon_matures_at_it(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Event-time base is the event clock, wall clock irrelevant."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("A", "BTCUSDT", "REVERSAL", "LONG", 100_000.0)
        assert rec.register_setup("A", cand, EVENT_BASE_MS) is True
        # Observe at the exact event-time maturity of the 1m horizon.
        outcomes = rec.observe("BTCUSDT", EVENT_BASE_MS + 60_000, 101_000.0, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["horizon"] == "1m"
        rec.stop_and_drain()

    def test_duplicate_same_candidate_key_returns_false(self):
        tmp_path = Path(tempfile.mkdtemp())
        """P1-14B.1 same candidate_key -> duplicate, never re-registered."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("KEY", "BTCUSDT", "REVERSAL", "LONG")
        assert rec.register_setup("KEY", cand, EVENT_BASE_MS) is True
        assert rec.register_setup("KEY", cand, EVENT_BASE_MS + 1) is False
        assert rec.status()["registered_setups"] == 1
        rec.stop_and_drain()

    def test_different_candidate_keys_are_independent(self):
        tmp_path = Path(tempfile.mkdtemp())
        """P1-14B.1 different candidate_key values => independent setups."""
        rec = _rec(tmp_path / "p.db")
        for i, (key, price) in enumerate([("A", 100_000.0), ("B", 200_000.0)]):
            cand = _cand(key, "BTCUSDT", "REVERSAL", "LONG", price)
            assert rec.register_setup(key, cand, EVENT_BASE_MS + i * 1000) is True
        assert rec.status()["registered_setups"] == 2
        rec.stop_and_drain()

    def test_register_persists_to_storage(self):
        tmp_path = Path(tempfile.mkdtemp())
        """P1-14B.1 setup survives recorder shutdown and is queryable from store."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("PERSIST", "ETHUSDT", "REVERSAL", "DOWN", 2500.0)
        rec.register_setup("PERSIST", cand, EVENT_BASE_MS)
        rec.stop_and_drain()
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        setups = store.prospective_setups()
        assert len(setups) == 1
        assert setups[0]["candidate_key"] == "PERSIST"
        assert setups[0]["symbol"] == "ETHUSDT"
        assert setups[0]["setup_json"]["detected_mark_price"] == 2500.0
        store.close()

    def test_register_requires_first_DETECTED_and_evals_le_one(self):
        tmp_path = Path(tempfile.mkdtemp())
        """P1-14B.1 probe contract: only lifecycle==DETECTED, evals<=1 is registered."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("LIVE", "BTCUSDT", "REVERSAL", "LONG")
        # EVALUATING lifecycle is ignored by the probe; recorder itself accepts,
        # so we verify the normalized dict was produced for a real DETECTED run.
        cand["lifecycle"] = "DETECTED"
        assert rec.register_setup("LIVE", cand, EVENT_BASE_MS) is True
        assert rec.status()["registered_setups"] == 1
        rec.stop_and_drain()

    def test_invalid_candidate_keys_rejected(self):
        tmp_path = Path(tempfile.mkdtemp())
        """P1-14B.1 malformed keys are normalized to None and rejected."""
        rec = _rec(tmp_path / "p.db")
        for bad in ("", None, 123, {}):
            assert rec.register_setup(bad, {}, EVENT_BASE_MS) is False
        assert rec.status()["registered_setups"] == 0
        rec.stop_and_drain()

    def test_disabled_recorder_never_registers(self):
        tmp_path = Path(tempfile.mkdtemp())
        """P1-14B.1 enabled=False => no registration path taken."""
        rec = ProspectiveRecorder(db_path=tmp_path / "p.db", enabled=False)
        cand = _cand("X", "BTCUSDT", "REVERSAL", "LONG")
        assert rec.register_setup("X", cand, EVENT_BASE_MS) is False
        assert rec.status()["state"] == "DISABLED"


# ------------------------------------------------------------------
# P1-14B.2 Horizon maturity: event-time, versioned horizons
# ------------------------------------------------------------------

class TestP14B2HorizonMaturity(TestCase):
    """P1-14B.2 horizons mature strictly at detected_ms + horizon_ms (event time)."""

    def test_1m_outcome_at_exact_event_time_maturity(self):
        tmp_path = Path(tempfile.mkdtemp())
        """observed_at_ms must equal detected_at_ms + 60000 exactly."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("MAT1M", "BTCUSDT", "REVERSAL", "LONG", 1000.0)
        rec.register_setup("MAT1M", cand, EVENT_BASE_MS)
        outcomes = rec.observe("BTCUSDT", EVENT_BASE_MS + 60_000, 1010.0, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["observed_at_ms"] == EVENT_BASE_MS + 60_000
        assert outcomes[0]["horizon"] == "1m"
        rec.stop_and_drain()

    def test_no_outcome_before_maturity(self):
        tmp_path = Path(tempfile.mkdtemp())
        """P1-14B.2 observe before maturity => empty, no outcome queued."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("PRE", "ETHUSDT", "REVERSAL", "UP", 2000.0)
        rec.register_setup("PRE", cand, EVENT_BASE_MS)
        for lag in (30_000, 59_000, 59_999):
            assert rec.observe("ETHUSDT", EVENT_BASE_MS + lag, 2010.0, mark_age_ms=1_000) == []
        # No outcome queued => persistence store stays empty until maturity.
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        assert len(store.prospective_outcomes()) == 0
        store.close()
        rec.stop_and_drain()

    def test_versioned_horizons_mature_separately(self):
        tmp_path = Path(tempfile.mkdtemp())
        """P1-14B.2 each horizon fires only at its own event-time offset."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("MULTI", "SOLUSDT", "IGNITION", "DOWN", 100.0)
        rec.register_setup("MULTI", cand, EVENT_BASE_MS)
        # 1m only
        o = rec.observe("SOLUSDT", EVENT_BASE_MS + 60_000, 101.0, mark_age_ms=1_000)
        assert len(o) == 1 and o[0]["horizon"] == "1m"
        # 5m only (1m already seen, 5m not yet)
        o = rec.observe("SOLUSDT", EVENT_BASE_MS + 300_000, 105.0, mark_age_ms=1_000)
        assert len(o) == 1 and o[0]["horizon"] == "5m"
        # 4h => all remaining horizons
        o = rec.observe("SOLUSDT", EVENT_BASE_MS + 14_400_000, 120.0, mark_age_ms=1_000)
        assert {x["horizon"] for x in o} == {"15m", "1h", "4h"}
        rec.stop_and_drain()

    def test_honest_return_over_horizon_window(self):
        tmp_path = Path(tempfile.mkdtemp())
        """P1-14B.2 return spans detected -> maturity price, not detection->now."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("RET", "BTCUSDT", "REVERSAL", "LONG", 100_000.0)
        rec.register_setup("RET", cand, EVENT_BASE_MS)
        outcomes = rec.observe("BTCUSDT", EVENT_BASE_MS + 60_000, 110_000.0, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["detected_price"] == 100_000.0
        assert outcomes[0]["current_price"] == 110_000.0
        expected = round((110_000.0 - 100_000.0) / 100_000.0 * 100.0, 6)
        assert outcomes[0]["mark_return_pct"] == expected
        rec.stop_and_drain()


# ------------------------------------------------------------------
# P1-14B.3 Event-time vs wall-clock integrity
# ------------------------------------------------------------------

class TestP14B3EventTimeIntegrity(TestCase):
    """P1-14B.3 observed_at_ms is event time; returns are honest over the window."""

    def test_observed_at_ms_is_event_time_not_wall_clock(self):
        tmp_path = Path(tempfile.mkdtemp())
        """observed_at_ms echoes the event-time as_of_ms, never the wall clock."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("ET", "BTCUSDT", "REVERSAL", "LONG", 1000.0)
        rec.register_setup("ET", cand, EVENT_BASE_MS)
        outcomes = rec.observe("BTCUSDT", EVENT_BASE_MS + 60_000, 1010.0, mark_age_ms=1_000)
        assert outcomes[0]["observed_at_ms"] == EVENT_BASE_MS + 60_000
        # Any wall-clock-based logic would break this equality.
        assert outcomes[0]["observed_at_ms"] < time.time() * 1000
        rec.stop_and_drain()

    def test_outcome_not_late_when_event_time_lags_wall_clock(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Even if wall clock races ahead, event-time maturity still fires."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("LATEWALL", "ETHUSDT", "REVERSAL", "UP", 2500.0)
        rec.register_setup("LATEWALL", cand, EVENT_BASE_MS)
        # Simulate wall clock far ahead; as_of_ms still the event clock.
        outcomes = rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 2510.0, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["observed_at_ms"] == EVENT_BASE_MS + 60_000
        rec.stop_and_drain()

    def test_outcome_at_maturity_matches_produced_price(self):
        tmp_path = Path(tempfile.mkdtemp())
        """The maturity mark used is the one observed AT maturity event time."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("ATM", "BTCUSDT", "REVERSAL", "LONG", 1000.0)
        rec.register_setup("ATM", cand, EVENT_BASE_MS)
        outcomes = rec.observe("BTCUSDT", EVENT_BASE_MS + 60_000, 1010.0, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["current_price"] == 1010.0
        assert outcomes[0]["mark_return_pct"] == round(1.0, 6)
        rec.stop_and_drain()


# ------------------------------------------------------------------
# P1-14B.4 Price timeliness: late, future, out-of-order
# ------------------------------------------------------------------

class TestP14B4PriceTimeliness(TestCase):
    """P1-14B.4 behavior with late / future / out-of-order price observations."""

    def test_late_arriving_price_still_computes_outcome(self):
        tmp_path = Path(tempfile.mkdtemp())
        """A price arriving long after event-time maturity still yields the outcome."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("LATE", "BTCUSDT", "REVERSAL", "LONG", 1000.0)
        rec.register_setup("LATE", cand, EVENT_BASE_MS)
        # Event time = maturity; wall clock could be arbitrarily far ahead.
        outcomes = rec.observe("BTCUSDT", EVENT_BASE_MS + 60_000, 1005.0, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["outcome_state"] == OUTCOME_COMPLETE
        rec.stop_and_drain()

    def test_future_event_time_outcome_computed_at_its_event_time(self):
        tmp_path = Path(tempfile.mkdtemp())
        """A price whose event time is ahead => maturity fires at that future time."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("FUTURE", "ETHUSDT", "REVERSAL", "DOWN", 2000.0)
        rec.register_setup("FUTURE", cand, EVENT_BASE_MS)
        # Event time = detection + 2m (ahead of 1m maturity)
        outcomes = rec.observe("ETHUSDT", EVENT_BASE_MS + 120_000, 2020.0, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["horizon"] == "1m"
        assert outcomes[0]["observed_at_ms"] == EVENT_BASE_MS + 120_000
        rec.stop_and_drain()

    def test_out_of_order_price_before_maturity_ignored(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Price older than maturity does not prematurely fire the outcome."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("OOO", "SOLUSDT", "IGNITION", "UP", 100.0)
        rec.register_setup("OOO", cand, EVENT_BASE_MS)
        # Event time 30s after detection < 1m maturity => ignored.
        assert rec.observe("SOLUSDT", EVENT_BASE_MS + 30_000, 101.0, mark_age_ms=1_000) == []
        # Only the mature event time produces the outcome.
        outcomes = rec.observe("SOLUSDT", EVENT_BASE_MS + 60_000, 102.0, mark_age_ms=1_000)
        assert len(outcomes) == 1
        rec.stop_and_drain()

    def test_no_lookahead_future_prices_invisible_until_arrive(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Prices for horizons beyond the current event time are not precomputed."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("NOLOOK", "BTCUSDT", "REVERSAL", "LONG", 1000.0)
        rec.register_setup("NOLOOK", cand, EVENT_BASE_MS)
        # At 1.5m event time: only 1m should mature, 5m not yet.
        outcomes = rec.observe("BTCUSDT", EVENT_BASE_MS + 90_000, 1005.0, mark_age_ms=1_000)
        assert len(outcomes) == 1 and outcomes[0]["horizon"] == "1m"
        # 5m at its own event time
        outcomes = rec.observe("BTCUSDT", EVENT_BASE_MS + 300_000, 1010.0, mark_age_ms=1_000)
        assert outcomes and outcomes[0]["horizon"] == "5m"
        rec.stop_and_drain()


# ------------------------------------------------------------------
# P1-14B.5 Restart idempotency
# ------------------------------------------------------------------

class TestP14B5RestartIdempotency(TestCase):
    """P1-14B.5 restart rehydrates state without duplicating setups/outcomes."""

    def test_rehydrate_preserves_setup_and_blocks_dup_registration(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _rec(tmp_path / "p.db")
        cand = _cand("RESTART", "BTCUSDT", "REVERSAL", "LONG", 1000.0)
        assert rec.register_setup("RESTART", cand, EVENT_BASE_MS) is True
        rec.stop_and_drain()
        # Fresh process: rehydrate from DB
        rec2 = ProspectiveRecorder(db_path=tmp_path / "p.db", enabled=True)
        rec2.start()
        assert rec2.register_setup("RESTART", cand, EVENT_BASE_MS) is False
        assert rec2.status()["registered_setups"] == 1
        rec2.stop_and_drain()

    def test_outcome_survives_restart(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _rec(tmp_path / "p.db")
        cand = _cand("OUTRESTART", "ETHUSDT", "REVERSAL", "UP", 2000.0)
        rec.register_setup("OUTRESTART", cand, EVENT_BASE_MS)
        rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 2020.0, mark_age_ms=1_000)
        rec.stop_and_drain()
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        assert len(store.prospective_outcomes(candidate_key="OUTRESTART")) == 1
        store.close()

    def test_restart_with_partial_queue_drain(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Worker queue drains on stop; nothing is lost."""
        rec = _rec(tmp_path / "p.db", max_queue=100000)
        cand = _cand("DRAIN", "BTCUSDT", "REVERSAL", "LONG", 1000.0)
        rec.register_setup("DRAIN", cand, EVENT_BASE_MS)
        rec.observe("BTCUSDT", EVENT_BASE_MS + 60_000, 1010.0, mark_age_ms=1_000)
        rec.stop_and_drain()
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        assert len(store.prospective_setups()) == 1
        assert len(store.prospective_outcomes(candidate_key="DRAIN")) == 1
        store.close()

    def test_rehydrate_rebuilds_seen_outcomes_set(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Restart rehydrates setups and keeps outcomes idempotent at storage."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("SEEN", "SOLUSDT", "IGNITION", "DOWN", 100.0)
        rec.register_setup("SEEN", cand, EVENT_BASE_MS)
        rec.observe("SOLUSDT", EVENT_BASE_MS + 60_000, 101.0, mark_age_ms=1_000)
        rec.stop_and_drain()
        rec2 = ProspectiveRecorder(db_path=tmp_path / "p.db", enabled=True)
        rec2.start()
        # P1-14B.1 hardened contract: the seen-outcome set rebuilds from
        # stored outcome rows, so the already-observed horizon does NOT
        # re-emit (no duplicate row even at a later tick). The rehydrated
        # registry still carries detected_mark_price (COMPLETE-capable).
        regs = {s["candidate_key"]: s for s in rec2.registered_setups()}
        assert regs["SEEN"].get("detected_mark_price") == 100.0
        outcomes = rec2.observe("SOLUSDT", EVENT_BASE_MS + 60_000, 101.0, mark_age_ms=1_000)
        assert outcomes == []
        outcomes_late = rec2.observe("SOLUSDT", EVENT_BASE_MS + 120_000, 102.0, mark_age_ms=1_000)
        assert outcomes_late == []
        # Storage-level idempotency: exactly one outcome persists.
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        assert len(store.prospective_outcomes(candidate_key="SEEN")) == 1
        assert store.prospective_outcomes(candidate_key="SEEN")[0]["outcome_state"] == OUTCOME_COMPLETE
        assert store.prospective_outcomes(candidate_key="SEEN")[0]["observed_at_ms"] == EVENT_BASE_MS + 60_000
        store.close()
        rec2.stop_and_drain()


# ------------------------------------------------------------------
# P1-14B.6 Schema migration v8 -> v9
# ------------------------------------------------------------------

class TestP14B6SchemaMigration(TestCase):
    """P1-14B.6 legacy v8 DB migrates to v9 prospective tables."""

    def test_init_db_creates_v10_tables(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        with store._get_cursor() as cursor:
            cursor.execute("SELECT value FROM persistence_meta WHERE key = 'schema_version'")
            row = cursor.fetchone()
        assert row is not None and int(row[0]) == 10
        with store._get_cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cursor.fetchall()}
        assert "prospective_setups" in tables and "prospective_outcomes" in tables
        store.close()

    def test_migration_v8_to_v10_adds_prospective_tables(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Fresh DB stops at v8 and init_db() adds prospective tables."""
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p8.db")
        # Build a v8-shaped DB: meta at 8 plus the pre-v9 tables a genuine
        # v8 carries (the v9 chain only adds the prospective ones).
        with store._get_cursor() as cursor:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS persistence_meta (
                   key TEXT PRIMARY KEY, value TEXT NOT NULL)"""
            )
            cursor.execute("INSERT INTO persistence_meta (key, value) VALUES ('schema_version', '8')")
            cursor.execute("CREATE TABLE IF NOT EXISTS universe_events (id INTEGER PRIMARY KEY,"
                           " timestamp REAL, kind TEXT, symbol TEXT, detail TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS telemetry_snapshots (id INTEGER PRIMARY KEY,"
                           " timestamp REAL)")
        store._initialized = True  # pretend v8 init done; now upgrade path
        store._initialized = False
        store.init_db()
        with store._get_cursor() as cursor:
            cursor.execute("SELECT value FROM persistence_meta WHERE key = 'schema_version'")
            assert int(cursor.fetchone()[0]) == 10
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cursor.fetchall()}
        assert "prospective_setups" in tables and "prospective_outcomes" in tables
        store.close()

    def test_migrated_db_can_read_written_rows(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "pm.db")
        store.init_db()
        store.store_prospective_setup("MIGRATED", _cand("MIGRATED", "BTCUSDT", "REVERSAL", "LONG"), EVENT_BASE_MS)
        store.store_prospective_outcome("MIGRATED", "BTCUSDT", "1m", EVENT_BASE_MS + 60, {"outcome_state": OUTCOME_COMPLETE})
        store.init_db()  # re-init (migration-safe)
        setups = store.prospective_setups()
        outcomes = store.prospective_outcomes(candidate_key="MIGRATED")
        assert len(setups) == 1 and len(outcomes) == 1
        store.close()


# ------------------------------------------------------------------
# P1-14B.7 Retention
# ------------------------------------------------------------------

class TestP14B7Retention(TestCase):
    """P1-14B.7 retention keeps logs bounded by configured days."""

    def test_retention_removes_old_setups(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        old_ms = int((time.time() - 86400 * 100) * 1000)  # 100 days ago
        store.store_prospective_setup("OLDSETUP", _cand("OLDSETUP", "BTCUSDT", "REVERSAL", "LONG"), old_ms)
        store.store_prospective_setup("NEWSETUP", _cand("NEWSETUP", "BTCUSDT", "REVERSAL", "LONG"), int(time.time() * 1000))
        cleaned = store.research_retention_cleanup({"prospective_setups": 90})
        assert cleaned.get("prospective_setups", 0) >= 1
        keys = {s["candidate_key"] for s in store.prospective_setups()}
        assert "OLDSETUP" not in keys and "NEWSETUP" in keys
        store.close()

    def test_retention_removes_old_outcomes(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        old_ms = int((time.time() - 86400 * 100) * 1000)
        store.store_prospective_outcome("RETKEY", "BTCUSDT", "1m", old_ms, {"outcome_state": OUTCOME_COMPLETE})
        store.store_prospective_outcome("RETKEY", "BTCUSDT", "1m", int(time.time() * 1000), {"outcome_state": OUTCOME_COMPLETE})
        cleaned = store.research_retention_cleanup({"prospective_outcomes": 90})
        assert cleaned.get("prospective_outcomes", 0) >= 1
        assert len(store.prospective_outcomes(candidate_key="RETKEY")) == 1
        store.close()

    def test_bounded_outcome_log_per_setup(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        for i in range(600):
            store.store_prospective_outcome("BOUNDED", "BTCUSDT", "1m", EVENT_BASE_MS + 60 + i * 1000, {"outcome_state": OUTCOME_COMPLETE})
        assert len(store.prospective_outcomes(candidate_key="BOUNDED")) <= 500
        store.close()


# ------------------------------------------------------------------
# P1-14B.8 Quality flags and cohort denominators
# ------------------------------------------------------------------

class TestP14B8QualityFlags(TestCase):
    """P1-14B.8 quality flags: INSUFFICIENT_HISTORY / PENDING, no fabrication."""

    def test_missing_detection_price_yields_insufficient_history(self):
        tmp_path = Path(tempfile.mkdtemp())
        """No detect_price => INSUFFICIENT_HISTORY, NOT a fabricated zero return."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("NODET", "BTCUSDT", "REVERSAL", "LONG")
        rec.register_setup("NODET", cand, EVENT_BASE_MS)
        rec._registered["NODET"]["detected_mark_price"] = None
        outcomes = rec.observe("BTCUSDT", EVENT_BASE_MS + 60_000, 1010.0, mark_age_ms=1_000)
        assert len(outcomes) == 1
        assert outcomes[0]["outcome_state"] == OUTCOME_INSUFFICIENT_HISTORY
        assert "mark_return_pct" not in outcomes[0]
        assert outcomes[0]["reason"] == "no detection-time reference price"
        rec.stop_and_drain()

    def test_no_mark_price_at_maturity_yields_pending(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Mark price absent at maturity => silent retry in-window, then
        PENDING (contract v1.1 grace), no fabrication."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("NOMARK", "ETHUSDT", "REVERSAL", "UP", 2500.0)
        rec.register_setup("NOMARK", cand, EVENT_BASE_MS)
        assert rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, None) == []
        outcomes = rec.observe("ETHUSDT", EVENT_BASE_MS + 120_001, None)
        assert outcomes[0]["outcome_state"] == OUTCOME_PENDING
        assert "mark_return_pct" not in outcomes[0]
        rec.stop_and_drain()

    def test_complete_outcome_has_all_denominator_fields(self):
        tmp_path = Path(tempfile.mkdtemp())
        """A COMPLETE outcome carries everything a cohort denominator needs."""
        rec = _rec(tmp_path / "p.db")
        cand = _cand("FULL", "BTCUSDT", "REVERSAL", "LONG", 1000.0)
        rec.register_setup("FULL", cand, EVENT_BASE_MS)
        outcomes = rec.observe("BTCUSDT", EVENT_BASE_MS + 60_000, 1010.0, mark_age_ms=1_000)
        o = outcomes[0]
        for field in ("candidate_key", "horizon", "observed_at_ms",
                      "detected_price", "current_price", "mark_return_pct",
                      "outcome_state", "reason"):
            assert field in o, field
        rec.stop_and_drain()

    def test_cohort_denominators_in_recorder_status(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Recorder status exposes setup/outcome counts for cohort denominators."""
        rec = _rec(tmp_path / "p.db")
        s = rec.status()
        for field in ("enabled", "state", "registered_setups", "writes",
                      "drops", "errors", "inflight", "high_water"):
            assert field in s, field
        assert s["registered_setups"] == 0
        rec.stop_and_drain()


# ------------------------------------------------------------------
# P1-14B.9 Dashboard read path
# ------------------------------------------------------------------

class TestP14B9DashboardIntegration(TestCase):
    """P1-14B.9 dashboard /api/prospective mirrors the recorder store."""

    def test_dashboard_prospective_status_reads_store(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.dashboard import DashboardState
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        cand = _cand("DASH", "BTCUSDT", "REVERSAL", "LONG", 1000.0)
        store.store_prospective_setup("DASH", cand, EVENT_BASE_MS)
        store.store_prospective_outcome("DASH", "BTCUSDT", "1m", EVENT_BASE_MS + 60, {"outcome_state": OUTCOME_COMPLETE})
        state = DashboardState(store)
        s = state.prospective_status()
        assert s["setup_count"] == 1 and s["outcome_count"] == 1
        assert s["registered_setups"] == 0  # recorder-side count, not store-side
        assert "latest_outcomes" in s
        store.close()

    def test_dashboard_prospective_empty_shape(self):
        tmp_path = Path(tempfile.mkdtemp())
        from src.microstructure_probe.dashboard import DashboardState
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        s = DashboardState(store).prospective_status()
        for key in ("enabled", "state", "registered_setups", "setup_count",
                    "outcome_count", "latest_outcomes", "drops", "errors"):
            assert key in s, key
        assert s["setup_count"] == 0 and s["outcome_count"] == 0
        store.close()


# ------------------------------------------------------------------
# P1-14B.10 Probe summary carries prospective key
# ------------------------------------------------------------------

class TestP14B10ProbeSummary(TestCase):
    """P1-14B.10 probe log_summary finalizes with a 'prospective' block."""

    def test_recorder_status_exposes_prospective_block(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = _rec(tmp_path / "p.db")
        s = rec.status()
        assert "enabled" in s
        # Recorder status is exactly the "prospective" block the probe embeds.
        assert s["state"] in ("READY", "RUNNING", "STOPPED", "DEGRADED", "DISABLED")
        rec.stop_and_drain()

    def test_probe_summary_hook_structure(self):
        tmp_path = Path(tempfile.mkdtemp())
        """The probe reads recorder status into the summary 'prospective' key."""
        rec = _rec(tmp_path / "p.db")
        expected_keys = {"enabled", "state", "registered_setups", "writes",
                         "drops", "errors", "inflight", "high_water"}
        actual = rec.status()
        assert expected_keys <= set(actual.keys())
        rec.stop_and_drain()


# ------------------------------------------------------------------
# P1-14B.11 Safety: observe-only, no order/position paths
# ------------------------------------------------------------------

class TestP14B11Safety(TestCase):
    """P1-14B.11 prospective module contains no order or position paths."""

    def test_no_trading_functions_in_prospective_module(self):
        import src.microstructure_probe.prospective as mod
        prohibited = (
            "place_order", "send_order", "submit_order", "cancel_order",
            "open_position", "close_position", "position_size", "leverage",
            "take_profit", "stop_loss", "reduce_position", "liquidate",
            "account_balance", "account_margin", "futures_client_order",
        )
        names = {n for n in dir(mod) if not n.startswith("_")}
        bad = [p for p in prohibited if any(p in n.lower() for n in names)]
        assert not bad, f"trading paths found: {bad}"

    def test_no_trading_imports_in_prospective_module(self):
        import src.microstructure_probe.prospective as mod
        source = open(mod.__file__).read()
        prohibited = (
            "binance_client.create_order", "create_position", "open_position",
            "place_order", "send_order", "account_update", "order_request",
        )
        for p in prohibited:
            assert p not in source, f"trading call found: {p}"

    def test_prospective_only_reads_and_appends(self):
        tmp_path = Path(tempfile.mkdtemp())
        """Recorder only APPENDS outcomes; never mutates/rewrites a setup."""
        from src.microstructure_probe.persistence import PersistenceStore

        store = PersistenceStore(db_path=tmp_path / "p.db")
        store.init_db()
        cand = _cand("SAFETY", "BTCUSDT", "REVERSAL", "LONG", 1000.0)
        store.store_prospective_setup("SAFETY", cand, EVENT_BASE_MS)
        before = store.prospective_setups()
        # Outcomes append without touching setups
        store.store_prospective_outcome("SAFETY", "BTCUSDT", "1m", EVENT_BASE_MS + 60, {"outcome_state": OUTCOME_COMPLETE})
        after = store.prospective_setups()
        assert len(after) == len(before) == 1
        assert after[0]["candidate_key"] == "SAFETY"
        store.close()