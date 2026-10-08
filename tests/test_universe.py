"""P1-12B universe manager tests (deterministic, offline, no network)."""

from __future__ import annotations

import unittest

from microstructure_probe.probe import build_hot_stream_urls
from microstructure_probe.probe import expected_stream_names
T0 = 1_791_000_000_000  # realistic ms epoch for timestamp gates


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
    account_streams,
    check_timestamp_fresh,
    movement_key,
    streams_for_symbols,
)


def cand(change=None, volume=None, eligible=True, close_ms=T0-60_000):
    """Synthetic candidate; default close is 60ms before the T0 scans."""
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
        out = self.mgr.update({"BTCUSDT": cand(1.0, 9.0)}, [], T0,
                              scan_ms=T0)
        self.assertEqual(out["promote"], [])
        self.assertEqual(self.mgr.desired_hot(), ())

    def test_promotes_top_ranked_fresh_candidate(self) -> None:
        cands = {"DOGEUSDT": cand(41.2, 356_000_000),
                 "SOLUSDT": cand(8.6, 820_000_000),
                 "BTCUSDT": cand(2.4, 1_900_000_000)}
        out = self.mgr.update(cands, ["DOGEUSDT", "SOLUSDT"], T0,
                              scan_ms=T0)
        self.assertEqual(out["promote"], ["DOGEUSDT", "SOLUSDT"])
        self.assertEqual(self.mgr.desired_hot(), ("DOGEUSDT", "SOLUSDT"))

    def test_ineligible_never_promoted(self) -> None:
        cands = {"XUSDT": cand(99.0, 9.0, eligible=False)}
        out = self.mgr.update(cands, ["XUSDT"], T0,
                              scan_ms=T0)
        self.assertEqual(out["promote"], [])
        self.assertEqual(self.mgr.desired_hot(), ())

    def test_stale_discovery_skipped(self) -> None:
        cands = {"DOGEUSDT": cand(41.2, 356_000_000, close_ms=T0)}
        out = self.mgr.update(cands, ["DOGEUSDT"], T0+3_000_000,
                              scan_ms=T0+3_000_000)
        self.assertEqual(out["promote"], [])
        kinds = [e["kind"] for e in out["events"]]
        self.assertIn("skipped", kinds)

    def test_missing_metrics_handled(self) -> None:
        # No change/volume: still promotable (ranks last), never fabricated.
        cands = {"XUSDT": cand(None, None)}
        out = self.mgr.update(cands, ["XUSDT"], T0,
                              scan_ms=T0)
        self.assertEqual(out["promote"], ["XUSDT"])

    def test_core_never_promoted_or_shadowed(self) -> None:
        cands = {"BTCUSDT": cand(99.0, 9.0)}
        out = self.mgr.update(cands, ["BTCUSDT"], T0,
                              scan_ms=T0)
        self.assertEqual(out["promote"], [])
        self.assertNotIn("BTCUSDT", self.mgr.desired_hot())

    def test_slot_enforcement(self) -> None:
        mgr = UniverseManager(core=("BTCUSDT",),
                              budget={"max_hot_slots": 1})
        cands = {"DOGEUSDT": cand(41.2, 1.0), "SOLUSDT": cand(8.6, 1.0)}
        out = mgr.update(cands, ["DOGEUSDT", "SOLUSDT"], T0,
                         scan_ms=T0)
        self.assertEqual(out["promote"], ["DOGEUSDT"])
        self.assertEqual(mgr.desired_hot(), ("DOGEUSDT",))

    def test_stream_budget_fail_closed(self) -> None:
        mgr = UniverseManager(core=("BTCUSDT",),
                              budget={"max_total_streams": 1})
        cands = {"DOGEUSDT": cand(41.2, 1.0)}
        out = mgr.update(cands, ["DOGEUSDT"], T0,
                         scan_ms=T0)
        self.assertEqual(out["promote"], [])
        self.assertEqual(out["refused"], ["DOGEUSDT"])
        self.assertEqual(mgr.budget_refusals, 1)

    def test_transport_freeze(self) -> None:
        cands = {"DOGEUSDT": cand(41.2, 1.0)}
        out = self.mgr.update(cands, ["DOGEUSDT"], T0,
                              scan_ms=T0, transport_ok=False)
        self.assertEqual(out["promote"], [])
        self.assertTrue(any(e["kind"] == "frozen"
                            for e in out["events"]))


class LifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = UniverseManager(core=("BTCUSDT",))
        self.cands = {"DOGEUSDT": cand(41.2, 356_000_000)}
        self.mgr.update(self.cands, ["DOGEUSDT"], T0,
                        scan_ms=T0)

    def test_promotion_pending_then_warming_then_live(self) -> None:
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_PROMOTION_PENDING)
        self.mgr.note_first_data("DOGEUSDT", T0+10_000)
        self.assertEqual(
            self.mgr.states_snapshot()["DOGEUSDT"]["state"], ST_WARMING)
        self.mgr.note_live("DOGEUSDT", T0+20_000)
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_LIVE)
        self.assertEqual(rec["live_since_ms"], T0+20_000)

    def test_live_to_degraded(self) -> None:
        self.mgr.note_first_data("DOGEUSDT", T0+10_000)
        self.mgr.note_live("DOGEUSDT", T0+20_000)
        self.mgr.note_degraded("DOGEUSDT", "all HOT streams silent",
                               T0+30_000)
        self.assertEqual(
            self.mgr.states_snapshot()["DOGEUSDT"]["state"], ST_DEGRADED)

    def test_demotion_dwell_and_cooldown(self) -> None:
        self.mgr.note_first_data("DOGEUSDT", T0+10_000)
        self.mgr.note_live("DOGEUSDT", T0+20_000)
        # Immediate rank loss: dwell holds (min 1800s default).
        out = self.mgr.update(self.cands, [], T0+30_000, scan_ms=T0+30_000)
        self.assertEqual(out["demote"], [])
        self.assertIn("DOGEUSDT", self.mgr.desired_hot())
        # After dwell + missed scans: demoted (fresh close at new scan).
        fresh_cands = {"DOGEUSDT": cand(41.2, 356_000_000,
                                       close_ms=T0+1_940_000)}
        out = self.mgr.update(fresh_cands, [], T0+2_000_000, scan_ms=T0+2_000_000)
        self.assertEqual(out["demote"], ["DOGEUSDT"])
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_UNSUBSCRIBING)
        self.mgr.confirm_unsubscribed(["DOGEUSDT"], 4_010_000)
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_UNKNOWN)
        # Cooldown blocks immediate re-promotion.
        out = self.mgr.update(self.cands, ["DOGEUSDT"], T0+2_100_000,
                              scan_ms=T0+2_100_000)
        self.assertEqual(out["promote"], [])
        self.assertEqual(self.mgr.desired_hot(), ())

    def test_ineligible_demotes_immediately(self) -> None:
        self.mgr.note_first_data("DOGEUSDT", T0+10_000)
        self.mgr.note_live("DOGEUSDT", T0+20_000)
        bad = {"DOGEUSDT": cand(41.2, 1.0, eligible=False)}
        out = self.mgr.update(bad, [], T0+30_000, scan_ms=T0+30_000)
        # Ineligibility bypasses dwell (proven breach class).
        self.assertEqual(out["demote"], ["DOGEUSDT"])

    def test_partial_failure_returns_to_pending(self) -> None:
        self.mgr.note_failure("DOGEUSDT", "connect timeout", T0+10_000)
        rec = self.mgr.states_snapshot()["DOGEUSDT"]
        self.assertEqual(rec["state"], ST_PROMOTION_PENDING)
        self.assertEqual(self.mgr.failed_promotions, 1)

    def test_repromotion_needs_fresh_data(self) -> None:
        self.mgr.confirm_unsubscribed(["DOGEUSDT"], T0+1_000_000)
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


class TimestampFreshnessTest(unittest.TestCase):
    """P1-12B.1 Concern A: strict ticker-timestamp gate (fail-closed)."""

    def test_valid_fresh_timestamp(self) -> None:
        fresh, reason = check_timestamp_fresh(1_790_999_940_000,
                                             1_791_000_000_000,
                                             1_800_000)
        self.assertTrue(fresh)

    def test_missing_timestamp_rejected(self) -> None:
        mgr = UniverseManager(core=("BTCUSDT",))
        cands = {"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                              "quote_volume_24h": 1.0,
                              "ticker_close_ms": None}}
        out = mgr.update(cands, ["DOGEUSDT"], T0, scan_ms=T0)
        self.assertEqual(out["promote"], [])
        self.assertTrue(any(e["kind"] == "skipped" and "missing" in e["reason"]
                            for e in out["events"]))

    def test_malformed_timestamp_rejected_without_aborting_update(self) -> None:
        mgr = UniverseManager(core=("BTCUSDT",))
        cands = {"BADUSDT": {"eligible": True, "change_24h_pct": 99.0,
                             "quote_volume_24h": 1.0,
                             "ticker_close_ms": "not-a-time"},
                 "DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                              "quote_volume_24h": 1.0,
                              "ticker_close_ms": T0-60_000}}
        out = mgr.update(cands, ["BADUSDT", "DOGEUSDT"], T0,
                         scan_ms=T0)
        self.assertEqual(out["promote"], ["DOGEUSDT"])
        self.assertTrue(any(e["symbol"] == "BADUSDT" and "malformed" in e["reason"]
                            for e in out["events"]))

    def test_seconds_confusion_rejected(self) -> None:
        fresh, reason = check_timestamp_fresh(1_790_000_000, 1_791_000_000_000,
                                             1_800_000)
        self.assertFalse(fresh)
        self.assertIn("unit", reason)

    def test_excessively_old_rejected(self) -> None:
        fresh, _ = check_timestamp_fresh(T0, 2_000_000_000, 1_800_000)
        self.assertFalse(fresh)

    def test_excessively_future_rejected(self) -> None:
        fresh, reason = check_timestamp_fresh(1_791_500_000_000,
                                             1_791_000_000_000,
                                             1_800_000, 60_000)
        self.assertFalse(fresh)
        self.assertIn("future", reason)

    def test_small_future_skew_permitted(self) -> None:
        fresh, _ = check_timestamp_fresh(1_791_000_030_000,
                                        1_791_000_000_000,
                                        1_800_000, 60_000)
        self.assertTrue(fresh)

    def test_stale_snapshot_blocks_promotion(self) -> None:
        mgr = UniverseManager(core=("BTCUSDT",))
        cands = {"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                              "quote_volume_24h": 1.0,
                              "ticker_close_ms": T0}}
        out = mgr.update(cands, ["DOGEUSDT"], T0+7_000_000, scan_ms=T0+7_000_000)
        self.assertEqual(out["promote"], [])

    def test_core_unaffected_by_invalid_hot_candidates(self) -> None:
        mgr = UniverseManager(core=("BTCUSDT",))
        cands = {"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                              "quote_volume_24h": 1.0,
                              "ticker_close_ms": None}}
        mgr.update(cands, ["DOGEUSDT", "BTCUSDT"], T0,
                   scan_ms=T0)
        self.assertNotIn("BTCUSDT", mgr.desired_hot())
        self.assertNotIn("BTCUSDT", mgr.states_snapshot())

    def test_missing_never_interpreted_as_zero(self) -> None:
        fresh, _ = check_timestamp_fresh(None, T0, 1_800_000)
        self.assertFalse(fresh)
        fresh2, _ = check_timestamp_fresh(0, T0, 1_800_000)
        self.assertFalse(fresh2)


class StreamAccountingTest(unittest.TestCase):
    """P1-12B.1 Concern B: one authoritative inventory, no conflation."""

    def test_canonical_inventory(self) -> None:
        acct = account_streams(3, ())
        self.assertEqual(acct["canonical_streams"], 11)  # 9 + 2 globals
        self.assertEqual(acct["hot_streams"], 0)
        self.assertEqual(acct["total_streams"], 11)
        self.assertEqual(acct["connections"], 2)
        self.assertEqual(acct["per_connection"],
                         {"canonical-public": 6, "canonical-market": 5,
                          "hot-public": 0, "hot-market": 0})

    def test_hot_inventory_three_symbols(self) -> None:
        acct = account_streams(3, ("A", "B", "C"))
        self.assertEqual(acct["hot_streams"], 9)
        self.assertEqual(acct["total_streams"], 20)  # 11 + 9, no +2 fudge
        self.assertEqual(acct["connections"], 4)
        self.assertEqual(acct["per_connection"]["hot-public"], 6)
        self.assertEqual(acct["per_connection"]["hot-market"], 3)

    def test_connections_and_streams_separate_units(self) -> None:
        acct = account_streams(3, ("A",))
        # One HOT symbol: 3 streams on 2 connections — never 3+2=5 streams.
        self.assertEqual(acct["hot_streams"], 3)
        self.assertEqual(acct["connections"], 4)
        self.assertEqual(acct["total_streams"], 14)

    def test_global_feeds_counted_once(self) -> None:
        from microstructure_probe.config import load_config
        import pathlib
        cfg = load_config(pathlib.Path("config/probe.json"))
        names = expected_stream_names(cfg)
        self.assertEqual(names.count("!markPrice@arr@1s"), 1)
        self.assertEqual(names.count("!forceOrder@arr"), 1)
        self.assertEqual(len(names), 11)

    def test_telemetry_matches_enforcement(self) -> None:
        mgr = UniverseManager(core=("BTCUSDT", "ETHUSDT", "SOLUSDT"))
        mgr.update({"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                                 "quote_volume_24h": 1.0,
                                 "ticker_close_ms": T0-60_000}},
                   ["DOGEUSDT"], T0, scan_ms=T0)
        usage = mgr.slot_usage()
        acct = account_streams(3, mgr.desired_hot())
        self.assertEqual(usage["total_streams"], acct["total_streams"])
        self.assertEqual(usage["connections"], acct["connections"])
        self.assertEqual(usage["canonical_streams"], 11)

    def test_total_stream_limit_enforced(self) -> None:
        mgr = UniverseManager(
            core=("BTCUSDT",),
            budget={"max_hot_slots": 5, "max_total_streams": 12,
                    "max_streams_per_connection": 50, "max_connections": 6,
                    "promotion_interval_seconds": 600,
                    "min_dwell_seconds": 0,
                    "demotion_cooldown_seconds": 0,
                    "max_discovery_age_seconds": 1800,
                    "demote_after_missed_scans": 2,
                    "max_hot_reconnects_per_hour": 10,
                    "clock_skew_tolerance_ms": 60_000})
        cands = {"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                              "quote_volume_24h": 1.0,
                              "ticker_close_ms": T0-60_000}}
        out = mgr.update(cands, ["DOGEUSDT"], T0, scan_ms=T0)
        # Canonical 1*3+2=5, +3 HOT = 8 <= 12: allowed.
        self.assertEqual(out["promote"], ["DOGEUSDT"])

    def test_connection_limit_enforced(self) -> None:
        mgr = UniverseManager(
            core=("BTCUSDT",),
            budget={"max_hot_slots": 5, "max_total_streams": 60,
                    "max_streams_per_connection": 50, "max_connections": 2,
                    "promotion_interval_seconds": 600,
                    "min_dwell_seconds": 0,
                    "demotion_cooldown_seconds": 0,
                    "max_discovery_age_seconds": 1800,
                    "demote_after_missed_scans": 2,
                    "max_hot_reconnects_per_hour": 10,
                    "clock_skew_tolerance_ms": 60_000})
        cands = {"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                              "quote_volume_24h": 1.0,
                              "ticker_close_ms": T0-60_000}}
        out = mgr.update(cands, ["DOGEUSDT"], T0, scan_ms=T0)
        # HOT needs 4 connections total > 2: refused, fail closed.
        self.assertEqual(out["promote"], [])
        self.assertEqual(out["refused"], ["DOGEUSDT"])

    def test_per_connection_limit_enforced(self) -> None:
        mgr = UniverseManager(
            core=("BTCUSDT",),
            budget={"max_hot_slots": 5, "max_total_streams": 600,
                    "max_streams_per_connection": 1, "max_connections": 6,
                    "promotion_interval_seconds": 600,
                    "min_dwell_seconds": 0,
                    "demotion_cooldown_seconds": 0,
                    "max_discovery_age_seconds": 1800,
                    "demote_after_missed_scans": 2,
                    "max_hot_reconnects_per_hour": 10,
                    "clock_skew_tolerance_ms": 60_000})
        cands = {"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                              "quote_volume_24h": 1.0,
                              "ticker_close_ms": T0-60_000}}
        out = mgr.update(cands, ["DOGEUSDT"], T0, scan_ms=T0)
        # hot-public would carry 2 streams > 1: refused.
        self.assertEqual(out["promote"], [])


if __name__ == "__main__":
    unittest.main()
