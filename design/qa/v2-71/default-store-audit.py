from pathlib import Path
import sys,os,unittest,json,traceback,sqlite3
from unittest import mock
b=Path(r"C:\proyectos\binance-futures-microstructure-bot");f=Path(r"C:\proyectos\binance-futures-dashboard-v2-worktree")
sys.path[:0]=[str(b/"src"),str(b/"tests")];os.chdir(b)
from microstructure_probe import probe
hits=[]
def forbidden(*a,**k):
 hits.append(traceback.format_stack(limit=8))
 raise AssertionError("default persistence forbidden in audit")
suite=unittest.defaultTestLoader.discover(str(b/"tests"),pattern="test_*.py")
def flatten(s):
 for t in s:
  if isinstance(t,unittest.TestSuite):yield from flatten(t)
  else:yield t
selected=unittest.TestSuite(t for t in flatten(suite) if not t.id().startswith(("test_persistence.","test_prospective.","test_research_recorder.")))
with mock.patch.object(probe,"get_persistence_store",side_effect=forbidden):
 r=unittest.TestResult();selected.run(r)
out={"tests":r.testsRun,"hits":hits,"failures":[(str(t),e) for t,e in r.failures],"errors":[(str(t),e) for t,e in r.errors]}
(f/"design/qa/v2-71/default-store-audit.json").write_bytes(json.dumps(out,indent=2).encode())
print(json.dumps(out,indent=2))
