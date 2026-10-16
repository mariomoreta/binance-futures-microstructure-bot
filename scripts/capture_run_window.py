"""R3 window capture: observe-only evidence collector for ONE expected run.

Reads ONLY the canonical local GET routes (/api/v1/runtime,
/api/v1/detections) while an authorized run is active. It never
starts, stops, restarts or otherwise mutates a run: the only HTTP
verb in this file is GET, and it never touches the registry, the
DBs, the logs, or any secret.

Binding (learn-and-pin): --run-id / --probe-uuid optionally pin the
expected identities up front; anything not pinned is learned from
the first RUNNING sighting and pinned from then on. A RUNNING
sighting WITHOUT a UUID is accepted (absence recorded); the first
later valid UUID is learned and pinned, and any DIFFERENT UUID
after pinning is recorded as incompatible-link and stops the
schedule (exit 3): data is never substituted and nothing is
relaunched. A UUID that disappears after pinning is recorded
(uuid-absent-after-pin) but does not stop the schedule; that
capture simply cannot prove exact attribution.

Detections identity: before a capture's detections content is
attributed to the expected run, its run_id/probe_run_id are
checked (detections-foreign / detections-link-mismatch /
detections-unlinked recorded; unattributed content is kept but
flagged, never substituted).

R3 verdict (separate from acquisition): a captured terminal state
(exit 0) does NOT imply R3 PASS. R3 PASS requires at least one
RUNNING capture of the expected run with a verified process
(process_verified true) AND demonstrable exact attribution:
pinned UUID present in the registry record AND in the snapshot row
(feed_snapshot_run_id) with feed_attribution_method exact-uuid and
feed_attribution current, plus detections content attributed to
the same run. HEALTHY/current alone, a temporal fallback row
(method temporal, or a snapshot without UUID), temporal
coincidence alone, or a post-close capture never suffice;
HEALTHY vs DEGRADED is recorded as context, never as the
attribution decision. The report carries the finally pinned
identities plus doc["r3"] = verdict/reasons.
Early-terminal acquisition, acquisition timeouts and
run-changed endings yield UNKNOWN (nothing to assess / broken
evidence); a proven contradictory link yields FAIL.

Schedule: capture at first RUNNING sighting (t0), then at
+offsets seconds (default 30,60,90), then wait (bounded) for a
terminal state and capture it. Every capture stores request/response
timestamps, HTTP duration/status and the REVIEWED fields only
(state, UUIDs, process_verified, attribution, health/freshness,
supervisor/sentinel, detections coverage). Raw bodies are not kept.

Output protection: --out must be a NEW path outside data/, logs/,
secrets/, private/ and never a database/journal/secret filename.
All budgets are explicit; nothing waits forever.

Exit codes: 0 terminal captured (acquisition complete; see doc["r3"]
for the separate R3 verdict, which may still be UNKNOWN);
1 usage/output-protection refusal (no request sent);
2 invalid binding (no request sent);
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
        "feed_attribution_method": _txt(x.get("feed_attribution_method")),
        "feed_snapshot_run_id": _txt(x.get("feed_snapshot_run_id")),
        "feed_snapshot_timestamp": _num(x.get("feed_snapshot_timestamp")),
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
    uuid_absences = 0
    uuid_first_seen = None
    doc: dict = {
        "tool": "capture_run_window/v2 (GET only, no Start/Stop; "
                "acquisition outcome separated from the R3 verdict)",
        "base_url": args.base_url,
        "expected": {"run_id": pinned_run, "probe_run_id": pinned_uuid},
        "events": [],
        "captures": [],
        "complete": False,
    }

    def event(kind: str, detail: str) -> None:
        doc["events"].append({"at": _utc_now(), "kind": kind, "detail": detail})

    def pinned_block() -> dict:
        return {"run_id": pinned_run, "probe_run_id": pinned_uuid,
                "uuid_absences": uuid_absences,
                "uuid_first_seen": uuid_first_seen}

    def r3_verdict() -> dict:
        """R3 over the captures so far (never from acquisition alone).

        PASS needs one RUNNING capture of the pinned run with a
        verified process and demonstrable EXACT attribution: the
        pinned UUID in the registry record (probe_run_id) AND in the
        snapshot row (feed_snapshot_run_id) with
        feed_attribution_method exact-uuid and feed_attribution
        current, plus detections content attributed to the same run.
        HEALTHY/current without the UUID, any temporal fallback
        (method temporal, snapshot without UUID), temporal
        coincidence, and post-close states never qualify.
        """
        running = [c for c in doc["captures"]
                   if c["runtime"]["reviewed"].get("state") == "RUNNING"
                   and c["runtime"]["reviewed"].get("run_id") == pinned_run]
        if not running:
            return {"verdict": "UNKNOWN",
                    "reasons": ["no-running-capture-of-expected-run"]}
        if any(e["kind"] == "incompatible-link" for e in doc["events"]):
            return {"verdict": "FAIL",
                    "reasons": ["contradictory-link-observed"]}
        if any(e["kind"] == "run-changed" for e in doc["events"]):
            return {"verdict": "UNKNOWN",
                    "reasons": ["run-changed-breaks-evidence"]}
        reasons = []
        for cap in running:
            rev = cap["runtime"]["reviewed"]
            det = cap["detections"]
            ok_uuid = (pinned_uuid is not None
                       and rev.get("probe_run_id") == pinned_uuid)
            ok_snap = (pinned_uuid is not None
                       and rev.get("feed_snapshot_run_id") == pinned_uuid)
            ok_method = (rev.get("feed_attribution_method") == "exact-uuid")
            ok_verified = rev.get("process_verified") is True
            ok_attr = (ok_uuid and ok_snap and ok_method
                       and rev.get("feed_attribution") == "current")
            ok_det = (isinstance(det, dict)
                      and det.get("attributed") is True)
            if ok_uuid and ok_snap and ok_method and ok_verified \
                    and ok_attr and ok_det:
                return {"verdict": "PASS",
                        "reasons": ["qualifying-capture: %s (health %s recorded "
                                    "as context, not as the decision; "
                                    "method exact-uuid, snapshot %s)" % (
                                        cap["tag"], rev.get("feed_health"),
                                        rev.get("feed_snapshot_run_id"))]}
            missing = []
            if not ok_uuid:
                missing.append("exact-uuid-not-demonstrated")
            if not ok_snap:
                missing.append("snapshot-uuid-not-demonstrated")
            if not ok_method:
                missing.append("attribution-method-not-exact")
            if not ok_verified:
                missing.append("process-not-verified")
            if not ok_attr:
                missing.append("attribution-not-current-with-uuid")
            if not ok_det:
                missing.append("detections-not-attributed")
            reasons.append("%s lacks %s" % (cap["tag"], "+".join(missing)))
        return {"verdict": "UNKNOWN", "reasons": reasons}

    def finish(outcome: str, code: int, complete: bool) -> int:
        doc["outcome"] = outcome
        doc["complete"] = complete
        doc["pinned"] = pinned_block()
        doc["r3"] = r3_verdict()
        out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        return code

    def check_detections(det: dict, tag: str):
        """(entry, event-or-None). Content attributed only after identity
        check; mismatches are kept but flagged, never substituted."""
        base = {"request_at": det.get("request_at"),
                "response_at": det.get("response_at"),
                "http_ms": det.get("http_ms"),
                "http_status": det.get("http_status"),
                "attributed": False}
        if not det.get("ok"):
            base["error"] = str(det.get("error"))
            return (base, ("detections-read-failed",
                           "%s: %s" % (tag, det.get("error"))))
        rev = _review_detections(det.get("payload"))
        base["reviewed"] = rev
        if rev.get("run_id") != pinned_run:
            return (base, ("detections-foreign",
                           "%s: expected run %s, detections run %s"
                           % (tag, pinned_run, rev.get("run_id"))))
        if pinned_uuid is None:
            return (base, ("detections-unlinked",
                           "%s: runtime UUID never pinned; content unattributed"
                           % tag))
        if rev.get("probe_run_id") is not None \
                and rev["probe_run_id"] != pinned_uuid:
            return (base, ("detections-link-mismatch",
                           "%s: expected UUID %s, detections UUID %s"
                           % (tag, pinned_uuid, rev.get("probe_run_id"))))
        base["attributed"] = True
        return (base, None)

    # 1) Acquire RUNNING (bounded). A RUNNING sighting without a
    # UUID is accepted (absence recorded); the first later valid UUID
    # is learned and pinned.
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
                return finish("run-changed", 3, False)
            if rev["state"] == "RUNNING" and rev["run_id"]:
                if pinned_run is None:
                    pinned_run = rev["run_id"]
                    event("run-pinned", pinned_run)
                uuid = rev["probe_run_id"]
                if uuid is not None and pinned_uuid is not None \
                        and uuid != pinned_uuid:
                    event("incompatible-link",
                          "expected %s, saw %s" % (pinned_uuid, uuid))
                    return finish("incompatible-link", 3, False)
                if uuid is not None and pinned_uuid is None:
                    pinned_uuid = uuid
                    uuid_first_seen = "acquire"
                    event("uuid-pinned", uuid)
                if uuid is None:
                    uuid_absences += 1
                    event("uuid-absent-at-acquire",
                          "RUNNING without UUID; watching for the first valid one")
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
        return finish("acquire-timeout", 4, False)

    def pin_late(uuid: str | None, tag: str) -> str | None:
        """Learn/pin/check the runtime UUID. Returns refusal kind or None."""
        nonlocal pinned_uuid, uuid_first_seen, uuid_absences
        if uuid is None:
            uuid_absences += 1
            event("uuid-absent", "%s: no UUID yet" % tag)
            return None
        if pinned_uuid is None:
            pinned_uuid = uuid
            uuid_first_seen = tag
            event("uuid-pinned", "%s: %s" % (tag, uuid))
            return None
        if uuid != pinned_uuid:
            event("incompatible-link",
                  "%s: expected %s, saw %s" % (tag, pinned_uuid, uuid))
            return "incompatible-link"
        return None

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
        refusal = pin_late(rev.get("probe_run_id"), tag)
        if refusal:
            return refusal
        det_rev, det_event = check_detections(det, tag)
        if det_event is not None:
            event(*det_event)
        entry = {
            "tag": tag,
            "runtime": {"request_at": res["request_at"],
                        "response_at": res["response_at"],
                        "http_ms": res["http_ms"],
                        "http_status": res["http_status"],
                        "reviewed": rev},
            "detections": det_rev,
        }
        doc["captures"].append(entry)
        return rev

    # t0 capture from the acquiring read (no second request).
    res0, rev0 = first
    det0 = _get(args.base_url, "/api/v1/detections", args.request_timeout_s)
    det0_rev, det0_event = check_detections(det0, "t0-running")
    if det0_event is not None:
        event(*det0_event)
    doc["captures"].append({
        "tag": "t0-running",
        "runtime": {"request_at": res0["request_at"],
                    "response_at": res0["response_at"],
                    "http_ms": res0["http_ms"],
                    "http_status": res0["http_status"], "reviewed": rev0},
        "detections": det0_rev,
    })
    if rev0["state"] in TERMINAL_STATES:
        # Acquisition complete, but a post-close capture alone can
        # never prove live exact attribution: R3 stays non-PASS.
        return finish("early-terminal-captured", 0, True)

    # 2) Scheduled offsets from t0.
    for off in offsets:
        wait = (t0_mono + off) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        got = capture("t+%gs" % off)
        if got in ("run-changed", "incompatible-link"):
            return finish(got, 3, False)

    # 3) Bounded terminal wait.
    end = time.monotonic() + args.terminal_timeout_s
    while time.monotonic() < end:
        time.sleep(min(args.poll_s, max(0.05, end - time.monotonic())))
        got = capture("terminal-poll")
        if got in ("run-changed", "incompatible-link"):
            return finish(got, 3, False)
        if isinstance(got, dict) and got.get("state") in TERMINAL_STATES:
            return finish("terminal-captured", 0, True)
        if got is None:
            continue
    # Final attempt already recorded by the loop; close out partial.
    return finish("terminal-timeout", 5, False)


if __name__ == "__main__":
    raise SystemExit(main())
