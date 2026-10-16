"""Build a versioned realized-funding calendar from a saved venue response.

Input: raw JSON saved from Binance USD-M `GET /fapi/v1/fundingRate`
(a list of {symbol, fundingTime, fundingRate, ...} with REALIZED venue
rates — never a quoted/next estimate). Output: calendar JSON accepted by
`scripts/run_family_evaluation.py --calendar`:
{version, source, interval_ms, symbol, settlements: [{settlement_ms,
rate_bps}], provenance: {endpoint, acquired_utc, response_sha256,
n_raw, n_settlements, coverage}}.

Offline and deterministic: no network. Exact-duplicate settlements are
kept here (the engine dedups and counts); same-ms different-rate rows
REJECT the run in the engine (fail-closed, never coerced).

Usage:
  python scripts/build_funding_calendar.py --raw funding_BTCUSDT.json \\
      --symbol BTCUSDT --version FUNDING-CAL-v1 --out calendar_BTC.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build realized funding calendar.")
    ap.add_argument("--raw", required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--version", default="FUNDING-CAL-v1")
    ap.add_argument("--interval-ms", type=int, default=8 * 3600 * 1000)
    ap.add_argument("--endpoint",
                    default="https://fapi.binance.com/fapi/v1/fundingRate")
    ap.add_argument("--acquired-utc", default="UNKNOWN")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    raw_text = Path(args.raw).read_text(encoding="utf-8")
    rows = json.loads(raw_text)
    symbol = str(args.symbol).upper()
    settlements = []
    for r in rows:
        if str(r.get("symbol", "")).upper() != symbol:
            continue
        settlements.append({
            "settlement_ms": int(r["fundingTime"]),
            "rate_bps": float(r["fundingRate"]) * 10000.0,
        })
    settlements.sort(key=lambda s: s["settlement_ms"])
    cal = {
        "version": str(args.version),
        "source": "exchange-funding-history (Binance USD-M fundingRate)",
        "interval_ms": int(args.interval_ms),
        "symbol": symbol,
        "settlements": settlements,
        "provenance": {
            "endpoint": str(args.endpoint),
            "acquired_utc": str(args.acquired_utc),
            "response_sha256": hashlib.sha256(
                raw_text.encode("utf-8")).hexdigest(),
            "n_raw": len(rows),
            "n_settlements": len(settlements),
            "coverage_ms": ([settlements[0]["settlement_ms"],
                             settlements[-1]["settlement_ms"]]
                            if settlements else [None, None]),
            "note": "realized venue rates; quoted/next estimates never "
                    "substitute them",
        },
    }
    Path(args.out).write_text(json.dumps(cal, indent=1), encoding="utf-8")
    print("symbol=%s settlements=%d out=%s" % (symbol, len(settlements),
                                              args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
