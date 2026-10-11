from pathlib import Path
import ast,subprocess,sys,json,hashlib,urllib.request
backend=Path(r'C:\proyectos\binance-futures-microstructure-bot');root=Path(r'C:\proyectos\binance-futures-dashboard-v2-worktree');q=root/'design/qa/v2-69';q.mkdir(parents=True,exist_ok=True)
old=subprocess.check_output(['git','show','5dedacb:src/microstructure_probe/dashboard.py'],cwd=backend,text=True,encoding='utf-8')
new=(backend/'src/microstructure_probe/host_process.py').read_text(encoding='utf-8')
names=['repo_root','no_window_flags','process_info','_creation_time_ctypes','pid_is_ours']
def functions(s):return {n.name:ast.get_source_segment(s,n) for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)}
a,b=functions(old),functions(new)
r={'backend_initial':subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip(),'helper_source_identical':{n:a[n]==b[n] for n in names}}
assert all(r['helper_source_identical'].values())
legacy="import sys\nclass Block:\n def find_module(self,name,path=None):\n  if name=='microstructure_probe.dashboard':return self\n def load_module(self,name):raise ImportError('blocked HTTP module')\nsys.meta_path.insert(0,Block())\nsys.path.insert(0,"+repr(str(backend/'src'))+")\nimport microstructure_probe.dashboard\nprint('HTTP_IMPORT_ALLOWED')\n"
p=subprocess.run(['python','-c',legacy],capture_output=True,text=True,cwd=backend)
r['legacy_blocker_negative_control']={'exit':p.returncode,'stdout':p.stdout.strip(),'stderr':p.stderr[-1200:]}
modern="import sys,importlib.abc,importlib\nclass Block(importlib.abc.MetaPathFinder):\n def find_spec(self,name,path=None,target=None):\n  if name=='microstructure_probe.dashboard':raise ImportError('blocked HTTP module')\nsys.meta_path.insert(0,Block())\nsys.path.insert(0,"+repr(str(backend/'src'))+")\ntry:importlib.import_module('microstructure_probe.dashboard')\nexcept ImportError as e:assert 'blocked HTTP module' in str(e)\nelse:raise AssertionError('blocker ineffective')\nfrom microstructure_probe import control,host_process\ncontrol.own_creation_time()\nassert host_process.repo_root()==__import__('pathlib').Path("+repr(str(backend))+")\nassert 'microstructure_probe.dashboard' not in sys.modules\nprint('BLOCK_VERIFIED_AND_CONTROL_ISOLATED')\n"
p=subprocess.run(['python','-c',modern],capture_output=True,text=True,cwd=backend)
r['modern_blocker_control']={'exit':p.returncode,'stdout':p.stdout.strip(),'stderr':p.stderr[-1200:]};assert p.returncode==0
reg=backend/'logs/probe_runtime.json';before=reg.read_bytes();r['get_checks']=[]
for route in ['/api/v1/runtime','/api/v1/runtime/readiness','/api/v1/historical-coverage?symbol=ORCAUSDT','/api/v1/price-series/BTCUSDT?range=24h']:
 with urllib.request.urlopen('http://127.0.0.1:3020'+route,timeout=15) as res:r['get_checks'].append({'route':route,'status':res.status,'keys':list(json.load(res))})
r['registry_unchanged']=before==reg.read_bytes();assert r['registry_unchanged']
(q/'extraction-review.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r,indent=2))
