"""Reconstruct the causal event census from stored series (offline, read-only).

Reuses P1-11C definitions verbatim (events.default_definition v1) and
re-derives EVERY detection from closed bars only, WITHOUT using the
retrospective `event_instances` table as selection. The stored instances
are used solely as comparison labels (originals preserved, never as input).

Time separation (explicit, versioned):
  formation_time = OPEN of the formation bar (condition needs its CLOSE).
  available_at   = venue close_time of the formation bar (chain-derived).
  decision_time  = NULL in offline census (no live detector exists;
                   reason recorded per detection).
  entry rule ENTRY-SAME-GRID-v1: first bar OPEN on the SAME interval with
                   open_time > formation_time. 1h events are NEVER replayed
                   on 15m candles (no cross-resolution replay without an
                   explicit rule; none is defined here).

IDs: census_id deterministic per (census_version, family, fam_version,
symbol, interval, formation_time, index). Original event_ids matched by
(definition, symbol, formation_time, source_interval) and preserved.
Duplicates (same symbol+interval+formation across families) counted.

Reads the canonical DB read-only (mode=ro). Writes ONLY --out-dir.
No network, no trading, no threshold tuning.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.events import (  # noqa: E402
    EVENT_FAMILIES,
    _matches_definition,
    default_definition,
    formation_features,
)

CENSUS_VERSION = "CENSUS-V1"
ENTRY_RULE = "ENTRY-SAME-GRID-v1"
HISTORICAL = ROOT / "data" / "historical" / "historical.db"


def _load_bars(con, symbol, interval):
    rows = con.execute(
        "SELECT open_time, open, high, low, close, close_time,"
        " quote_volume, taker_buy_quote FROM historical_klines"
        " WHERE symbol=? AND interval=? ORDER BY open_time",
        (symbol, interval)).fetchall()
    bars = []
    for (ot, o, h, lo, c, ct, qv, tbq) in rows:
        bars.append({"open_time": int(ot), "open": o, "high": h, "low": lo,
                     "close": c, "close_time": ct, "quote_volume": qv,
                     "taker_buy_quote": tbq})
    return bars


def _load_originals(con):
    rows = con.execute(
        "SELECT event_id, definition_name, definition_version, symbol,"
        " event_time, source_interval FROM event_instances").fetchall()
    out = []
    for (eid, d, v, s, t, si) in rows:
        out.append({"event_id": eid, "definition_name": d,
                    "definition_version": v, "symbol": s,
                    "event_time": int(t), "source_interval": si})
    return out


def _detect_with_motives(bars, definition, symbol, ref_source, interval,
                         btc_bars):
    fam = str(definition["definition_name"])
    params = dict(definition.get("parameters", {}))
    ordered = sorted(bars, key=lambda b: int(b["open_time"]))
    close_map = {int(b["open_time"]): b.get("close_time") for b in ordered}
    opens = [int(b["open_time"]) for b in ordered]
    events = []
    motives = {}
    n_scanned = 0
    for i in range(len(ordered)):
        if i < 5:
            continue
        n_scanned += 1
        feat = formation_features(ordered[: i + 1], i, symbol, ref_source,
                                  btc_bars)
        feat["source_interval"] = interval
        fire, ctx = _matches_definition(fam, params, feat)
        if not fire:
            motives[ctx] = motives.get(ctx, 0) + 1
            continue
        if feat.get("reference_price") is None:
            motives["null-reference-price"] = motives.get(
                "null-reference-price", 0) + 1
            continue
        formation = int(feat["event_time"])
        available = close_map.get(formation)
        # entry on the SAME grid: first open strictly after formation
        entry = next((o for o in opens if o > formation), None)
        chain_ok = True
        chain_reason = None
        if available is None:
            chain_ok = False
            chain_reason = "missing-close-time"
        elif entry is not None and available > entry:
            chain_ok = False
            chain_reason = "chain-violation"
        ev = {
            "definition_name": fam,
            "definition_version": int(definition.get("definition_version", 1)),
            "symbol": symbol.upper(),
            "source_interval": interval,
            "formation_time": formation,
            "available_at": available,
            "decision_time": None,
            "decision_time_reason": "no-live-detector-in-offline-census",
            "entry_time_same_grid": entry,
            "entry_rule": ENTRY_RULE,
            "chain_ok": chain_ok,
            "chain_reason": chain_reason,
            "formation_gap": bool(feat.get("formation_gap")),
            "direction": {"EXTENDED_GAINER": "up",
                           "MOMENTUM_ACCELERATION_UP": "up",
                           "FAILED_HIGH_CANDIDATE": "up",
                           "EXTENDED_LOSER": "down",
                           "MOMENTUM_ACCELERATION_DOWN": "down",
                           "FAILED_LOW_CANDIDATE": "down"}[fam],
            "context": ctx,
            "reference_price": feat["reference_price"],
            "reference_source": ref_source,
        }
        events.append(ev)
    events.sort(key=lambda e: (e["formation_time"], e["symbol"]))
    for k, e in enumerate(events):
        e["census_id"] = (
            f"{CENSUS_VERSION}-{interval}-{e['definition_name']}"
            f"-v{e['definition_version']}-{e['symbol']}"
            f"-{e['formation_time']}-{k}")
    return events, motives, n_scanned


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Causal census reconstruction.")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--intervals", default="15m")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--prefix-check", action="store_true",
                    help="run prefix-truncation + later-data invariance checks")
    args = ap.parse_args(argv)
    symbols = [s.strip().upper() for s in str(args.symbols).split(",")
               if s.strip()]
    intervals = [s.strip() for s in str(args.intervals).split(",")
                 if s.strip()]
    out_dir = Path(args.out_dir) if args.out_dir else Path(
        tempfile.mkdtemp(prefix="causal_census_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db) if args.db else HISTORICAL
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    try:
        originals = _load_originals(con)
        orig_keys = {(o["definition_name"], o["symbol"], o["event_time"],
                      o["source_interval"]): o["event_id"] for o in originals}
        series = {}
        for sym in symbols:
            for iv in intervals:
                series[(sym, iv)] = _load_bars(con, sym, iv)
        btc_cache = {}
        for iv in intervals:
            if ("BTCUSDT", iv) in series:
                btc_cache[iv] = series[("BTCUSDT", iv)]
            else:
                btc_cache[iv] = _load_bars(con, "BTCUSDT", iv)
    finally:
        con.close()

    all_dets = []
    per_cell = {}
    for (sym, iv), bars in series.items():
        if not bars:
            per_cell[f"{sym}/{iv}"] = {"bars": 0, "status": "no-series"}
            continue
        btc_bars = None if sym == "BTCUSDT" else btc_cache[iv]
        for fam in EVENT_FAMILIES:
            definition = default_definition(fam, 1)
            dets, motives, scanned = _detect_with_motives(
                bars, definition, sym, "regular_close", iv, btc_bars)
            for d in dets:
                key = (d["definition_name"], d["symbol"],
                       d["formation_time"], d["source_interval"])
                d["original_event_id"] = orig_keys.get(key)
                d["census_version"] = CENSUS_VERSION
            admitted = [d for d in dets if d["chain_ok"]]
            discarded = [d for d in dets if not d["chain_ok"]]
            disc_reasons = {}
            for d in discarded:
                disc_reasons[d["chain_reason"]] = disc_reasons.get(
                    d["chain_reason"], 0) + 1
            all_dets.extend(dets)
            per_cell[f"{sym}/{iv}/{fam}"] = {
                "bars_scanned": scanned,
                "candidates_fired": len(dets),
                "admitted": len(admitted),
                "admitted_with_formation_gap": sum(
                    1 for d in admitted if d["formation_gap"]),
                "discarded": len(discarded),
                "discard_reasons": disc_reasons,
                "nonfire_motives": motives,
            }

    # duplicates: same (symbol, interval, formation) across families
    seen = {}
    dup_groups = 0
    dup_extra = 0
    for d in all_dets:
        k = (d["symbol"], d["source_interval"], d["formation_time"])
        seen.setdefault(k, []).append(d["definition_name"])
    for k, fams in seen.items():
        if len(fams) > 1:
            dup_groups += 1
            dup_extra += len(fams) - 1

    # comparison vs originals restricted to census scope
    scope_syms = set(symbols)
    scope_ivs = set(intervals)
    orig_in_scope = [o for o in originals if o["symbol"] in scope_syms
                     and (o["source_interval"] in scope_ivs)]
    census_keys = {(d["definition_name"], d["symbol"], d["formation_time"],
                    d["source_interval"]) for d in all_dets}
    orig_key_set = {(o["definition_name"], o["symbol"], o["event_time"],
                     o["source_interval"]) for o in orig_in_scope}
    matched = census_keys & orig_key_set
    census_only = census_keys - orig_key_set
    orig_only = orig_key_set - census_keys

    prefix_report = {}
    if args.prefix_check:
        for (sym, iv), bars in series.items():
            if not bars:
                continue
            ordered = sorted(bars, key=lambda b: int(b["open_time"]))
            cut = len(ordered) * 60 // 100
            prefix = ordered[:cut]
            t_bound = int(prefix[-1]["open_time"])
            btc_full = None if sym == "BTCUSDT" else btc_cache[iv]
            btc_pre = (None if sym == "BTCUSDT" else
                       [b for b in btc_full
                        if int(b["open_time"]) <= t_bound])
            for fam in EVENT_FAMILIES:
                definition = default_definition(fam, 1)
                full, _, _ = _detect_with_motives(
                    ordered, definition, sym, "regular_close", iv, btc_full)
                trunc, _, _ = _detect_with_motives(
                    prefix, definition, sym, "regular_close", iv, btc_pre)
                full_le = sorted(d["formation_time"] for d in full
                                 if d["formation_time"] <= t_bound)
                trunc_ts = sorted(d["formation_time"] for d in trunc)
                prefix_ok = (full_le == trunc_ts)
                # invariance: mutate everything strictly after T
                mutated = copy.deepcopy(ordered)
                for b in mutated:
                    if int(b["open_time"]) > t_bound:
                        try:
                            b["close"] = str(float(b["close"]) * 1.5)
                            b["high"] = str(float(b["high"]) * 1.5)
                        except (TypeError, ValueError):
                            pass
                mut, _, _ = _detect_with_motives(
                    mutated, definition, sym, "regular_close", iv, btc_full)
                mut_le = sorted(d["formation_time"] for d in mut
                                if d["formation_time"] <= t_bound)
                inv_ok = (mut_le == trunc_ts)
                prefix_report[f"{sym}/{iv}/{fam}"] = {
                    "T_bound": t_bound, "n_prefix": len(trunc_ts),
                    "prefix_equal": prefix_ok,
                    "later_mutation_invariant": inv_ok,
                }

    summary = {
        "census_version": CENSUS_VERSION,
        "entry_rule": ENTRY_RULE,
        "scope": {"symbols": symbols, "intervals": intervals},
        "n_detections": len(all_dets),
        "n_admitted": sum(1 for d in all_dets if d["chain_ok"]),
        "n_discarded": sum(1 for d in all_dets if not d["chain_ok"]),
        "duplicate_groups": dup_groups,
        "duplicate_extra_rows": dup_extra,
        "per_cell": per_cell,
        "comparison": {
            "originals_in_scope": len(orig_in_scope),
            "matched": len(matched),
            "census_only": len(census_only),
            "originals_only": len(orig_only),
        },
        "prefix_report": prefix_report,
        "notes": [
            "decision_time is NULL by construction: no live detector exists;",
            "entry_time_same_grid uses SAME-interval next open (ENTRY-SAME-GRID-v1);",
            "1h detections are never replayed on 15m candles in this census.",
        ],
    }
    (out_dir / "detections.jsonl").write_text(
        "\n".join(json.dumps(d, sort_keys=True) for d in all_dets),
        encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    (out_dir / "compare.json").write_text(json.dumps(
        {"matched": sorted(list(matched)),
         "census_only": sorted(list(census_only))[:500],
         "census_only_total": len(census_only),
         "originals_only": sorted(list(orig_only))[:500],
         "originals_only_total": len(orig_only)}, indent=1, sort_keys=True),
        encoding="utf-8")
    print("detections=%d admitted=%d discarded=%d dup_groups=%d(+%d)"
          " matched=%d census_only=%d originals_only=%d dir=%s" % (
              len(all_dets), summary["n_admitted"], summary["n_discarded"],
              dup_groups, dup_extra, len(matched), len(census_only),
              len(orig_only), out_dir))
    if prefix_report:
        bad = {k: v for k, v in prefix_report.items()
               if not (v["prefix_equal"] and v["later_mutation_invariant"])}
        print("prefix_cells=%d bad=%d" % (len(prefix_report), len(bad)))
        if bad:
            print(json.dumps(bad, indent=1, sort_keys=True))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
