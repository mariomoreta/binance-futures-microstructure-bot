import {spawnSync} from "node:child_process";
import {normalizeWatcher, type WatcherEvidence} from "./supervision";
import {historicalRead} from "./historical-db";
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
export type FeedAttribution="current"|"previous-run"|"none";
export type RuntimeState={running:boolean;state:string;pid:number|null;launcher:string|null;mode:string;uptime_seconds:number|null;duration_seconds:number|null;started_at:string|null;feed_health:string;latest_snapshot_age:number|null;observed_at?:string;supervisor?:WatcherEvidence;sentinel?:WatcherEvidence;error?:string;run_id?:string|null;expected_end_at?:string|null;elapsed_seconds?:number|null;remaining_seconds?:number|null;last_exit_code?:number|null;last_exit_reason?:string|null;last_exit_at?:string|null;process_state?:string;process_verified?:boolean;preset?:string|null;feed_attribution?:FeedAttribution;feed_note?:string|null};
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
// Feed quality gates (documented, never abort thresholds):
// - SUPERVISOR_REJECT_GATE = 0.05 is the enforced abort rule
//   (control.REJECT_ABORT_RATE: cumulative rejected/total on the latest
//   summary; a run above it is aborted as invalid observation). The BFF
//   never modifies it; it only refuses to call such data HEALTHY.
// - DASHBOARD_DEGRADED_REJECT = 0.5 is the looser legacy display concept
//   (dashboard.DEGRADED_REJECTION_RATE transport warning). It is NOT a
//   health claim: anything above the supervisor gate is already DEGRADED.
export const SUPERVISOR_REJECT_GATE=0.05;
export const DASHBOARD_DEGRADED_REJECT=0.5;
export const FEED_STALE_AFTER_S=120;
export const FEED_ATTRIBUTION_SKEW_S=60;
export type FeedEvidence={feed_health:string;latest_snapshot_age:number|null;feed_attribution:FeedAttribution;feed_note:string|null};
export type FeedRunWindow={started_at:string|null;last_exit_at:string|null;expected_end_at:string|null;state:string};
function feedUnknown(note:string,age:number|null=null):FeedEvidence{
 return {feed_health:"UNKNOWN",latest_snapshot_age:age,feed_attribution:"none",feed_note:note};
}
export function feedFromStore(window:FeedRunWindow={started_at:null,last_exit_at:null,expected_end_at:null,state:"UNKNOWN"}):FeedEvidence{
 const nowMs=Date.now();
 let row:{timestamp:unknown;data_quality_json:unknown}|undefined;
 try{
  row=historicalRead(db=>db.prepare("SELECT timestamp,data_quality_json FROM telemetry_snapshots ORDER BY id DESC LIMIT 1").get() as typeof row);
 }catch{return feedUnknown("telemetry-unavailable")}
 if(!row||typeof row.timestamp!=="number"||!Number.isFinite(row.timestamp))return feedUnknown("missing-timestamp");
 const tsMs=row.timestamp*1000;
 const ageS=Math.round(nowMs/1000-row.timestamp);
 if(!Number.isFinite(ageS)||ageS<0)return feedUnknown("invalid-timestamp");
 // Attribution: the row must fall inside the current run window
 // [started_at - skew, windowEnd + stale]. Otherwise it is evidence from
 // another (usually previous) run and must never render as current HEALTHY.
 const startMs=typeof window.started_at==="string"?Date.parse(window.started_at):NaN;
 let endMs=Number.isFinite(Date.parse(window.last_exit_at??""))?Date.parse(window.last_exit_at as string):NaN;
 if(!Number.isFinite(endMs)&&typeof window.expected_end_at==="string")endMs=Date.parse(window.expected_end_at);
 if(!Number.isFinite(endMs))endMs=nowMs;
 let attribution:FeedAttribution="none";
 if(Number.isFinite(startMs)){
  attribution=(tsMs>=startMs-FEED_ATTRIBUTION_SKEW_S*1000&&tsMs<=endMs+FEED_STALE_AFTER_S*1000)?"current":"previous-run";
 }
 if(attribution!=="current"){
  // Stale data from another run: surface its age but never as current health.
  return {feed_health:"UNKNOWN",latest_snapshot_age:ageS,feed_attribution:attribution==="previous-run"?"previous-run":"none",feed_note:attribution==="previous-run"?"previous-run-evidence":"unattributable-no-run-window"};
 }
 if(ageS>FEED_STALE_AFTER_S)return {feed_health:"STALE",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:null};
 // Fresh + attributable: HEALTHY requires complete, sufficient evidence.
 // Anything else is UNKNOWN (insufficient) or DEGRADED (bad quality) —
 // never HEALTHY by default.
 let q:Record<string,unknown>;
 try{
  const parsed:unknown=JSON.parse(String(row.data_quality_json??"null"));
  if(!parsed||typeof parsed!=="object"||Array.isArray(parsed))return {feed_health:"UNKNOWN",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"invalid-quality-json"};
  q=parsed as Record<string,unknown>;
 }catch{return {feed_health:"UNKNOWN",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"invalid-quality-json"}}
 const msgsRaw=q.messagesByStream;
 if(!msgsRaw||typeof msgsRaw!=="object"||Array.isArray(msgsRaw))return {feed_health:"UNKNOWN",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"missing-messages"};
 const counts=Object.values(msgsRaw as Record<string,unknown>);
 if(counts.length===0||counts.some(v=>typeof v!=="number"||!Number.isFinite(v)||v<0))return {feed_health:"UNKNOWN",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"missing-messages"};
 const total=counts.reduce<number>((a,v)=>a+(v as number),0);
 if(!(total>0))return {feed_health:"UNKNOWN",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"zero-messages"};
 if(!Array.isArray(q.staleStreams)||!Array.isArray(q.missingStreams)||!Array.isArray(q.silentStreams))return {feed_health:"UNKNOWN",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"missing-stream-lists"};
 if(typeof q.activeStreams!=="number"||typeof q.expectedStreams!=="number")return {feed_health:"UNKNOWN",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"missing-coverage"};
 // Error counters arrive as numbers or per-endpoint maps depending on the
 // probe summary shape; both are accepted, anything else is insufficient.
 const errTotal=(v:unknown):number|null=>{
  if(typeof v==="number")return Number.isFinite(v)&&v>=0?v:null;
  if(!v||typeof v!=="object"||Array.isArray(v))return null;
  let sum=0;
  for(const n of Object.values(v as Record<string,unknown>)){
   if(typeof n!=="number"||!Number.isFinite(n)||n<0)return null;
   sum+=n;
  }
  return sum;
 };
 const reconn=errTotal(q.reconnections);
 const parseErr=errTotal(q.parseErrors);
 const payloadErr=errTotal(q.payloadErrors);
 const wsErr=errTotal(q.websocketErrors);
 if(reconn===null||parseErr===null||payloadErr===null||wsErr===null)return {feed_health:"UNKNOWN",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"missing-error-counters"};
 if(typeof q.timestampRejected!=="number"||!Number.isFinite(q.timestampRejected)||q.timestampRejected<0)return {feed_health:"UNKNOWN",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"missing-reject-counter"};
 const stale=q.staleStreams as unknown[];
 const missing=q.missingStreams as unknown[];
 const silent=q.silentStreams as unknown[];
 const rate=q.timestampRejected/total;
 // Supervisor quality condition: a run whose latest summary exceeds the
 // 0.05 abort gate is invalid observation — the BFF reports DEGRADED and
 // never HEALTHY there, without touching the enforced threshold itself.
 if(stale.length>0)return {feed_health:"DEGRADED",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"stale-streams"};
 if(missing.length>0||q.activeStreams!==q.expectedStreams)return {feed_health:"DEGRADED",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"incomplete-coverage"};
 if(reconn>0||wsErr>0)return {feed_health:"DEGRADED",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"reconnects"};
 if(rate>SUPERVISOR_REJECT_GATE)return {feed_health:"DEGRADED",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"reject-rate-above-supervisor-gate"};
 if(parseErr>0||payloadErr>0)return {feed_health:"DEGRADED",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"parse-payload-errors"};
 // Event-driven !forceOrder@arr silence is normal; any other silent stream
 // means the snapshot does not cover the cadenced surface.
 if(silent.some(s=>s!=="!forceOrder@arr"))return {feed_health:"DEGRADED",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:"silent-streams"};
 return {feed_health:"HEALTHY",latest_snapshot_age:ageS,feed_attribution:"current",feed_note:null};
}
export function runtimeStatus():RuntimeState{
 const r=execute(statusCode,STATUS_BUDGET_MS);
 if(!r.ok||typeof r.data.error==="string")return {running:false,state:"UNKNOWN",pid:null,launcher:null,mode:"UNKNOWN",uptime_seconds:null,duration_seconds:null,started_at:null,feed_health:"UNKNOWN",latest_snapshot_age:null,observed_at:new Date().toISOString(),supervisor:normalizeWatcher(null,"supervisor"),sentinel:normalizeWatcher(null,"sentinel"),run_id:null,expected_end_at:null,elapsed_seconds:null,remaining_seconds:null,last_exit_code:null,last_exit_reason:null,last_exit_at:null,process_state:"unknown",process_verified:false,preset:null,feed_attribution:"none",feed_note:"controller-unavailable",error:typeof r.data.error==="string"?r.data.error:"CANONICAL_CONTROLLER_UNAVAILABLE"};
 const x=r.data;
 // Feed: canonical controller is registry-only (UNKNOWN without a dashboard
 // feed provider). Enrich best-effort from the recorded telemetry snapshot
 // attributed to THIS run window; never masks a controller error and never
 // invents liveness or current-run health from another run's evidence.
 let feed_health=typeof x.feed_health==="string"&&x.feed_health.trim()?x.feed_health:"UNKNOWN";
 let latest_snapshot_age=num(x.latest_snapshot_age);
 let feed_attribution:FeedAttribution="none";
 let feed_note:string|null=null;
 if(feed_health==="UNKNOWN"&&latest_snapshot_age===null){
  const f=feedFromStore({started_at:txt(x.started_at),last_exit_at:txt(x.last_exit_at),expected_end_at:txt(x.expected_end_at),state:typeof x.state==="string"?x.state:"UNKNOWN"});
  feed_health=f.feed_health;latest_snapshot_age=f.latest_snapshot_age;feed_attribution=f.feed_attribution;feed_note=f.feed_note;
 }
 return {running:x.running===true,state:typeof x.running==="boolean"&&typeof x.state==="string"&&x.state.trim()?x.state:"UNKNOWN",pid:typeof x.pid==="number"?x.pid:null,launcher:typeof x.launcher==="string"?x.launcher:null,mode:typeof x.mode==="string"&&x.mode.trim()?x.mode:"UNKNOWN",uptime_seconds:num(x.uptime_seconds),duration_seconds:num(x.duration_seconds),started_at:txt(x.started_at),feed_health,latest_snapshot_age,observed_at:new Date().toISOString(),supervisor:normalizeWatcher(x.supervisor,"supervisor"),sentinel:normalizeWatcher(x.sentinel,"sentinel"),run_id:txt(x.run_id),expected_end_at:txt(x.expected_end_at),elapsed_seconds:num(x.elapsed_seconds),remaining_seconds:num(x.remaining_seconds),last_exit_code:num(x.last_exit_code),last_exit_reason:txt(x.last_exit_reason),last_exit_at:txt(x.last_exit_at),process_state:txt(x.process_state)??"unknown",process_verified:x.process_verified===true,preset:txt(x.preset),feed_attribution,feed_note,...(typeof x.error==="string"?{error:x.error}:{})};
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
