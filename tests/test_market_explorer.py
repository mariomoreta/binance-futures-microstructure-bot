"""Pruebas del explorador de mercado (catalogo + historico bajo demanda).

Sin red: el cliente REST se inyecta como fake y las bases son temporales.
Cubre elegibilidad de contratos, cache con TTL, merge canonico+cache, orden y
dedupe por tiempo de apertura, plan de bloques anteriores, presupuesto de
peticiones, politica 429/418, vela provisional, ausencia de volumen en
mark_klines, cobertura (huecos vs ausencia vs fin de historico), validacion de
entradas, aislamiento de la cache y el CLI JSON.
"""

from __future__ import annotations

import io
import json
import contextlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from microstructure_probe.history_client import (  # noqa: E402
    RequestStats,
    RateLimitExceeded,
)
from microstructure_probe.market_cache import MarketCache  # noqa: E402
from microstructure_probe import market_explorer as MX  # noqa: E402

T0 = 1_700_000_000_000
STEP_1H = 3_600_000


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


def _bar(open_time: int, price: float = 100.0, step: int = STEP_1H):
    return [open_time, f"{price}", f"{price + 1}", f"{price - 1}",
            f"{price + 0.5}", "10.0", open_time + step - 1, "1000.0", 50,
            "5.0", "500.0", "0"]


def _cache_bar(open_time: int, price: float = 100.0, step: int = STEP_1H,
               fetched_at: int = T0):
    return {
        "open_time": open_time, "open": f"{price}", "high": f"{price + 1}",
        "low": f"{price - 1}", "close": f"{price + 0.5}", "base_volume": "10.0",
        "quote_volume": "1000.0", "trade_count": 50,
        "close_time": open_time + step - 1, "fetched_at": fetched_at,
    }


class _FakeClient:
    """Cliente REST fake: registra peticiones, sin red."""

    def __init__(self, payload_bars=None, exchange=None, raises=None):
        self.stats = RequestStats()
        self._bars = payload_bars or []
        self._exchange = exchange
        self._raises = raises
        self.calls = []

    def exchange_info(self, symbol=None):
        self.stats.requests += 1
        if self._raises is not None:
            raise self._raises
        return self._exchange, {}

    def paginate_klines(self, symbol, interval, start_ms, end_ms,
                        source="klines", limit=1000, max_pages=200):
        self.calls.append((symbol, interval, start_ms, end_ms, source, max_pages))
        if self._raises is not None:
            self.stats.requests += 1
            raise self._raises
        self.stats.requests += 1
        rows = [b for b in self._bars if start_ms <= b[0] <= end_ms]
        return rows, {"pages": 1 if rows else 0, "skipped_ranges": []}

    def earliest_bar(self, symbol, interval, source="klines"):
        self.stats.requests += 1
        return self._bars[0] if self._bars else None


def _exchange_payload():
    return {
        "symbols": [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
             "marginAsset": "USDT", "contractType": "PERPETUAL",
             "status": "TRADING", "onboardDate": 1500000000000,
             "pricePrecision": 2,
             "filters": [{"filterType": "PRICE_FILTER",
                          "tickSize": "0.10"}]},
            {"symbol": "ETHUSDT_250627", "baseAsset": "ETH",
             "quoteAsset": "USDT", "contractType": "CURRENT_QUARTER",
             "status": "TRADING", "pricePrecision": 2, "filters": []},
            {"symbol": "OLDUSDT", "baseAsset": "OLD", "quoteAsset": "USDT",
             "contractType": "PERPETUAL", "status": "SETTLING",
             "pricePrecision": 4, "filters": []},
            {"symbol": "BTCEUR", "baseAsset": "BTC", "quoteAsset": "EUR",
             "contractType": "PERPETUAL", "status": "TRADING",
             "pricePrecision": 2, "filters": []},
            {"symbol": "NMRUSDT", "baseAsset": "NMR", "quoteAsset": "USDT",
             "contractType": "PERPETUAL", "status": "TRADING",
             "pricePrecision": 3, "filters": []},
        ]
    }


class CacheIsolationTest(unittest.TestCase):
    def test_cache_refuses_canonical_paths(self) -> None:
        for bad in ("data/microprobe.db", "data/historical/historical.db"):
            with self.assertRaises(ValueError):
                MarketCache(Path(bad))


class CatalogEntryTest(unittest.TestCase):
    def test_eligibility_is_explicit_and_never_silent(self) -> None:
        payload = _exchange_payload()
        rows = [MX.catalog_entry(e, T0) for e in payload["symbols"]]
        by_symbol = {r["symbol"]: r for r in rows if r}
        self.assertTrue(by_symbol["BTCUSDT"]["eligible"])
        self.assertEqual(by_symbol["BTCUSDT"]["tick_size"], "0.10")
        self.assertEqual(by_symbol["BTCUSDT"]["onboard_ms"], 1500000000000)
        self.assertFalse(by_symbol["ETHUSDT_250627"]["eligible"])
        self.assertIn("contract_type=CURRENT_QUARTER",
                      by_symbol["ETHUSDT_250627"]["exclusion_reasons"])
        self.assertIn("status=SETTLING",
                      by_symbol["OLDUSDT"]["exclusion_reasons"])
        self.assertIn("quote_asset=EUR", by_symbol["BTCEUR"]["exclusion_reasons"])

    def test_entry_without_symbol_is_dropped(self) -> None:
        self.assertIsNone(MX.catalog_entry({"baseAsset": "X"}, T0))


class CatalogCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mkt_cache_"))
        self.addCleanup(lambda: _rmtree(self.tmp))
        self.cache = MarketCache(self.tmp / "cache.db")
        self.cache.init_db()

    def test_refresh_then_fresh_short_circuit(self) -> None:
        client = _FakeClient(exchange=_exchange_payload())
        first = MX.refresh_catalog(self.cache, client, T0)
        self.assertTrue(first["refreshed"])
        self.assertEqual(first["entries"], 5)
        self.assertEqual(client.stats.requests, 1)
        again = MX.refresh_catalog(self.cache, client, T0 + 60_000)
        self.assertFalse(again["refreshed"])
        self.assertEqual(again["reason"], "FRESH_CACHE")
        self.assertEqual(client.stats.requests, 1)
        forced = MX.refresh_catalog(self.cache, client, T0 + 60_000, force=True)
        self.assertTrue(forced["refreshed"])
        self.assertEqual(client.stats.requests, 2)

    def test_expired_ttl_refreshes(self) -> None:
        client = _FakeClient(exchange=_exchange_payload())
        MX.refresh_catalog(self.cache, client, T0)
        later = T0 + MX.CATALOG_TTL_MS + 1000
        out = MX.refresh_catalog(self.cache, client, later)
        self.assertTrue(out["refreshed"])
        self.assertEqual(out["reason"], "REFRESHED")

    def test_forced_refresh_is_not_reported_stale(self) -> None:
        # Regresion: la antiguedad se recalculaba antes del refresco y el
        # catalogo recien pedido se anunciaba como desactualizado.
        client = _FakeClient(exchange=_exchange_payload())
        out = MX.catalog_payload(self.cache, client, limit=5, refresh=True, now_ms=T0)
        self.assertTrue(out["refresh"]["refreshed"])
        self.assertFalse(out["catalog"]["stale"])
        self.assertEqual(out["catalog"]["age_ms"], 0)
        self.assertEqual(out["catalog"]["entries"], 5)
        again = MX.catalog_payload(self.cache, client, limit=5, now_ms=T0 + 60_000)
        self.assertEqual(again["refresh"]["requests"], 0)
        self.assertFalse(again["catalog"]["stale"])
        self.assertEqual(client.stats.requests, 1)

    def test_refresh_failure_keeps_previous_rows(self) -> None:
        client = _FakeClient(exchange=_exchange_payload())
        MX.refresh_catalog(self.cache, client, T0)
        failing = _FakeClient(raises=RuntimeError("boom"))
        out = MX.refresh_catalog(self.cache, failing, T0 + 20 * 60 * 60 * 1000)
        self.assertFalse(out["refreshed"])
        self.assertEqual(out["reason"], "REFRESH_FAILED")
        self.assertEqual(self.cache.catalog_count(), 5)

    def test_catalog_diff_records_listing_events(self) -> None:
        client = _FakeClient(exchange=_exchange_payload())
        MX.refresh_catalog(self.cache, client, T0)
        second = {"symbols": [e for e in _exchange_payload()["symbols"]
                              if e["symbol"] != "NMRUSDT"]}
        MX.refresh_catalog(self.cache, _FakeClient(exchange=second),
                           T0 + 10_000_000, force=True)
        con = self.cache._con()  # noqa: SLF001
        try:
            events = [dict(r) for r in con.execute(
                "SELECT symbol, kind FROM contract_events").fetchall()]
        finally:
            con.close()
        self.assertIn({"symbol": "NMRUSDT", "kind": "not_listed"}, events)

    def test_diff_compares_the_whole_catalog_not_a_capped_page(self) -> None:
        # read_catalog limita a 500 (API de busqueda). Con 640 contratos, el
        # diff debe usar el snapshot completo: si no, las 140 filas fuera de la
        # pagina se reportarian como "altas" inexistentes.
        symbols = [
            {"symbol": f"S{i:04d}USDT", "baseAsset": f"S{i:04d}",
             "quoteAsset": "USDT", "contractType": "PERPETUAL",
             "status": "TRADING", "pricePrecision": 2, "filters": []}
            for i in range(640)
        ]
        client = _FakeClient(exchange={"symbols": symbols})
        MX.refresh_catalog(self.cache, client, T0)
        MX.refresh_catalog(self.cache, client, T0 + 1000, force=True)
        con = self.cache._con()  # noqa: SLF001
        try:
            total = con.execute("SELECT count(*) FROM contract_events").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(total, 0)

    def test_first_refresh_does_not_invent_listing_events(self) -> None:
        # Sin snapshot previo no se puede afirmar que 5 contratos "aparecieron".
        MX.refresh_catalog(self.cache, _FakeClient(exchange=_exchange_payload()), T0)
        con = self.cache._con()  # noqa: SLF001
        try:
            total = con.execute("SELECT count(*) FROM contract_events").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(total, 0)

    def test_search_payload_filters_and_states(self) -> None:
        MX.refresh_catalog(self.cache, _FakeClient(exchange=_exchange_payload()), T0)
        data = MX.catalog_payload(self.cache, None, query="BTC", limit=10,
                                  now_ms=T0)
        self.assertTrue(data["available"])
        self.assertFalse(data["spot_included"])
        # "BTC" tambien aparece en el base_asset de BTCEUR (no elegible): se
        # muestra con motivos, pero el match exacto de simbolo va primero.
        self.assertEqual([r["symbol"] for r in data["results"]],
                         ["BTCUSDT", "BTCEUR"])
        self.assertEqual(data["results"][1]["exclusion_reasons"],
                         ["quote_asset=EUR"])
        eligible = MX.catalog_payload(self.cache, None, query="", limit=10,
                                      eligible_only=True, now_ms=T0)
        symbols = {r["symbol"] for r in eligible["results"]}
        self.assertIn("BTCUSDT", symbols)
        self.assertIn("NMRUSDT", symbols)
        self.assertNotIn("OLDUSDT", symbols)

    def test_empty_catalog_is_declared_not_invented(self) -> None:
        data = MX.catalog_payload(self.cache, None, query="BTC", limit=10,
                                  now_ms=T0, allow_fetch=False)
        self.assertFalse(data["available"])
        self.assertEqual(data["reason"], "CATALOG_NOT_CACHED")
        self.assertEqual(data["results"], [])

    def test_stale_marker_reported(self) -> None:
        MX.refresh_catalog(self.cache, _FakeClient(exchange=_exchange_payload()), T0)
        data = MX.catalog_payload(self.cache, None, query="BTC", limit=10,
                                  now_ms=T0 + 48 * 3600 * 1000, allow_fetch=False)
        self.assertTrue(data["catalog"]["stale"])
        self.assertGreater(data["catalog"]["age_ms"], 0)


class StoredReadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mkt_read_"))
        self.addCleanup(lambda: _rmtree(self.tmp))
        self.cache = MarketCache(self.tmp / "cache.db")
        self.cache.init_db()
        self.history = self.tmp / "historical.db"

    def test_missing_canonical_db_is_tolerated(self) -> None:
        self.cache.upsert_klines("BTCUSDT", "1h", "klines",
                                 [_cache_bar(T0)], T0)
        bars, info = MX.read_stored(self.cache, "BTCUSDT", "1h", "klines",
                                    T0 - STEP_1H, T0 + STEP_1H, self.history)
        self.assertEqual(len(bars), 1)
        self.assertEqual(info["canonical_error"], "CANONICAL_MISSING")

    def test_canonical_rows_are_merged_and_deduped(self) -> None:
        import sqlite3
        con = sqlite3.connect(str(self.history))
        con.execute(
            "CREATE TABLE historical_klines (symbol TEXT, interval TEXT,"
            " open_time INTEGER, open TEXT, high TEXT, low TEXT, close TEXT,"
            " base_volume TEXT, close_time INTEGER, quote_volume TEXT,"
            " trade_count INTEGER, taker_buy_base TEXT, taker_buy_quote TEXT,"
            " fetched_at INTEGER, PRIMARY KEY (symbol, interval, open_time))")
        con.execute(
            "INSERT INTO historical_klines (symbol, interval, open_time, open,"
            " high, low, close, base_volume, close_time, quote_volume,"
            " trade_count, taker_buy_base, taker_buy_quote, fetched_at)"
            " VALUES ('BTCUSDT','1h',?, '200','201','199','200.5','7','x',"
            " '700', 9, '1','2', ?)", (T0, T0 - 5000))
        con.commit()
        con.close()
        # Cache trae la MISMA apertura mas reciente: gana la mas fresca.
        self.cache.upsert_klines("BTCUSDT", "1h", "klines",
                                 [_cache_bar(T0, price=100.0)], T0)
        bars, info = MX.read_stored(self.cache, "BTCUSDT", "1h", "klines",
                                    T0 - STEP_1H, T0 + STEP_1H, self.history)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["storage"], "cache")
        self.assertTrue(bars[0]["also_canonical"])
        self.assertEqual(info["canonical_rows"], 1)
        self.assertIsNone(info["canonical_error"])

    def test_canonical_only_row_is_kept(self) -> None:
        import sqlite3
        con = sqlite3.connect(str(self.history))
        con.execute(
            "CREATE TABLE historical_klines (symbol TEXT, interval TEXT,"
            " open_time INTEGER, open TEXT, high TEXT, low TEXT, close TEXT,"
            " base_volume TEXT, close_time INTEGER, quote_volume TEXT,"
            " trade_count INTEGER, taker_buy_base TEXT, taker_buy_quote TEXT,"
            " fetched_at INTEGER, PRIMARY KEY (symbol, interval, open_time))")
        con.execute(
            "INSERT INTO historical_klines (symbol, interval, open_time, open,"
            " high, low, close, base_volume, close_time, quote_volume,"
            " trade_count, taker_buy_base, taker_buy_quote, fetched_at)"
            " VALUES ('BTCUSDT','1h',?, '200','201','199','200.5','7','x',"
            " '700', 9, '1','2', ?)", (T0, T0 - 5000))
        con.commit()
        con.close()
        bars, _ = MX.read_stored(self.cache, "BTCUSDT", "1h", "klines",
                                 T0 - STEP_1H, T0 + STEP_1H, self.history)
        self.assertEqual(bars[0]["storage"], "canonical")
        self.assertEqual(bars[0]["close"], "200.5")

    def test_limit_keeps_the_most_recent_bars_of_the_range(self) -> None:
        """Rango con mas velas que el limite: se conserva la COLA (las mas
        recientes), no la cabeza. Un rango amplio ("todo lo almacenado") no
        debe perder las velas recientes por el recorte ASC."""
        bars_30 = [_cache_bar(T0 + i * STEP_1H, price=100.0 + i)
                   for i in range(30)]
        self.cache.upsert_klines("BTCUSDT", "1h", "klines", bars_30, T0)
        bars, _ = MX.read_stored(self.cache, "BTCUSDT", "1h", "klines",
                                 0, T0 + 1000 * STEP_1H, self.history,
                                 limit=10)
        self.assertEqual(len(bars), 10)
        self.assertEqual(
            [b["open_time"] for b in bars],
            [T0 + i * STEP_1H for i in range(20, 30)])
        self.assertEqual(
            [b["open_time"] for b in bars], sorted(
                b["open_time"] for b in bars))


class PlanMissingBlockTest(unittest.TestCase):
    def test_empty_cache_requests_newest_bounded_block(self) -> None:
        block = MX.plan_missing_block([], T0, T0 + 500 * STEP_1H, STEP_1H, 2,
                                      page_limit=100)
        self.assertIsNotNone(block)
        start, end = block
        self.assertEqual(end, T0 + 500 * STEP_1H)
        self.assertEqual(end - start, 199 * STEP_1H)

    def test_existing_bars_requests_block_before_oldest(self) -> None:
        bars = [{"open_time": T0}, {"open_time": T0 + STEP_1H}]
        start, end = MX.plan_missing_block(bars, T0 - 500 * STEP_1H,
                                           T0 + STEP_1H, STEP_1H, 1,
                                           page_limit=50)
        self.assertEqual(end, T0 - STEP_1H)
        self.assertEqual(end - start, 49 * STEP_1H)

    def test_returns_none_when_nothing_left_to_fetch(self) -> None:
        bars = [{"open_time": T0}, {"open_time": T0 + STEP_1H}]
        self.assertIsNone(MX.plan_missing_block(bars, T0, T0 + STEP_1H,
                                               STEP_1H, 1, page_limit=50))

    def test_gap_ahead_requests_later_block(self) -> None:
        bars = [{"open_time": T0}]
        start, end = MX.plan_missing_block(bars, T0, T0 + 100 * STEP_1H,
                                          STEP_1H, 1, page_limit=10)
        self.assertEqual(end, T0 + 100 * STEP_1H)
        self.assertEqual(end - start, 9 * STEP_1H)


class SeriesPayloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mkt_series_"))
        self.addCleanup(lambda: _rmtree(self.tmp))
        self.cache = MarketCache(self.tmp / "cache.db")
        self.cache.init_db()
        self.history = self.tmp / "historical.db"
        self.now = T0 + 400 * STEP_1H
        MX.refresh_catalog(self.cache, _FakeClient(exchange=_exchange_payload()),
                           T0)

    def _fill(self, count: int, start: int, price: float = 100.0) -> None:
        self.cache.upsert_klines(
            "BTCUSDT", "1h", "klines",
            [_cache_bar(start + i * STEP_1H, price + i * 0.1)
             for i in range(count)], T0)

    def test_no_fetch_reads_only_stored_and_reports_coverage(self) -> None:
        self._fill(5, T0)
        data = MX.series_payload(
            self.cache, None, symbol="btcusdt", interval="1h",
            from_ms=T0, to_ms=T0 + 4 * STEP_1H, allow_fetch=False,
            now_ms=self.now, history_db=self.history)
        self.assertEqual(data["symbol"], "BTCUSDT")
        self.assertFalse(data["labels"]["live"])
        self.assertEqual(data["labels"]["mode"], "HISTORICAL_ON_DEMAND")
        self.assertEqual(len(data["candles"]), 5)
        self.assertEqual([c["open_time_ms"] for c in data["candles"]],
                         [T0 + i * STEP_1H for i in range(5)])
        self.assertEqual(data["coverage"]["state"], "COVERED")
        self.assertFalse(data["fetch"]["performed"])
        self.assertEqual(data["volume"]["available"], True)
        self.assertEqual(data["volume"]["base_asset"], "BTC")
        self.assertFalse(data["candles"][0]["provisional"])
        self.assertEqual(data["candles"][0]["open"], "100.0")
        # Limites explicitos de adquisicion expuestos al cliente.
        self.assertEqual(data["budget"]["max_requests_per_window"],
                         MX.MAX_FETCH_REQUESTS_PER_WINDOW)
        self.assertEqual(data["budget"]["window_ms"], MX.ROLLING_WINDOW_MS)
        self.assertEqual(data["budget"]["concurrency"], MX.MAX_CONCURRENCY)
        self.assertEqual(data["budget"]["max_page_limit"], MX.PAGE_LIMIT)
        self.assertEqual(data["budget"]["max_pages_per_request"],
                         MX.MAX_PAGES_PER_REQUEST)
        self.assertEqual(data["budget"]["used_in_window"], 0)

    def test_missing_range_is_declared_as_absence(self) -> None:
        self._fill(3, T0 + 10 * STEP_1H)
        data = MX.series_payload(
            self.cache, None, symbol="BTCUSDT", interval="1h",
            from_ms=T0, to_ms=T0 + 12 * STEP_1H, allow_fetch=False,
            now_ms=self.now, history_db=self.history)
        self.assertEqual(data["coverage"]["state"], "PARTIAL")
        self.assertEqual(data["coverage"]["absent_ranges"],
                         [[T0, T0 + 9 * STEP_1H]])
        self.assertEqual(data["observed"]["start_ms"], T0 + 10 * STEP_1H)

    def test_real_holes_are_not_confused_with_absence(self) -> None:
        self._fill(2, T0)
        self._fill(2, T0 + 5 * STEP_1H)
        data = MX.series_payload(
            self.cache, None, symbol="BTCUSDT", interval="1h",
            from_ms=T0, to_ms=T0 + 6 * STEP_1H, allow_fetch=False,
            now_ms=self.now, history_db=self.history)
        self.assertEqual(data["coverage"]["gap_count"], 3)
        self.assertEqual(data["coverage"]["gaps"],
                         [[T0 + 2 * STEP_1H, T0 + 4 * STEP_1H]])
        self.assertEqual(data["coverage"]["absent_ranges"], [])

    def test_provisional_last_bar_hides_close_time(self) -> None:
        open_time = T0 + 400 * STEP_1H  # abierta en self.now, sin cerrar
        self._fill(1, open_time)
        data = MX.series_payload(
            self.cache, None, symbol="BTCUSDT", interval="1h",
            from_ms=open_time, to_ms=open_time, allow_fetch=False,
            now_ms=self.now + 1000, history_db=self.history)
        candle = data["candles"][0]
        self.assertTrue(candle["provisional"])
        self.assertIsNone(candle["close_time_ms"])
        self.assertTrue(data["freshness"]["provisional"])
        self.assertEqual(data["freshness"]["fetched_at_ms"], T0)

    def test_closed_bar_keeps_reported_close_time(self) -> None:
        self._fill(2, T0)
        data = MX.series_payload(
            self.cache, None, symbol="BTCUSDT", interval="1h",
            from_ms=T0, to_ms=T0 + STEP_1H, allow_fetch=False,
            now_ms=self.now, history_db=self.history)
        self.assertEqual(data["candles"][1]["close_time_ms"],
                         T0 + 2 * STEP_1H - 1)
        self.assertFalse(data["freshness"]["provisional"])

    def test_mark_klines_declare_no_volume(self) -> None:
        self.cache.upsert_klines(
            "BTCUSDT", "1h", "mark_klines",
            [{"open_time": T0, "open": "1", "high": "2", "low": "1",
              "close": "2", "trade_count": 3, "close_time": T0 + STEP_1H - 1,
              "fetched_at": T0}], T0)
        data = MX.series_payload(
            self.cache, None, symbol="BTCUSDT", interval="1h",
            source="mark_klines", from_ms=T0, to_ms=T0, allow_fetch=False,
            now_ms=self.now, history_db=self.history)
        self.assertFalse(data["volume"]["available"])
        self.assertEqual(data["volume"]["reason"], "mark_klines no publica volumen")
        self.assertEqual(data["volume"]["fields"], [])

    def test_contract_info_comes_from_cached_catalog(self) -> None:
        MX.refresh_catalog(self.cache, _FakeClient(exchange=_exchange_payload()),
                           T0)
        self._fill(1, T0)
        data = MX.series_payload(
            self.cache, None, symbol="BTCUSDT", interval="1h",
            from_ms=T0, to_ms=T0, allow_fetch=False, now_ms=self.now,
            history_db=self.history)
        self.assertEqual(data["contract"]["contract_type"], "PERPETUAL")
        self.assertTrue(data["contract"]["eligible"])

    def test_unknown_contract_is_null_not_invented(self) -> None:
        self.cache.upsert_klines("ZZZUSDT", "1h", "klines",
                                 [_cache_bar(T0)], T0)
        data = MX.series_payload(
            self.cache, None, symbol="ZZZUSDT", interval="1h",
            from_ms=T0, to_ms=T0, allow_fetch=False, now_ms=self.now,
            history_db=self.history)
        self.assertIsNone(data["contract"])
        self.assertFalse(data["volume"]["available"] is False)

    def test_fetch_performs_bounded_acquisition_and_records_budget(self) -> None:
        bars = [_bar(T0 + i * STEP_1H, 100.0 + i) for i in range(50)]
        client = _FakeClient(payload_bars=bars)
        data = MX.series_payload(
            self.cache, client, symbol="BTCUSDT", interval="1h",
            from_ms=T0, to_ms=T0 + 49 * STEP_1H, pages=1, page_limit=1000,
            now_ms=self.now, history_db=self.history)
        self.assertTrue(data["fetch"]["performed"])
        self.assertEqual(data["fetch"]["status"], "ok")
        self.assertEqual(client.stats.requests, 1)
        self.assertEqual(len(data["candles"]), 50)
        self.assertEqual(data["coverage"]["state"], "COVERED")
        self.assertEqual(self.cache.requests_in_window(self.now), 1)
        self.assertEqual(data["fetch"]["block"], [T0, T0 + 49 * STEP_1H])

    def test_second_call_reuses_cache_without_network(self) -> None:
        bars = [_bar(T0 + i * STEP_1H, 100.0 + i) for i in range(10)]
        client = _FakeClient(payload_bars=bars)
        MX.series_payload(self.cache, client, symbol="BTCUSDT", interval="1h",
                          from_ms=T0, to_ms=T0 + 9 * STEP_1H, pages=1,
                          now_ms=self.now, history_db=self.history)
        self.assertEqual(client.stats.requests, 1)
        data = MX.series_payload(self.cache, client, symbol="BTCUSDT",
                                 interval="1h", from_ms=T0,
                                 to_ms=T0 + 9 * STEP_1H, pages=1,
                                 now_ms=self.now, history_db=self.history)
        self.assertEqual(client.stats.requests, 1)
        self.assertEqual(len(data["candles"]), 10)

    def test_budget_exhausted_refuses_without_calling_client(self) -> None:
        self.cache.record_fetch(self.now - 1000, None, None, None,
                                MX.MAX_FETCH_REQUESTS_PER_WINDOW)
        client = _FakeClient(payload_bars=[_bar(T0)])
        data = MX.series_payload(
            self.cache, client, symbol="BTCUSDT", interval="1h",
            from_ms=T0, to_ms=T0, now_ms=self.now, history_db=self.history)
        self.assertEqual(data["fetch"]["error"], "RATE_BUDGET_EXHAUSTED")
        self.assertEqual(client.stats.requests, 0)
        self.assertEqual(client.calls, [])

    def test_rate_limit_abort_is_reported_not_retried_forever(self) -> None:
        client = _FakeClient(raises=RateLimitExceeded("HTTP 418 IP ban"))
        data = MX.series_payload(
            self.cache, client, symbol="BTCUSDT", interval="1h",
            from_ms=T0, to_ms=T0, now_ms=self.now, history_db=self.history)
        self.assertEqual(data["fetch"]["error"], "RATE_LIMIT_ABORTED")
        self.assertEqual(data["fetch"]["status"], "rate_limited")
        self.assertEqual(len(client.calls), 1)

    def test_transport_error_is_reported(self) -> None:
        client = _FakeClient(raises=OSError("network down"))
        data = MX.series_payload(
            self.cache, client, symbol="BTCUSDT", interval="1h",
            from_ms=T0, to_ms=T0, now_ms=self.now, history_db=self.history)
        self.assertEqual(data["fetch"]["error"], "FETCH_FAILED")
        self.assertIn("network down", data["fetch"]["detail"])

    def test_invalid_inputs_are_rejected(self) -> None:
        for kwargs in ({"symbol": "btc usdt"}, {"interval": "3m"},
                       {"source": "aggTrades"}):
            params = {"symbol": "BTCUSDT", "interval": "1h", "source": "klines",
                      "now_ms": self.now, "history_db": self.history}
            params.update(kwargs)
            with self.assertRaises(ValueError):
                MX.series_payload(self.cache, None, allow_fetch=False, **params)

    def test_inverted_range_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MX.series_payload(self.cache, None, symbol="BTCUSDT",
                              interval="1h", from_ms=T0 + 10, to_ms=T0,
                              now_ms=self.now, history_db=self.history)

    def test_earliest_probe_is_cached_and_marks_history_end(self) -> None:
        bars = [_bar(T0 + i * STEP_1H) for i in range(3)]
        client = _FakeClient(payload_bars=bars)
        data = MX.series_payload(
            self.cache, client, symbol="BTCUSDT", interval="1h",
            from_ms=T0 - 10 * STEP_1H, to_ms=T0, allow_fetch=False,
            now_ms=self.now, history_db=self.history)
        self.assertFalse(data["coverage"]["exhausted_before"])
        probe = MX._probe_earliest(self.cache, client, "BTCUSDT", "1h",
                                   "klines", self.now)  # noqa: SLF001
        self.assertTrue(probe["performed"])
        self.assertEqual(probe["earliest_available_ms"], T0)
        again = MX._probe_earliest(self.cache, client, "BTCUSDT", "1h",
                                   "klines", self.now)  # noqa: SLF001
        self.assertFalse(again["performed"])
        self.assertEqual(again["detail"], "cached")

    def test_coverage_no_candles_is_no_coverage(self) -> None:
        coverage = MX.compute_coverage([], T0, T0 + STEP_1H, STEP_1H)
        self.assertEqual(coverage["state"], "NO_COVERAGE")
        self.assertEqual(coverage["absent_ranges"], [[T0, T0 + STEP_1H]])


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mkt_cli_"))
        self.addCleanup(lambda: _rmtree(self.tmp))
        self.cache_db = str(self.tmp / "cache.db")
        self.history_db = str(self.tmp / "historical.db")

    def _run(self, argv):
        from market_explorer import main
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        raw = (out.getvalue() or err.getvalue()).strip().splitlines()
        return code, json.loads(raw[-1])

    def test_catalog_without_network_declares_unavailable(self) -> None:
        code, payload = self._run([
            "--action", "catalog", "--no-fetch", "--cache-db", self.cache_db,
            "--now-ms", str(T0)])
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["data"]["available"])
        self.assertEqual(payload["data"]["reason"], "CATALOG_NOT_CACHED")

    def test_series_without_network_reports_no_coverage(self) -> None:
        code, payload = self._run([
            "--action", "series", "--symbol", "btcusdt", "--interval", "1h",
            "--no-fetch", "--cache-db", self.cache_db, "--history-db",
            self.history_db, "--now-ms", str(T0)])
        self.assertEqual(code, 0)
        data = payload["data"]
        self.assertEqual(data["symbol"], "BTCUSDT")
        self.assertEqual(data["candles"], [])
        self.assertEqual(data["coverage"]["state"], "NO_COVERAGE")
        self.assertFalse(data["labels"]["live"])
        self.assertEqual(data["budget"]["max_pages_per_request"],
                         MX.MAX_PAGES_PER_REQUEST)

    def test_cli_rejects_invalid_interval(self) -> None:
        code, payload = self._run([
            "--action", "series", "--symbol", "BTCUSDT", "--interval", "3m",
            "--no-fetch", "--cache-db", self.cache_db])
        self.assertEqual(code, 3)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "VALIDATION_ERROR")

    def test_cli_rejects_unknown_action(self) -> None:
        from market_explorer import main
        buf = io.StringIO()
        with redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = main(["--action", "trade"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
