from pathlib import Path
import ast,json,sqlite3
b=Path(r"C:\proyectos\binance-futures-microstructure-bot")
findings=[]
for p in (b/"tests").glob("test_*.py"):
 s=p.read_text(encoding="utf-8-sig")
 for i,l in enumerate(s.splitlines(),1):
  if "log_universe_event" in l or "PersistenceStore()" in l:findings.append({"file":p.name,"line":i,"text":l.strip()})
c=sqlite3.connect((b/"data/microprobe.db").as_uri()+"?mode=ro",uri=True)
rows=c.execute("SELECT * FROM universe_events ORDER BY id DESC LIMIT 15").fetchall()
cols=[r[1] for r in c.execute("pragma table_info(universe_events)")]
c.close()
result={"source_hits":findings,"latest_rows":[dict(zip(cols,r)) for r in rows]}
o=Path(r"C:\proyectos\binance-futures-dashboard-v2-worktree\design\qa\v2-71\isolation-audit.json")
o.write_bytes(json.dumps(result,indent=2).encode())
print(json.dumps(result,indent=2))
