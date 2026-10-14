import {historicalRead} from "@/lib/historical-db";
import s from "./SystemEvidence.module.css";
const obj=(value:unknown):Record<string,unknown>=>{try{const x=JSON.parse(String(value??"{}")) as unknown;return x!==null&&typeof x==="object"&&!Array.isArray(x)?x as Record<string,unknown>:{} }catch{return {}}};
const num=(value:unknown):number|null=>typeof value==="number"&&Number.isFinite(value)?value:null;
const count=(x:unknown):number|null=>Array.isArray(x)?x.length:null;
export function SystemEvidence(){
 let data:null|{timestamp:number;runtime:number;expected:number|null;active:number|null;stale:number|null;silent:number|null;offset:number|null;events:[string,number][];setups:number;outcomes:number;samples:number;mode:string;orders:number;keys:number;capital:number}=null;
 try{data=historicalRead(db=>{
  const t=db.prepare("SELECT timestamp,runtime_seconds,bot_mode,api_keys_used,real_orders_sent,real_capital_at_risk,data_quality_json,clock_sync_json,events_by_type_json FROM telemetry_snapshots ORDER BY id DESC LIMIT 1").get() as Record<string,unknown>|undefined;
  if(!t)return null;
  const quality=obj(t.data_quality_json),clock=obj(t.clock_sync_json),events=obj(t.events_by_type_json);
  const total=(table:string)=>Number((db.prepare("SELECT COUNT(*) n FROM "+table).get() as {n:number}).n);
  return {timestamp:Number(t.timestamp),runtime:Number(t.runtime_seconds),expected:num(quality.expectedStreams),active:num(quality.activeStreams),stale:count(quality.staleStreams),silent:count(quality.silentStreams),offset:num(clock.clockOffsetMs),events:Object.entries(events).filter((x):x is [string,number]=>typeof x[1]==="number"&&Number.isFinite(x[1])),setups:total("prospective_setups"),outcomes:total("prospective_outcomes"),samples:total("price_samples"),mode:String(t.bot_mode??"UNKNOWN"),orders:Number(t.real_orders_sent),keys:Number(t.api_keys_used),capital:Number(t.real_capital_at_risk)};
 })}catch{}
 return <section className={s.root} aria-label="Last persisted operational evidence"><div className={s.heading}><div><small>RECORDED OBSERVATIONS / SQLITE</small><h2>Last captured system evidence</h2><p>Historic run snapshot. These measurements do not establish current connectivity or present-day feed health.</p></div><span className={s.source}>PERSISTED · NOT LIVE</span></div>
 {!data?<p role="alert">No verified persisted telemetry available. Values remain unavailable.</p>:<>
 <p className={s.date}>Snapshot UTC: {new Date(data.timestamp*1000).toISOString()} · Last recorded runtime: {Math.round(data.runtime)} seconds · Mode at capture: {data.mode}</p>
 <div className={s.cards}>{[["Streams at capture",data.active===null||data.expected===null?"UNKNOWN":data.active+" / "+data.expected],["Stale streams",data.stale??"UNKNOWN"],["Silent streams",data.silent??"UNKNOWN"],["Clock offset",data.offset===null?"UNKNOWN":data.offset.toFixed(1)+" ms"],["Saved setups",data.setups],["Saved outcomes",data.outcomes],["Price samples",data.samples],["Orders at capture",data.orders]].map(([label,value])=><div key={String(label)}><small>{label}</small><strong>{value}</strong></div>)}</div>
 <div className={s.bottom}><div><h3>Recorded event counters</h3>{data.events.length?data.events.map(([key,n])=><p key={key}><span>{key.replaceAll("_"," ")}</span><strong>{n.toLocaleString()}</strong></p>):<p>Not available</p>}</div><div><h3>Observe-only safety evidence</h3><p><span>API keys recorded</span><strong>{data.keys}</strong></p><p><span>Capital at risk recorded</span><strong>{data.capital}</strong></p><p className={s.note}>Counters describe the archived snapshot, not a live safety attestation or a trading-performance result.</p></div></div>
 </>}</section>
}
