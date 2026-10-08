"""P1-12B universe manager tests (deterministic, offline, no network)."""

from __future__ import annotations

import unittest

from microstructure_probe.probe import build_hot_stream_urls
from microstructure_probe.probe import expected_stream_names
from microstructure_probe.universe_manager import (
    ST_DEGRADED,
    ST_DEMOTION_PENDING,
    ST_DISCOVERY_ONLY,
    ST_LIVE,
    ST_PROMOTION_PENDING,
    ST_UNKNOWN,
    ST_UNSUBSCRIBING,
    ST_WARMING,
    UniverseManager,
    movement_key,
    streams_for_symbols,
)


def cand(change=None, volume=None, eligible=True, close_ms=1_000_000):
    return {"eligible": eligible, "change_24h_pct": change,
            "quote_volume_24h": volume, "ticker_close_ms": close_ms}


class RankingTest(unittest.TestCase):
    def test_movement_order_and_tie_break(self) -> None:
        self.assertLess(movement_key(5.0, 10.0, "B"),
                        movement_key(3.0, 99.0, "A"))
        self.assertLess(movement_key(5.0, 20.0, "B"),
                        movement_key(5.0, 10.0, "A"))
        self.assertLess(movement_key(5.0, 10.0, "AAA"),
                        movement_key(5.0, 10.0, "ZZZ"))
        # Missing change sorts last; missing volume after measured volume.
        self.assertGreater(movement_key(None, 10.0, "A"),
                           movement_key(0.1, 10.0, "A"))
        self.assertGreater(movement_key(5.0, None, "A"),
                           movement_key(5.0, 10.0, "A"))

    def test_stream_counts(self) -> None:
        self.assertEqual(streams_for_symbols(()), 0)
        self.assertEqual(streams_for_symbols(("A", "B", "C")), 9)
        self.assertEqual(streams_for_symbols(("A", "a")), 3)  # deduped


class SelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = UniverseManager(core=("BTCUSDT",))

    def test_no_promotion_without_proposals(self) -> None:
        out = self.mgr.update({"BTCUSDT": cand(1.0, 9.0)}, [], 2_000_000,
                              scan_ms=2_000_000)
        self.assertEqual(out["promote"], [])
        self.assertEqual(self.mgr.desired_hot(), ())

    def test_promotes_top_ranked_fresh_candidate(self) -> None:
        cands = {"DOGEUSDT": cand(41.2, 356_000_000),
                 "SOLUSDT": cand(8.6, 820_000_000),
                 "BTCUSDT": cand(2.4, 1_900_000_000)}
        out = self.mgr.update(cands, ["DOGEUSDT", "SOLUSDT"], 2_000_000,
                              scan_ms=2_000_000)
        self.assertEqual(out["promote"], ["DOGEUSDT", "SOLUSDT"])
        self.assertEqual(self.mgr.desired_hot(), ("DOGEUSDT", "SOLUSDT"))

    def test_ineligible_never_promoted(self) -> None:
        cands = {"XUSDT": cand(99.0, 9.0, eligible=False)}
        out = self.mgr.update(cands, ["XUSDT"], 2_000_000,
                              scan_ms=2_000_000)
        self.assertEqual(out["promote"], [])
        self.assertEqual(self.mgr.desired_hot(), ())

    def test_stale_discovery_skipped(self) -> None:
        cands = {"DOGEUSDT": cand(41.2, 356_000_000, close_ms=1_000)}
        out = self.mgr.update(cands, ["DOGEUSDT"], 5_000_000,
                              scan_ms=5_000_000)
        self.assertEqual(out["promote"], [])
        kinds = [e["kind"] for e in out["events"]]
        self.assertIn("skipped", kinds)

    def test_missing_metrics_handled(self) -> None:
        cands = {"XUSDT": cand(None, None)}
        out = self.mgr.update(cands, ["XUSDT"], 2_000_000,
                              scan_ms=2_000_000)
        # No change value: still promotable (ranks last), never fabricated.
        self.assertEqual(out["promote"], ["XUSDT"])

    def test_core_never_promoted_or_shadowed(self) -> None:
        cands = {"BTCUSDT": cand(99.0, 9.0)}
        out = self.mgr.update(cands, ["BTCUSDT"], 2_000_000,
                              scan_ms=2_000_000)
        self.assertEqual(out["promote"], [])
        self.assertNotIn("BTCUSDT", self.mgr.desired_hot())

    def test_slot_enforcement(self) -> None:
        mgr = UniverseManager(core=("BTCUSDT",),
                              budget={"max_hot_slots": 1})
        cands = {"DOGEUSDT": cand(41.2, 1.0), "SOLUSDT": cand(8.6, 1.0)}
        out = mgr.update(cands, ["DOGEUSDT", "SOLUSDT"], 2_000_000,
                         scan_ms=2_000_000)
        self.assertEqual(out["promote"], ["DOGEUSDT"])
        self.assertEqual(mgr.desired_hot(), ("DOGEUSDT",))

    def test_stream_budget_fail_closed(self) -> None:
        mgr = UniverseManager(core=("BTCUSDT",),
                              budget={"max_total_streams": 1})
        cands = {"DOGEUSDT": cand(41.2, 1.0)}
        out = mgr.update(cands, ["DOGEUSDT"], 2_000_000,
                         scan_ms=2_000_000)
        self.assertEqual(out["promote"], [])
        self.assertEqual(out["refused"], ["DOGEUSDT"])
        self.assertEqual(mgr.budget_refusals, 1)

    def test_transport_freeze(self) -> None:
        cands = {"DOGEUSDT": cand(41.2, 1.0)}
        out = self.mgr.update(cands, ["DOGEUSDT"], 2_000_000,
                              scan_ms=2_000_000, transport_ok=False)
        self.assertEqual(out["promote"], [])
        self.assertTrue(any(e["kind"] == "frozen"
                            for e in out["events"]))


class LifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = UniverseManager(core=("BTCUSDT",))
        self.cands = {"DOGEUSDT": cand(41.2, 356_000_000)}
        self.mgr.update(self.cands, ["DOGEUSDT"], 2_000_000,
                        scan_ms=2_000_000)

    def test_promotion_pending_then_warming_then_live(self) -> None:
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_PROMOTION_PENDING)
        self.mgr.note_first_data("DOGEUSDT", 2_010_000)
        self.assertEqual(
            self.mgr.states_snapshot()["DOGEUSDT"]["state"], ST_WARMING)
        self.mgr.note_live("DOGEUSDT", 2_020_000)
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_LIVE)
        self.assertEqual(rec["live_since_ms"], 2_020_000)

    def test_live_to_degraded(self) -> None:
        self.mgr.note_first_data("DOGEUSDT", 2_010_000)
        self.mgr.note_live("DOGEUSDT", 2_020_000)
        self.mgr.note_degraded("DOGEUSDT", "all HOT streams silent",
                               2_030_000)
        self.assertEqual(
            self.mgr.states_snapshot()["DOGEUSDT"]["state"], ST_DEGRADED)

    def test_demotion_dwell_and_cooldown(self) -> None:
        self.mgr.note_first_data("DOGEUSDT", 2_010_000)
        self.mgr.note_live("DOGEUSDT", 2_020_000)
        # Immediate rank loss: dwell holds (min 1800s default).
        out = self.mgr.update(self.cands, [], 2_030_000, scan_ms=2_030_000)
        self.assertEqual(out["demote"], [])
        self.assertIn("DOGEUSDT", self.mgr.desired_hot())
        # After dwell + missed scans: demoted.
        out = self.mgr.update(self.cands, [], 4_000_000, scan_ms=4_000_000)
        self.assertEqual(out["demote"], ["DOGEUSDT"])
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_UNSUBSCRIBING)
        self.mgr.confirm_unsubscribed(["DOGEUSDT"], 4_010_000)
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_UNKNOWN)
        # Cooldown blocks immediate re-promotion.
        out = self.mgr.update(self.cands, ["DOGEUSDT"], 4_100_000,
                              scan_ms=4_100_000)
        self.assertEqual(out["promote"], [])
        self.assertEqual(self.mgr.desired_hot(), ())

    def test_ineligible_demotes_immediately(self) -> None:
        self.mgr.note_first_data("DOGEUSDT", 2_010_000)
        self.mgr.note_live("DOGEUSDT", 2_020_000)
        bad = {"DOGEUSDT": cand(41.2, 1.0, eligible=False)}
        out = self.mgr.update(bad, [], 2_030_000, scan_ms=2_030_000)
        # Ineligibility bypasses dwell (proven breach class).
        self.assertEqual(out["demote"], ["DOGEUSDT"])

    def test_partial_failure_returns_to_pending(self) -> None:
        self.mgr.note_failure("DOGEUSDT", "connect timeout", 2_010_000)
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_PROMOTION_PENDING)
        self.assertEqual(self.mgr.failed_promotions, 1)

    def test_repromotion_needs_fresh_data(self) -> None:
        self.mgr.confirm_unsubscribed(["DOGEUSDT"], 3_000_000)
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_UNKNOWN)
        self.assertIsNone(rec["first_data_ms"])
        self.assertIsNone(rec["live_since_ms"])


class UrlTest(unittest.TestCase):
    def test_empty_means_no_connections(self) -> None:
        self.assertEqual(build_hot_stream_urls(()), {})

    def test_stream_counts_and_split(self) -> None:
        urls = build_hot_stream_urls(("DOGEUSDT", "SOLUSDT"))
        self.assertEqual(set(urls), {"hot-public", "hot-market"})
        self.assertEqual(urls["hot-public"].count("@bookTicker"), 2)
        self.assertEqual(urls["hot-public"].count("@depth20@100ms"), 2)
        self.assertEqual(urls["hot-market"].count("@aggTrade"), 2)
        # Global array feeds are never duplicated onto HOT connections.
        self.assertNotIn("markPrice", urls["hot-public"])
        self.assertNotIn("markPrice", urls["hot-market"])
        self.assertNotIn("forceOrder", urls["hot-market"])

    def test_no_duplicate_subscriptions(self) -> None:
        urls = build_hot_stream_urls(("DOGEUSDT", "dogeusdt"))
        self.assertEqual(urls["hot-market"].count("dogeusdt@aggTrade"), 1)

    def test_expected_names_cover_hot(self) -> None:
        from microstructure_probe.config import load_config
        import pathlib
        cfg = load_config(pathlib.Path("config/probe.json"))
        names = expected_stream_names(cfg, ("DOGEUSDT",))
        self.assertIn("dogeusdt@aggTrade", names)
        self.assertIn("dogeusdt@bookTicker", names)
        self.assertIn("dogeusdt@depth20@100ms", names)
        base = expected_stream_names(cfg)
        self.assertNotIn("dogeusdt@aggTrade", base)


if __name__ == "__main__":
    unittest.main()
