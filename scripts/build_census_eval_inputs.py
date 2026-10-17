"""Build runner inputs from the causal census (offline, read-only).

Reads census detections.jsonl + closed bars (canonical DB, mode=ro) and
writes per-(symbol, resolution) candles.json + events.json for the
EXISTING runner (scripts/run_family_evaluation.py), unchanged.

Mapping MAP-CANDIDATE-v2 (docs/HYPOTHESIS_MAPPING_CANDIDATE_V2.md):
  H1: MOM_UP/EXTENDED_GAINER -> continuation/H1/H1-v1/LONG @formation.
  H3: MOM_DOWN/EXTENDED_LOSER -> bearish-continuation/H3/H3-v1/SHORT.
  H2-exhaustion fade: FAILED_HIGH + CONFIRM-H2-SHORT-v1 (<=3 same-grid
      bars, close at/below formation close, no reclaim above trailing
      high) -> correction-exhaustion/H2/H2-v1/SHORT @confirmation bar.
  H2-reversal fade: mirror -> correction-reversal/H2/H2-v1/LONG.
  Rebound: excluded (0 events, no bounce definition).
Excluded with motive (counted, never fabricated): formation_gap rows,
tail-edge rows without same-grid entry, H2 unconfirmed/reclaimed.
Baseline TIME-PLACEBO-v1: seeded alternating-direction entries at
pseudorandom timestamps, same count/cadence per cell (group=baseline,
family H1/H1-v1 default contract, seed fixed).

Writes ONLY --out-dir. No network, no thresholds tuned on outcomes.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORICAL = ROOT / "data" / "historical" / "historical.db"
CONFIRM_WINDOW = 3  # IMPL (reviewable), see mapping doc

H1_SRC = ("MOMENTUM_ACCELERATION_UP", "EXTENDED_GAINER")
H3_SRC = ("MOMENTUM_ACCELERATION_DOWN", "EXTENDED_LOSER")


def _load_bars(con, symbol, interval):
    rows = con.execute(
        "SELECT open_time, open, high, low, close, close_time"
        " FROM historical_klines WHERE symbol=? AND interval=?"
        " ORDER BY open_time", (symbol, interval)).fetchall()
    return [{"symbol": symbol, "open_time_ms": int(t), "open": float(o),
             "high": float(h), "low": float(lo), "close": float(c),
             "close_time_ms": (int(ct) if ct is not None else None)}
            for (t, o, h, lo, c, ct) in rows]


def _confirm_h2(bars, by_open, formation, ref_close, trailing_high,
                want_short: bool):
    """CONFIRM-H2-{SHORT,LONG}-v1 over same-grid closed bars only."""
    start = formation
    fwd = sorted([b for b in bars if b["open_time_ms"] > start],
                 key=lambda b: b["open_time_ms"])
    for k in range(1, CONFIRM_WINDOW + 1):
        if len(fwd) < k:
            return None, "h2-no-confirmation"
        bar = fwd[k - 1]
        if want_short:
            if bar["close"] > trailing_high:
                return None, "h2-reclaim"
            if bar["close"] <= ref_close:
                return bar, None
        else:
            if bar["close"] < trailing_high:  # trailing_low passed in here
                return None, "h2-reclaim"
            if bar["close"] >= ref_close:
                return bar, None
    return None, "h2-no-confirmation"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Census eval input builder.")
    ap.add_argument("--detections", required=True)
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--interval", default="15m")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    symbols = [s.strip().upper() for s in str(args.symbols).split(",")
               if s.strip()]
    out_dir = Path(args.out_dir) if args.out_dir else Path(
        tempfile.mkdtemp(prefix="census_eval_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    dets = [json.loads(line) for line in
            Path(args.detections).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    con = sqlite3.connect(
        "file:%s?mode=ro" % (Path(args.db) if args.db else HISTORICAL),
        uri=True)
    try:
        bars_by = {s: _load_bars(con, s, args.interval) for s in symbols}
    finally:
        con.close()

    rng = random.Random(args.seed)
    total = {"h1": 0, "h3": 0, "h2ex": 0, "h2rev": 0, "placebo": 0,
             "excluded_gap": 0, "excluded_no_entry": 0,
             "excluded_h2_no_confirmation": 0, "excluded_h2_reclaim": 0,
             "excluded_other_symbol": 0}
    for sym in symbols:
        bars = bars_by[sym]
        by_open = {b["open_time_ms"]: b for b in bars}
        opens = sorted(by_open)
        first, last = opens[0], opens[-1]
        ev_rows = []
        cell_dets = [d for d in dets
                     if d["symbol"] == sym
                     and d["source_interval"] == args.interval]
        for d in cell_dets:
            if d["symbol"] not in symbols:
                total["excluded_other_symbol"] += 1
                continue
            if d["formation_gap"]:
                total["excluded_gap"] += 1
                continue
            if d["entry_time_same_grid"] is None:
                total["excluded_no_entry"] += 1
                continue
            fam = d["definition_name"]
            f = d["formation_time"]
            if fam in H1_SRC:
                ev_rows.append({"symbol": sym, "event_time_ms": f,
                                "direction": "LONG",
                                "reference_price": d["reference_price"],
                                "family": "H1", "rules_version": "H1-v1",
                                "group": "continuation"})
                total["h1"] += 1
            elif fam in H3_SRC:
                ev_rows.append({"symbol": sym, "event_time_ms": f,
                                "direction": "SHORT",
                                "reference_price": d["reference_price"],
                                "family": "H3", "rules_version": "H3-v1",
                                "group": "bearish-continuation"})
                total["h3"] += 1
            elif fam == "FAILED_HIGH_CANDIDATE":
                window = [b for b in bars
                          if b["open_time_ms"] <= f][-96:]
                th = max(b["high"] for b in window)
                bar, motive = _confirm_h2(bars, by_open, f,
                                          d["reference_price"], th, True)
                if motive == "h2-no-confirmation":
                    total["excluded_h2_no_confirmation"] += 1
                    continue
                if motive == "h2-reclaim":
                    total["excluded_h2_reclaim"] += 1
                    continue
                ev_rows.append({"symbol": sym,
                                "event_time_ms": bar["open_time_ms"],
                                "direction": "SHORT",
                                "reference_price": bar["close"],
                                "family": "H2", "rules_version": "H2-v1",
                                "group": "correction-exhaustion"})
                total["h2ex"] += 1
            elif fam == "FAILED_LOW_CANDIDATE":
                window = [b for b in bars
                          if b["open_time_ms"] <= f][-96:]
                tl = min(b["low"] for b in window)
                bar, motive = _confirm_h2(bars, by_open, f,
                                          d["reference_price"], tl, False)
                if motive == "h2-no-confirmation":
                    total["excluded_h2_no_confirmation"] += 1
                    continue
                if motive == "h2-reclaim":
                    total["excluded_h2_reclaim"] += 1
                    continue
                ev_rows.append({"symbol": sym,
                                "event_time_ms": bar["open_time_ms"],
                                "direction": "LONG",
                                "reference_price": bar["close"],
                                "family": "H2", "rules_version": "H2-v1",
                                "group": "correction-reversal"})
                total["h2rev"] += 1
        # TIME-PLACEBO-v1: same count as directional cell, seeded timestamps
        n_cell = sum(1 for e in ev_rows if e["group"] in (
            "continuation", "bearish-continuation",
            "correction-exhaustion", "correction-reversal"))
        span = last - first - 3_600_000
        pts = sorted(rng.randint(first, first + span) for _ in range(n_cell))
        # snap to grid (same-grid discipline, causal: bar open <= point)
        grid = [o for o in opens if o <= last - 3_600_000]
        for i, p in enumerate(pts):
            g = max(o for o in grid if o <= p)
            px = by_open[g]["close"]
            ev_rows.append({"symbol": sym, "event_time_ms": g,
                            "direction": "LONG" if i % 2 == 0 else "SHORT",
                            "reference_price": px,
                            "family": "H1", "rules_version": "H1-v1",
                            "group": "baseline"})
            total["placebo"] += 1
        (out_dir / ("candles_%s_%s.json" % (sym, args.interval))).write_text(
            json.dumps(bars), encoding="utf-8")
        (out_dir / ("events_%s_%s.json" % (sym, args.interval))).write_text(
            json.dumps(ev_rows), encoding="utf-8")
    (out_dir / "build_report.json").write_text(
        json.dumps({"interval": args.interval, "symbols": symbols,
                    "formation_method": "MAP-CANDIDATE-v2",
                    "confirm_window_bars": CONFIRM_WINDOW,
                    "placebo": "TIME-PLACEBO-v1 (seed %d)" % args.seed,
                    "counts": total}, indent=1), encoding="utf-8")
    print("built interval=%s counts=%s dir=%s" % (
        args.interval, total, out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
