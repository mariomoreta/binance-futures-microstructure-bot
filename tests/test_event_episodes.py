"""Versioned funding-episode grouping (v1): descriptive, never a signal.

Uses fixtures plus the retained 245-record copy
(tests/fixtures/funding_245_obs10m.json: frozen extraction of the
complete probe-20261015T230630Z funding records, 245/245 fields
present at freeze time). Originals are never mutated.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import event_episodes as ee

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "funding_245_obs10m.json"


def _ev(ts, symbol, rate, samples=None):
    return {"timestamp": ts, "symbol": symbol, "funding_rate": rate,
            "history_samples": samples}


class GroupingRuleTest(unittest.TestCase):
    def test_repetitions_group_symbols_stay_separate(self) -> None:
        events = [_ev("2026-10-16T00:00:0%dZ" % i, "BTCUSDT", 5e-05, 100 + i)
                  for i in range(3)]
        events += [_ev("2026-10-16T00:00:0%dZ" % i, "SOLUSDT", 5e-05, 100 + i)
                   for i in range(3)]
        out = ee.group_funding_episodes(events)
        self.assertEqual(out["grouping_version"], "v1")
        self.assertEqual(len(out["episodes"]), 2)
        self.assertEqual([e["repetitions"] for e in out["episodes"]], [3, 3])
        self.assertEqual(out["episodes"][0]["symbol"], "BTCUSDT")

    def test_new_rate_gap_and_edges_open_new_episodes(self) -> None:
        events = [
            _ev("2026-10-16T00:00:01Z", "BTCUSDT", 5e-05, 100),
            _ev("2026-10-16T00:00:02Z", "BTCUSDT", 5e-05, 101),
            _ev("2026-10-16T00:00:03Z", "BTCUSDT", 6e-05, 102),
            _ev("2026-10-16T00:00:30Z", "BTCUSDT", 6e-05, 103),
        ]
        out = ee.group_funding_episodes(events)
        self.assertEqual(len(out["episodes"]), 3)
        reasons = [(e["open_reason"], e["close_reason"]) for e in out["episodes"]]
        self.assertEqual(reasons[0], ("first-event", "superseded"))
        self.assertEqual(reasons[1][0], "new-rate")
        self.assertEqual(reasons[2], ("gap-exceeded", "end-of-evidence"))
        self.assertEqual(out["episodes"][2]["duration_s"], 0.0)

    def test_temporal_order_duplicates_and_insufficient(self) -> None:
        base = "2026-10-16T00:00:0%dZ"
        events = [
            _ev(base % 3, "BTCUSDT", 5e-05, 102),
            _ev(base % 1, "BTCUSDT", 5e-05, 100),
            _ev(base % 2, "BTCUSDT", 5e-05, 101),
            _ev(base % 2, "BTCUSDT", 5e-05, 101),
            {"timestamp": "bad", "symbol": "BTCUSDT", "funding_rate": 5e-05},
            {"symbol": "BTCUSDT"},
            "not-a-record",
        ]
        before = copy.deepcopy(events)
        out = ee.group_funding_episodes(events)
        self.assertEqual(events, before)
        self.assertEqual(len(out["episodes"]), 1)
        ep = out["episodes"][0]
        self.assertEqual(ep["repetitions"], 4)
        self.assertEqual(ep["duplicate_records"], 1)
        self.assertEqual(out["skipped"], 3)
        self.assertEqual(ep["duration_s"], 2.0)
        self.assertEqual(ep["event_indexes"], [1, 2, 3, 0])

    def test_originals_preserved_and_documented(self) -> None:
        events = [_ev("2026-10-16T00:00:01Z", "BTCUSDT", 5e-05, 100)]
        before = copy.deepcopy(events)
        out = ee.group_funding_episodes(events)
        self.assertEqual(events, before)
        ep = out["episodes"][0]
        for key in ("grouping_version", "episode_id", "event_type", "symbol",
                    "funding_rate", "repetitions", "first_observed_at",
                    "last_observed_at", "duration_s", "open_reason",
                    "close_reason", "event_indexes"):
            self.assertIn(key, ep)


class Retained245RegressionTest(unittest.TestCase):
    def test_frozen_copy_groups_245_into_documented_shape(self) -> None:
        events = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(events), 245)
        out = ee.group_funding_episodes(events)
        self.assertEqual(out["skipped"], 0)
        eps = out["episodes"]
        self.assertEqual(len(eps), 13)
        self.assertEqual(sum(e["repetitions"] for e in eps), 245)
        by_symbol: dict = {}
        for e in eps:
            by_symbol.setdefault(e["symbol"], []).append(e)
        self.assertEqual({k: len(v) for k, v in by_symbol.items()},
                         {"BTCUSDT": 6, "ETHUSDT": 1, "SOLUSDT": 6})
        self.assertEqual([e["repetitions"] for e in by_symbol["BTCUSDT"]],
                         [9, 12, 19, 22, 25, 31])
        self.assertEqual(by_symbol["ETHUSDT"][0]["repetitions"], 9)
        # Episodes are grouped sequences, never independent samples: every
        # repetition shares its episode rate and contiguous timing.
        for e in eps:
            self.assertGreater(e["repetitions"], 0)
            self.assertIsNotNone(e["close_reason"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
