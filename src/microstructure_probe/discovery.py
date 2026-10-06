"""P1-05 public market discovery layer (Binance USD-M Futures, REST only).

Verified live 2026-10-06 against the public endpoints (official docs site was
not fetchable from this environment; endpoint paths match the documented
USD-M Futures market-data REST API, same host family as the probe's existing
clock-sync endpoint):
- GET https://fapi.binance.com/fapi/v1/exchangeInfo -> 200, 924 symbols with
  status / contractType / quoteAsset fields.
- GET https://fapi.binance.com/fapi/v1/ticker/24hr -> 200, 789 rows with
  lastPrice / priceChangePercent / quoteVolume / count fields.

Public only. No API keys and no authenticated, private, account, or order
endpoints of any kind.
This layer NEVER subscribes websocket streams: it builds a broad candidate
universe cheaply so a bounded HOT set can be selected for deeper tracking.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
TICKER_24H_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
USER_AGENT = "microstructure-probe/0.4"

CORE_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

TIER_CORE = "CORE"
TIER_HOT = "HOT"
TIER_DISCOVERY = "DISCOVERY"


def fetch_json(url: str, timeout: float = 15.0) -> Any:
    """Public GET returning parsed JSON. No credentials of any kind."""
    request = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _to_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


@dataclass
class Candidate:
    """One discovery candidate with explicit quality metadata."""
    symbol: str
    status: Optional[str] = None
    contract_type: Optional[str] = None
    quote_asset: Optional[str] = None
    price: Optional[float] = None
    change_24h_pct: Optional[float] = None
    quote_volume_24h: Optional[float] = None
    trade_count_24h: Optional[int] = None
    eligible: bool = False
    exclusion_reasons: List[str] = field(default_factory=list)
    discovered_at_ms: int = 0
    ticker_close_ms: Optional[int] = None


def build_candidates(exchange_info: Dict[str, Any],
                     tickers_24h: List[Dict[str, Any]],
                     min_quote_volume_usdt: float,
                     discovered_at_ms: Optional[int] = None) -> List[Candidate]:
    """Join exchangeInfo metadata with 24h ticker stats.

    Eligibility (all required): contractType == PERPETUAL, status == TRADING,
    quoteAsset == USDT, 24h quote volume >= floor. Anything else is kept as
    an ineligible candidate with explicit reasons — never silently dropped,
    never fabricated.
    """
    now_ms = discovered_at_ms if discovered_at_ms is not None else int(time.time() * 1000)
    meta = {}
    for entry in exchange_info.get("symbols", []):
        if isinstance(entry, dict) and entry.get("symbol"):
            meta[str(entry["symbol"]).upper()] = entry
    tickers = {}
    for row in tickers_24h or []:
        if isinstance(row, dict) and row.get("symbol"):
            tickers[str(row["symbol"]).upper()] = row
    out: List[Candidate] = []
    for symbol in sorted(set(meta) | set(tickers)):
        info = meta.get(symbol, {})
        tick = tickers.get(symbol, {})
        reasons: List[str] = []
        contract_type = info.get("contractType")
        status = info.get("status")
        quote_asset = info.get("quoteAsset")
        if contract_type != "PERPETUAL":
            reasons.append(f"contract_type={contract_type}")
        if status != "TRADING":
            reasons.append(f"status={status}")
        if quote_asset != "USDT":
            reasons.append(f"quote_asset={quote_asset}")
        volume = _to_float(tick.get("quoteVolume"))
        if volume is None:
            reasons.append("quote_volume_unknown")
        elif volume < min_quote_volume_usdt:
            reasons.append(f"quote_volume_{volume:.0f}_below_floor")
        try:
            count = tick.get("count")
            trade_count = int(count) if count is not None else None
        except (TypeError, ValueError):
            trade_count = None
        try:
            close_ms = tick.get("closeTime")
            close_ms = int(close_ms) if close_ms is not None else None
        except (TypeError, ValueError):
            close_ms = None
        out.append(Candidate(
            symbol=symbol,
            status=status,
            contract_type=contract_type,
            quote_asset=quote_asset,
            price=_to_float(tick.get("lastPrice")),
            change_24h_pct=_to_float(tick.get("priceChangePercent")),
            quote_volume_24h=volume,
            trade_count_24h=trade_count,
            eligible=not reasons,
            exclusion_reasons=reasons,
            discovered_at_ms=now_ms,
            ticker_close_ms=close_ms,
        ))
    return out


def _score_key(candidate: Candidate):
    """Deterministic movement score: |24h%| desc, volume desc, symbol asc.

    Candidates without a 24h change cannot express movement and sort last.
    """
    change = candidate.change_24h_pct
    volume = candidate.quote_volume_24h
    return (change is None,
            -(abs(change) if change is not None else 0.0),
            -(volume if volume is not None else 0.0),
            candidate.symbol)


def select_hot(candidates: List[Candidate],
               core: tuple = CORE_SYMBOLS,
               dynamic_slots: int = 6,
               prior_dynamic: tuple = (),
               state: Optional[Dict[str, Dict[str, int]]] = None,
               min_votes: int = 2) -> tuple:
    """Deterministic bounded HOT selection with hysteresis.

    - Core symbols are pinned benchmarks (always in the HOT set, never voted).
    - Dynamic slots fill from eligible non-core candidates by movement score.
    - A contender enters only after `min_votes` consecutive scans inside the
      contender window; an incumbent leaves after `min_votes` consecutive
      scans outside it, or immediately when it becomes ineligible.
    - Pure function of (candidates, prior_dynamic, state); ties broken
      deterministically. Returns (dynamic_list, events, state).
    """
    if state is None:
        state = {"appear": {}, "absent": {}}
    appear = state.setdefault("appear", {})
    absent = state.setdefault("absent", {})
    present = {c.symbol for c in candidates}
    eligible = {c.symbol: c for c in candidates if c.eligible}
    ranked = sorted((c for c in eligible.values() if c.symbol not in core),
                    key=_score_key)
    contenders = [c.symbol for c in ranked
                  if c.change_24h_pct is not None][:max(dynamic_slots, 0)]
    contender_set = set(contenders)
    for symbol in contender_set:
        appear[symbol] = appear.get(symbol, 0) + 1
        absent.pop(symbol, None)
    for symbol in list(appear):
        if symbol not in contender_set:
            appear[symbol] = 0
    events: List[Dict[str, Any]] = []
    prior_set = set(prior_dynamic)
    # Proven breach (present in scan but ineligible: delist/floor) demotes
    # immediately. Merely vanishing from a scan only counts an absence.
    for symbol in sorted(prior_set - present - set(eligible)):
        absent[symbol] = absent.get(symbol, 0) + 1
        if absent[symbol] >= min_votes:
            events.append({"kind": "demoted", "symbol": symbol,
                           "reason": f"vanished_{absent[symbol]}_scans"})
    for symbol in sorted((prior_set & present) - set(eligible)):
        events.append({"kind": "demoted", "symbol": symbol,
                       "reason": "ineligible"})
    for symbol in sorted(prior_set & set(eligible) - contender_set):
        absent[symbol] = absent.get(symbol, 0) + 1
        if absent[symbol] >= min_votes:
            events.append({"kind": "demoted", "symbol": symbol,
                           "reason": f"absent_{absent[symbol]}_scans"})
    demoted = {e["symbol"] for e in events if e["kind"] == "demoted"}
    survivors = [s for s in prior_dynamic
                 if s not in demoted
                 and (s in eligible or absent.get(s, 0) < min_votes)]
    promoted = [s for s in contenders
                if s not in prior_set and appear.get(s, 0) >= min_votes]
    for symbol in sorted(promoted):
        events.append({"kind": "promoted", "symbol": symbol,
                       "reason": f"top_mover_{appear.get(symbol, 0)}_votes"})
    # Deterministic order: rank order, survivors first then promoted.
    rank_index = {s: i for i, s in enumerate(contenders)}
    dynamic = sorted(set(survivors) | set(promoted),
                     key=lambda s: (rank_index.get(s, 10 ** 9), s))
    dynamic = dynamic[:max(dynamic_slots, 0)]
    # Late demotions for survivors cut by the cap (stable order keeps top).
    for symbol in sorted(set(survivors) - set(dynamic)):
        events.append({"kind": "demoted", "symbol": symbol,
                       "reason": "hot_set_cap"})
    return dynamic, events, state


def top_movers(candidates: List[Candidate], top_n: int = 10) -> Dict[str, List[Dict[str, Any]]]:
    """Lightweight discovery tables (movement, not market cap)."""
    scored = [c for c in candidates
              if c.eligible and c.change_24h_pct is not None]
    volumed = [c for c in candidates
               if c.eligible and c.quote_volume_24h is not None]

    def row(c: Candidate) -> Dict[str, Any]:
        return {"symbol": c.symbol, "change_24h_pct": c.change_24h_pct,
                "price": c.price, "quote_volume_24h": c.quote_volume_24h,
                "trade_count_24h": c.trade_count_24h}

    gainers = sorted(scored, key=lambda c: (-c.change_24h_pct, c.symbol))[:top_n]
    losers = sorted(scored, key=lambda c: (c.change_24h_pct, c.symbol))[:top_n]
    active = sorted(volumed, key=lambda c: (-c.quote_volume_24h, c.symbol))[:top_n]
    return {"gainers": [row(c) for c in gainers],
            "losers": [row(c) for c in losers],
            "most_active": [row(c) for c in active]}


class DiscoveryClient:
    """Thin public-REST client with injectable fetch (tests never hit net)."""

    def __init__(self, fetch: Callable[[str, float], Any] = fetch_json,
                 timeout: float = 15.0) -> None:
        self._fetch = fetch
        self._timeout = timeout

    def scan(self, min_quote_volume_usdt: float) -> tuple:
        """One discovery scan: (candidates, raw_counts). Raises on transport
        failure so the caller can log-and-continue without breaking the probe.
        """
        exchange_info = self._fetch(EXCHANGE_INFO_URL, self._timeout)
        tickers = self._fetch(TICKER_24H_URL, self._timeout)
        if not isinstance(exchange_info, dict) or not isinstance(tickers, list):
            raise ValueError("unexpected discovery payload shapes")
        now_ms = int(time.time() * 1000)
        candidates = build_candidates(exchange_info, tickers,
                                      min_quote_volume_usdt, now_ms)
        counts = {"symbols_seen": len({c.symbol for c in candidates}),
                  "eligible": sum(1 for c in candidates if c.eligible)}
        return candidates, counts
