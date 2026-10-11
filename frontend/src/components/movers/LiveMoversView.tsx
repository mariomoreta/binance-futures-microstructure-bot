"use client";
import {UnavailableDataPanel} from "@/components/notices/UnavailableDataPanel";
import {usePollingJson} from "@/lib/use-polling-json";
import type {LiveMoversModel} from "@/lib/live-movers";
import styles from "./LiveMoversView.module.css";
const fmt=(x:number|null,d=2)=>x===null?"UNKNOWN":x.toLocaleString("en-US",{maximumFractionDigits:d});
export function LiveMoversView(){
 const {data,error}=usePollingJson<LiveMoversModel>("/api/v1/live-movers");
 if(error)return <UnavailableDataPanel title="Verified market observations" message={error} columns={["Symbol","Coverage","Price","Source","Freshness"]}/>;
 if(!data)return <section className={styles.notice} role="status">Checking persisted Python market data...</section>;
 return <><section className={styles.notice}><strong>PYTHON PERSISTED | RESEARCH ONLY</strong><p>Time alignment: {data.alignment} | Freshness: {data.freshness} | Retrieved: {data.generated_at}</p><p>Discovery: {data.sources.discovery?"AVAILABLE":"UNKNOWN"} | Momentum: {data.sources.momentum?"AVAILABLE":"UNKNOWN"} | These observations are not synchronized live quotes.</p></section>
 <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Symbol</th><th>Coverage</th><th>Price</th><th>Price source</th><th>Discovery 24h</th><th>Discovery volume</th><th>Deep velocity 1m</th><th>Price age / as-of</th></tr></thead><tbody>{data.rows.map(r=><tr key={r.symbol}><td>{r.symbol}</td><td>{r.tier}</td><td>{fmt(r.price,6)}</td><td>{r.priceSource.toUpperCase()}</td><td>{r.discoveryEvidence&&r.change24hPct!==null?fmt(r.change24hPct)+"%":"UNKNOWN"}</td><td>{r.discoveryEvidence?fmt(r.quoteVolume24h,0):"UNKNOWN"}</td><td>{r.deepEvidence?fmt(r.velocity1m,8):"DISCOVERY ONLY"}</td><td title={"Price: "+((r as typeof r & {observedAt?:string}).observedAt??"UNKNOWN")+" · Discovery: "+((r as typeof r & {discoveryAsOf?:string}).discoveryAsOf??"UNKNOWN")+" · Features: "+((r as typeof r & {featureAsOf?:string}).featureAsOf??"UNKNOWN")}>{r.sampleAgeMs===null?"UNKNOWN":fmt(r.sampleAgeMs/1000,1)+"s (at DB read)"}</td></tr>)}</tbody></table></div>{data.rows.length===0&&<p>No persisted rows available.</p>}<p className={styles.warning}>{data.warnings.join(" ")}</p></>;
}
