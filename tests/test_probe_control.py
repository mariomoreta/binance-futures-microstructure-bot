"""P1-11B.1 probe lifecycle + dashboard run-control tests.

Lifecycle units use an isolated registry file (MICROPROBE_RUNTIME_FILE)
and mocked process inspection / subprocess — no real processes are
touched. API tests run a real in-process dashboard server with mocked
control spawn/stop (no live probe launched); live roundtrip happens
in the task's verification step, not here.
"""

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="proberun_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    path = tmp / "probe_runtime.json"
    os.environ["MICROPROBE_RUNTIME_FILE"] = str(path)
    testcase.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
    return path


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


def _record(pid=999999, state="RUNNING", created="STAMP",
            duration=None, launcher="agent"):
    return {"schema": 1, "writer": "control/1", "state": state,
            "pid": pid, "create_time": created,
            "started_at": "2026-10-07T10:00:00+00:00", "mode": "observe",
            "command": ["python", "-m", "microstructure_probe"],
            "duration_seconds": duration, "expected_end_at": None,
            "launcher": launcher, "preset": "standard", "evidence": None,
            "last_exit": None}


class RegistryStatusTest(unittest.TestCase):
    def test_no_record_is_stopped(self) -> None:
        _temp_registry(self)
        out = pc.status()
        self.assertFalse(out["running"])
        self.assertEqual(out["state"], "STOPPED")
        self.assertIsNone(out["pid"])
        self.assertIsNone(out["remaining_seconds"])

    def test_register_flows_running(self) -> None:
        _temp_registry(self)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            reg = pc.try_register(21600, launcher="agent")
        self.assertTrue(reg["registered"])
        out = pc.status()
        self.assertTrue(out["running"])
        self.assertEqual(out["state"], "RUNNING")
        self.assertEqual(out["pid"], os.getpid())
        self.assertEqual(out["mode"], "observe")
        self.assertEqual(out["duration_seconds"], 21600)
        self.assertEqual(out["launcher"], "agent")
        self.assertIsNotNone(out["remaining_seconds"])

    def test_continuous_has_null_remaining(self) -> None:
        _temp_registry(self)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            pc.try_register(None)
        out = pc.status()
        self.assertIsNone(out["duration_seconds"])
        self.assertIsNone(out["remaining_seconds"])

    def test_duplicate_registration_refused(self) -> None:
        path = _temp_registry(self)
        path.write_text(json.dumps(_record(pid=424242)), encoding="utf-8")
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            reg = pc.try_register(21600)
        self.assertFalse(reg.get("registered"))
        self.assertIn("already_running", reg)
        # Live record untouched by the refused registration.
        kept = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(kept["pid"], 424242)

    def test_stale_record_recovered_to_failed(self) -> None:
        path = _temp_registry(self)
        path.write_text(json.dumps(_record(pid=111)), encoding="utf-8")
        with mock.patch.object(pc, "is_canonical_pid", return_value=False):
            out = pc.status()
        self.assertFalse(out["running"])
        self.assertEqual(out["state"], "FAILED")
        kept = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(kept["state"], "FAILED")
        self.assertIn("terminated-externally",
                      kept["last_exit"]["reason"])

    def test_creation_mismatch_is_not_canonical(self) -> None:
        _temp_registry(self)
        with mock.patch("microstructure_probe.control.pid_is_ours",
                        return_value=False):
            self.assertFalse(pc.is_canonical_pid(_record()))
        with mock.patch("microstructure_probe.control.pid_is_ours",
                        return_value=True):
            self.assertTrue(pc.is_canonical_pid(_record()))

    def test_terminal_markers(self) -> None:
        _temp_registry(self)
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            pc.try_register(None)
        pc.mark_completed()
        self.assertEqual(pc.status()["state"], "COMPLETED")
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            pc.try_register(None)
        pc.mark_stopped("run-returned")
        st = pc.status()
        self.assertEqual(st["state"], "STOPPED")
        self.assertEqual(st["last_exit_reason"], "run-returned")
        with mock.patch.object(pc, "is_canonical_pid", return_value=True):
            pc.try_register(None)
        pc.mark_failed("boom")
        st = pc.status()
        self.assertEqual(st["state"], "FAILED")
        self.assertEqual(st["last_exit_reason"], "boom")

    def test_foreign_record_never_marked(self) -> None:
        path = _temp_registry(self)
        path.write_text(json.dumps(_record(pid=424242)), encoding="utf-8")
        pc.mark_completed()  # own pid differs: must not touch
        kept = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(kept["state"], "RUNNING")


class DurationValidationTest(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertIsNone(pc.validate_duration(None))
        self.assertIsNone(pc.validate_duration(""))
        self.assertEqual(pc.validate_duration(21600), 21600)
        self.assertEqual(pc.validate_duration("60"), 60)
        self.assertEqual(pc.validate_duration(86400), 86400)

    def test_invalid(self) -> None:
        for bad in (0, 59, 86401, -5, "abc", "1; rm -rf", [1], {"x": 1}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                pc.validate_duration(bad)


class StartStopTest(unittest.TestCase):
    def test_start_refused_when_running(self) -> None:
        _temp_registry(self)
        with mock.patch.object(pc, "status_readonly", return_value={
                "running": True, "state": "RUNNING", "pid": 7,
                "uptime_seconds": 10.0, "mode": "observe"}):
            with mock.patch.object(pc, "read_registry", return_value={
                    "state": "RUNNING", "pid": 7, "create_time": "STAMP"}):
                with mock.patch.object(pc, "is_canonical_pid",
                                       return_value=True):
                    with mock.patch("subprocess.Popen") as popen:
                        out = pc.start_probe(21600)
        popen.assert_not_called()
        self.assertTrue(out["already_running"])
        self.assertEqual(out["pid"], 7)

    def test_start_spawns_fixed_command_observe_only(self) -> None:
        _temp_registry(self)
        captured = {}

        class FakeProc:
            pid = 31337

        def fake_popen(argv, cwd=None, env=None, stdout=None, stderr=None,
                       **kwargs):
            captured.update(argv=argv, cwd=cwd, env=env, stdout=stdout,
                            stderr=stderr, kwargs=kwargs)
            return FakeProc()

        with mock.patch.object(pc, "status_readonly",
                               return_value={"running": False,
                                             "state": "STOPPED"}):
            with mock.patch("subprocess.Popen", side_effect=fake_popen):
                with mock.patch.object(pc, "own_creation_time",
                                       return_value="STAMP"):
                    with mock.patch.dict(os.environ, {"BOT_MODE": "live"}):
                        out = pc.start_probe(21600, launcher="dashboard")
        self.assertTrue(out["started"])
        self.assertEqual(out["pid"], 31337)
        # Fixed module invocation: no shell, no caller-supplied fragments.
        self.assertEqual(captured["argv"][:3],
                         [sys.executable, "-m", "microstructure_probe"])
        self.assertEqual(captured["argv"][3:], ["--duration", "21600"])
        self.assertEqual(captured["env"]["BOT_MODE"], "observe")
        self.assertEqual(captured["env"]["MICROPROBE_LAUNCHER"], "dashboard")
        # Merged UTF-8 file logging (never inherits the console).
        self.assertIs(captured["stderr"], __import__("subprocess").STDOUT)
        self.assertTrue(str(out["evidence"]["log"]).endswith(".log"))
        # P1-10R-FIX-01: spawned probe hides its console on Windows.
        import microstructure_probe.dashboard as _dash
        self.assertEqual(captured["kwargs"].get("creationflags"),
                         _dash.no_window_flags())
        pc._close_log_handles(31337)
        try:
            os.unlink(out["evidence"]["log"])
        except OSError:
            pass

    def test_stop_without_record(self) -> None:
        _temp_registry(self)
        out = pc.stop_probe()
        self.assertFalse(out["stopped"])
        self.assertEqual(out["error"], "no-active-probe")

    def test_stop_stale_recovers_without_kill(self) -> None:
        _temp_registry(self)
        path = Path(os.environ["MICROPROBE_RUNTIME_FILE"])
        path.write_text(json.dumps(_record(pid=111)), encoding="utf-8")
        with mock.patch.object(pc, "is_canonical_pid", return_value=False):
            with mock.patch.object(pc, "_terminate_verified_pid") as term:
                out = pc.stop_probe()
        term.assert_not_called()
        self.assertFalse(out["stopped"])
        self.assertEqual(pc.status()["state"], "FAILED")

    def test_stop_kills_only_verified_pid(self) -> None:
        _temp_registry(self)
        path = Path(os.environ["MICROPROBE_RUNTIME_FILE"])
        path.write_text(json.dumps(_record(pid=424242, created="STAMP")),
                        encoding="utf-8")
        killed = []
        alive = {"n": True}

        def fake_is_ours(pid, created):
            return alive["n"] and pid == 424242 and created == "STAMP"

        def fake_canonical(record):
            return alive["n"] and int(record.get("pid")) == 424242 \
                and record.get("create_time") == "STAMP"

        def fake_term(pid, *args):
            killed.append(pid)
            alive["n"] = False
            return True

        with mock.patch.object(pc, "is_canonical_pid",
                               side_effect=fake_canonical):
            with mock.patch.object(pc, "_terminate_verified_pid",
                                   side_effect=fake_term):
                with mock.patch("microstructure_probe.control.pid_is_ours",
                               side_effect=fake_is_ours):
                    out = pc.stop_probe(requester="dashboard")
        self.assertEqual(killed, [424242])
        self.assertTrue(out["stopped"])
        self.assertEqual(out["pid"], 424242)
        kept = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(kept["state"], "STOPPED")
        self.assertIn("dashboard", kept["last_exit"]["reason"])

    def test_stop_refuses_identity_changed_pid(self) -> None:
        # PID now belongs to something else (image/ctime mismatch):
        # terminate must never fire.
        _temp_registry(self)
        path = Path(os.environ["MICROPROBE_RUNTIME_FILE"])
        path.write_text(json.dumps(_record(pid=424242, created="STAMP")),
                        encoding="utf-8")
        with mock.patch.object(pc, "is_canonical_pid", return_value=False):
            with mock.patch.object(pc, "_terminate_verified_pid") as term:
                out = pc.stop_probe()
        term.assert_not_called()
        self.assertFalse(out["stopped"])


class ControlApiTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="probeapi_"))
        self.addCleanup(lambda: _rmtree(tmp))
        reg = tmp / "probe_runtime.json"
        os.environ["MICROPROBE_RUNTIME_FILE"] = str(reg)
        self.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
        from microstructure_probe.dashboard import DashboardServer
        from microstructure_probe.persistence import PersistenceStore
        live = PersistenceStore(db_path=tmp / "live.db")
        live.init_db()
        live.close()
        self.server = DashboardServer(host="127.0.0.1", port=0,
                                      db_path=tmp / "live.db").start()
        self.addCleanup(self.server.stop)
        self.base = f"http://127.0.0.1:{self.server.bound_port()}"
        body = self._raw_get("/overview")
        marker = "data-nonce='"
        self.nonce = body.split(marker)[1].split("'")[0]
        self.assertTrue(self.nonce)

    def _raw_get(self, path):
        with urllib.request.urlopen(self.base + path,
                                     timeout=15) as resp:
            return resp.read().decode("utf-8")

    def _api(self, method, path, payload=None, origin=None):
        data = json.dumps(payload or {}).encode()
        req = urllib.request.Request(self.base + path, data=data,
                                     method=method)
        req.add_header("Content-Type", "application/json")
        if origin is not None:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode() or "{}")

    def test_status_shape(self) -> None:
        with urllib.request.urlopen(self.base + "/api/control/probe/status",
                                     timeout=15) as resp:
            code, payload = resp.status, json.loads(resp.read().decode())
        self.assertEqual(code, 200)
        for key in ("running", "state", "pid", "started_at",
                    "uptime_seconds", "mode", "duration_seconds",
                    "elapsed_seconds", "remaining_seconds", "expected_end_at",
                    "launcher", "last_exit_code", "last_exit_reason",
                    "latest_snapshot_age", "feed_health"):
            self.assertIn(key, payload)
        self.assertEqual(payload["state"], "STOPPED")

    def test_get_mutation_rejected(self) -> None:
        for path in ("/api/control/probe/start", "/api/control/probe/stop"):
            try:
                urllib.request.urlopen(self.base + path, timeout=15)
                self.fail(f"expected 405 for GET {path}")
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 405, path)

    def test_post_requires_nonce(self) -> None:
        req = urllib.request.Request(
            self.base + "/api/control/probe/start",
            data=json.dumps({"mode": "continuous"}).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            urllib.request.urlopen(req, timeout=15)
            self.fail("expected 403")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 403)

    def test_post_rejects_bad_origin(self) -> None:
        code, _ = self._api("POST", "/api/control/probe/start",
                            {"nonce": self.nonce, "mode": "continuous"},
                            origin="http://evil.example/")
        self.assertEqual(code, 403)

    def test_post_validates_duration(self) -> None:
        for bad in ({"nonce": self.nonce, "duration_seconds": "abc"},
                    {"nonce": self.nonce, "duration_seconds": 10},
                    {"nonce": self.nonce, "preset": "rocket"}):
            code, _ = self._api("POST", "/api/control/probe/start", bad)
            self.assertEqual(code, 400, repr(bad))

    def test_start_stop_mapping(self) -> None:
        with mock.patch("microstructure_probe.control.start_probe",
                        return_value={"started": True, "pid": 5,
                                      "mode": "observe",
                                      "duration_seconds": None,
                                      "preset": "standard",
                                      "evidence": None}) as start:
            code, payload = self._api(
                "POST", "/api/control/probe/start",
                {"nonce": self.nonce, "mode": "continuous"})
            self.assertEqual(code, 200)
            self.assertTrue(payload["started"])
            _, kwargs = start.call_args
            self.assertEqual(kwargs.get("launcher"), "dashboard")
        with mock.patch("microstructure_probe.control.start_probe",
                        return_value={"started": False,
                                      "already_running": True, "pid": 5,
                                      "uptime_seconds": 3.0,
                                      "mode": "observe", "state": "RUNNING"}):
            code, payload = self._api(
                "POST", "/api/control/probe/start",
                {"nonce": self.nonce, "mode": "continuous"})
            self.assertEqual(code, 409)
            self.assertEqual(payload["error"], "already_running")
        with mock.patch("microstructure_probe.control.stop_probe",
                        return_value={"stopped": True, "pid": 5}):
            code, payload = self._api("POST", "/api/control/probe/stop",
                                      {"nonce": self.nonce})
            self.assertEqual(code, 200)
            self.assertTrue(payload["stopped"])
        with mock.patch("microstructure_probe.control.stop_probe",
                        return_value={"stopped": False,
                                      "error": "no-active-probe",
                                      "state": "STOPPED"}):
            code, _ = self._api("POST", "/api/control/probe/stop",
                                {"nonce": self.nonce})
            self.assertEqual(code, 404)

    def test_ui_renders_control_without_buttons(self) -> None:
        for path in ("/overview", "/movers", "/system"):
            body = self._raw_get(path)
            self.assertIn("MARKET ENGINE", body, path)
            self.assertIn("data-nonce=", body, path)
            self.assertNotIn("<button", body.lower(), path)
            self.assertNotIn("place_order", body.lower(), path)
        self.assertIn("/api/control/probe/status", body)


if __name__ == "__main__":
    unittest.main()
