from pathlib import Path
import urllib.request,urllib.error,json,sqlite3,hashlib,math
root=Path(r'C:\proyectos\binance-futures-dashboard-v2-worktree');b=Path(r'C:\proyectos\binance-futures-microstructure-bot');dbfile=b/'data/historical/historical.db';reg=b/'logs/probe_runtime.json'
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [dbfile,reg,b/'data/microprobe.db']}
def get(path):
 try:
  with urllib.request.urlopen('http://127.0.0.1:3020'+path,timeout=15) as r:return r.status,dict(r.headers),r.read()
 except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read()
results=[]
for query in ['', '?symbol=BTCUSDT', '?symbol=ORCAUSDT', '?symbol=BTCUSDT&definition=EXTENDED_GAINER', '?symbol=ZZZNODATAUSDT', '?definition=INVALID', '?symbol=%27DROP', '?symbol=BTCUSDT&symbol=ETHUSDT']:
 status,headers,raw=get('/api/v1/historical-coverage'+query);data=json.loads(raw);assert 'no-store' in {k.lower():v for k,v in headers.items()}.get('cache-control','')
 expected=400 if 'INVALID' in query or 'DROP' in query or 'symbol=ETHUSDT' in query else 200;assert status==expected,(query,status,data)
 if status==200:
  assert data['source']=='HISTORICAL_SQLITE_READONLY' and data['historical_schema_version']==2
  assert len(data['events'])<=50 and len(data['coverage'])<=500
  if 'ZZZNODATA' in query:assert data['coverage']==data['studies']==data['events']==[]
  elif 'symbol=' not in query:assert data['counts']=={'contract_bars':17270,'mark_bars':2157,'events':2831,'outcomes':16986}
  elif 'BTCUSDT' in query:assert all(x['symbol']=='BTCUSDT' for x in data['coverage']+data['events'])
 results.append({'query':query,'status':status,'counts':data.get('counts'),'coverage_rows':len(data.get('coverage',[])),'study_rows':len(data.get('studies',[])),'event_rows':len(data.get('events',[]))})
 if query=='':(root/'design/qa/v2-68/actual-history.json').write_text(json.dumps(data,indent=2),encoding='utf-8');sample=data
con=sqlite3.connect(dbfile.as_uri()+'?mode=ro',uri=True)
for s in sample['studies']:
 expected=con.execute('SELECT COUNT(*),SUM(o.usable_for_statistics),COUNT(o.forward_return),AVG(o.forward_return) FROM event_outcomes o JOIN event_instances e ON e.event_id=o.event_id WHERE e.definition_name=? AND e.definition_version=1 AND o.horizon=?',(s['definition'],s['horizon'])).fetchone()
 assert tuple(s[x] for x in ['n_total','n_usable','n_with_return'])==expected[:3]
 assert (s['mean_forward_return'] is None and expected[3] is None) or (s['mean_forward_return'] is not None and expected[3] is not None and math.isclose(s['mean_forward_return'],expected[3],rel_tol=1e-12,abs_tol=1e-14))
con.close()
after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [dbfile,reg,b/'data/microprobe.db']};assert before==after
(root/'design/qa/v2-68/http-results.json').write_text(json.dumps({'checks':results,'native_aggregate_parity':True,'source_hashes_before':before,'source_hashes_after':after,'unchanged':True},indent=2),encoding='utf-8')
print(json.dumps(results,indent=2));print('SQL aggregates match; both DBs and registry unchanged')
