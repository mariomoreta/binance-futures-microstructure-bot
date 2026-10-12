"""Offline family evaluation prep (uses backtest_offline; no parallel engine).

Runs SEPARATE mechanical replays per study group (continuation,
correction legs, bearish continuation, explicit rebound variant,
pooled baseline reference) over caller-supplied events + candles JSON,
with a chronological dev/OOS split, cost sensitivity, and a manifest
recording coverage, discards, versions and hashes.

Reads/writes files ONLY at caller-given paths (default: temp dir).
Never touches the network, live modules, or canonical DBs. Results are
MECHANICS prep, never financial validation. RSI/ATR are research
candidates, not engine rules; formation methodology is caller-declared
and echoed verbatim into the manifest (this runner invents no entries).

Usage:
  python scripts/run_family_evaluation.py --events events.json \\
      --candles candles.json --out manifest.json --cutoff-ms <ms>
  python scripts/run_family_evaluation.py --demo   # synthetic, labeled
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.backtest_offline import (  # noqa: E402
    BacktestConfig,
    Candle,
    FundingCalendar,
    FundingSettlement,
    StudyEvent,
    input_hash,
    run_backtest,
    split_by_time,
)

GROUPS = ("continuation", "correction-exhaustion", "correction-reversal",
          "bearish-continuation", "rebound-variant", "baseline")


def _load_events(path: Path):
    out = []
    groups = {}
    for row in json.loads(path.read_text(encoding="utf-8")):
        ev = StudyEvent(
            symbol=str(row["symbol"]), event_time_ms=int(row["event_time_ms"]),
            direction=str(row["direction"]),
            reference_price=float(row.get("reference_price", 0.0)),
            family=str(row.get("family", "H1")),
            rules_version=str(row.get("rules_version", "H1-v1")))
        out.append(ev)
        # Runner-level annotation (not engine semantics; excluded from
        # input_hash): keeps families separate without touching the engine.
        groups[(ev.symbol, ev.event_time_ms, ev.direction)] = str(
            row.get("group", "continuation"))
    return out, groups


def _load_candles(path: Path):
    out = []
    for row in json.loads(path.read_text(encoding="utf-8")):
        out.append(Candle(
            symbol=str(row["symbol"]), open_time_ms=int(row["open_time_ms"]),
            open=float(row["open"]), high=float(row["high"]),
            low=float(row["low"]), close=float(row["close"])))
    return out


def _load_calendar(path: Path | None):
    if path is None:
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return FundingCalendar(
        version=str(raw.get("version", "external/v1")),
        source=str(raw.get("source", "external")),
        interval_ms=raw.get("interval_ms"),
        settlements=tuple(
            FundingSettlement(int(s["settlement_ms"]),
                              float(s["rate_bps"]))
            for s in raw.get("settlements", [])))


def _demo(out_dir: Path):
    H = 3600_000
    T0 = 1_700_000_000_000
    candles, events = [], []
    px = 100.0
    for i in range(200):
        o = px
        c = px * (1.002 if i % 5 else 0.999)
        candles.append({"symbol": "DEMOUSDT", "open_time_ms": T0 + i * 60_000,
                        "open": o, "high": max(o, c) * 1.001,
                        "low": min(o, c) * 0.999, "close": c})
        px = c
        if i % 25 == 0:
            events.append({"symbol": "DEMOUSDT",
                           "event_time_ms": T0 + i * 60_000,
                           "direction": "LONG", "reference_price": o,
                           "family": "H1", "rules_version": "H1-v1",
                           "group": ["continuation", "correction-reversal",
                                     "bearish-continuation",
                                     "rebound-variant", "baseline"][i // 25 %
                                                                     5]})
    ev_path = out_dir / "demo_events.json"
    cx_path = out_dir / "demo_candles.json"
    ev_path.write_text(json.dumps(events), encoding="utf-8")
    cx_path.write_text(json.dumps(candles), encoding="utf-8")
    return ev_path, cx_path, T0 + 100 * 60_000


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=None)
    ap.add_argument("--candles", default=None)
    ap.add_argument("--calendar", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--cutoff-ms", type=int, default=None)
    ap.add_argument("--formation-method", default="caller-declared")
    ap.add_argument("--scales", default="1.0,2.0,3.0")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args(argv)

    work = Path(tempfile.mkdtemp(prefix="family_eval_"))
    if args.demo:
        ev_path, cx_path, cutoff = _demo(work)
        out_path = Path(args.out) if args.out else work / "manifest.json"
        label = "DEMO-SYNTHETIC — mechanics only, NOT performance"
    else:
        if not args.events or not args.candles or args.cutoff_ms is None:
            print("need --events, --candles and --cutoff-ms (or --demo)",
                  file=sys.stderr)
            return 2
        ev_path, cx_path, cutoff = Path(args.events), Path(args.candles), \
            int(args.cutoff_ms)
        out_path = Path(args.out) if args.out else work / "manifest.json"
        label = "OFFLINE-EVAL-PREP — mechanics only, NOT validation"
    events, groups_of = _load_events(ev_path)
    candles = _load_candles(cx_path)
    calendar = _load_calendar(Path(args.calendar)
                              if args.calendar else None)
    scales = [float(s) for s in str(args.scales).split(",")]
    dataset_id = "synthetic-fixture" if args.demo else "caller-supplied"

    manifest: dict = {
        "label": label,
        "engine": "backtest_offline",
        "input_hash": input_hash(events, candles),
        "dataset_id": dataset_id,
        "cutoff_ms": cutoff,
        "formation_method": args.formation_method,
        "formation_note": "Formation is caller-declared and echoed; this "
                          "runner invents no entries and validates no edge.",
        "groups": {},
    }
    for group in GROUPS:
        gev = [e for e in events
               if groups_of.get((e.symbol, e.event_time_ms,
                                 e.direction)) == group]
        parts = split_by_time(gev, cutoff)
        manifest["groups"][group] = {}
        for seg, seg_events in parts.items():
            manifest["groups"][group][seg] = {}
            for scale in scales:
                cfg = BacktestConfig(cost_scale=scale,
                                     funding_calendar=calendar)
                res = run_backtest(seg_events, candles, cfg,
                                   dataset_id=dataset_id, segment=seg)
                trades = res["trades"]
                stops = sum(1 for t in trades
                            if t["exit_reason"] == "stop")
                manifest["groups"][group][seg][str(scale)] = {
                    "n_events": res["n_events"],
                    "n_trades": res["n_trades"],
                    "n_expired": res["n_expired"],
                    "n_mismatched": res["n_mismatched"],
                    "skipped_overlap": res["skipped_overlap"],
                    "exit_reasons": res["exit_reasons"],
                    "confirmation_rate_mech": (
                        (len(trades) - stops) / len(trades)
                        if trades else None),
                    "confirmation_note": "mechanical proxy "
                        "(not-stopped-out); NOT a validated confirmation "
                        "concept",
                    "expectancy_net": res["expectancy_net"],
                    "expectancy_gross": res["expectancy_gross"],
                    "total_net": res["total_net"],
                    "total_fees": res["total_fees"],
                    "total_funding": res["total_funding"],
                    "max_drawdown": res["max_drawdown"],
                    "mfe_mean": res["mfe_mean"],
                    "mae_mean": res["mae_mean"],
                    "config_hash": res["config_hash"],
                }
    manifest["blockers"] = [
        "no-historical-universe (symbols/windows caller-scoped)",
        "no-availability-proof (query time != available time)",
        "no-measured-costs (assumed fee/spread/slip/funding inputs)",
        "event-time OOS split without purge",
        "baseline is a pooled reference, not a strategy",
    ]
    out_path.write_text(json.dumps(manifest, indent=2, default=str),
                        encoding="utf-8")
    n_trades = sum(g["dev"]["1.0"]["n_trades"] + g["oos"]["1.0"]["n_trades"]
                   for g in manifest["groups"].values())
    print("groups=%d dev/oos x scales=%s trades=%d manifest=%s" % (
        len(GROUPS), args.scales if not args.demo else "1.0,2.0,3.0",
        n_trades, out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
