import Link from "next/link";import {VerifiedPriceChart} from "./VerifiedPriceChart";
import { DataStateBadge, TierBadge, StatusChip } from "@/components/status/badges";
import type { TokenDetail as Detail } from "@/lib/token-detail";
import styles from "./TokenDetail.module.css";


type IconName = "layers" | "chart" | "check" | "document" | "database" | "clock" | "pulse" | "arrows";
const ICON_PATHS: Record<IconName, string> = {
 layers: "M12 3 3 8l9 5 9-5-9-5ZM3 12l9 5 9-5M3 16l9 5 9-5",
 chart: "M4 20V12M10 20V8M16 20V4M22 20H2",
 check: "M9 4H5v17h14V4h-4M9 3h6v4H9V3ZM8 13l3 3 5-6",
 document: "M6 3h9l4 4v14H6V3ZM14 3v5h5M9 12h7M9 16h7",
 database: "M20 6c0 2-4 3-8 3S4 8 4 6s4-3 8-3 8 1 8 3ZM4 6v12c0 2 4 3 8 3s8-1 8-3V6M4 12c0 2 4 3 8 3s8-1 8-3",
 clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 7v6l4 2",
 pulse: "M2 12h5l3-8 4 16 3-8h5",
 arrows: "M3 8h16l-4-4M21 16H5l4 4",
};
function DetailIcon({name}: {name: IconName}) {
 return <span className={styles.icon} aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" focusable="false"><path d={ICON_PATHS[name]}/></svg></span>;
}

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
    <div className={styles.stateHeader}><div className={styles.sectionTitle}><DetailIcon name="layers"/><div><h2>Market State Intelligence</h2><p>Classifier not connected · illustrative rules label {data.ruleVersion??"UNKNOWN"}</p></div></div></div>
    <div className={styles.classificationRow}><div className={styles.stateFlow} aria-label="Possible research states, not a mandatory progression">
      {STATE_SEQUENCE.map(state=><span key={state} className={state===data.state?styles.currentState:styles.inactiveState}>{state}</span>)}
    </div><div className={styles.status}><div><span className={styles.statusLabel}>Observed state</span><StatusChip label={data.state}/></div><div><span className={styles.statusLabel}>Direction</span><StatusChip label={data.direction}/></div><div><span className={styles.statusLabel}>Illustrative rules</span><strong>{data.ruleVersion??"UNKNOWN"}</strong></div></div></div>
    <p className={styles.notice}>No authoritative live classifier response is connected. UNKNOWN is intentional; static price fixtures cannot establish market state. States above describe possible categories, not a predicted sequence.</p>
    <div className={styles.stateEvidence}>
      <div><h3><DetailIcon name="check"/>Supporting evidence</h3>{data.evidence.length?<ul>{data.evidence.map(x=><li key={x}>{x}</li>)}</ul>:<p>No verified supporting evidence</p>}</div>
      <div><h3><DetailIcon name="document"/>Counterevidence</h3>{data.counterevidence.length?<ul>{data.counterevidence.map(x=><li key={x}>{x}</li>)}</ul>:<p>Not evaluated</p>}</div>
      <div><h3><DetailIcon name="database"/>Data gaps</h3><ul>{data.missing.map(x=><li key={x}>{x}</li>)}</ul></div>
      <div className={styles.auditCard}><h3><DetailIcon name="clock"/>Observation audit</h3><dl><dt>Previous state</dt><dd>{data.previousState??"UNKNOWN"}</dd><dt>Last authoritative evaluation</dt><dd>UNKNOWN</dd></dl></div>
    </div>
    <div className={styles.stateFoot}><span>Research only · No probability or trade recommendation</span><span>Classifier source: NOT CONNECTED</span></div>
  </section>
  <section className={styles.panel}><div className={styles.panelTop}><div className={styles.sectionTitle}><DetailIcon name="chart"/><div><h2>Microstructure Snapshot</h2><p>Static design examples only · NOT LIVE</p></div></div><span className={styles.count}>{validInputs}/{data.metrics.length} demo fields populated</span></div>
    <div className={styles.metricGrid}>{data.metrics.map(x=><div className={styles.metric} key={x.label}><div className={styles.metricTitle}><DetailIcon name={x.label.includes("flow")?"arrows":x.label.includes("book")?"database":x.label.includes("Return")?"chart":"pulse"}/><div><b>{x.label}</b><small>{x.context}</small></div></div><strong>{x.value??"—"}</strong></div>)}</div>
  </section>
  <div className={styles.columns}>
    <section className={styles.panel}><h2 className={styles.sectionTitle}><DetailIcon name="chart"/>Price and structure</h2><VerifiedPriceChart symbol={data.symbol}/></section>
    <section className={styles.panel}><h2 className={styles.sectionTitle}><DetailIcon name="document"/>Research history / transitions</h2><div className={styles.empty}><strong>No validated outcomes attached</strong><span>Transition timeline is a separately proposed feature. Historical hypotheses require P1-14 validation.</span><span className={styles.emptyBadge}>NOT EVALUATED</span></div></section>
  </div>
  <footer>RESEARCH ONLY · DEMO DATA — NOT LIVE · No trade recommendations, forecasts or P&amp;L.</footer>
 </div>;
}
