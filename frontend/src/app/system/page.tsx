import {SystemEvidence} from "@/components/system/SystemEvidence";
import {BotControl} from "@/components/system/BotControl";
import styles from "./System.module.css";
const blocks=[
{title:"Market Engine",description:"Probe lifecycle and bounded universe",metric:"UNKNOWN",rows:[["Process","NOT CONNECTED"],["Runtime mode","READ-ONLY UI"],["Evaluation age","UNKNOWN"]]},
{title:"Data Feed",description:"Connections, freshness and timestamp integrity",metric:"UNKNOWN",rows:[["Active streams","UNKNOWN"],["Reconnects","UNKNOWN"],["Timestamp rejects","UNKNOWN"]]},
{title:"Research Recorder",description:"Prospective capture and integrity",metric:"UNKNOWN",rows:[["Writes / drops","UNKNOWN"],["Research queue","UNKNOWN"],["Last observation","UNKNOWN"]]},
{title:"Persistence",description:"Snapshots, schema and storage",metric:"UNKNOWN",rows:[["Database integrity","NOT CHECKED"],["Schema version","UNKNOWN"],["Stored rows","UNKNOWN"]]},
{title:"Universe Manager",description:"Protected CORE and bounded HOT coverage",metric:"UNKNOWN",rows:[["CORE active","UNKNOWN"],["HOT live","UNKNOWN"],["Stream budget","UNKNOWN"]]},
{title:"Classifier & Opportunity",description:"Rule versions, states and candidate lifecycle",metric:"UNKNOWN",rows:[["Classifier state","UNKNOWN"],["Research candidates","UNKNOWN"],["Rule versions","UNKNOWN"]]},
];
export default function SystemPage(){return <div className={styles.root} data-testid="system-v2">
<header className={styles.header}><div><h1>System & Research Health</h1><p>Infrastructure · transport · persistence · research pipeline</p></div><span className={styles.tag}>CONTROL CONNECTED · LEGACY TILES PENDING</span></header>
<BotControl/><SystemEvidence/><div className={styles.stats}>{[["Engine state","UNKNOWN"],["Feed state","UNKNOWN"],["Research state","UNKNOWN"],["Data freshness","UNKNOWN"]].map(([label,value])=><section className={styles.stat} key={label}><small>{label}</small><strong>{value}</strong><span>Awaiting verified runtime contract</span></section>)}</div>
<div className={styles.warning}><strong>Legacy diagnostic tiles are not yet connected.</strong><span>Operational status, stream counts and integrity checks are intentionally UNKNOWN. No healthy status is inferred from this preview. The canonical process controller above provides process status; the legacy cards below remain placeholders.</span></div>
<div className={styles.grid}>{blocks.map(block=><section className={styles.panel} key={block.title}><div className={styles.heading}><div><h2>{block.title}</h2><p>{block.description}</p></div><span className={styles.unknown}>{block.metric}</span></div><div className={styles.rows}>{block.rows.map(([k,v])=><div className={styles.row} key={k}><span>{k}</span><strong>{v}</strong></div>)}</div></section>)}</div>
<section className={styles.panel}><div className={styles.heading}><div><h2>System events and audit log</h2><p>Timestamped operational events require a verified API.</p></div><span className={styles.unknown}>NO FEED</span></div><div className={styles.empty}>No real events loaded. This view never invents uptime, errors, recoveries, or passing checks.</div></section>
<p className={styles.disclaimer}>RESEARCH ONLY · NOT LIVE · Canonical observe-only process control above. Legacy diagnostics below are placeholders; no account credentials, trading execution or fabricated telemetry.</p></div>}
