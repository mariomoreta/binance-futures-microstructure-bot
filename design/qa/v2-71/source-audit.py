from pathlib import Path
import sqlite3,json,subprocess
f=Path(r"C:\proyectos\binance-futures-dashboard-v2-worktree")
b=Path(r"C:\proyectos\binance-futures-microstructure-bot")
out=f/"design/qa/v2-71";out.mkdir(parents=True,exist_ok=True)
c=sqlite3.connect((b/"data/microprobe.db").as_uri()+"?mode=ro",uri=True)
tables=[r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")]
data={}
for t in tables:
 if t not in ["discovery_snapshots","research_status","prospective_status","opportunity_candidates","universe_events","state_features","telemetry_snapshots","db_metadata","metadata","research_events"]:continue
 cols=[r[1] for r in c.execute('pragma table_info('+t+')')]
 rows=c.execute('select * from '+t+' limit 2').fetchall()
 objs=[]
 for row in rows:
  obj=dict(zip(cols,row))
  for k,v in list(obj.items()):
   if k.endswith("_json"):
    try:obj[k]=json.loads(v)
    except (ValueError,TypeError):pass
  objs.append(obj)
 data[t]={"columns":cols,"rows":objs,"count":c.execute("select count(*) from "+t).fetchone()[0]}
c.close()
(out/"source-audit.json").write_bytes(json.dumps({"tables":tables,"sources":data},indent=2,ensure_ascii=False).encode())
print(json.dumps({"tables":tables,"sources":data},ensure_ascii=False,indent=2)[:22000])
print("BACKEND_HEAD",subprocess.check_output(["git","rev-parse","HEAD"],cwd=b,text=True).strip())
