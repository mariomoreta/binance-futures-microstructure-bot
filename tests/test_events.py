"""P1-11C event-study engine tests (deterministic, no lookahead)."""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("MICROPROBE_HISTORICAL_DB",
                      os.path.join(tempfile.gettempdir(),
                                   "p11c-events-test.db"))

from microstructure_probe import events as EV


def _bars(n=300, step=60_000, start=1_700_000_000_000, drift=0.0002,
          vol=1_000_000.0):
    bars = []
    price = 100.0
    for i in range(n):
        ot = start + i * step
        price *= (1 + drift)
        bars.append({
            "open_time": ot, "open": str(price * 0.999),
            "high": str(price * 1.001), "low": str(price * 0.998),
            "close": str(price), "base_volume": "10",
            "close_time": ot + step - 1, "quote_volume": str(vol),
            "trade_count": 50, "taker_buy_base": "6",
            "taker_buy_quote": str(vol * 0.6),
        })
    return bars


class NoLookaheadTest(unittest.TestCase):
    def test_event_at_T_cannot_access_Tplus1(self) -> None:
        bars = _bars(1500, drift=0.0005)
        # poison the future: huge spike AFTER the last formation bar
        future = [dict(b) for b in _bars(20, start=bars[-1]["open_time"] + 60_000,
                                         drift=0.5)]
        definition = EV.default_definition("EXTENDED_GAINER")
        definition["parameters"].update({"prior_24h_return_min": -99.0,
                                         "prior_1h_return_min": -99.0,
                                         "range_position_min": 0.0})
        evs_base = EV.detect_events(bars, definition, "TSTUSDT",
                                    "regular_close", "1m")
        evs_poison = EV.detect_events(bars + future, definition, "TSTUSDT",
                                      "regular_close", "1m")
        # events with event_time < future start must be identical
        cut = future[0]["open_time"]
        base_ids = [e["event_time"] for e in evs_base if e["event_time"] < cut]
        pois_ids = [e["event_time"] for e in evs_poison if e["event_time"] < cut]
        self.assertEqual(base_ids, pois_ids)

    def test_future_path_separated_from_feature_snapshot(self) -> None:
        bars = _bars(1500, drift=0.0005)
        definition = EV.default_definition("EXTENDED_GAINER")
        definition["parameters"].update({"prior_24h_return_min": -99.0,
                                         "prior_1h_return_min": -99.0,
                                         "range_position_min": 0.0})
        evs = EV.detect_events(bars, definition, "TSTUSDT",
                               "regular_close", "1m")
        self.assertTrue(evs)
        e = evs[0]
        self.assertLessEqual(e["formation_window_end"], e["event_time"])
        out = EV.compute_outcome(e, bars, "5m")
        self.assertIn(out["path"], ("COMPLETE", "PARTIAL", "INVALID_GAP",
                                    "INSUFFICIENT_HISTORY"))

    def test_mark_regular_provenance_separation(self) -> None:
        bars = _bars(60)
        definition = EV.default_definition("EXTENDED_LOSER")
        evs_m = EV.detect_events(bars, definition, "TSTUSDT", "mark_close",
                                 "15m")
        evs_r = EV.detect_events(bars, definition, "TSTUSDT", "regular_close",
                                 "15m")
        for e in evs_m:
            self.assertEqual(e["reference_source"], "mark_close")
        for e in evs_r:
            self.assertEqual(e["reference_source"], "regular_close")


class OutcomeMathTest(unittest.TestCase):
    def _event(self, ref=100.0, direction="up"):
        return {"event_id": "e1", "event_time": 1_000_000,
                "reference_price": ref, "direction": direction}

    def _path(self, moves):
        # moves: list of (open_time, high, low, close)
        return [{"open_time": t, "high": str(h), "low": str(l),
                 "close": str(c)} for (t, h, l, c) in moves]

    def test_long_mfe_mae(self) -> None:
        e = self._event(100.0, "up")
        bars = self._path([(1_060_000, 103, 99, 101),
                           (1_120_000, 105, 98, 102),
                           (1_200_000, 104, 97, 100)])
        out = EV.compute_outcome(e, bars, "5m")
        self.assertAlmostEqual(out["mfe"], 0.05)
        self.assertAlmostEqual(out["mae"], -0.03)
        self.assertEqual(out["time_to_mfe_ms"], 120_000)
        self.assertEqual(out["time_to_mae_ms"], 200_000)

    def test_short_mfe_mae_mirror(self) -> None:
        e = self._event(100.0, "down")
        bars = self._path([(1_060_000, 101, 97, 99),
                           (1_120_000, 102, 95, 98)])
        out = EV.compute_outcome(e, bars, "5m")
        # favorable downward magnitude positive, adverse upward positive
        self.assertGreater(out["mfe"], 0)
        self.assertGreater(out["mae"], 0)

    def test_invalidation_timestamp_predeclared(self) -> None:
        e = self._event(100.0, "up")
        bars = self._path([(1_060_000, 101, 98, 100),
                           (1_120_000, 102, 96, 99)])
        out = EV.compute_outcome(e, bars, "5m", invalidation_pct=0.03)
        self.assertEqual(out["invalidation_time"], 1_120_000)

    def test_incomplete_future_path_partial(self) -> None:
        e = self._event(100.0, "up")
        bars = self._path([(1_060_000, 101, 99, 100)])
        out = EV.compute_outcome(e, bars, "1h")
        self.assertEqual(out["path"], "PARTIAL")
        self.assertFalse(out["usable_for_statistics"])

    def test_gap_exclusion(self) -> None:
        e = self._event(100.0, "up")
        # 1-minute grid with a 5-minute hole in the middle of a 15m window
        t0 = 1_060_000
        grid = []
        for i in range(16):
            if 5 <= i <= 9:
                continue
            grid.append((t0 + i * 60_000, 101, 99, 100))
        bars = self._path(grid)
        out = EV.compute_outcome(e, bars, "15m")
        # hole on the outcome grid -> excluded (INVALID_GAP or PARTIAL)
        self.assertFalse(out["usable_for_statistics"])

    def test_formation_gap_exclusion(self) -> None:
        e = self._event(100.0, "up")
        e["formation_gap"] = True
        bars = self._path([(1_060_000 + i * 60_000, 101, 99, 100)
                           for i in range(40)])
        out = EV.compute_outcome(e, bars, "5m")
        self.assertFalse(out["usable_for_statistics"])


class ContextDisciplineTest(unittest.TestCase):
    def test_btc_synchronized_lookup_no_future(self) -> None:
        bars = _bars(120)
        btc = _bars(120)
        # future BTC spike must not leak into formation features
        feat_before = EV.formation_features(bars[:60], 59, "TSTUSDT",
                                            "regular_close", btc[:60])
        feat_after = EV.formation_features(bars[:60], 59, "TSTUSDT",
                                           "regular_close", btc)
        self.assertEqual(feat_before["btc_context"].get("reference_close"),
                         feat_after["btc_context"].get("reference_close"))

    def test_relative_return(self) -> None:
        bars = _bars(120, drift=0.001)
        btc = _bars(120, drift=0.0005)
        feat = EV.formation_features(bars, 119, "TSTUSDT",
                                     "regular_close", btc)
        if feat["prior_1h_return"] is not None and feat["btc_ret_1h"] is not None:
            self.assertAlmostEqual(feat["relative_return_1h"],
                                   feat["prior_1h_return"] - feat["btc_ret_1h"])

    def test_30d_high_asof(self) -> None:
        bars = _bars(200, drift=0.001)
        f1 = EV.formation_features(bars[:100], 99, "TSTUSDT", "regular_close")
        f2 = EV.formation_features(bars[:200], 199, "TSTUSDT", "regular_close")
        # as-of discipline: earlier snapshot cannot see later highs
        self.assertLessEqual(f1["high_30d"], f2["high_30d"] + 1e-9)

    def test_taker_buy_proxy_calc_and_label(self) -> None:
        bar = {"quote_volume": "1000", "taker_buy_quote": "600"}
        self.assertAlmostEqual(EV.taker_buy_proxy(bar), 0.6)
        bars = _bars(60)
        feat = EV.formation_features(bars, 59, "TSTUSDT", "regular_close")
        self.assertEqual(feat["taker_buy_proxy_label"],
                         "HISTORICAL_TAKER_BUY_PROXY")

    def test_sample_size_tiers(self) -> None:
        self.assertEqual(EV.sample_size_label(5), "INSUFFICIENT")
        self.assertEqual(EV.sample_size_label(50), "EXPLORATORY")
        self.assertEqual(EV.sample_size_label(200), "PRELIMINARY")
        self.assertEqual(EV.sample_size_label(600), "LARGER_SAMPLE")

    def test_deterministic_rerun(self) -> None:
        bars = _bars(150, drift=0.001)
        definition = EV.default_definition("EXTENDED_GAINER")
        a = EV.detect_events(bars, definition, "TSTUSDT", "regular_close",
                             "1m")
        b = EV.detect_events(bars, definition, "TSTUSDT", "regular_close",
                             "1m")
        self.assertEqual([e["event_id"] for e in a],
                         [e["event_id"] for e in b])

    def test_definition_versioning_new_version_on_change(self) -> None:
        d1 = EV.default_definition("EXTENDED_GAINER", 1)
        d2 = EV.default_definition("EXTENDED_GAINER", 2)
        d2["parameters"]["prior_24h_return_min"] = 0.99
        self.assertNotEqual(d1["parameters"], d2["parameters"])
        self.assertNotEqual(d1["definition_version"], d2["definition_version"])

    def test_idempotent_event_persistence(self) -> None:
        from microstructure_probe.history_store import HistoryStore
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore(__import__("pathlib").Path(tmp) / "h.db")
            definition = EV.default_definition("EXTENDED_GAINER")
            store.upsert_event_definition(definition)
            bars = _bars(150, drift=0.002)
            definition["parameters"].update(
                {"prior_24h_return_min": -99.0,
                 "prior_1h_return_min": -99.0, "range_position_min": 0.0})
            evs = EV.detect_events(bars, definition, "TSTUSDT",
                                   "regular_close", "1m")
            run = store.start_event_run({"definition": "EXTENDED_GAINER",
                                         "version": 1, "symbol": "TSTUSDT"})
            n1 = store.store_event_instances(run, definition, evs)
            n2 = store.store_event_instances(run, definition, evs)
            self.assertEqual(n1, n2)

    def test_no_threshold_autotuning_surface(self) -> None:
        import inspect
        src = inspect.getsource(EV)
        for token in ("GridSearch", "optimize_threshold", "maximize_sharpe",
                      "auto_tune"):
            self.assertNotIn(token, src)


if __name__ == "__main__":
    unittest.main()
