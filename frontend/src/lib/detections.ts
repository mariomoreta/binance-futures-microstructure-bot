import {spawnSync} from "node:child_process";
const ROOT="C:/proyectos/binance-futures-microstructure-bot";
const PY="python";
export const DETECTIONS_BUDGET_MS=4200;
export type DetectionEpisode={episode_id:string;symbol:string;funding_rate:number|null;repetitions:number|null;duplicate_records:number|null;first_observed_at:string|null;last_observed_at:string|null;duration_s:number|null;samples_first:number|null;samples_last:number|null;open_reason:string|null;close_reason:string|null};
export type DetectionsState={available:boolean;run_id:string|null;probe_run_id:string|null;grouping_version:string;events_total:number|null;episodes_total:number|null;skipped_records:number|null;episodes:DetectionEpisode[];limitation:string|null;observed_at:string;error?:string};
const code="import json;from microstructure_probe import control;print(json.dumps(control.read_run_detections()))";
const num=(v:unknown):number|null=>typeof v==="number"&&Number.isFinite(v)?v:null;
const txt=(v:unknown):string|null=>typeof v==="string"&&v.trim()?v:null;
function episode(v:unknown):DetectionEpisode{
 const x=v&&typeof v==="object"&&!Array.isArray(v)?v as Record<string,unknown>:{};
 return {episode_id:txt(x.episode_id)??"UNKNOWN",symbol:txt(x.symbol)??"UNKNOWN",funding_rate:num(x.funding_rate),
  repetitions:num(x.repetitions),duplicate_records:num(x.duplicate_records),
  first_observed_at:txt(x.first_observed_at),last_observed_at:txt(x.last_observed_at),
  duration_s:num(x.duration_s),samples_first:num(x.samples_first),samples_last:num(x.samples_last),
  open_reason:txt(x.open_reason),close_reason:txt(x.close_reason)};
}
// Read-only observation of the RECORDED run's retained funding evidence
// (registry evidence log only, bounded tail, canonical Python grouping).
// Missing evidence surfaces as unavailable/UNKNOWN — episodes are never
// invented from aggregates.
export function runDetections():DetectionsState{
 const observed_at=new Date().toISOString();
 let raw:Record<string,unknown>;
 try{
  const p=spawnSync(PY,["-c",code],{cwd:ROOT,encoding:"utf8",timeout:DETECTIONS_BUDGET_MS,maxBuffer:1048576,windowsHide:true,env:{...process.env,PYTHONPATH:ROOT+"/src"}});
  if(p.error||!p.stdout?.trim())return {available:false,run_id:null,probe_run_id:null,grouping_version:"v1",events_total:null,episodes_total:null,skipped_records:null,episodes:[],limitation:"detections-unavailable",observed_at,error:"CANONICAL_CONTROLLER_UNAVAILABLE"};
  const value:unknown=JSON.parse(p.stdout);
  if(!value||typeof value!=="object"||Array.isArray(value))return {available:false,run_id:null,probe_run_id:null,grouping_version:"v1",events_total:null,episodes_total:null,skipped_records:null,episodes:[],limitation:"detections-unavailable",observed_at,error:"INVALID_CONTROLLER_RESPONSE"};
  raw=value as Record<string,unknown>;
 }catch{return {available:false,run_id:null,probe_run_id:null,grouping_version:"v1",events_total:null,episodes_total:null,skipped_records:null,episodes:[],limitation:"detections-unavailable",observed_at,error:"CANONICAL_CONTROLLER_UNAVAILABLE"}}
 return {available:raw.available===true,run_id:txt(raw.run_id),probe_run_id:txt(raw.probe_run_id),
  grouping_version:txt(raw.grouping_version)??"v1",events_total:num(raw.events_total),episodes_total:num(raw.episodes_total),
  skipped_records:num(raw.skipped_records),episodes:Array.isArray(raw.episodes)?raw.episodes.map(episode):[],
  limitation:txt(raw.limitation),observed_at,...(typeof raw.error==="string"?{error:raw.error}:{})};
}
