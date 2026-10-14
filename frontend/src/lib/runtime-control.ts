import {spawnSync} from "node:child_process";
import {normalizeWatcher, type WatcherEvidence} from "./supervision";
const ROOT="C:/proyectos/binance-futures-microstructure-bot";
const PY="python";
export type RuntimeState={running:boolean;state:string;pid:number|null;launcher:string|null;mode:string;uptime_seconds:number|null;duration_seconds:number|null;started_at:string|null;feed_health:string;latest_snapshot_age:number|null;observed_at?:string;supervisor?:WatcherEvidence;sentinel?:WatcherEvidence;error?:string};
function execute(code:string):{ok:boolean;data:Record<string,unknown>}{
 const p=spawnSync(PY,["-c",code],{cwd:ROOT,encoding:"utf8",timeout:4200,maxBuffer:262144,windowsHide:true,env:{...process.env,PYTHONPATH:ROOT+"/src"}});
 if(p.error||!p.stdout?.trim())return {ok:false,data:{error:"CANONICAL_CONTROLLER_UNAVAILABLE"}};
 try{
  const value:unknown=JSON.parse(p.stdout);
  if(!value||typeof value!=="object"||Array.isArray(value))return {ok:false,data:{error:"INVALID_CONTROLLER_RESPONSE"}};
  return {ok:p.status===0,data:value as Record<string,unknown>};
 }catch{return {ok:false,data:{error:"INVALID_CONTROLLER_RESPONSE"}}}
}
const pureStatusCode="import json;from microstructure_probe import control;f=getattr(control,'status_readonly',None);s=f() if callable(f) else {'error':'READ_ONLY_STATUS_REQUIRED'};";
const statusCode=pureStatusCode+"print(json.dumps(s))";
export function runtimeStatus():RuntimeState{
 const r=execute(statusCode);
 if(!r.ok||typeof r.data.error==="string")return {running:false,state:"UNKNOWN",pid:null,launcher:null,mode:"UNKNOWN",uptime_seconds:null,duration_seconds:null,started_at:null,feed_health:"UNKNOWN",latest_snapshot_age:null,observed_at:new Date().toISOString(),supervisor:normalizeWatcher(null,"supervisor"),sentinel:normalizeWatcher(null,"sentinel"),error:typeof r.data.error==="string"?r.data.error:"CANONICAL_CONTROLLER_UNAVAILABLE"};
 const x=r.data;
 return {running:x.running===true,state:typeof x.running==="boolean"&&typeof x.state==="string"&&x.state.trim()?x.state:"UNKNOWN",pid:typeof x.pid==="number"?x.pid:null,launcher:typeof x.launcher==="string"?x.launcher:null,mode:typeof x.mode==="string"&&x.mode.trim()?x.mode:"UNKNOWN",uptime_seconds:typeof x.uptime_seconds==="number"?x.uptime_seconds:null,duration_seconds:typeof x.duration_seconds==="number"?x.duration_seconds:null,started_at:typeof x.started_at==="string"?x.started_at:null,feed_health:"UNKNOWN",latest_snapshot_age:null,observed_at:new Date().toISOString(),supervisor:normalizeWatcher(x.supervisor,"supervisor"),sentinel:normalizeWatcher(x.sentinel,"sentinel"),...(typeof x.error==="string"?{error:x.error}:{})};
}
export const LAUNCH_PRESETS={brief:120,standard:3600,"validation-6h":21600} as const;
export type LaunchPreset=keyof typeof LAUNCH_PRESETS;
export function parseLaunchPreset(x:unknown):LaunchPreset|null{
 return typeof x==="string"&&x in LAUNCH_PRESETS?(x as LaunchPreset):null;
}
const launchProbeCode="import json;from microstructure_probe import control;print(json.dumps({'has_launch':callable(getattr(control,'launch_supervised_transaction',None))}))";
export function controllerHasLaunch():boolean{
 const r=execute(launchProbeCode);
 return r.ok&&(r.data as {has_launch?:unknown}).has_launch===true;
}
function launchCode(preset:LaunchPreset):string{
 const seconds=LAUNCH_PRESETS[preset];
 return "import json;from microstructure_probe import control;print(json.dumps(control.launch_supervised_transaction(duration_seconds="+seconds+",launcher='dashboard',preset='"+preset+"')))";
}
export function runtimeAction(kind:"start"|"stop",preset?:unknown){
 if(kind==="start"){
  const chosen=parseLaunchPreset(preset===undefined?"brief":preset);
  if(chosen===null)return {ok:false,data:{error:"INVALID_PRESET",detail:"preset must be brief|standard|validation-6h"}};
  return execute(launchCode(chosen));
 }
 const code=pureStatusCode+"r=s if s.get('error') else ({'error':'not_dashboard_owned','launcher':s.get('launcher')} if not s.get('running') or s.get('launcher')!='dashboard' else control.stop_probe(requester='dashboard-v2'));print(json.dumps(r))";
 return execute(code);
}
export function requestAllowed(req:Request){
 const origin=req.headers.get("origin"),host=req.headers.get("host");
 return origin==="http://127.0.0.1:3020"&&host==="127.0.0.1:3020"&&req.headers.get("x-v2-action")==="observe-only"&&req.headers.get("sec-fetch-site")!=="cross-site";
}
