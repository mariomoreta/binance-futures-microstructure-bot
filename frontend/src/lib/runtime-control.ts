import {spawnSync} from "node:child_process";
const ROOT="C:/proyectos/binance-futures-microstructure-bot";
const PY="python";
export type RuntimeState={running:boolean;state:string;pid:number|null;launcher:string|null;mode:string;uptime_seconds:number|null;duration_seconds:number|null;started_at:string|null;feed_health:string;latest_snapshot_age:number|null;supervisor?:{state?:string;watched_pid?:number|null;run_id?:string|null;last_check_at?:string|null;abort_triggered?:boolean;abort_reason?:string|null;abort_rule?:string|null};error?:string};
function execute(code:string):{ok:boolean;data:Record<string,unknown>}{
 const p=spawnSync(PY,["-c",code],{cwd:ROOT,encoding:"utf8",timeout:4200,maxBuffer:262144,windowsHide:true,env:{...process.env,PYTHONPATH:ROOT+"/src"}});
 if(p.error||!p.stdout?.trim())return {ok:false,data:{error:"CANONICAL_CONTROLLER_UNAVAILABLE"}};
 try{const value=JSON.parse(p.stdout) as Record<string,unknown>;return {ok:p.status===0,data:value}}catch{return {ok:false,data:{error:"INVALID_CONTROLLER_RESPONSE"}}}
}
const statusCode="import json;from microstructure_probe import control;print(json.dumps(control.status()))";
export function runtimeStatus():RuntimeState{
 const r=execute(statusCode);
 if(!r.ok)return {running:false,state:"UNKNOWN",pid:null,launcher:null,mode:"observe",uptime_seconds:null,duration_seconds:null,started_at:null,feed_health:"UNKNOWN",latest_snapshot_age:null,supervisor:{state:"SUPERVISOR_UNKNOWN"},error:String(r.data.error)};
 const x=r.data;
 return {running:x.running===true,state:String(x.state??"UNKNOWN"),pid:typeof x.pid==="number"?x.pid:null,launcher:typeof x.launcher==="string"?x.launcher:null,mode:String(x.mode??"observe"),uptime_seconds:typeof x.uptime_seconds==="number"?x.uptime_seconds:null,duration_seconds:typeof x.duration_seconds==="number"?x.duration_seconds:null,started_at:typeof x.started_at==="string"?x.started_at:null,feed_health:"UNKNOWN",latest_snapshot_age:null,supervisor:x.supervisor&&typeof x.supervisor==="object"?x.supervisor as RuntimeState["supervisor"]:{state:"SUPERVISOR_UNKNOWN"}};
}
export function runtimeAction(kind:"start"|"stop"){
 const code=kind==="start"?
 "import json;from microstructure_probe import control;s=control.status();r={'error':'already_running','state':s.get('state')} if s.get('running') or s.get('state') in ('STARTING','STOPPING','UNKNOWN') else control.start_probe(2100,launcher='dashboard',preset='standard');print(json.dumps(r))":
 "import json;from microstructure_probe import control;s=control.status();r={'error':'not_dashboard_owned','launcher':s.get('launcher')} if not s.get('running') or s.get('launcher')!='dashboard' else control.stop_probe(requester='dashboard-v2');print(json.dumps(r))";
 return execute(code);
}
export function requestAllowed(req:Request){
 const origin=req.headers.get("origin"),host=req.headers.get("host");
 return origin==="http://127.0.0.1:3020"&&host==="127.0.0.1:3020"&&req.headers.get("x-v2-action")==="observe-only"&&req.headers.get("sec-fetch-site")!=="cross-site";
}
