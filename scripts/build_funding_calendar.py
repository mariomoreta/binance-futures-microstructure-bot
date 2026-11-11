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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.backtest_offline import (  # noqa: E402
    FundingCoverage,
    FundingSettlement,
    funding_settlements_sha256,
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build realized funding calendar.")
    ap.add_argument("--raw", required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--version", default="FUNDING-CAL-v1")
    ap.add_argument("--interval-ms", type=int, default=8 * 3600 * 1000)
    ap.add_argument("--endpoint",
                    default="https://fapi.binance.com/fapi/v1/fundingRate")
    ap.add_argument("--acquired-utc", default="UNKNOWN")
    ap.add_argument("--coverage-start-ms", type=int, default=None)
    ap.add_argument("--coverage-end-ms", type=int, default=None,
                    help="endTime inclusivo; la cobertura se expresa [start,end+1)")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--acquired-ms", type=int, default=0)
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
    response_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    cal = {
        "version": str(args.version),
        "source": "exchange-funding-history (Binance USD-M fundingRate)",
        "interval_ms": int(args.interval_ms),
        "symbol": symbol,
        "settlements": settlements,
        "provenance": {
            "endpoint": str(args.endpoint),
            "acquired_utc": str(args.acquired_utc),
            "response_sha256": response_sha,
            "n_raw": len(rows),
            "n_settlements": len(settlements),
            "coverage_ms": ([settlements[0]["settlement_ms"],
                             settlements[-1]["settlement_ms"]]
                            if settlements else [None, None]),
            "note": "realized venue rates; quoted/next estimates never "
                    "substitute them",
        },
    }
    if (args.coverage_start_ms is None) != (args.coverage_end_ms is None):
        raise ValueError(
            "--coverage-start-ms y --coverage-end-ms deben proporcionarse juntos")
    if args.coverage_start_ms is not None:
        if args.coverage_end_ms < args.coverage_start_ms:
            raise ValueError("coverage endTime debe ser >= startTime")
        normalized = tuple(
            FundingSettlement(int(item["settlement_ms"]),
                              float(item["rate_bps"]))
            for item in settlements)
        row_symbols = sorted({str(row.get("symbol", "")).upper()
                              for row in rows if row.get("symbol")})
        foreign = [item for item in row_symbols if item != symbol]
        truncated = len(rows) >= int(args.limit)
        if truncated:
            status = "incomplete"
            reason = "response reached the requested limit and may be truncated"
        elif foreign:
            status = "incomplete"
            reason = "response contains rows for a different symbol: %s" % foreign
        else:
            status = "unknown"
            reason = (
                "venue response alone does not prove complete history or "
                "absence of unreturned settlements")
        coverage = FundingCoverage(
            version="funding-coverage/v1",
            status=status,
            symbol=symbol,
            venue="binance-usd-m",
            source="exchange-funding-history (Binance USD-M fundingRate)",
            interval_start_ms=int(args.coverage_start_ms),
            interval_end_ms=int(args.coverage_end_ms) + 1,
            acquired_at_ms=int(args.acquired_ms),
            available_at_ms=int(args.acquired_ms),
            method="binance-funding-rate-response",
            evidence={
                "kind": "venue-response",
                "reference": str(args.endpoint),
                "statement": (
                    "saved venue response; completeness and maximum "
                    "publication delay are not guaranteed by the response"),
                "sha256": response_sha,
                "valid_from_ms": int(args.coverage_start_ms),
                "valid_until_ms": int(args.coverage_end_ms) + 1,
            },
            request={
                "endpoint": str(args.endpoint),
                "params": {
                    "symbol": symbol,
                    "startTime": int(args.coverage_start_ms),
                    "endTime": int(args.coverage_end_ms),
                    "limit": int(args.limit),
                },
                "http_status": 200,
                "sent_at_ms": int(args.acquired_ms),
                "completed_at_ms": int(args.acquired_ms),
            },
            response={
                "sha256": response_sha,
                "row_count": len(rows),
                "symbols": row_symbols,
                "pagination": {
                    "pages": 1,
                    "complete": not truncated,
                    "truncated": truncated,
                },
                "settlement_sha256": funding_settlements_sha256(normalized),
                "first_settlement_ms": (
                    normalized[0].settlement_ms if normalized else None),
                "last_settlement_ms": (
                    normalized[-1].settlement_ms if normalized else None),
            },
            publication_delay_ms=None,
            publication_delay_evidence={
                "kind": "UNKNOWN",
                "reference": "Binance USD-M market-data documentation",
                "statement": "no official maximum publication delay is documented",
                "sha256": response_sha,
            },
            reason=reason,
        )
        cal["coverage"] = coverage.to_dict()
    Path(args.out).write_text(json.dumps(cal, indent=1), encoding="utf-8")
    print("symbol=%s settlements=%d out=%s" % (symbol, len(settlements),
                                              args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
