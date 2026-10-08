"use client";
import {useEffect,useState} from "react";
import type {ProspectiveModel} from "@/lib/prospective-api";
import s from "./ProspectiveView.module.css";
export function ProspectiveView(){
 const [data,setData]=useState<ProspectiveModel|null>(null),[failure,setFailure]=useState(false);
 useEffect(()=>{const c=new AbortController();fetch("/api/v1/prospective",{cache:"no-store",signal:c.signal}).then(r=>{if(!r.ok)throw Error("Unreachable");return r.json() as Promise<ProspectiveModel>}).then(x=>{if(!c.signal.aborted)setData(x)}).catch(()=>{if(!c.signal.aborted)setFailure(true)});return()=>c.abort()},[]);
 if(failure)return <section role="alert" className={s.alert}>Prospective API unavailable. No results can be verified.</section>;
 if(!data)return <p role="status">Loading prospectively recorded data…</p>;
 const complete=data.latest_outcomes.filter(x=>x.outcome_state==="COMPLETE").length;
 return <><div className={s.alert}><strong>RESEARCH ONLY — NOT A TRADE SIGNAL</strong><p>These are stored observations. Completed horizons are not evidence of profitable execution. Source: {data.source}; generated at {data.generated_at??"UNKNOWN"}.</p></div>
 <div className={s.grid}>{[["Registered setups",data.setup_count],["Persisted outcomes",data.outcome_count],["Recent complete",complete],["Recorder state",data.status]].map(([k,v])=><section className={s.panel} key={String(k)}><small>{k}</small><strong>{v??"UNKNOWN"}</strong></section>)}</div>
 <section className={s.panel}><h2>Latest recorded outcomes</h2>{data.latest_outcomes.length===0?<p>No outcomes recorded. No outcomes does not imply zero returns.</p>:<div className={s.scroll}><table><thead><tr><th>Symbol</th><th>Horizon</th><th>State</th><th>Mark return</th><th>Observed UTC</th><th>Reason</th></tr></thead><tbody>{data.latest_outcomes.map((x,i)=><tr key={x.candidate_key+":"+x.horizon+":"+i}><td>{x.symbol}</td><td>{x.horizon}</td><td>{x.outcome_state}</td><td>{x.outcome_state==="COMPLETE"&&x.mark_return_pct!==null?x.mark_return_pct.toFixed(3)+"%":"—"}</td><td>{x.observed_at_ms===null?"UNKNOWN":new Date(x.observed_at_ms).toISOString()}</td><td>{x.reason}</td></tr>)}</tbody></table></div>}</section>
 <section className={s.panel}><h2>Integrity and limitations</h2><p>Reported recorder drops: {data.drops??"UNKNOWN"}. Errors: {data.errors??"UNKNOWN"}. No confidence, win-rate or net profit is inferred.</p><p>1m / 5m / 15m / 1h / 4h are target horizons; individual observation validity depends on timestamps, coverage and quality gates.</p></section></>
}
