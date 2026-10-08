"use client";
import {useEffect,useState} from "react";
import type {OpportunityReadModel} from "@/lib/opportunities-api";
import styles from "./Observations.module.css";
export function Observations(){
 const [data,setData]=useState<OpportunityReadModel|null>(null);
 const [error,setError]=useState<string|null>(null);
 const [loading,setLoading]=useState(true);
 useEffect(()=>{const controller=new AbortController();fetch("/api/v1/opportunities",{cache:"no-store",signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error("Read-only backend unavailable");return r.json() as Promise<OpportunityReadModel>}).then(x=>{if(!controller.signal.aborted){setData(x);setLoading(false)}}).catch(()=>{if(!controller.signal.aborted){setError("Backend unavailable — cannot verify observations");setLoading(false)}});return()=>controller.abort()},[]);
 if(loading)return <section className={styles.panel} role="status">Loading persisted research records…</section>;
 if(error||!data)return <section className={styles.warning} role="alert">{error??"No validated response"}</section>;
 const sourceTime=data.as_of_ms===null?"UNKNOWN":new Date(data.as_of_ms).toISOString();
 return <><div className={styles.banner} role="status"><strong>{data.freshness} · HISTORICAL/PERSISTED</strong><span>Source: {data.source} · as-of {sourceTime}</span><span>These are saved observations, NOT current setups, trade signals or demonstrated predictive edges.</span></div>
 <div className={styles.grid}><div><small>Stored candidates</small><strong>{data.items.length}</strong></div><div><small>Data condition</small><strong>{data.freshness}</strong></div><div><small>API schema</small><strong>v{data.schema_version}</strong></div></div>
 <section className={styles.panel}><h2>Recorded candidates</h2>{data.items.length===0?<p>No valid candidates were returned. Missing does not mean zero performance.</p>:<div className={styles.scroll} tabIndex={0} role="region" aria-label="Persisted opportunity records"><table><thead><tr><th>Symbol</th><th>Research family</th><th>Lifecycle at observation</th><th>Market state</th><th>Research score</th><th>Observed UTC</th></tr></thead><tbody>{data.items.map((item,i)=><tr key={item.candidate_key||String(i)}><td>{item.symbol}</td><td>{item.setup_family.replaceAll("_"," ")}</td><td>{item.lifecycle}</td><td>{item.market_state} / {item.direction}</td><td>{item.ranking?.score??"—"}</td><td>{new Date(item.observed_at_ms).toISOString()}</td></tr>)}</tbody></table></div>}</section>
 <section className={styles.panel}><h2>Provenance and limitations</h2><p>Quality flags: {data.quality_flags.join(", ")||"UNKNOWN"}</p><p>Rule-specific evidence and counterevidence remain attached to individual backend records. This view does not infer execution prices or probabilities.</p></section></>
}
