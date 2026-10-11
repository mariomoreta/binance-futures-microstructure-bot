from pathlib import Path
import subprocess,json,time,urllib.request,hashlib,sqlite3
root=Path(r'C:\proyectos\binance-futures-dashboard-v2-worktree')
backend=Path(r'C:\proyectos\binance-futures-microstructure-bot')
out=root/'design/qa/v2-67';out.mkdir(parents=True,exist_ok=True)
r={'backend_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip(),'frontend_base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()}
r['get_checks']=[]
for route in ['/api/v1/runtime','/api/v1/runtime/readiness','/api/v1/price-series/BTCUSDT?range=24h','/search?q=BTC','/api/v1/historical-research']:
 try:
  with urllib.request.urlopen('http://127.0.0.1:3020'+route,timeout=15) as response:
   data=response.read();entry={'route':route,'status':response.status,'bytes':len(data)}
   if 'json' in response.headers.get('Content-Type',''):
    payload=json.loads(data);entry['keys']=list(payload) if isinstance(payload,dict) else []
    entry['schema_version']=payload.get('schema_version') if isinstance(payload,dict) else None
   r['get_checks'].append(entry)
 except Exception as e:r['get_checks'].append({'route':route,'error':str(e)})
r['databases']=[]
for path in (backend/'data').glob('*.db'):
 db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
 tables=[x[0] for x in db.execute("select name from sqlite_master where type='table'")]
 r['databases'].append({'file':path.name,'tables':tables})
 db.close()
start=time.monotonic()
with (out/'backend-tests.log').open('w',encoding='utf-8') as log:
 p=subprocess.run(['python','run_tests.py'],cwd=backend,stdout=log,stderr=subprocess.STDOUT)
r['canonical_tests']={'exit_code':p.returncode,'elapsed_seconds':round(time.monotonic()-start,3)}
(out/'review-evidence.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
print(json.dumps(r,indent=2))
