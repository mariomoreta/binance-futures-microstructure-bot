"""P1-09 market-intelligence terminal tests.

Covers: routing (/movers, /symbol/:symbol, /search), search behavior,
movers categories + tier/capability labels, token-detail panels + honesty,
chart API + CSV export, UI regressions (no signals/controls, escaping,
unicode), and P1-04..P1-08 API regressions.
"""

import json
import re
import sys
import tempfile
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import dashboard
from microstructure_probe.dashboard import DashboardServer
from microstructure_probe.persistence import PersistenceStore

T0 = 1_700_000_000_000


def _temp_store(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="p109_test_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    store = PersistenceStore(db_path=tmp / "p109.db")
    store.init_db()
    testcase.addCleanup(store.close)
    return store


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


def _snapshot(**overrides):
    base = {
        "runtimeSeconds": 100.0,
        "safety": {
            "BOT_MODE": "observe",
            "apiKeysUsed": 0,
            "realOrdersSent": 0,
            "realCapitalAtRisk": 0.0,
            "maxDrawdownKillSwitchActive": False,
            "authenticatedClientsPresent": False,
            "orderExecutionPathPresent": False,
        },
        "dataQuality": {
            "expectedStreams": 11,
            "activeStreams": 11,
            "missingStreams": [],
            "staleStreams": [],
            "silentStreams": ["!forceOrder@arr"],
            "messagesByStream": {"btcusdt@bookTicker": 1000},
            "maxObservedSilenceMsByStream": {"btcusdt@bookTicker": 500.0},
            "reconnections": {"public": 0, "market": 0},
            "depthSequenceGapsBySymbol": {"BTCUSDT": 0},
            "timestampRejected": 0,
            "connectivityObservationSeconds": 100.0,
            "observedUptimePercentByEndpoint": {"public": 100.0, "market": 100.0},
        },
        "eventsByType": {},
    }
    base.update(overrides)
    return base


def _return_feature(symbol="BTCUSDT", price=50000.0, rets=None, tier="CORE"):
    all_none = {tf: None for tf in
                ("1m", "3m", "5m", "15m", "1h", "4h", "24h")}
    if rets:
        all_none.update(rets)
    return {
        "symbol": symbol,
        "current_price": price,
        "source": "markPrice",
        "source_timestamp_ms": T0,
        "sample_age_ms": 5_000,
        "history_span_ms": 600_000,
        "returns": all_none,
        "anchor_ms": {tf: None for tf in all_none},
        "available_tfs": [tf for tf, v in all_none.items() if v is not None],
        "warmup_complete": False,
        "tier": tier,
        "momentum": {"velocity": {"1m": 1e-06},
                     "acceleration": {"1m": None}},
        "ranks": {"velocity_1m": {"rank": 1, "change": 0}},
    }


def _discovery():
    now = int(time.time() * 1000)
    return {
        "generated_at_ms": now,
        "eligible_count": 449,
        "seen_count": 924,
        "filtered_count": 475,
        "core": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "hot_dynamic": ["ORCAUSDT"],
        "hot_full": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ORCAUSDT"],
        "top_n": 10,
        "min_quote_volume_usdt": 1_000_000,
        "tops": {
            "gainers": [
                {"symbol": "ORCAUSDT", "change_24h_pct": 31.5,
                 "price": 2.5, "quote_volume_24h": 5e6},
                {"symbol": "BTCUSDT", "change_24h_pct": 2.5,
                 "price": 50000.0, "quote_volume_24h": 9e8},
            ],
            "losers": [
                {"symbol": "MINAUSDT", "change_24h_pct": -24.0,
                 "price": 0.5, "quote_volume_24h": 3e6},
            ],
            "most_active": [
                {"symbol": "BTCUSDT", "change_24h_pct": 2.5,
                 "price": 50000.0, "quote_volume_24h": 9e8},
                {"symbol": "ETHUSDT", "change_24h_pct": 1.5,
                 "price": 3000.0, "quote_volume_24h": 5e8},
            ],
        },
    }


class _ServerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _temp_store(self)
        self.server = DashboardServer(host="127.0.0.1", port=0,
                                      db_path=self.store.db_path).start()
        self.addCleanup(self.server.stop)
        self.base = f"http://127.0.0.1:{self.server.bound_port()}"

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path,
                                         timeout=15) as resp:
                return (resp.status, resp.read().decode("utf-8"),
                        resp.headers.get("Content-Type", ""))
        except urllib.request.HTTPError as exc:
            return (exc.code, exc.read().decode("utf-8", "replace"),
                    exc.headers.get("Content-Type", ""))


class RoutingTest(_ServerCase):
    def test_movers_200(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        code, body, _ = self._get("/movers")
        self.assertEqual(code, 200)
        self.assertIn("Market table", body)

    def test_symbol_live_200(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features([_return_feature()])
        code, body, _ = self._get("/symbol/BTCUSDT")
        self.assertEqual(code, 200)
        self.assertIn("BTCUSDT", body)

    def test_symbol_discovery_only_200(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_discovery_snapshot(_discovery())
        code, body, _ = self._get("/symbol/ORCAUSDT")
        self.assertEqual(code, 200)
        self.assertIn("ORCAUSDT", body)
        self.assertIn("DISCOVERY ONLY", body)

    def test_symbol_unknown_404(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features([_return_feature()])
        code, _, _ = self._get("/symbol/FOOUSDT")
        self.assertEqual(code, 404)

    def test_symbol_malformed_400(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        for bad in ("/symbol/BTC", "/symbol/BTC%20USDT",
                    "/symbol/%3Cscript%3E"):
            code, _, _ = self._get(bad)
            self.assertEqual(code, 400, bad)

    def test_symbol_case_insensitive(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features([_return_feature()])
        code, _, _ = self._get("/symbol/btcusdt")
        self.assertEqual(code, 200)


class SearchTest(_ServerCase):
    def _seed(self):
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features([_return_feature()])
        self.store.store_discovery_snapshot(_discovery())

    def test_exact_symbol(self) -> None:
        self._seed()
        code, body, _ = self._get("/search?q=ORCAUSDT")
        self.assertEqual(code, 200)
        self.assertIn("ORCAUSDT", body)

    def test_partial_symbol(self) -> None:
        self._seed()
        code, body, _ = self._get("/search?q=ORC")
        self.assertEqual(code, 200)
        self.assertIn("ORCAUSDT", body)

    def test_case_insensitive(self) -> None:
        self._seed()
        code, body, _ = self._get("/search?q=orca")
        self.assertEqual(code, 200)
        self.assertIn("ORCAUSDT", body)

    def test_escaping_injection_safe(self) -> None:
        self._seed()
        evil = urllib.parse.quote("<script>alert(1)</script>")
        code, body, _ = self._get(f"/search?q={evil}")
        self.assertEqual(code, 200)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_search_api(self) -> None:
        self._seed()
        code, body, ctype = self._get("/api/search?q=orc")
        self.assertEqual(code, 200)
        self.assertIn("application/json", ctype)
        payload = json.loads(body)
        syms = [r["symbol"] for r in payload["results"]]
        self.assertIn("ORCAUSDT", syms)


class MoversTest(_ServerCase):
    def _seed(self):
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features([
            _return_feature("BTCUSDT", 50000.0, {"1m": 0.002}),
            _return_feature("ETHUSDT", 3000.0, {"1m": -0.001}),
        ])
        self.store.store_discovery_snapshot(_discovery())

    def test_categories_present(self) -> None:
        self._seed()
        code, body, _ = self._get("/movers")
        self.assertEqual(code, 200)
        for marker in ("Top gainers 24h", "Top losers 24h",
                       "Highest 24h activity", "HOT proposals",
                       "Acceleration leaders", "Volume expansion",
                       "Aggressive-flow leaders"):
            self.assertIn(marker, body)

    def test_tier_labels(self) -> None:
        self._seed()
        _, body, _ = self._get("/movers")
        for tier in ("CORE", "HOT", "DISCOVERY"):
            self.assertIn(tier, body)

    def test_live_vs_discovery_only(self) -> None:
        self._seed()
        _, body, _ = self._get("/movers")
        self.assertIn("DISCOVERY ONLY", body)
        # Subscribed BTC has live capability (LIVE or WARMING), never fake.
        self.assertRegex(body, r"WARMING|LIVE")

    def test_rows_clickable(self) -> None:
        self._seed()
        _, body, _ = self._get("/movers")
        self.assertIn("/symbol/BTCUSDT", body)
        self.assertIn("/symbol/ORCAUSDT", body)


class MoversIntegrityTest(_ServerCase):
    """P1-11A: every movers category must render its OWN source field.

    Regression for the shared-`_v` contamination bug (a symbol present in
    several categories displayed the last-assigned value in every table,
    mixing velocity/acceleration/volume-z/flow scales). Fixture numbers are
    deliberately unique per field so any cross-category leak is visible.
    """

    VEL = 1.1e-6
    ACC = 2.2e-8
    FLOW = 333333
    VOLZ = 4.4
    QVOL = 55555555
    CHG = 6.6

    def _seed(self):
        self.store.store_telemetry_snapshot(_snapshot())
        feat = _return_feature("INTUSDT", 100.0, {"1m": 0.001})
        feat["momentum"] = {"velocity": {"1m": self.VEL},
                            "acceleration": {"1m": self.ACC}}
        self.store.store_return_features([feat])
        self.store.store_flow_features([{
            "symbol": "INTUSDT",
            "horizons": {"1m": {"signed_delta": float(self.FLOW)}},
            "baselines": {"1m": {"z_score": self.VOLZ}},
        }])
        tops_row = {"symbol": "INTUSDT", "change_24h_pct": self.CHG,
                    "price": 100.0, "quote_volume_24h": self.QVOL}
        disc = _discovery()
        disc["core"] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        disc["hot_dynamic"] = ["INTUSDT"]
        disc["hot_full"] = ["INTUSDT"]
        disc["tops"] = {
            "gainers": [tops_row],
            "losers": [{"symbol": "ZZZUSDT", "change_24h_pct": -1.5,
                        "price": 1.0, "quote_volume_24h": 10}],
            "most_active": [tops_row],
        }
        self.store.store_discovery_snapshot(disc)

    def _section(self, body, title):
        for part in body.split("<h2>"):
            if part.startswith(title):
                return part.split("</table>")[0]
        self.fail(f"movers section missing: {title}")

    def test_gainers_shows_24h_pct_not_live_fields(self) -> None:
        self._seed()
        _, body, _ = self._get("/movers")
        sec = self._section(body, "Top gainers 24h (discovery)")
        self.assertIn("INTUSDT", sec)
        self.assertIn(f"{self.CHG:+.2f}%", sec)
        for leak in ("1.1e-06/s", "2.2e-08", "+4.40 z", "+333333.00",
                     str(self.QVOL), "proposed"):
            self.assertNotIn(leak, sec, f"gainers leaked {leak}")

    def test_live_velocity_and_accel_use_own_fields(self) -> None:
        self._seed()
        _, body, _ = self._get("/movers")
        vel = self._section(body, "Fastest positive velocity (live)")
        self.assertIn("INTUSDT", vel)
        self.assertIn(f"{self.VEL:.3g}/s", vel)
        acc = self._section(body, "Acceleration leaders (live)")
        self.assertIn("INTUSDT", acc)
        self.assertIn(f"{self.ACC:.3g}/s", acc)
        # Velocity table must not show the acceleration value and vice versa.
        self.assertNotIn(f"{self.ACC:.3g}/s", vel)
        self.assertNotIn(f"{self.VEL:.3g}/s", acc)

    def test_volume_expansion_and_flow_use_own_fields(self) -> None:
        self._seed()
        _, body, _ = self._get("/movers")
        volx = self._section(body, "Volume expansion (live z-score)")
        self.assertIn("INTUSDT", volx)
        self.assertIn(f"{self.VOLZ:+.2f} z", volx)
        flow = self._section(body, "Aggressive-flow leaders (live)")
        self.assertIn("INTUSDT", flow)
        self.assertIn(f"{float(self.FLOW):+.2f}", flow)
        self.assertNotIn(f"{float(self.FLOW):+.2f}", volx)
        self.assertNotIn(f"{self.VOLZ:+.2f} z", flow)

    def test_hot_and_activity_values(self) -> None:
        self._seed()
        _, body, _ = self._get("/movers")
        hot = self._section(body, "HOT proposals")
        self.assertIn("INTUSDT", hot)
        self.assertIn("proposed", hot)
        active = self._section(body,
                               "Highest 24h activity / quote volume (discovery)")
        self.assertIn("INTUSDT", active)
        self.assertIn(str(self.QVOL), active)
        self.assertNotIn(f"{self.CHG:+.2f}%", active)

    def test_velocity_sort_key_unchanged(self) -> None:
        self._seed()
        faster = _return_feature("SRTUSDT", 50.0, {"1m": 0.002})
        faster["momentum"] = {"velocity": {"1m": 9.9e-6},
                              "acceleration": {"1m": None}}
        self.store.store_return_features([faster])
        _, body, _ = self._get("/movers")
        vel = self._section(body, "Fastest positive velocity (live)")
        self.assertLess(vel.index("SRTUSDT"), vel.index("INTUSDT"))


class TokenDetailTest(_ServerCase):
    def _seed_live(self):
        from microstructure_probe.flow import FlowEngine
        from microstructure_probe.book import BookEngine
        from microstructure_probe.open_interest import OpenInterestTracker
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features(
            [_return_feature("BTCUSDT", 50000.0,
                             {"1m": 0.002, "3m": 0.004, "5m": 0.006})])
        self.store.store_discovery_snapshot(_discovery())
        eng = FlowEngine(symbols=("BTCUSDT",))
        eng.ingest("BTCUSDT", T0, 50000.0, 1.0, False)
        eng.ingest("BTCUSDT", T0 + 1000, 50000.0, 0.5, True)
        self.store.store_flow_features(eng.snapshot_all(T0 + 1000))
        book = BookEngine(symbols=("BTCUSDT",))
        book.ingest("BTCUSDT", T0, 100, 99,
                    [("49999", "1.0")], [("50001", "1.0")])
        self.store.store_book_features(book.snapshot_all(T0))
        tracker = OpenInterestTracker(symbols=("BTCUSDT",))
        tracker.ingest("BTCUSDT", T0, T0, 90000.0)
        tracker.ingest("BTCUSDT", T0 + 60_000, T0 + 60_000, 90100.0)
        snaps = tracker.snapshot_all(T0 + 60_000, {"BTCUSDT": 0.001})
        self.store.store_oi_features(snaps)
        self.store.store_structure_features([{
            "symbol": "BTCUSDT", "subscribed": True,
            "as_of_ms": T0, "reference_price": 50000.0,
            "reference_source": "markPrice", "price_age_ms": 500,
            "vwap": {"1m": {"vwap": 49999.0, "displacement_bps": 0.2,
                            "trades": 10, "notional": 500000.0,
                            "warmup_complete": True}},
            "volatility": {"1m": {"realized_vol": 0.0012, "returns": 6,
                                  "warmed": True},
                           "5m": {"realized_vol": None, "returns": 0,
                                  "warmed": False}},
            "ranges": {"5m": {"high": 50100.0, "low": 49900.0,
                              "range_position": 0.5,
                              "expansion_ratio": 1.2}},
            "structure": {"higher_high": True, "lower_high": False,
                          "higher_low": None, "lower_low": None,
                          "last_swing_high": 50100.0,
                          "last_swing_low": 49900.0,
                          "breakout_state": "INSIDE_PRIOR_RANGE"},
        }])
        now_ms = int(time.time() * 1000)
        self.store.store_price_samples(
            [(  # 30 x 10s buckets ending now
                "BTCUSDT", now_ms - (29 - i) * 10_000,
                50000.0 + i) for i in range(30)])

    def test_core_live_panels(self) -> None:
        self._seed_live()
        code, body, _ = self._get("/symbol/BTCUSDT")
        self.assertEqual(code, 200)
        for marker in ("Momentum", "Trade flow", "Order book",
                       "Open interest", "VWAP / volatility / structure",
                       "Price chart"):
            self.assertIn(marker, body)

    def test_discovery_only_honesty(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_discovery_snapshot(_discovery())
        _, body, _ = self._get("/symbol/ORCAUSDT")
        self.assertIn("DISCOVERY ONLY", body)
        self.assertIn("NO LIVE DEEP FEATURES", body)
        for fake in ("Trade flow (aggressor", "Order book (visible",
                     "Open interest (descriptive",
                     "VWAP / volatility / structure (descriptive"):
            self.assertNotIn(fake, body)

    def test_no_fake_live_metrics(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features([_return_feature()])
        self.store.store_discovery_snapshot(_discovery())
        # MINAUSDT is discovery-only: its page must not show flow/book/OI.
        _, body, _ = self._get("/symbol/MINAUSDT")
        self.assertIn("DISCOVERY ONLY", body)
        self.assertNotIn("signed delta", body)

    def test_unknown_warming_rendering(self) -> None:
        self._seed_live()
        _, body, _ = self._get("/symbol/BTCUSDT")
        # 5m RV is None -> UNKNOWN/WARMING marker, never blank-zero claim.
        self.assertRegex(body, r"UNKNOWN|WARMING|—")

    def test_integrity_copy(self) -> None:
        self._seed_live()
        _, body, _ = self._get("/symbol/BTCUSDT")
        self.assertRegex(body, r"HEALTHY|DEGRADED")
        self.assertNotIn("OK (1 gaps)", body)


class ChartApiTest(_ServerCase):
    def _seed(self, n=30):
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features([_return_feature()])
        now_ms = int(time.time() * 1000)
        self.store.store_price_samples(
            [("BTCUSDT", now_ms - (n - 1 - i) * 10_000, 50000.0 + i)
             for i in range(n)])

    def test_valid_ranges(self) -> None:
        self._seed()
        for rng in ("5m", "15m", "1h", "4h", "24h"):
            code, body, ctype = self._get(
                f"/api/symbol/BTCUSDT/price?range={rng}")
            self.assertEqual(code, 200, rng)
            self.assertIn("application/json", ctype)
            payload = json.loads(body)
            self.assertEqual(payload["symbol"], "BTCUSDT")
            self.assertEqual(payload["range"], rng)
            self.assertIn("points", payload)

    def test_bounded_output(self) -> None:
        self._seed(n=1500)
        code, body, _ = self._get("/api/symbol/BTCUSDT/price?range=24h")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertLessEqual(len(payload["points"]), 1000)
        self.assertLessEqual(payload["points_returned"], 1000)

    def test_ordering_and_no_future(self) -> None:
        self._seed()
        now_ms = int(time.time() * 1000)
        self.store.store_price_samples(
            [("BTCUSDT", now_ms + 600_000, 999999.0)])
        _, body, _ = self._get("/api/symbol/BTCUSDT/price?range=24h")
        payload = json.loads(body)
        ts = [p["timestamp"] for p in payload["points"]]
        self.assertEqual(ts, sorted(ts))
        self.assertTrue(all(t <= now_ms + 5_000 for t in ts))
        self.assertNotIn(999999.0, [p["price"] for p in payload["points"]])

    def test_insufficient_history(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features([_return_feature()])
        code, body, _ = self._get("/api/symbol/BTCUSDT/price?range=5m")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["points"], [])

    def test_invalid_range_400(self) -> None:
        self._seed()
        code, _, _ = self._get("/api/symbol/BTCUSDT/price?range=99h")
        self.assertEqual(code, 400)

    def test_invalid_symbol_400_and_unknown_404(self) -> None:
        self._seed()
        code, _, _ = self._get("/api/symbol/BTC/price?range=1h")
        self.assertEqual(code, 400)
        code, _, _ = self._get("/api/symbol/FOOUSDT/price?range=1h")
        self.assertEqual(code, 404)

    def test_csv_export(self) -> None:
        self._seed()
        code, body, ctype = self._get(
            "/api/symbol/BTCUSDT/price.csv?range=1h")
        self.assertEqual(code, 200)
        self.assertIn("text/csv", ctype)
        lines = body.strip().splitlines()
        self.assertEqual(lines[0], "timestamp,price")
        self.assertGreater(len(lines), 1)
        for line in lines[1:]:
            ts, px = line.split(",")
            int(ts)
            float(px)


class UiRegressionTest(_ServerCase):
    def _seed(self):
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features([_return_feature()])
        self.store.store_discovery_snapshot(_discovery())

    def test_no_trading_controls(self) -> None:
        self._seed()
        for path in ("/overview", "/movers", "/system",
                     "/symbol/BTCUSDT", "/search?q=ORC"):
            code, body, _ = self._get(path)
            self.assertEqual(code, 200, path)
            low = body.lower()
            self.assertNotIn("<button", low, path)
            self.assertNotIn("place_order", low, path)

    def test_no_forbidden_signal_language(self) -> None:
        self._seed()
        for path in ("/overview", "/movers", "/symbol/BTCUSDT"):
            _, body, _ = self._get(path)
            scrubbed = re.sub(r"aggr(essive)?\s+(buy|sell)", "",
                              body, flags=re.IGNORECASE)
            for word in (r"\bBUY\b", r"\bSELL\b", r"\bLONG\b",
                         r"\bSHORT\b", r"\bENTRY\b", r"\bEXIT\b",
                         r"STRONG BUY", r"STRONG SELL", r"TRADE NOW"):
                self.assertIsNone(re.search(word, scrubbed, re.IGNORECASE),
                                  f"{path}: {word}")

    def test_unicode_symbol(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        disc = _discovery()
        disc["tops"]["gainers"].append(
            {"symbol": "龙虾USDT", "change_24h_pct": 35.0,
             "price": 1.0, "quote_volume_24h": 2e6})
        self.store.store_discovery_snapshot(disc)
        _, body, _ = self._get("/movers")
        self.assertIn("龙虾USDT", body)
        code, _, _ = self._get("/symbol/" + urllib.parse.quote("龙虾USDT"))
        self.assertEqual(code, 200)

    def test_html_escaping(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        evil = dict(_return_feature())
        evil["symbol"] = "X<script>USDT"
        self.store.store_return_features([evil])
        _, body, _ = self._get("/overview")
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_health_separation(self) -> None:
        self._seed()
        code, body, _ = self._get("/api/health")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertIn("server", payload)
        self.assertIn("feed", payload)

    def test_forceorder_semantics(self) -> None:
        from microstructure_probe.probe import MarketProbe
        from test_detectors import test_config
        probe = MarketProbe(test_config(), wall_clock_ms=lambda: 11_000.0,
                            monotonic=lambda: 11.0)
        probe.stats.last_seen_monotonic["!forceOrder@arr"] = 10.0
        probe.stats.first_seen_monotonic["!forceOrder@arr"] = 10.0
        summary = probe.build_summary(final=False)
        dq = summary["dataQuality"]
        self.assertNotIn("!forceOrder@arr", dq["missingStreams"])
        self.assertNotIn("!forceOrder@arr", dq["staleStreams"])

    def test_dashboard_version(self) -> None:
        self.assertEqual(dashboard.DASHBOARD_VERSION, "0.8.0")


class FeatureApiRegressionTest(_ServerCase):
    def test_p104_p108_apis_intact(self) -> None:
        self.store.store_telemetry_snapshot(_snapshot())
        self.store.store_return_features([_return_feature()])
        for path in ("/api/features/returns", "/api/features/momentum",
                     "/api/discovery"):
            code, _, _ = self._get(path)
            self.assertIn(code, (200, 404), path)
        # Seeded ones must be 200.
        self.store.store_discovery_snapshot(_discovery())
        for path in ("/api/features/returns", "/api/features/momentum",
                     "/api/discovery", "/api/health", "/api/snapshot"):
            code, _, _ = self._get(path)
            self.assertEqual(code, 200, path)


if __name__ == "__main__":
    unittest.main()
