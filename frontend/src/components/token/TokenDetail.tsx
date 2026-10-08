import Link from "next/link";
import { DataStateBadge, TierBadge, StatusChip } from "@/components/status/badges";
import { DemoPill } from "@/components/overview/TopBar";
import type { TokenDetail as Detail } from "@/lib/token-detail";
import styles from "./TokenDetail.module.css";

export function TokenDetail({data}:{data:Detail}) {
 const ch=data.change24h;
 return <main className={styles.page}>
  <header className={styles.header}><div><Link href="/movers">← Market Movers</Link><h1>{data.symbol}</h1><p>Binance USD-M Futures · Research Workspace</p></div><DemoPill /></header>
  <div className={styles.hero}>
   <div><small>Reference price · DEMO</small><strong>{data.price===null?"—":data.price.toLocaleString("en-US")} USDT</strong></div>
   <div><small>24h change · DEMO</small><strong>{ch===null?"—":`${ch>0?"+":""}${ch.toFixed(2)}%`}</strong></div>
   <div><small>Coverage</small><TierBadge tier={data.tier}/><DataStateBadge capability={data.capability}/></div>
  </div>
  <div className={styles.columns}>
   <section className={styles.panel}><h2>Market State Intelligence</h2><p className={styles.status}><StatusChip label={data.state}/><StatusChip label={data.direction}/><span>Rules: {data.ruleVersion??"UNKNOWN"}</span></p>
    <p className={styles.notice}>No authoritative live classifier response is connected. UNKNOWN is intentional; static price fixtures cannot establish market state.</p>
    <div className={styles.twocol}><div><h3>Supporting evidence</h3>{data.evidence.length?<ul>{data.evidence.map(x=><li key={x}>{x}</li>)}</ul>:<p>Not available</p>}</div><div><h3>Counterevidence</h3>{data.counterevidence.length?<ul>{data.counterevidence.map(x=><li key={x}>{x}</li>)}</ul>:<p>Not evaluated</p>}</div></div>
    <h3>Missing inputs</h3><ul>{data.missing.map(x=><li key={x}>{x}</li>)}</ul><p>Previous state: {data.previousState??"UNKNOWN"}</p>
   </section>
   <section className={styles.panel}><h2>Microstructure Snapshot</h2><p>Static design examples only · NOT LIVE</p>{data.metrics.map(x=><div className={styles.metric} key={x.label}><div><b>{x.label}</b><small>{x.context}</small></div><strong>{x.value??"—"}</strong></div>)}</section>
  </div>
  <div className={styles.columns}><section className={styles.panel}><h2>Price and structure</h2><div className={styles.empty}>No verified price series connected. Future API will supply time-aligned candles and structure.</div></section><section className={styles.panel}><h2>Historical research / transitions</h2><div className={styles.empty}>Historical outcomes and state timeline not yet connected. Timeline is a proposed future feature.</div></section></div>
  <footer>RESEARCH ONLY · DEMO DATA — NOT LIVE · No trade recommendations, forecasts or P&amp;L.</footer>
 </main>;
}
