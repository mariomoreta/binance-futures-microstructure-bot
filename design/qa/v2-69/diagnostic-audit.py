from pathlib import Path
import sqlite3,json,urllib.request,hashlib
b=Path(r"C:\proyectos\binance-futures-microstructure-bot")
f=Path(r"C:\proyectos\binance-futures-dashboard-v2-worktree")
db=b/"data/microprobe.db"
reg=b/"logs/probe_runtime.json"
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [db,reg]}
c=sqlite3.connect(db.as_uri()+"?mode=ro",uri=True)
cols=[r[1] for r in c.execute("pragma table_info(telemetry_snapshots)")]
r=c.execute("select * from telemetry_snapshots order by id desc limit 1").fetchone()
obj=dict(zip(cols,r)) if r else {}
for k,v in list(obj.items()):
 if k.endswith("_json"):
  try:obj[k]=json.loads(v)
  except (ValueError,TypeError):pass
c.close()
runtime=json.load(urllib.request.urlopen("http://127.0.0.1:3020/api/v1/runtime"))
page=urllib.request.urlopen("http://127.0.0.1:3020/system").read().decode()
after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [db,reg]}
result={"snapshot_columns":cols,"latest_snapshot":obj,"runtime":runtime,"system_http":200,"bytes_unchanged":before==after,"system_pending_labels":{s:s in page for s in ["NOT CONNECTED","Host resources","NO EVENT FEED"]},"audit_limits":"source/HTTP audit, not new browser or liveness verification"}
(f/"design/qa/v2-69/diagnostic-audit.json").write_bytes(json.dumps(result,indent=2).encode())
print(json.dumps({"columns":cols,"snapshot_fields":{k:list(v) if isinstance(v,dict) else str(v)[:100] for k,v in obj.items()},"bytes_unchanged":before==after},indent=2))
