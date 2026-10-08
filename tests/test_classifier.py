"""P1-12A classifier v0 tests (deterministic, fixtures only, no lookahead)."""

from __future__ import annotations

import json
import unittest

from microstructure_probe.classifier import (
    RULES_VERSION,
    ClassifierEngine,
    STATES,
    classify_symbol,
)


def make_features(**over) -> dict:
    base = {
        "subscribed": True,
        "live": True,
        "tier": "CORE",
        "price": {"current_price": 100.0, "sample_age_ms": 5_000},
        "returns": {"returns": {"1m": 0.0004, "15m": 0.001,
                                "1h": 0.002}},
        "momentum": {"velocity": {"1m": 1e-7, "5m": 1e-7},
                     "acceleration": {"1m": 0.0}},
        "flow": {"horizons": {"1m": {"signed_delta": 50_000.0,
                                     "delta_ratio": 0.05,
                                     "notional": 1_000_000.0}},
                 "baselines": {"1m": {"z_score": 0.5}}},
        "book": {"imbalance_notional": 0.05},
        "oi": {"horizons": {"1m": {"delta": 10.0}}},
        "structure": {
            "ranges": {"15m": {"expansion_ratio": 1.0,
                               "range_position": 0.5}},
            "structure": {"breakout_state": "INSIDE_PRIOR_RANGE"},
            "volatility": {"15m": {"realized_vol": 0.002}}},
    }
    base.update(over)
    return base


def engine_with(records, as_of_ms=1_700_000_000_000):
    eng = ClassifierEngine(symbols=tuple(records))
    return eng, eng.evaluate(records, as_of_ms)


class NormalUnknownTest(unittest.TestCase):
    def test_normal_with_sufficient_quiet_data(self) -> None:
        out = classify_symbol("BTCUSDT", make_features(), 1_000_000)
        self.assertEqual(out["state"], "NORMAL")
        self.assertIn(out["direction"], ("UP", "DOWN", "NONE"))
        self.assertEqual(out["rules_version"], RULES_VERSION)
        self.assertTrue(out["validity"]["sufficient_data"])

    def test_none_direction_on_exact_zero(self) -> None:
        feat = make_features()
        feat["momentum"]["velocity"]["1m"] = 0.0
        feat["returns"]["returns"]["1m"] = 0.0
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "NORMAL")
        self.assertEqual(out["direction"], "NONE")

    def test_unknown_on_missing_data(self) -> None:
        out = classify_symbol("BTCUSDT", {}, 1_000_000)
        self.assertEqual(out["state"], "UNKNOWN")
        self.assertEqual(out["direction"], "UNKNOWN")
        self.assertFalse(out["validity"]["sufficient_data"])

    def test_unknown_on_stale_data(self) -> None:
        feat = make_features()
        feat["price"]["sample_age_ms"] = 999_999_999
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "UNKNOWN")

    def test_unknown_gap_even_with_strong_motion(self) -> None:
        feat = make_features()
        feat["momentum"]["velocity"]["1m"] = 9e-5
        feat["price"]["sample_age_ms"] = 10_000_000
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "UNKNOWN")

    def test_discovery_only_never_deep(self) -> None:
        feat = make_features(subscribed=False, live=False, tier="DISCOVERY")
        feat["momentum"]["velocity"]["1m"] = 9e-5
        out = classify_symbol("ORCAUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "UNKNOWN")
        self.assertIn("live_subscription", out["missing_features"])


class IgnitionTest(unittest.TestCase):
    def test_ignition_up(self) -> None:
        feat = make_features()
        feat["momentum"]["velocity"]["1m"] = 5e-6
        feat["momentum"]["acceleration"]["1m"] = 2e-7
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "IGNITION")
        self.assertEqual(out["direction"], "UP")

    def test_ignition_down(self) -> None:
        feat = make_features()
        feat["momentum"]["velocity"]["1m"] = -5e-6
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = -0.4
        feat["flow"]["horizons"]["1m"]["signed_delta"] = -400_000.0
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "IGNITION")
        self.assertEqual(out["direction"], "DOWN")

    def test_velocity_alone_is_not_ignition(self) -> None:
        feat = make_features()
        feat["momentum"]["velocity"]["1m"] = 5e-6
        feat["momentum"]["acceleration"]["1m"] = 0.0
        feat["flow"]["baselines"]["1m"]["z_score"] = 0.1
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = 0.05
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertNotEqual(out["state"], "IGNITION")


class ExpansionTest(unittest.TestCase):
    def test_expansion_up(self) -> None:
        feat = make_features()
        feat["returns"]["returns"]["15m"] = 0.005
        feat["momentum"]["velocity"]["1m"] = 3e-6
        feat["structure"]["ranges"]["15m"]["expansion_ratio"] = 1.8
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = 0.5
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "EXPANSION")
        self.assertEqual(out["direction"], "UP")

    def test_expansion_down(self) -> None:
        feat = make_features()
        feat["returns"]["returns"]["15m"] = -0.006
        feat["momentum"]["velocity"]["1m"] = -4e-6
        feat["structure"]["ranges"]["15m"]["expansion_ratio"] = 2.0
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = -0.5
        feat["flow"]["horizons"]["1m"]["signed_delta"] = -500_000.0
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "EXPANSION")
        self.assertEqual(out["direction"], "DOWN")

    def test_big_24h_style_return_alone_is_not_expansion(self) -> None:
        feat = make_features()
        feat["returns"]["returns"]["1h"] = 0.08
        feat["momentum"]["velocity"]["1m"] = 1e-7
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertNotEqual(out["state"], "EXPANSION")

    def test_contradictory_flow_recorded_not_hidden(self) -> None:
        feat = make_features()
        feat["returns"]["returns"]["15m"] = 0.005
        feat["momentum"]["velocity"]["1m"] = 3e-6
        feat["structure"]["ranges"]["15m"]["expansion_ratio"] = 1.8
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = -0.5
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertTrue(any("contradict" in e for e in
                            out["evidence_against"]))


class ExhaustionTest(unittest.TestCase):
    def test_exhaustion_up(self) -> None:
        feat = make_features()
        feat["momentum"]["velocity"]["1m"] = 2e-6
        feat["momentum"]["acceleration"]["1m"] = -3e-7
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = 0.05
        feat["structure"]["ranges"]["15m"]["range_position"] = 0.9
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "EXHAUSTION")
        self.assertEqual(out["direction"], "UP")

    def test_exhaustion_down(self) -> None:
        feat = make_features()
        feat["momentum"]["velocity"]["1m"] = -2e-6
        feat["momentum"]["acceleration"]["1m"] = 3e-7
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = -0.05
        feat["flow"]["horizons"]["1m"]["signed_delta"] = -50_000.0
        feat["structure"]["ranges"]["15m"]["range_position"] = 0.1
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "EXHAUSTION")
        self.assertEqual(out["direction"], "DOWN")

    def test_big_up_move_alone_is_not_exhaustion(self) -> None:
        feat = make_features()
        feat["returns"]["returns"]["1h"] = 0.08
        feat["momentum"]["velocity"]["1m"] = 3e-6
        feat["momentum"]["acceleration"]["1m"] = 1e-7
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = 0.5
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertNotEqual(out["state"], "EXHAUSTION")


class ReversalTest(unittest.TestCase):
    def _up_expansion(self):
        feat = make_features()
        feat["returns"]["returns"]["15m"] = 0.005
        feat["momentum"]["velocity"]["1m"] = 3e-6
        feat["structure"]["ranges"]["15m"]["expansion_ratio"] = 1.8
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = 0.5
        return feat

    def _down_flip(self):
        feat = make_features()
        feat["returns"]["returns"]["1m"] = -0.002
        feat["momentum"]["velocity"]["1m"] = -4e-6
        feat["momentum"]["acceleration"]["1m"] = -2e-7
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = -0.5
        feat["flow"]["horizons"]["1m"]["signed_delta"] = -500_000.0
        feat["structure"]["structure"]["breakout_state"] = "BELOW_PRIOR_RANGE"
        return feat

    def test_reversal_needs_confirmation(self) -> None:
        eng = ClassifierEngine(symbols=("BTCUSDT",))
        first = eng.evaluate({"BTCUSDT": self._up_expansion()}, 1_000_000)[0]
        self.assertEqual(first["state"], "EXPANSION")
        second = eng.evaluate({"BTCUSDT": self._down_flip()}, 1_030_000)[0]
        # One flip is not yet a confirmed reversal: prior state held.
        self.assertEqual(second["state"], "EXPANSION")
        self.assertTrue(any("unconfirmed" in e or "confirmation" in r
                            for e in second["evidence_for"]
                            for r in [e]))
        third = eng.evaluate({"BTCUSDT": self._down_flip()}, 1_060_000)[0]
        self.assertEqual(third["state"], "REVERSAL")
        self.assertEqual(third["direction"], "DOWN")
        self.assertTrue(third["transition"]["changed"])
        self.assertEqual(third["transition"]["previous_state"], "EXPANSION")

    def test_small_pullback_is_not_reversal(self) -> None:
        eng = ClassifierEngine(symbols=("BTCUSDT",))
        eng.evaluate({"BTCUSDT": self._up_expansion()}, 1_000_000)
        feat = self._up_expansion()
        feat["momentum"]["velocity"]["1m"] = 1e-6  # weaker, same sign
        out = eng.evaluate({"BTCUSDT": feat}, 1_030_000)[0]
        self.assertNotEqual(out["state"], "REVERSAL")


class TransitionHysteresisTest(unittest.TestCase):
    def test_hysteresis_holds_then_releases(self) -> None:
        eng = ClassifierEngine(symbols=("BTCUSDT",))
        ign = make_features()
        ign["momentum"]["velocity"]["1m"] = 5e-6
        ign["momentum"]["acceleration"]["1m"] = 2e-7
        first = eng.evaluate({"BTCUSDT": ign}, 1_000_000)[0]
        self.assertEqual(first["state"], "IGNITION")
        calm = make_features()  # NORMAL-shaped
        second = eng.evaluate({"BTCUSDT": calm}, 1_030_000)[0]
        self.assertEqual(second["state"], "IGNITION")  # dwell 1/2
        self.assertIn("previous_state", second["transition"])
        third = eng.evaluate({"BTCUSDT": calm}, 1_060_000)[0]
        self.assertEqual(third["state"], "NORMAL")
        self.assertTrue(third["transition"]["changed"])
        self.assertGreaterEqual(third["transition"]["duration_ms"], 0)

    def test_unknown_exits_immediately(self) -> None:
        eng = ClassifierEngine(symbols=("BTCUSDT",))
        ign = make_features()
        ign["momentum"]["velocity"]["1m"] = 5e-6
        ign["momentum"]["acceleration"]["1m"] = 2e-7
        eng.evaluate({"BTCUSDT": ign}, 1_000_000)
        stale = make_features()
        stale["price"]["sample_age_ms"] = 10_000_000
        out = eng.evaluate({"BTCUSDT": stale}, 1_030_000)[0]
        self.assertEqual(out["state"], "UNKNOWN")

    def test_restart_cold_memory_no_phantom_reversal(self) -> None:
        feat = make_features()
        feat["momentum"]["velocity"]["1m"] = -4e-6
        feat["flow"]["horizons"]["1m"]["delta_ratio"] = -0.5
        feat["flow"]["horizons"]["1m"]["signed_delta"] = -500_000.0
        eng = ClassifierEngine(symbols=("BTCUSDT",))  # fresh: no history
        out = eng.evaluate({"BTCUSDT": feat}, 1_000_000)[0]
        self.assertNotEqual(out["state"], "REVERSAL")

    def test_timestamps_and_transition_reasons(self) -> None:
        eng = ClassifierEngine(symbols=("BTCUSDT",))
        first = eng.evaluate({"BTCUSDT": make_features()}, 1_000_000)[0]
        self.assertEqual(first["observed_at_ms"], 1_000_000)
        second = eng.evaluate({"BTCUSDT": make_features()}, 1_060_000)[0]
        self.assertEqual(second["observed_at_ms"], 1_060_000)
        self.assertIn("reasons", second["transition"])
        self.assertIsInstance(second["transition"]["reasons"], list)


class NoLookaheadTest(unittest.TestCase):
    def test_future_keys_ignored(self) -> None:
        feat = make_features(future_return=0.99,
                             next_hour_outcome="UP_UP_UP")
        plain = make_features()
        eng1 = ClassifierEngine(symbols=("BTCUSDT",))
        eng2 = ClassifierEngine(symbols=("BTCUSDT",))
        a = eng1.evaluate({"BTCUSDT": feat}, 1_000_000)[0]
        b = eng2.evaluate({"BTCUSDT": plain}, 1_000_000)[0]
        self.assertEqual(a["state"], b["state"])
        self.assertEqual(a["direction"], b["direction"])
        self.assertNotIn("future_return", a["features_used"])

    def test_deterministic_rerun(self) -> None:
        feat = make_features()
        feat["momentum"]["velocity"]["1m"] = 5e-6
        feat["momentum"]["acceleration"]["1m"] = 2e-7
        eng1 = ClassifierEngine(symbols=("BTCUSDT",))
        eng2 = ClassifierEngine(symbols=("BTCUSDT",))
        a = eng1.evaluate({"BTCUSDT": feat}, 1_000_000)[0]
        b = eng2.evaluate({"BTCUSDT": feat}, 1_000_000)[0]
        self.assertEqual(dict(a), dict(b))


class SerializationTest(unittest.TestCase):
    def test_record_is_json_serializable(self) -> None:
        eng, out = engine_with({"BTCUSDT": make_features()})
        blob = json.dumps(out[0])
        back = json.loads(blob)
        self.assertEqual(back["state"], out[0]["state"])
        self.assertEqual(back["rules_version"], RULES_VERSION)
        for state in {r["state"] for r in out}:
            self.assertIn(state, STATES)


if __name__ == "__main__":
    unittest.main()
