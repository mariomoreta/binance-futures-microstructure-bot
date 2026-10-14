"use client";
import {useEffect,useRef,useState} from "react";
import type {RuntimeState} from "@/lib/runtime-control";
import {watcherDisplayState, type WatcherEvidence, type WatcherKind} from "@/lib/supervision";
import s from "./BotControl.module.css";

function WatcherPanel({kind,evidence,state}:{kind:WatcherKind;evidence:WatcherEvidence|undefined;state:string}) {
  const rows: [string, string|number|null|undefined][] = [
    ["Controller label", evidence?.state], ["Raw lease state", evidence?.lease_state],
    ["Watcher PID", evidence?.watcher_pid], ["Watcher created UTC", evidence?.watcher_create_time],
    ["Watched PID", evidence?.watched_pid], ["Run ID", evidence?.run_id],
    ["Lease heartbeat UTC", evidence?.lease_last_check_at], ["Reported heartbeat UTC", evidence?.last_check_at],
    ["Source", evidence?.supervision_source],
    ...(kind === "supervisor" ? [
      ["Abort triggered", evidence?.abort_triggered === true ? "YES" : evidence?.abort_triggered === false ? "NO" : null],
      ["Abort rule", evidence?.abort_rule], ["Abort reason", evidence?.abort_reason],
      ["Threshold", evidence?.abort_threshold], ["Observed", evidence?.abort_observed],
    ] as [string,string|number|null|undefined][] : [
      ["Action taken", evidence?.action_taken], ["Action reason", evidence?.action_reason],
    ] as [string,string|number|null|undefined][]),
  ];
  return <section className={s.supervisor} aria-label={kind + " evidence"}>
    <div className={s.supervisorHeading}><strong>{kind === "supervisor" ? "Persistent supervisor" : "Sentinel watchdog"}</strong><span>{state}</span></div>
    <div className={s.supervisorGrid}>{rows.map(([label,value]) => <div key={label}><small>{label}</small><b>{value ?? "UNKNOWN"}</b></div>)}</div>
  </section>;
}
export function BotControl(){
  const [state,setState]=useState<RuntimeState|null>(null),[busy,setBusy]=useState(false),
    [confirm,setConfirm]=useState(false),[message,setMessage]=useState(""),[now,setNow]=useState(Date.now);
  const [ready,setReady]=useState<boolean|null>(null);
  const [preset,setPreset]=useState<"brief"|"standard"|"validation-6h">("brief");
  const sequence=useRef(0);
  async function refresh(){
    const request=++sequence.current;
    try{
      const r=await fetch("/api/v1/runtime",{cache:"no-store"});
      if(!r.ok)throw Error();
      const result=await r.json() as RuntimeState;
      if(request===sequence.current){setState(result);setNow(Date.now())}
    }catch{
      if(request===sequence.current)setState({state:"UNKNOWN",running:false,pid:null,launcher:null,
        mode:"UNKNOWN",uptime_seconds:null,duration_seconds:null,started_at:null,feed_health:"UNKNOWN",
        latest_snapshot_age:null,error:"STATUS_UNAVAILABLE"});
    }
    try{
      const r=await fetch("/api/v1/runtime/readiness",{cache:"no-store"});
      if(!r.ok)throw Error();
      const result=await r.json() as {ready?:unknown};
      if(request===sequence.current)setReady(result.ready===true);
    }catch{
      if(request===sequence.current)setReady(null);
    }
  }
  useEffect(()=>{
    const first=setTimeout(()=>{void refresh()},0);
    const timer=setInterval(()=>{void refresh()},10000);
    const clock=setInterval(()=>setNow(Date.now()),1000);
    return()=>{clearTimeout(first);clearInterval(timer);clearInterval(clock);sequence.current++};
  },[]);
  const supervisor=watcherDisplayState("supervisor",state?.supervisor,state?.pid,state?.observed_at,now);
  const sentinel=watcherDisplayState("sentinel",state?.sentinel,state?.pid,state?.observed_at,now);
  const owned=state?.running===true&&state?.launcher==="dashboard";
  const canStart=ready===true&&!busy;
  const canStop=owned&&state?.state==="RUNNING"&&!state?.error;
  const presetSeconds=preset==="brief"?120:preset==="standard"?3600:21600;
  async function action(kind:"start"|"stop"){
    setBusy(true);setMessage("");
    try{
      const r=await fetch("/api/v1/runtime/"+kind,{method:"POST",headers:{"content-type":"application/json","x-v2-action":"observe-only"},
        body:JSON.stringify(kind==="start"?{confirm:"START_OBSERVE_2100",preset}:{confirm:"STOP_DASHBOARD_SESSION"})});
      const body=await r.json() as {error?:string;outcome?:string};
      setMessage(r.ok?(kind==="start"?"Observe-only monitor started via supervised chain ("+body.outcome+").":"Dashboard-owned monitor stopped."):(body.error??"Action rejected by controller"));
    }catch{setMessage("Controller request failed. No success confirmed.")}
    finally{setConfirm(false);setBusy(false);await refresh()}
  }
  const cards=[
    ["Recorded process",state?.state??"LOADING"],["Data feed",state?.feed_health??"UNKNOWN"],
    ["Supervisor",supervisor.replace("SUPERVISOR_","")],["Sentinel",sentinel.replace("SENTINEL_","")],
    ["Runtime mode",state?.mode?.toUpperCase()??"UNKNOWN"],
  ];
  return <section className={s.root} aria-label="Bot Control Center">
    <div className={s.header}><div><small>CANONICAL CONTROLLER / OBSERVE-ONLY MONITORING</small></div><button className={s.refresh} onClick={()=>void refresh()} type="button">Refresh status</button></div>
    <div className={s.stats}>{cards.map(([label,value])=><div key={label}><small>{label}</small><strong>{value}</strong><span>Controller observation / polled every 10s</span></div>)}</div>
    <p className={s.foot}>Process state is recorded in the runtime registry; current process liveness is not reported by this endpoint. Feed, supervisor and sentinel are independent. ACTIVE is a point-in-time controller observation, not proof of continuing protection. Freshness bound: 90s.</p>
    {state?.error?<p role="alert" className={s.warn}>{state.error==="READ_ONLY_STATUS_REQUIRED" ? "Runtime observation is paused until status can be reported without changing runtime records. Commands are disabled." : <>Canonical status unavailable — commands are disabled. {state.error}</>}</p>:null}
    <details className={s.inspector}><summary>Runtime controls & supervisor evidence<span>Inspect supervisor, sentinel, ownership and abort details</span></summary>
      <div className={s.details}><span>Observed UTC: <b>{state?.observed_at??"UNKNOWN"}</b></span></div>
      <WatcherPanel kind="supervisor" evidence={state?.supervisor} state={supervisor}/>
      <WatcherPanel kind="sentinel" evidence={state?.sentinel} state={sentinel}/>
      <div className={s.details}><span>PID: <b>{state?.pid??"UNKNOWN"}</b></span><span>Elapsed since start: <b>{state?.uptime_seconds==null?"UNKNOWN":Math.round(state.uptime_seconds)+"s"}</b></span><span>Planned duration: <b>{state?.duration_seconds==null?"UNKNOWN":Math.round(state.duration_seconds)+"s"}</b></span><span>Started UTC: <b>{state?.started_at??"UNKNOWN"}</b></span></div>
      {state?.running&&state.launcher!=="dashboard"?<p className={s.warn}>A session launched by {state.launcher??"another process"} is recorded. V2 will not stop or replace it.</p>:null}
      <div className={s.actions}><label>Preset <select aria-label="Launch preset" value={preset} onChange={e=>setPreset(e.target.value as typeof preset)} disabled={busy}><option value="brief">brief · 120s</option><option value="standard">standard · 3600s</option><option value="validation-6h">validation-6h · 21600s</option></select></label><button type="button" disabled={!canStart||busy} onClick={()=>{setConfirm(true);setMessage("")}}>Start monitor (requires supervised launch)</button><button type="button" disabled={!canStop||busy} onClick={()=>{setConfirm(true);setMessage("")}}>Stop dashboard-owned monitor</button></div>
      {confirm?<div className={s.confirm}><p>Confirm one observe-only action. Duration is fixed to {presetSeconds}s ({preset} preset). No automatic restart and no trading access. Launch requires readiness-green plus this confirmation.</p><button disabled={busy} onClick={()=>void action(canStop?"stop":"start")} type="button">Confirm {canStop?"stop":"start"}</button><button disabled={busy} onClick={()=>setConfirm(false)} type="button">Cancel</button></div>:null}
      {message?<p role="status" className={s.warn}>{message}</p>:null}
      <p className={s.foot}>Unknown health is not healthy. Start requires readiness-green, confirmation and a bounded preset through the supervised chain (probe + supervisor + sentinel, verified identity, kill-only rollback).</p>
    </details>
  </section>;
}