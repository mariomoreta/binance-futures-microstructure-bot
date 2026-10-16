"""Prefix-causality + strict-posterior invariance of P1-11C formation.

Synthetic bars only (no DB, no network). Locks the property the V1
audit relies on: decisions knowable at T never depend on data after T.
"""
import unittest

from microstructure_probe.events import (
    default_definition,
    detect_events,
    formation_features,
)


def _bars(n=120, start=1_700_000_000_000, step=900_000, drift=1.0005):
    px = 100.0
    bars = []
    for i in range(n):
        o = px
        c = px * drift
        bars.append({"open_time": start + i * step, "open": o, "high": max(o, c) * 1.001,
                     "low": min(o, c) * 0.999, "close": c,
                     "quote_volume": 1_000_000.0, "taker_buy_quote": 500_000.0})
        px = c
    return bars


class PrefixCausalityTest(unittest.TestCase):
    def test_truncation_preserves_early_detections(self) -> None:
        bars = _bars()
        for fam in ("MOMENTUM_ACCELERATION_UP", "MOMENTUM_ACCELERATION_DOWN",
                    "EXTENDED_GAINER", "EXTENDED_LOSER",
                    "FAILED_HIGH_CANDIDATE", "FAILED_LOW_CANDIDATE"):
            d = default_definition(fam)
            full = detect_events(bars, d, "BTCUSDT", "regular_close", "15m")
            k = len(bars) * 3 // 5
            t_cut = int(bars[k]["open_time"])
            prefix = [b for b in bars if int(b["open_time"]) <= t_cut]
            pre = detect_events(prefix, d, "BTCUSDT", "regular_close", "15m")
            a = sorted((int(e["event_time"]), e["direction"]) for e in full
                       if int(e["event_time"]) <= t_cut)
            b = sorted((int(e["event_time"]), e["direction"]) for e in pre)
            self.assertEqual(a, b, fam)

    def test_strict_posterior_mutation_changes_nothing_early(self) -> None:
        bars = _bars()
        k = len(bars) * 3 // 5
        t_cut = int(bars[k]["open_time"])
        mutated = [dict(b) for b in bars]
        for b in mutated:
            if int(b["open_time"]) > t_cut:
                b["close"] = b["close"] * 1.5
                b["high"] = b["high"] * 1.5
                b["low"] = b["low"] * 1.5
        for fam in ("MOMENTUM_ACCELERATION_UP", "EXTENDED_GAINER",
                    "FAILED_HIGH_CANDIDATE"):
            d = default_definition(fam)
            a = detect_events(bars, d, "BTCUSDT", "regular_close", "15m")
            b = detect_events(mutated, d, "BTCUSDT", "regular_close", "15m")
            ka = sorted((int(e["event_time"]), e["direction"]) for e in a
                        if int(e["event_time"]) <= t_cut)
            kb = sorted((int(e["event_time"]), e["direction"]) for e in b
                        if int(e["event_time"]) <= t_cut)
            self.assertEqual(ka, kb, fam)

    def test_formation_uses_prefix_only(self) -> None:
        bars = _bars()
        feat_full = formation_features(bars, 50, "BTCUSDT", "regular_close")
        feat_same_prefix = formation_features(bars[:51], 50, "BTCUSDT", "regular_close")
        self.assertEqual(feat_full["event_time"], feat_same_prefix["event_time"])
        self.assertEqual(feat_full["reference_price"], feat_same_prefix["reference_price"])
        self.assertEqual(feat_full["prior_1h_return"], feat_same_prefix["prior_1h_return"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
