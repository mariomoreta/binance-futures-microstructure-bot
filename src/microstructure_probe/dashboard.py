"""P1-09 market-intelligence terminal (stdlib only, no new dependencies).

Reads the P1-02 persistence store and renders operator pages. This module is
visualization only: nothing here can trade, and the engine never consumes
anything rendered here.

Routes: / (→ /overview), /overview, /movers, /search, /symbol/:symbol,
/system, /api/health, /api/snapshot, /api/features/returns,
/api/features/momentum, /api/features/flow, /api/features/volume,
/api/features/book, /api/features/open-interest, /api/features/vwap,
/api/features/volatility, /api/features/structure, /api/discovery,
/api/search, /api/symbol/:symbol/price[.csv].

Presentation lives in dashboard_views.py / dashboard_components.py;
composition helpers live in dashboard_data.py. This module keeps routing,
lifecycle CLI, health model, and backwards-compatible render entry points.

Lifecycle CLI (operator commands, Binance dashboard only):
    python -m microstructure_probe.dashboard start [--port N] [--db PATH]
    python -m microstructure_probe.dashboard stop
    python -m microstructure_probe.dashboard restart
    python -m microstructure_probe.dashboard status
    python -m microstructure_probe.dashboard serve --port N [--db PATH]
    python -m microstructure_probe.dashboard pick-port
"""

from __future__ import annotations

import argparse
import html
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .persistence import PersistenceStore

DASHBOARD_VERSION = "0.8.0"
HOST = "127.0.0.1"
PORT_CANDIDATES = [8091, 8092, 8093, 8094, 8095, 18091, 18765]
PIDFILE_NAME = "dashboard.pid"
STALE_SNAPSHOT_SECONDS = 120.0
DEGRADED_REJECTION_RATE = 0.5

STATUS_LABELS = {
    "ok": "HEALTHY",
    "degraded": "DEGRADED",
    "stale": "STALE",
    "unknown": "UNKNOWN",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def default_db_path() -> Path:
    return repo_root() / "data" / "microprobe.db"


def pidfile_path() -> Path:
    return repo_root() / "logs" / PIDFILE_NAME


# --------------------------------------------------------------------------
# Port selection
# --------------------------------------------------------------------------

def is_port_free(port: int, host: str = HOST) -> bool:
    """True if nothing is listening on host:port (never kills anything)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(candidates: List[int] = PORT_CANDIDATES,
                   host: str = HOST) -> int:
    """First free port from the ordered candidate list. Raises if all busy."""
    for port in candidates:
        if is_port_free(port, host):
            return port
    raise RuntimeError(f"no free dashboard port on {host} from {candidates}")


# --------------------------------------------------------------------------
# Process identity (safe PID handling — never touch unrelated processes)
# --------------------------------------------------------------------------

def process_info(pid: int) -> Tuple[Optional[str], Optional[str]]:
    """(image_name, creation_time) for pid, or (None, None) if not present."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return None, None
    image = None
    for line in out:
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].strip() == str(pid):
            image = parts[0].strip('"')
            break
    if image is None:
        return None, None
    creation = None
    try:
        wmic = subprocess.run(
            ["wmic", "process", "where", f"ProcessId={pid}",
             "get", "CreationDate", "/VALUE"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        for line in wmic.splitlines():
            if line.strip().startswith("CreationDate="):
                creation = line.strip().split("=", 1)[1]
                break
    except (OSError, subprocess.SubprocessError):
        creation = None
    return image, creation


def pid_is_ours(pid: int, expected_creation: Optional[str]) -> bool:
    """True only if pid exists, looks like Python, and matches the recorded
    creation time (when recorded). Stale/reused PIDs return False."""
    image, creation = process_info(pid)
    if image is None or "python" not in image.lower():
        return False
    if expected_creation and creation and creation != expected_creation:
        return False
    return True


def read_pidfile() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(pidfile_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_pidfile(pid: int, port: int, url: str) -> None:
    pidfile_path().parent.mkdir(parents=True, exist_ok=True)
    _, creation = process_info(pid)
    pidfile_path().write_text(json.dumps({
        "pid": pid,
        "port": port,
        "url": url,
        "created": creation,
        "version": DASHBOARD_VERSION,
    }), encoding="utf-8")


def remove_pidfile() -> None:
    try:
        pidfile_path().unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------
# Health model (display heuristics only — never trade signals)
# --------------------------------------------------------------------------

def compute_health(snapshot: Optional[Dict[str, Any]],
                   rejection_stats: Dict[str, Any],
                   now: float = None) -> Dict[str, Any]:
    """Overall dashboard status from persisted state.

    ok: fresh snapshot, no stale streams, no reconnects, low rejection rate.
    degraded: fresh snapshot but transport/quality warnings present.
    stale: snapshot too old (or persistence unreachable — handled by caller).
    unknown: no snapshot yet.
    """
    now = time.time() if now is None else now
    if snapshot is None:
        return {"status": "unknown", "reasons": ["no telemetry snapshot persisted yet"]}
    age = now - float(snapshot.get("snapshotTimestamp") or 0.0)
    if age > STALE_SNAPSHOT_SECONDS:
        return {"status": "stale",
                "reasons": [f"latest snapshot is {age:.0f}s old (>{STALE_SNAPSHOT_SECONDS:.0f}s)"]}
    dq = snapshot.get("dataQuality", {}) or {}
    reasons: List[str] = []
    if dq.get("staleStreams"):
        reasons.append(f"stale streams: {', '.join(dq['staleStreams'])}")
    reconnects = dq.get("reconnections", {}) or {}
    total_reconnects = sum(int(v) for v in reconnects.values())
    if total_reconnects > 0:
        reasons.append(f"{total_reconnects} websocket reconnects observed")
    rate = float(rejection_stats.get("rejection_rate", 0.0))
    if rate > DEGRADED_REJECTION_RATE:
        reasons.append(f"timestamp rejection rate {rate:.1%} exceeds {DEGRADED_REJECTION_RATE:.0%}")
    if reasons:
        return {"status": "degraded", "reasons": reasons}
    return {"status": "ok", "reasons": []}


# --------------------------------------------------------------------------
# Read models (P1-02 read paths, or thin wrappers — never log scraping)
# --------------------------------------------------------------------------

class DashboardState:
    """All data the pages/API need, sourced only from the persistence store."""

    def __init__(self, store: PersistenceStore) -> None:
        self.store = store
        # Idempotent: creates the schema on a fresh DB, no-op otherwise.
        # Without this, a store instance that never wrote would report
        # "no snapshot" even when rows exist in the file.
        try:
            self.store.init_db()
        except (OSError, sqlite3.Error):
            pass
        self.server_started_monotonic = time.monotonic()

    def snapshot(self) -> Optional[Dict[str, Any]]:
        try:
            return self.store.latest_telemetry()
        except (OSError, sqlite3.Error):
            return None

    def rejection_stats(self) -> Dict[str, Any]:
        try:
            return self.store.get_rejection_stats()
        except (OSError, sqlite3.Error):
            return {"total_rejected": 0, "rejection_rate": 0.0,
                    "by_reason": {}, "by_stream": {}}

    def return_features(self) -> List[Dict[str, Any]]:
        """Latest return feature per symbol (P1-04 dashboard section + API)."""
        try:
            return self.store.latest_return_features()
        except (OSError, sqlite3.Error):
            return []

    def discovery(self) -> Optional[Dict[str, Any]]:
        """Latest compact discovery snapshot (P1-05), or None before scans."""
        try:
            return self.store.latest_discovery()
        except (OSError, sqlite3.Error):
            return None

    def universe_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Recent promotion/demotion history (P1-05)."""
        try:
            return self.store.universe_events(limit=limit)
        except (OSError, sqlite3.Error):
            return []

    def ranks(self) -> Dict[str, Dict[str, Any]]:
        """Latest rank vectors per metric (P1-05), or {} before evaluation."""
        try:
            return self.store.latest_ranks()
        except (OSError, sqlite3.Error):
            return {}

    def flow_features(self) -> List[Dict[str, Any]]:
        """Latest flow feature per symbol (P1-06), or [] before summaries."""
        try:
            return self.store.latest_flow_features()
        except (OSError, sqlite3.Error):
            return []

    def book_features(self) -> List[Dict[str, Any]]:
        """Latest book record per symbol (P1-07), or [] before depth."""
        try:
            return self.store.latest_book_features()
        except (OSError, sqlite3.Error):
            return []

    def oi_features(self) -> List[Dict[str, Any]]:
        """Latest OI record per symbol (P1-07), or [] before polls."""
        try:
            return self.store.latest_oi_features()
        except (OSError, sqlite3.Error):
            return []

    def structure_features(self) -> List[Dict[str, Any]]:
        """Latest structure record per symbol (P1-08), or [] before eval."""
        try:
            return self.store.latest_structure_features()
        except (OSError, sqlite3.Error):
            return []

    def history_coverage(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Historical research coverage (P1-11B separate DB), [] when absent."""
        try:
            from .history_store import HistoryStore
            rows = HistoryStore().coverage_summary()
        except (OSError, sqlite3.Error, ValueError):
            return []
        if symbol is None:
            return rows
        sym = str(symbol).upper()
        return [r for r in rows if r.get("symbol") == sym]

    def price_points(self, symbol: str, range_name: str):
        """Bounded mark-price chart points (P1-09, persisted price_samples)."""
        from .dashboard_data import price_history_points
        return price_history_points(self.store, symbol, range_name)

    def storage(self) -> Dict[str, Any]:
        try:
            return self.store.storage_info()
        except (OSError, sqlite3.Error):
            return {"db_path": str(self.store.db_path), "exists": False,
                    "size_bytes": 0, "rows": {}}

    def health(self) -> Dict[str, Any]:
        snap = self.snapshot()
        if snap is None and not self.storage().get("exists", False):
            return {"status": "unknown", "reasons": ["persistence unreachable (no database)"]}
        return compute_health(snap, self.rejection_stats())

    def server_uptime_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.server_started_monotonic)


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def stream_rows(dq: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per-stream health rows for the /system page."""
    messages = _safe_dict(dq.get("messagesByStream"))
    silence = _safe_dict(dq.get("maxObservedSilenceMsByStream"))
    stale = set(_safe_list(dq.get("staleStreams")))
    silent = set(_safe_list(dq.get("silentStreams")))
    runtime = max(float(dq.get("connectivityObservationSeconds")
                        or 1.0), 1.0)
    streams = sorted(set(messages) | set(silence))
    rows = []
    for stream in streams:
        count = int(messages.get(stream, 0))
        rows.append({
            "stream": stream,
            "messages": count,
            "rate_per_s": round(count / runtime, 3),
            "max_silence_ms": silence.get(stream),
            "stale": stream in stale,
            "silent": stream in silent,
        })
    return rows


def latency_rows(latency: Dict[str, Any], metric: str) -> List[Dict[str, Any]]:
    """p50/p95 rows for one latency metric across stream/symbol keys."""
    dists = _safe_dict(latency.get(metric))
    rows = []
    for key in sorted(dists):
        snap = dists[key]
        if not isinstance(snap, dict) or "p50" not in snap:
            continue
        rows.append({"key": key, "count": snap.get("count"),
                     "p50": snap.get("p50"), "p95": snap.get("p95"),
                     "max": snap.get("max")})
    return rows


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------

CSS = """
body{background:#0d1117;color:#c9d1d9;font-family:Consolas,monospace;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 12px}h2{font-size:14px;margin:20px 0 8px;color:#8b949e}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{border:1px solid #30363d;padding:4px 8px;text-align:left}
th{background:#161b22;color:#8b949e}
.banner{background:#161b22;border:1px solid #30363d;padding:8px 12px;margin-bottom:12px;font-size:13px}
.chip{display:inline-block;padding:2px 10px;border-radius:10px;font-weight:bold;font-size:12px}
.ok{background:#1a7f37;color:#fff}.degraded{background:#9e6a03;color:#fff}
.stale{background:#da3633;color:#fff}.unknown{background:#6e7681;color:#fff}
nav{margin-bottom:12px;font-size:13px}nav a{color:#58a6ff;margin-right:12px}
.warn{color:#e3b341}.note{color:#8b949e;font-size:11px}
.pos{color:#3fb950}.neg{color:#f85149}
.bar{letter-spacing:1px;white-space:nowrap}
"""

BANNER_NOTE = ("Observe-only market-intelligence dashboard. "
               "Detector counts below are telemetry, NOT trade signals. "
               "No execution controls exist on this page.")


def _page(title: str, banner_html: str, body: str) -> str:
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<meta http-equiv='refresh' content='10'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
            f"<body><nav><a href='/overview'>/overview</a>"
            f"<a href='/system'>/system</a><a href='/api/health'>/api/health</a>"
            f"<a href='/api/snapshot'>/api/snapshot</a>"
            f"<a href='/api/features/returns'>/api/features/returns</a>"
            f"<a href='/api/features/momentum'>/api/features/momentum</a>"
            f"<a href='/api/features/flow'>/api/features/flow</a>"
            f"<a href='/api/features/volume'>/api/features/volume</a>"
            f"<a href='/api/features/book'>/api/features/book</a>"
            f"<a href='/api/features/open-interest'>/api/features/open-interest</a>"
            f"<a href='/api/features/vwap'>/api/features/vwap</a>"
            f"<a href='/api/features/volatility'>/api/features/volatility</a>"
            f"<a href='/api/features/structure'>/api/features/structure</a>"
            f"<a href='/api/discovery'>/api/discovery</a></nav>"
            f"<h1>{html.escape(title)}</h1>{banner_html}{body}"
            f"<p class='note'>{html.escape(BANNER_NOTE)} Auto-refresh 10s.</p>"
            f"</body></html>")


def _banner(safety: Dict[str, Any], status: str) -> str:
    label = STATUS_LABELS.get(status, status.upper())
    return (f"<div class='banner'>BOT_MODE=<b>{html.escape(str(safety.get('BOT_MODE', '?')))}</b> "
            f"keys={safety.get('apiKeysUsed', '?')} orders={safety.get('realOrdersSent', '?')} "
            f"capital={safety.get('realCapitalAtRisk', '?')} "
            f"<span class='chip {html.escape(status)}'>{html.escape(label)}</span></div>")


def _kv_table(rows: List[Tuple[str, Any]]) -> str:
    body = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
                   for k, v in rows)
    return f"<table>{body}</table>"


def _format_return(value: Any) -> str:
    """Log-return fraction -> '+0.123%' or an insufficient-history marker."""
    if value is None:
        return "<span title='insufficient history'>—</span>"
    try:
        return f"{float(value) * 100:+.3f}%"
    except (TypeError, ValueError):
        return "<span title='insufficient history'>—</span>"


def _format_age_ms(age_ms: Any) -> str:
    if age_ms is None:
        return "—"
    try:
        return f"{float(age_ms) / 1000:.0f}s ago"
    except (TypeError, ValueError):
        return "—"


def render_returns_section(features: List[Dict[str, Any]]) -> str:
    """Read-only Symbol Returns table (P1-04). No ranking, no states."""
    body = "<h2>Symbol Returns (mark-price log returns, read-only)</h2>"
    if not features:
        return body + "<p class='note'>No return features persisted yet — " \
            "insufficient history (engine warming up or probe not running).</p>"
    body += "<table><tr><th>symbol</th><th>price</th><th>1m</th><th>3m</th>" \
            "<th>5m</th><th>15m</th><th>1h</th><th>4h</th><th>24h</th>" \
            "<th>freshness</th><th>warmup</th></tr>"
    for feat in features:
        if not isinstance(feat, dict):
            continue
        returns = feat.get("returns") if isinstance(feat.get("returns"), dict) else {}
        available = feat.get("available_tfs") if isinstance(
            feat.get("available_tfs"), list) else []
        try:
            price = f"{float(feat.get('current_price')):.4f}" \
                if feat.get("current_price") is not None else "—"
        except (TypeError, ValueError):
            price = "—"
        cells = "".join(f"<td>{_format_return(returns.get(tf))}</td>"
                        for tf in ("1m", "3m", "5m", "15m", "1h", "4h", "24h"))
        body += (f"<tr><td>{html.escape(str(feat.get('symbol', '?')))}</td>"
                 f"<td>{price}</td>{cells}"
                 f"<td>{_format_age_ms(feat.get('sample_age_ms'))}</td>"
                 f"<td>{len(available)}/7"
                 f"{' READY' if feat.get('warmup_complete') else ' WARMING'}</td></tr>")
    return body + "</table>"


def _format_scientific(value: Any, suffix: str = "/s") -> str:
    if value is None:
        return "<span title='insufficient history'>—</span>"
    try:
        return f"{float(value):.3g}{suffix}"
    except (TypeError, ValueError):
        return "<span title='insufficient history'>—</span>"


def _format_usdt(value: Any) -> str:
    """Signed quote-notional cell, or an insufficient-data marker."""
    if value is None:
        return "<span title='no data'>—</span>"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "<span title='no data'>—</span>"
    cls = "pos" if number > 0 else ("neg" if number < 0 else "")
    text = f"{number:+.2f}"
    return f"<span class='{cls}'>{html.escape(text)}</span>" if cls else html.escape(text)


def _format_ratio(value: Any) -> str:
    """Signed delta-ratio cell in [-1, +1], or an insufficient-data marker."""
    if value is None:
        return "<span title='no directional volume yet'>—</span>"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "<span title='no directional volume yet'>—</span>"
    cls = "pos" if number > 0 else ("neg" if number < 0 else "")
    text = f"{number:+.3f}"
    return f"<span class='{cls}'>{html.escape(text)}</span>" if cls else html.escape(text)


def _format_z(value: Any) -> str:
    """Volume z-score cell, or an insufficient-baseline marker (never fake 0)."""
    if value is None:
        return "<span title='baseline warming up or zero variance'>—</span>"
    try:
        return f"{float(value):+.2f}"
    except (TypeError, ValueError):
        return "<span title='baseline warming up or zero variance'>—</span>"


def _flow_bar(buy_pct: Any, sell_pct: Any) -> str:
    """Compact aggressive split bar (text blocks, no frontend framework)."""
    try:
        buy = float(buy_pct) if buy_pct is not None else None
        sell = float(sell_pct) if sell_pct is not None else None
    except (TypeError, ValueError):
        buy = sell = None
    if buy is None or sell is None:
        return "<span title='no directional volume yet'>—</span>"
    buy_blocks = "█" * max(int(round(buy / 5.0)), 1) if buy > 0 else ""
    sell_blocks = "█" * max(int(round(sell / 5.0)), 1) if sell > 0 else ""
    return (f"<span class='bar'><span class='pos'>BUY {buy_blocks} {buy:.0f}%</span>"
            f"<br><span class='neg'>SELL {sell_blocks} {sell:.0f}%</span></span>")


def render_flow_section(flow_features: List[Dict[str, Any]],
                        return_features: List[Dict[str, Any]]) -> str:
    """P1-06 live trade-flow table (subscribed symbols only).

    Read-only market description: aggressive buy/sell split, signed delta,
    delta ratio, trade rate, volume z-score, freshness, warmup. Nothing here
    is a signal, entry, or classifier output.
    """
    body = "<h2>Live trade flow (subscribed symbols only — read-only, NOT signals)</h2>"
    body += ("<p class='note'>Aggressor: buyer-is-maker=true → aggressive SELL; "
             "false → aggressive BUY. Totals use q (includes RPI fills). "
             "Delta = buy − sell notional. Unsubscribed symbols never appear here.</p>")
    live = [f for f in flow_features
            if isinstance(f, dict) and f.get("subscribed")]
    if not live:
        return body + "<p class='note'>No live flow yet — insufficient history " \
            "(engine warming up or probe not running).</p>"
    prices = {f.get("symbol"): f.get("current_price") for f in return_features
              if isinstance(f, dict)}
    body += "<table><tr><th>symbol</th><th>price</th>" \
            "<th>1m notional</th><th>aggr. split</th>" \
            "<th>signed Δ</th><th>Δ ratio</th>" \
            "<th>trade rate</th><th>vol z (1m)</th>" \
            "<th>freshness</th><th>warmup</th></tr>"
    for feat in sorted(live, key=lambda f: str(f.get("symbol", ""))):
        horizons = feat.get("horizons") if isinstance(
            feat.get("horizons"), dict) else {}
        hour1 = horizons.get("1m") if isinstance(
            horizons.get("1m"), dict) else {}
        baselines = feat.get("baselines") if isinstance(
            feat.get("baselines"), dict) else {}
        base1m = baselines.get("1m") if isinstance(
            baselines.get("1m"), dict) else {}
        try:
            price = f"{float(prices.get(feat.get('symbol'))):.4f}" \
                if prices.get(feat.get("symbol")) is not None else "—"
        except (TypeError, ValueError):
            price = "—"
        try:
            notional = f"{float(hour1.get('notional')):.2f}" \
                if hour1.get("notional") is not None else "—"
        except (TypeError, ValueError):
            notional = "—"
        complete = sum(1 for h in ("10s", "30s", "1m", "3m", "5m", "15m")
                       if isinstance(horizons.get(h), dict)
                       and horizons[h].get("warmup_complete"))
        body += (f"<tr><td>{html.escape(str(feat.get('symbol', '?')))}</td>"
                 f"<td>{price}</td>"
                 f"<td>{notional}</td>"
                 f"<td>{_flow_bar(hour1.get('buy_pct'), hour1.get('sell_pct'))}</td>"
                 f"<td>{_format_usdt(hour1.get('signed_delta'))}</td>"
                 f"<td>{_format_ratio(hour1.get('delta_ratio'))}</td>"
                 f"<td>{_format_scientific(hour1.get('trade_rate'))}</td>"
                 f"<td>{_format_z(base1m.get('z_score'))}</td>"
                 f"<td>{_format_age_ms(feat.get('freshness_ms'))}</td>"
                 f"<td>{complete}/6"
                 f"{' READY' if complete == 6 else ' WARMING'}</td></tr>")
    return body + "</table>"


def _format_book_num(value: Any, decimals: int = 2) -> str:
    """Book notional/price cell, or an insufficient-data marker."""
    if value is None:
        return "<span title='no book data yet'>—</span>"
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return "<span title='no book data yet'>—</span>"


def _format_integrity(degraded: Any, gaps: Any) -> str:
    """Sequence-integrity cell: OK vs DEGRADED with gap count."""
    try:
        gap_count = int(gaps or 0)
    except (TypeError, ValueError):
        gap_count = 0
    if degraded:
        return f"<span class='neg'>DEGRADED ({gap_count} gaps)</span>"
    return f"<span class='pos'>OK ({gap_count} gaps)</span>"


def render_book_section(book_features: List[Dict[str, Any]]) -> str:
    """P1-07 live order-book table (subscribed symbols only).

    Read-only liquidity description: spread, visible depth, imbalance,
    microprice displacement, slope, concentration, integrity. Nothing here
    is a signal, entry, or classifier output.
    """
    body = "<h2>Live order book (subscribed symbols only — read-only, NOT signals)</h2>"
    body += ("<p class='note'>Full top-20 snapshots @100ms. Imbalance = "
             "(bid − ask)/(bid + ask) notionals. Microprice from top-of-book. "
             "DEGRADED = sequence gap seen since last chained update.</p>")
    live = [f for f in book_features
            if isinstance(f, dict) and f.get("subscribed")]
    if not live:
        return body + "<p class='note'>No live book yet — no depth snapshots " \
            "processed (probe not running or feed silent).</p>"
    body += "<table><tr><th>symbol</th><th>bid/ask</th><th>spread bps</th>" \
            "<th>bid depth</th><th>ask depth</th><th>imbalance</th>" \
            "<th>micro Δ bps</th><th>slope asym</th><th>conc 10bps</th>" \
            "<th>integrity</th><th>freshness</th></tr>"
    for feat in sorted(live, key=lambda f: str(f.get("symbol", ""))):
        book = feat.get("book") if isinstance(feat.get("book"), dict) else {}
        depth = book.get("depth") if isinstance(book.get("depth"), dict) else {}
        top20 = depth.get("top20") if isinstance(depth.get("top20"), dict) else {}
        slopes = book.get("slopes") if isinstance(book.get("slopes"), dict) else {}
        conc = book.get("concentration") if isinstance(
            book.get("concentration"), dict) else {}
        conc_bid = conc.get("bid") if isinstance(conc.get("bid"), dict) else {}
        conc_ask = conc.get("ask") if isinstance(conc.get("ask"), dict) else {}
        pair = (f"{_format_book_num(book.get('best_bid'), 2)} / "
                f"{_format_book_num(book.get('best_ask'), 2)}"
                if book.get("best_bid") is not None
                and book.get("best_ask") is not None else "—")
        c10 = conc_bid.get("within_10bps")
        if c10 is None:
            c10 = conc_ask.get("within_10bps")
        try:
            c10_cell = f"{float(c10) * 100:.0f}%" if c10 is not None else "—"
        except (TypeError, ValueError):
            c10_cell = "—"
        body += (f"<tr><td>{html.escape(str(feat.get('symbol', '?')))}</td>"
                 f"<td>{pair}</td>"
                 f"<td>{_format_book_num(book.get('spread_bps'))}</td>"
                 f"<td>{_format_book_num(top20.get('bid_notional'), 0)}</td>"
                 f"<td>{_format_book_num(top20.get('ask_notional'), 0)}</td>"
                 f"<td>{_format_ratio(book.get('imbalance_notional'))}</td>"
                 f"<td>{_format_ratio(book.get('microprice_displacement_bps'))}</td>"
                 f"<td>{_format_ratio(slopes.get('asymmetry'))}</td>"
                 f"<td>{c10_cell}</td>"
                 f"<td>{_format_integrity(feat.get('degraded'), feat.get('sequence_gaps'))}</td>"
                 f"<td>{_format_age_ms(feat.get('freshness_ms'))}</td></tr>")
    return body + "</table>"


def render_oi_section(oi_features: List[Dict[str, Any]]) -> str:
    """P1-07 live open-interest table (subscribed symbols only).

    Read-only positioning description: current OI, horizon deltas, rate,
    acceleration, descriptive price/OI context, freshness. Context labels
    are regime descriptions, never trade signals.
    """
    body = "<h2>Live open interest (subscribed symbols only — read-only, NOT signals)</h2>"
    body += ("<p class='note'>Public REST polls (60s cadence). "
             "Deltas vs actual-timestamp anchors; UNKNOWN until history warms. "
             "Context labels describe joint price/OI direction only.</p>")
    live = [f for f in oi_features
            if isinstance(f, dict) and f.get("subscribed")]
    if not live:
        return body + "<p class='note'>No live OI yet — no poll samples " \
            "stored (probe not running or polls failing).</p>"
    body += "<table><tr><th>symbol</th><th>OI (base)</th>" \
            "<th>Δ 1m</th><th>Δ 5m</th><th>accel</th>" \
            "<th>context 1m</th><th>freshness</th></tr>"
    for feat in sorted(live, key=lambda f: str(f.get("symbol", ""))):
        horizons = feat.get("horizons") if isinstance(
            feat.get("horizons"), dict) else {}
        contexts = feat.get("price_oi_context") if isinstance(
            feat.get("price_oi_context"), dict) else {}
        h1 = horizons.get("1m") if isinstance(horizons.get("1m"), dict) else {}
        h5 = horizons.get("5m") if isinstance(horizons.get("5m"), dict) else {}
        stale = " STALE" if feat.get("stale") else ""
        body += (f"<tr><td>{html.escape(str(feat.get('symbol', '?')))}</td>"
                 f"<td>{_format_book_num(feat.get('current_oi'), 3)}</td>"
                 f"<td>{_format_usdt(h1.get('delta'))}</td>"
                 f"<td>{_format_usdt(h5.get('delta'))}</td>"
                 f"<td>{_format_scientific(feat.get('acceleration_per_s2'), '/s²')}</td>"
                 f"<td>{html.escape(str(contexts.get('1m', 'UNKNOWN')))}</td>"
                 f"<td>{_format_age_ms(feat.get('freshness_ms'))}{stale}</td></tr>")
    return body + "</table>"


def _format_bps(value: Any) -> str:
    """Signed displacement cell in bps, or an insufficient-data marker."""
    if value is None:
        return "<span title='no data'>—</span>"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "<span title='no data'>—</span>"
    cls = "pos" if number > 0 else ("neg" if number < 0 else "")
    text = f"{number:+.1f}"
    return f"<span class='{cls}'>{html.escape(text)}</span>" if cls else html.escape(text)


def _format_vol(value: Any) -> str:
    """Realized-vol cell (raw horizon fraction), or a warmup marker."""
    if value is None:
        return "<span title='insufficient history'>—</span>"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "<span title='insufficient history'>—</span>"


def render_structure_section(structure_features: List[Dict[str, Any]]
                             ) -> str:
    """P1-08 compact VWAP/volatility/structure table (subscribed only).

    Read-only description: 1m VWAP + displacement, realized vol, range
    position/expansion, swing relations, prior-range state. Nothing here
    is a signal, entry, or classifier output.
    """
    body = "<h2>VWAP / volatility / structure (subscribed only — read-only, NOT signals)</h2>"
    body += ("<p class='note'>VWAP from trade flow (mark reference). "
             "Vol = raw horizon sqrt-sum-squared log returns. "
             "States are descriptive range tags only.</p>")
    live = [f for f in structure_features
            if isinstance(f, dict) and f.get("subscribed")]
    if not live:
        return body + "<p class='note'>No structure features yet — peer " \
            "engines warming up or probe not running.</p>"
    body += "<table><tr><th>symbol</th><th>1m VWAP</th><th>displ bps</th>" \
            "<th>rv 1m</th><th>rv 5m</th><th>range pos</th><th>expand ×</th>" \
            "<th>swings HH/HL</th><th>prior range</th><th>freshness</th></tr>"
    for feat in sorted(live, key=lambda f: str(f.get("symbol", ""))):
        vwap = feat.get("vwap") if isinstance(feat.get("vwap"), dict) else {}
        vol = feat.get("volatility") if isinstance(
            feat.get("volatility"), dict) else {}
        ranges = feat.get("ranges") if isinstance(
            feat.get("ranges"), dict) else {}
        structure = feat.get("structure") if isinstance(
            feat.get("structure"), dict) else {}
        v1 = vwap.get("1m") if isinstance(vwap.get("1m"), dict) else {}
        rv1 = vol.get("1m") if isinstance(vol.get("1m"), dict) else {}
        rv5 = vol.get("5m") if isinstance(vol.get("5m"), dict) else {}
        r5 = ranges.get("5m") if isinstance(ranges.get("5m"), dict) else {}
        swing_rel = ("HH" if structure.get("higher_high")
                     else ("LH" if structure.get("lower_high") else "—"))
        swing_rel += (" / HL" if structure.get("higher_low")
                      else (" / LL" if structure.get("lower_low") else " / —"))
        try:
            vwap_cell = f"{float(v1.get('vwap')):.4f}" \
                if v1.get("vwap") is not None else "—"
        except (TypeError, ValueError):
            vwap_cell = "—"
        try:
            expand = r5.get("expansion_ratio")
            expand_cell = f"{float(expand):.2f}×" if expand is not None else "—"
        except (TypeError, ValueError):
            expand_cell = "—"
        try:
            pos = r5.get("range_position")
            pos_cell = f"{float(pos):.2f}" if pos is not None else "—"
        except (TypeError, ValueError):
            pos_cell = "—"
        body += (f"<tr><td>{html.escape(str(feat.get('symbol', '?')))}</td>"
                 f"<td>{vwap_cell}</td>"
                 f"<td>{_format_bps(v1.get('displacement_bps'))}</td>"
                 f"<td>{_format_vol(rv1.get('realized_vol'))}</td>"
                 f"<td>{_format_vol(rv5.get('realized_vol'))}</td>"
                 f"<td>{pos_cell}</td>"
                 f"<td>{expand_cell}</td>"
                 f"<td>{html.escape(swing_rel)}</td>"
                 f"<td>{html.escape(str(structure.get('breakout_state', 'UNKNOWN')))}</td>"
                 f"<td>{_format_age_ms(feat.get('price_age_ms'))}</td></tr>")
    return body + "</table>"


def render_intel_sections(state: DashboardState) -> str:
    """P1-05 market-intelligence area: tiers, live momentum, discovery movers.

    Read-only. Discovery metrics and live-feature metrics are visually
    separated; nothing here is a signal, entry, or classifier output.
    """
    body = "<h2>Market intelligence (read-only, NOT signals)</h2>"
    features = state.return_features()
    discovery = state.discovery()
    live_by_symbol = {f.get("symbol"): f for f in features
                      if isinstance(f, dict)}
    core = (discovery or {}).get("core") or sorted(live_by_symbol)
    hot = (discovery or {}).get("hot_dynamic") or []
    body += "<h2>Universe tiers</h2>" + _kv_table([
        ("CORE benchmarks", ", ".join(core) or "—"),
        ("HOT dynamic", ", ".join(hot) or "none selected"),
        ("DISCOVERY",
         f"{(discovery or {}).get('eligible_count', '?')} eligible of "
         f"{(discovery or {}).get('seen_count', '?')} seen "
         f"(scan: {_format_age_ms(time.time() * 1000 - ((discovery or {}).get('generated_at_ms') or 0)) if discovery else 'never'})"),
    ])
    body += "<h2>Live momentum (subscribed symbols only)</h2>"
    if not features:
        body += "<p class='note'>No live features yet — insufficient history.</p>"
    else:
        body += "<table><tr><th>symbol</th><th>tier</th><th>price</th>" \
                "<th>1m</th><th>3m</th><th>5m</th><th>15m</th>" \
                "<th>velocity 1m</th><th>accel 1m</th>" \
                "<th>rank (vel 1m)</th><th>rank Δ</th>" \
                "<th>freshness</th><th>warmup</th></tr>"
        for feat in features:
            if not isinstance(feat, dict):
                continue
            returns = feat.get("returns") if isinstance(
                feat.get("returns"), dict) else {}
            momentum = feat.get("momentum") if isinstance(
                feat.get("momentum"), dict) else {}
            velocity = momentum.get("velocity") if isinstance(
                momentum.get("velocity"), dict) else {}
            accel = momentum.get("acceleration") if isinstance(
                momentum.get("acceleration"), dict) else {}
            ranks = feat.get("ranks") if isinstance(
                feat.get("ranks"), dict) else {}
            rank_vel = ranks.get("velocity_1m") if isinstance(
                ranks.get("velocity_1m"), dict) else {}
            try:
                price = f"{float(feat.get('current_price')):.4f}" \
                    if feat.get("current_price") is not None else "—"
            except (TypeError, ValueError):
                price = "—"
            available = feat.get("available_tfs") if isinstance(
                feat.get("available_tfs"), list) else []
            rank_n = rank_vel.get("rank")
            rank_d = rank_vel.get("change")
            rank_cell = (f"{rank_n} ({rank_d:+d})" if isinstance(rank_n, int)
                         and isinstance(rank_d, int)
                         else (str(rank_n) if rank_n is not None else "—"))
            cells = "".join(f"<td>{_format_return(returns.get(tf))}</td>"
                            for tf in ("1m", "3m", "5m", "15m"))
            body += (f"<tr><td>{html.escape(str(feat.get('symbol', '?')))}</td>"
                     f"<td>{html.escape(str(feat.get('tier', '?')))}</td>"
                     f"<td>{price}</td>{cells}"
                     f"<td>{_format_scientific(velocity.get('1m'))}</td>"
                     f"<td>{_format_scientific(accel.get('1m'))}</td>"
                     f"<td>{html.escape(rank_cell)}</td>"
                     f"<td>{_format_age_ms(feat.get('sample_age_ms'))}</td>"
                     f"<td>{len(available)}/7"
                     f"{' READY' if feat.get('warmup_complete') else ' WARMING'}</td></tr>")
        body += "</table>"
    flow = state.flow_features()
    body += render_flow_section(flow, features)
    books = state.book_features()
    body += render_book_section(books)
    body += render_oi_section(state.oi_features())
    body += render_structure_section(state.structure_features())
    body += "<h2>Discovery movers (24h REST metrics — discovery only, NOT live)</h2>"
    tops = (discovery or {}).get("tops") or {}
    live_symbols = {f.get("symbol") for f in list(flow) + list(books)
                    if isinstance(f, dict) and f.get("subscribed")}
    hot_set = set(hot or [])
    core_set = set(core or [])
    if not tops:
        body += "<p class='note'>No discovery scan yet.</p>"
    else:
        for title, rows in (("Top gainers 24h", tops.get("gainers", [])),
                            ("Top losers 24h", tops.get("losers", [])),
                            ("Most active 24h (quote volume)", tops.get("most_active", []))):
            body += f"<h2>{html.escape(title)}</h2>"
            if not rows:
                body += "<p class='note'>none</p>"
                continue
            body += "<table><tr><th>symbol</th><th>tier</th><th>24h %</th><th>price</th>" \
                    "<th>quote vol 24h</th><th>eligibility</th><th>live feed</th></tr>"
            for row in rows:
                chg = row.get("change_24h_pct")
                chg_cell = (f"{float(chg):+.2f}%" if chg is not None else "—")
                symbol = str(row.get("symbol", "?"))
                tier = ("CORE" if symbol in core_set
                        else "HOT" if symbol in hot_set else "DISCOVERY")
                live_cell = ("LIVE (subscribed)" if symbol in live_symbols
                             else "DISCOVERY ONLY — NO LIVE FLOW/BOOK")
                body += (f"<tr><td>{html.escape(symbol)}</td>"
                         f"<td>{tier}</td>"
                         f"<td>{chg_cell}</td>"
                         f"<td>{html.escape(str(row.get('price', '—')))}</td>"
                         f"<td>{html.escape(str(row.get('quote_volume_24h', '—')))}</td>"
                         f"<td>eligible</td>"
                         f"<td>{live_cell}</td></tr>")
            body += "</table>"
    events = state.universe_events(limit=10)
    if events:
        body += "<h2>Universe events (promotion/demotion history)</h2><table>" \
                "<tr><th>time UTC</th><th>kind</th><th>symbol</th><th>detail</th></tr>"
        for event in events:
            body += (f"<tr><td>{html.escape(time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(event.get('timestamp', 0))))}</td>"
                     f"<td>{html.escape(str(event.get('kind', '?')))}</td>"
                     f"<td>{html.escape(str(event.get('symbol', '?')))}</td>"
                     f"<td>{html.escape(str(event.get('detail', '')))}</td></tr>")
        body += "</table>"
    return body


def render_overview(state: DashboardState) -> str:
    snap = state.snapshot()
    health = state.health()
    status = health["status"]
    if snap is None:
        return _page("Overview — Binance Futures",
                     _banner({}, status),
                     "<p class='warn'>No telemetry snapshot persisted yet. "
                     "Run the probe to generate persistence state.</p>"
                     f"<p class='note'>Reasons: {html.escape('; '.join(health['reasons']))}</p>")
    safety = _safe_dict(snap.get("safety"))
    dq = _safe_dict(snap.get("dataQuality"))
    rj = state.rejection_stats()
    storage = state.storage()
    messages = _safe_dict(dq.get("messagesByStream"))
    total_messages = sum(int(v) for v in messages.values())
    runtime = float(snap.get("runtimeSeconds") or 0.0)
    gaps = _safe_dict(dq.get("depthSequenceGapsBySymbol"))
    recon = _safe_dict(dq.get("reconnections"))
    snap_ts = snap.get("snapshotTimestamp")
    attempts = _safe_dict(dq.get("connectionAttempts"))
    successes = _safe_dict(dq.get("connectionSuccesses"))
    uptime = _safe_dict(dq.get("observedUptimePercentByEndpoint"))
    rows = storage.get("rows") if isinstance(storage.get("rows"), dict) else {}

    def _conn_table() -> str:
        endpoints = sorted(set(attempts) | set(successes) | set(recon) | set(uptime))
        if not endpoints:
            return "<p class='note'>no connection data</p>"
        out = "<table><tr><th>endpoint</th><th>attempts</th><th>successes</th>" \
              "<th>reconnects</th><th>uptime %</th></tr>"
        for endpoint in endpoints:
            out += (f"<tr><td>{html.escape(endpoint)}</td>"
                    f"<td>{attempts.get(endpoint, '?')}</td>"
                    f"<td>{successes.get(endpoint, '?')}</td>"
                    f"<td>{_safe_dict(dq.get('reconnections')).get(endpoint, '?')}</td>"
                    f"<td>{uptime.get(endpoint, '?')}</td></tr>")
        return out + "</table>"

    body = "<h2>Dashboard server health</h2>"
    body += _kv_table([
        ("server", f"UP (v{DASHBOARD_VERSION}, "
         f"{state.server_uptime_seconds():.0f}s uptime)"),
        ("persistence reachable", storage.get("exists", "?")),
        ("database", f"{storage.get('db_path', '?')} "
         f"({storage.get('size_bytes', '?')} bytes)"),
        ("stored rows", json.dumps(rows)),
        ("snapshot age",
         f"{time.time() - snap_ts:.0f}s" if snap_ts else "unknown"),
    ])
    body += "<h2>Market feed health</h2>"
    body += _conn_table()
    body += _kv_table([
        ("streams active/expected",
         f"{dq.get('activeStreams', '?')}/{dq.get('expectedStreams', '?')}"),
        ("missing streams (event-driven excluded)",
         ", ".join(_safe_list(dq.get("missingStreams"))) or "none"),
        ("stale streams", ", ".join(_safe_list(dq.get("staleStreams"))) or "none"),
        ("silent streams (event-driven silence is normal)",
         ", ".join(_safe_list(dq.get("silentStreams"))) or "none"),
        ("total messages", f"{total_messages} ({total_messages / max(runtime, 1):.1f}/s)"),
        ("depth sequence gaps", json.dumps(gaps)),
        ("timestamp rejected (this run)",
         f"{dq.get('timestampRejected', '?')}"),
        ("retained rejected rows / rate (persistence)",
         f"{rj.get('total_rejected', '?')} / "
         f"{float(rj.get('rejection_rate', 0.0)):.1%}"),
        ("probe runtime", f"{runtime:.1f}s"),
        ("feed status", "DEGRADED — see reasons" if status == "degraded" else status.upper()),
    ])
    body += "<h2>Persistence health</h2>"
    discovery = state.discovery()
    body += _kv_table([
        ("telemetry snapshots retained", rows.get("telemetry_snapshots", "?")),
        ("return feature rows", rows.get("return_features", "?")),
        ("flow feature rows", rows.get("flow_features", "?")),
        ("flow buckets retained", rows.get("flow_buckets", "?")),
        ("book feature rows", rows.get("book_features", "?")),
        ("OI samples retained", rows.get("oi_samples", "?")),
        ("OI feature rows", rows.get("oi_features", "?")),
        ("structure feature rows", rows.get("structure_features", "?")),
        ("last discovery scan",
         time.strftime("%Y-%m-%d %H:%M:%S UTC",
                       time.gmtime((discovery or {}).get("generated_at_ms", 0) / 1000))
         if discovery else "never"),
        ("discovery eligible/filtered",
         f"{(discovery or {}).get('eligible_count', '?')}/"
         f"{(discovery or {}).get('filtered_count', '?')}" if discovery else "—"),
    ])
    body += render_returns_section(state.return_features())
    body += render_intel_sections(state)
    body += "<h2>Detector telemetry (NOT trade signals)</h2>"
    events = _safe_dict(snap.get("eventsByType"))
    if events:
        body += _kv_table([(k, v) for k, v in sorted(events.items())])
    else:
        body += "<p class='note'>No detector threshold crossings in this snapshot window.</p>"
    return _page("Overview — Binance Futures", _banner(safety, status), body)


def render_system(state: DashboardState) -> str:
    snap = state.snapshot()
    health = state.health()
    status = health["status"]
    storage = state.storage()
    if snap is None:
        return _page("System — Binance Futures",
                     _banner({}, status),
                     "<p class='warn'>No telemetry snapshot persisted yet.</p>")
    safety = _safe_dict(snap.get("safety"))
    dq = _safe_dict(snap.get("dataQuality"))
    latency = _safe_dict(snap.get("latency"))
    processing = _safe_dict(snap.get("processing"))
    clock = _safe_dict(snap.get("clock"))
    rj = state.rejection_stats()
    body = "<h2>Streams</h2><table><tr><th>stream</th><th>messages</th><th>msg/s</th>" \
           "<th>max silence ms</th><th>stale</th><th>silent</th></tr>"
    for row in stream_rows(dq):
        body += (f"<tr><td>{html.escape(row['stream'])}</td><td>{row['messages']}</td>"
                 f"<td>{row['rate_per_s']}</td><td>{row['max_silence_ms']}</td>"
                 f"<td>{'YES' if row['stale'] else 'no'}</td>"
                 f"<td>{'yes' if row['silent'] else 'no'}</td></tr>")
    body += "</table>"
    for metric in ("rawEventLagMs", "correctedEventLagMs"):
        rows = latency_rows(latency, metric)
        if rows:
            body += f"<h2>Latency {html.escape(metric)} (ms)</h2>" \
                    "<table><tr><th>key</th><th>n</th><th>p50</th><th>p95</th><th>max</th></tr>"
            for r in rows:
                body += (f"<tr><td>{html.escape(r['key'])}</td><td>{r['count']}</td>"
                         f"<td>{r['p50']}</td><td>{r['p95']}</td><td>{r['max']}</td></tr>")
            body += "</table>"
    prows = latency_rows(processing, "processingLatencyMs")
    if prows:
        body += "<h2>Processing latency (ms)</h2>" \
                "<table><tr><th>key</th><th>n</th><th>p50</th><th>p95</th><th>max</th></tr>"
        for r in prows:
            body += (f"<tr><td>{html.escape(r['key'])}</td><td>{r['count']}</td>"
                     f"<td>{r['p50']}</td><td>{r['p95']}</td><td>{r['max']}</td></tr>")
        body += "</table>"
    body += "<h2>Clock</h2>" + _kv_table([
        ("offset ms", clock.get("clockOffsetMs", "?")),
        ("RTT ms", clock.get("serverTimeRttMs", "?")),
        ("syncs ok/failed",
         f"{clock.get('clockSyncSuccessful', '?')}/{clock.get('clockSyncFailed', '?')}"),
    ])
    body += "<h2>Rejections / skew (run counter vs retained rows)</h2>" + _kv_table([
        ("timestamp rejected — this run (probe counter)", dq.get("timestampRejected", "?")),
        ("retained rejected rows (persistence)", rj.get("total_rejected", "?")),
        ("rejection rate (retained)", f"{float(rj.get('rejection_rate', 0.0)):.1%}"),
        ("by reason", json.dumps(rj.get("by_reason", {}))),
        ("by stream", json.dumps(rj.get("by_stream", {}))),
    ])
    body += "<h2>Persistence</h2>" + _kv_table([
        ("reachable", storage.get("exists", "?")),
        ("db path", storage.get("db_path", "?")),
        ("size bytes", storage.get("size_bytes", "?")),
        ("rows", json.dumps(storage.get("rows", {}))),
    ])
    body += "<h2>Safety</h2>" + _kv_table([
        ("BOT_MODE", safety.get("BOT_MODE", "?")),
        ("apiKeysUsed", safety.get("apiKeysUsed", "?")),
        ("realOrdersSent", safety.get("realOrdersSent", "?")),
        ("realCapitalAtRisk", safety.get("realCapitalAtRisk", "?")),
        ("authenticatedClientsPresent", safety.get("authenticatedClientsPresent", "?")),
        ("orderExecutionPathPresent", safety.get("orderExecutionPathPresent", "?")),
    ])
    return _page("System — Binance Futures", _banner(safety, status), body)


# --------------------------------------------------------------------------
# HTTP server
# --------------------------------------------------------------------------

class DashboardHandler(BaseHTTPRequestHandler):
    state: DashboardState
    server_version = f"BinanceDash/{DASHBOARD_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:  # keep logs quiet
        pass

    def _send(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: Dict[str, Any]) -> None:
        self._send(code, "application/json",
                   json.dumps(payload, sort_keys=True).encode("utf-8"))

    def _health_payload(self) -> Dict[str, Any]:
        snap = self.state.snapshot()
        health = self.state.health()
        dq = _safe_dict((snap or {}).get("dataQuality"))
        safety = _safe_dict((snap or {}).get("safety"))
        snap_ts = (snap or {}).get("snapshotTimestamp")
        return {
            "status": health["status"],
            "version": DASHBOARD_VERSION,
            "uptime_seconds": round(self.state.server_uptime_seconds(), 1),
            "server": {
                "status": "ok",
                "uptime_seconds": round(self.state.server_uptime_seconds(), 1),
                "version": DASHBOARD_VERSION,
            },
            "feed": {
                "status": health["status"],
                "snapshot_age_seconds": round(time.time() - snap_ts, 1) if snap_ts else None,
                "reasons": health["reasons"],
            },
            "host": HOST,
            "persistence_reachable": bool(self.state.storage().get("exists", False)),
            "latest_snapshot_timestamp": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(snap_ts))
                if snap_ts else None),
            "snapshot_age_seconds": round(time.time() - snap_ts, 1) if snap_ts else None,
            "stream_summary": {
                "expected": dq.get("expectedStreams"),
                "active": dq.get("activeStreams"),
                "stale": _safe_list(dq.get("staleStreams")),
                "missing": _safe_list(dq.get("missingStreams")),
            },
            "bot_mode": safety.get("BOT_MODE", "unknown"),
            "safety": {
                "apiKeysUsed": safety.get("apiKeysUsed", 0),
                "realOrdersSent": safety.get("realOrdersSent", 0),
                "realCapitalAtRisk": safety.get("realCapitalAtRisk", 0),
            },
            "reasons": health["reasons"],
        }

    def _send_csv(self, code: int, filename: str, text: str) -> None:
        raw = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition",
                         f"attachment; filename={filename}")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        from . import dashboard_views as views
        from .dashboard_data import (VALID_RANGES, movers_table,
                                     normalize_symbol, search_symbols)
        split = urllib.parse.urlsplit(self.path)
        path = split.path
        query = urllib.parse.parse_qs(split.query or "")
        if path == "/":
            body = b'<a href="/overview">/overview</a>'
            self.send_response(302)
            self.send_header("Location", "/overview")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/overview":
            self._send(200, "text/html; charset=utf-8",
                       views.render_overview(self.state).encode("utf-8"))
        elif path == "/movers":
            self._send(200, "text/html; charset=utf-8",
                       views.render_movers(self.state).encode("utf-8"))
        elif path == "/search":
            q = (query.get("q") or [""])[0]
            self._send(200, "text/html; charset=utf-8",
                       views.render_search(self.state, q).encode("utf-8"))
        elif path == "/system":
            self._send(200, "text/html; charset=utf-8",
                       views.render_system(self.state).encode("utf-8"))
        elif path.startswith("/symbol/"):
            raw = urllib.parse.unquote(path[len("/symbol/"):]).split("/")[0]
            if normalize_symbol(raw) is None:
                self._send(400, "text/html; charset=utf-8",
                           b"<h1>400 invalid symbol</h1>")
                return
            rng = (query.get("range") or ["1h"])[0]
            if rng not in VALID_RANGES:
                self._send(400, "text/html; charset=utf-8",
                           b"<h1>400 invalid range</h1>")
                return
            page = views.render_symbol(self.state, raw, rng)
            if page is None:
                self._send(404, "text/html; charset=utf-8",
                           b"<h1>404 unknown symbol</h1>")
            else:
                self._send(200, "text/html; charset=utf-8",
                           page.encode("utf-8"))
        elif path == "/api/search":
            q = (query.get("q") or [""])[0]
            results = search_symbols(q or "", movers_table(self.state))
            self._send_json(200, {"query": q or "", "results": results})
        elif path.startswith("/api/symbol/"):
            rest = path[len("/api/symbol/"):]
            parts = rest.split("/")
            if len(parts) == 2 and parts[1] in ("price", "price.csv"):
                raw_sym, leaf = parts
                if normalize_symbol(raw_sym) is None:
                    self._send_json(400, {"error": "invalid symbol"})
                    return
                rng = (query.get("range") or ["1h"])[0]
                if rng not in VALID_RANGES:
                    self._send_json(400, {
                        "error": f"invalid range; valid: {sorted(VALID_RANGES)}"})
                    return
                try:
                    points, meta = self.state.price_points(raw_sym, rng)
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                sym_norm = (meta.get("symbol") or raw_sym).upper()
                # Unknown symbol (no persisted rows anywhere) -> 404.
                from .dashboard_data import compose_universe
                uni = compose_universe(self.state)
                known = (set(uni["live_symbols"]) | set(uni["disc_rows"])
                         | set(uni["core"]) | set(uni["hot"]))
                if sym_norm not in known:
                    self._send_json(404, {"error": f"unknown symbol {sym_norm}"})
                    return
                if leaf == "price.csv":
                    lines = ["timestamp,price"]
                    lines += [f"{p['timestamp']},{p['price']}"
                              for p in points]
                    self._send_csv(200, f"{sym_norm}-{rng}.csv",
                                   "\n".join(lines) + "\n")
                else:
                    self._send_json(200, {
                        "symbol": sym_norm,
                        "source": meta.get("source", "markPrice"),
                        "range": rng,
                        "generated_at": meta.get("generated_at"),
                        "points": points,
                        "points_total": meta.get("points_total"),
                        "points_returned": meta.get("points_returned"),
                        "truncated": meta.get("truncated", False),
                        "point_limit": meta.get("point_limit"),
                    })
                return
            self._send_json(404, {"error": f"unknown route {path}"})
        elif path == "/api/health":
            self._send_json(200, self._health_payload())
        elif path == "/api/history/status":
            cov = self.state.history_coverage()
            if not cov:
                self._send_json(404, {"error": "no historical coverage yet"})
            else:
                self._send_json(200, {
                    "generated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "source": "historical research store (REST bootstrap)",
                    "series": cov,
                })
        elif path.startswith("/api/history/"):
            raw = urllib.parse.unquote(path[len("/api/history/"):]).split("/")[0]
            if normalize_symbol(raw) is None:
                self._send_json(400, {"error": "invalid symbol"})
                return
            cov = self.state.history_coverage(raw)
            if not cov:
                self._send_json(404, {"error": f"no historical coverage for {raw.upper()}"})
            else:
                self._send_json(200, {"symbol": raw.upper(), "series": cov})
        elif path == "/api/snapshot":
            snap = self.state.snapshot()
            if snap is None:
                self._send_json(404, {"error": "no snapshot persisted yet"})
            else:
                self._send_json(200, snap)
        elif path == "/api/features/returns":
            features = self.state.return_features()
            if not features:
                self._send_json(404, {"error": "no return features persisted yet"})
            else:
                self._send_json(200, {
                    "generated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "source": "markPrice",
                    "semantics": "log returns; unavailable horizons are null (never 0)",
                    "features": features,
                })
        elif path == "/api/features/momentum":
            features = self.state.return_features()
            if not features:
                self._send_json(404, {"error": "no momentum features persisted yet"})
            else:
                self._send_json(200, {
                    "generated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "source": "markPrice",
                    "velocity_semantics": "change in h-return over basis window, per second",
                    "acceleration_semantics": "timestamp-aware change in velocity, per second",
                    "ranks": self.state.ranks(),
                    "features": [
                        {"symbol": f.get("symbol"), "tier": f.get("tier"),
                         "current_price": f.get("current_price"),
                         "sample_age_ms": f.get("sample_age_ms"),
                         "warmup_complete": f.get("warmup_complete"),
                         "momentum": f.get("momentum"),
                         "ranks": f.get("ranks")}
                        for f in features if isinstance(f, dict)],
                })
        elif path == "/api/discovery":
            discovery = self.state.discovery()
            if discovery is None:
                self._send_json(404, {"error": "no discovery scan persisted yet"})
            else:
                self._send_json(200, {
                    "universe_architecture": "CORE pinned benchmarks + "
                                             "DISCOVERY scan + bounded HOT set",
                    "subscription_note": "only CORE symbols subscribed to "
                                         "websocket streams; HOT is proposed only",
                    "discovery": discovery,
                    "events": self.state.universe_events(limit=20),
                })
        elif path == "/api/features/flow":
            features = self.state.flow_features()
            if not features:
                self._send_json(404, {"error": "no flow features persisted yet"})
            else:
                self._send_json(200, {
                    "generated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "source": "aggTrade",
                    "aggressor_semantics": "buyer-is-maker=true -> aggressive "
                                           "SELL; false -> aggressive BUY "
                                           "(maker side is never the aggressor)",
                    "quantity_semantics": "q includes RPI fills; nq excludes "
                                          "RPI; totals use q",
                    "horizons": ["10s", "30s", "1m", "3m", "5m", "15m"],
                    "baselines": ["10s", "30s", "1m", "5m"],
                    "delta_semantics": "signed_delta = buy_notional - "
                                       "sell_notional; delta_ratio in [-1, +1], "
                                       "null when no directional volume",
                    "symbols": features,
                })
        elif path == "/api/features/volume":
            features = self.state.flow_features()
            if not features:
                self._send_json(404, {"error": "no volume features persisted yet"})
            else:
                self._send_json(200, {
                    "generated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "source": "aggTrade",
                    "semantics": "trailing completed-bucket quote notionals; "
                                 "z_score null when baseline insufficient or "
                                 "zero-variance (never fake 0)",
                    "symbols": [
                        {"symbol": f.get("symbol"),
                         "subscribed": f.get("subscribed"),
                         "as_of_ms": f.get("as_of_ms"),
                         "freshness_ms": f.get("freshness_ms"),
                         "trades_total": f.get("trades_total"),
                         "baselines": f.get("baselines"),
                         "acceleration": f.get("acceleration")}
                         for f in features if isinstance(f, dict)],
                })
        elif path == "/api/features/book":
            features = self.state.book_features()
            if not features:
                self._send_json(404, {"error": "no book features persisted yet"})
            else:
                self._send_json(200, {
                    "generated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "source": "depth20@100ms",
                    "semantics": "full top-20 snapshots; imbalance = "
                                 "(bid - ask)/(bid + ask); microprice from "
                                 "top-of-book; slope = LS-through-origin of "
                                 "cumulative notional vs distance-bps; "
                                 "concentration null when the book does not "
                                 "span the band",
                    "integrity_note": "degraded=true after a sequence gap "
                                      "until a chained update arrives",
                    "symbols": features,
                })
        elif path == "/api/features/open-interest":
            features = self.state.oi_features()
            if not features:
                self._send_json(404, {"error": "no open-interest features persisted yet"})
            else:
                self._send_json(200, {
                    "generated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "source": "GET /fapi/v1/openInterest",
                    "semantics": "public REST polls; deltas vs "
                                 "actual-timestamp anchors; null until "
                                 "history warms",
                    "context_note": "price_oi_context labels are descriptive "
                                    "regime tags only, never trade signals",
                    "symbols": features,
                })
        elif path == "/api/features/vwap":
            features = self.state.structure_features()
            if not features:
                self._send_json(404, {"error": "no vwap features persisted yet"})
            else:
                self._send_json(200, {
                    "generated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "source": "aggTrade via flow aggregates",
                    "semantics": "vwap = sum(price*qty)/sum(qty) per trailing "
                                 "window; markPrice reference; displacement "
                                 "is raw description, never bullish/bearish",
                    "horizons": ["1m", "3m", "5m", "15m"],
                    "symbols": [
                        {"symbol": f.get("symbol"),
                         "subscribed": f.get("subscribed"),
                         "as_of_ms": f.get("as_of_ms"),
                         "reference_price": f.get("reference_price"),
                         "reference_source": f.get("reference_source"),
                         "price_age_ms": f.get("price_age_ms"),
                         "vwap": f.get("vwap")}
                        for f in features if isinstance(f, dict)],
                })
        elif path == "/api/features/volatility":
            features = self.state.structure_features()
            if not features:
                self._send_json(404, {"error": "no volatility features persisted yet"})
            else:
                self._send_json(200, {
                    "generated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "source": "markPrice 10s buckets",
                    "semantics": "raw horizon sqrt-sum-squared log returns "
                                 "(not annualized); null until >=5 returns "
                                 "and full-span coverage",
                    "horizons": ["1m", "5m", "15m", "1h"],
                    "symbols": [
                        {"symbol": f.get("symbol"),
                         "subscribed": f.get("subscribed"),
                         "as_of_ms": f.get("as_of_ms"),
                         "price_age_ms": f.get("price_age_ms"),
                         "volatility": f.get("volatility"),
                         "ranges": f.get("ranges")}
                        for f in features if isinstance(f, dict)],
                })
        elif path == "/api/features/structure":
            features = self.state.structure_features()
            if not features:
                self._send_json(404, {"error": "no structure features persisted yet"})
            else:
                self._send_json(200, {
                    "generated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                    "source": "markPrice 10s buckets",
                    "semantics": "confirmed pivots (3-bucket each side, 30s "
                                 "explicit delay); breakout vs prior completed "
                                 "15m block; descriptive tags only, never "
                                 "trade signals",
                    "symbols": [
                        {"symbol": f.get("symbol"),
                         "subscribed": f.get("subscribed"),
                         "as_of_ms": f.get("as_of_ms"),
                         "price_age_ms": f.get("price_age_ms"),
                         "structure": f.get("structure")}
                        for f in features if isinstance(f, dict)],
                })
        else:
            self._send_json(404, {"error": f"unknown route {path}"})


class DashboardServer:
    """Threaded HTTP server bound to 127.0.0.1; start()/stop() lifecycle."""

    def __init__(self, host: str = HOST, port: int = 0,
                 db_path: Optional[Path] = None) -> None:
        self.host = host
        self.port = port
        self.store = PersistenceStore(
            db_path=Path(db_path) if db_path else default_db_path())
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.bound_port()}"

    def bound_port(self) -> int:
        if self._httpd is not None:
            return self._httpd.server_address[1]
        return self.port

    def start(self) -> "DashboardServer":
        handler = type("BoundHandler", (DashboardHandler,),
                       {"state": DashboardState(self.store)})
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        kwargs={"poll_interval": 0.2},
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=10)
        try:
            self.store.close()
        except Exception:
            pass
        self._httpd = None
        self._thread = None


# --------------------------------------------------------------------------
# Lifecycle CLI
# --------------------------------------------------------------------------

def http_get_json(url: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def http_status(url: str, timeout: float = 5.0) -> Optional[int]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except Exception:
        return None


def cmd_serve(args: argparse.Namespace) -> int:
    server = DashboardServer(host=HOST, port=args.port,
                             db_path=Path(args.db) if args.db else None)
    server.start()
    print(json.dumps({"serving": server.url, "db": str(server.store.db_path)}))
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


def _child_env() -> Dict[str, str]:
    env = dict(os.environ)
    src = str(repo_root() / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    env["BOT_MODE"] = "observe"
    return env


def cmd_start(args: argparse.Namespace) -> int:
    existing = read_pidfile()
    if existing is not None:
        pid = int(existing.get("pid", -1))
        if pid_is_ours(pid, existing.get("created")):
            health = http_get_json(f"http://{HOST}:{existing['port']}/api/health")
            print(json.dumps({"already_running": True, "url": existing.get("url"),
                              "pid": pid, "health": (health or {}).get("status")}))
            return 0
        remove_pidfile()  # stale PID file — discard, fresh start
    port = int(args.port) if args.port else find_free_port()
    if not is_port_free(port):
        port = find_free_port()
    db = str(Path(args.db)) if args.db else str(default_db_path())
    log_path = repo_root() / "logs" / "dashboard.out.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as logfh:
        proc = subprocess.Popen(
            [sys.executable, "-m", "microstructure_probe.dashboard",
             "serve", "--port", str(port), "--db", db],
            cwd=str(repo_root()), env=_child_env(),
            stdout=logfh, stderr=subprocess.STDOUT,
            creationflags=subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    url = f"http://{HOST}:{port}"
    write_pidfile(proc.pid, port, url)
    health = None
    deadline = time.time() + 25
    while time.time() < deadline:
        health = http_get_json(url + "/api/health")
        if health is not None:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    print(json.dumps({
        "started": True, "url": url, "host": HOST, "port": port,
        "pid": proc.pid, "health_endpoint": url + "/api/health",
        "health_status": (health or {}).get("status"),
        "start_command": "python -m microstructure_probe.dashboard start",
        "stop_command": "python -m microstructure_probe.dashboard stop",
        "restart_command": "python -m microstructure_probe.dashboard restart",
    }, indent=2))
    return 0 if health is not None else 1


def cmd_stop(_args: argparse.Namespace) -> int:
    existing = read_pidfile()
    if existing is None:
        print(json.dumps({"running": False, "detail": "no PID file"}))
        return 0
    pid = int(existing.get("pid", -1))
    if not pid_is_ours(pid, existing.get("created")):
        remove_pidfile()
        print(json.dumps({"running": False, "detail": "stale PID file discarded",
                          "pid": pid}))
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    deadline = time.time() + 10
    while time.time() < deadline:
        if not pid_is_ours(pid, existing.get("created")):
            break
        time.sleep(0.3)
    remove_pidfile()
    print(json.dumps({"stopped": True, "pid": pid}))
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    existing = read_pidfile()
    if existing is None:
        print(json.dumps({"running": False, "detail": "no PID file"}))
        return 1
    pid = int(existing.get("pid", -1))
    port = int(existing.get("port", 0))
    alive = pid_is_ours(pid, existing.get("created"))
    url = f"http://{HOST}:{port}"
    health = http_get_json(url + "/api/health") if alive else None
    overview = http_status(url + "/overview") if alive else None
    system = http_status(url + "/system") if alive else None
    print(json.dumps({
        "running": bool(alive), "pid": pid, "url": url,
        "health_status": (health or {}).get("status"),
        "overview_http": overview, "system_http": system,
        "health": health,
    }, indent=2))
    return 0 if alive and health is not None else 1


def cmd_restart(args: argparse.Namespace) -> int:
    cmd_stop(args)
    time.sleep(1)
    return cmd_start(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Binance Futures operator dashboard")
    sub = parser.add_subparsers(dest="command", required=True)
    p_serve = sub.add_parser("serve", help="run the HTTP server in the foreground")
    p_serve.add_argument("--port", type=int, required=True)
    p_serve.add_argument("--db", default=None)
    p_start = sub.add_parser("start", help="start detached dashboard, first free port")
    p_start.add_argument("--port", type=int, default=None)
    p_start.add_argument("--db", default=None)
    sub.add_parser("stop", help="stop only the tracked dashboard process")
    p_restart = sub.add_parser("restart", help="stop + start")
    p_restart.add_argument("--port", type=int, default=None)
    p_restart.add_argument("--db", default=None)
    sub.add_parser("status", help="PID + health + route check")
    sub.add_parser("pick-port", help="print first free candidate port")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        return cmd_serve(args)
    if args.command == "start":
        return cmd_start(args)
    if args.command == "stop":
        return cmd_stop(args)
    if args.command == "restart":
        return cmd_restart(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "pick-port":
        print(find_free_port())
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
