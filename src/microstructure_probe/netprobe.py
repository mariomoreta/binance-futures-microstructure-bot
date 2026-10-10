"""Independent transport diagnostic probe (P1-14B.5).

A minimal reference WebSocket client for Binance USD-M Futures PUBLIC
streams, deliberately INDEPENDENT from the MarketProbe engine: separate
process, separate connection, no shared state, no feature computation.

Purpose: attribute delivery stalls to host/process vs path/provider by
comparing this reference against bot logs over coincident windows:
  both degrade identically -> host, ISP path, or provider (not the bot)
  bot degrades, reference healthy -> bot process/loop (local backlog etc.)
  reference degrades, bot healthy -> per-connection effects

Safety: public streams only. The URL host is pinned to
wss://fstream.binance.com and any stream mentioning user-data/listen
keys is refused. Read-only: only protocol frames (ping/pong/close) are
ever sent. One connection, two default streams (negligible load; no
request-rate impact). Connection parameters mirror probe.py so that
timing differences isolate host/process variables, not tuning.

Usage:
  python -m microstructure_probe.netprobe --duration 600
  python -m microstructure_probe.netprobe --duration 120 --streams btcusdt@bookTicker

Output: UTF-8 JSON-lines, one file per run (never truncated: refuses to
overwrite, appends a numeric suffix). Periodic summaries + final summary.
Exit 0 on duration-reached (diagnostic completeness, not a health verdict).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ALLOWED_HOST = "wss://fstream.binance.com"
DEFAULT_STREAMS = ("btcusdt@bookTicker", "!markPrice@arr@1s")
MIN_DURATION_S = 60
MAX_DURATION_S = 3600
SUMMARY_EVERY_S = 30.0
BACKOFF_MAX_S = 30.0
REFUSED_SUBSTRINGS = ("listenkey", "listen_key", "userdata", "user_data",
                      "account", "order", "position", "@userData")


def validate_target(base_url: str, streams: Any) -> List[str]:
    """Refuse non-public targets. Returns the cleaned stream list."""
    if not isinstance(base_url, str) or not base_url.startswith(ALLOWED_HOST):
        raise ValueError("only %s targets allowed" % ALLOWED_HOST)
    if isinstance(streams, str):
        streams = [streams]
    clean = [str(s).strip() for s in (streams or []) if str(s).strip()]
    if not clean:
        raise ValueError("at least one stream required")
    for stream in clean:
        lowered = stream.lower()
        if any(token in lowered for token in REFUSED_SUBSTRINGS):
            raise ValueError("refusing non-public stream %r" % stream)
    if len(set(clean)) != len(clean):
        raise ValueError("duplicate streams refused")
    return clean


def classify_connect_error(exc: BaseException) -> str:
    """Classify a connection failure (pure, testable)."""
    if isinstance(exc, socket.gaierror):
        return "dns-error"
    if isinstance(exc, ConnectionRefusedError):
        return "tcp-refused"
    if isinstance(exc, TimeoutError):
        return "handshake-timeout"
    name = type(exc).__name__
    if "ConnectionClosed" in name:
        return "ws-closed:%s" % name
    return "other:%s" % name


def stream_event_time(stream: str, payload: Any) -> Optional[float]:
    """Extract the exchange event time E in ms (None when absent)."""
    try:
        if stream == "!markPrice@arr@1s" and isinstance(payload, list):
            candidates = [float(item["E"]) for item in payload
                          if isinstance(item, dict) and "E" in item]
            return max(candidates) if candidates else None
        if isinstance(payload, dict) and "E" in payload:
            return float(payload["E"])
    except (TypeError, ValueError):
        return None
    return None


class ReferenceTracker:
    """Per-stream reference stats (injectable clocks for tests)."""

    def __init__(self, wall_clock_ms: Optional[Callable[[], float]] = None,
                 monotonic: Optional[Callable[[], float]] = None) -> None:
        from .telemetry import RunningDistribution
        self._wall = wall_clock_ms or (lambda: time.time_ns() / 1_000_000)
        self._mono = monotonic or time.monotonic
        self._lag: Dict[str, Any] = {}
        self._dist = RunningDistribution
        self.count: Dict[str, int] = {}
        self.last_e: Dict[str, float] = {}
        self.max_e: Dict[str, float] = {}
        self.e_reorders: Dict[str, int] = {}
        self.last_recv_ms: Dict[str, float] = {}
        self.max_gap_ms: Dict[str, float] = {}
        self._last_mono: Dict[str, float] = {}

    def observe(self, stream: str, event_ms: Optional[float]) -> Dict[str, Any]:
        """Record one message. Returns the observation row (JSON-safe)."""
        now_ms = self._wall()
        now_mono = self._mono()
        self.count[stream] = self.count.get(stream, 0) + 1
        prev_mono = self._last_mono.get(stream)
        gap_ms: Optional[float] = None
        if prev_mono is not None:
            gap_ms = (now_mono - prev_mono) * 1000.0
            if gap_ms > self.max_gap_ms.get(stream, 0.0):
                self.max_gap_ms[stream] = gap_ms
        self._last_mono[stream] = now_mono
        self.last_recv_ms[stream] = now_ms
        lag_ms: Optional[float] = None
        reorder = False
        if event_ms is not None:
            lag_ms = now_ms - event_ms
            if stream not in self._lag:
                self._lag[stream] = self._dist()
            self._lag[stream].add(lag_ms)
            if event_ms < self.max_e.get(stream, float("-inf")):
                reorder = True
                self.e_reorders[stream] = self.e_reorders.get(stream, 0) + 1
            else:
                self.max_e[stream] = event_ms
            self.last_e[stream] = event_ms
        return {"stream": stream, "recv_ms": now_ms, "event_ms": event_ms,
                "lag_ms": lag_ms, "gap_ms": gap_ms, "e_reorder": reorder}

    def summary(self) -> Dict[str, Any]:
        """Cumulative per-stream summary (JSON-safe)."""
        streams: Dict[str, Any] = {}
        for stream in sorted(set(list(self.count) + list(self._lag))):
            lag = self._lag[stream].snapshot() if stream in self._lag else None
            streams[stream] = {
                "messages": self.count.get(stream, 0),
                "lagMs": lag,
                "eReorders": self.e_reorders.get(stream, 0),
                "maxInterArrivalMs": round(self.max_gap_ms.get(stream, 0.0), 3),
                "lastRecvMs": self.last_recv_ms.get(stream),
                "lastEventMs": self.last_e.get(stream),
            }
        return streams


def resolve_out_path(out: Optional[str], run_tag: str) -> Path:
    """Unique output path (never truncates existing evidence)."""
    base = Path(out) if out else (Path("logs") / "netprobe")
    if base.suffix == ".jsonl":
        candidate = base
        parent = base.parent
        stem = base.stem
    else:
        parent = base
        stem = "netprobe-%s" % run_tag
        candidate = parent / (stem + ".jsonl")
    parent.mkdir(parents=True, exist_ok=True)
    if not candidate.exists():
        return candidate
    for i in range(2, 1000):
        alt = parent / ("%s-%d.jsonl" % (stem, i))
        if not alt.exists():
            return alt
    raise OSError("no free output path under %s" % parent)


async def run_reference(streams: List[str], duration_s: float, out_path: Path,
                        base_url: str = ALLOWED_HOST,
                        connect: Optional[Callable[..., Any]] = None,
                        wall_clock_ms: Optional[Callable[[], float]] = None,
                        monotonic: Optional[Callable[[], float]] = None,
                        sleep: Optional[Callable[[float], Any]] = None) -> Dict[str, Any]:
    """Run the reference capture. Returns the final summary dict."""
    import websockets
    wall = wall_clock_ms or (lambda: time.time_ns() / 1_000_000)
    mono = monotonic or time.monotonic
    sleep_fn = sleep or asyncio.sleep
    do_connect = connect or websockets.connect
    tracker = ReferenceTracker(wall_clock_ms=wall, monotonic=mono)
    url = "%s/stream?streams=%s" % (base_url, "/".join(streams))
    start_wall = wall()
    start_mono = mono()
    deadline = start_mono + duration_s
    attempts = 0
    successes = 0
    errors: Dict[str, int] = {}
    reconnects = 0
    dns_ms: Optional[float] = None
    try:
        t0 = mono()
        socket.getaddrinfo("fstream.binance.com", 443)
        dns_ms = (mono() - t0) * 1000.0
    except Exception as exc:
        errors["dns-error"] = errors.get("dns-error", 0) + 1
        dns_ms = None
        _ = exc
    out_fh = open(str(out_path), "w", encoding="utf-8")
    backoff = 1.0

    def emit(record: Dict[str, Any]) -> None:
        out_fh.write(json.dumps(record, allow_nan=False,
                                default=str) + "\n")
        out_fh.flush()

    emit({"kind": "netprobe_start",
          "started_at": datetime.now(timezone.utc).isoformat(),
          "url_host": ALLOWED_HOST, "streams": streams,
          "duration_s": duration_s, "dns_ms": dns_ms})
    last_summary = start_mono
    stop = False
    while not stop and mono() < deadline:
        attempts += 1
        t_conn = mono()
        try:
            async with do_connect(
                    url, open_timeout=15, close_timeout=10,
                    ping_interval=180, ping_timeout=600,
                    max_queue=4096) as websocket:
                successes += 1
                handshake_ms = (mono() - t_conn) * 1000.0
                backoff = 1.0
                emit({"kind": "netprobe_connected",
                      "handshake_ms": round(handshake_ms, 1),
                      "attempt": attempts})
                async for raw in websocket:
                    try:
                        envelope = json.loads(raw)
                        stream = str(envelope.get("stream", "?"))
                        payload = envelope.get("data")
                    except (json.JSONDecodeError, AttributeError):
                        continue
                    tracker.observe(stream, stream_event_time(stream, payload))
                    now = mono()
                    if now - last_summary >= SUMMARY_EVERY_S or now >= deadline:
                        last_summary = now
                        emit({"kind": "netprobe_summary",
                              "elapsed_s": round(now - start_mono, 1),
                              "streams": tracker.summary()})
                    if now >= deadline:
                        stop = True
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            kind = classify_connect_error(exc)
            errors[kind] = errors.get(kind, 0) + 1
            reconnects += 1
            emit({"kind": "netprobe_error", "error": kind,
                  "detail": str(exc)[:200], "retry_s": backoff})
            try:
                await sleep_fn(min(backoff, max(0.0, deadline - mono())))
            except asyncio.CancelledError:
                raise
            backoff = min(backoff * 2.0, BACKOFF_MAX_S)
    final = {"kind": "netprobe_final",
             "elapsed_s": round(mono() - start_mono, 1),
             "duration_reached": mono() >= deadline,
             "attempts": attempts, "successes": successes,
             "reconnects": reconnects, "errors": errors,
             "streams": tracker.summary()}
    emit(final)
    out_fh.close()
    return final


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Independent Binance USD-M "
                                                 "transport reference probe")
    parser.add_argument("--duration", default=600,
                        help="capture seconds in [60,3600]")
    parser.add_argument("--streams", nargs="*", default=list(DEFAULT_STREAMS))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    try:
        duration = int(float(args.duration))
    except (TypeError, ValueError):
        print("invalid --duration %r" % (args.duration,), file=sys.stderr)
        return 2
    if not (MIN_DURATION_S <= duration <= MAX_DURATION_S):
        print("duration %ss outside [%d,%d]" % (duration, MIN_DURATION_S,
                                                MAX_DURATION_S),
              file=sys.stderr)
        return 2
    try:
        streams = validate_target(ALLOWED_HOST, args.streams)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        out_path = resolve_out_path(args.out, run_tag)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("netprobe streams=%s duration=%ss out=%s" % (streams, duration,
                                                       out_path),
          flush=True)
    final = asyncio.run(run_reference(streams, float(duration), out_path))
    print("netprobe done elapsed=%ss attempts=%s errors=%s" % (
        final["elapsed_s"], final["attempts"], final["errors"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
