"use client";
import {useEffect,useState} from "react";
import type {DetectionsState} from "@/lib/detections";
import s from "./DetectionEpisodes.module.css";

// Recorded-run funding interpretation (research only): raw events vs
// grouped episodes under the versioned rule. Episodes describe
// repetition; they are not independent samples and never entry
// signals. Unvalidated funding stays labeled as research.
export function DetectionEpisodes(){
 const [state,setState]=useState<DetectionsState|null>(null);
 async function refresh(){
  try{
   const r=await fetch("/api/v1/detections",{cache:"no-store"});
   if(!r.ok)throw new Error();
   setState(await r.json() as DetectionsState);
  }catch{
   setState({available:false,run_id:null,probe_run_id:null,grouping_version:"v1",events_total:null,episodes_total:null,skipped_records:null,episodes:[],limitation:"detections-unavailable",observed_at:new Date().toISOString()});
  }
 }
 useEffect(()=>{const t0=setTimeout(()=>{void refresh()},0);const t1=setInterval(()=>{void refresh()},30000);return ()=>{clearTimeout(t0);clearInterval(t1)};},[]);
 if(state===null)return <section className={s.root} aria-label="Detection episodes"><p className={s.note}>Loading recorded detection evidence…</p></section>;
 if(!state.available)return <section className={s.root} aria-label="Detection episodes"><h2>Detection episodes · research</h2><p className={s.note}>UNKNOWN — {state.limitation??"no recorded funding evidence"}. Episodes are not reconstructed from aggregates.</p></section>;
 return <section className={s.root} aria-label="Detection episodes">
  <div className={s.heading}><div><small>RESEARCH ONLY · DESCRIPTIVE GROUPING</small><h2>Detection episodes</h2><p>Raw funding events vs grouped episodes (rule {state.grouping_version}). Run {state.run_id??"UNKNOWN"}{state.probe_run_id?` · probe ${state.probe_run_id.slice(0,8)}…`:" · probe link UNKNOWN"} · observed {state.observed_at}</p></div>
  <div className={s.counts}><div><small>Raw events</small><strong data-testid="ep-events">{state.events_total??"UNKNOWN"}</strong></div><div><small>Grouped episodes</small><strong data-testid="ep-episodes">{state.episodes_total??"UNKNOWN"}</strong></div><div><small>Skipped records</small><strong>{state.skipped_records??"UNKNOWN"}</strong></div></div></div>
  {state.limitation?<p className={s.note}>Limitation: {state.limitation}.</p>:null}
  <p className={s.note}>Episodes describe repetition within a run; they are not independent samples and never entry signals. Funding thresholds remain unvalidated hypotheses.</p>
  {state.episodes.length?<div className={s.table} role="table" aria-label="Grouped episodes">{state.episodes.slice(0,50).map(e=><div role="row" key={e.episode_id}><span role="cell">{e.symbol}</span><span role="cell">{e.funding_rate??"—"}</span><span role="cell">×{e.repetitions??"—"}</span><span role="cell">{e.duration_s==null?"—":e.duration_s+"s"}</span><span role="cell">{e.first_observed_at??"—"}</span><span role="cell">{e.open_reason??"—"}→{e.close_reason??"—"}</span></div>)}</div>:<p className={s.note}>No funding episodes in the recorded evidence.</p>}
 </section>;
}
