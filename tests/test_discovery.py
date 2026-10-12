"""Tests for P1-05 public discovery layer + HOT selection + hysteresis."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe.discovery import (
    CORE_SYMBOLS,
    DiscoveryClient,
    build_candidates,
    select_hot,
    top_movers,
)


def _meta(symbol, status="TRADING", ctype="PERPETUAL", quote="USDT"):
    return {"symbol": symbol, "status": status, "contractType": ctype,
            "quoteAsset": quote}


def _tick(symbol, change="5.0", volume="2000000", price="100.0", count=100):
    return {"symbol": symbol, "priceChangePercent": change,
            "quoteVolume": volume, "lastPrice": price, "count": count,
            "closeTime": 1_700_000_000_000}


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


class DiscoveryFilterTest(unittest.TestCase):
    def test_core_trio_eligible(self) -> None:
        infos = {"symbols": [_meta(s) for s in CORE_SYMBOLS]}
        ticks = [_tick(s) for s in CORE_SYMBOLS]
        cands = {c.symbol: c for c in build_candidates(infos, ticks, 1_000_000.0)}
        for symbol in CORE_SYMBOLS:
            self.assertTrue(cands[symbol].eligible, symbol)
            self.assertEqual(cands[symbol].exclusion_reasons, [])

    def test_eligibility_rules(self) -> None:
        infos = {"symbols": [
            _meta("AUSDT"),
            _meta("BUSDT", status="SETTLING"),
            _meta("CUSDT", ctype="CURRENT_QUARTER"),
            _meta("DUSDC", quote="USDC"),
            _meta("EUSDT"),
        ]}
        ticks = [_tick("AUSDT"), _tick("BUSDT"), _tick("CUSDT"),
                 _tick("DUSDC"), _tick("EUSDT", volume="10.0")]
        by_symbol = {c.symbol: c for c in build_candidates(infos, ticks, 1_000_000.0)}
        self.assertTrue(by_symbol["AUSDT"].eligible)
        self.assertIn("status=SETTLING", by_symbol["BUSDT"].exclusion_reasons)
        self.assertIn("contract_type=CURRENT_QUARTER",
                      by_symbol["CUSDT"].exclusion_reasons)
        self.assertIn("quote_asset=USDC", by_symbol["DUSDC"].exclusion_reasons)
        self.assertTrue(any("below_floor" in r
                            for r in by_symbol["EUSDT"].exclusion_reasons))

    def test_unknown_volume_never_eligible_never_fabricated(self) -> None:
        infos = {"symbols": [_meta("XUSDT")]}
        ticks = [{"symbol": "XUSDT", "priceChangePercent": "99.0",
                  "lastPrice": "1.0"}]
        (cand,) = build_candidates(infos, ticks, 1_000_000.0)
        self.assertFalse(cand.eligible)
        self.assertIn("quote_volume_unknown", cand.exclusion_reasons)
        self.assertIsNone(cand.quote_volume_24h)

    def test_missing_sides_kept_with_reasons(self) -> None:
        infos = {"symbols": [_meta("NOMETAUSDT")]}
        cands = build_candidates(infos, [], 1_000_000.0)
        self.assertEqual(len(cands), 1)
        self.assertFalse(cands[0].eligible)


class HotSelectionTest(unittest.TestCase):
    def _pool(self):
        infos = {"symbols": [_meta(s) for s in
                             ("AAAUSDT", "BBBUSDT", "CCUSDT", "DDUSDT")]}
        ticks = [_tick("AAAUSDT", change="25.0", volume="5000000"),
                 _tick("BBBUSDT", change="-30.0", volume="4000000"),
                 _tick("CCUSDT", change="2.0", volume="9000000"),
                 _tick("DDUSDT", change="25.0", volume="6000000")]
        return build_candidates(infos, ticks, 1_000_000.0)

    def test_deterministic_bounded_movement_ranked(self) -> None:
        cands = self._pool()
        first, events1, state = select_hot(cands, dynamic_slots=2, min_votes=1)
        second, events2, _ = select_hot(cands, dynamic_slots=2, min_votes=1)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 2)
        # |change| first: BBB (-30) then DDD (+25, higher volume beats AAA).
        self.assertEqual(first, ["BBBUSDT", "DDUSDT"])
        self.assertTrue(all(e["kind"] == "promoted" for e in events1))

    def test_core_never_voted_never_in_dynamic(self) -> None:
        infos = {"symbols": [_meta(s) for s in CORE_SYMBOLS + ("HOTUSDT",)]}
        ticks = ([_tick(s, change="1.0") for s in CORE_SYMBOLS]
                 + [_tick("HOTUSDT", change="50.0")])
        cands = build_candidates(infos, ticks, 1_000_000.0)
        dynamic, _, _ = select_hot(cands, dynamic_slots=3, min_votes=1)
        self.assertNotIn("BTCUSDT", dynamic)
        self.assertIn("HOTUSDT", dynamic)

    def test_hysteresis_requires_votes_and_dwell(self) -> None:
        cands = self._pool()
        dynamic, events, state = select_hot(
            cands, dynamic_slots=2, prior_dynamic=(), state=None, min_votes=2)
        self.assertEqual(dynamic, [])  # one appearance is not enough
        self.assertEqual(events, [])
        dynamic, events, state = select_hot(
            cands, dynamic_slots=2, prior_dynamic=tuple(dynamic),
            state=state, min_votes=2)
        self.assertEqual(dynamic, ["BBBUSDT", "DDUSDT"])
        self.assertEqual(len([e for e in events if e["kind"] == "promoted"]), 2)
        # Incumbent survives a single absence.
        quiet = [c for c in cands if c.symbol not in ("BBBUSDT", "DDUSDT")]
        dynamic2, events2, state = select_hot(
            quiet, dynamic_slots=2, prior_dynamic=tuple(dynamic),
            state=state, min_votes=2)
        self.assertEqual(sorted(dynamic2), ["BBBUSDT", "DDUSDT"])
        self.assertEqual(events2, [])
        # Second consecutive absence demotes (empty eligible pool edge).
        dynamic3, events3, _ = select_hot(
            [], dynamic_slots=2, prior_dynamic=tuple(dynamic2),
            state=state, min_votes=2)
        self.assertEqual(dynamic3, [])
        self.assertTrue(any(e["kind"] == "demoted" for e in events3))

    def test_ineligibility_demotes_immediately(self) -> None:
        cands = self._pool()
        _, _, state = select_hot(cands, dynamic_slots=2, min_votes=1)
        dynamic, _, state = select_hot(
            cands, dynamic_slots=2, min_votes=1)
        # BBBUSDT delists: immediate demotion regardless of dwell.
        infos = {"symbols": [_meta("BBBUSDT", status="SETTLING")]}
        ticks = [_tick("BBBUSDT", change="-30.0")]
        stale = build_candidates(infos, ticks, 1_000_000.0)
        dynamic2, events, _ = select_hot(
            stale, dynamic_slots=2, prior_dynamic=tuple(dynamic),
            state=state, min_votes=2)
        self.assertNotIn("BBBUSDT", dynamic2)
        self.assertTrue(any(e["kind"] == "demoted"
                            and e["symbol"] == "BBBUSDT" for e in events))

    def test_top_movers_are_movement_not_cap(self) -> None:
        cands = self._pool()
        tops = top_movers(cands, top_n=2)
        self.assertEqual([r["symbol"] for r in tops["gainers"]],
                         ["AAAUSDT", "DDUSDT"])
        self.assertEqual([r["symbol"] for r in tops["losers"]],
                         ["BBBUSDT", "CCUSDT"])
        self.assertEqual(tops["most_active"][0]["symbol"], "CCUSDT")


class DiscoveryClientTest(unittest.TestCase):
    def test_scan_with_injected_fetch_never_hits_network(self) -> None:
        calls = []

        def fake_fetch(url: str, timeout: float):
            calls.append(url)
            if "exchangeInfo" in url:
                return {"symbols": [_meta("FAKEUSDT")]}
            return [_tick("FAKEUSDT", change="7.0")]

        client = DiscoveryClient(fetch=fake_fetch)
        cands, counts = client.scan(1_000_000.0)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("fapi.binance.com" in url for url in calls))
        self.assertNotIn("api key", " ".join(calls).lower())
        self.assertEqual(counts, {"symbols_seen": 1, "eligible": 1})
        self.assertEqual(cands[0].symbol, "FAKEUSDT")

    def test_malformed_payload_raises(self) -> None:
        client = DiscoveryClient(fetch=lambda url, timeout: {"nope": True})
        with self.assertRaises(ValueError):
            client.scan(1_000_000.0)


class SubscriptionBoundTest(unittest.TestCase):
    def test_hot_set_never_changes_subscriptions(self) -> None:
        """HOT proposal must not open unbounded websocket load."""
        from microstructure_probe.probe import MarketProbe, build_stream_urls
        from test_detectors import test_config

        import tempfile
        from microstructure_probe.history_store import HistoryStore
        from microstructure_probe.persistence import PersistenceStore
        tmp = Path(tempfile.mkdtemp(prefix="subbound_test_"))
        self.addCleanup(lambda: _rmtree(tmp))
        store = PersistenceStore(tmp / "probe.db")
        store.init_db()
        self.addCleanup(store.close)
        probe = MarketProbe(test_config(), persistence_store=store,
                            research_history_store=HistoryStore(
                                tmp / "historical.db"))
        probe._hot_dynamic = tuple(f"SYM{i}USDT" for i in range(50))
        urls = build_stream_urls(probe.config)
        blob = urls["public"] + urls["market"]
        self.assertIn("btcusdt@bookTicker", blob)
        for i in range(50):
            self.assertNotIn(f"sym{i}usdt@", blob)


class ProbeDiscoveryScanTest(unittest.TestCase):
    """Probe scan with injected client: selection + events + summary block."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path

        from microstructure_probe.persistence import PersistenceStore
        from microstructure_probe.probe import MarketProbe
        from test_detectors import test_config

        self.temp_dir = tempfile.mkdtemp(prefix="probe_disc_test_")
        self.db_path = Path(self.temp_dir) / "disc.db"
        self.store = PersistenceStore(db_path=self.db_path)
        self.store.sample_interval_ms = {}
        from microstructure_probe.history_store import HistoryStore
        self.hist = HistoryStore(Path(self.temp_dir) / "historical.db")
        self.probe = MarketProbe(test_config(), persistence_store=self.store,
                                 research_history_store=self.hist)

        infos = {"symbols": [_meta("BTCUSDT"),
                             _meta("SCREAMUSDT"),
                             _meta("LOWUSDT")]}
        ticks = [_tick("BTCUSDT", change="1.0"),
                 _tick("SCREAMUSDT", change="40.0", volume="8000000"),
                 _tick("LOWUSDT", change="60.0", volume="10.0")]

        class FakeClient:
            def scan(self, min_quote_volume_usdt):
                cands = build_candidates(infos, ticks, min_quote_volume_usdt)
                return cands, {"symbols_seen": 3,
                               "eligible": sum(1 for c in cands if c.eligible)}

        self.probe.set_discovery_client(FakeClient())

    def tearDown(self) -> None:
        self.store.close()
        try:
            self.db_path.unlink(missing_ok=True)
            self.db_path.parent.rmdir()
        except OSError:
            pass

    def test_scan_selects_hot_persists_and_reports(self) -> None:
        import asyncio

        snapshot = asyncio.run(self.probe.run_discovery_scan())
        # SCREAMUSDT eligible top mover; LOWUSDT fails the volume floor.
        self.assertEqual(snapshot["eligible_count"], 2)
        self.assertEqual(snapshot["hot_dynamic"], [])
        self.assertEqual(snapshot["core"], ["BTCUSDT"])
        second = asyncio.run(self.probe.run_discovery_scan())
        self.assertEqual(second["hot_dynamic"], ["SCREAMUSDT"])
        stored = self.store.latest_discovery()
        self.assertEqual(stored["hot_dynamic"], ["SCREAMUSDT"])
        events = self.store.universe_events()
        self.assertTrue(any(e["kind"] == "promoted"
                            and e["symbol"] == "SCREAMUSDT" for e in events))
        summary = self.probe.build_summary(final=False)
        self.assertEqual(summary["discovery"]["eligible"], 2)
        self.assertEqual(summary["discovery"]["hot_dynamic"], ["SCREAMUSDT"])

    def test_scan_failure_never_breaks_probe(self) -> None:
        class BadClient:
            def scan(self, floor):
                raise ConnectionError("offline")

        self.probe.set_discovery_client(BadClient())
        import asyncio
        snapshot = asyncio.run(self.probe.run_discovery_scan())
        self.assertIn("error", snapshot)
        self.assertIsNone(self.store.latest_discovery())
        self.assertIn("offline", self.probe._discovery_info["error"])

    def test_momentum_and_ranks_persisted_on_summary(self) -> None:
        import json as _json

        from microstructure_probe.probe import MarketProbe
        from test_detectors import test_config

        t0 = 1_700_000_000_000
        clock = [t0]
        probe = MarketProbe(
            test_config(), wall_clock_ms=lambda: float(clock[0]),
            monotonic=lambda: 10.0, persistence_store=self.store,
            research_history_store=self.hist)
        for i in range(25):  # ~4 min of rising mark-price history, zero skew
            clock[0] = t0 + i * 10_000
            probe._handle_message(_json.dumps({
                "stream": "!markPrice@arr@1s",
                "data": [{"E": t0 + i * 10_000, "T": 999_999,
                          "s": "BTCUSDT", "p": str(100.0 + i * 0.1),
                          "r": "0.0001"}],
            }))
        probe.log_summary(final=False)
        rows = {f["symbol"]: f for f in self.store.latest_return_features()}
        self.assertIn("BTCUSDT", rows)
        row = rows["BTCUSDT"]
        self.assertIn("momentum", row)
        self.assertEqual(row["tier"], "CORE")
        self.assertIsNotNone(row["momentum"]["velocity"]["1m"])
        ranks = self.store.latest_ranks()
        self.assertIn("velocity_1m", ranks)
        self.assertEqual(ranks["velocity_1m"]["BTCUSDT"]["rank"], 1)


if __name__ == "__main__":
    unittest.main()
