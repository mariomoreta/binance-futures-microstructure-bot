from pathlib import Path
import os,sys,unittest,types,json,tempfile,subprocess
from unittest import mock
b=Path(r"C:\proyectos\binance-futures-microstructure-bot")
f=Path(r"C:\proyectos\binance-futures-dashboard-v2-worktree")
sys.path[:0]=[str(b/"src"),str(b/"tests")];os.chdir(b)
from microstructure_probe.persistence import PersistenceStore
p=b/"tests/test_universe_probe.py"
original=subprocess.check_output(["git","show","HEAD:tests/test_universe_probe.py"],cwd=b).decode("utf-8-sig")
m=types.ModuleType("isolation_before");m.__file__=str(p);exec(compile(original,str(p),"exec"),m.__dict__)
with tempfile.TemporaryDirectory() as t:
 store=PersistenceStore(Path(t)/"negative-control.db");store.init_db()
 with mock.patch("microstructure_probe.probe.get_persistence_store",return_value=store) as default:
  r=unittest.TestResult();unittest.defaultTestLoader.loadTestsFromTestCase(m.HotSyncTest).run(r);assert r.wasSuccessful()
  before={"default_factory_calls":default.call_count,"temporary_universe_rows":len(store.universe_events(limit=500))}
 store.close()
m=types.ModuleType("isolation_after");m.__file__=str(p);exec(compile(p.read_text(encoding="utf-8-sig"),str(p),"exec"),m.__dict__)
with mock.patch("microstructure_probe.probe.get_persistence_store",side_effect=AssertionError("canonical store forbidden")) as default:
 r=unittest.TestResult();unittest.defaultTestLoader.loadTestsFromModule(m).run(r);assert r.wasSuccessful(),(r.failures,r.errors)
 after={"tests":r.testsRun,"default_factory_calls":default.call_count,"failures":len(r.failures),"errors":len(r.errors)}
assert before["default_factory_calls"]>0 and before["temporary_universe_rows"]==3 and after["default_factory_calls"]==0
(f/"design/qa/v2-71/isolation-negative-control.json").write_bytes(json.dumps({"before":before,"after":after,"canonical_not_used_in_control":True},indent=2).encode())
print(before,after)
