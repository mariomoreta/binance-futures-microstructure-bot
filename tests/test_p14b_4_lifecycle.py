"""P1-14B.4 prospective freshness & PENDING lifecycle integrity.

Outcome Contract v1.1 (see docs/PROSPECTIVE_EVALUATION_SPEC.md):
  - UNKNOWN age is never FRESH: None/malformed/non-finite/future ages record
    PENDING with explicit reasons (never a silent COMPLETE).
  - PENDING is grace-deferred, then terminal: a matured horizon with no valid
    sample retries (absent, no row) while now - first_failure <= horizon_ms
    (recovery window = one horizon-length past maturity, i.e. obs < det + 2H);
    only after the window exhausts is terminal PENDING recorded.
  - INSUFFICIENT_HISTORY (no reference) stays immediate + terminal.
  - No schema change (v9); no new outcome states; no rewrites.

Deterministic, injected event times -- no network, no live prices, no
fabricated probabilities. Run: python run_tests.py
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from unittest import TestCase

from src.microstructure_probe.prospective import (
    HORIZONS_MS,
    OUTCOME_COMPLETE,
    OUTCOME_INSUFFICIENT_HISTORY,
    OUTCOME_PENDING,
    PROSPECTIVE_CONTRACT_VERSION,
    STALE_MARK_AGE_MS,
    ProspectiveRecorder,
    _classify_mark_age,
)

EVENT_BASE_MS = 1791502924007
FRESH_AGE_MS = 1_000


def _cand(key, symbol="ETHUSDT", price=2477.50):
    return {
        "candidate_key": key,
        "symbol": symbol,
        "setup_family": "REVERSAL_WATCH",
        "direction": "UP",
        "market_state": "REVERSAL",
        "rule_version": "v0.1.0",
        "capability_tier": "CORE",
        "ranking": {"score": 7.39},
        "lifecycle": "DETECTED",
        "detect_price": price,
        "evidence_for": [],
        "evidence_against": [],
        "missing_features": [],
        "data_freshness": {"price_age_ms": 0},
    }


def _rec(db_path, enabled=True):
    rec = ProspectiveRecorder(db_path=db_path, enabled=enabled)
    rec.start()
    return rec


def _store(db_path):
    from src.microstructure_probe.persistence import PersistenceStore
    store = PersistenceStore(db_path=db_path)
    store.init_db()
    return store


# ------------------------------------------------------------------
# Contract version + age classifier
# ------------------------------------------------------------------

class TestContractVersion(TestCase):
    def test_version(self):
        self.assertEqual(PROSPECTIVE_CONTRACT_VERSION, "1.1")
        self.assertEqual(STALE_MARK_AGE_MS, 120_000)

    def test_classify_ok(self):
        self.assertEqual(_classify_mark_age(0), ("ok", 0.0))
        self.assertEqual(_classify_mark_age(45_000), ("ok", 45000.0))
        self.assertEqual(_classify_mark_age(120_000), ("ok", 120000.0))

    def test_classify_tiny_negative_clamped(self):
        verdict, value = _classify_mark_age(-0.5)
        self.assertEqual(verdict, "ok")
        self.assertEqual(value, 0.0)

    def test_classify_unknown(self):
        self.assertEqual(_classify_mark_age(None)[0], "unknown")
        self.assertEqual(_classify_mark_age("abc")[0], "unknown")
        self.assertEqual(_classify_mark_age(object())[0], "unknown")

    def test_classify_nonfinite(self):
        self.assertEqual(_classify_mark_age(float("inf"))[0], "nonfinite")
        self.assertEqual(_classify_mark_age(float("nan"))[0], "nonfinite")

    def test_classify_future(self):
        self.assertEqual(_classify_mark_age(-5_000)[0], "future")


# ------------------------------------------------------------------
# Boundary + stale/unknown lifecycle under grace
# ------------------------------------------------------------------

class TestStaleGraceLifecycle(TestCase):
    def test_exact_threshold_completes(self):
        tmp = Path(tempfile.mkdtemp()) / "e.db"
        rec = _rec(tmp)
        rec.register_setup("E", _cand("E"), EVENT_BASE_MS)
        out = rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 2480.0,
                          mark_age_ms=120_000)
        rec.stop_and_drain()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["outcome_state"], OUTCOME_COMPLETE)

    def test_first_stale_tick_absent_then_pending(self):
        tmp = Path(tempfile.mkdtemp()) / "g.db"
        rec = _rec(tmp)
        rec.register_setup("G", _cand("G"), EVENT_BASE_MS)
        t0 = EVENT_BASE_MS + 60_000
        # First matured-stale tick: absent (grace, no row).
        self.assertEqual(rec.observe("ETHUSDT", t0, 2480.0,
                                     mark_age_ms=600_000), [])
        store = _store(tmp)
        self.assertEqual(len(store.prospective_outcomes(candidate_key="G")), 0)
        store.close()
        # Still within grace (1m): absent.
        self.assertEqual(rec.observe("ETHUSDT", t0 + 30_000, 2480.0,
                                     mark_age_ms=600_000), [])
        # Past grace (now - first > 60_000): terminal PENDING with reason.
        out = rec.observe("ETHUSDT", t0 + 60_001, 2480.0, mark_age_ms=600_000)
        rec.stop_and_drain()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["outcome_state"], OUTCOME_PENDING)
        self.assertIn("600000", out[0]["reason"])
        self.assertNotIn("mark_return_pct", out[0])

    def test_unknown_age_grace_then_pending(self):
        tmp = Path(tempfile.mkdtemp()) / "u.db"
        rec = _rec(tmp)
        rec.register_setup("U", _cand("U"), EVENT_BASE_MS)
        t0 = EVENT_BASE_MS + 60_000
        self.assertEqual(rec.observe("ETHUSDT", t0, 2480.0, mark_age_ms=None), [])
        out = rec.observe("ETHUSDT", t0 + 60_001, 2480.0, mark_age_ms=None)
        rec.stop_and_drain()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["outcome_state"], OUTCOME_PENDING)
        self.assertIn("unknown mark age", out[0]["reason"])

    def test_absent_mark_grace_then_pending(self):
        tmp = Path(tempfile.mkdtemp()) / "a.db"
        rec = _rec(tmp)
        rec.register_setup("A", _cand("A"), EVENT_BASE_MS)
        t0 = EVENT_BASE_MS + 60_000
        self.assertEqual(rec.observe("ETHUSDT", t0, None), [])
        out = rec.observe("ETHUSDT", t0 + 60_001, None)
        rec.stop_and_drain()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["outcome_state"], OUTCOME_PENDING)
        self.assertIn("no mark price", out[0]["reason"])

    def test_nonfinite_and_future_pending_reasons(self):
        for age, fragment in ((float("inf"), "non-finite"),
                              (float("nan"), "non-finite"),
                              (-5_000, "ahead of observation clock")):
            tmp = Path(tempfile.mkdtemp()) / ("n%s.db" % str(age).replace(".", "_").replace("-", "m"))
            rec = _rec(tmp)
            rec.register_setup("N", _cand("N"), EVENT_BASE_MS)
            t0 = EVENT_BASE_MS + 60_000
            rec.observe("ETHUSDT", t0, 2480.0, mark_age_ms=age)
            out = rec.observe("ETHUSDT", t0 + 60_001, 2480.0, mark_age_ms=age)
            rec.stop_and_drain()
            self.assertEqual(len(out), 1, age)
            self.assertEqual(out[0]["outcome_state"], OUTCOME_PENDING, age)
            self.assertIn(fragment, out[0]["reason"], age)


# ------------------------------------------------------------------
# Recovery within grace + terminality after
# ------------------------------------------------------------------

class TestGraceRecovery(TestCase):
    def test_fresh_quote_within_grace_completes(self):
        """UNKNOWN_TO_FRESH: unknown ages during grace, then a fresh quote
        arrives in-window -> COMPLETE (single terminal row)."""
        tmp = Path(tempfile.mkdtemp()) / "r.db"
        rec = _rec(tmp)
        rec.register_setup("R", _cand("R", price=100.0), EVENT_BASE_MS)
        t0 = EVENT_BASE_MS + 60_000
        self.assertEqual(rec.observe("ETHUSDT", t0, 101.0, mark_age_ms=None), [])
        out = rec.observe("ETHUSDT", t0 + 30_000, 102.0, mark_age_ms=5_000)
        rec.stop_and_drain()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["outcome_state"], OUTCOME_COMPLETE)
        self.assertAlmostEqual(out[0]["mark_return_pct"], 2.0)
        self.assertEqual(out[0]["observed_at_ms"], t0 + 30_000)
        store = _store(tmp)
        rows = store.prospective_outcomes(candidate_key="R")
        store.close()
        self.assertEqual(len(rows), 1)

    def test_pending_then_fresh_stays_pending(self):
        """PENDING_TO_COMPLETE guard: recorded PENDING never upgrades."""
        tmp = Path(tempfile.mkdtemp()) / "p.db"
        rec = _rec(tmp)
        rec.register_setup("P", _cand("P", price=100.0), EVENT_BASE_MS)
        t0 = EVENT_BASE_MS + 60_000
        rec.observe("ETHUSDT", t0, 101.0, mark_age_ms=600_000)
        first = rec.observe("ETHUSDT", t0 + 60_001, 101.0, mark_age_ms=600_000)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["outcome_state"], OUTCOME_PENDING)
        later = rec.observe("ETHUSDT", t0 + 120_000, 103.0, mark_age_ms=2_000)
        rec.stop_and_drain()
        self.assertEqual(later, [])
        store = _store(tmp)
        rows = store.prospective_outcomes(candidate_key="P")
        store.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome_state"], OUTCOME_PENDING)

    def test_multiple_evaluations_single_terminal_row(self):
        tmp = Path(tempfile.mkdtemp()) / "m.db"
        rec = _rec(tmp)
        rec.register_setup("M", _cand("M", price=50.0), EVENT_BASE_MS)
        t0 = EVENT_BASE_MS + 60_000
        for i in range(10):
            rec.observe("ETHUSDT", t0 + i * 10_000, 50.0 + i, mark_age_ms=600_000)
        rec.stop_and_drain()
        store = _store(tmp)
        rows = store.prospective_outcomes(candidate_key="M")
        store.close()
        # Ticks at +0..+60s: absent; tick +70s... only ticks past grace emit,
        # and the first emission terminally blocks the rest.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome_state"], OUTCOME_PENDING)


# ------------------------------------------------------------------
# Restart interplay
# ------------------------------------------------------------------

class TestPendingRestart(TestCase):
    def test_restart_with_pending_persisted_no_reemit(self):
        tmp = Path(tempfile.mkdtemp()) / "rp.db"
        rec = _rec(tmp)
        rec.register_setup("RP", _cand("RP", price=100.0), EVENT_BASE_MS)
        t0 = EVENT_BASE_MS + 60_000
        rec.observe("ETHUSDT", t0, 101.0, mark_age_ms=600_000)
        rec.observe("ETHUSDT", t0 + 60_001, 101.0, mark_age_ms=600_000)
        rec.stop_and_drain()
        rec2 = ProspectiveRecorder(db_path=tmp, enabled=True)
        rec2.start()
        # The stored 1m PENDING never re-emits; the newly matured 5m may
        # complete normally (different horizon, never seen).
        out2 = rec2.observe("ETHUSDT", t0 + 300_000, 105.0, mark_age_ms=1_000)
        rec2.stop_and_drain()
        self.assertEqual([o["horizon"] for o in out2], ["5m"])
        self.assertEqual(out2[0]["outcome_state"], OUTCOME_COMPLETE)
        store = _store(tmp)
        rows = store.prospective_outcomes(candidate_key="RP")
        store.close()
        by_hor = {r["horizon"]: r for r in rows}
        self.assertEqual(by_hor["1m"]["outcome_state"], OUTCOME_PENDING)
        self.assertEqual(by_hor["1m"]["observed_at_ms"], t0 + 60_001)
        self.assertEqual(by_hor["5m"]["outcome_state"], OUTCOME_COMPLETE)

    def test_restart_during_grace_restarts_grace(self):
        tmp = Path(tempfile.mkdtemp()) / "rg.db"
        rec = _rec(tmp)
        rec.register_setup("RG", _cand("RG", price=100.0), EVENT_BASE_MS)
        t0 = EVENT_BASE_MS + 60_000
        # One stale tick pre-restart: absent, grace tracked only in memory.
        self.assertEqual(rec.observe("ETHUSDT", t0, 101.0, mark_age_ms=600_000), [])
        rec.stop_and_drain()
        rec2 = ProspectiveRecorder(db_path=tmp, enabled=True)
        rec2.start()
        # Fresh quote immediately post-restart still completes (new grace).
        out = rec2.observe("ETHUSDT", t0 + 30_000, 102.0, mark_age_ms=2_000)
        rec2.stop_and_drain()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["outcome_state"], OUTCOME_COMPLETE)

    def test_rehydrate_complete_no_reemit(self):
        tmp = Path(tempfile.mkdtemp()) / "rc.db"
        rec = _rec(tmp)
        rec.register_setup("RC", _cand("RC", price=100.0), EVENT_BASE_MS)
        rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 101.0, mark_age_ms=FRESH_AGE_MS)
        rec.stop_and_drain()
        rec2 = ProspectiveRecorder(db_path=tmp, enabled=True)
        rec2.start()
        out2 = rec2.observe("ETHUSDT", EVENT_BASE_MS + 300_000, 110.0,
                            mark_age_ms=FRESH_AGE_MS)
        rec2.stop_and_drain()
        self.assertEqual([o["horizon"] for o in out2], ["5m"])


# ------------------------------------------------------------------
# Telemetry
# ------------------------------------------------------------------

class TestLifecycleTelemetry(TestCase):
    def test_verdict_counters(self):
        tmp = Path(tempfile.mkdtemp()) / "v.db"
        rec = _rec(tmp)
        rec.register_setup("V1", _cand("V1", symbol="ETHUSDT", price=100.0),
                           EVENT_BASE_MS)
        rec.register_setup("V2", _cand("V2", symbol="BTCUSDT", price=100.0),
                           EVENT_BASE_MS)
        t0 = EVENT_BASE_MS + 60_000
        rec.observe("ETHUSDT", t0, 101.0, mark_age_ms=FRESH_AGE_MS)  # COMPLETE
        rec.observe("BTCUSDT", t0, 101.0, mark_age_ms=600_000)  # grace...
        st_mid = rec.status()
        self.assertEqual(st_mid["in_grace"], 1)
        rec.observe("BTCUSDT", t0 + 60_001, 101.0, mark_age_ms=600_000)  # PENDING
        st = rec.status()
        rec.stop_and_drain()
        self.assertEqual(st["completed"], 1)
        self.assertEqual(st["pending"], 1)
        self.assertEqual(st["insufficient"], 0)
        self.assertEqual(st["in_grace"], 0)

    def test_insufficient_counter(self):
        tmp = Path(tempfile.mkdtemp()) / "i.db"
        rec = _rec(tmp)
        bad = _cand("I")
        del bad["detect_price"]
        rec.register_setup("I", bad, EVENT_BASE_MS)
        out = rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 101.0,
                          mark_age_ms=FRESH_AGE_MS)
        st = rec.status()
        rec.stop_and_drain()
        self.assertEqual(out[0]["outcome_state"], OUTCOME_INSUFFICIENT_HISTORY)
        self.assertEqual(st["insufficient"], 1)
