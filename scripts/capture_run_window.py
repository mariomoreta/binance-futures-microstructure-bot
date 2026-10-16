"""R3 window capture: observe-only evidence collector for ONE expected run.

Reads ONLY the canonical local GET routes (/api/v1/runtime,
/api/v1/detections) while an authorized run is active. It never
starts, stops, restarts or otherwise mutates a run: the only HTTP
verb in this file is GET, and it never touches the registry, the
DBs, the logs, or any secret.

Binding (learn-and-pin): --run-id / --probe-uuid optionally pin the
expected identities up front; anything not pinned is learned from
the first RUNNING sighting and pinned from then on. A different
run_id later, or a different probe_run_id once pinned, is recorded
as run-changed / incompatible-link and stops the schedule (exit 3):
data is never substituted and nothing is relaunched.

Schedule: capture at first RUNNING sighting (t0), then at
+offsets seconds (default 30,60,90), then wait (bounded) for a
terminal state and capture it. Every capture stores request/response
timestamps, HTTP duration/status and the REVIEWED fields only
(state, UUIDs, process_verified, attribution, health/freshness,
supervisor/sentinel, detections coverage). Raw bodies are not kept.

Output protection: --out must be a NEW path outside data/, logs/,
secrets/, private/ and never a database/journal/secret filename.
All budgets are explicit; nothing waits forever.

Exit codes: 0 terminal captured; 1 usage/output-protection refusal
(no request sent); 2 invalid binding (no request sent);
3 run-changed/incompatible-link (partial written);
4 acquisition timeout (attempt record written);
5 terminal timeout (partial written).

Usage (next authorized window; run from repo root AFTER launch):
  python scripts/capture_run_window.py --run-id probe-20261016T005550Z \\
      --out docs/evidence/R3_WINDOW_<run>.json
  (omit --run-id/--probe-uuid to learn-and-pin from first RUNNING)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMINAL_STATES = ("COMPLETED", "FAILED", "ABORTED")
DB_SUFFIXES = (".db", "-journal", "-wal", "-shm")
SECRET_NAMES = (".env",)
SECRET_SUFFIXES = (".key", ".pem")
PROTECTED_DIRS = ("data", "logs", "secrets", "private")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_uuid(value: str | None) -> bool:
    if value is None:
        return True
    if len(value) != 32:
        return False
    try:
        return all(c in "0123456789abcdef" for c in value.lower()) \
            and value == value.lower()
    except Exception:
        return False


def _protect(out: Path) -> str | None:
    """None if writable-new-and-safe, else refusal reason (no I/O done).

    Inside the repo: data/, logs/, secrets/, private/ and .git are
    off-limits, as are database/journal/secret filenames anywhere.
    Outside the repo (e.g. a temp dir): still refuses existing files
    and database/journal/secret filenames. Nothing is ever overwritten.
    """
    try:
        real = out.resolve()
    except OSError as exc:
        return "unresolvable-path: %s" % exc
    if real.exists():
        return "already-exists (refusing overwrite)"
    if real.suffix.lower() in DB_SUFFIXES[:1] + SECRET_SUFFIXES:
        return "protected-suffix"
    name = real.name.lower()
    if name in SECRET_NAMES or name in ("journal",):
        return "protected-name"
    if name.endswith(DB_SUFFIXES[1:]):
        return "protected-name"
    try:
        rel = real.relative_to(ROOT)
    except ValueError:
        return None  # outside repo, filename already vetted above
    if ".git" in (p.lower() for p in rel.parts):
        return "protected-dir"
    if set(p.lower() for p in rel.parts[:-1]) & set(PROTECTED_DIRS):
        return "protected-dir"
    return None


def _get(base: str, route: str, timeout_s: float) -> dict:
    started = time.monotonic()
    req_at = _utc_now()
    req = urllib.request.Request(base.rstrip("/") + route, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return {"ok": False, "request_at": req_at,
                "response_at": _utc_now(),
                "http_ms": round((time.monotonic() - started) * 1000.0, 1),
                "http_status": None,
                "error": "%s: %s" % (type(exc).__name__, exc)}
    http_ms = round((time.monotonic() - started) * 1000.0, 1)
    try:
        payload = json.loads(body) if body.strip() else None
    except ValueError:
        return {"ok": False, "request_at": req_at,
                "response_at": _utc_now(), "http_ms": http_ms,
                "http_status": status, "error": "invalid-json"}
    return {"ok": True, "request_at": req_at,
            "response_at": _utc_now(), "http_ms": http_ms,
            "http_status": status, "payload": payload}


def _num(value) -> float | int | None:
    return value if isinstance(value, (int, float)) and value == value else None


def _txt(value) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _review_runtime(payload) -> dict:
    x = payload if isinstance(payload, dict) else {}
    sup = x.get("supervisor") if isinstance(x.get("supervisor"), dict) else {}
    sen = x.get("sentinel") if isinstance(x.get("sentinel"), dict) else {}
    return {
        "state": _txt(x.get("state")), "running": x.get("running"),
        "run_id": _txt(x.get("run_id")),
        "probe_run_id": _txt(x.get("probe_run_id")),
        "process_verified": x.get("process_verified"),
        "feed_health": _txt(x.get("feed_health")),
        "feed_attribution": _txt(x.get("feed_attribution")),
        "feed_note": _txt(x.get("feed_note")),
        "latest_snapshot_age": _num(x.get("latest_snapshot_age")),
        "started_at": _txt(x.get("started_at")),
        "last_exit_at": _txt(x.get("last_exit_at")),
        "last_exit_reason": _txt(x.get("last_exit_reason")),
        "supervisor": {k: sup.get(k) for k in
                       ("state", "lease_state", "abort_triggered")},
        "sentinel": {k: sen.get(k) for k in ("state", "lease_state")},
    }


def _review_detections(payload) -> dict:
    x = payload if isinstance(payload, dict) else {}
    return {
        "available": x.get("available"),
        "run_id": _txt(x.get("run_id")),
        "probe_run_id": _txt(x.get("probe_run_id")),
        "grouping_version": _txt(x.get("grouping_version")),
        "events_total": _num(x.get("events_total")),
        "episodes_total": _num(x.get("episodes_total")),
        "limitation": _txt(x.get("limitation")),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Observe-only R3 window capture (GET only).")
    ap.add_argument("--base-url", default="http://127.0.0.1:3020")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--probe-uuid", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--poll-s", type=float, default=5.0)
    ap.add_argument("--acquire-timeout-s", type=float, default=180.0)
    ap.add_argument("--offsets", default="30,60,90")
    ap.add_argument("--terminal-timeout-s", type=float, default=600.0)
    ap.add_argument("--request-timeout-s", type=float, default=10.0)
    args = ap.parse_args(argv)

    if args.run_id is not None and not args.run_id.strip():
        print("invalid --run-id", file=sys.stderr)
        return 2
    if not _valid_uuid(args.probe_uuid):
        print("invalid --probe-uuid (need 32 lowercase hex)", file=sys.stderr)
        return 2
    if not (args.poll_s > 0 and args.acquire_timeout_s > 0
            and args.terminal_timeout_s > 0 and args.request_timeout_s > 0):
        print("timeouts must be positive", file=sys.stderr)
        return 2
    try:
        offsets = sorted({float(s) for s in str(args.offsets).split(",") if s.strip()})
    except ValueError:
        print("invalid --offsets", file=sys.stderr)
        return 2
    if any(o < 0 or o > 3600 for o in offsets):
        print("offsets must be within [0, 3600]", file=sys.stderr)
        return 2

    out = Path(args.out)
    refusal = _protect(out)
    if refusal is not None:
        print("output refused: %s" % refusal, file=sys.stderr)
        return 1

    pinned_run = args.run_id.strip() if args.run_id else None
    pinned_uuid = args.probe_uuid
    doc: dict = {
        "tool": "capture_run_window/v1 (GET only, no Start/Stop)",
        "base_url": args.base_url,
        "expected": {"run_id": pinned_run, "probe_run_id": pinned_uuid},
        "events": [],
        "captures": [],
        "complete": False,
    }

    def event(kind: str, detail: str) -> None:
        doc["events"].append({"at": _utc_now(), "kind": kind, "detail": detail})

    # 1) Acquire RUNNING (bounded).
    deadline = time.monotonic() + args.acquire_timeout_s
    t0_mono = None
    first = None
    while time.monotonic() < deadline:
        res = _get(args.base_url, "/api/v1/runtime", args.request_timeout_s)
        if not res["ok"]:
            event("acquire-read-failed", str(res.get("error")))
        else:
            rev = _review_runtime(res.get("payload"))
            if rev["run_id"] is not None and pinned_run is not None \
                    and rev["run_id"] != pinned_run:
                event("run-changed",
                      "expected %s, saw %s" % (pinned_run, rev["run_id"]))
                doc["outcome"] = "run-changed"
                out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
                return 3
            if rev["state"] == "RUNNING" and rev["run_id"]:
                if pinned_run is None:
                    pinned_run = rev["run_id"]
                    event("run-pinned", pinned_run)
                uuid = rev["probe_run_id"]
                if uuid is not None and pinned_uuid is not None \
                        and uuid != pinned_uuid:
                    event("incompatible-link",
                          "expected %s, saw %s" % (pinned_uuid, uuid))
                    doc["outcome"] = "incompatible-link"
                    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
                    return 3
                if pinned_uuid is None and uuid is not None:
                    pinned_uuid = uuid
                    event("uuid-pinned", uuid)
                t0_mono = time.monotonic()
                first = (res, rev)
                break
            if rev["state"] in TERMINAL_STATES and rev["run_id"] \
                    and (pinned_run is None or rev["run_id"] == pinned_run):
                # Early terminal: the expected run already closed.
                if pinned_run is None:
                    pinned_run = rev["run_id"]
                t0_mono = time.monotonic()
                first = (res, rev)
                event("early-terminal", str(rev["state"]))
                break
        time.sleep(min(args.poll_s, max(0.05, deadline - time.monotonic())))
    if first is None:
        event("acquire-timeout",
              "no RUNNING sighting within %.0fs" % args.acquire_timeout_s)
        doc["outcome"] = "acquire-timeout"
        out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        return 4

    def capture(tag: str) -> dict | None:
        res = _get(args.base_url, "/api/v1/runtime", args.request_timeout_s)
        det = _get(args.base_url, "/api/v1/detections", args.request_timeout_s)
        if not res["ok"]:
            event("capture-read-failed", "%s: %s" % (tag, res.get("error")))
            return None
        rev = _review_runtime(res.get("payload"))
        if rev["run_id"] != pinned_run:
            event("run-changed",
                  "%s: expected %s, saw %s" % (tag, pinned_run, rev["run_id"]))
            return "run-changed"
        uuid = rev["probe_run_id"]
        if uuid is not None and pinned_uuid is not None and uuid != pinned_uuid:
            event("incompatible-link", "%s: %s" % (tag, uuid))
            return "incompatible-link"
        entry = {
            "tag": tag,
            "runtime": {"request_at": res["request_at"],
                        "response_at": res["response_at"],
                        "http_ms": res["http_ms"],
                        "http_status": res["http_status"],
                        "reviewed": rev},
            "detections": ({"request_at": det["request_at"],
                            "response_at": det["response_at"],
                            "http_ms": det["http_ms"],
                            "http_status": det["http_status"],
                            "reviewed": _review_detections(det.get("payload"))}
                           if det["ok"] else
                           {"request_at": det["request_at"],
                            "response_at": det["response_at"],
                            "http_ms": det["http_ms"],
                            "http_status": det["http_status"],
                            "error": str(det.get("error"))}),
        }
        doc["captures"].append(entry)
        return rev

    # t0 capture from the acquiring read (no second request).
    res0, rev0 = first
    det0 = _get(args.base_url, "/api/v1/detections", args.request_timeout_s)
    doc["captures"].append({
        "tag": "t0-running",
        "runtime": {"request_at": res0["request_at"],
                    "response_at": res0["response_at"],
                    "http_ms": res0["http_ms"],
                    "http_status": res0["http_status"], "reviewed": rev0},
        "detections": ({"request_at": det0["request_at"],
                        "response_at": det0["response_at"],
                        "http_ms": det0["http_ms"],
                        "http_status": det0["http_status"],
                        "reviewed": _review_detections(det0.get("payload"))}
                       if det0["ok"] else {"error": str(det0.get("error"))}),
    })
    if rev0["state"] in TERMINAL_STATES:
        doc["outcome"] = "early-terminal-captured"
        doc["complete"] = True
        out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        return 0

    # 2) Scheduled offsets from t0.
    for off in offsets:
        wait = (t0_mono + off) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        got = capture("t+%gs" % off)
        if got in ("run-changed", "incompatible-link"):
            doc["outcome"] = got
            out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
            return 3

    # 3) Bounded terminal wait.
    end = time.monotonic() + args.terminal_timeout_s
    while time.monotonic() < end:
        time.sleep(min(args.poll_s, max(0.05, end - time.monotonic())))
        got = capture("terminal-poll")
        if got in ("run-changed", "incompatible-link"):
            doc["outcome"] = got
            out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
            return 3
        if isinstance(got, dict) and got.get("state") in TERMINAL_STATES:
            doc["outcome"] = "terminal-captured"
            doc["complete"] = True
            out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
            return 0
        if got is None:
            continue
    # Final attempt already recorded by the loop; close out partial.
    doc["outcome"] = "terminal-timeout"
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
