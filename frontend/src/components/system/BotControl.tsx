"use client";
import {useEffect,useState} from "react";
import s from "./BotControl.module.css";
type Status={state:string;running:boolean;pid:number|null;launcher:string|null;mode:string;uptime_seconds:number|null;duration_seconds:number|null;started_at:string|null;feed_health:string;error?:string};
export function BotControl(){
 const [state,setState]=useState<Status|null>(null),[busy,setBusy]=useState(false),[confirm,setConfirm]=useState(false),[message,setMessage]=useState("");
 async function refresh(){try{const r=await fetch("/api/v1/runtime",{cache:"no-store"});if(!r.ok)throw Error();setState(await r.json() as Status)}catch{setState({state:"UNKNOWN",running:false,pid:null,launcher:null,mode:"observe",uptime_seconds:null,duration_seconds:null,started_at:null,feed_health:"UNKNOWN",error:"STATUS_UNAVAILABLE"})}}
 useEffect(()=>{const first=setTimeout(()=>{void refresh()},0);const timer=setInterval(()=>{void refresh()},10000);return()=>{clearTimeout(first);clearInterval(timer)}},[]);
 const owned=state?.running===true&&state?.launcher==="dashboard";
 const canStart=state?.state==="STOPPED"||state?.state==="COMPLETED"||state?.state==="FAILED";
 const canStop=owned&&state?.state==="RUNNING";
 async function action(kind:"start"|"stop"){setBusy(true);setMessage("");try{const r=await fetch("/api/v1/runtime/"+kind,{method:"POST",headers:{"content-type":"application/json","x-v2-action":"observe-only"},body:JSON.stringify({confirm:kind==="start"?"START_OBSERVE_2100":"STOP_DASHBOARD_SESSION"})});const body=await r.json() as {error?:string;started?:boolean;stopped?:boolean};setMessage(r.ok?(kind==="start"?"Observe-only monitor started.":"Dashboard-owned monitor stopped."):(body.error??"Action rejected by controller"))}catch{setMessage("Controller request failed. No success confirmed.")}finally{setConfirm(false);setBusy(false);await refresh()}}
 return <section className={s.root} aria-label="Bot Control Center"><div className={s.header}><div><small>CANONICAL PROCESS CONTROLLER</small><h2>Bot Control Center</h2><p>Observe-only monitoring. No live trading, private keys, orders or funds.</p></div><button className={s.refresh} onClick={()=>void refresh()} type="button">Refresh status</button></div>
 <div className={s.stats}>{[["Process",state?.state??"LOADING"],["Feed health",state?.feed_health??"UNKNOWN"],["Started by",state?.launcher?.toUpperCase()??"UNKNOWN"],["Mode",state?.mode?.toUpperCase()??"UNKNOWN"]].map(([k,v])=><div key={k}><small>{k}</small><strong>{v}</strong></div>)}</div>
 <div className={s.details}><span>PID: <b>{state?.pid??"UNKNOWN"}</b></span><span>Uptime: <b>{state?.uptime_seconds==null?"UNKNOWN":Math.round(state.uptime_seconds)+"s"}</b></span><span>Planned duration: <b>{state?.duration_seconds==null?"UNKNOWN":Math.round(state.duration_seconds)+"s"}</b></span><span>Started UTC: <b>{state?.started_at??"UNKNOWN"}</b></span></div>
 {state?.error?<p role="alert" className={s.warn}>Canonical status unavailable — commands are disabled. {state.error}</p>:null}
 {state?.running&&state.launcher!=="dashboard"?<p className={s.warn}>A session launched by {state.launcher??"another process"} is detected. V2 will not stop or replace it.</p>:null}
 <div className={s.actions}><button type="button" disabled={!canStart||busy} onClick={()=>{setConfirm(true);setMessage("")}}>Start 35-min observe monitor</button><button type="button" disabled={!canStop||busy} onClick={()=>{setConfirm(true);setMessage("")}}>Stop dashboard-owned monitor</button></div>
 {confirm?<div className={s.confirm}><p>Confirm one observe-only action. Duration is fixed to 35 minutes. No automatic restart and no trading access.</p><button disabled={busy} onClick={()=>void action(canStop?"stop":"start")} type="button">Confirm {canStop?"stop":"start"}</button><button disabled={busy} onClick={()=>setConfirm(false)} type="button">Cancel</button></div>:null}
 {message?<p role="status" className={s.warn}>{message}</p>:null}
 <p className={s.foot}>Process state is independent of feed health. Unknown health is not healthy. Refresh uses the canonical Python lifecycle manager; control requests are limited to loopback and explicit confirmation.</p></section>
}
