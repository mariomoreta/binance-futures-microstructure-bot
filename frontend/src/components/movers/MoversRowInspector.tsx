import type {ProfessionalMover} from "@/lib/movers-domain";
import {formatCompact,formatPrice,formatSignedPct} from "@/lib/format";
import styles from "./MoversRowInspector.module.css";
const human=(x:number|null,suffix:string)=>x===null?"UNKNOWN":x.toExponential(3)+suffix;
export function MoversRowInspector({row}:{row:ProfessionalMover}){
 const items=[
 ["24h REST change",formatSignedPct(row.change24hPct),"Discovery context; not time-aligned with deep samples"],
 ["24h quote volume",formatCompact(row.quoteVolume24h),"Discovery context; not confirmed deep feed"],
 ["Fixture price",formatPrice(row.price),"Illustrative reference, not an executable market quote"],
 ["Velocity 1m",human(row.velocity1m,"/s"),"Deep feature fixture, not a probability"],
 ["Acceleration 1m",human(row.accel1m,"/s²"),"Deep feature fixture, not a predicted return"],
 ["Observation age",row.sampleAgeMs===null?"UNKNOWN":(row.sampleAgeMs/1000).toFixed(1)+" s","Fixture-relative age only; not current clock age"],
 ] as const;
 return <div className={styles.root}><header><strong>{row.symbol} · Evidence &amp; coverage</strong><span>DEMO FIXTURE · NO CURRENT MARKET CLAIM</span></header>
 <div className={styles.grid}>{items.map(([label,value,desc])=><div key={label}><small>{label}</small><strong>{value}</strong><p>{desc}</p></div>)}</div>
 <footer><span>Tier: {row.tier} · Capability: {row.capability} · Deep subscription fixture: {row.subscribed?"YES":"NO"}</span><span>Fixture as-of: {row.observedAt??"UNKNOWN"} · Source: {row.source}</span></footer>
 </div>;
}
