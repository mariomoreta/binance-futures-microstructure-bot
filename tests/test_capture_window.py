"""R3 capture tool: GET-only, pinned identities, bounded waits, safe output.

Local HTTPServer fixtures only. Never touches the network beyond
localhost, never starts a monitor, never reads the canonical DBs.
Run: python run_tests.py
"""

import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from capture_run_window import main  # noqa: E402

UUID_A = "a" * 32
UUID_B = "b" * 32


def _runtime(state="RUNNING", run="probe-test", uuid=UUID_A):
    return {"state": state, "running": state == "RUNNING", "run_id": run,
            "probe_run_id": uuid, "process_verified": True,
            "feed_health": "HEALTHY", "feed_attribution": "current",
            "feed_note": None, "latest_snapshot_age": 5,
            "started_at": "2026-10-16T00:00:00+00:00",
            "supervisor": {"state": "SUPERVISOR_ACTIVE", "lease_state": "ACTIVE",
                           "abort_triggered": False},
            "sentinel": {"state": "SENTINEL_ACTIVE", "lease_state": "ACTIVE"}}


def _detections(run="probe-test"):
    return {"available": True, "run_id": run, "probe_run_id": UUID_A,
            "grouping_version": "v1", "events_total": 10,
            "episodes_total": 2, "limitation": None}


class _Handler(BaseHTTPRequestHandler):
    runtime_plan = []
    detections_body = {}
    runtime_calls = 0
    total_calls = 0
    sleep_s = 0.0
    status_code = 200

    def log_message(self, *a):
        pass

    def do_GET(self):
        type(self).total_calls += 1
        if self.sleep_s:
            time.sleep(self.sleep_s)
        if self.status_code != 200:
            self.send_response(self.status_code)
            self.end_headers()
            return
        if self.path.startswith("/api/v1/detections"):
            body = json.dumps(type(self).detections_body).encode()
        else:
            type(self).runtime_calls += 1
            idx = min(type(self).runtime_calls - 1,
                      len(type(self).runtime_plan) - 1)
            body = json.dumps(type(self).runtime_plan[idx]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError,
                ConnectionAbortedError):
            pass


def _serve(testcase, runtime_plan, detections=None, sleep_s=0.0,
           status_code=200):
    handler = type("H%d" % id(testcase), (_Handler,), {})  # fresh counters
    handler.runtime_plan = runtime_plan
    handler.detections_body = detections if detections is not None else _detections()
    handler.runtime_calls = 0
    handler.total_calls = 0
    handler.sleep_s = sleep_s
    handler.status_code = status_code
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
    thread.daemon = True
    thread.start()
    # LIFO: join runs last, so shutdown -> close -> join in that order.
    testcase.addCleanup(thread.join, 5)
    testcase.addCleanup(server.server_close)
    testcase.addCleanup(server.shutdown)
    return server, handler


def _tmpout(testcase, name="r3.json"):
    tmp = Path(tempfile.mkdtemp(prefix="r3cap_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    return tmp / name


def _rmtree(path: Path) -> None:
    try:
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
    except OSError:
        pass


BASE_ARGS = ["--poll-s", "0.05", "--acquire-timeout-s", "5",
             "--terminal-timeout-s", "5", "--request-timeout-s", "2"]


class CaptureFlowTest(unittest.TestCase):
    def test_valid_run_to_terminal(self) -> None:
        server, _ = self._run_server(
            [_runtime("RUNNING"), _runtime("RUNNING"), _runtime("COMPLETED")])
        out = _tmpout(self)
        code = main(["--base-url", self._url(server), "--out", str(out),
                     "--offsets", "0.2,0.4"] + BASE_ARGS)
        self.assertEqual(code, 0)
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertTrue(doc["complete"])
        self.assertEqual(doc["outcome"], "terminal-captured")
        tags = [c["tag"] for c in doc["captures"]]
        self.assertEqual(tags[0], "t0-running")
        rev = doc["captures"][0]["runtime"]["reviewed"]
        self.assertEqual((rev["run_id"], rev["probe_run_id"]), ("probe-test", UUID_A))
        self.assertEqual(rev["feed_attribution"], "current")
        det = doc["captures"][0]["detections"]["reviewed"]
        self.assertEqual((det["events_total"], det["episodes_total"]), (10, 2))

    def test_learn_and_pin_without_args(self) -> None:
        server, _ = self._run_server([_runtime("RUNNING"), _runtime("COMPLETED")])
        out = _tmpout(self)
        code = main(["--base-url", self._url(server), "--out", str(out),
                     "--offsets", "0.2"] + BASE_ARGS)
        self.assertEqual(code, 0)
        kinds = [e["kind"] for e in
                 json.loads(out.read_text(encoding="utf-8"))["events"]]
        self.assertIn("run-pinned", kinds)
        self.assertIn("uuid-pinned", kinds)

    def test_run_change_stops_without_substitution(self) -> None:
        server, handler = self._run_server(
            [_runtime("RUNNING", run="probe-test"), _runtime("RUNNING", run="probe-other")])
        out = _tmpout(self)
        before = handler.total_calls
        code = main(["--base-url", self._url(server), "--out", str(out),
                     "--run-id", "probe-test", "--offsets", "30"] + BASE_ARGS)
        self.assertEqual(code, 3)
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["outcome"], "run-changed")
        self.assertFalse(doc["complete"])
        # No capture carries the foreign run.
        for cap in doc["captures"]:
            self.assertEqual(cap["runtime"]["reviewed"]["run_id"], "probe-test")
        self.assertGreater(handler.total_calls, before)

    def test_incompatible_link_refused(self) -> None:
        server, _ = self._run_server([_runtime("RUNNING", uuid=UUID_B)])
        out = _tmpout(self)
        code = main(["--base-url", self._url(server), "--out", str(out),
                     "--probe-uuid", UUID_A] + BASE_ARGS)
        self.assertEqual(code, 3)
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["outcome"], "incompatible-link")

    def test_early_terminal_captured(self) -> None:
        server, _ = self._run_server([_runtime("COMPLETED")])
        out = _tmpout(self)
        code = main(["--base-url", self._url(server), "--out", str(out),
                     "--offsets", "30"] + BASE_ARGS)
        self.assertEqual(code, 0)
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["outcome"], "early-terminal-captured")

    def test_error_status_records_attempt(self) -> None:
        server, _ = self._run_server([], status_code=500)
        out = _tmpout(self)
        code = main(["--base-url", self._url(server), "--out", str(out),
                     "--acquire-timeout-s", "1"] + BASE_ARGS)
        self.assertEqual(code, 4)
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["outcome"], "acquire-timeout")
        self.assertTrue(any(e["kind"] == "acquire-read-failed"
                            for e in doc["events"]))

    def test_timeout_records_without_hanging(self) -> None:
        server, _ = self._run_server([_runtime("RUNNING")], sleep_s=3.0)
        out = _tmpout(self)
        code = main(["--base-url", self._url(server), "--out", str(out),
                     "--acquire-timeout-s", "1", "--request-timeout-s", "0.2"]
                    + BASE_ARGS[2:])
        self.assertEqual(code, 4)

    def _run_server(self, runtime_plan, **kw):
        return _serve(self, runtime_plan, **kw)

    def _url(self, server) -> str:
        return "http://127.0.0.1:%d" % server.server_address[1]


class OutputProtectionTest(unittest.TestCase):
    def test_refuses_existing_db_logs_and_secrets_without_requests(self) -> None:
        server, handler = _serve(self, [_runtime("RUNNING")])
        url = "http://127.0.0.1:%d" % server.server_address[1]
        tmp = Path(tempfile.mkdtemp(prefix="r3prot_"))
        self.addCleanup(lambda: _rmtree(tmp))
        existing = tmp / "out.json"
        existing.write_text("{}", encoding="utf-8")
        repo = Path(__file__).resolve().parent.parent
        cases = [existing,
                 tmp / "x.db", tmp / "x-journal",
                 repo / "data" / "r3.json", repo / "logs" / "r3.json",
                 repo / "secrets" / "r3.json", tmp / "k.key"]
        for path in cases:
            code = main(["--base-url", url, "--out", str(path)] + BASE_ARGS)
            self.assertEqual(code, 1, path)
        self.assertEqual(handler.total_calls, 0)

    def test_invalid_binding_sends_nothing(self) -> None:
        server, handler = _serve(self, [_runtime("RUNNING")])
        out = _tmpout(self)
        code = main(["--base-url",
                     "http://127.0.0.1:%d" % server.server_address[1],
                     "--out", str(out), "--probe-uuid", "ZZZ"] + BASE_ARGS)
        self.assertEqual(code, 2)
        self.assertEqual(handler.total_calls, 0)
        self.assertFalse(out.exists())

    def test_source_is_get_only_and_repo_clean(self) -> None:
        src = (Path(__file__).resolve().parent.parent / "scripts"
               / "capture_run_window.py").read_text(encoding="utf-8")
        for token in ("POST", "PUT", "DELETE", "urlencode("):
            self.assertNotIn(token, src)
        self.assertIn('method="GET"', src)
        imports = [ln for ln in src.splitlines()
                   if ln.startswith("import ") or ln.startswith("from ")]
        for token in ("microstructure_probe", "sqlite3"):
            self.assertFalse(any(token in ln for ln in imports), token)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
