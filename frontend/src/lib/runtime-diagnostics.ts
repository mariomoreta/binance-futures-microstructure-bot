import {historicalRead} from "@/lib/historical-db";
import {runtimeStatus} from "@/lib/runtime-control";

type TelemetryRow = {
 timestamp:number; runtime_seconds:number;
 data_quality_json:string; clock_sync_json:string;
};
const parse=(value:unknown):Record<string,unknown>=>{
 try {
  const parsed:unknown=JSON.parse(String(value??"null"));
  return parsed&&typeof parsed==="object"&&!Array.isArray(parsed)
   ?parsed as Record<string,unknown>:{};
 } catch {return {}}
};
const finite=(value:unknown)=>typeof value==="number"&&Number.isFinite(value)?value:null;
const count=(value:unknown)=>{
 const number=finite(value);
 return number!==null&&number>=0?number:null;
};
const total=(value:unknown):number|null=>{
 if(typeof value==="number")return count(value);
 if(!value||typeof value!=="object"||Array.isArray(value))return null;
 const values=Object.values(value);
 if(!values.length)return null;
 const counts=values.map(count);
 return counts.some(x=>x===null)?null:counts.reduce<number>((a,b)=>a+(b??0),0);
};
const listCount=(value:unknown)=>Array.isArray(value)?value.length:null;

/** Observation time never establishes process/run identity or transport liveness. */
export function projectRecordedTelemetry(row:TelemetryRow,nowMs=Date.now()){
 const timestamp=finite(row.timestamp);
 if(timestamp===null||!Number.isFinite(nowMs))return null;
 const date=new Date(timestamp*1000);
 if(!Number.isFinite(date.getTime()))return null;
 const ageMs=nowMs-date.getTime();
 const quality=parse(row.data_quality_json),clock=parse(row.clock_sync_json);
 return {
  at:date.toISOString(),ageSeconds:Math.round(ageMs/1000),
  provenance:ageMs<0?"FUTURE_RECORDED_SAMPLE":
   ageMs<=90000?"RECENT_RECORDED_SAMPLE":"HISTORICAL_ONLY",
  expected:count(quality.expectedStreams),active:count(quality.activeStreams),
  missing:listCount(quality.missingStreams),stale:listCount(quality.staleStreams),
  silent:listCount(quality.silentStreams),
  rejected:total(quality.timestampRejected),reconnects:total(quality.reconnections),
  websocketErrors:total(quality.websocketErrors),
  parseErrors:total(quality.parseErrors),payloadErrors:total(quality.payloadErrors),
  clockOffsetMs:finite(clock.clockOffsetMs),runtimeSeconds:count(row.runtime_seconds),
 };
}
export function diagnostics(){
 const process=runtimeStatus();
 try{return historicalRead(db=>{
  const row=db.prepare("SELECT timestamp,runtime_seconds,data_quality_json,clock_sync_json FROM telemetry_snapshots ORDER BY id DESC LIMIT 1").get() as TelemetryRow|undefined;
  return {process,snapshot:row?projectRecordedTelemetry(row):null};
 })}catch{return {process,snapshot:null}}
}
