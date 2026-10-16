"""Aggregate per-symbol evaluation manifests into the versioned artifact.

Deterministic bundling only (no engine, no network, no DB): reads the
per-symbol `run_family_evaluation.py` manifests plus their export meta,
purge-selection reports and realized funding calendars, and writes
`frontend/src/data/offline-eval-v1.json` (OFFLINE-EVAL-V1, schema 1).

Fails closed on any inconsistency (cutoff mismatch, selection not adding
up, calendar-symbol mismatch, unexpected groups/scales). Pooled reference
is arithmetic aggregation over the directional groups (never a strategy).

Usage (paths are caller-given; temp manifests stay outside Git):
  python scripts/aggregate_offline_eval.py \\
      --inputs <inputs.json> --out frontend/src/data/offline-eval-v1.json

inputs.json:
  {"cutoff_ms": 1790010000000, "horizon_ms": 3600000,
   "symbols": {"BTCUSDT": {"manifest": "...", "meta": "...",
                           "selection": "...", "calendar": "..."}, ...}}

Byte layout: indent=1 JSON with CRLF (Windows text-mode convention of the
original generation). Content equality is what matters and is verified by
tests; the file sha256 is pinned in docs/OFFLINE_EVAL_REPORT_V1.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GROUPS = ("continuation", "correction-exhaustion", "correction-reversal",
          "bearish-continuation", "rebound-variant", "baseline")
DIRECTIONAL = GROUPS[:4]
SEGMENTS = ("dev", "oos")
SCALES = ("1.0", "2.0", "3.0")

LABEL = "OFFLINE-EVAL \u2014 mechanics with conditioned costs, NOT validation"
ENGINE_VERSION = "backtest-offline/v4.2"
FORMATION_METHOD = "PROPOSED-P1-11C-map-v1 (caller-declared, NOT approved)"
MAP_CANDIDATE = "MAP-CANDIDATE-v1 (docs/HYPOTHESIS_ENTRY_MAPPING_CANDIDATE.md)"
VENUE = "Binance USD-M (fapi.binance.com)"

LIMITS = [
    "mapping caller-declared, NOT approved",
    "costs assumed (COST-ASSUME-v1), never measured",
    "funding realized venue calendars attached per symbol",
    "eval segment is time-held-out (non-pristine), never clean OOS",
    "grouped events are NOT independent samples",
    "H2 legs INSUFFICIENT sample; rebound-variant excluded (0 events)",
    "no availability proof (query time != tradable time)",
    "no buy-and-hold/time-placebo baseline in V1",
    "pooled reference is arithmetic aggregation, not a strategy",
]

COST_NOTE = ("assumed drag (defaults, untouched); spread/depth history "
             "absent so slippage is NOT measured; account fee tier unknown "
             "so fees are NOT applicable commissions")
FQ_NOTE = ("per-position accounting completeness; calendar-complete "
           "never implies it")


def _cell(src: dict) -> dict:
    return {
        "n_events": src["n_events"],
        "n_trades": src["n_trades"],
        "n_expired": src["n_expired"],
        "n_mismatched": src["n_mismatched"],
        "skipped_overlap": src["skipped_overlap"],
        "n_realized": src["n_realized"],
        "n_open": src["n_open"],
        "exit_reasons": dict(src["exit_reasons"]),
        "expectancy_net": src["expectancy_net"],
        "expectancy_gross": src["expectancy_gross"],
        "total_net": src["total_net"],
        "total_net_realized": src["total_net_realized"],
        "total_fees": src["total_fees"],
        "total_funding": src["total_funding"],
        "max_drawdown": src["max_drawdown"],
        "max_drawdown_realized": src["max_drawdown_realized"],
        "mfe_mean": src["mfe_mean"],
        "mae_mean": src["mae_mean"],
        "config_hash": src["config_hash"],
        "funding_quality": {
            "settled_events": src["funding_quality"]["settled_events"],
            "unknown_excluded": src["funding_quality"]["unknown_excluded"],
            "gap_ms": src["funding_quality"]["gap_ms"],
            "uncovered_ms": src["funding_quality"]["uncovered_ms"],
            "accounting_complete_trades":
                src["funding_quality"]["accounting_complete_trades"],
            "note": FQ_NOTE,
        },
    }


def _pooled(cells: dict, seg: str, scale: str) -> dict:
    tot = {"n_events": 0, "n_trades": 0, "n_realized": 0, "n_open": 0,
           "skipped_overlap": 0, "n_expired": 0, "n_mismatched": 0,
           "total_net": 0.0, "total_net_realized": 0.0,
           "total_fees": 0.0, "total_funding": 0.0}
    for sym in sorted(cells):
        for group in DIRECTIONAL:
            c = cells[sym][group][seg][scale]
            for k in tot:
                tot[k] += c[k]
    out = dict(tot)
    out["expectancy_net"] = (tot["total_net"] / tot["n_trades"]
                             if tot["n_trades"] else 0.0)
    out["expectancy_net_realized"] = (
        tot["total_net_realized"] / tot["n_realized"]
        if tot["n_realized"] else 0.0)
    return out


def build(inputs: dict) -> dict:
    cutoff = int(inputs["cutoff_ms"])
    horizon = int(inputs["horizon_ms"])
    symbols, cells = {}, {}
    for sym in sorted(inputs["symbols"]):
        spec = inputs["symbols"][sym]
        manifest = json.loads(Path(spec["manifest"]).read_text(
            encoding="utf-8"))
        meta = json.loads(Path(spec["meta"]).read_text(encoding="utf-8"))
        selection = json.loads(Path(spec["selection"]).read_text(
            encoding="utf-8"))
        calendar = json.loads(Path(spec["calendar"]).read_text(
            encoding="utf-8"))
        if int(manifest["cutoff_ms"]) != cutoff:
            raise ValueError("manifest cutoff mismatch for %s" % sym)
        if selection["n_dev"] + selection["n_oos"] + \
                selection["n_purged_dev_crossing"] != selection["n_in"]:
            raise ValueError("selection does not add up for %s" % sym)
        if selection["n_in"] != meta["n_events"]:
            raise ValueError("selection/export count mismatch for %s" % sym)
        if str(calendar.get("symbol", "")).upper() != sym.upper():
            raise ValueError("calendar symbol mismatch for %s" % sym)
        if tuple(manifest["groups"]) != GROUPS:
            raise ValueError("unexpected groups for %s" % sym)
        settlements = calendar["settlements"]
        symbols[sym] = {
            "venue": VENUE,
            "interval": meta["interval"],
            "n_candles": meta["n_candles"],
            "window_open_ms": meta["coverage"]["window_open_ms"],
            "window_close_ms": meta["coverage"]["window_close_ms"],
            "null_close_time": meta["coverage"]["null_close_time"],
            "close_chain_violations":
                meta["coverage"]["close_chain_violations"],
            "n_events": meta["n_events"],
            "discarded": dict(meta["discarded"]),
            "input_hash": manifest["input_hash"],
            "cutoff_ms": cutoff,
            "selection": {
                "cutoff_ms": selection["cutoff_ms"],
                "horizon_ms": selection["horizon_ms"],
                "n_in": selection["n_in"],
                "n_dev": selection["n_dev"],
                "n_oos": selection["n_oos"],
                "n_purged_dev_crossing":
                    selection["n_purged_dev_crossing"],
                "note": selection["note"],
            },
            "funding_calendar": {
                "version": calendar["version"],
                "source": calendar["source"],
                "interval_ms": calendar["interval_ms"],
                "n_settlements": len(settlements),
                "span_ms": [settlements[0]["settlement_ms"],
                            settlements[-1]["settlement_ms"]],
                "response_sha256":
                    calendar["provenance"]["response_sha256"],
            },
        }
        cells[sym] = {}
        for group in GROUPS:
            cells[sym][group] = {}
            for seg in SEGMENTS:
                cells[sym][group][seg] = {}
                for scale in SCALES:
                    cells[sym][group][seg][scale] = _cell(
                        manifest["groups"][group][seg][scale])
    pooled = {seg: {scale: _pooled(cells, seg, scale)
                    for scale in SCALES} for seg in SEGMENTS}
    return {
        "schema_version": 1,
        "artifact_version": "OFFLINE-EVAL-V1",
        "label": LABEL,
        "engine_version": ENGINE_VERSION,
        "formation_method": FORMATION_METHOD,
        "map_candidate": MAP_CANDIDATE,
        "cutoff_ms": cutoff,
        "horizon_ms": horizon,
        "cost_assumption": {
            "id": "COST-ASSUME-v1",
            "fee_bps": 5.0,
            "spread_bps": 1.0,
            "slippage_bps": 2.0,
            "scales": [1.0, 2.0, 3.0],
            "note": COST_NOTE,
        },
        "symbols": symbols,
        "cells": cells,
        "limits": list(LIMITS),
        "pooled_reference": pooled,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Aggregate offline-eval artifact.")
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    text = json.dumps(build(inputs), indent=1)
    Path(args.out).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    print("artifact=%s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
