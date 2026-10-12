"""P1-09 view renderers: overview / movers / symbol / search / system.

P1-13A adds a minimal research-only opportunities read surface
(render_opportunities). Read-only composition over DashboardState.
No trading language anywhere: aggressive BUY/SELL appear only as
trade-side flow labels.
"""

from __future__ import annotations

import html
import json
import math
import time
from typing import Any, Dict, List, Optional

from . import dashboard_components as C
from .dashboard_data import (
    VALID_RANGES,
    capability_for,
    compose_universe,
    discovery_rows,
    funding_snapshot,
    movers_table,
    normalize_symbol,
    price_history_points,
    search_symbols,
    tier_for,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _finite(value: Any) -> Optional[float]:
    """Finite float or None (P1-11A.1: NaN/inf/None/str never enter leaders)."""
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _fmt_ts(ms: Any) -> str:
    """UTC timestamp or em-dash (never invents a time)."""
    try:
        value = float(ms)
    except (TypeError, ValueError):
        return "—"
    if value <= 0 or value != value:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(value / 1000))
    except (OverflowError, OSError, ValueError):
        return "—"


def _banner(state) -> str:
    snap = state.snapshot()
    safety = _safe_dict((snap or {}).get("safety"))
    return C.banner_html_fn(safety, state.health()["status"])


def _market_summary_cards(state) -> str:
    uni = compose_universe(state)
    discovery = uni["discovery"]
    health = state.health()
    snap = state.snapshot()
    snap_ts = (snap or {}).get("snapshotTimestamp")
    age_s = f"{time.time() - snap_ts:.0f}s" if snap_ts else "never"
    cards = [
        ("Discovery universe", f"{(discovery or {}).get('eligible_count', '?')} eligible"),
        ("CORE", str(len(uni["core"]))),
        ("HOT proposed", str(len(uni["hot"]))),
        ("LIVE subscribed", str(len(uni["live_symbols"]))),
        ("Feed state", health["status"].upper()),
        ("Latest discovery age", age_s),
    ]
    out = "<div class='grid g4'>"
    for label, value in cards:
        out += (f"<div class='card'><h3>{html.escape(label)}</h3>"
                f"<div class='big'>{html.escape(str(value))}</div></div>")
    return out + "</div>"


def _top_activity(state) -> str:
    uni = compose_universe(state)
    discovery = uni["discovery"] or {}
    tops = discovery.get("tops") or {}
    rows = movers_table(state)
    live = [r for r in rows if r.get("subscribed")]
    gainers = (tops.get("gainers") or [])[:5]
    losers = (tops.get("losers") or [])[:5]
    hot_syms = uni["hot"][:5]

    def _mini(title: str, items: List[str]) -> str:
        body = "".join(f"<div>{it}</div>" for it in items) or \
            "<div class='note'>none</div>"
        return f"<div class='card'><h3>{html.escape(title)}</h3>{body}</div>"

    g = [f"{C.symbol_link(str(r.get('symbol')))} "
         f"{C.signed_pct(r.get('change_24h_pct'))}" for r in gainers
         if isinstance(r, dict)]
    l = [f"{C.symbol_link(str(r.get('symbol')))} "
         f"{C.signed_pct(r.get('change_24h_pct'))}" for r in losers
         if isinstance(r, dict)]
    h = [C.symbol_link(s) for s in hot_syms]
    vel_sorted = sorted(
        [r for r in live if r.get("velocity_1m") is not None],
        key=lambda r: float(r["velocity_1m"]), reverse=True)[:5]
    v = [f"{C.symbol_link(str(r['symbol']))} {C.sci(r.get('velocity_1m'))}"
         for r in vel_sorted]
    return ("<div class='grid g4'>"
            + _mini("Strongest gainers 24h (discovery)", g)
            + _mini("Strongest losers 24h (discovery)", l)
            + _mini("HOT proposals", h)
            + _mini("Live momentum leaders (velocity 1m)", v)
            + "</div>")


def _live_core_compact(state) -> str:
    features = state.return_features()
    flow_by = {f.get("symbol"): f for f in state.flow_features()
               if isinstance(f, dict)}
    book_by = {f.get("symbol"): f for f in state.book_features()
               if isinstance(f, dict)}
    oi_by = {f.get("symbol"): f for f in state.oi_features()
             if isinstance(f, dict)}
    struct_by = {f.get("symbol"): f for f in state.structure_features()
                 if isinstance(f, dict)}
    discovery = state.discovery()
    snap = state.snapshot()
    health = state.health()
    stale = health.get("status") == "stale"
    degraded = health.get("status") == "degraded"
    has_snap = snap is not None
    if not features:
        from .dashboard_data import compose_universe as _compose
        _live = sorted(_compose(state).get("live_symbols") or [])
        links = ("<p class='note'>Live feature symbols: "
                 + ", ".join(C.symbol_link(s) for s in _live) + "</p>"
                 if _live else "")
        return ("<h2>Symbol Returns</h2>"
                "<p class='note'>No return features persisted yet — "
                "insufficient history (engine warming up or probe not running).</p>"
                + links)
    body = ("<h2>Symbol Returns</h2>"
            "<p class='note'>Mark-price log returns. Unavailable horizons show "
            "insufficient history, never 0%.</p>"
            "<div class='scrollx'><table><tr><th>symbol</th><th>tier</th>"
            "<th>price</th><th>1m</th><th>3m</th><th>5m</th><th>15m</th>"
            "<th>velocity 1m</th><th>flow Δ</th><th>OI Δ 1m</th>"
            "<th>spread bps</th><th>VWAP displ</th><th>freshness</th>"
            "<th>data state</th></tr>")
    for feat in sorted(features, key=lambda f: str(f.get("symbol", ""))):
        if not isinstance(feat, dict):
            continue
        sym = str(feat.get("symbol", "?"))
        returns = feat.get("returns") if isinstance(feat.get("returns"), dict) else {}
        momentum = feat.get("momentum") if isinstance(feat.get("momentum"), dict) else {}
        vel = momentum.get("velocity") if isinstance(momentum.get("velocity"), dict) else {}
        flow = flow_by.get(sym, {})
        horizons = flow.get("horizons") if isinstance(flow.get("horizons"), dict) else {}
        h1 = horizons.get("1m") if isinstance(horizons.get("1m"), dict) else {}
        oi = oi_by.get(sym, {})
        oi_h = oi.get("horizons") if isinstance(oi.get("horizons"), dict) else {}
        oi1 = oi_h.get("1m") if isinstance(oi_h.get("1m"), dict) else {}
        book = book_by.get(sym, {})
        book_in = book.get("book") if isinstance(book.get("book"), dict) else {}
        struct = struct_by.get(sym, {})
        vwap = struct.get("vwap") if isinstance(struct.get("vwap"), dict) else {}
        v1 = vwap.get("1m") if isinstance(vwap.get("1m"), dict) else {}
        try:
            price = f"{float(feat.get('current_price')):.4f}" \
                if feat.get("current_price") is not None else "—"
        except (TypeError, ValueError):
            price = "—"
        tier = tier_for(sym, discovery)
        cap = capability_for(
            sym, subscribed=True,
            warmup_complete=feat.get("warmup_complete"),
            snapshot_stale=stale, feed_degraded=degraded,
            has_snapshot=has_snap)
        available = feat.get("available_tfs") if isinstance(feat.get("available_tfs"), list) else []
        warm = " READY" if feat.get("warmup_complete") else " WARMING"
        body += (
            f"<tr class='rowlink' onclick=\"location='/symbol/{html.escape(sym)}'\">"
            f"<td>{C.symbol_link(sym)}</td>"
            f"<td>{C.tier_chip(tier)}</td><td>{price}</td>"
            + "".join(f"<td>{C.signed_frac(returns.get(tf), 3)}</td>"
                      for tf in ("1m", "3m", "5m", "15m"))
            + f"<td>{C.sci(vel.get('1m'))}</td>"
            f"<td>{C.signed_num(h1.get('signed_delta'), 2)}</td>"
            f"<td>{C.signed_num(oi1.get('delta'), 3)}</td>"
            f"<td>{html.escape(str(book_in.get('spread_bps', '—')))}</td>"
            f"<td>{C.signed_num(v1.get('displacement_bps'), 1)}</td>"
            f"<td>{C.age(feat.get('sample_age_ms'))} {len(available)}/7{warm}</td>"
            f"<td>{C.capability_chip(cap)}</td></tr>")
    return body + "</table></div>"


def render_overview(state) -> str:
    snap = state.snapshot()
    health = state.health()
    if snap is None:
        return C.page("Overview — Binance Futures", "OVERVIEW",
                      C.banner_html_fn({}, health["status"]),
                      "<p class='warn'>No telemetry snapshot persisted yet. "
                      "Run the probe to generate persistence state.</p>"
                      f"<p class='note'>Reasons: "
                      f"{html.escape('; '.join(health['reasons']))}</p>",
                      engine_html=C.engine_control_html(state))
    safety = _safe_dict(snap.get("safety"))
    dq = _safe_dict(snap.get("dataQuality"))
    rj = state.rejection_stats()
    storage = state.storage()
    rows = storage.get("rows") if isinstance(storage.get("rows"), dict) else {}
    body = "<h2>Market summary</h2>" + _market_summary_cards(state)
    body += "<h2>Top market activity</h2>" + _top_activity(state)
    body += "<h2>Live CORE / tracked symbols</h2>" + _live_core_compact(state)
    # Keep legacy intel markers (compact, links to /movers + /symbol pages).
    body += "<h2>Market intelligence</h2>"
    body += "<h2>Universe tiers</h2>"
    uni = compose_universe(state)
    discovery = uni["discovery"] or {}
    body += ("<table class='kv'><tr><th>CORE benchmarks</th><td>"
             + html.escape(", ".join(uni["core"]) or "—") + "</td></tr>"
             "<tr><th>HOT dynamic</th><td>"
             + html.escape(", ".join(uni["hot"]) or "none selected") + "</td></tr>"
             "<tr><th>HOT subscribed (deep)</th><td>"
             + html.escape(", ".join(
                 (discovery.get("hot_subscribed") or [])) or "none")
             + "</td></tr>"
             "<tr><th>DISCOVERY</th><td>"
             + html.escape(f"{discovery.get('eligible_count', '?')} eligible of "
                           f"{discovery.get('seen_count', '?')} seen") + "</td></tr></table>")
    states = discovery.get("universe_states") if isinstance(
        discovery.get("universe_states"), dict) else {}
    if states:
        body += ("<table class='kv'><tr><th>HOT symbol</th><th>lifecycle</th>"
                 "<th>reason</th></tr>" + "".join(
                     f"<tr><td>{html.escape(str(sym))}</td>"
                     f"<td>{html.escape(str((rec or {}).get('state', '?')))}</td>"
                     f"<td>{html.escape(str((rec or {}).get('reason', '')))}</td></tr>"
                     for sym, rec in sorted(states.items())) + "</table>")
    recent = []
    try:
        recent_fn = getattr(state, "universe_events", None)
        recent = recent_fn(limit=10) if callable(recent_fn) else []
    except Exception:
        recent = []
    hot_evts = [e for e in recent if isinstance(e, dict)
                and str(e.get("kind", "")).startswith("hot_")]
    if hot_evts:
        body += ("<table class='kv'><tr><th>promotion event</th><th>detail</th></tr>"
                 + "".join(
                     f"<tr><td>{html.escape(str(e.get('kind', '')))} "
                     f"{html.escape(str(e.get('symbol', '')))}</td>"
                     f"<td>{html.escape(str(e.get('detail', '')))}</td></tr>"
                     for e in hot_evts[:10]) + "</table>")
    body += "<h2>Live momentum (subscribed symbols only)</h2>"
    feats = state.return_features()
    if not feats:
        body += "<p class='note'>No live features yet — insufficient history.</p>"
    else:
        body += ("<p class='note'>Full per-symbol momentum lives on "
                 "<a href='/movers'>/movers</a> and "
                 "<a href='/symbol/BTCUSDT'>/symbol/:symbol</a> pages.</p>")
    body += "<h2>Discovery movers (24h REST metrics — discovery only, NOT live)</h2>"
    tops = discovery.get("tops") or {}
    if not tops:
        body += "<p class='note'>No discovery scan yet.</p>"
    else:
        for title, key in (("Top gainers 24h", "gainers"),
                           ("Top losers 24h", "losers"),
                           ("Most active 24h (quote volume)", "most_active")):
            rows_t = tops.get(key) or []
            body += f"<h2>{html.escape(title)}</h2>"
            if not rows_t:
                body += "<p class='note'>none</p>"
                continue
            body += ("<table><tr><th>symbol</th><th>24h %</th>"
                     "<th>quote vol 24h</th><th>live feed</th></tr>")
            for row in rows_t[:8]:
                sym = str(row.get("symbol", "?"))
                chg = row.get("change_24h_pct")
                try:
                    chg_cell = f"{float(chg):+.2f}%" if chg is not None else "—"
                except (TypeError, ValueError):
                    chg_cell = "—"
                live_cell = ("LIVE (subscribed)" if sym in uni["live_symbols"]
                             else "DISCOVERY ONLY — NO LIVE FLOW/BOOK "
                                  "(discovery only, NOT live)")
                body += (f"<tr><td>{C.symbol_link(sym)}</td><td>{chg_cell}</td>"
                         f"<td>{html.escape(str(row.get('quote_volume_24h', '—')))}</td>"
                         f"<td>{live_cell}</td></tr>")
            body += "</table>"
    body += "<div class='section'><h2>Dashboard server health</h2></div>"
    body += ("<table class='kv'><tr><th>server</th><td>UP "
             f"(v{html.escape(_dashboard_version())}, "
             f"{state.server_uptime_seconds():.0f}s uptime)</td></tr>"
             f"<tr><th>snapshot age</th><td>{html.escape(_snap_age(snap))}</td></tr>"
             "</table>")
    body += "<h2>Market feed health</h2>"
    messages = _safe_dict(dq.get("messagesByStream"))
    total = sum(int(v) for v in messages.values())
    body += ("<table class='kv'>"
             f"<tr><th>streams active/expected</th><td>{dq.get('activeStreams', '?')}/"
             f"{dq.get('expectedStreams', '?')}</td></tr>"
             f"<tr><th>total messages (this run)</th><td>{total}</td></tr>"
             f"<tr><th>silent streams (event-driven silence is normal)</th><td>{html.escape(', '.join(dq.get('silentStreams') or []) or 'none')}</td></tr>"
             f"<tr><th>timestamp rejected (this run)</th><td>{dq.get('timestampRejected', '?')}</td></tr>"
             f"<tr><th>retained rejected rows / rate (persistence)</th><td>"
             f"{rj.get('total_rejected', '?')} / "
             f"{float(rj.get('rejection_rate', 0.0)):.1%}</td></tr>"
             f"<tr><th>feed status</th><td>{html.escape(health['status'].upper())}</td></tr>"
             "</table>")
    body += "<h2>Persistence health</h2>"
    body += ("<table class='kv'><tr><th>stored rows</th><td>"
             + html.escape(json.dumps(rows)) + "</td></tr></table>")
    events = _safe_dict(snap.get("eventsByType"))
    body += "<h2>Detector telemetry (NOT trade signals)</h2>"
    if events:
        body += "<table class='kv'>" + "".join(
            f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
            for k, v in sorted(events.items())) + "</table>"
    else:
        body += "<p class='note'>No detector threshold crossings in this snapshot window.</p>"
    return C.page("Overview — Binance Futures", "OVERVIEW",
                  C.banner_html_fn(safety, health["status"]), body,
                  engine_html=C.engine_control_html(state))


def _dashboard_version() -> str:
    from . import dashboard as _d
    return _d.DASHBOARD_VERSION


def _snap_age(snap: Dict[str, Any]) -> str:
    ts = snap.get("snapshotTimestamp")
    try:
        return f"{time.time() - float(ts):.0f}s" if ts else "unknown"
    except (TypeError, ValueError):
        return "unknown"


def render_movers(state) -> str:
    rows = movers_table(state)
    uni = compose_universe(state)
    discovery = uni["discovery"] or {}
    scan_age = "never"
    if discovery.get("generated_at_ms"):
        try:
            scan_age = (f"{(time.time() * 1000 - float(discovery['generated_at_ms'])) / 1000:.0f}s ago")
        except (TypeError, ValueError):
            scan_age = "?"
    body = (f"<p class='note'>Discovery scan: {html.escape(scan_age)} · "
            f"{discovery.get('eligible_count', '?')} eligible · "
            "discovery-only metrics (24h %) and live metrics (velocity/flow) "
            "are labeled per row — never mixed.</p>")
    gainers = sorted([r for r in rows if r.get("change_24h_pct") is not None],
                     key=lambda r: (-float(r["change_24h_pct"]), r["symbol"]))[:15]
    losers = sorted([r for r in rows if r.get("change_24h_pct") is not None],
                    key=lambda r: (float(r["change_24h_pct"]), r["symbol"]))[:15]
    active = sorted([r for r in rows if r.get("quote_volume_24h") is not None],
                    key=lambda r: (-float(r["quote_volume_24h"]), r["symbol"]))[:15]
    hot_rows = [r for r in rows if r.get("tier") == "HOT"]
    # P1-11A.1: velocity leader tables are sign-filtered. Positive takes
    # ONLY finite velocity_1m > 0 (largest first); negative takes ONLY finite
    # velocity_1m < 0 (most negative first). Exact zero and UNKNOWN/None
    # (incl. NaN/inf) belong in neither table — never backfill a leader
    # table with wrong-signed rows merely because they rank highest.
    vel_live = [(r, _finite(r.get("velocity_1m"))) for r in rows
                if r.get("subscribed")]
    vel_pos = sorted([r for r, v in vel_live if v is not None and v > 0],
                     key=lambda r: (-float(r["velocity_1m"]), r["symbol"]))[:10]
    vel_neg = sorted([r for r, v in vel_live if v is not None and v < 0],
                     key=lambda r: (float(r["velocity_1m"]), r["symbol"]))[:10]
    live_acc = [r for r in rows
                if r.get("subscribed") and r.get("accel_1m") is not None]
    acc = sorted(live_acc, key=lambda r: (-abs(float(r["accel_1m"])), r["symbol"]))[:10]
    volx = sorted([r for r in rows
                   if r.get("subscribed") and r.get("vol_z_1m") is not None],
                  key=lambda r: (-float(r["vol_z_1m"]), r["symbol"]))[:10]
    flowl = sorted([r for r in rows
                    if r.get("subscribed") and r.get("flow_delta") is not None],
                   key=lambda r: (-abs(float(r["flow_delta"])), r["symbol"]))[:10]

    body += "<h2>Market table (click a row for token detail)</h2>"
    body += ("<div class='scrollx'><table><tr><th>symbol</th><th>tier</th>"
             "<th>price</th><th>24h %</th><th>24h quote vol</th>"
             "<th>1m %</th><th>5m %</th><th>velocity</th><th>accel</th>"
             "<th>flow</th><th>OI Δ</th><th>vol z</th><th>data state</th></tr>")
    for r in sorted(rows, key=lambda r: r["symbol"]):
        try:
            price = f"{float(r['price']):.4f}" if r.get("price") is not None else "—"
        except (TypeError, ValueError):
            price = "—"
        body += (
            f"<tr class='rowlink' onclick=\"location='/symbol/{html.escape(r['symbol'])}'\">"
            f"<td>{C.symbol_link(r['symbol'])}</td>"
            f"<td>{C.tier_chip(r['tier'])}</td><td>{price}</td>"
            f"<td>{C.signed_pct(r.get('change_24h_pct'))}</td>"
            f"<td>{html.escape(str(r.get('quote_volume_24h', '—')))}</td>"
            f"<td>{C.signed_frac(r.get('ret_1m'), 3)}</td>"
            f"<td>{C.signed_frac(r.get('ret_5m'), 3)}</td>"
            f"<td>{C.sci(r.get('velocity_1m'))}</td>"
            f"<td>{C.sci(r.get('accel_1m'), '/s²')}</td>"
            f"<td>{C.signed_num(r.get('flow_delta'), 2)}</td>"
            f"<td>—</td>"
            f"<td>{html.escape(str(r.get('vol_z_1m', '—')))}</td>"
            f"<td>{C.capability_chip(r.get('capability', 'UNKNOWN'))}</td></tr>")
    body += "</table></div>"

    def _cat(title: str, cat_rows: List[Dict[str, Any]], note: str,
             vkey: str,
             empty: str = "none (insufficient data).") -> str:
        # P1-11A: each category renders its OWN display-value key. A shared
        # key across categories let a symbol present in several tables show
        # the last-assigned value everywhere (velocity/accel/vol-z/flow
        # scales mixed). Per-category keys make that class impossible.
        # P1-11A.1: empty leader tables render an honest per-category note.
        out = f"<h2>{html.escape(title)}</h2><p class='note'>{html.escape(note)}</p>"
        if not cat_rows:
            return out + f"<p class='note'>{html.escape(empty)}</p>"
        out += "<table><tr><th>symbol</th><th>tier</th><th>value</th><th>data state</th></tr>"
        for r in cat_rows:
            out += (f"<tr><td>{C.symbol_link(r['symbol'])}</td>"
                    f"<td>{C.tier_chip(r['tier'])}</td>"
                    f"<td>{html.escape(str(r.get(vkey, '—')))}</td>"
                    f"<td>{C.capability_chip(r.get('capability', 'UNKNOWN'))}</td></tr>")
        return out + "</table>"

    for r in gainers:
        r["_v_pct"] = f"{float(r['change_24h_pct']):+.2f}%"
    for r in losers:
        r["_v_pct"] = f"{float(r['change_24h_pct']):+.2f}%"
    for r in active:
        r["_v_qvol"] = str(r["quote_volume_24h"])
    for r in hot_rows:
        r["_v_hot"] = "proposed"
    for r in vel_pos + vel_neg:
        r["_v_vel"] = f"{float(r['velocity_1m']):.3g}/s"
    for r in acc:
        r["_v_acc"] = f"{float(r['accel_1m']):.3g}/s²"
    for r in volx:
        r["_v_volz"] = f"{float(r['vol_z_1m']):+.2f} z"
    for r in flowl:
        r["_v_flow"] = f"{float(r['flow_delta']):+.2f}"
    body += _cat("Top gainers 24h (discovery)", gainers,
                 "REST 24h change — discovery metric.", "_v_pct")
    body += _cat("Top losers 24h (discovery)", losers,
                 "REST 24h change — discovery metric.", "_v_pct")
    body += _cat("Highest 24h activity / quote volume (discovery)", active,
                 "REST 24h quote volume — discovery metric.", "_v_qvol")
    body += _cat("HOT proposals", hot_rows,
                 "Dynamic discovery candidates (proposed only; may be DISCOVERY ONLY).",
                 "_v_hot")
    body += _cat("Fastest positive velocity (live)", vel_pos,
                 "Live 1m return-velocity — subscribed symbols only.", "_v_vel",
                 empty="No positive live velocity currently.")
    body += _cat("Fastest negative velocity (live)", vel_neg,
                 "Live 1m return-velocity — subscribed symbols only.", "_v_vel",
                 empty="No negative live velocity currently.")
    body += _cat("Acceleration leaders (live)", acc,
                 "Live 1m acceleration magnitude — subscribed symbols only.", "_v_acc")
    body += _cat("Volume expansion (live z-score)", volx,
                 "Live 1m volume z-score — subscribed symbols only.", "_v_volz")
    body += _cat("Aggressive-flow leaders (live)", flowl,
                 "Live signed flow delta magnitude — subscribed symbols only.", "_v_flow")
    return C.page("Movers — Binance Futures", "MOVERS", _banner(state), body,
                  engine_html=C.engine_control_html(state))


def render_search(state, query: str) -> str:
    uni = compose_universe(state)
    rows = movers_table(state)
    results = search_symbols(query, rows)
    discovery = uni["discovery"]
    body = (f"<p class='note'>Search across the persisted discovery universe "
            f"(tops + CORE + HOT + live symbols) — case-insensitive partial match, "
            f"deterministic order. Query is escaped, never executed.</p>")
    if not (query or "").strip():
        body += "<p class='note'>Type a symbol fragment above (e.g. ORC).</p>"
    elif not results:
        body += (f"<p class='warn'>No symbols match "
                 f"'{html.escape(query)}' in the persisted universe.</p>")
    else:
        body += ("<table><tr><th>symbol</th><th>tier</th><th>24h %</th>"
                 "<th>volume 24h</th><th>data state</th></tr>")
        for r in results:
            body += (
                f"<tr class='rowlink' onclick=\"location='/symbol/"
                f"{html.escape(r['symbol'])}'\">"
                f"<td>{C.symbol_link(r['symbol'])}</td>"
                f"<td>{C.tier_chip(r['tier'])}</td>"
                f"<td>{C.signed_pct(r.get('change_24h_pct'))}</td>"
                f"<td>{html.escape(str(r.get('quote_volume_24h', '—')))}</td>"
                f"<td>{C.capability_chip(r.get('capability', 'UNKNOWN'))}</td></tr>")
        body += "</table>"
    return C.page(f"Search — {query or ''}", "MOVERS", _banner(state), body,
                  search_query=query or "",
                  engine_html=C.engine_control_html(state))


def _svg_chart(points: List[Dict[str, Any]], symbol: str,
               range_name: str) -> str:
    if not points:
        return "<p class='note'>No price history in this range yet — warming.</p>"
    w, h, pad = 640, 220, 34
    prices = [p["price"] for p in points]
    lo, hi = min(prices), max(prices)
    span = (hi - lo) or abs(hi or 1.0) * 1e-6 or 1.0
    n = len(points)
    xs = [pad + (w - 2 * pad) * (i / max(n - 1, 1)) for i in range(n)]
    ys = [pad + (h - 2 * pad) * (1 - (p - lo) / span) for p in prices]
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    t0 = time.strftime("%H:%M", time.gmtime(points[0]["timestamp"] / 1000))
    t1 = time.strftime("%H:%M", time.gmtime(points[-1]["timestamp"] / 1000))
    return (
        f"<svg viewBox='0 0 {w} {h}' width='100%' role='img' "
        f"aria-label='mark price chart {html.escape(symbol)} {html.escape(range_name)}'>"
        f"<rect x='0' y='0' width='{w}' height='{h}' fill='#12161d'/>"
        f"<path d='{path}' fill='none' stroke='#6cb6ff' stroke-width='1.5'/>"
        f"<circle cx='{xs[-1]:.1f}' cy='{ys[-1]:.1f}' r='3' fill='#6cb6ff'/>"
        f"<text x='{pad}' y='{h - 8}' fill='#8b94a3' font-size='10'>{t0} UTC</text>"
        f"<text x='{w - pad - 40}' y='{h - 8}' fill='#8b94a3' font-size='10'>{t1} UTC</text>"
        f"<text x='4' y='14' fill='#8b94a3' font-size='10'>{hi:.4f}</text>"
        f"<text x='4' y='{h - pad}' fill='#8b94a3' font-size='10'>{lo:.4f}</text>"
        "</svg>")


def _integrity_cell(degraded: Any, gaps: Any) -> str:
    try:
        gap_count = int(gaps or 0)
    except (TypeError, ValueError):
        gap_count = 0
    if degraded:
        return (f"<span class='neg'>DEGRADED — Sequence gap active "
                f"({gap_count} gap{'s' if gap_count != 1 else ''})</span>")
    if gap_count > 0:
        return (f"<span class='pos'>HEALTHY — Recovered {gap_count} gap"
                f"{'s' if gap_count != 1 else ''}</span>")
    return "<span class='pos'>HEALTHY</span>"


_OI_CONTEXT_HELP = {
    "PRICE_UP_OI_UP": "price up + OI up (more contracts alongside higher price)",
    "PRICE_UP_OI_DOWN": "price up + OI down (fewer contracts alongside higher price)",
    "PRICE_DOWN_OI_UP": "price down + OI up (more contracts alongside lower price)",
    "PRICE_DOWN_OI_DOWN": "price down + OI down (fewer contracts alongside lower price)",
    "MIXED": "no joint direction (flat leg)",
    "UNKNOWN": "unknown (missing price or OI history)",
}


def _render_state_section(record: Any, subscribed: bool) -> str:
    """P1-12A market-state panel (observed HYPOTHESIS state, never a signal).

    Shows state + direction + as-of + top evidence + coverage. No LONG/
    SHORT wording, no entries, no recommendations. Discovery-only symbols
    get an honest no-state note instead of a fabricated classification.
    """
    head = ("<h2>Market state v0 (observed, HYPOTHESIS — NOT signals, "
            "NOT entries)</h2>")
    if not subscribed:
        return head + ("<p class='note'>DISCOVERY ONLY — no deep state is "
                        "computed for unsubscribed symbols.</p>")
    if not isinstance(record, dict) or not record:
        return head + ("<p class='note'>No state classification yet — "
                        "classifier warming up or probe not running.</p>")
    trans = record.get("transition") if isinstance(
        record.get("transition"), dict) else {}
    reasons = trans.get("reasons") if isinstance(
        trans.get("reasons"), list) else []
    validity = record.get("validity") if isinstance(
        record.get("validity"), dict) else {}
    missing = record.get("missing_features") if isinstance(
        record.get("missing_features"), list) else []
    evidence_for = record.get("evidence_for") if isinstance(
        record.get("evidence_for"), list) else []
    evidence_against = record.get("evidence_against") if isinstance(
        record.get("evidence_against"), list) else []
    try:
        observed = int(record.get("observed_at_ms") or 0)
        age_s = max(0, int(time.time() * 1000 - observed) // 1000) \
            if observed > 0 else None
        age = f"{age_s}s ago" if age_s is not None else "—"
    except (TypeError, ValueError):
        age = "—"
    since_ms = _finite(trans.get("state_since_ms"))
    duration_ms = _finite(trans.get("duration_ms"))
    try:
        duration_s = f"{float(duration_ms) / 1000:.0f}s" \
            if duration_ms is not None else "—"
    except (TypeError, ValueError):
        duration_s = "—"
    rows = [
        ("state", record.get("state", "UNKNOWN")),
        ("direction", record.get("direction", "UNKNOWN")),
        ("observed", age),
        ("rules", record.get("rules_version", "?")),
        ("previous", "%s / %s" % (trans.get("previous_state"),
                                  trans.get("previous_direction"))),
        ("phase since (transition time)", _fmt_ts(since_ms)),
        ("phase duration", duration_s),
        ("transition reasons",
         "; ".join(str(r) for r in reasons[:3]) or "—"),
        ("evidence for",
         "; ".join(str(e) for e in evidence_for[:6]) or "none recorded"),
        ("evidence against",
         "; ".join(str(e) for e in evidence_against[:6]) or "none recorded"),
        ("features used",
         ", ".join(str(f) for f in (
             record.get("features_used") or [])[:6]) or "—"),
        ("missing", ", ".join(str(f) for f in missing[:6]) or "none"),
        ("valid", "; ".join(str(r) for r in (
            validity.get("reasons") or [])) or "—"),
    ]
    return head + "<table class='kv'>" + "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in rows) + "</table>"


def render_symbol(state, symbol: str, range_name: str = "1h") -> Optional[str]:
    """Per-token intelligence page. None when the symbol is unknown."""
    sym = normalize_symbol(symbol)
    if sym is None:
        return None
    uni = compose_universe(state)
    feat_by = {f.get("symbol"): f for f in state.return_features()
               if isinstance(f, dict)}
    flow_by = {f.get("symbol"): f for f in state.flow_features()
               if isinstance(f, dict)}
    book_by = {f.get("symbol"): f for f in state.book_features()
               if isinstance(f, dict)}
    oi_by = {f.get("symbol"): f for f in state.oi_features()
             if isinstance(f, dict)}
    struct_by = {f.get("symbol"): f for f in state.structure_features()
                 if isinstance(f, dict)}
    try:
        _state_fn = getattr(state, "state_features", None)
        _state_rows = _state_fn() if callable(_state_fn) else []
    except Exception:
        _state_rows = []
    state_by = {f.get("symbol"): f for f in _state_rows
                if isinstance(f, dict)}
    disc_rows = discovery_rows(uni["discovery"])
    any_live = (set(feat_by) | set(flow_by) | set(book_by) | set(oi_by)
                | set(struct_by))
    known = (set(any_live) | set(disc_rows) | set(uni["core"])
             | set(uni["hot"]))
    if sym not in known:
        return None
    feat = feat_by.get(sym, {})
    disc = disc_rows.get(sym, {})
    subscribed = sym in any_live
    health = state.health()
    stale = health.get("status") == "stale"
    degraded = health.get("status") == "degraded"
    has_snap = state.snapshot() is not None
    warmup = feat.get("warmup_complete") if isinstance(feat, dict) else None
    tier = tier_for(sym, uni["discovery"])
    cap = capability_for(sym, subscribed=subscribed, warmup_complete=warmup,
                         snapshot_stale=stale and subscribed,
                         feed_degraded=degraded and subscribed,
                         has_snapshot=has_snap)
    price = feat.get("current_price", disc.get("price")) if isinstance(feat, dict) else disc.get("price")
    try:
        price_s = f"{float(price):.4f}" if price is not None else "—"
    except (TypeError, ValueError):
        price_s = "—"
    chg = disc.get("change_24h_pct")
    try:
        chg_s = f"{float(chg):+.2f}%" if chg is not None else "—"
    except (TypeError, ValueError):
        chg_s = "—"
    body = (f"<p>{C.tier_chip(tier)} {C.capability_chip(cap)} "
             f"<span class='note'>feed: {html.escape(health['status'].upper())}</span></p>")
    body += ("<div class='grid g4'>"
             f"<div class='card'><h3>Price (mark reference)</h3>"
             f"<div class='big'>{html.escape(price_s)}</div></div>"
             f"<div class='card'><h3>24h change (REST discovery)</h3>"
             f"<div class='big'>{C.signed_pct(chg)}</div></div>"
             f"<div class='card'><h3>Freshness</h3><div class='big'>"
             f"{html.escape(C.age(feat.get('sample_age_ms')) if isinstance(feat, dict) else None)}</div></div>"
             f"<div class='card'><h3>Quote volume 24h (discovery)</h3>"
             f"<div class='big'>{html.escape(str(disc.get('quote_volume_24h', '—')))}</div></div>"
             "</div>")
    body += ("<p class='note'>REST 24h change is exchange-computed and "
             "independent of the live anchored 24h return below (when the "
             "symbol is subscribed). They can disagree; neither is a signal."
             "</p>")
    if subscribed and isinstance(feat, dict):
        returns = feat.get("returns") if isinstance(feat.get("returns"), dict) else {}
        anchors = feat.get("anchor_ms") if isinstance(feat.get("anchor_ms"), dict) else {}
        src_ts = _finite(feat.get("source_timestamp_ms"))
        row_as_of = _finite(feat.get("updated_ms"))
        r24 = _finite(returns.get("24h"))
        a24 = _finite(anchors.get("24h"))
        anchor_px = None
        cur_px = _finite(feat.get("current_price"))
        if cur_px is not None and r24 is not None:
            try:
                anchor_px = cur_px / math.exp(r24)
            except (OverflowError, ValueError, ZeroDivisionError):
                anchor_px = None
        ref_rows = [
            ("reference price (markPrice)",
             f"{cur_px:.4f}" if cur_px is not None else "—"),
            ("reference time", _fmt_ts(src_ts)),
            ("row as-of (persisted)", _fmt_ts(row_as_of)),
            ("history span",
             f"{float(feat.get('history_span_ms', 0)) / 3600000:.1f}h"
             if _finite(feat.get("history_span_ms")) is not None else "—"),
            ("24h anchor time", _fmt_ts(a24)),
            ("24h anchor price (derived P/exp(r), not observed)",
             f"{anchor_px:.4f}" if anchor_px is not None else "—"),
        ]
        body += ("<h2>Reference &amp; 24h anchor (live, descriptive)</h2>"
                 "<table class='kv'>"
                 + "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>"
                           for k, v in ref_rows) + "</table>"
                 "<p class='note'>24h attribution (how much of the 24h move "
                 "comes from the current price vs the rolling anchor) needs "
                 "consecutive evaluations; only the latest row is retained, "
                 "so the split is UNKNOWN — never simulated.</p>")
    if subscribed and isinstance(feat, dict):
        returns = feat.get("returns") if isinstance(feat.get("returns"), dict) else {}
        momentum = feat.get("momentum") if isinstance(feat.get("momentum"), dict) else {}
        vel = momentum.get("velocity") if isinstance(momentum.get("velocity"), dict) else {}
        acc = momentum.get("acceleration") if isinstance(momentum.get("acceleration"), dict) else {}
        ranks = feat.get("ranks") if isinstance(feat.get("ranks"), dict) else {}
        rv = ranks.get("velocity_1m") if isinstance(ranks.get("velocity_1m"), dict) else {}
        body += ("<h2>Headline features (live, descriptive only)</h2>"
                 "<div class='grid g4'>"
                 + "".join(
                     f"<div class='card'><h3>{html.escape(k)}</h3>"
                      f"<div class='big'>{C.signed_frac(returns.get(k), 3)}</div></div>"
                     for k in ("1m", "5m"))
                 + f"<div class='card'><h3>Velocity 1m</h3><div class='big'>{C.sci(vel.get('1m'))}</div></div>"
                 + f"<div class='card'><h3>Acceleration 1m</h3><div class='big'>{C.sci(acc.get('1m'), '/s²')}</div></div>"
                 + "</div>")
        body += ("<table class='kv'><tr><th>rank (velocity 1m)</th><td>"
                 + html.escape(str(rv.get("rank", "—"))) + "</td></tr>"
                 "<tr><th>rank change</th><td>"
                 + html.escape(str(rv.get("change", "—"))) + "</td></tr></table>")
    else:
        body += ("<p class='warn'>DISCOVERY ONLY — NO LIVE DEEP FEATURES. "
                 "This symbol is not subscribed: flow, book, OI, VWAP, "
                 "volatility and structure are unavailable and never estimated.</p>")

    # Price chart (mark-price samples; honest partial history).
    if range_name not in VALID_RANGES:
        range_name = "1h"
    points: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}
    chart_note = ""
    if subscribed:
        try:
            points, meta = price_history_points(state.store, sym, range_name)
            if meta.get("insufficient"):
                chart_note = ("<p class='note'>Insufficient history in this range — "
                              "warming (partial history shown honestly, never invented).</p>")
        except ValueError:
            points, meta = [], {}
            chart_note = "<p class='note'>Price history unavailable.</p>"
    else:
        chart_note = ("<p class='note'>DISCOVERY ONLY — no mark-price history "
                      "for unsubscribed symbols.</p>")
    btns = "".join(
        f"<a href='/symbol/{html.escape(sym)}?range={r}' "
        f"class='{'active' if r == range_name else ''}'>{r}</a>"
        for r in ("5m", "15m", "1h", "4h", "24h"))
    body += (f"<h2>Price chart (mark price, {html.escape(range_name)})</h2>"
             f"<div class='chartbtns'>{btns}"
             f"<a href='/api/symbol/{html.escape(sym)}/price?range={html.escape(range_name)}'>JSON</a>"
             f"<a href='/api/symbol/{html.escape(sym)}/price.csv?range={html.escape(range_name)}'>CSV</a>"
             f"</div>")
    body += _svg_chart(points, sym, range_name) + chart_note
    if points:
        body += (f"<p class='note'>Latest {points[-1]['price']:.4f} · "
                 f"{len(points)} points (of {meta.get('points_total', len(points))}"
                 f"{', downsampled' if meta.get('truncated') else ''}) · "
                 f"range {html.escape(range_name)} · freshness "
                 f"{html.escape(C.age(feat.get('sample_age_ms')) if isinstance(feat, dict) else None)}</p>")

    if subscribed:
        # Momentum panel
        returns = feat.get("returns") if isinstance(feat.get("returns"), dict) else {}
        momentum = feat.get("momentum") if isinstance(feat.get("momentum"), dict) else {}
        vel = momentum.get("velocity") if isinstance(momentum.get("velocity"), dict) else {}
        acc = momentum.get("acceleration") if isinstance(momentum.get("acceleration"), dict) else {}
        body += "<h2>Momentum (descriptive, NOT signals)</h2><div class='grid g2'>"
        body += ("<div class='card'><h3>Returns (live, anchored)</h3><table class='kv'>"
                 + "".join(f"<tr><th>{tf}</th><td>{C.signed_frac(returns.get(tf), 3)}</td></tr>"
                           for tf in ("1m", "3m", "5m", "15m", "1h", "4h", "24h"))
                 + "</table></div>")
        body += ("<div class='card'><h3>Velocity / acceleration / rank</h3>"
                 "<table class='kv'>"
                 f"<tr><th>velocity 1m</th><td>{C.sci(vel.get('1m'))}</td></tr>"
                 f"<tr><th>acceleration 1m</th><td>{C.sci(acc.get('1m'), '/s²')}</td></tr>"
                 "</table></div></div>")
        # Flow panel
        flow = flow_by.get(sym)
        if flow:
            horizons = flow.get("horizons") if isinstance(flow.get("horizons"), dict) else {}
            h1 = horizons.get("1m") if isinstance(horizons.get("1m"), dict) else {}
            baselines = flow.get("baselines") if isinstance(flow.get("baselines"), dict) else {}
            b1 = baselines.get("1m") if isinstance(baselines.get("1m"), dict) else {}
            buy = h1.get("buy_pct")
            sell = h1.get("sell_pct")
            try:
                bar = ("—" if buy is None or sell is None else
                       f"aggr BUY {float(buy):.0f}% / aggr SELL {float(sell):.0f}%")
            except (TypeError, ValueError):
                bar = "—"
            body += ("<h2>Trade flow (aggressor side only, NOT signals)</h2>"
                     "<table class='kv'>"
                     f"<tr><th>1m notional</th><td>{html.escape(str(h1.get('notional', '—')))}</td></tr>"
                     f"<tr><th>aggressive split</th><td>{html.escape(bar)}</td></tr>"
                     f"<tr><th>signed delta</th><td>{C.signed_num(h1.get('signed_delta'))}</td></tr>"
                     f"<tr><th>delta ratio</th><td>{C.signed_num(h1.get('delta_ratio'), 3)}</td></tr>"
                     f"<tr><th>trade rate</th><td>{C.sci(h1.get('trade_rate'))}</td></tr>"
                     f"<tr><th>volume z (1m)</th><td>{html.escape(str(b1.get('z_score', '—')))}</td></tr>"
                     f"<tr><th>freshness / warmup</th><td>{html.escape(C.age(flow.get('freshness_ms')))} / "
                     + html.escape(str(flow.get('warmup_complete', ''))) + "</td></tr></table>")
        else:
            body += ("<h2>Trade flow</h2><p class='note'>No flow features yet — "
                     "WARMING.</p>")
        # Book panel
        book = book_by.get(sym)
        if book:
            bkin = book.get("book") if isinstance(book.get("book"), dict) else {}
            depth = bkin.get("depth") if isinstance(bkin.get("depth"), dict) else {}
            top20 = depth.get("top20") if isinstance(depth.get("top20"), dict) else {}
            slopes = bkin.get("slopes") if isinstance(bkin.get("slopes"), dict) else {}
            conc = bkin.get("concentration") if isinstance(bkin.get("concentration"), dict) else {}
            cbid = conc.get("bid") if isinstance(conc.get("bid"), dict) else {}
            body += ("<h2>Order book (visible depth, NOT signals)</h2>"
                     "<table class='kv'>"
                     f"<tr><th>best bid / ask</th><td>{html.escape(str(bkin.get('best_bid', '—')))} / "
                     f"{html.escape(str(bkin.get('best_ask', '—')))}</td></tr>"
                     f"<tr><th>spread bps</th><td>{html.escape(str(bkin.get('spread_bps', '—')))}</td></tr>"
                     f"<tr><th>visible bid notional</th><td>{html.escape(str(top20.get('bid_notional', '—')))}</td></tr>"
                     f"<tr><th>visible ask notional</th><td>{html.escape(str(top20.get('ask_notional', '—')))}</td></tr>"
                     f"<tr><th>imbalance</th><td>{C.signed_num(bkin.get('imbalance_notional'), 3)}</td></tr>"
                     f"<tr><th>microprice displacement</th><td>{C.signed_num(bkin.get('microprice_displacement_bps'), 3)}</td></tr>"
                     f"<tr><th>slope asymmetry</th><td>{C.signed_num(slopes.get('asymmetry'), 3)}</td></tr>"
                     f"<tr><th>concentration 10bps</th><td>{html.escape(str(cbid.get('within_10bps', '—')))}</td></tr>"
                     f"<tr><th>integrity</th><td>{_integrity_cell(book.get('degraded'), book.get('sequence_gaps'))}</td></tr>"
                     f"<tr><th>freshness</th><td>{html.escape(C.age(book.get('freshness_ms')))}</td></tr>"
                     "</table>")
        else:
            body += ("<h2>Order book</h2><p class='note'>No book features yet — "
                     "WARMING.</p>")
        # OI panel
        oi = oi_by.get(sym)
        if oi:
            horizons = oi.get("horizons") if isinstance(oi.get("horizons"), dict) else {}
            ctx = oi.get("price_oi_context") if isinstance(oi.get("price_oi_context"), dict) else {}
            c1 = str(ctx.get("1m", "UNKNOWN"))
            body += ("<h2>Open interest (descriptive, NOT signals)</h2>"
                     "<table class='kv'>"
                     f"<tr><th>current OI (base units, e.g. BTC — NOT notional)</th><td>{html.escape(str(oi.get('current_oi', '—')))}</td></tr>"
                     + "".join(
                         f"<tr><th>Δ {h} (base units)</th><td>{C.signed_num((horizons.get(h) or {}).get('delta') if isinstance(horizons.get(h), dict) else None)}</td></tr>"
                         for h in ("1m", "5m", "15m"))
                     + f"<tr><th>rate</th><td>{html.escape(str((horizons.get('1m') or {}).get('rate') if isinstance(horizons.get('1m'), dict) else '—'))}</td></tr>"
                     f"<tr><th>acceleration</th><td>{C.sci(oi.get('acceleration_per_s2'), '/s²')}</td></tr>"
                     f"<tr><th>price/OI context</th><td title='{html.escape(_OI_CONTEXT_HELP.get(c1, c1))}'>"
                     f"{html.escape(c1)}</td></tr>"
                     f"<tr><th>freshness{' STALE' if oi.get('stale') else ''}</th>"
                     f"<td>{html.escape(C.age(oi.get('freshness_ms')))}</td></tr>"
                     "</table>"
                     "<p class='note'>Context labels describe joint price/OI direction only. "
                     "Valued (notional) OI: UNKNOWN — no persisted valuation basis "
                     "(base units × a price would mix timestamps); never estimated. "
                     "Long/short account ratios: no account data exists — not shown, "
                     "never inferred from flow notionals.</p>")
        else:
            body += ("<h2>Open interest</h2><p class='note'>No OI features yet — "
                     "WARMING or STALE.</p>")
        # VWAP / vol / structure panel
        struct = struct_by.get(sym)
        if struct:
            vwap = struct.get("vwap") if isinstance(struct.get("vwap"), dict) else {}
            vol = struct.get("volatility") if isinstance(struct.get("volatility"), dict) else {}
            ranges = struct.get("ranges") if isinstance(struct.get("ranges"), dict) else {}
            sts = struct.get("structure") if isinstance(struct.get("structure"), dict) else {}
            struct_as_of = _finite(struct.get("as_of_ms"))
            vwap_rows = []
            for h in ("1m", "3m", "5m", "15m"):
                vh = vwap.get(h) if isinstance(vwap.get(h), dict) else {}
                window_ms = _finite(vh.get("window_ms"))
                anchor = None
                if struct_as_of is not None and window_ms is not None:
                    anchor = struct_as_of - window_ms
                vwap_rows.append(
                    f"<tr><th>{h} VWAP (trailing, anchor {_fmt_ts(anchor)})</th>"
                    f"<td>{html.escape(str(vh.get('vwap', '—')))}</td></tr>"
                    f"<tr><th>{h} displacement bps</th>"
                    f"<td>{C.signed_num(vh.get('displacement_bps'), 1)}</td></tr>")
            body += "<h2>VWAP / volatility / structure (descriptive, NOT signals)</h2><div class='grid g2'>"
            body += ("<div class='card'><h3>VWAP (flow provenance)</h3><table class='kv'>"
                     + "".join(vwap_rows)
                     + "</table>"
                     "<p class='note'>Windows trail the feature as-of; the "
                     "anchor is its start (as_of − window). Reference: "
                     "markPrice at as-of; displacement raw, never a signal."
                     "</p></div>")
            body += ("<div class='card'><h3>Realized volatility (raw)</h3><table class='kv'>"
                     + "".join(
                         f"<tr><th>RV {h}</th><td>{html.escape(str((vol.get(h) or {}).get('realized_vol', '—') if isinstance(vol.get(h), dict) else 'UNKNOWN'))}</td></tr>"
                         for h in ("1m", "5m", "15m", "1h"))
                     + "</table></div>")
            r5 = ranges.get("5m") if isinstance(ranges.get("5m"), dict) else {}
            body += ("<div class='card'><h3>Range 5m</h3><table class='kv'>"
                     f"<tr><th>high / low</th><td>{html.escape(str(r5.get('high', '—')))} / "
                     f"{html.escape(str(r5.get('low', '—')))}</td></tr>"
                     f"<tr><th>range position</th><td>{html.escape(str(r5.get('range_position', 'UNKNOWN')))}</td></tr>"
                     f"<tr><th>expansion</th><td>{html.escape(str(r5.get('expansion_ratio', 'UNKNOWN')))}</td></tr>"
                     "</table></div>")
            body += ("<div class='card'><h3>Structure</h3><table class='kv'>"
                     f"<tr><th>swing high / low</th><td>{html.escape(str(sts.get('last_swing_high', 'UNKNOWN')))} / "
                     f"{html.escape(str(sts.get('last_swing_low', 'UNKNOWN')))}</td></tr>"
                     f"<tr><th>HH/LH</th><td>{html.escape(str(sts.get('higher_high', 'UNKNOWN')))} / "
                     f"{html.escape(str(sts.get('lower_high', 'UNKNOWN')))}</td></tr>"
                     f"<tr><th>HL/LL</th><td>{html.escape(str(sts.get('higher_low', 'UNKNOWN')))} / "
                     f"{html.escape(str(sts.get('lower_low', 'UNKNOWN')))}</td></tr>"
                     f"<tr><th>prior-range state</th><td>{html.escape(str(sts.get('breakout_state', 'UNKNOWN')))}</td></tr>"
                     f"<tr><th>freshness</th><td>{html.escape(C.age(struct.get('price_age_ms')))}</td></tr>"
                     "</table></div></div>")
        else:
            body += ("<h2>VWAP / volatility / structure</h2>"
                     "<p class='note'>No structure features yet — UNKNOWN / WARMING.</p>")
        try:
            funding = funding_snapshot(state.store, sym)
        except Exception:
            funding = {"symbol": sym, "next_funding_time_ms": None,
                       "funding_rate": None, "observation_ms": None,
                       "settled_history": "UNKNOWN", "calendar": "UNKNOWN"}
        obs_age = None
        if isinstance(funding.get("observation_ms"), int):
            try:
                obs_age = max(0, int(time.time() * 1000)
                              - int(funding["observation_ms"])) // 1000
            except (TypeError, ValueError):
                obs_age = None
        body += ("<h2>Funding (quoted context, NOT settled accounting)</h2>"
                 "<table class='kv'>"
                 f"<tr><th>next funding time</th><td>{html.escape(_fmt_ts(funding.get('next_funding_time_ms')))}</td></tr>"
                 f"<tr><th>quoted rate (as-of observation)</th><td>{html.escape(str(funding.get('funding_rate', '—')))}</td></tr>"
                 f"<tr><th>observation age</th><td>{html.escape(f'{obs_age}s ago' if obs_age is not None else '—')}</td></tr>"
                 f"<tr><th>settled history</th><td>UNKNOWN (not computed)</td></tr>"
                 f"<tr><th>calendar</th><td>UNKNOWN (no venue calendar stored)</td></tr>"
                 "</table>"
                 "<p class='note'>Rate and next time come from the latest "
                 "persisted markPrice array only. The rate is quoted-as-of "
                 "(an estimate for the coming settlement), never a settled "
                 "record. Settled funding accounting belongs to versioned "
                 "study runs, not to this panel.</p>")
    body += _render_state_section(state_by.get(sym), subscribed)
    hist = []
    try:
        hist_fn = getattr(state, "history_coverage", None)
        hist = hist_fn(sym) if callable(hist_fn) else []
    except Exception:
        hist = []
    if hist:
        rows = []
        for h in sorted(hist, key=lambda r: str(r.get("interval"))):
            last = h.get("last_open")
            try:
                last_s = time.strftime("%Y-%m-%d", time.gmtime(int(last) / 1000)) \
                    if last else "—"
            except (TypeError, ValueError, OverflowError):
                last_s = "—"
            rows.append(
                f"<tr><th>{html.escape(str(h.get('interval')))} "
                f"{html.escape(str(h.get('source')))}</th>"
                f"<td>{h.get('actual_bars')}/{h.get('expected_bars')} bars "
                f"(ratio {h.get('coverage_ratio')}) · through {last_s} UTC</td></tr>")
        body += ("<h2>Historical coverage (research store)</h2>"
                 "<table class='kv'>" + "".join(rows) + "</table>"
                 "<p class='note'>REST bootstrap history for research; "
                 "live features above remain the current feed.</p>")
    else:
        body += ("<h2>Historical coverage</h2>"
                 "<p class='note'>No historical research coverage yet.</p>")
    try:
        studies_fn = getattr(state, "event_studies", None)
        studies = studies_fn() if callable(studies_fn) else []
    except Exception:
        studies = []
    if studies:
        srows = []
        for s in studies[:6]:
            hs = s.get("horizons") or []
            tot = sum(int(h.get("n_total", 0) or 0) for h in hs)
            srows.append(
                f"<tr><th>{html.escape(str(s.get('definition')))}</th>"
                f"<td>events {tot} · sample/n displayed per horizon "
                f"in /api/events/studies/{html.escape(str(s.get('definition')))}</td></tr>")
        body += ("<h2>Historical research</h2>"
                 "<p class='note'>RESEARCH ONLY — NOT A SIGNAL. "
                 "Descriptive event outcomes; no confidence badge.</p>"
                 "<table class='kv'>" + "".join(srows) + "</table>")
    else:
        body += ("<h2>Historical research</h2>"
                 "<p class='note'>RESEARCH ONLY — NOT A SIGNAL. "
                 "No event studies stored yet.</p>")
    return C.page(f"{sym} — token intelligence", "MOVERS", _banner(state), body,
                  engine_html=C.engine_control_html(state))


def render_system(state) -> str:
    """Technical diagnostics (P1-09): keeps every P1-03..P1-08 diagnostic."""
    snap = state.snapshot()
    health = state.health()
    if snap is None:
        return C.page("System — Binance Futures", "SYSTEM",
                      C.banner_html_fn({}, health["status"]),
                      "<p class='warn'>No telemetry snapshot persisted yet.</p>",
                      engine_html=C.engine_control_html(state))
    safety = _safe_dict(snap.get("safety"))
    dq = _safe_dict(snap.get("dataQuality"))
    latency = _safe_dict(snap.get("latency"))
    processing = _safe_dict(snap.get("processing"))
    clock = _safe_dict(snap.get("clock"))
    rj = state.rejection_stats()
    storage = state.storage()
    try:
        from .dashboard import stream_rows, latency_rows
    except Exception:  # pragma: no cover - fallback renders raw JSON
        stream_rows = latency_rows = None
    body = ("<p class='note'>Low-level diagnostics live here so "
            "<a href='/overview'>/overview</a> stays a market summary. "
            "Machine-readable APIs:</p><p class='note'>"
            + " ".join(
                f"<a href='{p}'>{p}</a>" for p in (
                    "/api/health", "/api/snapshot", "/api/features/returns",
                    "/api/features/momentum", "/api/features/flow",
                    "/api/features/volume", "/api/features/book",
                    "/api/features/open-interest", "/api/features/vwap",
                     "/api/features/volatility", "/api/features/structure",
                     "/api/discovery", "/api/opportunities", "/opportunities",
                     "/api/search?q=BTC")) + "</p>")
    if stream_rows is not None:
        body += ("<h2>Streams</h2><div class='scrollx'><table><tr><th>stream</th>"
                 "<th>messages</th><th>msg/s</th><th>max silence ms</th>"
                 "<th>stale</th><th>silent</th></tr>")
        for row in stream_rows(dq):
            body += (f"<tr><td>{html.escape(row['stream'])}</td>"
                     f"<td>{row['messages']}</td><td>{row['rate_per_s']}</td>"
                     f"<td>{row['max_silence_ms']}</td>"
                     f"<td>{'YES' if row['stale'] else 'no'}</td>"
                     f"<td>{'yes' if row['silent'] else 'no'}</td></tr>")
        body += "</table></div>"
        for metric in ("rawEventLagMs", "correctedEventLagMs"):
            rows = latency_rows(latency, metric)
            if rows:
                body += (f"<h2>Latency {html.escape(metric)} (ms)</h2>"
                         "<div class='scrollx'><table><tr><th>key</th><th>n</th>"
                         "<th>p50</th><th>p95</th><th>max</th></tr>")
                for r in rows:
                    body += (f"<tr><td>{html.escape(r['key'])}</td>"
                             f"<td>{r['count']}</td><td>{r['p50']}</td>"
                             f"<td>{r['p95']}</td><td>{r['max']}</td></tr>")
                body += "</table></div>"
        prows = latency_rows(processing, "processingLatencyMs")
        if prows:
            body += ("<h2>Processing latency (ms)</h2>"
                     "<div class='scrollx'><table><tr><th>key</th><th>n</th>"
                     "<th>p50</th><th>p95</th><th>max</th></tr>")
            for r in prows:
                body += (f"<tr><td>{html.escape(r['key'])}</td>"
                         f"<td>{r['count']}</td><td>{r['p50']}</td>"
                         f"<td>{r['p95']}</td><td>{r['max']}</td></tr>")
            body += "</table></div>"
    body += ("<h2>Clock</h2><table class='kv'>"
             f"<tr><th>offset ms</th><td>{html.escape(str(clock.get('clockOffsetMs', '?')))}</td></tr>"
             f"<tr><th>RTT ms</th><td>{html.escape(str(clock.get('serverTimeRttMs', '?')))}</td></tr>"
             f"<tr><th>syncs ok/failed</th><td>{clock.get('clockSyncSuccessful', '?')}/"
             f"{clock.get('clockSyncFailed', '?')}</td></tr></table>")
    body += ("<h2>Rejections / skew (run counter vs retained rows)</h2>"
             "<table class='kv'>"
             f"<tr><th>timestamp rejected — this run (probe counter)</th>"
             f"<td>{html.escape(str(dq.get('timestampRejected', '?')))}</td></tr>"
             f"<tr><th>retained rejected rows (persistence)</th>"
             f"<td>{html.escape(str(rj.get('total_rejected', '?')))}</td></tr>"
             f"<tr><th>rejection rate (retained)</th>"
             f"<td>{float(rj.get('rejection_rate', 0.0)):.1%}</td></tr>"
             f"<tr><th>by reason</th><td>{html.escape(json.dumps(rj.get('by_reason', {})))}</td></tr>"
             f"<tr><th>by stream</th><td>{html.escape(json.dumps(rj.get('by_stream', {})))}</td></tr>"
             "</table>")
    body += ("<h2>Persistence</h2><table class='kv'>"
             f"<tr><th>reachable</th><td>{html.escape(str(storage.get('exists', '?')))}</td></tr>"
             f"<tr><th>db path</th><td>{html.escape(str(storage.get('db_path', '?')))}</td></tr>"
             f"<tr><th>size bytes</th><td>{html.escape(str(storage.get('size_bytes', '?')))}</td></tr>"
             f"<tr><th>rows</th><td>{html.escape(json.dumps(storage.get('rows', {})))}</td></tr>"
             "</table>")
    body += ("<h2>Safety</h2><table class='kv'>"
             f"<tr><th>BOT_MODE</th><td>{html.escape(str(safety.get('BOT_MODE', '?')))}</td></tr>"
             f"<tr><th>apiKeysUsed</th><td>{html.escape(str(safety.get('apiKeysUsed', '?')))}</td></tr>"
             f"<tr><th>realOrdersSent</th><td>{html.escape(str(safety.get('realOrdersSent', '?')))}</td></tr>"
             f"<tr><th>realCapitalAtRisk</th><td>{html.escape(str(safety.get('realCapitalAtRisk', '?')))}</td></tr>"
             f"<tr><th>authenticatedClientsPresent</th>"
             f"<td>{html.escape(str(safety.get('authenticatedClientsPresent', '?')))}</td></tr>"
              f"<tr><th>orderExecutionPathPresent</th>"
              f"<td>{html.escape(str(safety.get('orderExecutionPathPresent', '?')))}</td></tr>"
              "</table>")
    return C.page("System — Binance Futures", "SYSTEM",
                  C.banner_html_fn(safety, health["status"]), body,
                  engine_html=C.engine_control_html(state))


def render_opportunities(state) -> str:
    """Minimal P1-13A research-only read surface (NOT the P1-13B UX).

    Lists setup candidates with family / symbol / direction / state /
    reason / counterevidence / freshness / lifecycle / coverage / version.
    Empty until the engine observes qualifying setups — never fabricated.
    """
    try:
        cands_fn = getattr(state, "opportunity_candidates", None)
        cands = cands_fn() if callable(cands_fn) else []
    except Exception:
        cands = []
    try:
        ev_fn = getattr(state, "opportunity_events", None)
        events = ev_fn(limit=20) if callable(ev_fn) else []
    except Exception:
        events = []
    body = ("<p class='warn'>RESEARCH ONLY — NOT A TRADE SIGNAL. "
            "Setups worth studying; no entries, exits, stops, targets, "
            "probabilities, or recommendations. Ranking is research "
            "priority, not expected profit.</p>")
    if not cands:
        body += ("<h2>Setup candidates</h2>"
                 "<p class='note'>No qualifying setups observed yet. "
                 "Candidates appear here only when LIVE deep-data evidence "
                 "meets the versioned family rules; discovery-only, stale, "
                 "or incomplete inputs are excluded or marked "
                 "INSUFFICIENT_DATA, never zero-filled.</p>")
    else:
        rows = []
        for cand in sorted(
                cands, key=lambda c: (
                    -float((c.get("ranking") or {}).get("score", 0.0)),
                    str(c.get("symbol", "")), str(c.get("setup_family", "")))):
            if not isinstance(cand, dict):
                continue
            fresh = cand.get("data_freshness") if isinstance(
                cand.get("data_freshness"), dict) else {}
            rank = cand.get("ranking") if isinstance(
                cand.get("ranking"), dict) else {}
            hist = cand.get("historical_reference") if isinstance(
                cand.get("historical_reference"), dict) else {}
            rows.append(
                f"<tr><td>{html.escape(str(cand.get('setup_family', '?')))}</td>"
                f"<td>{html.escape(str(cand.get('symbol', '?')))}</td>"
                f"<td>{html.escape(str(cand.get('direction', '?')))}</td>"
                f"<td>{html.escape(str(cand.get('market_state', '?')))}</td>"
                f"<td>{html.escape(str(cand.get('eligibility_reason', ''))[:160])}</td>"
                f"<td>{html.escape('; '.join(str(e) for e in (cand.get('evidence_against') or [])[:2]) or 'none')}</td>"
                f"<td>{html.escape(str(fresh.get('price_age_ms', '?')))} ms</td>"
                f"<td>{html.escape(str(cand.get('lifecycle', '?')))}</td>"
                f"<td>{html.escape(str(cand.get('capability_tier', '?')))}</td>"
                f"<td>{html.escape(str(cand.get('rule_version', '?')))}</td>"
                f"<td>{html.escape(str(rank.get('score', '?')))}</td>"
                f"<td>{html.escape(str(hist.get('status', '?')))}</td></tr>")
        body += ("<h2>Setup candidates (research priority order)</h2>"
                 "<div class='scrollx'><table><tr><th>family</th><th>symbol</th>"
                 "<th>direction</th><th>state</th><th>reason</th>"
                 "<th>counterevidence</th><th>freshness</th><th>lifecycle</th>"
                 "<th>coverage</th><th>version</th><th>priority</th>"
                 "<th>history</th></tr>" + "".join(rows) + "</table></div>")
    if events:
        erows = "".join(
            f"<tr><td>{html.escape(str(e.get('symbol', '?')))}</td>"
            f"<td>{html.escape(str(e.get('family', '?')))}</td>"
            f"<td>{html.escape(str(e.get('transition', '?')))}</td>"
            f"<td>{html.escape(str(e.get('reason', ''))[:160])}</td></tr>"
            for e in events if isinstance(e, dict))
        body += ("<h2>Lifecycle transitions (recent)</h2>"
                 "<div class='scrollx'><table><tr><th>symbol</th><th>family</th>"
                 "<th>transition</th><th>reason</th></tr>" + erows + "</table></div>")
    body += ("<p class='note'>Machine-readable: "
             "<a href='/api/opportunities'>/api/opportunities</a> "
             "(versioned candidate view-model for the future BFF; "
             "the browser never computes setups).</p>")
    return C.page("Opportunities (research) — Binance Futures", "SYSTEM",
                  _banner(state), body,
                  engine_html=C.engine_control_html(state))
