"use client";
import Link from "next/link";
import {useEffect,useRef,useState} from "react";
import type {RuntimeState} from "@/lib/runtime-control";
import {watcherDisplayState} from "@/lib/supervision";
import s from "./RunStatusBar.module.css";

function fmtSecs(v:number|null):string{
 if(v===null||!Number.isFinite(v))return "UNKNOWN";
 return Math.round(v)+"s";
}
function fmtClock(v:number|null):string{
 if(v===null)return "UNKNOWN";
 return Math.round(v)+"s";
}

export function RunStatusBar(){
 const [state,setState]=useState<RuntimeState|null>(null);
 const [now,setNow]=useState(Date.now());
 const seq=useRef(0);
 async function refresh(){
  const id=++seq.current;
  try{
   const r=await fetch("/api/v1/runtime",{cache:"no-store"});
   if(!r.ok)throw new Error();
   const body=await r.json() as RuntimeState;
   if(id===seq.current){setState(body);setNow(Date.now());}
  }catch{
   if(id===seq.current)setState({state:"UNKNOWN",running:false,pid:null,launcher:null,mode:"UNKNOWN",uptime_seconds:null,duration_seconds:null,started_at:null,feed_health:"UNKNOWN",latest_snapshot_age:null,run_id:null,expected_end_at:null,elapsed_seconds:null,remaining_seconds:null,last_exit_code:null,last_exit_reason:null,last_exit_at:null,process_state:"unknown",process_verified:false,preset:null,error:"STATUS_UNAVAILABLE"});
  }
 }
 useEffect(()=>{
  const t0=setTimeout(()=>{void refresh()},0);
  const t1=setInterval(()=>{void refresh()},10000);
  const clk=setInterval(()=>setNow(Date.now()),1000);
  return ()=>{clearTimeout(t0);clearInterval(t1);clearInterval(clk);seq.current++;};
 },[]);
 const supervisor=state?watcherDisplayState("supervisor",state.supervisor,state.pid,state.observed_at,now).replace("SUPERVISOR_",""):"…";
 const sentinel=state?watcherDisplayState("sentinel",state.sentinel,state.pid,state.observed_at,now).replace("SENTINEL_",""):"…";
 const terminal=state&&!["RUNNING","STARTING","STOPPING"].includes(state.state);
 // Live remaining: age the recorded remaining by time since observation.
 let remainingLive: number|null = state?.remaining_seconds ?? null;
 if(state?.running&&state.state==="RUNNING"&&remainingLive!==null&&state.observed_at){
  const obs=Date.parse(state.observed_at);
  if(Number.isFinite(obs))remainingLive=Math.max(0,remainingLive-(now-obs)/1000);
 }
 const dot=state?.error?"bad":state?.running?"live":terminal?"end":"idle";
 return <div className={s.bar} data-testid="run-status-bar" role="status" aria-label="Global run status">
  <span className={`${s.dot} ${s[dot]}`} aria-hidden="true" />
  <div className={s.main}>
   <span className={s.line}>
    <strong data-testid="rsb-recorded">{state?`RECORDED ${state.state}`:"LOADING"}</strong>
    <span data-testid="rsb-verified">VERIFY {state?(state.process_verified?"OWNED-LIVE":"NOT-LIVE ("+state.process_state+")"):"…"}</span>
    <span data-testid="rsb-origin">ORIGIN {state?.launcher??"…"}</span>
    <span data-testid="rsb-run">RUN {state?.run_id??"…"}</span>
   </span>
   <span className={s.line}>
    <span data-testid="rsb-start">START {state?.started_at??"…"}</span>
    <span data-testid="rsb-duration">PLAN {fmtSecs(state?.duration_seconds??null)}</span>
    {terminal
      ?<span data-testid="rsb-terminal">END {state?.last_exit_reason??"UNKNOWN"} · CLOSE {state?.last_exit_at??"UNKNOWN"} · FROZEN {fmtClock(state?.elapsed_seconds??state?.uptime_seconds??null)}</span>
      :<span data-testid="rsb-remaining">LEFT {fmtClock(remainingLive)}</span>}
   </span>
   <span className={s.line}>
    <span data-testid="rsb-feed">FEED {state?.feed_health??"…"}{state?.latest_snapshot_age!==null&&state?.latest_snapshot_age!==undefined?` ${state.latest_snapshot_age}s`:""}</span>
    <span data-testid="rsb-supervisor">SUP {supervisor}</span>
    <span data-testid="rsb-sentinel">SEN {sentinel}</span>
    {state?.error?<span data-testid="rsb-error">OFFLINE {state.error}</span>:null}
   </span>
  </div>
  <Link className={s.link} href="/system">System →</Link>
 </div>;
}
