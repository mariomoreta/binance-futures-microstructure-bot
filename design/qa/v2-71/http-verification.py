from pathlib import Path
import hashlib,json,urllib.request,sqlite3,time
f=Path(r"C:\proyectos\binance-futures-dashboard-v2-worktree")
b=Path(r"C:\proyectos\binance-futures-microstructure-bot")
paths=[b/"data/microprobe.db",b/"data/historical/historical.db",b/"logs/probe_runtime.json"]
hashes=lambda:{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
before=hashes()
def get(url):
 with urllib.request.urlopen("http://127.0.0.1:3020"+url,timeout=20) as response:return response.status,dict(response.headers),response.read()
status,headers,body=get("/api/v1/system-evidence")
d=json.loads(body)
assert status==200 and d["available"] and d["schema_version"]==1
assert next(v for k,v in headers.items() if k.lower()=="cache-control")=="no-store"
c=sqlite3.connect((b/"data/microprobe.db").as_uri()+"?mode=ro",uri=True)
expected={"setups":c.execute("select count(*) from prospective_setups").fetchone()[0],"outcomes":c.execute("select count(*) from prospective_outcomes").fetchone()[0],"complete_outcomes":c.execute("select count(*) from prospective_outcomes where outcome_state='COMPLETE'").fetchone()[0],"opportunity_events":c.execute("select count(*) from opportunity_events").fetchone()[0],"state_transitions":c.execute("select count(*) from state_transitions").fetchone()[0],"universe_events":c.execute("select count(*) from universe_events").fetchone()[0]}
assert all(d["research"][k]==v for k,v in expected.items())
assert sum(x["count"] for x in d["classifier"]["states"])==c.execute("select count(*) from state_features").fetchone()[0]
assert sum(x["count"] for x in d["opportunities"]["lifecycles"])==c.execute("select count(*) from opportunity_candidates").fetchone()[0]
discovery=c.execute("select updated_ms,payload_json from discovery_snapshots where id=0").fetchone()
j=json.loads(discovery[1]);assert d["universe"]["core"]==len(set(j["core"])) and d["universe"]["hot_dynamic"]==len(set(j["hot_dynamic"]))
c.close()
cases=[]
for url in ["/system","/overview","/movers","/opportunities","/historical-research","/historical-research/coverage","/api/v1/runtime","/api/v1/runtime/readiness"]:
 code,h,payload=get(url);assert code==200;cases.append({"url":url,"status":code})
after=hashes();assert after==before
result={"status":status,"headers":headers,"system_data":d,"research_sql_counts":expected,"routes":cases,"hashes_before":before,"hashes_after":after,"bytes_unchanged":True}
(f/"design/qa/v2-71/http-verification.json").write_bytes(json.dumps(result,indent=2).encode())
print(json.dumps({"research":expected,"universe":d["universe"],"classifier":d["classifier"],"opportunities":d["opportunities"],"bytes_unchanged":True},indent=2))
