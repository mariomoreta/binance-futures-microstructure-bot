"""P1-14B.5 transport health states & watchdog re-verification.

Diagnostic vocabulary (disjoint from P1-12A market states and P1-13A
lifecycles): CONNECTED/DOWN socket state plus FLOWING_FRESH/FLOWING_STALE/
SILENT/RECONNECTING/UNAVAILABLE health. An open socket never implies health.

Deterministic, injected clocks -- no live Binance dependency.
Run: python run_tests.py
"""

from __future__ import annotations

from unittest import TestCase

from microstructure_probe.probe import (
    _FRESHNESS_RECONNECT_AFTER_MS,
    _HOT_MARKET_FRESHNESS_AFTER_MS,
    classify_connection_health,
)


class TestHealthStates(TestCase):
    def test_flowing_fresh(self):
        now = 1_800_000_000_000.0
        out = classify_connection_health(
            socket_up=True, ever_attempted=True, now_wall_ms=now,
            last_receipt_wall_ms=now - 500.0,
            last_accepted_wall_ms=now - 800.0)
        self.assertEqual(out["socket"], "CONNECTED")
        self.assertEqual(out["health"], "FLOWING_FRESH")
        self.assertAlmostEqual(out["acceptedAgeMs"], 800.0)

    def test_open_but_stale(self):
        # The P1-14B.2 signature: receipts flowing, nothing accepted.
        now = 1_800_000_000_000.0
        out = classify_connection_health(
            socket_up=True, ever_attempted=True, now_wall_ms=now,
            last_receipt_wall_ms=now - 1_000.0,
            last_accepted_wall_ms=now - 200_000.0)
        self.assertEqual(out["socket"], "CONNECTED")
        self.assertEqual(out["health"], "FLOWING_STALE")

    def test_silent(self):
        now = 1_800_000_000_000.0
        out = classify_connection_health(
            socket_up=True, ever_attempted=True, now_wall_ms=now,
            last_receipt_wall_ms=now - 120_000.0,
            last_accepted_wall_ms=now - 120_000.0)
        self.assertEqual(out["health"], "SILENT")

    def test_reconnecting(self):
        out = classify_connection_health(
            socket_up=False, ever_attempted=True,
            now_wall_ms=1_800_000_000_000.0)
        self.assertEqual(out["socket"], "DOWN")
        self.assertEqual(out["health"], "RECONNECTING")

    def test_unavailable(self):
        out = classify_connection_health(
            socket_up=False, ever_attempted=False,
            now_wall_ms=1_800_000_000_000.0)
        self.assertEqual(out["health"], "UNAVAILABLE")

    def test_missing_data_never_zero_filled(self):
        out = classify_connection_health(
            socket_up=True, ever_attempted=True,
            now_wall_ms=1_800_000_000_000.0,
            last_receipt_wall_ms=None, last_accepted_wall_ms=None)
        self.assertIsNone(out["lastReceiptMs"])
        self.assertIsNone(out["lastAcceptedMs"])
        self.assertIsNone(out["receiptAgeMs"])
        self.assertIsNone(out["acceptedAgeMs"])
        self.assertEqual(out["health"], "SILENT")

    def test_low_frequency_feed_budget(self):
        # hot-market style: sparse but alive traffic stays FRESH under the
        # long budget, stale under it -- cadence never assumed.
        now = 1_800_000_000_000.0
        fresh = classify_connection_health(
            socket_up=True, ever_attempted=True, now_wall_ms=now,
            last_receipt_wall_ms=now - 1_000.0,
            last_accepted_wall_ms=now - 200_000.0,
            budget_ms=_HOT_MARKET_FRESHNESS_AFTER_MS)
        self.assertEqual(fresh["health"], "FLOWING_FRESH")
        stale = classify_connection_health(
            socket_up=True, ever_attempted=True, now_wall_ms=now,
            last_receipt_wall_ms=now - 1_000.0,
            last_accepted_wall_ms=now - 200_000.0,
            budget_ms=_FRESHNESS_RECONNECT_AFTER_MS)
        self.assertEqual(stale["health"], "FLOWING_STALE")

    def test_malformed_inputs_do_not_crash(self):
        out = classify_connection_health(
            socket_up=True, ever_attempted=True, now_wall_ms="abc",
            last_receipt_wall_ms="xyz", last_accepted_wall_ms=object())
        self.assertIn(out["health"], ("FLOWING_FRESH", "FLOWING_STALE",
                                      "SILENT", "RECONNECTING", "UNAVAILABLE"))
