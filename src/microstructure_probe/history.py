"""P1-11B historical ingestion orchestration + CLI.

Pipeline per (symbol, interval, source):
  resume-point (coverage table) → listing-aware earliest-bar probe →
  bounded forward pagination → normalize → quality validation (CLOSED
  candles only; partial final candle excluded, never stored) → idempotent
  upsert → coverage + gap rows → run ledger update.

Gap policy: missing history stays UNKNOWN/GAP (rows absent, ranges in
historical_gaps). No zeros, no forward-fill, no interpolation — P1-11C
must exclude events spanning invalid gaps.

CLI (safe defaults: explicit symbols, 7d, 25 requests max):
  python -m microstructure_probe.history status [--db PATH]
  python -m microstructure_probe.history fetch --symbol BTCUSDT
      [--interval 1h] [--source klines|mark_klines] [--days 7]
      [--max-requests 25] [--dry-run]
  python -m microstructure_probe.history verify --symbol X --interval I
      [--source S]
No bulk/all-symbols mode exists in P1-11B (pilot only, by construction).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .history_client import INTERVAL_MS, OI_PERIODS, HistoryClient
from .history_store import HistoryStore

SOURCES = ("klines", "mark_klines", "oi_hist")

DEFAULT_DAYS = 7
DEFAULT_MAX_REQUESTS = 25


def normalize_kline(arr: List[Any]) -> Dict[str, Any]:
    """Binance 12-field kline array → dict (prices kept as strings)."""
    return {
        "open_time": int(arr[0]),
        "open": str(arr[1]),
        "high": str(arr[2]),
        "low": str(arr[3]),
        "close": str(arr[4]),
        "base_volume": str(arr[5]),
        "close_time": int(arr[6]),
        "quote_volume": str(arr[7]),
        "trade_count": int(arr[8]),
        "taker_buy_base": str(arr[9]),
        "taker_buy_quote": str(arr[10]),
    }


def normalize_mark_kline(arr: List[Any]) -> Dict[str, Any]:
    """Mark-price klines: NO volume fields (API serves zeros there)."""
    return {
        "open_time": int(arr[0]),
        "open": str(arr[1]),
        "high": str(arr[2]),
        "low": str(arr[3]),
        "close": str(arr[4]),
        "close_time": int(arr[6]),
        "trade_count": int(arr[8]),
    }


def _fnum(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def validate_bars(rows: List[Dict[str, Any]], interval: str,
                  now_ms: Optional[int] = None) -> Dict[str, Any]:
    """Quality report over normalized bars (CLOSED candles for research).

    Returns counts + gap ranges + malformed list + the closed subset.
    The partial/in-progress final candle is EXCLUDED from `closed`.
    """
    step = INTERVAL_MS[interval]
    now = int(now_ms) if now_ms is not None else int(time.time() * 1000)
    seen: Dict[int, Dict[str, Any]] = {}
    duplicates = 0
    for r in rows:
        ot = int(r["open_time"])
        if ot in seen:
            duplicates += 1
        else:
            seen[ot] = r
    opens = sorted(seen)
    partial = [ot for ot in opens if ot + step > now]
    closed = [ot for ot in opens if ot + step <= now]
    malformed: List[Dict[str, Any]] = []
    future: List[int] = []
    for ot in closed:
        r = seen[ot]
        o, h, low, c = (_fnum(r["open"]), _fnum(r["high"]),
                        _fnum(r["low"]), _fnum(r["close"]))
        problems = []
        if ot > now:
            future.append(ot)
            continue
        if None in (o, h, low, c):
            problems.append("non-numeric-ohlc")
        else:
            assert o is not None and h is not None and low is not None \
                and c is not None
            if h < low:
                problems.append("high<low")
            if o < 0 or h <= 0 or low <= 0 or c <= 0:
                problems.append("non-positive-price")
            if o > h or o < low or c > h or c < low:
                problems.append("open-close-outside-high-low")
        if r.get("close_time") is not None and \
                int(r["close_time"]) != ot + step - 1:
            problems.append("close-time-misaligned")
        if problems:
            malformed.append({"open_time": ot, "problems": problems})
    missing: List[Tuple[int, int, int]] = []
    if closed:
        expect = closed[0]
        idx = 0
        while expect <= closed[-1]:
            if idx < len(closed) and closed[idx] == expect:
                idx += 1
            else:
                run_start = expect
                while (idx >= len(closed) or closed[idx] != expect) \
                        and expect <= closed[-1]:
                    expect += step
                missing.append((run_start, expect - step,
                                (expect - run_start) // step))
                continue
            expect += step
        expected = (closed[-1] - closed[0]) // step + 1
    else:
        expected = 0
    bad_opens = {m["open_time"] for m in malformed} | set(future)
    good = [seen[ot] for ot in closed if ot not in bad_opens]
    return {
        "fetched": len(rows),
        "unique": len(seen),
        "duplicates": duplicates,
        "closed": len(closed),
        "partial_excluded": len(partial),
        "expected_bars": expected,
        "actual_bars": len(good),
        "missing_ranges": [{"missing_from": a, "missing_to": b,
                            "expected_count": c} for (a, b, c) in missing],
        "malformed": malformed,
        "future": future,
        "closed_rows": good,
    }


def ingest_series(client: HistoryClient, store: HistoryStore, symbol: str,
                  interval: str, source: str, days_back: float,
                  max_requests: int, run_id: int,
                  now_ms: Optional[int] = None) -> Dict[str, Any]:
    """Listing-aware bounded ingest of one series. Returns the run report."""
    symbol = symbol.upper()
    step = INTERVAL_MS[interval]
    now = int(now_ms) if now_ms is not None else int(time.time() * 1000)
    requested_start = now - int(days_back * 86_400_000)
    before = client.stats.requests
    earliest = client.earliest_bar(symbol, interval, source=source)
    actual_start = requested_start
    first_available: Optional[int] = None
    if earliest is not None:
        first_available = int(earliest[0])
        actual_start = max(requested_start, first_available)
    else:
        return {"symbol": symbol, "interval": interval, "source": source,
                "status": "no-data",
                "requests": client.stats.requests - before}
    resume_from: Optional[int] = None
    prev = store.get_coverage(symbol, interval, source)
    if prev and prev.get("last_open"):
        resume_from = int(prev["last_open"]) + step
        actual_start = max(actual_start, resume_from)
    end_ms = now - step  # closed candles only; partial excluded by construction
    budget = max_requests - (client.stats.requests - before)
    if budget <= 0 or actual_start > end_ms:
        report = validate_bars([], interval, now_ms=now)
    else:
        raw, page_info = client.paginate_klines(
            symbol, interval, actual_start, end_ms, source=source,
            max_pages=budget)
        norm = (normalize_kline if source == "klines"
                else normalize_mark_kline)
        report = validate_bars([norm(b) for b in raw], interval, now_ms=now)
        report["paged_skipped_ranges"] = page_info["skipped_ranges"]
        report["pages"] = page_info["pages"]
    closed_rows = report["closed_rows"]
    if source == "klines":
        written = store.upsert_klines(symbol, interval, closed_rows)
    else:
        written = store.upsert_mark_klines(symbol, interval, closed_rows)
    opens = sorted(int(r["open_time"]) for r in closed_rows)
    store.record_coverage(
        symbol, interval, source, requested_start, first_available,
        opens[0] if opens else None, opens[-1] if opens else None,
        report["expected_bars"], len(opens))
    store.record_gaps(symbol, interval, source,
                      [(g["missing_from"], g["missing_to"],
                        g["expected_count"])
                       for g in report["missing_ranges"]])
    report.update({
        "symbol": symbol, "interval": interval, "source": source,
        "status": "ok", "written": written,
        "requested_start": requested_start,
        "actual_start": actual_start,
        "resume_from": resume_from,
        "first_available_open_time": first_available,
        "requests": client.stats.requests - before,
    })
    report.pop("closed_rows", None)
    return report


def ingest_oi_series(client: HistoryClient, store: HistoryStore,
                     symbol: str, period: str, days_back: float,
                     max_requests: int, run_id: int,
                     now_ms: Optional[int] = None) -> Dict[str, Any]:
    """Bounded openInterestHist ingest (availability-limited by Binance).

    Stores only what the API actually serves (sumOpenInterest +
    sumOpenInterestValue + timestamp); never invents deeper history. Does
    NOT touch the live OI tracker.
    """
    symbol = symbol.upper()
    now = int(now_ms) if now_ms is not None else int(time.time() * 1000)
    requested_start = now - int(days_back * 86_400_000)
    before = client.stats.requests
    budget = max(1, max_requests - (client.stats.requests - before))
    rows, _pages = client.paginate_oi(symbol, period, requested_start, now,
                                      limit=500, max_pages=budget)
    norm = [{"ts": int(r["timestamp"]), "sum_oi": str(r["sumOpenInterest"]),
             "sum_oi_value": str(r["sumOpenInterestValue"])} for r in rows
            if "timestamp" in r and "sumOpenInterest" in r]
    seen: Dict[int, Dict[str, Any]] = {}
    dups = 0
    for r in norm:
        if r["ts"] in seen:
            dups += 1
        else:
            seen[r["ts"]] = r
    future = sum(1 for t in seen if t > now)
    kept = [seen[t] for t in sorted(seen) if t <= now]
    written = store.upsert_oi(symbol, period, kept)
    store.record_coverage(symbol, period, "oi_hist", requested_start,
                          kept[0]["ts"] if kept else None,
                          kept[0]["ts"] if kept else None,
                          kept[-1]["ts"] if kept else None,
                          len(kept) + dups, len(kept))
    return {"symbol": symbol, "interval": period, "source": "oi_hist",
            "status": "ok", "written": written, "fetched": len(rows),
            "duplicates": dups, "future": future,
            "first_ts": kept[0]["ts"] if kept else None,
            "last_ts": kept[-1]["ts"] if kept else None,
            "requests": client.stats.requests - before}


def cmd_status(args: argparse.Namespace) -> int:
    store = HistoryStore(Path(args.db))
    rows = store.coverage_summary()
    print(f"schema={store.schema_version()} series={len(rows)}"
          f" db={store.db_path}")
    for r in rows:
        print(f"  {r['symbol']} {r['interval']} {r['source']}:"
              f" bars={r['actual_bars']}/{r['expected_bars']}"
              f" ratio={r['coverage_ratio']} last={r['last_open']}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    store = HistoryStore(Path(args.db))
    client = HistoryClient()
    run_id = store.start_run({"argv": sys.argv[1:], "cmd": "fetch"})
    reports = []
    failures = 0
    for symbol in args.symbol:
        for interval in args.interval:
            for source in args.source:
                if args.dry_run:
                    step = INTERVAL_MS[interval]
                    now = int(time.time() * 1000)
                    pages = max(1, int(args.days * 86_400_000 / step /
                                      1000) + 1)
                    print(f"DRY {symbol} {interval} {source}:"
                          f" ~{pages} pages, budget {args.max_requests}")
                    continue
                try:
                    if source == "oi_hist":
                        if interval not in OI_PERIODS:
                            raise ValueError(
                                f"unsupported OI period {interval}")
                        rep = ingest_oi_series(
                            client, store, symbol, interval,
                            args.days, args.max_requests, run_id)
                    else:
                        rep = ingest_series(
                            client, store, symbol, interval, source,
                            args.days, args.max_requests, run_id)
                except Exception as exc:  # never half-record silently
                    failures += 1
                    rep = {"symbol": symbol, "interval": interval,
                           "source": source, "status": f"error: {exc}"}
                reports.append(rep)
                print(f"{rep.get('status')} {symbol} {interval} {source}:"
                      f" written={rep.get('written')} req={rep.get('requests')}"
                      f" gaps={len(rep.get('missing_ranges', []))}"
                      f" malformed={len(rep.get('malformed', []))}")
    store.finish_run(run_id, client.stats.requests, client.stats.retries,
                     failures + client.stats.failures,
                     "ok" if failures == 0 else "partial")
    return 0 if failures == 0 else 1


def cmd_verify(args: argparse.Namespace) -> int:
    store = HistoryStore(Path(args.db))
    bad = 0
    for symbol in args.symbol:
        for interval in args.interval:
            for source in args.source:
                if source == "oi_hist":
                    rows = store.load_oi(symbol, interval)
                    ts = [r["ts"] for r in rows]
                    dups = len(ts) - len(set(ts))
                    print(f"{symbol} {interval} {source}: stored={len(rows)}"
                          f" dups={dups}"
                          f" span={(max(ts) - min(ts)) if ts else None}")
                    if dups:
                        bad += 1
                    continue
                rows = store.load_bars(symbol, interval, source)
                rep = validate_bars(rows, interval)
                gaps = len(rep["missing_ranges"])
                mal = len(rep["malformed"])
                print(f"{symbol} {interval} {source}: stored={len(rows)}"
                      f" closed={rep['closed']} expected={rep['expected_bars']}"
                      f" actual={rep['actual_bars']} gaps={gaps}"
                      f" malformed={mal} partial={rep['partial_excluded']}"
                      f" dup={rep['duplicates']}")
                if mal or rep["duplicates"]:
                    bad += 1
    return 0 if bad == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Historical research ingestion (public REST only)")
    parser.add_argument("--db", default=str(
        Path("data") / "historical" / "historical.db"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="coverage summary")
    fetch = sub.add_parser("fetch", help="bounded historical fetch")
    fetch.add_argument("--symbol", action="append", required=True,
                       help="repeatable; no all-symbols mode in P1-11B")
    fetch.add_argument("--interval", action="append", default=None,
                       choices=sorted(INTERVAL_MS))
    fetch.add_argument("--source", action="append", default=None,
                       choices=list(SOURCES))
    fetch.add_argument("--days", type=float, default=DEFAULT_DAYS)
    fetch.add_argument("--max-requests", type=int,
                       default=DEFAULT_MAX_REQUESTS)
    fetch.add_argument("--dry-run", action="store_true")
    verify = sub.add_parser("verify", help="re-validate stored series")
    verify.add_argument("--symbol", action="append", required=True)
    verify.add_argument("--interval", action="append", default=None,
                        choices=sorted(INTERVAL_MS))
    verify.add_argument("--source", action="append", default=None,
                        choices=list(SOURCES))
    return parser


def _with_defaults(args: argparse.Namespace) -> argparse.Namespace:
    if not getattr(args, "interval", None):
        args.interval = ["1h"]
    if not getattr(args, "source", None):
        args.source = ["klines"]
    return args


def main(argv: Optional[List[str]] = None) -> int:
    args = _with_defaults(build_parser().parse_args(argv))
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "fetch":
        return cmd_fetch(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
