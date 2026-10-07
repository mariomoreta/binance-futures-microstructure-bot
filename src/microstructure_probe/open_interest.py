"""P1-07 open-interest intelligence (public REST polling + tracker, in-memory).

Source: Binance USD-M ``GET /fapi/v1/openInterest?symbol=<SYM>`` (public,
no key; verified live 2026-10-08 -> {"symbol", "openInterest" (base-asset
units, string), "time" (exchange ms)}; see docs/MARKET_DATA.md). A bounded
async poller (one request per symbol per tick, configurable interval,
default 60s) appends timestamped samples; failures are counted and never
break websocket processing. Historical-statistics bootstrapping via
``/futures/data/openInterestHist`` was evaluated and deliberately deferred
(single-provenance history, bounded scope; see docs/DECISIONS.md).

Definitions (deterministic, no lookahead, UNKNOWN is None never 0):
- Sample: (fetch_ms [local receipt], exchange_time_ms, oi_base).
  Non-finite or negative OI refused + counted; strictly-older fetch times
  refused + counted (monotonic poller by construction).
- Horizon h in {1m, 5m, 15m}: current = latest sample with fetch_ms <=
  as_of; anchor(h) = latest sample with fetch_ms <= as_of - h, accepted
  only within max(60s, h/20) (same tolerance family as returns). delta =
  current - anchor; delta_pct = delta / anchor (None when anchor == 0);
  rate = delta / actual_elapsed_s. All None until anchor exists.
- Acceleration (1m): change in the 1m OI rate between consecutive windows:
  accel = (rate_now - rate_prev) / elapsed_s, where rate_prev is the 1m
  rate ending 60s earlier. Timestamp-aware; None until ~2m of span.
- Price/OI context (descriptive regime labels ONLY, never signals): joint
  sign of the h-horizon log price return (supplied by the caller from the
  P1-04 engine) and the OI delta: PRICE_UP_OI_UP / PRICE_UP_OI_DOWN /
  PRICE_DOWN_OI_UP / PRICE_DOWN_OI_DOWN; exact-zero on either side ->
  MIXED; either side unavailable -> UNKNOWN. No long/short/squeeze or
  bullish/bearish claims — methodology unvalidated.
- Freshness: as_of - last fetch_ms (None before the first sample). stale =
  freshness beyond 3x the poll interval (honest age display; stale rows
  stay visible, never hidden).

This module holds no trading, signaling, or execution paths.
"""

from __future__ import annotations

import json
import math
import time
import urllib.request
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from .telemetry import RunningDistribution

OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest"
USER_AGENT = "microstructure-probe/0.6"

# OI delta/rate horizons.
OI_HORIZONS_MS: Dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
}
OI_HORIZON_ORDER = ("1m", "5m", "15m")

# Samples retained per symbol (2000 @ 60s ~= 33h; covers 15m + tolerance).
OI_KEEP_SAMPLES = 2000


def anchor_tolerance_ms(timeframe_ms: int) -> int:
    """Max acceptable staleness of an anchor behind its ideal target."""
    return max(60_000, timeframe_ms // 20)


def fetch_open_interest(symbol: str, timeout: float = 15.0) -> Dict[str, Any]:
    """Public GET /fapi/v1/openInterest. No credentials of any kind."""
    url = f"{OPEN_INTEREST_URL}?symbol={symbol.upper()}"
    request = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.load(response)
    if not isinstance(parsed, dict):
        raise ValueError("openInterest response is not an object")
    return parsed


def parse_oi_payload(payload: Any) -> Optional[Tuple[float, Optional[int]]]:
    """(oi_base, exchange_time_ms) or None when unusable. Never raises."""
    if not isinstance(payload, dict):
        return None
    try:
        oi = float(payload.get("openInterest"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(oi) or oi < 0:
        return None
    exchange_ms: Optional[int] = None
    try:
        raw_time = payload.get("time")
        if raw_time is not None:
            exchange_ms = int(raw_time)
            if isinstance(exchange_ms, bool):
                exchange_ms = None
    except (TypeError, ValueError):
        exchange_ms = None
    return oi, exchange_ms


def price_oi_context(price_return: Optional[float],
                     oi_delta: Optional[float]) -> str:
    """Descriptive joint regime label. Pure function, no thresholds."""
    if price_return is None or oi_delta is None:
        return "UNKNOWN"
    try:
        ret = float(price_return)
        delta = float(oi_delta)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if not math.isfinite(ret) or not math.isfinite(delta):
        return "UNKNOWN"
    if ret == 0.0 or delta == 0.0:
        return "MIXED"
    if ret > 0 and delta > 0:
        return "PRICE_UP_OI_UP"
    if ret > 0 and delta < 0:
        return "PRICE_UP_OI_DOWN"
    if ret < 0 and delta > 0:
        return "PRICE_DOWN_OI_UP"
    return "PRICE_DOWN_OI_DOWN"


class SymbolOITracker:
    """Timestamped OI history for one LIVE symbol (bounded deque)."""

    def __init__(self, stale_after_ms: int = 180_000) -> None:
        self._samples: Deque[Tuple[int, Optional[int], float]] = deque(
            maxlen=OI_KEEP_SAMPLES)
        self.stale_after_ms = max(int(stale_after_ms), 1)
        self.samples_total = 0
        self.dropped_invalid = 0
        self.dropped_late = 0
        self._dirty: List[Tuple[int, Optional[int], float]] = []

    def ingest(self, fetch_ms: int, exchange_time_ms: Optional[int],
               oi_base: float) -> bool:
        """Append one poll sample. False when refused (counted)."""
        try:
            fetch = int(fetch_ms)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            self.dropped_invalid += 1
            return False
        if (isinstance(oi_base, bool) or not isinstance(oi_base, (int, float))
                or not math.isfinite(oi_base) or oi_base < 0):
            self.dropped_invalid += 1
            return False
        if self._samples and fetch < self._samples[-1][0]:
            self.dropped_late += 1
            return False
        if (exchange_time_ms is not None
                and (isinstance(exchange_time_ms, bool)
                     or not isinstance(exchange_time_ms, int))):
            try:
                exchange_time_ms = int(exchange_time_ms)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                exchange_time_ms = None
        sample = (fetch, exchange_time_ms, float(oi_base))
        self._samples.append(sample)
        self._dirty.append(sample)
        self.samples_total += 1
        return True

    def drain_new_samples(self) -> List[Tuple[int, Optional[int], float]]:
        """Samples since the last drain (for persistence)."""
        rows = list(self._dirty)
        self._dirty.clear()
        return rows

    def restore(self, samples: List[Tuple[int, Optional[int], float]]) -> int:
        """Reload persisted samples (restart continuity). Sorted, bounded."""
        ordered = sorted((int(f), e, float(o)) for f, e, o in samples
                         if isinstance(f, int) and not isinstance(f, bool))
        accepted = 0
        for sample in ordered[-OI_KEEP_SAMPLES:]:
            self._samples.append(sample)
            accepted += 1
        return accepted

    def _at_or_before(self, target_ms: int
                      ) -> Optional[Tuple[int, Optional[int], float]]:
        """Latest sample with fetch_ms <= target (no lookahead)."""
        best: Optional[Tuple[int, Optional[int], float]] = None
        for sample in self._samples:
            if sample[0] > target_ms:
                break
            best = sample
        return best

    def horizon_feature(self, horizon: str, as_of_ms: int) -> Dict[str, Any]:
        """OI delta/rate over one horizon. UNKNOWN until anchored."""
        window_ms = OI_HORIZONS_MS[horizon]
        current = self._at_or_before(int(as_of_ms))
        record: Dict[str, Any] = {
            "horizon": horizon, "window_ms": window_ms,
            "current_oi": None, "current_fetch_ms": None,
            "anchor_oi": None, "anchor_fetch_ms": None,
            "delta": None, "delta_pct": None, "rate_per_s": None,
        }
        if current is None:
            return record
        record["current_oi"] = current[2]
        record["current_fetch_ms"] = current[0]
        target = current[0] - window_ms
        anchor = self._at_or_before(target)
        if anchor is None:
            return record
        if target - anchor[0] > anchor_tolerance_ms(window_ms):
            return record
        elapsed_s = (current[0] - anchor[0]) / 1000.0
        if elapsed_s <= 0:
            return record
        delta = current[2] - anchor[2]
        record["anchor_oi"] = anchor[2]
        record["anchor_fetch_ms"] = anchor[0]
        record["delta"] = delta
        record["delta_pct"] = (delta / anchor[2]
                               if anchor[2] != 0 else None)
        record["rate_per_s"] = delta / elapsed_s
        return record

    def acceleration(self, as_of_ms: int) -> Optional[float]:
        """Change in the 1m OI rate between consecutive windows (/s^2)."""
        window_ms = OI_HORIZONS_MS["1m"]
        now = self.horizon_feature("1m", as_of_ms)
        if now["rate_per_s"] is None or now["current_fetch_ms"] is None:
            return None
        prev_as_of = now["current_fetch_ms"] - window_ms
        prev = self.horizon_feature("1m", prev_as_of)
        if prev["rate_per_s"] is None or prev["current_fetch_ms"] is None:
            return None
        elapsed_s = (now["current_fetch_ms"] - prev["current_fetch_ms"]) / 1000.0
        if elapsed_s <= 0:
            return None
        return (now["rate_per_s"] - prev["rate_per_s"]) / elapsed_s

    def snapshot(self, symbol: str, as_of_ms: int, subscribed: bool,
                 price_return_1m: Optional[float] = None) -> Dict[str, Any]:
        """Compact per-symbol OI record (persisted + dashboard/API)."""
        latest = self._samples[-1] if self._samples else None
        freshness_ms = (int(as_of_ms) - latest[0] if latest is not None
                        else None)
        horizons = {h: self.horizon_feature(h, as_of_ms)
                    for h in OI_HORIZON_ORDER}
        accel = self.acceleration(as_of_ms)
        contexts = {h: price_oi_context(
                        price_return_1m if h == "1m" else None,
                        horizons[h]["delta"])
                    for h in OI_HORIZON_ORDER}
        return {
            "symbol": symbol,
            "subscribed": subscribed,
            "live": subscribed and latest is not None,
            "as_of_ms": int(as_of_ms),
            "freshness_ms": freshness_ms,
            "stale": (freshness_ms is not None
                      and freshness_ms > self.stale_after_ms),
            "stale_after_ms": self.stale_after_ms,
            "current_oi": latest[2] if latest else None,
            "exchange_time_ms": latest[1] if latest else None,
            "last_fetch_ms": latest[0] if latest else None,
            "samples": len(self._samples),
            "samples_total": self.samples_total,
            "dropped_invalid": self.dropped_invalid,
            "dropped_late": self.dropped_late,
            "source": "GET /fapi/v1/openInterest",
            "horizons": horizons,
            "acceleration_per_s2": accel,
            "price_oi_context": contexts,
        }


class OpenInterestTracker:
    """Multi-symbol OI state (poll-fed, history bounded per symbol)."""

    def __init__(self, symbols: tuple = (),
                 stale_after_ms: int = 180_000) -> None:
        self._allowed = ({str(s).upper() for s in symbols} if symbols else None)
        self._trackers: Dict[str, SymbolOITracker] = {}
        self.stale_after_ms = max(int(stale_after_ms), 1)
        self.dropped_unknown = 0

    def ingest(self, symbol: str, fetch_ms: int,
               exchange_time_ms: Optional[int], oi_base: float) -> bool:
        """Ingest one poll sample. Unknown symbols refused (counted)."""
        key = str(symbol).upper()
        if self._allowed is not None and key not in self._allowed:
            self.dropped_unknown += 1
            return False
        tracker = self._trackers.get(key)
        if tracker is None:
            tracker = self._trackers[key] = SymbolOITracker(
                stale_after_ms=self.stale_after_ms)
        return tracker.ingest(fetch_ms, exchange_time_ms, oi_base)

    def snapshot_all(self, as_of_ms: int,
                     price_returns_1m: Optional[Dict[str, Optional[float]]] = None
                     ) -> List[Dict[str, Any]]:
        """One record per known symbol (subscribed set = allowed set)."""
        out = []
        for symbol in sorted(self._trackers):
            subscribed = (self._allowed is None) or (symbol in self._allowed)
            ret = (price_returns_1m or {}).get(symbol)
            out.append(self._trackers[symbol].snapshot(
                symbol, as_of_ms, subscribed, ret))
        return out

    def drain_new_samples(self) -> List[Dict[str, Any]]:
        """New OI samples since the last drain, with symbols."""
        rows = []
        for symbol in sorted(self._trackers):
            for fetch_ms, exchange_ms, oi in (
                    self._trackers[symbol].drain_new_samples()):
                rows.append({"symbol": symbol, "fetch_ms": fetch_ms,
                             "exchange_time_ms": exchange_ms, "oi": oi})
        return rows

    def restore_samples(self, rows: List[Dict[str, Any]]) -> int:
        """Reload persisted samples per symbol (no fabrication)."""
        by_symbol: Dict[str, List[Tuple[int, Optional[int], float]]] = {}
        for row in rows:
            try:
                symbol = str(row["symbol"]).upper()
                sample = (int(row["fetch_ms"]),
                          (int(row["exchange_time_ms"])
                           if row.get("exchange_time_ms") is not None else None),
                          float(row["oi"]))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            if self._allowed is not None and symbol not in self._allowed:
                continue
            by_symbol.setdefault(symbol, []).append(sample)
        accepted = 0
        for symbol, samples in by_symbol.items():
            tracker = self._trackers.get(symbol)
            if tracker is None:
                tracker = self._trackers[symbol] = SymbolOITracker(
                    stale_after_ms=self.stale_after_ms)
            accepted += tracker.restore(samples)
        return accepted

    def stats(self) -> Dict[str, Any]:
        """Tracker counters per symbol (probe summary block)."""
        per_symbol = {}
        for symbol in sorted(self._trackers):
            tracker = self._trackers[symbol]
            per_symbol[symbol] = {
                "samples": len(tracker._samples),
                "samples_total": tracker.samples_total,
                "dropped_invalid": tracker.dropped_invalid,
                "dropped_late": tracker.dropped_late,
            }
        return {
            "dropped_unknown": self.dropped_unknown,
            "symbols": per_symbol,
        }


class OpenInterestPoller:
    """Bounded shared REST scheduler: one round per tick, never per-message.

    A tick polls every configured symbol exactly once, sequentially, then
    sleeps `interval_seconds`. Failures increment counters and keep prior
    samples (stale honestly). The poller never touches websocket processing.
    """

    def __init__(self, symbols: tuple,
                 fetch_fn: Callable[[str], Dict[str, Any]] = fetch_open_interest,
                 interval_seconds: float = 60.0,
                 timeout_seconds: float = 15.0,
                 wall_clock_ms: Optional[Callable[[], float]] = None,
                 latency_max_samples: int = 20000) -> None:
        self.symbols = tuple(str(s).upper() for s in symbols)
        self._fetch = fetch_fn
        self.interval_seconds = max(float(interval_seconds), 1.0)
        self.timeout_seconds = max(float(timeout_seconds), 1.0)
        self._wall_clock_ms = wall_clock_ms
        self.requests = 0
        self.successes = 0
        self.failures = 0
        self.last_tick_ms: Optional[float] = None
        self.last_error: Optional[str] = None
        self._latency = RunningDistribution(max(1, int(latency_max_samples)))

    def poll_once(self, tracker: OpenInterestTracker) -> Dict[str, int]:
        """One bounded round: each symbol polled at most once."""
        now_ms = (self._wall_clock_ms() if self._wall_clock_ms is not None
                  else time.time() * 1000.0)
        self.last_tick_ms = now_ms
        outcome = {"requested": 0, "ok": 0, "failed": 0}
        for symbol in self.symbols:
            outcome["requested"] += 1
            self.requests += 1
            start_ns = time.perf_counter_ns()
            try:
                parsed = parse_oi_payload(self._fetch(symbol))
            except Exception as exc:  # never break the caller
                parsed = None
                self.last_error = f"{type(exc).__name__}: {exc}"
            finally:
                elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
                self._latency.add(max(elapsed_ms, 0.0))
            if parsed is None:
                outcome["failed"] += 1
                self.failures += 1
                continue
            oi, exchange_ms = parsed
            if tracker.ingest(symbol, int(now_ms), exchange_ms, oi):
                outcome["ok"] += 1
                self.successes += 1
            else:
                outcome["failed"] += 1
                self.failures += 1
        return outcome

    def stats(self) -> Dict[str, Any]:
        """Poll telemetry (probe summary block)."""
        return {
            "symbols": list(self.symbols),
            "interval_seconds": self.interval_seconds,
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "last_tick_ms": self.last_tick_ms,
            "last_error": self.last_error,
            "latency_ms": self._latency.snapshot(),
        }
