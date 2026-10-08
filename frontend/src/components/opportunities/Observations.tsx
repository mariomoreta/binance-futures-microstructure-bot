"use client";
import {useEffect,useMemo,useState} from "react";
import type {OpportunityApiRow,OpportunityReadModel} from "@/lib/opportunities-api";
import styles from "./Observations.module.css";

function Evidence({title,values}:{title:string;values:string[]}){return <div className={styles.evidence}><h3>{title}</h3>{values.length?<ul>{values.map((v,i)=><li key={i}>{v}</li>)}</ul>:<p>Not recorded — UNKNOWN</p>}</div>}
export function Observations(){
 const [data,setData]=useState<OpportunityReadModel|null>(null);
 const [error,setError]=useState<string|null>(null);
 const [loading,setLoading]=useState(true);
 const [selected,setSelected]=useState<string|null>(null);
 useEffect(()=>{const controller=new AbortController();fetch("/api/v1/opportunities",{cache:"no-store",signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error("Read-only backend unavailable");return r.json() as Promise<OpportunityReadModel>}).then(x=>{if(!controller.signal.aborted){setData(x);setLoading(false)}}).catch(()=>{if(!controller.signal.aborted){setError("Backend unavailable — cannot verify observations");setLoading(false)}});return()=>controller.abort()},[]);
 const rows=data?.items;
 const active:OpportunityApiRow|undefined=useMemo(()=>rows?.find(x=>x.candidate_key===selected)??rows?.[0],[rows,selected]);
 if(loading)return <section className={styles.panel} role="status">Loading persisted research records…</section>;
 if(error||!data)return <section className={styles.warning} role="alert">{error??"No validated response"}</section>;
 const sourceTime=data.as_of_ms===null?"UNKNOWN":new Date(data.as_of_ms).toISOString();
 return <><div className={styles.banner} role="status"><strong>{data.freshness} · HISTORICAL/PERSISTED</strong><span>Source: {data.source} · as-of {sourceTime}</span><span>Saved observations are NOT current setups, trade signals or demonstrated predictive edges.</span></div>
 <div className={styles.grid}><div><small>Stored candidates</small><strong>{data.items.length}</strong></div><div><small>Data condition</small><strong>{data.freshness}</strong></div><div><small>API schema</small><strong>v{data.schema_version}</strong></div></div>
 <div className={styles.columns}>
 <section className={styles.panel}><h2>Recorded candidates</h2>{data.items.length===0?<p>No valid candidates returned. Missing does not mean zero performance.</p>:<div className={styles.scroll} tabIndex={0} role="region" aria-label="Persisted opportunity records"><table><thead><tr><th>Symbol</th><th>Research family</th><th>Lifecycle</th><th>Market state</th><th>Priority</th><th>Observed UTC</th></tr></thead><tbody>{data.items.map((item,i)=><tr key={item.candidate_key||String(i)} className={active===item?styles.activeRow:""}><td><button className={styles.pick} type="button" aria-label={`Inspect saved ${item.symbol} ${item.setup_family}`} aria-pressed={active===item} onClick={()=>setSelected(item.candidate_key)}>{item.symbol}</button></td><td>{item.setup_family.replaceAll("_"," ")}</td><td>{item.lifecycle}</td><td>{item.market_state} / {item.direction}</td><td>{item.ranking?.score??"—"}</td><td>{new Date(item.observed_at_ms).toISOString()}</td></tr>)}</tbody></table></div>}</section>
 <aside className={styles.panel} aria-label="Saved candidate evidence"><h2>Evidence inspector</h2>{active?<><h3 className={styles.symbol}>{active.symbol}</h3><p>{active.setup_family.replaceAll("_"," ")} · {active.lifecycle} · {active.direction}</p><div className={styles.detailGrid}><div><small>Research priority</small><strong>{active.ranking?.score??"UNKNOWN"}</strong></div><div><small>Rule version</small><strong>{active.rule_version||"UNKNOWN"}</strong></div></div><Evidence title="Supporting evidence" values={active.evidence_for}/><Evidence title="Counterevidence" values={active.evidence_against}/><Evidence title="Missing features" values={active.missing_features}/><p className={styles.historical}>Historical evidence: {active.historical_reference?.status||"UNKNOWN"}</p><p>Saved at {new Date(active.observed_at_ms).toISOString()}. This observation is not a current signal.</p></>:<p>Select a saved record for evidence. No observed records available.</p>}</aside></div>
 <section className={styles.panel}><h2>Provenance and limitations</h2><p>Quality flags: {data.quality_flags.join(", ")||"UNKNOWN"}</p><p>Research priority is not probability or expected profit. No executable fills, positions, costs or outcomes are inferred.</p></section></>;
}
