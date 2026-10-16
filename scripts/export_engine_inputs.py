"""Export retained candles + study events into engine inputs (isolated copy).

Reads the canonical DBs READ-ONLY (mode=ro) and writes ONLY the
caller-given --out-dir (default: a fresh temp dir). Never touches
the network, never writes the repo, never invents entries.

Event mapping (PROPOSED, caller-declared, echoed verbatim into the
meta file — NOT an approved methodology):
  MOMENTUM_ACCELERATION_UP -> continuation (H1/H1-v1)
  EXTENDED_GAINER           -> continuation (H1/H1-v1)
  MOMENTUM_ACCELERATION_DOWN-> bearish-continuation (H3/H3-v1)
  EXTENDED_LOSER            -> bearish-continuation (H3/H3-v1)
  FAILED_HIGH_CANDIDATE     -> correction-exhaustion (H2/H2-v1)
  FAILED_LOW_CANDIDATE      -> correction-reversal (H2/H2-v1)
Only instances with a usable direction + reference_price are
exported; the rest are counted as discarded (never fabricated).
Candles: closed regular klines for the requested symbols/interval,
with venue close_time preserved per candle. --as-of-ms drops candles
still open at that frontier (close_time > as_of, counted); meta
records as_of_ms (dataset knowledge frontier, in ms epoch) SEPARATE
from cutoff_ms (dev/OOS event-time split): the two must never be
confused. Units and coverage are documented in meta.json.
Funding: NO realized calendar is exported — fundingRate history was
never ingested, so the engine falls back to its labeled synthetic
interval math (see inventory doc for the acquisition contract).

Output: candles.json, events.json, meta.json (coverage, mapping,
hashes, counts, discards, exclusions). Pair with:
  python scripts/run_family_evaluation.py --events events.json \\
      --candles candles.json --cutoff-ms <ms> --out manifest.json \\
      --formation-method PROPOSED-P1-11C-map-v1
whose results are MECHANICS ONLY, never validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORICAL = ROOT / "data" / "historical" / "historical.db"

# Direction convention (part of the PROPOSED caller-declared mapping):
# instances carry 'up'/'down' (realized drift side); the engine prices
# LONG/SHORT. 'up' -> LONG, 'down' -> SHORT, echoed in meta.
DIRECTION_MAP = {"up": "LONG", "down": "SHORT"}

# PROPOSED mapping only (see module docstring): (group, family, version).
PROPOSED_MAP = {
    "MOMENTUM_ACCELERATION_UP": ("continuation", "H1", "H1-v1"),
    "EXTENDED_GAINER": ("continuation", "H1", "H1-v1"),
    "MOMENTUM_ACCELERATION_DOWN": ("bearish-continuation", "H3", "H3-v1"),
    "EXTENDED_LOSER": ("bearish-continuation", "H3", "H3-v1"),
    "FAILED_HIGH_CANDIDATE": ("correction-exhaustion", "H2", "H2-v1"),
    "FAILED_LOW_CANDIDATE": ("correction-reversal", "H2", "H2-v1"),
}


def _sha(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only export of engine inputs.")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--interval", default="15m")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--cutoff-ms", type=int, default=None)
    ap.add_argument("--as-of-ms", type=int, default=None,
                    help="dataset knowledge frontier: keep only candles with "
                         "close_time <= as_of (open candles dropped+counted). "
                         "Distinct from --cutoff-ms (dev/OOS event split).")
    ap.add_argument("--db", default=None,
                    help="historical DB override (tests/fixtures only; "
                         "default: canonical read-only)")
    args = ap.parse_args(argv)

    symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]
    if not symbols:
        print("no symbols", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir) if args.out_dir else Path(
        tempfile.mkdtemp(prefix="engine_inputs_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect("file:%s?mode=ro" % (Path(args.db) if args.db
                                                  else HISTORICAL), uri=True)
    try:
        candles = []
        chain_violations = 0
        for sym in symbols:
            rows = con.execute(
                'SELECT open_time, open, high, low, close, close_time'
                ' FROM historical_klines'
                ' WHERE symbol=? AND interval=? ORDER BY open_time',
                (sym, args.interval)).fetchall()
            for (t, o, h, low, c, ct) in rows:
                if args.as_of_ms is not None and ct is not None \
                        and ct > args.as_of_ms:
                    continue  # still open at the frontier (counted below)
                candles.append({"symbol": sym, "open_time_ms": t, "open": o,
                                "high": h, "low": low, "close": c,
                                "close_time_ms": ct})
            chain = [r for r in rows if r[0] is not None]
            for (prev, cur) in zip(chain, chain[1:]):
                if prev[5] is not None and prev[5] > cur[0]:
                    chain_violations += 1
        n_open_dropped = 0
        if args.as_of_ms is not None:
            n_open_dropped = sum(
                1 for sym in symbols for r in con.execute(
                    'SELECT close_time FROM historical_klines'
                    ' WHERE symbol=? AND interval=?', (sym, args.interval))
                if r[0] is not None and r[0] > args.as_of_ms)
        raw_events = con.execute(
            'SELECT definition_name, symbol, event_time, direction, reference_price'
            ' FROM event_instances').fetchall()
    finally:
        con.close()

    events, discarded = [], {"unmapped-definition": 0, "bad-direction": 0,
                             "bad-price": 0, "bad-time": 0, "symbol-filtered": 0,
                             "open-after-asof": n_open_dropped}
    for (definition, symbol, event_time, direction, price) in raw_events:
        if definition not in PROPOSED_MAP:
            discarded["unmapped-definition"] += 1
            continue
        if symbol not in symbols:
            discarded["symbol-filtered"] += 1
            continue
        if direction not in DIRECTION_MAP:
            discarded["bad-direction"] += 1
            continue
        direction = DIRECTION_MAP[direction]
        try:
            price_f = float(price)
            time_ms = int(event_time)
        except (TypeError, ValueError):
            discarded["bad-price"] += 1
            continue
        if not (price_f > 0 and time_ms > 0):
            discarded["bad-time"] += 1
            continue
        group, family, version = PROPOSED_MAP[definition]
        events.append({"symbol": symbol, "event_time_ms": time_ms,
                       "direction": direction, "reference_price": price_f,
                       "family": family, "rules_version": version,
                       "group": group, "source_definition": definition})

    if args.cutoff_ms is not None:
        cutoff = int(args.cutoff_ms)
    else:
        times = sorted(e["event_time_ms"] for e in events)
        cutoff = times[len(times) // 2] if times else 0

    candles_text = json.dumps(candles, sort_keys=True)
    events_text = json.dumps(events, sort_keys=True)
    opens = sorted(c["open_time_ms"] for c in candles)
    closes = sorted(c["close_time_ms"] for c in candles
                    if c["close_time_ms"] is not None)
    meta = {
        "formation_method": "PROPOSED-P1-11C-map-v1 (caller-declared, NOT approved)",
        "mapping": {k: {"group": v[0], "family": v[1], "rules_version": v[2]}
                    for k, v in PROPOSED_MAP.items()},
        "direction_map": DIRECTION_MAP,
        "symbols": symbols, "interval": args.interval,
        "units": {"times_ms": "epoch milliseconds (open_time, close_time, "
                              "event_time, cutoff, as_of)",
                  "prices": "quote currency (USDT) per base unit",
                  "volumes": "not exported (engine Candle carries no volume)"},
        "coverage": {"window_open_ms": opens[0] if opens else None,
                     "window_close_ms": closes[-1] if closes else None,
                     "null_close_time": sum(1 for c in candles
                                            if c["close_time_ms"] is None),
                     "close_chain_violations": chain_violations},
        "n_candles": len(candles), "n_events": len(events),
        "discarded": discarded,
        "cutoff_ms": cutoff,
        "cutoff_note": "dev/OOS EVENT-time split (split_by_time); NOT a dataset "
                       "knowledge frontier",
        "as_of_ms": args.as_of_ms,
        "as_of_note": "dataset knowledge frontier: only candles with "
                      "close_time <= as_of are exported (None keeps all closed "
                      "rows as stored); never confuse with cutoff_ms",
        "funding_calendar": None,
        "funding_note": "no realized calendar exported (fundingRate history never "
                        "ingested); engine uses labeled synthetic interval fallback",
        "candles_sha": _sha(candles_text), "events_sha": _sha(events_text),
        "source_db": "%s (read-only)" % (args.db if args.db
                                              else "data/historical/historical.db"),
    }
    (out_dir / "candles.json").write_text(candles_text, encoding="utf-8")
    (out_dir / "events.json").write_text(events_text, encoding="utf-8")
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("candles=%d events=%d discarded=%s cutoff=%d dir=%s" % (
        len(candles), len(events), discarded, cutoff, out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
