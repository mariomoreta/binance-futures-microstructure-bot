"""V2-62: deterministic launch ownership/budget/uncertainty regressions."""
import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from microstructure_probe import control as pc
from microstructure_probe import dashboard

def rec(pid=100, leases=True, ctime=None, state="RUNNING"):
    r = {"pid": pid, "create_time": ctime or "c" + str(pid), "state": state,
         "evidence": {"log": "fake.log"}}
    if leases:
        for role, wp in (("supervisor", 201), ("sentinel", 202)):
            r[role] = {"pid": wp, "create_time": "c" + str(wp), "watched_pid": pid,
                       "state": "ACTIVE", "last_check_at":
                       (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
    return r

class LaunchCorrectionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = mock.patch.dict(os.environ, MICROPROBE_RUNTIME_FILE=str(Path(self.tmp.name)/"run.json"))
        self.env.start()
        self.addCleanup(self.env.stop)
        self.alive = {100: True, 999: True, 201: True, 202: True}
        self.ctime = {p: "c"+str(p) for p in self.alive}
        self.kills, self.spawns, self.starts, self.reads = [], [], [], 0
        self.guard = mock.patch.object(pc.subprocess, "Popen", side_effect=AssertionError("real spawn"))
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def state(self, pid, ct):
        if not self.alive.get(pid): return "gone"
        if ct is None: return "unknown"
        return "owned" if self.ctime[pid] == ct else "replaced"

    def execute(self, records, fail_spawn=False, budget=1, interval=0, clock=None, evidence=None):
        queue = list(records)
        def read():
            self.reads += 1
            item = queue.pop(0) if len(queue)>1 else queue[0]
            if isinstance(item, Exception): raise item
            return copy.deepcopy(item)
        def kill(pid, ct):
            self.kills.append(pid)
            self.alive[pid] = False
            return True
        def start(*args, **kwargs):
            self.starts.append(True)
            capture = kwargs.get("_on_spawn")
            if capture: capture(SimpleNamespace(pid=100), "c100")
            return {"started": True, "pid": 100}
        def spawn(role, watched):
            self.spawns.append((role, watched))
            if fail_spawn: raise OSError("injected")
            return SimpleNamespace(pid=201 if role=="supervisor" else 202)
        ident = {"read_record": read, "is_canonical": lambda r: self.state(r["pid"],r["create_time"])=="owned",
                 "watcher_alive": lambda pid, ct: self.state(pid,ct)=="owned",
                 "process_state": self.state, "terminate": kill,
                 "proc_ctime": lambda pid: self.ctime[pid]}
        with mock.patch.object(pc, "start_probe", side_effect=start):
            if clock is None:
                return pc._launch_supervised_impl(identity=ident, verify_budget_s=budget,
                    poll_interval_s=interval, evidence_dir=evidence or self.tmp.name,
                    spawners={k:(lambda pid, kind=k:spawn(kind,pid)) for k in ("supervisor","sentinel")})
            def sleep(dt):
                clock["sleeps"].append(dt)
                clock["now"] += dt
            with mock.patch.object(pc.time,"monotonic",side_effect=lambda:clock["now"]), \
                 mock.patch.object(pc.time,"sleep",side_effect=sleep):
                return pc._launch_supervised_impl(identity=ident,verify_budget_s=budget,
                    poll_interval_s=interval,evidence_dir=self.tmp.name,
                    spawners={k:(lambda pid,kind=k:spawn(kind,pid)) for k in ("supervisor","sentinel")})

    def test_foreign_post_start_cannot_confirm(self):
        out=self.execute([None,rec(999),rec(999)])
        self.assertNotEqual(out["outcome"],"confirmed")
        self.assertEqual(self.spawns,[])
        self.assertNotIn(999,self.kills)
        self.assertIn(100,self.kills)

    def test_foreign_post_start_cannot_be_rolled_back(self):
        self.execute([None,rec(999)],fail_spawn=True)
        self.assertNotIn(999,self.kills)
        self.assertFalse(self.alive[100])
        self.assertTrue(self.alive[999])

    def test_same_pid_changed_ctime_not_adopted(self):
        out=self.execute([None,rec(100,ctime="other"),rec(100,ctime="other")])
        self.assertNotEqual(out["outcome"],"confirmed")
        self.assertEqual(self.spawns,[])
        self.assertEqual(out["run"]["create_time"],"c100")

    def test_stopping_before_watchers_not_spawned(self):
        self.execute([None,rec(state="STOPPING")])
        self.assertEqual(self.spawns,[])

    def test_terminal_before_watchers_owned_child_cleanup(self):
        self.execute([None,rec(state="COMPLETED")])
        self.assertFalse(self.alive[100])
        self.assertEqual(self.spawns,[])

    def test_one_verifier_result_per_watcher(self):
        calls=[]
        def alive(pid,ct):
            calls.append(pid)
            return len(calls)<=2
        ok,detail=pc._verify_launch_state(rec(),{"pid":100,"create_time":"c100"},
            {k:{"pid":p,"create_time":"c"+str(p)} for k,p in (("supervisor",201),("sentinel",202))},
            {"is_canonical":lambda r:True,"watcher_alive":alive})
        self.assertTrue(ok)
        self.assertEqual(calls,[201,202])
        self.assertIsNotNone(detail["supervisor_age_s"])

    def test_default_supervisor_command(self):
        seen=[]
        with mock.patch.object(dashboard,"repo_root",return_value=Path(self.tmp.name)), \
             mock.patch.object(dashboard,"no_window_flags",return_value=0), \
             mock.patch.object(pc.subprocess,"Popen",side_effect=lambda argv,**kw:(seen.append(argv) or SimpleNamespace(pid=700))):
            pc._default_watcher_spawner("supervisor")(100)
        pc._LOG_HANDLES.pop(700).close()
        self.assertEqual(seen[0][3],"supervise")

    def test_sleep_clamped_and_no_late_confirmation(self):
        clock={"now":0.0,"sleeps":[]}
        out=self.execute([None,rec(leases=False),rec(leases=False),rec()],budget=.1,interval=10,clock=clock)
        self.assertNotEqual(out["outcome"],"confirmed")
        self.assertLessEqual(sum(clock["sleeps"]),.1)

    def test_expired_read_cannot_confirm(self):
        clock={"now":0.0}
        records=[None,rec(),rec()]
        calls=0
        def read():
            nonlocal calls
            calls+=1
            if calls>=3:clock["now"]=2.0
            return records[min(calls-1,2)]
        def start(*args,**kwargs):
            if kwargs.get("_on_spawn"):kwargs["_on_spawn"](SimpleNamespace(pid=100),"c100")
            return {"started":True,"pid":100}
        ident={"read_record":read,"is_canonical":lambda r:True,"watcher_alive":lambda p,c:True,
               "process_state":lambda p,c:"gone","proc_ctime":lambda p:"c"+str(p),"terminate":lambda p,c:True}
        with mock.patch.object(pc,"start_probe",side_effect=start),mock.patch.object(pc.time,"monotonic",side_effect=lambda:clock["now"]):
            out=pc._launch_supervised_impl(identity=ident,verify_budget_s=1,evidence_dir=self.tmp.name,
                spawners={"supervisor":lambda p:SimpleNamespace(pid=201),"sentinel":lambda p:SimpleNamespace(pid=202)})
        self.assertNotEqual(out["outcome"],"confirmed")

    def test_invalid_numeric_inputs_before_effects(self):
        for value in (float("inf"),float("nan"),-1,0,"bad",True):
            with self.subTest(budget=repr(value)):
                self.starts.clear()
                out=self.execute([None,rec(),rec()],budget=value)
                self.assertEqual(out["outcome"],"rejected")
                self.assertEqual(self.starts,[])
        for value in (float("inf"),float("nan"),-1,"bad",True):
            with self.subTest(interval=repr(value)):
                self.starts.clear()
                out=self.execute([None,rec(),rec()],interval=value)
                self.assertEqual(out["outcome"],"rejected")
                self.assertEqual(self.starts,[])

    def test_final_unreadable_is_uncertain(self):
        out=self.execute([None,rec(leases=False),OSError("unreadable")],budget=.001)
        self.assertEqual(out["outcome"],"uncertain")
        self.assertTrue(any(p["reason"]=="final-registry-unreadable" for p in out["rollback"]["pending"]))

    def test_identity_mismatch_not_proved_dead(self):
        killed=[]
        result=pc._rollback_transaction([("probe",100,"old")],
            {"watcher_alive":lambda p,c:False,"process_state":lambda p,c:"replaced",
             "terminate":lambda p,c:killed.append(p)})
        self.assertEqual(killed,[])
        self.assertTrue(result["pending"])
        self.assertEqual(result["cleaned"],[])

    def test_unknown_identity_not_terminated(self):
        killed=[]
        result=pc._rollback_transaction([("probe",100,None)],
            {"watcher_alive":lambda p,c:True,"process_state":lambda p,c:"unknown",
             "terminate":lambda p,c:killed.append(p)})
        self.assertEqual(killed,[])
        self.assertTrue(result["pending"])

    def test_gone_is_cleaned_without_kill(self):
        kill=mock.Mock()
        result=pc._rollback_transaction([("probe",100,"c100")],
            {"watcher_alive":lambda p,c:False,"process_state":lambda p,c:"gone","terminate":kill})
        kill.assert_not_called()
        self.assertFalse(result["pending"])

    def test_positive_future_timestamp_rejected(self):
        r=rec()
        r["supervisor"]["last_check_at"]=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        ok,_=pc._verify_watcher_lease(r,"supervisor",201,"c201",100,lambda p,c:True)
        self.assertFalse(ok)

    def test_lock_preflight_failure_before_spawn(self):
        with mock.patch.object(pc,"_locked_registry",side_effect=OSError("locked")):
            out=self.execute([None,rec(),rec()])
        self.assertEqual(out["outcome"],"rejected")
        self.assertEqual(self.starts,[])

    def test_evidence_preflight_failure_before_spawn(self):
        bad=Path(self.tmp.name)/"file"
        bad.write_text("preserve")
        out=self.execute([None,rec(),rec()],evidence=str(bad))
        self.assertEqual(out["outcome"],"rejected")
        self.assertEqual(self.starts,[])
        self.assertEqual(bad.read_text(),"preserve")

    def test_missing_spawn_ctime_not_confirmed(self):
        records=[None,rec(),rec()]
        def start(*args,**kwargs):
            if kwargs.get("_on_spawn"):kwargs["_on_spawn"](SimpleNamespace(pid=100),None)
            return {"started":True,"pid":100}
        with mock.patch.object(pc,"start_probe",side_effect=start):
            out=pc._launch_supervised_impl(identity={"read_record":mock.Mock(side_effect=records),
                "is_canonical":lambda r:True,"watcher_alive":lambda p,c:True,
                "process_state":lambda p,c:"unknown","proc_ctime":lambda p:None,"terminate":mock.Mock()},
                evidence_dir=self.tmp.name,verify_budget_s=.001,
                spawners={"supervisor":lambda p:SimpleNamespace(pid=201),"sentinel":lambda p:SimpleNamespace(pid=202)})
        self.assertNotEqual(out["outcome"],"confirmed")
        self.assertEqual(out["outcome"],"uncertain")

    def test_foreign_registry_bytes_preserved(self):
        path=Path(os.environ["MICROPROBE_RUNTIME_FILE"])
        original=b'{"state":"ABORTED","pid":999,"abort_reason":"preserve"}'
        path.write_bytes(original)
        strict=mock.Mock(side_effect=AssertionError("registry write"))
        with mock.patch.object(pc,"update_registry",strict),mock.patch.object(pc,"_write_registry",strict):
            self.execute([None,rec(999),rec(999)])
        self.assertEqual(path.read_bytes(),original)
        self.assertNotIn(999,self.kills)

    def test_full_path_still_confirms(self):
        out=self.execute([None,rec(),rec()])
        self.assertEqual(out["outcome"],"confirmed")
        self.assertEqual(self.kills,[])
        self.assertEqual(out["verification"]["polls"],1)
        self.assertIsNotNone(out["verification"]["supervisor_age_s"])

    def test_deadline_expires_during_identity_callbacks(self):
        clock={"now":0.0}
        def alive(pid,ct):
            clock["now"]=2.0
            return True
        def start(*args,**kwargs):
            kwargs["_on_spawn"](SimpleNamespace(pid=100),"c100")
            return {"started":True,"pid":100}
        read=mock.Mock(side_effect=[None,rec(),rec(),rec()])
        with mock.patch.object(pc,"start_probe",side_effect=start),mock.patch.object(pc.time,"monotonic",side_effect=lambda:clock["now"]):
            out=pc._launch_supervised_impl(identity={"read_record":read,"is_canonical":lambda r:True,
                "watcher_alive":alive,"process_state":lambda p,c:"gone" if clock["now"] else "owned",
                "proc_ctime":lambda p:"c"+str(p),"terminate":mock.Mock()},verify_budget_s=1,evidence_dir=self.tmp.name,
                spawners={"supervisor":lambda p:SimpleNamespace(pid=201),"sentinel":lambda p:SimpleNamespace(pid=202)})
        self.assertNotEqual(out["outcome"],"confirmed")
