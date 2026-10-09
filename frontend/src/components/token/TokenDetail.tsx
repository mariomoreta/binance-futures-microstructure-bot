import Link from "next/link";import {VerifiedPriceChart} from "./VerifiedPriceChart";
import { DataStateBadge, TierBadge, StatusChip } from "@/components/status/badges";
import type { TokenDetail as Detail } from "@/lib/token-detail";
import styles from "./TokenDetail.module.css";

const STATE_SEQUENCE = ["NORMAL", "IGNITION", "EXPANSION", "EXHAUSTION", "REVERSAL"] as const;
export function TokenDetail({data}:{data:Detail}) {
 const ch=data.change24h;
 const validInputs=data.metrics.filter(x=>x.value!==null).length;
 const fixtureTime = data.asOf === null ? null : new Date(data.asOf).toLocaleString("en-US", { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" });
 return <div className={styles.page}>
  <header className={styles.header}><div><Link href="/movers">← Market Movers</Link><h1>{data.symbol}</h1><p>Binance USD-M Futures · Research Workspace</p></div></header>
  <aside className={styles.provenance} aria-label="Token dataset provenance">
    <strong>{fixtureTime ? "STATIC DEMO FIXTURE" : "NO SYMBOL FIXTURE"} · NOT LIVE</strong>
    <span>{fixtureTime ? `Example as-of: ${fixtureTime} UTC · historical fixture, not current market data` : "No symbol-specific observation or timestamp available"}</span>
    <span>Classifier API: NOT CONNECTED</span>
  </aside>
  <div className={styles.hero}>
   <div><small>Reference price · DEMO</small><strong>{data.price===null?"—":data.price.toLocaleString("en-US")} USDT</strong></div>
   <div><small>24h change · DEMO</small><strong data-tone={ch === null ? "unknown" : ch > 0 ? "positive" : ch < 0 ? "negative" : "neutral"}>{ch===null?"—":`${ch>0?"+":""}${ch.toFixed(2)}%`}</strong></div>
   <div><small>Coverage · DEMO</small><TierBadge tier={data.tier}/><DataStateBadge capability={data.capability}/></div>
  </div>
  <section className={styles.statePanel} aria-label="Market State Intelligence">
    <div className={styles.stateHeader}><div><h2>Market State Intelligence</h2><p>Classifier not connected · illustrative rules label {data.ruleVersion??"UNKNOWN"}</p></div><div className={styles.status}><span className={styles.statusLabel}>Observed state</span><StatusChip label={data.state}/><span className={styles.statusLabel}>Direction</span><StatusChip label={data.direction}/></div></div>
    <div className={styles.stateFlow} aria-label="Possible research states, not a mandatory progression">
      {STATE_SEQUENCE.map(state=><span key={state} className={state===data.state?styles.currentState:styles.inactiveState}>{state}</span>)}
    </div>
    <p className={styles.notice}>No authoritative live classifier response is connected. UNKNOWN is intentional; static price fixtures cannot establish market state. States above describe possible categories, not a predicted sequence.</p>
    <div className={styles.stateEvidence}>
      <div><h3>Supporting evidence</h3>{data.evidence.length?<ul>{data.evidence.map(x=><li key={x}>{x}</li>)}</ul>:<p>No verified supporting evidence</p>}</div>
      <div><h3>Counterevidence</h3>{data.counterevidence.length?<ul>{data.counterevidence.map(x=><li key={x}>{x}</li>)}</ul>:<p>Not evaluated</p>}</div>
      <div><h3>Data gaps</h3><ul>{data.missing.map(x=><li key={x}>{x}</li>)}</ul></div>
      <div className={styles.auditCard}><h3>Observation audit</h3><dl><dt>Previous state</dt><dd>{data.previousState??"UNKNOWN"}</dd><dt>Last authoritative evaluation</dt><dd>UNKNOWN</dd></dl></div>
    </div>
    <div className={styles.stateFoot}><span>Research only · No probability or trade recommendation</span><span>Classifier source: NOT CONNECTED</span></div>
  </section>
  <section className={styles.panel}><div className={styles.panelTop}><div><h2>Microstructure Snapshot</h2><p>Static design examples only · NOT LIVE</p></div><span className={styles.count}>{validInputs}/{data.metrics.length} demo fields populated</span></div>
    <div className={styles.metricGrid}>{data.metrics.map(x=><div className={styles.metric} key={x.label}><div><b>{x.label}</b><small>{x.context}</small></div><strong>{x.value??"—"}</strong></div>)}</div>
  </section>
  <div className={styles.columns}>
    <section className={styles.panel}><h2>Price and structure</h2><VerifiedPriceChart symbol={data.symbol}/></section>
    <section className={styles.panel}><h2>Research history / transitions</h2><div className={styles.empty}><strong>No validated outcomes attached</strong><span>Transition timeline is a separately proposed feature. Historical hypotheses require P1-14 validation.</span><span className={styles.emptyBadge}>NOT EVALUATED</span></div></section>
  </div>
  <footer>RESEARCH ONLY · DEMO DATA — NOT LIVE · No trade recommendations, forecasts or P&amp;L.</footer>
 </div>;
}
