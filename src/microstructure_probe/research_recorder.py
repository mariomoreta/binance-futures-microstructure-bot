"""P1-11C prospective microstructure research recorder.

Runs INSIDE the canonical MarketProbe process (no second process, no second
registry, no independent launcher). The probe owns exactly one recorder:
it starts when MarketProbe starts and stops/drains when MarketProbe exits.

Path: validated live engine state -> bounded in-memory aggregation ->
bounded async/off-thread SQLite persistence into the historical research DB
(data/historical/historical.db by default; never microprobe.db).

Failure isolation: any research-DB error degrades the recorder only; the
operational feed never crashes because the recorder failed. A full queue
drops research writes with telemetry (never stalls the live engine).
"""

from __future__ import annotations

import math
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

FLOW_BUCKET_SIZES_S = (10, 60)
BOOK_BUCKET_S = 60


def _fnum(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


class _FlowBucket:
    __slots__ = ("start", "end", "size_s", "buy_not", "sell_not", "buy_base",
                 "sell_base", "trades", "buy_trades", "sell_trades", "o", "h",
                 "l", "c", "first_ms", "last_ms", "partial")

    def __init__(self, start: int, size_s: int) -> None:
        self.start = start
        self.end = start + size_s * 1000
        self.size_s = size_s
        self.buy_not = 0.0
        self.sell_not = 0.0
        self.buy_base = 0.0
        self.sell_base = 0.0
        self.trades = 0
        self.buy_trades = 0
        self.sell_trades = 0
        self.o = None
        self.h = None
        self.l = None
        self.c = None
        self.first_ms = None
        self.last_ms = None
        self.partial = False

    def add(self, event_ms: int, price: float, qty: float,
            buyer_is_maker: bool) -> None:
        notional = price * qty
        if buyer_is_maker:
            self.sell_not += notional
            self.sell_base += qty
            self.sell_trades += 1
        else:
            self.buy_not += notional
            self.buy_base += qty
            self.buy_trades += 1
        self.trades += 1
        if self.o is None:
            self.o = self.h = self.l = price
        else:
            if price > self.h:  # type: ignore[operator]
                self.h = price
            if price < self.l:  # type: ignore[operator]
                self.l = price
        self.c = price
        if self.first_ms is None:
            self.first_ms = event_ms
        self.last_ms = event_ms

    def row(self, symbol: str, quality: str) -> Dict[str, Any]:
        denom = self.buy_not + self.sell_not
        return {
            "symbol": symbol.upper(),
            "bucket_start": self.start,
            "bucket_end": self.end,
            "bucket_size_s": self.size_s,
            "buy_notional": self.buy_not,
            "sell_notional": self.sell_not,
            "delta": self.buy_not - self.sell_not,
            "delta_ratio": ((self.buy_not - self.sell_not) / denom
                            if denom > 0 else None),
            "buy_base": self.buy_base,
            "sell_base": self.sell_base,
            "base_volume": self.buy_base + self.sell_base,
            "notional_volume": self.buy_not + self.sell_not,
            "trade_count": self.trades,
            "buy_trades": self.buy_trades,
            "sell_trades": self.sell_trades,
            "price_open": self.o, "price_high": self.h,
            "price_low": self.l, "price_close": self.c,
            "first_event_ms": self.first_ms,
            "last_event_ms": self.last_ms,
            "data_quality": ("PARTIAL_" + quality if self.partial else quality),
        }


class _BookBucket:
    __slots__ = ("start", "end", "spreads", "imbs", "micros", "bid5", "ask5",
                 "bid20", "ask20", "gaps", "degraded", "crossed", "first_ms",
                 "last_ms", "n")

    def __init__(self, start: int) -> None:
        self.start = start
        self.end = start + BOOK_BUCKET_S * 1000
        self.spreads: List[float] = []
        self.imbs: List[float] = []
        self.micros: List[float] = []
        self.bid5: List[float] = []
        self.ask5: List[float] = []
        self.bid20: List[float] = []
        self.ask20: List[float] = []
        self.gaps = 0
        self.degraded = 0
        self.crossed = 0
        self.first_ms = None
        self.last_ms = None
        self.n = 0

    def add(self, event_ms: int, features: Dict[str, Any],
            degraded: bool, gap: bool, crossed: bool) -> None:
        sp = _fnum(features.get("spread_bps"))
        if sp is not None:
            self.spreads.append(sp)
        im = _fnum(features.get("imbalance_notional"))
        if im is None:
            im = _fnum(features.get("imbalance_qty"))
        if im is not None:
            self.imbs.append(im)
        mi = _fnum(features.get("microprice_displacement_bps"))
        if mi is not None:
            self.micros.append(mi)
        try:
            depth = features.get("depth", {})
            self.bid5.append(float(depth["top5"]["bid_notional"]))
            self.ask5.append(float(depth["top5"]["ask_notional"]))
            self.bid20.append(float(depth["top20"]["bid_notional"]))
            self.ask20.append(float(depth["top20"]["ask_notional"]))
        except (KeyError, TypeError, ValueError):
            pass
        if gap:
            self.gaps += 1
        if degraded:
            self.degraded += 1
        if crossed:
            self.crossed += 1
        if self.first_ms is None:
            self.first_ms = event_ms
        self.last_ms = event_ms
        self.n += 1

    @staticmethod
    def _mm(vals: List[float]):
        if not vals:
            return None, None, None
        return min(vals), sum(vals) / len(vals), max(vals)

    def row(self, symbol: str) -> Dict[str, Any]:
        smin, smean, smax = self._mm(self.spreads)
        imin, imean, imax = self._mm(self.imbs)
        mmin, mmean, mmax = self._mm(self.micros)
        return {
            "symbol": symbol.upper(),
            "bucket_start": self.start,
            "bucket_end": self.end,
            "sample_count": self.n,
            "spread_min": smin, "spread_mean": smean, "spread_max": smax,
            "imb_min": imin, "imb_mean": imean, "imb_max": imax,
            "micro_min": mmin, "micro_mean": mmean, "micro_max": mmax,
            "bid5_mean": (sum(self.bid5) / len(self.bid5)) if self.bid5 else None,
            "ask5_mean": (sum(self.ask5) / len(self.ask5)) if self.ask5 else None,
            "bid20_mean": (sum(self.bid20) / len(self.bid20)) if self.bid20 else None,
            "ask20_mean": (sum(self.ask20) / len(self.ask20)) if self.ask20 else None,
            "depth_gaps": self.gaps, "degraded": self.degraded,
            "crossed": self.crossed, "first_event_ms": self.first_ms,
            "last_event_ms": self.last_ms,
        }


class ResearchRecorder:
    """Bounded non-blocking prospective flow/book recorder (probe-owned)."""

    def __init__(self, db_path: Optional[Path] = None,
                 max_queue: int = 2000,
                 retention_days: Optional[Dict[str, int]] = None,
                 enabled: bool = True,
                 history_store: Optional[Any] = None,
                 run_id: Optional[str] = None,
                 rules_version: Optional[str] = None,
                 dataset_id: Optional[str] = None,
                 clock_ms: Optional[Any] = None) -> None:
        """Optional ``history_store`` overrides the default HistoryStore
        for read-only count lookups in status() (Route-C injection point
        for hermetic tests). When None, behavior is unchanged.
        Optional linkage context (run_id / rules_version / dataset_id)
        stamps flushed bucket rows; all None by default (NULL = UNKNOWN).
        as_of_ms is stamped at flush wall time (persist-availability),
        price_source per table ("aggTrade" flow, "depth20" book)."""
        self.db_path = Path(db_path) if db_path else None
        self._history_store = history_store
        self.run_id = run_id
        self.rules_version = rules_version
        self.dataset_id = dataset_id
        # Inyeccion opcional del reloj (solo para pilotos/hermeticos). Por
        # defecto se conserva el reloj de pared historico.
        self._clock_ms = clock_ms
        self.max_queue = max(16, int(max_queue))
        self.retention_days = retention_days or {"flow_10s": 7, "flow_1m": 90,
                                                 "book_1m": 90}
        self.enabled = bool(enabled)
        self.state = "DISABLED" if not enabled else "READY"
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=self.max_queue)
        self._flow_open: Dict[tuple, _FlowBucket] = {}
        self._book_open: Dict[str, _BookBucket] = {}
        self._seen_flow_keys = set()
        self._writes = 0
        self._drops = 0
        self._errors = 0
        self._inflight = 0
        self._high_water = 0
        self._last_write_at: Optional[str] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_cleanup = 0.0

    # -- lifecycle (called by MarketProbe only) --------------------

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self.state = "RUNNING"
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker,
                                        name="research-recorder",
                                        daemon=True)
        self._thread.start()

    def _resolve_history(self):
        """Single choke point for HistoryStore access (R7).

        Injected store first, then explicit db_path, then the default
        operational store. Covers status(), the writer worker and
        retention cleanup alike; when nothing is injected and no path is
        set, behavior is unchanged (default store)."""
        if self._history_store is not None:
            return self._history_store
        from .history_store import HistoryStore as _HS
        return _HS(self.db_path) if self.db_path else _HS()

    def stop_and_drain(self, timeout: float = 10.0) -> Dict[str, Any]:
        # close open buckets as PARTIAL (explicitly marked, never complete)
        try:
            self._flush_partials()
        except Exception:
            pass
        self._stop.set()
        thr = self._thread
        if thr is not None:
            thr.join(timeout=timeout)
        self._thread = None
        if self.enabled:
            self.state = "STOPPED"
        return self.status()

    # -- live-engine hooks (never raise into the probe) -----------

    def finalize_symbol(self, symbol: str) -> Dict[str, int]:
        """Close a demoted symbol's open buckets as explicitly PARTIAL.

        Called on HOT demotion so the symbol's trailing buckets are
        persisted with PARTIAL quality instead of lingering open (they
        would otherwise never close — no more trades arrive). Flow
        buckets keep idempotent keys (no double-count on re-promotion);
        book partials are discarded per incomplete-bucket policy. Never
        raises; never blocks transport threads.
        """
        closed = {"flow": 0, "book_discarded": 0}
        try:
            sym = str(symbol).upper()
            for key in [k for k in self._flow_open if k[0] == sym]:
                bucket = self._flow_open.pop(key)
                bucket.partial = True
                try:
                    self._queue.put_nowait(
                        ("flow", key[1], sym, bucket))
                    closed["flow"] += 1
                except queue.Full:
                    with self._lock:
                        self._drops += 1
            if sym in self._book_open:
                del self._book_open[sym]
                closed["book_discarded"] += 1
        except Exception:
            pass
        return closed

    def record_trade(self, symbol: str, event_ms: int, price: float,
                     qty: float, buyer_is_maker: Any) -> None:
        if not self.enabled or self.state not in ("RUNNING", "READY"):
            return
        try:
            if not isinstance(buyer_is_maker, bool):
                return
            price_f = float(price)
            qty_f = float(qty)
            event_i = int(event_ms)
            if not (math.isfinite(price_f) and math.isfinite(qty_f)
                    and price_f > 0 and qty_f > 0):
                return
            sym = str(symbol).upper()
            for size_s in FLOW_BUCKET_SIZES_S:
                key = (sym, size_s)
                bstart = event_i - (event_i % (size_s * 1000))
                cur = self._flow_open.get(key)
                if cur is None:
                    cur = self._flow_open[key] = _FlowBucket(bstart, size_s)
                elif bstart != cur.start:
                    # close prior bucket (idempotent key prevents double-count)
                    self._enqueue(("flow", size_s, sym, cur))
                    cur = self._flow_open[key] = _FlowBucket(bstart, size_s)
                cur.add(event_i, price_f, qty_f, buyer_is_maker)
        except Exception:
            pass

    def record_book(self, symbol: str, event_ms: int,
                    features: Dict[str, Any], degraded: bool = False,
                    gap: bool = False, crossed: bool = False) -> None:
        if not self.enabled or self.state not in ("RUNNING", "READY"):
            return
        try:
            sym = str(symbol).upper()
            event_i = int(event_ms)
            bstart = event_i - (event_i % (BOOK_BUCKET_S * 1000))
            cur = self._book_open.get(sym)
            if cur is None:
                cur = self._book_open[sym] = _BookBucket(bstart)
            elif bstart != cur.start:
                self._enqueue(("book", BOOK_BUCKET_S, sym, cur))
                cur = self._book_open[sym] = _BookBucket(bstart)
            cur.add(event_i, features or {}, degraded, gap, crossed)
        except Exception:
            pass

    # -- internals -------------------------------------------------

    def _enqueue(self, item: Any) -> None:
        try:
            self._queue.put_nowait(item)
            with self._lock:
                self._inflight = self._queue.qsize()
                if self._inflight > self._high_water:
                    self._high_water = self._inflight
        except queue.Full:
            with self._lock:
                self._drops += 1

    def _flush_partials(self) -> None:
        for (sym, size_s), b in list(self._flow_open.items()):
            b.partial = True
            try:
                self._queue.put_nowait(("flow", size_s, sym, b))
            except queue.Full:
                with self._lock:
                    self._drops += 1
        self._flow_open.clear()
        # book partials are discarded (explicit policy: incomplete 1m book
        # buckets are never treated as complete)
        self._book_open.clear()

    def _stamp(self, row: Dict[str, Any], price_source: str) -> Dict[str, Any]:
        """Attach linkage context at flush time (never at event time).

        as_of_ms is the persist-availability wall time — distinct from
        event time (first/last_event_ms) and bucket close. Receive
        timestamps do not exist here and are never fabricated.
        """
        row["run_id"] = self.run_id
        row["rules_version"] = self.rules_version
        try:
            if self._clock_ms is not None:
                row["as_of_ms"] = int(self._clock_ms())
            else:
                row["as_of_ms"] = int(time.time() * 1000)
        except Exception:
            row["as_of_ms"] = None
        row["price_source"] = price_source
        row["dataset_id"] = self.dataset_id
        return row

    def _worker(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                kind = item[0]
                db = self._resolve_history()
                if kind == "flow":
                    _, size_s, sym, bucket = item
                    key = (sym, int(size_s), int(bucket.start))
                    if key in self._seen_flow_keys:
                        continue
                    self._seen_flow_keys.add(key)
                    table = "research_flow_10s" if int(size_s) == 10 \
                        else "research_flow_1m"
                    db.store_research_flow(
                        table, [self._stamp(bucket.row(sym, "OK"),
                                            "aggTrade")])
                else:
                    _, _, sym, bucket = item
                    if bucket.n == 0:
                        continue
                    db.store_research_book(
                        [self._stamp(bucket.row(sym), "depth20")])
                with self._lock:
                    self._writes += 1
                    try:
                        self._last_write_at = time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    except Exception:
                        pass
            except Exception:
                with self._lock:
                    self._errors += 1
                    if self.state == "RUNNING":
                        self.state = "DEGRADED"
            finally:
                with self._lock:
                    self._inflight = self._queue.qsize()
                # periodic retention (not every tick): at most hourly
                now = time.monotonic()
                if now - self._last_cleanup > 3600:
                    self._last_cleanup = now
                    try:
                        self._resolve_history().research_retention_cleanup(
                            self.retention_days)
                    except Exception:
                        pass

    def status(self) -> Dict[str, Any]:
        with self._lock:
            counts = {"flow_10s": 0, "flow_1m": 0, "book_1m": 0}
            try:
                raw = self._resolve_history().research_counts()
                counts = {"flow_10s": raw.get("research_flow_10s", 0),
                          "flow_1m": raw.get("research_flow_1m", 0),
                          "book_1m": raw.get("research_book_1m", 0)}
            except Exception:
                pass
            return {
                "enabled": self.enabled,
                "state": self.state,
                "writes": self._writes,
                "drops": self._drops,
                "errors": self._errors,
                "inflight": self._queue.qsize(),
                "high_water": self._high_water,
                "flow_10s_rows": counts["flow_10s"],
                "flow_1m_rows": counts["flow_1m"],
                "book_1m_rows": counts["book_1m"],
                "last_write_at": self._last_write_at,
            }

    def storage_estimate(self, symbols: int) -> Dict[str, Any]:
        # measured SQLite row sizes (~120B flow, ~150B book with overhead -> use 200B safe)
        per_row = 200
        f10_day = (86400 // 10) * symbols
        f1m_day = (86400 // 60) * symbols
        b1m_day = (86400 // 60) * symbols
        return {
            "rows_per_day_per_symbol": {"flow_10s": 8640, "flow_1m": 1440,
                                        "book_1m": 1440},
            "rows_per_day": {"flow_10s": f10_day, "flow_1m": f1m_day,
                             "book_1m": b1m_day},
            "bytes_per_day": (f10_day + f1m_day + b1m_day) * per_row,
            "retention": dict(self.retention_days),
            "bytes_retention_total": (
                f10_day * 7 + f1m_day * 90 + b1m_day * 90) * per_row,
            "per_symbol_retention_bytes": (
                8640 * 7 + 1440 * 90 + 1440 * 90) * per_row,
        }
