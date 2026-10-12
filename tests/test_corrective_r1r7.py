"""Corrective regressions R1-R7 (review of SHA 906c271).

Each test FAILS on the pristine 906c271 tree and PASSES after the fix.
Synthetic fixtures and temp resources exclusively; no network, DB, clock.
Mechanics only — no strategy, entries, or profitability invented.
Run: python run_tests.py
"""

from __future__ import annotations

import unittest

from microstructure_probe.backtest_offline import (
    BacktestConfig,
    Candle,
    StudyEvent,
    run_backtest,
)


def _cfg(**kw):
    base = dict(fee_bps=0.0, funding_8h_bps=0.0, spread_bps=0.0,
                slippage_bps=0.0, notional_usdt=1000.0)
    base.update(kw)
    return BacktestConfig(**base)


def _candle(t, o, h, l, c, symbol="BTCUSDT"):
    return Candle(symbol, t, o, h, l, c)


# ---------------------------------------------------------------- R1

class R1StopAvailabilityTest(unittest.TestCase):
    """Stops need known OHLC: open at its timestamp, rest at close."""

    def test_future_low_cannot_trigger_stop(self) -> None:
        base = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                _candle(2000, 100.0, 100.0, 100.0, 100.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=1000)
        calm = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                            base, cfg)
        moved = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                             [_candle(1000, 100.0, 100.0, 80.0, 100.0),
                              _candle(2000, 100.0, 100.0, 100.0, 100.0)],
                             cfg)
        self.assertEqual(calm["trades"], moved["trades"])
        # Data extends past the window, so the rule (not data-end) closes
        # the position — marked at last knowledge, never with future data.
        self.assertEqual(moved["trades"][0]["exit_reason"], "horizon")
        self.assertEqual(moved["trades"][0]["exit_ms"], 1000)
        self.assertAlmostEqual(moved["trades"][0]["exit_px"], 100.0)

    def test_unknown_close_time_never_triggers_stop(self) -> None:
        candles = [_candle(1000, 100.0, 100.0, 80.0, 100.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(res["trades"][0]["exit_reason"], "open_at_end")

    def test_close_exactly_at_boundary_is_usable(self) -> None:
        # Guard (passes before and after): the boundary close_time is
        # usable, so this stop must still trigger after the R1 fix.
        candles = [_candle(500, 100.0, 100.0, 80.0, 100.0),
                   _candle(1000, 100.0, 100.0, 100.0, 100.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=1000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(res["trades"][0]["exit_reason"], "stop")
        self.assertAlmostEqual(res["trades"][0]["exit_px"], 90.0)

    def test_short_mirror_future_high_ignored(self) -> None:
        base = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                _candle(2000, 100.0, 100.0, 100.0, 100.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=1000)
        calm = run_backtest([StudyEvent("BTCUSDT", 0, "SHORT", 100.0)],
                            base, cfg)
        moved = run_backtest([StudyEvent("BTCUSDT", 0, "SHORT", 100.0)],
                             [_candle(1000, 100.0, 120.0, 100.0, 100.0),
                              _candle(2000, 100.0, 100.0, 100.0, 100.0)],
                             cfg)
        self.assertEqual(calm["trades"], moved["trades"])


# ---------------------------------------------------------------- R2

class R2DataEndTest(unittest.TestCase):
    """Data end is a mark at last knowledge, never a horizon execution."""

    def test_horizon_beyond_data_marks_at_last_known(self) -> None:
        candles = [_candle(1000, 100.0, 100.5, 99.5, 100.0),
                   _candle(2000, 100.0, 100.5, 99.5, 100.0),
                   _candle(3000, 100.0, 100.5, 99.5, 100.0)]
        cfg = _cfg(stop_distance_pct=50.0, exit_horizon_ms=100_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(res["n_trades"], 1)
        trade = res["trades"][0]
        self.assertEqual(trade["exit_reason"], "open_at_end")
        self.assertTrue(trade["open_at_end"])
        self.assertEqual(trade["exit_ms"], 3000)
        self.assertAlmostEqual(trade["exit_px"], 100.0)

    def test_two_candles_partial_marks_at_last_known(self) -> None:
        candles = [_candle(1000, 100.0, 100.5, 99.5, 100.0),
                   _candle(2000, 100.0, 100.5, 99.5, 100.0)]
        cfg = _cfg(partial_fill_notional_cap=500.0, stop_distance_pct=50.0,
                   exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertTrue(trade["open_at_end"])
        self.assertEqual(trade["exit_reason"], "open_at_end")
        self.assertAlmostEqual(trade["filled_qty"], 10.0)
        self.assertAlmostEqual(trade["cancelled_notional"], 0.0)
        self.assertEqual(trade["exit_ms"], 2000)
        self.assertAlmostEqual(trade["exit_px"], 100.0)

    def test_no_candles_is_expired(self) -> None:
        # Guard (passes before and after): empty series already expired
        # with a count in v2; locked here against regressions.
        cfg = _cfg(exit_horizon_ms=1000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)], [],
                           cfg)
        self.assertEqual(res["n_trades"], 0)
        self.assertEqual(res["n_expired"], 1)


# ---------------------------------------------------------------- R3

class R3GapRecoveryTest(unittest.TestCase):
    """Resolve the observable gap at the open; no retrospective upgrade."""

    def test_long_gap_down_exits_at_open(self) -> None:
        candles = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                   _candle(2000, 80.0, 100.0, 80.0, 95.0),
                   _candle(3000, 95.0, 95.0, 95.0, 95.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertAlmostEqual(trade["exit_px"], 80.0)

    def test_short_gap_up_exits_at_open(self) -> None:
        candles = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                   _candle(2000, 120.0, 120.0, 90.0, 95.0),
                   _candle(3000, 95.0, 95.0, 95.0, 95.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "SHORT", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertAlmostEqual(trade["exit_px"], 120.0)

    def test_recovery_past_entry_still_exits_at_gap(self) -> None:
        candles = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                   _candle(2000, 80.0, 110.0, 80.0, 105.0),
                   _candle(3000, 105.0, 105.0, 105.0, 105.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertAlmostEqual(res["trades"][0]["exit_px"], 80.0)


# ---------------------------------------------------------------- R4

class R4StopBeforeFillsTest(unittest.TestCase):
    """Existing stops resolve before any new fill at the same candle."""

    def test_gap_open_ends_position_before_second_fill(self) -> None:
        candles = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                   _candle(2000, 89.0, 89.0, 89.0, 89.0),
                   _candle(3000, 89.0, 89.0, 89.0, 89.0)]
        cfg = _cfg(partial_fill_notional_cap=500.0, stop_distance_pct=10.0,
                   exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertEqual(trade["fills"], 1)
        self.assertAlmostEqual(trade["entry_px"], 100.0)
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertAlmostEqual(trade["exit_px"], 89.0)
        self.assertAlmostEqual(trade["cancelled_notional"], 500.0)

    def test_safe_open_still_permits_second_fill(self) -> None:
        # Guard (passes before and after): a safe open keeps the
        # permitted second fill; documents the allowed path next to R4a.
        candles = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                   _candle(2000, 95.0, 95.0, 95.0, 95.0),
                   _candle(3000, 95.0, 96.0, 94.0, 95.0)]
        cfg = _cfg(partial_fill_notional_cap=500.0, stop_distance_pct=10.0,
                   exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        self.assertEqual(res["trades"][0]["fills"], 2)


# ---------------------------------------------------------------- R5

class R5StopMetricsTest(unittest.TestCase):
    """MFE/MAE from demonstrated prints; extremes need known order."""

    def test_long_stop_reports_mae_without_candle_extreme(self) -> None:
        candles = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                   _candle(2000, 100.0, 101.0, 85.0, 86.0),
                   _candle(3000, 86.0, 86.0, 86.0, 86.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertAlmostEqual(trade["exit_px"], 90.0)
        self.assertAlmostEqual(trade["mae_pct"], 10.0)
        self.assertAlmostEqual(trade["mfe_pct"], 0.0)

    def test_open_print_credits_mfe_but_not_extreme(self) -> None:
        candles = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                   _candle(2000, 102.0, 103.0, 85.0, 86.0),
                   _candle(3000, 86.0, 86.0, 86.0, 86.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertAlmostEqual(trade["mfe_pct"], 2.0)
        self.assertAlmostEqual(trade["mae_pct"], 10.0)

    def test_short_stop_mirror(self) -> None:
        candles = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                   _candle(2000, 98.0, 112.0, 97.0, 111.0),
                   _candle(3000, 111.0, 111.0, 111.0, 111.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "SHORT", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertAlmostEqual(trade["exit_px"], 110.0)
        self.assertAlmostEqual(trade["mfe_pct"], 2.0)
        self.assertAlmostEqual(trade["mae_pct"], 10.0)

    def test_gap_stop_mae_is_full_gap(self) -> None:
        candles = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                   _candle(2000, 80.0, 100.0, 80.0, 95.0),
                   _candle(3000, 95.0, 95.0, 95.0, 95.0)]
        cfg = _cfg(stop_distance_pct=10.0, exit_horizon_ms=60_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertAlmostEqual(trade["mae_pct"], 20.0)
        self.assertAlmostEqual(trade["mfe_pct"], 0.0)

    def test_partial_fill_stop_uses_average(self) -> None:
        candles = [_candle(1000, 100.0, 100.0, 100.0, 100.0),
                   _candle(2000, 200.0, 200.0, 200.0, 200.0),
                   _candle(3000, 200.0, 200.0, 100.0, 100.0),
                   _candle(4000, 150.0, 150.0, 150.0, 150.0)]
        cfg = _cfg(partial_fill_notional_cap=500.0, stop_distance_pct=10.0,
                   exit_horizon_ms=600_000)
        res = run_backtest([StudyEvent("BTCUSDT", 0, "LONG", 100.0)],
                           candles, cfg)
        trade = res["trades"][0]
        self.assertAlmostEqual(trade["filled_qty"], 7.5)
        self.assertAlmostEqual(trade["exit_px"], 120.0)
        self.assertAlmostEqual(trade["mfe_pct"], 50.0)
        self.assertAlmostEqual(trade["mae_pct"], 10.0)


# ---------------------------------------------------------------- R6

class R6SingleInitToV10Test(unittest.TestCase):
    """One init_db from any supported version leaves a fully operable v10."""

    def _vkt_db(self, version, build):
        import sqlite3
        import tempfile
        from pathlib import Path

        from microstructure_probe.persistence import PersistenceStore

        tmp = Path(tempfile.mkdtemp(prefix="r6mig_"))
        self.addCleanup(lambda: _rmtree(tmp))
        path = tmp / ("v%d.db" % version)
        con = sqlite3.connect(str(path))
        try:
            build(con)
        finally:
            con.close()
        store = PersistenceStore(db_path=path)
        store.init_db()
        self.addCleanup(store.close)
        return store

    def test_v1_single_init_reaches_v10(self) -> None:
        def build(con):
            con.execute("CREATE TABLE persistence_meta (key TEXT PRIMARY KEY,"
                        " value TEXT NOT NULL)")
            con.execute("INSERT INTO persistence_meta VALUES"
                        " ('schema_version', '1')")
            # Genuine v1 shape: full snapshot columns (later versions only
            # ADD tables/columns around it).
            con.execute("CREATE TABLE telemetry_snapshots (id INTEGER PRIMARY"
                        " KEY AUTOINCREMENT, timestamp REAL NOT NULL,"
                        " runtime_seconds REAL NOT NULL, bot_mode TEXT NOT"
                        " NULL, api_keys_used INTEGER NOT NULL,"
                        " real_orders_sent INTEGER NOT NULL,"
                        " real_capital_at_risk REAL NOT NULL,"
                        " max_drawdown_kill_switch_active INTEGER NOT NULL,"
                        " authenticated_clients_present INTEGER NOT NULL,"
                        " order_execution_path_present INTEGER NOT NULL,"
                        " clock_sync_json TEXT, latency_json TEXT,"
                        " legacy_global_clamped_lag_ms REAL,"
                        " processing_json TEXT, detectors_json TEXT,"
                        " data_quality_json TEXT, events_by_type_json TEXT,"
                        " spread_bps_json TEXT, book_imbalance_json TEXT)")
            con.commit()

        store = self._vkt_db(1, build)
        self.assertEqual(_version(store), 10)
        self._assert_linked_operable(store)

    def test_v8_single_init_reaches_v10(self) -> None:
        from microstructure_probe.persistence import PersistenceStore

        def build(con):
            con.execute("CREATE TABLE persistence_meta (key TEXT PRIMARY KEY,"
                        " value TEXT NOT NULL)")
            con.execute("INSERT INTO persistence_meta VALUES"
                        " ('schema_version', '8')")
            # A genuine v8 carries all pre-v9 tables; the v9 chain adds
            # the prospective ones before the v10 column pass.
            con.execute("CREATE TABLE universe_events (id INTEGER PRIMARY"
                        " KEY, timestamp REAL, kind TEXT, symbol TEXT,"
                        " detail TEXT)")
            con.execute("CREATE TABLE telemetry_snapshots (id INTEGER PRIMARY"
                        " KEY AUTOINCREMENT, timestamp REAL NOT NULL,"
                        " runtime_seconds REAL NOT NULL, bot_mode TEXT NOT"
                        " NULL, api_keys_used INTEGER NOT NULL,"
                        " real_orders_sent INTEGER NOT NULL,"
                        " real_capital_at_risk REAL NOT NULL,"
                        " max_drawdown_kill_switch_active INTEGER NOT NULL,"
                        " authenticated_clients_present INTEGER NOT NULL,"
                        " order_execution_path_present INTEGER NOT NULL,"
                        " clock_sync_json TEXT, latency_json TEXT,"
                        " legacy_global_clamped_lag_ms REAL,"
                        " processing_json TEXT, detectors_json TEXT,"
                        " data_quality_json TEXT, events_by_type_json TEXT,"
                        " spread_bps_json TEXT, book_imbalance_json TEXT)")
            con.commit()

        store = self._vkt_db(8, build)
        self.assertIsInstance(store, PersistenceStore)
        self.assertEqual(_version(store), 10)
        self._assert_linked_operable(store)

    def test_repeat_init_is_idempotent(self) -> None:
        store = self._vkt_db(1, lambda con: (
            con.execute("CREATE TABLE persistence_meta (key TEXT PRIMARY KEY,"
                        " value TEXT NOT NULL)"),
            con.execute("INSERT INTO persistence_meta VALUES"
                        " ('schema_version', '1')"),
            con.execute("CREATE TABLE telemetry_snapshots (id INTEGER PRIMARY"
                        " KEY AUTOINCREMENT, timestamp REAL NOT NULL)"),
            con.commit(),
        ))
        store.log_universe_event("promoted", "BTCUSDT", "x", run_id="R1")
        store.init_db()
        store.init_db()
        self.assertEqual(_version(store), 10)
        rows = store.universe_events(limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["run_id"], "R1")

    def test_missing_linked_table_fails_loudly(self) -> None:
        import sqlite3
        import tempfile
        from pathlib import Path

        from microstructure_probe.persistence import PersistenceStore

        tmp = Path(tempfile.mkdtemp(prefix="r6partial_"))
        self.addCleanup(lambda: _rmtree(tmp))
        path = tmp / "partial.db"
        con = sqlite3.connect(str(path))
        try:
            con.execute("CREATE TABLE persistence_meta (key TEXT PRIMARY KEY,"
                        " value TEXT NOT NULL)")
            con.execute("INSERT INTO persistence_meta VALUES"
                        " ('schema_version', '9')")
            con.commit()
        finally:
            con.close()
        store = PersistenceStore(db_path=path)
        with self.assertRaises(ValueError) as ctx:
            store.init_db()
        self.assertIn("universe_events", str(ctx.exception))
        store.close()

    def _assert_linked_operable(self, store) -> None:
        store.log_universe_event("promoted", "BTCUSDT", "x", run_id="R9")
        self.assertEqual(store.universe_events(limit=1)[0]["run_id"], "R9")
        store.store_prospective_setup("K", {"symbol": "BTCUSDT"}, 1,
                                      run_id="R9")
        self.assertEqual(store.prospective_setups()[0]["run_id"], "R9")
        store.store_prospective_outcome(
            "K", "BTCUSDT", "1m", 2,
            {"outcome_state": "COMPLETE"}, run_id="R9")
        self.assertEqual(
            store.prospective_outcomes(candidate_key="K")[0]["run_id"], "R9")
        store.store_telemetry_snapshot({"run_id": "R9"})
        self.assertEqual(store.latest_telemetry()["run_id"], "R9")


def _version(store) -> int:
    with store._get_cursor() as cursor:
        cursor.execute("SELECT value FROM persistence_meta"
                       " WHERE key='schema_version'")
        return int(cursor.fetchone()[0])


def _rmtree(path) -> None:
    try:
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------- R7

class R7WorkerResolverTest(unittest.TestCase):
    """Enqueue -> worker -> drain -> cleanup with defaults forbidden."""

    def test_worker_and_retention_use_injected_store(self) -> None:
        import tempfile
        import time
        from pathlib import Path
        from unittest import mock

        from microstructure_probe.history_store import HistoryStore
        from microstructure_probe.research_recorder import ResearchRecorder
        import microstructure_probe.history_store as hist_mod

        tmp = Path(tempfile.mkdtemp(prefix="r7worker_"))
        self.addCleanup(lambda: _rmtree(tmp))
        injected = HistoryStore(tmp / "historical.db")
        injected.init_db()
        real_hs = hist_mod.HistoryStore
        default_calls = []

        def factory(db_path=None, *a, **k):
            if db_path is None:
                default_calls.append(1)
                blocked = mock.Mock()
                blocked.store_research_flow.side_effect = AssertionError(
                    "default store forbidden")
                blocked.store_research_book.side_effect = AssertionError(
                    "default store forbidden")
                blocked.research_retention_cleanup.side_effect = (
                    AssertionError("default store forbidden"))
                blocked.research_counts.side_effect = AssertionError(
                    "default store forbidden")
                return blocked
            return real_hs(db_path, *a, **k)

        rec = ResearchRecorder(db_path=None, enabled=True,
                               history_store=injected)
        with mock.patch.object(hist_mod, "HistoryStore",
                               side_effect=factory):
            base = 1_700_000_000_000 - (1_700_000_000_000 % 60_000)
            rec.record_trade("TSTUSDT", base, 100.0, 1.0, False)
            rec.record_trade("TSTUSDT", base + 15_000, 101.0, 1.0, False)
            rec.start()
            rec._last_cleanup = time.monotonic() - 4000.0  # force retention
            status = rec.stop_and_drain(timeout=10.0)
        self.assertEqual(default_calls, [])
        self.assertEqual(status["errors"], 0)
        self.assertGreaterEqual(status["writes"], 1)
        counts = injected.research_counts()
        self.assertGreaterEqual(counts["research_flow_10s"], 1)


if __name__ == "__main__":
    unittest.main()
