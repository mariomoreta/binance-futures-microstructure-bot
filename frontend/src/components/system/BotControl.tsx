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
const UNCERTAIN_START="Start outcome UNCERTAIN (HTTP 202): the launch may still confirm late. Reconciling by status read — success is announced only on explicit dashboard-owned confirmation. No new launch while uncertain.";
export function BotControl(){
  const [state,setState]=useState<RuntimeState|null>(null),[busy,setBusy]=useState(false),
    [confirm,setConfirm]=useState(false),[message,setMessage]=useState(""),[now,setNow]=useState(Date.now);
  const [ready,setReady]=useState<boolean|null>(null);
  const [preset,setPreset]=useState<"brief"|"standard"|"validation-6h">("brief");
  const sequence=useRef(0);
  // Pending uncertain start: set on HTTP 202, cleared ONLY by reconcile
  // (explicit dashboard-owned RUNNING with started_at at/after the
  // request, or a read proving no active run). Never cleared by time.
  type Pending={at:number;quiet:number};
  const [pendingStart,setPendingStart]=useState<Pending|null>(null);
  const pendingRef=useRef<Pending|null>(null);
  function setPending(value:Pending|null){setPendingStart(value);pendingRef.current=value;}
  function reconcile(next:RuntimeState|null,p:Pending):void{
    if(next===null||next.error){return}
    if(next.running===true&&next.launcher==="dashboard"&&next.started_at){
      const started=Date.parse(next.started_at);
      if(Number.isFinite(started)&&started>=p.at){
        setPending(null);
        setMessage("Observe-only monitor confirmed via supervised chain (dashboard-owned pid "+String(next.pid)+", started "+next.started_at+").");
        return;
      }
      setPending({at:p.at,quiet:0});
      return;
    }
    if(next.running!==true&&!["STARTING","STOPPING"].includes(next.state)){
      // One inactive read right after a timed-out spawn races the
      // server-side verification (late confirmation still possible), so
      // it never clears. Two consecutive inactive reads on the poll
      // cadence (>=10s apart) are reconcile-grade; the controller
      // pre-check still guards any new start.
      if(p.quiet+1>=2){
        setPending(null);
        setMessage("Reconciled: no active dashboard run recorded across consecutive reads. The uncertain start was never confirmed; a new start is allowed (the controller pre-check still prevents duplicates).");
      }else{
        setPending({at:p.at,quiet:p.quiet+1});
      }
      return;
    }
    setPending({at:p.at,quiet:0});
  }
  async function refresh(){
    const request=++sequence.current;
    const pending=pendingRef.current;
    try{
      const r=await fetch("/api/v1/runtime",{cache:"no-store"});
      if(!r.ok)throw Error();
      const result=await r.json() as RuntimeState;
      if(request===sequence.current){setState(result);setNow(Date.now());if(pending)reconcile(result,pending)}
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
  const canStart=ready===true&&!busy&&pendingStart===null;
  const canStop=owned&&state?.state==="RUNNING"&&!state?.error;
  const presetSeconds=preset==="brief"?120:preset==="standard"?3600:21600;
  async function action(kind:"start"|"stop"){
    setBusy(true);setMessage("");
    const at=Date.now();
    try{
      const r=await fetch("/api/v1/runtime/"+kind,{method:"POST",headers:{"content-type":"application/json","x-v2-action":"observe-only"},
        body:JSON.stringify(kind==="start"?{confirm:"START_OBSERVE_2100",preset}:{confirm:"STOP_DASHBOARD_SESSION"})});
      const body=await r.json() as {error?:string;outcome?:string;stopped?:unknown};
      if(kind==="start"&&(r.status===202||body.error==="START_TIMEOUT_UNCERTAIN")){
        // HTTP 202 is NEVER success: keep the outcome pending, block any
        // new launch, and reconcile by status read (refresh in finally).
        setPending({at,quiet:0});
        setMessage(UNCERTAIN_START);
      }else{
        if(pendingStart!==null&&kind==="start")setPending(null);
        // Separate success criteria per action (2026-10-14): start needs
        // outcome==="confirmed"; stop needs stopped===true. A valid stop
        // carries no outcome field and must not read as rejected.
        const succeeded=kind==="start"?r.ok&&body.outcome==="confirmed":r.ok&&body.stopped===true;
        setMessage(succeeded?(kind==="start"?"Observe-only monitor started via supervised chain ("+body.outcome+").":"Dashboard-owned monitor stopped."):(body.error??"Action rejected by controller"));
      }
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