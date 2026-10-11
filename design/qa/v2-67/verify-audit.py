from pathlib import Path
import sqlite3,json,urllib.request,hashlib
root=Path(r'C:\proyectos\binance-futures-dashboard-v2-worktree')
b=Path(r'C:\proyectos\binance-futures-microstructure-bot')
p=b/'data/historical/historical.db'
r={'historical_path':str(p),'exists':p.exists()}
if p.exists():
 db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
 r['schema']=list(db.execute('SELECT key,value FROM history_meta'))
 r['counts']={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ['historical_coverage','historical_klines','historical_mark_klines','event_instances','event_outcomes']}
 db.row_factory=sqlite3.Row
 r['coverage_rows']=[dict(x) for x in db.execute('SELECT * FROM historical_coverage ORDER BY symbol,interval,source LIMIT 25')]
 r['event_definition_counts']=[dict(x) for x in db.execute('SELECT definition_name,definition_version,COUNT(*) n FROM event_instances GROUP BY definition_name,definition_version')]
 db.close()
reg=b/'logs/probe_runtime.json'
before=reg.read_bytes() if reg.exists() else None
with urllib.request.urlopen('http://127.0.0.1:3020/api/v1/runtime',timeout=15) as response:r['runtime']=json.load(response)
after=reg.read_bytes() if reg.exists() else None
r['registry_unchanged']=before==after
r['registry_sha256']=hashlib.sha256(after).hexdigest() if after else None
(root/'design/qa/v2-67/source-audit.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
print(json.dumps(r,indent=2))
