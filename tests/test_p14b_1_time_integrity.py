"""P1-14B.1 time integrity, data quality & prospective readiness.

Reproduces the P1-14B pilot anomalies with deterministic tests and locks
the corrected contracts:

  T1  pilot `elapsed=-1789712305900s` anomaly: mechanism + exact-constant
      reproduction (seconds-minus-milliseconds in the monitor).
  T2  stored timestamps are unambiguously millisecond epochs.
  T3  recorder with default (None) db_path rehydrates setups (production
      path used by config/probe.json, which carries no db_path).
  T4  cross-restart horizon idempotency: re-observing at a LATER tick
      never inserts a second row for the same (key, horizon).
  T5  pending horizons survive restart and complete exactly once.
  T6  late observations stay honest (observed_at_ms recorded, never
      backdated to maturity, never fabricated).
  T7  maturity boundary is exact (detected_at_ms + horizon_ms).
  T8  observe() uses only the injected as_of_ms, never the wall clock.
  T9  horizon constants are exact millisecond values.
  T10 persistence exposes distinct (candidate_key, horizon) outcome keys.

Deterministic, injected event times -- no network, no live prices, no
fabricated probabilities. Run: python run_tests.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from src.microstructure_probe.prospective import (
    HORIZONS_MS,
    OUTCOME_COMPLETE,
    ProspectiveRecorder,
)

# Event-time base shared with the P1-14B suite (real recovered detection
# instant of REVERSAL_WATCH:ETHUSDT:UP, 2026-10-08T23:42:04.007Z).
EVENT_BASE_MS = 1791502924007

# Pilot Run A forensics (logs/p14b_pilot.log): first poll timestamp and the
# anomalous elapsed rendering produced by the executed monitor version.
POLL1_WALL_S = 1791503809.713313  # 2026-10-08T23:56:49.713313Z
POLL1_ELAPSED_RENDERED = "-1789712305900"
RECONSTRUCTED_T0_MS = 1791503809710  # now_ms() captured at monitor start

# Real recovered evidence (data/microprobe.db, schema v9, read-only audit
# 2026-10-09): every stored prospective timestamp must read as ms.
RECOVERED_SETUP_DETECTED_MS = (
    1791502924007,
    1791502984559,
    1791503014842,
    1791504390106,
)
RECOVERED_OUTCOME_OBSERVED_MS = (1791502984559,)


def _cand(key, symbol="ETHUSDT", family="REVERSAL_WATCH", direction="UP",
          detect_price=2477.50):
    return {
        "candidate_key": key,
        "symbol": symbol,
        "setup_family": family,
        "direction": direction,
        "market_state": "REVERSAL",
        "rule_version": "v0.1.0",
        "capability_tier": "CORE",
        "ranking": {"score": 7.39},
        "lifecycle": "DETECTED",
        "detect_price": detect_price,
        "evidence_for": [{"source": "t", "value": 1}],
        "evidence_against": [],
        "missing_features": [],
        "data_freshness": {"price_age_ms": 0},
    }


def _seed_setup_and_outcome(db_file, key="K", detected_ms=EVENT_BASE_MS,
                            observed_ms=None, price=100.0):
    """Seed one setup (+ optionally one COMPLETE outcome) via a recorder."""
    from src.microstructure_probe.persistence import PersistenceStore
    rec = ProspectiveRecorder(db_path=db_file, enabled=True)
    rec.start()
    assert rec.register_setup(key, _cand(key, detect_price=price), detected_ms)
    if observed_ms is not None:
        rec.observe("ETHUSDT", observed_ms, price * 1.01)
    rec.stop_and_drain()
    store = PersistenceStore(db_path=db_file)
    store.init_db()
    return store


# ------------------------------------------------------------------
# T1 -- pilot elapsed anomaly: mechanism + exact-constant reproduction
# ------------------------------------------------------------------

class TestElapsedAnomalyForensics(TestCase):
    """logs/p14b_pilot.log poll lines prove a seconds-minus-ms defect."""

    def test_anomaly_mechanism_reproduced_exactly(self):
        """wall_s - t0_ms with the reconstructed monitor start instant
        renders EXACTLY the logged anomaly (same :.0f formatting)."""
        elapsed = POLL1_WALL_S - RECONSTRUCTED_T0_MS
        self.assertEqual(f"{elapsed:.0f}", POLL1_ELAPSED_RENDERED)

    def test_seconds_minus_milliseconds_signature(self):
        """s-ms mixing is the ONLY unit error with magnitude ~-1.79e12 in
        Oct-2026: correct ms-ms elapsed stays in sane second ranges."""
        wall_s = POLL1_WALL_S
        t0_ms = RECONSTRUCTED_T0_MS
        buggy = wall_s - t0_ms
        self.assertTrue(-1.80e12 < buggy < -1.78e12)
        sane = wall_s - t0_ms / 1000.0  # the corrected computation
        self.assertTrue(0.0 <= sane < 120.0)

    def test_anomaly_tick_matches_poll_cadence(self):
        """Consecutive poll lines advance +10/poll: live seconds ticking
        from a fixed wrong base (constant ms t0, live s minuend)."""
        rendered = [
            -1789712305900, -1789712305890, -1789712305880, -1789712305870,
        ]
        for a, b in zip(rendered, rendered[1:]):
            self.assertEqual(b - a, 10)


# ------------------------------------------------------------------
# T2 -- stored timestamps are unambiguously millisecond epochs
# ------------------------------------------------------------------

class TestStoredTimestampUnits(TestCase):
    """Recovered v9 rows reject s/us/ns readings; only ms is plausible."""

    def test_recovered_timestamps_are_ms_epoch(self):
        for v in RECOVERED_SETUP_DETECTED_MS + RECOVERED_OUTCOME_OBSERVED_MS:
            self.assertTrue(1_700_000_000_000 < v < 1_800_000_000_000,
                            f"{v} is not a 2026 ms epoch")
            # seconds reading would land in year ~58760; us/ns out of range
            self.assertFalse(1_700_000_000 < v < 1_800_000_000)
            self.assertFalse(v > 1e15)

    def test_outcome_observed_after_detection(self):
        det = RECOVERED_SETUP_DETECTED_MS[0]
        obs = RECOVERED_OUTCOME_OBSERVED_MS[0]
        self.assertGreater(obs, det)
        self.assertEqual(obs - det, 60552)  # 552ms after 1m maturity
        self.assertGreaterEqual(obs, det + HORIZONS_MS["1m"])


# ------------------------------------------------------------------
# T3 -- default (None) db_path rehydration (production path)
# ------------------------------------------------------------------

class TestDefaultPathRehydration(TestCase):
    """config/probe.json carries no db_path, so production recorders run
    with db_path=None. Rehydration must work on that path."""

    def test_none_db_path_rehydrates_registered_setups(self):
        from src.microstructure_probe.persistence import PersistenceStore
        tmp_path = Path(tempfile.mkdtemp())
        seed_file = tmp_path / "seed.db"
        store = _seed_setup_and_outcome(seed_file, key="DEFAULTPATH")
        store.close()

        real_cls = PersistenceStore

        class RedirectedStore(real_cls):
            def __init__(self, db_path=None):
                super().__init__(db_path=seed_file)

        with patch("src.microstructure_probe.persistence.PersistenceStore",
                   RedirectedStore):
            rec = ProspectiveRecorder(db_path=None, enabled=True)
            keys = [s["candidate_key"] for s in rec.registered_setups()]
        self.assertIn("DEFAULTPATH", keys)

    def test_none_db_path_carries_detected_price(self):
        """Rehydrated setups must carry detected_mark_price so re-observed
        horizons recompute COMPLETE (never INSUFFICIENT_HISTORY)."""
        from src.microstructure_probe.persistence import PersistenceStore
        tmp_path = Path(tempfile.mkdtemp())
        seed_file = tmp_path / "seed2.db"
        store = _seed_setup_and_outcome(seed_file, key="PRICE", price=2500.0)
        store.close()

        real_cls = PersistenceStore

        class RedirectedStore(real_cls):
            def __init__(self, db_path=None):
                super().__init__(db_path=seed_file)

        with patch("src.microstructure_probe.persistence.PersistenceStore",
                   RedirectedStore):
            rec = ProspectiveRecorder(db_path=None, enabled=True)
            regs = {s["candidate_key"]: s for s in rec.registered_setups()}
        self.assertEqual(regs["PRICE"].get("detected_mark_price"), 2500.0)


# ------------------------------------------------------------------
# T4 -- cross-restart horizon idempotency at a LATER tick
# ------------------------------------------------------------------

class TestCrossRestartIdempotency(TestCase):
    """Restart + re-observe at a later timestamp must not insert a second
    row for the same (candidate_key, horizon)."""

    def test_later_reobservation_does_not_duplicate(self):
        from src.microstructure_probe.persistence import PersistenceStore
        tmp_path = Path(tempfile.mkdtemp())
        db_file = tmp_path / "dup.db"
        store = _seed_setup_and_outcome(
            db_file, key="NODUP", detected_ms=EVENT_BASE_MS,
            observed_ms=EVENT_BASE_MS + 60_000, price=100.0)
        store.close()

        rec2 = ProspectiveRecorder(db_path=db_file, enabled=True)
        rec2.start()
        outcomes = rec2.observe("ETHUSDT", EVENT_BASE_MS + 90_000, 102.0)
        rec2.stop_and_drain()

        self.assertEqual(outcomes, [])
        store2 = PersistenceStore(db_path=db_file)
        store2.init_db()
        rows = store2.prospective_outcomes(candidate_key="NODUP")
        store2.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome_state"], OUTCOME_COMPLETE)
        self.assertEqual(rows[0]["observed_at_ms"], EVENT_BASE_MS + 60_000)


# ------------------------------------------------------------------
# T5 -- pending horizons survive restart and complete exactly once
# ------------------------------------------------------------------

class TestPendingHorizonRestart(TestCase):
    def test_restart_before_maturity_completes_once(self):
        from src.microstructure_probe.persistence import PersistenceStore
        tmp_path = Path(tempfile.mkdtemp())
        db_file = tmp_path / "pend.db"
        rec = ProspectiveRecorder(db_path=db_file, enabled=True)
        rec.start()
        self.assertTrue(rec.register_setup(
            "PEND", _cand("PEND", detect_price=500.0), EVENT_BASE_MS))
        rec.stop_and_drain()  # restart BEFORE any horizon matures

        rec2 = ProspectiveRecorder(db_path=db_file, enabled=True)
        rec2.start()
        outcomes = rec2.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 505.0)
        rec2.stop_and_drain()

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["outcome_state"], OUTCOME_COMPLETE)
        self.assertAlmostEqual(outcomes[0]["mark_return_pct"], 1.0)
        store = PersistenceStore(db_path=db_file)
        store.init_db()
        rows = store.prospective_outcomes(candidate_key="PEND")
        store.close()
        self.assertEqual(len(rows), 1)


# ------------------------------------------------------------------
# T6 -- late observations stay honest
# ------------------------------------------------------------------

class TestLateObservationHonesty(TestCase):
    def test_late_observation_not_backdated_nor_fabricated(self):
        tmp_path = Path(tempfile.mkdtemp())
        db_file = tmp_path / "late.db"
        rec = ProspectiveRecorder(db_path=db_file, enabled=True)
        rec.start()
        rec.register_setup("LATE", _cand("LATE", detect_price=1000.0),
                           EVENT_BASE_MS)
        late_ms = EVENT_BASE_MS + 3 * 3_600_000  # 3h later: 1m/5m/15m/1h matured
        outcomes = rec.observe("ETHUSDT", late_ms, 990.0)
        rec.stop_and_drain()
        # All four matured horizons emit; 4h (14.4M ms) is not yet mature.
        self.assertEqual(len(outcomes), 4)
        self.assertEqual(
            sorted(o["horizon"] for o in outcomes), ["15m", "1h", "1m", "5m"])
        for out in outcomes:
            self.assertEqual(out["outcome_state"], OUTCOME_COMPLETE)
            self.assertEqual(out["observed_at_ms"], late_ms)  # recorded, visible
            self.assertNotEqual(out["observed_at_ms"],
                                EVENT_BASE_MS + HORIZONS_MS["1m"])  # not backdated
        by_hor = {o["horizon"]: o for o in outcomes}
        self.assertAlmostEqual(by_hor["1m"]["mark_return_pct"], -1.0)


# ------------------------------------------------------------------
# T7 -- maturity boundary is exact
# ------------------------------------------------------------------

class TestMaturityBoundary(TestCase):
    def test_fires_exactly_at_detected_plus_horizon(self):
        tmp_path = Path(tempfile.mkdtemp())
        rec = ProspectiveRecorder(db_path=tmp_path / "b.db", enabled=True)
        rec.start()
        rec.register_setup("B", _cand("B", detect_price=10.0), EVENT_BASE_MS)
        self.assertEqual(
            rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000 - 1, 10.5), [])
        fired = rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 10.5)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["outcome_state"], OUTCOME_COMPLETE)
        rec.stop_and_drain()


# ------------------------------------------------------------------
# T8 -- observe() never reads the wall clock
# ------------------------------------------------------------------

class TestNoWallClockInObserve(TestCase):
    def test_observe_uses_only_injected_as_of(self):
        import src.microstructure_probe.prospective as pros_mod
        tmp_path = Path(tempfile.mkdtemp())
        rec = ProspectiveRecorder(db_path=tmp_path / "w.db", enabled=True)
        rec.start()
        rec.register_setup("W", _cand("W", detect_price=50.0), EVENT_BASE_MS)
        with patch.object(pros_mod, "time") as mock_time:
            mock_time.time.side_effect = AssertionError("wall clock read")
            mock_time.monotonic.side_effect = AssertionError("clock read")
            outcomes = rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 51.0)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["observed_at_ms"], EVENT_BASE_MS + 60_000)
        rec.stop_and_drain()


# ------------------------------------------------------------------
# T9 -- horizon constants are exact millisecond values
# ------------------------------------------------------------------

class TestHorizonConstants(TestCase):
    def test_horizons_ms_exact(self):
        self.assertEqual(HORIZONS_MS, {
            "1m": 60_000,
            "5m": 300_000,
            "15m": 900_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
        })


# ------------------------------------------------------------------
# T10 -- distinct outcome keys helper + per-key store isolation
# ------------------------------------------------------------------

class TestOutcomeKeysHelper(TestCase):
    def test_distinct_candidate_horizon_pairs(self):
        from src.microstructure_probe.persistence import PersistenceStore
        tmp_path = Path(tempfile.mkdtemp())
        db_file = tmp_path / "keys.db"
        store = _seed_setup_and_outcome(
            db_file, key="KEYS", detected_ms=EVENT_BASE_MS,
            observed_ms=EVENT_BASE_MS + 60_000, price=100.0)
        pairs = store.prospective_outcome_keys()
        store.close()
        self.assertIn(("KEYS", "1m"), pairs)


def _outcome(mrp=0.1):
    return {"mark_return_pct": mrp, "detected_price": 100.0,
            "current_price": 100.0 + mrp, "outcome_state": OUTCOME_COMPLETE,
            "reason": "t"}


class TestOutcomeStoreIsolation(TestCase):
    """Storing one setup's outcome must never delete another setup's
    rows (P1-14B.1 storage-layer data-loss fix)."""

    def test_store_preserves_other_keys_rows(self):
        from src.microstructure_probe.persistence import PersistenceStore
        tmp_path = Path(tempfile.mkdtemp())
        store = PersistenceStore(db_path=tmp_path / "iso.db")
        store.init_db()
        store.store_prospective_outcome("KEY_A", "ETHUSDT", "1m", 1000, _outcome(0.1))
        store.store_prospective_outcome("KEY_A", "ETHUSDT", "5m", 2000, _outcome(0.2))
        store.store_prospective_outcome("KEY_B", "BTCUSDT", "1m", 3000, _outcome(0.3))
        self.assertEqual(len(store.prospective_outcomes()), 3)
        self.assertEqual(len(store.prospective_outcomes(candidate_key="KEY_A")), 2)
        self.assertEqual(len(store.prospective_outcomes(candidate_key="KEY_B")), 1)
        store.close()

    def test_bounded_log_is_per_key(self):
        """The 500-row bound applies per setup; other keys are untouched."""
        from src.microstructure_probe.persistence import PersistenceStore
        tmp_path = Path(tempfile.mkdtemp())
        store = PersistenceStore(db_path=tmp_path / "bound.db")
        store.init_db()
        for i in range(505):
            store.store_prospective_outcome(
                "KEY_A", "ETHUSDT", "1m", 1000 + i, _outcome(0.01 * i))
        store.store_prospective_outcome("KEY_B", "BTCUSDT", "1m", 999999, _outcome(0.5))
        rows_a = store.prospective_outcomes(candidate_key="KEY_A", limit=1000)
        self.assertEqual(len(rows_a), 500)
        self.assertEqual(len(store.prospective_outcomes(candidate_key="KEY_B")), 1)
        self.assertEqual(len(store.prospective_outcomes(limit=1000)), 501)
        store.close()
