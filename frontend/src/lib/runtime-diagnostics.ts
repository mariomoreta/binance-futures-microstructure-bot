import {historicalRead} from "@/lib/historical-db";
import {runtimeStatus} from "@/lib/runtime-control";
const parse=(x:unknown):Record<string,unknown>=>{try{return JSON.parse(String(x??"{}")) as Record<string,unknown>}catch{return {}}};
const n=(x:unknown)=>typeof x==="number"&&Number.isFinite(x)?x:null;
const total=(x:unknown)=>{if(typeof x==="number")return x;if(x&&typeof x==="object")return Object.values(x).reduce<number>((a,b)=>a+(typeof b==="number"?b:0),0);return null};
export function diagnostics(){
 const process=runtimeStatus();
 try{return historicalRead(db=>{
 const row=db.prepare("SELECT timestamp,runtime_seconds,data_quality_json,clock_sync_json FROM telemetry_snapshots ORDER BY id DESC LIMIT 1").get() as {timestamp:number;runtime_seconds:number;data_quality_json:string;clock_sync_json:string}|undefined;
 if(!row)return {process,snapshot:null};
 const q=parse(row.data_quality_json),clock=parse(row.clock_sync_json);
 const timestamp=row.timestamp*1000,ageMs=Date.now()-timestamp;
 const ownRun=!!process.running&&!!process.started_at&&timestamp>=Date.parse(process.started_at)-5000;
 const recent=ownRun&&ageMs>=-5000&&ageMs<=90000;
 return {process,snapshot:{at:new Date(timestamp).toISOString(),ageSeconds:Math.max(0,Math.round(ageMs/1000)),provenance:recent?"RECENT_FROM_ACTIVE_RUN":"HISTORICAL_ONLY",expected:n(q.expectedStreams),active:n(q.activeStreams),stale:Array.isArray(q.staleStreams)?q.staleStreams.length:null,silent:Array.isArray(q.silentStreams)?q.silentStreams.length:null,rejected:total(q.timestampRejected),reconnects:total(q.reconnections),websocketErrors:total(q.websocketErrors),clockOffsetMs:n(clock.clockOffsetMs),runtimeSeconds:row.runtime_seconds}};
 })}catch{return {process,snapshot:null}}
}
