"""DASH-V2-61: deterministic exact-archive launch review; no real processes."""
import argparse
import hashlib
import copy
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument("--archive", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
root = Path(args.archive)
expected_hash = '52beb68842da2777129e6594cfe5c083cb87c8328343b4dc840c58d974dd5088'
assert hashlib.sha256((root / 'src/microstructure_probe/control.py').read_bytes()).hexdigest() == expected_hash, 'Not the reviewed control source'
sys.path[:0] = [str(root / "src"), str(root)]
from microstructure_probe import control as pc
from microstructure_probe import dashboard

findings = {}
def record(pid=100, leases=True):
    result = {"state": "RUNNING", "pid": pid, "create_time": "c" + str(pid),
              "evidence": {"log": "mock-only.log"}}
    if leases:
        for kind, wp in (("supervisor", 201), ("sentinel", 202)):
            result[kind] = {"state": "ACTIVE", "pid": wp, "create_time": "c" + str(wp),
                            "watched_pid": pid,
                            "last_check_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}
    return result

def launch(records, fail_spawn=False, budget=0, interval=0, clock=None):
    queue = iter(records)
    alive = {100: True, 999: True, 201: True, 202: True}
    killed, spawned = [], []
    def read():
        item = next(queue)
        if isinstance(item, Exception):
            raise item
        return copy.deepcopy(item)
    def terminate(pid, ctime):
        killed.append(pid)
        alive[pid] = False
        return True
    def spawn(kind, pid):
        spawned.append({"role": kind, "watched_pid": pid})
        if fail_spawn:
            raise OSError("injected")
        return SimpleNamespace(pid=201 if kind == "supervisor" else 202)
    identity = {"read_record": read, "is_canonical": lambda r: True,
                "watcher_alive": lambda pid, ct: alive.get(pid, False),
                "terminate": terminate, "proc_ctime": lambda pid: "c" + str(pid)}
    with patch.object(pc, "start_probe", return_value={"started": True, "pid": 100}), \
         patch.object(pc.subprocess, "Popen", side_effect=AssertionError("real Popen forbidden")):
        if clock:
            with patch.object(pc.time, "monotonic", side_effect=lambda: clock["now"]), \
                 patch.object(pc.time, "sleep", side_effect=lambda dt: clock.update(
                     now=clock["now"] + dt, sleeps=clock["sleeps"] + [dt])):
                result = pc._launch_supervised_impl(identity=identity,
                    spawners={k: (lambda pid, kind=k: spawn(kind, pid)) for k in ("supervisor", "sentinel")},
                    verify_budget_s=budget, poll_interval_s=interval)
        else:
            result = pc._launch_supervised_impl(identity=identity,
                spawners={k: (lambda pid, kind=k: spawn(kind, pid)) for k in ("supervisor", "sentinel")},
                verify_budget_s=budget, poll_interval_s=interval)
    return {"result": result, "mock_kills": killed, "mock_spawns": spawned,
            "own_child_alive": alive[100], "foreign_alive": alive[999]}

# Public disabled guard: all side effects forbidden.
with patch.object(pc, "_launch_supervised_impl", side_effect=AssertionError("implementation reached")):
    disabled = pc.launch_supervised_transaction()
assert disabled["reason"] == "supervised-launch-disabled"
findings["disabled_guard"] = {"passes": True, "result": disabled}

foreign = launch([None, record(999)], fail_spawn=True)
assert 999 in foreign["mock_kills"] and foreign["own_child_alive"]
findings["R1_foreign_rollback"] = foreign
foreign_confirm = launch([None, record(999), record(999)])
assert foreign_confirm["result"]["outcome"] == "confirmed"
assert foreign_confirm["result"]["run"]["pid"] != 100
findings["R1_foreign_confirmation"] = foreign_confirm

watchers = {k: {"pid": wp, "create_time": "c" + str(wp)}
            for k, wp in (("supervisor", 201), ("sentinel", 202))}
calls = []
def losing_identity(pid, ctime):
    calls.append(pid)
    return len(calls) <= 2
ok, detail = pc._verify_launch_state(record(), {"pid": 100, "create_time": "c100"},
                                    watchers, {"is_canonical": lambda r: True,
                                               "watcher_alive": losing_identity})
assert ok and len(calls) == 4 and detail["supervisor_age_s"] is None
findings["R2_ignored_second_check"] = {"confirmed": ok, "detail": detail, "checks": calls}

with tempfile.TemporaryDirectory() as td:
    argv = []
    def popen(command, **kwargs):
        argv.extend(command)
        return SimpleNamespace(pid=777777)
    with patch.object(dashboard, "repo_root", return_value=Path(td)), \
         patch.object(dashboard, "no_window_flags", return_value=0), \
         patch.object(pc.subprocess, "Popen", side_effect=popen):
        pc._default_watcher_spawner("supervisor")(100)
    pc._LOG_HANDLES.pop(777777).close()
source = (root / "src/microstructure_probe/control.py").read_text(encoding="utf-8")
assert argv[3] == "supervisor" and 'sub.add_parser("supervise"' in source
assert 'sub.add_parser("supervisor"' not in source
findings["R3_wrong_default_command"] = {"argv": argv, "expected_subcommand": "supervise",
                                       "real_processes": 0}

clock = {"now": 0.0, "sleeps": []}
late = launch([None, record(leases=False), record(leases=False), record()],
              budget=0.1, interval=10, clock=clock)
assert late["result"]["outcome"] == "confirmed" and clock["now"] > 0.1
findings["R4_confirmed_after_deadline"] = {"execution": late, "fake_clock": clock,
                                        "budget_s": 0.1}
infinite = launch([None, record(), record()], budget=float("inf"))
assert infinite["result"]["outcome"] == "confirmed"
# JSON stays strict: replace non-finite internal response with characterization.
findings["R4_nonfinite_budget"] = {"accepted": True, "outcome": "confirmed",
                                 "budget_argument": "Infinity", "spawn_count": len(infinite["mock_spawns"])}

unreadable = launch([None, record(leases=False), OSError("unreadable")])
assert unreadable["result"]["outcome"] == "rejected"
findings["R5_unreadable_final_rejected"] = unreadable

r = record()
r["supervisor"]["last_check_at"] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
future_ok, future_detail = pc._verify_watcher_lease(r, "supervisor", 201, "c201", 100,
                                                   lambda pid, ct: True)
assert future_ok and future_detail["age_s"] < 0
findings["C1_future_tolerance"] = {"accepted": future_ok, "detail": future_detail,
    "scope": "New launch contract accepts up to 5s future; reconcile with prior strict freshness."}
out = {"backend_sha": "da231b911e9b1a0cfe86b3aaa3325e5b71928687",
       "real_processes_spawned": 0, "real_terminations": 0,
       "registry_writes": 0, "findings": findings,
       "meaning": "Defects reproduced, not acceptance tests passing."}
path = Path(args.output)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps({"reproductions": len(findings), "output": str(path), "real_processes": 0}))
