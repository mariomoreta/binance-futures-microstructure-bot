"""P1-09 market-intelligence data composition (read-only, no engine writes).

Sourcing rule: everything here reads persisted P1-02..P1-08 state via
DashboardState/persistence. Nothing here touches the network, nothing feeds
the probe, nothing computes feature-engine values — it only composes already
persisted feature outputs into overview/movers/symbol views.

Capability vocabulary (single source of truth for P1-09 UI):
  LIVE            subscribed symbol with fresh persisted features
  WARMING         subscribed symbol with fresh snapshot but incomplete warmup
  DISCOVERY ONLY  unsubscribed symbol: REST 24h metrics only, no live features
  STALE           subscribed symbol whose market snapshot is older than
                  STALE_SNAPSHOT_SECONDS (honest staleness, never masked)
  DEGRADED        subscribed symbol with fresh data but the feed health model
                  reports degraded transport (reconnects / stale streams /
                  high retained rejection rate)
  UNKNOWN         no snapshot at all (empty DB / probe never ran)

Tier vocabulary (orthogonal to capability, never color-coded directionally):
  CORE       pinned benchmark/live symbols
  HOT        dynamic discovery candidate (proposed only, may be unsubscribed)
  DISCOVERY  eligible broad universe (REST scan only)
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

VALID_RANGES: Dict[str, int] = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 3600,
    "4h": 4 * 3600,
    "24h": 24 * 3600,
}

MAX_CHART_POINTS = 1000

# Symbol validation: must end with USDT, 6..34 chars after strip/upper, and
# the prefix must be alphanumeric (unicode letters allowed for symbols like
#龙虾USDT) plus _ - . No slashes, query chars, angle brackets, quotes.
_MAX_SYMBOL_LEN = 34


def normalize_symbol(raw: Optional[str]) -> Optional[str]:
    """Upper-case + validate a user-supplied symbol. None when invalid."""
    if raw is None:
        return None
    try:
        text = str(raw).strip().upper()
    except Exception:
        return None
    if not text or len(text) > _MAX_SYMBOL_LEN or len(text) < 6:
        return None
    if not text.endswith("USDT"):
        return None
    prefix = text[:-4]
    if not prefix:
        return None
    for ch in prefix:
        if ch.isalnum() or ch in ("_", "-", "."):
            continue
        return None
    # Reject anything that could break routing/HTML even after escaping.
    if any(c in text for c in ("/", "?", "&", "#", "<", ">", '"', "'", "`",
                               " ", "%")):
        return None
    return text


def is_valid_symbol(raw: Optional[str]) -> bool:
    return normalize_symbol(raw) is not None


def tier_for(symbol: str, discovery: Optional[Dict[str, Any]],
             live_symbols: Optional[set] = None) -> str:
    """CORE / HOT / DISCOVERY for a symbol (neutral chips, never red/green)."""
    disc = discovery or {}
    core = set(disc.get("core") or [])
    hot = set(disc.get("hot_dynamic") or []) | set(disc.get("hot_full") or [])
    hot = {s for s in hot if s not in core}
    if symbol in core:
        return "CORE"
    if symbol in hot:
        return "HOT"
    return "DISCOVERY"


def capability_for(symbol: str, *,
                   subscribed: bool,
                   warmup_complete: Optional[bool],
                   snapshot_stale: bool,
                   feed_degraded: bool,
                   has_snapshot: bool) -> str:
    """Single capability label for a symbol (see module docstring)."""
    if not has_snapshot:
        return "UNKNOWN"
    if not subscribed:
        return "DISCOVERY ONLY"
    if snapshot_stale:
        return "STALE"
    if feed_degraded:
        return "DEGRADED"
    if warmup_complete is False:
        return "WARMING"
    if warmup_complete is None:
        return "WARMING"
    return "LIVE"


def discovery_rows(discovery: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Deduplicated discovery rows by symbol from tops + hot set.

    The dashboard never hits Binance REST: the searchable universe is the
    persisted discovery snapshot (tops + core + hot). Full exchange listing
    is intentionally NOT persisted (P1-05 compact snapshot contract).
    """
    disc = discovery or {}
    tops = disc.get("tops") if isinstance(disc.get("tops"), dict) else {}
    out: Dict[str, Dict[str, Any]] = {}
    for key in ("gainers", "losers", "most_active"):
        rows = tops.get(key) if isinstance(tops.get(key), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol", "")).upper()
            if not sym or sym in out:
                continue
            out[sym] = dict(row)
    for sym in list(disc.get("core") or []) + list(disc.get("hot_dynamic") or []):
        s = str(sym).upper()
        if s and s not in out:
            out[s] = {"symbol": s, "change_24h_pct": None, "price": None,
                      "quote_volume_24h": None}
    return out


def compose_universe(state) -> Dict[str, Any]:
    """Shared universe composition for overview/movers/search/symbol."""
    features = state.return_features()
    discovery = state.discovery()
    live_symbols = {f.get("symbol") for f in features if isinstance(f, dict)}
    for reader in (state.flow_features, state.book_features,
                   state.oi_features, state.structure_features):
        try:
            rows = reader()
        except Exception:
            rows = []
        live_symbols |= {f.get("symbol") for f in rows
                         if isinstance(f, dict) and f.get("symbol")}
    disc_rows = discovery_rows(discovery)
    # Include live symbols even before any discovery scan.
    for f in features:
        if isinstance(f, dict) and f.get("symbol") not in disc_rows:
            disc_rows[str(f.get("symbol"))] = {
                "symbol": f.get("symbol"), "change_24h_pct": None,
                "price": f.get("current_price"),
                "quote_volume_24h": None}
    core = list((discovery or {}).get("core") or sorted(live_symbols))
    hot = list((discovery or {}).get("hot_dynamic") or [])
    return {
        "features": features,
        "discovery": discovery,
        "live_symbols": live_symbols,
        "disc_rows": disc_rows,
        "core": core,
        "hot": hot,
    }


def _num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def movers_table(state) -> List[Dict[str, Any]]:
    """One composed row per known symbol for the /movers workbench.

    Discovery-only metrics (24h % / quote volume) are never mixed with live
    metrics (returns / velocity / flow) without explicit per-row capability.
    """
    uni = compose_universe(state)
    features = uni["features"]
    disc_rows = uni["disc_rows"]
    discovery = uni["discovery"]
    flow_by: Dict[str, Dict[str, Any]] = {
        f.get("symbol"): f for f in state.flow_features()
        if isinstance(f, dict)}
    book_syms = {f.get("symbol") for f in state.book_features()
                 if isinstance(f, dict)}
    oi_syms = {f.get("symbol") for f in state.oi_features()
               if isinstance(f, dict)}
    struct_syms = {f.get("symbol") for f in state.structure_features()
                   if isinstance(f, dict)}
    snap = state.snapshot()
    health = state.health()
    stale = health.get("status") == "stale"
    degraded = health.get("status") == "degraded"
    has_snap = snap is not None

    feat_by = {f.get("symbol"): f for f in features if isinstance(f, dict)}
    any_live = (set(feat_by) | set(flow_by) | book_syms | oi_syms
                | struct_syms)
    symbols = sorted(set(list(disc_rows) + list(feat_by)
                         + list(flow_by) + list(book_syms) + list(oi_syms)
                         + list(struct_syms)))
    rows: List[Dict[str, Any]] = []
    for sym in symbols:
        feat = feat_by.get(sym) or {}
        disc = disc_rows.get(sym) or {}
        returns = feat.get("returns") if isinstance(feat.get("returns"), dict) else {}
        momentum = feat.get("momentum") if isinstance(feat.get("momentum"), dict) else {}
        vel = momentum.get("velocity") if isinstance(momentum.get("velocity"), dict) else {}
        acc = momentum.get("acceleration") if isinstance(momentum.get("acceleration"), dict) else {}
        flow = flow_by.get(sym) or {}
        horizons = flow.get("horizons") if isinstance(flow.get("horizons"), dict) else {}
        h1 = horizons.get("1m") if isinstance(horizons.get("1m"), dict) else {}
        baselines = flow.get("baselines") if isinstance(flow.get("baselines"), dict) else {}
        b1 = baselines.get("1m") if isinstance(baselines.get("1m"), dict) else {}
        subscribed = sym in any_live
        tier = tier_for(sym, discovery)
        cap = capability_for(
            sym, subscribed=subscribed,
            warmup_complete=feat.get("warmup_complete") if isinstance(feat, dict) else None,
            snapshot_stale=stale and subscribed,
            feed_degraded=degraded and subscribed,
            has_snapshot=has_snap)
        rows.append({
            "symbol": sym,
            "tier": tier,
            "capability": cap,
            "subscribed": subscribed,
            "price": feat.get("current_price", disc.get("price")),
            "change_24h_pct": disc.get("change_24h_pct"),
            "quote_volume_24h": disc.get("quote_volume_24h"),
            "ret_1m": returns.get("1m"),
            "ret_5m": returns.get("5m"),
            "velocity_1m": vel.get("1m"),
            "accel_1m": acc.get("1m"),
            "flow_delta": h1.get("signed_delta"),
            "flow_ratio": h1.get("delta_ratio"),
            "vol_z_1m": b1.get("z_score"),
            "sample_age_ms": feat.get("sample_age_ms"),
        })
    return rows


def search_symbols(query: str, universe_rows: List[Dict[str, Any]],
                   limit: int = 25) -> List[Dict[str, Any]]:
    """Case-insensitive partial match over the persisted universe.

    Deterministic order: exact match first, then prefix, then substring,
    each group alphabetical. Safe: query is never rendered unescaped
    (callers must html.escape) and never evaluated.
    """
    q = (query or "").strip().upper()
    if not q:
        return []
    q = q[:32]
    exact, prefix, sub = [], [], []
    for row in universe_rows:
        sym = str(row.get("symbol", "")).upper()
        if not sym or q not in sym:
            continue
        if sym == q:
            exact.append(row)
        elif sym.startswith(q):
            prefix.append(row)
        else:
            sub.append(row)
    exact.sort(key=lambda r: str(r.get("symbol")))
    prefix.sort(key=lambda r: str(r.get("symbol")))
    sub.sort(key=lambda r: str(r.get("symbol")))
    return (exact + prefix + sub)[:max(int(limit), 1)]


def price_history_points(store, symbol: str,
                         range_name: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Bounded mark-price points for charting from persisted price_samples.

    - source: P1-04 10s mark-price buckets (no new market-data source)
    - window: now - range <= bucket_ms <= now (no future samples, ever)
    - order: oldest first
    - bound: even downsampling to MAX_CHART_POINTS preserving endpoints
    """
    if range_name not in VALID_RANGES:
        raise ValueError(f"unknown range {range_name!r}")
    sym = normalize_symbol(symbol)
    if sym is None:
        raise ValueError(f"invalid symbol {symbol!r}")
    window_s = VALID_RANGES[range_name]
    now_ms = int(time.time() * 1000)
    lo = now_ms - window_s * 1000
    rows = store.load_price_samples(symbol=sym)
    pts = [{"timestamp": int(ts), "price": float(px)}
           for (_s, ts, px) in rows if lo <= int(ts) <= now_ms]
    pts.sort(key=lambda p: p["timestamp"])
    total = len(pts)
    truncated = False
    if total > MAX_CHART_POINTS:
        step = total / MAX_CHART_POINTS
        picked = [pts[int(i * step)] for i in range(MAX_CHART_POINTS - 1)]
        picked.append(pts[-1])
        pts = picked
        truncated = True
    meta = {
        "symbol": sym,
        "source": "markPrice",
        "range": range_name,
        "window_seconds": window_s,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "points_total": total,
        "points_returned": len(pts),
        "truncated": truncated,
        "point_limit": MAX_CHART_POINTS,
        "insufficient": total == 0,
    }
    return pts, meta


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def funding_snapshot(store, symbol: str,
                     scan_limit: int = 200) -> Dict[str, Any]:
    """Next-funding context from the latest persisted markPrice array.

    Reads the newest MULTI observation (!markPrice stream) and extracts,
    for one symbol, the venue fields carried inside the payload:
    T = next funding time, r = funding rate quoted with that array.
    Everything else is UNKNOWN: no settled-funding history is computed,
    no calendar exists, and the rate is quoted-as-of (an estimate for the
    coming settlement), never a settled record. Observation age is
    reported honestly (sampled/capped retention may be stale).
    """
    sym = normalize_symbol(symbol)
    unknown: Dict[str, Any] = {
        "symbol": sym,
        "next_funding_time_ms": None,
        "funding_rate": None,
        "observation_ms": None,
        "settled_history": "UNKNOWN",
        "calendar": "UNKNOWN",
    }
    if sym is None:
        return unknown
    try:
        rows = store.latest_observations(limit=max(int(scan_limit), 1))
    except Exception:
        return unknown
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("symbol") != "MULTI":
            continue
        stream = str(row.get("stream_type") or "")
        if "markPrice" not in stream:
            continue
        payload = row.get("payload")
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("s", "")).upper() != sym:
                continue
            funding_time = _finite_number(item.get("T"))
            rate = _finite_number(item.get("r"))
            obs_ms = _finite_number(row.get("timestamp"))
            if obs_ms is not None and obs_ms < 1_000_000_000_000:
                obs_ms = obs_ms * 1000.0  # stored seconds -> ms
            return {
                "symbol": sym,
                "next_funding_time_ms": int(funding_time)
                if funding_time else None,
                "funding_rate": rate,
                "observation_ms": int(obs_ms) if obs_ms else None,
                "settled_history": "UNKNOWN",
                "calendar": "UNKNOWN",
            }
    return unknown
