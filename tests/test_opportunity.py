"""P1-13A research opportunity / setup engine v0 tests.

Deterministic fixtures only: no network, no wall-clock dependence (fixed
epochs), no lookahead. Covers every setup family x direction, eligibility
gates, lifecycle, ranking, persistence/migration, classifier preservation,
resource budgets, and observe-only safety.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe.classifier import (
    RULES_VERSION as CLASSIFIER_VERSION,
    STATES as CLASSIFIER_STATES,
    classify_symbol,
)
from microstructure_probe.opportunity import (
    FAMILIES,
    FAMILY_EXHAUSTION_WATCH,
    FAMILY_EXTREME_MOVE_RESEARCH,
    FAMILY_IGNITION_WATCH,
    FAMILY_MOMENTUM_CONTINUATION,
    FAMILY_REVERSAL_WATCH,
    LIFECYCLES,
    OPPORTUNITY_RULES_VERSION,
    OpportunityEngine,
    evaluate_symbol,
    historical_reference,
    normalize_symbol,
    rank_candidates,
)
from microstructure_probe.persistence import PersistenceStore

T0 = 1_700_000_100_000  # fixed observation epoch (ms)


def make_classification(state="EXPANSION", direction="UP",
                        observed_at_ms=T0 - 30_000,
                        version=CLASSIFIER_VERSION, **over):
    base = {
        "symbol": "BTCUSDT",
        "state": state,
        "direction": direction,
        "observed_at_ms": observed_at_ms,
        "features_used": ["velocity_1m(1/s)", "flow_signed_delta_1m(USDT)"],
        "evidence_for": ["velocity_1m 3.000e-06/s sustained",
                         "flow agrees (ratio +0.50)"],
        "evidence_against": [],
        "missing_features": [],
        "validity": {"sufficient_data": True, "fresh": True},
        "rules_version": version,
        "transition": {"previous_state": "IGNITION",
                       "previous_direction": "UP", "changed": True,
                       "state_since_ms": observed_at_ms,
                       "duration_ms": 0, "reasons": ["expansion confirmed"]},
    }
    base.update(over)
    return base


def make_features(price_age_ms=5_000, ret15m=0.004, ret1h=0.005,
                  vel1m=3e-6, acc1m=1e-7, flow_ratio=0.5,
                  flow_delta=500_000.0, flow_notional=2_000_000.0,
                  vol_z=2.5, expansion=1.8, range_pos=0.6,
                  breakout="ABOVE_PRIOR_RANGE", realized_vol=0.003,
                  imbalance=0.2, oi_delta=50.0):
    return {
        "price": {"current_price": 100.0, "sample_age_ms": price_age_ms},
        "current_price": 100.0,
        "sample_age_ms": price_age_ms,
        "returns": {"returns": {"1m": 0.0004, "15m": ret15m, "1h": ret1h}},
        "momentum": {"velocity": {"1m": vel1m, "5m": 1e-7},
                     "acceleration": {"1m": acc1m}},
        "flow": {"horizons": {"1m": {"signed_delta": flow_delta,
                                     "delta_ratio": flow_ratio,
                                     "notional": flow_notional}},
                 "baselines": {"1m": {"z_score": vol_z}}},
        "book": {"imbalance_notional": imbalance},
        "oi": {"horizons": {"1m": {"delta": oi_delta}}},
        "structure": {
            "ranges": {"15m": {"expansion_ratio": expansion,
                               "range_position": range_pos}},
            "structure": {"breakout_state": breakout},
            "volatility": {"15m": {"realized_vol": realized_vol}}},
    }


def make_bundle(state="EXPANSION", direction="UP", tier="CORE",
                subscribed=True, live=True, degraded=False,
                classification=None, features=None, **over):
    bundle = {
        "tier": tier,
        "subscribed": subscribed,
        "live": live,
        "market": "BTCUSDT USDT-M PERP",
        "classification": classification if classification is not None
        else make_classification(state, direction),
        "features": features if features is not None
        else make_features(),
        "transport": {"degraded": degraded,
                      "reason": "stale mandatory stream" if degraded
                      else "ok"},
    }
    bundle.update(over)
    return bundle


def down_bundle(family_state="EXPANSION", **over):
    """Mirror-image bearish bundle (negative velocity/returns/flow)."""
    cls = make_classification(family_state, "DOWN")
    feat = make_features(ret15m=-0.004, ret1h=-0.005, vel1m=-3e-6,
                         acc1m=-1e-7, flow_ratio=-0.5,
                         flow_delta=-500_000.0, imbalance=-0.2,
                         oi_delta=-50.0, range_pos=0.4,
                         breakout="BELOW_PRIOR_RANGE")
    return make_bundle(state=family_state, direction="DOWN",
                       classification=cls, features=feat, **over)


def bundle_at(as_of_ms, **over):
    """Time-consistent bundle: classification as-of 30s before the eval."""
    cls = over.pop("classification", None)
    if cls is None:
        cls = make_classification(over.get("state", "EXPANSION"),
                                  over.get("direction", "UP"),
                                  observed_at_ms=as_of_ms - 30_000)
    return make_bundle(classification=cls, **over)


def _temp_store(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="opp_test_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    store = PersistenceStore(db_path=tmp / "opp.db")
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


class FamilyTest(unittest.TestCase):
    def test_five_stable_families(self) -> None:
        self.assertEqual(len(FAMILIES), 5)
        for family in (FAMILY_MOMENTUM_CONTINUATION, FAMILY_IGNITION_WATCH,
                       FAMILY_EXHAUSTION_WATCH, FAMILY_REVERSAL_WATCH,
                       FAMILY_EXTREME_MOVE_RESEARCH):
            self.assertIn(family, FAMILIES)

    def test_momentum_continuation_up(self) -> None:
        matched, _ = evaluate_symbol(
            "BTCUSDT", make_bundle("EXPANSION", "UP"), T0)
        families = [c["setup_family"] for c in matched]
        self.assertIn(FAMILY_MOMENTUM_CONTINUATION, families)
        cand = next(c for c in matched
                    if c["setup_family"] == FAMILY_MOMENTUM_CONTINUATION)
        self.assertEqual(cand["direction"], "UP")
        self.assertEqual(cand["eligibility"], "ELIGIBLE")
        self.assertEqual(cand["rule_version"], OPPORTUNITY_RULES_VERSION)
        self.assertEqual(cand["market_state"], "EXPANSION")
        self.assertEqual(cand["classifier_version"], CLASSIFIER_VERSION)

    def test_momentum_continuation_down(self) -> None:
        matched, _ = evaluate_symbol("BTCUSDT", down_bundle(), T0)
        cand = next(c for c in matched
                    if c["setup_family"] == FAMILY_MOMENTUM_CONTINUATION)
        self.assertEqual(cand["direction"], "DOWN")

    def test_ignition_watch_up_and_down(self) -> None:
        matched, _ = evaluate_symbol(
            "BTCUSDT", make_bundle("IGNITION", "UP"), T0)
        self.assertIn(FAMILY_IGNITION_WATCH,
                      [c["setup_family"] for c in matched])
        matched, _ = evaluate_symbol(
            "BTCUSDT", down_bundle("IGNITION"), T0)
        self.assertIn(FAMILY_IGNITION_WATCH,
                      [c["setup_family"] for c in matched])

    def test_exhaustion_watch_up_and_down(self) -> None:
        matched, _ = evaluate_symbol(
            "BTCUSDT", make_bundle("EXHAUSTION", "UP"), T0)
        self.assertIn(FAMILY_EXHAUSTION_WATCH,
                      [c["setup_family"] for c in matched])
        matched, _ = evaluate_symbol(
            "BTCUSDT", down_bundle("EXHAUSTION"), T0)
        self.assertIn(FAMILY_EXHAUSTION_WATCH,
                      [c["setup_family"] for c in matched])

    def test_reversal_watch_requires_confirmation(self) -> None:
        # No confirmation anywhere -> rejected, not matched.
        cls = make_classification("REVERSAL", "UP", evidence_for=[
            "velocity sign flipped DOWN -> UP"])
        feat = make_features(flow_ratio=-0.5, breakout="INSIDE_PRIOR_RANGE")
        matched, rejected = evaluate_symbol(
            "BTCUSDT",
            make_bundle("REVERSAL", "UP", classification=cls,
                        features=feat), T0)
        self.assertNotIn(FAMILY_REVERSAL_WATCH,
                         [c["setup_family"] for c in matched])
        self.assertTrue(any(r["setup_family"] == FAMILY_REVERSAL_WATCH
                            for r in rejected))
        # Classifier confirmation present -> matched.
        cls2 = make_classification("REVERSAL", "UP", evidence_for=[
            "velocity sign flipped DOWN -> UP",
            "structure confirms (ABOVE_PRIOR_RANGE)",
            "reversal confirmed (2/2)"])
        matched, _ = evaluate_symbol(
            "BTCUSDT",
            make_bundle("REVERSAL", "UP", classification=cls2,
                        features=make_features()), T0)
        cand = next(c for c in matched
                    if c["setup_family"] == FAMILY_REVERSAL_WATCH)
        self.assertEqual(cand["direction"], "UP")

    def test_reversal_watch_down_with_flow_structure(self) -> None:
        cls = make_classification("REVERSAL", "DOWN", evidence_for=[
            "velocity sign flipped UP -> DOWN"])
        feat = make_features(ret15m=-0.004, vel1m=-3e-6, flow_ratio=-0.5,
                             flow_delta=-500_000.0,
                             breakout="BELOW_PRIOR_RANGE")
        matched, _ = evaluate_symbol(
            "BTCUSDT",
            make_bundle("REVERSAL", "DOWN", classification=cls,
                        features=feat), T0)
        cand = next(c for c in matched
                    if c["setup_family"] == FAMILY_REVERSAL_WATCH)
        self.assertEqual(cand["direction"], "DOWN")

    def test_extreme_move_up_and_down_is_research_not_fade(self) -> None:
        matched, _ = evaluate_symbol(
            "BTCUSDT",
            make_bundle("EXPANSION", "UP",
                        features=make_features(ret15m=0.012, ret1h=0.015)),
            T0)
        cand = next(c for c in matched
                    if c["setup_family"] == FAMILY_EXTREME_MOVE_RESEARCH)
        self.assertEqual(cand["direction"], "UP")
        self.assertIn("study", cand["eligibility_reason"].lower())
        matched, _ = evaluate_symbol(
            "BTCUSDT", down_bundle(),
            T0)  # 0.004 < extreme gate: no extreme candidate
        self.assertNotIn(FAMILY_EXTREME_MOVE_RESEARCH,
                         [c["setup_family"] for c in matched])
        feat = make_features(ret15m=-0.012, ret1h=-0.015, vel1m=-3e-6,
                             flow_ratio=-0.5, flow_delta=-500_000.0)
        matched, _ = evaluate_symbol(
            "BTCUSDT",
            make_bundle("EXPANSION", "DOWN",
                        classification=make_classification(
                            "EXPANSION", "DOWN"),
                        features=feat), T0)
        cand = next(c for c in matched
                    if c["setup_family"] == FAMILY_EXTREME_MOVE_RESEARCH)
        self.assertEqual(cand["direction"], "DOWN")

    def test_small_move_matches_no_family(self) -> None:
        cls = make_classification("NORMAL", "NONE")
        matched, _ = evaluate_symbol(
            "BTCUSDT",
            make_bundle("NORMAL", "NONE", classification=cls,
                        features=make_features(
                            ret15m=0.0001, ret1h=0.0002, vel1m=1e-7,
                            flow_ratio=0.02)), T0)
        self.assertEqual(matched, [])


class EligibilityGatesTest(unittest.TestCase):
    def test_discovery_only_excluded(self) -> None:
        _m, rejected = evaluate_symbol(
            "BTCUSDT", make_bundle(tier="DISCOVERY", subscribed=False,
                                   live=False), T0)
        self.assertEqual([c for c in _m], [])
        self.assertTrue(any(r["eligibility"] == "INELIGIBLE"
                            and "discovery-only" in r["eligibility_reason"]
                            for r in rejected))

    def test_hot_live_is_eligible_hot_discovery_is_not(self) -> None:
        matched, _ = evaluate_symbol(
            "DOGEUSDT",
            make_bundle(tier="HOT", subscribed=True, live=True,
                        classification=make_classification(
                            "EXPANSION", "UP", observed_at_ms=T0 - 30_000)),
            T0)
        # Symbol identity differs from bundle market label but must parse.
        self.assertTrue(all(c["symbol"] == "DOGEUSDT" for c in matched))
        _m2, rejected = evaluate_symbol(
            "DOGEUSDT", make_bundle(tier="HOT", subscribed=True,
                                    live=False), T0)
        self.assertEqual(_m2, [])
        self.assertTrue(rejected)

    def test_missing_classification_insufficient(self) -> None:
        bundle = make_bundle()
        bundle["classification"] = {}
        _m, rejected = evaluate_symbol("BTCUSDT", bundle, T0)
        self.assertEqual(_m, [])
        self.assertTrue(any(r["eligibility"] == "INSUFFICIENT_DATA"
                            for r in rejected))

    def test_stale_price_insufficient(self) -> None:
        _m, rejected = evaluate_symbol(
            "BTCUSDT",
            make_bundle(features=make_features(price_age_ms=600_000)), T0)
        self.assertEqual(_m, [])
        self.assertTrue(any("Stale" in r["eligibility_reason"]
                            or "stale" in r["eligibility_reason"]
                            for r in rejected))

    def test_incompatible_state_timestamp_rejected(self) -> None:
        cls = make_classification(observed_at_ms=T0 - 600_000)
        _m, rejected = evaluate_symbol(
            "BTCUSDT", make_bundle(classification=cls), T0)
        self.assertEqual(_m, [])
        self.assertTrue(any("incompatible" in r["eligibility_reason"]
                            for r in rejected))

    def test_unknown_state_insufficient(self) -> None:
        cls = make_classification("UNKNOWN", "UNKNOWN")
        _m, rejected = evaluate_symbol(
            "BTCUSDT", make_bundle(classification=cls), T0)
        self.assertEqual(_m, [])
        self.assertTrue(rejected)

    def test_degraded_transport_insufficient(self) -> None:
        _m, rejected = evaluate_symbol(
            "BTCUSDT", make_bundle(degraded=True), T0)
        self.assertEqual(_m, [])
        self.assertTrue(any("degradation" in r["eligibility_reason"]
                            for r in rejected))

    def test_malformed_symbol_rejected(self) -> None:
        _m, rejected = evaluate_symbol("btc/usdt", make_bundle(), T0)
        self.assertEqual(_m, [])
        self.assertTrue(any(r["eligibility"] == "INELIGIBLE"
                            for r in rejected))
        self.assertIsNone(normalize_symbol("btc/usdt"))
        self.assertEqual(normalize_symbol("btcusdt"), "BTCUSDT")

    def test_contradictory_flow_blocks_momentum_but_kept_as_evidence(self) -> None:
        cls = make_classification(evidence_against=[
            "flow contradicts (ratio -0.50 vs UP)"])
        feat = make_features(flow_ratio=-0.5, flow_delta=-500_000.0)
        matched, rejected = evaluate_symbol(
            "BTCUSDT",
            make_bundle(classification=cls, features=feat), T0)
        self.assertNotIn(FAMILY_MOMENTUM_CONTINUATION,
                         [c["setup_family"] for c in matched])
        self.assertTrue(any("corroboration" in r["eligibility_reason"]
                            for r in rejected))

    def test_no_lookahead_timestamps(self) -> None:
        matched, _ = evaluate_symbol(
            "BTCUSDT", make_bundle(), T0)
        for cand in matched:
            self.assertLessEqual(cand["observed_at_ms"], T0)
            self.assertLessEqual(
                cand["classification_observed_at_ms"], T0)


class LifecycleTest(unittest.TestCase):
    def _engine(self, **rules):
        base = {"watching_evals": 2, "active_research_evals": 3,
                "cooldown_ms": 60_000, "ttl_ms": 86_400_000,
                "max_candidates": 200}
        base.update(rules)
        from microstructure_probe.opportunity import RULES
        merged = dict(RULES)
        merged.update(base)
        return OpportunityEngine(rules=merged)

    def test_detected_watching_active_research(self) -> None:
        eng = self._engine()
        bundles = {"BTCUSDT": make_bundle()}
        matched, _ = eng.evaluate(bundles, T0)
        key = "MOMENTUM_CONTINUATION:BTCUSDT:UP"
        first = next(c for c in matched if c["candidate_key"] == key)
        self.assertEqual(first["lifecycle"], "DETECTED")
        matched, _ = eng.evaluate(bundles, T0 + 30_000)
        second = next(c for c in matched if c["candidate_key"] == key)
        self.assertEqual(second["lifecycle"], "WATCHING")
        self.assertEqual(second["evals_in_lifecycle"], 2)
        matched, _ = eng.evaluate(bundles, T0 + 60_000)
        third = next(c for c in matched if c["candidate_key"] == key)
        self.assertEqual(third["lifecycle"], "ACTIVE_RESEARCH")
        self.assertIn(third["lifecycle"], LIFECYCLES)

    def test_dedup_same_setup_not_counted_twice(self) -> None:
        eng = self._engine()
        bundles = {"BTCUSDT": make_bundle()}
        eng.evaluate(bundles, T0)
        eng.evaluate(bundles, T0 + 30_000)
        self.assertEqual(len(eng._memory), len(
            {k for k in eng._memory}))
        keys = [k for k in eng._memory
                if k.startswith("MOMENTUM_CONTINUATION:BTCUSDT")]
        self.assertEqual(len(keys), 1)
        self.assertEqual(eng.detected, 2)  # two evals, one tracked setup

    def test_invalidation_on_rule_loss(self) -> None:
        eng = self._engine()
        eng.evaluate({"BTCUSDT": make_bundle()}, T0)
        quiet = make_bundle(
            "NORMAL", "NONE",
            classification=make_classification("NORMAL", "NONE"),
            features=make_features(ret15m=0.0001, vel1m=1e-7,
                                   flow_ratio=0.02))
        matched, _ = eng.evaluate({"BTCUSDT": quiet}, T0 + 30_000)
        self.assertNotIn("MOMENTUM_CONTINUATION:BTCUSDT:UP",
                         [c["candidate_key"] for c in matched])
        mem = eng._memory["MOMENTUM_CONTINUATION:BTCUSDT:UP"]
        self.assertEqual(mem["lifecycle"], "INVALIDATED")
        closed = eng.drain_closed_events()
        self.assertTrue(any(e["transition"] == "INVALIDATED"
                            for e in closed))
        self.assertEqual(eng.drain_closed_events(), [])

    def test_cooldown_blocks_immediate_redetect(self) -> None:
        eng = self._engine()
        eng.evaluate({"BTCUSDT": bundle_at(T0)}, T0)

        def quiet_at(t):
            return make_bundle(
                "NORMAL", "NONE",
                classification=make_classification(
                    "NORMAL", "NONE", observed_at_ms=t - 30_000),
                features=make_features(ret15m=0.0001, vel1m=1e-7,
                                       flow_ratio=0.02))
        eng.evaluate({"BTCUSDT": quiet_at(T0 + 30_000)}, T0 + 30_000)
        matched, rejected = eng.evaluate(
            {"BTCUSDT": bundle_at(T0 + 40_000)}, T0 + 40_000)
        self.assertNotIn("MOMENTUM_CONTINUATION:BTCUSDT:UP",
                         [c["candidate_key"] for c in matched])
        self.assertTrue(any("cooldown" in r["lifecycle_reason"]
                            for r in rejected))
        # After cooldown elapses the same setup may detect again.
        matched, _ = eng.evaluate(
            {"BTCUSDT": bundle_at(T0 + 120_000)}, T0 + 120_000)
        cand = next(c for c in matched
                    if c["candidate_key"]
                    == "MOMENTUM_CONTINUATION:BTCUSDT:UP")
        self.assertEqual(cand["lifecycle"], "DETECTED")

    def test_expiration_after_ttl(self) -> None:
        eng = self._engine(ttl_ms=1_000)
        eng.evaluate({"BTCUSDT": bundle_at(T0)}, T0)
        matched, _ = eng.evaluate(
            {"BTCUSDT": bundle_at(T0 + 2_000)}, T0 + 2_000)
        cand = next(c for c in matched
                    if c["candidate_key"]
                    == "MOMENTUM_CONTINUATION:BTCUSDT:UP")
        self.assertEqual(cand["lifecycle"], "EXPIRED")

    def test_forget_on_hot_demotion_bars_stale_reuse(self) -> None:
        eng = self._engine()
        eng.evaluate({"BTCUSDT": make_bundle(tier="HOT")}, T0)
        self.assertTrue(eng.forget("BTCUSDT", "hot_demotion", T0))
        mem = eng._memory["MOMENTUM_CONTINUATION:BTCUSDT:UP"]
        self.assertEqual(mem["lifecycle"], "INVALIDATED")
        self.assertIn("hot_demotion", mem["lifecycle_reason"])
        closed = eng.drain_closed_events()
        self.assertTrue(any("hot_demotion" in e["reason"] for e in closed))
        self.assertFalse(eng.forget("UNKNOWNXXX", "hot_demotion", T0))

    def test_repromotion_starts_cold(self) -> None:
        eng = self._engine(cooldown_ms=0)
        eng.evaluate({"BTCUSDT": bundle_at(T0, tier="HOT")}, T0)
        eng.evaluate({"BTCUSDT": bundle_at(T0 + 30_000, tier="HOT")},
                     T0 + 30_000)
        eng.forget("BTCUSDT", "hot_demotion", T0 + 60_000)
        matched, _ = eng.evaluate(
            {"BTCUSDT": bundle_at(T0 + 90_000, tier="HOT")}, T0 + 90_000)
        cand = next(c for c in matched
                    if c["candidate_key"]
                    == "MOMENTUM_CONTINUATION:BTCUSDT:UP")
        self.assertEqual(cand["lifecycle"], "DETECTED")
        self.assertEqual(cand["evals_in_lifecycle"], 1)


class RankingTest(unittest.TestCase):
    def test_components_exposed_and_hypothesis_labeled(self) -> None:
        matched, _ = evaluate_symbol(
            "BTCUSDT", make_bundle(), T0)
        for cand in matched:
            rank = cand["ranking"]
            self.assertIn("score", rank)
            self.assertTrue(rank["weights_hypothesis"])
            for comp in ("movement", "corroboration", "activity",
                         "freshness_s", "completeness", "state_compat",
                         "counterevidence"):
                self.assertIn(comp, rank["components"])
            self.assertIn("NOT expected profit", rank["interpretation"])

    def test_stronger_move_outranks_weaker(self) -> None:
        weak = make_bundle(features=make_features(
            ret15m=0.0035, ret1h=0.004, vel1m=2.5e-6, flow_ratio=0.35,
            flow_delta=350_000.0))
        strong = make_bundle(features=make_features(
            ret15m=0.009, ret1h=0.012, vel1m=9e-6, flow_ratio=0.8,
            flow_delta=900_000.0))
        weak_m, _ = evaluate_symbol("BTCUSDT", weak, T0)
        strong_m, _ = evaluate_symbol("BTCUSDT", strong, T0)
        weak_c = next(c for c in weak_m
                      if c["setup_family"] == FAMILY_MOMENTUM_CONTINUATION)
        strong_c = next(c for c in strong_m
                        if c["setup_family"] == FAMILY_MOMENTUM_CONTINUATION)
        self.assertGreater(strong_c["ranking"]["score"],
                           weak_c["ranking"]["score"])

    def test_counterevidence_reduces_priority(self) -> None:
        clean = make_bundle()
        noisy = make_bundle(classification=make_classification(
            evidence_against=["flow contradicts (ratio +0.10 vs UP)",
                              "book imbalance opposes (0.20)",
                              "OI diverges from price move"]))
        clean_m, _ = evaluate_symbol("BTCUSDT", clean, T0)
        noisy_m, _ = evaluate_symbol("BTCUSDT", noisy, T0)
        clean_c = next(c for c in clean_m
                       if c["setup_family"] == FAMILY_MOMENTUM_CONTINUATION)
        noisy_c = next(c for c in noisy_m
                       if c["setup_family"] == FAMILY_MOMENTUM_CONTINUATION)
        self.assertGreater(clean_c["ranking"]["score"],
                           noisy_c["ranking"]["score"])

    def test_rank_candidates_sorts_descending(self) -> None:
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        ordered = rank_candidates(list(reversed(matched)))
        scores = [c["ranking"]["score"] for c in ordered]
        self.assertEqual(scores, sorted(scores, reverse=True))


class HistoricalEvidenceTest(unittest.TestCase):
    def test_default_is_insufficient(self) -> None:
        ref = historical_reference(FAMILY_MOMENTUM_CONTINUATION)
        self.assertEqual(ref["status"], "INSUFFICIENT_HISTORICAL_EVIDENCE")

    def test_candidates_carry_insufficient_by_default(self) -> None:
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        for cand in matched:
            self.assertEqual(cand["historical_reference"]["status"],
                             "INSUFFICIENT_HISTORICAL_EVIDENCE")

    def test_explicit_mapping_is_honored(self) -> None:
        eng = OpportunityEngine(historical_lookup=lambda fam: {
            "study_id": "P1-11C/EXTENDED_GAINER/v1",
            "note": "explicit comparable-timestamp mapping for test"})
        matched, _ = eng.evaluate({"BTCUSDT": make_bundle()}, T0)
        refs = [c["historical_reference"] for c in matched]
        self.assertTrue(any(r["status"] == "MAPPED" for r in refs))

    def test_failing_lookup_degrades_honestly(self) -> None:
        def boom(_fam):
            raise RuntimeError("store offline")
        ref = historical_reference(FAMILY_MOMENTUM_CONTINUATION,
                                   lookup=boom)
        self.assertEqual(ref["status"], "INSUFFICIENT_HISTORICAL_EVIDENCE")


class NoFabricationTest(unittest.TestCase):
    FORBIDDEN_KEYS = ("confidence", "probability", "win_rate", "winrate",
                      "expected_return", "expectancy", "entry", "stop_loss",
                      "take_profit", "position_size", "leverage")
    FORBIDDEN_TEXT = ("LONG", "SHORT", "70% probability", "win rate",
                      "expected return")

    def _all_text(self, records) -> str:
        return json.dumps(records, sort_keys=True, default=str)

    def test_no_confidence_or_predictions(self) -> None:
        import re
        eng = OpportunityEngine()
        matched, rejected = eng.evaluate({"BTCUSDT": make_bundle(),
                                              "ETHUSDT": down_bundle()}, T0)
        blob = self._all_text(matched + rejected)
        for token in ("confidence", "win_rate", "win rate",
                      "expected_return", "expected return", "expectancy",
                      "MFE", "MAE"):
            self.assertNotIn(token, blob)
        # No fabricated percentages anywhere (the ranking disclaimer
        # mentions win probability in words only, never as a number).
        self.assertIsNone(re.search(r"\d+%", blob))
        # No "probability of X%" pattern — honest disclaimers use
        # "NOT ... probability" without a numeric claim.
        self.assertIsNone(re.search(r"probability of \d+%", blob, re.I))

    def test_no_entry_exit_generation(self) -> None:
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        for cand in matched:
            for key in self.FORBIDDEN_KEYS:
                self.assertNotIn(key, cand)
        blob = self._all_text(matched)
        for token in self.FORBIDDEN_TEXT:
            self.assertNotIn(token, blob)

    def test_observe_only_source_surface(self) -> None:
        import microstructure_probe.opportunity as opp_mod
        src = Path(opp_mod.__file__).read_text(encoding="utf-8")
        for token in ("placeOrder", "place_order", "cancelOrder",
                      "setLeverage", "leverage", "api_key", "apiKey",
                      "secret", "private_key", "withdraw"):
            self.assertNotIn(token, src)
        self.assertIn("never orders", src)

    def test_taker_ratio_is_not_a_probability(self) -> None:
        import re
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        blob = self._all_text(matched)
        # No "X% probability" fabrication; honest disclaimers
        # say "NOT ... probability" without a numeric claim.
        self.assertIsNone(re.search(r"\d+%.*probability", blob, re.I))
        self.assertIsNone(re.search(r"probability.*\d+%", blob, re.I))


class PersistenceMigrationTest(unittest.TestCase):
    def test_store_and_retrieve_candidates(self) -> None:
        store = _temp_store(self)
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        store.store_opportunity_candidates(matched)
        rows = store.latest_opportunity_candidates()
        self.assertEqual(len(rows), len(matched))
        keys = {r["candidate_key"] for r in rows}
        self.assertEqual(len(keys), len(matched))

    def test_rejections_without_keys_are_never_stored(self) -> None:
        store = _temp_store(self)
        _m, rejected = evaluate_symbol(
            "BTCUSDT", make_bundle(tier="DISCOVERY", subscribed=False,
                                   live=False), T0)
        store.store_opportunity_candidates(rejected)
        self.assertEqual(store.latest_opportunity_candidates(), [])

    def test_replace_per_key_bounds_rows(self) -> None:
        store = _temp_store(self)
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        store.store_opportunity_candidates(matched)
        store.store_opportunity_candidates(matched)
        self.assertEqual(len(store.latest_opportunity_candidates()),
                         len(matched))

    def test_event_log_bounded(self) -> None:
        store = _temp_store(self)
        for i in range(520):
            store.log_opportunity_event("K%d" % (i % 7), "BTCUSDT",
                                        FAMILY_MOMENTUM_CONTINUATION,
                                        "-> DETECTED", "reason %d" % i)
        events = store.opportunity_events(limit=1000)
        self.assertLessEqual(len(events), 500)
        self.assertEqual(len(events), 500)

    def test_v7_database_migrates_to_v9_preserving_state_rows(self) -> None:
        store = _temp_store(self)
        store.store_state_features([{"symbol": "BTCUSDT", "state": "NORMAL",
                                     "direction": "UP",
                                     "observed_at_ms": T0,
                                     "rules_version": CLASSIFIER_VERSION}])
        store.close()
        conn = sqlite3.connect(str(store.db_path))
        conn.execute("DROP TABLE opportunity_candidates")
        conn.execute("DROP TABLE opportunity_events")
        conn.execute("INSERT OR REPLACE INTO persistence_meta (key, value)"
                     " VALUES ('schema_version', '7')")
        conn.commit()
        conn.close()
        reopened = PersistenceStore(db_path=store.db_path)
        self.addCleanup(reopened.close)
        reopened.init_db()
        with reopened._get_cursor() as cursor:
            cursor.execute("SELECT value FROM persistence_meta"
                           " WHERE key='schema_version'")
            self.assertEqual(int(cursor.fetchone()[0]), 9)
            for table in ("state_features", "state_transitions",
                          "opportunity_candidates", "opportunity_events"):
                cursor.execute("SELECT name FROM sqlite_master"
                               " WHERE type='table' AND name=?", (table,))
                self.assertIsNotNone(cursor.fetchone(), table)
        self.assertEqual(len(reopened.latest_state_features()), 1)
        # New tables are writable after migration.
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        reopened.store_opportunity_candidates(matched)
        self.assertEqual(len(reopened.latest_opportunity_candidates()),
                         len(matched))

    def test_storage_info_includes_opportunity_tables(self) -> None:
        store = _temp_store(self)
        info = store.storage_info()
        self.assertIn("opportunity_candidates", info["rows"])
        self.assertIn("opportunity_events", info["rows"])


class ClassifierPreservationTest(unittest.TestCase):
    def _features(self):
        return {
            "subscribed": True, "live": True, "tier": "CORE",
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

    def test_classifier_still_classifies(self) -> None:
        out = classify_symbol("BTCUSDT", self._features(), 1_000_000)
        self.assertIn(out["state"], CLASSIFIER_STATES)
        self.assertEqual(out["rules_version"], CLASSIFIER_VERSION)

    def test_classifier_unknown_paths_intact(self) -> None:
        feat = self._features()
        feat["subscribed"] = False
        out = classify_symbol("BTCUSDT", feat, 1_000_000)
        self.assertEqual(out["state"], "UNKNOWN")

    def test_opportunity_consumes_real_classifier_output(self) -> None:
        from microstructure_probe.classifier import ClassifierEngine
        eng = ClassifierEngine(symbols=("BTCUSDT",))
        recs = eng.evaluate({"BTCUSDT": self._features()}, T0)
        self.assertEqual(len(recs), 1)
        bundle = make_bundle(classification=dict(recs[0]),
                             features=self._features())
        matched, rejected = evaluate_symbol("BTCUSDT", bundle, T0)
        # A quiet NORMAL fixture must not fabricate a deep setup.
        self.assertEqual(recs[0]["state"], "NORMAL")
        self.assertEqual(matched, [])
        self.assertEqual(rejected, [])


class ResourceBudgetTest(unittest.TestCase):
    def test_tracked_candidates_bounded(self) -> None:
        from microstructure_probe.opportunity import RULES
        merged = dict(RULES)
        merged["max_candidates"] = 5
        eng = OpportunityEngine(rules=merged)
        bundles = {}
        for i in range(10):
            sym = "SYM%dUSDT" % i
            bundles[sym] = make_bundle(
                classification=make_classification(
                    "EXPANSION", "UP", observed_at_ms=T0 - 30_000))
            bundles[sym]["market"] = "%s USDT-M PERP" % sym
        matched, _ = eng.evaluate(bundles, T0)
        self.assertLessEqual(len(eng._memory), 5)
        self.assertLessEqual(len(matched), 10)

    def test_evaluation_cost_bounded(self) -> None:
        eng = OpportunityEngine()
        bundles = {}
        for i in range(8):
            sym = "SYM%dUSDT" % i
            bundles[sym] = make_bundle()
            bundles[sym]["market"] = "%s USDT-M PERP" % sym
        start = time.perf_counter()
        eng.evaluate(bundles, T0)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self.assertLess(elapsed_ms, 5000.0)
        eng.note_eval_ms(elapsed_ms)
        self.assertIsNotNone(eng.stats()["last_eval_ms"])


class ProbeIntegrationTest(unittest.TestCase):
    def test_probe_exposes_opportunity_engine(self) -> None:
        from test_detectors import test_config
        from microstructure_probe.probe import MarketProbe
        probe = MarketProbe(test_config())
        self.assertEqual(probe.opportunity().stats()["rules_version"],
                         OPPORTUNITY_RULES_VERSION)

    def test_summary_carries_opportunity_stats(self) -> None:
        from test_detectors import test_config
        from microstructure_probe.probe import MarketProbe
        probe = MarketProbe(test_config())
        summary = probe.build_summary(final=False)
        self.assertIn("opportunities", summary)
        self.assertEqual(
            summary["opportunities"]["rules_version"],
            OPPORTUNITY_RULES_VERSION)

    def test_hot_demotion_path_forgets_opportunities(self) -> None:
        import inspect
        from microstructure_probe import probe as probe_mod
        src = inspect.getsource(
            probe_mod.MarketProbe._sync_hot_subscriptions)
        self.assertIn("_opportunity.forget", src)
        src_log = inspect.getsource(probe_mod.MarketProbe.log_summary)
        self.assertIn("_opportunity.evaluate", src_log)
        self.assertIn("store_opportunity_candidates", src_log)


class DashboardSurfaceTest(unittest.TestCase):
    def test_state_accessors_default_empty(self) -> None:
        from microstructure_probe.dashboard import DashboardState
        store = _temp_store(self)
        state = DashboardState(store)
        self.assertEqual(state.opportunity_candidates(), [])
        self.assertEqual(state.opportunity_events(), [])

    def test_state_accessors_serve_stored_candidates(self) -> None:
        from microstructure_probe.dashboard import DashboardState
        store = _temp_store(self)
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        store.store_opportunity_candidates(matched)
        store.log_opportunity_event(
            matched[0]["candidate_key"], "BTCUSDT",
            matched[0]["setup_family"], "-> DETECTED", "test")
        state = DashboardState(store)
        self.assertEqual(len(state.opportunity_candidates()), len(matched))
        self.assertEqual(len(state.opportunity_events(limit=5)), 1)

    def test_opportunities_page_renders_research_only(self) -> None:
        from microstructure_probe.dashboard import DashboardState
        from microstructure_probe.dashboard_views import render_opportunities
        store = _temp_store(self)
        state = DashboardState(store)
        html_text = render_opportunities(state)
        self.assertIn("RESEARCH ONLY", html_text)
        self.assertIn("NOT A TRADE SIGNAL", html_text)
        self.assertIn("No qualifying setups", html_text)

    def test_opportunities_page_lists_candidate_fields(self) -> None:
        from microstructure_probe.dashboard import DashboardState
        from microstructure_probe.dashboard_views import render_opportunities
        store = _temp_store(self)
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        store.store_opportunity_candidates(matched)
        state = DashboardState(store)
        html_text = render_opportunities(state)
        for token in ("MOMENTUM_CONTINUATION", "BTCUSDT", "UP", "EXPANSION",
                      "DETECTED", "CORE", OPPORTUNITY_RULES_VERSION):
            self.assertIn(token, html_text)
        self.assertNotIn("LONG", html_text)
        self.assertNotIn("SHORT", html_text)

    def test_api_contract_shape(self) -> None:
        from microstructure_probe.dashboard import DashboardState
        store = _temp_store(self)
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        store.store_opportunity_candidates(matched)
        state = DashboardState(store)
        payload = {
            "note": "RESEARCH ONLY — NOT A TRADE SIGNAL.",
            "schema_version": 1,
            "rules_version": OPPORTUNITY_RULES_VERSION,
            "candidates": state.opportunity_candidates(),
            "lifecycle_events": state.opportunity_events(limit=20),
        }
        blob = json.dumps(payload, sort_keys=True, default=str)
        self.assertIn(OPPORTUNITY_RULES_VERSION, blob)
        self.assertNotIn("confidence", blob)


    def test_dashboard_api_exposes_candidates(self) -> None:
        """Live /api/opportunities endpoint returns v0.1.0 candidates."""
        from microstructure_probe.dashboard import DashboardServer
        store = _temp_store(self)
        matched, _ = evaluate_symbol("BTCUSDT", make_bundle(), T0)
        store.store_opportunity_candidates(matched)
        server = DashboardServer(host="127.0.0.1", port=0,
                                     db_path=store.db_path).start()
        self.addCleanup(server.stop)
        url = f"http://127.0.0.1:{server.bound_port()}/api/opportunities"
        with urllib.request.urlopen(url, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        self.assertIsInstance(payload.get("candidates"), list)
        self.assertGreater(len(payload["candidates"]), 0)
        cand = payload["candidates"][0]
        for key in ("candidate_key", "symbol", "setup_family",
                    "lifecycle", "rule_version"):
            self.assertIn(key, cand)
        self.assertEqual(cand["rule_version"], "v0.1.0")
        self.assertIsInstance(cand.get("ranking", {}).get("score"), float)
        blob = json.dumps(payload, sort_keys=True, default=str)
        self.assertNotIn("confidence", blob)
        self.assertNotIn("win_rate", blob)
        import re
        self.assertIsNone(re.search(r"\d+%.*probability", blob, re.I))
        self.assertIsNone(re.search(r"probability.*\d+%", blob, re.I))


if __name__ == "__main__":
    unittest.main()
