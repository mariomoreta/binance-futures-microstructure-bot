"""P1-03 minimal live operator dashboard (stdlib only, no new dependencies).

Reads the P1-02 persistence store and renders operator pages. This module is
visualization only: nothing here can trade, and the engine never consumes
anything rendered here.

Routes: / (→ /overview), /overview, /system, /api/health, /api/snapshot.

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
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .persistence import PersistenceStore

DASHBOARD_VERSION = "0.3.0"
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
            f"<a href='/api/snapshot'>/api/snapshot</a></nav>"
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
    messages = _safe_dict(dq.get("messagesByStream"))
    total_messages = sum(int(v) for v in messages.values())
    runtime = float(snap.get("runtimeSeconds") or 0.0)
    gaps = _safe_dict(dq.get("depthSequenceGapsBySymbol"))
    recon = _safe_dict(dq.get("reconnections"))
    snap_ts = snap.get("snapshotTimestamp")
    body = f"<h2>Status</h2>"
    body += _kv_table([
        ("dashboard status", STATUS_LABELS.get(status, status)),
        ("reasons", "; ".join(health["reasons"]) or "—"),
        ("runtime (probe)", f"{runtime:.1f}s"),
        ("total messages", f"{total_messages} ({total_messages / max(runtime, 1):.1f}/s)"),
        ("streams active/expected",
         f"{dq.get('activeStreams', '?')}/{dq.get('expectedStreams', '?')}"),
        ("missing streams", ", ".join(_safe_list(dq.get("missingStreams"))) or "none"),
        ("stale streams", ", ".join(_safe_list(dq.get("staleStreams"))) or "none"),
        ("silent streams", ", ".join(_safe_list(dq.get("silentStreams"))) or "none"),
        ("reconnects", json.dumps(recon)),
        ("depth sequence gaps", json.dumps(gaps)),
        ("timestamp rejected", f"{dq.get('timestampRejected', '?')} "
         f"(rate {float(rj.get('rejection_rate', 0.0)):.1%} over retained rows)"),
        ("snapshot timestamp",
         f"{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(snap_ts)) if snap_ts else '?'} "
         f"({time.time() - snap_ts:.0f}s ago)" if snap_ts else "unknown"),
        ("data quality", "DEGRADED — see reasons" if status == "degraded" else status.upper()),
    ])
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
    body += "<h2>Rejections / skew</h2>" + _kv_table([
        ("timestamp rejected (probe counter)", dq.get("timestampRejected", "?")),
        ("retained rejected rows", rj.get("total_rejected", "?")),
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

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            body = b'<a href="/overview">/overview</a>'
            self.send_response(302)
            self.send_header("Location", "/overview")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/overview":
            self._send(200, "text/html; charset=utf-8",
                       render_overview(self.state).encode("utf-8"))
        elif path == "/system":
            self._send(200, "text/html; charset=utf-8",
                       render_system(self.state).encode("utf-8"))
        elif path == "/api/health":
            self._send_json(200, self._health_payload())
        elif path == "/api/snapshot":
            snap = self.state.snapshot()
            if snap is None:
                self._send_json(404, {"error": "no snapshot persisted yet"})
            else:
                self._send_json(200, snap)
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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Binance Futures operator dashboard")
    sub = parser.add_subparsers(dest="command", required=True)
    p_serve = sub.add_parser("serve", help="run the HTTP server in the foreground")
    p_serve.add_argument("--port", type=int, required=True)
    p_serve.add_argument("--db", default=None)
    p_start = sub.add_parser("start", help="start detached dashboard, first free port")
    p_start.add_argument("--port", type=int, default=None)
    p_start.add_argument("--db", default=None)
    sub.add_parser("stop", help="stop only the tracked dashboard process")
    sub.add_parser("restart", help="stop + start")
    sub.add_parser("status", help="PID + health + route check")
    sub.add_parser("pick-port", help="print first free candidate port")
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
