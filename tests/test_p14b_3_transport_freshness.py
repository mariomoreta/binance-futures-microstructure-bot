"""P1-14B.3 transport freshness & prospective outcome validity.

Locks the P1-14B.2 episode findings with deterministic tests and the
minimal corrections:

  F1  stale-mark gate: horizons matured while the mark quote is stale
      (>120s old, known age) record PENDING with an explicit reason --
      never a stale-price COMPLETE. Unknown age stays fail-open.
  F2  freshness watchdog: a connection delivering only stale (rejected)
      traffic -- open but not fresh -- gets a forced reconnect through the
      existing retry path (cooldown-guarded, never aggressive).
  F3  accepted-traffic accounting: receipt != acceptance; staleness model
      keys on post-guard acceptance per stream.

Deterministic, injected clocks -- no network, no live prices, no
fabricated probabilities. Run: python run_tests.py
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest import TestCase

from microstructure_probe.probe import (
    MarketProbe,
    _connection_for_stream,
    _FRESHNESS_RECONNECT_AFTER_MS,
    _HOT_MARKET_FRESHNESS_AFTER_MS,
    _FORCED_RECONNECT_COOLDOWN_S,
)
from microstructure_probe.prospective import (
    OUTCOME_COMPLETE,
    OUTCOME_PENDING,
    ProspectiveRecorder,
    STALE_MARK_AGE_MS,
)

from test_detectors import test_config

EVENT_BASE_MS = 1791502924007


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


def _msg(stream, symbol, e_ms, extra=None):
    payload = {"E": e_ms, "T": e_ms, "s": symbol, "p": "100",
               "q": "1", "b": "100", "a": "100.01",
               "u": 1, "pu": 0, "m": True}
    if extra:
        payload.update(extra)
    return json.dumps({"stream": stream, "data": payload})


# ------------------------------------------------------------------
# F1 -- stale-mark gate in the recorder
# ------------------------------------------------------------------

class TestStaleMarkGate(TestCase):
    def _rec(self, db):
        rec = ProspectiveRecorder(db_path=db, enabled=True)
        rec.start()
        return rec

    def test_stale_mark_records_pending_with_reason(self):
        tmp = Path(tempfile.mkdtemp()) / "s.db"
        rec = self._rec(tmp)
        rec.register_setup("S", _cand("S"), EVENT_BASE_MS)
        out = rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 2480.0,
                          mark_age_ms=STALE_MARK_AGE_MS + 1)
        rec.stop_and_drain()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["outcome_state"], OUTCOME_PENDING)
        self.assertIn(str(STALE_MARK_AGE_MS + 1), out[0]["reason"])
        self.assertNotIn("mark_return_pct", out[0])

    def test_fresh_mark_records_complete(self):
        tmp = Path(tempfile.mkdtemp()) / "f.db"
        rec = self._rec(tmp)
        rec.register_setup("F", _cand("F"), EVENT_BASE_MS)
        out = rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 2480.0,
                          mark_age_ms=45_000)
        rec.stop_and_drain()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["outcome_state"], OUTCOME_COMPLETE)

    def test_unknown_age_stays_fail_open(self):
        tmp = Path(tempfile.mkdtemp()) / "u.db"
        rec = self._rec(tmp)
        rec.register_setup("U", _cand("U"), EVENT_BASE_MS)
        out = rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 2480.0,
                          mark_age_ms=None)
        rec.stop_and_drain()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["outcome_state"], OUTCOME_COMPLETE)

    def test_boundary_age_is_complete(self):
        tmp = Path(tempfile.mkdtemp()) / "b.db"
        rec = self._rec(tmp)
        rec.register_setup("B", _cand("B"), EVENT_BASE_MS)
        out = rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 2480.0,
                          mark_age_ms=STALE_MARK_AGE_MS)
        rec.stop_and_drain()
        self.assertEqual(out[0]["outcome_state"], OUTCOME_COMPLETE)

    def test_stale_pending_is_terminal_and_stored(self):
        from microstructure_probe.persistence import PersistenceStore
        tmp = Path(tempfile.mkdtemp()) / "t.db"
        rec = self._rec(tmp)
        rec.register_setup("T", _cand("T"), EVENT_BASE_MS)
        rec.observe("ETHUSDT", EVENT_BASE_MS + 60_000, 2480.0,
                    mark_age_ms=600_000)
        # Later fresh mark must NOT upgrade the recorded PENDING.
        again = rec.observe("ETHUSDT", EVENT_BASE_MS + 120_000, 2490.0,
                            mark_age_ms=1_000)
        rec.stop_and_drain()
        self.assertEqual(again, [])
        store = PersistenceStore(db_path=tmp)
        store.init_db()
        rows = store.prospective_outcomes(candidate_key="T")
        store.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome_state"], OUTCOME_PENDING)

    def test_threshold_value(self):
        self.assertEqual(STALE_MARK_AGE_MS, 120_000)


# ------------------------------------------------------------------
# F2/F3 -- accepted-traffic accounting + watchdog
# ------------------------------------------------------------------

class TestAcceptedTrafficAccounting(TestCase):
    def _probe(self, now_ms):
        return MarketProbe(test_config(), wall_clock_ms=lambda: float(now_ms),
                           monotonic=lambda: float(now_ms) / 1000.0)

    def test_accepted_message_updates_freshness(self):
        now = 1_800_000_000_000
        probe = self._probe(now)
        probe._handle_message(_msg("btcusdt@bookTicker", "BTCUSDT", now - 100))
        self.assertEqual(probe._last_accepted_ms.get("btcusdt@bookTicker"), float(now))

    def test_rejected_message_does_not_update_freshness(self):
        now = 1_800_000_000_000
        probe = self._probe(now)
        probe._handle_message(_msg("btcusdt@bookTicker", "BTCUSDT", now - 100))
        probe._handle_message(_msg("btcusdt@bookTicker", "BTCUSDT", now - 600_000))
        self.assertEqual(probe._last_accepted_ms.get("btcusdt@bookTicker"), float(now))
        self.assertEqual(probe.stats.rejected_timestamp, 1)

    def test_burst_of_rejects_leaves_freshness_frozen(self):
        now = 1_800_000_000_000
        probe = self._probe(now)
        probe._handle_message(_msg("btcusdt@bookTicker", "BTCUSDT", now - 100))
        for i in range(50):
            probe._handle_message(
                _msg("btcusdt@bookTicker", "BTCUSDT", now - 60_000 - i))
        self.assertEqual(probe.stats.rejected_timestamp, 50)
        self.assertEqual(probe._last_accepted_ms.get("btcusdt@bookTicker"), float(now))


class TestConnectionMapping(TestCase):
    CORE = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

    def test_canonical_mapping(self):
        self.assertEqual(_connection_for_stream("btcusdt@bookTicker", self.CORE, set()), "public")
        self.assertEqual(_connection_for_stream("btcusdt@depth20@100ms", self.CORE, set()), "public")
        self.assertEqual(_connection_for_stream("btcusdt@aggTrade", self.CORE, set()), "market")
        self.assertEqual(_connection_for_stream("!markPrice@arr@1s", self.CORE, set()), "market")
        self.assertEqual(_connection_for_stream("!forceOrder@arr", self.CORE, set()), "market")

    def test_hot_mapping(self):
        hot = {"JCTUSDT"}
        self.assertEqual(_connection_for_stream("jctusdt@bookTicker", self.CORE, hot), "hot-public")
        self.assertEqual(_connection_for_stream("jctusdt@depth20@100ms", self.CORE, hot), "hot-public")
        self.assertEqual(_connection_for_stream("jctusdt@aggTrade", self.CORE, hot), "hot-market")

    def test_unknown_symbol_skipped(self):
        self.assertIsNone(_connection_for_stream("xxusdt@bookTicker", self.CORE, set()))
        self.assertIsNone(_connection_for_stream("garbage", self.CORE, set()))


class TestFreshnessWatchdog(TestCase):
    def _probe(self, now_ms):
        probe = MarketProbe(test_config(), wall_clock_ms=lambda: float(now_ms),
                            monotonic=lambda: float(now_ms) / 1000.0)
        probe.stats.connection_started["public"] = float(now_ms) / 1000.0 - 600.0
        probe.stats.connection_started["market"] = float(now_ms) / 1000.0 - 600.0
        return probe

    def test_open_but_stale_connection_requests_reconnect(self):
        # Episode signature: receipts continue (silence fresh) but nothing
        # passes the guard for >90 s on any public stream.
        now = 1_800_000_000_000
        probe = self._probe(now)
        probe._last_accepted_ms["btcusdt@bookTicker"] = float(now - 200_000)
        probe.stats.last_seen_monotonic["btcusdt@bookTicker"] = float(now) / 1000.0 - 1.0
        fired = probe._check_connection_freshness(now)
        self.assertIn("public", fired)
        self.assertIn("public", probe._reconnect_requested)

    def test_fresh_connection_does_not_fire(self):
        now = 1_800_000_000_000
        probe = self._probe(now)
        probe._last_accepted_ms["btcusdt@bookTicker"] = float(now - 5_000)
        probe._last_accepted_ms["!markPrice@arr@1s"] = float(now - 2_000)
        fired = probe._check_connection_freshness(now)
        self.assertEqual(fired, [])

    def test_connection_age_grace(self):
        now = 1_800_000_000_000
        probe = self._probe(now)
        probe.stats.connection_started["public"] = float(now) / 1000.0 - 10.0
        fired = probe._check_connection_freshness(now)
        self.assertNotIn("public", fired)

    def test_cooldown_suppresses_refire(self):
        now = 1_800_000_000_000
        wall = [now]
        mono = [float(now) / 1000.0]
        probe = MarketProbe(test_config(),
                            wall_clock_ms=lambda: float(wall[0]),
                            monotonic=lambda: float(mono[0]))
        probe.stats.connection_started["public"] = mono[0] - 600.0
        probe.stats.connection_started["market"] = mono[0] - 600.0
        probe._last_accepted_ms["btcusdt@bookTicker"] = float(now - 200_000)
        first = probe._check_connection_freshness(wall[0])
        self.assertIn("public", first)
        probe._reconnect_requested.discard("public")
        wall[0] = now + 30_000
        mono[0] = mono[0] + 30.0
        second = probe._check_connection_freshness(wall[0])
        self.assertNotIn("public", second)
        wall[0] = now + (_FORCED_RECONNECT_COOLDOWN_S + 1.0) * 1000.0
        mono[0] = mono[0] + (_FORCED_RECONNECT_COOLDOWN_S + 1.0)
        third = probe._check_connection_freshness(wall[0])
        self.assertIn("public", third)

    def test_hot_market_uses_longer_threshold(self):
        now = 1_800_000_000_000
        probe = self._probe(now)
        probe._hot_tasks["hot-market"] = object()
        probe._hot_active = ("JCTUSDT",)
        probe.stats.connection_started["hot-market"] = float(now) / 1000.0 - 600.0
        probe._last_accepted_ms["jctusdt@aggTrade"] = float(now - 200_000)
        self.assertNotIn("hot-market", probe._check_connection_freshness(now))
        probe._last_accepted_ms["jctusdt@aggTrade"] = float(
            now - _HOT_MARKET_FRESHNESS_AFTER_MS - 1_000)
        self.assertIn("hot-market", probe._check_connection_freshness(now))

    def test_consume_request_is_one_shot(self):
        probe = MarketProbe(test_config())
        self.assertFalse(probe._consume_reconnect_request("market"))
        probe._reconnect_requested.add("market")
        self.assertTrue(probe._consume_reconnect_request("market"))
        self.assertFalse(probe._consume_reconnect_request("market"))

    def test_threshold_values_documented(self):
        self.assertEqual(_FRESHNESS_RECONNECT_AFTER_MS, 90_000)
        self.assertEqual(_HOT_MARKET_FRESHNESS_AFTER_MS, 300_000)
        self.assertEqual(_FORCED_RECONNECT_COOLDOWN_S, 120.0)


# ------------------------------------------------------------------
# Audit policy locks (labels only -- NOT motor states)
# ------------------------------------------------------------------

class TestOutcomeFreshnessLabels(TestCase):
    """The VALID_FRESH / VALID_BUT_DELAYED / INSUFFICIENT_FRESHNESS_EVIDENCE /
    STALE_OR_INVALID buckets are audit labels. This test locks the policy."""

    @staticmethod
    def label(*, state, prompt, pristine_window):
        if state != "COMPLETE":
            return "NON_COMPLETE:" + state
        if not pristine_window:
            return "INSUFFICIENT_FRESHNESS_EVIDENCE"
        return "VALID_FRESH" if prompt else "VALID_BUT_DELAYED"

    def test_policy(self):
        L = self.label
        self.assertEqual(L(state="COMPLETE", prompt=True, pristine_window=True), "VALID_FRESH")
        self.assertEqual(L(state="COMPLETE", prompt=False, pristine_window=True), "VALID_BUT_DELAYED")
        self.assertEqual(L(state="COMPLETE", prompt=True, pristine_window=False),
                         "INSUFFICIENT_FRESHNESS_EVIDENCE")
        self.assertEqual(L(state="PENDING", prompt=True, pristine_window=True), "NON_COMPLETE:PENDING")
