from pathlib import Path
import subprocess,time,json
root=Path(r'C:\proyectos\binance-futures-dashboard-v2-worktree');q=root/'design/qa/v2-68';q.mkdir(parents=True,exist_ok=True);results=[]
for name,cmd,cwd in [('frontend-tests',['npm.cmd','test','--','--run'],root/'frontend'),('typecheck',['npm.cmd','run','typecheck'],root/'frontend'),('lint',['npm.cmd','run','lint'],root/'frontend'),('build',['npm.cmd','run','build'],root/'frontend'),('python-tests',['python','run_tests.py'],root)]:
 start=time.monotonic()
 with (q/(name+'.log')).open('w',encoding='utf-8') as f:code=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT).returncode
 results.append({'check':name,'exit':code,'seconds':round(time.monotonic()-start,3)});(q/'verification.json').write_bytes(json.dumps(results,indent=2).encode('utf-8'));print(name,code,flush=True)
 if code:raise SystemExit(code)
