import Link from "next/link";
import type {ReactNode} from "react";
import {systemUtc,type SystemEvidenceResult} from "@/lib/system-evidence";
import s from "./RecordedSystemPanels.module.css";
const value=(x:unknown)=>x==null?"UNKNOWN":typeof x==="number"?x.toLocaleString("en-US"):String(x);
function Panel({title,eyebrow,children,note}:{title:string;eyebrow:string;children:ReactNode;note:string}){
 return <section className={s.panel} aria-label={title}><header><small>{eyebrow}</small><h2>{title}</h2><span className={s.tag}>RECORDED · NOT LIVE</span></header>{children}<p className={s.note}>{note}</p></section>;
}
function Rows({items}:{items:[string,unknown][]}){return <dl className={s.rows}>{items.map(([label,x])=><div key={label}><dt>{label}</dt><dd>{value(x)}</dd></div>)}</dl>}
function Missing(){return <p role="alert" className={s.note}>Source unavailable. No substitute values.</p>}
function Span({first,last}:{first:number|null;last:number|null}){return <p className={s.date}>Stored update span (UTC)<br/>{systemUtc(first)}<br/>→ {systemUtc(last)}</p>}
export function PersistencePanel({data}:{data:SystemEvidenceResult}){
 return <Panel title="Persistence evidence" eyebrow="CANONICAL STORE / SCHEMA 9" note="Allocated SQLite bytes describe logical database pages, not disk capacity or host usage. Read access is not a durability guarantee.">
 {data.available?<><Rows items={[["Telemetry snapshots",data.persistence.telemetry_rows],["Saved price samples",data.persistence.price_rows],["Allocated SQLite bytes",data.persistence.allocated_bytes],["Schema version",data.persistence.schema]]}/><p className={s.date}>Last telemetry UTC<br/>{systemUtc(data.persistence.last_telemetry_ms)}<br/>Last price bucket UTC<br/>{systemUtc(data.persistence.last_price_ms)}</p></>:<Missing/>}
 </Panel>;
}
export function ResearchPanel({data}:{data:SystemEvidenceResult}){
 return <Panel title="Research pipeline evidence" eyebrow="PROSPECTIVE ARCHIVE" note="Retained totals can span multiple runs. COMPLETE describes outcome recording, not a successful trade. Queue, drops and writer liveness remain UNKNOWN.">
 {data.available?<><Rows items={[["Retained setups",data.research.setups],["Retained outcomes",data.research.outcomes],["COMPLETE outcomes",data.research.complete_outcomes],["Opportunity lifecycle events",data.research.opportunity_events],["State transitions",data.research.state_transitions],["Recorder queue / drops","UNKNOWN"]]}/><p className={s.date}>Latest setup UTC<br/>{systemUtc(data.research.latest_setup_ms)}<br/>Latest outcome UTC<br/>{systemUtc(data.research.latest_outcome_ms)}</p><Link href="/historical-research">Open prospective archive →</Link></>:<Missing/>}
 </Panel>;
}
export function UniversePanel({data}:{data:SystemEvidenceResult}){
 return <Panel title="Universe allocation evidence" eyebrow="PERSISTED DISCOVERY" note="Lists reflect the saved discovery record. HOT subscribed is a recorded list, not proof of current websocket subscriptions. Counts include all retained rows; test-marked records have unverified origin. Capacity, cooldown and dwell budgets remain UNKNOWN.">
 {data.available?<><Rows items={[["CORE symbols (recorded)",data.universe.core],["HOT dynamic (recorded)",data.universe.hot_dynamic],["HOT subscribed list (recorded)",data.universe.hot_subscribed],["Eligible contracts at discovery",data.universe.eligible],["Retained universe rows (unaudited)",data.research.universe_events],["Rows flagged for provenance review",data.universe.unverified_test_detail_rows],["Subscription budget","UNKNOWN"]]}/><p className={s.date}>Discovery updated UTC<br/>{systemUtc(data.universe.updated_ms)}</p>{data.universe.unverified_test_detail_rows>0?<p role="status" className={s.warning}>{data.universe.unverified_test_detail_rows} records carry a test marker; origin is unverified. Retained counts are not certified operational activity.</p>:null}<Link href="/movers">Open retained market universe →</Link></>:<Missing/>}
 </Panel>;
}
export function ClassifierPanel({data}:{data:SystemEvidenceResult}){
 return <Panel title="Classifier & opportunity evidence" eyebrow="LATEST RETAINED ROW PER KEY" note="Aggregates mix independently dated records. ACTIVE_RESEARCH is a saved lifecycle label, not a live position. Versions are recorded rules, not running-engine attestation.">
 {data.available?<><Rows items={[["Retained classifications",data.classifier.records],["Retained candidate keys",data.opportunities.records],["Classifier rules recorded",data.classifier.versions.join(", ")||"UNKNOWN"],["Opportunity rules recorded",data.opportunities.versions.join(", ")||"UNKNOWN"]]}/>
 <div className={s.distributions}><div><h3>Saved market states</h3><Rows items={data.classifier.states.map(x=>[x.label,x.count])}/></div><div><h3>Saved candidate lifecycles</h3><Rows items={data.opportunities.lifecycles.map(x=>[x.label,x.count])}/></div></div>
 <Span first={data.classifier.span.first_ms} last={data.classifier.span.last_ms}/><p className={s.date}>Candidate stored update span (UTC)<br/>{systemUtc(data.opportunities.span.first_ms)}<br/>→ {systemUtc(data.opportunities.span.last_ms)}</p>
 {data.classifier.versions_truncated||data.opportunities.versions_truncated?<p className={s.note}>Version lists limited to 20 distinct labels per source.</p>:null}<Link href="/opportunities">Open recorded opportunities →</Link></>:<Missing/>}
 </Panel>;
}
export function ResourcePanel(){
 return <Panel title="Host & service coverage" eyebrow="ADAPTER AVAILABILITY" note="The connected SQLite telemetry schema has no host-resource columns. A dated host source and individual operational-event contract are still required.">
 <Rows items={[["CPU / memory","NOT AVAILABLE"],["Disk / network usage","NOT AVAILABLE"],["Writer liveness","UNKNOWN"],["Current service protection","UNKNOWN"],["Operational event feed","NOT CONNECTED"]]}/>
 </Panel>;
}
