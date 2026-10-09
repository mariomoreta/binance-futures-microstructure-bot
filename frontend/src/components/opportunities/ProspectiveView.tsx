"use client";
import {useEffect,useMemo,useState} from "react";
import type {ProspectiveModel} from "@/lib/prospective-api";
import s from "./ProspectiveView.module.css";
const HORIZONS=["1m","5m","15m","1h","4h"] as const;
const time=(x:number|null)=>x===null||!Number.isFinite(x)?"UNKNOWN":new Date(x).toISOString();
const price=(x:number|null)=>x===null?"UNKNOWN":x.toLocaleString("en-US",{maximumFractionDigits:8});
export function ProspectiveView(){
 const [data,setData]=useState<ProspectiveModel|null>(null),[failure,setFailure]=useState(false);
 useEffect(()=>{const c=new AbortController();fetch("/api/v1/prospective",{cache:"no-store",signal:c.signal}).then(r=>{if(!r.ok)throw Error("Unreachable");return r.json() as Promise<ProspectiveModel>}).then(x=>{if(!c.signal.aborted)setData(x)}).catch(()=>{if(!c.signal.aborted)setFailure(true)});return()=>c.abort()},[]);
 const horizonSummary=useMemo(()=>HORIZONS.map(h=>({h,count:data?.latest_outcomes.filter(x=>x.horizon===h&&x.outcome_state==="COMPLETE").length??0,missing:data?.latest_outcomes.filter(x=>x.horizon===h&&x.outcome_state!=="COMPLETE").length??0})),[data]);
 if(failure)return <section role="alert" className={s.alert}>Prospective API unavailable. No results can be verified. No substitute data displayed.</section>;
 if(!data)return <p role="status">Loading prospectively recorded data…</p>;
 const complete=data.latest_outcomes.filter(x=>x.outcome_state==="COMPLETE").length;
 return <div className={s.workspace}>
 <div className={s.alert}><strong>RESEARCH ONLY — NOT A TRADE SIGNAL</strong><p>Source: {data.source}. Retrieved snapshot: {data.generated_at??"UNKNOWN"}. The latest_outcomes API is a truncated recent list, not a complete historic cohort. Never interpret missing rows as zero returns.</p></div>
 <div className={s.grid}>{[["Registered setups",data.setup_count],["Stored outcomes",data.outcome_count],["Complete in latest list",complete],["Recorder status",data.status]].map(([k,v])=><section className={s.panel} key={String(k)}><small>{k}</small><strong>{v??"UNKNOWN"}</strong></section>)}</div>
 <section className={s.panel}><div className={s.sectionTitle}><h2>Outcome horizons</h2><span>Latest returned rows only · no maturity coverage claims</span></div><div className={s.horizons}>{horizonSummary.map(x=><div key={x.h}><span>{x.h}</span><strong>{x.count}</strong><small>COMPLETE in latest list</small>{x.missing>0?<small>{x.missing} other states</small>:null}</div>)}</div></section>
 <section className={s.panel}><div className={s.sectionTitle}><h2>Recorded observation ledger</h2><span>Mark-price change is observational, not executable P&amp;L</span></div>{data.latest_outcomes.length===0?<p>No outcomes returned. This does not imply zero returns.</p>:<div className={s.scroll}><table><thead><tr><th>Symbol</th><th>Horizon</th><th>Outcome</th><th>Detected mark</th><th>Observed mark</th><th>Return</th><th>Observed UTC</th><th>Reason</th></tr></thead><tbody>{data.latest_outcomes.map((x,i)=><tr key={x.candidate_key+":"+x.horizon+":"+i}><td className={s.symbol}>{x.symbol}</td><td>{x.horizon}</td><td>{x.outcome_state}</td><td>{price(x.detected_price)}</td><td>{price(x.current_price)}</td><td className={x.mark_return_pct!==null&&x.mark_return_pct>=0?s.positive:s.negative}>{x.outcome_state==="COMPLETE"&&x.mark_return_pct!==null?x.mark_return_pct.toFixed(4)+"%":"UNKNOWN"}</td><td>{time(x.observed_at_ms)}</td><td>{x.reason}</td></tr>)}</tbody></table></div>}</section>
 <section className={s.panel}><h2>Evidence quality and next gates</h2><p>Recorder drops: {data.drops??"UNKNOWN"} · Errors: {data.errors??"UNKNOWN"} · Source timestamp and maturity lateness not provided by this API response.</p><p>Target horizons: 1m, 5m, 15m, 1h and 4h. Do not infer success rates, calibrated probabilities, execution profit or market-state predictive power from these observations. The backend audit must establish full-cohort denominators.</p></section>
 </div>;
}
