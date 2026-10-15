import {spawnSync} from "node:child_process";
import {normalizeWatcher, type WatcherEvidence} from "./supervision";
const ROOT="C:/proyectos/binance-futures-microstructure-bot";
const PY="python";
// Separate spawn budgets per operation (2026-10-14, review: one 4200ms
// budget for everything made start ambiguous). Status is a pure read;
// stop is a bounded verified kill; start must cover the canonical
// 60s verification budget (SUPERVISED_LAUNCH_VERIFY_BUDGET_S) plus spawn
// margin. A start that still exceeds its budget NEVER reports plain
// failure: it reconciles via a status read and returns
// START_TIMEOUT_UNCERTAIN with retry-before-respawn discipline.
export const STATUS_BUDGET_MS=4200;
export const STOP_BUDGET_MS=8000;
export const START_BUDGET_MS=65000;
export type RuntimeState={running:boolean;state:string;pid:number|null;launcher:string|null;mode:string;uptime_seconds:number|null;duration_seconds:number|null;started_at:string|null;feed_health:string;latest_snapshot_age:number|null;observed_at?:string;supervisor?:WatcherEvidence;sentinel?:WatcherEvidence;error?:string;run_id?:string|null;expected_end_at?:string|null;elapsed_seconds?:number|null;remaining_seconds?:number|null;last_exit_code?:number|null;last_exit_reason?:string|null;last_exit_at?:string|null;process_state?:string;process_verified?:boolean;preset?:string|null};
// Project-owned launchers (canonical control.py): agent CLI, dashboard V2
// and direct terminal self-registration. Any other launcher value is
// treated as foreign and never offered a V2 stop. Backend stop_probe
// remains the authority: it terminates only the verified canonical PID.
export const PROJECT_LAUNCHERS=["dashboard","agent","direct"] as const;
export function isProjectLauncher(v:unknown):boolean{return typeof v==="string"&&(PROJECT_LAUNCHERS as readonly string[]).includes(v)}
function timedOut(p:{error?:unknown}):boolean{
 const code=(p.error as {code?:unknown}|null|undefined)?.code;
 if(code==="ETIMEDOUT")return true;
 const msg=(p.error as {message?:unknown}|null|undefined)?.message;
 return typeof msg==="string"&&/timed out/i.test(msg);
}
function execute(code:string,timeoutMs:number):{ok:boolean;data:Record<string,unknown>;timeout:boolean}{
 const p=spawnSync(PY,["-c",code],{cwd:ROOT,encoding:"utf8",timeout:timeoutMs,maxBuffer:262144,windowsHide:true,env:{...process.env,PYTHONPATH:ROOT+"/src"}});
 if(timedOut(p))return {ok:false,data:{error:"CANONICAL_CONTROLLER_TIMEOUT"},timeout:true};
 if(p.error||!p.stdout?.trim())return {ok:false,data:{error:"CANONICAL_CONTROLLER_UNAVAILABLE"},timeout:false};
 try{
  const value:unknown=JSON.parse(p.stdout);
  if(!value||typeof value!=="object"||Array.isArray(value))return {ok:false,data:{error:"INVALID_CONTROLLER_RESPONSE"},timeout:false};
  return {ok:p.status===0,data:value as Record<string,unknown>,timeout:false};
 }catch{return {ok:false,data:{error:"INVALID_CONTROLLER_RESPONSE"},timeout:false}}
}
const pureStatusCode="import json;from microstructure_probe import control;f=getattr(control,'status_readonly',None);s=f() if callable(f) else {'error':'READ_ONLY_STATUS_REQUIRED'};";
const statusCode=pureStatusCode+"print(json.dumps(s))";
const num=(v:unknown):number|null=>typeof v==="number"&&Number.isFinite(v)?v:null;
const txt=(v:unknown):string|null=>typeof v==="string"&&v.trim()?v:null;
function feedFromStore():{feed_health:string;latest_snapshot_age:number|null}{
 try{
  const {historicalRead}=require("@/lib/historical-db") as typeof import("@/lib/historical-db");
  return historicalRead(db=>{
   let row:{timestamp:number;data_quality_json:string}|undefined;
   try{row=db.prepare("SELECT timestamp,data_quality_json FROM telemetry_snapshots ORDER BY id DESC LIMIT 1").get() as typeof row;}
   catch{return {feed_health:"UNKNOWN",latest_snapshot_age:null}}
   if(!row||typeof row.timestamp!=="number"||!Number.isFinite(row.timestamp))return {feed_health:"UNKNOWN",latest_snapshot_age:null};
   const age=Math.round(Date.now()/1000-row.timestamp);
   if(!Number.isFinite(age)||age<0)return {feed_health:"UNKNOWN",latest_snapshot_age:null};
   if(age>120)return {feed_health:"STALE",latest_snapshot_age:age};
   // Fresh snapshot: distinguish HEALTHY vs DEGRADED from recorded quality.
   try{
    const q=JSON.parse(String(row.data_quality_json??"null")) as Record<string,unknown>;
    const stale=Array.isArray(q.staleStreams)?q.staleStreams.length:0;
    const reconn=q.reconnections&&typeof q.reconnections==="object"?Object.values(q.reconnections as Record<string,unknown>).reduce<number>((a,v)=>a+(typeof v==="number"?v:0),0):0;
    const msgs=q.messagesByStream&&typeof q.messagesByStream==="object"?Object.values(q.messagesByStream as Record<string,unknown>).reduce<number>((a,v)=>a+(typeof v==="number"?v:0),0):0;
    const rej=typeof q.timestampRejected==="number"?q.timestampRejected:0;
    const rate=msgs>0?rej/msgs:0;
    if(stale>0||reconn>0||rate>0.5)return {feed_health:"DEGRADED",latest_snapshot_age:age};
   }catch{}
   return {feed_health:"HEALTHY",latest_snapshot_age:age};
  });
 }catch{return {feed_health:"UNKNOWN",latest_snapshot_age:null}}
}
export function runtimeStatus():RuntimeState{
 const r=execute(statusCode,STATUS_BUDGET_MS);
 if(!r.ok||typeof r.data.error==="string")return {running:false,state:"UNKNOWN",pid:null,launcher:null,mode:"UNKNOWN",uptime_seconds:null,duration_seconds:null,started_at:null,feed_health:"UNKNOWN",latest_snapshot_age:null,observed_at:new Date().toISOString(),supervisor:normalizeWatcher(null,"supervisor"),sentinel:normalizeWatcher(null,"sentinel"),run_id:null,expected_end_at:null,elapsed_seconds:null,remaining_seconds:null,last_exit_code:null,last_exit_reason:null,last_exit_at:null,process_state:"unknown",process_verified:false,preset:null,error:typeof r.data.error==="string"?r.data.error:"CANONICAL_CONTROLLER_UNAVAILABLE"};
 const x=r.data;
 // Feed: canonical controller is registry-only (UNKNOWN without a dashboard
 // feed provider). Enrich best-effort from the recorded telemetry snapshot;
 // never masks a controller error and never invents liveness.
 let feed_health=typeof x.feed_health==="string"&&x.feed_health.trim()?x.feed_health:"UNKNOWN";
 let latest_snapshot_age=num(x.latest_snapshot_age);
 if(feed_health==="UNKNOWN"&&latest_snapshot_age===null){
  const f=feedFromStore();
  feed_health=f.feed_health;latest_snapshot_age=f.latest_snapshot_age;
 }
 return {running:x.running===true,state:typeof x.running==="boolean"&&typeof x.state==="string"&&x.state.trim()?x.state:"UNKNOWN",pid:typeof x.pid==="number"?x.pid:null,launcher:typeof x.launcher==="string"?x.launcher:null,mode:typeof x.mode==="string"&&x.mode.trim()?x.mode:"UNKNOWN",uptime_seconds:num(x.uptime_seconds),duration_seconds:num(x.duration_seconds),started_at:txt(x.started_at),feed_health,latest_snapshot_age,observed_at:new Date().toISOString(),supervisor:normalizeWatcher(x.supervisor,"supervisor"),sentinel:normalizeWatcher(x.sentinel,"sentinel"),run_id:txt(x.run_id),expected_end_at:txt(x.expected_end_at),elapsed_seconds:num(x.elapsed_seconds),remaining_seconds:num(x.remaining_seconds),last_exit_code:num(x.last_exit_code),last_exit_reason:txt(x.last_exit_reason),last_exit_at:txt(x.last_exit_at),process_state:txt(x.process_state)??"unknown",process_verified:x.process_verified===true,preset:txt(x.preset),...(typeof x.error==="string"?{error:x.error}:{})};
}
export const LAUNCH_PRESETS={brief:120,standard:3600,"validation-6h":21600} as const;
export type LaunchPreset=keyof typeof LAUNCH_PRESETS;
// Own-keys preset check (2026-10-14, review): `x in obj` walks the
// prototype chain, so "toString"/"constructor"/"__proto__" pass it.
// hasOwnProperty rejects every prototype member and any value outside
// the three allowlisted presets BEFORE any Python is spawned.
export function parseLaunchPreset(x:unknown):LaunchPreset|null{
 if(typeof x!=="string")return null;
 if(!Object.prototype.hasOwnProperty.call(LAUNCH_PRESETS,x))return null;
 return x as LaunchPreset;
}
// Capability query (2026-10-14, review): readiness must NOT certify the
// chain by callable() presence. It reads the ENABLED flag plus the
// explicit verification preconditions (finite positive budget,
// nonnegative poll), so a present-but-disabled or misconfigured
// controller stays BLOCKED.
export type LaunchCapability={present:boolean;enabled:boolean;verify_budget_s:number|null;poll_s:number|null};
const capabilityCode="import json,math;from microstructure_probe import control;f=getattr(control,'launch_supervised_transaction',None);b=getattr(control,'SUPERVISED_LAUNCH_VERIFY_BUDGET_S',None);p=getattr(control,'SUPERVISED_LAUNCH_POLL_S',None);print(json.dumps({'present':callable(f),'enabled':bool(getattr(control,'SUPERVISED_LAUNCH_ENABLED',False)),'verify_budget_s':b if isinstance(b,(int,float)) and math.isfinite(b) else None,'poll_s':p if isinstance(p,(int,float)) and math.isfinite(p) else None}))";
export function controllerLaunchCapability():LaunchCapability{
 const r=execute(capabilityCode,STATUS_BUDGET_MS);
 const d=r.data;
 return {present:r.ok&&d.present===true,enabled:r.ok&&d.enabled===true,
  verify_budget_s:r.ok&&typeof d.verify_budget_s==="number"?d.verify_budget_s:null,
  poll_s:r.ok&&typeof d.poll_s==="number"?d.poll_s:null};
}
export function controllerLaunchEnabled():boolean{
 const c=controllerLaunchCapability();
 return c.present&&c.enabled&&c.verify_budget_s!==null&&c.verify_budget_s>0&&c.poll_s!==null&&c.poll_s>=0;
}
function launchCode(preset:LaunchPreset):string{
 const seconds=LAUNCH_PRESETS[preset];
 return "import json;from microstructure_probe import control;print(json.dumps(control.launch_supervised_transaction(duration_seconds="+seconds+",launcher='dashboard',preset='"+preset+"')))";
}
function activeOwned(state:RuntimeState):boolean{
 return state.running||["STARTING","STOPPING"].includes(state.state);
}
export function runtimeAction(kind:"start"|"stop",preset?:unknown){
 if(kind==="start"){
  const chosen=parseLaunchPreset(preset===undefined?"brief":preset);
  if(chosen===null)return {ok:false,data:{error:"INVALID_PRESET",detail:"preset must be brief|standard|validation-6h"}};
  // Idempotency first: a retry while a run is active/starting/stopping
  // returns the live record and NEVER spawns a second probe.
  const before=runtimeStatus();
  if(!before.error&&activeOwned(before)&&before.launcher==="dashboard")
   return {ok:false,data:{error:"ALREADY_RUNNING",status:{state:before.state,pid:before.pid,launcher:before.launcher},retry:"reconcile-before-retry"}};
  if(!before.error&&activeOwned(before))
   return {ok:false,data:{error:"ALREADY_RUNNING_FOREIGN",status:{state:before.state,pid:before.pid,launcher:before.launcher},retry:"reconcile-before-retry"}};
  const r=execute(launchCode(chosen),START_BUDGET_MS);
  if(r.timeout){
   // Ambiguity is forbidden: the spawn may still confirm late, so
   // reconcile with a bounded status read instead of reporting failure.
   // The caller must reconcile (GET status/readiness) before any retry;
   // a retry re-enters this function and hits the pre-check above.
   const after=runtimeStatus();
   return {ok:false,data:{error:"START_TIMEOUT_UNCERTAIN",reason:"start exceeded its budget; result unknown until reconciled; never respawn without reconciling",preset:chosen,status:after.error?{error:after.error}:{state:after.state,pid:after.pid,launcher:after.launcher,running:after.running},retry:"reconcile-before-retry"}};
  }
  return r;
 }
 // Stop any verified project run (dashboard/agent/direct). The fixed script
 // refuses anything not recorded-running with a project launcher BEFORE
 // stop_probe; stop_probe itself revalidates PID+image+ctime under lock and
 // terminates only the verified canonical PID (never foreign processes).
 const code=pureStatusCode+"r=s if s.get('error') else ({'error':'not_project_owned','launcher':s.get('launcher')} if not s.get('running') or s.get('launcher') not in ('dashboard','agent','direct') else control.stop_probe(requester='dashboard-v2'));print(json.dumps(r))";
 return execute(code,STOP_BUDGET_MS);
}
export function requestAllowed(req:Request){
 const origin=req.headers.get("origin"),host=req.headers.get("host");
 return origin==="http://127.0.0.1:3020"&&host==="127.0.0.1:3020"&&req.headers.get("x-v2-action")==="observe-only"&&req.headers.get("sec-fetch-site")!=="cross-site";
}
