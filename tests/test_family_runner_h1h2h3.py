"""Runner: external H1/H2/H3 inputs, per-group family, identity integrity.

Proves a valid H3 event is replayed under its own H3 contract (never
discarded by a global H1 default), external H1/H2/H3 rows all match
inside their groups, and two rows sharing (symbol, time, direction) in
different groups never collide. Temp dirs only; no network/DB.
Run: python run_tests.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parent.parent / "scripts" / \
    "run_family_evaluation.py"

T0 = 1_700_000_000_000
H = 3600_000


def _candles(symbol="BTCUSDT", n=30):
    px = 100.0
    out = []
    for i in range(n):
        out.append({"symbol": symbol, "open_time_ms": T0 + i * H,
                    "open": px, "high": px * 1.001, "low": px * 0.999,
                    "close": px})
    return out


def _run(events, candles, cutoff):
    tmp = Path(tempfile.mkdtemp(prefix="fam_ext_"))
    ev_path = tmp / "events.json"
    cx_path = tmp / "candles.json"
    out_path = tmp / "manifest.json"
    ev_path.write_text(json.dumps(events), encoding="utf-8")
    cx_path.write_text(json.dumps(candles), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--events", str(ev_path),
         "--candles", str(cx_path), "--cutoff-ms", str(cutoff),
         "--out", str(out_path)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(out_path.read_text(encoding="utf-8"))


def _ev(symbol, at, family, version, group, direction="LONG"):
    return {"symbol": symbol, "event_time_ms": at, "direction": direction,
            "reference_price": 100.0, "family": family,
            "rules_version": version, "group": group}


class ExternalFamiliesTest(unittest.TestCase):
    def test_h1_h2_h3_each_match_their_group(self) -> None:
        candles = _candles()
        events = [
            _ev("BTCUSDT", T0, "H1", "H1-v1", "continuation"),
            _ev("BTCUSDT", T0 + H, "H2", "H2-v1",
                "correction-exhaustion"),
            _ev("BTCUSDT", T0 + 2 * H, "H3", "H3-v1",
                "bearish-continuation"),
        ]
        manifest = _run(events, candles, T0 + 100 * H)
        for group in ("continuation", "correction-exhaustion",
                      "bearish-continuation"):
            cell = manifest["groups"][group]["dev"]["1.0"]
            self.assertEqual(cell["n_events"], 1, group)
            self.assertEqual(cell["n_mismatched"], 0, group)
            self.assertEqual(cell["n_trades"], 1, group)

    def test_group_contracts_recorded(self) -> None:
        manifest = _run([], _candles(), T0)
        self.assertEqual(
            manifest["groups"]["bearish-continuation"]["family"], "H3")
        self.assertEqual(
            manifest["groups"]["bearish-continuation"]["rules_version"],
            "H3-v1")
        self.assertEqual(manifest["groups"]["continuation"]["family"],
                         "H1")


class IdentityCollisionTest(unittest.TestCase):
    def test_same_triple_different_groups_never_collide(self) -> None:
        candles = _candles()
        # Identical (symbol, time, direction); different group+family.
        events = [
            _ev("BTCUSDT", T0, "H1", "H1-v1", "continuation"),
            _ev("BTCUSDT", T0, "H3", "H3-v1", "bearish-continuation"),
        ]
        manifest = _run(events, candles, T0 + 100 * H)
        cont = manifest["groups"]["continuation"]["dev"]["1.0"]
        bear = manifest["groups"]["bearish-continuation"]["dev"]["1.0"]
        self.assertEqual(cont["n_events"], 1)
        self.assertEqual(bear["n_events"], 1)
        self.assertEqual(cont["n_mismatched"], 0)
        self.assertEqual(bear["n_mismatched"], 0)
        cont_ids = manifest["groups"]["continuation"]["event_ids"]
        bear_ids = manifest["groups"]["bearish-continuation"]["event_ids"]
        self.assertEqual(len(cont_ids), 1)
        self.assertEqual(len(bear_ids), 1)
        self.assertNotEqual(cont_ids[0], bear_ids[0])


if __name__ == "__main__":
    unittest.main()
