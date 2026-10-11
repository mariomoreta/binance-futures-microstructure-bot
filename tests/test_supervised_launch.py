"""Supervised transactional launch -- disabled preparation + contract.

Failing-first matrix (mocked spawns/processes, temp registries; no probe
launched, no Start enabled, no market I/O):

  D1  public entry refuses while disabled: no spawn, no registry file.
  D2  enabled flag delegates to the impl (patched).
  F1  full path: probe + supervisor + sentinel confirm together.
  F2  foreign live run pre-seeded: rejected before any spawn, bytes kept.
  F3  probe spawn failure: rejected, watchers never spawned.
  F4  supervisor spawn failure: rejected, probe rolled back.
  F5  sentinel spawn failure: rejected, probe+supervisor rolled back.
  L1  supervisor lease absent / stale / future / malformed / wrong-run:
      rejected, transaction rolled back.
  L2  dead watcher / reused watcher PID: rejected, rolled back.
  T1  leases never validate inside the budget: rejected on timeout.
  T2  verification/final registry unreadable: UNCERTAIN, pending assessment.
  T3  takeover/STOPPING interleave: rejected, foreign record preserved.
  T4  terminal record interleave: rejected, terminal preserved.
  U1  rollback kill refused: UNCERTAIN with pending evidence.
  U2  rollback kill not sticking: UNCERTAIN with pending evidence.
  C1  concurrent launches elect exactly one confirmation.
  C2  repeated launch while active: rejected, spawners untouched.
  P1  verification + rollback issue zero registry writes (strict mocks).

Confirmation is point-in-time only, never future protection. Provenance:
docs/SUPERVISED_LAUNCH_CONTRACT.md. Run: python run_tests.py
"""

from __future__ import annotations

import itertools
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc


def _temp_registry(testcase):
    tmp = Path(tempfile.mkdtemp(prefix="suplaunch_"))
    testcase.addCleanup(lambda: _rmtree(tmp))
    path = tmp / "probe_runtime.json"
    os.environ["MICROPROBE_RUNTIME_FILE"] = str(path)
    testcase.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
    return path, tmp


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


def _iso_age(seconds_ago):
    return datetime.fromtimestamp(time.time() - seconds_ago,
                                  tz=timezone.utc).isoformat()


def _iso_future(seconds_ahead):
    return datetime.fromtimestamp(time.time() + seconds_ahead,
                                  tz=timezone.utc).isoformat()


_UNSET_CTIME = object()


class _World:
    """Simulated OS processes: pid -> {ctime, alive, kill_calls}."""

    def __init__(self):
        self.procs = {}
        self._counter = itertools.count(1000)
        self.refuse_kill = set()
        self.stick_alive = set()

    def spawn(self, ctime=_UNSET_CTIME):
        # None is a legitimate ctime (indeterminable identity, as the real
        # own_creation_time() observes for simulated PIDs); only an
        # omitted argument takes the default.
        pid = next(self._counter)
        if ctime is _UNSET_CTIME:
            ctime = "C-%d" % pid
        self.procs[pid] = {"ctime": ctime,
                           "alive": True, "kill_calls": 0}
        return pid

    def kill(self, pid):
        entry = self.procs.get(pid)
        if entry is None:
            return
        entry["kill_calls"] += 1
        if pid not in self.stick_alive:
            entry["alive"] = False


def _identity(world):
    def _canonical(record):
        try:
            pid = int((record or {}).get("pid"))
        except (TypeError, ValueError):
            return False
        entry = world.procs.get(pid)
        return bool(entry and entry["alive"]
                    and (record or {}).get("create_time") == entry["ctime"])

    def _alive(pid, ctime):
        try:
            entry = world.procs.get(int(pid))
        except (TypeError, ValueError):
            return False
        return bool(entry and entry["alive"] and entry["ctime"] == ctime)

    def _terminate(pid, ctime):
        try:
            entry = world.procs.get(int(pid))
        except (TypeError, ValueError):
            return False
        if entry is None or entry["ctime"] != ctime or not entry["alive"]:
            return False
        if int(pid) in world.refuse_kill:
            return False
        world.kill(int(pid))
        return True

    def _ctime(pid):
        try:
            entry = world.procs.get(int(pid))
        except (TypeError, ValueError):
            return None
        return entry["ctime"] if entry else None

    def _state(pid, ctime):
        entry = world.procs.get(pid)
        if not entry or not entry["alive"]:
            return "gone"
        if ctime is None:
            return "unknown"
        return "owned" if entry["ctime"] == ctime else "replaced"

    return {"is_canonical": _canonical, "watcher_alive": _alive,
            "terminate": _terminate, "proc_ctime": _ctime,
            "process_state": _state, "read_record": pc.read_registry}


def _lease(pid, ctime, watched, age_s=5.0, state="ACTIVE"):
    base = {"pid": pid, "create_time": ctime,
            "started_at": _iso_age(300.0),
            "last_check_at": (_iso_age(age_s) if age_s != "bad"
                              else "not-a-timestamp"),
            "state": state, "consecutive_failures": 0,
            "watched_pid": watched}
    return base


class _FakeProc:
    def __init__(self, pid, world):
        self.pid = pid
        self._world = world

    def kill(self):
        self._world.kill(self.pid)


def _harness(testcase, world):
    """Wire a launch test: temp registry + world-backed patches.

    own_creation_time is world-backed so NO real tasklist/subprocess runs
    (a global Popen patch would otherwise hijack subprocess.run and spawn
    phantom probes mid-test).
    """
    path, tmp = _temp_registry(testcase)
    ident = _identity(world)

    def _ctime(pid=None):
        return world.procs.get(pid if pid is not None else os.getpid(),
                               {}).get("ctime")

    patches = [
        mock.patch.object(pc, "is_canonical_pid",
                          side_effect=ident["is_canonical"]),
        mock.patch("microstructure_probe.dashboard.pid_is_ours",
                   side_effect=lambda pid, ctime: ident["watcher_alive"](
                       pid, ctime)),
        mock.patch.object(pc, "own_creation_time", side_effect=_ctime),
    ]
    for p in patches:
        p.start()
        testcase.addCleanup(p.stop)
    return path, tmp, ident


def _probe_side_effect(world, ident):
    """Fake Popen: the child self-registers through REAL try_register.

    The patched creation-time query returns the world's captured identity;
    the successful transaction fixture requires a known ctime. A refused registration (lost race)
    is legitimate: the child would exit non-zero in reality, so just
    return the proc and let the parent's commit decide.
    """

    def _spawn(*args, **kwargs):
        pid = world.spawn()
        with mock.patch.object(pc.os, "getpid", return_value=pid):
            pc.try_register(duration_seconds=60, launcher="agent")
        return _FakeProc(pid, world)

    return _spawn


def _watcher_spawner(world, kind, overrides=None):
    """Fake watcher spawner; always publishes its lease immediately
    (simulating a fast claim), optionally with field overrides."""

    def _spawn(run_pid):
        pid = world.spawn()
        rec = pc.read_registry() or {}
        lease = _lease(pid, world.procs[pid]["ctime"], run_pid)
        if isinstance(overrides, dict):
            lease.update(overrides)
        rec[kind] = lease
        pc._write_registry(rec)
        return _FakeProc(pid, world)

    return _spawn


def _launch(testcase, world, **kw):
    path, tmp, ident = _harness(testcase, world)
    kw.setdefault("identity", ident)
    kw.setdefault("verify_budget_s", 5.0)
    kw.setdefault("poll_interval_s", 0.05)
    kw.setdefault("evidence_dir", str(tmp / "evidence"))
    with mock.patch.object(pc.subprocess, "Popen",
                           side_effect=_probe_side_effect(world, ident)):
        out = pc._launch_supervised_impl(duration_seconds=60, **kw)
    return out, path


class DisabledTest(unittest.TestCase):
    def test_refuses_without_side_effects(self):
        _temp_registry(self)
        spawner = mock.Mock(side_effect=AssertionError("must not spawn"))
        out = pc.launch_supervised_transaction(
            duration_seconds=60,
            spawners={"probe": spawner, "supervisor": spawner,
                      "sentinel": spawner})
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason"], "supervised-launch-disabled")
        spawner.assert_not_called()
        self.assertFalse(Path(os.environ["MICROPROBE_RUNTIME_FILE"]).exists())

    def test_enabled_delegates_to_impl(self):
        _temp_registry(self)
        sentinel = {"outcome": "rejected", "reason": "probe"}
        with mock.patch.object(pc, "SUPERVISED_LAUNCH_ENABLED", True):
            with mock.patch.object(pc, "_launch_supervised_impl",
                                   return_value=sentinel) as impl:
                out = pc.launch_supervised_transaction(duration_seconds=60)
        impl.assert_called_once()
        self.assertEqual(out, sentinel)


class FullPathTest(unittest.TestCase):
    def test_confirmed_together(self):
        world = _World()
        spawners = {"supervisor": _watcher_spawner(world, "supervisor"),
                    "sentinel": _watcher_spawner(world, "sentinel")}
        out, _ = _launch(self, world, spawners=spawners)
        self.assertEqual(out["outcome"], "confirmed")
        self.assertEqual(out["scope"],
                         "point-in-time confirmation, not future protection")
        self.assertTrue(out["watchers"]["supervisor"]["confirmed"])
        self.assertTrue(out["watchers"]["sentinel"]["confirmed"])
        self.assertEqual(out["rollback"], {"attempted": False, "cleaned": [],
                                           "pending": []})
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "RUNNING")
        self.assertTrue(all(world.procs[p]["alive"] for p in world.procs))


class PreconditionTest(unittest.TestCase):
    def test_foreign_live_run_rejected_before_spawn(self):
        import json
        world = _World()
        path, tmp = _temp_registry(self)
        # Seed foreign live RUNNING directly, then wire world identity.
        fpid = world.spawn()
        path.write_text(json.dumps(
            {"schema": 1, "writer": "control/1", "state": "RUNNING",
             "pid": fpid, "create_time": world.procs[fpid]["ctime"],
             "started_at": "2026-10-11T00:00:00+00:00", "mode": "observe",
             "command": [], "duration_seconds": 60, "expected_end_at": None,
             "launcher": "agent", "preset": "standard",
             "evidence": None, "last_exit": None}), encoding="utf-8")
        before = path.read_bytes()
        ident = _identity(world)
        canon = mock.patch.object(pc, "is_canonical_pid",
                                  side_effect=ident["is_canonical"])
        canon.start()
        self.addCleanup(canon.stop)
        spawner = mock.Mock(side_effect=AssertionError("must not spawn"))
        out = pc._launch_supervised_impl(
            duration_seconds=60, identity=ident, verify_budget_s=5.0,
            poll_interval_s=0.05, evidence_dir=str(tmp / "evidence"),
            spawners={"supervisor": spawner, "sentinel": spawner})
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason"], "already-running")
        spawner.assert_not_called()
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(world.procs[fpid]["alive"])

    def test_probe_spawn_failure_rejected(self):
        world = _World()
        path, tmp, ident = _harness(self, world)

        def _boom(*args, **kwargs):
            raise OSError("no fork")

        sup = mock.Mock(side_effect=AssertionError("must not spawn"))
        with mock.patch.object(pc.subprocess, "Popen", side_effect=_boom):
            out = pc._launch_supervised_impl(
                duration_seconds=60, identity=ident, verify_budget_s=5.0,
                poll_interval_s=0.05, evidence_dir=str(tmp / "evidence"),
                spawners={"supervisor": sup, "sentinel": sup})
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason"], "probe-spawn-failed")
        sup.assert_not_called()

    def test_supervisor_spawn_failure_rolls_back_probe(self):
        world = _World()

        def _boom(run_pid):
            raise OSError("no fork")

        sen = mock.Mock(side_effect=AssertionError("must not spawn"))
        spawners = {"supervisor": _boom, "sentinel": sen}
        out, _ = _launch(self, world, spawners=spawners)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason"], "supervisor-spawn-failed")
        sen.assert_not_called()
        self.assertTrue(out["rollback"]["attempted"])
        self.assertEqual(out["rollback"]["pending"], [])
        self.assertFalse(any(e["alive"] for e in world.procs.values()))

    def test_sentinel_spawn_failure_rolls_back_both(self):
        world = _World()

        def _boom(run_pid):
            raise OSError("no fork")

        spawners = {"supervisor": _watcher_spawner(world, "supervisor"),
                    "sentinel": _boom}
        out, _ = _launch(self, world, spawners=spawners)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason"], "sentinel-spawn-failed")
        self.assertEqual(out["rollback"]["pending"], [])
        self.assertFalse(any(e["alive"] for e in world.procs.values()))


class LeaseMatrixTest(unittest.TestCase):
    def _bad_lease_case(self, mutate):
        world = _World()

        def _sup(run_pid):
            pid = world.spawn()
            rec = pc.read_registry() or {}
            lease = _lease(pid, world.procs[pid]["ctime"], run_pid)
            mutate(world, lease, run_pid)
            rec["supervisor"] = lease
            pc._write_registry(rec)
            return _FakeProc(pid, world)

        spawners = {"supervisor": _sup,
                    "sentinel": _watcher_spawner(world, "sentinel")}
        out, _ = _launch(self, world, spawners=spawners)
        self.assertEqual(out["outcome"], "rejected")
        self.assertFalse(out["watchers"]["supervisor"]["confirmed"])
        self.assertEqual(out["rollback"]["pending"], [])
        self.assertFalse(any(e["alive"] for e in world.procs.values()))
        return out

    def test_absent_lease(self):
        world = _World()
        spawners = {"supervisor": lambda run_pid: _FakeProc(
            world.spawn(), world),
            "sentinel": _watcher_spawner(world, "sentinel")}
        out, _ = _launch(self, world, spawners=spawners,
                         verify_budget_s=0.3, poll_interval_s=0.02)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["rollback"]["pending"], [])

    def test_stale_lease(self):
        def _mut(world, lease, run):
            lease["last_check_at"] = _iso_age(9999.0)
        out = self._bad_lease_case(_mut)
        self.assertIn("lease", out["reason"])

    def test_future_lease(self):
        def _mut(world, lease, run):
            lease["last_check_at"] = _iso_future(60.0)
        out = self._bad_lease_case(_mut)
        self.assertIn("lease", out["reason"])

    def test_malformed_lease(self):
        def _mut(world, lease, run):
            lease["last_check_at"] = "not-a-timestamp"
        out = self._bad_lease_case(_mut)
        self.assertIn("lease", out["reason"])

    def test_wrong_run_lease(self):
        def _mut(world, lease, run):
            lease["watched_pid"] = 999999
        out = self._bad_lease_case(_mut)
        self.assertIn("lease", out["reason"])

    def test_dead_watcher(self):
        world = _World()

        def _sup(run_pid):
            pid = world.spawn()
            world.procs[pid]["alive"] = False
            rec = pc.read_registry() or {}
            rec["supervisor"] = _lease(pid, world.procs[pid]["ctime"],
                                       run_pid)
            pc._write_registry(rec)
            return _FakeProc(pid, world)

        spawners = {"supervisor": _sup,
                    "sentinel": _watcher_spawner(world, "sentinel")}
        out, _ = _launch(self, world, spawners=spawners)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["rollback"]["pending"], [])

    def test_reused_watcher_pid(self):
        world = _World()

        def _sup(run_pid):
            pid = world.spawn()
            rec = pc.read_registry() or {}
            rec["supervisor"] = _lease(pid, "OLD-CTIME", run_pid)
            pc._write_registry(rec)
            return _FakeProc(pid, world)

        spawners = {"supervisor": _sup,
                    "sentinel": _watcher_spawner(world, "sentinel")}
        out, _ = _launch(self, world, spawners=spawners)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["rollback"]["pending"], [])


class TimingInterleaveTest(unittest.TestCase):
    def test_verify_timeout(self):
        world = _World()
        spawners = {"supervisor": lambda run_pid: _FakeProc(
            world.spawn(), world),
            "sentinel": lambda run_pid: _FakeProc(world.spawn(), world)}
        out, _ = _launch(self, world, spawners=spawners,
                         verify_budget_s=0.2, poll_interval_s=0.02)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason"], "verify-timeout")
        self.assertGreaterEqual(out["verification"]["polls"], 1)
        self.assertEqual(out["rollback"]["pending"], [])
        self.assertFalse(any(e["alive"] for e in world.procs.values()))

    def test_unreadable_verification(self):
        world = _World()
        spawners = {"supervisor": _watcher_spawner(world, "supervisor"),
                    "sentinel": _watcher_spawner(world, "sentinel")}
        path, tmp, ident = _harness(self, world)
        # Setup phases (preflight + run establishment) read fine; every
        # verification poll fails.
        real_read = ident["read_record"]
        calls = {"n": 0}

        def _flaky():
            calls["n"] += 1
            if calls["n"] <= 2:
                return real_read()
            raise OSError("io")

        ident = dict(ident, read_record=_flaky)
        with mock.patch.object(pc.subprocess, "Popen",
                               side_effect=_probe_side_effect(world, ident)):
            out = pc._launch_supervised_impl(
                duration_seconds=60, identity=ident, verify_budget_s=0.3,
                poll_interval_s=0.02, evidence_dir=str(tmp / "evidence"),
                spawners=spawners)
        self.assertEqual(out["outcome"], "uncertain")
        self.assertIn(out["reason"], ("verify-timeout", "verify-unreadable"))
        self.assertTrue(any(p["reason"] == "final-registry-unreadable"
                            for p in out["rollback"]["pending"]))
        self.assertFalse(any(e["alive"] for e in world.procs.values()))

    def test_takeover_stopping_preserved(self):
        import json
        world = _World()

        def _sup(run_pid):
            return _FakeProc(world.spawn(), world)

        def _sen(run_pid):
            proc = _FakeProc(world.spawn(), world)
            take = pc.read_registry() or {}
            take["state"] = "STOPPING"
            take["stopping_by"] = "enforce:supervisor:999999"
            take["supervisor"] = {"pid": 999999, "state": "ACTIVE"}
            pc._write_registry(take)
            return proc

        spawners = {"supervisor": _sup, "sentinel": _sen}
        out, path = _launch(self, world, spawners=spawners)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn(out["reason"], ("takeover", "terminal-found",
                                      "run-replaced", "stale-run"))
        final = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(final.get("stopping_by"),
                         "enforce:supervisor:999999")
        self.assertFalse(any(e["alive"] for e in world.procs.values()))

    def test_terminal_record_preserved(self):
        import json
        world = _World()

        def _sup(run_pid):
            return _FakeProc(world.spawn(), world)

        def _sen(run_pid):
            proc = _FakeProc(world.spawn(), world)
            take = pc.read_registry() or {}
            take["state"] = "ABORTED"
            take["abort_reason"] = "keep-me"
            pc._write_registry(take)
            return proc

        spawners = {"supervisor": _sup, "sentinel": _sen}
        out, path = _launch(self, world, spawners=spawners)
        self.assertEqual(out["outcome"], "rejected")
        final = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(final.get("state"), "ABORTED")
        self.assertEqual(final.get("abort_reason"), "keep-me")


class RollbackUncertainTest(unittest.TestCase):
    def test_kill_refused_is_uncertain(self):
        world = _World()

        def _sup(run_pid):
            pid = world.spawn()
            rec = pc.read_registry() or {}
            rec["supervisor"] = _lease(pid, world.procs[pid]["ctime"],
                                       run_pid, age_s=9999.0)
            pc._write_registry(rec)
            world.refuse_kill.add(pid)
            return _FakeProc(pid, world)

        spawners = {"supervisor": _sup,
                    "sentinel": _watcher_spawner(world, "sentinel")}
        out, _ = _launch(self, world, spawners=spawners)
        self.assertEqual(out["outcome"], "uncertain")
        pending_roles = [p["role"] for p in out["rollback"]["pending"]]
        self.assertIn("supervisor", pending_roles)
        self.assertTrue(world.procs[
            out["rollback"]["pending"][0]["pid"]]["alive"])

    def test_kill_not_sticking_is_uncertain(self):
        world = _World()

        def _sup(run_pid):
            pid = world.spawn()
            rec = pc.read_registry() or {}
            rec["supervisor"] = _lease(pid, world.procs[pid]["ctime"],
                                       run_pid, age_s=9999.0)
            pc._write_registry(rec)
            world.stick_alive.add(pid)
            return _FakeProc(pid, world)

        spawners = {"supervisor": _sup,
                    "sentinel": _watcher_spawner(world, "sentinel")}
        out, _ = _launch(self, world, spawners=spawners)
        self.assertEqual(out["outcome"], "uncertain")
        self.assertTrue(any(p["role"] == "supervisor"
                            for p in out["rollback"]["pending"]))


class ConcurrencyRepeatTest(unittest.TestCase):
    def test_concurrent_launches_elect_one_confirmation(self):
        # Parent-first spawns (no getpid patching: two threads must not
        # share one global os.getpid override). The locked STARTING commit
        # serializes the race; watchers only spawn for the committer.
        # A SINGLE parent-held Popen patch covers both threads: nesting one
        # global patch per thread leaks the mock process-wide when the
        # exits interleave (later suites would inherit a fake Popen).
        world = _World()
        path, tmp, ident = _harness(self, world)
        outcomes = []
        spawners = {"supervisor": _watcher_spawner(world, "supervisor"),
                    "sentinel": _watcher_spawner(world, "sentinel")}

        def _plain_spawn(*args, **kwargs):
            return _FakeProc(world.spawn(), world)

        def _one():
            outcomes.append(pc._launch_supervised_impl(
                duration_seconds=60, identity=ident, verify_budget_s=5.0,
                poll_interval_s=0.02,
                evidence_dir=str(tmp / "evidence"), spawners=spawners))

        threads = [threading.Thread(target=_one) for _ in range(2)]
        with mock.patch.object(pc.subprocess, "Popen",
                               side_effect=_plain_spawn):
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=120)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(len(outcomes), 2)
        confirmed = [o for o in outcomes if o["outcome"] == "confirmed"]
        rejected = [o for o in outcomes if o["outcome"] == "rejected"]
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(len(rejected), 1)

    def test_repeated_launch_rejected(self):
        world = _World()
        spawners = {"supervisor": _watcher_spawner(world, "supervisor"),
                    "sentinel": _watcher_spawner(world, "sentinel")}
        first, path = _launch(self, world, spawners=spawners)
        self.assertEqual(first["outcome"], "confirmed")
        # The first harness stays alive (cleanup at test end), so the
        # registry still holds the live run: reuse its directory/file.
        calls = {"sup": 0, "sen": 0}
        orig_sup, orig_sen = spawners["supervisor"], spawners["sentinel"]

        def _count_sup(run_pid):
            calls["sup"] += 1
            return orig_sup(run_pid)

        def _count_sen(run_pid):
            calls["sen"] += 1
            return orig_sen(run_pid)

        before = path.read_bytes()
        ident = _identity(world)
        canon = mock.patch.object(pc, "is_canonical_pid",
                                  side_effect=ident["is_canonical"])
        canon.start()
        self.addCleanup(canon.stop)
        tmp = Path(tempfile.mkdtemp(prefix="suplaunch2_"))
        self.addCleanup(lambda: _rmtree(tmp))
        out = pc._launch_supervised_impl(
            duration_seconds=60, identity=ident, verify_budget_s=5.0,
            poll_interval_s=0.02, evidence_dir=str(tmp / "evidence"),
            spawners={"supervisor": _count_sup, "sentinel": _count_sen})
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason"], "already-running")
        self.assertEqual(calls, {"sup": 0, "sen": 0})
        self.assertEqual(path.read_bytes(), before)


class PurityTest(unittest.TestCase):
    def test_verify_and_rollback_issue_no_writes(self):
        world = _World()
        path, _, ident = _harness(self, world)
        pid = world.spawn()
        rec = {"schema": 1, "writer": "control/1", "state": "RUNNING",
               "pid": pid, "create_time": world.procs[pid]["ctime"],
               "started_at": "2026-10-11T00:00:00+00:00", "mode": "observe",
               "command": [], "duration_seconds": 60, "expected_end_at": None,
               "launcher": "agent", "preset": "standard",
               "evidence": None, "last_exit": None,
               "supervisor": _lease(pid, world.procs[pid]["ctime"], pid),
               "sentinel": _lease(pid, world.procs[pid]["ctime"], pid)}
        pc._write_registry(rec)
        strict = mock.Mock(side_effect=AssertionError("registry write"))
        with mock.patch.object(pc, "_write_registry", strict):
            with mock.patch.object(pc, "update_registry", strict):
                for _ in range(3):
                    pc._verify_launch_state(
                        dict(rec),
                        {"pid": pid,
                         "create_time": world.procs[pid]["ctime"]},
                        {"supervisor": {"pid": pid,
                                        "create_time":
                                        world.procs[pid]["ctime"]},
                         "sentinel": {"pid": pid,
                                      "create_time":
                                      world.procs[pid]["ctime"]}},
                        ident)
                pc._rollback_transaction(
                    [("sentinel", pid, world.procs[pid]["ctime"]),
                     ("supervisor", pid, world.procs[pid]["ctime"])],
                    ident)
