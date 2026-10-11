import type {ProfessionalMover} from "@/lib/movers-domain";
import {formatCompact,formatPrice,formatSignedPct} from "@/lib/format";
import styles from "./MoversRowInspector.module.css";
const human=(x:number|null,suffix:string)=>x===null?"UNKNOWN":x.toExponential(3)+suffix;
export function MoversRowInspector({row}:{row:ProfessionalMover}){
 const items=[
 ["24h REST change",formatSignedPct(row.change24hPct),"Discovery context; not time-aligned with deep samples"],
 ["24h quote volume",formatCompact(row.quoteVolume24h),"Discovery context; not confirmed deep feed"],
 ["Recorded price",formatPrice(row.price),"Stored reference, not an executable market quote"],
 ["Velocity 1m",human(row.velocity1m,"/s"),"Stored deep feature, not a probability"],
 ["Acceleration 1m",human(row.accel1m,"/s²"),"Stored deep feature, not a predicted return"],
 ["Observation age",row.sampleAgeMs===null?"UNKNOWN":(row.sampleAgeMs/1000).toFixed(1)+" s","Age at last DB read; not proof of current feed liveness"],
 ] as const;
 return <div className={styles.root}><header><strong>{row.symbol} · Evidence &amp; coverage</strong><span>PERSISTED RECORD · NO CURRENT MARKET CLAIM</span></header>
 <div className={styles.grid}>{items.map(([label,value,desc])=><div key={label}><small>{label}</small><strong>{value}</strong><p>{desc}</p></div>)}</div>
 <footer><span>Tier: {row.tier} · Capability: {row.capability} · Retained deep evidence: {row.subscribed?"YES":"NO"}</span><span>Price as-of: {row.observedAt??"UNKNOWN"} · Source: {row.source} / {row.priceSource??"UNKNOWN"} · Discovery: {row.discoveryAsOf??"UNKNOWN"} · Deep features: {row.featureAsOf??"UNKNOWN"}</span></footer>
 </div>;
}
