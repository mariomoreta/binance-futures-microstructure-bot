"use client";
import {UnavailableDataPanel} from "@/components/notices/UnavailableDataPanel";
import {useEffect,useState} from "react";
import type {LiveMoversModel} from "@/lib/live-movers";
import styles from "./LiveMoversView.module.css";
const fmt=(x:number|null,d=2)=>x===null?"UNKNOWN":x.toLocaleString("en-US",{maximumFractionDigits:d});
export function LiveMoversView(){
 const [data,setData]=useState<LiveMoversModel|null>(null),[error,setError]=useState<string|null>(null);
 useEffect(()=>{const c=new AbortController();fetch("/api/v1/live-movers",{cache:"no-store",signal:c.signal}).then(async r=>{if(!r.ok)throw Error("UNAVAILABLE");return r.json() as Promise<LiveMoversModel>}).then(v=>{if(!c.signal.aborted)setData(v)}).catch(()=>{if(!c.signal.aborted)setError("Python backend unavailable - no observations verified")});return()=>c.abort()},[]);
 if(error)return <UnavailableDataPanel title="Verified market observations" message={error} columns={["Symbol","Coverage","Price","Source","Freshness"]}/>;
 if(!data)return <section className={styles.notice} role="status">Checking persisted Python market data...</section>;
 return <><section className={styles.notice}><strong>PYTHON PERSISTED | RESEARCH ONLY</strong><p>Time alignment: {data.alignment} | Freshness: {data.freshness} | Retrieved: {data.generated_at}</p><p>Discovery: {data.sources.discovery?"AVAILABLE":"UNKNOWN"} | Momentum: {data.sources.momentum?"AVAILABLE":"UNKNOWN"} | These observations are not synchronized live quotes.</p></section>
 <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Symbol</th><th>Coverage</th><th>Price</th><th>Price source</th><th>Discovery 24h</th><th>Discovery volume</th><th>Deep velocity 1m</th><th>Sample age</th></tr></thead><tbody>{data.rows.map(r=><tr key={r.symbol}><td>{r.symbol}</td><td>{r.tier}</td><td>{fmt(r.price,6)}</td><td>{r.priceSource.toUpperCase()}</td><td>{r.discoveryEvidence&&r.change24hPct!==null?fmt(r.change24hPct)+"%":"UNKNOWN"}</td><td>{r.discoveryEvidence?fmt(r.quoteVolume24h,0):"UNKNOWN"}</td><td>{r.deepEvidence?fmt(r.velocity1m,8):"DISCOVERY ONLY"}</td><td>{r.sampleAgeMs===null?"UNKNOWN":fmt(r.sampleAgeMs/1000,1)+"s (snapshot)"}</td></tr>)}</tbody></table></div>{data.rows.length===0&&<p>No persisted rows available.</p>}<p className={styles.warning}>{data.warnings.join(" ")}</p></>;
}
