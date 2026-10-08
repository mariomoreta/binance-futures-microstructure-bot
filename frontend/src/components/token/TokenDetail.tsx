import Link from "next/link";
import { DataStateBadge, TierBadge, StatusChip } from "@/components/status/badges";
import { DemoPill } from "@/components/overview/TopBar";
import type { TokenDetail as Detail } from "@/lib/token-detail";
import styles from "./TokenDetail.module.css";

const STATE_SEQUENCE = ["NORMAL", "IGNITION", "EXPANSION", "EXHAUSTION", "REVERSAL"] as const;
export function TokenDetail({data}:{data:Detail}) {
 const ch=data.change24h;
 const validInputs=data.metrics.filter(x=>x.value!==null).length;
 return <main className={styles.page}>
  <header className={styles.header}><div><Link href="/movers">← Market Movers</Link><h1>{data.symbol}</h1><p>Binance USD-M Futures · Research Workspace</p></div><DemoPill /></header>
  <div className={styles.hero}>
   <div><small>Reference price · DEMO</small><strong>{data.price===null?"—":data.price.toLocaleString("en-US")} USDT</strong></div>
   <div><small>24h change · DEMO</small><strong>{ch===null?"—":`${ch>0?"+":""}${ch.toFixed(2)}%`}</strong></div>
   <div><small>Coverage</small><TierBadge tier={data.tier}/><DataStateBadge capability={data.capability}/></div>
  </div>
  <section className={styles.statePanel} aria-label="Market State Intelligence">
    <div className={styles.stateHeader}><div><h2>Market State Intelligence</h2><p>Observable classification · Python rules v{data.ruleVersion?.replace(/^v/,"")??"UNKNOWN"}</p></div><div className={styles.status}><StatusChip label={data.state}/><StatusChip label={data.direction}/></div></div>
    <div className={styles.stateFlow} aria-label="Possible research states, not a mandatory progression">
      {STATE_SEQUENCE.map(state=><span key={state} className={state===data.state?styles.currentState:styles.inactiveState}>{state}</span>)}
    </div>
    <p className={styles.notice}>No authoritative live classifier response is connected. UNKNOWN is intentional; static price fixtures cannot establish market state. States above describe possible categories, not a predicted sequence.</p>
    <div className={styles.stateEvidence}>
      <div><h3>Supporting evidence</h3>{data.evidence.length?<ul>{data.evidence.map(x=><li key={x}>{x}</li>)}</ul>:<p>No verified supporting evidence</p>}</div>
      <div><h3>Counterevidence</h3>{data.counterevidence.length?<ul>{data.counterevidence.map(x=><li key={x}>{x}</li>)}</ul>:<p>Not evaluated</p>}</div>
      <div><h3>Data gaps</h3><ul>{data.missing.map(x=><li key={x}>{x}</li>)}</ul></div>
    </div>
    <div className={styles.stateFoot}><span>Previous: {data.previousState??"UNKNOWN"}</span><span>Last authoritative evaluation: UNKNOWN</span><span>No probability or trade recommendation</span></div>
  </section>
  <section className={styles.panel}><div className={styles.panelTop}><div><h2>Microstructure Snapshot</h2><p>Static design examples only · NOT LIVE</p></div><span className={styles.count}>{validInputs}/{data.metrics.length} demo fields populated</span></div>
    <div className={styles.metricGrid}>{data.metrics.map(x=><div className={styles.metric} key={x.label}><div><b>{x.label}</b><small>{x.context}</small></div><strong>{x.value??"—"}</strong></div>)}</div>
  </section>
  <div className={styles.columns}>
    <section className={styles.panel}><h2>Price and structure</h2><div className={styles.empty}><strong>Awaiting verified candle series</strong><span>Chart, structure levels and event overlays require as-of aligned Python data.</span><span className={styles.emptyBadge}>NO SERIES · NOT LIVE</span></div></section>
    <section className={styles.panel}><h2>Research history / transitions</h2><div className={styles.empty}><strong>No validated outcomes attached</strong><span>Transition timeline is a separately proposed feature. Historical hypotheses require P1-14 validation.</span><span className={styles.emptyBadge}>NOT EVALUATED</span></div></section>
  </div>
  <footer>RESEARCH ONLY · DEMO DATA — NOT LIVE · No trade recommendations, forecasts or P&amp;L.</footer>
 </main>;
}
