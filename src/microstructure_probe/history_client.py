"""P1-11B historical REST client (public endpoints only, no keys).

Covers Binance USD-M Futures public market-data endpoints needed for the
historical foundation; contracts verified live 2026-10-07 against
https://fapi.binance.com (the developers.binance.com site was unfetchable
from this environment — same precedent as P1-05/P1-06 — so every contract
below is behavior-verified, with the public OpenAPI enum cross-checked for
the interval list).

Measured 2026-10-07 (limit=2 probes, x-mbx-used-weight-1m deltas):
  klines limit=2 ............ ~1    (12-field arrays, WITH volume)
  markPriceKlines limit=2 .... ~1    (12-field arrays, volume fields "0"/0)
  aggTrades limit=2 .......... ~20   (dicts {a,p,q,nq,f,l,T,m}, fromId paging)
  openInterestHist limit=2 ... data-pool (no weight header on market-data
                                  host; periods 5m..1d, availability limited)
  exchangeInfo ............... ~1    (REQUEST_WEIGHT pool 2400/min)

Conservative assumed per-request weights (upper bounds; the limiter ALSO
reads the live x-mbx-used-weight-1m header adaptively and pauses at 2000):
  klines/mark: 10, aggTrades: 20, oi_hist: 5, exchange_info: 20.
Retry policy: 5xx + network errors, budget 5, exp backoff 1/2/4/8/16s +
jitter; 429 honors Retry-After (default 60s) with a budget of 2, then
abort; 418 aborts immediately (IP ban) — never spin against the limiter.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

BASE_URL = "https://fapi.binance.com"

ASSUMED_WEIGHTS = {
    "klines": 10,
    "mark_klines": 10,
    "aggtrades": 20,
    "oi_hist": 5,
    "exchange_info": 20,
}

INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000,
    "6h": 21_600_000, "8h": 28_800_000, "12h": 43_200_000,
    "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000,
    "1M": 2_592_000_000,
}

OI_PERIODS = ("5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d")

MAX_KLINE_LIMIT = 1500
MAX_OI_LIMIT = 500
MAX_AGG_LIMIT = 1000

WEIGHT_HARD_STOP = 2000
WEIGHT_POOL = 2400


class RateLimitExceeded(RuntimeError):
    """Raised on 418 (IP ban) or exhausted 429 budget — abort, never spin."""


class UpstreamBudgetExceeded(RateLimitExceeded):
    """Presupuesto upstream EJERCIDO antes del envío: ningún byte sale.

    La puerta del presupuesto (``attempt_gate``) denegó la reserva; el
    intento queda registrado como bloqueado y se aborta sin transporte
    (nunca se envía la petición)."""



@dataclass
class RequestStats:
    requests: int = 0
    retries: int = 0
    failures: int = 0
    weight_spent: int = 0


class HistoryClient:
    """Bounded, resumable public-REST client with limiter + backoff."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        max_weight_per_minute: int = 1200,
        request_timeout: float = 20.0,
        max_retries: int = 5,
        max_429: int = 2,
        sleep: Callable[[float], None] = time.sleep,
        opener: Optional[Callable] = None,
        execution_id: Optional[str] = None,
        attempt_gate: Optional[Any] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_weight = max_weight_per_minute
        self.timeout = request_timeout
        self.max_retries = max_retries
        self.max_429 = max_429
        self._sleep = sleep
        self._opener = opener or urllib.request.urlopen
        self.attempt_gate = attempt_gate
        self.stats = RequestStats()
        self._window_start = time.monotonic()
        self._window_weight = 0
        self._429_seen = 0
        self.execution_id = execution_id or f"exec-{int(time.monotonic() * 1000)}"
        self.upstream_requests: List[Dict[str, Any]] = []

    def _window_reset_if_needed(self) -> None:
        now = time.monotonic()
        if now - self._window_start >= 60.0:
            self._window_start = now
            self._window_weight = 0
            self._429_seen = 0

    def _admit(self, weight: int) -> None:
        self._window_reset_if_needed()
        while self._window_weight + weight > self.max_weight:
            wait = max(1.0, 60.0 - (time.monotonic() - self._window_start))
            self._sleep(min(wait, 5.0))
            self._window_reset_if_needed()

    def get(self, path: str, params: Dict[str, Any], weight: int) -> Tuple[Any, Dict[str, str]]:
        """GET with limiter, retries, 429/418 handling. Returns (json, hdrs)."""
        query = urllib.parse.urlencode(params)
        url = self.base_url + path + ("?" + query if query else "")
        req = urllib.request.Request(
            url, headers={"User-Agent": "microprobe-history-p11b/1.0"})
        attempts_5xx = 0
        while True:
            self._admit(weight)
            # Registrar cada intento upstream ANTES de enviarlo.
            upstream_entry: Dict[str, Any] = {
                "execution_id": self.execution_id,
                "endpoint": url,
                "symbol": params.get("symbol"),
                "interval": params.get("interval"),
                "range": f"{params.get('startTime', '')}-{params.get('endTime', '')}",
                "page": params.get("limit"),
                "retry": attempts_5xx,
                "result": "pending",
                "duration_ms": None,
            }
            self.upstream_requests.append(upstream_entry)
            # Reserva de presupuesto ANTES del transporte: si la puerta
            # deniega, aqui se aborta sin abrir ninguna conexion.
            if self.attempt_gate is not None:
                self.attempt_gate.before_send(upstream_entry)
            try:
                hdrs: Dict[str, str] = {}
                t0: Optional[float] = None
                try:
                    t0 = time.monotonic()
                    with self._opener(req, timeout=self.timeout) as resp:
                        raw = resp.read().decode("utf-8")
                        hdrs = {k.lower(): v for k, v in resp.headers.items()}
                        payload = json.loads(raw)
                    upstream_entry["result"] = "ok"
                    upstream_entry["duration_ms"] = int((time.monotonic() - t0) * 1000)
                except urllib.error.HTTPError as exc:
                    self.stats.failures += 1
                    started = t0 if t0 is not None else time.monotonic()
                    upstream_entry["result"] = f"http_{exc.code}"
                    upstream_entry["duration_ms"] = int((time.monotonic() - started) * 1000)
                    if exc.code == 418:
                        raise RateLimitExceeded(
                            f"HTTP 418 IP ban on {path} — aborting") from exc
                    if exc.code == 429:
                        self._429_seen += 1
                        if self._429_seen > self.max_429:
                            raise RateLimitExceeded(
                                f"HTTP 429 budget exhausted on {path}") from exc
                        retry_after = exc.headers.get("Retry-After") if \
                            exc.headers else None
                        try:
                            delay = float(retry_after) if retry_after else 60.0
                        except (TypeError, ValueError):
                            delay = 60.0
                        self.stats.retries += 1
                        upstream_entry["result"] = f"http_429_retry_{attempts_5xx + 1}"
                        upstream_entry["duration_ms"] = int(
                            (time.monotonic() - started) * 1000)
                        self._sleep(min(delay, 65.0))
                        continue
                    if 500 <= exc.code < 600 and attempts_5xx < self.max_retries:
                        attempts_5xx += 1
                        self.stats.retries += 1
                        upstream_entry["result"] = f"http_5xx_retry_{attempts_5xx}"
                        upstream_entry["duration_ms"] = int(
                            (time.monotonic() - started) * 1000)
                        self._sleep(_backoff(attempts_5xx))
                        continue
                    raise
                except (urllib.error.URLError, TimeoutError, ConnectionError,
                        json.JSONDecodeError) as exc:
                    self.stats.failures += 1
                    started = t0 if t0 is not None else time.monotonic()
                    upstream_entry["result"] = "connection_error"
                    upstream_entry["duration_ms"] = int((time.monotonic() - started) * 1000)
                    if attempts_5xx >= self.max_retries:
                        raise
                    attempts_5xx += 1
                    self.stats.retries += 1
                    self._sleep(_backoff(attempts_5xx))
                    continue
                self.stats.requests += 1
                self.stats.weight_spent += weight
                self._window_weight += weight
                used = hdrs.get("x-mbx-used-weight-1m")
                try:
                    if used is not None and int(used) >= WEIGHT_HARD_STOP:
                        self._sleep(60.0)
                        self._window_start = time.monotonic()
                        self._window_weight = 0
                except (TypeError, ValueError):
                    pass
                return payload, hdrs
            finally:
                # Cada intento (ok, error o reintento) cierra su fila del
                # ledger con el resultado real.
                if self.attempt_gate is not None:
                    self.attempt_gate.after_send(upstream_entry)

    def klines(self, symbol: str, interval: str, start_ms: int,
               end_ms: int, limit: int = 1000,
               source: str = "klines") -> Tuple[List[List[Any]], Dict]:
        path = ("/fapi/v1/klines" if source == "klines"
                else "/fapi/v1/markPriceKlines")
        weight = ASSUMED_WEIGHTS["klines" if source == "klines"
                                 else "mark_klines"]
        payload, hdrs = self.get(path, {
            "symbol": symbol.upper(), "interval": interval,
            "startTime": int(start_ms), "endTime": int(end_ms),
            "limit": int(limit)}, weight)
        if not isinstance(payload, list):
            raise ValueError(f"unexpected {source} shape: {type(payload)}")
        return payload, hdrs

    def paginate_klines(self, symbol: str, interval: str, start_ms: int,
                        end_ms: int, source: str = "klines",
                        limit: int = 1000,
                        max_pages: int = 200) -> Tuple[List[List[Any]], Dict]:
        """Deterministic forward pagination over [start_ms, end_ms].

        Next page starts at last_open + interval_ms (no duplicate boundary
        bars); verifies the first bar of each page is strictly after the
        previous page's last bar (no overlap, no skip-without-record).
        Returns (rows, {"pages": n, "skipped_ranges": [...]}).
        """
        step = INTERVAL_MS[interval]
        cursor = int(start_ms)
        rows: List[List[Any]] = []
        pages = 0
        skipped: List[List[int]] = []
        last_open: Optional[int] = None
        while cursor <= int(end_ms) and pages < max_pages:
            page, _ = self.klines(symbol, interval, cursor, int(end_ms),
                                  limit=limit, source=source)
            pages += 1
            if not page:
                break
            first_open = int(page[0][0])
            if last_open is not None:
                if first_open <= last_open:
                    raise ValueError(
                        f"page overlap/rewind: {first_open} <= {last_open}")
                if first_open > last_open + step:
                    skipped.append([last_open + step, first_open - step])
            for bar in page:
                if last_open is None or int(bar[0]) > last_open:
                    rows.append(bar)
                    last_open = int(bar[0])
            cursor = last_open + step
            if len(page) < int(limit):
                break
        return rows, {"pages": pages, "skipped_ranges": skipped}

    def earliest_bar(self, symbol: str, interval: str,
                     source: str = "klines") -> Optional[List[Any]]:
        """Listing-aware probe: the earliest bar Binance serves.

        startTime=0 with NO endTime returns the earliest available bars;
        an endTime near epoch would (correctly) return nothing. Returns
        None when nothing is available (unknown/unlisted symbol).
        """
        path = ("/fapi/v1/klines" if source == "klines"
                else "/fapi/v1/markPriceKlines")
        weight = ASSUMED_WEIGHTS["klines" if source == "klines"
                                 else "mark_klines"]
        payload, _ = self.get(path, {
            "symbol": symbol.upper(), "interval": interval,
            "startTime": 0, "limit": 1}, weight)
        if not isinstance(payload, list):
            raise ValueError(f"unexpected {source} shape: {type(payload)}")
        return payload[0] if payload else None

    def aggtrades(self, symbol: str, limit: int = 500,
                  from_id: Optional[int] = None) -> Tuple[List[Dict], Dict]:
        params: Dict[str, Any] = {"symbol": symbol.upper(),
                                  "limit": int(limit)}
        if from_id is not None:
            params["fromId"] = int(from_id)
        payload, hdrs = self.get("/fapi/v1/aggTrades", params,
                                 ASSUMED_WEIGHTS["aggtrades"])
        if not isinstance(payload, list):
            raise ValueError("unexpected aggTrades shape")
        return payload, hdrs

    def oi_hist(self, symbol: str, period: str, start_ms: int,
                end_ms: int, limit: int = 200) -> Tuple[List[Dict], Dict]:
        if period not in OI_PERIODS:
            raise ValueError(f"unsupported OI period {period}")
        payload, hdrs = self.get("/futures/data/openInterestHist", {
            "symbol": symbol.upper(), "period": period,
            "startTime": int(start_ms), "endTime": int(end_ms),
            "limit": int(limit)}, ASSUMED_WEIGHTS["oi_hist"])
        if not isinstance(payload, list):
            raise ValueError("unexpected openInterestHist shape")
        return payload, hdrs

    def paginate_oi(self, symbol: str, period: str, start_ms: int,
                    end_ms: int, limit: int = 500,
                    max_pages: int = 20) -> Tuple[List[Dict], int]:
        """Forward OI pagination by timestamp (dedupe on ts, no rewind)."""
        rows: List[Dict] = []
        cursor = int(start_ms)
        pages = 0
        last_ts: Optional[int] = None
        while cursor <= int(end_ms) and pages < max_pages:
            page, _ = self.oi_hist(symbol, period, cursor, int(end_ms),
                                   limit=limit)
            pages += 1
            if not page:
                break
            for r in page:
                ts = int(r["timestamp"])
                if last_ts is None or ts > last_ts:
                    rows.append(r)
                    last_ts = ts
            cursor = int(last_ts) + 1 if last_ts is not None else cursor
            if len(page) < int(limit):
                break
        return rows, pages

    def exchange_info(self, symbol: Optional[str] = None) -> Tuple[Dict, Dict]:
        params = {"symbol": symbol.upper()} if symbol else {}
        payload, hdrs = self.get("/fapi/v1/exchangeInfo", params,
                                 ASSUMED_WEIGHTS["exchange_info"])
        if not isinstance(payload, dict):
            raise ValueError("unexpected exchangeInfo shape")
        return payload, hdrs


def _backoff(attempt: int) -> float:
    return min(16.0, 2.0 ** max(attempt - 1, 0)) + random.uniform(0, 1.0)