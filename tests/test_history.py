"""P1-11B historical foundation tests (mocked HTTP; no live network).

Covers: pagination, duplicate-boundary behavior, resume, idempotent
upserts, listing-aware first bar, gaps, malformed OHLC, partial-candle
exclusion, provenance separation (mark klines carry no volume), rate-limit
and backoff policy, schema, bounded-pilot safety, and the observe-only /
no-signal guards.
"""

import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import history as H
from microstructure_probe.history_client import HistoryClient, RateLimitExceeded
from microstructure_probe.history_store import HistoryStore, SCHEMA_VERSION

T0 = 1_700_000_000_000
STEP = 60_000


def _bar(open_time, o="100.0", h="101.0", low="99.0", c="100.5",
         base="10.0", quote="1000.0", trades=50, tb_base="5.0",
         tb_quote="500.0"):
    return [open_time, o, h, low, c, base, open_time + STEP - 1, quote,
            trades, tb_base, tb_quote, "0"]


def _mark_bar(open_time, o="100.0", h="101.0", low="99.0", c="100.5"):
    return [open_time, o, h, low, c, "0", open_time + STEP - 1, "0",
            7, "0", "0", "0"]


class _FakeResp:
    def __init__(self, payload, headers=None):
        self._body = json.dumps(payload).encode()
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _temp_store(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="hist_test_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    store = HistoryStore(tmp / "historical.db")
    store.init_db()
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


class SchemaTest(unittest.TestCase):
    def test_schema_version_and_tables(self) -> None:
        store = _temp_store(self)
        self.assertEqual(store.schema_version(), SCHEMA_VERSION)
        self.assertEqual(store.coverage_summary(), [])

    def test_live_db_rejected(self) -> None:
        with self.assertRaises(ValueError):
            HistoryStore(Path("data") / "microprobe.db")

    def test_mark_table_has_no_volume_columns(self) -> None:
        store = _temp_store(self)
        import sqlite3
        con = sqlite3.connect(str(store.db_path))
        try:
            cols = [r[1] for r in con.execute(
                "PRAGMA table_info(historical_mark_klines)")]
        finally:
            con.close()
        for col in cols:
            self.assertNotIn("volume", col.lower())

    def test_oi_round_trip_preserves_served_fields(self) -> None:
        store = _temp_store(self)
        rows = [{"ts": T0, "sum_oi": "96359.70200000",
                 "sum_oi_value": "8029543190.11928000"}]
        self.assertEqual(store.upsert_oi("BTCUSDT", "5m", rows), 1)
        self.assertEqual(store.upsert_oi("BTCUSDT", "5m", rows), 1)
        loaded = store.load_oi("BTCUSDT", "5m")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["sum_oi"], "96359.70200000")

    def test_oi_pagination_dedupes_boundary(self) -> None:
        client = HistoryClient(sleep=lambda s: None)

        def fake_oi(symbol, period, start, end, limit=500):
            if start <= T0:
                return ([{"symbol": symbol, "timestamp": T0,
                           "sumOpenInterest": "1", "sumOpenInterestValue": "2"},
                         {"symbol": symbol, "timestamp": T0 + 300_000,
                           "sumOpenInterest": "1", "sumOpenInterestValue": "2"}],
                        {})
            return ([{"symbol": symbol, "timestamp": T0 + 600_000,
                       "sumOpenInterest": "1",
                       "sumOpenInterestValue": "2"}], {})

        client.oi_hist = fake_oi
        rows, pages = client.paginate_oi("BTCUSDT", "5m", T0, T0 + 600_000,
                                         limit=2, max_pages=5)
        self.assertEqual([r["timestamp"] for r in rows],
                         [T0, T0 + 300_000, T0 + 600_000])
        self.assertEqual(pages, 2)


class PaginationTest(unittest.TestCase):
    def _client(self, pages):
        client = HistoryClient(sleep=lambda s: None)
        calls = []

        def fake_get(path, params, weight):
            calls.append(dict(params))
            start = int(params["startTime"])
            return [b for (s, b) in pages if s == start][0], {}

        client.get = fake_get
        client.calls = calls
        return client

    def test_forward_pagination_no_boundary_duplicates(self) -> None:
        p1 = [_bar(T0), _bar(T0 + STEP)]
        p2 = [_bar(T0 + 2 * STEP)]
        client = self._client([(T0, p1), (T0 + 2 * STEP, p2)])
        rows, info = client.paginate_klines("BTCUSDT", "1m", T0,
                                            T0 + 3 * STEP, limit=2)
        self.assertEqual([r[0] for r in rows],
                         [T0, T0 + STEP, T0 + 2 * STEP])
        self.assertEqual(info["pages"], 2)
        self.assertEqual(info["skipped_ranges"], [])

    def test_page_overlap_raises(self) -> None:
        p1 = [_bar(T0), _bar(T0 + STEP)]
        p2 = [_bar(T0 + STEP), _bar(T0 + 2 * STEP)]  # rewinds into page 1
        client = self._client([(T0, p1), (T0 + 2 * STEP, p2)])
        with self.assertRaises(ValueError):
            client.paginate_klines("BTCUSDT", "1m", T0, T0 + 3 * STEP,
                                   limit=2)

    def test_max_pages_bounds_requests(self) -> None:
        full = [_bar(T0 + i * STEP) for i in range(10)]
        client = self._client([(T0, full)])
        rows, info = client.paginate_klines("BTCUSDT", "1m", T0,
                                            T0 + 9 * STEP, limit=2,
                                            max_pages=1)
        self.assertEqual(info["pages"], 1)
        self.assertEqual(len(client.calls), 1)

    def test_earliest_bar_probe(self) -> None:
        client = HistoryClient(sleep=lambda s: None)
        client.get = lambda p, q, w: ([_bar(1_500_000_000_000)], {})
        bar = client.earliest_bar("BTCUSDT", "1m")
        self.assertEqual(bar[0], 1_500_000_000_000)

    def test_earliest_bar_none_when_unavailable(self) -> None:
        client = HistoryClient(sleep=lambda s: None)
        client.get = lambda p, q, w: ([], {})
        self.assertIsNone(client.earliest_bar("NOPEUSDT", "1m"))


class RateLimitTest(unittest.TestCase):
    def test_429_honors_retry_after_then_succeeds(self) -> None:
        sleeps = []
        state = {"n": 0}

        def opener(req, timeout=None):
            state["n"] += 1
            if state["n"] == 1:
                err = urllib.error.HTTPError(
                    req.full_url, 429, "slow down", {"Retry-After": "2"},
                    io.BytesIO(b"{}"))
                raise err
            return _FakeResp([1])

        client = HistoryClient(sleep=sleeps.append, opener=opener,
                               max_weight_per_minute=10_000)
        payload, _ = client.get("/fapi/v1/klines", {"symbol": "X"}, 1)
        self.assertEqual(payload, [1])
        self.assertEqual(sleeps, [2.0])
        self.assertEqual(client.stats.retries, 1)

    def test_429_budget_exhaustion_aborts(self) -> None:
        def opener(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 429, "slow",
                                         {"Retry-After": "1"},
                                         io.BytesIO(b"{}"))

        client = HistoryClient(sleep=lambda s: None, opener=opener,
                               max_weight_per_minute=10_000, max_429=1)
        with self.assertRaises(RateLimitExceeded):
            client.get("/fapi/v1/klines", {"symbol": "X"}, 1)

    def test_418_aborts_immediately(self) -> None:
        def opener(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 418, "ban", {},
                                         io.BytesIO(b"{}"))

        client = HistoryClient(sleep=lambda s: None, opener=opener,
                               max_weight_per_minute=10_000)
        with self.assertRaises(RateLimitExceeded):
            client.get("/fapi/v1/klines", {"symbol": "X"}, 1)

    def test_5xx_retried_within_budget(self) -> None:
        state = {"n": 0}

        def opener(req, timeout=None):
            state["n"] += 1
            if state["n"] < 3:
                raise urllib.error.HTTPError(req.full_url, 502, "bad", {},
                                             io.BytesIO(b"{}"))
            return _FakeResp({"ok": True})

        client = HistoryClient(sleep=lambda s: None, opener=opener,
                               max_weight_per_minute=10_000, max_retries=5)
        payload, _ = client.get("/fapi/v1/klines", {"symbol": "X"}, 1)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(client.stats.retries, 2)


class ValidationTest(unittest.TestCase):
    NOW = T0 + 10 * STEP

    def test_gap_detection(self) -> None:
        rows = [H.normalize_kline(_bar(T0 + i * STEP))
                for i in (0, 1, 2, 5, 6)]
        rep = H.validate_bars(rows, "1m", now_ms=self.NOW)
        self.assertEqual(rep["duplicates"], 0)
        self.assertEqual(len(rep["missing_ranges"]), 1)
        gap = rep["missing_ranges"][0]
        self.assertEqual(gap["missing_from"], T0 + 3 * STEP)
        self.assertEqual(gap["expected_count"], 2)
        self.assertEqual(rep["actual_bars"], 5)

    def test_duplicates_counted(self) -> None:
        rows = [H.normalize_kline(_bar(T0)), H.normalize_kline(_bar(T0)),
                H.normalize_kline(_bar(T0 + STEP))]
        rep = H.validate_bars(rows, "1m", now_ms=self.NOW)
        self.assertEqual(rep["duplicates"], 1)

    def test_malformed_ohlc_flagged(self) -> None:
        rows = [
            H.normalize_kline(_bar(T0, h="98.0")),          # high<low
            H.normalize_kline(_bar(T0 + STEP, o="200.0")),   # o outside h/l
            H.normalize_kline(_bar(T0 + 2 * STEP, o="-1")),  # non-positive
        ]
        rep = H.validate_bars(rows, "1m", now_ms=self.NOW)
        self.assertEqual(len(rep["malformed"]), 3)
        kinds = {m["problems"][0] for m in rep["malformed"]}
        self.assertEqual(kinds, {"high<low", "open-close-outside-high-low",
                                "non-positive-price"})

    def test_partial_final_candle_excluded(self) -> None:
        rows = [H.normalize_kline(_bar(T0)),
                H.normalize_kline(_bar(self.NOW - STEP // 2))]
        rep = H.validate_bars(rows, "1m", now_ms=self.NOW)
        self.assertEqual(rep["partial_excluded"], 1)
        self.assertEqual(rep["actual_bars"], 1)

    def test_mark_rows_carry_no_volume(self) -> None:
        row = H.normalize_mark_kline(_mark_bar(T0))
        self.assertNotIn("base_volume", row)
        self.assertNotIn("quote_volume", row)


class IngestTest(unittest.TestCase):
    def test_idempotent_upsert(self) -> None:
        store = _temp_store(self)
        rows = [H.normalize_kline(_bar(T0)), H.normalize_kline(_bar(T0 + STEP))]
        self.assertEqual(store.upsert_klines("BTCUSDT", "1m", rows), 2)
        self.assertEqual(store.upsert_klines("BTCUSDT", "1m", rows), 2)
        self.assertEqual(len(store.load_bars("BTCUSDT", "1m", "klines")), 2)

    def test_resume_continues_from_coverage(self) -> None:
        store = _temp_store(self)
        store.upsert_klines("BTCUSDT", "1m",
                            [H.normalize_kline(_bar(T0))])
        store.record_coverage("BTCUSDT", "1m", "klines", T0 - STEP, T0,
                              T0, T0, 1, 1)
        client = HistoryClient(sleep=lambda s: None)
        seen = {}

        def fake_paginate(symbol, interval, start, end, source="klines",
                          limit=1000, max_pages=200):
            seen["start"] = start
            return ([_bar(start)], {"pages": 1, "skipped_ranges": []})

        client.paginate_klines = fake_paginate
        client.earliest_bar = lambda s, i, source="klines": _bar(T0 - STEP)
        rep = H.ingest_series(client, store, "BTCUSDT", "1m", "klines",
                              days_back=30, max_requests=10, run_id=1,
                              now_ms=T0 + 10 * STEP)
        self.assertEqual(seen["start"], T0 + STEP)
        self.assertEqual(rep["resume_from"], T0 + STEP)

    def test_listing_aware_clamps_to_first_available(self) -> None:
        store = _temp_store(self)
        client = HistoryClient(sleep=lambda s: None)
        client.earliest_bar = lambda s, i, source="klines": _bar(T0)
        client.paginate_klines = lambda *a, **k: ([], {"pages": 1,
                                                       "skipped_ranges": []})
        rep = H.ingest_series(client, store, "BTCUSDT", "1m", "klines",
                              days_back=3650, max_requests=10, run_id=1,
                              now_ms=T0 + 10 * STEP)
        self.assertEqual(rep["actual_start"], T0)
        self.assertEqual(rep["first_available_open_time"], T0)

    def test_no_data_symbol_reported(self) -> None:
        store = _temp_store(self)
        client = HistoryClient(sleep=lambda s: None)
        client.earliest_bar = lambda s, i, source="klines": None
        rep = H.ingest_series(client, store, "BTCUSDT", "1m", "klines",
                              days_back=7, max_requests=10, run_id=1,
                              now_ms=T0 + 10 * STEP)
        self.assertEqual(rep["status"], "no-data")


class SafetyTest(unittest.TestCase):
    def test_cli_defaults_are_bounded(self) -> None:
        parser = H.build_parser()
        args = parser.parse_args(["fetch", "--symbol", "BTCUSDT"])
        self.assertEqual(args.days, H.DEFAULT_DAYS)
        self.assertEqual(args.max_requests, H.DEFAULT_MAX_REQUESTS)
        self.assertLessEqual(args.max_requests, 25)

    def test_no_bulk_mode_exists(self) -> None:
        parser = H.build_parser()
        for action in parser._actions:
            self.assertNotIn(getattr(action, "dest", ""), ("all", "universe"))

    def test_no_private_api_paths(self) -> None:
        import microstructure_probe.history_client as hc
        import microstructure_probe.history as hh
        src = open(hc.__file__).read() + open(hh.__file__).read()
        for token in ("apiKey", "api_secret", "signature", "X-MBX-APIKEY",
                      "leverage", "placeOrder", "/fapi/v1/order"):
            self.assertNotIn(token, src)

    def test_no_signal_or_trading_language(self) -> None:
        import microstructure_probe.history as hh
        src = open(hh.__file__).read().lower()
        for token in ("long signal", "short signal", "entry zone",
                      "take-profit", "stop-loss", "place order"):
            self.assertNotIn(token, src)


class HistoryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="histapi_"))
        self.addCleanup(lambda: _rmtree(tmp))
        hist = HistoryStore(tmp / "historical.db")
        hist.init_db()
        hist.upsert_klines("BTCUSDT", "1h",
                           [H.normalize_kline(_bar(T0)),
                            H.normalize_kline(_bar(T0 + 3_600_000))])
        hist.record_coverage("BTCUSDT", "1h", "klines", T0, T0, T0,
                             T0 + 3_600_000, 2, 2)
        os.environ["MICROPROBE_HISTORICAL_DB"] = str(tmp / "historical.db")
        self.addCleanup(os.environ.pop, "MICROPROBE_HISTORICAL_DB", None)
        from microstructure_probe.dashboard import DashboardServer
        from microstructure_probe.persistence import PersistenceStore
        live = PersistenceStore(db_path=tmp / "live.db")
        live.init_db()
        live.store_return_features([{
            "symbol": "BTCUSDT", "current_price": 50000.0,
            "returns": {"1m": 0.001}, "momentum": {"velocity": {},
                                                  "acceleration": {}},
            "tier": "CORE"}])
        live.close()
        self.server = DashboardServer(host="127.0.0.1", port=0,
                                      db_path=tmp / "live.db").start()
        self.addCleanup(self.server.stop)
        self.base = f"http://127.0.0.1:{self.server.bound_port()}"

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path,
                                         timeout=15) as resp:
                return (resp.status, resp.read().decode("utf-8"))
        except urllib.request.HTTPError as exc:
            return (exc.code, exc.read().decode("utf-8", "replace"))

    def test_status_lists_coverage(self) -> None:
        code, body = self._get("/api/history/status")
        self.assertEqual(code, 200)
        payload = json.loads(body)
        syms = [(s["symbol"], s["interval"], s["source"])
                for s in payload["series"]]
        self.assertIn(("BTCUSDT", "1h", "klines"), syms)

    def test_symbol_coverage(self) -> None:
        code, body = self._get("/api/history/BTCUSDT")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["symbol"], "BTCUSDT")

    def test_unknown_symbol_404_malformed_400(self) -> None:
        code, _ = self._get("/api/history/FOOUSDT")
        self.assertEqual(code, 404)
        code, _ = self._get("/api/history/BTC")
        self.assertEqual(code, 400)

    def test_token_page_shows_coverage_card(self) -> None:
        code, body = self._get("/symbol/BTCUSDT")
        self.assertEqual(code, 200)
        self.assertIn("Historical coverage", body)
        self.assertIn("1h klines", body)


if __name__ == "__main__":
    unittest.main()
