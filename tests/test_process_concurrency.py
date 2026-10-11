"""P1-14B.8 V2-51: concurrency between independent process owners.

Thread tests share one PID, so lease-pid fencing cannot distinguish owners.
These tests use real spawned processes (distinct PIDs) with a hermetic temp
registry (MICROPROBE_RUNTIME_FILE inherited):

  M1  supervisor + sentinel owners heartbeat concurrently: every call
      effectively writes (counted via the bool return), both timestamps
      advance, distinctive 11/22 values survive, no silent failures, all
      workers exit 0.
  M2  four processes racing claim_supervision elect exactly one winner.
  M3  four processes racing claim_sentinel elect exactly one winner.

No live probe, no market I/O. Run: python run_tests.py
"""

from __future__ import annotations

import multiprocessing
import os
import queue as _queue
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _run_record(pid=424243, state="RUNNING"):
    return {"schema": 1, "writer": "control/1", "state": state,
            "pid": pid, "create_time": "STAMP",
            "started_at": "2026-10-10T10:00:00+00:00", "mode": "observe",
            "command": [sys.executable, "-m", "microstructure_probe"],
            "duration_seconds": 2100, "expected_end_at": None,
            "launcher": "agent", "preset": "standard",
            "evidence": {"dir": "ev", "log": "run.log"},
            "last_exit": None}


# ------------------------------------------------------------------
# Top-level workers (spawn pickling requires module-level functions).
# ------------------------------------------------------------------

def _sup_beat_worker(registry, out_queue, n):
    import os as _os
    _os.environ["MICROPROBE_RUNTIME_FILE"] = registry
    from unittest import mock as _mock
    from microstructure_probe import control as _pc
    try:
        with _mock.patch.object(_pc, "is_canonical_pid", return_value=True):
            claim = _pc.claim_supervision()
        if not claim.get("supervised"):
            out_queue.put({"role": "supervisor", "pid": _os.getpid(),
                           "claimed": False, "wrote": 0,
                           "errors": ["claim-refused"]})
            return
        wrote, errors = 0, []
        for _ in range(int(n)):
            try:
                ok = _pc._heartbeat_lease(
                    consecutive_failures=11,
                    streaks={"persistence": 1, "clock": 2, "db": 3})
                if ok:
                    wrote += 1
                else:
                    errors.append("refused-or-unavailable")
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
        out_queue.put({"role": "supervisor", "pid": _os.getpid(),
                       "claimed": True, "wrote": wrote, "errors": errors})
    except Exception as exc:  # noqa: BLE001 - reported, never silent
        try:
            out_queue.put({"role": "supervisor", "pid": _os.getpid(),
                           "claimed": False, "wrote": 0,
                           "errors": [repr(exc)]})
        except Exception:
            pass


def _sen_beat_worker(registry, out_queue, n):
    import os as _os
    _os.environ["MICROPROBE_RUNTIME_FILE"] = registry
    from unittest import mock as _mock
    from microstructure_probe import control as _pc
    try:
        with _mock.patch.object(_pc, "is_canonical_pid", return_value=True):
            claim = _pc.claim_sentinel()
        if not claim.get("watching"):
            out_queue.put({"role": "sentinel", "pid": _os.getpid(),
                           "claimed": False, "wrote": 0,
                           "errors": ["claim-refused"]})
            return
        wrote, errors = 0, []
        for _ in range(int(n)):
            try:
                ok = _pc._heartbeat_sentinel(
                    failures=22,
                    action={"rule": "none", "at": "t", "aborted": False})
                if ok:
                    wrote += 1
                else:
                    errors.append("refused-or-unavailable")
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
        out_queue.put({"role": "sentinel", "pid": _os.getpid(),
                       "claimed": True, "wrote": wrote, "errors": errors})
    except Exception as exc:  # noqa: BLE001
        try:
            out_queue.put({"role": "sentinel", "pid": _os.getpid(),
                           "claimed": False, "wrote": 0,
                           "errors": [repr(exc)]})
        except Exception:
            pass


def _sup_claim_worker(registry, out_queue, barrier):
    import os as _os
    _os.environ["MICROPROBE_RUNTIME_FILE"] = registry
    from unittest import mock as _mock
    from microstructure_probe import control as _pc
    # Rendezvous so all claimants race while every candidate is alive;
    # without it a late starter legitimately takes over an exited winner's
    # stale lease (takeover, not a mutual-exclusion failure).
    try:
        barrier.wait(timeout=120)
    except Exception as exc:  # noqa: BLE001
        try:
            out_queue.put({"pid": _os.getpid(), "winner": False,
                           "error": "enter-barrier: %r" % (exc,)})
        except Exception:
            pass
        return
    winner, error = False, None
    try:
        with _mock.patch.object(_pc, "is_canonical_pid", return_value=True):
            out = _pc.claim_supervision()
        winner = bool(out.get("supervised"))
    except Exception as exc:  # noqa: BLE001
        error = repr(exc)
    try:
        barrier.wait(timeout=120)
    except Exception:
        pass
    try:
        out_queue.put({"pid": _os.getpid(), "winner": winner, "error": error})
    except Exception:
        pass


def _sen_claim_worker(registry, out_queue, barrier):
    import os as _os
    _os.environ["MICROPROBE_RUNTIME_FILE"] = registry
    from unittest import mock as _mock
    from microstructure_probe import control as _pc
    try:
        barrier.wait(timeout=120)
    except Exception as exc:  # noqa: BLE001
        try:
            out_queue.put({"pid": _os.getpid(), "winner": False,
                           "error": "enter-barrier: %r" % (exc,)})
        except Exception:
            pass
        return
    winner, error = False, None
    try:
        with _mock.patch.object(_pc, "is_canonical_pid", return_value=True):
            out = _pc.claim_sentinel()
        winner = bool(out.get("watching"))
    except Exception as exc:  # noqa: BLE001
        error = repr(exc)
    try:
        barrier.wait(timeout=120)
    except Exception:
        pass
    try:
        out_queue.put({"pid": _os.getpid(), "winner": winner, "error": error})
    except Exception:
        pass


# ------------------------------------------------------------------
# Parent side.
# ------------------------------------------------------------------

def _spawn(ctx, target, *args):
    proc = ctx.Process(target=target, args=args)
    proc.start()
    return proc


def _drain(out_queue, count, timeout=120.0):
    results = []
    deadline = time.monotonic() + timeout
    while len(results) < count and time.monotonic() < deadline:
        try:
            results.append(out_queue.get(timeout=5.0))
        except _queue.Empty:
            continue
    return results


class ProcessHeartbeatTest(unittest.TestCase):
    def test_independent_owners_both_advance(self):
        from microstructure_probe import control as pc
        tmp = Path(tempfile.mkdtemp(prefix="mpbeat_"))
        self.addCleanup(lambda: _rmtree(tmp))
        registry = str(tmp / "probe_runtime.json")
        os.environ["MICROPROBE_RUNTIME_FILE"] = registry
        self.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
        pc._write_registry(_run_record())
        ctx = multiprocessing.get_context("spawn")
        out_queue = ctx.Queue()
        n = 10
        procs = [_spawn(ctx, _sup_beat_worker, registry, out_queue, n),
                 _spawn(ctx, _sen_beat_worker, registry, out_queue, n)]
        for p in procs:
            p.join(timeout=180)
        for p in procs:
            self.assertFalse(p.is_alive())
            self.assertEqual(p.exitcode, 0)
        results = _drain(out_queue, 2)
        self.assertEqual(len(results), 2)
        by_role = {r["role"]: r for r in results}
        for role in ("supervisor", "sentinel"):
            self.assertIn(role, by_role)
            self.assertTrue(by_role[role]["claimed"])
            # Every call effectively wrote: no refused/silent drops.
            self.assertEqual(by_role[role]["errors"], [])
            self.assertEqual(by_role[role]["wrote"], n)
        # Distinct process owners (and distinct from the parent).
        pids = {by_role["supervisor"]["pid"], by_role["sentinel"]["pid"]}
        self.assertEqual(len(pids), 2)
        self.assertNotIn(os.getpid(), pids)
        final = pc.read_registry()
        self.assertEqual(final.get("state"), "RUNNING")
        self.assertEqual(final["supervisor"]["consecutive_failures"], 11)
        self.assertEqual(final["supervisor"]["streaks"],
                         {"persistence": 1, "clock": 2, "db": 3})
        self.assertEqual(final["sentinel"]["consecutive_failures"], 22)
        self.assertEqual(final["sentinel"]["action"],
                         {"rule": "none", "at": "t", "aborted": False})
        self.assertEqual(final["supervisor"]["pid"], by_role["supervisor"]["pid"])
        self.assertEqual(final["sentinel"]["pid"], by_role["sentinel"]["pid"])


class ProcessClaimRaceTest(unittest.TestCase):
    def _race(self, worker, kind):
        from microstructure_probe import control as pc
        tmp = Path(tempfile.mkdtemp(prefix="mprace_"))
        self.addCleanup(lambda: _rmtree(tmp))
        registry = str(tmp / "probe_runtime.json")
        os.environ["MICROPROBE_RUNTIME_FILE"] = registry
        self.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
        pc._write_registry(_run_record())
        ctx = multiprocessing.get_context("spawn")
        out_queue = ctx.Queue()
        barrier = ctx.Barrier(4)
        procs = [_spawn(ctx, worker, registry, out_queue, barrier)
                 for _ in range(4)]
        for p in procs:
            p.join(timeout=240)
        for p in procs:
            self.assertFalse(p.is_alive())
            self.assertEqual(p.exitcode, 0)
        results = _drain(out_queue, 4)
        self.assertEqual(len(results), 4)
        self.assertEqual([r["error"] for r in results], [None] * 4)
        winners = [r for r in results if r["winner"]]
        # Exactly one winner among independent processes.
        self.assertEqual(len(winners), 1, results)
        self.assertEqual(len({r["pid"] for r in results}), 4)

    def test_supervisor_claims_single_winner_across_processes(self):
        self._race(_sup_claim_worker, "supervisor")

    def test_sentinel_claims_single_winner_across_processes(self):
        self._race(_sen_claim_worker, "sentinel")


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
