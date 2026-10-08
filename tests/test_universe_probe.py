"""P1-12B probe integration tests (mocked transport, no network)."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from microstructure_probe.classifier import ClassifierEngine
T0 = 1_791_000_000_000  # realistic ms epoch for timestamp gates


from microstructure_probe.probe import MarketProbe
from test_detectors import test_config


def make_probe():
    return MarketProbe(test_config())


def cands(*symbols):
    out = []
    for i, sym in enumerate(symbols):
        m = mock.Mock()
        m.symbol = sym
        m.eligible = True
        m.change_24h_pct = 40.0 - i
        m.quote_volume_24h = 500_000_000.0
        m.ticker_close_ms = T0
        out.append(m)
    return out


class HotSyncTest(unittest.TestCase):
    def test_promote_spawns_managed_tasks_and_allows_engines(self) -> None:
        probe = make_probe()
        created = []

        async def fake_loop(name, url):
            created.append((name, url() if callable(url) else url))
            await asyncio.sleep(3600)

        probe._connection_loop = fake_loop  # type: ignore[method-assign]
        probe._universe.update(
            {"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                          "quote_volume_24h": 356_000_000.0,
                          "ticker_close_ms": T0-60_000}},
            ["DOGEUSDT"], T0, scan_ms=T0)
        asyncio.run(probe._sync_hot_subscriptions(reason="test"))
        try:
            names = sorted(probe._hot_tasks)
            self.assertEqual(names, ["hot-market", "hot-public"])
            self.assertEqual(probe._hot_active, ("DOGEUSDT",))
            self.assertIn("DOGEUSDT", probe._flow._allowed)
            self.assertIn("DOGEUSDT", probe._book._allowed)
            self.assertIn("DOGEUSDT", probe._returns._allowed)
            self.assertIn("DOGEUSDT", probe._classifier._allowed)
            self.assertIn("DOGEUSDT", probe._oi_poller.hot_symbols)
            # No duplicate subscriptions: exactly one task per endpoint.
            self.assertEqual(len(created), 2)
            hot_market = dict(created)["hot-market"]
            self.assertEqual(hot_market.count("dogeusdt@aggTrade"), 1)
        finally:
            for task in list(probe._hot_tasks.values()):
                task.cancel()

    def test_demote_cancels_forgets_and_cools_down(self) -> None:
        probe = make_probe()

        async def fake_loop(name, url):
            await asyncio.sleep(3600)

        async def scenario():
            probe._connection_loop = fake_loop  # type: ignore[method-assign]
            probe._universe.update(
                {"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                              "quote_volume_24h": 356_000_000.0,
                              "ticker_close_ms": T0-60_000}},
                ["DOGEUSDT"], T0, scan_ms=T0)
            await probe._sync_hot_subscriptions(reason="test")
            # Force demotion: ineligible bypasses dwell.
            probe._universe.update(
                {"DOGEUSDT": {"eligible": False, "change_24h_pct": 41.2,
                              "quote_volume_24h": 1.0,
                              "ticker_close_ms": T0+1_940_000}},
                [], T0+2_000_000, scan_ms=T0+2_000_000)
            probe._hot_last_resync = None  # past the resync guard
            with mock.patch.object(probe._flow, "forget",
                                   wraps=probe._flow.forget
                                   ) as forget_flow, \
                 mock.patch.object(probe._research, "finalize_symbol",
                                   wraps=probe._research.finalize_symbol
                                   ) as finalize:
                await probe._sync_hot_subscriptions(reason="test")
            return forget_flow, finalize

        try:
            forget_flow, finalize = asyncio.run(scenario())
            self.assertEqual(probe._hot_active, ())
            self.assertEqual(probe._hot_tasks, {})
            self.assertTrue(forget_flow.called)
            self.assertTrue(finalize.called)
            self.assertNotIn("DOGEUSDT", probe._oi_poller.hot_symbols)
            states = probe._universe.states_snapshot()
            self.assertEqual(states["DOGEUSDT"]["state"], "UNKNOWN")
        finally:
            for task in list(probe._hot_tasks.values()):
                task.cancel()

    def test_no_resync_when_set_unchanged(self) -> None:
        probe = make_probe()
        probe._hot_active = ("DOGEUSDT",)
        probe._universe.update(
            {"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                          "quote_volume_24h": 356_000_000.0,
                          "ticker_close_ms": T0-60_000}},
            ["DOGEUSDT"], T0, scan_ms=T0)
        with mock.patch.object(probe, "_connection_loop") as loop:
            asyncio.run(probe._sync_hot_subscriptions(reason="test"))
            loop.assert_not_called()

    def test_canonical_pair_untouched_by_sync(self) -> None:
        probe = make_probe()
        urls_before = sorted(probe._hot_tasks)
        asyncio.run(probe._sync_hot_subscriptions(reason="test"))
        self.assertEqual(sorted(probe._hot_tasks), urls_before)
        self.assertEqual(probe._hot_active, ())


class HotDataTrackingTest(unittest.TestCase):
    def _promoted(self, probe):
        probe._universe.update(
            {"DOGEUSDT": {"eligible": True, "change_24h_pct": 41.2,
                          "quote_volume_24h": 356_000_000.0,
                          "ticker_close_ms": T0-60_000}},
            ["DOGEUSDT"], T0, scan_ms=T0)
        probe._hot_active = ("DOGEUSDT",)

    def test_warming_then_live_on_mark_trade_depth(self) -> None:
        probe = make_probe()
        self._promoted(probe)
        with mock.patch.object(probe, "_wall_clock_ms",
                               return_value=T0+10_000.0):
            probe._note_hot_data("DOGEUSDT", "trade")
            self.assertEqual(
                probe._universe.states_snapshot()["DOGEUSDT"]["state"],
                "WARMING")
            probe._note_hot_data("DOGEUSDT", "mark")
            probe._note_hot_data("DOGEUSDT", "depth")
            self.assertEqual(
                probe._universe.states_snapshot()["DOGEUSDT"]["state"],
                "LIVE")

    def test_core_symbols_not_tracked(self) -> None:
        probe = make_probe()
        probe._note_hot_data("BTCUSDT", "trade")
        self.assertNotIn("BTCUSDT", probe._universe.states_snapshot())

    def test_classifier_unknown_during_warmup(self) -> None:
        eng = ClassifierEngine(symbols=("DOGEUSDT",))
        warming = {
            "subscribed": True, "live": False, "tier": "HOT",
            "price": {"current_price": None, "sample_age_ms": None},
            "returns": {"returns": {"1m": None}},
            "momentum": {"velocity": {"1m": None},
                         "acceleration": {"1m": None}},
            "flow": {}, "book": {}, "oi": {}, "structure": {},
        }
        out = eng.evaluate({"DOGEUSDT": warming}, T0+10_000)[0]
        self.assertEqual(out["state"], "UNKNOWN")


class RecorderIsolationTest(unittest.TestCase):
    def test_finalize_marks_partial_without_cross_contamination(self) -> None:
        from microstructure_probe.research_recorder import ResearchRecorder
        rec = ResearchRecorder(enabled=False)
        hot_bucket = mock.Mock(partial=False)
        core_bucket = mock.Mock(partial=False)
        rec._flow_open[("DOGEUSDT", 10)] = hot_bucket
        rec._flow_open[("BTCUSDT", 10)] = core_bucket
        rec._book_open["DOGEUSDT"] = mock.Mock()
        closed = rec.finalize_symbol("DOGEUSDT")
        self.assertEqual(closed, {"flow": 1, "book_discarded": 1})
        self.assertTrue(hot_bucket.partial)
        self.assertFalse(core_bucket.partial)
        self.assertIn(("BTCUSDT", 10), rec._flow_open)
        self.assertNotIn(("DOGEUSDT", 10), rec._flow_open)
        self.assertNotIn("DOGEUSDT", rec._book_open)
        # Enqueued for persistence with PARTIAL quality, not dropped.
        self.assertEqual(rec._queue.qsize(), 1)


class UniverseConfigTest(unittest.TestCase):
    def test_defaults_backward_compatible(self) -> None:
        cfg = test_config()
        self.assertTrue(cfg.universe.enabled)
        self.assertEqual(cfg.universe.max_hot_slots, 3)
        self.assertGreaterEqual(cfg.universe.max_connections, 4)

    def test_observe_only_safety_surface(self) -> None:
        import pathlib
        source = "\n".join(
            pathlib.Path("src/microstructure_probe", name).read_text(
                encoding="utf-8")
            for name in ("universe_manager.py", "probe.py",
                         "research_recorder.py")
        ).lower()
        for term in ("/fapi/v1/order", "x-mbx-apikey", "create_order",
                     "place_order", "send_order", "api_secret", "/private/"):
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
